"""9.25: a problem shown where it happened.

Spec: docs/superpowers/specs/2026-09-10-phase9-bundle9-message-boxes-design.md §4.4
"""

from PySide6.QtWidgets import QWidget

from gui.components.inline_message import InlineMessage
from shared.theme import current_tokens


def test_it_is_hidden_until_there_is_something_to_say(qapp):
    parent = QWidget()
    assert InlineMessage(parent).isHidden()


def test_show_message_shows_the_text(qapp):
    parent = QWidget()
    message = InlineMessage(parent)
    message.show_message("Enter an order number.")
    assert not message.isHidden()
    assert message.text() == "Enter an order number."


def test_clear_hides_it_again(qapp):
    parent = QWidget()
    message = InlineMessage(parent)
    message.show_message("Enter an order number.")
    message.clear()
    assert message.isHidden()
    assert message.text() == ""


def test_it_is_drawn_in_the_danger_colour(qapp):
    parent = QWidget()
    assert current_tokens().status_danger in InlineMessage(parent).styleSheet()
