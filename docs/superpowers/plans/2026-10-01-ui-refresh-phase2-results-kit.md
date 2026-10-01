# UI refresh phase 2: Results to mockup, and the web kit. Implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the Results page to the approved mockup on a shared web stylesheet (`gui/web/kit.css`) that
every later web page will link, with the tokens and the lint rule that stylesheet needs.

**Architecture:** `shared/theme.py` gains seven tokens (four colours, three CSS values) and `shared/style_lint.py`
allows `box-shadow` in three spellings. `gui/web/kit.css` holds every component a web page shares;
`gui/web/results.css` keeps only what is Results'. The page keeps its four scripts (`columns.js`, `pane.js`,
`bulk.js`, `results.js`) and every element id it has today; each task changes one area's markup, CSS and script
together, so the suite passes after every task. Python changes are small: one bridge member, three deleted
confirm dialogs, a results mode on the command bar, and three screen-menu items.

**Tech Stack:** Python 3.14, PySide6 (Qt widgets, QtWebEngine, QWebChannel), plain CSS and JavaScript (no build
step, no framework), pytest + pytest-qt driving a real Chromium offscreen.

**Spec:** `docs/superpowers/specs/2026-10-01-ui-refresh-phase2-results-kit-design.md`. Read it whole before
starting; this plan argues from it and does not repeat its tables.
Mockups: `docs/design/ui-refresh/mockups/results.html` and `component-sheet.html` (renders:
`mockups/renders/results.png`, `mockups/renders/component-sheet.png`). To read exact values, unpack a bundle
with the script in `docs/design/ui-refresh/mockups/README.md`.

## Global Constraints

- Work in `/home/gloopy/Desktop/Projects/shopify-fulfillment-tool/.claude/worktrees/dr-14` on branch
  `dr/14-ui-refresh-phase-2-results-to-mockup-and`. Never `cd` anywhere else. If `.venv` is missing, run
  `./scripts/setup_venv.sh`.
- Run tests only as `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q <paths>`. A hook blocks any other
  Bash text containing the word "pytest", so write test files with Write/Edit, never with heredocs.
- Git: `/usr/bin/git`, one plain command per Bash call, with no `;`, `&&` or `$VAR`. Commit with
  `/usr/bin/git commit -F <absolute path to a message file>`; write the message file under your job's tmp dir.
  End every message with the attribution line your session is given.
- **Pre-existing failures (baseline at f40b3d4: 2423 passed, 3 failed):** the three tests in
  `tests/test_label_printing.py::TestImageToZpl` fail on `origin/main`. They are not this task's. Do not fix
  them. The PR body mentions them. Every other test must pass after every task.
- No hex, colour name, `rgb()`, px font size, `transition`, `transform`, gradient or `opacity` in any file under
  `gui/` (`shared/style_lint.py`, enforced by `tests/test_style_literals_guard.py`). `box-shadow` only as
  `var(--card-shadow)`, `var(--overlay-shadow)` or `none`, and only in a `.css` file. `shared/theme.py` is the
  one file where a colour literal belongs.
- CSS custom properties from the theme are hyphenated: the token `surface_raised` is `var(--surface-raised)`.
- ADR 0018: a decorative line (card edge, divider, popover edge) is `--border-subtle`. The edge of a button, an
  input or a checkbox is `--border`.
- Every element id that exists in `gui/web/results.html` today keeps its name unless a task says it is removed.
- The four page scripts share one global scope and load in this order: `columns.js`, `pane.js`, `bulk.js`,
  `results.js`. A function may call a later file's function only from inside a function body.
- `shared/` is canonical here (ADR 0017). Edit it directly. Never touch `packing-tool/`.
- No `pyproject.toml`, no new dependency, no unused import (`ruff check .` must pass).
- Never mark a Chromium test skip, and never delete a test without a replacement that pins the new behaviour.
- A measured number in this plan (a width, a row count) comes from arithmetic on the CSS. If Chromium measures
  something else, read the page with `_eval` to find out why before changing the number; do not just paste
  the measured value.
- Copy is verbatim from the spec. The strings this plan introduces: "Map columns", "Order value shows once a
  price column is mapped.", "Value ready", "Remove filter", "Clear filters", "What will change",
  "You can undo this from the confirmation that follows.", "Order detail", "Hide detail", "Show detail",
  "Exclude order", "Last line: exclude the order instead", "Dismiss", "Run analysis again",
  "Open session folder", "Copy summary", "Summary copied", "Clear selection".

## Review Focus

1. **A selection that carries many SKUs.** With 30 SKUs on the checked orders, the picker scrolls inside the
   popover and the verb stays on screen under "What will change" (test in Task 8).
2. **Fifty checked orders.** "What will change" names three order numbers and "and 47 more", never all fifty
   (test in Task 8).
3. **A filter that hides the cursor's order.** The pane returns to "No order selected" and the row loses its
   cursor; nothing keeps pointing at an order the operator cannot see (test in Task 7).
4. **Floor density.** Rows are `--row-height` + 4 in both densities: 44px at floor, and the row maths follows
   (test in Task 4).
5. **A second shadow smuggled in after a token.** `box-shadow: var(--card-shadow), 0 0 4px var(--border)` is
   still a lint finding (test in Task 2).

---

### Task 1: Seven tokens (`shared/theme.py`)

**Files:**
- Modify: `shared/theme.py`: `ThemeTokens` (class at line 25), `LIGHT_THEME` (line 126), `DARK_THEME`
  (line 172), `_COLOR_FIELDS` (line 486), `_SURFACE_PLANES` (line 537), `validate_theme` (line 601),
  `theme_css_vars` (line 1069)
- Test: `tests/test_theme_palette.py`, `tests/test_theme_contrast.py`, `tests/test_theme_css_vars.py`

**Interfaces:**
- Produces: `ThemeTokens.surface_inverse`, `.on_inverse`, `.critical_fill`, `.on_critical`, `.card_border`,
  `.card_shadow`, `.overlay_shadow` (all `str`); module constants `_CSS_VALUE_FIELDS: tuple[str, ...]` and
  `_INVERSE_PAIRS: tuple[tuple[str, str], ...]`. The web tier reads them as `--surface-inverse`,
  `--on-inverse`, `--critical-fill`, `--on-critical`, `--card-border`, `--card-shadow`, `--overlay-shadow`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_theme_palette.py`, add to the `PALETTE` dict after the `"control_disabled_bg"` entry:

```python
    # New in phase 2 (spec 2026-10-01 section 3.1).
    "surface_inverse": ("#303030", "#E3E3E3"),
    "on_inverse": ("#FFFFFF", "#1A1B1E"),
    "critical_fill": ("#C70A24", "#C4343F"),
    "on_critical": ("#FFFFFF", "#FFFFFF"),
    "card_border": ("transparent", "#2E2F34"),
    "card_shadow": (
        "0 1px 0 rgba(26,26,26,0.07), 0 1px 3px rgba(26,26,26,0.12)",
        "none",
    ),
    "overlay_shadow": ("0 4px 12px rgba(26,26,26,0.2)", "none"),
```

In `tests/test_theme_contrast.py`, add `from dataclasses import replace` to the imports, add `validate_theme`
and `_CSS_VALUE_FIELDS` to the `from shared.theme import (...)` list if they are not there, and append:

```python
def test_the_inverse_plane_is_not_a_surface_plane():
    """Phase 2 spec section 3.2. Every text floor would fail against a dark
    plane in light mode, and packing-tool's test pins this tuple."""
    assert _SURFACE_PLANES == (
        "surface_sunken",
        "surface",
        "surface_raised",
        "surface_overlay",
    )


@pytest.mark.parametrize(
    "text, fill", [("on_inverse", "surface_inverse"), ("on_critical", "critical_fill")]
)
def test_text_on_an_inverse_or_critical_fill_is_validated(text, fill):
    broken = replace(LIGHT_THEME, **{text: getattr(LIGHT_THEME, fill)})
    with pytest.raises(ValueError, match=text):
        validate_theme(broken)


@pytest.mark.parametrize("field", _CSS_VALUE_FIELDS)
@pytest.mark.parametrize("value", ["", "none; } body { display: none", "0 0 0 {", "}"])
def test_a_css_value_token_cannot_break_out_of_its_declaration(field, value):
    with pytest.raises(ValueError, match=field):
        validate_theme(replace(LIGHT_THEME, **{field: value}))
```

In `tests/test_theme_css_vars.py`, append:

```python
@pytest.mark.parametrize("theme", [LIGHT_THEME, DARK_THEME], ids=lambda t: t.name)
def test_the_css_value_tokens_reach_the_web_tier_verbatim(theme, density):
    density("desk")
    decls = _parse(theme_css_vars(theme))
    assert decls["--card-border"] == theme.card_border
    assert decls["--card-shadow"] == theme.card_shadow
    assert decls["--overlay-shadow"] == theme.overlay_shadow
```

- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_theme_palette.py tests/test_theme_contrast.py tests/test_theme_css_vars.py`
Expected: collection error or FAIL: `ThemeTokens` has no `surface_inverse`, and `_CSS_VALUE_FIELDS` cannot be
imported.

- [ ] **Step 3: Add the fields and their values**

In `ThemeTokens`, after the `control_disabled_bg: str` line:

```python
    # Phase 2 (spec 2026-10-01 section 3.1): the toast's inverse plane, the
    # destructive confirm fill, and the web tier's card edge and shadows. The
    # last three are CSS values, not colours -- see _CSS_VALUE_FIELDS.
    surface_inverse: str
    on_inverse: str
    critical_fill: str
    on_critical: str
    card_border: str
    card_shadow: str
    overlay_shadow: str
```

In `LIGHT_THEME`, after `control_disabled_bg="#F1F1F1",`:

```python
    surface_inverse="#303030",
    on_inverse="#FFFFFF",
    critical_fill="#C70A24",
    on_critical="#FFFFFF",
    card_border="transparent",
    card_shadow="0 1px 0 rgba(26,26,26,0.07), 0 1px 3px rgba(26,26,26,0.12)",
    overlay_shadow="0 4px 12px rgba(26,26,26,0.2)",
```

In `DARK_THEME`, after `control_disabled_bg="#141518",`:

```python
    surface_inverse="#E3E3E3",
    on_inverse="#1A1B1E",
    critical_fill="#C4343F",
    on_critical="#FFFFFF",
    card_border="#2E2F34",
    card_shadow="none",
    overlay_shadow="none",
```

- [ ] **Step 4: Register and validate them**

In `_COLOR_FIELDS`, after `"control_disabled_bg",`:

```python
    "surface_inverse",
    "on_inverse",
    "critical_fill",
    "on_critical",
```

Replace the `_SURFACE_PLANES` line with:

```python
# surface_inverse is the toast's plane, not an elevation step: text is never
# measured against it except on_inverse (see _INVERSE_PAIRS), and
# packing-tool's tests/test_theme.py pins this tuple to the four planes.
_SURFACE_PLANES = tuple(
    f for f in _COLOR_FIELDS if f.startswith("surface") and f != "surface_inverse"
)
```

After the `_ACCENT_FILLS` line, add:

```python
# text -> the one fill it is drawn on. Each pair must clear AA (4.5:1).
_INVERSE_PAIRS = (
    ("on_inverse", "surface_inverse"),
    ("on_critical", "critical_fill"),
)

# Tokens the web tier reads that are CSS values rather than colours: an edge
# that is `transparent` in one theme, and shadows. Not hex-checked; checked
# instead for the characters that would close the :root block they land in.
_CSS_VALUE_FIELDS = ("card_border", "card_shadow", "overlay_shadow")
```

In `validate_theme`, after the `for fill in _ACCENT_FILLS:` loop (the end of the function), add:

```python
    for text, fill in _INVERSE_PAIRS:
        ratio = contrast_ratio(getattr(theme, text), getattr(theme, fill))
        if ratio < 4.5:
            raise ValueError(
                f"{theme.name}.{text} has {ratio:.2f}:1 contrast against "
                f"{fill}, below the 4.5:1 minimum"
            )

    for field_name in _CSS_VALUE_FIELDS:
        value = getattr(theme, field_name)
        if not isinstance(value, str) or not value.strip() or set(value) & set(";{}"):
            raise ValueError(
                f"{theme.name}.{field_name} = {value!r} is not a single CSS value"
            )
```

Add one sentence to `validate_theme`'s docstring, after "against all three accent fills.":
"Text on the inverse and critical fills is checked the same way, and the three CSS-value tokens are checked to
be single values."

In `theme_css_vars`, replace the `missing = ...` line with:

```python
    expected = [c for c in _COLOR_FIELDS if c not in aliases] + list(_CSS_VALUE_FIELDS)
    missing = {_css_name(c) for c in expected} - decls.keys()
```

- [ ] **Step 5: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_theme_palette.py tests/test_theme_contrast.py tests/test_theme_css_vars.py tests/test_shared_theme_buttons.py tests/test_shared_theme_widgets.py tests/test_results_bridge.py tests/test_style_literals_guard.py`
Expected: PASS. `test_the_palette_is_the_mockups_fitted_to_the_floors` now runs 38 tokens per theme.

- [ ] **Step 6: Commit**

`/usr/bin/git add shared/theme.py tests/test_theme_palette.py tests/test_theme_contrast.py tests/test_theme_css_vars.py`,
then commit with the message "Theme: inverse, critical and card tokens for the web kit".

---

### Task 2: `box-shadow` as a token only (`shared/style_lint.py`)

**Files:**
- Modify: `shared/style_lint.py`: the module docstring (lines 32-36), a new `_SHADOW_OK` after `_BANNED`
  (line 133), `_scan_web_asset` (line 233)
- Test: `tests/test_style_lint.py`

**Interfaces:**
- Consumes: the CSS names `--card-shadow` and `--overlay-shadow` from Task 1.
- Produces: `find_style_literals` reports no finding for `box-shadow: var(--card-shadow);`,
  `box-shadow: var(--overlay-shadow);` or `box-shadow: none;` in a `.css`, `.html` or `.js` file.

- [ ] **Step 1: Write the failing tests**

`tests/test_style_lint.py` has a helper `_scan_asset(tmp_path, name, text)` that returns findings as
`"<line>: <kind>: <text>"`. Append:

```python
@pytest.mark.parametrize(
    "value",
    [
        "var(--card-shadow)",
        "var(--overlay-shadow)",
        "none",
        "var( --card-shadow )",
    ],
)
def test_a_shadow_token_or_none_is_the_only_shadow_allowed(tmp_path, value):
    """ADR 0016, phase 2 spec section 3.3."""
    assert _scan_asset(tmp_path, "page.css", f".card {{ box-shadow: {value}; }}\n") == []
    # The last declaration of a rule may end at the brace instead.
    assert _scan_asset(tmp_path, "page.css", f".card {{ box-shadow: {value} }}\n") == []


@pytest.mark.parametrize(
    "declaration",
    [
        "box-shadow: 0 1px 2px var(--border);",
        "box-shadow: inset 3px 0 0 var(--selection-border);",
        "box-shadow: var(--border);",
        "box-shadow: var(--card-shadow), 0 0 4px var(--border);",
        "box-shadow: var(--card-shadow) !important;",
    ],
)
def test_any_other_shadow_is_still_banned(tmp_path, declaration):
    out = _scan_asset(tmp_path, "page.css", f".x {{ {declaration} }}\n")
    assert out == ["1: banned: box-shadow"]


def test_a_vendor_or_scripted_shadow_is_banned_even_with_a_token(tmp_path):
    css = _scan_asset(tmp_path, "page.css", ".x { -webkit-box-shadow: var(--card-shadow); }\n")
    assert css == ["1: banned: -webkit-box-shadow"]
    js = _scan_asset(tmp_path, "page.js", "el.style.boxShadow = 'var(--card-shadow)';\n")
    assert js == ["1: banned: boxShadow"]


def test_a_shadow_in_an_inline_style_attribute_is_banned(tmp_path):
    out = _scan_asset(
        tmp_path, "page.html", '<div style="box-shadow: var(--card-shadow)"></div>\n'
    )
    assert out == ["1: banned: box-shadow"]
```

- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_style_lint.py`
Expected: `test_a_shadow_token_or_none_is_the_only_shadow_allowed` FAILS four times with
`['1: banned: box-shadow'] == []`. The other new tests pass already.

- [ ] **Step 3: Allow the three spellings**

In `shared/style_lint.py`, after the `_BANNED = re.compile(...)` block, add:

```python
# ADR 0016: the web tier may cast a shadow, but only one of the theme's two
# shadow tokens (or none, to take one off). The value must be the whole
# declaration, so a second shadow cannot ride in after the token.
_SHADOW_OK = re.compile(
    r"\s*(?:var\(\s*--(?:card|overlay)-shadow\s*\)|none)\s*[;}]"
)
```

In `_scan_web_asset`, inside `for m in rx.finditer(code):`, after the `ALLOW_MARKER` check and before
`found.append(...)`, add:

```python
            if (
                kind == "banned"
                and m.group(1) == "box-shadow"
                and _SHADOW_OK.match(code, m.end())
            ):
                continue
```

`m.group(1)` is the CSS-declaration alternative of `_BANNED`, so `-webkit-box-shadow`, `.style.boxShadow` and
`setProperty("box-shadow", …)` never reach the allowance.

In the module docstring, replace "own: `banned` (box-shadow, gradients, transitions, transforms, opacity --
each a seam the Qt tier cannot match)" with:

```
own: `banned` (gradients, transitions, transforms, opacity -- each a seam the
Qt tier cannot match -- and box-shadow, unless its whole value is one of the
theme's two shadow tokens or `none`: ADR 0016)
```

- [ ] **Step 4: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_style_lint.py tests/test_style_literals_guard.py`
Expected: PASS, including the existing `test_a_box_shadow_in_a_stylesheet_is_flagged`.

- [ ] **Step 5: Commit**

`/usr/bin/git add shared/style_lint.py tests/test_style_lint.py`, message
"Style lint: box-shadow passes only as a shadow token or none (ADR 0016)".

---

### Task 3: The web kit (`gui/web/kit.css`) and its sheet

**Files:**
- Create: `gui/web/kit.css`, `tests/web/kit_sheet.html`, `tests/test_web_kit.py`
- Modify: `gui/web/results.html` (the `<head>`), `gui/web/results.css` (delete what the kit now owns)
- Modify: `tests/test_results_document.py` (the two z-index tests, lines 426-448),
  `tests/test_results_bridge.py` (two body-colour assertions)

**Interfaces:**
- Consumes: the seven CSS variables from Task 1; the lint allowance from Task 2.
- Produces: the classes in spec §4.2, used by every later task: `.card`, `.btn` with `.primary` `.secondary`
  `.ghost` `.dashed` `.danger` `.critical` `.icon` `.compact` `.link`, `.badge` with `.success` `.danger`
  `.warning` `.info` `.neutral`, `.code`, `.input`, `.field`, the checkbox, `.segmented` / `.segment` /
  `.segment-count`, `.menu-anchor`, `.menu`, `.menu-group`, `.menu-item`, `.menu-separator`, `.menu-hint`,
  `.check`, `.popover`, `.toast` / `.toast-text` / `.toast-badge` / `.toast-action` / `.toast-close`,
  `.banner` (`.danger`, `.neutral`) / `.banner-body` / `.banner-title` / `.banner-text` / `.banner-actions`,
  `.state` / `.state-glyph` / `.state-title` / `.state-text`, `.page-head` / `.page-title` / `.page-meta`,
  `.spacer`, `.mono`, `.glyph`; the variables `--kit-radius`, `--kit-radius-card`, `--kit-control-compact`,
  `--z-sticky`, `--z-header`, `--z-bar`, `--z-popover`, `--z-toast`.

- [ ] **Step 1: Write the kit sheet**

Create `tests/web/kit_sheet.html`. It is a test fixture: its own `<style>` block lays the samples out and may
use any CSS it likes, because nothing under `tests/` is linted or shipped.

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Web kit sheet</title>
<style id="theme-vars">/* theme-vars */</style>
<link rel="stylesheet" href="kit.css">
<style>
  body { overflow: auto; }
  main { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; padding: 16px 24px 20px; }
  section { display: flex; flex-direction: column; gap: 8px; padding: 10px 12px; }
  .row { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
  .stage { position: relative; height: 72px; }
  section > .menu { position: static; }
  h2 { margin: 0; font-size: var(--type-label-size); }
</style>
</head>
<body>
<main>
  <div class="page-head" style="grid-column: 1 / -1">
    <span class="page-title">Components</span>
    <span class="code">2026-09-30_1</span>
    <span class="page-meta">ACME · opened 14:02</span>
    <span class="spacer"></span>
    <button class="btn secondary" type="button">Secondary</button>
    <button class="btn primary" type="button">Primary</button>
  </div>

  <section class="card">
    <h2>Buttons</h2>
    <div class="row">
      <button id="b-primary" class="btn primary" type="button">Export 30 orders</button>
      <button id="b-secondary" class="btn secondary" type="button">Add filter</button>
      <button id="b-ghost" class="btn ghost" type="button">Plain</button>
      <button id="b-dashed" class="btn dashed" type="button">Add filter</button>
      <button id="b-danger" class="btn danger" type="button">Write off stock</button>
      <button id="b-ghost-danger" class="btn ghost danger" type="button">Exclude order</button>
      <button id="b-critical" class="btn critical" type="button">Remove 3 orders</button>
    </div>
    <div class="row">
      <button id="b-disabled" class="btn primary" type="button" disabled>Export 0 orders</button>
      <button id="b-compact" class="btn secondary compact" type="button">Hold these 3</button>
      <button id="b-icon" class="btn ghost icon" type="button" aria-label="More">⋯</button>
      <button id="b-link" class="btn link" type="button">Map columns</button>
    </div>
  </section>

  <section class="card">
    <h2>Badges</h2>
    <div class="row">
      <span id="g-success" class="badge success">Fulfillable</span>
      <span id="g-danger" class="badge danger">Blocked</span>
      <span id="g-warning" class="badge warning">2 stock left</span>
      <span id="g-info" class="badge info">Repeat</span>
      <span id="g-neutral" class="badge neutral">Lot L-2409</span>
      <span id="g-code" class="code">STOCK_SHORT</span>
    </div>
    <h2>Segmented control</h2>
    <div class="segmented" role="radiogroup" aria-label="Status">
      <button id="s-on" class="segment" type="button" role="radio" aria-checked="true">All <span class="segment-count">40</span></button>
      <button id="s-off" class="segment" type="button" role="radio" aria-checked="false">Fulfillable <span class="segment-count">30</span></button>
      <button class="segment" type="button" role="radio" aria-checked="false">Blocked <span class="segment-count">10</span></button>
    </div>
  </section>

  <section class="card">
    <h2>Inputs</h2>
    <label id="i-search" class="input">
      <svg class="glyph" viewBox="0 0 24 24" aria-hidden="true"><path d="M19 11a8 8 0 1 1-16 0 8 8 0 0 1 16 0zM21 21l-4.3-4.3"/></svg>
      <input type="search" placeholder="Order, customer or SKU">
    </label>
    <label id="i-invalid" class="input invalid"><input type="text" value="1O42"></label>
    <input id="i-field" class="field" type="text" placeholder="New tag">
    <div class="row">
      <input id="c-off" type="checkbox" aria-label="Unchecked">
      <input id="c-on" type="checkbox" checked aria-label="Checked">
      <input id="c-mixed" type="checkbox" aria-label="Mixed">
      <input id="c-disabled" type="checkbox" checked disabled aria-label="Disabled">
    </div>
  </section>

  <section class="card">
    <h2>Menu</h2>
    <div class="menu" role="menu">
      <div class="menu-group">Status</div>
      <button class="menu-item" type="button" role="menuitemcheckbox" aria-checked="true"><svg class="check" viewBox="0 0 24 24" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>Fulfillable</button>
      <button id="m-item" class="menu-item" type="button" role="menuitem">Copy 3 order numbers<span class="menu-hint">Ctrl+C</span></button>
      <div class="menu-separator"></div>
      <button id="m-danger" class="menu-item danger" type="button" role="menuitem">Remove a SKU from these 3 orders</button>
    </div>
  </section>

  <section class="card">
    <h2>State panel</h2>
    <div class="state">
      <svg class="state-glyph" viewBox="0 0 24 24" aria-hidden="true"><path d="M19 11a8 8 0 1 1-16 0 8 8 0 0 1 16 0zM21 21l-4.3-4.3M13.5 8.5l-5 5M8.5 8.5l5 5"/></svg>
      <p class="state-title">No orders match</p>
      <p class="state-text">Status is Blocked and Courier is DPD.</p>
      <button class="btn secondary" type="button">Clear filters</button>
    </div>
  </section>

  <section>
    <div id="n-danger" class="banner danger">
      <svg class="glyph" viewBox="0 0 24 24" aria-hidden="true"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3M12 9v4M12 17h.01"/></svg>
      <div class="banner-body">
        <div class="banner-title">Stock export could not be read</div>
        <div class="banner-text">acme-stock-30-09.csv has no SKU column. Found: Code, Qty, Lot.</div>
        <div class="banner-actions">
          <button class="btn secondary compact" type="button">Choose another file</button>
          <button class="btn ghost compact" type="button">Map columns</button>
        </div>
      </div>
    </div>
    <div id="n-neutral" class="banner neutral">
      <div class="banner-body">
        <div class="banner-title">Open a session to use these tools</div>
        <div class="banner-text">Both tools read the session's files and save into its folder.</div>
      </div>
      <button class="btn primary" type="button">New session</button>
    </div>
    <div class="stage">
      <div id="t-toast" class="toast" role="status">
        <span class="toast-text">Packing lists saved for 30 orders</span>
        <span class="toast-badge">3</span>
        <button class="toast-action" type="button">Undo</button>
        <button class="toast-close" type="button" aria-label="Dismiss"><svg class="glyph" viewBox="0 0 24 24" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg></button>
      </div>
    </div>
  </section>
</main>
<script>document.getElementById("c-mixed").indeterminate = true;</script>
</body>
</html>
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_web_kit.py`:

