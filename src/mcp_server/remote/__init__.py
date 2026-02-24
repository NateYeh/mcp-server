"""
遠端瀏覽器連線模組

提供 WebSocket Server 讓遠端 Browser Agent 連接，
並透過 PageProxy 介面操作遠端瀏覽器。
"""

from mcp_server.remote.connection_manager import RemoteConnectionManager
from mcp_server.remote.page_proxy import PageProxy

__all__ = ["RemoteConnectionManager", "PageProxy"]
