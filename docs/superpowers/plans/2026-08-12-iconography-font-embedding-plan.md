# Iconography & Font Embedding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace all 17 OS-native `QStyle.SP_*` stock icons with bundled Lucide SVGs recoloured per theme, bundle Inter as the app font, and give the app a window/taskbar icon it has never had.

**Architecture:** Two new leaf modules under `gui/`. `gui/icons.py` renders bundled Lucide SVGs through `QSvgRenderer` after substituting Lucide's `currentColor` token with the active theme colour, producing multi-resolution `QIcon`s. `gui/fonts.py` registers two bundled Inter TTFs with `QFontDatabase` and is consumed by `ThemeManager.get_current_theme()`, which overrides `ThemeTokens.font_family` via `dataclasses.replace()`. Neither touches `shared/theme.py`.

**Tech Stack:** PySide6 6.11.1 (`QtSvg`, `QtGui`), pytest, Lucide 1.31.0 (ISC), Inter 4.1 (SIL OFL 1.1), PyInstaller `--onedir`.

**Spec:** `docs/superpowers/specs/2026-08-12-iconography-font-embedding-design.md`

## Global Constraints

- **Python is not on `PATH`.** Use `/home/cognitiveghost/Desktop/Projects/shopify-fulfillment-tool/.venv/bin/python` and `.../.venv/bin/ruff` — absolute paths, because the venv lives in the main checkout, not in this worktree.
- **Gate before finishing:** `QT_QPA_PLATFORM=offscreen <venv>/bin/python -m pytest` and `<venv>/bin/ruff check . --exclude shared`.
- **Never hand-edit anything under `shared/`.** It is one-way synced from `../packing-tool`. All customization goes through `gui/theme_manager.py`.
- **Never hardcode colours.** Read them from `get_theme_manager().get_current_theme()`.
- **No new Python dependencies.** `PySide6.QtSvg` ships with PySide6.
- **Pinned asset versions:** Lucide **1.31.0**, Inter **4.1**. Lucide renamed `filter` → `funnel` in 2025, so unpinned names drift and 404.
- **Type-scale rule from Track 1 still applies:** no `font-size:`, `setPointSize` or `setPixelSize` anywhere under `gui/` except `theme_manager.py`. `tests/test_type_scale.py` enforces it.
- **No direct commits to `main`.** This branch is `worktree-iconography-font-embedding`; the work lands as a PR.

---

### Task 1: Vendor the Lucide and Inter assets

Downloads and commits the static assets everything else reads. No Python logic, but it ends with a test so a missing or renamed file fails loudly rather than surfacing as a blank icon at runtime.

**Files:**
- Create: `gui/assets/README.md`
- Create: `gui/assets/icons/*.svg` (15 files)
- Create: `gui/assets/icons/LICENSE`
- Create: `gui/assets/fonts/Inter-Regular.ttf`, `gui/assets/fonts/Inter-Bold.ttf`
- Create: `gui/assets/fonts/OFL.txt`
- Test: `tests/test_ui_assets.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `gui/assets/icons/<name>.svg` for the 15 names listed below; `gui/assets/fonts/Inter-Regular.ttf` and `gui/assets/fonts/Inter-Bold.ttf`. Tasks 2 and 4 read these paths.

- [ ] **Step 1: Download the 15 Lucide SVGs at the pinned tag**

```bash
mkdir -p gui/assets/icons gui/assets/fonts
BASE="https://raw.githubusercontent.com/lucide-icons/lucide/1.31.0/icons"
for n in clipboard-list table folder-open info wrench folder folder-plus funnel-x \
         refresh-cw tag tags circle-minus trash-2 copy package; do
  curl -sSfL -o "gui/assets/icons/$n.svg" "$BASE/$n.svg" || echo "FAILED: $n"
done
curl -sSfL -o gui/assets/icons/LICENSE \
  "https://raw.githubusercontent.com/lucide-icons/lucide/1.31.0/LICENSE"
ls gui/assets/icons/
```

Expected: 15 `.svg` files plus `LICENSE`, no `FAILED` lines. Each SVG should contain `stroke="currentColor"` — that token is what Task 4 substitutes.

- [ ] **Step 2: Download Inter 4.1 and extract only the two static faces**

```bash
curl -sSfL -o /tmp/inter.zip \
  "https://github.com/rsms/inter/releases/download/v4.1/Inter-4.1.zip"
unzip -o -j /tmp/inter.zip "extras/ttf/Inter-Regular.ttf" "extras/ttf/Inter-Bold.ttf" \
  -d gui/assets/fonts/
unzip -o -j /tmp/inter.zip "LICENSE.txt" -d gui/assets/fonts/
mv gui/assets/fonts/LICENSE.txt gui/assets/fonts/OFL.txt
rm /tmp/inter.zip
ls -la gui/assets/fonts/
```

Expected: `Inter-Regular.ttf` (~402 KB), `Inter-Bold.ttf` (~411 KB), `OFL.txt`. Take the files from `extras/ttf/`, **not** the `InterVariable.ttf` at the zip root — Qt's handling of variable fonts is inconsistent across platforms and only two weights are needed.

- [ ] **Step 3: Write the provenance README**

Create `gui/assets/README.md`:

```markdown
# Bundled UI assets

