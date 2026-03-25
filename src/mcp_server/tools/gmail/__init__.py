"""
Gmail Tool

Gmail 郵件操作功能
"""

from mcp_server.tools.gmail.gmail import (
    handle_gmail_list,
    handle_gmail_read,
    handle_gmail_send,
    handle_gmail_modify,
    handle_gmail_search,
)

__all__ = [
    "handle_gmail_list",
    "handle_gmail_read",
    "handle_gmail_send",
    "handle_gmail_modify",
    "handle_gmail_search",
]