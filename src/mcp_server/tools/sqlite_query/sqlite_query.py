"""
sqlite_query Tool

讀取 SQLite .db 檔案，執行 SQL 查詢與操作。
支援 SELECT, INSERT, UPDATE, DELETE 等操作。
"""

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from mcp_server.schemas import ExecutionResult
from mcp_server.tools.base import registry

logger = logging.getLogger(__name__)

# 預設資料庫路徑（可透過環境變數覆蓋）
DEFAULT_DB_PATH = "/mnt/public/Develop/Projects/external_projects/gpt-load/data/gpt-load.db"

# 安全限制
MAX_RESULTS = 500  # 單次查詢最大返回筆數
MAX_SQL_LENGTH = 10000  # SQL 語句最大長度
FORBIDDEN_KEYWORDS = [  # 禁止的危險操作（可根據需求調整）
    # "DROP", "ALTER", "CREATE", -- 視需求開放
]


def validate_sql(sql: str) -> tuple[bool, str]:
    """
    基本的 SQL 安全檢查
    
    Returns:
        (is_valid, error_message)
    """
    if not sql or not isinstance(sql, str):
        return False, "SQL 語句不能為空"
    
    sql_upper = sql.upper().strip()
    
    if len(sql) > MAX_SQL_LENGTH:
        return False, f"SQL 語句過長（超過 {MAX_SQL_LENGTH} 字元）"
    
    # 檢查禁止的關鍵字
    for keyword in FORBIDDEN_KEYWORDS:
        if keyword in sql_upper:
            return False, f"禁止執行包含 {keyword} 的操作"
    
    return True, ""


def format_value(value: Any) -> str:
    """格式化單一值用於顯示"""
    if value is None:
        return "NULL"
    if isinstance(value, bytes):
        return f"<BLOB {len(value)} bytes>"
    if isinstance(value, str) and len(value) > 200:
        return value[:200] + "...[truncated]"
    return str(value)


def format_row(row: tuple, columns: list[str]) -> str:
    """格式化單行資料"""
    parts = []
    for col, val in zip(columns, row):
        parts.append(f"{col}={format_value(val)}")
    return " | ".join(parts)


def execute_sql_internal(db_path: str, sql: str, params: list[Any] | None = None) -> ExecutionResult:
    """
    內部執行 SQL 的函數
    
    Args:
        db_path: 資料庫檔案路徑
        sql: SQL 語句
        params: 參數列表（用於參數化查詢）
    
    Returns:
        ExecutionResult
    """
    start_time = datetime.now()
    
    # 驗證 SQL
    is_valid, error_msg = validate_sql(sql)
    if not is_valid:
        return ExecutionResult(
            success=False,
            error_type="ValidationError",
            error_message=error_msg,
            execution_time="0.000s",
        )
    
    # 檢查資料庫檔案
    db_file = Path(db_path)
    if not db_file.exists():
        return ExecutionResult(
            success=False,
            error_type="FileNotFoundError",
            error_message=f"資料庫檔案不存在: {db_path}",
            execution_time="0.000s",
        )
    
    try:
        conn = sqlite3.connect(str(db_file))
        conn.row_factory = sqlite3.Row  # 使用 Row 工廠便於取得欄位名
        cursor = conn.cursor()
        
        # 啟用外鍵約束
        cursor.execute("PRAGMA foreign_keys = ON")
        
        # 執行 SQL
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)
        
        # 判斷操作類型
        sql_upper = sql.upper().strip()
        is_query = sql_upper.startswith(("SELECT", "PRAGMA", "EXPLAIN", "WITH"))
        
        if is_query:
            # 查詢操作：返回結果
            rows = cursor.fetchmany(MAX_RESULTS + 1)  # 多取一筆用於判斷是否截斷
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            
            truncated = len(rows) > MAX_RESULTS
            if truncated:
                rows = rows[:MAX_RESULTS]
            
            # 格式化輸出
            output_lines = []
            output_lines.append(f"📊 查詢結果: {len(rows)} 筆{' (已截斷)' if truncated else ''}")
            output_lines.append(f"📋 欄位: {', '.join(columns)}")
            output_lines.append("-" * 80)
            
            for row in rows:
                row_dict = dict(row)
                formatted = " | ".join(f"{k}={format_value(v)}" for k, v in row_dict.items())
                output_lines.append(formatted)
            
            # 如果是 PRAGMA，也返回結構化資料
            if sql_upper.startswith("PRAGMA"):
                output_lines.append("\n📝 結構化資料:")
                for row in rows:
                    output_lines.append(str(dict(row)))
            
            stdout = "\n".join(output_lines)
            conn.close()
            
            execution_time = (datetime.now() - start_time).total_seconds()
            return ExecutionResult(
                success=True,
                stdout=stdout,
                returncode=0,
                execution_time=f"{execution_time:.3f}s",
                metadata={
                    "db_path": db_path,
                    "row_count": len(rows),
                    "truncated": truncated,
                    "columns": columns,
                },
            )
        else:
            # 寫入操作：返回影響筆數
            affected_rows = cursor.rowcount
            conn.commit()
            conn.close()
            
            execution_time = (datetime.now() - start_time).total_seconds()
            
            # 判斷操作類型
            if "INSERT" in sql_upper:
                op_type = "插入"
            elif "UPDATE" in sql_upper:
                op_type = "更新"
            elif "DELETE" in sql_upper:
                op_type = "刪除"
            else:
                op_type = "執行"
            
            stdout = f"✅ {op_type}成功: 影響 {affected_rows} 筆資料"
            
            return ExecutionResult(
                success=True,
                stdout=stdout,
                returncode=0,
                execution_time=f"{execution_time:.3f}s",
                metadata={
                    "db_path": db_path,
                    "affected_rows": affected_rows,
                },
            )
    
    except sqlite3.Error as e:
        logger.exception(f"SQLite 錯誤: {e}")
        return ExecutionResult(
            success=False,
            error_type="SQLiteError",
            error_message=str(e),
            stderr=str(e),
            returncode=1,
            execution_time=f"{(datetime.now() - start_time).total_seconds():.3f}s",
            metadata={"db_path": db_path},
        )
    except Exception as e:
        logger.exception(f"執行 SQL 時發生錯誤: {e}")
        return ExecutionResult(
            success=False,
            error_type=type(e).__name__,
            error_message=str(e),
            stderr=str(e),
            returncode=1,
            execution_time=f"{(datetime.now() - start_time).total_seconds():.3f}s",
            metadata={"db_path": db_path},
        )


