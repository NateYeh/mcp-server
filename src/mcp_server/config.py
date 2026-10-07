"""
環境設定與常數

集中管理所有配置項，從環境變數載入。

路徑類設定（PYTHON_WORK_DIR、MCP_SHELL_CWD）的相對路徑一律以**專案根目錄**為基準，
避免受服務啟動時的工作目錄（CWD）影響而產生非預期的位置。
"""

import logging
import os
import secrets
import shutil
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# 基本設定
# ═══════════════════════════════════════════════════════════════════════════════
# 專案根目錄
PROJECT_ROOT = Path(__file__).parent.parent.parent

# 載入 .env 檔案
ENV_PATH = PROJECT_ROOT / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)


def _env_int(name: str, default: int, minimum: int, maximum: int | None = None) -> int:
    """
    讀取整數型環境變數並夾制於允許範圍

    設定值不合法時記錄日誌並退回預設值，避免服務在 import 期直接崩潰。

    Args:
        name: 環境變數名稱
        default: 未設定或無法解析時採用的預設值
        minimum: 允許的最小值
        maximum: 允許的最大值（None 表示不設上限）

    Returns:
        int: 合法的設定值
    """
    raw = os.getenv(name, "")
    if not raw.strip():
        return default

    try:
        value = int(raw.strip())
    except ValueError:
        logger.error(f"環境變數 {name}={raw!r} 不是合法整數，改用預設值 {default}")
        return default

    if value < minimum:
        logger.warning(f"環境變數 {name}={value} 低於下限 {minimum}，已調整為 {minimum}")
        return minimum
    if maximum is not None and value > maximum:
        logger.warning(f"環境變數 {name}={value} 超過上限 {maximum}，已調整為 {maximum}")
        return maximum
    return value


def _resolve_path(raw: str) -> Path:
    """
    將設定值解析為絕對路徑（相對路徑以專案根目錄為基準）

    Args:
        raw: 環境變數的原始字串值

    Returns:
        Path: 絕對路徑
    """
    path = Path(raw.strip() or ".").expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


# ═══════════════════════════════════════════════════════════════════════════════
# 認證設定 - 單一 AUTH_KEY
# ═══════════════════════════════════════════════════════════════════════════════
# 認證金鑰來源為環境變數 AUTH_KEY；未設定時於每次啟動隨機產生（僅存在於記憶體，
# 重啟後會變更）。金鑰由 __main__.py 於服務啟動時顯示。

AUTH_KEY = os.getenv("AUTH_KEY", "").strip()
AUTH_KEY_GENERATED = not AUTH_KEY

if AUTH_KEY_GENERATED:
    AUTH_KEY = secrets.token_urlsafe(32)

# ═══════════════════════════════════════════════════════════════════════════════
# 伺服器設定
# ═══════════════════════════════════════════════════════════════════════════════
MCP_HOST = os.getenv("MCP_HOST", "").strip() or "0.0.0.0"
MCP_PORT = _env_int("MCP_PORT", 8000, minimum=1, maximum=65535)

# ═══════════════════════════════════════════════════════════════════════════════
# 路徑設定
# ═══════════════════════════════════════════════════════════════════════════════
# 工作目錄（服務啟動時清空）
WORK_DIR = _resolve_path(os.getenv("PYTHON_WORK_DIR", "workspace"))

# Shell 預設執行目錄
DEFAULT_SHELL_CWD = _resolve_path(os.getenv("MCP_SHELL_CWD", "."))


def cleanup_work_directory() -> None:
    """
    建立並清空工作目錄

    Raises:
        OSError: 工作目錄無法建立時向上拋出，避免服務在無工作目錄的狀態下繼續運作
    """
    try:
        WORK_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        logger.exception(f"無法建立工作目錄: {WORK_DIR}")
        raise

    cleaned_count = 0
    for item in WORK_DIR.iterdir():
        try:
            if item.is_file():
                item.unlink()
                cleaned_count += 1
            elif item.is_dir():
                shutil.rmtree(item)
                cleaned_count += 1
        except OSError:
            logger.exception(f"無法清理 {item}")
    if cleaned_count > 0:
        logger.info(f"🧹 已清理工作目錄: 移除 {cleaned_count} 個項目")


# ═══════════════════════════════════════════════════════════════════════════════
# 執行限制
# ═══════════════════════════════════════════════════════════════════════════════
# 逾時上限固定為 300 秒，避免環境變數設定過大導致失控
MAX_TIMEOUT_LIMIT = 300
MAX_EXECUTION_TIME = _env_int("MCP_EXEC_TIMEOUT", 300, minimum=1, maximum=MAX_TIMEOUT_LIMIT)
MAX_INPUT_LENGTH = _env_int("MCP_MAX_INPUT", 1000000, minimum=1)
MAX_OUTPUT_LENGTH = _env_int("MCP_MAX_OUTPUT", 1000000, minimum=1)
