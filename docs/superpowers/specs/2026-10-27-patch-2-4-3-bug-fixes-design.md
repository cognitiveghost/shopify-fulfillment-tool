# Patch 2.4.3: reference-label matching, Repeat means packed, small fixes

Task: Todoist "Patch 2.4.3, bug fixes" (dev-runner run 103, branch `dr/38-patch-2-4-3-bug-fixes`).
Classification: bounded. Five independent fixes, all in this repo. Packing Tool needs no change.

No mockup: the patch changes no screen layout and adds no user-facing text.

## 1. Why

1. The owner's 2026-10-26 HERBAR Reference Labels run left 14 of 134 pages unmatched (Colissimo and others).
   Each unmatched page is a parcel with no REF stamp, which must be matched by hand before printing.
2. Orders that were only analysed, or only put on a packing list, are flagged **Repeat** in a later session.
   The owner's rule: Repeat means *packed before* in the Packer. Anything else is not a repeat.
3. Several smaller bugs found by the investigation the task asked for (section 7).

## 2. Evidence (investigation, 2026-10-27)

Example run: `~/Desktop/Server./label/` (`Shipments-HERBAR-2026-10-26.csv`, 132 rows;
`combined_a6_….pdf`, 134 pages). It is production data with PII, so it never goes into git or a fixture.
Today's code matches 118 pages by P-number and 2 by tracking number, and leaves 14 unmatched.

| Pages | Carrier | Why it fails today |
|---|---|---|
| 10 | Colissimo (FR) | No P-number on the label. The CSV tracking `9L37349396976` is printed with spaces, `9L 3734939697 6`. `extract_tracking_numbers` only finds unbroken `[A-Z0-9]{12,}` tokens. |
| 1 | ACS (GR) | Tracking `9819014181` is 10 digits, under the 12-character floor. |
| 2 | Packeta (CZ) | The page has no text layer (glyphs drawn as paths). pypdf and pdfium both extract `""`. |
| 1 | Slovak Post (SK) | The font has no usable ToUnicode map, so the text extracts as scrambled symbols. |

As a prototype, the 3 textless pages were rendered with `pypdfium2` (already a dependency) at 300 dpi and
decoded with `zxing-cpp`. All 3 tracking numbers came back, at about 30 ms per page: Packeta Code-128
`40858732093-14008` plus ITF `408587320939`, and Slovak Post Code-128 `EF919140313SK`.

Pages 45–46 are CN23 customs declarations for the parcel on page 44 (text contains `Customs Declaration - CN23`).
They match the same REF, so today's run also warns "REF #120730 is on more than one page", which is a false alarm.

Repeat (`shopify_tool/analysis.py:879` `_detect_repeated_orders`): an order is Repeat when any row of the
detection frame counts. The frame is `fulfillment_history.csv` (every *fulfillable* order of every analysis
run, `fulfillment_history.record_session`) unioned with the Packer's `completed_orders`
(`packed_orders.union_history_with_packed`). The history rows are what flags never-packed orders.

## 3. Decisions (owner, 2026-10-27, runner question 88)

| Question | Answer |
|---|---|
| Label pages with no readable text | **Barcode fallback**: add `zxing-cpp` and read barcodes on pages that text cannot match. |
| What counts as packed | **Completed in the Packer**: the order is in a `completed_orders` list of `packing_progress` in any live session, whether or not that run was ended. |
| Orders analysed or listed before but never packed | **Nothing.** No flag and no soft marker. `fulfillment_history.csv` stays as a record. |
| Extra fixes in 2.4.3 | Incomplete Packer lists need attention; no `nan` notes; CN23 pages are not duplicates. **Not** chosen: quieting the expiry-date warnings. |

## 4. Reference labels (`shopify_tool/pdf_processor.py`)

### 4.1 Tracking numbers match with whitespace ignored

`match_reference` step 2 changes. Steps 1 (P-number) and 3 (name fallback) do not.

