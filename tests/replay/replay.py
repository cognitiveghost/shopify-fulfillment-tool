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
    for i, (x, y) in enumerate(zip(eo, ao, strict=False)):
        if x != y:
            fields = [k for k in sorted(set(x) | set(y)) if x.get(k) != y.get(k)]
            return f"order {i} ({x.get('order_number')}): {fields}"
    return f"order count: expected {len(eo)}, got {len(ao)}"
