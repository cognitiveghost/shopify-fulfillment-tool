# Phase 9 Bundle 1 — Foundations Implementation Plan

> **For agentic workers:** implement this **in your own session**, task by
> task, in the order given. Do **not** dispatch subagents — this pipeline runs
> one stage per run and a subagent re-establishes context you already hold.

**Goal:** Ship the theme-repaint fix, the F0/F0b token retune, the F1 border
subtraction and the F3 control corrections as one cycle across both repos.

**Architecture:** Almost everything lands in `shared/theme.py` and its
`build_stylesheet()`. `shared/` is owned by `packing-tool`, so each shared
change is authored there and arrives here through `scripts/sync_shared.py`.
Two PRs, `packing-tool` first.

**Tech Stack:** Python 3, PySide6 (Qt 6.11.1), pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-09-03-phase9-bundle1-foundations-design.md`
**Decisions:** `docs/adr/0002-themed-glyphs-in-qss-image-properties.md`,
`docs/adr/0003-theme-restyling-is-a-closure-not-a-repolish.md`

## Global Constraints

- **`shared/` is never hand-edited in this repo.** Author in
  `../packing-tool`, then run `python scripts/sync_shared.py
  /home/cognitiveghost/Desktop/Projects/packing-tool` from this repo's root.
  The bare sibling default resolves to `.claude/worktrees/packing-tool` from a
  worktree and does not exist — always pass the path.
- **Token names and roles are frozen.** ~180 call sites read them by exact
  attribute name. Values move; names never do.
- **The dark elevation ramp does not move.** All four dark planes stay as
  shipped. Light nests downward, dark upward.
- **No hardcoded colours in stylesheets.** Every colour comes from a token.
- Run tests as `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest` (or
  `scripts/run_tests.sh`). Bare `python` and `ruff` are not on PATH — use
  `.venv/bin/`.
- Commit after each task. Branch only; never push to `main`.

## Worktrees

- **shopify:** `.claude/worktrees/phase9-bundle1-foundations`, branch
  `worktree-phase9-bundle1-foundations` (already created — you are in it).
- **packing-tool:** create at Task 1 as
  `../packing-tool/.claude/worktrees/phase9-bundle1-foundations`, branch
  `worktree-phase9-bundle1-foundations`.

## Order is load-bearing

Task 2 (the repaint fix) must land **before** Task 4 (the retune). The retune
changes every colour in the app, which is exactly what turns a stale value
into a visible artifact; fixing the cache afterwards means debugging both at
once.

## If you run out of room

Tasks 1–6 are a coherent, shippable unit on their own (repaint + 9.1 + 9.2).
If you cannot finish Tasks 7–9 (9.5) this run, **stop after Task 6**, commit,
and leave `next_stage: B` in `state.md` rather than opening a partial PR.

---

### Task 1: Create the packing-tool worktree

**Files:** none changed.

- [ ] **Step 1: Create it**

```bash
git -C /home/cognitiveghost/Desktop/Projects/packing-tool fetch origin
git -C /home/cognitiveghost/Desktop/Projects/packing-tool worktree add \
  -b worktree-phase9-bundle1-foundations \
  .claude/worktrees/phase9-bundle1-foundations origin/main
```

- [ ] **Step 2: Give it a venv**

```bash
cd /home/cognitiveghost/Desktop/Projects/packing-tool/.claude/worktrees/phase9-bundle1-foundations && ./scripts/setup_venv.sh
```

If `packing-tool` has no `setup_venv.sh`, symlink the main checkout's `.venv`.

- [ ] **Step 3: Confirm the baseline is green**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: all pass. If not, stop — you are not starting from a clean base.

---

### Task 2: `on_theme_changed` in shared

**Files:**
- Modify: `packing-tool/shared/theme.py` (add beside `set_current`, ~line 250)
- Test: `packing-tool/tests/test_theme_notifier.py`

**Interfaces:**
- Consumes: `theme_notifier` (`_ThemeNotifier.changed = Signal(str)`),
  `current_tokens() -> ThemeTokens`, both already in `shared/theme.py`.
- Produces: `on_theme_changed(widget, apply) -> None`. `apply` is called as
  `apply(tokens: ThemeTokens)`, immediately and on every subsequent
  `theme_notifier.changed`, until `widget` is destroyed.

Read ADR 0003 before starting. The short version: `unpolish()`/`polish()` is
**not** the fix and must not be written — it was measured and it repairs
nothing. The fault is a stylesheet *string* interpolated once at build time.

- [ ] **Step 1: Write the failing test**

In `packing-tool/tests/test_theme_notifier.py`:

```python
def test_on_theme_changed_reruns_the_closure(qapp):
    from PySide6.QtWidgets import QLabel
    from shared.theme import on_theme_changed, set_current

    set_current("light")
    label = QLabel()
    on_theme_changed(label, lambda t: label.setStyleSheet(f"color: {t.text};"))
    first = label.styleSheet()
    assert first  # applied immediately, not only on the next change

    set_current("dark")
    assert label.styleSheet() != first


