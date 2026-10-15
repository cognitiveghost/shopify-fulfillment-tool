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
from anonymise import (
    OrderMap,
    clean_config,
    config_of_day,
    orders_frame,
    packing_doc,
    rule_words,
)
from replay import first_difference, replay_session

from shopify_tool import fulfillment_history
from shopify_tool.csv_utils import AUTO_DELIMITER, resolve_delimiter

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
            found.append((datetime.strptime(m.group(1), "%Y%m%d_%H%M%S"), p))  # noqa: DTZ007 -- backup names are local time
    return found


def build_client(server: Path, client_id: str, only: set[str] | None, keep_failed: bool = False) -> list[str]:
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
        column = next(c for c, v in config["column_mappings"]["orders"].items() if v == "Order_Number")
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
    history = history[[c for c in fulfillment_history.COLUMNS if c in history.columns]]
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
        words = rule_words(config, "Notes")
        shutil.rmtree(target, ignore_errors=True)
        target.mkdir(parents=True)
        orders_frame(_raw_csv(_orders_file(source)), config, omap).to_csv(
            target / "orders.csv", index=False, encoding="utf-8")
        shutil.copyfile(source / "analysis" / "memory_baseline.json", target / "memory_baseline.json")
        _write_json(target / "expected" / "analysis_data.json",
                    packing_doc(_read(source / "analysis" / "analysis_data.json"), omap, words))
        lists = []
        if (client_id, name) not in WITH_OPERATIONS:
            for path in sorted((source / "packing_lists").glob("*.json")):
                lists.append(path.stem)
                _write_json(target / "expected" / "packing_lists" / path.name, packing_doc(_read(path), omap, words))
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
            if not keep_failed:
                shutil.rmtree(target)
            failed.append(f"{client_id}/{name}: {problem}")
        else:
            print(f"ok {client_id}/{name} ({'exact' if exact else 'nearest'} config, {len(lists)} lists)")
    return failed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--server", type=Path, required=True, help="the Server/ folder of the snapshot")
    parser.add_argument("--only", action="append", help="CLIENT/SESSION, repeatable")
    parser.add_argument("--keep-failed", action="store_true",
                        help="leave a session that did not reproduce on disk, for debugging (never commit it)")
    args = parser.parse_args()
    only = set(args.only or [])
    failed = []
    for client_id in GOLDEN:
        if only and not any(o.startswith(f"{client_id}/") for o in only):
            continue
        failed += build_client(args.server.expanduser(), client_id, only, args.keep_failed)
    for line in failed:
        print(f"FAILED {line}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
