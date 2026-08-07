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
    text (the label prints its own caption), via python-barcode's SVG writer."""

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
  label:value rows, calling `{{ label_tools.barcode(item.order_number) }}` for the code and
  `{{ label_tools.fit_font_block(item.tag, ...) }}` for the tag field instead of the current
  manual pixel positions, six graduated font sizes, and truncate-with-ellipsis. Note: `blabel`
  passes each page's records to the template as an `items` list (length `items_per_page`,
  which P-3 sets to 1) — fields are `item.field`, not flat top-level variables, even though
  each page holds exactly one label.
- `qr_label/`: order number as large text, `{{ label_tools.qr_code(item.qr_payload) }}` below
  it — same content D-4 already specified, now rendered via template instead of Python
  `QrCodeWidget` drawing calls. Same `items`-list convention as above.
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
call — no per-order Python loop, no PNG files ever created. `items_per_page=1` is what makes
each PDF page one label (see P-2's `items`-list note).

**Wiring** (`gui/barcode_generator_widget.py`, `_generate_barcodes_worker`): builds the
`orders` list (already collects this data today; currently feeds it into per-order PIL
calls) and calls the two functions above instead of the old per-order-then-composite flow.
No change to D-3's UI decisions (PDF-only, no PNG checkbox) — this implementation has no PNG
step to clean up at all, which is simpler than D-3 assumed ("PNGs remain an internal
implementation detail... always cleaned up after the PDF is built").

### P-4: Font bundling

JetBrains Mono, matching `barcode_tool` exactly — same font, same `fit_font_block()`
character-width math (`_MONO_CHAR_WIDTH = 0.6`), no new measurement logic needed. Font files
live under `shopify_tool/templates/assets/fonts/` and must be added to the PyInstaller spec's
data files alongside the templates themselves (both are new categories of bundled non-Python
assets this app didn't have before).

<!-- ponytail: a missing bundled font or WeasyPrint native dep doesn't always crash — a
missing @font-face file falls back to a default font silently. Mitigated by the CI check in
Testing below, not by runtime error handling (there's nothing to catch). -->

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
  within `[min_mm, max_mm]` and actually shrinks for longer text.
- **CI**: extend the existing headless smoke test in `.github/workflows/build_release.yml` to
  render one real label PDF from the **PyInstaller-built** package, not just the dev
  environment — this is the check that actually catches "works on my machine, breaks in the
  packaged `.zip`," the exact risk class that made WeasyPrint-on-Windows a concern in the
  first place. A missing bundled font also only shows up this way (see P-4's ponytail note),
  not via any runtime exception.
- **Manual QA** (unautomatable, matches D-4's existing testing section): print a real batch
  to the physical Citizen CL-E300; confirm the scanner reads the new vector Code-128 as
  reliably as today's raster one.

## Files touched

- `shopify_tool/label_tools.py` — new
- `shopify_tool/templates/barcode_label/{template.html,style.css}` — new
- `shopify_tool/templates/qr_label/{template.html,style.css}` — new
- `shopify_tool/templates/assets/fonts/{fonts.css,*.ttf}` — new
- `shopify_tool/barcode_processor.py` — delete PIL/reportlab rendering code, add
  `generate_code128_labels_pdf()` / `generate_qr_labels_pdf()`
- `gui/barcode_generator_widget.py` — `_generate_barcodes_worker` calls the new functions
- `requirements.txt` — add `blabel`, `qrcode`
- PyInstaller spec — add templates dir + font files as bundled data
- `.github/workflows/build_release.yml` — extend smoke test to render a label post-build
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
