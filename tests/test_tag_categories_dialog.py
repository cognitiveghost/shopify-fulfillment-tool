"""Tests for Tag Categories Dialog."""

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox, QInputDialog, QLineEdit
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from unittest.mock import Mock, patch, MagicMock

from gui.tag_categories_dialog import TagCategoriesDialog


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def tag_categories_v2():
    """V2 format tag categories."""
    return {
        "version": 2,
        "categories": {
            "packaging": {
                "label": "Пакетаж",
                "color": "#4CAF50",
                "order": 1,
                "tags": ["SMALL_BAG", "BOX"],
                "sku_writeoff": {
                    "enabled": False,
                    "mappings": {}
                }
            },
            "priority": {
                "label": "Пріоритет",
                "color": "#FF9800",
                "order": 2,
                "tags": ["URGENT"],
                "sku_writeoff": {
                    "enabled": False,
                    "mappings": {}
                }
            }
        }
    }


@pytest.fixture
def dialog(qapp, tag_categories_v2):
    """Create dialog instance."""
    dlg = TagCategoriesDialog(tag_categories_v2)
    yield dlg
    dlg.close()


# ============================================================================
# Basic UI Tests
# ============================================================================


def test_dialog_initializes(dialog):
    """Test dialog initializes correctly."""
    assert dialog.windowTitle() == "Tag Categories Management"
    assert dialog.isModal() is True
    assert dialog.working_categories["version"] == 2


def test_categories_list_populated(dialog):
    """Test categories list is populated on init."""
    assert dialog.categories_list.count() == 2

    # Check first item
    item = dialog.categories_list.item(0)
    assert item.text() == "Пакетаж"
    assert item.data(Qt.UserRole) == "packaging"


def test_editor_initially_disabled(dialog):
    """Test editor is disabled when no category selected."""
    assert dialog.category_id_input.isEnabled() is False
    assert dialog.label_input.isEnabled() is False
    assert dialog.add_tag_btn.isEnabled() is False


# ============================================================================
# Category Selection Tests
# ============================================================================


def test_select_category_loads_editor(dialog):
    """Test selecting category loads it into editor."""
    # Select first category
    dialog.categories_list.setCurrentRow(0)

    assert dialog.current_category_id == "packaging"
    assert dialog.category_id_input.text() == "packaging"
    assert dialog.label_input.text() == "Пакетаж"
    assert dialog.current_color == "#4CAF50"
    assert dialog.order_spin.value() == 1
    assert dialog.tags_list.count() == 2

    # Editor should be enabled
    assert dialog.label_input.isEnabled() is True


def test_select_different_categories(dialog):
    """Test switching between categories."""
    # Select packaging
    dialog.categories_list.setCurrentRow(0)
    assert dialog.current_category_id == "packaging"
    assert dialog.tags_list.count() == 2

    # Select priority
    dialog.categories_list.setCurrentRow(1)
    assert dialog.current_category_id == "priority"
    assert dialog.label_input.text() == "Пріоритет"
    assert dialog.tags_list.count() == 1


# ============================================================================
# Category Editing Tests
# ============================================================================


def test_edit_category_label(dialog):
    """Test editing category label."""
    dialog.categories_list.setCurrentRow(0)

    # Change label
    dialog.label_input.setText("New Label")

    assert dialog.modified is True

    # Check working copy updated
    categories = dialog.working_categories["categories"]
    assert categories["packaging"]["label"] == "New Label"


def test_edit_category_order(dialog):
    """Test editing category order."""
    dialog.categories_list.setCurrentRow(0)

    # Change order
    dialog.order_spin.setValue(5)

    assert dialog.modified is True

    # Check working copy updated
    categories = dialog.working_categories["categories"]
    assert categories["packaging"]["order"] == 5


def test_edit_category_color(dialog):
    """Test editing category color."""
    dialog.categories_list.setCurrentRow(0)

    # Mock color dialog to return red
    with patch('gui.tag_categories_dialog.QColorDialog.getColor') as mock_color:
        from PySide6.QtGui import QColor
        mock_color.return_value = QColor("#FF0000")

        # Click color button
        dialog.color_button.click()

    assert dialog.current_color.upper() == "#FF0000"  # QColor.name() returns lowercase
    assert dialog.modified is True


# ============================================================================
# Tags Management Tests
# ============================================================================


def test_add_tag_to_category(dialog, monkeypatch):
    """Test adding tag to category."""
    dialog.categories_list.setCurrentRow(0)

    initial_count = dialog.tags_list.count()

    # Mock input dialog
    mock_getText = MagicMock(return_value=("NEW_TAG", True))
    monkeypatch.setattr('PySide6.QtWidgets.QInputDialog.getText', mock_getText)

    # Click add tag button
    dialog._on_add_tag()

    assert dialog.tags_list.count() == initial_count + 1
    assert dialog.modified is True

    # Check tag added to working copy
    categories = dialog.working_categories["categories"]
    assert "NEW_TAG" in categories["packaging"]["tags"]


