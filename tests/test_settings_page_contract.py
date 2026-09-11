from PySide6.QtWidgets import QApplication

from gui.settings.base import SettingsPage


def test_settings_page_defaults_are_inert():
    """A page that owns no config contributes nothing and blocks nothing."""
    QApplication.instance() or QApplication([])
    page = SettingsPage()
    assert page.collect() == {}
    assert page.validate() == (True, [])


class _OneValuePage(SettingsPage):
    def __init__(self):
        super().__init__()
        self.value = 1

    def collect(self):
        return {"key": self.value}


def test_a_page_is_never_unsaved_before_mark_clean():
    QApplication.instance() or QApplication([])
    page = _OneValuePage()
    page.value = 2
    assert page.is_dirty() is False


def test_an_edit_reads_unsaved_and_reverting_it_reads_clean():
    QApplication.instance() or QApplication([])
    page = _OneValuePage()
    page.mark_clean()
    page.value = 2
    assert page.is_dirty() is True
    page.value = 1
    assert page.is_dirty() is False


def test_a_collect_that_raises_reads_unsaved(monkeypatch):
    QApplication.instance() or QApplication([])
    page = _OneValuePage()
    page.mark_clean()

    def boom():
        raise ValueError("half-typed")

    monkeypatch.setattr(page, "collect", boom)
    assert page.is_dirty() is True