def test_on_theme_changed_stops_when_the_widget_dies(qapp):
    from PySide6.QtWidgets import QLabel
    from shared.theme import on_theme_changed, set_current, theme_notifier

    set_current("light")
    label = QLabel()
    on_theme_changed(label, lambda t: label.setStyleSheet(f"color: {t.text};"))
    before = theme_notifier.receivers(theme_notifier.changed)

    label.deleteLater()
    qapp.processEvents()
    assert theme_notifier.receivers(theme_notifier.changed) < before
```

- [ ] **Step 2: Run it and watch it fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_theme_notifier.py -v`
Expected: FAIL — `ImportError: cannot import name 'on_theme_changed'`.

- [ ] **Step 3: Implement it**

In `shared/theme.py`, directly after `current_tokens()`:

```python
def on_theme_changed(widget, apply) -> None:
    """Run `apply(tokens)` now, and again whenever the rendering inputs change.

    A widget that styles itself with an interpolated string --
    `setStyleSheet(f"color: {tokens.text}")` -- bakes that hex in at build time
    and keeps it forever. Qt re-polishes the tree on an application stylesheet
    change, but re-polishing re-applies the same stale literal, so the fix is
    to re-run the recipe rather than to re-polish. See ADR 0003, which records
    the measurement.

    The connection is dropped when `widget` is destroyed. Without that, a
    closure holding a freed QWidget is called on the next toggle and Qt raises
    "Internal C++ object already deleted".
    """
    apply(current_tokens())

    def _reapply(_name: str) -> None:
        apply(current_tokens())

    theme_notifier.changed.connect(_reapply)
    widget.destroyed.connect(lambda *_: theme_notifier.changed.disconnect(_reapply))
```

Add `"on_theme_changed"` to `__all__` if the module defines one.

