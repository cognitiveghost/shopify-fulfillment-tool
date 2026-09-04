"""QtWebEngine must stay installed for the web tier (ADR 0001).

It arrives via PySide6-Addons, which the PySide6 metapackage depends on --
nothing names it directly, so a well-meaning switch to PySide6-Essentials
would remove it silently and only break the frozen Windows build.

find_spec, not import: importing loads libQt6WebEngineCore, which needs NSS
and friends that the Ubuntu CI image does not install. Packaging is what is
being guarded here, not runtime.
"""
import importlib.util


def test_qtwebengine_widgets_is_installed():
    assert importlib.util.find_spec("PySide6.QtWebEngineWidgets") is not None, (
        "PySide6.QtWebEngineWidgets is missing -- check that requirements.txt "
        "still installs the PySide6 metapackage and not PySide6-Essentials."
    )
