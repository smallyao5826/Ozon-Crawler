"""
Webhook 通知工具 - 企业微信 / 飞书
URL 从数据库读取, 可通过 API 动态管理
"""
import asyncio
import requests
from backend.utils.database import get_db
from backend.utils import get_logger

logger = get_logger(__name__)
TIMEOUT = 10


def _get_active_urls(platform: str) -> list:
    """从数据库获取指定平台的所有启用 webhook URL"""
    conn = get_db()
    rows = conn.execute(
        "SELECT url FROM webhooks WHERE platform = ? AND status = 'active'",
        (platform,),
    ).fetchall()
    conn.close()
    return [r["url"] for r in rows]


MAX_RETRIES = 3
RETRY_DELAY = 2  # 秒


async def _post(url: str, payload: dict, retries: int = MAX_RETRIES):
    last_code, last_text = None, ""
    for attempt in range(retries + 1):
        def _do():
            resp = requests.post(url, json=payload, timeout=TIMEOUT)
            return resp.status_code, resp.text
        code, text = await asyncio.to_thread(_do)
        if code == 200:
            return code, text
        last_code, last_text = code, text
        if attempt < retries:
            logger.warning(f"通知失败 {code}, 第 {attempt + 1} 次重试...")
            await asyncio.sleep(RETRY_DELAY)
    return last_code, last_text


async def _send(platform: str, payload: dict):
    urls = _get_active_urls(platform)
    if not urls:
        logger.warning(f"{platform} webhook 未配置, 跳过")
        return
    for url in urls:
        code, text = await _post(url, payload)
        if code != 200:
            logger.error(f"[{platform}] 通知失败: {code} {text[:200]}")


# ============================================================
# 企业微信
# ============================================================

async def wecom_markdown(content: str):
    await _send("wecom", {
        "msgtype": "markdown",
        "markdown": {"content": content},
    })


async def wecom_text(content: str):
    await _send("wecom", {
        "msgtype": "text",
        "text": {"content": content},
    })


# ============================================================
# 飞书
# ============================================================

async def feishu_text(content: str):
    await _send("feishu", {
        "msg_type": "text",
        "content": {"text": content},
    })


async def feishu_card(title: str, content: str, color: str = "blue"):
    await _send("feishu", {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"content": title, "tag": "plain_text"},
                "template": color,
            },
            "elements": [{"tag": "markdown", "content": content}],
        },
    })


# ============================================================
# 便捷方法
# ============================================================

async def notify_all(title: str, body: str, color: str = "blue"):
    md = f"## {title}\n{body}"
    await asyncio.gather(
        wecom_markdown(md),
        feishu_card(title, body, color),
    )
