"""
Gemini API 用戶端模組

提供 Gemini 和 Ollama API 的統一介面。
"""

import base64
import json
import logging
import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from mcp_server.base.data_structures import AIConfig

logger = logging.getLogger(__name__)


class GeminiAPIClient:
    """Gemini API 用戶端"""

    DEFAULT_API_VERSION = "v1beta"

    def __init__(self, api_keys: list[dict] | None = None):
        """初始化 API 用戶端。

        Args:
            api_keys: Gemini API Keys 列表，格式為 [{"key": "xxx", "mail": "yyy"}, ...]
        """
        self._api_keys = api_keys or []
        self._current_key_index = 0
        self._pay_key = ""
        self._api_base_url = ""
        self._proxy_url = ""
        self._ollama_proxy_url = ""

    def configure(
        self,
        pay_key: str = "",
        api_base_url: str = "https://generativelanguage.googleapis.com",
        proxy_url: str = "",
        ollama_proxy_url: str = "",
    ) -> None:
        """設定 API 配置"""
        self._pay_key = pay_key
        self._api_base_url = api_base_url
        self._proxy_url = proxy_url
        self._ollama_proxy_url = ollama_proxy_url

    def _get_api_key(self) -> str:
        """取得目前的 API Key"""
        if self._api_keys:
            idx = self._current_key_index % len(self._api_keys)
            return self._api_keys[idx].get("key", "")
        return ""

    def _rotate_key(self) -> None:
        """輪換 API Key"""
        if len(self._api_keys) > 1:
            self._current_key_index = (self._current_key_index + 1) % len(self._api_keys)

    def generate_content(
        self,
        ai_config: AIConfig,
        chat_data: dict[str, Any],
        is_pay: bool = False,
    ) -> dict[str, Any]:
        """發送生成內容請求"""
        model_name = ai_config.model_name
        headers = {"Content-Type": "application/json"}

        if ai_config.provider == "ollama":
            url = f"{self._ollama_proxy_url}/api/chat"
            headers["Authorization"] = f"Bearer {ai_config.api_key}"
        else:
            if is_pay and self._pay_key:
                url = f"{self._api_base_url}/{self.DEFAULT_API_VERSION}/models/{model_name}:generateContent"
                headers["X-goog-api-key"] = self._pay_key
            else:
                api_key = ai_config.api_key or self._get_api_key()
                if self._proxy_url:
                    url = f"{self._proxy_url}/{self.DEFAULT_API_VERSION}/models/{model_name}:generateContent"
                    headers["X-goog-api-key"] = api_key
                else:
                    url = f"{self._api_base_url}/{self.DEFAULT_API_VERSION}/models/{model_name}:generateContent"
                    headers["X-goog-api-key"] = api_key

        try:
            with requests.Session() as session:
                response = session.post(url, headers=headers, json=chat_data, timeout=60)
                response.raise_for_status()
                return response.json()
        except requests.exceptions.RequestException:
            logger.exception("API 請求失敗")
            return {}
        except Exception:
            logger.exception("發送 API 請求時發生未知錯誤")
            return {}

    def get_model_list(self) -> dict[str, Any]:
        """取得模型列表"""
        key = self._get_api_key()
        headers = {"Content-Type": "application/json"}

        # Ollama models
        if self._ollama_proxy_url:
            try:
                url = f"{self._ollama_proxy_url}/api/tags"
                headers["Authorization"] = f"Bearer {key}"
                with requests.Session() as session:
                    response = session.get(url, headers=headers, timeout=60)
                    response.raise_for_status()
                    return {"ollama": response.json()}
            except Exception:
                logger.exception("取得 Ollama 模型列表失敗")

        # Gemini models
        if self._proxy_url and key:
            try:
                url = f"{self._proxy_url}/{self.DEFAULT_API_VERSION}/models"
                headers["X-goog-api-key"] = key
                with requests.Session() as session:
                    response = session.get(url, headers=headers, timeout=60)
                    response.raise_for_status()
                    return {"gemini": response.json()}
            except Exception:
                logger.exception("取得 Gemini 模型列表失敗")

        return {}


# ═══════════════════════════════════════════════════════════════════════════════
# 全域用戶端實例（需要由外部配置）
# ═══════════════════════════════════════════════════════════════════════════════
_default_client: GeminiAPIClient | None = None


def get_client() -> GeminiAPIClient:
    """取得全域 API 用戶端實例"""
    global _default_client
    if _default_client is None:
        _default_client = GeminiAPIClient()
    return _default_client


