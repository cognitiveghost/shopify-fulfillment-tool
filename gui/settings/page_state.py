"""The values behind the settings pages the web tier draws (phase 7 spec section 4).

A draft is a settings page with no widget. It holds one page's values, takes
the page's edits through apply(), and meets PageContract, so SettingsWindow
saves and marks it exactly as it does a Qt page. view() is everything the web
page draws, sentences included: the page computes nothing. No Qt import.

apply(action, args) returns whether anything changed. The actions are the
spec's section 3.4: add one there before adding it here. The page sends
strings and booleans only; an edit of any other shape is dropped.
"""

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
