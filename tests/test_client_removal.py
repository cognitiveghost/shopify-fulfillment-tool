"""Removing a client from the app, and the Archived clients dialog (spec A6).

The main_window fixture is test_stale_session's: a real MainWindow on a tmp
server with a real ProfileManager, so the folder moves happen in tmp_path.
"""

from test_stale_session import main_window  # noqa: F401  main_window is a fixture

from gui.client_settings_dialog import ArchivedClientsDialog
from gui.components.commandbar import CommandBar
from shopify_tool.profile_manager import ProfileManagerError


def test_archiving_the_current_client_clears_it_and_moves_the_folders(main_window, qtbot):  # noqa: F811
    win = main_window
    # Profiles are stored under their upper-case ID, as the app writes them.
    win.current_client_id = "ACME"
    win.remove_client("ACME", "archived")

    assert win.current_client_id is None
    assert win.command_bar.current_client() == ""
    archived = win.profile_manager.clients_dir / "_archive" / "CLIENT_ACME"
    qtbot.waitUntil(archived.exists, timeout=5000)


def test_a_refused_archive_shows_its_reason(main_window, qtbot, monkeypatch):  # noqa: F811
    shown = []
    monkeypatch.setattr(
        "gui.main_window_pyside.show_error", lambda _w, h, d: shown.append((h, d))
    )

    def refuse(client_id):
        raise ProfileManagerError(
            "CLIENT_X is open on another PC. Close it there, then try again."
        )

    monkeypatch.setattr(main_window.profile_manager, "archive_client", refuse)

    main_window.remove_client("X", "archived")

    qtbot.waitUntil(lambda: bool(shown), timeout=5000)
    assert shown[0] == (
        "CLIENT_X wasn't archived",
        "CLIENT_X is open on another PC. Close it there, then try again.",
    )


def test_the_archived_dialog_lists_and_restores(qapp):
    restored = []
    dialog = ArchivedClientsDialog(
        [
            {
                "client_id": "OLD",
                "client_name": "Old Co",
                "archived_at": "2026-10-01T10:00:00+03:00",
            }
        ],
        restore=restored.append,
    )

    assert dialog.table.rowCount() == 1
    assert dialog.table.item(0, 0).text() == "OLD"
    dialog.table.selectRow(0)
    dialog.restore_button.click()
    assert restored == ["OLD"]


def test_the_archived_dialog_says_when_there_are_none(qapp):
    dialog = ArchivedClientsDialog([], restore=lambda client_id: None)

    assert dialog.empty_label.text() == "No archived clients."
    assert not dialog.restore_button.isEnabled()


def test_a_remembered_archived_client_opens_on_choose_a_client(qapp):
    bar = CommandBar()
    bar.set_current_client("GONE")  # remembered before the list arrives
    bar.set_clients_from(
        {
            "special_groups": {},
            "custom_groups": [],
            "all_clients": ["ACME"],
            "pinned_client_ids": set(),
            "group_members": {},
            "card_data": {},
        }
    )

    assert bar.current_client() == ""
    assert bar.client_selector.currentIndex() == -1
