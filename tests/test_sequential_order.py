"""Reference/sequential number generation accuracy (priority: reference number accuracy)."""
import json

import pandas as pd
import pytest

from shopify_tool.sequential_order import (
    generate_sequential_order_map,
    get_sequential_number,
    load_sequential_order_map,
    regenerate_sequential_order_map,
)


def _analysis_df(order_numbers, statuses=None):
    statuses = statuses or ["Fulfillable"] * len(order_numbers)
    return pd.DataFrame({
        "Order_Number": order_numbers,
        "Order_Fulfillment_Status": statuses,
    })


class TestGenerateSequentialOrderMap:
    def test_assigns_one_indexed_sequence_in_natural_order(self, tmp_path):
        df = _analysis_df(["#9", "#10", "#2", "#1"])
        order_map = generate_sequential_order_map(df, tmp_path)
        assert order_map == {"#1": 1, "#2": 2, "#9": 3, "#10": 4}

    def test_excludes_not_fulfillable_orders(self, tmp_path):
        df = _analysis_df(["#1", "#2"], statuses=["Fulfillable", "Not Fulfillable"])
        order_map = generate_sequential_order_map(df, tmp_path)
        assert order_map == {"#1": 1}

    def test_persists_to_json_and_is_reused_on_second_call(self, tmp_path):
        df = _analysis_df(["#1", "#2"])
        first = generate_sequential_order_map(df, tmp_path)

        json_path = tmp_path / "analysis" / "sequential_order.json"
        assert json_path.exists()
        data = json.loads(json_path.read_text(encoding="utf-8"))
        assert data["order_sequence"] == first
        assert data["total_orders"] == 2

        # Second call with a DIFFERENT df must NOT overwrite -- numbering is
        # meant to be stable across a session so previously printed labels
        # stay valid.
        different_df = _analysis_df(["#5", "#6", "#7"])
        second = generate_sequential_order_map(different_df, tmp_path)
        assert second == first

    def test_force_regenerate_overwrites_existing_map(self, tmp_path):
        df = _analysis_df(["#1", "#2"])
        generate_sequential_order_map(df, tmp_path)
        new_df = _analysis_df(["#5", "#6", "#7"])
        result = regenerate_sequential_order_map(new_df, tmp_path)
        assert result == {"#5": 1, "#6": 2, "#7": 3}

    def test_deduplicates_repeated_order_numbers(self, tmp_path):
        # Multi-line orders repeat the Order_Number across rows.
        df = _analysis_df(["#1", "#1", "#2"])
        order_map = generate_sequential_order_map(df, tmp_path)
        assert order_map == {"#1": 1, "#2": 2}

    def test_drops_nan_order_numbers(self, tmp_path):
        df = _analysis_df(["#1", float("nan")])
        order_map = generate_sequential_order_map(df, tmp_path)
        assert order_map == {"#1": 1}


class TestLoadAndLookup:
    def test_load_missing_file_returns_empty_dict(self, tmp_path):
        assert load_sequential_order_map(tmp_path) == {}

    def test_get_sequential_number_roundtrip(self, tmp_path):
        df = _analysis_df(["#1", "#2"])
        generate_sequential_order_map(df, tmp_path)
        assert get_sequential_number("#1", tmp_path) == 1
        assert get_sequential_number("#2", tmp_path) == 2

    def test_get_sequential_number_for_unknown_order_returns_none(self, tmp_path):
        df = _analysis_df(["#1"])
        generate_sequential_order_map(df, tmp_path)
        assert get_sequential_number("#999", tmp_path) is None

    def test_corrupt_json_returns_empty_dict_not_exception(self, tmp_path):
        json_path = tmp_path / "analysis" / "sequential_order.json"
        json_path.parent.mkdir(parents=True)
        json_path.write_text("{not valid json", encoding="utf-8")
        assert load_sequential_order_map(tmp_path) == {}


class TestStaleMapCollisionRisk:
    @pytest.mark.xfail(
        strict=True,
        reason="BUG (design gap): once sequential_order.json exists, "
               "generate_sequential_order_map() returns the OLD map verbatim "
               "and never assigns numbers to orders that only became "
               "Fulfillable after re-analysis (e.g. a restock). Any caller "
               "that falls back to `idx + 1` for orders missing from the map "
               "(see barcode_processor.generate_barcodes_batch) can then "
               "print a sequential number that collides with one already "
               "assigned to a different order in the persisted map.",
    )
    def test_new_fulfillable_order_after_restock_gets_a_number(self, tmp_path):
        df_before = _analysis_df(["#1", "#2"])
        generate_sequential_order_map(df_before, tmp_path)

        # Analysis reruns after a restock: #3 is now also Fulfillable.
        df_after = _analysis_df(["#1", "#2", "#3"])
        order_map = generate_sequential_order_map(df_after, tmp_path)
        assert "#3" in order_map
