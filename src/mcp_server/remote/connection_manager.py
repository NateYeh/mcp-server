"""
遠端連線管理器

WebSocket Server，等待遠端 Browser Agent 連接。
負責維護連線狀態、轉發指令、接收結果。
"""

import asyncio
import json
import logging
import uuid
from typing import Any, Optional

from mcp_server.config import REMOTE_BROWSER_ENABLED, REMOTE_BROWSER_PORT, REMOTE_BROWSER_TOKEN

logger = logging.getLogger(__name__)


class RemoteConnectionManager:
    """
    遠端連線管理器（Singleton）

    管理 WebSocket Server 與遠端 Browser Agent 的連線。
    """

    _instance: Optional["RemoteConnectionManager"] = None
    _lock: asyncio.Lock = asyncio.Lock()

    def __new__(cls) -> "RemoteConnectionManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True

        self._server: Any = None
        self._websocket: Any = None
        self._pending_requests: dict[str, asyncio.Future] = {}
        self._is_running = False
        self._connection_info: dict[str, Any] = {}

    @property
    def is_connected(self) -> bool:
        """檢查是否有遠端連線"""
        return self._websocket is not None and self._websocket.open

    @property
    def connection_info(self) -> dict[str, Any]:
        """取得連線資訊"""
        return self._connection_info.copy()

    async def start_server(self) -> None:
        """啟動 WebSocket Server"""
        if not REMOTE_BROWSER_ENABLED:
            logger.info("🔴 遠端瀏覽器功能已停用（REMOTE_BROWSER_ENABLED=false）")
            return

        if self._is_running:
            logger.warning("WebSocket Server 已在運行中")
            return

        try:
            import websockets

            serve = websockets.serve

            async def handler(websocket: Any) -> None:
                """處理 WebSocket 連線"""
                # 驗證 Token
                try:
                    auth_message = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                    auth_data = json.loads(auth_message)

                    if auth_data.get("type") != "auth":
                        await websocket.send(json.dumps({"type": "error", "message": "需要認證"}))
                        await websocket.close()
                        return

                    if auth_data.get("token") != REMOTE_BROWSER_TOKEN:
                        await websocket.send(json.dumps({"type": "auth_failed", "message": "Token 無效"}))
                        await websocket.close()
                        return

                    # 認證成功
                    self._websocket = websocket
                    self._connection_info = {
                        "client_id": auth_data.get("client_id", "unknown"),
                        "user_agent": auth_data.get("user_agent", "unknown"),
                        "connected_at": auth_data.get("timestamp", ""),
                    }

                    await websocket.send(json.dumps({"type": "auth_success"}))
                    logger.info(f"✅ 遠端 Browser Agent 已連線: {self._connection_info}")

                except asyncio.TimeoutError:
                    logger.warning("遠端連線認證逾時")
                    await websocket.close()
                    return
                except Exception as e:
                    logger.exception(f"遠端連線認證失敗: {e}")
                    await websocket.close()
                    return

                # 處理訊息迴圈
                try:
                    async for message in websocket:
                        await self._handle_message(message)
                except Exception as e:
                    logger.exception(f"WebSocket 訊息處理錯誤: {e}")
                finally:
                    logger.info("🔴 遠端 Browser Agent 已斷線")
                    self._websocket = None
                    self._connection_info = {}

            self._server = await serve(
                handler,
                "0.0.0.0",
                REMOTE_BROWSER_PORT,
                ping_interval=30,
                ping_timeout=10,
            )
            self._is_running = True
            logger.info(f"🚀 遠端瀏覽器 WebSocket Server 已啟動: ws://0.0.0.0:{REMOTE_BROWSER_PORT}")

        except ImportError:
            logger.error("❌ 未安裝 websockets 套件，請執行: pip install websockets")
        except Exception as e:
            logger.exception(f"❌ 啟動 WebSocket Server 失敗: {e}")

    async def stop_server(self) -> None:
        """停止 WebSocket Server"""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
            self._is_running = False
            logger.info("🛑 遠端瀏覽器 WebSocket Server 已停止")

    async def _handle_message(self, message: str) -> None:
        """處理來自遠端的訊息"""
        try:
            data = json.loads(message)
            msg_type = data.get("type")

            if msg_type == "response":
                # 處理指令回應
                request_id = data.get("request_id")
                if request_id in self._pending_requests:
                    future = self._pending_requests.pop(request_id)
                    if not future.done():
                        future.set_result(data)
                    logger.debug(f"收到回應: request_id={request_id}")

            elif msg_type == "event":
                # 處理事件（如頁面變化）
                logger.debug(f"收到事件: {data}")

            else:
                logger.warning(f"未知訊息類型: {msg_type}")

        except json.JSONDecodeError:
            logger.warning(f"無法解析訊息: {message[:100]}")
        except Exception as e:
            logger.exception(f"處理訊息錯誤: {e}")

    async def send_command(self, action: str, params: dict[str, Any], timeout: float = 30.0) -> dict[str, Any]:
        """
        發送指令到遠端 Browser Agent

        Args:
            action: 指令名稱（navigate, click, fill, screenshot 等）
            params: 指令參數
            timeout: 逾時時間（秒）

        Returns:
            遠端回傳的結果

        Raises:
            RuntimeError: 無遠端連線
            asyncio.TimeoutError: 指令逾時
        """
        if not self.is_connected:
            raise RuntimeError("無遠端 Browser Agent 連線")

        request_id = str(uuid.uuid4())
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending_requests[request_id] = future

        try:
            command = {
                "type": "command",
                "request_id": request_id,
                "action": action,
                "params": params,
            }

            await self._websocket.send(json.dumps(command))
            logger.debug(f"發送指令: action={action}, request_id={request_id}")

            # 等待回應
            result = await asyncio.wait_for(future, timeout=timeout)

            if not result.get("success", False):
                error_msg = result.get("error", "未知錯誤")
                raise RuntimeError(f"遠端執行失敗: {error_msg}")

            return result.get("data", {})

        except asyncio.TimeoutError:
            self._pending_requests.pop(request_id, None)
            logger.error(f"指令逾時: action={action}, request_id={request_id}")
            raise
        except Exception as e:
            self._pending_requests.pop(request_id, None)
            logger.exception(f"發送指令失敗: {e}")
            raise

    async def get_remote_url(self) -> str:
        """取得遠端瀏覽器當前 URL"""
        result = await self.send_command("get_url", {})
        return result.get("url", "")

    async def get_remote_title(self) -> str:
        """取得遠端瀏覽器當前標題"""
        result = await self.send_command("get_title", {})
        return result.get("title", "")

    async def get_remote_viewport(self) -> dict[str, int] | None:
        """取得遠端瀏覽器 viewport 尺寸"""
        result = await self.send_command("get_viewport", {})
        return result.get("viewport")


# 全域管理器實例
remote_connection_manager = RemoteConnectionManager()
