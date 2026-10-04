"""SettingsWebHost: one web view and its drafts (phase 7 spec section 6.5,
phase 8 spec section 6.2).

Nothing here waits for Chromium: the bridge's state is read on the Python
side, and the page's requests are made by calling the bridge's slots.
"""

import pandas as pd
import pytest
import shiboken6
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QFileDialog

from gui.settings.page_state import (
    FileColumns,
    GeneralDraft,
    OrdersDraft,
    StockDraft,
    read_file_columns,
)
from gui.settings.rules_state import RulesDraft
from gui.settings.web_host import SettingsWebHost


@pytest.fixture
def host(qtbot):
    mappings = {
        "version": 2,
        "orders": {
            "Name": "Order_Number",
            "Lineitem sku": "SKU",
            "Lineitem quantity": "Quantity",
            "Shipping Method": "Shipping_Method",
        },
        "stock": {"Article": "SKU", "Available": "Stock"},
        "additional_columns": [],
    }
    drafts = {
        "general": GeneralDraft({"low_stock_threshold": 5}, "ACME"),
        "orders": OrdersDraft(mappings, {}, "ACME"),
        "stock": StockDraft(mappings, "ACME"),
    }
    widget = SettingsWebHost(drafts)
    qtbot.addWidget(widget)
    return widget


def _edits(host):
    seen = []
    host.edited.connect(lambda: seen.append(True))
    return seen


def _pick(monkeypatch, path):
    asked = []

    def choose(parent, title, start, filters):
        asked.append((title, filters))
        return str(path), ""

    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(choose))
    return asked


def _errors(monkeypatch):
    seen = []
    monkeypatch.setattr(
        "gui.settings.web_host.show_error",
        lambda parent, headline, what: seen.append((headline, what)),
    )
    return seen


def test_it_opens_on_the_first_draft(host):
    assert host.bridge.state["page"] == "general"


def test_show_page_draws_that_draft(host):
    host.show_page("stock")
    assert host.bridge.state["page"] == "stock"
    assert host.bridge.state["title"] == "Stock mapping"


def test_an_edit_reaches_the_draft_is_drawn_and_is_announced(host):
    seen = _edits(host)
    host.bridge.edit("threshold", ["9"])
    assert host.drafts["general"].threshold == "9"
    assert host.bridge.state["general"]["threshold"]["value"] == "9"
    assert seen == [True]


def test_an_edit_that_changes_nothing_is_not_announced(host):
    seen = _edits(host)
    host.bridge.edit("threshold", ["5"])
    host.bridge.edit("no_such_action", [])
    assert seen == []


def test_an_edit_goes_to_the_page_that_is_showing(host):
    host.show_page("orders")
    host.bridge.edit("threshold", ["9"])
    assert host.drafts["general"].threshold == "5"
    host.bridge.edit("courier_add", [])
    assert host.drafts["orders"].courier_rows == [["", ""]]


def test_read_columns_offers_the_chosen_files_columns(host, monkeypatch, tmp_path):
    path = tmp_path / "picked.csv"
    path.write_text("Name,Lineitem sku,Notes\n#1,ABC,leave at door\n", encoding="utf-8")
    asked = _pick(monkeypatch, path)
    seen = _edits(host)
    host.show_page("orders")

    host.bridge.readColumns()

    assert asked == [("Select Orders CSV", "CSV Files (*.csv);;All Files (*)")]
    assert host.drafts["orders"].file == FileColumns(
        "picked.csv",
        ("Name", "Lineitem sku", "Notes"),
        {"Name": "#1", "Lineitem sku": "ABC", "Notes": "leave at door"},
        False,
    )
    assert host.drafts["stock"].file is None
    mapping = host.bridge.state["mapping"]
    assert mapping["can_pick"] is True
    assert mapping["source"] == {
        "lead": "Columns read from",
        "file": "picked.csv",
        "tail": ".",
    }
    assert seen == [True]


def test_read_columns_changes_no_mapping(host, monkeypatch, tmp_path):
    path = tmp_path / "picked.csv"
    path.write_text("A,B\n1,2\n", encoding="utf-8")
    _pick(monkeypatch, path)
    host.show_page("orders")
    before = dict(host.drafts["orders"].chosen)
    host.bridge.readColumns()
    assert host.drafts["orders"].chosen == before


