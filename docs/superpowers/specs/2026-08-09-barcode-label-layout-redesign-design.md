# Barcode/QR Label Layout Redesign — Design

## Problem

A real warehouse print (`ALL_ORDERS_ALMADERM_barcodes.pdf` / `_qr_labels.pdf`, courier
"Speedy", country "BG", tag "2|M|M++") showed the `.tag-row` divider line visually cutting
through the "COU: BG" text and the order-number underneath the barcode/QR code.

Root cause, confirmed by rendering the actual templates through `blabel`/WeasyPrint and
measuring pixel positions against the CSS math (not guessed): this was **not** a rendering
glitch — the `.tag-row` border-top was painting exactly where the CSS placed it (measured
29.01–29.18mm from top vs. 29mm predicted). The real defect was **zero vertical clearance**:
the info column (7 stacked rows: seq/courier/date/divider/SUM/divider/COU) and the
barcode-section (20mm barcode + margin + order-number text, ≈29mm) both came within ~0mm of
the 28mm budget available before the tag-row's fixed 8mm bottom strip, so COU text and the
order-number sat directly on top of the divider on the physical print.

The user separately asked to redesign the layout "to something better since we have a blabel
construction" rather than just patch the spacing.

## Goals

1. Fix the root cause: guarantee real, verified vertical clearance between the info
   column/order-number content and the `.tag-row` divider, on both `barcode_label/` and
   `qr_label/` templates.
