# NATE-MCP-SERVER v4.0.0

NATE-MCP-SERVER 是一個基於 **Model Context Protocol (MCP)** 的工具伺服器，讓大語言模型
（如 Claude Code、Claude Desktop）能安全地操作本地系統：目前提供 Linux Shell 命令執行能力。

## ✨ 核心功能

- 💻 **Shell 執行**: `execute_shell` 直接執行 Linux Shell 命令（bash），支援管道、重定向、環境變數，並可用 `cwd` 參數指定執行目錄（免在命令中自行 `cd` 與 quote）。
- ⏱️ **輸出與逾時保護**: 輸出邊讀邊截斷（預設 1,000,000 字元），超過即終止整個進程組；逾時上限固定 300 秒。
- 🔐 **單一金鑰認證 + 失敗次數限制**: 以 `AUTH_KEY` 保護 `/mcp` 端點；未設定時每次啟動自動產生隨機金鑰並顯示於 console；同一來源 60 秒內失敗 10 次即暫時拒絕。
- 🧩 **模組化工具架構**: 工具置於 `tools/` 下會自動被發現並註冊，易於擴充。
- 📝 **統一日誌**: console 彩色輸出 + `logs/mcp_server.log` 檔案輪替。

## 🚀 快速開始

### 1. 環境需求
- Python 3.10+
- 無需 Docker，直接本地執行

### 2. 安裝
```bash
git clone git@github.com:NateYeh/mcp-server.git
cd mcp-server

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -e .
cp .env.example .env             # 依需要填入 AUTH_KEY 等設定
```

### 3. 啟動服務
```bash
python -m mcp_server

# 或使用啟動腳本（直接執行 python -m mcp_server）
bash src/mcp_server/start.sh
```
服務監聽位址由 `.env` 的 `MCP_HOST` / `MCP_PORT` 決定（預設 `http://0.0.0.0:8000`）。
啟動時 console 會顯示本次使用的認證金鑰：

```
════════════════════════════════════════════════════════════════════════
🔑 AUTH_KEY = <本次啟動使用的金鑰>
════════════════════════════════════════════════════════════════════════
```

> 未設定 `AUTH_KEY` 時，金鑰為隨機產生且只存在記憶體，**重啟後會變更**；
> 建議將固定使用的金鑰寫入 `.env` 的 `AUTH_KEY`。

### 4. 連接客戶端

本伺服器是 HTTP 服務（`POST /mcp`），各客戶端的支援程度不同：

