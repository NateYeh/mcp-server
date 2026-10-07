"""
NATE-MCP-SERVER

MCP (Model Context Protocol) Server：模組化 Tool 架構，Tool 定義分散到獨立檔案中。
"""

import logging
import platform
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from mcp_server import __version__
from mcp_server.base.logging_config import setup_logging
from mcp_server.config import (
    MAX_EXECUTION_TIME,
    MAX_OUTPUT_LENGTH,
    WORK_DIR,
    cleanup_work_directory,
)
from mcp_server.schemas import MCPError
from mcp_server.security import verify_api_key
from mcp_server.tools import registry
from mcp_server.utils import format_tool_result

logger = logging.getLogger(__name__)

# 本伺服器對客戶端提供的工具使用說明（Claude Code 的 tool search 會參考此欄位）
SERVER_INSTRUCTIONS = (
    "本伺服器提供在本機執行 Linux Shell 命令的能力（工具：execute_shell）。"
    "當需要執行系統命令、檔案操作、查詢系統狀態或文字處理時，請使用 execute_shell。"
)


# ═══════════════════════════════════════════════════════════════════════════════
# Lifespan 管理
# ═══════════════════════════════════════════════════════════════════════════════
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI Lifespan 管理器

    啟動時：初始化日誌（若尚未設定）、清理工作目錄
    """
    # 透過 python -m mcp_server 啟動時，日誌已由 __main__ 設定，不重複建立 handler
    if not logging.getLogger().handlers:
        setup_logging()
        logger.info("🚀 MCP 伺服器初始化中...")

    cleanup_work_directory()

    yield  # FastAPI 運行中


# ═══════════════════════════════════════════════════════════════════════════════
# FastAPI 應用實例
# ═══════════════════════════════════════════════════════════════════════════════
app = FastAPI(
    title="NATE-MCP-SERVER",
    description="MCP Server with Modular Tool Architecture",
    version=__version__,
    lifespan=lifespan,
)


# ═══════════════════════════════════════════════════════════════════════════════
# HTTP 異常處理
# ═══════════════════════════════════════════════════════════════════════════════


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """自定義 HTTP 異常處理，確保 MCP 協議格式"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "jsonrpc": "2.0" if request.url.path == "/mcp" else None,
            "id": None,
            "error": {"code": -32000 if exc.status_code == 401 else -32001, "message": exc.detail, "status_code": exc.status_code},
        },
    )


@app.exception_handler(MCPError)
async def mcp_exception_handler(request: Request, exc: MCPError):
    """處理 MCPError 異常（未在 mcp_endpoint 內攔截時的備援）"""
    return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"jsonrpc": "2.0", "id": None, "error": {"code": exc.code, "message": exc.message, "data": exc.data}})


# ═══════════════════════════════════════════════════════════════════════════════
# MCP 端點
# ═══════════════════════════════════════════════════════════════════════════════


@app.post("/mcp", response_model=None)
async def mcp_endpoint(req: Request) -> dict | Response:
    """
    MCP 協議端點，受 Bearer Token 保護

    - Tool 處理邏輯位於 tools/ 目錄
    - 此處僅負責路由與協議層處理
    - JSON-RPC 通知（無 id）不回應内容，依 Streamable HTTP 規範回 202 Accepted
    """
    await verify_api_key(req)

    try:
        body = await req.json()
    except Exception:
        logger.warning("請求 JSON 解析失敗")
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error: Invalid JSON"}}

    if not isinstance(body, dict):
        logger.warning("請求內容非 JSON-RPC 物件")
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request: batch requests are not supported"}}

    # 通知（如 notifications/initialized）不帶 id，不應回傳任何内容
    if "id" not in body:
        logger.debug(f"收到通知，不回傳内容: {body.get('method')}")
        return Response(status_code=status.HTTP_202_ACCEPTED)

    req_id = body.get("id")
    method = body.get("method")

    try:
        if method == "initialize":
            result = _handle_initialize()
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = _handle_tools_list()
        elif method == "tools/call":
            result = await _handle_tools_call(body, req)
        elif method == "prompts/list":
            # 本伺服器未實作 prompts；部分客戶端仍會發送 discovery 請求，回空清單避免其記錄錯誤
            result = {"prompts": []}
        elif method == "resources/list":
            result = {"resources": []}
        elif method == "resources/templates/list":
            result = {"resourceTemplates": []}
        else:
            raise MCPError(-32601, f"Method not found: {method}")

        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    except MCPError as e:
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": e.code, "message": e.message, "data": e.data}}
    except ValueError as e:
        logger.exception(f"參數錯誤: {e}")
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32602, "message": f"Invalid params: {str(e)}"}}
    except Exception as e:
        logger.exception(f"處理請求失敗: {e}")
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32603, "message": f"Internal error: {str(e)}"}}


