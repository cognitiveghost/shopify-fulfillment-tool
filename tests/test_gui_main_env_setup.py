"""Regression test for gui_main.py's frozen-Windows WeasyPrint/fontconfig
runtime setup -- no test previously covered DLL-directory selection or
FONTCONFIG_PATH resolution (CodeRabbit review on PR #259).
"""
import os
import sys
from pathlib import Path

import gui_main


def test_frozen_weasyprint_env_adds_gtk_dlls_dir(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "/fake/App.exe", raising=False)
    calls = []
    monkeypatch.setattr(os, "add_dll_directory", lambda p: calls.append(p), raising=False)

    gui_main.configure_frozen_weasyprint_env()

    assert calls == [str(Path("/fake/App.exe").parent / "gtk-dlls")]


def test_frozen_weasyprint_env_noop_when_not_frozen(monkeypatch):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    calls = []
    monkeypatch.setattr(os, "add_dll_directory", lambda p: calls.append(p), raising=False)

    gui_main.configure_frozen_weasyprint_env()

    assert calls == []


def test_fontconfig_env_prefers_bundled_frozen_candidate(monkeypatch, tmp_path):
    bundled = tmp_path / "gtk-dlls" / "etc" / "fonts"
    bundled.mkdir(parents=True)
    (bundled / "fonts.conf").write_text("")
    # A valid fallback candidate too, so picking `bundled` actually proves
    # precedence rather than just being the only valid option available.
    fallback = tmp_path / "fallback"
    fallback.mkdir()
    (fallback / "fonts.conf").write_text("")

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "App.exe"), raising=False)
    monkeypatch.setattr(gui_main, "_WINDOWS_GTK3_FONTCONFIG_CANDIDATES", (str(fallback),))
    monkeypatch.delenv("FONTCONFIG_PATH", raising=False)

    gui_main.configure_windows_fontconfig_env()

    assert os.environ["FONTCONFIG_PATH"] == str(bundled)


def test_fontconfig_env_skips_candidates_missing_fonts_conf(monkeypatch, tmp_path):
    valid = tmp_path / "valid"
    valid.mkdir()
    (valid / "fonts.conf").write_text("")

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(
        gui_main,
        "_WINDOWS_GTK3_FONTCONFIG_CANDIDATES",
        (str(tmp_path / "nowhere"), str(valid)),
    )
    monkeypatch.delenv("FONTCONFIG_PATH", raising=False)

    gui_main.configure_windows_fontconfig_env()

    assert os.environ["FONTCONFIG_PATH"] == str(valid)


def test_fontconfig_env_never_overrides_existing_value(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("FONTCONFIG_PATH", "/already/set")

    gui_main.configure_windows_fontconfig_env()

    assert os.environ["FONTCONFIG_PATH"] == "/already/set"


def test_fontconfig_env_noop_off_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("FONTCONFIG_PATH", raising=False)

    gui_main.configure_windows_fontconfig_env()

    assert "FONTCONFIG_PATH" not in os.environ


def test_app_icon_is_built_in_a_fixed_accent_color():
    """The taskbar icon sits on the OS shell's surface, which has nothing to
    do with this app's theme -- so it is deliberately not re-themed."""
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])

    import gui_main
    from gui.theme_manager import get_theme_manager

    app_icon = gui_main.build_app_icon()
    assert not app_icon.isNull()

    image = app_icon.pixmap(48, 48).toImage()
    # alpha == 255 (fully covered), not just "mostly opaque": Qt's
    # antialiased edge pixels are alpha-blended against transparent and
    # unpremultiply with a +/-1 per-channel rounding drift for any color
    # whose channels aren't all 0 or 255 -- accent_blue (#007ACC) is exactly
    # such a color, so a >200 threshold picks up near-misses like #0079cc.
    opaque = {
        image.pixelColor(x, y).name()
        for y in range(image.height())
        for x in range(image.width())
        if image.pixelColor(x, y).alpha() == 255
    }
    assert opaque == {get_theme_manager().get_current_theme().accent_blue.lower()}
