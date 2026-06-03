"""
配置加载器 - 读取 config.yaml, 每次实时读取
"""
import yaml
from pathlib import Path

_CONFIG_PATH = Path(__file__).parent.parent.parent / "config.yaml"


def get_config() -> dict:
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def reload_config() -> dict:
    return get_config()
