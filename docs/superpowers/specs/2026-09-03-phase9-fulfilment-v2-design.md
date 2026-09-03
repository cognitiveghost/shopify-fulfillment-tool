# Phase 9 — Fulfilment System v2

**Date:** 2026-09-03
**Status:** design accepted, roadmap written, nothing implemented
**Source:** Claude Design project *Fulfilment System v2*
`75385f2c-4be2-446c-8e9d-bf90ee063ff7` — five sessions, 35 artboards, run
2026-09-02/03 from the mockup-chain runbook (Todoist `6hPqxm7gPmXfqMQV`).

Read this before the artboards. The canvas is the drawing; this is what
survives contact with the repo.

---

## 1. Why this phase exists

Phase 8 (`8.1`→`8.8b`, PRs #296–#308, all merged) rebuilt the design system
bottom-up: tokens, components, the rail-and-command-bar shell, and an
order-level Analysis Results table. The v2 mockup chain was commissioned
**after** 8.8b landed, deliberately, because the Analysis Results rework
solved the data-model fault (a row is an order, not a SKU line) without
solving the screen. v2 changes the angle rather than patching the result.

That framing is load-bearing for everything below: where v2 and shipped code
disagree about Analysis Results, **v2 wins and the shipped screen is
replaced**, not merged with.

## 2. The gap between what the mockups assume and what ships

The artboards read the shipped code accurately in almost every place — they
name real modules, real line numbers and real faults. One assumption is
wrong, and it is the expensive one.

**The mockups treat `QWebEngineView` as already shipped. It is not.**

| Assumption in the artboards | Actual state of `main` |
|---|---|
| "the shipped `QWebEngineView` Analysis Results document" (W3) | zero `QWebEngineView` references in the repo |
| "Info › Statistics is TIER WEB" (session 4 contract) | it is `_create_statistics_subtab`, Qt stat cards, `gui/ui_manager.py:1760` |
| `shopify_tool/templates/` holds the results document | it holds `barcode_label/`, `qr_label/`, `assets/` — label rendering only |
| PySide6-WebEngine available | not in `requirements.txt`, not installed |

So TIER WEB is **greenfield**, not a restyle. Three further facts the
artboards state as Qt limitations are already solved here, and the roadmap
must not spend a task re-solving them:

- **Tabular figures.** `gui/theme_manager.py:250` already calls
  `font.setFeature(QFont.Tag("tnum"), 1)`, and `requirements.txt` pins
  `PySide6>=6.7` in a comment naming that as the reason. F2 reaches the same
  conclusion independently; the implementation just already exists.
- **Sticky table headers.** `QHeaderView` does this natively.
- **312-row scrolling.** `QTableView` over a model handles 312 rows without
  virtualisation; 200-row tables already ship.

**Decision (user, 2026-09-03): build TIER WEB as designed anyway.** The
rationale is not that Qt cannot draw Analysis Results — it is that the Qt
screen was rebuilt once already and the result is what v2 exists to replace.
The web tier is bought for the rewrite, not for the four CSS properties.

The consequence is that the web tier's true cost has to be **named and
sequenced first**, because the artboards cost it at zero. Section 4 does that.

## 3. Decisions

Three were the user's, taken 2026-09-03. The rest are calls made here against
the artboards; each names what it overrides.

### 3.1 User decisions

| # | Decision | Consequence |
|---|---|---|
| D-1 | **Keep the two-tier substrate.** Analysis Results becomes a `QWebEngineView`. | Track W cannot start until Track V (section 4) proves the build. The merged 8.8a/8.8b Qt results screen is superseded, not extended. |
| D-2 | **Delete Info › Statistics (D3).** | `_create_statistics_subtab` and its stat-card page go. `shared/stats_manager.py` and `global_stats.json` stay **write-only** — the monthly export is unaffected. Destination renames `Info` → `Logs`. |
| D-3 | **Ship the full F0 + F0b token retune.** | 16 light values, 6 dark. One dataclass edit; ~180 call sites untouched. `tests/test_theme_contrast.py` fixtures move in the same commit — the test is the contract, not the artboard. |

### 3.2 Calls made here

- **The F5 three-channel status mechanism supersedes the locked contract's
  "tint carries authorship" line.** Colour = role, fill = live vs resting,
  mark = person (solid) vs system (hollow). F5 argues this correctly: tint
  cannot carry authorship *and* urgency, and forcing one silhouette per author
  is what made the app read as inconsistent. All five sessions after F5 drew
  against the new wording, so the artboards are already consistent with it.
- **F4's CONTRACT CHALLENGE is accepted.** `SelectionRingDelegate` (or an
  extension of `StatusEdgeDelegate`) paints a row-scoped ring. `QTableView::item`
  styles cells, so a QSS ring repeats at every column boundary. ~40 lines, and
  the precedent already ships twice.
- **W7's CONTRACT CHALLENGE is rejected; take the drawn fallback.** Two
  simultaneous primaries on Results is not worth two accent fills 44px apart.
  W7 as drawn needs no code beyond the bar itself, which the challenge board
  concedes.
