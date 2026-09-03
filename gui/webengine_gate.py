"""THROWAWAY. The Phase 9 build gate (Bundle 2 / roadmap 9.10).

A window containing one QWebEngineView, reached by `gui_main.py
--webengine-gate`. It answers one question -- does Chromium survive
PyInstaller and render over RDP -- and is deleted once that question has an
answer. It is not the beginning of Track W.

The frozen build is --windowed, so Windows gives it no console and anything
printed to stdout is lost. Every measurement is therefore rendered into the
page itself, where a human on an RDP session can read and screenshot it.
"""
import os
import sys
import time

from PySide6 import __version__ as _PYSIDE_VERSION
from PySide6.QtCore import qVersion
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QMainWindow

from gui.theme_manager import get_theme_manager
from shared.theme import font_css

GATE_WINDOW_SIZE = (1366, 768)

QT_VERSION = f"{qVersion()} (PySide6 {_PYSIDE_VERSION})"
CHROMIUM_VERSION = os.environ.get("QTWEBENGINE_CHROMIUM_VERSION", "bundled")


def build_gate_html(theme, *, startup_seconds, load_seconds, accommodations):
    """The probe page. Pure -- no Qt, no I/O -- so it can be tested."""
    load_text = f"{load_seconds:.2f}s" if load_seconds is not None else "measuring…"
    accommodation_text = ", ".join(accommodations) if accommodations else "none needed"
    return f"""<!doctype html>
<meta charset="utf-8">
<style>
  body {{
    margin: 0; padding: 48px;
    background: {theme.surface};
    color: {theme.text};
    font-family: {theme.font_family};
  }}
  .card {{
    background: {theme.surface_raised};
    border-left: 3px solid {theme.accent_fill};
    border-radius: 6px;
    padding: 24px 32px;
    max-width: 640px;
  }}
  h1 {{ {font_css("heading")} margin: 0 0 24px; }}
  dl {{ display: grid; grid-template-columns: max-content 1fr; gap: 8px 24px; margin: 0; }}
  dt {{ color: {theme.text}; opacity: 0.7; }}
  dd {{ margin: 0; font-variant-numeric: tabular-nums; }}
  footer {{ margin-top: 24px; padding-top: 16px; border-top: 1px solid {theme.border}; }}
</style>
<div class="card">
  <h1>Chromium is rendering this page.</h1>
  <dl>
    <dt>Qt</dt><dd>{QT_VERSION}</dd>
    <dt>Chromium</dt><dd>{CHROMIUM_VERSION}</dd>
    <dt>Startup to window</dt><dd>{startup_seconds:.2f}s</dd>
    <dt>View to loaded</dt><dd>{load_text}</dd>
    <dt>Accommodations</dt><dd>{accommodation_text}</dd>
  </dl>
  <footer>Screenshot this window. Phase 9 build gate — roadmap 9.10.</footer>
</div>
"""


def _accommodations_in_effect():
    """Which RDP workarounds the environment asked for, for the record."""
    found = []
    flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    if flags:
        found.extend(flags.split())
    if os.environ.get("QTWEBENGINE_DISABLE_SANDBOX"):
        found.append("sandbox disabled")
    return found


def run_gate(process_start=None):
    """Show one QWebEngineView and report what it cost. Returns an exit code."""
    start = process_start if process_start is not None else time.perf_counter()
    app = QApplication.instance() or QApplication(sys.argv)

    theme = get_theme_manager().get_current_theme()
    accommodations = _accommodations_in_effect()

    window = QMainWindow()
    window.setWindowTitle("Phase 9 build gate — QWebEngineView")
    window.resize(*GATE_WINDOW_SIZE)

    view_created = time.perf_counter()
    view = QWebEngineView()
    window.setCentralWidget(view)

    def on_loaded(ok):
        # Re-render with the real load time now that there is one. The first
        # paint used "measuring…" because the number does not exist yet.
        view.setHtml(
            build_gate_html(
                theme,
                startup_seconds=view_created - start,
                load_seconds=time.perf_counter() - view_created,
                accommodations=accommodations,
            )
        )
        print(f"gate: loadFinished ok={ok}", flush=True)

    view.loadFinished.connect(on_loaded)
    view.setHtml(
        build_gate_html(
            theme,
            startup_seconds=view_created - start,
            load_seconds=None,
            accommodations=accommodations,
        )
    )

    window.show()
    window.raise_()
    window.activateWindow()
    return app.exec()
