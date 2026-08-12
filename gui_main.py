"""Main entry point for the Shopify Fulfillment Tool application.

This script initializes the QApplication, creates the main window, and
starts the application's event loop. It also handles setting the platform
to 'offscreen' for testing or continuous integration (CI) environments.
"""
import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

__version__ = "1.9.9.1"

# Ensure the gui directory is on the path if running this as a script
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))


# WeasyPrint (via blabel, imported by shopify_tool.barcode_processor) needs
# GTK3's bundled Pango/Cairo/fontconfig on Windows. A frozen build ships its
# own GTK3 copy in gtk-dlls/ next to the exe; Windows won't find those DLLs
# (or, separately, fontconfig's own fonts.conf) unless we point at them
# explicitly first -- before MainWindow (and everything it imports) loads.
def configure_frozen_weasyprint_env() -> None:
    if getattr(sys, "frozen", False) and hasattr(os, "add_dll_directory"):
        os.add_dll_directory(str(Path(sys.executable).parent / "gtk-dlls"))


_WINDOWS_GTK3_FONTCONFIG_CANDIDATES = (
    r"C:\Program Files\GTK3-Runtime Win64\etc\fonts",
    r"C:\msys64\mingw64\etc\fonts",
)


def configure_windows_fontconfig_env() -> None:
    # Best-effort only: never overrides an already-set env var, and never
    # sets a path that doesn't actually contain a fonts.conf. When GTK3
    # isn't on PATH, fontconfig can't find its fonts.conf and prints
    # "Cannot load default config file" at startup -- labels still render
    # (this app's templates use a bundled @font-face TTF, not system font
    # lookup), so this only avoids the startup noise.
    if sys.platform != "win32" or os.environ.get("FONTCONFIG_PATH"):
        return
    candidates = list(_WINDOWS_GTK3_FONTCONFIG_CANDIDATES)
    if getattr(sys, "frozen", False):
        candidates.insert(0, str(Path(sys.executable).parent / "gtk-dlls" / "etc" / "fonts"))
    for candidate in candidates:
        if (Path(candidate) / "fonts.conf").is_file():
            os.environ["FONTCONFIG_PATH"] = candidate
            return


configure_frozen_weasyprint_env()
configure_windows_fontconfig_env()

from gui.icons import icon
from gui.main_window_pyside import MainWindow
from gui.theme_manager import get_theme_manager


def build_app_icon():
    """The window/taskbar icon. The app has never had one.

    Coloured with accent_blue rather than the theme's text colour, and never
    re-themed: this icon is drawn on the OS shell's own surface, whose
    background has nothing to do with which theme the app is running.
    """
    return icon("package", color=get_theme_manager().get_current_theme().accent_blue)


def main():
    """Sets up and runs the Qt application.

    Initializes the QApplication, instantiates the `MainWindow`, and shows it.
    It checks for specific environment conditions (like running under pytest
    or in a CI environment) to set the Qt platform to 'offscreen', which
    prevents a GUI from being shown during automated testing.
    """
    # Set platform to offscreen for CI/testing environments
    if "pytest" in sys.modules or os.environ.get("CI"):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        print("Running in offscreen mode.")

    app = QApplication(sys.argv)

    # Initialize and apply theme
    theme_manager = get_theme_manager()
    theme_manager.apply_theme()
    app.setWindowIcon(build_app_icon())

    window = MainWindow()

    if QApplication.platformName() != "offscreen":
        window.show()
        window.raise_()
        window.activateWindow()
        sys.exit(app.exec())
    else:
        # In offscreen mode, the window is created but not shown.
        # The app doesn't enter the event loop, allowing tests/CI to exit.
        print("Offscreen application initialized successfully.")


if __name__ == "__main__":
    # Standard entry point for a Python script.
    main()
