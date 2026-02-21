"""
Page Proxy - 遠端 Page 代理

模擬 Playwright Page 物件的介面，將操作轉發到遠端 Browser Agent。
讓 web_playwright 的 Tool 可以透明地使用遠端瀏覽器。
"""

import base64
import logging
from pathlib import Path
from typing import Any

from mcp_server.config import WORK_DIR
from mcp_server.remote.connection_manager import remote_connection_manager

logger = logging.getLogger(__name__)


class PageProxy:
    """
    遠端 Page 代理類別

    模擬 Playwright Page 物件的介面，將所有操作轉發到遠端 Browser Agent。
    """

    def __init__(self) -> None:
        self._screenshot_dir = WORK_DIR / "screenshots"
        self._screenshot_dir.mkdir(parents=True, exist_ok=True)

    @property
    def url(self) -> str:
        """當前頁面 URL（同步屬性，需用 asyncio 間接取得）"""
        # 這個屬性在非同步環境下會有問題，這裡返回空字串
        # 實際 URL 應該透過 async 方法取得
        return ""

    async def get_url(self) -> str:
        """取得當前頁面 URL"""
        result = await remote_connection_manager.send_command("get_url", {})
        return result.get("url", "")

    async def title(self) -> str:
        """取得頁面標題"""
        result = await remote_connection_manager.send_command("get_title", {})
        return result.get("title", "")

    @property
    def viewport_size(self) -> dict[str, int] | None:
        """viewport 尺寸"""
        return None

    async def get_viewport_size(self) -> dict[str, int] | None:
        """取得 viewport 尺寸"""
        result = await remote_connection_manager.send_command("get_viewport", {})
        return result.get("viewport")

    # ═══════════════════════════════════════════════════════════════════════════════
    # 導航相關方法
    # ═══════════════════════════════════════════════════════════════════════════════

    async def goto(
        self,
        url: str,
        wait_until: str = "load",
        timeout: int = 30000,
        **kwargs: Any,
    ) -> Any:
        """
        導航到指定 URL

        Args:
            url: 目標 URL
            wait_until: 等待條件 (load, domcontentloaded, networkidle, commit)
            timeout: 逾時時間（毫秒）
        """
        result = await remote_connection_manager.send_command(
            "navigate",
            {
                "url": url,
                "wait_until": wait_until,
                "timeout": timeout,
            },
            timeout=timeout / 1000 + 10,  # 額外 10 秒緩衝
        )
        return result

    # ═══════════════════════════════════════════════════════════════════════════════
    # 截圖相關方法
    # ═══════════════════════════════════════════════════════════════════════════════

    async def screenshot(
        self,
        full_page: bool = False,
        path: str | None = None,
        **kwargs: Any,
    ) -> bytes:
        """
        截圖

        Args:
            full_page: 是否截取完整頁面
            path: 儲存路徑（可選）

        Returns:
            截圖的 bytes 資料
        """
        result = await remote_connection_manager.send_command(
            "screenshot",
            {
                "full_page": full_page,
            },
            timeout=60.0,  # 截圖可能較慢
        )

        base64_data = result.get("base64", "")
        screenshot_bytes = base64.b64decode(base64_data)

        # 如果指定路徑，儲存檔案
        if path:
            Path(path).write_bytes(screenshot_bytes)

        return screenshot_bytes

    # ═══════════════════════════════════════════════════════════════════════════════
    # 元素操作方法
    # ═══════════════════════════════════════════════════════════════════════════════

    async def wait_for_selector(
        self,
        selector: str,
        timeout: int = 30000,
        state: str = "visible",
        **kwargs: Any,
    ) -> "ElementProxy | None":
        """
        等待元素出現

        Args:
            selector: CSS Selector
            timeout: 逾時時間（毫秒）
            state: 等待狀態 (visible, hidden, attached, detached)

        Returns:
            ElementProxy 或 None
        """
        result = await remote_connection_manager.send_command(
            "wait_for_selector",
            {
                "selector": selector,
                "timeout": timeout,
                "state": state,
            },
            timeout=timeout / 1000 + 5,
        )

        if result.get("found", False):
            return ElementProxy(selector)
        return None

    async def query_selector_all(self, selector: str) -> list["ElementProxy"]:
        """
        查詢所有符合的元素

        Args:
            selector: CSS Selector

        Returns:
            ElementProxy 列表
        """
        result = await remote_connection_manager.send_command(
            "query_selector_all",
            {"selector": selector},
        )

        elements = []
        for i in range(result.get("count", 0)):
            elements.append(ElementProxy(selector, index=i))
        return elements

    # ═══════════════════════════════════════════════════════════════════════════════
    # 內容提取方法
    # ═══════════════════════════════════════════════════════════════════════════════

    async def inner_text(self, selector: str, **kwargs: Any) -> str:
        """取得元素內部文字"""
        result = await remote_connection_manager.send_command(
            "inner_text",
            {"selector": selector},
        )
        return result.get("text", "")

    async def content(self, **kwargs: Any) -> str:
        """取得頁面 HTML"""
        result = await remote_connection_manager.send_command("get_content", {})
        return result.get("html", "")

    # ═══════════════════════════════════════════════════════════════════════════════
    # JavaScript 執行方法
    # ═══════════════════════════════════════════════════════════════════════════════

    async def evaluate(self, script: str, arg: Any = None, **kwargs: Any) -> Any:
        """
        執行 JavaScript

        Args:
            script: JavaScript 代碼
            arg: 傳遞給腳本的參數

        Returns:
            執行結果
        """
        params = {"script": script}
        if arg is not None:
            params["arg"] = arg

        result = await remote_connection_manager.send_command("evaluate", params)
        return result.get("result")

    async def wait_for_function(
        self,
        script: str,
        timeout: int = 30000,
        **kwargs: Any,
    ) -> Any:
        """
        等待 JavaScript 函數返回 true

        Args:
            script: JavaScript 代碼
            timeout: 逾時時間（毫秒）
        """
        await remote_connection_manager.send_command(
            "wait_for_function",
            {
                "script": script,
                "timeout": timeout,
            },
            timeout=timeout / 1000 + 5,
        )

    # ═══════════════════════════════════════════════════════════════════════════════
    # URL 等待方法
    # ═══════════════════════════════════════════════════════════════════════════════

    async def wait_for_url(
        self,
        url_pattern: str,
        timeout: int = 30000,
        **kwargs: Any,
    ) -> None:
        """
        等待 URL 符合指定模式

        Args:
            url_pattern: URL 模式（支援 * 萬用字元）
            timeout: 逾時時間（毫秒）
        """
        await remote_connection_manager.send_command(
            "wait_for_url",
            {
                "url_pattern": url_pattern,
                "timeout": timeout,
            },
            timeout=timeout / 1000 + 5,
        )

    # ═══════════════════════════════════════════════════════════════════════════════
    # 等待方法
    # ═══════════════════════════════════════════════════════════════════════════════

    async def wait_for_timeout(self, timeout: int) -> None:
        """
        等待指定時間

        Args:
            timeout: 等待時間（毫秒）
        """
        await remote_connection_manager.send_command(
            "wait_for_timeout",
            {"timeout": timeout},
            timeout=timeout / 1000 + 5,
        )

    # ═══════════════════════════════════════════════════════════════════════════════
    # Cookies 操作方法
    # ═══════════════════════════════════════════════════════════════════════════════

    async def get_cookies(self) -> list[dict[str, Any]]:
        """
        取得當前頁面的所有 cookies

        Returns:
            cookies 列表
        """
        result = await remote_connection_manager.send_command("get_cookies", {})
        return result.get("cookies", [])

    async def add_cookies(self, cookies: list[dict[str, Any]]) -> None:
        """
        新增 cookies

        Args:
            cookies: cookie 物件列表
        """
        for cookie in cookies:
            await remote_connection_manager.send_command(
                "add_cookie",
                {"cookie": cookie},
            )

    async def clear_cookies(self) -> None:
        """清除所有 cookies"""
        await remote_connection_manager.send_command("clear_cookies", {})


