# Phase 9 Bundle 11 — The seam (9.11 + 9.12) Implementation Plan

> **For agentic workers:** execute in-session, task by task, with superpowers:executing-plans (the runner forbids subagent fan-out). Steps use checkbox (`- [ ]`) syntax.

**Goal:** Export the theme to CSS custom properties, lint web assets, and build the Qt↔web bridge. The bridge carries a selection from JS into Python, and an order payload plus live theme changes from Python into JS.

**Architecture:** Two pure functions in `shared/` (authored in packing-tool, synced here), one pure function beside the existing order-frame helpers, and one small QObject behind `QWebChannel`. It loads a token-only page shell that 9.13 later fills. Nothing is mounted in the app.

**Tech Stack:** Python 3, PySide6 6.11 (QtWebEngineWidgets, QtWebChannel), pandas, pytest + pytest-qt.

**Spec:** `docs/superpowers/specs/2026-09-11-phase9-bundle11-seam-design.md` — read it first. The protocol rules (§5.1) and the catalogue (§5.2) are binding.

## Global Constraints

- `shared/` is **never edited in this repo**. Edit it in the packing-tool worktree, then sync.
- No hex, no `box-shadow`, gradients, transitions, transforms, `opacity`, or px font sizes in any `.css`/`.html`/`.js` under `gui/`.
- Bridge members called from JS are camelCase. The Python-facing API is snake_case. One member per message, and no behaviour-selecting string arguments.
- The ten frozen aliases are never exported and never read in a web asset.
- Printed-label templates (`shopify_tool/templates/`) are not touched.
- Bridge tests are never marked skip. If Chromium cannot start in CI, report it.
- **VM tooling** (from `state.md`):
  - Use `/usr/bin/git`, one command per call; no `&&` chains, heredocs, or sed with computed args.
  - Write files with the Write/Edit tools.
  - The write hook strips an import that has no usage yet, so add the usage first, then the import.
- Commit messages end with the attribution lines the session provides.

## Locations

| Name | Path |
|---|---|
| **SHOP** (session worktree, branch `worktree-phase9-bundle11-seam`) | `/home/gloopy/Desktop/Projects/shopify-fulfillment-tool/.claude/worktrees/phase9-bundle11-seam` |
| **PT** (packing-tool worktree, branch `phase9-bundle11-seam-shared`, `.venv` already linked) | `/home/gloopy/Desktop/Projects/packing-tool/.claude/worktrees/phase9-bundle11-seam-shared` |

