"""
replace_block Tool

基於內容簽名的區塊替換工具，使用「內容匹配」取代「行號定位」，
提供更安全、更精確的檔案修改能力。

支援功能：
1. find_content - 精確內容匹配
2. find_signature - 帶上下文的簽名匹配（推薦）
3. dry_run - 預覽模式
4. validate_syntax - Python 語法驗證
5. occurrence - 多匹配時指定目標
"""
import logging
import subprocess
from dataclasses import dataclass
from datetime import datetime
from difflib import unified_diff
from pathlib import Path
from typing import Any

from mcp_server.config import MAX_INPUT_LENGTH
from mcp_server.schemas import ExecutionResult
from mcp_server.tools.base import registry

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 資料結構
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class MatchResult:
    """匹配結果"""
    line_start: int        # 1-based 行號
    line_end: int          # 1-based 行號
    content: str           # 匹配到的原始內容
    before_matched: bool   # 前文是否匹配
    after_matched: bool    # 後文是否匹配
    before_line: int | None   # 前文所在行號
    after_line: int | None    # 後文所在行號
    confidence: float      # 匹配置信度 (0.0 ~ 1.0)


# ═══════════════════════════════════════════════════════════════════════════════
# Tool 註冊
# ═══════════════════════════════════════════════════════════════════════════════

