"""Session status derivation from packing progress and age (pure -- no Qt, no file server)."""
from datetime import datetime, timedelta

from shopify_tool.session_lifecycle import (
    DISPLAY_STATUSES,
    blocked_orders,
    derive_status_updates,
    display_status,
    is_fully_packed,
    packing_completion,
    parse_created_at,
)

NOW = datetime.now().astimezone()


def _entry(name="s", status="active", lists=None, progress=None, created=None, manual=None):
    entry = {
        "session_name": name,
        "status": status,
        "statistics": {"packing_lists": lists if lists is not None else []},
    }
    if progress is not None:
        entry["packing_progress"] = progress
    if created is not None:
        entry["created_at"] = created
    if manual is not None:
        entry["status_manually_set"] = manual
    return entry


def _done(*names):
    return {n: {"status": "completed"} for n in names}


class TestPackingCompletion:
    def test_counts_completed_lists(self):
        assert packing_completion(_entry(lists=["a", "b", "c"], progress=_done("a", "b"))) == (2, 3)

    def test_session_with_no_packing_lists_is_zero_of_zero(self):
        assert packing_completion(_entry(lists=[], progress={})) == (0, 0)

    def test_full_session_key_covers_every_list(self):
        # Packing Tool's whole-session mode records progress under the literal
        # key "full_session", which matches no list's file stem. Two of the 29
        # real sessions carrying packing_progress already use it; without this
        # they would read 0/N forever despite being entirely packed.
        assert packing_completion(_entry(lists=["a", "b"], progress=_done("full_session"))) == (2, 2)

    def test_full_session_with_no_lists_on_disk_reads_one_of_one(self):
        assert packing_completion(_entry(lists=[], progress=_done("full_session"))) == (1, 1)

    def test_incomplete_full_session_does_not_count(self):
        entry = _entry(lists=["a"], progress={"full_session": {"status": "in_progress"}})
        assert packing_completion(entry) == (0, 1)

    def test_progress_key_with_no_file_on_disk_cannot_block_completion(self):
        assert packing_completion(_entry(lists=["a"], progress=_done("a", "ghost"))) == (1, 1)

    def test_only_completed_counts_not_paused(self):
        assert packing_completion(_entry(lists=["a"], progress={"a": {"status": "paused"}})) == (0, 1)

    def test_malformed_shapes_do_not_raise(self):
        # Every value here comes from a file another tool writes.
        assert packing_completion({"packing_progress": "nonsense"}) == (0, 0)
        assert packing_completion({"statistics": "nonsense"}) == (0, 0)
        assert packing_completion(_entry(lists=["a"], progress={"a": ["not", "a", "dict"]})) == (0, 1)
        assert packing_completion(_entry(lists=["a"], progress={"a": {}})) == (0, 1)
        assert packing_completion({}) == (0, 0)


class TestIsFullyPacked:
    def test_all_lists_complete(self):
        assert is_fully_packed(_entry(lists=["a"], progress=_done("a"))) is True

    def test_empty_session_is_never_complete(self):
        # Vacuous truth would mark all 9 real list-less sessions complete.
        assert is_fully_packed(_entry(lists=[], progress={})) is False

    def test_partial_is_not_complete(self):
        assert is_fully_packed(_entry(lists=["a", "b"], progress=_done("a"))) is False


class TestParseCreatedAt:
    def test_naive_timestamp_becomes_local_aware(self):
        # created_at only became offset-aware on 2026-07-27 (PR #253), so every
        # session old enough to archive predates the fix. Skipping naive stamps
        # would archive nothing at all, forever.
        # Assert the *local* offset, not merely "aware": the tempting
        # .replace(tzinfo=timezone.utc) is the bug the docstring warns
        # against, and it satisfies a bare `tzinfo is not None`.
        naive = datetime(2026, 7, 20, 10, 0, 0)  # noqa: DTZ001 -- naive is the subject
        parsed = parse_created_at("2026-07-20T10:00:00")
        assert parsed.utcoffset() == naive.astimezone().utcoffset()
        assert parsed.replace(tzinfo=None) == naive

    def test_aware_timestamp_instant_is_preserved(self):
        aware = "2026-08-20T10:00:00+03:00"
        assert parse_created_at(aware) == datetime.fromisoformat(aware)

    def test_unreadable_values_return_none_and_never_raise(self):
        # A naive stamp once crashed the whole refresh and left the widget
        # stuck on "Loading..." forever. Nothing here may raise.
        assert parse_created_at("garbage") is None
        assert parse_created_at("") is None
        assert parse_created_at(None) is None
        assert parse_created_at(12345) is None