Commands:
- **PT tests:** `env -C <PT> QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q <tests…>`. If a hook refuses the `env -C` form, use `cd <PT> && QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q <tests…>`.
- **SHOP setup (once):** `./scripts/setup_venv.sh`
- **SHOP tests:** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q <tests…>`
- **SHOP lint:** `.venv/bin/ruff check . --exclude shared`
- **PT push:** `PT`'s branch tracks `origin/main`, so always push explicitly: `/usr/bin/git -C <PT> push -u origin phase9-bundle11-seam-shared`. Never a bare `git push` there.

## File map

| File | Repo | Change |
|---|---|---|
| `shared/theme.py` | PT | add `theme_css_vars`, `_css_name`, `_css_value` above `build_stylesheet` |
| `tests/test_theme_css_vars.py` | PT | new |
| `shared/style_lint.py` | PT | web-asset scanning, `banned` + web `alias` rules, `(?<!&)` on `_HEX` |
| `tests/test_style_lint.py` | PT | web-asset unit tests appended |
| `shared/*` | SHOP | synced by `scripts/sync_shared.py`, never hand-edited |
| `tests/test_style_literals_guard.py` | SHOP | one test for the synced web rules |
| `gui/orders_view.py` | SHOP | add `_json_value`, `order_payload` |
| `tests/test_order_payload.py` | SHOP | new |
| `gui/results_bridge.py` | SHOP | new — `ResultsBridge`, `mount_results_page` |
| `gui/web/results.html`, `results.css`, `results.js` | SHOP | new |
| `tests/test_results_bridge.py` | SHOP | new |
| `tests/conftest.py` | SHOP | `QTWEBENGINE_DISABLE_SANDBOX` default |
| `tests/test_webengine_available.py` | SHOP | docstring only |
| `.github/workflows/build_release.yml` | SHOP | apt libs, `--add-data gui/web`, verify loop |

**Test seams:**
- `theme_css_vars` is tested as a pure string: parse it back.
- `find_style_literals` is tested on files in `tmp_path`.
- `order_payload` is tested as a pure function on a hand-built frame.
- The bridge is tested through a real `QWebEngineView`, via `runJavaScript` plus `qtbot`, and never through private state.

---

### Task 1: `theme_css_vars` (packing-tool)

**Files:**
- Modify: `<PT>/shared/theme.py`: add `fields` to the existing `from dataclasses import …` line; insert new code immediately above `def build_stylesheet(`
- Create: `<PT>/tests/test_theme_css_vars.py`

**Interfaces:**
- Produces: `theme_css_vars(theme: ThemeTokens) -> str`. Format: `":root {\n  --a: v;\n  --b: w;\n}\n"`.

- [ ] **Step 1: Write the failing test** — `<PT>/tests/test_theme_css_vars.py`:

```python
"""theme_css_vars: the palette the web tier reads (ADR 0001, roadmap 9.11)."""
import re
from dataclasses import fields

import pytest

from shared.theme import (
    _ALIAS_PAIRS,
    _COLOR_FIELDS,
    DARK_THEME,
    DENSITY_PROFILES,
    LIGHT_THEME,
    TYPE_SCALE,
    get_density,
    set_density,
    theme_css_vars,
)

_DECL = re.compile(r"^  (--[a-z0-9-]+): ([^;{}]+);$")
_ALIASES = {alias for alias, _ in _ALIAS_PAIRS}


def _parse(css: str) -> dict[str, str]:
    lines = css.splitlines()
    assert lines[0] == ":root {" and lines[-1] == "}", css
    decls = {}
    for line in lines[1:-1]:
        m = _DECL.match(line)
        assert m, f"not a single clean declaration: {line!r}"
        assert m.group(1) not in decls, f"emitted twice: {m.group(1)}"
        decls[m.group(1)] = m.group(2)
    return decls


def _name(field_name: str) -> str:
    return "--" + field_name.replace("_", "-")


@pytest.fixture
def density():
    """Set a profile for one test and always put the previous one back."""
    before = get_density()
    yield set_density
    set_density(before)


@pytest.mark.parametrize("theme", [LIGHT_THEME, DARK_THEME], ids=lambda t: t.name)
def test_every_token_round_trips(theme, density):
    density("desk")
    decls = _parse(theme_css_vars(theme))
    for f in fields(theme):
        if f.name == "name" or f.name in _ALIASES:
            continue
        value = getattr(theme, f.name)
        expected = f"{value}px" if isinstance(value, int) else value
        assert decls[_name(f.name)] == expected, f.name


def test_every_colour_field_but_the_aliases_reaches_the_web_tier(density):
    density("desk")
    decls = _parse(theme_css_vars(LIGHT_THEME))
    for token in _COLOR_FIELDS:
        assert (_name(token) in decls) == (token not in _ALIASES), token


def test_one_mono_face_on_both_tiers(density):
    density("desk")
    decls = _parse(theme_css_vars(DARK_THEME))
    assert decls["--font-family-mono"] == LIGHT_THEME.font_family_mono == "Consolas, monospace"


@pytest.mark.parametrize("profile_name", ["desk", "floor"])
def test_type_and_density_are_the_active_profile(profile_name, density):
    density(profile_name)
    decls = _parse(theme_css_vars(LIGHT_THEME))
    profile = DENSITY_PROFILES[profile_name]
    assert decls["--control-height"] == f"{profile.control_height}px"
    assert decls["--row-height"] == f"{profile.row_height}px"
    assert decls["--padding-v"] == f"{profile.padding_v}px"
    assert decls["--padding-h"] == f"{profile.padding_h}px"
    assert "--type-overrides" not in decls
    for role, style in TYPE_SCALE.items():
        size = profile.type_overrides.get(role, style.size_pt)
        assert decls[_name(f"type_{role}_size")] == f"{size}pt", role
        assert decls[_name(f"type_{role}_weight")] == ("700" if style.bold else "400"), role
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `env -C <PT> QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q tests/test_theme_css_vars.py`
Expected: collection error, `ImportError: cannot import name 'theme_css_vars'`.

- [ ] **Step 3: Implement.** Insert this directly above `def build_stylesheet(` in `<PT>/shared/theme.py`. Then add `fields` to the `from dataclasses import …` line; add the import *after* the code exists, or the write hook strips it.

```python
def _css_name(field_name: str) -> str:
    return "--" + field_name.replace("_", "-")


def _css_value(value) -> str:
    return f"{value}px" if isinstance(value, int) else str(value)


def theme_css_vars(theme: ThemeTokens) -> str:
    """The theme as CSS custom properties, for the web tier (ADR 0001).

    Every ThemeTokens field under its own name with underscores turned into
    hyphens -- mechanically, so a token added to the dataclass reaches the web
    tier with no second registration site, the same reasoning that derives
    _SURFACE_PLANES. The aliases stay behind: a web asset has no legacy call
    sites to protect, so `--accent-green` would be new debt.

    Ints are px and type sizes stay pt. The type scale and the density
    fields are the *active* profile's, so a caller re-runs this on every
    theme_notifier change, which a density switch also announces.
    """
    aliases = {alias for alias, _ in _ALIAS_PAIRS}
    decls = {
        _css_name(f.name): _css_value(getattr(theme, f.name))
        for f in fields(theme)
        if f.name != "name" and f.name not in aliases
    }
    # Raised, not asserted: `python -O` strips assert statements.
    missing = {_css_name(c) for c in _COLOR_FIELDS if c not in aliases} - decls.keys()
    if missing:
        raise AssertionError(f"theme_css_vars did not emit {sorted(missing)}")

    for role in TYPE_SCALE:
        style = type_style(role)
        decls[_css_name(f"type_{role}_size")] = f"{style.size_pt}pt"
        decls[_css_name(f"type_{role}_weight")] = "700" if style.bold else "400"

    # control_content_height is a property compensating for Qt's box model;
    # fields() skips it, and the web tier's border-box does not need it.
    profile = get_density_profile()
    for f in fields(profile):
        if f.name != "type_overrides":
            decls[_css_name(f.name)] = _css_value(getattr(profile, f.name))

    body = "\n".join(f"  {name}: {value};" for name, value in decls.items())
    return f":root {{\n{body}\n}}\n"
```

- [ ] **Step 4: Run it and confirm it passes**

Run the Step 2 command. Expected: all pass (7 tests).
Then run the whole PT suite: `env -C <PT> QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q`. Expected: no new failures.

- [ ] **Step 5: Commit (PT)**

`/usr/bin/git -C <PT> add shared/theme.py tests/test_theme_css_vars.py`
`/usr/bin/git -C <PT> commit -m "shared: theme_css_vars exports the palette to the web tier (Phase 9 Bundle 11, 9.11)"`

---

### Task 2: web assets in `style_lint` (packing-tool)

**Files:**
- Modify: `<PT>/shared/style_lint.py`
- Modify: `<PT>/tests/test_style_lint.py` (append)

**Interfaces:**
- Produces: `find_style_literals(paths)` now also scans `.css`, `.html` and `.js`. Finding kinds on web assets are `hex`, `css-name`, `css-func`, `px-font`, `banned` and `alias`. The finding format is unchanged: `"{path}:{line}: {kind}: {text}"`.

- [ ] **Step 1: Write the failing tests.** Append to `<PT>/tests/test_style_lint.py`:

```python
# --- Web assets (ADR 0001, roadmap 9.11) ------------------------------------


def _scan_asset(tmp_path: Path, name: str, source: str) -> list[str]:
    f = tmp_path / name
    f.write_text(textwrap.dedent(source), encoding="utf-8")
    return [s.removeprefix(f"{f}:") for s in find_style_literals([f])]


def test_a_hex_in_a_stylesheet_is_flagged_on_its_own_line(tmp_path):
    out = _scan_asset(tmp_path, "page.css", """
        body { background: var(--surface); }
        .x { color: #ff0000; }
    """)
    assert out == ["3: hex: #ff0000"]


def test_a_box_shadow_in_a_stylesheet_is_flagged(tmp_path):
    out = _scan_asset(tmp_path, "page.css", """
        .card { box-shadow: 0 1px 2px var(--border); }
    """)
    assert out == ["2: banned: box-shadow"]


@pytest.mark.parametrize("declaration, banned", [
    ("transition: color 0s;", "transition"),
    ("transition-duration: 1s;", "transition-duration"),
    ("transform: none;", "transform"),
    ("opacity: 0.5;", "opacity"),
    ("background-image: linear-gradient(var(--a), var(--b));", "linear-gradient"),
    ("background-image: repeating-radial-gradient(var(--a), var(--b));",
     "repeating-radial-gradient"),
    ("background-image: conic-gradient(var(--a), var(--b));", "conic-gradient"),
])
def test_every_banned_property_is_flagged(tmp_path, declaration, banned):
    out = _scan_asset(tmp_path, "page.css", f".x {{ {declaration} }}\n")
    assert out == [f"1: banned: {banned}"]


def test_a_longer_property_merely_ending_in_a_banned_name_is_clean(tmp_path):
    assert _scan_asset(tmp_path, "page.css", """
        .x { text-transform: uppercase; fill-opacity: 1; }
    """) == []


def test_a_pixel_font_size_in_a_stylesheet_is_flagged(tmp_path):
    out = _scan_asset(tmp_path, "page.css", "body { font-size: 13px; }\n")
    assert out == ["1: px-font: font-size: 13px"]


def test_comments_are_ignored_and_lines_still_count(tmp_path):
    out = _scan_asset(tmp_path, "page.css", """
        /* legacy #ffffff
           and a box-shadow: 0 0 1px */
        .x { color: #000; }
    """)
    assert out == ["4: hex: #000"]


def test_html_style_blocks_are_scanned_but_comments_and_entities_are_not(tmp_path):
    out = _scan_asset(tmp_path, "page.html", """
        <!-- #ffffff -->
        <p>&#169; 2026</p>
        <style>.x { color: #abcdef; }</style>
    """)
    assert out == ["4: hex: #abcdef"]


def test_a_script_is_scanned_without_mistaking_a_url_for_a_comment(tmp_path):
    out = _scan_asset(tmp_path, "page.js", """
        // #ffffff is only a comment
        const url = "qrc:///qtwebchannel/qwebchannel.js"; const c = "#abcdef";
        el.style.boxShadow = "none";
    """)
    assert out == ["3: hex: #abcdef", "4: banned: boxShadow"]


def test_a_var_reading_a_frozen_alias_is_flagged(tmp_path):
    # Aliases without a colour word on purpose: var(--accent-blue) is ALSO a
    # css-name finding ("blue"), which is correct but would muddy this test.
    out = _scan_asset(tmp_path, "page.css", """
        .a { color: var(--active-border); }
        .b { background: var(--background-elevated, var(--surface)); }
        .c { background: var(--surface); }
    """)
    assert out == ["2: alias: active-border", "3: alias: background-elevated"]


def test_the_allow_marker_works_in_a_web_asset(tmp_path):
    assert _scan_asset(tmp_path, "page.css", """
        .x { color: #fff; } /* style-lint: allow */
    """) == []


def test_a_directory_walk_picks_up_web_assets_and_nothing_else(tmp_path):
    (tmp_path / "clean.py").write_text('S = "color: palette(text);"\n', encoding="utf-8")
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "page.css").write_text(".x { color: #fff; }\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("color: #fff;\n", encoding="utf-8")
    out = find_style_literals([tmp_path])
    assert len(out) == 1 and out[0].startswith(str(tmp_path / "web" / "page.css"))
```

If `pytest` is not already imported at the top of that file, add `import pytest`, after the usage exists.

- [ ] **Step 2: Run them and confirm they fail**

Run: `env -C <PT> QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q tests/test_style_lint.py`
Expected: the new web tests FAIL (web assets are never scanned yet); the existing tests PASS.

- [ ] **Step 3: Implement** in `<PT>/shared/style_lint.py`.

(a) Replace the `_HEX` line:

```python
# A 6- or 3-digit hex, refusing to match the front of a longer digit run so
# order numbers ("#1001") and PR references stay clean, and refusing a numeric
# character reference ("&#169;") in a web page.
_HEX = re.compile(r"(?<!&)#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})(?![0-9a-fA-F])")
```

(b) Add after `FROZEN_ALIASES`:

```python
WEB_SUFFIXES = (".css", ".html", ".js")

# Allowed by CSS, banned in a web asset: each is something the Qt tier cannot
# draw, so each is a visible seam (ADR 0001). The lookbehind keeps
# text-transform and fill-opacity clean. `opacity` is banned outright: QSS has
# no per-element opacity, so there is no container it could match.
_BANNED = re.compile(
    r"(?<![-\w])(box-shadow|transition(?:-[a-z-]+)?|transform|opacity)\s*:"
    r"|(?<![-\w])((?:repeating-)?(?:linear|radial|conic)-gradient)\s*\("
    r"|\.style\.(boxShadow|transition\w*|transform|opacity)\b"
)

# The aliases are never exported to the web tier, so var(--accent-blue)
# resolves to nothing and paints transparent without a sound.
_WEB_ALIAS = re.compile(
    r"var\(\s*--("
    + "|".join(sorted((a.replace("_", "-") for a in FROZEN_ALIASES), key=len, reverse=True))
    + r")\s*[,)]"
)

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/|<!--.*?-->", re.S)
# Only at line start or after whitespace, so "qrc:///..." is not a comment.
_LINE_COMMENT = re.compile(r"(?m)(?:^|(?<=\s))//.*$")


def _blank(match: re.Match) -> str:
    """The comment's text as spaces, newlines kept, so line numbers hold."""
    return re.sub(r"[^\n]", " ", match.group(0))
```

(c) Add after `_scan_file` (and put two blank lines between `_scan_file` and `find_style_literals`):

```python
def _scan_web_asset(path: Path) -> list[str]:
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    code = _BLOCK_COMMENT.sub(_blank, raw)
    if path.suffix != ".css":
        code = _LINE_COMMENT.sub(_blank, code)

    found: list[tuple[int, str, str]] = []
    for kind, rx in (("hex", _HEX), ("css-name", _CSS_NAME), ("css-func", _CSS_FUNC),
                     ("px-font", _PX_FONT), ("banned", _BANNED), ("alias", _WEB_ALIAS)):
        for m in rx.finditer(code):
            ln = code.count("\n", 0, m.start()) + 1
            # The marker usually sits in a comment, so read it from the raw line.
            if ALLOW_MARKER in lines[ln - 1]:
                continue
            found.append((ln, kind, m.group(m.lastindex) if m.lastindex else m.group(0)))

    return [f"{path}:{ln}: {kind}: {text}" for ln, kind, text in sorted(found)]
```

(d) Replace `find_style_literals` with:

```python
def find_style_literals(paths: Iterable[Path]) -> list[str]:
    """Every offending site under `paths`, sorted, one string per finding.

    A path may be a file or a directory; directories are walked recursively
    so a package added later cannot escape the guard silently. Python source
    and web assets (.css, .html, .js) are both scanned.
    """
    scanned = (".py", *WEB_SUFFIXES)
    files: list[Path] = []
    for p in (Path(x) for x in paths):
        if p.is_dir():
            files.extend(q for q in p.rglob("*") if q.suffix in scanned and q.is_file())
        else:
            files.append(p)
    out: list[str] = []
    for f in sorted(set(files)):
        out.extend(_scan_web_asset(f) if f.suffix in WEB_SUFFIXES else _scan_file(f))
    return out
```

(e) In the module docstring, add this paragraph after the "Scope note" paragraph:

```
Web assets (.css, .html, .js -- ADR 0001) are scanned as text with comments
blanked out. They get the same four colour and size rules plus two of their
own: `banned` (box-shadow, gradients, transitions, transforms, opacity --
each a seam the Qt tier cannot match) and `alias` (a var() reading a frozen
alias, which the web tier never receives).
```

- [ ] **Step 4: Run tests and confirm they pass**

Run: `env -C <PT> QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q tests/test_style_lint.py tests/test_style_literals_guard.py`
Expected: all pass.

If a test's expected string differs from the output only in the reported text of a match (e.g. the `px-font` text), compare it with how the existing `.py` `px-font` test reports and align the **test** with that established format. Do not change the regexes to fit.

Then run the full PT suite. Expected: no new failures.

- [ ] **Step 5: Commit and push (PT)**

`/usr/bin/git -C <PT> add shared/style_lint.py tests/test_style_lint.py`
`/usr/bin/git -C <PT> commit -m "shared: style_lint scans web assets for hex, banned properties and alias reads (Phase 9 Bundle 11, 9.11)"`
`/usr/bin/git -C <PT> push -u origin phase9-bundle11-seam-shared`

---

### Task 3: Sync `shared/` into shopify, and guard the synced web rules

**Files:**
- Modify (by script only): `<SHOP>/shared/theme.py`, `<SHOP>/shared/style_lint.py`
- Modify: `<SHOP>/tests/test_style_literals_guard.py`

- [ ] **Step 1: Run `./scripts/setup_venv.sh`** in SHOP, if `.venv` is not there yet.

- [ ] **Step 2: Write the failing guard test.** Append to `<SHOP>/tests/test_style_literals_guard.py`:

```python
def test_the_web_asset_rules_survived_the_shared_sync(tmp_path):
    """The same reasoning as above, for the rules ADR 0001 added: one planted
    offender per web rule, so a half-synced style_lint cannot pass quietly."""
    offender = tmp_path / "offender.css"
    offender.write_text(
        ".a { color: #ff0000; box-shadow: 0 0 1px; }\n"
        ".b { color: var(--accent-blue); font-size: 12px; }\n"
        ".c { background: linear-gradient(red, blue); }\n",
        encoding="utf-8",
    )
    kinds = {f.split(": ")[1] for f in find_style_literals([offender])}
    assert kinds == {"hex", "banned", "alias", "px-font", "css-name"}, kinds
```

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_style_literals_guard.py`
Expected: the new test FAILS (the old `shared/` scans no `.css`).

- [ ] **Step 3: Sync**

Run: `.venv/bin/python scripts/sync_shared.py /home/gloopy/Desktop/Projects/packing-tool/.claude/worktrees/phase9-bundle11-seam-shared`
Then check `/usr/bin/git status --short shared/`. Expected: only `shared/theme.py` and `shared/style_lint.py` changed. If other `shared/` files changed, PT's `origin/main` is ahead of this repo's `shared/`. That is legitimate: keep them, and say so in the commit body.

- [ ] **Step 4: Run the guard and the theme tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_style_literals_guard.py tests/test_type_scale.py`
Expected: all pass. `gui/` has no web assets yet, so the repo-wide guard stays clean.

- [ ] **Step 5: Commit (SHOP)**

`/usr/bin/git add shared/ tests/test_style_literals_guard.py`
`/usr/bin/git commit -m "Sync shared/: theme_css_vars and web-asset lint rules (Phase 9 Bundle 11)"`

---

### Task 4: `order_payload`

**Files:**
- Modify: `<SHOP>/gui/orders_view.py`: add `import math` and `import datetime` at the top (after the usage exists); add `_json_value` and `order_payload` at the end of the module
- Create: `<SHOP>/tests/test_order_payload.py`

**Interfaces:**
- Consumes: `orders_frame(df)`, `classify_columns(df)`, `ORDER_KEY`, `SEARCH_COLUMN`, all already in `gui/orders_view.py`
- Produces: `order_payload(df: pd.DataFrame) -> list[dict]`. Each dict holds the order-level columns plus `"lines": list[dict]`.

- [ ] **Step 1: Write the failing test** — `<SHOP>/tests/test_order_payload.py`:

```python
"""order_payload: the order frame as the web tier receives it (roadmap 9.12)."""
import json

import numpy as np
import pandas as pd

from gui.orders_view import SEARCH_COLUMN, order_payload


def _analysis_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "Order_Number": ["#1001", "#1002", "#1002", "#1003", "#1003", "#1003"],
        "Order_Fulfillment_Status": ["Fulfillable", "Not Fulfillable", "Not Fulfillable",
                                     "Fulfillable", "Fulfillable", "Fulfillable"],
        "Shipping_Provider": ["DHL"] * 6,
        "Notes": [np.nan, "call first", "call first", np.nan, np.nan, np.nan],
        "Total_Price": [10.5, 20.0, 20.0, np.nan, np.nan, np.nan],
        "SKU": ["A", "TS-4409-B", "C", "D", "E", "F"],
        "Quantity": np.array([1, 6, 2, 1, 1, 1], dtype="int64"),
        "Stock": [5.0, 4.0, np.inf, 1.0, 1.0, 1.0],
        "System_note": ["", "Cannot fulfill: TS-4409-B short",
                        "Cannot fulfill: TS-4409-B short", "", "", ""],
    })


def test_one_entry_per_order_in_frame_order():
    payload = order_payload(_analysis_frame())
    assert [o["Order_Number"] for o in payload] == ["#1001", "#1002", "#1003"]


def test_lines_are_nested_with_only_the_line_level_columns():
    order = order_payload(_analysis_frame())[1]
    assert order["lines"] == [
        {"SKU": "TS-4409-B", "Quantity": 6, "Stock": 4.0,
         "System_note": "Cannot fulfill: TS-4409-B short"},
        {"SKU": "C", "Quantity": 2, "Stock": None,
         "System_note": "Cannot fulfill: TS-4409-B short"},
    ]


def test_order_level_columns_appear_once_with_the_derived_ones():
    order = order_payload(_analysis_frame())[1]
    assert order["Shipping_Provider"] == "DHL"
    assert order["Items"] == 2 and type(order["Items"]) is int
    assert order["Blocker"] == "TS-4409-B short"
    assert "SKU" not in order and SEARCH_COLUMN not in order


def test_every_value_is_json_native():
    payload = order_payload(_analysis_frame())
    json.dumps(payload, allow_nan=False)   # raises on NaN, inf or numpy types
    assert payload[0]["Notes"] is None
    assert payload[2]["Total_Price"] is None
    assert type(payload[0]["lines"][0]["Quantity"]) is int


def test_nothing_to_send_is_an_empty_list():
    assert order_payload(None) == []
    assert order_payload(pd.DataFrame()) == []
    assert order_payload(pd.DataFrame({"SKU": ["A"]})) == []
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_order_payload.py`
Expected: `ImportError: cannot import name 'order_payload'`.

- [ ] **Step 3: Implement.** Append to `<SHOP>/gui/orders_view.py`, then add `import datetime` and `import math` above `import pandas as pd`:

```python
def _json_value(value):
    """One cell as the web tier can receive it: JSON-native, never NaN."""
    if isinstance(value, (list, tuple)):
        return [_json_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _json_value(v) for k, v in value.items()}
    if value is None or value is pd.NaT or value is pd.NA:
        return None
    if isinstance(value, float):          # numpy.float64 included
        return float(value) if math.isfinite(value) else None
    if isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, (datetime.date, datetime.datetime)):   # pd.Timestamp included
        return value.isoformat()
    if hasattr(value, "item"):            # numpy int, bool, ...
        return _json_value(value.item())
    return str(value)


