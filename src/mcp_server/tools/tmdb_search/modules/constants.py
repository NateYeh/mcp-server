"""
TMDB 相關常數定義

包含 Genre IDs、分級標記等常數
"""

# 綜藝節目 Genre IDs
# 99: 紀錄片, 10764: Reality Show, 10767: Talk Show
VARIETY_GENRE_IDS: set[int] = {99, 10764, 10767}

# 音樂 Genre ID
MUSIC_GENRE_ID: int = 10402

# 動畫 Genre ID
ANIME_GENRE_ID: int = 16

# 成人內容分級標記
ADULT_GENRE_IDS: list[str] = ["III", "19+"]
