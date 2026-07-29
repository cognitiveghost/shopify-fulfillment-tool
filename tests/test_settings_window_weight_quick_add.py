"""Regression/behavior test for the Weight tab's Quick Add panel
(gui.settings_window_pyside.SettingsWindow._weight_quick_add_product).

Exercises the bound methods directly against a bare QWidget standing in for
SettingsWindow, rather than constructing the real SettingsWindow -- its full
__init__ builds every settings tab and hangs under the offscreen QPA
platform (no way to dismiss real dialogs headlessly), which this test has
no need to go through just to check the Quick Add row-insertion logic.
"""
import pytest
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QLineEdit,
    QTableWidget,
)

from gui.settings_window_pyside import SettingsWindow


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def sw(qapp):
    """A real SettingsWindow instance with only QDialog.__init__ run (not
    SettingsWindow.__init__, which builds every settings tab and hangs under
    the offscreen QPA platform), carrying just the attributes the Quick Add
    methods touch. Using the real class (not a bare QWidget) keeps `self.` calls
    inside those methods resolving to the real bound methods."""
    obj = SettingsWindow.__new__(SettingsWindow)
    QDialog.__init__(obj)
    obj.weight_products_table = QTableWidget(0, 7)
    obj.weight_divisor_spin = QDoubleSpinBox()
    obj.weight_divisor_spin.setValue(6000)
    obj.weight_quick_sku = QLineEdit()
    obj.weight_quick_name = QLineEdit()
    obj.weight_quick_l = QDoubleSpinBox()
    obj.weight_quick_w = QDoubleSpinBox()
    obj.weight_quick_h = QDoubleSpinBox()
    obj.weight_quick_no_pkg = QCheckBox()
    return obj


def test_quick_add_appends_a_row_and_resets_the_form(sw):
    sw.weight_quick_sku.setText("NEWSKU")
    sw.weight_quick_name.setText("Test product")
    sw.weight_quick_l.setValue(5)
    sw.weight_quick_w.setValue(6)
    sw.weight_quick_h.setValue(7)
    sw.weight_quick_no_pkg.setChecked(True)

    SettingsWindow._weight_quick_add_product(sw)

    assert sw.weight_products_table.rowCount() == 1
    assert sw.weight_products_table.item(0, 0).text() == "NEWSKU"
    assert sw.weight_products_table.item(0, 1).text() == "Test product"
    assert sw.weight_products_table.item(0, 2).text() == "5.0"
    assert sw.weight_products_table.cellWidget(0, 6).findChild(QCheckBox).isChecked()
    # form resets for the next entry
    assert sw.weight_quick_sku.text() == ""
    assert sw.weight_quick_l.value() == 0


def test_quick_add_rejects_blank_sku(sw):
    SettingsWindow._weight_quick_add_product(sw)
    assert sw.weight_products_table.rowCount() == 0


def test_quick_add_rejects_duplicate_sku_without_adding_a_row(sw, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)

    sw.weight_quick_sku.setText("DUPE")
    SettingsWindow._weight_quick_add_product(sw)
    assert sw.weight_products_table.rowCount() == 1

    sw.weight_quick_sku.setText("DUPE")
    SettingsWindow._weight_quick_add_product(sw)
    assert sw.weight_products_table.rowCount() == 1
