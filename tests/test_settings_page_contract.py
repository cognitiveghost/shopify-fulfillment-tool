from PySide6.QtWidgets import QApplication

from gui.settings.base import SettingsPage


def test_settings_page_defaults_are_inert():
    """A page that owns no config contributes nothing and blocks nothing."""
    QApplication.instance() or QApplication([])
    page = SettingsPage()
    assert page.collect() == {}
    assert page.validate() == (True, [])
