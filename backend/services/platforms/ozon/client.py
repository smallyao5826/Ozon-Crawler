"""
OZON API 客户端 - 搜索、商品详情、店铺商品
"""
import json
import re
import asyncio
from backend.services.core.config import get_config
from backend.services.core.browser import get_browser
from backend.services.core.http import api_get_json
from backend.utils import get_logger
from .parser import (
    parse_search_response,
    parse_product_detail,
    _find_tile_grid_items,
    _parse_tile_item,
)

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
    order = get_config()["api"]["strategy_order"]
    logger.info(f"[API] 策略顺序: {order}")
    last_error = None

    for name in order:
        try:
            if name == "curl_cffi":
                cookies = await browser.refresh_cookies()
                data = await api_get_json(url, cookies)
                logger.info("[curl_cffi] API 成功")
                return data

            elif name == "playwright":
                page = browser.page
                logger.info(f"[Playwright] fetch {url[:100]}")
                timeout = get_config()["api"]["playwright"]["timeout"]
                result = await asyncio.wait_for(
                    page.evaluate("""
                        async (url) => {
                            const resp = await fetch(url);
                            const text = await resp.text();
                            return {_status: resp.status, _body: text};
                        }
                    """, url),
                    timeout=timeout + 5,
                )
                if isinstance(result, dict) and result.get("_status") == 200:
                    logger.info("[Playwright] API 成功")
                    return json.loads(result["_body"])
                status = result.get("_status", "N/A") if isinstance(result, dict) else "N/A"
                last_error = Exception(f"Playwright fetch 返回 {status}")
                logger.warning(f"[Playwright] 返回 {status}")

            else:
                logger.warning(f"[API] 未知策略: {name}")

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
        return parse_search_response(data, keyword)
    except Exception as e:
        return {"error": str(e), "keyword": keyword}


# ============================================================
# 商品详情
# ============================================================

def extract_product_id(url: str) -> str:
    """从商品 URL 提取数字 ID, 支持 /product/12345/ 和 /product/slug-12345/"""
    m = re.search(r'/product/(?:.*-)?(\d+)', url)
    return m.group(1) if m else ""


async def parse_product_url(url: str) -> dict:
    """传入商品 URL, 返回商品详情"""
    product_id = extract_product_id(url)
    logger.info(f"parse_product_url: url={url[:100]}, product_id={product_id}")
    if not product_id:
        return {"error": "无法从 URL 提取商品 ID", "url": url}
    return await get_product_detail(product_id)


async def get_product_detail(product_id: str) -> dict:
    browser = await get_browser()
    await browser.ensure_ready()

    logger.info(f"get_product_detail: product_id={product_id}")
    api_url = f"https://www.ozon.ru/api/composer-api.bx/page/json/v2?url=/product/{product_id}"

    try:
        data = await _fetch_api(api_url, browser)
        return parse_product_detail(data, product_id)
    except Exception as e:
        return {"error": str(e), "product_id": product_id}


# ============================================================
# 店铺
# ============================================================

def extract_seller_slug(url: str) -> str:
    """从店铺 URL 中提取 seller slug, 如 blank-2121713、ozon"""
    m = re.search(r'/seller/([^/?]+)', url)
    return m.group(1) if m else ""


async def _resolve_seller_slug_from_page(url: str, browser) -> str:
    """
    当 URL 中不包含 /seller/ 时, 通过访问页面 API 推断卖家 slug。
    目前支持: 产品链接 (/product/{id})
    """
    m = re.search(r'/product/(?:.*-)?(\d+)', url)
    if m:
        product_id = m.group(1)
        api_url = f"https://www.ozon.ru/api/composer-api.bx/page/json/v2?url=/product/{product_id}"
        try:
            data = await _fetch_api(api_url, browser)
            ws = data.get("widgetStates", {})
            if isinstance(ws, str):
                ws = json.loads(ws)
            for key, state in ws.items():
                if isinstance(state, str):
                    state = json.loads(state)
                if not isinstance(state, dict):
                    continue
                seller_link = state.get("sellerCell", {}).get("common", {}).get("action", {}).get("link", "")
                if seller_link:
                    s = extract_seller_slug(seller_link)
                    if s:
                        return s
        except Exception:
            pass

    return ""


async def get_seller_info(url: str) -> dict:
    """
    传入店铺 URL 或产品 URL, 返回卖家信息 + 第一页商品。
    支持: /seller/{slug} 直接提取, /product/{id} 反向解析卖家
    """
    browser = await get_browser()
    await browser.ensure_ready()

    slug = extract_seller_slug(url)
    if not slug:
        slug = await _resolve_seller_slug_from_page(url, browser)

    if not slug:
        return {"error": "无法从 URL 提取卖家标识", "url": url}

    result = await get_seller_products(slug, page_num=1)
    if "error" in result:
        result["url"] = url
        return result

    return {
        "seller_id": result.get("seller_id", ""),
        "seller_slug": slug,
        "seller_name": result.get("seller_name", slug),
        "seller_url": f"https://www.ozon.ru/seller/{slug}/",
        "total_pages": result.get("total_pages", 1),
        "products": result.get("products", []),
        "count": result.get("count", 0),
    }


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

        seller_name = ""
        for key, state in widget_states.items():
            if "sellerTransparency" in key or "sellerHeading" in key:
                if isinstance(state, str):
                    try:
                        state = json.loads(state)
                    except Exception:
                        pass
                if isinstance(state, dict):
                    seller_name = state.get("title", {}).get("text", "")
                    if seller_name:
                        break

        numeric_seller_id = ""
        page_info = data.get("pageInfo", {})
        if isinstance(page_info, str):
            page_info = json.loads(page_info)
        if isinstance(page_info, dict):
            numeric_seller_id = str(page_info.get("analyticsInfo", {}).get("sellerId", ""))

        return {
            "seller_id": numeric_seller_id or seller_id,
            "seller_slug": seller_id,
            "seller_name": seller_name,
            "page": page_num,
            "total_pages": total_pages,
            "count": len(products),
            "products": products,
        }
    except Exception as e:
        return {"error": str(e), "seller_id": seller_id}
