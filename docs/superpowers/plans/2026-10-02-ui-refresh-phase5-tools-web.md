# UI refresh phase 5: Tools on the web tier. Implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the two Qt tool widgets on Tools with one web page drawn to the approved mockup, in its own
`QWebEngineView`: one card per tool, a Driver / Raw ZPL switch per card with a Label setup fold, files checked
when they are picked, counted progress and Cancel for Reference labels, and a done toast with Open folder.

**Architecture:** Python words every fact. One pure function, `tools_state(...)` (`gui/tools_state.py`), builds
a dict from two tools' facts; `ToolsBridge` (`gui/tools_bridge.py`) carries it to the page as one `state`
property; `gui/web/tools.js` draws it. The two tools are `QObject`s, not widgets: `ReferenceTool`
(`gui/reference_tool.py`) and `BarcodeTool` (`gui/barcode_tool.py`) hold the picks, run the work on a `Worker`,
and emit `changed`. `ToolsWidget` (`gui/tools_widget.py`) hosts the view and joins them. The page's own state
is which menu is open and which Label setup fold is open.

**Tech Stack:** Python 3.14, PySide6 (Qt widgets, QtWebEngine, QWebChannel), plain CSS and JavaScript (no build
step, no framework), pikepdf, pandas, pytest + pytest-qt driving a real Chromium offscreen.

**Spec:** `docs/superpowers/specs/2026-10-02-ui-refresh-phase5-tools-web-design.md`. Read it whole before
starting; this plan argues from it. Copy (every reason line, title and toast) is in spec §4 and §6 and is
verbatim. Mockup: `docs/design/ui-refresh/mockups/tools.html` (render: `mockups/renders/tools.png`). To read
exact values, unpack the bundle with the script in `docs/design/ui-refresh/mockups/README.md`.

**Every code block in this plan was run before the plan was written**, against a scratch copy of the repo at
5b8839c (code identical to `origin/main` at 7ecea8b): the tests of every task passed there, and so did the
whole suite and `ruff check .`. The page was rendered in both themes and compared with the mockup. If a block
fails for you, suspect a typo in transcription, or a change on `main` since 7ecea8b, before you suspect the
design, and say what differed.

## Global Constraints

- Work in `/home/gloopy/Desktop/Projects/shopify-fulfillment-tool/.claude/worktrees/dr-17` on branch
  `dr/17-ui-refresh-phase-5-move-tools-to-the-web`. Never `cd` anywhere else. If `.venv` is missing, run
  `./scripts/setup_venv.sh`.
- Run tests only as `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q <paths>`. A hook blocks any other
  Bash text containing the word "pytest", so write test files with Write/Edit, never with heredocs.
- Git: `/usr/bin/git`, one plain command per Bash call, with no `;`, `&&` or `$VAR`. Commit with
  `/usr/bin/git commit -F <absolute path to a message file>`; write the message file under your job's tmp dir.
  End every message with the attribution lines your session is given.
- **Baseline:** see "Baseline" just below this list. Every test that passes there must pass after every task,
  unless the task rewrites or deletes it and says so.
- **Transcribe code blocks exactly.** A block headed "Create" is the whole file. A block pair headed "Find
  exactly" / "Replace with" is one Edit: the first block is the `old_string`, the second the `new_string`, and
  the first occurs once in the file. A block headed "Append" goes at the end of the file, after two blank
  lines.
- No hex, colour name, `rgb()`, px font size (that includes the `font:` shorthand), `transition`, `transform`,
  gradient or `opacity` in any file under `gui/` (`shared/style_lint.py`, enforced by
  `tests/test_style_literals_guard.py`). `box-shadow` only as `var(--card-shadow)`, `var(--overlay-shadow)` or
  `none`, and only in a `.css` file. Never set `element.style.*` to a colour from JavaScript: use a class.
- The lint reads a colour word after a colour property up to the next `;`. So every CSS declaration ends
  with `;`, including the last one in a rule.
- The lint reads `rotate`, `scale`, `translate` and `opacity` followed by `:` as a banned CSS property, in
  `.js` files too. So in `tools.js` never write an object key or a ternary branch that puts `rotate:` in the
  source (`{ rotate: x }`, `a ? setup.rotate : b`). The blocks in this plan avoid it; do not "tidy" them.
- The lint reads `#` followed by three or six hex digits as a colour, in CSS and in JavaScript strings. The
  ids in this plan are safe; do not rename them.
- CSS custom properties from the theme are hyphenated: the token `surface_raised` is `var(--surface-raised)`.
  Type sizes are `var(--type-caption-size)`, `--type-body-size`, `--type-label-size`, `--type-heading-size`.
  The mono face is `var(--font-family-mono)`. Control height is `var(--control-height)`.
- ADR 0018: a decorative line (card edge, divider) is `--border-subtle`. The edge of a button, an input or a
  select is `--border`.
- Nothing in `shared/` changes in this plan. Never touch `packing-tool/`.
- The two QSettings scope names, `reference_labels` and `barcode_generator`, and the seven setting keys in
  `gui/pdf_printing.py` do not change: every warehouse PC keeps what it has saved.
- No `pyproject.toml`, no new dependency, no unused import (`.venv/bin/ruff check .` must pass). If ruff reports
  import order (I001) in a file you wrote, run `.venv/bin/ruff check --fix <that file>` and keep its order.
- No UI call from a worker thread. A tool's worker reaches the UI only by emitting a Qt signal or by raising.
- Never mark a Chromium test skip, and never delete a test without a replacement that pins the new behaviour.
  The test files this plan deletes are named in Task 9, with what replaces them.
- The page names a tool, a packing list and a printer by name. Python never uses anything the page sends as a
  path.
- The implementer writes no "TODO". A step that cannot be finished is a stop: say what failed.

**Baseline.** Before Task 1, run `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` and write down the
pass and fail counts. On this branch at 5b8839c (code identical to `origin/main` at 7ecea8b) the run gave 2711 passed and 3 failed in about six minutes. The three failures are `tests/test_label_printing.py::TestImageToZpl` (`test_black_pixels_become_set_bits`, `test_invert_flips_the_polarity`, `test_rotate_and_invert_compose`); they are not this task's and the PR body mentions them.

## Review Focus

The inputs the spec implies but does not spell out, most likely first. Each has its test in the task that
owns the code.

1. **A packing list or printer name carrying quotes, angle brackets or spaces** (a list named by hand, a
   print-server queue such as `\\printsrv\Zebra "3"`). It is drawn as text, the menu still works, and Python
   is given the name exactly (Task 6: `test_a_list_name_with_markup_is_drawn_as_text_and_sent_back_exactly`;
   Task 3: `test_a_saved_printer_that_is_not_installed_is_still_listed`).
2. **A state that arrives while the operator is typing** in the Label setup fold: the other card's run pushes
   several a second. The typed text and the focus survive the redraw (Task 6:
   `test_text_being_typed_survives_a_state_that_arrives_mid_edit`).
3. **The session, or the screen, changes while a run is going.** The labels are written where the run was
   started, the new session shows no result that is not its own, and the toast still reaches the operator on
   the screen that is showing (Task 7 and Task 8: `test_a_run_that_outlives_its_session_…`; Task 9:
   `test_a_done_toast_while_another_screen_shows_goes_to_the_router`).
4. **A packing list workbook that is open in Excel, or damaged.** Excel's `~$DHL.xlsx` lock file is not a
   list; a workbook that cannot be read is listed as "Unreadable" and the others stay usable (Task 8:
   `test_excels_lock_file_is_not_a_packing_list`, `test_a_workbook_that_cannot_be_read_is_listed_as_unreadable`).
5. **A very large labels PDF, and a pick that vanishes.** A 2,000-page run reports at most ten times a second,
   never once a page; a file deleted between the dialog and the check is flagged, not raised (Task 7:
   `test_reports_are_throttled_but_a_phases_last_one_always_gets_through`,
   `test_a_pick_that_vanished_before_the_check_is_flagged_not_raised`).

## File structure

| File | Task | Responsibility |
|---|---|---|
| `shopify_tool/pdf_processor.py` | 1 | Counted progress, `ProcessingCancelled`, `pdf_page_count`, `rows` in the CSV mapping |
| `shopify_tool/barcode_processor.py` | 2 | `packing_list_orders`, `generate_list_labels` |
| `gui/setup_state.py` | 3 | `session_meta` extracted, so Tools words the page head as Setup does |
| `gui/tools_state.py` (new) | 3 | The facts dataclasses, `tools_state`, `apply_print_edit`. No Qt |
| `gui/tools_bridge.py` (new) | 4 | `ToolsBridge`, `mount_tools_page` |
| `gui/web/kit.css`, `tests/web/kit_sheet.html` | 5 | `.select`, disabled `.segment` and `.field` |
| `gui/web/tools.html`, `tools.css`, `tools.js` (new) | 6 | The page |
| `gui/reference_tool.py` (new) | 7 | `ReferenceTool` |
| `gui/barcode_tool.py` (new) | 8 | `BarcodeTool`, `read_packing_lists` |
| `gui/tools_widget.py` (rewritten) | 9 | `ToolsWidget`: the view, the wiring, `sync()` |
| `gui/ui_manager.py`, `gui/main_window_pyside.py`, `gui/pdf_printing.py`, `gui/components/__init__.py`, `tests/conftest.py` | 9 | The shell, one sentence, the export list, the fixture |
| Deleted in Task 9 | 9 | `gui/reference_labels_widget.py`, `gui/barcode_generator_widget.py`, `gui/components/print_options.py`, and six test files |
| `CONTEXT.md`, ADR 0016, `roadmap.md`, `build_release.yml` | 10 | Docs and the bundle check |

Tasks 1 to 8 add code and leave the old Tools screen working. Task 9 swaps the screen and deletes the old
widgets in one commit. Each task ends with the whole suite as green as the baseline.

---

### Task 1: Counted progress and Cancel for reference labels (`shopify_tool/pdf_processor.py`)

**Files:**
- Modify: `shopify_tool/pdf_processor.py`
- Test: `tests/test_pdf_processor.py` (append)

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `READING = "Reading labels"`, `STAMPING = "Stamping labels"`, `SAVING = "Saving"`.
  - `class ProcessingCancelled(PDFProcessorError)`.
  - `pdf_page_count(pdf_path) -> int`, raising `InvalidPDFError`.
  - `load_csv_mapping(csv_path)["rows"]: int`.
  - `process_reference_labels(pdf_path, csv_path, output_dir, progress_callback=None)`: unchanged signature.
    `progress_callback(done: int, total: int, label: str)` is called `(i, pages, READING)` per page read,
    `(i, pages, STAMPING)` per page stamped, then `(pages, pages, SAVING)` once. A callback may raise
    `ProcessingCancelled`; nothing is written before `SAVING`.

The old Qt widget still calls this function until Task 9. Its callback computes `current / total * 100`, which
still works with the new arguments.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_pdf_processor.py`:

````python
def _two_page_run(tmp_path):
    """A two-page courier PDF (one page matches), its mapping and an empty out dir."""
    pdf_path = tmp_path / "two.pdf"
    c = canvas.Canvas(str(pdf_path), pagesize=(288, 432))
    c.drawString(20, 400, "Nobody we know")
    c.showPage()
    c.drawString(20, 400, "Acme Warehouse Co")
    c.showPage()
    c.save()
    csv_path = tmp_path / "mapping.csv"
    csv_path.write_text(_MAPPING)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    return str(pdf_path), str(csv_path), out_dir


class TestProgressAndCancel:
    """Phase 5 spec section 7.1: counted progress, and a cancel that writes nothing."""

    def test_a_run_reports_each_page_read_each_page_stamped_then_saving(self, tmp_path):
        pdf_path, csv_path, out_dir = _two_page_run(tmp_path)
        calls = []
        pdf_processor.process_reference_labels(
            pdf_path, csv_path, str(out_dir), progress_callback=lambda *a: calls.append(a)
        )
        assert calls == [
            (1, 2, pdf_processor.READING),
            (2, 2, pdf_processor.READING),
            (1, 2, pdf_processor.STAMPING),
            (2, 2, pdf_processor.STAMPING),
            (2, 2, pdf_processor.SAVING),
        ]

    def test_the_labels_are_the_words_the_page_shows(self):
        assert (pdf_processor.READING, pdf_processor.STAMPING, pdf_processor.SAVING) == (
            "Reading labels",
            "Stamping labels",
            "Saving",
        )

    @pytest.mark.parametrize("phase", [pdf_processor.READING, pdf_processor.STAMPING])
    def test_cancelling_in_a_counted_phase_writes_no_file(self, tmp_path, phase):
        pdf_path, csv_path, out_dir = _two_page_run(tmp_path)

        def cancel(_done, _total, label):
            if label == phase:
                raise pdf_processor.ProcessingCancelled

        with pytest.raises(pdf_processor.ProcessingCancelled):
            pdf_processor.process_reference_labels(
                pdf_path, csv_path, str(out_dir), progress_callback=cancel
            )
        assert list(out_dir.iterdir()) == []

    def test_cancelled_is_one_of_the_processors_own_errors(self):
        # So process_reference_labels' "except PDFProcessorError: raise" lets
        # it through instead of wrapping it as an unexpected error.
        assert issubclass(pdf_processor.ProcessingCancelled, pdf_processor.PDFProcessorError)

    def test_a_pdf_pypdf_cannot_open_still_reports_the_reading_phase(
        self, tmp_path, monkeypatch
    ):
        pdf_path, csv_path, out_dir = _two_page_run(tmp_path)

        def broken(*_a, **_k):
            raise ValueError("pypdf choked")

        monkeypatch.setattr(pdf_processor, "PdfReader", broken)
        calls = []
        pdf_processor.process_reference_labels(
            pdf_path, csv_path, str(out_dir), progress_callback=lambda *a: calls.append(a)
        )
        assert calls[0] == (2, 2, pdf_processor.READING)
        assert calls[-1] == (2, 2, pdf_processor.SAVING)

    def test_no_callback_still_runs(self, tmp_path):
        pdf_path, csv_path, out_dir = _two_page_run(tmp_path)
        result = pdf_processor.process_reference_labels(pdf_path, csv_path, str(out_dir))
        assert result["pages_processed"] == 2


class TestPdfPageCount:
    def test_counts_the_pages(self, tmp_path):
        pdf_path, _csv, _out = _two_page_run(tmp_path)
        assert pdf_processor.pdf_page_count(pdf_path) == 2

    def test_a_file_that_is_not_a_pdf_is_invalid(self, tmp_path):
        bad = tmp_path / "notes.pdf"
        bad.write_text("this is not a pdf")
        with pytest.raises(pdf_processor.InvalidPDFError):
            pdf_processor.pdf_page_count(str(bad))

    def test_a_missing_file_is_invalid(self, tmp_path):
        with pytest.raises(pdf_processor.InvalidPDFError):
            pdf_processor.pdf_page_count(str(tmp_path / "gone.pdf"))

    def test_a_pdf_with_no_pages_is_invalid(self, tmp_path):
        import pikepdf

        empty = tmp_path / "empty.pdf"
        pikepdf.new().save(empty)
        with pytest.raises(pdf_processor.InvalidPDFError):
            pdf_processor.pdf_page_count(str(empty))


class TestCsvMappingRows:
    def test_the_mapping_says_how_many_rows_it_used(self, tmp_path):
        csv_path = tmp_path / "mapping.csv"
        csv_path.write_text(
            "PostOne,Tracking,Reference,Col3,Col4,Col5,Name\n"
            ",,REF-001,,,,Acme Warehouse Co\n"
            "short,row\n"
            ",,REF-002,,,,Borealis Ltd\n"
        )
        assert pdf_processor.load_csv_mapping(str(csv_path))["rows"] == 2

    def test_a_csv_with_no_seven_column_row_is_invalid(self, tmp_path):
        csv_path = tmp_path / "mapping.csv"
        csv_path.write_text("Order,Tracking,Date\n#1,TR1,2026-09-30\n")
        with pytest.raises(pdf_processor.InvalidCSVError):
            pdf_processor.load_csv_mapping(str(csv_path))
````

- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_pdf_processor.py`
Expected: an error while collecting the file: `AttributeError: module 'shopify_tool.pdf_processor' has no
attribute 'READING'`.

- [ ] **Step 3: Implement**

In `shopify_tool/pdf_processor.py`:

**Edit 1 of 11** (near line 60). Find exactly:

````python
def process_reference_labels(
    pdf_path: str,
````

Replace with:

````python
class ProcessingCancelled(PDFProcessorError):
    """Raised by a progress callback to stop a run before it saves."""


# What a progress callback is told, as callback(done, total, label): each page
# read, each page stamped, then one SAVING call. Nothing is written before
# SAVING and nothing is called after it, so a callback that raises
# ProcessingCancelled leaves no file (phase 5 spec section 7.1).
READING, STAMPING, SAVING = "Reading labels", "Stamping labels", "Saving"


def pdf_page_count(pdf_path) -> int:
    """How many pages a PDF has.

    Raises:
        InvalidPDFError: If it cannot be opened, or has no pages
    """
    try:
        with pikepdf.open(pdf_path) as pdf:
            pages = len(pdf.pages)
    except Exception as e:
        raise InvalidPDFError(f"Cannot read PDF: {e}") from e
    if pages == 0:
        raise InvalidPDFError("PDF file has no pages")
    return pages


def process_reference_labels(
    pdf_path: str,
````

**Edit 2 of 11** (near line 94). Find exactly:

````python
    try:
        # Step 1: Load and validate PDF
        if progress_callback:
            progress_callback(0, 100, "Loading PDF...")

        try:
            src = pikepdf.open(pdf_path)
````

Replace with:

````python
    try:
        # Step 1: Load and validate PDF
        try:
            src = pikepdf.open(pdf_path)
````

**Edit 3 of 11** (near line 111). Find exactly:

````python
        # Step 2: Load and validate CSV mapping
        if progress_callback:
            progress_callback(5, 100, "Loading CSV mapping...")

        try:
            mapping = load_csv_mapping(csv_path)
````

Replace with:

````python
        # Step 2: Load and validate CSV mapping
        try:
            mapping = load_csv_mapping(csv_path)
````

**Edit 4 of 11** (near line 126). Find exactly:

````python
            raise InvalidCSVError(f"Cannot read CSV: {e}")

        # Step 3: Process pages and match references
        if progress_callback:
            progress_callback(10, 100, "Processing pages...")

        page_data_list = []

        page_texts = _page_texts(pdf_path, total_pages)

        for i, page in enumerate(src.pages):
            # Update progress
            progress_pct = 10 + int((i / total_pages) * 70)
            if progress_callback:
                progress_callback(
                    progress_pct,
                    100,
                    f"Processing page {i+1}/{total_pages}"
                )

            # Match reference
            ref_data = match_reference(page_texts[i], mapping)
````

Replace with:

````python
            raise InvalidCSVError(f"Cannot read CSV: {e}")

        # Step 3: Read every page's text (the slow half), then match references
        page_data_list = []

        page_texts = _page_texts(pdf_path, total_pages, progress_callback)

        for i, page in enumerate(src.pages):
            # Match reference
            ref_data = match_reference(page_texts[i], mapping)
````

**Edit 5 of 11** (near line 163). Find exactly:

````python
        # Step 4: Sort pages by reference number
        if progress_callback:
            progress_callback(80, 100, "Sorting pages...")

        sorted_pages = sort_pages_by_reference(page_data_list)

        # Step 5: Add reference overlays and save
        if progress_callback:
            progress_callback(85, 100, "Adding reference labels...")

        out = pikepdf.new()

        stamped_refs = []
        name_matched = 0
        for page_data in sorted_pages:
            page, ref = page_data['page'], page_data['ref']
            if ref:
                try:
````

Replace with:

````python
        # Step 4: Sort pages by reference number
        sorted_pages = sort_pages_by_reference(page_data_list)

        # Step 5: Add reference overlays
        out = pikepdf.new()

        stamped_refs = []
        name_matched = 0
        for done, page_data in enumerate(sorted_pages, start=1):
            page, ref = page_data['page'], page_data['ref']
            stamped = False
            if ref:
                try:
````

**Edit 6 of 11** (near line 182). Find exactly:

````python
                    stamped_refs.append(ref)
                    name_matched += page_data['method'] == 'name'
                    continue
                except Exception:
                    logger.exception(f"Failed to add overlay for ref {ref}; page kept unstamped")
            out.pages.append(page)

        # "matched" is pages actually stamped, not pages a REF was found for
````

Replace with:

````python
                    stamped_refs.append(ref)
                    name_matched += page_data['method'] == 'name'
                    stamped = True
                except Exception:
                    logger.exception(f"Failed to add overlay for ref {ref}; page kept unstamped")
            if not stamped:
                out.pages.append(page)
            if progress_callback:
                progress_callback(done, total_pages, STAMPING)

        # "matched" is pages actually stamped, not pages a REF was found for
````

**Edit 7 of 11** (near line 195). Find exactly:

````python
        logger.info(f"Matching complete: {matched} matched, {unmatched} unmatched")

        # Step 6: Save output PDF
        if progress_callback:
            progress_callback(95, 100, "Saving PDF...")

        output_file = Path(output_dir) / generate_output_filename()
````

Replace with:

````python
        logger.info(f"Matching complete: {matched} matched, {unmatched} unmatched")

        # Step 6: Save output PDF. The last call a callback gets: a run that
        # has begun saving always finishes.
        if progress_callback:
            progress_callback(total_pages, total_pages, SAVING)

        output_file = Path(output_dir) / generate_output_filename()
````

**Edit 8 of 11** (near line 209). Find exactly:

````python
            f"({processing_time:.1f}s)"
        )

        if progress_callback:
            progress_callback(100, 100, "Complete!")

        return {
````

Replace with:

````python
            f"({processing_time:.1f}s)"
        )

        return {
````

**Edit 9 of 11** (near line 238). Find exactly:

````python
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
````

Replace with:

````python
def _page_texts(pdf_path: str, total_pages: int, progress_callback=None) -> list[str]:
    """Each page's text, read by pypdf: reference matching was tuned
    against its extraction (spec D4). A file pypdf cannot open still
    processes -- its pages just come out unmatched.

    progress_callback is told (i, total_pages, READING) after each page. It
    is called outside the per-page try, so a ProcessingCancelled it raises
    is not swallowed as an extraction failure."""
    try:
        reader = PdfReader(pdf_path)
    except Exception:
        logger.warning(f"pypdf could not open {pdf_path}; pages will be unmatched", exc_info=True)
        if progress_callback:
            progress_callback(total_pages, total_pages, READING)
        return [""] * total_pages
    texts = []
````

**Edit 10 of 11** (near line 252). Find exactly:

````python
            logger.warning(f"Failed to extract text from page {i+1}: {e}")
            texts.append("")
    return texts
````

Replace with:

````python
            logger.warning(f"Failed to extract text from page {i+1}: {e}")
            texts.append("")
        if progress_callback:
            progress_callback(i + 1, total_pages, READING)
    return texts
````

**Edit 11 of 11** (near line 375). Find exactly:

````python
            if row_count > 0:
                logger.info(f"CSV loaded with encoding {encoding}: {row_count} rows")
                return mappings
````

Replace with:

````python
            if row_count > 0:
                logger.info(f"CSV loaded with encoding {encoding}: {row_count} rows")
                mappings['rows'] = row_count
                return mappings
````

- [ ] **Step 4: Run the tests and see them pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_pdf_processor.py tests/test_reference_matching.py tests/audit/test_04_outputs.py`
Expected: all pass (71 passed).

- [ ] **Step 5: Lint**

Run: `.venv/bin/ruff check shopify_tool/pdf_processor.py tests/test_pdf_processor.py`
Expected: `All checks passed!`

- [ ] **Step 6: Commit**

Message: `Reference labels: counted progress, cancel, and a page count (phase 5 spec 7.1)`.
Add `shopify_tool/pdf_processor.py` and `tests/test_pdf_processor.py`.

---

### Task 2: One packing list's labels in one call (`shopify_tool/barcode_processor.py`)

**Files:**
- Modify: `shopify_tool/barcode_processor.py` (append)
- Test: `tests/test_barcode_processor.py` (append)

**Interfaces:**
- Consumes: `generate_barcodes_batch`, `generate_code128_labels_pdf`, `generate_qr_labels_pdf`,
  `barcode_pdf_path`, `qr_pdf_path` (all in this module), `shopify_tool.packing_lists.sort_for_packing_list`,
  `shopify_tool.tag_manager.merge_tags`.
- Produces:
  - `packing_list_orders(xlsx_path) -> frozenset`, raising `ValueError` with no `Order_Number` column.
  - `generate_list_labels(orders_df, folder, list_stem, *, qr=False, progress=None) -> dict` returning
    `{"list": str, "folder": str, "labels": int, "failed": int, "pdf": str | None, "qr_pdf": str | None,
    "qr_failed": bool}`. `progress(label: str)` is told `"Writing 120 barcode labels…"` and, with `qr`,
    `"Writing 120 QR labels…"`. It raises `BarcodeGenerationError` when the barcode PDF cannot be rendered.

This is the body of `BarcodeGeneratorWidget._generate_barcodes_worker` plus the two renders that today run on
the GUI thread in `_on_generation_complete`. The old widget is untouched until Task 9.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_barcode_processor.py`:

````python
# --- one packing list, start to finish (phase 5 spec section 7.2) -------------


def _order_lines():
    """Three order lines over two orders, out of packing-list order."""
    return pd.DataFrame(
        {
            "Order_Number": ["#10", "#9", "#9"],
            "SKU": ["A", "B", "C"],
            "Quantity": [1, 2, 3],
            "Shipping_Provider": ["DHL", "DHL", "DHL"],
            "Destination_Country": ["DE", "BG", "BG"],
            "Internal_Tags": ['["GIFT"]', '["BOX"]', '["FRAGILE"]'],
        }
    )


class TestPackingListOrders:
    def test_reads_the_order_numbers(self, tmp_path):
        from shopify_tool.barcode_processor import packing_list_orders

        path = tmp_path / "DHL.xlsx"
        pd.DataFrame({"Order_Number": ["#9", "#9", "#10"], "SKU": ["B", "C", "A"]}).to_excel(
            path, index=False
        )
        assert packing_list_orders(path) == frozenset({"#9", "#10"})

    def test_a_sheet_with_no_order_number_column_is_refused(self, tmp_path):
        from shopify_tool.barcode_processor import packing_list_orders

        path = tmp_path / "odd.xlsx"
        pd.DataFrame({"SKU": ["A"]}).to_excel(path, index=False)
        with pytest.raises(ValueError, match="Order_Number"):
            packing_list_orders(path)


class TestGenerateListLabels:
    def test_writes_the_barcode_pdf_and_says_what_it_did(self, tmp_path):
        from shopify_tool.barcode_processor import generate_list_labels

        folder = tmp_path / "barcodes" / "DHL"
        said = []
        outcome = generate_list_labels(_order_lines(), folder, "DHL", progress=said.append)

        assert outcome == {
            "list": "DHL",
            "folder": str(folder),
            "labels": 2,
            "failed": 0,
            "pdf": str(folder / "DHL_barcodes.pdf"),
            "qr_pdf": None,
            "qr_failed": False,
        }
        assert len(pypdf.PdfReader(outcome["pdf"]).pages) == 2
        assert said == ["Writing 2 barcode labels…"]

    def test_with_qr_it_writes_both_and_reports_twice(self, tmp_path):
        from shopify_tool.barcode_processor import generate_list_labels

        folder = tmp_path / "barcodes" / "DHL"
        said = []
        outcome = generate_list_labels(
            _order_lines(), folder, "DHL", qr=True, progress=said.append
        )

        assert outcome["qr_pdf"] == str(folder / "DHL_qr_labels.pdf")
        assert len(pypdf.PdfReader(outcome["qr_pdf"]).pages) == 2
        assert said == ["Writing 2 barcode labels…", "Writing 2 QR labels…"]

    def test_one_label_is_singular(self, tmp_path, monkeypatch):
        from shopify_tool import barcode_processor

        monkeypatch.setattr(
            barcode_processor, "generate_code128_labels_pdf", lambda orders, path: path
        )
        said = []
        barcode_processor.generate_list_labels(
            _order_lines().iloc[:1], tmp_path, "DHL", progress=said.append
        )
        assert said == ["Writing 1 barcode label…"]

    def test_labels_are_numbered_in_packing_list_order_with_summed_items(
        self, tmp_path, monkeypatch
    ):
        from shopify_tool import barcode_processor

        seen = []
        monkeypatch.setattr(
            barcode_processor,
            "generate_code128_labels_pdf",
            lambda orders, path: seen.extend(orders) or path,
        )
        barcode_processor.generate_list_labels(_order_lines(), tmp_path, "DHL")

        # "#9" sorts before "#10", and its two lines add up.
        assert [(o["order_number"], o["sequential_num"], o["item_count"]) for o in seen] == [
            ("#9", 1, 5),
            ("#10", 2, 1),
        ]
        # Every line's tags reach the label, not just the first line's.
        assert seen[0]["tag"] == "BOX|FRAGILE"

    def test_a_qr_failure_keeps_the_barcode_pdf(self, tmp_path, monkeypatch):
        from shopify_tool import barcode_processor

        def broken(_orders, _path):
            raise barcode_processor.BarcodeGenerationError("no QR today")

        monkeypatch.setattr(barcode_processor, "generate_qr_labels_pdf", broken)
        folder = tmp_path / "barcodes" / "DHL"
        outcome = barcode_processor.generate_list_labels(
            _order_lines(), folder, "DHL", qr=True
        )
        assert outcome["qr_failed"] is True
        assert outcome["qr_pdf"] is None
        assert (folder / "DHL_barcodes.pdf").exists()

    def test_a_barcode_render_failure_raises(self, tmp_path, monkeypatch):
        from shopify_tool import barcode_processor

        def broken(_orders, _path):
            raise barcode_processor.BarcodeGenerationError("renderer down")

        monkeypatch.setattr(barcode_processor, "generate_code128_labels_pdf", broken)
        with pytest.raises(barcode_processor.BarcodeGenerationError):
            barcode_processor.generate_list_labels(_order_lines(), tmp_path, "DHL")

    def test_order_numbers_that_cannot_be_encoded_are_counted_not_rendered(
        self, tmp_path, monkeypatch
    ):
        from shopify_tool import barcode_processor

        rendered = []
        monkeypatch.setattr(
            barcode_processor,
            "generate_code128_labels_pdf",
            lambda orders, path: rendered.append(len(orders)) or path,
        )
        lines = _order_lines()
        lines.loc[0, "Order_Number"] = "!!!"
        outcome = barcode_processor.generate_list_labels(lines, tmp_path, "DHL")
        assert (outcome["labels"], outcome["failed"]) == (1, 1)
        assert rendered == [1]

    def test_when_no_order_can_be_encoded_nothing_is_rendered(self, tmp_path, monkeypatch):
        from shopify_tool import barcode_processor

        rendered = []
        monkeypatch.setattr(
            barcode_processor,
            "generate_code128_labels_pdf",
            lambda orders, path: rendered.append(1) or path,
        )
        lines = _order_lines().iloc[:1].copy()
        lines.loc[0, "Order_Number"] = "!!!"
        said = []
        outcome = barcode_processor.generate_list_labels(
            lines, tmp_path, "DHL", qr=True, progress=said.append
        )
        assert (outcome["labels"], outcome["failed"], outcome["pdf"]) == (0, 1, None)
        assert rendered == [] and said == []
````

- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_barcode_processor.py`
Expected: the new tests fail with `ImportError: cannot import name 'packing_list_orders'` and
`AttributeError: ... has no attribute 'generate_list_labels'`; every older test passes.

- [ ] **Step 3: Implement**

Append to `shopify_tool/barcode_processor.py`:

````python
# === ONE PACKING LIST, START TO FINISH ===

def packing_list_orders(xlsx_path) -> frozenset:
    """The order numbers a packing list workbook holds, as pandas reads them.

    Raises:
        ValueError: If the sheet has no Order_Number column.
    """
    frame = pd.read_excel(xlsx_path)
    if "Order_Number" not in frame.columns:
        raise ValueError(f"Packing list has no Order_Number column: {xlsx_path}")
    return frozenset(frame["Order_Number"].dropna().unique())


def _writing(count: int, kind: str) -> str:
    return f"Writing {count:,} {kind} label{'' if count == 1 else 's'}…"


def generate_list_labels(
    orders_df: pd.DataFrame,
    folder,
    list_stem: str,
    *,
    qr: bool = False,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Write one packing list's label PDFs: the barcode labels, and with
    `qr` the QR labels beside them.

    Everything slow is in here, so a caller runs it on a worker thread
    (phase 5 spec section 7.2). `progress` is told one sentence before each
    render; a render is a single WeasyPrint call and reports nothing itself.

    Args:
        orders_df: The Fulfillable rows of the orders on this list, one row
            per order line (Order_Number, Quantity, Shipping_Provider, ...).
        folder: Where the PDFs go (barcodes_dir(session, list_stem)).
        list_stem: The packing list's name; it names the PDFs.

    Returns:
        {"list", "folder", "labels": labels written, "failed": orders whose
        number could not be encoded, "pdf": path or None, "qr_pdf": path or
        None, "qr_failed": bool}

    Raises:
        BarcodeGenerationError: If the barcode PDF cannot be rendered. A QR
            failure is logged and reported as qr_failed; the barcode PDF stands.
    """
    # Local imports: both modules import this one's helpers.
    from shopify_tool.packing_lists import sort_for_packing_list
    from shopify_tool.tag_manager import merge_tags

    # One row per order, carrying the order's total quantity.
    unique_orders = orders_df.groupby("Order_Number").first().reset_index()
    item_counts = orders_df.groupby("Order_Number")["Quantity"].sum().to_dict()
    unique_orders["item_count"] = unique_orders["Order_Number"].map(item_counts)

    # Merge tags from ALL rows of each order (not just the first row).
    # Internal_Tags is a serialized list (JSON string or native list), not
    # flat comma-separated text -- use tag_manager's parser/merger rather
    # than splitting the string ourselves, which corrupts multi-tag values
    # into something format_tags_for_barcode can't parse and leaks the raw
    # literal onto the printed label.
    if "Internal_Tags" in orders_df.columns:
        merged_tags = {
            order: merge_tags(group["Internal_Tags"].dropna().tolist())
            for order, group in orders_df.groupby("Order_Number", sort=False)
        }
        unique_orders["Internal_Tags"] = unique_orders["Order_Number"].map(merged_tags)

    # Label N is the N-th order on the packing list.
    unique_orders = sort_for_packing_list(unique_orders).reset_index(drop=True)

    results = generate_barcodes_batch(df=unique_orders)
    successful = [r for r in results if r["success"]]
    folder = Path(folder)
    outcome: dict[str, Any] = {
        "list": list_stem,
        "folder": str(folder),
        "labels": len(successful),
        "failed": len(results) - len(successful),
        "pdf": None,
        "qr_pdf": None,
        "qr_failed": False,
    }
    logger.info(
        f"Barcode generation for packing list {list_stem!r}: "
        f"{len(results)} orders filtered, "
        f"{outcome['labels']} labels written, {outcome['failed']} failed"
    )
    if not successful:
        return outcome

    if progress:
        progress(_writing(len(successful), "barcode"))
    outcome["pdf"] = str(
        generate_code128_labels_pdf(successful, barcode_pdf_path(folder, list_stem))
    )

    if qr:
        if progress:
            progress(_writing(len(successful), "QR"))
        try:
            outcome["qr_pdf"] = str(
                generate_qr_labels_pdf(successful, qr_pdf_path(folder, list_stem))
            )
        except Exception:
            logger.exception("QR labels PDF generation failed")
            outcome["qr_failed"] = True
    return outcome
````

- [ ] **Step 4: Run the tests and see them pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_barcode_processor.py`
Expected: all pass (46 passed). The tests that write a real PDF go through WeasyPrint and take a second or two.

- [ ] **Step 5: Lint**

Run: `.venv/bin/ruff check shopify_tool/barcode_processor.py tests/test_barcode_processor.py`
Expected: `All checks passed!`

- [ ] **Step 6: Commit**

Message: `Barcode labels: one packing list's PDFs in one call (phase 5 spec 7.2)`.
Add `shopify_tool/barcode_processor.py` and `tests/test_barcode_processor.py`.

---

### Task 3: The state (`gui/tools_state.py`)

**Files:**
- Create: `gui/tools_state.py`
- Modify: `gui/setup_state.py`
- Test: `tests/test_tools_state.py` (new)

**Interfaces:**
- Consumes: `gui.setup_state.SessionFacts(name, opened, analysed)`; from Task 1, `READING`, `STAMPING`,
  `SAVING` and the existing `reference_run_warning(result) -> str | None`.
- Produces (all in `gui/tools_state.py`):
  - `PickedFile(name, count=None, problem=None)`, `ToolRun(label, done=0, total=0, cancelling=False)`,
    `ReferenceFacts(pdf, csv, folder, open_pdf, run, result, has_output)`,
    `PackingList(name, count, has_labels=False, has_qr=False)`,
    `BarcodeFacts(lists, loading, analysed, selected, folder, qr, open_pdf, run, result)`,
    `PrintFacts(settings, printers=())`. All are frozen dataclasses. The required fields are
    `PickedFile.name`, `ToolRun.label`, `PackingList.name` and `.count`, and `PrintFacts.settings`; every
    other field has a default, so `ReferenceFacts()` and `BarcodeFacts()` are the empty tools.
  - `tools_state(*, client, session, reference, reference_print, barcode, barcode_print, now) -> dict`
    (the shape is spec §4.2).
  - `apply_print_edit(settings: dict, key: str, value) -> dict | None`.
  - `short_path(path: str) -> str`, `PRINT_SCOPE = {"reference": "reference_labels", "barcode":
    "barcode_generator"}`, `MODES = ("driver", "raw_zpl")`, `REFERENCE_SIZE_HINT`, `BARCODE_SIZE_HINT`.
  - In `gui/setup_state.py`: `session_meta(client: str, session: SessionFacts, now: datetime) -> str`.
- `tests/test_tools_state.py` also exports the builders the page test (Task 6) imports: `make_state`,
  `reference`, `barcode`, and the constants `DRIVER`, `ZPL`, `PRINTERS`, `BAD_CSV`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tools_state.py`:

````python
"""Everything the Tools page draws, built from plain facts (phase 5 spec section 4)."""

import os
from datetime import datetime

import pytest

from gui.setup_state import SessionFacts
from gui.tools_state import (
    BARCODE_SIZE_HINT,
    REFERENCE_SIZE_HINT,
    BarcodeFacts,
    PackingList,
    PickedFile,
    PrintFacts,
    ReferenceFacts,
    ToolRun,
    apply_print_edit,
    short_path,
    tools_state,
)
from shopify_tool.pdf_processor import READING, SAVING, STAMPING

NOW = datetime(2026, 9, 30, 15, 0).astimezone()
OPENED = datetime(2026, 9, 30, 14, 2).astimezone()
SESSION = SessionFacts("2026-09-30_1", OPENED, None)
SEP = os.sep
REF_FOLDER = SEP.join(["", "srv", "ACME", "2026-09-30_1", "reference_labels"])
DHL_FOLDER = SEP.join(["", "srv", "ACME", "2026-09-30_1", "barcodes", "DHL"])

DRIVER = {
    "print_mode": "driver",
    "raw_zpl_target": "",
    "raw_zpl_rotate": False,
    "raw_zpl_invert": False,
    "raw_zpl_label_width_mm": 0.0,
    "raw_zpl_label_height_mm": 0.0,
    "driver_printer_name": "",
}
ZPL = {**DRIVER, "print_mode": "raw_zpl", "raw_zpl_target": "Zebra ZD421"}
PRINTERS = ("Zebra ZD421", "HP LaserJet")

PDF = PickedFile("dhl-labels-30-09.pdf", 120)
CSV = PickedFile("acme-refs-30-09.csv", 120)
BAD_CSV = PickedFile(
    "acme-refs-30-09.csv", None, ("This CSV has no usable rows", "Each row needs…")
)
BAD_PDF = PickedFile("dhl.pdf", None, ("This PDF can't be read", "Check that it isn't damaged…"))

LISTS = (
    PackingList("DHL", 120),
    PackingList("DPD", 48),
    PackingList("Royal Mail", 31),
)


def reference(**over):
    """The mockup's Ready state for Reference labels."""
    facts = {"pdf": PDF, "csv": CSV, "folder": REF_FOLDER}
    facts.update(over)
    return ReferenceFacts(**facts)


def barcode(**over):
    """The mockup's Ready state for Barcode labels."""
    facts = {"lists": LISTS, "selected": "DHL", "folder": DHL_FOLDER}
    facts.update(over)
    return BarcodeFacts(**facts)


def make_state(**over):
    """tools_state with the mockup's Ready state as the default."""
    facts = {
        "client": "ACME",
        "session": SESSION,
        "reference": reference(),
        "reference_print": PrintFacts(DRIVER, PRINTERS),
        "barcode": barcode(),
        "barcode_print": PrintFacts(ZPL, PRINTERS),
        "now": NOW,
    }
    facts.update(over)
    return tools_state(**facts)


# --- session and banner ------------------------------------------------------


def test_with_a_session_the_head_names_it_and_there_is_no_banner():
    state = make_state()
    assert state["session"] == {"name": "2026-09-30_1", "meta": "ACME · opened 14:02"}
    assert state["banner"] is False


def test_an_analysed_session_says_when():
    analysed = datetime(2026, 9, 30, 14, 6).astimezone()
    state = make_state(session=SessionFacts("2026-09-30_1", OPENED, analysed))
    assert state["session"]["meta"] == "ACME · analysed 14:06"


def test_with_no_session_the_banner_shows_and_both_cards_go_quiet():
    state = make_state(session=None, reference=ReferenceFacts(), barcode=BarcodeFacts())
    assert state["session"] == {}
    assert state["banner"] is True
    for card in (state["reference"], state["barcode"]):
        assert card["quiet"] is True
        assert card["reason"] == ""
        assert card["can_run"] is False
        assert card["print_button"]["enabled"] is False
        assert card["folder"] == {"text": "Session folder", "title": "", "muted": True}
    assert state["barcode"]["lists"] == []
    assert state["barcode"]["list"]["placeholder"] == "No packing lists"


def test_no_session_hides_facts_left_from_the_last_one():
    # The tools clear themselves on a session change; the state does not rely on it.
    state = make_state(session=None)
    assert state["reference"]["folder"]["muted"] is True
    assert state["barcode"]["lists"] == []
    assert state["barcode"]["qr_button"] == {}


# --- a short path -------------------------------------------------------------


def test_a_short_path_is_the_last_two_parts():
    assert short_path(REF_FOLDER) == f"…{SEP}2026-09-30_1{SEP}reference_labels"


def test_a_short_path_reads_a_windows_path_on_any_platform():
    assert short_path(r"\\fs01\fulfilment\ACME\2026-09-30_1\barcodes\DHL") == (
        f"…{SEP}barcodes{SEP}DHL"
    )


# --- reference labels ---------------------------------------------------------


def test_reference_ready():
    card = make_state()["reference"]
    assert card["pdf"] == {"name": "dhl-labels-30-09.pdf", "meta": "120 pages", "problem": {}}
    assert card["csv"] == {"name": "acme-refs-30-09.csv", "meta": "120 rows", "problem": {}}
    assert card["folder"] == {
        "text": f"…{SEP}2026-09-30_1{SEP}reference_labels",
        "title": REF_FOLDER,
        "muted": False,
    }
    assert (card["reason"], card["tone"]) == ("120 pages, 120 CSV rows.", "")
    assert card["can_run"] is True
    assert card["quiet"] is False and card["locked"] is False
    assert card["run"] == {}
    assert card["open_pdf"] is True


def test_one_page_and_one_row_are_singular_and_thousands_take_a_comma():
    card = make_state(
        reference=reference(pdf=PickedFile("a.pdf", 1), csv=PickedFile("a.csv", 1))
    )["reference"]
    assert (card["pdf"]["meta"], card["csv"]["meta"]) == ("1 page", "1 row")
    assert card["reason"] == "1 page, 1 CSV row."
    card = make_state(
        reference=reference(pdf=PickedFile("a.pdf", 1204), csv=PickedFile("a.csv", 1204))
    )["reference"]
    assert card["pdf"]["meta"] == "1,204 pages"
    assert card["reason"] == "1,204 pages, 1,204 CSV rows."


@pytest.mark.parametrize(
    ("over", "reason", "tone"),
    [
        ({"pdf": BAD_PDF}, "Fix the labels PDF to process.", "danger"),
        ({"csv": BAD_CSV}, "Fix the mapping CSV to process.", "danger"),
        ({"pdf": BAD_PDF, "csv": BAD_CSV}, "Fix the labels PDF to process.", "danger"),
        ({"pdf": None, "csv": None}, "Choose the labels PDF and mapping CSV.", ""),
        ({"pdf": None}, "Choose the labels PDF.", ""),
        ({"csv": None}, "Choose the mapping CSV.", ""),
    ],
)
def test_reference_says_what_is_missing_and_cannot_run(over, reason, tone):
    card = make_state(reference=reference(**over))["reference"]
    assert (card["reason"], card["tone"]) == (reason, tone)
    assert card["can_run"] is False


def test_a_problem_file_shows_its_problem_on_its_row():
    card = make_state(reference=reference(csv=BAD_CSV))["reference"]
    assert card["csv"] == {
        "name": "acme-refs-30-09.csv",
        "meta": "Problem",
        "problem": {"title": "This CSV has no usable rows", "text": "Each row needs…"},
    }
    assert make_state(reference=reference(csv=None))["reference"]["csv"] == {}


RESULT = {
    "output_file": "/out/labels.pdf",
    "pages_processed": 120,
    "matched": 120,
    "unmatched": 0,
    "duplicate_refs": [],
    "missing_refs": [],
    "name_matched": 0,
}


@pytest.mark.parametrize(
    ("over", "reason"),
    [
        ({}, "120 of 120 labels matched."),
        ({"matched": 118, "unmatched": 2}, "118 of 120 labels matched, 2 unmatched."),
        ({"name_matched": 3}, "120 of 120 labels matched. 3 matched by name only."),
        (
            {"matched": 118, "unmatched": 2, "name_matched": 3},
            "118 of 120 labels matched, 2 unmatched. 3 matched by name only.",
        ),
    ],
)
def test_after_a_run_the_reason_says_what_matched(over, reason):
    card = make_state(reference=reference(result={**RESULT, **over}, has_output=True))[
        "reference"
    ]
    assert (card["reason"], card["tone"]) == (reason, "")
    assert card["can_run"] is True


def test_a_run_that_needs_checking_keeps_its_warning_on_screen():
    result = {**RESULT, "duplicate_refs": ["12"], "missing_refs": ["14"]}
    card = make_state(reference=reference(result=result, has_output=True))["reference"]
    assert card["tone"] == "warning"
    assert card["reason"].startswith("Check before printing: ")
    assert "12" in card["reason"] and "14" in card["reason"]


def test_reference_needs_a_folder_to_run():
    assert make_state(reference=reference(folder=""))["reference"]["can_run"] is False


@pytest.mark.parametrize(
    ("run", "label", "count", "percent", "cancel"),
    [
        (ToolRun(READING, 0, 120), "Reading labels", "0 of 120", 0, True),
        (ToolRun(READING, 60, 120), "Reading labels", "60 of 120", 25, True),
        (ToolRun(READING, 120, 120), "Reading labels", "120 of 120", 50, True),
        (ToolRun(STAMPING, 40, 120), "Stamping labels", "40 of 120", 66, True),
        (ToolRun(STAMPING, 120, 120), "Stamping labels", "120 of 120", 100, True),
        (ToolRun(SAVING, 120, 120), "Saving…", "", 100, False),
    ],
)
def test_a_counted_run_draws_one_bar_that_never_goes_back(run, label, count, percent, cancel):
    card = make_state(reference=reference(run=run))["reference"]
    assert card["locked"] is True
    assert card["reason"] == ""
    assert card["can_run"] is False
    assert card["run"]["label"] == label
    assert card["run"]["count"] == count
    assert card["run"]["bar"] is True
    assert card["run"]["percent"] == percent
    assert card["run"]["cancel"]["enabled"] is cancel


def test_cancel_says_what_it_is_doing_and_why_it_cannot():
    going = make_state(reference=reference(run=ToolRun(STAMPING, 40, 120)))["reference"]
    assert going["run"]["cancel"] == {"label": "Cancel", "enabled": True, "title": ""}
    cancelling = make_state(
        reference=reference(run=ToolRun(STAMPING, 40, 120, cancelling=True))
    )["reference"]
    assert cancelling["run"]["cancel"] == {
        "label": "Cancelling…",
        "enabled": False,
        "title": "",
    }
    saving = make_state(reference=reference(run=ToolRun(SAVING, 120, 120)))["reference"]
    assert saving["run"]["cancel"] == {
        "label": "Cancel",
        "enabled": False,
        "title": "Saving can't be cancelled",
    }


def test_a_big_count_takes_commas():
    card = make_state(reference=reference(run=ToolRun(READING, 1200, 2400)))["reference"]
    assert card["run"]["count"] == "1,200 of 2,400"


def test_one_card_running_does_not_lock_the_other():
    state = make_state(reference=reference(run=ToolRun(READING, 1, 2)))
    assert state["reference"]["locked"] is True
    assert state["barcode"]["locked"] is False
    assert state["barcode"]["can_run"] is True


# --- barcode labels -----------------------------------------------------------


def test_barcode_ready():
    card = make_state()["barcode"]
    assert card["list"] == {"name": "DHL", "meta": "120 Fulfillable", "placeholder": ""}
    assert card["lists"] == [
        {"name": "DHL", "meta": "120", "checked": True},
        {"name": "DPD", "meta": "48", "checked": False},
        {"name": "Royal Mail", "meta": "31", "checked": False},
    ]
    assert card["folder"] == {
        "text": f"…{SEP}barcodes{SEP}DHL",
        "title": DHL_FOLDER,
        "muted": False,
    }
    assert (card["reason"], card["tone"]) == (f"Saves to …{SEP}barcodes{SEP}DHL.", "")
    assert card["can_run"] is True
    assert card["qr"] is False and card["open_pdf"] is True
    assert card["run"] == {}
    assert card["qr_button"] == {}


def test_with_qr_ticked_the_reason_says_so():
    card = make_state(barcode=barcode(qr=True))["barcode"]
    assert card["reason"] == f"Saves to …{SEP}barcodes{SEP}DHL, with QR labels."


def _dhl(**over):
    return (PackingList("DHL", **{"count": 120, **over}), *LISTS[1:])


@pytest.mark.parametrize(
    ("facts", "reason", "tone", "can_run"),
    [
        ({"lists": (), "selected": "", "loading": True}, "Reading packing lists…", "", False),
        (
            {"lists": (), "selected": ""},
            "No packing lists in this session yet. Generate one on Results, then Refresh.",
            "",
            False,
        ),
        (
            {"analysed": False, "lists": _dhl(count=None)},
            "This session has no analysis loaded. Run it on Setup.",
            "",
            False,
        ),
        ({"selected": ""}, "Choose a packing list.", "", False),
        (
            {"lists": _dhl(count=None)},
            "This packing list couldn't be read. Details are in Logs.",
            "danger",
            False,
        ),
        ({"lists": _dhl(count=0)}, "No Fulfillable orders in this list.", "", False),
        (
            {"result": {"list": "DHL", "labels": 118, "failed": 2}},
            "118 labels written, 2 order numbers couldn't be encoded. Details are in Logs.",
            "warning",
            True,
        ),
        (
            {"result": {"list": "DHL", "labels": 1, "failed": 1}},
            "1 label written, 1 order number couldn't be encoded. Details are in Logs.",
            "warning",
            True,
        ),
        (
            {"result": {"list": "DHL", "labels": 120, "failed": 0, "qr_failed": True}},
            "Barcode labels written. The QR labels failed; details are in Logs.",
            "warning",
            True,
        ),
        (
            {"lists": _dhl(has_labels=True)},
            f"Generating again replaces the labels in …{SEP}barcodes{SEP}DHL.",
            "",
            True,
        ),
    ],
)
def test_barcode_reasons(facts, reason, tone, can_run):
    card = make_state(barcode=barcode(**facts))["barcode"]
    assert (card["reason"], card["tone"]) == (reason, tone)
    assert card["can_run"] is can_run


def test_a_refresh_with_lists_on_screen_keeps_them_and_their_reason():
    card = make_state(barcode=barcode(loading=True))["barcode"]
    assert card["list"]["name"] == "DHL"
    assert card["reason"] == f"Saves to …{SEP}barcodes{SEP}DHL."


def test_a_result_for_another_list_says_nothing_about_this_one():
    card = make_state(barcode=barcode(result={"list": "DPD", "labels": 1, "failed": 9}))[
        "barcode"
    ]
    assert card["tone"] == ""


@pytest.mark.parametrize(
    ("facts", "shown"),
    [
        (
            {"lists": (), "selected": "", "loading": True},
            {"name": "", "meta": "", "placeholder": "Reading packing lists…"},
        ),
        (
            {"lists": (), "selected": ""},
            {"name": "", "meta": "", "placeholder": "No packing lists"},
        ),
        ({"selected": ""}, {"name": "", "meta": "", "placeholder": "Choose a packing list"}),
        (
            {"lists": _dhl(count=None)},
            {"name": "DHL", "meta": "Unreadable", "placeholder": ""},
        ),
    ],
)
def test_what_the_packing_list_select_shows(facts, shown):
    assert make_state(barcode=barcode(**facts))["barcode"]["list"] == shown


def test_an_unreadable_list_shows_a_dash_in_the_menu():
    card = make_state(barcode=barcode(lists=_dhl(count=None)))["barcode"]
    assert card["lists"][0] == {"name": "DHL", "meta": "—", "checked": True}


def test_with_no_list_chosen_the_folder_asks_for_one():
    card = make_state(barcode=barcode(selected="", folder=""))["barcode"]
    assert card["folder"] == {"text": "Choose a packing list", "title": "", "muted": True}


def test_a_barcode_run_is_a_sentence_with_no_bar_and_no_cancel():
    card = make_state(barcode=barcode(run=ToolRun("Writing 120 barcode labels…")))[
        "barcode"
    ]
    assert card["locked"] is True
    assert card["can_run"] is False
    assert card["reason"] == ""
    assert card["run"] == {
        "label": "Writing 120 barcode labels…",
        "count": "",
        "bar": False,
        "percent": 0,
        "cancel": {},
    }


# --- the print block ----------------------------------------------------------


def test_driver_mode_lists_windows_default_first():
    block = make_state()["reference"]["print"]
    assert block["mode"] == "driver"
    assert block["printer"] == {"value": "", "label": "Windows default", "placeholder": False}
    assert block["printers"] == [
        {"value": "", "label": "Windows default", "checked": True},
        {"value": "Zebra ZD421", "label": "Zebra ZD421", "checked": False},
        {"value": "HP LaserJet", "label": "HP LaserJet", "checked": False},
    ]
    assert block["help"] == (
        "Prints stamped labels through the Windows print dialog. Saved for this PC."
    )
    assert block["help_tone"] == ""
    assert block["setup"] == {}


def test_driver_mode_shows_its_saved_printer():
    saved = {**DRIVER, "driver_printer_name": "HP LaserJet"}
    block = make_state(reference_print=PrintFacts(saved, PRINTERS))["reference"]["print"]
    assert block["printer"]["label"] == "HP LaserJet"
    assert [p["checked"] for p in block["printers"]] == [False, False, True]


def test_raw_zpl_lists_the_installed_printers_and_its_setup():
    block = make_state()["barcode"]["print"]
    assert block["mode"] == "raw_zpl"
    assert block["printer"] == {
        "value": "Zebra ZD421",
        "label": "Zebra ZD421",
        "placeholder": False,
    }
    assert block["printers"] == [
        {"value": "Zebra ZD421", "label": "Zebra ZD421", "checked": True},
        {"value": "HP LaserJet", "label": "HP LaserJet", "checked": False},
    ]
    assert block["help"] == (
        "Sends barcode labels straight to the label printer as ZPL, no dialog. "
        "Saved for this PC."
    )
    assert block["setup"] == {
        "summary": "the PDF's page size",
        "target": "Zebra ZD421",
        "width": 0.0,
        "height": 0.0,
        "rotate": False,
        "invert": False,
        "size_hint": BARCODE_SIZE_HINT,
    }


def test_each_tool_carries_its_own_size_hint():
    state = make_state(reference_print=PrintFacts(ZPL, PRINTERS))
    assert state["reference"]["print"]["setup"]["size_hint"] == REFERENCE_SIZE_HINT


@pytest.mark.parametrize(
    ("over", "summary"),
    [
        ({}, "the PDF's page size"),
        ({"raw_zpl_label_width_mm": 152.4}, "the PDF's page size"),
        (
            {"raw_zpl_label_width_mm": 152.4, "raw_zpl_label_height_mm": 101.6},
            "152.4 × 101.6 mm",
        ),
        (
            {"raw_zpl_label_width_mm": 68.0, "raw_zpl_label_height_mm": 38.0},
            "68 × 38 mm",
        ),
        ({"raw_zpl_rotate": True}, "the PDF's page size, rotated 90°"),
        (
            {
                "raw_zpl_label_width_mm": 68.0,
                "raw_zpl_label_height_mm": 38.0,
                "raw_zpl_rotate": True,
                "raw_zpl_invert": True,
            },
            "68 × 38 mm, rotated 90°, colours inverted",
        ),
    ],
)
def test_the_label_setup_summary(over, summary):
    block = make_state(barcode_print=PrintFacts({**ZPL, **over}, PRINTERS))["barcode"]["print"]
    assert block["setup"]["summary"] == summary


def test_a_saved_printer_that_is_not_installed_is_still_listed():
    saved = {**ZPL, "raw_zpl_target": r"\\printsrv\zebra-3"}
    block = make_state(barcode_print=PrintFacts(saved, PRINTERS))["barcode"]["print"]
    assert block["printers"][-1] == {
        "value": r"\\printsrv\zebra-3",
        "label": r"\\printsrv\zebra-3",
        "checked": True,
    }
    driver = {**DRIVER, "driver_printer_name": "Old Canon"}
    block = make_state(reference_print=PrintFacts(driver, PRINTERS))["reference"]["print"]
    assert block["printers"][-1] == {"value": "Old Canon", "label": "Old Canon", "checked": True}


def test_raw_zpl_with_no_printer_says_so_in_the_danger_tone():
    block = make_state(barcode_print=PrintFacts({**ZPL, "raw_zpl_target": "  "}, PRINTERS))[
        "barcode"
    ]["print"]
    assert block["printer"] == {"value": "", "label": "Choose a printer", "placeholder": True}
    assert block["help"] == "Raw ZPL needs a printer. Choose the one the labels go to."
    assert block["help_tone"] == "danger"


def test_an_unknown_saved_mode_reads_as_driver():
    block = make_state(reference_print=PrintFacts({**DRIVER, "print_mode": "fax"}, ()))[
        "reference"
    ]["print"]
    assert block["mode"] == "driver"


def test_print_stays_live_with_no_session():
    state = make_state(session=None, reference=ReferenceFacts(), barcode=BarcodeFacts())
    assert state["reference"]["print"]["mode"] == "driver"
    assert state["barcode"]["print"]["setup"]["target"] == "Zebra ZD421"


# --- the print buttons --------------------------------------------------------


@pytest.mark.parametrize(
    ("settings", "has_output", "button"),
    [
        (DRIVER, False, {"label": "Print…", "title": "Process labels first", "enabled": False}),
        (DRIVER, True, {"label": "Print…", "title": "Open the print dialog", "enabled": True}),
        (ZPL, False, {"label": "Print", "title": "Process labels first", "enabled": False}),
        (ZPL, True, {"label": "Print", "title": "Send to Zebra ZD421", "enabled": True}),
        (
            {**ZPL, "raw_zpl_target": ""},
            True,
            {"label": "Print", "title": "Choose a printer under Print mode", "enabled": False},
        ),
    ],
)
def test_the_reference_print_button(settings, has_output, button):
    card = make_state(
        reference=reference(has_output=has_output),
        reference_print=PrintFacts(settings, PRINTERS),
    )["reference"]
    assert card["print_button"] == button


def test_print_is_off_while_its_card_runs():
    card = make_state(reference=reference(has_output=True, run=ToolRun(READING, 1, 2)))[
        "reference"
    ]
    assert card["print_button"]["enabled"] is False


def test_barcode_print_is_live_when_the_list_has_a_pdf_on_disk():
    off = make_state()["barcode"]["print_button"]
    assert off == {
        "label": "Print",
        "title": "Generate this list's labels first",
        "enabled": False,
    }
    on = make_state(barcode=barcode(lists=_dhl(has_labels=True)))["barcode"]["print_button"]
    assert on == {"label": "Print", "title": "Send to Zebra ZD421", "enabled": True}


@pytest.mark.parametrize(
    ("facts", "button"),
    [
        ({}, {}),
        (
            {"qr": True},
            {
                "label": "Print QR labels",
                "title": "Generate with QR labels ticked first",
                "enabled": False,
            },
        ),
        (
            {"lists": _dhl(has_qr=True)},
            {"label": "Print QR labels", "title": "Send to Zebra ZD421", "enabled": True},
        ),
        ({"qr": True, "selected": ""}, {}),
    ],
)
def test_the_qr_print_button(facts, button):
    assert make_state(barcode=barcode(**facts))["barcode"]["qr_button"] == button


def test_the_qr_button_takes_the_ellipsis_in_driver_mode():
    card = make_state(
        barcode=barcode(lists=_dhl(has_qr=True)), barcode_print=PrintFacts(DRIVER, PRINTERS)
    )["barcode"]
    assert card["qr_button"]["label"] == "Print QR labels…"
    assert card["print_button"]["label"] == "Print…"


# --- print edits --------------------------------------------------------------


def test_a_mode_edit():
    assert apply_print_edit(DRIVER, "mode", "raw_zpl")["print_mode"] == "raw_zpl"
    assert apply_print_edit(ZPL, "mode", "driver")["print_mode"] == "driver"
    assert apply_print_edit(DRIVER, "mode", "fax") is None


def test_a_printer_edit_writes_the_modes_own_key():
    assert apply_print_edit(DRIVER, "printer", "HP LaserJet")["driver_printer_name"] == (
        "HP LaserJet"
    )
    assert apply_print_edit(DRIVER, "printer", "HP LaserJet")["raw_zpl_target"] == ""
    out = apply_print_edit(ZPL, "printer", "HP LaserJet")
    assert out["raw_zpl_target"] == "HP LaserJet"
    assert out["driver_printer_name"] == ""
    assert apply_print_edit(DRIVER, "printer", 7) is None


def test_a_target_edit_is_stripped():
    assert apply_print_edit(ZPL, "target", "  /dev/usb/lp0 ")["raw_zpl_target"] == "/dev/usb/lp0"
    assert apply_print_edit(ZPL, "target", None) is None


@pytest.mark.parametrize(
    ("value", "stored"),
    [(152.4, 152.4), (68, 68.0), (0, 0.0), (-3, 0.0), (9999, 500.0), (101.64, 101.6)],
)
def test_a_size_edit_is_clamped_and_rounded(value, stored):
    assert apply_print_edit(ZPL, "width", value)["raw_zpl_label_width_mm"] == stored
    assert apply_print_edit(ZPL, "height", value)["raw_zpl_label_height_mm"] == stored


@pytest.mark.parametrize("value", [True, "68", None, float("nan")])
def test_a_size_edit_must_be_a_number(value):
    assert apply_print_edit(ZPL, "width", value) is None


def test_rotate_and_invert_must_be_bools():
    assert apply_print_edit(ZPL, "rotate", True)["raw_zpl_rotate"] is True
    assert apply_print_edit(ZPL, "invert", True)["raw_zpl_invert"] is True
    assert apply_print_edit(ZPL, "rotate", 1) is None
    assert apply_print_edit(ZPL, "invert", "yes") is None


def test_an_unknown_key_is_dropped_and_the_input_is_never_changed():
    before = dict(ZPL)
    assert apply_print_edit(ZPL, "print_mode", "driver") is None
    assert apply_print_edit(ZPL, "width", 68) is not ZPL
    assert before == ZPL
````

- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_tools_state.py`
Expected: an error while collecting: `ModuleNotFoundError: No module named 'gui.tools_state'`.

- [ ] **Step 3: Extract `session_meta`**

In `gui/setup_state.py`:

**Edit 1 of 2** (near line 180). Find exactly:

````python
def _stat(key: str, value) -> dict:
    return {"k": key, "v": _n(value), "muted": value is None}
````

Replace with:

````python
def session_meta(client: str, session: SessionFacts, now: datetime) -> str:
    """What a page head says beside the session chip: "ACME · opened 14:02",
    "ACME · analysed 14:06" once analysed, the client alone with no time.
    Setup and Tools both draw it."""
    moment = session.analysed or session.opened
    verb = "analysed" if session.analysed is not None else "opened"
    return f"{client} · {verb} {_when(moment, now)}" if moment else client


def _stat(key: str, value) -> dict:
    return {"k": key, "v": _n(value), "muted": value is None}
````

**Edit 2 of 2** (near line 322). Find exactly:

````python
        session_out = {}
    else:
        moment = session.analysed or session.opened
        verb = "analysed" if analysed else "opened"
        session_out = {
            "name": session.name,
            "title": "Session" if analysed else "New session",
            "meta": f"{client} · {verb} {_when(moment, now)}" if moment else client,
        }
````

Replace with:

````python
        session_out = {}
    else:
        session_out = {
            "name": session.name,
            "title": "Session" if analysed else "New session",
            "meta": session_meta(client, session, now),
        }
````

- [ ] **Step 4: Write the state**

Create `gui/tools_state.py`:

````python
"""Everything the Tools page draws, built in one place (phase 5 spec section 4).

Python owns every fact and every sentence: tools_state() returns one dict and
gui/web/tools.js renders it. No Qt in this module, so the whole rule set runs
under plain pytest.
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from datetime import datetime

from gui.setup_state import SessionFacts, session_meta
from shopify_tool.pdf_processor import READING, SAVING, STAMPING, reference_run_warning

MODES = ("driver", "raw_zpl")
# The QSettings scope each tool's print settings live under. They predate
# this page and must not change: every PC keeps what it has saved.
PRINT_SCOPE = {"reference": "reference_labels", "barcode": "barcode_generator"}

REFERENCE_SIZE_HINT = (
    "Physical label size as loaded in the printer, e.g. 152.4 x 101.6 for 6x4in "
    "shipping labels. 0 disables fitting and uses each page's own PDF size."
)
BARCODE_SIZE_HINT = (
    "Physical label size as loaded in the printer, e.g. 68 x 38 for this flow's "
    "default label stock. 0 disables fitting and uses the generated PDF's own page size."
)


@dataclass(frozen=True)
class PickedFile:
    """One picked input file, as its row shows it."""

    name: str
    count: int | None = None  # pages, or CSV rows; None with a problem
    problem: tuple[str, str] | None = None  # (title, text)


@dataclass(frozen=True)
class ToolRun:
    """A run in progress. total == 0 means the run has no count."""

    label: str
    done: int = 0
    total: int = 0
    cancelling: bool = False


@dataclass(frozen=True)
class ReferenceFacts:
    pdf: PickedFile | None = None
    csv: PickedFile | None = None
    folder: str = ""  # the output folder's full path; "" with no session
    open_pdf: bool = True
    run: ToolRun | None = None
    result: dict | None = None  # process_reference_labels' result for these inputs
    has_output: bool = False  # a processed PDF Print can send


@dataclass(frozen=True)
class PackingList:
    name: str
    count: int | None  # Fulfillable orders; None when the file can't be read
    has_labels: bool = False  # its barcode PDF is on disk
    has_qr: bool = False  # its QR PDF is on disk


@dataclass(frozen=True)
class BarcodeFacts:
    lists: tuple[PackingList, ...] = ()
    loading: bool = False
    analysed: bool = True  # the window holds analysis data
    selected: str = ""  # a list's name
    folder: str = ""  # the selected list's label folder; "" with none
    qr: bool = False
    open_pdf: bool = True
    run: ToolRun | None = None
    result: dict | None = None  # generate_list_labels' result


@dataclass(frozen=True)
class PrintFacts:
    settings: dict  # gui.pdf_printing.load_print_settings(scope)
    printers: tuple[str, ...] = ()  # installed printer names


def short_path(path: str) -> str:
    """A path's last two parts behind an ellipsis: "…\\2026-09-30_1\\barcodes"."""
    parts = [part for part in re.split(r"[\\/]+", str(path)) if part]
    return "…" + os.sep + os.sep.join(parts[-2:])


def _count(value: int, noun: str) -> str:
    return f"{value:,} {noun}{'' if value == 1 else 's'}"


def _row(pick: PickedFile | None, noun: str) -> dict:
    if pick is None:
        return {}
    if pick.problem is not None:
        title, text = pick.problem
        return {"name": pick.name, "meta": "Problem", "problem": {"title": title, "text": text}}
    return {"name": pick.name, "meta": _count(pick.count or 0, noun), "problem": {}}


def _folder(path: str, empty: str) -> dict:
    if not path:
        return {"text": empty, "title": "", "muted": True}
    return {"text": short_path(path), "title": path, "muted": False}


def _run(run: ToolRun | None) -> dict:
    """The running footer, worded. {} when idle."""
    if run is None:
        return {}
    if run.total <= 0:
        # Barcode: one render call, so a sentence and nothing to cancel.
        return {"label": run.label, "count": "", "bar": False, "percent": 0, "cancel": {}}
    saving = run.label == SAVING
    # One bar across both counted phases, so it never goes back.
    steps = {READING: run.done, STAMPING: run.total + run.done}.get(run.label, 2 * run.total)
    return {
        "label": "Saving…" if saving else run.label,
        "count": "" if saving else f"{run.done:,} of {run.total:,}",
        "bar": True,
        "percent": min(100, steps * 100 // (2 * run.total)),
        "cancel": {
            "label": "Cancelling…" if run.cancelling else "Cancel",
            "enabled": not saving and not run.cancelling,
            "title": "Saving can't be cancelled" if saving else "",
        },
    }


def _print_block(facts: PrintFacts, noun: str, size_hint: str) -> dict:
    settings = facts.settings
    mode = settings.get("print_mode")
    if mode not in MODES:
        mode = "driver"
    installed = list(facts.printers)

    if mode == "raw_zpl":
        current = str(settings.get("raw_zpl_target") or "").strip()
        options = [(name, name) for name in installed]
        printer = {
            "value": current,
            "label": current or "Choose a printer",
            "placeholder": not current,
        }
        if current:
            help_text, tone = (
                f"Sends {noun} straight to the label printer as ZPL, no dialog. "
                "Saved for this PC."
            ), ""
        else:
            help_text, tone = "Raw ZPL needs a printer. Choose the one the labels go to.", "danger"
        width = float(settings.get("raw_zpl_label_width_mm") or 0.0)
        height = float(settings.get("raw_zpl_label_height_mm") or 0.0)
        turned = bool(settings.get("raw_zpl_rotate"))
        inverted = bool(settings.get("raw_zpl_invert"))
        summary = f"{width:g} × {height:g} mm" if width > 0 and height > 0 else "the PDF's page size"
        if turned:
            summary += ", rotated 90°"
        if inverted:
            summary += ", colours inverted"
        setup = {
            "summary": summary,
            "target": current,
            "width": width,
            "height": height,
            "rotate": turned,
            "invert": inverted,
            "size_hint": size_hint,
        }
    else:
        current = str(settings.get("driver_printer_name") or "")
        options = [("", "Windows default")] + [(name, name) for name in installed]
        printer = {
            "value": current,
            "label": current or "Windows default",
            "placeholder": False,
        }
        help_text, tone = (
            f"Prints {noun} through the Windows print dialog. Saved for this PC."
        ), ""
        setup = {}

    # A saved printer this PC no longer lists is still the one in use.
    if current and current not in installed:
        options.append((current, current))
    return {
        "mode": mode,
        "printer": printer,
        "printers": [
            {"value": value, "label": label, "checked": value == current}
            for value, label in options
        ],
        "help": help_text,
        "help_tone": tone,
        "setup": setup,
    }


def _print_button(block: dict, *, base: str, has_pdf: bool, live: bool, missing: str) -> dict:
    """A print button: what it says, why, and whether it can be pressed."""
    zpl = block["mode"] == "raw_zpl"
    target = block["printer"]["value"] if zpl else ""
    if not has_pdf:
        title = missing
    elif zpl and not target:
        title = "Choose a printer under Print mode"
    elif zpl:
        title = f"Send to {target}"
    else:
        title = "Open the print dialog"
    return {
        "label": base if zpl else f"{base}…",
        "title": title,
        "enabled": has_pdf and live and (not zpl or bool(target)),
    }


def _matched(result: dict) -> str:
    pages = result.get("pages_processed", 0)
    matched = result.get("matched", 0)
    unmatched = result.get("unmatched", 0)
    by_name = result.get("name_matched", 0)
    text = f"{matched:,} of {pages:,} labels matched"
    if unmatched:
        text += f", {unmatched:,} unmatched"
    text += "."
    if by_name:
        text += f" {by_name:,} matched by name only."
    return text


def _reference(facts: ReferenceFacts, prints: PrintFacts, quiet: bool) -> dict:
    locked = facts.run is not None
    pdf_bad = facts.pdf is not None and facts.pdf.problem is not None
    csv_bad = facts.csv is not None and facts.csv.problem is not None
    pdf_ok = facts.pdf is not None and not pdf_bad
    csv_ok = facts.csv is not None and not csv_bad

    reason, tone = "", ""
    if quiet or locked:
        pass
    elif pdf_bad:
        reason, tone = "Fix the labels PDF to process.", "danger"
    elif csv_bad:
        reason, tone = "Fix the mapping CSV to process.", "danger"
    elif facts.pdf is None and facts.csv is None:
        reason = "Choose the labels PDF and mapping CSV."
    elif facts.pdf is None:
        reason = "Choose the labels PDF."
    elif facts.csv is None:
        reason = "Choose the mapping CSV."
    elif facts.result is not None:
        warning = reference_run_warning(facts.result)
        if warning:
            reason, tone = warning, "warning"
        else:
            reason = _matched(facts.result)
    else:
        reason = (
            f"{_count(facts.pdf.count or 0, 'page')}, "
            f"{_count(facts.csv.count or 0, 'CSV row')}."
        )

    block = _print_block(prints, "stamped labels", REFERENCE_SIZE_HINT)
    return {
        "quiet": quiet,
        "locked": locked,
        "pdf": _row(facts.pdf, "page"),
        "csv": _row(facts.csv, "row"),
        "folder": _folder("" if quiet else facts.folder, "Session folder"),
        "open_pdf": facts.open_pdf,
        "print": block,
        "run": _run(facts.run),
        "reason": reason,
        "tone": tone,
        "can_run": not quiet and not locked and pdf_ok and csv_ok and bool(facts.folder),
        "print_button": _print_button(
            block,
            base="Print",
            has_pdf=facts.has_output,
            live=not quiet and not locked,
            missing="Process labels first",
        ),
    }


def _barcode(facts: BarcodeFacts, prints: PrintFacts, quiet: bool) -> dict:
    locked = facts.run is not None
    lists = () if quiet else facts.lists
    cur = next((entry for entry in lists if entry.name == facts.selected), None)
    waiting = facts.loading and not lists
    folder = facts.folder if cur is not None else ""
    result = facts.result if cur is not None and facts.result is not None else None
    if result is not None and result.get("list") != cur.name:
        result = None

    if cur is not None:
        meta = "Unreadable" if cur.count is None else f"{cur.count:,} Fulfillable"
        shown = {"name": cur.name, "meta": meta, "placeholder": ""}
    elif waiting and not quiet:
        shown = {"name": "", "meta": "", "placeholder": "Reading packing lists…"}
    elif lists:
        shown = {"name": "", "meta": "", "placeholder": "Choose a packing list"}
    else:
        shown = {"name": "", "meta": "", "placeholder": "No packing lists"}

    reason, tone = "", ""
    if quiet or locked:
        pass
    elif waiting:
        reason = "Reading packing lists…"
    elif not lists:
        reason = "No packing lists in this session yet. Generate one on Results, then Refresh."
    elif not facts.analysed:
        reason = "This session has no analysis loaded. Run it on Setup."
    elif cur is None:
        reason = "Choose a packing list."
    elif cur.count is None:
        reason, tone = "This packing list couldn't be read. Details are in Logs.", "danger"
    elif cur.count == 0:
        reason = "No Fulfillable orders in this list."
    elif result is not None and result.get("failed"):
        reason, tone = (
            f"{_count(result.get('labels', 0), 'label')} written, "
            f"{_count(result['failed'], 'order number')} couldn't be encoded. "
            "Details are in Logs."
        ), "warning"
    elif result is not None and result.get("qr_failed"):
        reason, tone = (
            "Barcode labels written. The QR labels failed; details are in Logs."
        ), "warning"
    elif cur.has_labels:
        reason = f"Generating again replaces the labels in {short_path(folder)}."
    else:
        reason = f"Saves to {short_path(folder)}" + (", with QR labels." if facts.qr else ".")

    block = _print_block(prints, "barcode labels", BARCODE_SIZE_HINT)
    live = not quiet and not locked
    qr_button = {}
    if cur is not None and (facts.qr or cur.has_qr):
        qr_button = _print_button(
            block,
            base="Print QR labels",
            has_pdf=cur.has_qr,
            live=live,
            missing="Generate with QR labels ticked first",
        )
    empty = "Session folder" if quiet else "Choose a packing list"
    return {
        "quiet": quiet,
        "locked": locked,
        "list": shown,
        "lists": [
            {
                "name": entry.name,
                "meta": "—" if entry.count is None else f"{entry.count:,}",
                "checked": entry.name == facts.selected,
            }
            for entry in lists
        ],
        "folder": _folder(folder, empty),
        "qr": facts.qr,
        "open_pdf": facts.open_pdf,
        "print": block,
        "run": _run(facts.run),
        "reason": reason,
        "tone": tone,
        "can_run": live and facts.analysed and cur is not None and bool(cur.count),
        "print_button": _print_button(
            block,
            base="Print",
            has_pdf=cur is not None and cur.has_labels,
            live=live,
            missing="Generate this list's labels first",
        ),
        "qr_button": qr_button,
    }


def tools_state(
    *,
    client: str,
    session: SessionFacts | None,
    reference: ReferenceFacts,
    reference_print: PrintFacts,
    barcode: BarcodeFacts,
    barcode_print: PrintFacts,
    now: datetime,
) -> dict:
    """The one map the Tools page draws. Spec section 4.2."""
    quiet = session is None
    return {
        "session": (
            {} if quiet else {"name": session.name, "meta": session_meta(client, session, now)}
        ),
        "banner": quiet,
        "reference": _reference(reference, reference_print, quiet),
        "barcode": _barcode(barcode, barcode_print, quiet),
    }


def apply_print_edit(settings: dict, key: str, value) -> dict | None:
    """One print setting changed from the page (spec section 4.5).

    Returns the new settings, or None for an edit that is not one of the
    page's: the page is not trusted with a key or a type it was not given.
    """
    out = dict(settings)
    if key == "mode":
        if value not in MODES:
            return None
        out["print_mode"] = value
    elif key == "printer":
        if not isinstance(value, str):
            return None
        zpl = settings.get("print_mode") == "raw_zpl"
        out["raw_zpl_target" if zpl else "driver_printer_name"] = value
    elif key == "target":
        if not isinstance(value, str):
            return None
        out["raw_zpl_target"] = value.strip()
    elif key in ("width", "height"):
        # bool is an int in Python; the page never sends one for a size.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        if math.isnan(value):
            return None
        out[f"raw_zpl_label_{key}_mm"] = round(min(500.0, max(0.0, float(value))), 1)
    elif key in ("rotate", "invert"):
        if not isinstance(value, bool):
            return None
        out[f"raw_zpl_{key}"] = value
    else:
        return None
    return out
````

- [ ] **Step 5: Run the tests and see them pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_tools_state.py tests/test_setup_state.py tests/test_setup_page.py`
Expected: all pass (158 passed). `test_setup_state.py` and `test_setup_page.py` prove the extraction changed
nothing on Setup.

- [ ] **Step 6: Lint**

Run: `.venv/bin/ruff check gui/tools_state.py gui/setup_state.py tests/test_tools_state.py`
Expected: `All checks passed!`

- [ ] **Step 7: Commit**

Message: `Tools state: everything the Tools page draws, built in one place (phase 5 spec 4)`.
Add `gui/tools_state.py`, `gui/setup_state.py` and `tests/test_tools_state.py`.

---

### Task 4: The bridge (`gui/tools_bridge.py`)

**Files:**
- Create: `gui/tools_bridge.py`
- Test: `tests/test_tools_bridge.py` (new)

**Interfaces:**
- Consumes: `gui.web_page.PageBridge` (`themeCss`, `toastRaised(str, bool)`, `raise_toast(message,
  undoable=False)`), `gui.web_page.mount_page(view, bridge, page, channel_name)`, `gui.web_page.WEB_DIR`.
- Produces:
  - `ToolsBridge(PageBridge)` with the `state` Property, `set_state(dict)`, and the slots and signals of spec
    §3.2: `chooseFile(kind)` → `fileRequested(str)`; `clearFile(kind)` → `clearRequested(str)`;
    `changeFolder()` → `folderRequested()`; `setOption(tool, name, on)` → `optionChanged(str, str, bool)`;
    `setPrint(tool, key, value)` → `printChanged(str, str, object)`; `chooseList(name)` → `listChosen(str)`;
    `refreshLists()` → `listsRequested()`; `run(tool)` → `runRequested(str)`; `cancel()` →
    `cancelRequested()`; `printLabels(tool, what)` → `printRequested(str, str)`; `openFolder()` →
    `folderOpenRequested()`; `newSession()` → `newSessionRequested()`; `openRecent()` → `recentRequested()`.
  - `mount_tools_page(view) -> ToolsBridge`, `PAGE` (the path of `tools.html`), `CHANNEL_NAME = "tools"`,
    `TOOLS = ("reference", "barcode")`.

`mount_tools_page` reads `gui/web/tools.html`, which Task 6 creates. Nothing calls it before Task 6, so this
task's tests do not need the page.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tools_bridge.py`:

````python
"""The Tools page's bridge: every message is its own named member (phase 5 spec 3.2)."""

import pytest
from PySide6.QtWidgets import QApplication

from gui.tools_bridge import ToolsBridge
from gui.web_page import PageBridge


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


def _caught(signal):
    seen = []
    signal.connect(lambda *args: seen.append(args))
    return seen


def test_it_is_a_page_bridge():
    assert issubclass(ToolsBridge, PageBridge)


@pytest.mark.parametrize(
    ("slot", "signal"),
    [("chooseFile", "fileRequested"), ("clearFile", "clearRequested")],
)
def test_a_file_slot_carries_its_kind_and_drops_an_unknown_one(slot, signal):
    bridge = ToolsBridge()
    seen = _caught(getattr(bridge, signal))
    getattr(bridge, slot)("pdf")
    getattr(bridge, slot)("csv")
    getattr(bridge, slot)("xlsx")
    assert seen == [("pdf",), ("csv",)]


@pytest.mark.parametrize(
    ("slot", "signal"),
    [
        ("changeFolder", "folderRequested"),
        ("refreshLists", "listsRequested"),
        ("cancel", "cancelRequested"),
        ("openFolder", "folderOpenRequested"),
        ("newSession", "newSessionRequested"),
        ("openRecent", "recentRequested"),
    ],
)
def test_a_plain_request_emits_its_signal(slot, signal):
    bridge = ToolsBridge()
    seen = _caught(getattr(bridge, signal))
    getattr(bridge, slot)()
    assert seen == [()]


def test_an_option_is_one_of_three_pairs():
    bridge = ToolsBridge()
    seen = _caught(bridge.optionChanged)
    bridge.setOption("reference", "open_pdf", False)
    bridge.setOption("barcode", "open_pdf", True)
    bridge.setOption("barcode", "qr", True)
    bridge.setOption("reference", "qr", True)
    bridge.setOption("labels", "open_pdf", True)
    bridge.setOption("barcode", "locked", True)
    assert seen == [
        ("reference", "open_pdf", False),
        ("barcode", "open_pdf", True),
        ("barcode", "qr", True),
    ]


def test_a_print_edit_carries_its_value_as_it_came():
    bridge = ToolsBridge()
    seen = _caught(bridge.printChanged)
    bridge.setPrint("reference", "mode", "raw_zpl")
    bridge.setPrint("barcode", "width", 68.5)
    bridge.setPrint("barcode", "rotate", True)
    assert seen == [
        ("reference", "mode", "raw_zpl"),
        ("barcode", "width", 68.5),
        ("barcode", "rotate", True),
    ]


def test_a_print_edit_for_an_unknown_tool_or_key_is_dropped():
    bridge = ToolsBridge()
    seen = _caught(bridge.printChanged)
    bridge.setPrint("labels", "mode", "driver")
    bridge.setPrint("reference", "print_mode", "driver")
    bridge.setPrint("reference", "raw_zpl_target", "x")
    assert seen == []


def test_a_packing_list_is_named_and_an_empty_name_is_dropped():
    bridge = ToolsBridge()
    seen = _caught(bridge.listChosen)
    bridge.chooseList("DHL")
    bridge.chooseList("")
    assert seen == [("DHL",)]


def test_run_names_a_tool():
    bridge = ToolsBridge()
    seen = _caught(bridge.runRequested)
    bridge.run("reference")
    bridge.run("barcode")
    bridge.run("everything")
    assert seen == [("reference",), ("barcode",)]


def test_print_names_a_tool_and_what_to_print():
    bridge = ToolsBridge()
    seen = _caught(bridge.printRequested)
    bridge.printLabels("reference", "labels")
    bridge.printLabels("barcode", "labels")
    bridge.printLabels("barcode", "qr")
    bridge.printLabels("reference", "qr")
    bridge.printLabels("barcode", "invoices")
    assert seen == [("reference", "labels"), ("barcode", "labels"), ("barcode", "qr")]


def test_set_state_announces_a_change_once_and_never_the_same_state_twice():
    bridge = ToolsBridge()
    seen = _caught(bridge.stateChanged)
    bridge.set_state({"banner": True})
    bridge.set_state({"banner": True})
    bridge.set_state({"banner": False})
    assert len(seen) == 2
    assert bridge.state == {"banner": False}
````

- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_tools_bridge.py`
Expected: an error while collecting: `ModuleNotFoundError: No module named 'gui.tools_bridge'`.

- [ ] **Step 3: Implement**

Create `gui/tools_bridge.py`:

````python
"""The Tools page's bridge (phase 5 spec section 3.2).

Python pushes one `state` map, built by gui/tools_state.py; the page draws it
and reports what the operator asks for through the named slots below. The
catalogue is the spec's section 3.2: add a member there before adding it here.

The page names a tool, a packing list and a printer by name. Nothing it sends
is used as a path.
"""

from PySide6.QtCore import Property, Signal, Slot
from PySide6.QtWebEngineWidgets import QWebEngineView

from gui.web_page import WEB_DIR, PageBridge, mount_page

PAGE = WEB_DIR / "tools.html"
CHANNEL_NAME = "tools"
TOOLS = ("reference", "barcode")
KINDS = ("pdf", "csv")
OPTIONS = (("reference", "open_pdf"), ("barcode", "open_pdf"), ("barcode", "qr"))
PRINT_KEYS = ("mode", "printer", "target", "width", "height", "rotate", "invert")
PRINTABLE = (("reference", "labels"), ("barcode", "labels"), ("barcode", "qr"))


class ToolsBridge(PageBridge):
    """The Tools page's one channel object."""

    stateChanged = Signal()
    # Python-facing. JS reports through the slots below and never connects to
    # these, so nothing it sends can echo back into the page.
    fileRequested = Signal(str)
    clearRequested = Signal(str)
    folderRequested = Signal()
    optionChanged = Signal(str, str, bool)
    printChanged = Signal(str, str, object)
    listChosen = Signal(str)
    listsRequested = Signal()
    runRequested = Signal(str)
    cancelRequested = Signal()
    printRequested = Signal(str, str)
    folderOpenRequested = Signal()
    newSessionRequested = Signal()
    recentRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state: dict = {}

    # --- out: Python -> JS -------------------------------------------------

    def _get_state(self) -> dict:
        return self._state

    state = Property("QVariantMap", _get_state, notify=stateChanged)

    def set_state(self, state: dict) -> None:
        if state == self._state:
            return
        self._state = state
        self.stateChanged.emit()

    # --- in: JS -> Python --------------------------------------------------

    @Slot(str)
    def chooseFile(self, kind) -> None:
        if kind in KINDS:
            self.fileRequested.emit(kind)

    @Slot(str)
    def clearFile(self, kind) -> None:
        if kind in KINDS:
            self.clearRequested.emit(kind)

    @Slot()
    def changeFolder(self) -> None:
        self.folderRequested.emit()

    @Slot(str, str, bool)
    def setOption(self, tool, name, on) -> None:
        if (tool, name) in OPTIONS:
            self.optionChanged.emit(tool, name, bool(on))

    @Slot(str, str, "QVariant")
    def setPrint(self, tool, key, value) -> None:
        # The value is checked where it is applied (tools_state.apply_print_edit).
        if tool in TOOLS and key in PRINT_KEYS:
            self.printChanged.emit(tool, key, value)

    @Slot(str)
    def chooseList(self, name) -> None:
        if isinstance(name, str) and name:
            self.listChosen.emit(name)

    @Slot()
    def refreshLists(self) -> None:
        self.listsRequested.emit()

    @Slot(str)
    def run(self, tool) -> None:
        if tool in TOOLS:
            self.runRequested.emit(tool)

    @Slot()
    def cancel(self) -> None:
        self.cancelRequested.emit()

    @Slot(str, str)
    def printLabels(self, tool, what) -> None:
        if (tool, what) in PRINTABLE:
            self.printRequested.emit(tool, what)

    @Slot()
    def openFolder(self) -> None:
        self.folderOpenRequested.emit()

    @Slot()
    def newSession(self) -> None:
        self.newSessionRequested.emit()

    @Slot()
    def openRecent(self) -> None:
        self.recentRequested.emit()


def mount_tools_page(view: QWebEngineView) -> ToolsBridge:
    """Load the Tools page into `view` and return the bridge it talks to."""
    bridge = ToolsBridge(view)
    mount_page(view, bridge, PAGE, CHANNEL_NAME)
    return bridge
````

- [ ] **Step 4: Run the tests and see them pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_tools_bridge.py`
Expected: all pass (16 passed).

- [ ] **Step 5: Lint**

Run: `.venv/bin/ruff check gui/tools_bridge.py tests/test_tools_bridge.py`
Expected: `All checks passed!`

- [ ] **Step 6: Commit**

Message: `Tools bridge: the page's one channel object (phase 5 spec 3.2)`.
Add `gui/tools_bridge.py` and `tests/test_tools_bridge.py`.

---

### Task 5: The kit: a select, and disabled segment and field (`gui/web/kit.css`)

**Files:**
- Modify: `gui/web/kit.css`
- Modify: `tests/web/kit_sheet.html`
- Test: `tests/test_web_kit.py` (append)

**Interfaces:**
- Consumes: the kit's `.menu-anchor`, `.menu`, `.menu-item`, `.check`, `.glyph`, `.segmented`, `.segment`,
  `.field`.
- Produces (CSS classes the page in Task 6 uses): `.select` (a `<button>`), `.select-value`,
  `.select-value.placeholder`, `.select-meta`; the states `.select[aria-expanded="true"]`, `.select:disabled`,
  `.segment:disabled`, `.field:disabled`.

- [ ] **Step 1: Add the new components to the kit sheet**

In `tests/web/kit_sheet.html`:

**Edit 1 of 1** (near line 157). Find exactly:

````html
    </div>
  </section>
</main>
<script>document.getElementById("c-mixed").indeterminate = true;</script>
````

Replace with:

````html
    </div>
  </section>
  <section class="card" style="grid-column: 1 / -1">
    <h2>Select, and disabled segment and field</h2>
    <div class="row">
      <button id="sel-value" class="select" type="button" aria-haspopup="menu" aria-expanded="false" style="width: 260px"><span class="select-value">DHL</span><span class="select-meta">120 Fulfillable</span><svg class="glyph" viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg></button>
      <button id="sel-empty" class="select" type="button" aria-haspopup="menu" aria-expanded="false" style="width: 200px"><span id="sel-placeholder" class="select-value placeholder">Choose a printer</span><svg class="glyph" viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg></button>
      <button id="sel-open" class="select" type="button" aria-haspopup="menu" aria-expanded="true" style="width: 200px"><span class="select-value">Zebra ZD421</span><svg class="glyph" viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg></button>
      <button id="sel-disabled" class="select" type="button" aria-haspopup="menu" aria-expanded="false" style="width: 200px" disabled><span id="sel-disabled-value" class="select-value placeholder">No packing lists</span><svg class="glyph" viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg></button>
    </div>
    <div class="row">
      <div class="segmented" role="radiogroup" aria-label="Print mode">
        <button id="s-locked-on" class="segment" type="button" role="radio" aria-checked="true" disabled>Driver</button>
        <button id="s-locked-off" class="segment" type="button" role="radio" aria-checked="false" disabled>Raw ZPL</button>
      </div>
      <input id="i-field-disabled" class="field" type="text" value="68" disabled>
    </div>
  </section>
</main>
<script>document.getElementById("c-mixed").indeterminate = true;</script>
````

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_web_kit.py`:

````python
@THEMES
def test_a_select_shows_its_value_and_wears_its_states(qtbot, theme):
    """Phase 5 spec section 5.8."""
    view = _sheet(qtbot, theme)
    assert _style(qtbot, view, "#sel-value", "borderTopColor") == _rgb(theme.border)
    assert _style(qtbot, view, "#sel-value", "backgroundColor") == _rgb(theme.surface)
    assert _style(qtbot, view, "#sel-value .select-value", "fontWeight") == "700"
    assert _style(qtbot, view, "#sel-value .select-meta", "color") == _rgb(
        theme.text_secondary
    )
    assert _style(qtbot, view, "#sel-placeholder", "color") == _rgb(theme.text_placeholder)
    assert _style(qtbot, view, "#sel-placeholder", "fontWeight") == "400"
    assert _style(qtbot, view, "#sel-open", "borderTopColor") == _rgb(theme.text)


@THEMES
def test_a_disabled_select_is_dashed_and_quiet(qtbot, theme):
    view = _sheet(qtbot, theme)
    assert _style(qtbot, view, "#sel-disabled", "borderTopStyle") == "dashed"
    assert _style(qtbot, view, "#sel-disabled", "backgroundColor") == _rgb(
        theme.control_disabled_bg
    )
    assert _style(qtbot, view, "#sel-disabled-value", "color") == _rgb(theme.text_disabled)
    assert _style(qtbot, view, "#sel-disabled .glyph", "color") == _rgb(theme.text_disabled)


@THEMES
def test_a_disabled_segment_and_field_go_quiet(qtbot, theme):
    view = _sheet(qtbot, theme)
    assert _style(qtbot, view, "#s-locked-off", "color") == _rgb(theme.text_disabled)
    # The chosen one still reads: the operator must see which mode is set.
    assert _style(qtbot, view, "#s-locked-on", "color") == _rgb(theme.text)
    assert _style(qtbot, view, "#i-field-disabled", "borderTopStyle") == "dashed"
    assert _style(qtbot, view, "#i-field-disabled", "backgroundColor") == _rgb(
        theme.control_disabled_bg
    )
    assert _style(qtbot, view, "#i-field-disabled", "color") == _rgb(theme.text_disabled)
````

- [ ] **Step 3: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_web_kit.py`
Expected: the three new tests fail in both themes (six failures), on the first assertion each: the select has
no kit rule yet, so its edge is the browser's default. Every older test passes.

- [ ] **Step 4: Implement**

In `gui/web/kit.css`:

**Edit 1 of 1** (near line 571). Find exactly:

````css
.form-label { padding-top: 2px; font-weight: 700; }

/* --- focus --------------------------------------------------------------- */

.btn:focus-visible,
.switch:focus-visible,
.radio-card:focus-visible,
````

Replace with:

````css
.form-label { padding-top: 2px; font-weight: 700; }

/* --- select -------------------------------------------------------------- */

/* A button that shows a value and opens a .menu beside it (phase 5). The
   value and an optional mono meta, then a chevron glyph. */
.select {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  height: var(--control-height);
  padding: 0 8px 0 10px;
  border: 1px solid var(--border);
  border-radius: var(--kit-radius);
  background: var(--surface);
  text-align: left;
  cursor: pointer;
}
.select > .glyph { color: var(--text-secondary); }
.select-value {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  font-weight: 700;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.select-value.placeholder { font-weight: 400; color: var(--text-placeholder); }
.select-meta {
  font-family: var(--font-family-mono);
  font-size: var(--type-caption-size);
  color: var(--text-secondary);
  white-space: nowrap;
}
.select[aria-expanded="true"] { border-color: var(--text); }
.select:disabled {
  border: 1px dashed var(--border);
  background: var(--control-disabled-bg);
  cursor: not-allowed;
}
.select:disabled .select-value,
.select:disabled .select-meta,
.select:disabled > .glyph { color: var(--text-disabled); }

/* --- disabled segment and field ------------------------------------------ */

.segment:disabled { cursor: default; }
.segment:disabled:not([aria-checked="true"]) { color: var(--text-disabled); }

.field:disabled {
  border: 1px dashed var(--border);
  background: var(--control-disabled-bg);
  color: var(--text-disabled);
  cursor: not-allowed;
}

/* --- focus --------------------------------------------------------------- */

.btn:focus-visible,
.select:focus-visible,
.switch:focus-visible,
.radio-card:focus-visible,
````

- [ ] **Step 5: Run the tests and see them pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_web_kit.py tests/test_style_literals_guard.py`
Expected: all pass (39 passed).

- [ ] **Step 6: Commit**

Message: `Web kit: a select, and disabled segment and field (phase 5 spec 5.8)`.
Add `gui/web/kit.css`, `tests/web/kit_sheet.html` and `tests/test_web_kit.py`.

---

### Task 6: The page (`gui/web/tools.html`, `tools.css`, `tools.js`)

**Files:**
- Create: `gui/web/tools.html`, `gui/web/tools.css`, `gui/web/tools.js`
- Test: `tests/test_tools_page.py` (replace the whole file)

**Interfaces:**
- Consumes: `mount_tools_page(view)` and `PAGE` (Task 4); the state of Task 3 (spec §4.2); the kit of Task 5;
  from `tests/test_tools_state.py`: `make_state`, `reference`, `barcode`, `DRIVER`, `ZPL`, `PRINTERS`,
  `BAD_CSV`; from `tests/test_results_bridge.py`: `_eval`, `_rgb`, `_until_js`.
- Produces: the page. It sets `document.documentElement.dataset.bridge = "ready"` once the channel is up and
  increments `document.documentElement.dataset.renders` on every draw. Every control carries a `data-key`:
  `new-session`, `open-recent`, `pdf-choose`, `pdf-clear`, `pdf-again`, `csv-choose`, `csv-clear`,
  `csv-again`, `reference-folder`, `reference-open_pdf`, `barcode-list`, `barcode-list-item-N`,
  `barcode-refresh`, `barcode-qr`, `barcode-open_pdf`, and per tool `T`: `T-mode-driver`, `T-mode-raw_zpl`,
  `T-printer`, `T-printer-item-N`, `T-fold`, `T-target`, `T-width`, `T-height`, `T-rotate`, `T-invert`,
  `T-print-labels`, `T-run`, `T-cancel`; also `barcode-print-qr`. The toast is `#toast`, `#toast-text`,
  `#toast-action`, `#toast-dismiss`.

`tests/test_tools_page.py` exists today and tests the Qt page. This task replaces its content; the Qt page it
tested stays in place until Task 9, covered until then by `test_tools_cards.py` and `test_tools_theme.py`.

- [ ] **Step 1: Write the failing tests**

Replace the whole of `tests/test_tools_page.py` with:

````python
"""The Tools page, driven through a real Chromium (phase 5 spec section 5).

The page is a renderer: every test pushes a state built by tools_state() and
reads the DOM back. 1166x720 is the page a 1366x768 window gives. Never mark
skip.
"""

import json

import pytest
from PySide6.QtWebEngineWidgets import QWebEngineView
from test_results_bridge import _eval, _rgb, _until_js
from test_tools_state import (
    BAD_CSV,
    DRIVER,
    PRINTERS,
    ZPL,
    barcode,
    make_state,
    reference,
)

from gui.theme_manager import get_theme_manager
from gui.tools_bridge import PAGE, mount_tools_page
from gui.tools_state import (
    BarcodeFacts,
    PackingList,
    PrintFacts,
    ReferenceFacts,
    ToolRun,
)
from gui.web_page import THEME_MARKER
from shopify_tool.pdf_processor import SAVING, STAMPING


@pytest.fixture
def page(qtbot):
    view = QWebEngineView()
    qtbot.addWidget(view)
    bridge = mount_tools_page(view)
    view.resize(1166, 720)
    view.show()
    _until_js(qtbot, view, "document.documentElement.dataset.bridge === 'ready'")
    return view, bridge


def _renders(qtbot, view):
    return _eval(qtbot, view, "Number(document.documentElement.dataset.renders || 0)")


def _show(qtbot, view, bridge, state):
    """Push a state and wait for the page to have drawn it."""
    before = _renders(qtbot, view)
    bridge.set_state(state)
    _until_js(
        qtbot, view, f"Number(document.documentElement.dataset.renders) > {before}"
    )


def _text(qtbot, view, selector):
    return _eval(
        qtbot, view, f"document.querySelector({selector!r}).textContent.trim()"
    )


def _json(qtbot, view, expr):
    """A list or an object from the page: runJavaScript hands back only scalars."""
    return json.loads(_eval(qtbot, view, f"JSON.stringify({expr})"))


def _count(qtbot, view, selector):
    return _eval(qtbot, view, f"document.querySelectorAll({selector!r}).length")


def _click(qtbot, view, selector):
    _eval(qtbot, view, f"document.querySelector({selector!r}).click(); true")


def _style(qtbot, view, selector, prop):
    return _eval(
        qtbot, view, f"getComputedStyle(document.querySelector({selector!r})).{prop}"
    )


def _disabled(qtbot, view, selector):
    return _eval(qtbot, view, f"document.querySelector({selector!r}).disabled")


def _attr(qtbot, view, selector, name):
    return _eval(
        qtbot, view, f"document.querySelector({selector!r}).getAttribute({name!r})"
    )


def _change(qtbot, view, selector, value):
    """Type `value` into a field and commit it, as blur or Enter would."""
    _eval(
        qtbot,
        view,
        "(function () {"
        f" const el = document.querySelector({selector!r});"
        f" el.value = {json.dumps(value)};"
        " el.dispatchEvent(new Event('change', { bubbles: true }));"
        " return true; })()",
    )


def _caught(signal):
    seen = []
    signal.connect(lambda *args: seen.append(args))
    return seen


def _key(name):
    return f'[data-key="{name}"]'


REF = '[data-tool="reference"]'
BAR = '[data-tool="barcode"]'


# --- the files ----------------------------------------------------------------


def test_the_page_carries_the_theme_marker_exactly_once():
    assert PAGE.read_text(encoding="utf-8").count(THEME_MARKER) == 1


def test_the_page_links_the_kit_before_its_own_stylesheet():
    html = PAGE.read_text(encoding="utf-8")
    assert html.index('href="kit.css"') < html.index('href="tools.css"')


# --- frame --------------------------------------------------------------------


def test_with_a_session_the_head_shows_its_chip_and_there_is_no_banner(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    assert _text(qtbot, view, ".page-title") == "Tools"
    assert _text(qtbot, view, ".page-head .code") == "2026-09-30_1"
    assert _text(qtbot, view, ".page-meta") == "ACME · opened 14:02"
    assert _count(qtbot, view, "[data-banner]") == 0
    assert _count(qtbot, view, ".tool-card") == 2
    assert _text(qtbot, view, f"{REF} .tool-title") == "Reference labels"
    assert _text(qtbot, view, f"{BAR} .tool-title") == "Barcode labels"


def test_with_no_session_one_banner_explains_and_offers_the_two_ways_in(qtbot, page):
    view, bridge = page
    _show(
        qtbot,
        view,
        bridge,
        make_state(session=None, reference=ReferenceFacts(), barcode=BarcodeFacts()),
    )
    assert _count(qtbot, view, ".page-head .code") == 0
    assert _text(qtbot, view, "[data-banner] .banner-title") == (
        "Open a session to use these tools"
    )
    new, recent = _caught(bridge.newSessionRequested), _caught(bridge.recentRequested)
    _click(qtbot, view, _key("new-session"))
    _click(qtbot, view, _key("open-recent"))
    qtbot.waitUntil(lambda: new == [()] and recent == [()])


def test_with_no_session_the_fields_go_quiet_and_print_mode_stays_live(qtbot, page):
    view, bridge = page
    _show(
        qtbot,
        view,
        bridge,
        make_state(session=None, reference=ReferenceFacts(), barcode=BarcodeFacts()),
    )
    for key in (
        "pdf-choose",
        "csv-choose",
        "reference-folder",
        "reference-open_pdf",
        "barcode-list",
        "barcode-refresh",
        "barcode-qr",
        "barcode-open_pdf",
        "reference-run",
        "barcode-run",
        "reference-print-labels",
        "barcode-print-labels",
    ):
        assert _disabled(qtbot, view, _key(key)) is True, key
    for key in (
        "reference-mode-driver",
        "reference-mode-raw_zpl",
        "reference-printer",
        "barcode-printer",
        "barcode-fold",
    ):
        assert _disabled(qtbot, view, _key(key)) is False, key
    assert _text(qtbot, view, f"{REF} .path") == "Session folder"
    theme = get_theme_manager().get_current_theme()
    assert _style(qtbot, view, f"{REF} .path", "color") == _rgb(theme.text_disabled)
    assert _text(qtbot, view, f"{BAR} .select-value") == "No packing lists"
    assert _text(qtbot, view, f"{REF} .tool-reason") == ""


def test_the_cards_sit_side_by_side_and_stack_when_the_page_is_narrow(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    tops = "Array.from(document.querySelectorAll('.tool-card')).map(c => c.getBoundingClientRect().top)"
    lefts = "Array.from(document.querySelectorAll('.tool-card')).map(c => c.getBoundingClientRect().left)"
    top = _json(qtbot, view, tops)
    left = _json(qtbot, view, lefts)
    assert top[0] == top[1]
    assert left[0] < left[1]
    # Nothing is wider than the page.
    assert _eval(qtbot, view, "document.getElementById('tools').scrollWidth <= window.innerWidth")

    view.resize(800, 720)
    _until_js(
        qtbot,
        view,
        "(function () { const c = document.querySelectorAll('.tool-card');"
        " return c[0].getBoundingClientRect().top < c[1].getBoundingClientRect().top; })()",
    )
    left = _json(qtbot, view, lefts)
    assert left[0] == left[1]
    assert _eval(qtbot, view, "document.getElementById('tools').scrollWidth <= window.innerWidth")


def test_the_tool_card_row_is_the_kit_row_with_a_narrow_quiet_label(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    assert _style(qtbot, view, f"{REF} .form-row", "gridTemplateColumns").startswith("112px ")
    assert _style(qtbot, view, f"{REF} .form-label", "fontWeight") == "400"
    theme = get_theme_manager().get_current_theme()
    assert _style(qtbot, view, f"{REF} .form-label", "color") == _rgb(theme.text_secondary)


# --- reference labels ---------------------------------------------------------


def test_with_nothing_picked_each_file_row_offers_choose(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state(reference=reference(pdf=None, csv=None)))
    assert _text(qtbot, view, _key("pdf-choose")) == "Choose PDF…"
    assert _text(qtbot, view, _key("csv-choose")) == "Choose CSV…"
    seen = _caught(bridge.fileRequested)
    _click(qtbot, view, _key("pdf-choose"))
    _click(qtbot, view, _key("csv-choose"))
    qtbot.waitUntil(lambda: seen == [("pdf",), ("csv",)])


def test_a_picked_file_shows_its_name_and_count_and_can_be_replaced(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    assert _text(qtbot, view, '[data-row="pdf"] .file-name') == "dhl-labels-30-09.pdf"
    assert _text(qtbot, view, '[data-row="pdf"] .file-meta') == "120 pages"
    assert _text(qtbot, view, '[data-row="csv"] .file-meta') == "120 rows"
    assert _count(qtbot, view, f"{REF} .banner") == 0
    seen = _caught(bridge.clearRequested)
    _click(qtbot, view, _key("csv-clear"))
    qtbot.waitUntil(lambda: seen == [("csv",)])


def test_a_bad_csv_is_flagged_under_its_own_field(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state(reference=reference(csv=BAD_CSV)))
    theme = get_theme_manager().get_current_theme()
    assert _count(qtbot, view, '[data-row="csv"] .banner.danger') == 1
    assert _count(qtbot, view, '[data-row="pdf"] .banner') == 0
    assert _text(qtbot, view, '[data-row="csv"] .problem-title') == (
        "This CSV has no usable rows"
    )
    assert _text(qtbot, view, '[data-row="csv"] .file-meta') == "Problem"
    assert _style(qtbot, view, '[data-row="csv"] .file-meta', "color") == _rgb(
        theme.status_danger
    )
    assert _style(qtbot, view, '[data-row="csv"] .tool-line .glyph', "color") == _rgb(
        theme.status_danger
    )
    assert _text(qtbot, view, f"{REF} .tool-reason") == "Fix the mapping CSV to process."
    assert _style(qtbot, view, f"{REF} .tool-reason", "color") == _rgb(theme.status_danger)
    assert _disabled(qtbot, view, _key("reference-run")) is True
    # The card's own edge does not change (the mockup flags the field only).
    assert _style(qtbot, view, REF, "borderTopColor") != _rgb(theme.status_danger_border)
    seen = _caught(bridge.fileRequested)
    _click(qtbot, view, _key("csv-again"))
    qtbot.waitUntil(lambda: seen == [("csv",)])


def test_the_output_folder_row_and_its_checkbox(qtbot, page):
    view, bridge = page
    state = make_state()
    _show(qtbot, view, bridge, state)
    assert _text(qtbot, view, f"{REF} .path") == state["reference"]["folder"]["text"]
    assert _attr(qtbot, view, f"{REF} .path", "title") == state["reference"]["folder"]["title"]
    folder, option = _caught(bridge.folderRequested), _caught(bridge.optionChanged)
    _click(qtbot, view, _key("reference-folder"))
    _click(qtbot, view, _key("reference-open_pdf"))
    qtbot.waitUntil(lambda: folder == [()] and option == [("reference", "open_pdf", False)])


# --- barcode labels -----------------------------------------------------------


def test_the_packing_list_select_shows_the_list_and_its_count(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    assert _text(qtbot, view, f"{_key('barcode-list')} .select-value") == "DHL"
    assert _text(qtbot, view, f"{_key('barcode-list')} .select-meta") == "120 Fulfillable"
    assert _attr(qtbot, view, _key("barcode-list"), "aria-expanded") == "false"
    assert _count(qtbot, view, f"{BAR} .menu") == 0
    # Barcode's folder is read-only: no Change… on this card.
    assert _count(qtbot, view, f"{BAR} [data-act='folder']") == 0


def test_the_packing_list_menu_lists_every_list_and_a_choice_closes_it(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    _click(qtbot, view, _key("barcode-list"))
    assert _attr(qtbot, view, _key("barcode-list"), "aria-expanded") == "true"
    assert _text(qtbot, view, f"{BAR} .menu-group") == "Packing lists in 2026-09-30_1"
    rows = _json(
        qtbot,
        view,
        "Array.from(document.querySelectorAll('[data-act=\"list\"]')).map(i => "
        "[i.querySelector('.menu-label').textContent, i.querySelector('.menu-hint').textContent,"
        " i.getAttribute('aria-checked')])",
    )
    assert rows == [["DHL", "120", "true"], ["DPD", "48", "false"], ["Royal Mail", "31", "false"]]
    seen = _caught(bridge.listChosen)
    _click(qtbot, view, _key("barcode-list-item-2"))
    qtbot.waitUntil(lambda: seen == [("Royal Mail",)])
    assert _count(qtbot, view, f"{BAR} .menu") == 0
    assert _eval(qtbot, view, "document.activeElement.dataset.key") == "barcode-list"


def test_escape_and_an_outside_click_close_the_menu(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    _click(qtbot, view, _key("barcode-list"))
    assert _count(qtbot, view, f"{BAR} .menu") == 1
    _eval(
        qtbot,
        view,
        "document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true})); true",
    )
    assert _count(qtbot, view, f"{BAR} .menu") == 0
    assert _eval(qtbot, view, "document.activeElement.dataset.key") == "barcode-list"

    _click(qtbot, view, _key("barcode-list"))
    assert _count(qtbot, view, f"{BAR} .menu") == 1
    _click(qtbot, view, ".page-title")
    assert _count(qtbot, view, f"{BAR} .menu") == 0


def test_only_one_menu_is_open_at_a_time(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    _click(qtbot, view, _key("barcode-list"))
    _click(qtbot, view, _key("reference-printer"))
    assert _count(qtbot, view, ".menu") == 1
    assert _count(qtbot, view, f"{REF} .menu") == 1


def test_arrow_keys_walk_the_open_menu(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    _click(qtbot, view, _key("barcode-list"))
    down = "document.dispatchEvent(new KeyboardEvent('keydown', {key: 'ArrowDown', bubbles: true})); document.activeElement.dataset.key"
    up = "document.dispatchEvent(new KeyboardEvent('keydown', {key: 'ArrowUp', bubbles: true})); document.activeElement.dataset.key"
    assert _eval(qtbot, view, down) == "barcode-list-item-0"
    assert _eval(qtbot, view, down) == "barcode-list-item-1"
    assert _eval(qtbot, view, up) == "barcode-list-item-0"
    assert _eval(qtbot, view, up) == "barcode-list-item-2"


def test_a_state_push_leaves_an_open_menu_open(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    _click(qtbot, view, _key("barcode-list"))
    _show(qtbot, view, bridge, make_state(reference=reference(open_pdf=False)))
    assert _count(qtbot, view, f"{BAR} .menu") == 1


def test_a_menu_closes_when_its_card_locks(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    _click(qtbot, view, _key("barcode-list"))
    _show(
        qtbot,
        view,
        bridge,
        make_state(barcode=barcode(run=ToolRun("Writing 120 barcode labels…"))),
    )
    assert _count(qtbot, view, ".menu") == 0
    assert _disabled(qtbot, view, _key("barcode-list")) is True


def test_a_list_name_with_markup_is_drawn_as_text_and_sent_back_exactly(qtbot, page):
    view, bridge = page
    name = 'DHL "Express" <b>&co'
    lists = (PackingList(name, 3), PackingList("DPD", 48))
    _show(qtbot, view, bridge, make_state(barcode=barcode(lists=lists, selected=name)))
    assert _text(qtbot, view, f"{_key('barcode-list')} .select-value") == name
    assert _count(qtbot, view, f"{BAR} b") == 0
    _click(qtbot, view, _key("barcode-list"))
    seen = _caught(bridge.listChosen)
    _click(qtbot, view, _key("barcode-list-item-0"))
    qtbot.waitUntil(lambda: seen == [(name,)])


def test_with_no_lists_the_select_is_disabled_and_refresh_is_not(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state(barcode=barcode(lists=(), selected="", folder="")))
    assert _disabled(qtbot, view, _key("barcode-list")) is True
    assert _text(qtbot, view, f"{_key('barcode-list')} .select-value") == "No packing lists"
    theme = get_theme_manager().get_current_theme()
    assert _style(qtbot, view, f"{_key('barcode-list')} .select-value", "color") == _rgb(
        theme.text_disabled
    )
    seen = _caught(bridge.listsRequested)
    _click(qtbot, view, _key("barcode-refresh"))
    qtbot.waitUntil(lambda: seen == [()])


def test_the_barcode_checkboxes_report_their_option(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    seen = _caught(bridge.optionChanged)
    _click(qtbot, view, _key("barcode-qr"))
    _click(qtbot, view, _key("barcode-open_pdf"))
    qtbot.waitUntil(
        lambda: seen == [("barcode", "qr", True), ("barcode", "open_pdf", False)]
    )


def test_the_qr_print_button_appears_with_its_state(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    assert _count(qtbot, view, _key("barcode-print-qr")) == 0
    _show(qtbot, view, bridge, make_state(barcode=barcode(qr=True)))
    assert _text(qtbot, view, _key("barcode-print-qr")) == "Print QR labels"
    assert _disabled(qtbot, view, _key("barcode-print-qr")) is True
    assert _attr(qtbot, view, _key("barcode-print-qr"), "title") == (
        "Generate with QR labels ticked first"
    )


# --- print mode ---------------------------------------------------------------


def test_the_mode_switch_shows_and_reports_the_mode(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    assert _attr(qtbot, view, _key("reference-mode-driver"), "aria-checked") == "true"
    assert _attr(qtbot, view, _key("reference-mode-raw_zpl"), "aria-checked") == "false"
    assert _attr(qtbot, view, _key("barcode-mode-raw_zpl"), "aria-checked") == "true"
    seen = _caught(bridge.printChanged)
    _click(qtbot, view, _key("reference-mode-raw_zpl"))
    _click(qtbot, view, _key("barcode-mode-driver"))
    qtbot.waitUntil(
        lambda: seen == [("reference", "mode", "raw_zpl"), ("barcode", "mode", "driver")]
    )


def test_the_printer_menu_reports_a_printer_by_name(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    assert _text(qtbot, view, f"{_key('reference-printer')} .select-value") == "Windows default"
    assert _text(qtbot, view, f"{_key('barcode-printer')} .select-value") == "Zebra ZD421"
    _click(qtbot, view, _key("reference-printer"))
    labels = _json(
        qtbot,
        view,
        "Array.from(document.querySelectorAll('[data-act=\"printer\"] .menu-label')).map(e => e.textContent)",
    )
    assert labels == ["Windows default", "Zebra ZD421", "HP LaserJet"]
    seen = _caught(bridge.printChanged)
    _click(qtbot, view, _key("reference-printer-item-2"))
    qtbot.waitUntil(lambda: seen == [("reference", "printer", "HP LaserJet")])
    assert _count(qtbot, view, ".menu") == 0

    _click(qtbot, view, _key("reference-printer"))
    _click(qtbot, view, _key("reference-printer-item-0"))
    qtbot.waitUntil(lambda: seen[-1] == ("reference", "printer", ""))


def test_the_help_line_follows_the_mode_and_turns_danger_with_no_printer(qtbot, page):
    view, bridge = page
    theme = get_theme_manager().get_current_theme()
    _show(qtbot, view, bridge, make_state())
    assert _text(qtbot, view, f"{REF} .mode-help") == (
        "Prints stamped labels through the Windows print dialog. Saved for this PC."
    )
    assert _style(qtbot, view, f"{REF} .mode-help", "color") == _rgb(theme.text_secondary)
    no_target = PrintFacts({**ZPL, "raw_zpl_target": ""}, PRINTERS)
    _show(qtbot, view, bridge, make_state(barcode_print=no_target))
    assert _text(qtbot, view, f"{BAR} .mode-help") == (
        "Raw ZPL needs a printer. Choose the one the labels go to."
    )
    assert _style(qtbot, view, f"{BAR} .mode-help", "color") == _rgb(theme.status_danger)
    assert _text(qtbot, view, f"{_key('barcode-printer')} .select-value") == "Choose a printer"
    assert _style(qtbot, view, f"{_key('barcode-printer')} .select-value", "color") == _rgb(
        theme.text_placeholder
    )


def test_label_setup_shows_only_in_raw_zpl_and_folds(qtbot, page):
    view, bridge = page
    sized = PrintFacts(
        {**ZPL, "raw_zpl_label_width_mm": 68.0, "raw_zpl_label_height_mm": 38.0}, PRINTERS
    )
    _show(qtbot, view, bridge, make_state(barcode_print=sized))
    assert _count(qtbot, view, _key("reference-fold")) == 0  # Driver mode
    assert _text(qtbot, view, f"{_key('barcode-fold')} .fold-title") == "Label setup"
    assert _text(qtbot, view, f"{_key('barcode-fold')} .fold-summary") == "68 × 38 mm"
    assert _attr(qtbot, view, _key("barcode-fold"), "aria-expanded") == "false"
    assert _count(qtbot, view, ".fold-body") == 0

    _click(qtbot, view, _key("barcode-fold"))
    assert _attr(qtbot, view, _key("barcode-fold"), "aria-expanded") == "true"
    assert _eval(qtbot, view, f"document.querySelector({_key('barcode-target')!r}).value") == (
        "Zebra ZD421"
    )
    assert _eval(qtbot, view, f"document.querySelector({_key('barcode-width')!r}).value") == "68"
    assert _eval(qtbot, view, f"document.querySelector({_key('barcode-height')!r}).value") == "38"
    assert _attr(qtbot, view, _key("barcode-width"), "title").startswith("Physical label size")

    # A state push leaves it open.
    _show(qtbot, view, bridge, make_state(barcode_print=sized, reference=reference(csv=None)))
    assert _count(qtbot, view, ".fold-body") == 1

    _click(qtbot, view, _key("barcode-fold"))
    assert _count(qtbot, view, ".fold-body") == 0


def test_a_zero_label_size_shows_as_empty(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    _click(qtbot, view, _key("barcode-fold"))
    assert _eval(qtbot, view, f"document.querySelector({_key('barcode-width')!r}).value") == ""
    assert _attr(qtbot, view, _key("barcode-width"), "placeholder") == "PDF"


def test_each_label_setup_control_reports_a_typed_value(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    _click(qtbot, view, _key("barcode-fold"))
    seen = _caught(bridge.printChanged)

    _change(qtbot, view, _key("barcode-target"), r"\\printsrv\zebra-3")
    _change(qtbot, view, _key("barcode-width"), "68.5")
    _change(qtbot, view, _key("barcode-height"), "")
    _click(qtbot, view, _key("barcode-rotate"))
    _click(qtbot, view, _key("barcode-invert"))
    qtbot.waitUntil(lambda: len(seen) == 5)

    assert seen[0] == ("barcode", "target", r"\\printsrv\zebra-3")
    assert seen[1] == ("barcode", "width", 68.5)
    assert seen[2] == ("barcode", "height", 0)
    assert seen[3] == ("barcode", "rotate", True)
    assert seen[4] == ("barcode", "invert", True)
    # The types apply_print_edit checks: a number is never a bool, a bool never a number.
    assert isinstance(seen[0][2], str)
    assert not isinstance(seen[1][2], bool) and isinstance(seen[1][2], (int, float))
    assert not isinstance(seen[2][2], bool) and isinstance(seen[2][2], (int, float))
    assert seen[3][2] is True and seen[4][2] is True


def test_text_being_typed_survives_a_state_that_arrives_mid_edit(qtbot, page):
    """The other card's run pushes a state several times a second."""
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    _click(qtbot, view, _key("barcode-fold"))
    _eval(
        qtbot,
        view,
        f"(function () {{ const el = document.querySelector({_key('barcode-target')!r});"
        " el.focus(); el.value = 'Zebra ZD4'; return true; })()",
    )
    _show(qtbot, view, bridge, make_state(reference=reference(run=ToolRun(STAMPING, 1, 120))))
    assert _eval(qtbot, view, "document.activeElement.dataset.key") == "barcode-target"
    assert _eval(qtbot, view, "document.activeElement.value") == "Zebra ZD4"


# --- footer -------------------------------------------------------------------


def test_the_idle_footers_state_the_reason_and_offer_the_actions(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    assert _text(qtbot, view, f"{REF} .tool-reason") == "120 pages, 120 CSV rows."
    assert _text(qtbot, view, _key("reference-run")) == "Process labels"
    assert _text(qtbot, view, _key("barcode-run")) == "Generate barcode labels"
    assert _disabled(qtbot, view, _key("reference-run")) is False
    theme = get_theme_manager().get_current_theme()
    assert _style(qtbot, view, _key("reference-run"), "backgroundColor") == _rgb(
        theme.accent_fill
    )
    assert _style(qtbot, view, _key("barcode-run"), "backgroundColor") == _rgb(
        theme.accent_fill
    )
    seen = _caught(bridge.runRequested)
    _click(qtbot, view, _key("reference-run"))
    _click(qtbot, view, _key("barcode-run"))
    qtbot.waitUntil(lambda: seen == [("reference",), ("barcode",)])


def test_a_disabled_primary_reports_nothing(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state(reference=reference(pdf=None)))
    assert _disabled(qtbot, view, _key("reference-run")) is True
    seen = _caught(bridge.runRequested)
    _click(qtbot, view, _key("reference-run"))
    _click(qtbot, view, _key("barcode-run"))
    qtbot.waitUntil(lambda: seen == [("barcode",)])


def test_the_warning_tone_colours_the_reason(qtbot, page):
    view, bridge = page
    result = {"list": "DHL", "labels": 118, "failed": 2}
    _show(qtbot, view, bridge, make_state(barcode=barcode(result=result)))
    theme = get_theme_manager().get_current_theme()
    assert _style(qtbot, view, f"{BAR} .tool-reason", "color") == _rgb(theme.status_warning)


def test_the_print_buttons_follow_their_state(qtbot, page):
    view, bridge = page
    lists = (PackingList("DHL", 120, has_labels=True, has_qr=True),)
    _show(
        qtbot,
        view,
        bridge,
        make_state(reference=reference(has_output=True), barcode=barcode(lists=lists)),
    )
    assert _text(qtbot, view, _key("reference-print-labels")) == "Print…"
    assert _attr(qtbot, view, _key("reference-print-labels"), "title") == "Open the print dialog"
    assert _text(qtbot, view, _key("barcode-print-labels")) == "Print"
    assert _attr(qtbot, view, _key("barcode-print-labels"), "title") == "Send to Zebra ZD421"
    seen = _caught(bridge.printRequested)
    _click(qtbot, view, _key("reference-print-labels"))
    _click(qtbot, view, _key("barcode-print-qr"))
    _click(qtbot, view, _key("barcode-print-labels"))
    qtbot.waitUntil(
        lambda: seen == [("reference", "labels"), ("barcode", "qr"), ("barcode", "labels")]
    )


def test_print_before_a_run_is_disabled_and_says_why(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    assert _disabled(qtbot, view, _key("reference-print-labels")) is True
    assert _attr(qtbot, view, _key("reference-print-labels"), "title") == "Process labels first"
    assert _disabled(qtbot, view, _key("barcode-print-labels")) is True


def test_a_counted_run_shows_its_count_its_bar_and_cancel(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state(reference=reference(run=ToolRun(STAMPING, 40, 120))))
    assert _text(qtbot, view, f"{REF} .run-label") == "Stamping labels — 40 of 120"
    assert _text(qtbot, view, f"{REF} .run-count") == "40 of 120"
    track = _eval(qtbot, view, "document.querySelector('.run-track').getBoundingClientRect().width")
    fill = _eval(qtbot, view, "document.querySelector('.run-fill').getBoundingClientRect().width")
    assert abs(fill / track - 0.66) < 0.02
    assert _count(qtbot, view, _key("reference-run")) == 0
    assert _count(qtbot, view, _key("reference-print-labels")) == 0
    assert _text(qtbot, view, _key("reference-cancel")) == "Cancel"
    seen = _caught(bridge.cancelRequested)
    _click(qtbot, view, _key("reference-cancel"))
    qtbot.waitUntil(lambda: seen == [()])


def test_cancel_is_disabled_while_cancelling_and_while_saving(qtbot, page):
    view, bridge = page
    _show(
        qtbot,
        view,
        bridge,
        make_state(reference=reference(run=ToolRun(STAMPING, 40, 120, cancelling=True))),
    )
    assert _text(qtbot, view, _key("reference-cancel")) == "Cancelling…"
    assert _disabled(qtbot, view, _key("reference-cancel")) is True
    _show(qtbot, view, bridge, make_state(reference=reference(run=ToolRun(SAVING, 120, 120))))
    assert _text(qtbot, view, f"{REF} .run-label") == "Saving…"
    assert _disabled(qtbot, view, _key("reference-cancel")) is True
    assert _attr(qtbot, view, _key("reference-cancel"), "title") == "Saving can't be cancelled"


def test_a_barcode_run_is_one_sentence_with_no_bar_and_no_cancel(qtbot, page):
    view, bridge = page
    _show(
        qtbot,
        view,
        bridge,
        make_state(barcode=barcode(run=ToolRun("Writing 120 barcode labels…"))),
    )
    assert _text(qtbot, view, f"{BAR} .run-label") == "Writing 120 barcode labels…"
    assert _count(qtbot, view, f"{BAR} .run-track") == 0
    assert _count(qtbot, view, f"{BAR} [data-act='cancel']") == 0
    assert _count(qtbot, view, _key("barcode-run")) == 0


def test_a_running_card_locks_its_inputs_and_leaves_the_other_card_alone(qtbot, page):
    view, bridge = page
    zpl = PrintFacts(ZPL, PRINTERS)
    _show(
        qtbot,
        view,
        bridge,
        make_state(
            reference=reference(run=ToolRun(STAMPING, 40, 120)), reference_print=zpl
        ),
    )
    _click(qtbot, view, _key("reference-fold"))
    for key in (
        "pdf-clear",
        "csv-clear",
        "reference-folder",
        "reference-open_pdf",
        "reference-mode-driver",
        "reference-mode-raw_zpl",
        "reference-printer",
        "reference-target",
        "reference-width",
        "reference-rotate",
    ):
        assert _disabled(qtbot, view, _key(key)) is True, key
    assert _disabled(qtbot, view, _key("reference-fold")) is False
    for key in ("barcode-list", "barcode-refresh", "barcode-qr", "barcode-mode-driver", "barcode-run"):
        assert _disabled(qtbot, view, _key(key)) is False, key


# --- toast and drops ----------------------------------------------------------


def test_the_done_toast_offers_open_folder(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    bridge.raise_toast("120 barcode labels saved to …/barcodes/DHL", True)
    _until_js(qtbot, view, "document.getElementById('toast').hidden === false")
    assert _text(qtbot, view, "#toast-text") == "120 barcode labels saved to …/barcodes/DHL"
    assert _eval(qtbot, view, "document.getElementById('toast-action').hidden") is False
    assert _text(qtbot, view, "#toast-action") == "Open folder"
    seen = _caught(bridge.folderOpenRequested)
    _click(qtbot, view, "#toast-action")
    qtbot.waitUntil(lambda: seen == [()])
    assert _eval(qtbot, view, "document.getElementById('toast').hidden") is True


def test_a_plain_toast_has_no_action_and_can_be_dismissed(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    bridge.raise_toast("Processing cancelled", False)
    _until_js(qtbot, view, "document.getElementById('toast').hidden === false")
    assert _eval(qtbot, view, "document.getElementById('toast-action').hidden") is True
    _click(qtbot, view, "#toast-dismiss")
    assert _eval(qtbot, view, "document.getElementById('toast').hidden") is True


def test_a_file_dropped_on_the_page_does_not_navigate_it(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())
    for name in ("dragover", "drop"):
        prevented = _eval(
            qtbot,
            view,
            f"(function () {{ const e = new Event({name!r}, {{bubbles: true, cancelable: true}});"
            " document.body.dispatchEvent(e); return e.defaultPrevented; })()",
        )
        assert prevented is True


def test_driver_mode_for_both_tools_draws_no_fold(qtbot, page):
    view, bridge = page
    driver = PrintFacts(DRIVER, PRINTERS)
    _show(qtbot, view, bridge, make_state(reference_print=driver, barcode_print=driver))
    assert _count(qtbot, view, ".fold") == 0
    assert _text(qtbot, view, _key("barcode-print-labels")) == "Print…"


def test_left_and_right_move_between_the_two_mode_segments(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, make_state())

    def press(start, key):
        return _eval(
            qtbot,
            view,
            f"(function () {{ const el = document.querySelector({_key(start)!r}); el.focus();"
            f" el.dispatchEvent(new KeyboardEvent('keydown', {{key: {key!r}, bubbles: true}}));"
            " return document.activeElement.dataset.key; })()",
        )

    assert press("reference-mode-driver", "ArrowRight") == "reference-mode-raw_zpl"
    assert press("reference-mode-raw_zpl", "ArrowRight") == "reference-mode-driver"  # wraps
    assert press("barcode-mode-raw_zpl", "ArrowLeft") == "barcode-mode-driver"
    # Moving focus chooses nothing: Space or Enter does.
    assert _attr(qtbot, view, _key("reference-mode-driver"), "aria-checked") == "true"
````

- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_tools_page.py`
Expected: every test errors or fails with `FileNotFoundError: ... gui/web/tools.html`.

- [ ] **Step 3: Write the document**

Create `gui/web/tools.html`:

````html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Tools</title>
<!-- gui/web_page.py writes theme_css_vars() over the marker before the page
     loads, then tools.js keeps it current from the bridge. -->
<style id="theme-vars">/* theme-vars */</style>
<link rel="stylesheet" href="kit.css">
<link rel="stylesheet" href="tools.css">
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<script src="tools.js" defer></script>
</head>
<body>
<main id="tools"></main>
<div id="toast" class="toast" role="status" aria-live="polite" hidden>
  <span id="toast-text"></span>
  <button id="toast-action" class="toast-action" type="button" hidden>Open folder</button>
  <button id="toast-dismiss" class="toast-close" type="button" aria-label="Dismiss"></button>
</div>
</body>
</html>
````

- [ ] **Step 4: Write the stylesheet**

Create `gui/web/tools.css`:

````css
/* The Tools page (phase 5 spec section 5). Layout only: every component is
   the kit's. Every colour is a token from theme_css_vars(). */

#tools {
  height: 100%;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 20px 24px;
}

/* --- the no-session banner ----------------------------------------------- */

#tools > .banner > .glyph {
  width: 20px;
  height: 20px;
  color: var(--text-secondary);
  stroke-width: 1.5;
}

/* --- the two cards ------------------------------------------------------- */

.tool-cards {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  align-items: start;
}
.tool-card { display: flex; flex-direction: column; min-width: 0; }

.tool-head { display: flex; flex-direction: column; gap: 2px; padding: 14px 16px 12px; }
.tool-title { font-size: var(--type-label-size); font-weight: 700; }
.tool-text { color: var(--text-secondary); }

/* The kit's form row, sized for a half-width card: a narrower label column,
   a quiet label on the control's line, and a rule above every row because the
   card's head sits over the first one. */
.tool-card .form-row {
  grid-template-columns: 112px minmax(0, 1fr);
  gap: 12px;
  padding: 10px 16px;
  border-top: 1px solid var(--border-subtle);
}
.tool-card .form-label {
  padding-top: 0;
  font-weight: 400;
  color: var(--text-secondary);
  line-height: var(--control-height);
}

.tool-control { display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.tool-line {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  min-height: var(--control-height);
}

/* --- a picked file, and a folder ----------------------------------------- */

.tool-line > .glyph {
  width: 16px;
  height: 16px;
  color: var(--text-secondary);
  stroke-width: 1.5;
}
/* The line height keeps an underscore inside the clip box: overflow: hidden
   on a tight line cut "2026-09-30_1" to "2026-09-30 1". */
.file-name {
  min-width: 0;
  overflow: hidden;
  font-family: var(--font-family-mono);
  font-weight: 700;
  line-height: 1.6;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.file-meta {
  font-family: var(--font-family-mono);
  font-size: var(--type-caption-size);
  color: var(--text-secondary);
  white-space: nowrap;
}
.tool-line.bad > .glyph,
.tool-line.bad .file-meta { color: var(--status-danger); }
.tool-line.bad .file-meta { font-weight: 700; }

.tool-control .banner { border-radius: var(--kit-radius); }
.problem-title { font-weight: 700; color: var(--status-danger); }
.tool-control .banner .btn.link { align-self: flex-start; }

.path {
  min-width: 0;
  overflow: hidden;
  font-family: var(--font-family-mono);
  line-height: 1.6;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.path.muted { color: var(--text-disabled); }

/* --- options ------------------------------------------------------------- */

.options { display: flex; flex-wrap: wrap; gap: 8px 16px; }
.option {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  align-self: flex-start;
  cursor: pointer;
}
.option.disabled { color: var(--text-disabled); cursor: not-allowed; }

/* --- packing list and printer -------------------------------------------- */

.list-anchor { flex: 1 1 0; min-width: 0; }
.printer-anchor { flex: 1 1 160px; min-width: 0; }
.list-anchor .select,
.printer-anchor .select { width: 100%; }
/* As wide as its select, however long a name is. */
.list-anchor .menu,
.printer-anchor .menu { right: 0; min-width: 0; }
.menu-label { min-width: 0; overflow: hidden; text-overflow: ellipsis; }

/* --- print mode ---------------------------------------------------------- */

.mode-line { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; min-width: 0; }
.mode-help { font-size: var(--type-caption-size); color: var(--text-secondary); }
.mode-help.danger { color: var(--status-danger); }

.fold {
  display: flex;
  align-items: center;
  gap: 6px;
  align-self: flex-start;
  max-width: 100%;
  padding: 0;
  border: 0;
  background: transparent;
  font-size: var(--type-caption-size);
  text-align: left;
  cursor: pointer;
}
.fold:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 1px; }
.fold-title { font-weight: 700; text-decoration: underline; white-space: nowrap; }
.fold-summary {
  min-width: 0;
  overflow: hidden;
  color: var(--text-secondary);
  white-space: nowrap;
  text-overflow: ellipsis;
}
.fold-body {
  display: grid;
  grid-template-columns: 88px minmax(0, 1fr);
  gap: 8px 12px;
  align-items: center;
}
.fold-label { color: var(--text-secondary); }
.fold-body .field { width: 100%; min-width: 0; }
.size { display: flex; align-items: center; gap: 6px; }
.fold-body .size-field { width: 72px; }

/* --- footer -------------------------------------------------------------- */

.tool-foot {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 56px;
  padding: 12px 16px;
  border-top: 1px solid var(--border-subtle);
}
.tool-reason {
  flex: 1;
  min-width: 0;
  font-size: var(--type-caption-size);
  color: var(--text-secondary);
}
.tool-reason.danger { color: var(--status-danger); }
.tool-reason.warning { color: var(--status-warning); }

.run { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 6px; }
.run-label { font-weight: 700; }
.run-track {
  height: 4px;
  overflow: hidden;
  border-radius: 2px;
  background: var(--border-subtle);
}
.run-fill { height: 100%; background: var(--accent-fill); }

/* --- a narrow page ------------------------------------------------------- */

@media (max-width: 900px) {
  .tool-cards { grid-template-columns: minmax(0, 1fr); }
}
````

- [ ] **Step 5: Write the script**

Create `gui/web/tools.js`:

````javascript
// The Tools page (phase 5 spec section 5). Python builds everything this page
// draws (gui/tools_state.py) and sends it as bridge.state; this file renders
// that map and reports what the operator asks for through the bridge's named
// slots. No rule, count or enabled flag is computed here. The page's own state
// is which menu is open and which Label setup folds are open.
"use strict";

const TOAST_MS = 4000;
const TOAST_ACTION_MS = 8000;

// Lucide glyphs, each as one path.
const GLYPH = {
  folder: "M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2z",
  file: "M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7zM14 2v4a2 2 0 0 0 2 2h4",
  alert: "m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3M12 9v4M12 17h.01",
  refresh: "M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8M21 3v5h-5M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16M8 16H3v5",
  printer: "M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2M6 9V3a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v6M7 14h10a1 1 0 0 1 1 1v6a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1v-6a1 1 0 0 1 1-1z",
  chevron: "m6 9 6 6 6-6",
  chevronRight: "m9 18 6-6-6-6",
  check: "M20 6 9 17l-5-5",
  x: "M18 6 6 18M6 6l12 12",
};

const TOOLS = {
  reference: {
    title: "Reference labels",
    text: "Stamps each courier label PDF with its order's reference number.",
    action: "Process labels",
  },
  barcode: {
    title: "Barcode labels",
    text: "One barcode label for every Fulfillable order in a packing list. Each list gets its own folder.",
    action: "Generate barcode labels",
  },
};

const FILES = {
  pdf: { label: "Labels PDF", choose: "Choose PDF…", again: "Choose another PDF" },
  csv: { label: "Mapping CSV", choose: "Choose CSV…", again: "Choose another CSV" },
};

const MODES = [
  { value: "driver", label: "Driver" },
  { value: "raw_zpl", label: "Raw ZPL" },
];

const els = {};
const page = { bridge: null, state: null, renders: 0, toastTimer: null };
// menu: "barcode-list", "reference-printer", "barcode-printer", or null.
const view = { menu: null, fold: { reference: false, barcode: false } };

function esc(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function svg(path, cls) {
  return `<svg class="${cls}" viewBox="0 0 24 24" aria-hidden="true"><path d="${path}"/></svg>`;
}

function off(disabled) {
  return disabled ? " disabled" : "";
}

// --- head and banner ---------------------------------------------------------

function head(s) {
  const session = s.session.name
    ? `<span class="code">${esc(s.session.name)}</span><span class="page-meta">${esc(s.session.meta)}</span>`
    : "";
  return `<div class="page-head"><span class="page-title">Tools</span>${session}</div>`;
}

function banner() {
  return `<section class="banner neutral" data-banner="no-session">
    ${svg(GLYPH.folder, "glyph")}
    <div class="banner-body">
      <span class="banner-title">Open a session to use these tools</span>
      <span class="banner-text">Both tools read the session's files and save into its folder. Print modes can be set now; they're saved on this PC.</span>
    </div>
    <button class="btn primary" type="button" data-act="new-session" data-key="new-session">New session</button>
    <button class="btn secondary" type="button" data-act="open-recent" data-key="open-recent">Open recent</button>
  </section>`;
}

// --- rows --------------------------------------------------------------------

function cardHead(tool) {
  return `<div class="tool-head">
    <span class="tool-title">${TOOLS[tool].title}</span>
    <span class="tool-text">${TOOLS[tool].text}</span>
  </div>`;
}

function row(name, label, body) {
  return `<div class="form-row" data-row="${name}"><span class="form-label">${label}</span><div class="tool-control">${body}</div></div>`;
}

function problemBlock(kind, problem, disabled) {
  return `<div class="banner danger" role="alert">
    ${svg(GLYPH.alert, "glyph")}
    <div class="banner-body">
      <span class="problem-title">${esc(problem.title)}</span>
      <span class="banner-text">${esc(problem.text)}</span>
      <button class="btn link" type="button" data-act="choose" data-kind="${kind}" data-key="${kind}-again"${off(disabled)}>${FILES[kind].again}</button>
    </div>
  </div>`;
}

function fileRow(kind, picked, disabled) {
  const file = FILES[kind];
  if (!picked.name) {
    return row(
      kind,
      file.label,
      `<div class="tool-line"><button class="btn secondary" type="button" data-act="choose" data-kind="${kind}" data-key="${kind}-choose"${off(disabled)}>${file.choose}</button></div>`,
    );
  }
  const bad = Boolean(picked.problem && picked.problem.title);
  return row(
    kind,
    file.label,
    `<div class="tool-line${bad ? " bad" : ""}">
      ${svg(GLYPH.file, "glyph")}
      <span class="file-name" title="${esc(picked.name)}">${esc(picked.name)}</span>
      <span class="file-meta">${esc(picked.meta)}</span>
      <span class="spacer"></span>
      <button class="btn secondary compact" type="button" data-act="clear" data-kind="${kind}" data-key="${kind}-clear"${off(disabled)}>Replace</button>
    </div>${bad ? problemBlock(kind, picked.problem, disabled) : ""}`,
  );
}

function folderText(folder) {
  return `<span class="path${folder.muted ? " muted" : ""}" title="${esc(folder.title)}">${esc(folder.text)}</span>`;
}

function option(tool, name, label, checked, disabled) {
  return `<label class="option${disabled ? " disabled" : ""}"><input type="checkbox" data-opt="${name}" data-tool="${tool}" data-key="${tool}-${name}"${checked ? " checked" : ""}${off(disabled)}>${label}</label>`;
}

function menuItem(act, tool, value, label, hint, checked, key) {
  const meta = hint ? `<span class="menu-hint mono">${esc(hint)}</span>` : "";
  return `<button class="menu-item" type="button" role="menuitemradio" aria-checked="${Boolean(checked)}" data-act="${act}" data-tool="${tool}" data-value="${esc(value)}" data-key="${key}">${svg(GLYPH.check, "check")}<span class="menu-label">${esc(label)}</span>${meta}</button>`;
}

function listRow(s) {
  const card = s.barcode;
  const open = view.menu === "barcode-list";
  const disabled = card.quiet || card.locked || !card.lists.length;
  const shown = card.list.name
    ? `<span class="select-value">${esc(card.list.name)}</span><span class="select-meta">${esc(card.list.meta)}</span>`
    : `<span class="select-value placeholder">${esc(card.list.placeholder)}</span>`;
  const items = card.lists
    .map((entry, n) =>
      menuItem("list", "barcode", entry.name, entry.name, entry.meta, entry.checked, `barcode-list-item-${n}`),
    )
    .join("");
  const menu = open
    ? `<div class="menu" role="menu"><div class="menu-group">Packing lists in ${esc(s.session.name)}</div>${items}</div>`
    : "";
  return row(
    "list",
    "Packing list",
    `<div class="tool-line">
      <div class="menu-anchor list-anchor">
        <button class="select" type="button" aria-haspopup="menu" aria-expanded="${open}" data-act="menu" data-menu="barcode-list" data-key="barcode-list"${off(disabled)}>${shown}${svg(GLYPH.chevron, "glyph")}</button>
        ${menu}
      </div>
      <button class="btn secondary" type="button" data-act="refresh" data-key="barcode-refresh" title="Refresh packing lists"${off(card.quiet || card.locked)}>${svg(GLYPH.refresh, "glyph")}Refresh</button>
    </div>`,
  );
}

// --- print mode --------------------------------------------------------------

function size(value) {
  return Number(value) > 0 ? String(value) : "";
}

function fold(tool, card) {
  const setup = card.print.setup;
  if (!setup.summary) return "";
  const open = view.fold[tool];
  const locked = card.locked;
  const turned = setup.rotate ? " checked" : "";
  const inverted = setup.invert ? " checked" : "";
  const body = open
    ? `<div class="fold-body">
        <label class="fold-label" for="${tool}-target">Target</label>
        <input id="${tool}-target" class="field" type="text" value="${esc(setup.target)}" placeholder="Printer name, or \\\\server\\printer" data-print="target" data-tool="${tool}" data-key="${tool}-target"${off(locked)}>
        <span class="fold-label">Label size</span>
        <div class="size">
          <input class="field size-field" type="number" min="0" max="500" step="0.1" value="${size(setup.width)}" placeholder="PDF" title="${esc(setup.size_hint)}" aria-label="Label width in mm" data-print="width" data-tool="${tool}" data-key="${tool}-width"${off(locked)}>
          <span>×</span>
          <input class="field size-field" type="number" min="0" max="500" step="0.1" value="${size(setup.height)}" placeholder="PDF" title="${esc(setup.size_hint)}" aria-label="Label height in mm" data-print="height" data-tool="${tool}" data-key="${tool}-height"${off(locked)}>
          <span>mm</span>
        </div>
        <span></span>
        <label class="option${locked ? " disabled" : ""}"><input type="checkbox" data-print="rotate" data-tool="${tool}" data-key="${tool}-rotate"${turned}${off(locked)}>Rotate 90°</label>
        <span></span>
        <label class="option${locked ? " disabled" : ""}" title="Tick if labels print white on black."><input type="checkbox" data-print="invert" data-tool="${tool}" data-key="${tool}-invert"${inverted}${off(locked)}>Invert colours</label>
      </div>`
    : "";
  return `<button class="fold" type="button" aria-expanded="${open}" data-act="fold" data-tool="${tool}" data-key="${tool}-fold">${svg(open ? GLYPH.chevron : GLYPH.chevronRight, "glyph")}<span class="fold-title">Label setup</span><span class="fold-summary">${esc(setup.summary)}</span></button>${body}`;
}

function printRow(tool, card) {
  const print = card.print;
  const locked = card.locked;
  const menuName = `${tool}-printer`;
  const open = view.menu === menuName;
  const segments = MODES.map((mode) => {
    const on = print.mode === mode.value;
    return `<button class="segment" type="button" role="radio" aria-checked="${on}" tabindex="${on ? 0 : -1}" data-act="mode" data-tool="${tool}" data-value="${mode.value}" data-key="${tool}-mode-${mode.value}"${off(locked)}>${mode.label}</button>`;
  }).join("");
  const items = print.printers
    .map((entry, n) =>
      menuItem("printer", tool, entry.value, entry.label, "", entry.checked, `${menuName}-item-${n}`),
    )
    .join("");
  const menu = open ? `<div class="menu" role="menu">${items}</div>` : "";
  return row(
    "print",
    "Print mode",
    `<div class="mode-line">
      <div class="segmented" role="radiogroup" aria-label="Print mode">${segments}</div>
      <div class="menu-anchor printer-anchor">
        <button class="select" type="button" aria-haspopup="menu" aria-expanded="${open}" aria-label="Printer" data-act="menu" data-menu="${menuName}" data-key="${menuName}"${off(locked)}>${svg(GLYPH.printer, "glyph")}<span class="select-value${print.printer.placeholder ? " placeholder" : ""}">${esc(print.printer.label)}</span>${svg(GLYPH.chevron, "glyph")}</button>
        ${menu}
      </div>
    </div>
    <span class="mode-help${print.help_tone === "danger" ? " danger" : ""}">${esc(print.help)}</span>
    ${fold(tool, card)}`,
  );
}

// --- footer ------------------------------------------------------------------

function printButton(tool, what, button) {
  return `<button class="btn secondary" type="button" data-act="print" data-tool="${tool}" data-what="${what}" data-key="${tool}-print-${what}" title="${esc(button.title)}"${off(!button.enabled)}>${esc(button.label)}</button>`;
}

function foot(tool, card) {
  const run = card.run;
  if (run.label) {
    const count = run.count ? ` — <span class="mono run-count">${esc(run.count)}</span>` : "";
    const bar = run.bar
      ? `<div class="run-track"><div class="run-fill" style="width: ${Number(run.percent)}%"></div></div>`
      : "";
    const cancel = run.cancel && run.cancel.label
      ? `<button class="btn secondary" type="button" data-act="cancel" data-key="${tool}-cancel" title="${esc(run.cancel.title)}"${off(!run.cancel.enabled)}>${esc(run.cancel.label)}</button>`
      : "";
    return `<div class="tool-foot" data-running="true">
      <div class="run"><span class="run-label">${esc(run.label)}${count}</span>${bar}</div>
      ${cancel}
    </div>`;
  }
  const qr = card.qr_button && card.qr_button.label ? printButton(tool, "qr", card.qr_button) : "";
  return `<div class="tool-foot">
    <span class="tool-reason${card.tone ? ` ${esc(card.tone)}` : ""}">${esc(card.reason)}</span>
    ${qr}
    ${printButton(tool, "labels", card.print_button)}
    <button class="btn primary" type="button" data-act="run" data-tool="${tool}" data-key="${tool}-run"${off(!card.can_run)}>${TOOLS[tool].action}</button>
  </div>`;
}

// --- the two cards -----------------------------------------------------------

function referenceCard(s) {
  const card = s.reference;
  const disabled = card.quiet || card.locked;
  return `<section class="card tool-card" data-tool="reference" aria-label="${TOOLS.reference.title}">
    ${cardHead("reference")}
    ${fileRow("pdf", card.pdf, disabled)}
    ${fileRow("csv", card.csv, disabled)}
    ${row(
      "folder",
      "Output folder",
      `<div class="tool-line">
        ${folderText(card.folder)}
        <span class="spacer"></span>
        <button class="btn secondary" type="button" data-act="folder" data-key="reference-folder"${off(disabled)}>Change…</button>
      </div>
      ${option("reference", "open_pdf", "Open the PDF when it's ready", card.open_pdf, disabled)}`,
    )}
    ${printRow("reference", card)}
    ${foot("reference", card)}
  </section>`;
}

function barcodeCard(s) {
  const card = s.barcode;
  const disabled = card.quiet || card.locked;
  return `<section class="card tool-card" data-tool="barcode" aria-label="${TOOLS.barcode.title}">
    ${cardHead("barcode")}
    ${listRow(s)}
    ${row(
      "folder",
      "Output folder",
      `<div class="tool-line">${folderText(card.folder)}</div>
      <div class="options">
        ${option("barcode", "qr", "Add QR labels (order number)", card.qr, disabled)}
        ${option("barcode", "open_pdf", "Open the PDF when it's ready", card.open_pdf, disabled)}
      </div>`,
    )}
    ${printRow("barcode", card)}
    ${foot("barcode", card)}
  </section>`;
}

// --- render ------------------------------------------------------------------

// A menu whose select a new state disabled must not stay open over it.
function menuStillOpens(s) {
  if (view.menu === "barcode-list") {
    return !s.barcode.quiet && !s.barcode.locked && s.barcode.lists.length > 0;
  }
  if (view.menu === "reference-printer") return !s.reference.locked;
  if (view.menu === "barcode-printer") return !s.barcode.locked;
  return false;
}

function render() {
  const s = page.state;
  if (!s || !s.reference) return;
  if (view.menu !== null && !menuStillOpens(s)) view.menu = null;
  // The whole page is redrawn, so the control that had focus is found again
  // by its key, and a field being typed in keeps what was typed: a state can
  // arrive mid-edit, from the other card's run.
  const active = document.activeElement;
  const key = active && active.dataset ? active.dataset.key : null;
  const typing = key && (active.type === "text" || active.type === "number");
  const typed = typing ? active.value : null;
  const caret = typing && active.type === "text" ? [active.selectionStart, active.selectionEnd] : null;
  els.tools.innerHTML =
    head(s) +
    (s.banner ? banner() : "") +
    `<div class="tool-cards">${referenceCard(s)}${barcodeCard(s)}</div>`;
  if (key) {
    const again = els.tools.querySelector(`[data-key="${key}"]`);
    if (again && !again.disabled) {
      if (typed !== null) again.value = typed;
      again.focus();
      if (caret) again.setSelectionRange(caret[0], caret[1]);
    }
  }
  page.renders += 1;
  document.documentElement.dataset.renders = String(page.renders);
}

function focusKey(key) {
  const el = els.tools.querySelector(`[data-key="${key}"]`);
  if (el && !el.disabled) el.focus();
}

// --- input -------------------------------------------------------------------

function onClick(event) {
  const el = event.target.closest("[data-act]");
  const bridge = page.bridge;
  if (!el || el.disabled || !bridge) return;
  const data = el.dataset;
  switch (data.act) {
    case "choose": bridge.chooseFile(data.kind); break;
    case "clear": bridge.clearFile(data.kind); break;
    case "folder": bridge.changeFolder(); break;
    case "mode": bridge.setPrint(data.tool, "mode", data.value); break;
    case "menu":
      view.menu = view.menu === data.menu ? null : data.menu;
      render();
      focusKey(data.menu);
      break;
    case "printer": {
      const menu = view.menu;
      view.menu = null;
      bridge.setPrint(data.tool, "printer", data.value);
      render();
      focusKey(menu);
      break;
    }
    case "list":
      view.menu = null;
      bridge.chooseList(data.value);
      render();
      focusKey("barcode-list");
      break;
    case "refresh": bridge.refreshLists(); break;
    case "fold":
      view.fold[data.tool] = !view.fold[data.tool];
      render();
      focusKey(`${data.tool}-fold`);
      break;
    case "run": bridge.run(data.tool); break;
    case "cancel": bridge.cancel(); break;
    case "print": bridge.printLabels(data.tool, data.what); break;
    case "new-session": bridge.newSession(); break;
    case "open-recent": bridge.openRecent(); break;
  }
}

// A checkbox reports at once; a text or number field on change (blur or
// Enter), never per keystroke.
function onChange(event) {
  const el = event.target;
  const bridge = page.bridge;
  if (!bridge || !el.dataset) return;
  const data = el.dataset;
  if (data.opt) {
    bridge.setOption(data.tool, data.opt, el.checked);
    return;
  }
  if (!data.print) return;
  if (el.type === "checkbox") {
    bridge.setPrint(data.tool, data.print, el.checked);
  } else if (el.type === "number") {
    const value = Number(el.value);
    bridge.setPrint(data.tool, data.print, Number.isFinite(value) ? value : 0);
  } else {
    bridge.setPrint(data.tool, data.print, el.value);
  }
}

function closeMenu() {
  const menu = view.menu;
  if (menu === null) return;
  view.menu = null;
  render();
  focusKey(menu);
}

function onKey(event) {
  if (event.key === "Escape" && view.menu !== null) {
    event.preventDefault();
    closeMenu();
    return;
  }
  const vertical = event.key === "ArrowUp" || event.key === "ArrowDown";
  if (vertical && view.menu !== null) {
    // Up and Down walk the open menu, from its select or from an item.
    const items = Array.from(els.tools.querySelectorAll(".menu .menu-item"));
    if (!items.length) return;
    const at = items.indexOf(document.activeElement);
    const step = event.key === "ArrowUp" ? -1 : 1;
    const next = at < 0 ? (step > 0 ? 0 : items.length - 1) : (at + step + items.length) % items.length;
    event.preventDefault();
    items[next].focus();
    return;
  }
  // Left and Right move between the two mode segments; Space and Enter are
  // the button's own.
  const segment = event.target.closest ? event.target.closest(".segment") : null;
  if (!segment || (event.key !== "ArrowLeft" && event.key !== "ArrowRight")) return;
  const group = Array.from(segment.parentElement.querySelectorAll(".segment:not(:disabled)"));
  if (group.length < 2) return;
  const step = event.key === "ArrowLeft" ? -1 : 1;
  event.preventDefault();
  group[(group.indexOf(segment) + step + group.length) % group.length].focus();
}

// --- toast (ADR 0007: a web page draws its own) --------------------------------

function raiseToast(text, action) {
  els.toastText.textContent = text;
  els.toastAction.hidden = !action;
  els.toast.hidden = false;
  if (page.toastTimer !== null) clearTimeout(page.toastTimer);
  page.toastTimer = setTimeout(dismissToast, action ? TOAST_ACTION_MS : TOAST_MS);
}

function dismissToast() {
  if (page.toastTimer !== null) clearTimeout(page.toastTimer);
  page.toastTimer = null;
  els.toast.hidden = true;
}

// --- boot --------------------------------------------------------------------

function bind() {
  els.tools = document.getElementById("tools");
  els.themeVars = document.getElementById("theme-vars");
  els.toast = document.getElementById("toast");
  els.toastText = document.getElementById("toast-text");
  els.toastAction = document.getElementById("toast-action");
  els.toastDismiss = document.getElementById("toast-dismiss");
  els.toastDismiss.innerHTML = svg(GLYPH.x, "glyph");
  els.toastDismiss.addEventListener("click", dismissToast);
  els.toastAction.addEventListener("click", () => {
    if (page.bridge) page.bridge.openFolder();
    dismissToast();
  });
  els.tools.addEventListener("click", onClick);
  els.tools.addEventListener("change", onChange);
  document.addEventListener("keydown", onKey);
  // After the page's own handler: a click anywhere but a menu's anchor closes
  // the open menu.
  document.addEventListener("click", (event) => {
    if (view.menu === null || event.target.closest(".menu-anchor")) return;
    view.menu = null;
    render();
  });
  // A file dropped on the page must not navigate the view. It loads nothing.
  document.addEventListener("dragover", (event) => event.preventDefault());
  document.addEventListener("drop", (event) => event.preventDefault());
}

bind();

new QWebChannel(qt.webChannelTransport, function (channel) {
  const bridge = channel.objects.tools;
  page.bridge = bridge;
  els.themeVars.textContent = bridge.themeCss;
  bridge.themeCssChanged.connect(() => { els.themeVars.textContent = bridge.themeCss; });
  bridge.stateChanged.connect(() => { page.state = bridge.state; render(); });
  bridge.toastRaised.connect((text, action) => raiseToast(text, action));
  page.state = bridge.state;
  render();
  window.toolsBridge = bridge;
  document.documentElement.dataset.bridge = "ready";
});
````

- [ ] **Step 6: Run the tests and see them pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_tools_page.py tests/test_style_literals_guard.py`
Expected: all pass (48 passed), in about fifteen seconds.

- [ ] **Step 7: Lint**

Run: `.venv/bin/ruff check tests/test_tools_page.py`
Expected: `All checks passed!`

- [ ] **Step 8: Commit**

Message: `Tools page: two tool cards on the web kit (phase 5 spec 5)`.
Add `gui/web/tools.html`, `gui/web/tools.css`, `gui/web/tools.js` and `tests/test_tools_page.py`.

---

### Task 7: The Reference labels tool (`gui/reference_tool.py`)

**Files:**
- Create: `gui/reference_tool.py`
- Test: `tests/test_reference_tool.py` (new)

**Interfaces:**
- Consumes: Task 1 (`pdf_page_count`, `load_csv_mapping(...)["rows"]`, `process_reference_labels`, `READING`,
  `SAVING`, `ProcessingCancelled`, `InvalidPDFError`, `InvalidCSVError`, `MappingError`,
  `reference_run_warning`); Task 3 (`PickedFile`, `ReferenceFacts`, `ToolRun`, `PRINT_SCOPE`, `short_path`);
  `gui.worker.Worker(fn, *args, **kwargs)` with `.signals.result/error/finished`, `.fn`, `.args`, `.kwargs`;
  `gui.components.show_error(source, headline, what_to_do)`; `gui.pdf_printing.print_pdf(parent, pdf_path,
  settings)` and `load_print_settings(scope)`, called through the module as `pdf_printing.print_pdf(...)`.
- Produces: `ReferenceTool(host: QWidget, pool: QThreadPool | None = None)` with signals `changed()` and
  `toast(str, str)` (text, folder to offer or `""`), and methods `facts() -> ReferenceFacts`,
  `set_session(session_path: str | None)`, `choose(kind)`, `load(kind, path)`, `clear(kind)`,
  `change_folder()`, `set_open_pdf(on)`, `start()`, `cancel()`, `print_output()`. `kind` is `"pdf"` or
  `"csv"`. Also `PDF_PROBLEM` and `CSV_PROBLEM`, each a `(title, text)` tuple.

A `Worker` emits `result` (or `error`) and then `finished`. The tests never start a thread: they give the tool a
pool whose `start` only records the worker, then call `worker.fn(*worker.args, **worker.kwargs)` and the tool's
`_on_result`, `_on_error` and `_on_finished` in that order.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_reference_tool.py`:

````python
"""Reference labels as the Tools page runs it (phase 5 spec section 6.2).

No test runs a real Worker thread: the tool is given a pool that only captures
the worker, and the test calls the worker's function and the tool's result,
error and finished slots itself, in the order Worker emits them.
"""

import os

import pytest
from PySide6.QtWidgets import QApplication, QFileDialog, QWidget
from reportlab.pdfgen import canvas

from gui import reference_tool
from gui.reference_tool import CSV_PROBLEM, PDF_PROBLEM, ReferenceTool
from gui.tools_state import PickedFile
from shopify_tool.pdf_processor import (
    READING,
    SAVING,
    STAMPING,
    InvalidCSVError,
    InvalidPDFError,
    MappingError,
    ProcessingCancelled,
)

MAPPING = (
    "PostOne,Tracking,Reference,Col3,Col4,Col5,Name\n"
    ",,REF-001,,,,Acme Warehouse Co\n"
    ",,REF-002,,,,Borealis Ltd\n"
)


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


class Pool:
    """Captures a worker instead of running it on a thread."""

    def __init__(self):
        self.started = []

    def start(self, worker):
        self.started.append(worker)


@pytest.fixture
def host(qtbot):
    widget = QWidget()
    qtbot.addWidget(widget)
    return widget


@pytest.fixture
def opened(monkeypatch):
    """Record PDFs the tool opens instead of launching a viewer."""
    seen = []

    def open_url(url):
        seen.append(url.toLocalFile())
        return True

    monkeypatch.setattr(reference_tool.QDesktopServices, "openUrl", open_url)
    return seen


@pytest.fixture
def errors(monkeypatch):
    seen = []
    monkeypatch.setattr(
        reference_tool, "show_error", lambda _host, headline, what: seen.append((headline, what))
    )
    return seen


@pytest.fixture
def files(tmp_path):
    """A two-page courier PDF, its mapping CSV, and a session folder."""
    pdf = tmp_path / "dhl-labels.pdf"
    c = canvas.Canvas(str(pdf), pagesize=(288, 432))
    c.drawString(20, 400, "Acme Warehouse Co")
    c.showPage()
    c.drawString(20, 400, "Borealis Ltd")
    c.showPage()
    c.save()
    csv = tmp_path / "refs.csv"
    csv.write_text(MAPPING)
    session = tmp_path / "2026-09-30_1"
    session.mkdir()
    return str(pdf), str(csv), str(session)


def _tool(host, session=None):
    pool = Pool()
    tool = ReferenceTool(host, pool)
    if session:
        tool.set_session(session)
    return tool, pool


def _ready(host, files):
    pdf, csv, session = files
    tool, pool = _tool(host, session)
    tool.load("pdf", pdf)
    tool.load("csv", csv)
    return tool, pool


def _caught(signal):
    seen = []
    signal.connect(lambda *args: seen.append(args))
    return seen


def _finish(tool, pool):
    """Run the captured worker's function here and hand the tool its result,
    as Worker would: result, then finished."""
    worker = pool.started[-1]
    result = worker.fn(*worker.args, **worker.kwargs)
    tool._on_result(result)
    tool._on_finished()
    return result


# --- session and picks --------------------------------------------------------


def test_a_new_tool_has_no_session_and_no_picks(host):
    tool, _pool = _tool(host)
    facts = tool.facts()
    assert (facts.pdf, facts.csv, facts.folder, facts.run, facts.result) == (
        None,
        None,
        "",
        None,
        None,
    )
    assert facts.open_pdf is True and facts.has_output is False


def test_a_session_sets_the_folder_without_touching_the_share(host, tmp_path):
    tool, _pool = _tool(host)
    session = tmp_path / "not-created-yet"
    tool.set_session(str(session))
    assert tool.facts().folder == str(session / "reference_labels")
    assert not session.exists()


def test_a_good_pdf_and_csv_are_counted(host, files):
    tool, _pool = _ready(host, files)
    facts = tool.facts()
    assert facts.pdf == PickedFile("dhl-labels.pdf", 2)
    assert facts.csv == PickedFile("refs.csv", 2)


def test_a_file_that_is_not_a_pdf_is_flagged(host, files, tmp_path):
    _pdf, _csv, session = files
    tool, _pool = _tool(host, session)
    bad = tmp_path / "notes.pdf"
    bad.write_text("not a pdf")
    tool.load("pdf", str(bad))
    assert tool.facts().pdf == PickedFile("notes.pdf", None, PDF_PROBLEM)


def test_a_csv_with_no_usable_rows_is_flagged(host, files, tmp_path):
    _pdf, _csv, session = files
    tool, _pool = _tool(host, session)
    bad = tmp_path / "orders.csv"
    bad.write_text("Order,Tracking,Date\n#1,TR1,2026-09-30\n")
    tool.load("csv", str(bad))
    assert tool.facts().csv == PickedFile("orders.csv", None, CSV_PROBLEM)


def test_a_pick_that_vanished_before_the_check_is_flagged_not_raised(host, files, tmp_path):
    _pdf, _csv, session = files
    tool, _pool = _tool(host, session)
    tool.load("pdf", str(tmp_path / "gone.pdf"))
    tool.load("csv", str(tmp_path / "gone.csv"))
    assert tool.facts().pdf.problem == PDF_PROBLEM
    assert tool.facts().csv.problem == CSV_PROBLEM


def test_with_no_session_nothing_loads(host, files):
    pdf, _csv, _session = files
    tool, _pool = _tool(host)
    tool.load("pdf", pdf)
    assert tool.facts().pdf is None


def test_every_change_is_announced(host, files):
    pdf, _csv, session = files
    tool, _pool = _tool(host)
    seen = _caught(tool.changed)
    tool.set_session(session)
    tool.load("pdf", pdf)
    tool.clear("pdf")
    tool.set_open_pdf(False)
    assert len(seen) == 4
    assert tool.facts().open_pdf is False


def test_a_session_change_clears_the_picks_and_the_result(host, files, opened, tmp_path):
    tool, pool = _ready(host, files)
    tool.start()
    _finish(tool, pool)
    assert tool.facts().has_output is True

    other = tmp_path / "2026-10-01_1"
    tool.set_session(str(other))
    facts = tool.facts()
    assert (facts.pdf, facts.csv, facts.result, facts.has_output) == (None, None, None, False)
    assert facts.folder == str(other / "reference_labels")

    tool.set_session(None)
    assert tool.facts().folder == ""


def test_choose_opens_a_dialog_and_loads_what_was_picked(host, files, monkeypatch):
    pdf, _csv, session = files
    tool, _pool = _tool(host, session)
    asked = []

    def pick(parent, title, start, pattern):
        asked.append((title, pattern))
        return pdf, pattern

    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(pick))
    tool.choose("pdf")
    assert asked == [("Select the labels PDF", "PDF Files (*.pdf)")]
    assert tool.facts().pdf.count == 2


def test_a_cancelled_dialog_changes_nothing(host, files, monkeypatch):
    _pdf, _csv, session = files
    tool, _pool = _tool(host, session)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a: ("", "")))
    seen = _caught(tool.changed)
    tool.choose("csv")
    assert seen == [] and tool.facts().csv is None


def test_change_folder_takes_the_chosen_folder_until_the_session_changes(
    host, files, monkeypatch, tmp_path
):
    _pdf, _csv, session = files
    tool, _pool = _tool(host, session)
    elsewhere = tmp_path / "elsewhere"
    monkeypatch.setattr(
        QFileDialog, "getExistingDirectory", staticmethod(lambda *a: str(elsewhere))
    )
    tool.change_folder()
    assert tool.facts().folder == str(elsewhere)
    tool.set_session(session)
    assert tool.facts().folder == os.path.join(session, "reference_labels")


# --- the run ------------------------------------------------------------------


@pytest.mark.parametrize("missing", ["pdf", "csv"])
def test_start_does_nothing_until_both_files_are_good(host, files, missing):
    tool, pool = _ready(host, files)
    tool.clear(missing)
    tool.start()
    assert pool.started == [] and tool.facts().run is None


def test_start_does_nothing_with_a_problem_file(host, files, tmp_path):
    tool, pool = _ready(host, files)
    bad = tmp_path / "bad.csv"
    bad.write_text("a,b\n1,2\n")
    tool.load("csv", str(bad))
    tool.start()
    assert pool.started == []


def test_start_hands_one_worker_to_the_pool_and_shows_the_first_phase(host, files):
    tool, pool = _ready(host, files)
    tool.start()
    assert len(pool.started) == 1
    run = tool.facts().run
    assert (run.label, run.done, run.total, run.cancelling) == (READING, 0, 2, False)
    tool.start()  # a second click while running
    assert len(pool.started) == 1


def test_inputs_cannot_change_while_running(host, files):
    pdf, _csv, _session = files
    tool, _pool = _ready(host, files)
    tool.start()
    tool.clear("pdf")
    tool.load("csv", pdf)
    assert tool.facts().pdf.count == 2
    assert tool.facts().csv.name == "refs.csv"


def test_a_finished_run_keeps_its_result_opens_the_pdf_and_toasts(host, files, opened):
    _pdf, _csv, session = files
    tool, pool = _ready(host, files)
    toasts = _caught(tool.toast)
    tool.start()
    result = _finish(tool, pool)

    folder = os.path.join(session, "reference_labels")
    assert os.path.dirname(result["output_file"]) == folder  # the worker made it
    facts = tool.facts()
    assert facts.run is None
    assert facts.result == result
    assert facts.has_output is True
    assert opened == [result["output_file"]]
    assert toasts == [
        (f"2 labels saved to …{os.sep}2026-09-30_1{os.sep}reference_labels", folder)
    ]


def test_with_open_pdf_off_nothing_is_opened(host, files, opened):
    tool, pool = _ready(host, files)
    tool.set_open_pdf(False)
    tool.start()
    _finish(tool, pool)
    assert opened == []


def test_a_run_that_needs_checking_raises_no_toast(host, files, opened):
    tool, _pool = _ready(host, files)
    toasts = _caught(tool.toast)
    tool.start()
    result = {
        "output_file": os.path.join(files[2], "reference_labels", "out.pdf"),
        "pages_processed": 2,
        "matched": 2,
        "unmatched": 0,
        "duplicate_refs": ["REF-001"],
        "missing_refs": [],
        "name_matched": 0,
    }
    tool._on_result(result)
    tool._on_finished()
    assert toasts == []
    assert tool.facts().result == result


def test_a_pdf_that_will_not_open_says_where_it_is(host, files, errors, monkeypatch):
    monkeypatch.setattr(reference_tool.QDesktopServices, "openUrl", lambda url: False)
    tool, pool = _ready(host, files)
    tool.start()
    result = _finish(tool, pool)
    assert errors == [("The PDF didn't open", f"Open it manually: {result['output_file']}")]


def test_progress_reaches_the_facts(host, files):
    tool, _pool = _ready(host, files)
    tool.start()
    tool._on_progress(1, 2, STAMPING)
    run = tool.facts().run
    assert (run.label, run.done, run.total) == (STAMPING, 1, 2)


def test_a_late_progress_report_after_the_run_is_ignored(host, files, opened):
    tool, pool = _ready(host, files)
    tool.start()
    _finish(tool, pool)
    tool._on_progress(2, 2, STAMPING)
    assert tool.facts().run is None


def test_reports_are_throttled_but_a_phases_last_one_always_gets_through(
    host, files, monkeypatch
):
    tool, _pool = _ready(host, files)
    tool.start()
    seen = _caught(tool._progress)
    clock = iter([10.0, 10.01, 10.02, 10.5])
    monkeypatch.setattr(reference_tool.time, "monotonic", lambda: next(clock))
    tool._report(1, 100, READING)  # first: through
    tool._report(2, 100, READING)  # 10 ms later: dropped
    tool._report(100, 100, READING)  # the phase's last: through
    tool._report(1, 100, STAMPING)  # 480 ms later: through
    assert seen == [(1, 100, READING), (100, 100, READING), (1, 100, STAMPING)]


def test_cancel_marks_the_run_and_stops_it_at_the_next_report(host, files):
    tool, _pool = _ready(host, files)
    tool.start()
    tool.cancel()
    assert tool.facts().run.cancelling is True
    with pytest.raises(ProcessingCancelled):
        tool._report(1, 2, READING)


def test_a_cancelled_run_writes_nothing_toasts_and_shows_no_error(host, files, errors, opened):
    _pdf, _csv, session = files
    tool, pool = _ready(host, files)
    toasts = _caught(tool.toast)
    tool.start()
    tool.cancel()
    worker = pool.started[-1]
    with pytest.raises(ProcessingCancelled) as caught:
        worker.fn(*worker.args, **worker.kwargs)
    tool._on_error((ProcessingCancelled, caught.value, "trace"))
    tool._on_finished()

    assert os.listdir(os.path.join(session, "reference_labels")) == []
    assert toasts == [("Processing cancelled", "")]
    assert errors == []
    facts = tool.facts()
    assert (facts.run, facts.result, facts.has_output) == (None, None, False)
    assert facts.pdf.count == 2  # the picks stay, ready to run again


def test_cancel_does_nothing_when_idle_or_once_saving(host, files):
    tool, _pool = _ready(host, files)
    tool.cancel()
    assert tool.facts().run is None
    tool.start()
    tool._on_progress(2, 2, SAVING)
    tool.cancel()
    assert tool.facts().run.cancelling is False
    tool._report(2, 2, SAVING)  # does not raise


def test_a_second_run_is_not_cancelled_by_the_first_ones_cancel(host, files, opened):
    tool, pool = _ready(host, files)
    tool.start()
    tool.cancel()
    tool._on_error((ProcessingCancelled, ProcessingCancelled(), ""))
    tool._on_finished()
    tool.start()
    result = _finish(tool, pool)
    assert result["pages_processed"] == 2


@pytest.mark.parametrize(
    ("error", "what"),
    [
        (
            InvalidPDFError("x"),
            "The PDF couldn't be read. Check that it isn't damaged, then process it again.",
        ),
        (
            InvalidCSVError("x"),
            (
                "The CSV isn't in the expected format. Expected columns: "
                "PostOne ID (0), Tracking (1), Reference (2), Name (6)."
            ),
        ),
        (
            MappingError("x"),
            (
                "Some pages didn't match a row in the CSV. Check the CSV "
                "mapping file, then process it again."
            ),
        ),
        (
            PermissionError("share gone"),
            "Can't reach this session's folder. Check the server connection.",
        ),
        (RuntimeError("boom"), "Details are in Logs."),
    ],
)
def test_a_failed_run_says_what_to_do(host, files, errors, error, what):
    tool, _pool = _ready(host, files)
    toasts = _caught(tool.toast)
    tool.start()
    tool._on_error((type(error), error, "trace"))
    tool._on_finished()
    assert errors == [("The PDF wasn't processed", what)]
    assert toasts == []
    assert tool.facts().run is None


def test_a_run_that_outlives_its_session_does_not_leave_its_result_behind(
    host, files, opened, tmp_path
):
    tool, pool = _ready(host, files)
    toasts = _caught(tool.toast)
    tool.start()
    tool.set_session(str(tmp_path / "2026-10-01_1"))
    _finish(tool, pool)
    facts = tool.facts()
    assert (facts.result, facts.has_output) == (None, False)
    assert len(toasts) == 1  # the labels were still written, and the toast says where


# --- print --------------------------------------------------------------------


def test_print_sends_the_output_with_the_reference_scopes_settings(
    host, files, opened, monkeypatch
):
    tool, pool = _ready(host, files)
    calls = []
    monkeypatch.setattr(
        reference_tool.pdf_printing, "load_print_settings", lambda scope: {"scope": scope}
    )
    monkeypatch.setattr(
        reference_tool.pdf_printing,
        "print_pdf",
        lambda parent, path, settings: calls.append((path, settings)),
    )
    tool.print_output()  # nothing to print yet
    assert calls == []
    tool.start()
    result = _finish(tool, pool)
    tool.print_output()
    assert [(str(path), settings) for path, settings in calls] == [
        (result["output_file"], {"scope": "reference_labels"})
    ]
````

- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_reference_tool.py`
Expected: an error while collecting: `ImportError: cannot import name 'reference_tool' from 'gui'`.

- [ ] **Step 3: Implement**

Create `gui/reference_tool.py`:

````python
"""Reference labels, as the Tools page runs it (phase 5 spec section 6.2).

Not a widget. It holds the two picked files and the output folder, checks a
file when it is picked, runs the stamping on a worker with counted progress
and Cancel, and prints the result. The page draws what facts() returns, worded
by gui/tools_state.py.
"""

import logging
import threading
import time
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QObject, QThreadPool, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QWidget

from gui import pdf_printing
from gui.components import show_error
from gui.tools_state import PRINT_SCOPE, PickedFile, ReferenceFacts, ToolRun, short_path
from gui.worker import Worker
from shopify_tool import pdf_processor
from shopify_tool.pdf_processor import (
    InvalidCSVError,
    InvalidPDFError,
    MappingError,
    ProcessingCancelled,
    reference_run_warning,
)

logger = logging.getLogger(__name__)

KINDS = ("pdf", "csv")
PDF_PROBLEM = (
    "This PDF can't be read",
    "Check that it isn't damaged, then choose it again.",
)
CSV_PROBLEM = (
    "This CSV has no usable rows",
    (
        "Each row needs the PostOne export's columns: PostOne ID (1st), Tracking (2nd), "
        "Reference (3rd) and Name (7th)."
    ),
)
_DIALOG = {
    "pdf": ("Select the labels PDF", "PDF Files (*.pdf)"),
    "csv": ("Select the mapping CSV", "CSV Files (*.csv);;All Files (*.*)"),
}
# Seconds between two progress pushes: a 2,000-page PDF must not redraw the
# page 4,000 times.
_REPORT_EVERY = 0.1


def _process(pdf_path, csv_path, folder, report):
    """The run, on a worker thread. Making the folder is part of it: the
    share can be slow, or gone."""
    Path(folder).mkdir(parents=True, exist_ok=True)
    return pdf_processor.process_reference_labels(
        pdf_path=pdf_path,
        csv_path=csv_path,
        output_dir=str(folder),
        progress_callback=report,
    )


class ReferenceTool(QObject):
    """The Reference labels tool: picks, one run at a time, and Print."""

    changed = Signal()
    toast = Signal(str, str)  # text, the folder to offer ("" for none)
    _progress = Signal(int, int, str)  # from the worker thread

    def __init__(self, host: QWidget, pool: QThreadPool | None = None):
        """host: the parent for dialogs and error banners. pool: where a
        run's Worker starts; the global pool when None."""
        super().__init__(host)
        self._host = host
        self._pool = pool
        self._paths: dict[str, str | None] = {"pdf": None, "csv": None}
        self._picks: dict[str, PickedFile | None] = {"pdf": None, "csv": None}
        self._folder: Path | None = None
        self._open_pdf = True
        self._run: ToolRun | None = None
        self._result: dict | None = None
        self._output: Path | None = None
        # Counts session changes, so a run that outlives its session does not
        # leave its result on the next one.
        self._generation = 0
        self._started_in = 0
        # Held until the run finishes: a Worker kept only by a local is
        # collected before its queued result arrives (see the client-load
        # worker in gui/main_window_pyside.py).
        self._worker: Worker | None = None
        self._cancel = threading.Event()
        self._last_report = 0.0
        self._progress.connect(self._on_progress)

    # --- facts ---------------------------------------------------------------

    def facts(self) -> ReferenceFacts:
        return ReferenceFacts(
            pdf=self._picks["pdf"],
            csv=self._picks["csv"],
            folder=str(self._folder) if self._folder is not None else "",
            open_pdf=self._open_pdf,
            run=self._run,
            result=self._result,
            has_output=self._output is not None,
        )

    def set_session(self, session_path: str | None) -> None:
        """Another session, or none. The picks belonged to the last one's
        batch, so they go. Touches no file."""
        self._generation += 1
        self._paths = {"pdf": None, "csv": None}
        self._picks = {"pdf": None, "csv": None}
        self._result = None
        self._output = None
        self._folder = Path(session_path) / "reference_labels" if session_path else None
        self.changed.emit()

    # --- inputs --------------------------------------------------------------

    def _editable(self) -> bool:
        return self._folder is not None and self._run is None

    def choose(self, kind: str) -> None:
        if kind not in KINDS or not self._editable():
            return
        title, pattern = _DIALOG[kind]
        path, _ = QFileDialog.getOpenFileName(self._host, title, "", pattern)
        if path:
            self.load(kind, path)

    def load(self, kind: str, path: str) -> None:
        """Take a picked file and check it now, so a bad one is flagged under
        its own field instead of after Process."""
        if kind not in KINDS or not self._editable():
            return
        # ponytail: both checks read the file on the GUI thread. It was just
        # picked in a dialog, so it is normally local. Move them to a worker
        # if a pick from the share ever stalls the window.
        name = Path(path).name
        try:
            if kind == "pdf":
                count = pdf_processor.pdf_page_count(path)
            else:
                count = pdf_processor.load_csv_mapping(path)["rows"]
            pick = PickedFile(name, count)
        except (InvalidPDFError, InvalidCSVError):
            logger.warning(f"Picked {kind} file can't be used: {path}", exc_info=True)
            pick = PickedFile(name, None, PDF_PROBLEM if kind == "pdf" else CSV_PROBLEM)
        self._paths[kind] = str(path)
        self._picks[kind] = pick
        self._drop_result()
        self.changed.emit()

    def clear(self, kind: str) -> None:
        if kind not in KINDS or not self._editable():
            return
        self._paths[kind] = None
        self._picks[kind] = None
        self._drop_result()
        self.changed.emit()

    def _drop_result(self) -> None:
        # They described the inputs before.
        self._result = None
        self._output = None

    def change_folder(self) -> None:
        if not self._editable():
            return
        chosen = QFileDialog.getExistingDirectory(
            self._host, "Select the output folder", str(self._folder)
        )
        if chosen:
            self._folder = Path(chosen)
            logger.info(f"Reference labels output folder changed: {chosen}")
            self.changed.emit()

    def set_open_pdf(self, on: bool) -> None:
        self._open_pdf = bool(on)
        self.changed.emit()

    # --- the run -------------------------------------------------------------

    def start(self) -> None:
        if not self._editable():
            return
        picks = self._picks
        if any(picks[kind] is None or picks[kind].problem is not None for kind in KINDS):
            return
        self._cancel.clear()
        self._last_report = 0.0
        self._started_in = self._generation
        self._run = ToolRun(pdf_processor.READING, 0, picks["pdf"].count or 0)
        worker = Worker(
            _process, self._paths["pdf"], self._paths["csv"], self._folder, self._report
        )
        worker.signals.result.connect(self._on_result)
        worker.signals.error.connect(self._on_error)
        worker.signals.finished.connect(self._on_finished)
        self._worker = worker
        logger.info(f"Starting reference label processing: {self._paths['pdf']}")
        self.changed.emit()
        (self._pool or QThreadPool.globalInstance()).start(worker)

    def _report(self, done: int, total: int, label: str) -> None:
        """The processor's progress callback. Runs on the worker thread, so
        it only raises or emits."""
        if self._cancel.is_set():
            raise ProcessingCancelled
        now = time.monotonic()
        if done < total and now - self._last_report < _REPORT_EVERY:
            return
        self._last_report = now
        self._progress.emit(done, total, label)

    def _on_progress(self, done: int, total: int, label: str) -> None:
        if self._run is None:
            return  # a report that arrived after the run finished
        self._run = ToolRun(label, done, total, self._run.cancelling)
        self.changed.emit()

    def cancel(self) -> None:
        """Stop at the next page. Nothing has been written, so nothing is left."""
        run = self._run
        if run is None or run.cancelling or run.label == pdf_processor.SAVING:
            return
        self._cancel.set()
        self._run = replace(run, cancelling=True)
        self.changed.emit()

    def _on_result(self, result: dict) -> None:
        output = Path(result["output_file"])
        if self._started_in == self._generation:
            self._result = result
            self._output = output
        logger.info(
            f"PDF processing complete: {result['matched']} matched, "
            f"{result['unmatched']} unmatched"
        )
        if self._open_pdf:
            self._open(output)
        # Duplicate or missing REFs stay on screen, in the footer, not in a toast.
        if reference_run_warning(result) is None:
            pages = result["pages_processed"]
            folder = str(output.parent)
            self.toast.emit(
                f"{pages:,} label{'' if pages == 1 else 's'} saved to {short_path(folder)}",
                folder,
            )

    def _on_error(self, error_info) -> None:
        _exctype, value, traceback_str = error_info
        if isinstance(value, ProcessingCancelled):
            logger.info("Reference label processing cancelled")
            self.toast.emit("Processing cancelled", "")
            return
        logger.error(f"PDF processing failed: {value}\n{traceback_str}")
        if isinstance(value, InvalidPDFError):
            what_to_do = (
                "The PDF couldn't be read. Check that it isn't damaged, "
                "then process it again."
            )
        elif isinstance(value, InvalidCSVError):
            what_to_do = (
                "The CSV isn't in the expected format. Expected columns: "
                "PostOne ID (0), Tracking (1), Reference (2), Name (6)."
            )
        elif isinstance(value, MappingError):
            what_to_do = (
                "Some pages didn't match a row in the CSV. Check the CSV "
                "mapping file, then process it again."
            )
        elif isinstance(value, OSError):
            what_to_do = "Can't reach this session's folder. Check the server connection."
        else:
            what_to_do = "Details are in Logs."
        show_error(self._host, "The PDF wasn't processed", what_to_do)

    def _on_finished(self) -> None:
        self._run = None
        self._worker = None
        self.changed.emit()

    # --- output --------------------------------------------------------------

    def _open(self, path: Path) -> None:
        if QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            logger.info(f"Opened PDF: {path}")
        else:
            logger.warning(f"Failed to open PDF: {path}")
            show_error(self._host, "The PDF didn't open", f"Open it manually: {path}")

    def print_output(self) -> None:
        if self._output is None or self._run is not None:
            return
        pdf_printing.print_pdf(
            self._host,
            self._output,
            pdf_printing.load_print_settings(PRINT_SCOPE["reference"]),
        )
````

- [ ] **Step 4: Run the tests and see them pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_reference_tool.py`
Expected: all pass (35 passed).

- [ ] **Step 5: Lint**

Run: `.venv/bin/ruff check gui/reference_tool.py tests/test_reference_tool.py`
Expected: `All checks passed!`

- [ ] **Step 6: Commit**

Message: `Reference tool: picks checked when chosen, a counted run, Cancel (phase 5 spec 6.2)`.
Add `gui/reference_tool.py` and `tests/test_reference_tool.py`.

---

### Task 8: The Barcode labels tool (`gui/barcode_tool.py`)

**Files:**
- Create: `gui/barcode_tool.py`
- Test: `tests/test_barcode_tool.py` (new)

**Interfaces:**
- Consumes: Task 2 (`packing_list_orders`, `generate_list_labels`), and from the same module `barcodes_dir(
  session_path, list_stem)`, `barcode_pdf_path(folder, list_stem)`, `qr_pdf_path(folder, list_stem)`; Task 3
  (`BarcodeFacts`, `PackingList`, `ToolRun`, `PRINT_SCOPE`, `short_path`);
  `shopify_tool.report_filters.fulfillable_only(df)`; `gui.worker.Worker`; `gui.components.ConfirmDialog.ask(
  parent, *, title, body, verb) -> bool` and `show_error`; `gui.pdf_printing` through the module.
- Produces:
  - `read_packing_lists(session_path, analysis_df) -> list[tuple[PackingList, frozenset]]`.
  - `BarcodeTool(host: QWidget, analysis: Callable[[], DataFrame | None], pool: QThreadPool | None = None)`
    with signals `changed()` and `toast(str, str)`, and methods `facts() -> BarcodeFacts`,
    `set_session(session_path)`, `reload()`, `choose(name)`, `set_option(name, on)` (`name` is `"qr"` or
    `"open_pdf"`), `start()`, `print_labels(what)` (`what` is `"labels"` or `"qr"`).
  - The module cache `_ORDERS_CACHE` (the tests clear it).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_barcode_tool.py`:

````python
"""Barcode labels as the Tools page runs it (phase 5 spec section 6.3).

No test runs a real Worker thread: the tool is given a pool that only captures
the worker, and the test calls the worker's function and the tool's slots
itself, in the order Worker emits them.
"""

import os

import pandas as pd
import pytest
from PySide6.QtWidgets import QApplication, QWidget

from gui import barcode_tool
from gui.barcode_tool import BarcodeTool, read_packing_lists
from gui.tools_state import PackingList
from shopify_tool.barcode_processor import BarcodeGenerationError


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


class Pool:
    """Captures a worker instead of running it on a thread."""

    def __init__(self):
        self.started = []

    def start(self, worker):
        self.started.append(worker)


@pytest.fixture
def host(qtbot):
    widget = QWidget()
    qtbot.addWidget(widget)
    return widget


@pytest.fixture(autouse=True)
def fresh_cache():
    barcode_tool._ORDERS_CACHE.clear()
    yield
    barcode_tool._ORDERS_CACHE.clear()


@pytest.fixture
def opened(monkeypatch):
    seen = []

    def open_url(url):
        seen.append(url.toLocalFile())
        return True

    monkeypatch.setattr(barcode_tool.QDesktopServices, "openUrl", open_url)
    return seen


@pytest.fixture
def errors(monkeypatch):
    seen = []
    monkeypatch.setattr(
        barcode_tool, "show_error", lambda _host, headline, what: seen.append((headline, what))
    )
    return seen


def _analysis():
    """Four orders: #1 and #2 Fulfillable on DHL, #3 Fulfillable on DPD, #4 blocked."""
    return pd.DataFrame(
        {
            "Order_Number": ["#1", "#1", "#2", "#3", "#4"],
            "SKU": ["A", "B", "A", "C", "A"],
            "Quantity": [1, 2, 1, 4, 1],
            "Shipping_Provider": ["DHL", "DHL", "DHL", "DPD", "DHL"],
            "Destination_Country": ["DE", "DE", "BG", "BG", "DE"],
            "Internal_Tags": ["[]", "[]", "[]", "[]", "[]"],
            "Order_Fulfillment_Status": [
                "Fulfillable",
                "Fulfillable",
                "Fulfillable",
                "Fulfillable",
                "Not Fulfillable",
            ],
        }
    )


def _write_list(session, name, orders):
    folder = session / "packing_lists"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.xlsx"
    pd.DataFrame({"Order_Number": orders}).to_excel(path, index=False)
    return path


@pytest.fixture
def session(tmp_path):
    """A session with two packing lists: DHL (#1, #2, #4) and DPD (#3)."""
    folder = tmp_path / "2026-09-30_1"
    folder.mkdir()
    _write_list(folder, "DHL", ["#1", "#1", "#2", "#4"])
    _write_list(folder, "DPD", ["#3"])
    return folder


def _tool(host, session=None, frame="default"):
    pool = Pool()
    held = {"frame": _analysis() if isinstance(frame, str) else frame}
    tool = BarcodeTool(host, lambda: held["frame"], pool)
    if session is not None:
        tool.set_session(str(session))
    return tool, pool, held


def _load(tool, pool):
    """Reload the lists as the worker would: run its function, hand back the result."""
    tool.reload()
    worker = pool.started[-1]
    tool._on_lists(worker.fn(*worker.args, **worker.kwargs))


def _loaded(host, session):
    tool, pool, held = _tool(host, session)
    _load(tool, pool)
    return tool, pool, held


def _generate(tool, pool):
    """Run the captured generation here: result, then finished."""
    worker = pool.started[-1]
    outcome = worker.fn(*worker.args, **worker.kwargs)
    tool._on_result(outcome)
    tool._on_finished()
    return outcome


def _caught(signal):
    seen = []
    signal.connect(lambda *args: seen.append(args))
    return seen


# --- reading the lists --------------------------------------------------------


def test_a_list_counts_its_fulfillable_orders(session):
    found = read_packing_lists(str(session), _analysis())
    assert [entry for entry, _orders in found] == [
        PackingList("DHL", 2, False, False),  # #4 is on the list but blocked
        PackingList("DPD", 1, False, False),
    ]
    assert found[0][1] == frozenset({"#1", "#2", "#4"})


def test_a_session_with_no_packing_lists_folder_has_none(tmp_path):
    assert read_packing_lists(str(tmp_path), _analysis()) == []


def test_with_no_analysis_the_lists_are_named_but_not_counted(session):
    found = read_packing_lists(str(session), None)
    assert [(entry.name, entry.count) for entry, _orders in found] == [("DHL", None), ("DPD", None)]


def test_a_workbook_that_cannot_be_read_is_listed_as_unreadable(session):
    (session / "packing_lists" / "Broken.xlsx").write_text("not a workbook")
    pd.DataFrame({"SKU": ["A"]}).to_excel(session / "packing_lists" / "NoOrders.xlsx", index=False)
    found = {
        entry.name: entry for entry, _orders in read_packing_lists(str(session), _analysis())
    }
    assert found["Broken"].count is None
    assert found["NoOrders"].count is None
    assert found["DHL"].count == 2


def test_excels_lock_file_is_not_a_packing_list(session):
    (session / "packing_lists" / "~$DHL.xlsx").write_text("lock")
    names = [entry.name for entry, _orders in read_packing_lists(str(session), _analysis())]
    assert names == ["DHL", "DPD"]


def test_label_pdfs_on_disk_are_seen(session):
    labels = session / "barcodes" / "DHL"
    labels.mkdir(parents=True)
    (labels / "DHL_barcodes.pdf").write_bytes(b"%PDF")
    (labels / "DHL_qr_labels.pdf").write_bytes(b"%PDF")
    found = {
        entry.name: entry for entry, _orders in read_packing_lists(str(session), _analysis())
    }
    assert (found["DHL"].has_labels, found["DHL"].has_qr) == (True, True)
    assert (found["DPD"].has_labels, found["DPD"].has_qr) == (False, False)


def test_an_unchanged_workbook_is_read_once(session, monkeypatch):
    reads = []
    real = barcode_tool.packing_list_orders

    def counting(path):
        reads.append(os.path.basename(str(path)))
        return real(path)

    monkeypatch.setattr(barcode_tool, "packing_list_orders", counting)
    read_packing_lists(str(session), _analysis())
    read_packing_lists(str(session), _analysis())
    assert sorted(reads) == ["DHL.xlsx", "DPD.xlsx"]

    # A list written again is read again.
    path = _write_list(session, "DPD", ["#3", "#2"])
    os.utime(path, (path.stat().st_atime, path.stat().st_mtime + 5))
    found = {
        entry.name: entry for entry, _orders in read_packing_lists(str(session), _analysis())
    }
    assert reads.count("DPD.xlsx") == 2
    assert found["DPD"].count == 2


# --- the tool: session and lists ---------------------------------------------


def test_a_new_tool_has_nothing(host):
    tool, _pool, _held = _tool(host)
    facts = tool.facts()
    assert (facts.lists, facts.selected, facts.folder, facts.loading) == ((), "", "", False)
    assert (facts.qr, facts.open_pdf, facts.run, facts.result) == (False, True, None, None)


def test_reload_without_a_session_does_nothing(host):
    tool, pool, _held = _tool(host)
    tool.reload()
    assert pool.started == []


def test_reload_reads_on_a_worker_and_selects_the_first_list(host, session):
    tool, pool, _held = _tool(host, session)
    seen = _caught(tool.changed)
    tool.reload()
    assert tool.facts().loading is True
    assert len(pool.started) == 1 and len(seen) == 1
    tool.reload()  # already loading
    assert len(pool.started) == 1

    worker = pool.started[-1]
    tool._on_lists(worker.fn(*worker.args, **worker.kwargs))
    facts = tool.facts()
    assert facts.loading is False
    assert [entry.name for entry in facts.lists] == ["DHL", "DPD"]
    assert facts.selected == "DHL"
    assert facts.folder == str(session / "barcodes" / "DHL")
    assert facts.analysed is True


def test_a_reload_keeps_the_selection_when_the_list_is_still_there(host, session):
    tool, pool, _held = _loaded(host, session)
    tool.choose("DPD")
    _load(tool, pool)
    assert tool.facts().selected == "DPD"


def test_a_reload_moves_to_the_first_list_when_the_selected_one_is_gone(host, session):
    tool, pool, _held = _loaded(host, session)
    tool.choose("DPD")
    (session / "packing_lists" / "DPD.xlsx").unlink()
    _load(tool, pool)
    assert tool.facts().selected == "DHL"


def test_lists_that_arrive_for_a_session_the_operator_left_are_dropped(host, session, tmp_path):
    tool, pool, _held = _tool(host, session)
    tool.reload()
    worker = pool.started[-1]
    other = tmp_path / "2026-10-01_1"
    other.mkdir()
    tool.set_session(str(other))
    tool._on_lists(worker.fn(*worker.args, **worker.kwargs))
    assert tool.facts().lists == ()
    # ...and the new session can load at once.
    tool.reload()
    assert len(pool.started) == 2


def test_with_no_analysis_the_facts_say_so(host, session):
    tool, pool, _held = _tool(host, session, frame=None)
    _load(tool, pool)
    facts = tool.facts()
    assert facts.analysed is False
    assert [entry.count for entry in facts.lists] == [None, None]


def test_a_failed_reload_stops_loading_and_says_so(host, session, errors):
    tool, _pool, _held = _tool(host, session)
    tool.reload()
    tool._on_lists_failed((OSError, OSError("share gone"), "trace"))
    assert tool.facts().loading is False
    assert errors == [
        ("The packing lists weren't read", "Check the server connection, then Refresh.")
    ]


def test_choose_selects_a_list_that_exists(host, session):
    tool, _pool, _held = _loaded(host, session)
    seen = _caught(tool.changed)
    tool.choose("DPD")
    tool.choose("Royal Mail")
    tool.choose("DPD")
    assert tool.facts().selected == "DPD"
    assert len(seen) == 1


def test_options(host, session):
    tool, _pool, _held = _loaded(host, session)
    tool.set_option("qr", True)
    tool.set_option("open_pdf", False)
    tool.set_option("locked", True)
    facts = tool.facts()
    assert (facts.qr, facts.open_pdf) == (True, False)


def test_a_session_change_forgets_the_lists(host, session):
    tool, _pool, _held = _loaded(host, session)
    tool.set_session(None)
    facts = tool.facts()
    assert (facts.lists, facts.selected, facts.folder) == ((), "", "")


# --- the run ------------------------------------------------------------------


def test_start_does_nothing_without_a_list_with_orders(host, session):
    tool, pool, held = _tool(host, session)
    tool.start()  # nothing loaded
    assert pool.started == []

    _load(tool, pool)
    before = len(pool.started)
    held["frame"] = None
    tool.start()  # no analysis
    assert len(pool.started) == before


def test_start_writes_the_selected_lists_fulfillable_orders(host, session, opened):
    tool, pool, _held = _loaded(host, session)
    toasts = _caught(tool.toast)
    tool.start()
    run = tool.facts().run
    assert run.label == "Preparing 2 labels…" and run.total == 0
    tool.start()  # a second click while running
    assert len(pool.started) == 2  # the list load, and one generation

    tool._on_progress("Writing 2 barcode labels…")
    assert tool.facts().run.label == "Writing 2 barcode labels…"

    outcome = _generate(tool, pool)
    folder = str(session / "barcodes" / "DHL")
    assert (outcome["list"], outcome["folder"], outcome["labels"]) == ("DHL", folder, 2)
    assert os.path.exists(outcome["pdf"])

    facts = tool.facts()
    assert facts.run is None
    assert facts.result == outcome
    assert facts.lists[0] == PackingList("DHL", 2, True, False)
    assert opened == [outcome["pdf"]]
    assert toasts == [(f"2 barcode labels saved to …{os.sep}barcodes{os.sep}DHL", folder)]


def test_with_qr_both_pdfs_are_written_opened_and_named_in_the_toast(host, session, opened):
    tool, pool, _held = _loaded(host, session)
    tool.set_option("qr", True)
    toasts = _caught(tool.toast)
    tool.start()
    outcome = _generate(tool, pool)
    assert opened == [outcome["pdf"], outcome["qr_pdf"]]
    assert toasts[0][0] == (
        f"2 barcode labels saved to …{os.sep}barcodes{os.sep}DHL. QR labels too."
    )
    assert tool.facts().lists[0].has_qr is True


def test_with_open_pdf_off_nothing_is_opened(host, session, opened):
    tool, pool, _held = _loaded(host, session)
    tool.set_option("open_pdf", False)
    tool.start()
    _generate(tool, pool)
    assert opened == []


def test_the_list_cannot_change_while_it_runs(host, session):
    tool, _pool, _held = _loaded(host, session)
    tool.start()
    tool.choose("DPD")
    assert tool.facts().selected == "DHL"


def test_replacing_existing_labels_asks_first(host, session, opened, monkeypatch):
    tool, pool, _held = _loaded(host, session)
    tool.start()
    _generate(tool, pool)
    started = len(pool.started)

    asked = []

    def ask(parent, *, title, body, verb):
        asked.append((title, body, verb))
        return False

    monkeypatch.setattr(barcode_tool.ConfirmDialog, "ask", staticmethod(ask))
    tool.start()
    assert asked == [
        (
            "Replace barcodes for DHL?",
            "The existing PDF is overwritten with 2 new barcodes. This cannot be undone.",
            "Replace barcodes",
        )
    ]
    assert len(pool.started) == started  # No: nothing started
    assert tool.facts().run is None

    monkeypatch.setattr(barcode_tool.ConfirmDialog, "ask", staticmethod(lambda *a, **k: True))
    tool.start()
    assert len(pool.started) == started + 1


def test_order_numbers_that_cannot_be_encoded_stay_in_the_result(host, tmp_path, opened):
    session = tmp_path / "2026-09-30_1"
    session.mkdir()
    _write_list(session, "DHL", ["#1", "!!!"])
    frame = _analysis()
    frame.loc[2, "Order_Number"] = "!!!"
    tool, pool, _held = _tool(host, session, frame=frame)
    _load(tool, pool)
    tool.start()
    outcome = _generate(tool, pool)
    assert (outcome["labels"], outcome["failed"]) == (1, 1)
    assert tool.facts().result == outcome


def test_a_render_failure_shows_the_error_and_no_toast(host, session, errors, monkeypatch):
    tool, _pool, _held = _loaded(host, session)
    toasts = _caught(tool.toast)
    tool.start()
    error = BarcodeGenerationError("renderer down")
    tool._on_error((type(error), error, "trace"))
    tool._on_finished()
    assert errors == [("The barcode PDF wasn't created", "Details are in Logs.")]
    assert toasts == []
    facts = tool.facts()
    assert facts.run is None and facts.result is None
    assert facts.lists[0].has_labels is False


def test_a_run_that_outlives_its_session_still_toasts_but_keeps_no_result(
    host, session, opened, tmp_path
):
    tool, pool, _held = _loaded(host, session)
    toasts = _caught(tool.toast)
    tool.start()
    other = tmp_path / "2026-10-01_1"
    other.mkdir()
    tool.set_session(str(other))
    outcome = _generate(tool, pool)
    # Written where the run was started, not into the new session.
    assert outcome["folder"] == str(session / "barcodes" / "DHL")
    assert tool.facts().result is None
    assert len(toasts) == 1


def test_a_late_progress_report_after_the_run_is_ignored(host, session, opened):
    tool, pool, _held = _loaded(host, session)
    tool.start()
    _generate(tool, pool)
    tool._on_progress("Writing 2 QR labels…")
    assert tool.facts().run is None


# --- print --------------------------------------------------------------------


def test_print_sends_the_selected_lists_pdf_with_the_barcode_scopes_settings(
    host, session, monkeypatch
):
    tool, _pool, _held = _loaded(host, session)
    calls = []
    monkeypatch.setattr(
        barcode_tool.pdf_printing, "load_print_settings", lambda scope: {"scope": scope}
    )
    monkeypatch.setattr(
        barcode_tool.pdf_printing,
        "print_pdf",
        lambda parent, path, settings: calls.append((str(path), settings)),
    )
    tool.print_labels("labels")
    tool.choose("DPD")
    tool.print_labels("qr")
    assert calls == [
        (str(session / "barcodes" / "DHL" / "DHL_barcodes.pdf"), {"scope": "barcode_generator"}),
        (str(session / "barcodes" / "DPD" / "DPD_qr_labels.pdf"), {"scope": "barcode_generator"}),
    ]


def test_print_does_nothing_with_no_list(host, monkeypatch):
    tool, _pool, _held = _tool(host)
    calls = []
    monkeypatch.setattr(barcode_tool.pdf_printing, "print_pdf", lambda *a: calls.append(a))
    tool.print_labels("labels")
    assert calls == []
````

- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_barcode_tool.py`
Expected: an error while collecting: `ImportError: cannot import name 'barcode_tool' from 'gui'`.

- [ ] **Step 3: Implement**

Create `gui/barcode_tool.py`:

````python
"""Barcode labels, as the Tools page runs it (phase 5 spec section 6.3).

Not a widget. It reads the session's packing lists on a worker, holds which
one is selected, writes that list's label PDFs on a worker, and prints them.
The page draws what facts() returns, worded by gui/tools_state.py.
"""

import logging
import os
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QObject, QThreadPool, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QWidget

from gui import pdf_printing
from gui.components import ConfirmDialog, show_error
from gui.tools_state import PRINT_SCOPE, BarcodeFacts, PackingList, ToolRun, short_path
from gui.worker import Worker
from shopify_tool.barcode_processor import (
    barcode_pdf_path,
    barcodes_dir,
    generate_list_labels,
    packing_list_orders,
    qr_pdf_path,
)
from shopify_tool.report_filters import fulfillable_only

logger = logging.getLogger(__name__)

# path -> (mtime, order numbers). The share is slow and the Tools page reloads
# its lists every time it is shown, so a workbook is read once until it changes.
_ORDERS_CACHE: dict[str, tuple[float, frozenset]] = {}


def _orders(path: Path) -> frozenset:
    key = str(path)
    mtime = os.path.getmtime(path)
    hit = _ORDERS_CACHE.get(key)
    if hit is not None and hit[0] == mtime:
        return hit[1]
    orders = packing_list_orders(path)
    _ORDERS_CACHE[key] = (mtime, orders)
    return orders


def read_packing_lists(session_path, analysis_df) -> list[tuple[PackingList, frozenset]]:
    """The session's packing lists, each with its order numbers.

    Runs on a worker: it reads every workbook and looks for each list's label
    PDFs on the share. A list's count is its Fulfillable orders, or None when
    its workbook can't be read or there is no analysis to count against.
    """
    folder = Path(session_path) / "packing_lists"
    if not folder.is_dir():
        return []
    fulfillable = None
    if analysis_df is not None:
        base = fulfillable_only(analysis_df)
        if "Order_Number" in base.columns:
            fulfillable = base["Order_Number"]

    found = []
    # "~$DHL.xlsx" is the lock file Excel leaves beside an open workbook.
    paths = [p for p in folder.glob("*.xlsx") if not p.name.startswith("~$")]
    for path in sorted(paths, key=lambda p: p.stem):
        name = path.stem
        orders, count = frozenset(), None
        try:
            orders = _orders(path)
            if fulfillable is not None:
                count = int(fulfillable[fulfillable.isin(orders)].nunique())
        except Exception:
            logger.exception(f"Failed to read packing list {path}")
            orders, count = frozenset(), None
        labels = barcodes_dir(session_path, name)
        found.append(
            (
                PackingList(
                    name,
                    count,
                    has_labels=barcode_pdf_path(labels, name).exists(),
                    has_qr=qr_pdf_path(labels, name).exists(),
                ),
                orders,
            )
        )
    return found


def _read(session_path, analysis_df):
    """The worker's function: the session comes back with its lists, so a
    result for a session the operator has left can be told apart."""
    return session_path, read_packing_lists(session_path, analysis_df)


class BarcodeTool(QObject):
    """The Barcode labels tool: the lists, one run at a time, and Print."""

    changed = Signal()
    toast = Signal(str, str)  # text, the folder to offer ("" for none)
    _progress = Signal(str)  # from the worker thread

    def __init__(
        self,
        host: QWidget,
        analysis: Callable[[], object],
        pool: QThreadPool | None = None,
    ):
        """host: the parent for dialogs and error banners. analysis: returns
        the window's analysis frame, or None. pool: where a Worker starts;
        the global pool when None."""
        super().__init__(host)
        self._host = host
        self._analysis = analysis
        self._pool = pool
        self._session: str | None = None
        self._lists: list[PackingList] = []
        self._orders: dict[str, frozenset] = {}
        self._loading = False
        self._analysed = True
        self._selected = ""
        self._qr = False
        self._open_pdf = True
        self._run: ToolRun | None = None
        self._result: dict | None = None
        # Held until each finishes: a Worker kept only by a local is collected
        # before its queued result arrives (see gui/main_window_pyside.py).
        self._list_worker: Worker | None = None
        self._run_worker: Worker | None = None
        self._progress.connect(self._on_progress)

    def _start(self, worker: Worker) -> None:
        (self._pool or QThreadPool.globalInstance()).start(worker)

    # --- facts ---------------------------------------------------------------

    def facts(self) -> BarcodeFacts:
        folder = ""
        if self._session and self._selected:
            folder = str(barcodes_dir(self._session, self._selected))
        return BarcodeFacts(
            lists=tuple(self._lists),
            loading=self._loading,
            analysed=self._analysed,
            selected=self._selected,
            folder=folder,
            qr=self._qr,
            open_pdf=self._open_pdf,
            run=self._run,
            result=self._result,
        )

    def _entry(self, name: str) -> PackingList | None:
        return next((entry for entry in self._lists if entry.name == name), None)

    def set_session(self, session_path: str | None) -> None:
        """Another session, or none: its lists are not this one's. Touches no file."""
        self._session = str(session_path) if session_path else None
        self._lists = []
        self._orders = {}
        self._selected = ""
        self._result = None
        self._loading = False
        self.changed.emit()

    # --- the lists -----------------------------------------------------------

    def reload(self) -> None:
        """Read the session's packing lists again, off the GUI thread."""
        if not self._session or self._loading:
            return
        frame = self._analysis()
        self._analysed = frame is not None
        self._loading = True
        worker = Worker(_read, self._session, frame)
        worker.signals.result.connect(self._on_lists)
        worker.signals.error.connect(self._on_lists_failed)
        self._list_worker = worker
        self.changed.emit()
        self._start(worker)

    def _on_lists(self, payload) -> None:
        session, found = payload
        if session != self._session:
            return  # the operator moved to another session while it loaded
        self._loading = False
        self._list_worker = None
        self._lists = [entry for entry, _orders in found]
        self._orders = {entry.name: orders for entry, orders in found}
        names = [entry.name for entry in self._lists]
        if self._selected not in names:
            self._selected = names[0] if names else ""
            self._result = None
        self.changed.emit()

    def _on_lists_failed(self, error_info) -> None:
        _exctype, value, traceback_str = error_info
        logger.error(f"Reading packing lists failed: {value}\n{traceback_str}")
        self._loading = False
        self._list_worker = None
        self.changed.emit()
        show_error(
            self._host,
            "The packing lists weren't read",
            "Check the server connection, then Refresh.",
        )

    def choose(self, name: str) -> None:
        if self._run is not None or self._entry(name) is None or name == self._selected:
            return
        self._selected = name
        self._result = None
        self.changed.emit()

    def set_option(self, name: str, on: bool) -> None:
        if name == "qr":
            self._qr = bool(on)
        elif name == "open_pdf":
            self._open_pdf = bool(on)
        else:
            return
        self.changed.emit()

    # --- the run -------------------------------------------------------------

    def start(self) -> None:
        if self._run is not None or not self._session:
            return
        entry = self._entry(self._selected)
        frame = self._analysis()
        if entry is None or not entry.count or frame is None:
            return
        folder = barcodes_dir(self._session, entry.name)
        if barcode_pdf_path(folder, entry.name).exists() and not ConfirmDialog.ask(
            self._host,
            title=f"Replace barcodes for {entry.name}?",
            body=(
                f"The existing PDF is overwritten with {entry.count} new barcodes. "
                "This cannot be undone."
            ),
            verb="Replace barcodes",
        ):
            return
        base = fulfillable_only(frame)
        rows = base[base["Order_Number"].isin(self._orders.get(entry.name, frozenset()))].copy()
        if rows.empty:
            logger.warning(f"No Fulfillable orders left for packing list {entry.name!r}")
            return
        # The folder and the name go in as arguments: a session change during
        # the run cannot redirect it.
        worker = Worker(
            generate_list_labels,
            rows,
            folder,
            entry.name,
            qr=self._qr,
            progress=self._progress.emit,
        )
        worker.signals.result.connect(self._on_result)
        worker.signals.error.connect(self._on_error)
        worker.signals.finished.connect(self._on_finished)
        self._run_worker = worker
        self._run = ToolRun(f"Preparing {entry.count:,} labels…")
        logger.info(f"Started barcode generation for packing list {entry.name!r}")
        self.changed.emit()
        self._start(worker)

    def _on_progress(self, label: str) -> None:
        if self._run is None:
            return  # a report that arrived after the run finished
        self._run = ToolRun(label)
        self.changed.emit()

    def _on_result(self, outcome: dict) -> None:
        name, folder = outcome["list"], outcome["folder"]
        ours = bool(self._session) and str(barcodes_dir(self._session, name)) == folder
        if ours:
            self._result = outcome
            self._lists = [
                replace(
                    entry,
                    has_labels=entry.has_labels or bool(outcome["pdf"]),
                    has_qr=entry.has_qr or bool(outcome["qr_pdf"]),
                )
                if entry.name == name
                else entry
                for entry in self._lists
            ]
        if self._open_pdf:
            for path in (outcome["pdf"], outcome["qr_pdf"]):
                if path:
                    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        if outcome["pdf"]:
            labels = outcome["labels"]
            text = (
                f"{labels:,} barcode label{'' if labels == 1 else 's'} "
                f"saved to {short_path(folder)}"
            )
            if outcome["qr_pdf"]:
                text += ". QR labels too."
            self.toast.emit(text, folder)

    def _on_error(self, error_info) -> None:
        _exctype, value, traceback_str = error_info
        logger.error(f"Barcode generation failed: {value}\n{traceback_str}")
        show_error(self._host, "The barcode PDF wasn't created", "Details are in Logs.")

    def _on_finished(self) -> None:
        self._run = None
        self._run_worker = None
        self.changed.emit()

    # --- output --------------------------------------------------------------

    def print_labels(self, what: str) -> None:
        if self._run is not None or not self._session or not self._selected:
            return
        folder = barcodes_dir(self._session, self._selected)
        path_for = qr_pdf_path if what == "qr" else barcode_pdf_path
        pdf_printing.print_pdf(
            self._host,
            path_for(folder, self._selected),
            pdf_printing.load_print_settings(PRINT_SCOPE["barcode"]),
        )
````

- [ ] **Step 4: Run the tests and see them pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_barcode_tool.py`
Expected: all pass (30 passed). The runs write real PDFs through WeasyPrint.

- [ ] **Step 5: Lint**

Run: `.venv/bin/ruff check gui/barcode_tool.py tests/test_barcode_tool.py`
Expected: `All checks passed!`

- [ ] **Step 6: Commit**

Message: `Barcode tool: lists read on a worker, labels rendered off the GUI thread (phase 5 spec 6.3)`.
Add `gui/barcode_tool.py` and `tests/test_barcode_tool.py`.

---

### Task 9: The widget hosts the page, the shell follows, and the Qt widgets go

**Files:**
- Create (replace the whole file): `gui/tools_widget.py`
- Modify: `gui/ui_manager.py`, `gui/main_window_pyside.py`, `gui/pdf_printing.py`,
  `gui/components/__init__.py`, `tests/conftest.py`, `tests/test_pdf_printing.py`,
  `tests/test_reports_sku_labels_removed.py`, `tests/test_shell.py` (append), `tests/test_toast_router.py`
- Create: `tests/test_tools_widget.py`
- Delete: `gui/reference_labels_widget.py`, `gui/barcode_generator_widget.py`,
  `gui/components/print_options.py`, `tests/test_tools_cards.py`, `tests/test_tools_theme.py`,
  `tests/test_reference_labels_widget.py`, `tests/test_barcode_generator_widget.py`,
  `tests/test_print_options.py`, `tests/test_print_summary.py`

**What replaces each deleted test file:**

| Deleted | Its behaviour is now pinned by |
|---|---|
| `test_tools_cards.py` (the two cards, no-session copy, readiness) | `test_tools_state.py`, `test_tools_page.py` |
| `test_tools_theme.py` (the Qt cards in both themes) | `test_tools_page.py` (tokens through Chromium), `test_web_kit.py` |
| `test_reference_labels_widget.py` | `test_reference_tool.py` |
| `test_barcode_generator_widget.py` (render failure, QR, auto-open, the log line, a list changed mid-run) | `test_barcode_processor.py` (`TestGenerateListLabels`), `test_barcode_tool.py` |
| `test_print_options.py`, `test_print_summary.py` | `test_tools_state.py` (the print block, the summary, `apply_print_edit`), `test_tools_widget.py` (saving) |

**Interfaces:**
- Consumes: `mount_tools_page` and `TOOLS` (Task 4); `tools_state`, `apply_print_edit`, `PrintFacts`,
  `PRINT_SCOPE` (Task 3); `ReferenceTool` (Task 7); `BarcodeTool` (Task 8); `gui.setup_state.SessionFacts`;
  `gui.components.toast(source, text)`; `gui.pdf_printing.load_print_settings(scope)` and
  `save_print_settings(scope, settings)` through the module. From the main window: `session_path`,
  `session_facts`, `current_client_id`, `analysis_results_df`.
- Produces: `ToolsWidget(main_window, parent=None, pool=None)` with `view`, `bridge`, `reference`, `barcode`,
  `sync()`, and the signals `new_session_requested()` and `recent_requested()`; the module function
  `installed_printers() -> tuple[str, ...]`. In `UIManager`: `refresh_tools()`. In `MainWindow`: `web_toast`
  answers tab 4.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tools_widget.py`:

````python
"""The Tools screen's widget: the view, the wiring, sync() (phase 5 spec 6.1).

The page itself is tested in test_tools_page.py and the tools in
test_reference_tool.py and test_barcode_tool.py. Here: the widget joins them.
"""

from datetime import datetime
from types import SimpleNamespace

import pytest
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QFileDialog

from gui import tools_widget
from gui.setup_state import SessionFacts
from gui.tools_widget import ToolsWidget


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


class Pool:
    """Captures a worker instead of running it on a thread."""

    def __init__(self):
        self.started = []

    def start(self, worker):
        self.started.append(worker)


@pytest.fixture
def window():
    """What ToolsWidget reads from the main window."""
    return SimpleNamespace(
        session_path=None,
        session_facts=None,
        current_client_id="ACME",
        analysis_results_df=None,
    )


@pytest.fixture
def tools(qtbot, window, print_settings_store, monkeypatch):
    monkeypatch.setattr(tools_widget, "installed_printers", lambda: ("Zebra ZD421",))
    widget = ToolsWidget(window, pool=Pool())
    qtbot.addWidget(widget)
    return widget


@pytest.fixture
def session(tmp_path):
    folder = tmp_path / "2026-09-30_1"
    (folder / "packing_lists").mkdir(parents=True)
    return folder


def _raised(bridge):
    seen = []
    bridge.toastRaised.connect(lambda text, action: seen.append((text, action)))
    return seen


def test_it_hosts_one_web_view_and_starts_on_the_banner(tools):
    assert tools.findChildren(QWebEngineView) == [tools.view]
    state = tools.bridge.state
    assert state["banner"] is True
    assert state["session"] == {}
    assert state["reference"]["quiet"] is True


def test_the_state_carries_this_pcs_printers_and_saved_settings(
    qtbot, window, print_settings_store, monkeypatch
):
    print_settings_store["barcode_generator"] = {
        "print_mode": "raw_zpl",
        "raw_zpl_target": "Zebra ZD421",
        "raw_zpl_rotate": True,
        "raw_zpl_invert": False,
        "raw_zpl_label_width_mm": 68.0,
        "raw_zpl_label_height_mm": 38.0,
        "driver_printer_name": "",
    }
    monkeypatch.setattr(tools_widget, "installed_printers", lambda: ("Zebra ZD421", "HP"))
    widget = ToolsWidget(window, pool=Pool())
    qtbot.addWidget(widget)
    block = widget.bridge.state["barcode"]["print"]
    assert block["mode"] == "raw_zpl"
    assert block["setup"]["summary"] == "68 × 38 mm, rotated 90°"
    assert [p["value"] for p in block["printers"]] == ["Zebra ZD421", "HP"]
    assert widget.bridge.state["reference"]["print"]["mode"] == "driver"


def test_sync_hands_a_new_session_to_both_tools(tools, window, session):
    window.session_path = str(session)
    tools.sync()
    state = tools.bridge.state
    assert state["banner"] is False
    assert state["session"] == {"name": "2026-09-30_1", "meta": "ACME"}
    assert state["reference"]["folder"]["title"] == str(session / "reference_labels")
    assert tools.barcode.facts().lists == ()


def test_the_page_head_uses_the_windows_session_facts_when_they_are_this_sessions(
    tools, window, session
):
    opened = datetime.now().astimezone().replace(hour=14, minute=2)
    window.session_path = str(session)
    window.session_facts = SessionFacts("2026-09-30_1", opened, None)
    tools.sync()
    assert tools.bridge.state["session"]["meta"] == "ACME · opened 14:02"

    # Facts read for another session say nothing about this one.
    window.session_facts = SessionFacts("2026-09-29_2", opened, None)
    tools.sync()
    assert tools.bridge.state["session"]["meta"] == "ACME"


def test_sync_with_the_same_session_keeps_the_picks(tools, window, session, tmp_path, monkeypatch):
    window.session_path = str(session)
    tools.sync()
    csv = tmp_path / "refs.csv"
    csv.write_text("a,b,c,d,e,f,g\n,,REF-1,,,,Acme\n")
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", staticmethod(lambda *a: (str(csv), ""))
    )
    tools.bridge.chooseFile("csv")
    assert tools.bridge.state["reference"]["csv"]["meta"] == "1 row"

    tools.sync()  # the shell calls this on every refresh
    assert tools.bridge.state["reference"]["csv"]["meta"] == "1 row"

    tools.bridge.clearFile("csv")
    assert tools.bridge.state["reference"]["csv"] == {}


def test_a_hidden_page_does_not_read_the_share_when_the_session_changes(
    tools, window, session
):
    window.session_path = str(session)
    tools.sync()
    assert tools.barcode._pool.started == []


def test_showing_the_page_reads_the_packing_lists(tools, window, session, qtbot):
    window.session_path = str(session)
    tools.show()
    qtbot.waitExposed(tools)
    assert len(tools.barcode._pool.started) == 1
    assert tools.bridge.state["barcode"]["list"]["placeholder"] == "Reading packing lists…"


def test_a_session_opened_while_the_page_shows_reads_its_lists(tools, window, session, qtbot):
    tools.show()
    qtbot.waitExposed(tools)
    assert tools.barcode._pool.started == []  # no session yet
    window.session_path = str(session)
    tools.sync()
    assert len(tools.barcode._pool.started) == 1


def test_a_print_edit_is_saved_for_this_pc_and_pushed(tools, print_settings_store):
    tools.bridge.setPrint("barcode", "mode", "raw_zpl")
    tools.bridge.setPrint("barcode", "printer", "Zebra ZD421")
    tools.bridge.setPrint("barcode", "width", 68)
    saved = print_settings_store["barcode_generator"]
    assert saved["print_mode"] == "raw_zpl"
    assert saved["raw_zpl_target"] == "Zebra ZD421"
    assert saved["raw_zpl_label_width_mm"] == 68.0
    assert "reference_labels" not in print_settings_store
    block = tools.bridge.state["barcode"]["print"]
    assert block["mode"] == "raw_zpl"
    assert block["printer"]["label"] == "Zebra ZD421"


def test_a_print_edit_of_the_wrong_type_saves_nothing(tools, print_settings_store):
    before = tools.bridge.state
    tools.bridge.setPrint("barcode", "width", "wide")
    tools.bridge.setPrint("reference", "mode", "fax")
    tools.bridge.setPrint("reference", "rotate", 1)
    assert print_settings_store == {}
    assert tools.bridge.state == before


def test_options_reach_their_tool(tools):
    tools.bridge.setOption("barcode", "qr", True)
    tools.bridge.setOption("barcode", "open_pdf", False)
    tools.bridge.setOption("reference", "open_pdf", False)
    state = tools.bridge.state
    assert (state["barcode"]["qr"], state["barcode"]["open_pdf"]) == (True, False)
    assert state["reference"]["open_pdf"] is False


def test_run_cancel_and_print_reach_the_right_tool(tools, monkeypatch):
    calls = []
    monkeypatch.setattr(tools.reference, "start", lambda: calls.append("reference.start"))
    monkeypatch.setattr(tools.barcode, "start", lambda: calls.append("barcode.start"))
    monkeypatch.setattr(tools.reference, "print_output", lambda: calls.append("reference.print"))
    monkeypatch.setattr(
        tools.barcode, "print_labels", lambda what: calls.append(f"barcode.print:{what}")
    )
    tools.bridge.run("reference")
    tools.bridge.run("barcode")
    tools.bridge.printLabels("reference", "labels")
    tools.bridge.printLabels("barcode", "labels")
    tools.bridge.printLabels("barcode", "qr")
    assert calls == [
        "reference.start",
        "barcode.start",
        "reference.print",
        "barcode.print:labels",
        "barcode.print:qr",
    ]


def test_a_tools_change_is_pushed(tools, window, session):
    window.session_path = str(session)
    tools.sync()
    tools.reference.set_open_pdf(False)
    assert tools.bridge.state["reference"]["open_pdf"] is False


def test_a_done_toast_while_tools_shows_offers_open_folder(tools, qtbot, monkeypatch, tmp_path):
    opened = []
    monkeypatch.setattr(
        tools_widget.QDesktopServices, "openUrl", lambda url: opened.append(url.toLocalFile())
    )
    tools.show()
    qtbot.waitExposed(tools)
    seen = _raised(tools.bridge)

    tools.bridge.openFolder()  # nothing finished yet
    assert opened == []

    tools.barcode.toast.emit("2 barcode labels saved to …/barcodes/DHL", str(tmp_path))
    assert seen == [("2 barcode labels saved to …/barcodes/DHL", True)]
    tools.bridge.openFolder()
    assert opened == [str(tmp_path)]


def test_a_done_toast_while_another_screen_shows_goes_to_the_router(tools, monkeypatch, tmp_path):
    routed = []
    monkeypatch.setattr(tools_widget, "toast", lambda source, text: routed.append(text))
    seen = _raised(tools.bridge)
    tools.reference.toast.emit("2 labels saved to …/reference_labels", str(tmp_path))
    assert routed == ["2 labels saved to …/reference_labels"]
    assert seen == []


def test_a_toast_with_no_folder_goes_to_the_router_even_on_tools(tools, qtbot, monkeypatch):
    routed = []
    monkeypatch.setattr(tools_widget, "toast", lambda source, text: routed.append(text))
    tools.show()
    qtbot.waitExposed(tools)
    tools.reference.toast.emit("Processing cancelled", "")
    assert routed == ["Processing cancelled"]


def test_the_banners_two_requests_are_passed_on(tools):
    new, recent = [], []
    tools.new_session_requested.connect(lambda: new.append(1))
    tools.recent_requested.connect(lambda: recent.append(1))
    tools.bridge.newSession()
    tools.bridge.openRecent()
    assert (new, recent) == ([1], [1])
````

Append to `tests/test_shell.py`:

````python
def test_tools_is_one_web_view(main_window):
    """Phase 5 spec section 6.4: tab 4 holds the Tools page and nothing else."""
    from PySide6.QtWebEngineWidgets import QWebEngineView

    from gui.tools_widget import ToolsWidget

    tab = main_window.main_tabs.widget(4)
    assert isinstance(tab, ToolsWidget)
    assert tab is main_window.tools_widget
    assert tab.findChildren(QWebEngineView) == [tab.view]
    margins = tab.layout().contentsMargins()
    assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (0, 0, 0, 0)


def test_tools_takes_the_page_area_to_its_edges(main_window):
    main_window.resize(1366, 768)
    main_window.main_tabs.setCurrentIndex(4)
    QApplication.processEvents()
    margins = main_window.page_area.layout().contentsMargins()
    assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (0, 0, 0, 0)
    assert main_window.main_tabs.width() == 1166


def test_the_bar_leaves_the_session_chip_to_the_setup_and_tools_page_heads(main_window):
    from gui.components import BarState

    main_window.command_bar.set_state(BarState.SESSION)
    main_window.command_bar.set_session_text("2026-09-30_1")
    for index, shown in ((0, False), (1, True), (2, True), (3, True), (4, False)):
        main_window.main_tabs.setCurrentIndex(index)
        QApplication.processEvents()
        assert main_window.command_bar.session_chip.isVisible() is shown, index


def test_a_session_change_reaches_the_tools_page(main_window, tmp_path):
    """refresh_setup() is where every session change passes; Tools follows it."""
    state = main_window.tools_widget.bridge.state
    assert state["banner"] is True and state["session"] == {}

    session = tmp_path / "2026-09-30_1"
    session.mkdir()
    main_window.session_path = str(session)
    main_window.ui_manager.refresh_setup()

    state = main_window.tools_widget.bridge.state
    assert state["banner"] is False
    assert state["session"]["name"] == "2026-09-30_1"
    assert state["reference"]["folder"]["title"] == str(session / "reference_labels")

    main_window.session_path = None
    main_window.ui_manager.refresh_setup()
    assert main_window.tools_widget.bridge.state["banner"] is True


def test_the_tools_banner_reaches_new_session_and_the_recent_menu(main_window, monkeypatch):
    calls = []
    monkeypatch.setattr(
        main_window.actions_handler, "create_new_session", lambda: calls.append("new")
    )
    monkeypatch.setattr(
        main_window.command_bar.session_button, "showMenu", lambda: calls.append("recent")
    )
    main_window.tools_widget.bridge.newSession()
    main_window.tools_widget.bridge.openRecent()
    assert calls == ["new", "recent"]
````

In `tests/test_toast_router.py`:

**Edit 1 of 1** (near line 72). Find exactly:

````python
def test_on_a_qt_page_the_qt_toast_shows(main_window):
    main_window.main_tabs.setCurrentIndex(3)
````

Replace with:

````python
def test_on_tools_the_tools_page_draws_it(main_window):
    main_window.main_tabs.setCurrentIndex(4)
    seen = _raised(main_window.tools_widget.bridge)
    other = _raised(main_window.setup_bridge)

    shown = toast(main_window, "Settings saved")

    # No action: the router's toast never offers Open folder.
    assert seen == [("Settings saved", False)]
    assert other == []
    assert shown is None
    assert Toast.for_window(main_window) is None


def test_on_a_qt_page_the_qt_toast_shows(main_window):
    main_window.main_tabs.setCurrentIndex(3)
````

- [ ] **Step 2: Point the print-settings fixture at `gui.pdf_printing`**

`print_settings_store` patches `gui.components.print_options`, which this task deletes.

In `tests/conftest.py`:

**Edit 1 of 2** (near line 134). Find exactly:

````python
@pytest.fixture
def print_settings_store(monkeypatch):
    """PrintOptions reads and writes QSettings("ShopifyFulfillmentTool",
    "Printing") -- the developer's real per-PC printer choice. Tests that build
    a real PrintOptions, or a widget holding one, get an in-memory store keyed
    by scope instead."""
    from gui.components import print_options

    defaults = {
````

Replace with:

````python
@pytest.fixture
def print_settings_store(monkeypatch):
    """The Tools page reads and writes QSettings("ShopifyFulfillmentTool",
    "Printing") -- the developer's real per-PC printer choice. Tests that edit
    a print setting through ToolsWidget get an in-memory store keyed by scope
    instead. ToolsWidget and both tools call gui.pdf_printing through the
    module, so patching it here reaches them."""
    from gui import pdf_printing

    defaults = {
````

**Edit 2 of 2** (near line 151). Find exactly:

````python
    store = {}
    monkeypatch.setattr(
        print_options,
        "load_print_settings",
        lambda scope: dict(store.get(scope, defaults)),
    )
    monkeypatch.setattr(
        print_options,
        "save_print_settings",
        lambda scope, settings: store.__setitem__(scope, dict(settings)),
````

Replace with:

````python
    store = {}
    monkeypatch.setattr(
        pdf_printing,
        "load_print_settings",
        lambda scope: dict(store.get(scope, defaults)),
    )
    monkeypatch.setattr(
        pdf_printing,
        "save_print_settings",
        lambda scope, settings: store.__setitem__(scope, dict(settings)),
````

- [ ] **Step 3: Run the new tests and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_tools_widget.py`
Expected: every test errors: `AttributeError: module 'gui.tools_widget' has no attribute
'installed_printers'` (the old widget is still in place).

- [ ] **Step 4: Replace the widget**

Replace the whole of `gui/tools_widget.py` with:

````python
"""The Tools screen: Reference labels and Barcode labels (phase 5 spec section 6.1).

A widget that hosts one web view. Everything drawn on this screen is in
gui/web/tools.*; what it draws is built by gui/tools_state.py from the two
tools' facts (gui/reference_tool.py, gui/barcode_tool.py). This widget wires
the page's requests to the tools and pushes the state.
"""

import logging
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QThreadPool, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtPrintSupport import QPrinterInfo
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QVBoxLayout, QWidget

from gui import pdf_printing
from gui.barcode_tool import BarcodeTool
from gui.components import toast
from gui.reference_tool import ReferenceTool
from gui.setup_state import SessionFacts
from gui.tools_bridge import TOOLS, mount_tools_page
from gui.tools_state import PRINT_SCOPE, PrintFacts, apply_print_edit, tools_state

logger = logging.getLogger(__name__)


def installed_printers() -> tuple[str, ...]:
    """The printers this PC lists, by name."""
    return tuple(QPrinterInfo.availablePrinterNames())


class ToolsWidget(QWidget):
    """The Tools screen's widget: one web view and the two tools behind it.

    Signals:
        new_session_requested: the no-session banner's New session
        recent_requested: the no-session banner's Open recent
    """

    new_session_requested = Signal()
    recent_requested = Signal()

    def __init__(self, main_window, parent=None, pool: QThreadPool | None = None):
        """main_window: read for session_path, session_facts, current_client_id
        and analysis_results_df. pool: where the tools' workers start; the
        global pool when None."""
        super().__init__(parent)
        self.mw = main_window
        self._session_path: str | None = None
        self._printers: tuple[str, ...] = ()
        self._settings: dict[str, dict] = {}
        self._toast_folder = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.view = QWebEngineView(self)
        self.bridge = mount_tools_page(self.view)
        layout.addWidget(self.view, 1)

        self.reference = ReferenceTool(self, pool)
        self.barcode = BarcodeTool(
            self, lambda: getattr(self.mw, "analysis_results_df", None), pool
        )
        for tool in (self.reference, self.barcode):
            tool.changed.connect(self._push)
            tool.toast.connect(self._on_toast)

        bridge = self.bridge
        bridge.fileRequested.connect(self.reference.choose)
        bridge.clearRequested.connect(self.reference.clear)
        bridge.folderRequested.connect(self.reference.change_folder)
        bridge.optionChanged.connect(self._on_option)
        bridge.printChanged.connect(self._on_print_edit)
        bridge.listChosen.connect(self.barcode.choose)
        bridge.listsRequested.connect(self.barcode.reload)
        bridge.runRequested.connect(self._on_run)
        bridge.cancelRequested.connect(self.reference.cancel)
        bridge.printRequested.connect(self._on_print)
        bridge.folderOpenRequested.connect(self._open_toast_folder)
        bridge.newSessionRequested.connect(self.new_session_requested)
        bridge.recentRequested.connect(self.recent_requested)

        self._read_this_pc()
        self.sync()
        logger.info("ToolsWidget initialized")

    # --- state ---------------------------------------------------------------

    def _read_this_pc(self) -> None:
        """The installed printers and both tools' saved print settings."""
        self._printers = installed_printers()
        self._settings = {
            tool: pdf_printing.load_print_settings(PRINT_SCOPE[tool]) for tool in TOOLS
        }

    def sync(self) -> None:
        """Follow the window's session, then push. Touches no file, so the
        shell calls it on every client, session and connection change."""
        path = getattr(self.mw, "session_path", None)
        path = str(path) if path else None
        if path != self._session_path:
            self._session_path = path
            self.reference.set_session(path)
            self.barcode.set_session(path)
            if path and self.isVisible():
                self.barcode.reload()
        self._push()

    def _push(self) -> None:
        """Build the page's state from what the tools hold and send it."""
        session = None
        if self._session_path:
            name = Path(self._session_path).name
            facts = getattr(self.mw, "session_facts", None)
            session = (
                facts
                if facts is not None and facts.name == name
                else SessionFacts(name, None, None)
            )
        self.bridge.set_state(
            tools_state(
                client=getattr(self.mw, "current_client_id", None) or "",
                session=session,
                reference=self.reference.facts(),
                reference_print=PrintFacts(self._settings["reference"], self._printers),
                barcode=self.barcode.facts(),
                barcode_print=PrintFacts(self._settings["barcode"], self._printers),
                now=datetime.now().astimezone(),
            )
        )

    def showEvent(self, event):
        """Each time Tools is shown: this PC's printers and settings, and the
        session's packing lists, are read again."""
        super().showEvent(event)
        self._read_this_pc()
        self.sync()
        if self._session_path:
            self.barcode.reload()

    # --- what the page asks for ----------------------------------------------

    def _on_option(self, tool: str, name: str, on: bool) -> None:
        if tool == "reference":
            self.reference.set_open_pdf(on)
        else:
            self.barcode.set_option(name, on)

    def _on_print_edit(self, tool: str, key: str, value) -> None:
        edited = apply_print_edit(self._settings[tool], key, value)
        if edited is None:
            logger.warning(f"Dropped a print edit the page should not send: {tool}.{key}")
            return
        self._settings[tool] = edited
        pdf_printing.save_print_settings(PRINT_SCOPE[tool], edited)
        self._push()

    def _on_run(self, tool: str) -> None:
        if tool == "reference":
            self.reference.start()
        else:
            self.barcode.start()

    def _on_print(self, tool: str, what: str) -> None:
        if tool == "reference":
            self.reference.print_output()
        else:
            self.barcode.print_labels(what)

    # --- toasts --------------------------------------------------------------

    def _on_toast(self, text: str, folder: str) -> None:
        """A run finished. While this screen shows, its page draws the toast
        with Open folder; otherwise the router sends it to the page that is
        showing (ADR 0007), with no action."""
        if folder and self.isVisible():
            self._toast_folder = folder
            self.bridge.raise_toast(text, True)
        else:
            toast(self, text)

    def _open_toast_folder(self) -> None:
        if self._toast_folder:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._toast_folder))
````

- [ ] **Step 5: The shell follows**

In `gui/ui_manager.py`:

**Edit 1 of 4** (near line 35). Find exactly:

````python
# own edges, so the page area's 5px inset would show as a white ring around
# it. Each phase that moves a screen adds its index (phase 2 spec section 5.1).
_WEB_PAGES = frozenset({0, 1, 2})
````

Replace with:

````python
# own edges, so the page area's 5px inset would show as a white ring around
# it. Each phase that moves a screen adds its index (phase 2 spec section 5.1).
_WEB_PAGES = frozenset({0, 1, 2, 4})
````

**Edit 2 of 4** (near line 323). Find exactly:

````python
        self.mw.main_tabs.currentChanged.connect(self._apply_page_inset)
        # The session chip on every screen but Setup, whose page head shows it;
        # the analysis age on Results.
        self.mw.main_tabs.currentChanged.connect(
            lambda index: self.mw.command_bar.set_screen(
                chip=index != 0, meta=index == 1
            )
        )
````

Replace with:

````python
        self.mw.main_tabs.currentChanged.connect(self._apply_page_inset)
        # The session chip on every screen but Setup and Tools, whose page
        # heads show it; the analysis age on Results.
        self.mw.main_tabs.currentChanged.connect(
            lambda index: self.mw.command_bar.set_screen(
                chip=index not in (0, 4), meta=index == 1
            )
        )
````

**Edit 3 of 4** (near line 481). Find exactly:

````python
        mw.run_analysis_button.setEnabled(state["run"]["enabled"])
        mw.setup_bridge.set_state(state)

    def refresh_recent_sessions(self, client_id: str):
````

Replace with:

````python
        mw.run_analysis_button.setEnabled(state["run"]["enabled"])
        mw.setup_bridge.set_state(state)
        self.refresh_tools()

    def refresh_tools(self) -> None:
        """Let the Tools page follow the window's session.

        Called from refresh_setup(): every client, session and connection
        change already passes through it. ToolsWidget.sync() touches no file.
        """
        tools = getattr(self.mw, "tools_widget", None)
        if tools is not None:
            tools.sync()

    def refresh_recent_sessions(self, client_id: str):
````

**Edit 4 of 4** (near line 792). Find exactly:

````python
    def _create_tab5_tools(self):
        """Create Tab 5: Tools

        Reference labels and Barcode labels as two cards, side by side, that
        stack when the page is narrow. See gui/tools_widget.py.

        Returns:
            QWidget: the Tools page
        """
        from gui.tools_widget import ToolsWidget
````

Replace with:

````python
    def _create_tab5_tools(self):
        """Tools: one QWebEngineView, no Qt inside (phase 5 spec).

        ToolsWidget hosts the view and the two tools behind it; everything
        drawn on this screen is in gui/web/tools.*.
        """
        from gui.tools_widget import ToolsWidget
````

In `gui/main_window_pyside.py`:

**Edit 1 of 3** (near line 161). Find exactly:

````python
        if index == 2:
            bridge = getattr(getattr(self, "session_browser", None), "bridge", None)
        else:
            bridge = getattr(
````

Replace with:

````python
        if index == 2:
            bridge = getattr(getattr(self, "session_browser", None), "bridge", None)
        elif index == 4:
            bridge = getattr(getattr(self, "tools_widget", None), "bridge", None)
        else:
            bridge = getattr(
````

**Edit 2 of 3** (near line 364). Find exactly:

````python
        )

        # Main actions
        self.run_analysis_button.clicked.connect(self.actions_handler.run_analysis)
````

Replace with:

````python
        )

        # The Tools page's no-session banner
        self.tools_widget.new_session_requested.connect(
            lambda: self.actions_handler.create_new_session()
        )
        self.tools_widget.recent_requested.connect(
            lambda: self.command_bar.session_button.showMenu()
        )

        # Main actions
        self.run_analysis_button.clicked.connect(self.actions_handler.run_analysis)
````

**Edit 3 of 3** (near line 558). Find exactly:

````python
        # WorkerSignals object before its already-queued cross-thread result
        # signal is dispatched to the main thread, silently dropping the
        # client switch. Verified via a minimal repro; the existing bare
        # `worker = Worker(...)` pattern elsewhere in this codebase
        # (e.g. barcode_generator_widget.py) has the same latent exposure.
        # Tracked in a set, not a single slot: a second switch before this one
        # finishes must not drop the first worker's reference out from under it.
````

Replace with:

````python
        # WorkerSignals object before its already-queued cross-thread result
        # signal is dispatched to the main thread, silently dropping the
        # client switch. Verified via a minimal repro; a bare
        # `worker = Worker(...)` anywhere else in this codebase has the same
        # latent exposure (the Tools page's tools hold theirs for this reason).
        # Tracked in a set, not a single slot: a second switch before this one
        # finishes must not drop the first worker's reference out from under it.
````

- [ ] **Step 6: The print sentence, and the export list**

Print is disabled when Raw ZPL has no printer, so this guard is a backstop; its sentence names the row the
operator now sees.

In `gui/pdf_printing.py`:

**Edit 1 of 1** (near line 77). Find exactly:

````python
            parent,
            "Nothing was printed",
            "Choose a Raw ZPL printer under Print options, then print again.",
        )
        return False
````

Replace with:

````python
            parent,
            "Nothing was printed",
            "Choose a printer under Print mode, then print again.",
        )
        return False
````

In `tests/test_pdf_printing.py`:

**Edit 1 of 1** (near line 120). Find exactly:

````python
        assert result is False
        assert warning.called
        assert "Print options" in warning.call_args.args[2]
        assert not called.called
````

Replace with:

````python
        assert result is False
        assert warning.called
        assert warning.call_args.args[2] == (
            "Choose a printer under Print mode, then print again."
        )
        assert not called.called
````

In `gui/components/__init__.py`:

**Edit 1 of 2** (near line 6). Find exactly:

````python
from gui.components.form_section import FormSection, row_widget
from gui.components.inline_message import InlineMessage
from gui.components.print_options import PrintOptions
from shared.components import (
    Card,
````

Replace with:

````python
from gui.components.form_section import FormSection, row_widget
from gui.components.inline_message import InlineMessage
from shared.components import (
    Card,
````

**Edit 2 of 2** (near line 50). Find exactly:

````python
    "NavRail",
    "OverflowMenu",
    "PrintOptions",
    "StatePanel",
    "Toast",
````

Replace with:

````python
    "NavRail",
    "OverflowMenu",
    "StatePanel",
    "Toast",
````

- [ ] **Step 7: Delete the Qt widgets and their tests**

Run, as one git command:

```bash
/usr/bin/git rm gui/reference_labels_widget.py gui/barcode_generator_widget.py gui/components/print_options.py tests/test_tools_cards.py tests/test_tools_theme.py tests/test_reference_labels_widget.py tests/test_barcode_generator_widget.py tests/test_print_options.py tests/test_print_summary.py
```

Then confirm nothing still names them. Use the Grep tool for
`print_options|PrintOptions|print_summary|reference_labels_widget|barcode_generator_widget|primary_holder`
over `gui/`, `tests/`, `shared/` and `shopify_tool/` (`*.py`). Expected: one hit, a comment in
`tests/test_tag_manager.py` about history ("barcode_generator_widget.py used to merge…"). Leave it.

`FormSection`, `row_widget`, `InlineMessage` and `ElidedLabel` stay: `gui/column_mapping_widget.py` and
`gui/settings/rules.py` use them.

- [ ] **Step 8: One test read the old widget's source**

In `tests/test_reports_sku_labels_removed.py`:

**Edit 1 of 2** (near line 13). Find exactly:

````python
from PySide6.QtWidgets import QApplication, QMainWindow

from gui.tools_widget import ToolsWidget
from gui.ui_manager import UIManager
````

Replace with:

````python
from PySide6.QtWidgets import QApplication, QMainWindow

import gui.tools_widget
from gui.ui_manager import UIManager
````

**Edit 2 of 2** (near line 25). Find exactly:

````python
def test_tools_widget_no_longer_wires_sku_labels_subtab(qapp):
    # ToolsWidget._init_ui() needs a full MainWindow (session_changed signal,
    # session_manager, etc.) to actually construct -- checking its source
    # avoids that heavyweight fixture while still failing if the SKU Labels
    # sub-tab wiring is ever reintroduced.
    source = inspect.getsource(ToolsWidget._init_ui)
    assert "SKULabelWidget" not in source
    assert "SKU Labels" not in source
````

Replace with:

````python
def test_tools_widget_no_longer_wires_sku_labels_subtab(qapp):
    # Checking the module's source avoids building the page while still
    # failing if the SKU Labels sub-tab wiring is ever reintroduced.
    source = inspect.getsource(gui.tools_widget)
    assert "SKULabelWidget" not in source
    assert "SKU Labels" not in source
````

- [ ] **Step 9: Run this task's tests and see them pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_tools_widget.py tests/test_shell.py tests/test_toast_router.py tests/test_reference_tool.py tests/test_barcode_tool.py tests/test_reports_sku_labels_removed.py tests/test_pdf_printing.py`
Expected: all pass (163 passed).

- [ ] **Step 10: Run the whole suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: 2904 passed and 3 failed, in about six minutes. The three failures are the baseline's (`tests/test_label_printing.py::TestImageToZpl`). Anything else that fails is yours: fix it before going on.

- [ ] **Step 11: Lint**

Run: `.venv/bin/ruff check .`
Expected: `All checks passed!`

- [ ] **Step 12: Commit**

Message: `Tools on the web tier: the widget hosts the page, the Qt tool widgets go (phase 5 spec 6, 8)`.
Add every file this task created or modified; the deletions are already staged by `git rm`. Check with
`/usr/bin/git status --short` that nothing else is staged.

---

### Task 10: Docs, the build check, the visual check, the gate

**Files:**
- Modify: `CONTEXT.md`, `docs/adr/0016-the-web-tier-grows-screen-by-screen.md`,
  `docs/design/ui-refresh/roadmap.md`, `.github/workflows/build_release.yml`
- Create: four PNGs under `docs/design/ui-refresh/renders/phase5/`

**Interfaces:**
- Consumes: everything above.
- Produces: the docs spec §12 lists, and the renders the PR carries.

- [ ] **Step 1: The glossary**

In `CONTEXT.md`:

**Edit 1 of 3** (near line 17). Find exactly:

````
**Web tier** — the part drawn in a `QWebEngineView`, styled with real CSS.
Analysis Results, Session Setup and Browse today; ADR 0016 lets each other screen move
in its own task. See ADR 0001 for why Results moved first.

**Renderer** — either tier, when the point is that there are two of them and
````

Replace with:

````
**Web tier** — the part drawn in a `QWebEngineView`, styled with real CSS.
Analysis Results, Session Setup, Browse and Tools today; ADR 0016 lets each other
screen move in its own task. See ADR 0001 for why Results moved first.

**Renderer** — either tier, when the point is that there are two of them and
````

**Edit 2 of 3** (near line 355). Find exactly:

````
records and decides no fact about a session.

**Needs attention** — the group Browse draws first: sessions that are paused,
stale or incomplete, and sessions still in flight that carry blocked orders.
````

Replace with:

````
records and decides no fact about a session.

**Tools state** — the one map Python builds for the Tools page: the session,
each tool card's rows, its print block, its footer's reason and what is
enabled. The page draws it and decides nothing.

**Tool card** — one tool on the Tools page (Reference labels, Barcode labels),
with its inputs, its print mode and its footer.

**Needs attention** — the group Browse draws first: sessions that are paused,
stale or incomplete, and sessions still in flight that carry blocked orders.
````

**Edit 3 of 3** (near line 384). Find exactly:

````
target (**Raw ZPL**). Chosen per tool and per PC.

**Print options** — one tool's print mode and the settings that mode needs.
Stored on the PC, not in the client profile.

**Actual size** — a label PDF printed at its own page dimensions, scaled
````

Replace with:

````
target (**Raw ZPL**). Chosen per tool and per PC.

**Print options** — one tool's print mode, its printer and its label setup.
Stored on the PC, not in the client profile.

**Label setup** — the Raw ZPL settings a tool keeps behind a fold under Print
mode: the printer target, the label size, rotate and invert.

**Actual size** — a label PDF printed at its own page dimensions, scaled
````

- [ ] **Step 2: ADR 0016**

In `docs/adr/0016-the-web-tier-grows-screen-by-screen.md`:

**Edit 1 of 1** (near line 47). Find exactly:

````
  phase 3 measurement (about 31 MB a view). Its page owns its view state (tab, search, checked rows), as
  the results document does; Python owns every fact about a session.

## What would reverse it
````

Replace with:

````
  phase 3 measurement (about 31 MB a view). Its page owns its view state (tab, search, checked rows), as
  the results document does; Python owns every fact about a session.
- Tools moved in phase 5 (2026-10-02) with the fourth bridge, `ToolsBridge`, and a fourth view, on the same
  measurement. Its page owns only which menu and which Label setup fold is open; Python owns every fact
  about a tool.

## What would reverse it
````

- [ ] **Step 3: The roadmap**

In `docs/design/ui-refresh/roadmap.md`:

**Edit 1 of 1** (near line 116). Find exactly:

````
toast for every change. The packing progress bar. The archived footer. Double-click opens the session.

### 5. Tools to the web tier

One card per tool (Reference labels, Barcode labels), each using the Setup row grid. A Driver / Raw ZPL switch
````

Replace with:

````
toast for every change. The packing progress bar. The archived footer. Double-click opens the session.

### 5. Tools to the web tier (built in run 47)

Spec: `docs/superpowers/specs/2026-10-02-ui-refresh-phase5-tools-web-design.md`.
Plan: `docs/superpowers/plans/2026-10-02-ui-refresh-phase5-tools-web.md`.

Built as listed below, with these differences. Reference labels has the count and Cancel; Barcode labels
says "Writing 120 barcode labels…" with neither, because its render is one call. Print prints what exists:
Reference after a run, Barcode whenever the list's PDF is on disk. Barcode's output folder is fixed, with no
Change…. The print settings the mockup does not draw (target, label size, rotate, invert) sit behind a
"Label setup" fold under Print mode, and the printer menu shows in Driver mode too. The CSV problem reads
"This CSV has no usable rows": the file is read by column position, not by header. A PDF that cannot be
opened is flagged the same way. The session chip is in the page head on Tools, as on Setup. The kit gained
`.select`.

One card per tool (Reference labels, Barcode labels), each using the Setup row grid. A Driver / Raw ZPL switch
````

- [ ] **Step 4: The bundle check**

The release build fails if a web page is missing from the bundle.

In `.github/workflows/build_release.yml`:

**Edit 1 of 1** (near line 152). Find exactly:

````
        shell: pwsh
        run: |
          foreach ($name in "package.svg", "Inter-Regular.ttf", "QtWebEngineProcess.exe", "results.html", "setup.html", "browse.html", "pikepdf", "fulfilment-tool.ico", "qico.dll") {
            if (-not (Get-ChildItem -Path "dist\FulfilmentTool" -Recurse -Filter $name)) {
              throw "PyInstaller did not bundle $name."
````

Replace with:

````
        shell: pwsh
        run: |
          foreach ($name in "package.svg", "Inter-Regular.ttf", "QtWebEngineProcess.exe", "results.html", "setup.html", "browse.html", "tools.html", "pikepdf", "fulfilment-tool.ico", "qico.dll") {
            if (-not (Get-ChildItem -Path "dist\FulfilmentTool" -Recurse -Filter $name)) {
              throw "PyInstaller did not bundle $name."
````

- [ ] **Step 5: Render the page and look at it (required, CLAUDE.md)**

Write this throwaway script to your job's tmp dir as `render_tools.py` (never into the repo):

````python
"""Throwaway: render the Tools page, the kit sheet and the window to PNG.

Run from the repo root:
    QT_QPA_PLATFORM=offscreen .venv/bin/python <this file> <output folder>
Never commit this file.
"""

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("FULFILLMENT_SERVER_PATH", tempfile.mkdtemp())
# The script lives outside the repo, so the repo root (the cwd) and its tests
# folder are put on the path by hand.
sys.path[:0] = [os.getcwd(), os.path.join(os.getcwd(), "tests")]

from PySide6.QtCore import QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication
from test_tools_state import BAD_CSV, PRINTERS, ZPL, barcode, make_state, reference

from gui.theme_manager import get_theme_manager
from gui.tools_bridge import mount_tools_page
from gui.tools_state import BarcodeFacts, PackingList, PrintFacts, ReferenceFacts, ToolRun
from gui.web_page import THEME_MARKER, WEB_DIR
from shared.theme import theme_css_vars
from shopify_tool.pdf_processor import STAMPING

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
app = QApplication.instance() or QApplication([])


def pump(seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


def js(view, code):
    box = []
    view.page().runJavaScript(code, 0, box.append)
    end = time.monotonic() + 5
    while not box and time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)
    return box[0] if box else None


SIZED = PrintFacts(
    {**ZPL, "raw_zpl_label_width_mm": 68.0, "raw_zpl_label_height_mm": 38.0}, PRINTERS
)
DONE_LISTS = (
    PackingList("DHL", 120, True, True),
    PackingList("DPD", 48),
    PackingList("Royal Mail", 31),
)
OPEN_MENU_AND_FOLD = (
    "document.querySelector('[data-key=\"barcode-fold\"]').click();"
    " document.querySelector('[data-key=\"barcode-list\"]').click(); true"
)
# name -> (state, what to do after it is drawn)
STATES = {
    "ready": (make_state(barcode_print=SIZED), None),
    "no-session": (
        make_state(
            session=None,
            reference=ReferenceFacts(),
            barcode=BarcodeFacts(),
            barcode_print=SIZED,
        ),
        None,
    ),
    "mapping-problem": (
        make_state(reference=reference(csv=BAD_CSV), barcode_print=SIZED),
        None,
    ),
    "reference-running": (
        make_state(reference=reference(run=ToolRun(STAMPING, 40, 120)), barcode_print=SIZED),
        None,
    ),
    "barcode-running": (
        make_state(
            barcode=barcode(run=ToolRun("Writing 120 barcode labels…")), barcode_print=SIZED
        ),
        None,
    ),
    "menu-and-label-setup": (
        make_state(
            barcode=barcode(qr=True, lists=DONE_LISTS),
            reference=reference(
                has_output=True,
                result={
                    "pages_processed": 120,
                    "matched": 118,
                    "unmatched": 2,
                    "name_matched": 3,
                },
            ),
            barcode_print=SIZED,
        ),
        OPEN_MENU_AND_FOLD,
    ),
    "done-toast": (make_state(barcode=barcode(lists=DONE_LISTS), barcode_print=SIZED), "TOAST"),
}


def render_page(theme):
    for name, (state, after) in STATES.items():
        view = QWebEngineView()
        bridge = mount_tools_page(view)
        view.resize(1166, 720)
        view.show()
        end = time.monotonic() + 15
        ready = "document.documentElement.dataset.bridge === 'ready'"
        while js(view, ready) is not True and time.monotonic() < end:
            pump(0.05)
        bridge.set_state(state)
        pump(0.4)
        if after == "TOAST":
            bridge.raise_toast("120 barcode labels saved to …/barcodes/DHL. QR labels too.", True)
        elif after:
            js(view, after)
        pump(0.5)
        view.grab().save(str(OUT / f"{theme}-{name}.png"))
        view.close()
        view.deleteLater()
        pump(0.1)


def render_sheet(theme):
    sheet = Path("tests/web/kit_sheet.html").read_text(encoding="utf-8")
    view = QWebEngineView()
    tokens = get_theme_manager().get_current_theme()
    view.setHtml(
        sheet.replace(THEME_MARKER, theme_css_vars(tokens)),
        QUrl.fromLocalFile(str(WEB_DIR) + "/"),
    )
    view.resize(1166, 1040)
    view.show()
    pump(1.5)
    view.grab().save(str(OUT / f"{theme}-kit-sheet.png"))
    view.close()
    view.deleteLater()
    pump(0.1)


def render_window(theme):
    from gui.main_window_pyside import MainWindow

    window = MainWindow()
    window.resize(1366, 768)
    window.show()
    window.main_tabs.setCurrentIndex(4)
    pump(2.5)
    window.grab().save(str(OUT / f"{theme}-window-tools.png"))
    window.close()
    pump(0.2)


for theme_name in ("light", "dark"):
    get_theme_manager().set_theme(theme_name)
    render_page(theme_name)
    render_sheet(theme_name)
    render_window(theme_name)
print("rendered to", OUT)
````

Run, from the repo root: `QT_QPA_PLATFORM=offscreen .venv/bin/python <your tmp dir>/render_tools.py <your tmp dir>/renders`
(the line "Release of profile requested but WebEnginePage still not deleted" on exit is harmless).

It writes, for `light` and `dark`: `ready`, `no-session`, `mapping-problem`, `reference-running`,
`barcode-running`, `menu-and-label-setup`, `done-toast`, `kit-sheet` and `window-tools`. Open each PNG with
the Read tool and compare with `docs/design/ui-refresh/mockups/renders/tools.png` and, for the other states,
with the mockup opened in Chrome (`mockups/README.md`). Check, in both themes:

- two cards side by side, each with its head, its rows on a 112px label column, and its footer;
- the session chip and "ACME · opened 14:02" in the page head; on `window-tools` the command bar draws **no**
  session chip;
- `no-session`: one banner with New session and Open recent; every field dashed and quiet; the mode switch
  and the printer select still live;
- `mapping-problem`: the danger banner under the Mapping CSV row only, the reason in the danger colour, both
  Reference actions disabled, the card's own edge unchanged;
- `reference-running`: "Stamping labels — 40 of 120", a bar two-thirds full, Cancel; `barcode-running`: the
  sentence alone;
- `menu-and-label-setup`: the menu under the packing-list select, as wide as it, with a tick on DHL; the fold
  open with Target, Label size, Rotate 90° and Invert colours;
- `done-toast`: the toast bottom right with Open folder and a dismiss cross;
- a path such as `…/2026-09-30_1/reference_labels` keeps its underscores.

The expected departures from the mockup are spec §10 (control height, the printer select in Driver mode, the
Label setup fold, no Change… and no bar on Barcode). Anything else that differs is a defect: fix it in
`tools.css` or `tools.js`, re-run Task 6's tests, and render again.

Copy four of the PNGs into the repo with the Bash tool (`mkdir -p docs/design/ui-refresh/renders/phase5`, then
`cp`): `light-ready.png`, `dark-ready.png`, `light-mapping-problem.png`, `light-no-session.png`.

- [ ] **Step 6: The gate**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: 2904 passed and 3 failed, in about six minutes. The three failures are the baseline's (`tests/test_label_printing.py::TestImageToZpl`). Anything else that fails is yours: fix it before going on.

Run: `.venv/bin/ruff check .`
Expected: `All checks passed!`

Run: `graphify update .`

- [ ] **Step 7: Commit**

Message: `Docs: Tools on the web tier (phase 5 spec 12), and its renders`.
Add `CONTEXT.md`, `docs/adr/0016-the-web-tier-grows-screen-by-screen.md`,
`docs/design/ui-refresh/roadmap.md`, `.github/workflows/build_release.yml` and the four PNGs.

- [ ] **Step 8: What the PR body must carry (for Stage C)**

- The four renders.
- "Nothing in `shared/` changes; no Packing Tool PR."
- The baseline failures, if any, named as not this task's.
- The Windows checks to run on a warehouse PC over RDP with the release build, before the release: Task
  Manager memory for the app's process plus every `QtWebEngineProcess.exe` on Tools (Linux says about +31 MB
  for the fourth view), the time to a drawn Tools page, and one reference label and one barcode label printed
  in each print mode (Driver, Raw ZPL).
- The behaviour changes an operator will notice, from spec §2 and §10: files are checked when picked; Print
  prints what exists; Barcode has no count and no Cancel; picks are cleared when the session changes; label
  size, rotate and invert are under "Label setup".