- [ ] **Step 4: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_theme_notifier.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add shared/theme.py tests/test_theme_notifier.py
git commit -m "Bundle 1: a widget re-styles by re-running its closure"
```

---

### Task 3: Fold `_tokens_with_font` into shared, and convert the shopify surfaces

**Files:**
- Modify: `packing-tool/shared/theme.py` — add `themed_tokens()`
- Modify: `packing-tool/gui/theme.py:31-52` — delete `_tokens` /
  `_tokens_with_font`, call shared
- Modify (shopify, after the sync in Task 5): `gui/theme_manager.py:193-217`,
  `gui/ui_manager.py:136-153`, `gui/session_browser_widget.py:448`,
  `gui/settings/*.py`

**Interfaces:**
- Produces: `themed_tokens(theme_name: str, family: str | None) -> ThemeTokens`
  — tokens with `font_family` set to `f"'{family}', {theme.font_family}"` when
  `family` is given, otherwise `get_theme(theme_name)` unchanged. Memoised on
  the success path only.

`packing-tool/gui/theme.py:48` and `shopify/gui/theme_manager.py:212` are the
same memoised function under two names, each wrapped by a near-identical
`_tokens()` / `_themed_tokens()`. Which font layers onto the tokens is a
decision, and a shim adapts rather than decides — so it moves to the module
that owns the tokens.

- [ ] **Step 1: Write the failing test** in `packing-tool/tests/test_theme.py`

```python
def test_themed_tokens_layers_the_family_and_memoises():
    from shared.theme import themed_tokens, get_theme

    plain = themed_tokens("light", None)
    assert plain is get_theme("light")

    themed = themed_tokens("light", "Inter")
    assert themed.font_family.startswith("'Inter', ")
    assert themed_tokens("light", "Inter") is themed  # memoised
```

- [ ] **Step 2: Run it and watch it fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_theme.py -k themed_tokens -v`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implement in `shared/theme.py`**

```python
@lru_cache(maxsize=2)
def _tokens_with_font(theme_name: str, family: str) -> ThemeTokens:
    theme = get_theme(theme_name)
    return replace(theme, font_family=f"'{family}', {theme.font_family}")


def themed_tokens(theme_name: str, family: str | None) -> ThemeTokens:
    """Tokens with an app's bundled family layered on, when there is one.

    Memoised because current_tokens() runs twice per table row on the scan
    path and replace() re-runs __init__ over all 50 fields every call.

    Only the success path is memoised: an app's font loader returns None
    before a QApplication exists, and caching that would leave the app on the
    fallback font for the rest of the process over one early call.
    """
    if family is None:
        return get_theme(theme_name)
    return _tokens_with_font(theme_name, family)


themed_tokens.cache_clear = _tokens_with_font.cache_clear
```

Add `from dataclasses import replace` and `from functools import lru_cache` if
they are not already imported.

- [ ] **Step 4: Point `packing-tool/gui/theme.py` at it**

Delete `_tokens` and `_tokens_with_font`; import `themed_tokens` from
`shared.theme` and replace the body of `_tokens(theme_name)`'s call site in
`apply_theme` with `themed_tokens(theme_name, load_bundled_fonts())`.

- [ ] **Step 5: Run the packing-tool suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add shared/theme.py gui/theme.py tests/test_theme.py
git commit -m "Bundle 1: one themed_tokens(), not one per app"
```

---

### Task 4: The token retune (9.1)

**Files:**
- Modify: `packing-tool/shared/theme.py` — `LIGHT_THEME` (~line 118),
  `DARK_THEME` (~line 163)
- Test: `packing-tool/tests/test_theme.py`

Transcribe **spec §3.1 and §3.2 verbatim**. Both tables are the contract; do
not re-derive a value and do not "improve" one.

Three traps, in the order you will hit them:

1. **The aliases are literals.** `_ALIAS_PAIRS` binds ten aliases and
   `validate_theme` asserts each pair is equal, but the values are spelled out
   in the dataclass, so each must be edited by hand. `button_hover_light` and
   `button_hover_dark` both follow `accent_fill_active` and sit under
   "Unchanged interaction colors" — they do not look alias-shaped and are the
   easy miss. Both become `#004B80` in **both** themes.
2. **`accent_fill_hover` and `accent_fill_active` are theme-independent.**
   Dark gets `#005F9F` / `#004B80` too.
3. **Do not touch the four dark planes**, or dark's `text`,
   `text_secondary`, `status_success`, `status_warning`, `focus_ring`, or any
   tint. Dark measures healthy; a symmetrical edit costs a second round of
   screenshots and gains nothing.

- [ ] **Step 1: Write the failing test** in `packing-tool/tests/test_theme.py`

```python
@pytest.mark.parametrize("theme", [LIGHT_THEME, DARK_THEME], ids=["light", "dark"])
def test_every_foreground_clears_its_floor_with_room(theme):
    """9.1's whole point: no token within 0.1 of its floor. Before the retune
    light's border sat at 3.02/3.0 and status_warning at 4.52/4.5."""
    for token, floor in _MIN_CONTRAST_ON_PLANES.items():
        for plane in _SURFACE_PLANES:
            ratio = contrast_ratio(getattr(theme, token), getattr(theme, plane))
            assert ratio >= floor + 0.1, (
                f"{theme.name}.{token} on {plane}: {ratio:.2f} < {floor} + 0.1"
            )


def test_light_planes_are_an_even_ramp():
    """218 / 230 / 242 / 255. Before the retune sunken->overlay was 2 units."""
    assert LIGHT_THEME.surface_sunken == "#DADADF"
    assert LIGHT_THEME.surface_overlay == "#E6E6EA"
    assert LIGHT_THEME.surface_raised == "#F2F2F4"
    assert LIGHT_THEME.surface == "#FFFFFF"


@pytest.mark.parametrize("theme", [LIGHT_THEME, DARK_THEME], ids=["light", "dark"])
def test_hover_is_the_overlay_plane(theme):
    """A row you point at should be a plane you can see."""
    assert theme.hover == theme.surface_overlay


@pytest.mark.parametrize("theme", [LIGHT_THEME, DARK_THEME], ids=["light", "dark"])
def test_the_three_blues_are_one_blue(theme):
    assert theme.selection_border == theme.status_info
    assert theme.focus_ring == theme.status_info


@pytest.mark.parametrize("theme", [LIGHT_THEME, DARK_THEME], ids=["light", "dark"])
def test_the_accent_hover_darkens(theme):
    """Lightening a fill is the one direction that costs contrast on the
    label sitting on it."""
    assert contrast_ratio(theme.on_accent, theme.accent_fill_hover) > \
           contrast_ratio(theme.on_accent, theme.accent_fill)
```

Import `_MIN_CONTRAST_ON_PLANES`, `_SURFACE_PLANES` and `contrast_ratio` from
`shared.theme` at the top of the file if they are not already imported.

- [ ] **Step 2: Run it and watch it fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_theme.py -v`
Expected: FAIL on the floor test (light `border` at 3.02) and on all four of
the new value assertions.

- [ ] **Step 3: Apply spec §3.1 to `LIGHT_THEME` and §3.2 to `DARK_THEME`**

- [ ] **Step 4: Delete the stale comment**

`LIGHT_THEME` opens with a note that `border` lands at 3.02 and
`status_warning` at 4.52, "both 0.02 above their floors… retune those two
tokens with it, not after." **This is that retune.** Delete the whole comment
block. `border` is now 3.52 and `status_warning` 5.37.

- [ ] **Step 5: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: all pass, including `validate_theme` in both themes.
If an alias-pair assertion fails, you missed one of trap 1's literals.

- [ ] **Step 6: Commit**

```bash
git add shared/theme.py tests/test_theme.py
git commit -m "Bundle 1 (9.1): the token retune, F0 + F0b"
```

---

### Task 5: Borders stop being furniture (9.2), shared half

**Files:**
- Modify: `packing-tool/shared/theme.py` — `build_stylesheet()`, ~lines 884–935
- Test: `packing-tool/tests/test_shared_theme_widgets.py`

Subtraction only. Qt has no `box-shadow`, so "raised" is a plane and never a
shadow — which is why Task 4 had to come first.

- [ ] **Step 1: Write the failing test**

```python
def test_regions_group_by_plane_not_by_outline():
    """F1: eleven outlines in one composition meant nothing was grouped,
    because everything was."""
    from shared.theme import LIGHT_THEME, build_stylesheet
    sheet = build_stylesheet(LIGHT_THEME)

    for rule in ("QTableView", "QListWidget", "QGroupBox", "QToolBar",
                 "QHeaderView::section"):
        block = _rule_block(sheet, rule)
        assert f"border: 1px solid {LIGHT_THEME.border}" not in block, (
            f"{rule} still outlines itself"
        )


def test_borders_stay_where_they_carry_meaning():
    """An input's edge and a hit target's edge are information."""
    from shared.theme import LIGHT_THEME, build_stylesheet
    sheet = build_stylesheet(LIGHT_THEME)
    for rule in ("QLineEdit", "QComboBox", "QPushButton"):
        assert f"border: 1px solid" in _rule_block(sheet, rule)


def test_groupbox_and_card_share_one_radius():
    """radius_lg is dialogs only."""
    from shared.theme import LIGHT_THEME, build_stylesheet
    sheet = build_stylesheet(LIGHT_THEME)
    assert f"border-radius: {LIGHT_THEME.radius_md}px" in _rule_block(sheet, "QGroupBox")
```

Write `_rule_block(sheet, selector)` as a small helper: find the selector at
the start of a line, return the text up to the next `}`. **Task 9's tests use
it too**, so put it in `packing-tool/tests/conftest.py` rather than in this
file, and import it in both.

- [ ] **Step 2: Run it and watch it fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_shared_theme_widgets.py -v`
Expected: FAIL — all five rules still say `border: 1px solid`.

- [ ] **Step 3: Remove the five borders**

Drop the `border: 1px solid {theme.border};` line from the `QTableView`,
`QListWidget`, `QGroupBox`, `QToolBar` and `QHeaderView::section` blocks.
Leave `QTableCornerButton::section` alone — it is not in F1's list.

- [ ] **Step 4: Fold the radii**

`QGroupBox` is `border-radius: {r + 4}px` today; make it
`{theme.radius_md}px`. Leave `QTableView` and `QListWidget` radii as they are
— F1 names only `QGroupBox` and `Card`.

- [ ] **Step 5: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: all pass.

- [ ] **Step 6: Commit, then sync into shopify**

```bash
git add shared/theme.py tests/test_shared_theme_widgets.py
git commit -m "Bundle 1 (9.2): five rules stop outlining themselves"
```

Then, from the **shopify** worktree root:

```bash
.venv/bin/python scripts/sync_shared.py /home/cognitiveghost/Desktop/Projects/packing-tool
```

The sync copies from packing-tool's **main checkout**, not its worktree. Point
it at the worktree path if the script accepts one; otherwise merge the
packing-tool branch locally first, or copy `shared/theme.py` and
`shared/icons.py` across by hand and note it in the PR. **Verify the diff
before committing** — `git diff shared/` must show only Bundle 1's changes.

---

### Task 6: The shopify half of the repaint fix and 9.2

**Files:**
- Modify: `gui/components/card.py:27-28`
- Modify: `gui/theme_manager.py:193-217` (delete the duplicate),
  `gui/theme_manager.py` `set_density()` (one line)
- Modify: `gui/ui_manager.py:136-153` (delete `_connect_theme_change`)
- Modify: `gui/session_browser_widget.py:448`
- Modify: `gui/settings/rules.py`, `sets.py`, `weight.py`, `mappings.py`
- Test: `tests/test_theme_repaint.py` (new)

**Interfaces:**
- Consumes: `on_theme_changed(widget, apply)` and `themed_tokens(name, family)`
  from Task 2 and Task 3, now present in the synced `shared/theme.py`.

- [ ] **Step 1: Write the failing test** in `tests/test_theme_repaint.py`

```python
"""A theme toggle must reach widgets that style themselves.

53 call sites in gui/ interpolate a token into a widget stylesheet once, at
build time. Re-polishing re-applies that same stale literal -- see ADR 0003.
"""
import pytest
from PySide6.QtWidgets import QLabel

from gui.theme_manager import get_theme_manager
from shared.theme import on_theme_changed


def test_a_converted_widget_follows_the_toggle(qapp):
    manager = get_theme_manager()
    manager.set_theme("light")

    label = QLabel()
    on_theme_changed(label, lambda t: label.setStyleSheet(f"color: {t.text};"))
    light = label.styleSheet()

    manager.set_theme("dark")
    assert label.styleSheet() != light, "widget kept the light theme's hex"


def test_a_converted_widget_follows_a_density_change(qapp):
    """15 of the 53 also interpolate font_css(), which moves with density."""
    from shared.theme import font_css

    manager = get_theme_manager()
    manager.set_density("desk")

    label = QLabel()
    on_theme_changed(label, lambda t: label.setStyleSheet(font_css("body")))
    desk = label.styleSheet()

    manager.set_density("floor")
    assert label.styleSheet() != desk, "widget kept the desk type scale"
```

- [ ] **Step 2: Run it and watch the density test fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_theme_repaint.py -v`
Expected: the toggle test passes (Task 2 shipped it); the **density** test
FAILS. `shared.set_current()` returns early when the name is unchanged, so a
density change never reaches `theme_notifier`.

- [ ] **Step 3: Make density announce itself**

In `gui/theme_manager.py`, `ThemeManager.set_density()`, after
`self.apply_theme()`:

```python
        # A density change moves the type scale without moving the theme name,
        # so set_current() inside apply_theme() returns early and announces
        # nothing. Listeners restyle from both -- see ADR 0003.
        theme_notifier.changed.emit(self._current_theme_name)
```

Import `theme_notifier` from `shared.theme`. Do **not** make
`shared.set_density()` emit: its docstring commits it to "no QSettings, no
restyle, no Qt", and that decision stands.

- [ ] **Step 4: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_theme_repaint.py -v`
Expected: PASS.

- [ ] **Step 5: Delete the two duplicates**

- `gui/theme_manager.py:193-217`: delete `_themed_tokens` and
  `_tokens_with_font`; call `themed_tokens(self._current_theme_name,
  load_bundled_fonts())` instead. Keep the `cache_clear` attribute wiring
  pointing at `themed_tokens.cache_clear`.
- `gui/ui_manager.py:136-153`: delete `_connect_theme_change` and replace its
  one call site (`self._connect_theme_change(self._refresh_icons)` at
  line ~204) with `on_theme_changed(self.mw, lambda _t: self._refresh_icons())`.
  `UIManager` is a plain Python object, so pass `self.mw` as the lifetime
  owner — that is what the old code used for its `destroyed` hook.

- [ ] **Step 6: `Card` stops drawing an OS frame**

In `gui/components/card.py`, replace:

```python
        self.setFrameShape(QFrame.StyledPanel)
        self.setFrameShadow(QFrame.Raised)
```

with:

```python
        # StyledPanel + Raised draws an OS frame *underneath* the stylesheet,
        # so the card ends up outlined no matter what QSS says. F1: regions
        # separate by plane, and a border is reserved for inputs and focus.
        self.setFrameShape(QFrame.NoFrame)
```

Then add the type-scoped rule to `build_stylesheet` in **packing-tool**
(`shared/theme.py`) and re-sync:

```
        Card {{
            background-color: {theme.surface_raised};
            border: none;
            border-radius: {theme.radius_md}px;
        }}
```

- [ ] **Step 7: Convert the named surfaces**

Convert every theme-derived `setStyleSheet(f"…")` in these files to
`on_theme_changed(widget, lambda t: widget.setStyleSheet(f"…"))`, replacing
each `theme.` with the closure's `t.`:

- `gui/settings/rules.py` (8 sites), `sets.py` (2), `weight.py` (2),
  `mappings.py` (1) — the open Settings page the criterion names.
- `gui/session_browser_widget.py:448` — `name_item.setIcon(icon("message-square"))`
  hands a `QIcon` **snapshot** to a model item, which does not follow a toggle.
  The item is not a QWidget, so give the closure the view that owns it:
  `on_theme_changed(self, lambda _t: name_item.setIcon(icon("message-square")))`
  at the point the item is built, or re-run the population pass.

Beware the late-binding trap: in a loop, bind the widget with a default
argument (`lambda t, w=widget: …`), or every closure will style the last one.

The results table needs no conversion — its delegates already read the theme
at paint time and Qt repaints the viewport on a stylesheet change (ADR 0003).

- [ ] **Step 8: Run the full shopify suite and lint**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q && .venv/bin/ruff check .`
Expected: all pass, no lint errors.

- [ ] **Step 9: Commit**

```bash
git add gui/ shared/ tests/test_theme_repaint.py
git commit -m "Bundle 1: the repaint fix, and Card stops drawing an OS frame"
```

---

### Task 7: `glyph_url()` learns a second dimension

**Files:**
- Modify: `packing-tool/shared/icons.py` — `_pixmap` (line 36), `glyph_url`
  (line 86)
- Test: `packing-tool/tests/test_ui_assets.py`

**Interfaces:**
- Produces: `glyph_url(name, color=None, size=18, height=None) -> str` and
  `_pixmap(source, size, height=None) -> QPixmap`. `height` defaults to
  `size`, so no existing call changes.

- [ ] **Step 1: Write the failing test**

```python
def test_glyph_url_renders_a_non_square_glyph(qapp):
    """The toggle track is 36x20; a square render squashes it."""
    from pathlib import Path
    from shared.icons import glyph_url
    from PySide6.QtGui import QPixmap

    url = glyph_url("check", "#000000", size=36, height=20)
    path = url.removeprefix('url("').removesuffix('")')
    assert QPixmap(path).size().toTuple() == (36, 20)


def test_square_and_non_square_renders_do_not_collide(qapp):
    from shared.icons import glyph_url
    assert glyph_url("check", "#000000", size=36) != \
           glyph_url("check", "#000000", size=36, height=20)
```

- [ ] **Step 2: Run it and watch it fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_ui_assets.py -k glyph -v`
Expected: FAIL — `glyph_url() got an unexpected keyword argument 'height'`.

- [ ] **Step 3: Implement**

In `_pixmap`, take `height: int | None = None`, set `height = height or size`,
and build `QPixmap(size, height)`.

In `glyph_url`, take `height: int | None = None`, pass it through to
`_pixmap`, and put it in the cache filename so a square and a non-square
render of the same glyph cannot collide:

```python
    path = cache_dir / f"{name}-{digest}-{size}x{height or size}.png"
```

Extend the docstring with one line naming why `height` exists.

- [ ] **Step 4: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: all pass — including every existing `glyph_url` test, unchanged.

- [ ] **Step 5: Commit**

```bash
git add shared/icons.py tests/test_ui_assets.py
git commit -m "Bundle 1: glyph_url() renders non-square sub-controls"
```

---

### Task 8: The toggle glyphs

**Files:**
- Create: `packing-tool/shared/assets/icons/toggle-off.svg`,
  `packing-tool/shared/assets/icons/toggle-on.svg`

Authored, not vendored — Lucide has no toggle track. Follow Lucide's
convention exactly: **every stroke and fill is `currentColor`**, so the single
substitution `glyph_url()` performs serves both themes from one file. Separate
track from thumb with `fill-opacity`, never with a second colour — a second
hex would be right in one theme and wrong in the other.

- [ ] **Step 1: Write `toggle-off.svg`**

```xml
<svg xmlns="http://www.w3.org/2000/svg" width="36" height="20" viewBox="0 0 36 20" fill="none">
  <rect x="1" y="1" width="34" height="18" rx="9" fill="currentColor" fill-opacity="0.18"
        stroke="currentColor" stroke-opacity="0.55" stroke-width="1.5"/>
  <circle cx="10" cy="10" r="6" fill="currentColor"/>
</svg>
```

- [ ] **Step 2: Write `toggle-on.svg`**

```xml
<svg xmlns="http://www.w3.org/2000/svg" width="36" height="20" viewBox="0 0 36 20" fill="none">
  <rect x="1" y="1" width="34" height="18" rx="9" fill="currentColor"/>
  <circle cx="26" cy="10" r="6" fill="#FFFFFF"/>
</svg>
```

The thumb here is the one deliberate literal: it is `on_accent`, which is
`#FFFFFF` in **both** themes (spec §3.1 and §3.2 both leave it unchanged), and
it sits on the accent fill rather than on a plane. If a future retune moves
`on_accent`, this file moves with it — note that in the PR body.

- [ ] **Step 3: Prove both render**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_ui_assets.py -q`
Expected: pass. If `test_ui_assets.py` enumerates the glyph directory, the two
new files are picked up automatically; if it has a hardcoded list, add them.

- [ ] **Step 4: Commit**

```bash
git add shared/assets/icons/toggle-off.svg shared/assets/icons/toggle-on.svg
git commit -m "Bundle 1 (9.5): the toggle's two states"
```

---

### Task 9: The control inventory's four gaps (9.5)

**Files:**
- Modify: `packing-tool/shared/theme.py` — `build_stylesheet()`
- Test: `packing-tool/tests/test_shared_theme_buttons.py`

Then re-sync into shopify as in Task 5, Step 6.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_button_grows_with_its_density_rung():
    """build_stylesheet hardcoded font-size: 10pt, so a floor-density button
    stayed at the desk size."""
    from shared.theme import LIGHT_THEME, build_stylesheet, font_css, set_density
    try:
        set_density("floor")
        assert "font-size: 12pt" in _rule_block(build_stylesheet(LIGHT_THEME),
                                                "QPushButton")
    finally:
        set_density("desk")


def test_primary_focuses_against_its_own_fill():
    """A focus_ring border on an accent fill is invisible. One exception,
    written down once."""
    from shared.theme import LIGHT_THEME, build_stylesheet
    sheet = build_stylesheet(LIGHT_THEME)
    primary_focus = _rule_block(sheet, 'QPushButton[role="primary"]:focus')
    assert f"2px solid {LIGHT_THEME.border_strong}" in primary_focus
    assert LIGHT_THEME.focus_ring not in primary_focus


def test_the_spin_box_is_specified_as_it_renders():
    """Qt adds room for the up/down buttons after min-height applies, so a
    'desk' spin box comes out 35px, not 32."""
    from shared.theme import get_density_profile
    profile = get_density_profile()
    assert profile.control_height + 3 == 35


def test_the_toggle_indicator_is_the_drawn_size():
    from shared.theme import LIGHT_THEME, build_stylesheet
    block = _rule_block(build_stylesheet(LIGHT_THEME),
                        'QCheckBox[role="toggle"]::indicator')
    assert "width: 36px" in block and "height: 20px" in block
```

- [ ] **Step 2: Run them and watch them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_shared_theme_buttons.py -v`
Expected: FAIL on all four.

- [ ] **Step 3: The button font size**

In `build_stylesheet`'s bare `QPushButton` block, replace the hardcoded
`font-size: 10pt;` with `{font_css("body")}`.

- [ ] **Step 4: The focus exception**

Add, after the existing `QPushButton[role="primary"]` rules:

```
        /* A focus_ring border on an accent fill is invisible: the ring and the
           fill are the same blue since 9.1 folded them together. Primary alone
           focuses against border_strong. Every other variant keeps focus_ring. */
        QPushButton[role="primary"]:focus {{
            border: 2px solid {theme.border_strong};
        }}
