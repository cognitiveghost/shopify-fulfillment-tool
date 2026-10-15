# Coverage floor, production replay suite and snapshot fixes: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the snapshot bugs 2.1 (Shopify side), 2.2, 2.3 and 2.5. Give the app one public analysis entry point, and pin it with 26 anonymised production replays. Silence the three warnings production still logs. Lift every listed module to 80% coverage, logging each bug found.

**Architecture:** Parts run in order C → B → L → A on one branch, ending in one PR. Every bug is an `AUDIT-10-k`: a strict-xfail test lands first, and the fix lands next and removes the marker. Bugs are logged in `docs/audit/10-coverage-and-snapshot.md`. The replay suite calls `core.analyse`, the same function `run_full_analysis` calls. Its fixtures are produced by a committed builder script that reads the raw snapshot and writes only anonymised files.

**Tech Stack:** Python 3.14, PySide6, pandas, pytest + pytest-qt + pytest-cov, ruff.

**Spec:** `docs/superpowers/specs/2026-10-15-coverage-replay-snapshot-fixes-design.md`. Read it first: every task argues from it.

## Global Constraints

- Gate: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` and `ruff check .`. Three known failures in `tests/test_label_printing.py::TestImageToZpl` also fail on main. Leave them alone.
- Run a single test as `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q <path>::<name>`. A hook refuses other spellings of "pytest" in Bash. Write test files with Write/Edit, never with heredocs.
- A full run takes about 9 minutes, so run it in the background.
- Git: `/usr/bin/git`, one plain command per Bash call, never chained with `&&` or `;`. Commit with `/usr/bin/git commit -F <absolute path to a message file>`, with the message file in your job's tmp dir. End every message with the `Co-Authored-By` line your session gives you.
- The repo is PR-only: never commit to `main`. Work on `dr/29-chores-coverage-test`.
- No hardcoded colours in Qt stylesheets (theme variables only). No new dependency. No `pyproject.toml`.
- `~/Desktop/Server./Server/` is raw production data with customer PII: **read-only, never committed, never quoted** in code, commits, the PR or the bug log. The only path from it into git is `scripts/build_replay_fixtures.py`, and that writes anonymised files only.
- User-facing text and code say "out of date" or "withdrawn" for packing lists, never "stale". **Stale** is the glossary's word (CONTEXT.md) for a PC's old copy of the session state.
- Bug IDs: `AUDIT-10-1` … in the order logged. The plan reserves 1–7. Bugs the coverage tests find take 8 and up.
- A `shared/` change reaches packing-tool at its next sync. Say so in the PR.
- After code changes, run `graphify update .` before the last commit (CLAUDE.md).

## Review Focus

1. **The old list stays visible when moving its JSON fails** (another PC or the Packer holds the file open). Expected: the XLSX is still moved, a warning is logged, the name is not reported as withdrawn, and nothing crashes. Test in Task 4 (`test_a_locked_json_is_not_reported_withdrawn`).
2. **An analysis re-run inside an open session that already has lists.** Expected: lists are withdrawn exactly as after an edit. Test in Task 5 (`test_a_rerun_analysis_withdraws_out_of_date_lists`).
3. **Report file names with odd suffixes** (`ALL`, `ALL.v2`, `MASKS.XLSX`, `X.xlsx` for a stock export). Expected: always exactly one correct lower-case extension. Test in Task 1 (parametrised).
4. **A session written before this change** (no `packing_list_orders`, no fingerprints). Expected: lifecycle behaves as today, and no edit withdraws anything. Tests in Task 3 (`test_no_recorded_count_trusts_the_status`) and Task 5 (`test_a_session_without_fingerprints_withdraws_nothing`).
5. **An order number without digits, or with a `#` prefix, in fixtures.** Expected: the mapping is consistent across orders, history and packed signals, so a Repeat still matches. Test in Task 8 (`test_order_map_*`).

---

## File map

| File | Change |
|---|---|
| `shopify_tool/report_jobs.py` | `_output_file` suffix fix; `packing_fingerprint`, `withdraw_lists`, `out_of_date_message`, `recorded_fingerprints`; `ReportOutcome.fingerprint`; `update_packing_list_statistics` (public, records order counts + fingerprints); withdraw on failed regeneration |
| `shopify_tool/session_lifecycle.py` | `packing_completion` checks the recorded order count |
| `shopify_tool/profile_manager.py` | `update_shopify_config(..., backup=True)` |
| `gui/report_selection_dialog.py` | `GenerateReportsDialog(..., writeoff_mode="off")` |
| `gui/actions_handler.py` | passes and stores `last_writeoff_mode`; records fingerprints; withdraws after a re-run |
| `gui/main_window_pyside.py` | `_list_fingerprints`; `_withdraw_out_of_date_lists()` called from `save_session_state` |
| `gui/session_write_queue.py` | `PACKING_LISTS` kind |
| `shopify_tool/core.py` | `AnalysisResult`, `analyse`, `read_orders_csv`, `today`/`now` threading, `input/shopify_config.json`; dead report functions removed |
| `shopify_tool/analysis.py` | `today` parameter through `run_analysis` → `_merge_results_to_dataframe` → `_detect_repeated_orders`; `"0"` expiry |
| `shopify_tool/packed_orders.py` | `signals_from_entries` |
| `tests/replay/anonymise.py`, `replay.py`, `test_anonymise.py`, `test_replay.py`, `fixtures/` | replay suite |
| `scripts/build_replay_fixtures.py` | fixture builder (IO only) |
| `shopify_tool/templates/{barcode,qr}_label/style.css` | `overflow-wrap: anywhere` |
| `shared/web_page.py` | paint timeout logged at INFO |
| `docs/audit/10-coverage-and-snapshot.md` | the bug log |
| `tests/audit/test_10_coverage_snapshot.py` | AUDIT-10 tests |
| `docs/adr/0019-withdrawn-packing-lists.md`, `CONTEXT.md` | contract + glossary |
| `.github/workflows/build_release.yml` | coverage gate |

---

## Before you start

- [ ] Run `./scripts/setup_venv.sh` (it links `.venv`). Then run the gate once in the background, to confirm the baseline: 3,774 passed, 3 failed (ZPL), 7 xfailed.
- [ ] Create `docs/audit/10-coverage-and-snapshot.md` with this skeleton. Each task appends its section.

```markdown
# Audit 10: coverage floor and production snapshot findings

Started 2026-10-15 from `~/Desktop/Server./findings.md` (snapshot of 2026-10-11, sections 2 and 5), the
production `log_issues` of the 2.3.1 build, and the coverage pass of part A. Tests:
`tests/audit/test_10_coverage_snapshot.py` unless named otherwise. Each AUDIT-10-k test was committed
as a strict xfail before its fix.

## Already fixed: 2.4 config backups used up by inventory-memory saves

`save_inventory_memory` saves with `backup=False` since AUDIT-07-M5 (PR #371, released in 2.2.1), pinned
by `tests/test_profile_manager.py` ("Settings saves keep a backup; inventory-memory saves don't"). The
snapshot shows no backup from LIDA's 2026-10-09 analysis on 2.3.1. No new id.

## Coverage

| Module | Before | After |
|---|---|---|
| `shopify_tool/core.py` | 68.3 | |
| `shopify_tool/undo_manager.py` | 59.8 | |
| `shopify_tool/groups_manager.py` | 57.3 | |
| `shopify_tool/sku_writeoff.py` | 53.6 | |
| `shopify_tool/tag_manager.py` | 68.3 | |
| `shopify_tool/profile_migrations.py` | 65.2 | |
| `shopify_tool/profile_manager.py` | 75.0 | |
| `gui/client_settings_dialog.py` | 11.1 | |
| `gui/groups_management_dialog.py` | 9.6 | |
| `shared/file_lock.py` | 57.4 | |
| `shared/server_connection.py` | 24.4 | |
| `shared/metadata_utils.py` | 33.3 | |
| **Total** (`shopify_tool`, `gui`, `shared`) | 84.5 | |

## Findings
```

- [ ] Create `tests/audit/test_10_coverage_snapshot.py` with this header. Tests are added by the tasks.

```python
"""Audit 10: production snapshot findings and bugs found by the coverage pass.

Report: docs/audit/10-coverage-and-snapshot.md. Every AUDIT-10-k test was committed failing, as
xfail(strict=True), before its fix removed the marker. Fixtures are synthetic; the production replay
lives in tests/replay/.
"""
```

- [ ] Commit both ("Audit 10: bug log and test module").

---

## Part C: snapshot findings

### Task 1: AUDIT-10-1, `.XLSX` report name fails the packing list (finding 2.5)

**Files:**
- Modify: `shopify_tool/report_jobs.py:59-70` (`_output_file`)
- Test: `tests/audit/test_10_coverage_snapshot.py`

**Interfaces:** Produces `report_jobs._output_file(report_type, report_name, report_config, output_dir) -> str`. The signature is unchanged; it always ends in `.xlsx` (packing lists) or `.xls` (stock exports).

- [ ] **Step 1: Write the failing test** (append to the audit file)

```python
from pathlib import Path

import pandas as pd
import pytest

from shopify_tool import report_jobs


@pytest.mark.xfail(strict=True, reason="AUDIT-10-1: .XLSX is not normalised")
@pytest.mark.parametrize(
    ("report_type", "filename", "expected"),
    [
        ("packing_lists", "MASKS.XLSX", "MASKS.xlsx"),
        ("packing_lists", "ALL", "ALL.xlsx"),
        ("packing_lists", "ALL.xls", "ALL.xlsx"),
        ("packing_lists", "ALL.v2", "ALL.v2.xlsx"),
        ("stock_exports", "ERP.XLS", "ERP.xls"),
        ("stock_exports", "ERP.xlsx", "ERP.xls"),
        ("stock_exports", "ERP", "ERP.xls"),
    ],
)
def test_audit_10_1_report_names_get_one_lower_case_extension(report_type, filename, expected, tmp_path):
    out = report_jobs._output_file(report_type, "X", {"output_filename": filename}, tmp_path)
    assert Path(out).name == expected


@pytest.mark.xfail(strict=True, reason="AUDIT-10-1: .XLSX fails in pd.ExcelWriter")
def test_audit_10_1_an_upper_case_name_still_writes_the_packing_list(tmp_path):
    frame = pd.DataFrame(
        {"Order_Number": ["#1001"], "SKU": ["A"], "Quantity": [1], "Stock": [5],
         "Order_Fulfillment_Status": ["Fulfillable"], "Shipping_Provider": ["DHL"],
         "Destination_Country": ["BG"], "Warehouse_Name": ["W-A"], "Product_Name": ["PA"],
         "Internal_Tags": ["[]"]}
    )
    config = {"name": "MASKS", "report_type": "packing_lists", "output_filename": "MASKS.XLSX", "filters": []}
    outcome = report_jobs.generate_report(config, tmp_path, frame, {}, "s")
    assert not outcome.failed
    assert (tmp_path / "packing_lists" / "MASKS.xlsx").exists()
    assert (tmp_path / "packing_lists" / "MASKS.json").exists()
```

- [ ] **Step 2: Run them.** Expected: all `XFAIL`, with no `XPASS`. (Some of the parametrised cases already pass on main: `ALL.xls` → `ALL.xlsx` and `ERP` → `ERP.xls`. Strict mode makes those XPASS fail. Move each one that passes into a separate, unmarked test, `test_report_names_already_normalised`, and keep only the failing cases under the xfail.)
- [ ] **Step 3: Commit the tests** ("AUDIT-10-1: failing test for upper-case report extension").
- [ ] **Step 4: Fix.** Replace the extension block of `_output_file`:

```python
def _output_file(report_type: str, report_name: str, report_config: dict, output_dir: Path) -> str:
    suffix = ".xlsx" if report_type == "packing_lists" else ".xls"
    base_filename = report_config.get("output_filename", "") or f"{report_name}{suffix}"
    # Case-insensitive (AUDIT-10-1): "MASKS.XLSX" passed through and pandas
    # refused the upper-case extension.
    path = Path(base_filename)
    if path.suffix.lower() in (".xls", ".xlsx"):
        path = path.with_suffix(suffix)
    else:
        path = Path(base_filename + suffix)
    return str(output_dir / path)
```

- [ ] **Step 5:** Remove the two xfail markers. Run the tests (PASS), then `tests/test_report_jobs.py` (PASS).
- [ ] **Step 6:** Append the finding to the bug log:

```markdown
### AUDIT-10-1: a report file name ending `.XLSX` fails the packing list (finding 2.5)

Found: snapshot finding 2.5, ALMA 2026-10-08 15:15 ("Invalid extension for engine … 'XLSX'").
`_output_file` compared the extension case-sensitively, so `MASKS.XLSX` reached `pd.ExcelWriter`,
which refuses it; a name with no extension (`ALL`) got none, and a stock export named `X.xlsx`
became `X.xlsx.xls`. Fix: one lower-case extension from `Path.with_suffix`.
Test: `test_audit_10_1_*`.
```

