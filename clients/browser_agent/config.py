"""
Browser Agent 配置

從環境變數或命令列參數載入設定。
"""

import os
from dataclasses import dataclass
from pathlib import Path

# 自動載入 .env 檔案
_ENV_PATH = Path(__file__).parent / ".env"
if _ENV_PATH.exists():
    from dotenv import load_dotenv
    load_dotenv(_ENV_PATH)


@dataclass
class Config:
    """Browser Agent 配置"""

    # MCP Server WebSocket 位址
    server_url: str = "ws://localhost:30787"

    # 認證 Token
    token: str = ""

    # Chrome CDP Endpoint
    cdp_endpoint: str = "http://localhost:9222"

    # Client ID（用於識別）
    client_id: str = "browser-agent"

    # 重連間隔（秒）
    reconnect_interval: float = 5.0

    # 心跳間隔（秒）
    heartbeat_interval: float = 30.0

    # 操作逾時（秒）
    operation_timeout: float = 60.0

    @classmethod
    def from_env(cls) -> "Config":
        """從環境變數載入配置"""
        return cls(
            server_url=os.getenv("MCP_SERVER_URL", "ws://localhost:30787"),
            token=os.getenv("MCP_TOKEN", ""),
            cdp_endpoint=os.getenv(
                "CHROME_CDP_ENDPOINT",
                f"http://localhost:{os.getenv('CHROME_CDP_PORT', '9222')}",
            ),
            client_id=os.getenv("CLIENT_ID", "browser-agent"),
            reconnect_interval=float(os.getenv("RECONNECT_INTERVAL", "5.0")),
            heartbeat_interval=float(os.getenv("HEARTBEAT_INTERVAL", "30.0")),
            operation_timeout=float(os.getenv("OPERATION_TIMEOUT", "60.0")),
        )
