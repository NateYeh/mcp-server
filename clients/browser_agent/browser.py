"""
瀏覽器操作模組

封裝 Playwright CDP 瀏覽器操作，提供統一的操作接口。
"""

import base64
import logging
from typing import Any

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)


class BrowserController:
    """
    瀏覽器控制器

    透過 Playwright CDP 連接本地 Chrome 瀏覽器，提供操作接口。
    """

    def __init__(self, cdp_endpoint: str = "http://localhost:9222"):
        self._cdp_endpoint = cdp_endpoint
        self._playwright: Any = None
        self._browser: Any = None
        self._page: Any = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        """是否已連接到瀏覽器"""
        return self._connected and self._browser is not None and self._browser.is_connected()

    async def connect(self) -> bool:
        """
        連接到 Chrome CDP

        Returns:
            是否連接成功
        """
        try:
            logger.info(f"正在連接到 Chrome CDP: {self._cdp_endpoint}")
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.connect_over_cdp(self._cdp_endpoint)
            logger.info(f"✅ 已連接到瀏覽器: {self._browser.version}")

            # 取得或建立 Page
            contexts = self._browser.contexts
            if contexts and contexts[0].pages:
                self._page = contexts[0].pages[0]
                logger.info(f"使用現有 Page: {self._page.url}")
            else:
                if contexts:
                    self._page = await contexts[0].new_page()
                else:
                    context = await self._browser.new_context()
                    self._page = await context.new_page()
                logger.info("建立新 Page")

            self._connected = True
            return True

        except Exception as e:
            logger.exception(f"連接 Chrome CDP 失敗: {e}")
            await self.disconnect()
            return False

    async def disconnect(self) -> None:
        """中斷瀏覽器連接"""
        self._connected = False
        self._page = None
        self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        logger.info("已中斷瀏覽器連接")

    async def _ensure_page(self) -> Any:
        """確保有可用的 Page"""
        if not self.is_connected or self._page is None:
            raise RuntimeError("瀏覽器未連接")
        return self._page

    # ═══════════════════════════════════════════════════════════════════════════════
    # 操作方法
    # ═══════════════════════════════════════════════════════════════════════════════

    async def get_url(self) -> str:
        """取得當前 URL"""
        page = await self._ensure_page()
        return page.url

    async def get_title(self) -> str:
        """取得頁面標題"""
        page = await self._ensure_page()
        return await page.title()

    async def get_viewport(self) -> dict[str, int] | None:
        """取得 viewport 尺寸"""
        page = await self._ensure_page()
        return page.viewport_size

    async def navigate(self, url: str, wait_until: str = "load", timeout: int = 30000) -> dict[str, Any]:
        """
        導航到指定 URL

        Args:
            url: 目標 URL
            wait_until: 等待條件
            timeout: 逾時時間（毫秒）

        Returns:
            導航結果
        """
        page = await self._ensure_page()
        await page.goto(url, wait_until=wait_until, timeout=timeout)
        return {
            "url": page.url,
            "title": await page.title(),
        }

    async def screenshot(self, full_page: bool = False, selector: str = "") -> dict[str, Any]:
        """
        截圖

        Args:
            full_page: 是否截取完整頁面
            selector: 截取特定元素（可選）

        Returns:
            包含 base64 編碼的結果
        """
        page = await self._ensure_page()

        if selector:
            element = await page.wait_for_selector(selector, timeout=10000)
            if not element:
                raise RuntimeError(f"找不到元素: {selector}")
            screenshot_bytes = await element.screenshot()
        else:
            screenshot_bytes = await page.screenshot(full_page=full_page)

        return {
            "base64": base64.b64encode(screenshot_bytes).decode("utf-8"),
            "size": len(screenshot_bytes),
        }

    async def click(self, selector: str, click_count: int = 1, timeout: int = 30000) -> dict[str, Any]:
        """
        點擊元素

        Args:
            selector: CSS Selector
            click_count: 點擊次數
            timeout: 逾時時間

        Returns:
            點擊結果
        """
        page = await self._ensure_page()
        element = await page.wait_for_selector(selector, timeout=timeout)
        if not element:
            raise RuntimeError(f"找不到元素: {selector}")
        await element.click(click_count=click_count)
        return {"success": True, "current_url": page.url}

    async def type_text(
        self,
        selector: str,
        text: str,
        clear_first: bool = True,
        press_enter: bool = False,
        timeout: int = 30000,
    ) -> dict[str, Any]:
        """
        輸入文字

        Args:
            selector: CSS Selector
            text: 要輸入的文字
            clear_first: 是否先清空
            press_enter: 是否按 Enter
            timeout: 逾時時間

        Returns:
            輸入結果
        """
        page = await self._ensure_page()
        element = await page.wait_for_selector(selector, timeout=timeout)
        if not element:
            raise RuntimeError(f"找不到元素: {selector}")

        if clear_first:
            await element.click(click_count=3)
            await element.press("Backspace")

        await element.type(text)

        if press_enter:
            await element.press("Enter")

        return {"success": True, "current_url": page.url}

    async def wait_for_selector(
        self,
        selector: str,
        timeout: int = 30000,
        state: str = "visible",
    ) -> dict[str, Any]:
        """
        等待元素

        Args:
            selector: CSS Selector
            timeout: 逾時時間
            state: 等待狀態

        Returns:
            等待結果
        """
        page = await self._ensure_page()
        element = await page.wait_for_selector(selector, timeout=timeout, state=state)
        return {"found": element is not None}

    async def query_selector_all(self, selector: str) -> dict[str, Any]:
        """
        查詢所有符合的元素

        Args:
            selector: CSS Selector

        Returns:
            元素數量和索引列表
        """
        page = await self._ensure_page()
        elements = await page.query_selector_all(selector)
        return {"count": len(elements)}

    async def inner_text(self, selector: str) -> dict[str, Any]:
        """取得元素內部文字"""
        page = await self._ensure_page()
        text = await page.inner_text(selector)
        return {"text": text}

    async def get_content(self) -> dict[str, Any]:
        """取得頁面 HTML"""
        page = await self._ensure_page()
        html = await page.content()
        return {"html": html}

    async def evaluate(self, script: str, arg: Any = None) -> dict[str, Any]:
        """
        執行 JavaScript

        Args:
            script: JavaScript 代碼
            arg: 傳遞給腳本的參數

        Returns:
            執行結果
        """
        page = await self._ensure_page()
        if arg is not None:
            result = await page.evaluate(script, arg)
        else:
            result = await page.evaluate(script)
        return {"result": result}

    async def wait_for_url(self, url_pattern: str, timeout: int = 30000) -> None:
        """等待 URL 符合模式"""
        page = await self._ensure_page()
        await page.wait_for_url(url_pattern, timeout=timeout)

    async def wait_for_function(self, script: str, timeout: int = 30000) -> None:
        """等待 JavaScript 函數返回 true"""
        page = await self._ensure_page()
        await page.wait_for_function(script, timeout=timeout)

    async def wait_for_timeout(self, timeout: int) -> None:
        """等待指定時間"""
        page = await self._ensure_page()
        await page.wait_for_timeout(timeout)

    async def scroll(self, scroll_type: str, selector: str = "", pixels: int = 0) -> dict[str, Any]:
        """
        滾動頁面

        Args:
            scroll_type: 滾動類型 (top, bottom, selector, pixels)
            selector: CSS Selector（當 scroll_type=selector 時使用）
            pixels: 像素數（當 scroll_type=pixels 時使用）

        Returns:
            滾動結果
        """
        page = await self._ensure_page()

        if scroll_type == "top":
            await page.evaluate("window.scrollTo(0, 0)")
        elif scroll_type == "bottom":
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        elif scroll_type == "selector":
            if not selector:
                raise RuntimeError("scroll_type=selector 時必須提供 selector")
            element = await page.wait_for_selector(selector)
            if element:
                await element.scroll_into_view_if_needed()
        elif scroll_type == "pixels":
            await page.evaluate(f"window.scrollBy(0, {pixels})")

        scroll_pos = await page.evaluate("({ x: window.scrollX, y: window.scrollY })")
        return {"scroll_position": scroll_pos}

    # ═══════════════════════════════════════════════════════════════════════════════
    # 元素操作方法
    # ═══════════════════════════════════════════════════════════════════════════════

    async def element_get_attribute(self, selector: str, index: int, name: str) -> dict[str, Any]:
        """取得元素屬性"""
        page = await self._ensure_page()
        elements = await page.query_selector_all(selector)
        if index >= len(elements):
            raise RuntimeError(f"元素索引超出範圍: {index} >= {len(elements)}")
        value = await elements[index].get_attribute(name)
        return {"value": value}

    async def element_inner_text(self, selector: str, index: int) -> dict[str, Any]:
        """取得元素內部文字"""
        page = await self._ensure_page()
        elements = await page.query_selector_all(selector)
        if index >= len(elements):
            raise RuntimeError(f"元素索引超出範圍: {index} >= {len(elements)}")
        text = await elements[index].inner_text()
        return {"text": text}

    # ═══════════════════════════════════════════════════════════════════════════════
    # Cookies 操作方法
    # ═══════════════════════════════════════════════════════════════════════════════

    async def get_cookies(self) -> dict[str, Any]:
        """
        取得當前頁面的所有 cookies

        Returns:
            cookies 列表
        """
        page = await self._ensure_page()
        context = page.context
        cookies = await context.cookies()
        return {"cookies": cookies, "count": len(cookies)}

    async def add_cookie(self, cookie: dict[str, Any]) -> dict[str, Any]:
        """
        新增 cookie

        Args:
            cookie: cookie 物件，需包含 name, value, 可選 domain, path 等

        Returns:
            操作結果
        """
        page = await self._ensure_page()
        context = page.context
        await context.add_cookies([cookie])
        return {"success": True, "cookie": cookie}

    async def clear_cookies(self) -> dict[str, Any]:
        """
        清除當前 context 的所有 cookies

        Returns:
            操作結果
        """
        page = await self._ensure_page()
        context = page.context
        await context.clear_cookies()
        return {"success": True}
