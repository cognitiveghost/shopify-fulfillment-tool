"""Client settings with a Profile page: the nav, one save for both files, and
Archive / Delete from the page (spec A4, plan Task 13).

Fixtures (qapp, no_modals, started_workers, make_settings_config) come from
conftest.py. A save runs on a Worker that started_workers captures; the tests
run it on this thread so the result reaches the window.
"""

from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QDialog

from gui.components import ConfirmDialog
from gui.settings.window import SettingsWindow

CLIENT_CONFIG = {
    "client_name": "Old",
    "ui_settings": {"group_id": None, "custom_color": "", "is_pinned": False},
}
PROFILE = {
    "client_config": CLIENT_CONFIG,
    "groups": [],
    "stats": {},
    "has_sessions": False,
}


def _manager(save=True, update=True):
    manager = Mock()
    manager.save_shopify_config.return_value = save
    manager.update_client_profile.return_value = update
    return manager


def _finish_save(started_workers):
    started_workers[-1].run()


@pytest.fixture
def make_window(qapp, no_modals, started_workers, make_settings_config):
    made = []

    def build(profile=None, manager=None):
        win = SettingsWindow(
            client_id="M",
            client_config=make_settings_config(),
            profile_manager=manager or Mock(),
            profile=profile,
        )
        made.append(win)
        return win

    yield build
    for win in made:
        win.deleteLater()


def _nav_names(win):
    return [
        win._settings_nav.item(row).text() for row in range(win._settings_nav.count())
    ]


def test_the_profile_page_is_the_first_entry_in_a_client_group(make_window):
    win = make_window(profile=PROFILE)
    assert win._settings_nav.item(0).text() == "Client"
    assert win._settings_nav.item(1).text() == "Profile"


def test_without_a_profile_there_is_no_profile_page(make_window):
    names = _nav_names(make_window())
    assert "Profile" not in names
    assert "Client" not in names


def test_saving_a_renamed_profile_writes_the_settings_then_the_profile(
    make_window, started_workers
):
    manager = _manager()
    win = make_window(profile=PROFILE, manager=manager)
    win._pages_by_name["Profile"].apply("profile_name", ["New"])

    win.save_settings()
    _finish_save(started_workers)

    writes = [
        name
        for name, *_ in manager.method_calls
        if name.startswith(("save_", "update_"))
    ]
    assert writes == ["save_shopify_config", "update_client_profile"]
    manager.update_client_profile.assert_called_once_with(
        "M",
        name="New",
        ui_settings={"group_id": None, "is_pinned": False},
    )
    assert win.profile_saved


def test_saving_without_a_profile_edit_leaves_the_profile_alone(
    make_window, started_workers
):
    manager = _manager()
    win = make_window(profile=PROFILE, manager=manager)

    win.save_settings()
    _finish_save(started_workers)

    manager.save_shopify_config.assert_called_once()
    manager.update_client_profile.assert_not_called()
    assert not win.profile_saved


def test_a_failed_settings_write_does_not_touch_the_profile(
    make_window, started_workers, monkeypatch
):
    shown = []
    monkeypatch.setattr(
        "gui.settings.window.show_error", lambda *args: shown.append(args)
    )
    manager = _manager(save=False)
    win = make_window(profile=PROFILE, manager=manager)
    win._pages_by_name["Profile"].apply("profile_name", ["New"])

    win.save_settings()
    _finish_save(started_workers)

    manager.update_client_profile.assert_not_called()
    assert not win.profile_saved
    assert shown[0][1] == "Settings weren't saved"


def test_archive_asks_first_then_closes_with_archived(make_window, monkeypatch):
    asked = []
    monkeypatch.setattr(
        ConfirmDialog,
        "ask",
        staticmethod(lambda parent, **kw: asked.append(kw) or True),
    )
    win = make_window(profile=PROFILE)

    win._on_client_action("archive")

    assert asked[0]["verb"] == "Archive"
    assert win.removed_client == "archived"
    assert win.result() == QDialog.DialogCode.Rejected


def test_declining_the_archive_changes_nothing(make_window, monkeypatch):
    monkeypatch.setattr(ConfirmDialog, "ask", staticmethod(lambda parent, **kw: False))
    win = make_window(profile=PROFILE)

    win._on_client_action("archive")

    assert win.removed_client is None


def test_delete_requires_the_client_id_typed(make_window, monkeypatch):
    asked = []
    monkeypatch.setattr(
        ConfirmDialog,
        "ask",
        staticmethod(lambda parent, **kw: asked.append(kw) or False),
    )
    win = make_window(profile=PROFILE)

    win._on_client_action("delete")

    assert asked[0]["require_text"] == "M"