class TestDeriveStatusUpdates:
    def setup_method(self):
        self.old = (NOW - timedelta(days=45)).isoformat()
        self.recent = (NOW - timedelta(days=5)).isoformat()

    def test_fully_packed_active_session_is_completed(self):
        entries = [_entry(created=self.recent, lists=["a"], progress=_done("a"))]
        assert derive_status_updates(entries, NOW) == {"s": "completed"}

    def test_empty_session_is_not_completed(self):
        assert derive_status_updates([_entry(created=self.recent, lists=[], progress={})], NOW) == {}

    def test_abandoned_session_is_not_completed(self):
        entries = [_entry(status="abandoned", created=self.recent, lists=["a"], progress=_done("a"))]
        assert derive_status_updates(entries, NOW) == {}

    def test_old_active_session_is_archived(self):
        assert derive_status_updates([_entry(created=self.old)], NOW) == {"s": "archived"}

    def test_old_completed_session_is_archived(self):
        assert derive_status_updates([_entry(status="completed", created=self.old)], NOW) == {"s": "archived"}

    def test_abandoned_is_an_explicit_human_judgment_and_is_left_alone(self):
        assert derive_status_updates([_entry(status="abandoned", created=self.old)], NOW) == {}

    def test_already_archived_is_terminal(self):
        assert derive_status_updates([_entry(status="archived", created=self.old)], NOW) == {}

    def test_archive_beats_complete(self):
        entries = [_entry(created=self.old, lists=["a"], progress=_done("a"))]
        assert derive_status_updates(entries, NOW) == {"s": "archived"}

    def test_manual_edit_wins_permanently(self):
        # Without this the automation fights the user: they un-archive an old
        # session and the next refresh archives it straight back.
        assert derive_status_updates([_entry(created=self.old, manual=True)], NOW) == {}
        packed = _entry(created=self.recent, lists=["a"], progress=_done("a"), manual=True)
        assert derive_status_updates([packed], NOW) == {}

    def test_unreadable_date_is_never_archived(self):
        assert derive_status_updates([_entry(created="garbage")], NOW) == {}
        assert derive_status_updates([_entry()], NOW) == {}

    def test_legacy_naive_stamp_older_than_cutoff_does_archive(self):
        # The whole point: this is the entire existing backlog.
        assert derive_status_updates([_entry(created="2026-07-01T09:00:00")], NOW) == {"s": "archived"}

    def test_steady_state_writes_nothing(self):
        entries = [_entry(status="completed", created=self.recent, lists=["a"], progress=_done("a"))]
        assert derive_status_updates(entries, NOW) == {}

    def test_junk_entries_do_not_raise(self):
        assert derive_status_updates([None, "nope", {}, {"session_name": ""}], NOW) == {}
        assert derive_status_updates(None, NOW) == {}


