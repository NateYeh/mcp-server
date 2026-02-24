"""
WebSocket 客戶端模組

負責與 MCP Server 建立連線、認證、接收指令並回傳結果。
"""

import asyncio
import json
import logging
import platform
import time
from collections.abc import Callable
from typing import Any

try:
    import websockets
except ImportError:
    print("Please install websockets: pip install websockets")
    exit(1)

from browser import BrowserController  # type: ignore
from config import Config  # type: ignore

logger = logging.getLogger(__name__)


class WebSocketClient:
    """
    WebSocket 客戶端

    連接 MCP Server，認證後接收指令並操作本地瀏覽器。
    """

    def __init__(self, config: Config, browser: BrowserController):
        self._config = config
        self._browser = browser
        self._websocket: Any = None
        self._running = False
        self._handlers: dict[str, Callable] = {
            "navigate": self._handle_navigate,
            "get_url": self._handle_get_url,
            "get_title": self._handle_get_title,
            "get_viewport": self._handle_get_viewport,
            "screenshot": self._handle_screenshot,
            "click": self._handle_click,
            "type": self._handle_type,
            "wait_for_selector": self._handle_wait_for_selector,
            "query_selector_all": self._handle_query_selector_all,
            "inner_text": self._handle_inner_text,
            "get_content": self._handle_get_content,
            "evaluate": self._handle_evaluate,
            "wait_for_url": self._handle_wait_for_url,
            "wait_for_function": self._handle_wait_for_function,
            "wait_for_timeout": self._handle_wait_for_timeout,
            "scroll": self._handle_scroll,
            "element_click": self._handle_element_click,
            "element_type": self._handle_element_type,
            "element_press": self._handle_element_press,
            "element_inner_text": self._handle_element_inner_text,
            "element_get_attribute": self._handle_element_get_attribute,
            "element_screenshot": self._handle_element_screenshot,
            "element_scroll_into_view": self._handle_element_scroll_into_view,
            # Cookies 操作
            "get_cookies": self._handle_get_cookies,
            "add_cookie": self._handle_add_cookie,
            "clear_cookies": self._handle_clear_cookies,
        }

    def _is_connected(self) -> bool:
        """
        檢查 WebSocket 連線狀態（兼容 websockets 新舊版本）

        Returns:
            是否已連接
        """
        if not self._websocket:
            return False

        # websockets >= 11.0 使用 state 屬性
        if hasattr(self._websocket, 'state'):
            from websockets.protocol import State
            return self._websocket.state == State.OPEN

        # websockets < 11.0 使用 closed 屬性
        return not getattr(self._websocket, 'closed', True)

    async def connect(self) -> bool:
        """
        連接到 MCP Server 並進行認證

        Returns:
            是否連接成功
        """
        try:
            logger.info(f"🔗 正在連接到 MCP Server: {self._config.server_url}")
            self._websocket = await websockets.connect(
                self._config.server_url,
                ping_interval=self._config.heartbeat_interval,
                ping_timeout=10,
            )

            # 發送認證訊息
            auth_message = {
                "type": "auth",
                "token": self._config.token,
                "client_id": self._config.client_id,
                "user_agent": f"BrowserAgent/1.0 ({platform.system()} {platform.release()})",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            await self._websocket.send(json.dumps(auth_message))
            logger.info("已發送認證請求...")

            # 等待認證回應
            response = await asyncio.wait_for(self._websocket.recv(), timeout=10.0)
            data = json.loads(response)

            if data.get("type") == "auth_success":
                logger.info("✅ 認證成功！已連接到 MCP Server")
                return True
            else:
                error_msg = data.get("message", "認證失敗")
                logger.error(f"❌ 認證失敗: {error_msg}")
                await self._websocket.close()
                return False

        except asyncio.TimeoutError:
            logger.error("❌ 認證逾時")
            return False
        except Exception as e:
            logger.exception(f"❌ 連接失敗: {e}")
            return False

    async def run(self) -> None:
        """
        執行主迴圈：接收訊息並處理指令

        當連線斷開時會自動重連。
        """
        self._running = True

        while self._running:
            try:
                # 檢查連線狀態，必要時重新連接
                if not self._is_connected() and not await self._reconnect():
                    await asyncio.sleep(self._config.reconnect_interval)
                    continue

                # 接收訊息
                message = await self._websocket.recv()
                await self._handle_message(message)

            except websockets.ConnectionClosed:
                logger.warning("🔴 與 MCP Server 的連線已斷開")
                self._websocket = None
            except Exception as e:
                logger.exception(f"處理訊息時發生錯誤: {e}")

    async def _reconnect(self) -> bool:
        """重新連接"""
        logger.info(f"嘗試重新連接（{self._config.reconnect_interval}秒後）...")
        await asyncio.sleep(self._config.reconnect_interval)

        # 確保瀏覽器已連接
        if not self._browser.is_connected and not await self._browser.connect():
            logger.error("無法連接到瀏覽器")
            return False

        return await self.connect()

    async def _handle_message(self, message: str) -> None:
        """處理來自 MCP Server 的訊息"""
        try:
            data = json.loads(message)
            msg_type = data.get("type")

            if msg_type == "command":
                await self._handle_command(data)
            else:
                logger.warning(f"未知訊息類型: {msg_type}")

        except json.JSONDecodeError:
            logger.warning(f"無法解析訊息: {message[:100]}")
        except Exception as e:
            logger.exception(f"處理訊息錯誤: {e}")

    async def _handle_command(self, data: dict[str, Any]) -> None:
        """處理指令"""
        request_id = data.get("request_id", "")
        action = data.get("action", "")
        params = data.get("params", {})

        logger.info(f"📥 收到指令: {action} (request_id: {request_id})")

        try:
            # 查找處理器
            handler = self._handlers.get(action)
            if not handler:
                raise ValueError(f"未知的指令: {action}")

            # 執行指令
            result = await handler(params)

            # 回傳成功結果
            response = {
                "type": "response",
                "request_id": request_id,
                "success": True,
                "data": result,
            }
            await self._websocket.send(json.dumps(response))
            logger.info(f"📤 指令執行成功: {action}")

        except Exception as e:
            logger.exception(f"指令執行失敗: {action}")
            response = {
                "type": "response",
                "request_id": request_id,
                "success": False,
                "error": str(e),
            }
            await self._websocket.send(json.dumps(response))

    # ═══════════════════════════════════════════════════════════════════════════════
    # 指令處理器
    # ═══════════════════════════════════════════════════════════════════════════════

    async def _handle_navigate(self, params: dict[str, Any]) -> dict[str, Any]:
        """處理導航指令"""
        return await self._browser.navigate(
            url=params["url"],
            wait_until=params.get("wait_until", "load"),
            timeout=params.get("timeout", 30000),
        )

    async def _handle_get_url(self, params: dict[str, Any]) -> dict[str, Any]:
        """處理取得 URL 指令"""
        url = await self._browser.get_url()
        return {"url": url}

    async def _handle_get_title(self, params: dict[str, Any]) -> dict[str, Any]:
        """處理取得標題指令"""
        title = await self._browser.get_title()
        return {"title": title}

    async def _handle_get_viewport(self, params: dict[str, Any]) -> dict[str, Any]:
        """處理取得 viewport 指令"""
        viewport = await self._browser.get_viewport()
        return {"viewport": viewport}

    async def _handle_screenshot(self, params: dict[str, Any]) -> dict[str, Any]:
        """處理截圖指令"""
        return await self._browser.screenshot(
            full_page=params.get("full_page", False),
            selector=params.get("selector", ""),
        )

    async def _handle_click(self, params: dict[str, Any]) -> dict[str, Any]:
        """處理點擊指令"""
        return await self._browser.click(
            selector=params["selector"],
            click_count=params.get("click_count", 1),
            timeout=params.get("timeout", 30000),
        )

    async def _handle_type(self, params: dict[str, Any]) -> dict[str, Any]:
        """處理輸入文字指令"""
        return await self._browser.type_text(
            selector=params["selector"],
            text=params["text"],
            clear_first=params.get("clear_first", True),
            press_enter=params.get("press_enter", False),
            timeout=params.get("timeout", 30000),
        )

    async def _handle_wait_for_selector(self, params: dict[str, Any]) -> dict[str, Any]:
        """處理等待元素指令"""
        return await self._browser.wait_for_selector(
            selector=params["selector"],
            timeout=params.get("timeout", 30000),
            state=params.get("state", "visible"),
        )

    async def _handle_query_selector_all(self, params: dict[str, Any]) -> dict[str, Any]:
        """處理查詢元素指令"""
        return await self._browser.query_selector_all(selector=params["selector"])

    async def _handle_inner_text(self, params: dict[str, Any]) -> dict[str, Any]:
        """處理取得文字指令"""
        return await self._browser.inner_text(selector=params["selector"])

    async def _handle_get_content(self, params: dict[str, Any]) -> dict[str, Any]:
        """處理取得 HTML 指令"""
        return await self._browser.get_content()

    async def _handle_evaluate(self, params: dict[str, Any]) -> dict[str, Any]:
        """處理執行 JavaScript 指令"""
        return await self._browser.evaluate(
            script=params["script"],
            arg=params.get("arg"),
        )

    async def _handle_wait_for_url(self, params: dict[str, Any]) -> dict[str, Any]:
        """處理等待 URL 指令"""
        await self._browser.wait_for_url(
            url_pattern=params["url_pattern"],
            timeout=params.get("timeout", 30000),
        )
        return {"success": True}

    async def _handle_wait_for_function(self, params: dict[str, Any]) -> dict[str, Any]:
        """處理等待函數指令"""
        await self._browser.wait_for_function(
            script=params["script"],
            timeout=params.get("timeout", 30000),
        )
        return {"success": True}

    async def _handle_wait_for_timeout(self, params: dict[str, Any]) -> dict[str, Any]:
        """處理等待時間指令"""
        await self._browser.wait_for_timeout(timeout=params["timeout"])
        return {"success": True}

    async def _handle_scroll(self, params: dict[str, Any]) -> dict[str, Any]:
        """處理滾動指令"""
        return await self._browser.scroll(
            scroll_type=params["scroll_type"],
            selector=params.get("selector", ""),
            pixels=params.get("pixels", 0),
        )

    # ═══════════════════════════════════════════════════════════════════════════════
    # 元素操作處理器
    # ═══════════════════════════════════════════════════════════════════════════════

    async def _handle_element_click(self, params: dict[str, Any]) -> dict[str, Any]:
        """處理元素點擊指令"""
        return await self._browser.click(
            selector=params["selector"],
            click_count=params.get("click_count", 1),
            timeout=params.get("timeout", 30000),
        )

    async def _handle_element_type(self, params: dict[str, Any]) -> dict[str, Any]:
        """處理元素輸入指令"""
        return await self._browser.type_text(
            selector=params["selector"],
            text=params["text"],
            timeout=params.get("timeout", 30000),
        )

    async def _handle_element_press(self, params: dict[str, Any]) -> dict[str, Any]:
        """處理元素按鍵指令"""
        # 重新使用 type_text 來模擬按鍵
        page = await self._browser._ensure_page()
        elements = await page.query_selector_all(params["selector"])
        index = params.get("index", 0)
        if index >= len(elements):
            raise RuntimeError(f"元素索引超出範圍: {index} >= {len(elements)}")
        await elements[index].press(params["key"])
        return {"success": True}

    async def _handle_element_inner_text(self, params: dict[str, Any]) -> dict[str, Any]:
        """處理元素文字指令"""
        return await self._browser.element_inner_text(
            selector=params["selector"],
            index=params.get("index", 0),
        )

    async def _handle_element_get_attribute(self, params: dict[str, Any]) -> dict[str, Any]:
        """處理元素屬性指令"""
        return await self._browser.element_get_attribute(
            selector=params["selector"],
            index=params.get("index", 0),
            name=params["name"],
        )

    async def _handle_element_screenshot(self, params: dict[str, Any]) -> dict[str, Any]:
        """處理元素截圖指令"""
        return await self._browser.screenshot(
            full_page=False,
            selector=params["selector"],
        )

    async def _handle_element_scroll_into_view(self, params: dict[str, Any]) -> dict[str, Any]:
        """處理元素滾動到可見指令"""
        return await self._browser.scroll(
            scroll_type="selector",
            selector=params["selector"],
        )

    # ═══════════════════════════════════════════════════════════════════════════════
    # Cookies 處理器
    # ═══════════════════════════════════════════════════════════════════════════════

    async def _handle_get_cookies(self, params: dict[str, Any]) -> dict[str, Any]:
        """處理取得 cookies 指令"""
        return await self._browser.get_cookies()

    async def _handle_add_cookie(self, params: dict[str, Any]) -> dict[str, Any]:
        """處理新增 cookie 指令"""
        return await self._browser.add_cookie(cookie=params["cookie"])

    async def _handle_clear_cookies(self, params: dict[str, Any]) -> dict[str, Any]:
        """處理清除 cookies 指令"""
        return await self._browser.clear_cookies()

    async def stop(self) -> None:
        """停止客戶端"""
        self._running = False
        if self._websocket:
            try:
                await self._websocket.close()
            except Exception:
                pass  # 忽略關閉時的錯誤
        await self._browser.disconnect()
        logger.info("🛑 Browser Agent 已停止")