```python
"""The web kit (phase 2 spec section 4), through a real Chromium. Never mark skip."""

import re
from pathlib import Path

import pytest
from PySide6.QtCore import QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView
from test_results_bridge import _eval, _rgb, _until_js

from gui.results_bridge import PAGE, THEME_MARKER, WEB_DIR
from shared.theme import DARK_THEME, LIGHT_THEME, theme_css_vars

SHEET = Path(__file__).resolve().parent / "web" / "kit_sheet.html"
KIT = WEB_DIR / "kit.css"
RESULTS_CSS = WEB_DIR / "results.css"

THEMES = pytest.mark.parametrize(
    "theme", [LIGHT_THEME, DARK_THEME], ids=["light", "dark"]
)


def _sheet(qtbot, theme):
    view = QWebEngineView()
    qtbot.addWidget(view)
    html = SHEET.read_text(encoding="utf-8").replace(
        THEME_MARKER, theme_css_vars(theme)
    )
    view.setHtml(html, QUrl.fromLocalFile(str(WEB_DIR) + "/"))
    view.resize(1166, 720)
    view.show()
    # The stylesheet loads after the document: wait for a kit rule to apply.
    _until_js(
        qtbot,
        view,
        "!!document.querySelector('.card') && getComputedStyle("
        "document.querySelector('.card')).borderTopLeftRadius === '12px'",
    )
    return view


def _style(qtbot, view, selector, prop):
    return _eval(
        qtbot, view, f"getComputedStyle(document.querySelector({selector!r})).{prop}"
    )


def _selectors(css: str) -> list[str]:
    """Every selector list in a stylesheet, comments removed."""
    code = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    return [s.strip() for s in re.findall(r"([^{}]+)\{", code) if s.strip()]


def test_results_links_the_kit_before_its_own_stylesheet():
    html = PAGE.read_text(encoding="utf-8")
    assert 'href="kit.css"' in html
    assert html.index('href="kit.css"') < html.index('href="results.css"')


def test_the_kit_names_no_page():
    """Components only: an #id in the kit means a page leaked into it."""
    with_ids = [s for s in _selectors(KIT.read_text(encoding="utf-8")) if "#" in s]
    assert with_ids == []


def test_the_layer_scale_lives_in_the_kit_and_orders_the_layers():
    """A popover must never open underneath the selection bar, and the toast
    sits over everything. One scale for every page."""
    text = KIT.read_text(encoding="utf-8")
    z = {n: int(v) for n, v in re.findall(r"--z-([a-z]+):\s*(\d+)", text)}
    assert z["popover"] > z["bar"] > z["header"] > z["sticky"]
    assert z["toast"] > z["popover"]


@pytest.mark.parametrize("path", [KIT, RESULTS_CSS], ids=["kit", "results"])
def test_no_bare_z_index_survives(path):
    bare = re.findall(r"z-index:\s*(\d+)", path.read_text(encoding="utf-8"))
    assert bare == [], f"z-index must come from the layer scale, found {bare}"


@THEMES
def test_a_card_casts_a_shadow_in_light_and_draws_an_edge_in_dark(qtbot, theme):
    view = _sheet(qtbot, theme)
    shadow = _style(qtbot, view, ".card", "boxShadow")
    assert (shadow == "none") is (theme.name == "dark")
    assert _style(qtbot, view, ".card", "backgroundColor") == _rgb(theme.surface)


@THEMES
def test_each_button_role_takes_its_tokens(qtbot, theme):
    view = _sheet(qtbot, theme)
    assert _style(qtbot, view, "#b-primary", "backgroundColor") == _rgb(theme.accent_fill)
    assert _style(qtbot, view, "#b-primary", "color") == _rgb(theme.on_accent)
    assert _style(qtbot, view, "#b-secondary", "borderTopColor") == _rgb(theme.border)
    assert _style(qtbot, view, "#b-dashed", "borderTopStyle") == "dashed"
    assert _style(qtbot, view, "#b-danger", "color") == _rgb(theme.status_danger)
    assert _style(qtbot, view, "#b-critical", "backgroundColor") == _rgb(theme.critical_fill)
    assert _style(qtbot, view, "#b-critical", "color") == _rgb(theme.on_critical)
    assert _style(qtbot, view, "#b-compact", "height") == "24px"


@THEMES
def test_a_disabled_button_drops_its_fill_and_dashes_its_edge(qtbot, theme):
    view = _sheet(qtbot, theme)
    assert _style(qtbot, view, "#b-disabled", "borderTopStyle") == "dashed"
    assert _style(qtbot, view, "#b-disabled", "backgroundColor") == _rgb(
        theme.control_disabled_bg
    )
    assert _style(qtbot, view, "#b-disabled", "boxShadow") == "none"


@THEMES
def test_a_badge_is_a_tinted_pill_with_no_outline(qtbot, theme):
    view = _sheet(qtbot, theme)
    for role in ("success", "danger", "warning", "info"):
        selector = f"#g-{role}"
        assert _style(qtbot, view, selector, "backgroundColor") == _rgb(
            getattr(theme, f"status_{role}_bg")
        )
        assert _style(qtbot, view, selector, "color") == _rgb(
            getattr(theme, f"status_{role}")
        )
    assert _style(qtbot, view, "#g-success", "height") == "20px"
    assert _style(qtbot, view, "#g-neutral", "borderTopColor") == _rgb(theme.border_subtle)


@THEMES
def test_the_checked_segment_is_raised_and_the_rest_are_quiet(qtbot, theme):
    view = _sheet(qtbot, theme)
    assert _style(qtbot, view, "#s-on", "backgroundColor") == _rgb(theme.surface)
    assert _style(qtbot, view, "#s-on", "fontWeight") == "700"
    assert _style(qtbot, view, "#s-off", "color") == _rgb(theme.text_secondary)
    assert _style(qtbot, view, ".segmented", "backgroundColor") == _rgb(theme.surface_sunken)


@THEMES
def test_the_banner_and_the_toast_take_their_planes(qtbot, theme):
    view = _sheet(qtbot, theme)
    assert _style(qtbot, view, "#n-danger", "backgroundColor") == _rgb(theme.status_danger_bg)
    assert _style(qtbot, view, "#n-danger", "borderTopColor") == _rgb(
        theme.status_danger_border
    )
    assert _style(qtbot, view, "#n-neutral", "backgroundColor") == _rgb(theme.surface)
    assert _style(qtbot, view, "#t-toast", "backgroundColor") == _rgb(theme.surface_inverse)
    assert _style(qtbot, view, "#t-toast", "color") == _rgb(theme.on_inverse)


@THEMES
def test_a_checkbox_fills_with_the_accent_when_checked_or_mixed(qtbot, theme):
    view = _sheet(qtbot, theme)
    assert _style(qtbot, view, "#c-off", "backgroundColor") == _rgb(theme.surface)
    assert _style(qtbot, view, "#c-off", "borderTopColor") == _rgb(theme.border)
    for box in ("#c-on", "#c-mixed"):
        assert _style(qtbot, view, box, "backgroundColor") == _rgb(theme.accent_fill)
    assert _style(qtbot, view, "#c-off", "width") == "16px"


@THEMES
def test_an_input_and_a_menu_take_their_edges(qtbot, theme):
    view = _sheet(qtbot, theme)
    assert _style(qtbot, view, "#i-search", "borderTopColor") == _rgb(theme.border)
    assert _style(qtbot, view, "#i-invalid", "backgroundColor") == _rgb(theme.status_danger_bg)
    assert _style(qtbot, view, ".menu", "backgroundColor") == _rgb(theme.surface_overlay)
    assert _style(qtbot, view, ".menu", "borderTopColor") == _rgb(theme.border_subtle)
    assert _style(qtbot, view, "#m-danger", "color") == _rgb(theme.status_danger)
    assert _style(qtbot, view, ".page-title", "fontWeight") == "700"
```

The kit paints `body` in `surface_sunken`, so two tests in `tests/test_results_bridge.py` change their
expected colour from `surface` to `surface_sunken`: `test_the_first_paint_is_already_themed` (its last line
becomes `== _rgb(LIGHT_THEME.surface_sunken)`) and `test_a_theme_switch_repaints_the_document_without_a_reload`
(its `_until_js` compares with `_rgb(DARK_THEME.surface_sunken)`).

Delete `_layers`, `test_a_popover_is_never_covered_by_the_selection_bar` and
`test_no_bare_z_index_survives_in_results_css` from `tests/test_results_document.py` (lines 426-448, and the
`_CSS` constant above them): the three tests above replace them. Remove the `re` and `Path` imports from that
file if nothing else uses them (`ruff check tests/test_results_document.py` says).

- [ ] **Step 3: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_web_kit.py`
Expected: FAIL. `kit.css` does not exist, so `test_results_links_the_kit...` fails on the missing `href` and
every sheet test times out waiting for the 12px radius.

- [ ] **Step 4: Write `gui/web/kit.css`**

```css
/* The web kit: what every web page shares (phase 2 spec section 4, ADR 0016).
   Components only -- no page layout and no #id. Every colour is a token from
   theme_css_vars(). A box-shadow is one of the theme's two shadow tokens or
   none, and nothing else (shared/style_lint.py). Lines: a decorative edge is
   --border-subtle, the edge of a control is --border (ADR 0018). */

/* Chromium cannot see fonts registered with Qt's QFontDatabase, so the
   bundled Inter the Qt tier renders in is declared again here. The relative
   path holds in the dev tree and under _internal/ in the --onedir build. */
@font-face {
  font-family: "Inter";
  font-weight: 400;
  src: url("../../shared/assets/fonts/Inter-Regular.ttf");
}
@font-face {
  font-family: "Inter";
  font-weight: 700;
  src: url("../../shared/assets/fonts/Inter-Bold.ttf");
}

*, *::before, *::after { box-sizing: border-box; }

/* Geometry the theme does not own, and the one layer scale every page
   stacks by. Two surfaces used to tie at 3 -- a menu and the selection bar --
   and document order put the menu underneath. */
:root {
  --kit-radius: 8px;
  --kit-radius-card: 12px;
  --kit-control-compact: 24px;
  --z-sticky: 1;
  --z-header: 2;
  --z-bar: 3;
  --z-popover: 5;
  --z-toast: 6;
}

html, body { margin: 0; height: 100%; }

body {
  overflow: hidden;
  background: var(--surface-sunken);
  color: var(--text);
  font-family: var(--font-family);
  font-size: var(--type-body-size);
  font-variant-numeric: tabular-nums;
}

button, input { font: inherit; color: inherit; }

[hidden] { display: none !important; }

/* --- utilities ----------------------------------------------------------- */

.spacer { flex: 1 1 auto; }
.mono { font-family: var(--font-family-mono); }

.glyph {
  flex-shrink: 0;
  width: 14px;
  height: 14px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.75;
  stroke-linecap: round;
  stroke-linejoin: round;
  vertical-align: middle;
}

/* --- card ---------------------------------------------------------------- */

.card {
  background: var(--surface);
  border: 1px solid var(--card-border);
  border-radius: var(--kit-radius-card);
  box-shadow: var(--card-shadow);
}

/* --- buttons ------------------------------------------------------------- */

.btn {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: var(--control-height);
  padding: 0 12px;
  border: 1px solid transparent;
  border-radius: var(--kit-radius);
  background: transparent;
  font-weight: 700;
  white-space: nowrap;
  cursor: pointer;
}

.btn.primary {
  background: var(--accent-fill);
  color: var(--on-accent);
  box-shadow: var(--card-shadow);
}
.btn.primary:hover { background: var(--accent-fill-hover); }
.btn.primary:active { background: var(--accent-fill-active); }

.btn.secondary {
  border-color: var(--border);
  background: var(--surface);
  box-shadow: var(--card-shadow);
}
.btn.secondary:hover { background: var(--hover); }
.btn.secondary:active { background: var(--selection-bg); }

.btn.ghost:hover { background: var(--hover); }

.btn.dashed { border: 1px dashed var(--border); }
.btn.dashed:hover { background: var(--surface); }

.btn.danger {
  border-color: var(--border);
  background: var(--surface);
  color: var(--status-danger);
  box-shadow: var(--card-shadow);
}
.btn.danger:hover, .btn.danger:active { background: var(--status-danger-bg); }
.btn.ghost.danger {
  border-color: transparent;
  background: transparent;
  box-shadow: none;
}
.btn.ghost.danger:hover { background: var(--status-danger-bg); }

.btn.critical { background: var(--critical-fill); color: var(--on-critical); }

.btn.icon { width: var(--control-height); padding: 0; }
.btn.compact { height: var(--kit-control-compact); padding: 0 10px; }
.btn.compact.icon { width: var(--kit-control-compact); padding: 0; }

/* A link in a sentence: no box, just the underline. */
.btn.link { height: auto; padding: 0; border: 0; text-decoration: underline; }

/* The component sheet's disabled button: a dropped fill and a dashed edge.
   After every role, so it wins at equal specificity. */
.btn:disabled,
.btn:disabled:hover {
  border: 1px dashed var(--border);
  background: var(--control-disabled-bg);
  color: var(--text-disabled);
  box-shadow: none;
  cursor: not-allowed;
}

/* --- badges -------------------------------------------------------------- */

.badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 20px;
  padding: 0 8px;
  border: 1px solid transparent;
  border-radius: var(--radius-lg);
  font-size: var(--type-caption-size);
  font-weight: 700;
  line-height: 1;
  white-space: nowrap;
  vertical-align: middle;
}
.badge.success { background: var(--status-success-bg); color: var(--status-success); }
.badge.danger { background: var(--status-danger-bg); color: var(--status-danger); }
.badge.warning { background: var(--status-warning-bg); color: var(--status-warning); }
.badge.info { background: var(--status-info-bg); color: var(--status-info); }
.badge.neutral {
  background: var(--surface-raised);
  border-color: var(--border-subtle);
  color: var(--text-secondary);
}

/* A machine word: a reason code, a session id. */
.code {
  display: inline-flex;
  align-items: center;
  height: 20px;
  padding: 0 6px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  background: var(--surface-raised);
  color: var(--text-secondary);
  font-family: var(--font-family-mono);
  font-size: var(--type-caption-size);
  line-height: 1;
  white-space: nowrap;
}

/* --- inputs -------------------------------------------------------------- */

/* A label wrapping a glyph and its <input>. */
.input {
  display: flex;
  align-items: center;
  gap: 6px;
  height: var(--control-height);
  padding: 0 8px;
  border: 1px solid var(--border);
  border-radius: var(--kit-radius);
  background: var(--surface);
  color: var(--text-placeholder);
}
.input input {
  flex: 1;
  min-width: 0;
  height: 100%;
  padding: 0;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--text);
}
.input input::placeholder { color: var(--text-placeholder); }
.input:focus-within { outline: 2px solid var(--focus-ring); outline-offset: 1px; }
.input.invalid { border-color: var(--status-danger); background: var(--status-danger-bg); }

/* A bare <input>, where there is no glyph to wrap. */
.field {
  height: var(--control-height);
  padding: 0 var(--padding-h);
  border: 1px solid var(--border);
  border-radius: var(--kit-radius);
  background: var(--surface);
}
.field::placeholder { color: var(--text-placeholder); }
.field:focus { outline: 2px solid var(--focus-ring); outline-offset: -1px; }

/* The tick and the bar are clipped shapes: the web tier may not rotate
   anything (ADR 0001), so no bordered box turned 45 degrees. */
input[type="checkbox"] {
  appearance: none;
  flex-shrink: 0;
  position: relative;
  width: 16px;
  height: 16px;
  margin: 0;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  vertical-align: middle;
  cursor: pointer;
}
input[type="checkbox"]::after {
  content: "";
  position: absolute;
  display: none;
  background: var(--on-accent);
}
input[type="checkbox"]:checked,
input[type="checkbox"]:indeterminate {
  border-color: transparent;
  background: var(--accent-fill);
}
input[type="checkbox"]:checked::after {
  display: block;
  inset: 2px;
  clip-path: polygon(14% 44%, 0 65%, 50% 100%, 100% 16%, 80% 0%, 43% 62%);
}
input[type="checkbox"]:indeterminate::after {
  display: block;
  inset: 6px 3px;
  clip-path: none;
}
input[type="checkbox"]:disabled {
  border: 1px dashed var(--border);
  background: var(--control-disabled-bg);
  cursor: not-allowed;
}
input[type="checkbox"]:disabled::after { background: var(--text-disabled); }

/* --- segmented control --------------------------------------------------- */

.segmented {
  display: inline-flex;
  align-self: flex-start;
  gap: 2px;
  padding: 2px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--kit-radius);
  background: var(--surface-sunken);
}
.segment {
  display: flex;
  align-items: center;
  gap: 6px;
  height: 24px;
  padding: 0 10px;
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--text-secondary);
  white-space: nowrap;
  cursor: pointer;
}
.segment[aria-checked="true"] {
  border-color: var(--card-border);
  background: var(--surface);
  color: var(--text);
  font-weight: 700;
  box-shadow: var(--card-shadow);
}
.segment-count {
  font-family: var(--font-family-mono);
  font-size: var(--type-caption-size);
  font-weight: 400;
  color: var(--text-secondary);
}

/* --- menus and popovers -------------------------------------------------- */

.menu-anchor { position: relative; flex-shrink: 0; }

.menu, .popover {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  z-index: var(--z-popover);
  background: var(--surface-overlay);
  border: 1px solid var(--border-subtle);
  border-radius: var(--kit-radius-card);
  box-shadow: var(--overlay-shadow);
}
.menu {
  min-width: 220px;
  max-height: 360px;
  overflow-y: auto;
  padding: 6px;
}
/* A titled panel with its own head and foot. */
.popover { display: flex; flex-direction: column; }

.menu-group {
  padding: 4px 10px;
  font-size: var(--type-caption-size);
  font-weight: 700;
  color: var(--text-secondary);
}
.menu-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  width: 100%;
  height: 30px;
  padding: 0 10px;
  border: 0;
  border-radius: var(--radius-md);
  background: transparent;
  text-align: left;
  white-space: nowrap;
  cursor: pointer;
}
.menu-item:hover { background: var(--hover); }
.menu-item.danger { color: var(--status-danger); }
.menu-item:disabled,
.menu-item:disabled:hover {
  background: transparent;
  color: var(--text-disabled);
  cursor: not-allowed;
}
.menu-separator { height: 1px; margin: 5px 0; background: var(--border-subtle); }
.menu-hint { margin-left: auto; padding-left: var(--spacing-md); color: var(--text-secondary); }

.check {
  flex-shrink: 0;
  width: 12px;
  height: 12px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  visibility: hidden;
}
.menu-item[aria-checked="true"] .check { visibility: visible; }

/* --- toast (ADR 0007: a web page draws its own) -------------------------- */

.toast {
  position: absolute;
  right: 24px;
  bottom: 24px;
  z-index: var(--z-toast);
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 40px;
  max-width: 480px;
  padding: 6px 8px 6px 14px;
  border-radius: var(--kit-radius);
  background: var(--surface-inverse);
  color: var(--on-inverse);
  box-shadow: var(--overlay-shadow);
}
.toast-badge {
  min-width: 18px;
  padding: 0 var(--spacing-xs);
  border: 1px solid var(--on-inverse);
  border-radius: var(--radius-sm);
  font-size: var(--type-caption-size);
  text-align: center;
}
.toast-action, .toast-close {
  flex-shrink: 0;
  height: 26px;
  border: 0;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--on-inverse);
  cursor: pointer;
}
.toast-action { padding: 0 8px; font-weight: 700; text-decoration: underline; }
.toast-close { display: grid; place-items: center; width: 26px; padding: 0; }

/* --- banner -------------------------------------------------------------- */

.banner {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid transparent;
  border-radius: var(--kit-radius-card);
}
.banner.danger {
  background: var(--status-danger-bg);
  border-color: var(--status-danger-border);
}
.banner.danger > .glyph { width: 18px; height: 18px; color: var(--status-danger); }
.banner.neutral {
  align-items: center;
  background: var(--surface);
  border-color: var(--card-border);
  box-shadow: var(--card-shadow);
}
.banner-body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.banner-title { font-weight: 700; }
.banner.neutral .banner-text { color: var(--text-secondary); }
.banner-actions { display: flex; gap: 6px; }

/* --- state panel --------------------------------------------------------- */

.state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: var(--spacing-xl);
  text-align: center;
}
.state-glyph {
  width: 22px;
  height: 22px;
  fill: none;
  stroke: var(--text-secondary);
  stroke-width: 1.5;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.state-title { margin: 0; font-size: var(--type-label-size); font-weight: 700; }
.state-text { margin: 0; max-width: 380px; color: var(--text-secondary); }
.state .btn { margin-top: 4px; }

/* --- page header --------------------------------------------------------- */

.page-head { display: flex; align-items: center; gap: 10px; min-height: 28px; }
.page-title { font-size: var(--type-heading-size); font-weight: 700; }
.page-meta { font-size: var(--type-caption-size); color: var(--text-secondary); }
.page-head .code { height: 22px; padding: 0 8px; color: var(--text); }

/* --- focus --------------------------------------------------------------- */

.btn:focus-visible,
.segment:focus-visible,
.menu-item:focus-visible,
.toast-action:focus-visible,
.toast-close:focus-visible,
input[type="checkbox"]:focus-visible {
  outline: 2px solid var(--focus-ring);
  outline-offset: 1px;
}
```

- [ ] **Step 5: Link the kit and take its rules out of `results.css`**

In `gui/web/results.html`, add the kit's link on the line above `<link rel="stylesheet" href="results.css">`:

```html
<link rel="stylesheet" href="kit.css">
```

In `gui/web/results.css`, delete every rule the kit now owns. By its current line numbers:

- lines 5-19: the comment about Chromium fonts, both `@font-face` blocks, and the `box-sizing` reset;
- lines 24-27 (the comment about the `--z-*` scale) and the five `--z-*` declarations at lines 30-34. Keep
  `:root { --table-head-height: 28px; }` and the comment above it (lines 21-23);
- lines 37-50: `html, body`, `body`, `button, input`, `[hidden]`;
- line 143: `.spacer`;
- lines 151-177: `.btn` and its variants, and the `:focus-visible` group. Keep `.chip-filter:focus-visible`
  as its own rule: `.chip-filter:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 1px; }`;
- lines 179-228: `.menu-anchor`, `.menu`, `.menu-group`, `.menu-item` and its states, `.menu-separator`,
  `.menu-hint`, `.check`;
- lines 323-347: the toast comment, `.toast`, `.toast-badge`;
- lines 463-474: `.state`, `.state-title`, `.state-text`. In their place put the Results-specific placement:
  `.table-wrap > .state { position: absolute; inset: 0; }`;
- line 494: `.glyph`;
- lines 604-612: `.btn.secondary`, `.btn.danger` and their `:focus-visible` group. Keep
  `.tag-chip:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 1px; }`.

Update the file's first comment to: "The results page: what is Results' alone. Components come from kit.css,
which the page links first (phase 2 spec section 4). Every value is a token from theme_css_vars()."

Then make the page's existing markup name kit classes where a class it used is gone:

- `gui/web/results.html`: `#toast-undo` becomes `class="toast-action"` (it was `btn ghost`).
- `gui/web/results.css`: `.btn.small { ... }` (line 564) is deleted; `gui/web/pane.js` line 189 changes
  `paneButton("ghost small", "+ Tag")` to `paneButton("ghost compact", "+ Tag")`.
- `.pane-menu .new-tag`, `.bulk-list .new-tag`, `.bulk-list .bulk-search` and `.columns-search` keep their
  rules for now; Tasks 8 to 10 move them onto `.field`.

- [ ] **Step 6: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_web_kit.py tests/test_style_literals_guard.py tests/test_style_lint.py tests/test_results_bridge.py tests/test_results_document.py tests/test_results_pane.py tests/test_results_columns.py tests/test_results_selection_bar.py tests/test_results_bulk_popover.py tests/test_results_toast.py`
Expected: PASS. The page is half-dressed after this task (kit buttons and menus on the old layout, a grey
page behind white panels); Tasks 4 to 10 finish it. If a results test fails, it pinned a look the kit
changed: fix the test to the kit's value only when spec §4.2 gives that value, otherwise the kit is wrong.

If `test_a_checkbox_fills_with_the_accent_when_checked_or_mixed` fails on `#c-mixed`, Chromium did not apply
`:indeterminate` before the read: the sheet sets it in a script at the end of `<body>`, so wait for it with
`_until_js(qtbot, view, "document.getElementById('c-mixed').indeterminate === true")` first.

- [ ] **Step 7: Look at it**