Static assets for the live GUI. Unrelated to `shopify_tool/templates/assets/`,
which holds fonts baked into *printed label* templates.

## icons/ — Lucide 1.31.0 (ISC, see LICENSE)

Source: https://github.com/lucide-icons/lucide/tree/1.31.0/icons

Only the glyphs the app actually uses are vendored. To add one, download it from
the pinned tag above into this directory; `tests/test_ui_assets.py` and
`tests/test_icons.py` will pick it up.

Pin the tag. Lucide renames glyphs between releases — `filter` became `funnel`
in 2025 and `filter.svg` now 404s on `main`.

## fonts/ — Inter 4.1 (SIL OFL 1.1, see OFL.txt)

Source: https://github.com/rsms/inter/releases/tag/v4.1, from `extras/ttf/`.

Regular and Bold only: `TYPE_SCALE` in `gui/theme_manager.py` expresses no
other weight, and no italic. The variable `InterVariable.ttf` is deliberately
not used.
```

- [ ] **Step 4: Write the asset-inventory test**

Create `tests/test_ui_assets.py`:

```python
"""The bundled assets are data, not code, so nothing else fails loudly when
one goes missing -- an absent SVG renders as a blank icon and an absent TTF
silently falls back to Segoe UI. This inventory is the only thing that
notices."""
from pathlib import Path

import pytest

ASSETS_DIR = Path(__file__).resolve().parent.parent / "gui" / "assets"

EXPECTED_ICONS = [
    "circle-minus", "clipboard-list", "copy", "folder", "folder-open",
    "folder-plus", "funnel-x", "info", "package", "refresh-cw", "table",
    "tag", "tags", "trash-2", "wrench",
]


@pytest.mark.parametrize("name", EXPECTED_ICONS)
def test_every_expected_icon_is_vendored(name):
    assert (ASSETS_DIR / "icons" / f"{name}.svg").is_file()


@pytest.mark.parametrize("name", EXPECTED_ICONS)
def test_every_icon_uses_the_currentcolor_token(name):
    """gui/icons.py recolours by substituting this exact string. A glyph
    drawn with a literal colour would render in Lucide's default black and
    vanish against the dark theme."""
    source = (ASSETS_DIR / "icons" / f"{name}.svg").read_text(encoding="utf-8")
    assert "currentColor" in source


@pytest.mark.parametrize("filename", ["Inter-Regular.ttf", "Inter-Bold.ttf"])
def test_both_inter_faces_are_vendored(filename):
    path = ASSETS_DIR / "fonts" / filename
    assert path.is_file()
    assert path.stat().st_size > 100_000, "truncated download?"


def test_licenses_travel_with_the_assets():
    """Both ISC and SIL OFL require the notice ship alongside the files."""
    assert (ASSETS_DIR / "icons" / "LICENSE").is_file()
    assert (ASSETS_DIR / "fonts" / "OFL.txt").is_file()
```

- [ ] **Step 5: Run the test**

Run: `QT_QPA_PLATFORM=offscreen <venv>/bin/python -m pytest tests/test_ui_assets.py -v`
Expected: PASS, 33 tests.

- [ ] **Step 6: Commit**

```bash
git add gui/assets tests/test_ui_assets.py
git commit -m "Vendor Lucide 1.31.0 icons and Inter 4.1 for the GUI

15 glyphs, not the full Lucide set -- adding one is a download into
gui/assets/icons/, documented in the README there. Inter is Regular + Bold
only; TYPE_SCALE expresses no other weight."
```

---

### Task 2: `gui/fonts.py` — register the bundled Inter faces

**Files:**
- Create: `gui/fonts.py`
- Test: `tests/test_fonts.py`

**Interfaces:**
- Consumes: `gui/assets/fonts/Inter-{Regular,Bold}.ttf` from Task 1.
- Produces: `load_bundled_fonts() -> str | None` returning `"Inter"` on success and `None` on any failure. Also `FONTS_DIR: Path` and `FAMILY: str = "Inter"`. Task 3 consumes `load_bundled_fonts`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_fonts.py`:

```python
"""Font loading must never raise. Production is Windows-only, where Segoe UI
always exists, so an unreadable bundled TTF should degrade to Segoe UI -- not
stop a warehouse PC from starting the app."""
import pytest
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication

from gui import fonts


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def clear_font_cache():
    """load_bundled_fonts() is lru_cached; tests that monkeypatch FONTS_DIR
    would otherwise see a neighbour's cached result."""
    fonts.load_bundled_fonts.cache_clear()
    yield
    fonts.load_bundled_fonts.cache_clear()


def test_returns_the_inter_family_name():
    assert fonts.load_bundled_fonts() == "Inter"


def test_family_is_actually_registered_with_qt():
    fonts.load_bundled_fonts()
    assert "Inter" in QFontDatabase.families()


def test_is_idempotent():
    assert fonts.load_bundled_fonts() == fonts.load_bundled_fonts() == "Inter"


def test_returns_none_without_raising_when_assets_are_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(fonts, "FONTS_DIR", tmp_path)
    assert fonts.load_bundled_fonts() is None


def test_returns_none_without_raising_when_a_face_is_corrupt(monkeypatch, tmp_path):
    for name in ("Inter-Regular.ttf", "Inter-Bold.ttf"):
        (tmp_path / name).write_bytes(b"not a font")
    monkeypatch.setattr(fonts, "FONTS_DIR", tmp_path)
    assert fonts.load_bundled_fonts() is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen <venv>/bin/python -m pytest tests/test_fonts.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gui.fonts'`.

