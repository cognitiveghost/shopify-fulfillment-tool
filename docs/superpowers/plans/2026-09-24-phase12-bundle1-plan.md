# Phase 12 Bundle 1 Implementation Plan

> **For agentic workers:** Execute in-session with superpowers:executing-plans (the
> roadmap runner forbids subagents at Stage B). Steps use checkbox (`- [ ]`) syntax.

**Goal:** Four fixes. Bulk actions work for clients whose order numbers are numeric.
The window no longer restores with its frame off-screen. Driver-mode prints come
out at actual size. The Reference Labels overlay moves from pypdf to pikepdf.

**Architecture:** Each fix goes where every caller passes through:
- item 1: one order-number matcher in `gui/selection_helper.py`
- item 2: the geometry helper in packing-tool's `shared/theme.py`, synced here
- item 3: the print loop in `gui/pdf_printing.py`
- item 4: page handling in `shopify_tool/pdf_processor.py`

**Tech Stack:** Python 3.11+, PySide6 6.11, pandas, pytest, reportlab, pypdf (text
only after this change), pikepdf (new), pypdfium2 (tests).

**Spec:** `docs/superpowers/specs/2026-09-24-phase12-bundle1-design.md`. Read it
first: it holds the verified root causes and the owner's decisions D1–D4.

## Global Constraints

- Worktree `.claude/worktrees/phase12-bundle1`, branch `worktree-phase12-bundle1`.
  If `.venv` is missing, run `./scripts/setup_venv.sh` first.
- Test command: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest` (add
  `-p no:randomly` for a stable full run). Lint: `.venv/bin/ruff check . --exclude shared`.
- **Never hand-edit `shopify-fulfillment-tool/shared/`.** Item 2 is edited in
  packing-tool, then synced with `scripts/sync_shared.py`.
- Use `/usr/bin/git`, one plain command per call. Commit with
  `git commit -F <file>`, the message file written to `$CLAUDE_JOB_DIR/tmp`. End
  every message with the Co-Authored-By line from the session's attribution reminder.
- The `ruff-on-edit` hook strips an import whose use is not in the same Edit. Add
  each import and its first use in one Edit.
- Keep pypdf in `requirements.txt` (D4). Add `pikepdf>=9.0`.
- Item 4 is its **own commit** (D3). Items 1–3 are one commit each.
- No UI calls from background threads, no hardcoded colours. This bundle adds no UI.

## Review Focus

1. **Whitespace or mixed types in order numbers.** An int64 frame queried with
   `" 10443 "`, and a str frame queried with `10443`, must both select order
   10443. (Task 1)
2. **The operator picks other paper in the print dialog.** The label must scale
   uniformly and sit centred, never stretched. (Task 3, `_fit_rect` with paper
   of a different aspect)
3. **A file pikepdf opens but pypdf cannot.** The job must still finish, with
   every page unmatched and in its original order, not raise `InvalidPDFError`.
   (Task 4)
4. **A mixed batch.** Matched pages are stamped, and unmatched pages pass through
   untouched, keeping their `/Rotate`. (Task 4)
5. **The input PDF stays locked after processing.** Windows can't overwrite or
   delete a file pikepdf still holds. The source `Pdf` must be closed after
   processing. A `finally` covers the error path. (Task 4)

---

### Task 1: Bulk actions match order numbers of any dtype

**Files:**
- Modify: `gui/selection_helper.py` (add `order_number_mask`, use it in `set_selected_orders`)
- Modify: `gui/actions_handler.py:910-919` (`_order_mask` delegates)
- Test: `tests/test_selection_helper.py`, `tests/test_actions_handler_bulk.py`

**Interfaces:**
- Produces: `order_number_mask(df: pd.DataFrame, order_numbers) -> pd.Series`
  (bool mask), in `gui/selection_helper.py`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_selection_helper.py`:

```python
from gui.selection_helper import order_number_mask


def _int_order_frame():
    # A non-Shopify client whose order numbers are plain digits: pandas
    # loads the column as int64, while the page always sends strings.
    return pd.DataFrame(
        {"Order_Number": [10443, 10443, 10444], "SKU": ["A", "B", "C"], "Quantity": [1, 1, 1]}
    )


def test_set_selected_orders_matches_int_order_numbers_sent_as_str():
    helper = SelectionHelper(_FakeMainWindow(_int_order_frame()))
    helper.set_selected_orders(["10443"])
    assert helper.get_selected_source_rows() == [0, 1]


def test_order_number_mask_strips_and_crosses_types():
    df = _int_order_frame()
    assert order_number_mask(df, [" 10444 "]).tolist() == [False, False, True]
    str_df = df.assign(Order_Number=df["Order_Number"].astype(str))
    assert order_number_mask(str_df, [10443]).tolist() == [True, True, False]
```

Append to `tests/test_actions_handler_bulk.py`:

```python
def test_bulk_change_status_works_for_int_order_numbers(handler, mw):
    """A non-Shopify client: int64 Order_Number, page sends strings."""
    df = mw.analysis_results_df
    mw.analysis_results_df = df.assign(Order_Number=df["Order_Number"].astype(int))
    handler.bulk_change_status(["10443", "10444"], False)
    written = mw.analysis_results_df.loc[
        mw.analysis_results_df["Order_Number"].isin([10443, 10444]),
        "Order_Fulfillment_Status",
    ]
    assert set(written) == {"Not Fulfillable"}
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_selection_helper.py tests/test_actions_handler_bulk.py -q -p no:randomly`
Expected: ImportError for `order_number_mask`, and the bulk test FAILS with the status unchanged.

- [ ] **Step 3: Implement**

In `gui/selection_helper.py`, add at module level (above the class):

```python
def order_number_mask(df: pd.DataFrame, order_numbers) -> pd.Series:
    """Rows of df whose Order_Number is one of order_numbers.

    Order numbers arrive as int, float or str depending on the CSV and on
    which tier sent them (the results page always sends str), so both sides
    go through str + strip. The one matching rule for an order number.
    """
    wanted = {str(n).strip() for n in order_numbers}
    return df["Order_Number"].astype(str).str.strip().isin(wanted)
```

In `set_selected_orders`, replace the last line:

```python
        self.checked_rows = set(df.index[order_number_mask(df, wanted)])
```

In `gui/actions_handler.py`, make `_order_mask` delegate. Put the import and its
use in the **same Edit**. Import at the top with the other `gui.` imports:
`from gui.selection_helper import order_number_mask`.

```python
    def _order_mask(self, order_number, df=None):
        """Rows belonging to one order, in `df` or the analysis frame.

        See order_number_mask: the one matching rule for order numbers.
        """
        if df is None:
            df = self.mw.analysis_results_df
        return order_number_mask(df, [order_number])
```

Check first that `gui/selection_helper.py` does not import `gui.actions_handler`.
It doesn't today; keep it that way so no import cycle forms.

- [ ] **Step 4: Run them and confirm they pass**

Run the Step 2 command, then the full suite. Expected: all pass.

- [ ] **Step 5: Commit**

`git add gui/selection_helper.py gui/actions_handler.py tests/test_selection_helper.py tests/test_actions_handler_bulk.py`
Message: `Bulk actions match numeric order numbers (non-Shopify clients)`, with a
body naming the root cause (int64 `isin` against str).

---

### Task 2: Window geometry restores through Qt alone (packing-tool, then sync)

**Files (packing-tool):**
- Modify: `shared/theme.py`. Delete `clamp_geometry` (around line 679) and rewrite
  `restore_window_geometry` (around line 1014).
- Modify: `tests/test_theme.py`. Remove the `clamp_geometry` import and its four tests
  (around lines 234–254). Add the two tests below.

**Files (this repo):** `shared/theme.py`, via sync only.

**Interfaces:**
- `restore_window_geometry(window, settings, key="window_geometry") -> bool`.
  The signature is unchanged; neither caller changes.

- [ ] **Step 1: Create the packing-tool worktree**

From `/home/gloopy/Desktop/Projects/packing-tool`, run
`/usr/bin/git worktree add .claude/worktrees/phase12-bundle1 -b worktree-phase12-bundle1 origin/main`
(fetch first). Run every git command for this task from inside that worktree.
**If the worktree guard refuses a git command in packing-tool, stop.** Record in
`state.md` what was refused, do Tasks 3–4, and leave Task 2 for the owner. Do not
work around it.

