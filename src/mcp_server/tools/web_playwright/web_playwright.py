"""
Web Playwright Tool

透過 Playwright CDP 連接瀏覽器，提供進階網頁自動化操作功能。
適用於需要複雜互動的場景：登入、表單填寫、點擊、截圖等。

支援兩種模式：
1. 本地 CDP：直接連接本地 Chrome CDP
2. 遠端模式：透過 WebSocket 連接遠端 Browser Agent
"""

import asyncio
import base64
import logging
from datetime import datetime
from typing import Any, Optional, cast

from playwright.async_api import Page

from mcp_server.config import (
    PLAYWRIGHT_CDP_ENDPOINT,
    PLAYWRIGHT_DEFAULT_TIMEOUT,
    REMOTE_BROWSER_ENABLED,
    WORK_DIR,
)
from mcp_server.schemas import ExecutionResult
from mcp_server.tools.base import registry

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════════════════════════
CDP_ENDPOINT = PLAYWRIGHT_CDP_ENDPOINT
CDP_FALLBACK_ENDPOINT = "http://127.0.0.1:9222"  # 備用 CDP Endpoint
DEFAULT_TIMEOUT = PLAYWRIGHT_DEFAULT_TIMEOUT
SCREENSHOT_DIR = WORK_DIR / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 瀏覽器連接管理器（Singleton）
# ═══════════════════════════════════════════════════════════════════════════════
class BrowserManager:
    """
    瀏覽器連接管理器

    使用 Singleton 模式，支援兩種連接模式：
    1. 遠端模式：優先使用遠端 Browser Agent（透過 WebSocket）
    2. 本地模式：連接本地 CDP 瀏覽器
    """

    _instance: Optional["BrowserManager"] = None
    _playwright: Any = None
    _browser: Any = None
    _page: Page | None = None
    _lock: asyncio.Lock = asyncio.Lock()
    _remote_page_proxy: Any = None  # PageProxy 實例

    def __new__(cls) -> "BrowserManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def _ensure_connected(self) -> None:
        """
        確保瀏覽器連接正常

        優先順序：
        1. 檢查遠端連線是否可用
        2. 若無遠端連線，使用本地 CDP
        """
        async with self._lock:
            # 檢查遠端連線
            if REMOTE_BROWSER_ENABLED:
                try:
                    from mcp_server.remote.connection_manager import remote_connection_manager

                    if remote_connection_manager.is_connected:
                        # 延遲導入 PageProxy
                        from mcp_server.remote.page_proxy import PageProxy

                        self._remote_page_proxy = PageProxy()
                        logger.info("✅ 使用遠端瀏覽器連線")
                        return
                except ImportError as e:
                    logger.warning(f"無法導入遠端連線模組: {e}")

            # 檢查目前連線
            if self._browser is not None and self._browser.is_connected():
                return

            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()

            # 優先嘗試 CDP 連線 (如果定義了 PLAYWRIGHT_CDP_ENDPOINT)
            if CDP_ENDPOINT:
                endpoints_to_try = [CDP_ENDPOINT]
                if CDP_ENDPOINT != CDP_FALLBACK_ENDPOINT:
                    endpoints_to_try.append(CDP_FALLBACK_ENDPOINT)

                for endpoint in endpoints_to_try:
                    try:
                        logger.info(f"正在嘗試連接遠端/外部 CDP: {endpoint}")
                        self._browser = await self._playwright.chromium.connect_over_cdp(endpoint)
                        logger.info(f"✅ 已連接到遠端瀏覽器: {self._browser.version}")
                        return
                    except Exception as e:
                        logger.warning(f"遠端連線 {endpoint} 失敗: {e}，準備嘗試下一種模式。")

            # 如果 CDP 連線失敗或未定義，則啟動容器內建瀏覽器 (Fallback)
            try:
                import os

                headless = os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() == "true"
                logger.info(f"正在啟動容器內建 Chromium 瀏覽器 (headless={headless})...")
                self._browser = await self._playwright.chromium.launch(
                    headless=headless,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],  # Docker 環境必備
                )
                logger.info(f"✅ 已啟動內建瀏覽器: {self._browser.version}")
            except Exception as e:
                if self._playwright:
                    await self._playwright.stop()
                    self._playwright = None
                logger.error(f"❌ 無法啟動內建瀏覽器: {e}")
                raise RuntimeError(f"瀏覽器啟動失敗 (CDP與內建皆不可用): {e}") from e

            # 取得或建立 Page
            contexts = self._browser.contexts
            if contexts and contexts[0].pages:
                self._page = contexts[0].pages[0]
                page_url = self._page.url if self._page else "unknown"
                logger.info(f"使用現有 Page: {page_url}")
            else:
                if contexts:
                    self._page = await contexts[0].new_page()
                else:
                    context = await self._browser.new_context()
                    self._page = await context.new_page()
                logger.info("建立新 Page")

    async def get_page(self) -> Page:
        """
        取得當前 Page

        Returns:
            Page 物件（本地 CDP 或遠端 PageProxy）
        """
        await self._ensure_connected()

        # 優先返回遠端 PageProxy
        if self._remote_page_proxy is not None:
            return self._remote_page_proxy

        if self._page is None:
            raise RuntimeError("無法取得 Page")
        return self._page

    async def disconnect(self) -> None:
        """中斷連接（但不關閉外部瀏覽器）"""
        self._remote_page_proxy = None

        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
            self._browser = None
            self._page = None
            logger.info("已中斷瀏覽器連接")

    @property
    def is_remote(self) -> bool:
        """是否使用遠端連線"""
        return self._remote_page_proxy is not None

    @property
    def connection_info(self) -> dict[str, Any]:
        """取得連線資訊"""
        if self._remote_page_proxy is not None:
            try:
                from mcp_server.remote.connection_manager import remote_connection_manager

                return {
                    "mode": "remote",
                    "connected": remote_connection_manager.is_connected,
                    **remote_connection_manager.connection_info,
                }
            except ImportError:
                return {"mode": "remote", "connected": False}

        return {
            "mode": "local",
            "connected": self._browser is not None and self._browser.is_connected(),
            "cdp_endpoint": CDP_ENDPOINT,
        }


