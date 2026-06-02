"""
curl_cffi HTTP 服务 - 模拟浏览器 TLS 指纹请求 OZON API
"""
import asyncio
import json
from curl_cffi import requests as curl_requests
from app.config import get_config
from app.utils import get_logger

logger = get_logger(__name__)


async def api_get_json(url: str, cookies: dict = None) -> dict:
    """用 curl_cffi 发起 GET, 返回解析好的 JSON"""
    cfg = get_config()["api"]["curl_cffi"]
    impersonate = cfg["impersonate"]
    timeout = cfg["timeout"]

    s = get_config()["settings"]

    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "User-Agent": s["user_agent"],
    }

    def _do():
        for attempt in range(cfg["max_retries"]):
            try:
                resp = curl_requests.get(
                    url,
                    headers=headers,
                    cookies=cookies or {},
                    impersonate=impersonate,
                    timeout=timeout,
                )
                if resp.status_code == 200:
                    return resp.text
                logger.warning(f"curl_cffi 第{attempt+1}次返回 {resp.status_code}")
            except Exception as e:
                logger.warning(f"curl_cffi 第{attempt+1}次异常: {e}")
                if attempt == cfg["max_retries"] - 1:
                    raise
        raise Exception(f"curl_cffi 重试{cfg['max_retries']}次后仍失败")

    text = await asyncio.to_thread(_do)
    return json.loads(text)
