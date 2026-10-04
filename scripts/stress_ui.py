"""Stress the refreshed UI and print what it cost.

    .venv/bin/python scripts/stress_ui.py

Offscreen, against a throwaway server path. Prints one markdown table and
exits non-zero on a Python exception or a JavaScript error. It measures; it
gates nothing (2026-10-04 quickfixes spec, section 5.2).
"""

import logging
import os
import resource
import statistics
import sys
import tempfile
import time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
SERVER = Path(tempfile.mkdtemp(prefix="stress-ui-"))
os.environ["FULFILLMENT_SERVER_PATH"] = str(SERVER)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication

app = QApplication([])

from gui.theme_manager import ThemeManager, get_theme_manager

# Never the developer's own saved theme.
ThemeManager._save_theme_preference = lambda self: None

from gui.components.commandbar import BarState
from gui.main_window_pyside import MainWindow
from gui.settings.window import SettingsWindow
from gui.web_page import switch_theme

ERROR_HOOK = (
    "window.__errors = window.__errors || [];"
    " window.addEventListener('error', (e) => window.__errors.push(String(e.message)));"
    " true"
)
ROWS = []
FAILURES = []


def spin(seconds: float) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.005)


def wait_for(predicate, timeout: float = 30.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.005)
    return False


def js(view, code: str, timeout: float = 30.0):
    box = []
    view.page().runJavaScript(code, 0, box.append)
    wait_for(lambda: bool(box), timeout)
    return box[0] if box else None


def settled(view) -> None:
    """One animation-frame round trip: the page has handled what it was sent."""
    js(view, "new Promise((r) => requestAnimationFrame(() => r(true)))")


def rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024  # Linux: KiB


def scenario(name: str, iterations: int, step) -> None:
    """Run step(i) `iterations` times; record time per step, widgets, RSS."""
    widgets, rss, times = len(app.allWidgets()), rss_mb(), []
    try:
        for i in range(iterations):
            start = time.perf_counter()
            step(i)
            times.append((time.perf_counter() - start) * 1000)
    except Exception as error:  # a finding, not a crash of the harness
        FAILURES.append(f"{name}: {error!r}")
    spin(0.5)
    ROWS.append(
        (
            name,
            len(times),
            f"{statistics.median(times):.0f}" if times else "-",
            f"{max(times):.0f}" if times else "-",
            f"{widgets} -> {len(app.allWidgets())}",
            f"{rss:.0f} -> {rss_mb():.0f}",
        )
    )


def orders(count: int) -> pd.DataFrame:
    rows = []
    for i in range(count):
        for line in range(1 + i % 4):
            rows.append(
                {
                    "Order_Number": f"#{10001 + i}",
                    "Order_Fulfillment_Status": "Not Fulfillable" if i % 10 == 3 else "Fulfillable",
                    "Shipping_Provider": ("DHL", "DPD", "Packeta", "")[i % 4],
                    "Customer": f"Customer {i:05d}",
                    "Total_Price": 10.0 + i,
                    "SKU": f"SKU-{i:05d}-{line}",
                    "Product_Name": f"Product {line}",
                    "Warehouse_Name": "Main",
                    "Quantity": 1 + line,
                    "Internal_Tags": "[]",
                    "System_note": "",
                }
            )
    return pd.DataFrame(rows)


