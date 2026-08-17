"""The filter evaluator every report path shares.

Before this module existed, packing_lists.py and stock_export.py each built a
pandas .query() string, which could not evaluate 3 of the 5 operators the
settings UI offered: "in" produced no file, "contains" raised SyntaxError, and
"not in" silently emitted the rows it was told to exclude. test_not_in_excludes
pins that last one -- it is the case that shipped wrong picking lists.
"""
import pandas as pd
import pytest

from shopify_tool.report_filters import apply_report_filters, normalize_operator


@pytest.fixture
def df():
    return pd.DataFrame({
        "Order_Number": ["#1001", "#1002", "#1003"],
        "SKU": ["AB-01", "CD-02", "EF-03"],
        "Quantity": [1, 2, 3],
        "Shipping_Provider": ["DHL", "DPD", "DHL"],
        # Both storage forms: a JSON string (what analysis.py writes) and a
        # native list (what the in-memory tag path can hold).
        "Internal_Tags": ['["Gift"]', '["NoGift"]', ["Gift", "Fragile"]],
    })


def _skus(df, filters):
    return sorted(apply_report_filters(df, filters)["SKU"].tolist())


@pytest.mark.parametrize("operator, value, expected", [
    # Legacy spellings, as stored by older builds of the settings UI.
    ("==", "DHL", ["AB-01", "EF-03"]),
    ("!=", "DHL", ["CD-02"]),
    # Rules-engine spellings.
    ("equals", "DHL", ["AB-01", "EF-03"]),
    ("does not equal", "DHL", ["CD-02"]),
])
def test_provider_operators(df, operator, value, expected):
    assert _skus(df, [{"field": "Shipping_Provider", "operator": operator, "value": value}]) == expected


@pytest.mark.parametrize("operator, value, expected", [
    ("in", "AB-01,CD-02", ["AB-01", "CD-02"]),
    ("in list", "AB-01,CD-02", ["AB-01", "CD-02"]),
    ("contains", "AB", ["AB-01"]),
    ("starts with", "AB", ["AB-01"]),
    ("ends with", "03", ["EF-03"]),
])
def test_sku_operators(df, operator, value, expected):
    assert _skus(df, [{"field": "SKU", "operator": operator, "value": value}]) == expected


@pytest.mark.parametrize("operator", ["not in", "not in list"])
def test_not_in_excludes_the_listed_skus(df, operator):
    """The regression that motivated this module.

    The old query-string builder wrote all three rows here, including both
    SKUs the filter named. A warehouse worker got a picking list containing
    items the configuration excluded, under a "Report saved" message.
    """
    assert _skus(df, [{"field": "SKU", "operator": operator, "value": "AB-01,CD-02"}]) == ["EF-03"]


def test_numeric_comparison(df):
    assert _skus(df, [{"field": "Quantity", "operator": "is greater than", "value": "1"}]) == ["CD-02", "EF-03"]


@pytest.mark.parametrize("operator, expected", [
    ("contains", ["AB-01", "EF-03"]),
    ("does not contain", ["CD-02"]),
])
def test_internal_tags_use_membership_not_substring(df, operator, expected):
    """"Gift" must match ["Gift"] but not ["NoGift"].

    A substring match against the raw JSON would match both, which is why this
    column gets tag_manager.has_tag semantics instead.
    """
    assert _skus(df, [{"field": "Internal_Tags", "operator": operator, "value": "Gift"}]) == expected


def test_filters_combine_with_and(df):
    filters = [
        {"field": "Shipping_Provider", "operator": "equals", "value": "DHL"},
        {"field": "SKU", "operator": "contains", "value": "AB"},
    ]
    assert _skus(df, filters) == ["AB-01"]


@pytest.mark.parametrize("filters", [
    [{"field": "SKU", "operator": "bogus", "value": "x"}],
    [{"field": "NoSuchColumn", "operator": "equals", "value": "x"}],
    [{"field": "", "operator": "equals", "value": "x"}],
])
def test_unresolvable_filter_matches_nothing(df, filters):
    """Skipping a filter widens the result set -- the exact failure this
    module exists to remove. An unusable filter matches nothing instead.
    """
    assert _skus(df, filters) == []


def test_no_filters_returns_everything(df):
    assert _skus(df, []) == ["AB-01", "CD-02", "EF-03"]


def test_empty_frame_is_returned_unchanged(df):
    empty = df.iloc[0:0]
    assert apply_report_filters(empty, [{"field": "SKU", "operator": "equals", "value": "AB-01"}]).empty


def test_normalize_operator_maps_legacy_names():
    assert normalize_operator("==") == "equals"
    assert normalize_operator("not in") == "not in list"
    assert normalize_operator("starts with") == "starts with"
