# NATE-MCP-SERVER v4.0.0 | AI 開發指引

> **用途**: 讓 LLM 快速理解專案架構，無需閱讀所有原始碼。

---

## 1. 專案定位

**MCP (Model Context Protocol) 伺服器**，提供安全的程式碼執行與系統操作能力。

| 類別 | 功能 |
|------|------|
| 程式執行 | Python、Shell、MySQL |
| 系統資訊 | Python 版本查詢 |
| 套件管理 | pip 安裝 |
| 檔案操作 | 讀取檔案、寫入檔案、行替換、區塊替換（內容簽名） |
| 網頁操作 | Playwright CDP、遠端瀏覽器、Ollama Web API |
| 外部整合 | TMDB、Gmail、圖片辨識 |

---

## 2. 架構總覽

```
mcp_server/
├── pyproject.toml          # 專案設定（Python 3.10+、依賴）
├── .env                    # 環境變數設定
├── README.md               # 本文件（AI 開發指引）
├── workspace/              # Python 臨時執行目錄（自動清理）
├── logs/                   # 日誌目錄
└── src/mcp_server/         # 主要程式碼目錄（src-layout）
    ├── __init__.py
    ├── __main__.py         # 啟動入口：python -m mcp_server
    ├── app.py              # FastAPI + MCP 協議路由
    ├── config.py           # 環境設定、API Keys、安全常數
    ├── schemas.py          # ExecutionResult、MCPError 資料模型
    ├── security.py         # Bearer Token 認證、權限檢查
    ├── utils.py            # format_tool_result() 格式化輸出
    ├── api/                # API 相關模組
    ├── base/               # 基礎模組
    │   ├── data_structures.py
    │   └── logging_config.py
    ├── model/              # AI 模型整合
    │   └── gemini_api_client.py
    ├── services/           # 服務層
    │   └── gmail_service.py
    ├── tools/              # Tool 模組（Registry 模式）
    │   ├── base.py         # ToolRegistry 單例 + @registry.register
    │   ├── __init__.py     # 自動載入所有 Tools
    │   ├── execute_python/
    │   ├── execute_shell/
    │   └── ...             # 其他 Tool 子目錄
    └── web/                # Web 相關模組
```

### 核心設計模式

| 模式 | 實作 |
|------|------|
| **Registry 模式** | `tools/base.py` - 單例註冊表，Decorator 自動註冊 |
| **權限分級** | `config.API_KEYS` - 每個 Key 綁定允許的 Tools |
| **統一輸出** | `ExecutionResult.to_text_output()` - 人類可讀格式 |

---

## 3. Tool 清單 (16+ 個)

| Tool | 檔案 | 關鍵參數 |
|------|------|----------|
| `execute_python` | `execute_python/execute_python.py` | `code`, `timeout` |
| `execute_shell` | `execute_shell/execute_shell.py` | `command`, `timeout` |
| `execute_mysql` | `execute_mysql/execute_mysql.py` | `sql`, `database` |
| `install_package` | `install_package/install_package.py` | `package` |
| `get_python_version` | `get_python_version/get_python_version.py` | - |
| `read_file` | `read_file/read_file.py` | `file_path`, `start_line`, `end_line`, `show_line_numbers`, `max_lines`, `encoding` |
| `write_file` | `write_file/write_file.py` | `file_path`, `content`, `mode`, `encoding`, `create_dirs`, `backup` |
| `replace_lines` | `replace_lines/replace_lines.py` | `file_path`, `start_line`, `end_line`, `new_content`, `dry_run`, `validate_syntax` |
| `replace_block` | `replace_block/replace_block.py` | `file_path`, `replace_with`, (`find_content` \| `find_signature`)*, `occurrence`, `dry_run`, `validate_syntax` |

*註: `find_content` 和 `find_signature` 必須提供其中一個，不可同時使用 |
| `search_tmdb` | `tmdb_search/tmdb_search.py` | `title`, `year`, `media_type`, `language` |
| `image_recognition` | `image_recognition/image_recognition.py` | `image_url`, `prompt` |
| `web_search` | `web_ollama/web_ollama.py` | `query` |
| `web_fetch` | `web_ollama/web_ollama.py` | `url` |
| `web_navigate` | `web_playwright/web_playwright.py` | `url` |
| `web_screenshot` | `web_playwright/web_playwright.py` | `full_page` |
| `web_extract` | `web_playwright/web_playwright.py` | `selector`, `extract_type` |
| `web_click/fill/evaluate/wait/scroll` | `web_playwright/web_playwright.py` | 對應操作參數 |
| `gmail_*` | `gmail/gmail.py` | 多種郵件操作 |

---

## 4. 新增 Tool 的標準流程

```python
# src/mcp_server/tools/my_tool/my_tool.py
from mcp_server.schemas import ExecutionResult
from mcp_server.tools.base import registry

@registry.register(
    name="my_tool",
    description="功能描述",
    input_schema={
        "type": "object",
        "properties": {
            "param": {"type": "string", "description": "參數說明"}
        },
        "required": ["param"]
    }
)
async def handle_my_tool(args: dict) -> ExecutionResult:
    """處理邏輯"""
    param = args.get("param")
    # ... 實作
    return ExecutionResult(success=True, stdout="結果")
```

**注意**: 
1. 在 `src/mcp_server/tools/my_tool/__init__.py` 加入 `from .my_tool import *`
2. 在 `src/mcp_server/tools/__init__.py` 加入 `from mcp_server.tools.my_tool import *`

---

