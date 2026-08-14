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


def test_theme_change_reblends_row_backgrounds(qtbot):
    from gui.tag_categories_dialog import TagCategoriesPanel
    from gui.theme_manager import get_theme_manager

    panel = TagCategoriesPanel(_sample_categories())
    qtbot.addWidget(panel)
    before = panel.categories_list.item(0).background().color().name()

    tm = get_theme_manager()
    original = tm.get_current_theme_name()
    try:
        tm.set_theme("dark" if original != "dark" else "light")
        after = panel.categories_list.item(0).background().color().name()
        assert after != before
        assert _labels(panel)["priority"] == "Priority"
    finally:
        tm.set_theme(original)


def test_theme_change_keeps_the_selection_visible(qtbot):
    """The rebuild runs with signals blocked, so nothing restores the current
    item on its own -- leaving Delete armed against an invisible selection."""
    from gui.tag_categories_dialog import TagCategoriesPanel
    from gui.theme_manager import get_theme_manager

    panel = TagCategoriesPanel(_sample_categories())
    qtbot.addWidget(panel)
    panel.categories_list.setCurrentRow(0)
    selected = panel.current_category_id
    assert selected

    tm = get_theme_manager()
    original = tm.get_current_theme_name()
    try:
        tm.set_theme("dark" if original != "dark" else "light")
        current = panel.categories_list.currentItem()
        assert current is not None
        assert current.data(Qt.UserRole) == selected
        assert panel.current_category_id == selected
    finally:
        tm.set_theme(original)


def test_removing_a_tag_drops_its_writeoff_mappings(qtbot):
    from gui.tag_categories_dialog import TagCategoriesPanel

    panel = TagCategoriesPanel(_sample_categories())
    qtbot.addWidget(panel)

    # select 'priority', which has tag URGENT with a writeoff mapping
    for i in range(panel.categories_list.count()):
        item = panel.categories_list.item(i)
        if item.data(Qt.UserRole) == "priority":
            panel.categories_list.setCurrentItem(item)
            break
    assert panel.current_category_id == "priority"
    assert panel.writeoff_mappings_table.rowCount() == 1

    panel.tags_list.setCurrentRow(0)  # URGENT
    panel._on_remove_tag()

    saved = panel.get_categories()["categories"]["priority"]
    assert saved["tags"] == []
    assert saved["sku_writeoff"]["mappings"] == {}


def test_category_id_validation_rejects_non_ascii():
    from gui.tag_categories_dialog import is_valid_category_id

    assert is_valid_category_id("my_category") is True
    assert is_valid_category_id("cat2") is True
    assert is_valid_category_id("категорія") is False
    assert is_valid_category_id("café") is False
    assert is_valid_category_id("") is False
    assert is_valid_category_id("___") is False
    assert is_valid_category_id("has space") is False
    assert is_valid_category_id("UPPER") is False


def test_new_category_order_is_unused_after_deletions():
    from gui.tag_categories_dialog import next_available_order

    assert next_available_order([1, 2, 3, 999]) == 4
    assert next_available_order([1, 3, 999]) == 2      # fills the gap
    assert next_available_order([999]) == 1
    assert next_available_order([]) == 1
    assert next_available_order([1, 2, 3, 4, 5, 6, 999]) == 7


def test_new_category_order_never_exceeds_the_spinbox_maximum():
    from gui.tag_categories_dialog import next_available_order

    assert next_available_order(list(range(1, 999))) <= 999


def test_writeoff_quantity_cells_are_not_editable(qtbot):
    from gui.tag_categories_dialog import TagCategoriesPanel

    panel = TagCategoriesPanel(_sample_categories())
    qtbot.addWidget(panel)
    for i in range(panel.categories_list.count()):
        item = panel.categories_list.item(i)
        if item.data(Qt.UserRole) == "priority":
            panel.categories_list.setCurrentItem(item)
            break

    for col in range(3):
        cell = panel.writeoff_mappings_table.item(0, col)
        assert not (cell.flags() & Qt.ItemIsEditable)


def test_duplicate_tag_and_sku_mapping_is_rejected():
    from gui.tag_categories_dialog import mapping_row_exists

    rows = [("URGENT", "S1"), ("URGENT", "S2")]
    assert mapping_row_exists(rows, "URGENT", "S1") is True
    assert mapping_row_exists(rows, "URGENT", "S3") is False
    assert mapping_row_exists(rows, "OTHER", "S1") is False


def test_deselecting_resets_the_color_swatch(qtbot):
    from gui.tag_categories_dialog import TagCategoriesPanel

    panel = TagCategoriesPanel(_sample_categories())
    qtbot.addWidget(panel)
    panel.categories_list.setCurrentRow(0)
    assert panel.current_color == "#4CAF50"

    panel._set_editor_enabled(False)

    assert panel.current_color == "#9E9E9E"


def test_writeoff_checkbox_toggles_the_mappings_table(qtbot):
    from gui.tag_categories_dialog import TagCategoriesPanel

    panel = TagCategoriesPanel(_sample_categories())
    qtbot.addWidget(panel)
    for i in range(panel.categories_list.count()):
        item = panel.categories_list.item(i)
        if item.data(Qt.UserRole) == "packaging":
            panel.categories_list.setCurrentItem(item)
            break

    assert panel.writeoff_enabled_checkbox.isChecked() is False
    assert panel.writeoff_mappings_table.isEnabled() is False

    panel.writeoff_enabled_checkbox.setChecked(True)
    assert panel.writeoff_mappings_table.isEnabled() is True
    assert panel.add_mapping_btn.isEnabled() is True

    panel.writeoff_enabled_checkbox.setChecked(False)
    assert panel.writeoff_mappings_table.isEnabled() is False