- **D1 Proposal 3 ("Last touched — who, where, when") is dropped.** It is the
  only item in the set with a cross-repo data cost (Packing Tool must stamp the
  last writer on the session index), and the artboard itself says to reject it
  first if the three proposals are too many. Proposals 1 (Age) and 2 (Blocked
  count) ship.
- **F4's frozen first column is dropped.** It exists to survive a 23-column
  table; W3 cuts the table to 9 columns at 866px. Nothing needs freezing, and
  a second synchronised `QTableView` is a permanent maintenance cost bought for
  a problem this phase deletes.
- **`QWebChannel` is added to the plan as its own task.** The artboards do not
  mention it, and it is the largest single omission — see 4.2.

## 4. What the web tier actually costs

The artboards specify the *document*. They do not specify the *platform under
it*, and that platform is five pieces of work that must land before W3 can be
drawn at all.

### 4.1 The build gate (do this first, alone)

`PySide6-QtWebEngine` adds Chromium — roughly 130 MB and a separate
`QTWebEngineProcess.exe` that PyInstaller has to collect. This repo has already
been forced once from `--onefile` to `--onedir` because WeasyPrint's GTK DLLs
could not self-extract reliably (`28eb210`). Chromium is a harder case than
GTK, and the app also runs over RDP on 1366×768 desks.

**This is a spike, and it gates the whole W track.** If the frozen build cannot
launch a `QWebEngineView` on a warehouse PC, every W task is stranded, so it is
cheaper to find out in one session than after four.

Done when: a `--onedir` build produced by the existing CI spec launches a
window containing a `QWebEngineView` that renders a themed page, on Windows,
over RDP, at 1366×768.

### 4.2 The bridge (the omission)

Analysis Results is not a report. It carries selection, sort, filter, a column
manager, per-order actions, bulk actions, and an Undo that calls
`undo_manager.py`. Every one of those crosses the Qt↔JS boundary, so the web
tier needs a real protocol:

- **Out:** the order-level frame as JSON (312 orders, SKU lines nested),
  plus the active theme's CSS custom properties.
- **In:** selection changes, sort/filter state, per-order and bulk action
  invocations, column config writes.

`QWebChannel` is the Qt-native answer and it is the seam that decides whether
this tier is maintainable. Design it as one object with a named method per
message, not as a string-passing hatch.

### 4.3 The other three

- **`theme_css_vars(theme)`** beside `build_stylesheet(theme)` in
  `shared/theme.py`. Field names with underscores → hyphens, mechanically, so a
  new token needs no second registration site. It asserts it emitted every name
  in `_COLOR_FIELDS` minus `_ALIAS_PAIRS`, which is what stops a token silently
  missing the web tier. The ten frozen aliases are **not** exported — a web
  asset has no legacy call sites to protect.
- **`shared/style_lint.py` extended to `.css` and `.html`.** No hex may be
  written into a web asset. Today the linter sees neither extension, so the two
  renderers would drift apart within a month.
- **The font seam.** `templates/assets/fonts/` ships JetBrains Mono while the Qt
  side uses Consolas. That is a live seam and it shows on every SKU. Pick
  Consolas — a Windows warehouse PC already has it.

### 4.4 Banned in the web tier

`box-shadow`, gradients, transitions, transforms, container opacity, and any
font size in px. CSS allows them; each one is a visible seam. The linter
enforces this alongside the hex rule.

## 5. What we implement, what it needs, what we drop

### 5.1 Implementable directly — Qt, against components that already ship

Roughly 70% of the artboards, and none of it waits on the web tier. This is
where the roadmap starts, so the phase delivers visible value before the
Chromium question is answered.

| Artboards | What lands |
|---|---|
| F0, F0b | 22 token values; contrast fixtures updated in the same commit |
| F1 | Border subtraction: `Card` → `QFrame.NoFrame`, five `build_stylesheet` rules drop `border: 1px`; `QGroupBox` radius folds onto `radius_md` |
| F2 | `QPushButton`'s hardcoded `font-size: 10pt` → `font_css("body")` |
| F3 | Toggle switch (the one new control), focus-on-primary exception, spin box drawn at its real 35px |
| F4 | `SelectionRingDelegate`, zebra stays off, sort caret only on sorted/hovered columns |
| F5 | `StatusChip` gains `live` and `manual` flags; `StatusDot` survives as the chip's mark |
| F7 | `StatePanel` — four constructors, one widget, replaces per-screen invention |
| S1–S4 | Shell measurements, command bar's four states, `OverflowMenu`, rail footer deleted, first run |
| W1, W1b, W2 | Setup as one card and three steps, `RadioCard`, drop targets, recent-sessions strip killed |
| D1, D2 | Session row glyph channel, comment column, Age + Blocked, needs-attention grouping, two empty states |
| D3 | Statistics deleted, `Info` → `Logs` |
| D4 | `LogViewer` — one widget replacing `activity_log_table` + `execution_log_edit`; dead `gui/log_viewer.py` deleted with it |
| D5 | Tools' inner `QTabWidget` deleted, two cards, print options folded |
| G1–G3 | Settings single-write model, Reports list+editor, `Toast` + `ConfirmDialog` and the 249-message-box triage |

