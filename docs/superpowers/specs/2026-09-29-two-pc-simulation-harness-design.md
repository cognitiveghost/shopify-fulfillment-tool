# Two-PC simulation harness — design

**Task:** dr-9, "Can we try to do a manual test of both apps?" Fulfilment Tool and Packer's Assistant run as a live
test on several PCs sharing one server, for Claude to hunt bugs in.
**Path:** architectural (new subsystem spanning both repos). No UI changes, no mockup.
**Owner decisions (2026-09-29):** a headless scenario harness, not visual GUI driving or a Windows VM runbook. Deliver
the harness plus one bug-hunt run, with each bug filed as a GitHub issue and fixes left to separate tasks. Cover all four
scenario groups. The server is a local temp folder.

## Can it be recreated in a VM?

It can't be done in *this* VM. The dev box is a VirtualBox guest with no nested virtualisation (no `vmx`/`svm`), 4
cores, 11 GB, no sudo, and no display in runner sessions. A faithful Windows rig (2 Windows VMs + an SMB share) would
have to live on the host machine and be driven by hand.

What *can* run here is every real line of both apps, headless, as several simulated PCs on one shared folder:

- Each app names its PC from `COMPUTERNAME`/`USERNAME` (`session_manager.py`, `profile_manager.py`,
  `packer_logic.py`, registry). Packer's session lock keys on `socket.gethostname()` **plus PID**
  (`session_lock_manager.py:103`), so two processes on one host are two lock owners.
- Per-machine state is QSettings plus the home directory. A process with its own `HOME` and `XDG_CONFIG_HOME` gets
  its own "PC".
- Both apps already run on Linux against a local folder (`run_dev.py` in each repo).

**Known blind spot:** a local ext4 folder is not an SMB share. Rename-over-existing, byte-range locks, mtime
granularity and directory-listing caching all differ (ADR 0008 was an SMB-only bug). The harness finds logic and
concurrency bugs, not SMB-semantics bugs. Swapping in a Samba container later only changes the server path, so it
stays possible.

## What already exists (and is not redone)

`tests/audit/` in both repos pins many two-PC cases **in-process**: fulfilment AUDIT-05 (stale save, session-name
collision), packer AUDIT-02 (lock race, registry writers, takeover). The harness adds what those can't: **separate OS
processes** running the **real MainWindows** end to end across **both apps**, real timers and heartbeats, and real
`kill -9`.

## Architecture

Everything lives in `shopify-fulfillment-tool/sim/`. That repo owns the dev server, and the pipeline starts there.
Packer's Assistant is found at `../packing-tool` (override `--packing-tool PATH`; from a worktree pass it explicitly,
the same as `sync_shared.py`). There are no changes to either app's code.

```
sim/
  __init__.py
  protocol.py          stdlib only: JSON-lines request/reply helpers, used by both agents and the orchestrator
  agent_common.py      stdlib + PySide6: per-PC Qt event loop, stdin reader thread, dialog/toast capture, log capture
  agent_fulfilment.py  runs under the fulfilment .venv, cwd = this repo; wraps gui.main_window_pyside.MainWindow
  agent_packer.py      runs under packing-tool's .venv, cwd = packing-tool; wraps gui.main_window.MainWindow
  world.py             orchestrator side: temp server, seeding, spawning/killing PCs, the RPC client
  data.py              deterministic synthetic orders/stock CSVs and client config
  invariants.py        post-scenario checks over the server folder (pure functions of a Path)
  scenarios.py         the scenarios, one function each
  run.py               CLI: `python -m sim.run [names...] [--packing-tool P] [--keep] [--list]`
tests/test_sim_invariants.py   the one runnable check: invariants against hand-built good and bad trees
```

### A PC is a process

`world.spawn_pc(name, app)` starts `<app venv>/bin/python -m sim.agent_<app>` (for packer: the packing-tool venv
python, with `PYTHONPATH=<this repo>` appended so `sim.agent_packer` imports while packing-tool's `gui`/`shared`
win on `sys.path` because cwd comes first). The two apps' `gui` and `shared` packages collide by name, so they can
never share a process. Per-PC environment:

