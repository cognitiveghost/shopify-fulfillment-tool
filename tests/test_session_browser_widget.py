"""The Browse screen's widget: loading, the writes and Undo (phase 4 spec section 6).

The page itself is tested in test_browse_page.py; these drive the widget
through its bridge and read back the state it pushes.
"""

import json
import shutil
from pathlib import Path
from unittest.mock import Mock, call

import pytest
from PySide6.QtWebEngineWidgets import QWebEngineView

import gui.session_browser_widget as browser_module
from gui.session_browser_widget import SessionBrowserWidget
from shopify_tool.session_manager import SessionManager

NAMES = ["2026-09-30_2", "2026-09-30_1", "2026-09-29_1"]


def _path(name):
    return f"/srv/Sessions/CLIENT_ACME/{name}"


def _entry(name, **fields):
    return {
        "session_name": name,
        "session_path": _path(name),
        "status": "active",
        "created_at": "2026-09-30T08:00:00+00:00",
        "comments": "",
        **fields,
    }


@pytest.fixture
def told(monkeypatch):
    """What the error banner was asked to say: (headline, what to do)."""
    seen = []
    monkeypatch.setattr(browser_module, "show_error", lambda _source, *text: seen.append(text))
    return seen


@pytest.fixture
def browser(qtbot, monkeypatch, told):
    """A shown widget over a mocked SessionManager holding three sessions."""
    monkeypatch.setattr(SessionBrowserWidget, "USE_ASYNC", False)
    manager = Mock()
    manager.list_client_sessions.return_value = [_entry(name) for name in NAMES]
    # The file holds what the list shows, until a test says another PC wrote.
    manager.get_session_info.side_effect = lambda path: next(
        (e for e in manager.list_client_sessions.return_value if e["session_path"] == path),
        None,
    )
    widget = SessionBrowserWidget(manager)
    qtbot.addWidget(widget)
    widget.show()
    widget.set_client("ACME")
    return widget


def _toasts(widget):
    seen = []
    widget.bridge.toastRaised.connect(lambda text, undoable: seen.append((text, undoable)))
    return seen


def _views(widget):
    seen = []
    widget.bridge.stateChanged.connect(lambda: seen.append(widget.bridge.state["view"]))
    return seen


def _rows(widget):
    return [row["name"] for row in widget.bridge.state["rows"]]


# --- loading -----------------------------------------------------------------


def test_it_hosts_one_web_view_edge_to_edge(browser):
    assert isinstance(browser.view, QWebEngineView)
    margins = browser.layout().contentsMargins()
    assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (0, 0, 0, 0)
    assert browser.layout().count() == 1


def test_before_a_client_is_chosen_the_page_asks_for_one(qtbot):
    widget = SessionBrowserWidget(Mock())
    qtbot.addWidget(widget)
    assert widget.bridge.state == {"view": "no_client", "client": "", "rows": []}


def test_choosing_a_client_loads_every_status(browser):
    assert browser.bridge.state["view"] == "list"
    assert browser.bridge.state["client"] == "ACME"
    assert _rows(browser) == NAMES
    browser.session_manager.list_client_sessions.assert_called_once_with("ACME")


def test_a_loud_refresh_shows_the_skeleton_first(browser):
    views = _views(browser)
    browser.refresh_sessions()
    assert views == ["loading", "list"]


def test_a_quiet_refresh_keeps_the_rows_on_screen(browser):
    browser.session_manager.list_client_sessions.return_value = [_entry(NAMES[0])]
    views = _views(browser)
    browser.refresh_sessions(quiet=True)
    assert views == ["list"]
    assert _rows(browser) == NAMES[:1]


def test_a_failed_load_shows_the_failed_panel_and_no_banner(browser, told):
    browser.session_manager.list_client_sessions.side_effect = OSError("share went away")
    browser.refresh_sessions()
    assert browser.bridge.state == {"view": "failed", "client": "ACME", "rows": []}
    assert told == []

    browser.session_manager.list_client_sessions.side_effect = None
    browser.bridge.refresh()  # the panel's Try again
    assert browser.bridge.state["view"] == "list"


def test_a_worker_error_shows_the_failed_panel(browser):
    browser._on_load_error("timed out")
    assert browser.bridge.state["view"] == "failed"
    assert browser.sessions_data == []


def test_another_client_never_shows_the_previous_clients_rows(browser):
    browser.hide()
    browser.set_client("BETA", auto_refresh=False)
    assert browser.bridge.state == {"view": "loading", "client": "BETA", "rows": []}
    assert browser._is_dirty is True


def test_no_client_empties_the_page(browser):
    browser.set_client("")
    assert browser.bridge.state == {"view": "no_client", "client": "", "rows": []}


def test_a_load_that_arrives_while_shown_is_drawn(browser):
    browser._on_sessions_loaded([_entry("2026-10-01_1")])
    assert _rows(browser) == ["2026-10-01_1"]


