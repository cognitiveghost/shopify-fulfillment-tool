"""Opens the user guide PDF from the server's Guides folder.

Files are `<server_root>/Guides/<app>-<lang>.pdf`. The app's language is tried
first, then English. A server that cannot be reached counts as missing, so the
Help action warns and never raises.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox, QWidget

from shared import i18n
from shared.i18n import _


def guide_pdf(server_root: str | Path, app: str) -> Path | None:
    guides = Path(server_root) / "Guides"
    for lang in dict.fromkeys((i18n.language(), "en")):
        try:
            path = guides / f"{app}-{lang}.pdf"
            if path.is_file():
                return path
        except OSError:
            return None
    return None


def open_guide(parent: QWidget | None, server_root: str | Path, app: str) -> None:
    path = guide_pdf(server_root, app)
    if path is None:
        folder = str(Path(server_root) / "Guides")
        QMessageBox.warning(parent, _("User guide"),
                            _("The user guide was not found in {folder}.", folder=folder))
        return
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
