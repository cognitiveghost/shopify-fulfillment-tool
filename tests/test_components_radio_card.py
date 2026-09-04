"""RadioCard: a radio button that says what choosing it does.

The combo it replaces made a supervisor read two words and guess what
"multi-item-first" meant.
"""

from PySide6.QtWidgets import QButtonGroup

from gui.components import RadioCard


def test_radio_card_keeps_its_strings(qapp):
    card = RadioCard("Multi-item first", "Fills orders that can go out whole.")
    assert card.title_text == "Multi-item first"
    assert card.description_text == "Fills orders that can go out whole."


def test_radio_card_is_a_radio_button(qapp):
    a = RadioCard("Multi-item first", "one")
    b = RadioCard("Oldest first", "two")
    group = QButtonGroup()
    group.addButton(a)
    group.addButton(b)

    a.setChecked(True)
    assert a.isChecked()
    b.setChecked(True)
    assert b.isChecked()
    assert not a.isChecked()


def test_radio_card_description_wraps(qapp):
    card = RadioCard("Oldest first", "x " * 60)
    assert card._description.wordWrap()


def test_radio_card_is_taller_than_a_bare_radio(qapp):
    card = RadioCard("Oldest first", "A description that occupies its own line.")
    assert card.sizeHint().height() > 30
