#!/bin/bash

# 1. 檢查並安裝 natekit (開發模式 -e)
NATEKIT_PATH="/mnt/public/Develop/Projects/project/libs/natekit"
if [ -d "$NATEKIT_PATH" ]; then
    echo "📦 檢測到 natekit，正在以開發模式安裝..."
    pip install -e "$NATEKIT_PATH"
else
    echo "⚠️ 未檢測到 natekit 目錄，跳過安裝。"
fi

# 2. 啟動 MCP Server
echo "🚀 啟動 MCP 伺服器..."
exec python -m mcp_server