# 全域管理器實例
browser_manager = BrowserManager()


# ═══════════════════════════════════════════════════════════════════════════════
# Tool: web_navigate
# ═══════════════════════════════════════════════════════════════════════════════
@registry.register(
    name="web_navigate",
    description="導航到指定 URL，等待頁面載入完成。可設定等待條件（load、domcontentloaded、networkidle）。",
    input_schema={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "要導航的 URL"},
            "wait_until": {
                "type": "string",
                "enum": ["load", "domcontentloaded", "networkidle", "commit"],
                "default": "load",
                "description": "等待條件：load（完整載入）、domcontentloaded（DOM 載入）、networkidle（網路閒置）、commit（導航開始）",
            },
            "timeout": {"type": "integer", "default": 30000, "description": "超時時間（毫秒），預設 30000"},
        },
        "required": ["url"],
    },
)
async def handle_web_navigate(args: dict[str, Any]) -> ExecutionResult:
    """處理 web_navigate 請求"""
    url = args.get("url", "")
    wait_until = args.get("wait_until", "load")
    timeout = args.get("timeout", DEFAULT_TIMEOUT)

    if not url:
        return ExecutionResult(success=False, error_type="ValueError", error_message="URL 不可為空")

    # URL 驗證
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        page = await browser_manager.get_page()
        start_time = datetime.now()

        await page.goto(url, wait_until=wait_until, timeout=timeout)

        execution_time = (datetime.now() - start_time).total_seconds()
        title = await page.title()

        return ExecutionResult(
            success=True, stdout=f"✅ 導航完成\nURL: {page.url}\n標題: {title}", execution_time=f"{execution_time:.3f}s", metadata={"url": page.url, "title": title}
        )
    except Exception as e:
        logger.exception(f"導航失敗: {e}")
        return ExecutionResult(success=False, error_type=type(e).__name__, error_message=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# Tool: web_screenshot
# ═══════════════════════════════════════════════════════════════════════════════
@registry.register(
    name="web_screenshot",
    description="網頁截圖。支援全頁截圖、可視區域截圖、特定元素截圖。可選擇是否儲存檔案與回傳 Base64。",
    input_schema={
        "type": "object",
        "properties": {
            "full_page": {"type": "boolean", "default": False, "description": "是否截取完整頁面（含滾動區域）"},
            "selector": {"type": "string", "description": "CSS Selector，截取特定元素（可選）"},
            "save_to_file": {"type": "boolean", "default": True, "description": "是否儲存為檔案"},
            "include_base64": {"type": "boolean", "default": True, "description": "是否回傳 Base64 編碼（讓 AI 能直接分析圖片）"},
            "timeout": {"type": "integer", "default": 30000, "description": "超時時間（毫秒）"},
        },
        "required": [],
    },
)
async def handle_web_screenshot(args: dict[str, Any]) -> ExecutionResult:
    """處理 web_screenshot 請求"""
    full_page = args.get("full_page", False)
    selector = args.get("selector", "")
    save_to_file = args.get("save_to_file", True)
    include_base64 = args.get("include_base64", True)
    timeout = args.get("timeout", DEFAULT_TIMEOUT)

    try:
        page = await browser_manager.get_page()
        start_time = datetime.now()

        screenshot_bytes: bytes

        if selector:
            # 截取特定元素
            element = await page.wait_for_selector(selector, timeout=timeout)
            if not element:
                return ExecutionResult(success=False, error_type="ElementNotFoundError", error_message=f"找不到元素: {selector}")
            screenshot_bytes = await element.screenshot()
        else:
            # 截取整頁或可視區域
            screenshot_bytes = await page.screenshot(full_page=full_page)

        execution_time = (datetime.now() - start_time).total_seconds()

        # 建立結果
        metadata: dict[str, Any] = {"full_page": full_page, "selector": selector or None}
        stdout_parts: list[str] = ["📷 截圖完成"]

        # 儲存檔案
        if save_to_file:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            filename = f"screenshot_{timestamp}.png"
            filepath = SCREENSHOT_DIR / filename
            filepath.write_bytes(screenshot_bytes)
            metadata["file_path"] = str(filepath)
            metadata["file_size_kb"] = round(len(screenshot_bytes) / 1024, 2)
            stdout_parts.append(f"檔案: {filepath}")
            stdout_parts.append(f"大小: {metadata['file_size_kb']} KB")

        # 取得頁面尺寸
        viewport = page.viewport_size
        if viewport:
            metadata["viewport"] = f"{viewport['width']}x{viewport['height']}"

        # Base64 編碼
        if include_base64:
            metadata["base64"] = base64.b64encode(screenshot_bytes).decode("utf-8")
            metadata["base64_length"] = len(metadata["base64"])
            stdout_parts.append(f"Base64 長度: {metadata['base64_length']} 字元")

        return ExecutionResult(success=True, stdout="\n".join(stdout_parts), execution_time=f"{execution_time:.3f}s", metadata=metadata)
    except Exception as e:
        logger.exception(f"截圖失敗: {e}")
        return ExecutionResult(success=False, error_type=type(e).__name__, error_message=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# Tool: web_extract
# ═══════════════════════════════════════════════════════════════════════════════
@registry.register(
    name="web_extract",
    description="提取網頁內容。支援提取文字、HTML、特定元素、連結列表等。",
    input_schema={
        "type": "object",
        "properties": {
            "extract_type": {
                "type": "string",
                "enum": ["text", "html", "elements", "links", "images"],
                "default": "text",
                "description": "提取類型：text（純文字）、html（完整 HTML）、elements（特定元素）、links（所有連結）、images（所有圖片）",
            },
            "selector": {"type": "string", "description": "CSS Selector（當 extract_type=elements 時使用）"},
            "attribute": {"type": "string", "description": "要提取的屬性名稱（例如 href、src、data-id）"},
        },
        "required": [],
    },
)
async def handle_web_extract(args: dict[str, Any]) -> ExecutionResult:
    """處理 web_extract 請求"""
    extract_type = args.get("extract_type", "text")
    selector = args.get("selector", "")
    attribute = args.get("attribute", "")

    try:
        page = await browser_manager.get_page()
        start_time = datetime.now()

        result_data: Any = None
        stdout_parts: list[str] = []

        if extract_type == "text":
            # 提取頁面純文字
            result_data = await page.inner_text("body")
            stdout_parts.append(f"📄 頁面文字內容（{len(result_data)} 字元）:")
            stdout_parts.append(result_data[:2000] + ("..." if len(result_data) > 2000 else ""))

        elif extract_type == "html":
            # 提取完整 HTML
            result_data = await page.content()
            stdout_parts.append(f"📄 頁面 HTML（{len(result_data)} 字元）:")
            stdout_parts.append(result_data[:2000] + ("..." if len(result_data) > 2000 else ""))

        elif extract_type == "elements":
            # 提取特定元素
            if not selector:
                return ExecutionResult(success=False, error_type="ValueError", error_message="extract_type=elements 時必須提供 selector")

            elements = await page.query_selector_all(selector)
            results: list[dict[str, Any]] = []

            for i, elem in enumerate(elements[:50]):  # 最多 50 個元素
                text = await elem.inner_text()
                elem_data = {"index": i, "text": text[:500]}
                if attribute:
                    attr_value = await elem.get_attribute(attribute)
                    elem_data[attribute] = attr_value
                results.append(elem_data)

            result_data = results
            stdout_parts.append(f"📦 找到 {len(elements)} 個元素，回傳前 {len(results)} 個")

        elif extract_type == "links":
            # 提取所有連結
            links = await page.query_selector_all("a[href]")
            results = []
            for link in links[:100]:  # 最多 100 個連結
                href = await link.get_attribute("href")
                text = await link.inner_text()
                if href:
                    results.append({"href": href, "text": text.strip()[:200]})

            result_data = results
            stdout_parts.append(f"🔗 找到 {len(links)} 個連結，回傳前 {len(results)} 個")

        elif extract_type == "images":
            # 提取所有圖片
            images = await page.query_selector_all("img[src]")
            results = []
            for img in images[:100]:  # 最多 100 張圖片
                src = await img.get_attribute("src")
                alt = await img.get_attribute("alt") or ""
                if src:
                    results.append({"src": src, "alt": alt[:200]})

            result_data = results
            stdout_parts.append(f"🖼️ 找到 {len(images)} 張圖片，回傳前 {len(results)} 張")

        execution_time = (datetime.now() - start_time).total_seconds()

        return ExecutionResult(success=True, stdout="\n".join(stdout_parts), execution_time=f"{execution_time:.3f}s", metadata={"extract_type": extract_type, "data": result_data})
    except Exception as e:
        logger.exception(f"提取內容失敗: {e}")
        return ExecutionResult(success=False, error_type=type(e).__name__, error_message=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# Tool: web_click
# ═══════════════════════════════════════════════════════════════════════════════
@registry.register(
    name="web_click",
    description="點擊網頁元素。使用 CSS Selector 定位元素。",
    input_schema={
        "type": "object",
        "properties": {
            "selector": {"type": "string", "description": "CSS Selector，例如 '#submit-btn', '.login-button', 'button[type=submit]'"},
            "click_count": {"type": "integer", "default": 1, "description": "點擊次數（1=單擊, 2=雙擊）"},
            "timeout": {"type": "integer", "default": 30000, "description": "等待元素超時時間（毫秒）"},
            "wait_after": {"type": "integer", "default": 1000, "description": "點擊後等待時間（毫秒），讓頁面反應"},
        },
        "required": ["selector"],
    },
)
async def handle_web_click(args: dict[str, Any]) -> ExecutionResult:
    """處理 web_click 請求"""
    selector = args.get("selector", "")
    click_count = args.get("click_count", 1)
    timeout = args.get("timeout", DEFAULT_TIMEOUT)
    wait_after = args.get("wait_after", 1000)

    if not selector:
        return ExecutionResult(success=False, error_type="ValueError", error_message="selector 不可為空")

    try:
        page = await browser_manager.get_page()
        start_time = datetime.now()

        # 等待元素出現
        element = await page.wait_for_selector(selector, timeout=timeout)
        if not element:
            return ExecutionResult(success=False, error_type="ElementNotFoundError", error_message=f"找不到元素: {selector}")

        # 執行點擊
        await element.click(click_count=click_count)

        # 等待反應
        if wait_after > 0:
            await page.wait_for_timeout(wait_after)

        execution_time = (datetime.now() - start_time).total_seconds()

        return ExecutionResult(
            success=True,
            stdout=f"✅ 已點擊元素: {selector}\n當前 URL: {page.url}",
            execution_time=f"{execution_time:.3f}s",
            metadata={"selector": selector, "click_count": click_count, "current_url": page.url},
        )
    except Exception as e:
        logger.exception(f"點擊失敗: {e}")
        return ExecutionResult(success=False, error_type=type(e).__name__, error_message=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# Tool: web_fill
# ═══════════════════════════════════════════════════════════════════════════════
@registry.register(
    name="web_fill",
    description="填寫表單輸入框。填寫完成後自動按 Enter 鍵。使用 CSS Selector 定位輸入框。",
    input_schema={
        "type": "object",
        "properties": {
            "selector": {"type": "string", "description": "CSS Selector，例如 '#username', 'input[name=email]', '.search-box'"},
            "value": {"type": "string", "description": "要填寫的值"},
            "press_enter": {"type": "boolean", "default": True, "description": "填寫後是否按 Enter 鍵"},
            "clear_first": {"type": "boolean", "default": True, "description": "是否先清空輸入框"},
            "timeout": {"type": "integer", "default": 30000, "description": "等待元素超時時間（毫秒）"},
            "wait_after": {"type": "integer", "default": 1000, "description": "填寫後等待時間（毫秒）"},
        },
        "required": ["selector", "value"],
    },
)
async def handle_web_fill(args: dict[str, Any]) -> ExecutionResult:
    """處理 web_fill 請求"""
    selector = args.get("selector", "")
    value = args.get("value", "")
    press_enter = args.get("press_enter", True)
    clear_first = args.get("clear_first", True)
    timeout = args.get("timeout", DEFAULT_TIMEOUT)
    wait_after = args.get("wait_after", 1000)

    if not selector:
        return ExecutionResult(success=False, error_type="ValueError", error_message="selector 不可為空")

    try:
        page = await browser_manager.get_page()
        start_time = datetime.now()

        # 等待元素出現
        element = await page.wait_for_selector(selector, timeout=timeout)
        if not element:
            return ExecutionResult(success=False, error_type="ElementNotFoundError", error_message=f"找不到元素: {selector}")

        # 清空並填寫（使用 triple click + type 代替 clear）
        if clear_first:
            await element.click(click_count=3)
            await element.press("Backspace")

        await element.type(value)

        # 按 Enter
        if press_enter:
            await element.press("Enter")

        # 等待反應
        if wait_after > 0:
            await page.wait_for_timeout(wait_after)

        execution_time = (datetime.now() - start_time).total_seconds()

        stdout_parts = [f"✅ 已填寫元素: {selector}", f"值: {value}"]
        if press_enter:
            stdout_parts.append("已按 Enter")
        stdout_parts.append(f"當前 URL: {page.url}")

        return ExecutionResult(
            success=True,
            stdout="\n".join(stdout_parts),
            execution_time=f"{execution_time:.3f}s",
            metadata={"selector": selector, "value": value, "press_enter": press_enter, "current_url": page.url},
        )
    except Exception as e:
        logger.exception(f"填寫失敗: {e}")
        return ExecutionResult(success=False, error_type=type(e).__name__, error_message=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# Tool: web_evaluate
# ═══════════════════════════════════════════════════════════════════════════════
@registry.register(
    name="web_evaluate",
    description="在頁面中執行 JavaScript 代碼，並回傳結果。",
    input_schema={
        "type": "object",
        "properties": {
            "script": {"type": "string", "description": "要執行的 JavaScript 代碼。可以使用 return 回傳結果。例如：'return document.title' 或 'return window.location.href'"},
            "arg": {"type": "string", "description": "傳遞給腳本的參數（可選）"},
        },
        "required": ["script"],
    },
)
async def handle_web_evaluate(args: dict[str, Any]) -> ExecutionResult:
    """處理 web_evaluate 請求"""
    script = args.get("script", "")
    arg = args.get("arg")

    if not script:
        return ExecutionResult(success=False, error_type="ValueError", error_message="script 不可為空")

    try:
        page = await browser_manager.get_page()
        start_time = datetime.now()

        # 執行 JavaScript
        if arg is not None:
            result = await page.evaluate(script, arg)
        else:
            result = await page.evaluate(script)

        execution_time = (datetime.now() - start_time).total_seconds()

        # 格式化結果
        result_str = str(result) if result is not None else "null"

        return ExecutionResult(
            success=True,
            stdout=f"✅ JavaScript 執行完成\n結果: {result_str[:2000] + '...' if len(result_str) > 2000 else result_str}",
            execution_time=f"{execution_time:.3f}s",
            metadata={"script": script, "result": result},
        )
    except Exception as e:
        logger.exception(f"JavaScript 執行失敗: {e}")
        return ExecutionResult(success=False, error_type=type(e).__name__, error_message=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# Tool: web_wait
# ═══════════════════════════════════════════════════════════════════════════════
@registry.register(
    name="web_wait",
    description="等待頁面元素出現、消失或達到指定時間。",
    input_schema={
        "type": "object",
        "properties": {
            "wait_type": {
                "type": "string",
                "enum": ["selector", "hidden", "timeout", "url", "title"],
                "default": "selector",
                "description": "等待類型：selector（元素出現）、hidden（元素消失）、timeout（指定時間）、url（URL 包含）、title（標題包含）",
            },
            "selector": {"type": "string", "description": "CSS Selector（當 wait_type=selector 或 hidden 時使用）"},
            "value": {"type": "string", "description": "等待的值（當 wait_type=url 或 title 時，表示要包含的字串）"},
            "timeout": {"type": "integer", "default": 30000, "description": "超時時間（毫秒）"},
        },
        "required": [],
    },
)
async def handle_web_wait(args: dict[str, Any]) -> ExecutionResult:
    """處理 web_wait 請求"""
    wait_type = args.get("wait_type", "selector")
    selector = args.get("selector", "")
    value = args.get("value", "")
    timeout = args.get("timeout", DEFAULT_TIMEOUT)

    try:
        page = await browser_manager.get_page()
        start_time = datetime.now()
        stdout = ""

        if wait_type == "selector":
            if not selector:
                return ExecutionResult(success=False, error_type="ValueError", error_message="wait_type=selector 時必須提供 selector")
            await page.wait_for_selector(selector, timeout=timeout)
            stdout = f"✅ 元素已出現: {selector}"

        elif wait_type == "hidden":
            if not selector:
                return ExecutionResult(success=False, error_type="ValueError", error_message="wait_type=hidden 時必須提供 selector")
            await page.wait_for_selector(selector, state="hidden", timeout=timeout)
            stdout = f"✅ 元素已消失: {selector}"

        elif wait_type == "timeout":
            wait_ms = int(value) if value.isdigit() else timeout
            await page.wait_for_timeout(wait_ms)
            stdout = f"✅ 已等待 {wait_ms} 毫秒"

        elif wait_type == "url":
            if not value:
                return ExecutionResult(success=False, error_type="ValueError", error_message="wait_type=url 時必須提供 value")
            await page.wait_for_url(f"*{value}*", timeout=timeout)
            stdout = f"✅ URL 已包含: {value}"

        elif wait_type == "title":
            if not value:
                return ExecutionResult(success=False, error_type="ValueError", error_message="wait_type=title 時必須提供 value")
            await page.wait_for_function(f'document.title.includes("{value}")', timeout=timeout)
            stdout = f"✅ 標題已包含: {value}"

        else:
            return ExecutionResult(success=False, error_type="ValueError", error_message=f"未知的 wait_type: {wait_type}")

        execution_time = (datetime.now() - start_time).total_seconds()

        return ExecutionResult(success=True, stdout=stdout, execution_time=f"{execution_time:.3f}s", metadata={"wait_type": wait_type, "current_url": page.url})
    except Exception as e:
        logger.exception(f"等待失敗: {e}")
        return ExecutionResult(success=False, error_type=type(e).__name__, error_message=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# Tool: web_scroll
# ═══════════════════════════════════════════════════════════════════════════════
@registry.register(
    name="web_scroll",
    description="滾動頁面。支援滾動到頂部、底部、特定元素或指定距離。",
    input_schema={
        "type": "object",
        "properties": {
            "scroll_type": {
                "type": "string",
                "enum": ["top", "bottom", "selector", "pixels"],
                "default": "bottom",
                "description": "滾動類型：top（頂部）、bottom（底部）、selector（特定元素）、pixels（指定像素）",
            },
            "selector": {"type": "string", "description": "CSS Selector（當 scroll_type=selector 時使用）"},
            "pixels": {"type": "integer", "description": "滾動像素數（當 scroll_type=pixels 時使用，正數向下，負數向上）"},
            "timeout": {"type": "integer", "default": 30000, "description": "等待元素超時時間（毫秒）"},
        },
        "required": [],
    },
)
async def handle_web_scroll(args: dict[str, Any]) -> ExecutionResult:
    """處理 web_scroll 請求"""
    scroll_type = args.get("scroll_type", "bottom")
    selector = args.get("selector", "")
    pixels = args.get("pixels", 0)
    timeout = args.get("timeout", DEFAULT_TIMEOUT)

    try:
        page = await browser_manager.get_page()
        start_time = datetime.now()
        stdout = ""

        if scroll_type == "top":
            await page.evaluate("window.scrollTo(0, 0)")
            stdout = "✅ 已滾動到頁面頂部"

        elif scroll_type == "bottom":
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            stdout = "✅ 已滾動到頁面底部"

        elif scroll_type == "selector":
            if not selector:
                return ExecutionResult(success=False, error_type="ValueError", error_message="scroll_type=selector 時必須提供 selector")
            element = await page.wait_for_selector(selector, timeout=timeout)
            if not element:
                return ExecutionResult(success=False, error_type="ElementNotFoundError", error_message=f"找不到元素: {selector}")
            await element.scroll_into_view_if_needed()
            stdout = f"✅ 已滾動到元素: {selector}"

        elif scroll_type == "pixels":
            await page.evaluate(f"window.scrollBy(0, {pixels})")
            direction = "向下" if pixels > 0 else "向上"
            stdout = f"✅ 已{direction}滾動 {abs(pixels)} 像素"

        else:
            return ExecutionResult(success=False, error_type="ValueError", error_message=f"未知的 scroll_type: {scroll_type}")

        # 等待一下讓頁面穩定
        await page.wait_for_timeout(500)

        execution_time = (datetime.now() - start_time).total_seconds()

        # 取得當前滾動位置
        scroll_pos = await page.evaluate("({ x: window.scrollX, y: window.scrollY })")

        return ExecutionResult(success=True, stdout=stdout, execution_time=f"{execution_time:.3f}s", metadata={"scroll_type": scroll_type, "scroll_position": scroll_pos})
    except Exception as e:
        logger.exception(f"滾動失敗: {e}")
        return ExecutionResult(success=False, error_type=type(e).__name__, error_message=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# Tool: web_get_url
# ═══════════════════════════════════════════════════════════════════════════════
@registry.register(name="web_get_url", description="取得當前頁面的 URL。", input_schema={"type": "object", "properties": {}, "required": []})
async def handle_web_get_url(args: dict[str, Any]) -> ExecutionResult:
    """處理 web_get_url 請求"""
    try:
        page = await browser_manager.get_page()

        # 支援遠端模式的 PageProxy
        if browser_manager.is_remote:
            url = await cast(Any, page).get_url()
        else:
            url = page.url

        return ExecutionResult(success=True, stdout=f"當前 URL: {url}", metadata={"url": url})
    except Exception as e:
        logger.exception(f"取得 URL 失敗: {e}")
        return ExecutionResult(success=False, error_type=type(e).__name__, error_message=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# Tool: web_get_title
# ═══════════════════════════════════════════════════════════════════════════════
@registry.register(name="web_get_title", description="取得當前頁面的標題。", input_schema={"type": "object", "properties": {}, "required": []})
async def handle_web_get_title(args: dict[str, Any]) -> ExecutionResult:
    """處理 web_get_title 請求"""
    try:
        page = await browser_manager.get_page()
        title = await page.title()

        return ExecutionResult(success=True, stdout=f"頁面標題: {title}", metadata={"title": title})
    except Exception as e:
        logger.exception(f"取得標題失敗: {e}")
        return ExecutionResult(success=False, error_type=type(e).__name__, error_message=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# Tool: web_get_status
# ═══════════════════════════════════════════════════════════════════════════════
@registry.register(name="web_get_status", description="取得當前瀏覽器連接狀態與頁面資訊。", input_schema={"type": "object", "properties": {}, "required": []})
async def handle_web_get_status(args: dict[str, Any]) -> ExecutionResult:
    """處理 web_get_status 請求"""
    try:
        page = await browser_manager.get_page()
        conn_info = browser_manager.connection_info
        is_remote = browser_manager.is_remote

        # 支援遠端模式
        if is_remote:
            url = await cast(Any, page).get_url()
            title = await page.title()
            viewport = await cast(Any, page).get_viewport_size()
        else:
            url = page.url
            title = await page.title()
            viewport = page.viewport_size

        # 構建狀態輸出
        stdout_parts = [
            "📊 瀏覽器狀態",
            f"連線模式: {'遠端 (Remote)' if is_remote else '本地 (Local CDP)'}",
        ]

        if is_remote:
            stdout_parts.append(f"Client ID: {conn_info.get('client_id', 'unknown')}")
            stdout_parts.append(f"連線時間: {conn_info.get('connected_at', 'unknown')}")
        else:
            stdout_parts.append(f"CDP Endpoint: {CDP_ENDPOINT}")

        stdout_parts.extend(
            [
                "連接狀態: ✅ 已連接",
                f"當前 URL: {url}",
                f"頁面標題: {title}",
            ]
        )

        if viewport:
            stdout_parts.append(f"Viewport: {viewport['width']}x{viewport['height']}")
        else:
            stdout_parts.append("Viewport: Unknown")

        metadata = {
            "connected": True,
            "mode": "remote" if is_remote else "local",
            **conn_info,
            "url": url,
            "title": title,
            "viewport": viewport,
        }

        return ExecutionResult(success=True, stdout="\n".join(stdout_parts), metadata=metadata)
    except Exception as e:
        logger.exception(f"取得狀態失敗: {e}")
        return ExecutionResult(success=False, error_type=type(e).__name__, error_message=str(e), metadata={"connected": False, "cdp_endpoint": CDP_ENDPOINT})


# ═══════════════════════════════════════════════════════════════════════════════
# Tool: web_get_cookies
# ═══════════════════════════════════════════════════════════════════════════════
@registry.register(
    name="web_get_cookies",
    description="取得當前頁面的所有 Cookies。",
    input_schema={
        "type": "object",
        "properties": {},
        "required": [],
    },
)
async def handle_web_get_cookies(args: dict[str, Any]) -> ExecutionResult:
    """處理 web_get_cookies 請求"""
    try:
        page = await browser_manager.get_page()
        start_time = datetime.now()

        # 支援遠端模式
        if browser_manager.is_remote:
            cookies = await cast(Any, page).get_cookies()
        else:
            context = page.context
            cookies = await context.cookies()

        execution_time = (datetime.now() - start_time).total_seconds()

        # 格式化輸出
        stdout_parts = [f"🍪 取得 {len(cookies)} 個 Cookies:"]
        for i, cookie in enumerate(cookies[:20]):  # 最多顯示 20 個
            name = cookie.get("name", "")
            domain = cookie.get("domain", "")
            stdout_parts.append(f"  {i + 1}. {name} ({domain})")

        if len(cookies) > 20:
            stdout_parts.append(f"  ... 還有 {len(cookies) - 20} 個")

        return ExecutionResult(
            success=True,
            stdout="\n".join(stdout_parts),
            execution_time=f"{execution_time:.3f}s",
            metadata={"cookies": cookies, "count": len(cookies)},
        )
    except Exception as e:
        logger.exception(f"取得 Cookies 失敗: {e}")
        return ExecutionResult(success=False, error_type=type(e).__name__, error_message=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# Tool: web_set_cookie
# ═══════════════════════════════════════════════════════════════════════════════
@registry.register(
    name="web_set_cookie",
    description="設定單一 Cookie。需提供 name 和 value，可選填 domain、path、expires 等。",
    input_schema={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Cookie 名稱"},
            "value": {"type": "string", "description": "Cookie 值"},
            "domain": {"type": "string", "description": "Cookie 所属網域（可選）"},
            "path": {"type": "string", "default": "/", "description": "Cookie 路路徑（預設 /）"},
            "expires": {"type": "integer", "description": "過期時間（Unix timestamp，可選）"},
            "http_only": {"type": "boolean", "default": False, "description": "是否為 HttpOnly"},
            "secure": {"type": "boolean", "default": False, "description": "是否僅 HTTPS 傳輸"},
            "same_site": {
                "type": "string",
                "enum": ["Strict", "Lax", "None"],
                "default": "Lax",
                "description": "SameSite 屬性",
            },
        },
        "required": ["name", "value"],
    },
)
async def handle_web_set_cookie(args: dict[str, Any]) -> ExecutionResult:
    """處理 web_set_cookie 請求"""
    name = args.get("name", "")
    value = args.get("value", "")

    if not name:
        return ExecutionResult(success=False, error_type="ValueError", error_message="name 不可為空")

    try:
        page = await browser_manager.get_page()
        start_time = datetime.now()

        # 構建 cookie 物件
        cookie: dict[str, Any] = {
            "name": name,
            "value": value,
        }

        # 可選參數
        if args.get("domain"):
            cookie["domain"] = args["domain"]
        if args.get("path"):
            cookie["path"] = args["path"]
        if args.get("expires"):
            cookie["expires"] = args["expires"]
        if args.get("http_only"):
            cookie["httpOnly"] = args["http_only"]
        if args.get("secure"):
            cookie["secure"] = args["secure"]
        if args.get("same_site"):
            cookie["sameSite"] = args["same_site"]

        # 設定 cookie
        if browser_manager.is_remote:
            await cast(Any, page).add_cookies([cookie])
        else:
            context = page.context
            await context.add_cookies(cast(Any, [cookie]))

        execution_time = (datetime.now() - start_time).total_seconds()

        return ExecutionResult(
            success=True,
            stdout=f"✅ 已設定 Cookie: {name}",
            execution_time=f"{execution_time:.3f}s",
            metadata={"cookie": cookie},
        )
    except Exception as e:
        logger.exception(f"設定 Cookie 失敗: {e}")
        return ExecutionResult(success=False, error_type=type(e).__name__, error_message=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# Tool: web_clear_cookies
# ═══════════════════════════════════════════════════════════════════════════════
@registry.register(
    name="web_clear_cookies",
    description="清除當前頁面的所有 Cookies。",
    input_schema={
        "type": "object",
        "properties": {},
        "required": [],
    },
)
async def handle_web_clear_cookies(args: dict[str, Any]) -> ExecutionResult:
    """處理 web_clear_cookies 請求"""
    try:
        page = await browser_manager.get_page()
        start_time = datetime.now()

        # 清除 cookies
        if browser_manager.is_remote:
            await cast(Any, page).clear_cookies()
        else:
            context = page.context
            await context.clear_cookies()

        execution_time = (datetime.now() - start_time).total_seconds()

        return ExecutionResult(
            success=True,
            stdout="✅ 已清除所有 Cookies",
            execution_time=f"{execution_time:.3f}s",
            metadata={},
        )
    except Exception as e:
        logger.exception(f"清除 Cookies 失敗: {e}")
        return ExecutionResult(success=False, error_type=type(e).__name__, error_message=str(e))
