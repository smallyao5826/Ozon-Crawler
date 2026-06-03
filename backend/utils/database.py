"""
SQLite 数据库设置 - 简单文件结构, 适合敏捷开发
"""
import sqlite3
import os

# 数据库文件
_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
os.makedirs(_DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(_DATA_DIR, "database.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        -- 监控目标表 (商品/店铺)
        CREATE TABLE IF NOT EXISTS monitors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,                    -- 备注名
            platform TEXT NOT NULL DEFAULT 'ozon', -- 平台: ozon / wildberries 等
            target_type TEXT NOT NULL,             -- 'product' 或 'seller'
            target_id TEXT NOT NULL,               -- 商品ID 或 卖家ID
            target_url TEXT,                       -- 完整URL
            status TEXT DEFAULT 'active',          -- active / paused / error
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_check_at DATETIME,
            last_error TEXT
        );

        -- 数据快照表 (记录每次抓取的价格/库存等变化)
        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            monitor_id INTEGER NOT NULL,
            snapshot_type TEXT NOT NULL,            -- 'product' 或 'seller_list'
            target_id TEXT NOT NULL,                -- 商品ID 或 卖家ID
            data_json TEXT NOT NULL,                -- 完整的 JSON 数据
            price REAL,                             -- 当前价格
            old_price REAL,                         -- 上次价格
            stock INTEGER,                          -- 库存
            old_stock INTEGER,                      -- 上次库存
            rating REAL,                            -- 评分
            title TEXT,                             -- 商品标题
            captured_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (monitor_id) REFERENCES monitors(id) ON DELETE CASCADE
        );

        -- 监控日志
        CREATE TABLE IF NOT EXISTS monitor_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            monitor_id INTEGER NOT NULL,
            level TEXT DEFAULT 'info',             -- info / warning / error
            message TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (monitor_id) REFERENCES monitors(id) ON DELETE CASCADE
        );

        -- 定时任务配置表
        CREATE TABLE IF NOT EXISTS scheduled_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            task_type TEXT NOT NULL,               -- 'monitor_check' / 'custom' 等
            task_mode TEXT DEFAULT 'interval',     -- 'interval' / 'cron' / 'once'
            interval_minutes INTEGER DEFAULT 30,   -- interval 模式下的分钟间隔
            cron_expression TEXT,                  -- cron 模式: "*/30 * * * *" (5字段)
            run_at DATETIME,                       -- once 模式: 指定执行时间
            status TEXT DEFAULT 'active',
            last_run_at DATETIME,
            next_run_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        -- Webhook 配置表
        CREATE TABLE IF NOT EXISTS webhooks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,                 -- 'wecom' / 'feishu'
            name TEXT,                              -- 备注名
            url TEXT NOT NULL,                      -- Webhook URL
            status TEXT DEFAULT 'active',           -- active / disabled
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        -- 索引
        CREATE INDEX IF NOT EXISTS idx_snapshots_monitor ON snapshots(monitor_id);
        CREATE INDEX IF NOT EXISTS idx_snapshots_target ON snapshots(target_id);
        CREATE INDEX IF NOT EXISTS idx_snapshots_captured ON snapshots(captured_at);
        CREATE INDEX IF NOT EXISTS idx_monitors_status ON monitors(status);

    """)
    # 迁移: 为已有表补充新字段
    for table, col, spec in [
        ("scheduled_tasks", "task_mode", "TEXT DEFAULT 'interval'"),
        ("scheduled_tasks", "cron_expression", "TEXT"),
        ("scheduled_tasks", "run_at", "DATETIME"),
        ("monitors", "platform", "TEXT NOT NULL DEFAULT 'ozon'"),
    ]:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {spec}")
        except Exception:
            pass
    conn.commit()
    conn.close()
