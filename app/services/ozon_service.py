"""
OZON 业务服务 - 搜索、商品详情、店铺商品
API 策略从 config.yaml 读取, 支持热切换
"""
import json
import re
import asyncio
import html as _html
from typing import Optional
from app.config import get_config
from app.services.browser_service import get_browser
from app.utils import get_logger

logger = get_logger(__name__)

SORT_MAP = {
    "popular": "score",
    "rating": "rating",
    "price": "price",
    "price_desc": "price_desc",
    "new": "new",
    "discount": "discount",
}


# ============================================================
# 核心: 多策略 API 请求
# ============================================================

async def _fetch_api(url: str, browser) -> dict:
    """按 config.yaml 中 api.strategy_order 依次尝试"""
    from app.services.http_service import api_get_json

    order = get_config()["api"]["strategy_order"]
    last_error = None

    for name in order:
        try:
            if name == "curl_cffi":
                cookies = await browser.refresh_cookies()
                data = await api_get_json(url, cookies)
                logger.info("curl_cffi API 成功")
                return data

            elif name == "playwright":
                page = browser.page
                timeout = get_config()["api"]["playwright"]["timeout"]
                resp = await asyncio.wait_for(
                    page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000),
                    timeout=timeout + 5,
                )
                if resp.status == 200:
                    logger.info("Playwright API 成功")
                    return await resp.json()
                last_error = Exception(f"Playwright 返回 {resp.status}")

            else:
                logger.warning(f"未知 API 策略: {name}")

        except Exception as e:
            last_error = e
            logger.warning(f"{name} 失败: {e}")

    raise last_error or Exception("所有 API 策略均失败")


# ============================================================
# 搜索
# ============================================================

async def search_products(keyword: str, page: int = 1, sort: str = None) -> dict:
    """
    搜索商品.
    sort: popular / rating / price / price_desc / new / discount
    """
    browser = await get_browser()
    await browser.ensure_ready()

    path = f"/search/?text={keyword}"
    params = []
    if page > 1:
        params.append(f"page={page}")
    if sort and sort in SORT_MAP:
        params.append(f"sorting={SORT_MAP[sort]}")
    if params:
        path = path + "&" + "&".join(params)

    api_url = f"https://www.ozon.ru/api/composer-api.bx/page/json/v2?url={path}"

    try:
        data = await _fetch_api(api_url, browser)
        return _parse_search_response(data, keyword)
    except Exception as e:
        return {"error": str(e), "keyword": keyword}


def _parse_search_response(data: dict, keyword: str) -> dict:
    widget_states = data.get("widgetStates", {})
    if isinstance(widget_states, str):
        widget_states = json.loads(widget_states)

    total_pages = 1
    shared = data.get("shared", "")
    if isinstance(shared, str):
        try:
            shared = json.loads(shared)
        except Exception:
            shared = {}
    if isinstance(shared, dict):
        total_pages = shared.get("catalog", {}).get("totalPages", 1)

    items = _find_tile_grid_items(widget_states)
    products = [_parse_tile_item(item) for item in items]

    return {
        "keyword": keyword,
        "total_pages": total_pages,
        "count": len(products),
        "products": products,
    }


# ============================================================
# 商品详情
# ============================================================

async def get_product_detail(product_id: str) -> dict:
    browser = await get_browser()
    await browser.ensure_ready()

    api_url = f"https://www.ozon.ru/api/composer-api.bx/page/json/v2?url=/product/{product_id}"

    try:
        data = await _fetch_api(api_url, browser)
        return _parse_product_detail(data, product_id)
    except Exception as e:
        return {"error": str(e), "product_id": product_id}


def _parse_product_detail(data: dict, product_id: str) -> dict:
    result = {"id": product_id}

    widget_states = data.get("widgetStates", {})
    if isinstance(widget_states, str):
        try:
            widget_states = json.loads(widget_states)
        except Exception:
            widget_states = {}

    for key, state in widget_states.items():
        if isinstance(state, str):
            try:
                state = json.loads(state)
            except Exception:
                pass
        if not isinstance(state, dict):
            continue

        if "webProductHeading" in key or "productHeading" in key:
            result["name"] = state.get("title", "")
            if not result.get("sku"):
                result["sku"] = state.get("sku") or state.get("id")

        if "price" in key.lower() or "webPrice" in key:
            price_str = state.get("price") or state.get("cardPrice") or ""
            result["price_raw"] = _parse_price_text(price_str)

        if "stock" in key.lower() or "availability" in key.lower():
            result["stock"] = state.get("quantity")

    return result


