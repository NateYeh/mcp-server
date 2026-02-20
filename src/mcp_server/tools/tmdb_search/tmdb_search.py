"""
TMDB 搜尋 Tool

搜尋 TMDB 資料庫中的電影或電視劇資訊
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from mcp_server.config import TMDB_API_KEY
from mcp_server.schemas import ExecutionResult
from mcp_server.tools.base import registry
from mcp_server.tools.tmdb_search.modules import (
    MediaInfo,
    MediaType,
    TMDBClient,
    format_results_list,
)

logger = logging.getLogger(__name__)


def _parse_media_type(media_type_str: str | None) -> MediaType | None:
    """
    將字串轉換為 MediaType 枚舉

    Args:
        media_type_str: 媒體類型字串 ("movie", "tv", 或其他)

    Returns:
        MediaType 枚舉值，若未指定或為 "both" 則返回 None
    """
    if not media_type_str:
        return None

    media_type_lower = media_type_str.lower().strip()
    if media_type_lower == "movie":
        return MediaType.MOVIE
    if media_type_lower == "tv":
        return MediaType.TV

    # "both" 或其他值都返回 None，表示同時搜尋電影和電視劇
    return None


def _parse_year(year_value: Any) -> int | None:
    """
    解析年份參數

    Args:
        year_value: 年份值（可能為 int 或 str）

    Returns:
        年份整數，若無效則返回 None
    """
    if year_value is None:
        return None

    if isinstance(year_value, int):
        return year_value

    try:
        return int(year_value)
    except (ValueError, TypeError):
        return None


async def _search_all_media(
    client: TMDBClient,
    title: str,
    year: int | None,
    media_type: MediaType | None,
) -> list[MediaInfo]:
    """
    搜尋所有媒體類型

    Args:
        client: TMDB 客戶端
        title: 標題
        year: 年份
        media_type: 媒體類型

    Returns:
        搜尋結果列表
    """
    tasks: list[Any] = []

    if media_type in (MediaType.MOVIE, None):
        tasks.append(client.search_movies(title, year))

    if media_type in (MediaType.TV, None):
        tasks.append(client.search_tv_shows(title, year))

    results = await asyncio.gather(*tasks)

    # 合併所有結果
    all_results: list[MediaInfo] = []
    for result in results:
        if isinstance(result, list):
            all_results.extend(result)

    return all_results


@registry.register(
    name="search_tmdb",
    description="搜尋 TMDB 資料庫中的電影或電視劇資訊。回傳符合條件的媒體列表，包含標題、年份、評分、簡介等資訊。",
    input_schema={
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "要搜尋的媒體標題（電影或電視劇名稱）",
            },
            "year": {
                "type": "integer",
                "description": "年份過濾（例如：2024），可選",
            },
            "media_type": {
                "type": "string",
                "enum": ["movie", "tv", "both"],
                "default": "both",
                "description": "媒體類型：movie（電影）、tv（電視劇）、both（兩者都搜尋，預設）",
            },
            "language": {
                "type": "string",
                "default": "zh-CN",
                "description": "語言代碼（例如：zh-CN, zh-TW, en-US），預設 zh-CN",
            },
        },
        "required": ["title"],
    },
)
async def handle_search_tmdb(args: dict[str, Any]) -> ExecutionResult:
    """
    處理 TMDB 搜尋請求

    Args:
        args: 包含 title, year, media_type, language 的參數字典

    Returns:
        ExecutionResult: 包含搜尋結果的執行結果
    """
    # 檢查 API Key
    if not TMDB_API_KEY:
        return ExecutionResult(
            success=False,
            error_type="ConfigurationError",
            error_message="TMDB_API_KEY 未設定，請檢查環境變數或 .env 檔案",
        )

    # 取得並驗證參數
    title = args.get("title", "")
    if not title or not isinstance(title, str):
        return ExecutionResult(
            success=False,
            error_type="ValueError",
            error_message="必須提供有效的 title 參數",
        )

    year = _parse_year(args.get("year"))
    media_type = _parse_media_type(args.get("media_type", "both"))
    language = args.get("language", "zh-CN")
    if not isinstance(language, str):
        language = "zh-CN"

    logger.info(
        "TMDB 搜尋: title=%s, year=%s, media_type=%s, language=%s",
        title,
        year,
        media_type,
        language,
    )

    try:
        # 使用 async with 管理 HTTP 客戶端生命週期
        async with TMDBClient(api_key=TMDB_API_KEY, language=language) as client:
            # 並行搜尋所有媒體類型
            results = await _search_all_media(client, title, year, media_type)

            if not results:
                return ExecutionResult(
                    success=True,
                    stdout=f"❌ 未找到符合 '{title}' 的媒體資訊",
                    metadata={
                        "title": title,
                        "year": year,
                        "media_type": args.get("media_type", "both"),
                        "language": language,
                        "result_count": 0,
                    },
                )

            # 格式化輸出
            output = format_results_list(results)

            return ExecutionResult(
                success=True,
                stdout=output,
                metadata={
                    "title": title,
                    "year": year,
                    "media_type": args.get("media_type", "both"),
                    "language": language,
                    "result_count": len(results),
                },
            )

    except Exception:
        logger.exception("TMDB 搜尋時發生錯誤")
        return ExecutionResult(
            success=False,
            error_type="InternalServerError",
            error_message="TMDB 搜尋時發生內部錯誤",
        )
