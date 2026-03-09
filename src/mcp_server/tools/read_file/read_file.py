"""
read_file Tool

讀取指定檔案的內容，支援行範圍選擇、行號顯示等功能。
"""

import logging
import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Any

from mcp_server.config import MAX_OUTPUT_LENGTH
from mcp_server.schemas import ExecutionResult
from mcp_server.tools.base import registry

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Tool 註冊
# ═══════════════════════════════════════════════════════════════════════════════


@registry.register(
    name="read_file",
    description=("讀取指定檔案的內容。支援行範圍選擇（start_line, end_line）、行號顯示等功能。適用於查看程式碼、設定檔、日誌等文字檔案。"),
    input_schema={
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "要讀取的檔案路徑（絕對路徑）"},
            "start_line": {"type": "integer", "description": "起始行號（1-based），預設 1", "minimum": 1, "default": 1},
            "end_line": {"type": "integer", "description": "結束行號（1-based），-1 表示到檔案末尾，預設 -1", "default": -1},
            "show_line_numbers": {"type": "boolean", "description": "是否顯示行號，預設 true", "default": True},
            "max_lines": {"type": "integer", "description": "最大讀取行數限制，預設 2000", "minimum": 1, "maximum": 10000, "default": 2000},
            "encoding": {"type": "string", "description": "檔案編碼，預設 utf-8", "default": "utf-8"},
        },
        "required": ["file_path"],
    },
)
async def handle_read_file(args: dict[str, Any]) -> ExecutionResult:
    """處理 read_file 請求"""
    file_path = args.get("file_path")
    start_line = args.get("start_line", 1)
    end_line = args.get("end_line", -1)
    show_line_numbers = args.get("show_line_numbers", True)
    max_lines = args.get("max_lines", 2000)
    encoding = args.get("encoding", "utf-8")

    # 參數驗證
    if not file_path or not isinstance(file_path, str):
        logger.warning(f"無效的 file_path 參數: {type(file_path)}")
        return ExecutionResult(
            success=False,
            error_type="ValueError",
            error_message="必須提供有效的 file_path 參數",
            returncode=-1,
            execution_time="0.000s",
        )

    if not isinstance(start_line, int) or start_line < 1:
        start_line = 1

    if not isinstance(end_line, int):
        end_line = -1

    if not isinstance(max_lines, int) or max_lines < 1:
        max_lines = 2000
    max_lines = min(max_lines, 10000)  # 上限 10000 行

    if not isinstance(encoding, str) or not encoding:
        encoding = "utf-8"

    return await read_file(file_path=file_path, start_line=start_line, end_line=end_line, show_line_numbers=show_line_numbers, max_lines=max_lines, encoding=encoding)


# ═══════════════════════════════════════════════════════════════════════════════
# 核心邏輯
# ═══════════════════════════════════════════════════════════════════════════════


