from shopify_tool.barcode_processor import format_tags_for_barcode
from shopify_tool.tag_manager import merge_tags


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
