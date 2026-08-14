"""Regression test: TagCategoriesPanel must not mutate the live config dict
it's constructed with -- edits should only reach the caller via the
categories_updated signal on Save/Apply. Root cause: __init__ did a shallow
.copy(), so working_categories["categories"] was the same nested dict object
as the caller's live config; deleting/editing a category mutated it
immediately, and Cancel never restored it.
"""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from gui.tag_categories_dialog import TagCategoriesPanel


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


def test_deleting_a_category_does_not_mutate_the_caller_s_dict():
    live_config = {
        "version": 2,
        "categories": {
            "packaging": {"label": "Packaging", "color": "#FF0000", "tags": ["BOX", "BAG"], "order": 1},
        },
    }
    panel = TagCategoriesPanel(live_config)

    panel.working_categories["categories"].pop("packaging")

    assert "packaging" in live_config["categories"]  # caller's dict untouched


def _sample_categories():
    return {
        "version": 2,
        "categories": {
            "packaging": {
                "label": "Packaging", "color": "#4CAF50", "order": 1,
                "tags": ["BOX"],
                "sku_writeoff": {"enabled": False, "mappings": {}},
            },
            "priority": {
                "label": "Priority", "color": "#FF9800", "order": 2,
                "tags": ["URGENT"],
                "sku_writeoff": {"enabled": True,
                                 "mappings": {"URGENT": [{"sku": "S1", "quantity": 2.0}]}},
            },
            "status": {
                "label": "Status", "color": "#2196F3", "order": 3,
                "tags": ["CHECKED"],
                "sku_writeoff": {"enabled": False, "mappings": {}},
            },
        },
    }


def _labels(panel):
    return {k: v["label"] for k, v in panel.working_categories["categories"].items()}


def test_rebuilding_the_list_preserves_every_label(qtbot):
    from gui.tag_categories_dialog import TagCategoriesPanel

    panel = TagCategoriesPanel(_sample_categories())
    qtbot.addWidget(panel)
    panel.categories_list.setCurrentRow(0)

    panel._load_categories()

    assert _labels(panel) == {
        "packaging": "Packaging", "priority": "Priority", "status": "Status"
    }


def test_adding_a_category_preserves_every_existing_label(qtbot):
    from gui.tag_categories_dialog import TagCategoriesPanel

    panel = TagCategoriesPanel(_sample_categories())
    qtbot.addWidget(panel)
    panel.categories_list.setCurrentRow(0)

    cats = panel.working_categories["categories"]
    cats["extra"] = {
        "label": "Extra", "color": "#9E9E9E", "order": 4, "tags": [],
        "sku_writeoff": {"enabled": False, "mappings": {}},
    }
    panel._load_categories()

    assert _labels(panel)["packaging"] == "Packaging"
    assert _labels(panel)["priority"] == "Priority"
    assert _labels(panel)["status"] == "Status"


def test_deleting_a_category_preserves_the_survivors_labels(qtbot):
    from gui.tag_categories_dialog import TagCategoriesPanel

    panel = TagCategoriesPanel(_sample_categories())
    qtbot.addWidget(panel)
    panel.categories_list.setCurrentRow(0)

    del panel.working_categories["categories"]["packaging"]
    panel.current_category_id = None
    panel._load_categories()

    assert _labels(panel) == {"priority": "Priority", "status": "Status"}


def test_rebuild_preserves_tags_colors_orders_and_writeoff(qtbot):
    from gui.tag_categories_dialog import TagCategoriesPanel

    expected = _sample_categories()["categories"]
    panel = TagCategoriesPanel(_sample_categories())
    qtbot.addWidget(panel)
    panel.categories_list.setCurrentRow(0)

    panel._load_categories()

    for cid, cat in panel.working_categories["categories"].items():
        assert cat["tags"] == expected[cid]["tags"]
        assert cat["color"] == expected[cid]["color"]
        assert cat["order"] == expected[cid]["order"]
        assert cat["sku_writeoff"] == expected[cid]["sku_writeoff"]


def test_new_category_becomes_the_selected_one(qtbot):
    from gui.tag_categories_dialog import TagCategoriesPanel

    panel = TagCategoriesPanel(_sample_categories())
    qtbot.addWidget(panel)
    panel.categories_list.setCurrentRow(0)

    cats = panel.working_categories["categories"]
    cats["extra"] = {
        "label": "Extra", "color": "#9E9E9E", "order": 4, "tags": [],
        "sku_writeoff": {"enabled": False, "mappings": {}},
    }
    panel._load_categories()
    for i in range(panel.categories_list.count()):
        item = panel.categories_list.item(i)
        if item.data(Qt.UserRole) == "extra":
            panel.categories_list.setCurrentItem(item)
            break

    assert panel.current_category_id == "extra"
    assert panel.label_input.text() == "Extra"
