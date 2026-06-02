"""
Webhook 管理路由: 企业微信 / 飞书通知配置的 CRUD
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional
from app.utils import get_db, success

router = APIRouter(prefix="/api/webhooks", tags=["Webhook 管理"])


class WebhookCreate(BaseModel):
    platform: str = Field(..., description="平台: wecom(企业微信) / feishu(飞书)")
    name: str = Field(..., description="备注名称")
    url: str = Field(..., description="Webhook URL")


class WebhookUpdate(BaseModel):
    name: Optional[str] = Field(None, description="备注名称")
    url: Optional[str] = Field(None, description="Webhook URL")
    status: Optional[str] = Field(None, description="状态: active(启用) / disabled(禁用)")


@router.get("", summary="Webhook 列表")
def list_webhooks(
    platform: Optional[str] = Query(None, description="按平台筛选: wecom / feishu"),
):
    conn = get_db()
    if platform:
        rows = conn.execute(
            "SELECT * FROM webhooks WHERE platform = ? ORDER BY created_at DESC",
            (platform,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM webhooks ORDER BY created_at DESC"
        ).fetchall()
    conn.close()
    return success([dict(r) for r in rows])


@router.post("", summary="添加 Webhook")
def add_webhook(item: WebhookCreate):
    if item.platform not in ("wecom", "feishu"):
        raise HTTPException(400, "platform 必须是 'wecom' 或 'feishu'")

    conn = get_db()
    try:
        cursor = conn.execute(
            "INSERT INTO webhooks (platform, name, url) VALUES (?, ?, ?)",
            (item.platform, item.name, item.url),
        )
        conn.commit()
        new_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM webhooks WHERE id = ?", (new_id,)).fetchone()
        return success(dict(row))
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, str(e))
    finally:
        conn.close()


@router.put("/{webhook_id}", summary="更新 Webhook")
def update_webhook(webhook_id: int, item: WebhookUpdate):
    conn = get_db()
    row = conn.execute("SELECT * FROM webhooks WHERE id = ?", (webhook_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Webhook 不存在")

    updates = {}
    if item.name is not None:
        updates["name"] = item.name
    if item.url is not None:
        updates["url"] = item.url
    if item.status is not None:
        if item.status not in ("active", "disabled"):
            conn.close()
            raise HTTPException(400, "status 必须是 'active' 或 'disabled'")
        updates["status"] = item.status

    if not updates:
        conn.close()
        raise HTTPException(400, "没有要更新的字段")

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [webhook_id]

    conn.execute(f"UPDATE webhooks SET {set_clause} WHERE id = ?", values)
    conn.commit()
    row = conn.execute("SELECT * FROM webhooks WHERE id = ?", (webhook_id,)).fetchone()
    conn.close()
    return success(dict(row))


@router.delete("/{webhook_id}", summary="删除 Webhook")
def delete_webhook(webhook_id: int):
    conn = get_db()
    row = conn.execute("SELECT * FROM webhooks WHERE id = ?", (webhook_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Webhook 不存在")

    conn.execute("DELETE FROM webhooks WHERE id = ?", (webhook_id,))
    conn.commit()
    conn.close()
    return success(None, message=f"已删除 webhook '{row['name']}'")


@router.post("/test", summary="测试通知")
async def test_notify(
    platform: str = Query(..., description="平台: wecom / feishu"),
):
    """发送一条测试通知到指定平台的所有启用 webhook"""
    if platform not in ("wecom", "feishu"):
        raise HTTPException(400, "platform 必须是 'wecom' 或 'feishu'")

    from app.utils.notify import wecom_text, feishu_text

    if platform == "wecom":
        await wecom_text("OZON Crawler 测试通知: 企业微信 webhook 配置正常 ✅")
    else:
        await feishu_text("OZON Crawler 测试通知: 飞书 webhook 配置正常 ✅")

    return success(None, message=f"已向 {platform} 发送测试通知")
