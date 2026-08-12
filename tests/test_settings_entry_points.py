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
