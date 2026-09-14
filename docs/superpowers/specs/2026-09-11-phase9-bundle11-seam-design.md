# Phase 9 Bundle 11 — The seam: palette export and the bridge (9.11 + 9.12)

- **Todoist:** bundle `6hQXj734Xj783Xf3`; items 9.11 `6hQVj56J5QWWHpV3`, 9.12 `6hQVj58xpRQpr6xV`
- **Contract:** roadmap § Track V (`docs/superpowers/plans/2026-09-03-phase9-roadmap.md`),
  Phase 9 spec §4.2–4.4, ADR 0001
- **Artboard:** F6 (palette). The bridge has none. **Nothing in this bundle is
  visible to a user.** No mockup applies, and `frontend-design` has nothing to
  decide.
- **Classification:** bounded. The briefs pin the design. This document records
  where the code disagreed with them and the four decisions that followed.

## 1. What this bundle delivers

Three pure or near-pure seams, and the plumbing that joins them:

| Seam | Where | Repo |
|---|---|---|
| `theme_css_vars(theme) -> str` | `shared/theme.py` | packing-tool (canonical), synced here |
| web-asset rules in `find_style_literals` | `shared/style_lint.py` | packing-tool (canonical), synced here |
| `order_payload(df) -> list[dict]` | `gui/orders_view.py` | shopify |
| `ResultsBridge` + `mount_results_page(view)` | `gui/results_bridge.py`, `gui/web/` | shopify |

**Bundle done when:**
- `theme_css_vars` round-trips both themes.
- The linter fails on a planted hex **and** on a planted `box-shadow` in a web
  asset.
- One mono face is used on screen by both tiers.
- A test drives a selection change from JS into Python **and** an order payload
  from Python into JS.
- A theme switch repaints the web document without a reload.

Following the Bundle 1 and 9.19 precedent, this ships as **two PRs**:
- a **packing-tool half** carrying the `shared/` change;
- a **shopify half** carrying the sync plus everything else.

The packing-tool half merges first. Until it does, the shopify PR's
`shared-sync-check` job fails, by design.

## 2. Premises the code disproved

1. **"The font seam shows on every SKU."** It does not.
   `shopify_tool/templates/assets/fonts/` belongs to the *printed-label*
   templates, which CONTEXT.md already calls unrelated to the UI.
   `shopify_tool/label_tools.py` wraps label text using JetBrains Mono's 0.6em
   character width.

   On screen, the Qt tier takes its mono face from `font_family_mono`
   (`"Consolas, monospace"`, read by `gui/log_model.py`). The web tier will
   read the same token as `--font-family-mono`.

   **Decision (repo owner, 2026-09-11): labels are untouched.** ADR 0001's
   guardrail now carries a dated correction.

2. **"The Qt-side `pandas_model` serves an order-level frame from here on."**
   That is already true. `gui/orders_view.py` has `classify_columns`,
   `orders_frame` and `order_lines` (the 1b redesign). The payload is built
   from those, not written again.

3. **The Ubuntu CI image cannot load QtWebEngine.** It lacks NSS and the X
   client libraries (`tests/test_webengine_available.py` says so).
   **Decision: install them in CI** so the round-trip test runs on every PR.
   The package list comes from `ldd` on `libQt6WebEngineCore.so.6` and
   `QtWebEngineProcess` against the dev box.

4. **Missed by the brief — a second font seam.** Chromium cannot see fonts
   registered with Qt's `QFontDatabase`. `--font-family` will read
   `'Inter', Segoe UI, sans-serif`. Without an `@font-face`, the web tier
   would silently render in Segoe UI beside Inter chrome. The page's base
   stylesheet therefore declares Inter from the asset library
   (`shared/assets/fonts/`).

## 3. `theme_css_vars(theme)` (9.11)

```python
def theme_css_vars(theme: ThemeTokens) -> str   # ":root {\n  --name: value;\n  …\n}\n"
```

It lives beside `build_stylesheet` in `shared/theme.py`. It is pure apart
from reading the active density, which `type_style()` and
`get_density_profile()` already do.

Declarations, in this order:

1. **Every `ThemeTokens` dataclass field except `name` and the ten aliases**
   (the left column of `_ALIAS_PAIRS`).
   - The name is `"--" + field.replace("_", "-")`, mechanically, so a field
     added later needs no second registration site.
   - `int` values get `px` appended (`radius`, `spacing_*`). `str` values
     are emitted verbatim (colours, `font_family`, `font_family_mono`).