| var | value |
|---|---|
| `COMPUTERNAME`, `USERNAME` | the PC name (e.g. `PC-A`), `user-<name>` |
| `HOME`, `XDG_CONFIG_HOME` | `<run dir>/pcs/<name>/home`, `.../home/.config` (isolates QSettings, caches, logs) |
| `QT_QPA_PLATFORM` | `offscreen` |
| `FULFILLMENT_SERVER_PATH` | the temp server (fulfilment reads it; packer gets a `config.ini` in its PC dir, the same shape `packing-tool/run_dev.py` writes, passed as `MainWindow(config_path=...)`) |
| `SIM_FAST_CLOCK` | `1` by default: packer agent sets `SessionLockManager.HEARTBEAT_INTERVAL = 1`, `STALE_TIMEOUT = 4` before building the window |

### Agent protocol

The orchestrator writes one JSON object per line to the agent's stdin: `{"id": n, "op": "scan", "args": {...}}`.
The agent answers with one JSON line on stdout: `{"id": n, "ok": bool, "result": ..., "error": str|null,
"events": [...]}`. Everything else the app prints goes to stderr, which is teed to `<run dir>/pcs/<name>/stderr.log`.
The agent reserves stdout by dup'ing the real fd for the protocol and pointing `sys.stdout` at stderr before importing
the app.

`events` is everything the app told the operator, or complained about, while the op ran:
`{"kind": "dialog"|"toast"|"error_banner"|"log", "level", "title", "text", "answer"}`. Captured by:

- **Dialogs:** patch `QMessageBox.question/warning/information/critical` and `QDialog.exec`. Each returns the answer
  the current op scripted (`args["answers"]`: `{title substring: "yes"|"no"|"accept"|"reject"}`). Otherwise it
  returns No/Reject and the event gets `"unexpected": true`. A modal never blocks the agent.
- **Toasts / error banners:** after the app is imported, walk `sys.modules` and replace every attribute that *is* the
  app's `toast`/`show_error` function with a recorder that also calls through. (Implementer: find the defining
  modules with `rg "def toast|def show_error"` in each repo.)
- **Logs:** a root-logger handler at WARNING and above.
- **Crashes:** `sys.excepthook` and `threading.excepthook` record `{"kind": "exception", traceback}`. Qt slot
  exceptions land there too. The event rides on the next reply, or on a final `{"id": null, ...}` line at exit.

The event loop is `QApplication.exec()`. A daemon thread reads stdin and hands each request to the Qt thread through a
queued signal, so the window's timers (heartbeat, async writers, progress publisher) keep running between ops.
Ops that start background work (`run_analysis`) reply only when that work has finished: the op pumps
`QApplication.processEvents()` until done, with a 120 s timeout that replies `ok: false`.

### Ops (the whole vocabulary)

Fulfilment agent. It builds `MainWindow()`, `show()`, and sets the session browser's `USE_ASYNC = False` like
`tests/audit/test_05_sessions_sweep.py`.

