"""
安全與認證模組

處理 API Key 驗證與安全相關功能（單一 AUTH_KEY 模式）
"""

import fnmatch
import hmac
import logging

from fastapi import HTTPException, Request, status

from mcp_server.config import AUTH_KEY

logger = logging.getLogger(__name__)

# 用於儲存 request state 的 key
STATE_ALLOWED_TOOLS = "allowed_tools"
STATE_EXCLUDED_TOOLS = "excluded_tools"


async def verify_api_key(request: Request) -> list[str]:
    """
    驗證 API Key 並回傳允許的 Tools 清單

    Args:
        request: FastAPI Request 物件

    Returns:
        list[str]: 允許的 tool 名稱列表，固定為 ["*"]（全部允許）

    Raises:
        HTTPException: 驗證失敗時拋出 401 或 403
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        client_host = request.client.host if request.client else "unknown"
        logger.warning(f"Authorization Header 缺失: {client_host}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization Header. Expected format: 'Authorization: Bearer <token>'",
            headers={"WWW-Authenticate": "Bearer"},
        )

    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        client_host = request.client.host if request.client else "unknown"
        logger.warning(f"無效的 Authorization 格式: {client_host}, Header: {auth_header[:20]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization format. Expected 'Bearer <token>'",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = parts[1]

    # 常數時間比較，避免 timing attack
    if not hmac.compare_digest(token, AUTH_KEY):
        client_host = request.client.host if request.client else "unknown"
        logger.warning(f"無效的 API Key 嘗試: {client_host}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API Key",
        )

    # 單一金錀模式：不區分工具權限
    request.state.allowed_tools = ["*"]
    request.state.excluded_tools = []
    request.state.api_key = token  # 儲存 API Key 供後續使用

    return ["*"]


def get_allowed_tools(request: Request) -> list[str]:
    """
    從 request state 取得允許的 tools 清單

    Args:
        request: FastAPI Request 物件

    Returns:
        list[str]: 允許的 tool 名稱列表
    """
    return getattr(request.state, STATE_ALLOWED_TOOLS, ["*"])


def get_excluded_tools(request: Request) -> list[str]:
    """
    從 request state 取得排除的 tools 清單

    Args:
        request: FastAPI Request 物件

    Returns:
        list[str]: 排除的 tool 名稱列表
    """
    return getattr(request.state, STATE_EXCLUDED_TOOLS, [])


def is_tool_allowed(request: Request, tool_name: str) -> bool:
    """
    檢查指定的 tool 是否被允許執行

    支援 wildcard 模式匹配：
    - ["*"] 表示所有 tools 都允許
    - ["web_*"] 表示所有 web_ 開頭的 tools 都允許
    - ["execute_*"] 表示所有 execute_ 開頭的 tools 都允許
    - 可混合使用 wildcard 和精確名稱

    支援 exclude_tools 排除清單（優先於允許清單）：
    - ["web_screenshot"] 排除特定 tool
    - ["web_*"] 排除所有 web_ 開頭的 tools

    Args:
        request: FastAPI Request 物件
        tool_name: Tool 名稱

    Returns:
        bool: 是否允許執行
    """
    excluded_tools = get_excluded_tools(request)

    # 先檢查是否在排除清單中（排除優先於允許）
    if excluded_tools and any(fnmatch.fnmatch(tool_name, pattern) for pattern in excluded_tools):
        return False

    allowed_tools = get_allowed_tools(request)

    # ["*"] 表示所有 tools 都允許
    if "*" in allowed_tools:
        return True

    # 支援 wildcard 模式匹配，例如 "web_*" 會匹配 "web_search", "web_fetch" 等
    return any(fnmatch.fnmatch(tool_name, pattern) for pattern in allowed_tools)


def filter_allowed_tools(request: Request, all_tools: list[dict]) -> list[dict]:
    """
    根據權限過濾 tools 清單

    支援 wildcard 模式匹配：
    - ["*"] 表示所有 tools 都允許
    - ["web_*"] 表示所有 web_ 開頭的 tools 都允許

    支援 exclude_tools 排除清單（優先於允許清單）

    Args:
        request: FastAPI Request 物件
        all_tools: 所有 tools 的清單，每個 tool 是一個 dict，包含 "name" 鍵

    Returns:
        list[dict]: 過濾後的 tools 清單
    """
    allowed_tools = get_allowed_tools(request)
    excluded_tools = get_excluded_tools(request)

    def is_excluded(tool_name: str) -> bool:
        """檢查 tool 是否在排除清單中"""
        return any(fnmatch.fnmatch(tool_name, pattern) for pattern in excluded_tools)

    def is_allowed(tool_name: str) -> bool:
        """檢查 tool 是否在允許清單中"""
        if "*" in allowed_tools:
            return True
        return any(fnmatch.fnmatch(tool_name, pattern) for pattern in allowed_tools)

    # 先過濾允許的 tools，再排除指定的 tools
    return [tool for tool in all_tools if is_allowed(tool.get("name", "")) and not is_excluded(tool.get("name", ""))]