## 5. 安全機制

### 5.1 API Key 權限 (`config.API_KEYS`)

```python
API_KEYS = {
    "sk-xxx": {"tools": ["*"]},           # 全部權限
    "sk-yyy": {"tools": ["execute_python", "replace_block"]},  # 僅特定 tools
    "sk-zzz": {"tools": ["web_*"]},       # wildcard: 所有 web_ 開頭的 tools
    "sk-aaa": {"tools": ["web_*", "read_file", "write_file"]},  # 混合使用
    "sk-bbb": {"tools": ["web_*"], "exclude_tools": ["web_screenshot"]},  # 排除特定 tool
    "sk-ccc": {"tools": ["*"], "exclude_tools": ["web_*", "execute_mysql"]}  # 全部權限但排除
}
```

**Wildcard 模式支援**:
| 設定 | 效果 |
|------|------|
| `["*"]` | 開放所有 tools |
| `["web_*"]` | 開放所有 `web_` 開頭的 tools (web_search, web_fetch, web_navigate 等) |
| `["execute_*"]` | 開放所有 `execute_` 開頭的 tools |
| `["gmail_*"]` | 開放所有 `gmail_` 開頭的 tools |

**exclude_tools 排除清單**（優先於 `tools` 允許清單）:
| 設定 | 效果 |
|------|------|
| `"exclude_tools": ["web_screenshot"]` | 排除特定 tool |
| `"exclude_tools": ["web_*"]` | 排除所有 `web_` 開頭的 tools |
| `"exclude_tools": ["web_*", "execute_mysql", "gmail_*"]` | 排除多個 tools（混合 wildcard） |

### 5.2 危險指令攔截

| 類型 | 黑名單位置 |
|------|-----------|
| Shell | `config.DANGEROUS_SHELL_PATTERNS` |
| SQL | `config.DANGEROUS_SQL_PATTERNS` |
| 套件名稱 | `config.DANGEROUS_PACKAGE_CHARS` |

### 5.3 執行限制

- 超時: `MAX_EXECUTION_TIME` (預設 300s)
- 輸入長度: `MAX_INPUT_LENGTH` (預設 1MB)
- 輸出長度: `MAX_OUTPUT_LENGTH` (預設 1MB)

---

## 6. 關鍵資料流

```
Client Request
    ↓
POST /mcp → verify_api_key() → 檢查 tool 權限
    ↓
_handle_tools_call() → registry.execute(tool_name, args)
    ↓
Tool Handler → 執行邏輯 → ExecutionResult
    ↓
format_tool_result() → MCP JSON Response
```

---

## 7. 環境變數

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `MCP_HOST` | `0.0.0.0` | 伺服器監聯位址 |
| `MCP_PORT` | `30786` | 伺服器 Port |
| `PYTHON_WORK_DIR` | `./workspace` | 臨時檔案目錄（啟動時自動清空） |
| `MCP_EXEC_TIMEOUT` | `300` | 最大執行秒數 |
| `MCP_MAX_INPUT` | `1000000` | 最大輸入長度 |
| `MCP_MAX_OUTPUT` | `1000000` | 最大輸出長度 |
| `MYSQL_*` | - | MySQL 連線設定 |
| `TMDB_API_KEY` | - | TMDB API Key |
| `OLLAMA_API_KEY` | - | Ollama Web API Key |
| `PLAYWRIGHT_CDP_ENDPOINT` | `http://127.0.0.1:9222` | Playwright CDP 端點 |
| `REMOTE_BROWSER_ENABLED` | `true` | 啟用遠端瀏覽器功能 |
| `REMOTE_BROWSER_PORT` | `30787` | 遠端瀏覽器 WebSocket Port |
| `REMOTE_BROWSER_TOKEN` | `""` | 遠端瀏覽器認證 Token |

---

## 8. 依賴關係

```
src/mcp_server/
├── __main__.py (啟動入口)
│   └── app.py (FastAPI 路由)
│       ├── config.py (全域設定)
│       ├── schemas.py (資料模型)
│       ├── security.py (認證)
│       ├── utils.py (格式化)
│       ├── api/ (API 相關模組)
│       ├── base/ (基礎模組)
│       │   ├── data_structures.py
│       │   └── logging_config.py
│       ├── model/ (AI 模型)
│       │   └── gemini_api_client.py
│       ├── tools/
│       │   ├── base.py (Registry)
│       │   ├── __init__.py (載入所有 Tools)
│       │   └── 各 Tool 子目錄
│       └── services/
│           └── gmail_service.py
```

---

## 9. 編碼規範

- **型別**: 全專案使用 `dict[str, Any]` + Type Hints
- **異步**: 所有 I/O 使用 `async/await`
- **錯誤處理**: `logger.exception()` 記錄完整堆疊
- **命名**: `snake_case` (函式/變數), `PascalCase` (類別)

---

## 10. 快速參考

| 需求 | 查看檔案 |
|------|----------|
| 修改 API Keys | `src/mcp_server/config.py` - `API_KEYS` |
| 調整超時/限制 | `src/mcp_server/config.py` - `MAX_*` 常數 |
| 新增 Tool | `src/mcp_server/tools/my_tool/my_tool.py` |
| 修改認證邏輯 | `src/mcp_server/security.py` |
| 調整輸出格式 | `src/mcp_server/utils.py` - `format_tool_result()` |
| 修改 MCP 協議 | `src/mcp_server/app.py` - `_handle_*` 函式 |
| 啟動伺服器 | `python -m mcp_server` |

