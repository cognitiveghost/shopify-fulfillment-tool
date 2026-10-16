"""Render the Fulfilment user-guide screenshots, one PNG per guide image, in one language.

    .venv/bin/python scripts/render_guide.py --lang en
    .venv/bin/python scripts/render_guide.py --lang bg --server <dir>

Drives the real MainWindow against a temp copy of the guide server folder (built by
build_guide_server.py unless --server is given), at the light theme and 1366x768. Dialogs
that would block in exec() are shown and grabbed instead, from inside the real opener.
Offscreen, with QSettings redirected to a temp dir, so this PC's settings and the real server
are never touched. Names are the same in EN and BG; only the folder differs.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import shutil
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

TMP = Path(tempfile.mkdtemp(prefix="render-guide-"))
SERVER = TMP / "server"
os.environ["FULFILLMENT_SERVER_PATH"] = str(SERVER)
assert SERVER.resolve().is_relative_to(Path(tempfile.gettempdir()).resolve())

# Redirect QSettings before any app import touches it.
from PySide6.QtCore import QPoint, QSettings, Qt

for fmt in (QSettings.Format.NativeFormat, QSettings.Format.IniFormat):
    QSettings.setPath(fmt, QSettings.Scope.UserScope, str(TMP / "settings"))

# QtWebEngine must be imported before the QApplication exists.
from PySide6.QtGui import QPainter
from PySide6.QtTest import QTest
from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
from PySide6.QtWidgets import QApplication, QWidget

from shared import i18n

CLIENT = "ALMA"
SERVER_LABEL = r"\\fs01\fulfillment"  # what the guide shows instead of the temp server path
SETTINGS_PAGES = {
    "profile": "Profile",
    "general": "General",
    "mappings": "Orders mapping",
    "rules": "Rules",
    "sets": "Sets",
    "weight": "Weight",
    "reports": "Reports",
    "tags": "Tag categories",
}
TABS = {"browse": 2, "logs": 3, "tools": 4}


def mask_server(text: str) -> str:
    """The temp server path, and any path under it, as the Windows share a warehouse PC sees."""
    return re.sub(re.escape(str(SERVER)) + r"[^\s'\"]*",
                  lambda m: SERVER_LABEL + m[0][len(str(SERVER)):].replace("/", "\\"), text)


def mask_server_everywhere() -> None:
    """Patch the sidebar's server line and every log message, before the window is built."""
    from gui.components.sidebar import Sidebar

    real_set = Sidebar.set_connection
    Sidebar.set_connection = lambda self, connected, path: real_set(self, connected, mask_server(path))
    make_record = logging.getLogRecordFactory()

    def masked_record(*args, **kwargs):
        record = make_record(*args, **kwargs)
        record.msg, record.args = mask_server(record.getMessage()), ()
        return record

    logging.setLogRecordFactory(masked_record)


def pump(ms: int) -> None:
    end = time.monotonic() + ms / 1000
    while time.monotonic() < end:
        QApplication.processEvents()
        time.sleep(0.01)


def pump_until(predicate, timeout: float = 20) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise SystemExit("timed out waiting for the app")
        pump(50)


def grab(widget: QWidget, out: Path, name: str, overlays: tuple = ()) -> None:
    """The widget as drawn, with popups (top-level windows, so not in the grab) pasted on.

    An overlay is (popup, top-left in widget coordinates). None means where the popup is now.
    The offscreen screen is 800x800, so a popup can be clamped; the paste puts it back.
    """
    image = widget.grab().toImage()
    painter = QPainter(image)
    origin = widget.mapToGlobal(QPoint(0, 0))
    for popup, at in overlays:
        if popup.isVisible():
            if at is None:
                at = popup.mapToGlobal(QPoint(0, 0)) - origin
            painter.drawPixmap(at, popup.grab())
    painter.end()
    path = out / f"{name}.png"
    if not image.save(str(path)):
        raise SystemExit(f"could not write {path}")
    print(path)


def settle(window: QWidget, ms: int = 1500) -> None:
    window.resize(1366, 768)
    window.show()
    pump(ms)


@contextmanager
def shown_not_executed(cls, out: Path, name: str):
    """Run the real opener, but show the dialog and grab it where it would block in exec()."""

    def show_and_grab(self, *_args):
        self.resize(max(self.width(), 900), max(self.height(), 600))
        self.show()
        pump(1500)
        grab(self, out, name)
        self.close()
        return 0

    with patch.object(cls, "exec", show_and_grab):
        yield


def pick_client(window, client_id: str) -> None:
    """Choose a client through the client selector, the way a user does: filter, then Enter."""
    bar = window.command_bar
    bar.client_selector.showPopup()
    popup = bar.client_selector.popup
    popup.filter_edit.setText(client_id)
    QTest.keyClick(popup.filter_edit, Qt.Key_Return)
    pump_until(lambda: window.current_client_id == client_id and not window._client_load_workers)
    pump(300)


