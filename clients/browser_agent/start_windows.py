#!/usr/bin/env python3
"""
Browser Agent Startup Script (Windows)

Features:
  1. Auto-start Chrome (with CDP Port 9222)
  2. Start Browser Agent to connect MCP Server

Usage:
  Method 1: Use .env file (recommended)
    1. Copy .env.example to .env
    2. Edit .env with your settings
    3. Run: python start_windows.py

  Method 2: Set environment variables then run
    set MCP_SERVER_URL=ws://192.168.1.100:30787
    set MCP_TOKEN=your-secret-token
    python start_windows.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# Auto-load .env file
_ENV_PATH = Path(__file__).parent / ".env"
if _ENV_PATH.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_ENV_PATH)
        print(f"📁 已載入設定檔: {_ENV_PATH}")
    except ImportError:
        print("⚠️ 未安裝 python-dotenv，請執行: pip install python-dotenv")

# ============================================================================
# Configuration - Use environment variables first, fallback to defaults
# ============================================================================

MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "")
MCP_TOKEN = os.environ.get("MCP_TOKEN", "")
CHROME_CDP_PORT = int(os.environ.get("CHROME_CDP_PORT", "9222"))
CLIENT_ID = os.environ.get("CLIENT_ID", "windows-browser-agent")
CHROME_USER_DATA = os.environ.get(
    "CHROME_USER_DATA",
    os.path.join(os.environ.get("TEMP", ""), "chrome_remote_debug"),
)

# ============================================================================
# Chrome Detection
# ============================================================================

CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
]


def find_chrome() -> str | None:
    """Find Chrome executable path."""
    # Check common paths
    for path in CHROME_PATHS:
        if os.path.exists(path):
            return path

    # Try to get from registry (Windows only)
    try:
        import winreg  # type: ignore[attr-defined]

        with winreg.OpenKey(  # type: ignore[attr-defined]
            winreg.HKEY_LOCAL_MACHINE,  # type: ignore[attr-defined]
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "")  # type: ignore[attr-defined]
            if os.path.exists(value):
                return value
    except (ImportError, OSError):
        pass

    return None


def check_cdp_running(port: int) -> bool:
    """Check if Chrome CDP is already running on the specified port."""
    try:
        url = f"http://localhost:{port}/json/version"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=2) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError, Exception):
        return False


def start_chrome(chrome_path: str, port: int, user_data: str) -> subprocess.Popen | None:
    """Start Chrome with CDP port enabled."""
    # Create user data directory
    Path(user_data).mkdir(parents=True, exist_ok=True)

    # Chrome arguments
    args = [
        chrome_path,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={user_data}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-networking",
        "--disable-extensions",
        "--disable-translate",
        "--about:blank",
    ]

    # Start Chrome in background
    try:
        process = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
        return process
    except OSError as e:
        print(f"[ERROR] Failed to start Chrome: {e}")
        return None


def wait_for_cdp(port: int, timeout: int = 10) -> bool:
    """Wait for Chrome CDP to be ready."""
    print("[WAIT] Waiting for Chrome CDP to start...")

    start_time = time.time()
    while time.time() - start_time < timeout:
        if check_cdp_running(port):
            return True
        time.sleep(0.5)

    return False


def start_browser_agent(
    server_url: str,
    token: str,
    cdp_port: int,
    client_id: str,
) -> int:
    """Start the Browser Agent Python script."""
    script_path = Path(__file__).parent / "agent.py"

    if not script_path.exists():
        print(f"[ERROR] Agent script not found: {script_path}")
        return 1

    cmd = [
        sys.executable,
        str(script_path),
        "--server", server_url,
        "--token", token,
        "--cdp-endpoint", f"http://localhost:{cdp_port}",
        "--client-id", client_id,
        "-v",
    ]

    print("[START] Starting Browser Agent...")
    print(f"        Server: {server_url}")
    print(f"        CDP: http://localhost:{cdp_port}")
    print(f"        Client ID: {client_id}")
    print()

    try:
        # Run in the script's directory for correct imports
        result = subprocess.run(cmd, cwd=script_path.parent)
        return result.returncode
    except KeyboardInterrupt:
        print("\n[INFO] Browser Agent stopped by user")
        return 0
    except OSError as e:
        print(f"[ERROR] Failed to start Browser Agent: {e}")
        return 1


def main() -> int:
    """Main entry point."""
    print()
    print("=" * 60)
    print(" Browser Agent for Windows")
    print("=" * 60)
    print()

    # Validate required environment variables
    missing_vars = []
    if not MCP_SERVER_URL:
        missing_vars.append("MCP_SERVER_URL")
    if not MCP_TOKEN:
        missing_vars.append("MCP_TOKEN")

    if missing_vars:
        print("[ERROR] 缺少必要環境變數！")
        print()
        for var in missing_vars:
            print(f"  {var}: ❌ 未設定")
        print()
        print("請透過以下方式設定：")
        print()
        print("  方法 1: 設定 .env 檔案")
        print("    1. 複製 .env.example 到 .env")
        print("    2. 編輯 .env 並設定 MCP_SERVER_URL 和 MCP_TOKEN")
        print("    3. 重新執行腳本")
        print()
        print("  方法 2: 設定環境變數")
        print("    set MCP_SERVER_URL=ws://192.168.1.100:30787")
        print("    set MCP_TOKEN=your-secret-token")
        print("    python start_windows.py")
        print()
        input("Press Enter to exit...")
        return 1

    # Find Chrome
    chrome_path = find_chrome()
    if not chrome_path:
        print("[ERROR] Chrome not found!")
        print("Please ensure Google Chrome is installed,")
        print("or manually set CHROME_PATH environment variable.")
        print()
        input("Press Enter to exit...")
        return 1

    print(f"MCP Server: {MCP_SERVER_URL}")
    print(f"CDP Port: {CHROME_CDP_PORT}")
    print(f"Client ID: {CLIENT_ID}")
    print(f"Chrome Path: {chrome_path}")
    print(f"User Data: {CHROME_USER_DATA}")
    print()

    # Check if CDP already running
    print("[CHECK] Checking if Chrome CDP is running...")
    if check_cdp_running(CHROME_CDP_PORT):
        print(f"[SKIP] Chrome CDP already running (port {CHROME_CDP_PORT})")
        print()
    else:
        # Start Chrome
        print("[START] Starting Chrome...")
        process = start_chrome(chrome_path, CHROME_CDP_PORT, CHROME_USER_DATA)
        if not process:
            input("Press Enter to exit...")
            return 1

        # Wait for CDP
        if not wait_for_cdp(CHROME_CDP_PORT, timeout=10):
            print("[ERROR] Chrome CDP startup timeout!")
            input("Press Enter to exit...")
            return 1

        print(f"[SUCCESS] Chrome CDP started (port {CHROME_CDP_PORT})")
        print()

    # Start Browser Agent
    print("=" * 60)
    print(" Press Ctrl+C to stop Browser Agent")
    print("=" * 60)
    print()

    return start_browser_agent(
        server_url=MCP_SERVER_URL,
        token=MCP_TOKEN,
        cdp_port=CHROME_CDP_PORT,
        client_id=CLIENT_ID,
    )


if __name__ == "__main__":
    sys.exit(main())