```

- [ ] **Step 5: The toggle**

Add a `role="toggle"` variant. The `role` property is the same mechanism
`QPushButton[role="primary"]` already uses; a caller opts in with
`checkbox.setProperty("role", "toggle")`. `set_button_role()` is for buttons —
do not widen it here unless a second widget type needs it.

```
        QCheckBox[role="toggle"]::indicator {{
            width: 36px; height: 20px;
        }}
        QCheckBox[role="toggle"]::indicator:unchecked {{
            image: {glyph_url("toggle-off", theme.border, size=36, height=20)};
        }}
        QCheckBox[role="toggle"]::indicator:checked {{
            image: {glyph_url("toggle-on", theme.accent_fill, size=36, height=20)};
        }}
```

`shared/theme.py` importing `shared.icons` would be a circular import —
`icons.py` already imports `current_tokens` from `theme.py`. Import
`glyph_url` **inside** `build_stylesheet` (a local import at the top of the
function), and say so in a one-line comment.

- [ ] **Step 6: The radio dot, with no glyph**

```
        QRadioButton::indicator {{
            width: 16px; height: 16px; border-radius: 8px;
            border: 1px solid {theme.border};
            background-color: {theme.surface};
        }}
        /* A filled dot, not a ring: Lucide draws in stroke="currentColor", so
           its circle glyph would give an outline. border-radius draws the dot
           in one rule and needs no asset. */
        QRadioButton::indicator:checked {{
            background-color: {theme.accent_fill};
            border: 4px solid {theme.surface};
        }}