class ElementProxy:
    """
    遠端 Element 代理類別

    模擬 Playwright ElementHandle 物件。
    """

    def __init__(self, selector: str, index: int = 0) -> None:
        self._selector = selector
        self._index = index

    async def click(self, click_count: int = 1, **kwargs: Any) -> None:
        """點擊元素"""
        await remote_connection_manager.send_command(
            "element_click",
            {
                "selector": self._selector,
                "index": self._index,
                "click_count": click_count,
            },
        )

    async def type(self, text: str, delay: int = 0, **kwargs: Any) -> None:
        """
        輸入文字

        Args:
            text: 要輸入的文字
            delay: 每個字元間的延遲（毫秒）
        """
        await remote_connection_manager.send_command(
            "element_type",
            {
                "selector": self._selector,
                "index": self._index,
                "text": text,
                "delay": delay,
            },
        )

    async def press(self, key: str, **kwargs: Any) -> None:
        """按鍵"""
        await remote_connection_manager.send_command(
            "element_press",
            {
                "selector": self._selector,
                "index": self._index,
                "key": key,
            },
        )

    async def inner_text(self, **kwargs: Any) -> str:
        """取得元素內部文字"""
        result = await remote_connection_manager.send_command(
            "element_inner_text",
            {
                "selector": self._selector,
                "index": self._index,
            },
        )
        return result.get("text", "")

    async def get_attribute(self, name: str, **kwargs: Any) -> str | None:
        """取得元素屬性"""
        result = await remote_connection_manager.send_command(
            "element_get_attribute",
            {
                "selector": self._selector,
                "index": self._index,
                "name": name,
            },
        )
        return result.get("value")

    async def screenshot(self, **kwargs: Any) -> bytes:
        """截取元素截圖"""
        result = await remote_connection_manager.send_command(
            "element_screenshot",
            {
                "selector": self._selector,
                "index": self._index,
            },
            timeout=60.0,
        )

        base64_data = result.get("base64", "")
        return base64.b64decode(base64_data)

    async def scroll_into_view_if_needed(self, **kwargs: Any) -> None:
        """滾動到元素可見"""
        await remote_connection_manager.send_command(
            "element_scroll_into_view",
            {
                "selector": self._selector,
                "index": self._index,
            },
        )
