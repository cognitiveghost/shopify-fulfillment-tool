"""Rules inside the settings window (phase 8 spec sections 3, 4.6 and 6.2).

Fixtures (window, started_workers, no_modals, make_settings_config) come from
conftest.py. The page is edited through the host's bridge, as the page does.
The fixture config holds one order rule, "Flag big orders": uid "1".
"""

from unittest.mock import Mock

import pandas as pd

from gui.settings.rules_state import RulesDraft
from gui.settings.window import SettingsWindow


def _rules(win):
    win._select_page("Rules")
    return win._web_host.bridge


def _rows(win):
    return [row for group in win._web_host.bridge.state["rules"]["groups"] for row in group["rows"]]


def test_rules_is_a_draft_the_web_host_draws(window):
    assert isinstance(window._pages_by_name["Rules"], RulesDraft)
    bridge = _rules(window)
    assert window.tab_widget.currentWidget() is window._web_host
    assert bridge.state["page"] == "rules"
    assert [row["name"] for row in _rows(window)] == ["Flag big orders"]


def test_a_rule_edit_marks_rules_unsaved_at_once(window):
    _rules(window).edit("rule_enabled", ["1", False])
    assert window._status_label.text() == "Unsaved changes in Rules"
    assert window.save_button.isEnabled()

    _rules(window).edit("rule_enabled", ["1", True])
    assert window._status_label.text() == ""
    assert not window.save_button.isEnabled()


def test_filtering_and_opening_a_rule_mark_nothing(window):
    bridge = _rules(window)
    bridge.edit("filter", ["big"])
    bridge.edit("open", ["1"])
    assert window._status_label.text() == ""
    assert not window.save_button.isEnabled()


def test_a_marked_rule_blocks_the_save_and_the_footers_link_opens_it(window):
    bridge = _rules(window)
    # "is greater than" needs a number.
    bridge.edit("cond_value", ["1", "0", "0", "many"])
    text = window._status_label.text()
    assert text.startswith('Fix rule “Flag big orders” in <a href="Rules"')
    assert text.endswith(">Rules</a> to save.")
    assert not window.save_button.isEnabled()

    window._select_page("General")
    asked = []
    window._web_host.bridge.problemFocusRequested.connect(asked.append)
    window._open_blocker("Rules")
    assert window._settings_nav.currentItem().text() == "Rules"
    assert [row["open"] for row in _rows(window)] == [True]
    assert asked == ["rule-1-s0-c0-value"]

    bridge.edit("cond_value", ["1", "0", "0", "7"])
    assert window._status_label.text() == "Unsaved changes in Rules"
    assert window.save_button.isEnabled()


def test_save_writes_a_rule_that_is_off(window, started_workers, no_modals):
    _rules(window).edit("rule_enabled", ["1", False])
    window.save_settings()
    assert no_modals == []
    _client, written = started_workers[0].args
    assert written["rules"] == [
        {
            "name": "Flag big orders",
            "priority": 1,
            "level": "order",
            "enabled": False,
            "steps": [
                {
                    "conditions": [
                        {"field": "item_count", "operator": "is greater than", "value": "5"}
                    ],
                    "match": "ALL",
                    "actions": [{"type": "ADD_ORDER_TAG", "value": "BULK"}],
                }
            ],
        }
    ]


def test_the_session_and_the_analysis_reach_test_rule(
    qapp, no_modals, started_workers, make_settings_config
):
    analysis = pd.DataFrame({"Order_Number": ["#1"], "SKU": ["A"], "Quantity": [9]})
    win = SettingsWindow(
        client_id="M",
        client_config=make_settings_config(),
        profile_manager=Mock(),
        analysis_df=analysis,
        session_name="2026-09-30_1",
    )
    try:
        assert win._web_host.session == "2026-09-30_1"
        assert win._web_host.analysis_df is analysis
        assert win._pages_by_name["Rules"].analysis_df is analysis
        win._select_page("Rules")
        assert _rows(win)[0]["can_test"] is True
    finally:
        win.deleteLater()


def test_with_no_session_test_rule_is_off_and_the_host_has_no_name(window):
    assert window._web_host.session == ""
    _rules(window)
    assert _rows(window)[0]["can_test"] is False
