"""Tests for merge_session_stock_exports (Feature 4: Multi-Session Combined Stock Export)."""

import pandas as pd
from shopify_tool.stock_export import merge_session_stock_exports


def _make_session(tmp_path, name, rows):
    """Create a session dir with analysis/current_state.pkl."""
    analysis_dir = tmp_path / name / "analysis"
    analysis_dir.mkdir(parents=True)
    pd.DataFrame(rows).to_pickle(analysis_dir / "current_state.pkl")
    return tmp_path / name


def _row(sku, qty, status="Fulfillable"):
    return {"Order_Fulfillment_Status": status, "SKU": sku, "Quantity": qty}


def test_merge_session_stock_exports_sums_correctly(tmp_path):
    s0 = _make_session(tmp_path, "session_0", [_row("SKU-A", 10), _row("SKU-B", 5)])
    s1 = _make_session(tmp_path, "session_1", [_row("SKU-A", 20), _row("SKU-B", 8)])

    result = merge_session_stock_exports([s0, s1])
    assert result.loc[result["Артикул"] == "SKU-A", "Брой"].iloc[0] == 30
    assert result.loc[result["Артикул"] == "SKU-B", "Брой"].iloc[0] == 13


def test_merge_handles_missing_session(tmp_path):
    result = merge_session_stock_exports([tmp_path / "nonexistent"])
    assert result.empty


def test_merge_excludes_non_fulfillable(tmp_path):
    """Only Fulfillable orders are counted."""
    s0 = _make_session(tmp_path, "s0", [
        _row("SKU-A", 10),
        _row("SKU-B", 5, status="Not Fulfillable"),
    ])
    result = merge_session_stock_exports([s0])
    assert len(result) == 1
    assert result.iloc[0]["Артикул"] == "SKU-A"


def test_merge_groups_by_lot(tmp_path):
    """When Lot_Details present, sums within each lot group across sessions."""
    def lot_row(sku, expiry, batch, qty, order_num):
        return {
            "Order_Fulfillment_Status": "Fulfillable",
            "SKU": sku,
            "Quantity": qty,
            "Order_Number": order_num,
            "Lot_Details": [{"expiry": expiry, "batch": batch, "qty_allocated": qty}],
        }

    s0 = _make_session(tmp_path, "lot0", [lot_row("SKU-A", "2025-01", "B1", 5, "ORD-001")])
    s1 = _make_session(tmp_path, "lot1", [lot_row("SKU-A", "2025-01", "B1", 3, "ORD-002")])
    result = merge_session_stock_exports([s0, s1])
    row = result[(result["Артикул"] == "SKU-A") & (result["Партида"] == "B1")]
    assert row["Брой"].iloc[0] == 8


def test_merge_returns_sorted_by_artykul(tmp_path):
    s0 = _make_session(tmp_path, "s0", [_row("ZZZ", 1), _row("AAA", 2)])
    result = merge_session_stock_exports([s0])
    assert list(result["Артикул"]) == ["AAA", "ZZZ"]


def test_merge_falls_back_to_xlsx_when_pkl_missing(tmp_path):
    """If pkl is absent, reads current_state.xlsx instead."""
    analysis_dir = tmp_path / "xlsx_session" / "analysis"
    analysis_dir.mkdir(parents=True)
    pd.DataFrame([_row("SKU-X", 7)]).to_excel(
        analysis_dir / "current_state.xlsx", index=False
    )
    result = merge_session_stock_exports([tmp_path / "xlsx_session"])
    assert result.iloc[0]["Артикул"] == "SKU-X"
    assert result.iloc[0]["Брой"] == 7


def test_merge_skips_session_without_analysis_dir(tmp_path):
    """Session dir with no analysis/ subfolder is skipped gracefully."""
    (tmp_path / "empty_session").mkdir()
    s_good = _make_session(tmp_path, "good", [_row("SKU-G", 5)])
    result = merge_session_stock_exports([tmp_path / "empty_session", s_good])
    assert len(result) == 1
    assert result.iloc[0]["Артикул"] == "SKU-G"