- Build `compact = re.sub(r"\s+", "", page_text).upper()`.
- A CSV tracking number `t` (from `mapping['by_tracking']`, with `len(t) >= 8`) hits when both of these hold:
  1. Cheap prefilter: `t.upper()` is a substring of `compact`.
  2. Whole-token confirm on the original text: `re.search(r"(?<![A-Z0-9])" + r"\s*".join(map(re.escape, t.upper())) + r"(?![A-Z0-9])", page_text, re.I)`.
     The tracking may contain whitespace inside it, but it may not sit inside a longer alphanumeric run.
     Example: the Colissimo label also prints `119L 37349396973`, and a tracking `9L37349396973` must not hit there.
- When every hit carries the same REF, return `{'ref', 'verified': check_name_presence(...), 'method': 'tracking'}`.
  When hits name more than one REF, log at INFO and fall through to the name step. A page never guesses
  between customers, as with AUDIT-04-7.
- Delete `extract_tracking_numbers`. Its only caller is `match_reference` (`pdf_processor.py:454`), and no test
  references it.

Builder's call: the length floor (8). Every real tracking number seen so far is 10 characters or more.

Prototype of exactly this rule (2026-10-27) over all 23 historical runs in the snapshot (`Server/Ref labels/` plus
`label/`, 566 pages): **no page changes REF**, 13 pages gain a tracking match, and 4 stay unmatched (no text layer).

Ceiling: this is O(rows × pages) substring prefilters, about 1M for a 1000-row CSV and 1000 pages, well under a
second. The regex only runs on prefilter hits.

### 4.2 Barcode fallback for pages text cannot match

- New dependency: `zxing-cpp>=3.0` in `requirements.txt`, with a comment in the file's style
  (`# barcode reading for Reference Labels pages with no text layer`). It is one compiled module with
  Windows wheels, and PyInstaller collects it by import. No workflow change is expected. If the CI build's
  bundle check fails on it, that is a plan step, not a redesign.
- In `process_reference_labels`, after the text-matching loop, gather the indices of pages still unmatched.
  For those pages only:
  - render with `pypdfium2`: `pdfium.PdfDocument(pdf_path)[i].render(scale=300/72, grayscale=True).to_numpy()`.
    This is the same call style as `shopify_tool/label_printing.py:45-48`.
  - decode with `zxingcpp.read_barcodes(array)`, then match the decoded texts with a new pure function
    `match_barcodes(values: list[str], mapping) -> dict | None`:
    1. A value equal to a P-number key or a tracking key gives that REF.
    2. Otherwise a tracking key `t` (`len(t) >= 8`) found in a value as a whole token gives its REF:
       `re.search(r"(?<![A-Z0-9])" + re.escape(t.upper()) + r"(?![A-Z0-9])", value.upper())`. This covers
       Packeta's Code-128 `40858732093-14008`. Its ITF `408587320939` does not match (trailing digit), which is fine.
    3. Collect the REFs from both rules. Exactly one distinct REF gives `{'ref', 'verified': False, 'method': 'barcode'}`.
       Zero or several give `None`.
  - If `import zxingcpp` fails, or the PDF cannot be opened by pdfium, log a WARNING once and skip the fallback,
    so those pages stay unmatched as today. A page whose render or decode raises is logged and skipped.
    The run never fails because of the fallback.
- Import `zxingcpp` lazily inside the fallback, so a broken install degrades to today's behaviour.
- Progress: no new phase. The fallback runs between READING and STAMPING. At about 30 ms per page, even an
  all-image PDF of 300 pages takes about 10 s.
  `# ponytail: no progress phase for the barcode pass; add one if all-image PDFs make Cancel feel stuck.`
- Result dict: add `'barcode_matched': int`, the number of stamped pages whose method is `'barcode'`, counted like
  `name_matched`. No UI change: a barcode match is a tracking-number match and as trustworthy as text.

### 4.3 CN23/CN22 pages are not duplicates

