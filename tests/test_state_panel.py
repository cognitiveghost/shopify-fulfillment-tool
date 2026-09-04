"""9.6: one empty state, not forty.

Spec: docs/superpowers/specs/2026-09-04-phase9-bundle3-components-design.md §5
"""

import pytest
from PySide6.QtWidgets import QLabel, QPushButton

from gui.components.state_panel import StatePanel


def _labels(panel):
    return [w.text() for w in panel.card.findChildren(QLabel)]


def test_nothing_loaded_names_its_cause_and_offers_one_action(qapp):
    panel = StatePanel.nothing_loaded(
        "No orders loaded",
        "Choose a Shopify export to analyse.",
        "Choose file…",
    )
    assert "No orders loaded" in _labels(panel)
    assert "Choose a Shopify export to analyse." in _labels(panel)
    assert panel.button.text() == "Choose file…"
    assert panel.button.property("role") == "primary"


def test_working_names_the_step_and_offers_nothing(qapp):
    panel = StatePanel.working("Analysing", "Matching 268 orders against stock")
    assert "Matching 268 orders against stock" in _labels(panel)
    assert panel.button is None


def test_no_results_clears_filters_as_a_secondary_action(qapp):
    # The operator may actually want the empty answer, so this is not accented.
    panel = StatePanel.no_results(
        "No orders match", "Filter: courier is DPD and status is Blocked."
    )
    assert panel.button.text() == "Clear all filters"
    assert panel.button.property("role") == "secondary"


def test_failed_carries_its_detail_and_one_way_out(qapp):
    panel = StatePanel.failed(
        "The stock file could not be read",
        "Nothing can be allocated until it loads.",
        "stock_2026_09.csv: no column named Quantity",
        "Choose another file…",
    )
    assert "stock_2026_09.csv: no column named Quantity" in _labels(panel)
    assert panel.button.property("role") == "primary"


@pytest.mark.parametrize(
    "panel_factory",
    [
        lambda: StatePanel.nothing_loaded("t", "c", "a"),
        lambda: StatePanel.working("t", "s"),
        lambda: StatePanel.no_results("t", "c"),
        lambda: StatePanel.failed("t", "c", "d", "a"),
    ],
)
def test_every_variant_has_at_most_one_accent_filled_action(qapp, panel_factory):
    panel = panel_factory()
    primaries = [
        b for b in panel.findChildren(QPushButton) if b.property("role") == "primary"
    ]
    assert len(primaries) <= 1


def test_the_detail_line_follows_a_theme_toggle(qapp):
    """ADR 0003: the secondary colour is re-run, not baked in at build time.

    Card.add_text's `css` interpolates once, so the naive spelling leaves the
    detail line in the old palette after a toggle -- and Bundle 4, the panel's
    first real screen, would have inherited that.
    """
    from gui.theme_manager import get_theme_manager

    manager = get_theme_manager()
    before = manager.get_current_theme().name
    try:
        manager.set_theme("light")
        panel = StatePanel.failed("t", "c", "the detail line", "a")
        detail = next(w for w in panel.card.findChildren(QLabel)
                      if w.text() == "the detail line")
        assert manager.get_current_theme().text_secondary in detail.styleSheet()

        manager.set_theme("dark")
        assert manager.get_current_theme().text_secondary in detail.styleSheet()
    finally:
        manager.set_theme(before)


def test_no_variant_says_no_data(qapp):
    """"No data · Nothing to display" cannot distinguish "you have not loaded
    anything" from "your filter is too tight" from "the server is unreachable"."""
    panel = StatePanel.nothing_loaded("No orders loaded", "Choose a file.", "Open…")
    assert not any("No data" in text for text in _labels(panel))
