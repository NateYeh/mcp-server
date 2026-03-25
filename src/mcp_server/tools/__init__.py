"""
Tools 模組入口

集中管理所有 MCP Tools，自動發現並註冊到 Registry

動態工具發現機制：
- 自動掃描 tools 目錄下的子目錄
- 載入每個子目錄中的 Python 模組
- 透過 @registry.register 裝飾器自動註冊工具
"""

import importlib
import logging
from pathlib import Path

from mcp_server.tools.base import ToolDefinition, ToolHandler, ToolRegistry, registry
from mcp_server.tools.schemas import ExecutionResult

logger = logging.getLogger(__name__)

# =========================================
# 動態工具發現
# =========================================


def _discover_tools() -> None:
    """
    自動發現並載入所有工具模組

    掃描 tools 目錄下的子目錄，動態載入其中的 Python 模組。
    每個模組會透過 @registry.register 裝飾器自動註冊到 registry。
    """
    tools_dir = Path(__file__).parent

    for item in tools_dir.iterdir():
        # 跳過非目錄、隱藏目錄、__pycache__ 和 base.py
        if not item.is_dir():
            continue
        if item.name.startswith("_"):
            continue
        if item.name == "__pycache__":
            continue

        # 檢查是否有 __init__.py 或同名 .py 檔案
        has_init = (item / "__init__.py").exists()
        has_module = (item / f"{item.name}.py").exists()

        if not (has_init or has_module):
            logger.debug(f"跳過無效的工具目錄: {item.name}")
            continue

        try:
            # 動態載入模組
            module_name = f"mcp_server.tools.{item.name}"
            importlib.import_module(module_name)
            logger.debug(f"已載入工具模組: {item.name}")
        except ImportError as e:
            logger.warning(f"載入工具模組失敗 {item.name}: {e}")
        except Exception as e:
            logger.exception(f"載入工具模組時發生錯誤 {item.name}: {e}")


# 執行工具發現
_discover_tools()

logger.info(f"🔧 已載入 {registry.get_tool_count()} 個 Tool 模組")

__all__ = [
    # Core
    "registry",
    "ToolRegistry",
    "ToolDefinition",
    "ToolHandler",
    "ExecutionResult",
]
