# NATE-MCP-SERVER v4.0.0

NATE-MCP-SERVER 是一個基於 **Model Context Protocol (MCP)** 的強力工具伺服器，旨在賦予大語言模型（如 Claude Desktop）安全地操作本地系統、執行代碼、搜尋網路與整合第三方服務的能力。

## ✨ 核心功能

- 💻 **多語言執行**: 支援 Python 代碼、Shell 指令與 MySQL 數據庫操作。
- 📁 **進階檔案操作**: 讀寫檔案、精準行替換，以及獨家的「區塊簽名替換」功能（大幅提高代碼修改準確度）。
- 🌐 **網路增強**: 整合 Google 搜尋、网页抓取 (Ollama Web) 與全功能瀏覽器自動化 (Playwright)。
- 📧 **服務整合**: Gmail 郵件管理、TMDB 電影資料查詢、圖片 AI 辨識。
- 🛡️ **安全防護**: 內建黑名單過濾機制與彈性的 API Key 權限分級管理。

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
| `MCP_API_KEYS` | JSON 格式，定義多組 API Key 及其對應的 Tool 權限。 |
| `PYTHON_WORK_DIR` | Python 隔離執行的工作目錄。 |
| `PLAYWRIGHT_CDP_ENDPOINT`| 遠端瀏覽器 CDP 連接點。 |
| `GMAIL_ACCOUNTS` | Gmail OAuth 憑證配置。 |

> 詳細配置說明請參閱內部技術文檔或 `.env.example`。

---
**提示**：如果你是開發者，想了解代碼架構或新增 Tool，請查閱 `docs/PROJECT_MAP.md`。
