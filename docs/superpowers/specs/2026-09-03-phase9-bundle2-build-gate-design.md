# Bundle 2 — BUILD GATE: prove Chromium survives the frozen build

**Date:** 2026-09-03
**Roadmap:** `docs/superpowers/plans/2026-09-03-phase9-roadmap.md` § Track V / 9.10
**Todoist:** Bundle 2 `6hQXj6CGvcxg63VV`, item 9.10 `6hQVhmcX2gh4v75V`
**Classification:** spike. The output is an answer, not a feature.

This gates all of Track W. If it fails, Bundles 11–14 do not start and the Qt
fallback becomes a live question for the user.

---

## Two premises in the brief are wrong

Both were checked against the installed toolchain before this spec was written.
Neither changes the gate's purpose; both make it smaller.

### 1. There is no `PySide6-QtWebEngine` package to add

That name is the PyQt5 convention (`PyQtWebEngine`). PySide6 ships QtWebEngine
inside **`PySide6-Addons`**, which the `PySide6` metapackage already depends on.
The repo's existing `PySide6>=6.7.0` line therefore already installs it — in the
dev venv, in CI, and on the Windows build runner:

```
PySide6            6.11.1
PySide6_Essentials 6.11.1
PySide6_Addons     6.11.1     <- QtWebEngine lives here
QtWebEngineWidgets: IMPORTABLE
```

**`requirements.txt` needs no new dependency.** It gets a comment instead, so
that a future size-trimming pass does not swap the metapackage for
`PySide6-Essentials` and silently remove the web tier.

### 2. PyInstaller already collects `QtWebEngineProcess.exe`

`PyInstaller/hooks/hook-PySide6.QtWebEngineCore.py` calls
`pyside6_library_info.collect_qtwebengine_files()`, whose docstring scope is
"helper process executable, translations, and resources", and adds
`PySide6.QtPrintSupport` as a hidden import. It refuses outright on Qt < 6.2.2
rather than producing a defunct build.

So the collection is upstream's job and it is already done. **Start with zero
new PyInstaller flags.** Add flags only if an actual build fails, and record
which ones were needed.

What is genuinely unproven — and what this gate buys — is everything after the
build succeeds: that the exe launches, that Chromium renders **over RDP** where
there is no GPU, and what it costs in bytes and in seconds.

---

## The real risks, in the order they will bite

1. **RDP rendering.** The likeliest failure. Chromium initialises GPU
   compositing and there is no GPU on an RDP session; the usual symptom is a
   white or black view in a window that otherwise works. Known accommodations
   are `QTWEBENGINE_CHROMIUM_FLAGS=--disable-gpu` and, separately,
   `QTWEBENGINE_DISABLE_SANDBOX=1` for a frozen helper process.
2. **Size.** Measured in the dev venv: `libQt6WebEngineCore` 195 MB, resources
   25 MB, `qtwebengine_locales` 44 MB — **265 MB** on Linux. Windows will differ
   but is the same order. The app ships as a zip to warehouse PCs over a file
   share, so this is an operational cost, not a footnote.
3. **Startup.** Both the cold-start cost of a much larger `--onedir` folder
   (file scanning, AV) and the cost of spawning the Chromium helper the first
   time a view is constructed.
4. **Getting a build at all.** The `build` job is `if: github.event_name ==
   'release'`, so no branch or PR produces an exe today.

Only #4 is fully solvable from Linux. The rest need a human on Windows.

---

## What gets built

Five small pieces. Nothing else — no document, no styling, no bridge.

### A. The probe window — `gui/webengine_gate.py` (throwaway)

A `QMainWindow` sized 1366×768 containing one `QWebEngineView` showing a page
built from the live theme's `surface`, `surface_raised`, `text`, `border`,
`accent_fill` and `font_family`. Themed, so the page proves colours reach the
view; hardcoded substitution, because `theme_css_vars()` is 9.11 and does not
exist yet. This module is **deleted when the gate closes** — it is scaffolding,
not the beginning of Track W.

**The page displays its own measurements.** The frozen build is `--windowed`,
so there is no console on Windows: anything printed to stdout is lost. The
numbers must be on screen where a human over RDP can read and screenshot them,
and in the log file. The page renders:

