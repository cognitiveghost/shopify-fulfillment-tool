# The primary action becomes something a screen declares, not something a button defaults to

**Date:** 2026-08-29
**Todoist:** `6hP5pf3pPMHm3w4V` (p3, under Phase 8 `6hM87j3HVcc576vV`)
**Worktree:** `worktree-commandbar-primary` (branch `worktree-commandbar-primary`)
**Repos:** `packing-tool` (authors `shared/theme.py`) and `shopify-fulfillment-tool`

## 1. The reported fault

From the user's screenshots of the running Shopify tool, 2026-08-28:

> On Session Setup, **Settings** renders as a full-width primary-blue bar spanning the
> window, while **Run Analysis** — the screen's actual primary — sits above it greyed out.
> The most prominent control on the screen is the least important one.

The ticket attributes this to `CommandBar.set_action()` having no production caller, which
is true (`grep -rn set_action` finds the definition and four tests, nothing else) but is
**not what makes Settings blue**.

## 2. Root cause

`shared/theme.py:538` styles the bare `QPushButton` selector:

```
QPushButton {
    background-color: {theme.accent_fill};
    color: {theme.on_accent};
    ...
}
```

That is the `QPushButton[role="primary"]` rule at line 554 byte-for-byte, minus
`font-weight: bold`. **The default button role is primary.** Settings is blue because
nobody marked it anything, not because anybody marked it important.

Measured on `origin/main` @ `e6acb6f`:

| repo | `QPushButton(` constructions | `set_button_role(` call sites | rendering primary blue |
|---|---:|---:|---:|
| shopify `gui/` | 106 | 42 | ~64 |
| packing-tool | 41 | 2 | ~39 |

So `CommandBar`'s docstring promise — *"One primary per screen is enforced structurally"* —
is unenforceable by construction. A hundred-odd buttons across two apps outrank the one
button the component library actually marks primary.

This is not a new discovery. `docs/superpowers/specs/2026-08-27-phase8.6-shell-design.md`
§8 already deferred it:

> Out of scope: … flipping the global button default (8.5 handoff: 112 shopify buttons,
> opt-in until a screen designates a primary).

This spec picks that deferral up.

### 2.1 What follows from the root cause

Demoting Settings alone — the ticket's suggested fix — leaves 63 sibling buttons in shopify
and 39 in packing-tool still shouting. The fix belongs in the one place all of them route
through: the stylesheet's default.

Conversely, **flipping the default fixes the screenshot on its own**, with no CommandBar
change at all: Settings goes grey, and Run Analysis becomes the only blue thing on Session
Setup. The slot wiring is a separate improvement that delivers the mockup's intent and
settles the contract before packing-tool's 8.6b inherits the same empty slot.

## 3. Decisions taken

Put to the user 2026-08-29; all three answered:

1. **Scope** — both halves, as separate commits. The default flip is cosmetic; the slot
   wiring is navigational. Phase 8's standing rule keeps navigation commits separate so nav
   can be reverted independently of restyle.
2. **Move vs. stay** — the bar *mirrors* the screen's existing in-page button, and the
   in-page button hides. Every existing `setEnabled` / `clicked` call site keeps working
   untouched. Accepted cost: Run Analysis stops being a 70px hero button in the page and
   becomes a normal-height button in the top bar.
3. **Mapping** — as the ticket proposed (§6 below).

## 4. Part one — the default role becomes secondary

One rule in `shared/theme.py::build_stylesheet`. The bare `QPushButton` selector takes the
appearance `[role="secondary"]` already has:

```
QPushButton {
    background-color: {theme.surface_raised};
    color: {theme.text};
    border: 1px solid {theme.border};
    border-radius: {r}px;
    padding: 6px 12px;
    font-size: 10pt;
}
QPushButton:hover    { background-color: {theme.hover}; }
QPushButton:pressed  { background-color: {theme.selection_bg}; }
```

`[role="primary"]`, `[role="ghost"]`, `[role="danger"]` and the shared `:disabled` rule are
unchanged. `[role="secondary"]` becomes a restatement of the default and **stays** — 42
shopify call sites name it explicitly, and an explicit role documents intent at the call
site in a way an absent property cannot.

**No new contrast risk.** The pair `text` on `surface_raised` is what every
`role="secondary"` button already renders today, in both themes; this change increases the
number of buttons using an already-shipping, already-validated pair. No hex is introduced —
Phase 8's "never re-derive a hex" rule is not engaged.