class TestBlockedOrders:
    def test_reads_the_stored_key(self):
        assert blocked_orders({"not_fulfillable_orders": 4}) == 4

    def test_zero_is_zero_not_none(self):
        assert blocked_orders({"not_fulfillable_orders": 0}) == 0

    def test_falls_back_to_the_complement(self):
        entry = {"total_orders": 31, "fulfillable_orders": 27}
        assert blocked_orders(entry) == 4

    def test_stored_key_wins_over_the_complement(self):
        entry = {"not_fulfillable_orders": 4, "total_orders": 31,
                 "fulfillable_orders": 99}
        assert blocked_orders(entry) == 4

    def test_never_analysed_is_none_not_zero(self):
        assert blocked_orders({"session_name": "2026-09-01_1"}) is None

    def test_nonsense_reads_as_none(self):
        assert blocked_orders({"not_fulfillable_orders": "four"}) is None
        assert blocked_orders({"not_fulfillable_orders": -1}) is None
        assert blocked_orders({"total_orders": 3, "fulfillable_orders": 9}) is None

    def test_survives_a_non_dict(self):
        assert blocked_orders(None) is None
        assert blocked_orders([]) is None


def _lifecycle_entry(status="active", lists=(), progress=None, updated=None):
    entry = {
        "session_name": "2026-09-01_1",
        "status": status,
        "statistics": {"packing_lists": list(lists)},
        "packing_progress": dict(progress or {}),
    }
    if updated:
        entry["last_updated"] = updated.isoformat()
    return entry


class TestDisplayStatus:
    def test_the_vocabulary_is_eight_states(self):
        assert DISPLAY_STATUSES == (
            "not_started", "in_progress", "paused", "stale",
            "completed", "incomplete", "abandoned", "archived",
        )

    def test_active_with_no_progress_is_not_started(self):
        assert display_status(_lifecycle_entry(lists=["a", "b"]), NOW) == "not_started"

    def test_active_with_some_progress_is_in_progress(self):
        entry = _lifecycle_entry(lists=["a", "b"], progress={"a": {"status": "completed"}},
                       updated=NOW - timedelta(days=1))
        assert display_status(entry, NOW) == "in_progress"

    def test_a_paused_list_beats_progress(self):
        entry = _lifecycle_entry(lists=["a", "b"],
                       progress={"a": {"status": "completed"},
                                 "b": {"status": "paused"}},
                       updated=NOW - timedelta(days=1))
        assert display_status(entry, NOW) == "paused"

    def test_in_progress_untouched_a_week_is_stale(self):
        entry = _lifecycle_entry(lists=["a", "b"], progress={"a": {"status": "completed"}},
                       updated=NOW - timedelta(days=8))
        assert display_status(entry, NOW) == "stale"

    def test_not_started_never_goes_stale(self):
        # Nothing has been touched because nothing was started. Age is the
        # column that says so; Stale would be the same fact drawn twice.
        entry = _lifecycle_entry(lists=["a"], updated=NOW - timedelta(days=90))
        assert display_status(entry, NOW) == "not_started"

    def test_completed_and_fully_packed_is_completed(self):
        entry = _lifecycle_entry(status="completed", lists=["a"],
                       progress={"a": {"status": "completed"}})
        assert display_status(entry, NOW) == "completed"

    def test_completed_with_work_left_is_incomplete(self):
        entry = _lifecycle_entry(status="completed", lists=["a", "b"],
                       progress={"a": {"status": "completed"}})
        assert display_status(entry, NOW) == "incomplete"

    def test_completed_with_no_lists_at_all_is_completed(self):
        # packing_completion returns (0, 0) here. A session with nothing to
        # pack that a person called done is done, not unfinished.
        assert display_status(_lifecycle_entry(status="completed"), NOW) == "completed"

    def test_abandoned_and_archived_pass_through(self):
        assert display_status(_lifecycle_entry(status="abandoned"), NOW) == "abandoned"
        assert display_status(_lifecycle_entry(status="archived"), NOW) == "archived"

    def test_an_unknown_stored_status_renders_as_itself(self):
        assert display_status(_lifecycle_entry(status="frozen"), NOW) == "frozen"

    def test_an_unreadable_timestamp_is_not_stale(self):
        entry = _lifecycle_entry(lists=["a", "b"], progress={"a": {"status": "completed"}})
        entry["last_updated"] = "not a date"
        assert display_status(entry, NOW) == "in_progress"

    def test_survives_a_non_dict(self):
        assert display_status(None, NOW) == "active"
