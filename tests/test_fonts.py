"""Font loading must never raise. Production is Windows-only, where Segoe UI
always exists, so an unreadable bundled TTF should degrade to Segoe UI -- not
stop a warehouse PC from starting the app."""
import pytest
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication

from gui import fonts


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def clear_font_cache():
    """load_bundled_fonts() is lru_cached; tests that monkeypatch FONTS_DIR
    would otherwise see a neighbour's cached result."""
    fonts.load_bundled_fonts.cache_clear()
    yield
    fonts.load_bundled_fonts.cache_clear()


def test_returns_the_inter_family_name():
    assert fonts.load_bundled_fonts() == "Inter"


def test_family_is_actually_registered_with_qt():
    fonts.load_bundled_fonts()
    assert "Inter" in QFontDatabase.families()


def test_is_idempotent():
    assert fonts.load_bundled_fonts() == fonts.load_bundled_fonts() == "Inter"


def test_returns_none_without_raising_when_assets_are_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(fonts, "FONTS_DIR", tmp_path)
    assert fonts.load_bundled_fonts() is None


def test_returns_none_without_raising_when_a_face_is_corrupt(monkeypatch, tmp_path):
    for name in ("Inter-Regular.ttf", "Inter-Bold.ttf"):
        (tmp_path / name).write_bytes(b"not a font")
    monkeypatch.setattr(fonts, "FONTS_DIR", tmp_path)
    assert fonts.load_bundled_fonts() is None


def test_theme_tokens_lead_with_inter_and_keep_segoe_as_fallback():
    """Keeping the original family on the tail is free insurance: a machine
    where Inter fails to register falls back to Segoe UI rather than to Qt's
    generic default."""
    from gui import theme_manager

    theme_manager._themed_tokens.cache_clear()
    family = theme_manager.get_theme_manager().get_current_theme().font_family
    assert family == "'Inter', Segoe UI, sans-serif"


def test_theme_tokens_are_untouched_when_fonts_are_unavailable(monkeypatch, tmp_path):
    from gui import theme_manager

    monkeypatch.setattr(fonts, "FONTS_DIR", tmp_path)
    fonts.load_bundled_fonts.cache_clear()
    theme_manager._themed_tokens.cache_clear()
    try:
        family = theme_manager.get_theme_manager().get_current_theme().font_family
        assert family == "Segoe UI, sans-serif"
    finally:
        fonts.load_bundled_fonts.cache_clear()
        theme_manager._themed_tokens.cache_clear()


def test_tokens_are_memoized_not_rebuilt_per_call():
    """get_current_theme() runs on ~180 call sites; dataclasses.replace()
    allocates a fresh ThemeTokens every time without this."""
    from gui import theme_manager

    theme_manager._themed_tokens.cache_clear()
    manager = theme_manager.get_theme_manager()
    assert manager.get_current_theme() is manager.get_current_theme()
