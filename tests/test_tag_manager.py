import pandas as pd
import pytest

from shopify_tool.barcode_processor import format_tags_for_barcode
from shopify_tool.tag_manager import expand_to_order_rows, merge_tags


class TestMergeTags:
    def test_merges_json_string_rows_deduped(self):
        assert merge_tags(['["A", "B"]', '["B", "C"]']) == '["A", "B", "C"]'

    def test_merges_native_list_rows(self):
        assert merge_tags([["A"], ["B"]]) == '["A", "B"]'

    def test_single_row_native_list_round_trips_clean(self):
        assert merge_tags([["MASK+BOX_ORDER"]]) == '["MASK+BOX_ORDER"]'

    def test_output_never_leaks_raw_literal_through_barcode_formatter(self):
        # Regression: barcode_generator_widget.py used to merge an order's
        # per-line-item Internal_Tags with a naive `str(val).split(',')`.
        # For an order with multiple tagged line items stored as native
        # lists, that reconstructed a comma-joined string of partial list
        # reprs (e.g. "['MASK+BOX_ORDER'], ['REGULAR_BOX']") which
        # format_tags_for_barcode's ast.literal_eval parsed as a *tuple* of
        # lists (not a list), failed its isinstance(list) check, and fell
        # through to leaking the raw bracketed literal onto the printed
        # label. merge_tags must hand back a single clean JSON array instead.
        merged = merge_tags([["MASK+BOX_ORDER"], ["REGULAR_BOX"]])
        assert format_tags_for_barcode(merged) == "MASK+BOX_ORDER|REGULAR_BOX"


class TestExpandToOrderRows:
    def _df(self):
        return pd.DataFrame({
            "Order_Number": ["A", "A", "B", "C", "C"],
            "SKU": ["S1", "S2", "S1", "S1", "S2"],
        })

    def test_single_line_mask_expands_to_all_lines_of_that_order(self):
        df = self._df()
        mask = (df["Order_Number"] == "A") & (df["SKU"] == "S1")  # matches only row 0
        result = expand_to_order_rows(df, mask)
        assert result.tolist() == [True, True, False, False, False]

    def test_multi_order_mask_expands_each_order_independently(self):
        df = self._df()
        mask = df.index.isin([0, 3])  # row 0 (order A), row 3 (order C)
        result = expand_to_order_rows(df, pd.Series(mask, index=df.index))
        assert result.tolist() == [True, True, False, True, True]

    def test_mask_matching_zero_rows_returns_all_false(self):
        df = self._df()
        mask = df["Order_Number"] == "DOES-NOT-EXIST"
        result = expand_to_order_rows(df, mask)
        assert not result.any()


def test_validator_rejects_empty_category_label():
    from shopify_tool.tag_manager import validate_tag_categories_v2

    config = {
        "version": 2,
        "categories": {
            "packaging": {
                "label": "", "color": "#4CAF50", "order": 1, "tags": [],
                "sku_writeoff": {"enabled": False, "mappings": {}},
            }
        },
    }
    is_valid, errors = validate_tag_categories_v2(config)
    assert is_valid is False
    assert any("empty label" in e for e in errors)


def test_validator_rejects_whitespace_only_label():
    from shopify_tool.tag_manager import validate_tag_categories_v2

    config = {
        "version": 2,
        "categories": {
            "packaging": {
                "label": "   ", "color": "#4CAF50", "order": 1, "tags": [],
                "sku_writeoff": {"enabled": False, "mappings": {}},
            }
        },
    }
    is_valid, _errors = validate_tag_categories_v2(config)
    assert is_valid is False


# --- validate_tag_categories_v2 (Audit 10, part A) ----------------------------------------


def _v2(**category):
    base = {"label": "Box", "color": "#112233", "tags": ["BOX"], "order": 1}
    base.update(category)
    return {"version": 2, "categories": {"packaging": base}}