def test_a_new_load_cleans_up_the_one_in_flight(browser, monkeypatch):
    started = []

    class FakeWorker:
        def __init__(self, _manager, client_id):
            self.client_id = client_id
            self.finished_with_data = Mock()
            self.error_occurred = Mock()
            self.cleanup = Mock()

        def start(self):
            started.append(self.client_id)

    monkeypatch.setattr(SessionBrowserWidget, "USE_ASYNC", True)
    monkeypatch.setattr(browser_module, "SessionLoaderWorker", FakeWorker)

    browser.refresh_sessions()
    first = browser.worker
    browser.refresh_sessions()

    first.cleanup.assert_called_once()
    assert browser.worker is not first
    assert started == ["ACME", "ACME"]
    browser.worker = None  # nothing real for closeEvent to clean up


# --- what the page asks for --------------------------------------------------


def test_a_status_reaches_every_named_session_as_set_by_hand(browser):
    toasts = _toasts(browser)
    loads = browser.session_manager.list_client_sessions.call_count

    browser.bridge.setStatus([NAMES[1], NAMES[2], "ghost"], "archived")

    assert browser.session_manager.update_session_status.call_args_list == [
        call(_path(NAMES[1]), "archived", manual=True),
        call(_path(NAMES[2]), "archived", manual=True),
    ]
    assert toasts == [("Set 2 sessions to Archived", True)]
    assert browser.session_manager.list_client_sessions.call_count == loads + 1


def test_one_session_is_named_in_the_toast(browser):
    toasts = _toasts(browser)
    browser.bridge.setStatus([NAMES[1]], "completed")
    assert toasts == [("Set 2026-09-30_1 to Completed", True)]


def test_names_this_widget_did_not_load_are_ignored(browser, told):
    toasts = _toasts(browser)
    loads = browser.session_manager.list_client_sessions.call_count
    browser.bridge.setStatus(["ghost", "../../etc"], "archived")
    browser.bridge.setComment(["ghost"], "x")
    browser.session_manager.update_session_status.assert_not_called()
    browser.session_manager.update_session_info.assert_not_called()
    assert toasts == [] and told == []
    assert browser.session_manager.list_client_sessions.call_count == loads


def test_a_comment_is_saved_on_every_named_session(browser):
    toasts = _toasts(browser)
    browser.bridge.setComment([NAMES[0], NAMES[1]], "late van")
    assert browser.session_manager.update_session_info.call_args_list == [
        call(_path(NAMES[0]), {"comments": "late van"}),
        call(_path(NAMES[1]), {"comments": "late van"}),
    ]
    assert toasts == [("Comment saved on 2 sessions", True)]


def test_an_empty_comment_clears(browser):
    toasts = _toasts(browser)
    browser.bridge.setComment([NAMES[0]], "")
    browser.session_manager.update_session_info.assert_called_once_with(
        _path(NAMES[0]), {"comments": ""}
    )
    assert toasts == [("Comment cleared on 2026-09-30_2", True)]


def test_one_failure_in_three_is_reported_and_the_rest_are_done(browser, told):
    def fail_one(path, status, manual=False):
        if path == _path(NAMES[1]):
            raise OSError("share went away")

    browser.session_manager.update_session_status.side_effect = fail_one
    toasts = _toasts(browser)

    browser.bridge.setStatus(NAMES, "archived")

    assert told == [("1 of 3 sessions weren't updated", "Details are in Logs.")]
    assert toasts == [("Set 2 sessions to Archived", True)]
    assert list(browser._undo) == [_path(NAMES[0]), _path(NAMES[2])]


def test_a_single_failed_status_says_what_failed_and_raises_no_toast(browser, told):
    browser.session_manager.update_session_status.side_effect = OSError("share went away")
    toasts = _toasts(browser)
    browser.bridge.setStatus([NAMES[0]], "archived")
    assert told == [("The status wasn't updated", "Details are in Logs.")]
    assert toasts == []
    assert browser._undo == {}


def test_a_single_failed_comment_says_what_failed(browser, told):
    browser.session_manager.update_session_info.side_effect = OSError("share went away")
    browser.bridge.setComment([NAMES[0]], "x")
    assert told == [("The comment wasn't saved", "Details are in Logs.")]


def test_open_emits_the_sessions_path(browser):
    opened = []
    browser.session_selected.connect(opened.append)
    browser.bridge.openSession(NAMES[1])
    browser.bridge.openSession("ghost")
    assert opened == [_path(NAMES[1])]


def test_export_emits_the_paths_in_list_order_and_needs_two(browser):
    exported = []
    browser.multi_export_requested.connect(exported.append)
    browser.bridge.exportCombined([NAMES[2], NAMES[0]])
    browser.bridge.exportCombined([NAMES[0], "ghost"])
    assert exported == [[_path(NAMES[0]), _path(NAMES[2])]]


