# Smart Ecom Automation(Ozon-Crawler)

OZON 跨境平台商品监控爬虫，支持搜索、商品详情、店铺商品抓取，价格/库存变化监控，企业微信/飞书通知。

## 技术栈

- **FastAPI** — Web API 框架
- **Playwright** — 浏览器反爬绕过
- **curl_cffi** — TLS 指纹伪装
- **SQLite** — 数据存储

## 快速开始

```bash
pip install -r requirements.txt
playwright install chromium
python -m uvicorn backend.main:app --reload
```

启动后访问 http://localhost:8000/docs 查看 API 文档。

## API 接口

| 接口 | 说明 |
|------|------|
| `GET /api/ozon/search?q=keyword` | 商品搜索 |
| `GET /api/ozon/product/parse?q=<url>` | 商品链接解析 |
| `GET /api/ozon/product/{id}` | 商品详情 (按ID) |
| `GET /api/ozon/seller?q=<url>` | 店铺信息 |
| `POST /api/monitor` | 添加监控 |
| `GET /api/monitor` | 监控列表 |

## 项目结构

```
backend/
├── main.py                  # FastAPI 入口
├── config.yaml              # 策略配置 (热加载)
├── routes/                  # API 路由
│   ├── ozon.py              # OZON 搜索/商品/店铺
│   ├── monitor.py           # 监控管理
│   └── webhook.py           # Webhook 管理
├── services/                # 业务服务
│   ├── core/                # 核心服务
│   │   ├── browser.py       # Playwright 浏览器 & 反爬
│   │   ├── config.py        # 配置热加载
│   │   └── http.py          # HTTP 请求 (curl_cffi)
│   ├── platforms/           # 平台实现
│   │   ├── base.py          # 平台抽象基类
│   │   └── ozon/
│   │       ├── client.py    # API 调用 & 业务编排
│   │       └── parser.py    # 响应数据解析
│   └── tasks/
│       └── scheduler.py     # 定时任务
├── tests/                   # 测试
│   ├── fixtures/            # API 响应固件
│   ├── test_parser.py       # 解析器测试 (37)
│   └── test_client.py       # 客户端测试 (17)
└── utils/                   # 工具
    ├── database.py          # SQLite 数据库
    ├── notify.py            # 企微/飞书通知
    ├── response.py          # 统一响应格式
    └── logger.py            # 日志
```

## 配置

编辑 `backend/config.yaml` 调整策略顺序、超时、反爬参数，无需重启服务。

```yaml
api:
  strategy_order:  # 请求策略优先级
    - playwright   # 浏览器 fetch (推荐)
    - curl_cffi    # TLS 指纹伪装
```

## 测试

```bash
pytest backend/tests/ -v
```