Test command there: `QT_QPA_PLATFORM=offscreen /home/gloopy/Desktop/Projects/packing-tool/.venv/bin/python -m pytest`.

- [ ] **Step 2: Write the failing tests** (append to packing-tool `tests/test_theme.py`)

```python
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QMainWindow

from shared.theme import restore_window_geometry, save_window_geometry


def _geometry_settings(tmp_path):
    return QSettings(str(tmp_path / "geometry.ini"), QSettings.Format.IniFormat)


def test_restore_window_geometry_leaves_qt_restored_geometry_alone(qapp, tmp_path, monkeypatch):
    """Qt's restoreGeometry already keeps the frame on-screen and handles
    maximized state. A setGeometry after it re-clamps the client rect
    without its title bar (frame under the top edge) and, on a maximized
    window, overwrites the normal geometry (QTBUG-4397)."""
    settings = _geometry_settings(tmp_path)
    saved = QMainWindow()
    saved.setGeometry(100, 120, 800, 600)
    save_window_geometry(saved, settings)

    window = QMainWindow()
    calls = []
    monkeypatch.setattr(window, "setGeometry", lambda *a: calls.append(a))

    assert restore_window_geometry(window, settings) is True
    assert calls == []


def test_restore_window_geometry_reports_nothing_saved(qapp, tmp_path):
    assert restore_window_geometry(QMainWindow(), _geometry_settings(tmp_path)) is False
```

(Stage A already confirmed the first test fails against today's code:
`[(1, 120, 798, 600)] != []`.)

- [ ] **Step 3: Run it and confirm the first test fails**

- [ ] **Step 4: Implement**

Replace `restore_window_geometry` with:

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

Delete `clamp_geometry`. Confirm with `grep -rn clamp_geometry` over packing-tool
(excluding `.venv`) that nothing else uses it.

- [ ] **Step 5: Run the packing-tool suite and ruff.** Both must be clean.

- [ ] **Step 6: Commit, push and open the PR in packing-tool**

Message: `shared: restore window geometry through Qt alone (frame off-screen fix)`.
Push the branch, then open a PR with `gh pr create --draft` against `main`. Its body
cites the spec's §2 root cause and states that the shopify PR depends on it merging
first.

- [ ] **Step 7: Sync into this repo and commit**

From this worktree:
`.venv/bin/python scripts/sync_shared.py /home/gloopy/Desktop/Projects/packing-tool/.claude/worktrees/phase12-bundle1`.
Then run this repo's full suite; nothing here references `clamp_geometry`.
Commit with the message `shared/: window geometry fix (synced from packing-tool #<n>)`.
CI's drift check fails until the packing-tool PR merges. That is expected, and
the PR description must say so.

---

### Task 3: Driver mode prints at actual size

**Files:**
- Modify: `gui/pdf_printing.py`. Add `_fit_rect`; in `_print_pdf_driver_mode`, set
  full page and draw into the fitted paper rect.
- Test: `tests/test_pdf_printing.py`

**Interfaces:**
- Produces: `_fit_rect(page_pt: QSizeF, paper: QRectF) -> QRectF`

- [ ] **Step 1: Write the failing tests** (append to `tests/test_pdf_printing.py`)

```python
from PySide6.QtCore import QRectF, QSizeF


class TestFitRect:
    def test_same_aspect_fills_the_paper(self):
        r = pdf_printing._fit_rect(QSizeF(100, 150), QRectF(0, 0, 1000, 1500))
        assert (r.x(), r.y(), r.width(), r.height()) == (0, 0, 1000, 1500)

    def test_other_aspect_scales_uniformly_and_centres(self):
        # A 100x150 label on square paper: height-bound, centred horizontally.
        r = pdf_printing._fit_rect(QSizeF(100, 150), QRectF(0, 0, 1500, 1500))
        assert r.height() == pytest.approx(1500)
        assert r.width() == pytest.approx(1000)
        assert r.x() == pytest.approx(250)
        assert r.y() == pytest.approx(0)


class TestPrintPdfDriverModeActualSize:
    def test_label_fills_the_page_with_no_margin_shrink(self, tmp_path):
        """Qt's default 10pt margins used to shrink a label to ~93%x95% and
        offset it by a second margin (spec §3). A border 1mm inside the page
        edge must print 1mm inside the page edge."""
        import pypdfium2 as pdfium
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas

        src_pdf = tmp_path / "border.pdf"
        c = canvas.Canvas(str(src_pdf), pagesize=(100 * mm, 150 * mm))
        c.setLineWidth(2)
        c.rect(1 * mm, 1 * mm, 98 * mm, 148 * mm)
        c.save()

        out_pdf = tmp_path / "out.pdf"
        assert pdf_printing._print_pdf_driver_mode(None, src_pdf, output_path=out_pdf)

        image = pdfium.PdfDocument(str(out_pdf))[0].render(scale=2, grayscale=True).to_pil()
        left, top, right, bottom = image.point(lambda v: 255 if v < 128 else 0).getbbox()
        w, h = image.size
        assert left / w <= 0.02 and top / h <= 0.02
        assert right / w >= 0.98 and bottom / h >= 0.98
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_pdf_printing.py -q -p no:randomly`
Expected: `_fit_rect` AttributeError. The actual-size test fails with left ≈ 0.076.