@registry.register(
    name="replace_block",
    description=(
        "基於內容簽名的區塊替換工具。"
        "使用「內容匹配」取代「行號定位」，更安全地修改檔案。"
        "支援精確匹配 (find_content) 和上下文簽名匹配 (find_signature)。"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "要修改的檔案路徑（絕對路徑）"
            },
            "find_content": {
                "type": "string",
                "description": "要尋找並替換的內容（精確匹配）"
            },
            "find_signature": {
                "type": "object",
                "description": "上下文簽名匹配（更精確）",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "要匹配的核心內容"
                    },
                    "context_before": {
                        "type": "string",
                        "description": "目標區塊之前的內容（向上搜尋）"
                    },
                    "context_after": {
                        "type": "string",
                        "description": "目標區塊之後的內容（向下搜尋）"
                    },
                    "context_range": {
                        "type": "integer",
                        "description": "上下文搜尋範圍（行數），預設 50",
                        "default": 50
                    }
                },
                "required": ["content"]
            },
            "replace_with": {
                "type": "string",
                "description": "替換後的新內容"
            },
            "occurrence": {
                "type": "integer",
                "description": "當有多個匹配時，指定要替換第幾個（1-based），預設 1",
                "minimum": 1,
                "default": 1
            },
            "dry_run": {
                "type": "boolean",
                "description": "預覽模式：顯示修改差異但不實際寫入",
                "default": False
            },
            "validate_syntax": {
                "type": "boolean",
                "description": "是否驗證 Python 檔案的語法正確性（僅對 .py 檔案有效）",
                "default": False
            },
            "require_all_context": {
                "type": "boolean",
                "description": "使用 find_signature 時，是否要求所有上下文都必須匹配（預設 True）",
                "default": True
            }
        },
        "required": ["file_path", "replace_with"],
        "oneOf": [
            {"required": ["find_content"]},
            {"required": ["find_signature"]}
        ]
    }
)
async def handle_replace_block(args: dict[str, Any]) -> ExecutionResult:
    """處理 replace_block 請求"""
    file_path = args.get("file_path")
    find_content = args.get("find_content")
    find_signature = args.get("find_signature")
    replace_with = args.get("replace_with")
    occurrence = args.get("occurrence", 1)
    dry_run = args.get("dry_run", False)
    validate_syntax = args.get("validate_syntax", False)
    require_all_context = args.get("require_all_context", True)

    # 參數驗證
    if not file_path or not isinstance(file_path, str):
        raise ValueError("必須提供有效的 file_path 參數")

    # find_content 和 find_signature 至少要有一個
    if not find_content and not find_signature:
        raise ValueError("必須提供 find_content 或 find_signature 參數")

    if find_content and find_signature:
        raise ValueError("find_content 和 find_signature 不能同時使用")

    if replace_with is None:
        replace_with = ""
    elif not isinstance(replace_with, str):
        replace_with = str(replace_with)

    if len(replace_with) > MAX_INPUT_LENGTH:
        raise ValueError(f"replace_with 超過最大長度限制 {MAX_INPUT_LENGTH} 字符")

    if not isinstance(occurrence, int) or occurrence < 1:
        occurrence = 1

    mode_str = "[預覽模式]" if dry_run else "[實際寫入]"
    match_mode = "簽名匹配" if find_signature else "精確匹配"
    logger.info(f"{mode_str} replace_block: {file_path} ({match_mode})")

    return await replace_block(
        file_path=file_path,
        find_content=find_content,
        find_signature=find_signature,
        replace_with=replace_with,
        occurrence=occurrence,
        dry_run=dry_run,
        validate_syntax=validate_syntax,
        require_all_context=require_all_context
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 核心邏輯
# ═══════════════════════════════════════════════════════════════════════════════

async def replace_block(
    file_path: str,
    find_content: str | None,
    find_signature: dict[str, Any] | None,
    replace_with: str,
    occurrence: int = 1,
    dry_run: bool = False,
    validate_syntax: bool = False,
    require_all_context: bool = True
) -> ExecutionResult:
    """
    執行區塊替換
    """
    start_time = datetime.now()

    try:
        # 解析檔案路徑
        target_path = _resolve_path(file_path)

        # 檢查檔案
        if not target_path.exists():
            raise FileNotFoundError(f"檔案不存在: {target_path}")
        if not target_path.is_file():
            raise ValueError(f"路徑不是檔案: {target_path}")

        # 讀取檔案內容
        with open(target_path, encoding="utf-8") as f:
            file_content = f.read()

        lines = file_content.splitlines(keepends=True)

        # 執行匹配
        if find_signature:
            content_to_find = find_signature.get("content", "")
            context_before = find_signature.get("context_before")
            context_after = find_signature.get("context_after")
            context_range = find_signature.get("context_range", 50)

            if not content_to_find:
                raise ValueError("find_signature 必須包含 content 欄位")

            matches = _find_by_signature(
                lines=lines,
                content=content_to_find,
                context_before=context_before,
                context_after=context_after,
                context_range=context_range,
                require_all_context=require_all_context
            )
        else:
            content_to_find = find_content or ""
            matches = _find_by_content(lines, content_to_find)

        # 處理匹配結果
        if not matches:
            return _build_no_match_result(
                target_path, file_content, content_to_find,
                find_signature, start_time
            )

        # 篩選高置信度匹配
        valid_matches = [m for m in matches if m.confidence > 0]

        if not valid_matches:
            return _build_no_match_result(
                target_path, file_content, content_to_find,
                find_signature, start_time
            )

        if len(valid_matches) > 1:
            # 多個匹配，需要指定 occurrence
            if occurrence > len(valid_matches):
                return _build_multiple_matches_result(
                    target_path, valid_matches, occurrence, start_time
                )
            selected_match = valid_matches[occurrence - 1]
            multiple_match_warning = len(valid_matches)
        else:
            if occurrence > 1:
                return _build_multiple_matches_result(
                    target_path, valid_matches, occurrence, start_time
                )
            selected_match = valid_matches[0]
            multiple_match_warning = 0

        # 構建新內容
        prefix_lines = lines[:selected_match.line_start - 1]
        suffix_lines = lines[selected_match.line_end:]

        # 處理 replace_with 的換行
        new_content_lines = replace_with.splitlines(keepends=True)
        if replace_with and new_content_lines and not new_content_lines[-1].endswith("\n"):
            new_content_lines[-1] += "\n"

        final_lines = prefix_lines + new_content_lines + suffix_lines
        final_content = "".join(final_lines)

        # 生成 diff
        diff_output = _generate_unified_diff(
            file_content, final_content,
            str(target_path), selected_match.line_start
        )

        # Python 語法驗證
        syntax_result = None
        if validate_syntax and target_path.suffix == ".py":
            syntax_result = _validate_python_syntax(final_content, target_path)
            if not syntax_result["valid"]:
                execution_time = (datetime.now() - start_time).total_seconds()
                error_msg = (
                    f"語法驗證失敗:\n{syntax_result['error']}\n\n"
                    f"修改已取消，檔案未被修改。"
                )
                return ExecutionResult(
                    success=False,
                    error_type="SyntaxValidationError",
                    error_message=error_msg,
                    stderr=error_msg,
                    returncode=-1,
                    execution_time=f"{execution_time:.3f}s",
                    metadata={
                        "file_path": str(target_path),
                        "syntax_check": syntax_result,
                        "diff_preview": diff_output,
                        "match_info": _match_to_dict(selected_match)
                    }
                )

        # Dry-run 模式
        if dry_run:
            execution_time = (datetime.now() - start_time).total_seconds()
            validation_msg = _format_syntax_result(syntax_result)

            # 多匹配警告
            warning_msg = ""
            if multiple_match_warning > 1:
                warning_msg = (
                    f"\n⚠️  注意: 找到 {multiple_match_warning} 處匹配，"
                    f"當前選擇第 {occurrence} 個\n"
                    f"   可使用 occurrence 參數選擇其他匹配 (1-{multiple_match_warning})\n"
                )

            return ExecutionResult(
                success=True,
                stdout=(
                    f"{warning_msg}"
                    f"✅ 找到匹配位置: 第 {selected_match.line_start}-{selected_match.line_end} 行\n"
                    f"📊 匹配置信度: {selected_match.confidence:.0%}\n"
                    f"{_format_context_info(selected_match)}"
                    f"{validation_msg}\n\n"
                    f"修改差異預覽:\n{diff_output}\n"
                    f"📝 若要實際執行修改，請設置 dry_run: false"
                ),
                returncode=0,
                execution_time=f"{execution_time:.3f}s",
                metadata={
                    "file_path": str(target_path),
                    "dry_run": True,
                    "match_info": _match_to_dict(selected_match),
                    "original_content": selected_match.content,
                    "new_content": replace_with,
                    "new_line_count": len(new_content_lines),
                    "syntax_check": syntax_result,
                    "diff_preview": diff_output,
                    "total_matches": multiple_match_warning if multiple_match_warning > 1 else None
                }
            )

        # 實際寫入
        with open(target_path, "w", encoding="utf-8") as f:
            f.writelines(final_lines)

        execution_time = (datetime.now() - start_time).total_seconds()

        logger.info(
            f"成功替換檔案 {target_path} 行 {selected_match.line_start}-{selected_match.line_end}，"
            f"原始 {selected_match.line_end - selected_match.line_start + 1} 行 -> "
            f"新 {len(new_content_lines)} 行"
        )

        # 多匹配警告
        warning_msg = ""
        if multiple_match_warning > 1:
            warning_msg = f"\n⚠️  注意: 檔案中共有 {multiple_match_warning} 處匹配，已替換第 {occurrence} 個"

        success_msg = f"✅ 檔案 {target_path} 已更新"
        success_msg += f"\n📍 替換位置: 第 {selected_match.line_start}-{selected_match.line_end} 行"
        if warning_msg:
            success_msg += warning_msg
        if syntax_result and syntax_result["valid"]:
            success_msg += "\n✅ 語法驗證通過"

        return ExecutionResult(
            success=True,
            stdout=success_msg,
            execution_time=f"{execution_time:.3f}s",
            metadata={
                "file_path": str(target_path),
                "match_info": _match_to_dict(selected_match),
                "original_line_count": selected_match.line_end - selected_match.line_start + 1,
                "new_line_count": len(new_content_lines),
                "bytes_written": len(final_content.encode("utf-8")),
                "syntax_check": syntax_result,
                "diff_preview": diff_output
            }
        )

    except Exception as e:
        logger.exception(f"replace_block 發生錯誤: {e}")
        return ExecutionResult(
            success=False,
            error_type=type(e).__name__,
            error_message=str(e),
            stderr=str(e),
            returncode=-1,
            execution_time="0.000s"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 匹配函數
# ═══════════════════════════════════════════════════════════════════════════════

def _find_by_content(
    lines: list[str],
    content: str
) -> list[MatchResult]:
    """精確內容匹配"""
    matches = []
    content_lines = content.splitlines(keepends=True)

    if not content_lines:
        return matches

    # 標準化：確保最後一行有換行符
    if content and content_lines[-1] and not content_lines[-1].endswith("\n"):
        content_lines[-1] += "\n"

    for i in range(len(lines) - len(content_lines) + 1):
        if _lines_match(lines[i:i + len(content_lines)], content_lines):
            matches.append(MatchResult(
                line_start=i + 1,  # 1-based
                line_end=i + len(content_lines),
                content="".join(lines[i:i + len(content_lines)]),
                before_matched=True,
                after_matched=True,
                before_line=None,
                after_line=None,
                confidence=1.0
            ))

    return matches


def _find_by_signature(
    lines: list[str],
    content: str,
    context_before: str | None,
    context_after: str | None,
    context_range: int,
    require_all_context: bool
) -> list[MatchResult]:
    """
    基於上下文簽名的匹配

    流程：
    1. 找到所有 content 匹配的位置
    2. 對每個匹配，檢查上下文
    3. 計算置信度
    """
    matches = _find_by_content(lines, content)

    if not matches:
        return matches

    if not context_before and not context_after:
        return matches

    # 為每個匹配檢查上下文
    for match in matches:
        # 檢查前文
        if context_before:
            before_found, before_line = _find_context_before(
                lines, match.line_start - 1, context_before, context_range
            )
            match.before_matched = before_found
            match.before_line = before_line
        else:
            match.before_matched = True

        # 檢查後文
        if context_after:
            after_found, after_line = _find_context_after(
                lines, match.line_end, context_after, context_range
            )
            match.after_matched = after_found
            match.after_line = after_line
        else:
            match.after_matched = True

        # 計算置信度
        scores = []
        if context_before:
            scores.append(1.0 if match.before_matched else 0.0)
        if context_after:
            scores.append(1.0 if match.after_matched else 0.0)
        match.confidence = sum(scores) / len(scores) if scores else 1.0

    # 如果要求所有上下文都匹配，過濾掉不完整的
    if require_all_context:
        matches = [m for m in matches if m.confidence == 1.0]

    return matches


def _find_context_before(
    lines: list[str],
    end_line: int,
    context: str,
    context_range: int
) -> tuple[bool, int | None]:
    """
    在指定行之前搜尋上下文

    Returns:
        (是否找到, 所在行號)
    """
    if end_line <= 0:
        return False, None

    search_start = max(0, end_line - context_range)
    search_content = "".join(lines[search_start:end_line])

    if context in search_content:
        # 找到上下文，計算行號
        # 找到上下文在搜尋範圍中的位置
        idx = search_content.find(context)
        # 計算實際行號
        char_count = 0
        for i, line in enumerate(lines[search_start:end_line]):
            if char_count + len(line) > idx:
                return True, search_start + i + 1
            char_count += len(line)
        return True, search_start + 1

    return False, None


def _find_context_after(
    lines: list[str],
    start_line: int,
    context: str,
    context_range: int
) -> tuple[bool, int | None]:
    """
    在指定行之後搜尋上下文

    Returns:
        (是否找到, 所在行號)
    """
    if start_line >= len(lines):
        return False, None

    search_end = min(len(lines), start_line + context_range)
    search_content = "".join(lines[start_line:search_end])

    if context in search_content:
        # 找到上下文，計算行號
        idx = search_content.find(context)
        char_count = 0
        for i, line in enumerate(lines[start_line:search_end]):
            if char_count + len(line) > idx:
                return True, start_line + i + 1
            char_count += len(line)
        return True, start_line + 1

    return False, None


def _lines_match(actual: list[str], expected: list[str]) -> bool:
    """比較兩組行是否匹配"""
    if len(actual) != len(expected):
        return False
    for a, e in zip(actual, expected, strict=False):
        # 統一換行符處理
        a_normalized = a.rstrip("\r\n")
        e_normalized = e.rstrip("\r\n")
        if a_normalized != e_normalized:
            return False
    return True


# ═══════════════════════════════════════════════════════════════════════════════
# 輔助函數
# ═══════════════════════════════════════════════════════════════════════════════

def _resolve_path(file_path: str) -> Path:
    """解析檔案路徑（只接受絕對路徑）"""
    path = Path(file_path)
    if not path.is_absolute():
        raise ValueError(f"file_path 必須為絕對路徑，當前傳入: '{file_path}'")
    return path.resolve()


def _generate_unified_diff(
    original: str,
    new: str,
    file_path: str,
    start_line: int
) -> str:
    """生成 unified diff 格式的差異"""
    original_lines = original.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)

    diff_lines = list(unified_diff(
        original_lines,
        new_lines,
        fromfile=f"a/{Path(file_path).name}",
        tofile=f"b/{Path(file_path).name}",
        lineterm=""
    ))

    return "".join(diff_lines)


def _validate_python_syntax(content: str, file_path: Path) -> dict[str, Any]:
    """
    使用 Ruff 或 py_compile 驗證 Python 檔案的語法
    """
    try:
        # 檢查致命語法錯誤
        syntax_check = subprocess.run(
            ["ruff", "check", "--select", "E9", "-"],
            input=content,
            capture_output=True,
            text=True,
            timeout=10
        )

        if syntax_check.returncode != 0:
            error_output = syntax_check.stdout or syntax_check.stderr or "語法錯誤"
            return {
                "valid": False,
                "error": error_output.strip(),
                "tool": "ruff",
                "fixable": False,
                "fixed_content": None
            }

        # 嘗試自動修正
        fix_result = subprocess.run(
            ["ruff", "check", "--fix", "--unsafe-fixes", "-"],
            input=content,
            capture_output=True,
            text=True,
            timeout=10
        )

        fixed_content = fix_result.stdout if fix_result.stdout else content

        # 檢查修正後是否還有問題
        remaining_check = subprocess.run(
            ["ruff", "check", "-"],
            input=fixed_content,
            capture_output=True,
            text=True,
            timeout=10
        )

        if remaining_check.returncode == 0:
            return {
                "valid": True,
                "error": None,
                "tool": "ruff",
                "fixable": True,
                "fixed_content": fixed_content,
                "was_fixed": fixed_content != content
            }
        else:
            return {
                "valid": False,
                "error": f"存在無法自動修正的問題:\n{remaining_check.stdout}",
                "tool": "ruff",
                "fixable": False,
                "fixed_content": None
            }

    except FileNotFoundError:
        return _validate_with_py_compile(content)
    except subprocess.TimeoutExpired:
        return {
            "valid": False,
            "error": "Ruff 語法驗證超時（10秒）",
            "tool": "ruff",
            "fixable": False,
            "fixed_content": None
        }
    except Exception:
        return _validate_with_py_compile(content)


def _validate_with_py_compile(content: str) -> dict[str, Any]:
    """使用 py_compile 驗證語法（備選方案）"""
    import os
    import py_compile
    import tempfile

    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(content)
            temp_path = f.name

        try:
            py_compile.compile(temp_path, doraise=True)
            return {
                "valid": True,
                "error": None,
                "tool": "py_compile",
                "fixable": False,
                "fixed_content": None
            }
        finally:
            os.unlink(temp_path)

    except py_compile.PyCompileError as e:
        return {
            "valid": False,
            "error": f"語法錯誤: {e}",
            "tool": "py_compile",
            "fixable": False,
            "fixed_content": None
        }


def _match_to_dict(match: MatchResult) -> dict[str, Any]:
    """將 MatchResult 轉換為字典"""
    return {
        "line_start": match.line_start,
        "line_end": match.line_end,
        "confidence": match.confidence,
        "before_matched": match.before_matched,
        "after_matched": match.after_matched,
        "before_line": match.before_line,
        "after_line": match.after_line
    }


def _format_syntax_result(syntax_result: dict[str, Any] | None) -> str:
    """格式化語法驗證結果"""
    if not syntax_result:
        return ""

    if syntax_result["valid"]:
        if syntax_result.get("was_fixed"):
            return "\n✅ Ruff 語法驗證: 通過（可自動修正部分問題）"
        return "\n✅ Ruff 語法驗證: 通過"
    else:
        return f"\n❌ Ruff 語法驗證: 失敗\n{syntax_result.get('error', '')}"


def _format_context_info(match: MatchResult) -> str:
    """格式化上下文匹配資訊"""
    lines = []

    if match.before_line is not None:
        status = "✅" if match.before_matched else "❌"
        lines.append(f"  {status} 前文: 第 {match.before_line} 行")

    if match.after_line is not None:
        status = "✅" if match.after_matched else "❌"
        lines.append(f"  {status} 後文: 第 {match.after_line} 行")

    if lines:
        return "📋 上下文驗證:\n" + "\n".join(lines) + "\n"

    return ""


def _build_no_match_result(
    target_path: Path,
    file_content: str,
    content_to_find: str,
    find_signature: dict[str, Any] | None,
    start_time: datetime
) -> ExecutionResult:
    """構建無匹配結果"""
    execution_time = (datetime.now() - start_time).total_seconds()

    # 提供檔案內容預覽
    lines = file_content.splitlines()
    preview_lines = lines[:20] if len(lines) > 20 else lines
    preview = "\n".join(f"  {i+1:4d}: {line}" for i, line in enumerate(preview_lines))

    if len(lines) > 20:
        preview += f"\n  ... (共 {len(lines)} 行)"

    error_msg = (
        f"❌ 找不到匹配的內容區塊\n\n"
        f"📁 檔案: {target_path}\n"
        f"📏 檔案總行數: {len(lines)}\n\n"
        f"🔍 搜尋內容:\n"
        f"  {content_to_find[:100]}{'...' if len(content_to_find) > 100 else ''}\n"
    )

    if find_signature:
        ctx_before = find_signature.get("context_before")
        ctx_after = find_signature.get("context_after")
        if ctx_before:
            error_msg += f"\n📌 前文上下文: {ctx_before[:50]}{'...' if len(ctx_before) > 50 else ''}"
        if ctx_after:
            error_msg += f"\n📌 後文上下文: {ctx_after[:50]}{'...' if len(ctx_after) > 50 else ''}"

    error_msg += f"\n\n📄 檔案內容預覽:\n{preview}"

    return ExecutionResult(
        success=False,
        error_type="ContentNotFoundError",
        error_message=error_msg,
        stderr=error_msg,
        returncode=-1,
        execution_time=f"{execution_time:.3f}s",
        metadata={
            "file_path": str(target_path),
            "file_line_count": len(lines),
            "search_content": content_to_find[:500],
            "find_signature": find_signature
        }
    )


def _build_multiple_matches_result(
    target_path: Path,
    matches: list[MatchResult],
    requested_occurrence: int,
    start_time: datetime
) -> ExecutionResult:
    """構建多匹配結果"""
    execution_time = (datetime.now() - start_time).total_seconds()

    match_list = []
    for i, m in enumerate(matches, 1):
        ctx_info = []
        if m.before_line is not None:
            ctx_info.append(f"前文@{m.before_line}行")
        if m.after_line is not None:
            ctx_info.append(f"後文@{m.after_line}行")

        ctx_str = f" ({', '.join(ctx_info)})" if ctx_info else ""
        confidence_str = f" {m.confidence:.0%}" if m.confidence < 1.0 else ""

        # 提取匹配內容的第一行作為上下文
        first_line = m.content.splitlines()[0][:50] if m.content else "(空)"

        match_list.append(
            f"  #{i}: 第 {m.line_start}-{m.line_end} 行{ctx_str}{confidence_str}\n"
            f"      內容: {first_line}{'...' if len(m.content.splitlines()[0]) > 50 else ''}"
        )

    error_msg = (
        f"❌ 找到 {len(matches)} 處匹配\n\n"
        f"匹配列表:\n" + "\n".join(match_list) + "\n\n"
        f"請使用 occurrence 參數指定要替換的目標（1-{len(matches)}）。\n"
        f"您請求的 occurrence={requested_occurrence} 超出範圍。"
    )

    return ExecutionResult(
        success=False,
        error_type="MultipleMatchesError",
        error_message=error_msg,
        stderr=error_msg,
        returncode=-1,
        execution_time=f"{execution_time:.3f}s",
        metadata={
            "file_path": str(target_path),
            "total_matches": len(matches),
            "matches": [_match_to_dict(m) for m in matches],
            "requested_occurrence": requested_occurrence
        }
    )
