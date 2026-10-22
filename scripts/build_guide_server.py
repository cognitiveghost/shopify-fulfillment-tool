"""Seed a throwaway server folder from the replay fixtures, for the user guides and their screenshots.

    .venv/bin/python scripts/build_guide_server.py <dest>

<dest> must be missing or empty. Everything is written by the headless code paths, from anonymised fixtures only,
so the folder holds what a working day holds: client profiles, sessions with analysis and packing lists, packer
settings and workers. It is never committed.
"""

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from shopify_tool import core, report_jobs
from shopify_tool.profile_manager import ProfileManager
from shopify_tool.session_manager import SessionManager

FIXTURES = REPO / "tests" / "replay" / "fixtures"
CLIENTS = {"ALMA": ("Alma Derm", 3), "HERBAR": ("Herbar", 2)}
BARCODES = ["2000000000008", "2000000000015", "2000000000022"]  # made-up EAN-13 numbers with valid check digits
WORKERS = ["Desislava", "Georgi", "Maria"]


def _read(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def _latest_config(client_id: str) -> dict:
    latest = max((FIXTURES / client_id).glob("*/meta.json"))
    return _read(FIXTURES / client_id / _read(latest)["config"])


def _report_config(config: dict, stem: str) -> dict:
    for candidate in config.get("packing_list_configs", []):
        name = candidate.get("output_filename") or f"{candidate.get('name')}.xlsx"
        if Path(name).stem == stem:
            return {**candidate, "report_type": "packing_lists"}
    raise KeyError(f"no packing_list_configs entry writes {stem}")


def _run_session(pm, sm, client_id: str, fixture: Path, config: dict) -> Path | None:
    """One fixture day through the app. None when it fails; its half-written session is removed."""
    meta = _read(fixture / "meta.json")
    baseline = _read(fixture / "memory_baseline.json")
    pm.save_inventory_memory(client_id, baseline["skus"], names_dict=baseline.get("names", {}))
    session_path = Path(sm.create_session(client_id))
    try:
        ok, message, final_df, _stats = core.run_full_analysis(
            None, str(fixture / "orders.csv"), None, "auto", "auto", config,
            client_id=client_id, session_manager=sm, profile_manager=pm, session_path=str(session_path),
        )
        if not ok:
            raise RuntimeError(message)
        batch = [_report_config(config, stem) for stem in meta["packing_lists"]]
        outcomes = report_jobs.generate_reports(
            batch, session_path, final_df, config.get("tag_categories", {}), session_path.name, sm,
        )
        failed = [o.name for o in outcomes if o.failed]
        if failed:
            raise RuntimeError(f"reports failed: {failed}")
    except Exception as error:
        print(f"skipped {fixture.parent.name}/{fixture.name}: {error}")
        shutil.rmtree(session_path, ignore_errors=True)
        return None
    return session_path


def _seed_sessions(pm, sm, client_id: str, config: dict, count: int) -> list[Path]:
    """The newest `count` fixture days that have packing lists, oldest first. A failed day is replaced by the
    next older one. Only days with packing lists count, so every seeded session has a list to show."""
    pool = [p.parent for p in sorted((FIXTURES / client_id).glob("*/meta.json")) if _read(p)["packing_lists"]]
    queue = pool[-count:]
    spare = list(reversed(pool[:-count]))
    seeded = []
    for fixture in queue:
        session_path = _run_session(pm, sm, client_id, fixture, config)
        if session_path is not None:
            seeded.append(session_path)
        elif spare:
            queue.append(spare.pop(0))
    if len(seeded) != count:
        raise RuntimeError(f"{client_id}: seeded {len(seeded)} of {count} sessions")
    return seeded


def _skus(session_path: Path) -> list[str]:
    """The first distinct SKUs on the session's first packing list."""
    list_file = next((session_path / "packing_lists").glob("*.json"))
    doc = _read(list_file)
    skus = [item["sku"] for order in doc["orders"] for item in order["items"]]
    return list(dict.fromkeys(skus))[: len(BARCODES)]


def build(dest: Path) -> None:
    dest = Path(dest)
    if dest.exists() and any(dest.iterdir()):
        raise ValueError(f"{dest} is not empty; give a new folder")

    pm = ProfileManager(base_path=str(dest))
    sm = SessionManager(pm)
    for client_id, (client_name, count) in CLIENTS.items():
        pm.create_client_profile(client_id, client_name)
        config = _latest_config(client_id)
        config.setdefault("inventory_memory", {})["enabled"] = True
        pm.save_shopify_config(client_id, config, backup=False)

        sessions = _seed_sessions(pm, sm, client_id, config, count)
        sku_mapping = dict(zip(BARCODES, _skus(sessions[-1]), strict=False))
        _write(
            dest / "Clients" / f"CLIENT_{client_id}" / "packer_config.json",
            {"client_id": client_id, "client_name": client_name, "sku_mapping": sku_mapping},
        )

    now = datetime.now().astimezone().isoformat(timespec="seconds")
    workers = [{"id": f"worker_{i:03d}", "name": name, "created_at": now} for i, name in enumerate(WORKERS, 1)]
    _write(dest / "Workers" / "workers.json", {"workers": workers, "version": "1.3.0"})


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: build_guide_server.py <dest>")
    try:
        build(Path(sys.argv[1]))
    except ValueError as error:
        sys.exit(str(error))
    print(f"built {sys.argv[1]}")
