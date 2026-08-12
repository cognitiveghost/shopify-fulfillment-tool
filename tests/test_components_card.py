"""Construction tests for the Card component. No window needed."""
import pytest
from PySide6.QtWidgets import QApplication, QLabel

from gui.components.card import Card
from gui.theme_manager import TYPE_SCALE


@pytest.fixture(scope="module", autouse=True)
def _app():
    yield QApplication.instance() or QApplication([])


def test_defaults_match_the_stat_card_geometry_it_replaces():
    card = Card()
    margins = card.layout().contentsMargins()
    assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (12, 8, 12, 8)
    assert card.layout().spacing() == 2


def test_margins_and_min_width_are_per_instance():
    card = Card(min_width=60, margins=(6, 4, 6, 4))
    margins = card.layout().contentsMargins()
    assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (6, 4, 6, 4)
    assert card.minimumWidth() == 60


def test_add_text_returns_a_label_in_the_layout():
    card = Card()
    label = card.add_text("42", "display")
    assert isinstance(label, QLabel)
    assert label.text() == "42"
    assert card.layout().indexOf(label) == 0


def test_add_text_resolves_the_point_size_from_the_type_scale():
    card = Card()
    label = card.add_text("42", "display")
    assert f"font-size: {TYPE_SCALE['display'].size_pt}pt" in label.styleSheet()


def test_extra_css_is_appended_not_substituted_for_the_role():
    card = Card()
    label = card.add_text("7", "label", css="background-color: #9E9E9E; border-radius: 8px;")
    assert f"font-size: {TYPE_SCALE['label'].size_pt}pt" in label.styleSheet()
    assert "border-radius: 8px;" in label.styleSheet()


def test_wrap_is_off_by_default_and_opt_in():
    card = Card()
    assert card.add_text("x").wordWrap() is False
    assert card.add_text("x", wrap=True).wordWrap() is True


def test_an_unknown_role_raises_rather_than_rendering_at_some_default():
    card = Card()
    with pytest.raises(KeyError):
        card.add_text("x", "headline")


# The three builders Card replaced. None of them touch `self`, so they run
# unbound -- no MainWindow needed. This is the safety net for the migration:
# it fails if a builder loses a row or stops handing back the live label.
def test_the_migrated_stat_card_keeps_its_live_value_label():
    from gui.ui_manager import UIManager

    card, value_lbl = UIManager._make_stat_card(None, "42", "Total orders")
    assert card.layout().count() == 2
    assert card.layout().itemAt(0).widget() is value_lbl
    assert value_lbl.text() == "42"


def test_the_migrated_courier_card_keeps_its_three_rows_in_order():
    from gui.ui_manager import UIManager

    card = UIManager._make_courier_card(None, "DHL", "12", "3")
    rows = [card.layout().itemAt(i).widget().text() for i in range(card.layout().count())]
    assert rows == ["12", "DHL", "3 repeated"]


def test_the_migrated_tag_card_defaults_its_badge_fill():
    from gui.ui_manager import UIManager

    card = UIManager._make_tag_card(None, "fragile", "7")
    badge, name = (card.layout().itemAt(i).widget() for i in range(2))
    assert "background-color: #9E9E9E" in badge.styleSheet()
    assert (badge.text(), name.text()) == ("7", "fragile")