2. Full visual rework (per user's explicit choice, not just a spacing patch): give Courier
   and TAG the most visual weight; seq#/date/SUM/COU become smaller, uniform utility rows.
3. Verify the result by actually rendering through the real `blabel`/WeasyPrint pipeline and
   measuring pixel positions — the same technique that found the root cause — not by CSS math
   alone (which is what produced the original, insufficiently-verified layout).

## Non-goals

- Barcode/QR pixel dimensions. Confirmed with user: stay exactly `41mm × 20mm` (barcode) /
  `20mm × 20mm` (QR) — no shrinking, to protect handheld-scanner reliability.
- The 68mm × 38mm physical label size, or the QR/Code-128 physical-separation rule (separate
  print jobs) — both settled in prior specs, unchanged here.
- The underlying field set (seq, courier, date, SUM/item_count, COU/country, TAG, order
  number) or `generate_barcodes_batch()`'s record shape — this is a template/CSS-only
  redesign, not a data model change.
- Reference Labels (`pdf_processor.py`) — untouched, unrelated system.

## Design

### Layout structure (both templates)

Same `.top-row` (fixed-height, two-column: `.info` + `.barcode-section`/`.qr-section`) +
full-width `.tag-row` structure as before, with these changes:

**Sizing/spacing** (frees the room needed for real clearance):
- `.label` padding: `1mm` → `0.6mm`, plus `overflow: hidden` added as a hard safety net.
- `.top-row` height: fixed `27mm` (was implicit `flex:1` filling whatever was left — now
  explicit, so `.tag-row` gets the remainder deterministically: `38 - 0.6*2 - 27 ≈ 9.8mm`).
- `.tag-row` height: `8mm` → `9.5mm` (taller — TAG is now emphasized, see below).
- Barcode/QR image `margin-top`, order-number `margin-top`: `1mm` → `0.4mm`.
- Divider between SUM and COU rows removed (one divider after date is enough once those
  rows are visually uniform/tight — see Hierarchy below); still present via `.divider` — a
  plain bordered `<div>`, functionally identical to the old `<hr>` visually — no behavioral
  difference from `<hr>`, kept as `<div>` only because it was already the working element
  during verification.

**Hierarchy** (per user's "Courier + Tag" choice):
- `.courier`: `5mm` → `5.8mm` bold (biggest element in the info column now).
- `.tag-row .field-value` (via `fit_font_block`): `max_mm` `3.2` → `4.2`, `min_mm` `1.8` →
  `2.0`, box height `7mm` → `8.5mm` (matches the taller row).
- `.seq`: `5.5mm` → `4.4mm` (still bold/prominent, no longer competing with courier).
- `.date`, `.field` (SUM/COU rows): unified at `2.6mm`, tight `1.15` line-height — a uniform
  utility row size, closer to the original D-4 intent of a consistent label:value grid for
  the secondary fields.
- `.order-number`: `6mm` → `5mm` (still large/legible, trimmed to fit the tighter budget).

### Bug found during verification: nested-flex `min-width: auto` overflow

Stress-testing with a long courier name ("DHL Express International") surfaced a real,
previously-latent WeasyPrint flexbox bug, independent of the original report: `.courier`
(inside `.info`, a flex column, itself a flex item of `.top-row`) ignored its `white-space:
nowrap; overflow: hidden; text-overflow: ellipsis` and pushed `.info` — and the whole
`.top-row` — wider than the label, shoving the barcode/order-number off the printable edge.

Root cause: WeasyPrint (like browsers, per the flexbox spec's "automatic minimum size")
gives flex items an implicit `min-width: auto`/`min-height: auto` that refuses to shrink
below the content's intrinsic size unless overridden. This applied at **every** nesting
level in the chain (`.top-row`, `.info`, and `.courier` itself all needed their own explicit
override) — fixing only the outermost container did not fix it; confirmed by iterating one
level at a time and re-rendering.

Fix: `min-width: 0` added to `.top-row`, `.info`, and `.courier` (plus `width: 100%` on
`.courier` so the stretch is explicit rather than relying on default `align-items: stretch`
alone), and `min-width: 0` added to `.barcode-section`/`.qr-section` for symmetry. This is a
standard, minimal fix for the well-known CSS flexbox "min-size content trap" — no
architectural change.

### Verification performed (not just CSS math)

Rendered both templates through the real `generate_code128_labels_pdf()`/
`generate_qr_labels_pdf()` pipeline (real barcode/QR SVGs, real bundled JetBrains Mono font),
rasterized at 300dpi, and measured pixel positions directly:

- Real data (Speedy/BG/2|M|M++, matching the original bug report): tag-row divider at
  28.08–28.42mm; last dark pixel in the info column above it at 21.74mm (**6.34mm
  clearance**); last dark pixel in the barcode/order-number column above it at 25.80mm
  (**2.28mm clearance** — the tighter of the two, since the barcode height is fixed).
- Stress case (courier "DHL Express International", tag
  "GIFT+1|GIFT+2|PRIORITY|FRAGILE", item_count 15): same clearance numbers (content height
  is fixed regardless of text length once truncation/wrapping kicks in); courier correctly
  truncates to "DHL E…"; barcode/order-number fully on-page; wrapped 2-line TAG value
  reaches 36.28mm of the 38mm label height (1.72mm clearance from the bottom edge).

Both label types (Code-128 and QR) produce the same numbers — QR's image is also 20mm tall,
so the vertical budget math is identical; only the code image's own markup/class names
differ (`.barcode`/`.barcode-section` vs. `.qr`/`.qr-section`).

### Final CSS values (both `barcode_label/style.css` and `qr_label/style.css`)

```css
@page { size: 68mm 38mm; margin: 0; }
* { box-sizing: border-box; margin: 0; padding: 0; }
body { width: 68mm; height: 38mm; font-family: "JetBrains Mono", monospace; }

.label { width: 68mm; height: 38mm; display: flex; flex-direction: column; padding: 0.6mm; overflow: hidden; }

.top-row { height: 27mm; flex-shrink: 0; display: flex; flex-direction: row; min-height: 0; min-width: 0; }

.info { width: 22mm; min-width: 0; display: flex; flex-direction: column; padding-right: 1mm; }

.seq { font-size: 4.4mm; font-weight: bold; line-height: 1.1; }
.courier {
  font-size: 5.8mm; font-weight: bold; line-height: 1.1;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  min-width: 0; width: 100%;
}
.date { font-size: 2.6mm; line-height: 1.15; }

.divider { border-top: 0.3mm solid black; margin: 0.4mm 0; }

.field { display: flex; font-size: 2.6mm; font-weight: bold; line-height: 1.15; margin: 0.2mm 0; }
.field-label { width: 7mm; }
.field-value { flex: 1; }

/* .barcode-section (Code-128) / .qr-section (QR) */
.barcode-section { flex: 1; min-width: 0; display: flex; flex-direction: column; align-items: center; justify-content: flex-start; }
.barcode { width: 41mm; height: 20mm; margin-top: 0.4mm; }
/* QR variant: .qr { width: 20mm; height: 20mm; margin-top: 0.4mm; } */

.order-number { font-size: 5mm; font-weight: bold; line-height: 1.1; margin-top: 0.4mm; text-align: center; }

.tag-row {
  height: 9.5mm; flex-shrink: 0; display: flex; align-items: center;
  border-top: 0.4mm solid black; padding-top: 0.5mm; margin-top: 0.5mm; overflow: hidden;
}
.tag-row .field-label { width: 9mm; font-size: 3mm; font-weight: bold; }
.tag-row .field-value { font-weight: bold; overflow: hidden; white-space: normal; word-break: break-word; }
```

(`color: #333` on `.date`, used only in the scratch mockup for visual contrast during
brainstorming, is intentionally **not** carried into this final spec — the Citizen CL-E300
is a monochrome direct-thermal printer, so grayscale ink has no defined behavior; the date
row stays plain black like every other field.)

### Final template structure (both, code-image line differs as noted)

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
      <div class="barcode-section"> <!-- qr-section for QR label -->
        <img class="barcode" src="{{ label_tools.barcode(order_number) }}"/> <!-- .qr / label_tools.qr_code(order_number) for QR label -->
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

## Testing

Per `CLAUDE.md`: `QT_QPA_PLATFORM=offscreen python -m pytest` and
`ruff check . --exclude shared` must pass before merge.

- `tests/test_label_templates.py` (existing structural tests): all currently-asserted
  markers (`tag-row`, `overflow: hidden`, `fit_font_block`, `box_width_mm=14` absence,
  `sequential_num`/`courier`/`date_str` presence, `label_tools.qr_code(order_number)`) remain
  true under the new markup — no test changes needed for those.
- New test in `tests/test_label_templates.py`: assert `min-width: 0` appears in both
  `style.css` files (regression guard for the nested-flex overflow bug found during this
  redesign — cheap structural proxy, consistent with this test file's existing style of
  asserting CSS markers rather than rendering+rasterizing in CI).
- Extend `tests/test_barcode_processor.py`'s existing PDF-integration smoke tests with one
  case using a long courier name (e.g. "DHL Express International") and a multi-tag value —
  asserts rendering doesn't raise and produces the correct page count, matching this test
  file's existing smoke-test style (structural/non-crashing, not pixel-level).
- **Not automated** (matches this repo's existing pattern of deferring visual/print
  correctness to manual QA — see the two prior label specs' Testing sections): the pixel-level
  clearance measurement performed during this design (rendering + rasterizing + measuring
  black-pixel rows) was a one-time verification step, not added as a CI test. Manual QA note
  carried forward: print a real batch to the physical Citizen CL-E300 with an order carrying
  4+ tags and a long courier name, confirm no visual clipping/overlap and that the barcode/QR
  still scan reliably.

## Files touched

- `shopify_tool/templates/barcode_label/template.html` — rewritten per Final template
  structure above
- `shopify_tool/templates/barcode_label/style.css` — rewritten per Final CSS values above
- `shopify_tool/templates/qr_label/template.html` — same structure, QR-specific code image
  line
- `shopify_tool/templates/qr_label/style.css` — same values, `.qr`/`.qr-section` instead of
  `.barcode`/`.barcode-section`
- `tests/test_label_templates.py` — new `min-width: 0` regression assertion
- `tests/test_barcode_processor.py` — extended smoke test (long courier + multi-tag case)