```

- [ ] **Step 7: The spin box, drawn as it renders**

`DensityProfile.control_content_height` already documents the +3 offset as a
measured `ponytail:` shortcut. Do **not** add a `-3` correction — the comment
explains why that would make Windows shorter if its offset differs. Only the
*documentation* changes: update the `QSpinBox` comment in `build_stylesheet`
to say 35px at desk, 47px at floor, matching what `control_height + 3` gives.

- [ ] **Step 8: Run everything in packing-tool**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q && .venv/bin/ruff check .`
Expected: all pass.

- [ ] **Step 9: Commit and sync**

```bash
git add shared/theme.py tests/test_shared_theme_buttons.py
git commit -m "Bundle 1 (9.5): the toggle, and three corrections"
```

Then re-sync into shopify and run the shopify suite and `ruff`.

---

### Task 10: Contrast fixtures, the README, and the graph

**Files:**
- Modify: `tests/test_theme_contrast.py` (shopify)
- Rewrite: `packing-tool/shared/README.md`

- [ ] **Step 1: Bring the shopify contrast guard up to the new values**

`tests/test_theme_contrast.py` is this repo's proof that whatever arrived
through the sync still satisfies the design-system contract. Add the same
floor-with-room assertion Task 4 added in packing-tool, so a future sync that
weakens a token fails here too:

```python
@pytest.mark.parametrize("theme", [LIGHT_THEME, DARK_THEME], ids=["light", "dark"])
def test_no_foreground_sits_within_a_tenth_of_its_floor(theme):
    """9.1's completion criterion. A sync that re-tightened a token would
    otherwise surface as an unreadable badge on a warehouse screen."""
    for token, floor in _MIN_CONTRAST_ON_PLANES.items():
        for plane in _SURFACE_PLANES:
            ratio = contrast_ratio(getattr(theme, token), getattr(theme, plane))
            assert ratio >= floor + 0.1, f"{theme.name}.{token} on {plane}: {ratio:.2f}"
```

Import `_MIN_CONTRAST_ON_PLANES` alongside the existing `_SURFACE_PLANES`.

- [ ] **Step 2: Rewrite `packing-tool/shared/README.md`**

It documents "Phase 1.4: Unified Statistics System" and nothing else, across
300+ lines, while `shared/` now holds the theme, the asset library, file
locking, atomic writes and session IDs. Replace it with a short index: what
each module is, and the one-way sync rule stated at the top —
`packing-tool` is canonical, `scripts/sync_shared.py` copies one way, a
`shared/` file edited in the Shopify repo is overwritten by the next sync.
Aim for well under 100 lines; this is an index, not a manual.

