"""
Client 层测试 — Mock 外部依赖 (浏览器/HTTP), 测业务编排和异常处理
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    with open(FIXTURES / name, "r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================
# extract_product_id
# ============================================================

from backend.services.platforms.ozon.client import extract_product_id


class TestExtractProductId:
    def test_numeric_id(self):
        assert extract_product_id("https://www.ozon.ru/product/12345/") == "12345"

    def test_slug_and_numeric_id(self):
        result = extract_product_id(
            "https://www.ozon.ru/product/kompakt-disk-blank-jones-1856972746/"
        )
        assert result == "1856972746"

    def test_with_query_params(self):
        result = extract_product_id(
            "https://www.ozon.ru/product/12345/?__rr=2&abt_att=1&at=abc123"
        )
        assert result == "12345"

    def test_no_product_in_url(self):
        assert extract_product_id("https://www.ozon.ru/seller/muzykalnyy-kiosk/") == ""

    def test_not_a_url(self):
        assert extract_product_id("not-a-url") == ""

    def test_product_without_id(self):
        """没有数字 ID 的 product URL 返回空"""
        assert extract_product_id("https://www.ozon.ru/product/some-slug/") == ""


# ============================================================
# extract_seller_slug
# ============================================================

from backend.services.platforms.ozon.client import extract_seller_slug


class TestExtractSellerSlug:
    def test_simple_slug(self):
        assert extract_seller_slug("https://www.ozon.ru/seller/muzykalnyy-kiosk/") == "muzykalnyy-kiosk"

    def test_slug_with_params(self):
        result = extract_seller_slug(
            "https://www.ozon.ru/seller/blank-2121713/?__rr=1&abt_att=1"
        )
        assert result == "blank-2121713"

    def test_no_seller_in_url(self):
        assert extract_seller_slug("https://www.ozon.ru/product/12345/") == ""

    def test_not_a_url(self):
        assert extract_seller_slug("random-text") == ""


# ============================================================
# _fetch_api — 策略编排
# ============================================================

from backend.services.platforms.ozon.client import _fetch_api


class TestFetchApi:
    @pytest.fixture
    def mock_browser(self):
        browser = MagicMock()
        browser.refresh_cookies = AsyncMock(return_value={"cookie": "test"})
        browser.page = MagicMock()
        return browser

    @pytest.mark.asyncio
    @patch("backend.services.platforms.ozon.client.api_get_json")
    @patch("backend.services.platforms.ozon.client.get_config")
    async def test_uses_first_strategy_when_successful(self, mock_config, mock_http, mock_browser):
        """第一个策略成功时直接返回, 不尝试后续策略"""
        mock_config.return_value = {
            "api": {
                "strategy_order": ["playwright", "curl_cffi"],
                "playwright": {"timeout": 10},
            }
        }
        mock_browser.page.evaluate = AsyncMock(return_value={
            "_status": 200,
            "_body": '{"result": "success"}',
        })

        result = await _fetch_api("http://test/api", mock_browser)
        assert result == {"result": "success"}
        mock_http.assert_not_called()  # curl_cffi 不应该被调用

    @pytest.mark.asyncio
    @patch("backend.services.platforms.ozon.client.api_get_json")
    @patch("backend.services.platforms.ozon.client.get_config")
    async def test_falls_back_to_second_strategy(self, mock_config, mock_http, mock_browser):
        """第一个策略失败时降级到第二个"""
        mock_config.return_value = {
            "api": {
                "strategy_order": ["playwright", "curl_cffi"],
                "playwright": {"timeout": 10},
                "curl_cffi": {
                    "timeout": 10,
                    "max_retries": 1,
                    "impersonate": "chrome124",
                },
            }
        }
        mock_http.return_value = {"result": "from_curl"}
        mock_browser.page.evaluate = AsyncMock(return_value={
            "_status": 404,
            "_body": "not found",
        })

        result = await _fetch_api("http://test/api", mock_browser)
        assert result == {"result": "from_curl"}
        mock_http.assert_called_once()  # curl_cffi 被调用了


# ============================================================
# get_product_detail — 商品详情 (Mock 完整链路)
# ============================================================

from backend.services.platforms.ozon.client import get_product_detail, parse_product_url


class TestGetProductDetail:
    @pytest.fixture
    def product_fixture(self):
        return load_fixture("product_detail.json")

    @pytest.mark.asyncio
    @patch("backend.services.platforms.ozon.client.get_config")
    @patch("backend.services.platforms.ozon.client.get_browser")
    async def test_parse_product_url_no_id(self, mock_get_browser, mock_config):
        """无法提取 ID 时返回 error"""
        result = await parse_product_url("https://www.ozon.ru/seller/shop/")
        assert "error" in result
        assert "无法从 URL 提取商品 ID" in result["error"]

    @pytest.mark.asyncio
    @patch("backend.services.platforms.ozon.client.get_config")
    @patch("backend.services.platforms.ozon.client.get_browser")
    async def test_parse_product_url_with_real_url(self, mock_get_browser, mock_config, product_fixture):
        """正常提取 ID 并调用详情"""
        mock_browser = MagicMock()
        mock_browser.ensure_ready = AsyncMock()
        mock_browser.page = MagicMock()
        mock_browser.page.evaluate = AsyncMock(return_value={
            "_status": 200,
            "_body": json.dumps(product_fixture),
        })
        mock_get_browser.return_value = mock_browser
        mock_config.return_value = {
            "api": {
                "strategy_order": ["playwright"],
                "playwright": {"timeout": 10},
            }
        }

        result = await parse_product_url(
            "https://www.ozon.ru/product/kompakt-disk-blank-jones-1856972746/"
        )
        assert "error" not in result
        assert result["id"] == "1856972746"
        assert result["price"] == 494.0
        assert result["stock"] == 2
        assert result["rating"] == "5"
        assert result["review_count"] == 8

    @pytest.mark.asyncio
    @patch("backend.services.platforms.ozon.client.get_config")
    @patch("backend.services.platforms.ozon.client.get_browser")
    async def test_api_exception_returns_error(self, mock_get_browser, mock_config):
        """API 异常时返回 error 而非抛出"""
        mock_browser = MagicMock()
        mock_browser.ensure_ready = AsyncMock()
        mock_browser.page = MagicMock()
        mock_browser.page.evaluate = AsyncMock(side_effect=Exception("网络超时"))
        mock_get_browser.return_value = mock_browser

        mock_config.return_value = {
            "api": {
                "strategy_order": ["playwright"],
                "playwright": {"timeout": 10},
            }
        }

        result = await get_product_detail("12345")
        assert "error" in result
        assert result["product_id"] == "12345"


# ============================================================
# get_seller_info — 店铺解析
# ============================================================

from backend.services.platforms.ozon.client import get_seller_info


class TestGetSellerInfo:
    @pytest.fixture
    def seller_fixture(self):
        return load_fixture("seller_products.json")

    @pytest.mark.asyncio
    @patch("backend.services.platforms.ozon.client.get_config")
    @patch("backend.services.platforms.ozon.client.get_browser")
    async def test_direct_seller_url(self, mock_get_browser, mock_config, seller_fixture):
        """直接传入 /seller/ URL"""
        mock_browser = MagicMock()
        mock_browser.ensure_ready = AsyncMock()
        mock_browser.page = MagicMock()
        mock_browser.page.evaluate = AsyncMock(return_value={
            "_status": 200,
            "_body": json.dumps(seller_fixture),
        })
        mock_get_browser.return_value = mock_browser
        mock_config.return_value = {
            "api": {
                "strategy_order": ["playwright"],
                "playwright": {"timeout": 10},
            }
        }

        result = await get_seller_info(
            "https://www.ozon.ru/seller/muzykalnyy-kiosk/"
        )
        assert "error" not in result
        assert result["seller_slug"] == "muzykalnyy-kiosk"
        assert "products" in result
        assert "total_pages" in result

    def test_no_seller_in_url(self):
        """无法提取卖家时返回 error"""
        assert extract_seller_slug("https://www.ozon.ru/product/12345/") == ""
        assert extract_seller_slug("random-text") == ""
