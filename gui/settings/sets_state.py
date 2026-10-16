"""The values behind the Sets page (phase 9 spec section 4).

A set is one SKU sold as several: the analysis replaces it with its component
SKUs before stock is allocated. SetsDraft holds config_data["set_decoders"],
takes the page's edits through apply(), and words everything the page draws.
No Qt import.
"""

import re
from pathlib import Path
from typing import ClassVar

from gui.settings.contract import FileProblem, PageContract
from gui.settings.page_state import _shaped
from shared.i18n import N_, _, _n
from shopify_tool.set_decoder import export_sets_to_csv, import_sets_from_csv

MAX_QUANTITY = 9999
CHIP_LIMIT = 6
LIST_LIMIT = 500

SUBTITLE = N_("A set SKU on an order is replaced by its components before stock is allocated.")
ADD_SET = N_("Add set")
NEW_SET = N_("New set")
EMPTY_TITLE = N_("No sets yet")
EMPTY_TEXT = N_("A set is one SKU sold as several. Add one, or import them all from a CSV.")
EMPTY_IMPORT = N_("Import from CSV…")
FILTER_PLACEHOLDER = N_("Filter by SKU or component")
IMPORT_HINT = N_("CSV columns: Set_SKU, Component_SKU, Component_Quantity")

NO_SKU = N_("Type the set's SKU.")
DUPLICATE_SKU = N_("Another set already has this SKU.")
NO_COMPONENT = N_("Add at least one component.")
QUANTITY_PROBLEM_TEMPLATE = N_("Type a whole number from 1 to {max}.")
QUANTITY_PROBLEM = QUANTITY_PROBLEM_TEMPLATE.format(max=MAX_QUANTITY)
NO_SETS_DETAIL = N_("Each row needs Set_SKU, Component_SKU and Component_Quantity.")

_KEY_UID = re.compile(r"set-(\d+)-")


def _text(value) -> str:
    return "" if value is None else str(value)


def whole_text(value) -> str:
    """A stored number as a field shows it: an integer with no fraction, so
    2, 2.0 and "2" all read "2". Anything else reads as str() gives it."""
    text = _text(value).strip()
    try:
        number = float(text)
    except ValueError:
        return text
    return str(int(number)) if number.is_integer() else text


def _quantity(text: str) -> int | None:
    """A component's quantity, or None when it is not a whole number in range."""
    text = text.strip()
    if not text.isdecimal():
        return None
    number = int(text)
    return number if 1 <= number <= MAX_QUANTITY else None


def _component(stored: dict) -> dict:
    return {
        "sku": _text(stored.get("sku")),
        "quantity": whole_text(stored.get("quantity", 1)),
        "stored": dict(stored),
    }


