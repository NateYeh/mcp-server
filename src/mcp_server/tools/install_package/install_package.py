"""
install_package Tool

安裝 Python 套件（使用 pip）
"""

import asyncio
import logging
import sys
import traceback
from typing import Any

from mcp_server.config import DANGEROUS_PACKAGE_CHARS, MAX_EXECUTION_TIME, MAX_OUTPUT_LENGTH
from mcp_server.tools.base import registry

from .. import ExecutionResult

logger = logging.getLogger(__name__)


@registry.register(
    name="install_package",
    description="安裝 Python 套件（使用 pip）。支援指定版本如 'requests==2.28.0'。安裝後即可在 execute_python 中使用。",
    input_schema={
        "type": "object",
        "properties": {
            "package": {"type": "string", "description": "套件名稱與版本規格，例如 'numpy', 'pandas==2.0.0', 'git+https://github.com/...'"},
            "timeout": {"type": "integer", "default": MAX_EXECUTION_TIME, "minimum": 1, "maximum": MAX_EXECUTION_TIME, "description": "安裝超時時間（秒）"},
        },
        "required": ["package"],
    },
)
async def handle_install_package(args: dict[str, Any]) -> ExecutionResult:
    """處理 install_package 請求"""
    package_spec = args.get("package")

    if not package_spec or not isinstance(package_spec, str):
        logger.warning(f"無效的 package 參數: {type(package_spec)}")
        return ExecutionResult(
            success=False,
            error_type="ValueError",
            error_message="必須提供有效的 package 參數",
            returncode=-1,
            execution_time="0.000s",
        )

    result = await install_package(package_spec.strip())

    if result.success:
        result.stdout = f"✅ Package '{package_spec}' installed successfully.\n\n📤 Output:\n{result.stdout}"
        if result.stderr:
            result.stdout += f"\n\n⚠️ Warnings:\n{result.stderr}"
        result.stderr = ""
        result.stdout += "\n\n💡 提醒：請將此套件新增至 /mnt/work/py_works/project/requirements.txt 以確保專案依賴一致性。"
    else:
        result.error_message = f"❌ Failed to install '{package_spec}': {result.error_message}"

    return result


async def install_package(package_spec: str, timeout: int = MAX_EXECUTION_TIME) -> ExecutionResult:
    """
    安裝 Python 套件。

    Args:
        package_spec: 套件名稱與版本規格，如 'requests==2.28.0'
        timeout: 安裝超時秒數

    Returns:
        ExecutionResult: 安裝結果
    """
    logger.info(f"開始安裝套件: {package_spec}")

    # 安全性檢查
    if any(char in package_spec for char in DANGEROUS_PACKAGE_CHARS):
        return ExecutionResult(
            success=False, error_type="ValueError", error_message="Package specification contains invalid characters", stderr="Invalid characters in package name"
        )

    if len(package_spec) > 200:
        return ExecutionResult(success=False, error_type="ValueError", error_message="Package specification too long (max 200 characters)", stderr="Package name too long")

    try:
        cmd = [sys.executable, "-m", "pip", "install", "--no-cache-dir", package_spec]

        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            logger.warning(f"套件安裝超時 ({timeout}s)")
            return ExecutionResult(success=False, error_type="TimeoutError", stderr=f"Installation timeout after {timeout}s")

        stdout_text = stdout_bytes.decode("utf-8", errors="replace")
        stderr_text = stderr_bytes.decode("utf-8", errors="replace")

        # 截斷過長輸出
        if len(stdout_text) > MAX_OUTPUT_LENGTH:
            stdout_text = stdout_text[:MAX_OUTPUT_LENGTH] + "... [truncated]"
        if len(stderr_text) > MAX_OUTPUT_LENGTH:
            stderr_text = stderr_text[:MAX_OUTPUT_LENGTH] + "... [truncated]"

        return ExecutionResult(success=proc.returncode == 0, stdout=stdout_text, stderr=stderr_text, returncode=proc.returncode or 0, metadata={"package": package_spec})

    except Exception as e:
        logger.exception(f"安裝套件失敗: {e}")
        return ExecutionResult(success=False, error_type=type(e).__name__, error_message=str(e), stderr=traceback.format_exc())
