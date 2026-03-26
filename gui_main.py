"""Main entry point for the Shopify Fulfillment Tool application.

This script initializes the QApplication, creates the main window, and
starts the application's event loop. It also handles setting the platform
to 'offscreen' for testing or continuous integration (CI) environments.
"""
import sys
import os
from PySide6.QtWidgets import QApplication

__version__ = "1.8.9.6"

# Ensure the gui directory is on the path if running this as a script
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from gui.main_window_pyside import MainWindow
from gui.theme_manager import get_theme_manager


def main():
    """Sets up and runs the Qt application.

    Initializes the QApplication, instantiates the `MainWindow`, and shows it.
    It checks for specific environment conditions (like running under pytest
    or in a CI environment) to set the Qt platform to 'offscreen', which
    prevents a GUI from being shown during automated testing.
    """
    # Set platform to offscreen for CI/testing environments
    if "pytest" in sys.modules or os.environ.get("CI"):
        QApplication.setPlatform("offscreen")
        print("Running in offscreen mode.")

    app = QApplication(sys.argv)

    # Initialize and apply theme
    theme_manager = get_theme_manager()
    theme_manager.apply_theme()

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
