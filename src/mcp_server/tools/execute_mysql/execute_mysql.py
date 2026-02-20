"""
execute_mysql Tool

執行 MySQL SQL 指令，支援查詢與資料操作
"""

import asyncio
import logging
from datetime import datetime
from typing import Any

import aiomysql

from mcp_server.config import (
    DANGEROUS_SQL_PATTERNS,
    MYSQL_DATABASE,
    MYSQL_HOST,
    MYSQL_MAX_ROWS,
    MYSQL_PASSWORD,
    MYSQL_PORT,
    MYSQL_USER,
)
from mcp_server.schemas import ExecutionResult
from mcp_server.tools.base import registry

logger = logging.getLogger(__name__)


@registry.register(
    name="execute_mysql",
    description="執行 MySQL SQL 指令，操作資料庫。支援 SELECT, INSERT, UPDATE, DELETE 等 SQL 語法。需先設定 MySQL 連線環境變數。",
    input_schema={
        "type": "object",
        "properties": {
            "sql": {
                "type": "string",
                "description": "要執行的 SQL 指令，例如 'SELECT * FROM users LIMIT 10'",
            },
            "database": {
                "type": "string",
                "description": "目標資料庫名稱（可選，未指定則使用預設資料庫）",
            },
            "timeout": {
                "type": "integer",
                "default": 60,
                "minimum": 1,
                "maximum": 300,
                "description": "執行超時時間（秒），預設 60 秒，最大 300 秒",
            },
        },
        "required": ["sql"],
    },
)
async def handle_execute_mysql(args: dict[str, Any]) -> ExecutionResult:
    """處理 execute_mysql 請求"""
    sql = args.get("sql")

    if not sql or not isinstance(sql, str):
        raise ValueError("必須提供有效的 sql 參數")

    sql = sql.strip()
    if not sql:
        raise ValueError("SQL 語句不可為空")

    database = args.get("database") or MYSQL_DATABASE
    timeout = args.get("timeout", 60)

    if not isinstance(timeout, int) or timeout < 1 or timeout > 300:
        timeout = 60

    logger.info(f"執行 MySQL 查詢 ({len(sql)} 字符)")

    return await execute_mysql_query(sql, database, timeout)


def _check_dangerous_sql(sql: str) -> str | None:
    """
    檢查 SQL 是否包含危險模式。

    Args:
        sql: 要檢查的 SQL 語句

    Returns:
        如果發現危險模式，返回該模式；否則返回 None
    """
    sql_upper = sql.upper()

    for pattern in DANGEROUS_SQL_PATTERNS:
        pattern_upper = pattern.upper()
        if pattern_upper in sql_upper:
            return pattern

    return None


def _format_value(value: Any) -> str:
    """格式化單一值為字串"""
    if value is None:
        return "NULL"
    elif isinstance(value, bytes):
        return f"<BLOB:{len(value)} bytes>"
    elif isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    else:
        return str(value)


def _format_results(columns: list[str], rows: list[dict], max_rows: int) -> str:
    """
    將查詢結果格式化為 Markdown 表格。

    Args:
        columns: 欄位名稱列表
        rows: 資料行列表（DictCursor 格式）
        max_rows: 最大顯示行數

    Returns:
        格式化後的字串
    """
    if not columns or not rows:
        return "無結果"

    # 計算每欄寬度
    col_widths = [len(str(col)) for col in columns]

    # 限制行數
    display_rows = rows[:max_rows]
    truncated = len(rows) > max_rows

    for row in display_rows:
        for i, col in enumerate(columns):
            value = row.get(col)
            formatted = _format_value(value)
            col_widths[i] = max(col_widths[i], len(formatted))

    # 建立表格
    lines = []

    # 表頭
    header = "| " + " | ".join(str(col).ljust(col_widths[i]) for i, col in enumerate(columns)) + " |"
    separator = "|" + "|".join("-" * (w + 2) for w in col_widths) + "|"

    lines.append(header)
    lines.append(separator)

    # 資料行
    for row in display_rows:
        formatted_values = []
        for i, col in enumerate(columns):
            value = row.get(col)
            formatted = _format_value(value)
            formatted_values.append(formatted.ljust(col_widths[i]))
        lines.append("| " + " | ".join(formatted_values) + " |")

    if truncated:
        lines.append(f"\n... 共 {len(rows)} 筆資料，僅顯示前 {max_rows} 筆")

    return "\n".join(lines)


