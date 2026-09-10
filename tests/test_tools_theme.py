"""The fold button sits on its card's plane, in both themes.

Rendered, not asserted from the stylesheet string: the failure this guards
against is the global `QWidget { background-color: surface }` rule painting a
surface patch on a surface_raised card, and only pixels show that.
"""

from types import SimpleNamespace

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtGui import QColor

from gui.theme_manager import get_theme_manager
from gui.tools_widget import ToolsWidget


@pytest.mark.parametrize("theme_name", ["light", "dark"])
def test_the_fold_button_sits_on_the_card_plane(theme_name, qapp, print_settings_store):
    manager = get_theme_manager()
    manager.set_theme(theme_name)
    manager.apply_theme()

    tools = ToolsWidget(SimpleNamespace(session_path=None))
    tools.resize(1310, 700)
    tools.show()
    qapp.processEvents()

    widget = tools.reference_labels_widget
    card = widget.parentWidget()
    button = widget.print_options.fold_button
    image = card.grab().toImage()

    # The right end of the row: past the summary text, inside the 1px border.
    point = button.mapTo(card, QPoint(button.width() - 8, button.height() // 2))
    expected = QColor(manager.get_current_theme().surface_raised).name()
    assert image.pixelColor(point).name() == expected


@pytest.mark.parametrize("theme_name", ["light", "dark"])
def test_the_card_is_raised_off_the_page(theme_name, qapp, print_settings_store):
    manager = get_theme_manager()
    manager.set_theme(theme_name)
    manager.apply_theme()

    tools = ToolsWidget(SimpleNamespace(session_path=None))
    tools.resize(1310, 700)
    tools.show()
    qapp.processEvents()

    card = tools.reference_labels_widget.parentWidget()
    image = card.grab().toImage()
    # Inside the card's 16px margin, clear of any child and of the rounded corner.
    assert (
        image.pixelColor(QPoint(8, card.height() // 2)).name()
        == QColor(manager.get_current_theme().surface_raised).name()
    )
