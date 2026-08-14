# Rule actions: Internal tags only

**Date:** 2026-08-14
**Todoist:** `6hGfgPGhxWp2cFwV` (Phase 6)
**Branch:** `worktree-rule-actions-refactor`

## Problem

The rule editor offers four actions whose names suggest they add tags. Only one does.

| Action | What it actually writes | Notes |
|---|---|---|
| `ADD_TAG` | `Status_Note` (free text, comma-joined) | `rules.py:1063-1067`. Does not touch any tag column. |
| `ADD_ORDER_TAG` | `Status_Note` | `rules.py:1069-1073`. Byte-identical logic to `ADD_TAG`. |
| `SET_MULTI_TAGS` | `Status_Note` | `rules.py:1111-1141`. Comma-splits first; equals N× `ADD_TAG`. |
| `ADD_INTERNAL_TAG` | `Internal_Tags` | `rules.py:1075-1084`. The real one: JSON array, order-level via `expand_to_order_rows`, deduped, wired to tag categories, colors and SKU write-off. |

So it is not four tag actions — it is **one tag action and three aliases for "append to a note field."**
The order-level dispatcher (`rules.py:864-871`) treats `ADD_TAG` and `ADD_ORDER_TAG` as the same
bucket too, so there is no behavioural difference there either.

The editor's own help text contradicts the code:

```
• ADD_TAG - applies to ALL rows (for filtering)
• ADD_ORDER_TAG - applies to first row only (for counting)
```
— `gui/settings/rules.py:398-400`. That per-row distinction does not exist.

## Decisions taken

Settled with the user before design:

1. **Drop all three from the authoring surface.** Internal tags become the only tag action a
   new rule can be built with.
2. **No migration, no silent rewrites.** Rules already configured with the legacy actions are
   *flagged in the editor* for the user to fix by hand.
3. **Also in scope:** an `ADD_INTERNAL_TAG` value dropdown seeded from tag categories, a new
   `REMOVE_INTERNAL_TAG` action, and a corrected help text.

### The load-bearing consequence

Decision 2 ("flag, don't rewrite") only holds if the engine keeps running the legacy actions.
So:

> **The rule engine is unchanged for legacy actions.** `ADD_TAG`, `ADD_ORDER_TAG` and
> `SET_MULTI_TAGS` keep executing exactly as today. Nothing about warehouse output changes on
> upgrade. Only the *editor's dropdown* stops offering them.

This is a deliberate asymmetry: **the writer gets stricter, the reader stays tolerant.** It is
what makes this change zero-risk to deploy — an existing profile behaves identically until a
human chooses to rewrite a rule.

Do **not** add the three to `rules.py`'s `deprecated_actions` list (`rules.py:1055`). That list
*skips* actions with a warning, which would silently stop populating `Status_Note` for every
client that already uses them.

## Design

### §1 — Authoring surface shrinks

`gui/settings/fields.py`:

```python
ACTION_TYPES: list[str] = [
    "ADD_INTERNAL_TAG",
    "REMOVE_INTERNAL_TAG",
    "SET_STATUS",
    "COPY_FIELD",
    "CALCULATE",
    "ALERT_NOTIFICATION",
    "ADD_PRODUCT",
]

# Executed by the engine, but no longer offered when building a new rule.
# A rule already using one keeps working; the editor flags it. See
# docs/superpowers/specs/2026-08-14-rule-actions-internal-tags-design.md.
LEGACY_ACTION_TYPES: list[str] = ["ADD_TAG", "ADD_ORDER_TAG", "SET_MULTI_TAGS"]
```

`ACTION_TYPES` is the dropdown's contents and nothing else. `LEGACY_ACTION_TYPES` is the single
source of truth for "flag this."

### §2 — Round-trip safety (the actual risk in this change)

Two silent-corruption paths open up the moment a name leaves `ACTION_TYPES`. Both must be closed
in the same change:

**(a) The combo silently retypes the action.** `_add_action_widget` does
`type_combo.addItems(ACTION_TYPES)` then `type_combo.setCurrentText(config["type"])`
(`rules.py:1180-1181`). On a non-editable `QComboBox`, `setCurrentText` with an absent string is
a **no-op** — the combo stays on index 0. A rule loaded with `ADD_TAG` would display
`ADD_INTERNAL_TAG`, and `collect()` would write `ADD_INTERNAL_TAG` back on the next save. That is
exactly the silent rewrite decision 2 forbids.

