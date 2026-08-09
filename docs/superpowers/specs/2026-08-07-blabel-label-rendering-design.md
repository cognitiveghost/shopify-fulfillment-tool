# Blabel-Based Label Rendering — Design (patch on Phase 4 D-4)

## Problem

`docs/superpowers/specs/2026-07-30-label-barcode-system-design.md` (D-4) already redesigned
the Barcode Generator's Code-128 label layout and added an optional QR label, but kept the
existing rendering technology: `python-barcode` + PIL `ImageDraw` (hand-tuned pixel x/y
positions, six font sizes, manual text truncation) composited via `reportlab` canvas, plus a
vector `reportlab.graphics.barcode.qr.QrCodeWidget` for the new QR label. That plan hasn't
been implemented yet (still on branch `phase4-con`).

Since writing that plan, the user has proven a template-based alternative in a sibling
project, `cognitiveghost/barcode_tool`: labels rendered from HTML/Jinja2 templates via
`blabel`, with barcodes and QR codes as vector SVG (not raster), auto-shrinking text instead
of truncating it, and PyInstaller `--onedir` packaging already solving `blabel`'s WeasyPrint
native-dependency risk on Windows in production. This patch supersedes D-4's rendering
approach with that pattern, adapted to this app's constraints (see Non-goals).

This is a **patch to D-4 only** — D-1 (shared print helper), D-2 (Reference Labels barcode
overlay), and D-3 (Barcode Generator window decluttering) from the 2026-07-30 plan are
unchanged and unaffected.

## Goals

1. Replace `barcode_processor.py`'s PIL pixel-compositing and D-4's reportlab-vector QR
   drawing with `blabel` HTML/Jinja2 templates, one for the Code-128 label and one for the
   QR label.
2. Render barcodes and QR codes as vector SVG (via ported helpers from `barcode_tool`), not
   raster — sharper on the physical label, and removes the current PIL font-hunting/fallback
   chain and manual text-truncation logic.
3. Render the whole batch directly to the output PDF in one `blabel` call per label type —
   no PNG intermediates, no raster/DPI-thresholding step, since nothing downstream needs raw
   pixels (see Non-goals: QPrinter-only).
4. Bundle a font (JetBrains Mono, matching `barcode_tool`) with the app instead of relying on
   Arial/DejaVu being present on the target machine.

## Non-goals