Write a throwaway script under your job's tmp dir that does what `_sheet` does for each theme and saves
`view.grab()` to a PNG (wait 500 ms after the radius check so fonts settle), run it with
`QT_QPA_PLATFORM=offscreen QTWEBENGINE_DISABLE_SANDBOX=1 .venv/bin/python <script>`, and Read both PNGs. Compare
with `docs/design/ui-refresh/mockups/renders/component-sheet.png`. Check in particular: the tick and the bar
inside the checkboxes are centred and readable; the disabled button is dashed; in dark the cards have an edge
and no shadow. If the tick is misshapen, adjust the `clip-path` polygon and the `inset`, nothing else.

- [ ] **Step 8: Commit**

`/usr/bin/git add gui/web/kit.css gui/web/results.html gui/web/results.css gui/web/pane.js tests/web/kit_sheet.html tests/test_web_kit.py tests/test_results_document.py tests/test_results_bridge.py`,
message "Web kit: kit.css, its sheet, and results.css shedding what the kit owns".

---
### Task 4: Page frame, the split card and the table

**Files:**
- Modify: `gui/web/results.html` (`#table-area`, `#pane-strip`), `gui/web/results.css` (the `:root`, the page
  section, the slot rules, the table rules, the status chip section, the pane's plane and strip rules),
  `gui/web/results.js` (constants, `measureColumns`, `layout`, `slotMode`, `renderSlot`, `renderHeader`,
  `cellElement`, the `summaryChanged` handler), `gui/web/columns.js` (the registry's widths), `gui/web/pane.js`
  (`bindPane`), `gui/ui_manager.py` (`create_widgets`, `_create_tabs`)
- Test: `tests/test_results_document.py`, `tests/test_results_pane.py`, `tests/test_results_columns.py`,
  `tests/test_shell.py`

**Interfaces:**
- Consumes: `.card`, `.badge`, the z scale from Task 3.
- Produces: `data-slot` values `pane` / `rail` / `columns` / `none` (`columns` goes in Task 9);
  `statusBadge(o) -> HTMLSpanElement` in `results.js`; the CSS variable `--results-row-height` set on `#table`;
  `state.rowH` = density row + 4; `PANE_PX = 340`, `TABLE_MIN_PX = 728`; `mw.page_area` (the `QWidget` whose
  layout holds the error banner and `main_tabs`); `UIManager._apply_page_inset(index: int)`.

Arithmetic the tests below rely on, for the `doc` fixture's 1310×692 view: page padding takes 48 of width and
36 of height. Height: 692 − 36 − 88 (KPI row) − 32 (filter row, `--control-height` at desk) − 24 (two gaps)
= 512 for the card; its two 1px edges leave `clientHeight` 510; minus the 36px header leaves 474, which holds
14 rows of 32. Width: 1310 − 48 = 1262; the card's edges leave 1260; the slot takes 340 (pane) or 40 (rail),
so the table is 920 or 1220 wide. The slot's own left edge takes 1px, so the pane inside it is 339 wide.

- [ ] **Step 1: Rewrite the tests that pin the old geometry, and add the new ones**

In `tests/test_results_document.py`, add `from gui.theme_manager import get_theme_manager` and
`from shared.theme import LIGHT_THEME` and `from test_results_bridge import _rgb` to the imports (extend the
existing `from test_results_bridge import _eval, _until_js` line), then replace
`test_17_whole_rows_at_1366`, `test_28_whole_rows_at_1920` and `test_only_a_window_of_rows_exists` with:

```python
def test_14_whole_rows_at_1366(qtbot, doc):
    """692 high: 36 of page padding, 88 of KPI, 32 of filter bar and two 12px
    gaps leave a 512px card. Its edges leave 510, the header takes 36, and
    474 holds 14 rows of 32."""
    view, _ = doc
    _until_js(
        qtbot, view, "document.getElementById('table').dataset.visibleRows === '14'"
    )
    assert (
        _eval(qtbot, view, "document.getElementById('scroller').clientHeight")
        == 36 + 14 * 32
    )


def test_24_whole_rows_at_1920(qtbot, doc):
    view, _ = doc
    _resize(qtbot, view, 1864, 1004)
    _until_js(
        qtbot, view, "document.getElementById('table').dataset.visibleRows === '24'"
    )


def test_only_a_window_of_rows_exists(qtbot, doc):
    view, _ = doc
    assert (
        _eval(qtbot, view, "document.querySelectorAll('#rows .row').length") <= 14 + 8
    )
    _eval(qtbot, view, "document.getElementById('scroller').scrollTop = 32 * 150; true")
    _until_js(qtbot, view, "!!document.querySelector('#rows .row[data-index=\"150\"]')")
    assert (
        _eval(qtbot, view, "document.querySelectorAll('#rows .row').length") <= 14 + 8
    )


def test_the_header_is_36_tall_and_a_row_32(qtbot, doc):
    view, _ = doc
    assert _eval(qtbot, view, "document.getElementById('header').offsetHeight") == 36
    assert _eval(qtbot, view, "document.querySelector('#rows .row').offsetHeight") == 32


def test_floor_density_rows_are_four_taller_than_the_token(qtbot, doc):
    """Review focus 4: the +4 holds in both densities, and the row maths follows."""
    view, _ = doc
    get_theme_manager().set_density("floor")  # conftest restores desk
    _until_js(qtbot, view, "document.querySelector('#rows .row').offsetHeight === 44")
    rows = int(
        _eval(qtbot, view, "document.getElementById('table').dataset.visibleRows")
    )
    assert (
        _eval(qtbot, view, "document.getElementById('scroller').clientHeight")
        == 36 + rows * 44
    )


def test_the_table_and_the_pane_share_one_card(qtbot, doc):
    view, _ = doc
    area = "document.getElementById('table-area')"
    assert _eval(qtbot, view, f"{area}.classList.contains('card')") is True
    assert _eval(qtbot, view, f"{area}.contains(document.getElementById('pane'))") is True
    assert _eval(
        qtbot, view, "getComputedStyle(document.body).backgroundColor"
    ) == _rgb(LIGHT_THEME.surface_sunken)


def test_the_status_is_a_badge(qtbot, doc):
    view, _ = doc
    blocked = "document.querySelector('#rows .row[data-order=\"#10004\"] .status .badge')"
    ready = "document.querySelector('#rows .row[data-order=\"#10001\"] .status .badge')"
    assert _eval(qtbot, view, f"{blocked}.className") == "badge danger"
    assert _eval(qtbot, view, f"{ready}.className") == "badge success"
    # A repeat order wears an info badge in its Repeat cell.
    assert (
        _eval(
            qtbot,
            view,
            "cellElement({key: 'repeat', text: function () { return 'Repeat'; }},"
            " {key: 'x', o: {_repeat: true}}, false).querySelector('.badge.info') !== null",
        )
        is True
    )


def test_the_order_is_bold_mono_and_a_missing_value_is_quiet(qtbot, doc):
    view, _ = doc
    row = "#rows .row[data-order=\"#10004\"]"
    for cell in ("order", "lines", "units", "value"):
        assert (
            _eval(
                qtbot,
                view,
                f"document.querySelector('{row} .{cell}').classList.contains('mono')",
            )
            is True
        ), cell
    assert (
        _eval(
            qtbot, view, f"getComputedStyle(document.querySelector('{row} .order')).fontWeight"
        )
        == "700"
    )
    # i=3 ships with no courier: the dash is in the disabled text colour.
    assert _eval(
        qtbot, view, f"getComputedStyle(document.querySelector('{row} .courier')).color"
    ) == _rgb(LIGHT_THEME.text_disabled)


def test_the_value_header_is_quiet_until_a_price_column_is_mapped(qtbot, doc):
    view, bridge = doc
    head = "document.querySelector('#header .head.value')"
    assert _eval(qtbot, view, f"{head}.classList.contains('unmapped')") is False
    bridge.set_orders(results_lines().drop(columns=["Total_Price"]))
    _until_js(qtbot, view, f"{head}.classList.contains('unmapped')")
```

In `tests/test_results_pane.py`:

- `test_the_pane_is_400_by_508_beside_the_table` becomes `test_the_pane_is_339_by_510_beside_the_table`
  and asserts `size == "339x510"`, with this docstring: "The slot is 340; its left edge, the one rule between
  table and pane, takes 1."
- `test_hiding_leaves_a_strip_and_showing_restores_the_table` becomes
  `test_hiding_leaves_a_rail_and_showing_restores_the_table`: both `dataset.slot === 'strip'` checks become
  `'rail'`, `1242` becomes `1220`, `866` becomes `920`. Add after the first `_until_js`:
  `assert _text(qtbot, view, "#pane-show").strip() == "Order detail"`.
- `test_a_narrow_page_collapses_the_pane_until_asked`: `'strip'` becomes `'rail'`.

In `tests/test_results_columns.py`:

- `test_the_pane_slot_leaves_the_table_866_wide_and_17_rows` becomes
  `test_the_pane_slot_leaves_the_table_920_wide_and_14_rows`: `866` → `920`, `400` → `340`, `"17"` → `"14"`.
- `test_the_manager_keeps_the_table_width_and_counts_shown_and_hidden`: `866` → `920`.

In `tests/test_shell.py`, append:

```python
def test_a_web_page_takes_the_page_area_to_its_edges(main_window):
    """Phase 2 spec section 5.1: a Qt page keeps its 5px inset, a web page has
    none, or a white ring would show around the grey page."""
    main_window.resize(1366, 768)
    main_window.main_tabs.setCurrentIndex(1)
    QApplication.processEvents()
    margins = main_window.page_area.layout().contentsMargins()
    assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (
        0,
        0,
        0,
        0,
    )
    assert main_window.main_tabs.width() == 1166
    main_window.main_tabs.setCurrentIndex(0)
    QApplication.processEvents()
    assert main_window.page_area.layout().contentsMargins().left() == 5
    assert main_window.main_tabs.width() == 1156
```

- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_results_document.py tests/test_results_pane.py tests/test_results_columns.py tests/test_shell.py`
Expected: the tests above FAIL (17 rows not 14, no `.card` on `#table-area`, no `page_area`).

- [ ] **Step 3: Markup**

In `gui/web/results.html`, the `#table-area` opening tag becomes:

```html
  <section id="table-area" class="card split" data-slot="none">
```

and the strip becomes a labelled rail (the chevron is added by `bindPane`):

```html
      <div id="pane-strip" class="pane-strip" hidden>
        <button id="pane-show" class="pane-rail" type="button"
                aria-label="Show order detail" title="Show detail"><span class="pane-rail-label">Order detail</span></button>
      </div>
```

In `gui/web/pane.js`, `bindPane`'s first line `els.paneShow.innerHTML = svg(CHEVRON_LEFT, "glyph");` becomes:

```js
  els.paneShow.insertAdjacentHTML("afterbegin", svg(CHEVRON_LEFT, "glyph"));
```

- [ ] **Step 4: CSS**

In `gui/web/results.css`:

(a) The `:root` block becomes (its comment about the selection bar taking the header's place stays above it):

```css
:root {
  --table-head-height: 36px;
}
```

(b) Replace the page section (the `/* --- page: ...` banner and `#results { ... }`) with:

```css
/* --- page: KPI card, filter bar, split card, 12 apart -------------------- */

/* The KPI row is fixed so the table's height never depends on a font. */
#results {
  position: relative;
  height: 100%;
  padding: 16px 24px 20px;
  display: grid;
  grid-template-rows: 88px var(--control-height) minmax(0, 1fr);
  row-gap: var(--spacing-md);
  container-type: inline-size;
}
```

(c) Replace the slot rules (from the `/* --- table ---` banner and its two comments through
`.cell.filler { padding: 0; }`) with:

```css
/* --- the split card: table and pane on one surface, one rule between ----- */

/* min-width: 0 overrides the grid item's default min-content size, which
   would otherwise stretch to the row's minimum and push the whole page wider
   than the viewport instead of scrolling inside #scroller. */
.split {
  position: relative;
  min-width: 0;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  overflow: hidden;
}
.split[data-slot="pane"],
.split[data-slot="columns"] { grid-template-columns: minmax(0, 1fr) 340px; }
.split[data-slot="rail"] { grid-template-columns: minmax(0, 1fr) 40px; }
.split[data-slot="none"] .slot { display: none; }
.table-wrap, .slot { position: relative; min-width: 0; min-height: 0; }
.slot { border-left: 1px solid var(--border-subtle); }
.cell.filler { padding: 0; }
```

(d) Replace the table rules, from `.table:focus { outline: none; }` through `.cell.select input { ... }`, and
the whole `/* --- status chip ...` section after them (`.chip`, `.chip::before`, `.chip.success`,
`.chip.danger`), with the block below. The two `.rows .row.selected` ring rules and their comment are kept as
they are, between `.rows .row:hover` and `.cell` (Task 7 replaces them):

```css
/* --- table --------------------------------------------------------------- */

.table:focus { outline: none; }
.table:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: -2px; }

.scroller { overflow: auto; }

.row {
  display: grid;
  grid-template-columns: var(--cols);
  min-width: var(--table-min, 728px); /* results.js measureColumns */
  background: var(--surface);
}

.header {
  position: sticky;
  top: 0;
  z-index: var(--z-header);
  height: var(--table-head-height);
  background: var(--surface-raised);
  border-bottom: 1px solid var(--border-subtle);
}

.rows { position: relative; min-width: var(--table-min, 728px); }

/* --results-row-height is the density's row plus 4: results.js layout(). */
.rows .row {
  position: absolute;
  left: 0;
  right: 0;
  height: var(--results-row-height);
  border-bottom: 1px solid var(--border-subtle);
}
.rows .row:hover { background: var(--hover); }

/* (the two .rows .row.selected rules stay here until Task 7) */

.cell {
  padding: 0 8px;
  line-height: var(--results-row-height);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.head {
  line-height: calc(var(--table-head-height) - 1px);
  font-size: var(--type-caption-size);
  font-weight: 700;
  color: var(--text-secondary);
  cursor: pointer;
  user-select: none;
}
.head.sorted { color: var(--text); }
.head.select { cursor: default; }
/* The Value column while no price column is mapped. */
.head.unmapped { color: var(--text-disabled); }

.caret {
  width: 12px;
  height: 12px;
  margin-left: 2px;
  vertical-align: middle;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  visibility: hidden;
}
.head:hover .caret, .head.sorted .caret { visibility: visible; }

.num { text-align: right; }
.cell.mono { font-family: var(--font-family-mono); }
.cell.order { font-weight: 700; }
.cell.missing { color: var(--text-disabled); }

/* Pinned when the table scrolls sideways. No z-index, so what the row draws
   over itself still paints over them. */
.cell.select, .cell.status { position: sticky; background: inherit; }
.cell.select { left: 0; padding: 0; text-align: center; }
.cell.status { left: 36px; }
```

(e) In the pane section: in the `.pane, .columns-panel { ... }` rule change `background` to `var(--surface)`
and delete its `border-radius` line; change `background` to `var(--surface)` in `.line.line-head` and in
`.col-group`. Replace `.pane-strip { height: 100%; }` and `.btn.strip-button { ... }` with:

```css
/* Collapsed, the pane is a rail that says what it is. */
.pane-strip { height: 100%; }
.pane-rail {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  width: 100%;
  height: 100%;
  padding: 8px 0;
  border: 0;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
}
.pane-rail:hover { background: var(--hover); }
.pane-rail:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: -2px; }
.pane-rail-label {
  writing-mode: vertical-rl;
  font-size: var(--type-caption-size);
  font-weight: 700;
}
```

- [ ] **Step 5: Script**

In `gui/web/results.js`:

Constants at the top become:

```js
const HEADER_PX = 36;
const ROW_EXTRA_PX = 4; // a results row is the density's row plus this
const OVERSCAN = 4;
const TABLE_MIN_PX = 728;
const PANE_PX = 340;
```

and further down:

```js
const SELECT_COLUMN = { key: "select", title: "", width: 36 };
const SLOT_NARROW_PX = TABLE_MIN_PX + PANE_PX; // below this the pane folds to its rail
```

In `state`, `rowH: 28` becomes `rowH: 32`.

In `measureColumns`, the body of the `widths` map becomes:

```js
  const widths = cols.map((col) => {
    if (col.key === "select" || col.stretch) return col.width || 0;
    ctx.font = "700 " + caption;
    let widest = ctx.measureText(col.title).width + 14; // + the sort caret
    if (col.key === "status") {
      widest = Math.max(widest, ctx.measureText(FULFILLABLE).width + 18); // badge padding + edge
    } else {
      ctx.font = (col.key === "order" ? "700 " : "") + (col.mono ? mono : sans);
      for (const r of state.records) widest = Math.max(widest, ctx.measureText(col.text(r.o) || DASH).width);
    }
    const width = Math.max(col.width, Math.ceil(widest + 16));
    return col.maxWidth ? Math.min(col.maxWidth, width) : width;
  });
```

and `Math.max(120, TABLE_MIN_PX - fixed)` becomes `Math.max(140, TABLE_MIN_PX - fixed)`.

In `layout`, the `state.rowH = ...` line becomes:

```js
  state.rowH = (parseFloat(cssVar("--row-height")) || 28) + ROW_EXTRA_PX;
  els.table.style.setProperty("--results-row-height", state.rowH + "px");
```

In `slotMode`, `"strip"` becomes `"rail"`; in `renderSlot`, `mode !== "strip"` becomes `mode !== "rail"`.

In `renderHeader`, after `cell.setAttribute("aria-sort", ...)`, add:

```js
      const s = (state.bridge && state.bridge.summary) || {};
      if (col.key === "value" && s.orders !== undefined && s.value_total === null) cell.classList.add("unmapped");
```

Above `cellElement`, add:

```js
function statusBadge(o) {
  const badge = document.createElement("span");
  badge.className = "badge " + (isFulfillable(o) ? "success" : "danger");
  badge.textContent = statusText(o);
  return badge;
}
```

`cellElement` becomes:

```js
function cellElement(col, record, selected) {
  const cell = document.createElement("div");
  cell.className = "cell " + col.key + (col.numeric ? " num" : "") + (col.mono ? " mono" : "");
  cell.setAttribute("role", "gridcell");
  if (col.key === "select") {
    const box = document.createElement("input");
    box.type = "checkbox";
    box.tabIndex = -1;
    box.checked = selected;
    box.setAttribute("aria-label", "Select order " + record.key);
    cell.appendChild(box);
  } else if (col.key === "status") {
    cell.appendChild(statusBadge(record.o));
  } else if (col.key === "repeat" && record.o._repeat === true) {
    const badge = document.createElement("span");
    badge.className = "badge info";
    badge.textContent = "Repeat";
    cell.appendChild(badge);
  } else {
    const text = col.text(record.o);
    const missing = text === "" || text === DASH;
    cell.textContent = missing ? DASH : text;
    cell.classList.toggle("missing", missing);
  }
  return cell;
}
```

In the `QWebChannel` callback, the `summaryChanged` handler gains the header (the Value header depends on the
summary):

```js
  bridge.summaryChanged.connect(() => {
    renderKpis();
    renderExport();
    renderHeader();
  });
```

In `gui/web/columns.js`, the first eight registry entries and `repeat` take the mockup's base widths, and the
number columns the mono face (a column still grows to its widest value):

```js
  { key: "status", title: "Status", group: "Order", width: 108, pinned: true, shown: true,
    text: (o) => statusText(o), sortValue: (o) => (isFulfillable(o) ? 0 : 1) },
  { key: "order", title: "Order", group: "Order", width: 64, pinned: true, shown: true, mono: true,
    text: (o) => str(o.Order_Number) },
  { key: "customer", title: "Customer", group: "Customer", stretch: true, shown: true, text: (o) => str(o.Customer) },
  { key: "lines", title: "Lines", group: "Order", width: 52, shown: true, numeric: true, mono: true,
    text: (o) => fmtInt(o.Items), sortValue: (o) => num(o.Items) },
  { key: "units", title: "Units", group: "Order", width: 52, shown: true, numeric: true, mono: true,
    text: (o) => fmtInt(o.Units), sortValue: (o) => num(o.Units) },
  { key: "value", title: "Value", group: "Money", width: 76, shown: true, numeric: true, mono: true,
    text: (o) => fmtMoney(o.Total_Price), sortValue: (o) => num(o.Total_Price) },
  { key: "courier", title: "Courier", group: "Shipping", width: 72, shown: true, text: (o) => str(o.Shipping_Provider) },
  { key: "age", title: "Age", group: "Order", width: 52, shown: true, numeric: true, mono: true,
    text: (o) => fmtAge(o.Created_At), sortValue: (o) => ageMs(o.Created_At) },
```

and further down `subtotal` gains `mono: true`, and `repeat`'s `width: 64` becomes `width: 76`.

- [ ] **Step 6: The page inset (`gui/ui_manager.py`)**

Below `_COLLAPSED_KEY`, add:

```python
# The tabs drawn on the web tier. A web page paints the sunken plane to its
# own edges, so the page area's 5px inset would show as a white ring around
# it. Each phase that moves a screen adds its index (phase 2 spec section 5.1).
_WEB_PAGES = frozenset({1})
```

In `create_widgets`, right after `page_area = QWidget()`, add `self.mw.page_area = page_area`.

In `_create_tabs`, after `self.mw.main_tabs.currentChanged.connect(self._bind_screen_action)`, add:

```python
        self.mw.main_tabs.currentChanged.connect(self._apply_page_inset)
```

and add the method next to `_bind_screen_action`:

```python
    def _apply_page_inset(self, index: int) -> None:
        """No inset around a web page, the old 5px around a Qt one."""
        inset = 0 if index in _WEB_PAGES else 5
        self.mw.page_area.layout().setContentsMargins(inset, inset, inset, inset)
```

- [ ] **Step 7: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_results_document.py tests/test_results_pane.py tests/test_results_columns.py tests/test_results_selection_bar.py tests/test_results_bulk_popover.py tests/test_shell.py tests/test_web_kit.py tests/test_style_literals_guard.py`
Expected: PASS. `test_the_selection_ring_closes_across_the_frozen_cells` still passes: its samples at x=40 and
x=100 now fall on the ring over the checkbox cell and the Status cell of a row that starts at x=25.
If it fails because a sample lands outside the row, change its three x positions to
`int(rect["left"]) + 16, int(rect["left"]) + 40, int(rect["left"]) + 100`; Task 7 replaces the test anyway.

- [ ] **Step 8: Commit**

`/usr/bin/git add gui/web gui/ui_manager.py tests/test_results_document.py tests/test_results_pane.py tests/test_results_columns.py tests/test_shell.py`,
message "Results: sunken page, one split card, 36px header and 32px rows".

---

### Task 5: The KPI strip and the Map columns link

**Files:**
- Modify: `gui/web/results.html` (`#kpis`), `gui/web/results.css` (the KPI section, `:root`),
  `gui/web/results.js` (`renderKpis`, a glyph constant), `gui/results_bridge.py`, `gui/ui_manager.py`
  (`_create_tab2_analysis_results`)
- Test: `tests/test_results_document.py`, `tests/test_results_bridge.py`, `tests/test_results_screen.py`

**Interfaces:**
- Consumes: `.card`, `.btn.link`, `.glyph` from Task 3.
- Produces: `ResultsBridge.columnMappingRequested = Signal()` and `@Slot() openColumnMapping()`; in the page,
  `#map-columns` (a button) inside `[data-kpi=value].kpi-hint` while `summary.value_total` is `null`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_results_bridge.py`, append:

```python
def test_open_column_mapping_is_a_request_python_hears(qapp):
    """Phase 2 spec section 6.3: the KPI hint's Map columns link."""
    bridge = ResultsBridge()
    seen = []
    bridge.columnMappingRequested.connect(lambda: seen.append(1))
    bridge.openColumnMapping()
    assert seen == [1]
```

In `tests/test_results_document.py`, append after `test_the_sixth_card_only_on_a_wide_page`:

```python
def test_the_kpi_strip_is_one_card(qtbot, doc):
    view, _ = doc
    assert (
        _eval(qtbot, view, "document.getElementById('kpis').classList.contains('card')")
        is True
    )
    # Cells, not cards: five of them at this width, the wide one hidden.
    assert _eval(qtbot, view, "document.querySelectorAll('#kpis .kpi').length") == 6
    assert _eval(qtbot, view, "document.querySelectorAll('#kpis .card').length") == 0
    assert (
        _eval(qtbot, view, "document.querySelectorAll('#kpis .kpi-dot').length") == 2
    )


def test_a_mapped_price_gives_the_value_ready_cell(qtbot, doc):
    view, _ = doc
    _until_js(
        qtbot,
        view,
        "document.querySelector('[data-kpi=value] .kpi-label') !== null"
        " && document.querySelector('[data-kpi=value] .kpi-sub').textContent !== ''",
    )
    assert _text(qtbot, view, "[data-kpi=value] .kpi-label") == "Value ready"
    assert (
        _text(qtbot, view, "[data-kpi=value] .kpi-sub")
        == "across 281 fulfillable orders"
    )
    assert _eval(qtbot, view, "document.getElementById('map-columns') === null") is True


def test_an_unmapped_price_gives_a_hint_that_opens_the_mapping(qtbot, doc):
    view, bridge = doc
    bridge.set_orders(results_lines().drop(columns=["Total_Price"]))
    _until_js(qtbot, view, "document.getElementById('map-columns') !== null")
    assert (
        "Order value shows once a price column is mapped."
        in _text(qtbot, view, "[data-kpi=value]")
    )
    assert _text(qtbot, view, "#map-columns") == "Map columns"
    with qtbot.waitSignal(bridge.columnMappingRequested, timeout=5000):
        _eval(qtbot, view, "document.getElementById('map-columns').click(); true")
```

In `tests/test_results_screen.py`, append (it has a `main_window` fixture):

```python
def test_map_columns_opens_the_orders_mapping_page(main_window, monkeypatch):
    opened = []
    monkeypatch.setattr(
        main_window.actions_handler,
        "open_settings_window",
        lambda page=None: opened.append(page),
    )
    main_window.results_bridge.openColumnMapping()
    assert opened == ["Orders Mapping"]
```

- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_results_bridge.py tests/test_results_document.py tests/test_results_screen.py`
Expected: FAIL with `AttributeError: ... has no attribute 'columnMappingRequested'`, and the three page tests
fail (`#kpis` has no `card` class, the value sub-line reads "of 46.1k analysed", no `#map-columns`).

- [ ] **Step 3: The bridge member and its wiring**

In `gui/results_bridge.py`, extend the module docstring's catalogue paragraph with: "Phase 2 added
`openColumnMapping` (docs/superpowers/specs/2026-10-01-ui-refresh-phase2-results-kit-design.md section 6.3)."
After the `undoRequested = Signal()` line, add:

```python
    # Python-facing (phase 2): the KPI hint's link to the column mappings.
    columnMappingRequested = Signal()
```

and after the `openScreenMenu` slot:

```python
    @Slot()
    def openColumnMapping(self) -> None:
        self.columnMappingRequested.emit()
```

In `gui/ui_manager.py::_create_tab2_analysis_results`, after the `bridge.columnSettingsChanged.connect(...)`
block, add:

```python
        # The KPI strip's hint: straight to the page that maps the price column.
        bridge.columnMappingRequested.connect(
            lambda: actions().open_settings_window(page="Orders Mapping")
        )
```

- [ ] **Step 4: Markup and CSS**

`gui/web/results.html`: `<section id="kpis" class="card kpis" aria-label="Session numbers"></section>`.

`gui/web/results.css`: add `--kpi-value-size: 20pt;` to `:root` with the comment
`/* off the type scale on purpose: the mockup's KPI numeral */`, and replace the KPI section (the banner,
`.kpis`, `.kpi`, `.kpi-label, .kpi-sub`, `.kpi-label`, `.kpi-value`, `.kpi-wide`, the comment and the
`@container` block) with:

```css
/* --- KPI strip: one card, cells divided by hairlines --------------------- */

.kpis {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr)) 196px;
  overflow: hidden;
}

.kpi {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 2px;
  min-width: 0;
  padding: 0 16px;
  overflow: hidden;
}
.kpi + .kpi { border-left: 1px solid var(--border-subtle); }

.kpi-label, .kpi-sub {
  line-height: 1.3;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--type-caption-size);
  color: var(--text-secondary);
}
.kpi-label { display: flex; align-items: center; gap: 6px; font-weight: 700; }

.kpi-dot { flex-shrink: 0; width: 8px; height: 8px; border-radius: 50%; }
.kpi-dot.success { background: var(--status-success-dot); }
.kpi-dot.danger { background: var(--status-danger-dot); }

.kpi-value { font-size: var(--kpi-value-size); font-weight: 700; line-height: 1.1; }

/* The value cell while no price column is mapped: a hint, not a number. */
.kpi-hint {
  flex-direction: row;
  align-items: flex-start;
  justify-content: flex-start;
  gap: 8px;
  padding: 12px 14px;
  font-size: var(--type-caption-size);
  color: var(--text-secondary);
}
.kpi-hint > .glyph { margin-top: 2px; }
.kpi-hint-body { display: flex; flex-direction: column; align-items: flex-start; gap: 4px; min-width: 0; }
.kpi-hint .btn.link { color: var(--text); }

.kpi-wide { display: none; }

/* The one container query. #results is the container; 1496px of content is
   a 1544px page once the 24px padding is off both sides. */
@container (min-width: 1496px) {
  .kpis.has-wide { grid-template-columns: repeat(5, minmax(0, 1fr)) 196px; }
  .kpis.has-wide .kpi-wide { display: flex; }
}
```

- [ ] **Step 5: `renderKpis`**

In `gui/web/results.js`, add to the glyph constants at the top:

```js
// Lucide info, as one path: a circle and its two strokes.
const INFO = "M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0zM12 16v-4M12 8h.01";
```

Replace `renderKpis` with:

```js
function kpiCell(key, label, value, sub, dot) {
  const cell = document.createElement("div");
  cell.className = "kpi" + (key === "oldest" ? " kpi-wide" : "");
  cell.dataset.kpi = key;
  const head = document.createElement("div");
  head.className = "kpi-label";
  if (dot) {
    const mark = document.createElement("span");
    mark.className = "kpi-dot " + dot;
    head.appendChild(mark);
  }
  head.appendChild(document.createTextNode(label));
  cell.appendChild(head);
  for (const [cls, text] of [["kpi-value", value], ["kpi-sub", sub]]) {
    const part = document.createElement("div");
    part.className = cls;
    part.textContent = text;
    cell.appendChild(part);
  }
  return cell;
}

// Until a price column is mapped the cell is a hint with the way to fix it.
function valueHint() {
  const cell = document.createElement("div");
  cell.className = "kpi kpi-hint";
  cell.dataset.kpi = "value";
  cell.innerHTML = svg(INFO, "glyph");
  const body = document.createElement("div");
  body.className = "kpi-hint-body";
  const text = document.createElement("span");
  text.textContent = "Order value shows once a price column is mapped.";
  const link = document.createElement("button");
  link.type = "button";
  link.id = "map-columns";
  link.className = "btn link";
  link.textContent = "Map columns";
  link.addEventListener("click", () => state.bridge && state.bridge.openColumnMapping());
  body.append(text, link);
  cell.appendChild(body);
  return cell;
}

function renderKpis() {
  const s = (state.bridge && state.bridge.summary) || {};
  const has = s.orders !== undefined;
  const oldest = has ? s.oldest : null;
  const cells = [
    kpiCell("orders", "Orders", has ? fmtInt(s.orders) : DASH,
      has ? NUMBER.format(s.lines) + " lines · " + NUMBER.format(s.skus) + " SKUs touched" : ""),
    kpiCell("fulfillable", "Fulfillable", has ? fmtInt(s.fulfillable) : DASH,
      has && s.orders ? Math.round((100 * s.fulfillable) / s.orders) + "% of orders" : "", "success"),
    kpiCell("blocked", "Blocked", has ? fmtInt(s.blocked) : DASH,
      has ? NUMBER.format(s.blocked_lines) + " lines, " + NUMBER.format(s.blocked_skus) + " SKUs" : "", "danger"),
    kpiCell("labels", "Labels", has ? fmtInt(s.fulfillable) : DASH,
      has ? (s.labels_by_courier || []).map((p) => p[0] + " " + NUMBER.format(p[1])).join(" · ") : ""),
    kpiCell("oldest", "Oldest waiting", oldest ? fmtAge(oldest.created_at) : DASH,
      oldest ? "order " + oldest.order_number : ""),
    has && s.value_total === null
      ? valueHint()
      : kpiCell("value", "Value ready", has && s.value_ready !== null ? fmtCompact(s.value_ready) : DASH,
        has ? "across " + plural(s.fulfillable, "fulfillable order") : ""),
  ];
  els.kpis.classList.toggle("has-wide", Boolean(oldest));
  els.kpis.replaceChildren(...cells);
}
```

- [ ] **Step 6: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_results_bridge.py tests/test_results_document.py tests/test_results_screen.py tests/test_results_summary.py tests/test_style_literals_guard.py`
Expected: PASS, including the existing `test_the_kpis_count_the_session`,
`test_the_sixth_card_only_on_a_wide_page` and `test_nothing_analysed_shows_its_state`.

- [ ] **Step 7: Commit**

`/usr/bin/git add gui/web gui/results_bridge.py gui/ui_manager.py tests/test_results_bridge.py tests/test_results_document.py tests/test_results_screen.py`,
message "Results: the KPI strip is one card, and an unmapped price links to the mapping".

---

### Task 6: The filter bar

**Files:**
- Modify: `gui/web/results.html` (`#filterbar`, `#results-no-match`), `gui/web/results.css` (the filter bar
  section), `gui/web/results.js` (glyph constants, `renderChips`, `renderExport`, `renderStates`,
  `renderSlot`, `bind`)
- Test: `tests/test_results_document.py`

**Interfaces:**
- Consumes: `.input`, `.btn.dashed`, `.btn.ghost`, `.btn.primary`, `.state`, `.glyph` from Task 3.
- Produces: in `results.js`: `CHIP_KEYS`, `chipValue(chip) -> string`, `filterSentence() -> string`, and the
  glyph constants `X_MARK`, `COLUMNS`, `DOWNLOAD`; in the page: `.chip-filter` (a `<span>`) holding
  `.chip-key`, `.chip-value` and a `.chip-remove` button; `#no-match-text`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_results_document.py`, replace `test_a_chip_removes_itself_when_clicked` with:

```python
def test_the_filter_bar_reads_search_add_filter_then_chips(qtbot, doc):
    view, _ = doc
    order = json.loads(
        _eval(
            qtbot,
            view,
            "JSON.stringify([...document.getElementById('filterbar').children]"
            ".map(function (e) { return e.id || e.className; }))",
        )
    )
    assert order[:4] == ["input search", "filter-anchor", "chips", "clear-all"]
    assert order[-3:] == ["columns-button", "screen-menu", "export"]


def test_a_chip_names_its_key_and_only_its_x_removes_it(qtbot, doc):
    view, _ = doc
    _choose_filter(qtbot, view, "Courier: DPD")
    _until_js(
        qtbot, view, "document.querySelectorAll('#chips .chip-filter').length === 1"
    )
    assert _text(qtbot, view, "#chips .chip-filter") == "Courier is DPD"
    _count_is(qtbot, view, "78 of 312 orders")
    _eval(qtbot, view, "document.querySelector('#chips .chip-value').click(); true")
    _count_is(qtbot, view, "78 of 312 orders")
    assert (
        _eval(qtbot, view, "document.querySelector('#chips .chip-remove').title")
        == "Remove filter"
    )
    _eval(qtbot, view, "document.querySelector('#chips .chip-remove').click(); true")
    _count_is(qtbot, view, "312 orders")


def test_no_match_says_what_is_filtering(qtbot, doc):
    view, _ = doc
    _choose_filter(qtbot, view, "Blocked")
    _choose_filter(qtbot, view, "Courier: DHL")  # no blocked order ships DHL
    _until_js(qtbot, view, "!document.getElementById('results-no-match').hidden")
    assert _text(qtbot, view, "#no-match-text") == "Status is Blocked and Courier is DHL."
    _search(qtbot, view, "zzz")
    _until_js(
        qtbot,
        view,
        "document.getElementById('no-match-text').textContent"
        " === 'Status is Blocked and Courier is DHL and search is “zzz”.'",
    )
    # Within Courier the chips are alternatives, and the sentence says so.
    _choose_filter(qtbot, view, "Courier: DPD")
    assert (
        _eval(qtbot, view, "filterSentence()")
        == "Status is Blocked and Courier is DHL or DPD and search is “zzz”."
    )
    assert _text(qtbot, view, "#no-match-clear") == "Clear filters"
    _eval(qtbot, view, "document.getElementById('no-match-clear').click(); true")
    _count_is(qtbot, view, "312 orders")


def test_columns_and_export_keep_their_words_beside_a_glyph(qtbot, doc):
    view, _ = doc
    assert _text(qtbot, view, "#columns-button") == "Columns 9/18"
    assert _eval(qtbot, view, "!!document.querySelector('#columns-button svg')") is True
    _until_js(
        qtbot,
        view,
        "document.getElementById('export').textContent === 'Export 281 orders'",
    )
    assert _eval(qtbot, view, "!!document.querySelector('#export svg')") is True
```

- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_results_document.py`
Expected: the four tests FAIL (`#search` is the bar's first child, the chip reads "Courier: DPD  ×",
there is no `#no-match-text`).

- [ ] **Step 3: Markup**

In `gui/web/results.html`, replace the whole `<div id="filterbar" ...> ... </div>` with:

```html
  <div id="filterbar" class="filterbar">
    <label class="input search">
      <svg class="glyph" viewBox="0 0 24 24" aria-hidden="true"><path d="M19 11a8 8 0 1 1-16 0 8 8 0 0 1 16 0zM21 21l-4.3-4.3"/></svg>
      <input id="search" type="search" placeholder="Order, customer or SKU"
             aria-label="Search orders" autocomplete="off" spellcheck="false">
    </label>
    <div id="filter-anchor" class="menu-anchor">
      <button id="add-filter" class="btn dashed" type="button"
              aria-haspopup="menu" aria-expanded="false"><svg class="glyph" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14M12 5v14"/></svg>Add filter</button>
      <div id="filter-menu" class="menu" role="menu" hidden></div>
    </div>
    <div id="chips" class="chips"></div>
    <button id="clear-all" class="btn ghost" type="button" hidden>Clear all</button>
    <span class="spacer"></span>
    <span id="count" class="count"></span>
    <button id="columns-button" class="btn ghost" type="button" aria-pressed="false" disabled></button>
    <button id="screen-menu" class="btn ghost icon" type="button"
            title="More actions for this screen" aria-label="More actions for this screen">⋯</button>
    <button id="export" class="btn primary" type="button" disabled></button>
  </div>
```

and the no-match state with:

```html
      <div id="results-no-match" class="state" hidden>
        <svg class="state-glyph" viewBox="0 0 24 24" aria-hidden="true"><path d="M19 11a8 8 0 1 1-16 0 8 8 0 0 1 16 0zM21 21l-4.3-4.3M13.5 8.5l-5 5M8.5 8.5l5 5"/></svg>
        <p class="state-title">No orders match</p>
        <p id="no-match-text" class="state-text"></p>
        <button id="no-match-clear" class="btn secondary" type="button">Clear filters</button>
      </div>
```

- [ ] **Step 4: CSS**

In `gui/web/results.css`, replace the filter bar section (the banner, `.filterbar`, `#search` and its two
states, `.chips`, `.chip-filter`, `.chip-filter:hover`, `.count`, and the `.chip-filter:focus-visible` rule
Task 3 kept) with:

```css
/* --- filter bar ---------------------------------------------------------- */

.filterbar {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  min-width: 0;
}

.search { flex: 0 0 260px; }

.chips { display: flex; gap: var(--spacing-sm); min-width: 0; overflow: hidden; }

/* A filter chip states its filter; only its x removes it. */
.chip-filter {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: var(--control-height);
  padding: 0 4px 0 10px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--kit-radius);
  background: var(--surface);
  box-shadow: var(--card-shadow);
  white-space: nowrap;
}
.chip-key { color: var(--text-secondary); }
.chip-value { font-weight: 700; }
.chip-remove {
  display: grid;
  place-items: center;
  width: 20px;
  height: 20px;
  padding: 0;
  border: 0;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
}
.chip-remove:hover { background: var(--hover); }
.chip-remove:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 1px; }

/* The pane's tag chip is one button: the whole chip removes the tag. */
.tag-chip { height: var(--kit-control-compact); padding: 0 8px; box-shadow: none; cursor: pointer; }
.tag-chip:hover { background: var(--hover); }

.count {
  font-size: var(--type-caption-size);
  color: var(--text-secondary);
  white-space: nowrap;
}
.columns-count { font-size: var(--type-caption-size); font-weight: 400; color: var(--text-secondary); }
```

Keep the `.tag-chip:focus-visible` rule Task 3 left in the pane section.

- [ ] **Step 5: Script**

In `gui/web/results.js`, add to the glyph constants:

```js
// Lucide x, columns-3 and download, each as one path.
const X_MARK = "M18 6 6 18M6 6l12 12";
const COLUMNS = "M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2zM9 3v18M15 3v18";
const DOWNLOAD = "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3";
```

Below `chipId`, add:

```js
const CHIP_KEYS = { status: "Status", flag: "Flag", courier: "Courier", tag: "Tag" };

// What the chip says after "is": the menu's label carries a "Courier: " or
// "Tag: " prefix the chip's own key already states.
function chipValue(chip) {
  return chip.kind === "courier" || chip.kind === "tag" ? chip.value : chip.label;
}

// The filters as one sentence, for the no-match state. Flags all have to
// hold; within Status, Courier and Tag the chips are alternatives.
function filterSentence() {
  const parts = [];
  for (const kind of Object.keys(CHIP_KEYS)) {
    const values = state.chips.filter((c) => c.kind === kind).map(chipValue);
    if (values.length) parts.push(CHIP_KEYS[kind] + " is " + values.join(kind === "flag" ? " and " : " or "));
  }
  const query = els.search.value.trim();
  if (query) parts.push("search is “" + query + "”");
  return parts.join(" and ") + ".";
}
```

Replace `renderChips` with:

```js
function renderChips() {
  els.chips.textContent = "";
  for (const chip of state.chips) {
    const box = document.createElement("span");
    box.className = "chip-filter";
    box.dataset.chip = chipId(chip);
    const key = document.createElement("span");
    key.className = "chip-key";
    key.textContent = CHIP_KEYS[chip.kind] + " is";
    const value = document.createElement("span");
    value.className = "chip-value";
    value.textContent = chipValue(chip);
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "chip-remove";
    remove.title = "Remove filter";
    remove.setAttribute("aria-label", "Remove filter: " + CHIP_KEYS[chip.kind] + " is " + chipValue(chip));
    remove.innerHTML = svg(X_MARK, "glyph");
    remove.addEventListener("click", () => {
      toggleChip(chip);
      render();
    });
    // The text node is the space a reader hears; flex ignores it for layout.
    box.append(key, " ", value, remove);
    els.chips.appendChild(box);
  }
  els.clearAll.hidden = !(state.chips.length || state.query);
}
```

Replace `renderExport` with:

```js
function renderExport() {
  const s = (state.bridge && state.bridge.summary) || {};
  const n = s.fulfillable || 0;
  els.exportBtn.replaceChildren();
  els.exportBtn.insertAdjacentHTML("beforeend", svg(DOWNLOAD, "glyph"));
  els.exportBtn.append(s.fulfillable === undefined ? "Export" : "Export " + plural(n, "order"));
  els.exportBtn.disabled = !(state.bridge && state.bridge.exportEnabled && n > 0);
}
```

In `renderStates`, after `els.noMatch.hidden = !noMatch;`, add:

```js
  if (noMatch) els.noMatchText.textContent = filterSentence();
```

In `renderSlot`, replace the `els.columnsButton.textContent = ...` line with:

```js
  const count = document.createElement("span");
  count.className = "columns-count mono";
  count.textContent = visibleColumns().length + "/" + allColumns().length;
  els.columnsButton.replaceChildren();
  els.columnsButton.insertAdjacentHTML("beforeend", svg(COLUMNS, "glyph"));
  els.columnsButton.append("Columns ", count);
```

In `bind`, add `noMatchText: "no-match-text",` to the `ids` map.

- [ ] **Step 6: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_results_document.py tests/test_results_columns.py tests/test_results_pane.py tests/test_results_selection_bar.py tests/test_style_literals_guard.py`
Expected: PASS. `test_chips_and_across_groups_and_or_within_one` and the search tests pass unchanged.

- [ ] **Step 7: Commit**

`/usr/bin/git add gui/web tests/test_results_document.py`, message
"Results: the filter bar to the mockup, and a no-match state that says what is filtering".

---

### Task 7: Cursor and checked orders, and the selection bar

**Files:**
- Modify: `gui/web/results.html` (`#selection-bar`), `gui/web/results.css` (the selected-row rules, the
  selection bar rules), `gui/web/results.js` (`renderHeader`, `rowElement`, `onRowClick`, `onTableKey`,
  `bind`, a new `moveCursor`), `gui/web/bulk.js` (`renderSelectionBar`, `bindSelectionBar`, `copySelection`,
  a new `markableKeys`; `clearSelection` and `selectionSummary` are deleted)
- Test: `tests/test_results_document.py`, `tests/test_results_selection_bar.py`, `tests/test_results_pane.py`

**Interfaces:**
- Consumes: `.btn.secondary.compact` and the checkbox from Task 3; the table CSS from Task 4.
- Produces: `moveCursor(key)` in `results.js`; `markableKeys() -> string[]` in `bulk.js`; a row carries class
  `cursor` when it is `state.cursorKey` and class `selected` (with `aria-selected="true"`) when it is checked;
  `bridge.setSelection` reports the checked set only.

- [ ] **Step 1: Rewrite the selection tests**

In `tests/test_results_document.py`, add this helper next to `_click_order`:

```python
def _check(qtbot, view, order):
    _eval(
        qtbot,
        view,
        f"document.querySelector('#rows .row[data-order=\"{order}\"] input[type=checkbox]')"
        ".click(); true",
    )
```

Replace `test_a_row_click_reaches_python_and_a_hiding_filter_drops_it`,
`test_arrow_down_moves_the_selection` and `test_the_selection_ring_closes_across_the_frozen_cells` with:

```python
def _has_class(order, name):
    return (
        f"document.querySelector('#rows .row[data-order=\"{order}\"]')"
        f".classList.contains('{name}')"
    )


def test_a_row_click_moves_the_cursor_and_checks_nothing(qtbot, doc):
    view, bridge = doc
    _click_order(qtbot, view, "#10001")
    _until_js(qtbot, view, _has_class("#10001", "cursor"))
    assert bridge.selection() == []
    assert _eval(qtbot, view, "state.selected.size") == 0
    assert _eval(qtbot, view, "document.getElementById('selection-bar').hidden") is True


def test_a_checkbox_checks_the_order_and_leaves_the_cursor(qtbot, doc):
    view, bridge = doc
    _click_order(qtbot, view, "#10001")
    _check(qtbot, view, "#10003")
    qtbot.waitUntil(lambda: bridge.selection() == ["#10003"])
    assert _eval(qtbot, view, "state.cursorKey") == "#10001"
    assert _eval(qtbot, view, _has_class("#10003", "selected")) is True
    assert _eval(qtbot, view, _has_class("#10003", "cursor")) is False
    assert _eval(qtbot, view, "document.getElementById('selection-bar').hidden") is False
    _click_order(qtbot, view, "#10003", ctrlKey=True)  # Ctrl-click toggles too
    qtbot.waitUntil(lambda: bridge.selection() == [])


def test_a_hiding_filter_unchecks_the_order_and_empties_the_pane(qtbot, doc):
    """Review focus 3: nothing keeps pointing at an order the operator cannot see."""
    view, bridge = doc
    _click_order(qtbot, view, "#10001")
    _check(qtbot, view, "#10001")
    qtbot.waitUntil(lambda: bridge.selection() == ["#10001"])
    with qtbot.waitSignal(bridge.selectionChanged, timeout=5000) as blocker:
        _choose_filter(qtbot, view, "Blocked")  # #10001 is fulfillable
    assert blocker.args == [[]]
    assert _eval(qtbot, view, "state.cursorKey === null") is True
    assert _eval(qtbot, view, "document.querySelectorAll('#rows .row.cursor').length") == 0
    assert _text(qtbot, view, "#pane-empty .state-title") == "No order selected"


def test_arrow_down_moves_the_cursor_only(qtbot, doc):
    view, bridge = doc
    _click_order(qtbot, view, "#10001")
    _key(qtbot, view, "ArrowDown")
    _until_js(qtbot, view, "state.cursorKey === '#10002'")
    assert bridge.selection() == []


def test_escape_clears_the_checked_orders_and_then_the_cursor(qtbot, doc):
    view, bridge = doc
    _click_order(qtbot, view, "#10001")
    _check(qtbot, view, "#10002")
    qtbot.waitUntil(lambda: bridge.selection() == ["#10002"])
    _key(qtbot, view, "Escape")
    qtbot.waitUntil(lambda: bridge.selection() == [])
    assert _eval(qtbot, view, "state.cursorKey") == "#10001"
    _key(qtbot, view, "Escape")
    _until_js(qtbot, view, "state.cursorKey === null")


def test_the_header_box_checks_everything_or_clears(qtbot, doc):
    view, bridge = doc
    box = "document.querySelector('#header .select input')"
    _choose_filter(qtbot, view, "Blocked")
    _count_is(qtbot, view, "31 of 312 orders")
    _eval(qtbot, view, f"{box}.click(); true")
    qtbot.waitUntil(lambda: len(bridge.selection()) == 31)
    assert _eval(qtbot, view, f"{box}.title") == "Clear selection"
    _check(qtbot, view, "#10004")  # 30 of 31: the box is mixed, and still clears
    qtbot.waitUntil(lambda: len(bridge.selection()) == 30)
    assert _eval(qtbot, view, f"{box}.indeterminate") is True
    _eval(qtbot, view, f"{box}.click(); true")
    qtbot.waitUntil(lambda: bridge.selection() == [])


def test_the_cursor_row_wears_a_bar_on_its_left_edge(qtbot, doc):
    """The bar is a pseudo-element above the sticky cells, or they would paint
    over it. Only pixels can tell -- getComputedStyle cannot."""
    view, _ = doc
    _click_order(qtbot, view, "#10001")
    rect = json.loads(
        _eval(
            qtbot,
            view,
            "JSON.stringify(document.querySelector('#rows .row.cursor')"
            ".getBoundingClientRect())",
        )
    )

    def token(name):
        return QColor(
            _eval(
                qtbot,
                view,
                "getComputedStyle(document.documentElement)"
                f".getPropertyValue('{name}').trim()",
            )
        ).name()

    x = int(rect["left"]) + 1  # inside the 3px bar
    y = int(rect["top"]) + int(rect["height"]) // 2
    qtbot.waitUntil(
        lambda: view.grab().toImage().pixelColor(x, y).name()
        == token("--selection-border"),
        timeout=5000,
    )
    # The rest of the row is the selection tint: sampled in the last cell's
    # right padding, clear of any text.
    tint_x = int(rect["right"]) - 4
    assert view.grab().toImage().pixelColor(tint_x, y).name() == token("--selection-bg")
```

In `test_an_orders_push_keeps_the_selection`, replace `_click_order(qtbot, view, "#10002")` with
`_check(qtbot, view, "#10002")`. `test_shift_selects_a_range_and_shift_arrow_can_shrink_it` and
`test_ctrl_a_selects_every_order_shown_and_escape_clears` stay as they are and must still pass.

In `tests/test_results_selection_bar.py`:

- In `selection_bar_orders()`, order `10445` becomes blocked: `"Order_Fulfillment_Status": "Not Fulfillable"`.
  Its docstring's first line becomes "Three orders; 10445 is blocked, the other two fulfillable."
- Replace `test_the_bar_counts_orders_and_units`,
  `test_one_order_reads_singular_and_the_verbs_drop_their_count`, `test_the_verbs_carry_the_count_above_one`,
  `test_the_sub_line_counts_value_and_couriers`, `test_export_drops_to_secondary_while_the_bar_is_up` and
  `test_clear_empties_the_selection_and_hides_the_bar` with:

```python
def test_the_bar_counts_the_checked_orders(qtbot, page):
    view, _ = page
    _select(qtbot, view, ["10443", "10444", "10445"])
    assert _text(qtbot, view, "#selection-count") == "3 selected"
    assert _eval(qtbot, view, "document.getElementById('selection-sub')") in (None, "")


def test_mark_counts_and_sends_only_the_blocked_orders(qtbot, page):
    view, bridge = page
    _select(qtbot, view, ["10443", "10444", "10445"])
    assert _text(qtbot, view, "#selection-mark") == "Mark 1 fulfillable"
    assert _eval(qtbot, view, "document.getElementById('selection-mark').disabled") is False
    with qtbot.waitSignal(bridge.bulkStatusRequested, timeout=3000) as blocker:
        _eval(qtbot, view, "document.getElementById('selection-mark').click(); true")
    assert list(blocker.args) == [["10445"], True]


def test_mark_is_disabled_when_every_checked_order_is_fulfillable(qtbot, page):
    view, _ = page
    _select(qtbot, view, ["10443", "10444"])
    assert _text(qtbot, view, "#selection-mark") == "Mark 2 fulfillable"
    assert _eval(qtbot, view, "document.getElementById('selection-mark').disabled") is True


def test_hold_names_this_one_or_these_n_and_sends_them_all(qtbot, page):
    view, bridge = page
    _select(qtbot, view, ["10443"])
    assert _text(qtbot, view, "#selection-hold") == "Hold this"
    _select(qtbot, view, ["10443", "10444", "10445"])
    assert _text(qtbot, view, "#selection-hold") == "Hold these 3"
    with qtbot.waitSignal(bridge.bulkStatusRequested, timeout=3000) as blocker:
        _eval(qtbot, view, "document.getElementById('selection-hold').click(); true")
    assert list(blocker.args) == [["10443", "10444", "10445"], False]


def test_export_stays_the_screens_primary_while_the_bar_is_up(qtbot, page):
    view, _ = page
    _select(qtbot, view, ["10443"])
    assert "primary" in _eval(qtbot, view, "document.getElementById('export').className")


def test_the_header_box_clears_the_checked_orders_and_hides_the_bar(qtbot, page):
    view, _ = page
    _select(qtbot, view, ["10443"])
    _eval(qtbot, view, "document.querySelector('#header .select input').click(); true")
    assert _eval(qtbot, view, "document.getElementById('selection-bar').hidden") is True
    assert _eval(qtbot, view, "state.selected.size") == 0
    assert _eval(qtbot, view, "document.getElementById('selection-clear')") in (None, "")
```

- Append:

```python
def test_ctrl_c_with_nothing_checked_copies_the_cursors_order(qtbot, page):
    from PySide6.QtGui import QGuiApplication

    view, _ = page
    _eval(qtbot, view, "state.cursorKey = '10444'; render(); true")
    _eval(
        qtbot,
        view,
        "document.dispatchEvent(new KeyboardEvent('keydown', "
        "{key: 'c', ctrlKey: true, bubbles: true})); true",
    )
    assert QGuiApplication.clipboard().text() == "10444"
```

In `tests/test_results_pane.py`, append:

```python
def test_clicking_a_row_brings_a_hidden_pane_back(qtbot, doc):
    view, _ = doc
    _js(qtbot, view, "document.getElementById('pane-hide').click()")
    _until_js(
        qtbot, view, "document.getElementById('table-area').dataset.slot === 'rail'"
    )
    _js(qtbot, view, "document.querySelector('#rows .row[data-order=\"#10445\"]').click()")
    _until_js(
        qtbot, view, "document.getElementById('table-area').dataset.slot === 'pane'"
    )
```

- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_results_document.py tests/test_results_selection_bar.py tests/test_results_pane.py`
Expected: the new tests FAIL (a click still checks the row; the bar still reads "3 orders · 19 units selected").

- [ ] **Step 3: Markup**

In `gui/web/results.html`, replace the whole `<div id="selection-bar" ...> ... </div>` with (Exclude stays
until Task 8 gives it its popover):

```html
      <div id="selection-bar" class="selection-bar" role="toolbar"
           aria-label="Actions for the checked orders" hidden>
        <span id="selection-count" class="selection-count" aria-live="polite"></span>
        <button id="selection-mark" class="btn secondary compact" type="button"></button>
        <button id="selection-hold" class="btn secondary compact" type="button"></button>
        <div class="menu-anchor">
          <button id="selection-more" class="btn secondary compact" type="button"
                  aria-haspopup="menu" aria-expanded="false">More</button>
          <div id="selection-menu" class="menu" role="menu" hidden></div>
        </div>
        <span class="spacer"></span>
        <button id="selection-exclude" class="btn danger compact" type="button">Exclude from run</button>
      </div>
```

- [ ] **Step 4: CSS**

In `gui/web/results.css`, replace the two `.rows .row.selected` rules and the comment above them ("The
selection ring: a closed rectangle...") with:

```css
/* A checked row is raised; the cursor row is tinted and wears a bar on its
   left edge. The bar is a pseudo-element, not a border: the sticky select and
   status cells are positioned, so they paint over anything the row draws. */
.rows .row.selected { background: var(--surface-raised); }
.rows .row.cursor { background: var(--selection-bg); }
.rows .row.cursor::before {
  content: "";
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
  z-index: var(--z-sticky); /* over the sticky cells, which sit at auto */
  background: var(--selection-border);
  pointer-events: none;
}
```

and replace the selection bar rules (`.selection-bar`, `.selection-bar .btn`, `.selection-counts`,
`.selection-count`, `.selection-sub`, `.selection-separator`, keeping the banner and the comment about the
bar covering the header) with:

```css
.selection-bar {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  z-index: var(--z-bar); /* over the sticky .header */
  display: flex;
  align-items: center;
  gap: 6px;
  height: var(--table-head-height);
  padding: 0 8px;
  background: var(--surface-raised);
  border-bottom: 1px solid var(--border-subtle);
}
.selection-count { margin-right: 6px; font-weight: 700; white-space: nowrap; }
```

- [ ] **Step 5: `results.js`**

In `renderHeader`, the `select` branch becomes:

```js
    if (col.key === "select") {
      const box = document.createElement("input");
      box.type = "checkbox";
      box.tabIndex = -1;
      // With anything checked the box clears; with nothing, it checks all shown.
      box.title = picked > 0 ? "Clear selection" : "Select every order shown";
      box.setAttribute("aria-label", box.title);
      box.checked = all;
      box.indeterminate = picked > 0 && !all;
      box.addEventListener("click", () => selectAll(picked === 0));
      cell.appendChild(box);
    } else {
```

In `rowElement`, the class and ARIA lines become:

```js
  const selected = state.selected.has(record.key);
  const cursor = state.cursorKey === record.key;
  row.className = "row" + (selected ? " selected" : "") + (cursor ? " cursor" : "");
  row.setAttribute("role", "row");
  row.setAttribute("aria-selected", String(selected));
  if (cursor) row.setAttribute("aria-current", "true");
```

Replace `onRowClick` and the Escape and arrow parts of `onTableKey` with:

```js
// The cursor is the one order the pane shows. Asking for an order brings a
// pane the operator hid back; a pane folded because the page is narrow stays.
function moveCursor(key) {
  state.cursorKey = key;
  state.anchorKey = key;
  state.paneHidden = false;
}

function onRowClick(event) {
  const row = event.target.closest(".row");
  if (!row || !row.dataset.order) return;
  const key = row.dataset.order;
  const ctrl = event.ctrlKey || event.metaKey;
  if (event.shiftKey && state.anchorKey !== null) {
    selectRange(state.anchorKey, key, ctrl);
    state.cursorKey = key; // the range's moving end, so Shift+arrow carries on from it
  } else if (ctrl || event.target.matches("input[type=checkbox]")) {
    if (state.selected.has(key)) state.selected.delete(key);
    else state.selected.add(key);
    state.anchorKey = key;
  } else {
    moveCursor(key);
  }
  els.table.focus({ preventScroll: true });
  render();
}
```

```js
function onTableKey(event) {
  const ctrl = event.ctrlKey || event.metaKey;
  if (ctrl && event.key.toLowerCase() === "a") {
    event.preventDefault();
    selectAll(true);
    return;
  }
  if (event.key === "Escape") {
    // Innermost first: the checked orders, then the cursor.
    if (state.selected.size) {
      state.selected = new Set();
    } else {
      state.cursorKey = null;
      state.anchorKey = null;
    }
    render();
    return;
  }
  if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
  event.preventDefault();
  if (!state.view.length) return;
  const keys = state.view.map((r) => r.key);
  const from = state.cursorKey !== null ? state.cursorKey : state.anchorKey;
  const at = from === null ? -1 : keys.indexOf(from);
  const next = Math.min(keys.length - 1, Math.max(0, at + (event.key === "ArrowDown" ? 1 : -1)));
  if (event.shiftKey) {
    // The anchor stays and the range re-spans to the cursor, so reversing shrinks.
    const anchor = state.anchorKey !== null ? state.anchorKey : keys[Math.max(0, at)];
    selectRange(anchor, keys[next], false);
    state.anchorKey = anchor;
    state.cursorKey = keys[next];
    state.paneHidden = false;
  } else {
    moveCursor(keys[next]);
  }
  scrollIntoView(next);
  render();
}
```

In `bind`, remove `selectionSub: "selection-sub",` and `selectionClear: "selection-clear",` from the `ids` map.

Update the file's header comment, which says "the selection gesture": add the sentence "A click moves the
cursor; checkboxes, Ctrl and Shift build the checked set Python hears (phase 2 spec section 5.5)."

- [ ] **Step 6: `bulk.js`**

Delete `selectionSummary` and `clearSelection`. Add below `selectedKeys`:

```js
// Mark fulfillable only means something for an order that is not.
function markableKeys() {
  return state.view.filter((r) => state.selected.has(r.key) && !isFulfillable(r.o)).map((r) => r.key);
}
```

Replace `renderSelectionBar` with:

```js
function renderSelectionBar() {
  const n = state.selected.size;
  els.selectionBar.hidden = n === 0;
  if (n === 0) {
    closeSelectionMenu();
    closeBulkPopover();
    return;
  }
  els.selectionCount.textContent = NUMBER.format(n) + " selected";
  const markable = markableKeys().length;
  els.selectionMark.textContent = "Mark " + NUMBER.format(markable || n) + " fulfillable";
  els.selectionMark.disabled = markable === 0;
  els.selectionHold.textContent = n === 1 ? "Hold this" : "Hold these " + NUMBER.format(n);
}
```

In `bindSelectionBar`: the Mark listener sends `markableKeys()` instead of `selectedKeys()`; delete the
`els.selectionClear.addEventListener(...)` line; after the listeners add
`els.selectionMore.insertAdjacentHTML("beforeend", svg(CHEVRON_DOWN, "glyph"));` (the chevron beside "More");
and the Ctrl+C listener's guard `state.selected.size` becomes
`(state.selected.size || state.cursorKey !== null)`.

Replace `copySelection` with:

```js
// The checked orders, or with none checked the order the cursor is on.
function copySelection() {
  const keys = state.selected.size ? selectedKeys() : [state.cursorKey];
  state.bridge.copyText(keys.join("\n"));
  raiseToast(countedWord(keys.length, "order number") + " copied", false);
}
```

- [ ] **Step 7: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_results_document.py tests/test_results_selection_bar.py tests/test_results_pane.py tests/test_results_bulk_popover.py tests/test_results_columns.py tests/test_results_toast.py`
Expected: PASS. In `tests/test_results_selection_bar.py`, `test_more_lists_its_seven_items_in_order` and the
Escape tests pass unchanged. If a test elsewhere still clicks a row and then expects `bridge.selection()` to
name it, it is pinning the old gesture: change its click to `_check`.

- [ ] **Step 8: Commit**

`/usr/bin/git add gui/web tests/test_results_document.py tests/test_results_selection_bar.py tests/test_results_pane.py`,
message "Results: a click moves the cursor, checkboxes build the selection the bar acts on".

---
### Task 8: The bulk popover that confirms, and no Qt confirm after it

**Files:**
- Modify: `gui/web/bulk.js` (`moreItems`, `openBulkPopover`, `openTagPopover`, `openSkuPopover`,
  `bindSelectionBar`; new `orderList`, `exportLine`, `skuLinesOf`, `unitsOf`, `skuRemovalChanges`,
  `orderRemovalChanges`, `renderBulkChanges`, `openExcludePopover`), `gui/web/results.html` (remove
  `#selection-exclude`), `gui/web/results.css` (the bulk popover rules), `gui/web/results.js` (`bind`),
  `gui/actions_handler.py` (three `ConfirmDialog.ask` blocks and the import)
- Test: `tests/test_results_bulk_popover.py`, `tests/test_results_selection_bar.py`,
  `tests/test_actions_handler_bulk.py`, `tests/test_actions_handler.py`, `tests/test_undo_manager.py`

**Interfaces:**
- Consumes: `.popover`, `.btn.critical`, `.btn.secondary`, `.field` from Task 3; `selectedOrders()`,
  `selectedKeys()`, `countedWord()`, `theseOrders()` in `bulk.js`; `state.bridge.summary.fulfillable`;
  `HEADER_PX` from Task 4.
- Produces: `#more-exclude` in the More menu; in the popover `#bulk-body`, `#bulk-changes` holding
  `.bulk-change` lines, `#bulk-verb.btn.critical` for the three destructive verbs.
  `ActionsHandler.bulk_remove_sku_from_orders`, `.bulk_remove_orders_with_sku` and `.bulk_delete_orders` no
  longer ask before writing.

- [ ] **Step 1: Write the failing page tests**

In `tests/test_results_bulk_popover.py`, add two helpers below `_open_sku`:

```python
def _pick(qtbot, view, tag):
    _eval(qtbot, view, f"document.querySelector(\"[data-tag='{tag}']\").click(); true")


def _changes(qtbot, view):
    return _json(
        qtbot,
        view,
        "[...document.querySelectorAll('#bulk-changes .bulk-change')]"
        ".map(e => e.textContent)",
    )
```

Replace `test_the_line_removal_verb_names_the_orders_it_touches` and
`test_the_order_removal_verb_names_the_orders_it_deletes` with:

```python
def test_removing_a_sku_says_what_will_change(qtbot, page):
    """Phase 2 spec section 5.7. 10443 keeps its other line; 10445 has only
    this one. All three orders in the session are fulfillable."""
    view, _ = page
    _open_sku(qtbot, view, ["10443", "10445"], "more-remove-sku")
    assert _eval(qtbot, view, "document.getElementById('bulk-verb').disabled") is True
    assert _eval(qtbot, view, "document.getElementById('bulk-changes').hidden") is True
    _pick(qtbot, view, "TS-4409-B")
    assert _changes(qtbot, view) == [
        "2 TS-4409-B lines removed from 10443, 10445",
        "10445 has no lines left and leaves the session",
        "2 units of TS-4409-B go back to stock",
        "Export goes from 3 to 2 orders",
    ]
    assert _text(qtbot, view, "#bulk-verb") == "Remove TS-4409-B from 2"
    assert "critical" in _eval(qtbot, view, "document.getElementById('bulk-verb').className")
    assert _eval(qtbot, view, "document.getElementById('bulk-verb').disabled") is False
    assert (
        _text(qtbot, view, ".bulk-hint")
        == "You can undo this from the confirmation that follows."
    )


def test_removing_orders_with_a_sku_says_what_will_change(qtbot, page):
    view, _ = page
    _open_sku(qtbot, view, ["10443", "10445"], "more-remove-orders")
    _pick(qtbot, view, "TS-4409-B")
    assert _changes(qtbot, view) == [
        "10443, 10445 leave the session: results, export and labels",
        "3 units go back to stock. Other orders do not get them until you mark"
        " them fulfillable or run the analysis again",
        "Export goes from 3 to 1 order",
    ]
    assert _text(qtbot, view, "#bulk-verb") == "Remove 2 orders"


def test_excluding_orders_needs_no_pick_and_says_what_will_change(qtbot, page):
    view, bridge = page
    _select(qtbot, view, ["10444"])
    _eval(qtbot, view, "document.getElementById('selection-more').click(); true")
    _eval(qtbot, view, "document.getElementById('more-exclude').click(); true")
    assert _text(qtbot, view, "#bulk-title") == "Exclude this order from the run"
    assert _eval(qtbot, view, "document.getElementById('bulk-list').hidden") is True
    assert _changes(qtbot, view) == [
        "10444 leaves the session: results, export and labels",
        "1 unit goes back to stock. Other orders do not get them until you mark"
        " them fulfillable or run the analysis again",
        "Export goes from 3 to 2 orders",
    ]
    assert _text(qtbot, view, "#bulk-verb") == "Exclude 1 order"
    with qtbot.waitSignal(bridge.bulkExcludeRequested, timeout=3000) as blocker:
        _eval(qtbot, view, "document.getElementById('bulk-verb').click(); true")
    assert list(blocker.args) == [["10444"]]


def _line(order, sku, status, note="", qty=1):
    return {
        "Order_Number": order,
        "SKU": sku,
        "Product_Name": "Product " + sku,
        "Quantity": qty,
        "Final_Stock": 10,
        "Order_Fulfillment_Status": status,
        "Shipping_Provider": "DPD",
        "Total_Price": 10.0,
        "Internal_Tags": "[]",
        "Customer": "A",
        "System_note": note,
    }


def test_a_blocked_order_is_told_it_stays_blocked(qtbot, page):
    """The app does not re-evaluate an order when its short line goes, so the
    popover must not promise that it does."""
    view, bridge = page
    short = "Cannot fulfill: X-1: Insufficient stock (need 2, have 0)"
    bridge.set_orders(
        pd.DataFrame(
            [
                _line("B1", "X-1", "Not Fulfillable", short, qty=2),
                _line("B1", "Y-1", "Not Fulfillable", short),
                _line("F1", "Y-1", "Fulfillable"),
            ]
        )
    )
    _until_js(qtbot, view, "document.querySelectorAll('#rows .row').length === 2")
    _open_sku(qtbot, view, ["B1"], "more-remove-sku")
    _pick(qtbot, view, "X-1")
    assert _changes(qtbot, view) == [
        "1 X-1 line removed from B1",
        "B1 stays Blocked until marked fulfillable",
        "Export stays at 1 order",
    ]


def test_fifty_orders_are_named_three_and_counted(qtbot, page):
    """Review focus 2."""
    view, bridge = page
    bridge.set_orders(
        pd.DataFrame([_line(f"O{i:02d}", "S-1", "Fulfillable") for i in range(1, 51)])
    )
    _until_js(qtbot, view, "state.records.length === 50")
    _eval(
        qtbot,
        view,
        "state.selected = new Set(state.records.map(r => r.key)); render(); true",
    )
    _eval(qtbot, view, "document.getElementById('selection-more').click(); true")
    _eval(qtbot, view, "document.getElementById('more-exclude').click(); true")
    assert _changes(qtbot, view)[0] == (
        "O01, O02, O03 and 47 more leave the session: results, export and labels"
    )
    assert _text(qtbot, view, "#bulk-verb") == "Exclude 50 orders"


def test_thirty_skus_scroll_and_the_verb_stays_on_screen(qtbot, page):
    """Review focus 1: the picker scrolls inside the popover; the foot does not."""
    view, bridge = page
    bridge.set_orders(
        pd.DataFrame([_line("W1", f"SKU-{i:02d}", "Fulfillable") for i in range(30)])
    )
    _until_js(qtbot, view, "document.querySelectorAll('#rows .row').length === 1")
    _open_sku(qtbot, view, ["W1"], "more-remove-sku")
    _pick(qtbot, view, "SKU-00")
    fits = _json(
        qtbot,
        view,
        "(function () {"
        " var verb = document.getElementById('bulk-verb').getBoundingClientRect();"
        " var area = document.getElementById('table-area').getBoundingClientRect();"
        " var list = document.getElementById('bulk-list');"
        " return [verb.bottom <= area.bottom, list.scrollHeight > list.clientHeight];"
        " })()",
    )
    assert fits == [True, True]
```

In `tests/test_results_selection_bar.py`:

- `test_more_lists_its_seven_items_in_order` becomes `test_more_lists_its_eight_items_in_order`, and the list
  gains a last entry `"Exclude these 3 orders from the run"`.
- `test_a_separator_sits_above_the_two_destructive_items` becomes
  `test_separators_fence_off_the_exports_and_the_destructive_items` and expects `== 2`.
- Append:

```python
def test_the_bar_has_no_exclude_button_of_its_own(qtbot, page):
    view, _ = page
    _select(qtbot, view, ["10443"])
    assert _eval(qtbot, view, "document.getElementById('selection-exclude')") in (None, "")
    labels = _json(qtbot, view, "moreItems().map(i => i.label || '')")
    assert "Exclude this order from the run" in labels
```

- [ ] **Step 2: Write the failing Python tests**

In `tests/test_actions_handler_bulk.py`, replace the six tests from
`test_bulk_delete_orders_confirms_before_it_writes` through
`test_bulk_remove_orders_with_sku_writes_when_confirmed` with:

```python
@pytest.fixture
def no_confirm(monkeypatch):
    """The popover is the confirmation now (phase 2 spec section 5.7). A Qt
    confirm on top of it would ask twice about something Undo takes back."""

    def refuse(*args, **kwargs):
        raise AssertionError("an undoable bulk action must not confirm")

    monkeypatch.setattr("shared.components.confirm_dialog.ConfirmDialog.ask", refuse)


def test_bulk_delete_orders_writes_without_asking(handler, mw, no_confirm):
    handler.bulk_delete_orders(["10443"])
    assert "10443" not in set(mw.analysis_results_df["Order_Number"])
    mw.undo_manager.record_operation.assert_called_once()
    mw.results_bridge.raise_toast.assert_called_once_with(
        "1 order excluded from the run", undoable=True
    )


def test_bulk_remove_sku_from_orders_writes_without_asking(handler, mw, no_confirm):
    handler.bulk_remove_sku_from_orders(["10443", "10444"], "TS-4409-B")
    remaining = mw.analysis_results_df
    assert "TS-4409-B" not in set(remaining["SKU"])
    assert {"10443", "10444"} <= set(remaining["Order_Number"])
    mw.undo_manager.record_operation.assert_called_once()
    mw.results_bridge.raise_toast.assert_called_once_with(
        "TS-4409-B removed from 2 orders", undoable=True
    )


def test_bulk_remove_orders_with_sku_writes_without_asking(handler, mw, no_confirm):
    handler.bulk_remove_orders_with_sku(["10443", "10444"], "TS-4409-B")
    assert set(mw.analysis_results_df["Order_Number"]) == {"10445"}
    mw.undo_manager.record_operation.assert_called_once()
    mw.results_bridge.raise_toast.assert_called_once_with(
        "2 orders containing TS-4409-B removed", undoable=True
    )


def test_actions_handler_holds_no_confirm_dialog():
    source = Path("gui/actions_handler.py").read_text(encoding="utf-8")
    assert "ConfirmDialog" not in source
```

Remove the `import gui.actions_handler as actions_handler_module` line from that file if nothing else uses it.

In `tests/test_actions_handler.py`, in `test_removing_an_item_asks_nothing_and_offers_undo`, the patch target
`"gui.actions_handler.ConfirmDialog.ask"` becomes `"shared.components.confirm_dialog.ConfirmDialog.ask"`, and
the comment above it becomes "Patched on the class itself: actions_handler no longer imports it."

In `tests/test_undo_manager.py`, delete the `confirm` fixture (line 146) and remove `confirm` from the
parameter list of `test_undo_of_bulk_delete_restores_row_order`; drop the `actions_handler_module` import if
it is now unused.

- [ ] **Step 3: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_results_bulk_popover.py tests/test_results_selection_bar.py tests/test_actions_handler_bulk.py tests/test_actions_handler.py tests/test_undo_manager.py`
Expected: the page tests FAIL (no `#bulk-changes`, no `#more-exclude`); the three `without_asking` tests FAIL
with "an undoable bulk action must not confirm"; `test_actions_handler_holds_no_confirm_dialog` FAILS.

- [ ] **Step 4: Python**

In `gui/actions_handler.py`:

- line 10 becomes `from gui.components import show_error, toast`;
- in `bulk_remove_sku_from_orders`, delete the whole `if not ConfirmDialog.ask(...): return` block. The
  variable `orders_count` is then unused: delete the line
  `orders_count, _ = self.mw.selection_helper.get_selection_summary()` too;
- in `bulk_remove_orders_with_sku`, delete its `if not ConfirmDialog.ask(...): return` block;
- in `bulk_delete_orders`, delete its `if not ConfirmDialog.ask(...): return` block, and change the docstring
  to "Exclude the given orders from the run. The page's popover has already said what will change."

Run `.venv/bin/ruff check gui/actions_handler.py` and remove anything it reports as unused.

- [ ] **Step 5: Markup and CSS**

`gui/web/results.html`: delete the `<span class="spacer"></span>` and the `#selection-exclude` button from
`#selection-bar`.

`gui/web/results.js`, `bind`: remove `selectionExclude: "selection-exclude",` from the `ids` map.

`gui/web/results.css`: replace the bulk popover rules (`.bulk-popover` through the
`.bulk-list .new-tag:focus, .bulk-list .bulk-search:focus` rule) with:

```css
/* --- bulk popover: one surface carries a whole bulk action --------------- */

/* Opens under the selection bar. results.js caps its height to the table
   area, so the foot and its verb are always on screen. */
.bulk-popover { width: 384px; }
.bulk-title { padding: 12px 14px 6px; font-size: var(--type-label-size); font-weight: 700; }
.bulk-body { flex: 1; min-height: 0; overflow-y: auto; }
.bulk-list { max-height: 180px; overflow-y: auto; padding: 0 6px; }
.bulk-list .menu-group { position: sticky; top: 0; background: var(--surface-overlay); }
.bulk-list .field { display: block; width: calc(100% - 8px); margin: 4px; }
.bulk-row.picked { background: var(--selection-bg); }
.bulk-count { margin-left: auto; padding-left: var(--spacing-md); color: var(--text-secondary); }

.bulk-changes {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 10px 14px 0;
  padding: 10px 12px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--kit-radius);
  background: var(--surface-raised);
}
.bulk-changes-title {
  font-size: var(--type-caption-size);
  font-weight: 700;
  color: var(--text-secondary);
}
.bulk-change { position: relative; padding-left: 12px; }
.bulk-change::before {
  content: "";
  position: absolute;
  left: 0;
  top: 0.55em;
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--text-secondary);
}
.bulk-hint {
  margin: 10px 14px 0;
  font-size: var(--type-caption-size);
  color: var(--text-secondary);
}
.bulk-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-sm);
  margin-top: 10px;
  padding: 10px 14px;
  border-top: 1px solid var(--border-subtle);
}
```

- [ ] **Step 6: `bulk.js`**

In `bindSelectionBar`, delete the `els.selectionExclude.addEventListener(...)` block.

In `moreItems`, the tail of the returned array (from `more-copy` on) becomes:

```js
    { id: "more-copy", label: "Copy " + countedWord(n, "order number"), hint: "Ctrl+C", run: copySelection },
    { separator: true },
    {
      id: "more-export-xlsx",
      label: "Export " + theseOrders(n) + " to Excel",
      run: () => exportSelectionAs("xlsx"),
    },
    {
      id: "more-export-csv",
      label: "Export " + theseOrders(n) + " to CSV",
      run: () => exportSelectionAs("csv"),
    },
    { separator: true },
    { id: "more-remove-sku", label: "Remove a SKU from " + theseOrders(n), danger: true, run: () => openSkuPopover("line") },
    { id: "more-remove-orders", label: "Remove whole orders containing a SKU", danger: true, run: () => openSkuPopover("order") },
    { id: "more-exclude", label: "Exclude " + theseOrders(n) + " from the run", danger: true, run: openExcludePopover },
  ];
```

Replace `openBulkPopover` with:

```js
// opts: title, danger, verb(value) -> {text, disabled}, onCommit(value), and
// optionally fill(list, pick) for a picker, rest (the verb's label before a
// pick) and changes(value) -> string[] for a verb that removes something.
function openBulkPopover(opts) {
  closeBulkPopover();
  const box = el("div", "popover bulk-popover");
  box.id = "bulk-popover";
  box.setAttribute("role", "dialog");
  box.setAttribute("aria-label", opts.title);
  // Never taller than the table under the bar, so the foot stays on screen.
  box.style.maxHeight = Math.max(200, els.tableArea.clientHeight - HEADER_PX - 12) + "px";

  const title = el("div", "bulk-title", opts.title);
  title.id = "bulk-title";

  const body = el("div", "bulk-body");
  body.id = "bulk-body";
  const list = el("div", "bulk-list");
  list.id = "bulk-list";
  list.hidden = !opts.fill;
  const changes = el("div", "bulk-changes");
  changes.id = "bulk-changes";
  changes.hidden = true;
  const hint = el("p", "bulk-hint", "You can undo this from the confirmation that follows.");
  hint.hidden = !opts.changes;
  body.append(list, changes, hint);

  const verb = document.createElement("button");
  verb.type = "button";
  verb.id = "bulk-verb";
  verb.className = "btn " + (opts.danger ? "critical" : "primary");
  verb.textContent = opts.rest || "";
  verb.disabled = true;
  const cancel = document.createElement("button");
  cancel.type = "button";
  cancel.className = "btn secondary";
  cancel.textContent = "Cancel";
  cancel.addEventListener("click", closeBulkPopover);
  const footer = el("div", "bulk-footer");
  footer.append(cancel, verb);
  box.append(title, body, footer);

  const pick = (value, row) => {
    bulkPicked = value;
    if (row) {
      for (const other of list.querySelectorAll(".bulk-row")) other.classList.remove("picked");
      row.classList.add("picked");
    }
    const label = opts.verb(value);
    verb.textContent = label.text;
    verb.disabled = label.disabled;
    if (opts.changes) renderBulkChanges(changes, opts.changes(value));
  };
  if (opts.fill) opts.fill(list, pick);

  list.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    const rows = [...list.querySelectorAll(".bulk-row")].filter((r) => !r.hidden);
    const here = rows.indexOf(document.activeElement);
    const next = here + (e.key === "ArrowDown" ? 1 : -1);
    if (next < 0 || next >= rows.length) return;
    e.preventDefault();
    rows[next].focus();
  });

  verb.addEventListener("click", () => {
    const value = bulkPicked;
    closeBulkPopover();
    opts.onCommit(value);
  });

  els.selectionBar.appendChild(box);
  if (!opts.fill) pick(null, null); // nothing to choose: say what will change at once
  const first = list.querySelector(".bulk-row");
  (first || cancel).focus();
  return box;
}

function renderBulkChanges(host, lines) {
  host.textContent = "";
  host.hidden = false;
  host.append(el("div", "bulk-changes-title", "What will change"));
  for (const line of lines) host.append(el("div", "bulk-change", line));
}
```

In `openTagPopover`: add `rest: "Pick a tag",` to the options, and `el("input", "new-tag")` becomes
`el("input", "field new-tag")`.

Above `openSkuPopover`, add the arithmetic. Every line it returns is true of what Python then does:

```js
// Up to four order numbers in full; beyond that three and a count.
function orderList(orders) {
  const ids = orders.map((o) => str(o.Order_Number));
  if (ids.length <= 4) return ids.join(", ");
  return ids.slice(0, 3).join(", ") + " and " + NUMBER.format(ids.length - 3) + " more";
}

// `leaving` fulfillable orders drop out of the export.
function exportLine(leaving) {
  const s = (state.bridge && state.bridge.summary) || {};
  const from = num(s.fulfillable) || 0;
  if (leaving === 0) return "Export stays at " + countedWord(from, "order");
  return "Export goes from " + NUMBER.format(from) + " to " + countedWord(from - leaving, "order");
}

function skuLinesOf(o, sku) {
  return (o.lines || []).filter((line) => str(line.SKU).trim() === sku);
}

function unitsOf(lines) {
  return lines.reduce((sum, line) => sum + (num(line.Quantity) || 0), 0);
}

// Only a fulfillable order's SKU lines draw stock (ADR 0010), so only those
// give units back.
function skuRemovalChanges(sku) {
  const hit = selectedOrders().filter((o) => skuLinesOf(o, sku).length);
  if (!hit.length) return ["None of these orders contain " + sku];
  const lines = hit.reduce((sum, o) => sum + skuLinesOf(o, sku).length, 0);
  const emptied = hit.filter((o) => skuLinesOf(o, sku).length === (o.lines || []).length);
  const blocked = hit.filter((o) => !emptied.includes(o) && !isFulfillable(o));
  const units = unitsOf(hit.filter(isFulfillable).flatMap((o) => skuLinesOf(o, sku)));
  const out = [NUMBER.format(lines) + " " + sku + (lines === 1 ? " line" : " lines") + " removed from " + orderList(hit)];
  if (emptied.length) {
    out.push(orderList(emptied) + (emptied.length === 1
      ? " has no lines left and leaves the session"
      : " have no lines left and leave the session"));
  }
  if (units) out.push(countedWord(units, "unit") + " of " + sku + (units === 1 ? " goes" : " go") + " back to stock");
  if (blocked.length) {
    out.push(orderList(blocked) + (blocked.length === 1 ? " stays" : " stay") + " Blocked until marked fulfillable");
  }
  out.push(exportLine(emptied.filter(isFulfillable).length));
  return out;
}

function orderRemovalChanges(hit, sku) {
  if (!hit.length) return ["None of these orders contain " + sku];
  const ready = hit.filter(isFulfillable);
  const units = unitsOf(ready.flatMap((o) => (o.lines || []).filter((line) => str(line.SKU).trim())));
  const out = [orderList(hit) + (hit.length === 1 ? " leaves" : " leave") + " the session: results, export and labels"];
  if (units) {
    out.push(countedWord(units, "unit") + (units === 1 ? " goes" : " go") + " back to stock."
      + " Other orders do not get them until you mark them fulfillable or run the analysis again");
  }
  out.push(exportLine(ready.length));
  return out;
}
```

In `openSkuPopover`, the options gain a resting label and the changes, the search field takes the kit class,
and the line verb names the SKU:

```js
  openBulkPopover({
    title: line
      ? "Remove a SKU from " + theseOrders(n)
      : "Remove whole orders containing a SKU",
    danger: true,
    rest: "Pick a SKU",
    changes: (sku) =>
      line
        ? skuRemovalChanges(sku)
        : orderRemovalChanges(selectedOrders().filter((o) => skuLinesOf(o, sku).length), sku),
    fill: (host, onPick) => {
      if (skus.length > BULK_SEARCH_ABOVE) {
        const search = el("input", "field bulk-search");
        search.id = "bulk-search";
        search.type = "search";
        search.placeholder = "Find a SKU";
        search.setAttribute("aria-label", "Find a SKU");
        search.addEventListener("input", () => {
          const q = search.value.trim().toLowerCase();
          for (const row of host.querySelectorAll(".bulk-row")) {
            row.hidden = q !== "" && !row.dataset.tag.toLowerCase().includes(q);
          }
        });
        host.appendChild(search);
      }
      renderTagList(host, [{ id: "skus", label: "SKUs on these orders", tags: skus }], badge, onPick);
    },
    verb: (sku) => {
      const on = badge.counts.get(sku) || 0;
      return {
        text: line ? "Remove " + sku + " from " + NUMBER.format(on) : "Remove " + countedWord(on, "order"),
        disabled: on === 0,
      };
    },
    onCommit: (sku) => {
      const keys = selectedKeys();
      if (line) state.bridge.removeSkuFromOrders(keys, sku);
      else state.bridge.removeOrdersWithSku(keys, sku);
    },
  });
```

The first lines of `openSkuPopover` (`n`, `badge`, `skus`, `line`) are unchanged. The only change inside
`fill` is the search field's class, `field bulk-search`.

Below `openSkuPopover`, add:

```js
// Exclude from the run: no picker, so the popover opens already saying what
// will change.
function openExcludePopover() {
  const n = state.selected.size;
  openBulkPopover({
    title: "Exclude " + theseOrders(n) + " from the run",
    danger: true,
    changes: () => orderRemovalChanges(selectedOrders(), ""),
    verb: () => ({ text: "Exclude " + countedWord(n, "order"), disabled: n === 0 }),
    onCommit: () => state.bridge.excludeOrders(selectedKeys()),
  });
}
```

Update the file's header comment: after "the bulk popover and the toast (Bundle 14)." add "The three verbs
that remove orders or lines say what will change and confirm in the popover; no dialog follows (phase 2 spec
section 5.7)."

- [ ] **Step 7: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_results_bulk_popover.py tests/test_results_selection_bar.py tests/test_actions_handler_bulk.py tests/test_actions_handler.py tests/test_undo_manager.py tests/test_results_bridge_bulk.py tests/test_style_literals_guard.py`
Expected: PASS. The tag popover tests pass unchanged (their verb is still `.btn.primary`, they have no
changes box).

- [ ] **Step 8: Commit**

`/usr/bin/git add gui/web gui/actions_handler.py tests/test_results_bulk_popover.py tests/test_results_selection_bar.py tests/test_actions_handler_bulk.py tests/test_actions_handler.py tests/test_undo_manager.py`,
message "Results: the bulk popover says what will change and confirms; the Qt confirms are gone".

---

### Task 9: The column manager as a popover

**Files:**
- Modify: `gui/web/results.html` (`#columns-button`, `#columns-panel`), `gui/web/results.css` (the slot's
  `columns` mode, the column manager section), `gui/web/results.js` (`slotMode`, `renderSlot`),
  `gui/web/columns.js` (`closeColumnsPanel`, `buildColumnsChrome`, `bindColumns`, the section comment)
- Test: `tests/test_results_columns.py`

**Interfaces:**
- Consumes: `.popover`, `.field`, `.btn.ghost.compact` from Task 3.
- Produces: `#columns-anchor` (a `.menu-anchor` in the filter bar) holding `#columns-button` and
  `#columns-panel`; `closeColumnsPanel(restoreFocus = true)`; `data-slot` is only ever `pane`, `rail` or
  `none`; `#columns-button` carries `aria-expanded`.

- [ ] **Step 1: Rewrite the tests**

In `tests/test_results_columns.py`:

`_open_columns` becomes:

```python
def _open_columns(qtbot, view):
    _eval(qtbot, view, "document.getElementById('columns-button').click()")
    _until_js(qtbot, view, "!document.getElementById('columns-panel').hidden")
```

`test_the_manager_keeps_the_table_width_and_counts_shown_and_hidden` becomes:

```python
def test_the_manager_opens_over_the_page_and_the_pane_stays(qtbot, doc):
    """Phase 2 spec section 5.8: a popover under the Columns button, not a
    mode of the slot."""
    view, _ = doc
    _open_columns(qtbot, view)
    assert _width(qtbot, view, ".table-wrap") == 920
    assert (
        _eval(qtbot, view, "document.getElementById('table-area').dataset.slot")
        == "pane"
    )
    assert _eval(qtbot, view, "document.getElementById('pane').hidden") is False
    assert (
        _eval(
            qtbot,
            view,
            "document.getElementById('columns-anchor')"
            ".contains(document.getElementById('columns-panel'))",
        )
        is True
    )
    assert _width(qtbot, view, "#columns-panel") == 280
    assert (
        _eval(qtbot, view, "document.getElementById('columns-count').textContent")
        == "9 shown · 9 hidden"
    )
```

`test_done_closes_the_manager_and_returns_focus_to_the_button` becomes:

```python
def test_a_second_click_on_columns_closes_the_manager(qtbot, doc):
    view, _ = doc
    _open_columns(qtbot, view)
    button = "document.getElementById('columns-button')"
    assert _eval(qtbot, view, f"{button}.getAttribute('aria-expanded')") == "true"
    _eval(qtbot, view, f"{button}.click()")
    _until_js(qtbot, view, "document.getElementById('columns-panel').hidden")
    assert _eval(qtbot, view, "document.activeElement.id") == "columns-button"
    assert _eval(qtbot, view, f"{button}.getAttribute('aria-expanded')") == "false"
    assert _eval(qtbot, view, "document.getElementById('columns-done')") in (None, "")
```

In `test_escape_closes_the_manager`, the final `_until_js` waits for
`"document.getElementById('columns-panel').hidden"` instead of the slot.

Append:

```python
def test_a_click_outside_closes_the_manager_and_one_inside_does_not(qtbot, doc):
    view, _ = doc
    _open_columns(qtbot, view)
    _eval(
        qtbot,
        view,
        "document.getElementById('columns-scroller').dispatchEvent("
        "new MouseEvent('mousedown', {bubbles: true})); true",
    )
    assert _eval(qtbot, view, "document.getElementById('columns-panel').hidden") is False
    _eval(
        qtbot,
        view,
        "document.getElementById('search').dispatchEvent("
        "new MouseEvent('mousedown', {bubbles: true})); true",
    )
    assert _eval(qtbot, view, "document.getElementById('columns-panel').hidden") is True
```

- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_results_columns.py`
Expected: the three rewritten tests and the new one FAIL (the slot goes to `columns`, there is no
`#columns-anchor`).

- [ ] **Step 3: Markup**

In `gui/web/results.html`, the `#columns-button` line in the filter bar becomes:

```html
    <div id="columns-anchor" class="menu-anchor">
      <button id="columns-button" class="btn ghost" type="button"
              aria-haspopup="dialog" aria-expanded="false" disabled></button>
      <div id="columns-panel" class="popover columns-panel" role="dialog" aria-label="Columns" hidden></div>
    </div>
```

and the `<aside id="columns-panel" ...></aside>` line inside `#slot` is deleted.
`test_the_filter_bar_reads_search_add_filter_then_chips` in `tests/test_results_document.py` then expects
`order[-3:] == ["columns-anchor", "screen-menu", "export"]`.

- [ ] **Step 4: CSS**

In `gui/web/results.css`:

- in the split card rules, `.split[data-slot="pane"], .split[data-slot="columns"] { ... }` becomes
  `.split[data-slot="pane"] { grid-template-columns: minmax(0, 1fr) 340px; }`;
- the rule `.pane, .columns-panel { ... }` now selects `.pane` only; delete `.columns-panel { gap: ... }`;
- replace the column manager section (its banner, the "16 + 40 + 8 ..." comment, `.columns-head` through
  `.columns-hide-empty`) with:

```css
/* --- the column manager: a popover under the Columns button -------------- */

.columns-panel {
  left: auto;
  right: 0;
  width: 280px;
  gap: var(--spacing-sm);
  padding: 10px 12px;
}

.columns-head { display: flex; align-items: baseline; gap: var(--spacing-sm); }
.columns-title { flex: 1; font-weight: 700; }
.columns-count-line { font-size: var(--type-caption-size); color: var(--text-secondary); }

.columns-search { width: 100%; }

.columns-scroller { max-height: 340px; overflow-y: auto; scrollbar-gutter: stable; }
.columns-scroller::-webkit-scrollbar { width: 10px; }
.columns-scroller::-webkit-scrollbar-thumb { background: var(--border-subtle); border-radius: 5px; }
.columns-scroller::-webkit-scrollbar-track { background: transparent; }

.col-group {
  position: sticky;
  top: 0;
  z-index: var(--z-sticky); /* .col-row is positioned and comes later, so it paints over an auto z-index */
  height: 22px;
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  background: var(--surface-overlay);
  font-size: var(--type-caption-size);
  font-weight: 700;
  letter-spacing: 0.06em;
  color: var(--text-secondary);
}
.col-group-count { font-weight: 400; letter-spacing: normal; }

.col-row {
  position: relative;
  height: 30px;
  display: grid;
  grid-template-columns: 16px 20px minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--spacing-xs);
  border-radius: var(--radius-md);
}
.col-row:hover { background: var(--hover); }
.col-row:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: -2px; }
.col-grip { display: flex; align-items: center; color: var(--text-secondary); cursor: grab; }
.grip { width: 14px; height: 14px; fill: none; stroke: currentColor; stroke-width: 2.5; stroke-linecap: round; }
.col-title { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.col-title.muted { color: var(--text-secondary); }
.col-note { font-size: var(--type-caption-size); color: var(--text-secondary); white-space: nowrap; }

/* The insertion line a drop would land on. */
.col-row[data-drop]::before {
  content: "";
  position: absolute;
  left: 0;
  right: 0;
  height: 2px;
  background: var(--focus-ring);
}
.col-row[data-drop="before"]::before { top: 0; }
.col-row[data-drop="after"]::before { bottom: 0; }

.columns-foot { display: flex; align-items: center; gap: var(--spacing-sm); }
.columns-hide-empty { display: flex; align-items: center; gap: 6px; white-space: nowrap; }
```

- [ ] **Step 5: Script**

In `gui/web/results.js`, `slotMode` and `renderSlot` become:

```js
function slotMode() {
  if (!state.records.length) return "none";
  return state.paneHidden || (state.narrow && !state.paneForced) ? "rail" : "pane";
}

function renderSlot() {
  const mode = slotMode();
  els.tableArea.dataset.slot = mode;
  els.pane.hidden = mode !== "pane";
  els.paneStrip.hidden = mode !== "rail";
  // The column manager is a popover of its own; it only needs a session.
  if (mode === "none") state.columnsOpen = false;
  els.columnsPanel.hidden = !state.columnsOpen;
  els.columnsButton.disabled = mode === "none";
  els.columnsButton.setAttribute("aria-expanded", String(state.columnsOpen));
  const count = document.createElement("span");
  count.className = "columns-count mono";
  count.textContent = visibleColumns().length + "/" + allColumns().length;
  els.columnsButton.replaceChildren();
  els.columnsButton.insertAdjacentHTML("beforeend", svg(COLUMNS, "glyph"));
  els.columnsButton.append("Columns ", count);
  if (mode === "pane") renderPane();
  if (state.columnsOpen) renderColumnsPanel();
}
```

In `gui/web/columns.js`:

The section comment "The slot's third mode. It shows every column grouped for finding, while the table beside
it keeps the one order a drop rearranges." becomes "A popover under the Columns button (phase 2 spec section
5.8). It shows every column grouped for finding, while the table behind it keeps the one order a drop
rearranges."

`closeColumnsPanel` becomes:

```js
// An outside click closes without taking focus from what was clicked.
function closeColumnsPanel(restoreFocus = true) {
  state.columnsOpen = false;
  columnDragKey = null;
  renderSlot();
  if (restoreFocus) els.columnsButton.focus();
}
```

In `buildColumnsChrome`, the head and the foot become (the search field and the scroller between them are
unchanged apart from the class):

```js
  const head = el("div", "columns-head");
  head.append(el("div", "columns-title", "Columns"), el("div", "columns-count-line"));
  head.lastChild.id = "columns-count";

  const search = el("input", "field columns-search");
```

```js
  const reset = paneButton("ghost compact", "Reset");
  reset.id = "columns-reset";
  reset.title = "Reset to defaults";
  reset.addEventListener("click", () => storeColumns({ order: null, visible: null }, (b) => b.resetColumns()));
  foot.append(hideLabel, el("span", "spacer"), reset);

  panel.append(head, search, scroller, foot);
```

The `close` button (`#columns-close`), the `titles` wrapper and the `done` button are deleted.

`bindColumns` becomes:

```js
function bindColumns() {
  els.columnsButton.addEventListener("click", () =>
    state.columnsOpen ? closeColumnsPanel() : openColumnsPanel(),
  );
  els.columnsPanel.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    e.stopPropagation();
    closeColumnsPanel();
  });
  document.addEventListener("mousedown", (e) => {
    if (state.columnsOpen && !e.target.closest("#columns-anchor")) closeColumnsPanel(false);
  });
}
```

- [ ] **Step 6: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_results_columns.py tests/test_results_document.py tests/test_results_pane.py tests/test_style_literals_guard.py`
Expected: PASS, including the drag, Alt+arrow, search, group-count, reset and auto-hide tests, which do not
care where the panel sits.

- [ ] **Step 7: Commit**

`/usr/bin/git add gui/web tests/test_results_columns.py tests/test_results_document.py`, message
"Results: the column manager is a popover and the pane stays up".

---

### Task 10: The detail pane

**Files:**
- Modify: `gui/web/pane.js` (everything from `renderPane` through `paneActions`, `menuItem`,
  `openPaneMenu`, `openTagMenu`, `openQtyMenu`, `bindPane`), `gui/web/results.css` (the pane section)
- Test: `tests/test_results_pane.py`

**Interfaces:**
- Consumes: `statusBadge(o)` from Task 4; `.code`, `.field`, `.btn.ghost.danger`, `.btn.compact` from Task 3;
  `num`, `str`, `fmtInt`, `fmtMoney`, `fmtAge`, `ageMs`, `plural`, `NUMBER`, `DASH` from `results.js`.
- Produces: in the pane: `.pane-head` (`.pane-title` with `.pane-order` inside, a `.badge`, `#pane-hide`),
  `.pane-body`, `.verdict` (unchanged classes), `.pane-meta`, `.pane-codes .code`, `.pane-numbers`,
  `.lines .line[data-index]` with `.line-sku`, `.line-qty`, `.line-product`, `.line-stock`, `.line-lot`,
  `.line-menu-button`; `.pane-tags`, `.pane-notes`, `.pane-actions` (`#pane-status-verb`, `#pane-exclude`,
  `.pane-position`). `#pane-more` is removed. `reasonCodes(o) -> string[]`, `stockSentence(o, line)`,
  `lotTexts(line) -> string[]`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_results_pane.py`:

In `test_a_short_order_names_the_sku_and_both_numbers`, `== "2 of 4"` becomes `== "↑ ↓  2 / 4"` (two spaces
after the arrows).

Append:

```python
def _codes(qtbot, view):
    return _eval(
        qtbot,
        view,
        "[...document.querySelectorAll('#pane .pane-codes .code')]"
        ".map(c => c.textContent).join('|')",
    )


def test_the_header_names_the_order_and_wears_its_status(qtbot, doc):
    view, _ = doc
    assert _text(qtbot, view, "#pane .pane-title") == "Order detail"
    _select(qtbot, view, "#10445")
    assert _text(qtbot, view, "#pane .pane-title") == "Order #10445"
    assert _text(qtbot, view, "#pane .pane-head .badge") == "Blocked"
    assert (
        _eval(qtbot, view, "document.getElementById('pane-hide').title") == "Hide detail"
    )


@pytest.mark.parametrize(
    ("order", "codes"),
    [
        ("#10443", "ALL_LINES_IN_STOCK"),
        ("#10445", "STOCK_SHORT"),
        ("#10447", "NO_SKU"),
        ("#10449", "MARKED_FULFILLABLE|OUT_OF_STOCK"),
    ],
)
def test_the_reason_codes_follow_the_verdict(qtbot, doc, order, codes):
    view, _ = doc
    _select(qtbot, view, order)
    assert _codes(qtbot, view) == codes


def test_a_hand_hold_and_a_rule_hold_name_themselves(qtbot, doc):
    view, bridge = doc
    row = pane_lines().iloc[0].to_dict()
    held = {"Order_Fulfillment_Status": "Not Fulfillable"}
    bridge.set_orders(
        pd.DataFrame(
            [
                {**row, **held, "Order_Number": "H1", "System_note": ""},
                {
                    **row,
                    **held,
                    "Order_Number": "R1",
                    "System_note": "Cannot fulfill: Held by rule: Fragile first",
                },
            ]
        )
    )
    _until_js(qtbot, view, "document.querySelectorAll('#rows .row').length === 2")
    _select(qtbot, view, "H1")
    assert _codes(qtbot, view) == "HELD_BY_USER"
    _select(qtbot, view, "R1")
    assert _codes(qtbot, view) == "HELD_BY_RULE"


def test_the_meta_line_gathers_who_where_how_old_and_how_much(qtbot, doc):
    view, _ = doc
    _select(qtbot, view, "#10443")
    meta = _text(qtbot, view, "#pane .pane-meta")
    assert meta.startswith("B. Fischer · AT · DPD · ")
    assert meta.endswith(" old · 204.30")
    assert _text(qtbot, view, "#pane .pane-numbers") == "2 lines · 6 units"


def test_a_line_says_what_stock_it_has(qtbot, doc):
    view, _ = doc
    _select(qtbot, view, "#10445")
    short = "#pane .line[data-index=\"0\"] .line-stock"
    assert _text(qtbot, view, short) == "4 of 6 in stock, short 2"
    assert (
        _eval(qtbot, view, f"document.querySelector('{short}').classList.contains('short')")
        is True
    )
    assert _text(qtbot, view, "#pane .line[data-index=\"1\"] .line-stock") == "18 left in stock"
    assert _text(qtbot, view, "#pane .line[data-index=\"0\"] .line-sku") == "TS-4409-B"
    assert _text(qtbot, view, "#pane .line[data-index=\"0\"] .line-qty") == "× 6"
    _select(qtbot, view, "#10449")
    assert _text(qtbot, view, "#pane .line[data-index=\"0\"] .line-stock") == "None in stock"


def test_a_line_names_its_lot(qtbot, doc):
    view, bridge = doc
    lot = {
        "batch": "B7",
        "expiry": "261230",
        "expiry_dt": pd.Timestamp("2026-12-30").date(),
        "qty_allocated": 4,
    }
    lines = pane_lines()
    lines["Lot_Details"] = [[lot] if i == 0 else None for i in range(len(lines))]
    bridge.set_orders(lines)
    _until_js(qtbot, view, "document.querySelectorAll('#rows .row').length === 4")
    _select(qtbot, view, "#10443")
    # The click can land before the new payload does; wait for the lot itself.
    _until_js(qtbot, view, "!!document.querySelector('#pane .line-lot')")
    assert _text(qtbot, view, "#pane .line[data-index=\"0\"] .line-lot") == "Lot B7 · exp 261230"
    assert _eval(qtbot, view, "document.querySelectorAll('#pane .line-lot').length") == 1


def test_the_last_line_cannot_be_removed(qtbot, doc):
    view, _ = doc
    _select(qtbot, view, "#10449")  # one line
    _js(qtbot, view, "document.querySelector('#pane .line .line-menu-button').click()")
    item = (
        "[...document.querySelectorAll('#line-menu .menu-item')]"
        ".find(b => b.textContent === 'Remove this line')"
    )
    assert _eval(qtbot, view, f"{item}.disabled") is True
    assert _eval(qtbot, view, f"{item}.title") == "Last line: exclude the order instead"


def test_the_footer_holds_the_verb_exclude_and_the_position(qtbot, doc):
    view, _ = doc
    _select(qtbot, view, "#10443")
    assert _text(qtbot, view, "#pane-exclude") == "Exclude order"
    assert _text(qtbot, view, "#pane .pane-position") == "↑ ↓  1 / 4"
    assert _eval(qtbot, view, "document.getElementById('pane-more')") in (None, "")
    fits = _eval(
        qtbot,
        view,
        "(function () { var f = document.querySelector('#pane .pane-actions');"
        " return f.scrollWidth <= f.clientWidth; })()",
    )
    assert fits is True
```

- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_results_pane.py`
Expected: the new tests FAIL (no `.pane-title`, no `.pane-codes`, no `.line-stock`).

- [ ] **Step 3: `pane.js`**

Replace the `FLAG_CHIPS` constant with:

```js
const FLAG_CODES = [["_repeat", "REPEAT_CUSTOMER"], ["Unknown_SKU", "UNKNOWN_SKU"], ["Low_Stock", "LOW_STOCK"]];
const PROBLEM_CODES = {
  short: "STOCK_SHORT",
  out_of_stock: "OUT_OF_STOCK",
  invalid_quantity: "INVALID_QUANTITY",
  no_sku: "NO_SKU",
  rule_hold: "HELD_BY_RULE",
  other: "OTHER",
};
```

`problemSentence`, `verdictCopy` and `paneRecord` are unchanged. Replace everything from `renderPane` through
`paneActions` with:

```js
function renderPane() {
  const pane = els.pane;
  pane.textContent = ""; // also drops any open pane menu
  const hit = paneRecord();

  const head = el("div", "pane-head");
  const title = el("span", "pane-title", hit ? "Order " : "Order detail");
  if (hit) title.append(el("span", "pane-order", str(hit.o.Order_Number)));
  head.append(title);
  if (hit) head.append(statusBadge(hit.o));
  const hide = paneButton("ghost icon compact", undefined, "Hide detail");
  hide.id = "pane-hide";
  hide.innerHTML = svg(CHEVRON_RIGHT, "glyph");
  hide.addEventListener("click", hidePane);
  head.append(hide);
  pane.append(head);

  if (!hit) {
    const empty = el("div", "pane-empty");
    empty.id = "pane-empty";
    empty.append(
      el("p", "state-title", "No order selected"),
      el("p", "state-text", "Click a row to see whether it can ship and, if it cannot, why. ↑ ↓ moves through the " +
        NUMBER.format(state.view.length) + " shown."),
    );
    pane.append(empty);
    return;
  }
  const o = hit.o;
  const body = el("div", "pane-body");
  body.append(paneVerdict(o), paneMeta(o), paneCodes(o), paneLines(o), paneTags(o), paneNotes(o));
  pane.append(body, paneFooter(o, hit.index));
}

function paneVerdict(o) {
  const v = o.Verdict || {};
  const copy = verdictCopy(o);
  const box = el("div", "verdict");
  box.dataset.state = v.state || "ready";
  box.dataset.role = copy.role;
  box.dataset.byHand = String(Boolean(v.by_hand));
  const title = el("div", "verdict-title");
  // The mark: hollow when the run detected it, solid when a person set it.
  title.append(el("span", "mark" + (v.by_hand ? " solid" : "")), document.createTextNode(copy.title));
  box.append(title, el("p", "verdict-text", copy.text));
  if (copy.source) box.append(el("p", "verdict-source", copy.source));
  return box;
}

function paneMeta(o) {
  const parts = [o.Customer, o.Destination_Country, o.Shipping_Provider].map((v) => str(v).trim()).filter(Boolean);
  if (ageMs(o.Created_At) !== null) parts.push(fmtAge(o.Created_At) + " old");
  if (num(o.Total_Price) !== null) parts.push(fmtMoney(o.Total_Price));
  return el("div", "pane-meta", parts.length ? parts.join(" · ") : DASH);
}

// The verdict's causes as machine words, then the order's flags.
function reasonCodes(o) {
  const v = o.Verdict || { state: "ready", by_hand: false, problems: [] };
  const codes = [];
  if (v.state === "ready") codes.push("ALL_LINES_IN_STOCK");
  if (v.by_hand) codes.push(isFulfillable(o) ? "MARKED_FULFILLABLE" : "HELD_BY_USER");
  for (const p of v.problems || []) codes.push(PROBLEM_CODES[p.code] || PROBLEM_CODES.other);
  for (const [field, code] of FLAG_CODES) if (o[field] === true) codes.push(code);
  return [...new Set(codes)];
}

function paneCodes(o) {
  const box = el("div", "pane-codes");
  for (const code of reasonCodes(o)) box.append(el("span", "code", code));
  return box;
}

// What the run saw for a short line; stock left for every other.
function stockSentence(o, line) {
  if (line.Short) {
    const sku = str(line.SKU);
    const p = ((o.Verdict && o.Verdict.problems) || []).find((x) => x.sku === sku);
    if (p && p.code === "short") {
      return { short: true, text: NUMBER.format(p.have) + " of " + NUMBER.format(p.need) +
        " in stock, short " + NUMBER.format(p.need - p.have) };
    }
    return { short: true, text: "None in stock" };
  }
  const left = num(line.Final_Stock);
  return left === null ? null : { short: false, text: NUMBER.format(left) + " left in stock" };
}

// The run writes "1" where the stock file has no lot; that is not a label.
function lotWord(value) {
  const text = str(value).trim();
  return text === "1" ? "" : text;
}

// One caption per lot. A cell read back from disk as text is shown as it is.
function lotTexts(line) {
  const lots = line.Lot_Details;
  if (!lots) return [];
  if (!Array.isArray(lots)) return [str(lots)];
  const real = lots.filter((lot) => lot && typeof lot === "object");
  return real.map((lot) => {
    const parts = [];
    if (lotWord(lot.batch)) parts.push("Lot " + lotWord(lot.batch));
    if (lotWord(lot.expiry)) parts.push("exp " + lotWord(lot.expiry));
    if (parts.length && real.length > 1 && num(lot.qty_allocated) !== null) {
      parts.push("×" + NUMBER.format(lot.qty_allocated));
    }
    return parts.join(" · ");
  }).filter(Boolean);
}

function paneLines(o) {
  const order = str(o.Order_Number);
  const lines = o.lines || [];
  const wrap = el("div", "pane-lines");
  wrap.append(el("div", "pane-numbers", plural(lines.length, "line") + " · " + plural(num(o.Units) || 0, "unit")));
  const box = el("div", "lines");
  lines.forEach((line, index) => {
    const sku = str(line.SKU);
    const row = el("div", "line" + (line.Short ? " short" : ""));
    row.dataset.index = String(index);
    const main = el("div", "line-main");
    const top = el("div", "line-top");
    top.append(el("span", "line-sku", sku || DASH), el("span", "line-qty", "× " + fmtInt(line.Quantity)));
    main.append(top);
    if (str(line.Product_Name)) {
      const product = el("div", "line-product", str(line.Product_Name));
      product.title = str(line.Product_Name);
      main.append(product);
    }
    const stock = stockSentence(o, line);
    if (stock) main.append(el("div", "line-stock" + (stock.short ? " short" : ""), stock.text));
    for (const text of lotTexts(line)) main.append(el("div", "line-lot", text));
    const more = paneButton("ghost icon compact line-menu-button", "⋯", "Actions for this line");
    more.addEventListener("click", () => openPaneMenu(more, "line-menu", [
      ["Remove this line", () => state.bridge.removeLine(order, index, sku),
        lines.length < 2 ? "Last line: exclude the order instead" : ""],
      ["Change quantity…", () => openQtyMenu(more, order, index, sku, line.Quantity)],
      ["Copy SKU", () => state.bridge.copyText(sku)],
    ]));
    row.append(main, more);
    box.append(row);
  });
  wrap.append(box);
  return wrap;
}

function paneTags(o) {
  const order = str(o.Order_Number);
  const box = el("div", "pane-tags");
  for (const tag of (o.Tag_List || []).map(String)) {
    const chip = paneButton("", tag + "  ×", "Remove tag " + tag);
    chip.className = "chip-filter tag-chip";
    chip.dataset.tag = tag;
    chip.addEventListener("click", () => state.bridge && state.bridge.removeOrderTag(order, tag));
    box.append(chip);
  }
  const add = paneButton("ghost compact", "+ Tag");
  add.id = "pane-add-tag";
  add.addEventListener("click", () => openTagMenu(add, o));
  box.append(add);
  return box;
}

function paneNotes(o) {
  const parts = [str(o.Notes).trim(), str(o.Status_Note).trim()].filter(Boolean);
  if (str(o.Tags).trim()) parts.push("Shopify tags: " + str(o.Tags).trim());
  return el("p", "pane-notes", parts.length ? parts.join("\n") : "No notes on this order.");
}

// Never a primary: the screen's one primary is Export. Copy order number
// left with its menu: Ctrl+C copies the cursor's order (bulk.js).
function paneFooter(o, index) {
  const order = str(o.Order_Number);
  const fulfillable = isFulfillable(o);
  const box = el("div", "pane-actions");
  const verb = paneButton("secondary", fulfillable ? "Hold" : "Mark fulfillable");
  verb.id = "pane-status-verb";
  verb.addEventListener("click", () => {
    if (!state.bridge) return;
    if (fulfillable) state.bridge.holdOrder(order);
    else state.bridge.fulfillOrder(order);
  });
  const exclude = paneButton("ghost danger", "Exclude order");
  exclude.id = "pane-exclude";
  exclude.addEventListener("click", () => state.bridge && state.bridge.excludeOrder(order));
  const position = el("span", "pane-position",
    "↑ ↓  " + NUMBER.format(index + 1) + " / " + NUMBER.format(state.view.length));
  box.append(verb, exclude, el("span", "spacer"), position);
  return box;
}
```

`menuItem` and `openPaneMenu` take an optional third entry, the reason an item is disabled:

```js
function menuItem(label, act, disabledTitle) {
  const item = el("button", "menu-item", label);
  item.type = "button";
  item.setAttribute("role", "menuitem");
  if (disabledTitle) {
    item.disabled = true;
    item.title = disabledTitle;
  }
  item.addEventListener("click", () => {
    closePaneMenus();
    if (state.bridge) act();
  });
  return item;
}

function openPaneMenu(anchor, id, items) {
  const menu = newMenu(id);
  for (const [label, act, disabledTitle] of items) menu.append(menuItem(label, act, disabledTitle));
  placeMenu(menu, anchor);
}
```

In `openTagMenu` and `openQtyMenu`, `el("input", "new-tag")` becomes `el("input", "field new-tag")`.

In `bindPane`, the outside-click selector loses `#pane-more`:
`".pane-menu, .line-menu-button, #pane-add-tag"`.

Update the file's header comment to: "The order detail pane (phase 2 spec section 5.9): the cursor order's
header, verdict, reason codes, lines, tags, notes and footer. One order, never the checked set. No optimistic
updates: it changes when `orders` comes back."

- [ ] **Step 4: CSS**

In `gui/web/results.css`, replace the pane section, from its banner
(`/* --- detail pane and column manager planes ...`) through `.pane-empty { ... }`, with the block below.
The rail rules Task 4 wrote (`.pane-strip`, `.pane-rail`, `.pane-rail-label`) stay after it, and so does
`.tag-chip:focus-visible`.

```css
/* --- detail pane (phase 2 spec section 5.9) ------------------------------ */

.pane {
  position: relative;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--surface);
}

.pane-head {
  flex: none;
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  height: var(--table-head-height);
  padding: 0 6px 0 14px;
  background: var(--surface-raised);
  border-bottom: 1px solid var(--border-subtle);
}
.pane-title {
  flex: 1;
  min-width: 0;
  font-weight: 700;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.pane-order { font-family: var(--font-family-mono); }

/* The body scrolls; the header and the footer never do. */
.pane-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 14px;
}

.verdict[data-role="success"] { --role: var(--status-success); }
.verdict[data-role="danger"] { --role: var(--status-danger); }
.verdict[data-role="warning"] { --role: var(--status-warning); }
.verdict-title {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: var(--type-heading-size);
  font-weight: 700;
  line-height: 1.3;
  color: var(--role);
}
/* The mark (CONTEXT.md): hollow when detected by the run, solid when set by a person. */
.mark { flex-shrink: 0; width: 8px; height: 8px; border: 1.5px solid var(--role); border-radius: 50%; }
.mark.solid { background: var(--role); }
.verdict-text { margin: 6px 0 0; }
.verdict-source { margin: var(--spacing-xs) 0 0; font-size: var(--type-caption-size); color: var(--text-secondary); }

.pane-meta { font-size: var(--type-caption-size); color: var(--text-secondary); }
.pane-codes { display: flex; flex-wrap: wrap; gap: var(--spacing-xs); }

.pane-lines { display: flex; flex-direction: column; gap: 6px; }
.pane-numbers { font-size: var(--type-caption-size); font-weight: 700; color: var(--text-secondary); }
.lines { border: 1px solid var(--border-subtle); border-radius: var(--kit-radius); }
.line {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-sm);
  padding: 8px 6px 8px 10px;
}
.line + .line { border-top: 1px solid var(--border-subtle); }
.line-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.line-top { display: flex; align-items: baseline; gap: var(--spacing-sm); }
.line-sku { font-family: var(--font-family-mono); font-weight: 700; }
.line-qty {
  font-family: var(--font-family-mono);
  font-size: var(--type-caption-size);
  color: var(--text-secondary);
}
.line-product, .line-stock, .line-lot { font-size: var(--type-caption-size); color: var(--text-secondary); }
.line-product { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.line-stock.short { color: var(--status-danger); font-weight: 700; }

.pane-tags { display: flex; flex-wrap: wrap; align-items: center; gap: var(--spacing-xs); }
.pane-notes {
  margin: 0;
  white-space: pre-line;
  font-size: var(--type-caption-size);
  color: var(--text-secondary);
}

.pane-actions {
  flex: none;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 14px;
  border-top: 1px solid var(--border-subtle);
}
.pane-position {
  font-family: var(--font-family-mono);
  font-size: var(--type-caption-size);
  color: var(--text-secondary);
  white-space: nowrap;
}

/* Menus open upward inside the pane, which clips anything outside it. */
.pane-menu { top: auto; max-height: 240px; }
.pane-menu .field { display: block; width: calc(100% - 8px); margin: 4px; }

.pane-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: var(--spacing-xl);
  text-align: center;
}
.pane-empty .state-title { font-size: inherit; }
```

- [ ] **Step 5: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_results_pane.py tests/test_pane_actions.py tests/test_results_bulk_popover.py tests/test_results_document.py tests/test_style_literals_guard.py`
Expected: PASS. If `test_the_footer_holds_the_verb_exclude_and_the_position` fails on the fit (Inter is wider
than the mockup's Segoe UI), give the footer's two buttons the kit's `compact` class
(`paneButton("secondary compact", ...)` and `paneButton("ghost danger compact", "Exclude order")`) and run
again. Do not shorten the copy.

- [ ] **Step 6: Commit**

`/usr/bin/git add gui/web tests/test_results_pane.py`, message
"Results: the detail pane to the mockup, with reason codes and stock per line".

---

### Task 11: The toast can be dismissed

**Files:**
- Modify: `gui/web/results.html` (`#toast`), `gui/web/bulk.js` (`bindToast`), `gui/web/results.js` (`bind`)
- Test: `tests/test_results_toast.py`

**Interfaces:**
- Consumes: `.toast`, `.toast-text`, `.toast-action`, `.toast-close` from Task 3; `X_MARK` from Task 6.
- Produces: `#toast-dismiss`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_results_toast.py`, extend the import to `from test_results_bridge import _eval, _rgb, _until_js`,
add `from shared.theme import LIGHT_THEME`, and append:

```python
def test_the_toast_can_be_dismissed(qtbot, page):
    view, bridge = page
    bridge.raise_toast("3 orders held")
    _until_js(qtbot, view, "document.getElementById('toast').hidden === false")
    assert (
        _eval(qtbot, view, "document.getElementById('toast-dismiss').getAttribute('aria-label')")
        == "Dismiss"
    )
    _eval(qtbot, view, "document.getElementById('toast-dismiss').click(); true")
    assert _eval(qtbot, view, "document.getElementById('toast').hidden") is True


def test_the_toast_sits_on_the_inverse_plane(qtbot, page):
    view, bridge = page
    bridge.raise_toast("3 orders held")
    _until_js(qtbot, view, "document.getElementById('toast').hidden === false")
    assert _eval(
        qtbot, view, "getComputedStyle(document.getElementById('toast')).backgroundColor"
    ) == _rgb(LIGHT_THEME.surface_inverse)
```

- [ ] **Step 2: Run them and see the first fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_results_toast.py`
Expected: `test_the_toast_can_be_dismissed` FAILS (no `#toast-dismiss`). The plane test passes already: the
kit dressed the toast in Task 3.

- [ ] **Step 3: Implement**

`gui/web/results.html`, the toast becomes:

```html
  <div id="toast" class="toast" role="status" aria-live="polite" hidden>
    <span id="toast-text" class="toast-text"></span>
    <span id="toast-badge" class="toast-badge" hidden></span>
    <button id="toast-undo" class="toast-action" type="button" hidden>Undo</button>
    <button id="toast-dismiss" class="toast-close" type="button" aria-label="Dismiss" title="Dismiss"></button>
  </div>
```

`gui/web/results.js`, `bind`: add `toastDismiss: "toast-dismiss",` to the `ids` map.

`gui/web/bulk.js`, `bindToast` becomes:

```js
function bindToast() {
  els.toastUndo.addEventListener("click", () => {
    dismissToast();
    if (state.bridge) state.bridge.undo();
  });
  els.toastDismiss.innerHTML = svg(X_MARK, "glyph");
  els.toastDismiss.addEventListener("click", dismissToast);
}
```

and the comment above `TOAST_MS` becomes: "The page's own toast (ADR 0007). It follows the web kit; the Qt
toast in shared/components/toast.py keeps its look until its screens move."

- [ ] **Step 4: Run the tests and commit**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_results_toast.py`
Expected: PASS.

`/usr/bin/git add gui/web tests/test_results_toast.py`, message "Results: the toast has a dismiss button".

---

### Task 12: The session chip on Results, and the screen menu

**Files:**
- Modify: `gui/components/commandbar.py` (`__init__`, `set_status`, `set_stock_age`, `_refresh`; new
  `set_results_mode`, `_style_session`, `_refresh_meta`), `gui/ui_manager.py` (`_SCREEN_ACTIONS`,
  `_create_tabs`, `_create_results_overflow`; new `_refresh_results_menu`, `_copy_results_summary`),
  `gui/orders_view.py` (new `summary_text`)
- Test: `tests/test_commandbar_states.py`, `tests/test_results_summary.py`, `tests/test_results_screen.py`,
  `tests/test_screen_primary_actions.py`

**Interfaces:**
- Produces: `CommandBar.set_results_mode(on: bool) -> None`, `CommandBar.meta_label: QLabel`;
  `gui.orders_view.summary_text(summary: dict) -> str`; `mw.rerun_analysis_action`, `mw.open_folder_action`,
  `mw.copy_summary_action` (`QAction`s in `mw.results_menu`, before the two it holds today).

- [ ] **Step 1: Write the failing tests**

In `tests/test_results_summary.py`, append:

```python
def test_summary_text_is_the_kpi_strip_on_one_line():
    from gui.orders_view import summary_text

    summary = {
        "orders": 40,
        "fulfillable": 30,
        "blocked": 10,
        "labels_by_courier": [["DHL", 10], ["DPD", 10], ["Speedy", 10]],
        "value_ready": None,
    }
    assert summary_text(summary) == (
        "40 orders · 30 fulfillable · 10 blocked · labels DHL 10, DPD 10, Speedy 10"
    )
    assert summary_text({**summary, "value_ready": 1234.5}).endswith(
        " · value ready 1234.50"
    )
    assert summary_text({**summary, "labels_by_courier": []}) == (
        "40 orders · 30 fulfillable · 10 blocked"
    )
    assert summary_text({}) == ""
```

In `tests/test_commandbar_states.py`, append:

```python
def _analysed(bar):
    bar.set_session_text("2026-09-30_1")
    bar.set_status("text_secondary", "Analysed 14:06")
    bar.set_stock_age("Stock file 19 h old")
    bar.set_state(BarState.SESSION)
    return bar


def test_results_mode_draws_the_session_as_a_chip_and_its_age_as_text(bar):
    """Phase 2 spec section 6.1."""
    _analysed(bar).set_results_mode(True)
    assert not bar.status_chip.isVisible()
    assert not bar.stock_chip.isVisible()
    assert not bar.open_folder_button.isVisible()
    assert bar.meta_label.isVisible()
    assert bar.meta_label.text() == "analysed 14:06 · stock file 19 h old"
    assert bar.session_button.text() == "2026-09-30_1"
    assert "border-radius: 6px" in bar.session_button.styleSheet()


def test_leaving_results_mode_puts_the_bar_back(bar):
    _analysed(bar).set_results_mode(True)
    bar.set_results_mode(False)
    assert bar.status_chip.isVisible()
    assert bar.stock_chip.isVisible()
    assert bar.open_folder_button.isVisible()
    assert not bar.meta_label.isVisible()
    assert "border-radius" not in bar.session_button.styleSheet()


def test_results_mode_follows_chips_that_change_under_it(bar):
    _analysed(bar).set_results_mode(True)
    bar.set_stock_age("")
    assert bar.meta_label.text() == "analysed 14:06"
    assert not bar.stock_chip.isVisible()
    bar.set_status("text_secondary", "")
    assert not bar.meta_label.isVisible()


def test_results_mode_with_no_session_adds_nothing(bar):
    bar.set_state(BarState.NO_SESSION)
    bar.set_results_mode(True)
    assert not bar.meta_label.isVisible()
```

In `tests/test_results_screen.py`, replace `test_the_screen_menu_holds_add_product_and_undo` and
`test_results_binds_run_analysis_as_the_secondary_action` with the four tests below:

```python
def test_the_screen_menu_holds_what_left_the_bar_then_add_product_and_undo(main_window):
    actions = main_window.results_menu.actions()
    assert [a.text() for a in actions[:3]] == [
        "Run analysis again",
        "Open session folder",
        "Copy summary",
    ]
    assert actions[3].isSeparator()
    assert actions[4:] == [main_window.add_product_button_tab2, main_window.undo_button]


def test_results_has_no_bar_action_and_draws_the_session_chip(main_window):
    from PySide6.QtWidgets import QApplication

    bar = main_window.command_bar
    main_window.main_tabs.setCurrentIndex(1)
    QApplication.processEvents()
    assert bar._bound_action is None
    assert bar.action_button.isHidden()
    assert bar._results_mode is True
    main_window.main_tabs.setCurrentIndex(0)
    QApplication.processEvents()
    assert bar._results_mode is False
    assert bar.action_button.property("role") == "primary"


def test_run_analysis_again_clicks_the_run_button_and_follows_its_state(main_window):
    """The real button starts an analysis, so a stand-in takes its place: the
    menu reads `mw.run_analysis_button` when it is used, not when it is built."""
    from PySide6.QtWidgets import QPushButton

    real = main_window.run_analysis_button
    stub = QPushButton("stand-in")
    clicks = []
    stub.clicked.connect(lambda: clicks.append(1))
    main_window.run_analysis_button = stub
    try:
        stub.setEnabled(False)
        main_window.results_menu.aboutToShow.emit()
        assert not main_window.rerun_analysis_action.isEnabled()
        stub.setEnabled(True)
        main_window.results_menu.aboutToShow.emit()
        assert main_window.rerun_analysis_action.isEnabled()
        main_window.rerun_analysis_action.trigger()
        assert clicks == [1]
    finally:
        main_window.run_analysis_button = real


def test_copy_summary_puts_the_numbers_on_the_clipboard(main_window, lines_df):
    from PySide6.QtGui import QGuiApplication

    main_window.results_menu.aboutToShow.emit()
    assert not main_window.copy_summary_action.isEnabled()
    main_window.results_bridge.set_orders(lines_df)
    main_window.results_menu.aboutToShow.emit()
    assert main_window.copy_summary_action.isEnabled()
    main_window.copy_summary_action.trigger()
    assert QGuiApplication.clipboard().text().startswith(
        f"{main_window.results_bridge.summary['orders']} orders · "
    )
```

`lines_df` is that file's existing fixture (`test_set_ui_busy_drives_the_pages_export` uses it).

In `tests/test_screen_primary_actions.py`: in `test_each_screen_puts_its_own_primary_in_the_bar`, the
`expected` dict loses its entry `1` and the comment about Results becomes "Results (1) has no bar action:
re-running the analysis lives in its screen menu (phase 2 spec section 6)". In
`test_a_screen_with_no_primary_hides_the_slot`, `for index in (3, 4):` becomes `for index in (1, 3, 4):`.

- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_commandbar_states.py tests/test_results_summary.py tests/test_results_screen.py tests/test_screen_primary_actions.py`
Expected: FAIL (`CommandBar` has no `set_results_mode`, `summary_text` cannot be imported, the menu has two
actions).

- [ ] **Step 3: `summary_text` (`gui/orders_view.py`)**

Below `results_summary`, add:

```python
def summary_text(summary: dict) -> str:
    """The KPI strip as one line for the clipboard (phase 2 spec section 6.2)."""
    if not summary:
        return ""
    parts = [
        f"{summary['orders']} orders",
        f"{summary['fulfillable']} fulfillable",
        f"{summary['blocked']} blocked",
    ]
    labels = ", ".join(
        f"{name} {count}" for name, count in summary.get("labels_by_courier") or []
    )
    if labels:
        parts.append(f"labels {labels}")
    if summary.get("value_ready") is not None:
        parts.append(f"value ready {summary['value_ready']:.2f}")
    return " · ".join(parts)
```

- [ ] **Step 4: The command bar (`gui/components/commandbar.py`)**

In `__init__`, after `self._restore_client = ""`, add `self._results_mode = False`.

Delete the line `self.session_button.setStyleSheet(font_css("caption"))`.

After the `self.stock_chip` block (`layout.addWidget(self.stock_chip)`), add:

```python
        # Results only (phase 2 spec section 6.1): the two chips' text as one
        # quiet caption beside the session chip.
        self.meta_label = QLabel("", self)
        self.meta_label.hide()
        layout.addWidget(self.meta_label)
```

At the very end of `__init__`, after `self._progress = (0, "")`, add:

```python
        self._style_session()
        get_theme_manager().theme_changed.connect(self._style_session)
```

Add these methods next to `_apply_theme`:

```python
    def _style_session(self) -> None:
        """The session button as plain text, or on Results as the mockup's chip.

        Its own sheet rather than the app's: this is the one QToolButton drawn
        this way, and a widget sheet has to be re-applied on a theme change.
        """
        theme = get_theme_manager().get_current_theme()
        if self._results_mode:
            self.session_button.setStyleSheet(
                f"QToolButton {{ {font_css('caption')}"
                f" font-family: {theme.font_family_mono};"
                f" background-color: {theme.surface_raised};"
                f" border: 1px solid {theme.border}; border-radius: 6px;"
                " padding: 0px 8px; min-height: 20px; max-height: 20px; }"
                " QToolButton::menu-indicator { image: none; }"
            )
        else:
            self.session_button.setStyleSheet(font_css("caption"))
        self.meta_label.setStyleSheet(
            f"{font_css('caption')} color: {theme.text_secondary};"
        )

    def set_results_mode(self, on: bool) -> None:
        """On Results the session is the mockup's chip and its age plain text."""
        self._results_mode = bool(on)
        self._style_session()
        self._refresh()

    def _refresh_meta(self) -> None:
        """`analysed 14:06 · stock file 19 h old`, from the two chips' own text."""
        parts = [t for t in (self.status_chip.text(), self.stock_chip.text()) if t]
        self.meta_label.setText(" · ".join(t[0].lower() + t[1:] for t in parts))
        has_session = self._state in (BarState.SESSION, BarState.RUNNING)
        self.meta_label.setVisible(self._results_mode and has_session and bool(parts))
```

`set_status` and `set_stock_age` become:

```python
    def set_status(self, role: str, text: str) -> None:
        self.status_chip.set_status(role, text, get_theme_manager().get_current_theme())
        self.status_chip.setVisible(bool(text) and not self._results_mode)
        self._refresh_meta()

    def set_stock_age(self, text: str) -> None:
        self.stock_chip.set_status(
            "text_secondary", text, get_theme_manager().get_current_theme()
        )
        self.stock_chip.setVisible(bool(text) and not self._results_mode)
        self._refresh_meta()
```

In `_refresh`, the three lines that show the folder button and the two chips become:

```python
        chips = has_session and not self._results_mode
        self.open_folder_button.setVisible(chips)
        self.status_chip.setVisible(chips and bool(self.status_chip.text()))
        self.stock_chip.setVisible(chips and bool(self.stock_chip.text()))
        self._refresh_meta()
```

Update the module docstring's second sentence to mention it: after "...marks a button primary." add "On
Results the session is drawn as a chip (set_results_mode)."

- [ ] **Step 5: The wiring and the menu (`gui/ui_manager.py`)**

`_SCREEN_ACTIONS` loses its entry for Results, and the comment above it gains one line:

```python
# Results (1) has no bar action since phase 2: re-running the analysis lives
# in its screen menu, as the mockup has it.
_SCREEN_ACTIONS = {
    0: ("run_analysis_button", True, "primary"),
}
```

In `_create_tabs`, next to the `_apply_page_inset` connection from Task 4, add:

```python
        self.mw.main_tabs.currentChanged.connect(
            lambda index: self.mw.command_bar.set_results_mode(index == 1)
        )
```

Add `from PySide6.QtGui import QGuiApplication` to the module's imports (merge it into an existing
`PySide6.QtGui` import if there is one) and `summary_text` to the `gui.orders_view` import (add the import if
the module has none).

