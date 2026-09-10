"""The Tools page: two cards side by side from 1180px of page width, stacked
below it, never a horizontal scroll (spec §2)."""

from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication, QBoxLayout, QTabWidget

from gui.components import Card
from gui.tools_widget import ToolsWidget


@pytest.fixture
def tools(qapp, print_settings_store):
    widget = ToolsWidget(SimpleNamespace(session_path=None))
    widget.show()
    return widget


def _resize(widget, width):
    widget.resize(width, 700)
    QApplication.processEvents()


def _cards(tools):
    return (
        tools.reference_labels_widget.parentWidget(),
        tools.barcode_generator_widget.parentWidget(),
    )


def test_no_inner_tabs_and_two_cards(tools):
    assert tools.findChildren(QTabWidget) == []
    reference_card, barcode_card = _cards(tools)
    assert isinstance(reference_card, Card)
    assert isinstance(barcode_card, Card)
    assert reference_card is not barcode_card


def test_side_by_side_at_the_1366_page_width_with_no_horizontal_scroll(tools):
    _resize(tools, 1310)
    assert tools.cards_row.direction() == QBoxLayout.LeftToRight
    assert tools.scroll.widget().width() <= tools.scroll.viewport().width()

    reference_card, barcode_card = _cards(tools)
    assert reference_card.y() == barcode_card.y()
    assert reference_card.x() < barcode_card.x()
    assert reference_card.height() == barcode_card.height()


def test_side_by_side_still_fits_at_the_breakpoint(tools):
    _resize(tools, 1180)
    assert tools.cards_row.direction() == QBoxLayout.LeftToRight
    assert tools.scroll.widget().width() <= tools.scroll.viewport().width()


def test_stacked_below_1180(tools):
    _resize(tools, 1100)
    assert tools.cards_row.direction() == QBoxLayout.TopToBottom
    assert tools.scroll.widget().width() <= tools.scroll.viewport().width()

    reference_card, barcode_card = _cards(tools)
    assert reference_card.x() == barcode_card.x()
    assert reference_card.y() < barcode_card.y()


def test_widening_again_restores_side_by_side(tools):
    _resize(tools, 1100)
    _resize(tools, 1310)
    assert tools.cards_row.direction() == QBoxLayout.LeftToRight
