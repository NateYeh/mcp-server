"""
安全與認證模組

處理 API Key 驗證與安全相關功能，支援多 Key 權限管理
"""
import fnmatch
import logging
from typing import Any

from fastapi import HTTPException, Request, status

from mcp_server.config import API_KEYS, GMAIL_ACCOUNTS

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
        list[str]: 允許的 tool 名稱列表，若為 ["*"] 表示所有 tools

    Raises:
        HTTPException: 驗證失敗時拋出 401 或 403
    """
    # 若無設定任何 API Key，則跳過認證（開發模式）
    if not API_KEYS:
        request.state.allowed_tools = ["*"]
        return ["*"]

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
        logger.warning(
            f"無效的 Authorization 格式: {client_host}, Header: {auth_header[:20]}..."
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization format. Expected 'Bearer <token>'",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = parts[1]

    # 檢查 token 是否存在於 API_KEYS 中
    if token not in API_KEYS:
        client_host = request.client.host if request.client else "unknown"
        logger.warning(f"無效的 API Key 嘗試: {client_host}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API Key",
        )

    # 取得該 API Key 允許的 tools 和排除的 tools
    allowed_tools: list[str] = API_KEYS[token].get("tools", [])
    excluded_tools: list[str] = API_KEYS[token].get("exclude_tools", [])
    request.state.allowed_tools = allowed_tools
    request.state.excluded_tools = excluded_tools
    request.state.api_key = token  # 儲存 API Key 供後續使用

    # logger.debug(f"API Key 驗證成功，允許 tools: {allowed_tools}, 排除 tools: {excluded_tools}")
    return allowed_tools


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
    return [
        tool for tool in all_tools
        if is_allowed(tool.get("name", "")) and not is_excluded(tool.get("name", ""))
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# Gmail 多帳號相關函數
# ═══════════════════════════════════════════════════════════════════════════════


def get_api_key_config(request: Request) -> dict[str, Any]:
    """
    從 Request 取得該 API Key 的完整配置

    Args:
        request: FastAPI Request 物件

    Returns:
        dict: API Key 配置，若無則回傳空 dict
    """
    # 從 request state 取得 API Key（由 verify_api_key 設定）
    api_key = getattr(request.state, "api_key", None)
    if not api_key:
        # 如果 request.state 沒有，嘗試從 Authorization header 解析
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            api_key = auth_header[7:]

    if not api_key:
        return {}

    return API_KEYS.get(api_key, {})


def get_gmail_account(request: Request) -> str | None:
    """
    從 Request 取得該 API Key 綁定的 Gmail 帳號 ID

    Args:
        request: FastAPI Request 物件

    Returns:
        str | None: Gmail 帳號 ID（email），若無綁定則回傳 None
    """
    config = get_api_key_config(request)
    return config.get("gmail_account")


def get_gmail_credentials(request: Request) -> dict[str, str] | None:
    """
    取得該 API Key 對應的 Gmail OAuth2 Credentials

    Args:
        request: FastAPI Request 物件

    Returns:
        dict | None: Gmail credentials，格式如下:
            {
                "client_id": "xxx",
                "client_secret": "xxx",
                "refresh_token": "xxx",
                "token_uri": "xxx"
            }
    """
    account_id = get_gmail_account(request)
    if not account_id:
        return None

    return GMAIL_ACCOUNTS.get(account_id)


def check_gmail_access(request: Request) -> tuple[str, dict[str, str]]:
    """
    檢查 Gmail 權限並取得帳號資訊

    Args:
        request: FastAPI Request 物件

    Returns:
        tuple: (account_id, credentials)

    Raises:
        ValueError: 無 Gmail 權限或設定不存在
    """
    account_id = get_gmail_account(request)
    if not account_id:
        raise ValueError("此 API Key 未綁定 Gmail 帳號，無法使用 Gmail 功能")

    credentials = get_gmail_credentials(request)
    if not credentials:
        raise ValueError(f"Gmail 帳號 '{account_id}' 設定不存在，請檢查 GMAIL_ACCOUNTS 環境變數")

    return account_id, credentials
