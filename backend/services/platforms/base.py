"""
平台爬虫抽象基类 (预留)
"""
from abc import ABC, abstractmethod


class BasePlatform(ABC):
    """所有平台爬虫的抽象基类"""

    @abstractmethod
    async def search_products(self, keyword: str, page: int = 1, **kwargs) -> dict:
        ...

    @abstractmethod
    async def get_product_detail(self, product_id: str) -> dict:
        ...

    @abstractmethod
    async def get_seller_info(self, url: str) -> dict:
        ...

    @abstractmethod
    async def get_seller_products(self, seller_id: str, page: int = 1) -> dict:
        ...
