# Two-PC Simulation Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `sim/`, a harness that runs the real Fulfilment Tool and Packer's Assistant main windows as separate
simulated PCs on one temp server folder. Then run it once and file every app bug it finds as a GitHub issue.

**Architecture:** Each simulated PC is its own OS process, an *agent*. The agent builds that app's real `MainWindow`
offscreen, reads JSON requests on stdin, drives the window through its existing methods, and replies with a JSON
line. The reply carries the result and every dialog, toast, error banner, warning log and exception the app produced.
An orchestrator (`sim/world.py`) spawns and kills agents with per-PC environments (`COMPUTERNAME`, `HOME`, …).
Scenarios (`sim/scenarios.py`) script both apps across several PCs, and pure file checks (`sim/invariants.py`)
validate the server folder afterwards.

**Tech Stack:** Python 3.14 stdlib (`subprocess`, `threading`, `queue`, `json`, `csv`), PySide6 (already a
dependency of both apps). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-29-two-pc-simulation-harness-design.md`. Read it first. It holds the "why",
the op tables and the scenario list.

## Global Constraints

- No change to either app's code (`gui/`, `shopify_tool/`, `shared/`, or anything in packing-tool). Everything new is
  under `sim/`, plus `tests/test_sim_invariants.py`, one `.gitignore` line and one CLAUDE.md section.
- Never hand-edit `shared/`.
- No production data. Everything is synthesised by `sim/data.py`, and `~/Desktop/production info/` is never read.
- Gate: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` and `ruff check . --exclude shared` (so `sim/` is
  linted).
- Use `/usr/bin/git`, one plain git command per Bash call, and `git commit -F <absolute path to message file>`. End
  every commit message with the attribution lines your session's system reminder gives.
- The pytest-guard hook blocks Bash text containing "pytest" in any form other than the plain gate run. If a filtered
  run (`... -m pytest -q tests/test_sim_invariants.py`) is refused, run the full gate instead.
- Packing-tool lives at `/home/gloopy/Desktop/Projects/packing-tool` (its `.venv` is there). From this worktree,
  **always pass `--packing-tool /home/gloopy/Desktop/Projects/packing-tool`** to `sim.run`, because the sibling
  default resolves inside `.claude/worktrees/`.
- The harness only drives the apps through methods that already exist. When an attribute or method named here is
  different in the code, keep the op's contract, use the real seam, and write it down in the task's commit message.
- A harness run is slow (the Qt and WebEngine startup costs a few seconds per PC). Run one scenario at a time while
  building it.

## Review Focus

1. **An agent that hangs on a modal.** If any `exec()` or static `QMessageBox` escapes the patches, the PC blocks
   forever. Every `call` has a timeout that kills the agent and records a finding. Task 2 pins this with the
   `dialog_probe` op and its test step.
2. **Protocol corruption from app prints.** An app `print()` on stdout would break the JSON-lines channel.
   `agent_common` moves fd 1 to stderr *before* the app is imported. Task 2 checks this with the `print_probe` op.
3. **Findings lost between ops.** Heartbeat and async-writer failures happen between requests. Events are buffered
   and ride on the next reply, and scenarios in the server-trouble group deliberately call `state` after a sleep to
   collect them (Task 6).
4. **Killed-PC artefacts misread as app bugs.** Locks and temp files from a SIGKILL'd PC are expected. The lock
   check excludes killed PIDs (Task 1 test). Temp files from a killed PC are triaged, not auto-filed (Task 7).
5. **Two sim PCs share one hostname.** Packer's lock text names `socket.gethostname()` and `os.getlogin()`, which are
   the same for every sim PC. Only the PID differs. Scenarios match on "another PC", never on a PC name inside a
   lock message (Task 5).

---

## File Structure

| file | responsibility |
|---|---|
| `sim/__init__.py` | package marker (one docstring line) |
| `sim/invariants.py` | pure checks over a server folder, returning `list[str]` |
| `sim/data.py` | deterministic synthetic orders/stock CSVs, and `CLIENT` / `COURIERS` constants |
| `sim/agent_common.py` | per-PC plumbing: stdout redirect, dialog/toast/log/exception capture, request loop, `pump_until` |
| `sim/agent_fulfilment.py` | fulfilment PC: builds `gui.main_window_pyside.MainWindow`, fulfilment ops |
| `sim/agent_packer.py` | packer PC: builds packing-tool's `gui.main_window.MainWindow`, packer ops |
| `sim/world.py` | orchestrator: `World`, `PC`, `Reply`, process spawning, server offline/read-only helpers |
| `sim/scenarios.py` | the 10 scenarios plus helpers `analysed_session`, `pack_all`; `ALL` registry |
| `sim/run.py` | CLI entry point and `report.md` writer |
| `tests/test_sim_invariants.py` | the one runnable check of harness logic |

**Departures from the spec, decided here:** there is no `sim/protocol.py`, because the framing is one `json.dumps`
per side and lives in `agent_common.py` and `world.py`. There is no `--keep` flag, because `sim-out/` is gitignored
and always kept. There is no final `{"id": null}` line at exit, because `quit` is itself an op, so its reply carries
the shutdown events. `generate_packing_lists` takes `couriers: list[str]` and names each list `<courier>_Orders`,
instead of the spec's `lists:[{name, courier}]`. `state` does not report the lock owner, because scenarios read
lock files directly. The packer agent also shortens the heartbeat **timer** (hard-coded at 60 s in
`_start_heartbeat_timer`) to 1 s, alongside `STALE_TIMEOUT`. Without that, a live PC's lock would look stale after 4 s.

---

### Task 1: Server invariants

**Files:**
- Create: `sim/__init__.py`, `sim/invariants.py`
- Create: `tests/test_sim_invariants.py`
- Modify: `.gitignore` (append `sim-out/`)

**Interfaces:**
- Produces: `sim.invariants.check_all(server: Path, killed_pids: frozenset[int] = frozenset()) -> list[str]`, plus
  the individual `check_json_parses`, `check_no_temp_files`, `check_no_locks`, `check_packing_state`,
  `check_registry_counts` and `check_packed_signal` with the same shape (the last three take only `server`).

Facts the checks rely on (verified in the code):
- Packing list: `Sessions/CLIENT_<id>/<session>/packing_lists/<list>.json` → `{"orders": [{"order_number": ...}]}`.
- Packer state: `Sessions/CLIENT_<id>/<session>/packing/<list>/packing_state.json` →
  `{"completed": [{"order_number": ...}], "completed_off_list": [...]}`.
- Lock: `.../packing/<list>/.session.lock` (JSON, has `process_id`).
- Registry: `Sessions/CLIENT_<id>/registry_index.json` → `{"sessions": {"<session>::<list>": {"completed_orders":
  <int>}}}`.
- Packed-order signal: `<session>/session_info.json` → `{"packing_progress": {"<list>": {"completed_orders":
  [...]}}}`.
- Atomic-write temps: `.<stem>_tmp_XXXX<suffix>` (`shared/atomic_write.py`), plus `*.tmp` (`stock_export.py`).

- [ ] **Step 1: Write the failing test**

`tests/test_sim_invariants.py`:

