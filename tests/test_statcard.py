"""The stat card: a big number over a small label.

Two hand-rolled copies of this widget exist in main_window.py today -- the
session-totals card and the courier card -- which is why it is a component.
"""

import pytest

from shared.components.statcard import StatCard


@pytest.fixture
def card(qtbot):
    widget = StatCard("14", "Orders")
    qtbot.addWidget(widget)
    return widget


def test_the_card_shows_its_value_and_its_label(card):
    assert card.value_label.text() == "14"
    assert card.caption_label.text() == "Orders"


def test_the_value_can_be_replaced_without_rebuilding_the_card(card):
    card.set_value("15")
    assert card.value_label.text() == "15"


def test_the_small_variant_is_the_same_widget_at_a_smaller_scale(qtbot):
    small = StatCard("6", "DPD · orders", small=True)
    qtbot.addWidget(small)
    assert small.value_label.text() == "6"
