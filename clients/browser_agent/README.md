# Browser Agent

連接 MCP Server 的遠端瀏覽器代理程式。

## 功能

- 透過 WebSocket 反向連接 MCP Server（繞過防火牆限制）
- 操作本地 Chrome 瀏覽器
- 支援所有 Playwright CDP 操作

## 架構

```
┌─────────────────────────────────────────────────────────────────┐
│                         Docker 容器 (MCP)                        │
│  ┌─────────────────┐         ┌────────────────────────────┐    │
│  │  web_playwright │ ◄────── │  Remote Connection Manager │    │
│  │     (Tools)     │         │  (WebSocket Server: 8001) │    │
│  └─────────────────┘         └────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                                        ▲
                                        │ WebSocket（主動連出）
                                        │
┌───────────────────────────────────────┴─────────────────────────┐
│                          Windows 端                              │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    Browser Agent                           │   │
│  │  ┌──────────────┐    ┌─────────────────────────────────┐  │   │
│  │  │ WebSocket    │    │  Playwright CDP                 │  │   │
│  │  │ Client       │◄──►│  (連接本地 Chrome:9222)         │  │   │
│  │  └──────────────┘    └─────────────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│                    ┌──────────────────┐                         │
│                    │  Chrome Browser  │                         │
│                    │  (可見視窗)       │                         │
│                    └──────────────────┘                         │
└─────────────────────────────────────────────────────────────────┘
```

## 安裝

### 1. 安裝依賴

```bash
cd clients/browser_agent
pip install -r requirements.txt
playwright install chromium
```

### 2. 啟動 Chrome（開啟 CDP Port）

**Windows:**
```cmd
"C:\Program Files\Google\Chrome\Application\chrome.exe" ^
  --remote-debugging-port=9222 ^
  --user-data-dir="%TEMP%\chrome_debug"
```

**macOS:**
```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir=/tmp/chrome_debug
```

**Linux:**
```bash
google-chrome \
  --remote-debugging-port=9222 \
  --user-data-dir=/tmp/chrome_debug
```

### 3. 設定 MCP Server

在 MCP Server 的 `.env` 檔案中加入：

```env
# 遠端瀏覽器設定
REMOTE_BROWSER_ENABLED=true
REMOTE_BROWSER_PORT=8001
REMOTE_BROWSER_TOKEN=your-secret-token
```

### 4. 設定 Browser Agent（推薦使用 .env 檔案）

複製範例設定檔並編輯：

```bash
cd clients/browser_agent
cp .env.example .env
# 編輯 .env 檔案，填入 MCP_SERVER_URL 和 MCP_TOKEN
```

`.env` 檔案內容：
```env
MCP_SERVER_URL=ws://your-mcp-server-ip:8001
MCP_TOKEN=your-secret-token-here
CHROME_CDP_PORT=9222
CLIENT_ID=browser-agent
```

### 5. 啟動 Browser Agent

**使用 .env 檔案（推薦）：**
```bash
python agent.py
# 或 Windows 啟動腳本（會自動啟動 Chrome）
python start_windows.py
```

**使用命令列參數：**
```bash
python agent.py --server ws://your-server-ip:8001 --token your-secret-token
```

## 環境變數

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `MCP_SERVER_URL` | `ws://localhost:8001` | MCP Server WebSocket 位址 |
| `MCP_TOKEN` | `""` | 認證 Token |
| `CHROME_CDP_ENDPOINT` | `http://localhost:9222` | Chrome CDP Endpoint |
| `CLIENT_ID` | `browser-agent` | Client ID（用於識別） |
| `RECONNECT_INTERVAL` | `5.0` | 重連間隔（秒） |
| `HEARTBEAT_INTERVAL` | `30.0` | 心跳間隔（秒） |

## 支援的操作

Browser Agent 支援所有 MCP web_playwright 工具的操作：

- `web_navigate` - 導航到 URL
- `web_screenshot` - 截圖
- `web_click` - 點擊元素
- `web_fill` - 填寫表單
- `web_extract` - 提取內容
- `web_evaluate` - 執行 JavaScript
- `web_wait` - 等待元素
- `web_scroll` - 滾動頁面
- `web_get_url` - 取得 URL
- `web_get_title` - 取得標題
- `web_get_status` - 取得狀態

## 故障排除

### 無法連接到 Chrome

確認 Chrome 已使用以下參數啟動：
```
--remote-debugging-port=9222 --user-data-dir=/tmp/chrome_debug
```

檢查 CDP 是否可用：
```bash
curl http://localhost:9222/json/version
```

### 無法連接到 MCP Server

1. 確認 MCP Server 已啟動遠端瀏覽器功能
2. 確認防火牆允許出站連接到 8001 Port
3. 確認 Token 正確

### 認證失敗

確認 `REMOTE_BROWSER_TOKEN` 與 `MCP_TOKEN` 設定一致。

## 授權

MIT License