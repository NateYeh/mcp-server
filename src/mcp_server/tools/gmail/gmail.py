"""Gmail Tool（多帳號支援）

提供 Gmail 郵件與標籤管理功能，支援多帳號切換
"""
import base64
import logging
from typing import Any

from fastapi import Request

from mcp_server.schemas import ExecutionResult
from mcp_server.security import check_gmail_access
from mcp_server.services.gmail_service import gmail_service
from mcp_server.tools.base import registry

logger = logging.getLogger(__name__)


# =========================================================================
# 輔助函數
# =========================================================================


def _extract_email_header(payload: dict, header_name: str) -> str:
    """
    從郵件 payload 提取指定 header

    Args:
        payload: 郵件 payload
        header_name: Header 名稱

    Returns:
        str: Header 值
    """
    for header in payload.get("headers", []):
        if header.get("name", "").lower() == header_name.lower():
            return header.get("value", "")
    return ""


def _extract_body(payload: dict) -> str:
    """
    從郵件 payload 提取正文

    Args:
        payload: 郵件 payload

    Returns:
        str: 郵件正文
    """
    # 檢查是否有直接的 body
    body_data = payload.get("body", {}).get("data")
    if body_data:
        return base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")

    # 遞迴處理 multipart
    parts = payload.get("parts", [])
    for part in parts:
        mime_type = part.get("mimeType", "")
        # 優先返回 text/plain
        if mime_type == "text/plain":
            data = part.get("body", {}).get("data")
            if data:
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
        # 如果是 multipart，繼續遞迴
        elif mime_type.startswith("multipart"):
            result = _extract_body(part)
            if result:
                return result

    # 如果沒有 text/plain，嘗試 text/html
    for part in parts:
        if part.get("mimeType") == "text/html":
            data = part.get("body", {}).get("data")
            if data:
                html = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
                # 簡單移除 HTML 標籤
                import re
                text = re.sub(r"<[^>]+>", "", html)
                return text.strip()

    return "(無正文內容)"


def _format_message_summary(msg: dict) -> str:
    """
    格式化郵件摘要

    Args:
        msg: 郵件資料

    Returns:
        str: 格式化的摘要
    """
    payload = msg.get("payload", {})
    subject = _extract_email_header(payload, "Subject")
    sender = _extract_email_header(payload, "From")
    date = _extract_email_header(payload, "Date")

    snippet = msg.get("snippet", "")[:100]

    return f"""📬 {subject}
   來自: {sender}
   日期: {date}
   摘要: {snippet}..."""


# =========================================================================
# 郵件 Tools
# =========================================================================


@registry.register(
    name="gmail_list",
    description=(
        "列出 Gmail 郵件清單，支援標籤過濾與搜尋語法。"
        "會使用當前 API Key 綁定的 Gmail 帳號。"
        "常用標籤: INBOX, SENT, DRAFT, SPAM, TRASH, UNREAD, STARRED。"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "max_results": {
                "type": "integer",
                "default": 10,
                "minimum": 1,
                "maximum": 100,
                "description": "最多回傳郵件數量，預設 10，最大 100",
            },
            "label_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "標籤 ID 過濾，例如 ['INBOX', 'UNREAD']",
            },
            "query": {
                "type": "string",
                "description": (
                    "Gmail 搜尋語法，例如: "
                    "'is:unread', 'from:boss@company.com', "
                    "'subject:報告', 'has:attachment'"
                ),
            },
        },
        "required": [],
    },
)
async def handle_gmail_list(args: dict[str, Any], request: Request) -> ExecutionResult:
    """處理 gmail_list 請求"""
    try:
        account_id, credentials = check_gmail_access(request)

        max_results = min(args.get("max_results", 10), 100)
        label_ids = args.get("label_ids")
        query = args.get("query", "")

        messages = await gmail_service.list_messages(
            account_id=account_id,
            credentials=credentials,
            max_results=max_results,
            label_ids=label_ids,
            query=query,
        )

        if not messages:
            output = f"📭 [{account_id}] 沒有找到符合條件的郵件"
            return ExecutionResult(success=True, stdout=output, metadata={"count": 0})

        output = f"📬 [{account_id}] 找到 {len(messages)} 封郵件:\n\n"

        # 取得每封郵件的摘要
        for msg in messages:
            try:
                msg_detail = await gmail_service.get_message(
                    account_id=account_id,
                    credentials=credentials,
                    message_id=msg["id"],
                    format_type="metadata",
                )
                output += f"• ID: {msg['id']}\n"
                output += _format_message_summary(msg_detail) + "\n\n"
            except Exception as e:
                logger.warning(f"取得郵件 {msg['id']} 摘要失敗: {e}")
                output += f"• ID: {msg['id']}\n"

        return ExecutionResult(
            success=True,
            stdout=output,
            metadata={"account": account_id, "count": len(messages)},
        )

    except ValueError as e:
        return ExecutionResult(
            success=False, error_type="PermissionError", error_message=str(e)
        )
    except Exception as e:
        logger.exception(f"gmail_list 執行失敗: {e}")
        return ExecutionResult(
            success=False, error_type=type(e).__name__, error_message=str(e)
        )