### 4.1 The opt-in pass that must accompany the flip

Flipping the default with no other change leaves both apps with **no primary anywhere**,
which trades one wrong hierarchy for a flat one. Each app therefore marks its genuine
primaries in the same commit:

- **packing-tool** — four, across 10 files holding 41 buttons: `Start Packing`
  (`gui/main_window.py:385`), `Load Session` (`gui/session_selector.py:222`),
  `Restore Selected` (`gui/restore_session_dialog.py:72`) and `Save & Close`
  (`gui/sku_mapping_dialog.py:132`). Note `Scan` (`gui/packer_mode_widget.py:299`) is
  **not** one: it is a developer scan simulator beside a `QLineEdit`, not the screen's
  action.
- **shopify** — dialog accept buttons, principally. `gui/settings/window.py:186` already
  marks its save button primary and needs nothing. The audit is concentrated in six files:
  `ui_manager.py` (20 buttons), `column_config_dialog.py` (11), `settings/weight.py` (10),
  `bulk_operations_toolbar.py` (8), `tag_categories_dialog.py` (7), `settings/sets.py` (7).
  `settings/rules.py` already roles all 12 of its own.

**The rule the pass applies:** a button is primary only if it is the single action its
screen or dialog exists to perform. Everything else is secondary (the new default, so no
edit), `ghost`, or `danger`. Toolbar buttons, row actions, Browse/Refresh/Export and every
Cancel are secondary by definition.

This pass is judgement, not mechanism — the plan enumerates it file by file so review can
disagree per button rather than per commit.

## 5. Part two — `CommandBar.bind_action()`

### 5.1 Why bind rather than move

The three screen primaries already exist as `QPushButton`s whose enabled state is computed
in three other modules:

| button | constructed | enabled by |
|---|---|---|
| `run_analysis_button` | `ui_manager.py:823` | `file_handler.py`, `main_window_pyside.py:747` |
| `generate_reports_button_tab2` | `ui_manager.py:1190` | `main_window_pyside.py:774` |
| `new_session_btn` | `ui_manager.py:1105` | `main_window_pyside.py:208`, `:734` |

Deleting them and re-homing that logic into the bar is a large, risky diff across three
modules. Binding is a small one in a single component, and it reverts by deleting one hook.

The in-page button stays alive as the command's state — its text, tooltip, enabled flag and
`clicked` connections are the single source of truth — and merely stops painting itself.
This is what `QAction` is for in Qt; `QPushButton` cannot consume a `QAction` (only
`QToolButton` can, via `setDefaultAction`), so a retrofit would mean changing the widget
class at all 30-odd call sites. The hidden button is the same idea at a fraction of the
cost, and gets a `ponytail:` comment naming the ceiling.

### 5.2 API

```python
def bind_action(self, button: QPushButton | None) -> None:
    """Mirror `button` in the bar's primary slot. None hides the slot."""
```

- Copies `button.text()` and `button.toolTip()` at bind time. Neither is mutated at runtime
  for any of the three buttons (verified: no `setText` call site), so a one-shot copy is
  sufficient and no text-change observer is needed.
- Mirrors `button.isEnabled()` initially, and thereafter via an event filter on
  `QEvent.Type.EnabledChange` — `QWidget` has no `enabledChanged` signal, and the event is
  Qt's only notification for it.
- The bar button's click calls `button.click()`, so every existing `clicked` connection
  fires unchanged regardless of when it was made.
- Rebinding replaces the previous binding and removes its event filter.

`set_action(label)` is unchanged and stays public: it is the primitive `bind_action` is
built on, and the primitive a screen with no pre-existing button needs — which is the case
packing-tool's 8.6b will hit.

### 5.3 Where the wiring lives

A module constant in `gui/ui_manager.py`, keyed by tab index, resolved to a `main_window`
attribute lazily because the buttons are constructed during `_create_tabs()`:

```python
# index -> (main_window attribute of the screen's primary, hide it in the page)
_SCREEN_ACTIONS = {
    0: ("run_analysis_button", True),
    1: ("generate_reports_button_tab2", True),
    2: ("new_session_btn", False),
}
```

Bound on `main_tabs.currentChanged`, plus one call for the initial index. Ordering
constraint: `_create_command_bar()` runs at `ui_manager.py:153`, **before** `_create_tabs()`
at `:155`, so the wiring must be installed at the end of `_create_tabs()`, not with the bar.