In `_create_results_overflow`, before `self.mw.add_product_button_tab2 = action(`, add:

```python
        # What the mockup moves out of the command bar on Results (phase 2
        # spec section 6.2). Their enabled state is read when the menu opens.
        self.mw.rerun_analysis_action = action(
            "Run analysis again",
            lambda: self.mw.run_analysis_button.click(),
            "Run the analysis again on this session's files",
        )
        self.mw.open_folder_action = action(
            "Open session folder",
            self._open_session_folder,
            "Open this session's folder",
        )
        self.mw.copy_summary_action = action(
            "Copy summary",
            self._copy_results_summary,
            "Copy the session's numbers as one line",
        )
        menu.addSeparator()
        menu.aboutToShow.connect(self._refresh_results_menu)
```

Update that method's docstring: "Configure Columns returns with the column manager (Bundle 13)." is followed
by "Run analysis again, Open session folder and Copy summary came from the command bar in phase 2."

Add the two methods below it:

```python
    def _refresh_results_menu(self) -> None:
        """Enable what can run now. Called as the menu opens."""
        self.mw.rerun_analysis_action.setEnabled(self.mw.run_analysis_button.isEnabled())
        self.mw.open_folder_action.setEnabled(
            bool(getattr(self.mw, "session_path", None))
        )
        self.mw.copy_summary_action.setEnabled(bool(self.mw.results_bridge.summary))

    def _copy_results_summary(self) -> None:
        text = summary_text(self.mw.results_bridge.summary)
        if not text:
            return
        QGuiApplication.clipboard().setText(text)
        self.mw.results_bridge.raise_toast("Summary copied")
```

