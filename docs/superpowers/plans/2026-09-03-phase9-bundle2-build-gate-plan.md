# Phase 9 Bundle 2 — Build Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a Windows `--onedir` build containing Chromium and a probe window that reports its own timings, so a human can answer whether `QWebEngineView` survives freezing and renders over RDP.

**Architecture:** Four independent pieces. A pure HTML builder plus a throwaway Qt probe window reached by an argv flag on the existing entry point; three lines of startup instrumentation kept permanently; a CI change that lets a labelled PR produce a Windows artifact; a guard test that the QtWebEngine module is present. Nothing imports QtWebEngine except the probe.

**Tech Stack:** PySide6 6.11 (`PySide6-Addons` supplies QtWebEngine), PyInstaller 6.x `--onedir --windowed`, GitHub Actions `windows-latest`, pytest.

**Spec:** `docs/superpowers/specs/2026-09-03-phase9-bundle2-build-gate-design.md`

## Global Constraints

- **Do not add any dependency to `requirements.txt`.** QtWebEngine ships in `PySide6-Addons`, already pulled in by the existing `PySide6>=6.7.0` line. Verified: `PySide6 6.11.1`, `PySide6_Addons 6.11.1`, `QtWebEngineWidgets` importable.
- **Do not add PyInstaller flags in the first attempt.** `PyInstaller/hooks/hook-PySide6.QtWebEngineCore.py` already calls `collect_qtwebengine_files()` for the helper process, translations and resources. Add flags only if a build actually fails, and record which.
- **No hardcoded colours.** Every colour in the probe page comes from theme tokens. Token names available and used here: `surface`, `surface_raised`, `text`, `border`, `accent_fill`, `font_family`.
- **`shared/` is not editable in this repo.** Nothing in this plan touches it.
- Python is not on `PATH`. Use `.venv/bin/python`, or `./scripts/run_tests.sh`. Run `./scripts/setup_venv.sh` once in this worktree first.
- Tests run as `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest`. Lint is `.venv/bin/ruff check . --exclude shared`.
- This is a **spike**. `gui/webengine_gate.py` is scaffolding and is deleted when the gate closes. Do not grow it toward Track W.

---

### Task 1: Guard that QtWebEngine is present, and say why in requirements.txt

**Files:**
- Create: `tests/test_webengine_available.py`
- Modify: `requirements.txt` (the `# GUI Framework` block, around the `PySide6>=6.7.0` line)

**Interfaces:**
- Consumes: nothing.
- Produces: nothing other tasks import. This is a standalone guard.

- [ ] **Step 1: Write the failing test**

Create `tests/test_webengine_available.py`:

```python
"""QtWebEngine must stay installed for the web tier (ADR 0001).

It arrives via PySide6-Addons, which the PySide6 metapackage depends on --
nothing names it directly, so a well-meaning switch to PySide6-Essentials
would remove it silently and only break the frozen Windows build.

find_spec, not import: importing loads libQt6WebEngineCore, which needs NSS
and friends that the Ubuntu CI image does not install. Packaging is what is
being guarded here, not runtime.
"""
import importlib.util


def test_qtwebengine_widgets_is_installed():
    assert importlib.util.find_spec("PySide6.QtWebEngineWidgets") is not None, (
        "PySide6.QtWebEngineWidgets is missing -- check that requirements.txt "
        "still installs the PySide6 metapackage and not PySide6-Essentials."
    )
```

