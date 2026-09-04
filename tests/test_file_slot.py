"""FileSlot owns whether a file is usable.

Before Bundle 5 that fact lived in a QLabel containing the string "✓",
which FileHandler.check_files_ready read back to decide whether Run
Analysis could be enabled.
"""

from pathlib import Path

import pytest

from gui.components import FileSlot


@pytest.fixture
def slot(qapp):
    return FileSlot("Orders file", "Drop the Shopify orders export here")


def test_a_new_slot_is_empty_and_not_valid(slot):
    assert slot.path is None
    assert slot.is_valid is False
    assert slot.missing_columns == []
    assert slot.choose_button.isVisible() or not slot.isVisible()


def test_loading_a_file_makes_the_slot_valid(slot):
    slot.set_loaded(Path("/tmp/orders.csv"), "1 842 rows · 4 columns matched")
    assert slot.path == Path("/tmp/orders.csv")
    assert slot.is_valid is True
    assert slot.missing_columns == []


def test_an_invalid_file_is_not_valid_and_keeps_its_missing_columns(slot):
    slot.set_invalid(
        Path("/tmp/stock.csv"), ["Stock"], ["Артикул", "Име", "Цена"]
    )
    assert slot.path == Path("/tmp/stock.csv")
    assert slot.is_valid is False
    assert slot.missing_columns == ["Stock"]
    assert slot.present_columns == ["Артикул", "Име", "Цена"]


def test_the_invalid_state_offers_both_ways_out(slot):
    slot.set_invalid(Path("/tmp/stock.csv"), ["Stock"], ["Артикул"])
    assert slot.map_columns_button.isEnabled()
    assert slot.choose_other_button.isEnabled()


def test_the_error_names_the_consequence_before_the_cause(slot):
    slot.set_invalid(Path("/tmp/stock.csv"), ["Stock"], ["Артикул"])
    text = slot.error_text()
    assert text.index("Nothing can be allocated") < text.index("Stock")
    assert "stock.csv" in text
    assert "Артикул" in text


def test_clearing_returns_the_slot_to_empty(slot):
    slot.set_loaded(Path("/tmp/orders.csv"), "1 842 rows")
    slot.clear()
    assert slot.path is None
    assert slot.is_valid is False


def test_every_transition_emits_changed(slot, qtbot):
    with qtbot.waitSignal(slot.changed):
        slot.set_loaded(Path("/tmp/orders.csv"), "1 842 rows")
    with qtbot.waitSignal(slot.changed):
        slot.set_invalid(Path("/tmp/orders.csv"), ["SKU"], ["Name"])
    with qtbot.waitSignal(slot.changed):
        slot.clear()
