"""The values behind the settings pages the web tier draws (phase 7 spec section 4).

A draft is a settings page with no widget. It holds one page's values, takes
the page's edits through apply(), and meets PageContract, so SettingsWindow
saves and marks it exactly as it does a Qt page. view() is everything the web
page draws, sentences included: the page computes nothing. No Qt import.

apply(action, args) returns whether anything changed. The actions are the
spec's section 3.4: add one there before adding it here. The page sends
strings and booleans only; an edit of any other shape is dropped.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from gui.settings.contract import PageContract
from shopify_tool.csv_utils import discover_additional_columns, read_csv_preview


@dataclass(frozen=True)
class FileColumns:
    """A CSV's header and first row, as a mapping page shows them."""

    name: str  # the file's name, as the card shows it
    columns: tuple[str, ...]  # the header row, in file order
    first_row: dict[str, str] = field(default_factory=dict)  # "" when empty
    loaded: bool = False  # True: the file loaded on Setup. False: picked here


def read_file_columns(path, loaded: bool, delimiter: str | None = None) -> FileColumns:
    """A CSV's header and first row. Raises what reading the file raises.

    `delimiter` is what to split it on; None detects it.
    """
    headers, first_row = read_csv_preview(str(path), delimiter)
    return FileColumns(Path(path).name, tuple(headers), first_row, loaded)


def _shaped(args, *kinds: type) -> bool:
    """Whether `args` is a list of exactly these types, in order."""
    return (
        isinstance(args, list)
        and len(args) == len(kinds)
        and all(type(arg) is kind for arg, kind in zip(args, kinds, strict=True))
    )


# --- General -----------------------------------------------------------------

KINDS = ("stock", "orders")
DELIMITER_LABEL = {"stock": "Stock CSV delimiter", "orders": "Orders CSV delimiter"}
OTHER = "other"
# The segments, in order: (the name the page sends, the label, the character).
DELIMITER_MODES = (
    ("auto", "Auto", "auto"),
    ("comma", "Comma", ","),
    ("semicolon", "Semicolon", ";"),
    ("tab", "Tab", "\t"),
    (OTHER, "Other", None),
)
_MODE_OF = {char: name for name, _label, char in DELIMITER_MODES if char}
_CHAR_OF = {name: char for name, _label, char in DELIMITER_MODES if char}
_SPLIT_ON = {"comma": "commas", "semicolon": "semicolons", "tab": "tabs"}

DELIMITER_PROBLEM = "Type the character that separates the columns."
THRESHOLD_HINT = (
    "A SKU is low when fewer than this are left after the session's orders "
    "are allocated."
)
THRESHOLD_PROBLEM = "Type a whole number, 0 or more."
_WHOLE = re.compile(r"[0-9]+")