- **Reference Labels overlay** (`pdf_processor.py`'s `create_reference_overlay()`, D-2).
  Different job — overlaying a small barcode onto an existing courier-provided PDF page,
  not generating a fresh label. `blabel` generates whole PDFs from templates; it doesn't fit
  an overlay-onto-an-existing-page job. D-2 stays on `reportlab` (with `pypdf` → `pikepdf`,
  independent of this patch).
- **Raw ZPL printing.** `barcode_tool` supports both driver printing (`QPrinter`) and raw
  ZPL (`zebrafy` + `win32print`, bypassing the OS driver). This patch keeps D-1's
  `QPrinter`-only path (`gui/pdf_printing.py`, zero new deps for printing). Revisit only if
  the Citizen CL-E300 is confirmed to support raw ZPL and there's an actual need to bypass
  the driver — not assumed here.
  <!-- ponytail: no raw-ZPL path; add one if QPrinter driver printing turns out to be the
  bottleneck or the printer needs to be shared over a raw network port -->
- **Rasterizing to a bilevel image at printer DPI**, and the `pypdfium2` dependency that
  requires. `barcode_tool` rasterizes because its ZPL path needs raw pixels; this app's print
  path (D-1) consumes PDFs directly via `QPdfDocument`/`QPrinter`, so nothing needs raster
  pixels. Keeping the whole pipeline vector end-to-end is strictly higher quality (no
  DPI-dependent thresholding step at all) and needs one fewer dependency.
- **Externalizing templates to the shared file server.** `barcode_tool` seeds
  `template.html`/`style.css`/`meta.json` into a user-configurable network folder so
  multiple warehouse PCs can customize labels without a code change. This app's templates
  stay app-bundled and static, matching the current hardcoded-in-code design. Revisit only
  if a real per-warehouse customization need shows up — not assumed here.
- **The QR/Code-128 physical-separation rule** (D-4 non-goal, unchanged): QR still never
  shares a physical label with the Code-128 barcode — a handheld scanner near two adjacent
  codes risks picking up the wrong one.
- **Threaded/background printing** (D-1 non-goal, unchanged): printing stays synchronous on
  the main thread.
- **`label_width_mm`/`label_height_mm` as function parameters.** Confirmed via `grep` that
  neither is ever called with a non-default value anywhere in this codebase (production code
  or tests). Dead flexibility — `68mm × 38mm` moves into `style.css`'s `@page` rule as the
  single source of truth instead of being threaded through two Python function signatures.

## Design

### P-1: `shopify_tool/label_tools.py` — vector rendering helpers (new module)

Ported from `barcode_tool`'s `app/core/label_tools.py`, trimmed to only what this app's two
label types need:

```python
def barcode(data: str, **writer_options) -> str:
    """Vector Code-128 barcode as an <img src=...> SVG data URI, no human-readable
    text (the label prints its own caption). Thin wrapper around blabel's own
    built-in blabel.label_tools.barcode(data, fmt="svg", write_text=False,
    **writer_options) — verified working for alphanumeric Code-128 data
    (order numbers containing '#'/'-' render correctly; the function's
    internal .zfill(constructor.digits) call is a no-op for Code128, whose
    `digits` class attribute is 0)."""

def qr_code(data: str, border: int = 2, **qr_code_params) -> str:
    """Vector QR code as an <img src=...> SVG data URI, via qrcode's SvgPathImage."""

def fit_font_block(
    text: str, box_width_mm: float, box_height_mm: float,
    max_mm: float, min_mm: float = 2.0, line_height: float = 1.25,
) -> float:
    """Largest font size (mm) at which wrapped `text` still fits the box.
    Assumes a monospace font (JetBrains Mono) for the cheap character-count
    width estimate — see P-4."""
```

Not ported: `datamatrix`, `hiro_square`, `pil_to_html_imgdata` (other label modes
`barcode_tool` supports that this app doesn't need), `now` (unused here).

New dependency: `qrcode` (SVG image factory). `python-barcode` and `Pillow` are already
installed — `python-barcode`'s SVG writer is a different code path than the `ImageWriter`
raster path currently used, no new package.

### P-2: Templates (new, app-bundled, static)

```
shopify_tool/templates/barcode_label/{template.html, style.css}
shopify_tool/templates/qr_label/{template.html, style.css}
shopify_tool/templates/assets/fonts/{JetBrains Mono files, fonts.css}
```

- `barcode_label/`: Jinja2 template laying out the label as a CSS grid — the same fields the
  current PIL code draws (seq#, courier, date, item count, country, tag, order number) as
  label:value rows, calling `{{ label_tools.barcode(order_number) }}` for the code and
  `{{ label_tools.fit_font_block(tag, ...) }}` for the tag field instead of the current
  manual pixel positions, six graduated font sizes, and truncate-with-ellipsis. Verified
  against the installed `blabel==0.1.7`: `LabelWriter.record_to_html()` renders the item
  template **once per record**, passing each record's dict keys as flat top-level template
  variables (`context.update(record)` before `.render(**context)`) — so fields are
  `{{ order_number }}` directly, not wrapped in an `items` list, regardless of
  `items_per_page`. (An earlier draft of this spec claimed the opposite; corrected after
  actually running `LabelWriter.write_labels()` against a 2-record batch during
  implementation-plan verification.)
- `qr_label/`: order number as large text, `{{ label_tools.qr_code(qr_payload) }}` below it —
  same content D-4 already specified, now rendered via template instead of Python
  `QrCodeWidget` drawing calls. Same flat-field convention as above.
- Both `style.css` files set `@page { size: 68mm 38mm; margin: 0 }` (page size lives here
  now, not in Python — see Non-goals).
- `fonts.css` declares `@font-face` for JetBrains Mono, referenced by both label stylesheets.
  Bundling the font removes the current `load_font()` fallback chain (Arial → DejaVu → PIL
  default) entirely — the font is guaranteed present because it ships with the app.

### P-3: `barcode_processor.py` — replace PIL/reportlab with blabel calls

**Deleted:** `load_font()`, `_clamp_text_to_width()`, the `ImageWriter._paint_text` monkeypatch,
all PIL/DPI pixel constants (`DPI`, `LABEL_WIDTH_PX`, `INFO_SECTION_WIDTH`, etc.),
`generate_barcode_label()`, `generate_barcodes_pdf()`, and D-4's reportlab-based
`generate_qr_labels_pdf()`.

**Kept unchanged:** `sanitize_order_number()`, `format_tags_for_barcode()` — pure data-prep,
still needed as the record-building step before handing data to the template. The
`country`/`tag` "N/A" fallback logic (currently inline in `generate_barcode_label()`) moves
into the new record-building step, same behavior, relocated.

**New:**

```python
def generate_code128_labels_pdf(orders: list[dict[str, Any]], output_pdf: Path) -> Path:
    """Render one Code-128 label per order as a single multi-page PDF.

    Each order dict: order_number, sequential_num, courier, country, tag,
    item_count. Raises ValueError if orders is empty, BarcodeGenerationError
    if rendering fails.
    """

def generate_qr_labels_pdf(orders: list[dict[str, Any]], output_pdf: Path) -> Path:
    """Render one QR label per order as a single multi-page PDF.

    Each order dict: order_number, sku_qty_lines. Same signature D-4 already
    specified; reportlab QrCodeWidget replaced by the qr_label template.
    """
```

Both build a `list[dict]` of records (sanitizing/formatting via the kept functions above),
then a single `blabel.LabelWriter(template_path, default_stylesheets=(fonts_css, style_css),
items_per_page=1, label_tools=label_tools).write_labels(records, target=str(output_pdf))`
call — no per-order Python loop, no PNG files ever created. `items_per_page=1` (blabel's own
default) is what makes each PDF page one label.

**Wiring** (`gui/barcode_generator_widget.py`, `_generate_barcodes_worker`): builds the
`orders` list (already collects this data today; currently feeds it into per-order PIL
calls) and calls the two functions above instead of the old per-order-then-composite flow.
With no PNG artifact ever produced, `generate_png_checkbox` and `generate_pdf_checkbox`
(currently letting the user choose PNG-only/PDF-only/both) become structurally meaningless —
this patch removes both, PDF becomes the unconditional output. This mechanically implements
the narrow "no PNG, PDF isn't optional" slice of D-3's already-decided end state for just
these two controls; D-3's other UI changes (info label removal, auto-open-folder→Print button
swap, "Add QR labels" checkbox, Print buttons themselves) are untouched — still D-3's job.

### P-4: Font bundling

JetBrains Mono, matching `barcode_tool` exactly — same font, same `fit_font_block()`
character-width math (`_MONO_CHAR_WIDTH = 0.6`), no new measurement logic needed. Font files
live under `shopify_tool/templates/assets/fonts/`.

<!-- ponytail: a missing bundled font or WeasyPrint native dep doesn't always crash — a
missing @font-face file falls back to a default font silently. Mitigated by the CI check in
P-5/Testing below, not by runtime error handling (there's nothing to catch). -->

### P-5: Windows packaging (verified against `barcode_tool`'s proven, shipping recipe)

This app's actual current release build (`.github/workflows/build_release.yml`) is
`pyinstaller --onefile --windowed gui_main.py`, shipping a single `.exe`. That is **not**
sufficient for WeasyPrint — `barcode_tool`'s working Windows build needed all of the
following, verified by reading its actual `release.yml` and `app/main.py` (not assumed):

1. **Runtime DLL-path setup** (`gui_main.py`, before `from gui.main_window_pyside import
   MainWindow` — that import chain reaches `barcode_processor.py`, which imports `blabel`):
   port `barcode_tool`'s `configure_frozen_weasyprint_env()` (calls
   `os.add_dll_directory(...)` pointing at a `gtk-dlls/` folder next to the frozen exe, only
   when `sys.frozen`) and `configure_windows_fontconfig_env()` (best-effort `FONTCONFIG_PATH`,
   never overrides an existing value).
2. **CI `verify` job** (Linux, already runs `pytest`): add the Pango/Cairo/GDK-Pixbuf system
   packages WeasyPrint needs to import at all
   (`libpango-1.0-0 libcairo2 libgdk-pixbuf-2.0-0`, alongside the `libegl1` this job already
   installs for Qt).
3. **CI `build` job rewrite**: `--onefile` → `--onedir --noconfirm`, add
   `--add-data "shopify_tool/templates;shopify_tool/templates"` and `--collect-data blabel`
   (blabel ships its own package data — needed regardless of our custom templates). Add an
   MSYS2 step (`C:\msys64\usr\bin\pacman.exe -S --noconfirm --needed
   mingw-w64-x86_64-pango`) — GitHub's `windows-latest` runner image ships MSYS2
   pre-installed at `C:\msys64`, confirmed by `barcode_tool`'s workflow using it with no
   separate MSYS2-install step. Then copy `C:\msys64\mingw64\bin` into
   `dist\<name>\gtk-dlls\` before packaging.
4. **Release artifact changes shape**: a `.zip` of the onedir folder, not a single `.exe`.
   This is a real, user-facing change to how warehouse PCs receive updates — extract-and-run
   instead of download-and-run-one-file. Flagged explicitly; not treated as an internal-only
   CI detail.
5. **Known WeasyPrint/pytest gotcha** (`barcode_tool` hit this in production CI): Pango's
   font-map cache carries state across renders within the same process. A test asserting the
   bundled font is actually applied can pass in isolation but segfault the process once
   enough prior WeasyPrint renders have accumulated state in the same `pytest` run. Mitigation
   (matching `barcode_tool`): run any such font-identity-asserting test in its own `pytest -k`
   invocation, separate from the rest of the suite.

## Testing

Per `AGENTS.md`: `QT_QPA_PLATFORM=offscreen python -m pytest` and `ruff check . --exclude
shared` must pass before merge.

- Extend `tests/test_barcode_processor.py`: `generate_code128_labels_pdf()` /
  `generate_qr_labels_pdf()` — smoke test (valid orders → PDF with page count equal to order
  count, non-trivial file size, no exception), empty-orders `ValueError`.
  `sanitize_order_number()` / `format_tags_for_barcode()` — no behavior change, existing
  tests should pass unmodified.
- New `tests/test_label_tools.py`: `barcode()` / `qr_code()` return well-formed SVG data-URI
  strings without raising, for typical order numbers and edge cases (very long order number,
  special characters surviving `sanitize_order_number()`). `fit_font_block()` returns a value
  within `[min_mm, max_mm]` and actually shrinks for longer text. Any test asserting the
  bundled font was actually used (not a fallback) is isolated per P-5 point 5.
- **CI**: the `build` job (P-5) now produces a real onedir Windows package with the bundled
  templates/fonts/GTK DLLs — that build succeeding *is* the check that catches "works on my
  machine, breaks in the packaged build," the risk class that made WeasyPrint-on-Windows a
  concern in the first place. A missing bundled font doesn't crash (falls back silently, see
  P-4's ponytail note) — only a real print/render smoke test on the built package would catch
  that; not added here (no Windows runner available for an interactive smoke test beyond what
  PyInstaller itself already validates at build time), tracked as a Follow-up.
- **Manual QA** (unautomatable, matches D-4's existing testing section): print a real batch
  to the physical Citizen CL-E300; confirm the scanner reads the new vector Code-128 as
  reliably as today's raster one. Also confirm the new `.zip` distribution extracts and runs
  correctly on a real warehouse PC.

## Files touched

- `shopify_tool/label_tools.py` — new
- `shopify_tool/templates/barcode_label/{template.html,style.css}` — new
- `shopify_tool/templates/qr_label/{template.html,style.css}` — new
- `shopify_tool/templates/assets/fonts/{fonts.css,*.ttf}` — new
- `shopify_tool/barcode_processor.py` — delete PIL/reportlab rendering code, add
  `generate_code128_labels_pdf()` / `generate_qr_labels_pdf()`
- `gui/barcode_generator_widget.py` — `_generate_barcodes_worker` calls the new functions,
  `generate_png_checkbox`/`generate_pdf_checkbox` removed
- `gui_main.py` — add `configure_frozen_weasyprint_env()` /
  `configure_windows_fontconfig_env()`, called before `MainWindow` import
- `requirements.txt` — add `blabel`, `qrcode`
- `.github/workflows/build_release.yml` — `verify` job gets WeasyPrint's Linux system deps;
  `build` job rewritten: `--onefile`→`--onedir`, MSYS2 Pango install, `--add-data`/
  `--collect-data blabel`, GTK DLL bundling, `.zip` artifact instead of renamed `.exe`
- `tests/test_barcode_processor.py` — extended
- `tests/test_label_tools.py` — new

## Relationship to D-2/D-3 (2026-07-30 plan, unchanged by this patch)

D-1 (`gui/pdf_printing.py` shared print helper), D-2 (Reference Labels history removal +
reportlab/pikepdf barcode overlay), and D-3 (Barcode Generator window decluttering — remove
info label, PNG/PDF choice, auto-open-folder checkbox; add auto-open-PDF checkbox, "Add QR
labels" checkbox, Print buttons) proceed exactly as specified in the 2026-07-30 plan. This
patch only changes *how* D-4's redesigned Code-128 label and new QR label get rendered, not
the surrounding window/workflow changes D-1–D-3 already specified.

## Follow-ups (not in this patch's scope)

- Raw ZPL printing (`zebrafy` + `win32print`) — revisit if the Citizen CL-E300 is confirmed
  to support it and driver printing becomes a real bottleneck.
- Template externalization to the shared file server, for per-warehouse customization —
  revisit if that need actually materializes.
- If a future courier or label size needs different dimensions, the `@page` rule in each
  template's `style.css` is now the single place to change it.
- An actual print/render smoke test against the built Windows package (beyond PyInstaller
  succeeding) needs a Windows runner exercising the frozen exe — not added here.
- `barcode_tool`'s Windows build bundles the *entire* MSYS2 `mingw64/bin` tree rather than a
  hand-picked minimal DLL set (their own documented known limitation — bigger artifact than
  strictly necessary, but correct without manually tracing the dependency graph). Same
  trade-off adopted here for the same reason; revisit if artifact size becomes a problem.
