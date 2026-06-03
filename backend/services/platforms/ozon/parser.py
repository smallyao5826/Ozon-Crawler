"""
OZON 数据解析 - 纯函数, 无副作用, 不依赖浏览器或配置
"""
import json
import re
import html as _html
from typing import Optional


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


def _find_in_dict(obj, target_key):
    """递归查找字典中的指定 key"""
    if isinstance(obj, dict):
        if target_key in obj:
            return obj[target_key]
        for v in obj.values():
            r = _find_in_dict(v, target_key)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for item in obj:
            r = _find_in_dict(item, target_key)
            if r is not None:
                return r
    return None


# ============================================================
# 搜索
# ============================================================

def parse_search_response(data: dict, keyword: str) -> dict:
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

def parse_product_detail(data: dict, product_id: str) -> dict:
    result = {
        "id": product_id,
        "name": "",
        "price": None,
        "stock": None,
        "rating": "",
        "review_count": 0,
        "image": "",
        "url": f"https://www.ozon.ru/product/{product_id}/",
    }

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

        if "webPrice" in key:
            price_str = state.get("cardPrice") or state.get("price") or ""
            result["price"] = _parse_price_text(price_str)

        if "webGallery" in key:
            result["image"] = state.get("coverImage", "")

        if "webReviewProductScore" in key:
            score = state.get("totalScore") or state.get("score")
            result["rating"] = str(score) if score else ""
            result["review_count"] = state.get("reviewsCount", 0)

        if "webAddToCart" in key:
            stock = _find_in_dict(state, "freeRest")
            if stock is not None:
                result["stock"] = stock

    if result["stock"] is None:
        for key, state in widget_states.items():
            if "webPrice" in key:
                if isinstance(state, str):
                    try:
                        state = json.loads(state)
                    except Exception:
                        pass
                if isinstance(state, dict) and not state.get("isAvailable", True):
                    result["stock"] = 0
                break

    return result


# ============================================================
# tileGrid 解析 (搜索 / 店铺商品 共用)
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
        "review_count": 0,
        "image": "",
        "url": "",
    }

    tile_image = item.get("tileImage", {})
    img_items = tile_image.get("items", [])
    if img_items:
        prod["image"] = img_items[0].get("image", {}).get("link", "")

    link = item.get("action", {}).get("link", "")
    prod["url"] = f"https://www.ozon.ru{link}" if link else ""

    labels = []
    all_prices = []

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

    for style, val in all_prices:
        if style == "PRICE":
            prod["price"] = val
            break
    if prod["price"] is None and all_prices:
        prod["price"] = all_prices[0][1]

    for txt in labels:
        if re.match(r'^\d+[.,]\d+$', txt) and not prod["rating"]:
            prod["rating"] = txt
        if "отзыв" in txt.lower():
            m = re.search(r'(\d+)', txt)
            prod["review_count"] = int(m.group(1)) if m else 0

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