*Fix:* when the loaded config's type is not in `ACTION_TYPES`, append it to **that row's** combo
before `setCurrentText`:

```python
configured_type = config.get("type", ACTION_TYPES[0])
if configured_type and configured_type not in ACTION_TYPES:
    type_combo.addItem(configured_type)
type_combo.setCurrentText(configured_type)
```

Per-row, not global — a new action row still only offers the seven current types.

**(b) The value is dropped on save.** `_on_action_type_changed` (`rules.py:1234`) and `collect()`
(`rules.py:1381`, `:1394`) both branch on literal name lists. If the legacy names are removed
from those lists, the row builds no value widget and `collect()` emits `{"type": "ADD_TAG"}` with
no `value` — the rule's tag text is lost on the next save of an unrelated setting.

*Fix:* those two branch lists keep the legacy names. They are internal dispatch, not the
dropdown. Concretely, the current `["ADD_TAG", "ADD_ORDER_TAG", "ADD_INTERNAL_TAG",
"SET_STATUS"]` list splits in two, because §4 gives the tag actions a combo instead of a line
edit:

| branch | types | widget | `collect()` reads |
|---|---|---|---|
| plain value | `ADD_TAG`, `ADD_ORDER_TAG`, `SET_STATUS` | `QLineEdit` | `.text()` |
| tag value | `ADD_INTERNAL_TAG`, `REMOVE_INTERNAL_TAG` | editable combo (§4) | `.currentText()` |

The `SET_MULTI_TAGS` branch stays exactly as-is in both methods.

Net effect: the only line that actually loses the three names is `ACTION_TYPES`.

### §3 — Legacy flag on the action row

Mirror the pattern #278 established for condition rows (`rules.py:677-694`): wrap the action row's
`QHBoxLayout` in a `QVBoxLayout` and put a hidden, word-wrapped `QLabel` underneath. A hidden
label is skipped by the layout, so a row with nothing to say keeps its current height.

The label shows, in `theme.accent_orange`, when the row's type is in `LEGACY_ACTION_TYPES`:

- `ADD_TAG` / `ADD_ORDER_TAG` — *"Writes the Status_Note text column, not tags. Replace with
  ADD_INTERNAL_TAG to add a real tag."*
- `SET_MULTI_TAGS` — *"Writes the Status_Note text column, not tags. Replace with one
  ADD_INTERNAL_TAG per tag."*

Wording states what the action *does* before what to do about it — the user's mental model is
"this adds a tag", and correcting that is the whole point of the message.