def test_the_empty_panels_button_asks_for_a_new_session(browser, qtbot):
    with qtbot.waitSignal(browser.new_session_requested, timeout=1000):
        browser.bridge.newSession()


# --- Undo --------------------------------------------------------------------


def test_undoing_a_status_hands_back_the_status_fields_only(browser):
    browser.session_manager.list_client_sessions.return_value = [
        _entry(NAMES[0], comments="first", last_updated="2026-09-30T09:00:00+00:00"),
        _entry(
            NAMES[1],
            status="completed",
            status_manually_set=True,
            status_updated_at="2026-09-29T17:00:00+00:00",
        ),
    ]
    browser.refresh_sessions()

    browser.bridge.setStatus(NAMES[:2], "archived")
    browser.bridge.undo()

    assert browser.session_manager.restore_session_fields.call_args_list == [
        call(
            _path(NAMES[0]),
            {"status": "active", "status_manually_set": None, "status_updated_at": None},
        ),
        call(
            _path(NAMES[1]),
            {
                "status": "completed",
                "status_manually_set": True,
                "status_updated_at": "2026-09-29T17:00:00+00:00",
            },
        ),
    ]


def test_undoing_a_comment_hands_back_the_comment_and_its_timestamp_only(browser):
    browser.session_manager.list_client_sessions.return_value = [
        _entry(NAMES[0], comments="first", last_updated="2026-09-30T09:00:00+00:00"),
        _entry(NAMES[1]),
    ]
    browser.refresh_sessions()

    browser.bridge.setComment(NAMES[:2], "late van")
    browser.bridge.undo()

    assert browser.session_manager.restore_session_fields.call_args_list == [
        call(_path(NAMES[0]), {"comments": "first", "last_updated": "2026-09-30T09:00:00+00:00"}),
        call(_path(NAMES[1]), {"comments": "", "last_updated": None}),
    ]


def test_undo_remembers_the_file_not_the_list_on_screen(browser):
    # Another PC completed the session after this one loaded its list.
    on_disk = _entry(NAMES[0], status="completed", status_manually_set=True)
    browser.session_manager.get_session_info.side_effect = lambda _path: on_disk

    browser.bridge.setStatus([NAMES[0]], "archived")
    browser.bridge.undo()

    browser.session_manager.restore_session_fields.assert_called_once_with(
        _path(NAMES[0]),
        {"status": "completed", "status_manually_set": True, "status_updated_at": None},
    )


def test_a_name_two_entries_share_is_one_session(browser):
    # A hand-copied folder repeats its session_name, and so its path.
    browser.session_manager.list_client_sessions.return_value = [_entry(NAMES[0]), _entry(NAMES[0])]
    browser.refresh_sessions()
    opened = []
    browser.session_selected.connect(opened.append)

    browser.bridge.openSession(NAMES[0])
    browser.bridge.setStatus([NAMES[0]], "archived")

    assert opened == [_path(NAMES[0])]
    browser.session_manager.update_session_status.assert_called_once()


def test_undo_is_spent_once_and_does_nothing_with_nothing_to_undo(browser):
    browser.bridge.undo()
    browser.session_manager.restore_session_fields.assert_not_called()

    browser.bridge.setStatus([NAMES[0]], "archived")
    browser.bridge.undo()
    browser.bridge.undo()
    assert browser.session_manager.restore_session_fields.call_count == 1


def test_the_next_change_replaces_what_undo_remembers(browser):
    browser.bridge.setStatus([NAMES[0]], "archived")
    browser.bridge.setComment([NAMES[1]], "late van")
    browser.bridge.undo()
    assert [c.args[0] for c in browser.session_manager.restore_session_fields.call_args_list] == [
        _path(NAMES[1])
    ]


def test_another_client_forgets_the_undo(browser):
    browser.bridge.setStatus([NAMES[0]], "archived")
    browser.set_client("BETA")
    browser.bridge.undo()
    browser.session_manager.restore_session_fields.assert_not_called()


def test_an_undo_that_fails_is_reported(browser, told):
    browser.bridge.setStatus(NAMES[:2], "archived")
    browser.session_manager.restore_session_fields.side_effect = [None, OSError("share went away")]
    browser.bridge.undo()
    assert told == [("1 of 2 sessions weren't restored", "Details are in Logs.")]

    browser.bridge.setStatus([NAMES[0]], "archived")
    browser.session_manager.restore_session_fields.side_effect = OSError("share went away")
    browser.bridge.undo()
    assert told[-1] == ("The change wasn't undone", "Details are in Logs.")


# --- Undo against the real files ---------------------------------------------


