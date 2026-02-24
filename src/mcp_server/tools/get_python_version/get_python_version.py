"""
get_python_version Tool

查詢目前伺服器使用的 Python 版本、實作方式（CPython/PyPy）、平台資訊與 pip 版本
"""

import platform as pf
import subprocess
import sys
from typing import Any

from mcp_server.config import MAX_EXECUTION_TIME
from mcp_server.schemas import ExecutionResult
from mcp_server.tools.base import registry


@registry.register(
    name="get_python_version",
    description="查詢目前伺服器使用的 Python 版本、實作方式（CPython/PyPy）、平台資訊與 pip 版本。",
    input_schema={
        "type": "object",
        "properties": {}
    }
)
async def handle_get_python_version(args: dict[str, Any]) -> ExecutionResult:
    """處理 get_python_version 請求"""
    version_info = {
        "version": pf.python_version(),
        "version_info": list(sys.version_info),
        "implementation": pf.python_implementation(),
        "compiler": pf.python_compiler(),
        "executable": sys.executable,
        "platform": pf.platform(),
        "architecture": pf.machine(),
        "pip_version": get_pip_version()
    }

    output = "\n".join([
        f"🐍 Python Version: {version_info['version']}",
        f"🔧 Implementation: {version_info['implementation']}",
        f"🖥️ Platform: {version_info['platform']}",
        f"🏗️ Architecture: {version_info['architecture']}",
        f"📦 Pip Version: {version_info['pip_version']}",
        f"📍 Executable: {version_info['executable']}"
    ])

    return ExecutionResult(
        success=True,
        stdout=output,
        metadata=version_info
    )

def get_pip_version() -> str:
    """取得 pip 版本。"""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "--version"],
            capture_output=True,
            text=True,
            timeout=min(MAX_EXECUTION_TIME, 30)
        )
        if result.returncode == 0:
            return result.stdout.strip().split()[1]
        return "unknown"
    except Exception:
        return "unknown"
