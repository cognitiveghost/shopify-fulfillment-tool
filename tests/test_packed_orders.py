import json
import os

import pandas as pd

from shopify_tool.packed_orders import load_packed_orders, union_history_with_packed


class _FakeProfileManager:
    """Minimal stand-in exposing only what load_packed_orders uses."""

    def __init__(self, sessions_root):
        self._sessions_root = sessions_root

    def get_sessions_root(self):
        return self._sessions_root


def _write_sessions(tmp_path, client_id, entries):
    """Write each entry as a real session directory's session_info.json.

    Deliberately writes no session_index.json. These fixtures used to
    hand-write the index, which assumed the very link that was broken:
    Packing Tool writes session_info.json and nothing else, so a test that
    seeds the index proves nothing about whether its writes are visible.
    """
    client_dir = tmp_path / f"CLIENT_{client_id}"
    client_dir.mkdir(parents=True, exist_ok=True)
    for entry in entries:
        session_dir = client_dir / entry["session_name"]
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / "session_info.json").write_text(
            json.dumps(entry), encoding="utf-8"
        )
    return _FakeProfileManager(tmp_path)


class TestLoadPackedOrders:
    def test_reads_completed_orders_with_packing_date(self, tmp_path):
        pm = _write_sessions(tmp_path, "ALMADERM", [
            {
                "session_name": "2026-07-26_2",
                "packing_progress": {
                    "ALL_ORDERS": {
                        "started_at": "2026-07-26T18:25:33+00:00",
                        "updated_at": "2026-07-28T09:10:00+00:00",
                        "status": "completed",
                        "completed_orders": ["#11019512", "#11019513"],
                    }
                },
            }
        ])

        df = load_packed_orders(pm, "ALMADERM")

        assert list(df.columns) == ["Order_Number", "Execution_Date"]
        assert dict(zip(df["Order_Number"], df["Execution_Date"])) == {
            "#11019512": "2026-07-28",
            "#11019513": "2026-07-28",
        }

    def test_falls_back_to_started_at_when_no_updated_at(self, tmp_path):
        pm = _write_sessions(tmp_path, "ALMADERM", [
            {
                "session_name": "2026-07-26_2",
                "packing_progress": {
                    "ALL_ORDERS": {
                        "started_at": "2026-07-26T18:25:33+00:00",
                        "status": "completed",
                        "completed_orders": ["#A"],
                    }
                },
            }
        ])

        df = load_packed_orders(pm, "ALMADERM")
        assert df.iloc[0]["Execution_Date"] == "2026-07-26"

    def test_falls_back_to_started_at_when_updated_at_is_unparseable(self, tmp_path):
        """`updated_at or started_at` on the raw values picks the garbage and
        drops the whole block; the fallback has to be per-parse."""
        pm = _write_sessions(tmp_path, "ALMADERM", [
            {
                "session_name": "2026-07-26_2",
                "packing_progress": {
                    "ALL_ORDERS": {
                        "started_at": "2026-07-26T18:25:33+00:00",
                        "updated_at": "not-a-date",
                        "completed_orders": ["#A"],
                    }
                },
            }
        ])

        df = load_packed_orders(pm, "ALMADERM")
        assert df.iloc[0]["Execution_Date"] == "2026-07-26"

    def test_collects_across_sessions_and_packing_lists(self, tmp_path):
        pm = _write_sessions(tmp_path, "ALMADERM", [
            {
                "session_name": "2026-07-01_1",
                "packing_progress": {
                    "LIST_A": {"updated_at": "2026-07-01T10:00:00+00:00",
                               "completed_orders": ["#A"]},
                    "LIST_B": {"updated_at": "2026-07-01T11:00:00+00:00",
                               "completed_orders": ["#B"]},
                },
            },
            {
                "session_name": "2026-07-02_1",
                "packing_progress": {
                    "LIST_C": {"updated_at": "2026-07-02T10:00:00+00:00",
                               "completed_orders": ["#C"]},
                },
            },
        ])

        df = load_packed_orders(pm, "ALMADERM")
        assert set(df["Order_Number"]) == {"#A", "#B", "#C"}

    def test_same_order_packed_twice_keeps_earliest(self, tmp_path):
        pm = _write_sessions(tmp_path, "ALMADERM", [
            {"session_name": "2026-07-05_1", "packing_progress": {
                "L": {"updated_at": "2026-07-05T10:00:00+00:00",
                      "completed_orders": ["#A"]}}},
            {"session_name": "2026-07-01_1", "packing_progress": {
                "L": {"updated_at": "2026-07-01T10:00:00+00:00",
                      "completed_orders": ["#A"]}}},
        ])

        df = load_packed_orders(pm, "ALMADERM")
        assert len(df) == 1
        assert df.iloc[0]["Execution_Date"] == "2026-07-01"

    # --- degradation: each of these must return empty, not raise ---

    def test_entry_without_completed_orders_key_is_skipped(self, tmp_path):
        """The normal case before Task 4 ships -- not an error."""
        pm = _write_sessions(tmp_path, "ALMADERM", [
            {
                "session_name": "2026-07-26_2",
                "packing_progress": {
                    "ALL_ORDERS": {
                        "started_at": "2026-07-26T18:25:33+00:00",
                        "status": "in_progress",
                    }
                },
            }
        ])

        df = load_packed_orders(pm, "ALMADERM")
        assert df.empty
        assert list(df.columns) == ["Order_Number", "Execution_Date"]

    def test_entry_without_packing_progress_is_skipped(self, tmp_path):
        pm = _write_sessions(tmp_path, "ALMADERM", [
            {"session_name": "2026-07-26_1", "status": "active"}
        ])
        assert load_packed_orders(pm, "ALMADERM").empty

    def test_missing_client_directory_returns_empty(self, tmp_path):
        assert load_packed_orders(_FakeProfileManager(tmp_path), "NOSUCH").empty

    def test_malformed_index_is_rebuilt_from_the_session_directories(self, tmp_path):
        pm = _write_sessions(tmp_path, "ALMADERM", [
            {"session_name": "s", "packing_progress": {
                "L": {"updated_at": "2026-07-01T10:00:00+00:00",
                      "completed_orders": ["#A"]}}},
        ])
        (tmp_path / "CLIENT_ALMADERM" / "session_index.json").write_text(
            "{not json", encoding="utf-8"
        )

        assert set(load_packed_orders(pm, "ALMADERM")["Order_Number"]) == {"#A"}

    def test_unparseable_timestamp_is_skipped_without_raising(self, tmp_path):
        pm = _write_sessions(tmp_path, "ALMADERM", [
            {"session_name": "s", "packing_progress": {
                "L": {"updated_at": "not-a-date", "completed_orders": ["#A"]}}},
        ])
        assert load_packed_orders(pm, "ALMADERM").empty

    def test_client_id_is_case_insensitive(self, tmp_path):
        pm = _write_sessions(tmp_path, "ALMADERM", [
            {"session_name": "s", "packing_progress": {
                "L": {"updated_at": "2026-07-01T10:00:00+00:00",
                      "completed_orders": ["#A"]}}},
        ])
        assert not load_packed_orders(pm, "almaderm").empty