- [ ] **Step 6: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_commandbar_states.py tests/test_components_commandbar.py tests/test_results_summary.py tests/test_results_screen.py tests/test_screen_primary_actions.py tests/test_shell.py tests/test_first_run.py tests/test_components_render_roles.py`
Expected: PASS. `test_resuming_a_past_session_reaches_the_session_state` in `tests/test_shell.py` asserts
`open_folder_button.isVisible()`, which holds while the window is on Setup. If it fails because loading a
session moved the window to Results, the bar is right and the test's assumption is stale: add
`main_window.main_tabs.setCurrentIndex(0)` and `QApplication.processEvents()` before that assertion, with the
comment "the folder button lives in the bar on every screen but Results (phase 2 spec section 6.1)".

- [ ] **Step 7: Commit**

`/usr/bin/git add gui/components/commandbar.py gui/ui_manager.py gui/orders_view.py tests/test_commandbar_states.py tests/test_results_summary.py tests/test_results_screen.py tests/test_screen_primary_actions.py tests/test_shell.py`,
message "Shell: the session chip on Results, and a screen menu that takes over the bar's actions".

---

### Task 13: Docs, the visual check, the gate

**Files:**
- Modify: `CONTEXT.md`, `docs/adr/0016-the-web-tier-grows-screen-by-screen.md`,
  `docs/adr/0007-the-results-screen-toasts-inside-the-document.md`, `docs/design/ui-refresh/roadmap.md`,
  `README.md`
- Create: `docs/design/ui-refresh/renders/phase2/light-default.png`, `dark-three-selected.png`,
  `light-kit-sheet.png`

**Interfaces:**
- Consumes: everything above. Produces the PR.

- [ ] **Step 1: `CONTEXT.md`**

Make these edits. Keep the file's 80-column wrap.

- **Web tier**: replace its second and third sentences ("Analysis Results only. See ADR 0001, which also
  records the deletion of Info › Statistics that leaves it the sole occupant.") with: "Analysis Results
  today; ADR 0016 lets each other screen move in its own task. See ADR 0001 for why Results moved first."
- **Results document**: "the web tier's one page: KPI strip, filter bar and order table, with a slot beside
  the table for the detail pane." becomes "the Results page: two cards on the sunken plane, the KPI strip
  and one split card that holds the order table and, beside it, the detail pane."
- After **Web asset**, add:
  "**Web kit** — `gui/web/kit.css`, the stylesheet every web page links first: cards, buttons, badges, inputs,
  menus, the toast, the banner, the state panel, the page header. Components only, never a page's layout. Its
  sheet, `tests/web/kit_sheet.html`, shows one of each."
- **Detail pane**: add the sentence "It collapses to a rail that still says what it is."
- **Column manager**: replace the entry with "a popover under the Columns button. It chooses and orders the
  table's columns and is saved per client. The pane stays visible behind it."
- After **Chip**, add:
  "**Badge** — the web tier's status pill: a tinted fill, no outline and no mark. Authorship, which the mark
  carries on a chip, is said in the pane's verdict instead. Not a **chip**, which stays the Qt tier's
  silhouette."
- **Selection ring**: add the sentence "The Qt tier's only: on the web tier the **cursor** row wears a bar on
  its left edge."
- Before **State panel**, add:
  "**Cursor** — the one order the detail pane shows, moved by a click or ↑ ↓. Not a selection: a bulk action
  never reaches it.

  **Checked orders** — the set a bulk action reaches, built with the row checkboxes, Ctrl-click, Shift-click
  and Ctrl+A. It is what Python hears as the selection. A filter that hides an order unchecks it."
- **Selection bar**: "the 44px bar that exists only while orders are selected. It counts the selection in two
  units, orders and units, and holds every verb that acts on more than one order. It takes its height from the
  table rather than floating over rows." becomes "the bar that exists only while orders are checked. It takes
  the table header's place, counts the checked orders and holds every verb that acts on more than one. It
  never floats over rows." Keep the entry's last sentence about the Session Browser.
- **Bulk popover**: its last two sentences ("It replaces a chain of blocking dialogs. It never confirms,
  because the verb states the count and Undo is real; the three verbs that destroy data raise a **confirm** on
  top of it instead.") become "It replaces a chain of blocking dialogs. For a verb that removes orders or
  lines it lists what will change, and its own verb is the confirmation: no dialog follows, because Undo is
  real."

- [ ] **Step 2: The two ADRs**

In `docs/adr/0016-the-web-tier-grows-screen-by-screen.md`, under Consequences, replace the bullet that starts
"`shared/style_lint.py` (owned by packing-tool) still bans `box-shadow`." with:

```markdown
- `shared/style_lint.py` allows `box-shadow` in a web asset since phase 2 (2026-10-01), and only when its
  whole value is `var(--card-shadow)`, `var(--overlay-shadow)` or `none`. Any other shadow is still a
  finding, so a shadow is always one of the theme's two tokens. The lint is shared, so the allowance reaches
  Packing Tool at its next sync; its own ADR 0001 still bans shadows until a Packing Tool spec decides
  otherwise.
