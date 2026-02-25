# 🗺️ AI Developer Project Map (mcp-server)

本檔案旨在讓 AI 或開發者快速理解專案架構、代碼邏輯與開發規範，無需閱讀所有原始碼。

## 🏗️ 核心架構與路徑
專案採用 `src-layout` 結構，主要代碼位於 `src/mcp_server/`。

- **`app.py`**: 伺服器入口。負責 FastAPI 路由初始化、MCP 協議處理與工具分發邏輯。
- **`config.py`**: 全域配置中心。包含 API Key 定義、超時設定、安全黑名單（DANGEROUS_PATTERNS）。
- **`security.py`**: 安全驗證層。處理 Bearer Token、Tool 權限過濾 (Wildcard 支援) 與指令安全檢查。
- **`tools/`**: **【核心擴展區】**
    -   `base.py`: 提供 `ToolRegistry` 單例與 `@registry.register` 裝飾器。
    -   `__init__.py`: 負責自動遍歷子目錄並註冊所有工具模組。
- **`schemas.py`**: 統一的數據交換模型，所有 Tool 必須返回 `ExecutionResult`。
- **`workspace/`**: 執行環境隔離區域，所有 Shell/Python 工具的執行起點。

## 🛠️ 開發範式：新增 Tool 流程
當 AI 需要新增一個工具（例如 `my_tool`）時，必須嚴格執行以下步驟：

1.  **建立結構**: 建立目錄 `src/mcp_server/tools/my_tool/`。
2.  **撰寫代碼**: 在 `my_tool.py` 中實作業務邏輯。
    ```python
    from mcp_server.schemas import ExecutionResult
    from mcp_server.tools.base import registry

    @registry.register(
        name="my_tool",
        description="描述功能...",
        input_schema={"type": "object", "properties": {...}}
    )
    async def handle_my_tool(args: dict) -> ExecutionResult:
        # 1. 解析參數 args
        # 2. 執行業務邏輯 (異步優先)
        # 3. 返回 ExecutionResult
        return ExecutionResult(success=True, stdout="...")
    ```
3.  **註冊匯入**:
    -   在 `tools/my_tool/__init__.py` 加入 `from .my_tool import *`
    -   在 `tools/__init__.py` 加入 `from mcp_server.tools.my_tool import *`

## 🛡️ 安全機制規範
-   **權限控制**: 存取 `config.API_KEYS` 來檢查當前 Key 的授權範圍。
-   **黑名單**: `execute_shell` 必須經過 `security.py` 的樣式檢查。
-   **資源限制**: 所有 Tool 應尊重 `MAX_EXECUTION_TIME` 與 `MAX_OUTPUT_LENGTH`。

## 🔍 代碼執行數據流
`LLM Request` -> `app.py` -> `security.py (權限檢查)` -> `tools/base.py (分發)` -> `Specific Tool Handler` -> `format_tool_result()` -> `JSON Response`

---
**日誌規範**: 關鍵錯誤請使用 `logger.exception()`，所有運行日誌記錄於 `logs/mcp_server.log`。
