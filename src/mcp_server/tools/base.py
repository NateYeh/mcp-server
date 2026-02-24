"""
Tool Registry 基礎架構

提供 Tool 註冊與執行的核心機制
"""

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, ClassVar

from fastapi import Request

from mcp_server.schemas import ExecutionResult

ToolHandler = Callable[..., Awaitable[ExecutionResult]]


@dataclass
class ToolDefinition:
    """Tool 定義，包含 schema 與 handler"""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: ToolHandler


class ToolRegistry:
    """
    Tool 註冊表：集中管理所有 MCP Tools

    使用單例模式，確保全域只有一個 registry
    """

    _instance: ClassVar["ToolRegistry | None"] = None

    # 明確宣告實例屬性，解決 Pylance 的靜態分析警告
    _tools: dict[str, ToolDefinition]

    def __new__(cls) -> "ToolRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tools = {}
        return cls._instance

    def register(self, name: str, description: str, input_schema: dict[str, Any]) -> Callable[[ToolHandler], ToolHandler]:
        """
        Decorator 用於註冊 Tool

        使用方式:
            @registry.register(
                name="execute_python",
                description="執行 Python 代碼",
                input_schema={...}
            )
            async def handle_python(args: dict) -> ExecutionResult:
                ...
        """

        def decorator(handler: ToolHandler) -> ToolHandler:
            self._tools[name] = ToolDefinition(name=name, description=description, input_schema=input_schema, handler=handler)
            return handler

        return decorator

    def list_tools(self) -> list[dict[str, Any]]:
        """列出所有 Tool 的 schema"""
        return [{"name": t.name, "description": t.description, "inputSchema": t.input_schema} for t in self._tools.values()]

    async def execute(self, name: str, args: dict[str, Any], request: Request | None = None) -> ExecutionResult:
        """
        執行指定的 Tool

        Args:
            name: Tool 名稱
            args: Tool 參數
            request: FastAPI Request（用於權限檢查、多帳號等）

        Returns:
            ExecutionResult: 執行結果

        Raises:
            MCPError: Tool 不存在
        """
        from mcp_server.schemas import MCPError

        tool = self._tools.get(name)
        if not tool:
            raise MCPError(-32601, f"Tool not found: {name}")

        # 檢查 handler 是否需要 request 參數
        sig = inspect.signature(tool.handler)
        params = list(sig.parameters.keys())

        if "request" in params and request is not None:
            return await tool.handler(args, request=request)
        else:
            return await tool.handler(args)

    def get_tool_count(self) -> int:
        """取得已註冊的工具數量"""
        return len(self._tools)


# 全域註冊表（單例）
# 所有 Tool 模組都會共用這個 registry
registry = ToolRegistry()
