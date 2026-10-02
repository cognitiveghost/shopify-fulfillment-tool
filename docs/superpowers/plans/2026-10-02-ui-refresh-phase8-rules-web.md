# UI refresh phase 8: Rules and Test rule on the web tier. Implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Qt Rules editor and its Test dialog with a Rules page in the Client settings web
document: the mockup's rule list, an editor that opens inside a rule's row, on/off per rule, reordering by
button and by drag, and Test rule as a panel that runs the rule on the whole analysis.

**Architecture:** Rules becomes a fourth *draft* beside phase 7's three. `RulesDraft`
(`gui/settings/rules_state.py`, no widget) holds the rules, takes every edit through `apply(action, args)`,
words everything the page shows in `view()`, and meets `PageContract`, so `SettingsWindow` saves and marks it
like any other page. `gui/web/settings_rules.js` draws that view inside the settings document and reports
each edit through `SettingsBridge.edit`. Test rule is a pure function (`gui/settings/rule_test.py`) that
`SettingsWebHost` runs on a `Worker` and pushes to the page as `state["test"]`. The engine learns one thing:
a rule stored with `enabled: False` is skipped.

**Tech Stack:** Python 3.14, PySide6 (Qt widgets, QtWebEngine, QWebChannel), pandas, plain CSS and
JavaScript (no build step, no framework), pytest + pytest-qt driving a real Chromium offscreen.

**Spec:** `docs/superpowers/specs/2026-10-02-ui-refresh-phase8-rules-web-design.md`. Read it whole before starting; this plan argues from it. Copy (every label, sentence
and empty state) is in spec §4.4, §4.5, §4.8 and §6.3 and is verbatim. Mockup:
`docs/design/ui-refresh/mockups/client-settings.html`, states Rules, Rules empty and Test rule. To read exact
values, unpack the bundle with the script in `docs/design/ui-refresh/mockups/README.md`.

**Every code block in this plan was run before the plan was written**, in a scratch copy of the repo at
bcf91d5 (code identical to `origin/main` at 62bc88e). This document was generated from that copy: each
"Create" block is the file as it ran, and each "Find exactly / Replace with" pair was applied to the file as
the earlier tasks left it. There, each task's own tests failed as its "Expected" line says before the
implementation and passed after it, `ruff check .` passed, and the whole suite passed at the end but for the
baseline failures below. The dialog was rendered in both themes and compared with the mockup. If a block
fails for you, suspect a typo in transcription, or a change on `main` since 62bc88e, before you suspect the
design, and say what differed.

## Global Constraints

- Work in `/home/gloopy/Desktop/Projects/shopify-fulfillment-tool/.claude/worktrees/dr-20` on branch `dr/20-ui-refresh-phase-8-client-settings-on-th`. Never `cd` anywhere else. If `.venv` is missing, run
  `./scripts/setup_venv.sh`.
- Run tests only as `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q <paths>`. A hook blocks any other Bash text containing the word "pytest", so
  write test files with Write/Edit, never with heredocs.
- Git: `/usr/bin/git`, one plain command per Bash call, with no `;`, `&&` or `$VAR`. Commit with
  `/usr/bin/git commit -F <absolute path to a message file>`; write the message file under your job's tmp
  dir. End every message with the attribution lines your session is given. The post-commit hook refreshes
  the graphify graph; there is nothing to run by hand.
- **Transcribe code blocks exactly.** A block headed "Create" is the whole file. A pair headed "Find
  exactly" / "Replace with" is one Edit: the first block is the `old_string`, the second the `new_string`,
  and the first occurs once in the file at the moment you reach it. Apply a file's edits in the order
  given. "Append at the end of the file" means: Read the file, then Edit its last lines to add the block
  after them, leaving exactly two blank lines between the file's old last line and the block's first line
  in a Python file, and one in a CSS file.
- No hex, colour name, `rgb()`, px font size (that includes the `font:` shorthand), `transition`,
  `transform`, gradient or `opacity` in any file under `gui/` (`shared/style_lint.py`, enforced by
  `tests/test_style_literals_guard.py`). `box-shadow` only as `var(--card-shadow)`,
  `var(--overlay-shadow)` or `none`, and only in a `.css` file. Never set `element.style.*` to a colour
  from JavaScript: use a class. `shared/theme.py` itself is not scanned; the one `rgba()` this plan adds
  lives there (Task 2).
- The lint reads a colour word after a colour property up to the next `;`. So every CSS declaration ends
  with `;`, including the last one in a rule.
- CSS custom properties from the theme are hyphenated: the token `surface_raised` is
  `var(--surface-raised)`. Type sizes are `var(--type-caption-size)`, `--type-body-size`,
  `--type-label-size`, `--type-heading-size`. The mono face is `var(--font-family-mono)`.
- ADR 0018: a decorative line (card edge, divider) is `--border-subtle`. The edge of a button, an input or
  a box the eye must find is `--border`.
- **Everything from the profile or the analysis goes through `esc()` before it reaches `innerHTML`** in
  `settings_rules.js`: rule names, field names, values, tags, order numbers. A rule's name can hold `<`,
  `"` or anything else.
- **The page sends strings and booleans only.** A uid and a position travel as strings (`"2"`). A
  JavaScript number arrives in Python as a float, and the draft drops it.
- **Python owns every value and every sentence.** `settings_rules.js` validates nothing, filters nothing
  and words nothing. Its own state is which menu is open, a drag in progress, and whether the Test panel
  was showing.
- **No UI call from a background thread.** The Test worker returns a dict; the host receives it through
  a signal connected to a bound method (Task 6).
- A rule keeps what it was stored with. The draft never replaces a field, an operator, a value or an
  action it has no control for (spec §4.1, §11).
- `shared/` changes in `shared/theme.py` only (Task 2). Never edit `packing-tool/shared/`.
- No `pyproject.toml`. No new dependency. No direct commit to `main`.
- `ruff check .` must pass after every task.

## Baseline

On this dev VM three tests fail before any change, and they are not yours:
`tests/test_label_printing.py::TestImageToZpl::test_black_pixels_become_set_bits`,
`::test_invert_flips_the_polarity` and `::test_rotate_and_invert_compose`. Every other test passes on
bcf91d5. Every test that passes there must pass after every task, unless the task rewrites or deletes it
and says so. The whole suite takes about eight minutes; run it twice, at the end of Task 7 (the task that
deletes files) and in Task 8. Each other task runs the files it names.

Chromium prints `SharedImageManager::ProduceMemory`, `libEGL` and `VMware: No 3D enabled` lines while the
web tests run. The rule engine logs `[RULE ENGINE] Invalid regex pattern` when a test feeds it one. They are
noise, not failures.

## Review Focus

The inputs the spec implies and a person will meet, most likely first. Each has its test in the task that
owns the code.

1. **A value far longer than its row**: an `in list` of fifty SKUs, a long regex. The summary chip is cut
   with an ellipsis and carries the whole value as its title, and the page never scrolls sideways. Test:
   `test_a_very_long_value_is_cut_and_never_widens_the_page` (Task 5).
2. **A profile edited by hand into an odd shape**: an entry in `rules` that is not an object, `steps` that
   is text, `conditions: null`, a number or a list as a value. The page opens, lists what it can read and
   saves without raising. Test: `test_a_profile_edited_into_odd_shapes_still_loads_and_saves` (Task 3).
3. **Text with markup in it**: a rule named `<b>"VIP" & co</b>`, a tag with a quote. It is drawn as text
   and comes back as typed. Test: `test_markup_in_a_name_or_a_value_is_drawn_as_text` (Task 5).
4. **An analysis the test did not expect**: a line with no order number, a column of lists (`Lot_Details`),
   a non-text column name. Test rule counts and lists without raising. Test:
   `test_an_analysis_with_a_blank_order_number_and_list_cells_is_still_tested` (Task 4).
5. **The dialog closed while a test is still running.** The result has nowhere to go and nothing is
   raised. Test: `test_a_result_that_arrives_after_the_host_is_gone_raises_nothing` (Task 6).

Also covered where it lives: an edit the draft does not know, or of the wrong shape
(`test_an_edit_that_is_unknown_misshapen_or_changes_nothing_is_dropped`, Task 3); a result from a test that
was replaced by another (`test_a_result_from_a_test_that_was_replaced_is_dropped`, Task 6); a filter text
that is a regex character (`test_a_filter_is_plain_text`, Task 3); a rule that is off still runs under Test
(`test_a_rule_that_is_off_still_runs`, Task 4).

## File map

| File | Task | What it is |
|---|---|---|
| `shopify_tool/rules.py` | 1 | `RuleEngine` skips a rule whose `enabled` is `False` |
| `shared/theme.py` | 2 | The `scrim` token; the `--color-scheme` variable |
| `gui/settings/rules_state.py` (new) | 3 | `RulesDraft`, `rule_fields`, `value_kind`, the sentences |
| `gui/settings/rule_test.py` (new) | 4 | `run_rule_test`, `running_view`, `failed_view` |
| `gui/settings/bridge.py` | 5 | `testRule`, `closeTest` |
| `gui/web/settings_rules.js` (new) | 5 | The Rules page and the Test panel |
| `gui/web/settings.js`, `settings.css`, `settings.html` | 5 | The hooks into the document; the styles; the script tag |
| `gui/settings/web_host.py` | 6 | Runs the test on a worker; reveals a blocked rule |
| `gui/settings/window.py`, `gui/actions_handler.py` | 7 | Rules is a draft; the session's name |
| `gui/rule_validator.py` | 7 | A docstring that named the deleted page |
| `gui/settings/rules.py`, `gui/rule_test_dialog.py` | 7 | Deleted |
| `docs/design/ui-refresh/roadmap.md`, `CONTEXT.md`, renders | 8 | Docs |

Tests: `tests/test_rules.py` (1), `tests/test_theme_palette.py` and `tests/test_theme_css_vars.py` (2),
`tests/test_settings_draft_rules.py` (3), `tests/test_rule_test.py` (4), `tests/test_settings_bridge.py` and
`tests/test_settings_rules_page.py` (5), `tests/test_settings_web_host.py` (6),
`tests/test_settings_rules_window.py`, `tests/test_actions_handler.py` and
`tests/audit/test_03_rule_engine.py` (7). Deleted in Task 7: `tests/test_rules_page.py`,
`tests/test_settings_page_rules.py`, `tests/test_rule_test_dialog.py`; their cases live in the Task 3 and
Task 4 files.

---

### Task 1: The engine skips a rule that is off

**Files:**
- Modify: `shopify_tool/rules.py` (`RuleEngine.__init__`)
- Test: `tests/test_rules.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `RuleEngine(rules)` leaves out every rule whose `enabled` is `False`. A rule with no `enabled`
  key, or with `True`, runs. `RuleEngine.execution_order(rules)` is unchanged and still returns every rule.
  Tasks 3 and 4 rely on both.

Spec §7. `shopify_tool/core.py` is the only caller that runs saved rules, and it needs no change.

- [ ] **Step 1: Write the failing tests**

**Modify `tests/test_rules.py`.**
 Append at the end of the file:

```python
def _tagging(name, **extra):
    """An article rule that tags every order holding SKU A with its own name."""
    return {"name": name, "level": "article", **extra, "steps": [{
        "conditions": [{"field": "SKU", "operator": "equals", "value": "A"}],
        "match": "ALL", "actions": [{"type": "ADD_INTERNAL_TAG", "value": name}]}]}


def _all_tags(df):
    return {tag for value in df["Internal_Tags"] for tag in parse_tags(value)}


def test_a_rule_that_is_off_is_skipped():
    out = RuleEngine([_tagging("OFF", enabled=False), _tagging("ON")]).apply(_status_frame())
    assert _all_tags(out) == {"ON"}


@pytest.mark.parametrize("extra", [{}, {"enabled": True}], ids=["no flag", "on"])
def test_a_rule_runs_unless_it_is_stored_off(extra):
    out = RuleEngine([_tagging("T", **extra)]).apply(_status_frame())
    assert _all_tags(out) == {"T"}


def test_an_engine_of_off_rules_changes_nothing():
    df = _status_frame()
    engine = RuleEngine([_tagging("OFF", enabled=False)])
    out = engine.apply(df)
    assert engine.rules == []
    assert _all_tags(out) == set()
    assert not engine.matched_rows.any()


def test_execution_order_still_lists_a_rule_that_is_off():
    """The Rules page orders every rule with it, off or not."""
    off = _tagging("off", enabled=False, priority=1)
    on = _tagging("on", priority=2)
    assert [r["name"] for r in RuleEngine.execution_order([on, off])] == ["off", "on"]
```

- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_rules.py`
Expected: `2 failed, 48 passed`: `test_a_rule_that_is_off_is_skipped` and `test_an_engine_of_off_rules_changes_nothing`. The other new tests already pass: a rule with no flag runs today, and `execution_order` never looked at the flag.

- [ ] **Step 3: Skip the rules that are off**

**Modify `shopify_tool/rules.py`.**
 Find exactly:

```python
                dictionary represents a single rule. A rule consists of
                conditions and actions. Optional 'priority' field controls
                execution order (lower number = higher priority = executes first).
        """
        import logging
        logger = logging.getLogger(__name__)

        if not rules_config:
            self.rules = []
            return

        # Deep-copy so we never mutate the caller's config in-place
        rules_working = copy.deepcopy(rules_config)

        # Normalize: add default priority to rules without it
        self.rules = self._normalize_priorities(rules_working)
```

Replace with:

```python
                dictionary represents a single rule. A rule consists of
                conditions and actions. Optional 'priority' field controls
                execution order (lower number = higher priority = executes first).
                A rule stored with 'enabled': False is off and never runs;
                a rule with no such key is on.
        """
        import logging
        logger = logging.getLogger(__name__)

        # Deep-copy so we never mutate the caller's config in-place
        rules_working = [
            copy.deepcopy(rule)
            for rule in rules_config or []
            if rule.get("enabled", True) is not False
        ]
        skipped = len(rules_config or []) - len(rules_working)
        if skipped:
            logger.info(f"[RULE ENGINE] Skipped {skipped} rules that are off")

        if not rules_working:
            self.rules = []
            return

        # Normalize: add default priority to rules without it
        self.rules = self._normalize_priorities(rules_working)
```

- [ ] **Step 4: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_rules.py tests/audit/test_03_rule_engine.py tests/test_rule_settle.py`
Expected: all pass. (`81 passed`.)

- [ ] **Step 5: Commit**

`/usr/bin/git add -A`, then write this message to a file under your job's tmp dir and commit with
`/usr/bin/git commit -F <that file>`. Subject: `Rule engine: a rule stored with enabled false is skipped`. Body: one or two sentences: missing means on, and execution_order still lists every rule. End the message with the
attribution lines your session is given.

### Task 2: The `scrim` token and the `--color-scheme` variable

**Files:**
- Modify: `shared/theme.py`
- Test: `tests/test_theme_palette.py`, `tests/test_theme_css_vars.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `ThemeTokens.scrim` (a CSS value, `"rgba(0,0,0,0.35)"` in both themes), which `theme_css_vars`
  emits as `--scrim`; and a derived `--color-scheme`, `light` or `dark`. Task 5's stylesheet reads both.

Spec §8. `scrim` is a CSS value like the two shadows, not a hex colour, so it joins `_CSS_VALUE_FIELDS`:
that is what gets it emitted and checked. `shared/theme.py` is the canonical copy (ADR 0017); Packing Tool
picks the change up at its next sync and needs no work.

- [ ] **Step 1: Write the failing tests**

**Modify `tests/test_theme_palette.py`.**
 Find exactly:

```python
        "none",
    ),
    "overlay_shadow": ("0 4px 12px rgba(26,26,26,0.2)", "none"),
}

THEMES = pytest.mark.parametrize("theme", [LIGHT_THEME, DARK_THEME], ids=["light", "dark"])
```

Replace with:

```python
        "none",
    ),
    "overlay_shadow": ("0 4px 12px rgba(26,26,26,0.2)", "none"),
    # New in phase 8 (spec 2026-10-02 section 8): the backdrop behind a panel
    # that takes the page over. The mockup's value, in both themes.
    "scrim": ("rgba(0,0,0,0.35)", "rgba(0,0,0,0.35)"),
}

THEMES = pytest.mark.parametrize("theme", [LIGHT_THEME, DARK_THEME], ids=["light", "dark"])
```

**Modify `tests/test_theme_css_vars.py`.**
 Find exactly:

```python
    assert decls["--card-border"] == theme.card_border
    assert decls["--card-shadow"] == theme.card_shadow
    assert decls["--overlay-shadow"] == theme.overlay_shadow
```

Replace with:

```python
    assert decls["--card-border"] == theme.card_border
    assert decls["--card-shadow"] == theme.card_shadow
    assert decls["--overlay-shadow"] == theme.overlay_shadow
    assert decls["--scrim"] == theme.scrim


@pytest.mark.parametrize("theme", [LIGHT_THEME, DARK_THEME], ids=lambda t: t.name)
def test_the_theme_names_its_colour_scheme(theme, density):
    """A page that opts in (color-scheme: var(--color-scheme)) gets Chromium's
    own popups, the date picker and the suggestion list, in the theme."""
    density("desk")
    assert _parse(theme_css_vars(theme))["--color-scheme"] == theme.name
```

- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_theme_palette.py tests/test_theme_css_vars.py`
Expected: `5 failed, 50 passed`: `test_the_palette_is_the_mockups_fitted_to_the_floors[scrim]` (`ThemeTokens` has no `scrim`), and both cases of `test_the_css_value_tokens_reach_the_web_tier_verbatim` and of `test_the_theme_names_its_colour_scheme` (`KeyError`).

- [ ] **Step 3: Add the token and the variable**

**Modify `shared/theme.py`.**
 Find exactly:

```python
    card_border: str
    card_shadow: str
    overlay_shadow: str

    # --- Solid accent fill; on_accent is the text that sits on it (spec 3.4a) ---
    # hover and active are per theme: dark fills lighten toward white.
```

Replace with:

```python
    card_border: str
    card_shadow: str
    overlay_shadow: str
    # Phase 8 (spec 2026-10-02 section 8): the backdrop behind a panel that
    # takes a web page over. A CSS value too.
    scrim: str

    # --- Solid accent fill; on_accent is the text that sits on it (spec 3.4a) ---
    # hover and active are per theme: dark fills lighten toward white.
```

 Find exactly:

```python
    card_border="transparent",
    card_shadow="0 1px 0 rgba(26,26,26,0.07), 0 1px 3px rgba(26,26,26,0.12)",
    overlay_shadow="0 4px 12px rgba(26,26,26,0.2)",
    accent_fill="#303030",
    accent_fill_hover="#1A1A1A",
    accent_fill_active="#000000",
```

Replace with:

```python
    card_border="transparent",
    card_shadow="0 1px 0 rgba(26,26,26,0.07), 0 1px 3px rgba(26,26,26,0.12)",
    overlay_shadow="0 4px 12px rgba(26,26,26,0.2)",
    scrim="rgba(0,0,0,0.35)",
    accent_fill="#303030",
    accent_fill_hover="#1A1A1A",
    accent_fill_active="#000000",
```

 Find exactly:

```python
    card_border="#2E2F34",
    card_shadow="none",
    overlay_shadow="none",
    accent_fill="#E3E3E3",
    accent_fill_hover="#FFFFFF",
    accent_fill_active="#C4C4C8",
```

Replace with:

```python
    card_border="#2E2F34",
    card_shadow="none",
    overlay_shadow="none",
    scrim="rgba(0,0,0,0.35)",
    accent_fill="#E3E3E3",
    accent_fill_hover="#FFFFFF",
    accent_fill_active="#C4C4C8",
```

 Find exactly:

```python
)

# Tokens the web tier reads that are CSS values rather than colours: an edge
# that is `transparent` in one theme, and shadows. Not hex-checked; checked
# instead for the characters that would close the :root block they land in.
_CSS_VALUE_FIELDS = ("card_border", "card_shadow", "overlay_shadow")

# Legacy name -> canonical token. Each pair carries the same literal in both
# theme constructors; validate_theme asserts they stay equal so the
```

Replace with:

```python
)

# Tokens the web tier reads that are CSS values rather than colours: an edge
# that is `transparent` in one theme, shadows, and the translucent backdrop.
# Not hex-checked; checked instead for the characters that would close the
# :root block they land in.
_CSS_VALUE_FIELDS = ("card_border", "card_shadow", "overlay_shadow", "scrim")

# Legacy name -> canonical token. Each pair carries the same literal in both
# theme constructors; validate_theme asserts they stay equal so the
```

 Find exactly:

```python
        if f.name != "type_overrides":
            derived[_css_name(f.name)] = _css_value(getattr(profile, f.name))

    # A token named like a derived value would be overwritten without a sound.
    clash = derived.keys() & decls.keys()
    if clash:
```

Replace with:

```python
        if f.name != "type_overrides":
            derived[_css_name(f.name)] = _css_value(getattr(profile, f.name))

    # For a page that opts in with `color-scheme: var(--color-scheme)`:
    # Chromium then draws its own popups (a date picker, a suggestion list)
    # in the theme.
    derived["--color-scheme"] = "dark" if theme.name == "dark" else "light"

    # A token named like a derived value would be overwritten without a sound.
    clash = derived.keys() & decls.keys()
    if clash:
```

- [ ] **Step 4: Run the theme tests and the style lint**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_theme_palette.py tests/test_theme_css_vars.py tests/test_theme_contrast.py tests/test_style_literals_guard.py`
Expected: all pass. (`94 passed`.) `tests/test_theme_contrast.py` now also checks that `scrim` cannot break
out of its declaration: it is parametrized over `_CSS_VALUE_FIELDS`.

- [ ] **Step 5: Commit**

`/usr/bin/git add -A`, then write this message to a file under your job's tmp dir and commit with
`/usr/bin/git commit -F <that file>`. Subject: `Theme: a scrim token and a --color-scheme variable for the web tier`. Body: say that shared/ gains one CSS-value token and one derived variable, and that Packing Tool needs no work. End the message with the
attribution lines your session is given.

### Task 3: `RulesDraft`

**Files:**
- Create: `gui/settings/rules_state.py`
- Test: `tests/test_settings_draft_rules.py`

**Interfaces:**
- Consumes: `PageContract` (`gui/settings/contract.py`); `_shaped(args, *kinds)` from
  `gui/settings/page_state.py`; `ACTION_TYPES`, `CONDITION_OPERATORS` from `gui/settings/fields.py`;
  `condition_error(operator, value) -> str | None` and `validate_list(text) -> (ok, count, message)` from
  `gui/rule_validator.py`; `RuleEngine.execution_order`, `RuleEngine.ORDER_LEVEL_FIELDS` and
  `_parse_date_safe` from `shopify_tool/rules.py`; `get_unique_column_values(df, column)` from
  `shopify_tool/core.py`.
- Produces, for Tasks 5 to 7:
  - `RulesDraft(rules: list, analysis_df=None, tag_categories: dict | None = None)`, a `PageContract`.
  - `apply(action: str, args) -> bool`: the actions of spec §3.3.
  - `view() -> dict`: spec §4.7. `view()["rules"]["groups"][n]["rows"][m]` is a row; the open row's
    `"editor"` is a dict, every other row's is `None`.
  - `collect() -> {"rules": [...]}`, `blocker() -> str | None`, `blocker_key() -> str`,
    `validate() -> (bool, list[str])`.
  - `test_config(uid: str) -> dict | None`.
  - `rules`: the list of model rules, each a dict with `uid`, `name`, `level`, `enabled`, `steps`, `extra`.
  - `open_uid`, `filter`, `analysis_df`.
  - Module names the tests and the page tests import: `rule_fields`, `value_kind`, `CLEAR_FILTER`,
    `HOLD_HINT`, `NO_DATE`, `NO_FIELD`, `NOT_AVAILABLE`, `QUANTITY_PROBLEM`, `RETIRED_ONE`, `RETIRED_MANY`,
    `SUGGESTION_LIMIT`, `TEST_BLOCKED`, `TEST_NO_ANALYSIS`, `TEST_NO_CONDITION`, `UNKNOWN_ACTION`.

Spec §3.3 and §4. This file replaces the logic of `gui/settings/rules.py`; that file is deleted in Task 7,
so until then both exist. The draft has no widget and needs no `QApplication`: the tests are plain Python.

Three things the tests pin that are easy to get wrong:

- A rule's uid is a counter the draft hands out in list order as it loads, starting at `"1"`. It is never
  written to the profile.
- `enabled` is written only when a rule is off, so a profile opened and saved with no edit is unchanged.
- `filter`, `open`, `close` and `reveal` return `True` (the page must redraw) but change nothing
  `collect()` returns, so they never mark the page unsaved.

- [ ] **Step 1: Write the failing tests**

**Create `tests/test_settings_draft_rules.py`:**

