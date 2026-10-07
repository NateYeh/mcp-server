# NATE-MCP-SERVER v4.0.0

NATE-MCP-SERVER 是一個基於 **Model Context Protocol (MCP)** 的強力工具伺服器，旨在賦予大語言模型（如 Claude Desktop）安全地操作本地系統、執行代碼、搜尋網路與整合第三方服務的能力。

## ✨ 核心功能

- 💻 **Shell 執行**: 直接執行 Linux Shell 命令（bash），支援管道、重定向與環境變數。
- 🔐 **單一金錀認證**: 以 `AUTH_KEY` 保護 `/mcp` 端點；未設定時自動產生隨機金錀並於啟動時顯示。
- 🧩 **模組化工具架構**: 工具放在 `tools/` 下自動發現註冊，易於擴充。

## 🚀 快速開始

### 1. 環境需求
- Python 3.10+
- （選用）Chrome / Chromium，供 Playwright 瀏覽器自動化使用

> 本專案僅支援本地直接執行，不提供容器化部署。

### 2. 本地安裝
1.  **建立虛擬環境並安裝依賴**:
    ```bash
    python -m venv .venv
    source .venv/bin/activate        # Windows: .venv\Scripts\activate
    pip install -e .
    playwright install chromium
    ```
2.  **準備配置**:
    - 複製 `.env.example` 並重新命名為 `.env`，填入必要的 API Key。
    - 依實際環境調整 `PYTHON_WORK_DIR`、`MCP_HOST`、`MCP_PORT` 等路徑與埠號。

### 3. 啟動服務
```bash
python -m mcp_server

# 或使用啟動腳本（會先以開發模式安裝 natekit，再啟動服務）
bash src/mcp_server/start.sh
```
服務預設監聽 `http://0.0.0.0:8000`（由 `.env` 的 `MCP_HOST` / `MCP_PORT` 決定）。

啟動時 console 會顯示本次使用的認證金錀：

```
════════════════════════════════════════════════════════════════════════
🔑 AUTH_KEY = <本次啟動使用的金錀>
════════════════════════════════════════════════════════════════════════
```

> 未設定 `AUTH_KEY` 時，金錀為隨機產生且只存在記憶體，**重啟後會變更**；
> 建議將長期使用的金錀寫入 `.env` 的 `AUTH_KEY`。

### 4. 配置 Claude Desktop
修改你的 `config.json` (通常位於 `%AppData%\Claude\config.json` 或 `~/Library/Application Support/Claude/config.json`)：
```json
{
  "mcpServers": {
    "Nate-MCP": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "/absolute/path/to/mcp-server"
    }
  }
}
```
> 建議將 `command` 指向虛擬環境中的 Python（例如 `/absolute/path/to/mcp-server/.venv/bin/python`），以確保依賴正確載入。

## ⚙️ 環境變數配置摘要

| 變數 | 說明 |
|------|------|
| `AUTH_KEY` | 唯一認證金錀（`Authorization: Bearer <AUTH_KEY>`）。留空時每次啟動自動產生隨機金錀並顯示於 console。 |
| `PYTHON_WORK_DIR` | 工作目錄（`execute_shell` 產出檔案的隔離區）。 |
| `MCP_SHELL_CWD` | `execute_shell` 的預設執行目錄。 |
| `MCP_EXEC_TIMEOUT` | 命令執行逾時秒數（預設 300）。 |

> 詳細配置說明請參閱內部技術文檔或 `.env.example`。

---
**提示**：如果你是開發者，想了解代碼架構或新增 Tool，請查閱 `docs/PROJECT_MAP.md`。
