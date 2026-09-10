"""The Tools page: two cards side by side from 1180px of page width, stacked
below it, never a horizontal scroll (spec §2)."""

from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication, QBoxLayout, QTabWidget

from gui.components import Card
from gui.tools_widget import ToolsWidget, primary_holder


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


@pytest.mark.parametrize(
    ("reference_ready", "barcode_ready", "current", "expected"),
    [
        (True, False, None, "reference"),
        (False, True, None, "barcode"),
        (True, False, "barcode", "reference"),
        (False, True, "reference", "barcode"),
        (True, True, None, "reference"),
        (True, True, "barcode", "barcode"),
        (True, True, "reference", "reference"),
        (False, False, "reference", None),
        (False, False, None, None),
    ],
)
def test_primary_holder(reference_ready, barcode_ready, current, expected):
    assert primary_holder(reference_ready, barcode_ready, current) == expected


def _role(button):
    return button.property("role")


def test_the_primary_follows_whichever_card_can_run(qapp, print_settings_store):
    tools = ToolsWidget(SimpleNamespace(session_path=None))
    process = tools.reference_labels_widget.process_btn
    generate = tools.barcode_generator_widget.generate_btn
    assert "primary" not in (_role(process), _role(generate))

    process.setEnabled(True)
    assert _role(process) == "primary"

    generate.setEnabled(True)  # both ready: Reference keeps it
    assert _role(process) == "primary"
    assert _role(generate) != "primary"

    process.setEnabled(False)  # Reference running, or no longer ready
    assert _role(generate) == "primary"
    assert _role(process) == "secondary"

    generate.setEnabled(False)
    assert "primary" not in (_role(process), _role(generate))


def test_readiness_is_the_widgets_own_verdict(qapp, print_settings_store, tmp_path):
    tools = ToolsWidget(SimpleNamespace(session_path=None))
    reference = tools.reference_labels_widget
    reference.pdf_path, reference.csv_path, reference.output_dir = (
        "in.pdf",
        "in.csv",
        tmp_path,
    )
    reference._update_process_button()
    assert _role(reference.process_btn) == "primary"
