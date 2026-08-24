"""Session status derivation from packing progress and age (pure -- no Qt, no file server)."""
from datetime import datetime, timedelta

from shopify_tool.session_lifecycle import (
    derive_status_updates,
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
        assert parse_created_at("2026-07-20T10:00:00").tzinfo is not None

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
