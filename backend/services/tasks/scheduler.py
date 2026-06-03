"""
定时任务调度器 - APScheduler AsyncIOScheduler
支持 interval / cron / once 三种模式, 动态增删改查
"""
import json
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from backend.utils import get_db, get_logger
from backend.utils.notify import notify_all
from backend.services.platforms.ozon import client as ozon_service

logger = get_logger(__name__)
scheduler = AsyncIOScheduler()

# task_type → 执行函数映射
_TASK_HANDLERS = {}


def register_handler(task_type: str, fn):
    """注册任务类型的执行函数"""
    _TASK_HANDLERS[task_type] = fn


# ============================================================
# DB 查询
# ============================================================

def _get_active_monitors() -> list[dict]:
    conn = get_db()
    rows = conn.execute("SELECT * FROM monitors WHERE status = 'active'").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_tasks() -> list[dict]:
    conn = get_db()
    rows = conn.execute("SELECT * FROM scheduled_tasks ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_task(task_id: int) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM scheduled_tasks WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


# ============================================================
# 快照 & 变化检测
# ============================================================

def _save_snapshot(monitor: dict, result: dict, title: str = "",
                   price: float = None, stock: int = 0, rating=None) -> list[str]:
    """仅在首次快照或价格/库存发生变化时写入, 返回变化列表"""
    conn = get_db()
    last = conn.execute(
        "SELECT price, stock FROM snapshots WHERE monitor_id = ? ORDER BY captured_at DESC LIMIT 1",
        (monitor["id"],),
    ).fetchone()

    old_price = last["price"] if last else None
    old_stock = last["stock"] if last else None

    # 判断是否有变化 (首次快照总是写入)
    has_prev = last is not None
    price_changed = price is not None and old_price is not None and price != old_price
    stock_changed = stock is not None and old_stock is not None and stock != old_stock
    changed = price_changed or stock_changed

    if not has_prev or changed:
        conn.execute(
            """INSERT INTO snapshots
               (monitor_id, snapshot_type, target_id, data_json,
                price, old_price, stock, old_stock, rating, title)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (monitor["id"], monitor["target_type"], monitor["target_id"],
             json.dumps(result, ensure_ascii=False),
             price, old_price, stock, old_stock, rating, title),
        )

    now = datetime.now().isoformat()
    conn.execute(
        "UPDATE monitors SET last_check_at = ?, updated_at = ? WHERE id = ?",
        (now, now, monitor["id"]),
    )
    conn.commit()
    conn.close()

    changes = []
    if price_changed:
        pct = ((price - old_price) / old_price) * 100
        changes.append(f"价格变化: {old_price} -> {price} ({pct:+.1f}%)")
    if stock_changed:
        changes.append(f"库存变化: {old_stock} -> {stock}")
    return changes


def _log_error(monitor: dict, error: str):
    conn = get_db()
    conn.execute(
        "INSERT INTO monitor_logs (monitor_id, level, message) VALUES (?, 'error', ?)",
        (monitor["id"], error),
    )
    conn.execute(
        "UPDATE monitors SET last_error = ?, updated_at = ? WHERE id = ?",
        (error, datetime.now().isoformat(), monitor["id"]),
    )
    conn.commit()
    conn.close()


def _mark_task_run(task_id: int):
    now = datetime.now().isoformat()
    conn = get_db()
    conn.execute(
        "UPDATE scheduled_tasks SET last_run_at = ? WHERE id = ?",
        (now, task_id),
    )
    conn.commit()
    conn.close()


# ============================================================
# 检查逻辑
# ============================================================

async def _check_product(monitor: dict):
    try:
        result = await ozon_service.get_product_detail(monitor["target_id"])
        if "error" in result:
            raise Exception(result["error"])
        title = result.get("name", "")
        price = result.get("price")
        stock = result.get("stock") or 0
        rating = result.get("rating")
        changes = _save_snapshot(monitor, result, title, price, stock, rating)

        if changes:
            logger.info(f"[监控] {title[:30]} 有变化: {changes}")
            await notify_all(f"商品变更: {title[:40]}", "\n".join(changes))
        else:
            logger.info(f"[监控] {title[:30]} 无变化 | 价格={price} 库存={stock}")
    except Exception as e:
        logger.error(f"[监控] 商品 {monitor['target_id']} 检查失败: {e}")
        _log_error(monitor, str(e))


async def _check_seller(monitor: dict):
    try:
        result = await ozon_service.get_seller_products(monitor["target_id"])
        if "error" in result:
            raise Exception(result["error"])
        products = result.get("products", [])
        logger.info(f"[监控] 卖家 {monitor['target_id']}: {len(products)} 个商品")
        for p in products:
            pid = p.get("id", "")
            if not pid:
                continue
            _save_snapshot(monitor, p, title=p.get("name", ""),
                           price=p.get("price"), stock=p.get("stock") or 0,
                           rating=p.get("rating"))
    except Exception as e:
        logger.error(f"[监控] 卖家 {monitor['target_id']} 检查失败: {e}")
        _log_error(monitor, str(e))


async def check_all_monitors():
    """遍历所有 active 监控, 逐个检查并快照"""
    logger.info("[调度器] 开始检查所有监控...")
    monitors = _get_active_monitors()
    if not monitors:
        logger.info("[调度器] 无活跃监控")
        return
    for m in monitors:
        if m["target_type"] == "product":
            await _check_product(m)
        elif m["target_type"] == "seller":
            await _check_seller(m)
    logger.info("[调度器] 检查完成")


register_handler("monitor_check", check_all_monitors)


# ============================================================
# 执行指定任务 (供 API 和调度器内部使用)
# ============================================================

async def execute_task(task_id: int):
    """根据 task_id 立即执行对应任务"""
    task = get_task(task_id)
    if not task:
        raise ValueError(f"任务 {task_id} 不存在")
    handler = _TASK_HANDLERS.get(task["task_type"])
    if not handler:
        raise ValueError(f"未知任务类型: {task['task_type']}")
    await handler()
    _mark_task_run(task_id)
    if task["task_mode"] == "once":
        conn = get_db()
        conn.execute(
            "UPDATE scheduled_tasks SET status = 'completed' WHERE id = ?",
            (task_id,),
        )
        conn.commit()
        conn.close()
        _unschedule_job(task_id)
    logger.info(f"[调度器] 任务 {task_id} ({task['name']}) 执行完成")


# ============================================================
# 动态调度
# ============================================================

def _build_trigger(task: dict):
    """根据 task_mode 构建 APScheduler 触发器"""
    mode = task.get("task_mode", "interval")
    if mode == "cron":
        expr = task.get("cron_expression", "*/30 * * * *")
        return CronTrigger.from_crontab(expr)
    elif mode == "once":
        run_at = task.get("run_at")
        if not run_at:
            raise ValueError("once 模式需要指定 run_at")
        return DateTrigger(run_date=run_at)
    else:
        minutes = task.get("interval_minutes", 30)
        return IntervalTrigger(minutes=minutes)


def _schedule_job(task: dict):
    """将任务加入 APScheduler"""
    job_id = f"task_{task['id']}"
    trigger = _build_trigger(task)
    scheduler.add_job(
        execute_task,
        trigger=trigger,
        args=[task["id"]],
        id=job_id,
        name=task["name"],
        replace_existing=True,
    )
    logger.info(f"[调度器] 已添加任务: {job_id} ({task['name']}) mode={task.get('task_mode', 'interval')}")


def _unschedule_job(task_id: int):
    """从 APScheduler 移除任务"""
    job_id = f"task_{task_id}"
    try:
        scheduler.remove_job(job_id)
        logger.info(f"[调度器] 已移除任务: {job_id}")
    except Exception:
        pass


def run_task_now(task_id: int):
    """立即执行一次任务 (异步触发, 不等待结果)"""
    job_id = f"task_{task_id}"
    try:
        scheduler.modify_job(job_id, next_run_time=datetime.now())
    except Exception:
        pass
    # 如果不在 job store 中, 直接通过 add_job 跑一次
    import asyncio
    try:
        asyncio.ensure_future(execute_task(task_id))
    except Exception:
        pass


# ============================================================
# 调度器生命周期
# ============================================================

def start_scheduler():
    """启动调度器, 从 DB 加载所有 active 定时任务"""
    tasks = [t for t in get_all_tasks() if t["status"] == "active"]
    if not tasks:
        logger.warning("[调度器] 无活跃定时任务, 使用默认 monitor_check (30分钟)")
        conn = get_db()
        conn.execute(
            """INSERT OR IGNORE INTO scheduled_tasks
               (name, task_type, task_mode, interval_minutes)
               VALUES ('商品监控定时检查', 'monitor_check', 'interval', 30)""",
        )
        conn.commit()
        conn.close()
        tasks = get_all_tasks()

    for task in tasks:
        try:
            _schedule_job(task)
        except Exception as e:
            logger.error(f"[调度器] 无法加载任务 {task['id']}: {e}")

    scheduler.start()
    logger.info(f"[调度器] 已启动, 共 {len(tasks)} 个定时任务")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("[调度器] 已停止")


def reload_task(task_id: int):
    """DB 更新后重新加载单个任务"""
    task = get_task(task_id)
    if not task:
        _unschedule_job(task_id)
        return
    if task["status"] == "active":
        _schedule_job(task)
    else:
        _unschedule_job(task_id)