class TestStaleIndexIsRefreshed:
    """The transport this feature rides on.

    Packing Tool only writes session_info.json. It never touches this
    repo's session_index.json and never changes the session count, so a
    count-only staleness check leaves the packed orders invisible forever
    -- silently, which is how this shipped as a draft.
    """

    def test_packed_orders_written_after_the_index_are_still_seen(self, tmp_path):
        pm = _write_sessions(tmp_path, "ALMADERM", [
            {"session_name": "2026-07-01_1", "packing_progress": {
                "L": {"updated_at": "2026-07-01T10:00:00+00:00",
                      "completed_orders": ["#A"]}}},
        ])
        client_dir = tmp_path / "CLIENT_ALMADERM"
        # The index as it looked before Packing Tool packed anything: same
        # session, same count, no packing_progress.
        index_path = client_dir / "session_index.json"
        index_path.write_text(
            json.dumps([{"session_name": "2026-07-01_1", "status": "active"}]),
            encoding="utf-8",
        )
        session_mtime = (client_dir / "2026-07-01_1").stat().st_mtime
        os.utime(index_path, (session_mtime - 10, session_mtime - 10))

        assert set(load_packed_orders(pm, "ALMADERM")["Order_Number"]) == {"#A"}


class TestUnionHistoryWithPacked:
    def test_order_in_both_sources_keeps_earlier_date(self):
        history = pd.DataFrame({"Order_Number": ["#A"], "Execution_Date": ["2026-07-10"]})
        packed = pd.DataFrame({"Order_Number": ["#A"], "Execution_Date": ["2026-07-01"]})

        out = union_history_with_packed(history, packed)
        assert len(out) == 1
        assert out.iloc[0]["Execution_Date"] == "2026-07-01"

    def test_order_in_both_sources_keeps_earlier_date_when_history_is_earlier(self):
        history = pd.DataFrame({"Order_Number": ["#A"], "Execution_Date": ["2026-07-01"]})
        packed = pd.DataFrame({"Order_Number": ["#A"], "Execution_Date": ["2026-07-10"]})

        out = union_history_with_packed(history, packed)
        assert len(out) == 1
        assert out.iloc[0]["Execution_Date"] == "2026-07-01"

    def test_packed_only_order_is_included(self):
        history = pd.DataFrame(columns=["Order_Number", "Execution_Date"])
        packed = pd.DataFrame({"Order_Number": ["#A"], "Execution_Date": ["2026-07-01"]})

        out = union_history_with_packed(history, packed)
        assert set(out["Order_Number"]) == {"#A"}

    def test_history_only_order_survives_empty_packed(self):
        """The no-cliff guarantee: the analysis signal keeps working when
        Packing Tool has contributed nothing yet."""
        history = pd.DataFrame({"Order_Number": ["#A"], "Execution_Date": ["2026-07-01"]})
        packed = pd.DataFrame(columns=["Order_Number", "Execution_Date"])

        out = union_history_with_packed(history, packed)
        assert dict(zip(out["Order_Number"], out["Execution_Date"])) == {"#A": "2026-07-01"}

    def test_both_empty_returns_empty_with_expected_columns(self):
        empty = pd.DataFrame(columns=["Order_Number", "Execution_Date"])
        out = union_history_with_packed(empty, empty)
        assert out.empty
        assert list(out.columns) == ["Order_Number", "Execution_Date"]