def configure_client(
    api_keys: list[dict] | None = None,
    pay_key: str = "",
    api_base_url: str = "https://generativelanguage.googleapis.com",
    proxy_url: str = "",
    ollama_proxy_url: str = "",
) -> None:
    """配置全域 API 用戶端"""
    client = get_client()
    client.configure(pay_key, api_base_url, proxy_url, ollama_proxy_url)
    if api_keys:
        client._api_keys = api_keys


# ═══════════════════════════════════════════════════════════════════════════════
# 便捷函式（向後相容）
# ═══════════════════════════════════════════════════════════════════════════════

def _generate_content_gemini(
    ai_config: AIConfig,
    chat_data: dict[str, Any] | None = None,
    role: str = "user",
    text: str = "",
    system_instruction: str = "",
    image_path_list: list[str] | None = None,
) -> dict[str, Any]:
    """產生符合 Gemini API 要求的內容請求結構"""
    if chat_data is None:
        chat_data = {
            "contents": [],
            "safetySettings": [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ],
            "generationConfig": {},
            "systemInstruction": {"parts": []},
        }
        generation_config = {
            "candidateCount": 1,
            "maxOutputTokens": 65536,
            "temperature": ai_config.temperature,
            "topP": ai_config.top_p,
            "topK": ai_config.top_k,
        }
        chat_data["generationConfig"] = generation_config

    parts: list[dict[str, Any]] = []

    # 處理圖片
    if image_path_list:
        for image_path_str in image_path_list:
            try:
                image_path = Path(image_path_str)
                if not image_path.is_file():
                    logger.warning(f"圖片檔案不存在，已略過：{image_path}")
                    continue

                mime_type, _ = mimetypes.guess_type(image_path)
                if not mime_type or not mime_type.startswith("image"):
                    logger.warning(f"無法識別的圖片 MIME 類型，已略過：{mime_type}")
                    continue

                image_bytes = image_path.read_bytes()
                encoded_image = base64.b64encode(image_bytes).decode("utf-8")
                parts.append({"inlineData": {"mimeType": mime_type, "data": encoded_image}})
            except Exception:
                logger.exception(f"處理圖片時發生錯誤：{image_path_str}")

    # 處理文字
    if text:
        parts.append({"text": text})

    if parts:
        chat_data["contents"].append({"role": role, "parts": parts})

    if system_instruction:
        chat_data["systemInstruction"]["parts"].append({"text": system_instruction})
        chat_data["systemInstruction"]["role"] = "user"

    return chat_data


def _generate_content_ollama(
    ai_config: AIConfig,
    chat_data: dict[str, Any] | None = None,
    role: str = "user",
    text: str = "",
    system_instruction: str = "",
    image_path_list: list[str] | None = None,
) -> dict[str, Any]:
    """產生符合 Ollama API 要求的內容請求結構"""
    if chat_data is None:
        chat_data = {"messages": [], "model": ai_config.model_name, "stream": False}

    if system_instruction:
        chat_data["messages"].append({"role": "system", "content": system_instruction})

    if text or image_path_list:
        message: dict[str, Any] = {"role": role, "content": text}

        if image_path_list:
            images_base64: list[str] = []
            for image_path_str in image_path_list:
                try:
                    image_path = Path(image_path_str)
                    if not image_path.is_file():
                        logger.warning(f"圖片檔案不存在，已略過：{image_path}")
                        continue

                    mime_type, _ = mimetypes.guess_type(image_path)
                    if not mime_type or not mime_type.startswith("image"):
                        continue

                    image_bytes = image_path.read_bytes()
                    encoded_image = base64.b64encode(image_bytes).decode("utf-8")
                    images_base64.append(encoded_image)
                except Exception:
                    logger.exception(f"處理圖片時發生錯誤：{image_path_str}")

            if images_base64:
                message["images"] = images_base64

        chat_data["messages"].append(message)

    return chat_data


def _generate_content_request(
    ai_config: AIConfig,
    chat_data: dict[str, Any] | None = None,
    role: str = "user",
    text: str = "",
    system_instruction: str = "",
    image_path_list: list[str] | None = None,
) -> dict[str, Any]:
    """產生符合 API 要求的內容請求結構"""
    if ai_config.provider == "gemini":
        return _generate_content_gemini(ai_config, chat_data, role, text, system_instruction, image_path_list)
    elif ai_config.provider == "ollama":
        if role == "model":
            role = "assistant"
        return _generate_content_ollama(ai_config, chat_data, role, text, system_instruction, image_path_list)
    return {}


