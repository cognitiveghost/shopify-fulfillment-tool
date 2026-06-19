"""Database connection settings dialog.

Allows per-PC configuration of the PostgreSQL connection string.
Settings are saved to %LOCALAPPDATA%/ShopifyFulfillment/db_connection.json
and picked up automatically on next app start (or after clicking Save & Reconnect).
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from gui.theme_manager import get_theme_manager
from shopify_tool.db_manager import load_local_dsn, reset_db, save_local_dsn

logger = logging.getLogger(__name__)

_DEFAULT_HOST = "localhost"
_DEFAULT_PORT = 5432
_DEFAULT_DB = "fulfillment_db"
_DEFAULT_USER = "postgres"


def _parse_dsn(dsn: str) -> dict:
    """Extract fields from a postgresql://user:pass@host:port/db DSN."""
    result = {
        "host": _DEFAULT_HOST,
        "port": _DEFAULT_PORT,
        "dbname": _DEFAULT_DB,
        "user": _DEFAULT_USER,
        "password": "",
    }
    try:
        # Strip scheme
        rest = dsn
        for scheme in ("postgresql://", "postgres://"):
            if rest.startswith(scheme):
                rest = rest[len(scheme):]
                break

        # user:pass@host:port/db
        if "@" in rest:
            userinfo, hostinfo = rest.split("@", 1)
        else:
            userinfo, hostinfo = "", rest

        if ":" in userinfo:
            result["user"], result["password"] = userinfo.split(":", 1)
        elif userinfo:
            result["user"] = userinfo

        if "/" in hostinfo:
            hostpart, result["dbname"] = hostinfo.split("/", 1)
        else:
            hostpart = hostinfo

        if ":" in hostpart:
            result["host"], port_str = hostpart.split(":", 1)
            try:
                result["port"] = int(port_str)
            except ValueError:
                pass
        elif hostpart:
            result["host"] = hostpart
    except Exception:
        pass
    return result


def _build_dsn(host: str, port: int, dbname: str, user: str, password: str) -> str:
    if password:
        return f"postgresql://{user}:{password}@{host}:{port}/{dbname}"
    return f"postgresql://{user}@{host}:{port}/{dbname}"