- [ ] **Step 3: Implement** (Stage A ran this code headlessly: ink at 0.7%–99.3%)

Add near `_apply_default_page_size`. Extend the QtCore import to
`from PySide6.QtCore import QRectF, QSettings, QSizeF` in the same Edit.

```python
def _fit_rect(page_pt: QSizeF, paper: QRectF) -> QRectF:
    """page_pt scaled uniformly to fit paper, centred in it.

    Actual size when the paper matches the PDF page, which
    _apply_default_page_size arranges; never stretched when the operator
    picks other paper.
    """
    if page_pt.isEmpty():
        return QRectF(paper)
    scale = min(paper.width() / page_pt.width(), paper.height() / page_pt.height())
    w, h = page_pt.width() * scale, page_pt.height() * scale
    return QRectF(
        paper.x() + (paper.width() - w) / 2, paper.y() + (paper.height() - h) / 2, w, h
    )
```

In `_print_pdf_driver_mode`, directly after `_apply_default_page_size(printer, document)`:

```python
    # Draw on the whole sheet: with full page off, Qt's default 10pt margins
    # shrank every label and offset it by a second margin (spec §3).
    printer.setFullPage(True)
```

Replace the render loop body:

```python
        painter = QPainter(printer)
        paper = printer.paperRect(QPrinter.Unit.DevicePixel)
        for page in range(first_page, last_page + 1):
            if page > first_page:
                printer.newPage()
            target = _fit_rect(document.pagePointSize(page), paper)
            image = document.render(page, target.size().toSize())
            painter.drawImage(target, image)
        painter.end()
```

- [ ] **Step 4: Run and confirm everything passes**

That includes the existing `test_renders_larger_than_the_old_point_size_bug`.

- [ ] **Step 5: Commit** with the message `Driver-mode print at actual size (no margin shrink or offset)`.

---

### Task 4: Reference Labels pages via pikepdf (separate commit, D3/D4)

**Files:**
- Modify: `shopify_tool/pdf_processor.py`. Covers the imports; `process_reference_labels`
  steps 1, 3 and 5; a new `_page_texts`; a new `_stamp_reference`.
- Modify: `requirements.txt`. Add `pikepdf>=9.0` next to `pypdf` and keep pypdf.
  Change pypdf's comment to `# page text for Reference Labels matching`.
- Modify: `.github/workflows/build_release.yml`. In step "Verify bundled assets
  shipped", add `"pikepdf"` to the `foreach` list. It matches the package
  directory, and `Get-ChildItem -Filter` matches directories too.
- Test: `tests/test_pdf_processor.py`

**Interfaces:**
- Consumes: `create_reference_overlay(ref, w, h) -> BytesIO`, unchanged.
- Produces: `_page_texts(pdf_path, total_pages) -> list[str]` and
  `_stamp_reference(out: pikepdf.Pdf, page: pikepdf.Page, ref: str) -> None`.

- [ ] **Step 1: Install pikepdf into the dev venv**

`.venv/bin/python -m pip install "pikepdf>=9.0"`. The venv is shared with the main
checkout, and that's fine: the requirement lands in `requirements.txt` in this task.

- [ ] **Step 2: Write the failing and guard tests** (append to `tests/test_pdf_processor.py`)

