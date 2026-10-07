"""
環境設定與常數

集中管理所有配置項，從環境變數載入。
"""

import logging
import os
import secrets
import shutil
import sys
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

# 將專案根目錄加入 sys.path，以便載入 natekit 等模組
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

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
MCP_HOST = os.getenv("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.getenv("MCP_PORT", "8000"))

# ═══════════════════════════════════════════════════════════════════════════════
# 路徑設定
# ═══════════════════════════════════════════════════════════════════════════════
# 修正工作目錄路徑，避免巢狀目錄問題
_raw_work_dir = os.getenv("PYTHON_WORK_DIR", "workspace")
WORK_DIR = (PROJECT_ROOT / _raw_work_dir[2:]).resolve() if _raw_work_dir.startswith("./") else Path(_raw_work_dir).resolve()

WORK_DIR.mkdir(parents=True, exist_ok=True)

# Shell 預設執行目錄
DEFAULT_SHELL_CWD = Path(os.getenv("MCP_SHELL_CWD", "."))


def cleanup_work_directory() -> None:
    """清理工作目錄中的所有檔案"""
    WORK_DIR.mkdir(parents=True, exist_ok=True)

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
MAX_EXECUTION_TIME = int(os.getenv("MCP_EXEC_TIMEOUT", "300"))
MAX_INPUT_LENGTH = int(os.getenv("MCP_MAX_INPUT", "1000000"))
MAX_OUTPUT_LENGTH = int(os.getenv("MCP_MAX_OUTPUT", "1000000"))

# ═══════════════════════════════════════════════════════════════════════════════
# 安全設定
# ═══════════════════════════════════════════════════════════════════════════════
# Shell 危險指令黑名單（命中即拒絕執行）
DANGEROUS_SHELL_PATTERNS: list[str] = []