class DbSettingsDialog(QDialog):
    """Dialog for configuring the PostgreSQL connection."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Database Connection Settings")
        self.setMinimumWidth(460)
        self.setModal(True)

        theme = get_theme_manager().get_current_theme()
        self.setStyleSheet(f"""
            QDialog {{
                background: {theme.background};
                color: {theme.text};
            }}
            QLabel {{
                color: {theme.text};
            }}
            QLineEdit, QSpinBox {{
                background: {theme.background_elevated};
                color: {theme.text};
                border: 1px solid {theme.border};
                border-radius: 4px;
                padding: 4px 8px;
            }}
            QGroupBox {{
                color: {theme.text};
                border: 1px solid {theme.border};
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 8px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 8px;
            }}
            QPushButton {{
                background: {theme.background_elevated};
                color: {theme.text};
                border: 1px solid {theme.border};
                border-radius: 4px;
                padding: 6px 14px;
            }}
            QPushButton:hover {{
                background: {theme.border};
            }}
            QPushButton#testBtn {{
                background: {theme.accent if hasattr(theme, 'accent') else '#2196F3'};
                color: white;
                border: none;
            }}
        """)

        self._build_ui()
        self._load_current()

    # ── UI construction ────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Info label
        info = QLabel(
            "These settings are saved locally on this PC and override the\n"
            "DATABASE_URL environment variable."
        )
        info.setWordWrap(True)
        theme = get_theme_manager().get_current_theme()
        info.setStyleSheet(f"color: {theme.text_secondary}; font-size: 11px;")
        layout.addWidget(info)

        # Connection group
        group = QGroupBox("PostgreSQL Connection")
        form = QFormLayout(group)
        form.setLabelAlignment(Qt.AlignRight)
        form.setSpacing(8)

        self._host_edit = QLineEdit()
        self._host_edit.setPlaceholderText("localhost or server IP")
        form.addRow("Host:", self._host_edit)

        self._port_spin = QSpinBox()
        self._port_spin.setRange(1, 65535)
        self._port_spin.setValue(_DEFAULT_PORT)
        self._port_spin.setFixedWidth(100)
        form.addRow("Port:", self._port_spin)

        self._db_edit = QLineEdit()
        self._db_edit.setPlaceholderText("fulfillment_db")
        form.addRow("Database:", self._db_edit)

        self._user_edit = QLineEdit()
        self._user_edit.setPlaceholderText("postgres")
        form.addRow("Username:", self._user_edit)

        self._pass_edit = QLineEdit()
        self._pass_edit.setEchoMode(QLineEdit.Password)
        self._pass_edit.setPlaceholderText("(empty = no password)")
        form.addRow("Password:", self._pass_edit)

        layout.addWidget(group)

        # DSN preview
        self._dsn_label = QLabel()
        self._dsn_label.setStyleSheet(f"color: {get_theme_manager().get_current_theme().text_secondary}; font-family: monospace; font-size: 11px;")
        self._dsn_label.setWordWrap(True)
        layout.addWidget(self._dsn_label)

        for w in (self._host_edit, self._db_edit, self._user_edit, self._pass_edit):
            w.textChanged.connect(self._update_preview)
        self._port_spin.valueChanged.connect(self._update_preview)

        # Test connection button
        test_row = QHBoxLayout()
        self._test_btn = QPushButton("Test Connection")
        self._test_btn.setObjectName("testBtn")
        self._test_btn.clicked.connect(self._test_connection)
        self._status_label = QLabel()
        self._status_label.setWordWrap(True)
        test_row.addWidget(self._test_btn)
        test_row.addWidget(self._status_label, 1)
        layout.addLayout(test_row)

        # Dialog buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Save && Reconnect")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ── Data helpers ───────────────────────────────────────────────────────

    def _load_current(self):
        from shopify_tool.db_manager import _resolve_dsn
        dsn = _resolve_dsn(None)
        fields = _parse_dsn(dsn)
        self._host_edit.setText(fields["host"])
        self._port_spin.setValue(fields["port"])
        self._db_edit.setText(fields["dbname"])
        self._user_edit.setText(fields["user"])
        self._pass_edit.setText(fields["password"])
        self._update_preview()

    def _current_dsn(self) -> str:
        return _build_dsn(
            self._host_edit.text().strip() or _DEFAULT_HOST,
            self._port_spin.value(),
            self._db_edit.text().strip() or _DEFAULT_DB,
            self._user_edit.text().strip() or _DEFAULT_USER,
            self._pass_edit.text(),
        )

    def _update_preview(self):
        dsn = self._current_dsn()
        # Mask password in preview
        if self._pass_edit.text():
            display = dsn.replace(f":{self._pass_edit.text()}@", ":***@")
        else:
            display = dsn
        self._dsn_label.setText(f"DSN: {display}")

    # ── Actions ────────────────────────────────────────────────────────────

    def _test_connection(self):
        import psycopg2

        self._test_btn.setEnabled(False)
        self._status_label.setText("Connecting…")
        self._status_label.setStyleSheet("color: gray;")
        QDialog.repaint(self)

        dsn = self._current_dsn()
        try:
            conn = psycopg2.connect(dsn, connect_timeout=5)
            conn.close()
            self._status_label.setText("Connection successful!")
            self._status_label.setStyleSheet("color: #4CAF50;")
        except Exception as e:
            self._status_label.setText(f"Failed: {e}")
            self._status_label.setStyleSheet("color: #f44336;")
        finally:
            self._test_btn.setEnabled(True)

    def _save(self):
        dsn = self._current_dsn()
        try:
            save_local_dsn(dsn)
            reset_db(dsn)
            logger.info("DB reconnected to: %s", dsn.split("@")[-1])
            QMessageBox.information(
                self,
                "Saved",
                "Database settings saved.\nApplication is now connected to the new database.",
            )
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save settings:\n{e}")
