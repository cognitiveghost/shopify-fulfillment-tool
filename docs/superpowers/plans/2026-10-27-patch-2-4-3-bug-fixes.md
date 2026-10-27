# Patch 2.4.3 Bug Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Match every Reference Labels page the example run missed, flag Repeat only for orders the Packer packed,
surface ended-with-unpacked Packer lists, and stop writing `"nan"` for empty notes/tags.

**Architecture:** Five independent fixes in the Shopify tool. No Packing Tool change, no `shared/` change, no UI or
new user-facing text. Labels: whitespace-tolerant whole-token tracking match, then a barcode pass (pypdfium2 render
+ zxing-cpp) on pages still unmatched, and customs-declaration pages excluded from the duplicate count.

**Tech Stack:** Python 3.11+, pandas, pypdf, pikepdf, pypdfium2, reportlab (tests), new `zxing-cpp`.

**Spec:** `docs/superpowers/specs/2026-10-27-patch-2-4-3-bug-fixes-design.md`. Read it first; section numbers below (§)
refer to it.

## Global Constraints

- New dependency only `zxing-cpp>=3.0`, imported lazily inside the barcode pass; a failed import degrades to today's behaviour.
- Tracking floor: a CSV tracking number counts only when `len(t) >= 8`.
- Never commit anything from `~/Desktop/Server./` (customer PII). Test PDFs are synthetic, built with reportlab.
- No bare UI strings: this patch adds none. If you find you need one, stop and report.
- Gate: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` and `ruff check .`. A pytest-guard hook blocks Bash
  text containing "pytest" in other forms; append a test path to that exact form, nothing else (no `-k`, no `-x`).
- `/usr/bin/git`, one plain git command per Bash call; commit with `git commit -F <absolute path to message file>`;
  message ends with the attribution lines the session gives you.
- The suite takes ~10 min; run single files while iterating and the full gate once at the end (Task 7).

## Review Focus

1. A short or empty CSV tracking value (e.g. `"1234"`, `""`) must never match a page; covered in Task 1.
2. A tracking number printed inside a longer number (`119L 37349396973` vs tracking `9L37349396973`) must not match; Task 1.
3. A machine without a working `zxing-cpp` (import fails) or a PDF pdfium cannot open must still finish the run, pages unmatched; Task 2.
4. An order packed in *this* session must still be Repeat after the rule change, while a history-only order is not; Task 4.
5. A session a person stored as `completed` whose list block says `incomplete` must keep reading `incomplete`, not `paused`; Task 5.

---

### Task 1: Tracking numbers match with whitespace ignored, as whole tokens (§4.1)

**Files:**
- Modify: `shopify_tool/pdf_processor.py` (`match_reference` step 2, ~line 452; delete `extract_tracking_numbers`, ~line 511)
- Test: `tests/test_pdf_processor.py` (new class `TestTrackingMatch`)

**Interfaces:**
- Produces: `match_reference(page_text: str, mapping: dict) -> dict | None` unchanged signature; step 2 returns
  `{'ref', 'verified', 'method': 'tracking'}`.
- Mapping shape (from `load_csv_mapping`): `{'by_postone': {}, 'by_tracking': {t: {'ref', 'name'}}, 'by_name': {}, 'refs': set(), 'rows': int}`.

- [ ] **Step 1: Write the failing tests** (build mappings by hand with a small helper `_mapping(tracking_to_ref: dict)`
  returning the shape above with empty `by_postone`/`by_name`, `name` = `""`)

```python
class TestTrackingMatch:
    def test_tracking_printed_with_spaces_matches(self):
        m = _mapping({"9L37349396976": "#119850"})
        assert pdf_processor.match_reference("Poids\n9L 3734939697 6\nSite", m)["ref"] == "#119850"

    def test_ten_digit_tracking_matches(self):
        m = _mapping({"9819014181": "#120090"})
        r = pdf_processor.match_reference("AWB Nr\n9819014181\nOrigin", m)
        assert (r["ref"], r["method"]) == ("#120090", "tracking")

    def test_tracking_inside_a_longer_number_does_not_match(self):
        m = _mapping({"9L37349396973": "#1"})
        assert pdf_processor.match_reference("x 119L 37349396973 y", m) is None

    def test_short_or_empty_tracking_never_matches(self):
        m = _mapping({"1234": "#1", "": "#2"})
        assert pdf_processor.match_reference("ref 1234 here", m) is None

    def test_two_trackings_for_different_refs_is_no_tracking_match(self):
        m = _mapping({"AB12345678": "#1", "CD87654321": "#2"})
        assert pdf_processor.match_reference("AB12345678 CD87654321", m) is None

    def test_two_trackings_for_the_same_ref_match(self):
        m = _mapping({"AB12345678": "#1", "CD87654321": "#1"})
        assert pdf_processor.match_reference("AB12345678 CD87654321", m)["ref"] == "#1"
