"""
execute_shell Tool

執行 Linux Shell 命令（使用 bash）
"""

import asyncio
import contextlib
import logging
import os
import signal
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from mcp_server.config import (
    DEFAULT_SHELL_CWD,
    MAX_EXECUTION_TIME,
    MAX_INPUT_LENGTH,
    MAX_OUTPUT_LENGTH,
    MAX_TIMEOUT_LIMIT,
)
from mcp_server.tools.base import registry

from .. import ExecutionResult

logger = logging.getLogger(__name__)

# 每次從子行程 pipe 讀取的位元組數
_READ_CHUNK_SIZE = 65536


def _kill_process_group(proc: asyncio.subprocess.Process) -> None:
    """
    終止子行程所屬的整個進程組

    進程已結束或已無權限時靜默略過（此處為收尾動作，失敗不應影響回應）。
    """
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)


async def _read_stream_capped(stream: asyncio.StreamReader, limit: int, on_overflow: Callable[[], None]) -> tuple[bytes, bool]:
    """
    讀取子行程輸出，最多保留 limit 個位元組

    超過上限時立即停止讀取並呼叫 on_overflow（通常用於終止子行程），
    避免呼叫端為了等逾時而白等，也避免將無上限的輸出累積於記憶體。

    Args:
        stream: 子行程的 stdout 或 stderr
        limit: 保留的位元組上限
        on_overflow: 超出上限時呼叫的無參數函式

    Returns:
        tuple[bytes, bool]: (擷取到的內容, 是否因超過上限而截斷)
    """
    buffer = bytearray()
    while True:
        chunk = await stream.read(_READ_CHUNK_SIZE)
        if not chunk:
            return bytes(buffer), False

        remaining = limit - len(buffer)
        if remaining <= 0:
            # 已達上限且仍有未讀資料
            on_overflow()
            return bytes(buffer), True

        buffer.extend(chunk[:remaining])
        if len(chunk) > remaining:
            on_overflow()
            return bytes(buffer), True


@registry.register(
    name="execute_shell",
    description="執行 Linux Shell 命令（使用 bash）。支援管道、重定向、環境變數等標準 shell 語法。可用於檔案操作、系統查詢、文字處理等。",
    input_schema={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "要執行的 shell 命令，支援 bash 語法。例如 'ls -la', 'cat file.txt', 'ps aux | grep python'"},
            "timeout": {
                "type": "integer",
                "default": MAX_EXECUTION_TIME,
                "minimum": 1,
                "maximum": MAX_TIMEOUT_LIMIT,
                "description": f"執行超時時間（秒），預設 {MAX_EXECUTION_TIME} 秒，最大 {MAX_TIMEOUT_LIMIT} 秒",
            },
        },
        "required": ["command"],
    },
)
async def handle_execute_shell(args: dict[str, Any]) -> ExecutionResult:
    """處理 execute_shell 請求"""
    command = args.get("command")

    if not command or not isinstance(command, str):
        logger.warning(f"無效的 command 參數: {type(command)}")
        return ExecutionResult(
            success=False,
            error_type="ValueError",
            error_message="必須提供有效的 command 參數",
            returncode=-1,
            execution_time="0.000s",
        )

    timeout = args.get("timeout")
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not (1 <= timeout <= MAX_TIMEOUT_LIMIT):
        if timeout is not None:
            logger.warning(f"timeout 參數不合法（{timeout!r}），改用預設值 {MAX_EXECUTION_TIME}s")
        timeout = MAX_EXECUTION_TIME

    logger.info(f"執行 Shell 命令 ({len(command)} 字符)")

    return await execute_shell_command(command, timeout)


