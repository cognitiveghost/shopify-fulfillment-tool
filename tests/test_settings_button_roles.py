"""Inside the Hub, Save is the only accent-filled button on screen."""
from PySide6.QtWidgets import QDialogButtonBox, QPushButton


def test_the_footer_marks_save_primary_and_cancel_secondary(window):
    assert window.save_button.property("role") == "primary"
    cancel = window.save_button.parent().button(QDialogButtonBox.Cancel)
    assert cancel.property("role") == "secondary"


def test_no_page_leaves_an_unmarked_button_competing_with_save(window):
    """An unmarked button still renders accent-blue, so it would read as a
    second primary action. Inside the Hub every in-page button is secondary."""
    unmarked = []
    for page in window._pages:
        for button in page.findChildren(QPushButton):
            if button.property("role") is None:
                unmarked.append(f"{type(page).__name__}: {button.text()!r}")
    assert unmarked == [], "unmarked buttons inside the Hub: " + ", ".join(unmarked)