- A page is a customs page when its text contains `customs declaration` (case-insensitive) **and**
  `extract_postone_number(text)` is None. Do not key on `CN22`/`CN23` alone: across the snapshot, 9 real label
  pages (each with a P-number) print `CN22`/`CN23`. All 11 `Customs Declaration` pages in the snapshot have no
  P-number.
- Customs pages still get matched, stamped and sorted as today. Sorting by `(ref, original_order)` already
  puts them right after their label.
- `duplicate_refs` counts only stamped pages that are **not** customs pages. A REF on two real label pages
  still warns. A REF on one label plus its CN23 pages does not.
- `missing_refs` is unchanged.

### 4.4 Acceptance

On the 2026-10-26 example run locally (never committed), 134/134 pages are stamped, `missing_refs` is empty,
and `duplicate_refs` is empty. The test suite uses synthetic PDFs only, built with reportlab like
`tests/test_pdf_processor.py`:
- a page whose tracking is drawn with spaces (`"9L 3734939697 6"`) matches by tracking;
- a 10-digit tracking matches;
- two CSV trackings found on one page with different REFs gives no tracking match;
- a page with **no text**, only a reportlab `code128` barcode drawn with `drawOn`, which is vector paths and so
  mimics Packeta, matches with method `barcode`. Use a value like `"40858732093-14008"` against a CSV tracking
  `40858732093`;
- `match_barcodes` unit cases: exact, contained, ambiguous, none;
- a label page plus a page with text `Customs Declaration - CN23` for the same REF gives `duplicate_refs == []`,
  while two plain pages for one REF still give a duplicate;
- `zxingcpp` import failing (monkeypatch `sys.modules['zxingcpp'] = None`) gives a run that completes with the page unmatched.

## 5. Repeat means packed (`shopify_tool/analysis.py`)

- In `_detect_repeated_orders`, a row counts only when `source == "packed"`. History rows (`Source` missing or
  `"history"`) never count, legacy or sessioned. A frame without a `Source` column therefore flags nothing.
- "Packed" is the Packer's signal exactly as `packed_orders.load_session_signals` reads it today: `completed_orders`
  of any `packing_progress` block, in sessions not marked abandoned. It is written after every completed order,
  so an un-ended run counts. A packed order is Repeat in its own session too (unchanged).
- Rewrite the docstring table to match. Leave the `current_session`/`today` parameters and the history loading in
  place: `today` is threaded through the public `core.analyse` and the replay, and the history file is still written
  and read by `fulfillment_history.record_session`. Builder's call: whether `current_session` stays a
  now-unused parameter of `_detect_repeated_orders`. Prefer dropping it from that one function and its single
  call at `analysis.py:1136` if the diff stays small.
- `fulfillment_history.csv` keeps being written exactly as today.
- New ADR `docs/adr/0023-repeat-means-packed.md`. It supersedes rule 3 of ADR 0012 ("detection compares sessions")
  for detection: Repeat comes only from the Packer's packed signal, and the history file is a record. ADR 0012
  gets a one-line "Superseded in part by 0023" note at the top.
- `CONTEXT.md` "Repeat order" (line ~397) becomes: "an order the Packer has already packed in any live session
  (this one included). Being in fulfillment history alone does not make it a repeat. Marked, never held: …" (keep
  the rest), citing ADR 0012 and 0023.
- Tests: existing tests in `tests/audit/test_02_repeat_orders.py`, `tests/test_analysis.py` and `tests/test_core.py`
  that flag an order from history rows alone (no `packing_progress` `completed_orders`) now expect no flag. Invert
  them and rename them to say so. Do not delete them. A test whose Repeat comes from a packed signal must stay green
  untouched. Add one test: an order present in `fulfillment_history.csv` from another session, with no packed signal,
  is not Repeat.
- Replay: measured on the 26 fixtures, the packed-only rule changes no stored result.

## 6. Incomplete Packer lists need attention (`shopify_tool/session_lifecycle.py`)

The Packer writes a list block's `status` as `"incomplete"` when a run is ended with orders unpacked
(packing-tool `gui/main_window.py:1470`). It never writes `"paused"`. The Shopify tool only looks for `"paused"`
(`_has_paused_list`, `session_lifecycle.py:140`), so such a session reads **In progress** and is never grouped
under needs-attention.

