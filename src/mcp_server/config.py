"""
環境設定與常數

集中管理所有配置項，從環境變數載入。
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

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
    logger.info(f"📁 已載入環境設定檔: {ENV_PATH}")

# 將專案根目錄加入 sys.path，以便載入 natekit 等模組
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
    logger.info(f"📁 已將專案根目錄加入 sys.path: {PROJECT_ROOT}")

# ═══════════════════════════════════════════════════════════════════════════════
# 認證設定 - 多 API Key 權限管理
# ═══════════════════════════════════════════════════════════════════════════════
# API_KEYS 結構:
# {
#     "api_key": {
#         "tools": ["*"] 或 ["tool1", "tool2", ...],  # 允許的 tools
#         "gmail_account": "email@gmail.com"          # 綁定的 Gmail 帳號（可選）
#     }
# }
# ["*"] 表示允許所有 tools
# gmail_account 綁定後，該 API Key 只能使用綁定的 Gmail 帳號
#
# 設定方式：請在 .env 中設定 MCP_API_KEYS (Base64 編碼的 JSON 陣列)


class APIKeyManager:
    """API Keys 管理類別"""

    @staticmethod
    def _load_json_env(key: str, default: Any = None) -> Any:
        """從環境變數載入 JSON 格式的值"""
        import base64

        value = os.getenv(key, "")
        if not value:
            return default
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            try:
                return json.loads(base64.b64decode(value).decode("utf-8"))
            except Exception:
                return default

    @classmethod
    def get_api_keys(cls) -> dict[str, dict]:
        """取得 MCP API Keys"""
        raw = cls._load_json_env("MCP_API_KEYS", [])
        if not raw:
            return {}
        return {item["api_key"]: {k: v for k, v in item.items() if k != "api_key"} for item in raw}

    @classmethod
    def get_gemini_keys(cls) -> list[dict]:
        """取得 Gemini API Keys"""
        return cls._load_json_env("GEMINI_API_KEYS", [])

    @classmethod
    def get_deepseek_key(cls) -> str:
        """取得 DeepSeek API Key"""
        return os.getenv("DEEPSEEK_API_KEY", "")

    @classmethod
    def get_ollama_key(cls) -> str:
        """取得 Ollama API Key"""
        return os.getenv("OLLAMA_API_KEY", "")


# ═══════════════════════════════════════════════════════════════════════════════
# 認證設定
# ═══════════════════════════════════════════════════════════════════════════════
API_KEYS = APIKeyManager.get_api_keys()

if API_KEYS:
    logger.info(f"🔐 API Key 認證已啟用，已設定 {len(API_KEYS)} 組 Key")
else:
    logger.warning("⚠️ 未設定 API_KEYS，API Key 認證已停用（開發模式）")

# ═══════════════════════════════════════════════════════════════════════════════
# 路徑設定
# ═══════════════════════════════════════════════════════════════════════════════
WORK_DIR = Path(os.getenv("PYTHON_WORK_DIR", str(PROJECT_ROOT / "python_workspace")))
WORK_DIR.mkdir(parents=True, exist_ok=True)

# Shell 預設執行目錄
DEFAULT_SHELL_CWD = Path(os.getenv("MCP_SHELL_CWD", "."))


def cleanup_work_directory() -> None:
    """清理工作目錄中的所有檔案"""
    import shutil

    WORK_DIR.mkdir(parents=True, exist_ok=True)

    if WORK_DIR.exists():
        cleaned_count = 0
        for item in WORK_DIR.iterdir():
            try:
                if item.is_file():
                    item.unlink()
                    cleaned_count += 1
                elif item.is_dir():
                    shutil.rmtree(item)
                    cleaned_count += 1
            except Exception as e:
                logger.warning(f"無法清理 {item}: {e}")
        if cleaned_count > 0:
            logger.info(f"🧹 已清理工作目錄: 移除 {cleaned_count} 個項目")


# ═══════════════════════════════════════════════════════════════════════════════
# 伺服器設定
# ═══════════════════════════════════════════════════════════════════════════════
MCP_HOST = os.getenv("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.getenv("MCP_PORT", "8000"))

# ═══════════════════════════════════════════════════════════════════════════════
# 執行限制
# ═══════════════════════════════════════════════════════════════════════════════
MAX_EXECUTION_TIME = int(os.getenv("MCP_EXEC_TIMEOUT", "300"))
MAX_INPUT_LENGTH = int(os.getenv("MCP_MAX_INPUT", "1000000"))
MAX_OUTPUT_LENGTH = int(os.getenv("MCP_MAX_OUTPUT", "1000000"))

# ═══════════════════════════════════════════════════════════════════════════════
# 安全設定
# ═══════════════════════════════════════════════════════════════════════════════
DANGEROUS_SHELL_PATTERNS: list[str] = []
DANGEROUS_PACKAGE_CHARS = [";", "|", "&", "$", "`", "||", "&&", "<", ">"]

# ═══════════════════════════════════════════════════════════════════════════════
# TMDB 設定
# ═══════════════════════════════════════════════════════════════════════════════
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")
if TMDB_API_KEY:
    logger.info("🎬 TMDB API Key 已載入")
else:
    logger.warning("⚠️ 未設定 TMDB_API_KEY，TMDB 搜尋功能將無法使用")

# ═══════════════════════════════════════════════════════════════════════════════
# MySQL 設定
# ═══════════════════════════════════════════════════════════════════════════════
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "")
MYSQL_MAX_ROWS = int(os.getenv("MYSQL_MAX_ROWS", "10000"))

if MYSQL_USER and MYSQL_PASSWORD:
    logger.info(f"🗄️ MySQL 連線設定已載入: {MYSQL_USER}@{MYSQL_HOST}:{MYSQL_PORT}")
else:
    logger.warning("⚠️ 未完整設定 MySQL 連線資訊，MySQL 執行功能可能無法使用")

# MySQL 安全設定 - 危險 SQL 指令黑名單
# 這些模式會被攔截，防止危險操作
DANGEROUS_SQL_PATTERNS = [
    "DROP DATABASE",
    "DROP SCHEMA",
    "TRUNCATE",  # 禁止 TRUNCATE（清空資料表）
    "LOAD_FILE",  # 禁止讀取伺服器檔案
    "INTO OUTFILE",  # 禁止寫入檔案
    "INTO DUMPFILE",  # 禁止寫入二進制檔案
    "-- ",  # SQL 註解攻擊（注意前後要有空格）
    "/*",  # 多行註解攻擊
    "*/",
    "EXEC ",  # 預存程序執行
    "EXECUTE ",
    "xp_",  # SQL Server 擴展預存程序（防禦性加入）
    "sp_",  # 預存程序前綴
    "information_schema",  # 禁止存取系統資訊表
    "mysql.user",  # 禁止存取使用者表
    "sys.",  # 系統資料庫
]

# ═══════════════════════════════════════════════════════════════════════════════
# Gmail 多帳號設定
# ═══════════════════════════════════════════════════════════════════════════════


def load_gmail_accounts() -> dict[str, dict[str, str]]:
    """
    從環境變數 GMAIL_ACCOUNTS 載入 Gmail 帳號設定

    環境變數格式 (JSON):
        GMAIL_ACCOUNTS={"alice@gmail.com":{"client_id":"xxx","client_secret":"xxx","refresh_token":"xxx"},"bob@gmail.com":{...}}

    Returns:
        dict: Gmail 帳號配置，key 為 email，value 包含 client_id, client_secret, refresh_token
    """
    raw = os.getenv("GMAIL_ACCOUNTS", "")
    if not raw:
        logger.debug("未設定 GMAIL_ACCOUNTS 環境變數")
        return {}

    try:
        accounts = json.loads(raw)
        if not isinstance(accounts, dict):
            logger.warning("GMAIL_ACCOUNTS 格式錯誤：必須是 JSON 物件")
            return {}

        # 為每個帳號加入預設的 token_uri
        default_token_uri = "https://oauth2.googleapis.com/token"
        for _account_id, creds in accounts.items():
            if "token_uri" not in creds:
                creds["token_uri"] = default_token_uri

        if accounts:
            logger.info(f"📧 已載入 {len(accounts)} 個 Gmail 帳號設定")
        return accounts
    except json.JSONDecodeError:
        logger.exception("GMAIL_ACCOUNTS JSON 解析失敗")
        return {}
    except Exception:
        logger.exception("載入 Gmail 帳號設定失敗")
        return {}


# Gmail 帳號配置（全域）
GMAIL_ACCOUNTS: dict[str, dict[str, str]] = load_gmail_accounts()

# ═══════════════════════════════════════════════════════════════════════════════
# Playwright Web Browser 設定
# ═══════════════════════════════════════════════════════════════════════════════
PLAYWRIGHT_CDP_ENDPOINT = os.getenv("PLAYWRIGHT_CDP_ENDPOINT", "http://127.0.0.1:9222")
PLAYWRIGHT_DEFAULT_TIMEOUT = int(os.getenv("PLAYWRIGHT_DEFAULT_TIMEOUT", "30000"))  # 30 秒

if PLAYWRIGHT_CDP_ENDPOINT:
    logger.info(f"🌐 Playwright CDP Endpoint: {PLAYWRIGHT_CDP_ENDPOINT}")

# ═══════════════════════════════════════════════════════════════════════════════
# 遠端瀏覽器設定（WebSocket 反向連線）
# ═══════════════════════════════════════════════════════════════════════════════
REMOTE_BROWSER_ENABLED = os.getenv("REMOTE_BROWSER_ENABLED", "true").lower() == "true"
REMOTE_BROWSER_PORT = int(os.getenv("REMOTE_BROWSER_PORT", "8001"))
REMOTE_BROWSER_TOKEN = os.getenv("REMOTE_BROWSER_TOKEN", "")  # 認證 Token

if REMOTE_BROWSER_ENABLED:
    logger.info(f"🔗 遠端瀏覽器功能已啟用，WebSocket Port: {REMOTE_BROWSER_PORT}")
    if not REMOTE_BROWSER_TOKEN:
        logger.warning("⚠️ 未設定 REMOTE_BROWSER_TOKEN，建議設定以提高安全性")

# ═══════════════════════════════════════════════════════════════════════════════
# Ollama Web API 設定
# ═══════════════════════════════════════════════════════════════════════════════
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")
OLLAMA_WEB_SEARCH_URL = os.getenv("OLLAMA_WEB_SEARCH_URL", "")
OLLAMA_WEB_FETCH_URL = os.getenv("OLLAMA_WEB_FETCH_URL", "")
OLLAMA_WEB_TIMEOUT = int(os.getenv("OLLAMA_WEB_TIMEOUT", "30"))

if OLLAMA_API_KEY:
    logger.info("🔍 Ollama Web API Key 已載入")
else:
    logger.warning("⚠️ 未設定 OLLAMA_API_KEY，Ollama Web API 功能將無法使用")

# ═══════════════════════════════════════════════════════════════════════════════
# Gemini API 設定
# ═══════════════════════════════════════════════════════════════════════════════
GEMINI_API_KEYS = APIKeyManager.get_gemini_keys()
GEMINI_PAY_KEY = os.getenv("GEMINI_PAY_KEY", "")
GEMINI_API_BASE_URL = os.getenv("GEMINI_API_BASE_URL", "https://generativelanguage.googleapis.com")
GEMINI_PROXY_URL = os.getenv("GEMINI_PROXY_URL", "")
OLLAMA_PROXY_URL = os.getenv("OLLAMA_PROXY_URL", "")
GEMINI_API_VERSION = "v1beta"

GEMINI_MODEL_LIST = [
    "models/gemini-3-flash-preview",
    "models/gemini-3-pro-preview",
    "models/gemini-2.5-flash-lite",
    "models/gemini-2.5-flash",
    "models/gemini-2.5-pro",
    "models/gemini-2.5-pro-preview-03-25",
    "models/gemini-2.5-flash-image-preview",
]

GEMINI_SAFETY_SETTINGS = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]
