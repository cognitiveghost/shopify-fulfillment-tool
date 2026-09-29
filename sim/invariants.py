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