def order_payload(df: pd.DataFrame) -> list[dict]:
    """The order frame with each order's lines nested -- what the bridge sends.

    One entry per order in the frame's row order: the order-level columns once,
    under their own names, and ``lines``, the line-level columns one dict per
    line. SEARCH_COLUMN stays behind -- it is the Qt filter proxy's helper, and
    the web tier filters on its own terms (9.13).
    """
    orders = orders_frame(df)
    if orders.empty:
        return []
    _, line_level = classify_columns(df)
    lines = {
        key: [dict(zip(line_level, map(_json_value, row)))
              for row in group[line_level].itertuples(index=False, name=None)]
        for key, group in df.groupby(ORDER_KEY, sort=False)
    }
    columns = [ORDER_KEY] + [c for c in orders.columns if c not in (ORDER_KEY, SEARCH_COLUMN)]
    payload = []
    for row in orders[columns].itertuples(index=False, name=None):
        entry = dict(zip(columns, map(_json_value, row)))
        entry["lines"] = lines.get(row[0], [])
        payload.append(entry)
    return payload
```

- [ ] **Step 4: Run tests and confirm they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_order_payload.py tests/test_orders_view.py`
Expected: all pass. If `tests/test_orders_view.py` does not exist, drop it from the command.

If `test_lines_are_nested…` fails because `classify_columns` puts a column in the other group, read `_order_level_extras` (`gui/orders_view.py:60`) and fix the **test frame**. That classification is the existing, shipped contract.

