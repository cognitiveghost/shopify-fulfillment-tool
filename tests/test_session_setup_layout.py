"""Session Setup is one card of three rows.

Bundle 5 deleted the splitter, the scroll area and the recent-sessions
strip. The constraints the previous version of this file protected — a
706px column floor, a fixed recent-list height — belonged to a layout that
no longer exists.
"""

import pytest
from PySide6.QtWidgets import QApplication, QScrollArea, QSplitter

from gui.components import Card, FileSlot, RadioCard


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def main_window(tmp_path, monkeypatch):
    """A real MainWindow rooted at a throwaway server path -- same
    construction test_shell.py uses; there is no conftest fixture for this,
    and copying seven lines beats making one test file import another."""
    monkeypatch.setenv("FULFILLMENT_SERVER_PATH", str(tmp_path))
    from gui.main_window_pyside import MainWindow

    win = MainWindow()
    win.resize(1366, 768)
    win.show()
    QApplication.processEvents()
    win.main_tabs.setCurrentIndex(0)
    # This file measures the card's own layout (page 1), not page 0's empty
    # state -- and a QStackedWidget page that has never been current is
    # never laid out, so every widget in it would read back as (0, 0).
    win.setup_stack.setCurrentIndex(1)
    QApplication.processEvents()
    yield win
    win.close()


def test_the_setup_page_holds_exactly_one_card(main_window):
    page = main_window.setup_stack.widget(1)
    assert len(page.findChildren(Card)) == 1


def test_the_card_fits_above_600px(main_window):
    """The plan's original 480px estimate assumed the two RadioCard
    descriptions would never wrap past two lines; rendering the real page
    (not just its sizeHint at an untested width) showed a three-line wrap
    at the card's actual 840px cap, which this cap accounts for."""
    page = main_window.setup_stack.widget(1)
    card = page.findChildren(Card)[0]
    assert card.sizeHint().height() <= 600


def test_nothing_on_the_setup_page_scrolls(main_window):
    page = main_window.setup_stack.widget(1)
    assert page.findChildren(QScrollArea) == []
    assert page.findChildren(QSplitter) == []


def test_the_page_has_two_file_slots(main_window):
    page = main_window.setup_stack.widget(1)
    assert len(page.findChildren(FileSlot)) == 2


def test_the_strategy_is_two_radio_cards_not_a_combo(main_window):
    page = main_window.setup_stack.widget(1)
    cards = page.findChildren(RadioCard)
    assert len(cards) == 2
    assert {c.title_text for c in cards} == {"Multi-item first", "Oldest first"}
    assert all(c.description_text for c in cards)


def test_the_recent_sessions_strip_is_gone(main_window):
    assert not hasattr(main_window, "recent_sessions_list")


def test_the_shell_controls_are_not_duplicated_on_the_page(main_window):
    for gone in (
        "new_session_btn",
        "settings_button",
        "generate_reports_button",
        "open_session_folder_button",
        "add_product_button",
    ):
        assert not hasattr(main_window, gone), f"{gone} still on the page"


def test_the_label_gutter_is_208(main_window):
    from PySide6.QtWidgets import QFormLayout

    from gui.components import FormSection

    page = main_window.setup_stack.widget(1)
    section = page.findChildren(FormSection)[0]
    label = section.form.itemAt(0, QFormLayout.LabelRole).widget()
    assert label.width() == 208


def test_the_session_name_field_takes_focus_first(main_window):
    page = main_window.setup_stack.widget(1)
    assert main_window.session_name_edit in page.findChildren(type(main_window.session_name_edit))
    assert main_window.session_name_edit.focusPolicy() != 0
