"""
OZON Crawler - FastAPI 应用入口

启动: python app/main.py
"""
import sys
import os

# Windows Playwright 兼容: 必须在任何 asyncio 操作之前设置
if sys.platform == "win32":
    import asyncio as _asyncio
    if not isinstance(_asyncio.get_event_loop_policy(), _asyncio.WindowsSelectorEventLoopPolicy):
        _asyncio.set_event_loop_policy(_asyncio.WindowsSelectorEventLoopPolicy())

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.utils import init_db, get_logger

logger = get_logger(__name__)
from app.routes import ozon, monitor, webhook


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("数据库已初始化")
    logger.info("OZON Crawler 已启动")
    logger.info("API 文档: http://localhost:8000/docs")
    yield
    from app.services.browser_service import _browser_instance
    if _browser_instance:
        await _browser_instance.close()
    logger.info("已关闭")


app = FastAPI(
    title="OZON 商品监控爬虫",
    description="OZON 商品搜索、详情查询、价格库存监控",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ozon.router)
app.include_router(monitor.router)
app.include_router(webhook.router)


@app.get("/health", summary="健康检查", tags=["系统"])
async def health():
    """检查服务是否正常运行"""
    return {"status": "ok", "service": "OZON Crawler"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000)