class SetsDraft(PageContract):
    """Set definitions, stored under config_data["set_decoders"]."""

    # kind -> the file dialog's title
    imports: ClassVar[dict[str, str]] = {
        "sets-merge": N_("Import Sets from CSV"),
        "sets-replace": N_("Import Sets from CSV"),
    }
    # kind -> (the file dialog's title, the name it offers)
    exports: ClassVar[dict[str, tuple[str, str]]] = {
        "sets": (N_("Export Sets to CSV"), "sets_export.csv")
    }
    # kind -> the headline of a failure that is not a FileProblem
    import_failed: ClassVar[dict[str, str]] = {
        "sets-merge": N_("The sets weren't imported"),
        "sets-replace": N_("The sets weren't imported"),
    }
    export_failed: ClassVar[dict[str, str]] = {"sets": N_("The sets weren't exported")}

    def __init__(self, set_decoders: dict):
        # The live dict: collect() refills it in place (PageContract).
        self._live = set_decoders
        self._next = 0
        self.filter = ""
        self.open_uid: str | None = None
        self.entries = [self._entry(sku, parts) for sku, parts in set_decoders.items()]

    def _uid(self) -> str:
        self._next += 1
        return str(self._next)

    def _entry(self, sku, components) -> dict:
        components = components if isinstance(components, list) else []
        return {
            "uid": self._uid(),
            "sku": _text(sku),
            "components": [_component(c) for c in components if isinstance(c, dict)],
        }

    def _find(self, uid: str) -> dict | None:
        return next((e for e in self.entries if e["uid"] == uid), None)

    # --- the edits ---------------------------------------------------------

    def apply(self, action: str, args) -> bool:
        if action == "filter" and _shaped(args, str):
            if self.filter == args[0]:
                return False
            self.filter = args[0]
            return True
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
        if action == "set_add" and _shaped(args):
            entry = {
                "uid": self._uid(),
                "sku": "",
                "components": [_component({"sku": "", "quantity": 1})],
            }
            # First, so it is in view among hundreds.
            self.entries.insert(0, entry)
            self.open_uid = entry["uid"]
            return True
        if action == "set_delete" and _shaped(args, str):
            entry = self._find(args[0])
            if entry is None:
                return False
            self.entries.remove(entry)
            if self.open_uid == entry["uid"]:
                self.open_uid = None
            return True
        if action == "set_sku" and _shaped(args, str, str):
            entry = self._find(args[0])
            if entry is None or entry["sku"] == args[1]:
                return False
            entry["sku"] = args[1]
            return True
        if action == "comp_add" and _shaped(args, str):
            entry = self._find(args[0])
            if entry is None:
                return False
            entry["components"].append(_component({"sku": "", "quantity": 1}))
            return True
        if action == "comp_remove" and _shaped(args, str, str):
            entry, at = self._component_at(args[0], args[1])
            if at is None:
                return False
            del entry["components"][at]
            return True
        if action in ("comp_sku", "comp_quantity") and _shaped(args, str, str, str):
            entry, at = self._component_at(args[0], args[1])
            name = action.removeprefix("comp_")
            if at is None or entry["components"][at][name] == args[2]:
                return False
            entry["components"][at][name] = args[2]
            return True
        return False

    def _component_at(self, uid: str, position: str) -> tuple[dict | None, int | None]:
        entry = self._find(uid)
        if entry is None or not position.isdecimal():
            return entry, None
        at = int(position)
        return entry, at if at < len(entry["components"]) else None

    # --- what blocks a save ------------------------------------------------

    def _duplicates(self) -> set[str]:
        """The uids of the sets whose SKU an earlier set has."""
        seen, found = set(), set()
        for entry in self.entries:
            sku = entry["sku"].strip()
            if sku and sku in seen:
                found.add(entry["uid"])
            seen.add(sku)
        return found

    def _problems(self, entry: dict, duplicates: set[str]) -> list[tuple[str, str]]:
        """(sentence, data-key) for each thing on this set that blocks a save."""
        key = f"set-{entry['uid']}"
        found = []
        if not entry["sku"].strip():
            found.append((_(NO_SKU), f"{key}-sku"))
        elif entry["uid"] in duplicates:
            found.append((_(DUPLICATE_SKU), f"{key}-sku"))
        named = [
            (c, part) for c, part in enumerate(entry["components"]) if part["sku"].strip()
        ]
        if not named:
            found.append((_(NO_COMPONENT), f"{key}-comp-add"))
        found.extend(
            (_(QUANTITY_PROBLEM_TEMPLATE, max=MAX_QUANTITY), f"{key}-c{c}-quantity")
            for c, part in named
            if _quantity(part["quantity"]) is None
        )
        return found

    def _blocking(self) -> list[tuple[dict, list[tuple[str, str]]]]:
        duplicates = self._duplicates()
        return [
            (entry, problems)
            for entry in self.entries
            if (problems := self._problems(entry, duplicates))
        ]

    def blocker(self) -> str | None:
        blocking = self._blocking()
        if not blocking:
            return None
        sku = blocking[0][0]["sku"].strip()
        return _("Fix set “{sku}”", sku=sku) if sku else _("Fix the new set")

    def blocker_key(self) -> str:
        blocking = self._blocking()
        return blocking[0][1][0][1] if blocking else ""

    def validate(self) -> tuple[bool, list[str]]:
        lines = []
        for entry, problems in self._blocking():
            sku = entry["sku"].strip()
            who = _("Set “{sku}”", sku=sku) if sku else _(NEW_SET)
            lines.extend(_("{who}: {sentence}", who=who, sentence=sentence) for sentence, _key in problems)
        return not lines, lines

    # --- what is saved -----------------------------------------------------

    def stored(self) -> dict:
        """set_decoders as stored. A set or a component with no SKU is left
        out; a quantity that blocks the save is written as typed."""
        result = {}
        for entry in self.entries:
            sku = entry["sku"].strip()
            if not sku:
                continue
            result[sku] = [
                {
                    **part["stored"],
                    "sku": part["sku"].strip(),
                    "quantity": part["quantity"]
                    if _quantity(part["quantity"]) is None
                    else _quantity(part["quantity"]),
                }
                for part in entry["components"]
                if part["sku"].strip()
            ]
        return result

    def collect(self) -> dict:
        stored = self.stored()
        self._live.clear()
        self._live.update(stored)
        return {"set_decoders": self._live}

    # --- files -------------------------------------------------------------

    def import_csv(self, kind: str, path, update: bool = False) -> tuple[str, bool]:
        """Import a sets CSV. (the toast's text, whether "Update them" applies)."""
        if kind not in self.imports:
            raise ValueError(f"Unknown import: {kind}")
        name = Path(path).name
        imported = import_sets_from_csv(str(path))
        if not imported:
            raise FileProblem(_("No sets found in {file}", file=name), _(NO_SETS_DETAIL))
        self.open_uid = None
        if kind == "sets-replace":
            self.entries = []
        listed = {entry["sku"].strip(): entry for entry in self.entries}
        for sku, components in imported.items():
            fresh = self._entry(sku, components)
            if sku in listed:
                listed[sku]["components"] = fresh["components"]
            else:
                self.entries.append(fresh)
        if kind == "sets-replace":
            return _("Replaced all sets with {count} from {file}", count=len(imported), file=name), False
        sets = _n("{n} set", "{n} sets", len(imported))
        return _("Imported {sets} from {file}", sets=sets, file=name), False

    def export_csv(self, kind: str, path) -> str:
        if kind not in self.exports:
            raise ValueError(f"Unknown export: {kind}")
        stored = self.stored()
        export_sets_to_csv(stored, str(path))
        sets = _n("{n} set", "{n} sets", len(stored))
        return _("Exported {sets} to {file}", sets=sets, file=Path(path).name)

    # --- what the page draws -----------------------------------------------

    def _listed(self) -> list[dict]:
        needle = self.filter.strip().casefold()
        if not needle:
            return list(self.entries)
        return [
            entry
            for entry in self.entries
            if entry["uid"] == self.open_uid
            or needle in entry["sku"].casefold()
            or any(needle in part["sku"].casefold() for part in entry["components"])
        ]

    def _row(self, entry: dict, duplicates: set[str]) -> dict:
        problems = self._problems(entry, duplicates)
        by_key = {key: sentence for sentence, key in reversed(problems)}
        key = f"set-{entry['uid']}"
        named = [part for part in entry["components"] if part["sku"].strip()]
        is_open = entry["uid"] == self.open_uid
        editor = None
        if is_open:
            editor = {
                "sku_problem": by_key.get(f"{key}-sku", ""),
                "components_problem": by_key.get(f"{key}-comp-add", ""),
                "components": [
                    {
                        "sku": part["sku"],
                        "quantity": part["quantity"],
                        "problem": by_key.get(f"{key}-c{c}-quantity", ""),
                        "invalid": f"{key}-c{c}-quantity" in by_key,
                    }
                    for c, part in enumerate(entry["components"])
                ],
            }
        more = len(named) - CHIP_LIMIT
        return {
            "uid": entry["uid"],
            "sku": entry["sku"],
            "label": entry["sku"].strip() or _(NEW_SET),
            "open": is_open,
            "chips": [f"{part['sku'].strip()} ×{part['quantity']}" for part in named[:CHIP_LIMIT]],
            "more_chips": _("+{count} more", count=more) if more > 0 else "",
            "problem": problems[0][0] if problems else "",
            "editor": editor,
        }

    def view(self) -> dict:
        empty = None
        if not self.entries:
            empty = {
                "title": _(EMPTY_TITLE),
                "text": _(EMPTY_TEXT),
                "action": _(ADD_SET),
                "import": _(EMPTY_IMPORT),
            }
        listed = self._listed()
        duplicates = self._duplicates()
        no_hits = ""
        if self.entries and not listed:
            no_hits = _("No set matches “{query}”.", query=self.filter.strip())
        more = ""
        if len(listed) > LIST_LIMIT:
            more = _(
                "Showing {shown} of {total}. Filter to find the rest.",
                shown=LIST_LIMIT,
                total=len(listed),
            )
        shown = listed[:LIST_LIMIT]
        # The open set is drawn even past the limit: the footer's link opens it.
        shown += [entry for entry in listed[LIST_LIMIT:] if entry["uid"] == self.open_uid]
        return {
            "page": "sets",
            "title": _("Sets"),
            "subtitle": _(SUBTITLE),
            "action": _(ADD_SET) if self.entries else "",
            "sets": {
                "empty": empty,
                "filter": self.filter,
                "filter_placeholder": _(FILTER_PLACEHOLDER),
                "count": _n("{n} set", "{n} sets", len(self.entries)),
                "no_hits": no_hits,
                "more": more,
                "can_export": bool(self.stored()),
                "import_hint": _(IMPORT_HINT),
                "rows": [self._row(entry, duplicates) for entry in shown],
            },
        }