@registry.register(
    name="gmail_read",
    description="讀取指定郵件的完整內容（含標題、發件人、正文等）",
    input_schema={
        "type": "object",
        "properties": {
            "message_id": {
                "type": "string",
                "description": "郵件 ID（從 gmail_list 取得）",
            },
            "format": {
                "type": "string",
                "enum": ["minimal", "full", "raw"],
                "default": "full",
                "description": "郵件格式：minimal（僅標題）、full（完整內容）、raw（原始數據）",
            },
        },
        "required": ["message_id"],
    },
)
async def handle_gmail_read(args: dict[str, Any], request: Request) -> ExecutionResult:
    """處理 gmail_read 請求"""
    try:
        account_id, credentials = check_gmail_access(request)

        message_id = args.get("message_id")
        if not message_id:
            raise ValueError("必須提供 message_id")

        format_type = args.get("format", "full")

        msg = await gmail_service.get_message(
            account_id=account_id,
            credentials=credentials,
            message_id=message_id,
            format_type=format_type,
        )

        payload = msg.get("payload", {})
        subject = _extract_email_header(payload, "Subject")
        sender = _extract_email_header(payload, "From")
        to = _extract_email_header(payload, "To")
        date = _extract_email_header(payload, "Date")

        output = f"""📧 郵件詳情
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🆔 ID: {message_id}
👤 發件人: {sender}
📧 收件人: {to}
📋 標題: {subject}
📅 日期: {date}
📤 帳號: {account_id}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

        # 解析郵件正文
        if format_type == "full":
            body = _extract_body(payload)
            output += f"\n📝 正文:\n{body}\n"

        # 標籤資訊
        labels = msg.get("labelIds", [])
        if labels:
            output += f"\n🏷️ 標籤: {', '.join(labels)}\n"

        return ExecutionResult(
            success=True,
            stdout=output,
            metadata={"account": account_id, "message_id": message_id},
        )

    except ValueError as e:
        return ExecutionResult(
            success=False, error_type="ValueError", error_message=str(e)
        )
    except Exception as e:
        logger.exception(f"gmail_read 執行失敗: {e}")
        return ExecutionResult(
            success=False, error_type=type(e).__name__, error_message=str(e)
        )


@registry.register(
    name="gmail_send",
    description="發送 Gmail 郵件",
    input_schema={
        "type": "object",
        "properties": {
            "to": {
                "type": "array",
                "items": {"type": "string"},
                "description": "收件者 Email 清單",
            },
            "subject": {"type": "string", "description": "郵件標題"},
            "body": {"type": "string", "description": "郵件內容"},
            "cc": {
                "type": "array",
                "items": {"type": "string"},
                "description": "副本收件者",
            },
            "bcc": {
                "type": "array",
                "items": {"type": "string"},
                "description": "密件副本收件者",
            },
            "html": {
                "type": "boolean",
                "default": False,
                "description": "是否為 HTML 格式",
            },
        },
        "required": ["to", "subject", "body"],
    },
)
async def handle_gmail_send(args: dict[str, Any], request: Request) -> ExecutionResult:
    """處理 gmail_send 請求"""
    try:
        account_id, credentials = check_gmail_access(request)

        to = args.get("to", [])
        subject = args.get("subject", "")
        body = args.get("body", "")

        if not to:
            raise ValueError("必須提供收件者 (to)")
        if not subject:
            raise ValueError("必須提供郵件標題 (subject)")
        if not body:
            raise ValueError("必須提供郵件內容 (body)")

        result = await gmail_service.send_email(
            account_id=account_id,
            credentials=credentials,
            to=to,
            subject=subject,
            body=body,
            cc=args.get("cc"),
            bcc=args.get("bcc"),
            html=args.get("html", False),
        )

        output = f"""✅ 郵件已發送
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📤 帳號: {account_id}
📧 收件者: {', '.join(to)}
📋 標題: {subject}
🆔 Message ID: {result.get('id')}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

        return ExecutionResult(
            success=True,
            stdout=output,
            metadata={"account": account_id, "message_id": result.get("id")},
        )

    except ValueError as e:
        return ExecutionResult(
            success=False, error_type="ValueError", error_message=str(e)
        )
    except Exception as e:
        logger.exception(f"gmail_send 執行失敗: {e}")
        return ExecutionResult(
            success=False, error_type=type(e).__name__, error_message=str(e)
        )