@registry.register(
    name="sqlite_query",
    description="執行 SQLite SQL 指令，操作 .db 資料庫檔案。支援 SELECT, INSERT, UPDATE, DELETE 等 SQL 語法。預設使用 gpt-load.db。",
    input_schema={
        "type": "object",
        "properties": {
            "sql": {
                "type": "string",
                "description": "要執行的 SQL 指令，例如 'SELECT * FROM api_keys LIMIT 10'",
            },
            "database": {
                "type": "string",
                "description": "資料庫檔案路徑（可選，預設使用 gpt-load.db）",
                "default": DEFAULT_DB_PATH,
            },
            "params": {
                "type": "array",
                "description": "SQL 參數列表（用於參數化查詢，防止 SQL 注入）",
                "items": {"type": ["string", "number", "boolean", "null"]},
            },
        },
        "required": ["sql"],
    },
)
async def handle_sqlite_query(args: dict[str, Any]) -> ExecutionResult:
    """處理 sqlite_query 請求"""
    sql = args.get("sql")
    
    if not sql or not isinstance(sql, str):
        raise ValueError("必須提供有效的 sql 參數")
    
    db_path = args.get("database", DEFAULT_DB_PATH)
    params = args.get("params")
    
    logger.info(f"執行 SQLite 查詢: {sql[:100]}... (db={db_path})")
    
    return execute_sql_internal(db_path, sql, params)


@registry.register(
    name="sqlite_tables",
    description="列出 SQLite 資料庫中的所有表及其結構。",
    input_schema={
        "type": "object",
        "properties": {
            "database": {
                "type": "string",
                "description": "資料庫檔案路徑（可選，預設使用 gpt-load.db）",
                "default": DEFAULT_DB_PATH,
            },
        },
        "required": [],
    },
)
async def handle_sqlite_tables(args: dict[str, Any]) -> ExecutionResult:
    """列出資料庫中的所有表"""
    db_path = args.get("database", DEFAULT_DB_PATH)
    
    logger.info(f"列出資料庫表: {db_path}")
    
    # 驗證檔案
    db_file = Path(db_path)
    if not db_file.exists():
        return ExecutionResult(
            success=False,
            error_type="FileNotFoundError",
            error_message=f"資料庫檔案不存在: {db_path}",
            execution_time="0.000s",
        )
    
    start_time = datetime.now()
    
    try:
        conn = sqlite3.connect(str(db_file))
        cursor = conn.cursor()
        
        # 取得所有表
        cursor.execute("""
            SELECT name, type 
            FROM sqlite_master 
            WHERE type IN ('table', 'view') 
            ORDER BY type, name
        """)
        tables = cursor.fetchall()
        
        output_lines = []
        output_lines.append(f"📁 資料庫: {db_path}")
        output_lines.append(f"📊 大小: {db_file.stat().st_size / 1024:.2f} KB")
        output_lines.append(f"📋 共 {len(tables)} 個表/視圖\n")
        
        table_info = []
        
        for table_name, table_type in tables:
            if table_name.startswith("sqlite_"):
                continue  # 跳過系統表
            
            # 取得表結構
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = cursor.fetchall()
            
            # 取得筆數
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cursor.fetchone()[0]
            
            output_lines.append(f"{'📌' if table_type == 'table' else '👁️'} {table_name}")
            output_lines.append(f"   類型: {table_type}")
            output_lines.append(f"   筆數: {count:,}")
            output_lines.append(f"   欄位: {len(columns)}")
            
            col_info = []
            for col in columns:
                col_name = col[1]
                col_type = col[2]
                col_pk = " 🔑" if col[5] else ""
                col_info.append(f"{col_name} ({col_type}){col_pk}")
            
            output_lines.append(f"   結構: {', '.join(col_info)}")
            output_lines.append("")
            
            table_info.append({
                "name": table_name,
                "type": table_type,
                "row_count": count,
                "columns": [{"name": c[1], "type": c[2], "pk": bool(c[5])} for c in columns],
            })
        
        conn.close()
        
        execution_time = (datetime.now() - start_time).total_seconds()
        
        return ExecutionResult(
            success=True,
            stdout="\n".join(output_lines),
            returncode=0,
            execution_time=f"{execution_time:.3f}s",
            metadata={
                "db_path": db_path,
                "table_count": len(tables),
                "tables": table_info,
            },
        )
    
    except Exception as e:
        logger.exception(f"列出資料庫表時發生錯誤: {e}")
        return ExecutionResult(
            success=False,
            error_type=type(e).__name__,
            error_message=str(e),
            stderr=str(e),
            returncode=1,
            execution_time=f"{(datetime.now() - start_time).total_seconds():.3f}s",
            metadata={"db_path": db_path},
        )