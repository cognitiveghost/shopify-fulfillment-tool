import pandas as pd
import pytest

from shopify_tool import fulfillment_history as fh


def frame(statuses):
    """statuses: {order: status}; one SKU line per order."""
    return pd.DataFrame(
        {
            "Order_Number": list(statuses),
            "SKU": ["A"] * len(statuses),
            "Order_Fulfillment_Status": list(statuses.values()),
        }
    )


def rows(path):
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    return sorted(map(tuple, df[fh.COLUMNS].values.tolist()))


def test_missing_file_loads_empty(tmp_path):
    df = fh.load(tmp_path / "h.csv")
    assert df.empty and list(df.columns) == fh.COLUMNS


def test_legacy_file_without_session_loads(tmp_path):
    p = tmp_path / "h.csv"
    p.write_text("Order_Number,Execution_Date\n#1,2026-01-05\n#2,\n", encoding="utf-8")
    df = fh.load(p)
    assert df["Session"].tolist() == ["", ""]
    assert df["Execution_Date"].tolist() == ["2026-01-05", ""]


def test_load_reads_order_numbers_as_text(tmp_path):
    p = tmp_path / "h.csv"
    p.write_text("Order_Number,Execution_Date\n12345,2026-01-05\n", encoding="utf-8")
    assert fh.load(p)["Order_Number"].tolist() == ["12345"]


def test_unreadable_file_raises_and_is_never_written(tmp_path):
    p = tmp_path / "h.csv"
    p.write_text("Order_Number,Execution_Date\n#1,2026-01-05\n#2,2026-01-05,stray\n", encoding="utf-8")
    before = p.read_bytes()
    with pytest.raises(fh.HistoryUnreadable):
        fh.load(p)
    assert fh.record_session(p, "S1", frame({"#9": "Fulfillable"})) is False
    assert p.read_bytes() == before


def test_every_row_with_an_extra_field_is_unreadable_not_shifted(tmp_path):
    p = tmp_path / "h.csv"
    p.write_text("Order_Number,Execution_Date,Session\n#1,2026-01-01,s1,x\n", encoding="utf-8")
    before = p.read_bytes()
    with pytest.raises(fh.HistoryUnreadable):
        fh.load(p)
    assert fh.record_session(p, "S1", frame({"#9": "Fulfillable"})) is False
    assert p.read_bytes() == before


def test_empty_file_loads_empty_and_is_written(tmp_path):
    p = tmp_path / "h.csv"
    p.write_bytes(b"")
    assert fh.load(p).empty
    assert fh.record_session(p, "S1", frame({"#9": "Fulfillable"}), today="2026-01-01")
    assert rows(p) == [("#9", "2026-01-01", "S1")]


def test_record_replaces_only_this_sessions_rows(tmp_path):
    p = tmp_path / "h.csv"
    fh.record_session(p, "S0", frame({"#1": "Fulfillable"}), today="2026-01-01")
    fh.record_session(p, "S1", frame({"#1": "Fulfillable", "#2": "Fulfillable"}), today="2026-01-02")
    # A person holds #2 in S1.
    fh.record_session(p, "S1", frame({"#1": "Fulfillable", "#2": "Not Fulfillable"}), today="2026-01-03")
    assert rows(p) == [("#1", "2026-01-01", "S0"), ("#1", "2026-01-02", "S1")]


def test_record_keeps_the_sessions_first_date(tmp_path):
    p = tmp_path / "h.csv"
    fh.record_session(p, "S1", frame({"#1": "Fulfillable"}), today="2026-01-01")
    fh.record_session(p, "S1", frame({"#1": "Fulfillable"}), today="2026-01-05")
    assert rows(p) == [("#1", "2026-01-01", "S1")]


def test_legacy_record_merges_earliest_and_leaves_sessions(tmp_path):
    p = tmp_path / "h.csv"
    p.write_text("Order_Number,Execution_Date\n#1,2026-01-05\n", encoding="utf-8")
    fh.record_session(p, "S1", frame({"#1": "Fulfillable"}), today="2026-02-01")
    fh.record_session(p, None, frame({"#1": "Fulfillable", "#2": "Fulfillable"}), today="2026-02-02")
    assert rows(p) == [("#1", "2026-01-05", ""), ("#1", "2026-02-01", "S1"), ("#2", "2026-02-02", "")]


def test_record_leaves_no_temp_files(tmp_path):
    p = tmp_path / "h.csv"
    fh.record_session(p, "S1", frame({"#1": "Fulfillable"}))
    assert sorted(x.name for x in tmp_path.iterdir()) == ["h.csv", "h.csv.lock"]


def test_lock_timeout_returns_false_and_writes_nothing(tmp_path, monkeypatch):
    from shared.file_lock import FileLockError

    def refuse(*_a, **_k):
        raise FileLockError("held")

    monkeypatch.setattr(fh, "locked_file", refuse)
    p = tmp_path / "h.csv"
    assert fh.record_session(p, "S1", frame({"#1": "Fulfillable"})) is False
    assert not p.exists()


# --- The run drops rows of deleted session folders (AUDIT-07-L1) ---

SHIPS_4 = frame({"#4": "Fulfillable"})


def _write(path, rows_):
    pd.DataFrame(rows_, columns=fh.COLUMNS).to_csv(path, index=False)


def test_the_run_drops_rows_of_deleted_sessions(tmp_path):
    path = tmp_path / fh.FILE_NAME
    _write(path, [("#1", "2026-01-01", "gone"), ("#2", "2026-01-01", "kept"), ("#3", "2026-01-01", "")])
    assert fh.record_session(path, "now", SHIPS_4, existing_sessions={"kept", "now"})
    loaded = fh.load(path)
    assert set(zip(loaded["Order_Number"], loaded["Session"])) == {("#2", "kept"), ("#3", ""), ("#4", "now")}


def test_without_a_listing_nothing_is_pruned(tmp_path):
    path = tmp_path / fh.FILE_NAME
    _write(path, [("#1", "2026-01-01", "gone"), ("#2", "2026-01-01", "kept"), ("#3", "2026-01-01", "")])
    assert fh.record_session(path, "now", SHIPS_4, existing_sessions=None)
    assert "gone" in set(fh.load(path)["Session"])


def test_session_folders_refuses_a_listing_without_the_current_session(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "file.txt").write_text("x", encoding="utf-8")
    assert fh.session_folders(tmp_path, "a") == {"a"}
    assert fh.session_folders(tmp_path, "b") is None
    assert fh.session_folders(tmp_path / "missing", None) is None
