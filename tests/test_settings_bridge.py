"""The settings pages' bridge (phase 7 spec section 3.3, phase 8 spec section 3.2)."""

import pytest
from PySide6.QtWidgets import QApplication

from gui.settings.bridge import SettingsBridge
from gui.web_page import PageBridge


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


def _caught(signal):
    seen = []
    signal.connect(lambda *args: seen.append(args))
    return seen


def test_it_is_a_page_bridge():
    assert issubclass(SettingsBridge, PageBridge)


def test_the_state_notifies_only_when_it_changes():
    bridge = SettingsBridge()
    seen = _caught(bridge.stateChanged)
    bridge.set_state({"page": "general"})
    bridge.set_state({"page": "general"})
    bridge.set_state({"page": "orders"})
    assert len(seen) == 2
    assert bridge.state == {"page": "orders"}


def test_an_edit_carries_its_action_and_its_arguments():
    bridge = SettingsBridge()
    seen = _caught(bridge.editRequested)
    bridge.edit("delimiter", ["stock", "comma"])
    bridge.edit("courier_add", [])
    bridge.edit("column_fill", ["Notes", False])
    assert seen == [
        ("delimiter", ["stock", "comma"]),
        ("courier_add", []),
        ("column_fill", ["Notes", False]),
    ]


@pytest.mark.parametrize("args", ["stock", None, 3, {"kind": "stock"}])
def test_an_edit_whose_arguments_are_not_a_list_is_dropped(args):
    bridge = SettingsBridge()
    seen = _caught(bridge.editRequested)
    bridge.edit("delimiter", args)
    assert seen == []


def test_read_columns_emits_its_signal():
    bridge = SettingsBridge()
    seen = _caught(bridge.readColumnsRequested)
    bridge.readColumns()
    assert seen == [()]


def test_test_rule_names_the_rule_and_close_test_says_so():
    bridge = SettingsBridge()
    asked = _caught(bridge.testRequested)
    closed = _caught(bridge.testClosed)
    bridge.testRule("4")
    bridge.closeTest()
    assert asked == [("4",)]
    assert closed == [()]


def test_import_export_and_the_toasts_action_reach_python():
    bridge = SettingsBridge()
    imports = _caught(bridge.importRequested)
    exports = _caught(bridge.exportRequested)
    actions = _caught(bridge.toastActionRequested)
    bridge.importFile("sets-merge")
    bridge.exportFile("sets")
    bridge.toastAction()
    assert imports == [("sets-merge",)]
    assert exports == [("sets",)]
    assert actions == [()]
