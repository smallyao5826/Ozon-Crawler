"""
监控路由: 添加/删除/查看监控目标, 数据快照
"""
import json
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional
from backend.utils import get_db, success, error, paginated
from backend.services.platforms.ozon import client as ozon_service

router = APIRouter(prefix="/api/monitor", tags=["监控管理"])


# ============================================================
# Pydantic 模型
# ============================================================

class MonitorCreate(BaseModel):
    """添加监控请求体"""
    name: str = Field(..., description="备注名称")
    target_type: str = Field(..., description="类型: product(商品) 或 seller(卖家)")
    target_id: str = Field(..., description="商品ID 或 卖家ID")


class MonitorUpdate(BaseModel):
    """更新监控请求体"""
    name: Optional[str] = Field(None, description="备注名称")
    status: Optional[str] = Field(None, description="状态: active(启用) / paused(暂停) / error(异常)")


# ============================================================
# 监控目标 CRUD
# ============================================================

@router.get("/list", summary="监控列表")
def list_monitors(
    status: Optional[str] = Query(None, description="按状态筛选: active / paused / error"),
):
    """获取所有监控目标, 可按状态筛选"""
    conn = get_db()
    if status:
        rows = conn.execute(
            "SELECT * FROM monitors WHERE status = ? ORDER BY created_at DESC", (status,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM monitors ORDER BY created_at DESC"
        ).fetchall()
    conn.close()
    return success([dict(r) for r in rows])


@router.post("/add", summary="添加监控")
def add_monitor(item: MonitorCreate):
    """添加商品或卖家到监控列表"""
    if item.target_type not in ("product", "seller"):
        raise HTTPException(400, "target_type 必须是 'product' 或 'seller'")

    conn = get_db()
    try:
        cursor = conn.execute(
            """INSERT INTO monitors (name, target_type, target_id, target_url)
               VALUES (?, ?, ?, ?)""",
            (
                item.name,
                item.target_type,
                item.target_id,
                f"https://www.ozon.ru/{item.target_type}/{item.target_id}",
            ),
        )
        conn.commit()
        new_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM monitors WHERE id = ?", (new_id,)).fetchone()
        return success(dict(row))
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, str(e))
    finally:
        conn.close()


@router.put("/{monitor_id}", summary="更新监控")
def update_monitor(monitor_id: int, item: MonitorUpdate):
    """更新监控目标的名称或状态"""
    conn = get_db()
    updates = {}
    if item.name is not None:
        updates["name"] = item.name
    if item.status is not None:
        updates["status"] = item.status

    if not updates:
        raise HTTPException(400, "没有要更新的字段")

    updates["updated_at"] = datetime.now().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [monitor_id]

    conn.execute(f"UPDATE monitors SET {set_clause} WHERE id = ?", values)
    conn.commit()
    row = conn.execute("SELECT * FROM monitors WHERE id = ?", (monitor_id,)).fetchone()
    conn.close()

    if not row:
        raise HTTPException(404, "监控目标不存在")
    return {"success": True, "data": dict(row)}


@router.delete("/{monitor_id}", summary="删除监控")
def delete_monitor(monitor_id: int):
    """删除监控目标及其所有快照数据"""
    conn = get_db()
    row = conn.execute("SELECT * FROM monitors WHERE id = ?", (monitor_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "监控目标不存在")

    conn.execute("DELETE FROM monitors WHERE id = ?", (monitor_id,))
    conn.commit()
    conn.close()
    return success(None, message=f"已删除监控 '{row['name']}'")


# ============================================================
# 数据快照
# ============================================================

@router.post("/{monitor_id}/snapshot", summary="抓取快照")
async def take_snapshot(monitor_id: int):
    """立即对监控目标抓取一次数据快照, 记录价格/库存变化"""
    conn = get_db()
    monitor = conn.execute(
        "SELECT * FROM monitors WHERE id = ?", (monitor_id,)
    ).fetchone()

    if not monitor:
        conn.close()
        raise HTTPException(404, "监控目标不存在")

    monitor = dict(monitor)

    try:
        if monitor["target_type"] == "product":
            result = await ozon_service.get_product_detail(monitor["target_id"])
            title = result.get("name", "")
            price = result.get("price")
            stock = result.get("stock") or 0
            rating = result.get("rating")
        else:
            result = await ozon_service.get_seller_products(monitor["target_id"])
            products = result.get("products", [])
            title = f"卖家 {monitor['target_id']}"
            price = None
            stock = len(products)
            rating = None

        last_snapshot = conn.execute(
            """SELECT price, stock FROM snapshots
               WHERE monitor_id = ? ORDER BY captured_at DESC LIMIT 1""",
            (monitor_id,),
        ).fetchone()

        old_price = last_snapshot["price"] if last_snapshot else None
        old_stock = last_snapshot["stock"] if last_snapshot else None

        cursor = conn.execute(
            """INSERT INTO snapshots
               (monitor_id, snapshot_type, target_id, data_json,
                price, old_price, stock, old_stock, rating, title)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                monitor_id,
                monitor["target_type"],
                monitor["target_id"],
                json.dumps(result, ensure_ascii=False),
                price, old_price, stock, old_stock, rating, title,
            ),
        )

        conn.execute(
            "UPDATE monitors SET last_check_at = ?, updated_at = ? WHERE id = ?",
            (datetime.now().isoformat(), datetime.now().isoformat(), monitor_id),
        )
        conn.commit()

        snapshot_id = cursor.lastrowid
        snapshot = conn.execute(
            "SELECT * FROM snapshots WHERE id = ?", (snapshot_id,)
        ).fetchone()

        changes = []
        if price is not None and old_price is not None and price != old_price:
            change_pct = ((price - old_price) / old_price) * 100
            changes.append(f"价格变化: {old_price} -> {price} ({change_pct:+.1f}%)")
        if stock is not None and old_stock is not None and stock != old_stock:
            changes.append(f"库存变化: {old_stock} -> {stock}")

        return success(dict(snapshot), changes=changes if changes else None)

    except Exception as e:
        conn.execute(
            "INSERT INTO monitor_logs (monitor_id, level, message) VALUES (?, ?, ?)",
            (monitor_id, "error", str(e)),
        )
        conn.execute(
            "UPDATE monitors SET last_error = ?, updated_at = ? WHERE id = ?",
            (str(e), datetime.now().isoformat(), monitor_id),
        )
        conn.commit()
        conn.close()
        raise HTTPException(500, f"快照失败: {e}")

    finally:
        if conn:
            conn.close()


@router.get("/{monitor_id}/snapshots", summary="快照历史")
def get_snapshots(
    monitor_id: int,
    limit: int = Query(20, description="返回条数"),
):
    """获取监控目标的快照历史记录"""
    conn = get_db()
    snapshots = conn.execute(
        """SELECT * FROM snapshots
           WHERE monitor_id = ?
           ORDER BY captured_at DESC LIMIT ?""",
        (monitor_id, limit),
    ).fetchall()
    conn.close()
    return success([dict(s) for s in snapshots])


@router.get("/{monitor_id}/changes", summary="变化记录")
def get_changes(monitor_id: int):
    """获取价格或库存发生过变化的快照记录"""
    conn = get_db()
    changes = conn.execute(
        """SELECT * FROM snapshots
           WHERE monitor_id = ?
           AND (price != old_price OR stock != old_stock)
           AND old_price IS NOT NULL
           ORDER BY captured_at DESC LIMIT 50""",
        (monitor_id,),
    ).fetchall()
    conn.close()
    return success([dict(c) for c in changes], count=len(changes))
