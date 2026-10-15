"""Where the app finds its file server, and the dialogs that change it
(shared/server_connection.py; Audit 10, part A). QSettings is redirected to tmp_path."""

import time
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QDialog, QPushButton

import shared.server_connection as sc

ORG = "AuditTestOrg"
ENV = "AUDIT_TEST_SERVER_PATH"


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    """QSettings under tmp_path for both formats; the real ones restored afterwards."""
    home = str(Path.home() / ".config")
    for fmt in (QSettings.NativeFormat, QSettings.IniFormat):
        QSettings.setPath(fmt, QSettings.UserScope, str(tmp_path / "settings"))
    monkeypatch.delenv(ENV, raising=False)
    yield
    for fmt in (QSettings.NativeFormat, QSettings.IniFormat):
        QSettings.setPath(fmt, QSettings.UserScope, home)


def test_a_reachable_directory_passes_and_a_file_does_not(tmp_path):
    assert sc.test_path_reachable(str(tmp_path)) is True
    a_file = tmp_path / "a_file.txt"
    a_file.write_text("x", encoding="utf-8")
    assert sc.test_path_reachable(str(a_file)) is False


def test_a_check_that_hangs_is_reported_unreachable_in_time(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "touch", lambda *a, **k: time.sleep(2))
    started = time.monotonic()
    assert sc.test_path_reachable(str(tmp_path), timeout=0.2) is False
    assert time.monotonic() - started < 1.5


def test_the_effective_path_is_env_then_saved_then_fallback(monkeypatch):
    assert sc.get_saved_server_path(ORG) is None
    assert sc.resolve_server_path(ORG, ENV, "/fallback") == "/fallback"
    sc.save_server_path(ORG, "/saved")
    assert sc.get_saved_server_path(ORG) == "/saved"
    assert sc.resolve_server_path(ORG, ENV, "/fallback") == "/saved"
    monkeypatch.setenv(ENV, "/env")
    assert sc.resolve_server_path(ORG, ENV, "/fallback") == "/env"


def _click(dialog, text):
    (button,) = [b for b in dialog.findChildren(QPushButton) if b.text() == text]
    button.click()


def test_the_settings_dialog_shows_the_effective_path_and_saves_an_edit(qtbot, tmp_path, monkeypatch):
    told = []
    monkeypatch.setattr(sc.QMessageBox, "information", staticmethod(lambda *a, **k: told.append(a[1])))
    sc.save_server_path(ORG, "/saved")
    dialog = sc.ConnectionSettingsDialog(None, ORG, ENV, "/fallback")
    qtbot.addWidget(dialog)
    assert dialog.path_edit.text() == "/saved"

    dialog.path_edit.setText(f"  {tmp_path}  ")
    dialog._save()
    assert sc.get_saved_server_path(ORG) == str(tmp_path)
    assert told == ["Saved"]
    assert dialog.result() == QDialog.Accepted


def test_the_settings_dialog_says_when_an_environment_variable_overrides(qtbot, monkeypatch):
    monkeypatch.setenv(ENV, "/env")
    dialog = sc.ConnectionSettingsDialog(None, ORG, ENV, "/fallback")
    qtbot.addWidget(dialog)
    assert dialog.path_edit.text() == "/env"
    from PySide6.QtWidgets import QLabel

    assert any(f"Overridden by {ENV}" in label.text() for label in dialog.findChildren(QLabel))


def test_test_connection_reports_the_result(qtbot, tmp_path):
    dialog = sc.ConnectionSettingsDialog(None, ORG, ENV, str(tmp_path))
    qtbot.addWidget(dialog)
    from PySide6.QtWidgets import QLabel

    _click(dialog, "Test Connection")
    labels = [label.text() for label in dialog.findChildren(QLabel)]
    assert "✅ Connected" in labels
    dialog.path_edit.setText(str(tmp_path / "a_file"))
    (tmp_path / "a_file").write_text("x", encoding="utf-8")
    _click(dialog, "Test Connection")
    assert "❌ Not reachable" in [label.text() for label in dialog.findChildren(QLabel)]


def test_browse_puts_the_chosen_folder_in_the_field(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(sc.QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: "/picked"))
    dialog = sc.ConnectionSettingsDialog(None, ORG, ENV, str(tmp_path))
    qtbot.addWidget(dialog)
    _click(dialog, "Browse…")
    assert dialog.path_edit.text() == "/picked"
    monkeypatch.setattr(sc.QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: ""))
    _click(dialog, "Browse…")
    assert dialog.path_edit.text() == "/picked"  # cancelling keeps it


def _press(text, new_path=None):
    """A stand-in for QDialog.exec that types a path and presses `text`."""

    def fake_exec(self):
        if new_path is not None:
            from PySide6.QtWidgets import QLineEdit

            self.findChildren(QLineEdit)[0].setText(new_path)
        _click(self, text)
        return 0

    return fake_exec


def test_recovery_retry_saves_the_new_path_and_says_retry(qapp, monkeypatch):
    monkeypatch.setattr(QDialog, "exec", _press("Retry", " /new/server "))
    assert sc.prompt_for_recovery_path(None, "/dead/share", ORG) is True
    assert sc.get_saved_server_path(ORG) == "/new/server"


def test_recovery_retry_with_an_empty_field_keeps_the_saved_path(qapp, monkeypatch):
    sc.save_server_path(ORG, "/kept")
    monkeypatch.setattr(QDialog, "exec", _press("Retry", ""))
    assert sc.prompt_for_recovery_path(None, "/dead/share", ORG) is True
    assert sc.get_saved_server_path(ORG) == "/kept"


def test_recovery_exit_says_no_and_saves_nothing(qapp, monkeypatch):
    monkeypatch.setattr(QDialog, "exec", _press("Exit", "/typed/but/abandoned"))
    assert sc.prompt_for_recovery_path(None, "/dead/share", ORG) is False
    assert sc.get_saved_server_path(ORG) is None