- [ ] **Step 5: Commit**

`/usr/bin/git add gui/orders_view.py tests/test_order_payload.py`
`/usr/bin/git commit -m "order_payload: the order frame with lines nested, JSON-native (Phase 9 Bundle 11, 9.12)"`

---

### Task 5: The bridge, the page shell, and the round-trip tests

**Files:**
- Create: `<SHOP>/gui/results_bridge.py`
- Create: `<SHOP>/gui/web/results.html`, `<SHOP>/gui/web/results.css`, `<SHOP>/gui/web/results.js`
- Modify: `<SHOP>/tests/conftest.py`: add `os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")` right after the imports, and `import os` after that line exists
- Create: `<SHOP>/tests/test_results_bridge.py`

**Interfaces:**
- Consumes: `order_payload(df)` (Task 4), `theme_css_vars(theme)` (Task 1, synced), `shared.theme.on_theme_changed(widget, apply)`, `gui.theme_manager.get_theme_manager()`
- Produces:
  - `ResultsBridge(QObject)`, with channel members `orders` (property), `themeCss` (property), `setSelection(list)` (slot), and Python API `selectionChanged: Signal(list)`, `selection() -> list[str]`, `set_orders(df) -> None`, `set_theme_css(css: str) -> None`.
  - `mount_results_page(view: QWebEngineView) -> ResultsBridge`, plus constants `WEB_DIR`, `PAGE`, `THEME_MARKER = "/* theme-vars */"`, `CHANNEL_NAME = "results"`.
  - In JS: `window.resultsBridge`, and `document.documentElement.dataset.bridge === "ready"`.