### 5.2 Needs building first — the platform under TIER WEB

Section 4, in order: build gate → `theme_css_vars` + lint + font → bridge.
Three tasks, and the first is a gate.

### 5.3 Dropped

| Dropped | Why |
|---|---|
| D1 Proposal 3 — Last touched | Only cross-repo data cost in the set; the artboard says reject it first |
| F4 frozen first column | Bought for a 23-column table that W3 deletes |
| W7 two-primaries challenge | Fallback is drawn, needs no code, and the rule is worth more |
| D6 | Already satisfied — D2, D4 and D5 are drawn full-window |
| Statistics charts | D-2 |

### 5.4 Real bugs the artboards surfaced

Not design work; they need an owner and a small PR each.

- `AddProductDialog` hard-codes its low-stock threshold at `5` instead of
  reading `low_stock_threshold`.
- **`SHORT ON STOCK` and `BLK` are the same number under two names.** Pick one
  in `session_lifecycle.py` before D1 Proposal 2 ships the column, or the two
  screens will disagree in public.
- `session_info.json` has no `blocked_orders` key — `actions_handler` computes
  `fulfillable_orders` at analysis time and throws the complement away. This
  **gates** D1 Proposal 2 and D2's needs-attention filter.
- `SetsPage` and `_ColumnConfigPage` self-save, so Cancel does not cancel them.
  G1 is the fix; it is listed here because it is a correctness fault, not a
  layout one.

## 6. Sequencing

Two tracks run independently until they meet at Results.

```
Track Q (Qt, no gate)          Track V (web platform)
  9.0  asset library             9.10 BUILD GATE — spike
  9.1  tokens                          |
  9.2  border discipline         9.11 theme_css_vars + lint + font
  9.3  status chip                     |
  9.4  selection ring            9.12 QWebChannel bridge
  9.5  controls                        |
  9.6  state panel                     v
  9.7  shell                     Track W (Results, web) 9.13 → 9.17
  9.8  overflow menu
  9.9  first run
  9.18 setup
  9.19 session browser  <- gated by blocked_orders (5.4)
  9.20 statistics deleted
  9.21 log viewer
  9.22 tools
  9.23 settings save model
  9.24 reports page
  9.25 toast + confirm
```

Track Q is ordered by dependency: tokens before anything that draws them,
status chip before the session row that paints it, state panel before the
screens that swap it in. Track V is strictly serial. Track W cannot start
until 9.12 lands.

## 7. The asset library

The user asked for a single library of assets. Most of it exists — and it
exists **twice**.

`gui/icons.py`, `gui/fonts.py` and `gui/assets/` are duplicated between
`shopify-fulfillment-tool` and `packing-tool`, byte-for-byte apart from one
icon. `gui/icons.py` is good code: it substitutes Lucide's `currentColor` in
the SVG source before handing it to `QSvgRenderer`, so glyphs recolour as
vectors and the frozen build never depends on Qt's `qsvg` plugin.

The work is consolidation, not invention:

1. Move `gui/icons.py`, `gui/fonts.py` and `gui/assets/` into `shared/`, which
   is the established cross-repo sync path (`scripts/sync_shared.py`, owned by
   `packing-tool`). One library, two apps.
2. Add the icons v2 needs and the repo lacks: `plus` (New session),
   `ellipsis-vertical` (overflow), plus the sub-control glyphs QSS reaches
   through `image:` — checkbox tick, radio dot, the sort caret's
   `::up-arrow`/`::down-arrow`, and the toggle switch's two states.
3. Expose the same SVG directory to the web tier so one glyph set serves both
   renderers, under the same rule as the tokens.
4. `tests/test_icon_usage_guard.py` and `tests/test_ui_assets.py` follow the
   move and keep guarding it.

D1's status glyphs (half-disc, check, bang, clock, slash) are **painted paths
in a delegate**, not SVGs — they must never depend on a font shipping `◐`.

## 8. Open, and who decides

- **Sets imports CSV straight to disk today.** Forcing it into the settings
  dialog's single write means holding an imported set list in memory until
  Save. Confirm that is acceptable for the largest client profile before 9.23.
- **Logs keeps Activity as a source for now.** If the activity log is only ever
  a filtered view of the execution log, the switch can go — needs one look at
  real data, not a design decision.
- **Toast over the web tier.** A Qt child window always paints above a
  `QWebEngineView`, so the Results page emits its own toast. Two
  implementations, one appearance; the F6 rule applies and the linter enforces
  it.
- **Print settings stay per-window**, restyled to the settings-page anatomy.
  The `QSettings` scope names stay as shipped.

## 9. What must not move

- **Token names and roles are frozen.** ~180 call sites read them by exact
  attribute name. Values moved in D-3; names did not.
- **The elevation ramp direction is frozen.** Light nests downward, dark
  upward.
- **`shared/` is owned by `packing-tool`.** Every `shared/` change is made
  there and arrives here through `scripts/sync_shared.py`. That includes the
  token retune and the asset-library move.
- **1366×768 is the design case**, not the degraded case.
- **Never commit to `main`.** Branch and PR, docs-only included.
