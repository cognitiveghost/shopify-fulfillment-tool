"""Regression check for the Reports tab / SKU Labels feature removal.

Confirmed unused in the current workflow (Todoist backlog task), removed
for maintainability: the global Reports tab (gui.client_reports_widget),
the SKU Labels tool sub-tab (gui.sku_label_widget), the SKU Label Printing
settings tab, and the sku_label_manager backend. This just confirms the
surrounding UI still constructs cleanly with the feature gone.
"""
import inspect
import sys

import pytest
from PySide6.QtWidgets import QApplication, QMainWindow

import gui.tools_widget
from gui.ui_manager import UIManager


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


def test_tools_widget_no_longer_wires_sku_labels_subtab(qapp):
    # Checking the module's source avoids building the page while still
    # failing if the SKU Labels sub-tab wiring is ever reintroduced.
    source = inspect.getsource(gui.tools_widget)
    assert "SKULabelWidget" not in source
    assert "SKU Labels" not in source


def test_ui_manager_has_no_reports_tab_builder(qapp):
    window = QMainWindow()
    ui = UIManager(window)

    assert not hasattr(ui, "_create_tab6_reports")
    assert "_create_tab6_reports" not in inspect.getsource(ui._create_tabs)


def test_sku_label_manager_module_is_gone():
    with pytest.raises(ModuleNotFoundError):
        import shopify_tool.sku_label_manager  # noqa: F401


def test_client_reports_widget_module_is_gone():
    with pytest.raises(ModuleNotFoundError):
        import gui.client_reports_widget  # noqa: F401
