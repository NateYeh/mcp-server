# NATE-MCP-SERVER v4.0.0

NATE-MCP-SERVER 是一個基於 **Model Context Protocol (MCP)** 的工具伺服器，讓大語言模型
（如 Claude Desktop）能安全地操作本地系統：目前提供 Linux Shell 命令執行能力。

## ✨ 核心功能

- 💻 **Shell 執行**: `execute_shell` 直接執行 Linux Shell 命令（bash），支援管道、重定向、環境變數。
- 🔐 **單一金鑰認證**: 以 `AUTH_KEY` 保護 `/mcp` 端點；未設定時每次啟動自動產生隨機金鑰並顯示於 console。
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

### 4. 配置 Claude Desktop

Claude Desktop 的 `claude_desktop_config.json` **只接受 stdio 子行程**（`command` / `args` / `env`），
不支援直接填 URL；而本伺服器是 HTTP 服務（`/mcp`），因此需透過 stdio↔HTTP 橋接器
[`mcp-remote`](https://www.npmjs.com/package/mcp-remote) 連接（需 Node.js 18+）。

設定檔位置：

| 平台 | 路徑 |
|------|------|
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |

> 檔案不存在時，先在 Claude Desktop 的 `Settings → Developer` 開啟。

#### 4-1. 本機（Claude Desktop 與伺服器同一台機器）

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

#### 4-2. 區網／遠端（伺服器在另一台機器，例如 192.168.0.30）

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

#### 注意事項

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

# 健康檢查
curl -s http://127.0.0.1:8000/mcp -H "Authorization: Bearer $AUTH_KEY"
```

## ⚙️ 環境變數配置摘要

| 變數 | 說明 |
|------|------|
| `AUTH_KEY` | 唯一認證金鑰。留空時每次啟動自動產生隨機金鑰並顯示於 console。 |
| `MCP_HOST` / `MCP_PORT` | 服務監聽位址與埠號（預設 `0.0.0.0:8000`）。 |
| `PYTHON_WORK_DIR` | 工作目錄（服務啟動時清空，預設 `./workspace`）。 |
| `MCP_SHELL_CWD` | `execute_shell` 的預設執行目錄（預設 `.`）。 |
| `MCP_EXEC_TIMEOUT` | 命令執行逾時秒數（預設 300，上限亦為 300）。 |
| `MCP_MAX_INPUT` / `MCP_MAX_OUTPUT` | 單次輸入／輸出字元數上限（預設 1000000）。 |

> 完整說明請參閱 `.env.example`。

## 🧰 開發

```bash
ruff check src/ && pyright src/
```

新增工具與架構說明請見 [AGENTS.md](AGENTS.md) 與 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

---
**授權**：MIT License
