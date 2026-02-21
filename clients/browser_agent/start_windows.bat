@echo off
chcp 65001 >nul
REM ============================================================================
REM Browser Agent 啟動腳本 (Windows)
REM 
REM 功能：
REM   1. 自動啟動 Chrome（開啟 CDP Port 9222）
REM   2. 啟動 Browser Agent 連接 MCP Server
REM
REM 使用方式：
REM   方式一：設定環境變數後執行
REM     set MCP_SERVER_URL=ws://192.168.1.100:30787
REM     set MCP_TOKEN=your-secret-token
REM     start_windows.bat
REM
REM   方式二：直接修改下方預設值後執行
REM     start_windows.bat
REM ============================================================================

setlocal enabledelayedexpansion

REM ═══════════════════════════════════════════════════════════════════════════════
REM 配置區 - 優先使用環境變數，若無則使用預設值
REM ═══════════════════════════════════════════════════════════════════════════════

REM MCP Server WebSocket 位址
if not defined MCP_SERVER_URL set MCP_SERVER_URL=ws://your-server-ip:30787

REM 認證 Token（與 MCP Server 設定的 REMOTE_BROWSER_TOKEN 相同）
if not defined MCP_TOKEN set MCP_TOKEN=your-secret-token

REM Chrome CDP Port（通常不需要修改）
if not defined CHROME_CDP_PORT set CHROME_CDP_PORT=9222

REM Client ID（可選，用於識別）
if not defined CLIENT_ID set CLIENT_ID=windows-browser-agent

REM Chrome 用戶資料目錄（使用獨立目錄避免衝突）
if not defined CHROME_USER_DATA set CHROME_USER_DATA=%TEMP%\chrome_remote_debug

REM ═══════════════════════════════════════════════════════════════════════════════
REM 自動偵測 Chrome 路徑
REM ═══════════════════════════════════════════════════════════════════════════════

set CHROME_PATH=

REM 優先檢查常見路徑
if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" (
    set CHROME_PATH=C:\Program Files\Google\Chrome\Application\chrome.exe
    goto :chrome_found
)

if exist "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" (
    set CHROME_PATH=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe
    goto :chrome_found
)

REM 檢查使用者目錄
set CHROME_USER_PATH=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe
if exist "%CHROME_USER_PATH%" (
    set CHROME_PATH=%CHROME_USER_PATH%
    goto :chrome_found
)

REM 嘗試從登錄檔取得
for /f "tokens=2*" %%A in ('reg query "HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe" /ve 2^>nul') do (
    set CHROME_PATH=%%B
    goto :chrome_found
)

echo.
echo [錯誤] 找不到 Chrome！
echo 請確認 Google Chrome 已安裝，或手動設定 CHROME_PATH 環境變數。
echo.
pause
exit /b 1

:chrome_found
echo.
echo ============================================================
echo  Browser Agent for Windows
echo ============================================================
echo.
echo MCP Server: %MCP_SERVER_URL%
echo CDP Port: %CHROME_CDP_PORT%
echo Client ID: %CLIENT_ID%
echo Chrome Path: %CHROME_PATH%
echo User Data: %CHROME_USER_DATA%
echo.

REM ═══════════════════════════════════════════════════════════════════════════════
REM 檢查 Chrome CDP 是否已在運行
REM ═══════════════════════════════════════════════════════════════════════════════

echo [檢查] 檢查 Chrome CDP 是否已啟動...

powershell -Command "try { Invoke-WebRequest -Uri 'http://localhost:%CHROME_CDP_PORT%/json/version' -TimeoutSec 2 -UseBasicParsing | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1

if %errorlevel% equ 0 (
    echo [跳過] Chrome CDP 已在運行中 (port %CHROME_CDP_PORT%)
    goto :start_agent
)

REM ═══════════════════════════════════════════════════════════════════════════════
REM 啟動 Chrome（開啟 CDP Port）
REM ═══════════════════════════════════════════════════════════════════════════════

echo [啟動] 正在啟動 Chrome...

REM 建立用戶資料目錄
if not exist "%CHROME_USER_DATA%" mkdir "%CHROME_USER_DATA%"

REM 啟動 Chrome（背景執行）
start "" "%CHROME_PATH%" ^
    --remote-debugging-port=%CHROME_CDP_PORT% ^
    --user-data-dir="%CHROME_USER_DATA%" ^
    --no-first-run ^
    --no-default-browser-check ^
    --disable-background-networking ^
    --disable-extensions ^
    --disable-translate ^
    --about:blank

echo [等待] 等待 Chrome CDP 啟動...

REM 等待 Chrome CDP 啟動（最多等待 10 秒）
set WAIT_COUNT=0
:wait_chrome
if %WAIT_COUNT% geq 20 (
    echo [錯誤] Chrome CDP 啟動逾時！
    pause
    exit /b 1
)

powershell -Command "try { Invoke-WebRequest -Uri 'http://localhost:%CHROME_CDP_PORT%/json/version' -TimeoutSec 1 -UseBasicParsing | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1

if %errorlevel% neq 0 (
    set /a WAIT_COUNT+=1
    timeout /t 1 >nul
    goto :wait_chrome
)

echo [成功] Chrome CDP 已啟動 (port %CHROME_CDP_PORT%)
echo.

REM ═══════════════════════════════════════════════════════════════════════════════
REM 啟動 Browser Agent
REM ═══════════════════════════════════════════════════════════════════════════════

:start_agent
echo ============================================================
echo 按 Ctrl+C 停止 Browser Agent
echo ============================================================
echo.

python "%~dp0agent.py" ^
  --server %MCP_SERVER_URL% ^
  --token %MCP_TOKEN% ^
  --cdp-endpoint http://localhost:%CHROME_CDP_PORT% ^
  --client-id %CLIENT_ID% ^
  -v

REM ═══════════════════════════════════════════════════════════════════════════════
REM 結束
REM ═══════════════════════════════════════════════════════════════════════════════

echo.
echo Browser Agent 已停止
endlocal
pause