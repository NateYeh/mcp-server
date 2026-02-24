"""
execute_shell Tool

執行 Linux Shell 命令（使用 bash）
"""

import asyncio
import contextlib
import logging
import os
import signal
from datetime import datetime
from pathlib import Path
from typing import Any

from mcp_server.config import (
    DANGEROUS_SHELL_PATTERNS,
    DEFAULT_SHELL_CWD,
    MAX_EXECUTION_TIME,
    MAX_INPUT_LENGTH,
    MAX_OUTPUT_LENGTH,
)
from mcp_server.schemas import ExecutionResult
from mcp_server.tools.base import registry

logger = logging.getLogger(__name__)


@registry.register(
    name="execute_shell",
    description="執行 Linux Shell 命令（使用 bash）。支援管道、重定向、環境變數等標準 shell 語法。可用於檔案操作、系統查詢、文字處理等。請注意：避免執行危險命令。",
    input_schema={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "要執行的 shell 命令，支援 bash 語法。例如 'ls -la', 'cat file.txt', 'ps aux | grep python'"},
            "timeout": {"type": "integer", "default": MAX_EXECUTION_TIME, "minimum": 1, "maximum": 300, "description": "執行超時時間（秒），預設 300 秒，最大 300 秒"},
        },
        "required": ["command"],
    },
)
async def handle_execute_shell(args: dict[str, Any]) -> ExecutionResult:
    """處理 execute_shell 請求"""
    command = args.get("command")

    if not command or not isinstance(command, str):
        raise ValueError("必須提供有效的 command 參數")

    timeout = args.get("timeout", MAX_EXECUTION_TIME)
    if not isinstance(timeout, int) or timeout < 1 or timeout > 300:
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
            raise ValueError(f"Command exceeds maximum length of {MAX_INPUT_LENGTH} characters")

        # 安全性檢查
        cmd_normalized = command.lower().replace(" ", "")
        for pattern in DANGEROUS_SHELL_PATTERNS:
            if pattern.replace(" ", "") in cmd_normalized:
                raise ValueError(f"Potentially dangerous command detected: {pattern}")

        cwd = str(working_dir) if working_dir else str(DEFAULT_SHELL_CWD)

        # 確保工作目錄存在
        if not Path(cwd).exists():
            Path(cwd).mkdir(parents=True, exist_ok=True)
            logger.warning(f"工作目錄不存在，已創建: {cwd}")

        logger.info(f"執行 Shell 命令: {command[:100]}{'...' if len(command) > 100 else ''} (timeout={timeout}s)")

        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            executable="/bin/bash",
            preexec_fn=os.setsid,  # 建立新進程組
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            # 殺掉整個進程組
            with contextlib.suppress(ProcessLookupError):
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            await proc.wait()
            logger.warning(f"Shell 執行超時 ({timeout}s)，整個進程組已終止")
            return ExecutionResult(
                success=False, error_type="TimeoutError", stderr=f"Execution timeout after {timeout}s", returncode=-1, execution_time=f">{timeout}s", metadata={"command": command}
            )

        stdout_text = stdout_bytes.decode("utf-8", errors="replace")
        stderr_text = stderr_bytes.decode("utf-8", errors="replace")

        # 截斷過長輸出
        if len(stdout_text) > MAX_OUTPUT_LENGTH:
            stdout_text = stdout_text[:MAX_OUTPUT_LENGTH] + "... [truncated]"
        if len(stderr_text) > MAX_OUTPUT_LENGTH:
            stderr_text = stderr_text[:MAX_OUTPUT_LENGTH] + "... [truncated]"

        execution_time = (datetime.now() - start_time).total_seconds()

        return ExecutionResult(
            success=proc.returncode == 0,
            stdout=stdout_text,
            stderr=stderr_text,
            returncode=proc.returncode or 0,
            execution_time=f"{execution_time:.3f}s",
            metadata={"command": command},
        )

    except Exception as e:
        logger.exception(f"執行 Shell 命令時發生錯誤: {e}")
        return ExecutionResult(
            success=False, error_type=type(e).__name__, error_message=str(e), stderr=str(e), returncode=-1, execution_time="0.000s", metadata={"command": command}
        )
