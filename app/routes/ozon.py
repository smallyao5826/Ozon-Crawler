"""
OZON 相关路由: 搜索、商品详情、店铺商品
"""
from fastapi import APIRouter, Query, Path, HTTPException
from app.services import ozon_service
from app.services.browser_service import get_browser
from app.utils import success, error

router = APIRouter(prefix="/api/ozon", tags=["OZON 数据"])


@router.get("/search", summary="搜索商品")
async def search(
    keyword: str = Query(..., description="搜索关键词"),
    page: int = Query(1, ge=1, description="页码"),
    sort: str = Query(None, description="排序: popular(热门)/rating(评分)/price(低价)/price_desc(高价)/new(最新)/discount(折扣)"),
):
    """在 OZON 搜索商品"""
    try:
        result = await ozon_service.search_products(keyword, page, sort)
        if "error" in result:
            return error(result["error"])
        return success(
            result["products"],
            keyword=result["keyword"],
            page=page,
            count=result["count"],
            total_pages=result["total_pages"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"搜索失败: {e}")


@router.get("/product/{product_id}", summary="商品详情")
async def product_detail(
    product_id: str = Path(..., description="OZON 商品 ID"),
):
    """获取单个商品的详细信息(价格/库存/评分等)"""
    try:
        result = await ozon_service.get_product_detail(product_id)
        if "error" in result:
            return error(result["error"])
        return success(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取失败: {e}")


@router.get("/seller/{seller_id}/products", summary="店铺商品列表")
async def seller_products(
    seller_id: str = Path(..., description="OZON 卖家 ID"),
    page: int = Query(1, ge=1, description="页码"),
):
    """获取指定店铺的商品列表"""
    try:
        result = await ozon_service.get_seller_products(seller_id, page)
        if "error" in result:
            return error(result["error"])
        return success(
            result["products"],
            seller_id=result["seller_id"],
            page=result["page"],
            count=result["count"],
            total_pages=result["total_pages"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取失败: {e}")


@router.get("/status", summary="浏览器状态")
async def browser_status():
    """检查浏览器反爬会话是否就绪"""
    try:
        browser = await get_browser()
        return success({
            "ready": browser.is_ready,
            "cookies_count": len(browser.cookies),
        })
    except Exception as e:
        return error(str(e))
