"""圖片辨識 Tool - 使用 AI 模型進行圖片內容分析"""

import logging
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from mcp_server.base.data_structures import AIConfig
from mcp_server.config import WORK_DIR
from mcp_server.model.gemini_api_client import process_prompt
from mcp_server.schemas import ExecutionResult
from mcp_server.tools.base import registry

logger = logging.getLogger(__name__)

# 支援的圖片格式（MIME type 對照）
SUPPORTED_IMAGE_FORMATS = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}

# 預設 AI 配置
DEFAULT_PROVIDER = "ollama"
DEFAULT_MODEL_NAME = "kimi-k2.5"

# 圖片下載設定
DEFAULT_DOWNLOAD_TIMEOUT = 60  # 圖片下載超時（秒）
DEFAULT_RECOGNITION_TIMEOUT = 300  # AI 辨識超時（秒）
MAX_IMAGE_SIZE = 50 * 1024 * 1024  # 最大圖片大小 50MB


def _validate_image_url(url: str) -> tuple[bool, str, str]:
    """
    驗證圖片 URL 是否有效。

    Args:
        url: 圖片 URL

    Returns:
        tuple[bool, str, str]: (是否有效, 錯誤訊息, 副檔名)
    """
    try:
        parsed = urlparse(url)

        # 檢查協議
        if parsed.scheme not in ("http", "https"):
            return False, f"不支援的協議: {parsed.scheme}，僅支援 http/https", ""

        # 檢查副檔名
        path = parsed.path.lower()
        ext = ""
        for supported_ext in SUPPORTED_IMAGE_FORMATS:
            if path.endswith(supported_ext):
                ext = supported_ext
                break

        if not ext:
            # 嘗試從 query string 中找副檔名
            for supported_ext in SUPPORTED_IMAGE_FORMATS:
                if supported_ext in url.lower():
                    ext = supported_ext
                    break

        # 如果還是找不到副檔名，使用 .png 作為預設（後續會從 Content-Type 驗證）
        if not ext:
            ext = ".png"  # 預設副檔名，實際格式會在下載時驗證

        return True, "", ext

    except Exception as e:
        return False, f"URL 解析失敗: {e}", ""


def _get_extension_from_content_type(content_type: str) -> str:
    """
    從 Content-Type 取得對應的副檔名。

    Args:
        content_type: Content-Type 字串，例如 "image/png"

    Returns:
        str: 副檔名（包含點），例如 ".png"
    """
    # 清理 content_type（移除 charset 等參數）
    mime = content_type.split(";")[0].strip().lower()

    # MIME type 到副檔名的對照
    mime_to_ext = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "image/bmp": ".bmp",
    }

    return mime_to_ext.get(mime, ".png")