def _parse_content_gemini(response: dict[str, Any]) -> tuple[bool, str, str]:
    """解析 Gemini API 回應"""
    result_text = ""
    image_output_path = ""

    try:
        candidates = response.get("candidates", [])
        if not candidates:
            return False, json.dumps(response, indent=2, ensure_ascii=False), ""

        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            return False, json.dumps(response, indent=2, ensure_ascii=False), ""

        for part in parts:
            if "text" in part:
                result_text += part["text"]
            elif "inlineData" in part and not image_output_path:
                inline_data = part["inlineData"]
                mime_type = inline_data.get("mimeType", "")
                b64_data = inline_data.get("data", "")

                if mime_type.startswith("image/") and b64_data:
                    try:
                        image_bytes = base64.b64decode(b64_data)
                        output_dir = Path("output_images")
                        output_dir.mkdir(exist_ok=True)
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                        extension = mimetypes.guess_extension(mime_type) or ".png"
                        save_path = output_dir / f"{timestamp}{extension}"
                        save_path.write_bytes(image_bytes)
                        image_output_path = str(save_path)
                        logger.info(f"AI 生成的圖片已儲存至：{image_output_path}")
                    except Exception:
                        logger.exception("解碼或儲存 AI 生成的圖片時失敗")

        if not result_text and not image_output_path:
            return False, "API 回應中未找到有效的文字或影像內容", ""

        return True, result_text, image_output_path

    except Exception:
        logger.exception("解析 API 回應時發生錯誤")
        return False, "解析 API 回應時發生錯誤", ""


def _parse_content_ollama(response: dict[str, Any]) -> tuple[bool, str, str]:
    """解析 Ollama API 回應"""
    try:
        message = response.get("message", {})
        if not message:
            return False, json.dumps(response, indent=2, ensure_ascii=False), ""

        result_text = message.get("content", "")
        if not result_text:
            return False, json.dumps(response, indent=2, ensure_ascii=False), ""

        return True, result_text, ""

    except Exception:
        logger.exception("解析 Ollama 回應時發生錯誤")
        return False, "解析 Ollama 回應時發生錯誤", ""


def _parse_content_response(ai_config: AIConfig, response: dict[str, Any]) -> tuple[bool, str, str]:
    """解析 API 回應"""
    if ai_config.provider == "gemini":
        return _parse_content_gemini(response)
    elif ai_config.provider == "ollama":
        return _parse_content_ollama(response)
    return False, f"錯誤的供應商: {ai_config.provider}", ""


def process_prompt(
    ai_config: AIConfig,
    system_text: str = "",
    prompt_text: str = "",
    image_path_list: list[str] | None = None,
    role: int = 0,
) -> tuple[bool, str, str]:
    """發送提示詞給 AI 模型並處理回應。

    Args:
        ai_config: AI 配置物件。
        system_text: 系統提示詞。
        prompt_text: 用戶提示詞。
        image_path_list: 輸入圖片路徑列表。
        role: 角色模式（0 或 1）。

    Returns:
        (是否成功, 回應文字, 圖片路徑)
    """
    chat_data = None

    if system_text:
        if role == 0:
            chat_data = _generate_content_request(ai_config, text=system_text, role="user")
            chat_data = _generate_content_request(ai_config, chat_data=chat_data, text="OK", role="model")
        elif role == 1:
            chat_data = _generate_content_request(ai_config, text="生成規則", role="user")
            chat_data = _generate_content_request(ai_config, chat_data=chat_data, text=system_text, role="model")
        else:
            chat_data = _generate_content_request(ai_config, chat_data=chat_data, system_instruction=system_text)

    chat_data = _generate_content_request(
        ai_config, chat_data=chat_data, text=prompt_text, role="user", image_path_list=image_path_list
    )

    # 發送請求
    client = get_client()
    response = client.generate_content(ai_config, chat_data)

    if not response:
        return False, "API 請求未收到有效回應或回應為空", ""

    return _parse_content_response(ai_config, response)


def requests_prompt(
    system_text: str = "",
    prompt_text: str = "",
    role: int = 0,
) -> list[dict[str, Any]]:
    """取得請求 payload（用於除錯或預覽）"""
    ai_config = AIConfig({})
    chat_data = None

    if system_text:
        if role == 0:
            chat_data = _generate_content_request(ai_config, text=system_text, role="user")
            chat_data = _generate_content_request(ai_config, chat_data=chat_data, text="好的，我將遵循指示", role="model")
        else:
            chat_data = _generate_content_request(ai_config, text="生成規則", role="user")
            chat_data = _generate_content_request(ai_config, chat_data=chat_data, text=system_text, role="model")

    chat_data = _generate_content_request(ai_config, chat_data=chat_data, text=prompt_text, role="user")
    return chat_data.get("contents", [])
