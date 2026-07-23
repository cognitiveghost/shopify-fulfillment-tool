"""SKU normalization and order-number sort accuracy (priority: order/SKU accuracy)."""
import pandas as pd
import pytest

from shopify_tool.csv_utils import (
    discover_additional_columns,
    merge_csv_files,
    normalize_sku,
    normalize_sku_for_matching,
    order_number_sort_key,
)


class TestNormalizeSku:
    @pytest.mark.parametrize("raw, expected", [
        (5170.0, "5170"),
        ("5170.0", "5170"),
        ("5170", "5170"),
        (" 5170 ", "5170"),
        ("ABC-123", "ABC-123"),
        ("07", "07"),          # leading zero preserved
        ("07.0", "07"),        # leading zero preserved even through float artifact
        (None, ""),
        ("", ""),
        ("   ", ""),
    ])
    def test_matches_documented_examples(self, raw, expected):
        assert normalize_sku(raw) == expected

    def test_nan_returns_empty_string(self):
        assert normalize_sku(float("nan")) == ""

    def test_pd_na_returns_empty_string(self):
        assert normalize_sku(pd.NA) == ""


class TestNormalizeSkuForMatching:
    @pytest.mark.parametrize("raw, expected", [
        (7, "7"),
        ("07", "7"),
        ("07.0", "7"),
        ("0042", "42"),
        ("ABC-123", "ABC-123"),
        ("01-DM-0379", "01-DM-0379"),
    ])
    def test_matches_documented_examples(self, raw, expected):
        assert normalize_sku_for_matching(raw) == expected

    def test_leading_zero_skus_are_interchangeable(self):
        """The whole point of this function: '07', '7', 7 must collide."""
        assert (
            normalize_sku_for_matching("07")
            == normalize_sku_for_matching("7")
            == normalize_sku_for_matching(7)
        )

    # --- BUGS found while exercising this function (see also barcode_processor) ---

    @pytest.mark.xfail(
        strict=True,
        reason="BUG: a SKU literally 'inf'/'Infinity'/'-inf' makes float() succeed "
               "and int(float(...)) raise an uncaught OverflowError instead of "
               "falling back to the alphanumeric branch like other non-numeric SKUs.",
    )
    @pytest.mark.parametrize("raw", ["inf", "-inf", "Infinity", "INF"])
    def test_infinity_like_sku_does_not_crash(self, raw):
        # Every other non-numeric SKU (e.g. "ABC-123") is returned unchanged by
        # the except-branch; a SKU that happens to spell "inf" should behave the
        # same way, not raise OverflowError and take down whatever exclude-SKU /
        # packing-list filter called it.
        assert normalize_sku_for_matching(raw) == raw

    @pytest.mark.xfail(
        strict=True,
        reason="BUG: scientific-notation-shaped SKUs (e.g. '5E3') are silently "
               "reinterpreted as numbers via float() and mangled to '5000' instead "
               "of being treated as an opaque alphanumeric SKU.",
    )
    def test_scientific_notation_sku_is_not_mangled(self):
        assert normalize_sku_for_matching("5E3") == "5E3"


class TestOrderNumberSortKey:
    def test_extracts_last_digit_run(self):
        assert order_number_sort_key("#1009") == 1009
        assert order_number_sort_key("#1010") == 1010

    def test_no_digits_returns_zero(self):
        assert order_number_sort_key("ORDER-ABC") == 0

    def test_numeric_not_lexicographic_ordering(self):
        orders = ["#9", "#10", "#2", "#1"]
        assert sorted(orders, key=order_number_sort_key) == ["#1", "#2", "#9", "#10"]

    def test_uses_last_digit_run_when_multiple_present(self):
        # e.g. a SKU-suffixed or dated order id -- last run is the actual sequence
        assert order_number_sort_key("ORD-2026-045") == 45


class TestDiscoverAdditionalColumns:
    def test_finds_unmapped_columns(self):
        config = {"orders": {"Name": "Order_Number", "SKU": "SKU"}}
        df = pd.DataFrame({"Name": [1], "SKU": ["A"], "Email": ["x@y.com"]})
        result = discover_additional_columns(df, config, [])
        assert result == [{
            "csv_name": "Email",
            "internal_name": "Email",
            "enabled": False,
            "is_order_level": True,
            "exists_in_df": True,
        }]

    def test_skips_columns_colliding_with_critical_internal_names(self):
        # A CSV column literally named "Quantity" that isn't in the mapping
        # would collide with the critical internal name -- must be skipped,
        # not silently aliased over the real Quantity column.
        config = {"orders": {"Name": "Order_Number"}}
        df = pd.DataFrame({"Name": [1], "Quantity": [5]})
        result = discover_additional_columns(df, config, [])
        assert result == []

    def test_retains_previously_configured_column_missing_from_current_csv(self):
        config = {"orders": {"Name": "Order_Number"}}
        df = pd.DataFrame({"Name": [1]})
        existing = [{"csv_name": "Old_Col", "internal_name": "Old_Col", "enabled": True, "is_order_level": True}]
        result = discover_additional_columns(df, config, existing)
        assert result == [{
            "csv_name": "Old_Col",
            "internal_name": "Old_Col",
            "enabled": True,
            "is_order_level": True,
            "exists_in_df": False,
        }]


class TestMergeCsvFiles:
    def test_merges_and_dedupes_on_keys(self, tmp_path):
        f1 = tmp_path / "a.csv"
        f2 = tmp_path / "b.csv"
        f1.write_text("Name,Lineitem sku\n#1,A1\n#2,A2\n", encoding="utf-8")
        f2.write_text("Name,Lineitem sku\n#2,A2\n#3,A3\n", encoding="utf-8")  # #2 duplicated

        merged = merge_csv_files(
            [str(f1), str(f2)],
            delimiter=",",
            remove_duplicates=True,
            duplicate_keys=["Name", "Lineitem sku"],
        )
        assert sorted(merged["Name"].tolist()) == ["#1", "#2", "#3"]

    def test_empty_file_list_raises(self):
        with pytest.raises(ValueError):
            merge_csv_files([], delimiter=",")