class GeneralDraft(PageContract):
    """Delimiters and the low-stock threshold, stored under config_data["settings"]."""

    def __init__(self, settings: dict, client: str):
        # Held by reference so collect() can update it in place: the window
        # assigns collect()'s value straight over config_data[key], so a fresh
        # dict here would drop every key this page does not draw.
        self._settings = settings
        self.client = client
        self.mode: dict[str, str] = {}
        self.char: dict[str, str] = {}
        for kind in KINDS:
            # None and "" read as Auto, as resolve_delimiter reads them.
            stored = settings.get(f"{kind}_csv_delimiter") or "auto"
            # Pipe, and any hand-edited value, open as Other: kept, not rewritten.
            self.mode[kind] = _MODE_OF.get(stored, OTHER)
            self.char[kind] = "" if stored in _MODE_OF else str(stored)
        self.threshold = str(settings.get("low_stock_threshold", 5))

    def apply(self, action: str, args) -> bool:
        if action == "delimiter" and _shaped(args, str, str):
            kind, mode = args
            known = mode == OTHER or mode in _CHAR_OF
            if kind not in KINDS or not known or self.mode[kind] == mode:
                return False
            self.mode[kind] = mode
            return True
        if action == "delimiter_char" and _shaped(args, str, str):
            kind, text = args
            if kind not in KINDS or self.char[kind] == text:
                return False
            self.char[kind] = text
            return True
        if action == "threshold" and _shaped(args, str):
            if self.threshold == args[0]:
                return False
            self.threshold = args[0]
            return True
        return False

    def delimiter(self, kind: str) -> str:
        """What is stored for `kind`: "auto", or the character."""
        mode = self.mode[kind]
        return self.char[kind] if mode == OTHER else _CHAR_OF[mode]

    def _problems(self) -> list[tuple[str, str, str]]:
        """(blocker, data-key, sentence) for each value that cannot be saved."""
        found = [
            (f"Set {DELIMITER_LABEL[kind]}", f"char-{kind}", DELIMITER_PROBLEM)
            for kind in KINDS
            if self.mode[kind] == OTHER and not self.char[kind]
        ]
        if self._bad_threshold():
            found.append(("Set Low-stock threshold", "threshold", THRESHOLD_PROBLEM))
        return found

    def _bad_threshold(self) -> bool:
        return not _WHOLE.fullmatch(self.threshold.strip())

    def blocker(self) -> str | None:
        problems = self._problems()
        return problems[0][0] if problems else None

    def blocker_key(self) -> str:
        problems = self._problems()
        return problems[0][1] if problems else ""

    def validate(self) -> tuple[bool, list[str]]:
        problems = self._problems()
        return not problems, [
            f"{blocker.removeprefix('Set ')}: {sentence}"
            for blocker, _key, sentence in problems
        ]

    def collect(self) -> dict:
        self._settings.update(
            {
                "stock_csv_delimiter": self.delimiter("stock"),
                "orders_csv_delimiter": self.delimiter("orders"),
                "low_stock_threshold": int(self.threshold.strip()),
            }
        )
        return {"settings": self._settings}

    def _delimiter_view(self, kind: str) -> dict:
        mode = self.mode[kind]
        missing = mode == OTHER and not self.char[kind]
        if mode == "auto":
            hint = "Detected for each file as it is read."
        elif mode == OTHER:
            hint = "" if missing else f"Every file is split on “{self.char[kind]}”."
        else:
            hint = f"Every file is split on {_SPLIT_ON[mode]}."
        return {
            "kind": kind,
            "label": DELIMITER_LABEL[kind],
            "options": [
                {"value": name, "label": label, "checked": name == mode}
                for name, label, _char in DELIMITER_MODES
            ],
            "other": mode == OTHER,
            "char": self.char[kind],
            "hint": hint,
            "problem": DELIMITER_PROBLEM if missing else "",
        }

    def view(self) -> dict:
        return {
            "page": "general",
            "title": "General",
            "subtitle": (
                f"How {self.client}'s files are read, and when stock counts as low."
            ),
            "action": "",
            "general": {
                "csv_text": (
                    f"The character that separates columns in {self.client}'s files."
                ),
                "alerts_text": "When a SKU is flagged as low stock in Results.",
                "delimiters": [self._delimiter_view(kind) for kind in KINDS],
                "threshold": {
                    "value": self.threshold,
                    "unit": "units",
                    "hint": THRESHOLD_HINT,
                    "problem": THRESHOLD_PROBLEM if self._bad_threshold() else "",
                },
            },
        }


# --- column mapping ----------------------------------------------------------

READ_ACTION = "Read columns from CSV…"
NOT_IN_FILE = "Not in this file"
MAPPING_TITLE = {"orders": "Orders mapping", "stock": "Stock mapping"}


@dataclass(frozen=True)
class MappingField:
    """One internal field a CSV column can be mapped to."""

    name: str  # the internal name the analysis reads
    label: str
    required: bool = False
    hint: str = ""
    example: str = ""  # a column that usually holds it; required fields only


