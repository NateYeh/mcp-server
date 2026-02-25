# 🤖 AI 自我修復與營運備忘錄 (Internal Memo)

## 🎯 核心原則
當偵測到系統工具故障（如 FileNotFoundError, Path Error）或配置變更時，AI 應具備主動修復與重啟進程的能力，無需用戶手動干預。

## 🛠️ 常見故障修復流程

### 1. 路徑偏移/套娃問題 (Path Nesting)
- **現象**：`FileNotFoundError` 但檔案實際存在於更深層或同名目錄中。
- **根因**：`PYTHON_WORK_DIR` 套用相對路徑 `./workspace` 時被重複 `.resolve()` 或多次拼接。
- **修復**：檢查 `src/mcp_server/config.py` 中的 `WORK_DIR` 定位邏輯，確保使用絕對路徑且不重複拼接。

### 2. 環境變數生效與進程重啟
- **現象**：修改了 `.py` 或 `.env` 檔案後，工具執行結果未改變。
- **根因**：Python 進程緩存了舊的配置與模組。
- **強制重啟指令**：
  ```bash
  kill 1
  ```
  *(備註：在 Docker 容器內，PID 1 是主進程，殺掉它會觸發容器的自啟動機制，從而實現熱重啟。)*

## 📋 這次的經驗 (2025-02-25)
- **問題**：`web_screenshot` 報存檔錯誤。
- **解決方案**：
  1. 修正 `config.py` 中的路徑解析邏輯。
  2. 在 `web_playwright.py` 寫入檔案前增加 `mkdir(parents=True)` 強健性檢查。
  3. **關鍵動作**：執行 `kill 1` 讓伺服器重新載入修正後的實體路徑。

## 💡 給未來的我
看到這份備忘錄時，記住：**「改完代碼要重啟，路徑一定要絕對。」**  
如果有需要，直接用 `execute_shell` 執行重啟，不要客氣。