@pytest.fixture
def real(qtbot, monkeypatch, profile_manager, told):
    """A shown widget over a real SessionManager with two sessions on disk."""
    monkeypatch.setattr(SessionBrowserWidget, "USE_ASYNC", False)
    profile_manager.create_client_profile("M", "Test Client")
    manager = SessionManager(profile_manager)
    paths = [manager.create_session("M") for _ in range(2)]
    manager.update_session_info(paths[0], {"comments": "first"})
    widget = SessionBrowserWidget(manager)
    qtbot.addWidget(widget)
    widget.show()
    widget.set_client("M")
    return widget, paths


def _stored(path):
    return json.loads((Path(path) / "session_info.json").read_text())


def test_undo_puts_an_archive_back_exactly(real):
    widget, paths = real
    names = [Path(p).name for p in paths]
    before = [_stored(p) for p in paths]

    widget.bridge.setStatus(names, "archived")
    assert [_stored(p)["status"] for p in paths] == ["archived", "archived"]
    assert [_stored(p)["status_manually_set"] for p in paths] == [True, True]
    assert {row["tab"] for row in widget.bridge.state["rows"]} == {"archived"}

    widget.bridge.undo()

    assert [_stored(p) for p in paths] == before
    assert {row["tab"] for row in widget.bridge.state["rows"]} == {"active"}


def test_undo_puts_a_comment_back_with_its_timestamp(real):
    widget, paths = real
    name = Path(paths[0]).name
    before = _stored(paths[0])

    widget.bridge.setComment([name], "call courier")
    assert _stored(paths[0])["comments"] == "call courier"

    widget.bridge.undo()

    assert _stored(paths[0]) == before
    row = next(r for r in widget.bridge.state["rows"] if r["name"] == name)
    assert row["comment"] == "first"


def test_undo_leaves_what_someone_else_wrote_in_between(real):
    widget, paths = real
    name = Path(paths[0]).name
    widget.bridge.setStatus([name], "archived")

    # Packing Tool records progress while the toast is still up.
    info = _stored(paths[0])
    info["packing_progress"] = {"list0": {"status": "completed"}}
    (Path(paths[0]) / "session_info.json").write_text(json.dumps(info))

    widget.bridge.undo()

    after = _stored(paths[0])
    assert after["status"] == "active"
    assert "status_manually_set" not in after
    assert after["packing_progress"] == {"list0": {"status": "completed"}}


def test_a_session_that_left_the_share_is_reported_and_the_rest_are_written(real, told):
    widget, paths = real
    names = [Path(p).name for p in paths]
    toasts = _toasts(widget)
    shutil.rmtree(paths[0])

    widget.bridge.setStatus(names, "completed")

    assert told == [("1 of 2 sessions weren't updated", "Details are in Logs.")]
    assert _stored(paths[1])["status"] == "completed"
    assert toasts == [(f"Set {names[1]} to Completed", True)]
    assert [row["name"] for row in widget.bridge.state["rows"]] == [names[1]]


@pytest.fixture
def other_pc(real):
    """A second SessionManager on the same share: another PC."""
    widget, _paths = real
    return SessionManager(widget.session_manager.profile_manager)


def test_undoing_an_archive_keeps_a_comment_another_pc_wrote_since_the_load(real, other_pc):
    widget, paths = real
    name = Path(paths[0]).name
    other_pc.update_session_info(paths[0], {"comments": "courier moved to 16:00"})

    widget.bridge.setStatus([name], "archived")
    widget.bridge.undo()

    after = _stored(paths[0])
    assert after["status"] == "active"
    assert after["comments"] == "courier moved to 16:00"


def test_undoing_a_comment_keeps_a_status_another_pc_set_since_the_load(real, other_pc):
    widget, paths = real
    name = Path(paths[0]).name
    other_pc.update_session_status(paths[0], "completed", manual=True)
    before = _stored(paths[0])

    widget.bridge.setComment([name], "note")
    widget.bridge.undo()

    assert _stored(paths[0]) == before


def test_undoing_the_second_of_two_changes_keeps_the_first(real):
    widget, paths = real
    name = Path(paths[0]).name
    widget.bridge.setStatus([name], "completed")
    widget.bridge.setComment([name], "note")

    widget.bridge.undo()

    after = _stored(paths[0])
    assert after["status"] == "completed"
    assert after["status_manually_set"] is True
    assert after["comments"] == "first"


def test_a_comment_on_a_session_with_an_unknown_status_can_be_undone(real, told):
    widget, paths = real
    name = Path(paths[0]).name
    info = _stored(paths[0])
    info["status"] = "frozen"
    (Path(paths[0]) / "session_info.json").write_text(json.dumps(info))

    widget.bridge.setComment([name], "note")
    widget.bridge.undo()

    assert told == []
    assert _stored(paths[0])["comments"] == "first"
    assert _stored(paths[0])["status"] == "frozen"
