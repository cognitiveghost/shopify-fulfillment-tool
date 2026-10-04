"""The values behind the Reports page (phase 9 spec section 6).

Packing lists and stock exports: two lists, in the order they generate.
ReportsDraft holds config_data["packing_list_configs"] and
["stock_export_configs"], takes the page's edits through apply(), and words
everything the page draws. No Qt import.
"""

import json
import logging
import re

from gui.settings.contract import PageContract
from gui.settings.fields import REPORT_FILTER_OPERATORS, report_filter_fields
from gui.settings.page_state import _shaped
from gui.settings.rules_state import (
    _PLACEHOLDER,
    EQUALITY_OPERATORS,
    NOT_AVAILABLE,
    SUGGESTION_LIMIT,
    iso_date,
    value_kind,
)
from shopify_tool.core import get_unique_column_values
from shopify_tool.report_filters import (
    count_matches,
    normalize_operator,
    parse_sku_list,
)

logger = logging.getLogger(__name__)

PACKING = "packing"
STOCK = "stock"
# (kind, the card's title, its Add button, the config key, its empty line)
KINDS = (
    (
        PACKING,
        "Packing lists",
        "Add packing list",
        "packing_list_configs",
        "No packing lists yet. Add one, then generate it from Results after an analysis.",
    ),
    (
        STOCK,
        "Stock exports",
        "Add stock export",
        "stock_export_configs",
        "No stock exports yet. Add one, then generate it from Results after an analysis.",
    ),
)

SUBTITLE = "The packing lists and stock exports this client generates from Results."
GROUP_TEXT = "Generated in this order."
UNTITLED = "Untitled report"
NO_FILTER = "Every fulfillable order."
NO_FILENAME = "No file name yet, so this report can't be generated."
FILENAME_HINT = "The file's name in the session's folder, e.g. DHL.xlsx."
FILTERS_HINT = "An order line is listed when it passes every filter."
EXCLUDE_HINT = "Lines with these SKUs are left off the list."
EXCLUDE_PLACEHOLDER = "SKU-1, SKU-2"
COLUMNS_HINT = "Printed in this order. None chosen: the default layout."
ALL_COLUMNS = "Every column is chosen."
CANT_COUNT = "Can't count matches for these filters."

_KEY_UID = re.compile(r"report-(\d+)-")


def _text(value) -> str:
    return "" if value is None else str(value)


def match_text(counts) -> str:
    """Copy for a report's match count; None means no analysis has run."""
    if counts is None:
        return "Run an analysis to see how many orders this report matches."
    orders, rows = counts
    if orders == 0:
        return "Matches no orders. Check the filters."
    return (
        f"Matches {orders} order{'' if orders == 1 else 's'}"
        f" · {rows} row{'' if rows == 1 else 's'}"
    )


def _filter(stored: dict) -> dict:
    value = stored.get("value")
    try:
        operator = normalize_operator(stored.get("operator"))
    except TypeError:
        # Not a string at all (a list): kept as text, and matches nothing.
        operator = stored.get("operator")
    return {
        "field": _text(stored.get("field")),
        # A stored "!=" reads "does not equal": shown as the name it now has.
        "operator": _text(operator),
        "value": ", ".join(map(str, value)) if isinstance(value, list) else _text(value),
        "stored": dict(stored),
    }