2. **The type scale, resolved for the active density.** For each role in
   `TYPE_SCALE`:
   - `--type-<role>-size: <type_style(role).size_pt>pt`
   - `--type-<role>-weight: 700|400`

   The role name is hyphenated the same way (`display_xl` →
   `--type-display-xl-size`). Point sizes stay pt.
3. **The active `DensityProfile`'s fields except `type_overrides`**, named the
   same mechanical way, with `int` values in px (`--control-height: 32px`,
   `--row-height`, `--padding-v`, `--padding-h`).

   `control_content_height` is a property that compensates for Qt's box
   model. The web tier uses `box-sizing: border-box` and does not need it, so
   it is not exported.

**The assertion.** After step 1, if any name in `_COLOR_FIELDS` minus the
aliases is missing from the output, raise `AssertionError`. It is raised
explicitly, not with an `assert` statement, so it survives `-O`.

**Repaint inputs.** A theme toggle and a density change both announce through
`shared.theme.theme_notifier.changed`. For density, see
`gui/theme_manager.py:118`. So one `on_theme_changed` subscription refreshes
colours and type together.

## 4. Web-asset rules in `shared/style_lint.py` (9.11)

**Web asset:** a `.css`, `.html` or `.js` file.

- `.css` and `.html` are the brief.
- `.js` is added, because a hex written into a script leaks exactly as it
  would from a stylesheet.

The printed-label templates live under `shopify_tool/`. Neither repo's guard
scope includes them, so they stay out of scope.

- `find_style_literals` walks `*.py` **and** web assets in a directory, and
  dispatches an explicit file by suffix.
- **Comments are blanked before scanning, keeping newlines**, so a finding
  reports its real line. The comment forms blanked:
  - `/* … */` in all three types;
  - `<!-- … -->` in HTML;
  - `//` to end of line in `.js`/`.html`, but only at line start or after
    whitespace, so `qrc:///…` survives.
- `# style-lint: allow` becomes `style-lint: allow` anywhere on the finding's
  raw line, typically inside a comment.
- **Rules on a web asset:**
  - The existing `hex`, `css-name`, `css-func` and `px-font`.
  - **`banned`:** `box-shadow`, `transition` and `transition-*`, `transform`
    and the individual `scale`/`rotate`/`translate`, `opacity`, the
    `(repeating-)linear|radial|conic-gradient(` functions, each also with a
    `-webkit-`/`-moz-`/`-ms-`/`-o-` prefix; the JS spellings
    `.style.boxShadow|transition*|transform|scale|rotate|translate|opacity`
    (vendor-prefixed too) and `style.setProperty('<banned>', …)`.
    - A property only matches when not preceded by `-` or a word character
      (a vendor prefix aside), so `text-transform` and `fill-opacity` stay
      clean.
    - The prefixes and individual transforms were added at Stage C review:
      without them `-webkit-box-shadow` and `scale:` passed, and ADR 0001 bans
      the effect, not one spelling of it.
    - `opacity` is banned outright. QSS has no per-element opacity, so there
      is no container it could legitimately match.
  - **`alias`:** `var(--<alias>)` for any frozen alias, hyphenated. Aliases
    are not exported (§3), so such a `var()` resolves to nothing and paints
    transparent without a sound.
- **`_HEX` gains `(?<!&)`**, so a numeric character reference such as
  `&#169;` is not a colour. It is harmless for `.py`.

**Known ceiling:** `css-name` scans to the next `;`. A declaration missing its
semicolon can run into `white-space` on the next rule and report `white`.
Always terminate declarations.

## 5. The bridge (9.12)

### 5.1 Protocol rules — binding on Track W

1. **One object**, registered on the channel as `results`.
2. **One member per message.** No member takes a string that selects
   behaviour (`invoke("addTag", …)` is forbidden).
3. **Arguments and property values are JSON-native:** str, int, float, bool,
   None, list, dict.
4. **State that Python owns crosses as a notify `Property`.** QWebChannel
   hands its current value to the page when the channel connects, so a page
   that connects late needs no handshake (verified by probe, §7).
5. **What JS reports crosses as a `Slot`** returning nothing. Results come
   back as property changes, never as return values.
6. **Channel members are camelCase**, because JS calls them. The
   Python-facing API is snake_case.