```

In `docs/adr/0007-the-results-screen-toasts-inside-the-document.md`, add at the end of the file:

```markdown
## Amendment, 2026-10-01 (UI refresh phase 2)

The web toast now takes its look from the web kit (`gui/web/kit.css`): the inverse plane, a shadow, and a
dismiss button. "Two implementations, one appearance" no longer holds. The Qt toast in
`shared/components/toast.py` keeps its look until the screens that raise it move to the web tier
(ADR 0016), and then it is deleted rather than restyled.
```

- [ ] **Step 3: `roadmap.md` and `README.md`**

In `docs/design/ui-refresh/roadmap.md`, the heading `### 2. Results to mockup, and the web kit` becomes
`### 2. Results to mockup, and the web kit (built in run 38)`, and directly under it add:

```markdown
Spec: `docs/superpowers/specs/2026-10-01-ui-refresh-phase2-results-kit-design.md`.
Plan: `docs/superpowers/plans/2026-10-01-ui-refresh-phase2-results-kit.md`.

Built as listed below, with these differences. Two more tokens, `critical_fill` and `on_critical`, for the
popover's confirm button. The kit has a sheet, `tests/web/kit_sheet.html`, where the components no screen
draws yet (segmented control, banner, page header) are tested and rendered. Held is not a status: the owner
kept two. The column manager is the mockup's popover holding the full manager.
```