The existing `TestProcessReferenceLabelsShrink` and `TestProcessReferenceLabelsRotation`
are the regression net. They must pass **unchanged**. Add:

```python
_MAPPING = "PostOne,Tracking,Reference,Col3,Col4,Col5,Name\n,,REF-001,,,,Acme Warehouse Co\n"


class TestProcessReferenceLabelsPikepdf:
    def _run(self, tmp_path, pdf_path):
        csv_path = tmp_path / "mapping.csv"
        csv_path.write_text(_MAPPING)
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        return pdf_processor.process_reference_labels(str(pdf_path), str(csv_path), str(out_dir))

    def test_rotate_270_bakes_to_visual_size(self, tmp_path):
        import pikepdf

        pdf_path = tmp_path / "courier.pdf"
        _make_courier_pdf(pdf_path, width_pt=288, height_pt=432)
        with pikepdf.open(pdf_path, allow_overwriting_input=True) as pdf:
            pdf.pages[0].Rotate = 270
            pdf.save(pdf_path)
        result = self._run(tmp_path, pdf_path)
        page = PdfReader(result["output_file"]).pages[0]
        assert page.rotation == 0
        assert (float(page.mediabox.width), float(page.mediabox.height)) == (432, 288)
        assert "REF: REF-001" in page.extract_text()

    def test_unmatched_page_passes_through_untouched(self, tmp_path):
        from reportlab.pdfgen import canvas

        pdf_path = tmp_path / "other.pdf"
        c = canvas.Canvas(str(pdf_path), pagesize=(288, 432))
        c.drawString(20, 400, "Nobody we know")
        c.save()
        result = self._run(tmp_path, pdf_path)
        assert result["unmatched"] == 1
        page = PdfReader(result["output_file"]).pages[0]
        assert "REF:" not in page.extract_text()
        assert (float(page.mediabox.width), float(page.mediabox.height)) == (288, 432)

    def test_file_pypdf_cannot_open_still_processes_unmatched(self, tmp_path, monkeypatch):
        pdf_path = tmp_path / "courier.pdf"
        _make_courier_pdf(pdf_path)

        def broken(*_a, **_k):
            raise ValueError("pypdf choked")

        monkeypatch.setattr(pdf_processor, "PdfReader", broken)
        result = self._run(tmp_path, pdf_path)
        assert result["matched"] == 0 and result["unmatched"] == 1

    def test_source_pdf_is_closed_after_processing(self, tmp_path, monkeypatch):
        """Windows cannot replace or delete a file pikepdf still holds open.
        A closed pikepdf.Pdf raises nothing on access (checked at Stage A),
        so spy on close() itself; patching the class attribute works."""
        import pikepdf

        opened, closed = [], []
        real_open, real_close = pikepdf.open, pikepdf.Pdf.close

        def spy_open(*a, **k):
            pdf = real_open(*a, **k)
            opened.append(pdf)
            return pdf

        def spy_close(self):
            closed.append(self)
            return real_close(self)

        monkeypatch.setattr(pikepdf, "open", spy_open)
        monkeypatch.setattr(pikepdf.Pdf, "close", spy_close)
        pdf_path = tmp_path / "courier.pdf"
        _make_courier_pdf(pdf_path)
        self._run(tmp_path, pdf_path)
        assert any(c is opened[0] for c in closed)  # opened[0] is the source
```

Before relying on these tests, check `_make_courier_pdf`'s signature at the top of
the test file. It takes `width_pt`/`height_pt`, and the existing tests match on
the name "Acme Warehouse Co".

- [ ] **Step 3: Run them and see which fail.** The 270 test may already pass on
  pypdf. The pypdf-cannot-open test must fail today with `InvalidPDFError`.

- [ ] **Step 4: Implement**

Imports: `import pikepdf`, and keep `from pypdf import PdfReader` only. Drop
`PdfWriter` and `Transformation`. Put each import in the same Edit as its first use.

Step 1 of `process_reference_labels` opens with pikepdf. Wrap the **whole body**
so the source is always closed. Declare `src = None` before the outer `try`, and
add `finally: if src is not None: src.close()` to the outer `try`, after the
existing `except` clauses.