class TestMalformedCrossToolDataNeverAborts:
    """The contract is 'never raises'. These shapes all come from a file the
    OTHER tool writes, and each one used to escape to run_full_analysis's
    outer handler and fail the whole analysis."""

    def _load(self, tmp_path, block):
        pm = _write_sessions(tmp_path, "ALMADERM", [
            {"session_name": "s", "packing_progress": {"ALL": block}}
        ])
        return load_packed_orders(pm, "ALMADERM")

    def test_completed_orders_not_a_list(self, tmp_path):
        out = self._load(tmp_path, {"updated_at": "2026-07-01T10:00:00+03:00",
                                    "completed_orders": 5})
        assert out.empty

    def test_completed_orders_is_a_bare_string(self, tmp_path):
        """A string is iterable: this used to yield one row per character."""
        out = self._load(tmp_path, {"updated_at": "2026-07-01T10:00:00+03:00",
                                    "completed_orders": "#A"})
        assert out.empty

    def test_timestamp_is_a_list(self, tmp_path):
        out = self._load(tmp_path, {"updated_at": ["2026-07-01", "2026-07-02"],
                                    "completed_orders": ["#A"]})
        assert out.empty

    def test_timestamp_is_a_dict(self, tmp_path):
        out = self._load(tmp_path, {"updated_at": {"a": 1},
                                    "completed_orders": ["#A"]})
        assert out.empty

    def test_non_string_order_numbers_are_dropped(self, tmp_path):
        out = self._load(tmp_path, {"updated_at": "2026-07-01T10:00:00+03:00",
                                    "completed_orders": ["#A", None, 7, "#B"]})
        assert set(out["Order_Number"]) == {"#A", "#B"}


class TestUnionToleratesLegacyHistory:
    def test_history_without_execution_date_is_returned_untouched(self):
        """analysis._detect_repeated_orders has its own branch for this shape.
        Unioning here raised KeyError and aborted the analysis instead."""
        history = pd.DataFrame({"Order_Number": ["#A"]})
        packed = pd.DataFrame({"Order_Number": ["#B"], "Execution_Date": ["2026-07-01"]})

        out = union_history_with_packed(history, packed)
        assert list(out.columns) == ["Order_Number"]
        assert set(out["Order_Number"]) == {"#A"}

    def test_legacy_date_format_does_not_win_earliest_by_string_sort(self):
        """'27/11/2025' sorts after '2026-07-01' lexicographically but is
        the earlier date."""
        history = pd.DataFrame({"Order_Number": ["#A"], "Execution_Date": ["27/11/2025"]})
        packed = pd.DataFrame({"Order_Number": ["#A"], "Execution_Date": ["2026-07-01"]})

        out = union_history_with_packed(history, packed)
        assert out.iloc[0]["Execution_Date"] == "27/11/2025"


class TestPackedDateUsesWarehouseLocalDate:
    def test_after_midnight_local_is_not_shifted_to_yesterday(self, tmp_path):
        """utc=True turned 01:00 local (+03:00) into the previous day, which
        flags an order packed this morning as a same-day Repeat."""
        pm = _write_sessions(tmp_path, "ALMADERM", [
            {"session_name": "s", "packing_progress": {"ALL": {
                "updated_at": "2026-07-02T01:00:00+03:00",
                "completed_orders": ["#A"],
            }}}
        ])
        out = load_packed_orders(pm, "ALMADERM")
        assert out.iloc[0]["Execution_Date"] == "2026-07-02"