def _download_image(url: str, work_dir: Path, timeout: int = DEFAULT_DOWNLOAD_TIMEOUT) -> tuple[bool, str, str]:
    """
    下載圖片到指定目錄。

    Args:
        url: 圖片 URL
        work_dir: 工作目錄
        timeout: 下載超時時間（秒）

    Returns:
        tuple[bool, str, str]: (成功, 本地檔案路徑, 錯誤訊息)
    """
    # 驗證 URL
    is_valid, error_msg, ext = _validate_image_url(url)
    if not is_valid:
        return False, "", error_msg

    # 產生唯一的暫存檔名
    timestamp = int(time.time() * 1000)
    temp_filepath = work_dir / f"image_{timestamp}.tmp"

    try:
        logger.info(f"開始下載圖片: {url}")

        # 發送請求
        response = requests.get(url, timeout=timeout, stream=True, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
        response.raise_for_status()

        # 檢查 Content-Length
        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > MAX_IMAGE_SIZE:
            return False, "", f"圖片大小超過限制 ({MAX_IMAGE_SIZE // 1024 // 1024}MB)"

        # 檢查 Content-Type 並決定實際副檔名
        content_type = response.headers.get("Content-Type", "")
        if content_type and not content_type.startswith("image/"):
            return False, "", f"Content-Type 不是圖片: {content_type}"

        # 從 Content-Type 取得正確的副檔名
        actual_ext = _get_extension_from_content_type(content_type) if content_type else ext
        final_filepath = work_dir / f"image_{timestamp}{actual_ext}"

        # 下載並寫入檔案
        downloaded_size = 0
        with open(temp_filepath, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded_size += len(chunk)
                    if downloaded_size > MAX_IMAGE_SIZE:
                        temp_filepath.unlink(missing_ok=True)
                        return False, "", f"圖片大小超過限制 ({MAX_IMAGE_SIZE // 1024 // 1024}MB)"

        # 將暫存檔重命名為最終檔名
        temp_filepath.rename(final_filepath)

        logger.info(f"圖片下載完成: {final_filepath} ({downloaded_size} bytes)")
        return True, str(final_filepath), ""

    except requests.exceptions.Timeout:
        temp_filepath.unlink(missing_ok=True)
        return False, "", f"下載超時（{timeout}秒）"
    except requests.exceptions.RequestException as e:
        temp_filepath.unlink(missing_ok=True)
        return False, "", f"下載失敗: {e}"
    except Exception as e:
        logger.exception(f"下載圖片時發生未預期錯誤: {e}")
        temp_filepath.unlink(missing_ok=True)
        return False, "", f"下載時發生錯誤: {e}"


def _recognize_image(image_path: str, prompt: str, system_instruction: str, ai_config: AIConfig) -> tuple[bool, str, str]:
    """
    呼叫 AI 進行圖片辨識。

    Args:
        image_path: 本地圖片路徑
        prompt: 辨識提示詞
        system_instruction: 系統提示詞
        ai_config: AI 配置

    Returns:
        tuple[bool, str, str]: (成功, 辨識結果, 錯誤訊息)
    """
    try:
        logger.info(f"開始 AI 辨識: provider={ai_config.provider}, model={ai_config.model_name}")

        # 呼叫 natekit 的 process_prompt
        success, result_text, output_image_path = process_prompt(ai_config=ai_config, system_text=system_instruction, prompt_text=prompt, image_path_list=[image_path], role=0)

        if not success:
            return False, "", f"AI 辨識失敗: {result_text}"

        logger.info(f"AI 辨識完成，結果長度: {len(result_text)} 字元")
        return True, result_text, ""

    except Exception as e:
        logger.exception(f"AI 辨識時發生錯誤: {e}")
        return False, "", f"AI 辨識時發生錯誤: {e}"


@registry.register(
    name="image_recognition",
    description=("下載圖片並使用 AI 模型進行內容辨識分析。支援主流圖片格式（PNG、JPEG、GIF、WebP、BMP）。可指定 AI 模型與提示詞進行各種圖片分析任務。"),
    input_schema={
        "type": "object",
        "properties": {
            "image_url": {"type": "string", "description": "要辨識的圖片網址（支援 http/https）"},
            "prompt": {"type": "string", "description": "圖片辨識要求，例如：'描述這張圖片的內容'、'識別圖中的文字'、'分析這張圖片的風格'"},
            "system_instruction": {"type": "string", "description": "系統提示詞，設定 AI 的角色或輸出格式（可選，預設為專業圖片分析師）"},
            "provider": {"type": "string", "description": "AI 服務提供商，預設 'ollama'", "default": "ollama"},
            "model_name": {"type": "string", "description": "模型名稱，預設 'kimi-k2.5'", "default": "kimi-k2.5"},
            "download_timeout": {"type": "integer", "description": "圖片下載超時時間（秒），預設 60 秒", "default": 60},
        },
        "required": ["image_url", "prompt"],
    },
)
async def handle_image_recognition(args: dict[str, Any]) -> ExecutionResult:
    """
    處理圖片辨識請求。

    Args:
        args: 包含以下參數的字典：
            - image_url: 圖片網址
            - prompt: 辨識提示詞
            - system_instruction: 系統提示詞（可選）
            - provider: AI 提供商（可選，預設 ollama）
            - model_name: 模型名稱（可選，預設 kimi-k2.5）
            - download_timeout: 下載超時時間（可選，預設 60 秒）

    Returns:
        ExecutionResult: 執行結果
    """
    start_time = time.time()

    # 解析參數
    image_url = args.get("image_url", "")
    prompt = args.get("prompt", "")
    system_instruction = args.get("system_instruction", "你是一位專業的圖片分析師，請仔細觀察圖片並提供準確、詳細的分析結果。")
    provider = args.get("provider", DEFAULT_PROVIDER)
    model_name = args.get("model_name", DEFAULT_MODEL_NAME)
    download_timeout = args.get("download_timeout", DEFAULT_DOWNLOAD_TIMEOUT)

    # 參數驗證
    if not image_url:
        return ExecutionResult(success=False, error_type="ValidationError", error_message="缺少必要參數: image_url")

    if not prompt:
        return ExecutionResult(success=False, error_type="ValidationError", error_message="缺少必要參數: prompt")

    # 建立 AI 配置
    ai_config = AIConfig(
        {
            "provider": provider,
            "model_name": model_name,
        }
    )

    downloaded_file = None

    try:
        # 步驟 1: 下載圖片
        logger.info(f"開始處理圖片辨識請求: {image_url}")
        download_success, local_path, download_error = _download_image(image_url, WORK_DIR, download_timeout)

        if not download_success:
            return ExecutionResult(success=False, error_type="DownloadError", error_message=download_error, metadata={"image_url": image_url})

        downloaded_file = local_path

        # 步驟 2: AI 辨識
        recognition_success, result, recognition_error = _recognize_image(local_path, prompt, system_instruction, ai_config)

        if not recognition_success:
            return ExecutionResult(
                success=False,
                error_type="RecognitionError",
                error_message=recognition_error,
                metadata={"image_url": image_url, "local_path": local_path, "provider": provider, "model_name": model_name},
            )

        # 成功
        execution_time = time.time() - start_time
        return ExecutionResult(
            success=True,
            stdout=result,
            metadata={"image_url": image_url, "local_path": local_path, "provider": provider, "model_name": model_name},
            execution_time=f"{execution_time:.3f}s",
        )

    except Exception as e:
        logger.exception(f"圖片辨識過程發生未預期錯誤: {e}")
        return ExecutionResult(success=False, error_type="UnexpectedError", error_message=str(e), metadata={"image_url": image_url})

    finally:
        # 清理暫存檔案
        if downloaded_file:
            try:
                Path(downloaded_file).unlink(missing_ok=True)
                logger.debug(f"已清理暫存圖片: {downloaded_file}")
            except Exception as e:
                logger.warning(f"清理暫存圖片失敗: {e}")