def test_a_cancelled_dialog_changes_nothing(host, monkeypatch):
    _pick(monkeypatch, "")
    seen = _edits(host)
    host.show_page("stock")
    host.bridge.readColumns()
    assert host.drafts["stock"].file is None
    assert seen == []


def test_a_file_that_cannot_be_read_says_so_and_changes_nothing(
    host, monkeypatch, tmp_path
):
    _pick(monkeypatch, tmp_path / "gone.csv")
    errors = _errors(monkeypatch)
    seen = _edits(host)
    host.show_page("orders")
    host.bridge.readColumns()
    assert errors == [("The column names couldn't be read", "Details are in Logs.")]
    assert host.drafts["orders"].file is None
    assert seen == []


def test_an_empty_file_cannot_be_read(host, monkeypatch, tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("", encoding="utf-8")
    _pick(monkeypatch, path)
    errors = _errors(monkeypatch)
    host.show_page("orders")
    host.bridge.readColumns()
    assert errors == [("The column names couldn't be read", "Details are in Logs.")]


def test_general_has_no_columns_to_read(host, monkeypatch, tmp_path):
    asked = _pick(monkeypatch, tmp_path / "x.csv")
    host.bridge.readColumns()
    assert asked == []


def test_focus_problem_asks_the_page_for_that_control(host):
    seen = []
    host.bridge.problemFocusRequested.connect(seen.append)
    host.focus_problem("threshold")
    assert seen == ["threshold"]


def test_read_file_columns_names_the_file_and_marks_where_it_came_from(tmp_path):
    path = tmp_path / "stock-30-09.csv"
    path.write_text("Артикул;Наличност\nABC;4\nXYZ;9\n", encoding="utf-8")
    assert read_file_columns(path, loaded=True) == FileColumns(
        "stock-30-09.csv",
        ("Артикул", "Наличност"),
        {"Артикул": "ABC", "Наличност": "4"},
        True,
    )


# --- Rules: Test rule, and the footer's link (phase 8) ------------------------


def _analysis():
    return pd.DataFrame(
        {
            "Order_Number": ["#1", "#1", "#2", "#3"],
            "SKU": ["A", "B", "B", "A"],
            "Quantity": [4, 3, 1, 1],
            "Internal_Tags": ["[]"] * 4,
        }
    )


def _rule(name, operator="equals", value="A"):
    return {
        "name": name,
        "level": "article",
        "steps": [
            {
                "conditions": [{"field": "SKU", "operator": operator, "value": value}],
                "match": "ALL",
                "actions": [{"type": "ADD_INTERNAL_TAG", "value": "T"}],
            }
        ],
    }


@pytest.fixture
def test_workers(monkeypatch):
    """Catch the worker a test starts instead of letting a thread run it:
    the test then delivers its result when it chooses, by calling run()."""
    started = []
    monkeypatch.setattr(
        "gui.settings.web_host.QThreadPool",
        type(
            "Pool",
            (),
            {
                "globalInstance": staticmethod(
                    lambda: type("P", (), {"start": staticmethod(started.append)})()
                )
            },
        ),
    )
    return started


@pytest.fixture
def rules_host(qtbot, test_workers):
    drafts = {
        "general": GeneralDraft({"low_stock_threshold": 5}, "ACME"),
        "rules": RulesDraft([_rule("VIP"), _rule("bad", "matches regex", "(")], _analysis()),
    }
    widget = SettingsWebHost(drafts, analysis_df=_analysis(), session="2026-09-30_1")
    qtbot.addWidget(widget)
    widget.show_page("rules")
    return widget


def test_a_rule_edit_reaches_the_rules_draft(rules_host):
    seen = _edits(rules_host)
    rules_host.bridge.edit("rule_name", ["1", "VIP first"])
    assert rules_host.drafts["rules"].rules[0]["name"] == "VIP first"
    assert rules_host.bridge.state["rules"]["groups"][0]["rows"][0]["name"] == "VIP first"
    assert seen == [True]


def test_a_test_shows_the_panel_running_then_its_result(rules_host, test_workers):
    rules_host.bridge.testRule("1")
    test = rules_host.bridge.state["test"]
    assert (test["status"], test["uid"], test["message"]) == ("running", "1", "Testing 3 orders…")
    assert test["intro"]["session"] == "2026-09-30_1"
    assert len(test_workers) == 1

    test_workers[0].run()
    test = rules_host.bridge.state["test"]
    assert (test["status"], test["uid"]) == ("done", "1")
    assert (test["matched"], test["total"]) == ("2", "of 3 orders match")
    assert [row["order"] for row in test["rows"]] == ["#1", "#3"]
    # The page is still the Rules page under the panel.
    assert rules_host.bridge.state["page"] == "rules"


def test_a_test_runs_the_rule_as_edited(rules_host, test_workers):
    rules_host.bridge.edit("cond_value", ["1", "0", "0", "B"])
    rules_host.bridge.testRule("1")
    test_workers[0].run()
    assert [row["order"] for row in rules_host.bridge.state["test"]["rows"]] == ["#1", "#2"]


def test_a_test_does_not_mark_the_page_unsaved(rules_host, test_workers):
    seen = _edits(rules_host)
    rules_host.bridge.testRule("1")
    test_workers[0].run()
    rules_host.bridge.closeTest()
    assert seen == []


def test_close_takes_the_panel_away(rules_host, test_workers):
    rules_host.bridge.testRule("1")
    test_workers[0].run()
    rules_host.bridge.closeTest()
    assert "test" not in rules_host.bridge.state
    rules_host.bridge.closeTest()
    assert "test" not in rules_host.bridge.state


def test_a_result_that_arrives_after_close_is_dropped(rules_host, test_workers):
    rules_host.bridge.testRule("1")
    rules_host.bridge.closeTest()
    test_workers[0].run()
    assert "test" not in rules_host.bridge.state


def test_a_result_from_a_test_that_was_replaced_is_dropped(rules_host, test_workers):
    rules_host.bridge.testRule("1")
    rules_host.bridge.closeTest()
    rules_host.bridge.edit("cond_value", ["1", "0", "0", "B"])
    rules_host.bridge.testRule("1")
    test_workers[0].run()
    assert rules_host.bridge.state["test"]["status"] == "running"
    test_workers[1].run()
    assert [row["order"] for row in rules_host.bridge.state["test"]["rows"]] == ["#1", "#2"]


def test_showing_another_page_closes_the_panel(rules_host, test_workers):
    rules_host.bridge.testRule("1")
    rules_host.show_page("general")
    assert "test" not in rules_host.bridge.state
    test_workers[0].run()
    assert "test" not in rules_host.bridge.state
    assert rules_host.bridge.state["page"] == "general"


def test_a_rule_that_cannot_be_tested_starts_nothing(rules_host, test_workers):
    rules_host.bridge.testRule("2")  # its regex is marked
    rules_host.bridge.testRule("9")  # no such rule
    rules_host.show_page("general")
    rules_host.bridge.testRule("1")  # not on Rules
    assert test_workers == []
    assert "test" not in rules_host.bridge.state


def test_a_test_that_raises_shows_the_failed_panel_and_is_logged(
    rules_host, test_workers, monkeypatch, caplog
):
    def boom(rule, analysis_df, session):
        raise RuntimeError("engine fell over")

    monkeypatch.setattr("gui.settings.web_host.run_rule_test", boom)
    rules_host.bridge.testRule("1")
    test_workers[0].run()
    test = rules_host.bridge.state["test"]
    assert (test["status"], test["uid"]) == ("failed", "1")
    assert test["message"] == "The rule test didn’t finish. Details are in Logs."
    assert "engine fell over" in caplog.text


def test_focus_problem_opens_the_rule_before_it_asks_for_the_control(rules_host):
    key = rules_host.drafts["rules"].blocker_key()
    assert key == "rule-2-s0-c0-value"
    asked = []

    def on_focus(wanted):
        rows = rules_host.bridge.state["rules"]["groups"][0]["rows"]
        asked.append((wanted, [row["open"] for row in rows]))

    rules_host.bridge.problemFocusRequested.connect(on_focus)
    rules_host.focus_problem(key)
    # By the time the page is asked, the state that draws the control is out.
    assert asked == [(key, [False, True])]


def test_a_result_that_arrives_after_the_host_is_gone_raises_nothing(qtbot, test_workers):
    """The dialog closed while its test was still running."""
    drafts = {"rules": RulesDraft([_rule("VIP")], _analysis())}
    widget = SettingsWebHost(drafts, analysis_df=_analysis())
    widget.bridge.testRule("1")
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert not shiboken6.isValid(widget)

    test_workers[0].run()
