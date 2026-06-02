"""
日志工具 - 每个模块通过 get_logger(__name__) 获取带模块路径的 logger
格式: 时间 | 级别 | 模块名 | 消息
"""
import logging
import os
import sys

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# 根 logger 名称, 所有模块 logger 都是它的子级
ROOT_NAME = "app"

_initialized = False


def _ensure_handlers():
    """确保根 logger 已配置 handler (只执行一次)"""
    global _initialized
    if _initialized:
        return
    _initialized = True

    root = logging.getLogger(ROOT_NAME)
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

    # 阻止日志向上传播到 root logger (避免重复)
    root.propagate = False


def get_logger(name: str) -> logging.Logger:
    """
    获取模块专属 logger.
    用法: logger = get_logger(__name__)
    输出示例: 2026-06-02 21:41:14 | INFO    | app.services.browser_service | 挑战通过!
    """
    _ensure_handlers()

    # 将 __name__ 转换为 app.xxx 格式
    if not name.startswith(ROOT_NAME):
        name = f"{ROOT_NAME}.{name}" if not name.startswith(f"{ROOT_NAME}.") else name

    return logging.getLogger(name)