Under `## After the roadmap`, add:

```markdown
- Re-evaluate an order's status when its short SKU is removed. The mockup's popover promises "becomes
  Fulfillable"; today the order stays Blocked until someone marks it fulfillable, and the popover says so.
  Stock-ledger work with its own spec.
- `gui/web/kit.css` moves to `shared/` when Packing Tool adopts it.
```

In `README.md`, the line "- `gui/`: Qt UI; `gui/web/` is the results document (QtWebEngine)" becomes
"- `gui/`: Qt UI; `gui/web/` holds the web pages and their shared kit (QtWebEngine)".

- [ ] **Step 4: The visual check (required by CLAUDE.md)**

Write this throwaway script under your job's tmp dir as `render_phase2.py`. It is not committed.

```python
"""Throwaway: render the Results page's mockup states to PNG."""

import sys
from pathlib import Path

import pandas as pd
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication

from gui.results_bridge import mount_results_page
from gui.theme_manager import get_theme_manager

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
NAMES = ["Maria Petrova", "Georgi Ivanov", "Elena Dimitrova", "Nikolai Stoyanov", "Ana Koleva"]
BLOCKED = {0, 2, 8, 12, 14, 20, 24, 26, 30, 36}


def orders(priced):
    rows = []
    for i in range(40):
        qty = [1, 2, 3][i % 3]
        blocked = i in BLOCKED
        note = f"Cannot fulfill: SRM-30ML: Insufficient stock (need {qty}, have 0)" if blocked else ""
        for sku in ("CRM-50ML", "SRM-30ML"):
            row = {
                "Order_Number": str(1000 + i),
                "Order_Fulfillment_Status": "Not Fulfillable" if blocked else "Fulfillable",
                "Shipping_Provider": "DHL" if blocked else ["DHL", "DPD", "Speedy"][i % 3],
                "Customer": NAMES[i % 5],
                "Destination_Country": "BG",
                "Created_At": f"2026-09-30 {i % 12:02d}:15:00 +0300",
                "SKU": sku,
                "Product_Name": "Day cream 50 ml" if sku.startswith("CRM") else "Serum 30 ml",
                "Quantity": qty,
                "Final_Stock": 12 + i % 9,
                "Internal_Tags": "[]",
                "System_note": note,
                "Has_SKU": True,
                "Stock_Alert": "",
            }
            if priced:
                row["Total_Price"] = 26.4 * qty
            rows.append(row)
    return pd.DataFrame(rows)


def pump(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


RESET = (
    "closeBulkPopover(); closeSelectionMenu(); dismissToast();"
    " if (state.columnsOpen) closeColumnsPanel(false);"
    " state.selected = new Set(); state.cursorKey = null; state.paneHidden = false;"
    " clearFilters();"
)
THREE = "state.selected = new Set(['1000', '1002', '1008']); state.cursorKey = '1002'; render();"
STATES = {
    "default": "",
    "one-selected": "state.cursorKey = '1002'; render();",
    "three-selected": THREE,
    "bulk-popover": THREE
    + " document.getElementById('selection-more').click();"
    " document.getElementById('more-remove-sku').click();"
    " document.querySelector(\"[data-tag='CRM-50ML']\").click();",
    "no-match": "toggleChip({kind: 'status', value: 'blocked', label: 'Blocked'});"
    " toggleChip({kind: 'courier', value: 'DPD', label: 'Courier: DPD'}); render();",
    "toast": "raiseToast('3 orders held', true);",
    "pane-collapsed": "hidePane();",
    "columns": "openColumnsPanel();",
}

app = QApplication.instance() or QApplication(sys.argv)
view = QWebEngineView()
bridge = mount_results_page(view)
view.resize(1166, 720)  # the page a 1366x768 window gives Results
view.show()
pump(1500)
bridge.set_export_enabled(True)
bridge.set_undo_available(True)
for theme in ("light", "dark"):
    get_theme_manager().set_theme(theme)
    bridge.set_orders(orders(priced=False))
    pump(800)
    for name, js in STATES.items():
        view.page().runJavaScript(RESET + js)
        pump(500)
        view.grab().save(str(OUT / f"{theme}-{name}.png"))
    bridge.set_orders(orders(priced=True))
    pump(500)
    view.page().runJavaScript(RESET)
    pump(300)
    view.grab().save(str(OUT / f"{theme}-priced.png"))
get_theme_manager().set_theme("light")
print("saved to", OUT)
```

