# Phase 12 Bundle 1 — bulk actions, window frame, Reference Labels print, pikepdf

- **Date:** 2026-09-24
- **Todoist:** `6hcMGGJxvr8JQXRV` (four raw items nested under it)
- **Repos:** `shopify-fulfillment-tool` (primary), `packing-tool` (item 2 only,
  because the defect lives in `shared/`)
- **Classification:** bounded. Four fixes to flows that already exist; no new
  subsystem. No mockup: the only visible change is that labels print at the right size.
- **Plan:** `docs/superpowers/plans/2026-09-24-phase12-bundle1-plan.md`

## Owner decisions (AskUserQuestion, 2026-09-24)

| # | Question | Answer |
|---|---|---|
| D1 | Where does the window-frame fix land? | Fix `shared/` in packing-tool and sync it here, so both apps get it |
| D2 | Which setup prints Reference Labels small? | Driver mode (the print dialog opens) |
| D3 | pypdf → pikepdf? | Migrate, as a separate commit |
| D4 | Which library reads page text for matching? | Keep pypdf for text; pikepdf does open, layout and save |

Decided by the agent (reversible): item 1 is fixed in the selection matcher, not
by forcing `Order_Number` to `str` at load. Forcing it at load would change every
export and packing list for numeric-order clients, which is a much larger change.

---

## 1. Bulk actions do nothing for clients with numeric order numbers

### Root cause (verified)

`SelectionHelper.set_selected_orders` (`gui/selection_helper.py`) matches with a
raw `df["Order_Number"].isin(wanted)`.

- The results page keys every order by `String(o.Order_Number)`
  (`gui/web/results.js:639`), and `ResultsBridge._orders` casts to `str`. So the
  order numbers always arrive as strings.
- The analysis forces only SKU columns to `str` at load
  (`core._get_sku_dtype_dict`). A shop whose order numbers are plain digits
  (a non-Shopify client with mapped columns) gets an **int64** `Order_Number`
  column.
- `int64.isin({"12345"})` matches nothing, the selection is empty, and every
  bulk verb exits silently at `if not selected_indexes: return`.
- **Copy** is the only bulk verb that works, because it never leaves the page.
  The single-order pane verbs also work, because they go through
  `ActionsHandler._order_mask`, which already compares `astype(str).str.strip()`.

### Fix

There is one rule for matching an order number: compare on the stripped string
form. It moves out of `ActionsHandler._order_mask` into a module-level function in
`gui/selection_helper.py`:

```python
def order_number_mask(df, order_numbers) -> pd.Series:
    """Rows of df whose Order_Number is one of order_numbers.

    Order numbers arrive as int, float or str depending on the CSV and on
    which tier sent them, so both sides go through str + strip.
    """
    wanted = {str(n).strip() for n in order_numbers}
    return df["Order_Number"].astype(str).str.strip().isin(wanted)
```

- `SelectionHelper.set_selected_orders` uses it in place of the raw `isin`.
- `ActionsHandler._order_mask(order_number, df=None)` keeps its signature and
  becomes a one-line call: `order_number_mask(df, [order_number])`. Its docstring
  points at the new function.
- The later `isin(unique_orders)` calls inside the bulk verbs stay as they are.
  They compare the frame's own values with themselves, so the dtype always agrees.

Known limit, accepted: a *float* `Order_Number` column (only possible when some
order number is missing) stringifies to `"12345.0"` and still won't match. That is
the same limit `_order_mask` already has; nobody has reported it.

---

## 2. The window frame restores under the top edge of the screen

### Root cause (verified against the Qt 6.11 source, `qwidget.cpp`)

`shared/theme.py::restore_window_geometry` calls `window.restoreGeometry(raw)`,
then reads `window.geometry()`, clamps it with `clamp_geometry` to
`availableGeometry()`, and calls `window.setGeometry(...)`. It runs from the
MainWindow constructor, **before `show()`**, in both apps
(`gui/main_window_pyside.py:77` here, `gui/main_window.py:197` in packing-tool).
That causes two faults:

1. `geometry()` is the **client** rect, which excludes the title bar. Clamping the
   client top to `avail.y` puts the title bar above the available area. The top of
   the frame ends up under the top edge of the screen or a taskbar docked at the top.
2. When the saved state is maximized, `restoreGeometry` has already set
   `WindowMaximized`. Qt's source says it outright: *"Setting a geometry on an
   already maximized window causes this to be restored into a broken,
   half-maximized state (QTBUG-4397)."* Our `setGeometry` writes the full-screen
   rect in as the normal geometry. Un-maximizing then brings back a screen-sized
   window with its frame off the top. That's the "sometimes resizes on full again"
   in the report.

`QWidget::restoreGeometry` already does the job correctly. Its docs say *"If the
restored geometry is off-screen, it will be modified to be inside the available
screen geometry"*. `checkRestoredGeometry` adds `PM_TitleBarHeight`, keeps the size
2 px under the screen size, and handles maximized and fullscreen state itself.

### Fix (packing-tool, then sync)

Delete the clamp. `restore_window_geometry` becomes:

```python
def restore_window_geometry(window, settings, key: str = "window_geometry") -> bool:
    """Restore previously-saved geometry.

    Returns True if geometry was restored, False if there was nothing saved
    (caller should fall back to its own default size in that case).

    Qt's restoreGeometry already moves an off-screen rect back inside the
    available screen, frame included, and keeps maximized state intact. Do
    not clamp again or call setGeometry after it: that re-clamps the client
    rect without its title bar and breaks a maximized window (QTBUG-4397).
    """
    raw = settings.value(key)
    if raw is None:
        return False
    return bool(window.restoreGeometry(raw))
```

- Delete `clamp_geometry` from `shared/theme.py`. Its only caller is this function.
  Also delete its four tests in `packing-tool/tests/test_theme.py`.
- Add a test in packing-tool that fails today and passes after the fix. See the plan, Task 2.
- Sync into this repo with `scripts/sync_shared.py`. Neither caller changes.

**Merge order:** the shopify CI job `verify` diffs `shared/` against packing-tool's
default branch. Merge the packing-tool PR **first**. Until then the shopify PR's
drift check fails, and that is expected.

---

## 3. Driver-mode prints come out smaller than Adobe's

### Root cause (measured headlessly)

`gui/pdf_printing.py::_print_pdf_driver_mode` draws each page into
`printer.pageRect(DevicePixel)`, which is the area **inside** the page margins.
Qt's default `QPrinter` margins are **10 pt (3.53 mm) on every side**. So a
100×150 mm label prints at 92.9×142.9 mm: 93% wide and 95% tall. It is smaller,
and slightly squashed, because the two axes scale by different amounts. Adobe's
"Actual size" prints at 100%.

There is also a second fault. `pageRect(DevicePixel)` has the margin as its
origin, and with full-page off the painter's origin already sits at the margin.
The label is therefore **offset twice**: pushed right and down by an extra
margin, then clipped at the right and bottom edges. Measured on a 100×150 mm
page with a border 1 mm in from each edge: the ink starts 7.6% in from the left
and 5% down from the top, but runs to the right and bottom edges.

The deliberate 88% shrink for the **reference strip** (`pdf_processor._CONTENT_SCALE`)
is baked into the PDF, so Adobe shows it too. It is not part of this defect and
stays as it is.

### Fix: driver mode prints at actual size

- Call `printer.setFullPage(True)` before the dialog, so the paper rect is the
  drawing area and margins no longer shrink the label.
- For each page, fit the PDF page (points) **uniformly** into
  `printer.paperRect(DevicePixel)` and centre it. `_apply_default_page_size`
  already sets the paper size from the PDF's first page, so normally the fit is
  1:1. If the operator picks other paper in the dialog, the label scales
  uniformly to fit it and is never distorted.
- Render the QPdfDocument page at the target rect's size, as today, so the raster
  stays at printer resolution.

A pure helper holds the geometry, so it can be tested without a printer:

```python
def _fit_rect(page_pt: QSizeF, paper: QRectF) -> QRectF:
    """page_pt scaled uniformly to fit paper, centred in it."""
```

The raw ZPL path is unchanged: it has no margins (D2).

---

## 4. The Reference Labels overlay moves from pypdf to pikepdf (separate commit)

### What changes

In `shopify_tool/pdf_processor.py::process_reference_labels`:

| Job | Today | After |
|---|---|---|
| Open and count pages | `pypdf.PdfReader` | `pikepdf.open` (qpdf repairs damaged files on open) |
| Extract text for matching | `pypdf` `page.extract_text()` | **unchanged**: pypdf (D4) |
| Bake `/Rotate`, shrink content to 88%, stamp the reference strip | `transfer_rotation_to_content` + `add_transformation` + `merge_page` | a new blank page at the page's *visual* size, then `Page.add_overlay(courier_page, rect_top_88%)` then `Page.add_overlay(strip_page, full_rect)` |
| Unmatched page | copied through | `out.pages.append(src.pages[i])` |
| Save | `PdfWriter.write` | `out.save(path)` |

`create_reference_overlay` still draws the strip with reportlab and returns a
`BytesIO`. Its signature and drawing code are unchanged.

A throwaway prototype (not committed; it lives in the Stage A job's tmp directory)
settled that pikepdf does this correctly:

- `add_overlay` bakes `/Rotate` in. A 432×288 page with `/Rotate` 90 or 270 comes
  out 288×432, content upright as a viewer shows it. The content sits centred in
  the top 88%, with the strip below it. This matches today's pypdf output.
- **Gotcha:** keep the overlay's source `pikepdf.Pdf` referenced until
  `add_overlay` returns. A temporary like `strip(...).pages[0]` raises
  `RuntimeError: QPDFPageObjectHelper::getFormXObjectForPage called with a direct object`.
- The visual size is the mediabox width and height, swapped when
  `int(page.obj.get("/Rotate", 0)) % 180` is non-zero.

Text extraction was also compared on 36 real courier pages in 6 files, including
a malformed FedEx PDF. The PostOne and tracking tokens from pypdf and pypdfium2
were identical on every page, but the full normalized text differed on 22 pages.
So the owner chose to keep pypdf for text (D4), and matching behaves exactly as
it does today.

Text is read through a `pypdf.PdfReader` over the same file. If pypdf can't open a
file that pikepdf opened, log a warning and treat every page's text as `""`. The
pages then come out unmatched in their original order. Today the whole job fails
with `InvalidPDFError` in that case.

### Dependency and packaging

- `requirements.txt`: add `pikepdf>=9.0` and keep `pypdf` (still used for text).
- `.github/workflows/build_release.yml`, step "Verify bundled assets shipped": also
  fail when no `pikepdf` directory is in `dist\ShopifyFulfillmentTool`.
  pyinstaller-hooks-contrib ships a pikepdf hook, so no `--collect` flag is expected.
  **The Windows build runs only when a PR has the `windows-build` label.** Stage C
  must add that label and confirm the build passes before calling the bundle done.

---

## Testing seams

| Item | Seam | Test file |
|---|---|---|
| 1 | `order_number_mask`, `SelectionHelper.set_selected_orders` with an int64 frame; one bulk verb end-to-end through `ActionsHandler` | `tests/test_selection_helper.py`, `tests/test_actions_handler_bulk.py` |
| 2 | `restore_window_geometry` on a real `QMainWindow` (offscreen) | `packing-tool/tests/test_theme.py` |
| 3 | `_fit_rect` (pure); `_print_pdf_driver_mode(output_path=...)`, where the output page's ink spans the full page | `tests/test_pdf_printing.py` |
| 4 | `process_reference_labels` output: page count, visual page size for `/Rotate` 0/90/270, reference text present, unmatched pages unchanged | `tests/test_pdf_processor.py` |

## Out of scope

- Forcing `Order_Number` to `str` at load.
- Changing the reference-strip shrink (`_CONTENT_SCALE`).
- The raw ZPL path.
- Replacing pypdf in tests.
