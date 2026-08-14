import pandas as pd

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
