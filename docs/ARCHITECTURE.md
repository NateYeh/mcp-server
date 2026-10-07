# 🗺️ mcp-server 架構說明

本檔案說明專案架構、代碼邏輯與開發範式。專案總覽與規範請見 [../AGENTS.md](../AGENTS.md)。

## 🏗️ 核心架構與路徑

專案採用 `src-layout` 結構，主要代碼位於 `src/mcp_server/`。

- **`__main__.py`**: 入口。初始化日誌、清理工作目錄、顯示本次 `AUTH_KEY`、啟動 uvicorn。
- **`app.py`**: FastAPI 應用。負責 `/mcp` 路由、MCP 協議處理（`initialize` / `tools/list` / `tools/call`）與工具分發。
- **`config.py`**: 全域配置中心。包含 `AUTH_KEY`、伺服器監聽位址、路徑、執行限制與 `DANGEROUS_SHELL_PATTERNS`。
- **`security.py`**: 認證層。`verify_api_key()` 以 `hmac.compare_digest` 比對 Bearer Token 與 `AUTH_KEY`。
- **`tools/`**: **【核心擴展區】**
    -   `base.py`: 提供 `ToolRegistry` 單例與 `@registry.register` 裝飾器。
    -   `__init__.py`: `_discover_tools()` 自動遍歷子目錄並匯入所有工具模組。
    -   `schemas.py`: `ExecutionResult`，所有工具統一的回傳格式。
    -   `execute_shell/`: 目前唯一的工具（Linux Shell 命令執行）。
- **`schemas.py`**: MCP 協議層錯誤型別 `MCPError`。
- **`utils.py`**: `format_tool_result()`，將 `ExecutionResult` 轉為 MCP 回應格式。
- **`base/logging_config.py`**: 統一日誌設定（console 彩色 + RotatingFileHandler）。
- **`workspace/`**: 工作目錄，服務啟動時清空；工具執行以此為預設起點（不進版控）。

## 🛠️ 開發範式：新增 Tool 流程

1.  **建立結構**: 建立目錄 `src/mcp_server/tools/my_tool/`，內含 `__init__.py` 與 `my_tool.py`。
2.  **撰寫代碼**: 在 `my_tool.py` 中實作業務邏輯並以裝飾器註冊。
    ```python
    from mcp_server.tools.base import registry
    from mcp_server.tools.schemas import ExecutionResult

    @registry.register(
        name="my_tool",
        description="描述功能...",
        input_schema={"type": "object", "properties": {"arg": {"type": "string"}}, "required": ["arg"]},
    )
    async def handle_my_tool(args: dict) -> ExecutionResult:
        # 1. 解析參數 args
        # 2. 執行業務邏輯（異步優先）
        # 3. 返回 ExecutionResult
        return ExecutionResult(success=True, stdout="...")
    ```
3.  **無須註冊匯入**: `tools/__init__.py` 的 `_discover_tools()` 會自動載入 `tools/` 下的子目錄。
4.  **需要 Request 時**: 在 handler 簽名加入 `request` 關鍵字參數，`ToolRegistry.execute()` 會自動注入。

## 🛡️ 安全機制規範

- **認證**: 僅接受 `Authorization: Bearer <AUTH_KEY>`；缺 Header／格式錯誤 → 401，金鑰錯誤 → 403。
- **黑名單**: `execute_shell` 執行前比對 `config.DANGEROUS_SHELL_PATTERNS`（預設空清單，可依需求增補）。
- **資源限制**: 工具應尊重 `MAX_EXECUTION_TIME`、`MAX_INPUT_LENGTH`、`MAX_OUTPUT_LENGTH`。

## 🔍 代碼執行數據流

`LLM Request` → `app.py` → `security.py (verify_api_key)` → `tools/base.py (registry 分發)`
→ `Specific Tool Handler` → `format_tool_result()` → `JSON Response`

---
**日誌規範**: 關鍵錯誤請使用 `logger.exception()`；運行日誌記錄於 `logs/mcp_server.log`。
