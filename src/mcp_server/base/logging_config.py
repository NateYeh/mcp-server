"""
日誌設定模組

提供統一的日誌系統配置，支援控制台顏色輸出和檔案輪替。
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# 預設外部套件日誌等級
EXTERNAL_LOG = [
    "yfinance",
    "peewee",
    "urllib3",
    "PIL",
    "qbittorrentapi",
    "asyncio",
    "fakeredis",
    "docket.worker",
    "playwright",
    "httpx",
    "httpcore",
    "charset_normalizer",
    "websockets",
]

# 日誌時間格式
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def _get_color_formatter_func(fg: int | None = None, bg: int | None = None):
    """根據前景或背景顏色代碼，返回用於文字著色的函式。"""
    color_codes = []
    if fg is not None:
        color_codes.append(f"38;5;{fg}")
    if bg is not None:
        color_codes.append(f"48;5;{bg}")

    if not color_codes:
        return lambda text: text

    color_prefix = f"\033[{';'.join(color_codes)}m"
    reset_code = "\033[0m"

    def apply_color(text: str) -> str:
        return f"{color_prefix}{text}{reset_code}"

    return apply_color


# 不同日誌等級的顏色映射
_LEVEL_COLORS = {
    logging.DEBUG: _get_color_formatter_func(fg=7),    # 白色
    logging.INFO: _get_color_formatter_func(fg=2),    # 綠色
    logging.WARNING: _get_color_formatter_func(fg=3),   # 黃色
    logging.ERROR: _get_color_formatter_func(fg=1),     # 紅色
    logging.CRITICAL: _get_color_formatter_func(fg=6, bg=1),
}


class ColoredFormatter(logging.Formatter):
    """自訂日誌格式化器，為控制台輸出添加 ANSI 顏色。"""

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        return _LEVEL_COLORS.get(record.levelno, lambda x: x)(message)


def setup_logging(
    log_file: str = "mcp_server.log",
    console_log_level: int = logging.DEBUG,
    file_log_level: int = logging.WARNING,
    log_dir: str | None = None,
) -> None:
    """
    設定應用的全局日誌系統。

    Args:
        log_file: 日誌檔案名稱（相對於 log_dir）。
        console_log_level: 控制台輸出的日誌等級。
        file_log_level: 檔案輸出的日誌等級。
        log_dir: 日誌目錄路徑，預設為專案根目錄的 logs/。
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # 清除現有的 handler
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        handler.close()

    # 1. 檔案處理器
    if file_log_level != logging.NOTSET:
        # 確定日誌目錄
        if log_dir:
            log_dir_path = Path(log_dir)
        else:
            # 預設使用專案根目錄下的 logs/
            project_root = Path(__file__).parent.parent.parent.parent
            log_dir_path = project_root / "logs"

        log_dir_path.mkdir(parents=True, exist_ok=True)
        log_file_path = log_dir_path / log_file

        try:
            file_handler = RotatingFileHandler(
                filename=str(log_file_path),
                maxBytes=10 * 1024 * 1024,  # 10 MB
                backupCount=5,
                encoding="utf-8",
            )
            file_handler.setLevel(file_log_level)
            file_formatter = logging.Formatter(
                fmt="[%(asctime)s][%(levelname)-8s][%(name)s:%(module)s:%(lineno)d] %(message)s",
                datefmt=DATE_FORMAT,
            )
            file_handler.setFormatter(file_formatter)
            root_logger.addHandler(file_handler)
        except OSError as e:
            sys.stderr.write(f"警告: 無法建立日誌檔案處理器: {e}\n")

    # 2. 控制台處理器
    if console_log_level != logging.NOTSET:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(console_log_level)

        if sys.platform == "win32":
            console_formatter = logging.Formatter(
                fmt="[%(asctime)s][%(levelname)-8s][%(name)s:%(module)s:%(lineno)d] %(message)s",
                datefmt=DATE_FORMAT,
            )
        else:
            console_formatter = ColoredFormatter(
                fmt="[%(asctime)s][%(levelname)-8s][%(name)s:%(module)s:%(lineno)d] %(message)s",
                datefmt=DATE_FORMAT,
            )
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)

    # 設定外部套件日誌等級
    for log_name in EXTERNAL_LOG:
        logger = logging.getLogger(log_name)
        logger.setLevel(logging.INFO)

    if root_logger.handlers:
        root_logger.debug("日誌系統設定完成")
