"""
解析逻辑测试 — 用真实 API 响应样本, 无网络/浏览器依赖
"""
import json
import pytest
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    with open(FIXTURES / name, "r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================
# _parse_price_text
# ============================================================

from backend.services.platforms.ozon.parser import _parse_price_text


class TestParsePriceText:
    def test_int(self):
        assert _parse_price_text(123) == 123.0

    def test_float(self):
        assert _parse_price_text(99.9) == 99.9

    def test_rubles_with_space(self):
        assert _parse_price_text("543 ₽") == 543.0

    def test_rubles_no_space(self):
        assert _parse_price_text("1 234 ₽") == 1234.0

    def test_with_decimal_comma(self):
        assert _parse_price_text("1 234,56 ₽") == 1234.56

    def test_empty_string(self):
        assert _parse_price_text("") is None

    def test_none(self):
        assert _parse_price_text(None) is None

    def test_no_digits(self):
        assert _parse_price_text("нет в наличии") is None


# ============================================================
# _find_in_dict
# ============================================================

from backend.services.platforms.ozon.parser import _find_in_dict


class TestFindInDict:
    def test_shallow(self):
        assert _find_in_dict({"freeRest": 5}, "freeRest") == 5

    def test_nested_one_level(self):
        assert _find_in_dict({"a": {"freeRest": 10}}, "freeRest") == 10

    def test_deeply_nested(self):
        data = {"a": {"b": {"c": {"d": {"freeRest": 3}}}}}
        assert _find_in_dict(data, "freeRest") == 3

    def test_in_list(self):
        data = {"items": [{"x": 1}, {"freeRest": 7}]}
        assert _find_in_dict(data, "freeRest") == 7

    def test_not_found(self):
        assert _find_in_dict({"a": 1}, "freeRest") is None

    def test_empty_dict(self):
        assert _find_in_dict({}, "freeRest") is None

    def test_first_match_wins(self):
        data = {"freeRest": 5, "nested": {"freeRest": 10}}
        assert _find_in_dict(data, "freeRest") == 5


# ============================================================
# parse_product_detail — 商品详情解析
# ============================================================

from backend.services.platforms.ozon.parser import parse_product_detail


class TestParseProductDetail:
    @pytest.fixture(scope="class")
    def data(self):
        return load_fixture("product_detail.json")

    def test_id(self, data):
        result = parse_product_detail(data, "1856972746")
        assert result["id"] == "1856972746"

    def test_name(self, data):
        result = parse_product_detail(data, "1856972746")
        assert "BLANK" in result["name"]
        assert len(result["name"]) > 10

    def test_price_is_float(self, data):
        result = parse_product_detail(data, "1856972746")
        assert isinstance(result["price"], float)
        assert result["price"] > 0

    def test_price_is_card_price_not_original(self, data):
        """应取折扣价 cardPrice(494), 非原价 price(543)"""
        result = parse_product_detail(data, "1856972746")
        assert result["price"] == 494.0

    def test_stock_is_int(self, data):
        result = parse_product_detail(data, "1856972746")
        assert isinstance(result["stock"], int)
        assert result["stock"] >= 0

    def test_rating_is_str(self, data):
        result = parse_product_detail(data, "1856972746")
        assert isinstance(result["rating"], str)
        assert result["rating"] == "5"

    def test_review_count_is_int(self, data):
        result = parse_product_detail(data, "1856972746")
        assert isinstance(result["review_count"], int)
        assert result["review_count"] >= 0

    def test_image_is_url(self, data):
        result = parse_product_detail(data, "1856972746")
        assert result["image"].startswith("https://")

    def test_url_is_constructed(self, data):
        result = parse_product_detail(data, "1856972746")
        assert result["url"] == "https://www.ozon.ru/product/1856972746/"

    def test_all_required_fields_present(self, data):
        result = parse_product_detail(data, "1856972746")
        expected_keys = {"id", "name", "price", "stock", "rating", "review_count", "image", "url"}
        assert set(result.keys()) == expected_keys

    def test_missing_widget_states_returns_defaults(self):
        result = parse_product_detail({}, "999")
        assert result["id"] == "999"
        assert result["name"] == ""
        assert result["price"] is None
        assert result["stock"] is None


# ============================================================
# parse_search_response — 搜索响应解析
# ============================================================

from backend.services.platforms.ozon.parser import parse_search_response


class TestParseSearchResponse:
    @pytest.fixture(scope="class")
    def data(self):
        return load_fixture("search_response.json")

    def test_keyword_preserved(self, data):
        result = parse_search_response(data, "samsung")
        assert result["keyword"] == "samsung"

    def test_products_is_list(self, data):
        result = parse_search_response(data, "samsung")
        assert isinstance(result["products"], list)
        assert len(result["products"]) > 0

    def test_count_matches_products(self, data):
        result = parse_search_response(data, "samsung")
        assert result["count"] == len(result["products"])

    def test_total_pages_is_int(self, data):
        result = parse_search_response(data, "samsung")
        assert isinstance(result["total_pages"], int)
        assert result["total_pages"] >= 1

    def test_each_product_has_required_fields(self, data):
        result = parse_search_response(data, "samsung")
        for p in result["products"]:
            assert "id" in p
            assert "name" in p
            assert "price" in p
            assert "stock" in p
            assert "rating" in p
            assert "review_count" in p
            assert "image" in p
            assert "url" in p

    def test_product_url_starts_with_ozon(self, data):
        result = parse_search_response(data, "samsung")
        for p in result["products"]:
            if p["url"]:
                assert p["url"].startswith("https://www.ozon.ru")

    def test_review_count_is_int(self, data):
        """review_count 应为纯数字, 不含 'отзывов'"""
        result = parse_search_response(data, "samsung")
        for p in result["products"]:
            assert isinstance(p["review_count"], int)

    def test_empty_data(self):
        result = parse_search_response({}, "test")
        assert result["keyword"] == "test"
        assert result["products"] == []
        assert result["count"] == 0


# ============================================================
# _parse_tile_item
# ============================================================

from backend.services.platforms.ozon.parser import _parse_tile_item


class TestParseTileItem:
    def test_default_fields(self):
        """空 tile 返回默认字段"""
        result = _parse_tile_item({})
        assert result["id"] == ""
        assert result["name"] == ""
        assert result["price"] is None
        assert result["stock"] is None
        assert result["rating"] == ""
        assert result["review_count"] == 0
        assert result["image"] == ""
        assert result["url"] == ""

    def test_review_count_no_otzyv_text(self):
        """没有 'отзыв' 文字时 review_count 为 0"""
        result = _parse_tile_item({"mainState": []})
        assert result["review_count"] == 0

    def test_price_from_real_tile(self):
        data = load_fixture("search_response.json")
        ws = data.get("widgetStates", {})
        if isinstance(ws, str):
            ws = json.loads(ws)
        # 找第一个有 tileGrid 的 widget
        for key, state in ws.items():
            if "tileGrid" in key:
                if isinstance(state, str):
                    state = json.loads(state)
                items = state.get("items", [])
                if items:
                    result = _parse_tile_item(items[0])
                    assert result["id"] != ""
                    assert result["name"] != ""
                    assert result["price"] is not None
                    return
        pytest.skip("fixture 中无 tileGrid 数据")
