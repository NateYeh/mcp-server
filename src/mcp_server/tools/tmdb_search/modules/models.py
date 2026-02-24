"""
資料模型定義

包含 MediaType 枚舉和 MediaInfo 資料類別
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from mcp_server.tools.tmdb_search.modules.constants import (
    ADULT_GENRE_IDS,
    ANIME_GENRE_ID,
    MUSIC_GENRE_ID,
    VARIETY_GENRE_IDS,
)


class MediaType(Enum):
    """媒體類型枚舉"""

    MOVIE = "movie"
    TV = "tv"

    def get_display_name(self) -> str:
        """
        取得顯示名稱

        Returns:
            中文顯示名稱
        """
        names = {MediaType.MOVIE: "電影", MediaType.TV: "電視劇"}
        return names[self]


@dataclass
class MediaInfo:
    """
    媒體資訊資料類別

    Attributes:
        tmdb_id: TMDB ID
        media_type: 媒體類型
        title: 標題
        original_title: 原文標題
        original_language: 原始語言代碼
        year: 發行年份
        overview: 簡介
        vote_average: 平均評分
        vote_count: 評分人數
        poster_path: 海報路徑
        backdrop_path: 背景圖路徑
        release_date: 發行日期
        genre_ids: Genre ID 列表
        certification: 分級標記列表
        season_number: 季數（TV 專用）
        episode_number: 集數（TV 專用）
        episode_name: 集數名稱（TV 專用）
        episode_overview: 集數簡介（TV 專用）
    """

    tmdb_id: int
    media_type: MediaType
    title: str
    original_title: str = ""
    original_language: str = ""
    year: int | None = None
    overview: str = ""
    vote_average: float = 0.0
    vote_count: int = 0
    poster_path: str | None = None
    backdrop_path: str | None = None
    release_date: str | None = None
    genre_ids: list[int] = field(default_factory=list)
    certification: list[str] = field(default_factory=list)

    # TV 專用欄位
    season_number: int | None = None
    episode_number: int | None = None
    episode_name: str = ""
    episode_overview: str = ""

    def is_variety_show(self) -> bool:
        """
        判斷是否為綜藝節目

        Returns:
            是否為綜藝節目（真人秀/脫口秀）
        """
        return bool(VARIETY_GENRE_IDS & set(self.genre_ids))

    def is_adult(self) -> bool:
        """
        判斷是否為限制級內容

        Returns:
            是否為限制級內容
        """
        return any(genre in self.certification for genre in ADULT_GENRE_IDS)

    def is_anime(self) -> bool:
        """
        判斷是否為動畫

        Returns:
            是否為動畫
        """
        return ANIME_GENRE_ID in self.genre_ids

    def is_music(self) -> bool:
        """
        判斷是否為純音樂類型

        Returns:
            是否為純音樂類型（僅包含音樂 Genre）
        """
        return self.genre_ids == [MUSIC_GENRE_ID]

    def get_language_code(self) -> str:
        """
        取得語言代碼

        Returns:
            語言代碼（小寫），若無則返回 "unknown"
        """
        if self.original_language:
            return self.original_language.lower()
        return "unknown"

    def to_dict(self) -> dict[str, Any]:
        """
        轉換為字典格式

        Returns:
            包含所有屬性的字典
        """
        return {
            "tmdb_id": self.tmdb_id,
            "media_type": self.media_type.value,
            "title": self.title,
            "original_title": self.original_title,
            "original_language": self.original_language,
            "year": self.year,
            "overview": self.overview,
            "vote_average": self.vote_average,
            "vote_count": self.vote_count,
            "poster_path": self.poster_path,
            "backdrop_path": self.backdrop_path,
            "release_date": self.release_date,
            "genre_ids": self.genre_ids,
            "certification": self.certification,
            "season_number": self.season_number,
            "episode_number": self.episode_number,
            "episode_name": self.episode_name,
            "episode_overview": self.episode_overview,
        }