| op | drives |
|---|---|
| `select_client {client_id}` | `mw.current_client_id = id; mw.load_client_config(id)` (the audit fixture's seam) |
| `new_session` → `session_path` | `mw.actions_handler.create_new_session()` |
| `open_session {session_path}` | `mw.load_existing_session(path)` |
| `set_inputs {orders, stock}` | `mw.orders_file_path`, `mw.stock_file_path` (the attributes `run_analysis` reads) |
| `run_analysis` → counts | `mw.actions_handler.run_analysis()`; wait until `mw._analysis_running` is False |
| `generate_packing_lists {lists:[{name, courier}]}` | `mw.actions_handler._generate_reports(batch, mw.session_path)`, one packing-list report per courier; the filter uses the same `{field, operator, value}` shape `_apply_filters` reads |
| `set_fulfillable {order, value}` | `mw.actions_handler.set_order_fulfillable(order, value)` |
| `orders` → `[{order, status, repeat}]` | reads `mw.analysis_results_df` (the repeat flag column the analysis writes) |
| `save_client_setting {key, value}` | read, modify and save the client config through `mw.profile_manager` (the path the settings window uses) |
| `quit` | `mw.close()`, then exit 0 |

Packer agent. It builds `MainWindow(config_path=...)` with `MainWindow._select_worker` patched to pick (creating if
missing) worker `<PC name>` through `WorkerManager`.

| op | drives |
|---|---|
| `start_list {client_id, session_path, list_name}` | `mw._handle_start_packing_from_browser({...})` with `list_file = session/packing_lists/<name>.json`; replies `{started: mw.logic is not None}` |
| `scan {text}` | `mw.on_scanner_input(text)` |
| `pack_order {order}` | scan the order number, then each item's SKU `quantity` times, reading items from `mw.logic` |
| `skip` | `mw._on_skip_order()` |
| `end_session` | `mw.end_session()`; wait for its slow writes (`_do_slow_writes`) to finish |
| `state` → `{completed, skipped, in_progress, lock_owner}` | `mw.logic` plus the lock file |
| `quit` | `mw.close()`, then exit 0 |

The implementer confirms each attribute name against the code before using it. Where one differs, the op keeps its
contract and the plan's task notes the real seam. A missing seam is not built into the app: the op drives the nearest
real public or `_handler` method.

### Orchestrator (`world.py`)

- `World(run_dir, packing_tool)` creates `server/`, seeds client `SIM` through the **fulfilment** `ProfileManager`
  (in a short subprocess under the fulfilment venv, `sim.agent_fulfilment --seed`), and writes the synthetic CSVs to
  `run_dir/inputs/`.
- `pc = world.spawn_pc("PC-A", "fulfilment")`. `pc.call(op, **args)` returns the reply and raises `AgentDied` if the
  process exited. `pc.kill()` sends SIGKILL. `pc.quit()` does a clean exit.
- `world.server_offline()` / `world.server_online()` rename `server/` to `server.offline/` and back.
  `world.readonly(path)` / `world.writable(path)` chmod a subtree.
- Every reply's events go into `run_dir/events.jsonl`, tagged with scenario and PC.

### Synthetic data (`data.py`)

Deterministic (seeded `random.Random(0)`), using the default column mapping from
`ProfileManager._create_default_shopify_config`. Orders use headers `Name, Lineitem sku, Lineitem quantity, Lineitem
name, Shipping Method, Shipping Country, Tags, Notes, Total, Subtotal, Shipping Name, Created at`. Stock uses the
Cyrillic headers `Артикул, Име, Наличност`. The data is 40 orders over 12 SKUs, split across DHL and DPD. A few
orders have multi-quantity lines, a few are multi-line, and 3 are out of stock so that "not fulfillable" is
exercised. There is no production data, in the repo or anywhere else.

### Invariants (`invariants.py`)

Pure functions `check_*(server: Path) -> list[str]` (an empty list means pass), run after every scenario:

1. Every `*.json` under `server/` parses. No torn writes.
2. No leftover temp files (`*.tmp`, `*.tmp.*`, atomic-write temps) once all PCs have quit.
3. No `.session.lock` remains once all packer PCs have quit cleanly. Killed PCs are excluded, and the scenario says
   which ones.
4. For each packing work dir, `packing_state.json`'s completed orders ⊆ the list's orders, with no duplicates.
5. The registry entry's completed count for each list equals `packing_state.json`'s.
6. The Shopify session's `session_info.json` packed-order signal equals the union of completed orders across its
   lists.

Scenario-specific assertions sit beside them in each scenario, through `expect(cond, message)`.

### Scenarios (`scenarios.py`)

Each scenario gets a fresh `World` and has a short docstring saying what a pass means.

**Full pipeline**
- `pipeline` — PC-A (fulfilment) creates a session, runs analysis and generates DHL and DPD lists. PC-B (packer)
  packs all of DHL and ends. PC-A then creates a *new* session on the same orders file and analyses it. Expect every
  DHL order to be flagged a repeat and no DPD order to be flagged.

**Two packers, one client**
- `lock_race` — PC-B and PC-C `start_list` the same list back to back. Expect exactly one `started`, and the other
  to see a "locked" dialog naming the owner.
- `crash_takeover` — PC-B packs 5 orders and is killed with SIGKILL. PC-C starts the same list and answers yes to
  the stale-lock prompt (after `STALE_TIMEOUT` + 1 s). Expect 5 completed on resume, and PC-C finishes the rest.
  After the end, every order in the list is completed exactly once.
- `parallel_lists` — PC-B packs DHL while PC-C packs DPD, interleaved one order at a time, and both end. Expect
  invariants 5 and 6 to hold, with both lists' orders in the packed-order signal.

**Two fulfilment PCs**
- `stale_save` — PC-A and PC-D open the same analysed session. A sets order X not fulfillable, then D sets order Y
  not fulfillable. Expect D's edit to be refused with an operator-visible message, and a reopen on a third
  fulfilment PC to show X held and Y untouched (ADR 0011).
- `same_day_sessions` — PC-A and PC-D run `new_session` concurrently (both requests sent before either reply is
  read). Expect two distinct session dirs, both with `session_info.json`.
- `config_race` — PC-A and PC-D each save a client setting 20 times, interleaved. Expect the config always to parse
  and the final value to be one of the two writers' (ADR 0008).

**Server trouble**
- `server_vanishes_mid_pack` — PC-B is packing when the server goes offline. It scans, and expects an
  operator-visible error and no `exception` event. The server comes back and PC-B scans again. Expect packing to
  continue and invariants 1 and 4 to hold.
- `readonly_end` — the session dir goes read-only before PC-B's `end_session`. Expect a visible error, no exception
  and no partial files. Make it writable and end again, and expect success.
- `killed_mid_analysis` — PC-A starts `run_analysis` and is SIGKILLed about 0.2 s in (async send, sleep, kill). PC-D
  opens that session. Expect a visible message or a clean open, never an exception.

### Findings

A scenario **finds** something when any of these happen: an `expect` fails, an invariant fails, an agent dies
unexpectedly, an `exception` event appears, or an `unexpected` dialog appears. `run.py` prints one line per scenario
(`PASS`/`FIND`), writes `run_dir/report.md` with each finding's scenario, PC, op, message, events and the tail of
that PC's stderr, and exits non-zero on any finding. `run_dir` defaults to `sim-out/<timestamp>/` in the repo root,
which is gitignored. `--keep` keeps the server tree for inspection, and by default it is deleted on PASS.

A harness defect (wrong seam, flaky wait) is not an app bug. The bug-hunt step triages every finding into **app bug**
(file an issue), **harness bug** (fix the harness and re-run) or **by design** (cite the ADR and drop it).

### The bug-hunt run (last step of this task)

1. Run all scenarios. Triage each finding as above, and re-run after harness fixes until only app bugs and by-design
   findings remain.
2. File each app bug as a GitHub issue on the repo that owns the faulty code (`cognitiveghost/shopify-fulfillment-tool`
   or `cognitiveghost/packing-tool`), using `gh issue create`. The title states the symptom. The body gives the
   scenario, the repro (`python -m sim.run <scenario> --packing-tool ../packing-tool`), expected vs. actual, the
   relevant events and log tail, and the suspected code location. No production data.
3. Post the list of issues (or "no app bugs found") in the PR description.

## Error handling

- An agent that fails to start (import error, missing venv) makes that scenario `FIND` with its stderr tail, and the
  other scenarios still run.
- Every `call` has a timeout (default 30 s; 120 s for `run_analysis`). A timeout kills the agent and is a finding.
- The orchestrator always kills its agents in `finally`, so no orphaned Qt processes are left behind.

## Testing

- `tests/test_sim_invariants.py` builds a small good server tree in `tmp_path` (every invariant passes) and one bad
  tree per invariant (exactly that invariant fails). It is pure file I/O, fast, and runs in the normal suite.
- The harness itself is proven by running it: `python -m sim.run pipeline` must pass the pipeline before the other
  scenarios are written. It is not wired into CI, because it needs the sibling packing-tool checkout and its venv.
- The gate is unchanged: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` and `ruff check . --exclude shared`
  (`sim/` is linted).

## Out of scope

- SMB fidelity (Samba container, Windows VMs). The documented upgrade is a server path swap.
- Fixing any bug the run finds. Each becomes its own task.
- Visual GUI driving and screenshots.
- Wiring the harness into CI.
