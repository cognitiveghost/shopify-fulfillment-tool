"""Tests for merge_session_stock_exports (Feature 4: Multi-Session Combined Stock Export)."""

import pandas as pd
from shopify_tool.stock_export import merge_session_stock_exports


def _make_session(tmp_path, name, rows):
    """Helper: create a session dir with a stock_exports/export.csv file."""
    exports_dir = tmp_path / name / "stock_exports"
    exports_dir.mkdir(parents=True)
    pd.DataFrame(rows).to_csv(
        exports_dir / "export.csv", index=False, encoding="utf-8-sig"
    )
    return tmp_path / name


def test_merge_session_stock_exports_sums_correctly(tmp_path):
    s0 = _make_session(
        tmp_path,
        "session_0",
        [
            {"Артикул": "SKU-A", "Мярка": "бр", "Колич": 10},
            {"Артикул": "SKU-B", "Мярка": "бр", "Колич": 5},
        ],
    )
    s1 = _make_session(
        tmp_path,
        "session_1",
        [
            {"Артикул": "SKU-A", "Мярка": "бр", "Колич": 20},
            {"Артикул": "SKU-B", "Мярка": "бр", "Колич": 8},
        ],
    )

    result = merge_session_stock_exports([s0, s1])
    assert result.loc[result["Артикул"] == "SKU-A", "Колич"].iloc[0] == 30
    assert result.loc[result["Артикул"] == "SKU-B", "Колич"].iloc[0] == 13


def test_merge_handles_missing_session(tmp_path):
    result = merge_session_stock_exports([tmp_path / "nonexistent"])
    assert result.empty


def test_merge_handles_old_nalichnost_column(tmp_path):
    """Should accept the old 'Наличност' column name."""
    s0 = _make_session(tmp_path, "s0", [{"Артикул": "SKU-X", "Наличност": 7}])
    s1 = _make_session(tmp_path, "s1", [{"Артикул": "SKU-X", "Наличност": 3}])
    result = merge_session_stock_exports([s0, s1])
    assert result.loc[result["Артикул"] == "SKU-X", "Колич"].iloc[0] == 10


def test_merge_groups_by_lot_columns(tmp_path):
    """When Годност/Партида are present, sums within each lot group."""
    rows = [
        {"Артикул": "SKU-A", "Колич": 5, "Годност": "2025-01", "Партида": "B1"},
        {"Артикул": "SKU-A", "Колич": 3, "Годност": "2025-01", "Партида": "B1"},
    ]
    s0 = _make_session(tmp_path, "lot0", rows[:1])
    s1 = _make_session(tmp_path, "lot1", rows[1:])
    result = merge_session_stock_exports([s0, s1])
    row = result[(result["Артикул"] == "SKU-A") & (result["Партида"] == "B1")]
    assert row["Колич"].iloc[0] == 8


def test_merge_returns_sorted_by_artykul(tmp_path):
    s0 = _make_session(
        tmp_path,
        "s0",
        [
            {"Артикул": "ZZZ", "Колич": 1},
            {"Артикул": "AAA", "Колич": 2},
        ],
    )
    result = merge_session_stock_exports([s0])
    assert list(result["Артикул"]) == ["AAA", "ZZZ"]


def test_merge_skips_session_without_stock_exports_dir(tmp_path):
    """Session dir with no stock_exports/ subfolder is skipped gracefully."""
    (tmp_path / "empty_session").mkdir()
    s_good = _make_session(tmp_path, "good", [{"Артикул": "SKU-G", "Колич": 5}])
    result = merge_session_stock_exports([tmp_path / "empty_session", s_good])
    assert len(result) == 1
    assert result.iloc[0]["Артикул"] == "SKU-G"
