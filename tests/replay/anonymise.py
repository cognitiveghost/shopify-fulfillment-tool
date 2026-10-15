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