- Qt and Chromium versions
- seconds from process start to the probe window being shown
- seconds from `QWebEngineView` construction to `loadFinished`
- which of the two environment accommodations were in effect

Reached by `gui_main.py --webengine-gate`, a branch inside `main()`. A
function-level `from gui.webengine_gate import run_gate` is still visible to
PyInstaller's bytecode analysis, so the import pulls Chromium into the bundle
exactly as a production import would. One exe proves both halves: that the app
still starts normally with Chromium bundled, and that the view renders.

### B. Startup timing in `gui_main.py` (kept)

`time.perf_counter()` at module import, logged as a duration when the window is
shown. Three lines, useful permanently, and the only way the "before and after"
number is anything better than a stopwatch.

### C. A Windows build from a branch (kept)

The `build` job's condition gains a labelled-PR case, and a non-release run
uploads the dist through `actions/upload-artifact` instead of attaching it to a
release. The repo is **public**, so Windows runner minutes are free and the only
reason to gate it is wall-clock, which one label handles.

Deliberately **not** `workflow_dispatch`: that trigger only becomes dispatchable
once it is on the default branch, which is precisely what has not happened yet.
It would be dead until the merge it is meant to precede.

### D. Size on record (kept)

One `pwsh` step printing the dist folder's total size. "The cost is on record"
should not depend on somebody remembering to right-click a folder.

### E. A guard test — `tests/test_webengine_available.py` (kept)

`importlib.util.find_spec("PySide6.QtWebEngineWidgets")` is not `None`. It uses
`find_spec` rather than an import on purpose: importing loads
`libQt6WebEngineCore`, which pulls NSS and other libraries the Ubuntu CI image
does not install, and the thing worth guarding is packaging, not runtime.

No headless WebEngine render test. Making QtWebEngine run in the CI container is
a day of yak-shaving that answers a different question than the one this gate
asks, which is about Windows over RDP.

---

## Measuring before and after

The decision-relevant split is measured by the gate build itself, from B and the
probe's own readout:

- **before** — time to the main window with Chromium bundled but never imported
- **after** — that, plus the cost of constructing the view and loading a page

The one number this cannot produce is cold start from the file share with 265 MB
more on disk. That needs the current production exe as a baseline, and it has no
instrumentation, so it is a stopwatch comparison the operator makes once. Stated
here so it is not mistaken for rigour it does not have.

---

## Three outcomes, decided in advance

- **PASS** — the window opens over RDP at 1366×768 and the page renders themed
  with no environment flags. Track W is unblocked.
- **PASS WITH CAVEAT** — it renders only with `--disable-gpu` and/or the sandbox
  disabled. Still a pass: these are ordinary accommodations for RDP and VDI.
  Record exactly which were needed. They must then be set **before any Qt import**
  in `gui_main.py`, which is a constraint on Track W and earns an ADR at that
  point. Disabling the Chromium sandbox is worth the user's explicit attention
  even though the tier only ever renders a local page.
- **FAIL** — no combination renders, or no working exe is produced. Stop and
  report. Do not route around it, do not start Track W, and put the Qt fallback
  to the user as a live question.

---

## Open question for the user, at merge time — not now

**If the gate passes, does this branch merge?**

Merging it means every release from here on is ~200 MB larger, for a capability
nothing uses until Bundle 11. Not merging means carrying a divergent branch
across Bundles 3–10 and rebasing it through the entire Qt track.

Recommendation: **merge it.** A gate whose result is not continuously re-proven
by CI decays into an assumption, which is the exact failure mode this item
exists to prevent. The size arrives whenever Track W ships; paying it early buys
eight bundles of certainty.

This is not a Stage A decision — it needs the gate's actual numbers to answer,
so it belongs to whoever reviews the result.

---

## Out of scope

- Trimming `qtwebengine_locales` (44 MB) or any other size work. Trimming while
  proving basic viability confounds the experiment. If size is the problem, that
  is a finding, and its own item.
- `theme_css_vars()`, the `QWebChannel` bridge, any part of the results
  document. Those are 9.11, 9.12 and Track W.
- `CONTEXT.md` changes. The gate introduces no domain term; **web tier** is
  already defined there and is used unchanged.
