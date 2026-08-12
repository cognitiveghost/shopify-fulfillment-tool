"""Icons are recoloured by substituting Lucide's currentColor token in the SVG
source before rasterizing, so these tests assert on actual rendered pixels --
a QIcon that is merely non-null proves nothing about whether it is visible
against the current theme."""
import pytest
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from gui.icons import icon
from gui.theme_manager import get_theme_manager


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


def _opaque_colors(qicon: QIcon, size: int = 32) -> set[str]:
    image = qicon.pixmap(size, size).toImage()
    # Fully-covered pixels only. Qt's antialiased edges are premultiplied, and
    # unpremultiplying drifts each RGB channel by +/-1 -- invisible for colours
    # whose channels are all 0 or 255, but the light theme's #1A1A1A is not one
    # of those, so a looser threshold makes the exact-colour asserts flaky.
    return {
        image.pixelColor(x, y).name()
        for y in range(image.height())
        for x in range(image.width())
        if image.pixelColor(x, y).alpha() == 255
    }


def test_returns_a_non_null_icon():
    assert not icon("package").isNull()


def test_unknown_name_raises_rather_than_returning_a_blank_icon():
    """A blank QIcon renders as empty space -- silently, and only on whichever
    screen uses it. Fail during development instead."""
    with pytest.raises(KeyError):
        icon("definitely-not-a-lucide-glyph")


def test_renders_in_an_explicitly_requested_color():
    assert _opaque_colors(icon("package", color="#FF0000")) == {"#ff0000"}


def test_defaults_to_the_current_theme_text_color():
    expected = get_theme_manager().get_current_theme().text.lower()
    assert _opaque_colors(icon("trash-2")) == {expected}


def test_color_follows_a_theme_toggle():
    """The whole point: a dark-grey icon on a dark background is invisible."""
    manager = get_theme_manager()
    original = manager.get_current_theme_name()
    try:
        manager.set_theme("light")
        light = _opaque_colors(icon("wrench"))
        manager.set_theme("dark")
        dark = _opaque_colors(icon("wrench"))
        assert light != dark
    finally:
        manager.set_theme(original)


def test_icon_carries_several_resolutions_for_hidpi():
    """Rendering one 16px pixmap and letting Qt upscale it is what makes icons
    blurry on the 125%/150%-scaled displays the warehouse PCs run."""
    sizes = {size.width() for size in icon("info").availableSizes()}
    assert {16, 24, 32, 48} <= sizes


def test_repeated_calls_reuse_the_cached_render():
    assert icon("copy") is icon("copy")


def test_every_long_lived_icon_name_resolves():
    """The five tab icons are the app's most-seen chrome, and with the three
    buttons they are the only icons that outlive a theme change -- everything
    in the context menu is rebuilt on each right-click."""
    from gui.ui_manager import UIManager

    assert UIManager._TAB_ICONS == (
        "clipboard-list", "table", "folder-open", "info", "wrench",
    )
    for name in UIManager._TAB_ICONS:
        assert not icon(name).isNull()
    for name in UIManager._BUTTON_ICONS.values():
        assert not icon(name).isNull()


def test_context_menu_no_longer_reaches_for_stock_icons():
    """Three separate menu actions shared SP_FileDialogDetailedView, which is
    why the app's icons carried no meaning. Each gets its own glyph now."""
    from pathlib import Path

    source = (
        Path(__file__).resolve().parent.parent / "gui" / "main_window_pyside.py"
    ).read_text(encoding="utf-8")
    assert "QStyle.SP_" not in source
    for name in ("refresh-cw", "tag", "tags", "circle-minus", "trash-2", "copy"):
        assert f'icon("{name}")' in source