```

- [ ] **Step 2: Run** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_pdf_processor.py`
  Expected: the spaced, 10-digit and same-ref tests FAIL; others may pass.

- [ ] **Step 3: Implement step 2 of `match_reference`** exactly per §4.1: `compact = re.sub(r"\s+", "", page_text).upper()`;
  for each `t, data` in `mapping['by_tracking']` with `len(t) >= 8`: prefilter `t.upper() in compact`, confirm with
  `re.search(r"(?<![A-Z0-9])" + r"\s*".join(map(re.escape, t.upper())) + r"(?![A-Z0-9])", page_text, re.I)`.
  Collect distinct REFs: exactly one → return it with `verified=check_name_presence(data['name'], page_text)`;
  more than one → `logger.info(...)` and fall through to the name step. Delete `extract_tracking_numbers`.

- [ ] **Step 4: Run** the same command. Expected: PASS (whole file).

- [ ] **Step 5: Commit** `fix(labels): match tracking numbers printed with spaces or under 12 chars`

### Task 2: Barcode fallback for pages text cannot match (§4.2)

**Files:**
- Modify: `requirements.txt` (add after the `pypdfium2` line: `zxing-cpp>=3.0           # barcode reading for Reference Labels pages with no text layer`)
- Modify: `shopify_tool/pdf_processor.py` (new `match_barcodes`, new `_barcode_pass`, call in `process_reference_labels` after the text loop; result key)
- Test: `tests/test_pdf_processor.py` (new class `TestBarcodeFallback`)

**Interfaces:**
- Produces: `match_barcodes(values: list[str], mapping: dict) -> dict | None` returning `{'ref': str, 'verified': False, 'method': 'barcode'}` or None.
- Produces: `_barcode_values(pdf_path: str, indices: list[int]) -> dict[int, list[str]]` (decoded texts per page index; `{}` when zxing-cpp or pdfium is unavailable).
- Produces: result dict key `'barcode_matched': int` (stamped pages with method `'barcode'`), beside `name_matched`.