- [ ] **Step 7: Commit** ("AUDIT-10-1: normalise report file extensions").

### Task 2: AUDIT-10-2, write-off mode defaults to off every time (finding 2.3)

**Files:**
- Modify: `shopify_tool/profile_manager.py:708-735` (`update_shopify_config`)
- Modify: `gui/report_selection_dialog.py:214-227, 274` (`GenerateReportsDialog.__init__`, `_add_extra_sections`)
- Modify: `gui/actions_handler.py:617-631` (dialog creation), `:633-655` (`_generate_reports`)
- Test: `tests/audit/test_10_coverage_snapshot.py`

**Interfaces:**
- Produces: `ProfileManager.update_shopify_config(client_id, apply, backup: bool = True) -> dict`.
- Produces: `GenerateReportsDialog(packing_configs, stock_configs, analysis_df, apply_filters_fn, parent=None, writeoff_mode="off")`.
- Produces: config key `last_writeoff_mode` in `shopify_config.json`, one of `"off" | "merged" | "separate"`.

- [ ] **Step 1: Write the failing tests**

```python
from gui.report_selection_dialog import GenerateReportsDialog

PACKING = [{"name": "ALL", "filters": []}]
STOCK = [{"name": "ERP", "filters": []}]
ONE_ORDER = pd.DataFrame(
    {"Order_Number": ["#1001"], "SKU": ["A"], "Quantity": [1], "Order_Fulfillment_Status": ["Fulfillable"]}
)


@pytest.mark.xfail(strict=True, reason="AUDIT-10-2: the dialog cannot preselect a mode")
@pytest.mark.parametrize("mode", ["off", "merged", "separate"])
def test_audit_10_2_the_dialog_preselects_the_given_mode(qapp, mode):
    dialog = GenerateReportsDialog(PACKING, STOCK, ONE_ORDER, lambda df, f: df, writeoff_mode=mode)
    checked = {"off": dialog.writeoff_off, "merged": dialog.writeoff_merged,
               "separate": dialog.writeoff_separate}
    assert checked[mode].isChecked()


@pytest.mark.xfail(strict=True, reason="AUDIT-10-2: the choice is not stored")
def test_audit_10_2_generating_stores_the_mode_without_a_backup(main_window, monkeypatch):
    from shopify_tool import report_jobs as jobs
    path = _open_with_state(main_window, ONE_ORDER.assign(Stock=5))
    monkeypatch.setattr(jobs, "generate_reports", lambda *a, **k: [])
    backups = Path(main_window.profile_manager.get_client_directory("acme")) / "backups"
    before = set(backups.glob("*")) if backups.exists() else set()

    main_window.actions_handler._generate_reports(
        [{"name": "ERP", "report_type": "stock_exports", "writeoff_mode": "merged"}], path
    )

    saved = main_window.profile_manager.load_shopify_config("acme")
    assert saved["last_writeoff_mode"] == "merged"
    assert main_window.active_profile_config["last_writeoff_mode"] == "merged"
    after = set(backups.glob("*")) if backups.exists() else set()
    assert after == before
```

Import the fixtures at the top of the audit file:
`from test_stale_session import _open_with_state, main_window  # noqa: F401  main_window is a fixture`.
Take `qapp` from `tests/conftest.py`. Check that `ProfileManager.get_client_directory` exists (it is used by `fulfillment_history.history_path`). Let the worker run synchronously, or flush the threadpool with `main_window.threadpool.waitForDone(5000)` before asserting, if needed.

- [ ] **Step 2:** Run them. Expected: XFAIL. **Step 3:** Commit the tests.
- [ ] **Step 4: Fix `update_shopify_config`.** Add `backup: bool = True` to its signature, document it ("False for a value that is not a Settings change, such as the write-off choice; see AUDIT-07-M5"), and call `self.save_shopify_config(client_id, config, backup=backup)`.
- [ ] **Step 5: Fix the dialog.** In `GenerateReportsDialog.__init__`, add the keyword `writeoff_mode: str = "off"`, and set `self._writeoff_mode = writeoff_mode` **before** `super().__init__(...)`, because `_add_extra_sections` runs inside it. In `_add_extra_sections`, replace `self.writeoff_off.setChecked(True)` with:

```python
        # The client's last choice (AUDIT-10-2): it used to reset to "off" every time.
        {"merged": self.writeoff_merged, "separate": self.writeoff_separate}.get(
            self._writeoff_mode, self.writeoff_off
        ).setChecked(True)
```

- [ ] **Step 6: Fix the handler.** In `open_generate_reports_dialog`, pass `writeoff_mode=fresh_config.get("last_writeoff_mode", "off")` to `GenerateReportsDialog`. In `_generate_reports`, right after `batch = [dict(report_config) for report_config in batch]`, call `self._remember_writeoff_mode(batch)`, and add:

```python
    def _remember_writeoff_mode(self, batch) -> None:
        """Keep the client's packaging write-off choice for the next dialog (AUDIT-10-2).

        Saved without a backup: it is not a Settings change, and backups are kept for those.
        """
        modes = {c.get("writeoff_mode") for c in batch if c.get("report_type") == "stock_exports"}
        modes.discard(None)
        client_id = self.mw.current_client_id
        if len(modes) != 1 or not client_id:
            return
        (mode,) = modes
        if (self.mw.active_profile_config or {}).get("last_writeoff_mode", "off") == mode:
            return
        try:
            self.mw.active_profile_config = self.mw.profile_manager.update_shopify_config(
                client_id, lambda config: config.update(last_writeoff_mode=mode), backup=False
            )
        except Exception:
            self.log.exception("Could not save the packaging write-off choice")
```

- [ ] **Step 7:** Remove the markers. Run the new tests, `tests/test_generate_reports_dialog.py`, `tests/test_profile_manager.py` and `tests/test_actions_handler.py`. All PASS.
- [ ] **Step 8:** Add the bug-log section (title, "Found: snapshot finding 2.3, LIDA exports from 2026-10-05 without packaging rows", cause, fix, tests). Then commit ("AUDIT-10-2: remember the write-off mode per client").

### Task 3: AUDIT-10-3, a list ended with orders unpacked counts as packed (finding 2.1, Shopify side)

**Files:**
- Modify: `shopify_tool/report_jobs.py:188-220` (`generate_reports`, `_update_packing_list_statistics` → `update_packing_list_statistics`)
- Modify: `shopify_tool/session_lifecycle.py:30-60` (`packing_completion`)
- Test: `tests/test_session_lifecycle.py`, `tests/audit/test_10_coverage_snapshot.py`

**Interfaces:**
- Produces: `report_jobs.update_packing_list_statistics(session_manager, session_path, outcomes=()) -> None`. It writes `statistics.packing_lists` (sorted JSON stems), `packing_lists_count`, `packing_list_orders: {stem: int}` and `packing_list_fingerprints: {stem: str}` (filled from Task 4 on).
- Consumes: `session_info.statistics.packing_list_orders`.

- [ ] **Step 1: Write the failing tests.** Add them to `tests/test_session_lifecycle.py`, which already has the `_entry` helper. Mark them xfail AUDIT-10-3:

```python
def _counted(entry, counts):
    entry["statistics"]["packing_list_orders"] = counts
    return entry


@pytest.mark.xfail(strict=True, reason="AUDIT-10-3: a short run counts as packed")
def test_a_completed_run_short_of_its_list_is_not_packed():
    progress = {"ALL": {"status": "completed", "completed_orders": [f"#{i}" for i in range(38)]}}
    entry = _counted(_entry(lists=["ALL"], progress=progress), {"ALL": 40})
    assert packing_completion(entry) == (0, 1)
    assert not is_fully_packed(entry)


def test_a_completed_run_with_every_order_is_packed():
    progress = {"ALL": {"status": "completed", "completed_orders": [f"#{i}" for i in range(40)]}}
    entry = _counted(_entry(lists=["ALL"], progress=progress), {"ALL": 40})
    assert packing_completion(entry) == (1, 1)


def test_no_recorded_count_trusts_the_status():
    progress = {"ALL": {"status": "completed", "completed_orders": ["#1"]}}
    assert packing_completion(_entry(lists=["ALL"], progress=progress)) == (1, 1)


@pytest.mark.xfail(strict=True, reason="AUDIT-10-3: a short full-session run counts as packed")
def test_a_short_full_session_run_is_not_packed():
    progress = {"full_session": {"status": "completed", "completed_orders": ["#1", "#2"]}}
    entry = _counted(_entry(lists=["A", "B"], progress=progress), {"A": 2, "B": 1})
    assert packing_completion(entry) == (0, 2)


def test_duplicate_order_numbers_count_once():
    progress = {"ALL": {"status": "completed", "completed_orders": ["#1", "#1"]}}
    entry = _counted(_entry(lists=["ALL"], progress=progress), {"ALL": 2})
    assert packing_completion(entry) == (0, 1)
```

The last test passes after the fix only. Mark it xfail too if it does not fail today; check this in step 2. And in `tests/test_report_jobs.py`:

```python
def test_statistics_record_each_lists_order_count(tmp_path):
    from types import SimpleNamespace
    lists = tmp_path / "packing_lists"
    lists.mkdir()
    (lists / "ALL.json").write_text(json.dumps({"total_orders": 40}), encoding="utf-8")
    (lists / "BROKEN.json").write_text("{", encoding="utf-8")
    info = {"statistics": {}}
    sm = SimpleNamespace(get_session_info=lambda p: info,
                         update_session_info=lambda p, u: info.update(u) or True)
    report_jobs.update_packing_list_statistics(sm, tmp_path)
    assert info["statistics"]["packing_lists"] == ["ALL", "BROKEN"]
    assert info["statistics"]["packing_list_orders"] == {"ALL": 40}
```

- [ ] **Step 2:** Run them. Expected: the xfails XFAIL, and the statistics test FAILs (the name is still private). **Step 3:** Commit the lifecycle tests. Keep the statistics test in the fix commit.
- [ ] **Step 4: Fix the statistics.** Rename `_update_packing_list_statistics` to `update_packing_list_statistics(session_manager, session_path, outcomes=())`. It has one caller, in `generate_reports`. Give it this body:

```python
def update_packing_list_statistics(session_manager, session_path, outcomes=()) -> None:
    """Record the session's packing lists in session_info's statistics.

    Rebuilt from the JSON files in packing_lists/, so a withdrawn or removed list drops out:
    names, each list's order count (AUDIT-10-3) and the fingerprint it was written from
    (AUDIT-10-4). Never raises.
    """
    try:
        packing_lists_dir = Path(session_path) / "packing_lists"
        if not packing_lists_dir.exists():
            return
        names = sorted(f.stem for f in packing_lists_dir.glob("*.json"))
        session_info = session_manager.get_session_info(str(session_path))
        if not session_info:
            return
        statistics = session_info.get("statistics", {})
        orders = {}
        for name in names:
            try:
                total = json.loads((packing_lists_dir / f"{name}.json").read_text(encoding="utf-8")).get("total_orders")
            except (OSError, ValueError, AttributeError):
                continue
            if isinstance(total, int) and not isinstance(total, bool):
                orders[name] = total
        fingerprints = dict(statistics.get("packing_list_fingerprints") or {})
        for outcome in outcomes:
            if outcome.report_type == "packing_lists" and outcome.fingerprint and outcome.output_file:
                fingerprints[Path(outcome.output_file).stem] = outcome.fingerprint
        statistics["packing_lists_count"] = len(names)
        statistics["packing_lists"] = names
        statistics["packing_list_orders"] = orders
        statistics["packing_list_fingerprints"] = {n: fingerprints[n] for n in names if n in fingerprints}
        session_manager.update_session_info(str(session_path), {"statistics": statistics})
        logger.info(f"Updated session statistics: {len(names)} packing lists")
    except Exception as e:
        # Don't fail the report if statistics update fails
        logger.warning(f"Failed to update session statistics: {e}")
```

`outcome.fingerprint` arrives in Task 4. In this task, add the field `fingerprint: str | None = None` to `ReportOutcome` now, so the code above runs. In `generate_reports`, call `update_packing_list_statistics(session_manager, session_path, outcomes)` when `session_manager is not None and any(o.report_type == "packing_lists" for o in outcomes)`. Every packing-list outcome counts, failed ones included: a failed regeneration withdraws the old list (Task 4), and the statistics must follow.

- [ ] **Step 5: Fix `packing_completion`.** Inside it, after `progress` is resolved:

```python
    counts = stats.get("packing_list_orders") if isinstance(stats, dict) else None
    if not isinstance(counts, dict):
        counts = {}

    def _done(key: str, expected: int | None = None) -> bool:
        block = progress.get(key)
        # Only "completed" counts; "in_progress" and "paused" do not.
        if not (isinstance(block, dict) and block.get("status") == "completed"):
            return False
        if expected is None:
            return True  # written before order counts were recorded
        # The Packer writes "completed" for a run ended with orders unpacked (AUDIT-10-3).
        orders = block.get("completed_orders")
        packed = {o for o in orders if isinstance(o, str)} if isinstance(orders, list) else set()
        return len(packed) >= expected

    total = len(names)
    known = [_count(counts.get(name)) for name in names]
    full_expected = sum(known) if names and all(k is not None for k in known) else None
    if _done(FULL_SESSION_KEY, full_expected):
        return (total, total) if total else (1, 1)
    return sum(1 for name, k in zip(names, known, strict=True) if _done(name, k)), total
```

This replaces the old `_done` and the two return statements. `_count` is defined further down the module, which is fine at call time.

- [ ] **Step 6:** Remove the markers. Run `tests/test_session_lifecycle.py`, `tests/test_report_jobs.py`, `tests/test_browse_state.py` and the audit file. All PASS.
- [ ] **Step 7:** Add the bug-log section (finding 2.1, LIDA 2026-10-02 and 10-05; the Packer side is the packing-tool task). Then commit ("AUDIT-10-3: a short packing run does not complete a session").

### Task 4: AUDIT-10-4 (backend), fingerprint, withdrawal and failed regeneration (finding 2.2)

**Files:**
- Modify: `shopify_tool/report_jobs.py`
- Test: `tests/test_report_jobs.py`, `tests/audit/test_10_coverage_snapshot.py`

**Interfaces (produced, used by Task 5):**
- `report_jobs.WITHDRAWN_DIR = "withdrawn"`
- `report_jobs.packing_fingerprint(df: pd.DataFrame) -> str`
- `report_jobs.withdraw_lists(session_path, names: list[str]) -> list[str]` returns the names moved out.
- `report_jobs.out_of_date_message(withdrawn: list[str], started: list[str]) -> str`
- `report_jobs.recorded_fingerprints(session_info: dict | None) -> dict[str, str]`
- `ReportOutcome.fingerprint: str | None`, set for a packing list that was written.

- [ ] **Step 1: Write the failing tests** (in `tests/test_report_jobs.py`, reusing its `FRAME` and `PACKING_ALL`)

```python
def test_a_tag_edit_keeps_the_fingerprint_and_a_status_edit_changes_it():
    base = report_jobs.packing_fingerprint(FRAME)
    tagged = FRAME.assign(Internal_Tags=['["BOX"]', "[]"], Tags=["VIP", ""], Notes=["n", ""])
    assert report_jobs.packing_fingerprint(tagged) == base
    held = FRAME.copy()
    held.loc[0, "Order_Fulfillment_Status"] = "Not Fulfillable"
    assert report_jobs.packing_fingerprint(held) != base
    assert report_jobs.packing_fingerprint(FRAME.assign(Quantity=[1, 3])) != base
    assert report_jobs.packing_fingerprint(FRAME.iloc[:1]) != base
    assert report_jobs.packing_fingerprint(FRAME.iloc[::-1]) == base  # row order is not content


def test_withdraw_moves_an_unstarted_list_and_leaves_a_started_one(tmp_path):
    lists = tmp_path / "packing_lists"
    lists.mkdir()
    for name in ("ALL", "DHL"):
        (lists / f"{name}.json").write_text("{}", encoding="utf-8")
        (lists / f"{name}.xlsx").write_bytes(b"x")
    (tmp_path / "packing" / "DHL").mkdir(parents=True)

    assert report_jobs.withdraw_lists(tmp_path, ["ALL", "DHL"]) == ["ALL"]
    assert not (lists / "ALL.json").exists()
    assert (lists / "withdrawn" / "ALL.json").exists()
    assert (lists / "withdrawn" / "ALL.xlsx").exists()
    assert (lists / "DHL.json").exists()


def test_withdraw_replaces_an_older_withdrawn_copy(tmp_path):
    lists = tmp_path / "packing_lists"
    (lists / "withdrawn").mkdir(parents=True)
    (lists / "withdrawn" / "ALL.json").write_text("old", encoding="utf-8")
    (lists / "ALL.json").write_text("new", encoding="utf-8")
    report_jobs.withdraw_lists(tmp_path, ["ALL"])
    assert (lists / "withdrawn" / "ALL.json").read_text(encoding="utf-8") == "new"


def test_a_locked_json_is_not_reported_withdrawn(tmp_path, monkeypatch):
    lists = tmp_path / "packing_lists"
    lists.mkdir()
    (lists / "ALL.json").write_text("{}", encoding="utf-8")
    real = report_jobs.os.replace

    def locked(src, dst):
        if str(src).endswith(".json"):
            raise PermissionError(13, "in use", str(src))
        return real(src, dst)

    monkeypatch.setattr(report_jobs.os, "replace", locked)
    assert report_jobs.withdraw_lists(tmp_path, ["ALL"]) == []
    assert (lists / "ALL.json").exists()


def test_a_written_list_carries_its_fingerprint(tmp_path):
    outcome = report_jobs.generate_report(PACKING_ALL, tmp_path, FRAME, {}, "s")
    assert outcome.fingerprint == report_jobs.packing_fingerprint(FRAME)


def test_the_message_names_withdrawn_and_started_lists():
    assert report_jobs.out_of_date_message(["ALL"], []) == (
        "Your change makes packing list ALL out of date. Generate it again; "
        "until then the Packer can't open it."
    )
    assert report_jobs.out_of_date_message(["ALL", "DHL"], ["MASKS"]) == (
        "Your change makes packing lists ALL, DHL out of date. Generate them again; "
        "until then the Packer can't open them. MASKS is already being packed and still "
        "holds the old contents. Check it with the packer."
    )


def test_recorded_fingerprints_ignores_junk():
    info = {"statistics": {"packing_list_fingerprints": {"ALL": "ab", "X": 3}}}
    assert report_jobs.recorded_fingerprints(info) == {"ALL": "ab"}
    assert report_jobs.recorded_fingerprints(None) == {}
```

And in the audit file, the bug itself:

```python
@pytest.mark.xfail(strict=True, reason="AUDIT-10-4: a failed regeneration leaves the old list")
def test_audit_10_4_a_failed_regeneration_withdraws_the_old_list(tmp_path, monkeypatch):
    lists = tmp_path / "packing_lists"
    lists.mkdir()
    (lists / "ALL.json").write_text("{}", encoding="utf-8")

    def held(session_path, stem):
        raise PermissionError(13, "open in a viewer", f"{stem}_barcodes.pdf")

    monkeypatch.setattr(report_jobs.barcode_processor, "invalidate_label_pdfs", held)
    config = {"name": "ALL", "report_type": "packing_lists", "output_filename": "ALL.xlsx", "filters": []}
    outcome = report_jobs.generate_report(config, tmp_path, pd.DataFrame(), {}, "s")
    assert outcome.failed and outcome.locked_file
    assert not (lists / "ALL.json").exists()
```

- [ ] **Step 2:** Run them. The new-function tests FAIL with `AttributeError`, and the audit test XFAILs. **Step 3:** Commit the audit test alone ("AUDIT-10-4: failing test for an out-of-date packing list").
- [ ] **Step 4: Implement** in `report_jobs.py` (add `import hashlib`, `import os`, and `from . import report_filters` if missing; it is imported already):

```python
WITHDRAWN_DIR = "withdrawn"


def packing_fingerprint(df: pd.DataFrame) -> str:
    """What the Packer would pack from `df`: each fulfillable order's SKUs and quantities.

    Tags and notes are not in it, so a tag edit never makes a list out of date (AUDIT-10-4).
    """
    orders = core.build_packing_orders(report_filters.fulfillable_only(df))
    canon = sorted(
        [o["order_number"], sorted([i["sku"], i["quantity"]] for i in o["items"])] for o in orders
    )
    return hashlib.sha256(json.dumps(canon).encode("utf-8")).hexdigest()


def recorded_fingerprints(session_info) -> dict[str, str]:
    """The fingerprints session_info records for its packing lists; {} for an older session."""
    stats = (session_info or {}).get("statistics")
    found = stats.get("packing_list_fingerprints") if isinstance(stats, dict) else None
    if not isinstance(found, dict):
        return {}
    return {k: v for k, v in found.items() if isinstance(k, str) and isinstance(v, str)}


def withdraw_lists(session_path, names) -> list[str]:
    """Move unstarted packing lists out of the Packer's reach (AUDIT-10-4, ADR 0019).

    The Packer reads only packing_lists/*.json; a list moved to packing_lists/withdrawn/ cannot
    be opened. A list whose packing/<name>/ folder exists has been started and stays. Returns
    the names whose JSON was moved. Never raises for a file held open: it logs and goes on.
    """
    session = Path(session_path)
    lists_dir = session / "packing_lists"
    withdrawn = []
    for name in names:
        if (session / "packing" / name).exists():
            continue
        moved_json = False
        for suffix in (".json", ".xlsx"):
            source = lists_dir / f"{name}{suffix}"
            if not source.exists():
                continue
            try:
                (lists_dir / WITHDRAWN_DIR).mkdir(exist_ok=True)
                os.replace(source, lists_dir / WITHDRAWN_DIR / source.name)
            except PermissionError:
                logger.warning(f"Could not withdraw {source.name}: it is open in another program")
                continue
            moved_json |= suffix == ".json"
        if not moved_json:
            continue
        try:
            barcode_processor.invalidate_label_pdfs(session_path, name)
        except PermissionError:
            logger.warning(f"A label PDF of withdrawn list {name} is open; it stays until regenerated")
        withdrawn.append(name)
    return withdrawn


def out_of_date_message(withdrawn: list[str], started: list[str]) -> str:
    """The toast after an edit that made packing lists out of date."""
    parts = []
    if withdrawn:
        names = ", ".join(withdrawn)
        if len(withdrawn) == 1:
            parts.append(f"Your change makes packing list {names} out of date. Generate it again; "
                         "until then the Packer can't open it.")
        else:
            parts.append(f"Your change makes packing lists {names} out of date. Generate them again; "
                         "until then the Packer can't open them.")
    if started:
        names = ", ".join(started)
        if len(started) == 1:
            parts.append(f"{names} is already being packed and still holds the old contents. "
                         "Check it with the packer.")
        else:
            parts.append(f"{names} are already being packed and still hold the old contents. "
                         "Check them with the packer.")
    return " ".join(parts)
```

In `generate_report`, wrap the `invalidate_label_pdfs` call:

```python
            try:
                barcode_processor.invalidate_label_pdfs(session_path, Path(output_file).stem)
            except PermissionError:
                # The old list must not wait for the Packer while the PDF is closed (AUDIT-10-4).
                withdraw_lists(session_path, [Path(output_file).stem])
                raise
```

In the `else` branch where the list was written, after the JSON block, set `outcome.fingerprint = packing_fingerprint(analysis_df)`. Put it outside the JSON `try`, so a fingerprint exists whenever the XLSX was written.

- [ ] **Step 5:** Remove the marker. Run `tests/test_report_jobs.py`, `tests/test_label_pdf_invalidation.py` and the audit file. All PASS.
- [ ] **Step 6: Commit** ("AUDIT-10-4: packing fingerprint and list withdrawal"). The bug-log section is written in Task 5.

### Task 5: AUDIT-10-4 (window), withdraw out-of-date lists after an edit or a re-run

**Files:**
- Modify: `gui/session_write_queue.py:31-35` (add `PACKING_LISTS = "packing_lists"`)
- Modify: `gui/main_window_pyside.py` (imports; `_reset_session_state`; `load_existing_session` near `session_info = self.session_manager.get_session_info(session_path)`; `save_session_state`; new `_withdraw_out_of_date_lists`)
- Modify: `gui/actions_handler.py` (`_on_reports_generated`; `on_analysis_complete` success path)
- Create: `docs/adr/0019-withdrawn-packing-lists.md`
- Modify: `CONTEXT.md` (Sessions section)
- Test: `tests/audit/test_10_coverage_snapshot.py`

**Interfaces:**
- Consumes (Task 4): `packing_fingerprint`, `withdraw_lists`, `out_of_date_message`, `recorded_fingerprints`, `update_packing_list_statistics`, `ReportOutcome.fingerprint`.
- Produces: `MainWindow._list_fingerprints: dict[str, str]` and `MainWindow._withdraw_out_of_date_lists() -> None`.

- [ ] **Step 1: Write the failing tests** (audit file). Use the `main_window` fixture and `_open_with_state` from `tests/test_stale_session.py`:

```python
import gui.main_window_pyside as main_window_module

LISTED = pd.DataFrame(
    {"Order_Number": ["#1001", "#1002"], "SKU": ["A", "B"], "Quantity": [1, 1], "Stock": [5, 5],
     "Order_Fulfillment_Status": ["Fulfillable", "Fulfillable"], "Internal_Tags": ["[]", "[]"],
     "Tags": ["", ""]}
)


def _with_list(win, name="ALL", started=False):
    path = _open_with_state(win, LISTED)
    lists = Path(path) / "packing_lists"
    lists.mkdir(exist_ok=True)
    (lists / f"{name}.json").write_text('{"total_orders": 2}', encoding="utf-8")
    (lists / f"{name}.xlsx").write_bytes(b"x")
    if started:
        (Path(path) / "packing" / name).mkdir(parents=True)
    win._list_fingerprints = {name: report_jobs.packing_fingerprint(LISTED)}
    return path


@pytest.fixture
def toasts(monkeypatch):
    seen = []
    monkeypatch.setattr(main_window_module, "toast", lambda src, text, **k: seen.append(text))
    return seen


@pytest.mark.xfail(strict=True, reason="AUDIT-10-4: an edit leaves the old list for the Packer")
def test_audit_10_4_an_edit_withdraws_the_out_of_date_list_once(main_window, toasts):
    path = _with_list(main_window)
    main_window.actions_handler.bulk_change_status(["#1001"], False)
    assert main_window.write_queue.flush(timeout=10)
    assert not (Path(path) / "packing_lists" / "ALL.json").exists()
    assert (Path(path) / "packing_lists" / "withdrawn" / "ALL.json").exists()
    assert toasts == [report_jobs.out_of_date_message(["ALL"], [])]
    main_window.actions_handler.bulk_change_status(["#1002"], False)
    assert toasts == [report_jobs.out_of_date_message(["ALL"], [])]  # once, not per edit


def test_a_tag_edit_withdraws_nothing(main_window, toasts):
    path = _with_list(main_window)
    main_window.actions_handler.bulk_add_tag(["#1001"], "VIP")
    assert main_window.write_queue.flush(timeout=10)
    assert (Path(path) / "packing_lists" / "ALL.json").exists()
    assert toasts == []


def test_a_started_list_stays_and_is_named(main_window, toasts):
    path = _with_list(main_window, started=True)
    main_window.actions_handler.bulk_change_status(["#1001"], False)
    assert main_window.write_queue.flush(timeout=10)
    assert (Path(path) / "packing_lists" / "ALL.json").exists()
    assert toasts == [report_jobs.out_of_date_message([], ["ALL"])]


def test_a_session_without_fingerprints_withdraws_nothing(main_window, toasts):
    path = _with_list(main_window)
    main_window._list_fingerprints = {}
    main_window.actions_handler.bulk_change_status(["#1001"], False)
    assert main_window.write_queue.flush(timeout=10)
    assert (Path(path) / "packing_lists" / "ALL.json").exists()


def test_a_rerun_analysis_withdraws_out_of_date_lists(main_window, toasts):
    path = _with_list(main_window)
    rerun = LISTED.assign(Quantity=[2, 1])
    main_window.actions_handler.on_analysis_complete((True, "report.xlsx", rerun, {}))
    assert main_window.write_queue.flush(timeout=10)
    assert not (Path(path) / "packing_lists" / "ALL.json").exists()


def test_opening_a_session_loads_its_recorded_fingerprints(main_window):
    path = main_window.session_manager.create_session("acme")
    main_window.session_manager.update_session_info(
        path, {"statistics": {"packing_list_fingerprints": {"ALL": "ab"}}}
    )
    from shopify_tool import session_state
    session_state.save_state(path, LISTED, None)
    main_window.load_existing_session(path)
    assert main_window._list_fingerprints == {"ALL": "ab"}
```

If the toast for a withdrawn list reaches the web page through `web_toast` instead of the patched `toast`, follow the existing pattern in `tests/test_save_session_queue.py`, which patches `main_window_module.toast`. Make sure `_withdraw_out_of_date_lists` calls `toast(self, …)` by that module-level name.

- [ ] **Step 2:** Run them. The xfail XFAILs. Most of the others FAIL on `_list_fingerprints` (AttributeError). Mark each one that fails because of the bug with the same AUDIT-10-4 xfail. **Step 3:** Commit the tests.
- [ ] **Step 4: Implement.**

`gui/session_write_queue.py`: add `PACKING_LISTS = "packing_lists"` beside the other kinds. Mention it in the module docstring's list of files.

`gui/main_window_pyside.py`:
- Import `PACKING_LISTS` with the other kinds, and add `report_jobs` to `from shopify_tool import ...`.
- In `__init__`, before any session can load, set `self._list_fingerprints: dict[str, str] = {}`. In `_reset_session_state`, set `self._list_fingerprints = {}`.
- In `load_existing_session`, right after `session_info = self.session_manager.get_session_info(session_path)`, set `self._list_fingerprints = report_jobs.recorded_fingerprints(session_info)`.
- At the end of `save_session_state` (after the `SESSION_INFO` submit), call `self._withdraw_out_of_date_lists()`.
- Add the method:

```python
    def _withdraw_out_of_date_lists(self) -> None:
        """Withdraw the packing lists the frame on screen has made out of date (AUDIT-10-4, ADR 0019).

        A list records the packing fingerprint it was written from. When the frame's own
        fingerprint differs, the list no longer says what to pack: an unstarted one leaves the
        Packer's reach on the write queue, a started one is named so the operator checks it.
        Each list is reported once; generating it again records it afresh.
        """
        recorded = getattr(self, "_list_fingerprints", None)
        df = self.analysis_results_df
        if not recorded or not self.session_path or df is None:
            return
        current = report_jobs.packing_fingerprint(df)
        out_of_date = sorted(name for name, fp in recorded.items() if fp != current)
        if not out_of_date:
            return
        for name in out_of_date:
            del recorded[name]
        session_path = str(self.session_path)
        started = [n for n in out_of_date if (Path(session_path) / "packing" / n).exists()]
        unstarted = [n for n in out_of_date if n not in started]
        if unstarted:
            session_manager = getattr(self, "session_manager", None)

            def withdraw():
                report_jobs.withdraw_lists(session_path, unstarted)
                if session_manager is not None:
                    report_jobs.update_packing_list_statistics(session_manager, session_path)

            submit_or_run(getattr(self, "write_queue", None), session_path, PACKING_LISTS, withdraw)
            if hasattr(self, "session_browser"):
                self.session_browser.mark_dirty()
        toast(self, report_jobs.out_of_date_message(unstarted, started), role="info")
```

`gui/actions_handler.py`:
- In `_on_reports_generated`, inside the loop over outcomes that did not fail: when `outcome.removed_empty`, `self.mw._list_fingerprints.pop(Path(outcome.output_file).stem, None)`; else, when `outcome.fingerprint`, `self.mw._list_fingerprints[Path(outcome.output_file).stem] = outcome.fingerprint`. Use `getattr(self.mw, "_list_fingerprints", None)` and skip if it is None, because test doubles have no such attribute. Import `Path` if the module lacks it.
- In `on_analysis_complete`, on the success path, after the new frame is assigned to `self.mw.analysis_results_df` (find the assignment), call `self.mw._withdraw_out_of_date_lists()` if the window has it (`getattr(self.mw, "_withdraw_out_of_date_lists", None)`).

- [ ] **Step 5:** Remove the markers. Run the audit file, `tests/test_save_session_queue.py`, `tests/test_stale_session.py`, `tests/test_report_jobs.py` and `tests/test_actions_handler.py`. All PASS.
- [ ] **Step 6: ADR and glossary.** Create `docs/adr/0019-withdrawn-packing-lists.md`, in the format of `docs/adr/0018-*.md` (read it first):
  - Context: finding 2.2, ALMA 2026-10-02, where a removed line was packed and not written off. The Packer cannot be changed in this task.
  - Decision: each list records its packing fingerprint in `session_info.statistics.packing_list_fingerprints`. An edit or re-run whose fingerprint differs moves the unstarted lists to `packing_lists/withdrawn/`. A failed regeneration does the same. Started lists stay and are named in a toast. The Packer never reads `withdrawn/`. Regenerating writes a fresh list.
  - Consequences: the operator must regenerate after such an edit. Tag edits don't count. A list started before the edit still holds the old contents; the Packer-side fix (refusing a list older than the session's last edit) is future packing-tool work.

  In `CONTEXT.md` under `## Sessions`, add:

```markdown
**Packing fingerprint** — what a packing list would make the Packer pack: each fulfillable
order's SKUs and quantities, hashed. Tags and notes are not in it. Each list records the one it
was written from. ADR 0019.

**Withdrawn packing list** — a list moved to `packing_lists/withdrawn/` because an edit or a
re-run changed the packing fingerprint before the Packer started it. The Packer cannot open
it; generating the list again replaces it. Not **stale**, which is about a PC's copy of the
session state.
```

- [ ] **Step 7:** Bug-log section for AUDIT-10-4 (finding 2.2: ALMA 2026-10-02_2, HERBAR 2026-09-28_1 and 09-29_1; what happens now; tests in both files). Commit ("AUDIT-10-4: withdraw packing lists an edit makes out of date").

---

## Part B: production replay suite

### Task 6: B1, one public analysis entry point

**Files:**
- Modify: `shopify_tool/analysis.py:878-925` (`_detect_repeated_orders`), `:988-1000` and `:1125` (`_merge_results_to_dataframe`), `:1328-1336` and `:1472-1482` (`run_analysis`)
- Modify: `shopify_tool/core.py:229-300` (`_create_analysis_data_for_packing`), `:600-795` (`_load_and_validate_files`), `:898-1006` (`_run_analysis_and_rules`), `:1399-1405` (`_save_results_and_reports`), `:1515-1727` (`run_full_analysis`)
- Modify: `shopify_tool/packed_orders.py:44-131`
- Test: `tests/test_core.py`, `tests/test_packed_orders.py`, `tests/test_analysis.py`

**Interfaces (produced, used by Tasks 7–9):**

```python
# shopify_tool/core.py
@dataclass
class AnalysisResult:
    final_df: pd.DataFrame
    summary_present_df: pd.DataFrame
    stats: dict
    analysis_data: dict

def analyse(orders_df, stock_df, config, *, history_df=None, current_session=None, now=None) -> AnalysisResult
def read_orders_csv(path, column_mappings: dict, delimiter: str = AUTO_DELIMITER) -> pd.DataFrame
def _create_analysis_data_for_packing(final_df, now: datetime | None = None) -> dict
def _run_analysis_and_rules(orders_df, stock_df, history_df, config, current_session=None, today: date | None = None)

# shopify_tool/analysis.py
def run_analysis(stock_df, orders_df, history_df, column_mappings=None, courier_mappings=None,
                 current_session=None, mode="multi_first", today: date | None = None)
def _detect_repeated_orders(final_df, history_df, current_session=None, today: date | None = None)

# shopify_tool/packed_orders.py
def signals_from_entries(entries: list) -> tuple[pd.DataFrame, set[str] | None]
```

- [ ] **Step 1: Write the failing tests.**

`tests/test_analysis.py`:

```python
def test_repeat_detection_uses_the_given_day():
    from datetime import date
    from shopify_tool.analysis import _detect_repeated_orders
    final = pd.DataFrame({"Order_Number": ["#1"]})
    history = pd.DataFrame({"Order_Number": ["#1"], "Execution_Date": ["2026-10-05"], "Session": [""]})
    assert list(_detect_repeated_orders(final, history, None, today=date(2026, 10, 5))) == [""]
    assert list(_detect_repeated_orders(final, history, None, today=date(2026, 10, 6))) == ["Repeat"]
```

`tests/audit/test_10_coverage_snapshot.py` (it can use the audit fixtures; add
`from audit_support import analysis_run, sessions  # noqa: F401  pytest fixtures, used by name` and
`import json`, `from datetime import datetime, timedelta, timezone`, `from shopify_tool import core`):