@registry.register(
    name="gmail_modify",
    description=(
        "修改郵件狀態（標籤、已讀、封存、刪除等）。"
        "可同時對多封郵件進行批次操作。"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "message_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "郵件 ID 清單（可單封或多封）",
            },
            "mark_read": {"type": "boolean", "description": "標記為已讀"},
            "mark_unread": {"type": "boolean", "description": "標記為未讀"},
            "archive": {"type": "boolean", "description": "封存（從 INBOX 移除）"},
            "trash": {"type": "boolean", "description": "移至垃圾桶"},
            "star": {"type": "boolean", "description": "加星號"},
            "unstar": {"type": "boolean", "description": "移除星號"},
            "add_labels": {
                "type": "array",
                "items": {"type": "string"},
                "description": "新增標籤 ID 或名稱",
            },
            "remove_labels": {
                "type": "array",
                "items": {"type": "string"},
                "description": "移除標籤 ID 或名稱",
            },
        },
        "required": ["message_ids"],
    },
)
async def handle_gmail_modify(
    args: dict[str, Any], request: Request
) -> ExecutionResult:
    """處理 gmail_modify 請求"""
    try:
        account_id, credentials = check_gmail_access(request)

        message_ids = args.get("message_ids", [])
        if not message_ids:
            raise ValueError("必須提供 message_ids")

        add_labels: list[str] = []
        remove_labels: list[str] = []

        # 便捷操作轉換為標籤
        if args.get("mark_read"):
            remove_labels.append("UNREAD")
        if args.get("mark_unread"):
            add_labels.append("UNREAD")
        if args.get("archive"):
            remove_labels.append("INBOX")
        if args.get("trash"):
            add_labels.append("TRASH")
        if args.get("star"):
            add_labels.append("STARRED")
        if args.get("unstar"):
            remove_labels.append("STARRED")

        # 處理自訂標籤（可能是名稱而非 ID）
        custom_add_labels = args.get("add_labels", [])
        custom_remove_labels = args.get("remove_labels", [])

        for label in custom_add_labels:
            # 系統標籤直接使用
            if label.isupper():
                add_labels.append(label)
            else:
                # 自訂標籤需要查找或建立
                label_id = await gmail_service.find_or_create_label(
                    account_id, credentials, label
                )
                add_labels.append(label_id)

        for label in custom_remove_labels:
            if label.isupper():
                remove_labels.append(label)
            else:
                # 自訂標籤需要查找 ID
                labels = await gmail_service.list_labels(account_id, credentials)
                found_label_id = next(
                    (lbl.get("id") for lbl in labels if lbl.get("name") == label), label
                )
                if found_label_id:
                    remove_labels.append(found_label_id)

        # 執行批次修改
        if len(message_ids) == 1:
            await gmail_service.modify_message(
                account_id=account_id,
                credentials=credentials,
                message_id=message_ids[0],
                add_label_ids=add_labels if add_labels else None,
                remove_label_ids=remove_labels if remove_labels else None,
            )
        else:
            await gmail_service.batch_modify_messages(
                account_id=account_id,
                credentials=credentials,
                message_ids=message_ids,
                add_label_ids=add_labels if add_labels else None,
                remove_label_ids=remove_labels if remove_labels else None,
            )

        actions = []
        if add_labels:
            actions.append(f"新增標籤: {', '.join(add_labels)}")
        if remove_labels:
            actions.append(f"移除標籤: {', '.join(remove_labels)}")

        output = f"""✅ 郵件已修改
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📤 帳號: {account_id}
📧 影響郵件: {len(message_ids)} 封
🔧 操作: {'; '.join(actions) if actions else '無變更'}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

        return ExecutionResult(
            success=True,
            stdout=output,
            metadata={"account": account_id, "affected_count": len(message_ids)},
        )

    except ValueError as e:
        return ExecutionResult(
            success=False, error_type="ValueError", error_message=str(e)
        )
    except Exception as e:
        logger.exception(f"gmail_modify 執行失敗: {e}")
        return ExecutionResult(
            success=False, error_type=type(e).__name__, error_message=str(e)
        )


@registry.register(
    name="gmail_search",
    description=(
        "使用 Gmail 搜尋語法查詢郵件。"
        "常用語法: from:xxx, to:xxx, subject:xxx, is:unread, is:starred, "
        "has:attachment, after:2024/1/1, before:2024/12/31, category:primary"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Gmail 搜尋語法",
            },
            "max_results": {
                "type": "integer",
                "default": 20,
                "minimum": 1,
                "maximum": 100,
                "description": "最多回傳郵件數量",
            },
        },
        "required": ["query"],
    },
)
async def handle_gmail_search(
    args: dict[str, Any], request: Request
) -> ExecutionResult:
    """處理 gmail_search 請求"""
    try:
        account_id, credentials = check_gmail_access(request)

        query = args.get("query", "")
        if not query:
            raise ValueError("必須提供搜尋 query")

        max_results = min(args.get("max_results", 20), 100)

        messages = await gmail_service.list_messages(
            account_id=account_id,
            credentials=credentials,
            max_results=max_results,
            query=query,
        )

        if not messages:
            output = f"📭 [{account_id}] 搜尋 '{query}' 沒有找到符合的郵件"
            return ExecutionResult(success=True, stdout=output, metadata={"count": 0})

        output = f"🔍 [{account_id}] 搜尋 '{query}' 找到 {len(messages)} 封郵件:\n\n"

        for msg in messages:
            try:
                msg_detail = await gmail_service.get_message(
                    account_id=account_id,
                    credentials=credentials,
                    message_id=msg["id"],
                    format_type="metadata",
                )
                output += f"• ID: {msg['id']}\n"
                output += _format_message_summary(msg_detail) + "\n\n"
            except Exception as e:
                logger.warning(f"取得郵件 {msg['id']} 摘要失敗: {e}")
                output += f"• ID: {msg['id']}\n"

        return ExecutionResult(
            success=True,
            stdout=output,
            metadata={"account": account_id, "count": len(messages), "query": query},
        )

    except ValueError as e:
        return ExecutionResult(
            success=False, error_type="ValueError", error_message=str(e)
        )
    except Exception as e:
        logger.exception(f"gmail_search 執行失敗: {e}")
        return ExecutionResult(
            success=False, error_type=type(e).__name__, error_message=str(e)
        )


# =========================================================================
# 標籤 Tools
# =========================================================================


@registry.register(
    name="gmail_labels_list",
    description="列出 Gmail 帳號的所有標籤（含系統標籤與自訂標籤）",
    input_schema={
        "type": "object",
        "properties": {},
        "required": [],
    },
)
async def handle_gmail_labels_list(
    args: dict[str, Any], request: Request
) -> ExecutionResult:
    """處理 gmail_labels_list 請求"""
    try:
        account_id, credentials = check_gmail_access(request)

        labels = await gmail_service.list_labels(account_id, credentials)

        system_labels = []
        user_labels = []

        for label in labels:
            label_type = label.get("type", "user")
            if label_type == "system":
                system_labels.append(label)
            else:
                user_labels.append(label)

        output = f"""🏷️ Gmail 標籤清單 [{account_id}]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📡 系統標籤 ({len(system_labels)} 個):