async def execute_mysql_query(
    sql: str,
    database: str | None,
    timeout: int,
) -> ExecutionResult:
    """
    執行 MySQL SQL 指令。

    Args:
        sql: SQL 語句
        database: 資料庫名稱（可選）
        timeout: 執行超時秒數

    Returns:
        ExecutionResult: 執行結果
    """
    start_time = datetime.now()

    # 檢查連線設定
    if not MYSQL_USER or not MYSQL_PASSWORD:
        return ExecutionResult(
            success=False,
            error_type="ConfigurationError",
            error_message="MySQL 連線設定不完整，請設定 MYSQL_USER 和 MYSQL_PASSWORD 環境變數",
            stderr="Missing MySQL credentials",
            returncode=-1,
            execution_time="0.000s",
            metadata={"sql": sql},
        )

    # 安全性檢查
    dangerous_pattern = _check_dangerous_sql(sql)
    if dangerous_pattern:
        logger.warning(f"攔截危險 SQL 指令: {dangerous_pattern}")
        return ExecutionResult(
            success=False,
            error_type="SecurityError",
            error_message=f"SQL 包含危險模式: {dangerous_pattern}，已攔截",
            stderr=f"Dangerous SQL pattern detected: {dangerous_pattern}",
            returncode=-1,
            execution_time="0.000s",
            metadata={"sql": sql, "blocked_pattern": dangerous_pattern},
        )

    conn = None
    try:
        # 建立連線
        conn = await asyncio.wait_for(
            aiomysql.connect(
                host=MYSQL_HOST,
                port=MYSQL_PORT,
                user=MYSQL_USER,
                password=MYSQL_PASSWORD,
                db=database,
                charset="utf8mb4",
                autocommit=True,
            ),
            timeout=timeout,
        )

        async with conn.cursor(aiomysql.DictCursor) as cursor:
            # 執行 SQL
            await asyncio.wait_for(cursor.execute(sql), timeout=timeout)

            # 判斷是否為 SELECT 類查詢
            sql_upper = sql.upper().strip()
            is_query = sql_upper.startswith(("SELECT", "SHOW", "DESC", "DESCRIBE", "EXPLAIN"))

            if is_query:
                rows = await asyncio.wait_for(cursor.fetchall(), timeout=timeout)
                columns = [desc[0] for desc in cursor.description] if cursor.description else []

                execution_time = (datetime.now() - start_time).total_seconds()

                # 格式化結果
                result_text = _format_results(columns, rows, MYSQL_MAX_ROWS)

                return ExecutionResult(
                    success=True,
                    stdout=result_text,
                    execution_time=f"{execution_time:.3f}s",
                    returncode=0,
                    metadata={
                        "sql": sql,
                        "database": database or MYSQL_DATABASE or "default",
                        "rows_returned": len(rows),
                        "columns": len(columns),
                    },
                )
            else:
                # 非 SELECT 操作（INSERT, UPDATE, DELETE 等）
                affected_rows = cursor.rowcount
                execution_time = (datetime.now() - start_time).total_seconds()

                return ExecutionResult(
                    success=True,
                    stdout=f"✅ 執行成功\n📊 影響行數: {affected_rows}",
                    execution_time=f"{execution_time:.3f}s",
                    returncode=0,
                    metadata={
                        "sql": sql,
                        "database": database or MYSQL_DATABASE or "default",
                        "rows_affected": affected_rows,
                    },
                )

    except asyncio.TimeoutError:
        logger.warning(f"MySQL 查詢超時 ({timeout}s)")
        return ExecutionResult(
            success=False,
            error_type="TimeoutError",
            error_message=f"查詢超時 ({timeout}s)",
            stderr=f"Query timeout after {timeout}s",
            returncode=-1,
            execution_time=f">{timeout}s",
            metadata={"sql": sql},
        )

    except aiomysql.Error as e:
        logger.exception(f"MySQL 錯誤: {e}")
        return ExecutionResult(
            success=False,
            error_type="MySQLError",
            error_message=str(e),
            stderr=f"MySQL Error: {type(e).__name__}: {e}",
            returncode=-1,
            execution_time=f"{(datetime.now() - start_time).total_seconds():.3f}s",
            metadata={"sql": sql, "error_code": getattr(e, "args", (None,))[0]},
        )

    except Exception as e:
        logger.exception(f"執行 MySQL 查詢時發生錯誤: {e}")
        return ExecutionResult(
            success=False,
            error_type=type(e).__name__,
            error_message=str(e),
            stderr=str(e),
            returncode=-1,
            execution_time=f"{(datetime.now() - start_time).total_seconds():.3f}s",
            metadata={"sql": sql},
        )

    finally:
        if conn:
            conn.close()
