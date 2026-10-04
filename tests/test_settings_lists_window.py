"""Sets, Weight, Reports and Tag categories inside the settings window (phase 9
spec sections 8 and 9).

Fixtures (window, started_workers, no_modals) come from conftest.py. The pages
are edited through the host's bridge, as the pages do. The fixture config has
one product (uid "1"), one box (uid "2"), one packing list (uid "1"), one stock
export (uid "2"), no set and no tag category.
"""

import pytest
from PySide6.QtCore import QTimer

from gui.settings.reports_state import ReportsDraft
from gui.settings.sets_state import SetsDraft
from gui.settings.tags_state import TagsDraft
from gui.settings.weight_state import WeightDraft
from gui.settings.window import WEB_PAGE_KEYS


def _on(win, name):
    win._select_page(name)
    return win._web_host.bridge


@pytest.mark.parametrize(
    ("name", "kind"),
    [("Sets", SetsDraft), ("Weight", WeightDraft), ("Reports", ReportsDraft), ("Tag categories", TagsDraft)],
)
def test_each_page_is_a_draft_the_web_host_draws(window, name, kind):
    assert isinstance(window._pages_by_name[name], kind)
    bridge = _on(window, name)
    assert window.tab_widget.currentWidget() is window._web_host
    assert bridge.state["page"] == WEB_PAGE_KEYS[name]


def test_no_page_is_a_widget_and_nothing_polls(window):
    assert window.tab_widget.count() == 1
    assert window.findChildren(QTimer) == []


def test_an_edit_on_each_page_marks_it_unsaved_at_once(window):
    _on(window, "Weight").edit("divisor", ["6000"])
    assert window._status_label.text() == "Unsaved changes in Weight"
    _on(window, "Reports").edit("report_name", ["1", "Renamed"])
    _on(window, "Tag categories").edit("cat_add", [])
    _on(window, "Sets").edit("set_add", [])
    # The new set has no SKU yet: that blocks, and the footer says so first.
    assert window._blocked == {"Sets": "Fix the new set"}
    _on(window, "Sets").edit("set_delete", ["1"])
    assert window._status_label.text() == "Unsaved changes in Weight, Reports, Tag categories"
    assert window.save_button.isEnabled()


def test_opening_and_filtering_mark_nothing(window):
    _on(window, "Reports").edit("open", ["1"])
    _on(window, "Weight").edit("product_filter", ["sku"])
    assert window._status_label.text() == ""
    assert not window.save_button.isEnabled()


def test_a_weight_blocker_reaches_the_footer_and_its_link_asks_for_the_field(window):
    _on(window, "Weight").edit("product_text", ["1", "w", "wide"])
    text = window._status_label.text()
    assert text.startswith('Fix product “SKU1” in <a href="Weight"')
    assert not window.save_button.isEnabled()

    window._select_page("General")
    asked = []
    window._web_host.bridge.problemFocusRequested.connect(asked.append)
    window._open_blocker("Weight")
    assert window._settings_nav.currentItem().text() == "Weight"
    assert asked == ["product-1-w"]


def test_a_sets_blocker_opens_the_set_before_it_asks_for_the_field(window):
    bridge = _on(window, "Sets")
    bridge.edit("set_add", [])
    bridge.edit("set_sku", ["1", "SET-A"])
    bridge.edit("comp_sku", ["1", "0", "HAT"])
    bridge.edit("comp_quantity", ["1", "0", "x"])
    bridge.edit("close", [])
    assert window._blocked == {"Sets": "Fix set “SET-A”"}

    window._select_page("General")
    asked = []
    window._web_host.bridge.problemFocusRequested.connect(asked.append)
    window._open_blocker("Sets")
    assert window._web_host.bridge.state["sets"]["rows"][0]["open"] is True
    assert asked == ["set-1-c0-quantity"]


def test_a_tag_category_blocker_names_the_category_by_its_place(window):
    bridge = _on(window, "Tag categories")
    bridge.edit("cat_add", [])
    bridge.edit("cat_label", ["1", ""])
    assert window._blocked == {"Tag categories": "Name category 1"}
    assert window._status_label.text().startswith("Name category 1 in <a")


def test_save_writes_each_pages_keys(window, started_workers):
    bridge = _on(window, "Sets")
    bridge.edit("set_add", [])
    bridge.edit("set_sku", ["1", "SET-A"])
    bridge.edit("comp_sku", ["1", "0", "HAT"])
    _on(window, "Weight").edit("product_text", ["1", "l", "12,5"])
    bridge = _on(window, "Reports")
    bridge.edit("report_add", ["stock"])
    bridge.edit("report_name", ["3", "Weekly"])
    bridge = _on(window, "Tag categories")
    bridge.edit("cat_add", [])
    bridge.edit("cat_label", ["1", "Gift wrap"])
    bridge.edit("tag_add", ["1", "gift"])

    window.save_settings()

    assert len(started_workers) == 1
    written = started_workers[0].args[1]
    assert written["set_decoders"] == {"SET-A": [{"sku": "HAT", "quantity": 1}]}
    assert written["weight_config"]["products"]["SKU1"]["length_cm"] == 12.5
    assert [c["name"] for c in written["stock_export_configs"]] == ["Daily", "Weekly"]
    assert written["packing_list_configs"][0]["exclude_skus"] == ["X1", "X2"]
    category = written["tag_categories"]["categories"]["gift_wrap"]
    assert (category["label"], category["tags"], category["order"]) == ("Gift wrap", ["GIFT"], 1)


def test_a_save_fixes_a_new_tag_categorys_id(window, started_workers):
    bridge = _on(window, "Tag categories")
    bridge.edit("cat_add", [])
    bridge.edit("cat_label", ["1", "Gifts"])
    window.save_settings()
    window._on_save_settings_result(True)
    bridge.edit("cat_label", ["1", "Presents"])
    saved = window._pages_by_name["Tag categories"].collect()["tag_categories"]["categories"]
    assert list(saved) == ["gifts"]
    assert saved["gifts"]["label"] == "Presents"
