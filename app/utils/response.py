"""
统一 API 响应格式工具
"""
from typing import Any, Optional


def success(data: Any = None, **extra) -> dict:
    """成功响应: {"success": True, "data": ...}"""
    result = {"success": True, "data": data}
    result.update(extra)
    return result


def error(message: str, code: int = 500) -> dict:
    """错误响应: {"success": False, "error": ...}"""
    return {"success": False, "error": message, "code": code}


def paginated(
    items: list,
    page: int,
    page_size: int,
    total: int,
) -> dict:
    """
    分页响应.
    自动计算 total_pages, has_next, has_prev.
    """
    total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
    return {
        "success": True,
        "data": {
            "items": items,
            "page": page,
            "page_size": page_size,
            "count": len(items),
            "total": total,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        },
    }
