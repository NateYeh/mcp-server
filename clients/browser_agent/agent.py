#!/usr/bin/env python3
"""
Browser Agent 主程式

連接 MCP Server，操作本地 Chrome 瀏覽器。

使用方式：
    python agent.py --server ws://your-server:30787 --token your-token

環境變數：
    MCP_SERVER_URL      - MCP Server WebSocket 位址
    MCP_TOKEN           - 認證 Token
    CHROME_CDP_ENDPOINT - Chrome CDP Endpoint (預設 http://localhost:9222)
    CLIENT_ID           - Client ID (預設 browser-agent)

Chrome 啟動參數 (Windows)：
    chrome.exe --remote-debugging-port=9222 --user-data-dir="C:\\temp\\chrome_debug"
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# 將當前目錄加入 sys.path（支援直接執行）
_current_dir = Path(__file__).parent
if str(_current_dir) not in sys.path:
    sys.path.insert(0, str(_current_dir))

# ruff: noqa: E402
from browser import BrowserController  # type: ignore  # noqa: E402
from client import WebSocketClient  # type: ignore  # noqa: E402
from config import Config  # type: ignore  # noqa: E402


def setup_logging(verbose: bool = False) -> None:
    """設定日誌"""
    level = logging.DEBUG if verbose else logging.INFO

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )

    # 過濾外部套件的 DEBUG 日誌
    logging.getLogger("websockets").setLevel(logging.WARNING)


def parse_args() -> argparse.Namespace:
    """解析命令列參數"""
    parser = argparse.ArgumentParser(
        description="Browser Agent - 連接 MCP Server 並操作本地 Chrome 瀏覽器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例：
  # 使用預設設定
  python agent.py

  # 指定 Server 和 Token
  python agent.py --server ws://192.168.1.100:30787 --token your-secret-token

  # 使用環境變數
  export MCP_SERVER_URL=ws://192.168.1.100:30787
  export MCP_TOKEN=your-secret-token
  python agent.py

Chrome 啟動 (Windows)：
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" ^
    --remote-debugging-port=9222 ^
    --user-data-dir="C:\\temp\\chrome_debug"

Chrome 啟動 (macOS)：
  /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome \\
    --remote-debugging-port=9222 \\
    --user-data-dir=/tmp/chrome_debug

Chrome 啟動 (Linux)：
  google-chrome \\
    --remote-debugging-port=9222 \\
    --user-data-dir=/tmp/chrome_debug
        """,
    )

    parser.add_argument(
        "--server",
        type=str,
        help="MCP Server WebSocket 位址 (預設: ws://localhost:30787)",
    )
    parser.add_argument(
        "--token",
        type=str,
        help="認證 Token",
    )
    parser.add_argument(
        "--cdp-endpoint",
        type=str,
        help="Chrome CDP Endpoint (預設: http://localhost:9222)",
    )
    parser.add_argument(
        "--client-id",
        type=str,
        help="Client ID (預設: browser-agent)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="顯示詳細日誌",
    )

    return parser.parse_args()


async def main() -> int:
    """主函式"""
    args = parse_args()
    setup_logging(verbose=args.verbose)

    logger = logging.getLogger(__name__)

    # 載入配置
    config = Config.from_env()

    # 命令列參數覆蓋環境變數
    if args.server:
        config.server_url = args.server
    if args.token:
        config.token = args.token
    if args.cdp_endpoint:
        config.cdp_endpoint = args.cdp_endpoint
    if args.client_id:
        config.client_id = args.client_id

    logger.info("=" * 60)
    logger.info("🌐 Browser Agent 啟動中...")
    logger.info(f"   Server URL: {config.server_url}")
    logger.info(f"   CDP Endpoint: {config.cdp_endpoint}")
    logger.info(f"   Client ID: {config.client_id}")
    logger.info("=" * 60)

    # 檢查 Token
    if not config.token:
        logger.warning("⚠️ 未設定 Token，建議使用 --token 或設定 MCP_TOKEN 環境變數")

    # 建立瀏覽器控制器
    browser = BrowserController(cdp_endpoint=config.cdp_endpoint)

    # 連接瀏覽器
    logger.info("🔗 正在連接 Chrome...")
    if not await browser.connect():
        logger.error("❌ 無法連接到 Chrome，請確認 Chrome 已啟動並開啟 CDP Port 9222")
        logger.error("   啟動參數: chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome_debug")
        return 1

    # 建立 WebSocket 客戶端
    client = WebSocketClient(config, browser)

    try:
        # 執行主迴圈
        await client.run()
    except KeyboardInterrupt:
        logger.info("\n👋 收到中斷訊號，正在停止...")
    finally:
        await client.stop()

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