# Expiry_Date and Batch are the exact internal names _build_fifo_lots() looks
# for (shopify_tool/analysis.py): renaming them here silently turns FIFO lot
# allocation off.
FIELDS: dict[str, tuple[MappingField, ...]] = {
    "orders": (
        MappingField("Order_Number", "Order number", True, example="Name"),
        MappingField("SKU", "SKU", True, example="Lineitem sku"),
        MappingField("Quantity", "Quantity", True, example="Lineitem quantity"),
        MappingField(
            "Shipping_Method", "Shipping method", True, example="Shipping Method"
        ),
        MappingField("Product_Name", "Product name"),
        MappingField("Shipping_Country", "Country"),
        MappingField("Tags", "Tags"),
        MappingField("Notes", "Notes"),
        MappingField("Total_Price", "Total price"),
        MappingField("Subtotal", "Subtotal"),
        MappingField("Customer", "Customer"),
        MappingField("Created_At", "Created at"),
    ),
    "stock": (
        MappingField("SKU", "SKU", True, example="Артикул"),
        MappingField("Stock", "Quantity", True, example="Наличност"),
        MappingField("Product_Name", "Product name"),
        MappingField(
            "Expiry_Date",
            "Expiry date",
            hint=(
                "When mapped, stock is allocated oldest expiry first, and each "
                "packing list row shows its lot. Reads YYMMDD, YYYYMMDD, DDMMYY "
                "and MMYY."
            ),
        ),
        MappingField(
            "Batch",
            "Batch",
            hint=(
                "Lot or batch number. Shown per lot on packing lists, and keeps "
                "separate deliveries of one SKU apart."
            ),
        ),
    ),
}


