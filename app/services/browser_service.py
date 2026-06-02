"""
浏览器管理服务 - 多策略绕过 OZON FAB 反爬系统
策略从 config.yaml 读取, 支持热切换
"""
import asyncio
import subprocess
import time
import os
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from app.config import get_config
from app.utils import get_logger

logger = get_logger(__name__)

# 策略函数注册表
STRATEGIES = {}


def _cfg():
    return get_config()


def _make_context_options():
    s = _cfg()["settings"]
    return {
        "user_agent": s["user_agent"],
        "viewport": {"width": s["window_width"], "height": s["window_height"]},
        "locale": s["locale"],
        "timezone_id": s["timezone"],
        "geolocation": {"latitude": s["latitude"], "longitude": s["longitude"]},
        "permissions": ["geolocation"],
        "extra_http_headers": {
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        },
    }


class OzonBrowser:
    """OZON 浏览器会话管理器"""

    def __init__(self):
        self._playwright = None
        self._browser: Browser = None
        self._context: BrowserContext = None
        self._page: Page = None
        self._chrome_proc = None
        self._cookies: dict = {}
        self._ready = False
        self._strategy_used: str = ""

    async def start(self):
        """按 config.yaml 中的 strategy_order 依次尝试各策略"""
        order = _cfg()["browser"]["strategy_order"]
        strategy_map = {
            "native": self._start_native,
            "cdp": self._start_cdp,
        }

        for i, name in enumerate(order):
            if name not in strategy_map:
                logger.warning(f"未知浏览器策略: {name}, 跳过")
                continue

            fn = strategy_map[name]
            label = "Playwright" if name == "native" else "CDP"
            result = await self._try_strategy(fn, label)
            if result:
                self._strategy_used = name
                return True

            if i < len(order) - 1:
                logger.info(f"{label} 未通过, 尝试下一个策略...")
                await self._close_playwright()

        return False

    @property
    def page(self) -> Page:
        return self._page

    @property
    def context(self) -> BrowserContext:
        return self._context

    @property
    def cookies(self) -> dict:
        return self._cookies

    @property
    def is_ready(self) -> bool:
        return self._ready

    async def ensure_ready(self, max_retries: int = None):
        if self._ready:
            return True
        if max_retries is None:
            max_retries = _cfg()["browser"]["challenge"]["max_retries"]

        retry_delay = _cfg()["browser"]["challenge"]["retry_delay"]
        for attempt in range(max_retries):
            logger.info(f"ensure_ready 第 {attempt + 1}/{max_retries} 次...")
            await self.close()
            await asyncio.sleep(retry_delay)
            if await self.start():
                return True

        logger.error(f"ensure_ready: {max_retries} 次重试均失败")
        return False

    async def refresh_cookies(self):
        if self._context:
            cookies = await self._context.cookies()
            self._cookies = {c["name"]: c["value"] for c in cookies}
        return self._cookies

    async def close(self):
        await self._close_playwright()
        if self._chrome_proc:
            try:
                self._chrome_proc.terminate()
            except Exception:
                pass
            self._chrome_proc = None
        self._kill_chrome()
        self._ready = False

    # ============================================================
    # 内部
    # ============================================================

    async def _try_strategy(self, strategy_fn, name: str) -> bool:
        try:
            await strategy_fn()
            return await self._pass_challenge(name)
        except Exception as e:
            logger.error(f"[{name}] 异常: {e}")
            return False

    async def _close_playwright(self):
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    # ============================================================
    # 策略: Playwright 原生
    # ============================================================

    async def _start_native(self):
        cfg = _cfg()
        w, h = cfg["settings"]["window_width"], cfg["settings"]["window_height"]

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=cfg["browser"]["native"]["headless"],
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
                f"--window-size={w},{h}",
                "--window-position=0,0",
            ],
        )
        self._context = await self._browser.new_context(**_make_context_options())
        self._page = await self._context.new_page()

    # ============================================================
    # 策略: CDP
    # ============================================================

    async def _start_cdp(self):
        cfg = _cfg()
        self._launch_chrome()

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.connect_over_cdp(
            f"http://127.0.0.1:{cfg['browser']['cdp']['port']}"
        )
        self._context = await self._browser.new_context(**_make_context_options())
        self._page = await self._context.new_page()

    # ============================================================
    # 反爬挑战
    # ============================================================

    async def _pass_challenge(self, strategy: str) -> bool:
        cfg = _cfg()
        poll = cfg["browser"]["challenge"]["poll_interval"]
        max_attempts = cfg["browser"]["challenge"]["max_attempts"]
        start_time = time.time()

        resp = await self._page.goto(
            "https://www.ozon.ru/",
            wait_until="domcontentloaded",
            timeout=cfg["browser"]["native"]["timeout"] * 1000,
        )
        status = resp.status if resp else 'N/A'
        logger.info(f"[{strategy}] 请求 -> {status} -> 等待中...")

        self._ready = False
        first_check = True
        for i in range(max_attempts):
            await self._page.wait_for_timeout(poll * 1000)
            try:
                await self._page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass

            title = await self._page.title()
            url = self._page.url

            if "OZON" in title.upper() and "Antibot" not in title and "ограничен" not in title.lower():
                self._ready = True
                elapsed = int(time.time() - start_time)
                logger.info(f"[{strategy}] 访问成功 | 耗时: {elapsed}秒 | {title[:40]}")
                break

            if first_check:
                first_check = False
                logger.info(f"[{strategy}] 检测中 | 标题: {title[:40]} | URL: {url[:60]}")
            elif "Antibot" in title:
                logger.info(f"[{strategy}] 仍在挑战页...")

        if not self._ready:
            elapsed = int(time.time() - start_time)
            logger.warning(f"[{strategy}] 超时未通过 | 耗时: {elapsed}秒 | {await self._page.title()[:40]}")

        if self._context:
            cookies = await self._context.cookies()
            self._cookies = {c["name"]: c["value"] for c in cookies}

        return self._ready

    # ============================================================
    # Chrome 进程 (CDP 用)
    # ============================================================

    def _launch_chrome(self):
        cfg = _cfg()
        w, h = cfg["settings"]["window_width"], cfg["settings"]["window_height"]
        self._kill_chrome()
        time.sleep(0.5)

        args = [
            cfg["browser"]["cdp"]["chrome_path"],
            f"--remote-debugging-port={cfg['browser']['cdp']['port']}",
            f"--user-data-dir={os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'chrome_profile')}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-features=Translate",
            "--disable-blink-features=AutomationControlled",
            f"--window-size={w},{h}",
            "--window-position=0,0",
            "about:blank",
        ]
        self._chrome_proc = subprocess.Popen(
            args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        time.sleep(2)

    @staticmethod
    def _kill_chrome():
        subprocess.run(["taskkill", "/F", "/IM", "chrome.exe"], capture_output=True)


# 全局单例
_browser_instance: OzonBrowser = None


async def get_browser() -> OzonBrowser:
    global _browser_instance
    if _browser_instance is None:
        _browser_instance = OzonBrowser()
        await _browser_instance.start()
    return _browser_instance