```python
"""The simulation harness's server checks: a sound tree passes, each fault is caught."""

import json
from pathlib import Path

from sim import invariants

LIST = "DHL_Orders"
SESSION = "2026-09-29_1"


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _tree(root, completed=("#1001",), signal=("#1001",), registry_count=1, lock_pid=None):
    client = root / "Sessions" / "CLIENT_SIM"
    session = client / SESSION
    work = session / "packing" / LIST
    _write(session / "packing_lists" / f"{LIST}.json",
           {"orders": [{"order_number": "#1001"}, {"order_number": "#1002"}]})
    _write(work / "packing_state.json",
           {"completed": [{"order_number": o} for o in completed], "completed_off_list": []})
    _write(session / "session_info.json",
           {"packing_progress": {LIST: {"completed_orders": list(signal)}}})
    _write(client / "registry_index.json",
           {"sessions": {f"{SESSION}::{LIST}": {"completed_orders": registry_count}}})
    if lock_pid is not None:
        _write(work / ".session.lock", {"process_id": lock_pid})
    return root


def test_a_sound_tree_passes(tmp_path):
    assert invariants.check_all(_tree(tmp_path)) == []


def test_a_torn_json_file_is_caught(tmp_path):
    server = _tree(tmp_path)
    (server / "Sessions" / "CLIENT_SIM" / "registry_index.json").write_text('{"sessions": {', encoding="utf-8")
    assert invariants.check_json_parses(server)


def test_a_temp_file_is_caught_and_not_parsed_as_json(tmp_path):
    server = _tree(tmp_path)
    (server / "Sessions" / ".session_info_tmp_ab12.json").write_text("{", encoding="utf-8")
    assert invariants.check_no_temp_files(server)
    assert invariants.check_json_parses(server) == []


def test_a_lock_left_by_a_live_pc_is_caught(tmp_path):
    assert invariants.check_no_locks(_tree(tmp_path, lock_pid=4242))


def test_a_lock_left_by_a_killed_pc_is_allowed(tmp_path):
    assert invariants.check_no_locks(_tree(tmp_path, lock_pid=4242), frozenset({4242})) == []


def test_a_completed_order_not_on_the_list_is_caught(tmp_path):
    server = _tree(tmp_path, completed=("#1001", "#9999"), signal=("#1001", "#9999"), registry_count=2)
    assert invariants.check_packing_state(server)


def test_an_order_completed_twice_is_caught(tmp_path):
    server = _tree(tmp_path, completed=("#1001", "#1001"), registry_count=2)
    assert invariants.check_packing_state(server)


def test_a_registry_count_that_disagrees_is_caught(tmp_path):
    assert invariants.check_registry_counts(_tree(tmp_path, registry_count=2))


def test_a_packed_signal_that_disagrees_is_caught(tmp_path):
    assert invariants.check_packed_signal(_tree(tmp_path, signal=()))
```

- [ ] **Step 2: Run it to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_sim_invariants.py`
Expected: collection error `ModuleNotFoundError: No module named 'sim'`.

- [ ] **Step 3: Write the implementation**

`sim/__init__.py`:

```python
"""Two-PC simulation harness: see docs/superpowers/specs/2026-09-29-two-pc-simulation-harness-design.md."""
```

`sim/invariants.py`:

```python
"""Checks over a simulated server folder once a scenario's PCs have stopped.

Each check returns the problems it found; an empty list is a pass. Pure file
reads and no app imports, so the harness and the test suite share them.
"""

import json
from pathlib import Path

TEMP_GLOBS = (".*_tmp_*", "*.tmp")


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _is_temp(path: Path) -> bool:
    return any(path.match(glob) for glob in TEMP_GLOBS)


def check_json_parses(server: Path) -> list[str]:
    problems = []
    for path in sorted(server.rglob("*.json")):
        if _is_temp(path):
            continue  # check_no_temp_files reports it
        try:
            _json(path)
        except (OSError, ValueError) as exc:
            problems.append(f"torn JSON {path.relative_to(server)}: {exc}")
    return problems


def check_no_temp_files(server: Path) -> list[str]:
    return [
        f"leftover temp file {path.relative_to(server)}"
        for path in sorted(server.rglob("*"))
        if path.is_file() and _is_temp(path)
    ]


def check_no_locks(server: Path, killed_pids: frozenset[int] = frozenset()) -> list[str]:
    problems = []
    for lock in sorted(server.rglob(".session.lock")):
        try:
            pid = _json(lock).get("process_id")
        except (OSError, ValueError):
            pid = None
        if pid not in killed_pids:
            problems.append(f"lock left behind in {lock.parent.relative_to(server)} (pid {pid})")
    return problems


def _work_dirs(server: Path):
    """(session dir, list name, work dir) for every packing work dir with saved state."""
    for state in sorted(server.glob("Sessions/CLIENT_*/*/packing/*/packing_state.json")):
        work = state.parent
        yield work.parent.parent, work.name, work


def _completed(work: Path) -> tuple[list[str], list[str]]:
    state = _json(work / "packing_state.json")
    return (
        [entry["order_number"] for entry in state.get("completed", [])],
        list(state.get("completed_off_list", [])),
    )


def check_packing_state(server: Path) -> list[str]:
    problems = []
    for session, name, work in _work_dirs(server):
        where = f"{session.name}/{name}"
        try:
            listed = {o["order_number"] for o in _json(session / "packing_lists" / f"{name}.json")["orders"]}
            completed, _ = _completed(work)
        except (OSError, ValueError, KeyError) as exc:
            problems.append(f"{where}: packing state unreadable ({exc})")
            continue
        dupes = sorted({o for o in completed if completed.count(o) > 1})
        if dupes:
            problems.append(f"{where}: completed more than once: {dupes}")
        off_list = sorted(set(completed) - listed)
        if off_list:
            problems.append(f"{where}: completed but not on the list: {off_list}")
    return problems


def check_registry_counts(server: Path) -> list[str]:
    problems = []
    for session, name, work in _work_dirs(server):
        where = f"{session.name}/{name}"
        try:
            completed, _ = _completed(work)
            entry = _json(session.parent / "registry_index.json")["sessions"].get(f"{session.name}::{name}")
        except (OSError, ValueError, KeyError) as exc:
            problems.append(f"{where}: registry unreadable ({exc})")
            continue
        if entry is None:
            problems.append(f"{where}: no registry entry")
        elif entry.get("completed_orders") != len(completed):
            problems.append(
                f"{where}: registry says {entry.get('completed_orders')} completed, packing state says {len(completed)}"
            )
    return problems


def check_packed_signal(server: Path) -> list[str]:
    problems = []
    for session, name, work in _work_dirs(server):
        where = f"{session.name}/{name}"
        try:
            completed, off_list = _completed(work)
            block = _json(session / "session_info.json").get("packing_progress", {}).get(name) or {}
        except (OSError, ValueError, KeyError) as exc:
            problems.append(f"{where}: session_info unreadable ({exc})")
            continue
        signal = set(block.get("completed_orders", []))
        packed = set(completed) | set(off_list)
        if signal != packed:
            problems.append(
                f"{where}: packed-order signal {sorted(signal)} != packed {sorted(packed)}"
            )
    return problems


def check_all(server: Path, killed_pids: frozenset[int] = frozenset()) -> list[str]:
    return [
        *check_json_parses(server),
        *check_no_temp_files(server),
        *check_no_locks(server, killed_pids),
        *check_packing_state(server),
        *check_registry_counts(server),
        *check_packed_signal(server),
    ]
```

Append to `.gitignore`:

```
# Two-PC simulation runs (python -m sim.run)
sim-out/
```

- [ ] **Step 4: Run it to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_sim_invariants.py`
Expected: 9 passed. Then `ruff check . --exclude shared` → no errors.

- [ ] **Step 5: Commit**

```bash
/usr/bin/git add sim/__init__.py sim/invariants.py tests/test_sim_invariants.py .gitignore
/usr/bin/git commit -F /abs/path/msg.txt   # "sim: server invariants for the two-PC harness"
```

---

### Task 2: Agent plumbing, fulfilment agent, orchestrator, CLI, first scenario

**Files:**
- Create: `sim/agent_common.py`, `sim/agent_fulfilment.py`, `sim/data.py`, `sim/world.py`, `sim/scenarios.py`,
  `sim/run.py`

