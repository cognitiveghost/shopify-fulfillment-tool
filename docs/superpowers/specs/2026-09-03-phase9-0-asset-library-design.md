# 9.0 — One asset library, shared by both apps

Parent spec: `docs/superpowers/specs/2026-09-03-phase9-fulfilment-v2-design.md` § 7
Roadmap: `docs/superpowers/plans/2026-09-03-phase9-roadmap.md` § Track Q / 9.0
Decision record: `docs/adr/0002-themed-glyphs-in-qss-image-properties.md`
Plan: `docs/superpowers/plans/2026-09-03-phase9-0-asset-library-plan.md`
Artboard: none — enabling work.

Classification: **bounded**. The move is mechanical; one question inside it
was not, and ADR 0002 answers it.

---

## 1. What is actually duplicated

The parent spec says the three files are "byte-for-byte identical apart from
one icon". Measured, that is true of two of them:

| | packing-tool | shopify-fulfillment-tool |
|---|---|---|
| `gui/fonts.py` | identical | identical |
| `gui/assets/fonts/` | identical | identical |
| `gui/assets/icons/` | 17 files | same 17 + `message-square.svg` |
| `gui/assets/README.md` | differs (prose only) | differs (prose only) |
| `gui/icons.py` | **differs — 2 lines** | **differs — 2 lines** |

`gui/icons.py` differs in exactly one thing, and it is the thing that decides
where the module can live:

```python
# packing-tool                     # shopify-fulfillment-tool
from gui.theme import current_tokens        from .theme_manager import get_theme_manager
color = current_tokens().text              color = get_theme_manager().get_current_theme().text
```

Each repo reaches its own theme shim. A module in `shared/` can reach neither.

## 2. The theme seam

`shared/navrail.py` already settles this and is the precedent to copy: it does
`from shared.theme import current_tokens, font_css, theme_notifier`.
`shared/theme.py` owns `_current` and is the single record of which theme is
live — both apps' shims call `set_current()` last in their apply path
specifically so shared widgets can read it.

So `shared/icons.py` reads `shared.theme.current_tokens().text`.

This is colour-identical to both call sites today. The one documented
difference between `shared.theme.current_tokens()` and each app's
`current_tokens()` is that the shared one omits the bundled font family
(`shared/theme.py:254`) — irrelevant here, because `icons.py` reads a colour
and never `font_family`.

Its unseeded fallback is also correct for us: `get_theme(None)` returns the
same default `get_theme()` would, so an icon built before a theme is applied
renders in the default theme's text colour rather than blank.

## 3. Target shape

```
shared/
├── icons.py          # was gui/icons.py, ×2
├── fonts.py          # was gui/fonts.py, ×2 (byte-identical, moves unchanged)
└── assets/
    ├── README.md     # merged from the two, one library
    ├── fonts/        # Inter Regular + Bold, OFL.txt
    └── icons/        # union of both repos + 5 new glyphs, LICENSE
```

`gui/icons.py`, `gui/fonts.py` and `gui/assets/` are **deleted** from both
repos — no re-export shims. There are only 8 importing files across both, and
a shim that exists to avoid touching 8 lines is the kind of pass-through the
deletion test rejects: delete it and no complexity reappears anywhere.

`scripts/sync_shared.py` needs **no change**. It already walks
`SOURCE.rglob("*")`, skips `__pycache__`, copies every file and creates parent
directories — so `shared/assets/**` rides along for free. (It never *deletes*,
which matters in the other direction only.)

## 4. The glyph inventory

The brief lists what to vendor. Verified against the pinned tag
(`lucide-icons/lucide` **1.31.0**) — all five return HTTP 200:

| glyph | consumer | route |
|---|---|---|
| `plus` | New session (9.7) | `icon()` → `QIcon` |
| `ellipsis-vertical` | overflow menu (9.8) | `icon()` → `QIcon` |
| `check` | checkbox tick (9.5) | `glyph_url()` → QSS `image:` |
| `chevron-up` | sort caret ascending (9.4) | `glyph_url()` → QSS `image:` |
| `chevron-down` | sort caret descending (9.4) | `glyph_url()` → QSS `image:` |

**Departure from the brief — two of the named sub-controls get no glyph.**
The brief asks for "the radio dot and the toggle's two states". A radio dot is
a filled circle and a toggle knob is a filled circle; QSS draws circles with
`border-radius`, natively, in one rule. Vendoring an SVG for a shape the
stylesheet already draws adds a file, a cache entry and a rasterisation to
produce a worse circle. 9.5 draws both in QSS. If 9.5 finds a case this cannot
express, it adds the glyph then — the library is the point, and adding one
file to it later costs nothing.

`message-square.svg` is currently shopify-only. It moves into the shared
library and both apps get it; a shared library that is the union is the whole
idea, and the file is 285 bytes.

