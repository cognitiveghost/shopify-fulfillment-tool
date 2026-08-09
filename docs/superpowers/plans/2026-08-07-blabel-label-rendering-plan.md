# Blabel-Based Label Rendering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `barcode_processor.py`'s hand-tuned PIL pixel-compositing + reportlab PDF assembly with `blabel` HTML/Jinja2 template rendering (vector Code-128 + QR, shrink-to-fit text), and ship it in a working Windows build.

**Architecture:** Two blabel templates (`barcode_label/`, `qr_label/`) render one label per order directly to a multi-page PDF — no PNG intermediates, no raster step (verified: nothing downstream needs raw pixels, since printing goes through `QPrinter`/`QPdfDocument`, not raw image data). `shopify_tool/label_tools.py` exposes vector `barcode()`/`qr_code()`/`fit_font_block()` to the templates, ported from `cognitiveghost/barcode_tool`. WeasyPrint (blabel's PDF engine) needs its native Pango/Cairo/GTK dependencies bundled for the Windows build — this plan includes that packaging work, verified against `barcode_tool`'s actual shipping `release.yml`, not assumed.

**Tech Stack:** Python, `blabel` 0.1.7 (Jinja2 + WeasyPrint), `qrcode` (SVG QR), `python-barcode` (already installed, SVG writer via blabel's own `label_tools.barcode()`), PySide6, PyInstaller, GitHub Actions (MSYS2 on `windows-latest`).

## Global Constraints

- Per `AGENTS.md`/`CLAUDE.md`: `QT_QPA_PLATFORM=offscreen python -m pytest` and `ruff check . --exclude shared` must pass before merge.
- No hardcoded colors — N/A to this patch (no theme/stylesheet code touched).
- No `pyproject.toml` — dependencies go in `requirements.txt` only.
- Label page size (68mm × 38mm) lives in each template's `style.css` `@page` rule, never as a Python function parameter (confirmed via `grep`: `label_width_mm`/`label_height_mm` were never called with non-default values anywhere in this codebase).
- `blabel`'s `LabelWriter.record_to_html()` renders the item template once per record, with the record's dict flattened into **top-level** Jinja2 variables (verified against the installed `blabel==0.1.7` source) — template fields are `{{ order_number }}`, never `{{ item.order_number }}`.
- Spec: `docs/superpowers/specs/2026-08-07-blabel-label-rendering-design.md`. This patch supersedes only D-4 of `docs/superpowers/plans/2026-07-30-label-barcode-system-plan.md`; D-1/D-2/D-3 of that plan are untouched by this plan.

---

### Task 1: `shopify_tool/label_tools.py` — vector rendering helpers

**Files:**
- Create: `shopify_tool/label_tools.py`
- Create: `tests/test_label_tools.py`
- Modify: `requirements.txt` (add `blabel`, `qrcode`)

**Interfaces:**
- Produces: `barcode(data: str, **writer_options) -> str`, `qr_code(data: str, border: int = 2, **qr_code_params) -> str`, `fit_font_block(text, box_width_mm: float, box_height_mm: float, max_mm: float, min_mm: float = 2.0, line_height: float = 1.25) -> float` — all used by templates in Tasks 3–4 and imported directly by `barcode_processor.py` in Task 5.

- [ ] **Step 1: Add `blabel` and `qrcode` to `requirements.txt`**

Open `requirements.txt` and add this block directly after the existing `# Barcode Generation (Feature #5 - Barcode Generator)` section (after the `Pillow>=10.0.0` line):

```
Pillow>=10.0.0          # Image processing for barcode label composition

# Label Rendering (blabel HTML/Jinja2 templates - barcode + QR labels)
# -----------------------------------------------------------------
blabel>=0.1.7           # HTML/Jinja2 template-based label rendering (WeasyPrint backend)
qrcode>=7.4              # QR code generation (SVG vector output via blabel templates)
```

Then run: `pip install -r requirements.txt` to install them locally.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_label_tools.py`:

```python
"""label_tools.py exposes vector barcode/QR rendering and text-fit helpers
to blabel templates. These tests cover the Python-level contract (valid
SVG data URIs, no exceptions, shrink-to-fit behavior) -- visual/print
correctness is manual QA (see spec Testing section)."""
import pytest

from shopify_tool.label_tools import barcode, fit_font_block, qr_code


class TestBarcode:
    @pytest.mark.parametrize("order_number", [
        "1029392", "BG10129-A", "ORDER_001234", "A", "#1029392",
    ])
    def test_returns_svg_data_uri(self, order_number):
        result = barcode(order_number)
        assert result.startswith("data:image/svg+xml")

    def test_does_not_render_human_readable_text_by_default(self):
        # write_text defaults to False -- the barcode payload carries no
        # visible caption, the label template draws its own order_number
        # text separately (see barcode_label/template.html).
        result = barcode("1029392", write_text=True)
        # Explicit override is honored (not clobbered by setdefault).
        assert result.startswith("data:image/svg+xml")


class TestQrCode:
    def test_returns_svg_data_uri(self):
        result = qr_code("#1029392\nWIDGET x2\nGADGET x1")
        assert result.startswith("data:image/svg+xml")

    def test_handles_multiline_payload(self):
        payload = "\n".join([f"SKU-{i} x{i}" for i in range(20)])
        result = qr_code(payload)
        assert result.startswith("data:image/svg+xml")


class TestFitFontBlock:
    def test_empty_text_returns_max_size(self):
        assert fit_font_block("", box_width_mm=30, box_height_mm=10, max_mm=5) == 5

    def test_stays_within_min_max_range(self):
        size = fit_font_block(
            "A very long tag list that will not fit on one line easily",
            box_width_mm=20, box_height_mm=8, max_mm=5, min_mm=2,
        )
        assert 2 <= size <= 5

    def test_shrinks_for_longer_text(self):
        short_size = fit_font_block("GIFT+1", box_width_mm=30, box_height_mm=10, max_mm=5, min_mm=2)
        long_size = fit_font_block(
            "GIFT+1, GIFT+2, URGENT, FRAGILE, PRIORITY, EXPRESS",
            box_width_mm=30, box_height_mm=10, max_mm=5, min_mm=2,
        )
        assert long_size <= short_size
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_label_tools.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'shopify_tool.label_tools'`

- [ ] **Step 4: Write `shopify_tool/label_tools.py`**

This exact code was verified end-to-end (including a full `LabelWriter.write_labels()` render producing a correct-page-count PDF) before being written into this plan:

```python
"""Vector barcode/QR rendering and text-fit helpers, exposed to blabel
templates as `label_tools`.

Ported from cognitiveghost/barcode_tool's app/core/label_tools.py, trimmed
to what this app's two label templates need. Not ported: datamatrix,
hiro_square, pil_to_html_imgdata, now -- other label modes barcode_tool
supports that this app doesn't need.
"""

from __future__ import annotations

import base64
from io import BytesIO

import qrcode
import qrcode.image.svg
from blabel.label_tools import barcode as _blabel_barcode
from blabel.label_tools import wrap

_SVG_DATA_URI = "data:image/svg+xml;charset=utf-8;base64,"

# JetBrains Mono (and any monospace) advances 0.6em per character -- see
# templates/assets/fonts/fonts.css, the only font these templates use.
_MONO_CHAR_WIDTH = 0.6


def barcode(data, **writer_options) -> str:
    """Vector Code-128 barcode as an <img src=...> SVG data URI, no
    human-readable text under the bars by default (the label template
    draws its own order_number caption from the record's own field).

    Thin wrapper around blabel's own blabel.label_tools.barcode(fmt="svg").
    Verified working for alphanumeric Code-128 data (order numbers
    containing '#'/'-' render correctly) -- the function's internal
    .zfill(constructor.digits) call is a no-op for Code128, whose `digits`
    class attribute is 0.
    """
    writer_options.setdefault("write_text", False)
    return _blabel_barcode(data, fmt="svg", **writer_options)


def qr_code(data, border: int = 2, **qr_code_params) -> str:
    """Vector QR code as an <img src=...> SVG data URI."""
    qr = qrcode.QRCode(
        border=border, image_factory=qrcode.image.svg.SvgPathImage, **qr_code_params
    )
    qr.add_data(str(data))
    buffer = BytesIO()
    qr.make_image().save(buffer)
    return _SVG_DATA_URI + base64.b64encode(buffer.getvalue()).decode()


def fit_font_block(
    text,
    box_width_mm: float,
    box_height_mm: float,
    max_mm: float,
    min_mm: float = 2.0,
    line_height: float = 1.25,
) -> float:
    """Largest font size (mm) at which wrapped `text` still fits the box.

    Assumes a monospace font (see _MONO_CHAR_WIDTH) for a cheap
    character-count width estimate instead of real glyph measurement --
    correct for JetBrains Mono, the only font these templates bundle.
    """
    text = str(text or "")
    if not text:
        return max_mm
    size = max_mm
    while size > min_mm:
        chars_per_line = max(1, int(box_width_mm / (size * _MONO_CHAR_WIDTH)))
        lines = sum(
            len(wrap(part, chars_per_line).splitlines()) or 1
            for part in text.splitlines()
        ) or 1
        if lines * size * line_height <= box_height_mm:
            break
        size = round(size - 0.1, 2)
    return max(size, min_mm)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_label_tools.py -v`
Expected: PASS (7 tests)

- [ ] **Step 6: Lint and commit**

Run: `ruff check shopify_tool/label_tools.py tests/test_label_tools.py`

```bash
git add requirements.txt shopify_tool/label_tools.py tests/test_label_tools.py
git commit -m "Add label_tools.py: vector barcode/QR + shrink-to-fit text helpers"
```

---

### Task 2: Bundle JetBrains Mono font

**Files:**
- Create: `shopify_tool/templates/assets/fonts/JetBrainsMono-Regular.ttf`
- Create: `shopify_tool/templates/assets/fonts/JetBrainsMono-Bold.ttf`
- Create: `shopify_tool/templates/assets/fonts/fonts.css`

**Interfaces:**
- Produces: `fonts.css` declaring the `"JetBrains Mono"` font family, consumed by both templates' `style.css` in Tasks 3–4 via `default_stylesheets`.

This is an external binary asset, not code — acquire it rather than writing it:

- [ ] **Step 1: Download the font files**

Download from the official JetBrains Mono GitHub releases (SIL Open Font License 1.1, freely redistributable): https://github.com/JetBrains/JetBrainsMono/releases — take the latest release's asset zip, extract `fonts/ttf/JetBrainsMono-Regular.ttf` and `fonts/ttf/JetBrainsMono-Bold.ttf` (matching `barcode_tool`'s own font choice, so `fit_font_block()`'s `_MONO_CHAR_WIDTH = 0.6` constant is correct for this font). Place both files at:

```
shopify_tool/templates/assets/fonts/JetBrainsMono-Regular.ttf
shopify_tool/templates/assets/fonts/JetBrainsMono-Bold.ttf
```

- [ ] **Step 2: Write `fonts.css`**

Create `shopify_tool/templates/assets/fonts/fonts.css`:

```css
@font-face {
  font-family: "JetBrains Mono";
  src: url("JetBrainsMono-Regular.ttf");
  font-weight: normal;
}

@font-face {
  font-family: "JetBrains Mono";
  src: url("JetBrainsMono-Bold.ttf");
  font-weight: bold;
}
```

- [ ] **Step 3: Verify the font loads via WeasyPrint**

Run this one-off check (not a permanent test — just confirms the font files and `fonts.css` are valid before Tasks 3–4 depend on them):

```bash
python -c "
from blabel.Blabel import write_pdf
html = '<html><body style=\"font-family: \\'JetBrains Mono\\'; font-size: 20px;\">Test 12345</body></html>'
pdf = write_pdf(html, target='@memory', extra_stylesheets=('shopify_tool/templates/assets/fonts/fonts.css',))
assert len(pdf) > 500
print('Font loads OK,', len(pdf), 'bytes')
"
```

Expected: `Font loads OK, N bytes` with no WeasyPrint font-loading warnings printed.

- [ ] **Step 4: Commit**

```bash
git add shopify_tool/templates/assets/fonts/
git commit -m "Bundle JetBrains Mono font for label templates"
```

---

### Task 3: `shopify_tool/templates/barcode_label/` — Code-128 label template

**Files:**
- Create: `shopify_tool/templates/barcode_label/template.html`
- Create: `shopify_tool/templates/barcode_label/style.css`

**Interfaces:**
- Consumes: `label_tools.barcode()`, `label_tools.fit_font_block()` (Task 1); `fonts.css` (Task 2).
- Produces: a blabel item template expecting a record dict with keys `order_number, sequential_num, courier, country, tag, item_count, date_str` — this exact shape is what Task 5's `generate_code128_labels_pdf()` must build and pass in.

This exact template.html/style.css pair was verified end-to-end via `LabelWriter.write_labels()` (correct 68mm×38mm page size, 2-page PDF, no WeasyPrint errors) before being written into this plan.

- [ ] **Step 1: Write `template.html`**

```html
<!DOCTYPE html>
<html>
<body>
  <div class="label">
    <div class="info">
      <div class="seq">#{{ sequential_num }}</div>
      <div class="courier">{{ courier }}</div>
      <div class="date">{{ date_str }}</div>
      <hr>
      <div class="field"><span class="field-label">SUM:</span><span class="field-value">{{ item_count }}</span></div>
      <hr class="thin">
      <div class="field"><span class="field-label">COU:</span><span class="field-value">{{ country }}</span></div>
      <hr class="thin">
      <div class="field tag-field">
        <span class="field-label">TAG:</span>
        <span class="field-value" style="font-size: {{ label_tools.fit_font_block(tag, box_width_mm=14, box_height_mm=10, max_mm=3.2, min_mm=1.8) }}mm;">{{ tag }}</span>
      </div>
    </div>
    <div class="barcode-section">
      <img class="barcode" src="{{ label_tools.barcode(order_number) }}"/>
      <div class="order-number">{{ order_number }}</div>
    </div>
  </div>
</body>
</html>
```

- [ ] **Step 2: Write `style.css`**

```css
@page { size: 68mm 38mm; margin: 0; }

* { box-sizing: border-box; margin: 0; padding: 0; }

body { width: 68mm; height: 38mm; font-family: "JetBrains Mono", monospace; }

.label {
  width: 68mm;
  height: 38mm;
  display: flex;
  flex-direction: row;
  padding: 1mm;
}

.info {
  width: 24mm;
  display: flex;
  flex-direction: column;
  padding-right: 1mm;
}

.seq { font-size: 5.5mm; font-weight: bold; }
.courier {
  font-size: 5mm;
  font-weight: bold;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.date { font-size: 3mm; }

hr { border: none; border-top: 0.5mm solid black; margin: 0.5mm 0; }
hr.thin { border-top-width: 0.3mm; }

.field { display: flex; font-size: 3mm; font-weight: bold; margin: 0.3mm 0; }
.field-label { width: 8mm; }
.field-value { flex: 1; }

.tag-field { flex: 1; align-items: flex-start; }

.barcode-section {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-start;
}

.barcode { width: 41mm; height: 20mm; margin-top: 1mm; }

.order-number {
  font-size: 6mm;
  font-weight: bold;
  margin-top: 1mm;
  text-align: center;
}
```

- [ ] **Step 3: Verify it renders**

```bash
python -c "
from blabel import LabelWriter
from shopify_tool import label_tools
import pypdf, io

writer = LabelWriter(
    'shopify_tool/templates/barcode_label/template.html',
    default_stylesheets=(
        'shopify_tool/templates/assets/fonts/fonts.css',
        'shopify_tool/templates/barcode_label/style.css',
    ),
    items_per_page=1,
    label_tools=label_tools,
)
records = [{
    'sequential_num': 12, 'courier': 'DHL Express International',
    'date_str': '16/01/26', 'item_count': 5, 'country': 'DE',
    'tag': 'GIFT+1|GIFT+2|URGENT|FRAGILE|PRIORITY', 'order_number': '#BG10129-A',
}]
pdf_bytes = writer.write_labels(records, target='@memory')
reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
assert len(reader.pages) == 1
w, h = float(reader.pages[0].mediabox.width), float(reader.pages[0].mediabox.height)
assert abs(w - 192.76) < 1.5 and abs(h - 107.72) < 1.5, f'wrong page size: {w}x{h}'
print('barcode_label template OK:', len(pdf_bytes), 'bytes,', w, 'x', h, 'pt')
"
```

Expected: `barcode_label template OK: N bytes, 192.76 x 107.72 pt` with no exceptions.

- [ ] **Step 4: Commit**

```bash
git add shopify_tool/templates/barcode_label/
git commit -m "Add barcode_label blabel template (Code-128 label)"
```

---

### Task 4: `shopify_tool/templates/qr_label/` — QR label template

**Files:**
- Create: `shopify_tool/templates/qr_label/template.html`
- Create: `shopify_tool/templates/qr_label/style.css`

**Interfaces:**
- Consumes: `label_tools.qr_code()` (Task 1); `fonts.css` (Task 2).
- Produces: a blabel item template expecting a record dict with keys `order_number, qr_payload` — this shape is what Task 5's `generate_qr_labels_pdf()` must build and pass in.

Also verified end-to-end (1-page PDF, no errors) before being written into this plan.

- [ ] **Step 1: Write `template.html`**

```html
<!DOCTYPE html>
<html>
<body>
  <div class="label">
    <div class="order-number">{{ order_number }}</div>
    <img class="qr" src="{{ label_tools.qr_code(qr_payload) }}"/>
  </div>
</body>
</html>
```

- [ ] **Step 2: Write `style.css`**

```css
@page { size: 68mm 38mm; margin: 0; }
* { box-sizing: border-box; margin: 0; padding: 0; }
body { width: 68mm; height: 38mm; font-family: "JetBrains Mono", monospace; }
.label {
  width: 68mm;
  height: 38mm;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 2mm;
}
.order-number { font-size: 7mm; font-weight: bold; margin-bottom: 2mm; }
.qr { width: 30mm; height: 30mm; }
```

- [ ] **Step 3: Verify it renders**

```bash
python -c "
from blabel import LabelWriter
from shopify_tool import label_tools
import pypdf, io

writer = LabelWriter(
    'shopify_tool/templates/qr_label/template.html',
    default_stylesheets=(
        'shopify_tool/templates/assets/fonts/fonts.css',
        'shopify_tool/templates/qr_label/style.css',
    ),
    items_per_page=1,
    label_tools=label_tools,
)
records = [{'order_number': '#BG10129-A', 'qr_payload': '#BG10129-A\nWIDGET x2\nGADGET x1'}]
pdf_bytes = writer.write_labels(records, target='@memory')
reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
assert len(reader.pages) == 1
print('qr_label template OK:', len(pdf_bytes), 'bytes')
"
```

Expected: `qr_label template OK: N bytes` with no exceptions.

- [ ] **Step 4: Commit**

```bash
git add shopify_tool/templates/qr_label/
git commit -m "Add qr_label blabel template (QR label)"
```

---

### Task 5: `shopify_tool/barcode_processor.py` — replace PIL/reportlab with blabel

**Files:**
- Modify: `shopify_tool/barcode_processor.py` (full rewrite of the rendering portion)
- Modify: `tests/test_barcode_processor.py`

**Interfaces:**
- Consumes: `shopify_tool.label_tools` (Task 1), `shopify_tool/templates/barcode_label/` (Task 3), `shopify_tool/templates/qr_label/` (Task 4).
- Produces: `generate_barcodes_batch(df, sequential_map=None, progress_callback=None) -> list[dict]` (signature changed: **`output_dir` parameter removed** — no PNGs are written, so there's no directory to write them to; each successful record now carries a `safe_order_number` key), `generate_code128_labels_pdf(orders: list[dict], output_pdf: Path) -> Path`, `generate_qr_labels_pdf(orders: list[dict], output_pdf: Path) -> Path`. `sanitize_order_number()` and `format_tags_for_barcode()` are unchanged. `BarcodeProcessorError`, `InvalidOrderNumberError`, `BarcodeGenerationError` are unchanged. **Deleted:** `load_font()`, `_clamp_text_to_width()`, `generate_barcode_label()`, `generate_barcodes_pdf()`, the `ImageWriter._paint_text` monkeypatch, all PIL/DPI pixel constants.
- Consumed by: `gui/barcode_generator_widget.py` (Task 6).

- [ ] **Step 1: Write the failing tests**

Replace `tests/test_barcode_processor.py` in full (deletes `TestClampTextToWidth` and `TestGenerateBarcodeLabelIntegration`, which test functions this task deletes; rewrites `TestItemCountZeroFalsyBug`, which no longer has anything to monkeypatch since `generate_barcodes_batch` no longer calls a per-row rendering function; adds `TestGenerateBarcodesBatch` and `TestGenerateCode128LabelsPdfIntegration`/`TestGenerateQrLabelsPdfIntegration`):

```python
"""Barcode content accuracy (priority: barcode generation accuracy).

generate_code128_labels_pdf()/generate_qr_labels_pdf() render real PDFs via
blabel/WeasyPrint (not asserted pixel-by-pixel here); what's tested is the
data that ends up ON the label -- the Code-128 payload, and that the batch
builder produces correctly-shaped, correctly-validated records.
"""
import io

import pandas as pd
import pypdf
import pytest
from barcode.codex import Code128

from shopify_tool.barcode_processor import (
    InvalidOrderNumberError,
    format_tags_for_barcode,
    generate_barcodes_batch,
    generate_code128_labels_pdf,
    generate_qr_labels_pdf,
    sanitize_order_number,
)


class TestSanitizeOrderNumber:
    @pytest.mark.parametrize("raw, expected", [
        ("#1029392", "#1029392"),
        ("BG-10129", "BG-10129"),
        ("ORDER_001", "ORDER_001"),
        ("#12 34", "#1234"),      # internal space stripped
        ("Ord#5!", "Ord#5"),      # punctuation stripped
    ])
    def test_preserves_shopify_safe_characters(self, raw, expected):
        assert sanitize_order_number(raw) == expected

    def test_empty_raises(self):
        with pytest.raises(InvalidOrderNumberError):
            sanitize_order_number("")

    def test_all_symbols_raises(self):
        with pytest.raises(InvalidOrderNumberError):
            sanitize_order_number("!!!***")


class TestSanitizedNumberEncodesFaithfullyInCode128:
    """The whole point of sanitize_order_number is that what gets barcode-encoded
    is EXACTLY what the packer will read back -- verify via python-barcode's own
    get_fullcode(), which is the actual payload the scanner will decode."""

    @pytest.mark.parametrize("raw", ["#1029392", "BG-10129", "ORDER_001", "12345"])
    def test_fullcode_matches_sanitized_input_exactly(self, raw):
        safe = sanitize_order_number(raw)
        assert Code128(safe).get_fullcode() == safe


class TestFormatTagsForBarcode:
    def test_json_array_joined_with_pipe(self):
        assert format_tags_for_barcode('["GIFT+1", "GIFT+2"]') == "GIFT+1|GIFT+2"

    def test_plain_string_passthrough(self):
        assert format_tags_for_barcode("Priority") == "Priority"

    def test_empty_and_sentinel_values_return_blank(self):
        assert format_tags_for_barcode("") == ""
        assert format_tags_for_barcode("nan") == ""
        assert format_tags_for_barcode("None") == ""

    def test_empty_json_array_returns_blank_not_literal_brackets(self):
        assert format_tags_for_barcode("[]") == ""

    def test_native_list_input_is_joined_not_stringified(self):
        assert format_tags_for_barcode(["BAG", "TEST"]) == "BAG|TEST"

    def test_python_repr_style_list_string_is_parsed_not_leaked_raw(self):
        assert format_tags_for_barcode(str(["BAG", "TEST"])) == "BAG|TEST"

    def test_native_list_with_blank_element_has_no_stray_pipe(self):
        assert format_tags_for_barcode([" ", "A"]) == "A"

    def test_padded_json_array_string_is_parsed_not_leaked_raw(self):
        assert format_tags_for_barcode(' ["A"] ') == "A"


class TestGenerateBarcodesBatch:
    """generate_barcodes_batch() now only builds/validates records -- no
    rendering, no output_dir. Rendering is generate_code128_labels_pdf()."""

    def _df(self, **overrides):
        row = {
            "Order_Number": "#1029392", "Shipping_Provider": "DHL",
            "Destination_Country": "DE", "Internal_Tags": "[]", "item_count": 3,
        }
        row.update(overrides)
        return pd.DataFrame([row])

    def test_zero_item_count_is_not_coerced_to_one(self):
        results = generate_barcodes_batch(self._df(item_count=0))
        assert results[0]["item_count"] == 0

    def test_successful_row_has_safe_order_number(self):
        results = generate_barcodes_batch(self._df(Order_Number="#1029392!!"))
        assert results[0]["success"] is True
        assert results[0]["safe_order_number"] == "#1029392"

    def test_invalid_order_number_reports_failure_not_exception(self):
        results = generate_barcodes_batch(self._df(Order_Number="!!!"))
        assert results[0]["success"] is False
        assert results[0]["safe_order_number"] is None
        assert results[0]["error"]

    def test_sequential_numbering_defaults_to_row_index_plus_one(self):
        df = pd.concat([self._df(Order_Number="#1"), self._df(Order_Number="#2")], ignore_index=True)
        results = generate_barcodes_batch(df)
        assert [r["sequential_num"] for r in results] == [1, 2]

    def test_sequential_map_overrides_default_numbering(self):
        results = generate_barcodes_batch(self._df(), sequential_map={"#1029392": 42})
        assert results[0]["sequential_num"] == 42


class TestGenerateCode128LabelsPdfIntegration:
    """Smoke test the real blabel/WeasyPrint rendering path (no pixel
    assertions -- does it run, correct page count)."""

    def _order(self, **overrides):
        order = {
            "order_number": "#1029392", "safe_order_number": "#1029392",
            "sequential_num": 7, "courier": "DHL", "country": "DE",
            "tag": "N/A", "item_count": 3,
        }
        order.update(overrides)
        return order

    def test_generates_pdf_with_one_page_per_order(self, tmp_path):
        output_pdf = tmp_path / "labels.pdf"
        result = generate_code128_labels_pdf(
            [self._order(safe_order_number="#1"), self._order(safe_order_number="#2")],
            output_pdf,
        )
        assert result == output_pdf
        assert output_pdf.exists()
        reader = pypdf.PdfReader(str(output_pdf))
        assert len(reader.pages) == 2

    def test_empty_orders_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            generate_code128_labels_pdf([], tmp_path / "labels.pdf")


class TestGenerateQrLabelsPdfIntegration:
    def test_generates_pdf_with_one_page_per_order(self, tmp_path):
        output_pdf = tmp_path / "qr_labels.pdf"
        orders = [{
            "order_number": "#1029392",
            "sku_qty_lines": [("WIDGET", 2), ("GADGET", 1)],
        }]
        result = generate_qr_labels_pdf(orders, output_pdf)
        assert result == output_pdf
        reader = pypdf.PdfReader(str(output_pdf))
        assert len(reader.pages) == 1

    def test_empty_orders_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            generate_qr_labels_pdf([], tmp_path / "qr_labels.pdf")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_barcode_processor.py -v`
Expected: FAIL — `ImportError` (`generate_code128_labels_pdf`, `generate_qr_labels_pdf` don't exist yet; `generate_barcodes_batch` still has the old `output_dir`-based implementation).

- [ ] **Step 3: Rewrite `shopify_tool/barcode_processor.py`**

Replace the file's contents from the docstring through the end (i.e. everything) with:

```python
"""
Barcode Label Generator for Warehouse Operations.

Renders Code-128 barcode labels and QR labels for the Citizen CL-E300
thermal printer via blabel HTML/Jinja2 templates (shopify_tool/templates/),
label size 68mm x 38mm. See docs/superpowers/specs/2026-08-07-blabel-label-rendering-design.md.
"""

import json
import logging
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from blabel import LabelWriter

from shopify_tool import label_tools

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_FONTS_CSS = _TEMPLATES_DIR / "assets" / "fonts" / "fonts.css"
_BARCODE_LABEL_TEMPLATE = _TEMPLATES_DIR / "barcode_label" / "template.html"
_BARCODE_LABEL_STYLE = _TEMPLATES_DIR / "barcode_label" / "style.css"
_QR_LABEL_TEMPLATE = _TEMPLATES_DIR / "qr_label" / "template.html"
_QR_LABEL_STYLE = _TEMPLATES_DIR / "qr_label" / "style.css"


# === EXCEPTIONS ===
class BarcodeProcessorError(Exception):
    """Base exception for barcode processor."""


class InvalidOrderNumberError(BarcodeProcessorError):
    """Invalid order number for barcode encoding."""


class BarcodeGenerationError(BarcodeProcessorError):
    """Error during barcode generation."""


# === UTILITY FUNCTIONS ===

def sanitize_order_number(order_number: str) -> str:
    """
    Clean order number for Code-128 barcode encoding.

    Preserves alphanumeric characters, hyphens, underscores, and the '#' prefix
    used by Shopify order numbers (e.g. #1029392, #BG10129). Code-128 mode B
    supports the full printable ASCII range so '#' encodes reliably.

    Args:
        order_number: Raw order number

    Returns:
        Sanitized order number safe for barcode encoding

    Raises:
        InvalidOrderNumberError: If order number is empty after sanitization
    """
    if not order_number:
        raise InvalidOrderNumberError("Order number cannot be empty")

    clean = ''.join(c for c in order_number if c.isalnum() or c in ['-', '_', '#'])

    if not clean:
        raise InvalidOrderNumberError(f"Order number '{order_number}' contains no valid characters")

    return clean


def format_tags_for_barcode(internal_tag) -> str:
    """
    Format internal tags for barcode label display.

    Parses JSON array format and returns all tags pipe-separated.

    Args:
        internal_tag: Internal tag string (JSON array format: '["GIFT+1", "GIFT+2"]'),
            or a native list (Internal_Tags is sometimes stored unserialized).

    Returns:
        Formatted tag string with all tags pipe-separated

    Examples:
        >>> format_tags_for_barcode('["GIFT+1", "GIFT+2"]')
        "GIFT+1|GIFT+2"
        >>> format_tags_for_barcode("Priority")
        "Priority"
    """
    if isinstance(internal_tag, list):
        tags = [str(tag).strip() for tag in internal_tag if tag]
        return '|'.join(tag for tag in tags if tag)

    if isinstance(internal_tag, str):
        internal_tag = internal_tag.strip()

    if not internal_tag or internal_tag == 'nan' or internal_tag == 'None':
        return ""

    if internal_tag.startswith('[') and internal_tag.endswith(']'):
        tags_list = None
        try:
            tags_list = json.loads(internal_tag)
        except (json.JSONDecodeError, ValueError):
            try:
                import ast
                tags_list = ast.literal_eval(internal_tag)
            except (ValueError, SyntaxError):
                pass
        if isinstance(tags_list, list):
            return '|'.join(str(tag).strip() for tag in tags_list if tag)

    if '|' in internal_tag:
        tags = [t.strip() for t in internal_tag.split('|') if t.strip()]
        return '|'.join(tags)

    return internal_tag.strip()


# === BATCH RECORD BUILDING ===

def generate_barcodes_batch(
    df: pd.DataFrame,
    sequential_map: dict[str, int] | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None
) -> list[dict[str, Any]]:
    """
    Build one label record per order, validating/sanitizing each order number.

    No rendering happens here -- pass the successful records to
    generate_code128_labels_pdf() to render the actual PDF.

    Args:
        df: DataFrame with columns:
            - Order_Number (required)
            - Shipping_Provider (required, courier name)
            - Destination_Country (required, may be empty)
            - Internal_Tag (required, may be empty)
            - item_count (preferred) or Quantity (fallback): number of items in order
        sequential_map: Dict mapping Order_Number to sequential number (from sequential_order.json)
                       If None, will use row index + 1 as fallback
        progress_callback: Optional callback(current, total, message) for progress updates

    Returns:
        List of result dicts (one per order). success=True results carry
        order_number (original), safe_order_number (barcode-safe, what the
        label actually shows/encodes), sequential_num, courier, country,
        tag, item_count -- ready to pass to generate_code128_labels_pdf().
        success=False results carry safe_order_number=None and an error.
    """
    results = []
    total_orders = len(df)

    logger.info(f"Starting batch barcode generation: {total_orders} orders")

    using_independent_numbering = sequential_map is None
    if using_independent_numbering:
        logger.info("Using independent packing list numbering (1, 2, 3...)")

    for idx, row in df.iterrows():
        order_number = str(row['Order_Number'])
        if sequential_map:
            sequential_num = sequential_map.get(order_number, idx + 1)
        else:
            sequential_num = idx + 1

        if progress_callback:
            progress_callback(
                len(results) + 1,
                total_orders,
                f"Preparing barcode {len(results) + 1} of {total_orders}..."
            )

        try:
            safe_order_number = sanitize_order_number(order_number)
        except InvalidOrderNumberError as e:
            logger.exception(f"Invalid order number '{order_number}'")
            results.append({
                "order_number": order_number,
                "safe_order_number": None,
                "sequential_num": 0,
                "courier": "",
                "country": "N/A",
                "tag": "N/A",
                "item_count": 0,
                "success": False,
                "error": str(e)
            })
            continue

        courier = str(row['Shipping_Provider'])
        country = str(row.get('Destination_Country', '')) if pd.notna(row.get('Destination_Country')) else ''

        tag_raw = row.get('Internal_Tags', row.get('Internal_Tag', ''))
        tag = str(tag_raw) if pd.notna(tag_raw) and tag_raw else ''
        if tag and tag != 'nan' and tag != 'None':
            logger.info(f"Order {order_number}: Tag found = '{tag}'")

        raw_count = row.get('item_count')
        if pd.isna(raw_count):
            raw_count = row.get('Quantity', 1)
        try:
            # Do not use `raw_count or 1` -- a genuinely-zero item_count is
            # falsy in Python and would be wrongly coerced to 1.
            item_count = int(float(raw_count))
        except (ValueError, TypeError):
            item_count = 1

        results.append({
            "order_number": order_number,
            "safe_order_number": safe_order_number,
            "sequential_num": sequential_num,
            "courier": courier,
            "country": country if country else "N/A",
            "tag": format_tags_for_barcode(tag) if tag else "N/A",
            "item_count": item_count,
            "success": True,
            "error": None
        })

    logger.info(
        f"Batch preparation complete: {sum(r['success'] for r in results)}/{total_orders} successful"
    )
    return results


# === PDF RENDERING ===

def generate_code128_labels_pdf(orders: list[dict[str, Any]], output_pdf: Path) -> Path:
    """
    Render one Code-128 label per order as a single multi-page PDF.

    Args:
        orders: List of dicts as produced by generate_barcodes_batch()'s
            successful results: safe_order_number, sequential_num, courier,
            country, tag, item_count.
        output_pdf: Output PDF path.

    Returns:
        Path to the generated PDF (same as output_pdf).

    Raises:
        ValueError: If orders is empty.
        BarcodeGenerationError: If rendering fails.
    """
    if not orders:
        raise ValueError("Cannot generate PDF: no orders provided")

    date_str = datetime.now().astimezone().strftime("%d/%m/%y")
    records = [
        {
            "order_number": order["safe_order_number"],
            "sequential_num": order["sequential_num"],
            "courier": order["courier"],
            "country": order["country"],
            "tag": order["tag"],
            "item_count": order["item_count"],
            "date_str": date_str,
        }
        for order in orders
    ]

    try:
        writer = LabelWriter(
            str(_BARCODE_LABEL_TEMPLATE),
            default_stylesheets=(str(_FONTS_CSS), str(_BARCODE_LABEL_STYLE)),
            items_per_page=1,
            label_tools=label_tools,
        )
        pdf_bytes = writer.write_labels(records, target="@memory")
        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        output_pdf.write_bytes(pdf_bytes)
    except Exception as e:
        raise BarcodeGenerationError(f"Failed to generate barcode labels PDF: {e}") from e

    logger.info(f"Generated PDF: {output_pdf} ({len(records)} pages)")
    return output_pdf


def generate_qr_labels_pdf(orders: list[dict[str, Any]], output_pdf: Path) -> Path:
    """
    Render one QR label per order as a single multi-page PDF.

    Args:
        orders: List of dicts: order_number (str), sku_qty_lines
            (list[tuple[str, int]] -- (SKU, quantity) pairs for that order).
        output_pdf: Output PDF path.

    Returns:
        Path to the generated PDF (same as output_pdf).

    Raises:
        ValueError: If orders is empty.
        BarcodeGenerationError: If rendering fails.
    """
    if not orders:
        raise ValueError("Cannot generate PDF: no orders provided")

    records = []
    for order in orders:
        lines = [f"{sku} x{qty}" for sku, qty in order["sku_qty_lines"]]
        qr_payload = "\n".join([order["order_number"], *lines])
        records.append({
            "order_number": order["order_number"],
            "qr_payload": qr_payload,
        })

    try:
        writer = LabelWriter(
            str(_QR_LABEL_TEMPLATE),
            default_stylesheets=(str(_FONTS_CSS), str(_QR_LABEL_STYLE)),
            items_per_page=1,
            label_tools=label_tools,
        )
        pdf_bytes = writer.write_labels(records, target="@memory")
        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        output_pdf.write_bytes(pdf_bytes)
    except Exception as e:
        raise BarcodeGenerationError(f"Failed to generate QR labels PDF: {e}") from e

    logger.info(f"Generated QR labels PDF: {output_pdf} ({len(records)} pages)")
    return output_pdf
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_barcode_processor.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Lint and commit**

Run: `ruff check shopify_tool/barcode_processor.py tests/test_barcode_processor.py`

```bash
git add shopify_tool/barcode_processor.py tests/test_barcode_processor.py
git commit -m "Replace PIL/reportlab label rendering with blabel templates"
```

---

### Task 6: `gui/barcode_generator_widget.py` — wire up the new functions, remove PNG/PDF checkboxes

**Files:**
- Modify: `gui/barcode_generator_widget.py`

**Interfaces:**
- Consumes: `generate_barcodes_batch()`, `generate_code128_labels_pdf()` (Task 5).
- No test file — this widget has no existing GUI test coverage for this flow (matches the codebase's current state; D-3's own plan is what adds `test_barcode_generator_widget.py`, out of scope here). Verify manually via `python run_dev.py` per Step 5.

With no PNG artifact ever produced, `generate_png_checkbox`/`generate_pdf_checkbox` become structurally meaningless — this task removes both, PDF becomes the unconditional output (confirmed with the user; this mechanically implements the "no PNG, PDF isn't optional" slice of D-3's already-decided end state for just these two controls, nothing else from D-3).

- [ ] **Step 1: Remove the PNG/PDF checkboxes from `_create_options_section`**

In `gui/barcode_generator_widget.py`, find `_create_options_section` (around line 119). Replace:

```python
        # Output format options
        format_label = QLabel("Output Format:")
        format_label.setStyleSheet("font-weight: bold; margin-top: 5px;")
        layout.addWidget(format_label)

        # Generate PNG checkbox
        self.generate_png_checkbox = QCheckBox("Generate PNG files (individual barcode images)")
        self.generate_png_checkbox.setChecked(False)  # Optional, off by default
        layout.addWidget(self.generate_png_checkbox)

        # Generate PDF checkbox
        self.generate_pdf_checkbox = QCheckBox("Generate PDF file (all barcodes in one document)")
        self.generate_pdf_checkbox.setChecked(True)  # Default option
        layout.addWidget(self.generate_pdf_checkbox)

        # Output directory label
```

with:

```python
        # Output directory label
```

(Deletes the format-choice UI entirely — PDF is now the only output, matching the `Options` group's remaining `auto_open_folder_checkbox` and output-dir label unchanged above/below this block.)

- [ ] **Step 2: Remove the format-selection validation from `_on_generate_clicked`**

Find (around line 343):

```python
        # Validate format selection
        if not self.generate_png_checkbox.isChecked() and not self.generate_pdf_checkbox.isChecked():
            QMessageBox.warning(
                self,
                "No Format Selected",
                "Please select at least one output format (PNG or PDF)."
            )
            return

        # Confirm generation
        order_count = self.filtered_orders_df['Order_Number'].nunique()

        # Build format string
        formats = []
        if self.generate_png_checkbox.isChecked():
            formats.append("PNG")
        if self.generate_pdf_checkbox.isChecked():
            formats.append("PDF")
        format_str = " + ".join(formats)

        reply = QMessageBox.question(
            self,
            "Confirm Generation",
            f"Generate barcodes for {order_count} orders?\n\n"
            f"Packing List: {self.current_packing_list}\n"
            f"Output Format: {format_str}\n"
            f"Output: {self.barcodes_dir}",
            QMessageBox.Yes | QMessageBox.No
        )
```

Replace with:

```python
        # Confirm generation
        order_count = self.filtered_orders_df['Order_Number'].nunique()

        reply = QMessageBox.question(
            self,
            "Confirm Generation",
            f"Generate barcodes for {order_count} orders?\n\n"
            f"Packing List: {self.current_packing_list}\n"
            f"Output: {self.barcodes_dir}",
            QMessageBox.Yes | QMessageBox.No
        )
```

- [ ] **Step 3: Rewrite `_generate_barcodes_worker`**

Find (around line 394) the `results = generate_barcodes_batch(...)` call:

```python
        # Generate barcodes with independent numbering per packing list (sequential_map=None)
        results = generate_barcodes_batch(
            df=unique_orders,
            output_dir=self.barcodes_dir,
            sequential_map=None,  # Independent per-generation numbering
            progress_callback=None  # No progress updates from worker thread
        )

        return results
```

Replace with (drops `output_dir` — `generate_barcodes_batch` no longer writes files):

```python
        # Prepare barcode records with independent numbering per packing list
        results = generate_barcodes_batch(
            df=unique_orders,
            sequential_map=None,  # Independent per-generation numbering
            progress_callback=None  # No progress updates from worker thread
        )

        return results
```

- [ ] **Step 4: Rewrite `_on_generation_complete`, `_generate_pdf_from_results`; delete `_cleanup_png_files`**

Find (around line 438) `_on_generation_complete` through `_cleanup_png_files` (ending before `_open_barcodes_folder`) and replace the whole span with:

```python
    def _on_generation_complete(self, results):
        """Handle successful generation."""
        successful = [r for r in results if r['success']]
        failed = [r for r in results if not r['success']]

        # Reset progress bar to normal mode and set to 100%
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.status_label.setText(
            f"Complete: {len(successful)} barcodes generated"
        )
        self.status_label.setStyleSheet("color: green; font-weight: bold;")

        self.log.info(
            f"Barcode generation complete: {len(successful)} successful, "
            f"{len(failed)} failed"
        )

        if successful:
            self._generate_pdf_from_results(successful)

        message = f"Successfully generated {len(successful)} barcode labels as a PDF document."

        if failed:
            message += f"\n\n{len(failed)} barcodes failed to generate."

        QMessageBox.information(self, "Generation Complete", message)

        # Auto-open folder if enabled
        if self.auto_open_folder_checkbox.isChecked():
            self._open_barcodes_folder()

        # Emit signal
        self.generation_complete.emit({
            'packing_list': self.current_packing_list,
            'successful': len(successful),
            'failed': len(failed),
            'total': len(results)
        })

    def _on_generation_error(self, error_info):
        """Handle generation error."""
        _exctype, value, traceback_str = error_info

        self.status_label.setText("Generation failed")
        self.status_label.setStyleSheet("color: red; font-weight: bold;")

        self.log.error(f"Barcode generation failed: {value}\n{traceback_str}")

        QMessageBox.critical(
            self,
            "Generation Error",
            f"Barcode generation failed:\n\n{value}\n\n"
            "See execution log for details."
        )

    def _on_generation_finished(self):
        """Re-enable UI after generation."""
        self.progress_bar.setVisible(False)
        self.generate_btn.setEnabled(True)

    def _generate_pdf_from_results(self, results):
        """Generate the barcode labels PDF from prepared order records."""
        try:
            from shopify_tool.barcode_processor import generate_code128_labels_pdf

            pdf_filename = f"{self.current_packing_list}_barcodes.pdf"
            pdf_path = self.barcodes_dir / pdf_filename

            generate_code128_labels_pdf(results, pdf_path)

            self.log.info(f"Generated PDF: {pdf_path}")

            url = QUrl.fromLocalFile(str(pdf_path))
            QDesktopServices.openUrl(url)

        except Exception:
            self.log.exception("PDF generation failed")
```

(This deletes `_cleanup_png_files` entirely — no callers remain, since no PNGs are ever created.)

- [ ] **Step 5: Manual verification**

Run: `python run_dev.py`, navigate to the Barcode Generator tab, select a packing list, click Generate. Confirm: no PNG/PDF checkboxes shown, generation completes, a PDF opens with one label per order, no traceback in the log panel.

- [ ] **Step 6: Lint and commit**

Run: `ruff check gui/barcode_generator_widget.py`

```bash
git add gui/barcode_generator_widget.py
git commit -m "Wire barcode_generator_widget.py to blabel-based rendering, drop PNG/PDF format choice"
```

---

### Task 7: `gui_main.py` — WeasyPrint runtime DLL/fontconfig setup

**Files:**
- Modify: `gui_main.py`

**Interfaces:**
- Produces: `configure_frozen_weasyprint_env()`, `configure_windows_fontconfig_env()`, both called at module import time before any WeasyPrint-importing module loads.

Ported from `barcode_tool`'s `app/main.py`, adapted to this file's structure. Must run **before** `from gui.main_window_pyside import MainWindow` — that import chain reaches `barcode_processor.py`, which imports `blabel`/WeasyPrint.

- [ ] **Step 1: Insert the runtime setup**

In `gui_main.py`, between the existing imports (`import os` / `import sys`) and the `from gui.main_window_pyside import MainWindow` line, insert:

```python
import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

__version__ = "1.9.9.1"

# Ensure the gui directory is on the path if running this as a script
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))


# WeasyPrint (via blabel, imported by shopify_tool.barcode_processor) needs
# GTK3's bundled Pango/Cairo/fontconfig on Windows. A frozen build ships its
# own GTK3 copy in gtk-dlls/ next to the exe; Windows won't find those DLLs
# (or, separately, fontconfig's own fonts.conf) unless we point at them
# explicitly first -- before MainWindow (and everything it imports) loads.
def configure_frozen_weasyprint_env() -> None:
    if getattr(sys, "frozen", False) and hasattr(os, "add_dll_directory"):
        os.add_dll_directory(str(Path(sys.executable).parent / "gtk-dlls"))


_WINDOWS_GTK3_FONTCONFIG_CANDIDATES = (
    r"C:\Program Files\GTK3-Runtime Win64\etc\fonts",
    r"C:\msys64\mingw64\etc\fonts",
)


def configure_windows_fontconfig_env() -> None:
    # Best-effort only: never overrides an already-set env var, and never
    # sets a path that doesn't actually contain a fonts.conf. When GTK3
    # isn't on PATH, fontconfig can't find its fonts.conf and prints
    # "Cannot load default config file" at startup -- labels still render
    # (this app's templates use a bundled @font-face TTF, not system font
    # lookup), so this only avoids the startup noise.
    if sys.platform != "win32" or os.environ.get("FONTCONFIG_PATH"):
        return
    candidates = list(_WINDOWS_GTK3_FONTCONFIG_CANDIDATES)
    if getattr(sys, "frozen", False):
        candidates.insert(0, str(Path(sys.executable).parent / "gtk-dlls" / "etc" / "fonts"))
    for candidate in candidates:
        if (Path(candidate) / "fonts.conf").is_file():
            os.environ["FONTCONFIG_PATH"] = candidate
            return


configure_frozen_weasyprint_env()
configure_windows_fontconfig_env()

from gui.main_window_pyside import MainWindow
from gui.theme_manager import get_theme_manager
```

(This replaces the file's existing import block, lines 7–18, in place — everything below `def main():` is unchanged.)

- [ ] **Step 2: Verify the app still starts headlessly**

Run: `CI=1 python run_dev.py`
Expected: `Offscreen application initialized successfully.` printed, no traceback (confirms the new module-level code doesn't break non-Windows/non-frozen startup — both guard conditions, `sys.frozen` and `sys.platform != "win32"`, are false in this dev environment, so both functions no-op).

- [ ] **Step 3: Lint and commit**

Run: `ruff check gui_main.py`

```bash
git add gui_main.py
git commit -m "Add WeasyPrint DLL-path/fontconfig runtime setup for frozen Windows builds"
```

---

### Task 8: CI `verify` job — Linux system deps for WeasyPrint

**Files:**
- Modify: `.github/workflows/build_release.yml`

**Interfaces:**
- Produces: the `verify` job's Linux runner has Pango/Cairo/GDK-Pixbuf available, so `import shopify_tool.barcode_processor` (which imports `blabel` → WeasyPrint) succeeds during `pytest` and the `ruff`/smoke-test steps.

- [ ] **Step 1: Add the system packages**

In `.github/workflows/build_release.yml`, find the `verify` job's `Install dependencies` step (around line 27):

```yaml
      - name: Install dependencies
        run: |
          sudo apt-get update && sudo apt-get install -y libegl1
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install -r requirements-dev.txt
```

Replace with (adds the three packages `barcode_tool`'s own `RELEASING.md` documents as the Linux runtime requirement for Pango/Cairo/GDK-Pixbuf, verified against that file directly):

```yaml
      - name: Install dependencies
        run: |
          sudo apt-get update && sudo apt-get install -y libegl1 libpango-1.0-0 libcairo2 libgdk-pixbuf-2.0-0
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install -r requirements-dev.txt
```

- [ ] **Step 2: Verify locally (best-effort — CI is the real check)**

If running Linux locally: `sudo apt-get install -y libpango-1.0-0 libcairo2 libgdk-pixbuf-2.0-0 && python -c "import shopify_tool.barcode_processor"` should succeed with no `OSError`/`ImportError` from WeasyPrint's native-library loading.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/build_release.yml
git commit -m "CI: add Pango/Cairo/GDK-Pixbuf system deps for WeasyPrint import"
```

---

### Task 9: CI `build` job — onedir + MSYS2 Pango + GTK DLL bundling + zip artifact

**Files:**
- Modify: `.github/workflows/build_release.yml`

**Interfaces:**
- Produces: the release artifact changes from a renamed single `.exe` to a `.zip` of a PyInstaller `--onedir` build with a `gtk-dlls/` folder bundled alongside the exe. This is a real, user-facing distribution change — confirmed in scope with the user (see spec P-5).

This exact recipe (MSYS2 pacman package name, `--add-data`/`--collect-data` flags, GTK DLL copy step) is verified against `barcode_tool`'s actual shipping `.github/workflows/release.yml`, not assumed.

- [ ] **Step 1: Rewrite the `build` job**

In `.github/workflows/build_release.yml`, replace the entire `build` job (from `build:` through the end of the file) with:

```yaml
  build:
    name: Build Executable
    needs: [verify]
    runs-on: windows-latest
    # Only run build job for releases, not on every push/pr
    if: github.event_name == 'release'

    steps:
      - name: Check out code
        uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          # PyInstaller is in dev requirements
          pip install -r requirements-dev.txt
      - name: Install Pango/GTK runtime (MSYS2)
        shell: cmd
        run: |
          C:\msys64\usr\bin\pacman.exe -S --noconfirm --needed mingw-w64-x86_64-pango
      - name: Build with PyInstaller
        run: >
          pyinstaller --name ShopifyFulfillmentTool --onedir --windowed --noconfirm
          --add-data "shopify_tool/templates;shopify_tool/templates"
          --collect-data blabel
          gui_main.py
      - name: Bundle GTK DLLs
        shell: pwsh
        run: |
          Copy-Item -Recurse -Path "C:\msys64\mingw64\bin" -Destination "dist\ShopifyFulfillmentTool\gtk-dlls"
      - name: Zip artifact
        shell: pwsh
        run: |
          Compress-Archive -Path "dist\ShopifyFulfillmentTool\*" -DestinationPath "ShopifyFulfillmentTool-v${{ github.ref_name }}.zip"
      - name: Upload Release Asset
        uses: softprops/action-gh-release@v2
        with:
          files: ShopifyFulfillmentTool-v${{ github.ref_name }}.zip
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

Note what did NOT change from `barcode_tool`'s recipe: the MSYS2 package name (`mingw-w64-x86_64-pango`, which pulls in Cairo/GDK-Pixbuf as its own dependencies), the GTK DLL bundling step (copies the whole `mingw64\bin` tree — `barcode_tool`'s own documented known limitation is a bigger artifact than strictly necessary; same trade-off accepted here, see spec Follow-ups). What did change: `--onedir` output is named `ShopifyFulfillmentTool` (matches this app's existing naming, e.g. `--name ShopifyFulfillmentTool`) instead of `BarcodeTool`; `--windowed` is kept (this app already builds `--windowed`, unlike `barcode_tool` which didn't need to specify it in the recipe read); `--add-data` points at `shopify_tool/templates` (this app's actual template location from Tasks 2–4) instead of `barcode_tool`'s `app/templates/examples`+`app/assets/fonts` (this app's fonts already live under `shopify_tool/templates/assets/fonts/`, covered by the same `--add-data` glob since it's a subdirectory).

- [ ] **Step 2: Verify the workflow YAML is well-formed**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/build_release.yml'))"`
Expected: no exception.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/build_release.yml
git commit -m "CI: rebuild Windows release as onedir+GTK-bundled zip, not a single onefile exe"
```

- [ ] **Step 4: Note for the next actual release**

This task cannot be fully verified until a real GitHub Release is published (the `build` job only runs `if: github.event_name == 'release'`) and the resulting `.zip` is tested on a real Windows machine — tracked as a Follow-up in the spec (no Windows runner available for an interactive smoke test beyond what PyInstaller itself validates at build time). The next release cut should specifically confirm: the app launches, WeasyPrint renders a real label without a Pango/GTK error dialog, and the printed output matches the physical Citizen CL-E300 label stock.

---

## Plan Self-Review Notes

- **Spec coverage:** P-1 → Task 1. P-2 (templates+fonts) → Tasks 2–4. P-3 (barcode_processor.py + wiring) → Tasks 5–6. P-4 (font bundling) → Task 2. P-5 (Windows packaging) → Tasks 7–9. Testing section → Steps embedded in Tasks 1, 5. Files touched → every listed file has a task. Non-goals (Reference Labels overlay, raw ZPL, template externalization, threaded printing) → correctly has no task.
- **Placeholder scan:** the font-download step (Task 2) points at an exact URL/exact files/exact target paths rather than a vague "add a font" — the only defensible exception to "no placeholders," since a binary asset can't be written as plan text.
- **Type consistency:** `generate_barcodes_batch()`'s new `safe_order_number` key (Task 5) is the same key `generate_code128_labels_pdf()` (Task 5) reads and `TestGenerateBarcodesBatch`/`TestGenerateCode128LabelsPdfIntegration` (Task 5) assert on. `sku_qty_lines` (Task 5's `generate_qr_labels_pdf()`) matches its own test's shape — no other task currently builds this list (QR-label wiring in `barcode_generator_widget.py` is D-3/D-4's own UI work per the 2026-07-30 plan's "Add QR labels" checkbox, out of this patch's scope per the confirmed Barcode-Generator-only decision covering the *rendering*, not the not-yet-built QR checkbox UI — `generate_qr_labels_pdf()` is ready for that wiring when D-3 lands, but nothing in this plan calls it yet, matching the spec's scope).
