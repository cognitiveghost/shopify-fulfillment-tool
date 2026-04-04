"""Tests for SessionBrowserWidget."""

import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import pytest
from unittest.mock import Mock, patch
from datetime import datetime

# Set Qt platform to offscreen for CI/headless environments
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from gui.session_browser_widget import SessionBrowserWidget
from shopify_tool.session_manager import SessionManager


@pytest.fixture
def mock_session_manager(tmp_path):
    """Create a mock SessionManager."""
    sm = Mock(spec=SessionManager)
    # sessions_root is an instance attribute — add it manually
    sm.sessions_root = tmp_path
    # Packing registry methods return empty data by default
    sm.get_registry_path.return_value = tmp_path / "registry_index.json"
    sm.get_session_packing_summary.return_value = {
        "pack_status": "not_started",
        "packed_orders": 0,
        "total_orders": 0,
        "worker_names": [],
        "packing_lists": [],
        "last_pack_activity": "",
    }
    return sm


@pytest.fixture
def session_browser(qtbot, mock_session_manager):
    """Create a SessionBrowserWidget for testing."""
    # Disable async mode for tests (use synchronous loading)
    SessionBrowserWidget.USE_ASYNC = False
    widget = SessionBrowserWidget(mock_session_manager)
    qtbot.addWidget(widget)
    return widget


@pytest.fixture
def sample_sessions():
    """Create sample session data."""
    return [
        {
            "session_name": "2025-11-05_1",
            "status": "active",
            "created_at": datetime.now().isoformat(),
            "analysis_completed": True,
            "session_path": "/path/to/session1",
            "statistics": {
                "total_orders": 10,
                "total_items": 25,
                "packing_lists_count": 2,
                "packing_lists": ["DHL", "UPS"]
            },
            "comments": "Test session 1"
        },
        {
            "session_name": "2025-11-04_2",
            "status": "completed",
            "created_at": datetime.now().isoformat(),
            "analysis_completed": True,
            "session_path": "/path/to/session2",
            "statistics": {
                "total_orders": 5,
                "total_items": 15,
                "packing_lists_count": 1,
                "packing_lists": ["FedEx"]
            },
            "comments": "Completed session"
        },
        {
            "session_name": "2025-11-04_1",
            "status": "active",
            "created_at": datetime.now().isoformat(),
            "analysis_completed": False,
            "session_path": "/path/to/session3",
            "statistics": {
                "total_orders": 0,
                "total_items": 0,
                "packing_lists_count": 0,
                "packing_lists": []
            },
            "comments": ""
        }
    ]


def test_session_browser_initialization(session_browser):
    """Test that SessionBrowserWidget initializes correctly."""
    assert session_browser.sessions_table.rowCount() == 0
    assert session_browser.sessions_table.columnCount() == 11
    assert not session_browser.open_btn.isEnabled()


def test_set_client_and_load_sessions(session_browser, mock_session_manager, sample_sessions):
    """Test setting client and loading sessions."""
    mock_session_manager.list_client_sessions.return_value = sample_sessions

    session_browser.set_client("M")

    # Should call session manager
    mock_session_manager.list_client_sessions.assert_called_once_with("M", status_filter=None)

    # Should populate table
    assert session_browser.sessions_table.rowCount() == 3


def test_status_filter(session_browser, mock_session_manager, sample_sessions):
    """Test status filtering."""
    # Setup
    session_browser.current_client_id = "M"

    # Filter by active
    mock_session_manager.list_client_sessions.return_value = [
        s for s in sample_sessions if s["status"] == "active"
    ]

    session_browser.status_filter.setCurrentText("Active")

    # Should filter sessions
    mock_session_manager.list_client_sessions.assert_called_with("M", status_filter="active")


def test_refresh_sessions(session_browser, mock_session_manager, sample_sessions):
    """Test refreshing sessions."""
    mock_session_manager.list_client_sessions.return_value = sample_sessions
    session_browser.current_client_id = "M"

    session_browser.refresh_sessions()

    assert session_browser.sessions_table.rowCount() == 3


def test_session_selection_enables_button(qtbot, session_browser, mock_session_manager, sample_sessions):
    """Test that selecting a session enables the open button."""
    mock_session_manager.list_client_sessions.return_value = sample_sessions
    session_browser.set_client("M")

    # Initially disabled
    assert not session_browser.open_btn.isEnabled()

    # Select first row
    session_browser.sessions_table.selectRow(0)

    # Should be enabled
    assert session_browser.open_btn.isEnabled()


def test_double_click_emits_signal(qtbot, session_browser, mock_session_manager, sample_sessions):
    """Test that double-clicking a session emits signal."""
    mock_session_manager.list_client_sessions.return_value = sample_sessions
    session_browser.set_client("M")

    # Double-click first row
    session_browser.sessions_table.selectRow(0)

    with qtbot.waitSignal(session_browser.session_selected, timeout=1000) as blocker:
        session_browser._on_session_double_clicked(None)

    # Check signal was emitted with session path
    assert blocker.args == ["/path/to/session1"]


def test_no_client_selected(session_browser, mock_session_manager):
    """Test behavior when no client is selected."""
    session_browser.refresh_sessions()

    # Should not crash, table should be empty
    assert session_browser.sessions_table.rowCount() == 0


def test_get_selected_session_path(session_browser, mock_session_manager, sample_sessions):
    """Test getting selected session path."""
    mock_session_manager.list_client_sessions.return_value = sample_sessions
    session_browser.set_client("M")

    # Select second row
    session_browser.sessions_table.selectRow(1)

    session_path = session_browser.get_selected_session_path()
    assert session_path == "/path/to/session2"