7. **Python listens to Python-facing signals** (`selectionChanged`). JS never
   connects to those, so a selection cannot echo back into the page.

### 5.2 The catalogue

Names and signatures are fixed now. The owning bundle's Stage A may amend one
only with a recorded reason. Bundle 11 implements the first three rows and
nothing else.

| Dir | Member | Kind | Bundle |
|---|---|---|---|
| out | `orders: list[order]` | property | **11** |
| out | `themeCss: str` | property | **11** |
| in | `setSelection(orderNumbers: list[str])` | slot | **11** |
| ~~in~~ | ~~`setSort`, `setFilterText`, `setFilterChips`~~ | removed | 12 — no Python consumer, the page owns view state (ADR 0005) |
| out | `summary: dict` | property | 12 (9.13) |
| out | `exportEnabled: bool` | property | 12 (9.13) |
| out | `focusSearchRequested()` | signal | 12 (9.13) |
| in | `openExport()` | slot | 12 (9.13) — canvas W3 puts Export in the document |
| in | `openScreenMenu()` | slot | 12 (9.13) |
| ~~out~~ | ~~`columns: list[{name, visible, pinned}]`~~ | removed | amended by Bundle 13 spec §4 |
| ~~in~~ | ~~`setColumnVisible(name: str, visible: bool)`~~ | removed | amended by Bundle 13 spec §4 |
| out | `columns: dict` | notify property | 13 (9.16) — `{"order", "visible", "auto_hide_empty", "extras"}` |
| out | `tagCategories: dict` | notify property | 13 (9.16) |
| in | `holdOrder(orderNumber: str)` | slot → `holdRequested(str)` | 13 (9.14) |
| in | `fulfillOrder(orderNumber: str)` | slot → `fulfillRequested(str)` | 13 (9.14) |
| in | `excludeOrder(orderNumber: str)` | slot → `excludeRequested(str)` | 13 (9.14) |
| in | `removeLine(orderNumber: str, lineIndex: int, sku: str)` | slot → `lineRemovalRequested(str, int, str)` | 13 (9.14) |
| in | `addOrderTag(orderNumber: str, tag: str)` | slot → `tagAddRequested(str, str)` | 13 (9.14) |
| in | `removeOrderTag(orderNumber: str, tag: str)` | slot → `tagRemovalRequested(str, str)` | 13 (9.14) |
| in | `copyText(text: str)` | slot, handled in the bridge | 13 (9.14) |
| in | `setColumnOrder(names: list[str])` | slot | 13 (9.16) |
| in | `setVisibleColumns(names: list[str])` | slot | 13 (9.16) |
| in | `resetColumns()` | slot | 13 (9.16) |
| in | `setAutoHideEmpty(on: bool)` | slot | 13 (9.16) |
| in | `addTag(orderNumbers: list[str], tag: str)` | slot | 14 (9.17) |
| in | `removeTag(orderNumbers: list[str], tag: str)` | slot | 14 (9.17) |
| in | `excludeOrders(orderNumbers: list[str])` | slot | 14 (9.17) |
| in | `undo()` | slot | 14 (9.17) |
| out | `undoAvailable: bool` | property | 14 (9.17) |
| out | `toastRaised(message: str, undoable: bool)` | signal | 14 (9.17) |

9.14 names its own pane verbs, because the pane's action set is its brief.
Export was first kept off the bridge; Bundle 12 moved it into the document per canvas W3.

### 5.3 `order_payload(df)`

It lives in `gui/orders_view.py`, beside `orders_frame`, because all order
folding is kept in one module.

```python
def order_payload(df: pd.DataFrame) -> list[dict]
```

- One dict per row of `orders_frame(df)`, in its row order. `[]` for
  `None`/empty/no `Order_Number`.
- The order-level columns appear once, under their internal names, including
  the derived `Items`, `Blocker` and the repeat flag. `SEARCH_COLUMN` is
  dropped: it is the Qt filter proxy's helper, and 9.13 decides how the web
  tier filters.
- `"lines"`: that order's line-level columns (from `classify_columns`), one
  dict per line, in frame order. Built with **one** `groupby`, not
  `order_lines()` once per order.
- **Every value is made JSON-native:**
  - `None`, `NaN`, `NaT` and `pd.NA` become `None`;
  - a non-finite float becomes `None`;
  - numpy scalars become Python scalars;
  - datetimes become ISO strings;
  - lists and dicts are converted recursively;
  - anything else becomes `str()`.

  `json.dumps(payload, allow_nan=False)` must succeed.
