"""
MCP Server 套件入口

版本號以 pyproject.toml 為唯一來源，避免多處硬編碼造成漂移。
"""

import logging
from importlib.metadata import PackageNotFoundError, version

logger = logging.getLogger(__name__)

try:
    __version__ = version("mcp-server")
except PackageNotFoundError:
    # 未安裝為套件（例如直接以原始碼路徑執行）時仍可運作
    logger.exception("無法取得 mcp-server 套件版本，改用預設值")
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