- `_has_paused_list` returns true for a block whose status is `"paused"` or `"incomplete"`. The session's
  derived state becomes `paused`, which `gui/browse_state.py` already labels "Paused" and puts in `_ATTENTION_STATES`.
- Builder's call: map to the existing `paused` state, not to session-level `incomplete`. Session-level `incomplete`
  already means "a person called the session done with lists unpacked".
- `packing_completion` is unchanged: only `"completed"` counts as done.
- Tests in `tests/test_session_lifecycle.py` (or wherever `_has_paused_list` / `derive_state` are tested):
  an active session with one list block `{"status": "incomplete", ...}` derives `paused`.
  `in_progress` still derives `in_progress`.

## 7. Empty notes and tags are blank, not `nan` (`shopify_tool/core.py`)

`_text_or_blank` (`core.py:95`) is `str(value or "")`. NaN is truthy, so an empty Notes cell becomes `"nan"` in
`analysis_data.json` and every packing-list JSON. The Packer hides that one (packing-tool `gui/packer_bridge.py:127`).
The same root cause hits Tags: `core.py:188` `tags_value = first["Tags"][g] or ""` turns an empty Tags cell into
`tags: ["nan"]`, which the Packer does not filter (packing-tool `gui/packer_bridge.py:143` lists tags).
Builder-check finding. The fix is included as the same bug: my call, under the owner's "No nan notes" pick.

- `_text_or_blank` returns `""` for anything `pd.isna` calls missing (None, NaN, NaT), and otherwise behaves as
  today. It is used for every JSON text field (status, notes, system note, courier, country, order type).
- `core.py:188`: `tags_value = _text_or_blank(first["Tags"][g])`, so an empty Tags cell gives `tags: []`.
- Replay fixtures, measured: 1267 `"notes": "nan"` in 44 expected files, and 382 orders whose `tags` is exactly
  `["nan"]`. No other field holds `"nan"`. Rewrite them with a one-off Python snippet over
  `tests/replay/fixtures/**/expected/**/*.json` that does the following and is not committed:
  load the JSON; for each order, set `notes` from `"nan"` to `""` and `tags` from `["nan"]` to `[]`; write the file back with
  `json.dumps(doc, ensure_ascii=False, indent=2)`, the writer's own format (`scripts/build_replay_fixtures.py:62`).
  Check that `git diff --stat` touches only those files and that the diff holds only those two kinds of line.
  Then update the comment in `tests/replay/anonymise.py:115-116`, which explains the `"nan"` case. The
  `("", "nan", None)` guard there can stay, since old sessions still hold `"nan"`.
- Delete the AUDIT-10 open question about `nan` notes in `docs/audit/10-coverage-and-snapshot.md`, or mark it
  resolved by this patch.
- Test: `_text_or_blank(float("nan")) == ""`, `_text_or_blank(None) == ""`, `_text_or_blank("x") == "x"`. Also test that
  an order with empty Notes and Tags cells gives `notes == ""` and `tags == []` in the packing JSON.

## 8. Not doing (and why)

- Expiry-date warning flood (`analysis.py:138`, 274 lines a month): the owner did not pick it.
- Packer warning "Config not found for client REVE": REVE was never set up in the Packer, and the Packer creates
  `packer_config.json` on setup. That is expected behaviour, not a bug.
- `full_session` progress key never written by the Packer (`session_lifecycle.py:21`): dead branch, harmless.
- packing-tool's `shared/` copy is behind (`shared_synced_from.txt` → `e070d6b`): its next sync picks this up.
  This patch does not touch `shared/`.
- Production errors already fixed on main: config-save Windows lock (atomic saves, #382), `.XLSX` packing-list
  extension (AUDIT-10-1).

## 9. Gate

`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` and `ruff check .`. CI's Windows build must still bundle
`zxing-cpp`. The release itself is the owner's step (Actions → Run workflow, patch bump).
