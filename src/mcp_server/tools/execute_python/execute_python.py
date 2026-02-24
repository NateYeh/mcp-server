"""
execute_python Tool

執行 Python 3 代碼並返回標準輸出、錯誤訊息與執行結果
"""

import asyncio
import contextlib
import logging
import os
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from mcp_server.config import MAX_EXECUTION_TIME, MAX_INPUT_LENGTH, MAX_OUTPUT_LENGTH, WORK_DIR
from mcp_server.schemas import ExecutionResult
from mcp_server.tools.base import registry

logger = logging.getLogger(__name__)


@registry.register(
    name="execute_python",
    description="執行 Python 3 代碼並返回標準輸出、錯誤訊息與執行結果。",
    input_schema={
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "要執行的 Python 3 源代碼。可使用標準庫與已安裝的第三方套件，執行結果透過 print() 或返回值查看。"},
            "timeout": {
                "type": "integer",
                "default": MAX_EXECUTION_TIME,
                "minimum": 1,
                "maximum": MAX_EXECUTION_TIME,
                "description": "執行超時時間（秒），預設 300 秒，最大 300 秒",
            },
        },
        "required": ["code"],
    },
)
async def handle_execute_python(args: dict[str, Any]) -> ExecutionResult:
    """處理 execute_python 請求"""
    code = args.get("code")

    if not code or not isinstance(code, str):
        raise ValueError("必須提供有效的 code 參數")

    timeout = args.get("timeout", MAX_EXECUTION_TIME)
    if not isinstance(timeout, int) or timeout < 1 or timeout > MAX_EXECUTION_TIME:
        timeout = MAX_EXECUTION_TIME

    logger.info(f"執行 Python 代碼 ({len(code)} 字符, timeout={timeout}s)")

    return await execute_python_file(code, timeout)


async def execute_python_file(code: str, timeout: int = MAX_EXECUTION_TIME) -> ExecutionResult:
    """
    將代碼寫入臨時檔案後執行。

    Args:
        code: Python 源代碼
        timeout: 執行超時秒數

    Returns:
        ExecutionResult: 執行結果
    """
    start_time = datetime.now()
    temp_file: Path | None = None

    try:
        if len(code) > MAX_INPUT_LENGTH:
            raise ValueError(f"Code exceeds maximum length of {MAX_INPUT_LENGTH} characters")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        temp_file = WORK_DIR / f"exec_{timestamp}.py"
        temp_file.write_text(code, encoding="utf-8")
        logger.debug(f"Python 代碼已寫入: {temp_file}")

        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            str(temp_file.absolute()),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(WORK_DIR),
            preexec_fn=os.setsid,  # 建立新進程組
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            stdout_text = stdout_bytes.decode("utf-8", errors="replace")
            stderr_text = stderr_bytes.decode("utf-8", errors="replace")
        except asyncio.TimeoutError:
            # 殺掉整個進程組
            with contextlib.suppress(ProcessLookupError):
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            await proc.wait()
            logger.warning(f"執行超時 ({timeout}s)，整個進程組已終止")
            return ExecutionResult(
                success=False,
                error_type="TimeoutError",
                stderr=f"Execution timeout after {timeout}s",
                returncode=-1,
                execution_time=f">{timeout}s",
                metadata={"temp_file": str(temp_file)},
            )

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
            metadata={"temp_file": str(temp_file)},
        )

    except Exception as e:
        logger.exception(f"執行 Python 檔案時發生錯誤: {e}")
        return ExecutionResult(
            success=False,
            error_type=type(e).__name__,
            error_message=str(e),
            stderr=str(e),
            returncode=-1,
            execution_time="0.000s",
            metadata={"temp_file": str(temp_file) if temp_file else None},
        )
