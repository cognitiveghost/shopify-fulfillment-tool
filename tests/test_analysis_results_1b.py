"""Widget-level tests for Analysis Results 1b (spec §10 tests 9-11)."""

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def main_window(app):
    from gui.main_window_pyside import MainWindow

    window = MainWindow()
    yield window
    window.close()


def test_the_workaround_code_is_gone():
    """These existed only to fake order-level behaviour over a line table."""
    import importlib

    for module in ("gui.checkbox_delegate", "gui.order_group_delegate"):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(module)


def test_no_bulk_mode_and_no_tag_panel_toggle(app, main_window):
    assert not hasattr(main_window, "toggle_bulk_mode")
    assert not hasattr(main_window, "toggle_tag_panel")
    assert not hasattr(main_window, "toggle_bulk_mode_btn")
    assert not hasattr(main_window, "toggle_tags_panel_btn")


# The lot batch/expiry search this file used to pin moved with the search into
# the results document: tests/test_results_document.py.
