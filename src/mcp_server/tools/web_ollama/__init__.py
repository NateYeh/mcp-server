"""
Web Ollama Tool

Ollama Web Search 和 Web Fetch 功能
"""

from mcp_server.tools.web_ollama.web_ollama import (
    handle_web_search,
    handle_web_fetch,
)

__all__ = ["handle_web_search", "handle_web_fetch"]