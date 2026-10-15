"""The client-group manager dialog: what an operator sees and what each button does to the stored
groups (Audit 10, part A). Prompts are patched on the dialog's module; exec() is never called."""

import pytest
from PySide6.QtGui import QColor

import gui.groups_management_dialog as module
from gui.groups_management_dialog import GroupsManagementDialog
from shopify_tool.groups_manager import GroupsManager


@pytest.fixture
def groups(tmp_path):
    return GroupsManager(base_path=str(tmp_path))


@pytest.fixture
def told(monkeypatch):
    seen = {"toasts": [], "errors": []}
    monkeypatch.setattr(module, "toast", lambda _w, text, **k: seen["toasts"].append(text))
    monkeypatch.setattr(module, "show_error", lambda _w, head, body="": seen["errors"].append(head))
    return seen


def _dialog(qtbot, groups, profile_manager):
    dialog = GroupsManagementDialog(groups, profile_manager)
    qtbot.addWidget(dialog)
    return dialog


def _rows(dialog):
    table = dialog.groups_table
    return [(table.item(r, 0).text(), table.item(r, 1).text(), table.item(r, 2).text())
            for r in range(table.rowCount())]


def _select(dialog, name):
    table = dialog.groups_table
    for row in range(table.rowCount()):
        if table.item(row, 0).text() == name:
            table.selectRow(row)
            return
    raise AssertionError(f"no group row named {name}")


def test_the_table_lists_each_group_with_its_colour_and_client_count(qtbot, groups, profile_manager):
    gid = groups.create_group("Wholesale", "#FF0000")
    groups.create_group("Retail", "#00FF00")
    profile_manager.create_client_profile("AAA", "Client A")
    profile_manager.update_ui_settings("AAA", {"group_id": gid})
    dialog = _dialog(qtbot, groups, profile_manager)
    assert _rows(dialog) == [("Wholesale", "#FF0000", "1"), ("Retail", "#00FF00", "0")]
    assert not dialog.edit_btn.isEnabled() and not dialog.delete_btn.isEnabled()
    _select(dialog, "Retail")
    assert dialog.edit_btn.isEnabled() and dialog.delete_btn.isEnabled()


def test_create_adds_the_group_and_reloads_the_table(qtbot, groups, profile_manager, monkeypatch, told):
    dialog = _dialog(qtbot, groups, profile_manager)
    monkeypatch.setattr(module.QInputDialog, "getText", staticmethod(lambda *a, **k: ("  Bulk  ", True)))
    monkeypatch.setattr(module.QColorDialog, "getColor", staticmethod(lambda *a, **k: QColor("#123456")))
    dialog._create_group()
    assert _rows(dialog) == [("Bulk", "#123456", "0")]
    assert [g["name"] for g in groups.list_groups()] == ["Bulk"]
    assert told["toasts"] == ["Group Bulk created."]


@pytest.mark.parametrize(
    ("name", "ok", "color"),
    [("Bulk", False, "#123456"), ("   ", True, "#123456"), ("Bulk", True, None)],
    ids=["name cancelled", "blank name", "colour cancelled"],
)
def test_cancelling_a_prompt_creates_nothing(qtbot, groups, profile_manager, monkeypatch, told, name, ok, color):
    dialog = _dialog(qtbot, groups, profile_manager)
    monkeypatch.setattr(module.QInputDialog, "getText", staticmethod(lambda *a, **k: (name, ok)))
    monkeypatch.setattr(module.QColorDialog, "getColor",
                        staticmethod(lambda *a, **k: QColor(color) if color else QColor()))
    dialog._create_group()
    assert groups.list_groups() == [] and told["toasts"] == []


def test_a_duplicate_name_is_reported_not_raised(qtbot, groups, profile_manager, monkeypatch, told):
    groups.create_group("Bulk")
    dialog = _dialog(qtbot, groups, profile_manager)
    monkeypatch.setattr(module.QInputDialog, "getText", staticmethod(lambda *a, **k: ("bulk", True)))
    monkeypatch.setattr(module.QColorDialog, "getColor", staticmethod(lambda *a, **k: QColor("#123456")))
    dialog._create_group()
    assert told["errors"] == ["The group wasn't created"]
    assert len(groups.list_groups()) == 1


def test_edit_renames_and_recolours(qtbot, groups, profile_manager, monkeypatch, told):
    groups.create_group("Bulk", "#FF0000")
    dialog = _dialog(qtbot, groups, profile_manager)
    _select(dialog, "Bulk")
    monkeypatch.setattr(module.QInputDialog, "getText", staticmethod(lambda *a, **k: ("Pallets", True)))
    monkeypatch.setattr(module.QColorDialog, "getColor", staticmethod(lambda *a, **k: QColor("#0000FF")))
    dialog._edit_group()
    assert _rows(dialog) == [("Pallets", "#0000ff", "0")]
    assert told["toasts"] == ["Group Pallets updated."]


def test_edit_of_a_group_deleted_elsewhere_reloads_the_list(qtbot, groups, profile_manager, told):
    gid = groups.create_group("Bulk")
    dialog = _dialog(qtbot, groups, profile_manager)
    _select(dialog, "Bulk")
    groups.delete_group(gid)  # another PC
    dialog._edit_group()
    assert told["errors"] == ["The group wasn't found"]
    assert _rows(dialog) == []


def test_delete_asks_first_and_unassigns_the_clients(qtbot, groups, profile_manager, monkeypatch, told):
    gid = groups.create_group("Bulk")
    profile_manager.create_client_profile("AAA", "Client A")
    profile_manager.update_ui_settings("AAA", {"group_id": gid})
    dialog = _dialog(qtbot, groups, profile_manager)
    _select(dialog, "Bulk")
    asked = []
    monkeypatch.setattr(module.ConfirmDialog, "ask", staticmethod(lambda *a, **k: asked.append(k) or False))
    dialog._delete_group()
    assert len(groups.list_groups()) == 1  # declined
    assert asked[0]["title"] == "Delete group Bulk?" and asked[0]["body"].startswith("1 client(s)")

    monkeypatch.setattr(module.ConfirmDialog, "ask", staticmethod(lambda *a, **k: True))
    dialog._delete_group()
    assert groups.list_groups() == [] and _rows(dialog) == []
    assert profile_manager.get_ui_settings("AAA")["group_id"] is None
    assert told["toasts"] == ["Group Bulk deleted."]


def test_nothing_selected_means_edit_and_delete_do_nothing(qtbot, groups, profile_manager, told):
    groups.create_group("Bulk")
    dialog = _dialog(qtbot, groups, profile_manager)
    dialog._edit_group()
    dialog._delete_group()
    assert len(groups.list_groups()) == 1 and told == {"toasts": [], "errors": []}


def test_a_group_list_that_cannot_load_is_reported(qtbot, groups, profile_manager, monkeypatch, told):
    dialog = _dialog(qtbot, groups, profile_manager)
    monkeypatch.setattr(groups, "list_groups", lambda: (_ for _ in ()).throw(OSError("share dropped")))
    dialog._load_groups()
    assert told["errors"] == ["Groups didn't load"]
