# Next session: verify, plan and fix audits 07–09

Paste everything below the line into a new Claude Code session on this repo.

---

You are fixing the findings of three report-only audits of this repo (Fulfilment Tool, PySide6, Windows
production on a slow SMB file server, multi-PC). Read `CLAUDE.md` first and follow it, including the
gate, the git rules (PR-only, branch from `origin/main`) and the token budget note: this account runs on
a limited budget, so keep each session to one fix group and avoid subagents unless asked.

## Inputs

- `docs/audit/07-core-io-review.md`: analysis run, per-edit save path, config, session index, `shared/` writes
- `docs/audit/08-rules-undo-review.md`: rule engine, undo
- `docs/audit/09-outputs-sets-ledger-review.md`: set decoding, Packing Tool JSON, stock ledger, exports
- `docs/audit/repro/*.py`: one script per reproduced finding. Run with `.venv/bin/python docs/audit/repro/<file>.py`.
- Convention from audits 01–06 (`tests/audit/test_01_*.py` … `test_06_*.py`): every finding gets a test
  named for it (`AUDIT-07-H1`, `AUDIT-08-U1`, …), marked `xfail(strict=True)` until the fix lands; the
  fix removes the marker. Tests that pin verified-correct behaviour stay unmarked.

## Environment

- If `.venv` is missing or `./scripts/setup_venv.sh` fails on an old system Python (audit 08 T1), build
  it with `uv venv --python 3.14 .venv` and
  `uv pip install --python .venv/bin/python -r requirements.txt -r requirements-dev.txt`.
- Gate: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` and `.venv/bin/ruff check .`
  (baseline when the audits were written: 3,571 passed, ruff clean).
- Coverage: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q --cov=shopify_tool --cov=shared --cov-report=term-missing`.

## Step 1: verify (one session, no product code)

1. Run every script in `docs/audit/repro/` and confirm the output still matches the report.
2. For each High and Medium finding, write its `xfail(strict=True)` test in
   `tests/audit/test_07_core_io.py`, `test_08_rules_undo.py` and `test_09_outputs_sets_ledger.py`.
   Timing findings (07-H2, 08-R1, 08-R2, 08-U2, 09-O1, 09-O2) get a test with a generous ceiling on the
   benchmark frame from the repro scripts (for example, set decoding of 15,000 lines under 1 s), not a
   tight micro-benchmark.
3. Mark any finding that no longer reproduces as such in its report, with the evidence.
4. One PR: the tests plus report updates. The suite must stay green (xfails count as expected).

## Step 2: plan

Write `docs/superpowers/plans/<date>-audit-07-09-fixes.md` with the fix groups below, each with its
tests, files and risk. Ask the owner the open decisions first and record the answers in the plan:

- 07-M1: how negative stock rows count when the stock file has lot columns
- 09-O3: whether force-fulfil may mark an order whose SKU is missing from the stock file
- 08-R4: one case and whitespace rule for all text operators
- 07-H2: what may move off the GUI thread after a save, and whether `current_state.xlsx` is still needed

## Step 3: fix, one PR per group (TDD: the xfail test goes green, then remove the marker)

| Group | Findings | Notes |
|---|---|---|
| A, data safety | 07-H1, 07-M6, 08-U1, 07-M7 | small; stop config loss and undo duplication first |
| B, session index | 07-H3, 07-H4 | count only real sessions; refresh changed entries only |
| C, atomic and honest saves | 07-M2, 07-M3, 07-M4, 09-O5 | reuse `shared/atomic_write.py` and `session_state.save_state` |
| D, speed in the run | 09-O1, 09-O2, 08-R1, 08-R2 | vectorise; the existing tests pin behaviour |
| E, per-edit I/O | 07-H2, 08-U2, 07-M5, 07-L1 | needs the Step 2 decision; design note first |
| F, allocation rules | 07-M1, 09-O3, 09-O4, 08-R3, 08-R4 | owner decisions from Step 2 |
| G, low items | everything marked Low | batch into one or two PRs |

`shared/` changes (07-M4) reach packing-tool at its next sync; say so in the PR (see `CLAUDE.md`).

## Step 4: coverage (part of every group, and a final pass)

Raise coverage where the audits found untested paths. Each PR adds tests for the code it touches. Then
one closing PR reaches at least:

- `shopify_tool/undo_manager.py`: 90% (55% at audit time). Cover every `_undo_*` handler, the
  wrong-client and wrong-session guard, a corrupt history file, and undo across an analysis re-run.
- `shopify_tool/rules.py`: 90% (77% at audit time). Cover `date after`, every `CALCULATE` branch,
  `ADD_PRODUCT` with a known SKU, and the order fields `total_quantity`, `unique_sku_count`,
  `max_quantity`, `order_volumetric_weight`, `all_no_packaging`, `has_product`.
- The modules listed under "Coverage at audit time" below that sit under 80% and hold allocation,
  saving or export logic.

Assert on outcomes (frame contents, files on disk, returned values), not on mocks being called. Use the
synthetic fixtures style from `tests/audit/` and never production data.

## Coverage at audit time

COVERAGE_TABLE

## Done means

Every High and Medium finding is fixed or carries a recorded owner decision. Its test is unmarked and
green. The coverage targets above are met. Every PR passed the gate, and `graphify update .` was run
after code changes (see `CLAUDE.md`).
