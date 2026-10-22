"""Guards the naming fix: the button label and the dialog title must not
both say "Client Settings" again. They named different windows, which is
the confusion Phase 6 flagged."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QApplication

from gui.actions_handler import ActionsHandler


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_profile_manager_dialog_is_gone():
    with pytest.raises(ModuleNotFoundError):
        import gui.profile_manager_dialog  # noqa: F401


def _window_recorder(monkeypatch, **attrs):
    """Stand in for SettingsWindow: record its kwargs; its exec() returns 0."""
    seen = {}

    def window(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(
            exec=lambda: 0,
            deleteLater=lambda: None,
            **{"removed_client": None, "profile_saved": False, **attrs},
        )

    monkeypatch.setattr("gui.actions_handler.SettingsWindow", window)
    return seen


def _main_window():
    profile_manager = Mock()
    profile_manager.load_shopify_config.return_value = {"settings": {}}
    profile_manager.load_client_config.return_value = {"client_name": "Other"}
    profile_manager.calculate_metadata.return_value = {"total_sessions": 0}
    profile_manager.client_has_sessions.return_value = False
    return SimpleNamespace(
        current_client_id="ME",
        profile_manager=profile_manager,
        groups_manager=Mock(list_groups=Mock(return_value=[])),
        analysis_results_df=None,
        orders_file_path=None,
        stock_file_path=None,
        session_path=None,
        client_directory=Mock(),
        remove_client=Mock(),
    )


def test_edit_settings_opens_the_profile_page_for_that_client(monkeypatch):
    seen = _window_recorder(monkeypatch)
    mw = _main_window()

    ActionsHandler(mw).open_settings_window(page="Profile", client_id="OTHER")

    assert seen["client_id"] == "OTHER"
    assert seen["initial_page"] == "Profile"
    assert seen["profile"] == {
        "client_config": {"client_name": "Other"},
        "groups": [],
        "stats": {"total_sessions": 0},
        "has_sessions": False,
    }
    assert seen["loaded_files"] is None
    assert seen["session_name"] is None


def test_archiving_from_the_profile_hands_the_client_to_the_main_window(monkeypatch):
    _window_recorder(monkeypatch, removed_client="archived")
    mw = _main_window()

    ActionsHandler(mw).open_settings_window(page="Profile", client_id="OTHER")

    mw.remove_client.assert_called_once_with("OTHER", "archived")


def test_a_profile_save_refreshes_the_client_list(monkeypatch):
    _window_recorder(monkeypatch, profile_saved=True)
    mw = _main_window()

    ActionsHandler(mw).open_settings_window(page="Profile", client_id="OTHER")

    mw.client_directory.refresh.assert_called_once_with()


def test_settings_buttons_are_labelled_settings():
    """Settings opens SettingsWindow from one entry point: the sidebar footer's
    "Client settings" (UI refresh phase 1, spec section 4.2), which replaced the
    command-bar overflow item. Object config, not a screen action."""
    from pathlib import Path

    import gui.ui_manager as mod
    from gui.components import sidebar

    source = Path(mod.__file__).read_text()
    assert source.count('QPushButton("Settings")') == 0
    assert '"Client settings…"' not in source
    assert 'QPushButton("Client Settings")' not in source
    assert '"Client Settings",' not in source
    assert '"Client settings"' in Path(sidebar.__file__).read_text()
