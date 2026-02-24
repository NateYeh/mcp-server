"""
輸出格式化工具

負責將 MediaInfo 格式化為人類可讀的字串輸出
"""

from __future__ import annotations

from mcp_server.tools.tmdb_search.modules.models import MediaInfo, MediaType


def format_media_info(media: MediaInfo) -> str:
    """
    格式化單個媒體資訊

    Args:
        media: MediaInfo 物件

    Returns:
        格式化的字串輸出
    """
    lines: list[str] = []
    lines.append("=" * 50)

    # 標題
    lines.append(f"📺 標題: {media.title}")
    if media.original_title and media.original_title != media.title:
        lines.append(f"   原文標題: {media.original_title}")

    # TMDB ID
    lines.append(f"🆔 TMDB ID: {media.tmdb_id}")

    # 媒體類型
    media_type_str = media.media_type.get_display_name()
    if media.media_type == MediaType.TV and media.is_variety_show():
        media_type_str += " (綜藝)"
    lines.append(f"🎬 類型: {media_type_str}")

    # 年份
    lines.append(f"📅 年份: {media.year or '未知'}")

    # Genre IDs
    if media.genre_ids:
        lines.append(f"🎭 分類: {', '.join(map(str, media.genre_ids))}")

    # 分級
    if media.certification:
        lines.append(f"🔞 分級: {', '.join(map(str, media.certification))}")

    # 語言
    if media.original_language:
        lines.append(f"🗣️  語言: {media.original_language}")

    # 評分
    lines.append(f"⭐ 評分: {media.vote_average:.1f} ({media.vote_count} 票)")

    # TV 專用資訊
    if media.media_type == MediaType.TV and media.season_number:
        lines.append(f"📼 季/集: S{media.season_number:02d}E{media.episode_number:02d}")
        if media.episode_name:
            lines.append(f"📝 集名: {media.episode_name}")
        if media.episode_overview:
            overview_preview = media.episode_overview[:200]
            lines.append(f"📄 集數簡介: {overview_preview}...")

    # 簡介
    if media.overview:
        overview_preview = media.overview[:300]
        lines.append(f"📄 簡介: {overview_preview}...")

    # 海報
    if media.poster_path:
        lines.append(f"🖼️ 海報: https://image.tmdb.org/t/p/w500{media.poster_path}")

    lines.append("=" * 50)

    return "\n".join(lines)


def format_results_list(results: list[MediaInfo]) -> str:
    """
    格式化搜尋結果列表

    Args:
        results: MediaInfo 列表

    Returns:
        格式化的字串輸出
    """
    if not results:
        return "❌ 未找到符合的媒體資訊"

    lines: list[str] = []
    lines.append(f"🔍 找到 {len(results)} 個結果:\n")

    for media in results:
        lines.append(format_media_info(media))
        lines.append("")  # 空行分隔

    return "\n".join(lines)
