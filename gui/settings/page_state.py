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

from gui.settings.contract import PageContract


@dataclass(frozen=True)
class FileColumns:
    """A CSV's header and first row, as a mapping page shows them."""

    name: str  # the file's name, as the card shows it
    columns: tuple[str, ...]  # the header row, in file order
    first_row: dict[str, str] = field(default_factory=dict)  # "" when empty
    loaded: bool = False  # True: the file loaded on Setup. False: picked here


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
            stored = settings.get(f"{kind}_csv_delimiter", "auto")
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
        if not _WHOLE.fullmatch(self.threshold.strip()):
            found.append(("Set Low-stock threshold", "threshold", THRESHOLD_PROBLEM))
        return found

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
        bad_threshold = not _WHOLE.fullmatch(self.threshold.strip())
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
                    "problem": THRESHOLD_PROBLEM if bad_threshold else "",
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
