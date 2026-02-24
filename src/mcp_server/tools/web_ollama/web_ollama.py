"""
Web Ollama Tool

透過 Ollama Web API 進行網路搜尋與網頁抓取。
適用於簡單的網頁資訊獲取，無需瀏覽器自動化。
"""

import logging
import time
from typing import Any
from urllib.parse import urlparse

import requests

from mcp_server.config import (
    OLLAMA_API_KEY,
    OLLAMA_WEB_FETCH_URL,
    OLLAMA_WEB_SEARCH_URL,
    OLLAMA_WEB_TIMEOUT,
)
from mcp_server.schemas import ExecutionResult
from mcp_server.tools.base import registry

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Tool: web_search
# ═══════════════════════════════════════════════════════════════════════════════
@registry.register(
    name="web_search",
    description=("透過 Ollama Web Search API 進行網路搜尋。回傳搜尋結果列表，包含標題、URL 和內容摘要。"),
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜尋關鍵字"},
            "max_results": {"type": "integer", "default": 5, "description": "最大搜尋結果數量（預設 5，最大 10）"},
            "timeout": {"type": "integer", "default": 30, "description": "請求超時時間（秒），預設 30 秒"},
        },
        "required": ["query"],
    },
)
async def handle_web_search(args: dict[str, Any]) -> ExecutionResult:
    """
    處理 web_search 請求。

    透過 Ollama Web Search API 進行網路搜尋，回傳相關搜尋結果。

    Args:
        args: 包含以下參數的字典：
            - query: 搜尋關鍵字（必填）
            - max_results: 最大結果數（預設 5，最大 10）
            - timeout: 超時時間（預設 30 秒）

    Returns:
        ExecutionResult: 執行結果，包含搜尋結果列表
    """
    query = args.get("query", "")
    max_results = args.get("max_results", 5)
    timeout = args.get("timeout", OLLAMA_WEB_TIMEOUT)

    # 參數驗證
    if not query:
        return ExecutionResult(success=False, error_type="ValidationError", error_message="缺少必要參數：query")

    # 限制 max_results 範圍
    if max_results < 1:
        max_results = 1
    elif max_results > 10:
        max_results = 10

    # 檢查 API Key
    if not OLLAMA_API_KEY:
        return ExecutionResult(success=False, error_type="ConfigurationError", error_message="未設定 OLLAMA_API_KEY，無法使用 Web Search 功能")

    start_time = time.time()

    try:
        logger.info(f"開始 Web Search: query='{query}', max_results={max_results}")

        # 準備請求
        headers = {"Authorization": f"Bearer {OLLAMA_API_KEY}", "Content-Type": "application/json"}
        payload = {"query": query, "max_results": max_results}

        # 發送請求
        response = requests.post(OLLAMA_WEB_SEARCH_URL, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()

        # 解析回應
        data = response.json()
        results = data.get("results", [])

        if not results:
            return ExecutionResult(success=True, stdout="🔍 未找到相關搜尋結果", metadata={"query": query, "count": 0}, execution_time=f"{time.time() - start_time:.3f}s")

        # 格式化輸出
        stdout_parts = [f"🔍 搜尋結果：{query}", f"找到 {len(results)} 筆結果\n"]

        for i, result in enumerate(results, 1):
            title = result.get("title", "無標題")
            url = result.get("url", "")
            content = result.get("content", "")[:300]  # 限制摘要長度

            stdout_parts.append(f"{i}. {title}")
            stdout_parts.append(f"   URL: {url}")
            if content:
                stdout_parts.append(f"   摘要：{content}...")
            stdout_parts.append("")

        execution_time = time.time() - start_time

        return ExecutionResult(
            success=True, stdout="\n".join(stdout_parts), metadata={"query": query, "count": len(results), "results": results}, execution_time=f"{execution_time:.3f}s"
        )

    except requests.exceptions.Timeout:
        logger.exception(f"Web Search 超時：{timeout}秒")
        return ExecutionResult(success=False, error_type="TimeoutError", error_message=f"請求超時（{timeout}秒）")
    except requests.exceptions.RequestException as e:
        logger.exception(f"Web Search 請求失敗：{e}")
        return ExecutionResult(success=False, error_type="RequestError", error_message=f"網路請求失敗：{e}")
    except Exception as e:
        logger.exception(f"Web Search 發生意外錯誤：{e}")
        return ExecutionResult(success=False, error_type=type(e).__name__, error_message=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# Tool: web_fetch
# ═══════════════════════════════════════════════════════════════════════════════
@registry.register(
    name="web_fetch",
    description=("透過 Ollama Web Fetch API 抓取網頁內容。回傳頁面標題、主要內容和連結列表。"),
    input_schema={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "要抓取的網頁 URL"},
            "timeout": {"type": "integer", "default": 30, "description": "請求超時時間（秒），預設 30 秒"},
        },
        "required": ["url"],
    },
)
async def handle_web_fetch(args: dict[str, Any]) -> ExecutionResult:
    """
    處理 web_fetch 請求。

    透過 Ollama Web Fetch API 抓取網頁內容，回傳標題、內容和連結。

    Args:
        args: 包含以下參數的字典：
            - url: 要抓取的網頁 URL（必填）
            - timeout: 超時時間（預設 30 秒）

    Returns:
        ExecutionResult: 執行結果，包含網頁內容
    """
    url = args.get("url", "")
    timeout = args.get("timeout", OLLAMA_WEB_TIMEOUT)

    # 參數驗證
    if not url:
        return ExecutionResult(success=False, error_type="ValidationError", error_message="缺少必要參數：url")

    # URL 格式驗證
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return ExecutionResult(success=False, error_type="ValidationError", error_message=f"不支援的 URL 協議：{parsed.scheme}")
    except Exception as e:
        return ExecutionResult(success=False, error_type="ValidationError", error_message=f"URL 格式錯誤：{e}")

    # 檢查 API Key
    if not OLLAMA_API_KEY:
        return ExecutionResult(success=False, error_type="ConfigurationError", error_message="未設定 OLLAMA_API_KEY，無法使用 Web Fetch 功能")

    start_time = time.time()

    try:
        logger.info(f"開始 Web Fetch: url='{url}'")

        # 準備請求
        headers = {"Authorization": f"Bearer {OLLAMA_API_KEY}", "Content-Type": "application/json"}
        payload = {"url": url}

        # 發送請求
        response = requests.post(OLLAMA_WEB_FETCH_URL, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()

        # 解析回應
        data = response.json()
        title = data.get("title", "無標題")
        content = data.get("content", "")
        links = data.get("links", [])

        # 限制內容長度
        max_content_length = 5000
        content_display = content[:max_content_length]
        if len(content) > max_content_length:
            content_display += "\n...（內容已截斷）"

        # 格式化輸出
        stdout_parts = [f"🌐 網頁內容：{url}", f"標題：{title}", f"內容長度：{len(content)} 字元", f"連結數量：{len(links)}", "", "─" * 60, content_display]

        if links:
            stdout_parts.append("")
            stdout_parts.append("─" * 60)
            stdout_parts.append("頁面連結：")
            for i, link in enumerate(links[:20], 1):  # 最多顯示 20 個連結
                stdout_parts.append(f"  {i}. {link}")
            if len(links) > 20:
                stdout_parts.append(f"  ... 共 {len(links)} 個連結")

        execution_time = time.time() - start_time

        return ExecutionResult(
            success=True,
            stdout="\n".join(stdout_parts),
            metadata={"url": url, "title": title, "content": content, "links": links, "content_length": len(content)},
            execution_time=f"{execution_time:.3f}s",
        )

    except requests.exceptions.Timeout:
        logger.exception(f"Web Fetch 超時：{timeout}秒")
        return ExecutionResult(success=False, error_type="TimeoutError", error_message=f"請求超時（{timeout}秒）")
    except requests.exceptions.RequestException as e:
        logger.exception(f"Web Fetch 請求失敗：{e}")
        return ExecutionResult(success=False, error_type="RequestError", error_message=f"網路請求失敗：{e}")
    except Exception as e:
        logger.exception(f"Web Fetch 發生意外錯誤：{e}")
        return ExecutionResult(success=False, error_type=type(e).__name__, error_message=str(e))
