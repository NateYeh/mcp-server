# AGENTS.md — mcp-server 專案指南

> 本檔案供 AI 與開發者快速進入狀況。詳細設計說明見 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## 專案概述

MCP (Model Context Protocol) Server：以 FastAPI 提供 `/mcp` HTTP 端點，讓 LLM 客戶端
（如 Claude Desktop）能呼叫本機工具。目前僅提供 `execute_shell`（Linux Shell 命令執行）。

- 版本：4.0.0
- Python：>= 3.10
- 執行方式：**本地直接執行**（無容器化部署）
- 認證：單一 `AUTH_KEY`（Bearer Token）

## 目錄結構

```
mcp-server/
├── src/mcp_server/
│   ├── __main__.py            # 入口：日誌初始化、顯示 AUTH_KEY、啟動 uvicorn
│   ├── app.py                 # FastAPI 應用、/mcp 路由、MCP 協議分發
│   ├── config.py              # 全域配置（AUTH_KEY、路徑、伺服器、執行限制）
│   ├── security.py            # Bearer Token 驗證（hmac.compare_digest）
│   ├── schemas.py             # MCPError（協議層錯誤）
│   ├── utils.py               # format_tool_result()（ExecutionResult → MCP 回應）
│   ├── base/
│   │   └── logging_config.py  # 統一日誌（console 彩色 + RotatingFileHandler）
│   ├── tools/
│   │   ├── __init__.py        # 動態掃描目錄、自動註冊所有工具
│   │   ├── base.py            # ToolRegistry 單例與 @registry.register
│   │   ├── schemas.py         # ExecutionResult（工具回傳格式）
│   │   └── execute_shell/     # 目前唯一的工具
│   └── start.sh               # 啟動腳本（先開發模式安裝 natekit，再啟動服務）
├── docs/
│   ├── ARCHITECTURE.md        # 詳細架構與開發範式
│   └── SELF_HEALING_MEMO.md   # 故障排除備忘錄
├── .env.example               # 環境變數範本
├── pyproject.toml             # 套件與工具設定（ruff / mypy / pyright）
└── workspace/                 # 執行工作目錄（runtime 自動建立，不進版控）
```

## 認證機制

- 金鑰來源：環境變數 `AUTH_KEY`。
- 未設定時：`config.py` 以 `secrets.token_urlsafe(32)` **隨機產生**，僅存在於記憶體，
  `__main__.py` 會於啟動時在 console 顯示；**重啟即變更**。
- 客戶端必須帶：`Authorization: Bearer <AUTH_KEY>`。
  - 缺少或格式錯誤 → `401`
  - 金鑰不符 → `403`
- 驗證邏輯在 `security.py` 的 `verify_api_key()`，使用 `hmac.compare_digest` 常數時間比較。
- 已移除多金鑰（`MCP_API_KEYS`）、Tool 權限白名單／排除清單與 Gmail 帳號綁定機制。

## MCP 端點

| 方法 | 路徑 | 說明 |
|------|------|------|
| POST | `/mcp` | MCP 協議：`initialize`、`tools/list`、`tools/call` |
| GET | `/mcp` | 健康檢查（回傳版本、已載入工具數、設定摘要） |

## 執行與驗證

```bash
# 安裝（開發模式）
pip install -e .
cp .env.example .env      # 視需要填入 AUTH_KEY

# 啟動
python -m mcp_server       # 或 bash src/mcp_server/start.sh

# 靜態檢查（變更後必跑）
ruff check src/
pyright src/

# 冒煙測試
curl -s -X POST http://127.0.0.1:8000/mcp \
  -H "Authorization: Bearer <AUTH_KEY>" -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call",
       "params":{"name":"execute_shell","arguments":{"command":"echo hi"}}}'
```

## 新增 Tool 流程

1. 建立目錄 `src/mcp_server/tools/my_tool/`，內含 `__init__.py` 與 `my_tool.py`。
2. 以裝飾器註冊（`name` 即為 MCP 工具名稱）：

   ```python
   from mcp_server.tools.base import registry
   from mcp_server.tools.schemas import ExecutionResult

   @registry.register(
       name="my_tool",
       description="描述功能...",
       input_schema={"type": "object", "properties": {"arg": {"type": "string"}}, "required": ["arg"]},
   )
   async def handle_my_tool(args: dict) -> ExecutionResult:
       return ExecutionResult(success=True, stdout="...")
   ```

3. `tools/__init__.py` 的 `_discover_tools()` 會自動載入子目錄，**無須手動加入 import**。
4. 若 handler 需要 FastAPI `Request`，將 `request` 設為關鍵字參數即可（`base.py` 會自動注入）。

## 程式碼規範

- 所有函式必須標註參數與回傳型別（Type Hint）。
- 遵循 PEP8；Docstring 與註解一律使用**繁體中文**。
- 禁止 `try-except: pass`；例外一律以 `logger.exception()` 記錄完整上下文。
- 嚴禁在程式碼中寫死密鑰，一律由環境變數／`.env` 提供。
- 預設值：`str` → `''`、`list` → `[]`、`dict` → `{}`（避免 `None` 造成 runtime error）。
- 變更後必須通過 `ruff check` 與 `pyright`（0 error）；不留一次性測試、除錯 print 等墓碑代碼。

## 日誌規範

- 透過 `mcp_server.base.logging_config.setup_logging()` 初始化（console 彩色輸出 + 檔案輪替）。
- 日誌檔：`logs/mcp_server.log`（10 MB × 5 份輪替）。
- `workspace/` 於服務啟動時清空，僅作為工具執行的工作目錄。
