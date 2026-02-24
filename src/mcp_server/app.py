"""
NATE-MCP-SERVER v4.0.0 (Refactored)

完全模組化重構版本，Tool 定義分散到獨立檔案中
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from mcp_server.config import (
    API_KEYS,
    MAX_EXECUTION_TIME,
    MCP_HOST,
    MCP_PORT,
    REMOTE_BROWSER_ENABLED,
    WORK_DIR,
)
from mcp_server.schemas import MCPError  # noqa: E402
from mcp_server.security import filter_allowed_tools, is_tool_allowed, verify_api_key  # noqa: E402

# ═══════════════════════════════════════════════════════════════════════════════
# 關鍵：載入所有 Tools（透過 tools/__init__.py 自動註冊）
# ═══════════════════════════════════════════════════════════════════════════════
from mcp_server.tools import registry  # noqa: E402
from mcp_server.utils import format_tool_result  # noqa: E402

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Lifespan 管理 - 啟動/關閉 WebSocket Server
# ═══════════════════════════════════════════════════════════════════════════════
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI Lifespan 管理器

    啟動時：初始化日誌、清理暫存區、啟動遠端瀏覽器 WebSocket Server
    關閉時：停止 WebSocket Server
    """
    from mcp_server.base.logging_config import setup_logging
    from mcp_server.config import cleanup_work_directory

    # 初始化日誌系統
    setup_logging()
    logger.info("🚀 MCP 伺服器初始化中...")

    # 清理工作目錄
    cleanup_work_directory()

    # 啟動遠端瀏覽器 WebSocket Server
    if REMOTE_BROWSER_ENABLED:
        try:
            from mcp_server.remote.connection_manager import remote_connection_manager

            logger.info("🔗 正在啟動遠端瀏覽器 WebSocket Server...")
            await remote_connection_manager.start_server()
        except ImportError:
            logger.warning("⚠️ 無法導入遠端連線模組，遠端瀏覽器功能已停用")
        except Exception as e:
            logger.exception(f"❌ 啟動遠端瀏覽器 WebSocket Server 失敗: {e}")

    yield  # FastAPI 運行中

    # 關閉遠端瀏覽器 WebSocket Server
    if REMOTE_BROWSER_ENABLED:
        try:
            from mcp_server.remote.connection_manager import remote_connection_manager

            logger.info("🛑 正在停止遠端瀏覽器 WebSocket Server...")
            await remote_connection_manager.stop_server()
        except Exception as e:
            logger.exception(f"停止遠端瀏覽器 WebSocket Server 時發生錯誤: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# FastAPI 應用實例
# ═══════════════════════════════════════════════════════════════════════════════
app = FastAPI(
    title="NATE-MCP-SERVER",
    description="MCP Server with Modular Tool Architecture (v4.0.0)",
    version="4.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
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
            "error": {
                "code": -32000 if exc.status_code == 401 else -32001,
                "message": exc.detail,
                "status_code": exc.status_code
            }
        }
    )


@app.exception_handler(MCPError)
async def mcp_exception_handler(request: Request, exc: MCPError):
    """處理 MCPError 異常"""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "jsonrpc": "2.0",
            "id": None,
            "error": {
                "code": exc.code,
                "message": exc.message,
                "data": exc.data
            }
        }
    )


# ═══════════════════════════════════════════════════════════════════════════════
# MCP 端點 (v4.0.0 - 精簡版)
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/mcp")
async def mcp_endpoint(req: Request) -> dict:
    """
    MCP 協議端點，受 Bearer Token 保護

    v4.0.0 變更：
    - Tool 處理邏輯已完全移動到 tools/ 目錄
    - 此處僅負責路由與協議層處理
    """
    await verify_api_key(req)

    try:
        body = await req.json()
    except Exception:
        logger.warning("請求 JSON 解析失敗")
        return {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32700, "message": "Parse error: Invalid JSON"}
        }

    req_id = body.get("id")
    method = body.get("method")

    try:
        if method == "initialize":
            result = _handle_initialize()
        elif method == "tools/list":
            result = _handle_tools_list(req)
        elif method == "tools/call":
            result = await _handle_tools_call(body, req)
        else:
            raise MCPError(-32601, f"Method not found: {method}")

        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    except MCPError as e:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": e.code, "message": e.message, "data": e.data}
        }
    except ValueError as e:
        logger.exception(f"參數錯誤: {e}")
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32602, "message": f"Invalid params: {str(e)}"}
        }
    except Exception as e:
        logger.exception(f"處理請求失敗: {e}")
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32603, "message": f"Internal error: {str(e)}"}
        }


