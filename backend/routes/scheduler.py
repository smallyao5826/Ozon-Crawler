"""
定时任务管理路由: CRUD + 立即执行
支持 interval / cron / once 三种模式
"""
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional
from backend.utils import get_db, success, error
from backend.services.tasks.scheduler import (
    get_all_tasks, get_task, run_task_now, reload_task, execute_task,
)

router = APIRouter(prefix="/api/scheduler", tags=["定时任务"])


# ============================================================
# Pydantic 模型
# ============================================================

class TaskCreate(BaseModel):
    name: str = Field(..., description="任务名称")
    task_type: str = Field(..., description="任务类型: monitor_check / custom")
    task_mode: str = Field("interval", description="调度模式: interval / cron / once")
    interval_minutes: Optional[int] = Field(30, description="interval 模式: 间隔分钟数")
    cron_expression: Optional[str] = Field(None, description="cron 模式: 5字段 cron 表达式, 如 '*/30 * * * *'")
    run_at: Optional[str] = Field(None, description="once 模式: 执行时间 ISO格式, 如 '2026-06-03T18:00:00'")


class TaskUpdate(BaseModel):
    name: Optional[str] = Field(None, description="任务名称")
    task_type: Optional[str] = Field(None, description="任务类型")
    task_mode: Optional[str] = Field(None, description="调度模式: interval / cron / once")
    interval_minutes: Optional[int] = Field(None, description="interval 模式: 间隔分钟数")
    cron_expression: Optional[str] = Field(None, description="cron 表达式")
    run_at: Optional[str] = Field(None, description="once 模式: 执行时间")
    status: Optional[str] = Field(None, description="active / paused / completed")


# ============================================================
# CRUD
# ============================================================

@router.get("/tasks", summary="定时任务列表")
def list_tasks():
    return success(get_all_tasks())


@router.get("/tasks/{task_id}", summary="查看任务详情")
def get_task_detail(task_id: int):
    task = get_task(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    return success(task)


@router.post("/tasks", summary="创建定时任务")
def create_task(item: TaskCreate):
    if item.task_mode not in ("interval", "cron", "once"):
        raise HTTPException(400, "task_mode 必须是 interval / cron / once")
    if item.task_mode == "cron" and not item.cron_expression:
        raise HTTPException(400, "cron 模式需提供 cron_expression")
    if item.task_mode == "once" and not item.run_at:
        raise HTTPException(400, "once 模式需提供 run_at")

    conn = get_db()
    cursor = conn.execute(
        """INSERT INTO scheduled_tasks
           (name, task_type, task_mode, interval_minutes, cron_expression, run_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (item.name, item.task_type, item.task_mode,
         item.interval_minutes, item.cron_expression, item.run_at),
    )
    conn.commit()
    task_id = cursor.lastrowid
    conn.close()

    reload_task(task_id)
    return success(get_task(task_id), message="任务已创建并调度")


@router.put("/tasks/{task_id}", summary="更新定时任务")
def update_task(task_id: int, item: TaskUpdate):
    task = get_task(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")

    updates = {}
    for field in ("name", "task_type", "task_mode", "interval_minutes",
                  "cron_expression", "run_at", "status"):
        val = getattr(item, field, None)
        if val is not None:
            updates[field] = val

    if not updates:
        raise HTTPException(400, "没有要更新的字段")

    updates["updated_at"] = datetime.now().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [task_id]

    conn = get_db()
    conn.execute(f"UPDATE scheduled_tasks SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()

    reload_task(task_id)
    return success(get_task(task_id), message="任务已更新")


@router.delete("/tasks/{task_id}", summary="删除定时任务")
def delete_task(task_id: int):
    task = get_task(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")

    conn = get_db()
    conn.execute("DELETE FROM scheduled_tasks WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()

    from backend.services.tasks.scheduler import _unschedule_job
    _unschedule_job(task_id)
    return success(None, message=f"已删除任务 '{task['name']}'")


# ============================================================
# 执行控制
# ============================================================

@router.post("/tasks/{task_id}/run", summary="立即执行任务")
async def trigger_task(task_id: int):
    """立即触发一次定时任务 (后台执行, 立即返回)"""
    import asyncio
    task = get_task(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    asyncio.create_task(execute_task(task_id))
    return success(None, message=f"任务 '{task['name']}' 已触发, 后台执行中")