- [ ] **Step 3: Write the implementation**

Create `gui/fonts.py`:

```python
"""The bundled Inter faces, registered with Qt on first use.

Windows always ships Segoe UI, so embedding a font buys visual consistency
and dev/prod parity rather than availability. That is exactly why nothing
here raises: a machine that cannot read the bundled TTF falls back to Segoe
UI and keeps working. Contrast gui/icons.py, which fails loudly on an
unknown name -- that is a developer typo caught in seconds, this would be a
production outage.
"""
import logging
from functools import lru_cache
from pathlib import Path

from PySide6.QtGui import QFontDatabase

logger = logging.getLogger(__name__)

FONTS_DIR = Path(__file__).resolve().parent / "assets" / "fonts"
FAMILY = "Inter"

# Regular and Bold only -- TYPE_SCALE expresses no other weight. Registering
# a real Bold face matters: without it Qt synthesizes bold by smearing the
# regular outlines, which looks muddy at 9-10pt.
_FONT_FILES = ("Inter-Regular.ttf", "Inter-Bold.ttf")


@lru_cache(maxsize=1)
def load_bundled_fonts() -> str | None:
    """Register the bundled faces and return the family name, or None.

    Idempotent and cached -- ThemeManager.get_current_theme() calls this, and
    that runs on roughly 180 call sites across gui/*.py.
    """
    families: set[str] = set()
    for filename in _FONT_FILES:
        path = FONTS_DIR / filename
        if not path.is_file():
            logger.warning("Bundled font missing, falling back to system font: %s", path)
            return None
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id == -1:
            logger.warning("Qt rejected bundled font, falling back: %s", path)
            return None
        families.update(QFontDatabase.applicationFontFamilies(font_id))
    if FAMILY not in families:
        logger.warning("Bundled fonts registered as %s, expected %s", families, FAMILY)
        return None
    return FAMILY
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen <venv>/bin/python -m pytest tests/test_fonts.py -v`
Expected: PASS, 5 tests.

Note: do **not** assert with `QFont("Inter").exactMatch()`. It returns `False` even for a correctly registered Inter — verified during the spec spike. `QFontDatabase.families()` membership is the reliable check.

- [ ] **Step 5: Commit**

```bash
git add gui/fonts.py tests/test_fonts.py
git commit -m "Add gui/fonts.py: register the bundled Inter faces

Returns None rather than raising on any failure, so a machine that cannot
read the TTF falls back to Segoe UI instead of failing to start."
```

---

### Task 3: Override `font_family` in `ThemeManager`

**Files:**
- Modify: `gui/theme_manager.py` (imports, and `get_current_theme` at `:41-42`)
- Test: `tests/test_fonts.py` (append)

**Interfaces:**
- Consumes: `gui.fonts.load_bundled_fonts` from Task 2.
- Produces: `get_theme_manager().get_current_theme().font_family` == `"'Inter', Segoe UI, sans-serif"`. Task 4 reads `.text` off the same tokens object. Also `gui.theme_manager._themed_tokens` (module-level, `lru_cache`d) — tests must call `_themed_tokens.cache_clear()` after monkeypatching fonts.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_fonts.py`:

```python
def test_theme_tokens_lead_with_inter_and_keep_segoe_as_fallback():
    """Keeping the original family on the tail is free insurance: a machine
    where Inter fails to register falls back to Segoe UI rather than to Qt's
    generic default."""
    from gui import theme_manager

    theme_manager._themed_tokens.cache_clear()
    family = theme_manager.get_theme_manager().get_current_theme().font_family
    assert family == "'Inter', Segoe UI, sans-serif"


def test_theme_tokens_are_untouched_when_fonts_are_unavailable(monkeypatch, tmp_path):
    from gui import theme_manager

    monkeypatch.setattr(fonts, "FONTS_DIR", tmp_path)
    fonts.load_bundled_fonts.cache_clear()
    theme_manager._themed_tokens.cache_clear()
    try:
        family = theme_manager.get_theme_manager().get_current_theme().font_family
        assert family == "Segoe UI, sans-serif"
    finally:
        fonts.load_bundled_fonts.cache_clear()
        theme_manager._themed_tokens.cache_clear()


def test_tokens_are_memoized_not_rebuilt_per_call():
    """get_current_theme() runs on ~180 call sites; dataclasses.replace()
    allocates a fresh ThemeTokens every time without this."""
    from gui import theme_manager

    theme_manager._themed_tokens.cache_clear()
    manager = theme_manager.get_theme_manager()
    assert manager.get_current_theme() is manager.get_current_theme()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen <venv>/bin/python -m pytest tests/test_fonts.py -v`
Expected: FAIL — `AttributeError: module 'gui.theme_manager' has no attribute '_themed_tokens'`.

- [ ] **Step 3: Write the implementation**

In `gui/theme_manager.py`, extend the imports:

```python
from dataclasses import dataclass, replace
from functools import lru_cache
```

and add `from .fonts import load_bundled_fonts` below the `shared.theme` import.

Replace `get_current_theme` (currently `return get_theme(self._current_theme_name)`) with:

```python
    def get_current_theme(self) -> ThemeTokens:
        return _themed_tokens(self._current_theme_name)