- [ ] **Step 1: Write the failing tests** — `<SHOP>/tests/test_results_bridge.py`:

```python
"""The bridge, driven through a real Chromium (ADR 0001, roadmap 9.12).

Needs QtWebEngine's runtime libraries; CI installs them in the verify job.
Never mark these skip -- a bridge nobody can run is a bridge nobody guards.
"""
import time

import pandas as pd
import pytest
from PySide6.QtWebEngineWidgets import QWebEngineView

from gui.results_bridge import PAGE, THEME_MARKER, ResultsBridge, mount_results_page
from gui.theme_manager import get_theme_manager
from shared.theme import DARK_THEME, LIGHT_THEME


def _eval(qtbot, view, expr):
    box = []
    view.page().runJavaScript(expr, 0, box.append)
    qtbot.waitUntil(lambda: bool(box), timeout=5000)
    return box[0]


def _until_js(qtbot, view, expr, timeout_s=15):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if _eval(qtbot, view, expr) is True:
            return
        qtbot.wait(50)
    pytest.fail(f"never became true in the page: {expr}")


def _rgb(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    return "rgb({}, {}, {})".format(*(int(h[i:i + 2], 16) for i in (0, 2, 4)))


@pytest.fixture
def page(qtbot):
    view = QWebEngineView()
    qtbot.addWidget(view)
    bridge = mount_results_page(view)
    view.resize(1366, 768)
    view.show()
    _until_js(qtbot, view, "document.documentElement.dataset.bridge === 'ready'")
    return view, bridge


def test_the_page_carries_the_theme_marker_exactly_once():
    assert PAGE.read_text(encoding="utf-8").count(THEME_MARKER) == 1


def test_an_unchanged_selection_is_announced_once(qapp):
    bridge = ResultsBridge()
    seen = []
    bridge.selectionChanged.connect(seen.append)
    bridge.setSelection(["#1001"])
    bridge.setSelection(["#1001"])
    assert seen == [["#1001"]]


def test_a_selection_made_in_js_arrives_in_python(qtbot, page):
    view, bridge = page
    with qtbot.waitSignal(bridge.selectionChanged, timeout=5000) as blocker:
        view.page().runJavaScript("window.resultsBridge.setSelection(['#1002'])")
    assert blocker.args == [["#1002"]]
    assert bridge.selection() == ["#1002"]


def test_an_order_payload_arrives_in_js_with_its_lines_nested(qtbot, page):
    view, bridge = page
    bridge.set_orders(pd.DataFrame({
        "Order_Number": ["#1001", "#1002", "#1002"],
        "SKU": ["A", "TS-4409-B", "C"],
        "Quantity": [1, 6, 2],
    }))
    _until_js(qtbot, view, "window.resultsBridge.orders.length === 2")
    assert _eval(qtbot, view, "window.resultsBridge.orders[1].lines[0].SKU") == "TS-4409-B"
    assert _eval(qtbot, view, "window.resultsBridge.orders[1].lines[0].Quantity") == 6


def test_the_first_paint_is_already_themed(qtbot, page):
    view, _ = page
    assert _eval(qtbot, view, "getComputedStyle(document.body).backgroundColor") == _rgb(
        LIGHT_THEME.surface
    )


def test_a_theme_switch_repaints_the_document_without_a_reload(qtbot, page):
    view, _ = page
    _eval(qtbot, view, "window.__loadMarker = 'first load'")
    get_theme_manager().set_theme("dark")   # conftest's reset_theme_and_density restores light
    _until_js(
        qtbot, view,
        f"getComputedStyle(document.body).backgroundColor === '{_rgb(DARK_THEME.surface)}'",
    )
    assert _eval(qtbot, view, "window.__loadMarker") == "first load"


def test_a_density_change_reaches_the_type_scale(qtbot, page):
    view, _ = page
    get_theme_manager().set_density("floor")
    _until_js(
        qtbot, view,
        "getComputedStyle(document.documentElement)"
        ".getPropertyValue('--type-body-size').trim() === '12pt'",
    )
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_results_bridge.py`
Expected: `ModuleNotFoundError: No module named 'gui.results_bridge'`.