# ============================================================
# 店铺商品
# ============================================================

async def get_seller_products(seller_id: str, page_num: int = 1) -> dict:
    browser = await get_browser()
    await browser.ensure_ready()

    page_param = f"?page={page_num}" if page_num > 1 else ""
    api_url = (
        f"https://www.ozon.ru/api/composer-api.bx/page/json/v2"
        f"?url=/seller/{seller_id}/products/{page_param}"
    )

    try:
        data = await _fetch_api(api_url, browser)
        widget_states = data.get("widgetStates", {})
        if isinstance(widget_states, str):
            widget_states = json.loads(widget_states)

        items = _find_tile_grid_items(widget_states)
        products = [_parse_tile_item(item) for item in items]

        total_pages = 1
        shared = data.get("shared", "")
        if isinstance(shared, str):
            shared = json.loads(shared)
        if isinstance(shared, dict):
            total_pages = shared.get("catalog", {}).get("totalPages", 1)

        return {
            "seller_id": seller_id,
            "page": page_num,
            "total_pages": total_pages,
            "count": len(products),
            "products": products,
        }
    except Exception as e:
        return {"error": str(e), "seller_id": seller_id}


# ============================================================
# tileGrid 解析
# ============================================================

def _find_tile_grid_items(widget_states: dict) -> list:
    for key, state in widget_states.items():
        if "tileGrid" not in key:
            continue
        if isinstance(state, str):
            state = json.loads(state)
        if isinstance(state, dict) and "items" in state:
            return state["items"]
    return []



def _parse_tile_item(item: dict) -> dict:
    """解析商品 tile"""
    prod = {
        "id": item.get("id", ""),
        "name": "",
        "price": None,
        "stock": None,
        "rating": "",
        "review_count": "",
        "image": "",
        "url": "",
    }

    # 主图
    tile_image = item.get("tileImage", {})
    img_items = tile_image.get("items", [])
    if img_items:
        prod["image"] = img_items[0].get("image", {}).get("link", "")

    # 链接
    link = item.get("action", {}).get("link", "")
    prod["url"] = f"https://www.ozon.ru{link}" if link else ""

    labels = []
    all_prices = []  # 收集所有价格文本

    for block in item.get("mainState", []):
        t = block.get("type", "")

        if t == "textAtom":
            raw = block.get("textAtom", {}).get("text", "")
            prod["name"] = _html.unescape(raw)

        elif t == "priceV2":
            pv = block.get("priceV2", {})
            for p in pv.get("price", []):
                text = p.get("text", "")
                parsed = _parse_price_text(text)
                if parsed is not None:
                    all_prices.append((p.get("textStyle", ""), parsed))

        elif t == "labelListV2":
            for label in block.get("labelListV2", {}).get("items", []):
                if "text" in label:
                    txt = label["text"].get("text", "")
                    labels.append(txt)

    # 价格: 优先 PRICE style, 否则取第一个
    for style, val in all_prices:
        if style == "PRICE":
            prod["price"] = val
            break
    if prod["price"] is None and all_prices:
        prod["price"] = all_prices[0][1]

    # 评分 & 评论数
    for txt in labels:
        if re.match(r'^\d+[.,]\d+$', txt) and not prod["rating"]:
            prod["rating"] = txt
        if "отзыв" in txt.lower():
            prod["review_count"] = txt

    # 库存: labels 中 "X шт" > maxItems
    for txt in labels:
        m = re.search(r'(\d+)\s*шт', txt.lower())
        if m:
            prod["stock"] = int(m.group(1))
            break

    if prod["stock"] is None:
        for btn_key in ("ozonButton", "expressButton"):
            max_items = (
                item.get("multiButton", {})
                .get(btn_key, {})
                .get("addToCart", {})
                .get("quantityButton", {})
                .get("maxItems")
            )
            if max_items is not None:
                prod["stock"] = max_items
                break

    return prod


# ============================================================
# 工具函数
# ============================================================

def _parse_price_text(value) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = re.sub(r'[^\d,]', '', value)
        cleaned = cleaned.replace(',', '.')
        try:
            return float(cleaned)
        except (ValueError, TypeError):
            pass
    return None
