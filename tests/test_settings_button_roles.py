"""Inside the Hub, Save is the only accent-filled button on screen."""
from PySide6.QtWidgets import QPushButton


def test_the_footer_marks_save_primary_and_cancel_secondary(window):
    assert window.save_button.property("role") == "primary"
    assert window.cancel_button.property("role") == "secondary"


def test_no_page_leaves_an_unmarked_button_competing_with_save(window):
    """An unmarked button still renders accent-blue, so it would read as a
    second primary action. Inside the Hub every in-page button is secondary."""
    unmarked = []
    # The stack's widgets, not _pages: three pages are drafts with no widget.
    for index in range(window.tab_widget.count()):
        page = window.tab_widget.widget(index)
        for button in page.findChildren(QPushButton):
            if button.property("role") is None:
                unmarked.append(f"{type(page).__name__}: {button.text()!r}")
    assert unmarked == [], "unmarked buttons inside the Hub: " + ", ".join(unmarked)
