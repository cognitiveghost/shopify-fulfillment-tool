# UI refresh phase 1: shell sidebar and Polaris palette

**Task:** dev-runner run 35, Todoist 6hfwmjHXG6mWpc9M: "i add mock up from claude design from our previous task
(its on desktop on fulfilment mock up folder), lets this time will plan tasks (you can create a tasks as phases)
for phase of developments".
**Path:** architectural. It re-colours both apps through `shared/`, changes the shell every screen sits in, and
sets the phases that follow.
**Mockup followed:** `docs/design/ui-refresh/mockups/app-shell.html` (sidebar, connection, overflow) and
`component-sheet.html` (tokens only). Departures are listed in §7.

## 1. What this task delivers

1. The approved mockups in the repo: `docs/design/ui-refresh/mockups/` (8 bundles, 8 renders, a README).
2. `docs/design/ui-refresh/roadmap.md`: nine phases, each one task, with a title ready to paste into Todoist.
   dev-runner cannot create Todoist tasks from Stage A, so the owner adds phases 2 to 9 from that table.
3. `docs/adr/0018-contrast-floors-outrank-the-mockup-palette.md`.
4. Phase 1 itself, built at Stages B and C from `docs/superpowers/plans/2026-09-30-ui-refresh-phase1-shell.md`.
   The rest of this spec describes it.

## 2. Owner's decisions (2026-09-30)

| Question | Answer |
|---|---|
| Which screens move to the web tier | All five (Setup, Browse, Tools, Logs, Client settings) |
| What this task builds | Roadmap + mockups in repo + Phase 1 |
| The 200px sidebar in `shared/navrail.py` | Opt-in wide mode. Packing Tool keeps its rail |
| Mockup palette vs the WCAG floors | Keep the floors. Hairlines use `border_subtle` (ADR 0018) |
| The palette reaching Packing Tool | Yes, at its next sync |
| The 9-phase roadmap and Phase 1 scope | Approved |

## 3. Palette (`shared/theme.py`)

### 3.1 Values

`LIGHT_THEME` and `DARK_THEME` take these values. They come from the mockup's token table (`const T` in
`component-sheet.html`). Where a mockup value failed a floor, the value shown here is the lightest grey that
clears the floor plus 0.1 in light mode, or the darkest in dark mode, and it is marked ⚑. The extra 0.1 is the
margin `tests/test_theme_contrast.py::test_no_foreground_sits_within_a_tenth_of_its_floor` requires. At Stage
A, the whole table was swapped into `shared/theme.py` as a throwaway probe. It passed `validate_theme` and the
margin test. The probe also found the two button tests §8 amends.

| token | light | dark |
|---|---|---|
| `surface_sunken` | `#F1F1F1` | `#0F1012` |
| `surface` | `#FFFFFF` | `#1A1B1E` |
| `surface_raised` | `#F7F7F7` | `#232428` |
| `surface_overlay` | `#FFFFFF` | `#2A2B30` |
| `text` | `#303030` | `#E3E3E3` |
| `text_secondary` | `#616161` | `#A3A3A8` |
| `text_disabled` ⚑ | `#888888` | `#767676` |
| `text_placeholder` ⚑ | `#6C6C6C` | `#949494` |
| `border` ⚑ | `#888888` | `#767676` |
| `border_subtle` | `#E3E3E3` | `#34353A` |
| `border_strong` | `#888888` | `#767676` |
| `status_info` | `#00527C` | `#7CC4F8` |
| `status_info_bg` | `#E0F0FF` | `#0B2A40` |
| `status_success` | `#0C5132` | `#6ED3A0` |
| `status_success_bg` | `#CDFEE1` | `#0E3222` |
| `status_warning` | `#5E4200` | `#F5C451` |
| `status_warning_bg` | `#FFEF9D` | `#3A2C05` |
| `status_danger` | `#8E0B21` | `#FF9A9A` |
| `status_danger_bg` | `#FEE9E8` | `#43141A` |
| `accent_fill` | `#303030` | `#E3E3E3` |
| `accent_fill_hover` | `#1A1A1A` | `#FFFFFF` |
| `accent_fill_active` | `#000000` | `#C4C4C8` |
| `on_accent` | `#FFFFFF` | `#1A1B1E` |
| `selection_border` | `#005BD3` | `#4A9CFF` |
| `selection_bg` | `#EAF4FF` | `#12243B` |
| `focus_ring` | `#005BD3` | `#4A9CFF` |
| `hover` | `#F7F7F7` | `#232428` |

