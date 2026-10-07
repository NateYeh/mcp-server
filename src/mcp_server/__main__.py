"""
MCP Server 主入口

可透過 python -m mcp_server 啟動伺服器
"""

import logging
import sys

import uvicorn

from mcp_server import __version__
from mcp_server.app import app
from mcp_server.base.logging_config import setup_logging
from mcp_server.config import (
    AUTH_KEY,
    AUTH_KEY_GENERATED,
    MAX_EXECUTION_TIME,
    MCP_HOST,
    MCP_PORT,
    WORK_DIR,
)
from mcp_server.tools import registry

logger = logging.getLogger(__name__)


def main() -> None:
    """主函式：初始化日誌與環境，顯示認證金鑰，啟動 uvicorn"""
    # 日誌必須在顯示金鑰前完成設定（否則 info 等級訊息不會輸出）
    setup_logging(file_log_level=logging.INFO)

    logger.info(f"🚀 MCP 伺服器啟動 [{__version__}]")
    logger.info(f"📂 工作目錄: {WORK_DIR}")
    logger.info(f"🐍 Python: {sys.version}")
    logger.info(f"⏱️ 執行超時: {MAX_EXECUTION_TIME}s")
    logger.info(f"🔧 已載入 {registry.get_tool_count()} 個 Tools")

    # 顯示本次使用的認證金鑰
    if AUTH_KEY_GENERATED:
        logger.warning("🔑 未設定 AUTH_KEY，已自動產生隨機金鑰（僅存於記憶體，重啟後會變更）")
    else:
        logger.info("🔐 認證金鑰來源：環境變數 AUTH_KEY")
    logger.info("═" * 72)
    logger.info(f"🔑 AUTH_KEY = {AUTH_KEY}")
    logger.info("═" * 72)

    # 啟動伺服器（工作目錄清理交由 app.lifespan 處理）
    uvicorn.run(app, host=MCP_HOST, port=MCP_PORT)


if __name__ == "__main__":
    main()