- [ ] **Step 3: Add the sandbox default to `tests/conftest.py`.** Directly below the existing import block, add:

```python
# Chromium's sandbox needs unprivileged user namespaces, which the CI runner's
# AppArmor profile refuses. Test-only: the app never sets this.
os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
```

Then add `import os` beside `import gc`.

- [ ] **Step 4: Write the page shell.**

`<SHOP>/gui/web/results.html`:

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Analysis Results</title>
<!-- gui/results_bridge.py writes theme_css_vars() over the marker before the
     page loads, then results.js keeps it current from the bridge. -->
<style id="theme-vars">/* theme-vars */</style>
<link rel="stylesheet" href="results.css">
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<script src="results.js" defer></script>
</head>
<body>
<main id="results"></main>
</body>
</html>
```

`<SHOP>/gui/web/results.css`:

```css
/* The web tier's base. Every value is a token from theme_css_vars(): no hex,
   and nothing the Qt tier cannot draw (ADR 0001, shared/style_lint.py). */

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

html, body { margin: 0; height: 100%; }

body {
  background: var(--surface);
  color: var(--text);
  font-family: var(--font-family);
  font-size: var(--type-body-size);
  font-variant-numeric: tabular-nums;
}
```

`<SHOP>/gui/web/results.js`:

```js
// The page's end of the bridge (gui/results_bridge.py). Bundle 11 keeps the
// theme live and hands the bridge to the page; the results document (9.13)
// is built on top of this.
new QWebChannel(qt.webChannelTransport, function (channel) {
  const bridge = channel.objects.results;
  const themeVars = document.getElementById("theme-vars");
  const applyTheme = function () {
    themeVars.textContent = bridge.themeCss;
  };
  applyTheme();
  bridge.themeCssChanged.connect(applyTheme);
  window.resultsBridge = bridge;
  document.documentElement.dataset.bridge = "ready";
});
```

- [ ] **Step 5: Write the bridge** — `<SHOP>/gui/results_bridge.py`:

```python
"""The bridge: the one object the web tier talks to (ADR 0001, roadmap 9.12).

Every message is its own named member, never a generic send(kind, data).
State Python owns crosses as a notify Property, so a page that connects late
still reads the current value with no handshake; what JS reports crosses as a
Slot. Channel members are camelCase because JS calls them.

The full catalogue, and which bundle adds each member, is section 5.2 of
docs/superpowers/specs/2026-09-11-phase9-bundle11-seam-design.md. Add a
member there before adding it here.
"""
from pathlib import Path

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot
from PySide6.QtWebChannel import QWebChannel

