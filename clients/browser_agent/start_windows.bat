@echo off
REM Browser Agent 啟動腳本 (Windows)
REM 
REM 使用方式：
REM   1. 修改下方的 MCP_SERVER_URL 和 MCP_TOKEN
REM   2. 先啟動 Chrome：chrome --remote-debugging-port=9222 --user-data-dir=%TEMP%\chrome_debug
REM   3. 執行此腳本

setlocal

REM ═══════════════════════════════════════════════════════════════════════════════
REM 配置區 - 請修改這裡
REM ═══════════════════════════════════════════════════════════════════════════════

REM MCP Server WebSocket 位址
set MCP_SERVER_URL=ws://your-server-ip:30787

REM 認證 Token（與 MCP Server 設定的 REMOTE_BROWSER_TOKEN 相同）
set MCP_TOKEN=your-secret-token

REM Chrome CDP Endpoint（通常不需要修改）
set CHROME_CDP_ENDPOINT=http://localhost:9222

REM Client ID（可選，用於識別）
set CLIENT_ID=windows-browser-agent

REM ═══════════════════════════════════════════════════════════════════════════════
REM 啟動 Browser Agent
REM ═══════════════════════════════════════════════════════════════════════════════

echo ============================================================
echo  Browser Agent for Windows
echo ============================================================
echo.
echo MCP Server: %MCP_SERVER_URL%
echo CDP Endpoint: %CHROME_CDP_ENDPOINT%
echo Client ID: %CLIENT_ID%
echo.
echo 請確認 Chrome 已啟動並開啟 CDP Port 9222
echo 啟動參數: chrome --remote-debugging-port=9222 --user-data-dir=%%TEMP%%\chrome_debug
echo.
echo 按 Ctrl+C 停止
echo ============================================================
echo.

python agent.py ^
  --server %MCP_SERVER_URL% ^
  --token %MCP_TOKEN% ^
  --cdp-endpoint %CHROME_CDP_ENDPOINT% ^
  --client-id %CLIENT_ID% ^
  -v

endlocal
pause