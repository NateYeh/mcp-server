"""
MCP Server 主入口

可透過 python -m mcp_server 或直接執行啟動伺服器
"""

import sys

import uvicorn

from mcp_server.base.logging_config import setup_logging
from mcp_server.config import (
    API_KEYS,
    GEMINI_API_KEYS,
    GEMINI_PAY_KEY,
    GEMINI_PROXY_URL,
    MAX_EXECUTION_TIME,
    MCP_PORT,
    OLLAMA_PROXY_URL,
    WORK_DIR,
    cleanup_work_directory,
)
from mcp_server.model.gemini_api_client import configure_client
from mcp_server.tools import registry


def main():
    """主函式"""
    # 設定日誌
    import logging
    setup_logging(file_log_level=logging.INFO)

    # 清理工作目錄
    cleanup_work_directory()

    # 配置 Gemini API 用戶端
    configure_client(
        api_keys=GEMINI_API_KEYS,
        pay_key=GEMINI_PAY_KEY,
        proxy_url=GEMINI_PROXY_URL,
        ollama_proxy_url=OLLAMA_PROXY_URL,
    )

    # 取得 app 實例
    import logging

    from mcp_server.app import app

    logger = logging.getLogger(__name__)
    logger.info("🚀 MCP 伺服器啟動 [v4.0.0]")
    logger.info(f"📂 工作目錄: {WORK_DIR.absolute()}")
    logger.info(f"🐍 Python: {sys.version}")
    logger.info(f"⏱️ 執行超時: {MAX_EXECUTION_TIME}s")
    logger.info(f"🔧 已載入 {registry.get_tool_count()} 個 Tools")

    if API_KEYS:
        logger.info(f"🔐 API Key 認證: 已啟用，共 {len(API_KEYS)} 組 Key")
    else:
        logger.warning("⚠️ API Key 認證: 已停用（開發模式）")

    # 啟動伺服器
    uvicorn.run(app, host="0.0.0.0", port=MCP_PORT)


if __name__ == "__main__":
    main()
