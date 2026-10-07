# 🤖 AI 自我修復與營運備忘錄 (Internal Memo)

## 🎯 核心原則
偵測到系統工具故障（如 `FileNotFoundError`、路徑錯誤）或配置變更時，AI 應能自行修復並重啟服務；
但**重啟必須精準**，不可使用可能誤殺其他行程的模糊比對指令。

## 🛠️ 常見故障修復流程

### 1. 路徑問題
- **現象**：`FileNotFoundError`，或工作目錄出現在非預期的位置。
- **根因**：`PYTHON_WORK_DIR` / `MCP_SHELL_CWD` 為相對路徑時，若以行程的 CWD 為基準解析，結果會隨啟動位置改變。
- **現行設計**（自 v4.0.0 修復後）：`config.py` 的 `_resolve_path()` 一律以**專案根目錄**（`PROJECT_ROOT`）為基準解析相對路徑，
  且**不在 import 期建立目錄**；`MCP_SHELL_CWD` 不存在時直接回錯誤，不自動建立。
- **排查方式**：`python -c "from mcp_server.config import WORK_DIR, DEFAULT_SHELL_CWD; print(WORK_DIR, DEFAULT_SHELL_CWD)"`
  （可切換不同 cwd 執行，兩者應輸出相同結果）。

### 2. 環境變數生效與進程重啟
- **現象**：修改 `.py` 或 `.env` 後行為未改變。
- **根因**：Python 行程已載入舊的模組與配置。
- **強制重啟方式**（精準）：先終止舊行程再啟動，避免 `pkill -f "mcp_server"` 這類模糊比對誤殺其他行程。

  ```bash
  # 1) 找出正在監聽該埠的 PID（精準）
  PID=$(ss -ltnp 2>/dev/null | grep ':8000' | grep -oP 'pid=\K[0-9]+' | head -1)
  kill "$PID"

  # 2) 等埠釋放後重新啟動
  while ss -ltn | grep -q ':8000'; do sleep 1; done
  cd /path/to/mcp-server && python -m mcp_server
  ```

- 若服務以 `screen` 託管，改用 `screen -S <名稱> -X quit` 後重建；
  注意 `screen -X quit` **不會**終止其子行程，仍需以上述 PID 方式確認埠已釋放。
- 本專案無容器自啟動機制；重啟後務必確認服務已恢復（`curl -H "Authorization: Bearer $AUTH_KEY" http://127.0.0.1:8000/mcp`）。

## 💡 給未來的我
> **改完代碼要重啟；路徑一律以專案根目錄為基準；重啟一律用精準 PID，不要 `pkill -f`。**