class TestValidateTagCategoriesV2:
    def test_a_well_formed_config_is_valid(self):
        from shopify_tool.tag_manager import validate_tag_categories_v2

        config = _v2(sku_writeoff={"enabled": True, "mappings": {"BOX": [{"sku": "PKG", "quantity": 2}]}})
        assert validate_tag_categories_v2(config) == (True, [])

    @pytest.mark.parametrize(
        ("config", "expected"),
        [
            ({"categories": {}}, "Missing 'version'"),
            ({"version": 2}, "Missing 'categories'"),
            ({"version": 2, "categories": []}, "'categories' must be a dictionary"),
            ({"version": 2, "categories": {"packaging": "x"}}, "Category 'packaging' config must be a dictionary"),
            (_v2(label=" "), "has an empty label"),
            (_v2(color="red"), "invalid color format: red"),
            (_v2(tags="BOX"), "tags must be a list"),
            (_v2(order="1"), "order must be an integer"),
            (_v2(sku_writeoff="x"), "sku_writeoff must be a dictionary"),
            (_v2(sku_writeoff={"mappings": {}}), "missing 'enabled' field"),
            (_v2(sku_writeoff={"enabled": True, "mappings": []}), "mappings must be a dictionary"),
            (_v2(sku_writeoff={"enabled": True, "mappings": {"BOX": "PKG"}}), "must be a list"),
            (_v2(sku_writeoff={"enabled": True, "mappings": {"BOX": ["PKG"]}}), "must be a dictionary"),
            (_v2(sku_writeoff={"enabled": True, "mappings": {"BOX": [{"quantity": 1}]}}), "missing 'sku' field"),
            (_v2(sku_writeoff={"enabled": True, "mappings": {"BOX": [{"sku": "P"}]}}), "missing 'quantity' field"),
            (_v2(sku_writeoff={"enabled": True, "mappings": {"BOX": [{"sku": "P", "quantity": "2"}]}}),
             "quantity must be a number"),
            (_v2(sku_writeoff={"enabled": True, "mappings": {"BOX": [{"sku": "P", "quantity": 0}]}}),
             "quantity must be positive"),
        ],
    )
    def test_each_kind_of_mistake_is_named(self, config, expected):
        from shopify_tool.tag_manager import validate_tag_categories_v2

        valid, errors = validate_tag_categories_v2(config)
        assert valid is False
        assert any(expected in e for e in errors), errors

    def test_a_missing_field_is_named_once(self):
        from shopify_tool.tag_manager import validate_tag_categories_v2

        config = {"version": 2, "categories": {"packaging": {"color": "#112233", "tags": [], "order": 1}}}
        valid, errors = validate_tag_categories_v2(config)
        assert valid is False and errors == ["Category 'packaging' missing required field 'label'"]

    def test_a_tag_in_two_categories_names_both(self):
        from shopify_tool.tag_manager import validate_tag_categories_v2

        config = _v2()
        config["categories"]["status"] = {"label": "S", "color": "#445566", "tags": ["BOX"], "order": 2}
        valid, errors = validate_tag_categories_v2(config)
        assert not valid and "'packaging' and 'status'" in errors[0]


class TestV2Helpers:
    def test_normalise_accepts_both_shapes(self):
        from shopify_tool.tag_manager import (
            _normalize_tag_categories,
            get_category_tags,
            get_tag_color,
        )

        v1 = {"packaging": {"tags": ["BOX"], "color": "#112233"}}
        v2 = {"version": 2, "categories": v1}
        assert _normalize_tag_categories(v1) == v1 == _normalize_tag_categories(v2)
        assert _normalize_tag_categories({}) == {}
        assert get_category_tags("packaging", v2) == ["BOX"] and get_category_tags("nope", v2) == []
        assert get_tag_color("BOX", v2) == "#112233"
        assert get_tag_color("UNKNOWN", v2) == "#9E9E9E"  # not in any category: "custom" has no colour here
