"""
日志工具 - 每个模块通过 get_logger(__name__) 获取 logger
格式: 时间 [模块名] 级别    消息
"""
import logging
import os
import sys

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FORMAT = "%(asctime)s | [%(name)s] | %(levelname)s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


_initialized = False


def _ensure_handlers():
    """确保根 logger 已配置 handler (只执行一次)"""
    global _initialized
    if _initialized:
        return
    _initialized = True

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # 控制台
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
    root.addHandler(console)

    # 文件
    file_handler = logging.FileHandler(
        os.path.join(LOG_DIR, "crawler.log"), encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
    root.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """
    获取模块专属 logger.
    用法: logger = get_logger(__name__)
    输出示例: 2026-06-02 21:41:14 [browser_service] INFO    挑战通过!
    """
    _ensure_handlers()
    short_name = name.rsplit(".", 1)[-1]
    return logging.getLogger(short_name)