The aliases follow their canonical token, as `_ALIAS_PAIRS` requires: `background` = `surface`,
`background_elevated` = `surface_raised`, `accent_blue` = `accent_fill`, `accent_green` = `status_success`,
`accent_orange` = `status_warning`, `accent_red` = `status_danger`, `active_background` = `selection_bg`,
`active_border` = `selection_border`, and `button_hover_light` = `button_hover_dark` = `accent_fill_active`.

`border_strong` equals `border` in both themes. In the mockup, dark `border_strong` (#5C5D63) is weaker than the
floored `border`, which would invert the pair.

Mapping rule (ADR 0018): the mockup's `border` is a hairline, so here it becomes `border_subtle`. The mockup's
`border_strong` becomes `border`. No call site changes its token in Phase 1. Most `{theme.border}` uses are
control edges already. The few that are panes (`QTabWidget::pane`, the log viewer's box) get a slightly lighter
grey than today and belong to screens that later phases replace. The §8 render check looks for any line that
now reads wrong.

### 3.2 New tokens

Four tokens, the ones Phase 1 uses. They are ordinary `#RRGGBB` colour fields on `ThemeTokens`, declared after
`status_danger_bg`. Each is also added to the explicit `_COLOR_FIELDS` tuple after `"status_danger_bg"`, and
that one registration gives it `validate_theme`'s hex check and the `theme_css_vars` emission check. None of the
names starts with `surface` or `accent_fill`, so neither contrast matrix grows.

| token | light | dark | used by |
|---|---|---|---|
| `status_success_dot` | `#29845A` | `#6ED3A0` | sidebar connection dot, connected |
| `status_danger_dot` | `#E51C00` | `#FF9A9A` | sidebar connection dot, unreachable |
| `status_danger_border` | `#FDB5B4` | `#6B2029` | unreachable box edge and its Retry button |
| `control_disabled_bg` | `#F1F1F1` | `#141518` | disabled button fill (§3.3) |

No floors are added. The dots are marks next to a text label that carries the same meaning, and
`control_disabled_bg` sits under `text_disabled`, which is already floored against every plane.
`control_disabled_bg` equals `surface_sunken` in light mode, and `text_disabled` is measured against that plane.

Not in Phase 1: `card_shadow`, `card_border`, `overlay_shadow`, `surface_inverse`, `on_inverse` and
`status_warning_dot` arrive with the phase that first draws them (roadmap Phase 2, and Phase 4 for the warning
dot).

### 3.3 Disabled buttons look disabled (audit A6)

In `build_stylesheet` (`shared/theme.py`, the `QPushButton:disabled` rule and the role-qualified `:disabled`
rule under it), both rules become:

```
background-color: {theme.control_disabled_bg};
color: {theme.text_disabled};
border: 1px dashed {theme.border_strong};
```

That is the component sheet's disabled button: a dropped fill and a dashed edge.

### 3.4 Reaching Packing Tool

The palette and the disabled rule reach Packing Tool at its next `sync_shared.py`. The PR body says so, and
says Packing Tool can hold its sync until it wants the new look. No floor moved, so Packing Tool's mirrored
floor test still passes.

## 4. Sidebar

### 4.1 `shared/navrail.py`: an opt-in sidebar mode

`NavRail.__init__(self, parent=None, width=RAIL_WIDTH, expanded_width: int | None = None)`.

- **`expanded_width is None` (the default): exactly today's rail.** Same widths, text under the icon, same
  stylesheet. Packing Tool constructs `NavRail(width=76)` and sees no change.
- **`expanded_width` set (sidebar mode):**
  - It starts expanded: `setFixedWidth(expanded_width)`. Items are `QToolButton`s with
    `Qt.ToolButtonTextBesideIcon`, 32px tall and `expanded_width - 16` wide, in a layout with 8px margins and
    2px spacing. A render at Stage A confirmed that a text-beside-icon `QToolButton` with a fixed width keeps
    its icon and label left-aligned under QSS.
  - Stylesheet (scoped to `NavRail`, re-applied on `theme_notifier.changed` as now): the rail's background is
    `surface_sunken`. Items are transparent with a 1px transparent border, radius 8px, left padding 9px and
    colour `text_secondary`. `:hover` uses `hover`. `:checked` uses a `surface` background, a
    `1px solid border_subtle` edge, colour `text` and bold. `:disabled` uses colour `text_disabled`.
  - `set_expanded(expanded: bool)` switches between `expanded_width` with text beside the icon, and `width`
    (56) with `Qt.ToolButtonIconOnly` and 40px-wide items. `is_expanded()` reads it. On a rail with no
    `expanded_width`, `set_expanded` raises `RuntimeError`.
  - The label text stays `"Setup"` and so on in both states. Tooltips are the caller's, as now.

Only `NavRail` goes in `shared/`. The header and footer are this app's (§4.2), because they carry this app's
server and client. Packing Tool builds its own when it opts in.

### 4.2 `gui/components/sidebar.py`: `Sidebar(QWidget)`

The shell's left column, top to bottom, following `app-shell.html`:

1. **Header**, 44px, bottom edge `1px solid border_subtle`, 8px side padding.
   - Expanded: a 28×28 mark tile (a `QLabel` with an `accent_fill` background, radius 8, holding
     `icon("package", color=theme.on_accent)` at 16px), then "Fulfilment Tool" in bold, eliding, then a 28×28
     auto-raise `QToolButton` using `panel-left-close`, tooltip "Collapse sidebar".
   - Collapsed: only a 40×32 `QToolButton` using `panel-left-open`, tooltip "Expand sidebar".
2. **`self.rail = NavRail(self, expanded_width=SIDEBAR_WIDTH)`**, where `SIDEBAR_WIDTH = 200`. It takes the
   stretch.
3. **Footer**, top edge `1px solid border_subtle`, padding 8, spacing 6.
   - **Client settings:** a `QToolButton` using `settings`, "Client settings", styled like a rail item and not
     checkable. It emits `settingsRequested`. Collapsed, it shows the icon only and the tooltip
     "Client settings".
   - **Theme:**
     - Expanded: a segmented pair in a frame (`surface_sunken` background, `1px solid border`, radius 8, 2px
       padding). It holds two checkable `QToolButton`s in an exclusive group, "Light" with `sun` and "Dark"
       with `moon`, each 24px tall and sharing the width equally. The checked one gets a `surface` background,
       a `1px solid border_subtle` edge and bold. Clicking emits `themeRequested("light" | "dark")`.
     - Collapsed: one 40×32 button showing `moon` in light and `sun` in dark, tooltip "Switch to Dark" or
       "Switch to Light". It emits the other theme's name.
   - **Connection:**
     - Expanded: a box (radius 8, padding 6/8, min height 44) holding an 8px round dot, then a column: the
       label in bold 9pt (`caption` role, bold) in the status colour, then the server path in Consolas 9pt,
       `text_secondary`, elided in the middle, with the full path as its tooltip.
       - Connected: `status_success_dot` and "Server connected". The box is transparent.
       - Unreachable: `status_danger_dot` and "Server unreachable". The box has a `status_danger_bg` background
         and a `1px solid status_danger_border` edge, and a "Retry" `QPushButton` shows under the path
         (24px tall, `surface` background, `1px solid status_danger_border` edge, bold 9pt). Retry emits
         `retryRequested`.
     - Collapsed: a 40×32 box holding `server`, with the 8px dot at its bottom-right. The tooltip is the
       label, " · ", then the path (for example "Server connected · \\fs01\fulfilment"). The box is transparent when
       connected and `status_danger_bg` when unreachable.

**Public API:**

```python
class Sidebar(QWidget):
    settingsRequested = Signal()
    themeRequested = Signal(str)      # "light" | "dark"
    retryRequested = Signal()
    expandedChanged = Signal(bool)    # emitted by the header's collapse/expand buttons only

    rail: NavRail
    def set_expanded(self, expanded: bool) -> None   # width SIDEBAR_WIDTH / RAIL_WIDTH, swaps header/footer parts
    def is_expanded(self) -> bool
    def set_connection(self, connected: bool, server_path: str) -> None
    def set_theme_name(self, name: str) -> None      # checks the matching segment, picks the collapsed glyph
    def set_settings_enabled(self, enabled: bool) -> None
```

The Sidebar re-applies its own stylesheet and re-renders its icons on theme change with `on_theme_changed`,
the same hook `ui_manager` uses. A `QIcon` is a snapshot.

### 4.3 Glyphs

Vendor `panel-left-close`, `panel-left-open`, `sun`, `moon` and `server` from Lucide **1.31.0** into
`shared/assets/icons/` (`https://raw.githubusercontent.com/lucide-icons/lucide/1.31.0/icons/<name>.svg`; Stage
A confirmed all five return 200). Add them to `EXPECTED_ICONS` in `tests/test_ui_assets.py`
(`shared/assets/README.md`). `settings` and `package` are already vendored.

## 5. Shell wiring (`gui/ui_manager.py`, `gui/main_window_pyside.py`, `gui/actions_handler.py`)

### 5.1 Layout

- `create_widgets` builds `self.mw.sidebar = Sidebar(self.mw)` in place of `NavRail(self.mw)`, and sets
  `self.mw.nav_rail = self.mw.sidebar.rail`. Every existing `nav_rail` call site (`add_item`, `button`,
  `set_current`, `currentChanged`, `_refresh_icons`) keeps working unchanged.
- The right side's layout gets 0 margins and 0 spacing, so the command bar runs edge to edge with its own bottom
  edge as the divider. The error banner and `main_tabs` go in a wrapper `QWidget` whose layout keeps today's
  5px margins and 5px spacing, so no Qt page moves.
- `CommandBar._apply_theme`: the bar's background becomes `surface_sunken` (it was `surface_raised`). Its
  bottom edge stays `border_subtle`.
- The client selector gets `setPlaceholderText("Choose a client")`, which fixes audit Shell finding 1 (an empty
  grey box). Check the render: the placeholder only paints when the current index is -1.

### 5.2 The status bar is deleted

- `create_widgets` no longer touches `self.mw.statusBar()`, and `self.mw.connection_chip` is gone. Nothing may
  call `statusBar()`, because the call creates the bar.
- `MainWindow.update_ui_state`: delete the four `showMessage` calls. Each one repeats something the screen
  already shows.
- `MainWindow`, around lines 575 and 655: delete "Loading CLIENT_…" and "CLIENT_… loaded".
- `ActionsHandler` (the two report messages around line 822): send the same two strings through
  `self._results_toast(...)`. Reports are generated from Results, where the toast lives (ADR 0007).
  "No orders matched {report_name}; its old files were removed" and "Report saved: {saved}" keep their text.

### 5.3 Connection

`_on_connection_changed(connected)` calls
`self.mw.sidebar.set_connection(connected, str(self.mw.profile_manager.base_path))` where it used to set the
chip. `sidebar.retryRequested` connects to `self.mw.recheck_connection`, the same call the Server Connection
dialog makes. That call is synchronous, as the dialog's is.

### 5.4 Destinations: one enabling rule

A new `UIManager._refresh_nav()` holds the rule. `_on_connection_changed` and `MainWindow.update_ui_state` both
call it, and the loop over `_OFFLINE_RAIL_ITEMS` is deleted.

| index | destination | enabled when |
|---|---|---|
| 0 | Setup | always |
| 1 | Results | connected **and** `analysis_results_df is not None` |
| 2 | Browse | connected **and** a client is selected |
| 3 | Logs | always |
| 4 | Tools | connected **and** a client is selected |

If the current destination becomes disabled, `nav_rail.set_current(0)`, which is what happens offline today.
The Results button's tooltip is "Analysis Results — available after Run analysis (Ctrl+2)" while disabled. The
full destination name stays, because `test_the_full_destination_name_survives_in_the_tooltip` needs it. Otherwise it shows its normal tooltip. Ctrl+1–5 already go through `_go_to_destination`, which checks `isEnabled()`, so shortcuts follow the
rule with no change.

The analysis finishing, and a past session opening from Browse, must enable Results **before** the jump to it.
Otherwise the rule bounces the operator back to Setup. §8 has a test for each path.

`_refresh_nav` also calls `self.mw.sidebar.set_settings_enabled(connected and has_client)`.

`MainWindow._focus_results_search` (Ctrl+F) jumps straight to `main_tabs.setCurrentIndex(1)`, which bypasses the
rule. It returns early when `self.nav_rail.button(1).isEnabled()` is False.

### 5.5 Theme and collapse

- `sidebar.themeRequested` goes to `get_theme_manager().set_theme(name)`, and a theme change calls
  `sidebar.set_theme_name(...)` (hook it in the existing `on_theme_changed(self.mw, ...)` callback).
- The collapsed state is saved per PC. A module-level `_shell_settings()` in `gui/ui_manager.py` returns
  `QSettings("ShopifyFulfillmentTool", "FulfillmentApp")`, the pair `theme_manager` and `log_viewer` use. The
  key is `"shell/sidebar_collapsed"`. At startup, `sidebar.set_expanded(not collapsed)`, where `collapsed` is
  read with `type=bool` and defaults to False. `sidebar.expandedChanged` writes the key. Tests monkeypatch
  `_shell_settings` to an INI file under `tmp_path`.

### 5.6 Command-bar overflow

`_populate_overflow` becomes:

- Section **client name**: "New session…", as now. It stays in the overflow until Phase 3 makes the bar's New
  session button always visible (§7).
- Section **THIS PC**: "Server connection…", as now, and "Keyboard shortcuts…", which is new.
- "Client settings…" and the Light/Dark choice group are removed. The sidebar footer owns them now.
- `settingsRequested` connects to `self.mw.actions_handler.open_settings_window()`, the same target the overflow
  item used.

### 5.7 Keyboard shortcuts dialog (`gui/shortcuts_dialog.py`)

A module-level tuple `SHORTCUTS` of `(keys, action)` rows, and `ShortcutsDialog(QDialog)`, which shows them in a
two-column form (keys in Consolas) with a Close button. Rows: "Ctrl+1 … Ctrl+5" go to Setup, Results, Browse,
Logs, Tools. "Ctrl+R" runs analysis. "Ctrl+F" searches results. "Ctrl+Z" undoes the last change. The overflow
item opens it with `exec()`. The window title is "Keyboard shortcuts".

## 6. Docs

- `CONTEXT.md` § Shell. **Shell** becomes: "the sidebar, the command bar and the page. Not a screen itself, and
  it never scrolls." Add **Sidebar**: "the shell's left column: the destinations, and a footer holding what
  configures the client and this PC (Client settings, the theme, the server connection). It collapses to a
  56px **rail**." Rewrite **Destination** so it no longer says the rail has no footer: "the sidebar holds
  destinations in its list, and configuration only in its footer." Change **Overflow** so the command-bar
  overflow "holds what the sidebar footer does not: New session, the server connection and the keyboard
  shortcuts."
- The docstring of `tests/test_settings_entry_points.py::test_settings_buttons_are_labelled_settings` and its
  `'"Client settings…"' in source` assertion move from the overflow to `gui/components/sidebar.py`. The test now
  reads that file and asserts `"Client settings"`.

## 7. Departures from the mockup

| Mockup | Phase 1 | Why / when |
|---|---|---|
| Hairline `border`, disabled text and placeholder as drawn | Darker `border`, `text_disabled` and `text_placeholder` | ADR 0018 |
| 10px gap between an item's icon and its label | Qt's fixed gap (~4px) | `QToolButton` has no QSS spacing property. Not worth a custom paint |
| "Reconnecting…" (warning) connection state | Two states: connected and unreachable | `recheck_connection` is synchronous, so the in-between state never paints |
| With no client, every destination is disabled | Setup and Logs stay enabled | Logs is where an operator reads why the server is unreachable, and with no server there is no client |
| New session is always shown, secondary, disabled with no client | Unchanged (state-owned). "New session…" stays in the overflow | Roadmap Phase 3, which owns the no-session and running bar |
| While running: step count, step name, disabled "Running…" | Unchanged (progress label and Cancel) | Roadmap Phase 3: Cancel moves onto the Setup page |
| Page headers ("Setup · Session opened 14:02") | None on Qt pages | Each screen's own phase draws its header on the web tier |
| Session chip in the command bar on Results | Unchanged (the session button carries the id) | Roadmap Phase 2 |
| Client combo dot in `status_*_dot` | Unchanged | Roadmap Phase 3, with the bar |

## 8. Tests (test-first; files in `tests/`)

| Seam | File | Asserts |
|---|---|---|
| Palette | `test_theme_palette.py` (new) | Every §3.1 value and every §3.2 token, per theme; `validate_theme` passes for both. |
| Disabled rule | `test_theme_palette.py` | `build_stylesheet(LIGHT_THEME)` contains `1px dashed #888888` and `#F1F1F1` inside the `QPushButton:disabled` rule |
| NavRail default unchanged | `test_components_navrail.py` | `NavRail()` items are `ToolButtonTextUnderIcon`; `set_expanded` raises `RuntimeError` |
| NavRail sidebar mode | `test_components_navrail.py` | `NavRail(expanded_width=200)` is 200 wide with `TextBesideIcon` items 184 wide; `set_expanded(False)` gives 56, `IconOnly`, 40-wide items; `is_expanded()` follows |
| Sidebar | `test_sidebar.py` (new) | Retry hidden when connected and shown when not; clicking it emits `retryRequested`; the path label's tooltip is the full path; clicking Dark emits `themeRequested("dark")`; the collapse button emits `expandedChanged(False)` and the width becomes 56; `set_settings_enabled(False)` disables the settings button |
| No status bar | `test_shell.py` | `main_window.findChild(QStatusBar) is None`; replaces the `statusBar().height() == 28` assertion |
| Nav rule | `test_shell.py` | With no client: Setup and Logs enabled, Results, Browse and Tools disabled; with a client and no analysis: Results disabled and its tooltip says "available after Run analysis"; setting `analysis_results_df` and calling `update_ui_state()` enables it; sitting on Browse when `connectionChanged(False)` fires moves to Setup |
| Reaching Results | `test_shell.py` | The order both call sites use (set `analysis_results_df`, `setCurrentIndex(1)`, `update_ui_state()`) leaves the current index at 1 with button 1 enabled |
| Collapse persists | `test_shell.py` | With `_shell_settings` monkeypatched to an INI file, collapsing writes `True`; a new window starts collapsed at 56px |
| Overflow | `test_shell.py` | Item texts are exactly New session…, Server connection…, Keyboard shortcuts…; no choice group |
| Shortcuts stay true | `test_shortcuts_dialog.py` (new) | Every key in `SHORTCUTS` (with "Ctrl+1 … Ctrl+5" expanded to five) matches a `QShortcut` on the main window |
| Offline | `test_first_run.py` | `test_the_status_bar_says_so_too` becomes a sidebar test: the connection label reads "Server unreachable" and Retry is visible |
| Report toast | `test_label_pdf_invalidation.py` | The message is read from `h.mw.results_bridge.raise_toast.call_args[0][0]` |
| Entry point | `test_settings_entry_points.py` | As in §6 |
| Glyphs | `test_ui_assets.py` | The five names in `EXPECTED_ICONS` |
| Button tests | `test_shared_theme_buttons.py` | `test_the_unmarked_button_rule_is_secondary` and `test_an_unmarked_button_is_not_primary` assert `f"background-color: {theme.accent_fill}"` is absent, not the bare hex: dark `accent_fill` equals dark `text` (#E3E3E3), so the bare hex now matches the text colour |
| Ctrl+F | `test_shell.py` | With Results disabled, `_focus_results_search()` leaves the current page unchanged |

**Visual check (required, CLAUDE.md):** render `MainWindow` offscreen at 1366×768 in light and dark, expanded and
collapsed, connected and unreachable. Save the PNGs, look at them, and compare them with
`mockups/renders/app-shell.png`. Attach the light-expanded and dark-collapsed renders to the PR.

**Gate:** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` and `ruff check .`, then `graphify update .`.

## 9. Delivery

One PR on `cognitiveghost/shopify-fulfillment-tool` from `dr/13-mock-up-of-fulfilment-tool`: the docs (§1) and
Phase 1. No packing-tool PR. The PR body says `shared/theme.py` (palette, disabled buttons, four tokens),
`shared/navrail.py` (opt-in mode, default unchanged) and five new glyphs reach Packing Tool at its next sync,
and that it can hold the sync.

## 10. Out of scope

Everything in roadmap phases 2 to 9, including the web kit, shadows, and any page moving to the web tier.
Packing Tool screens. Making Todoist tasks (the owner adds them from `roadmap.md`).
