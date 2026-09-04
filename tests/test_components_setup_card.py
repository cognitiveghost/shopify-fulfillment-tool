"""Card and FormSection gain the two things the setup card needs.

Card could only take centred text; FormSection could not pin its label
column, which is what the 208px gutter in Bundle 5's setup card is.
"""

from PySide6.QtWidgets import QLabel, QLineEdit

from gui.components import Card, FormSection


def test_card_takes_an_arbitrary_widget(qapp):
    card = Card()
    child = QLabel("not centred")
    card.add_widget(child)
    assert child.parent() is card
    assert card.layout().indexOf(child) != -1


def test_form_section_pins_its_label_column(qapp):
    section = FormSection("", label_width=208)
    label = section.add_row("Session name", QLineEdit())
    assert label.width() == 208
    assert label.minimumWidth() == 208
    assert label.maximumWidth() == 208


def test_form_section_without_label_width_leaves_labels_free(qapp):
    section = FormSection("")
    label = section.add_row("Session name", QLineEdit())
    assert label.maximumWidth() > 208