- [ ] **Step 3: Run both suites one final time**

In each repo: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q && .venv/bin/ruff check .`

- [ ] **Step 4: Update the graph in each main checkout**

```bash
graphify update .
```

Per each repo's CLAUDE.md — run it in the **main checkout**, not the worktree,
where `graphify-out/` is gitignored.

- [ ] **Step 5: Commit**

```bash
git add tests/test_theme_contrast.py
git commit -m "Bundle 1: the contrast guard carries the new floors"
```

---

## Verification before opening the PRs

Do not claim any of these without running the command and reading the output.

- [ ] `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` green in **both** repos
- [ ] `.venv/bin/ruff check .` clean in **both** repos
- [ ] `validate_theme` passes in both themes (it runs inside the suite)
- [ ] `git diff origin/main -- shared/` in shopify shows **only** Bundle 1's
      changes — a sync that dragged in something else is a bug, not a rebase
- [ ] A launched app switches theme with the session browser and a Settings
      page open, leaving no stale colour. `python run_dev.py` needs no
      production server.

## Seams to test at

Named so Stage B does not have to guess where a test belongs.

| Seam | Test file | What it protects |
|---|---|---|
| `theme_notifier` → a widget's closure | `packing-tool/tests/test_theme_notifier.py` | the repaint fix's mechanism, both repos |
| `ThemeManager.set_density` → `theme_notifier` | `tests/test_theme_repaint.py` | the density half, shopify only |
| token values → `_MIN_CONTRAST_ON_PLANES` | `packing-tool/tests/test_theme.py` | the retune is measurably safe |
| the synced `shared/` → this repo's contract | `tests/test_theme_contrast.py` | a bad sync fails loudly here |
| `build_stylesheet` output → F1/F3 rules | `packing-tool/tests/test_shared_theme_widgets.py`, `test_shared_theme_buttons.py` | borders, focus, toggle, button type |
| `glyph_url` → a QSS-ready PNG | `packing-tool/tests/test_ui_assets.py` | non-square sub-controls render |

## Two PRs

`packing-tool` first, then shopify — the shopify PR contains the synced
`shared/` and cannot be reviewed before the change it carries has landed.
Title them as 9.0 did:

- `Phase 9 Bundle 1 (packing-tool half): foundations — repaint, tokens, borders, controls`
- `Phase 9 Bundle 1 (shopify half): foundations — repaint, tokens, borders, controls`

Both PR bodies should name the three departures from the briefs recorded in
spec §8, so the reviewer sees them without opening the spec.
