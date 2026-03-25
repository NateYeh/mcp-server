"""
輔助函數工具箱

包含通用工具函數與格式化功能
"""

import logging
from typing import Any

from mcp_server.tools.schemas import ExecutionResult

logger = logging.getLogger(__name__)


def format_tool_result(result: ExecutionResult) -> dict[str, Any]:
    """
    格式化 ExecutionResult 為 MCP 回應格式

    Args:
        result: 執行結果

    Returns:
        MCP 格式的字典
    """
    text_output = result.to_text_output()
    response = {"content": [{"type": "text", "text": text_output}], "isError": not result.success}
    if result.metadata:
        response["metadata"] = result.metadata

    # 記錄回覆長度
    logger.info(
        f"📊 MCP 回覆格式化完成 | "
        f"文本長度: {len(text_output):,} 字符 | "
        f"成功: {result.success} | "
        f"Tool: {result.metadata.get('command', result.metadata.get('file_path', 'unknown'))}"
    )

    return response


def truncate_string(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """截斷過長的字串"""
    if len(text) > max_length:
        return text[:max_length] + suffix
    return text