class ReportsDraft(PageContract):
    """Owns both packing_list_configs and stock_export_configs."""

    def __init__(self, packing_configs, stock_configs, analysis_df=None):
        self.analysis_df = analysis_df
        self._next = 0
        self.open_uid: str | None = None
        # The analysis is fixed for the dialog's life, so a count never goes
        # stale. ponytail: one entry per filter text ever typed; a dialog
        # lives minutes. Bound it if a session is ever left open for days.
        self._matches: dict[str, tuple[str, bool]] = {}
        self._fields = report_filter_fields(analysis_df)
        self.entries = [
            self._entry(kind, stored)
            for kind, configs in ((PACKING, packing_configs), (STOCK, stock_configs))
            for stored in (configs if isinstance(configs, list) else [])
        ]

    def _uid(self) -> str:
        self._next += 1
        return str(self._next)

    def _entry(self, kind: str, stored) -> dict:
        stored = stored if isinstance(stored, dict) else {}
        filters = stored.get("filters")
        columns = stored.get("columns")
        return {
            "uid": self._uid(),
            "kind": kind,
            "name": _text(stored.get("name")),
            "filename": _text(stored.get("output_filename")),
            "filters": [
                _filter(f) for f in (filters if isinstance(filters, list) else []) if isinstance(f, dict)
            ],
            "exclude": ", ".join(parse_sku_list(stored.get("exclude_skus"))),
            "columns": [str(c) for c in columns] if isinstance(columns, list) else [],
            "stored": dict(stored),
        }

    def _find(self, uid: str) -> dict | None:
        return next((e for e in self.entries if e["uid"] == uid), None)

    def _of_kind(self, kind: str) -> list[dict]:
        return [entry for entry in self.entries if entry["kind"] == kind]

    def _has_analysis(self) -> bool:
        return self.analysis_df is not None and not self.analysis_df.empty

    def _candidates(self, entry: dict) -> list[str]:
        """The columns a packing list can still add. Repeat is derived at
        print time, so it is never a column of the analysis."""
        offered = list(self._fields)
        if "Repeat" not in offered:
            offered.append("Repeat")
        return [name for name in offered if name not in entry["columns"]]

    # --- the edits ---------------------------------------------------------

    def apply(self, action: str, args) -> bool:
        if action == "open" and _shaped(args, str):
            if self._find(args[0]) is None or self.open_uid == args[0]:
                return False
            self.open_uid = args[0]
            return True
        if action == "close" and _shaped(args):
            if self.open_uid is None:
                return False
            self.open_uid = None
            return True
        if action == "reveal" and _shaped(args, str):
            found = _KEY_UID.match(args[0])
            return bool(found) and self.apply("open", [found.group(1)])
        if action == "report_add" and _shaped(args, str):
            if args[0] not in (PACKING, STOCK):
                return False
            entry = self._entry(args[0], {})
            self.entries.append(entry)
            self.open_uid = entry["uid"]
            return True
        entry = self._find(args[0]) if isinstance(args, list) and args and type(args[0]) is str else None
        if entry is None:
            return False
        if action == "report_delete" and _shaped(args, str):
            self.entries.remove(entry)
            if self.open_uid == entry["uid"]:
                self.open_uid = None
            return True
        if action == "report_move" and _shaped(args, str, str):
            return self._move(entry, args[1])
        if action in ("report_name", "report_filename", "report_exclude") and _shaped(args, str, str):
            name = action.removeprefix("report_")
            if name == "exclude" and entry["kind"] != PACKING:
                return False
            if entry[name] == args[1]:
                return False
            entry[name] = args[1]
            return True
        if action == "filter_add" and _shaped(args, str):
            first = self._fields[0] if self._fields else ""
            entry["filters"].append(
                {"field": first, "operator": "equals", "value": "", "stored": {}}
            )
            return True
        if action == "filter_remove" and _shaped(args, str, str):
            at = self._filter_at(entry, args[1])
            if at is None:
                return False
            del entry["filters"][at]
            return True
        if action in ("filter_field", "filter_operator", "filter_value") and _shaped(args, str, str, str):
            at = self._filter_at(entry, args[1])
            name = action.removeprefix("filter_")
            if at is None or entry["filters"][at][name] == args[2]:
                return False
            row = entry["filters"][at]
            if name == "operator":
                if args[2] not in REPORT_FILTER_OPERATORS:
                    return False
                if value_kind(args[2]) != value_kind(row["operator"]):
                    row["value"] = ""
            row[name] = args[2]
            return True
        if action == "column_add" and _shaped(args, str, str):
            if entry["kind"] != PACKING or args[1] not in self._candidates(entry):
                return False
            entry["columns"].append(args[1])
            return True
        if action == "column_remove" and _shaped(args, str, str):
            if args[1] not in entry["columns"]:
                return False
            entry["columns"].remove(args[1])
            return True
        return False

    @staticmethod
    def _filter_at(entry: dict, position: str) -> int | None:
        if not position.isdecimal() or int(position) >= len(entry["filters"]):
            return None
        return int(position)

    def _move(self, entry: dict, direction: str) -> bool:
        """One place up or down among the reports of its kind."""
        if direction not in ("up", "down"):
            return False
        same = self._of_kind(entry["kind"])
        at = same.index(entry) + (-1 if direction == "up" else 1)
        if not 0 <= at < len(same):
            return False
        a, b = self.entries.index(entry), self.entries.index(same[at])
        self.entries[a], self.entries[b] = self.entries[b], self.entries[a]
        return True

    # --- what is saved -----------------------------------------------------

    @staticmethod
    def _stored_filters(entry: dict) -> list[dict]:
        return [
            {**f["stored"], "field": f["field"], "operator": f["operator"], "value": f["value"]}
            for f in entry["filters"]
        ]

    def _stored(self, entry: dict) -> dict:
        config = {
            **entry["stored"],
            "name": entry["name"],
            "output_filename": entry["filename"],
            "filters": self._stored_filters(entry),
        }
        if entry["kind"] == PACKING:
            config["exclude_skus"] = parse_sku_list(entry["exclude"])
            if entry["columns"]:
                config["columns"] = list(entry["columns"])
            else:
                # None chosen means the default layout: no key at all.
                config.pop("columns", None)
        return config

    def collect(self) -> dict:
        return {
            config_key: [self._stored(entry) for entry in self._of_kind(kind)]
            for kind, _title, _add, config_key, _empty in KINDS
        }

    # --- what the page draws -----------------------------------------------

    def _match(self, entry: dict) -> dict:
        filters = [
            {"field": f["field"], "operator": f["operator"], "value": f["value"]}
            for f in entry["filters"]
        ]
        key = json.dumps(filters, sort_keys=True)
        if key not in self._matches:
            try:
                counts = count_matches(self.analysis_df, filters)
                self._matches[key] = (match_text(counts), counts is not None and counts[0] == 0)
            except Exception:
                # Debug, not warning: a half-typed regex lands here on every keystroke.
                logger.debug("Couldn't count report matches", exc_info=True)
                self._matches[key] = (CANT_COUNT, False)
        text, warn = self._matches[key]
        return {"text": text, "warn": warn}

    def _summary(self, entry: dict) -> list[dict]:
        parts = []
        for n, f in enumerate(entry["filters"]):
            if n:
                parts.append({"t": "join", "v": "and"})
            parts.append({"t": "bold", "v": f["field"]})
            parts.append({"t": "text", "v": f["operator"]})
            if value_kind(f["operator"]) != "none" and f["value"] != "":
                parts.append({"t": "chip", "v": f["value"]})
        return parts or [{"t": "muted", "v": NO_FILTER}]

    def _filter_view(self, f: dict) -> dict:
        """One filter, in the shape of a rule's condition (phase 8 spec 4.7)."""
        field, operator = f["field"], f["operator"]
        offered = field in self._fields
        kind = value_kind(operator)
        suggestions = []
        if kind == "text" and operator in EQUALITY_OPERATORS and offered and self._has_analysis():
            suggestions = get_unique_column_values(self.analysis_df, field)
        return {
            "field": field,
            # A stored field that is not offered: listed first, and kept.
            "extra_field": None
            if offered or not field
            else {"value": field, "note": NOT_AVAILABLE if self._has_analysis() else ""},
            "field_invalid": bool(field) and not offered and self._has_analysis(),
            "operator": operator,
            "extra_operator": None if operator in REPORT_FILTER_OPERATORS else operator,
            "value": {
                "kind": kind,
                "text": iso_date(f["value"]) if kind == "date" else f["value"],
                "placeholder": _PLACEHOLDER.get(operator, "Value"),
                "suggestions": suggestions[:SUGGESTION_LIMIT],
            },
            "problem": "",
            "hint": "",
            "invalid": False,
        }

    def _editor(self, entry: dict) -> dict:
        packing = entry["kind"] == PACKING
        candidates = self._candidates(entry) if packing else []
        return {
            "filename_hint": FILENAME_HINT,
            "filters_hint": FILTERS_HINT,
            "field_groups": [{"label": "", "fields": list(self._fields)}],
            "operators": list(REPORT_FILTER_OPERATORS),
            "filters": [self._filter_view(f) for f in entry["filters"]],
            "exclude": {
                "value": entry["exclude"],
                "placeholder": EXCLUDE_PLACEHOLDER,
                "hint": EXCLUDE_HINT,
            }
            if packing
            else None,
            "columns": {
                "chips": list(entry["columns"]),
                "candidates": candidates,
                "hint": COLUMNS_HINT,
                "add_title": "" if candidates else ALL_COLUMNS,
            }
            if packing
            else None,
        }

    def _row(self, entry: dict, place: int, count: int) -> dict:
        is_open = entry["uid"] == self.open_uid
        return {
            "uid": entry["uid"],
            "name": entry["name"],
            "label": entry["name"].strip() or UNTITLED,
            "filename": entry["filename"],
            "open": is_open,
            "can_up": place > 0,
            "can_down": place < count - 1,
            "summary": self._summary(entry),
            "match": self._match(entry),
            "note": "" if entry["filename"].strip() else NO_FILENAME,
            "editor": self._editor(entry) if is_open else None,
        }

    def view(self) -> dict:
        groups = []
        for kind, title, add, _config_key, empty in KINDS:
            same = self._of_kind(kind)
            groups.append(
                {
                    "kind": kind,
                    "title": title,
                    "text": GROUP_TEXT,
                    "add": add,
                    "empty": empty,
                    "rows": [self._row(entry, n, len(same)) for n, entry in enumerate(same)],
                }
            )
        return {
            "page": "reports",
            "title": "Reports",
            "subtitle": SUBTITLE,
            "action": "",
            "reports": {"groups": groups},
        }
