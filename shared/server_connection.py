"""File-server connection path: resolution, persistence, and UI.

Canonical copy lives in packing-tool/shared/; synced into
shopify-fulfillment-tool/shared/ by
shopify-fulfillment-tool/scripts/sync_shared.py.

Effective path priority (highest first):
    1. Env var (e.g. FULFILLMENT_SERVER_PATH)
    2. Value saved via the UI below (QSettings)
    3. Caller-supplied fallback (config.ini / hardcoded production path)
"""
import os
import threading
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

_SETTINGS_KEY = "server_path"


def test_path_reachable(path: str, timeout: int = 5) -> bool:
    """Touch-file check: True if `path` is a writable, reachable directory.

    Runs the filesystem check in a worker thread and bounds the wait to
    `timeout` seconds — a dead UNC path can block far longer than that at
    the OS level, and this is called synchronously from the Qt main thread
    (startup recovery loop, dialog "Test Connection" buttons), so an
    unbounded check would freeze the GUI instead of failing fast. A timed
    out check is reported unreachable; the worker thread is daemonized and
    left to finish on its own since a blocking filesystem call can't be
    cancelled from Python.
    """
    result = {}

    def _check():
        try:
            test_file = Path(path) / ".connection_test"
            test_file.parent.mkdir(parents=True, exist_ok=True)
            test_file.touch(exist_ok=True)
            result["ok"] = test_file.exists()
        except Exception:
            result["ok"] = False

    thread = threading.Thread(target=_check, daemon=True)
    thread.start()
    thread.join(timeout)
    return result.get("ok", False)


def get_saved_server_path(org: str) -> str | None:
    """Path saved via the UI for `org`, or None if never set."""
    value = QSettings(org, "Connection").value(_SETTINGS_KEY, None)
    return value or None


def save_server_path(org: str, path: str) -> None:
    """Persist `path` for `org` (takes effect after restart)."""
    QSettings(org, "Connection").setValue(_SETTINGS_KEY, path)


def resolve_server_path(org: str, env_var: str, fallback: str) -> str:
    """Effective path for `org`: env var > saved UI value > fallback."""
    env_path = os.environ.get(env_var)
    if env_path:
        return env_path
    return get_saved_server_path(org) or fallback


def _build_path_fields(layout, initial_path: str):
    """Add a path row (QLineEdit + Browse…) and a test row (button + result
    label) to `layout`. Shared by ConnectionSettingsDialog and
    prompt_for_recovery_path so both stay in sync. Returns (path_edit,
    result_label).
    """
    path_row = QHBoxLayout()
    path_edit = QLineEdit(initial_path)
    path_row.addWidget(path_edit)

    def _browse():
        directory = QFileDialog.getExistingDirectory(
            path_edit.parentWidget(), "Select Server Path", path_edit.text()
        )
        if directory:
            path_edit.setText(directory)

    browse_btn = QPushButton("Browse…")
    browse_btn.clicked.connect(_browse)
    path_row.addWidget(browse_btn)
    layout.addLayout(path_row)

    test_row = QHBoxLayout()
    result_label = QLabel("")

    def _test():
        ok = test_path_reachable(path_edit.text())
        result_label.setText("✅ Connected" if ok else "❌ Not reachable")

    test_btn = QPushButton("Test Connection")
    test_btn.clicked.connect(_test)
    test_row.addWidget(test_btn)
    test_row.addWidget(result_label)
    test_row.addStretch()
    layout.addLayout(test_row)

    return path_edit, result_label


class ConnectionSettingsDialog(QDialog):
    """Settings dialog: view, test, and save the server path for `org`.

    Reachable from Settings (packing-tool) / the header panel
    (shopify-fulfillment-tool, no menu bar there).
    """

    def __init__(self, parent, org: str, env_var: str, fallback: str):
        super().__init__(parent)
        self.org = org

        self.setWindowTitle("Server Connection")
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)

        env_value = os.environ.get(env_var)
        if env_value:
            warning = QLabel(f"Overridden by {env_var} environment variable")
            warning.setEnabled(False)
            layout.addWidget(warning)

        layout.addWidget(QLabel("Server path:"))
        self.path_edit, _ = _build_path_fields(
            layout, resolve_server_path(org, env_var, fallback)
        )

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save(self):
        save_server_path(self.org, self.path_edit.text().strip())
        QMessageBox.information(
            self, "Saved", "Restart the application for the new path to take effect."
        )
        self.accept()


def prompt_for_recovery_path(parent, attempted_path: str, org: str) -> bool:
    """Startup recovery prompt shown when connecting to the server fails.

    Same path/Browse/Test fields as ConnectionSettingsDialog, plus
    Retry/Exit. Returns True if the user saved a new path and chose Retry
    (caller should retry building ProfileManager), False if Exit (caller
    exits as before).
    """
    dialog = QDialog(parent)
    dialog.setWindowTitle("Cannot Connect to Server")
    dialog.setMinimumWidth(480)

    layout = QVBoxLayout(dialog)

    error_label = QLabel(str(attempted_path))
    error_label.setWordWrap(True)
    layout.addWidget(error_label)

    layout.addWidget(QLabel("Server path:"))
    path_edit, _ = _build_path_fields(layout, get_saved_server_path(org) or "")

    button_row = QHBoxLayout()
    button_row.addStretch()
    exit_btn = QPushButton("Exit")
    retry_btn = QPushButton("Retry")
    button_row.addWidget(exit_btn)
    button_row.addWidget(retry_btn)
    layout.addLayout(button_row)

    outcome = {"retry": False}

    def _on_retry():
        new_path = path_edit.text().strip()
        if new_path:
            save_server_path(org, new_path)
        outcome["retry"] = True
        dialog.accept()

    retry_btn.clicked.connect(_on_retry)
    exit_btn.clicked.connect(dialog.reject)

    dialog.exec()
    return outcome["retry"]


if __name__ == "__main__":
    import tempfile as _tempfile

    with _tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        # test_path_reachable
        assert test_path_reachable(str(tmp_path)) is True
        not_a_dir = tmp_path / "a_file.txt"
        not_a_dir.write_text("x")
        assert test_path_reachable(str(not_a_dir)) is False

        # resolve_server_path — isolate QSettings from the real user profile.
        # QSettings(org, app) uses NativeFormat; redirect both formats since
        # setPath only affects settings objects of the format it's given.
        QSettings.setPath(QSettings.NativeFormat, QSettings.UserScope, tmp)
        QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, tmp)

        org = "SelfCheckOrg"
        env_var = "SELF_CHECK_SERVER_PATH"
        os.environ.pop(env_var, None)

        assert resolve_server_path(org, env_var, "/fallback") == "/fallback"

        save_server_path(org, "/saved/path")
        assert resolve_server_path(org, env_var, "/fallback") == "/saved/path"

        os.environ[env_var] = "/env/path"
        assert resolve_server_path(org, env_var, "/fallback") == "/env/path"
        del os.environ[env_var]

    print("server_connection self-check OK")
