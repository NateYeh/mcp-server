"""
write_file Tool

寫入內容到指定檔案，支援建立新檔案、覆蓋現有檔案、追加內容等操作。
"""

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from mcp_server.config import MAX_INPUT_LENGTH
from mcp_server.tools.base import registry

from .. import ExecutionResult

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Tool 註冊
# ═══════════════════════════════════════════════════════════════════════════════


@registry.register(
    name="write_file",
    description=("寫入內容到指定檔案。支援建立新檔案、覆蓋現有檔案、追加內容等操作。可自動建立上層目錄，並選擇是否備份原檔案。"),
    input_schema={
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "要寫入的檔案路徑（絕對路徑）"},
            "content": {"type": "string", "description": "要寫入的內容"},
            "mode": {"type": "string", "description": "寫入模式：write（覆蓋）或 append（追加），預設 write", "enum": ["write", "append"], "default": "write"},
            "encoding": {"type": "string", "description": "檔案編碼，預設 utf-8", "default": "utf-8"},
            "create_dirs": {"type": "boolean", "description": "是否自動建立上層目錄，預設 true", "default": True},
            "backup": {"type": "boolean", "description": "覆蓋前是否備份原檔案（.bak），預設 false", "default": False},
        },
        "required": ["file_path", "content"],
    },
)
async def handle_write_file(args: dict[str, Any]) -> ExecutionResult:
    """處理 write_file 請求"""
    file_path = args.get("file_path")
    content = args.get("content")
    mode = args.get("mode", "write")
    encoding = args.get("encoding", "utf-8")
    create_dirs = args.get("create_dirs", True)
    backup = args.get("backup", False)

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

    if content is None:
        logger.warning("content 參數為 None")
        return ExecutionResult(
            success=False,
            error_type="ValueError",
            error_message="必須提供 content 參數",
            returncode=-1,
            execution_time="0.000s",
        )

    if not isinstance(content, str):
        content = str(content)

    if not isinstance(mode, str) or mode not in ("write", "append"):
        mode = "write"

    if not isinstance(encoding, str) or not encoding:
        encoding = "utf-8"

    if not isinstance(create_dirs, bool):
        create_dirs = True

    if not isinstance(backup, bool):
        backup = False

    return await write_file(file_path=file_path, content=content, mode=mode, encoding=encoding, create_dirs=create_dirs, backup=backup)


# ═══════════════════════════════════════════════════════════════════════════════
# 核心邏輯
# ═══════════════════════════════════════════════════════════════════════════════


