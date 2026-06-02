# Smart Ecom Automation

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
python app/main.py
```

启动后访问 http://localhost:8000/docs 查看 API 文档。

## 项目结构

```
app/
├── main.py              # FastAPI 入口
├── config.yaml           # 策略配置 (热加载)
├── config.py             # 配置读取
├── routes/               # API 路由
│   ├── ozon.py           # 搜索/商品/店铺
│   ├── monitor.py        # 监控管理
│   └── webhook.py        # Webhook 管理
├── services/             # 业务服务
│   ├── browser_service.py # 浏览器反爬
│   ├── ozon_service.py   # OZON 接口
│   └── http_service.py   # HTTP 请求 (curl_cffi)
└── utils/                # 工具
    ├── database.py       # 数据库
    ├── notify.py         # 企微/飞书通知
    ├── response.py       # 统一响应
    └── logger.py         # 日志
```

## 配置

编辑 `app/config.yaml` 调整浏览器策略、API 策略、超时等参数，无需重启。
