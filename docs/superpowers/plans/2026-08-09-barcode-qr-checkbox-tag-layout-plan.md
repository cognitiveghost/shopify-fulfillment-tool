# Barcode Generator: QR Checkbox, Auto-Open-PDF, Tag Layout Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the already-built (but never GUI-connected) QR-label backend into the Barcode Generator window behind a new checkbox, replace the "auto-open folder" checkbox with a real "auto-open PDF" toggle, and fix the Code-128/QR label layout so the TAG field can never overflow the physical 68mm × 38mm label.

**Architecture:** `shopify_tool/barcode_processor.py`'s `generate_qr_labels_pdf()` is resigned to consume the exact same order-record shape `generate_code128_labels_pdf()` already does (QR payload becomes the order number only). `gui/barcode_generator_widget.py` gains an `add_qr_checkbox` and an `auto_open_pdf_checkbox`, a new `_generate_qr_pdf_from_results()` alongside the existing `_generate_pdf_from_results()`, and a small `_open_pdf()` helper so rendering and opening become separate, checkbox-gated concerns instead of the current unconditional open. Both blabel/Jinja2 label templates (`shopify_tool/templates/{barcode_label,qr_label}/`) are restructured from a single side-by-side row into a top row (info column + code image) plus a dedicated full-width bottom row for the TAG field, with `overflow: hidden` as a hard guarantee against physical overflow.

**Tech Stack:** PySide6 (Qt widgets), blabel/WeasyPrint (HTML→PDF label rendering), Jinja2 templates, pytest (`QT_QPA_PLATFORM=offscreen`), ruff.

## Global Constraints

- `QT_QPA_PLATFORM=offscreen python -m pytest` and `ruff check . --exclude shared` must pass before merge (per `AGENTS.md` / `CLAUDE.md`).
- Label physical dimensions are fixed at 68mm × 38mm (`@page` rule in each `style.css`) — do not change.
- The label print CSS (`shopify_tool/templates/**/style.css`) is thermal-printer markup, not app UI — it correctly uses literal `black` for ink already; this is unrelated to `CLAUDE.md`'s "never hardcode colors" rule, which governs `theme_manager`-driven Qt stylesheets only. No new Qt stylesheet is added by this plan.
- `shared/` is not touched by any task in this plan.
- No new dependencies — `blabel`, `qrcode`, `pypdf` are already installed.

---

## Task 1: Simplify `generate_qr_labels_pdf()` to encode order number only

**Files:**
- Modify: `shopify_tool/barcode_processor.py:283-325` (`generate_qr_labels_pdf`)
- Modify: `shopify_tool/templates/qr_label/template.html`
- Test: `tests/test_barcode_processor.py:156-188` (`TestGenerateQrLabelsPdfIntegration`)

**Interfaces:**
- Produces: `generate_qr_labels_pdf(orders: list[dict[str, Any]], output_pdf: Path) -> Path` where each `orders` dict has the same shape `generate_code128_labels_pdf()` already takes: `safe_order_number`, `sequential_num`, `courier`, `country`, `tag`, `item_count`. Raises `ValueError` on empty `orders`, `BarcodeGenerationError` on render failure — unchanged from today.
- Consumed by: Task 2's `_generate_qr_pdf_from_results()`, which passes it the same `successful` records list already built for the barcode PDF.

- [ ] **Step 1: Replace `TestGenerateQrLabelsPdfIntegration` with the new contract (failing test first)**

Replace the entire class (lines 156-188) in `tests/test_barcode_processor.py`:

```python
class TestGenerateQrLabelsPdfIntegration:
    def _order(self, **overrides):
        order = {
            "safe_order_number": "#1029392",
            "sequential_num": 7, "courier": "DHL", "country": "DE",
            "tag": "N/A", "item_count": 3,
        }
        order.update(overrides)
        return order

    def test_generates_pdf_with_one_page_per_order(self, tmp_path):
        output_pdf = tmp_path / "qr_labels.pdf"
        result = generate_qr_labels_pdf(
            [self._order(safe_order_number="#1"), self._order(safe_order_number="#2")],
            output_pdf,
        )
        assert result == output_pdf
        reader = pypdf.PdfReader(str(output_pdf))
        assert len(reader.pages) == 2

    def test_empty_orders_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            generate_qr_labels_pdf([], tmp_path / "qr_labels.pdf")

    def test_qr_payload_is_order_number_only(self, tmp_path, monkeypatch):
        captured = {}
        original_qr_code = label_tools.qr_code

        def spy_qr_code(data, *args, **kwargs):
            captured["data"] = data
            return original_qr_code(data, *args, **kwargs)

        monkeypatch.setattr(label_tools, "qr_code", spy_qr_code)

        generate_qr_labels_pdf(
            [self._order(safe_order_number="#1029392")], tmp_path / "qr_labels.pdf"
        )

        assert captured["data"] == "#1029392"
```

- [ ] **Step 2: Run to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_barcode_processor.py -k TestGenerateQrLabelsPdfIntegration -v`
Expected: FAIL — `KeyError: 'sku_qty_lines'` (the old implementation still expects the old shape).

- [ ] **Step 3: Rewrite `generate_qr_labels_pdf()`**

Replace the function body in `shopify_tool/barcode_processor.py` (lines 283-325) with:

```python
def generate_qr_labels_pdf(orders: list[dict[str, Any]], output_pdf: Path) -> Path:
    """
    Render one QR label per order as a single multi-page PDF.

    Args:
        orders: List of dicts as produced by generate_barcodes_batch()'s
            successful results -- same shape generate_code128_labels_pdf()
            takes: safe_order_number, sequential_num, courier, country, tag,
            item_count. The QR code encodes the order number only.
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

- [ ] **Step 4: Update `qr_label/template.html` to encode `order_number` instead of the removed `qr_payload`**

`shopify_tool/templates/qr_label/template.html` currently reads:

```html
<img class="qr" src="{{ label_tools.qr_code(qr_payload) }}"/>
```

Change the `qr_code(...)` call's argument from `qr_payload` to `order_number`:

```html
<img class="qr" src="{{ label_tools.qr_code(order_number) }}"/>
```

(Leave the rest of the file as-is for this task — Task 4 rebuilds this template's full layout.)

- [ ] **Step 5: Run to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_barcode_processor.py -k TestGenerateQrLabelsPdfIntegration -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add shopify_tool/barcode_processor.py shopify_tool/templates/qr_label/template.html tests/test_barcode_processor.py
git commit -m "Simplify generate_qr_labels_pdf() to encode order number only"
```

---

## Task 2: Wire QR-labels checkbox and auto-open-PDF checkbox into the widget

**Files:**
- Modify: `gui/barcode_generator_widget.py`
- Test: `tests/test_barcode_generator_widget.py` (full rewrite)

**Interfaces:**
- Consumes: `generate_qr_labels_pdf(orders, output_pdf) -> Path` from Task 1.
- Produces: `BarcodeGeneratorWidget.add_qr_checkbox` (QCheckBox, default unchecked), `auto_open_pdf_checkbox` (QCheckBox, default checked), `_generate_qr_pdf_from_results(self, results) -> bool`, `_open_pdf(self, pdf_path)`. `_generate_pdf_from_results()` no longer opens the PDF itself (returns bool only). `_open_barcodes_folder()` and `auto_open_folder_checkbox` are removed.

- [ ] **Step 1: Rewrite `tests/test_barcode_generator_widget.py` for the new contract (failing test first)**

Replace the entire file with:

```python
"""Regression test for gui.barcode_generator_widget.BarcodeGeneratorWidget.