Screens 3 (Information) and 4 (Tools) are absent from the map; the slot hides.

## 6. The per-screen mapping

| # | screen | bar action | in-page button |
|---|---|---|---|
| 0 | Session Setup | ▶ Run Analysis | hidden |
| 1 | Analysis Results | Generate Reports | hidden |
| 2 | Session Browser | Create New Session | **stays visible** |
| 3 | Information | none — slot hidden | — |
| 4 | Tools | none — slot hidden | — |

**Why row 2 is the exception.** `SessionBrowserWidget` has no New Session control of its
own — only Refresh and Show Archived. The button being mirrored lives on Session Setup,
where it is *not* that screen's primary and must keep rendering. Hence the explicit
per-entry `hide` flag rather than inferring hiding from the mapping: three entries, one
flag each, no rule to reconstruct at the call site.

The bar shows the bound button's text verbatim, so Session Setup's action reads
"▶ Run Analysis" with its glyph intact — one source of truth for the label.

## 7. Cross-repo sequencing

`shared/theme.py` is authored in `packing-tool` and pulled here. Two PRs, **packing-tool
merges first**, exactly as the selection-ring item ran:

1. **packing-tool** — the `build_stylesheet` default flip, packing-tool's own opt-in pass,
   and its `shared/theme.py` self-check assertion.
2. **shopify** — `python scripts/sync_shared.py ../../../../packing-tool` (the sibling
   default resolves wrongly from inside a worktree), shopify's opt-in pass, then
   `bind_action` and the wiring as a separate commit.

Editing shopify's `shared/` copy directly is a defect the next sync silently overwrites.

## 8. Incidental deletion

`gui/ui_manager.py` holds two helpers with no callers and no tests
(`grep -rn` over the repo finds only their `def` lines):

- `_create_session_management_group()` (`:515`) — constructs a **second**
  `self.mw.new_session_btn`, overwritten by the live one at `:1105`.
- `_create_actions_layout()` (`:753`).

Roughly 50 lines. The first is a live landmine for this change specifically: it assigns the
very attribute `_SCREEN_ACTIONS` resolves, so anyone wiring it up later would silently
rebind the bar to an orphan widget. Deleted in its own commit so review can drop it
independently.

## 9. Testing

- `shared/theme.py` `__main__` self-check: the bare `QPushButton` block does not contain
  `accent_fill`, and `[role="primary"]` still does.
- pytest against `build_stylesheet(DARK_THEME)` and `LIGHT_THEME`: default block uses
  `surface_raised`; the four role selectors all still present.
- `tests/test_components_commandbar.py`: `bind_action` mirrors text, tooltip and enabled
  state; a later `setEnabled` on the source propagates; the bar's click fires the source's
  `clicked`; `bind_action(None)` hides the slot; rebinding drops the old event filter.
- A ui_manager test driving `main_tabs.setCurrentIndex` 0→1→2→3 and asserting the bar's
  action label and visibility, and that the two hidden in-page buttons are hidden.

Plus the repo gate in each repo: `QT_QPA_PLATFORM=offscreen python -m pytest` and
`ruff check . --exclude shared` for shopify; packing-tool's own per its `CLAUDE.md`.

Existing tests that assert on button colour are expected to need updating; that is the
change working, not a regression, and each such edit is called out in the PR.

## 10. Out of scope

- Renaming any action or destination. Phase 8's standing rule: structure and labels never
  change in the same release.
- Restyling packing-tool's screens beyond marking its primaries — that is 8.9.
- The `Add Product to Order` button's 70px height, and the Session Setup Actions group's
  layout once Run Analysis leaves it. Cosmetic follow-up, not this change.
- Retiring the ten read-only legacy aliases. That is 8.3.

## 11. Risks

- **Blast radius is every button in both apps.** The diff is small; the visual change is
  not. Mitigated by shipping the flip as its own commit, ahead of the wiring.
- **A button that should be primary gets missed** in the opt-in pass and renders grey. Low
  severity — it still works and still reads as a button — and correctable per button. The
  plan enumerating the audit file by file is the mitigation.
- **Warehouse retraining.** Run Analysis moves from a 70px hero in the page to the top bar.
  The user accepted this deliberately; spec §9 of the selection-ring item already flags that
  a release note is owed before the next warehouse build, and this change belongs in it.
