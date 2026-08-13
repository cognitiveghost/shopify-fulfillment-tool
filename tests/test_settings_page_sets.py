import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from gui.settings.sets import SetsPage


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_sets_page_contributes_nothing_to_collect(qapp):
    page = SetsPage({"SET-A": [{"sku": "X", "quantity": 2}]})
    assert page.collect() == {}
    assert page.validate() == (True, [])


def test_sets_page_populates_table_from_existing_decoders(qapp):
    set_decoders = {
        "SET-A": [{"sku": "X", "quantity": 2}],
        "SET-B": [],
    }
    page = SetsPage(set_decoders)
    assert page.sets_table.rowCount() == 2


def test_sets_page_delete_mutates_the_live_dict_in_place(qapp, monkeypatch):
    """SetsPage owns no collect() -- the window persists config_data as-is,
    so a delete must land on the same dict object the window holds, not a copy."""
    set_decoders = {"SET-A": [{"sku": "X", "quantity": 2}]}
    page = SetsPage(set_decoders)

    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))

    page._delete_set("SET-A")

    assert set_decoders == {}