```python
"""RulesDraft: the rules behind the Rules page (phase 8 spec sections 3.3 and 4).

No widget and no Chromium: the draft is plain Python. Rules are addressed by
the uid the draft hands out: "1", "2", ... in the order it lists them.
"""

import copy
import json

import pandas as pd
import pytest

from gui.settings.fields import ACTION_TYPES, CONDITION_OPERATORS, LEGACY_ACTION_TYPES
from gui.settings.rules_state import (
    CLEAR_FILTER,
    HOLD_HINT,
    NO_DATE,
    NO_FIELD,
    NOT_AVAILABLE,
    QUANTITY_PROBLEM,
    RETIRED_MANY,
    RETIRED_ONE,
    SUGGESTION_LIMIT,
    TEST_BLOCKED,
    TEST_NO_ANALYSIS,
    TEST_NO_CONDITION,
    UNKNOWN_ACTION,
    RulesDraft,
    rule_fields,
    value_kind,
)
from shopify_tool.rules import RuleEngine

TAG_CATEGORIES = {
    "version": 2,
    "categories": {
        "handling": {"label": "Handling", "color": "#FF0000", "tags": ["FRAGILE", "GIFT"], "order": 1},
        "shipping": {"label": "Shipping", "color": "#00FF00", "tags": ["EXPRESS", "GIFT"], "order": 2},
    },
}


@pytest.fixture
def analysis_df():
    return pd.DataFrame(
        {
            "Order_Number": ["A", "B"],
            "SKU": ["x", "y"],
            "Quantity": [1, 2],
            "Notes": ["leave at door", ""],
            "_internal": [0, 0],
        }
    )


def cond(field="SKU", operator="equals", value="x"):
    return {"field": field, "operator": operator, "value": value}


def tag(value="T"):
    return {"type": "ADD_INTERNAL_TAG", "value": value}


def rule(name="r", level="article", conditions=None, actions=None, match="ALL", **extra):
    return {
        "name": name,
        "level": level,
        **extra,
        "steps": [
            {
                "conditions": [cond()] if conditions is None else conditions,
                "match": match,
                "actions": [tag()] if actions is None else actions,
            }
        ],
    }


def names(draft):
    return [r["name"] for r in draft.rules]


def stored(draft):
    return draft.collect()["rules"]


def rows(draft):
    return [row for group in draft.view()["rules"]["groups"] for row in group["rows"]]


def editor(draft):
    return next(row["editor"] for row in rows(draft) if row["open"])


def opened(rules, analysis_df=None, **kwargs):
    """A draft with its first rule open."""
    draft = RulesDraft(rules, analysis_df, **kwargs)
    assert draft.apply("open", ["1"])
    return draft


# --- loading -----------------------------------------------------------------


def test_rules_load_in_the_order_the_engine_runs_them():
    given = [
        rule("o1", "order", priority=1),
        rule("a2", priority=2),
        rule("a1", priority=1),
        rule("late"),
    ]
    draft = RulesDraft(given)
    assert names(draft) == [r["name"] for r in RuleEngine(given).rules]
    assert names(draft) == ["a1", "a2", "late", "o1"]


def test_the_callers_rules_are_not_written_to():
    given = [rule("a", actions=[{"type": "SET_STATUS", "value": "Ready"}])]
    before = copy.deepcopy(given)
    draft = RulesDraft(given)
    draft.apply("rule_name", ["1", "renamed"])
    assert given == before


def test_the_old_format_loads_as_one_step():
    old = {
        "name": "old",
        "match": "ANY",
        "conditions": [cond()],
        "actions": [tag()],
    }
    assert stored(RulesDraft([old])) == [
        {
            "name": "old",
            "priority": 1,
            "level": "article",
            "steps": [{"conditions": [cond()], "match": "ANY", "actions": [tag()]}],
        }
    ]


@pytest.mark.parametrize(
    "match, read", [("any", "ANY"), ("ANY", "ANY"), ("all", "ALL"), ("either", "ALL"), (None, "ALL")]
)
def test_match_loads_as_the_engine_reads_it(match, read):
    draft = RulesDraft([rule(match=match)])
    assert stored(draft)[0]["steps"][0]["match"] == read


def test_a_rule_with_no_steps_gets_one_empty_step():
    draft = RulesDraft([{"name": "bare"}])
    assert stored(draft)[0]["steps"] == [{"conditions": [], "match": "ALL", "actions": []}]


def test_a_stale_status_loads_as_the_hold():
    draft = RulesDraft([rule(actions=[{"type": "SET_STATUS", "value": "Fulfillable"}])])
    assert stored(draft)[0]["steps"][0]["actions"] == [
        {"type": "SET_STATUS", "value": "Not Fulfillable"}
    ]


def test_set_multi_tags_loads_its_list_as_text():
    draft = RulesDraft([rule(actions=[{"type": "SET_MULTI_TAGS", "tags": ["A", "B"]}])])
    assert stored(draft)[0]["steps"][0]["actions"] == [{"type": "SET_MULTI_TAGS", "value": "A, B"}]


@pytest.mark.parametrize("legacy", ["ADD_TAG", "ADD_ORDER_TAG"])
def test_a_retired_action_survives_untouched(legacy):
    action = {"type": legacy, "value": "KEEP_ME"}
    assert stored(RulesDraft([rule(actions=[action])]))[0]["steps"][0]["actions"] == [action]


def test_an_actions_extra_keys_survive():
    action = {"type": "ADD_PRODUCT", "sku": "GIFT", "quantity": 3, "product_name": "Bonus pen"}
    assert stored(RulesDraft([rule(actions=[action])]))[0]["steps"][0]["actions"] == [action]


def test_add_product_with_no_quantity_takes_one():
    draft = RulesDraft([rule(actions=[{"type": "ADD_PRODUCT", "sku": "GIFT"}])])
    assert stored(draft)[0]["steps"][0]["actions"][0]["quantity"] == 1


def test_an_unknown_operator_field_and_action_are_kept():
    given = rule(
        conditions=[cond("Mystery", "sounds like", "x")],
        actions=[{"type": "SET_PRIORITY", "value": "High"}],
    )
    assert stored(RulesDraft([given]))[0]["steps"] == given["steps"]


def test_a_profile_edited_into_odd_shapes_still_loads_and_saves(analysis_df):
    """A hand-edited profile: the page opens, lists what it can read, and
    saves without raising."""
    odd = [
        None,
        "not a rule",
        {"name": 7, "steps": "soon"},
        {"name": "nulls", "steps": [{"conditions": None, "actions": None, "match": None}, "x"]},
        {
            "name": "values",
            "steps": [
                {
                    "conditions": [cond("Quantity", "equals", 5), cond("SKU", "in list", ["A", "B"]), "junk", {}],
                    "actions": [{}, "junk", {"type": None}],
                }
            ],
        },
    ]
    draft = RulesDraft(odd, analysis_df)
    assert names(draft) == ["7", "nulls", "values"]
    for model in draft.rules:
        assert draft.apply("open", [model["uid"]])
        assert editor(draft)["steps"]
    saved = stored(draft)
    assert json.loads(json.dumps(saved)) == saved
    assert saved[0]["steps"] == [{"conditions": [], "match": "ALL", "actions": []}]
    assert saved[1]["steps"] == [{"conditions": [], "match": "ALL", "actions": []}]
    assert saved[2]["steps"][0]["conditions"] == [
        cond("Quantity", "equals", 5),
        cond("SKU", "in list", ["A", "B"]),
        cond("", "equals", ""),
    ]
    assert saved[2]["steps"][0]["actions"] == [{"type": "ADD_INTERNAL_TAG"}, {"type": ""}]
    assert draft.blocker() is None
    assert draft.snapshot()


def test_a_rules_other_keys_survive():
    assert stored(RulesDraft([rule(note="keep me")]))[0]["note"] == "keep me"


# --- collect, snapshot ---------------------------------------------------------


def test_the_fixture_config_round_trips():
    """What tests/conftest.py's settings_fixture_config holds under "rules"."""
    rules = [
        {
            "name": "Flag big orders",
            "priority": 1,
            "level": "order",
            "steps": [
                {
                    "conditions": [cond("item_count", "is greater than", "5")],
                    "match": "ALL",
                    "actions": [{"type": "ADD_ORDER_TAG", "value": "BULK"}],
                }
            ],
        }
    ]
    assert RulesDraft(rules).collect() == {"rules": rules}


def test_no_rules_collect_as_an_empty_list():
    assert RulesDraft([]).collect() == {"rules": []}
    assert RulesDraft(None).collect() == {"rules": []}


def test_priority_is_the_place_in_the_list():
    draft = RulesDraft([rule("a", priority=7), rule("b", priority=9)])
    assert [r["priority"] for r in stored(draft)] == [1, 2]


def test_enabled_is_written_only_when_a_rule_is_off():
    draft = RulesDraft([rule("on", enabled=True), rule("off", enabled=False), rule("plain")])
    assert ["enabled" in r for r in stored(draft)] == [False, True, False]
    assert stored(draft)[1]["enabled"] is False


def test_turning_a_rule_off_and_on_again_leaves_no_trace():
    draft = RulesDraft([rule()])
    draft.mark_clean()
    assert draft.apply("rule_enabled", ["1", False])
    assert draft.is_dirty()
    assert draft.apply("rule_enabled", ["1", True])
    assert not draft.is_dirty()


def test_what_is_only_drawn_does_not_mark_the_page_unsaved():
    draft = RulesDraft([rule("alpha"), rule("beta")])
    draft.mark_clean()
    assert draft.apply("filter", ["alp"])
    assert draft.apply("open", ["2"])
    assert draft.apply("close", [])
    assert not draft.is_dirty()


# --- edits the draft drops -------------------------------------------------------


@pytest.mark.parametrize(
    "action, args",
    [
        ("no_such_action", []),
        ("rule_name", ["1"]),
        ("rule_name", ["1", 5]),
        ("rule_name", "1"),
        ("rule_name", ["9", "x"]),
        ("rule_name", ["1", "r"]),
        ("rule_enabled", ["1", "false"]),
        ("rule_enabled", ["1", True]),
        ("rule_level", ["1", "line"]),
        ("rule_level", ["1", "article"]),
        ("rule_move", ["1", "sideways"]),
        ("rule_move", ["1", "up"]),
        ("rule_move", ["1", "down"]),
        ("rule_move_to", ["1", "0"]),
        ("rule_move_to", ["1", "1"]),
        ("rule_move_to", ["1", "-1"]),
        ("rule_delete", ["9"]),
        ("rule_duplicate", ["9"]),
        ("open", ["9"]),
        ("close", []),
        ("filter", [""]),
        ("reveal", ["threshold"]),
        ("reveal", ["rule-9-s0-c0-value"]),
        ("step_remove", ["1", "0"]),
        ("step_remove", ["1", "1"]),
        ("step_match", ["1", "0", "ALL"]),
        ("step_match", ["1", "0", "SOME"]),
        ("step_match", ["1", "4", "ANY"]),
        ("cond_add", ["1", "4"]),
        ("cond_remove", ["1", "0", "4"]),
        ("cond_field", ["1", "0", "0", "No_Such_Column"]),
        ("cond_field", ["1", "0", "0", "item_count"]),
        ("cond_field", ["1", "0", "0", "SKU"]),
        ("cond_operator", ["1", "0", "0", "sounds like"]),
        ("cond_operator", ["1", "0", "0", "equals"]),
        ("cond_value", ["1", "0", "0", "x"]),
        ("cond_value", ["1", "0", "x", "y"]),
        ("action_remove", ["1", "0", "4"]),
        ("action_type", ["1", "0", "0", "ADD_TAG"]),
        ("action_type", ["1", "0", "0", "ADD_INTERNAL_TAG"]),
        ("action_param", ["1", "0", "0", "sku", "x"]),
        ("action_param", ["1", "0", "0", "value", "T"]),
    ],
)
def test_an_edit_that_is_unknown_misshapen_or_changes_nothing_is_dropped(action, args, analysis_df):
    draft = RulesDraft([rule()], analysis_df)
    before = draft.collect()
    assert draft.apply(action, args) is False
    assert draft.collect() == before


# --- the list --------------------------------------------------------------------


def test_filter_lists_the_rules_whose_name_holds_the_text():
    draft = RulesDraft([rule("Alpha"), rule("beta"), rule("alphabet")])
    assert draft.apply("filter", [" ALP "])
    view = draft.view()["rules"]
    assert [row["name"] for row in rows(draft)] == ["Alpha", "alphabet"]
    assert [row["num"] for row in rows(draft)] == ["01", "03"]
    assert view["filtering"] is True
    assert view["no_hits"] == ""


def test_a_filter_is_plain_text():
    draft = RulesDraft([rule("Size (EU)"), rule("Size [US]")])
    draft.apply("filter", ["("])
    assert [row["name"] for row in rows(draft)] == ["Size (EU)"]
    draft.apply("filter", ["[u"])
    assert [row["name"] for row in rows(draft)] == ["Size [US]"]


def test_a_filter_with_no_match_says_so():
    draft = RulesDraft([rule("Alpha")])
    draft.apply("filter", [" zeta "])
    view = draft.view()["rules"]
    assert view["groups"] == []
    assert view["no_hits"] == "No rules named “zeta”."


def test_the_open_rule_is_listed_whatever_the_filter():
    draft = RulesDraft([rule("Alpha"), rule("beta")])
    draft.apply("open", ["2"])
    draft.apply("filter", ["alp"])
    assert [row["name"] for row in rows(draft)] == ["Alpha", "beta"]


def test_open_shows_one_editor_at_a_time():
    draft = RulesDraft([rule("a"), rule("b")])
    assert draft.apply("open", ["1"])
    assert draft.apply("open", ["2"])
    assert [row["open"] for row in rows(draft)] == [False, True]
    assert [row["editor"] is None for row in rows(draft)] == [True, False]
    assert draft.apply("close", [])
    assert not any(row["open"] for row in rows(draft))


def test_reveal_opens_the_rule_a_key_belongs_to():
    draft = RulesDraft([rule("a"), rule("b")])
    assert draft.apply("reveal", ["rule-2-s0-c0-value"])
    assert draft.open_uid == "2"
    assert draft.apply("reveal", ["rule-2-s0-c0-value"]) is False


def test_add_rule_appends_an_article_rule_and_opens_it():
    draft = RulesDraft([rule("a"), rule("o", "order")])
    assert draft.apply("rule_add", [])
    assert names(draft) == ["a", "New rule", "o"]
    new = stored(draft)[1]
    assert new == {
        "name": "New rule",
        "priority": 2,
        "level": "article",
        "steps": [{"conditions": [], "match": "ALL", "actions": []}],
    }
    assert draft.open_uid == draft.rules[1]["uid"]


def test_duplicate_puts_a_copy_right_after():
    draft = RulesDraft([rule("a", enabled=False, note="n"), rule("b")])
    assert draft.apply("rule_duplicate", ["1"])
    assert names(draft) == ["a", "a copy", "b"]
    twin = stored(draft)[1]
    assert twin["enabled"] is False and twin["note"] == "n"
    draft.apply("cond_value", [draft.rules[1]["uid"], "0", "0", "changed"])
    assert stored(draft)[0]["steps"][0]["conditions"][0]["value"] == "x"


def test_delete_removes_the_rule_and_closes_its_editor():
    draft = opened([rule("a"), rule("b")])
    assert draft.apply("rule_delete", ["1"])
    assert names(draft) == ["b"]
    assert draft.open_uid is None


def test_a_move_stays_inside_the_rules_level():
    draft = RulesDraft([rule("a1"), rule("a2"), rule("o1", "order"), rule("o2", "order")])
    assert draft.apply("rule_move", ["2", "down"]) is False
    assert draft.apply("rule_move", ["3", "up"]) is False
    assert draft.apply("rule_move", ["2", "up"])
    assert draft.apply("rule_move", ["3", "down"])
    assert names(draft) == ["a2", "a1", "o2", "o1"]


def test_move_to_takes_a_place_among_the_rules_of_its_level():
    draft = RulesDraft(
        [rule("a1"), rule("a2"), rule("a3"), rule("o1", "order"), rule("o2", "order")]
    )
    assert draft.apply("rule_move_to", ["1", "2"])
    assert names(draft) == ["a2", "a3", "a1", "o1", "o2"]
    assert draft.apply("rule_move_to", ["5", "0"])
    assert names(draft) == ["a2", "a3", "a1", "o2", "o1"]
    assert draft.apply("rule_move_to", ["5", "2"]) is False


def test_changing_the_level_moves_the_rule_to_the_end_of_that_level():
    draft = RulesDraft([rule("a1"), rule("a2"), rule("o1", "order")])
    assert draft.apply("rule_level", ["1", "order"])
    assert names(draft) == ["a2", "o1", "a1"]
    assert stored(draft)[2]["level"] == "order"
    # o1 (uid 3) becomes the last article rule; a1 is the one order rule left.
    assert draft.apply("rule_level", ["3", "article"])
    assert names(draft) == ["a2", "o1", "a1"]
    assert [r["level"] for r in draft.rules] == ["article", "article", "order"]


def test_the_groups_are_labelled_only_when_both_levels_exist():
    one = RulesDraft([rule("a1"), rule("a2")]).view()["rules"]["groups"]
    assert [(g["level"], g["label"], g["note"]) for g in one] == [("article", "", "")]
    both = RulesDraft([rule("a1"), rule("o1", "order")]).view()["rules"]["groups"]
    assert [(g["level"], g["label"], g["note"]) for g in both] == [
        ("article", "Article rules", "Check one order line at a time."),
        ("order", "Order rules", "Check the whole order. Run after every article rule."),
    ]


def test_a_row_says_where_it_can_move():
    draft = RulesDraft([rule("a1"), rule("a2"), rule("o1", "order")])
    got = [(r["num"], r["can_up"], r["can_down"], r["can_drag"]) for r in rows(draft)]
    assert got == [
        ("01", False, True, True),
        ("02", True, False, True),
        ("03", False, False, False),
    ]
    draft.apply("filter", ["a"])
    assert all(
        (r["can_up"], r["can_down"], r["can_drag"], r["move_title"])
        == (False, False, False, CLEAR_FILTER)
        for r in rows(draft)
    )


def test_a_row_shows_whether_the_rule_is_on():
    draft = RulesDraft([rule("on"), rule("off", enabled=False)])
    assert [(r["on"], r["badge"], r["switch_title"]) for r in rows(draft)] == [
        (True, "", "Turn off"),
        (False, "Off", "Turn on"),
    ]


def test_a_row_is_called_by_its_name_or_says_it_has_none():
    draft = RulesDraft([rule("VIP"), rule("")])
    assert [(r["name"], r["label"]) for r in rows(draft)] == [("VIP", "VIP"), ("", "Unnamed rule")]
    assert stored(draft)[1]["name"] == ""


@pytest.mark.parametrize(
    "rules, count",
    [
        ([rule()], "1 rule · 1 on"),
        ([rule(), rule(enabled=False), rule()], "3 rules · 2 on"),
    ],
)
def test_the_count(rules, count):
    assert RulesDraft(rules).view()["rules"]["count"] == count


def test_the_head_and_the_empty_state():
    view = RulesDraft([]).view()
    assert view["page"] == "rules"
    assert view["title"] == "Rules"
    assert view["subtitle"] == (
        "Change orders at the end of each analysis. Rules run top to bottom."
    )
    assert view["action"] == ""
    assert view["rules"]["empty"] == {
        "title": "No rules yet",
        "text": "Rules change orders at the end of each analysis, e.g. tag VIP orders.",
        "action": "Add rule",
    }
    assert view["rules"]["groups"] == []
    assert view["rules"]["no_hits"] == ""

    with_one = RulesDraft([rule()]).view()
    assert with_one["action"] == "Add rule"
    assert with_one["rules"]["empty"] is None
    assert with_one["rules"]["filter_placeholder"] == "Filter by name"


# --- the summary -------------------------------------------------------------------


def parts(*pairs):
    return [{"t": kind, "v": text} for kind, text in pairs]


def test_a_summary_reads_as_a_sentence():
    given = rule(
        conditions=[cond("Tags", "contains", "VIP"), cond("Notes", "is empty", "")],
        actions=[tag("priority"), {"type": "SET_STATUS", "value": "Not Fulfillable"}],
    )
    row = rows(RulesDraft([given]))[0]
    assert row["wide_labels"] is False
    assert row["summary"] == [
        {
            "label": "When",
            "parts": parts(
                ("bold", "Tags"),
                ("text", "contains"),
                ("chip", "VIP"),
                ("join", "and"),
                ("bold", "Notes"),
                ("text", "is empty"),
            ),
        },
        {
            "label": "Then",
            "parts": parts(
                ("text", "Add internal tag"),
                ("chip", "priority"),
                ("join", "and"),
                ("text", "Hold the order"),
            ),
        },
    ]


def test_any_joins_its_conditions_with_or():
    given = rule(conditions=[cond("SKU", "equals", "A"), cond("SKU", "equals", "B")], match="ANY")
    when = rows(RulesDraft([given]))[0]["summary"][0]["parts"]
    assert {"t": "join", "v": "or"} in when


def test_a_rule_with_steps_reads_step_by_step():
    given = rule()
    given["steps"].append({"conditions": [cond("Quantity", "is greater than", "2")], "match": "ALL", "actions": []})
    row = rows(RulesDraft([given]))[0]
    assert row["wide_labels"] is True
    assert [line["label"] for line in row["summary"]] == ["When", "Then", "And when", "Then"]
    assert row["summary"][3]["parts"] == parts(("muted", "No action yet."))


def test_an_empty_rule_says_it_never_matches():
    row = rows(RulesDraft([rule(conditions=[], actions=[])]))[0]
    assert row["summary"][0]["parts"] == parts(
        ("muted", "No condition yet, so this rule never matches.")
    )


@pytest.mark.parametrize(
    "action, expected",
    [
        ({"type": "REMOVE_INTERNAL_TAG", "value": "hold"}, [("text", "Remove internal tag"), ("chip", "hold")]),
        (
            {"type": "COPY_FIELD", "source": "SKU", "target": "Code"},
            [("text", "Copy"), ("chip", "SKU"), ("text", "to"), ("chip", "Code")],
        ),
        (
            {"type": "CALCULATE", "operation": "multiply", "field1": "Quantity", "field2": "Stock", "target": "Total"},
            [("text", "Calculate"), ("chip", "Quantity × Stock"), ("text", "into"), ("chip", "Total")],
        ),
        (
            {"type": "ALERT_NOTIFICATION", "message": "Check this", "severity": "warning"},
            [("text", "Log an alert"), ("chip", "Check this")],
        ),
        ({"type": "ADD_PRODUCT", "sku": "GIFT", "quantity": 2}, [("text", "Add bonus line"), ("chip", "GIFT ×2")]),
        ({"type": "ADD_TAG", "value": "VIP"}, [("text", "Add status note"), ("chip", "VIP")]),
        ({"type": "SET_MULTI_TAGS", "value": "A, B"}, [("text", "Add status notes"), ("chip", "A, B")]),
        ({"type": "SET_PRIORITY", "value": "High"}, [("text", "SET_PRIORITY")]),
        ({"type": "ADD_INTERNAL_TAG", "value": ""}, [("text", "Add internal tag")]),
    ],
)
def test_each_action_has_its_words(action, expected):
    then = rows(RulesDraft([rule(actions=[action])]))[0]["summary"][1]["parts"]
    assert then == parts(*expected)


# --- fields --------------------------------------------------------------------------


def test_an_article_rule_is_not_offered_the_order_fields(analysis_df):
    groups = rule_fields("article", analysis_df)
    assert [label for label, _fields in groups] == ["Common fields", "Other fields in this analysis"]
    offered = {f for _label, fields in groups for f in fields}
    assert not offered & set(RuleEngine.ORDER_LEVEL_FIELDS)
    assert {"SKU", "Quantity", "Notes"} <= offered
    assert "_internal" not in offered
    assert groups[1][1] == ["Notes"]


def test_an_order_rule_is_offered_every_order_field_first(analysis_df):
    groups = rule_fields("order", analysis_df)
    assert groups[0] == ("Order fields", list(RuleEngine.ORDER_LEVEL_FIELDS))


@pytest.mark.parametrize("frame", [None, pd.DataFrame()])
def test_with_no_analysis_only_the_common_fields_are_listed(frame):
    assert [label for label, _fields in rule_fields("article", frame)] == ["Common fields"]


@pytest.mark.parametrize(
    "operator, kind",
    [("is empty", "none"), ("is not empty", "none"), ("date before", "date"),
     ("date equals", "date"), ("equals", "text"), ("matches regex", "text")],
)
def test_value_kind(operator, kind):
    assert value_kind(operator) == kind


# --- the editor: edits -----------------------------------------------------------------


def test_steps_are_added_and_removed_but_never_the_first():
    draft = opened([rule()])
    assert draft.apply("step_add", ["1"])
    assert stored(draft)[0]["steps"][1] == {"conditions": [], "match": "ALL", "actions": []}
    steps = editor(draft)["steps"]
    assert [(s["title"], s["note"], s["removable"]) for s in steps] == [
        ("Step 1", "", False),
        ("Step 2", "Checks only the lines step 1 matched.", True),
    ]
    assert draft.apply("step_remove", ["1", "1"])
    assert len(stored(draft)[0]["steps"]) == 1
    assert editor(draft)["steps"][0]["title"] == ""


def test_an_order_rules_later_step_says_it_is_a_gate():
    draft = opened([rule(level="order")])
    draft.apply("step_add", ["1"])
    assert editor(draft)["steps"][1]["note"] == "Runs only if step 1 matched."


def test_match_is_drawn_from_two_conditions_up():
    draft = opened([rule()])
    assert editor(draft)["steps"][0]["match"]["show"] is False
    assert draft.apply("cond_add", ["1", "0"])
    match = editor(draft)["steps"][0]["match"]
    assert match["show"] is True
    assert match["tail"] == "of these match"
    assert [(o["value"], o["label"], o["checked"]) for o in match["options"]] == [
        ("ALL", "All", True),
        ("ANY", "Any", False),
    ]
    assert draft.apply("step_match", ["1", "0", "ANY"])
    assert stored(draft)[0]["steps"][0]["match"] == "ANY"


@pytest.mark.parametrize("level, first", [("article", "Order_Number"), ("order", "item_count")])
def test_a_new_condition_starts_on_the_levels_first_field(level, first):
    draft = opened([rule(level=level, conditions=[])])
    assert draft.apply("cond_add", ["1", "0"])
    assert stored(draft)[0]["steps"][0]["conditions"] == [cond(first, "equals", "")]


def test_a_condition_is_edited_and_removed(analysis_df):
    draft = opened([rule()], analysis_df)
    assert draft.apply("cond_field", ["1", "0", "0", "Quantity"])
    assert draft.apply("cond_operator", ["1", "0", "0", "is greater than"])
    assert draft.apply("cond_value", ["1", "0", "0", "5"])
    assert stored(draft)[0]["steps"][0]["conditions"] == [cond("Quantity", "is greater than", "5")]
    assert draft.apply("cond_remove", ["1", "0", "0"])
    assert stored(draft)[0]["steps"][0]["conditions"] == []


def test_an_operator_keeps_the_value_unless_it_takes_another_kind():
    draft = opened([rule(conditions=[cond("SKU", "equals", "ABC")])])
    draft.apply("cond_operator", ["1", "0", "0", "contains"])
    assert stored(draft)[0]["steps"][0]["conditions"][0]["value"] == "ABC"
    draft.apply("cond_operator", ["1", "0", "0", "date before"])
    assert stored(draft)[0]["steps"][0]["conditions"][0]["value"] == ""
    draft.apply("cond_value", ["1", "0", "0", "2026-01-30"])
    draft.apply("cond_operator", ["1", "0", "0", "date after"])
    assert stored(draft)[0]["steps"][0]["conditions"][0]["value"] == "2026-01-30"
    draft.apply("cond_operator", ["1", "0", "0", "is empty"])
    assert stored(draft)[0]["steps"][0]["conditions"][0] == cond("SKU", "is empty", "")


def test_a_stored_number_is_kept_until_it_is_edited():
    draft = opened([rule(conditions=[cond("Quantity", "is greater than", 5)])])
    assert stored(draft)[0]["steps"][0]["conditions"][0]["value"] == 5
    assert editor(draft)["steps"][0]["conditions"][0]["value"]["text"] == "5"
    assert draft.apply("cond_value", ["1", "0", "0", "6"])
    assert stored(draft)[0]["steps"][0]["conditions"][0]["value"] == "6"


def test_a_new_action_adds_an_internal_tag_and_starts_blank():
    draft = opened([rule(actions=[])], tag_categories=TAG_CATEGORIES)
    assert draft.apply("action_add", ["1", "0"])
    assert stored(draft)[0]["steps"][0]["actions"] == [{"type": "ADD_INTERNAL_TAG", "value": ""}]


@pytest.mark.parametrize(
    "kind, default",
    [
        ("REMOVE_INTERNAL_TAG", {"value": ""}),
        ("SET_STATUS", {"value": "Not Fulfillable"}),
        ("COPY_FIELD", {"source": "Order_Number", "target": ""}),
        ("CALCULATE", {"operation": "add", "field1": "Order_Number", "field2": "Order_Number", "target": ""}),
        ("ALERT_NOTIFICATION", {"message": "", "severity": "info"}),
        ("ADD_PRODUCT", {"sku": "", "quantity": 1}),
    ],
)
def test_changing_an_actions_type_starts_it_from_that_types_default(kind, default):
    draft = opened([rule(actions=[{"type": "ADD_TAG", "value": "old"}])])
    assert draft.apply("action_type", ["1", "0", "0", kind])
    assert stored(draft)[0]["steps"][0]["actions"] == [{"type": kind, **default}]


def test_every_offered_type_has_a_label_a_default_and_parameters():
    draft = opened([rule()])
    offered = editor(draft)["action_types"]
    assert [t["value"] for t in offered] == ACTION_TYPES
    assert not {t["value"] for t in offered} & set(LEGACY_ACTION_TYPES)
    for kind in ACTION_TYPES[1:] + ACTION_TYPES[:1]:
        assert draft.apply("action_type", ["1", "0", "0", kind])
        assert editor(draft)["steps"][0]["actions"][0]["extra_type"] is None


def test_an_actions_parameters_are_edited(analysis_df):
    draft = opened([rule(actions=[{"type": "CALCULATE", "operation": "add", "field1": "SKU", "field2": "SKU", "target": ""}])], analysis_df)
    assert draft.apply("action_param", ["1", "0", "0", "operation", "divide"])
    assert draft.apply("action_param", ["1", "0", "0", "field1", "Quantity"])
    assert draft.apply("action_param", ["1", "0", "0", "target", "Half"])
    assert draft.apply("action_param", ["1", "0", "0", "operation", "modulo"]) is False
    assert draft.apply("action_param", ["1", "0", "0", "field2", "Nope"]) is False
    assert stored(draft)[0]["steps"][0]["actions"] == [
        {"type": "CALCULATE", "operation": "divide", "field1": "Quantity", "field2": "SKU", "target": "Half"}
    ]


def test_a_quantity_is_stored_as_a_number_when_it_is_one():
    draft = opened([rule(actions=[{"type": "ADD_PRODUCT", "sku": "GIFT", "quantity": 1}])])
    assert draft.apply("action_param", ["1", "0", "0", "quantity", " 3 "])
    assert stored(draft)[0]["steps"][0]["actions"][0]["quantity"] == 3
    assert draft.apply("action_param", ["1", "0", "0", "quantity", "3"]) is False
    assert draft.apply("action_param", ["1", "0", "0", "quantity", "lots"])
    assert stored(draft)[0]["steps"][0]["actions"][0]["quantity"] == "lots"


def test_an_action_is_removed():
    draft = opened([rule(actions=[tag("a"), tag("b")])])
    assert draft.apply("action_remove", ["1", "0", "0"])
    assert stored(draft)[0]["steps"][0]["actions"] == [tag("b")]


# --- the editor: the view ----------------------------------------------------------------


def test_the_editor_names_the_level_and_lists_its_fields(analysis_df):
    draft = opened([rule()], analysis_df)
    got = editor(draft)
    assert got["level"] == {
        "options": [
            {"value": "article", "label": "Article", "checked": True},
            {"value": "order", "label": "Order", "checked": False},
        ],
        "hint": "Checks one order line at a time.",
    }
    assert [g["label"] for g in got["field_groups"]] == ["Common fields", "Other fields in this analysis"]
    assert got["operators"] == CONDITION_OPERATORS

    draft.apply("rule_level", ["1", "order"])
    got = editor(draft)
    assert got["level"]["hint"] == "Checks the whole order. Runs after every article rule."
    assert got["field_groups"][0]["label"] == "Order fields"


@pytest.mark.parametrize(
    "operator, placeholder",
    [
        ("contains", "Value"),
        ("in list", "Value1, Value2, Value3"),
        ("not between", "10-100"),
        ("matches regex", "^SKU-\\d{4}$"),
    ],
)
def test_a_text_value_has_its_operators_placeholder(operator, placeholder):
    draft = opened([rule(conditions=[cond("SKU", operator, "1-2")])])
    value = editor(draft)["steps"][0]["conditions"][0]["value"]
    assert (value["kind"], value["placeholder"]) == ("text", placeholder)


def test_an_empty_check_has_no_value_control():
    draft = opened([rule(conditions=[cond("SKU", "is empty", "")])])
    assert editor(draft)["steps"][0]["conditions"][0]["value"]["kind"] == "none"


@pytest.mark.parametrize(
    "stored_date, shown",
    [("2026-01-30", "2026-01-30"), ("30/01/2026", "2026-01-30"), ("30.01.2026", "2026-01-30"), ("soon", ""), ("", "")],
)
def test_a_date_is_shown_as_the_engine_reads_it(stored_date, shown):
    draft = opened([rule(conditions=[cond("Created_At", "date before", stored_date)])])
    got = editor(draft)["steps"][0]["conditions"][0]
    assert got["value"] == {"kind": "date", "text": shown, "placeholder": "Value", "suggestions": []}
    assert got["problem"] == ("" if shown else NO_DATE)
    assert got["invalid"] is False
    # Shown, not rewritten: the stored text is what Save writes.
    assert stored(draft)[0]["steps"][0]["conditions"][0]["value"] == stored_date


def test_equals_on_a_column_suggests_its_values(analysis_df):
    draft = opened([rule(conditions=[cond("SKU", "equals", "gone")])], analysis_df)
    value = editor(draft)["steps"][0]["conditions"][0]["value"]
    assert value["suggestions"] == ["x", "y"]
    assert value["text"] == "gone"

    draft.apply("cond_operator", ["1", "0", "0", "contains"])
    assert editor(draft)["steps"][0]["conditions"][0]["value"]["suggestions"] == []


def test_suggestions_stop_at_the_limit():
    frame = pd.DataFrame({"Order_Number": [f"#{n:05d}" for n in range(SUGGESTION_LIMIT + 50)]})
    draft = opened([rule(conditions=[cond("Order_Number", "equals", "")])], frame)
    got = editor(draft)["steps"][0]["conditions"][0]["value"]["suggestions"]
    assert len(got) == SUGGESTION_LIMIT
    assert got[0] == "#00000"


@pytest.mark.parametrize(
    "condition, problem",
    [
        (cond("SKU", "matches regex", "("), "Invalid regex syntax"),
        (cond("Quantity", "between", "100-10"),
         "Start is greater than end. Write the smaller number first, for example 10-100."),
        (cond("SKU", "in list", " , "), "No valid items in list"),
        (cond("Quantity", "is greater than", "many"), "Value must be a number"),
    ],
)
def test_a_value_save_refuses_is_marked_and_blocks(condition, problem, analysis_df):
    draft = opened([rule("sizes", conditions=[cond(), condition])], analysis_df)
    got = editor(draft)["steps"][0]["conditions"][1]
    assert (got["problem"], got["invalid"]) == (problem, True)
    assert draft.blocker() == "Fix rule “sizes”"
    assert draft.blocker_key() == "rule-1-s0-c1-value"
    assert draft.validate() == (False, [f"Rule “sizes”, step 1, condition 2: {problem}"])
    assert rows(draft)[0]["problem"] == f"Condition 2: {problem}"


def test_a_clean_page_blocks_nothing(analysis_df):
    draft = RulesDraft([rule()], analysis_df)
    assert draft.blocker() is None
    assert draft.blocker_key() == ""
    assert draft.validate() == (True, [])
    assert rows(draft)[0]["problem"] == ""


def test_the_blocker_names_the_first_rule_in_the_list():
    bad = cond("SKU", "matches regex", "(")
    draft = RulesDraft([rule("fine"), rule("", conditions=[bad]), rule("later", conditions=[bad])])
    assert draft.blocker() == "Fix rule 02"
    assert draft.blocker_key() == "rule-2-s0-c0-value"


def test_a_rule_with_steps_says_which_step():
    given = rule("deep")
    given["steps"].append({"conditions": [cond("SKU", "matches regex", "(")], "match": "ALL", "actions": []})
    assert rows(RulesDraft([given]))[0]["problem"] == "Step 2, condition 1: Invalid regex syntax"


def test_a_list_says_how_many_items():
    draft = opened([rule(conditions=[cond("SKU", "in list", "A, B ,C"), cond("SKU", "not in list", "A")])])
    got = editor(draft)["steps"][0]["conditions"]
    assert [(c["problem"], c["hint"]) for c in got] == [("", "3 items"), ("", "1 item")]


def test_an_order_field_on_an_article_rule_never_matches(analysis_df):
    draft = opened([rule(conditions=[cond("item_count", "equals", "2")])], analysis_df)
    got = editor(draft)["steps"][0]["conditions"][0]
    assert got["problem"] == (
        "“item_count” is not a field an article rule can read, so this condition never matches."
    )
    assert got["field_invalid"] is True
    assert got["extra_field"] == {"value": "item_count", "note": NOT_AVAILABLE}
    assert got["invalid"] is False
    assert draft.blocker() is None
    # Kept, not replaced.
    assert stored(draft)[0]["steps"][0]["conditions"][0]["field"] == "item_count"


def test_the_same_holds_with_no_analysis():
    draft = opened([rule(conditions=[cond("item_count", "equals", "2")])])
    assert editor(draft)["steps"][0]["conditions"][0]["field_invalid"] is True


def test_an_unlisted_column_is_not_flagged_with_no_analysis():
    """Settings opens before any analysis runs, and the offered list is then
    only a guess: a client's own column must not be called a never-match."""
    draft = opened([rule(conditions=[cond("Total_Price", "equals", "1")])])
    got = editor(draft)["steps"][0]["conditions"][0]
    assert (got["problem"], got["field_invalid"]) == ("", False)
    assert got["extra_field"] == {"value": "Total_Price", "note": ""}


def test_an_unlisted_column_is_flagged_once_an_analysis_says_it_is_not_there(analysis_df):
    draft = opened([rule(conditions=[cond("Total_Price", "equals", "1")])], analysis_df)
    assert editor(draft)["steps"][0]["conditions"][0]["field_invalid"] is True


def test_switching_level_keeps_a_field_the_new_level_does_not_offer(analysis_df):
    draft = opened([rule(level="order", conditions=[cond("item_count", "equals", "2")])], analysis_df)
    assert editor(draft)["steps"][0]["conditions"][0]["extra_field"] is None
    draft.apply("rule_level", ["1", "article"])
    got = editor(draft)["steps"][0]["conditions"][0]
    assert got["field"] == "item_count" and got["field_invalid"] is True


def test_a_condition_with_no_field_says_so():
    draft = opened([rule(conditions=[{"operator": "equals", "value": "x"}])])
    got = editor(draft)["steps"][0]["conditions"][0]
    assert (got["field"], got["problem"], got["extra_field"]) == ("", NO_FIELD, None)


def test_an_unknown_operator_is_listed_and_flagged(analysis_df):
    draft = opened([rule(conditions=[cond("SKU", "sounds like", "x")])], analysis_df)
    got = editor(draft)["steps"][0]["conditions"][0]
    assert got["extra_operator"] == "sounds like"
    assert got["problem"] == (
        "“sounds like” is not an operator this version knows, so this condition never matches."
    )


def test_a_tag_action_suggests_the_configured_tags():
    draft = opened([rule(actions=[tag("BRAND_NEW")])], tag_categories=TAG_CATEGORIES)
    assert draft.configured_tags() == ["EXPRESS", "FRAGILE", "GIFT"]
    action = editor(draft)["steps"][0]["actions"][0]
    assert action["label"] == "Add internal tag"
    assert action["params"] == [
        {
            "name": "value",
            "kind": "suggest",
            "value": "BRAND_NEW",
            "placeholder": "Tag",
            "lead": "",
            "options": ["EXPRESS", "FRAGILE", "GIFT"],
            "extra": None,
            "invalid": False,
        }
    ]


def test_no_tag_categories_means_no_suggestions():
    assert RulesDraft([]).configured_tags() == []


def test_the_hold_has_no_parameter_and_says_what_it_does():
    draft = opened([rule(actions=[{"type": "SET_STATUS", "value": "Not Fulfillable"}])])
    action = editor(draft)["steps"][0]["actions"][0]
    assert (action["label"], action["params"], action["hint"]) == ("Hold the order", [], HOLD_HINT)


def test_calculate_draws_its_four_parameters_in_reading_order(analysis_df):
    draft = opened(
        [rule(actions=[{"type": "CALCULATE", "operation": "add", "field1": "Gone", "field2": "SKU", "target": "T"}])],
        analysis_df,
    )
    params = editor(draft)["steps"][0]["actions"][0]["params"]
    assert [(p["name"], p["kind"], p["lead"]) for p in params] == [
        ("field1", "field", ""),
        ("operation", "choice", ""),
        ("field2", "field", ""),
        ("target", "text", "→"),
    ]
    assert params[0]["extra"] == "Gone"
    assert params[2]["extra"] is None
    assert params[1]["options"] == [
        {"value": "add", "label": "plus"},
        {"value": "subtract", "label": "minus"},
        {"value": "multiply", "label": "times"},
        {"value": "divide", "label": "divided by"},
    ]
    assert "Notes" in params[0]["options"]


@pytest.mark.parametrize(
    "action, hint",
    [
        ({"type": "ADD_TAG", "value": "T"}, RETIRED_ONE),
        ({"type": "ADD_ORDER_TAG", "value": "T"}, RETIRED_ONE),
        ({"type": "SET_MULTI_TAGS", "value": "A, B"}, RETIRED_MANY),
    ],
)
def test_a_retired_action_is_listed_on_its_own_row_and_explains_itself(action, hint):
    draft = opened([rule(actions=[action, tag()])])
    retired, current = editor(draft)["steps"][0]["actions"]
    assert retired["extra_type"] == {"value": action["type"], "label": retired["label"]}
    assert "(retired)" in retired["label"]
    assert (retired["problem"], retired["hint"]) == ("", hint)
    assert (current["extra_type"], current["hint"]) == (None, "")


def test_an_unknown_action_says_it_does_nothing():
    draft = opened([rule(actions=[{"type": "SET_PRIORITY", "value": "High"}])])
    action = editor(draft)["steps"][0]["actions"][0]
    assert (action["label"], action["params"], action["problem"]) == ("SET_PRIORITY", [], UNKNOWN_ACTION)
    assert draft.blocker() is None


@pytest.mark.parametrize("quantity", ["", "0", "lots", "10000", "2.5"])
def test_a_bad_quantity_blocks(quantity):
    draft = opened([rule("bonus", actions=[{"type": "ADD_PRODUCT", "sku": "GIFT", "quantity": quantity}])])
    action = editor(draft)["steps"][0]["actions"][0]
    assert action["problem"] == QUANTITY_PROBLEM
    assert [p["invalid"] for p in action["params"]] == [False, True]
    assert draft.blocker_key() == "rule-1-s0-a0-quantity"
    assert draft.validate() == (False, [f"Rule “bonus”, step 1, action 1: {QUANTITY_PROBLEM}"])
    assert rows(draft)[0]["problem"] == f"Action 1: {QUANTITY_PROBLEM}"


@pytest.mark.parametrize("quantity", [1, 9999, "3"])
def test_a_whole_quantity_in_range_does_not(quantity):
    draft = RulesDraft([rule(actions=[{"type": "ADD_PRODUCT", "sku": "GIFT", "quantity": quantity}])])
    assert draft.blocker() is None


# --- Test... ----------------------------------------------------------------------------


def test_test_runs_what_save_would_store_whether_or_not_the_rule_is_on(analysis_df):
    given = rule("r", enabled=False, actions=[{"type": "ADD_PRODUCT", "sku": "GIFT", "quantity": 3}])
    draft = RulesDraft([given], analysis_df)
    assert draft.test_config("1") == {"name": "r", "level": "article", "steps": given["steps"]}
    assert rows(draft)[0]["can_test"] is True
    assert rows(draft)[0]["test_title"] == ""


@pytest.mark.parametrize(
    "given, frame, why",
    [
        (rule(), None, TEST_NO_ANALYSIS),
        (rule(), pd.DataFrame(), TEST_NO_ANALYSIS),
        (rule(conditions=[]), "analysis", TEST_NO_CONDITION),
        (rule(conditions=[cond("SKU", "matches regex", "(")]), "analysis", TEST_BLOCKED),
    ],
)
def test_test_says_why_it_cannot_run(given, frame, why, analysis_df):
    draft = RulesDraft([given], analysis_df if isinstance(frame, str) else frame)
    assert draft.test_config("1") is None
    assert (rows(draft)[0]["can_test"], rows(draft)[0]["test_title"]) == (False, why)


def test_test_config_of_a_rule_that_is_not_there(analysis_df):
    assert RulesDraft([rule()], analysis_df).test_config("9") is None
```

- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_settings_draft_rules.py`
Expected: collection stops with `ModuleNotFoundError: No module named 'gui.settings.rules_state'` (`1 error`).

- [ ] **Step 3: Write the draft**

**Create `gui/settings/rules_state.py`:**

```python
"""The rules behind the Rules page the web tier draws (phase 8 spec section 4).

RulesDraft is a draft like page_state.py's: a settings page with no widget.
It holds the rules, takes the page's edits through apply(), and meets
PageContract, so SettingsWindow saves and marks it like any other page.
view() is everything the page draws, sentences included: the page computes
nothing.

A rule is addressed by a uid the draft hands out when it loads or adds one.
The uid is never stored. Steps, conditions and actions are addressed by their
position inside the rule. The actions are the spec's section 3.3: add one
there before adding it here.
"""

import copy
import re
from typing import ClassVar

from gui.rule_validator import condition_error, validate_list
from gui.settings.contract import PageContract
from gui.settings.fields import ACTION_TYPES, CONDITION_OPERATORS
from gui.settings.page_state import _shaped
from shopify_tool.core import get_unique_column_values
from shopify_tool.rules import RuleEngine, _parse_date_safe
from shopify_tool.stock_ledger import NOT_FULFILLABLE
from shopify_tool.tag_manager import _normalize_tag_categories

LEVELS = ("article", "order")
COMMON_FIELDS = (
    "Order_Number",
    "Order_Type",
    "SKU",
    "Product_Name",
    "Quantity",
    "Stock",
    "Final_Stock",
    "Shipping_Provider",
    "Shipping_Method",
    "Destination_Country",
)
VALUELESS_OPERATORS = ("is empty", "is not empty")
DATE_OPERATORS = ("date before", "date after", "date equals")
LIST_OPERATORS = ("in list", "not in list")
EQUALITY_OPERATORS = ("equals", "does not equal")
# ponytail: a column's first 200 values, sorted. A column with more (order
# numbers) offers no complete list; the field takes any text. Filter on the
# typed text in Python if that stops being enough.
SUGGESTION_LIMIT = 200
MAX_QUANTITY = 9999

SUBTITLE = "Change orders at the end of each analysis. Rules run top to bottom."
ADD_RULE = "Add rule"
EMPTY_TITLE = "No rules yet"
EMPTY_TEXT = "Rules change orders at the end of each analysis, e.g. tag VIP orders."
NEW_RULE_NAME = "New rule"
UNNAMED = "Unnamed rule"
CLEAR_FILTER = "Clear the filter to reorder"
GROUPS = {
    "article": ("Article rules", "Check one order line at a time."),
    "order": ("Order rules", "Check the whole order. Run after every article rule."),
}
LEVEL_LABEL = {"article": "Article", "order": "Order"}
LEVEL_HINT = {
    "article": "Checks one order line at a time.",
    "order": "Checks the whole order. Runs after every article rule.",
}
NO_CONDITION = "No condition yet, so this rule never matches."
NO_ACTION = "No action yet."
TEST_NO_ANALYSIS = "Run an analysis first. Test needs its orders."
TEST_NO_CONDITION = "Add a condition first."
TEST_BLOCKED = "Fix the marked value first."
NOT_AVAILABLE = "Not available"
NO_FIELD = "Choose a field. Until then this condition never matches."
NO_DATE = "Pick a date. Until then this condition never matches."
QUANTITY_PROBLEM = f"Type a whole number from 1 to {MAX_QUANTITY}."
HOLD_HINT = "Holds every line of the order and returns its stock."
RETIRED_ONE = "Writes the Status_Note text, not a tag. Use Add internal tag for a real tag."
RETIRED_MANY = "Writes the Status_Note text, not tags. Use one Add internal tag per tag."
UNKNOWN_ACTION = "This version does not know this action, so it does nothing."

ACTION_LABELS = {
    "ADD_INTERNAL_TAG": "Add internal tag",
    "REMOVE_INTERNAL_TAG": "Remove internal tag",
    "SET_STATUS": "Hold the order",
    "COPY_FIELD": "Copy field",
    "CALCULATE": "Calculate",
    "ALERT_NOTIFICATION": "Log an alert",
    "ADD_PRODUCT": "Add bonus line",
    "ADD_TAG": "Add status note (retired)",
    "ADD_ORDER_TAG": "Add status note (retired)",
    "SET_MULTI_TAGS": "Add status notes (retired)",
}
# (stored value, the menu's label, the summary's sign)
OPERATIONS = (
    ("add", "plus", "+"),
    ("subtract", "minus", "−"),
    ("multiply", "times", "×"),
    ("divide", "divided by", "÷"),
)
SEVERITIES = (("info", "Info"), ("warning", "Warning"), ("error", "Error"))
_CHOICES = {
    "operation": [(value, label) for value, label, _sign in OPERATIONS],
    "severity": list(SEVERITIES),
}
_SIGN = {value: sign for value, _label, sign in OPERATIONS}

# type -> its parameters, in the order the row draws them:
# (name, kind, placeholder, the word or sign drawn before it).
_TAG = (("value", "suggest", "Tag", ""),)
_NOTE = (("value", "text", "Value", ""),)
ACTION_PARAMS = {
    "ADD_INTERNAL_TAG": _TAG,
    "REMOVE_INTERNAL_TAG": _TAG,
    "SET_STATUS": (),
    "COPY_FIELD": (
        ("source", "field", "", ""),
        ("target", "text", "Target column", "→"),
    ),
    "CALCULATE": (
        ("field1", "field", "", ""),
        ("operation", "choice", "", ""),
        ("field2", "field", "", ""),
        ("target", "text", "Result column", "→"),
    ),
    "ALERT_NOTIFICATION": (
        ("message", "text", "Alert message", ""),
        ("severity", "choice", "", ""),
    ),
    "ADD_PRODUCT": (
        ("sku", "text", "Product SKU", ""),
        ("quantity", "number", "", "×"),
    ),
    "ADD_TAG": _NOTE,
    "ADD_ORDER_TAG": _NOTE,
    "SET_MULTI_TAGS": (("value", "text", "TAG1, TAG2, TAG3", ""),),
}

_PLACEHOLDER = {
    "in list": "Value1, Value2, Value3",
    "not in list": "Value1, Value2, Value3",
    "between": "10-100",
    "not between": "10-100",
    "matches regex": "^SKU-\\d{4}$",
    "does not match regex": "^SKU-\\d{4}$",
}
_RULE_KEYS = frozenset(
    {"name", "level", "enabled", "steps", "priority", "conditions", "match", "actions"}
)
_KEY_UID = re.compile(r"rule-(\d+)-")


def rule_fields(level: str, analysis_df) -> list[tuple[str, list[str]]]:
    """The fields a condition on a rule of this level can read, in groups.

    Order fields come from RuleEngine.ORDER_LEVEL_FIELDS, so the page cannot
    drift from what the engine dispatches on, and only an order rule gets
    them: on an article rule they are never columns.
    """
    groups = []
    if level == "order":
        groups.append(("Order fields", list(RuleEngine.ORDER_LEVEL_FIELDS)))
    groups.append(("Common fields", list(COMMON_FIELDS)))
    if analysis_df is not None and not analysis_df.empty:
        other = sorted(
            column
            for column in map(str, analysis_df.columns)
            if not column.startswith("_") and column not in COMMON_FIELDS
        )
        if other:
            groups.append(("Other fields in this analysis", other))
    return groups


def value_kind(operator: str) -> str:
    """The control a condition's value takes: "none", "date" or "text"."""
    if operator in VALUELESS_OPERATORS:
        return "none"
    if operator in DATE_OPERATORS:
        return "date"
    return "text"


def _text(value) -> str:
    return "" if value is None else str(value)


def _kind(action: dict) -> str:
    """The action's type as the engine dispatches on it."""
    return _text(action.get("type")).upper()


def _valid_quantity(value) -> bool:
    try:
        number = int(_text(value).strip())
    except ValueError:
        return False
    return 1 <= number <= MAX_QUANTITY


def _at(items: list, position: str):
    """items[position], where the position arrives as text; None when it is
    not a position in the list."""
    if not position.isdigit() or int(position) >= len(items):
        return None
    return items[int(position)]


def _empty_step() -> dict:
    return {"conditions": [], "match": "ALL", "actions": []}


def _loaded_condition(stored: dict) -> dict:
    condition = dict(stored)
    condition["field"] = _text(stored.get("field"))
    condition["operator"] = _text(stored.get("operator", CONDITION_OPERATORS[0]))
    condition["value"] = stored.get("value", "")
    return condition


def _loaded_action(stored: dict) -> dict:
    action = dict(stored)
    action["type"] = _text(stored.get("type", ACTION_TYPES[0]))
    kind = _kind(action)
    if kind == "SET_STATUS":
        # A rule can only hold an order (spec 2026-09-26 D3): a stale value
        # loads as the hold.
        action["value"] = NOT_FULFILLABLE
    elif kind == "SET_MULTI_TAGS":
        tags = action.pop("tags", None) or action.get("value", "")
        action["value"] = (
            ", ".join(map(str, tags)) if isinstance(tags, list) else _text(tags)
        )
    elif kind == "ADD_PRODUCT":
        action.setdefault("quantity", 1)
    return action


def _loaded_step(stored: dict) -> dict:
    return {
        "conditions": [
            _loaded_condition(c) for c in stored.get("conditions") or [] if isinstance(c, dict)
        ],
        # As the engine reads it: upper-cased, and anything but ANY is ALL.
        "match": "ANY" if _text(stored.get("match", "ALL")).upper() == "ANY" else "ALL",
        "actions": [
            _loaded_action(a) for a in stored.get("actions") or [] if isinstance(a, dict)
        ],
    }


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def _part(kind: str, text) -> dict:
    return {"t": kind, "v": _text(text)}


def _action_parts(action: dict) -> list[dict]:
    """One action as the words and chips of a summary line."""
    kind = _kind(action)

    def chips(*values) -> list[dict]:
        return [_part("chip", v) for v in values if _text(v) != ""]

    if kind in ("ADD_INTERNAL_TAG", "REMOVE_INTERNAL_TAG"):
        return [_part("text", ACTION_LABELS[kind]), *chips(action.get("value"))]
    if kind == "SET_STATUS":
        return [_part("text", ACTION_LABELS[kind])]
    if kind == "COPY_FIELD":
        return [
            _part("text", "Copy"),
            *chips(action.get("source")),
            _part("text", "to"),
            *chips(action.get("target")),
        ]
    if kind == "CALCULATE":
        sign = _SIGN.get(_text(action.get("operation")), "?")
        sum_text = f"{_text(action.get('field1'))} {sign} {_text(action.get('field2'))}"
        return [
            _part("text", "Calculate"),
            _part("chip", sum_text),
            _part("text", "into"),
            *chips(action.get("target")),
        ]
    if kind == "ALERT_NOTIFICATION":
        return [_part("text", ACTION_LABELS[kind]), *chips(action.get("message"))]
    if kind == "ADD_PRODUCT":
        line = f"{_text(action.get('sku'))} ×{_text(action.get('quantity', 1))}"
        return [_part("text", ACTION_LABELS[kind]), _part("chip", line)]
    if kind in ("ADD_TAG", "ADD_ORDER_TAG"):
        return [_part("text", "Add status note"), *chips(action.get("value"))]
    if kind == "SET_MULTI_TAGS":
        return [_part("text", "Add status notes"), *chips(action.get("value"))]
    return [_part("text", _text(action.get("type")))]


class RulesDraft(PageContract):
    """The rule engine's rules, stored under config_data["rules"]."""

    def __init__(self, rules: list, analysis_df=None, tag_categories: dict | None = None):
        self.analysis_df = analysis_df
        # ponytail: a snapshot taken when the dialog opens. The Tag categories
        # page can add a tag while this page is open and the suggestions will
        # not see it; the field takes any text, so the tag is still typeable.
        self._tag_categories = tag_categories or {}
        self._next_uid = 0
        self._dates: dict[str, str] = {}
        self.rules = [
            self._loaded(rule)
            for rule in RuleEngine.execution_order(
                [copy.deepcopy(r) for r in rules or [] if isinstance(r, dict)]
            )
        ]
        self.filter = ""
        self.open_uid: str | None = None

    # --- the model ---------------------------------------------------------

    def _uid(self) -> str:
        self._next_uid += 1
        return str(self._next_uid)

    def _loaded(self, stored: dict) -> dict:
        steps = stored.get("steps")
        if not (isinstance(steps, list) and steps):
            # The old format: one step's worth of keys at the rule's root.
            steps = [stored]
        return {
            "uid": self._uid(),
            "name": _text(stored.get("name")),
            "level": "order" if stored.get("level") == "order" else "article",
            "enabled": stored.get("enabled", True) is not False,
            "steps": [_loaded_step(s) for s in steps if isinstance(s, dict)]
            or [_empty_step()],
            "extra": {k: v for k, v in stored.items() if k not in _RULE_KEYS},
        }

    def _stored(self, rule: dict, priority: int | None = None) -> dict:
        """One rule as the profile holds it. Save and Test both build through
        here, so a test runs exactly what Save would store."""
        stored = {"name": rule["name"]}
        if priority is not None:
            stored["priority"] = priority
        stored["level"] = rule["level"]
        if not rule["enabled"]:
            # Only when off: a rule that is on is written as it always was.
            stored["enabled"] = False
        stored["steps"] = copy.deepcopy(rule["steps"])
        stored.update(copy.deepcopy(rule["extra"]))
        return stored

    def _rule(self, uid: str) -> dict | None:
        return next((rule for rule in self.rules if rule["uid"] == uid), None)

    def _step(self, uid: str, s: str) -> tuple[dict | None, dict | None]:
        rule = self._rule(uid)
        return rule, (None if rule is None else _at(rule["steps"], s))

    def _level_rules(self, level: str) -> list[dict]:
        return [rule for rule in self.rules if rule["level"] == level]

    def _place(self, rule: dict, position: int) -> None:
        """Put a rule that is not in the list at `position` among the rules
        of its level. Article rules come first, as they run first."""
        before = 0 if rule["level"] == "article" else len(self._level_rules("article"))
        self.rules.insert(before + position, rule)

    def _fields(self, level: str) -> list[str]:
        return [f for _label, fields in rule_fields(level, self.analysis_df) for f in fields]

    def configured_tags(self) -> list[str]:
        """Every tag the tag categories name, sorted. The analyser's own
        system tags are left out on purpose: offering them invites rules that
        fight it. The field takes any text, so they stay typeable."""
        tags = set()
        for category in _normalize_tag_categories(self._tag_categories).values():
            tags.update(category.get("tags", []))
        return sorted(tags)

    def _has_analysis(self) -> bool:
        return self.analysis_df is not None and not self.analysis_df.empty

    def _resolvable(self, field: str, level: str) -> bool:
        """Whether the engine can evaluate a condition on this field. It fails
        one it cannot closed, so the rule quietly stops firing."""
        if not field:
            return False
        if field in self._fields(level):
            return True
        if not self._has_analysis():
            # The offered list is then only a guess at the columns, and a
            # client's own column would be flagged falsely. An order field on
            # an article rule never resolves, whatever the data.
            return field not in RuleEngine.ORDER_LEVEL_FIELDS
        return False

    def _iso_date(self, value) -> str:
        """A stored date as YYYY-MM-DD; "" when the engine cannot read it.
        Remembered: the parser logs every value it cannot read."""
        text = _text(value)
        if text not in self._dates:
            parsed = _parse_date_safe(text)
            self._dates[text] = "" if parsed is None else parsed.strftime("%Y-%m-%d")
        return self._dates[text]

    # --- the edits ---------------------------------------------------------

    # action -> (the types of its arguments, the method that applies it)
    _ACTIONS: ClassVar[dict[str, tuple[tuple, str]]] = {
        "filter": ((str,), "_set_filter"),
        "open": ((str,), "_open"),
        "close": ((), "_close"),
        "reveal": ((str,), "_reveal"),
        "rule_add": ((), "_rule_add"),
        "rule_duplicate": ((str,), "_rule_duplicate"),
        "rule_delete": ((str,), "_rule_delete"),
        "rule_move": ((str, str), "_rule_move"),
        "rule_move_to": ((str, str), "_rule_move_to"),
        "rule_enabled": ((str, bool), "_rule_enabled"),
        "rule_name": ((str, str), "_rule_name"),
        "rule_level": ((str, str), "_rule_level"),
        "step_add": ((str,), "_step_add"),
        "step_remove": ((str, str), "_step_remove"),
        "step_match": ((str, str, str), "_step_match"),
        "cond_add": ((str, str), "_cond_add"),
        "cond_remove": ((str, str, str), "_cond_remove"),
        "cond_field": ((str, str, str, str), "_cond_field"),
        "cond_operator": ((str, str, str, str), "_cond_operator"),
        "cond_value": ((str, str, str, str), "_cond_value"),
        "action_add": ((str, str), "_action_add"),
        "action_remove": ((str, str, str), "_action_remove"),
        "action_type": ((str, str, str, str), "_action_type"),
        "action_param": ((str, str, str, str, str), "_action_param"),
    }

    def apply(self, action: str, args) -> bool:
        known = self._ACTIONS.get(action)
        if known is None or not _shaped(args, *known[0]):
            return False
        return bool(getattr(self, known[1])(*args))

    def _set_filter(self, text: str) -> bool:
        if text == self.filter:
            return False
        self.filter = text
        return True

    def _open(self, uid: str) -> bool:
        if self._rule(uid) is None or self.open_uid == uid:
            return False
        self.open_uid = uid
        return True

    def _close(self) -> bool:
        if self.open_uid is None:
            return False
        self.open_uid = None
        return True

    def _reveal(self, key: str) -> bool:
        found = _KEY_UID.match(key)
        return bool(found) and self._open(found.group(1))

    def _rule_add(self) -> bool:
        rule = {
            "uid": self._uid(),
            "name": NEW_RULE_NAME,
            "level": "article",
            "enabled": True,
            "steps": [_empty_step()],
            "extra": {},
        }
        self._place(rule, len(self._level_rules("article")))
        self.open_uid = rule["uid"]
        return True

    def _rule_duplicate(self, uid: str) -> bool:
        rule = self._rule(uid)
        if rule is None:
            return False
        twin = copy.deepcopy(rule)
        twin["uid"] = self._uid()
        twin["name"] = f"{rule['name']} copy"
        self.rules.insert(self.rules.index(rule) + 1, twin)
        return True

    def _rule_delete(self, uid: str) -> bool:
        rule = self._rule(uid)
        if rule is None:
            return False
        self.rules.remove(rule)
        if self.open_uid == uid:
            self.open_uid = None
        return True

    def _rule_move(self, uid: str, direction: str) -> bool:
        rule = self._rule(uid)
        if rule is None or direction not in ("up", "down"):
            return False
        position = self._level_rules(rule["level"]).index(rule)
        target = position + (-1 if direction == "up" else 1)
        return target >= 0 and self._rule_move_to(uid, str(target))

    def _rule_move_to(self, uid: str, position: str) -> bool:
        rule = self._rule(uid)
        if rule is None or not position.isdigit():
            return False
        group = self._level_rules(rule["level"])
        target = int(position)
        if target >= len(group) or target == group.index(rule):
            return False
        self.rules.remove(rule)
        self._place(rule, target)
        return True

    def _rule_enabled(self, uid: str, on: bool) -> bool:
        rule = self._rule(uid)
        if rule is None or rule["enabled"] == on:
            return False
        rule["enabled"] = on
        return True

    def _rule_name(self, uid: str, text: str) -> bool:
        rule = self._rule(uid)
        if rule is None or rule["name"] == text:
            return False
        rule["name"] = text
        return True

    def _rule_level(self, uid: str, level: str) -> bool:
        rule = self._rule(uid)
        if rule is None or level not in LEVELS or rule["level"] == level:
            return False
        self.rules.remove(rule)
        rule["level"] = level
        self._place(rule, len(self._level_rules(level)))
        return True

    def _step_add(self, uid: str) -> bool:
        rule = self._rule(uid)
        if rule is None:
            return False
        rule["steps"].append(_empty_step())
        return True

    def _step_remove(self, uid: str, s: str) -> bool:
        rule, step = self._step(uid, s)
        if step is None or s == "0":
            return False
        rule["steps"].remove(step)
        return True

    def _step_match(self, uid: str, s: str, match: str) -> bool:
        _rule, step = self._step(uid, s)
        if step is None or match not in ("ALL", "ANY") or step["match"] == match:
            return False
        step["match"] = match
        return True

    def _cond_add(self, uid: str, s: str) -> bool:
        rule, step = self._step(uid, s)
        if step is None:
            return False
        step["conditions"].append(
            {
                "field": self._fields(rule["level"])[0],
                "operator": CONDITION_OPERATORS[0],
                "value": "",
            }
        )
        return True

    def _condition(self, uid: str, s: str, c: str) -> tuple[dict | None, dict | None]:
        rule, step = self._step(uid, s)
        return rule, (None if step is None else _at(step["conditions"], c))

    def _cond_remove(self, uid: str, s: str, c: str) -> bool:
        _rule, step = self._step(uid, s)
        condition = None if step is None else _at(step["conditions"], c)
        if condition is None:
            return False
        del step["conditions"][int(c)]
        return True

    def _cond_field(self, uid: str, s: str, c: str, field: str) -> bool:
        rule, condition = self._condition(uid, s, c)
        if (
            condition is None
            or field not in self._fields(rule["level"])
            or condition["field"] == field
        ):
            return False
        condition["field"] = field
        return True

    def _cond_operator(self, uid: str, s: str, c: str, operator: str) -> bool:
        _rule, condition = self._condition(uid, s, c)
        if (
            condition is None
            or operator not in CONDITION_OPERATORS
            or condition["operator"] == operator
        ):
            return False
        if value_kind(operator) != value_kind(condition["operator"]):
            # A date is no use to a text operator, and the other way round.
            condition["value"] = ""
        condition["operator"] = operator
        return True

    def _cond_value(self, uid: str, s: str, c: str, text: str) -> bool:
        _rule, condition = self._condition(uid, s, c)
        if condition is None or condition["value"] == text:
            return False
        condition["value"] = text
        return True

    def _default_action(self, kind: str) -> dict:
        first = self._fields("article")[0]
        defaults = {
            "ADD_INTERNAL_TAG": {"value": ""},
            "REMOVE_INTERNAL_TAG": {"value": ""},
            "SET_STATUS": {"value": NOT_FULFILLABLE},
            "COPY_FIELD": {"source": first, "target": ""},
            "CALCULATE": {
                "operation": "add",
                "field1": first,
                "field2": first,
                "target": "",
            },
            "ALERT_NOTIFICATION": {"message": "", "severity": "info"},
            "ADD_PRODUCT": {"sku": "", "quantity": 1},
        }
        return {"type": kind, **defaults[kind]}

    def _action_add(self, uid: str, s: str) -> bool:
        _rule, step = self._step(uid, s)
        if step is None:
            return False
        step["actions"].append(self._default_action(ACTION_TYPES[0]))
        return True

    def _action(self, uid: str, s: str, a: str) -> tuple[dict | None, dict | None]:
        _rule, step = self._step(uid, s)
        return step, (None if step is None else _at(step["actions"], a))

    def _action_remove(self, uid: str, s: str, a: str) -> bool:
        step, action = self._action(uid, s, a)
        if action is None:
            return False
        del step["actions"][int(a)]
        return True

    def _action_type(self, uid: str, s: str, a: str, kind: str) -> bool:
        step, action = self._action(uid, s, a)
        if action is None or kind not in ACTION_TYPES or _kind(action) == kind:
            return False
        step["actions"][int(a)] = self._default_action(kind)
        return True

    def _action_param(self, uid: str, s: str, a: str, name: str, text: str) -> bool:
        _step, action = self._action(uid, s, a)
        if action is None:
            return False
        spec = next(
            (p for p in ACTION_PARAMS.get(_kind(action), ()) if p[0] == name), None
        )
        if spec is None:
            return False
        value = text
        if spec[1] == "field" and text not in self._fields("article"):
            return False
        if spec[1] == "choice" and text not in dict(_CHOICES[name]):
            return False
        if spec[1] == "number" and _valid_quantity(text):
            value = int(text.strip())
        if name in action and action[name] == value and type(action[name]) is type(value):
            return False
        action[name] = value
        return True

    # --- what is wrong, and what blocks a save -----------------------------

    def _condition_report(self, rule: dict, condition: dict) -> tuple[str, str, bool]:
        """(problem, hint, whether it blocks a save) for one condition row."""
        field, operator = condition["field"], condition["operator"]
        value = _text(condition["value"])
        # condition_error's alone, so Save refuses exactly what is marked.
        error = condition_error(operator, value)
        if error:
            return error, "", True
        if not field:
            return NO_FIELD, "", False
        if not self._resolvable(field, rule["level"]):
            unread = (
                f"“{field}” is not a field an {rule['level']} rule can read, "
                "so this condition never matches."
            )
            return unread, "", False
        if operator not in CONDITION_OPERATORS:
            unknown = (
                f"“{operator}” is not an operator this version knows, "
                "so this condition never matches."
            )
            return unknown, "", False
        if value_kind(operator) == "date" and not self._iso_date(value):
            return NO_DATE, "", False
        if operator in LIST_OPERATORS:
            return "", _plural(validate_list(value)[1], "item"), False
        return "", "", False

    def _action_report(self, action: dict) -> tuple[str, str, bool]:
        """(problem, hint, whether it blocks a save) for one action row."""
        kind = _kind(action)
        if kind == "ADD_PRODUCT":
            if not _valid_quantity(action.get("quantity", 1)):
                return QUANTITY_PROBLEM, "", True
            return "", "", False
        if kind == "SET_STATUS":
            return "", HOLD_HINT, False
        if kind in ("ADD_TAG", "ADD_ORDER_TAG"):
            return "", RETIRED_ONE, False
        if kind == "SET_MULTI_TAGS":
            return "", RETIRED_MANY, False
        if kind not in ACTION_PARAMS:
            return UNKNOWN_ACTION, "", False
        return "", "", False

    def _blocking(self, rule: dict) -> list[tuple[int, str, int, str, str]]:
        """(step, "condition" or "action", row, message, data-key), counted
        from 1, for every row of a rule that blocks a save."""
        uid, found = rule["uid"], []
        for s, step in enumerate(rule["steps"]):
            for c, condition in enumerate(step["conditions"]):
                problem, _hint, blocks = self._condition_report(rule, condition)
                if blocks:
                    key = f"rule-{uid}-s{s}-c{c}-value"
                    found.append((s + 1, "condition", c + 1, problem, key))
            for a, action in enumerate(step["actions"]):
                problem, _hint, blocks = self._action_report(action)
                if blocks:
                    key = f"rule-{uid}-s{s}-a{a}-quantity"
                    found.append((s + 1, "action", a + 1, problem, key))
        return found

    def _first_blocked(self) -> tuple[int, dict, tuple] | None:
        for position, rule in enumerate(self.rules):
            blocking = self._blocking(rule)
            if blocking:
                return position, rule, blocking[0]
        return None

    def blocker(self) -> str | None:
        blocked = self._first_blocked()
        if blocked is None:
            return None
        position, rule, _row = blocked
        return f"Fix rule “{rule['name']}”" if rule["name"] else f"Fix rule {position + 1:02d}"

    def blocker_key(self) -> str:
        blocked = self._first_blocked()
        return "" if blocked is None else blocked[2][4]

    def validate(self) -> tuple[bool, list[str]]:
        """Refuse to save a rule the page marks red (AUDIT-03-5)."""
        errors = [
            f"Rule “{rule['name']}”, step {s}, {row} {n}: {message}"
            for rule in self.rules
            for s, row, n, message, _key in self._blocking(rule)
        ]
        return not errors, errors

    # --- the contract ------------------------------------------------------

    def collect(self) -> dict:
        return {
            "rules": [
                self._stored(rule, priority=position + 1)
                for position, rule in enumerate(self.rules)
            ]
        }

    def _untestable(self, rule: dict) -> str:
        """Why Test cannot run this rule; "" when it can."""
        if not self._has_analysis():
            return TEST_NO_ANALYSIS
        if not any(step["conditions"] for step in rule["steps"]):
            return TEST_NO_CONDITION
        if self._blocking(rule):
            return TEST_BLOCKED
        return ""

    def test_config(self, uid: str) -> dict | None:
        """The rule as Test runs it: what Save would store, without its
        place in the list and whether or not it is on. None when it cannot
        be tested."""
        rule = self._rule(uid)
        if rule is None or self._untestable(rule):
            return None
        stored = self._stored(rule)
        stored.pop("enabled", None)
        return stored

    # --- the view ----------------------------------------------------------

    def _summary(self, rule: dict) -> list[dict]:
        lines = []
        for s, step in enumerate(rule["steps"]):
            join = "or" if step["match"] == "ANY" else "and"
            when = []
            for c, condition in enumerate(step["conditions"]):
                if c:
                    when.append(_part("join", join))
                when.append(_part("bold", condition["field"]))
                when.append(_part("text", condition["operator"]))
                value = _text(condition["value"])
                if value_kind(condition["operator"]) != "none" and value != "":
                    when.append(_part("chip", value))
            then = []
            for a, action in enumerate(step["actions"]):
                if a:
                    then.append(_part("join", "and"))
                then.extend(_action_parts(action))
            lines.append(
                {
                    "label": "And when" if s else "When",
                    "parts": when or [_part("muted", NO_CONDITION)],
                }
            )
            lines.append({"label": "Then", "parts": then or [_part("muted", NO_ACTION)]})
        return lines

    def _row_problem(self, rule: dict) -> str:
        blocking = self._blocking(rule)
        if not blocking:
            return ""
        s, row, n, message, _key = blocking[0]
        where = f"{row.capitalize()} {n}"
        if len(rule["steps"]) > 1:
            where = f"Step {s}, {row} {n}"
        return f"{where}: {message}"

    def _condition_view(self, rule: dict, condition: dict) -> dict:
        field, operator = condition["field"], condition["operator"]
        problem, hint, blocks = self._condition_report(rule, condition)
        kind = value_kind(operator)
        resolvable = self._resolvable(field, rule["level"])
        offered = field in self._fields(rule["level"])
        suggestions = []
        if kind == "text" and operator in EQUALITY_OPERATORS and self._has_analysis():
            suggestions = get_unique_column_values(self.analysis_df, field)
        text = _text(condition["value"])
        return {
            "field": field,
            # A stored field the level does not offer: listed first, and kept.
            "extra_field": None
            if offered or not field
            else {"value": field, "note": "" if resolvable else NOT_AVAILABLE},
            "field_invalid": not resolvable,
            "operator": operator,
            "extra_operator": None if operator in CONDITION_OPERATORS else operator,
            "value": {
                "kind": kind,
                "text": self._iso_date(text) if kind == "date" else text,
                "placeholder": _PLACEHOLDER.get(operator, "Value"),
                "suggestions": suggestions[:SUGGESTION_LIMIT],
            },
            "problem": problem,
            "hint": hint,
            "invalid": blocks,
        }

    def _param_view(self, action: dict, spec: tuple, blocks: bool) -> dict:
        name, kind, placeholder, lead = spec
        value = _text(action.get(name))
        options, extra = [], None
        if kind == "suggest":
            options = self.configured_tags()
        elif kind == "field":
            options = self._fields("article")
            if value and value not in options:
                extra = value
        elif kind == "choice":
            options = [{"value": v, "label": label} for v, label in _CHOICES[name]]
        return {
            "name": name,
            "kind": kind,
            "value": value,
            "placeholder": placeholder,
            "lead": lead,
            "options": options,
            "extra": extra,
            "invalid": blocks and kind == "number",
        }

    def _action_view(self, action: dict) -> dict:
        kind = _kind(action)
        problem, hint, blocks = self._action_report(action)
        label = ACTION_LABELS.get(kind, _text(action.get("type")))
        return {
            "type": kind,
            "label": label,
            # A type the menu does not offer is listed on this row only.
            "extra_type": None
            if kind in ACTION_TYPES
            else {"value": kind, "label": label},
            "params": [
                self._param_view(action, spec, blocks)
                for spec in ACTION_PARAMS.get(kind, ())
            ],
            "problem": problem,
            "hint": hint,
        }

    def _step_view(self, rule: dict, s: int, step: dict) -> dict:
        several = len(rule["steps"]) > 1
        note = ""
        if several and s:
            note = (
                f"Runs only if step {s} matched."
                if rule["level"] == "order"
                else f"Checks only the lines step {s} matched."
            )
        return {
            "title": f"Step {s + 1}" if several else "",
            "note": note,
            "removable": s > 0,
            "match": {
                "show": len(step["conditions"]) > 1,
                "options": [
                    {"value": value, "label": label, "checked": step["match"] == value}
                    for value, label in (("ALL", "All"), ("ANY", "Any"))
                ],
                "tail": "of these match",
            },
            "conditions": [self._condition_view(rule, c) for c in step["conditions"]],
            "actions": [self._action_view(a) for a in step["actions"]],
        }

    def _editor(self, rule: dict) -> dict:
        return {
            "level": {
                "options": [
                    {
                        "value": level,
                        "label": LEVEL_LABEL[level],
                        "checked": rule["level"] == level,
                    }
                    for level in LEVELS
                ],
                "hint": LEVEL_HINT[rule["level"]],
            },
            "field_groups": [
                {"label": label, "fields": fields}
                for label, fields in rule_fields(rule["level"], self.analysis_df)
            ],
            "operators": list(CONDITION_OPERATORS),
            "action_types": [
                {"value": kind, "label": ACTION_LABELS[kind]} for kind in ACTION_TYPES
            ],
            "steps": [
                self._step_view(rule, s, step) for s, step in enumerate(rule["steps"])
            ],
        }

    def _row(self, position: int, rule: dict, filtering: bool) -> dict:
        group = self._level_rules(rule["level"])
        place = group.index(rule)
        is_open = rule["uid"] == self.open_uid
        untestable = self._untestable(rule)
        return {
            "uid": rule["uid"],
            "num": f"{position + 1:02d}",
            "name": rule["name"],
            # What the row calls the rule: a rule can be saved with no name.
            "label": rule["name"] or UNNAMED,
            "on": rule["enabled"],
            "open": is_open,
            "switch_title": "Turn off" if rule["enabled"] else "Turn on",
            "badge": "" if rule["enabled"] else "Off",
            "can_up": not filtering and place > 0,
            "can_down": not filtering and place < len(group) - 1,
            "can_drag": not filtering and len(group) > 1,
            "move_title": CLEAR_FILTER if filtering else "",
            "can_test": not untestable,
            "test_title": untestable,
            "summary": self._summary(rule),
            "wide_labels": len(rule["steps"]) > 1,
            "problem": self._row_problem(rule),
            "editor": self._editor(rule) if is_open else None,
        }

    def view(self) -> dict:
        needle = self.filter.strip().lower()
        both = bool(self._level_rules("article")) and bool(self._level_rules("order"))
        groups = []
        for level in LEVELS:
            rows = [
                self._row(position, rule, bool(needle))
                for position, rule in enumerate(self.rules)
                if rule["level"] == level
                and (
                    not needle
                    or needle in rule["name"].lower()
                    or rule["uid"] == self.open_uid
                )
            ]
            if rows:
                label, note = GROUPS[level] if both else ("", "")
                groups.append({"level": level, "label": label, "note": note, "rows": rows})
        on = sum(1 for rule in self.rules if rule["enabled"])
        return {
            "page": "rules",
            "title": "Rules",
            "subtitle": SUBTITLE,
            # With no rule the empty state holds the button.
            "action": ADD_RULE if self.rules else "",
            "rules": {
                "empty": None
                if self.rules
                else {"title": EMPTY_TITLE, "text": EMPTY_TEXT, "action": ADD_RULE},
                "filter": self.filter,
                "filter_placeholder": "Filter by name",
                "filtering": bool(needle),
                "count": f"{_plural(len(self.rules), 'rule')} · {on} on",
                "no_hits": f"No rules named “{self.filter.strip()}”."
                if self.rules and not groups
                else "",
                "groups": groups,
            },
        }
