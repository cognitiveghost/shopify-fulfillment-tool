"""Render Fulfilment's main pages and settings pages to PNG, for checking a language.

Offscreen, against a temp settings store and server path, so it never touches
this PC's real QSettings or the production server. Run it once per theme:

    .venv/bin/python scripts/render_i18n.py --lang bg --theme light
    .venv/bin/python scripts/render_i18n.py --lang bg --theme dark
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock

os.environ["QT_QPA_PLATFORM"] = "offscreen"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

TMP = Path(tempfile.mkdtemp(prefix="render-i18n-"))
os.environ["FULFILLMENT_SERVER_PATH"] = str(TMP / "server")

# Redirect QSettings before any app import touches it.
from PySide6.QtCore import QSettings

for fmt in (QSettings.Format.NativeFormat, QSettings.Format.IniFormat):
    QSettings.setPath(fmt, QSettings.Scope.UserScope, str(TMP / "settings"))

# QtWebEngine must be imported before the QApplication exists.
import pandas as pd
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication

from shared import i18n


def pump(ms: int) -> None:
    end = time.monotonic() + ms / 1000
    while time.monotonic() < end:
        QApplication.processEvents()
        time.sleep(0.01)


def wait_js(view: QWebEngineView, expr: str, timeout: float = 15) -> None:
    box: list = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        view.page().runJavaScript(expr, 0, box.append)
        pump(100)
        if box and box[-1] is True:
            return
        box.clear()
    raise SystemExit(f"page never became true: {expr}")


def slug(text: str) -> str:
    return "".join(c.lower() if c.isalnum() else "-" for c in text).strip("-")


def settle(widget, ms: int = 1500) -> None:
    widget.resize(1366, 768)
    widget.show()
    pump(ms)


def save(widget, out: Path, name: str, theme: str) -> None:
    path = out / f"{name}-{theme}.png"
    if not widget.grab().save(str(path)):
        raise SystemExit(f"could not write {path}")
    print(path)


def render_main(window, out: Path, theme: str) -> None:
    from gui.ui_manager import UIManager

    for index, label in enumerate(UIManager._RAIL_LABELS):
        window.main_tabs.setCurrentIndex(index)
        settle(window, 1500)
        save(window, out, f"{index + 1:02d}-{slug(label)}", theme)


def render_settings(out: Path, theme: str, cfg_factory) -> None:
    from gui.settings.window import SettingsWindow

    win = SettingsWindow(client_id="M", client_config=cfg_factory(), profile_manager=Mock())
    # Only the pages this window has: Profile needs a profile payload.
    for index, name in enumerate(win._nav_page_names()):
        win._select_page(name)
        settle(win, 1200)
        save(win, out, f"settings-{index + 1:02d}-{slug(name)}", theme)
    win.deleteLater()
    QApplication.processEvents()


def render_results(out: Path, theme: str) -> None:
    from gui.results_bridge import mount_results_page

    view = QWebEngineView()
    mount_results_page(view).set_orders(
        pd.DataFrame(
            {
                "Order_Number": ["#1001", "#1002", "#1002"],
                "Notes": [None, "call first", "call first"],
                "SKU": ["A", "TS-4409-B", "C"],
                "Quantity": [1, 6, 2],
            }
        )
    )
    view.resize(1366, 768)
    view.show()
    wait_js(view, "window.resultsBridge && window.resultsBridge.orders.length === 2")
    pump(800)
    view.grab().save(str(out / f"12-results-with-data-{theme}.png"))
    print(out / f"12-results-with-data-{theme}.png")
    view.close()


def render_browse(out: Path, theme: str) -> None:
    from test_browse_page import SESSIONS
    from test_browse_state import make_state

    from gui.browse_bridge import mount_browse_page

    view = QWebEngineView()
    bridge = mount_browse_page(view)
    view.resize(1166, 720)
    view.show()
    wait_js(view, "document.documentElement.dataset.bridge === 'ready'")
    bridge.set_state(make_state(SESSIONS))
    wait_js(view, "Number(document.documentElement.dataset.renders || 0) > 0")
    pump(800)
    view.grab().save(str(out / f"13-browse-with-data-{theme}.png"))
    print(out / f"13-browse-with-data-{theme}.png")
    view.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lang", default="bg", choices=sorted(i18n.LANGUAGES))
    parser.add_argument("--theme", default="light", choices=("light", "dark"))
    parser.add_argument("--out", default=str(ROOT / "docs" / "design" / "i18n-renders" / "fulfilment"))
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    app = QApplication.instance() or QApplication(sys.argv)
    i18n.set_language(args.lang, i18n.catalogue_files(ROOT, args.lang))

    from gui.theme_manager import get_theme_manager

    theme_manager = get_theme_manager()
    theme_manager.set_theme(args.theme)
    theme_manager.apply_theme()

    from conftest import settings_fixture_config

    from gui.main_window_pyside import MainWindow

    window = MainWindow()
    window.show()
    pump(500)
    render_main(window, out, args.theme)
    # The conftest fixture is a plain function under pytest's wrapper.
    cfg_factory = getattr(settings_fixture_config, "__wrapped__", settings_fixture_config)
    render_settings(out, args.theme, cfg_factory)
    window.close()

    render_results(out, args.theme)
    render_browse(out, args.theme)
    app.processEvents()
    return 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    # QtWebEngine segfaults in its teardown after the PNGs are written; skip it.
    os._exit(code)