Root cause: _generate_pdf_from_results() swallowed rendering exceptions and
_on_generation_complete() always showed the "Generation Complete" success
dialog regardless, so a WeasyPrint/blabel failure looked like success with
no PDF ever written (CodeRabbit review on PR #259). Extended to cover the
"Add QR labels" checkbox and the auto-open-PDF checkbox (PR #259 follow-up).
"""
from pathlib import Path
from unittest.mock import Mock

from PySide6.QtWidgets import QMessageBox

from gui.barcode_generator_widget import BarcodeGeneratorWidget


class _FakeWidget:
    """Stand-in exposing only what _on_generation_complete() touches --
    avoids constructing a real BarcodeGeneratorWidget (needs a live session)."""

    def __init__(self, pdf_ok, qr_pdf_ok=True):
        self._pdf_ok = pdf_ok
        self._qr_pdf_ok = qr_pdf_ok
        self.log = Mock()
        self.progress_bar = Mock()
        self.status_label = Mock()
        self.add_qr_checkbox = Mock()
        self.auto_open_pdf_checkbox = Mock()
        self.current_packing_list = "PL1"
        self.barcodes_dir = Path("/fake/barcodes")
        self.generation_complete = Mock()
        self.opened_pdfs = []
        self.pdf_render_calls = 0
        self.qr_pdf_render_calls = 0

    def _generate_pdf_from_results(self, results):
        self.pdf_render_calls += 1
        return self._pdf_ok

    def _generate_qr_pdf_from_results(self, results):
        self.qr_pdf_render_calls += 1
        return self._qr_pdf_ok

    def _open_pdf(self, pdf_path):
        self.opened_pdfs.append(pdf_path)


def _run(monkeypatch, pdf_ok, results=None, auto_open=True, add_qr=False, qr_pdf_ok=True):
    info = Mock()
    critical = Mock()
    monkeypatch.setattr(QMessageBox, "information", info)
    monkeypatch.setattr(QMessageBox, "critical", critical)

    widget = _FakeWidget(pdf_ok, qr_pdf_ok=qr_pdf_ok)
    widget.auto_open_pdf_checkbox.isChecked.return_value = auto_open
    widget.add_qr_checkbox.isChecked.return_value = add_qr
    if results is None:
        results = [{"success": True, "order_number": "#1"}]

    BarcodeGeneratorWidget._on_generation_complete(widget, results)
    return widget, info, critical


def test_pdf_render_failure_shows_error_not_success(monkeypatch):
    widget, info, critical = _run(monkeypatch, pdf_ok=False)
    assert critical.called
    assert not info.called
    assert not widget.opened_pdfs


def test_pdf_render_success_shows_completion_message(monkeypatch):
    widget, info, critical = _run(monkeypatch, pdf_ok=True)
    assert info.called
    assert not critical.called
    assert widget.opened_pdfs == [Path("/fake/barcodes/PL1_barcodes.pdf")]


def test_all_orders_failed_skips_pdf_render_and_shows_completion_message(monkeypatch):
    widget, info, critical = _run(
        monkeypatch, pdf_ok=True, results=[{"success": False, "order_number": "#1"}]
    )
    assert widget.pdf_render_calls == 0
    assert info.called
    assert not critical.called
    assert not widget.opened_pdfs


def test_auto_open_off_renders_but_does_not_open(monkeypatch):
    widget, info, critical = _run(monkeypatch, pdf_ok=True, auto_open=False)
    assert widget.pdf_render_calls == 1
    assert not widget.opened_pdfs


def test_qr_checkbox_off_skips_qr_generation(monkeypatch):
    widget, info, critical = _run(monkeypatch, pdf_ok=True, add_qr=False)
    assert widget.qr_pdf_render_calls == 0
    assert widget.opened_pdfs == [Path("/fake/barcodes/PL1_barcodes.pdf")]


def test_qr_checkbox_on_generates_and_opens_both_pdfs(monkeypatch):
    widget, info, critical = _run(monkeypatch, pdf_ok=True, add_qr=True, qr_pdf_ok=True)
    assert widget.qr_pdf_render_calls == 1
    assert widget.opened_pdfs == [
        Path("/fake/barcodes/PL1_barcodes.pdf"),
        Path("/fake/barcodes/PL1_qr_labels.pdf"),
    ]
    assert info.called
    assert not critical.called
    message = info.call_args[0][2]
    assert "QR" in message


def test_qr_generation_failure_does_not_block_primary_success_dialog(monkeypatch):
    widget, info, critical = _run(monkeypatch, pdf_ok=True, add_qr=True, qr_pdf_ok=False)
    assert info.called
    assert not critical.called
    message = info.call_args[0][2]
    assert "QR labels PDF failed" in message
    assert widget.opened_pdfs == [Path("/fake/barcodes/PL1_barcodes.pdf")]
```

- [ ] **Step 2: Run to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_barcode_generator_widget.py -v`
Expected: FAIL — `AttributeError` (widget's `_on_generation_complete` still references `self.auto_open_folder_checkbox`, which `_FakeWidget` no longer defines).

- [ ] **Step 3: Update `_create_options_section()` in `gui/barcode_generator_widget.py:119-139`**

Replace with:

```python
    def _create_options_section(self):
        """Create options section."""
        group = QGroupBox("Options")
        layout = QVBoxLayout(group)

        # Add QR labels checkbox
        self.add_qr_checkbox = QCheckBox("Add QR labels (order number)")
        self.add_qr_checkbox.setChecked(False)
        layout.addWidget(self.add_qr_checkbox)

        # Auto-open PDF checkbox
        self.auto_open_pdf_checkbox = QCheckBox("Auto-open PDF after generation")
        self.auto_open_pdf_checkbox.setChecked(True)
        layout.addWidget(self.auto_open_pdf_checkbox)

        # Output directory label
        output_row = QHBoxLayout()
        output_row.addWidget(QLabel("Output:"))
        self.output_dir_label = QLabel("No packing list selected")
        theme = get_theme_manager().get_current_theme()
        self.output_dir_label.setStyleSheet(f"font-weight: bold; color: {theme.text_secondary};")
        self.output_dir_label.setWordWrap(True)
        output_row.addWidget(self.output_dir_label, 1)
        layout.addLayout(output_row)

        return group
```

- [ ] **Step 4: Update `_generate_pdf_from_results()` in `gui/barcode_generator_widget.py:472-493` to stop opening the PDF itself, add `_generate_qr_pdf_from_results()` and `_open_pdf()`, and remove `_open_barcodes_folder()`**

Replace lines 472-509 (from `def _generate_pdf_from_results` through the end of `_open_barcodes_folder`) with:

```python
    def _generate_pdf_from_results(self, results):
        """Generate the barcode labels PDF from prepared order records.

        Returns True on success, False if rendering failed.
        """
        try:
            from shopify_tool.barcode_processor import generate_code128_labels_pdf

            pdf_filename = f"{self.current_packing_list}_barcodes.pdf"
            pdf_path = self.barcodes_dir / pdf_filename

            generate_code128_labels_pdf(results, pdf_path)

            self.log.info(f"Generated PDF: {pdf_path}")
            return True

        except Exception:
            self.log.exception("PDF generation failed")
            return False

    def _generate_qr_pdf_from_results(self, results):
        """Generate the QR labels PDF from prepared order records.

        Returns True on success, False if rendering failed.
        """
        try:
            from shopify_tool.barcode_processor import generate_qr_labels_pdf

            pdf_filename = f"{self.current_packing_list}_qr_labels.pdf"
            pdf_path = self.barcodes_dir / pdf_filename

            generate_qr_labels_pdf(results, pdf_path)

            self.log.info(f"Generated QR labels PDF: {pdf_path}")
            return True

        except Exception:
            self.log.exception("QR labels PDF generation failed")
            return False

    def _open_pdf(self, pdf_path):
        """Open a generated PDF in the OS default viewer."""
        url = QUrl.fromLocalFile(str(pdf_path))
        QDesktopServices.openUrl(url)
```

- [ ] **Step 5: Rewrite `_on_generation_complete()` in `gui/barcode_generator_widget.py:404-449`**

Replace with:

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

        pdf_generated = self._generate_pdf_from_results(successful) if successful else False

        want_qr = bool(successful) and self.add_qr_checkbox.isChecked()
        qr_pdf_generated = self._generate_qr_pdf_from_results(successful) if want_qr else False

        if successful and not pdf_generated:
            QMessageBox.critical(
                self,
                "PDF Generation Failed",
                f"{len(successful)} barcodes were validated, but rendering the "
                "PDF failed.\n\nSee execution log for details."
            )
        else:
            message = f"Successfully generated {len(successful)} barcode labels as a PDF document."

            if want_qr:
                if qr_pdf_generated:
                    message += "\n\nAlso generated QR labels as a PDF document."
                else:
                    message += "\n\nQR labels PDF failed to generate. See execution log for details."

            if failed:
                message += f"\n\n{len(failed)} barcodes failed to generate."

            QMessageBox.information(self, "Generation Complete", message)

        # Auto-open generated PDFs if enabled
        if self.auto_open_pdf_checkbox.isChecked():
            if pdf_generated:
                self._open_pdf(self.barcodes_dir / f"{self.current_packing_list}_barcodes.pdf")
            if qr_pdf_generated:
                self._open_pdf(self.barcodes_dir / f"{self.current_packing_list}_qr_labels.pdf")

        # Emit signal
        self.generation_complete.emit({
            'packing_list': self.current_packing_list,
            'successful': len(successful),
            'failed': len(failed),
            'total': len(results)
        })
```

- [ ] **Step 6: Run to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_barcode_generator_widget.py -v`
Expected: PASS (7 tests).

- [ ] **Step 7: Commit**

```bash
git add gui/barcode_generator_widget.py tests/test_barcode_generator_widget.py
git commit -m "Add QR-labels and auto-open-PDF checkboxes to Barcode Generator window"
```

---

## Task 3: Fix Code-128 label layout — TAG field moves to a full-width row

**Files:**
- Modify: `shopify_tool/templates/barcode_label/template.html`
- Modify: `shopify_tool/templates/barcode_label/style.css`
- Test: `tests/test_label_templates.py` (new)

**Interfaces:**
- Consumes: `label_tools.fit_font_block(text, box_width_mm, box_height_mm, max_mm, min_mm)` — unchanged function, called with new box dimensions.
- Produces: the `.top-row` / `.tag-row` structural pattern that Task 4 mirrors in `qr_label/`.

- [ ] **Step 1: Write the failing structural regression test**

Create `tests/test_label_templates.py`:

```python
"""Regression tests for the label template markup itself (not just that
blabel/WeasyPrint can render it without raising) -- guards against
re-introducing the TAG field's cramped 14mm x 10mm column box, which could
overflow the physical 68mm x 38mm label once an order carried enough tags
to need more than a line or two (reported against PR #259)."""
from pathlib import Path

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "shopify_tool" / "templates"


class TestBarcodeLabelLayout:
    def test_tag_field_is_full_width_row_not_cramped_column_box(self):
        html = (_TEMPLATES_DIR / "barcode_label" / "template.html").read_text()
        css = (_TEMPLATES_DIR / "barcode_label" / "style.css").read_text()
        assert "tag-row" in html
        assert "tag-row" in css

    def test_tag_value_box_has_hard_overflow_guard(self):
        css = (_TEMPLATES_DIR / "barcode_label" / "style.css").read_text()
        assert "overflow: hidden" in css

    def test_tag_font_fit_uses_full_width_box_not_old_14mm_column(self):
        html = (_TEMPLATES_DIR / "barcode_label" / "template.html").read_text()
        assert "box_width_mm=14" not in html
        assert "fit_font_block" in html
```

- [ ] **Step 2: Run to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_label_templates.py -k TestBarcodeLabelLayout -v`
Expected: FAIL — `tag-row` not found (current template still has the old cramped `.tag-field` column box).

- [ ] **Step 3: Rewrite `shopify_tool/templates/barcode_label/template.html`**

```html
<!DOCTYPE html>
<html>
<body>
  <div class="label">
    <div class="top-row">
      <div class="info">
        <div class="seq">#{{ sequential_num }}</div>
        <div class="courier">{{ courier }}</div>
        <div class="date">{{ date_str }}</div>
        <hr>
        <div class="field"><span class="field-label">SUM:</span><span class="field-value">{{ item_count }}</span></div>
        <hr class="thin">
        <div class="field"><span class="field-label">COU:</span><span class="field-value">{{ country }}</span></div>
      </div>
      <div class="barcode-section">
        <img class="barcode" src="{{ label_tools.barcode(order_number) }}"/>
        <div class="order-number">{{ order_number }}</div>
      </div>
    </div>
    <div class="tag-row">
      <span class="field-label">TAG:</span>
      <span class="field-value" style="font-size: {{ label_tools.fit_font_block(tag, box_width_mm=55, box_height_mm=7, max_mm=3.2, min_mm=1.8) }}mm;">{{ tag }}</span>
    </div>
  </div>
</body>
</html>
```

- [ ] **Step 4: Rewrite `shopify_tool/templates/barcode_label/style.css`**

```css
@page { size: 68mm 38mm; margin: 0; }

* { box-sizing: border-box; margin: 0; padding: 0; }

body { width: 68mm; height: 38mm; font-family: "JetBrains Mono", monospace; }

.label {
  width: 68mm;
  height: 38mm;
  display: flex;
  flex-direction: column;
  padding: 1mm;
}

.top-row {
  flex: 1;
  display: flex;
  flex-direction: row;
  min-height: 0;
}

.info {
  width: 22mm;
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

.tag-row {
  height: 8mm;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  border-top: 0.3mm solid black;
  padding-top: 0.5mm;
  margin-top: 0.5mm;
  overflow: hidden;
}

.tag-row .field-label { width: 9mm; font-size: 3mm; font-weight: bold; }
.tag-row .field-value {
  font-weight: bold;
  overflow: hidden;
  white-space: normal;
  word-break: break-word;
}
```

- [ ] **Step 5: Run to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_label_templates.py tests/test_barcode_processor.py -v`
Expected: PASS — new structural tests pass, and `TestGenerateCode128LabelsPdfIntegration` (existing smoke test) still passes unmodified, proving the restructured template still renders.

- [ ] **Step 6: Commit**

```bash
git add shopify_tool/templates/barcode_label/template.html shopify_tool/templates/barcode_label/style.css tests/test_label_templates.py
git commit -m "Fix Code-128 label TAG field overflow: full-width row instead of cramped column box"
```

---

## Task 4: Rebuild QR label to mirror the barcode label's info column

**Files:**
- Modify: `shopify_tool/templates/qr_label/template.html`
- Modify: `shopify_tool/templates/qr_label/style.css`
- Test: `tests/test_label_templates.py` (extend)

**Interfaces:**
- Consumes: the `.top-row` / `.tag-row` layout pattern from Task 3; the `sequential_num`/`courier`/`date_str`/`country`/`tag`/`item_count`/`order_number` record fields Task 1 already made `generate_qr_labels_pdf()` supply.
- Produces: nothing consumed by later tasks — this is the last content task.

- [ ] **Step 1: Extend `tests/test_label_templates.py` with the failing QR-layout test**

Append to `tests/test_label_templates.py`:

```python
class TestQrLabelLayout:
    def test_mirrors_barcode_label_info_column_and_tag_row(self):
        html = (_TEMPLATES_DIR / "qr_label" / "template.html").read_text()
        css = (_TEMPLATES_DIR / "qr_label" / "style.css").read_text()
        for marker in ("sequential_num", "courier", "date_str", "tag-row"):
            assert marker in html
        assert "overflow: hidden" in css

    def test_qr_code_encodes_order_number_not_multiline_payload(self):
        html = (_TEMPLATES_DIR / "qr_label" / "template.html").read_text()
        assert "label_tools.qr_code(order_number)" in html
```

- [ ] **Step 2: Run to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_label_templates.py -k TestQrLabelLayout -v`
Expected: FAIL — `sequential_num` not found (current QR template still only has `order_number` + QR image, from Task 1's minimal edit).

- [ ] **Step 3: Rewrite `shopify_tool/templates/qr_label/template.html`**

```html
<!DOCTYPE html>
<html>
<body>
  <div class="label">
    <div class="top-row">
      <div class="info">
        <div class="seq">#{{ sequential_num }}</div>
        <div class="courier">{{ courier }}</div>
        <div class="date">{{ date_str }}</div>
        <hr>
        <div class="field"><span class="field-label">SUM:</span><span class="field-value">{{ item_count }}</span></div>
        <hr class="thin">
        <div class="field"><span class="field-label">COU:</span><span class="field-value">{{ country }}</span></div>
      </div>
      <div class="qr-section">
        <img class="qr" src="{{ label_tools.qr_code(order_number) }}"/>
        <div class="order-number">{{ order_number }}</div>
      </div>
    </div>
    <div class="tag-row">
      <span class="field-label">TAG:</span>
      <span class="field-value" style="font-size: {{ label_tools.fit_font_block(tag, box_width_mm=55, box_height_mm=7, max_mm=3.2, min_mm=1.8) }}mm;">{{ tag }}</span>
    </div>
  </div>
</body>
</html>
```

- [ ] **Step 4: Rewrite `shopify_tool/templates/qr_label/style.css`**

```css
@page { size: 68mm 38mm; margin: 0; }

* { box-sizing: border-box; margin: 0; padding: 0; }

body { width: 68mm; height: 38mm; font-family: "JetBrains Mono", monospace; }

.label {
  width: 68mm;
  height: 38mm;
  display: flex;
  flex-direction: column;
  padding: 1mm;
}

.top-row {
  flex: 1;
  display: flex;
  flex-direction: row;
  min-height: 0;
}

.info {
  width: 22mm;
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

.qr-section {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-start;
}

.qr { width: 20mm; height: 20mm; margin-top: 1mm; }

.order-number {
  font-size: 6mm;
  font-weight: bold;
  margin-top: 1mm;
  text-align: center;
}

.tag-row {
  height: 8mm;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  border-top: 0.3mm solid black;
  padding-top: 0.5mm;
  margin-top: 0.5mm;
  overflow: hidden;
}

.tag-row .field-label { width: 9mm; font-size: 3mm; font-weight: bold; }
.tag-row .field-value {
  font-weight: bold;
  overflow: hidden;
  white-space: normal;
  word-break: break-word;
}
```

- [ ] **Step 5: Run to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_label_templates.py tests/test_barcode_processor.py -v`
Expected: PASS — new QR-layout structural tests pass, `TestGenerateQrLabelsPdfIntegration` (Task 1's tests) still pass unmodified (payload assertion is unaffected by the added display fields).

- [ ] **Step 6: Commit**

```bash
git add shopify_tool/templates/qr_label/template.html shopify_tool/templates/qr_label/style.css tests/test_label_templates.py
git commit -m "Rebuild QR label to mirror the Code-128 label's info column and tag row"
```

---

## Task 5: Full verification

No code changes — this is the merge gate confirming all four tasks integrate cleanly.

- [ ] **Step 1: Run the full test suite**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest`
Expected: All tests pass, including every test touched or added in Tasks 1-4.

- [ ] **Step 2: Run lint**

Run: `ruff check . --exclude shared`
Expected: No errors.

- [ ] **Step 3: Manual QA note (not automatable in this environment)**

Record for the user: print a real batch to the physical Citizen CL-E300 with an order carrying 4+ tags to confirm the tag row no longer clips, and generate a QR-labels batch to confirm a phone camera reads the order number correctly from the printed QR. This matches the spec's Testing section — no CI/pytest coverage exists for physical print output or camera-scan correctness.