def _handle_initialize() -> dict:
    """處理 initialize method"""
    return {
        "protocolVersion": "2024-11-05",
        "capabilities": {
            "tools": {},
            "resources": {},
            "prompts": {}
        },
        "serverInfo": {
            "name": "NATE-MCP-SERVER",
            "version": "4.0.0",
            "architecture": "modular",
            "features": [
                "python_execution",
                "package_management",
                "version_query",
                "shell_execution"
            ]
        }
    }


def _handle_tools_list(request: Request) -> dict:
    """
    處理 tools/list method - 從 registry 取得，並根據權限過濾

    支援 wildcard 模式匹配：
    - ["*"] 表示所有 tools 都允許
    - ["web_*"] 表示所有 web_ 開頭的 tools 都允許

    Args:
        request: FastAPI Request 物件，用於取得權限資訊

    Returns:
        dict: 包含允許使用的 tools 清單
    """
    all_tools = registry.list_tools()
    filtered_tools = filter_allowed_tools(request, all_tools)
    return {"tools": filtered_tools}


async def _handle_tools_call(body: dict, request: Request) -> dict:
    """
    處理 tools/call method - 委派給 registry，並檢查權限

    Args:
        body: MCP 請求 body
        request: FastAPI Request 物件，用於權限檢查

    Returns:
        dict: 執行結果

    Raises:
        MCPError: 權限不足或執行失敗
    """
    params = body.get("params", {})
    tool_name = params.get("name")
    args = params.get("arguments", {})

    # 檢查該 API Key 是否有權限執行此 tool
    if not is_tool_allowed(request, tool_name):
        logger.warning(f"Tool '{tool_name}' 權限不足")
        raise MCPError(
            code=-32603,
            message=f"Permission denied: Tool '{tool_name}' is not allowed for this API Key",
            data={"tool": tool_name}
        )

    exec_result = await registry.execute(tool_name, args, request)
    result = format_tool_result(exec_result)

    # 記錄回覆摘要 (不進行完整序列化以節省效能)
    logger.info(f"✅ Tool {tool_name} 執行完成")

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 健康檢查端點
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/mcp")
async def mcp_get(req: Request) -> dict:
    """健康檢查端點，受 Bearer Token 保護。"""
    await verify_api_key(req)

    # 取得 Python 版本資訊
    import platform
    version_info = {
        "version": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "architecture": platform.machine(),
    }

    py_files = len(list(WORK_DIR.glob("exec_*.py"))) if WORK_DIR.exists() else 0

    return {
        "status": "ok",
        "authenticated": True,
        "protocol": "MCP 2024-11-05",
        "version": "4.0.0",
        "architecture": "modular",
        "features": [
            "python_execution",
            "package_management",
            "version_query",
            "shell_execution"
        ],
        "tools_loaded": registry.get_tool_count(),
        "security": {
            "api_key_required": bool(API_KEYS),
            "api_keys_count": len(API_KEYS) if API_KEYS else 0,
            "auth_method": "Authorization: Bearer <token>" if API_KEYS else "None (Development Mode)"
        },
        "python": version_info,
        "config": {
            "work_directory": str(WORK_DIR.absolute()),
            "python_timeout": MAX_EXECUTION_TIME,
            "max_output_length": 100000
        },
        "stats": {"temp_python_files": py_files}
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 啟動入口
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn

    logger.info(f"🔧 已載入 {registry.get_tool_count()} 個 Tools")
    logger.info(f"📂 預計工作目錄: {WORK_DIR.absolute()}")

    uvicorn.run(app, host=MCP_HOST, port=MCP_PORT)