- [ ] **Step 2: Run it and watch it pass, then prove it can fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_webengine_available.py -v`
Expected: PASS.

This test passes immediately — the dependency is already there. That makes it a regression guard rather than a red-green cycle, so prove it bites by temporarily changing the module name in the assertion to `PySide6.QtNotARealModule` and re-running.
Expected: FAIL with the assertion message. Change it back and re-run to confirm PASS.

- [ ] **Step 3: Add the comment to requirements.txt**

Append to the existing `PySide6>=6.7.0` comment block, keeping the established alignment style of that file:

```
PySide6>=6.7.0         # Qt6 for Python - cross-platform GUI framework
                       # 6.7 is the floor for QFont.setFeature(), which is the
                       # only working route to tabular numerals (Qt QSS has no
                       # font-variant-numeric property).
                       # Keep the METAPACKAGE, not PySide6-Essentials: QtWebEngine
                       # (the web tier, ADR 0001) ships in PySide6-Addons, which only
                       # the metapackage pulls in. tests/test_webengine_available.py
                       # guards this.
```

- [ ] **Step 4: Commit**

```bash
git add tests/test_webengine_available.py requirements.txt
git commit -m "Guard that QtWebEngine stays installed via the PySide6 metapackage"
```

---

### Task 2: Record startup duration

**Files:**
- Modify: `gui_main.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `gui_main._PROCESS_START` — a `float` from `time.perf_counter()`, read by Task 3's probe to report time-to-window.

No unit test. This is three lines whose only observable is a log line, and the existing CI smoke test (`CI=1 python run_dev.py`) already exercises the path it sits on. A test asserting a logger emitted a number would test the logging library.

- [ ] **Step 1: Add the timestamp at module import**

In `gui_main.py`, add `import time` to the existing stdlib import block (`os`, `sys`, `pathlib`), then immediately below the `__version__` line add:

```python
# Wall clock starts as early as the module loads -- everything below this,
# including the MainWindow import, is part of what the operator experiences
# as startup.
_PROCESS_START = time.perf_counter()
```

- [ ] **Step 2: Log the duration when the window is shown**

In `main()`, inside the `if QApplication.platformName() != "offscreen":` branch, after `window.activateWindow()` and before `sys.exit(app.exec())`:

```python
        logging.getLogger(__name__).info(
            "Startup complete in %.2fs", time.perf_counter() - _PROCESS_START
        )
```

Add `import logging` to the stdlib import block. Use the stdlib logger directly rather than `shared.logger` — `setup_logging()` has already run by this point via `MainWindow`, so a module logger inherits the configured handlers, and importing `shared.logger` here would add an import to the startup path being measured.

- [ ] **Step 3: Verify the app still starts**

Run: `CI=1 .venv/bin/python run_dev.py`
Expected: exits cleanly with "Offscreen application initialized successfully." (The offscreen branch does not log the duration — that is correct, there is no window to show.)

Run: `.venv/bin/ruff check . --exclude shared`
Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add gui_main.py
git commit -m "Log startup duration so the web tier's cost can be measured"
```

---

### Task 3: The probe window

**Files:**
- Create: `gui/webengine_gate.py`
- Create: `tests/test_webengine_gate.py`
- Modify: `gui_main.py` (inside `main()`)

**Interfaces:**
- Consumes: `gui_main._PROCESS_START` (float, from Task 2); `gui.theme_manager.get_theme_manager()`.
- Produces:
  - `build_gate_html(theme, *, startup_seconds: float, load_seconds: float | None, accommodations: list[str]) -> str` — pure, no Qt, the testable seam.
  - `run_gate() -> int` — builds the window, runs the event loop, returns an exit code for `sys.exit()`.

**The seam is `build_gate_html`.** It is a pure string function and that is where the tests go. `run_gate` constructs Qt objects and spawns Chromium; it is verified by a human on Windows, not by pytest. Do not try to unit-test the window.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_webengine_gate.py`:

```python
"""Tests for the build-gate probe page.

Only build_gate_html is tested. run_gate spawns a Chromium helper process
and is verified by a human running the frozen build on Windows -- that is
the entire point of the gate.
"""
import re

from gui.theme_manager import get_theme_manager
from gui.webengine_gate import build_gate_html


def _theme():
    return get_theme_manager().get_current_theme()


def test_page_uses_theme_colours_not_literals():
    theme = _theme()
    html = build_gate_html(theme, startup_seconds=1.5, load_seconds=0.25, accommodations=[])

    assert theme.surface in html
    assert theme.text in html
    assert theme.accent_fill in html

    # Every hex in the page must be one the theme handed us. A stray literal
    # here would make the page prove less than it claims: it would render
    # correctly even if theme values never reached the view.
    theme_hexes = {v.lower() for v in vars(theme).values() if isinstance(v, str) and v.startswith("#")}
    for found in re.findall(r"#[0-9a-fA-F]{3,8}", html):
        assert found.lower() in theme_hexes, f"hardcoded colour {found} in the gate page"


def test_page_reports_its_measurements():
    html = build_gate_html(_theme(), startup_seconds=2.5, load_seconds=0.75, accommodations=[])
    assert "2.50" in html
    assert "0.75" in html


def test_page_reports_a_pending_load_before_it_finishes():
    html = build_gate_html(_theme(), startup_seconds=2.5, load_seconds=None, accommodations=[])
    assert "2.50" in html
    assert "measuring" in html.lower()


def test_page_names_the_accommodations_in_effect():
    html = build_gate_html(
        _theme(), startup_seconds=1.0, load_seconds=0.1, accommodations=["--disable-gpu"]
    )
    assert "--disable-gpu" in html


def test_page_says_so_when_no_accommodation_was_needed():
    html = build_gate_html(_theme(), startup_seconds=1.0, load_seconds=0.1, accommodations=[])
    assert "none" in html.lower()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_webengine_gate.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'gui.webengine_gate'`.

- [ ] **Step 3: Write the page builder**

Create `gui/webengine_gate.py` with the imports and the pure function. Qt imports stay at module top — PyInstaller needs the `QtWebEngineWidgets` import statically visible in order to collect Chromium, which is the whole reason this file exists.

```python
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

from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QMainWindow

from gui.theme_manager import get_theme_manager

GATE_WINDOW_SIZE = (1366, 768)


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
  h1 {{ font-size: 20px; margin: 0 0 24px; }}
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
```

`QT_VERSION` and `CHROMIUM_VERSION` are module-level constants — define them above `build_gate_html`:

```python
from PySide6 import __version__ as _PYSIDE_VERSION
from PySide6.QtCore import qVersion

QT_VERSION = f"{qVersion()} (PySide6 {_PYSIDE_VERSION})"
CHROMIUM_VERSION = os.environ.get("QTWEBENGINE_CHROMIUM_VERSION", "bundled")
```

Chromium does not expose its version through a stable PySide6 API, so report the bundled marker rather than inventing one. The Qt version identifies the Chromium build well enough for the record.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_webengine_gate.py -v`
Expected: all five PASS.

If `test_page_uses_theme_colours_not_literals` fails on a colour you did not write, it is catching a real hardcoded value — fix the page, not the test.

- [ ] **Step 5: Write run_gate**

Append to `gui/webengine_gate.py`:

```python
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
```

`on_loaded` calls `setHtml` again, which fires `loadFinished` again — that second pass re-renders with a slightly larger load time and then settles, because the number it prints stops changing meaningfully. This is a throwaway probe and a re-entrant repaint costs nothing; do not add a guard flag for it unless the page visibly flickers, in which case disconnect the signal inside `on_loaded` before calling `setHtml`.

- [ ] **Step 6: Wire the flag into gui_main.py**

In `gui_main.py`, at the very top of `main()`, before the offscreen check:

```python
    if "--webengine-gate" in sys.argv:
        # Phase 9 build gate (roadmap 9.10). Deleted when the gate closes.
        # This import must stay statically visible to PyInstaller -- it is
        # what pulls Chromium into the frozen bundle.
        from gui.webengine_gate import run_gate

        sys.exit(run_gate(_PROCESS_START))
