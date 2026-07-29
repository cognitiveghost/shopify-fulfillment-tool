"""Regression test: TagCategoriesPanel must not mutate the live config dict
it's constructed with -- edits should only reach the caller via the
categories_updated signal on Save/Apply. Root cause: __init__ did a shallow
.copy(), so working_categories["categories"] was the same nested dict object
as the caller's live config; deleting/editing a category mutated it
immediately, and Cancel never restored it.
"""
import pytest
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
