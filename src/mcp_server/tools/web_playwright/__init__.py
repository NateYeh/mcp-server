"""
Web Playwright Tool

Playwright 瀏覽器自動化功能
"""

from mcp_server.tools.web_playwright.web_playwright import (
    handle_web_navigate,
    handle_web_screenshot,
    handle_web_extract,
    handle_web_click,
    handle_web_fill,
)

__all__ = [
    "handle_web_navigate",
    "handle_web_screenshot",
    "handle_web_extract",
    "handle_web_click",
    "handle_web_fill",
]