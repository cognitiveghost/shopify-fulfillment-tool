"""THROWAWAY. The Phase 9 build gate (Bundle 2 / roadmap 9.10).

A window containing one QWebEngineView, reached by `gui_main.py
--webengine-gate`. It answers one question -- does Chromium survive
PyInstaller and render over RDP -- and is deleted once that question has an
answer. It is not the beginning of Track W.

The frozen build is --windowed, so Windows gives it no console and anything
printed to stdout is lost. Every measurement therefore goes two places: into
the page itself, where a human on an RDP session can read and screenshot it,
and into the log file under ~/Logs/ShopifyTool/, where it can be copy-pasted.
"""
import logging
import os
import sys
import time
from pathlib import Path

from PySide6 import __version__ as _PYSIDE_VERSION
from PySide6.QtCore import qVersion
from PySide6.QtWebEngineCore import qWebEngineChromiumVersion
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QMainWindow

from gui.theme_manager import get_theme_manager
from shared.logger import setup_logging

GATE_WINDOW_SIZE = (1366, 768)

QT_VERSION = f"{qVersion()} (PySide6 {_PYSIDE_VERSION})"
CHROMIUM_VERSION = qWebEngineChromiumVersion()


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
  /* Deliberately unsized -- Chromium's default h1 is fine. font_css() emits a
     QSS fragment in pt, which Chromium resolves as 1/72in rather than through
     Qt's logical-DPI path, so the tiers would disagree; and a literal size is
     banned under gui/ by tests/test_type_scale.py. Bridging the two properly
     is theme_css_vars(), which is 9.11. The spec's token list for this page
     is colours and font_family, not sizes. */
  h1 {{ margin: 0 0 24px; }}
  dl {{ display: grid; grid-template-columns: max-content 1fr; gap: 8px 24px; margin: 0; }}
  dt {{ color: {theme.text_secondary}; }}
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


def run_gate(process_start):
    """Show one QWebEngineView and report what it cost. Returns an exit code."""
    # The screenshot is the primary record, but a 1366x768 JPEG-compressed RDP
    # session is a poor medium for reading "2.47s" off. Log the same numbers
    # somewhere copy-pasteable. Home, not ProfileManager.base_path: the probe
    # must run on a box where the warehouse share is unreachable, and resolving
    # the share is a whole subsystem this gate is not testing.
    setup_logging("ShopifyTool", str(Path.home()))
    log = logging.getLogger(__name__)

    app = QApplication.instance() or QApplication(sys.argv)

    theme = get_theme_manager().get_current_theme()
    accommodations = _accommodations_in_effect()

    window = QMainWindow()
    window.setWindowTitle("Phase 9 build gate — QWebEngineView")
    window.resize(*GATE_WINDOW_SIZE)

    view = QWebEngineView()
    # After the constructor, not before: spawning the Chromium helper is part
    # of what "view to loaded" is supposed to be measuring.
    view_constructed = time.perf_counter()
    window.setCentralWidget(view)

    # Show before the first setHtml so "startup to window" is genuinely the
    # time to a window on screen, which is what the spec asks for.
    window.show()
    window.raise_()
    window.activateWindow()
    shown = time.perf_counter()

    def on_loaded(ok):
        # Disconnect FIRST. setHtml() below issues another load, which would
        # re-enter this handler indefinitely -- ~100 reloads a second, with
        # "view to loaded" climbing without bound, so the operator would
        # screenshot whatever the clock happened to read. The second render
        # is the one that gets screenshotted; it has to settle.
        view.loadFinished.disconnect(on_loaded)
        load_seconds = time.perf_counter() - view_constructed
        view.setHtml(
            build_gate_html(
                theme,
                startup_seconds=shown - process_start,
                load_seconds=load_seconds,
                accommodations=accommodations,
            )
        )
        log.info(
            "gate: ok=%s qt=%s chromium=%s startup=%.2fs view_to_loaded=%.2fs "
            "accommodations=%s",
            ok,
            QT_VERSION,
            CHROMIUM_VERSION,
            shown - process_start,
            load_seconds,
            accommodations or "none needed",
        )

    view.loadFinished.connect(on_loaded)
    view.setHtml(
        build_gate_html(
            theme,
            startup_seconds=shown - process_start,
            load_seconds=None,
            accommodations=accommodations,
        )
    )

    return app.exec()