**Interfaces:**
- Consumes: `sim.invariants.check_all` (Task 1).
- Produces (used by every later task):
  - `sim.agent_common`: `record(kind: str, **fields)`, `capture_calls(module_name: str, func_name: str, kind: str)`,
    `pump_until(cond: Callable[[], bool], timeout: float, what: str)`, `serve(ops: dict[str, Callable])`,
    `install_capture()` (before the window is built), `capture_logs()` (after).
  - `sim.data`: `CLIENT = "SIM"`, `COURIERS = ("DHL", "DPD")`, `Inputs(orders: Path, stock: Path)`,
    `write_inputs(folder: Path) -> Inputs`.
  - `sim.world`: `REPO: Path`, `World(run_dir: Path, packing_tool: Path)` with `.server`, `.inputs`, `.findings`,
    `.killed_pids`, `.spawn(name, app) -> PC`, `.expect(cond, message)`, `.close()`, `.server_offline()`,
    `.server_online()`, `.readonly(path)`, `.writable(path)`. Also `PC` with `.send(op, **args)`,
    `.receive(timeout=30) -> Reply`, `.call(op, timeout=30, **args) -> Reply`, `.kill()`, `.quit()`, `.pid`,
    `.name`, and `Reply` with `.result`, `.events`, `.saw(kind, text="") -> bool`. Plus `class OpFailed(Exception)`.
  - `sim.scenarios`: `ALL: dict[str, Callable[[World], None]]` and `fulfilment_pc(world, name, create=False) -> PC`.

- [ ] **Step 1: Write `sim/agent_common.py`**

```python
"""One simulated PC: a Qt app driven by JSON lines on stdin, answering on the real stdout.

Imported by both agents before their app. It must never import either app.
Importing it moves fd 1 onto stderr, so an app print() cannot corrupt the
protocol channel.
"""

import json
import logging
import os
import sys
import threading
import time
import traceback

_PROTO = os.fdopen(os.dup(1), "w", buffering=1, encoding="utf-8")
os.dup2(2, 1)
sys.stdout = sys.stderr

from PySide6.QtCore import QObject, Qt, Signal  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox  # noqa: E402

_EVENTS: list[dict] = []
_ANSWERS: dict[str, str] = {}


def record(kind: str, **fields) -> None:
    _EVENTS.append({"kind": kind, **fields})


def _scripted(title: str, text: str) -> str | None:
    """The answer the current op scripted for a dialog, matched on a title/text substring."""
    haystack = f"{title}\n{text}".lower()
    for key, answer in _ANSWERS.items():
        if key.lower() in haystack:
            return answer
    return None


def _static_box(level: str):
    def box(parent, title, text, *args, **kwargs):
        answer = _scripted(str(title), str(text))
        record("dialog", level=level, title=str(title), text=str(text), answer=answer,
               unexpected=level == "question" and answer is None)
        if level == "question":
            return QMessageBox.StandardButton.Yes if answer == "yes" else QMessageBox.StandardButton.No
        return QMessageBox.StandardButton.Ok
    return box


def _exec(self):
    title = self.windowTitle()
    text = self.text() if isinstance(self, QMessageBox) else type(self).__name__
    answer = _scripted(title, text)
    record("dialog", level="exec", title=title, text=text, answer=answer, unexpected=answer is None)
    if isinstance(self, QMessageBox):
        return QMessageBox.StandardButton.Yes if answer == "yes" else QMessageBox.StandardButton.No
    return QDialog.DialogCode.Accepted if answer in ("yes", "accept") else QDialog.DialogCode.Rejected


class _LogCapture(logging.Handler):
    def emit(self, rec: logging.LogRecord) -> None:
        record("log", level=rec.levelname, source=rec.name, text=rec.getMessage()[:500])


def _on_exception(exc_type, exc, tb) -> None:
    record("exception", text="".join(traceback.format_exception(exc_type, exc, tb))[-4000:])


def install_capture() -> None:
    """Patch every modal and hook every crash. Call before building the window."""
    for level in ("question", "warning", "information", "critical"):
        setattr(QMessageBox, level, _static_box(level))
    QDialog.exec = _exec
    QMessageBox.exec = _exec
    sys.excepthook = _on_exception
    threading.excepthook = lambda a: _on_exception(a.exc_type, a.exc_value, a.exc_traceback)


def capture_logs() -> None:
    """Record WARNING and above. Call after the app has set up its own logging."""
    handler = _LogCapture(level=logging.WARNING)
    logging.getLogger().addHandler(handler)


def capture_calls(module_name: str, func_name: str, kind: str) -> None:
    """Record every call of module.func_name, wherever it has been imported to."""
    import importlib

    original = getattr(importlib.import_module(module_name), func_name)

    def recorder(*args, **kwargs):
        record(kind, text=" | ".join(str(a) for a in args[1:]))
        return original(*args, **kwargs)

    for module in list(sys.modules.values()):
        if getattr(module, func_name, None) is original:
            setattr(module, func_name, recorder)


def pump_until(cond, timeout: float, what: str) -> None:
    deadline = time.monotonic() + timeout
    while not cond():
        if time.monotonic() > deadline:
            raise TimeoutError(f"{what} did not finish within {timeout}s")
        QApplication.processEvents()
        time.sleep(0.02)


def _reply(req_id, ok: bool, result, error) -> None:
    events = _EVENTS[:]
    _EVENTS.clear()
    _PROTO.write(json.dumps(
        {"id": req_id, "ok": ok, "result": result, "error": error, "events": events}, default=str
    ) + "\n")


class _Inbox(QObject):
    request = Signal(dict)


def serve(ops: dict) -> None:
    """Answer requests on the Qt thread until `quit` or stdin closes. Needs the QApplication built."""
    app = QApplication.instance()
    inbox = _Inbox()

    def handle(req: dict) -> None:
        args = dict(req.get("args") or {})
        _ANSWERS.clear()
        _ANSWERS.update(args.pop("answers", None) or {})
        try:
            result, ok, error = ops[req["op"]](**args), True, None
        except Exception:
            result, ok, error = None, False, traceback.format_exc()[-4000:]
        if req.get("id") is not None:
            _reply(req["id"], ok, result, error)
        if req["op"] == "quit":
            app.quit()

    inbox.request.connect(handle, Qt.ConnectionType.QueuedConnection)

    def read_stdin() -> None:
        for line in sys.stdin:
            if line.strip():
                inbox.request.emit(json.loads(line))
        inbox.request.emit({"id": None, "op": "quit"})

    threading.Thread(target=read_stdin, daemon=True).start()
    ops.setdefault("ping", lambda: {"pid": os.getpid()})
    ops.setdefault("print_probe", lambda: print("stray app output") or {"printed": True})
    ops.setdefault("dialog_probe", lambda: {"answer": str(QMessageBox.question(None, "Probe", "unscripted?"))})
    app.exec()
```

- [ ] **Step 2: Write `sim/data.py`**

```python
"""Deterministic synthetic Shopify orders and stock for the simulation. Never production data.

Headers follow ProfileManager._create_default_shopify_config's default column mapping.
"""

import csv
import random
from dataclasses import dataclass
from pathlib import Path

CLIENT = "SIM"
COURIERS = ("DHL", "DPD")
_METHOD = {"DHL": "DHL Express", "DPD": "DPD Bulgaria"}
ORDER_HEADERS = [
    "Name", "Lineitem sku", "Lineitem quantity", "Lineitem name", "Shipping Method", "Shipping Country",
    "Tags", "Notes", "Total", "Subtotal", "Shipping Name", "Created at",
]
STOCK_HEADERS = ["Артикул", "Име", "Наличност"]
SKUS = [f"SIM-{i:03d}" for i in range(1, 13)]
OUT_OF_STOCK = SKUS[-1]
N_ORDERS = 40


@dataclass(frozen=True)
class Inputs:
    orders: Path
    stock: Path


def write_inputs(folder: Path) -> Inputs:
    """40 orders over 12 SKUs, alternating DHL/DPD; every 5th is two lines, every 7th has
    quantity 3, and orders 8, 19 and 30 want only the out-of-stock SKU."""
    rng = random.Random(0)
    folder.mkdir(parents=True, exist_ok=True)
    rows = []
    for i in range(N_ORDERS):
        courier = COURIERS[i % 2]
        skus = [OUT_OF_STOCK] if i in (7, 18, 29) else rng.sample(SKUS[:-1], 2 if i % 5 == 0 else 1)
        for sku in skus:
            rows.append({
                "Name": f"#{1001 + i}", "Lineitem sku": sku, "Lineitem quantity": 3 if i % 7 == 0 else 1,
                "Lineitem name": f"Product {sku}", "Shipping Method": _METHOD[courier],
                "Shipping Country": "BG", "Tags": "", "Notes": "", "Total": "10.00", "Subtotal": "10.00",
                "Shipping Name": f"Customer {i}", "Created at": f"2026-09-01 10:{i:02d}:00 +0300",
            })
    orders = folder / "orders_export.csv"
    with orders.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=ORDER_HEADERS)
        writer.writeheader()
        writer.writerows(rows)
    stock = folder / "stock.csv"
    with stock.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(STOCK_HEADERS)
        for sku in SKUS:
            writer.writerow([sku, f"Product {sku}", 0 if sku == OUT_OF_STOCK else 500])
    return Inputs(orders=orders, stock=stock)
```