class MappingDraft(PageContract):
    """One CSV's column mapping, stored as {csv column: internal name}.

    Both mapping drafts hold the SAME live config_data["column_mappings"] dict
    and write only their own sub-key into it, in place. Never clear() it and
    never rebuild it: whichever draft collect()s second would wipe the other's
    sub-key.
    """

    def __init__(
        self,
        kind: str,
        column_mappings: dict,
        client: str,
        file: FileColumns | None = None,
    ):
        self.kind = kind
        self.column_mappings = column_mappings
        self.client = client
        self.file = file
        self.fields = FIELDS[kind]
        by_internal = {internal: column for column, internal in self._stored().items()}
        self.chosen = {f.name: by_internal.get(f.name, "") for f in self.fields}

    def _stored(self) -> dict:
        stored = self.column_mappings.get(self.kind)
        return stored if isinstance(stored, dict) else {}

    def _field(self, name: str) -> MappingField | None:
        return next((f for f in self.fields if f.name == name), None)

    def set_file(self, file: FileColumns) -> None:
        """Offer this file's columns. It changes no mapping."""
        self.file = file

    def apply(self, action: str, args) -> bool:
        if action != "column" or not _shaped(args, str, str):
            return False
        name, column = args
        target = self._field(name)
        if target is None or self.file is None:
            return False
        if column == "":
            if target.required:
                return False
        elif column not in self.file.columns:
            return False
        if self.chosen[name] == column:
            return False
        if column:
            # The profile stores one field per column, so the column moves.
            for other in self.chosen:
                if self.chosen[other] == column:
                    self.chosen[other] = ""
            self._column_taken(column)
        self.chosen[name] = column
        return True

    def _column_taken(self, column: str) -> None:
        """A field now holds `column`. OrdersDraft lets go of it elsewhere."""

    def mappings(self) -> dict:
        """{csv column: internal name}, as stored.

        Entries for internal names this page has no row for are carried
        through untouched: dropping them is how the Expiry_Date and Batch
        mappings that drive FIFO were once deleted on every save. A field
        with no column is left out.
        """
        managed = {f.name for f in self.fields}
        result = {
            column: internal
            for column, internal in self._stored().items()
            if internal not in managed
        }
        for f in self.fields:
            if self.chosen[f.name]:
                result[self.chosen[f.name]] = f.name
        return result

    def _write_mapping(self) -> dict:
        """Write this draft's sub-key into the live dict and return the dict."""
        self.column_mappings["version"] = 2
        self.column_mappings[self.kind] = self.mappings()
        return self.column_mappings

    def collect(self) -> dict:
        return {"column_mappings": self._write_mapping()}

    def snapshot(self) -> str:
        """Only this draft's own mapping: column_mappings is one live dict
        shared by both mapping drafts, so a snapshot of collect() would mark
        both unsaved when either changes."""
        return json.dumps(self.mappings(), sort_keys=True, default=str)

    def _missing(self) -> MappingField | None:
        return next(
            (f for f in self.fields if f.required and not self.chosen[f.name]), None
        )

    def blocker(self) -> str | None:
        missing = self._missing()
        return f"Map {missing.label}" if missing else None

    def blocker_key(self) -> str:
        missing = self._missing()
        return f"field-{missing.name}" if missing else ""

    def _problem(self, f: MappingField) -> tuple[str, str]:
        """(sentence, example): the page draws the example in the mono face
        and closes the sentence after it."""
        if not f.required or self.chosen[f.name]:
            return "", ""
        if self.file is None:
            return (
                f"{f.label} is required. Use {READ_ACTION}, then choose its column.",
                "",
            )
        return f"{f.label} is required. Choose the column that holds it, e.g.", f.example

    def validate(self) -> tuple[bool, list[str]]:
        problems = []
        for f in self.fields:
            sentence, example = self._problem(f)
            if sentence:
                problems.append(f"{sentence} {example}." if example else sentence)
        return not problems, problems

    def _source(self) -> dict:
        if self.file is None:
            return {
                "lead": f"No CSV has been read. Use {READ_ACTION} to change a field.",
                "file": "",
                "tail": "",
            }
        return {
            "lead": "Columns read from",
            "file": self.file.name,
            "tail": ", the file loaded on Setup." if self.file.loaded else ".",
        }

    def _field_view(self, f: MappingField) -> dict:
        column = self.chosen[f.name]
        lacking = bool(column) and self.file is not None and column not in self.file.columns
        if lacking:
            sample = NOT_IN_FILE
        elif column and self.file is not None:
            sample = self.file.first_row.get(column, "")
        else:
            sample = ""
        problem, example = self._problem(f)
        return {
            "name": f.name,
            "label": f.label,
            "required": f.required,
            "column": column,
            "placeholder": "Choose column" if f.required else "Not imported",
            "sample": sample,
            "sample_missing": lacking,
            "problem": problem,
            "example": example,
            "hint": f.hint,
        }

    def _mapping_view(self) -> dict:
        labels = {f.name: f.label for f in self.fields}
        return {
            "kind": self.kind,
            "source": self._source(),
            "can_pick": self.file is not None,
            "columns": list(self.file.columns) if self.file is not None else [],
            "held": {
                column: labels[name] for name, column in self.chosen.items() if column
            },
            "fields": [self._field_view(f) for f in self.fields],
        }

    def view(self) -> dict:
        return {
            "page": self.kind,
            "title": MAPPING_TITLE[self.kind],
            "subtitle": (
                f"Which column of {self.client}'s {self.kind} CSV holds each field."
            ),
            "action": READ_ACTION,
            "mapping": self._mapping_view(),
        }


class StockDraft(MappingDraft):
    """Stock CSV columns, including the two that drive FIFO lot allocation."""

    def __init__(
        self, column_mappings: dict, client: str, file: FileColumns | None = None
    ):
        super().__init__("stock", column_mappings, client, file)


# --- orders: courier names and additional columns ----------------------------

ADDITIONAL_COLUMNS_UNREADABLE = object()
"""Passed as `fallback_additional_columns` when the client config could not be
read, so the draft can tell "there are none" from "we don't know" (ADR 0006).
Saving the first over the second would discard the profile's real list."""

COURIER_TEXT = (
    "A shipping method that contains the text on the left is filed under the "
    "courier on the right. Anything else keeps its own name."
)
COURIER_EMPTY = "No courier names yet. The built-in ones apply: DHL, DPD and PostOne."
ADDITIONAL_TEXT = (
    "Orders columns with no field, carried through the analysis under their own names."
)
ADDITIONAL_EMPTY = "None kept."
ADDITIONAL_UNKNOWN = (
    "The saved list couldn't be read, so saving leaves it as it is. "
    "Add a column to replace it."
)
NOT_FILLED_DOWN = "not filled down"