```

- [ ] **Step 4: Run the tests and the lint**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_settings_draft_rules.py`
Expected: all pass. (`177 passed`.)

Run: `.venv/bin/ruff check .`
Expected: `All checks passed!`

- [ ] **Step 5: Commit**

`/usr/bin/git add -A`, then write this message to a file under your job's tmp dir and commit with
`/usr/bin/git commit -F <that file>`. Subject: `Settings: RulesDraft, the rules page's values with no widget`. Body: one or two sentences: what it holds, and that it keeps what it has no control for. End the message with the
attribution lines your session is given.

### Task 4: `run_rule_test`

**Files:**
- Create: `gui/settings/rule_test.py`
- Test: `tests/test_rule_test.py`

**Interfaces:**
- Consumes: `RuleEngine` and its `matched_rows` (a boolean Series on the input frame's index, set by
  `apply`); Task 1's rule that an engine skips a rule that is off; `cell_display_text` from
  `gui/pandas_model.py`; `parse_tags` from `shopify_tool/tag_manager.py`; `NOT_FULFILLABLE` from
  `shopify_tool/stock_ledger.py`.
- Produces, for Tasks 5 and 6:
  - `run_rule_test(rule: dict, df: pd.DataFrame, session: str = "", limit: int = 5) -> dict`
  - `running_view(rule: dict, df: pd.DataFrame, session: str = "") -> dict`
  - `failed_view(rule: dict, session: str = "") -> dict`
  - Each returns the same keys: `status` (`"running"`, `"done"`, `"failed"`), `title`, `intro`
    (`lead`, `session`, `tail`), `message`, `matched`, `total`, `heads`, `rows` (each `order`, `why`,
    `change`, `changed`), `more`, `empty`, `note`. The host adds `uid`.
  - Constants the tests import: `FAILED`, `HEADS`, `NO_CHANGE`, `NO_CHANGE_NOTE`, `NO_MATCH`.

Spec §6.1 and §6.3. This replaces the logic of `gui/rule_test_dialog.py`, which is deleted in Task 7.

`RuleEngine.apply` only ever appends rows: the first `len(df)` rows of what it returns are `df`'s rows in
order, and any below them are lines the rule added. The function reads rows by position for that reason, and
never by label: `apply` reindexes when it appends.

- [ ] **Step 1: Write the failing tests**

**Create `tests/test_rule_test.py`:**

```python
"""run_rule_test: what the Test panel says about one rule (phase 8 spec section 6).

Plain Python on a small analysis-shaped frame. No widget and no Chromium.
"""

import pandas as pd
import pytest

from gui.settings.rule_test import (
    FAILED,
    HEADS,
    NO_CHANGE,
    NO_CHANGE_NOTE,
    NO_MATCH,
    failed_view,
    run_rule_test,
    running_view,
)
from shopify_tool.rules import RuleEngine


def frame(rows):
    """Analysis-shaped: (order, sku, quantity) lines, all Fulfillable."""
    return pd.DataFrame(
        {
            "Order_Number": [r[0] for r in rows],
            "SKU": [r[1] for r in rows],
            "Quantity": [r[2] for r in rows],
            "Stock": [10] * len(rows),
            "Product_Name": [f"P-{r[1]}" for r in rows],
            "Order_Fulfillment_Status": ["Fulfillable"] * len(rows),
            "System_note": [""] * len(rows),
            "Status_Note": [""] * len(rows),
            "Internal_Tags": ["[]"] * len(rows),
        }
    )


ORDERS = [("#1", "A", 4), ("#1", "B", 3), ("#2", "B", 1), ("#3", "A", 1)]


def cond(field, operator, value=""):
    return {"field": field, "operator": operator, "value": value}


def tag(value="T"):
    return {"type": "ADD_INTERNAL_TAG", "value": value}


def rule(conditions, actions, level="article", match="ALL", name="r", **extra):
    return {
        "name": name,
        "level": level,
        **extra,
        "steps": [{"conditions": conditions, "match": match, "actions": actions}],
    }


SKU_A = [cond("SKU", "equals", "A")]


def listed(view):
    return [(row["order"], row["why"], row["change"]) for row in view["rows"]]


def test_it_counts_orders_and_lists_what_matched_and_what_changed():
    view = run_rule_test(rule(SKU_A, [tag("priority")], name="VIP"), frame(ORDERS), "2026-09-30_1")
    assert view["status"] == "done"
    assert view["title"] == "Test “VIP”"
    assert view["intro"] == {
        "lead": "Runs this rule, as edited, against the analysis in ",
        "session": "2026-09-30_1",
        "tail": ". Orders aren’t changed.",
    }
    assert (view["matched"], view["total"]) == ("2", "of 3 orders match")
    assert view["heads"] == HEADS == ["Order", "Matched on", "Change"]
    assert listed(view) == [("#1", "SKU: A", "+ priority"), ("#3", "SKU: A", "+ priority")]
    assert [row["changed"] for row in view["rows"]] == [True, True]
    assert (view["more"], view["empty"], view["note"], view["message"]) == ("", "", "", "")


def test_the_analysis_is_left_as_it_was():
    df = frame(ORDERS)
    before = df.copy()
    run_rule_test(rule(SKU_A, [tag(), {"type": "ADD_PRODUCT", "sku": "GIFT", "quantity": 1}]), df)
    pd.testing.assert_frame_equal(df, before)


def test_with_no_session_name_it_says_the_last_analysis():
    view = run_rule_test(rule(SKU_A, [tag()]), frame(ORDERS))
    assert view["intro"] == {
        "lead": "Runs this rule, as edited, against the last analysis",
        "session": "",
        "tail": ". Orders aren’t changed.",
    }


def test_a_rule_that_is_off_still_runs():
    view = run_rule_test(rule(SKU_A, [tag()], enabled=False), frame(ORDERS))
    assert view["matched"] == "2"


def test_only_the_first_five_are_listed():
    df = frame([(f"#{n}", "A", 1) for n in range(1, 9)])
    view = run_rule_test(rule(SKU_A, [tag()]), df)
    assert (view["matched"], view["total"]) == ("8", "of 8 orders match")
    assert [row["order"] for row in view["rows"]] == ["#1", "#2", "#3", "#4", "#5"]
    assert view["more"] == "and 3 more"


def test_no_match_says_so():
    view = run_rule_test(rule([cond("SKU", "equals", "Z")], [tag()]), frame(ORDERS))
    assert (view["matched"], view["rows"], view["empty"], view["more"]) == ("0", [], NO_MATCH, "")


def test_one_order_is_singular():
    view = run_rule_test(rule(SKU_A, [tag()]), frame([("#1", "A", 1)]))
    assert (view["matched"], view["total"]) == ("1", "of 1 order matches")


def test_a_frame_with_no_order_numbers_counts_its_lines():
    df = frame(ORDERS).drop(columns="Order_Number")
    view = run_rule_test(rule(SKU_A, [{"type": "COPY_FIELD", "source": "SKU", "target": "Code"}]), df)
    assert (view["matched"], view["total"]) == ("2", "of 4 orders match")
    assert [row["order"] for row in view["rows"]] == ["0", "3"]


def test_an_analysis_with_a_blank_order_number_and_list_cells_is_still_tested():
    df = frame([*ORDERS, (None, "A", 2)])
    df["Lot_Details"] = [[{"lot": 1}], [], [{"lot": 1}, {"lot": 2}], [], []]
    df[7] = "x"  # a column whose name is not text
    view = run_rule_test(rule(SKU_A, [{"type": "COPY_FIELD", "source": "SKU", "target": 7}]), df)
    assert (view["status"], view["matched"], view["total"]) == ("done", "3", "of 4 orders match")
    assert listed(view) == [
        ("#1", "SKU: A", "7 → A"),
        ("#3", "SKU: A", "7 → A"),
        ("", "SKU: A", "7 → A"),
    ]


# --- Matched on --------------------------------------------------------------


def test_an_article_rule_shows_the_lines_that_matched():
    view = run_rule_test(rule([cond("Quantity", "is greater than", "2")], [tag()]), frame(ORDERS))
    assert listed(view) == [("#1", "Quantity: 4; 3", "+ T")]


def test_an_order_rule_shows_every_line_of_the_order():
    view = run_rule_test(rule(SKU_A, [tag()], level="order"), frame(ORDERS))
    assert listed(view)[0] == ("#1", "SKU: A; B", "+ T")


def test_a_numeric_order_field_shows_what_the_engine_worked_out():
    conditions = [cond("total_quantity", "is greater than", "5"), cond("item_count", "equals", "2")]
    view = run_rule_test(rule(conditions, [tag()], level="order"), frame(ORDERS))
    assert listed(view) == [("#1", "total_quantity: 7 · item_count: 2", "+ T")]


def test_a_yes_or_no_order_field_shows_what_it_was_asked():
    view = run_rule_test(rule([cond("has_sku", "equals", "B")], [tag()], level="order"), frame(ORDERS))
    assert [row["why"] for row in view["rows"]] == ["has_sku: B", "has_sku: B"]


def test_a_field_is_named_once_and_more_than_three_values_trail_off():
    df = frame([("#1", sku, 1) for sku in "ABCDE"])
    conditions = [cond("SKU", "is not empty"), cond("SKU", "does not equal", "Z")]
    view = run_rule_test(rule(conditions, [tag()]), df)
    assert listed(view) == [("#1", "SKU: A; B; C; …", "+ T")]


def test_an_empty_cell_reads_empty():
    df = frame(ORDERS)
    df["Notes"] = [None, "", "x", "y"]
    view = run_rule_test(rule([cond("Notes", "is empty")], [tag()]), df)
    assert listed(view) == [("#1", "Notes: empty", "+ T")]


def test_a_field_the_engine_cannot_read_is_left_out():
    conditions = [cond("SKU", "equals", "A"), cond("Nope", "equals", "x")]
    view = run_rule_test(rule(conditions, [tag()], match="ANY"), frame(ORDERS))
    assert [row["why"] for row in view["rows"]] == ["SKU: A", "SKU: A"]


def test_every_step_of_a_rule_is_read():
    stepped = rule(SKU_A, [tag("one")])
    stepped["steps"].append(
        {"conditions": [cond("Quantity", "is greater than", "2")], "match": "ALL", "actions": [tag("two")]}
    )
    view = run_rule_test(stepped, frame(ORDERS))
    assert listed(view) == [
        ("#1", "SKU: A · Quantity: 4", "+ one, + two"),
        ("#3", "SKU: A · Quantity: 1", "+ one"),
    ]


# --- Change ------------------------------------------------------------------


def test_removing_a_tag():
    df = frame(ORDERS)
    df["Internal_Tags"] = '["old", "keep"]'
    view = run_rule_test(rule(SKU_A, [{"type": "REMOVE_INTERNAL_TAG", "value": "old"}, tag("new")]), df)
    assert view["rows"][0]["change"] == "+ new, − old"


def test_a_hold_reads_held_and_hides_its_reason_code():
    hold = rule(SKU_A, [{"type": "SET_STATUS", "value": "Not Fulfillable"}], name="big")
    view = run_rule_test(hold, frame(ORDERS))
    assert [row["change"] for row in view["rows"]] == ["Held", "Held"]


@pytest.mark.parametrize(
    "action, change",
    [
        ({"type": "COPY_FIELD", "source": "SKU", "target": "Code"}, "Code → A"),
        ({"type": "COPY_FIELD", "source": "SKU", "target": "Product_Name"}, "Product_Name → A"),
        (
            {"type": "CALCULATE", "operation": "multiply", "field1": "Quantity", "field2": "Stock", "target": "Total"},
            "Total → 40.0",
        ),
        ({"type": "ADD_TAG", "value": "VIP"}, "Status_Note → VIP"),
        ({"type": "SET_MULTI_TAGS", "value": "A, B"}, "Status_Note → A, B"),
        ({"type": "ADD_PRODUCT", "sku": "GIFT", "quantity": 2}, "+ GIFT ×2"),
        ({"type": "ALERT_NOTIFICATION", "message": "look", "severity": "info"}, NO_CHANGE),
    ],
)
def test_each_action_reads_as_its_change(action, change):
    view = run_rule_test(rule(SKU_A, [action]), frame(ORDERS))
    assert view["rows"][0]["change"] == change


def test_several_changes_are_joined():
    actions = [tag("gift"), {"type": "ADD_PRODUCT", "sku": "GIFT", "quantity": 1}]
    view = run_rule_test(rule(SKU_A, actions), frame(ORDERS))
    assert view["rows"][0]["change"] == "+ gift, + GIFT ×1"


def test_an_order_the_saved_rules_already_changed_reads_no_change():
    tagging = rule(SKU_A, [tag("T")])
    analysed = RuleEngine([tagging]).apply(frame(ORDERS))
    view = run_rule_test(tagging, analysed)
    assert view["matched"] == "2"
    assert [(row["change"], row["changed"]) for row in view["rows"]] == [(NO_CHANGE, False)] * 2
    assert view["note"] == NO_CHANGE_NOTE == (
        "No change: the analysis already has the saved rules applied."
    )


# --- the other two states ----------------------------------------------------


def test_running_says_how_many_orders():
    view = running_view(rule(SKU_A, [tag()], name="VIP"), frame(ORDERS), "S1")
    assert (view["status"], view["message"]) == ("running", "Testing 3 orders…")
    assert view["title"] == "Test “VIP”"
    assert view["intro"]["session"] == "S1"
    assert view["rows"] == []
    assert running_view(rule(SKU_A, []), frame([("#1", "A", 1)]))["message"] == "Testing 1 order…"


def test_failed_says_where_to_look():
    view = failed_view(rule(SKU_A, [tag()], name="VIP"), "S1")
    assert (view["status"], view["message"]) == ("failed", FAILED)
    assert FAILED == "The rule test didn’t finish. Details are in Logs."


def test_every_state_has_the_same_keys():
    r, df = rule(SKU_A, [tag()]), frame(ORDERS)
    assert set(running_view(r, df)) == set(failed_view(r)) == set(run_rule_test(r, df))
```

- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_rule_test.py`
Expected: collection stops with `ModuleNotFoundError: No module named 'gui.settings.rule_test'` (`1 error`).

- [ ] **Step 3: Write the function**

**Create `gui/settings/rule_test.py`:**

```python
"""Test rule: one rule, as edited, run on a copy of the analysis (phase 8 spec
section 6).

run_rule_test returns everything the Test panel draws, sentences included.
It counts orders, lists the first few that match with what they matched on
and what the rule changed, and leaves the analysis as it found it. No widget:
SettingsWebHost runs it on a worker thread.
"""

import numpy as np
import pandas as pd

from gui.pandas_model import cell_display_text
from shopify_tool.rules import RuleEngine
from shopify_tool.stock_ledger import NOT_FULFILLABLE
from shopify_tool.tag_manager import parse_tags

LIMIT = 5
# How many of an order's values Matched on spells out before it trails off.
VALUES_SHOWN = 3
HEADS = ["Order", "Matched on", "Change"]
NO_CHANGE = "No change"
NO_CHANGE_NOTE = "No change: the analysis already has the saved rules applied."
NO_MATCH = "No order in this analysis matches."
FAILED = "The rule test didn’t finish. Details are in Logs."
# The order fields the engine works out as a number. The others (has_sku and
# its kin) answer yes or no about the condition's own value.
NUMERIC_ORDER_FIELDS = (
    "item_count",
    "total_quantity",
    "unique_sku_count",
    "max_quantity",
    "order_volumetric_weight",
)
# Written by a hold beside the status: its reason code, not a change to show.
_UNLISTED = ("Internal_Tags", "Order_Fulfillment_Status", "System_note")


def _order_keys(df: pd.DataFrame) -> pd.Series:
    """What tells one order from the next: its number, or the line itself in
    a frame that has none."""
    if "Order_Number" in df.columns:
        return df["Order_Number"]
    return pd.Series(df.index.astype(str), index=df.index)


def _orders_text(count: int) -> str:
    return "1 order" if count == 1 else f"{count} orders"


def _view(rule: dict, session: str, status: str, **drawn) -> dict:
    """One state of the panel. Every state carries every key, so the page
    never has to ask whether one is there."""
    view = {
        "status": status,
        "title": f"Test “{rule.get('name', '')}”",
        "intro": {
            "lead": "Runs this rule, as edited, against the analysis in "
            if session
            else "Runs this rule, as edited, against the last analysis",
            "session": session,
            "tail": ". Orders aren’t changed.",
        },
        "message": "",
        "matched": "",
        "total": "",
        "heads": HEADS,
        "rows": [],
        "more": "",
        "empty": "",
        "note": "",
    }
    view.update(drawn)
    return view


def running_view(rule: dict, df: pd.DataFrame, session: str = "") -> dict:
    total = _order_keys(df).nunique(dropna=False)
    return _view(rule, session, "running", message=f"Testing {_orders_text(total)}…")


def failed_view(rule: dict, session: str = "") -> dict:
    return _view(rule, session, "failed", message=FAILED)


def _number(value) -> str:
    number = float(value)
    return str(int(number)) if number.is_integer() else str(round(number, 2))


def _matched_on(rule: dict, engine: RuleEngine, order: pd.DataFrame, lines: pd.DataFrame) -> str:
    """What the rule's conditions read on this order: `field: value` for each
    field, once, in the rule's order."""
    order_rule = rule.get("level") == "order"
    parts, seen = [], set()
    for step in rule.get("steps", []):
        for condition in step.get("conditions", []):
            field = condition.get("field")
            if not field or field in seen:
                continue
            seen.add(field)
            if field in order.columns:
                values = list(dict.fromkeys(cell_display_text(v) or "empty" for v in lines[field]))
                # "; " and not ", ": a value can hold commas (Tags: VIP, repeat).
                shown = "; ".join(values[:VALUES_SHOWN])
                if len(values) > VALUES_SHOWN:
                    shown += "; …"
                parts.append(f"{field}: {shown}")
            elif order_rule and field in NUMERIC_ORDER_FIELDS:
                worked_out = getattr(engine, RuleEngine.ORDER_LEVEL_FIELDS[field])(order, None)
                parts.append(f"{field}: {_number(worked_out)}")
            elif order_rule and field in RuleEngine.ORDER_LEVEL_FIELDS:
                parts.append(f"{field}: {cell_display_text(condition.get('value'))}")
    return " · ".join(parts)


def _tags(lines: pd.DataFrame) -> list[str]:
    if "Internal_Tags" not in lines.columns:
        return []
    return list(dict.fromkeys(tag for value in lines["Internal_Tags"] for tag in parse_tags(value)))


def _texts(lines: pd.DataFrame, column: str) -> np.ndarray:
    return np.array([cell_display_text(value) for value in lines[column]], dtype=object)


def _change(before: pd.DataFrame, after: pd.DataFrame, added: pd.DataFrame) -> str:
    """What the rule did to one order, from its lines before and after."""
    was, now = _tags(before), _tags(after)
    parts = [f"+ {tag}" for tag in now if tag not in was]
    parts += [f"− {tag}" for tag in was if tag not in now]

    status = "Order_Fulfillment_Status"
    if status in before.columns and status in after.columns:
        changed = _texts(before, status) != _texts(after, status)
        if changed.any():
            value = _texts(after, status)[changed][0]
            # A rule can only hold an order (spec 2026-09-26 D3).
            parts.append("Held" if value == NOT_FULFILLABLE else f"{status} → {value}")

    for column in after.columns:
        if column in _UNLISTED:
            continue
        shown = _texts(after, column)
        if column in before.columns:
            changed = _texts(before, column) != shown
        else:
            # A column the rule made: empty on every line it did not write.
            changed = shown != ""
        if changed.any():
            parts.append(f"{column} → {shown[changed][0]}")

    for _label, line in added.iterrows():
        sku = cell_display_text(line.get("SKU"))
        parts.append(f"+ {sku} ×{cell_display_text(line.get('Quantity'))}")
    return ", ".join(parts) or NO_CHANGE


def run_rule_test(rule: dict, df: pd.DataFrame, session: str = "", limit: int = LIMIT) -> dict:
    """Run `rule` on a copy of `df` and say which orders it matched.

    The rule runs whether or not it is stored as on. `df` is not changed.
    """
    engine = RuleEngine([{key: value for key, value in rule.items() if key != "enabled"}])
    after = engine.apply(df.copy())
    # apply() only ever appends: the first len(df) rows of `after` are df's
    # rows in order, and any below them are lines the rule added.
    existing, added = after.iloc[: len(df)], after.iloc[len(df) :]
    matched = engine.matched_rows.to_numpy(dtype=bool)

    codes, orders = pd.factorize(_order_keys(df), use_na_sentinel=False)
    hit = pd.unique(codes[matched])
    added_keys = _order_keys(added).to_numpy() if len(added) else np.array([], dtype=object)

    rows = []
    for code in hit[:limit]:
        of_order = codes == code
        lines = of_order if rule.get("level") == "order" else of_order & matched
        change = _change(df[of_order], existing[of_order], added[added_keys == orders[code]])
        rows.append(
            {
                "order": cell_display_text(orders[code]),
                "why": _matched_on(rule, engine, df[of_order], df[lines]),
                "change": change,
                "changed": change != NO_CHANGE,
            }
        )

    more = len(hit) - len(rows)
    total = len(orders)
    return _view(
        rule,
        session,
        "done",
        matched=str(len(hit)),
        total="of 1 order matches" if total == 1 else f"of {total} orders match",
        rows=rows,
        more=f"and {more} more" if more else "",
        empty="" if len(hit) else NO_MATCH,
        note=NO_CHANGE_NOTE if any(not row["changed"] for row in rows) else "",
    )
```

- [ ] **Step 4: Run the tests and the lint**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_rule_test.py`
Expected: all pass. (`31 passed`.)

Run: `.venv/bin/ruff check .`
Expected: `All checks passed!`

- [ ] **Step 5: Commit**

`/usr/bin/git add -A`, then write this message to a file under your job's tmp dir and commit with
`/usr/bin/git commit -F <that file>`. Subject: `Settings: run_rule_test, one rule over the whole analysis, counted in orders`. Body: one or two sentences: what it returns, and that the frame is left as it was. End the message with the
attribution lines your session is given.

### Task 5: The bridge and the page

**Files:**
- Modify: `gui/settings/bridge.py`, `gui/web/settings.js`, `gui/web/settings.css`, `gui/web/settings.html`
- Create: `gui/web/settings_rules.js`
- Test: `tests/test_settings_bridge.py`, `tests/test_settings_rules_page.py` (new)

**Interfaces:**
- Consumes: `RulesDraft.view()` and `.apply()` (Task 3); `run_rule_test`, `running_view`, `failed_view`
  (Task 4); `--scrim`, `--color-scheme` (Task 2); the kit's `.card`, `.btn`, `.switch`, `.select`,
  `.menu`, `.menu-item`, `.menu-group`, `.segmented`, `.segment`, `.field`, `.input`, `.badge`, `.state`,
  `.hint`, `.problem`; `settings.js`'s `esc`, `svg`, `off`, `menuItem`, `problemLine`, `focusKey`,
  `closeMenu`, `byKey`, `GLYPH`, `view`, `page`, `els`.
- Produces:
  - `SettingsBridge.testRule(uid)` (a Slot) → `testRequested(str)`; `SettingsBridge.closeTest()` →
    `testClosed()`. Task 6 connects both.
  - A page that draws `state["rules"]` and `state["test"]`, and whose controls carry the `data-key`s of
    spec §5.6. Task 6's `focus_problem` and `RulesDraft.blocker_key()` rely on those keys.

Spec §3.2, §5 and §6.4. The window still shows the Qt Rules page after this task: nothing pushes a
`rules` state yet outside the tests. The tests push views built by `RulesDraft` straight into the bridge,
as phase 7's page tests do.

`settings_rules.js` is loaded before `settings.js` and calls its helpers. That works because both are
classic scripts sharing one global scope, and nothing in `settings_rules.js` runs until `settings.js` has
bound the page and the channel has answered.

How the page keeps its place (read this before you touch `morph` or the keys):

- Every control has a `data-key` built from the rule's uid, never from its position in the list, so a rule
  that moves keeps its keys and the render can give focus back to the same control.
- A row carries `data-key="rule-<uid>"`. `morph` replaces a node whose key differs from the one arriving at
  its position; that is what moves a row.
- A menu's name is the `data-key` of the control that opens it. `closeMenu()` therefore returns focus to the
  opener, and a menu whose opener is gone is dropped after the render.