- [ ] **Step 3: Write `sim/agent_fulfilment.py`**

Seams (verified): `MainWindow()` reads `FULFILLMENT_SERVER_PATH`. There are `mw.actions_handler`, `mw.profile_manager`,
`mw.load_client_config(id)`, `mw.load_existing_session(path)` (synchronous), `mw.orders_file_path`,
`mw.stock_file_path`, `mw._analysis_running`, `mw.analysis_results_df`, `mw.session_path`, and
`actions_handler.create_new_session()`, `.run_analysis()`, `._generate_reports(batch, session_path)` (synchronous,
and runs the stale-export check) and `.set_order_fulfillable(order, bool)`. Also
`profile_manager.load_shopify_config(id)` / `save_shopify_config(id, cfg)`. The repeat flag is `"Repeat"` inside the
`System_note` column. Toasts come from `shared.components.toast.toast`, and error banners from
`gui.components.error_banner.show_error`.

```python
"""A fulfilment PC. Run as `.venv/bin/python -m sim.agent_fulfilment` with cwd = this repo."""

from pathlib import Path

from sim import agent_common as ac


def main() -> None:
    from PySide6.QtWidgets import QApplication

    app = QApplication([])  # noqa: F841 - must outlive the window
    ac.install_capture()
    import gui.session_browser_widget as browser
    from gui.main_window_pyside import MainWindow

    browser.SessionBrowserWidget.USE_ASYNC = False  # as tests/audit/test_05_sessions_sweep.py
    mw = MainWindow()
    mw.resize(1100, 900)
    mw.show()
    QApplication.processEvents()
    ac.capture_calls("shared.components.toast", "toast", "toast")
    ac.capture_calls("gui.components.error_banner", "show_error", "error_banner")
    ac.capture_logs()

    def create_client(client_id: str) -> dict:
        return {"created": bool(mw.profile_manager.create_client_profile(client_id, f"Client {client_id}"))}

    def select_client(client_id: str) -> dict:
        mw.current_client_id = client_id
        mw.load_client_config(client_id)
        return {"client_id": mw.current_client_id}

    def new_session() -> dict:
        mw.actions_handler.create_new_session()
        return {"session_path": str(mw.session_path) if mw.session_path else None}

    def open_session(session_path: str) -> dict:
        mw.load_existing_session(session_path)
        return {"session_path": str(mw.session_path) if mw.session_path else None}

    def set_inputs(orders: str, stock: str) -> dict:
        mw.orders_file_path, mw.stock_file_path = orders, stock
        return {}

    def run_analysis() -> dict:
        mw.actions_handler.run_analysis()
        ac.pump_until(lambda: not getattr(mw, "_analysis_running", False), 120, "analysis")
        df = mw.analysis_results_df
        return {"orders": 0 if df is None else int(df["Order_Number"].nunique())}

    def generate_packing_lists(couriers: list[str]) -> dict:
        batch = [
            {
                "report_type": "packing_lists",
                "name": f"{c}_Orders",
                "output_filename": f"{c}_Orders.xlsx",
                "filters": [{"field": "Shipping_Provider", "operator": "==", "value": c}],
            }
            for c in couriers
        ]
        mw.actions_handler._generate_reports(batch, mw.session_path)
        return {"lists": sorted(p.stem for p in (Path(mw.session_path) / "packing_lists").glob("*.json"))}

    def set_fulfillable(order: str, value: bool) -> dict:
        mw.actions_handler.set_order_fulfillable(order, value)
        return {}

    def orders() -> list:
        df = mw.analysis_results_df
        if df is None:
            return []
        return [
            {
                "order": str(number),
                "status": str(group["Order_Fulfillment_Status"].iloc[0]),
                "repeat": "Repeat" in str(group["System_note"].iloc[0]),
            }
            for number, group in df.groupby("Order_Number")
        ]

    def save_client_setting(key: str, value) -> dict:
        config = mw.profile_manager.load_shopify_config(mw.current_client_id)
        config.setdefault("settings", {})[key] = value
        return {"saved": bool(mw.profile_manager.save_shopify_config(mw.current_client_id, config))}

    def client_setting(key: str) -> dict:
        config = mw.profile_manager.load_shopify_config(mw.current_client_id) or {}
        return {"value": config.get("settings", {}).get(key)}

    def quit_() -> dict:
        mw.close()
        return {}

    ac.serve({
        "create_client": create_client, "select_client": select_client, "new_session": new_session,
        "open_session": open_session, "set_inputs": set_inputs, "run_analysis": run_analysis,
        "generate_packing_lists": generate_packing_lists, "set_fulfillable": set_fulfillable,
        "orders": orders, "save_client_setting": save_client_setting, "client_setting": client_setting,
        "quit": quit_,
    })


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Write `sim/world.py`**

```python
"""Orchestrator side: a temp server, simulated PCs as subprocesses, and the RPC to them."""

import json
import os
import queue
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path

from sim import data

REPO = Path(__file__).resolve().parent.parent

PACKER_CONFIG = """[Network]
FileServerPath = {server}
ConnectionTimeout = 5
LocalCachePath = {cache}

[Logging]
LogLevel = INFO
LogRetentionDays = 30
MaxLogSizeMB = 10

[General]
Environment = development
DebugMode = true

[UI]
RememberLastClient = true
AutoRefreshInterval = 0
"""


class OpFailed(Exception):
    """An op raised inside the agent; the message carries its traceback."""


class AgentDied(Exception):
    """The agent process exited or stopped answering."""


@dataclass
class Reply:
    result: object
    events: list = field(default_factory=list)

    def saw(self, kind: str, text: str = "") -> bool:
        return any(
            e["kind"] == kind and text.lower() in f"{e.get('title', '')}\n{e.get('text', '')}".lower()
            for e in self.events
        )

    def told_operator(self) -> bool:
        """A dialog, toast or error banner: something a person at the PC would see."""
        return any(e["kind"] in ("dialog", "toast", "error_banner") for e in self.events)


