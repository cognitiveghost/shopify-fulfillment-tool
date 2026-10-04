# UI refresh roadmap: from the approved mockups to the app

The owner approved the Claude Design mockups in [`mockups/`](mockups/) on 2026-09-30 (dev-runner run 35).
This file turns them into ten phases. Each phase is one task, one branch and one PR, and each gets its own
spec and plan at Stage A. The mockups are the brief for every phase (CLAUDE.md, "UI work: the mockup is the
brief").

**Decisions that hold for every phase (owner, 2026-09-30):**

- All five screens move to the web tier: Setup, Browse, Tools, Logs and Client settings. The shell (sidebar and
  command bar) stays Qt (ADR 0016).
- The palette is the mockup's, except where it falls below the WCAG floors in `shared/theme.py`. The floors win.
  Hairlines (card edges, dividers, the active item's edge) use `border_subtle`, and control edges use `border`
  (ADR 0018).
- The palette lives in `shared/theme.py`, so Packing Tool gets it at its next sync. The wide sidebar is opt-in,
  and Packing Tool keeps its 56px rail until a Packing Tool task opts in.
- Packing Tool screens are out of scope.

## How to read a mockup

Each `mockups/<screen>.html` is a Claude Design bundle. Open it in Chrome. The dark strip at the top switches
between the screen's states and themes, and the dark panel at the bottom holds the design notes, which are part
of the brief. `mockups/renders/<screen>.png` shows the default state at 1440×1000.

To read exact sizes and colours, unpack the bundle. `mockups/README.md` has the script.

## Phases

The order follows dependency: Phase 1 lays the tokens and the shell that every page sits in. Phase 2 builds
the web kit (the shared CSS) on the one screen that is already web. Each later phase reuses that kit. After
Phase 2, phases 3 to 6 are independent and can run in any order. 7 to 10 run in sequence.

| # | Task title (paste into Todoist) | Mockup | Depends on |
|---|---|---|---|
| 1 | UI refresh phase 1: shell sidebar and Polaris palette | `app-shell.html`, `component-sheet.html` (tokens) | none |
| 2 | UI refresh phase 2: Results to mockup and the web kit | `results.html`, `component-sheet.html` | 1 |
| 3 | UI refresh phase 3: move Setup to the web tier | `setup.html` | 2 |
| 4 | UI refresh phase 4: move Browse to the web tier | `browse.html` | 2 |
| 5 | UI refresh phase 5: move Tools to the web tier | `tools.html` | 2 |
| 6 | UI refresh phase 6: move Logs to the web tier | `logs.html` | 2 |
| 7 | UI refresh phase 7: Client settings on the web tier: frame, General, mappings | `client-settings.html` | 2 |
| 8 | UI refresh phase 8: Client settings on the web tier: Rules and Test rule | `client-settings.html` | 7 |
| 9 | UI refresh phase 9: Client settings on the web tier: Sets, Weight, Reports, Tag categories | `client-settings.html` (anatomy only) | 8 |
| 10 | UI refresh phase 10: Client settings on the web tier: the frame | `client-settings.html` | 9 |

### 1. Shell sidebar and Polaris palette (built in run 35)

Spec: `docs/superpowers/specs/2026-09-30-ui-refresh-phase1-shell-design.md`.
Plan: `docs/superpowers/plans/2026-09-30-ui-refresh-phase1-shell.md`.

The mockup palette in `shared/theme.py`, fitted to the contrast floors. Five new tokens. Disabled buttons that
look disabled. The 200px sidebar that collapses to a 56px rail: header, destinations, and a footer holding
Client settings, the theme switch and the connection block with Retry. The status bar is deleted. The
command-bar overflow is cut down to Server connection… and Keyboard shortcuts. Results stays greyed out until
the session has been analysed.

### 2. Results to mockup, and the web kit (built in run 38)

Spec: `docs/superpowers/specs/2026-10-01-ui-refresh-phase2-results-kit-design.md`.
Plan: `docs/superpowers/plans/2026-10-01-ui-refresh-phase2-results-kit.md`.

Built as listed below, with these differences. Two more tokens, `critical_fill` and `on_critical`, for the
popover's confirm button. The kit has a sheet, `tests/web/kit_sheet.html`, where the components no screen
draws yet (segmented control, banner, page header) are tested and rendered. Held is not a status: the owner
kept two. The column manager is the mockup's popover holding the full manager.

- Pulls the parts every web page shares (tokens as CSS variables, cards, buttons, badges, segmented control,
  inputs, toast, banner, state panel, page header) out of `gui/web/results.css` into `gui/web/kit.css`.
  Results links it first.
- Adds the `card_shadow`, `card_border`, `overlay_shadow`, `surface_inverse` and `on_inverse` tokens.
  `card_shadow` and `card_border` are CSS values, not hex, so they need their own path through
  `theme_css_vars` and `validate_theme`. `shared/style_lint.py` starts allowing `box-shadow` in web assets,
  but only as `var(--card_shadow)` or `var(--overlay_shadow)` (ADR 0016).
- Results changes: two cards only (the KPI strip, and one split card holding the table and the detail pane
  divided by one rule). "Value ready" collapses to a hint that links to column mapping. The detail pane
  collapses to a labelled rail. The bulk popover and Undo toasts follow the mockup's states.
- The session chip in the command bar (`2026-09-30_1  analysed 14:06`) is drawn on Results only.

### 3. Setup to the web tier (built in run 41)

Spec: `docs/superpowers/specs/2026-10-01-ui-refresh-phase3-setup-web-design.md`.
Plan: `docs/superpowers/plans/2026-10-01-ui-refresh-phase3-setup-web.md`.

Built as listed below, with these differences. The second view was measured on Linux only (about +31 MB and
at most +0.15 s); the Windows check over RDP is in the PR and is done before the release. With a client and
no session the page shows the "No session open" panel from `app-shell.html`, not live cards. The run names
four real steps and has no per-order count. The session chip is in the page head on Setup and in the bar on
every other screen, until Logs and Tools get their own page heads (Browse's mockup has none). One router sends a toast to the
web page that is showing.

- The second `QWebEngineView`, with its own bridge (`SetupBridge`). `gui/web_page.py` holds what every
  bridge shares.
- File cards (Missing / Loaded / Problem) with rows, orders or SKUs, and the detected delimiter. Folder merge,
  and problems inline with a link to the fix. The inventory memory switch with its explanation, and
  allocation strategy as radio cards. A fixed 300px Run summary column holding Run analysis. The run summary
  becomes the progress view with its step and Cancel.
- Picking files through the bridge (a Qt file dialog opened by a Slot) and dropping files onto the page.
- Command bar: New session is always shown as a secondary button and disabled with no client. While running,
  the bar shows the step count and step name and a disabled "Running…". Cancel is on the page.
- Kit: `.switch`, `.radio-card`, `.form-row`. Phase 5 reuses `.form-row`.

### 4. Browse to the web tier (built in run 44)

Spec: `docs/superpowers/specs/2026-10-01-ui-refresh-phase4-browse-web-design.md`.
Plan: `docs/superpowers/plans/2026-10-01-ui-refresh-phase4-browse-web.md`.

Built as listed below, with these differences. Export combined stock stays in the selection bar (two or more
checked). Column sorting is gone: rows are newest first inside each group. The auto-archive countdown moved
from the Age cell to its tooltip, with the age in the warning colour, and shows only on sessions the
automation will really archive. Packing counts packing lists. A session with no analysis opens on Setup.
Undo restores the status, the hand-set flag, the comment and the timestamps. A failed load is a panel in
the page. The session chip stays in the bar on Browse.

Status tabs with live counts (All, Active, Completed, Abandoned, Archived), search and Refresh on one row. The
"Needs attention" group first, with its reasons, then "Everything else". Eight display statuses as badges.
The Status menu offers the four a person can set and says what each one resolves to. Comment, and an Undo
toast for every change. The packing progress bar. The archived footer. Double-click opens the session.

### 5. Tools to the web tier (built in run 47)

Spec: `docs/superpowers/specs/2026-10-02-ui-refresh-phase5-tools-web-design.md`.
Plan: `docs/superpowers/plans/2026-10-02-ui-refresh-phase5-tools-web.md`.

Built as listed below, with these differences. Reference labels has the count and Cancel; Barcode labels
says "Writing 120 barcode labels…" with neither, because its render is one call. Print prints what exists:
Reference after a run, Barcode whenever the list's PDF is on disk. Barcode's output folder is fixed, with no
Change…. The print settings the mockup does not draw (target, label size, rotate, invert) sit behind a
"Label setup" fold under Print mode, and the printer menu shows in Driver mode too. The CSV problem reads
"This CSV has no usable rows": the file is read by column position, not by header. A PDF that cannot be
opened is flagged the same way. The session chip is in the page head on Tools, as on Setup. The kit gained
`.select`.

One card per tool (Reference labels, Barcode labels), each using the Setup row grid. A Driver / Raw ZPL switch
per card, saved per PC, with the printer target shown for Raw ZPL. With no session, one banner explains why
and the fields go quiet. While a tool runs, its footer shows the count and Cancel. When it finishes, a toast
names the folder and offers Open folder. A bad mapping CSV is flagged under its own field.

### 6. Logs to the web tier (built in run 50)

Spec: `docs/superpowers/specs/2026-10-02-ui-refresh-phase6-logs-web-design.md`.
Plan: `docs/superpowers/plans/2026-10-02-ui-refresh-phase6-logs-web.md`.

Built as listed below, with these differences. The counts are on Level only, as the mockup draws them. Save
as text opens a save dialog first, then the toast names the file. The count of entries below is of the
entries the filter shows. Any row with a traceback expands, whatever its level. The chevron swaps its glyph
and does not turn. The session chip stays in the bar on Logs, as on Browse: the mockup has no page head. No
Qt page is left, so the page area's inset rule is deleted.

Two single-select segmented controls, Source (All, Activity, Execution) and Level (All, Info, Warning,
Error), each with a live count. Search, and Save as text. Dense 26px rows, where only Warning and Error get a
tone. Source shows the last module segment, with the full path on hover. Error rows expand to show their
traceback. Follow tracks the scroll position: it turns off when the operator scrolls up and counts the entries
that arrive below. Entries stream through the bridge in batches, never one message per line.

### 7. Client settings on the web tier: frame, General, mappings (built in run 53)

Spec: `docs/superpowers/specs/2026-10-02-ui-refresh-phase7-settings-web-design.md`.
Plan: `docs/superpowers/plans/2026-10-02-ui-refresh-phase7-settings-web.md`.

Built as listed below, with these differences. The frame stays Qt, restyled to the mockup: a Qt page cannot
be drawn over a web view (ADR 0007), so a web frame could not hold the five pages that are still Qt. One
web view sits in the page area and draws General and both mappings; the frame moves in phase 10. The native
title bar stands in for the mockup's header strip. Save is live only when a page is unsaved, and the dialog
stays open after it ("Saved. Applies from the next analysis."). Columns are picked from the file loaded on
Setup, or one read in the dialog, never typed. Courier names is one row per pattern, under "Shipping method
contains". Stock mapping has no Additional columns card. The kit gained the page anatomy: `.card-head`,
`.card-row`, `.hint`, `.problem`, `.chip`.

The modal becomes a `QDialog` that hosts a web view. Search, the grouped left nav with an unsaved dot per page,
and a Cancel/Save footer that lists the unsaved pages. Each page has the same anatomy: a title and a subtitle,
then cards made of label/control rows with a hint under each control. General gets segmented delimiter
choices and the low-stock threshold. Orders mapping and Stock mapping follow the mockup's "Orders mapping"
state. The pages not ported yet keep their Qt widgets inside the same dialog until 8 and 9 land.

### 8. Client settings on the web tier: Rules and Test rule (built in run 56)

Spec: `docs/superpowers/specs/2026-10-02-ui-refresh-phase8-rules-web-design.md`.
Plan: `docs/superpowers/plans/2026-10-02-ui-refresh-phase8-rules-web.md`.

Built as listed below, with these differences. It fitted one PR. The mockup stops at "Edit": a rule's row
opens in place into an editor that is its summary with the words turned into controls. Article rules always
run before order rules, so a client with both sees two labelled groups, and up, down and the grip stop at a
group's edge. All three are off while a filter is on. A rule gained `enabled` (written only when it is off);
the analysis skips a rule that is off and Test still runs it. A PC still on an older version runs an off
rule, and any Settings save from it drops `enabled` and turns the rule back on for every PC: update every
PC before anyone uses the switch. A row that is off is drawn in secondary text,
not at 60% opacity (ADR 0001). Fields keep the analysis's own names, and the seven real actions get plain
labels; the status action is "Hold the order". Test runs on a worker over the whole analysis, dims the page
area only until phase 10, and says "No change" for an order the saved rules already changed. The date picker
and the suggestion lists are Chromium's own. `shared/theme.py` gained the `scrim` token and the
`--color-scheme` variable. The page has its own script, `gui/web/settings_rules.js`, and its values are in
`gui/settings/rules_state.py`.

The rule list with toggles and reordering. The empty state, which replaces "No rules defined". Test rule.
The Qt editor (`gui/settings/rules.py`, about 1,500 lines) and its Test dialog are deleted. The page joins
the settings document phase 7 built (`gui/web/settings.*`).

### 9. Client settings on the web tier: Sets, Weight, Reports, Tag categories (built in run 59)

Spec: `docs/superpowers/specs/2026-10-04-ui-refresh-phase9-settings-lists-design.md`.
Plan: `docs/superpowers/plans/2026-10-04-ui-refresh-phase9-settings-lists.md`.

Built as listed below, with these differences. It fitted one PR. Sets, Reports and Tag categories are
lists whose row opens in place, as Rules is; Weight is three cards, with products edited in the table, 200
rows at a time. A tag category's colour, order number and ID are no longer drawn: the colour is kept as
stored, the order is the list's (set by up and down, and Results' "+ Tag" menu now follows it), and a new
category's ID is made from its name. Reports reorder by up and down, not by dragging. Packing-list columns
are chips and print in the order they were added. CSV import and export go through the settings bridge to
a native file dialog, and the page has a toast. Several quiet data losses are now blocked and said: a set
renamed onto another set's SKU, a dimension that is not a number, a product SKU typed twice. The unsaved
poll is gone: every page reports its own edits. The standalone Tag Categories dialog, which had no caller,
is deleted. Also gone or changed (the spec's section 12 has the table): deleting a tag category asks nothing
(Cancel undoes it), Weight's Quick Add and Delete Selected are gone, a new set or product goes first in its
list, and Boxes has no search. Renders: `renders/phase9/`.

The mockup has no drawing of these pages. They follow the page anatomy from Phase 7, and the spec names each
place where it had to decide something the mockup does not show.

### 10. Client settings on the web tier: the frame

The nav, the search, the footer and the close guard move into the settings document, and the Qt frame goes.
It waits for 9: a Qt page cannot be drawn over a web view (ADR 0007), so the frame can be web only once no
Qt page is left inside it. The header strip the mockup draws stays out; the native title bar does that job.

## After the roadmap

- Re-evaluate an order's status when its short SKU is removed. The mockup's popover promises "becomes
  Fulfillable"; today the order stays Blocked until someone marks it fulfillable, and the popover says so.
  Stock-ledger work with its own spec.
- `gui/web/kit.css` moves to `shared/` when Packing Tool adopts it.
- Packing Tool adopts the wide sidebar and the web kit in its own tasks.
- Revisit this file whenever a phase changes the plan for the ones after it.
