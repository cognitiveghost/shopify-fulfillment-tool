# Next session: plan groups B, D, E, F and G of audits 07–09

Paste everything below the line into a new Claude Code session on this repo. Merge PR #369 first: it holds the
overview plan this session builds on, and the group A fixes.

---

You are writing the implementation plan for the remaining fixes from three audits of this repo (Fulfilment Tool,
PySide6, Windows production on a slow SMB file server, multi-PC). **This session writes the plan only: no product
code and no test changes.** The owner will execute the plan later and review each group's PR.

Read `CLAUDE.md` first and follow it: the git rules (PR-only, branch from `origin/main`) and the token budget note.
This account runs on a limited budget, so avoid subagents unless asked, and read code in targeted slices.

## Where things stand

- **Step 1 is done** (PR #368). Every High and Medium finding has a strict-xfail test in
  `tests/audit/test_07_core_io.py`, `test_08_rules_undo.py` and `test_09_outputs_sets_ledger.py`. Shared fixtures
  live in `tests/audit/audit_support.py`. Do not add a `tests/audit/conftest.py`: it shadows `tests/conftest.py`.
- **Step 2 and group A are done** (PR #369). The overview plan is
  `docs/superpowers/plans/2026-10-05-audit-07-09-fixes.md`. It holds the owner decisions, each group's findings,
  files, tests and risk, and the Step 4 coverage targets. Group A fixed 07-H1, 07-M6, 08-U1 and 07-M7.
- **Group C is deferred** to issue #370 (07-M2, M3, M4, 09-O5). Do not plan it. Where another group touches the
  same files (`core.py`, `fulfillment_history.py`), leave its fixes to #370.
- Baseline after #369: 3,588 passed, 22 xfailed, ruff clean.

## This session

Write **one combined plan**: `docs/superpowers/plans/<today>-audit-07-09-groups-b-d-g.md`. Use the
`superpowers:writing-plans` skill and its header, Global Constraints and Review Focus sections. Then open one PR
with that file and stop.

| Group | Findings | What the plan must settle |
|---|---|---|
| B, session index | 07-H3, 07-H4 | How staleness is detected without counting stray folders, and how one changed entry is refreshed without rereading every `session_info.json` |
| D, speed in the run | 09-O1, 09-O2, 08-R1, 08-R2 | The vectorised shape of set decoding, the packing JSON builder, order-level rules and date parsing; moving report generation to a `Worker` with no UI calls from it |
| E, per-edit I/O | 07-H2, 08-U2, 07-M5, 07-L1 | **Opens with a short design note** (below), then the tasks |
| F, allocation rules | 07-M1, 09-O3, 09-O4, 08-R3, 08-R4 | Apply the owner decisions exactly. Tighten the 07-M1 and 09-O3 xfail tests to assert the chosen rule. Include the ADR 0015 update and the test that no stock export holds a negative quantity |
| G, low items | 07-L2–L6; 08-R5, U4, U5, T1; 09-O6, O7, O8 | One task per item, each with its own test where it has behaviour. Confirm 07-L3 has no caller before deleting it |

### What the plan contains

- One section per group. **Each group is one PR**, branched from `origin/main`, that passes the gate on its own.
- Bite-sized TDD tasks. For an existing finding: run its xfail test with `--runxfail` and see it fail on its own
  assertion, fix, see it pass, remove the marker. For new behaviour: the new test's name and assertions, as code,
  with exact values.
- For each code step: the exact file, function and signature. Check every path, name and line reference against
  `origin/main` as it is after #369. The audits' line numbers have drifted.
- An **execution order** for the five PRs, with reasons, and the **file overlaps** between them (for example,
  `rules.py` in D and F, `core.py` in D and E, `actions_handler.py` in D, E and F), so that PRs merged one after
  another don't conflict.
- Per-group **risk**, and what the PR description must warn the owner about. F changes which lots ship first, and
  R4 makes rules that never matched start matching.
- Coverage: each group adds tests for the code it touches (Step 4 in the overview plan). The closing coverage PR
  is not part of this plan.
- Proportion: signatures, test names and assertions, not function bodies. A body appears only for an algorithm the
  signature and tests do not determine, such as the 07-M1 lot netting or the E coalescing queue.

### Group E design note (the first part of the E section)

Apply the 07-H2 owner decision and settle:

1. What stays on the click: only `current_state.pkl`, through `session_state.save_state`.
2. The per-session coalescing background queue for history, inventory memory, `analysis_stats.json` and
   `session_info`. Cover the thread it runs on, how a newer write replaces a pending one, the order between
   sessions, the flush on session switch and on app close, and how a failure reaches the person (a signal to the
   GUI thread, never a UI call from the worker).
3. Removing `current_state.xlsx` from edits and from the run, and the open-session fallback to
   `fulfillment_analysis.xlsx`.
4. 08-U2: the new undo record format (changed columns plus positions for status, tag and quantity edits; whole rows
   only for removals), and how history files in the old format still load.
5. 07-M5: no backup for inventory-memory-only saves, or a separate rotation. Pick one and say why.
6. 07-L1: prune or append `fulfillment_history.csv` instead of rewriting it whole. Leave the retry-backoff part of
   07-M4 to #370.

## Owner decisions (2026-10-05)

Already recorded in the overview plan. Do not ask them again.

| Finding | Decision |
|---|---|
| 07-M1 | A negative stock row is subtracted from the lot with the same expiry and batch first, and any remainder from the oldest lots. Lot totals always equal the SKU total. **Also:** rows with no expiry and no batch are drawn **first**, and the dated or batched lots only after them, earliest expiry first. Today `_build_fifo_lots` sorts no-expiry rows **last**, so this changes existing allocation: update ADR 0015 and say so in the PR. **The stock export must never contain a negative quantity**; add a test for that. |
| 09-O3 | Allow force-fulfil and bulk "mark fulfillable" on a SKU missing from the stock file, with a warning toast that names the SKU. Do not refuse. |
| 08-R4 | Every text operator (`equals`, `does not equal`, `starts with`, `ends with`, `contains`, `in list`) ignores case and trims whitespace on both sides. |
| 07-H2 | Only `current_state.pkl` is written on the click. History, inventory memory, `analysis_stats.json` and `session_info` move to a per-session coalescing background queue, never touching the UI from the worker thread. **Stop writing `current_state.xlsx`** on edits and in the run: the pickle is the state. Opening a session falls back to `fulfillment_analysis.xlsx`. |

08-R3 has no owner decision because the report already states the fix: the Rules page shows the order the engine
runs. If the plan needs any new decision, ask the owner before writing that part, rather than choosing yourself.

## Inputs

- Reports: `docs/audit/07-core-io-review.md`, `08-rules-undo-review.md`, `09-outputs-sets-ledger-review.md`. Read
  each "Verification, 2026-10-05" section.
- Repro scripts: `docs/audit/repro/*.py`. Run with `.venv/bin/python docs/audit/repro/<file>.py`.
- The xfail tests named in the overview plan, per group.
- `docs/adr/` (0008 last-writer-wins, 0010 stock left, 0011 stale check, 0015 lots) and `CONTEXT.md`.

## Environment

- If `.venv` is missing or `./scripts/setup_venv.sh` fails on an old system Python (audit 08 T1), build it with
  `uv venv --python 3.14 .venv` and
  `uv pip install --python .venv/bin/python -r requirements.txt -r requirements-dev.txt`.
- Gate for code PRs: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` and `.venv/bin/ruff check .`.
  This session changes docs only, so run `ruff check .`. The suite needn't run.

## Done means

- The combined plan is in `docs/superpowers/plans/`, and one PR holds it.
- It covers B, D, E (with its design note), F and G, each as its own PR-sized section, with an execution order.
- Every finding in those groups maps to a task with a named test.
- The owner can execute it group by group and review each PR.