class PC:
    def __init__(self, world: "World", name: str, app: str):
        self.world, self.name, self.app = world, name, app
        pc_dir = world.run_dir / "pcs" / name
        home = pc_dir / "home"
        (home / ".config").mkdir(parents=True, exist_ok=True)
        env = {
            **os.environ,
            "COMPUTERNAME": name, "USERNAME": f"user-{name}",
            "HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config"),
            "QT_QPA_PLATFORM": "offscreen", "QTWEBENGINE_DISABLE_SANDBOX": "1",
            "FULFILLMENT_SERVER_PATH": str(world.server), "SIM_FAST_CLOCK": "1",
        }
        if app == "fulfilment":
            python, cwd, extra = REPO / ".venv" / "bin" / "python", REPO, []
        else:
            config = pc_dir / "config.ini"
            config.write_text(PACKER_CONFIG.format(server=world.server, cache=home / "cache"), encoding="utf-8")
            python, cwd, extra = world.packing_tool / ".venv" / "bin" / "python", world.packing_tool, ["--config", str(config)]
            # cwd comes first on sys.path under -m, so packing-tool's gui/shared win over this repo's.
            env["PYTHONPATH"] = os.pathsep.join(p for p in (str(REPO), env.get("PYTHONPATH")) if p)
        self._stderr = (pc_dir / "stderr.log").open("ab")
        self.proc = subprocess.Popen(
            [str(python), "-m", f"sim.agent_{app}", *extra],
            cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self._stderr,
            text=True, encoding="utf-8",
        )
        self.pid = self.proc.pid
        self._lines: queue.Queue = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()
        self._next_id = 0
        self._pending: list[str] = []

    def _read(self) -> None:
        for line in self.proc.stdout:
            self._lines.put(line)
        self._lines.put(None)

    def send(self, op: str, **args) -> None:
        self._next_id += 1
        self._pending.append(op)
        try:
            self.proc.stdin.write(json.dumps({"id": self._next_id, "op": op, "args": args}) + "\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise AgentDied(f"{self.name} is gone ({exc})") from exc

    def receive(self, timeout: float = 30) -> Reply:
        op = self._pending.pop(0)
        try:
            line = self._lines.get(timeout=timeout)
        except queue.Empty:
            self.kill()
            raise AgentDied(f"{self.name} did not answer {op} within {timeout}s") from None
        if line is None:
            raise AgentDied(f"{self.name} exited during {op} (code {self.proc.poll()})")
        msg = json.loads(line)
        reply = Reply(msg["result"], msg["events"])
        self.world.note_events(self.name, op, reply.events)
        if not msg["ok"]:
            raise OpFailed(f"{self.name} {op} failed:\n{msg['error']}")
        return reply

    def call(self, op: str, timeout: float = 30, **args) -> Reply:
        self.send(op, **args)
        return self.receive(timeout)

    def kill(self) -> None:
        if self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait()
            self.world.killed_pids.add(self.pid)

    def quit(self) -> None:
        """A clean exit: says yes to any close-time question."""
        if self.proc.poll() is None:
            try:
                self.call("quit", timeout=30, answers={"": "yes"})
                self.proc.wait(timeout=15)
            except (AgentDied, OpFailed, subprocess.TimeoutExpired):
                self.kill()


class World:
    def __init__(self, run_dir: Path, packing_tool: Path, scenario: str = ""):
        self.run_dir, self.packing_tool, self.scenario = run_dir, packing_tool, scenario
        self.server = run_dir / "server"
        self.server.mkdir(parents=True)
        self.inputs = data.write_inputs(run_dir / "inputs")
        self.findings: list[str] = []
        self.killed_pids: set[int] = set()
        self.pcs: list[PC] = []
        self._events = (run_dir / "events.jsonl").open("a", encoding="utf-8")

    def spawn(self, name: str, app: str) -> PC:
        pc = PC(self, name, app)
        self.pcs.append(pc)
        pc.call("ping", timeout=90)  # startup events (first-run prompts, import errors) land here
        return pc

    def note_events(self, pc: str, op: str, events: list) -> None:
        for event in events:
            self._events.write(json.dumps({"scenario": self.scenario, "pc": pc, "op": op, **event}) + "\n")
            if event["kind"] == "exception" or event.get("unexpected"):
                self.findings.append(f"{pc} {op}: {event['kind']}: {event.get('title', '')} {event['text'][:1500]}")
        self._events.flush()

    def expect(self, cond, message: str) -> None:
        if not cond:
            self.findings.append(message)

    def close(self) -> None:
        for pc in self.pcs:
            pc.quit()
        self._events.close()

    def server_offline(self) -> None:
        self.server.rename(self.server.with_name("server.offline"))

    def server_online(self) -> None:
        self.server.with_name("server.offline").rename(self.server)

    @staticmethod
    def readonly(path: Path) -> None:
        for p in [path, *path.rglob("*")]:
            p.chmod(0o555 if p.is_dir() else 0o444)

    @staticmethod
    def writable(path: Path) -> None:
        for p in [path, *path.rglob("*")]:
            p.chmod(0o755 if p.is_dir() else 0o644)
```

(Both build the file list before the first chmod, so the walk never meets a directory it can't read, and a 0o555
directory still lets its children be chmodded.)

- [ ] **Step 5: Write `sim/scenarios.py` with the first scenario**

```python
"""The scenarios. Each takes a fresh World and records what it finds through world.expect."""

from pathlib import Path

from sim.data import CLIENT
from sim.world import World


def fulfilment_pc(world: World, name: str, create: bool = False):
    pc = world.spawn(name, "fulfilment")
    if create:
        pc.call("create_client", client_id=CLIENT)
    pc.call("select_client", client_id=CLIENT)
    return pc


def same_day_sessions(world: World) -> None:
    """Two fulfilment PCs create a session at the same moment: two distinct sessions, both intact."""
    a = fulfilment_pc(world, "PC-A", create=True)
    d = fulfilment_pc(world, "PC-D")
    a.send("new_session")
    d.send("new_session")
    pa, pd = a.receive().result["session_path"], d.receive().result["session_path"]
    world.expect(pa and pd and pa != pd, f"new sessions collided: A={pa} D={pd}")
    for path in (pa, pd):
        if path:
            world.expect((Path(path) / "session_info.json").exists(), f"{path} has no session_info.json")


ALL = {
    "same_day_sessions": same_day_sessions,
}
```

- [ ] **Step 6: Write `sim/run.py`**

```python
"""Run the two-PC simulation: python -m sim.run [scenario ...] --packing-tool PATH [--list]."""

import argparse
import sys
import traceback
from datetime import datetime
from pathlib import Path

from sim import invariants, scenarios
from sim.world import REPO, World


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("names", nargs="*", help="scenarios to run (default: all)")
    parser.add_argument("--packing-tool", type=Path, default=REPO.parent / "packing-tool")
    parser.add_argument("--list", action="store_true", help="list scenarios and exit")
    args = parser.parse_args(argv)
    if args.list:
        print("\n".join(scenarios.ALL))
        return 0
    unknown = [n for n in args.names if n not in scenarios.ALL]
    if unknown:
        parser.error(f"unknown scenario(s): {', '.join(unknown)}")
    packing_tool = args.packing_tool.resolve()
    if not (packing_tool / ".venv" / "bin" / "python").exists():
        parser.error(f"no packing-tool venv at {packing_tool}; pass --packing-tool")

    out = REPO / "sim-out" / datetime.now().strftime("%Y%m%d-%H%M%S")
    report = [f"# Simulation run {out.name}\n"]
    found = 0
    for name in args.names or list(scenarios.ALL):
        world = World(out / name, packing_tool, name)
        try:
            scenarios.ALL[name](world)
        except Exception:
            world.findings.append("scenario aborted:\n" + traceback.format_exc(limit=6))
        finally:
            world.close()
        world.findings += invariants.check_all(world.server, frozenset(world.killed_pids))
        verdict = "FIND" if world.findings else "PASS"
        found += bool(world.findings)
        print(f"{verdict} {name}", flush=True)
        report.append(f"## {verdict} {name}\n\n{(scenarios.ALL[name].__doc__ or '').strip()}\n")
        report += [f"- {f}".replace("\n", "\n  ") for f in world.findings]
        report.append(f"\nLogs: `{(out / name / 'pcs').relative_to(REPO)}/*/stderr.log`, events: `events.jsonl`\n")
    (out / "report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"report: {out / 'report.md'}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 7: Prove the plumbing by hand**

Run (one command):
`.venv/bin/python -c "from sim.world import World; from pathlib import Path; import tempfile; w = World(Path(tempfile.mkdtemp())/'r', Path('/home/gloopy/Desktop/Projects/packing-tool')); a = w.spawn('PC-A','fulfilment'); print(a.call('print_probe').result); print(a.call('dialog_probe').events); w.close(); print(w.findings)"`

Expected:
- `{'printed': True}`. The stray print went to stderr, not the protocol.
- One `dialog` event with `"unexpected": True`, and `w.findings` holding that one "unexpected" entry. That proves an
  unscripted modal neither blocks nor goes unrecorded.
- If `ping` records a startup dialog (a first-run prompt on an empty server), note it. Task 2's scenario still has
  to pass, so script its answer in `fulfilment_pc` by passing `answers=` on the create/select call, or handle it
  where it appears, and say so in the commit message.

- [ ] **Step 8: Run the first scenario**

Run: `.venv/bin/python -m sim.run same_day_sessions --packing-tool /home/gloopy/Desktop/Projects/packing-tool`
Expected: `PASS same_day_sessions`, or `FIND` whose findings are genuine app behaviour and not harness errors. An
`OpFailed` traceback pointing into `sim/` is a harness bug: fix it and re-run. Then run the gate.

- [ ] **Step 9: Commit**

```bash
/usr/bin/git add sim/agent_common.py sim/agent_fulfilment.py sim/data.py sim/world.py sim/scenarios.py sim/run.py
/usr/bin/git commit -F /abs/path/msg.txt   # "sim: agents, orchestrator and CLI; same_day_sessions"
```

---

### Task 3: The fulfilment scenarios

**Files:**
- Modify: `sim/scenarios.py`

**Interfaces:**
- Consumes: `World`, `PC`, `Reply` (Task 2); fulfilment ops `create_client`, `select_client`, `new_session`,
  `open_session`, `set_inputs`, `run_analysis`, `generate_packing_lists`, `set_fulfillable`, `orders`,
  `save_client_setting`, `client_setting`.
- Produces: `analysed_session(world: World) -> tuple[PC, str]` (PC-A still running with the session open, and the
  session path; lists `DHL_Orders` and `DPD_Orders` generated). Tasks 4 to 6 use it.

- [ ] **Step 1: Add the helper and three scenarios to `sim/scenarios.py`** (above `ALL`)

```python
import time

from sim.data import COURIERS


def analysed_session(world: World):
    """PC-A creates the client and a session, analyses the synthetic inputs and makes the DHL and DPD lists."""
    a = fulfilment_pc(world, "PC-A", create=True)
    session = a.call("new_session").result["session_path"]
    a.call("set_inputs", orders=str(world.inputs.orders), stock=str(world.inputs.stock))
    a.call("run_analysis", timeout=150)
    lists = a.call("generate_packing_lists", couriers=list(COURIERS)).result["lists"]
    world.expect(lists == ["DHL_Orders", "DPD_Orders"], f"packing lists generated: {lists}")
    return a, session


def stale_save(world: World) -> None:
    """Two PCs edit one session: the second PC's stale save is refused visibly, the first PC's edit survives."""
    a, session = analysed_session(world)
    d = fulfilment_pc(world, "PC-D")
    d.call("open_session", session_path=session)
    fulfillable = [o["order"] for o in a.call("orders").result if o["status"] == "Fulfillable"]
    x, y = fulfillable[0], fulfillable[1]
    a.call("set_fulfillable", order=x, value=False)
    r = d.call("set_fulfillable", order=y, value=False)
    world.expect(r.told_operator(), "PC-D's edit to a session PC-A had changed was not refused visibly")
    e = fulfilment_pc(world, "PC-E")
    e.call("open_session", session_path=session)
    status = {o["order"]: o["status"] for o in e.call("orders").result}
    world.expect(status.get(x) != "Fulfillable", f"PC-A's hold on {x} was lost (status {status.get(x)})")
    world.expect(status.get(y) == "Fulfillable", f"PC-D's stale edit to {y} was saved (status {status.get(y)})")


def config_race(world: World) -> None:
    """Two PCs save the client config 20 times each, interleaved: it always parses and ends as one writer's value."""
    a = fulfilment_pc(world, "PC-A", create=True)
    d = fulfilment_pc(world, "PC-D")
    for i in range(20):
        a.send("save_client_setting", key="low_stock_threshold", value=100 + i)
        d.send("save_client_setting", key="low_stock_threshold", value=200 + i)
        a.receive()
        d.receive()
    final = a.call("client_setting", key="low_stock_threshold").result["value"]
    world.expect(final in (119, 219), f"final low_stock_threshold {final} is neither writer's last value")


def killed_mid_analysis(world: World) -> None:
    """PC-A dies 0.2 s into an analysis; PC-D can still open the session without an exception."""
    a = fulfilment_pc(world, "PC-A", create=True)
    session = a.call("new_session").result["session_path"]
    a.call("set_inputs", orders=str(world.inputs.orders), stock=str(world.inputs.stock))
    a.send("run_analysis")
    time.sleep(0.2)
    a.kill()
    d = fulfilment_pc(world, "PC-D")
    d.call("open_session", session_path=session)  # exceptions surface as findings through the events
```

Then extend `ALL`:

```python
ALL = {
    "same_day_sessions": same_day_sessions,
    "stale_save": stale_save,
    "config_race": config_race,
    "killed_mid_analysis": killed_mid_analysis,
}
```

Move the `import time` and `from sim.data import COURIERS` lines up to the module's import block (ruff's isort order).

- [ ] **Step 2: Run each new scenario**

Run one at a time, for example:
`.venv/bin/python -m sim.run stale_save --packing-tool /home/gloopy/Desktop/Projects/packing-tool`
Expected: `PASS` or `FIND` with app-level findings. If `analysed_session` records `packing lists generated: [...]`
with other names, open the `_generate_single_report` naming code, fix the op or the expectation, and write the reason
in the commit message. Then run the gate.

- [ ] **Step 3: Commit** — `"sim: fulfilment scenarios (stale save, config race, killed analysis)"`

---

### Task 4: Packer agent and the full pipeline

**Files:**
- Create: `sim/agent_packer.py`
- Modify: `sim/scenarios.py`

**Interfaces:**
- Consumes: `agent_common` (Task 2), `analysed_session` (Task 3).
- Produces: packer ops `start_list(client_id, session_path, list_name) -> {"started": bool}`,
  `pack_order(order) -> {"completed": bool}`, `skip() -> {}`, `end_session() -> {"ended": bool}`,
  `state() -> {"active": bool, "all": [str], "completed": [str], "skipped": [str], "current": str|None}`, `quit`.
  Helpers `packer_pc(world, name) -> PC`, `pack_all(pc) -> list[str]` and
  `list_args(session: str, list_name: str) -> dict` (the `start_list` arguments for client `SIM`).

Seams (verified in packing-tool): `MainWindow(skip_worker_selection=True, config_path=...)`,
`mw.worker_manager.get_all_workers()` / `.create_worker(name)` (a `WorkerProfile` with `.id`, `.name`),
`mw.current_worker_id` / `mw.current_worker_name`,
`mw._handle_start_packing_from_browser({"session_path", "client_id", "packing_list_name", "list_file"})`
(synchronous; waits for its own worker thread), `mw.logic` (`None` when no list is open),
`mw.logic.orders_data[order]["items"]` → `[{"sku", "quantity"}]`, `mw.logic.current_order_number`,
`mw.logic.session_packing_state["completed_orders" | "skipped_orders"]`, `mw.on_scanner_input(text)`,
`mw._on_skip_order()` and `mw.end_session()` (synchronous: it spins until `SessionEndWorker` finishes).
`SessionLockManager.HEARTBEAT_INTERVAL` / `STALE_TIMEOUT` are class attributes, but
`MainWindow._start_heartbeat_timer` hard-codes `start(60000)`. Toasts come from `shared.components.toast.toast`.

- [ ] **Step 1: Write `sim/agent_packer.py`**

```python
"""A packer PC. Run with packing-tool's venv, cwd = packing-tool, PYTHONPATH = this repo:
`python -m sim.agent_packer --config <pc config.ini>`."""

import os
import sys
from pathlib import Path

from sim import agent_common as ac

FAST_CLOCK = os.environ.get("SIM_FAST_CLOCK") == "1"


def main() -> None:
    from PySide6.QtWidgets import QApplication

    config = sys.argv[sys.argv.index("--config") + 1]
    app = QApplication([])  # noqa: F841 - must outlive the window
    ac.install_capture()
    from gui.main_window import MainWindow
    from packing_tool.session_lock_manager import SessionLockManager

    if FAST_CLOCK:  # a crashed PC's lock goes stale in seconds, not minutes
        SessionLockManager.HEARTBEAT_INTERVAL = 1
        SessionLockManager.STALE_TIMEOUT = 4
        original_start = MainWindow._start_heartbeat_timer

        def fast_heartbeat(self):
            original_start(self)
            self.heartbeat_timer.start(1000)

        MainWindow._start_heartbeat_timer = fast_heartbeat

    mw = MainWindow(skip_worker_selection=True, config_path=config)
    pc_name = os.environ["COMPUTERNAME"]
    worker = next((w for w in mw.worker_manager.get_all_workers() if w.name == pc_name), None)
    worker = worker or mw.worker_manager.create_worker(pc_name)
    mw.current_worker_id, mw.current_worker_name = worker.id, worker.name
    mw.show()
    QApplication.processEvents()
    ac.capture_calls("shared.components.toast", "toast", "toast")
    ac.capture_logs()

    def start_list(client_id: str, session_path: str, list_name: str) -> dict:
        mw._handle_start_packing_from_browser({
            "session_path": session_path, "client_id": client_id, "packing_list_name": list_name,
            "list_file": str(Path(session_path) / "packing_lists" / f"{list_name}.json"),
        })
        return {"started": mw.logic is not None}

    def completed() -> list[str]:
        return list(mw.logic.session_packing_state.get("completed_orders", []))

    def pack_order(order: str) -> dict:
        mw.on_scanner_input(order)
        items = mw.logic.orders_data[mw.logic.current_order_number]["items"]
        for item in items:
            for _ in range(int(item["quantity"])):
                mw.on_scanner_input(str(item["sku"]))
        ac.pump_until(lambda: mw.logic is None or mw.logic.current_order_number is None, 5, f"closing {order}")
        return {"completed": mw.logic is not None and order in completed()}

    def skip() -> dict:
        mw._on_skip_order()
        return {}

    def end_session() -> dict:
        mw.end_session()
        return {"ended": mw.logic is None}

    def state() -> dict:
        if mw.logic is None:
            return {"active": False, "all": [], "completed": [], "skipped": [], "current": None}
        return {
            "active": True,
            "all": list(mw.logic.orders_data),
            "completed": completed(),
            "skipped": list(mw.logic.session_packing_state.get("skipped_orders", [])),
            "current": mw.logic.current_order_number,
        }

    def quit_() -> dict:
        mw.close()
        return {}

    ac.serve({
        "start_list": start_list, "pack_order": pack_order, "skip": skip,
        "end_session": end_session, "state": state, "quit": quit_,
    })


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Prove the packer agent starts**

Run: `.venv/bin/python -c "from sim.world import World; from pathlib import Path; import tempfile; w = World(Path(tempfile.mkdtemp())/'r', Path('/home/gloopy/Desktop/Projects/packing-tool')); b = w.spawn('PC-B','packer'); print(b.call('state').result); w.close(); print(w.findings)"`
Expected: `{'active': False, ...}` and no findings. If the agent dies, read `r/pcs/PC-B/stderr.log`. An
`ImportError` for `sim` means `PYTHONPATH` is wrong. A startup dialog means scripting it in `ping`'s place, as in
Task 2 Step 7.

- [ ] **Step 3: Add the helpers and the pipeline scenario to `sim/scenarios.py`**

```python
def packer_pc(world: World, name: str):
    return world.spawn(name, "packer")


def list_args(session: str, list_name: str) -> dict:
    return {"client_id": CLIENT, "session_path": session, "list_name": list_name}


def pack_all(pc) -> list[str]:
    """Pack every order of the open list that is not packed yet; returns the completed orders."""
    state = pc.call("state").result
    for order in state["all"]:
        if order not in state["completed"]:
            pc.call("pack_order", order=order)
    return pc.call("state").result["completed"]


def pipeline(world: World) -> None:
    """PC-A analyses and makes lists; PC-B packs all of DHL; PC-A's next session on the same orders
    flags exactly the DHL orders as repeats."""
    a, session = analysed_session(world)
    b = packer_pc(world, "PC-B")
    started = b.call("start_list", **list_args(session, "DHL_Orders")).result["started"]
    world.expect(started, "PC-B could not start DHL_Orders")
    if not started:
        return
    packed = pack_all(b)
    b.call("end_session")
    b.quit()
    a.call("new_session")
    a.call("set_inputs", orders=str(world.inputs.orders), stock=str(world.inputs.stock))
    a.call("run_analysis", timeout=150)
    repeats = {o["order"] for o in a.call("orders").result if o["repeat"]}
    world.expect(repeats == set(packed), f"repeats {sorted(repeats)} != orders packed on PC-B {sorted(packed)}")
```

Add `"pipeline": pipeline` as the **first** entry of `ALL`.

- [ ] **Step 4: Run it**

Run: `.venv/bin/python -m sim.run pipeline --packing-tool /home/gloopy/Desktop/Projects/packing-tool`
Expected: `PASS pipeline`, or `FIND` with app findings only. If `pack_order` fails with a `KeyError` on
`orders_data`, the order number normalisation differs (`#1001` against `1001`). Scan exactly what
`state()["all"]` returned, and fix the op rather than the app. Then run the gate.

- [ ] **Step 5: Commit** — `"sim: packer agent and the full pipeline scenario"`

---

### Task 5: Two packers, one client

**Files:**
- Modify: `sim/scenarios.py`

**Interfaces:**
- Consumes: `analysed_session`, `packer_pc`, `list_args`, `pack_all` (Tasks 3 and 4), `PC.send/receive/kill`, and
  `World.killed_pids`.

- [ ] **Step 1: Add the scenarios** (above `ALL`)

```python
import json


def lock_race(world: World) -> None:
    """PC-B and PC-C open the same list at the same moment: exactly one gets it, the other is told
    it is open on another PC."""
    a, session = analysed_session(world)
    a.quit()
    b, c = packer_pc(world, "PC-B"), packer_pc(world, "PC-C")
    b.send("start_list", **list_args(session, "DHL_Orders"))
    c.send("start_list", **list_args(session, "DHL_Orders"))
    rb, rc = b.receive(60), c.receive(60)
    got = (rb.result["started"], rc.result["started"])
    world.expect(sorted(got) == [False, True], f"started: PC-B={got[0]} PC-C={got[1]}")
    loser = rc if got[0] else rb
    # Every sim PC shares one hostname, so match the wording, not a PC name (Review Focus 5).
    world.expect(loser.saw("dialog", "another PC"), "the PC that lost the race was not told the list is open elsewhere")
    for pc, started in ((b, got[0]), (c, got[1])):
        if started:
            pc.call("end_session", timeout=60)


def crash_takeover(world: World) -> None:
    """PC-B packs 5 orders and is killed; after the lock goes stale PC-C takes the list over, keeps
    those 5 and finishes it, every order completed exactly once."""
    a, session = analysed_session(world)
    a.quit()
    b = packer_pc(world, "PC-B")
    b.call("start_list", **list_args(session, "DHL_Orders"))
    orders = b.call("state").result["all"]
    for order in orders[:5]:
        b.call("pack_order", order=order)
    time.sleep(2)  # let the async state writer land: a crash inside that window is a separate question
    b.kill()
    time.sleep(5)  # STALE_TIMEOUT (4 s under SIM_FAST_CLOCK) + 1
    c = packer_pc(world, "PC-C")
    r = c.call("start_list", answers={"stale": "yes"}, **list_args(session, "DHL_Orders"))
    world.expect(r.result["started"], "PC-C could not take over the stale list")
    if not r.result["started"]:
        return
    resumed = c.call("state").result["completed"]
    world.expect(set(orders[:5]) <= set(resumed), f"orders lost in the crash: {sorted(set(orders[:5]) - set(resumed))}")
    done = pack_all(c)
    world.expect(sorted(done) == sorted(orders), f"after takeover completed {len(done)} of {len(orders)}")
    c.call("end_session", timeout=60)


def parallel_lists(world: World) -> None:
    """PC-B packs DHL while PC-C packs DPD, one order each in turn: both lists' orders reach the packed signal."""
    a, session = analysed_session(world)
    a.quit()
    b, c = packer_pc(world, "PC-B"), packer_pc(world, "PC-C")
    b.call("start_list", **list_args(session, "DHL_Orders"))
    c.call("start_list", **list_args(session, "DPD_Orders"))
    ob, oc = b.call("state").result["all"], c.call("state").result["all"]
    for i in range(max(len(ob), len(oc))):
        if i < len(ob):
            b.call("pack_order", order=ob[i])
        if i < len(oc):
            c.call("pack_order", order=oc[i])
    b.call("end_session", timeout=60)
    c.call("end_session", timeout=60)
    b.quit()
    c.quit()
    progress = json.loads((Path(session) / "session_info.json").read_text(encoding="utf-8")).get("packing_progress", {})
    for name, orders in (("DHL_Orders", ob), ("DPD_Orders", oc)):
        signal = set((progress.get(name) or {}).get("completed_orders", []))
        world.expect(signal == set(orders), f"{name}: packed signal holds {len(signal)} of {len(orders)} orders")
```

Move `import json` to the import block, and add to `ALL`: `"lock_race"`, `"crash_takeover"`, `"parallel_lists"`.

- [ ] **Step 2: Run each one**, e.g.
`.venv/bin/python -m sim.run lock_race --packing-tool /home/gloopy/Desktop/Projects/packing-tool`
Expected: `PASS`, or `FIND` with app findings. In `crash_takeover`, the killed PC's lock is excluded from the lock
invariant by PID. If the stale prompt is never shown, check the `events.jsonl` dialog titles and adjust the `answers`
key to the real title. Then run the gate.

- [ ] **Step 3: Commit** — `"sim: two-packer scenarios (lock race, crash takeover, parallel lists)"`

---

### Task 6: Server trouble

**Files:**
- Modify: `sim/scenarios.py`

**Interfaces:**
- Consumes: `World.server_offline/server_online/readonly/writable`, `Reply.told_operator`, and the helpers from
  Tasks 3 and 4.

- [ ] **Step 1: Add the scenarios** (above `ALL`)

```python
def server_vanishes_mid_pack(world: World) -> None:
    """The server goes away while PC-B packs: PC-B is told, nothing crashes, and once the server is back
    packing continues with the pre-outage order kept."""
    a, session = analysed_session(world)
    a.quit()
    b = packer_pc(world, "PC-B")
    b.call("start_list", **list_args(session, "DHL_Orders"))
    orders = b.call("state").result["all"]
    b.call("pack_order", order=orders[0])
    time.sleep(2)
    world.server_offline()
    try:
        r1 = b.call("pack_order", order=orders[1])
        time.sleep(3)  # heartbeat (1 s) and async writes hit the missing server; their events ride on the next reply
        r2 = b.call("state")
        world.expect(r1.told_operator() or r2.told_operator(),
                     "PC-B kept packing with the server gone and was not told")
    finally:
        world.server_online()
    if not b.call("state").result["active"]:  # a lost lock tears the list down by design (spec B3)
        b.call("start_list", answers={"stale": "yes"}, **list_args(session, "DHL_Orders"))
    st = b.call("state").result
    world.expect(orders[0] in st["completed"], f"{orders[0]}, packed before the outage, was lost")
    if st["active"]:
        b.call("pack_order", order=next(o for o in orders if o not in st["completed"]))
        b.call("end_session", timeout=60)


def readonly_end(world: World) -> None:
    """The session folder turns read-only before PC-B ends its list: PC-B is told, nothing crashes, no
    partial files; once writable again the list ends cleanly with its packed orders kept."""
    a, session = analysed_session(world)
    a.quit()
    b = packer_pc(world, "PC-B")
    b.call("start_list", **list_args(session, "DHL_Orders"))
    orders = b.call("state").result["all"]
    for order in orders[:2]:
        b.call("pack_order", order=order)
    time.sleep(2)
    world.readonly(Path(session))
    try:
        r = b.call("end_session", timeout=60)
        world.expect(r.told_operator(), "ending a list on a read-only share told the operator nothing")
    finally:
        world.writable(Path(session))
    if b.call("state").result["active"]:
        world.expect(b.call("end_session", timeout=60).result["ended"], "the list would not end once writable")
    state_file = Path(session) / "packing" / "DHL_Orders" / "packing_state.json"
    kept = [c["order_number"] for c in json.loads(state_file.read_text(encoding="utf-8")).get("completed", [])]
    world.expect(set(orders[:2]) <= set(kept), f"packed orders lost: {sorted(set(orders[:2]) - set(kept))}")
```

Add both to `ALL`.

- [ ] **Step 2: Run each one**, then the gate. Expected: `PASS` or `FIND` with app findings. An `OpFailed` from
`pack_order` after the outage (for example `'NoneType' object has no attribute 'orders_data'`) means the list was
torn down mid-op. It is not an app bug on its own: guard the op (`if mw.logic is None: return {"completed": False}`)
and re-run.

- [ ] **Step 3: Commit** — `"sim: server-trouble scenarios (server vanishes, read-only end)"`

---

### Task 7: Document, run the bug hunt, file the issues

**Files:**
- Modify: `CLAUDE.md` (the "Run & Test Commands" section)

- [ ] **Step 1: Document the harness in CLAUDE.md**, after the test-suite block:

````markdown
```bash
# Two-PC simulation: real Fulfilment + Packer windows as separate simulated PCs on one temp server
.venv/bin/python -m sim.run --packing-tool ../packing-tool     # all scenarios; --list to list them
```
Findings land in `sim-out/<timestamp>/report.md` (gitignored). A local folder is not an SMB share, so SMB-only
bugs (ADR 0008) are out of its reach. See `docs/superpowers/specs/2026-09-29-two-pc-simulation-harness-design.md`.
````

- [ ] **Step 2: Run everything**

Run: `.venv/bin/python -m sim.run --packing-tool /home/gloopy/Desktop/Projects/packing-tool`

- [ ] **Step 3: Triage every finding** in `report.md`, reading `events.jsonl` and the PCs' `stderr.log`, into
exactly one of:
- **harness bug**: the traceback points into `sim/`, or an op used a seam wrongly. Fix it, commit
  (`"sim: fix <what>"`), and re-run that scenario.
- **by design**: an ADR or the spec says so. Examples: ADR 0011 (a stale save is refused and the refusing PC's
  screen still shows its edit), spec B3 (a PC that lost its lock tears down), a temp file left by a SIGKILL'd PC, or a
  lock text naming the same host for every sim PC. Write it down with the ADR/spec reference for the PR description.
- **app bug**: everything else.

Repeat until only by-design findings and app bugs remain.

- [ ] **Step 4: File each app bug** on the repo that owns the faulty code (`cognitiveghost/shopify-fulfillment-tool`
or `cognitiveghost/packing-tool`), one issue per root cause, with `gh issue create --repo <repo> --title "<symptom>"
--body-file <abs path>`. Body template:

```markdown
Found by the two-PC simulation harness (`sim/`, branch dr/9-can-we-try-to-do-a-manual-test-of-both-a).

**Scenario:** `<name>`, <its docstring>
**Repro:** `.venv/bin/python -m sim.run <name> --packing-tool ../packing-tool` (in shopify-fulfillment-tool)
**Expected:** ...
**Actual:** ...
**Evidence:** <the finding line; relevant events; 10-20 lines of stderr.log>
**Suspected location:** `<file:line>`, <one sentence why>
```

No production data and no absolute home paths in bodies (use `sim-out/...` relative paths).

- [ ] **Step 5: Gate and commit.** Run `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` and
`ruff check . --exclude shared`, then commit CLAUDE.md (`"docs: how to run the two-PC simulation"`). The PR
description (Stage C) lists every issue filed and every by-design finding with its reference, or says "no app bugs
found".