- `view.pending` is a key to focus once the state that draws it arrives. Two requests are not keys:
  `"@open-name"` (focus the open rule's name and select it) and `"@move:<uid>:<dir>"` (focus the move
  button just pressed, or the other one when the rule reached its group's edge).

- [ ] **Step 1: Write the failing tests**

**Modify `tests/test_settings_bridge.py`.**
 Find exactly:

```python
"""The settings pages' bridge (phase 7 spec section 3.3)."""

import pytest
from PySide6.QtWidgets import QApplication
```

Replace with:

```python
"""The settings pages' bridge (phase 7 spec section 3.3, phase 8 spec section 3.2)."""

import pytest
from PySide6.QtWidgets import QApplication
```

 Append at the end of the file:

```python
def test_test_rule_names_the_rule_and_close_test_says_so():
    bridge = SettingsBridge()
    asked = _caught(bridge.testRequested)
    closed = _caught(bridge.testClosed)
    bridge.testRule("4")
    bridge.closeTest()
    assert asked == [("4",)]
    assert closed == [()]
```

**Create `tests/test_settings_rules_page.py`:**

```python
"""The Rules page and the Test rule panel, driven through a real Chromium
(phase 8 spec sections 5 and 6).

The page is a renderer: every test pushes a view built by RulesDraft and
reads the DOM back, or clicks and reads what the bridge was sent. 868x700 is
the page area a small dialog gives. Never mark skip.
"""

import json

import pandas as pd
import pytest
from PySide6.QtWebEngineWidgets import QWebEngineView
from test_results_bridge import _eval, _rgb, _until_js
from test_settings_web_page import (
    _active,
    _attr,
    _click,
    _count,
    _key,
    _keydown,
    _prop,
    _show,
    _style,
    _text,
    _texts,
    _type,
)

from gui.settings.bridge import PAGE, mount_settings_page
from gui.settings.rule_test import failed_view, run_rule_test, running_view
from gui.settings.rules_state import (
    CLEAR_FILTER,
    HOLD_HINT,
    RETIRED_ONE,
    TEST_NO_ANALYSIS,
    RulesDraft,
)
from gui.theme_manager import get_theme_manager

TAGS = {
    "version": 2,
    "categories": {"h": {"label": "H", "color": "#FF0000", "tags": ["priority", "heavy"], "order": 1}},
}


def cond(field="SKU", operator="equals", value="A"):
    return {"field": field, "operator": operator, "value": value}


def tag(value="T"):
    return {"type": "ADD_INTERNAL_TAG", "value": value}


def rule(name, level="article", conditions=None, actions=None, match="ALL", **extra):
    return {
        "name": name,
        "level": level,
        **extra,
        "steps": [
            {
                "conditions": [cond()] if conditions is None else conditions,
                "match": match,
                "actions": [tag()] if actions is None else actions,
            }
        ],
    }


def frame():
    return pd.DataFrame(
        {
            "Order_Number": ["#1", "#1", "#2", "#3"],
            "SKU": ["A", "B", "B", "A"],
            "Quantity": [4, 3, 1, 1],
            "Tags": ["VIP, repeat", "", "", "VIP"],
            "Order_Fulfillment_Status": ["Fulfillable"] * 4,
            "Internal_Tags": ["[]"] * 4,
            "Status_Note": [""] * 4,
        }
    )


def rules():
    """Three article rules and one order rule: uids 1 to 4, in that order."""
    return [
        rule("VIP priority", conditions=[cond("Tags", "contains", "VIP")], actions=[tag("priority")]),
        rule("Second"),
        rule("Third", enabled=False),
        rule("Heavy parcels", "order", conditions=[cond("total_quantity", "is greater than", "5")]),
    ]


def draft(given=None, analysis=True):
    return RulesDraft(rules() if given is None else given, frame() if analysis else None, TAGS)


@pytest.fixture
def page(qtbot):
    view = QWebEngineView()
    qtbot.addWidget(view)
    bridge = mount_settings_page(view)
    view.resize(868, 700)
    view.show()
    _until_js(qtbot, view, "document.documentElement.dataset.bridge === 'ready'")
    return view, bridge


def _wired(qtbot, view, bridge, d):
    """Show `d` and answer the page's edits the way the host does."""
    seen = []

    def on_edit(action, args):
        seen.append((action, args))
        if d.apply(action, args):
            bridge.set_state(d.view())

    bridge.editRequested.connect(on_edit)
    _show(qtbot, view, bridge, d)
    return seen


def _sent(qtbot, seen, action, args):
    qtbot.waitUntil(lambda: (action, args) in seen, timeout=5000)


def _there(qtbot, view, selector):
    _until_js(qtbot, view, f"document.querySelector({selector!r}) !== null")


def _gone(qtbot, view, selector):
    _until_js(qtbot, view, f"document.querySelector({selector!r}) === null")


def _focused(qtbot, view, key):
    _until_js(qtbot, view, f"(document.activeElement.dataset.key || '') === {key!r}")


def _open(qtbot, view, uid):
    _click(qtbot, view, _key(f"rule-{uid}-name"))
    _there(qtbot, view, f'.rule.open[data-rule="{uid}"] .rule-editor')


def _pointer(qtbot, view, kind, target, y):
    _eval(
        qtbot,
        view,
        f"{target}.dispatchEvent(new PointerEvent({kind!r}, {{bubbles: true, cancelable: true,"
        f" button: 0, pointerId: 7, clientX: 30, clientY: {y}}})); true",
    )


def _row_edge(qtbot, view, uid, edge):
    return _eval(
        qtbot, view, f"document.querySelector('.rule[data-rule=\"{uid}\"]').getBoundingClientRect().{edge}"
    )


# --- the files ---------------------------------------------------------------


def test_the_rules_script_loads_before_the_page_script():
    html = PAGE.read_text(encoding="utf-8")
    assert html.index('src="settings_rules.js"') < html.index('src="settings.js"')


# --- the head and the empty state ----------------------------------------------


def test_the_head_offers_add_rule(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, draft())
    assert _text(qtbot, view, ".page-title") == "Rules"
    assert _text(qtbot, view, ".page-sub") == (
        "Change orders at the end of each analysis. Rules run top to bottom."
    )
    assert _text(qtbot, view, _key("rule-add")) == "Add rule"

    _click(qtbot, view, _key("rule-add"))
    _sent(qtbot, seen, "rule_add", [])
    _there(qtbot, view, ".rule.open .rule-name-field")
    _focused(qtbot, view, "rule-5-name")
    assert _prop(qtbot, view, ".rule.open .rule-name-field", "value") == "New rule"
    # Selected, so typing replaces the placeholder name.
    assert _eval(qtbot, view, "document.activeElement.selectionEnd") == len("New rule")
    assert _eval(qtbot, view, "document.activeElement.selectionStart") == 0


def test_no_rules_shows_the_empty_state_and_its_own_button(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, draft([]))
    assert _count(qtbot, view, ".page-head [data-act]") == 0
    assert _count(qtbot, view, ".rules-card") == 0
    assert _text(qtbot, view, ".rules-empty .state-title") == "No rules yet"
    assert _text(qtbot, view, ".rules-empty .state-text") == (
        "Rules change orders at the end of each analysis, e.g. tag VIP orders."
    )
    assert _count(qtbot, view, ".rules-empty-tile svg") == 1
    assert _text(qtbot, view, ".rules-empty .btn.primary") == "Add rule"

    _click(qtbot, view, ".rules-empty .btn.primary")
    _sent(qtbot, seen, "rule_add", [])
    _there(qtbot, view, ".rules-card .rule.open")


# --- the list --------------------------------------------------------------------


def test_a_row_is_the_mockups_grid(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, draft())
    columns = _style(qtbot, view, ".rule", "gridTemplateColumns").split()
    assert columns[:2] == ["20px", "32px"] and len(columns) == 4
    theme = get_theme_manager().get_current_theme()
    assert _style(qtbot, view, ".rule", "borderTopColor") == _rgb(theme.border_subtle)
    assert _texts(qtbot, view, ".rule-num") == ["01", "02", "03", "04"]
    assert _texts(qtbot, view, ".rule-name") == ["VIP priority", "Second", "Third", "Heavy parcels"]
    assert _text(qtbot, view, ".rules-count") == "4 rules · 3 on"


def test_a_summary_reads_when_and_then_with_its_values_as_chips(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, draft())
    first = '.rule[data-rule="1"]'
    assert _texts(qtbot, view, f"{first} .rule-line-label") == ["When", "Then"]
    assert _texts(qtbot, view, f"{first} .rule-line:nth-of-type(2) > :not(.rule-line-label)") == [
        "Tags",
        "contains",
        "VIP",
    ]
    assert _texts(qtbot, view, f"{first} .rule-chip") == ["VIP", "priority"]
    theme = get_theme_manager().get_current_theme()
    assert _style(qtbot, view, f"{first} .rule-chip", "backgroundColor") == _rgb(theme.surface_raised)
    assert _style(qtbot, view, f"{first} .rule-word.bold", "fontWeight") == "700"
    assert _style(qtbot, view, f"{first} .rule-line-label", "width") == "36px"


def test_a_rule_with_steps_has_wider_labels(qtbot, page):
    view, bridge = page
    stepped = rule("Stepped")
    stepped["steps"].append({"conditions": [cond("Quantity", "is greater than", "2")], "match": "ALL", "actions": []})
    _show(qtbot, view, bridge, draft([stepped]))
    assert _texts(qtbot, view, ".rule-line-label") == ["When", "Then", "And when", "Then"]
    assert _style(qtbot, view, ".rule-line-label", "width") == "60px"
    assert _texts(qtbot, view, ".rule-word.muted") == ["No action yet."]


def test_the_two_levels_are_labelled_groups(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, draft())
    assert _texts(qtbot, view, ".rules-group-label") == ["Article rules", "Order rules"]
    assert _texts(qtbot, view, ".rules-group") == [
        "Article rulesCheck one order line at a time.",
        "Order rulesCheck the whole order. Run after every article rule.",
    ]
    assert json.loads(
        _eval(
            qtbot,
            view,
            "JSON.stringify(Array.from(document.querySelectorAll('.rule')).map((r) => r.dataset.group))",
        )
    ) == ["article", "article", "article", "order"]


def test_a_very_long_value_is_cut_and_never_widens_the_page(qtbot, page):
    view, bridge = page
    skus = ", ".join(f"SKU-{n:04d}" for n in range(60))
    _wired(qtbot, view, bridge, draft([rule("long", conditions=[cond("SKU", "in list", skus)])]))
    fits = (
        "(() => { const s = document.getElementById('settings');"
        " return s.scrollWidth <= s.clientWidth; })()"
    )
    assert _attr(qtbot, view, ".rule-chip", "title") == skus
    assert _eval(
        qtbot,
        view,
        "(() => { const c = document.querySelector('.rule-chip');"
        " return c.scrollWidth > c.clientWidth; })()",
    ) is True
    assert _eval(qtbot, view, fits) is True
    _open(qtbot, view, "1")
    assert _prop(qtbot, view, _key("rule-1-s0-c0-value"), "value") == skus
    assert _eval(qtbot, view, fits) is True


def test_markup_in_a_name_or_a_value_is_drawn_as_text(qtbot, page):
    view, bridge = page
    name = '<b>"VIP" & co</b>'
    value = '<i>"x"</i>'
    given = rule(name, conditions=[cond("SKU", "equals", value)], actions=[tag('say "hi"')])
    seen = _wired(qtbot, view, bridge, draft([given]))
    assert _text(qtbot, view, ".rule-name") == name
    assert _count(qtbot, view, ".rule b, .rule i") == 0
    assert _texts(qtbot, view, ".rule-chip") == [value, 'say "hi"']
    assert _attr(qtbot, view, ".switch", "aria-label") == name

    _open(qtbot, view, "1")
    assert _prop(qtbot, view, _key("rule-1-name"), "value") == name
    assert _prop(qtbot, view, _key("rule-1-s0-c0-value"), "value") == value
    assert _prop(qtbot, view, _key("rule-1-s0-a0-value"), "value") == 'say "hi"'
    _type(qtbot, view, _key("rule-1-name"), name + "!")
    _sent(qtbot, seen, "rule_name", ["1", name + "!"])


def test_one_level_has_no_group_label(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, draft([rule("a"), rule("b")]))
    assert _count(qtbot, view, ".rules-group") == 0


def test_a_rule_that_is_off_reads_quieter_and_says_off(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, draft())
    theme = get_theme_manager().get_current_theme()
    off = '.rule[data-rule="3"]'
    assert _text(qtbot, view, f"{off} .badge") == "Off"
    assert _attr(qtbot, view, f"{off} .switch", "aria-checked") == "false"
    assert _attr(qtbot, view, f"{off} .switch", "title") == "Turn on"
    assert _style(qtbot, view, f"{off} .rule-name", "color") == _rgb(theme.text_secondary)
    assert _style(qtbot, view, f"{off} .rule-line", "color") == _rgb(theme.text_secondary)
    on = '.rule[data-rule="1"]'
    assert _count(qtbot, view, f"{on} .badge") == 0
    assert _style(qtbot, view, f"{on} .rule-name", "color") == _rgb(theme.text)


def test_the_switch_turns_a_rule_off_and_on(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, draft())
    _click(qtbot, view, _key("rule-1-switch"))
    _sent(qtbot, seen, "rule_enabled", ["1", False])
    _there(qtbot, view, '.rule.off[data-rule="1"]')
    assert _text(qtbot, view, ".rules-count") == "4 rules · 2 on"
    _click(qtbot, view, _key("rule-1-switch"))
    _sent(qtbot, seen, "rule_enabled", ["1", True])


def test_a_rule_with_no_name_is_still_a_row_to_click(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, draft([rule("")]))
    assert _text(qtbot, view, ".rule-name") == "Unnamed rule"
    assert _attr(qtbot, view, ".switch", "aria-label") == "Unnamed rule"


def test_the_filter_narrows_the_list_and_stops_reordering(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, draft())
    assert _attr(qtbot, view, _key("rules-filter"), "placeholder") == "Filter by name"
    _type(qtbot, view, _key("rules-filter"), "sec")
    _sent(qtbot, seen, "filter", ["sec"])
    _until_js(qtbot, view, "document.querySelectorAll('.rule').length === 1")
    assert _texts(qtbot, view, ".rule-num") == ["02"]
    assert _active(qtbot, view) == "rules-filter"
    assert _prop(qtbot, view, _key("rules-filter"), "value") == "sec"
    assert _prop(qtbot, view, _key("rule-2-up"), "disabled") is True
    assert _attr(qtbot, view, _key("rule-2-up"), "title") == CLEAR_FILTER
    assert _attr(qtbot, view, ".rule-grip", "title") == CLEAR_FILTER

    _type(qtbot, view, _key("rules-filter"), "zzz")
    _there(qtbot, view, ".rules-none")
    assert _text(qtbot, view, ".rules-none") == "No rules named “zzz”."


def test_up_and_down_move_a_rule_inside_its_group_and_keep_the_focus_on_it(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, draft())
    assert _prop(qtbot, view, _key("rule-1-up"), "disabled") is True
    assert _prop(qtbot, view, _key("rule-3-down"), "disabled") is True
    assert _prop(qtbot, view, _key("rule-4-up"), "disabled") is True
    assert _prop(qtbot, view, _key("rule-4-down"), "disabled") is True
    assert _attr(qtbot, view, _key("rule-2-up"), "title") == "Move up"
    assert _attr(qtbot, view, _key("rule-2-down"), "title") == "Move down"

    _eval(qtbot, view, f"document.querySelector({_key('rule-2-down')!r}).focus(); true")
    _click(qtbot, view, _key("rule-2-down"))
    _sent(qtbot, seen, "rule_move", ["2", "down"])
    _until_js(
        qtbot, view, "document.querySelectorAll('.rule')[2].dataset.rule === '2'"
    )
    # It reached the group's end: Down is disabled, so Up takes the focus.
    _focused(qtbot, view, "rule-2-up")


def test_a_move_button_at_the_edge_only_greys(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, draft())
    theme = get_theme_manager().get_current_theme()
    edge = _key("rule-1-up")
    assert _style(qtbot, view, edge, "color") == _rgb(theme.text_disabled)
    assert _style(qtbot, view, edge, "borderTopColor") == "rgba(0, 0, 0, 0)"
    assert _style(qtbot, view, edge, "backgroundColor") == "rgba(0, 0, 0, 0)"
    assert _style(qtbot, view, _key("rule-2-up"), "color") == _rgb(theme.text_secondary)


def test_the_more_menu_edits_duplicates_and_deletes(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, draft())
    more = _key("rule-2-menu")
    assert _attr(qtbot, view, more, "title") == "Edit, duplicate, delete"
    _click(qtbot, view, more)
    assert _attr(qtbot, view, more, "aria-expanded") == "true"
    assert _texts(qtbot, view, ".rule-menu .menu-item") == ["Edit", "Duplicate", "Delete"]
    theme = get_theme_manager().get_current_theme()
    assert _style(qtbot, view, _key("rule-2-menu-delete"), "color") == _rgb(theme.status_danger)

    _click(qtbot, view, _key("rule-2-menu-duplicate"))
    _sent(qtbot, seen, "rule_duplicate", ["2"])
    _until_js(qtbot, view, "document.querySelectorAll('.rule').length === 5")
    assert _count(qtbot, view, ".rule-menu") == 0
    assert _texts(qtbot, view, ".rule-name")[1:3] == ["Second", "Second copy"]

    _click(qtbot, view, more)
    _click(qtbot, view, _key("rule-2-menu-delete"))
    _sent(qtbot, seen, "rule_delete", ["2"])
    _gone(qtbot, view, '.rule[data-rule="2"]')
    _focused(qtbot, view, "rules-filter")

    _click(qtbot, view, _key("rule-1-menu"))
    _click(qtbot, view, _key("rule-1-menu-edit"))
    _sent(qtbot, seen, "open", ["1"])
    _there(qtbot, view, '.rule.open[data-rule="1"]')
    assert _count(qtbot, view, ".rule-menu") == 0
    _click(qtbot, view, _key("rule-1-menu"))
    assert _texts(qtbot, view, ".rule-menu .menu-item")[0] == "Close editor"
    _click(qtbot, view, _key("rule-1-menu-edit"))
    _sent(qtbot, seen, "close", [])
    _gone(qtbot, view, ".rule.open")


def test_escape_closes_the_more_menu_and_returns_focus(qtbot, page):
    view, bridge = page
    _wired(qtbot, view, bridge, draft())
    _click(qtbot, view, _key("rule-1-menu"))
    _there(qtbot, view, ".rule-menu")
    _keydown(qtbot, view, "Escape")
    _gone(qtbot, view, ".rule-menu")
    assert _active(qtbot, view) == "rule-1-menu"


# --- reordering by the grip --------------------------------------------------------


def test_dragging_a_grip_shows_where_the_rule_lands_and_moves_it_there(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, draft())
    grip = "document.querySelector('[data-grip=\"1\"]')"
    assert _attr(qtbot, view, '[data-grip="1"]', "title") == "Drag to reorder"

    _pointer(qtbot, view, "pointerdown", grip, _row_edge(qtbot, view, "1", "top") + 5)
    assert _count(qtbot, view, '.rule.dragging[data-rule="1"]') == 1
    theme = get_theme_manager().get_current_theme()
    assert _style(qtbot, view, ".rule.dragging", "backgroundColor") == _rgb(theme.selection_bg)

    # Just under the second rule's middle: it lands between the second and third.
    _pointer(qtbot, view, "pointermove", "document", _row_edge(qtbot, view, "2", "bottom") - 3)
    assert _count(qtbot, view, '.rule.drop-before[data-rule="3"]') == 1
    # Under the group's last rule: it lands at the end, never among the order rules.
    _pointer(qtbot, view, "pointermove", "document", _row_edge(qtbot, view, "4", "bottom") - 3)
    assert _count(qtbot, view, '.rule.drop-after[data-rule="3"]') == 1
    assert _count(qtbot, view, ".rule.drop-before") == 0

    _pointer(qtbot, view, "pointerup", "document", 0)
    _sent(qtbot, seen, "rule_move_to", ["1", "2"])
    _until_js(qtbot, view, "document.querySelectorAll('.rule')[2].dataset.rule === '1'")
    assert _count(qtbot, view, ".rule.dragging, .rule.drop-after, .rule.drop-before") == 0
    assert _eval(qtbot, view, "document.body.classList.contains('is-dragging')") is False


def test_a_drag_dropped_where_it_started_or_escaped_moves_nothing(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, draft())
    grip = "document.querySelector('[data-grip=\"2\"]')"
    middle = _row_edge(qtbot, view, "2", "top") + 5

    _pointer(qtbot, view, "pointerdown", grip, middle)
    _pointer(qtbot, view, "pointermove", "document", middle)
    assert _count(qtbot, view, ".rule.drop-before, .rule.drop-after") == 0
    _pointer(qtbot, view, "pointerup", "document", middle)

    _pointer(qtbot, view, "pointerdown", grip, middle)
    _pointer(qtbot, view, "pointermove", "document", _row_edge(qtbot, view, "1", "top") + 2)
    assert _count(qtbot, view, '.rule.drop-before[data-rule="1"]') == 1
    _keydown(qtbot, view, "Escape")
    assert _count(qtbot, view, ".rule.dragging, .rule.drop-before") == 0
    _pointer(qtbot, view, "pointerup", "document", 0)

    qtbot.wait(150)
    assert not [edit for edit in seen if edit[0].startswith("rule_move")]


def test_a_grip_that_cannot_drag_starts_nothing(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, draft())
    # The one order rule has nowhere to go.
    _pointer(qtbot, view, "pointerdown", "document.querySelector('[data-grip=\"4\"]')", 400)
    assert _count(qtbot, view, ".rule.dragging") == 0
    _pointer(qtbot, view, "pointerup", "document", 0)
    qtbot.wait(100)
    assert not [edit for edit in seen if edit[0].startswith("rule_move")]


# --- opening a rule ------------------------------------------------------------------


def test_clicking_a_name_opens_the_editor_in_the_row(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, draft())
    _click(qtbot, view, _key("rule-1-name"))
    _sent(qtbot, seen, "open", ["1"])
    row = '.rule.open[data-rule="1"]'
    _there(qtbot, view, f"{row} .rule-editor")
    _focused(qtbot, view, "rule-1-name")
    assert _prop(qtbot, view, f"{row} .rule-name-field", "value") == "VIP priority"
    assert _count(qtbot, view, f"{row} .rule-line") == 0
    assert _style(qtbot, view, f"{row} .rule-editor", "gridColumnStart") == "3"
    assert _texts(qtbot, view, f"{row} .editor-label") == ["Level", "When", "Then"]
    assert _count(qtbot, view, ".rule.open") == 1

    _click(qtbot, view, _key("rule-2-name"))
    _there(qtbot, view, '.rule.open[data-rule="2"]')
    assert _count(qtbot, view, ".rule.open") == 1

    _click(qtbot, view, _key("rule-2-done"))
    _sent(qtbot, seen, "close", [])
    _gone(qtbot, view, ".rule.open")
    _focused(qtbot, view, "rule-2-name")


def test_typing_a_name_reports_every_keystroke_and_keeps_the_caret(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, draft())
    _open(qtbot, view, "1")
    _type(qtbot, view, _key("rule-1-name"), "VIP first")
    _sent(qtbot, seen, "rule_name", ["1", "VIP first"])
    qtbot.wait(100)
    assert _active(qtbot, view) == "rule-1-name"
    assert _prop(qtbot, view, _key("rule-1-name"), "value") == "VIP first"


def test_the_level_is_two_segments_with_what_each_means(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, draft())
    _open(qtbot, view, "1")
    assert _texts(qtbot, view, ".level-line .segment") == ["Article", "Order"]
    assert _attr(qtbot, view, _key("rule-1-level-article"), "aria-checked") == "true"
    assert _text(qtbot, view, ".level-line .hint") == "Checks one order line at a time."

    _click(qtbot, view, _key("rule-1-level-order"))
    _sent(qtbot, seen, "rule_level", ["1", "order"])
    _until_js(qtbot, view, "document.querySelector('.rule.open').dataset.group === 'order'")
    assert _text(qtbot, view, ".level-line .hint") == (
        "Checks the whole order. Runs after every article rule."
    )
    _focused(qtbot, view, "rule-1-level-order")


# --- conditions ------------------------------------------------------------------------


def test_a_condition_row_is_a_field_an_operator_and_a_value(qtbot, page):
    view, bridge = page
    _wired(qtbot, view, bridge, draft())
    _open(qtbot, view, "1")
    assert _text(qtbot, view, _key("rule-1-s0-c0-field")) == "Tags"
    assert _text(qtbot, view, _key("rule-1-s0-c0-op")) == "contains"
    assert _prop(qtbot, view, _key("rule-1-s0-c0-value"), "value") == "VIP"
    assert _attr(qtbot, view, _key("rule-1-s0-c0-value"), "placeholder") == "Value"
    assert _attr(qtbot, view, _key("rule-1-s0-c0-remove"), "title") == "Remove condition"
    assert _count(qtbot, view, ".match-line") == 0
    columns = _style(qtbot, view, ".cond-row", "gridTemplateColumns").split()
    assert columns[1] == "180px" and columns[3] == "28px"


def test_the_field_menu_is_grouped_and_picking_reports_the_field(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, draft())
    _open(qtbot, view, "4")
    field = _key("rule-4-s0-c0-field")
    _click(qtbot, view, field)
    assert _texts(qtbot, view, ".editor-menu .menu-group") == [
        "Order fields",
        "Common fields",
        "Other fields in this analysis",
    ]
    assert _text(qtbot, view, '.editor-menu .menu-item[aria-checked="true"]') == "total_quantity"

    _eval(
        qtbot,
        view,
        "Array.from(document.querySelectorAll('.editor-menu .menu-item'))"
        ".find((el) => el.dataset.value === 'item_count').click(); true",
    )
    _sent(qtbot, seen, "cond_field", ["4", "0", "0", "item_count"])
    _until_js(qtbot, view, f"document.querySelector({field!r}).textContent.trim() === 'item_count'")
    assert _count(qtbot, view, ".editor-menu") == 0
    assert _active(qtbot, view) == "rule-4-s0-c0-field"


def test_a_field_the_level_does_not_offer_is_kept_listed_first_and_marked(qtbot, page):
    view, bridge = page
    _wired(qtbot, view, bridge, draft([rule("r", conditions=[cond("item_count", "equals", "2")])]))
    _open(qtbot, view, "1")
    field = _key("rule-1-s0-c0-field")
    assert _text(qtbot, view, field) == "item_count"
    assert "invalid" in _attr(qtbot, view, field, "class")
    assert _text(qtbot, view, ".cond .problem") == (
        "“item_count” is not a field an article rule can read, so this condition never matches."
    )
    _click(qtbot, view, field)
    assert _text(qtbot, view, ".editor-menu .menu-item") == "item_countNot available"


def test_the_operator_decides_the_value_control(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, draft())
    _open(qtbot, view, "2")
    value = _key("rule-2-s0-c0-value")
    # equals on a column of the analysis: its values are suggested.
    assert _attr(qtbot, view, value, "type") == "text"
    assert _attr(qtbot, view, value, "list") == "dl-rule-2-s0-c0"
    assert json.loads(
        _eval(
            qtbot,
            view,
            "JSON.stringify(Array.from(document.querySelectorAll('#dl-rule-2-s0-c0 option')).map((o) => o.value))",
        )
    ) == ["A", "B"]

    def pick(operator):
        _click(qtbot, view, _key("rule-2-s0-c0-op"))
        _eval(
            qtbot,
            view,
            "Array.from(document.querySelectorAll('.editor-menu .menu-item'))"
            f".find((el) => el.dataset.value === {operator!r}).click(); true",
        )
        _sent(qtbot, seen, "cond_operator", ["2", "0", "0", operator])

    pick("date before")
    _until_js(qtbot, view, f"document.querySelector({value!r}).type === 'date'")
    pick("is empty")
    _gone(qtbot, view, value)
    assert _count(qtbot, view, ".cond-none") == 1
    pick("in list")
    _there(qtbot, view, value)
    assert _attr(qtbot, view, value, "placeholder") == "Value1, Value2, Value3"
    assert _eval(qtbot, view, f"document.querySelector({value!r}).hasAttribute('list')") is False


def test_typing_a_value_reports_every_keystroke_and_keeps_the_caret(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, draft())
    _open(qtbot, view, "1")
    value = _key("rule-1-s0-c0-value")
    _type(qtbot, view, value, "VIPs")
    _sent(qtbot, seen, "cond_value", ["1", "0", "0", "VIPs"])
    qtbot.wait(100)
    assert _active(qtbot, view) == "rule-1-s0-c0-value"
    assert _prop(qtbot, view, value, "value") == "VIPs"


def test_a_value_save_refuses_is_marked_under_its_row_and_on_the_closed_row(qtbot, page):
    view, bridge = page
    bad = rule("sizes", conditions=[cond("SKU", "matches regex", "(")])
    _wired(qtbot, view, bridge, draft([bad]))
    theme = get_theme_manager().get_current_theme()
    assert _text(qtbot, view, ".rule .problem") == "Condition 1: Invalid regex syntax"
    assert _style(qtbot, view, ".rule .problem", "color") == _rgb(theme.status_danger)

    _open(qtbot, view, "1")
    value = _key("rule-1-s0-c0-value")
    assert "invalid" in _attr(qtbot, view, value, "class")
    assert _style(qtbot, view, value, "borderTopColor") == _rgb(theme.status_danger)
    assert _text(qtbot, view, ".cond .problem") == "Invalid regex syntax"
    assert _prop(qtbot, view, _key("rule-1-test"), "disabled") is True
    assert _attr(qtbot, view, _key("rule-1-test"), "title") == "Fix the marked value first."


def test_a_list_says_how_many_items_under_its_row(qtbot, page):
    view, bridge = page
    _wired(qtbot, view, bridge, draft([rule("r", conditions=[cond("SKU", "in list", "A, B")])]))
    _open(qtbot, view, "1")
    assert _text(qtbot, view, ".cond .hint") == "2 items"
    assert _count(qtbot, view, ".cond .problem") == 0


def test_adding_and_removing_a_condition_moves_the_focus_with_it(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, draft())
    _open(qtbot, view, "1")
    add = _key("rule-1-s0-cond-add")
    assert _text(qtbot, view, add) == "Add condition"
    _click(qtbot, view, add)
    _sent(qtbot, seen, "cond_add", ["1", "0"])
    _there(qtbot, view, _key("rule-1-s0-c1-field"))
    _focused(qtbot, view, "rule-1-s0-c1-field")
    assert _text(qtbot, view, _key("rule-1-s0-c1-field")) == "Order_Number"

    # Two conditions: how they combine is now a choice.
    assert _texts(qtbot, view, ".match-line .segment") == ["All", "Any"]
    assert _text(qtbot, view, ".match-line > span") == "of these match"
    _click(qtbot, view, _key("rule-1-s0-match-ANY"))
    _sent(qtbot, seen, "step_match", ["1", "0", "ANY"])
    _until_js(
        qtbot,
        view,
        f"document.querySelector({_key('rule-1-s0-match-ANY')!r}).getAttribute('aria-checked') === 'true'",
    )

    _click(qtbot, view, _key("rule-1-s0-c1-remove"))
    _sent(qtbot, seen, "cond_remove", ["1", "0", "1"])
    _gone(qtbot, view, _key("rule-1-s0-c1-field"))
    _focused(qtbot, view, "rule-1-s0-cond-add")
    assert _count(qtbot, view, ".match-line") == 0


# --- actions -----------------------------------------------------------------------------


def test_an_action_row_names_its_type_in_words_and_suggests_the_tags(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, draft())
    _open(qtbot, view, "1")
    assert _text(qtbot, view, _key("rule-1-s0-a0-type")) == "Add internal tag"
    value = _key("rule-1-s0-a0-value")
    assert _prop(qtbot, view, value, "value") == "priority"
    assert _attr(qtbot, view, value, "placeholder") == "Tag"
    assert json.loads(
        _eval(
            qtbot,
            view,
            "JSON.stringify(Array.from(document.querySelectorAll('#dl-rule-1-s0-a0-value option')).map((o) => o.value))",
        )
    ) == ["heavy", "priority"]
    assert _attr(qtbot, view, _key("rule-1-s0-a0-remove"), "title") == "Remove action"

    _type(qtbot, view, value, "urgent")
    _sent(qtbot, seen, "action_param", ["1", "0", "0", "value", "urgent"])
    qtbot.wait(100)
    assert _active(qtbot, view) == "rule-1-s0-a0-value"


def test_the_type_menu_offers_the_seven_and_changing_type_redraws_the_row(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, draft())
    _open(qtbot, view, "1")
    kind = _key("rule-1-s0-a0-type")
    _click(qtbot, view, kind)
    assert _texts(qtbot, view, ".editor-menu .menu-item") == [
        "Add internal tag",
        "Remove internal tag",
        "Hold the order",
        "Copy field",
        "Calculate",
        "Log an alert",
        "Add bonus line",
    ]
    _eval(
        qtbot,
        view,
        "Array.from(document.querySelectorAll('.editor-menu .menu-item'))"
        ".find((el) => el.dataset.value === 'CALCULATE').click(); true",
    )
    _sent(qtbot, seen, "action_type", ["1", "0", "0", "CALCULATE"])
    _there(qtbot, view, _key("rule-1-s0-a0-target"))
    assert _text(qtbot, view, kind) == "Calculate"
    assert _text(qtbot, view, _key("rule-1-s0-a0-field1")) == "Order_Number"
    assert _text(qtbot, view, _key("rule-1-s0-a0-operation")) == "plus"
    assert _text(qtbot, view, _key("rule-1-s0-a0-field2")) == "Order_Number"
    assert _attr(qtbot, view, _key("rule-1-s0-a0-target"), "placeholder") == "Result column"
    assert _texts(qtbot, view, ".action .param-lead") == ["→"]

    _click(qtbot, view, _key("rule-1-s0-a0-operation"))
    assert _texts(qtbot, view, ".editor-menu .menu-item") == ["plus", "minus", "times", "divided by"]
    _eval(
        qtbot,
        view,
        "Array.from(document.querySelectorAll('.editor-menu .menu-item'))"
        ".find((el) => el.dataset.value === 'multiply').click(); true",
    )
    _sent(qtbot, seen, "action_param", ["1", "0", "0", "operation", "multiply"])
    _until_js(
        qtbot,
        view,
        f"document.querySelector({_key('rule-1-s0-a0-operation')!r}).textContent.trim() === 'times'",
    )

    _click(qtbot, view, _key("rule-1-s0-a0-field1"))
    _eval(
        qtbot,
        view,
        "Array.from(document.querySelectorAll('.editor-menu .menu-item'))"
        ".find((el) => el.dataset.value === 'Quantity').click(); true",
    )
    _sent(qtbot, seen, "action_param", ["1", "0", "0", "field1", "Quantity"])


def test_a_bad_quantity_is_marked(qtbot, page):
    view, bridge = page
    bonus = rule("bonus", actions=[{"type": "ADD_PRODUCT", "sku": "GIFT", "quantity": 1}])
    seen = _wired(qtbot, view, bridge, draft([bonus]))
    _open(qtbot, view, "1")
    quantity = _key("rule-1-s0-a0-quantity")
    assert _text(qtbot, view, _key("rule-1-s0-a0-type")) == "Add bonus line"
    assert _prop(qtbot, view, quantity, "value") == "1"
    assert _texts(qtbot, view, ".action .param-lead") == ["×"]
    _type(qtbot, view, quantity, "lots")
    _sent(qtbot, seen, "action_param", ["1", "0", "0", "quantity", "lots"])
    _there(qtbot, view, ".action .problem")
    assert _text(qtbot, view, ".action .problem") == "Type a whole number from 1 to 9999."
    assert "invalid" in _attr(qtbot, view, quantity, "class")
    assert _active(qtbot, view) == "rule-1-s0-a0-quantity"


def test_the_hold_and_a_retired_action_explain_themselves(qtbot, page):
    view, bridge = page
    actions = [{"type": "SET_STATUS", "value": "Not Fulfillable"}, {"type": "ADD_TAG", "value": "hold"}]
    _wired(qtbot, view, bridge, draft([rule("r", actions=actions)]))
    _open(qtbot, view, "1")
    assert _text(qtbot, view, _key("rule-1-s0-a0-type")) == "Hold the order"
    assert _text(qtbot, view, _key("rule-1-s0-a1-type")) == "Add status note (retired)"
    assert _texts(qtbot, view, ".action .hint") == [HOLD_HINT, RETIRED_ONE]
    _click(qtbot, view, _key("rule-1-s0-a1-type"))
    # The retired type is offered on the row that holds it, and only there.
    assert _texts(qtbot, view, ".editor-menu .menu-item")[0] == "Add status note (retired)"
    assert _count(qtbot, view, ".editor-menu .menu-item") == 8
    _keydown(qtbot, view, "Escape")
    _click(qtbot, view, _key("rule-1-s0-a0-type"))
    assert _count(qtbot, view, ".editor-menu .menu-item") == 7


def test_adding_and_removing_an_action_moves_the_focus_with_it(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, draft())
    _open(qtbot, view, "1")
    _click(qtbot, view, _key("rule-1-s0-action-add"))
    _sent(qtbot, seen, "action_add", ["1", "0"])
    _focused(qtbot, view, "rule-1-s0-a1-type")
    assert _prop(qtbot, view, _key("rule-1-s0-a1-value"), "value") == ""
    _click(qtbot, view, _key("rule-1-s0-a1-remove"))
    _sent(qtbot, seen, "action_remove", ["1", "0", "1"])
    _focused(qtbot, view, "rule-1-s0-action-add")


# --- steps ---------------------------------------------------------------------------------


def test_a_second_step_gives_every_step_a_heading(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, draft())
    _open(qtbot, view, "1")
    assert _count(qtbot, view, ".step-head") == 0
    _click(qtbot, view, _key("rule-1-step-add"))
    _sent(qtbot, seen, "step_add", ["1"])
    _until_js(qtbot, view, "document.querySelectorAll('.step-head').length === 2")
    assert _texts(qtbot, view, ".step-title") == ["Step 1", "Step 2"]
    assert _texts(qtbot, view, ".step-note") == ["", "Checks only the lines step 1 matched."]
    assert _count(qtbot, view, _key("rule-1-s0-remove")) == 0
    assert _text(qtbot, view, _key("rule-1-s1-remove")) == "Remove step"

    _click(qtbot, view, _key("rule-1-s1-remove"))
    _sent(qtbot, seen, "step_remove", ["1", "1"])
    _until_js(qtbot, view, "document.querySelectorAll('.step-head').length === 0")
    _focused(qtbot, view, "rule-1-step-add")


# --- Test... ----------------------------------------------------------------------------------


def test_test_asks_the_bridge_for_that_rule(qtbot, page):
    view, bridge = page
    asked = []
    bridge.testRequested.connect(asked.append)
    _show(qtbot, view, bridge, draft())
    assert _text(qtbot, view, _key("rule-2-test")) == "Test…"
    assert _attr(qtbot, view, _key("rule-2-test"), "title") == ""
    _click(qtbot, view, _key("rule-2-test"))
    qtbot.waitUntil(lambda: asked == ["2"])


def test_with_no_analysis_test_is_disabled_and_says_why(qtbot, page):
    view, bridge = page
    asked = []
    bridge.testRequested.connect(asked.append)
    _show(qtbot, view, bridge, draft(analysis=False))
    assert _prop(qtbot, view, _key("rule-1-test"), "disabled") is True
    assert _attr(qtbot, view, _key("rule-1-test"), "title") == TEST_NO_ANALYSIS
    _click(qtbot, view, _key("rule-1-test"))
    qtbot.wait(100)
    assert asked == []


def _with_test(d, test):
    return {**d.view(), "test": {"uid": "1", **test}}


def _push(qtbot, view, bridge, state):
    before = _eval(qtbot, view, "Number(document.documentElement.dataset.renders || 0)")
    bridge.set_state(state)
    _until_js(qtbot, view, f"Number(document.documentElement.dataset.renders) > {before}")


def test_the_panel_says_it_is_running_and_takes_the_page_over(qtbot, page):
    view, bridge = page
    d = draft()
    _show(qtbot, view, bridge, d)
    _push(qtbot, view, bridge, _with_test(d, running_view(d.test_config("1"), frame(), "2026-09-30_1")))
    assert _attr(qtbot, view, ".scrim", "data-test") == "running"
    assert _text(qtbot, view, ".test-title") == "Test “VIP priority”"
    assert _text(qtbot, view, ".test-intro") == (
        "Runs this rule, as edited, against the analysis in 2026-09-30_1. Orders aren’t changed."
    )
    assert _text(qtbot, view, ".test-intro .mono") == "2026-09-30_1"
    assert _text(qtbot, view, ".test-message") == "Testing 3 orders…"
    assert _count(qtbot, view, ".test-table") == 0
    assert _prop(qtbot, view, ".settings-page", "inert") is True
    assert _attr(qtbot, view, ".test-panel", "role") == "dialog"
    _focused(qtbot, view, "test-close")
    assert _style(qtbot, view, ".scrim", "backgroundColor") == "rgba(0, 0, 0, 0.35)"
    assert _style(qtbot, view, ".scrim", "position") == "fixed"
    assert _style(qtbot, view, ".test-panel", "width") == "580px"


def test_the_panel_counts_orders_and_lists_them(qtbot, page):
    view, bridge = page
    d = draft()
    _show(qtbot, view, bridge, d)
    _push(qtbot, view, bridge, _with_test(d, run_rule_test(d.test_config("1"), frame(), "S1")))
    assert _attr(qtbot, view, ".scrim", "data-test") == "done"
    assert _text(qtbot, view, ".test-matched") == "2"
    assert _text(qtbot, view, ".test-count") == "2of 3 orders match"
    assert _texts(qtbot, view, ".test-row.heads span") == ["Order", "Matched on", "Change"]
    assert _texts(qtbot, view, ".test-order") == ["#1", "#3"]
    assert _texts(qtbot, view, ".test-why") == ["Tags: VIP, repeat", "Tags: VIP"]
    assert _texts(qtbot, view, ".test-change") == ["+ priority", "+ priority"]
    theme = get_theme_manager().get_current_theme()
    assert _style(qtbot, view, ".test-change", "color") == _rgb(theme.status_success)
    assert _style(qtbot, view, ".test-row.heads", "backgroundColor") == _rgb(theme.surface_raised)
    columns = _style(qtbot, view, ".test-row", "gridTemplateColumns").split()
    assert columns[0] == "90px" and columns[2] == "150px"
    assert _count(qtbot, view, ".test-more") == 0
    assert _count(qtbot, view, ".test-body .hint") == 0


def test_the_panel_says_more_no_change_and_no_match(qtbot, page):
    view, bridge = page
    d = draft()
    _show(qtbot, view, bridge, d)
    done = run_rule_test(d.test_config("1"), frame(), "S1", limit=1)
    done["rows"][0].update(change="No change", changed=False)
    done["note"] = "No change: the analysis already has the saved rules applied."
    _push(qtbot, view, bridge, _with_test(d, done))
    assert _text(qtbot, view, ".test-more") == "and 1 more"
    assert "same" in _attr(qtbot, view, ".test-change", "class")
    theme = get_theme_manager().get_current_theme()
    assert _style(qtbot, view, ".test-change", "color") == _rgb(theme.text_secondary)
    assert _text(qtbot, view, ".test-body .hint") == (
        "No change: the analysis already has the saved rules applied."
    )

    none = run_rule_test(rule("r", conditions=[cond("SKU", "equals", "Z")]), frame(), "S1")
    _push(qtbot, view, bridge, _with_test(d, none))
    assert _text(qtbot, view, ".test-matched") == "0"
    assert _text(qtbot, view, ".test-message") == "No order in this analysis matches."
    assert _count(qtbot, view, ".test-table") == 0


def test_a_failed_test_says_where_to_look(qtbot, page):
    view, bridge = page
    d = draft()
    _show(qtbot, view, bridge, d)
    _push(qtbot, view, bridge, _with_test(d, failed_view(d.test_config("1"), "S1")))
    assert _attr(qtbot, view, ".scrim", "data-test") == "failed"
    assert _text(qtbot, view, ".test-body .problem") == (
        "The rule test didn’t finish. Details are in Logs."
    )


@pytest.mark.parametrize("how", ["test-close", "test-x", "Escape"])
def test_close_the_x_and_escape_all_close_the_panel_and_focus_returns(qtbot, page, how):
    view, bridge = page
    d = draft()
    closed = []
    bridge.testClosed.connect(lambda: closed.append(True))
    _show(qtbot, view, bridge, d)
    _push(qtbot, view, bridge, _with_test(d, run_rule_test(d.test_config("1"), frame(), "S1")))
    if how == "Escape":
        _keydown(qtbot, view, "Escape")
    else:
        _click(qtbot, view, _key(how))
    qtbot.waitUntil(lambda: closed == [True])

    _push(qtbot, view, bridge, d.view())
    assert _count(qtbot, view, ".scrim") == 0
    assert _prop(qtbot, view, ".settings-page", "inert") is False
    _focused(qtbot, view, "rule-1-test")


def test_escape_with_nothing_open_is_left_for_the_dialog(qtbot, page):
    view, bridge = page
    closed = []
    bridge.testClosed.connect(lambda: closed.append(True))
    _show(qtbot, view, bridge, draft())
    prevented = _eval(
        qtbot,
        view,
        "!document.dispatchEvent(new KeyboardEvent('keydown',"
        " {key: 'Escape', bubbles: true, cancelable: true}))",
    )
    assert prevented is False
    assert closed == []


# --- the footer's link, and the theme -----------------------------------------------------------


def test_every_blocker_key_names_a_control_the_page_draws_once_revealed(qtbot, page):
    """The keys are spelled in rules_state.py and again in settings_rules.js."""
    view, bridge = page
    bad_value = rule("sizes", conditions=[cond(), cond("SKU", "matches regex", "(")])
    bad_quantity = rule("bonus", actions=[tag(), {"type": "ADD_PRODUCT", "sku": "G", "quantity": "x"}])
    for given in (bad_value, bad_quantity):
        d = draft([given])
        key = d.blocker_key()
        assert key
        assert d.apply("reveal", [key])
        _show(qtbot, view, bridge, d)
        assert _count(qtbot, view, _key(key)) == 1, key
        bridge.problemFocusRequested.emit(key)
        _focused(qtbot, view, key)


def test_the_page_follows_a_theme_change_without_a_reload(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, draft())
    manager = get_theme_manager()
    start = manager.get_current_theme().name
    other = "dark" if start == "light" else "light"
    try:
        manager.set_theme(other)
        raised = _rgb(manager.get_current_theme().surface_raised)
        _until_js(
            qtbot,
            view,
            f"getComputedStyle(document.querySelector('.rule-chip')).backgroundColor === {raised!r}",
        )
        assert _style(qtbot, view, "#settings", "colorScheme") == other
    finally:
        manager.set_theme(start)
```

- [ ] **Step 2: Run two of them and see them fail**

Do not run the whole page file yet: with no page script every test in it waits out its timeout.

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_settings_bridge.py tests/test_settings_rules_page.py::test_the_rules_script_loads_before_the_page_script`
Expected: `2 failed, 8 passed`: `test_test_rule_names_the_rule_and_close_test_says_so` (`SettingsBridge` has no `testRequested`) and `test_the_rules_script_loads_before_the_page_script` (`ValueError: substring not found`).

- [ ] **Step 3: Add the two slots to the bridge**

**Modify `gui/settings/bridge.py`.**
 Find exactly:

```python
"""The settings pages' bridge (phase 7 spec section 3.3).

Python pushes one `state` map, built by a draft's view() (gui/settings/
page_state.py); the page draws it and reports each edit through edit(). The
catalogue is the spec's section 3.3: add a member there before adding it here.

Nothing the page sends is used as a path.
"""
```

Replace with:

```python
"""The settings pages' bridge (phase 7 spec section 3.3, phase 8 spec
section 3.2).

Python pushes one `state` map, built by a draft's view() (gui/settings/
page_state.py, rules_state.py); the page draws it and reports each edit
through edit(). The catalogue is those two sections: add a member there
before adding it here.

Nothing the page sends is used as a path.
"""
```

 Find exactly:

```python
    # these, so nothing it sends can echo back into the page.
    editRequested = Signal(str, list)
    readColumnsRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
```

Replace with:

```python
    # these, so nothing it sends can echo back into the page.
    editRequested = Signal(str, list)
    readColumnsRequested = Signal()
    testRequested = Signal(str)
    testClosed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
```

 Find exactly:

```python
    def readColumns(self) -> None:
        self.readColumnsRequested.emit()


def mount_settings_page(view: QWebEngineView) -> SettingsBridge:
    """Load the settings page into `view` and return the bridge it talks to."""
```

Replace with:

```python
    def readColumns(self) -> None:
        self.readColumnsRequested.emit()

    @Slot(str)
    def testRule(self, uid) -> None:
        """Test... on the rule with this uid (phase 8 spec section 6)."""
        self.testRequested.emit(str(uid))

    @Slot()
    def closeTest(self) -> None:
        self.testClosed.emit()


def mount_settings_page(view: QWebEngineView) -> SettingsBridge:
    """Load the settings page into `view` and return the bridge it talks to."""
```

- [ ] **Step 4: Write the page script**

**Create `gui/web/settings_rules.js`:**

```javascript
// The Rules page and the Test rule panel (phase 8 spec sections 5 and 6).
// settings.js renders and routes; this file draws what bridge.state holds
// under `rules` and `test`, and turns a click or a keystroke there into
// bridge.edit(action, args). Python holds every rule and words every sentence
// (gui/settings/rules_state.py, gui/settings/rule_test.py). The page's own
// state here is a drag in progress and whether the panel was showing.
//
// Loaded before settings.js: it calls that file's helpers (esc, svg, off,
// menuItem, problemLine, focusKey, closeMenu), but only once the page runs.
"use strict";

const RULE_GLYPH = {
  search: "M18 11a7 7 0 1 1-14 0 7 7 0 0 1 14 0M20 20l-3.5-3.5",
  up: "m18 15-6-6-6 6",
  // Dots are zero-length strokes with round caps.
  more: "M5 12h.01M12 12h.01M19 12h.01",
  grip: "M9 6h.01M15 6h.01M9 12h.01M15 12h.01M9 18h.01M15 18h.01",
  rules: "M3 5h8M3 12h8M3 19h8M15 7l3 3 3-3M18 3v7M15 16h6",
};

// drag: the rule being dragged by its grip, the rows of its group, where it
// started and the place it would land. shown / uid: the Test panel as the
// last render drew it, to move focus in and back out.
const rulesView = { drag: null, shown: false, uid: null };

// --- the list ----------------------------------------------------------------

function summaryPart(part) {
  if (part.t === "chip") return `<span class="rule-chip mono" title="${esc(part.v)}">${esc(part.v)}</span>`;
  if (part.t === "bold") return `<span class="rule-word bold">${esc(part.v)}</span>`;
  if (part.t === "join" || part.t === "muted") return `<span class="rule-word muted">${esc(part.v)}</span>`;
  return `<span class="rule-word">${esc(part.v)}</span>`;
}

function summaryLines(row) {
  return row.summary
    .map(
      (line) =>
        `<div class="rule-line"><span class="rule-line-label">${esc(line.label)}</span>${line.parts.map(summaryPart).join("")}</div>`,
    )
    .join("");
}

function ruleMenu(row, key) {
  const edit = row.open ? "Close editor" : "Edit";
  const item = (act, label, cls) =>
    `<button class="menu-item${cls}" type="button" role="menuitem" data-act="${act}" data-uid="${row.uid}" data-key="${key}-${act.slice(5)}">${label}</button>`;
  return `<div class="menu rule-menu" role="menu">
    ${item("rule-edit", edit, "")}
    ${item("rule-duplicate", "Duplicate", "")}
    <div class="menu-separator"></div>
    ${item("rule-delete", "Delete", " danger")}
  </div>`;
}

function ruleActions(row) {
  const key = `rule-${row.uid}`;
  const menuName = `${key}-menu`;
  const open = view.menu === menuName;
  const move = (dir, glyph, able) => {
    const title = row.move_title || (dir === "up" ? "Move up" : "Move down");
    return `<button class="btn ghost compact icon rule-move" type="button" title="${esc(title)}" aria-label="${esc(title)}" data-act="rule-move" data-uid="${row.uid}" data-dir="${dir}" data-key="${key}-${dir}"${off(!able)}>${svg(glyph, "glyph")}</button>`;
  };
  return `<div class="rule-actions">
    <button class="btn secondary compact rule-test" type="button" title="${esc(row.test_title)}" data-act="rule-test" data-uid="${row.uid}" data-key="${key}-test"${off(!row.can_test)}>Test…</button>
    ${move("up", RULE_GLYPH.up, row.can_up)}
    ${move("down", GLYPH.chevron, row.can_down)}
    <div class="menu-anchor">
      <button class="btn ghost compact icon rule-more" type="button" title="Edit, duplicate, delete" aria-label="Edit, duplicate, delete" aria-haspopup="menu" aria-expanded="${open}" data-act="menu" data-menu="${menuName}" data-key="${menuName}">${svg(RULE_GLYPH.more, "glyph dots")}</button>
      ${open ? ruleMenu(row, menuName) : ""}
    </div>
  </div>`;
}

function ruleRow(row, level) {
  const key = `rule-${row.uid}`;
  const grip = row.can_drag ? "Drag to reorder" : row.move_title;
  const name = row.open
    ? `<input class="field rule-name-field" type="text" value="${esc(row.name)}" aria-label="Rule name" data-input="rule_name" data-uid="${row.uid}" data-key="${key}-name">`
    : `<button class="rule-name" type="button" data-act="rule-open" data-uid="${row.uid}" data-key="${key}-name">${esc(row.label)}</button>`;
  const badge = row.badge ? `<span class="badge neutral">${esc(row.badge)}</span>` : "";
  const below = row.open ? "" : summaryLines(row) + (row.problem ? problemLine(row.problem) : "");
  const cls = `rule${row.open ? " open" : ""}${row.on ? "" : " off"}${row.wide_labels ? " wide" : ""}`;
  return `<div class="${cls}" data-rule="${row.uid}" data-group="${level}" data-key="${key}">
    <span class="rule-grip${row.can_drag ? "" : " disabled"}" data-grip="${row.uid}" title="${esc(grip)}" aria-hidden="true">${svg(RULE_GLYPH.grip, "glyph dots")}</span>
    <button class="switch" type="button" role="switch" aria-checked="${Boolean(row.on)}" aria-label="${esc(row.label)}" title="${esc(row.switch_title)}" data-act="rule-enabled" data-uid="${row.uid}" data-key="${key}-switch"><span class="switch-knob"></span></button>
    <div class="rule-text">
      <div class="rule-head"><span class="rule-num mono">${esc(row.num)}</span>${name}${badge}</div>
      ${below}
    </div>
    ${ruleActions(row)}
    ${row.open ? ruleEditor(row) : ""}
  </div>`;
}

function rulesGroup(group) {
  const label = group.label
    ? `<div class="rules-group"><span class="rules-group-label">${esc(group.label)}</span><span>${esc(group.note)}</span></div>`
    : "";
  return label + group.rows.map((row) => ruleRow(row, group.level)).join("");
}

function rulesPage(r) {
  if (r.empty) {
    return `<section class="card state rules-empty" data-card="rules-empty">
      <span class="rules-empty-tile">${svg(RULE_GLYPH.rules, "state-glyph")}</span>
      <p class="state-title">${esc(r.empty.title)}</p>
      <p class="state-text">${esc(r.empty.text)}</p>
      <button class="btn primary" type="button" data-act="rule-add" data-key="rule-add">${svg(GLYPH.plus, "glyph")}${esc(r.empty.action)}</button>
    </section>`;
  }
  const none = r.no_hits ? `<div class="rules-none">${esc(r.no_hits)}</div>` : "";
  return `<section class="card rules-card" data-card="rules">
    <div class="rules-bar">
      <label class="input rules-filter">${svg(RULE_GLYPH.search, "glyph")}<input type="text" value="${esc(r.filter)}" placeholder="${esc(r.filter_placeholder)}" aria-label="${esc(r.filter_placeholder)}" data-input="filter" data-key="rules-filter"></label>
      <span class="spacer"></span>
      <span class="rules-count">${esc(r.count)}</span>
    </div>
    ${r.groups.map(rulesGroup).join("")}
    ${none}
  </section>`;
}

// --- the editor ----------------------------------------------------------------

// A .select and, while it is open, its menu. The menu's name is the select's
// own data-key, so closing it gives focus back to the select.
function ruleSelect(key, label, text, invalid, menu, cls) {
  const open = view.menu === key;
  const value = text
    ? `<span class="select-value">${esc(text)}</span>`
    : `<span class="select-value placeholder">Choose</span>`;
  return `<div class="menu-anchor ${cls}">
    <button class="select${invalid ? " invalid" : ""}" type="button" aria-haspopup="menu" aria-expanded="${open}" aria-label="${esc(label)}" data-act="menu" data-menu="${key}" data-key="${key}">${value}${svg(GLYPH.chevron, "glyph")}</button>
    ${open ? `<div class="menu editor-menu" role="menu">${menu()}</div>` : ""}
  </div>`;
}

function segments(options, label, act, data, key) {
  const attrs = Object.keys(data)
    .map((name) => ` data-${name}="${esc(data[name])}"`)
    .join("");
  const buttons = options
    .map(
      (o) =>
        `<button class="segment" type="button" role="radio" aria-checked="${Boolean(o.checked)}" tabindex="${o.checked ? 0 : -1}" data-act="${act}"${attrs} data-value="${o.value}" data-key="${key}-${o.value}">${esc(o.label)}</button>`,
    )
    .join("");
  return `<div class="segmented" role="radiogroup" aria-label="${esc(label)}">${buttons}</div>`;
}

// An <input list> and its <datalist>: any text can be typed.
function suggestions(key, options) {
  if (!options.length) return ["", ""];
  const id = `dl-${key}`;
  return [` list="${id}"`, `<datalist id="${id}">${options.map((o) => `<option value="${esc(o)}"></option>`).join("")}</datalist>`];
}

function under(problem, hint) {
  if (problem) return problemLine(problem);
  return hint ? `<span class="hint">${esc(hint)}</span>` : "";
}

function conditionRow(e, uid, s, c, cond) {
  const key = `rule-${uid}-s${s}-c${c}`;
  const at = { uid, s, c };
  const fieldMenu = () => {
    const items = [];
    let n = 0;
    const item = (field, note) =>
      menuItem("cond-field", { ...at, value: field }, field, note, field === cond.field, `${key}-field-item-${n++}`, false);
    if (cond.extra_field) items.push(item(cond.extra_field.value, cond.extra_field.note));
    e.field_groups.forEach((group) => {
      items.push(`<div class="menu-group">${esc(group.label)}</div>`);
      group.fields.forEach((field) => items.push(item(field, "")));
    });
    return items.join("");
  };
  const operatorMenu = () => {
    const listed = cond.extra_operator ? [cond.extra_operator].concat(e.operators) : e.operators;
    return listed
      .map((operator, n) =>
        menuItem("cond-op", { ...at, value: operator }, operator, n === 0 && cond.extra_operator ? "Not available" : "", operator === cond.operator, `${key}-op-item-${n}`, false),
      )
      .join("");
  };
  const v = cond.value;
  const input = `data-input="cond_value" data-uid="${uid}" data-s="${s}" data-c="${c}" data-key="${key}-value" aria-label="Value"`;
  let value = `<span class="cond-none"></span>`;
  if (v.kind === "date") {
    value = `<input class="field${cond.invalid ? " invalid" : ""}" type="date" value="${esc(v.text)}" ${input}>`;
  } else if (v.kind === "text") {
    const [list, datalist] = suggestions(key, v.suggestions);
    value = `<input class="field${cond.invalid ? " invalid" : ""}" type="text" value="${esc(v.text)}" placeholder="${esc(v.placeholder)}"${list} ${input}>${datalist}`;
  }
  return `<div class="cond" data-cond="${c}">
    <div class="cond-row">
      ${ruleSelect(`${key}-field`, "Field", cond.field, cond.field_invalid, fieldMenu, "cond-field")}
      ${ruleSelect(`${key}-op`, "Operator", cond.operator, Boolean(cond.extra_operator), operatorMenu, "cond-op")}
      <div class="cond-value">${value}</div>
      <button class="btn ghost compact icon" type="button" title="Remove condition" aria-label="Remove condition" data-act="cond-remove" data-uid="${uid}" data-s="${s}" data-c="${c}" data-key="${key}-remove">${svg(GLYPH.x, "glyph")}</button>
    </div>
    ${under(cond.problem, cond.hint)}
  </div>`;
}

function actionParam(uid, s, a, p) {
  const key = `rule-${uid}-s${s}-a${a}-${p.name}`;
  const at = { uid, s, a, name: p.name };
  const lead = p.lead ? `<span class="param-lead">${esc(p.lead)}</span>` : "";
  const input = `data-input="action_param" data-uid="${uid}" data-s="${s}" data-a="${a}" data-name="${p.name}" data-key="${key}" aria-label="${esc(p.placeholder || p.name)}"`;
  if (p.kind === "field") {
    const listed = p.extra ? [p.extra].concat(p.options) : p.options;
    const menu = () =>
      listed
        .map((field, n) =>
          menuItem("action-param", { ...at, value: field }, field, n === 0 && p.extra ? "Not available" : "", field === p.value, `${key}-item-${n}`, false),
        )
        .join("");
    return lead + ruleSelect(key, p.name, p.value, Boolean(p.extra), menu, "param-field");
  }
  if (p.kind === "choice") {
    const chosen = p.options.find((o) => o.value === p.value);
    const menu = () =>
      p.options
        .map((o, n) => menuItem("action-param", { ...at, value: o.value }, o.label, "", o.value === p.value, `${key}-item-${n}`, false))
        .join("");
    return lead + ruleSelect(key, p.name, chosen ? chosen.label : p.value, false, menu, "param-choice");
  }
  if (p.kind === "number") {
    return `${lead}<input class="field mono param-number${p.invalid ? " invalid" : ""}" type="text" inputmode="numeric" value="${esc(p.value)}" ${input}>`;
  }
  const [list, datalist] = p.kind === "suggest" ? suggestions(key, p.options) : ["", ""];
  return `${lead}<input class="field param-text" type="text" value="${esc(p.value)}" placeholder="${esc(p.placeholder)}"${list} ${input}>${datalist}`;
}

function actionRow(e, uid, s, a, action) {
  const key = `rule-${uid}-s${s}-a${a}`;
  const typeMenu = () => {
    const listed = action.extra_type ? [action.extra_type].concat(e.action_types) : e.action_types;
    return listed
      .map((t, n) => menuItem("action-type", { uid, s, a, value: t.value }, t.label, "", t.value === action.type, `${key}-type-item-${n}`, false))
      .join("");
  };
  return `<div class="action" data-action="${a}">
    <div class="action-row">
      <div class="action-controls">
        ${ruleSelect(`${key}-type`, "Action", action.label, false, typeMenu, "action-type")}
        ${action.params.map((p) => actionParam(uid, s, a, p)).join("")}
      </div>
      <button class="btn ghost compact icon" type="button" title="Remove action" aria-label="Remove action" data-act="action-remove" data-uid="${uid}" data-s="${s}" data-a="${a}" data-key="${key}-remove">${svg(GLYPH.x, "glyph")}</button>
    </div>
    ${under(action.problem, action.hint)}
  </div>`;
}

function addRow(act, label, uid, s, count, key) {
  return `<button class="btn ghost compact add-row" type="button" data-act="${act}" data-uid="${uid}" data-s="${s}" data-count="${count}" data-key="${key}">${svg(GLYPH.plus, "glyph")}${label}</button>`;
}

function editorStep(e, uid, s, step) {
  const key = `rule-${uid}-s${s}`;
  const remove = step.removable
    ? `<button class="btn ghost compact danger" type="button" data-act="step-remove" data-uid="${uid}" data-s="${s}" data-key="${key}-remove">Remove step</button>`
    : "";
  const head = step.title
    ? `<div class="step-head"><span class="step-title">${esc(step.title)}</span><span class="step-note">${esc(step.note)}</span><span class="spacer"></span>${remove}</div>`
    : "";
  const match = step.match.show
    ? `<div class="match-line">${segments(step.match.options, "Match", "step-match", { uid, s }, `${key}-match`)}<span>${esc(step.match.tail)}</span></div>`
    : "";
  return `<div class="editor-step${step.title ? " titled" : ""}" data-step="${s}">
    ${head}
    <div class="editor-line">
      <span class="editor-label">When</span>
      <div class="editor-content">
        ${match}
        ${step.conditions.map((cond, c) => conditionRow(e, uid, s, c, cond)).join("")}
        ${addRow("cond-add", "Add condition", uid, s, step.conditions.length, `${key}-cond-add`)}
      </div>
    </div>
    <div class="editor-line">
      <span class="editor-label">Then</span>
      <div class="editor-content">
        ${step.actions.map((action, a) => actionRow(e, uid, s, a, action)).join("")}
        ${addRow("action-add", "Add action", uid, s, step.actions.length, `${key}-action-add`)}
      </div>
    </div>
  </div>`;
}

function ruleEditor(row) {
  const e = row.editor;
  const uid = row.uid;
  const key = `rule-${uid}`;
  return `<div class="rule-editor">
    <div class="editor-line">
      <span class="editor-label">Level</span>
      <div class="editor-content level-line">${segments(e.level.options, "Level", "rule-level", { uid }, `${key}-level`)}<span class="hint">${esc(e.level.hint)}</span></div>
    </div>
    ${e.steps.map((step, s) => editorStep(e, uid, s, step)).join("")}
    <div class="editor-foot">
      <button class="btn ghost compact add-row" type="button" data-act="step-add" data-uid="${uid}" data-key="${key}-step-add">${svg(GLYPH.plus, "glyph")}Add step</button>
      <span class="spacer"></span>
      <button class="btn secondary" type="button" data-act="rule-close" data-uid="${uid}" data-key="${key}-done">Done</button>
    </div>
  </div>`;
}

// --- the Test panel ------------------------------------------------------------

function testPanel(t) {
  const session = t.intro.session ? `<span class="mono">${esc(t.intro.session)}</span>` : "";
  let body = "";
  if (t.status === "running") {
    body = `<div class="test-message">${esc(t.message)}</div>`;
  } else if (t.status === "failed") {
    body = problemLine(t.message);
  } else {
    const rows = t.rows
      .map(
        (row) =>
          `<div class="test-row"><span class="test-order mono">${esc(row.order)}</span><span class="test-why mono" title="${esc(row.why)}">${esc(row.why)}</span><span class="test-change mono${row.changed ? "" : " same"}" title="${esc(row.change)}">${esc(row.change)}</span></div>`,
      )
      .join("");
    const table = t.rows.length
      ? `<div class="test-table">
          <div class="test-row heads">${t.heads.map((head) => `<span>${esc(head)}</span>`).join("")}</div>
          ${rows}
          ${t.more ? `<div class="test-more">${esc(t.more)}</div>` : ""}
        </div>`
      : `<div class="test-message">${esc(t.empty)}</div>`;
    body = `<div class="test-count"><span class="test-matched mono">${esc(t.matched)}</span><span>${esc(t.total)}</span></div>
      ${table}
      ${t.note ? `<span class="hint">${esc(t.note)}</span>` : ""}`;
  }
  return `<div class="scrim" data-test="${esc(t.status)}">
    <div class="test-panel" role="dialog" aria-modal="true" aria-labelledby="test-title">
      <div class="test-head">
        <span class="test-title" id="test-title">${esc(t.title)}</span>
        <button class="btn ghost icon" type="button" title="Close" aria-label="Close" data-act="test-close" data-key="test-x">${svg(GLYPH.x, "glyph")}</button>
      </div>
      <div class="test-body">
        <span class="test-intro">${esc(t.intro.lead)}${session}${esc(t.intro.tail)}</span>
        ${body}
      </div>
      <div class="test-foot"><button class="btn secondary" type="button" data-act="test-close" data-key="test-close">Close</button></div>
    </div>
  </div>`;
}

// --- render hooks ----------------------------------------------------------------

function ruleRowOf(r, uid) {
  for (const group of r.groups) {
    const row = group.rows.find((candidate) => candidate.uid === uid);
    if (row) return row;
  }
  return null;
}

// A rule's "…" menu needs its row; a menu inside the editor needs it open.
function rulesMenuStillOpens(r, name) {
  const found = /^rule-(\d+)-(.*)$/.exec(name);
  if (!found) return false;
  const row = ruleRowOf(r, found[1]);
  return Boolean(row) && (found[2] === "menu" || row.open);
}

// After every render: the focus an edit asked for, and the panel's.
function rulesRendered(s) {
  const pending = view.pending;
  if (pending === "@open-name") {
    const field = els.root.querySelector(".rule.open .rule-name-field");
    if (field) {
      field.focus();
      field.select();
      view.pending = null;
    }
  } else if (typeof pending === "string" && pending.startsWith("@move:")) {
    // The button pressed may have reached its group's edge: the other one
    // then takes the focus, so the keyboard can keep moving the rule.
    const [, uid, dir] = pending.split(":");
    const other = dir === "up" ? "down" : "up";
    if (focusKey(`rule-${uid}-${dir}`) || focusKey(`rule-${uid}-${other}`)) view.pending = null;
  }
  const shown = Boolean(s.test);
  if (shown && !rulesView.shown) focusKey("test-close");
  if (!shown && rulesView.shown) focusKey(`rule-${rulesView.uid}-test`);
  rulesView.shown = shown;
  if (shown) rulesView.uid = s.test.uid;
}

// --- input -------------------------------------------------------------------------

// Whether the click was one of this page's.
function rulesClick(data, el, bridge) {
  const uid = data.uid;
  switch (data.act) {
    case "rule-add":
      view.pending = "@open-name";
      bridge.edit("rule_add", []);
      return true;
    case "rule-open":
      view.pending = "@open-name";
      bridge.edit("open", [uid]);
      return true;
    case "rule-edit": {
      const open = Boolean(el.closest(".rule.open"));
      view.menu = null;
      view.pending = open ? `rule-${uid}-name` : "@open-name";
      bridge.edit(open ? "close" : "open", open ? [] : [uid]);
      return true;
    }
    case "rule-close":
      view.pending = `rule-${uid}-name`;
      bridge.edit("close", []);
      return true;
    case "rule-enabled":
      bridge.edit("rule_enabled", [uid, el.getAttribute("aria-checked") !== "true"]);
      return true;
    case "rule-move":
      view.pending = `@move:${uid}:${data.dir}`;
      bridge.edit("rule_move", [uid, data.dir]);
      return true;
    case "rule-duplicate":
      bridge.edit("rule_duplicate", [uid]);
      closeMenu();
      return true;
    case "rule-delete":
      view.menu = null;
      view.pending = "rules-filter";
      bridge.edit("rule_delete", [uid]);
      return true;
    case "rule-test":
      bridge.testRule(uid);
      return true;
    case "test-close":
      bridge.closeTest();
      return true;
    case "rule-level":
      view.pending = `rule-${uid}-level-${data.value}`;
      bridge.edit("rule_level", [uid, data.value]);
      return true;
    case "step-add":
      bridge.edit("step_add", [uid]);
      return true;
    case "step-remove":
      view.pending = `rule-${uid}-step-add`;
      bridge.edit("step_remove", [uid, data.s]);
      return true;
    case "step-match":
      view.pending = `rule-${uid}-s${data.s}-match-${data.value}`;
      bridge.edit("step_match", [uid, data.s, data.value]);
      return true;
    case "cond-add":
      // The new row is the next position: focus its field once it arrives.
      view.pending = `rule-${uid}-s${data.s}-c${data.count}-field`;
      bridge.edit("cond_add", [uid, data.s]);
      return true;
    case "cond-remove":
      view.pending = `rule-${uid}-s${data.s}-cond-add`;
      bridge.edit("cond_remove", [uid, data.s, data.c]);
      return true;
    case "cond-field":
      bridge.edit("cond_field", [uid, data.s, data.c, data.value]);
      closeMenu();
      return true;
    case "cond-op":
      bridge.edit("cond_operator", [uid, data.s, data.c, data.value]);
      closeMenu();
      return true;
    case "action-add":
      view.pending = `rule-${uid}-s${data.s}-a${data.count}-type`;
      bridge.edit("action_add", [uid, data.s]);
      return true;
    case "action-remove":
      view.pending = `rule-${uid}-s${data.s}-action-add`;
      bridge.edit("action_remove", [uid, data.s, data.a]);
      return true;
    case "action-type":
      bridge.edit("action_type", [uid, data.s, data.a, data.value]);
      closeMenu();
      return true;
    case "action-param":
      bridge.edit("action_param", [uid, data.s, data.a, data.name, data.value]);
      closeMenu();
      return true;
  }
  return false;
}

// Whether the keystroke was in one of this page's fields.
function rulesInput(data, el, bridge) {
  switch (data.input) {
    case "filter":
      bridge.edit("filter", [el.value]);
      return true;
    case "rule_name":
      bridge.edit("rule_name", [data.uid, el.value]);
      return true;
    case "cond_value":
      bridge.edit("cond_value", [data.uid, data.s, data.c, el.value]);
      return true;
    case "action_param":
      bridge.edit("action_param", [data.uid, data.s, data.a, data.name, el.value]);
      return true;
  }
  return false;
}

// Escape ends a drag, else closes the Test panel. Whether it did either.
function rulesEscape() {
  if (rulesView.drag) {
    endDrag();
    return true;
  }
  if (page.state && page.state.test && page.bridge) {
    page.bridge.closeTest();
    return true;
  }
  return false;
}

// --- dragging a rule by its grip -------------------------------------------------

const DRAG_EDGE_PX = 40;
const DRAG_SCROLL_PX = 12;

function markDrop() {
  const d = rulesView.drag;
  d.rows.forEach((row) => row.classList.remove("drop-before", "drop-after"));
  if (d.to === d.from) return;
  const others = d.rows.filter((row, n) => n !== d.from);
  if (d.to < others.length) others[d.to].classList.add("drop-before");
  else others[others.length - 1].classList.add("drop-after");
}

function endDrag() {
  const d = rulesView.drag;
  if (!d) return;
  d.rows.forEach((row) => row.classList.remove("dragging", "drop-before", "drop-after"));
  document.body.classList.remove("is-dragging");
  rulesView.drag = null;
}

function onGripDown(event) {
  const grip = event.target.closest ? event.target.closest("[data-grip]") : null;
  if (!grip || event.button !== 0 || grip.classList.contains("disabled")) return;
  const row = grip.closest(".rule");
  const rows = Array.from(els.root.querySelectorAll(`.rule[data-group="${row.dataset.group}"]`));
  const from = rows.indexOf(row);
  rulesView.drag = { uid: grip.dataset.grip, rows, from, to: from };
  row.classList.add("dragging");
  document.body.classList.add("is-dragging");
  // So the drag keeps its events outside the view. A synthetic pointer has
  // nothing to capture.
  try {
    grip.setPointerCapture(event.pointerId);
  } catch (error) {
    /* not a live pointer */
  }
  event.preventDefault();
}

function onGripMove(event) {
  const d = rulesView.drag;
  if (!d) return;
  // The place it would land: how many of the other rows sit above the pointer.
  let to = 0;
  d.rows.forEach((row, n) => {
    if (n === d.from) return;
    const box = row.getBoundingClientRect();
    if (event.clientY > box.top + box.height / 2) to += 1;
  });
  d.to = to;
  markDrop();
  // ponytail: scrolls only while the pointer moves. A timer would keep it
  // going on a held pointer; add one if a client's list outgrows the window.
  const box = els.root.getBoundingClientRect();
  if (event.clientY < box.top + DRAG_EDGE_PX) els.root.scrollTop -= DRAG_SCROLL_PX;
  else if (event.clientY > box.bottom - DRAG_EDGE_PX) els.root.scrollTop += DRAG_SCROLL_PX;
}

function onGripUp() {
  const d = rulesView.drag;
  if (!d) return;
  const moved = d.to !== d.from;
  endDrag();
  if (moved && page.bridge) page.bridge.edit("rule_move_to", [d.uid, String(d.to)]);
}

function bindRules() {
  els.root.addEventListener("pointerdown", onGripDown);
  document.addEventListener("pointermove", onGripMove);
  document.addEventListener("pointerup", onGripUp);
  document.addEventListener("pointercancel", endDrag);
}
```

- [ ] **Step 5: Hook it into the settings document**

**Modify `gui/web/settings.html`.**
 Find exactly:

```html
<link rel="stylesheet" href="kit.css">
<link rel="stylesheet" href="settings.css">
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<script src="settings.js" defer></script>
</head>
<body>
```

Replace with:

```html
<link rel="stylesheet" href="kit.css">
<link rel="stylesheet" href="settings.css">
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<script src="settings_rules.js" defer></script>
<script src="settings.js" defer></script>
</head>
<body>
```

**Modify `gui/web/settings.js`.**
 Find exactly:

```javascript
// The Client settings pages the web tier draws: General, Orders mapping and
// Stock mapping (phase 7 spec section 5). Python holds every value and words
// every sentence (gui/settings/page_state.py) and sends one page's view as
// bridge.state; this file renders it and reports each edit through
// bridge.edit(action, args). Nothing is validated or computed here. The page's
// own state is which menu is open.
"use strict";
```

Replace with:

```javascript
// The Client settings pages the web tier draws: General, Orders mapping,
// Stock mapping (phase 7 spec section 5) and Rules (phase 8 spec section 5,
// drawn by settings_rules.js). Python holds every value and words every
// sentence (gui/settings/page_state.py, rules_state.py) and sends one page's
// view as bridge.state; this file renders it and reports each edit through
// bridge.edit(action, args). Nothing is validated or computed here. The page's
// own state is which menu is open.
"use strict";
```

 Find exactly:

```javascript
const els = {};
const page = { bridge: null, state: null, renders: 0 };
// menu: "field-<internal name>", "courier-code-<row>", "column-add",
// "chip:<column>", or null. shown: the page the last render drew. pending: a
// data-key to focus once the state that creates it arrives. problem: the key
// the footer's link asked for while another page was still showing.
const view = { menu: null, shown: null, pending: null, problem: null };

// A carriage return too: the parser would turn a bare one into a line feed,
```

Replace with:

```javascript
const els = {};
const page = { bridge: null, state: null, renders: 0 };
// menu: "field-<internal name>", "courier-code-<row>", "column-add",
// "chip:<column>", a Rules menu ("rule-<uid>-..."), or null: always the
// data-key of the control that opens it. shown: the page the last render drew.
// pending: a data-key to focus once the state that creates it arrives, or one
// of the Rules page's own requests ("@..."). problem: the key the footer's
// link asked for while another page was still showing.
const view = { menu: null, shown: null, pending: null, problem: null };

// A carriage return too: the parser would turn a bare one into a line feed,
```

 Find exactly:

```javascript

// --- what every page shares --------------------------------------------------

function head(s) {
  const action = s.action
    ? `<button class="btn secondary" type="button" data-act="read" data-key="read-columns">${svg(GLYPH.plus, "glyph")}${esc(s.action)}</button>`
    : "";
  return `<div class="page-head split">
    <div class="page-head-text"><span class="page-title">${esc(s.title)}</span><span class="page-sub">${esc(s.subtitle)}</span></div>
```

Replace with:

```javascript

// --- what every page shares --------------------------------------------------

// The page head's action: what it does, and its data-key.
const HEAD_ACTION = { rules: ["rule-add", "rule-add"] };

function head(s) {
  const [act, key] = HEAD_ACTION[s.page] || ["read", "read-columns"];
  const action = s.action
    ? `<button class="btn secondary" type="button" data-act="${act}" data-key="${key}">${svg(GLYPH.plus, "glyph")}${esc(s.action)}</button>`
    : "";
  return `<div class="page-head split">
    <div class="page-head-text"><span class="page-title">${esc(s.title)}</span><span class="page-sub">${esc(s.subtitle)}</span></div>
```

 Find exactly:

```javascript
// A menu whose opener a new state removed or disabled must not stay open.
function menuStillOpens(s) {
  const name = view.menu;
  const m = s.mapping;
  if (!m) return false;
  if (name.startsWith("field-")) {
```

Replace with:

```javascript
// A menu whose opener a new state removed or disabled must not stay open.
function menuStillOpens(s) {
  const name = view.menu;
  if (s.rules) return rulesMenuStillOpens(s.rules, name);
  const m = s.mapping;
  if (!m) return false;
  if (name.startsWith("field-")) {
```

 Find exactly:

```javascript
    view.pending = null;
  }
  if (view.menu !== null && !menuStillOpens(s)) view.menu = null;
  const active = document.activeElement;
  const key = active ? keyOf(active) : null;
  const fresh = document.createElement("template");
  fresh.innerHTML =
    `<div class="settings-page" data-page="${esc(s.page)}">` +
    head(s) +
    (s.general ? generalPage(s.general) : "") +
    (s.mapping ? mappingPage(s.mapping) : "") +
    "</div>";
  morph(els.root, fresh.content);
  if (s.page !== view.shown) {
    view.shown = s.page;
    els.root.scrollTop = 0;
```

Replace with:

```javascript
    view.pending = null;
  }
  if (view.menu !== null && !menuStillOpens(s)) view.menu = null;
  // A new state under a drag: the rows it was measuring may be gone.
  endDrag();
  const active = document.activeElement;
  const key = active ? keyOf(active) : null;
  const fresh = document.createElement("template");
  // The Test panel takes the page over: what is under it cannot be reached.
  fresh.innerHTML =
    `<div class="settings-page" data-page="${esc(s.page)}"${s.test ? " inert" : ""}>` +
    head(s) +
    (s.general ? generalPage(s.general) : "") +
    (s.mapping ? mappingPage(s.mapping) : "") +
    (s.rules ? rulesPage(s.rules) : "") +
    "</div>" +
    (s.test ? testPanel(s.test) : "");
  morph(els.root, fresh.content);
  // A menu whose opener this state no longer draws (a removed row).
  if (view.menu !== null && !byKey(view.menu)) view.menu = null;
  if (s.page !== view.shown) {
    view.shown = s.page;
    els.root.scrollTop = 0;
```

 Find exactly:

```javascript
    focusKey(key);
  }
  if (view.pending !== null && focusKey(view.pending)) view.pending = null;
  if (view.problem !== null) {
    const problem = view.problem;
    view.problem = null;
```

Replace with:

```javascript
    focusKey(key);
  }
  if (view.pending !== null && focusKey(view.pending)) view.pending = null;
  rulesRendered(s);
  if (view.problem !== null) {
    const problem = view.problem;
    view.problem = null;
```

 Find exactly:

```javascript
  const bridge = page.bridge;
  if (!el || el.disabled || !bridge) return;
  const data = el.dataset;
  switch (data.act) {
    case "read": bridge.readColumns(); break;
    case "delimiter": bridge.edit("delimiter", [data.kind, data.value]); break;
```

Replace with:

```javascript
  const bridge = page.bridge;
  if (!el || el.disabled || !bridge) return;
  const data = el.dataset;
  if (rulesClick(data, el, bridge)) return;
  switch (data.act) {
    case "read": bridge.readColumns(); break;
    case "delimiter": bridge.edit("delimiter", [data.kind, data.value]); break;
```

 Find exactly:

```javascript
  const bridge = page.bridge;
  if (!bridge || !el.dataset || !el.dataset.input) return;
  const data = el.dataset;
  if (data.input === "threshold") bridge.edit("threshold", [el.value]);
  else if (data.input === "delimiter_char") bridge.edit("delimiter_char", [data.kind, el.value]);
  else if (data.input === "courier_pattern") bridge.edit("courier_pattern", [data.index, el.value]);
```

Replace with:

```javascript
  const bridge = page.bridge;
  if (!bridge || !el.dataset || !el.dataset.input) return;
  const data = el.dataset;
  if (rulesInput(data, el, bridge)) return;
  if (data.input === "threshold") bridge.edit("threshold", [el.value]);
  else if (data.input === "delimiter_char") bridge.edit("delimiter_char", [data.kind, el.value]);
  else if (data.input === "courier_pattern") bridge.edit("courier_pattern", [data.index, el.value]);
```

 Find exactly:

```javascript
function onKey(event) {
  const target = event.target;
  if (event.key === "Escape") {
    // With no menu open the page leaves Escape alone, and the dialog takes it.
    if (view.menu === null) return;
    event.preventDefault();
    closeMenu();
    return;
  }
  if (event.key === "Enter" && target.dataset && target.dataset.newCourier !== undefined) {
```

Replace with:

```javascript
function onKey(event) {
  const target = event.target;
  if (event.key === "Escape") {
    // With no menu open, no drag and no Test panel, the page leaves Escape
    // alone, and the dialog takes it.
    if (view.menu !== null) {
      event.preventDefault();
      closeMenu();
    } else if (rulesEscape()) {
      event.preventDefault();
    }
    return;
  }
  if (event.key === "Enter" && target.dataset && target.dataset.newCourier !== undefined) {
```

 Find exactly:

```javascript
  // A file dropped on the page must not navigate the view. It loads nothing.
  document.addEventListener("dragover", (event) => event.preventDefault());
  document.addEventListener("drop", (event) => event.preventDefault());
}

bind();
```

Replace with:

```javascript
  // A file dropped on the page must not navigate the view. It loads nothing.
  document.addEventListener("dragover", (event) => event.preventDefault());
  document.addEventListener("drop", (event) => event.preventDefault());
  bindRules();
}

bind();
```

- [ ] **Step 6: Add the styles**

**Modify `gui/web/settings.css`.**
 Find exactly:

```css
/* The Client settings pages the web tier draws: General, Orders mapping and
   Stock mapping (phase 7 spec section 5). Layout only: every component is the
   kit's. Every colour is a token from theme_css_vars(). */

#settings {
```

Replace with:

```css
/* The Client settings pages the web tier draws: General, Orders mapping,
   Stock mapping (phase 7 spec section 5) and Rules with its Test panel
   (phase 8 spec sections 5 and 6). Layout only: every component is the
   kit's. Every colour is a token from theme_css_vars(). */

#settings {
```

 Append at the end of the file:

```css
/* --- Rules (phase 8 spec section 5) -------------------------------------- */

/* Chromium's own popups, the date picker and the suggestion list, follow the
   theme on this page. */
#settings { color-scheme: var(--color-scheme); }

.rules-card { display: flex; flex-direction: column; }
.rules-bar { display: flex; align-items: center; gap: 12px; padding: 12px 16px; }
.rules-filter { width: 260px; }
.rules-count,
.rules-none { color: var(--text-secondary); }
.rules-none { padding: 16px; border-top: 1px solid var(--border-subtle); }

.rules-group {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 10px 16px 6px;
  border-top: 1px solid var(--border-subtle);
  font-size: var(--type-caption-size);
  color: var(--text-secondary);
}
.rules-group-label { font-weight: 700; }

.rules-empty { padding: 48px 24px; gap: 10px; }
.rules-empty-tile {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface-raised);
}
.rules-empty .state-text { max-width: 360px; }

/* The mockup's row: grip, switch, text, actions. The editor takes a second
   line under the text and the actions. */
.rule {
  position: relative;
  display: grid;
  grid-template-columns: 20px 32px minmax(0, 1fr) auto;
  column-gap: 12px;
  row-gap: 10px;
  align-items: start;
  padding: 12px 16px;
  border-top: 1px solid var(--border-subtle);
}
.rule > .switch { margin-top: 1px; }

.rule-grip {
  display: grid;
  place-items: center;
  height: 20px;
  color: var(--text-disabled);
  cursor: grab;
  touch-action: none;
  user-select: none;
}
.rule-grip:hover { color: var(--text-secondary); }
.rule-grip.disabled { cursor: default; }
.rule-grip.disabled:hover { color: var(--text-disabled); }
.glyph.dots { stroke-width: 3; }

.rule-text { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.rule-head { display: flex; align-items: center; gap: 8px; min-width: 0; min-height: 20px; }
.rule-num { font-size: var(--type-caption-size); color: var(--text-secondary); }
.rule-name {
  min-width: 0;
  padding: 0;
  border: 0;
  background: transparent;
  overflow: hidden;
  font-weight: 700;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: pointer;
}
.rule-name:hover { text-decoration: underline; }
.rule-name:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 1px; }
.rule-name-field { flex: 1; min-width: 0; max-width: 360px; font-weight: 700; }

.rule-line { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.rule-line-label {
  width: 36px;
  font-size: var(--type-caption-size);
  font-weight: 700;
  color: var(--text-secondary);
}
.rule.wide .rule-line-label { width: 60px; }
.rule-word.bold { font-weight: 700; }
.rule-word.muted { color: var(--text-secondary); }
/* A value longer than its line is cut; its title holds the rest. */
.rule-chip {
  max-width: 100%;
  height: 22px;
  padding: 0 6px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface-raised);
  line-height: 20px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* A rule that is off reads quieter. Not by opacity: the web tier has none. */
.rule.off .rule-name,
.rule.off .rule-line { color: var(--text-secondary); }

.rule-actions { display: flex; align-items: center; gap: 2px; }
.rule-test { margin-right: 6px; font-size: var(--type-caption-size); }
.rule-move,
.rule-more { color: var(--text-secondary); }
/* At its group's edge a move button only greys, as the mockup draws it. */
.rule-move:disabled,
.rule-move:disabled:hover {
  border-color: transparent;
  background: transparent;
  cursor: default;
}
/* The button sits at the row's right edge: its menu opens leftwards. */
.rule-menu { left: auto; right: 0; min-width: 160px; }

/* A drag: the row in hand, and a line at the gap it would land in. */
.rule.dragging { background: var(--selection-bg); }
.rule.drop-before::before,
.rule.drop-after::after {
  content: "";
  position: absolute;
  left: 0;
  right: 0;
  height: 2px;
  background: var(--focus-ring);
}
.rule.drop-before::before { top: -1px; }
.rule.drop-after::after { bottom: -1px; }
.is-dragging { cursor: grabbing; user-select: none; }

/* --- the rule editor (phase 8 spec section 5.3) -------------------------- */

/* The summary with its words turned into controls: the same labels, in the
   same column. */
.rule-editor {
  grid-column: 3 / -1;
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
}
.editor-step { display: flex; flex-direction: column; gap: 12px; }
.editor-step.titled { padding-top: 12px; border-top: 1px solid var(--border-subtle); }
.editor-line {
  display: grid;
  grid-template-columns: 44px minmax(0, 1fr);
  column-gap: 6px;
  align-items: start;
}
.editor-label {
  font-size: var(--type-caption-size);
  font-weight: 700;
  line-height: var(--control-height);
  color: var(--text-secondary);
}
.editor-content { display: flex; flex-direction: column; align-items: stretch; gap: 6px; min-width: 0; }
.level-line,
.match-line { flex-direction: row; flex-wrap: wrap; align-items: center; gap: 8px; }
.match-line { display: flex; }
.level-line { min-height: var(--control-height); }

.step-head { display: flex; align-items: center; gap: 8px; min-height: var(--kit-control-compact); }
.step-title { font-weight: 700; }
.step-note { color: var(--text-secondary); }

.cond,
.action { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.cond-row {
  display: grid;
  grid-template-columns: minmax(140px, 220px) 180px minmax(0, 1fr) 28px;
  column-gap: 8px;
  align-items: center;
}
.cond-row .select,
.cond-value .field { width: 100%; }
.cond-op .select-value,
.param-choice .select-value { font-weight: 400; }
.cond-value { display: flex; min-width: 0; }

/* The parameters wrap under the type; the remove button stays on its line. */
.action-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 28px;
  column-gap: 8px;
  align-items: start;
}
.action-controls { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; min-width: 0; }
.action-type .select { width: 190px; }
.param-field .select { width: 150px; }
.param-choice .select { width: 120px; }
.param-text { flex: 1 1 140px; min-width: 120px; }
.param-number { width: 64px; text-align: right; }
.param-lead { color: var(--text-secondary); }
.action-row .btn.icon,
.cond-row .btn.icon { color: var(--text-secondary); }

.editor-menu { min-width: 100%; max-height: 280px; }
.add-row { align-self: flex-start; padding: 0 8px; color: var(--text-secondary); }
.editor-foot { display: flex; align-items: center; gap: 8px; }

/* --- the Test rule panel (phase 8 spec section 6.4) ---------------------- */

.scrim {
  position: fixed;
  inset: 0;
  z-index: calc(var(--z-toast) + 1);
  display: grid;
  place-items: center;
  background: var(--scrim);
}
.test-panel {
  display: flex;
  flex-direction: column;
  width: 580px;
  max-width: calc(100% - 32px);
  max-height: calc(100% - 32px);
  border: 1px solid var(--card-border);
  border-radius: var(--kit-radius-card);
  background: var(--surface);
  box-shadow: var(--overlay-shadow);
}
.test-head {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  height: 48px;
  padding: 0 12px 0 16px;
  border-bottom: 1px solid var(--border-subtle);
}
.test-title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  font-size: var(--type-label-size);
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.test-head .btn.icon { color: var(--text-secondary); }
.test-body { display: flex; flex-direction: column; gap: 12px; padding: 16px; overflow: auto; }
.test-intro,
.test-message,
.test-more { color: var(--text-secondary); }
.test-intro .mono { color: var(--text); }
.test-count { display: flex; align-items: baseline; gap: 6px; }
.test-matched { font-size: var(--type-heading-size); font-weight: 700; }
.test-table {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: var(--kit-radius);
}
.test-row {
  display: grid;
  grid-template-columns: 90px minmax(0, 1fr) 150px;
  column-gap: 12px;
  padding: 7px 12px;
  border-top: 1px solid var(--border-subtle);
}
.test-row.heads {
  padding: 6px 12px;
  border-top: 0;
  background: var(--surface-raised);
  font-size: var(--type-caption-size);
  font-weight: 700;
  color: var(--text-secondary);
}
.test-order { font-weight: 700; }
.test-order,
.test-why,
.test-change { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.test-change { color: var(--status-success); }
.test-change.same { color: var(--text-secondary); }
.test-more { padding: 7px 12px; border-top: 1px solid var(--border-subtle); }
.test-foot {
  flex-shrink: 0;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 16px;
  border-top: 1px solid var(--border-subtle);
}
```

- [ ] **Step 7: Run the tests, the style lint and the lint**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_settings_bridge.py tests/test_settings_rules_page.py tests/test_settings_web_page.py tests/test_style_literals_guard.py`
Expected: all pass. (`110 passed`.) The page file takes about a minute.

Run: `.venv/bin/ruff check .`
Expected: `All checks passed!`

- [ ] **Step 8: Commit**

`/usr/bin/git add -A`, then write this message to a file under your job's tmp dir and commit with
`/usr/bin/git commit -F <that file>`. Subject: `Settings: the Rules page and the Test rule panel on the web kit`. Body: two or three sentences: the list to the mockup, the editor that opens in the row, drag and button reordering, and that the window does not show it yet. End the message with the
attribution lines your session is given.

### Task 6: The host runs Test rule and reveals a blocked rule

**Files:**
- Modify: `gui/settings/web_host.py`
- Test: `tests/test_settings_web_host.py`

**Interfaces:**
- Consumes: `SettingsBridge.testRequested(str)`, `testClosed()`, `problemFocusRequested(str)`, `set_state`
  (Task 5); `RulesDraft.test_config(uid)` and `apply("reveal", [key])` (Task 3); `run_rule_test`,
  `running_view`, `failed_view` (Task 4); `Worker(fn, *args)` and its `signals.result` from `gui/worker.py`.
- Produces, for Task 7:
  - `SettingsWebHost(drafts: dict, analysis_df=None, session: str = "", parent=None)`.
  - `host.session`, `host.analysis_df`.
  - `show_page(key)` also ends a test; `focus_problem(key)` first reveals the control's rule.
  - `bridge.state["test"]` while a panel is open: the Task 4 view plus `"uid"`.

Spec §6.2.

Why the worker is wired the way it is: the function the worker runs (`_tested`) catches everything and
returns a view, so only `signals.result` is connected, and it is connected to a bound method of the host.
A bound method of a `QObject` is delivered on that object's thread; a lambda would run on the worker's.
Each test has a token. A result whose token is no longer the current one is dropped: the panel was closed,
the page changed, or another test started.

The tests patch `gui.settings.web_host.QThreadPool`, so `QThreadPool` must be imported into that module by
name, as the block below does.

- [ ] **Step 1: Write the failing tests**

**Modify `tests/test_settings_web_host.py`.**
 Find exactly:

```python
"""SettingsWebHost: one web view, three drafts (phase 7 spec section 6.5).

Nothing here waits for Chromium: the bridge's state is read on the Python
side, and the page's requests are made by calling the bridge's slots.
"""

import pytest
from PySide6.QtWidgets import QFileDialog

from gui.settings.page_state import (
```

Replace with:

```python
"""SettingsWebHost: one web view and its drafts (phase 7 spec section 6.5,
phase 8 spec section 6.2).

Nothing here waits for Chromium: the bridge's state is read on the Python
side, and the page's requests are made by calling the bridge's slots.
"""

import pandas as pd
import pytest
import shiboken6
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QFileDialog

from gui.settings.page_state import (
```

 Find exactly:

```python
    StockDraft,
    read_file_columns,
)
from gui.settings.web_host import SettingsWebHost
```

Replace with:

```python
    StockDraft,
    read_file_columns,
)
from gui.settings.rules_state import RulesDraft
from gui.settings.web_host import SettingsWebHost
```

 Append at the end of the file:

```python
# --- Rules: Test rule, and the footer's link (phase 8) ------------------------


def _analysis():
    return pd.DataFrame(
        {
            "Order_Number": ["#1", "#1", "#2", "#3"],
            "SKU": ["A", "B", "B", "A"],
            "Quantity": [4, 3, 1, 1],
            "Internal_Tags": ["[]"] * 4,
        }
    )


def _rule(name, operator="equals", value="A"):
    return {
        "name": name,
        "level": "article",
        "steps": [
            {
                "conditions": [{"field": "SKU", "operator": operator, "value": value}],
                "match": "ALL",
                "actions": [{"type": "ADD_INTERNAL_TAG", "value": "T"}],
            }
        ],
    }


@pytest.fixture
def test_workers(monkeypatch):
    """Catch the worker a test starts instead of letting a thread run it:
    the test then delivers its result when it chooses, by calling run()."""
    started = []
    monkeypatch.setattr(
        "gui.settings.web_host.QThreadPool",
        type(
            "Pool",
            (),
            {
                "globalInstance": staticmethod(
                    lambda: type("P", (), {"start": staticmethod(started.append)})()
                )
            },
        ),
    )
    return started


@pytest.fixture
def rules_host(qtbot, test_workers):
    drafts = {
        "general": GeneralDraft({"low_stock_threshold": 5}, "ACME"),
        "rules": RulesDraft([_rule("VIP"), _rule("bad", "matches regex", "(")], _analysis()),
    }
    widget = SettingsWebHost(drafts, analysis_df=_analysis(), session="2026-09-30_1")
    qtbot.addWidget(widget)
    widget.show_page("rules")
    return widget


def test_a_rule_edit_reaches_the_rules_draft(rules_host):
    seen = _edits(rules_host)
    rules_host.bridge.edit("rule_name", ["1", "VIP first"])
    assert rules_host.drafts["rules"].rules[0]["name"] == "VIP first"
    assert rules_host.bridge.state["rules"]["groups"][0]["rows"][0]["name"] == "VIP first"
    assert seen == [True]


def test_a_test_shows_the_panel_running_then_its_result(rules_host, test_workers):
    rules_host.bridge.testRule("1")
    test = rules_host.bridge.state["test"]
    assert (test["status"], test["uid"], test["message"]) == ("running", "1", "Testing 3 orders…")
    assert test["intro"]["session"] == "2026-09-30_1"
    assert len(test_workers) == 1

    test_workers[0].run()
    test = rules_host.bridge.state["test"]
    assert (test["status"], test["uid"]) == ("done", "1")
    assert (test["matched"], test["total"]) == ("2", "of 3 orders match")
    assert [row["order"] for row in test["rows"]] == ["#1", "#3"]
    # The page is still the Rules page under the panel.
    assert rules_host.bridge.state["page"] == "rules"


def test_a_test_runs_the_rule_as_edited(rules_host, test_workers):
    rules_host.bridge.edit("cond_value", ["1", "0", "0", "B"])
    rules_host.bridge.testRule("1")
    test_workers[0].run()
    assert [row["order"] for row in rules_host.bridge.state["test"]["rows"]] == ["#1", "#2"]


def test_a_test_does_not_mark_the_page_unsaved(rules_host, test_workers):
    seen = _edits(rules_host)
    rules_host.bridge.testRule("1")
    test_workers[0].run()
    rules_host.bridge.closeTest()
    assert seen == []


def test_close_takes_the_panel_away(rules_host, test_workers):
    rules_host.bridge.testRule("1")
    test_workers[0].run()
    rules_host.bridge.closeTest()
    assert "test" not in rules_host.bridge.state
    rules_host.bridge.closeTest()
    assert "test" not in rules_host.bridge.state


def test_a_result_that_arrives_after_close_is_dropped(rules_host, test_workers):
    rules_host.bridge.testRule("1")
    rules_host.bridge.closeTest()
    test_workers[0].run()
    assert "test" not in rules_host.bridge.state


def test_a_result_from_a_test_that_was_replaced_is_dropped(rules_host, test_workers):
    rules_host.bridge.testRule("1")
    rules_host.bridge.closeTest()
    rules_host.bridge.edit("cond_value", ["1", "0", "0", "B"])
    rules_host.bridge.testRule("1")
    test_workers[0].run()
    assert rules_host.bridge.state["test"]["status"] == "running"
    test_workers[1].run()
    assert [row["order"] for row in rules_host.bridge.state["test"]["rows"]] == ["#1", "#2"]


def test_showing_another_page_closes_the_panel(rules_host, test_workers):
    rules_host.bridge.testRule("1")
    rules_host.show_page("general")
    assert "test" not in rules_host.bridge.state
    test_workers[0].run()
    assert "test" not in rules_host.bridge.state
    assert rules_host.bridge.state["page"] == "general"


def test_a_rule_that_cannot_be_tested_starts_nothing(rules_host, test_workers):
    rules_host.bridge.testRule("2")  # its regex is marked
    rules_host.bridge.testRule("9")  # no such rule
    rules_host.show_page("general")
    rules_host.bridge.testRule("1")  # not on Rules
    assert test_workers == []
    assert "test" not in rules_host.bridge.state


def test_a_test_that_raises_shows_the_failed_panel_and_is_logged(
    rules_host, test_workers, monkeypatch, caplog
):
    def boom(rule, analysis_df, session):
        raise RuntimeError("engine fell over")

    monkeypatch.setattr("gui.settings.web_host.run_rule_test", boom)
    rules_host.bridge.testRule("1")
    test_workers[0].run()
    test = rules_host.bridge.state["test"]
    assert (test["status"], test["uid"]) == ("failed", "1")
    assert test["message"] == "The rule test didn’t finish. Details are in Logs."
    assert "engine fell over" in caplog.text


def test_focus_problem_opens_the_rule_before_it_asks_for_the_control(rules_host):
    key = rules_host.drafts["rules"].blocker_key()
    assert key == "rule-2-s0-c0-value"
    asked = []

    def on_focus(wanted):
        rows = rules_host.bridge.state["rules"]["groups"][0]["rows"]
        asked.append((wanted, [row["open"] for row in rows]))

    rules_host.bridge.problemFocusRequested.connect(on_focus)
    rules_host.focus_problem(key)
    # By the time the page is asked, the state that draws the control is out.
    assert asked == [(key, [False, True])]


def test_a_result_that_arrives_after_the_host_is_gone_raises_nothing(qtbot, test_workers):
    """The dialog closed while its test was still running."""
    drafts = {"rules": RulesDraft([_rule("VIP")], _analysis())}
    widget = SettingsWebHost(drafts, analysis_df=_analysis())
    widget.bridge.testRule("1")
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert not shiboken6.isValid(widget)

    test_workers[0].run()
```

- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_settings_web_host.py`
Expected: `13 passed, 12 errors`: every new test errors in its fixture with `'module' object at gui.settings.web_host has no attribute 'QThreadPool'`. The thirteen phase 7 tests still pass.

- [ ] **Step 3: Run the test on a worker, and reveal before focusing**

**Modify `gui/settings/web_host.py`.**
 Find exactly:

```python
"""The widget that shows the settings pages the web tier draws (phase 7 spec
section 6.5).

One web view for General, Orders mapping and Stock mapping. The window keeps
the three drafts in its page list, like any other page; this widget shows one
of them at a time, hands the page's edits to it, and says when it changed.
"""

import logging

from PySide6.QtCore import Signal
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QFileDialog, QVBoxLayout, QWidget

from gui.components import show_error
from gui.settings.bridge import mount_settings_page
from gui.settings.page_state import MappingDraft, read_file_columns

logger = logging.getLogger(__name__)


class SettingsWebHost(QWidget):
    """One web view and the drafts it draws, keyed "general", "orders", "stock".

    Signals:
        edited: a draft's values, or the file it reads columns from, changed
```

Replace with:

```python
"""The widget that shows the settings pages the web tier draws (phase 7 spec
section 6.5, phase 8 spec section 6.2).

One web view for General, Orders mapping, Stock mapping and Rules. The window
keeps the drafts in its page list, like any other page; this widget shows one
of them at a time, hands the page's edits to it, and says when it changed. It
also runs Test rule: on a worker, since one order rule over a whole analysis
can take seconds.
"""

import logging

from PySide6.QtCore import QThreadPool, Signal
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QFileDialog, QVBoxLayout, QWidget

from gui.components import show_error
from gui.settings.bridge import mount_settings_page
from gui.settings.page_state import MappingDraft, read_file_columns
from gui.settings.rule_test import failed_view, run_rule_test, running_view
from gui.settings.rules_state import RulesDraft
from gui.worker import Worker

logger = logging.getLogger(__name__)


def _tested(token: int, uid: str, rule: dict, analysis_df, session: str) -> tuple[int, dict]:
    """The test, as the worker thread runs it: (token, the panel's view).

    It never raises. A test that fails is a view too, so the one signal the
    host listens to always arrives.
    """
    try:
        view = run_rule_test(rule, analysis_df, session)
    except Exception:
        logger.exception("The rule test didn't finish")
        view = failed_view(rule, session)
    return token, {"uid": uid, **view}


class SettingsWebHost(QWidget):
    """One web view and the drafts it draws, keyed "general", "orders",
    "stock" and "rules".

    Signals:
        edited: a draft's values, or the file it reads columns from, changed
```

 Find exactly:

```python

    edited = Signal()

    def __init__(self, drafts: dict, parent=None):
        super().__init__(parent)
        self.drafts = drafts
        self._current = next(iter(drafts))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
```

Replace with:

```python

    edited = Signal()

    def __init__(self, drafts: dict, analysis_df=None, session: str = "", parent=None):
        super().__init__(parent)
        self.drafts = drafts
        self.analysis_df = analysis_df
        self.session = session
        self._current = next(iter(drafts))
        # The Test panel as the page draws it, or None. A test's result is
        # wanted only while its token is still the current one.
        self._test: dict | None = None
        self._test_token = 0
        # ponytail: every worker a test started, kept until the dialog goes.
        # Dropping one while it runs destroys its signals under it. A handful
        # per dialog; prune on `finished` if someone tests by the hundred.
        self._test_workers: list[Worker] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
```

 Find exactly:

```python

        self.bridge.editRequested.connect(self._on_edit)
        self.bridge.readColumnsRequested.connect(self._read_columns)
        self._push()

    def show_page(self, key: str) -> None:
        """Draw the draft under `key`."""
        self._current = key
        self._push()

    def focus_problem(self, key: str) -> None:
        """Put the operator on the control with this data-key."""
        self.view.setFocus()
        self.bridge.problemFocusRequested.emit(key)

    def _push(self) -> None:
        self.bridge.set_state(self.drafts[self._current].view())

    def _on_edit(self, action: str, args: list) -> None:
        if not self.drafts[self._current].apply(action, args):
```

Replace with:

```python

        self.bridge.editRequested.connect(self._on_edit)
        self.bridge.readColumnsRequested.connect(self._read_columns)
        self.bridge.testRequested.connect(self._start_test)
        self.bridge.testClosed.connect(self._close_test)
        self._push()

    def show_page(self, key: str) -> None:
        """Draw the draft under `key`. A Test panel does not follow."""
        self._current = key
        self._end_test()
        self._push()

    def focus_problem(self, key: str) -> None:
        """Put the operator on the control with this data-key. On Rules the
        control is drawn only while its rule is open, so that comes first."""
        if self.drafts[self._current].apply("reveal", [key]):
            self._push()
        self.view.setFocus()
        self.bridge.problemFocusRequested.emit(key)

    def _push(self) -> None:
        state = self.drafts[self._current].view()
        if self._test is not None:
            state = {**state, "test": self._test}
        self.bridge.set_state(state)

    def _start_test(self, uid: str) -> None:
        """Test... on a rule: show the panel, and run the rule on a worker."""
        draft = self.drafts[self._current]
        rule = draft.test_config(uid) if isinstance(draft, RulesDraft) else None
        if rule is None:
            # Not on Rules, or a rule the page draws Test... disabled for.
            return
        self._test_token += 1
        self._test = {"uid": uid, **running_view(rule, self.analysis_df, self.session)}
        self._push()
        worker = Worker(
            _tested, self._test_token, uid, rule, self.analysis_df, self.session
        )
        # A bound method, so the result is delivered on the GUI thread.
        worker.signals.result.connect(self._on_tested)
        self._test_workers.append(worker)
        QThreadPool.globalInstance().start(worker)

    def _on_tested(self, result) -> None:
        token, view = result
        if token != self._test_token or self._test is None:
            # The panel was closed, or another test took its place.
            return
        self._test = view
        self._push()

    def _end_test(self) -> bool:
        """Forget the panel and whatever result is still on its way."""
        self._test_token += 1
        showing = self._test is not None
        self._test = None
        return showing

    def _close_test(self) -> None:
        if self._end_test():
            self._push()

    def _on_edit(self, action: str, args: list) -> None:
        if not self.drafts[self._current].apply(action, args):
```

- [ ] **Step 4: Run the tests and the lint**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_settings_web_host.py tests/test_settings_footer.py`
Expected: all pass. (`49 passed`.)

Run: `.venv/bin/ruff check .`
Expected: `All checks passed!`

- [ ] **Step 5: Commit**

`/usr/bin/git add -A`, then write this message to a file under your job's tmp dir and commit with
`/usr/bin/git commit -F <that file>`. Subject: `Settings: the web host runs Test rule on a worker and reveals a blocked rule`. Body: one or two sentences: the token that drops a late result, and reveal before focus. End the message with the
attribution lines your session is given.

### Task 7: The dialog hosts the Rules draft; the Qt page and dialog go

**Files:**
- Modify: `gui/settings/window.py`, `gui/actions_handler.py`, `gui/rule_validator.py`
- Delete: `gui/settings/rules.py`, `gui/rule_test_dialog.py`, `tests/test_rules_page.py`,
  `tests/test_settings_page_rules.py`, `tests/test_rule_test_dialog.py`
- Test: `tests/test_settings_rules_window.py` (new), `tests/test_actions_handler.py`,
  `tests/audit/test_03_rule_engine.py`

**Interfaces:**
- Consumes: `RulesDraft` (Task 3); `SettingsWebHost(drafts, analysis_df=..., session=...)` (Task 6).
- Produces: `SettingsWindow(..., session_name=None)`; `WEB_PAGE_KEYS["Rules"] == "rules"`;
  `window._pages_by_name["Rules"]` is a `RulesDraft`.

Spec §3.1. `WEB_PAGE_KEYS` is what makes the rest work with no further change: the nav shows the host for
a page listed there, `_refresh_status` re-checks every page listed there on each web edit (so Rules' unsaved
mark and blocker follow an edit at once), and `_open_blocker` calls `focus_problem` for it.

The three deleted test files tested the Qt page and dialog. Their cases are in
`tests/test_settings_draft_rules.py` (Task 3) and `tests/test_rule_test.py` (Task 4). Four tests in
`tests/audit/test_03_rule_engine.py` built the Qt page or dialog; they are rewritten here against the draft
and `run_rule_test`, with the same assertions.

- [ ] **Step 1: Write the failing tests**

**Create `tests/test_settings_rules_window.py`:**

```python
"""Rules inside the settings window (phase 8 spec sections 3, 4.6 and 6.2).

Fixtures (window, started_workers, no_modals, make_settings_config) come from
conftest.py. The page is edited through the host's bridge, as the page does.
The fixture config holds one order rule, "Flag big orders": uid "1".
"""

from unittest.mock import Mock

import pandas as pd

from gui.settings.rules_state import RulesDraft
from gui.settings.window import SettingsWindow


def _rules(win):
    win._select_page("Rules")
    return win._web_host.bridge


def _rows(win):
    return [row for group in win._web_host.bridge.state["rules"]["groups"] for row in group["rows"]]


def test_rules_is_a_draft_the_web_host_draws(window):
    assert isinstance(window._pages_by_name["Rules"], RulesDraft)
    bridge = _rules(window)
    assert window.tab_widget.currentWidget() is window._web_host
    assert bridge.state["page"] == "rules"
    assert [row["name"] for row in _rows(window)] == ["Flag big orders"]


def test_a_rule_edit_marks_rules_unsaved_at_once(window):
    _rules(window).edit("rule_enabled", ["1", False])
    assert window._status_label.text() == "Unsaved changes in Rules"
    assert window.save_button.isEnabled()

    _rules(window).edit("rule_enabled", ["1", True])
    assert window._status_label.text() == ""
    assert not window.save_button.isEnabled()


def test_filtering_and_opening_a_rule_mark_nothing(window):
    bridge = _rules(window)
    bridge.edit("filter", ["big"])
    bridge.edit("open", ["1"])
    assert window._status_label.text() == ""
    assert not window.save_button.isEnabled()


def test_a_marked_rule_blocks_the_save_and_the_footers_link_opens_it(window):
    bridge = _rules(window)
    # "is greater than" needs a number.
    bridge.edit("cond_value", ["1", "0", "0", "many"])
    text = window._status_label.text()
    assert text.startswith('Fix rule “Flag big orders” in <a href="Rules"')
    assert text.endswith(">Rules</a> to save.")
    assert not window.save_button.isEnabled()

    window._select_page("General")
    asked = []
    window._web_host.bridge.problemFocusRequested.connect(asked.append)
    window._open_blocker("Rules")
    assert window._settings_nav.currentItem().text() == "Rules"
    assert [row["open"] for row in _rows(window)] == [True]
    assert asked == ["rule-1-s0-c0-value"]

    bridge.edit("cond_value", ["1", "0", "0", "7"])
    assert window._status_label.text() == "Unsaved changes in Rules"
    assert window.save_button.isEnabled()


def test_save_writes_a_rule_that_is_off(window, started_workers, no_modals):
    _rules(window).edit("rule_enabled", ["1", False])
    window.save_settings()
    assert no_modals == []
    _client, written = started_workers[0].args
    assert written["rules"] == [
        {
            "name": "Flag big orders",
            "priority": 1,
            "level": "order",
            "enabled": False,
            "steps": [
                {
                    "conditions": [
                        {"field": "item_count", "operator": "is greater than", "value": "5"}
                    ],
                    "match": "ALL",
                    "actions": [{"type": "ADD_ORDER_TAG", "value": "BULK"}],
                }
            ],
        }
    ]


def test_the_session_and_the_analysis_reach_test_rule(
    qapp, no_modals, started_workers, make_settings_config
):
    analysis = pd.DataFrame({"Order_Number": ["#1"], "SKU": ["A"], "Quantity": [9]})
    win = SettingsWindow(
        client_id="M",
        client_config=make_settings_config(),
        profile_manager=Mock(),
        analysis_df=analysis,
        session_name="2026-09-30_1",
    )
    try:
        assert win._web_host.session == "2026-09-30_1"
        assert win._web_host.analysis_df is analysis
        assert win._pages_by_name["Rules"].analysis_df is analysis
        win._select_page("Rules")
        assert _rows(win)[0]["can_test"] is True
    finally:
        win.deleteLater()


def test_with_no_session_test_rule_is_off_and_the_host_has_no_name(window):
    assert window._web_host.session == ""
    _rules(window)
    assert _rows(window)[0]["can_test"] is False
```

**Modify `tests/test_actions_handler.py`.**
 Find exactly:

```python
        analysis_results_df=None,
        orders_file_path=None,
        stock_file_path=None,
    )

    ActionsHandler(mw).open_settings_window()
```

Replace with:

```python
        analysis_results_df=None,
        orders_file_path=None,
        stock_file_path=None,
        session_path=None,
    )

    ActionsHandler(mw).open_settings_window()
```

 Find exactly:

```python
        analysis_results_df=None,
        orders_file_path="/data/orders.csv",
        stock_file_path=None,
    )

    ActionsHandler(mw).open_settings_window(page="Orders mapping")

    assert seen["loaded_files"] == {"orders": "/data/orders.csv", "stock": None}
    assert seen["initial_page"] == "Orders mapping"
    # The main window is the dialog's parent: left alone, every open would
    # leave a dialog and its web view alive (ADR 0016).
    assert deleted == [True]


def test_the_writeoff_bypass_is_gone():
```

Replace with:

```python
        analysis_results_df=None,
        orders_file_path="/data/orders.csv",
        stock_file_path=None,
        session_path="/server/Sessions/CLIENT_M/2026-09-30_1",
    )

    ActionsHandler(mw).open_settings_window(page="Orders mapping")

    assert seen["loaded_files"] == {"orders": "/data/orders.csv", "stock": None}
    assert seen["initial_page"] == "Orders mapping"
    # Test rule names the analysis it ran against by the session's folder.
    assert seen["session_name"] == "2026-09-30_1"
    # The main window is the dialog's parent: left alone, every open would
    # leave a dialog and its web view alive (ADR 0016).
    assert deleted == [True]


def test_with_no_session_the_settings_window_gets_no_session_name(monkeypatch):
    seen = {}

    def window(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(exec=lambda: False, deleteLater=lambda: None)

    monkeypatch.setattr("gui.actions_handler.SettingsWindow", window)
    profile_manager = Mock()
    profile_manager.load_shopify_config.return_value = {"settings": {}}
    mw = SimpleNamespace(
        current_client_id="M",
        profile_manager=profile_manager,
        analysis_results_df=None,
        orders_file_path=None,
        stock_file_path=None,
        session_path=None,
    )

    ActionsHandler(mw).open_settings_window()

    assert seen["session_name"] is None


def test_the_writeoff_bypass_is_gone():
```

- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_settings_rules_window.py tests/test_actions_handler.py`
Expected: `8 failed, 23 passed`: six of the seven tests in `tests/test_settings_rules_window.py` (Rules is still the Qt page, and `SettingsWindow` takes no `session_name`), and in `tests/test_actions_handler.py` `test_the_settings_window_is_told_which_files_are_loaded` and `test_with_no_session_the_settings_window_gets_no_session_name` (`KeyError: 'session_name'`). `test_filtering_and_opening_a_rule_mark_nothing` passes already: the Qt page ignores those edits.

- [ ] **Step 3: Put the draft in the dialog**

**Modify `gui/settings/window.py`.**
 Find exactly:

```python
    read_file_columns,
)
from gui.settings.reports import ReportsPage
from gui.settings.rules import RulesPage
from gui.settings.sets import SetsPage
from gui.settings.web_host import SettingsWebHost
from gui.settings.weight import WeightPage
```

Replace with:

```python
    read_file_columns,
)
from gui.settings.reports import ReportsPage
from gui.settings.rules_state import RulesDraft
from gui.settings.sets import SetsPage
from gui.settings.web_host import SettingsWebHost
from gui.settings.weight import WeightPage
```

 Find exactly:

```python
    "Tag categories": ["tags", "labels", "colours", "colors", "writeoff", "sku"],
}

# Nav name -> the key SettingsWebHost draws that page under (phase 7). Every
# other page is a Qt widget.
WEB_PAGE_KEYS: dict[str, str] = {
    "General": "general",
    "Orders mapping": "orders",
    "Stock mapping": "stock",
}
```

Replace with:

```python
    "Tag categories": ["tags", "labels", "colours", "colors", "writeoff", "sku"],
}

# Nav name -> the key SettingsWebHost draws that page under (phases 7 and 8).
# Every other page is a Qt widget.
WEB_PAGE_KEYS: dict[str, str] = {
    "General": "general",
    "Orders mapping": "orders",
    "Stock mapping": "stock",
    "Rules": "rules",
}
```

 Find exactly:

```python
        parent=None,
        initial_page=None,
        loaded_files=None,
    ):
        """Initializes the SettingsWindow.
```

Replace with:

```python
        parent=None,
        initial_page=None,
        loaded_files=None,
        session_name=None,
    ):
        """Initializes the SettingsWindow.
```

 Find exactly:

```python
            loaded_files (dict, optional): {"orders": path, "stock": path} for
                the files loaded on Setup. A mapping page opens with that
                file's columns. Defaults to None.
        """
        super().__init__(parent)
        self._initial_page = initial_page
```

Replace with:

```python
            loaded_files (dict, optional): {"orders": path, "stock": path} for
                the files loaded on Setup. A mapping page opens with that
                file's columns. Defaults to None.
            session_name (str, optional): The open session's folder name.
                Test rule says which analysis it ran against. Defaults to
                None.
        """
        super().__init__(parent)
        self._initial_page = initial_page
```

 Find exactly:

```python
        self._pages_by_name: dict[str, PageContract] = {}
        self._unsaved: set[str] = set()

        # The three pages the web tier draws are drafts: pages with no widget.
        # One host widget shows whichever of them the nav selects.
        client = str(self.client_id)
        column_mappings = self.config_data.get("column_mappings", {})
        drafts = {
```

Replace with:

```python
        self._pages_by_name: dict[str, PageContract] = {}
        self._unsaved: set[str] = set()

        # The pages the web tier draws are drafts: pages with no widget. One
        # host widget shows whichever of them the nav selects.
        client = str(self.client_id)
        column_mappings = self.config_data.get("column_mappings", {})
        drafts = {
```

 Find exactly:

```python
            "stock": StockDraft(
                column_mappings, client, file=self._loaded_file(loaded_files, "stock")
            ),
        }
        self._web_host = SettingsWebHost(drafts)
        self._web_host.edited.connect(self._on_web_edit)

        # Create all tabs (unchanged call order/method names)
        self._add_page(drafts["general"], "General", self._web_host)
        self._add_page(
            RulesPage(
                self.config_data.get("rules", []),
                self.analysis_df,
                tag_categories=self.config_data.get("tag_categories", {}),
            ),
            "Rules",
        )
        self._add_page(
            ReportsPage(
                self.config_data.get("packing_list_configs", []),
```

Replace with:

```python
            "stock": StockDraft(
                column_mappings, client, file=self._loaded_file(loaded_files, "stock")
            ),
            "rules": RulesDraft(
                self.config_data.get("rules", []),
                self.analysis_df,
                tag_categories=self.config_data.get("tag_categories", {}),
            ),
        }
        self._web_host = SettingsWebHost(
            drafts, analysis_df=self.analysis_df, session=session_name or ""
        )
        self._web_host.edited.connect(self._on_web_edit)

        # Create all tabs (unchanged call order/method names)
        self._add_page(drafts["general"], "General", self._web_host)
        self._add_page(drafts["rules"], "Rules", self._web_host)
        self._add_page(
            ReportsPage(
                self.config_data.get("packing_list_configs", []),
```

- [ ] **Step 4: Pass the session's name**

**Modify `gui/actions_handler.py`.**
 Find exactly:

```python
                "orders": self.mw.orders_file_path,
                "stock": self.mw.stock_file_path,
            },
        )

        saved = settings_win.exec()
```

Replace with:

```python
                "orders": self.mw.orders_file_path,
                "stock": self.mw.stock_file_path,
            },
            # Test rule names the analysis it ran against.
            session_name=os.path.basename(self.mw.session_path)
            if self.mw.session_path
            else None,
        )

        saved = settings_win.exec()
```

- [ ] **Step 5: Delete the Qt page, the dialog and their tests**

**Delete `gui/settings/rules.py`** (`/usr/bin/git rm gui/settings/rules.py`).

**Delete `gui/rule_test_dialog.py`** (`/usr/bin/git rm gui/rule_test_dialog.py`).

**Delete `tests/test_rules_page.py`** (`/usr/bin/git rm tests/test_rules_page.py`).

**Delete `tests/test_settings_page_rules.py`** (`/usr/bin/git rm tests/test_settings_page_rules.py`).

**Delete `tests/test_rule_test_dialog.py`** (`/usr/bin/git rm tests/test_rule_test_dialog.py`).

- [ ] **Step 6: Point what named them at what replaced them**

**Modify `gui/rule_validator.py`.**
 Find exactly:

```python
def condition_error(operator: str, value: str) -> str | None:
    """The error the Rules page shows in red for this condition, or None.

    RulesPage._perform_validation marks red exactly this, and Save refuses
    it, so the two can't disagree (AUDIT-03-5).
    """
    if operator in ("matches regex", "does not match regex"):
        ok, msg = validate_regex(value)
```

Replace with:

```python
def condition_error(operator: str, value: str) -> str | None:
    """The error the Rules page shows in red for this condition, or None.

    RulesDraft (gui/settings/rules_state.py) marks red exactly this, and Save
    refuses it, so the two can't disagree (AUDIT-03-5).
    """
    if operator in ("matches regex", "does not match regex"):
        ok, msg = validate_regex(value)
```

**Modify `tests/audit/test_03_rule_engine.py`.**
 Find exactly:

```python
import pandas as pd
import pytest

from gui.rule_test_dialog import RuleTestDialog
from gui.rule_validator import validate_range
from gui.settings.rules import RulesPage
from shopify_tool import core
from shopify_tool.report_filters import fulfillable_only
from shopify_tool.rules import (
```

Replace with:

```python
import pandas as pd
import pytest

from gui.rule_validator import validate_range
from gui.settings.rule_test import run_rule_test
from gui.settings.rules_state import RulesDraft
from shopify_tool import core
from shopify_tool.report_filters import fulfillable_only
from shopify_tool.rules import (
```

 Find exactly:

```python
    assert not result.any()


def test_rules_page_refuses_to_save_an_invalid_rule(qtbot):
    bad = rule([cond("SKU", "matches regex", "(")], [tag("X")], level="article")
    page = RulesPage([bad], pd.DataFrame({"Order_Number": ["#1"], "SKU": ["A"]}))
    qtbot.addWidget(page)

    ok, _errors = page.validate()
    assert not ok
```

Replace with:

```python
    assert not result.any()


def test_rules_page_refuses_to_save_an_invalid_rule():
    bad = rule([cond("SKU", "matches regex", "(")], [tag("X")], level="article")
    page = RulesDraft([bad], pd.DataFrame({"Order_Number": ["#1"], "SKU": ["A"]}))

    ok, _errors = page.validate()
    assert not ok
```

 Find exactly:

```python
    assert a == b


def test_rule_test_dialog_reports_rows_the_saved_rule_already_tagged(qtbot, no_modals):
    r = rule([cond("SKU", "equals", "A")], [tag("T")], level="article")
    # What the dialog is given: the results of a run that already applied r.
    analysed = RuleEngine([r]).apply(frame([("#1", "A", 1), ("#2", "B", 1)]))

    dialog = RuleTestDialog(r, analysed)
    qtbot.addWidget(dialog)
    assert dialog.matched_count == 1


@pytest.mark.parametrize("value", ["100-10", "-10-0"])
```

Replace with:

```python
    assert a == b


def test_rule_test_reports_orders_the_saved_rule_already_tagged():
    r = rule([cond("SKU", "equals", "A")], [tag("T")], level="article")
    # What the test is given: the results of a run that already applied r.
    analysed = RuleEngine([r]).apply(frame([("#1", "A", 1), ("#2", "B", 1)]))

    assert run_rule_test(r, analysed)["matched"] == "1"


@pytest.mark.parametrize("value", ["100-10", "-10-0"])
```

 Find exactly:

```python
    assert validate_range(value)[0] is (_parse_range(value) is not None)


def test_rule_test_config_keeps_add_product_quantity(qtbot):
    r = rule([cond("SKU", "equals", "A")],
             [{"type": "ADD_PRODUCT", "sku": "GIFT", "quantity": 3}], level="article")
    page = RulesPage([r], pd.DataFrame({"Order_Number": ["#1"], "SKU": ["A"]}))
    qtbot.addWidget(page)

    tested = page._build_rule_config_from_widgets(page.rule_widgets[0])
    assert tested["steps"][0]["actions"][0].get("quantity") == 3
```

Replace with:

```python
    assert validate_range(value)[0] is (_parse_range(value) is not None)


def test_rule_test_config_keeps_add_product_quantity():
    r = rule([cond("SKU", "equals", "A")],
             [{"type": "ADD_PRODUCT", "sku": "GIFT", "quantity": 3}], level="article")
    page = RulesDraft([r], pd.DataFrame({"Order_Number": ["#1"], "SKU": ["A"]}))

    tested = page.test_config("1")
    assert tested["steps"][0]["actions"][0].get("quantity") == 3
```

 Find exactly:

```python
    assert tags_by_order(RuleEngine([r]).apply(df)) == {"#1": []}


def test_rules_page_shows_rules_in_execution_order(qtbot):
    second = rule([cond("SKU", "equals", "A")], [tag("X")], level="article", name="runs second", priority=2)
    first = rule([cond("SKU", "equals", "A")], [tag("Y")], level="article", name="runs first", priority=1)
    page = RulesPage([second, first], pd.DataFrame({"Order_Number": ["#1"], "SKU": ["A"]}))
    qtbot.addWidget(page)

    engine_order = [r["name"] for r in RuleEngine([second, first]).rules]
    shown = [w["name_edit"].text() for w in page.rule_widgets]
    assert shown == engine_order
```

Replace with:

```python
    assert tags_by_order(RuleEngine([r]).apply(df)) == {"#1": []}


def test_rules_page_shows_rules_in_execution_order():
    second = rule([cond("SKU", "equals", "A")], [tag("X")], level="article", name="runs second", priority=2)
    first = rule([cond("SKU", "equals", "A")], [tag("Y")], level="article", name="runs first", priority=1)
    page = RulesDraft([second, first], pd.DataFrame({"Order_Number": ["#1"], "SKU": ["A"]}))

    engine_order = [r["name"] for r in RuleEngine([second, first]).rules]
    shown = [row["name"] for group in page.view()["rules"]["groups"] for row in group["rows"]]
    assert shown == engine_order
```

- [ ] **Step 7: Check nothing else names what was deleted**

Use the Grep tool for `RulesPage|RuleTestDialog|rule_test_dialog|settings\.rules import|rule_widgets` over
`gui`, `shopify_tool`, `shared`, `tests` and the repo root's `*.py`.
Expected: no match. (`docs/` still names them in old specs and plans; leave those.)

- [ ] **Step 8: Run the window's tests, then the whole suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_settings_rules_window.py tests/test_actions_handler.py tests/audit/test_03_rule_engine.py tests/test_settings_roundtrip.py tests/test_settings_footer.py tests/test_settings_unsaved.py tests/test_settings_nav.py tests/test_settings_entry_points.py`
Expected: all pass. (`137 passed`.)

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: `3 failed, 3412 passed`: the three baseline failures in `tests/test_label_printing.py` and nothing else.

Run: `.venv/bin/ruff check .`
Expected: `All checks passed!`

- [ ] **Step 9: Commit**

`/usr/bin/git add -A`, then write this message to a file under your job's tmp dir and commit with
`/usr/bin/git commit -F <that file>`. Subject: `Settings: Rules is a web page in the dialog; the Qt editor and Test dialog are deleted`. Body: two or three sentences: Rules joins the web host, the session name reaches Test rule, and which files and tests went and where their cases live now. End the message with the
attribution lines your session is given.

### Task 8: Renders, docs and the gate

**Files:**
- Create: PNGs under `docs/design/ui-refresh/renders/phase8/`
- Modify: `docs/design/ui-refresh/roadmap.md`, `CONTEXT.md`

- [ ] **Step 1: Render the dialog and look at it**

Write this throwaway script as `<your tmp dir>/render_settings.py`:

```python
"""Throwaway: render the Client settings dialog's Rules page in its phase 8 states.

    QT_QPA_PLATFORM=offscreen PYTHONPATH=. .venv/bin/python render_settings.py <out dir>
"""

import copy
import os
import sys
import time
from pathlib import Path
from unittest.mock import Mock

os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")

import pandas as pd
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from gui.settings.window import SettingsWindow
from gui.theme_manager import get_theme_manager

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)


def step(conditions, actions, match="ALL"):
    return {"conditions": conditions, "match": match, "actions": actions}


def cond(field, operator, value=""):
    return {"field": field, "operator": operator, "value": value}


RULES = [
    {
        "name": "VIP priority",
        "level": "article",
        "steps": [
            step(
                [cond("Tags", "contains", "VIP")],
                [{"type": "ADD_INTERNAL_TAG", "value": "priority"}],
            )
        ],
    },
    {
        "name": "Samples get a card",
        "level": "article",
        "steps": [
            step(
                [cond("SKU", "starts with", "SMP-"), cond("SKU", "in list", "TEE-01, MUG-02")],
                [{"type": "ADD_PRODUCT", "sku": "CARD-THANKS", "quantity": 1}],
                match="ANY",
            ),
            step(
                [cond("Quantity", "is greater than", "3")],
                [{"type": "ADD_INTERNAL_TAG", "value": "bulk-sample"}],
            ),
        ],
    },
    {
        "name": "Heavy parcels",
        "level": "order",
        "steps": [
            step(
                [cond("total_quantity", "is greater than", "20"), cond("has_sku", "equals", "GIFT")],
                [
                    {"type": "ADD_INTERNAL_TAG", "value": "heavy"},
                    {
                        "type": "CALCULATE",
                        "operation": "multiply",
                        "field1": "Quantity",
                        "field2": "Stock",
                        "target": "Load",
                    },
                ],
            )
        ],
    },
    {
        "name": "Hold international samples",
        "level": "order",
        "enabled": False,
        "steps": [
            step(
                [cond("Destination_Country", "does not equal", "GB")],
                [
                    {"type": "SET_STATUS", "value": "Not Fulfillable"},
                    {"type": "ADD_TAG", "value": "hold"},
                ],
            )
        ],
    },
]

CONFIG = {
    "settings": {"stock_csv_delimiter": "auto", "orders_csv_delimiter": "auto", "low_stock_threshold": 5},
    "rules": RULES,
    "packing_list_configs": [],
    "stock_export_configs": [],
    "column_mappings": {
        "version": 2,
        "orders": {
            "Name": "Order_Number",
            "Lineitem sku": "SKU",
            "Lineitem quantity": "Quantity",
            "Shipping Method": "Shipping_Method",
        },
        "stock": {"Артикул": "SKU", "Наличност": "Stock"},
        "additional_columns": [],
    },
    "courier_mappings": {},
    "set_decoders": {},
    "weight_config": {"volumetric_divisor": 5000, "products": {}, "boxes": []},
    "tag_categories": {
        "version": 2,
        "categories": {
            "handling": {"label": "Handling", "color": "#C0392B", "tags": ["priority", "heavy"], "order": 1}
        },
    },
}

ANALYSIS = pd.DataFrame(
    {
        "Order_Number": [f"#{10480 + n // 2}" for n in range(40)],
        "SKU": ["SMP-TEE-01", "ACM-MUG-WHT"] * 20,
        "Quantity": [1, 30] * 20,
        "Stock": [10] * 40,
        "Tags": ["VIP, repeat", ""] * 10 + ["", ""] * 10,
        "Destination_Country": ["GB", "DE"] * 20,
        "Order_Fulfillment_Status": ["Fulfillable"] * 40,
        "System_note": [""] * 40,
        "Status_Note": [""] * 40,
        "Internal_Tags": ["[]"] * 40,
    }
)


def settle(ms=500):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def window(rules=None, analysis=ANALYSIS):
    config = copy.deepcopy(CONFIG)
    if rules is not None:
        config["rules"] = rules
    profile_manager = Mock()
    profile_manager.load_client_config.return_value = {}
    win = SettingsWindow(
        client_id="ACME",
        client_config=config,
        profile_manager=profile_manager,
        analysis_df=analysis,
        session_name="2026-09-30_1",
    )
    win.resize(1180, 760)
    win.show()
    win._select_page("Rules")
    settle(1500)
    return win


def shot(win, name, theme):
    settle()
    win.grab().save(str(OUT / f"{theme}-{name}.png"))


def edit(win, action, args):
    win._web_host.bridge.edit(action, args)


def close(win):
    win.done(0)
    win.deleteLater()


app = QApplication(sys.argv)
manager = get_theme_manager()
started_as = manager.get_current_theme_name()
for theme in ("light", "dark"):
    manager.set_theme(theme)
    # set_theme does nothing when the theme is already the current one, and
    # only apply_theme puts the app's stylesheet on a bare QApplication.
    manager.apply_theme()

    win = window()
    shot(win, "rules", theme)
    edit(win, "open", ["3"])
    shot(win, "rules-open", theme)
    edit(win, "open", ["2"])
    shot(win, "rules-steps", theme)
    edit(win, "open", ["1"])
    edit(win, "cond_operator", ["1", "0", "0", "matches regex"])
    edit(win, "cond_value", ["1", "0", "0", "("])
    shot(win, "rules-problem", theme)
    close(win)

    win = window()
    win._web_host.bridge.testRule("1")
    deadline = time.monotonic() + 20
    while win._web_host.bridge.state.get("test", {}).get("status") != "done":
        assert time.monotonic() < deadline, "the test never finished"
        settle(50)
    shot(win, "rules-test", theme)
    close(win)

    win = window(rules=[])
    shot(win, "rules-empty", theme)
    close(win)

# set_theme stores the choice for this PC: put back what it was.
manager.set_theme(started_as)
print(sorted(p.name for p in OUT.iterdir()))
```

Run, from the repo root:
`QT_QPA_PLATFORM=offscreen PYTHONPATH=. .venv/bin/python <your tmp dir>/render_settings.py <your tmp dir>/renders`

It writes twelve PNGs (six states, two themes). Read each with the Read tool and compare with the mockup's
Rules, Rules empty and Test rule states (open `docs/design/ui-refresh/mockups/client-settings.html` as its
README describes). Check, in both themes:

- `*-rules.png`: the Rules nav row is open. One card: a filter field with a magnifier on the left, "4 rules
  · 3 on" on the right. Two group lines, "Article rules" and "Order rules", each with its note. Four rows:
  a six-dot grip, a switch, the number in mono, the name in bold, then When and Then lines whose values are
  mono chips. On the right of each row: "Test…", an up and a down chevron, and three dots. The second rule
  has four lines, labelled When, Then, And when, Then. The fourth rule's switch is off, it carries an "Off"
  badge, and its name and lines are in the secondary colour. A move button at a group's edge is greyed, with
  no box around it.
- `*-rules-open.png`: the third rule is open. Its name is a field. Under it: "Level" with Article / Order
  segments (Order chosen) and its hint; "When" with All / Any segments and "of these match", then two rows
  of field, operator, value and ✕, then "Add condition"; "Then" with two action rows, the second
  (Calculate) wrapping its target onto a second line with "→" before it, then "Add action"; then "Add step"
  on the left and "Done" on the right. The other rules are still collapsed around it.
- `*-rules-steps.png`: the second rule is open. "Step 1" and "Step 2" headings, each over a hairline;
  Step 2 reads "Checks only the lines step 1 matched." and has "Remove step" on its right in the danger
  colour. Step 1's second condition has "2 items" under it. The bonus line row shows "×" before a small
  right-aligned quantity.
- `*-rules-problem.png`: the first rule is open, its value field has a danger edge, and "Invalid regex
  syntax" sits under the row with the alert glyph. Its "Test…" is disabled. The Rules nav row carries the
  alert and the unsaved dot. The footer reads "Fix rule “VIP priority” in Rules to save." in the danger
  colour with the page name underlined, and Save is disabled.
- `*-rules-test.png`: the page is dimmed and the panel sits over it: the title "Test “VIP priority”", a ✕,
  the sentence naming `2026-09-30_1` in mono, "10 of 20 orders match" with the number large and mono, a
  table with the heads Order / Matched on / Change and five rows whose Change is in the success colour,
  "and 5 more", and Close. The nav and the footer are not dimmed.
- `*-rules-empty.png`: the page head has no button. One card, centred: a glyph in a small raised tile, "No
  rules yet", the sentence, and a filled "Add rule".

If anything differs from the mockup beyond the departures in spec §10, fix the CSS, re-run Task 5's tests,
and render again.

Copy nine of the PNGs into the repo with the Bash tool (`mkdir -p docs/design/ui-refresh/renders/phase8`,
then `cp`): `light-rules.png`, `light-rules-empty.png`, `light-rules-open.png`, `light-rules-problem.png`,
`light-rules-steps.png`, `light-rules-test.png`, `dark-rules.png`, `dark-rules-open.png`,
`dark-rules-test.png`. Delete the script and the rest.

- [ ] **Step 2: Update the roadmap and the glossary**

**Modify `docs/design/ui-refresh/roadmap.md`.**
 Find exactly:

```markdown
choices and the low-stock threshold. Orders mapping and Stock mapping follow the mockup's "Orders mapping"
state. The pages not ported yet keep their Qt widgets inside the same dialog until 8 and 9 land.

### 8. Client settings on the web tier: Rules and Test rule

The rule list with toggles and reordering. The empty state, which replaces today's "No rules defined". Test
rule. This is the largest single editor (`gui/settings/rules.py`, about 1,500 lines). Split it again at its
own Stage A if it does not fit one PR. The page joins the settings document phase 7 built
(`gui/web/settings.*`), with its values in a draft (`gui/settings/page_state.py`).

### 9. Client settings on the web tier: Sets, Weight, Reports, Tag categories
```

Replace with:

```markdown
choices and the low-stock threshold. Orders mapping and Stock mapping follow the mockup's "Orders mapping"
state. The pages not ported yet keep their Qt widgets inside the same dialog until 8 and 9 land.

### 8. Client settings on the web tier: Rules and Test rule (built in run 56)

Spec: `docs/superpowers/specs/2026-10-02-ui-refresh-phase8-rules-web-design.md`.
Plan: `docs/superpowers/plans/2026-10-02-ui-refresh-phase8-rules-web.md`.

Built as listed below, with these differences. It fitted one PR. The mockup stops at "Edit": a rule's row
opens in place into an editor that is its summary with the words turned into controls. Article rules always
run before order rules, so a client with both sees two labelled groups, and up, down and the grip stop at a
group's edge. All three are off while a filter is on. A rule gained `enabled` (written only when it is off);
the analysis skips a rule that is off and Test still runs it. A row that is off is drawn in secondary text,
not at 60% opacity (ADR 0001). Fields keep the analysis's own names, and the seven real actions get plain
labels; the status action is "Hold the order". Test runs on a worker over the whole analysis, dims the page
area only until phase 10, and says "No change" for an order the saved rules already changed. The date picker
and the suggestion lists are Chromium's own. `shared/theme.py` gained the `scrim` token and the
`--color-scheme` variable. The page has its own script, `gui/web/settings_rules.js`, and its values are in
`gui/settings/rules_state.py`.

The rule list with toggles and reordering. The empty state, which replaces "No rules defined". Test rule.
The Qt editor (`gui/settings/rules.py`, about 1,500 lines) and its Test dialog are deleted. The page joins
the settings document phase 7 built (`gui/web/settings.*`).

### 9. Client settings on the web tier: Sets, Weight, Reports, Tag categories
```

**Modify `CONTEXT.md`.**
 Find exactly:

```markdown
**Article rule** / **Order rule** — a rule whose conditions test one order
line at a time, or the whole order. Article rules run before order rules.

**Negative operator** — `does not equal`, `does not contain`, `not in list`,
`not between`, `does not match regex`. On an order rule it means *no line*
matches the positive form, whatever the field.
```

Replace with:

```markdown
**Article rule** / **Order rule** — a rule whose conditions test one order
line at a time, or the whole order. Article rules run before order rules.

**Off rule** — a rule kept in the profile that the analysis skips: its
`enabled` is false. A rule with no such key is on. A rule test still runs an
off rule.

**Rule test** — one rule, as edited, run on a copy of the open session's
analysis. It counts the orders that match and says what the rule would change
on the first few. It changes nothing. The analysis it runs on already has the
saved rules applied, so an order they changed reads "No change".

**Negative operator** — `does not equal`, `does not contain`, `not in list`,
`not between`, `does not match regex`. On an order rule it means *no line*
matches the positive form, whatever the field.
```

- [ ] **Step 3: The gate**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: `3 failed, 3412 passed`: the three baseline failures in `tests/test_label_printing.py` and nothing else.

Run: `.venv/bin/ruff check .`
Expected: `All checks passed!`

- [ ] **Step 4: Commit**

`/usr/bin/git add -A`, then write this message to a file under your job's tmp dir and commit with
`/usr/bin/git commit -F <that file>`. Subject: `Docs: phase 8 as built, the Off rule and Rule test terms, and the renders`. Body: one sentence. End the message with the
attribution lines your session is given.


- [ ] **Step 5: What the PR must say**

The PR body, written at Stage C, has to carry three facts from this plan:

- `shared/theme.py` gains the `scrim` token and the `--color-scheme` variable. Packing Tool gets both at its
  next sync and needs no work.
- A PC still on an older version ignores `enabled` and runs a rule that is off, until it updates.
- Test rule now runs on the whole analysis; before the release, try it over RDP on the largest real
  session, since an order rule takes about a second per 2,000 orders.