async def write_file(file_path: str, content: str, mode: str = "write", encoding: str = "utf-8", create_dirs: bool = True, backup: bool = False) -> ExecutionResult:
    """
    執行檔案寫入

    Args:
        file_path: 檔案絕對路徑
        content: 要寫入的內容
        mode: 寫入模式（write/append）
        encoding: 檔案編碼
        create_dirs: 是否自動建立上層目錄
        backup: 是否備份原檔案

    Returns:
        ExecutionResult: 執行結果
    """
    start_time = datetime.now()

    try:
        # 檢查內容長度
        content_length = len(content)
        if content_length > MAX_INPUT_LENGTH:
            return ExecutionResult(
                success=False,
                error_type="ContentTooLarge",
                error_message=f"內容長度 {content_length} 超過限制 {MAX_INPUT_LENGTH}",
                returncode=-1,
                execution_time=_get_elapsed_time(start_time),
            )

        # 解析檔案路徑
        target_path = _resolve_path(file_path)
        parent_dir = target_path.parent

        # 檢查是否為目錄
        if target_path.exists() and target_path.is_dir():
            logger.warning(f"路徑是目錄，無法寫入檔案: {target_path}")
            return ExecutionResult(
                success=False,
                error_type="ValueError",
                error_message=f"路徑是目錄，無法寫入檔案: {target_path}",
                returncode=-1,
                execution_time=_get_elapsed_time(start_time),
            )

        # 處理目錄
        if not parent_dir.exists():
            if create_dirs:
                parent_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"已建立目錄: {parent_dir}")
            else:
                logger.warning(f"目錄不存在且未啟用自動建立: {parent_dir}")
                return ExecutionResult(
                    success=False,
                    error_type="FileNotFoundError",
                    error_message=f"目錄不存在: {parent_dir}",
                    returncode=-1,
                    execution_time=_get_elapsed_time(start_time),
                )

        # 記錄操作前的狀態
        file_existed = target_path.exists()
        original_size = target_path.stat().st_size if file_existed else 0
        original_lines = 0
        if file_existed:
            try:
                with open(target_path, encoding=encoding) as f:
                    original_lines = len(f.read().splitlines())
            except Exception:
                pass

        # 備份處理
        backup_path = None
        if file_existed and mode == "write" and backup:
            backup_path = target_path.with_suffix(target_path.suffix + ".bak")
            shutil.copy2(target_path, backup_path)
            logger.info(f"已備份原檔案至: {backup_path}")

        # 寫入檔案
        write_mode = "a" if mode == "append" else "w"
        with open(target_path, write_mode, encoding=encoding) as f:
            f.write(content)

        # 取得寫入後的資訊
        new_size = target_path.stat().st_size
        with open(target_path, encoding=encoding) as f:
            new_content = f.read()
        new_lines = len(new_content.splitlines())

        logger.info(f"write_file: {target_path} ({mode}, {content_length} bytes)")

        # 構建輸出訊息
        operation_text = "追加" if mode == "append" else "寫入"
        status_text = ("已更新" if mode == "append" else "已覆蓋") if file_existed else "已建立"

        header_parts = [
            f"📁 檔案: {target_path}",
            f"📏 檔案大小: {_format_size(new_size)}",
            f"📋 總行數: {new_lines}",
            f"⚙️ 操作: {operation_text} ({status_text})",
            f"📝 寫入內容: {_format_size(content_length)}, {len(content.splitlines())} 行",
        ]

        if backup_path:
            header_parts.append(f"🗃️ 備份: {backup_path}")

        stdout = "\n".join(header_parts)
        execution_time = _get_elapsed_time(start_time)

        return ExecutionResult(
            success=True,
            stdout=stdout,
            returncode=0,
            execution_time=execution_time,
            metadata={
                "file_path": str(target_path),
                "mode": mode,
                "encoding": encoding,
                "content_length": content_length,
                "file_size": new_size,
                "total_lines": new_lines,
                "file_existed": file_existed,
                "original_size": original_size if file_existed else None,
                "original_lines": original_lines if file_existed else None,
                "backup_created": backup_path is not None,
                "backup_path": str(backup_path) if backup_path else None,
            },
        )

    except FileNotFoundError as e:
        logger.exception(f"檔案或目錄不存在: {e}")
        return ExecutionResult(success=False, error_type="FileNotFoundError", error_message=str(e), stderr=str(e), returncode=-1, execution_time=_get_elapsed_time(start_time))
    except PermissionError as e:
        logger.exception(f"權限不足: {e}")
        return ExecutionResult(
            success=False,
            error_type="PermissionError",
            error_message=f"權限不足，無法寫入檔案: {file_path}",
            stderr=str(e),
            returncode=-1,
            execution_time=_get_elapsed_time(start_time),
        )
    except Exception as e:
        logger.exception(f"write_file 發生錯誤: {e}")
        return ExecutionResult(success=False, error_type=type(e).__name__, error_message=str(e), stderr=str(e), returncode=-1, execution_time=_get_elapsed_time(start_time))


# ═══════════════════════════════════════════════════════════════════════════════
# 輔助函數
# ═══════════════════════════════════════════════════════════════════════════════


def _resolve_path(file_path: str) -> Path:
    """解析檔案路徑（只接受絕對路徑）"""
    path = Path(file_path)
    if not path.is_absolute():
        logger.warning(f"檔案路徑必須為絕對路徑: {file_path}")
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