def _handle_initialize() -> dict:
    """處理 initialize method"""
    return {
        "protocolVersion": "2024-11-05",
        "capabilities": {"tools": {}},
        "serverInfo": {"name": "NATE-MCP-SERVER", "version": __version__},
        "instructions": SERVER_INSTRUCTIONS,
    }


def _handle_tools_list() -> dict:
    """
    處理 tools/list method

    Returns:
        dict: 已註冊的 tools 清單
    """
    return {"tools": registry.list_tools()}


async def _handle_tools_call(body: dict, request: Request) -> dict:
    """
    處理 tools/call method - 委派給 registry 執行

    Args:
        body: MCP 請求 body
        request: FastAPI Request 物件

    Returns:
        dict: 執行結果

    Raises:
        MCPError: Tool 不存在或執行失敗
    """
    params = body.get("params", {})
    if not isinstance(params, dict):
        raise MCPError(-32602, "Invalid params: params must be an object")

    tool_name = params.get("name")
    if not isinstance(tool_name, str) or not tool_name:
        raise MCPError(-32602, "Invalid params: name is required")

    args = params.get("arguments", {})
    if not isinstance(args, dict):
        raise MCPError(-32602, "Invalid params: arguments must be an object")

    start_time = time.perf_counter()
    logger.info(f"⏳ [Tool Start] {tool_name} | Args: {str(args)[:200]}{'...' if len(str(args)) > 200 else ''}")

    try:
        exec_result = await registry.execute(tool_name, args, request)
        duration = time.perf_counter() - start_time
        result = format_tool_result(exec_result)

        # 記錄回覆摘要
        status_icon = "✅" if exec_result.success else "❌"
        logger.info(f"{status_icon} [Tool End] {tool_name} | Duration: {duration:.3f}s")
        return result
    except Exception as e:
        duration = time.perf_counter() - start_time
        logger.error(f"🔥 [Tool Error] {tool_name} | Duration: {duration:.3f}s | Error: {str(e)}")
        raise


# ═══════════════════════════════════════════════════════════════════════════════
# 健康檢查端點
# ═══════════════════════════════════════════════════════════════════════════════


@app.get("/mcp")
async def mcp_get(req: Request) -> dict:
    """健康檢查端點，受 Bearer Token 保護。"""
    await verify_api_key(req)

    version_info = {
        "version": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "architecture": platform.machine(),
    }

    return {
        "status": "ok",
        "authenticated": True,
        "protocol": "MCP 2024-11-05",
        "version": __version__,
        "architecture": "modular",
        "features": ["shell_execution"],
        "tools_loaded": registry.get_tool_count(),
        "security": {
            "api_key_required": True,
            "auth_method": "Authorization: Bearer <AUTH_KEY>",
            "rate_limit": "10 failed attempts / 60s per client",
        },
        "python": version_info,
        "config": {"work_directory": str(WORK_DIR), "exec_timeout": MAX_EXECUTION_TIME, "max_output_length": MAX_OUTPUT_LENGTH},
    }


if __name__ == "__main__":  # pragma: no cover
    # 唯一入口為 python -m mcp_server（__main__.py）；此處僅提示使用者，避免出現不顯示 AUTH_KEY 的第二條啟動路徑
    raise SystemExit("請以 `python -m mcp_server` 啟動服務（AUTH_KEY 會於啟動畫面顯示）")
