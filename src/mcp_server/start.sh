#!/bin/bash

# 啟動 MCP Server（服務啟動時會於 console 顯示本次使用的 AUTH_KEY）
echo "🚀 啟動 MCP 伺服器..."
exec python -m mcp_server