```python
MAPPINGS_10 = {
    "orders": {"Name": "Order_Number", "Lineitem sku": "SKU",
               "Lineitem quantity": "Quantity", "Shipping Method": "Shipping_Method"},
    "stock": {"Артикул": "SKU", "Име": "Product_Name", "Наличност": "Stock"},
}


def _inputs(tmp_path):
    """Orders and stock read the way a run reads them (as tests/test_rule_settle.py does)."""
    (tmp_path / "orders.csv").write_text(
        "Name,Lineitem sku,Lineitem quantity,Shipping Method\n#1,A,1,DHL\n#2,B,2,DHL\n", encoding="utf-8")
    (tmp_path / "stock.csv").write_text("Артикул,Име,Наличност\nA,Alpha,5\nB,Beta,1\n", encoding="utf-8")
    config = {"column_mappings": MAPPINGS_10, "settings": {}}
    orders, stock = core._load_and_validate_files(
        str(tmp_path / "stock.csv"), str(tmp_path / "orders.csv"), ",", ",", config)
    return orders, stock, config


def test_analyse_stamps_the_given_time_and_matches_the_private_path(tmp_path):
    orders, stock, config = _inputs(tmp_path)
    when = datetime(2026, 10, 9, 9, 13, tzinfo=timezone(timedelta(hours=3)))
    result = core.analyse(orders, stock, config, now=when, current_session="S1")
    assert result.analysis_data["analyzed_at"] == when.isoformat()
    final, _, stats = core._run_analysis_and_rules(
        orders, stock, pd.DataFrame({"Order_Number": []}), config, "S1")
    pd.testing.assert_frame_equal(result.final_df, final)
    assert result.analysis_data["total_orders"] == 2


def test_run_full_analysis_writes_what_analyse_returns(analysis_run, sessions, monkeypatch):
    seen = {}
    real = core.analyse

    def spy(*a, **k):
        seen["result"] = real(*a, **k)
        return seen["result"]

    monkeypatch.setattr(core, "analyse", spy)
    session = sessions.create_session("M")
    ok, msg, _df, _stats = analysis_run(session)
    assert ok, msg
    written = json.loads((Path(session) / "analysis" / "analysis_data.json").read_text(encoding="utf-8"))
    assert written == seen["result"].analysis_data
```

`tests/test_packed_orders.py`:

```python
def test_signals_from_entries_reads_packed_orders_and_live_sessions():
    entries = [
        {"session_name": "S1", "status": "completed",
         "packing_progress": {"ALL": {"started_at": "2026-10-05T09:14:52+03:00", "completed_orders": ["#1", "#2"]}}},
        {"session_name": "S2", "status": "abandoned"},
    ]
    packed, live = packed_orders.signals_from_entries(entries)
    assert sorted(packed["Order_Number"]) == ["#1", "#2"]
    assert set(packed["Execution_Date"]) == {"2026-10-05"}
    assert live == {"S1"}
    packed, live = packed_orders.signals_from_entries([])
    assert packed.empty and live is None
```

- [ ] **Step 2:** Run. Expected: FAIL (unknown keyword `today`, no `analyse`, no `signals_from_entries`).
- [ ] **Step 3: Implement `today`.** In `_detect_repeated_orders`, add `today: date | None = None` (import `date` from `datetime`) and use `today = pd.Timestamp(today or datetime.now().date())  # noqa: DTZ005`. Thread `today` as a keyword through `_merge_results_to_dataframe(..., today=None)` (its call at line 1125) and `run_analysis(..., today=None)` (its call to `_merge_results_to_dataframe`). Document it in each docstring: "the day repeat detection treats as today; None is the real date (a replay passes the session's)".
- [ ] **Step 4: Implement in core.**
  - `_create_analysis_data_for_packing(final_df, now=None)`: `stamp = (now or datetime.now().astimezone()).isoformat()` once, used for every `analyzed_at` in the function.
  - `_run_analysis_and_rules(..., today=None)` passes `today=today` to `analysis.run_analysis`.
  - Add `AnalysisResult` (with `from dataclasses import dataclass`) and:

```python
def analyse(orders_df, stock_df, config, *, history_df=None, current_session=None, now=None) -> AnalysisResult:
    """Analyse these frames with this config at this time.

    The one path a run and a replay share: run_full_analysis calls it, and tests/replay/
    calls it on stored production sessions. `history_df` is the detection frame
    (packed_orders.union_history_with_packed); `now` is an aware datetime, the session's
    creation time in a replay, and dates both repeat detection and analyzed_at.
    """
    now = now or datetime.now().astimezone()
    if history_df is None:
        history_df = pd.DataFrame({"Order_Number": []})
    final_df, summary_present_df, stats = _run_analysis_and_rules(
        orders_df, stock_df, history_df, config, current_session, today=now.date()
    )
    return AnalysisResult(final_df, summary_present_df, stats, _create_analysis_data_for_packing(final_df, now))
```

  - `read_orders_csv`: move the orders `pd.read_csv(...)` call (dtype from `_get_sku_dtype_dict(column_mappings, "orders")`, `encoding="utf-8-sig"`, `delimiter=resolve_delimiter(path, delimiter, "orders")`) into this function. Call it from both places in `_load_and_validate_files`, and keep their `try/except` logging around the call as it is.
  - `run_full_analysis`: replace the `_run_analysis_and_rules(...)` call with `result = analyse(orders_df, stock_df, config, history_df=detection_history_df, current_session=current_session)` and unpack `final_df, summary_present_df, stats = result.final_df, result.summary_present_df, result.stats`. Give `_save_results_and_reports` a new keyword `analysis_data: dict | None = None`. Pass `analysis_data=result.analysis_data`, and in the export block use `analysis_data = analysis_data if analysis_data is not None else _create_analysis_data_for_packing(final_df)`.
- [ ] **Step 5: Implement `signals_from_entries`.** Move the body of `_load_session_signals` from `if not entries:` onwards into `signals_from_entries(entries)`. `_load_session_signals` then becomes `return signals_from_entries(SessionManager(profile_manager).list_client_sessions(client_id))`. Its docstring says what an entry must hold (`session_name` or `session_path`, `status`, `packing_progress`).
- [ ] **Step 6:** Run the new tests, then `tests/test_core.py`, `tests/test_analysis.py`, `tests/test_packed_orders.py`, `tests/test_rule_settle.py`, `tests/audit/test_02_repeat_orders.py` and `tests/test_memory_baseline.py`. All PASS. Then `ruff check .`.
- [ ] **Step 7: Commit** ("Replay: public core.analyse entry point").

### Task 7: B2, the session keeps the config it ran with

**Files:**
- Modify: `shopify_tool/core.py` (`_save_results_and_reports`, session-mode block; `run_full_analysis` passes the config)
- Test: `tests/test_core.py`

**Interfaces:** Produces the file `<session>/input/shopify_config.json`.