| 客戶端 | 傳輸方式 | 設定方式 |
|--------|----------|----------|
| **Claude Code** | 原生 Streamable HTTP | 直接填 `type: "http"` + `url` + `headers`，**不需橋接** |
| **Claude Desktop** | 設定檔僅 stdio | 需 [`mcp-remote`](https://www.npmjs.com/package/mcp-remote) 橋接（Node.js 18+） |
| 其他（Cursor / VS Code / Cline…） | 多數支援 HTTP | 欄位名稱各異，請查該客戶端文件 |

> 建議優先用 **Claude Code**：原生 HTTP 免去 npx 啟動開銷、免安裝全域套件，也沒有橋接器版本維護問題。

#### 4-1. Claude Code（原生 HTTP，建議）

以 CLI 加入（`--scope user` 為所有專案可用）：

```bash
claude mcp add --transport http nate-mcp http://127.0.0.1:8000/mcp \
  --header "Authorization: Bearer <你的 AUTH_KEY>" --scope user
```

或直接寫入 JSON（`.mcp.json` 專案共用／`~/.claude.json` 個人所有專案）：

```json
{
  "mcpServers": {
    "nate-mcp": {
      "type": "http",
      "url": "http://127.0.0.1:8000/mcp",
      "headers": { "Authorization": "Bearer <你的 AUTH_KEY>" }
    }
  }
}
```

伺服器在另一台機器時，將 `url` 改為 `http://192.168.0.30:8000/mcp`。

**注意事項**

- `type` **必填**：只有 `url` 而無 `type` 的條目會被當成 stdio 而跳過（Claude Code 會提示
  `has a "url" but no "type"`）；`"streamable-http"` 是同義別名。
- 本機連線請用 `127.0.0.1` 而非 `localhost`（Node 可能先解析到 IPv6 `::1`，而本服務監聽 IPv4）。
- 金鑰**別寫進會進版控的檔案**：`.mcp.json` 應改用 `"Authorization": "Bearer ${AUTH_KEY}"` 由環境變數帶入。
  但 Claude Code 對部分憑證類變數名稱會**讀成空字串**（如 `ANTHROPIC_API_KEY`、`ANTHROPIC_AUTH_TOKEN`、
  `NPM_TOKEN` 等），若非清單內的名稱才會正常展開；不確定時先寫死值驗證，成功後再換變數。
- 金鑰錯誤時 Claude Code 標記為 `✘ Failed`，**不會**退回 OAuth 流程；用 `claude mcp list` 或 `/mcp` 查狀態。
- 純 `http://` + 靜態標頭不受限制；Claude Code 僅對 **OAuth token 端點**強制 HTTPS 或 localhost。

#### 4-2. Claude Desktop（stdio 橋接）

`claude_desktop_config.json` **只接受 stdio 子行程**（`command` / `args` / `env`），不支援直接填 URL，
因此需透過 [`mcp-remote`](https://www.npmjs.com/package/mcp-remote) 轉接。

設定檔位置：

| 平台 | 路徑 |
|------|------|
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |

> 檔案不存在時，先在 Claude Desktop 的 `Settings → Developer` 開啟。

##### 本機（Claude Desktop 與伺服器同一台機器）

端點用 `127.0.0.1`，**不要用 `localhost`**（Node 可能先解析到 IPv6 `::1` 而連不上 IPv4 監聽）。

```json
{
  "mcpServers": {
    "nate-mcp": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote@latest",
        "http://127.0.0.1:8000/mcp",
        "--transport", "http-only",
        "--allow-http",
        "--header", "Authorization:${AUTH_HEADER}"
      ],
      "env": { "AUTH_HEADER": "Bearer <你的 AUTH_KEY>" }
    }
  }
}
```

##### 區網／遠端（伺服器在另一台機器，例如 192.168.0.30）

```json
{
  "mcpServers": {
    "nate-mcp": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote@latest",
        "http://192.168.0.30:8000/mcp",
        "--transport", "http-only",
        "--allow-http",
        "--header", "Authorization:${AUTH_HEADER}"
      ],
      "env": { "AUTH_HEADER": "Bearer <你的 AUTH_KEY>" }
    }
  }
}
```

##### 注意事項

- ⚠️ **切勿把 4-1 的 `"url"` 寫法貼進 `claude_desktop_config.json`**：Desktop 不支援遠端條目，
  且已知會**靜默刪除整個 `mcpServers` 區段**（造成既有設定遺失，見 anthropics/claude-code#37286）。
- `http://` 端點**必須加 `--allow-http`**，否則 mcp-remote 會拒絕明文連線（僅在可信任網段使用）。
- **Windows**：`args` 內的空格會被截斷（Claude Desktop 已知問題），因此憑證務必用 `env` 傳入，
  並寫成 `Authorization:${AUTH_HEADER}`（冒號前後不留空格）。上面範例即為此寫法，macOS/Linux 同樣可用。
- 憑證會出現在 process 清單（`ps`）中；若在意，可改用 `--header-file /path/to/headers.txt`，
  檔案內容一行 `Authorization: Bearer <token>`。
- 修改設定後必須**完整結束並重新啟動** Claude Desktop（關閉視窗不算）。
- 驗證：`Settings → Developer` 查看伺服器是否為 connected，或看日誌
  （macOS：`~/Library/Logs/Claude/mcp*.log`、Windows：`%LOCALAPPDATA%\Claude\Logs\mcp.log`）。
- 本伺服器**不提供 stdio transport**，因此無法用 `"command": "python", "args": ["-m", "mcp_server"]`
  直接啟動（客戶端會收到日誌而非 JSON-RPC）；若希望 Desktop 直接以 stdio 拉起，需在伺服器端另新增 stdio 模式。
- 若要從公網給 claude.ai / Claude Desktop 的「自訂連接器（Custom Connector）」使用，該連線是由
  Anthropic 雲端發起，伺服器須有公開 HTTPS 端點並開放其 IP 範圍，不適用於內網部署。

## 🔒 安全提醒

- 本服務的設計目的就是執行任意 shell，**唯一的存取控制是 `AUTH_KEY`**（加上監聽位址）。
  服務刻意不提供命令黑名單——子字串比對可被引號、變數、`$IFS` 等方式繞過，只會造成錯誤的安全感。
- 所以 `AUTH_KEY` 等同於該機器上的 shell 權限：
  - 只在可信任網段使用；純本機使用建議設 `MCP_HOST=127.0.0.1`。
  - 不要寫進版控（寫法見 4-1 的 `${AUTH_KEY}`）。
  - 曾出現在對話、截圖或日誌中的金鑰請直接輪換（改環境變數後重啟服務）。
- 認證失敗有速率限制：同一來源 IP 於 60 秒內失敗 10 次即回 `429`。
- 日誌不會記錄金鑰本身（格式錯誤時僅記錄 scheme）。

## 🔌 API 使用

所有請求需帶 `Authorization: Bearer <AUTH_KEY>`，並以 `POST /mcp` 發送 JSON-RPC。

```bash
# 列出工具
curl -s -X POST http://127.0.0.1:8000/mcp \
  -H "Authorization: Bearer $AUTH_KEY" -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'

# 執行命令
curl -s -X POST http://127.0.0.1:8000/mcp \
  -H "Authorization: Bearer $AUTH_KEY" -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call",
       "params":{"name":"execute_shell","arguments":{"command":"ls -la"}}}'

# 指定執行目錄（選填；相對路徑以 MCP_SHELL_CWD 為基準，預設為專案根目錄）
curl -s -X POST http://127.0.0.1:8000/mcp \
  -H "Authorization: Bearer $AUTH_KEY" -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call",
       "params":{"name":"execute_shell","arguments":{"command":"git status -s","cwd":"apps/ai_novel","timeout":60}}}'

# 健康檢查
curl -s http://127.0.0.1:8000/mcp -H "Authorization: Bearer $AUTH_KEY"
```

> 連線後客戶端會發送 `prompts/list`、`resources/list` 等 discovery 請求，本服務一律回傳空清單（非錯誤），
> 避免客戶端記錄無意義的錯誤。JSON-RPC 通知（無 `id`）則回 `202 Accepted` 且無 body。

## ⚙️ 環境變數配置摘要

| 變數 | 說明 |
|------|------|
| `AUTH_KEY` | 唯一認證金鑰。留空時每次啟動自動產生隨機金鑰並顯示於 console（重啟即變更）。 |
| `MCP_HOST` / `MCP_PORT` | 服務監聽位址與埠號（預設 `0.0.0.0:8000`）。建議僅本機使用時設為 `127.0.0.1`。 |
| `PYTHON_WORK_DIR` | 工作目錄（服務啟動時建立並清空，預設 `./workspace`）。 |
| `MCP_SHELL_CWD` | `execute_shell` 的預設執行目錄（預設專案根目錄；不存在時直接回錯，不自動建立）。工具的 `cwd` 參數以相對路徑給值時，亦以此目錄為基準。 |
| `MCP_EXEC_TIMEOUT` | 命令執行逾時秒數（預設 300；**上限固定 300**，超過會被夾制並記錄警告）。 |
| `MCP_MAX_INPUT` | 單次命令長度上限（預設 1000000 字元）。 |
| `MCP_MAX_OUTPUT` | 單次輸出上限（預設 1000000 字元，stdout / stderr 各自計算）；**邊讀邊截斷**，超過即終止命令並回報 `OutputLimitError`。 |

> 相對路徑（`PYTHON_WORK_DIR`、`MCP_SHELL_CWD`）一律以**專案根目錄**為基準，不受啟動時的工作目錄影響。
> 完整說明請參閱 `.env.example`。

## 🧰 開發

```bash
ruff check src/ && pyright src/
```

新增工具與架構說明請見 [AGENTS.md](AGENTS.md) 與 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

---
**授權**：MIT License