```

Add near `TYPE_SCALE`, after the `ThemeManager` class:

```python
@lru_cache(maxsize=2)
def _themed_tokens(theme_name: str) -> ThemeTokens:
    """shared.theme's tokens with the bundled font family layered on top.

    shared/theme.py is sync-owned by packing-tool and must not be hand-edited,
    so the override happens here -- dataclasses.replace() on the frozen
    ThemeTokens it hands back. Memoized because get_current_theme() runs on
    roughly 180 call sites and replace() allocates.
    """
    theme = get_theme(theme_name)
    family = load_bundled_fonts()
    if family is None:
        return theme
    return replace(theme, font_family=f"'{family}', {theme.font_family}")
```

`shared/theme.py:201` is the only place `font_family` reaches the stylesheet, so this single override covers the whole app.

- [ ] **Step 4: Run the full suite — this changes tokens every other test reads**

Run: `QT_QPA_PLATFORM=offscreen <venv>/bin/python -m pytest -q`
Expected: PASS. If `tests/test_type_scale.py::test_body_role_matches_shared_button_size` fails, the stylesheet build broke — that test reads `build_stylesheet(get_theme("light"))` directly and should be unaffected, so investigate rather than adjusting it.

- [ ] **Step 5: Commit**

```bash
git add gui/theme_manager.py tests/test_fonts.py
git commit -m "Use bundled Inter as the app font family

