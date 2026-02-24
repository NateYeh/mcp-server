"""
資料結構模組

定義常用的資料結構和列舉類別。
"""

import os
import re
from enum import Enum
from typing import Any

# ═══════════════════════════════════════════════════════════════════════════════
# MIME 類型映射
# ═══════════════════════════════════════════════════════════════════════════════
IMG_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
}

AUDIO_MIME_TYPES = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
    ".m4a": "audio/mp4",
}

VIDEO_MIME_TYPES = {
    ".mp4": "video/mp4",
    ".avi": "video/x-msvideo",
    ".mov": "video/quicktime",
    ".mkv": "video/x-matroska",
    ".webm": "video/webm",
    ".flv": "video/x-flv",
    ".wmv": "video/x-ms-wmv",
    ".ts": "video/mp2t",
    ".m2ts": "video/mp2t",
    ".mts": "video/mp2t",
    ".rmvb": "video/vnd.rn-realvideo",
    ".mpg": "video/mpeg",
    ".vob": "video/mpeg",
}

ALLOWED_EXTENSIONS = {
    **IMG_MIME_TYPES,
    ".m3u8": "application/x-mpegURL",
    ".mp4": "video/mp4",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
    ".m4a": "audio/mp4",
}


# ═══════════════════════════════════════════════════════════════════════════════
# 列舉類別
# ═══════════════════════════════════════════════════════════════════════════════
class ChatError(Enum):
    """直播網站可能遇到的錯誤狀態。"""
    NOT_FOUND = "Model not found"
    SERVER_ERROR = "Internal Server Error"
    OFF = "off"


# ═══════════════════════════════════════════════════════════════════════════════
# 資料類別
# ═══════════════════════════════════════════════════════════════════════════════
class AIConfig:
    """AI 模型配置類別。

    屬性:
        provider: 封裝格式或服務商，例如 "gemini" 或 "ollama"。
        model_name: 模型名稱。
        temperature: 模型的隨機性。
        top_k: 考慮的最高機率詞彙個數。
        top_p: 累計機率最高的詞彙集合。
        api_key: API 金鑰。
    """

    def __init__(self, params_dict: dict[str, Any]) -> None:
        self.provider: str = params_dict.get("provider", "gemini")
        self.model_name: str = params_dict.get("model_name", "gemini-3-flash-preview")
        self.temperature: float = params_dict.get("temperature", 1.0)
        self.top_k: int = params_dict.get("top_k", 100)
        self.top_p: float = params_dict.get("top_p", 0.9)
        self.api_key: str = params_dict.get("api_key", "")

    def __repr__(self) -> str:
        return str(self.__dict__)

    def __str__(self) -> str:
        return str(self.__dict__)


class AudioProcParams:
    """音訊處理參數類別。"""

    def __init__(self, params_dict: dict[str, Any]) -> None:
        # 測量值
        self.measured_i: float = params_dict.get("measured_i", 0)
        self.measured_tp: float = params_dict.get("measured_tp", 0)
        self.measured_lra: float = params_dict.get("measured_lra", 0)
        self.measured_thresh: float = params_dict.get("measured_thresh", 0)
        self.offset: float = params_dict.get("offset", 0)

        # 目標值
        self.integrated_loudness: float = params_dict.get("integrated_loudness", -16)
        self.true_peak: float = params_dict.get("true_peak", -1.5)
        self.loudness_range: float = params_dict.get("loudness_range", 7)

    def __repr__(self) -> str:
        return str(self.__dict__)


class FileProcParams:
    """檔案處理參數類別。"""

    def __init__(self, _dict: dict[str, Any]) -> None:
        self.src_path: str = ""
        self.work_path: str = ""
        self.work_folder: str = ""
        self.__dict__.update(_dict)
        self.file_name = os.path.basename(self.src_path)
        if self.work_folder and self.src_path:
            self.work_path = os.path.join(self.work_folder, self.file_name)

    def __repr__(self) -> str:
        return str(self.__dict__)


class FFmpegCodecArgs:
    """FFmpeg 編解碼器參數類別。"""

    def __init__(self, _dict: dict[str, Any]) -> None:
        self.encoder: str = _dict.get("encoder", "libx265")
        self.scale: bool = _dict.get("scale", False)
        self.fps: bool = _dict.get("fps", False)
        self.transpose: int = _dict.get("transpose", 0)
        self.timeout: bool = _dict.get("timeout", False)
        self.duration: int = _dict.get("duration", 0)
        self.force_comment: bool = _dict.get("force_comment", False)
        self.vf: list[str] = _dict.get("vf", [])


class HLSPlaylist:
    """解析 M3U8 播放列表結構的類別。"""

    def __init__(self, playlist_content: str) -> None:
        stream_list = []
        current_stream_info: dict[str, str] = {}
        for line in playlist_content.splitlines():
            if line.startswith("#EXT-X-STREAM-INF:"):
                current_stream_info = parse_stream_info(line.replace("#EXT-X-STREAM-INF:", ""))
            elif line.startswith("https://"):
                current_stream_info["url"] = line
                stream_list.append(current_stream_info)
                current_stream_info = {}
        self.playlists = [self.StreamInfo(info) for info in stream_list]

    def __repr__(self) -> str:
        return str(self.__dict__)

    class StreamInfo:
        def __init__(self, _dict: dict[str, str]) -> None:
            self.bandwidth: str | None = _dict.get("bandwidth")
            self.codecs: str | None = _dict.get("codecs")
            self.resolution: str | None = _dict.get("resolution")
            self.rate: str | None = _dict.get("rate")
            self.captions: str | None = _dict.get("captions")
            self.name: str | None = _dict.get("name")
            self.url: str | None = _dict.get("url")

        def __repr__(self) -> str:
            return str(self.__dict__)


class VideoDownloadArgs:
    """視訊下載參數類別。"""

    def __init__(self, _dict: dict[str, Any]) -> None:
        self.uid: str = _dict.get("uid", "")
        self.url: str = _dict.get("url", "")
        self.dst: str = _dict.get("dst", "")
        self.work_folder: str = _dict.get("work_folder", "")
        self.proc_way: str = _dict.get("proc_way", "m3u8")
        self.duration: int = int(_dict.get("duration", 0))
        self.min_size: int = _dict.get("min_size", 100)
        self.stream_name: str = _dict.get("stream_name", "")


# ═══════════════════════════════════════════════════════════════════════════════
# 工具函式
# ═══════════════════════════════════════════════════════════════════════════════
def obj_to_dict(obj: object) -> dict[str, Any] | object:
    """將物件轉換為字典。"""
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    return obj


def parse_stream_info(info_str: str) -> dict[str, str]:
    """解析串流資訊字串。"""
    info_dict: dict[str, str] = {}
    for match in re.findall(r'(\w+)=("[^"]+"|[^,]+)', info_str):
        key, value = match
        value = value.strip('"')
        info_dict[key.lower()] = value
    return info_dict
