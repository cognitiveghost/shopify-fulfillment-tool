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


def _caught_only_by(found, server) -> None:
    """The fault is caught, and by that invariant alone."""
    assert found
    assert invariants.check_all(server) == found


def test_a_sound_tree_passes(tmp_path):
    assert invariants.check_all(_tree(tmp_path)) == []


def test_a_torn_json_file_is_caught(tmp_path):
    server = _tree(tmp_path)
    (server / "Sessions" / "CLIENT_SIM" / "client_config.json").write_text('{"settings": {', encoding="utf-8")
    _caught_only_by(invariants.check_json_parses(server), server)


def test_a_temp_file_is_caught_and_not_parsed_as_json(tmp_path):
    server = _tree(tmp_path)
    (server / "Sessions" / ".session_info_tmp_ab12.json").write_text("{", encoding="utf-8")
    _caught_only_by(invariants.check_no_temp_files(server), server)


def test_a_lock_left_by_a_live_pc_is_caught(tmp_path):
    server = _tree(tmp_path, lock_pid=4242)
    _caught_only_by(invariants.check_no_locks(server), server)


def test_a_lock_left_by_a_killed_pc_is_allowed(tmp_path):
    assert invariants.check_no_locks(_tree(tmp_path, lock_pid=4242), frozenset({4242})) == []


def test_a_completed_order_not_on_the_list_is_caught(tmp_path):
    server = _tree(tmp_path, completed=("#1001", "#9999"), signal=("#1001", "#9999"), registry_count=2)
    _caught_only_by(invariants.check_packing_state(server), server)


def test_an_order_completed_twice_is_caught(tmp_path):
    server = _tree(tmp_path, completed=("#1001", "#1001"), registry_count=2)
    _caught_only_by(invariants.check_packing_state(server), server)


def test_a_registry_count_that_disagrees_is_caught(tmp_path):
    server = _tree(tmp_path, registry_count=2)
    _caught_only_by(invariants.check_registry_counts(server), server)


def test_a_packed_signal_that_disagrees_is_caught(tmp_path):
    server = _tree(tmp_path, signal=())
    _caught_only_by(invariants.check_packed_signal(server), server)
