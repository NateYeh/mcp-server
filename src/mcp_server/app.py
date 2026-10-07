"""
NATE-MCP-SERVER v4.0.0

MCP (Model Context Protocol) Server：模組化 Tool 架構，Tool 定義分散到獨立檔案中。
"""

import logging
import platform
import time
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from mcp_server.base.logging_config import setup_logging
from mcp_server.config import (
    MAX_EXECUTION_TIME,
    MAX_OUTPUT_LENGTH,
    MCP_HOST,
    MCP_PORT,
    WORK_DIR,
    cleanup_work_directory,
)
from mcp_server.schemas import MCPError
from mcp_server.security import verify_api_key

# ═══════════════════════════════════════════════════════════════════════════════
# 關鍵：載入所有 Tools（透過 tools/__init__.py 自動註冊）
# ═══════════════════════════════════════════════════════════════════════════════
from mcp_server.tools import registry
from mcp_server.utils import format_tool_result

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Lifespan 管理
# ═══════════════════════════════════════════════════════════════════════════════
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI Lifespan 管理器

    啟動時：初始化日誌、清理工作目錄
    """
    # 初始化日誌系統
    setup_logging()
    logger.info("🚀 MCP 伺服器初始化中...")

    # 清理工作目錄
    cleanup_work_directory()

    yield  # FastAPI 運行中


# ═══════════════════════════════════════════════════════════════════════════════
# FastAPI 應用實例
# ═══════════════════════════════════════════════════════════════════════════════
app = FastAPI(
    title="NATE-MCP-SERVER",
    description="MCP Server with Modular Tool Architecture (v4.0.0)",
    version="4.0.0",
    lifespan=lifespan,
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

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
    """處理 MCPError 異常"""
    return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"jsonrpc": "2.0", "id": None, "error": {"code": exc.code, "message": exc.message, "data": exc.data}})


# ═══════════════════════════════════════════════════════════════════════════════
# MCP 端點
# ═══════════════════════════════════════════════════════════════════════════════


@app.post("/mcp")
async def mcp_endpoint(req: Request) -> dict:
    """
    MCP 協議端點，受 Bearer Token 保護

    - Tool 處理邏輯位於 tools/ 目錄
    - 此處僅負責路由與協議層處理
    """
    await verify_api_key(req)

    try:
        body = await req.json()
    except Exception:
        logger.warning("請求 JSON 解析失敗")
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error: Invalid JSON"}}

    req_id = body.get("id")
    method = body.get("method")

    try:
        if method == "initialize":
            result = _handle_initialize()
        elif method == "tools/list":
            result = _handle_tools_list()
        elif method == "tools/call":
            result = await _handle_tools_call(body, req)
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
        "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
        "serverInfo": {
            "name": "NATE-MCP-SERVER",
            "version": "4.0.0",
            "architecture": "modular",
            "features": ["shell_execution"],
        },
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
    tool_name = params.get("name")
    args = params.get("arguments", {})

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
        raise e


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
        "version": "4.0.0",
        "architecture": "modular",
        "features": ["shell_execution"],
        "tools_loaded": registry.get_tool_count(),
        "security": {
            "api_key_required": True,
            "auth_method": "Authorization: Bearer <AUTH_KEY>",
        },
        "python": version_info,
        "config": {"work_directory": str(WORK_DIR.absolute()), "exec_timeout": MAX_EXECUTION_TIME, "max_output_length": MAX_OUTPUT_LENGTH},
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 啟動入口
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logger.info(f"🔧 已載入 {registry.get_tool_count()} 個 Tools")
    logger.info(f"📂 預計工作目錄: {WORK_DIR.absolute()}")

    uvicorn.run(app, host=MCP_HOST, port=MCP_PORT)