def test_add_duplicate_tag_warning(dialog, monkeypatch):
    """Test warning when adding duplicate tag in same category."""
    dialog.categories_list.setCurrentRow(0)

    # Mock dialogs
    mock_getText = MagicMock(return_value=("BOX", True))  # Already exists
    mock_warning = MagicMock()

    monkeypatch.setattr('PySide6.QtWidgets.QInputDialog.getText', mock_getText)
    monkeypatch.setattr('PySide6.QtWidgets.QMessageBox.warning', mock_warning)

    # Try to add existing tag
    dialog._on_add_tag()

    # Should show warning
    mock_warning.assert_called_once()
    assert "already exists" in str(mock_warning.call_args).lower()


def test_add_tag_duplicate_across_categories_warning(dialog, monkeypatch):
    """Test warning when adding tag that exists in another category."""
    dialog.categories_list.setCurrentRow(1)  # Select priority

    # Mock dialogs
    mock_getText = MagicMock(return_value=("BOX", True))  # Exists in packaging
    mock_warning = MagicMock()

    monkeypatch.setattr('PySide6.QtWidgets.QInputDialog.getText', mock_getText)
    monkeypatch.setattr('PySide6.QtWidgets.QMessageBox.warning', mock_warning)

    # Try to add tag from packaging category
    dialog._on_add_tag()

    # Should show warning
    mock_warning.assert_called_once()
    assert "another category" in str(mock_warning.call_args).lower()


def test_remove_tag_from_category(dialog):
    """Test removing tag from category."""
    dialog.categories_list.setCurrentRow(0)

    initial_count = dialog.tags_list.count()

    # Select first tag
    dialog.tags_list.setCurrentRow(0)

    # Click remove button
    dialog.remove_tag_btn.click()

    assert dialog.tags_list.count() == initial_count - 1
    assert dialog.modified is True


def test_remove_tag_button_disabled_when_no_selection(dialog):
    """Test remove tag button is disabled when no tag selected."""
    dialog.categories_list.setCurrentRow(0)

    assert dialog.remove_tag_btn.isEnabled() is False

    # Select a tag
    dialog.tags_list.setCurrentRow(0)

    assert dialog.remove_tag_btn.isEnabled() is True


# ============================================================================
# New Category Tests
# ============================================================================


def test_create_new_category(dialog, monkeypatch):
    """Test creating new category."""
    initial_count = dialog.categories_list.count()

    # Mock input dialog
    mock_getText = MagicMock(return_value=("test_category", True))
    monkeypatch.setattr('PySide6.QtWidgets.QInputDialog.getText', mock_getText)

    # Create new category
    dialog._on_new_category()

    assert dialog.categories_list.count() == initial_count + 1
    assert dialog.modified is True

    # Check category added to working copy
    categories = dialog.working_categories["categories"]
    assert "test_category" in categories
    assert categories["test_category"]["label"] == "Test Category"


def test_create_new_category_invalid_id(dialog, monkeypatch):
    """Test creating category with invalid ID shows warning."""
    # Mock dialogs
    mock_getText = MagicMock(return_value=("Invalid-ID!", True))  # Invalid characters
    mock_warning = MagicMock()

    monkeypatch.setattr('PySide6.QtWidgets.QInputDialog.getText', mock_getText)
    monkeypatch.setattr('PySide6.QtWidgets.QMessageBox.warning', mock_warning)

    # Try to create with invalid ID
    dialog._on_new_category()

    # Should show warning
    mock_warning.assert_called_once()
    assert "lowercase letters" in str(mock_warning.call_args).lower()


def test_create_duplicate_category_warning(dialog, monkeypatch):
    """Test warning when creating category with existing ID."""
    # Mock dialogs
    mock_getText = MagicMock(return_value=("packaging", True))  # Already exists
    mock_warning = MagicMock()

    monkeypatch.setattr('PySide6.QtWidgets.QInputDialog.getText', mock_getText)
    monkeypatch.setattr('PySide6.QtWidgets.QMessageBox.warning', mock_warning)

    # Try to create with existing ID
    dialog._on_new_category()

    # Should show warning
    mock_warning.assert_called_once()
    assert "already exists" in str(mock_warning.call_args).lower()


# ============================================================================
# Delete Category Tests
# ============================================================================


def test_delete_category(dialog, monkeypatch):
    """Test deleting category."""
    initial_count = dialog.categories_list.count()

    dialog.categories_list.setCurrentRow(0)

    # Mock confirmation dialog
    mock_question = MagicMock(return_value=QMessageBox.Yes)
    monkeypatch.setattr('PySide6.QtWidgets.QMessageBox.question', mock_question)

    # Delete category
    dialog._on_delete_category()

    assert dialog.categories_list.count() == initial_count - 1
    assert dialog.modified is True

    # Check category removed from working copy
    categories = dialog.working_categories["categories"]
    assert "packaging" not in categories