```

- [ ] **Step 7: Run it on Linux as a smoke check**

The Ubuntu dev machine has QtWebEngine installed, so the code path can be exercised before it ever reaches Windows.

Run: `.venv/bin/python gui_main.py --webengine-gate`
Expected: a 1366×768 window showing the themed card with real numbers.

If there is no display available in this session, try:
`QT_QPA_PLATFORM=offscreen QTWEBENGINE_CHROMIUM_FLAGS=--disable-gpu QTWEBENGINE_DISABLE_SANDBOX=1 timeout 30 .venv/bin/python gui_main.py --webengine-gate`
and look for `gate: loadFinished ok=True` on stdout before the timeout kills it.

**If neither works, do not spend the run fixing it.** Headless QtWebEngine on Linux is a different problem from frozen QtWebEngine on Windows, and only the second one is the gate. Note what happened in the handoff and move on — the unit tests and the Windows build are the checks that matter.

- [ ] **Step 8: Run the full suite and lint**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest`
Expected: all pass (1122 passed at Bundle 1's merge, plus the six added here).

Run: `.venv/bin/ruff check . --exclude shared`
Expected: clean.

- [ ] **Step 9: Commit**

```bash
git add gui/webengine_gate.py tests/test_webengine_gate.py gui_main.py
git commit -m "Add the throwaway QWebEngineView probe behind --webengine-gate"
```

---

### Task 4: Let a labelled PR produce a Windows build

**Files:**
- Modify: `.github/workflows/build_release.yml`

**Interfaces:**
- Consumes: nothing.
- Produces: a downloadable `ShopifyFulfillmentTool-gate` artifact on any PR carrying the `windows-build` label, plus a bundle-size line in the run summary.

No test. CI configuration is verified by the run it produces, which happens when the PR opens.

- [ ] **Step 1: Add `labeled` to the pull_request trigger**

**This step is load-bearing and easy to miss.** `on: pull_request` defaults to `opened, synchronize, reopened`. Adding a label to an existing PR fires none of those, so without this the label would do nothing and the build would never run — and the label cannot be applied before the PR exists.

In the `on:` block, change:

```yaml
  pull_request:
    branches:
      - main
```

to:

```yaml
  pull_request:
    branches:
      - main
    # 'labeled' so applying the windows-build label triggers a build on an
    # already-open PR. The default types do not include it.
    types: [opened, synchronize, reopened, labeled]
```

- [ ] **Step 2: Widen the build job's condition**

Change:

```yaml
    # Only run build job for releases, not on every push/pr
    if: github.event_name == 'release'
```

to:

```yaml
    # Releases always. PRs only when explicitly asked with the windows-build
    # label -- Windows-only questions (frozen bundles, RDP) cannot be answered
    # from the Ubuntu dev machine, and the repo is public so the minutes are free.
    if: >
      github.event_name == 'release' ||
      contains(github.event.pull_request.labels.*.name, 'windows-build')
```

- [ ] **Step 3: Put the bundle size on record**

After the existing "Bundle GTK DLLs" step and before the zip steps, add:

```yaml
      - name: Report bundle size
        shell: pwsh
        run: |
          $files = Get-ChildItem -Path "dist\ShopifyFulfillmentTool" -Recurse -File
          $mb = ($files | Measure-Object -Property Length -Sum).Sum / 1MB
          $line = "Frozen bundle: {0:N0} MB across {1:N0} files" -f $mb, $files.Count
          Write-Output $line
          Add-Content -Path $env:GITHUB_STEP_SUMMARY -Value $line
```

- [ ] **Step 4: Split the zip and upload steps by event**

Replace the existing "Zip artifact" and "Upload Release Asset" steps with four steps. The PR path needs its own zip name because `github.ref_name` on a pull_request is `<number>/merge`, and the slash is not legal in a filename.

```yaml
      - name: Zip artifact (release)
        if: github.event_name == 'release'
        shell: pwsh
        run: |
          Compress-Archive -Path "dist\ShopifyFulfillmentTool\*" -DestinationPath "ShopifyFulfillmentTool-v${{ github.ref_name }}.zip"

      - name: Zip artifact (PR gate build)
        if: github.event_name == 'pull_request'
        shell: pwsh
        run: |
          Compress-Archive -Path "dist\ShopifyFulfillmentTool\*" -DestinationPath "ShopifyFulfillmentTool-gate.zip"

      - name: Upload gate build
        if: github.event_name == 'pull_request'
        uses: actions/upload-artifact@v4
        with:
          name: ShopifyFulfillmentTool-gate
          path: ShopifyFulfillmentTool-gate.zip
          # Already a zip; re-compressing several hundred MB buys nothing.
          compression-level: 0

      - name: Upload Release Asset
        if: github.event_name == 'release'
        uses: softprops/action-gh-release@v2
        with:
          files: ShopifyFulfillmentTool-v${{ github.ref_name }}.zip
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

- [ ] **Step 5: Check the YAML parses**

Run: `.venv/bin/python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/build_release.yml')); print('ok')"`
Expected: `ok`. If PyYAML is not installed, skip — the push will surface a parse error as a failed workflow.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/build_release.yml
git commit -m "Build a Windows artifact from a PR carrying the windows-build label"
```

---

## Handing the gate to a human

Stage B cannot close this gate. Once the four tasks are committed and pushed:

1. Open the PR (Stage C).
2. Create the label if it does not exist, then apply it — this is what triggers the build:
   ```bash
   gh label create windows-build --description "Run the Windows build job on this PR" --color 1D76DB || true
   gh pr edit <N> --add-label windows-build
   ```
   (If `gh pr edit` fails with a Projects-classic GraphQL error, add the label with
   `gh api -X POST repos/cognitiveghost/shopify-fulfillment-tool/issues/<N>/labels -f labels[]=windows-build`.)
3. Confirm the build job ran and record the bundle-size line from the run summary.
4. Write the Windows checklist into the PR body for the user:
   - Download the `ShopifyFulfillmentTool-gate` artifact, unzip on the Windows box.
   - **Baseline:** launch `ShopifyFulfillmentTool.exe` normally, note the startup line in the log. Time the current production exe with a stopwatch for a cold-start comparison from the share.
   - **The gate:** over RDP at 1366×768, run `ShopifyFulfillmentTool.exe --webengine-gate`. Screenshot the window.
   - If the view is blank or black, retry with `set QTWEBENGINE_CHROMIUM_FLAGS=--disable-gpu`, then additionally `set QTWEBENGINE_DISABLE_SANDBOX=1`. Report which combination first worked — the page prints them back.
5. Record the outcome as PASS / PASS WITH CAVEAT / FAIL per the spec's three outcomes.

**On FAIL: stop and report.** Do not add flags, do not try alternative packagers, do not start Track W. Whether to fall back to Qt becomes the user's question, which is exactly what this item exists to buy early.

---

## Self-review

**Spec coverage.** Spec §A probe window → Task 3. §B startup timing → Task 2. §C branch build → Task 4. §D size on record → Task 4 step 3. §E guard test → Task 1. The requirements.txt comment correcting premise 1 → Task 1 step 3. Premise 2 (no PyInstaller flags) → Global Constraints. Three outcomes → the handoff section. The merge-time open question is deliberately not a task; it needs the gate's numbers.

**Placeholders.** None. Every code step carries the code.

**Type consistency.** `build_gate_html(theme, *, startup_seconds, load_seconds, accommodations)` is keyword-only after `theme` in Task 3 step 3, and every call site — the two in `run_gate` and the five in the tests — matches. `run_gate(process_start=None)` is called as `run_gate(_PROCESS_START)` from `gui_main.py`, and `_PROCESS_START` is the name Task 2 defines.
