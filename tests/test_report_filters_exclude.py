import pandas as pd

from shopify_tool.report_filters import exclude_skus, parse_sku_list


def test_parse_sku_list_accepts_a_string_or_a_list():
    assert parse_sku_list("07, 8 ,") == ["07", "8"]
    assert parse_sku_list([" 07 ", "", None, 8]) == ["07", "8"]
    assert parse_sku_list(None) == []
    assert parse_sku_list(42) == []


def test_exclude_skus_matches_like_the_xlsx_always_did():
    df = pd.DataFrame({"SKU": ["7", "7.0", "B", None]})
    kept = exclude_skus(df, "07")
    assert kept["SKU"].iloc[0] == "B"
    assert len(kept) == 2 and kept["SKU"].isna().tolist() == [False, True]


def test_exclude_skus_with_nothing_to_exclude_returns_the_frame_unchanged():
    df = pd.DataFrame({"SKU": ["A"]})
    assert exclude_skus(df, []).equals(df)
