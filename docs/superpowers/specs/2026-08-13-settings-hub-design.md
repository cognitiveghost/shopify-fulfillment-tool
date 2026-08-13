# UI Design System Track 4 — Settings Hub — Design

## Context

The 2026-08-11 vision doc (`2026-08-11-ui-design-system-vision-design.md`) describes Track 4
as:

> One window: left-nav categories + right-side `QStackedWidget` content, built from
> `Card`/`FormSection`. Directly resolves Phase 6's flagged "two competing client-settings
> windows".

**Most of that shipped already, in Track C (PR #272).** Splitting
`settings_window_pyside.py` into `gui/settings/` was scoped as structural risk reduction,
but it also delivered the Hub's shape:

| Vision doc's Track 4 item | State after #272 |
|---|---|
| Left-nav categories | `SettingsWindow.SETTINGS_NAV_GROUPS`, `window.py:56-61` — four groups, nine pages |
| Right-side `QStackedWidget` | `window.py:126` |
| "Two competing client-settings windows" | `profile_manager_dialog.py` deleted; `ClientSettingsDialog` retitled "Client Profile". Guarded by `tests/test_settings_entry_points.py` |
| Tag Categories / Column Config as separate popups | Absorbed as Hub pages (`_TagCategoriesPage`, `_ColumnConfigPage`) |
| Built from `Card`/`FormSection` | **Not done.** `FormSection` does not exist |

So Track 4 is smaller than the vision doc anticipated, and its content shifts: the
structure exists, what is missing is that the Hub does not yet *look* or *behave* like a
designed surface, and its page contract has a known sharp edge that #272's review found and
recommended designing away rather than testing around.

This doc covers what actually remains.

## Problems this design solves

**1. `collect()`'s merge semantics are a silent-data-loss trap.**
`window.py:231-236` merges each page's `collect()` output one level deep:

```python
if isinstance(value, dict) and isinstance(self.config_data.get(key), dict):
    self.config_data[key].update(value)
else:
    self.config_data[key] = value
```

`update()` can add and overwrite but never remove. Both Important findings in #272's review
trace to this single line:

- A page that *stops* producing a config field cannot be detected — the fixture's stale
  value survives the merge. The reviewer proved it by deleting `repeat_detection_days` from
  `GeneralPage.collect()` and watching the round-trip test stay green.
- Deleting a courier row could not stick, because the removed key survived the merge.
  `MappingsPage` works around this by mutating and returning its live sub-dicts
  (`mappings.py:206-218`) — a correct fix, but one explained only in a comment. A future
  `deepcopy` anywhere upstream silently reinstates the bug with the whole suite green.

The workaround is right; the contract is wrong. One page discovered the rule and the other
two did not, which is the definition of a contract that should not be implicit.

**2. There is no visual hierarchy on any button, anywhere.**
`shared/theme.py:203-211` styles *every* `QPushButton` accent-blue on white. In the Hub's
Rules page, "Add Rule", "Add Step", "Delete", and the window's "Save" all render identically.
Track 3 explicitly recorded that no `:default` rule exists and that primary/secondary
differentiation "still has to be built, not re-enabled".

**3. `FormSection` was deferred to here so a real page would shape its API.**
Track 3 deferred it on purpose (`2026-08-12-component-library-design.md:12-17`) because its
motivating example moved into Track C. The real call sites now exist and can be counted.

**4. The Hub forgets where you were.**
Nine pages, one `QListWidget`, and every open lands on "General". The Weight page and the
Rules page are the ones people return to.

## Non-goals, and why

**Client Profile does not move into the Hub.** The vision doc lists "Client Profile" as a
Hub nav category. Two facts changed since it was written:

- The duplication it was meant to fix is already gone. Phase 6's "two competing
  client-settings windows" were `settings_window_pyside.py` and `profile_manager_dialog.py`.
  The latter is deleted and `tests/test_settings_entry_points.py:13` asserts it stays
  deleted. The remaining `ClientSettingsDialog` was retitled "Client Profile" and edits a
  genuinely different thing — display name, colour, group membership — not fulfillment
  config.
- The entry points do not line up. `SettingsWindow` is bound to the *active* client
  (`actions_handler.py:383` passes `self.mw.current_client_id`). `ClientSettingsDialog` is
  launched from the sidebar's per-row Edit for *any* client
  (`client_sidebar.py:719-728`). Folding it in means either the Hub accepts an arbitrary
  client — new coupling, and a modal settings window that edits a client you are not working
  on — or the sidebar's Edit silently switches the active client. Both are worse than one
  small focused dialog.

Moving it later stays cheap; moving it now and reverting does not. **Flagged as an open
question for the user** rather than decided silently — see Open Questions.

**`GroupsManagementDialog` does not move in either.** Client groups are a sidebar
organisation concern, not per-client fulfillment config. It has no `client_id` at all.

**The repeating-item group boxes are not migrated to `FormSection`.** There are 13
`QGroupBox(...)` sites in `gui/settings/`. Eight are *item containers or their sub-boxes* —
one box per rule, per report, per step, plus the IF/THEN and Filters boxes nested inside
them (`rules.py:263,418,426,444`, `packing_lists.py:50,60`, `stock_exports.py:50,58`). Two
of those are `QGroupBox()` with no title at all. They are card-like repeating rows, not
titled form sections; `FormSection` is the wrong tool and forcing it there would be a large
diff that makes the code worse. Of the five that *are* page-level titled sections, four are
migrated below; `weight.py:102`'s "Quick Add" box is left alone because `weight.py` is
already being edited for the contract change and is the largest page in the package —
adding a layout rewrite there buys little and risks more.

**No button restyle outside `gui/settings/`.** The mechanism is app-wide, the application of
it is scoped to the Hub. See "Button hierarchy" for why that is deliberate and not laziness.

**`shared/theme.py` is not edited.** It is sync-owned by `packing-tool` (this repo's
`CLAUDE.md`). Everything below layers on top through `gui/theme_manager.py`, the same
repo-owned seam Track 1 used for the `font_family` override.

## Design

### 1. The `collect()` contract: replace, never merge

**New contract, stated in `SettingsPage`'s docstring:**

> `collect()` returns `{config_key: value}`. Each returned value **replaces**
> `config_data[key]` outright. A page that owns a dict sub-tree must mutate and return the
> live dict it was constructed with, so keys it does not render survive.

The shell becomes an unconditional assignment:

```python
for page in self._pages:
    for key, value in page.collect().items():
        self.config_data[key] = value
```

The `isinstance` branch disappears, and with it the reasoning about whether a given key is
shrinkable.

**Why "mutate the live dict" rather than "return a fresh complete dict".** These are live
warehouse client configs on a production file server. `config["settings"]` is *canonically*
the four keys `GeneralPage` renders (`profile_manager.py:403-408`), but a config written by
an older build can carry keys nothing in the current UI knows about —
`profile_migrations.py` exists precisely because that has happened before. A fresh-dict
return silently drops them on every save. Holding the live sub-dict means unrendered keys
are never removed in the first place, so preservation is structural rather than a rule
someone has to remember.

**Three pages return dict values and are affected:**

| page | key | change |
|---|---|---|
| `MappingsPage` | `column_mappings`, `courier_mappings` | None — already correct. Its explanatory comment is rewritten to cite the contract instead of describing the merge it was working around |
| `GeneralPage` | `settings` | Hold the constructor's dict as `self._settings`; `collect()` updates it in place and returns it |
| `WeightPage` | `weight_config` | Same. **Watch `weight.py:41**: `weight_cfg = weight_config or {...}` substitutes a *fresh* dict when the config is empty, so the page must hold whichever dict it actually used, not the parameter |

`RulesPage`, `PackingListsPage`, `StockExportsPage` return lists — they already replace
wholesale and are unaffected. `SetsPage` and `_ColumnConfigPage` self-save and collect
nothing.

**`collect()` gains a side effect** (it writes into `config_data` before the shell assigns).
This is safe by construction: `save_settings` runs `validate()` across *all* pages before
calling `collect()` on any of them, so no page mutates during a save that a later page will
block. `config_data` is already a deep copy (`window.py:78`), so a failed server write
cannot leak into the caller's config. The docstring says this explicitly.

**Testing.** `test_no_page_silently_drops_a_field` (added in #272 for exactly this) already
compares each page's `collect()` output directly and keeps working. Add one test asserting
that a key present in the loaded config but rendered by no page survives a full save
round-trip — that is the behaviour the live-dict rule buys, and nothing currently proves it.

### 2. `FormSection`

`gui/components/form_section.py`, alongside the existing `Card`.

```python
FormSection(title: str, description: str = "", parent=None)
    .add_row(label: str, widget: QWidget, tooltip: str = "") -> QWidget
    .add_widget(widget: QWidget) -> None
```

A `QFrame` with a title label at the `label` type-scale role, an optional wrapped
description at `caption` in `theme.text_secondary`, and a `QFormLayout` body. Margins and
spacing come from Track 1's tokens, not per-widget magic numbers. `add_row` builds the
`QLabel` itself — the pages currently construct a named `QLabel` variable per row purely to
pass it to `addRow` (`general.py:25,37,52,61`), which is four lines of ceremony per field.
`tooltip` is applied to both the label and the widget, so hovering the *label* explains the
field; today only the input carries the tooltip.

`add_widget` exists because the sections that need a title do not all contain form rows —
`mappings.py:87` is a title over a button-and-rows column, and `SetsPage`
(`sets.py:44-46`) and `_ColumnConfigPage` (`window.py:344-358`) each hand-roll a
`font_css("heading")` label plus, in one case, an italic description. That is the same
widget written three times. One component covers all of them; a separate `PageHeader` type
would be a second component for the same job.

**Adopted at these call sites, and no others:**

| site | today | becomes |
|---|---|---|
| `general.py:22` | `QGroupBox("General Settings")` + 4 hand-built label/row pairs | One `FormSection`, 4 `add_row` calls |
| `mappings.py:43,65,87` | 3 `QGroupBox` | 3 `FormSection` |
| `sets.py:44` | bare `font_css("heading")` label | `FormSection` title |
| `window.py:344` (`_ColumnConfigPage`) | hand-rolled heading + italic help `QLabel` | `FormSection` title + description |

Six sites. If it does not earn its keep at six, it should not exist — the count is stated
here so the implementation can report honestly whether the diff shrank.

**Testing.** Construction test with stub rows, no window needed (the shape Track 3's `Card`
tests already use): assert `add_row` labels the row and propagates the tooltip to both
widgets, and that an unknown type-scale role raises rather than silently rendering at a
default size — the rule Tracks 1-3 set.

### 3. Button hierarchy

A `role` dynamic property read by QSS:

```python
button.setProperty("role", "primary")    # accent fill — the commit action
button.setProperty("role", "secondary")  # neutral fill, bordered — everything else
```

The rules live in a small stylesheet suffix appended in `ThemeManager.apply_theme()`, after
`build_stylesheet(theme)`. `theme_manager.py` is already established as the repo-owned
customization seam (Track 1 layered `font_family` there via `dataclasses.replace`), and an
app-level suffix means every dialog picks the rules up without importing anything.

**Unmarked buttons keep exactly today's appearance.** The opposite arrangement — make the
default neutral and mark primaries — is fewer edits, but it restyles every button in the
application in one commit. This is a Windows-only app developed on Linux with three tracks
of unverified visual change already stacked and no screenshot pass yet (see Open Questions).
Opt-in means the blast radius is exactly the widgets that were touched deliberately.

**Applied within `gui/settings/` only**: the Hub footer's Save becomes `primary` and Cancel
`secondary`; the in-page action buttons (Add Rule, Add Step, Add Filter, delete `X`, Browse)
become `secondary`. That is the point of the exercise — inside the Hub, Save should be the
only accent-blue button on screen. The rest of the app adopts the property as its screens are
touched, per Track 5's incremental rule.

One catch worth stating because it is a classic Qt trap: **Qt does not restyle a widget when
a dynamic property changes after the stylesheet is applied.** Setting `role` before the
widget is polished (i.e. at construction, which is every call site here) is fine. If any site
ever needs to flip it live, it must call `style().unpolish(w); style().polish(w)`. The helper
that sets the property does the unpolish/polish unconditionally so the trap cannot be
stepped in.

**Testing.** Assert the generated stylesheet suffix contains a rule for each role and that
the two roles produce different background colours in both light and dark themes — a
property typo or a token that resolves to the same colour in one theme is otherwise
invisible until someone looks at Windows.

### 4. Hub chrome: nav styling and remembered selection

**Nav styling.** The nav is a bare `QListWidget` at a fixed 170px (`window.py:121-124`). It
reads as a list dropped next to the content, not as a sidebar. The same stylesheet suffix
from §3 gives `QListWidget#settingsNav` a subdued background (`theme.background`, against the
content's `background_elevated`), no frame, and a clear selected-row treatment. Group headers
are already non-selectable and already use the `caption` role bold (`window.py:194-196`) —
they need only the secondary text colour to stop competing with the entries under them.

**Remembered selection.** `QSettings("ShopifyFulfillmentTool", "FulfillmentApp")` — the same
store `ThemeManager` uses (`theme_manager.py:80`) — under key `settings_hub/last_page`. Store
the page *name*, not the row index: nav groups have gained entries twice already, and an
index would silently point at a different page after the next one. On open, select the saved
name if it still exists, else fall back to today's behaviour (first selectable row).

**Testing.** A `TableConfigManager`-style state test, as the vision doc anticipated: save a
page name, reopen, assert the selection lands there; then assert an unknown/removed name
falls back to the first entry rather than raising or landing on nothing.

## Files touched

| file | change |
|---|---|
| `gui/components/form_section.py` | new |
| `gui/components/__init__.py` | export `FormSection` |
| `gui/settings/base.py` | contract docstring |
| `gui/settings/window.py` | assignment not merge; nav object name; selection persistence; `_ColumnConfigPage` header → `FormSection` |
| `gui/settings/general.py` | live `settings` dict; `FormSection` |
| `gui/settings/weight.py` | live `weight_config` dict |
| `gui/settings/mappings.py` | comment cites contract; 3 × `FormSection` |
| `gui/settings/sets.py` | header → `FormSection` |
| `gui/settings/rules.py`, `packing_lists.py`, `stock_exports.py` | `role="secondary"` on action buttons only |
| `gui/theme_manager.py` | stylesheet suffix (button roles, nav) + the `role` helper |
| `tests/` | new tests per section above; existing `test_settings_roundtrip.py` extended |

## Risks

**The contract change is the only one that can lose data**, and it is the reason the live-dict
rule exists rather than a fresh-dict return. The mitigation is the round-trip test for
unrendered keys, and the mutation discipline #272 established: introduce the bug, watch the
new test fail, restore. A guard test never shown to fail is decoration.

**Everything else is visual and unverifiable on Linux.** Nothing in §2-§4 changes what is
written to a config file. The failure mode is "looks wrong on Windows", not "corrupts a
client config" — which is why the button work is opt-in and Hub-scoped.

## Open questions for the user

1. **Should Client Profile move into the Hub after all?** This design says no, with the
   reasoning above, and the "no" is the reversible choice. If the intent behind the vision
   doc was genuinely one window for everything client-related, say so and it becomes its own
   task — it needs the Hub to accept a client independent of the active one, which is a
   real change, not a page move.

2. **Windows visual check, still outstanding.** Tracks 1-3 (type scale, Inter embedding,
   icon-only header buttons) plus Track C's relabelled buttons plus this track's button
   hierarchy and nav styling are now five layers of visual change with no screenshot on the
   target OS. One pass covering all of them is the standing recommendation. This track adds
   to the stack; it does not create the problem.