def _is_entry(value) -> bool:
    return isinstance(value, dict) and bool(value.get("csv_name"))


def _additional_entry(value: dict) -> dict:
    """A stored entry with every key discover_additional_columns reads."""
    name = str(value["csv_name"])
    return {
        "csv_name": name,
        "internal_name": value.get("internal_name")
        or name.strip().replace(" ", "_").replace("-", "_"),
        "enabled": bool(value.get("enabled", False)),
        "is_order_level": bool(value.get("is_order_level", True)),
        "exists_in_df": value.get("exists_in_df", True),
    }


def _courier_rows(courier_mappings) -> list[list[str]]:
    """One [text, code] row per stored pattern, in stored order.

    A legacy entry is {pattern: code}: the analysis still matches it, so it
    loads as a row instead of being dropped on the next save.
    """
    rows: list[list[str]] = []
    if not isinstance(courier_mappings, dict):
        return rows
    for code, data in courier_mappings.items():
        if isinstance(data, dict):
            rows.extend([str(text), str(code)] for text in data.get("patterns") or [])
        elif isinstance(data, str):
            rows.append([str(code), data])
    return rows


class OrdersDraft(MappingDraft):
    """Orders CSV columns, the courier names that resolve the shipping method
    those columns carry, and the additional columns kept beside them."""

    def __init__(
        self,
        column_mappings: dict,
        courier_mappings: dict,
        client: str,
        fallback_additional_columns=None,
        file: FileColumns | None = None,
    ):
        super().__init__("orders", column_mappings, client, file)
        self.courier_mappings = courier_mappings
        self.courier_rows = _courier_rows(courier_mappings)

        # ADR 0006: the list lives in column_mappings; a profile not saved
        # since Bundle 13 still has it only in the client config.
        source = (
            column_mappings.get("additional_columns")
            if "additional_columns" in column_mappings
            else fallback_additional_columns
        )
        # A client config that could not be read means the stored list is
        # unknown, not empty: collect() must leave it alone, not save [] over it.
        self.additional_known = source is not ADDITIONAL_COLUMNS_UNREADABLE
        if not self.additional_known:
            source = []
        self.entries = [_additional_entry(e) for e in (source or []) if _is_entry(e)]

    # --- edits ---------------------------------------------------------------

    def _row(self, text: str) -> int | None:
        if text.isdecimal() and int(text) < len(self.courier_rows):
            return int(text)
        return None

    def _entry(self, name: str) -> dict | None:
        return next((e for e in self.entries if e["csv_name"] == name), None)

    def apply(self, action: str, args) -> bool:
        if action == "column":
            return super().apply(action, args)
        if action == "courier_add" and _shaped(args):
            self.courier_rows.append(["", ""])
            return True
        if action in ("courier_pattern", "courier_code") and _shaped(args, str, str):
            row = self._row(args[0])
            side = 0 if action == "courier_pattern" else 1
            value = args[1] if side == 0 else args[1].strip()
            if row is None or (side == 1 and not value):
                return False
            if self.courier_rows[row][side] == value:
                return False
            self.courier_rows[row][side] = value
            return True
        if action == "courier_remove" and _shaped(args, str):
            row = self._row(args[0])
            if row is None:
                return False
            del self.courier_rows[row]
            return True
        if action == "column_add" and _shaped(args, str):
            return self._keep(args[0])
        if action == "column_remove" and _shaped(args, str):
            entry = self._entry(args[0])
            if entry is None or not entry["enabled"]:
                return False
            entry["enabled"] = False
            return True
        if action == "column_fill" and _shaped(args, str, bool):
            entry = self._entry(args[0])
            if entry is None or entry["is_order_level"] == args[1]:
                return False
            entry["is_order_level"] = args[1]
            return True
        return False

    def _keep(self, name: str) -> bool:
        """Keep a candidate: turn its entry on, or store a discovered one."""
        candidate = next(
            (e for e in self._discovered() if e["csv_name"] == name and not e["enabled"]),
            None,
        )
        if candidate is None:
            return False
        entry = self._entry(name)
        if entry is None:
            self.entries.append({**candidate, "enabled": True})
        else:
            entry["enabled"] = True
        # What the operator keeps supersedes a list that could not be read.
        self.additional_known = True
        return True

    def _column_taken(self, column: str) -> None:
        entry = self._entry(column)
        if entry is not None:
            entry["enabled"] = False

    # --- what is saved -------------------------------------------------------

    def couriers(self) -> dict:
        """courier_mappings as stored: codes in the order their first row
        appears. A row missing its text or its courier is left out."""
        result: dict[str, dict] = {}
        for text, code in self.courier_rows:
            text, code = text.strip(), code.strip()
            if not text or not code:
                continue
            patterns = result.setdefault(
                code, {"patterns": [], "case_sensitive": False}
            )["patterns"]
            if text not in patterns:
                patterns.append(text)
        return result

    def collect(self) -> dict:
        # Same live-dict contract as column_mappings: clear and refill in
        # place, so a removed courier does not survive the save.
        couriers = self.couriers()
        self.courier_mappings.clear()
        self.courier_mappings.update(couriers)

        mappings = self._write_mapping()
        if self.additional_known:
            mappings["additional_columns"] = [dict(e) for e in self.entries]
        return {"column_mappings": mappings, "courier_mappings": self.courier_mappings}

    def snapshot(self) -> str:
        return json.dumps(
            [super().snapshot(), self.couriers(), self.entries],
            sort_keys=True,
            default=str,
        )

    # --- what the page draws -------------------------------------------------

    def _discovered(self) -> list[dict]:
        """Every additional column there is to show.

        With a file read: its unmapped columns and the stored entries, each
        saying whether the file has it. With none: the stored entries. Nothing
        here is stored until the operator keeps it.
        """
        if self.file is None:
            return [dict(e) for e in self.entries]
        return discover_additional_columns(
            pd.DataFrame(columns=list(self.file.columns)),
            {"orders": self.mappings()},
            self.entries,
        )

    def _additional_view(self) -> dict:
        read = self.file is not None
        chips, candidates = [], []
        for entry in self._discovered():
            lacking = read and not entry["exists_in_df"]
            if entry["enabled"]:
                notes = [NOT_IN_FILE] if lacking else []
                if not entry["is_order_level"]:
                    notes.append(NOT_FILLED_DOWN)
                chips.append(
                    {
                        "name": entry["csv_name"],
                        "note": ", ".join(notes),
                        "fill": bool(entry["is_order_level"]),
                    }
                )
            else:
                candidates.append(
                    {"name": entry["csv_name"], "note": NOT_IN_FILE if lacking else ""}
                )
        if candidates:
            add_title = ""
        elif read:
            add_title = "Every column in this file is mapped or kept."
        else:
            add_title = f"Use {READ_ACTION} to list the file's unmapped columns."
        return {
            "text": ADDITIONAL_TEXT,
            "chips": chips,
            "candidates": candidates,
            "group": (
                f"Unmapped columns in {self.file.name}" if read else "Turned off earlier"
            ),
            "empty": ADDITIONAL_EMPTY,
            "notice": "" if self.additional_known else ADDITIONAL_UNKNOWN,
            "add_title": add_title,
        }

    def _couriers_view(self) -> dict:
        codes: list[str] = []
        for _text, code in self.courier_rows:
            if code and code not in codes:
                codes.append(code)
        return {
            "text": COURIER_TEXT,
            "rows": [{"text": text, "code": code} for text, code in self.courier_rows],
            "codes": codes,
            "empty": COURIER_EMPTY,
        }

    def _mapping_view(self) -> dict:
        view = super()._mapping_view()
        view["couriers"] = self._couriers_view()
        view["additional"] = self._additional_view()
        return view