def main() -> int:
    get_theme_manager().apply_theme()
    win = MainWindow()
    win.resize(1280, 860)
    win.show()
    spin(2)
    for cid in ("A", "B"):
        win.profile_manager.create_client_profile(cid, f"Client {cid}")
    win.command_bar.set_clients(["A", "B"])
    win.command_bar.set_current_client("A")
    wait_for(lambda: not win._client_load_workers)
    for view in win.findChildren(QWebEngineView):
        js(view, ERROR_HOOK)

    # 1. Results at size. The page is told the same frame again each step.
    results = win.results_view
    df = orders(10_000)

    python_side = []

    def push_results(_i):
        start = time.perf_counter()
        win.analysis_results_df = df
        win._update_all_views()
        win.update_ui_state()
        win.main_tabs.setCurrentIndex(1)
        python_side.append((time.perf_counter() - start) * 1000)
        if not wait_for(
            lambda: js(results, "document.querySelectorAll('#rows .row').length > 0") is True
        ):
            raise RuntimeError("no rows rendered")

    scenario("Results, 10 000 orders pushed", 3, push_results)
    ROWS[-1] = (
        f"{ROWS[-1][0]} (Python side {statistics.median(python_side):.0f} ms)",
        *ROWS[-1][1:],
    )

    # 2. Results interaction: select-all twice, two sorts, a search.
    def interact(i):
        js(results, "document.querySelector('#header .col-select input').click(); true")
        js(results, "document.querySelector('#header .col-select input').click(); true")
        js(results, "document.querySelector('#header .col-order').click(); true")
        js(results, "document.querySelector('#header .col-customer').click(); true")
        js(
            results,
            "(() => { const field = document.getElementById('search');"
            f" field.value = '{'' if i % 2 else 'Customer 0001'}';"
            " field.dispatchEvent(new Event('input', {bubbles: true})); return true; })()",
        )
        settled(results)

    scenario("Results: select all, sort x2, search", 20, interact)

    # 3. Theme switching, Results visible.
    def flip(i):
        target = "dark" if i % 2 == 0 else "light"
        switch_theme(target)
        if not wait_for(lambda: get_theme_manager().get_current_theme_name() == target):
            raise RuntimeError(f"theme never became {target}")

    scenario("Theme switch (Results visible)", 100, flip)
    switch_theme("light")
    wait_for(lambda: get_theme_manager().get_current_theme_name() == "light")

    # 4. Client switching. The open session must go with the client.
    win.session_path = win.session_manager.create_session("A")

    def client(i):
        win.command_bar.set_current_client("B" if i % 2 == 0 else "A")
        wait_for(lambda: not win._client_load_workers)

    scenario("Client switch A <-> B", 50, client)

    # 5. Session loop: what New session does, minus its progress dialog.
    def new_session(_i):
        path = win.session_manager.create_session(win.current_client_id)
        win._reset_session_state()
        win.session_path = path
        win.command_bar.set_state(BarState.SESSION)
        win.ui_manager.update_session_chips()
        win.update_ui_state()

    scenario("Session create + reset", 30, new_session)

    # 6. Log flood through the root handler into the Logs page.
    win.main_tabs.setCurrentIndex(3)
    flood = logging.getLogger("stress")
    flood.setLevel(logging.INFO)

    def flood_logs(_i):
        for k in range(20_000):
            flood.info("entry %d", k)
        spin(1)

    scenario("Log flood, 20 000 entries", 1, flood_logs)
    rendered = js(win.logs_widget.view, "document.querySelectorAll('.row, tr').length")
    ROWS[-1] = (f"{ROWS[-1][0]} ({rendered} nodes kept)", *ROWS[-1][1:])

    # 7. The Settings window, opened and closed. Built directly: the
    # actions handler's opener is modal and would block this script.
    config = win.profile_manager.load_shopify_config("A")

    def settings(_i):
        window = SettingsWindow(
            client_id="A",
            client_config=config,
            profile_manager=win.profile_manager,
            parent=win,
        )
        window.show()
        spin(0.3)
        for view in window.findChildren(QWebEngineView):
            errors = js(view, "window.__errors || []")
            if errors:
                FAILURES.append(f"JS errors in Settings: {errors}")
        window.close()
        window.deleteLater()
        # deleteLater() posted from inside a nested loop is only delivered
        # when asked for; without this the widget count measures the script.
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        spin(0.1)

    scenario("Settings window open + close", 20, settings)

    # 8. Browse at size: 500 session folders for client A.
    for _ in range(500):
        win.session_manager.create_session("A")
    win.command_bar.set_current_client("A")

    def browse(_i):
        win.main_tabs.setCurrentIndex(2)
        win.session_browser.refresh_sessions()
        wait_for(lambda: not win.session_browser._loading)
        settled(win.session_browser.view)

    scenario("Browse, 500 sessions reload", 3, browse)

    for view in win.findChildren(QWebEngineView):
        errors = js(view, "window.__errors || []")
        if errors:
            FAILURES.append(f"JS errors in {view.url().toString()[-40:]}: {errors}")

    print("| Scenario | n | median ms | worst ms | widgets | RSS MB |")
    print("|---|---|---|---|---|---|")
    for row in ROWS:
        print("| " + " | ".join(str(c) for c in row) + " |")
    for failure in FAILURES:
        print("FAILED:", failure)
    return 1 if FAILURES else 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)  # Chromium's teardown can hang an offscreen exit