def test_delete_category_cancelled(dialog, monkeypatch):
    """Test cancelling category deletion."""
    initial_count = dialog.categories_list.count()

    dialog.categories_list.setCurrentRow(0)

    # Mock confirmation dialog - user clicks No
    mock_question = MagicMock(return_value=QMessageBox.No)
    monkeypatch.setattr('PySide6.QtWidgets.QMessageBox.question', mock_question)

    # Try to delete category
    dialog._on_delete_category()

    # Category should not be deleted
    assert dialog.categories_list.count() == initial_count
    assert "packaging" in dialog.working_categories["categories"]


# ============================================================================
# Validation Tests
# ============================================================================


def test_validation_fails_with_invalid_config(dialog, monkeypatch):
    """Test validation fails when config is invalid."""
    # Mock critical dialog
    mock_critical = MagicMock()
    monkeypatch.setattr('PySide6.QtWidgets.QMessageBox.critical', mock_critical)

    # Break the config
    dialog.working_categories["categories"]["packaging"]["color"] = "invalid"  # Invalid color

    result = dialog._validate()

    assert result is False
    # Should show error message
    mock_critical.assert_called_once()


def test_validation_passes_with_valid_config(dialog):
    """Test validation passes with valid config."""
    result = dialog._validate()

    assert result is True


# ============================================================================
# Save/Cancel Tests
# ============================================================================


def test_save_emits_signal(dialog, monkeypatch):
    """Test save button emits categories_updated signal."""
    signal_spy = Mock()
    dialog.categories_updated.connect(signal_spy)

    # Mock any potential dialogs
    mock_critical = MagicMock()
    monkeypatch.setattr('PySide6.QtWidgets.QMessageBox.critical', mock_critical)

    # Make a change
    dialog.categories_list.setCurrentRow(0)
    dialog.label_input.setText("Modified")

    # Save
    with patch.object(dialog, 'accept'):  # Don't actually close
        dialog._on_save()

    # Check signal emitted
    signal_spy.assert_called_once()
    emitted_categories = signal_spy.call_args[0][0]
    assert emitted_categories["categories"]["packaging"]["label"] == "Modified"


def test_apply_button_saves_without_closing(dialog, monkeypatch):
    """Test apply button saves but doesn't close dialog."""
    signal_spy = Mock()
    dialog.categories_updated.connect(signal_spy)

    # Mock information dialog
    mock_info = MagicMock()
    monkeypatch.setattr('PySide6.QtWidgets.QMessageBox.information', mock_info)

    # Make a change
    dialog.categories_list.setCurrentRow(0)
    dialog.label_input.setText("Modified")

    # Apply
    dialog._on_apply()

    # Check signal emitted
    signal_spy.assert_called_once()

    # Dialog should still be open (not closed)
    assert dialog.modified is False  # Reset after successful save


def test_cancel_with_unsaved_changes_shows_warning(dialog, monkeypatch):
    """Test cancel with unsaved changes shows warning."""
    # Make a change
    dialog.categories_list.setCurrentRow(0)
    dialog.label_input.setText("Modified")

    assert dialog.modified is True

    # Mock question dialog
    mock_question = MagicMock(return_value=QMessageBox.No)  # Don't cancel
    monkeypatch.setattr('PySide6.QtWidgets.QMessageBox.question', mock_question)

    # Try to cancel
    dialog._on_cancel()

    # Should show warning
    mock_question.assert_called_once()
    assert "unsaved changes" in str(mock_question.call_args).lower()


def test_cancel_without_changes_closes_immediately(dialog):
    """Test cancel without changes closes immediately."""
    assert dialog.modified is False

    with patch.object(dialog, 'reject') as mock_reject:
        dialog._on_cancel()

        # Should reject without warning
        mock_reject.assert_called_once()


# ============================================================================
# Integration Tests
# ============================================================================


def test_full_workflow_create_edit_save(dialog, monkeypatch):
    """Test full workflow: create category, edit it, save."""
    signal_spy = Mock()
    dialog.categories_updated.connect(signal_spy)

    # Mock getText for all steps
    getText_returns = [
        ("test_cat", True),  # Step 1: category name
        ("TAG1", True),       # Step 3a: first tag
        ("TAG2", True)        # Step 3b: second tag
    ]
    mock_getText = MagicMock(side_effect=getText_returns)
    monkeypatch.setattr('PySide6.QtWidgets.QInputDialog.getText', mock_getText)

    # 1. Create new category
    dialog._on_new_category()

    # 2. Edit the new category
    # (Should be auto-selected after creation)
    dialog.label_input.setText("Test Category")

    # 3. Add tags
    dialog._on_add_tag()
    dialog._on_add_tag()

    # 4. Save
    with patch.object(dialog, 'accept'):
        dialog._on_save()

    # Verify
    signal_spy.assert_called_once()
    saved_categories = signal_spy.call_args[0][0]["categories"]

    assert "test_cat" in saved_categories
    assert saved_categories["test_cat"]["label"] == "Test Category"
    assert "TAG1" in saved_categories["test_cat"]["tags"]
    assert "TAG2" in saved_categories["test_cat"]["tags"]