```python
        try:
            src = pikepdf.open(pdf_path)
            total_pages = len(src.pages)

            if total_pages == 0:
                raise InvalidPDFError("PDF file has no pages")

            logger.info(f"PDF loaded: {total_pages} pages")

        except Exception as e:
            raise InvalidPDFError(f"Cannot read PDF: {e}")
```

Step 3 reads text through the new helper:

```python
        page_texts = _page_texts(pdf_path, total_pages)

        for i, page in enumerate(src.pages):
            ...progress unchanged...
            page_text = page_texts[i]
            ...matching and page_data_list.append unchanged ('page': page)...
```

Step 5 writes with pikepdf:

```python
        out = pikepdf.new()

        for page_data in sorted_pages:
            page = page_data['page']
            ref = page_data['ref']

            if ref:
                try:
                    _stamp_reference(out, page, ref)
                    continue
                except Exception:
                    logger.exception(f"Failed to add overlay for ref {ref}")

            out.pages.append(page)
```

Step 6 saves with `out.save(output_file)`, replacing the `open(...)`/`writer.write` pair.

New module-level helpers (place them after `process_reference_labels`):

```python
def _page_texts(pdf_path: str, total_pages: int) -> list[str]:
    """Each page's text, read by pypdf: reference matching was tuned
    against its extraction (spec D4). A file pypdf cannot open still
    processes -- its pages just come out unmatched."""
    try:
        reader = PdfReader(pdf_path)
    except Exception:
        logger.warning(f"pypdf could not open {pdf_path}; pages will be unmatched", exc_info=True)
        return [""] * total_pages
    texts = []
    for i in range(total_pages):
        try:
            texts.append(reader.pages[i].extract_text() or "")
        except Exception as e:
            logger.warning(f"Failed to extract text from page {i+1}: {e}")
            texts.append("")
    return texts


def _stamp_reference(out: "pikepdf.Pdf", page: "pikepdf.Page", ref: str) -> None:
    """Append page to out, its content shrunk into the top of a same-size
    page with the reference strip below.

    Courier PDFs set varied /Rotate values; add_overlay bakes the rotation
    in, so the new page takes the courier page's *visual* size and the
    strip always lands on the visual bottom.
    """
    box = page.mediabox
    width, height = float(box[2] - box[0]), float(box[3] - box[1])
    if int(page.obj.get("/Rotate", 0)) % 180:
        width, height = height, width

    # Keep the strip's Pdf referenced until add_overlay returns: a
    # temporary raises "getFormXObjectForPage called with a direct object".
    strip = pikepdf.open(create_reference_overlay(ref, width, height))
    out.add_blank_page(page_size=(width, height))
    stamped = out.pages[-1]
    try:
        stamped.add_overlay(
            page,
            pikepdf.Rectangle(
                width * (1 - _CONTENT_SCALE) / 2,
                height * (1 - _CONTENT_SCALE),
                width * (1 + _CONTENT_SCALE) / 2,
                height,
            ),
        )
        stamped.add_overlay(strip.pages[0], pikepdf.Rectangle(0, 0, width, height))
    except Exception:
        del out.pages[-1]
        raise
```

Update `create_reference_overlay`'s docstring reference, "freed up by
process_reference_labels()'s content-shrink transform", to name `_stamp_reference`.

- [ ] **Step 5: Run `tests/test_pdf_processor.py` and then the full suite.** All must
  pass. The existing shrink and rotation tests must pass unchanged.

- [ ] **Step 6: Edit `requirements.txt` and the workflow** as listed under Files.

- [ ] **Step 7: Commit, separately** from items 1–3.
  Message: `Reference Labels: pages via pikepdf, text still via pypdf`.

---

### Task 5: Gate and hand-off

- [ ] Full suite `-p no:randomly` and `ruff check . --exclude shared`, both clean.
  Record the pass count in `state.md`.
- [ ] `graphify update .` in this repo, and in packing-tool if Task 2 ran.
- [ ] Push `worktree-phase12-bundle1`. **Don't open the shopify PR**: that's Stage C.
- [ ] Stage C must add the `windows-build` label to the shopify PR and confirm
  the Windows build and its pikepdf check pass (spec §4). Write that into
  `state.md` for Stage C.
- [ ] Set `next_stage: C`.