Overrides ThemeTokens.font_family in get_current_theme() via
dataclasses.replace(), keeping Segoe UI on the tail of the family list as a
fallback. shared/theme.py stays untouched -- it is sync-owned by packing-tool."
```

---

### Task 4: `gui/icons.py` — themed Lucide icons

**Files:**
- Create: `gui/icons.py`
- Test: `tests/test_icons.py`

**Interfaces:**
- Consumes: `gui/assets/icons/*.svg` from Task 1; `get_theme_manager().get_current_theme().text` from Task 3.
- Produces: `icon(name: str, color: str | None = None) -> QIcon`, raising `KeyError` on an unknown name. Also `ICONS_DIR: Path`. Tasks 5, 6, 7 and 8 all consume `icon`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_icons.py`:

```python
"""Icons are recoloured by substituting Lucide's currentColor token in the SVG
source before rasterizing, so these tests assert on actual rendered pixels --
a QIcon that is merely non-null proves nothing about whether it is visible
against the current theme."""
import pytest
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from gui.icons import icon
from gui.theme_manager import get_theme_manager


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


def _opaque_colors(qicon: QIcon, size: int = 32) -> set[str]:
    image = qicon.pixmap(size, size).toImage()
    return {
        image.pixelColor(x, y).name()
        for y in range(image.height())
        for x in range(image.width())
        if image.pixelColor(x, y).alpha() > 200
    }


def test_returns_a_non_null_icon():
    assert not icon("package").isNull()


def test_unknown_name_raises_rather_than_returning_a_blank_icon():
    """A blank QIcon renders as empty space -- silently, and only on whichever
    screen uses it. Fail during development instead."""
    with pytest.raises(KeyError):
        icon("definitely-not-a-lucide-glyph")


def test_renders_in_an_explicitly_requested_color():
    assert _opaque_colors(icon("package", color="#FF0000")) == {"#ff0000"}


def test_defaults_to_the_current_theme_text_color():
    expected = get_theme_manager().get_current_theme().text.lower()
    assert _opaque_colors(icon("trash-2")) == {expected}


def test_color_follows_a_theme_toggle():
    """The whole point: a dark-grey icon on a dark background is invisible."""
    manager = get_theme_manager()
    original = manager.get_current_theme_name()
    try:
        manager.set_theme("light")
        light = _opaque_colors(icon("wrench"))
        manager.set_theme("dark")
        dark = _opaque_colors(icon("wrench"))
        assert light != dark
    finally:
        manager.set_theme(original)


def test_icon_carries_several_resolutions_for_hidpi():
    """Rendering one 16px pixmap and letting Qt upscale it is what makes icons
    blurry on the 125%/150%-scaled displays the warehouse PCs run."""
    sizes = {size.width() for size in icon("info").availableSizes()}
    assert {16, 24, 32, 48} <= sizes


def test_repeated_calls_reuse_the_cached_render():
    assert icon("copy") is icon("copy")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen <venv>/bin/python -m pytest tests/test_icons.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gui.icons'`.

- [ ] **Step 3: Write the implementation**

Create `gui/icons.py`:

```python
"""Themed icons rendered from the bundled Lucide SVGs.

Lucide draws every glyph with stroke="currentColor". Substituting that token
in the SVG source before handing it to QSvgRenderer recolours the *vectors*,
so output stays crisp at any size and DPI -- unlike recolouring an already
rasterized pixmap with CompositionMode_SourceIn. It also means we never load
an .svg through QIcon, so the frozen build does not depend on Qt's qsvg
imageformats plugin being collected.
"""
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from .theme_manager import get_theme_manager

ICONS_DIR = Path(__file__).resolve().parent / "assets" / "icons"

# Qt picks the closest of these for the widget size and the screen's device
# pixel ratio. Querying devicePixelRatio ourselves would be wrong on a
# multi-monitor setup, where it differs per screen.
_RENDER_SIZES = (16, 24, 32, 48)


@lru_cache(maxsize=None)
def _source(name: str) -> str:
    path = ICONS_DIR / f"{name}.svg"
    if not path.is_file():
        raise KeyError(f"No bundled icon named {name!r} (looked in {ICONS_DIR})")
    return path.read_text(encoding="utf-8")


@lru_cache(maxsize=None)
def _render(name: str, color: str) -> QIcon:
    data = QByteArray(_source(name).replace("currentColor", color).encode())
    result = QIcon()
    for size in _RENDER_SIZES:
        # One renderer per size: QSvgRenderer keeps view state across render()
        # calls, and reusing it across sizes skews the later ones.
        renderer = QSvgRenderer(data)
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        renderer.render(painter)
        painter.end()
        result.addPixmap(pixmap)
    return result


def icon(name: str, color: str | None = None) -> QIcon:
    """A themed icon by Lucide glyph name, e.g. icon("trash-2").

    Defaults to the active theme's text colour. Pass `color` only where the
    icon has to read against something that is not this app's background --
    the window/taskbar icon, which sits on the OS shell's own surface.

    Raises KeyError on an unknown name, matching font_css()'s rule: a typo
    must fail during development rather than render invisible in production.

    Cached on (name, colour). A theme toggle needs no invalidation -- the
    colour is part of the key, so it simply misses into a second set of
    entries, and two themes times fifteen glyphs is the ceiling.
    """
    if color is None:
        color = get_theme_manager().get_current_theme().text
    return _render(name, color)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen <venv>/bin/python -m pytest tests/test_icons.py -v`
Expected: PASS, 7 tests.

If `test_renders_in_an_explicitly_requested_color` fails with an empty set, the SVG has no opaque pixels at 32px — check that `pixmap.fill(Qt.transparent)` runs before the `QPainter` is constructed, not after.

- [ ] **Step 5: Commit**

```bash
git add gui/icons.py tests/test_icons.py
git commit -m "Add gui/icons.py: theme-recoloured Lucide icons

Substitutes Lucide's currentColor in the SVG source and renders through
QSvgRenderer at 16/24/32/48px into one multi-resolution QIcon, so icons stay
sharp on scaled Windows displays. Recolouring vectors rather than a rasterized
pixmap also avoids depending on Qt's qsvg imageformats plugin under
PyInstaller."
```

---

### Task 5: Migrate `ui_manager.py`'s 9 long-lived icons

These are the icons that outlive a theme toggle, so this task also adds the refresh slot. The context-menu icons are Task 6.

**Files:**
- Modify: `gui/ui_manager.py` — imports (`:5-27`), `create_widgets` (`:64-112`), `_create_tabs` (`:114-142`), `_create_global_header` (`:185-187`), `_create_reports_group` (`:719-722`), `_create_session_management_section` (`:1053-1056`), `_create_filter_controls` (`:1096-1099`)
- Test: `tests/test_icons.py` (append)

**Interfaces:**
- Consumes: `gui.icons.icon` from Task 4.
- Produces: `UIManager._refresh_icons()`, `UIManager._TAB_ICONS`, `UIManager._BUTTON_ICONS`; and a new `self.mw.session_folder_icon_label` attribute (previously a local named `session_icon_label`).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_icons.py`:

```python
def test_every_long_lived_icon_name_resolves():
    """The five tab icons are the app's most-seen chrome, and with the three
    buttons they are the only icons that outlive a theme change -- everything
    in the context menu is rebuilt on each right-click."""
    from gui.ui_manager import UIManager

    assert UIManager._TAB_ICONS == (
        "clipboard-list", "table", "folder-open", "info", "wrench",
    )
    for name in UIManager._TAB_ICONS:
        assert not icon(name).isNull()
    for name in UIManager._BUTTON_ICONS.values():
        assert not icon(name).isNull()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen <venv>/bin/python -m pytest tests/test_icons.py -k tab_icons -v`
Expected: FAIL — `AttributeError: type object 'UIManager' has no attribute '_TAB_ICONS'`.

- [ ] **Step 3: Add the icon tables and the refresh slot**

In `gui/ui_manager.py`, add to the imports below `from .bulk_operations_toolbar import BulkOperationsToolbar`:

```python
from .icons import icon
```

Add these as class attributes on `UIManager`, directly above `def __init__`:

```python
    # Only long-lived icons need re-theming on a theme toggle. The context
    # menu in main_window_pyside.py is rebuilt on every right-click, so its
    # icons pick up the new colour for free.
    _TAB_ICONS = ("clipboard-list", "table", "folder-open", "info", "wrench")
    _BUTTON_ICONS = {
        "open_session_folder_button": "folder-open",
        "new_session_btn": "folder-plus",
        "clear_filter_button": "funnel-x",
    }
```

Add this method next to `_update_theme_button_text`:

```python
    def _refresh_icons(self):
        """Re-render every long-lived icon in the app's current theme colour.

        A QIcon handed to addTab()/setIcon() is a snapshot -- it does not
        follow a theme toggle, and a dark-grey glyph on the dark theme's
        background is invisible.
        """
        for index, name in enumerate(self._TAB_ICONS):
            self.mw.main_tabs.setTabIcon(index, icon(name))
        for attr, name in self._BUTTON_ICONS.items():
            widget = getattr(self.mw, attr, None)
            if widget is not None:
                widget.setIcon(icon(name))
        label = getattr(self.mw, "session_folder_icon_label", None)
        if label is not None:
            label.setPixmap(icon("folder").pixmap(16, 16))
```

- [ ] **Step 4: Replace the six call sites**

In `_create_tabs`, delete the five `standardIcon` lines and pass no icon to `addTab` — `_refresh_icons()` sets them all in Step 5:

```python
        self.mw.main_tabs.addTab(tab1, "Session Setup")
        self.mw.main_tabs.addTab(tab2, "Analysis Results")
        self.mw.main_tabs.addTab(tab3, "Session Browser")
        self.mw.main_tabs.addTab(tab4, "Information")
        self.mw.main_tabs.addTab(tab5, "Tools")
```

In `_create_global_header` (~`:185`), promote the local label to an attribute so the refresh slot can reach it:

```python
        self.mw.session_folder_icon_label = QLabel()
        session_row.addWidget(self.mw.session_folder_icon_label)
```

(delete the `folder_icon = ...standardIcon(QStyle.SP_DirIcon)` line and the `setPixmap` line — `_refresh_icons()` sets the pixmap.)

In `_create_reports_group` (~`:720`), `_create_session_management_section` (~`:1054`) and `_create_filter_controls` (~`:1097`), delete each `.setIcon(self.mw.style().standardIcon(...))` call entirely. `_refresh_icons()` sets all three from `_BUTTON_ICONS`.

Finally remove `QStyle` from the `PySide6.QtWidgets` import block — it has no remaining use in this file.

- [ ] **Step 5: Wire the initial paint and the theme signal**

At the end of `create_widgets`, immediately before `self.mw.statusBar().showMessage("Ready")`:

```python
        # Every widget exists by now, so one pass sets every long-lived icon.
        self._refresh_icons()
        get_theme_manager().theme_changed.connect(self._refresh_icons)
```

- [ ] **Step 6: Run the suite**

Run: `QT_QPA_PLATFORM=offscreen <venv>/bin/python -m pytest -q`
Expected: PASS. `tests/test_session_setup_layout.py` and `tests/test_session_browser_filter.py` construct these widgets — if either fails on a missing attribute, a `setIcon` line was deleted without its widget being listed in `_BUTTON_ICONS`.

- [ ] **Step 7: Commit**

```bash
git add gui/ui_manager.py tests/test_icons.py
git commit -m "Replace ui_manager's 9 stock icons with themed Lucide glyphs

Adds _refresh_icons(), connected to theme_changed: a QIcon handed to addTab()
is a snapshot and would stay dark-grey against the dark theme otherwise.
Only these nine need it -- the context-menu icons are rebuilt per right-click."
```

---

### Task 6: Migrate the analysis-table context menu

**Files:**
- Modify: `gui/main_window_pyside.py:1465-1573` (8 icon sites, plus the function-local `from PySide6.QtWidgets import QStyle` at `:1469`)
- Test: `tests/test_icons.py` (append)

**Interfaces:**
- Consumes: `gui.icons.icon` from Task 4.
- Produces: nothing new. This menu is rebuilt on every right-click and registers no refresh hook.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_icons.py`:

```python
def test_context_menu_no_longer_reaches_for_stock_icons():
    """Three separate menu actions shared SP_FileDialogDetailedView, which is
    why the app's icons carried no meaning. Each gets its own glyph now."""
    from pathlib import Path

    source = (
        Path(__file__).resolve().parent.parent / "gui" / "main_window_pyside.py"
    ).read_text(encoding="utf-8")
    assert "QStyle.SP_" not in source
    for name in ("refresh-cw", "tag", "tags", "circle-minus", "trash-2", "copy"):
        assert f'icon("{name}")' in source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen <venv>/bin/python -m pytest tests/test_icons.py -k context_menu -v`
Expected: FAIL — `assert "QStyle.SP_" not in source`.

- [ ] **Step 3: Replace the eight call sites**

Add `from .icons import icon` to the module's imports at the top of `gui/main_window_pyside.py`, then apply these substitutions inside the context-menu block. Delete the function-local `from PySide6.QtWidgets import QStyle` line at `:1469` and the `# Add actions with icons from QStyle` comment above `menu = QMenu()`.

| Line | From | To |
|---|---|---|
| `:1476` | `self.style().standardIcon(QStyle.SP_BrowserReload),` | `icon("refresh-cw"),` |
| `:1490` | `self.style().standardIcon(QStyle.SP_FileDialogDetailedView),` | `icon("tag"),` |
| `:1501-1503` | `tags_menu.setIcon(\n    self.style().standardIcon(QStyle.SP_FileDialogDetailedView)\n)` | `tags_menu.setIcon(icon("tags"))` |
| `:1526` | `self.style().standardIcon(QStyle.SP_DialogCancelButton),` | `icon("circle-minus"),` |
| `:1543` | `self.style().standardIcon(QStyle.SP_TrashIcon),` | `icon("trash-2"),` |
| `:1556` | `self.style().standardIcon(QStyle.SP_FileDialogDetailedView),` | `icon("copy"),` |
| `:1567` | `self.style().standardIcon(QStyle.SP_FileDialogDetailedView),` | `icon("copy"),` |

Note the last two are both "Copy" actions (Copy Order Number, Copy SKU) and correctly share the `copy` glyph — that is the one place sharing an icon is meaningful.

If `QStyle` is imported at module level in this file and now has no other use, remove it. Check with `grep -n "QStyle" gui/main_window_pyside.py` before deleting.

- [ ] **Step 4: Run the suite**

Run: `QT_QPA_PLATFORM=offscreen <venv>/bin/python -m pytest -q`
Expected: PASS. `tests/test_main_window_tags.py` exercises this file.

- [ ] **Step 5: Commit**

```bash
git add gui/main_window_pyside.py tests/test_icons.py
git commit -m "Replace the analysis-table context menu's stock icons

Three actions shared SP_FileDialogDetailedView; each now has its own glyph.
No refresh hook needed -- the menu is rebuilt on every right-click."
```

---

### Task 7: Give the app a window and taskbar icon

**Files:**
- Modify: `gui_main.py` (imports, and `main()`)
- Test: `tests/test_gui_main_env_setup.py` (append)

**Interfaces:**
- Consumes: `gui.icons.icon` from Task 4.
- Produces: `gui_main.build_app_icon() -> QIcon`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_gui_main_env_setup.py`:

```python
def test_app_icon_is_built_in_a_fixed_accent_color():
    """The taskbar icon sits on the OS shell's surface, which has nothing to
    do with this app's theme -- so it is deliberately not re-themed."""
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])

    import gui_main
    from gui.theme_manager import get_theme_manager

    app_icon = gui_main.build_app_icon()
    assert not app_icon.isNull()

    image = app_icon.pixmap(48, 48).toImage()
    opaque = {
        image.pixelColor(x, y).name()
        for y in range(image.height())
        for x in range(image.width())
        if image.pixelColor(x, y).alpha() > 200
    }
    assert opaque == {get_theme_manager().get_current_theme().accent_blue.lower()}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen <venv>/bin/python -m pytest tests/test_gui_main_env_setup.py -k app_icon -v`
Expected: FAIL — `AttributeError: module 'gui_main' has no attribute 'build_app_icon'`.

- [ ] **Step 3: Write the implementation**

In `gui_main.py`, add below the existing `from gui.theme_manager import get_theme_manager`:

```python
from gui.icons import icon
```

Add this function above `main()`:

```python
def build_app_icon():
    """The window/taskbar icon. The app has never had one.

    Coloured with accent_blue rather than the theme's text colour, and never
    re-themed: this icon is drawn on the OS shell's own surface, whose
    background has nothing to do with which theme the app is running.
    """
    return icon("package", color=get_theme_manager().get_current_theme().accent_blue)
```

In `main()`, immediately after `theme_manager.apply_theme()`:

```python
    app.setWindowIcon(build_app_icon())
```

`build_app_icon` must be called after `QApplication(sys.argv)` exists — `QPixmap` construction requires a live QGuiApplication.

- [ ] **Step 4: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen <venv>/bin/python -m pytest tests/test_gui_main_env_setup.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gui_main.py tests/test_gui_main_env_setup.py
git commit -m "Add a window and taskbar icon

First one the app has ever had. Fixed accent_blue rather than theme text --
it renders on the OS shell's surface, not on ours."
```

---

### Task 8: Guard tests and packaging

Locks the migration in and makes the assets survive a frozen build. Both guards mirror the bypass guard Track 1 shipped in `tests/test_type_scale.py`.

**Files:**
- Create: `tests/test_icon_usage_guard.py`
- Modify: `.github/workflows/build_release.yml:94-96`
- Modify: `README.md` (version line only if bumping)

**Interfaces:**
- Consumes: everything from Tasks 1-7.
- Produces: nothing consumed downstream.

- [ ] **Step 1: Write the failing guards**

Create `tests/test_icon_usage_guard.py`:

```python
"""Two guards, not unit tests.

The first is the whole point of this track: without it, the next dialog
someone adds reaches for a stock icon and the app drifts back to mixed
iconography one widget at a time. The second catches the failure mode
icon()'s KeyError cannot -- a typo in a rarely-opened dialog that no test
ever constructs.
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GUI_DIR = REPO_ROOT / "gui"
ICONS_DIR = GUI_DIR / "assets" / "icons"

# rglob, not glob: gui/ is flat today but Track 3 adds gui/components/, and a
# non-recursive scan would let the first package inside it escape silently.
_PY_FILES = sorted(GUI_DIR.rglob("*.py")) + [REPO_ROOT / "gui_main.py"]

_ICON_CALL = re.compile(r'\bicon\(\s*["\']([a-z0-9-]+)["\']')


def test_no_stock_icons_remain_anywhere_in_the_gui():
    offenders = []
    for path in _PY_FILES:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "QStyle.SP_" in line:
                offenders.append(f"{path.name}:{lineno}: {line.strip()}")
    assert not offenders, (
        "Use gui.icons.icon() instead of OS-native stock icons:\n" + "\n".join(offenders)
    )


def test_every_referenced_icon_name_is_vendored():
    missing = []
    for path in _PY_FILES:
        if path.name == "icons.py":
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for name in _ICON_CALL.findall(line):
                if not (ICONS_DIR / f"{name}.svg").is_file():
                    missing.append(f"{path.name}:{lineno}: {name}")
    assert not missing, (
        "Referenced icons with no vendored SVG (see gui/assets/README.md to add "
        "one):\n" + "\n".join(missing)
    )


def test_ui_managers_icon_tables_are_vendored():
    """_TAB_ICONS and _BUTTON_ICONS hold bare string literals, not icon()
    calls, so the regex guard above cannot see them -- and they are the names
    most worth catching, since a typo there blanks the app's five tabs."""
    from gui.ui_manager import UIManager

    names = list(UIManager._TAB_ICONS) + list(UIManager._BUTTON_ICONS.values())
    missing = [n for n in names if not (ICONS_DIR / f"{n}.svg").is_file()]
    assert not missing, f"UIManager references unvendored icons: {missing}"


def test_the_guard_can_actually_see_icon_calls():
    """A regex guard that matches nothing passes vacuously forever. Assert it
    finds the call sites we know exist."""
    found = set()
    for path in _PY_FILES:
        found.update(_ICON_CALL.findall(path.read_text(encoding="utf-8")))
    assert {"package", "trash-2", "copy"} <= found
```

- [ ] **Step 2: Run the guards**

Run: `QT_QPA_PLATFORM=offscreen <venv>/bin/python -m pytest tests/test_icon_usage_guard.py -v`
Expected: PASS, 4 tests. If the first guard fails, a `QStyle.SP_` site was missed in Task 5 or 6 — fix the site, not the guard.

- [ ] **Step 3: Ship the assets in the frozen build**

In `.github/workflows/build_release.yml`, add one line to the `pyinstaller` invocation, directly below the existing `--add-data` (currently line 95):

```yaml
          --add-data "gui/assets;gui/assets"
```

The runtime path (`Path(__file__).resolve().parent / "assets"`) already works under `--onedir`: it is the identical pattern `shopify_tool/barcode_processor.py:23` uses for its templates directory, which ships this way today.

`PySide6.QtSvg` needs no `--collect-submodules`. It is a real module imported statically by `gui/icons.py`, so PyInstaller's PySide6 hook collects it. Note that `gui/icons.py` deliberately never loads an `.svg` through `QIcon`, so the frozen build does not need Qt's `qsvg` **imageformats plugin** either — only the module.

- [ ] **Step 4: Run the full gate**

```bash
QT_QPA_PLATFORM=offscreen <venv>/bin/python -m pytest
<venv>/bin/ruff check . --exclude shared
```

Expected: all tests pass (397 before this branch, plus ~48 new), ruff clean.

- [ ] **Step 5: Refresh the knowledge graph**

```bash
graphify update .
```

Required by `CLAUDE.md` after modifying code. `graphify-out/` is gitignored, so there is nothing to commit.

- [ ] **Step 6: Commit**

```bash
git add tests/test_icon_usage_guard.py .github/workflows/build_release.yml
git commit -m "Guard the icon migration and ship gui/assets in frozen builds

The first guard is what stops the next new dialog from reaching for a stock
icon and drifting the app back to mixed iconography. The second catches a
typo in a dialog no test constructs, which icon()'s KeyError cannot."
```

---

## Verification checklist

Before opening the PR:

- [ ] `QT_QPA_PLATFORM=offscreen <venv>/bin/python -m pytest` — all pass
- [ ] `<venv>/bin/ruff check . --exclude shared` — clean
- [ ] `grep -rn "QStyle.SP_" gui/ gui_main.py` — no output
- [ ] `git status` — no stray files; `gui/assets/` is committed, not gitignored (check `.gitignore` does not exclude `*.ttf`)
- [ ] `graphify update .` has been run

## What the reviewer should look at

- **Nothing here has been seen on Windows.** Development is Ubuntu-only, and this is the second consecutive uncalibrated visual change after Track 1's type scale.
- **Inter renders smaller than Segoe UI at the same point size** — measured 16px line height against the fallback's 18px at 10pt. If text reads small on Windows, the fix is a one-line `TYPE_SCALE` bump in `gui/theme_manager.py`, not a revert.
- **Lucide's 2px stroke on a 24px grid softens at 16px**, which is the size tab icons render at. If it reads muddy, substitute `stroke-width` alongside `currentColor` in `gui/icons.py`.
- **Icon semantics are a judgement call.** `clipboard-list` for Session Setup and `funnel-x` for the Clear-filter button are the two least obvious; both are one-line edits in `UIManager._TAB_ICONS` / `_BUTTON_ICONS`.
