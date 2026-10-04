# UI refresh quickfixes and verification — design

**Date:** 2026-10-04 · **Branch:** `dr/22-ui-refresh-quickfixes-verifying` · **Follows:** UI refresh phases 1–9
(#355–#364)

## 1. What the owner asked for

Four defects seen after the nine UI-refresh phases, and one verification pass:

1. Borders do not match between the page area (Setup/Results/…) and the chrome around it.
2. Checkboxes have an outside square.
3. Opening "Manage groups" or "New client" closes the open session.
4. Switching the theme does not feel like one change.
5. Verify the changes of phases 1–9 and stress-test the app for bugs and performance problems.

Success: each defect is gone and held by a test that fails without the fix; the verification pass has run, its
small findings are fixed in this PR and the rest are GitHub issues; the gate is green.

No mockup governs these fixes: they repair departures from the existing mockups in
`docs/design/ui-refresh/mockups/`. Nothing in `shared/` changes, so packing-tool needs no work.

## 2. What the code actually does (measured 2026-10-04)

All four were reproduced offscreen on this branch.

| # | Symptom | Root cause |
|---|---|---|
| 1a | A 1px strip of `surface` (white in light, `#1a1b1e` in dark) frames the page area on all four sides. | `main_tabs` is a `QTabWidget` with its tab bar hidden; the app sheet's `QTabWidget::pane { border: 1px … }` still draws. The page stack sits at (201, 49), one pixel inside `main_tabs` at (200, 48). |
| 1b | The rule under the sidebar header sits 4px above the rule under the command bar. | `gui/components/sidebar.py` fixes the header at 44px; `BAR_HEIGHT` in `gui/components/commandbar.py` is 48. |
| 1c | "Open recent" is a white box on the sunken bar. | `session_button` (a `QToolButton`) takes the app sheet's `surface` background; the bar gives it only a font. |
| 2 | Every checkbox cell in the Results table (header and rows) is drawn inside a rounded 1px box. | The select column's cell is classed `cell select`. Phase 5 added the kit dropdown class `.select` to `gui/web/kit.css` (border, radius, padding, `display: flex`). The cell is styled as a dropdown. |
| 2′ | Latent, same mechanism. | Cell classes are the raw column key. An additional column is keyed `extra:<field>`, so a field named `Tracking code` yields the class tokens `extra:Tracking` and `code`, and `.code` is a kit class. |
| 3 | The session closes on "New client…", "Manage groups…", "Refresh list", pin/unpin and move-to-group. | `CommandBar` re-emits `clientChanged` for the client it is already on: when `_on_row_activated` puts the box back after an action row, and when `set_clients_from` restores the selection after every refresh. `MainWindow.on_client_changed` then calls `_reset_session_state()`. |
| 4 | Sidebar and bar change colour first, the page a moment later. | `ThemeManager.set_theme` costs ~40 ms (79 widgets) and repaints the Qt chrome synchronously. Each web view repaints later, in its own process. Web views also have no backing colour, so Chromium's white shows wherever the page has not painted yet. |

## 3. Decisions

| Decision | Chosen | Why |
|---|---|---|
| Borders | Fix 1a, 1b, 1c | Owner, 2026-10-04. |
| Theme switch | Synchronised, no fade | Owner, 2026-10-04. A fade needs transitions or opacity, banned on both tiers (ADR 0016 §3, linted), and a snapshot overlay cannot draw above a web view on Windows (ADR 0007). |
| Verification findings | Fix small ones here, file the rest | Owner, 2026-10-04. |
| Cell classes | `col-<safe key>` for every column, not a one-off rename of `select` | Fixes 2 and 2′ at the one place both come from. |
| Where the pane fix lives | A scoped sheet on `main_tabs`, not `shared/theme.py` | The shared `QTabWidget::pane` rule is right for real tab widgets in both apps; only this hidden-tab-bar stack is wrong. |
| Stress harness | A script under `scripts/`, not a test | It measures; it does not gate. A slow, machine-dependent test in the gate would be flaky. |

## 4. The fixes

### 4.1 The session survives (defect 3)

`gui/components/commandbar.py`. The bar remembers the last client it announced (`_announced`, initially `""`).
`_on_client_changed` returns without emitting when the current client equals `_announced`; otherwise it records
the client and emits as today. `_restore_client` keeps its present meaning.

A programmatic `set_current_client()` to a *different* client still emits, as it does today: the test suite and
`MainWindow.on_client_changed` both rely on it.

Result: `clientChanged` means "the client changed". Picking an action row, refreshing the list, pinning, moving a
client to a group, cancelling or accepting either dialog, and re-picking the client already selected all leave
the session alone. Creating a client still switches to it (a different client).

### 4.2 The seams (defect 1)

- **1a** — `gui/ui_manager.py::_create_tabs`: `main_tabs` gets the object name `PageStack` and the sheet
  `#PageStack::pane { border: 0; }`. No colour is involved, so nothing needs re-running on a theme change.
- **1b** — `gui/components/sidebar.py`: the header's height is `BAR_HEIGHT`, imported from
  `gui/components/commandbar.py`, not the literal 44. The two rules then share y = 47.
- **1c** — `gui/components/commandbar.py::_style_labels`: `session_button`'s sheet becomes
  `QToolButton { <caption font> background-color: transparent; border: 1px solid transparent;
  border-radius: <radius_md>px; padding: 0 8px; } QToolButton:hover { background-color: <hover>; }`,
  the same recipe the sidebar's tool buttons use. `_style_labels` already re-runs on a theme change.

### 4.3 Column cells get their own class namespace (defect 2)

`gui/web/results.js`: one helper,

```js
// A column's CSS class. Never the bare key: `select` is a kit class, and an
// additional column's key carries the profile's own field name.
function colClass(key) { return "col-" + String(key).replace(/[^A-Za-z0-9_-]/g, "-"); }
```

used wherever a header or row cell builds its `className` from `col.key` (`renderHeader`, `cellElement`). The
click handler's `closest(".cell.select")` becomes `closest(".cell.col-select")`. `gui/web/results.css` and the
tests follow: `.cell.select` → `.cell.col-select`, `.head.select` → `.head.col-select`, `.cell.status` →
`.cell.col-status`, `.cell.order` → `.cell.col-order`, `.head.value` → `.head.col-value`, and every other
`.cell.<key>` / `.head.<key>` selector, including those in `tests/`. State classes (`head`, `num`, `mono`,
`missing`, `sorted`, `unmapped`, `filler`) are not column keys and keep their names.

`columns.js`, `bulk.js` and `pane.js` are checked for the same pattern and changed only if they build a class
from a column key.

### 4.4 The theme changes in one step (defect 4)

Order of events today: Qt chrome, then pages. New order: pages, then Qt chrome once the visible page has
painted.

- **`gui/theme_manager.py`** — `ThemeManager.tokens_for(name)` returns the font-layered tokens for a theme
  name; `get_current_theme()` calls it.
- **`gui/web_page.py`**
  - `PageBridge` gains a slot `themeApplied()` (called by the page) that emits a Python signal `themePainted`.
  - `mount_page` records the bridge and its view in a module-level `weakref.WeakKeyDictionary` (bridge → view).
  - `_push_theme` also sets the view's backing colour: `view.page().setBackgroundColor(QColor(tokens.surface_sunken))`
    — the plane every page paints (`kit.css` body). No white shows before a page's first paint or during a
    resize.
  - `switch_theme(name)`:
    1. Same theme as the current one: return.
    2. A switch already waiting: finish it now, then continue.
    3. Collect the bridges whose view `isVisible()`. None: `get_theme_manager().set_theme(name)` and return.
    4. Push `theme_css_vars(manager.tokens_for(name))` to each of them with `set_theme_css`.
    5. When every one of them has emitted `themePainted`, or after `THEME_ACK_TIMEOUT_MS = 150`, whichever
       comes first, call `set_theme(name)` exactly once. That repaints the chrome and pushes the same CSS to
       the hidden pages (a no-op for the visible ones: `set_theme_css` ignores an unchanged value).
- **`gui/ui_manager.py::_wire_sidebar`** — `themeRequested` calls `switch_theme(name)`.
- **Every page script** (`setup.js`, `results.js`, `browse.js`, `logs.js`, `tools.js`, `settings.js`) — the
  `themeCssChanged` handler, after writing the variables, acknowledges once the frame is on screen:
  `requestAnimationFrame(() => requestAnimationFrame(() => bridge.themeApplied()));`. Two frames, because the
  first callback runs before that frame is painted. Not on the initial load, only in the change handler.

`ThemeManager.set_theme`, `toggle_theme` and `set_density` keep their behaviour; anything that calls them
directly still works, just without the synchronisation. The sidebar toggle is the only theme switch in the UI.

The fallback is the error handling: a page that never acknowledges (hidden mid-switch, crashed renderer,
missing handler) costs 150 ms, never a stuck theme.

## 5. Verification and stress pass (item 5)

### 5.1 Render sweep

A throwaway render script (not committed) grabs every screen in both themes at 1280×860 with a real
`MainWindow` on a temp server path: Setup (no client, no session, files loaded), Results (with orders, a row
selected, the pane open), Browse (empty, with sessions), Logs, Tools (no session, session open), every Client
settings section, and the three Qt dialogs (New client, Manage groups, report selection). Each PNG is looked at
and compared with its mockup. The fixed states are saved to `docs/design/ui-refresh/renders/quickfixes/`,
following the per-phase precedent.

Checked on every render: the seams of §2 are gone; no kit class leaks onto a page element; no white backing;
light and dark both hold.

### 5.2 Stress script

`scripts/stress_ui.py`, kept in the repo, run by hand with `.venv/bin/python scripts/stress_ui.py`. Offscreen,
temp server path, never writes the real `QSettings` theme preference. It prints one markdown table (scenario,
iterations, median and worst time, widget count before/after, RSS before/after) and exits non-zero on a Python
exception or a JavaScript error (`window.onerror` collected per page).

| Scenario | Load |
|---|---|
| Results at size | 10 000 orders (~25 000 lines) pushed with `set_orders`; time to push, time to first rows |
| Results interaction | select all, clear, sort two columns, type a filter |
| Theme switching | 100 toggles through `switch_theme`, Results visible |
| Client switching | 50 switches between two clients, a session open on one |
| Session loop | 30 × create session → reset |
| Log flood | 20 000 entries appended while Logs is visible |
| Settings window | 20 × open → close |
| Browse at size | 500 sessions listed |

What counts as a finding: an exception or JS error; widget count or RSS that grows with iterations (a leak);
a single interaction over 200 ms on the dev VM; anything visibly wrong in a render.

### 5.3 What happens to findings

- **Small** — fixed in this PR, each with a test: at most about 30 changed lines, no new design decision, no
  `shared/` change that packing-tool would have to follow.
- **Everything else** — a GitHub issue on `cognitiveghost/shopify-fulfillment-tool` with the reproduction and
  the measurement.
- The PR body carries the stress table and a findings list (fixed here / issue number).

## 6. Testing

Seams, each with a test that fails before its fix:

| Fix | Seam | Test |
|---|---|---|
| 4.1 | `CommandBar` | No `clientChanged` after an action row is activated; none after `set_clients_from` with the same client selected; one when the client really changes. |
| 4.1 | `MainWindow` | With a session open (`session_path` set), `client_directory.loaded` re-emitted and each action row activated leave `session_path` and `analysis_results_df` untouched. |
| 4.2 | `MainWindow` render | The page stack's top-left equals `main_tabs`'s top-left; `sidebar.header.height() == BAR_HEIGHT`; `session_button`'s grabbed corner pixel is the bar's `surface_sunken`. |
| 4.3 | Results page | The select cell's computed `border-top-width` is `0px` and its `display` is not `flex`; an additional column named `Tracking code` yields exactly one `col-` class and no `code` class. |
| 4.3 | Static | No `col-…` class and no page-local cell class equals a class defined in `kit.css` (a guard over `results.js`/`results.css`). |
| 4.4 | `gui/web_page.py` | With a visible page: after `switch_theme("dark")` the bridge's `themeCss` is the dark CSS while the manager still reports light; emitting `themePainted` flips the manager. With no ack it flips after the timeout. With no visible page it flips at once. A second switch during the wait ends on the last theme asked for. |
| 4.4 | Each page | Changing `themeCss` makes the page call `themeApplied` (one parametrised test over the six pages). |
| 4.4 | `mount_page` | The page's `backgroundColor()` is the theme's `surface_sunken`, and follows a switch. |

Gate: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`, plus `ruff check .`.

## 7. Out of scope

- A fade or any other animation (ADR 0016).
- Restyling the Qt dialogs to the web kit; they move or go when their screens reach the web tier.
- The disabled-checkbox dashed box and the Qt `QCheckBox` indicator: looked at, not what the owner meant.
- The double config load right after creating a client (`clientCreated` and the bar both announce it): it
  predates the refresh and costs one extra read.
- Synchronising a density change; only the theme toggle was reported.
