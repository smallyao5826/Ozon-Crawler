"""
SQLite 数据库设置 - 简单文件结构, 适合敏捷开发
"""
import sqlite3
import os

# 数据库放在 app/data/ 目录
_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
os.makedirs(_DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(_DATA_DIR, "ozon_monitor.db")


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

        -- 种子数据: 默认 webhook (如已存在则跳过)
        INSERT OR IGNORE INTO webhooks (platform, name, url) VALUES
            ('wecom', '默认企微', 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=26b1857d-a664-4eb4-9172-f994a949bded'),
            ('feishu', '默认飞书', 'https://open.feishu.cn/open-apis/bot/v2/hook/89e96990-71ee-444d-8ece-c9228527c21b');
    """)
    conn.commit()
    conn.close()
