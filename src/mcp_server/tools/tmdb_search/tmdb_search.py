"""
TMDB 搜尋 Tool

搜尋 TMDB 資料庫中的電影或電視劇資訊
"""
import logging
from typing import Any

from tmdb_parser.api import MediaInfo, TMDBClient, format_output
from tmdb_parser.parser import MediaType

from mcp_server.config import TMDB_API_KEY
from mcp_server.schemas import ExecutionResult
from mcp_server.tools.base import registry

logger = logging.getLogger(__name__)


def _get_media_type(media_type_str: str | None) -> MediaType | None:
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
    elif media_type_lower == "tv":
        return MediaType.TV
    # "both" 或其他值都返回 None，表示同時搜尋電影和電視劇
    return None


def _format_results(results: list[MediaInfo]) -> str:
    """
    格式化搜尋結果列表

    Args:
        results: MediaInfo 列表

    Returns:
        格式化的字串輸出
    """
    if not results:
        return "❌ 未找到符合的媒體資訊"

    lines = []
    lines.append(f"🔍 找到 {len(results)} 個結果:\n")

    for media in results:
        lines.append(format_output(media))
        lines.append("")  # 空行分隔

    return "\n".join(lines)


@registry.register(
    name="search_tmdb",
    description="搜尋 TMDB 資料庫中的電影或電視劇資訊。回傳符合條件的媒體列表，包含標題、年份、評分、簡介等資訊。",
    input_schema={
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "要搜尋的媒體標題（電影或電視劇名稱）"
            },
            "year": {
                "type": "integer",
                "description": "年份過濾（例如：2024），可選"
            },
            "media_type": {
                "type": "string",
                "enum": ["movie", "tv", "both"],
                "default": "both",
                "description": "媒體類型：movie（電影）、tv（電視劇）、both（兩者都搜尋，預設）"
            },
            "language": {
                "type": "string",
                "default": "zh-CN",
                "description": "語言代碼（例如：zh-CN, zh-TW, en-US），預設 zh-CN"
            }
        },
        "required": ["title"]
    }
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
            error_message="TMDB_API_KEY 未設定，請檢查環境變數或 .env 檔案"
        )

    # 取得參數
    title = args.get("title", "")
    year = args.get("year")
    media_type_str = args.get("media_type", "both")
    language = args.get("language", "zh-CN")

    # 驗證必填參數
    if not title or not isinstance(title, str):
        return ExecutionResult(
            success=False,
            error_type="ValueError",
            error_message="必須提供有效的 title 參數"
        )

    # 驗證 year 參數
    if year is not None and not isinstance(year, int):
        try:
            year = int(year)
        except (ValueError, TypeError):
            year = None

    # 驗證 language 參數
    if not isinstance(language, str):
        language = "zh-CN"

    logger.info(f"搜尋 TMDB: title='{title}', year={year}, media_type={media_type_str}, language={language}")

    try:
        # 初始化 TMDB 客戶端
        client = TMDBClient(api_key=TMDB_API_KEY, language=language)

        # 轉換媒體類型
        media_type = _get_media_type(media_type_str)

        # 收集所有結果
        all_results: list[MediaInfo] = []

        if media_type == MediaType.MOVIE or media_type is None:
            movie_results = client._search_movie(title, year)
            all_results.extend(movie_results)
            logger.debug(f"電影搜尋結果: {len(movie_results)} 筆")

        if media_type == MediaType.TV or media_type is None:
            tv_results = client._search_tv(title, year)
            all_results.extend(tv_results)
            logger.debug(f"電視劇搜尋結果: {len(tv_results)} 筆")

        if not all_results:
            return ExecutionResult(
                success=True,
                stdout=f"❌ 未找到符合 '{title}' 的媒體資訊",
                metadata={
                    "title": title,
                    "year": year,
                    "media_type": media_type_str,
                    "language": language,
                    "result_count": 0
                }
            )

        # 格式化輸出
        output = _format_results(all_results)

        return ExecutionResult(
            success=True,
            stdout=output,
            metadata={
                "title": title,
                "year": year,
                "media_type": media_type_str,
                "language": language,
                "result_count": len(all_results)
            }
        )

    except Exception as e:
        logger.exception(f"TMDB 搜尋時發生錯誤: {e}")
        return ExecutionResult(
            success=False,
            error_type=type(e).__name__,
            error_message=str(e),
            stderr=str(e)
        )
