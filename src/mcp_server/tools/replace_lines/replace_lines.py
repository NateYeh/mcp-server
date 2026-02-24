"""
replace_lines Tool

指定行號範圍，將檔案中的指定行替換為新內容

支援功能：
1. Dry-run 預覽模式 - 預覽修改內容而不實際寫入
2. Ruff/py_compile 語法驗證 - 確保修改後的 Python 檔案語法正確
"""

import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from mcp_server.config import MAX_INPUT_LENGTH
from mcp_server.schemas import ExecutionResult
from mcp_server.tools.base import registry

logger = logging.getLogger(__name__)


@registry.register(
    name="replace_lines",
    description="指定開始行～結束行，將檔案中的這段內容完全替換為新內容。行號以 1 開始計算。支援 dry_run 模式預覽，以及 ruff 語法驗證。",
    input_schema={
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "要修改的檔案路徑。只支援絕對路徑，例如 '/home/user/project/src/main.py'"},
            "start_line": {"type": "integer", "minimum": 1, "description": "開始行號（1-based，包含）"},
            "end_line": {"type": "integer", "minimum": 1, "description": "結束行號（1-based，包含），必須大於等於 start_line"},
            "new_content": {"type": "string", "description": "用於替換的新內容（可以是多行文字）"},
            "dry_run": {"type": "boolean", "default": False, "description": "預覽模式：顯示修改前後的差異，但不實際寫入檔案"},
            "validate_syntax": {"type": "boolean", "default": False, "description": "是否驗證 Python 檔案的語法正確性（僅對 .py 檔案有效）"},
        },
        "required": ["file_path", "start_line", "end_line", "new_content"],
    },
)
async def handle_replace_lines(args: dict[str, Any]) -> ExecutionResult:
    """處理 replace_lines 請求"""
    file_path = args.get("file_path")
    start_line = args.get("start_line")
    end_line = args.get("end_line")
    new_content = args.get("new_content")
    dry_run = args.get("dry_run", False)
    validate_syntax = args.get("validate_syntax", False)

    # 參數驗證
    if not file_path or not isinstance(file_path, str):
        raise ValueError("必須提供有效的 file_path 參數")

    if not isinstance(start_line, int) or not isinstance(end_line, int):
        raise ValueError("start_line 和 end_line 必須為整數")

    if start_line < 1 or end_line < 1:
        raise ValueError("行號必須從 1 開始")

    if start_line > end_line:
        raise ValueError(f"start_line ({start_line}) 不能大於 end_line ({end_line})")

    if new_content is None:
        new_content = ""
    elif not isinstance(new_content, str):
        new_content = str(new_content)

    if len(new_content) > MAX_INPUT_LENGTH:
        raise ValueError(f"new_content 超過最大長度限制 {MAX_INPUT_LENGTH} 字符")

    if not isinstance(dry_run, bool):
        dry_run = False

    if not isinstance(validate_syntax, bool):
        validate_syntax = False

    mode_str = "[預覽模式]" if dry_run else "[實際寫入]"
    logger.info(f"{mode_str} 替換檔案行: {file_path} [{start_line}:{end_line}]")

    return await replace_file_lines(file_path, start_line, end_line, new_content, dry_run, validate_syntax)


