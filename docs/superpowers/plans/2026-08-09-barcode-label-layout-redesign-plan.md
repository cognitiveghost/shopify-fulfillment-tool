# Barcode/QR Label Layout Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite both label templates (`barcode_label/`, `qr_label/`) to fix a real print bug — the tag-row divider visually overlapping the COU/order-number text due to near-zero vertical clearance — and give Courier/TAG more visual weight, per `docs/superpowers/specs/2026-08-09-barcode-label-layout-redesign-design.md`.

**Architecture:** Same `.top-row` (info column + code column) / `.tag-row` (full-width bottom strip) structure as today, with tightened margins, resized fonts (courier and TAG bigger, seq/date/SUM/COU smaller and uniform), and `min-width: 0` flex guards added at every nesting level to fix a real WeasyPrint flexbox bug (long courier names previously pushed the barcode off the printable page edge — found and verified during design, independent of the original report).

**Tech Stack:** Jinja2 templates, CSS (WeasyPrint's flexbox implementation), pytest (`QT_QPA_PLATFORM=offscreen`), ruff.

## Global Constraints

- `QT_QPA_PLATFORM=offscreen python -m pytest` and `ruff check . --exclude shared` must pass before merge (per `CLAUDE.md`).
- Label physical dimensions stay `68mm × 38mm` (`@page` rule) — unchanged.
- Barcode/QR pixel dimensions stay exactly `41mm × 20mm` / `20mm × 20mm` — confirmed with user, do not shrink (handheld-scanner reliability).
- `shared/` is not touched by any task in this plan.
- No new dependencies.
- This is a template/CSS-only redesign — no changes to `generate_barcodes_batch()`, `generate_code128_labels_pdf()`, `generate_qr_labels_pdf()`, or any other Python logic/signature.

---

## Task 1: Rewrite Code-128 barcode label (`barcode_label/`)

**Files:**
- Modify: `shopify_tool/templates/barcode_label/template.html`
- Modify: `shopify_tool/templates/barcode_label/style.css`
- Test: `tests/test_label_templates.py` (`TestBarcodeLabelLayout`)

**Interfaces:**
- Consumes: `label_tools.barcode(order_number)`, `label_tools.fit_font_block(text, box_width_mm, box_height_mm, max_mm, min_mm)` — both unchanged, called with new box dimensions (`box_height_mm=8.5, max_mm=4.2, min_mm=2.0`, `box_width_mm=55` unchanged).
- Produces: the `.divider` / `min-width: 0` pattern Task 2 mirrors in `qr_label/`.

- [ ] **Step 1: Add the failing regression test for the flex `min-width: 0` guard**

Add this method to the existing `TestBarcodeLabelLayout` class in `tests/test_label_templates.py` (after `test_tag_font_fit_uses_full_width_box_not_old_14mm_column`):

```python
    def test_courier_and_info_column_have_min_width_guard(self):
        """Regression guard: a long courier name previously pushed .info (and the
        barcode/order-number next to it) off the printable page edge, because
        WeasyPrint's flexbox gives nested flex items an implicit min-width:auto
        that ignores white-space:nowrap/overflow:hidden unless overridden."""
        css = (_TEMPLATES_DIR / "barcode_label" / "style.css").read_text()
        assert "min-width: 0" in css
```

- [ ] **Step 2: Run to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_label_templates.py -k test_courier_and_info_column_have_min_width_guard -v`
Expected: FAIL — `assert "min-width: 0" in css` is False (current `style.css` has no such rule).

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
        <div class="divider"></div>
        <div class="field"><span class="field-label">SUM:</span><span class="field-value">{{ item_count }}</span></div>
        <div class="field"><span class="field-label">COU:</span><span class="field-value">{{ country }}</span></div>
      </div>
      <div class="barcode-section">
        <img class="barcode" src="{{ label_tools.barcode(order_number) }}"/>
        <div class="order-number">{{ order_number }}</div>
      </div>
    </div>
    <div class="tag-row">
      <span class="field-label">TAG:</span>
      <span class="field-value" style="font-size: {{ label_tools.fit_font_block(tag, box_width_mm=55, box_height_mm=8.5, max_mm=4.2, min_mm=2.0) }}mm;">{{ tag }}</span>
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
  padding: 0.6mm;
  overflow: hidden;
}

.top-row {
  height: 27mm;
  flex-shrink: 0;
  display: flex;
  flex-direction: row;
  min-height: 0;
  min-width: 0;
}

.info {
  width: 22mm;
  min-width: 0;
  display: flex;
  flex-direction: column;
  padding-right: 1mm;
}

.seq { font-size: 4.4mm; font-weight: bold; line-height: 1.1; }
.courier {
  font-size: 5.8mm;
  font-weight: bold;
  line-height: 1.1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
  width: 100%;
}
.date { font-size: 2.6mm; line-height: 1.15; }

.divider { border-top: 0.3mm solid black; margin: 0.4mm 0; }

.field { display: flex; font-size: 2.6mm; font-weight: bold; line-height: 1.15; margin: 0.2mm 0; }
.field-label { width: 7mm; }
.field-value { flex: 1; }

.barcode-section {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-start;
}

.barcode { width: 41mm; height: 20mm; margin-top: 0.4mm; }

.order-number {
  font-size: 5mm;
  font-weight: bold;
  line-height: 1.1;
  margin-top: 0.4mm;
  text-align: center;
}

.tag-row {
  height: 9.5mm;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  border-top: 0.4mm solid black;
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

- [ ] **Step 5: Run to verify it passes, and that existing structural tests still pass**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_label_templates.py -k TestBarcodeLabelLayout -v`
Expected: PASS (4 tests) — the 3 pre-existing tests (`tag-row` presence, `overflow: hidden` presence, `box_width_mm=14` absence + `fit_font_block` presence) still hold under the new markup, plus the new `min-width: 0` test.

- [ ] **Step 6: Run the barcode PDF integration smoke test to confirm the template still renders**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_barcode_processor.py -k TestGenerateCode128LabelsPdfIntegration -v`
Expected: PASS (2 tests, unmodified) — proves the restructured template still renders through the real `blabel`/WeasyPrint pipeline without raising.

- [ ] **Step 7: Commit**

```bash
git add shopify_tool/templates/barcode_label/template.html shopify_tool/templates/barcode_label/style.css tests/test_label_templates.py
git commit -m "Redesign Code-128 label: fix tag-row clearance, emphasize courier/TAG, fix flex min-width overflow"
```

---

## Task 2: Rewrite QR label (`qr_label/`) to mirror Task 1

**Files:**
- Modify: `shopify_tool/templates/qr_label/template.html`
- Modify: `shopify_tool/templates/qr_label/style.css`
- Test: `tests/test_label_templates.py` (`TestQrLabelLayout`)

**Interfaces:**
- Consumes: `label_tools.qr_code(order_number)`, `label_tools.fit_font_block(...)` — same call as Task 1, unchanged signature.
- Produces: nothing consumed by later tasks — this is the last template task.

- [ ] **Step 1: Add the failing regression test for the QR label's `min-width: 0` guard**

Add this method to the existing `TestQrLabelLayout` class in `tests/test_label_templates.py` (after `test_qr_code_encodes_order_number_not_multiline_payload`):

```python
    def test_courier_and_info_column_have_min_width_guard(self):
        """Same regression guard as the Code-128 label (see
        TestBarcodeLabelLayout.test_courier_and_info_column_have_min_width_guard)
        -- the QR label shares the same .info/.courier structure and needs the
        same fix."""
        css = (_TEMPLATES_DIR / "qr_label" / "style.css").read_text()
        assert "min-width: 0" in css
```

- [ ] **Step 2: Run to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_label_templates.py -k "TestQrLabelLayout and test_courier_and_info_column_have_min_width_guard" -v`
Expected: FAIL — current `qr_label/style.css` has no `min-width: 0` rule.

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
        <div class="divider"></div>
        <div class="field"><span class="field-label">SUM:</span><span class="field-value">{{ item_count }}</span></div>
        <div class="field"><span class="field-label">COU:</span><span class="field-value">{{ country }}</span></div>
      </div>
      <div class="qr-section">
        <img class="qr" src="{{ label_tools.qr_code(order_number) }}"/>
        <div class="order-number">{{ order_number }}</div>
      </div>
    </div>
    <div class="tag-row">
      <span class="field-label">TAG:</span>
      <span class="field-value" style="font-size: {{ label_tools.fit_font_block(tag, box_width_mm=55, box_height_mm=8.5, max_mm=4.2, min_mm=2.0) }}mm;">{{ tag }}</span>
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
  padding: 0.6mm;
  overflow: hidden;
}

