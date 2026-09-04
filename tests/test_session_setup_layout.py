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


def test_the_card_fits_above_530px(main_window):
    """The spec's 480px estimate assumed the two RadioCard descriptions
    would never wrap past two lines; rendering the real page (not just its
    sizeHint at an untested width) showed a three-line wrap at the card's
    actual 840px cap. The requirement behind the number -- no scrolling on
    the 692px page at 1366x768 -- still holds at the measured 515px. Kept
    within 15px of that so it still catches drift rather than absorbing it.
    """
    page = main_window.setup_stack.widget(1)
    card = page.findChildren(Card)[0]
    assert card.sizeHint().height() <= 530


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


def test_there_is_no_session_name_row(main_window):
    """PR #317 review picked dropping the row over wiring an inert field
    sight unseen (design call 1, option (c))."""
    assert not hasattr(main_window, "session_name_edit")


def test_orders_file_is_the_first_row_of_the_card(main_window):
    from PySide6.QtWidgets import QFormLayout

    from gui.components import FormSection

    page = main_window.setup_stack.widget(1)
    section = page.findChildren(FormSection)[0]
    assert section.form.itemAt(0, QFormLayout.FieldRole).widget() is (
        main_window.orders_slot
    )


def test_inventory_memory_is_its_own_row_not_folded_into_stock_file(main_window):
    """PR #317 review: the checkbox should be a labelled option on the card,
    not a second widget squeezed into the Stock file row's field column."""
    from PySide6.QtWidgets import QCheckBox, QFormLayout

    from gui.components import FormSection

    page = main_window.setup_stack.widget(1)
    section = page.findChildren(FormSection)[0]
    labels = [
        section.form.itemAt(row, QFormLayout.LabelRole).widget().text()
        for row in range(section.form.rowCount())
    ]
    assert "Inventory memory" in labels
    row = labels.index("Inventory memory")
    field = section.form.itemAt(row, QFormLayout.FieldRole).widget()
    assert field is main_window.inventory_memory_checkbox
    assert isinstance(field, QCheckBox)


def test_the_gutter_degrades_below_1024_and_flattens_below_840(qapp):
    """Spec §8: 208 above 1024px, 96 down to the card's 840px cap, then 0
    with labels stacked above their fields. Unreachable on the 1366px
    Windows floor, but this page also runs on Linux, in dev and in tests --
    tested standalone rather than through the full shell, where the page's
    width is the stack's, not something a test can dial to an exact number.
    """
    from PySide6.QtWidgets import QFormLayout, QLineEdit

    from gui.components import FormSection
    from gui.ui_manager import _SetupPage

    section = FormSection("", label_width=208)
    section.add_row("Orders file", QLineEdit())
    page = _SetupPage(section)
    page.show()
    label = section.form.itemAt(0, QFormLayout.LabelRole).widget()

    page.resize(1200, 400)
    QApplication.processEvents()
    assert label.width() == 208

    page.resize(900, 400)
    QApplication.processEvents()
    assert label.width() == 96

    page.resize(700, 400)
    QApplication.processEvents()
    assert label.maximumWidth() > 208
    assert section.form.rowWrapPolicy() == QFormLayout.WrapAllRows

    page.close()
