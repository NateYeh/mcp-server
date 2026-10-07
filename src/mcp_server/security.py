"""
安全與認證模組

處理 API Key 驗證（單一 AUTH_KEY 模式）
"""

import hmac
import logging

from fastapi import HTTPException, Request, status

from mcp_server.config import AUTH_KEY

logger = logging.getLogger(__name__)


async def verify_api_key(request: Request) -> None:
    """
    驗證 Bearer Token 是否等於 AUTH_KEY

    認證失敗時拋出 HTTPException，成功則直接返回。

    Args:
        request: FastAPI Request 物件

    Raises:
        HTTPException: 驗證失敗時拋出 401（缺少或格式錯誤）或 403（金鑰錯誤）
    """
    client_host = request.client.host if request.client else "unknown"

    auth_header = request.headers.get("Authorization")
    if not auth_header:
        logger.warning(f"Authorization Header 缺失: {client_host}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization Header. Expected format: 'Authorization: Bearer <token>'",
            headers={"WWW-Authenticate": "Bearer"},
        )

    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        logger.warning(f"無效的 Authorization 格式: {client_host}, Header: {auth_header[:20]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization format. Expected 'Bearer <token>'",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 常數時間比較，避免 timing attack
    if not hmac.compare_digest(parts[1], AUTH_KEY):
        logger.warning(f"無效的 API Key 嘗試: {client_host}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API Key",
        )