async def read_file(file_path: str, start_line: int = 1, end_line: int = -1, show_line_numbers: bool = True, max_lines: int = 2000, encoding: str = "utf-8") -> ExecutionResult:
    """
    執行檔案讀取

    Args:
        file_path: 檔案絕對路徑
        start_line: 起始行號（1-based）
        end_line: 結束行號（-1 表示到末尾）
        show_line_numbers: 是否顯示行號
        max_lines: 最大讀取行數
        encoding: 檔案編碼

    Returns:
        ExecutionResult: 執行結果
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

        # 取得檔案資訊
        file_size = target_path.stat().st_size
        mime_type, _ = mimetypes.guess_type(str(target_path))

        logger.info(f"read_file: {target_path} (start={start_line}, end={end_line})")

        # 嘗試讀取檔案內容
        try:
            with open(target_path, encoding=encoding) as f:
                content = f.read()
        except UnicodeDecodeError as e:
            # 嘗試其他編碼
            for alt_encoding in ["utf-8-sig", "gbk", "gb2312", "latin-1"]:
                try:
                    with open(target_path, encoding=alt_encoding) as f:
                        content = f.read()
                    encoding = alt_encoding
                    break
                except UnicodeDecodeError:
                    continue
            else:
                return ExecutionResult(
                    success=False,
                    error_type="EncodingError",
                    error_message="無法解碼檔案，嘗試過的編碼: utf-8, utf-8-sig, gbk, gb2312, latin-1",
                    stderr=f"UnicodeDecodeError: {e}",
                    returncode=-1,
                    execution_time=_get_elapsed_time(start_time),
                    metadata={"file_path": str(target_path), "file_size": file_size, "mime_type": mime_type},
                )

        lines = content.splitlines()

        # 檔案為空
        if not lines:
            return ExecutionResult(
                success=True,
                stdout=f"📁 檔案: {target_path}\n📏 檔案大小: {file_size} bytes\n📋 檔案為空",
                returncode=0,
                execution_time=_get_elapsed_time(start_time),
                metadata={"file_path": str(target_path), "file_size": file_size, "total_lines": 0, "encoding": encoding, "mime_type": mime_type},
            )

        total_lines = len(lines)

        # 處理行範圍
        actual_start = max(1, start_line)
        actual_end = total_lines if end_line == -1 else min(end_line, total_lines)

        # 檢查範圍有效性
        if actual_start > total_lines:
            return ExecutionResult(
                success=False,
                error_type="RangeError",
                error_message=f"起始行號 {actual_start} 超過檔案總行數 {total_lines}",
                returncode=-1,
                execution_time=_get_elapsed_time(start_time),
                metadata={"file_path": str(target_path), "file_size": file_size, "total_lines": total_lines},
            )

        # 應用 max_lines 限制
        if actual_end - actual_start + 1 > max_lines:
            actual_end = actual_start + max_lines - 1
            truncated = True
        else:
            truncated = False

        # 擷取目標行
        target_lines = lines[actual_start - 1 : actual_end]

        # 格式化輸出
        if show_line_numbers:
            line_number_width = len(str(actual_end))
            formatted_lines = [f"{actual_start + i:>{line_number_width}}: {line}" for i, line in enumerate(target_lines)]
        else:
            formatted_lines = target_lines

        output_content = "\n".join(formatted_lines)

        # 檢查輸出長度
        if len(output_content) > MAX_OUTPUT_LENGTH:
            # 截斷輸出
            output_content = output_content[:MAX_OUTPUT_LENGTH]
            output_truncated = True
        else:
            output_truncated = False

        # 構建輸出訊息
        header_parts = [f"📁 檔案: {target_path}", f"📏 檔案大小: {_format_size(file_size)}", f"📋 總行數: {total_lines} | 讀取範圍: {actual_start}-{actual_end}"]

        if encoding != "utf-8":
            header_parts.append(f"🔢 編碼: {encoding}")

        if mime_type:
            header_parts.append(f"📄 類型: {mime_type}")

        warning_parts = []
        if truncated:
            warning_parts.append(f"⚠️ 已達最大行數限制 ({max_lines} 行)，輸出已截斷")
        if output_truncated:
            warning_parts.append("⚠️ 輸出已達最大長度限制，內容已截斷")

        stdout = "\n".join(header_parts)
        if warning_parts:
            stdout += "\n" + "\n".join(warning_parts)
        stdout += f"\n\n📤 檔案內容:\n{output_content}"

        execution_time = _get_elapsed_time(start_time)

        return ExecutionResult(
            success=True,
            stdout=stdout,
            returncode=0,
            execution_time=execution_time,
            metadata={
                "file_path": str(target_path),
                "file_size": file_size,
                "total_lines": total_lines,
                "read_start": actual_start,
                "read_end": actual_end,
                "read_lines": len(target_lines),
                "encoding": encoding,
                "mime_type": mime_type,
                "truncated": truncated or output_truncated,
                "show_line_numbers": show_line_numbers,
            },
        )

    except FileNotFoundError as e:
        logger.exception(f"檔案不存在: {e}")
        return ExecutionResult(success=False, error_type="FileNotFoundError", error_message=str(e), stderr=str(e), returncode=-1, execution_time=_get_elapsed_time(start_time))
    except PermissionError as e:
        logger.exception(f"權限不足: {e}")
        return ExecutionResult(
            success=False,
            error_type="PermissionError",
            error_message=f"權限不足，無法讀取檔案: {file_path}",
            stderr=str(e),
            returncode=-1,
            execution_time=_get_elapsed_time(start_time),
        )
    except Exception as e:
        logger.exception(f"read_file 發生錯誤: {e}")
        return ExecutionResult(success=False, error_type=type(e).__name__, error_message=str(e), stderr=str(e), returncode=-1, execution_time=_get_elapsed_time(start_time))


# ═══════════════════════════════════════════════════════════════════════════════
# 輔助函數
# ═══════════════════════════════════════════════════════════════════════════════


def _resolve_path(file_path: str) -> Path:
    """解析檔案路徑（只接受絕對路徑）"""
    path = Path(file_path)
    if not path.is_absolute():
        logger.warning(f"檔案路徑必須為絕對路徑: {file_path}")
        # 不拋出異常，而是返回一個標記讓呼叫者處理
        # 這裡仍然拋出異常，因為這是內部函數，由上層捕獲
        raise ValueError(f"file_path 必須為絕對路徑，當前傳入: '{file_path}'")
    return path.resolve()


def _format_size(size_bytes: int) -> str:
    """格式化檔案大小"""
    if size_bytes < 1024:
        return f"{size_bytes} bytes"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


def _get_elapsed_time(start_time: datetime) -> str:
    """取得經過時間"""
    elapsed = (datetime.now() - start_time).total_seconds()
    return f"{elapsed:.3f}s"
