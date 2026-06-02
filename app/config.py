"""
配置加载器 - 读取 config.yaml + .env
支持热重载: reload_config()
"""
import os
import yaml
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

_CONFIG_PATH = Path(__file__).parent / "config.yaml"

_config = None


def get_config() -> dict:
    global _config
    if _config is None:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            _config = yaml.safe_load(f)
    return _config


def reload_config() -> dict:
    global _config
    _config = None
    return get_config()