- [ ] **Step 1: Install** `.venv/bin/python -m pip install "zxing-cpp>=3.0"` (the worktree's `.venv` is a symlink to the
  main checkout's; installing there is expected). Check: `.venv/bin/python -c "import zxingcpp"` prints nothing.

- [ ] **Step 2: Write the failing tests**

```python
def _barcode_only_pdf(path, value):
    """A page with no text layer, only a Code-128 drawn as vector bars (mimics Packeta)."""
    from reportlab.graphics.barcode import code128
    c = canvas.Canvas(str(path), pagesize=(360, 286))
    code128.Code128(value, barHeight=60, barWidth=1.2).drawOn(c, 20, 100)
    c.showPage(); c.save()

class TestBarcodeFallback:
    def test_match_barcodes_exact_postone(self):
        m = {**_mapping({}), "by_postone": {"P3362241198": {"ref": "#119770", "name": ""}}}
        assert match_barcodes(["P3362241198"], m)["ref"] == "#119770"

    def test_match_barcodes_tracking_as_token_inside_value(self):
        r = match_barcodes(["40858732093-14008"], _mapping({"40858732093": "#121000"}))
        assert (r["ref"], r["method"], r["verified"]) == ("#121000", "barcode", False)

    def test_match_barcodes_tracking_inside_longer_digits_does_not_match(self):
        assert match_barcodes(["408587320939"], _mapping({"40858732093": "#1"})) is None

    def test_match_barcodes_ambiguous_or_none(self):
        m = _mapping({"AB12345678": "#1", "CD87654321": "#2"})
        assert match_barcodes(["AB12345678", "CD87654321"], m) is None
        assert match_barcodes(["ZZZ"], m) is None

    def _run_packeta(self, tmp_path):
        pdf = tmp_path / "packeta.pdf"; _barcode_only_pdf(pdf, "40858732093-14008")
        csv_path = tmp_path / "m.csv"
        csv_path.write_text("PostOne,Tracking,Reference,C3,C4,C5,Product\nP3286312240,40858732093,#121000,,,,X\n")
        out = tmp_path / "out"; out.mkdir()
        return pdf_processor.process_reference_labels(str(pdf), str(csv_path), str(out))

    def test_textless_page_matches_by_barcode(self, tmp_path):
        r = self._run_packeta(tmp_path)
        assert (r["matched"], r["barcode_matched"], r["missing_refs"]) == (1, 1, [])

    def test_run_completes_when_zxing_is_missing(self, tmp_path, monkeypatch):
        monkeypatch.setitem(sys.modules, "zxingcpp", None)  # makes `import zxingcpp` raise ImportError
        r = self._run_packeta(tmp_path)
        assert (r["matched"], r["unmatched"], r["barcode_matched"]) == (0, 1, 0)
```

  Note: the CSV in these tests uses column 6 as the name column (as `load_csv_mapping` reads it); the existing
  `_MAPPING` in this file follows the same layout.

- [ ] **Step 3: Run** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_pdf_processor.py`. Expected: new tests FAIL (ImportError / KeyError `barcode_matched`).

- [ ] **Step 4: Implement**
  - `match_barcodes`: rule 1, a value equal to a `by_postone` or `by_tracking` key, gives its REF. Rule 2, a tracking `t`
    with `len(t) >= 8` and `re.search(r"(?<![A-Z0-9])" + re.escape(t.upper()) + r"(?![A-Z0-9])", value.upper())`,
    gives its REF. Collect REFs from both rules over all values: exactly one → match, else None.
  - `_barcode_values`: `try: import zxingcpp, pypdfium2 as pdfium` and `pdfium.PdfDocument(pdf_path)`; on any exception
    `logger.warning(...)` once and return `{}`. Per index: `page.render(scale=300 / 72, grayscale=True).to_numpy()`,
    then `[r.text for r in zxingcpp.read_barcodes(array)]`. Per-page exceptions → `logger.warning`, skip that page.
    Close the document in `finally`. Add `# ponytail: no progress phase for the barcode pass; add one if all-image PDFs make Cancel feel stuck.`
  - In `process_reference_labels`, after the Step 3 loop: unmatched indices → `_barcode_values` → `match_barcodes` →
    fill `ref`/`verified`/`method` on those `page_data_list` entries. Count `barcode_matched` in the stamping loop
    like `name_matched`, and add it to the returned dict.

- [ ] **Step 5: Run** the same command. Expected: PASS. Then `ruff check .` clean.

- [ ] **Step 6: Commit** `feat(labels): read barcodes on pages with no usable text` (include `requirements.txt`).

### Task 3: Customs-declaration pages are not duplicates (§4.3)

**Files:**
- Modify: `shopify_tool/pdf_processor.py` (`process_reference_labels`: per-page `customs` flag; `duplicate_refs` computation)
- Test: `tests/test_pdf_processor.py` (class `TestCustomsPages`)

**Interfaces:**
- Produces: `is_customs_page(text: str) -> bool`, true when `"customs declaration" in text.lower()` and `extract_postone_number(text) is None`.

- [ ] **Step 1: Write the failing tests.** Build a 2-page PDF with reportlab: page 1 text `P3286312240 Acme`, page 2 text
  `Customs Declaration - CN23` and `P3286312240`-free but containing tracking `AB12345678`. CSV row:
  `P3286312240,AB12345678,#7,,,,X`. Assert `duplicate_refs == []` and `matched == 2`. Second test: two plain label
  pages both with `P3286312240` → `duplicate_refs == ["#7"]`. Third: `is_customs_page("CN22 P1234567890 label") is False`,
  `is_customs_page("Customs Declaration - CN23") is True`.

- [ ] **Step 2: Run** the file. Expected: first test FAILS (`duplicate_refs == ["#7"]`).

- [ ] **Step 3: Implement.** Store `'customs': is_customs_page(page_texts[i])` in each `page_data_list` entry (False for
  barcode-only pages, whose text is empty). Build `counts` for `duplicate_refs` from stamped pages whose `customs` is
  False. `stamped_refs`, `matched` and `missing_refs` stay as they are.

- [ ] **Step 4: Run** the file. Expected: PASS.

- [ ] **Step 5: Commit** `fix(labels): CN23 customs pages no longer warn as duplicate REFs`

### Task 4: Repeat means packed (§5)

**Files:**
- Modify: `shopify_tool/analysis.py:879-932` (`_detect_repeated_orders` rule + docstring), and its call at `analysis.py:1136-1137` if you drop `current_session`
- Create: `docs/adr/0023-repeat-means-packed.md`
- Modify: `docs/adr/0012-fulfillment-history-follows-the-session.md` (one line under the title: `**Superseded in part by 0023** (detection: only packed orders are Repeat).`)
- Modify: `CONTEXT.md` (~line 397, "Repeat order" entry)
- Test: `tests/test_analysis.py` (~lines 560-625), `tests/audit/test_02_repeat_orders.py`, `tests/test_core.py` (~300-340)

**Interfaces:**
- `_detect_repeated_orders(final_df, history_df, ...) -> pd.Series`: same return. A row counts only when its `Source`
  column equals `"packed"`. No `Source` column → nothing counts.

- [ ] **Step 1: Add the failing test** in `tests/test_analysis.py`:
  `test_order_only_in_another_sessions_history_is_not_repeat`. Use a history frame with one row
  `{Order_Number: "#1", Execution_Date: "2026-10-01", Session: "S0", Source: "history"}`, final_df with `#1`, and
  `current_session="S1"` → result `[""]`. Also `test_order_packed_in_this_session_is_still_repeat`: row with
  `Session: "S1", Source: "packed"`, `current_session="S1"` → `["Repeat"]`.

- [ ] **Step 2: Run** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_analysis.py`. Expected: the first new test FAILS.

- [ ] **Step 3: Implement** `counts = source == "packed"`. Remove the now-unused session and legacy-date code inside
  the function, and rewrite the docstring table to one rule. Keep the `today` parameter, since callers pass it; drop it
  only if nothing else in the function uses it *and* the call sites are just `analysis.py:1137`. Do the same for
  `current_session`. Do not change `core.analyse`, `packed_orders.py` or `fulfillment_history.py`.

- [ ] **Step 4: Run** `tests/test_analysis.py`, `tests/audit/test_02_repeat_orders.py`, `tests/test_core.py`,
  `tests/test_packed_orders.py`, `tests/test_packing_lists.py`, `tests/replay/test_replay.py` (one command each).
  For each failure: if the test's Repeat comes **only** from fulfillment-history rows (no `packing_progress`
  `completed_orders` / `Source == "packed"` in its setup), invert the assertion to "not Repeat" and rename the test to
  say so (e.g. `..._is_flagged` → `..._is_not_flagged_without_packing`). Never delete one. If a failing test *does*
  have a packed signal, stop and report BLOCKED with its name. Expected after edits: all PASS. Replay must pass unchanged,
  since the spec measured zero changes.

- [ ] **Step 5: Write ADR 0023** in the style of 0012 (Status: Accepted, 2026-10-27; Context: spec path + runner
  question 88). Decision: Repeat = packed by the Packer (`completed_orders` in any live session, this one included,
  whether or not the run was ended); `fulfillment_history.csv` is still written and is a record only. Consequence: an
  order analysed or listed but never packed is plain in later sessions. Update `CONTEXT.md` per §5 wording.

- [ ] **Step 6: Commit** `fix(repeat): only orders the Packer packed are Repeat (ADR 0023)`

### Task 5: Ended-with-unpacked Packer lists need attention (§6)

**Files:**
- Modify: `shopify_tool/session_lifecycle.py:140-143` (`_has_paused_list`)
- Test: `tests/test_session_lifecycle.py` (next to `test_a_paused_list_beats_progress`, ~line 265)

- [ ] **Step 1: Write the failing tests** using the file's `_lifecycle_entry` helper and `NOW`:

```python
    def test_an_incomplete_list_reads_paused(self):
        entry = _lifecycle_entry(lists=["a"], progress={"a": {"status": "incomplete"}},
                                 updated=NOW - timedelta(days=1))
        assert display_status(entry, NOW) == "paused"

    def test_stored_completed_with_an_incomplete_list_stays_incomplete(self):
        entry = _lifecycle_entry(lists=["a"], progress={"a": {"status": "incomplete"}},
                                 updated=NOW - timedelta(days=1))
        entry["status"] = "completed"
        assert display_status(entry, NOW) == "incomplete"
```

- [ ] **Step 2: Run** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_session_lifecycle.py`. Expected: the first FAILS (`in_progress`).

- [ ] **Step 3: Implement** `block.get("status") in ("paused", "incomplete")`, with a one-line comment that the Packer
  writes `incomplete` for a run ended with orders unpacked (packing-tool `gui/main_window.py:1470`) and never `paused`.

- [ ] **Step 4: Run** the file plus `tests/test_browse_page.py` and `tests/test_session_browser_lifecycle_sync.py`. Expected: PASS.

- [ ] **Step 5: Commit** `fix(sessions): a Packer list ended with unpacked orders needs attention`

### Task 6: Empty notes and tags are blank, not "nan" (§7)

**Files:**
- Modify: `shopify_tool/core.py:95-97` (`_text_or_blank`), `core.py:188` (`tags_value`)
- Modify: `tests/replay/fixtures/**/expected/**/*.json` (44+ files, mechanical)
- Modify: `tests/replay/anonymise.py:115-116` (comment only)
- Modify: `docs/audit/10-coverage-and-snapshot.md` (Open questions: mark the `nan` notes item resolved by patch 2.4.3)
- Test: `tests/test_packing_orders.py`

- [ ] **Step 1: Write the failing tests** in `tests/test_packing_orders.py`:
  `test_text_or_blank_treats_missing_as_blank` (`core._text_or_blank(float("nan")) == ""`, `(None) == ""`,
  `("x") == "x"`, `(pd.NaT) == ""`) and `test_empty_notes_and_tags_are_blank`: copy one row of the file's `FRAME`, set
  `Notes` and `Tags` to `float("nan")`, then assert `build_packing_orders(frame)[0]["notes"] == ""` and `["tags"] == []`.

- [ ] **Step 2: Run** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_packing_orders.py`. Expected: FAIL (`"nan"`, `["nan"]`).

- [ ] **Step 3: Implement** `_text_or_blank`: `return "" if value is None or pd.isna(value) or not value else str(value)`.
  Guard `pd.isna` against non-scalars with `pd.api.types.is_scalar(value)` first. Fix the docstring. Then
  `tags_value = _text_or_blank(first["Tags"][g])`.

- [ ] **Step 4: Run** the file. Expected: PASS. Run `tests/replay/test_replay.py`. Expected: FAIL on `notes`/`tags` differences only.

- [ ] **Step 5: Rewrite the fixtures** with a throwaway script, kept outside the repo (e.g. `$CLAUDE_JOB_DIR/tmp/fix_nan.py`), never committed:
  for every `tests/replay/fixtures/**/expected/**/*.json`, load it; for each `doc["orders"]` entry set `notes` `"nan"`→`""`
  and `tags` `["nan"]`→`[]`; write it back only if changed, with `json.dumps(doc, ensure_ascii=False, indent=2)` and
  `encoding="utf-8"`. Expected counts: 1267 notes, 382 tags (verified pre-plan by a read-only scan). Then
  `/usr/bin/git diff --stat` must show only fixture files. Every changed line in `/usr/bin/git diff` must be one of:
  a `"notes"` line, a `"tags": [` / `"tags": [],` line, a line holding only `"nan"`, or a line holding only `]` / `],`.
  If you see anything else (e.g. reformatting of unrelated lines), the writer format differs: stop and fix the script
  before committing.

- [ ] **Step 6: Run** `tests/replay/test_replay.py` and `tests/replay/test_anonymise.py`. Expected: PASS. Update the
  `anonymise.py` comment: old sessions still hold `"nan"`, so the guard stays, and today's code writes `""`. Update the audit doc line.

- [ ] **Step 7: Commit** `fix(packing): empty notes and tags are blank, not "nan"`

### Task 7: Acceptance on the real example, full gate, push

**Files:** none committed besides fixes found here.

- [ ] **Step 1: Real-data check, local only, nothing written under the repo.** Run `process_reference_labels` on
  `~/Desktop/Server./label/combined_a6_17930023956adf0b9b55c766.19938115.pdf` with
  `~/Desktop/Server./label/Shipments-HERBAR-2026-10-26.csv`, `output_dir` in `$CLAUDE_JOB_DIR/tmp`. Expected:
  `matched == 134`, `unmatched == 0`, `missing_refs == []`, `duplicate_refs == []`, `barcode_matched == 3`. Print only
  these counts; never print page text (PII). Delete the output PDF afterwards.

- [ ] **Step 2: Full gate.** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` (run in the background, ~10 min)
  and `ruff check .`. Expected: all pass. The 3 known `test_label_printing` ZPL failures on main are pre-existing:
  confirm they fail on `origin/main` too before ignoring them.

- [ ] **Step 3: Push** the branch (`/usr/bin/git push`).