It updates on `currentTextChanged`, so switching a legacy row to `ADD_INTERNAL_TAG` clears the
flag immediately, and (because the legacy name is only in that row's combo) switching away is
one-directional — which is the desired nudge.

No rule-level or page-level warning banner. The flag sits on the row that has the problem.

### §4 — `ADD_INTERNAL_TAG` value becomes an editable combo

Today the value is a bare `QLineEdit`, so a typo silently creates a tag that
`get_tag_category` reports as `"custom"` — no category, no colour, no SKU write-off.

Replace it with an **editable** `WheelIgnoreComboBox` seeded from the configured tag vocabulary:
every `tags` entry across `_normalize_tag_categories(tag_categories)`, deduped and sorted.

- **Editable, not fixed.** A tag the user is about to create must remain typeable, and this also
  guarantees an unknown value loaded from config round-trips (same failure mode as §2a).
- **Seeded from a snapshot,** taken when the settings dialog opens. The Tag Categories page lives
  in the same dialog and can add a tag while the Rules page is open; live cross-page sync is not
  worth building for this. Mark with a `ponytail:` comment naming the ceiling.
- **Configured category tags only** — `SYSTEM_TAGS` (`core.py:18`: `Repeat`, `Priority`, `Error`)
  are computed by analysis, and listing them invites rules that fight the analyser. Still
  typeable, since the combo is editable.

This needs `tag_categories` inside `RulesPage`, which does not have it today. Add it as a keyword
argument:

```python
def __init__(self, rules: list, analysis_df, tag_categories: dict | None = None, parent=None):
```

and pass `self.config_data.get("tag_categories", {})` at `gui/settings/window.py:141`. Defaulting
to `None` keeps every existing `RulesPage(rules, df)` call — including the ones in
`tests/test_rules_page.py` — working with an empty vocabulary.

`collect()` reads `.currentText()` for this action instead of `.text()` — see the table in §2b.

### §5 — `REMOVE_INTERNAL_TAG`

A rule can add a tag but not remove one, even though `tag_manager.remove_tag` already exists and
is unused by the engine. Symmetric with `ADD_INTERNAL_TAG`, same order-level expansion:

```python
elif action_type == "REMOVE_INTERNAL_TAG":
    from shopify_tool.tag_manager import expand_to_order_rows, remove_tag

    order_mask = expand_to_order_rows(df, matches)
    current_tags = df.loc[order_mask, "Internal_Tags"]
    df.loc[order_mask, "Internal_Tags"] = current_tags.apply(
        lambda t, value=value: remove_tag(t, value)
    )
```

Also:

- `_prepare_df_for_actions` (`rules.py:918-921`): add it to the `Internal_Tags` branch. Removing a
  tag from a column that does not exist is a no-op, but the column must exist to be read.
- Order-level dispatcher (`rules.py:864-871`): **no change needed.** It lands in the
  `apply_to_first` bucket alongside `ADD_INTERNAL_TAG`, and both expand to the full order
  internally. Worth a comment saying so, since the bucket name reads misleadingly.
- Editor: same value combo as §4 (§4 and §5 share one branch).

### §6 — Help text

Rewrite `gui/settings/rules.py:397-400` to describe what the actions actually do, and drop the
invented per-row distinction:

```
  → Actions:
     • ADD_INTERNAL_TAG / REMOVE_INTERNAL_TAG - order-level structured tags
       (applied to every row of the order)
     • all other actions - applied to the order's first row
```

`gui/rule_test_dialog.py` describes actions too and needs the same treatment, at
`:398-403`: `ADD_TAG` says `"→ Appends to Status_Note column"` and should say so as a
correction rather than a neutral description; `ADD_ORDER_TAG` and `SET_MULTI_TAGS` fall through
with no description at all and should get one; `REMOVE_INTERNAL_TAG` needs a branch.

Its display-column list (`:487-496`) already carries both `Status_Note` and `Internal_Tags`, so
it needs no change.

## Data model

**Nothing changes on disk.** No new config key, no `profile_migrations.py` entry, no version bump.
The rules JSON schema is unchanged; a profile written by this version is readable by the previous
one and vice versa. This is a direct consequence of decision 2 and is what keeps a multi-PC
warehouse on mixed versions safe.

## Testing

Engine (`tests/test_rules.py`, real engine, no mocks):

1. `REMOVE_INTERNAL_TAG` removes a tag from every row of a matched order, and is a no-op for a
   tag that is not present.
2. `REMOVE_INTERNAL_TAG` on an article-level rule that matches one line still clears the tag on
   the whole order (the `expand_to_order_rows` contract).
3. **Regression guard:** `ADD_TAG`, `ADD_ORDER_TAG` and `SET_MULTI_TAGS` still write
   `Status_Note` exactly as before. The existing tests at `test_rules.py:29-296` already cover
   this — the job here is to confirm none of them are weakened, not to add more.

Editor (`tests/test_rules_page.py`, qtbot):

4. **The important one:** load a rule whose action is `ADD_TAG` with a value, call `collect()`
   without touching anything, and assert the result is still `{"type": "ADD_TAG", "value": ...}`.
   This is the test that fails if either §2a or §2b is missed.
5. A legacy action row shows its flag label; an `ADD_INTERNAL_TAG` row does not.
6. Switching a legacy row's type to `ADD_INTERNAL_TAG` hides the flag.
7. The value combo is seeded with the configured category tags, and a tag typed into it that is
   not in the list survives `collect()`.

## Out of scope

- Migrating or rewriting existing rules — explicitly rejected (decision 2).
- Removing the `Status_Note` column, its manual add-note UI (`gui/actions_handler.py:1018`) or its
  export (`core.py:142`). Rules stop being able to author it; the column stays.
- Cleaning up `deprecated_actions` (`rules.py:1055`) — untouched, and deliberately not extended.
- The `int → float64` widening and Rule Test change-detector warts left by #277. Both are
  `COPY_FIELD`/`CALCULATE` dtype issues with no connection to tag actions.
- Live sync between the Tag Categories page and the Rules page's tag vocabulary (§4).
