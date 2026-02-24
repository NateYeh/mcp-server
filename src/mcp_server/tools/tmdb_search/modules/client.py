"""
TMDB API 客戶端

負責與 TMDB API 進行通訊，搜尋電影和電視劇資訊
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any

import httpx

from mcp_server.tools.tmdb_search.modules.models import MediaInfo, MediaType

logger = logging.getLogger(__name__)


class TMDBClient:
    """
    TMDB API 客戶端

    使用 httpx.AsyncClient 進行非同步 HTTP 請求

    Attributes:
        BASE_URL: TMDB API 基礎 URL
        api_key: TMDB API Key
        language: 語言代碼
    """

    BASE_URL: str = "https://api.themoviedb.org/3"

    def __init__(self, api_key: str, language: str = "zh-CN") -> None:
        """
        初始化 TMDB 客戶端

        Args:
            api_key: TMDB API Key
            language: 語言代碼，預設 zh-CN
        """
        self.api_key = api_key
        self.language = language
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> TMDBClient:
        """進入非同步上下文管理器"""
        self._client = httpx.AsyncClient(timeout=30.0)
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """離開非同步上下文管理器"""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _build_params(self, extra_params: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        建構 API 請求參數

        Args:
            extra_params: 額外參數

        Returns:
            完整的請求參數字典
        """
        params: dict[str, Any] = {
            "api_key": self.api_key,
            "language": self.language,
            "include_adult": True,
        }
        if extra_params:
            params.update(extra_params)
        return params

    async def _get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        發送 GET 請求到 TMDB API

        Args:
            endpoint: API 端點（不含基礎 URL）
            params: 查詢參數

        Returns:
            API 回應 JSON 資料

        Raises:
            httpx.HTTPStatusError: HTTP 錯誤
            httpx.RequestError: 請求錯誤
        """
        if not self._client:
            raise RuntimeError("TMDBClient 未初始化，請使用 async with 語句")

        url = f"{self.BASE_URL}/{endpoint}"
        full_params = self._build_params(params)

        logger.debug("TMDB API 請求: %s, params=%s", url, full_params)

        response = await self._client.get(url, params=full_params)
        response.raise_for_status()

        return response.json()

    async def search_movies(self, title: str, year: int | None = None) -> list[MediaInfo]:
        """
        搜尋電影

        Args:
            title: 電影標題
            year: 發行年份（可選）

        Returns:
            MediaInfo 列表
        """
        params: dict[str, Any] = {"query": title}
        if year:
            params["year"] = year

        try:
            response = await self._get("search/movie", params)
            return [self._parse_movie(item) for item in response.get("results", [])]
        except Exception:
            logger.exception("搜尋電影時發生錯誤: title=%s, year=%s", title, year)
            return []

    async def search_tv_shows(self, title: str, year: int | None = None) -> list[MediaInfo]:
        """
        搜尋電視劇

        Args:
            title: 電視劇標題
            year: 首播年份（可選）

        Returns:
            MediaInfo 列表
        """
        params: dict[str, Any] = {"query": title}
        if year:
            params["first_air_date_year"] = year

        try:
            response = await self._get("search/tv", params)
            return [self._parse_tv(item) for item in response.get("results", [])]
        except Exception:
            logger.exception("搜尋電視劇時發生錯誤: title=%s, year=%s", title, year)
            return []

    def _parse_movie(self, data: dict[str, Any]) -> MediaInfo:
        """
        解析電影 API 回應

        Args:
            data: API 回應資料

        Returns:
            MediaInfo 物件
        """
        release_date = data.get("release_date", "")
        year = None
        if release_date and len(release_date) >= 4:
            with contextlib.suppress(ValueError):
                year = int(release_date[:4])

        return MediaInfo(
            tmdb_id=data["id"],
            media_type=MediaType.MOVIE,
            title=data.get("title", ""),
            original_title=data.get("original_title", ""),
            original_language=data.get("original_language", ""),
            year=year,
            overview=data.get("overview", ""),
            vote_average=float(data.get("vote_average", 0)),
            vote_count=int(data.get("vote_count", 0)),
            poster_path=data.get("poster_path"),
            backdrop_path=data.get("backdrop_path"),
            release_date=release_date or None,
            genre_ids=data.get("genre_ids", []),
            certification=[],
        )

    def _parse_tv(self, data: dict[str, Any]) -> MediaInfo:
        """
        解析電視劇 API 回應

        Args:
            data: API 回應資料

        Returns:
            MediaInfo 物件
        """
        first_air_date = data.get("first_air_date", "")
        year = None
        if first_air_date and len(first_air_date) >= 4:
            with contextlib.suppress(ValueError):
                year = int(first_air_date[:4])

        return MediaInfo(
            tmdb_id=data["id"],
            media_type=MediaType.TV,
            title=data.get("name", ""),
            original_title=data.get("original_name", ""),
            original_language=data.get("original_language", ""),
            year=year,
            overview=data.get("overview", ""),
            vote_average=float(data.get("vote_average", 0)),
            vote_count=int(data.get("vote_count", 0)),
            poster_path=data.get("poster_path"),
            backdrop_path=data.get("backdrop_path"),
            release_date=first_air_date or None,
            genre_ids=data.get("genre_ids", []),
            certification=[],
        )
