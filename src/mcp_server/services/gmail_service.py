"""Gmail API 服務層

封裝 Gmail API 操作，支援多帳號管理
"""

import base64
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import httpx

from mcp_server.config import GMAIL_ACCOUNTS

logger = logging.getLogger(__name__)


class GmailService:
    """Gmail API 服務類別"""

    TOKEN_URL = "https://oauth2.googleapis.com/token"
    GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1"

    def __init__(self) -> None:
        """初始化服務實例"""
        pass

    async def _get_access_token(self, credentials: dict[str, str]) -> str:
        """
        使用 refresh_token 取得 access_token

        Args:
            credentials: 包含 client_id, client_secret, refresh_token 的憑證

        Returns:
            str: access_token

        Raises:
            ValueError: 憑證無效或取得 token 失敗
        """
        required_keys = ["client_id", "client_secret", "refresh_token"]
        for key in required_keys:
            if not credentials.get(key):
                raise ValueError(f"缺少必要的憑證: {key}")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.TOKEN_URL,
                data={
                    "client_id": credentials["client_id"],
                    "client_secret": credentials["client_secret"],
                    "refresh_token": credentials["refresh_token"],
                    "grant_type": "refresh_token",
                },
                timeout=30.0,
            )

            if response.status_code != 200:
                raise ValueError(f"取得 access_token 失敗: {response.text}")

            data = response.json()
            return data["access_token"]

    def _get_credentials(self, account_id: str) -> dict[str, str]:
        """
        取得指定帳號的憑證

        Args:
            account_id: Gmail 帳號 ID

        Returns:
            dict: 憑證資訊

        Raises:
            ValueError: 帳號不存在
        """
        if account_id not in GMAIL_ACCOUNTS:
            available = list(GMAIL_ACCOUNTS.keys())
            raise ValueError(f"Gmail 帳號不存在: {account_id}，可用帳號: {available}")

        return GMAIL_ACCOUNTS[account_id]

    async def _api_request(
        self,
        credentials: dict[str, str],
        method: str,
        endpoint: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        執行 Gmail API 請求

        Args:
            credentials: 帳號憑證
            method: HTTP 方法
            endpoint: API 端點（不含 base URL）
            **kwargs: 其他請求參數

        Returns:
            dict: API 回應

        Raises:
            Exception: API 請求失敗
        """
        access_token = await self._get_access_token(credentials)

        async with httpx.AsyncClient() as client:
            url = f"{self.GMAIL_API_BASE}{endpoint}"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }

            response = await client.request(
                method=method,
                url=url,
                headers=headers,
                timeout=60.0,
                **kwargs,
            )

            if response.status_code >= 400:
                error_msg = f"Gmail API 錯誤 ({response.status_code}): {response.text}"
                logger.error(error_msg)
                raise Exception(error_msg)

            if response.status_code == 204:
                return {}
            return response.json()

    async def list_messages(
        self,
        account_id: str,
        credentials: dict[str, str],
        max_results: int = 10,
        label_ids: list[str] | None = None,
        query: str = "",
    ) -> list[dict[str, Any]]:
        """
        列出郵件

        Args:
            account_id: Gmail 帳號 ID
            credentials: 帳號憑證
            max_results: 最大結果數
            label_ids: 標籤 ID 篩選
            query: 搜尋查詢

        Returns:
            list: 郵件列表
        """
        params: dict[str, Any] = {"maxResults": max_results}
        if label_ids:
            params["labelIds"] = ",".join(label_ids)
        if query:
            params["q"] = query

        response = await self._api_request(
            credentials=credentials,
            method="GET",
            endpoint="/users/me/messages",
            params=params,
        )

        return response.get("messages", [])

    async def get_message(
        self,
        account_id: str,
        credentials: dict[str, str],
        message_id: str,
        format_type: str = "full",
    ) -> dict[str, Any]:
        """
        取得郵件內容

        Args:
            account_id: Gmail 帳號 ID
            credentials: 帳號憑證
            message_id: 郵件 ID
            format_type: 格式類型 (full, metadata, minimal, raw)

        Returns:
            dict: 郵件內容
        """
        return await self._api_request(
            credentials=credentials,
            method="GET",
            endpoint=f"/users/me/messages/{message_id}",
            params={"format": format_type},
        )

    async def send_email(
        self,
        account_id: str,
        credentials: dict[str, str],
        to: str,
        subject: str,
        body: str,
        cc: str | None = None,
        bcc: str | None = None,
        html: bool = False,
    ) -> dict[str, Any]:
        """
        發送郵件

        Args:
            account_id: Gmail 帳號 ID
            credentials: 帳號憑證
            to: 收件人
            subject: 主旨
            body: 內容
            cc: 副本
            bcc: 密件副本
            html: 是否為 HTML 格式

        Returns:
            dict: 發送結果
        """
        # 建立 MIME 郵件
        message = MIMEMultipart()
        message["to"] = to
        message["subject"] = subject
        if cc:
            message["cc"] = cc
        if bcc:
            message["bcc"] = bcc

        # 添加郵件內容
        content_type = "html" if html else "plain"
        message.attach(MIMEText(body, content_type))

        # 編碼為 base64
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

        return await self._api_request(
            credentials=credentials,
            method="POST",
            endpoint="/users/me/messages/send",
            json={"raw": raw_message},
        )

    async def list_labels(
        self,
        account_id: str,
        credentials: dict[str, str],
    ) -> list[dict[str, Any]]:
        """
        列出所有標籤

        Args:
            account_id: Gmail 帳號 ID
            credentials: 帳號憑證

        Returns:
            list: 標籤列表
        """
        response = await self._api_request(
            credentials=credentials,
            method="GET",
            endpoint="/users/me/labels",
        )
        return response.get("labels", [])

    async def create_label(
        self,
        account_id: str,
        credentials: dict[str, str],
        name: str,
        color: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        建立標籤

        Args:
            account_id: Gmail 帳號 ID
            credentials: 帳號憑證
            name: 標籤名稱
            color: 標籤顏色設定 {"textColor": ..., "backgroundColor": ...}

        Returns:
            dict: 建立的標籤
        """
        label_data: dict[str, Any] = {
            "name": name,
            "labelListVisibility": "labelShow",
            "messageListVisibility": "show",
        }
        if color:
            label_data["color"] = color

        return await self._api_request(
            credentials=credentials,
            method="POST",
            endpoint="/users/me/labels",
            json=label_data,
        )

    async def find_or_create_label(
        self,
        account_id: str,
        credentials: dict[str, str],
        name: str,
    ) -> str:
        """
        查找或建立標籤

        Args:
            account_id: Gmail 帳號 ID
            credentials: 帳號憑證
            name: 標籤名稱

        Returns:
            str: 標籤 ID
        """
        # 先查找現有標籤
        labels = await self.list_labels(account_id, credentials)
        for label in labels:
            if label.get("name", "").lower() == name.lower():
                return label["id"]

        # 建立新標籤
        result = await self.create_label(account_id, credentials, name)
        return result["id"]

    async def modify_message(
        self,
        account_id: str,
        credentials: dict[str, str],
        message_id: str,
        add_label_ids: list[str] | None = None,
        remove_label_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        修改郵件標籤

        Args:
            account_id: Gmail 帳號 ID
            credentials: 帳號憑證
            message_id: 郵件 ID
            add_label_ids: 要新增的標籤 ID 列表
            remove_label_ids: 要移除的標籤 ID 列表

        Returns:
            dict: 修改結果
        """
        body: dict[str, list[str]] = {}
        if add_label_ids:
            body["addLabelIds"] = add_label_ids
        if remove_label_ids:
            body["removeLabelIds"] = remove_label_ids

        return await self._api_request(
            credentials=credentials,
            method="POST",
            endpoint=f"/users/me/messages/{message_id}/modify",
            json=body,
        )

    async def batch_modify_messages(
        self,
        account_id: str,
        credentials: dict[str, str],
        message_ids: list[str],
        add_label_ids: list[str] | None = None,
        remove_label_ids: list[str] | None = None,
    ) -> None:
        """
        批次修改郵件標籤

        Args:
            account_id: Gmail 帳號 ID
            credentials: 帳號憑證
            message_ids: 郵件 ID 列表
            add_label_ids: 要新增的標籤 ID 列表
            remove_label_ids: 要移除的標籤 ID 列表
        """
        body: dict[str, list[str]] = {"ids": message_ids}
        if add_label_ids:
            body["addLabelIds"] = add_label_ids
        if remove_label_ids:
            body["removeLabelIds"] = remove_label_ids

        await self._api_request(
            credentials=credentials,
            method="POST",
            endpoint="/users/me/messages/batchModify",
            json=body,
        )


# 全域服務實例
gmail_service = GmailService()
