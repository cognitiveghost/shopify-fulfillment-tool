# Audits 07–09, Groups B, D, E, F, G Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the remaining findings of audits 07, 08 and 09, except group C: B (session index), D (speed in
the run), E (per-edit I/O), F (allocation rules) and G (low items). All of it lands in one PR, with one commit
per group.

**Architecture:** One branch and one PR. This plan is the PR's first commit. The groups follow in the order
B, D, F, E, G, one commit each. Inside a group the TDD steps run without committing. Each group ends at a
checkpoint: the full gate passes, then one commit whose message starts with the group letter, then a push. A
finding with a strict-xfail test is fixed by making that test pass and then removing its marker.

**Tech Stack:** Python 3.14, pandas 3, PySide6, pytest + pytest-qt.

**Spec:** `docs/superpowers/plans/2026-10-05-audit-07-09-fixes.md` (the overview plan: owner decisions, and each
group's findings, files and tests), and the three reports `docs/audit/07-core-io-review.md`,
`08-rules-undo-review.md` and `09-outputs-sets-ledger-review.md` (each "Verification, 2026-10-05" section).
Repro scripts are in `docs/audit/repro/`. The ADRs it touches are 0011, 0012 and 0015.

## Global Constraints

- Branch `claude/focused-volta-ah85ui`, cut from `origin/main` at `28fa5b0` (#369). Never commit or push to `main`.
- Gate at every checkpoint: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` and `.venv/bin/ruff check .`.
  Baseline: 3,588 passed, 22 xfailed, ruff clean. Expected xfailed after each group: B 20, D 14, F 10, E 7, G 7.
  The 7 that remain belong to group C, #370: 07-M2, 07-M3, 07-M4 ×3, 09-O5 ×2.
- If `.venv` is missing or `./scripts/setup_venv.sh` fails on an old Python, build the venv with
  `uv venv --python 3.14 .venv`, then `uv pip install --python .venv/bin/python -r requirements.txt -r requirements-dev.txt`.
- TDD for a finding: run its xfail test with `--runxfail` and see it fail **on its own assertion**. Fix the code,
  see the test pass, remove the marker. For new behaviour: write the test, see it fail, then implement.
- Group C stays with #370. Do not fix 07-M2, M3, M4 or 09-O5 in passing. When a group touches `core.py`,
  `fulfillment_history.py` or the packing-list JSON write, run the group C tests with `--runxfail` at the
  checkpoint and confirm each still fails on its own assertion:
  `-k "M2 or M3 or M4 or O5"` over `tests/audit/test_07_core_io.py tests/audit/test_09_outputs_sets_ledger.py`.
- Do not add `tests/audit/conftest.py`: it shadows `tests/conftest.py`. Shared audit fixtures live in
  `tests/audit/audit_support.py`.
- Use synthetic fixtures only. Never use production data.
- No UI call from a worker thread: a worker reports by signal. No hardcoded colours.
- No group changes `shared/`. If one has to, say so in the PR: packing-tool picks it up at its next sync.
- After each group's code changes, run `graphify update .`. Skip it when `graphify-out/` or the command is absent.
- Write test files with Write/Edit: the pytest-guard hook blocks Bash text containing "pytest" other than the plain run.
- Ask `context7` about pandas and PySide6 APIs, rather than relying on memory. Two places need it here:
  `GroupBy.transform("first", skipna=False)` in D2, and delivery of a signal emitted from a Python thread in E1.
- Git on the dev VM: use `/usr/bin/git`, one plain command per Bash call, and commit with `git commit -F <absolute path>`.
- Assert on outcomes: frame contents, files on disk, returned values. A test of fixed behaviour has no marker.

## Owner decisions

Decisions already in the overview plan, applied exactly:

| Finding | Decision |
|---|---|
| 07-M1 | A negative stock row is subtracted from the lot with the same expiry and batch first, and any remainder from the oldest lots. Lot totals always equal the SKU total. Rows with no expiry and no batch are drawn **first**, then the dated or batched lots, earliest expiry first. Update ADR 0015. The stock export never holds a negative quantity. |
| 09-O3 | Allow force-fulfil and bulk "mark fulfillable" on a SKU missing from the stock file, with a toast that names the SKU. |
| 08-R4 | Every text operator (`equals`, `does not equal`, `starts with`, `ends with`, `contains`, `in list`) ignores case and trims whitespace on both sides. |
| 07-H2 | Only `current_state.pkl` is written on the click. History, inventory memory, `analysis_stats.json` and `session_info` move to a per-session coalescing background queue. Stop writing `current_state.xlsx`. Opening a session falls back to `fulfillment_analysis.xlsx`. |

Added by the owner in the session that wrote this plan (2026-10-05):

| Finding | Decision |
|---|---|
| 07-L1 | Keep the whole rewrite of `fulfillment_history.csv`, now on the background queue. The run drops rows whose session folder no longer exists. Rows of abandoned sessions stay. No pruning by age, which would reverse ADR 0012 rule 5. |
| 07-H2 | `operations_history.json` also goes through the queue: only `current_state.pkl` is written on the click. |
| 08-U4 | One undo file per PC: `operations_history_<PC>.json`. |
| 07-M1 | "Oldest lots" means draw order: undated and unbatched lots first, then earliest expiry. A negative row cancels what would ship next. |

08-R3 needs no decision: the Rules page shows the order the engine runs.

## Review Focus

Inputs no task's own fix would exercise, most likely to bite first. Each has its test in the owning task.

1. **A `Created at` column that crosses a DST change.** `+0200` and `+0300` in one column must both parse to the
   date as written. pandas raises on mixed offsets unless the offset is dropped first.
   (D3, `test_mixed_offsets_parse_to_the_date_as_written`)
2. **An analysis run started while background writes are pending.** Repeat detection must see the last edit's
   history, so the run waits for the queue, or refuses with a toast. (E3, `test_a_run_waits_for_pending_writes`,
   `test_a_run_is_refused_while_writes_are_still_pending`)
3. **Editing while reports generate.** The report holds the frame as it was at the click, and the edit is saved
   normally. (D5, `test_a_report_uses_the_frame_as_it_was_at_the_click`)
4. **A report filter on a text field.** Report filters share the rule operators, so after R4 a packing list
   filtered on `Shipping_Provider equals dhl` includes `DHL` orders. That is intended, and it is pinned.
   (F6, `test_a_report_filter_ignores_case_and_spaces`)
5. **An undo file written by an older build.** Shared name, whole rows: it must still load, and its last step
   must still undo. (E5, `test_a_whole_row_record_from_an_older_build_still_undoes`; G7,
   `test_a_legacy_shared_history_still_loads`)

---

## Execution order and file overlaps

**Order: B, D, F, E, G.**

- **B** touches only `session_manager.py`. Nothing else depends on it, so it goes first and is the cheapest to
  review.
- **D** reworks `RuleEngine.apply`, the date operators and `decode_sets_in_orders` for speed, without changing
  behaviour. F then changes rule operators and set keys on top of the new code, so F's diff reads as a behaviour
  change only.
- **F** changes allocation and rule matching. It goes before E so that E's large diff in `undo_manager.py`,
  `main_window_pyside.py` and `actions_handler.py` lands on settled behaviour.
- **E** is the largest group (a new queue, the save path, undo records, backups, history). It goes after the
  behaviour changes and before G, because G edits two of E's files: the undo file name and the backup names.
- **G** comes last: twelve small, independent items across many files.

| File | Groups | What each changes |
|---|---|---|
| `shopify_tool/rules.py` | D, F, G | D: `apply` order-level path, date operators. F: text operators, `execution_order`. G: `ADD_PRODUCT` tracking fields |
| `shopify_tool/core.py` | D, E, G (+ C in #370) | D: `build_packing_orders`. E: drop the `current_state.xlsx` write, history prune argument. G: `analysis_report_path`. C later: atomic writes in `_save_results_and_reports` |
| `gui/actions_handler.py` | D, F, E | D: `_generate_reports` on a `Worker`. F: unlisted-SKU toasts in `toggle_fulfillment_status_for_order` and `bulk_change_status`. E: `run_analysis` flushes the queue |
| `shopify_tool/set_decoder.py` | D, F | D: vectorised `decode_sets_in_orders`, `_set_table`. F: `normalize_sku` on import and in `_set_table` |
| `shopify_tool/analysis.py` | F, G | F: `_build_fifo_lots`, `toggle_order_fulfillment`. G: delete `_calculate_final_stock`, vectorise the reason notes |
| `shopify_tool/undo_manager.py` | E, G | E: column-only records, saves through the queue. G: per-PC file, the "Cleared N" count |
| `shopify_tool/profile_manager.py` | E, G | E: `save_shopify_config(..., backup=)`. G: backup names that cannot collide |
| `shopify_tool/session_manager.py` | B, G | B: index refresh. G: `_exclusive_lock` unlock guard |
| `shopify_tool/stock_export.py` | E, G (F tests only) | E: merge fallback to `fulfillment_analysis.xlsx`. G: O7 grouping, O8 archive names |
| `shopify_tool/fulfillment_history.py` | E (+ C in #370) | E: `record_session(..., existing_sessions=)`. C later: `_write_atomic` backoff. Leave `_write_atomic` alone |
| `tests/audit/test_07_core_io.py` | B, F, E, G | Markers removed: B H3, H4; F M1; E H2, M5. G adds one unmarked L2 test |
| `tests/audit/test_08_rules_undo.py` | D, E, G | D: R1, R2 markers. E: U2 marker. G: undo-file paths for U4 |
| `tests/audit/test_09_outputs_sets_ledger.py` | D, F | D: O1, O2 markers, and O5's patch target. F: O3, O4 |

---

## Group B: session index (07-H3, 07-H4)

**Risk: medium.** A missed refresh shows a stale status in Browse, and hides packed orders from repeat
detection. Mitigations: the comparison is per entry and by equality, so clock skew between PCs no longer
matters. A mismatch only costs one reread, never wrong data.

**PR warning text:** "B: the session index now records each session folder's modification time and rereads only
the folders that changed. A folder without `session_info.json` is remembered and read again only when it
changes. During a mixed-version rollout an older PC may list such a folder as a blank session until its next
full rebuild. A Packing Tool write that lands in the same timestamp tick as this PC's own index write can still
be missed until that session's next change, the same as before."

**Index format.** It stays a JSON list, so older builds can still read it. Two private keys are added:

- every entry gets `"_dir_mtime": float`: the session folder's `st_mtime` when the entry was read or written;
- a folder whose `session_info.json` is missing or unreadable gets a marker entry
  `{"session_name": <folder>, "_dir_mtime": <float>, "_no_session_info": True}`.

`list_client_sessions` skips markers, and strips every key that starts with `_` before returning an entry.

**How staleness is detected.** One `os.scandir` of the client folder gives `{name: st_mtime}` for every
subfolder. A name missing from the index, or whose mtime differs from its entry's `_dir_mtime`, is reread through
`get_session_info`. An entry whose folder is gone is dropped. Nothing changed means no lock and no write. A legacy
entry without `_dir_mtime` counts as changed, so the first listing after the upgrade rereads each session once.

### Task B1: refresh only the entries that changed (07-H4; ends 07-H3's rescans)

**Files:**
- Modify: `shopify_tool/session_manager.py`: `list_client_sessions`, `_scan_sessions`, `_rebuild_index`,
  `_upsert_index_entry`, `apply_status_updates`. Delete `_index_is_stale`.
- Modify: `shopify_tool/packed_orders.py`: the module docstring names `_index_is_stale`; point it at the refresh
  in `list_client_sessions`.
- Test: `tests/audit/test_07_core_io.py` (remove the H3 and H4 markers), `tests/test_session_manager.py`

**Interfaces:**
- Produces:
  - `SessionManager._listing(client_sessions_dir: Path) -> dict[str, float]`
  - `SessionManager._index_entry(session_dir: Path, dir_mtime: float) -> dict`: an entry, or a marker
  - `SessionManager._refresh_index(client_sessions_dir: Path, entries: list[dict]) -> list[dict]`

- [ ] **Step 1: Write the failing tests** (`tests/test_session_manager.py`, new class `TestIndexRefresh`)

```python
def test_a_new_session_folder_is_added_without_a_full_scan(self, session_manager, monkeypatch):
    first = Path(session_manager.create_session("M"))
    session_manager.list_client_sessions("M")
    other = first.parent / "2099-01-01_1"            # written by another tool
    other.mkdir()
    atomic_write_json(other / "session_info.json", {"session_name": other.name, "status": "active"})
    scans = _spy(monkeypatch, session_manager, "_scan_sessions")
    reads = _spy(monkeypatch, session_manager, "get_session_info")
    names = {s["session_name"] for s in session_manager.list_client_sessions("M")}
    assert names == {first.name, other.name}
    assert scans == [] and len(reads) == 1

def test_a_deleted_session_is_dropped_without_a_read(self, session_manager, monkeypatch):
    keep = Path(session_manager.create_session("M"))
    gone = Path(session_manager.create_session("M"))
    session_manager.list_client_sessions("M")
    shutil.rmtree(gone)
    reads = _spy(monkeypatch, session_manager, "get_session_info")
    assert [s["session_name"] for s in session_manager.list_client_sessions("M")] == [keep.name]
    assert reads == []
    index = json.loads((keep.parent / SessionManager.INDEX_FILENAME).read_text())
    assert gone.name not in {e["session_name"] for e in index}

def test_own_writes_reread_nothing(self, session_manager, monkeypatch):  # pins today's behaviour
    session_manager.create_session("M")
    path = session_manager.create_session("M")
    session_manager.update_session_status(path, "completed")
    session_manager.update_session_info(path, {"comments": "hi"})
    session_manager.apply_status_updates("M", {Path(path).name: "archived"})
    reads = _spy(monkeypatch, session_manager, "get_session_info")
    for _ in range(3):
        session_manager.list_client_sessions("M")
    assert reads == []

def test_a_legacy_index_without_mtimes_is_refreshed_once(self, session_manager, monkeypatch):
    a, b = (Path(session_manager.create_session("M")) for _ in range(2))
    (a.parent / SessionManager.INDEX_FILENAME).write_text(json.dumps(
        [{"session_name": a.name, "status": "active"}, {"session_name": b.name, "status": "active"}]))
    reads = _spy(monkeypatch, session_manager, "get_session_info")
    session_manager.list_client_sessions("M")
    session_manager.list_client_sessions("M")
    assert len(reads) == 2
```

`_spy(monkeypatch, obj, name) -> list` is a module-level helper, a copy of `_count_calls` in
`tests/audit/test_07_core_io.py`.

Change `TestSessionIndex::test_another_tools_write_to_a_session_is_picked_up`: after the atomic write, push the
session folder's mtime forward (`os.utime(session_path, (t + 5, t + 5))`, where `t` is its current `st_mtime`)
instead of moving the index's mtime back. The index's own mtime no longer matters.

- [ ] **Step 2: Run them with `test_AUDIT_07_H3_*` and `test_AUDIT_07_H4_*` under `--runxfail`. All fail on
  their assertions, except `test_own_writes_reread_nothing`, which pins today's behaviour and passes**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_session_manager.py tests/audit/test_07_core_io.py --runxfail -k "IndexRefresh or H3 or H4 or another_tools"`

- [ ] **Step 3: Implement**

- `list_client_sessions`: no index, or an unreadable one, means `_rebuild_index`. Otherwise call `_refresh_index`.
  Then filter out markers and strip the `_` keys.
- `_refresh_index`: compare `_listing` with the entries. If nothing changed, return the entries as they are.
  Otherwise, under `_exclusive_lock(_index_lock_path(...))`: re-read the index, list again, reread only the
  changed folders through `_index_entry`, drop the gone ones, then write. Use the listing's mtime taken
  **before** the read, so a write that lands during the read shows up as a change next time.
- `_scan_sessions`: build every entry through `_index_entry`, markers included. It is only used by `_rebuild_index`.
- `_upsert_index_entry` and `apply_status_updates`: set `entry["_dir_mtime"] = os.stat(session_dir).st_mtime`
  after the `session_info.json` write each one mirrors, so the next listing sees no change.
- `create_session`: its upsert must come after the last change to the new folder (the subfolders and
  `session_info.json`); move it there if needed.

- [ ] **Step 4: Run Step 2's command without `--runxfail`; all pass. Remove the H3 and H4 markers. Run the whole of
  `tests/test_session_manager.py tests/test_packed_orders.py tests/audit/test_07_core_io.py`**

### Task B2: a folder without `session_info.json` is read once until it changes

**Files:** `shopify_tool/session_manager.py` (`_index_entry`), `tests/test_session_manager.py`

- [ ] **Step 1: Write the failing tests** (in `TestIndexRefresh`)

```python
def test_a_stray_folder_is_read_once_until_it_changes(self, session_manager, monkeypatch):
    real = Path(session_manager.create_session("M"))
    stray = real.parent / "archive"
    stray.mkdir()
    reads = _spy(monkeypatch, session_manager, "get_session_info")
    for _ in range(3):
        listed = session_manager.list_client_sessions("M")
    assert [s["session_name"] for s in listed] == [real.name]
    assert len(reads) == 1
    atomic_write_json(stray / "session_info.json", {"session_name": "archive", "status": "active"})
    t = stray.stat().st_mtime + 5
    os.utime(stray, (t, t))
    assert {s["session_name"] for s in session_manager.list_client_sessions("M")} == {real.name, "archive"}

def test_private_index_keys_never_reach_callers(self, session_manager):
    path = Path(session_manager.create_session("M"))
    (path.parent / "stray").mkdir()
    listed = session_manager.list_client_sessions("M")
    assert all(not k.startswith("_") for s in listed for k in s)
```

- [ ] **Step 2: Run them; the first fails (the stray is reread on every listing)**
- [ ] **Step 3: `_index_entry` returns the marker when `get_session_info` returns `None`.** `_refresh_index` already
  compares markers by mtime, like any other entry.
- [ ] **Step 4: Run them and `tests/test_session_manager.py`; all pass**

### Group B checkpoint

- [ ] Run the full gate. Expected: 20 xfailed, ruff clean.
- [ ] Run `graphify update .`.
- [ ] Commit, starting the message with `B: the session index refreshes only what changed (AUDIT-07-H3, AUDIT-07-H4)`.
  The body lists the two findings and the tests unmarked.
- [ ] `git push -u origin claude/focused-volta-ah85ui`. Tick B in the PR body.

---

## Group D: speed in the run (09-O1, 09-O2, 08-R1, 08-R2)

**Risk: medium-high.** Vectorising can change edge behaviour: NaN, mixed types, row order, the order of added
rows. Each task pins today's behaviour with a test written first, which passes on today's code and must still
pass after. The existing suites stay unchanged: `tests/test_rules.py`, `tests/audit/test_03_rule_engine.py`,
`tests/test_set_decoder.py`, `tests/audit/test_06_second_pass.py`, the packing-list tests.

**PR warning text:** "D: set decoding, order-level rules, date conditions and the Packing Tool JSON are
vectorised. Results are meant to be identical, pinned by tests against frozen copies of the old code. Two log
changes are visible: an order rule's `ALERT_NOTIFICATION` now logs one line per rule step with the total number
of matched rows, not one per order; and a date column with unparseable cells logs one summary line, not one per
cell. Report generation now runs in the background: the window stays usable, and the toasts arrive when the
files are written."

### Task D1: set lines expand by a merge (09-O1)

**Files:**
- Modify: `shopify_tool/set_decoder.py`: `decode_sets_in_orders` and a new `_set_table`
- Test: `tests/audit/test_09_outputs_sets_ledger.py` (remove the O1 marker), `tests/test_set_decoder.py`

**Interfaces:**
- Produces:
  - `_set_table(set_decoders: dict[str, list[dict]]) -> pd.DataFrame`, with columns `Original_SKU, SKU,
    _per_unit, _seq`. It has one row per (set, component) from `_components(set_sku, 1, set_decoders, {set_sku})`,
    so nested, self-listing and cyclic sets keep today's rules. A set whose expansion is empty is absent.
    Warnings are logged once per set, not once per line.
  - `decode_sets_in_orders(orders_df, set_decoders) -> pd.DataFrame`: same signature and same output as today.

- [ ] **Step 1: Write the pinning test.** Copy today's `decode_sets_in_orders` into `tests/test_set_decoder.py` as
  `_decode_reference`, with the comment `# the pre-D implementation, frozen to pin behaviour`. Then:

```python
@pytest.mark.parametrize("sets", [SETS_MIXED, {}], ids=["sets", "no-sets"])
def test_decoding_matches_the_reference(sets):
    out = decode_sets_in_orders(ORDERS.copy(), sets)
    ref = _decode_reference(ORDERS.copy(), sets)
    pd.testing.assert_frame_equal(out, ref, check_dtype=False)  # index labels and row order included
```

`ORDERS` holds 4 orders: a plain line; a 2-component set; a nested set; a self-listing set (`NECTAR-30` style); a
cycle (`X` → `Y` → `X`); a set with `[]` components; a set whose components are all invalid (quantity 0, no SKU);
a NaN SKU; a float `Quantity` of `2.0`; a NaN `Quantity`. `SETS_MIXED` defines those sets.

- [ ] **Step 2: Run it; it passes on today's code. Run `test_AUDIT_09_O1_*` with `--runxfail`; it fails on `seconds < 1.0`**
- [ ] **Step 3: Implement.** Keep non-set lines as they are and add the three tracking columns. Merge the set
  lines with `_set_table` on `SKU` == `Original_SKU`, and set `Quantity = Quantity × _per_unit`. Restore the input
  order by stable-sorting on (source position, `_seq`), and give each expanded row its source row's index label.
  The output columns are the input columns, then `Original_SKU, Original_Quantity, Is_Set_Component`, as today.
- [ ] **Step 4: Run both; they pass. Remove the O1 marker. Run `tests/test_set_decoder.py tests/audit/test_06_second_pass.py`**

### Task D2: order rules evaluate per rule over the whole frame (08-R1)

**Files:**
- Modify: `shopify_tool/rules.py`: `RuleEngine.apply` (the order-level section). New methods replace the
  per-order use of `_evaluate_order_conditions` (delete it once unused) and of the `_calculate_*` and `_check_*`
  helpers.
- Test: `tests/audit/test_08_rules_undo.py` (remove both R1 markers), `tests/test_rules.py`

**Interfaces:**
- Produces:
  - `RuleEngine._order_condition_rows(self, df: pd.DataFrame, keys: pd.Series, condition: dict) -> pd.Series`:
    one bool per row, the same for every row of an order, and False where `keys` is NaN.
  - `RuleEngine._order_step_rows(self, df: pd.DataFrame, keys: pd.Series, step: dict) -> pd.Series`: the step's
    conditions combined by `ALL`/`ANY`. An unusable condition is no match, with one warning per step.

- [ ] **Step 1: Write the pinning tests** (`tests/test_rules.py`, class `TestOrderRulesVectorised`).
  They pass on today's engine.

```python
FRAME = pd.DataFrame({
    "Order_Number": ["#1", "#1", "#2", "#3", "#3", "#3", None],
    "SKU": ["A", "B", "A", "C", "C", None, "A"],
    "Product_Name": ["Apple", "Box", "Apple", "Cup", "Cup", "Lid", "Apple"],
    "Quantity": [1, 4, 2, 1, 1, 3, 9],
    "Order_Volumetric_Weight": [1.5, 1.5, 0.2, float("nan"), 9.0, 9.0, 9.0],
    "All_No_Packaging": [True, True, False, "true", "true", "true", True],
    "Order_Min_Box": ["S", "S", "M", "L", "L", "L", "S"],
})

@pytest.mark.parametrize("condition, tagged", [
    ({"field": "item_count", "operator": "is greater than", "value": "1"}, {"#1", "#3"}),
    ({"field": "total_quantity", "operator": "is greater than or equal", "value": "5"}, {"#1", "#3"}),
    ({"field": "unique_sku_count", "operator": "equals", "value": "2"}, {"#1", "#3"}),  # NaN counts
    ({"field": "max_quantity", "operator": "is greater than", "value": "3"}, {"#1"}),
    ({"field": "order_volumetric_weight", "operator": "is greater than", "value": "1"}, {"#1"}),  # first row
    ({"field": "all_no_packaging", "operator": "equals", "value": "true"}, {"#1", "#3"}),
    ({"field": "order_min_box", "operator": "equals", "value": "M"}, {"#2"}),
    ({"field": "has_sku", "operator": "equals", "value": "A"}, {"#1", "#2"}),
    ({"field": "has_sku", "operator": "does not equal", "value": "A"}, {"#3"}),
    ({"field": "has_product", "operator": "contains", "value": "pp"}, {"#1", "#2"}),
    ({"field": "SKU", "operator": "equals", "value": "C"}, {"#3"}),
    ({"field": "SKU", "operator": "does not equal", "value": "C"}, {"#1", "#2"}),
    ({"field": "no_such_column", "operator": "equals", "value": "x"}, set()),
])
def test_order_rule_matches_the_orders_it_names(condition, tagged):
    rule = {"name": "o", "level": "order", "conditions": [condition],
            "actions": [{"type": "ADD_TAG", "value": "hit"}]}
    out = RuleEngine([rule]).apply(FRAME.copy())
    assert set(out.loc[out["Status_Note"].fillna("").str.contains("hit"), "Order_Number"]) == tagged

def test_order_steps_gate_on_the_step_before():
    rule = {"name": "g", "level": "order", "steps": [
        {"conditions": [{"field": "item_count", "operator": "is greater than", "value": "1"}],
         "match": "ALL", "actions": [{"type": "ADD_TAG", "value": "s1"}]},
        {"conditions": [{"field": "has_sku", "operator": "equals", "value": "B"}],
         "match": "ALL", "actions": [{"type": "ADD_TAG", "value": "s2"}]}]}
    out = RuleEngine([rule]).apply(FRAME.copy())
    notes = out.groupby("Order_Number")["Status_Note"].first()
    assert notes.to_dict() == {"#1": "s1, s2", "#2": "", "#3": "s1"}

def test_added_products_keep_order_then_rule_order():
    rules = [{"name": n, "level": "order", "priority": p,
              "conditions": [{"field": "has_sku", "operator": "equals", "value": "A"}],
              "actions": [{"type": "ADD_PRODUCT", "sku": g, "quantity": 1}]}
             for n, p, g in [("r1", 1, "G1"), ("r2", 2, "G2")]]
    out = RuleEngine(rules).apply(FRAME.copy())
    added = out.iloc[len(FRAME):]
    assert list(zip(added["Order_Number"], added["SKU"])) == [("#1", "G1"), ("#1", "G2"), ("#2", "G1"), ("#2", "G2")]

def test_matched_rows_cover_every_line_of_a_matched_order():
    rule = {"name": "o", "level": "order",
            "conditions": [{"field": "has_sku", "operator": "equals", "value": "B"}],
            "actions": [{"type": "ADD_TAG", "value": "hit"}]}
    engine = RuleEngine([rule])
    engine.apply(FRAME.copy())
    assert engine.matched_rows.tolist() == [True, True, False, False, False, False, False]
```

These tests pin today's behaviour. If one of them fails on today's engine, its expectation is wrong: correct
the expectation to today's output before you change the engine.

- [ ] **Step 2: Run them; they pass on today's engine. Run `test_AUDIT_08_R1_*` with `--runxfail`; both fail on `seconds < 0.5`**
- [ ] **Step 3: Implement.** Use `keys = df["Order_Number"]` (raw, as `groupby(..., sort=False)` grouped it).
  For each order rule, set `alive = keys.notna()`. For each step, `matched = alive & _order_step_rows(df, keys, step)`.
  If nothing matched, stop. Otherwise: `matched_rows |= matched`; run the `ADD_TAG`/`ADD_ORDER_TAG` actions once
  with `matched`; run the other actions once with `matched & ~keys.duplicated()` (the first row of each order);
  set `alive = matched`. The condition rows:
  - Numeric order fields use `df.groupby(keys)[col].transform(...)`: `size` for `item_count`, `sum` for
    `total_quantity`, `nunique(dropna=False)` for `unique_sku_count` (today counts `None` as a SKU), `max` for
    `max_quantity`. Then the global operator runs on that series. A missing column gives `0`.
  - First-row fields (`order_volumetric_weight`, `all_no_packaging`, `order_min_box`) take the **first row's
    value, NaN included**: `transform("first", skipna=False)`. Check it with context7, and use a positional
    first-row broadcast if it is unavailable.
  - Line fields, `has_sku` and `has_product`: the operator runs once over the column, then a grouped
    `transform("any")`, or `transform("all")` for `NEGATIVE_OPERATORS`. Keep today's guards: an empty value for
    `has_sku`/`has_product` is no match; an unknown operator falls back to `equals`.
  - Rows whose key is NaN never match.
  New rows from `ADD_PRODUCT` keep today's order: by order (first appearance), then rule, then step, then action.
  Tag each collected row with that sort key, sort them, and drop the key before the final `concat`.
- [ ] **Step 4: Run Step 2's tests without `--runxfail`; all pass. Remove both R1 markers. Run
  `tests/test_rules.py tests/audit/test_03_rule_engine.py tests/test_rule_test.py tests/test_rule_settle.py`**

### Task D3: dates are parsed once per format (08-R2)

**Files:** `shopify_tool/rules.py` (`_op_date_before`, `_op_date_after`, `_op_date_equals`, new `_parse_dates`),
`tests/audit/test_08_rules_undo.py` (remove both R2 markers), `tests/test_rules.py`

**Interfaces:**
- Produces: `_parse_dates(series: pd.Series) -> pd.Series`: naive `datetime64[ns]`, NaT where a value is blank or
  matches no format. It accepts exactly the inputs `_parse_date_safe` accepts, with the same results. If any
  non-blank value is unparseable it logs **one** WARNING:
  `[RULE ENGINE] {n} values in {series.name!r} are not dates, e.g. {first!r}`.
  `_parse_date_safe` stays for the rule's own value.

- [ ] **Step 1: Write the tests** (`tests/test_rules.py`, class `TestParseDates`)

```python
VALUES = ["2024-01-30", "30/01/2024", "30.01.2024", "2026-10-01 10:00:00", "2026-10-01 10:00:00 +0200",
          "2026-10-01T10:00:00+02:00", "2026-10-01T10:00:00Z", " 2024-01-30 ", "2026-10-01T10:00:00",
          "2026-10-01 10:00:00+0200", "2024-02-30", "1/2/2024", "", None, float("nan"), "not a date",
          pd.Timestamp("2024-01-30 08:00")]

@pytest.mark.parametrize("value", VALUES)
def test_parse_dates_matches_the_single_value_parser(value):
    got = _parse_dates(pd.Series([value], dtype=object)).iloc[0]
    want = _parse_date_safe(value)
    assert (pd.isna(got) and want is None) or got == want

def test_mixed_offsets_parse_to_the_date_as_written():
    s = pd.Series(["2026-03-28 23:30:00 +0200", "2026-03-30 00:30:00 +0300"], name="Created_At")
    assert _parse_dates(s).tolist() == [pd.Timestamp("2026-03-28 23:30"), pd.Timestamp("2026-03-30 00:30")]
```

- [ ] **Step 2: Run them; they fail (`_parse_dates` does not exist). Run both `test_AUDIT_08_R2_*` with `--runxfail`; they fail on their assertions**
- [ ] **Step 3: Implement.** Strip each value. For each format in `_parse_date_safe`'s list, in order, run
  `pd.to_datetime(remaining, format=fmt, errors="coerce")` over the rows that are still NaT. For the two offset
  formats, cut the trailing offset from the text first (`%z` accepts `+0200`, `+02:00` and `Z`) and parse the
  rest. That applies spec D9 (the date as written) and avoids pandas' mixed-offset error. Let the parametrized
  test decide the edge cases. The three operators become `_parse_dates(series).dt.normalize()` compared with the
  normalised rule date, with NaT counting as False.
- [ ] **Step 4: Run all of them; they pass. Remove both R2 markers. Run `tests/test_rules.py tests/audit/test_03_rule_engine.py`**

### Task D4: the Packing Tool JSON is built once per frame (09-O2, the builder)

**Files:**
- Modify: `shopify_tool/core.py`: replace `build_packing_order_data` with `build_packing_orders`, and call it
  inside the existing `try` of `_create_analysis_data_for_packing`. Leave the `except` branches alone: they are
  09-O5's, in #370.
- Test: `tests/audit/test_09_outputs_sets_ledger.py` (remove the O2 marker; repoint O5's patch, which stays
  marked), new `tests/test_packing_orders.py`

**Interfaces:**
- Produces: `core.build_packing_orders(df: pd.DataFrame) -> list[dict]`. It returns one dict per order, sorted by
  `Order_Number` (as `groupby` sorted it), with exactly the keys and values the old per-order builder gave. It
  calls `stock_ledger.fulfillable_orders(df)` once. The status is `"Unknown"` when `Order_Fulfillment_Status` is
  missing.

- [ ] **Step 1: Write the pinning test.** Copy today's `build_packing_order_data` into
  `tests/test_packing_orders.py` as `_order_reference`, with the same "frozen" comment:

```python
def test_orders_match_the_reference():
    expected = [_order_reference(str(n), g) for n, g in FRAME.groupby("Order_Number")]
    assert core.build_packing_orders(FRAME) == expected
```

`FRAME` covers: `Internal_Tags` of `"[]"`, `'["a","b"]'`, invalid JSON and NaN; `Tags` of `"x, y"`, `""` and NaN;
`Order_Min_Box` of NaN, `""` and `"M"`; `Warehouse_Name` of `""`, `"N/A"` and NaN (each falls back to
`Product_Name`); `Quantity` of NaN, `"3"` and `"x"` (which gives 0); an order with one line not fulfillable; a
no-SKU line in a fulfillable order; integer and string order numbers; `Status_Note` NaN.

In `test_AUDIT_09_O5_a_failed_packing_build_does_not_empty_the_session`, patch `core.build_packing_orders`
(`def broken(_df): raise ValueError(...)`) instead of `core.build_packing_order_data`. It stays marked for #370.

- [ ] **Step 2: Run it (it fails: no `build_packing_orders`), and `test_AUDIT_09_O2_*` with `--runxfail` (it fails on `seconds < 2.0`)**
- [ ] **Step 3: Implement.** Compute the per-item fields once over the whole frame with column operations: the
  name fallback, `int` quantity or 0, and `str(... or "")` for the notes. Then take one
  `groupby("Order_Number", sort=True)`; for each group, the first row gives the order fields, and
  `group[item_cols].to_dict("records")` gives the items.
- [ ] **Step 4: Run both; they pass. Remove the O2 marker. Run the O5 tests with `--runxfail`: each still fails on
  its own assertion. Run `tests/test_packing_lists.py tests/test_packing_list_order.py tests/audit/test_04_outputs.py`**

### Task D5: reports generate on a `Worker` (09-O2, the GUI thread)

**Files:**
- Create: `shopify_tool/report_jobs.py`, with no Qt imports
- Modify: `gui/actions_handler.py`: `_generate_reports`, `_generate_single_report`, `__init__`
  (`self._reports_worker = None`), new `_on_reports_generated` and `_on_reports_finished`. Delete
  `_create_analysis_json`; it moves to `report_jobs.packing_list_json`.
- Test: new `tests/test_report_jobs.py`; rewrite
  `tests/test_generate_reports_dialog.py::test_one_failing_report_does_not_cost_the_user_the_others`

**Interfaces:**
- Produces, in `shopify_tool/report_jobs.py`:
  - `@dataclass class ReportOutcome: name: str; report_type: str; output_file: str | None = None;
    packaging_file: str | None = None; removed_empty: bool = False; failed: bool = False; locked_file: str | None = None`
  - `packing_list_json(df: pd.DataFrame, session_id: str) -> dict`: today's `_create_analysis_json`, on
    `core.build_packing_orders`.
  - `generate_report(report_config: dict, session_path, analysis_df: pd.DataFrame, tag_categories: dict,
    session_id: str) -> ReportOutcome`: today's file work of `_generate_single_report`. That is: output folder,
    file name, `barcode_processor.invalidate_label_pdfs`, the packing list XLSX and JSON (the JSON is still
    written with `open(..., "w")`, which is 09-O5's, in #370), the stock export. `report_config["report_type"]`
    picks the kind. A `PermissionError` gives `failed=True, locked_file=<name>`; any other exception is logged
    and gives `failed=True`.
  - `generate_reports(batch: list[dict], session_path, analysis_df, tag_categories, session_id,
    session_manager=None) -> list[ReportOutcome]`: one outcome per config, in batch order, and one failure never
    stops the others. Afterwards, if a packing list was written and `session_manager` is given, it updates
    `statistics.packing_lists_count` and `statistics.packing_lists` once, as today.
- In `ActionsHandler`:
  - `_generate_reports(batch, session_path)`: runs the stale check, as today. While `self._reports_worker` is set
    it does `_results_toast("Reports are still being generated")` and returns. Otherwise it takes a snapshot on
    the GUI thread (`analysis_results_df.copy()`, `dict(tag_categories)`, the session id) and starts
    `Worker(report_jobs.generate_reports, ...)` on `self.mw.threadpool`, with `result` connected to
    `_on_reports_generated`, `error` to `on_task_error`, and `finished` to `_on_reports_finished`.
  - `_on_reports_generated(outcomes: list[ReportOutcome]) -> None`, on the GUI thread: the toasts,
    `log_activity` and `show_error` calls, with today's exact texts, then `session_browser.mark_dirty()` if a
    packing list was written.
  - `_generate_single_report(report_type, report_config, session_path)` stays **synchronous**, for its direct
    callers: `self._on_reports_generated(report_jobs.generate_reports([dict(report_config, report_type=report_type)], ...))`.

- [ ] **Step 1: Write the failing tests** (`tests/test_report_jobs.py`)

```python
def test_one_failing_report_does_not_stop_the_others(monkeypatch, tmp_path):
    def fake(config, *a, **k):
        if config["name"] == "DPD":
            raise ValueError("no such column")
        return ReportOutcome(config["name"], config["report_type"], output_file="x.xlsx")
    monkeypatch.setattr(report_jobs, "generate_report", fake)
    batch = [{"name": n, "report_type": "packing_lists"} for n in ("DHL", "DPD", "Daily ERP")]
    out = report_jobs.generate_reports(batch, tmp_path, FRAME, {}, "s")
    assert [(o.name, o.failed) for o in out] == [("DHL", False), ("DPD", True), ("Daily ERP", False)]

def test_reports_toast_from_the_gui_thread(main_window, qtbot, monkeypatch, tmp_path):
    # session open with a 2-order state, as tests/test_stale_session.py's _open_with_state does
    threads = []
    monkeypatch.setattr(main_window.actions_handler, "_results_toast",
                        lambda *a, **k: threads.append(threading.current_thread()))
    main_window.actions_handler._generate_reports([PACKING_ALL], main_window.session_path)
    qtbot.waitUntil(lambda: threads, timeout=10_000)
    assert threads == [threading.main_thread()]
    assert (Path(main_window.session_path) / "packing_lists" / "ALL.xlsx").exists()

def test_a_report_uses_the_frame_as_it_was_at_the_click(main_window, qtbot, monkeypatch):
    gate = threading.Event()
    real = report_jobs.generate_reports
    def held(*a, **k):
        gate.wait(5)
        return real(*a, **k)
    monkeypatch.setattr(report_jobs, "generate_reports", held)
    main_window.actions_handler._generate_reports([PACKING_ALL], main_window.session_path)
    main_window.actions_handler.bulk_change_status(["#1002"], False)  # an edit while it runs
    gate.set()
    qtbot.waitUntil(lambda: main_window.actions_handler._reports_worker is None, timeout=10_000)
    data = json.loads((Path(main_window.session_path) / "packing_lists" / "ALL.json").read_text(encoding="utf-8"))
    assert [o["order_number"] for o in data["orders"]] == ["#1001", "#1002"]
    assert stock_ledger.is_fulfillable(main_window.analysis_results_df, "#1002") is False
```

`PACKING_ALL = {"name": "ALL", "report_type": "packing_lists", "output_filename": "ALL.xlsx", "filters": []}`.
Open the session with a 2-order frame that has the packing-list columns (copy the frame of the O5 test in
`tests/audit/test_09_outputs_sets_ledger.py`). `_generate_reports` must look up `report_jobs.generate_reports`
when it is called, not import the name, or the patch in the third test has no effect.
Rewrite `test_one_failing_report_does_not_cost_the_user_the_others` in `tests/test_generate_reports_dialog.py` as
a test of `_on_reports_generated`: given outcomes `DHL` ok, `DPD` failed, `Daily ERP` ok, `show_error` is called
once and names `DPD`.

- [ ] **Step 2: Run them; they fail (no `report_jobs`)**
- [ ] **Step 3: Implement the module and the handler changes above**
- [ ] **Step 4: Run them and `tests/test_generate_reports_dialog.py tests/test_label_pdf_invalidation.py tests/test_stale_session.py tests/audit/test_04_outputs.py tests/test_results_screen.py`; all pass. The O5 tests still xfail on their own assertions under `--runxfail`**

### Group D checkpoint

- [ ] Run the full gate. Expected: 14 xfailed, ruff clean. Group C's tests still fail on their own assertions
  under `--runxfail` (Global Constraints).
- [ ] Run `graphify update .`.
- [ ] Commit, starting the message with `D: vectorise set decoding, order rules, dates and the packing JSON; reports off the GUI thread`.
  The body lists AUDIT-09-O1, AUDIT-09-O2, AUDIT-08-R1, AUDIT-08-R2 and the tests unmarked.
- [ ] Push. Tick D.

---

## Group F: allocation rules (07-M1, 09-O3, 09-O4, 08-R3, 08-R4)

**Risk: high for 07-M1 and 08-R4.**

**PR warning text:** "F changes results. (1) Lots: undated, unbatched stock now ships **first**, then dated or
batched lots, earliest expiry first. Until now undated stock shipped last, so for every client with lot columns
the lot labels on packing lists and stock exports change. Negative stock rows now net against their own lot,
then in draw order, so lots never promise more than the SKU total (ADR 0015 updated). (2) Text rule operators
and report filters ignore case and surrounding spaces: a rule or filter `equals dhl` now matches `DHL`, and
`has_sku equals abc` matches `ABC`. Rules that never matched may start matching; check the client rule lists.
(3) An order can be force-fulfilled, or bulk-marked fulfillable, with a SKU missing from the stock file. The
toast names the SKU. The Results toast has no warning style, so the words carry the warning; a styled warning
would be web-tier work. (4) Set CSV imports trim SKUs. (5) The Rules page lists rules in run order."

### Task F1: lots net negative rows, and undated lots are drawn first (07-M1)

**Files:**
- Modify: `shopify_tool/analysis.py`: `_build_fifo_lots` (its docstring too), and the `with_lots` docstring line
  that says "FIFO (earliest expiry first)"
- Modify: `docs/adr/0015-lot-allocation-is-derived-not-stored.md`
- Test: `tests/audit/test_07_core_io.py` (tighten M1, remove its marker), `tests/test_lot_allocation.py`

**Interfaces:**
- Produces: `_build_fifo_lots(stock_df) -> dict[str, list[dict]] | None`, with an unchanged signature and lot dict
  shape. A SKU's lots now sum to its net total, and SKUs whose net total is ≤ 0 have no lots. The draw order is
  the key `(0 if expiry == "1" and batch is None else 1, expiry_dt or SENTINEL, batch or "")`.

- [ ] **Step 1: Tighten the M1 test and write the new tests**

Append to `test_AUDIT_07_M1_a_lot_column_does_not_change_the_answer`:

```python
    table = lot_table(pd.DataFrame({"SKU": ["A", "A"], "Stock": [10, -3],
                                    "Expiry_Date": ["2027-01-01", "2027-02-01"]}))
    assert [(l["expiry"], l["qty"]) for l in table["A"]] == [("2027-01-01", 7.0)]
```

In `tests/test_lot_allocation.py`, build each frame with `_stock(rows)` → `pd.DataFrame(rows, columns=["SKU",
"Stock", "Expiry_Date", "Batch"])`, where `None` means a blank cell:

```python
def _lots(table, sku="A"):
    return [(l["expiry"], l["batch"], l["qty"]) for l in table[sku]]

def test_a_negative_row_nets_its_own_lot_first():
    t = lot_table(_stock([("A", 5, "2027-01-01", "B1"), ("A", 10, "2027-03-01", "B2"), ("A", -4, "2027-03-01", "B2")]))
    assert _lots(t) == [("2027-01-01", "B1", 5.0), ("2027-03-01", "B2", 6.0)]

def test_a_negative_remainder_nets_in_draw_order():
    t = lot_table(_stock([("A", 5, None, None), ("A", 10, "2027-01-01", None), ("A", -7, "2027-05-01", None)]))
    assert _lots(t) == [("2027-01-01", None, 8.0)]

def test_undated_unbatched_lots_are_drawn_first():
    t = lot_table(_stock([("A", 3, "2027-01-01", None), ("A", 2, None, None), ("A", 4, None, "B9")]))
    assert _lots(t) == [("1", None, 2.0), ("2027-01-01", None, 3.0), ("1", "B9", 4.0)]

def test_lot_totals_equal_the_sku_total():
    rows = [("A", 4, "2027-01-01", None), ("A", -1, None, None), ("B", 2, "2027-01-01", None), ("B", -5, None, None)]
    t = lot_table(_stock(rows))
    assert sum(l["qty"] for l in t["A"]) == 3.0
    assert "B" not in t

def test_an_order_ships_the_undated_lot_first():
    # run_analysis with stock A: +5 (Годност 2027-01-01) and +5 (blank Годност); one order for 3 x A
    line = with_lots(df, lot_table(<internal stock>)).iloc[0]
    assert [e["expiry"] for e in line["Lot_Details"]] == ["1"]
```

- [ ] **Step 2: Run them with `test_AUDIT_07_M1_*` under `--runxfail`; all fail on their assertions**
- [ ] **Step 3: Implement** (the netting algorithm, which the signature does not determine):

```python
for sku, group in stock_df.groupby("SKU"):
    rows = [(_lot_fields(row), qty) for row in group.itertuples(index=False)]  # ((expiry, expiry_dt, batch), qty)
    lots = sorted(({"expiry": e, "expiry_dt": d, "batch": b, "qty": q} for (e, d, b), q in rows if q > 0),
                  key=_draw_key)
    for (e, _d, b), q in rows:
        if q >= 0:
            continue
        debt = -q
        same = [lot for lot in lots if (lot["expiry"], lot["batch"]) == (e, b)]
        rest = [lot for lot in lots if all(lot is not s for s in same)]
        for lot in same + rest:                       # own lot first, then draw order
            take = min(lot["qty"], debt)
            lot["qty"] -= take
            debt -= take
            if debt <= 0:
                break
    lots = [lot for lot in lots if lot["qty"] > 0]
    if lots:
        fifo_lots[str(sku)] = lots
```

`_lot_fields(row)` holds today's expiry and batch parsing, moved out of the loop unchanged. `_draw_key` is the key
in Interfaces.

- [ ] **Step 4: Run them; they pass. Remove the M1 marker. Run `tests/test_lot_allocation.py tests/test_lot_integrity.py
  tests/audit/test_06_second_pass.py tests/test_stock_export.py`.** A test that pinned "undated last" now fails
  by design. Change its expectation to the new order, and name it in the commit body.
- [ ] **Step 5: Update ADR 0015.** In the Decision: "`with_lots` draws undated, unbatched lots first, then dated or
  batched lots, earliest expiry first. The opening lots net negative stock rows: each against the lot with the
  same expiry and batch first, any remainder in draw order, so a SKU's lots sum to its stock total." Add an
  "Amended 2026-10-05 (AUDIT-07-M1)" line under Status, and a Consequences bullet saying the change moved which
  lots ship first.

### Task F2: the stock export never holds a negative quantity (07-M1)

**Files:** `tests/test_stock_export.py` only. `_finalize_export_df` already clips at zero and drops rows ≤ 0.
This pins it end to end, as the owner asked.

- [ ] **Step 1: Write the test**

```python
@pytest.mark.parametrize("with_lots_column", [True, False])
def test_the_stock_export_never_holds_a_negative_quantity(tmp_path, monkeypatch, with_lots_column):
    # stock: A +10 and -3 (lot column when with_lots_column); B +5; C -2 only
    # orders: #1 needs 4 x A; #2 needs 2 x B, plus a manual line of -2 x B; #3 needs 1 x C
    written = []
    monkeypatch.setattr(stock_export, "_write_xls", lambda df, path: written.append(df))
    stock_export.create_stock_export(analysis_df=frame, output_file=str(tmp_path / "e.xls"),
                                     report_name="ERP", filters=[], writeoff_mode="off", tag_categories={})
    assert (written[0][stock_export.QTY_COL] > 0).all()
```

- [ ] **Step 2: Run it; it passes.** If it fails, the netting in F1 or `lot_parts` let a negative through: fix that, not the test.

### Task F3: force-fulfil and bulk mark-fulfillable name an unlisted SKU (09-O3)

**Files:**
- Modify: `shopify_tool/stock_ledger.py` (new `unlisted_skus`), `shopify_tool/analysis.py`
  (`toggle_order_fulfillment`, plus its docstring: the second element is the error when it fails, and a warning
  when it succeeds), `gui/actions_handler.py` (`toggle_fulfillment_status_for_order`, `bulk_change_status`)
- Test: `tests/audit/test_09_outputs_sets_ledger.py` (tighten both O3 tests, remove the markers), `tests/test_stock_ledger.py`

**Interfaces:**
- Produces: `stock_ledger.unlisted_skus(df, order_numbers) -> list[str]`: the sorted SKUs on these orders' SKU
  lines that no row lists in the stock file (`Final_Stock` null on every row of that SKU). Returns `[]` when the
  frame has no ledger columns.

- [ ] **Step 1: Tighten the O3 tests; write the ledger test**

```python
def test_AUDIT_09_O3_force_fulfilling_an_unlisted_sku_is_not_silent(unlisted_sku_order):
    ok, message, out = toggle_order_fulfillment(unlisted_sku_order.copy(), "#1")
    assert ok is True
    assert message == "Not in the stock file: X"
    assert out["Order_Fulfillment_Status"].tolist() == ["Fulfillable"]

# bulk test, after bulk_change_status(["#1"], True):
    assert mw.analysis_results_df["Order_Fulfillment_Status"].tolist() == ["Fulfillable"]
    assert [c.args[0] for c in mw.results_bridge.raise_toast.call_args_list] == [
        "1 order marked fulfillable · not in the stock file: X"]

# tests/test_stock_ledger.py
def test_unlisted_skus_names_skus_without_a_stock_row():
    df = pd.DataFrame({"Order_Number": ["#1", "#1", "#2"], "SKU": ["A", "X", "Y"], "Quantity": [1, 1, 1],
                       "Stock": [5, 0, 0], "Final_Stock": [5, None, None],
                       "Order_Fulfillment_Status": ["Not Fulfillable"] * 3})
    assert stock_ledger.unlisted_skus(df, ["#1"]) == ["X"]
    assert stock_ledger.unlisted_skus(df, ["#1", "#2"]) == ["X", "Y"]
```

- [ ] **Step 2: Run them, both O3 tests under `--runxfail`; they fail on their assertions**
- [ ] **Step 3: Implement.**
  - `toggle_order_fulfillment`: after a successful force-fulfil, if `unlisted_skus(df, [order_number])`, return
    `(True, f"Not in the stock file: {', '.join(skus)}", df)`.
  - `toggle_fulfillment_status_for_order`: on success with a message, also call
    `_results_toast(f"Order {order_number} marked fulfillable · {message[0].lower() + message[1:]}")`.
  - `bulk_change_status`: when `is_fulfillable` and `unlisted_skus(df, covered)`, append
    `f" · not in the stock file: {', '.join(skus)}"` to the success toast text.
  - A listed SKU that is short is still refused (`test_a_listed_sku_short_of_stock_is_refused` stays green).
- [ ] **Step 4: Run them; they pass. Remove both O3 markers. Run `tests/test_actions_handler.py tests/test_stock_ledger.py tests/test_analysis.py`**

### Task F4: set SKUs are trimmed on import and in the lookup (09-O4)

**Files:** `shopify_tool/set_decoder.py` (`import_sets_from_csv`, `_set_table` from D1),
`tests/audit/test_09_outputs_sets_ledger.py` (remove the O4 marker), `tests/test_set_decoder.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_a_saved_set_with_spaces_still_expands():
    out = decode_sets_in_orders(pd.DataFrame({"Order_Number": ["#1"], "SKU": ["SET-1"], "Quantity": [1]}),
                                {"SET-1 ": [{"sku": "A ", "quantity": 2}]})
    assert out["SKU"].tolist() == ["A"] and out["Quantity"].tolist() == [2]

def test_import_trims_set_and_component_skus(tmp_path):
    csv = tmp_path / "s.csv"
    csv.write_text("Set_SKU,Component_SKU,Component_Quantity\n SET-1 , A ,2\n", encoding="utf-8")
    assert import_sets_from_csv(str(csv)) == {"SET-1": [{"sku": "A", "quantity": 2}]}
```

- [ ] **Step 2: Run them and `test_AUDIT_09_O4_*` under `--runxfail`; they fail**
- [ ] **Step 3: Apply `csv_utils.normalize_sku` to `Set_SKU` and `Component_SKU` in the import, before the
  empty-SKU and duplicate checks. In `decode_sets_in_orders`, normalise the decoder dict once (keys and component
  SKUs) before `_set_table`. Two keys that normalise to the same SKU: the last one wins, with one warning.**
- [ ] **Step 4: Run them; they pass. Remove the O4 marker. Run `tests/test_set_decoder.py` (D1's reference test too)**

### Task F5: the Rules page order is the run order (08-R3)

**Files:** `shopify_tool/rules.py` (`RuleEngine.execution_order`), `tests/test_rules.py`

- [ ] **Step 1: Write the failing test**

```python
def test_the_page_order_is_the_run_order():
    rules = [{"name": "A", "enabled": False}, {"name": "B"}, {"name": "C", "priority": 1000}]
    assert [r["name"] for r in RuleEngine.execution_order(rules)] == ["B", "C", "A"]
    assert [r["name"] for r in RuleEngine(rules).rules] == ["B", "C"]

@pytest.mark.parametrize("rules", RULE_LISTS)  # 4 lists: mixed levels, priorities, enabled flags
def test_enabled_rules_list_in_the_order_the_engine_runs_them(rules):
    page = [r["name"] for r in RuleEngine.execution_order(rules) if r.get("enabled", True) is not False]
    assert page == [r["name"] for r in RuleEngine(rules).rules]
```

- [ ] **Step 2: Run them; the first fails (it gives A, C, B)**
- [ ] **Step 3: In `execution_order`, give the default priorities (1000, 1001, ...) to enabled rules first, in
  list order, then continue the count over disabled rules. The docstring says so.**
- [ ] **Step 4: Run them, `.venv/bin/python docs/audit/repro/08_R3_rule_order.py` (page and engine now agree),
  and `tests/test_settings_draft_rules.py tests/test_settings_rules_page.py`**

### Task F6: text operators ignore case and trim both sides (08-R4)

**Files:** `shopify_tool/rules.py` (`_op_equals`, `_op_not_equals`, `_op_contains`, `_op_not_contains`,
`_op_starts_with`, `_op_ends_with`, `_op_in_list`, `_op_not_in_list`, new `_fold`), `tests/test_rules.py`,
`tests/test_report_filters.py`

**Interfaces:**
- Produces: `_fold(values: pd.Series) -> pd.Series`, which is `values.astype(str).str.strip().str.casefold()`,
  and `_fold_value(value) -> str`. `equals` is `notna & (_fold(s) == _fold_value(v))`, and `does not equal` is
  its negation, so NaN gives True, as today. A numeric column with a numeric rule value still compares as numbers.

- [ ] **Step 1: Write the failing tests**

```python
S = pd.Series([" DHL ", "dhl", "Dhl-Express", None, "UPS"])

@pytest.mark.parametrize("op, value, want", [
    ("equals", "dhl ", [True, True, False, False, False]),
    ("does not equal", " DHL", [False, False, True, True, True]),
    ("starts with", " dhl", [True, True, True, False, False]),
    ("ends with", "HL ", [True, True, False, False, False]),
    ("contains", " Express", [False, False, True, False, False]),
    ("does not contain", "dhl", [False, False, False, True, True]),
    ("in list", "dhl , ups", [True, True, False, False, True]),
    ("not in list", "DHL", [False, False, True, True, True]),
])
def test_text_operators_ignore_case_and_spaces(op, value, want):
    assert getattr(rules, OPERATOR_MAP[op])(S, value).tolist() == want   # from shopify_tool import rules

# tests/test_report_filters.py
def test_a_report_filter_ignores_case_and_spaces():
    df = pd.DataFrame({"Order_Number": ["#1", "#2"], "Shipping_Provider": ["DHL", "UPS"]})
    out = apply_report_filters(df, [{"field": "Shipping_Provider", "operator": "equals", "value": " dhl"}])
    assert out["Order_Number"].tolist() == ["#1"]
```

- [ ] **Step 2: Run them; equals, does not equal, starts with and ends with fail; the filter test fails**
- [ ] **Step 3: Implement with `_fold` / `_fold_value`. The numeric path of `equals`/`does not equal` with a
  non-numeric rule value folds as well.**
- [ ] **Step 4: Run them, `tests/test_rules.py tests/audit/test_03_rule_engine.py tests/test_report_filters.py
  tests/test_report_filters_exclude.py`, and D2's pinning tests: `has_sku equals A` still gives `{"#1", "#2"}`**

### Group F checkpoint

- [ ] Run the full gate. Expected: 10 xfailed, ruff clean.
- [ ] Run `graphify update .`.
- [ ] Commit, starting the message with `F: lots net negative rows and ship undated stock first; case-insensitive text rules; unlisted SKUs warn`.
  The body lists AUDIT-07-M1, AUDIT-09-O3, AUDIT-09-O4, AUDIT-08-R3, AUDIT-08-R4, the tests unmarked or tightened,
  any test whose expectation changed because of the new draw order, and the ADR 0015 amendment.
- [ ] Push. Tick F.

---

## Group E: per-edit I/O (07-H2, 08-U2, 07-M5, 07-L1)

### Design note

1. **On the click.** `save_session_state` writes `current_state.pkl` through `session_state.save_state` (lock,
   stamp check, pickle, replace) and returns. Its two failure dialogs are unchanged. Everything else it used to
   write goes to the queue.

2. **The queue.** It lives in `gui/session_write_queue.py`, as `SessionWriteQueue(QObject)`, and the main window
   owns one (`self.write_queue`, created early in `MainWindow.__init__`).
   - *Thread.* One daemon `threading.Thread`, named `session-writes`, started on the first `submit`. A single
     thread means two writes never overlap.
   - *Keys.* A key is `(session_path, kind)`, where kind is one of `history`, `inventory_memory`,
     `analysis_stats`, `session_info`, `undo_history`.
   - *Coalescing.* Submitting to a key that is already pending replaces its job and keeps its place in line. A job
     that is already running is never cancelled; the newer job runs after it. Every job writes a whole snapshot,
     so the last job submitted always wins.
   - *Order between sessions.* First in, first out, by the time each key was first queued. A session switched
     away from keeps its pending writes, and they land on the right session, because every job carries its own
     path.
   - *Snapshots.* A job captures copies taken on the GUI thread at submit time: `df.copy()` (lazy under pandas 3
     copy-on-write), `dict(stats)`, and a copy of the operations list. It never reads live window state.
   - *Flush.* `flush(session_path=None, timeout=None) -> bool` waits until no key of that session (or of any
     session) is pending or running.
     - `_reset_session_state`, which every way into another session or client calls, flushes with a 10 s
       timeout, and on timeout logs a warning and carries on: the jobs still land.
     - `ActionsHandler.run_analysis` flushes with a 30 s timeout before it starts the run. Repeat detection reads
       history, and inventory memory feeds the run. On timeout it does not start, and it shows the toast "Your
       last changes are still being saved. Run the analysis again in a moment."
     - `closeEvent` flushes with a 10 s timeout. If writes are still pending, it asks, using
       `QMessageBox.question` (no confirm component exists in `gui/components`). The title is "Still saving this
       session" and the text is "History and stock memory are still being written to the server. If you close
       now, they're written the next time this session is saved." The buttons are "Keep waiting" (the default;
       it flushes another 10 s and asks again) and "Close anyway", which logs the pending keys at ERROR.
   - *Failure.* A job that raises or returns `False` is logged with its traceback on the worker thread, and the
     queue emits `failed(session_path: str, kind: str)`. The main window connects it to
     `_on_session_write_failed`, which runs on the GUI thread because the signal is queued across threads; check
     the delivery with context7. That slot shows a toast for `history` ("Fulfilment history wasn't saved. It's
     saved again with your next change.") and for `inventory_memory` ("Inventory memory wasn't updated. It's
     updated again with your next change."). The other kinds only log, as today. The worker never calls `toast`
     or `show_error`.
   - *No window.* `submit_or_run(queue, session_path, kind, job)` runs the job immediately, logging any failure,
     when `queue` is `None`. That keeps the `SimpleNamespace` windows in the existing tests working unchanged.

3. **`current_state.xlsx`.** It is no longer written, by `save_session_state` or by `core._save_results_and_reports`.
   `_load_session_analysis` reads `current_state.pkl`, then `fulfillment_analysis.xlsx`, then the legacy
   `analysis_report.xlsx` (the `analysis_data.json` gate is unchanged). `stock_export.merge_session_stock_exports`
   falls back from the pickle to `fulfillment_analysis.xlsx`. Old `current_state.xlsx` files stay on disk and are
   never read: once runs stop rewriting it, the file can be older than the session's current run.

4. **08-U2 undo records.** The record keeps its shape, `affected_rows_before: list[dict]` plus `row_positions`.
   For the edit types, the records hold `Order_Number` and the columns that type's undo handler restores. The map
   is `UndoManager.RESTORED_COLUMNS`:

   | Types | Columns |
   |---|---|
   | `toggle_status`, `bulk_change_status` | `Order_Fulfillment_Status` |
   | `add_tag` | `Status_Note` |
   | `add_internal_tag`, `remove_internal_tag`, `bulk_add_tag`, `bulk_remove_tag` | `Internal_Tags` |
   | `change_quantity` | `Quantity`, `Order_Fulfillment_Status` |

   The removal types (`remove_item`, `remove_order`, `bulk_remove_sku`, `bulk_remove_orders_with_sku`,
   `bulk_delete_orders`) keep whole rows, because `_reinsert` puts them back. Every handler reads columns by name,
   so an older file with whole rows loads and undoes unchanged; no format version is needed. `_save_history` goes
   through the queue (kind `undo_history`); the job creates `analysis/` itself.

5. **07-M5 backups.** Inventory-memory saves make no backup: `save_shopify_config(..., backup=False)`. Memory is
   derived data, rebuilt from the session's state on its next save or by the next run, so a backup of it restores
   nothing that the session doesn't already hold. A separate rotation would put a copy, a glob and unlinks on the
   share for every edit, which is the I/O that H2 removes. The 10 slots then hold Settings changes only.

6. **07-L1 history.** The whole rewrite stays, but now runs in the background and coalesced. Only the run
   prunes: `record_session(..., existing_sessions=)` drops rows whose `Session` is set and not among the client's
   session folders. The run lists them with one `os.scandir`. It does not prune when the listing fails, or when
   the listing does not contain the current session (a wrong or unreachable folder). Edits never prune. Rows of
   abandoned sessions stay. `_write_atomic` and its retry belong to 07-M4, in #370.

**Risk: high.** Background writes can be lost on exit or land out of order; the queue's FIFO order, its flushes
and the close dialog cover that. An undo file from before the change must still load.

**PR warning text:** "E: an edit now writes only `current_state.pkl` before the window responds. History,
inventory memory, `analysis_stats.json`, `session_info` and the undo file are written in the background, in
order, one at a time, and are flushed before a session switch, before a run, and on close (which asks if the
server is slow). `current_state.xlsx` is no longer written. A session whose pickle is unreadable opens from
`fulfillment_analysis.xlsx`, so it shows the run's results without later edits. Old `current_state.xlsx` files
are left in place but ignored. Inventory-memory saves no longer make config backups. The run removes history rows
of deleted session folders. Undo records for edits store only the changed columns, and older undo files still load."

### Task E1: the per-session coalescing write queue

**Files:** Create `gui/session_write_queue.py` and `tests/test_session_write_queue.py`.

**Interfaces:**
- Produces:
  - `HISTORY, INVENTORY_MEMORY, ANALYSIS_STATS, SESSION_INFO, UNDO_HISTORY: str`
  - `class SessionWriteQueue(QObject)`, with `failed = Signal(str, str)`, `__init__(self, parent=None)`,
    `submit(self, session_path: str, kind: str, job: Callable[[], object]) -> None`,
    `flush(self, session_path: str | None = None, timeout: float | None = None) -> bool`,
    `pending(self, session_path: str | None = None) -> list[tuple[str, str]]`
  - `submit_or_run(queue: SessionWriteQueue | None, session_path: str, kind: str, job: Callable[[], object]) -> None`

- [ ] **Step 1: Write the failing tests.** `gated(queue) -> threading.Event` submits a job on key `("S0", "gate")`
  that waits on the event, so later jobs queue behind it. Put it in a plain helper module,
  `tests/session_queue_support.py` (not a conftest), because E2, E3 and E5 use it too. A test that gates a queue
  sets the event in a `finally`, so that a failure never leaves the window's close waiting on it.

```python
def test_a_newer_write_replaces_a_pending_one(qapp):
    q, ran = SessionWriteQueue(), []
    gate = gated(q)
    q.submit("S1", HISTORY, lambda: ran.append("old"))
    q.submit("S1", HISTORY, lambda: ran.append("new"))
    gate.set()
    assert q.flush(timeout=5) and ran == ["new"]

def test_a_replaced_write_keeps_its_place_in_line(qapp):
    q, ran = SessionWriteQueue(), []
    gate = gated(q)
    q.submit("S1", HISTORY, lambda: ran.append("s1-old"))
    q.submit("S2", HISTORY, lambda: ran.append("s2"))
    q.submit("S1", HISTORY, lambda: ran.append("s1-new"))
    q.submit("S1", ANALYSIS_STATS, lambda: ran.append("s1-stats"))
    gate.set()
    q.flush(timeout=5)
    assert ran == ["s1-new", "s2", "s1-stats"]

def test_a_write_submitted_while_its_key_runs_runs_after_it(qapp):
    # job A for (S1, history) blocks on an event; submit B for the same key; release; flush
    assert ran == ["A", "B"]

def test_flush_times_out_and_says_so(qapp):
    q = SessionWriteQueue()
    gate = gated(q)
    assert q.flush(timeout=0.1) is False
    gate.set()
    assert q.flush(timeout=5) is True and q.pending() == []

def test_a_failed_write_is_signalled_on_the_gui_thread(qapp, qtbot):
    q, threads = SessionWriteQueue(), []
    q.failed.connect(lambda path, kind: threads.append((path, kind, threading.current_thread())))
    q.submit("S1", HISTORY, lambda: False)
    q.submit("S1", SESSION_INFO, lambda: 1 / 0)
    qtbot.waitUntil(lambda: len(threads) == 2, timeout=5000)
    assert threads == [("S1", HISTORY, threading.main_thread()), ("S1", SESSION_INFO, threading.main_thread())]

def test_without_a_queue_the_job_runs_now():
    ran = []
    submit_or_run(None, "S1", HISTORY, lambda: ran.append(1))
    assert ran == [1]
```

- [ ] **Step 2: Run them; they fail (no module)**
- [ ] **Step 3: Implement** (the algorithm the signature leaves open):

```python
def submit(self, session_path, kind, job):
    with self._cond:
        self._pending[(str(session_path), kind)] = job   # OrderedDict: replacing keeps the key's place
        self._ensure_thread()
        self._cond.notify_all()

def _run(self):
    while True:
        with self._cond:
            while not self._pending:
                self._cond.wait()
            key, job = self._pending.popitem(last=False)
            self._running = key
        try:
            ok = job() is not False
        except Exception:
            logger.exception(f"Background write {key[1]} failed for {key[0]}")
            ok = False
        with self._cond:
            self._running = None
            self._cond.notify_all()
        if not ok:
            self.failed.emit(*key)

def flush(self, session_path=None, timeout=None):
    deadline = None if timeout is None else time.monotonic() + timeout
    with self._cond:
        while self._busy(session_path):          # any pending key, or the running one, of that session
            left = None if deadline is None else deadline - time.monotonic()
            if left is not None and left <= 0:
                return False
            self._cond.wait(left)
    return True
```

- [ ] **Step 4: Run them; they pass**

### Task E2: an edit writes only the pickle on the click (07-H2)

**Files:**
- Modify: `gui/main_window_pyside.py`: `follow_inventory_memory` becomes
  `follow_inventory_memory(profile_manager, client_id: str, session_path: str, df: pd.DataFrame) -> None`, with
  the same rule (only the session that owns the memory rewrites it); `save_session_state`; `__init__` (creates
  `write_queue`, and connects `failed` to `_on_session_write_failed`); new
  `_on_session_write_failed(self, session_path: str, kind: str) -> None`
- Test: `tests/audit/test_07_core_io.py` (edit and unmark H2), new `tests/test_save_session_queue.py`

- [ ] **Step 1: Edit the H2 test; write the failing tests.** In `test_AUDIT_07_H2_*`, add the `qapp` fixture and
  `write_queue=SessionWriteQueue()` to `pc`, and append after the timing:

```python
    assert pc.write_queue.flush(timeout=30)
    history = fulfillment_history.load(fulfillment_history.history_path(pc.profile_manager, "M"))
    assert (history["Session"] == Path(pc.session_path).name).any()
    info = json.loads((Path(pc.session_path) / "session_info.json").read_text(encoding="utf-8"))
    assert session_state.order_counts(pc.analysis_results_df).items() <= info.items()
```

In `tests/test_save_session_queue.py` (using the `main_window` fixture, `_orders` and `_open_with_state` from
`tests/test_stale_session.py`; move them to a shared helper module if importing them is awkward):

```python
def test_an_edit_writes_only_the_pickle_before_returning(main_window, monkeypatch):
    path = _open_with_state(main_window, _orders("Fulfillable", "Fulfillable"))
    gate = gated(main_window.write_queue)
    calls = []
    monkeypatch.setattr(fulfillment_history, "record_session", lambda *a, **k: calls.append("history") or True)
    monkeypatch.setattr(main_window.session_manager, "update_session_info", lambda *a, **k: calls.append("info") or True)
    before = session_state.state_stamp(path)
    main_window.actions_handler.bulk_change_status(["#1002"], False)
    assert session_state.state_stamp(path) != before        # the pickle is written
    assert calls == []                                       # nothing else yet
    gate.set()
    assert main_window.write_queue.flush(timeout=10)
    assert sorted(calls) == ["history", "info"]

def test_a_failed_history_write_toasts_on_the_gui_thread(main_window, qtbot, monkeypatch):
    _open_with_state(main_window, _orders("Fulfillable"))
    seen = []
    monkeypatch.setattr(fulfillment_history, "record_session", lambda *a, **k: False)
    monkeypatch.setattr(main_window_module, "toast",
                        lambda src, text, **k: seen.append((text, threading.current_thread())))
    main_window.actions_handler.bulk_change_status(["#1001"], False)
    qtbot.waitUntil(lambda: seen, timeout=5000)
    assert seen == [("Fulfilment history wasn't saved. It's saved again with your next change.",
                     threading.main_thread())]
```

- [ ] **Step 2: Run them and the H2 test under `--runxfail`; they fail (H2 on `seconds < 1.0`)**
- [ ] **Step 3: Implement `save_session_state` per design note §1–2.** After `save_state`, it takes one snapshot
  and calls `submit_or_run(getattr(self, "write_queue", None), self.session_path, kind, job)` for:
  - `HISTORY`: `record_session(history_path, session_name, df)`
  - `INVENTORY_MEMORY`, only when memory is on: `follow_inventory_memory(...)`
  - `ANALYSIS_STATS`, when there are stats: `atomic_write_json(stats_path, stats)`
  - `SESSION_INFO`, when there is a session manager: `update_session_info(path, order_counts(df))`

  Delete the `current_state.xlsx` line and the ponytail comment.
- [ ] **Step 4: Run them; they pass. Remove the H2 marker. Run `tests/test_save_session_history.py tests/test_stale_session.py tests/test_session_state.py`**

### Task E3: the queue is flushed on session switch, before a run, and on close (07-H2)

**Files:** `gui/main_window_pyside.py` (`_reset_session_state`, `closeEvent`), `gui/actions_handler.py`
(`run_analysis`), `tests/test_save_session_queue.py`, `tests/test_actions_handler.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_switching_sessions_waits_for_pending_writes(main_window):
    _open_with_state(main_window, _orders("Fulfillable"))
    done = []
    main_window.write_queue.submit("S", HISTORY, lambda: time.sleep(0.3) or done.append(1))
    main_window._reset_session_state()
    assert done == [1]

def test_closing_waits_for_pending_writes(main_window):
    done = []
    main_window.write_queue.submit("S", HISTORY, lambda: time.sleep(0.3) or done.append(1))
    main_window.close()
    assert done == [1]

def test_close_asks_when_writes_outlast_the_wait(main_window, monkeypatch):
    asked = []
    monkeypatch.setattr(main_window.write_queue, "flush", lambda *a, **k: False)
    monkeypatch.setattr(main_window_module.QMessageBox, "question",
                        lambda *a, **k: asked.append(a) or CLOSE_ANYWAY)  # the "Close anyway" button value
    assert main_window.close() is True
    assert len(asked) == 1

# tests/test_actions_handler.py, using the SimpleNamespace set-up of the existing run_analysis test
def test_a_run_waits_for_pending_writes(monkeypatch):
    events = []
    mw.write_queue = Mock(flush=Mock(side_effect=lambda **k: events.append(("flush", k)) or True))
    # fake Worker records ("worker",) in events
    handler.run_analysis()
    assert events == [("flush", {"timeout": 30}), ("worker",)]

def test_a_run_is_refused_while_writes_are_still_pending(monkeypatch):
    mw.write_queue = Mock(flush=Mock(return_value=False))
    toasts = []
    monkeypatch.setattr(actions_handler, "toast", lambda src, text, **k: toasts.append(text))
    handler.run_analysis()
    assert toasts == ["Your last changes are still being saved. Run the analysis again in a moment."]
    assert captured == {}  # no Worker built
```

Map the "Keep waiting" and "Close anyway" buttons to whichever `StandardButton` values the implementation uses,
and name them in the test.

- [ ] **Step 2: Run them; they fail**
- [ ] **Step 3: Implement the three flush points per design note §2.** In `run_analysis`, the flush comes after
  the double-run guard and before `_analysis_running = True`. Use `getattr(self.mw, "write_queue", None)`; no
  queue means no wait. `closeEvent` flushes before `threadpool.waitForDone`.
- [ ] **Step 4: Run them, `tests/test_actions_handler.py` and `tests/test_main_window*.py`; all pass**

### Task E4: `current_state.xlsx` is gone; opening falls back to `fulfillment_analysis.xlsx` (07-H2)

**Files:** `shopify_tool/core.py` (`_save_results_and_reports`: delete the xlsx write and fix its comment;
`current_state.pkl` stays as it is, because it is 07-M2's, in #370), `gui/main_window_pyside.py`
(`_load_session_analysis` and its docstring), `shopify_tool/stock_export.py` (`merge_session_stock_exports`),
`tests/test_save_session_queue.py`, `tests/test_stock_export.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/audit/test_07_core_io.py, unmarked (it has the sessions and analysis_run fixtures)
def test_a_run_writes_no_excel_mirror(sessions, analysis_run):
    path = sessions.create_session("M")
    ok, msg, _df, _stats = analysis_run(path)
    assert ok, msg
    assert not (Path(path) / "analysis" / "current_state.xlsx").exists()

def test_a_session_with_an_unreadable_pickle_opens_from_the_run_report(main_window):
    # a run's files: fulfillment_analysis.xlsx with 2 orders, analysis_data.json, a corrupt current_state.pkl,
    # and a stale current_state.xlsx holding 1 order
    main_window.load_existing_session(path)
    assert main_window.analysis_results_df["Order_Number"].tolist() == ["#1001", "#1002"]

def test_a_merge_reads_the_run_report_when_the_pickle_is_unreadable(tmp_path):
    # session/analysis/current_state.pkl corrupt; fulfillment_analysis.xlsx: #1 2 x A, Fulfillable
    out = stock_export.merge_session_stock_exports([session])
    assert out.loc[out["Артикул"] == "A", stock_export.QTY_COL].tolist() == [2]
```

For the edit path, add `assert not (Path(path) / "analysis" / "current_state.xlsx").exists()` to E2's
`test_an_edit_writes_only_the_pickle_before_returning`, after the flush.

- [ ] **Step 2: Run them; they fail**
- [ ] **Step 3: Implement per design note §3**
- [ ] **Step 4: Run them, `tests/test_stock_export.py tests/test_core.py`, and group C's tests under `--runxfail` (M2 still fails on `in_place == []`)**

### Task E5: undo records hold changed columns; the undo file goes through the queue (08-U2)

**Files:** `shopify_tool/undo_manager.py` (`RESTORED_COLUMNS: ClassVar[dict[str, tuple[str, ...]]]`,
`record_operation`, `_save_history`), `tests/audit/test_08_rules_undo.py` (remove the U2 marker),
`tests/test_undo_manager.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_an_edit_record_holds_only_the_order_and_changed_columns(tmp_path):
    mw = _window(FRAME, session_path=str(tmp_path))  # extend the module's _window(df) with session_path
    ActionsHandler(mw).bulk_change_status(["#1"], False)
    op = mw.undo_manager.operations[-1]
    assert set(op["affected_rows_before"][0]) == {"Order_Number", "Order_Fulfillment_Status"}

def test_a_removal_record_keeps_whole_rows(tmp_path):
    # remove_entire_order("#1"): the record's keys equal FRAME's columns

def test_a_whole_row_record_from_an_older_build_still_undoes(tmp_path):
    # write analysis/operations_history.json by hand: one toggle_status op whose affected_rows_before rows
    # carry every column (status "Fulfillable"), the frame now has "Not Fulfillable"; then:
    mw.undo_manager.reload_session_history()
    ok, _ = mw.undo_manager.undo()
    assert ok and mw.analysis_results_df["Order_Fulfillment_Status"].tolist() == ["Fulfillable"]

def test_the_undo_file_is_written_by_the_queue(tmp_path, qapp):
    mw = _window(FRAME, session_path=str(tmp_path))
    mw.write_queue = SessionWriteQueue()
    gate = gated(mw.write_queue)
    mw.undo_manager.record_operation("toggle_status", "t", {"order_number": "#1"}, FRAME.iloc[:1])
    assert not (tmp_path / "analysis" / "operations_history.json").exists()
    gate.set()
    mw.write_queue.flush(timeout=5)
    assert json.loads((tmp_path / "analysis" / "operations_history.json").read_text())["current_position"] == 1
```

- [ ] **Step 2: Run them and `test_AUDIT_08_U2_*` under `--runxfail`; they fail (U2 on the 2 MB ceiling)**
- [ ] **Step 3: Implement per design note §4.** `record_operation` keeps
  `["Order_Number", *RESTORED_COLUMNS[type]]` (only the columns present) for the types in the map, and whole rows
  for every other type. `_save_history` builds the dict snapshot (`list(self.operations)`, position, max) and
  calls `submit_or_run(getattr(self.main_window, "write_queue", None), session_path, UNDO_HISTORY, job)`.
- [ ] **Step 4: Run them; they pass. Remove the U2 marker. Run `tests/test_undo_manager.py tests/audit/test_08_rules_undo.py tests/test_actions_handler.py`**

### Task E6: inventory-memory saves make no backup (07-M5)

**Files:** `shopify_tool/profile_manager.py` (`save_shopify_config(self, client_id: str, config: dict, backup: bool = True) -> bool`,
`save_inventory_memory`), `tests/audit/test_07_core_io.py` (remove the M5 marker), `tests/test_profile_manager.py`

- [ ] **Step 1: Write the test**

```python
def test_a_settings_save_still_makes_a_backup(self, profile_manager):
    profile_manager.create_client_profile("M", "Client")
    cfg = profile_manager.load_shopify_config("M")
    profile_manager.save_shopify_config("M", cfg)
    backups = list((profile_manager.clients_dir / "CLIENT_M" / "backups").glob("shopify_config_*.json"))
    assert len(backups) == 1

def test_a_memory_save_makes_no_backup(self, profile_manager):
    profile_manager.create_client_profile("M", "Client")
    profile_manager.save_inventory_memory("M", {"A": 1}, session="S")
    assert list((profile_manager.clients_dir / "CLIENT_M" / "backups").glob("shopify_config_*.json")) == []
```

- [ ] **Step 2: Run them and `test_AUDIT_07_M5_*` under `--runxfail`; the second and M5 fail**
- [ ] **Step 3: Add the `backup` flag; `save_inventory_memory` passes `backup=False`. Docstrings say why (design note §5).**
- [ ] **Step 4: Run them; they pass. Remove the M5 marker. Run `tests/test_profile_manager.py`**

### Task E7: the run drops history rows of deleted session folders (07-L1)

**Files:** `shopify_tool/fulfillment_history.py` (`record_session(path, session, df, today=None,
existing_sessions: set[str] | None = None) -> bool`, new `session_folders`), `shopify_tool/core.py`
(`_save_results_and_reports` passes `existing_sessions=fulfillment_history.session_folders(Path(session_path).parent, current_session)`
when `session_path` is set), `tests/test_fulfillment_history.py`

**Interfaces:**
- Produces: `session_folders(sessions_dir: Path, current: str | None) -> set[str] | None`: the names of the
  subfolders from one `os.scandir`. It returns `None` on `OSError`, or when `current` is given and missing from
  the listing.

- [ ] **Step 1: Write the failing tests**

```python
def test_the_run_drops_rows_of_deleted_sessions(tmp_path):
    path = tmp_path / FILE_NAME
    _write(path, [("#1", "2026-01-01", "gone"), ("#2", "2026-01-01", "kept"), ("#3", "2026-01-01", "")])
    assert record_session(path, "now", SHIPS_4, existing_sessions={"kept", "now"})
    rows = load(path)
    assert set(zip(rows["Order_Number"], rows["Session"])) == {("#2", "kept"), ("#3", ""), ("#4", "now")}

def test_without_a_listing_nothing_is_pruned(tmp_path):
    # same file; existing_sessions=None keeps "gone"

def test_session_folders_refuses_a_listing_without_the_current_session(tmp_path):
    (tmp_path / "a").mkdir()
    assert session_folders(tmp_path, "a") == {"a"}
    assert session_folders(tmp_path, "b") is None
    assert session_folders(tmp_path / "missing", None) is None
```

`SHIPS_4` is a one-line frame that ships `#4`; `_write` writes the CSV with `COLUMNS`.

- [ ] **Step 2: Run them; they fail**
- [ ] **Step 3: Implement per design note §6. The prune happens in `_replace`'s caller, under the existing lock.
  Leave `_write_atomic` untouched.**
- [ ] **Step 4: Run them, `tests/test_fulfillment_history.py tests/audit/test_02_repeat_orders.py`, and group C's
  M4 tests under `--runxfail` (each still fails on its own assertion)**

### Group E checkpoint

- [ ] Run the full gate. Expected: 7 xfailed, ruff clean. Group C's tests still fail on their own assertions under `--runxfail`.
- [ ] Run `graphify update .`.
- [ ] Commit, starting the message with `E: an edit writes only the pickle; derived files go through a background queue`.
  The body lists AUDIT-07-H2, AUDIT-08-U2, AUDIT-07-M5 and AUDIT-07-L1, the tests unmarked, and the H2 test's edit.
- [ ] Push. Tick E.

---

## Group G: low items (07-L2–L6; 08-R5, U4, U5, T1; 09-O6, O7, O8)

**Risk: low.** 07-L3 deletes dead code: `grep -rn "_calculate_final_stock" --include=*.py .` found only the
definition (`shopify_tool/analysis.py:843`) and a comment (`:640`). There is no caller in the code or the tests.

**PR warning text:** "G: `session_info.analysis_report_path` now names `analysis/fulfillment_analysis.xlsx`, the
file the run writes; Packing Tool's use of it is unconfirmed. Undo history is per PC
(`operations_history_<PC>.json`): a session reopened on another PC no longer offers the first PC's undo steps,
and an older shared file is read once as a fallback. A same-minute stock re-export no longer overwrites the copy
already in `old/`. `setup_venv.sh` refuses a Python older than 3.12."

Each task: write the test, see it fail, fix, see it pass. Group G commits once, at its checkpoint.

### Task G1: 07-L2, `analysis_report_path` names the file written

- [ ] `core._save_results_and_reports`: `"analysis_report_path": "analysis/fulfillment_analysis.xlsx"`.
- [ ] Test in `tests/audit/test_07_core_io.py`, unmarked:

```python
def test_the_session_names_the_report_it_wrote(sessions, analysis_run):
    path = sessions.create_session("M")
    assert analysis_run(path)[0]
    info = json.loads((Path(path) / "session_info.json").read_text(encoding="utf-8"))
    assert (Path(path) / info["analysis_report_path"]).exists()
```

### Task G2: 07-L3, delete `analysis._calculate_final_stock`

- [ ] Re-run the grep above, then delete the function. Reword the comment at `analysis.py:640` so it no longer
  names it. No test: there is no behaviour. Ruff and the full suite are the check.

### Task G3: 07-L4, `_exclusive_lock` releases only a lock it took

- [ ] `SessionManager._exclusive_lock`: set `locked = True` after the lock call succeeds, and unlock in `finally`
  only `if locked`.
- [ ] Test in `tests/test_session_manager.py`:

```python
def test_a_lock_that_was_never_taken_is_not_released(session_manager, tmp_path, monkeypatch):
    import fcntl
    calls = []
    def flock(fd, op):
        calls.append(op)
        if op == fcntl.LOCK_EX:
            raise OSError("lock refused")
    monkeypatch.setattr(fcntl, "flock", flock)
    with pytest.raises(OSError, match="lock refused"):
        with session_manager._exclusive_lock(tmp_path / "x.lock"):
            pass
    assert calls == [fcntl.LOCK_EX]
```

### Task G4: 07-L5, the "Cannot fulfill" notes without `apply(axis=1)`

- [ ] Extract `analysis._with_fulfillment_reasons(notes: pd.Series, order_numbers: pd.Series,
  fulfillment_results: dict) -> pd.Series`. It is vectorised: a `{order: reason}` dict for orders whose result
  is a dict with `fulfillable` False, then `map`, then `where`. `_merge_results_to_dataframe` calls it.
- [ ] Test in `tests/test_analysis.py`:

```python
def test_fulfillment_reasons_join_the_existing_note():
    results = {"#1": {"fulfillable": False, "reason": "A short"}, "#2": {"fulfillable": True},
               "#3": {"fulfillable": False}, "#4": "Fulfillable"}
    notes = pd.Series(["Repeat", "", float("nan"), "x", "y"])
    orders = pd.Series(["#1", "#2", "#3", "#4", "#5"])
    assert _with_fulfillment_reasons(notes, orders, results).tolist() == [
        "Repeat; Cannot fulfill: A short", "", "Cannot fulfill: Unknown reason", "x", "y"]
```

### Task G5: 07-L6, two backups in the same second both survive

- [ ] `ProfileManager._create_backup`: the name stamp becomes `%Y%m%d_%H%M%S_%f`. If that path exists, append
  `_1`, `_2`, ... before `.json`. Sorting stays oldest-first: `.` sorts before `_`.
- [ ] Test in `tests/test_profile_manager.py`: freeze `profile_manager_module.datetime` at one instant
  (microseconds included), save the Settings config twice, and assert `len(backups) == 2`.

### Task G6: 08-R5, a rule-added product is not a set component

- [ ] `_execute_actions`, `ADD_PRODUCT`: on each new row, when the columns exist, set `Original_SKU = sku`,
  `Original_Quantity = quantity` and `Is_Set_Component = False`.
- [ ] Test in `tests/test_rules.py`:

```python
def test_a_product_added_from_a_set_line_is_not_a_component():
    df = pd.DataFrame({"Order_Number": ["#1"], "SKU": ["A"], "Quantity": [2], "Original_SKU": ["SET-1"],
                       "Original_Quantity": [1], "Is_Set_Component": [True]})
    rule = {"name": "gift", "level": "article", "conditions": [{"field": "SKU", "operator": "equals", "value": "A"}],
            "actions": [{"type": "ADD_PRODUCT", "sku": "GIFT", "quantity": 1}]}
    added = RuleEngine([rule]).apply(df).iloc[-1]
    assert (added["Original_SKU"], added["Original_Quantity"], added["Is_Set_Component"]) == ("GIFT", 1, False)
```

### Task G7: 08-U4, undo history per PC

- [ ] `UndoManager._get_history_path()` returns `analysis/operations_history_{_pc_name()}.json`. The new
  module-level `_pc_name() -> str` is `os.environ.get("COMPUTERNAME") or platform.node() or "unknown"`, with every
  character outside `[A-Za-z0-9_-]` replaced by `_`. `_load_history` reads the legacy
  `analysis/operations_history.json` only when the per-PC file is missing, and never writes the legacy file.
- [ ] In `tests/audit/test_08_rules_undo.py`, `test_a_rerun_empties_the_saved_undo_history` and the U2 test read
  `mw.undo_manager._get_history_path()` instead of the literal path. So does E5's
  `test_the_undo_file_is_written_by_the_queue`.
- [ ] Tests in `tests/test_undo_manager.py`:

```python
def test_two_pcs_keep_their_own_undo_history(tmp_path, monkeypatch):
    monkeypatch.setenv("COMPUTERNAME", "PC-A")
    a = _window(FRAME, session_path=str(tmp_path))
    a.undo_manager.record_operation("toggle_status", "by A", {"order_number": "#1"}, FRAME.iloc[:1])
    monkeypatch.setenv("COMPUTERNAME", "PC-B")
    b = _window(FRAME, session_path=str(tmp_path))
    b.undo_manager.record_operation("toggle_status", "by B", {"order_number": "#1"}, FRAME.iloc[:1])
    monkeypatch.setenv("COMPUTERNAME", "PC-A")
    a.undo_manager.reload_session_history()
    assert [op["description"] for op in a.undo_manager.operations] == ["by A"]

def test_a_legacy_shared_history_still_loads(tmp_path, monkeypatch):
    # write analysis/operations_history.json holding one op; a fresh UndoManager on PC-A loads it
    assert [op["description"] for op in mw.undo_manager.operations] == ["legacy"]
```

### Task G8: 08-U5, the "Cleared N future operations" count

- [ ] `record_operation`: compute `cleared = len(self.operations) - self.current_position` before slicing, and log
  `f"Cleared {cleared} future operations"`.
- [ ] Test in `tests/test_undo_manager.py`: record 3, undo 2, record 1; `caplog` holds
  `"Cleared 2 future operations"`.

### Task G9: 08-T1, `setup_venv.sh` refuses a Python older than 3.12

- [ ] In the candidate loop, before the venv probe:
  `"$p" -c 'import sys; sys.exit(sys.version_info < (3, 12))' || continue`. Read the candidates from
  `${SETUP_VENV_PYTHONS:-/usr/bin/python3 python3 python3.14 python3.13 python3.12}`, which gives the test a seam.
  The error lines say "No Python 3.12 or newer on this machine can create a venv with pip." and list the
  candidates tried. 3.12 is the floor because audit 08 confirmed that `numpy>=2.5.3` needs Python 3.12 or newer.
- [ ] Test in the new `tests/test_setup_venv.py`:

```python
def test_a_python_older_than_3_12_is_refused(tmp_path):
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    shutil.copy(REPO / "scripts" / "setup_venv.sh", repo / "scripts")
    old = tmp_path / "python3"
    old.write_text("#!/bin/sh\n[ \"$1\" = -c ] && exit 1\nexit 0\n")
    old.chmod(0o755)
    run = subprocess.run(["bash", str(repo / "scripts" / "setup_venv.sh")], capture_output=True, text=True,
                         env={**os.environ, "SETUP_VENV_PYTHONS": str(old)}, cwd=repo)
    assert run.returncode == 1
    assert "3.12" in run.stderr
    assert not (repo / ".venv").exists()
```

### Task G10: 09-O6, write-off dedupes stripped order numbers

- [ ] `sku_writeoff.calculate_writeoff_quantities`: `order_col = rows_df["Order_Number"].astype(str).str.strip()`.
- [ ] Test in `tests/test_sku_writeoff.py`. Use the module's existing tag-category fixture shape, with a tag
  `BOX` that writes off 1 × `PKG`. Rows `"1001"` and `"1001 "`, both Fulfillable and both tagged `BOX`, give a
  total `PKG` write-off of 1.

### Task G11: 09-O7, the non-lot stock export groups stripped SKUs

- [ ] `stock_export.create_stock_export`, the non-lot branch: group by
  `filtered_items["SKU"].astype(str).str.strip()`, the same key `_check_totals` uses.
- [ ] Test in `tests/test_stock_export.py`: Fulfillable lines `A` × 1 and `A ` × 2, captured through
  `_write_xls`, give one row `A` with `Брой` 3.

### Task G12: 09-O8, a same-minute re-export keeps both archived copies

- [ ] `prepare_export_path`: when a file being moved to `old/` would land on an existing name, add `_2`, `_3`,
  ... before `.xls`. The stamp format stays as it is: the ERP sees the same names.
- [ ] Test in `tests/test_stock_export_names.py`: with a fixed `now`, three rounds of `prepare_export_path(base,
  now)` followed by writing the returned path with a distinct content. Afterwards `old/` holds 2 files with the
  first two contents, and the folder holds the third.

### Group G checkpoint

- [ ] Run the full gate. Expected: 7 xfailed (group C only), ruff clean.
- [ ] Run `graphify update .`.
- [ ] Commit, starting the message with `G: low items`. The body lists AUDIT-07-L2, L3, L4, L5, L6, AUDIT-08-R5,
  U4, U5, T1, AUDIT-09-O6, O7, O8.
- [ ] Push. Tick G, then mark the PR ready for review.

---

## Coverage (Step 4 of the overview plan)

Each group adds tests for what it touches. The tasks above name them. The closing coverage PR (90% for
`undo_manager.py`, `rules.py` and `sku_writeoff.py`; 80% for the backend list in the overview plan) is **not**
part of this plan. Before closing each checkpoint, run the coverage command from the overview plan on the
group's modules, and note the before and after numbers in the commit body:
`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q --cov=shopify_tool --cov=shared --cov-report=term-missing`.
