"""
MCP 協議資料模型定義

包含 MCPError 等 MCP 協議專用的資料結構
"""

from typing import Any


class MCPError(Exception):
    """MCP 協議專用的錯誤類型"""

    def __init__(self, code: int, message: str, data: dict[str, Any] | None = None):
        self.code = code
        self.message = message
        self.data = data
        super().__init__(message)
