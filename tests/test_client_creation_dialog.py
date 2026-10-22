"""Creating a client: the dialog's fields, live ID check, and what it stores (spec A3)."""

import pytest
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QDialog

import gui.client_settings_dialog as module
from gui.client_settings_dialog import ClientCreationDialog
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


def _creation(qtbot, profile_manager, groups=None, clients=None, archived_ids=None):
    dialog = ClientCreationDialog(
        profile_manager,
        groups,
        clients=clients if clients is not None else [("SRC", "Source Co")],
        archived_ids=archived_ids if archived_ids is not None else ["OLD"],
    )
    qtbot.addWidget(dialog)
    return dialog


def test_copy_from_lists_defaults_then_clients(qtbot, profile_manager):
    d = _creation(qtbot, profile_manager)
    assert [d.copy_combo.itemText(i) for i in range(d.copy_combo.count())] == ["Defaults", "Source Co  (SRC)"]
    assert d.copy_combo.itemData(0) is None
    assert d.copy_combo.itemData(1) == "SRC"


def test_the_id_is_checked_as_you_type(qtbot, profile_manager):
    d = _creation(qtbot, profile_manager)
    d.client_id_input.setText("src")
    assert "CLIENT_SRC already exists." in d.client_id_error.text()
    assert not d.create_button.isEnabled()
    d.client_id_input.setText("old")
    assert "CLIENT_OLD is archived. Restore it from Archived clients." in d.client_id_error.text()
    d.client_id_input.setText("bad id!")
    assert d.client_id_error.text()  # validate_client_id's own message
    assert not d.create_button.isEnabled()
    d.client_id_input.setText("NEW")
    assert d.client_id_error.text() == ""
    assert d.create_button.isEnabled()


def test_create_writes_look_and_copied_settings_at_once(qtbot, profile_manager):
    pm = profile_manager
    assert pm.create_client_profile("SRC", "Source Co")
    d = _creation(qtbot, pm)
    d.client_id_input.setText("NEW")
    d.client_name_input.setText("New Co")
    d.copy_combo.setCurrentIndex(1)
    d.pin_checkbox.setChecked(True)
    d.validate_and_accept()
    assert pm.get_ui_settings("NEW")["is_pinned"] is True
    assert pm.load_shopify_config("NEW")["client_name"] == "New Co"


# --- moved from test_client_settings_dialog.py ---------------------------------------------


def test_creation_without_groups_disables_the_group_choice(qtbot, profile_manager):
    dialog = _creation(qtbot, profile_manager)
    assert not dialog.group_combo.isEnabled()
    assert dialog.group_combo.count() == 1


@pytest.mark.parametrize(
    ("client_id", "name", "field", "message"),
    [
        ("", "Acme", "client_id_error", "Enter a client ID."),
        ("ACME", "", "client_name_error", "Enter a client name."),
        ("A B", "Acme", "client_id_error", "Client ID can only contain letters, numbers, and underscore"),
        ("X" * 21, "Acme", "client_id_error", "Client ID too long (max 20 characters)"),
    ],
)
def test_creation_refuses_bad_input_inline(qtbot, profile_manager, client_id, name, field, message):
    dialog = _creation(qtbot, profile_manager)
    dialog.client_id_input.setText(client_id)
    dialog.client_name_input.setText(name)
    dialog.validate_and_accept()
    assert getattr(dialog, field).text() == message
    assert dialog.result() != QDialog.Accepted
    assert profile_manager.list_clients() == []


def test_creation_stores_the_client_with_its_appearance(qtbot, profile_manager, groups, monkeypatch):
    dialog = _creation(qtbot, profile_manager, groups)
    monkeypatch.setattr(module.QColorDialog, "getColor", staticmethod(lambda *a, **k: QColor("#123456")))
    dialog._choose_color()
    dialog.client_id_input.setText(" acme ")
    dialog.client_name_input.setText("Acme Ltd")
    dialog.group_combo.setCurrentIndex(1)
    dialog.pin_checkbox.setChecked(True)
    dialog.validate_and_accept()

    assert dialog.result() == QDialog.Accepted
    assert profile_manager.list_clients() == ["ACME"]
    ui = profile_manager.get_ui_settings("ACME")
    assert ui["is_pinned"] is True
    assert ui["custom_color"] == "#123456"
    assert ui["group_id"] == groups.list_groups()[0]["id"]
    assert profile_manager.load_client_config("ACME")["client_name"] == "Acme Ltd"


def test_a_cancelled_colour_prompt_keeps_the_colour(qtbot, profile_manager, monkeypatch):
    dialog = _creation(qtbot, profile_manager)
    before = dialog.current_color
    monkeypatch.setattr(module.QColorDialog, "getColor", staticmethod(lambda *a, **k: QColor()))
    dialog._choose_color()
    assert dialog.current_color == before


def test_creating_an_existing_client_says_so_inline(qtbot, profile_manager):
    profile_manager.create_client_profile("ACME", "Acme Ltd")
    dialog = _creation(qtbot, profile_manager, clients=[])
    dialog.client_id_input.setText("acme")
    dialog.client_name_input.setText("Other")
    dialog.validate_and_accept()
    assert dialog.client_id_error.text() == "CLIENT_ACME already exists or is archived."
    assert dialog.result() != QDialog.Accepted


def test_a_failing_create_is_reported_and_keeps_the_dialog_open(qtbot, profile_manager, errors, monkeypatch):
    def boom(*a, **k):
        raise ProfileManagerError("share dropped")

    monkeypatch.setattr(profile_manager, "create_client_profile", boom)
    dialog = _creation(qtbot, profile_manager)
    dialog.client_id_input.setText("ACME")
    dialog.client_name_input.setText("Acme Ltd")
    dialog.validate_and_accept()
    assert errors == ["The client profile wasn't created"]
    assert dialog.result() != QDialog.Accepted


def test_typing_clears_an_inline_message(qtbot, profile_manager):
    dialog = _creation(qtbot, profile_manager)
    dialog.validate_and_accept()
    assert dialog.client_id_error.text() == "Enter a client ID."
    dialog.client_id_input.setText("A")
    assert dialog.client_id_error.text() == ""