.top-row {
  height: 27mm;
  flex-shrink: 0;
  display: flex;
  flex-direction: row;
  min-height: 0;
  min-width: 0;
}

.info {
  width: 22mm;
  min-width: 0;
  display: flex;
  flex-direction: column;
  padding-right: 1mm;
}

.seq { font-size: 4.4mm; font-weight: bold; line-height: 1.1; }
.courier {
  font-size: 5.8mm;
  font-weight: bold;
  line-height: 1.1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
  width: 100%;
}
.date { font-size: 2.6mm; line-height: 1.15; }

.divider { border-top: 0.3mm solid black; margin: 0.4mm 0; }

.field { display: flex; font-size: 2.6mm; font-weight: bold; line-height: 1.15; margin: 0.2mm 0; }
.field-label { width: 7mm; }
.field-value { flex: 1; }

.qr-section {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-start;
}

.qr { width: 20mm; height: 20mm; margin-top: 0.4mm; }

.order-number {
  font-size: 5mm;
  font-weight: bold;
  line-height: 1.1;
  margin-top: 0.4mm;
  text-align: center;
}

.tag-row {
  height: 9.5mm;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  border-top: 0.4mm solid black;
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

- [ ] **Step 5: Run to verify it passes, and that existing structural tests still pass**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_label_templates.py -v`
Expected: PASS (7 tests total — 4 from `TestBarcodeLabelLayout`, 3 from `TestQrLabelLayout` [2 pre-existing + 1 new]).

- [ ] **Step 6: Run the QR PDF integration smoke test to confirm the template still renders**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_barcode_processor.py -k TestGenerateQrLabelsPdfIntegration -v`
Expected: PASS (3 tests, unmodified).

- [ ] **Step 7: Commit**

```bash
git add shopify_tool/templates/qr_label/template.html shopify_tool/templates/qr_label/style.css tests/test_label_templates.py
git commit -m "Redesign QR label to mirror the Code-128 label's new layout and flex fix"
```

---

## Task 3: Add stress-case coverage (long courier name + multi-tag order)

**Files:**
- Modify: `tests/test_barcode_processor.py` (`TestGenerateCode128LabelsPdfIntegration`, `TestGenerateQrLabelsPdfIntegration`)

**Interfaces:**
- Consumes: `generate_code128_labels_pdf()`, `generate_qr_labels_pdf()` — both unchanged, from `shopify_tool/barcode_processor.py`.
- Produces: nothing consumed by later tasks — this is the last task.

**Note on why this task doesn't reproduce a failing test first:** the flex-overflow bug this covers didn't raise an exception or change the PDF page count — WeasyPrint silently paints overflowing content past the page edge rather than crashing (this is exactly why the CSS-marker test in Task 1/2 exists: it's the only automated guard that meaningfully fails against the old, unfixed CSS). This task instead adds broader input-shape coverage (long courier name, four pipe-separated tags, higher item_count) to the existing smoke-test style, so it's write-then-verify-passes rather than red-green.

- [ ] **Step 1: Add the stress-case test to `TestGenerateCode128LabelsPdfIntegration`**

Add this method in `tests/test_barcode_processor.py`, after `test_empty_orders_raises_value_error` in `TestGenerateCode128LabelsPdfIntegration`:

```python
    def test_long_courier_and_multi_tag_order_renders_without_crash(self, tmp_path):
        """Coverage for the input shape that surfaced the flex min-width overflow
        bug during the 2026-08-09 layout redesign (see
        docs/superpowers/specs/2026-08-09-barcode-label-layout-redesign-design.md):
        a long courier name and a multi-segment tag value. The bug itself doesn't
        raise or change page count -- the real regression guard is the CSS
        min-width:0 marker test in test_label_templates.py -- this just confirms
        the template still renders end-to-end for this input shape."""
        output_pdf = tmp_path / "stress.pdf"
        result = generate_code128_labels_pdf(
            [self._order(
                courier="DHL Express International",
                tag="GIFT+1|GIFT+2|PRIORITY|FRAGILE",
                item_count=15,
            )],
            output_pdf,
        )
        assert result == output_pdf
        reader = pypdf.PdfReader(str(output_pdf))
        assert len(reader.pages) == 1
```

- [ ] **Step 2: Run to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_barcode_processor.py -k test_long_courier_and_multi_tag_order_renders_without_crash -v`
Expected: PASS (1 test — only `TestGenerateCode128LabelsPdfIntegration`'s copy exists so far; Step 3 below adds the QR one).

- [ ] **Step 3: Add the equivalent stress-case test to `TestGenerateQrLabelsPdfIntegration`**

Add this method in `tests/test_barcode_processor.py`, after `test_qr_payload_is_order_number_only` in `TestGenerateQrLabelsPdfIntegration`:

```python
    def test_long_courier_and_multi_tag_order_renders_without_crash(self, tmp_path):
        """See TestGenerateCode128LabelsPdfIntegration's test of the same name --
        same stress-case input, same rationale, applied to the QR label path."""
        output_pdf = tmp_path / "qr_stress.pdf"
        result = generate_qr_labels_pdf(
            [self._order(
                courier="DHL Express International",
                tag="GIFT+1|GIFT+2|PRIORITY|FRAGILE",
                item_count=15,
            )],
            output_pdf,
        )
        assert result == output_pdf
        reader = pypdf.PdfReader(str(output_pdf))
        assert len(reader.pages) == 1
```

- [ ] **Step 4: Run to verify both pass**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_barcode_processor.py -k test_long_courier_and_multi_tag_order_renders_without_crash -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add tests/test_barcode_processor.py
git commit -m "Add long-courier/multi-tag stress-case coverage for both label PDF paths"
```

---

## Task 4: Full verification

No code changes — this is the merge gate confirming all three tasks integrate cleanly.

- [ ] **Step 1: Run the full test suite**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest`
Expected: All tests pass, including every test touched or added in Tasks 1-3.

- [ ] **Step 2: Run lint**

Run: `ruff check . --exclude shared`
Expected: No errors.

- [ ] **Step 3: Manual QA note (not automatable in this environment)**

Record for the user: print a real batch to the physical Citizen CL-E300 with an order carrying a long courier name (e.g. "DHL Express International") and 4+ tags, confirm no visual clipping/overlap anywhere on the label and that the barcode/QR still scan reliably at the new (slightly smaller-margin) proportions. This matches the design spec's Testing section — no CI/pytest coverage exists for physical print output, scan reliability, or pixel-level visual clearance (that was verified once, manually, during design — see the spec's "Verification performed" section).
