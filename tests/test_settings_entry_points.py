"""Guards the naming fix: the button label and the dialog title must not
both say "Client Settings" again. They named different windows, which is
the confusion Phase 6 flagged."""
import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_profile_manager_dialog_is_gone():
    with pytest.raises(ModuleNotFoundError):
        import gui.profile_manager_dialog  # noqa: F401


def test_client_profile_dialog_has_no_placeholder_advanced_tab(qapp, monkeypatch):
    from gui.client_settings_dialog import ClientSettingsDialog

    assert not hasattr(ClientSettingsDialog, "_create_advanced_tab")


def test_client_profile_dialog_is_titled_client_profile():
    """ClientSettingsDialog edits the client *profile*; the settings window
    is the one called "Settings". Reading the source keeps this off the
    constructor, which needs a live profile_manager and a server path."""
    from pathlib import Path

    import gui.client_settings_dialog as mod

    source = Path(mod.__file__).read_text()
    assert 'setWindowTitle(f"Client Profile - CLIENT_{client_id}")' in source


def test_settings_buttons_are_labelled_settings():
    """Both settings entry points open SettingsWindow, so neither may say
    "Client Settings" -- that named the other dialog. Tab 2's is a QAction
    in the overflow menu (Phase 8.8b), not a QPushButton like Tab 1's."""
    import re
    from pathlib import Path

    import gui.ui_manager as mod

    source = Path(mod.__file__).read_text()
    assert source.count('QPushButton("Settings")') == 1
    tab2_label = re.search(
        r'self\.mw\.settings_button_tab2 = action\(\s*"([^"]*)"', source
    )
    assert tab2_label and tab2_label.group(1) == "Settings"
    assert 'QPushButton("Client Settings")' not in source
    assert '"Client Settings",' not in source
