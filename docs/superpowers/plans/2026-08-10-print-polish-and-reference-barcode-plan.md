# Print Polish + Reference-Number Barcode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix three problems found in manual QA of direct label printing: print settings shared/clobbered across the Reference Labels and Barcode Generator windows, driver-mode printing rendering labels as tiny corner stamps, and the never-built Reference Labels barcode overlay.

**Architecture:** All changes land in the three files the original print-dispatcher feature touched — `gui/pdf_printing.py` (settings scoping + driver-mode render/page-range/page-size/printer-name fixes), `gui/reference_labels_widget.py` / `gui/barcode_generator_widget.py` (per-window UI wiring), and `shopify_tool/pdf_processor.py` (new barcode overlay + content-shrink transform). No new dependencies.

**Tech Stack:** PySide6 (`QtPrintSupport`, `QtPdf`, `QtGui`), `pypdf` (`Transformation`, `PageObject.add_transformation`), `reportlab` (`reportlab.graphics.barcode.code128.Code128`, `reportlab.pdfgen.canvas`), pytest with `QT_QPA_PLATFORM=offscreen`.

## Global Constraints

- `QT_QPA_PLATFORM=offscreen python -m pytest` and `ruff check . --exclude shared` must both pass before any commit that isn't explicitly marked "expected to fail" in this plan.
- Never hand-edit anything under `shared/` (not touched by this plan; noted per `CLAUDE.md`).
- No hardcoded colors — not applicable here (no stylesheet changes in this plan), but keep in mind if any `QLabel` styling is touched.
- No UI calls from background threads — not applicable, all changes in this plan run on the main thread (printing is already synchronous, per the design spec's non-goals).
- Run `graphify update .` after each task's commit (per this repo's `CLAUDE.md`), so the knowledge graph doesn't go stale mid-plan.
- Design reference: `docs/superpowers/specs/2026-08-10-print-polish-and-reference-barcode-design.md`.
- Line numbers in "Files" blocks are accurate against the pre-Task-1 state of each file. Task 1 removes one line from each widget's import block (and one more from `showEvent`), shifting everything below by 1-2 lines in Tasks 3+. Locate edit points by the surrounding code shown in each step (e.g. "after the `raw_zpl_rotate_check` block", "the `_save_print_settings` method"), not by line number alone.

---

## Task 1: Scope print settings per window

**Files:**
- Modify: `gui/pdf_printing.py:28-72` (`load_print_settings`, `save_print_settings`, `refresh_print_controls` — the last is deleted)
- Modify: `gui/barcode_generator_widget.py:33-38,154,602-613,245-252`
- Modify: `gui/reference_labels_widget.py:30-35,151,566-586`
- Test: `tests/test_pdf_printing.py:1-90` (`TestPrintSettingsRoundTrip` rewritten, `TestRefreshPrintControls` deleted)

**Interfaces:**
- Produces: `load_print_settings(scope: str) -> dict` — same three keys as before (`print_mode`, `raw_zpl_target`, `raw_zpl_rotate`), now stored under `f"{scope}/..."` QSettings keys. Callers pass `"reference_labels"` or `"barcode_generator"`.
- Produces: `save_print_settings(scope: str, settings: dict) -> None` — same shape.
- Removes: `refresh_print_controls()` (no longer needed — see design spec D-1).

- [ ] **Step 1: Write the failing tests for scoped settings**

Replace `class TestPrintSettingsRoundTrip` in `tests/test_pdf_printing.py` (currently lines 30-43) with:

```python
class TestPrintSettingsRoundTrip:
    def test_defaults_when_nothing_saved(self, isolated_settings):
        settings = pdf_printing.load_print_settings("reference_labels")
        assert settings == {"print_mode": "driver", "raw_zpl_target": "", "raw_zpl_rotate": False}

    def test_save_then_load_roundtrip(self, isolated_settings):
        pdf_printing.save_print_settings(
            "reference_labels",
            {"print_mode": "raw_zpl", "raw_zpl_target": "ZPL-RAW-Printer", "raw_zpl_rotate": True},
        )
        assert pdf_printing.load_print_settings("reference_labels") == {
            "print_mode": "raw_zpl",
            "raw_zpl_target": "ZPL-RAW-Printer",
            "raw_zpl_rotate": True,
        }

    def test_different_scopes_do_not_collide(self, isolated_settings):
        pdf_printing.save_print_settings(
            "reference_labels",
            {"print_mode": "raw_zpl", "raw_zpl_target": "Labels 6x4", "raw_zpl_rotate": False},
        )
        pdf_printing.save_print_settings(
            "barcode_generator",
            {"print_mode": "driver", "raw_zpl_target": "Barcodes", "raw_zpl_rotate": True},
        )

        ref_settings = pdf_printing.load_print_settings("reference_labels")
        barcode_settings = pdf_printing.load_print_settings("barcode_generator")
        assert ref_settings["raw_zpl_target"] == "Labels 6x4"
        assert barcode_settings["raw_zpl_target"] == "Barcodes"
        assert ref_settings["print_mode"] == "raw_zpl"
        assert barcode_settings["print_mode"] == "driver"
```

Delete `class TestRefreshPrintControls` entirely (the whole class, including its `_make_controls` staticmethod and both test methods — currently lines 45-90).

Trim the now-unused imports at the top of the file — `QCheckBox`, `QComboBox`, `QLineEdit` were only used by the deleted class:

```python
from PySide6.QtWidgets import QApplication, QMessageBox
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_pdf_printing.py -v`
Expected: `TestPrintSettingsRoundTrip` tests FAIL with `TypeError: load_print_settings() missing 1 required positional argument: 'scope'` (or similar for `save_print_settings`).