async def execute_shell_command(command: str, timeout: int = MAX_EXECUTION_TIME, working_dir: Path | None = None) -> ExecutionResult:
    """
    執行 Linux Shell 命令。

    Args:
        command: shell 命令
        timeout: 執行超時秒數
        working_dir: 工作目錄（預設為 DEFAULT_SHELL_CWD）

    Returns:
        ExecutionResult: 執行結果
    """
    start_time = datetime.now()

    try:
        if len(command) > MAX_INPUT_LENGTH:
            logger.warning(f"命令超過最大長度限制: {len(command)} > {MAX_INPUT_LENGTH}")
            return ExecutionResult(
                success=False,
                error_type="ValueError",
                error_message=f"命令超過最大長度限制 {MAX_INPUT_LENGTH} 字元",
                returncode=-1,
                execution_time="0.000s",
            )

        cwd = str(working_dir) if working_dir else str(DEFAULT_SHELL_CWD)

        # 不自動建立目錄，避免在非預期位置產生檔案系統變更
        if not Path(cwd).is_dir():
            logger.warning(f"工作目錄不存在或非目錄: {cwd}")
            return ExecutionResult(
                success=False,
                error_type="FileNotFoundError",
                error_message=f"工作目錄不存在: {cwd}",
                returncode=-1,
                execution_time="0.000s",
            )

        logger.info(f"執行 Shell 命令: {command[:100]}{'...' if len(command) > 100 else ''} (timeout={timeout}s)")

        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            executable="/bin/bash",
            start_new_session=True,  # 建立新進程組，逾時可整組終止（等價 os.setsid 且執行緒安全）
        )
        logger.info(f"🐚 Shell 進程已啟動 | PID: {proc.pid}")

        # 已指定 stdout/stderr 為 PIPE，此處僅為了型別收窄
        if proc.stdout is None or proc.stderr is None:
            raise RuntimeError("無法建立子行程的輸出管道")

        truncated = False

        def _on_overflow() -> None:
            """輸出超過上限：立刻終止進程組，避免子行程阻塞在 pipe 上等逾時"""
            nonlocal truncated
            truncated = True
            _kill_process_group(proc)

        stdout_task = asyncio.create_task(_read_stream_capped(proc.stdout, MAX_OUTPUT_LENGTH, _on_overflow))
        stderr_task = asyncio.create_task(_read_stream_capped(proc.stderr, MAX_OUTPUT_LENGTH, _on_overflow))
        read_task = asyncio.gather(stdout_task, stderr_task)

        timed_out = False
        try:
            # shield 避免逾時時取消讀取任務，才能取回已讀到的輸出
            await asyncio.wait_for(asyncio.shield(read_task), timeout=timeout)
        except asyncio.TimeoutError:
            timed_out = True
            logger.warning(f"Shell 執行超時 ({timeout}s)，整個進程組已終止")
            _kill_process_group(proc)
            await read_task
        finally:
            if proc.returncode is None:
                await proc.wait()

        stdout_bytes, stdout_truncated = stdout_task.result()
        stderr_bytes, stderr_truncated = stderr_task.result()
        truncated = truncated or stdout_truncated or stderr_truncated

        stdout_text = stdout_bytes.decode("utf-8", errors="replace")
        stderr_text = stderr_bytes.decode("utf-8", errors="replace")
        execution_time = f"{(datetime.now() - start_time).total_seconds():.3f}s"

        if timed_out:
            return ExecutionResult(
                success=False,
                error_type="TimeoutError",
                stderr=f"Execution timeout after {timeout}s",
                returncode=proc.returncode if proc.returncode is not None else -1,
                execution_time=f">{timeout}s",
                metadata={"command": command},
            )

        if truncated:
            note = f"輸出超過上限 {MAX_OUTPUT_LENGTH} 字元，內容已截斷並終止命令"
            logger.warning(f"{note} | 命令: {command[:100]}")
            stderr_text = f"{stderr_text}\n[truncated] {note}" if stderr_text else f"[truncated] {note}"
            return ExecutionResult(
                success=False,
                error_type="OutputLimitError",
                error_message=note,
                stdout=stdout_text,
                stderr=stderr_text,
                returncode=proc.returncode if proc.returncode is not None else -1,
                execution_time=execution_time,
                metadata={"command": command},
            )

        return ExecutionResult(
            success=proc.returncode == 0,
            stdout=stdout_text,
            stderr=stderr_text,
            returncode=proc.returncode or 0,
            execution_time=execution_time,
            metadata={"command": command},
        )

    except Exception as e:
        logger.exception(f"執行 Shell 命令時發生錯誤: {e}")
        return ExecutionResult(
            success=False, error_type=type(e).__name__, error_message=str(e), stderr=str(e), returncode=-1, execution_time="0.000s", metadata={"command": command}
        )