- No display mapping and no 9-column view. That is 9.13's.

### 5.4 The page and its mount

- **`gui/web/results.html`** — a shell holding:
  - `<style id="theme-vars">/* theme-vars */</style>`;
  - a link to `results.css`;
  - `qrc:///qtwebchannel/qwebchannel.js`;
  - `results.js` (deferred);
  - an empty `<main id="results">`.
- **`gui/web/results.css`** — `@font-face` for Inter Regular and Bold at
  `../../shared/assets/fonts/`. That relative path holds both in the dev tree
  and in the `--onedir` build, where `gui/web` and `shared/assets` both sit
  under `_internal/`. Then the body: `surface` background, `text` colour,
  `--font-family`, `--type-body-size`, tabular numerals. Tokens only.
- **`gui/web/results.js`** — connects the channel and sets `#theme-vars` from
  `themeCss`, then again on `themeCssChanged`. It exposes
  `window.resultsBridge` and sets `data-bridge="ready"` on `<html>`. No
  rendering; 9.13 builds the document here.
- **`mount_results_page(view: QWebEngineView) -> ResultsBridge`**:
  1. Creates the bridge and a `QWebChannel`, both parented to `view`, and
     registers the bridge as `results`.
  2. Subscribes with `on_theme_changed(view, …)`. Each call sets `themeCss`
     from `theme_css_vars(get_theme_manager().get_current_theme())`: the
     manager's tokens, which carry the bundled Inter family.
  3. Loads the page with `setHtml`, with the marker replaced by that CSS, so
     the first paint is already themed, and a `file://` base URL at
     `gui/web/`.

  **Not mounted anywhere in the app in this bundle.** 9.13 mounts it.

## 6. Build and CI

- `pyinstaller … --add-data "gui/web;gui/web"`, and add `results.html` to the
  "Verify bundled assets shipped" loop.
- `verify` job apt line gains: `libnss3 libnspr4 libxcomposite1 libxdamage1
  libxrandr2 libxkbfile1 libxtst6 libxkbcommon0 libgbm1 libasound2t64
  libxcb-dri3-0`.
- `tests/conftest.py` sets `QTWEBENGINE_DISABLE_SANDBOX=1` via `setdefault`
  before anything imports QtWebEngine. The runner's AppArmor blocks the
  unprivileged user namespaces Chromium's sandbox needs. This is test-only;
  the app does not set it.
- If Chromium still will not start on the runner, **Stage B reports it**. The
  bridge tests are never marked skip.

## 7. Evidence (throwaway probes, deleted)

Three probes ran on the dev box with `QT_QPA_PLATFORM=offscreen`, and all
passed:

1. **Round-trip:** a JS `setSelection` reached a Python slot as a `list`; a
   nested list-of-dicts signal arrived as JS arrays and objects; a CSS custom
   property set from Python changed `getComputedStyle`. 0.56s end to end.
2. **Page loading:**
   - a `Property("QVariantList", notify=…)` is readable in JS at channel init
     and updates on notify;
   - `setHtml` with a `file://` base URL still loads
     `qrc:///qtwebchannel/qwebchannel.js`;
   - `@font-face` from a file URL works.
3. **Import order:** importing `QtWebEngineWidgets` *after* a `QApplication`
   exists still loads a page. The conftest needs no import-order hack.

## 8. Not in this bundle

- Mounting the page in the main window, any visible document, and any
  catalogue member beyond the three.
- Label templates and their font.
- Deleting `gui/webengine_gate.py`. Its question is answered (ADR 0001), and
  removing it is a cleanup of its own.

## 9. Departures from the brief, all recorded

| Brief | This design | Why |
|---|---|---|
| Swap `templates/assets/fonts/` to Consolas | Labels untouched | Premise wrong; repo owner's decision (§2.1) |
| Linter scans `.css`, `.html` | Also `.js`; also `var(--alias)`; `&#NNN;` is not a hex | Same leak, a silent-transparent failure, a false positive |
| Bridge carries the full In/Out list | Catalogue fixed, three members built | Nothing ships without a caller; 9.17 rewrites the bulk handlers anyway (repo owner's decision) |
| — | Inter `@font-face` in the page | Chromium cannot see Qt-registered fonts (§2.4) |
| — | CI installs Chromium's runtime libs | The round-trip must run on PRs (repo owner's decision) |
