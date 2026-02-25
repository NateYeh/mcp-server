# PROJECT_MAP.md — mcp-server 專案導覽

> 快速定位專案結構，詳細架構請參閱 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

## 專案概述

MCP (Model Context Protocol) Server - 讓 AI 能執行 Shell、Python、網頁操作等工具的伺服器。

## 核心目錄

```
src/mcp_server/
├── app.py          # 伺服器入口、路由分發
├── config.py       # 全域配置
├── security.py     # 權限與安全檢查
├── schemas.py      # 資料模型定義
└── tools/          # 工具模組（擴展區）
    ├── base.py     # 工具註冊機制
    ├── shell/      # Shell 執行工具
    ├── python/     # Python 執行工具
    └── web/        # 網頁自動化工具
```

## 新增工具

在 `src/mcp_server/tools/` 下建立目錄，使用 `@registry.register()` 裝飾器註冊。