"""
安全與認證模組

處理 API Key 驗證（單一 AUTH_KEY 模式）與失敗次數限制
"""

import hmac
import logging
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from mcp_server.config import AUTH_KEY

logger = logging.getLogger(__name__)

# 失敗嘗試限制：同一來源於 _FAILURE_WINDOW 秒內失敗達 _MAX_FAILURES 次即暫時拒絕
_MAX_FAILURES = 10
_FAILURE_WINDOW = 60.0

# 來源 IP → 失敗時間戳（沉餘資料於記錄時一併清除）
_failures: dict[str, deque[float]] = defaultdict(deque)


def _prune(records: deque[float], now: float) -> None:
    """移除超出統計視窗的失敗紀錄"""
    while records and now - records[0] > _FAILURE_WINDOW:
        records.popleft()


def _register_failure(client_host: str) -> None:
    """記錄一次認證失敗"""
    now = time.monotonic()
    records = _failures[client_host]
    records.append(now)
    _prune(records, now)

    # 避免大量來源造成字典無限成長
    if len(_failures) > 10000:
        for key in [key for key, value in _failures.items() if not value]:
            del _failures[key]


def _is_rate_limited(client_host: str) -> bool:
    """判斷來源是否已達失敗次數上限"""
    records = _failures.get(client_host)
    if not records:
        return False
    _prune(records, time.monotonic())
    return len(records) >= _MAX_FAILURES


async def verify_api_key(request: Request) -> None:
    """
    驗證 Bearer Token 是否等於 AUTH_KEY

    認證失敗時拋出 HTTPException，成功則直接返回。

    Args:
        request: FastAPI Request 物件

    Raises:
        HTTPException: 驗證失敗時拋出 401（缺少或格式錯誤）、403（金鑰錯誤）
            或 429（同來源失敗次數過多）
    """
    client_host = request.client.host if request.client else "unknown"

    if _is_rate_limited(client_host):
        logger.warning(f"認證失敗次數過多，暫時拒絕: {client_host}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed authentication attempts",
            headers={"Retry-After": str(int(_FAILURE_WINDOW))},
        )

    auth_header = request.headers.get("Authorization")
    if not auth_header:
        _register_failure(client_host)
        logger.warning(f"Authorization Header 缺失: {client_host}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization Header. Expected format: 'Authorization: Bearer <token>'",
            headers={"WWW-Authenticate": "Bearer"},
        )

    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        _register_failure(client_host)
        # 僅記錄驗證方式，避免將金鑰片段寫入日誌
        scheme = parts[0][:20] if parts else ""
        logger.warning(f"無效的 Authorization 格式: {client_host}, scheme={scheme!r}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization format. Expected 'Bearer <token>'",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 常數時間比較，避免 timing attack
    if not hmac.compare_digest(parts[1], AUTH_KEY):
        _register_failure(client_host)
        logger.warning(f"無效的 API Key 嘗試: {client_host}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API Key",
        )