from gui.orders_view import order_payload
from gui.theme_manager import get_theme_manager
from shared.theme import on_theme_changed, theme_css_vars

WEB_DIR = Path(__file__).resolve().parent / "web"
PAGE = WEB_DIR / "results.html"
THEME_MARKER = "/* theme-vars */"
CHANNEL_NAME = "results"


class ResultsBridge(QObject):
    """Bundle 11's three members: orders, themeCss, setSelection."""

    ordersChanged = Signal()
    themeCssChanged = Signal()
    # Python-facing. JS reports a selection through setSelection() and never
    # connects to this, so a selection cannot echo back into the page.
    selectionChanged = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._orders: list = []
        self._theme_css = ""
        self._selection: list[str] = []

    # --- out: Python -> JS -------------------------------------------------

    def _get_orders(self) -> list:
        return self._orders

    orders = Property("QVariantList", _get_orders, notify=ordersChanged)

    def _get_theme_css(self) -> str:
        return self._theme_css

    themeCss = Property(str, _get_theme_css, notify=themeCssChanged)

    # --- in: JS -> Python --------------------------------------------------

    @Slot("QVariantList")
    def setSelection(self, order_numbers) -> None:
        selection = [str(n) for n in order_numbers]
        if selection == self._selection:
            return
        self._selection = selection
        self.selectionChanged.emit(selection)

    # --- Python-facing API -------------------------------------------------

    def selection(self) -> list[str]:
        return list(self._selection)

    def set_orders(self, df) -> None:
        self._orders = order_payload(df)
        self.ordersChanged.emit()

    def set_theme_css(self, css: str) -> None:
        if css == self._theme_css:
            return
        self._theme_css = css
        self.themeCssChanged.emit()