- [ ] **Step 1: Write the failing test** (audit file, beside Task 6's session test):

```python
def test_a_session_keeps_the_config_it_ran_with(sessions, tmp_path, monkeypatch):
    from shopify_tool import fulfillment_history
    monkeypatch.setattr(core, "load_session_signals",
                        lambda _pm, _cid: (pd.DataFrame(columns=fulfillment_history.COLUMNS), None))
    (tmp_path / "o.csv").write_text(
        "Name,Lineitem sku,Lineitem quantity,Shipping Method\n#1,A,1,DHL\n", encoding="utf-8")
    (tmp_path / "s.csv").write_text("Артикул,Име,Наличност\nA,Alpha,5\n", encoding="utf-8")
    config = {"column_mappings": MAPPINGS_10, "rules": [], "inventory_memory": {"skus": {"A": 1}},
              "_client_config": {"x": 1}, "test_history_df": None}
    session = sessions.create_session("M")
    ok, msg, _df, _stats = core.run_full_analysis(
        str(tmp_path / "s.csv"), str(tmp_path / "o.csv"), str(tmp_path / "out"), ",", ",", config,
        client_id="M", session_manager=sessions, profile_manager=sessions.profile_manager,
        session_path=str(session))
    assert ok, msg
    kept = json.loads((Path(session) / "input" / "shopify_config.json").read_text(encoding="utf-8"))
    assert kept == {"column_mappings": MAPPINGS_10, "rules": []}
```

- [ ] **Step 2:** Run. FAIL (no file). **Step 3: Implement.** Give `_save_results_and_reports` a keyword `run_config: dict | None = None`, and pass `run_config=config` from `run_full_analysis`. In the session-mode export block, before `analysis_data.json` is written:

```python
            # The config of the day, so the session can be replayed later (spec Part B2):
            # backups rotate within days. Without derived data and run-only keys.
            if run_config is not None:
                kept = {k: v for k, v in run_config.items()
                        if not k.startswith(("_", "test_")) and k != "inventory_memory"}
                try:
                    atomic_write_json(Path(working_path) / "input" / "shopify_config.json", kept)
                except Exception:
                    logger.warning("Could not keep the session's config copy", exc_info=True)
```

A DataFrame value would make `atomic_write_json` fail. The filter drops the `test_*` keys that hold frames; the `try` is the backstop. The real path to `input/` is `session_manager.get_input_dir(working_path)` when that exists. Check `_validate_and_prepare_inputs` for how inputs are copied and use the same directory.

- [ ] **Step 4:** Run the test and `tests/test_core.py`. PASS. **Step 5: Commit** ("Replay: keep the run's config in the session").

### Task 8: B3, replay harness, anonymiser and fixture builder

**Files:**
- Create: `tests/replay/anonymise.py`, `tests/replay/replay.py`, `tests/replay/test_anonymise.py`
- Create: `scripts/build_replay_fixtures.py`

**Interfaces:**
- `anonymise.OrderMap(numbers)` with `.map(raw: str) -> str`.
- `anonymise.orders_frame(raw: DataFrame, config: dict, omap: OrderMap) -> DataFrame`.
- `anonymise.packing_doc(doc: dict, omap) -> dict` (analysis_data or packing list).
- `anonymise.clean_config(config: dict) -> dict`.
- `anonymise.config_of_day(backups: list[tuple[datetime, Path]], current: Path, created: datetime) -> tuple[Path, bool]`.
- `replay.replay_session(session_dir: Path, work_dir: Path) -> tuple[dict, dict[str, dict]]`.
- `replay.first_difference(expected: dict, actual: dict) -> str | None`.

- [ ] **Step 1: Write the anonymiser tests** (`tests/replay/test_anonymise.py`; synthetic data only):

```python
from datetime import datetime
from pathlib import Path

import pandas as pd
from anonymise import OrderMap, clean_config, config_of_day, orders_frame, packing_doc


def test_order_map_keeps_prefix_length_and_order():
    omap = OrderMap(["#1500", "#1203", "#987", "BG-77"])
    assert omap.map("#1203") == "#1001"
    assert omap.map("#1500") == "#1002"
    assert omap.map("#987") == "#101"
    assert omap.map("BG-77") == "BG-11"
    assert omap.map("") == ""


def test_order_map_without_digits_and_whitespace():
    omap = OrderMap(["ABC", " #12 "])
    assert omap.map("ABC") == "ORD1"
    assert omap.map("#12") == omap.map(" #12 ") == "#11"


CONFIG = {"column_mappings": {"orders": {"Name": "Order_Number", "Shipping Name": "Customer",
                                         "Notes": "Notes", "Lineitem sku": "SKU"},
                              "additional_columns": [{"csv_name": "Financial Status", "enabled": True}]},
          "inventory_memory": {"skus": {}}, "last_updated": "x", "updated_by": "PC"}


def test_orders_frame_keeps_only_mapped_columns_and_masks_people():
    raw = pd.DataFrame({"Name": ["#12", "#12"], "Shipping Name": ["Real Person", ""],
                        "Notes": ["call me", ""], "Lineitem sku": ["A", "B"], "Email": ["a@b.c", ""],
                        "Financial Status": ["paid", "paid"], "_source_file": ["shop.csv", "shop.csv"]})
    out = orders_frame(raw, CONFIG, OrderMap(["#12"]))
    assert list(out.columns) == ["Name", "Shipping Name", "Notes", "Lineitem sku", "Financial Status", "_source_file"]
    assert list(out["Name"]) == ["#11", "#11"]
    assert list(out["Shipping Name"]) == ["Customer", ""]
    assert list(out["Notes"]) == ["Note", ""]


def test_packing_doc_maps_numbers_and_masks_notes():
    doc = {"analyzed_at": "t", "orders": [{"order_number": "#12", "notes": "call me", "items": []},
                                         {"order_number": "#13", "notes": "", "items": []}]}
    out = packing_doc(doc, OrderMap(["#12", "#13"]))
    assert [o["order_number"] for o in out["orders"]] == ["#11", "#12"]
    assert [o["notes"] for o in out["orders"]] == ["Note", ""]
    assert doc["orders"][0]["order_number"] == "#12"  # input untouched


def test_clean_config_drops_derived_and_machine_keys():
    assert set(clean_config(CONFIG)) == {"column_mappings"}


def test_config_of_day_takes_the_first_backup_after_the_session():
    created = datetime.fromisoformat("2026-10-05T11:07:09+03:00")
    b = [(datetime(2026, 10, 5, 9), Path("b1")), (datetime(2026, 10, 5, 12), Path("b2")),
         (datetime(2026, 10, 6, 9), Path("b3"))]
    assert config_of_day(b, Path("cur"), created) == (Path("b2"), True)
    assert config_of_day(b[1:], Path("cur"), created) == (Path("b2"), False)  # older ones rotated away
    assert config_of_day(b[:1], Path("cur"), created) == (Path("cur"), True)  # nothing saved since
```

- [ ] **Step 2:** Run. FAIL (no module). **Step 3: Implement `tests/replay/anonymise.py`:**

```python
"""Anonymise production snapshot data into replay fixtures (spec Part B3).

Pure functions; scripts/build_replay_fixtures.py does the file work. Nothing here may let a
name, address, phone or e-mail through: only the columns the config maps survive, and the
two mapped columns that hold people's words (Customer, Notes) are masked.
"""

import copy
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

_NUMBER = re.compile(r"(\D*)(\d+)(\D*)")
DROPPED_CONFIG_KEYS = {"inventory_memory", "last_updated", "updated_by"}


class OrderMap:
    """One client's order-number mapping, shared by every file of its fixtures.

    Keeps the prefix, the suffix and the digit count; numbers of one digit count, sorted
    numerically, become 10^(n-1)+1, +2, ... so numeric order is kept. Numbers without
    digits become ORD1, ORD2, ...
    """

    def __init__(self, numbers):
        self._map: dict[str, str] = {}
        clean = sorted({str(n).strip() for n in numbers if str(n).strip()})
        by_width: dict[int, list[tuple[int, str]]] = {}
        plain = []
        for raw in clean:
            m = _NUMBER.fullmatch(raw)
            if m:
                by_width.setdefault(len(m.group(2)), []).append((int(m.group(2)), raw))
            else:
                plain.append(raw)
        for width, items in by_width.items():
            start = 10 ** (width - 1) if width > 1 else 0
            assert len(items) < 10**width - start, f"too many {width}-digit order numbers"
            for i, (_, raw) in enumerate(sorted(items)):
                m = _NUMBER.fullmatch(raw)
                self._map[raw] = f"{m.group(1)}{start + i + 1:0{width}d}{m.group(3)}"
        for i, raw in enumerate(plain):
            self._map[raw] = f"ORD{i + 1}"

    def map(self, raw) -> str:
        key = "" if raw is None else str(raw).strip()
        return self._map.get(key, key) if key else ""


def _column_for(config: dict, internal: str) -> list[str]:
    return [c for c, v in config["column_mappings"]["orders"].items() if v == internal]


def orders_frame(raw: pd.DataFrame, config: dict, omap: OrderMap) -> pd.DataFrame:
    mapping = config["column_mappings"]["orders"]
    extra = [c["csv_name"] for c in config["column_mappings"].get("additional_columns", []) or []
             if c.get("enabled")]
    keep = [c for c in raw.columns if c in mapping or c in extra or c == "_source_file"]
    out = raw[keep].copy()
    for column in _column_for(config, "Order_Number"):
        if column in out:
            out[column] = out[column].map(omap.map)
    for internal, placeholder in (("Customer", "Customer"), ("Notes", "Note")):
        for column in _column_for(config, internal):
            if column in out:
                out[column] = out[column].where(out[column].fillna("") == "", placeholder)
    return out


def packing_doc(doc: dict, omap: OrderMap) -> dict:
    out = copy.deepcopy(doc)
    for order in out.get("orders", []):
        order["order_number"] = omap.map(order.get("order_number"))
        if order.get("notes"):
            order["notes"] = "Note"
    return out


def clean_config(config: dict) -> dict:
    return {k: v for k, v in config.items() if k not in DROPPED_CONFIG_KEYS}


def config_of_day(backups, current: Path, created: datetime) -> tuple[Path, bool]:
    """The config in force when the session was created, and whether that is certain.

    A backup holds the file as it was before a save, so the first backup taken after the
    session is the config of the session. It is certain only when an older backup is still
    there (none were rotated away in between); with no backup after the session, nothing was
    saved since and the current file is it.
    """
    local = created.replace(tzinfo=None)
    after = sorted((t, p) for t, p in backups if t > local)
    if not after:
        return current, True
    return after[0][1], any(t <= local for t, _ in backups)
```

`orders_frame` must keep the column order of the raw file; the test checks the order of `keep`. `Path` order inside `sorted` tuples: the timestamps are unique, so the paths are never compared.

- [ ] **Step 4:** Run `tests/replay/test_anonymise.py`. PASS.
- [ ] **Step 5: Implement `tests/replay/replay.py`:**

```python
"""Replay one anonymised production session through today's code (spec Part B3).

Inputs are read the way the app reads them, the clock is the session's creation time, and
history and Packer signals are cut to what existed when the session was created.
"""

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from shopify_tool import core, fulfillment_history, packed_orders, report_jobs

IGNORED = {"analyzed_at", "created_at", "session_id"}


def _read(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _when(value) -> datetime | None:
    try:
        return datetime.fromisoformat(value) if value else None
    except (TypeError, ValueError):
        return None


def _report_config(config: dict, stem: str) -> dict:
    for candidate in config.get("packing_list_configs", []):
        name = candidate.get("output_filename") or f"{candidate.get('name')}.xlsx"
        if Path(name).stem == stem:
            return candidate
    raise KeyError(f"no packing_list_configs entry writes {stem}")


def replay_session(session_dir, work_dir) -> tuple[dict, dict[str, dict]]:
    session_dir = Path(session_dir)
    client_dir = session_dir.parent
    meta = _read(session_dir / "meta.json")
    config = _read(client_dir / meta["config"])
    created = datetime.fromisoformat(meta["created_at"])
    name = session_dir.name

    sessions = _read(client_dir / "sessions.json")
    not_yet = {e["session_name"] for e in sessions if (_when(e.get("created_at")) or created) >= created}
    history = fulfillment_history.load(client_dir / "history.csv")
    dates = pd.to_datetime(history["Execution_Date"], errors="coerce", format="mixed")
    future_legacy = (history["Session"] == "") & (dates >= pd.Timestamp(created.date()))
    history = history[~history["Session"].isin(not_yet) & ~future_legacy]

    earlier = []
    for entry in sessions:
        when = _when(entry.get("created_at"))
        if when is None or when >= created:
            continue
        progress = {
            key: block for key, block in (entry.get("packing_progress") or {}).items()
            if isinstance(block, dict)
            and (_when(block.get("started_at") or block.get("updated_at")) or created) < created
        }
        earlier.append({**entry, "packing_progress": progress})
    earlier.append({"session_name": name, "status": "active"})
    packed, live = packed_orders.signals_from_entries(earlier)
    detection = packed_orders.union_history_with_packed(history, packed, live)

    orders = core.read_orders_csv(session_dir / "orders.csv", config.get("column_mappings", {}))
    stock = core.baseline_stock_df(_read(session_dir / "memory_baseline.json"))
    result = core.analyse(orders, stock, config, history_df=detection, current_session=name, now=created)

    lists = {}
    for stem in meta.get("packing_lists", []):
        report_config = {**_report_config(config, stem), "report_type": "packing_lists"}
        report_jobs.generate_report(report_config, work_dir, result.final_df,
                                    config.get("tag_categories", {}), name)
        lists[stem] = _read(Path(work_dir) / "packing_lists" / f"{stem}.json")
    return result.analysis_data, lists


def strip_ignored(doc):
    if isinstance(doc, dict):
        return {k: strip_ignored(v) for k, v in doc.items() if k not in IGNORED}
    if isinstance(doc, list):
        return [strip_ignored(v) for v in doc]
    return doc


def first_difference(expected: dict, actual: dict) -> str | None:
    """None when equal (ignoring time stamps and session ids), else where they first differ."""
    e, a = strip_ignored(expected), strip_ignored(actual)
    if e == a:
        return None
    for key in sorted(set(e) | set(a)):
        if key != "orders" and e.get(key) != a.get(key):
            return f"{key}: expected {e.get(key)!r}, got {a.get(key)!r}"
    eo, ao = e.get("orders", []), a.get("orders", [])
    for i, (x, y) in enumerate(zip(eo, ao)):
        if x != y:
            fields = [k for k in sorted(set(x) | set(y)) if x.get(k) != y.get(k)]
            return f"order {i} ({x.get('order_number')}): {fields}"
    return f"order count: expected {len(eo)}, got {len(ao)}"
```

Add to `test_anonymise.py` a `first_difference` test: equal documents ignoring `analyzed_at` give None, and a changed `quantity` names the order and `items`.

- [ ] **Step 6: Implement `scripts/build_replay_fixtures.py`** (IO only; never prints raw values):

```python
#!/usr/bin/env python3
"""Build anonymised replay fixtures from the production server snapshot (spec Part B3).

    .venv/bin/python scripts/build_replay_fixtures.py --server ~/Desktop/Server./Server [--only ALMA/2026-10-05_2]

Reads the raw tree read-only and writes only anonymised files under tests/replay/fixtures/.
Every session is replayed after it is written; one that does not reproduce its stored result
is deleted again and named, and the script exits 1. Never edit an expected file to pass.
"""

import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO), str(REPO / "tests" / "replay")]
from anonymise import OrderMap, clean_config, config_of_day, orders_frame, packing_doc  # noqa: E402
from replay import first_difference, replay_session  # noqa: E402

from shopify_tool import fulfillment_history  # noqa: E402
from shopify_tool.csv_utils import AUTO_DELIMITER, resolve_delimiter  # noqa: E402

TREE = "0BFulfilment (new)"
OUT = REPO / "tests" / "replay" / "fixtures"
# golden_sessions of ~/Desktop/Server./snapshot.duckdb (2026-10-11). LIDA: 2026-10-09_1 only (owner's rule).
GOLDEN = {
    "ALMA": ["2026-09-30_6", "2026-10-01_5", "2026-10-01_7", "2026-10-01_8", "2026-10-02_2",
             "2026-10-02_3", "2026-10-02_6", "2026-10-02_8", "2026-10-05_10", "2026-10-05_2",
             "2026-10-05_3", "2026-10-05_4", "2026-10-05_8", "2026-10-05_9", "2026-10-06_2",
             "2026-10-06_7", "2026-10-06_9", "2026-10-07_3", "2026-10-07_5"],
    "HERBAR": ["2026-09-30_1", "2026-10-02_1", "2026-10-05_1", "2026-10-06_1", "2026-10-07_1", "2026-10-09_1"],
    "LIDA": ["2026-10-09_1"],
}
# Golden sessions with manual operations after the analysis: their packing lists include the
# operations, which the replay does not apply (task B4), so only analysis_data.json is compared.
WITH_OPERATIONS = {("ALMA", "2026-10-01_8"), ("ALMA", "2026-10-02_2"), ("ALMA", "2026-10-02_3"),
                   ("ALMA", "2026-10-02_6"), ("ALMA", "2026-10-02_8"), ("HERBAR", "2026-10-09_1")}
_BACKUP = re.compile(r"shopify_config_(\d{8}_\d{6})")


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path, doc):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def _raw_csv(path):
    sep = resolve_delimiter(str(path), AUTO_DELIMITER, "orders")
    return pd.read_csv(path, sep=sep, dtype=str, keep_default_na=False, encoding="utf-8-sig")


def _orders_file(session):
    merged = session / "input" / "merged_orders.csv"
    return merged if merged.exists() else session / "input" / "orders_export.csv"


def _backups(client):
    found = []
    for p in (client / "backups").glob("shopify_config_*.json"):
        m = _BACKUP.match(p.name)
        if m:
            found.append((datetime.strptime(m.group(1), "%Y%m%d_%H%M%S"), p))
    return found


def build_client(server: Path, client_id: str, only: set[str] | None) -> list[str]:
    tree = server / TREE
    client = tree / "Clients" / f"CLIENT_{client_id}"
    sessions_root = tree / "Sessions" / f"CLIENT_{client_id}"
    infos = {}
    for d in sorted(sessions_root.iterdir()):
        try:
            infos[d.name] = _read(d / "session_info.json")
        except (OSError, ValueError):
            continue
    golden = [s for s in GOLDEN[client_id] if not only or f"{client_id}/{s}" in only]

    # Pass 1: the config of each session, and every order number the fixtures will hold.
    configs, numbers = {}, []
    for name in golden:
        path, exact = config_of_day(_backups(client), client / "shopify_config.json",
                                    datetime.fromisoformat(infos[name]["created_at"]))
        configs[name] = (clean_config(_read(path)), exact)
        config = configs[name][0]
        column = [c for c, v in config["column_mappings"]["orders"].items() if v == "Order_Number"][0]
        numbers += list(_raw_csv(_orders_file(sessions_root / name))[column])
        numbers += [o["order_number"] for o in _read(sessions_root / name / "analysis" / "analysis_data.json")["orders"]]
    history = fulfillment_history.load(client / "fulfillment_history.csv")
    numbers += list(history["Order_Number"])
    for info in infos.values():
        for block in (info.get("packing_progress") or {}).values():
            if isinstance(block, dict) and isinstance(block.get("completed_orders"), list):
                numbers += block["completed_orders"]
    omap = OrderMap(numbers)

    # Pass 2: client-wide files.
    out = OUT / client_id
    history = history.assign(Order_Number=history["Order_Number"].map(omap.map))
    out.mkdir(parents=True, exist_ok=True)
    history.to_csv(out / "history.csv", index=False, encoding="utf-8")
    entries = []
    for name, info in infos.items():
        progress = {}
        for key, block in (info.get("packing_progress") or {}).items():
            if isinstance(block, dict):
                block = dict(block)
                if isinstance(block.get("completed_orders"), list):
                    block["completed_orders"] = [omap.map(o) for o in block["completed_orders"]]
                progress[key] = {k: block.get(k) for k in ("status", "started_at", "updated_at", "completed_orders")}
        entries.append({"session_name": name, "status": info.get("status"),
                        "created_at": info.get("created_at"), "packing_progress": progress})
    _write_json(out / "sessions.json", entries)

    # Pass 3: one folder per session, replayed before it is kept.
    failed = []
    for name in golden:
        source = sessions_root / name
        config, exact = configs[name]
        config_name = f"config/{hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:8]}.json"
        _write_json(out / config_name, config)
        target = out / name
        shutil.rmtree(target, ignore_errors=True)
        target.mkdir(parents=True)
        orders_frame(_raw_csv(_orders_file(source)), config, omap).to_csv(
            target / "orders.csv", index=False, encoding="utf-8")
        shutil.copyfile(source / "analysis" / "memory_baseline.json", target / "memory_baseline.json")
        _write_json(target / "expected" / "analysis_data.json",
                    packing_doc(_read(source / "analysis" / "analysis_data.json"), omap))
        lists = []
        if (client_id, name) not in WITH_OPERATIONS:
            for path in sorted((source / "packing_lists").glob("*.json")):
                lists.append(path.stem)
                _write_json(target / "expected" / "packing_lists" / path.name, packing_doc(_read(path), omap))
        _write_json(target / "meta.json", {"created_at": infos[name]["created_at"], "config": config_name,
                                           "config_exact": exact, "packing_lists": lists})
        with tempfile.TemporaryDirectory() as work:
            try:
                analysis_data, replayed = replay_session(target, work)
                diffs = [first_difference(_read(target / "expected" / "analysis_data.json"), analysis_data)]
                diffs += [first_difference(_read(target / "expected" / "packing_lists" / f"{s}.json"), doc)
                          for s, doc in replayed.items()]
                problem = next((d for d in diffs if d), None)
            except Exception as e:  # a crash is a failed replay too
                problem = f"{type(e).__name__}: {e}"
        if problem:
            shutil.rmtree(target)
            failed.append(f"{client_id}/{name}: {problem}")
        else:
            print(f"ok {client_id}/{name} ({'exact' if exact else 'nearest'} config, {len(lists)} lists)")
    return failed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--server", type=Path, required=True, help="the Server/ folder of the snapshot")
    parser.add_argument("--only", action="append", help="CLIENT/SESSION, repeatable")
    args = parser.parse_args()
    only = set(args.only or [])
    failed = []
    for client_id in GOLDEN:
        if only and not any(o.startswith(f"{client_id}/") for o in only):
            continue
        failed += build_client(args.server.expanduser(), client_id, only)
    for line in failed:
        print(f"FAILED {line}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
```

A failure message can quote an order number. It is the anonymised one, so it is safe to print. Still, never paste builder output into a commit or the PR.

- [ ] **Step 7:** `ruff check .` (fix what it reports in the new files). Commit `tests/replay/anonymise.py`, `replay.py`, `test_anonymise.py` and `scripts/build_replay_fixtures.py` ("Replay: anonymiser, harness and fixture builder").

### Task 9: B3, build the fixtures and the suite

**Files:**
- Create: `tests/replay/test_replay.py`, `tests/replay/fixtures/**`

- [ ] **Step 1: Write the suite:**

```python
"""Today's code reproduces 26 production sessions (spec Part B3; ~/Desktop/Server./findings.md §5).

A failure is a regression or a bug fixed since; decide which before touching an expected file.
Fixtures are anonymised by scripts/build_replay_fixtures.py and hold no customer data.
"""

import json
import re
from pathlib import Path

import pandas as pd
import pytest
from replay import first_difference, replay_session

FIXTURES = Path(__file__).parent / "fixtures"
SESSIONS = sorted(p.parent for p in FIXTURES.glob("*/*/meta.json"))
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
PHONE = re.compile(r"\+\d[\d \-]{8,}")
PATH = re.compile(r"\\\\|\b[A-Za-z]:\\")


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_the_suite_holds_all_26_sessions():
    assert len(SESSIONS) == 26


@pytest.mark.parametrize("session_dir", SESSIONS, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_replay_reproduces_the_stored_result(session_dir, tmp_path):
    analysis_data, lists = replay_session(session_dir, tmp_path)
    diff = first_difference(_read(session_dir / "expected" / "analysis_data.json"), analysis_data)
    assert diff is None, diff
    for stem, doc in lists.items():
        diff = first_difference(_read(session_dir / "expected" / "packing_lists" / f"{stem}.json"), doc)
        assert diff is None, f"{stem}: {diff}"


def test_fixtures_hold_no_pii():
    files = [p for p in FIXTURES.rglob("*") if p.is_file()]
    assert files
    for path in files:
        text = path.read_text(encoding="utf-8")
        for pattern in (EMAIL, PHONE, PATH):
            assert not pattern.search(text), f"{path.relative_to(FIXTURES)} matches {pattern.pattern}"
    for orders in FIXTURES.glob("*/*/orders.csv"):
        config = _read(orders.parent.parent / _read(orders.parent / "meta.json")["config"])
        mappings = config["column_mappings"]
        allowed = set(mappings["orders"]) | {"_source_file"} | {
            c["csv_name"] for c in mappings.get("additional_columns", []) or [] if c.get("enabled")}
        assert set(pd.read_csv(orders, nrows=0).columns) <= allowed, orders
    for history in FIXTURES.glob("*/history.csv"):
        assert set(pd.read_csv(history, nrows=0).columns) <= {"Order_Number", "Execution_Date", "Session"}
```

If the history file has more columns than those three, read `fulfillment_history.COLUMNS` and the `load` function. Allow exactly the columns `load` returns, after checking that none of them holds people's data. If one does, drop it in the builder.

- [ ] **Step 2: Build.** `.venv/bin/python scripts/build_replay_fixtures.py --server ~/Desktop/Server./Server`. Expected: 26 `ok` lines and exit 0.
  - **If any session fails, stop.** Do not edit expected files or the comparison. Two causes are understood. (a) The order mapping changed the order of orders: the message names order 0 or a shifted order number. (b) A real regression. For (a), make the mapping also keep lexicographic order across digit counts, then rebuild. For (b), or anything else, `runner <run> note` the failing session and the message (the anonymised order number only), and stop the task without committing fixtures. Findings §5 replayed all 26 identically on this code, so a failure is news.
  - A crash from the expected-files path while reading a raw file means the snapshot layout differs from the spec. Note it and stop.
- [ ] **Step 3: Check by eye, as the task requires.** Open every `tests/replay/fixtures/*/config/*.json` and confirm it holds no e-mail address, person's name or path. Open one `orders.csv` per client and confirm the columns are as expected. Grep the fixtures for any customer surname you can find in the raw `orders_export.csv` of one session (`Shipping Name`), and expect no hit. Do not write that name anywhere.
- [ ] **Step 4:** Run `tests/replay/`. All PASS: 26 replays, the count and the PII guard. The full run adds a few seconds.
- [ ] **Step 5:** Run `du -sh tests/replay/fixtures` and note the size in the commit message (expected: a few MB).
- [ ] **Step 6: Commit** the fixtures and `test_replay.py` ("Replay: 26 anonymised production sessions").
- [ ] **Step 7:** Add a short "Replay suite" paragraph to the bug log (no id): what it covers, how to rebuild, and that operation replay (B4) is a follow-up. Commit it with the next task's log edit.

---

## Part L: production log warnings

### Task 10: AUDIT-10-5..7, the three warnings 2.3.1 still logs

**Files:**
- Modify: `shopify_tool/templates/barcode_label/style.css:90`, `shopify_tool/templates/qr_label/style.css:90`
- Modify: `shopify_tool/analysis.py:~106` (`_parse_expiry_date`)
- Modify: `shared/web_page.py:256-262` (`when_painted.finish`)
- Test: the audit file; `tests/test_web_page.py:149-158`

- [ ] **Step 1: Write the failing tests:**

```python
import logging


@pytest.mark.xfail(strict=True, reason="AUDIT-10-5: label CSS uses word-break: break-word")
def test_audit_10_5_label_css_has_no_property_weasyprint_ignores():
    root = Path(__file__).resolve().parents[2] / "shopify_tool" / "templates"
    for name in ("barcode_label", "qr_label"):
        css = (root / name / "style.css").read_text(encoding="utf-8")
        assert "break-word" not in css
        assert "overflow-wrap: anywhere" in css


@pytest.mark.xfail(strict=True, reason="AUDIT-10-6: expiry '0' logs a warning")
def test_audit_10_6_expiry_zero_means_none_quietly(caplog):
    from shopify_tool.analysis import _parse_expiry_date
    with caplog.at_level(logging.WARNING, logger="shopify_tool.analysis"):
        assert _parse_expiry_date("0") is None
    assert caplog.records == []
```

Check the expiry parser's real name and signature first (`grep -n "def _parse_expiry_date" shopify_tool/analysis.py`). If it takes more arguments, pass the minimal ones. For AUDIT-10-7, change the existing `test_when_painted_gives_up_at_the_timeout_and_says_so` in `tests/test_web_page.py`. Capture at `logging.INFO`, and add `assert all(r.levelno == logging.INFO for r in caplog.records if "did not report" in r.getMessage())`. Mark it xfail AUDIT-10-7 until the fix.

The real WeasyPrint check (a label rendered with a long product name logs no `weasyprint` warning) is better still, if `tests/test_label_templates.py` already renders labels. Add it there as a second test for AUDIT-10-5, capturing the `weasyprint` logger at WARNING.

- [ ] **Step 2:** Run. XFAIL. **Step 3:** Commit the tests.
- [ ] **Step 4: Fix.**
  - Both CSS files, line 90: replace `word-break: break-word;` with `overflow-wrap: anywhere;`.
  - `_parse_expiry_date`: change `if not s or s == "1":` to `if not s or s in ("0", "1"):`. Extend the comment above it: "0" and "1" are placeholders some exports write for "no expiry" (production log, 2.3.1).
  - `shared/web_page.py`: change `logger.warning(` in the `timed_out` branch to `logger.info(`. Add the comment: "Handled: the action runs anyway. On the warehouse PCs a large Results frame takes longer than the cap, which is nothing an operator or a log reader can act on (AUDIT-10-7)."
- [ ] **Step 5:** Remove the markers. Run the audit file, `tests/test_web_page.py`, `tests/test_label_templates.py`, `tests/test_analysis.py` and `tests/test_shell.py`. All PASS.
- [ ] **Step 6:** Bug-log sections for AUDIT-10-5, -6 and -7, each with its production log line and count (×110, ×11, ×10, last seen 2026-10-09, 2.3.1) and the fix. Commit ("AUDIT-10-5..7: the warnings production still logs").

---

## Part A: coverage

Measure with `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q --cov=shopify_tool --cov=gui --cov=shared --cov-report=term-missing` (background, about 10 minutes). For one module, run only its test files with `--cov=<package.module>` to iterate quickly.

Rules for every test in this part (spec Part A):
- Assert a behaviour a user or caller relies on: a value returned, a file written, a row restored, a signal emitted. Never only that a line ran.
- Bugs become `AUDIT-10-8`, `-9`, …: strict xfail test, commit, fix, remove the marker, commit, bug-log section. Something you cannot classify as bug or intent goes into the bug log under "Open questions", unfixed.
- No `pragma: no cover`. A branch that cannot run on Linux goes into the coverage table with its reason.

### Task 11: delete the dead code

**Files:** `shopify_tool/core.py`, `shopify_tool/sku_writeoff.py`, `shopify_tool/tag_manager.py`, `gui/client_settings_dialog.py`, and the tests of deleted functions.

- [ ] **Step 1:** For each symbol, run `grep -rn "<name>" gui shopify_tool shared tests scripts gui_main.py docs/audit/repro`, and in packing-tool for `shared/` symbols (none here). Symbols: `create_packing_list_report`, `create_stock_export_report`, `create_writeoff_report` (core), `generate_writeoff_report`, `apply_writeoff_to_stock_export` (sku_writeoff), `get_tag_category_cached`, `get_config_hash` (tag_manager), `ClientSelectorWidget` (client_settings_dialog). Expected: references only in their own definitions, their docstrings, and tests of those very functions. If any other caller shows up, keep that symbol and say so in the bug log.
- [ ] **Step 2:** Delete the functions, the imports only they used (ruff reports unused imports), and the tests that test only them (`tests/test_sku_writeoff.py` has at least one). Keep `calculate_writeoff_quantities` and `_extract_writeoff_mappings`, which `stock_export` uses.
- [ ] **Step 3:** Run `ruff check .` and the gate (background). PASS, apart from the known ZPL three.
- [ ] **Step 4:** Commit ("Coverage: remove dead report and helper code"), listing the symbols in the message.

### Task 12: `undo_manager` to 80%

**Files:** Test: `tests/test_undo_roundtrip.py` (new).

Every undoable edit, done through the app's own path and undone, gives back the frame it started from. Use the `main_window` fixture and `_open_with_state` from `tests/test_stale_session.py`, and this frame:

```python
FRAME = pd.DataFrame({
    "Order_Number": ["#1001", "#1001", "#1002", "#1003"],
    "SKU": ["A", "B", "A", "C"], "Product_Name": ["PA", "PB", "PA", "PC"],
    "Quantity": [1, 2, 1, 3], "Stock": [10, 10, 10, 10],
    "Order_Fulfillment_Status": ["Fulfillable"] * 4,
    "Tags": ["", "", "VIP", ""], "Internal_Tags": ["[]", "[]", '["BOX"]', "[]"],
    "Status_Note": ["", "", "", ""],
})
```

- [ ] **Step 1:** Write one parametrised test over these edits. Read each `ActionsHandler` method first, for its exact arguments and for whether it asks a `ConfirmDialog` (patch it as `_confirm` in `tests/test_save_session_queue.py` does):

```python
EDITS = [
    ("toggle", lambda h: h.toggle_fulfillment_status_for_order("#1002")),
    ("bulk_status", lambda h: h.bulk_change_status(["#1001", "#1003"], False)),
    ("bulk_add_tag", lambda h: h.bulk_add_tag(["#1001", "#1003"], "BOX")),
    ("bulk_remove_tag", lambda h: h.bulk_remove_tag(["#1002"], "BOX")),
    ("add_internal_tag", lambda h: h.add_internal_tag("#1001", "BOX")),
    ("remove_internal_tag", lambda h: h.remove_internal_tag("#1002", "BOX")),
    ("remove_line", lambda h: h.remove_line("#1001", 1, "B")),
    ("change_quantity", lambda h: h.change_line_quantity("#1003", 0, "C", 1)),
    ("remove_order", lambda h: h.remove_entire_order("#1002")),
    ("bulk_remove_sku", lambda h: h.bulk_remove_sku_from_orders(["#1001", "#1002"], "A")),
    ("bulk_remove_orders_with_sku", lambda h: h.bulk_remove_orders_with_sku(["#1001", "#1002"], "A")),
    ("bulk_delete", lambda h: h.bulk_delete_orders(["#1003"])),
]
COMPARED = ["Order_Number", "SKU", "Quantity", "Order_Fulfillment_Status", "Tags", "Internal_Tags"]


@pytest.mark.parametrize(("name", "edit"), EDITS, ids=[e[0] for e in EDITS])
def test_undo_gives_back_the_frame_before_the_edit(main_window, name, edit):
    _open_with_state(main_window, FRAME)
    before = main_window.analysis_results_df[COMPARED].reset_index(drop=True).copy()
    edit(main_window.actions_handler)
    assert not main_window.analysis_results_df[COMPARED].reset_index(drop=True).equals(before), "edit did nothing"
    ok, _ = main_window.undo_manager.undo()
    assert ok
    after = main_window.analysis_results_df[COMPARED].reset_index(drop=True)
    pd.testing.assert_frame_equal(after, before, check_dtype=False)
```

An undo that restores rows in another order is a bug if the Results table shows them in another order. Check `_reinsert`, and log it as AUDIT-10-k if so. If row order is not part of the contract, compare sorted by `Order_Number` and `SKU` instead, and write down why in the test's docstring.
- [ ] **Step 2:** Add: `undo()` with nothing to undo returns `(False, <message>)`; `record_operation` past `max_history` drops the oldest; `_load_history` on a corrupt `operations_history_<PC>.json` starts empty and logs; history written by one PC is read back by `reload_session_history`.
- [ ] **Step 3:** Run with `--cov=shopify_tool.undo_manager`. Iterate until ≥80%. Handle failures per the rules above. Commit.

### Task 13: `core` to 80%

**Files:** Test: `tests/test_core_inputs.py` (new).

- [ ] **Step 1:** `_load_and_validate_files` error paths. Each test writes real files to `tmp_path`:
  - a stock file with a broken quote raises `pd.errors.ParserError`, and `run_full_analysis` returns `(False, "CSV parsing error: …", None, None)`;
  - a missing file → `FileNotFoundError` → `"File not found: …"`;
  - a stock file in cp1251 bytes (`"Артикул".encode("cp1251")`) → `UnicodeDecodeError`, surfaced as `"Analysis failed: …"` (or whatever `run_full_analysis` maps it to: read the code, and assert that);
  - orders missing a required column → `ValueError` → `"Validation error: …"`, naming the column.
- [ ] **Step 2:** `_validate_and_prepare_inputs`: legacy mode (no session manager) writes into `output_dir_path`; session mode without `session_path` creates a session; a given `session_path` is reused.
- [ ] **Step 3:** `validate_csv_headers` and `_validate_dataframes`: missing column, wrong delimiter, empty file, memory-mode stock (`_stock_from_memory`) skipping the CSV-name check.
- [ ] **Step 4:** `_save_results_and_reports`: a `PermissionError` while writing `current_state.pkl` is logged, and the run still writes `analysis_data.json` (monkeypatch `pd.DataFrame.to_pickle` to raise).
- [ ] **Step 5:** Run with `--cov=shopify_tool.core` until ≥80%. Commit.

### Task 14: `groups_manager` and `groups_management_dialog` to 80%

**Files:** Test: `tests/test_groups_manager.py` (extend), `tests/test_groups_management_dialog.py` (new).

- [ ] **Step 1 (manager):** `update_group` renames and recolours and returns the group; `update_group` of an unknown id raises `GroupsManagerError`; `delete_group` with a profile manager moves that group's clients to no group (`profile_manager.get_ui_settings(c)["group_id"] is None`); `get_clients_in_group` lists exactly the clients whose `ui_settings.group_id` matches; `load_groups` on a corrupt `groups.json` returns the default structure and logs. Read `load_groups` to see what it actually returns, and assert that.
- [ ] **Step 2 (dialog):** Construct `GroupsManagementDialog(GroupsManager(...), profile_manager)` with the `profile_manager` fixture from `tests/conftest.py`. Patch `QInputDialog.getText` and `QColorDialog.getColor` on the dialog's module, `gui.groups_management_dialog`, to return fixed answers. Test create (a group appears in the manager and in the list widget), edit (renamed), delete (patch the confirm the dialog uses; the group is gone and its clients unassigned), and cancel at each prompt (nothing changes). Use `qtbot.addWidget(dialog)` and never call `exec()`.
- [ ] **Step 3:** Run with `--cov=shopify_tool.groups_manager --cov=gui.groups_management_dialog` until both are ≥80%. Commit.

### Task 15: `client_settings_dialog` to 80%

**Files:** Test: `tests/test_client_settings_dialog.py` (new).

- [ ] **Step 1:** `ClientCreationDialog(profile_manager, groups_manager)`: an empty id or a duplicate id keeps the dialog open and shows the inline message (read `validate_and_accept` for how), and a valid id creates `CLIENT_<ID>` with its name and group. Patch `QColorDialog.getColor` for the colour button.
- [ ] **Step 2:** `ClientSettingsDialog(client_id, profile_manager, groups_manager)`: it loads the client's name, colour, badges and group into its fields (`_load_data`). Saving writes them through `update_ui_settings` / `save_client_config` (`_save_and_accept`, `_on_save_result`). A failed save (monkeypatch `update_ui_settings` to raise `ProfileManagerError`) keeps the dialog open and reports it. The statistics tab shows the client's session count (`_create_statistics_tab`). Read each method before writing its test.
- [ ] **Step 3:** Run with `--cov=gui.client_settings_dialog` until ≥80%. Commit.

### Task 16: `profile_manager`, `profile_migrations`, `tag_manager`, `sku_writeoff` to 80%

**Files:** Tests: extend `tests/test_profile_manager.py`, `tests/test_profile_migrations.py`, `tests/test_tag_manager.py`, `tests/test_sku_writeoff.py`.

- [ ] **Step 1 (profile_manager):** `add_set` then `get_set_decoders` contains it; `add_set` of an existing SKU replaces it (or refuses: read the code); `delete_set` of an unknown SKU returns False; `save_set_decoders` round-trips; `load_client_config` on invalid JSON returns None and logs; `calculate_metadata` counts the client's sessions; `update_last_accessed` writes a timestamp; `list_clients` ignores folders that are not `CLIENT_*`.
- [ ] **Step 2 (migrations):** For `migrate_tag_categories_v1_to_v2` and `migrate_delimiter_config_v1_to_v2`, take a v1 config literal (find one in the tests or the function's docstring). Check that the migration returns True, produces the v2 shape and is idempotent (a second call returns False and leaves the config equal). `migrate_column_mappings_v1_to_v2` on an already-v2 config returns False.
- [ ] **Step 3 (tag_manager):** `validate_tag_categories_v2`: valid config → `(True, [])`; each error class it checks (read the function) → `False` with a message naming the category.
- [ ] **Step 4 (sku_writeoff):** `calculate_writeoff_quantities` with two tags mapping to one SKU sums them; a tag with no write-off mapping adds nothing; an empty frame returns an empty frame with the expected columns.
- [ ] **Step 5:** Run with `--cov` for the four modules until each is ≥80%. Commit.

### Task 17: `shared/file_lock`, `server_connection`, `metadata_utils` to 80%

**Files:** Tests: `tests/test_file_lock.py`, `tests/test_server_connection.py`, `tests/test_metadata_utils.py` (new or extended; `tests/` holds the `shared/` tests, per CLAUDE.md).

- [ ] **Step 1 (metadata_utils):** Copy `../packing-tool/tests/test_metadata_utils.py`, from the packing-tool worktree named in your Context, to `tests/test_metadata_utils.py`. Read it first and adapt the imports. Add tests for `parse_timestamp` (aware, naive, `Z`, garbage → None) if they are missing.
- [ ] **Step 2 (file_lock):** `locked_file` on Linux: two handles on one file, where the second times out with `FileLockError` after `timeout` and succeeds once the first is released. The Windows branch: monkeypatch the module's platform check and a fake `msvcrt` with `locking` that raises `OSError` twice and then succeeds, to prove the retry loop. Read the module for how it chooses the branch. If the branch is chosen at import time and cannot be driven, record it in the coverage table with that reason.
- [ ] **Step 3 (server_connection):** `ConnectionSettingsDialog` with a reachable `tmp_path`: entering it and accepting saves it (`get_saved_server_path(org)` returns it; use a throwaway `org` name and clean up its QSettings key). An unreachable path keeps the dialog open with its message (patch `test_path_reachable` to return False). `prompt_for_recovery_path` with patched dialog results: retry succeeds → True; cancel → False. Browse: patch `QFileDialog.getExistingDirectory`.
- [ ] **Step 4:** Run with `--cov=shared.file_lock --cov=shared.server_connection --cov=shared.metadata_utils` until each is ≥80%. Commit. In the PR, note that these are tests of `shared/`; packing-tool picks up only the code changes from Task 10.

### Task 18: CI gate, bug log, final check

**Files:** `.github/workflows/build_release.yml:58`, `docs/audit/10-coverage-and-snapshot.md`.

- [ ] **Step 1:** Run the full coverage measurement (background). Fill the "After" column of the bug log's coverage table and the total. Every listed module must be ≥80%. If one is not, go back to its task.
- [ ] **Step 2:** In `build_release.yml`, change the test step's `run: python -m pytest` to `run: python -m pytest --cov=shopify_tool --cov=gui --cov=shared --cov-report=term --cov-fail-under=<N>`, where N is the measured total rounded down to a whole number. Keep its `env`.
- [ ] **Step 3:** `graphify update .`, `ruff check .` and the full gate. Expected: everything passes except the three known ZPL tests. No `xfail` with an AUDIT-10 reason remains (`grep -rn "AUDIT-10" tests | grep xfail` is empty).
- [ ] **Step 4:** Read the bug log once from top to bottom. Every AUDIT-10 id needs a section with where it was found, the cause, the fix and its test, and the open questions are listed. Commit ("Audit 10: coverage gate and bug log").
- [ ] **Step 5:** PR body checklist (Stage C writes the PR):
  - the `shared/web_page.py` change reaches packing-tool at its next sync;
  - the Packer side of 2.1 is in the packing-tool task;
  - ADR 0019 changes what the Packer sees in `packing_lists/` (a `withdrawn/` subfolder it ignores);
  - fixtures are anonymised, and the builder plus the PII guard are how;
  - coverage before/after.
