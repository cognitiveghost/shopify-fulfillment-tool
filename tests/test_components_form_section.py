"""Construction tests for the FormSection component. No window needed."""
import pytest
from PySide6.QtWidgets import QApplication, QFormLayout, QLabel, QLineEdit

from gui.components.form_section import FormSection
from gui.theme_manager import TYPE_SCALE


@pytest.fixture(scope="module", autouse=True)
def _app():
    yield QApplication.instance() or QApplication([])


def test_title_renders_at_the_label_role():
    section = FormSection("General Settings")
    title = section.layout().itemAt(0).widget()
    assert isinstance(title, QLabel)
    assert title.text() == "General Settings"
    assert f"font-size: {TYPE_SCALE['label'].size_pt}pt" in title.styleSheet()


def test_description_is_omitted_when_not_given():
    section = FormSection("General Settings")
    # title + the form body, nothing else
    assert section.layout().count() == 2


def test_description_wraps_and_renders_at_caption():
    section = FormSection("Courier Mappings", "Map provider names to codes.")
    desc = section.layout().itemAt(1).widget()
    assert desc.text() == "Map provider names to codes."
    assert desc.wordWrap() is True
    assert f"font-size: {TYPE_SCALE['caption'].size_pt}pt" in desc.styleSheet()


def test_add_row_builds_the_label_and_puts_both_in_the_form():
    section = FormSection("S")
    field = QLineEdit()
    label = section.add_row("Stock CSV Delimiter:", field)
    form = section.form
    assert isinstance(form, QFormLayout)
    assert form.rowCount() == 1
    assert form.itemAt(0, QFormLayout.LabelRole).widget() is label
    assert form.itemAt(0, QFormLayout.FieldRole).widget() is field
    assert label.text() == "Stock CSV Delimiter:"


def test_add_row_tooltip_reaches_the_label_too():
    """Hovering the label should explain the field. Today only the input
    carries the tooltip, so the explanation is invisible to anyone reading
    the form rather than clicking into it."""
    section = FormSection("S")
    field = QLineEdit()
    label = section.add_row("Low Stock Threshold:", field, tooltip="Alert below this.")
    assert label.toolTip() == "Alert below this."
    assert field.toolTip() == "Alert below this."


def test_add_row_leaves_an_existing_widget_tooltip_alone():
    section = FormSection("S")
    field = QLineEdit()
    field.setToolTip("set by the caller")
    section.add_row("X:", field)
    assert field.toolTip() == "set by the caller"


def test_add_widget_appends_below_the_form():
    section = FormSection("Courier Mappings")
    child = QLineEdit()
    section.add_widget(child)
    assert section.layout().indexOf(child) == section.layout().count() - 1