def mount_results_page(view) -> ResultsBridge:
    """Load the results page into `view` and return the bridge it talks to.

    The theme is written into the page before it loads, so the first paint is
    already themed, then pushed through the bridge on every theme or density
    change, so the document repaints without a reload. Both the bridge and
    the channel are parented to `view` and die with it.
    """
    bridge = ResultsBridge(view)
    channel = QWebChannel(view)
    channel.registerObject(CHANNEL_NAME, bridge)
    view.page().setWebChannel(channel)

    def _push_theme(_tokens) -> None:
        # The manager's tokens rather than the argument: only those carry the
        # bundled Inter family the Qt tier renders in.
        bridge.set_theme_css(theme_css_vars(get_theme_manager().get_current_theme()))

    on_theme_changed(view, _push_theme)   # runs once now, then on every change

    html = PAGE.read_text(encoding="utf-8").replace(THEME_MARKER, bridge.themeCss)
    view.setHtml(html, QUrl.fromLocalFile(str(WEB_DIR) + "/"))
    return bridge
```

- [ ] **Step 6: Run the bridge tests, the guard and ruff**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_results_bridge.py tests/test_style_literals_guard.py`
Expected: all pass. The guard now scans `gui/web/` and must stay clean.

Run: `.venv/bin/ruff check . --exclude shared`. Expected: clean.

Troubleshooting, in order, only if needed:
- **(a) `bridge` never becomes `ready`:** read the page's console. Temporarily subclass `QWebEnginePage.javaScriptConsoleMessage` to print. The usual causes are a typo in the channel name, and `results.js` running before `qwebchannel.js`. Keep `defer` on `results.js` only.
- **(b) The process segfaults at exit after these tests:** in the `page` fixture, `yield` instead of `return`, then tear down with `view.page().deleteLater()`, `qtbot.wait(50)`.
- **(c) `Quantity` comes back as `6.0`:** that still equals `6` in Python. Leave it.

- [ ] **Step 7: Run the full suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: no new failures against the last known gate (1562 passed on `main` after Bundle 10), plus this bundle's new tests.

- [ ] **Step 8: Commit**

`/usr/bin/git add gui/results_bridge.py gui/web tests/test_results_bridge.py tests/conftest.py`
`/usr/bin/git commit -m "The bridge: ResultsBridge over QWebChannel and the themed page shell (Phase 9 Bundle 11, 9.12)"`

---

### Task 6: CI libraries, packaging, and the stale docstring

**Files:**
- Modify: `<SHOP>/.github/workflows/build_release.yml`: lines ~32, ~101-106 and ~120
- Modify: `<SHOP>/tests/test_webengine_available.py`: docstring only

- [ ] **Step 1: apt libraries.** Replace this line (~32):

```yaml
          sudo apt-get update && sudo apt-get install -y libegl1 libpango-1.0-0 libcairo2 libgdk-pixbuf-2.0-0
```

with:

```yaml
          # Second half: QtWebEngine's runtime (NSS and X client libs), measured
          # with ldd against libQt6WebEngineCore and QtWebEngineProcess, so
          # tests/test_results_bridge.py drives a real Chromium on every PR.
          sudo apt-get update && sudo apt-get install -y libegl1 libpango-1.0-0 libcairo2 libgdk-pixbuf-2.0-0 libnss3 libnspr4 libxcomposite1 libxdamage1 libxrandr2 libxkbfile1 libxtst6 libxkbcommon0 libgbm1 libasound2t64 libxcb-dri3-0
```

- [ ] **Step 2: Bundle the page.** After `--add-data "shared/assets;shared/assets"` (~103), add the line:

```yaml
          --add-data "gui/web;gui/web"
```

and change the verify loop (~120) to:

```yaml
          foreach ($name in "package.svg", "Inter-Regular.ttf", "QtWebEngineProcess.exe", "results.html") {
```

- [ ] **Step 3: Fix the docstring.** In `tests/test_webengine_available.py`, replace the paragraph starting `find_spec, not import:` with:

```
find_spec, not import: this test guards packaging, not runtime. Runtime is
tests/test_results_bridge.py, which drives a real Chromium -- the CI verify
job installs the NSS and X client libraries that needs.
```

- [ ] **Step 4: Validate the YAML**

Run: `.venv/bin/python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/build_release.yml')); print('ok')"`
Expected: `ok`. If PyYAML is not installed, read the edited region back instead and check indentation matches its neighbours.

- [ ] **Step 5: Commit**

`/usr/bin/git add .github/workflows/build_release.yml tests/test_webengine_available.py`
`/usr/bin/git commit -m "CI installs QtWebEngine's runtime; the build bundles gui/web (Phase 9 Bundle 11)"`

---

### Task 7: Gate, graph, push

- [ ] **Step 1: Run the full suites and lint.**
  - SHOP: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` and `.venv/bin/ruff check . --exclude shared`
  - PT: `env -C <PT> QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q`

  Record the pass counts in `state.md`.
- [ ] **Step 2:** In SHOP, run `graphify update .`.
- [ ] **Step 3:** Push SHOP with `/usr/bin/git push -u origin worktree-phase9-bundle11-seam`. PT was pushed in Task 2; if PT gained commits since, push again with the explicit form.
- [ ] **Step 4: Check the spec's "Bundle done when" list (§1), item by item, against the passing tests:**
  - round-trip → `test_every_token_round_trips`
  - planted hex and box-shadow → `test_a_hex_in_a_stylesheet…`, `test_a_box_shadow…`
  - one mono face → `test_one_mono_face_on_both_tiers`
  - JS→Python selection → `test_a_selection_made_in_js…`
  - Python→JS payload → `test_an_order_payload_arrives…`
  - repaint without reload → `test_a_theme_switch_repaints…`

  Note in `state.md` any that is not green, and do not claim it.

**Stage C needs to know:** two PRs, packing-tool's first. The shopify PR's `shared-sync-check` fails until that one merges, and CI's first run is the first time Chromium starts on the Ubuntu runner.