async def replace_file_lines(file_path: str, start_line: int, end_line: int, new_content: str, dry_run: bool = False, validate_syntax: bool = False) -> ExecutionResult:
    """
    將檔案中指定行號範圍的內容替換為新內容。
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
            all_lines = f.readlines()

        total_lines = len(all_lines)

        # 檢查行號範圍
        if start_line > total_lines:
            raise ValueError(f"start_line ({start_line}) 超過檔案總行數 ({total_lines})")

        actual_end_line = min(end_line, total_lines)

        # 處理新內容的換行
        if new_content and not new_content.endswith("\n"):
            new_content += "\n"

        # 計算修改前後的內容
        prefix_lines = all_lines[: start_line - 1]
        suffix_lines = all_lines[actual_end_line:]
        replaced_lines = all_lines[start_line - 1 : actual_end_line]
        original_content = "".join(replaced_lines)
        original_line_count = len(replaced_lines)

        new_content_lines = new_content.splitlines(keepends=True)
        if new_content and not new_content_lines[-1].endswith("\n"):
            new_content_lines[-1] += "\n"

        final_lines = prefix_lines + new_content_lines + suffix_lines
        final_content = "".join(final_lines)

        # 生成 diff 預覽
        diff_output = _generate_diff(target_path, original_content, new_content, start_line, actual_end_line)

        # Python 語法驗證
        syntax_result = None
        if validate_syntax and target_path.suffix == ".py":
            syntax_result = _validate_python_syntax(final_content, target_path)
            if not syntax_result["valid"]:
                execution_time = (datetime.now() - start_time).total_seconds()
                error_msg = f"Ruff 語法驗證失敗:\n{syntax_result['error']}\n\n修改已取消，檔案未被修改。"
                return ExecutionResult(
                    success=False,
                    error_type="SyntaxValidationError",
                    error_message=error_msg,
                    stderr=error_msg,
                    returncode=-1,
                    execution_time=f"{execution_time:.3f}s",
                    metadata={"file_path": str(target_path), "syntax_check": syntax_result, "diff_preview": diff_output},
                )

        # Dry-run 模式：不實際寫入
        if dry_run:
            execution_time = (datetime.now() - start_time).total_seconds()
            validation_msg = ""
            if syntax_result:
                if syntax_result["valid"]:
                    validation_msg = "\n✅ Ruff 語法驗證: 通過（可自動修正部分問題）" if syntax_result.get("was_fixed") else "\n✅ Ruff 語法驗證: 通過"
                else:
                    validation_msg = f"\n❌ Ruff 語法驗證: 失敗\n{syntax_result.get('error', '')}"

            return ExecutionResult(
                success=True,
                stdout=(f"{validation_msg}\n\n修改差異預覽:\n{diff_output}\n若要實際執行修改，請設置 dry_run: false"),
                returncode=0,
                execution_time=f"{execution_time:.3f}s",
                metadata={
                    "file_path": str(target_path),
                    "dry_run": True,
                    "original_start_line": start_line,
                    "original_end_line": actual_end_line,
                    "original_line_count": original_line_count,
                    "new_line_count": len(new_content_lines),
                    "final_total_lines": len(final_lines),
                    "syntax_check": syntax_result,
                    "diff_preview": diff_output,
                },
            )

        # 實際寫入檔案
        with open(target_path, "w", encoding="utf-8") as f:
            f.writelines(final_lines)

        execution_time = (datetime.now() - start_time).total_seconds()
        new_line_count = len(new_content_lines) if new_content else 0
        final_total_lines = len(final_lines)

        logger.info(f"成功替換檔案 {target_path} 行 {start_line}-{actual_end_line}，原始 {original_line_count} 行 -> 新 {new_line_count} 行")

        success_msg = f"檔案 {target_path} 已更新"
        success_msg = f"檔案 {target_path} 已更新"
        if syntax_result and syntax_result["valid"]:
            if syntax_result.get("was_fixed"):
                success_msg += "\n✅ Ruff 語法驗證通過（已自動修正部分問題）"
            else:
                success_msg += "\n✅ Ruff 語法驗證通過"

        return ExecutionResult(
            success=True,
            stdout=success_msg,
            execution_time=f"{execution_time:.3f}s",
            metadata={
                "file_path": str(target_path),
                "original_start_line": start_line,
                "original_end_line": actual_end_line,
                "original_line_count": original_line_count,
                "new_line_count": new_line_count,
                "final_total_lines": final_total_lines,
                "bytes_written": len(final_content.encode("utf-8")),
                "syntax_check": syntax_result,
                "diff_preview": diff_output,
            },
        )

    except Exception as e:
        logger.exception(f"替換行內容時發生錯誤: {e}")
        return ExecutionResult(success=False, error_type=type(e).__name__, error_message=str(e), stderr=str(e), returncode=-1, execution_time="0.000s")


def _generate_diff(file_path: Path, original_content: str, new_content: str, start_line: int, end_line: int) -> str:
    """生成類似 git diff 的預覽格式"""
    lines = []
    lines.append(f"--- 原始檔案 ({start_line}-{end_line})")
    lines.append("+++ 新內容")
    lines.append("")

    if original_content:
        for i, line in enumerate(original_content.splitlines(), start=start_line):
            lines.append(f"-{i:4d}: {_truncate_text(line, 100)}")
    else:
        lines.append("- (空內容)")

    lines.append("")

    if new_content:
        for i, line in enumerate(new_content.splitlines(), start=start_line):
            lines.append(f"+{i:4d}: {_truncate_text(line, 100)}")
    else:
        lines.append("+ (空內容)")

    return "\n".join(lines)


def _validate_python_syntax(content: str, file_path: Path) -> dict[str, Any]:
    """
    使用 Ruff 或 py_compile 驗證 Python 檔案的語法

    驗證邏輯：
    1. 先檢查致命語法錯誤（E9 系列）- 這些無法自動修正
    2. 如果有致命錯誤 → 失敗
    3. 嘗試 ruff --fix 自動修正
    4. 如果修正後沒有問題 → 通過（返回修正後的內容）
    5. 如果仍有問題 → 失敗
    """
    # 優先嘗試使用 Ruff
    try:
        # 第一步：檢查致命語法錯誤（E9 系列）
        syntax_check = subprocess.run(["ruff", "check", "--select", "E9", "-"], input=content, capture_output=True, text=True, timeout=10)

        if syntax_check.returncode != 0:
            error_output = syntax_check.stdout or syntax_check.stderr or "語法錯誤"
            return {"valid": False, "error": error_output.strip(), "tool": "ruff", "command": "ruff check --select E9 -", "fixable": False, "fixed_content": None}

        # 第二步：嘗試自動修正
        fix_result = subprocess.run(["ruff", "check", "--fix", "--unsafe-fixes", "-"], input=content, capture_output=True, text=True, timeout=10)

        # stdin 模式下，修正後的內容在 stdout
        fixed_content = fix_result.stdout if fix_result.stdout else content

        # 第三步：檢查修正後是否還有問題
        remaining_check = subprocess.run(["ruff", "check", "-"], input=fixed_content, capture_output=True, text=True, timeout=10)

        if remaining_check.returncode == 0:
            return {
                "valid": True,
                "error": None,
                "tool": "ruff",
                "command": "ruff check --fix",
                "fixable": True,
                "fixed_content": fixed_content,
                "was_fixed": fixed_content != content,
            }
        else:
            # 仍有無法修正的問題
            return {"valid": False, "error": f"存在無法自動修正的問題:\n{remaining_check.stdout}", "tool": "ruff", "command": "ruff check", "fixable": False, "fixed_content": None}

    except FileNotFoundError:
        return _validate_with_py_compile(content, file_path)
    except subprocess.TimeoutExpired:
        return {"valid": False, "error": "Ruff 語法驗證超時（10秒）", "tool": "ruff", "fixable": False, "fixed_content": None}
    except Exception:
        return _validate_with_py_compile(content, file_path)


def _validate_with_py_compile(content: str, file_path: Path) -> dict[str, Any]:
    """
    使用 Python 內建的 py_compile 驗證語法（Ruff 的備選方案）

    注意：py_compile 只能驗證語法，無法自動修正問題
    """
    import os
    import py_compile
    import tempfile

    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(content)
            temp_path = f.name

        try:
            py_compile.compile(temp_path, doraise=True)
            return {"valid": True, "error": None, "tool": "py_compile", "fixable": False, "fixed_content": None}
        finally:
            os.unlink(temp_path)

    except py_compile.PyCompileError as e:
        return {"valid": False, "error": f"語法錯誤: {e}", "tool": "py_compile", "fixable": False, "fixed_content": None}


def _resolve_path(file_path: str) -> Path:
    """解析檔案路徑（只接受絕對路徑）"""
    path = Path(file_path)

    # 檢查是否為絕對路徑
    if not path.is_absolute():
        raise ValueError(f"file_path 必須為絕對路徑，當前傳入: '{file_path}'")

    return path.resolve()


def _truncate_text(text: str, max_length: int) -> str:
    """截斷過長的文字"""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."