def newest_session(session_manager, client_id: str) -> Path:
    listing = session_manager.list_client_sessions(client_id)
    return Path(session_manager.get_session_path(client_id, listing[0]["session_name"]))


def render(window, out: Path, lang: str) -> None:
    from gui.add_product_dialog import AddProductDialog
    from gui.client_settings_dialog import ArchivedClientsDialog, ClientCreationDialog
    from gui.report_selection_dialog import GenerateReportsDialog
    from gui.settings.window import SettingsWindow

    bar = window.command_bar
    settle(window, 1200)
    pick_client(window, CLIENT)
    settle(window, 1200)
    grab(window, out, "start")

    bar.client_selector.showPopup()
    settle(window, 600)
    grab(window, out, "client-menu", ((bar.client_selector.popup, None),))
    bar.client_selector.popup.close()

    latest = newest_session(window.session_manager, CLIENT)

    window.actions_handler.create_new_session()
    window.main_tabs.setCurrentIndex(0)
    settle(window, 1500)
    grab(window, out, "setup-empty")

    orders = next((latest / "input").glob("*orders*.csv"))
    window.file_handler.accept_dropped_path("orders", str(orders))
    settle(window, 1500)
    grab(window, out, "setup-loaded")

    window.load_existing_session(str(latest))
    pump_until(lambda: window.main_tabs.currentIndex() == 1)
    settle(window, 2000)
    grab(window, out, "results")

    with shown_not_executed(AddProductDialog, out, "add-product"):
        window.actions_handler.show_add_product_dialog()
    with shown_not_executed(GenerateReportsDialog, out, "reports"):
        window.actions_handler.open_generate_reports_dialog()

    window.main_tabs.setCurrentIndex(TABS["browse"])
    settle(window, 1500)
    grab(window, out, "browse")

    with shown_not_executed(ClientCreationDialog, out, "client-new"):
        window.client_directory.open_create_client_dialog(window)

    for slug, page in SETTINGS_PAGES.items():
        with shown_not_executed(SettingsWindow, out, f"settings-{slug}"):
            window.actions_handler.open_settings_window(page=page)

    window.main_tabs.setCurrentIndex(TABS["tools"])
    settle(window, 1500)
    grab(window, out, "tools")
    window.main_tabs.setCurrentIndex(TABS["logs"])
    settle(window, 1500)
    grab(window, out, "logs")

    window.main_tabs.setCurrentIndex(0)
    settle(window, 1000)
    # Last: the archive and restore write to the log.
    # One archived client, so the dialog shows a row; restored straight after.
    window.profile_manager.archive_client("HERBAR")
    with shown_not_executed(ArchivedClientsDialog, out, "client-archived"):
        window.open_archived_clients()
        pump(300)
    window.profile_manager.restore_client("HERBAR")

    # The language segment is in the sidebar footer; the menu holds the updates entry.
    button = bar.overflow_button
    bar.overflow.popup(button.mapToGlobal(QPoint(0, button.height())))
    pump(800)
    # Right-aligned under the button, as a user sees it; the popup itself may be clamped.
    corner = button.mapTo(window, QPoint(button.width(), button.height()))
    menu_at = corner - QPoint(bar.overflow.width(), 0)
    grab(window, out, "language", ((bar.overflow, menu_at),))
    bar.overflow.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lang", required=True, choices=sorted(i18n.LANGUAGES))
    parser.add_argument("--server", help="a guide server folder to copy (default: build a fresh one)")
    parser.add_argument("--out", help="output folder (default: docs/user-guide/img/<lang>)")
    args = parser.parse_args()

    out = Path(args.out) if args.out else ROOT / "docs" / "user-guide" / "img" / args.lang
    out.mkdir(parents=True, exist_ok=True)

    if args.server:
        shutil.copytree(args.server, SERVER)
    else:
        from build_guide_server import build

        build(SERVER)

    app = QApplication.instance() or QApplication(sys.argv)
    i18n.set_language(args.lang, i18n.catalogue_files(ROOT, args.lang))

    from gui.theme_manager import get_theme_manager

    theme_manager = get_theme_manager()
    theme_manager.set_theme("light")
    theme_manager.apply_theme()

    from gui.main_window_pyside import MainWindow

    mask_server_everywhere()
    window = MainWindow()
    window.show()
    pump(500)
    render(window, out, args.lang)
    window.close()
    app.processEvents()
    return 0


if __name__ == "__main__":
    try:
        code = main()
    finally:
        sys.stdout.flush()
        shutil.rmtree(TMP, ignore_errors=True)
    # QtWebEngine segfaults in its teardown after the PNGs are written; skip it.
    os._exit(code)
