"""
Tools 模組入口

集中管理所有 MCP Tools，自動載入並註冊到 Registry
"""

import logging

from mcp_server.tools.base import ToolDefinition, ToolHandler, ToolRegistry, registry

# 自動載入所有 Tool 模組（副作用：自動註冊到 registry）
from mcp_server.tools.execute_mysql import execute_mysql  # noqa: F401
from mcp_server.tools.execute_python import execute_python  # noqa: F401
from mcp_server.tools.execute_shell import execute_shell  # noqa: F401
from mcp_server.tools.get_python_version import get_python_version  # noqa: F401
from mcp_server.tools.gmail import gmail  # noqa: F401
from mcp_server.tools.image_recognition import image_recognition  # noqa: F401
from mcp_server.tools.install_package import install_package  # noqa: F401
from mcp_server.tools.read_file import read_file  # noqa: F401
from mcp_server.tools.replace_block import replace_block  # noqa: F401
from mcp_server.tools.replace_lines import replace_lines  # noqa: F401
from mcp_server.tools.tmdb_search import tmdb_search  # noqa: F401
from mcp_server.tools.web_ollama import web_ollama  # noqa: F401
from mcp_server.tools.web_playwright import web_playwright  # noqa: F401
from mcp_server.tools.sqlite_query import sqlite_query  # noqa: F401
from mcp_server.tools.write_file import write_file  # noqa: F401

logger = logging.getLogger(__name__)
logger.info(f"🧰 已載入 {registry.get_tool_count()} 個 Tool 模組")

__all__ = [
    "registry",
    "ToolRegistry",
    "ToolDefinition",
    "ToolHandler",
]
