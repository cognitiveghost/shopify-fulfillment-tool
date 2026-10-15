"""Creating a client and editing its profile: what the dialogs show, validate and store
(Audit 10, part A). Real ProfileManager under tmp_path; colour prompts are patched."""

import pytest
from PySide6.QtCore import QThreadPool
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QDialog

import gui.client_settings_dialog as module
from gui.client_settings_dialog import ClientSettingsDialog
from shopify_tool.groups_manager import GroupsManager
from shopify_tool.profile_manager import ProfileManagerError


@pytest.fixture
def groups(tmp_path):
    manager = GroupsManager(base_path=str(tmp_path))
    manager.create_group("Wholesale")
    return manager


@pytest.fixture
def errors(monkeypatch):
    seen = []
    monkeypatch.setattr(module, "show_error", lambda _w, head, body="": seen.append(head))
    return seen


# --- ClientSettingsDialog ---------------------------------------------------------------


@pytest.fixture
def client(profile_manager, groups):
    profile_manager.create_client_profile("ACME", "Acme Ltd")
    profile_manager.update_ui_settings("ACME", {
        "is_pinned": True, "group_id": groups.list_groups()[0]["id"],
        "custom_color": "#abcdef", "custom_badges": ["VIP", "PRIORITY"]})
    return "ACME"


def _settings(qtbot, profile_manager, groups, client_id="ACME"):
    dialog = ClientSettingsDialog(client_id, profile_manager, groups)
    qtbot.addWidget(dialog)
    return dialog


def test_the_form_shows_the_stored_profile(qtbot, profile_manager, groups, client):
    dialog = _settings(qtbot, profile_manager, groups)
    assert dialog.client_name_input.text() == "Acme Ltd"
    assert dialog.pin_checkbox.isChecked()
    assert dialog.group_combo.currentText() == "Wholesale"
    assert dialog.current_color == "#abcdef"
    assert dialog.badges_input.text() == "VIP, PRIORITY"
    assert dialog.total_sessions_label.text() == "0"
    assert dialog.last_session_label.text() == "Never"


def test_saving_writes_the_edited_profile_and_closes(qtbot, profile_manager, groups, client, monkeypatch):
    dialog = _settings(qtbot, profile_manager, groups)
    monkeypatch.setattr(module.QColorDialog, "getColor", staticmethod(lambda *a, **k: QColor("#00ff00")))
    dialog._choose_color()
    dialog.client_name_input.setText(" Acme Group ")
    dialog.pin_checkbox.setChecked(False)
    dialog.group_combo.setCurrentIndex(0)
    dialog.badges_input.setText("a, ,b")

    dialog._save_and_accept()
    assert not dialog.save_button.isEnabled() and dialog.save_button.text() == "Saving..."
    qtbot.waitUntil(lambda: not dialog._is_saving, timeout=5000)
    QThreadPool.globalInstance().waitForDone(5000)

    assert dialog.result() == QDialog.Accepted
    config = profile_manager.load_client_config("ACME")
    assert config["client_name"] == "Acme Group"
    ui = profile_manager.get_ui_settings("ACME")
    assert (ui["is_pinned"], ui["group_id"], ui["custom_color"], ui["custom_badges"]) == (
        False, None, "#00ff00", ["a", "b"])


def test_a_save_that_returns_false_keeps_the_dialog_open(qtbot, profile_manager, groups, client, errors, monkeypatch):
    monkeypatch.setattr(profile_manager, "update_client_profile", lambda *a, **k: False)
    dialog = _settings(qtbot, profile_manager, groups)
    dialog._save_and_accept()
    qtbot.waitUntil(lambda: not dialog._is_saving, timeout=5000)
    assert errors == ["The settings weren't saved"]
    assert dialog.result() != QDialog.Accepted
    assert dialog.save_button.isEnabled() and dialog.save_button.text() == "Save"


def test_a_save_that_raises_is_reported_and_unlocks_the_button(qtbot, profile_manager, groups, client, errors,
                                                                monkeypatch):
    def boom(*a, **k):
        raise ProfileManagerError("share dropped")

    monkeypatch.setattr(profile_manager, "update_client_profile", boom)
    dialog = _settings(qtbot, profile_manager, groups)
    dialog._save_and_accept()
    qtbot.waitUntil(lambda: not dialog._is_saving, timeout=5000)
    assert errors == ["The settings weren't saved"]
    assert dialog.save_button.isEnabled()


def test_the_dialog_cannot_be_dismissed_while_saving(qtbot, profile_manager, groups, client):
    dialog = _settings(qtbot, profile_manager, groups)
    closed = []
    dialog.rejected.connect(lambda: closed.append(True))
    dialog._is_saving = True
    dialog.reject()
    assert closed == []
    dialog._is_saving = False
    dialog.reject()
    assert closed == [True]


def test_a_client_whose_config_will_not_load_rejects_itself(qtbot, profile_manager, groups, errors):
    dialog = ClientSettingsDialog("MISSING", profile_manager, groups)
    qtbot.addWidget(dialog)
    assert dialog.config in (None, {})  # it gave up in __init__, before building any tab
    assert not hasattr(dialog, "tabs")
