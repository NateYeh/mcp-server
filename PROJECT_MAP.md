# PROJECT_MAP.md — mcp-server 專案導覽

> 快速定位專案結構，詳細架構請參閱 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

## 專案概述

MCP (Model Context Protocol) Server - 讓 AI 能執行 Shell 命令的伺服器。

## 核心目錄

```
src/mcp_server/
├── __main__.py     # 伺服器入口（日誌、AUTH_KEY 顯示、uvicorn）
├── app.py          # FastAPI 應用、路由分發
├── config.py       # 全域配置（含 AUTH_KEY）
├── security.py     # Bearer Token 驗證
├── schemas.py      # 資料模型定義
└── tools/          # 工具模組（擴展區）
    ├── base.py     # 工具註冊機制
    └── execute_shell/  # Shell 執行工具
```

## 認證

- 環境變數 `AUTH_KEY` 為唯一認證金鑰，未設定時每次啟動隨機產生並顯示於 console。
- 客戶端需帶上 `Authorization: Bearer <AUTH_KEY>`。

## 新增工具

在 `src/mcp_server/tools/` 下建立目錄，使用 `@registry.register()` 裝飾器註冊。