- [ ] **Step 3: Implement scoped settings and delete `refresh_print_controls`**

In `gui/pdf_printing.py`, replace the current `load_print_settings`/`save_print_settings`/`refresh_print_controls` block (lines 28-71) with:

```python
def load_print_settings(scope: str) -> dict:
    qs = QSettings(*_SETTINGS)
    return {
        "print_mode": qs.value(f"{scope}/print_mode", "driver"),
        "raw_zpl_target": qs.value(f"{scope}/raw_zpl_target", ""),
        "raw_zpl_rotate": qs.value(f"{scope}/raw_zpl_rotate", False, type=bool),
    }


def save_print_settings(scope: str, settings: dict) -> None:
    qs = QSettings(*_SETTINGS)
    qs.setValue(f"{scope}/print_mode", settings["print_mode"])
    qs.setValue(f"{scope}/raw_zpl_target", settings["raw_zpl_target"])
    qs.setValue(f"{scope}/raw_zpl_rotate", settings["raw_zpl_rotate"])
```

(`refresh_print_controls` is gone — each window now owns its own QSettings key namespace, so the cross-window clobber it guarded against can't happen anymore.) `QCheckBox`, `QComboBox`, `QLineEdit` were only used by `refresh_print_controls`'s parameter type hints — nowhere else in the file — so change the `PySide6.QtWidgets` import (currently line 19) from:

```python
from PySide6.QtWidgets import QCheckBox, QComboBox, QLineEdit, QMessageBox, QWidget
```

to:

```python
from PySide6.QtWidgets import QMessageBox, QWidget
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_pdf_printing.py -v`
Expected: PASS (the `TestPrintSettingsRoundTrip` class only — the rest of the file still references the old call patterns and gets fixed in later steps of this task).

- [ ] **Step 5: Update `gui/barcode_generator_widget.py` call sites**

Change the import block (lines 33-38):

```python
from gui.pdf_printing import (
    load_print_settings,
    print_pdf,
    save_print_settings,
)
```

Change line 154:

```python
        print_settings = load_print_settings("barcode_generator")
```

Replace `_save_print_settings` (lines 602-607):

```python
    def _save_print_settings(self):
        save_print_settings("barcode_generator", {
            "print_mode": self.print_mode_combo.currentData(),
            "raw_zpl_target": self.raw_zpl_target_edit.text(),
            "raw_zpl_rotate": self.raw_zpl_rotate_check.isChecked(),
        })
```

Replace `_on_print_clicked`/`_on_print_qr_clicked` (lines 609-613):

```python
    def _on_print_clicked(self):
        print_pdf(self, self.last_barcode_pdf, load_print_settings("barcode_generator"))

    def _on_print_qr_clicked(self):
        print_pdf(self, self.last_qr_pdf, load_print_settings("barcode_generator"))
```

In `showEvent` (lines 245-252), delete only the last line (the `refresh_print_controls(...)` call), keeping the packing-list refresh above it:

```python
    def showEvent(self, event):
        """Override showEvent to refresh packing lists when tab becomes visible."""
        super().showEvent(event)
        # Auto-refresh packing lists when user switches to this tab
        if self.mw.session_path:
            self._refresh_packing_lists()
            self.log.debug("Auto-refreshed packing lists on tab switch")
```

- [ ] **Step 6: Update `gui/reference_labels_widget.py` call sites**

Change the import block (lines 30-35):

```python
from gui.pdf_printing import (
    load_print_settings,
    print_pdf,
    save_print_settings,
)
```

Change line 151:

```python
        print_settings = load_print_settings("reference_labels")
```

Replace `_save_print_settings` (lines 566-571):

```python
    def _save_print_settings(self):
        save_print_settings("reference_labels", {
            "print_mode": self.print_mode_combo.currentData(),
            "raw_zpl_target": self.raw_zpl_target_edit.text(),
            "raw_zpl_rotate": self.raw_zpl_rotate_check.isChecked(),
        })
```

Replace `_on_print_clicked` (lines 573-574):

```python
    def _on_print_clicked(self):
        print_pdf(self, self.last_output_pdf, load_print_settings("reference_labels"))
```

In `showEvent` (lines 580-586), delete only the last line (the `refresh_print_controls(...)` call), keeping `_update_output_dir()`:

```python
    def showEvent(self, event):
        """Handle widget show event - update output directory when tab becomes visible."""
        super().showEvent(event)
        # Update output directory when tab becomes visible
        # This ensures we pick up the current session even if it was set before widget creation
        self._update_output_dir()
```

- [ ] **Step 7: Run the full test suite**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest`
Expected: PASS, no failures or errors.

- [ ] **Step 8: Run the headless smoke test**

Run: `CI=1 QT_QPA_PLATFORM=offscreen python run_dev.py`
Expected: exits cleanly with no traceback — this constructs the full `MainWindow`, including both widgets, so it's what would catch a missed call site (matches the CI job "Smoke test (headless import + construct MainWindow)" in `.github/workflows/build_release.yml`).

- [ ] **Step 9: Lint and commit**

Run: `ruff check . --exclude shared`
Expected: no errors (confirms the trimmed imports in `gui/pdf_printing.py` didn't leave anything unused/undefined).

```bash
git add gui/pdf_printing.py gui/barcode_generator_widget.py gui/reference_labels_widget.py tests/test_pdf_printing.py
git commit -m "Scope print settings per window (Reference Labels vs Barcode Generator)"
```

---

## Task 2: Fix driver-mode render size and honor the print dialog's page range

**Files:**
- Modify: `gui/pdf_printing.py:104-138` (`_print_pdf_driver_mode`; add `_resolve_page_range`, `_apply_default_page_size`)
- Test: `tests/test_pdf_printing.py` (extend `TestPrintPdfDriverMode`, add `TestResolvePageRange`, `TestApplyDefaultPageSize`)

**Interfaces:**
- Consumes: nothing new from Task 1.
- Produces: `_resolve_page_range(printer: QPrinter, page_count: int) -> tuple[int, int]` — 0-indexed `(first_page, last_page)` inclusive range.
- Produces: `_apply_default_page_size(printer: QPrinter, document: QPdfDocument) -> None`.
- `_print_pdf_driver_mode(parent, pdf_path: Path, output_path: Path | None = None) -> bool` — same signature, fixed behavior.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_pdf_printing.py` (new imports needed at the top: `from PySide6.QtCore import QSizeF` is not required in the test file itself, but `from PySide6.QtGui import QPageSize` and `from PySide6.QtPdf import QPdfDocument` and `from PySide6.QtPrintSupport import QPrinter` are — add them):

```python
from PySide6.QtGui import QPageSize
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPrintSupport import QPrinter
```

```python
class TestResolvePageRange:
    def test_all_pages_when_range_unset(self):
        printer = QPrinter()
        assert pdf_printing._resolve_page_range(printer, page_count=5) == (0, 4)

    def test_honors_page_range_selection(self):
        printer = QPrinter()
        printer.setPrintRange(QPrinter.PrintRange.PageRange)
        printer.setFromTo(2, 3)
        assert pdf_printing._resolve_page_range(printer, page_count=5) == (1, 2)

    def test_page_range_clamped_to_document_length(self):
        printer = QPrinter()
        printer.setPrintRange(QPrinter.PrintRange.PageRange)
        printer.setFromTo(2, 99)
        assert pdf_printing._resolve_page_range(printer, page_count=5) == (1, 4)


class TestApplyDefaultPageSize:
    def test_sets_page_size_from_pdf_dimensions(self, tmp_path):
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas

        src_pdf = tmp_path / "label.pdf"
        c = canvas.Canvas(str(src_pdf), pagesize=(68 * mm, 38 * mm))
        c.drawString(5 * mm, 5 * mm, "TEST")
        c.showPage()
        c.save()

        document = QPdfDocument()
        document.load(str(src_pdf))
        printer = QPrinter()

        pdf_printing._apply_default_page_size(printer, document)

        page_size = printer.pageLayout().pageSize()
        assert page_size.width(QPageSize.Unit.Millimeter) == pytest.approx(68, abs=0.5)
        assert page_size.height(QPageSize.Unit.Millimeter) == pytest.approx(38, abs=0.5)


class TestPrintPdfDriverModeRendersAtCorrectSize:
    def test_renders_larger_than_the_old_point_size_bug(self, monkeypatch, tmp_path):
        """Regression test for the tiny-corner-stamp bug: the old code called
        document.render(page, document.pagePointSize(page).toSize()) -- a
        68x38mm label's *point* size (~193x108) used directly as *pixel*
        dimensions, then drawn 1:1 onto the printer's high-res canvas. The
        fix renders at the printer's actual device-pixel page rect instead,
        which is always larger than the raw point size once a real printer
        resolution (HighResolution mode) is applied."""
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas

        src_pdf = tmp_path / "labels.pdf"
        c = canvas.Canvas(str(src_pdf), pagesize=(68 * mm, 38 * mm))
        c.drawString(5 * mm, 5 * mm, "TEST")
        c.showPage()
        c.save()

        render_calls = []
        original_render = QPdfDocument.render

        def spy_render(self, page, size):
            render_calls.append(size)
            return original_render(self, page, size)

        monkeypatch.setattr(QPdfDocument, "render", spy_render)

        out_pdf = tmp_path / "out.pdf"
        result = pdf_printing._print_pdf_driver_mode(None, src_pdf, output_path=out_pdf)
        assert result is True

        probe = QPdfDocument()
        probe.load(str(src_pdf))
        point_size = probe.pagePointSize(0).toSize()

        assert len(render_calls) == 1
        rendered_size = render_calls[0]
        assert rendered_size.width() > point_size.width()
        assert rendered_size.height() > point_size.height()
```

`TestPrintPdfDriverMode`'s existing `test_renders_expected_page_count_to_pdf_output` needs no edits — it only asserts page *count* (2), which `_apply_default_page_size` and `_resolve_page_range` don't change (no dialog runs in the `output_path` test path, so `_resolve_page_range` returns the full 2-page range regardless of the render-size fix).

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_pdf_printing.py -v -k "ResolvePageRange or ApplyDefaultPageSize or RendersAtCorrectSize"`
Expected: FAIL — `_resolve_page_range` and `_apply_default_page_size` don't exist yet (`AttributeError`), and the render-size test fails because `rendered_size` currently equals `point_size` exactly (the bug).

- [ ] **Step 3: Implement the fix**

In `gui/pdf_printing.py`, add to the imports:

```python
from PySide6.QtCore import QSettings, QSizeF
from PySide6.QtGui import QPageSize, QPainter
```

(`QSizeF` and `QPageSize` are new; `QSettings` and `QPainter` already exist in the import list — merge rather than duplicate.)

Add two new helper functions above `_print_pdf_driver_mode`:

```python
def _resolve_page_range(printer: QPrinter, page_count: int) -> tuple[int, int]:
    """0-indexed [first, last] page range from the print dialog's page-range
    selection, or the full document if the operator left it on "All"."""
    if printer.printRange() == QPrinter.PrintRange.PageRange:
        from_page = printer.fromPage() or 1
        to_page = printer.toPage() or page_count
        return from_page - 1, min(to_page, page_count) - 1
    return 0, page_count - 1


def _apply_default_page_size(printer: QPrinter, document: QPdfDocument) -> None:
    """Set the printer's page size to match the PDF's own first-page
    dimensions, so the print dialog opens already matching the label size
    instead of the operator manually re-entering it each time. Still
    overridable by the operator inside the dialog."""
    size_pt = document.pagePointSize(0)
    if size_pt.isEmpty():
        return
    size_mm = QSizeF(size_pt.width() / 72 * 25.4, size_pt.height() / 72 * 25.4)
    printer.setPageSize(QPageSize(size_mm, QPageSize.Unit.Millimeter))
```

Replace `_print_pdf_driver_mode` (lines 104-138) with:

```python
def _print_pdf_driver_mode(parent, pdf_path: Path, output_path: Path | None = None) -> bool:
    document = QPdfDocument()
    load_error = document.load(str(pdf_path))
    if load_error != QPdfDocument.Error.None_:
        QMessageBox.critical(parent, "Print Failed", f"Could not open PDF for printing:\n\n{pdf_path}\n\n{load_error}")
        return False

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    _apply_default_page_size(printer, document)

    if output_path is not None:
        # Test-only escape hatch: PDF output needs no OS printer and no
        # dialog, so the render path is coverable headlessly (see
        # tests/test_pdf_printing.py -- dialog interaction itself isn't
        # testable in CI, matching the original D-1 design's testing note).
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(str(output_path))
    else:
        dialog = QPrintDialog(printer, parent)
        if dialog.exec() != QPrintDialog.DialogCode.Accepted:
            return False

    first_page, last_page = _resolve_page_range(printer, document.pageCount())

    try:
        painter = QPainter(printer)
        page_rect = printer.pageRect(QPrinter.Unit.DevicePixel).toRect()
        for page in range(first_page, last_page + 1):
            if page > first_page:
                printer.newPage()
            image = document.render(page, page_rect.size())
            painter.drawImage(page_rect, image)
        painter.end()
        return True
    except Exception as error:
        logger.exception("Driver print failed")
        QMessageBox.critical(parent, "Print Failed", f"Printing failed:\n\n{error}")
        return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_pdf_printing.py -v`
Expected: PASS, all tests in the file including the pre-existing ones.

- [ ] **Step 5: Run the full test suite and smoke test**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest`
Expected: PASS.

Run: `CI=1 QT_QPA_PLATFORM=offscreen python run_dev.py`
Expected: exits cleanly.

- [ ] **Step 6: Lint and commit**

Run: `ruff check . --exclude shared`

```bash
git add gui/pdf_printing.py tests/test_pdf_printing.py
git commit -m "Fix driver-mode print rendering: correct size, honor page range, default page size"
```

---

## Task 3: Remembered default printer per window (driver mode)

**Files:**
- Modify: `gui/pdf_printing.py` (extend settings shape with `driver_printer_name`; apply it in `_print_pdf_driver_mode`)
- Modify: `gui/barcode_generator_widget.py` (printer combo + wiring)
- Modify: `gui/reference_labels_widget.py` (printer combo + wiring)
- Test: `tests/test_pdf_printing.py` (extend settings round-trip + driver-mode tests)

**Interfaces:**
- Consumes: `_resolve_page_range`, `_apply_default_page_size` from Task 2 (unchanged).
- Produces: `load_print_settings(scope)` / `save_print_settings(scope, settings)` now include a fourth key, `driver_printer_name: str`.
- Produces: `_print_pdf_driver_mode(parent, pdf_path, output_path=None, driver_printer_name="") -> bool` — new optional parameter.
- Produces: `print_pdf(parent, pdf_path, settings)` now forwards `settings["driver_printer_name"]` to `_print_pdf_driver_mode`.

- [ ] **Step 1: Write the failing tests**

Update the three `TestPrintSettingsRoundTrip` tests in `tests/test_pdf_printing.py` to include the new key:

```python
class TestPrintSettingsRoundTrip:
    def test_defaults_when_nothing_saved(self, isolated_settings):
        settings = pdf_printing.load_print_settings("reference_labels")
        assert settings == {
            "print_mode": "driver", "raw_zpl_target": "", "raw_zpl_rotate": False,
            "driver_printer_name": "",
        }

    def test_save_then_load_roundtrip(self, isolated_settings):
        pdf_printing.save_print_settings(
            "reference_labels",
            {
                "print_mode": "raw_zpl", "raw_zpl_target": "ZPL-RAW-Printer",
                "raw_zpl_rotate": True, "driver_printer_name": "Labels 6x4",
            },
        )
        assert pdf_printing.load_print_settings("reference_labels") == {
            "print_mode": "raw_zpl",
            "raw_zpl_target": "ZPL-RAW-Printer",
            "raw_zpl_rotate": True,
            "driver_printer_name": "Labels 6x4",
        }

    def test_different_scopes_do_not_collide(self, isolated_settings):
        pdf_printing.save_print_settings(
            "reference_labels",
            {
                "print_mode": "raw_zpl", "raw_zpl_target": "Labels 6x4",
                "raw_zpl_rotate": False, "driver_printer_name": "Labels 6x4",
            },
        )
        pdf_printing.save_print_settings(
            "barcode_generator",
            {
                "print_mode": "driver", "raw_zpl_target": "Barcodes",
                "raw_zpl_rotate": True, "driver_printer_name": "Barcodes",
            },
        )

        ref_settings = pdf_printing.load_print_settings("reference_labels")
        barcode_settings = pdf_printing.load_print_settings("barcode_generator")
        assert ref_settings["driver_printer_name"] == "Labels 6x4"
        assert barcode_settings["driver_printer_name"] == "Barcodes"
```

Add new tests for the printer-name application:

```python
class TestPrintPdfDriverModeDefaultPrinter:
    def test_applies_stored_default_printer_name(self, monkeypatch, tmp_path):
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas

        src_pdf = tmp_path / "labels.pdf"
        c = canvas.Canvas(str(src_pdf), pagesize=(68 * mm, 38 * mm))
        c.drawString(5 * mm, 5 * mm, "TEST")
        c.showPage()
        c.save()

        calls = []
        original_set_name = QPrinter.setPrinterName

        def spy_set_name(self, name):
            calls.append(name)
            return original_set_name(self, name)

        monkeypatch.setattr(QPrinter, "setPrinterName", spy_set_name)

        out_pdf = tmp_path / "out.pdf"
        result = pdf_printing._print_pdf_driver_mode(
            None, src_pdf, output_path=out_pdf, driver_printer_name="Labels 6x4"
        )

        assert result is True
        assert calls == ["Labels 6x4"]

    def test_blank_default_printer_name_does_not_set_printer_name(self, monkeypatch, tmp_path):
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas

        src_pdf = tmp_path / "labels.pdf"
        c = canvas.Canvas(str(src_pdf), pagesize=(68 * mm, 38 * mm))
        c.drawString(5 * mm, 5 * mm, "TEST")
        c.showPage()
        c.save()

        calls = []
        monkeypatch.setattr(QPrinter, "setPrinterName", lambda self, name: calls.append(name))

        out_pdf = tmp_path / "out.pdf"
        pdf_printing._print_pdf_driver_mode(None, src_pdf, output_path=out_pdf)

        assert calls == []


class TestPrintPdfDispatchesDriverPrinterName:
    def test_print_pdf_forwards_stored_printer_name(self, monkeypatch, tmp_path):
        called = Mock()
        monkeypatch.setattr(pdf_printing, "_print_pdf_driver_mode", called)

        pdf_printing.print_pdf(
            None, tmp_path / "x.pdf",
            {
                "print_mode": "driver", "raw_zpl_target": "", "raw_zpl_rotate": False,
                "driver_printer_name": "Labels 6x4",
            },
        )

        called.assert_called_once_with(None, tmp_path / "x.pdf", driver_printer_name="Labels 6x4")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_pdf_printing.py -v`
Expected: FAIL — `driver_printer_name` missing from settings dicts, `_print_pdf_driver_mode` doesn't accept the new keyword, `print_pdf` doesn't forward it.

- [ ] **Step 3: Implement the setting, the parameter, and the dispatch**

In `gui/pdf_printing.py`, extend `load_print_settings`/`save_print_settings`:

```python
def load_print_settings(scope: str) -> dict:
    qs = QSettings(*_SETTINGS)
    return {
        "print_mode": qs.value(f"{scope}/print_mode", "driver"),
        "raw_zpl_target": qs.value(f"{scope}/raw_zpl_target", ""),
        "raw_zpl_rotate": qs.value(f"{scope}/raw_zpl_rotate", False, type=bool),
        "driver_printer_name": qs.value(f"{scope}/driver_printer_name", ""),
    }


def save_print_settings(scope: str, settings: dict) -> None:
    qs = QSettings(*_SETTINGS)
    qs.setValue(f"{scope}/print_mode", settings["print_mode"])
    qs.setValue(f"{scope}/raw_zpl_target", settings["raw_zpl_target"])
    qs.setValue(f"{scope}/raw_zpl_rotate", settings["raw_zpl_rotate"])
    qs.setValue(f"{scope}/driver_printer_name", settings["driver_printer_name"])
```

Update `print_pdf` to forward the new field:

```python
def print_pdf(parent: QWidget | None, pdf_path: Path, settings: dict) -> bool:
    if settings.get("print_mode") == "raw_zpl":
        return _print_pdf_raw_zpl_mode(parent, pdf_path, settings)
    return _print_pdf_driver_mode(parent, pdf_path, driver_printer_name=settings.get("driver_printer_name", ""))
```

Update `_print_pdf_driver_mode`'s signature and apply the name right after constructing `printer`:

```python
def _print_pdf_driver_mode(
    parent, pdf_path: Path, output_path: Path | None = None, driver_printer_name: str = ""
) -> bool:
    document = QPdfDocument()
    load_error = document.load(str(pdf_path))
    if load_error != QPdfDocument.Error.None_:
        QMessageBox.critical(parent, "Print Failed", f"Could not open PDF for printing:\n\n{pdf_path}\n\n{load_error}")
        return False

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    if driver_printer_name:
        printer.setPrinterName(driver_printer_name)
    _apply_default_page_size(printer, document)

    if output_path is not None:
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(str(output_path))
    else:
        dialog = QPrintDialog(printer, parent)
        if dialog.exec() != QPrintDialog.DialogCode.Accepted:
            return False

    first_page, last_page = _resolve_page_range(printer, document.pageCount())

    try:
        painter = QPainter(printer)
        page_rect = printer.pageRect(QPrinter.Unit.DevicePixel).toRect()
        for page in range(first_page, last_page + 1):
            if page > first_page:
                printer.newPage()
            image = document.render(page, page_rect.size())
            painter.drawImage(page_rect, image)
        painter.end()
        return True
    except Exception as error:
        logger.exception("Driver print failed")
        QMessageBox.critical(parent, "Print Failed", f"Printing failed:\n\n{error}")
        return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_pdf_printing.py -v`
Expected: PASS.

- [ ] **Step 5: Add the printer picker to `gui/barcode_generator_widget.py`**

Add `QPrinterInfo` to the imports (new import block, since `QtPrintSupport` isn't currently imported in this file):

```python
from PySide6.QtPrintSupport import QPrinterInfo
```

After the `raw_zpl_rotate_check` block (lines 176-178) and before `_update_zpl_controls_enabled` (line 180), add:

```python
        printer_row = QHBoxLayout()
        printer_row.addWidget(QLabel("Default printer (driver mode):"))
        self.driver_printer_combo = QComboBox()
        self.driver_printer_combo.addItem("(Windows default)", "")
        for info in QPrinterInfo.availablePrinters():
            self.driver_printer_combo.addItem(info.printerName(), info.printerName())
        printer_index = self.driver_printer_combo.findData(print_settings["driver_printer_name"])
        if printer_index >= 0:
            self.driver_printer_combo.setCurrentIndex(printer_index)
        printer_row.addWidget(self.driver_printer_combo, 1)
        layout.addLayout(printer_row)
```

Update `_update_zpl_controls_enabled` and the signal connections (lines 180-189) so the driver-printer combo is enabled/disabled opposite the raw-ZPL controls, and its selection is saved:

```python
        def _update_zpl_controls_enabled():
            is_zpl = self.print_mode_combo.currentData() == "raw_zpl"
            self.raw_zpl_target_edit.setEnabled(is_zpl)
            self.raw_zpl_rotate_check.setEnabled(is_zpl)
            self.driver_printer_combo.setEnabled(not is_zpl)

        _update_zpl_controls_enabled()
        self.print_mode_combo.currentIndexChanged.connect(_update_zpl_controls_enabled)
        self.print_mode_combo.currentIndexChanged.connect(self._save_print_settings)
        self.raw_zpl_target_edit.editingFinished.connect(self._save_print_settings)
        self.raw_zpl_rotate_check.toggled.connect(self._save_print_settings)
        self.driver_printer_combo.currentIndexChanged.connect(self._save_print_settings)
```

Update `_save_print_settings`:

```python
    def _save_print_settings(self):
        save_print_settings("barcode_generator", {
            "print_mode": self.print_mode_combo.currentData(),
            "raw_zpl_target": self.raw_zpl_target_edit.text(),
            "raw_zpl_rotate": self.raw_zpl_rotate_check.isChecked(),
            "driver_printer_name": self.driver_printer_combo.currentData(),
        })
```

- [ ] **Step 6: Add the printer picker to `gui/reference_labels_widget.py`**

Same changes, mirrored. Add the import:

```python
from PySide6.QtPrintSupport import QPrinterInfo
```

After the `raw_zpl_rotate_check` block (lines 173-175) and before `_update_zpl_controls_enabled` (line 177):

```python
        printer_row = QHBoxLayout()
        printer_row.addWidget(QLabel("Default printer (driver mode):"))
        self.driver_printer_combo = QComboBox()
        self.driver_printer_combo.addItem("(Windows default)", "")
        for info in QPrinterInfo.availablePrinters():
            self.driver_printer_combo.addItem(info.printerName(), info.printerName())
        printer_index = self.driver_printer_combo.findData(print_settings["driver_printer_name"])
        if printer_index >= 0:
            self.driver_printer_combo.setCurrentIndex(printer_index)
        printer_row.addWidget(self.driver_printer_combo, 1)
        layout.addLayout(printer_row)
```

```python
        def _update_zpl_controls_enabled():
            is_zpl = self.print_mode_combo.currentData() == "raw_zpl"
            self.raw_zpl_target_edit.setEnabled(is_zpl)
            self.raw_zpl_rotate_check.setEnabled(is_zpl)
            self.driver_printer_combo.setEnabled(not is_zpl)

        _update_zpl_controls_enabled()
        self.print_mode_combo.currentIndexChanged.connect(_update_zpl_controls_enabled)
        self.print_mode_combo.currentIndexChanged.connect(self._save_print_settings)
        self.raw_zpl_target_edit.editingFinished.connect(self._save_print_settings)
        self.raw_zpl_rotate_check.toggled.connect(self._save_print_settings)
        self.driver_printer_combo.currentIndexChanged.connect(self._save_print_settings)
```

```python
    def _save_print_settings(self):
        save_print_settings("reference_labels", {
            "print_mode": self.print_mode_combo.currentData(),
            "raw_zpl_target": self.raw_zpl_target_edit.text(),
            "raw_zpl_rotate": self.raw_zpl_rotate_check.isChecked(),
            "driver_printer_name": self.driver_printer_combo.currentData(),
        })
```

- [ ] **Step 7: Run the full test suite and smoke test**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest`
Expected: PASS.

Run: `CI=1 QT_QPA_PLATFORM=offscreen python run_dev.py`
Expected: exits cleanly — this is the step that actually exercises `QPrinterInfo.availablePrinters()` against the offscreen platform plugin (which reports zero printers in CI, so the combo ends up with just the "(Windows default)" entry — that's fine, confirms no crash on an empty printer list).

- [ ] **Step 8: Lint and commit**

Run: `ruff check . --exclude shared`

```bash
git add gui/pdf_printing.py gui/barcode_generator_widget.py gui/reference_labels_widget.py tests/test_pdf_printing.py
git commit -m "Add remembered default driver-mode printer per window"
```

---

## Task 4: Drop the synthetic order counter and shrink original page content

**Files:**
- Modify: `shopify_tool/pdf_processor.py:44-224` (`process_reference_labels` loop), `:499-522` (`create_reference_order_map` — deleted), `:525-556` (`create_reference_overlay` — signature change)
- Test: `tests/test_pdf_processor.py` (new)

**Interfaces:**
- Removes: `create_reference_order_map(sorted_pages: list) -> dict[str, int]`.
- Produces: `create_reference_overlay(reference_number: str, page_width: float, page_height: float) -> BytesIO` (drops the `order_number` parameter).
- Produces: module-level constant `_CONTENT_SCALE = 0.88` in `shopify_tool/pdf_processor.py`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pdf_processor.py`:

```python
"""Tests for shopify_tool.pdf_processor's reference-overlay content-shrink +
barcode strip. See
docs/superpowers/specs/2026-08-10-print-polish-and-reference-barcode-design.md."""
import inspect
from io import BytesIO

import pytest
from pypdf import PdfReader
from reportlab.pdfgen import canvas

from shopify_tool import pdf_processor


def _make_courier_pdf(path, width_pt=288, height_pt=432, name="Acme Warehouse Co"):
    c = canvas.Canvas(str(path), pagesize=(width_pt, height_pt))
    c.drawString(20, height_pt - 20, name)
    c.showPage()
    c.save()


class TestCreateReferenceOverlaySignature:
    def test_order_number_parameter_removed(self):
        params = list(inspect.signature(pdf_processor.create_reference_overlay).parameters)
        assert params == ["reference_number", "page_width", "page_height"]


class TestCreateReferenceOrderMapRemoved:
    def test_function_no_longer_exists(self):
        assert not hasattr(pdf_processor, "create_reference_order_map")


class TestCreateReferenceOverlayContent:
    def test_shows_ref_text_without_counter_prefix(self):
        overlay_pdf = pdf_processor.create_reference_overlay("REF-001", 288, 432)
        text = PdfReader(overlay_pdf).pages[0].extract_text()
        assert "REF: REF-001" in text
        assert "1. REF" not in text


class TestProcessReferenceLabelsShrink:
    def test_matched_page_shrinks_content_but_keeps_page_size(self, tmp_path):
        pdf_path = tmp_path / "courier.pdf"
        _make_courier_pdf(pdf_path)

        csv_path = tmp_path / "mapping.csv"
        csv_path.write_text(
            "PostOne,Tracking,Reference,Col3,Col4,Col5,Name\n"
            ",,REF-001,,,,Acme Warehouse Co\n"
        )

        output_dir = tmp_path / "out"
        output_dir.mkdir()

        result = pdf_processor.process_reference_labels(str(pdf_path), str(csv_path), str(output_dir))

        assert result["matched"] == 1
        reader = PdfReader(result["output_file"])
        assert len(reader.pages) == 1
        page = reader.pages[0]
        # Shrink is a content transform, not a page-size change -- the
        # output page must stay the same physical size as the courier
        # label stock.
        assert float(page.mediabox.width) == pytest.approx(288)
        assert float(page.mediabox.height) == pytest.approx(432)
        assert "REF: REF-001" in page.extract_text()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_pdf_processor.py -v`
Expected: FAIL — `create_reference_overlay` still takes 4 params (`reference_number, order_number, page_width, page_height`), `create_reference_order_map` still exists, and the shrink transform hasn't been added yet (the ref-text assertion in the full-flow test will actually already pass since `create_reference_overlay` already draws `REF: {ref}` text today — but the signature test and the `create_reference_order_map` removal test will fail).

- [ ] **Step 3: Implement the counter removal and shrink transform**

In `shopify_tool/pdf_processor.py`, add the import and constant near the top (after the existing imports, before `class PDFProcessorError`):

```python
from pypdf import PdfReader, PdfWriter, Transformation
```

(replaces the current `from pypdf import PdfReader, PdfWriter` at line 21)

Add the constant right after the logger line:

```python
logger = logging.getLogger(__name__)

_CONTENT_SCALE = 0.88
```

Replace the overlay-adding loop inside `process_reference_labels` (currently lines 166-189):

```python
        writer = PdfWriter()

        for page_data in sorted_pages:
            page = page_data['page']
            ref = page_data['ref']

            if ref:
                try:
                    page_width = float(page.mediabox.width)
                    page_height = float(page.mediabox.height)

                    transform = Transformation().scale(_CONTENT_SCALE, _CONTENT_SCALE).translate(
                        tx=page_width * (1 - _CONTENT_SCALE) / 2,
                        ty=page_height * (1 - _CONTENT_SCALE),
                    )
                    page.add_transformation(transform)

                    overlay = create_reference_overlay(ref, page_width, page_height)
                    page.merge_page(PdfReader(overlay).pages[0])

                except Exception:
                    logger.exception(f"Failed to add overlay for ref {ref}")

            writer.add_page(page)
```

Delete `create_reference_order_map` entirely (currently lines 499-522).

Replace `create_reference_overlay` (currently lines 525-556):

```python
def create_reference_overlay(
    reference_number: str,
    page_width: float,
    page_height: float
) -> BytesIO:
    """
    Create PDF overlay with the Reference Number, positioned in the bottom
    strip freed up by process_reference_labels()'s content-shrink transform.

    Args:
        reference_number: Reference number to display
        page_width: Page width in points
        page_height: Page height in points

    Returns:
        BytesIO: PDF overlay buffer
    """
    packet = BytesIO()
    can = canvas.Canvas(packet, pagesize=(page_width, page_height))

    strip_height = page_height * (1 - _CONTENT_SCALE)
    margin = 8

    can.setFont("Helvetica-Bold", 10)
    text = f"REF: {reference_number}"
    text_y = strip_height / 2 - 3
    can.drawString(margin, text_y, text)

    can.save()
    packet.seek(0)

    return packet
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_pdf_processor.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full test suite**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest`
Expected: PASS. (No other module calls `create_reference_order_map` or `create_reference_overlay` with the old 4-arg signature — confirmed by `grep -rn "create_reference_order_map\|create_reference_overlay" --include="*.py" .` before starting this task.)

- [ ] **Step 6: Lint and commit**

Run: `ruff check . --exclude shared`

```bash
git add shopify_tool/pdf_processor.py tests/test_pdf_processor.py
git commit -m "Reference Labels: drop synthetic order counter, shrink content to reserve a bottom strip"
```

---

## Task 5: Add the Code-128 barcode to the reserved strip

**Files:**
- Modify: `shopify_tool/pdf_processor.py` (`create_reference_overlay` — add barcode)
- Test: `tests/test_pdf_processor.py` (extend)

**Interfaces:**
- Consumes: `_CONTENT_SCALE` constant and `create_reference_overlay(reference_number, page_width, page_height)` signature from Task 4 (unchanged signature — this task only changes the function body).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_pdf_processor.py`:

```python
class TestCreateReferenceOverlayBarcode:
    def test_draws_code128_barcode_with_reference_value(self, monkeypatch):
        from reportlab.graphics.barcode import code128

        calls = []
        original_draw_on = code128.Code128.drawOn

        def spy_draw_on(self, canv, x, y, **kwargs):
            calls.append((self.value, x, y))
            return original_draw_on(self, canv, x, y, **kwargs)

        monkeypatch.setattr(code128.Code128, "drawOn", spy_draw_on)

        pdf_processor.create_reference_overlay("REF-001", 288, 432)

        assert len(calls) == 1
        value, x, y = calls[0]
        assert value == "REF-001"
        assert x > 0
        assert y >= 0

    def test_overlay_still_valid_single_page_pdf(self):
        overlay_pdf = pdf_processor.create_reference_overlay("REF-001", 288, 432)
        reader = PdfReader(overlay_pdf)
        assert len(reader.pages) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_pdf_processor.py -v -k Barcode`
Expected: FAIL — `code128.Code128.drawOn` is never called (no barcode drawn yet).

- [ ] **Step 3: Add the barcode to `create_reference_overlay`**

In `shopify_tool/pdf_processor.py`, add the import (near the top, alongside the `reportlab.pdfgen` import):

```python
from reportlab.graphics.barcode import code128
from reportlab.pdfgen import canvas
```

Replace `create_reference_overlay`'s body (from Task 4) to add the barcode after the REF text:

```python
def create_reference_overlay(
    reference_number: str,
    page_width: float,
    page_height: float
) -> BytesIO:
    """
    Create PDF overlay with the Reference Number and a horizontal Code-128
    barcode encoding it, positioned in the bottom strip freed up by
    process_reference_labels()'s content-shrink transform.

    Args:
        reference_number: Reference number to display and encode
        page_width: Page width in points
        page_height: Page height in points

    Returns:
        BytesIO: PDF overlay buffer
    """
    packet = BytesIO()
    can = canvas.Canvas(packet, pagesize=(page_width, page_height))

    strip_height = page_height * (1 - _CONTENT_SCALE)
    margin = 8

    can.setFont("Helvetica-Bold", 10)
    text = f"REF: {reference_number}"
    text_y = strip_height / 2 - 3
    can.drawString(margin, text_y, text)
    text_width = can.stringWidth(text, "Helvetica-Bold", 10)

    bar_height = strip_height * 0.6
    barcode = code128.Code128(reference_number, barHeight=bar_height, barWidth=0.8)
    barcode.drawOn(can, margin + text_width + 12, (strip_height - bar_height) / 2)

    can.save()
    packet.seek(0)

    return packet
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_pdf_processor.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full test suite and smoke test**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest`
Expected: PASS.

Run: `CI=1 QT_QPA_PLATFORM=offscreen python run_dev.py`
Expected: exits cleanly.

- [ ] **Step 6: Lint and commit**

Run: `ruff check . --exclude shared`

```bash
git add shopify_tool/pdf_processor.py tests/test_pdf_processor.py
git commit -m "Add Code-128 barcode encoding the Reference Number to the overlay strip"
```

- [ ] **Step 7: Manual QA (not automatable — physical printer required)**

Per the design spec's Testing section:
- Print a real batch in driver mode to an actual Windows-installed printer from both windows; confirm labels print at correct physical size and that selecting a page range in the print dialog only prints that range.
- Process a real courier PDF through Reference Labels; confirm the barcode strip scans correctly with a handheld scanner and doesn't visually overlap the courier's own label content. If `_CONTENT_SCALE = 0.88` leaves too little or too much strip space for the actual courier PDFs in use, adjust the constant in `shopify_tool/pdf_processor.py` (see the design spec's Follow-ups).
- Set a raw ZPL target/printer in one window (Reference Labels or Barcode Generator) and confirm the other window's settings are unaffected.
- Confirm the driver-mode printer combo in each window lists real installed Windows printers and that selecting one persists across restarting the app.

---

## Self-Review Notes

- **Spec coverage:** D-1 → Task 1. D-2 (render fix + page range + default page size) → Task 2; D-2's default-printer picker → Task 3. D-3 (drop counter, shrink, barcode) → Tasks 4-5. All three Goals and all three numbered Design sections in the spec have a corresponding task.
- **Placeholder scan:** no TBD/TODO; every step has runnable code or an exact command.
- **Type/name consistency:** `_CONTENT_SCALE` defined once in Task 4, reused unchanged in Task 5. `create_reference_overlay`'s 3-parameter signature introduced in Task 4 is unchanged by Task 5 (only the function body changes). `driver_printer_name` key name is consistent across `load_print_settings`/`save_print_settings`/`_print_pdf_driver_mode`/both widgets' `_save_print_settings` from the point it's introduced in Task 3 onward. `_resolve_page_range`/`_apply_default_page_size` introduced in Task 2 are consumed unchanged (by name) in Task 3's rewritten `_print_pdf_driver_mode`.