Run it: `QT_QPA_PLATFORM=offscreen QTWEBENGINE_DISABLE_SANDBOX=1 .venv/bin/python <tmp>/render_phase2.py <tmp>/renders`
(the working directory must be the worktree root so `gui` imports). Read every PNG. Then:

1. Compare `light-default.png` with `docs/design/ui-refresh/mockups/renders/results.png`, element by element:
   the page plane, the KPI card and its dots, the hint cell, the filter bar's order, the header and row
   heights, the badges, the pane's empty state.
2. Open `docs/design/ui-refresh/mockups/results.html` in Chrome if a browser tool is available, or read the
   unpacked template, for the other five states and for dark; compare each with its PNG.
3. Check by eye for what tests cannot: clipped text, a popover cut off by the card's edge, a misaligned
   checkbox tick, a control taller or shorter than its neighbours, an unreadable colour pair in dark, a pane
   footer that wraps.
4. Render the kit sheet in both themes with the script from Task 3 Step 7 and compare with
   `mockups/renders/component-sheet.png`.
5. Render the shell: construct `MainWindow` as `tests/test_shell.py`'s `main_window` fixture does (set
   `FULFILLMENT_SERVER_PATH` to a temp dir), `resize(1366, 768)`, call
   `win.command_bar.set_session_text("2026-09-30_1")`, `set_status("text_secondary", "Analysed 14:06")`,
   `set_stock_age("Stock file 19 h old")`, `set_state(BarState.SESSION)`, `win.main_tabs.setCurrentIndex(1)`,
   pump 1500 ms and save `win.grab()`. The web view may come out blank in a window grab offscreen; that is
   expected. Judge the command bar (the chip, the caption beside it, no Run Analysis button) and that the
   page area has no 5px ring.

Fix what is wrong in the CSS or the script, re-run the affected tests, and render again. Every departure you
keep must already be in spec §9; if you find a new one, add it to §9 in the same commit and say so in the PR.

Copy three renders into the repo: `light-default.png`, `dark-three-selected.png`, and the light kit sheet as
`light-kit-sheet.png`, under `docs/design/ui-refresh/renders/phase2/`.

- [ ] **Step 5: The gate**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: only the three pre-existing `tests/test_label_printing.py::TestImageToZpl` failures.

Run: `.venv/bin/ruff check .`
Expected: no findings.

Run: `graphify update .`

- [ ] **Step 6: Commit**

`/usr/bin/git add CONTEXT.md README.md docs/adr docs/design/ui-refresh`, plus `graphify-out` if the update
changed tracked files, message "Docs: the web kit, cursor and checked orders, and the phase 2 renders".

The PR body (Stage C writes it) must say: what reaches Packing Tool at its next sync (seven tokens in
`shared/theme.py`, with no floor moved and `_SURFACE_PLANES` unchanged; the `box-shadow` allowance in
`shared/style_lint.py`, which its own ADR 0001 still forbids it to use); the three pre-existing test
failures; the follow-up in spec §10; and it attaches the three renders.