"""
        label_names = {
            "INBOX": "收件匣",
            "SENT": "已寄出",
            "DRAFT": "草稿",
            "SPAM": "垃圾郵件",
            "TRASH": "垃圾桶",
            "UNREAD": "未讀",
            "STARRED": "已加星號",
            "IMPORTANT": "重要",
            "CHAT": "聊天",
            "CATEGORY_PERSONAL": "社交",
            "CATEGORY_SOCIAL": "社交網路",
            "CATEGORY_PROMOTIONS": "促銷",
            "CATEGORY_UPDATES": "更新",
            "CATEGORY_FORUMS": "論壇",
        }

        for label in system_labels:
            name = label.get("name", "")
            display_name = label_names.get(name, name)
            output += f"  • {name} ({display_name})\n"

        output += f"\n📁 自訂標籤 ({len(user_labels)} 個):\n"

        for label in user_labels:
            name = label.get("name", "")
            label_id = label.get("id", "")
            color = label.get("color", {})
            color_info = f" - {color.get('backgroundColor', '')}" if color else ""
            output += f"  • {name} (ID: {label_id}){color_info}\n"

        output += f"\n共 {len(labels)} 個標籤\n"

        return ExecutionResult(
            success=True,
            stdout=output,
            metadata={"account": account_id, "count": len(labels)},
        )

    except ValueError as e:
        return ExecutionResult(
            success=False, error_type="PermissionError", error_message=str(e)
        )
    except Exception as e:
        logger.exception(f"gmail_labels_list 執行失敗: {e}")
        return ExecutionResult(
            success=False, error_type=type(e).__name__, error_message=str(e)
        )


@registry.register(
    name="gmail_label_create",
    description="建立新的 Gmail 標籤",
    input_schema={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "標籤名稱"},
            "color": {
                "type": "string",
                "description": "標籤顏色 (hex)，例如 #ff5722",
            },
        },
        "required": ["name"],
    },
)
async def handle_gmail_label_create(
    args: dict[str, Any], request: Request
) -> ExecutionResult:
    """處理 gmail_label_create 請求"""
    try:
        account_id, credentials = check_gmail_access(request)

        name = args.get("name", "")
        if not name:
            raise ValueError("必須提供標籤名稱 (name)")

        color = args.get("color")

        result = await gmail_service.create_label(
            account_id=account_id,
            credentials=credentials,
            name=name,
            color=color,
        )

        output = f"""✅ 標籤已建立
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📤 帳號: {account_id}
📝 名稱: {name}
🆔 ID: {result.get('id')}
🎨 顏色: {color or '預設'}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

        return ExecutionResult(
            success=True,
            stdout=output,
            metadata={"account": account_id, "label_id": result.get("id")},
        )

    except ValueError as e:
        return ExecutionResult(
            success=False, error_type="ValueError", error_message=str(e)
        )
    except Exception as e:
        logger.exception(f"gmail_label_create 執行失敗: {e}")
        return ExecutionResult(
            success=False, error_type=type(e).__name__, error_message=str(e)
        )