## 5. Themed glyphs in QSS `image:` — see ADR 0002

Summary of the decision the ADR records: `image: url(x.svg)` works but
reintroduces the `qsvg` imageformats plugin that `icons.py` exists to avoid;
`url(data:…)` does not work at all in Qt's QSS. `shared/icons.py` therefore
gains `glyph_url()`, which rasterises the recoloured SVG to a cached PNG with
the same `QSvgRenderer` `icon()` already uses and returns a QSS `url("…")`
token. The path must be spelled `as_posix()` — a backslash path draws nothing,
silently, on Windows only.

Nothing in 9.0 *calls* `glyph_url()`. 9.4 and 9.5 do. 9.0 ships it with the
glyphs so those two do not each invent a scheme.

## 6. What "expose the SVG directory to the web tier" means here

The web tier does not exist yet — 9.11 emits the tokens as CSS custom
properties and 9.12 builds the QWebChannel bridge. Building a URL scheme
handler now would be a handler with no page to serve.

**9.0 exposes it as a public path**: `shared.icons.ICONS_DIR` and
`shared.fonts.FONTS_DIR` are documented as the library's public surface, and
the frozen build ships the directory (§ 7). 9.12 points the web view's base
URL or custom scheme at `ICONS_DIR` when there is a web view to point.

Stated as a departure so it is not mistaken for an oversight: the "one glyph
set serves both renderers" outcome is achieved by there being one directory
with a stable name, not by 9.0 writing web plumbing.

The parent spec's rule that no hex may appear in a web asset is unaffected —
Lucide SVGs carry `currentColor`, and `tests/test_ui_assets.py` already
asserts exactly that on every vendored glyph.

## 7. The frozen build

Both build definitions currently ship `gui/assets` and must ship
`shared/assets` instead:

- `packing-tool/main.spec` — `datas=[('gui/assets', 'gui/assets'), …]`
  becomes `('shared/assets', 'shared/assets')`.
- `shopify-fulfillment-tool/.github/workflows/build_release.yml:96` —
  `--add-data "gui/assets;gui/assets"` becomes
  `--add-data "shared/assets;shared/assets"`.

The path arithmetic is unchanged in kind. `Path(__file__).resolve().parent /
"assets"` works under PyInstaller today because `--add-data` lands the data
beside the (archived) module's nominal path; moving both the module and its
data from `gui/` to `shared/` preserves that relationship exactly.

The workflow's "Verify bundled assets shipped" step already greps the built
tree for `package.svg` and `Inter-Regular.ttf` recursively, so it keeps
working unchanged and is what proves the move on Windows. It is the only part
of this that cannot be checked from the Linux dev machine.

## 8. Tests

`shared/` carries no tests and this task does not change that. Each repo keeps
its own copies, repointed at `shared/assets`:

| test | today | after |
|---|---|---|
| `test_ui_assets.py` | shopify only, inventory + licences | both repos, union inventory |
| `test_icon_usage_guard.py` | shopify only, bans `QStyle.SP_` | both repos |
| `test_icons.py` / `test_assets.py` | render + KeyError, one each | both repos, plus `glyph_url` |

Seams to test at, so Stage B is not guessing:

1. **`shared/icons.py` public functions** — `icon()`, `glyph_url()`. Unit,
   with `qapp`. This is where the `as_posix()` rule is asserted.
2. **The asset directory as an inventory** — filesystem only, no Qt.
   `test_ui_assets.py`, parametrised over the union list.
3. **The source tree as text** — the usage guards. Regex over `gui/**/*.py`;
   they must now also accept `from shared.icons import icon`.
4. **The frozen tree** — the existing Windows CI grep. Not runnable locally.

## 9. Out of scope, deliberately

- **The duplicated font-layering.** `shopify/gui/theme_manager.py:194-218`
  and `packing/gui/theme.py:31-50` hold the same `_tokens_with_font()`,
  the same `lru_cache(maxsize=2)`, and the same comment about not caching the
  miss. Once `fonts.py` is in `shared/`, `shared/theme.py` could own this and
  both copies would go. It is a real deletion and it belongs to whoever next
  opens `shared/theme.py` — **9.1**, which opens it anyway. Not folded in
  here: it changes what `current_tokens()` returns, which ~180 call sites
  read, and that does not belong in a file-move PR.
- **`shared/README.md` is stale** — it still describes installing `shared/`
  as a git submodule, which is not how either repo consumes it. Noted, not
  fixed here.
- **Retiring `QStyle.SP_`-style stock icons in packing-tool.** Adopting
  shopify's usage guard in packing-tool may surface offenders. If it does,
  they are listed for a follow-up, not fixed in this PR — see the plan's
  Stage 4 note.
