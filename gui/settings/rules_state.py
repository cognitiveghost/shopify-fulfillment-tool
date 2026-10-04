"""The rules behind the Rules page the web tier draws (phase 8 spec section 4).

RulesDraft is a draft like page_state.py's: a settings page with no widget.
It holds the rules, takes the page's edits through apply(), and meets
PageContract, so SettingsWindow saves and marks it like any other page.
view() is everything the page draws, sentences included: the page computes
nothing.

A rule is addressed by a uid the draft hands out when it loads or adds one.
The uid is never stored. Steps, conditions and actions are addressed by their
position inside the rule. The actions are the spec's section 3.3: add one
there before adding it here.
"""

import copy
import functools
import re
from typing import ClassVar

from gui.rule_validator import condition_error, validate_list
from gui.settings.contract import PageContract
from gui.settings.fields import ACTION_TYPES, CONDITION_OPERATORS
from gui.settings.page_state import _shaped
from shopify_tool.core import get_unique_column_values
from shopify_tool.rules import RuleEngine, _parse_date_safe
from shopify_tool.stock_ledger import NOT_FULFILLABLE
from shopify_tool.tag_manager import _normalize_tag_categories

LEVELS = ("article", "order")
COMMON_FIELDS = (
    "Order_Number",
    "Order_Type",
    "SKU",
    "Product_Name",
    "Quantity",
    "Stock",
    "Final_Stock",
    "Shipping_Provider",
    "Shipping_Method",
    "Destination_Country",
)
VALUELESS_OPERATORS = ("is empty", "is not empty")
DATE_OPERATORS = ("date before", "date after", "date equals")
LIST_OPERATORS = ("in list", "not in list")
EQUALITY_OPERATORS = ("equals", "does not equal")
# ponytail: a column's first 200 values, sorted. A column with more (order
# numbers) offers no complete list; the field takes any text. Filter on the
# typed text in Python if that stops being enough.
SUGGESTION_LIMIT = 200
MAX_QUANTITY = 9999

SUBTITLE = "Change orders at the end of each analysis. Rules run top to bottom."
ADD_RULE = "Add rule"
EMPTY_TITLE = "No rules yet"
EMPTY_TEXT = "Rules change orders at the end of each analysis, e.g. tag VIP orders."
NEW_RULE_NAME = "New rule"
UNNAMED = "Unnamed rule"
CLEAR_FILTER = "Clear the filter to reorder"
GROUPS = {
    "article": ("Article rules", "Check one order line at a time."),
    "order": ("Order rules", "Check the whole order. Run after every article rule."),
}
LEVEL_LABEL = {"article": "Article", "order": "Order"}
LEVEL_HINT = {
    "article": "Checks one order line at a time.",
    "order": "Checks the whole order. Runs after every article rule.",
}
NO_CONDITION = "No condition yet, so this rule never matches."
NO_ACTION = "No action yet."
TEST_NO_ANALYSIS = "Run an analysis first. Test needs its orders."
TEST_NO_CONDITION = "Add a condition first."
TEST_BLOCKED = "Fix the marked value first."
NOT_AVAILABLE = "Not available"
NO_FIELD = "Choose a field. Until then this condition never matches."
NO_DATE = "Pick a date. Until then this condition never matches."
QUANTITY_PROBLEM = f"Type a whole number from 1 to {MAX_QUANTITY}."
HOLD_HINT = "Holds every line of the order and returns its stock."
RETIRED_ONE = "Writes the Status_Note text, not a tag. Use Add internal tag for a real tag."
RETIRED_MANY = "Writes the Status_Note text, not tags. Use one Add internal tag per tag."
NO_OPERATOR = "This condition has no operator, so it never matches."
UNKNOWN_ACTION = "This version does not know this action, so it does nothing."

ACTION_LABELS = {
    "ADD_INTERNAL_TAG": "Add internal tag",
    "REMOVE_INTERNAL_TAG": "Remove internal tag",
    "SET_STATUS": "Hold the order",
    "COPY_FIELD": "Copy field",
    "CALCULATE": "Calculate",
    "ALERT_NOTIFICATION": "Log an alert",
    "ADD_PRODUCT": "Add bonus line",
    "ADD_TAG": "Add status note (retired)",
    "ADD_ORDER_TAG": "Add status note (retired)",
    "SET_MULTI_TAGS": "Add status notes (retired)",
}
# (stored value, the menu's label, the summary's sign)
OPERATIONS = (
    ("add", "plus", "+"),
    ("subtract", "minus", "−"),
    ("multiply", "times", "×"),
    ("divide", "divided by", "÷"),
)
SEVERITIES = (("info", "Info"), ("warning", "Warning"), ("error", "Error"))
_CHOICES = {
    "operation": [(value, label) for value, label, _sign in OPERATIONS],
    "severity": list(SEVERITIES),
}
_SIGN = {value: sign for value, _label, sign in OPERATIONS}

# type -> its parameters, in the order the row draws them:
# (name, kind, placeholder, the word or sign drawn before it).
_TAG = (("value", "suggest", "Tag", ""),)
_NOTE = (("value", "text", "Value", ""),)
ACTION_PARAMS = {
    "ADD_INTERNAL_TAG": _TAG,
    "REMOVE_INTERNAL_TAG": _TAG,
    "SET_STATUS": (),
    "COPY_FIELD": (
        ("source", "field", "", ""),
        ("target", "text", "Target column", "→"),
    ),
    "CALCULATE": (
        ("field1", "field", "", ""),
        ("operation", "choice", "", ""),
        ("field2", "field", "", ""),
        ("target", "text", "Result column", "→"),
    ),
    "ALERT_NOTIFICATION": (
        ("message", "text", "Alert message", ""),
        ("severity", "choice", "", ""),
    ),
    "ADD_PRODUCT": (
        ("sku", "text", "Product SKU", ""),
        ("quantity", "number", "", "×"),
    ),
    "ADD_TAG": _NOTE,
    "ADD_ORDER_TAG": _NOTE,
    "SET_MULTI_TAGS": (("value", "text", "TAG1, TAG2, TAG3", ""),),
}

_PLACEHOLDER = {
    "in list": "Value1, Value2, Value3",
    "not in list": "Value1, Value2, Value3",
    "between": "10-100",
    "not between": "10-100",
    "matches regex": "^SKU-\\d{4}$",
    "does not match regex": "^SKU-\\d{4}$",
}
_RULE_KEYS = frozenset(
    {"name", "level", "enabled", "steps", "priority", "conditions", "match", "actions"}
)
_KEY_UID = re.compile(r"rule-(\d+)-")


def rule_fields(level: str, analysis_df) -> list[tuple[str, list[str]]]:
    """The fields a condition on a rule of this level can read, in groups.

    Order fields come from RuleEngine.ORDER_LEVEL_FIELDS, so the page cannot
    drift from what the engine dispatches on, and only an order rule gets
    them: on an article rule they are never columns.
    """
    groups = []
    if level == "order":
        groups.append(("Order fields", list(RuleEngine.ORDER_LEVEL_FIELDS)))
    groups.append(("Common fields", list(COMMON_FIELDS)))
    if analysis_df is not None and not analysis_df.empty:
        other = sorted(
            column
            for column in map(str, analysis_df.columns)
            if not column.startswith("_") and column not in COMMON_FIELDS
        )
        if other:
            groups.append(("Other fields in this analysis", other))
    return groups


@functools.lru_cache(maxsize=512)
def iso_date(text: str) -> str:
    """A stored date as YYYY-MM-DD; "" when the engine cannot read it.
    Remembered: the parser logs every value it cannot read."""
    parsed = _parse_date_safe(text)
    return "" if parsed is None else parsed.strftime("%Y-%m-%d")


def value_kind(operator: str) -> str:
    """The control a condition's value takes: "none", "date" or "text"."""
    if operator in VALUELESS_OPERATORS:
        return "none"
    if operator in DATE_OPERATORS:
        return "date"
    return "text"


def _text(value) -> str:
    return "" if value is None else str(value)


def _kind(action: dict) -> str:
    """The action's type as the engine dispatches on it."""
    return _text(action.get("type")).upper()


def _valid_quantity(value) -> bool:
    try:
        number = int(_text(value).strip())
    except ValueError:
        return False
    return 1 <= number <= MAX_QUANTITY


def _at(items: list, position: str):
    """items[position], where the position arrives as text; None when it is
    not a position in the list."""
    if not position.isdigit() or int(position) >= len(items):
        return None
    return items[int(position)]


def _empty_step() -> dict:
    return {"conditions": [], "match": "ALL", "actions": []}


def _loaded_condition(stored: dict) -> dict:
    condition = dict(stored)
    condition["field"] = _text(stored.get("field"))
    condition["operator"] = _text(stored.get("operator"))
    condition["value"] = stored.get("value", "")
    return condition


def _loaded_action(stored: dict) -> dict:
    action = dict(stored)
    action["type"] = _text(stored.get("type"))
    kind = _kind(action)
    if kind == "SET_STATUS":
        # A rule can only hold an order (spec 2026-09-26 D3): a stale value
        # loads as the hold.
        action["value"] = NOT_FULFILLABLE
    elif kind == "SET_MULTI_TAGS":
        tags = action.pop("tags", None) or action.get("value", "")
        action["value"] = (
            ", ".join(map(str, tags)) if isinstance(tags, list) else _text(tags)
        )
    elif kind == "ADD_PRODUCT":
        action.setdefault("quantity", 1)
    return action


def _loaded_step(stored: dict) -> dict:
    return {
        "conditions": [
            _loaded_condition(c) for c in stored.get("conditions") or [] if isinstance(c, dict)
        ],
        # As the engine reads it: upper-cased, and anything but ANY is ALL.
        "match": "ANY" if _text(stored.get("match", "ALL")).upper() == "ANY" else "ALL",
        "actions": [
            _loaded_action(a) for a in stored.get("actions") or [] if isinstance(a, dict)
        ],
    }


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def _part(kind: str, text) -> dict:
    return {"t": kind, "v": _text(text)}


def _action_parts(action: dict) -> list[dict]:
    """One action as the words and chips of a summary line."""
    kind = _kind(action)

    def chips(*values) -> list[dict]:
        return [_part("chip", v) for v in values if _text(v) != ""]

    if kind in ("ADD_INTERNAL_TAG", "REMOVE_INTERNAL_TAG"):
        return [_part("text", ACTION_LABELS[kind]), *chips(action.get("value"))]
    if kind == "SET_STATUS":
        return [_part("text", ACTION_LABELS[kind])]
    if kind == "COPY_FIELD":
        return [
            _part("text", "Copy"),
            *chips(action.get("source")),
            _part("text", "to"),
            *chips(action.get("target")),
        ]
    if kind == "CALCULATE":
        sign = _SIGN.get(_text(action.get("operation")), "?")
        sum_text = f"{_text(action.get('field1'))} {sign} {_text(action.get('field2'))}"
        return [
            _part("text", "Calculate"),
            _part("chip", sum_text),
            _part("text", "into"),
            *chips(action.get("target")),
        ]
    if kind == "ALERT_NOTIFICATION":
        return [_part("text", ACTION_LABELS[kind]), *chips(action.get("message"))]
    if kind == "ADD_PRODUCT":
        line = f"{_text(action.get('sku'))} ×{_text(action.get('quantity', 1))}"
        return [_part("text", ACTION_LABELS[kind]), _part("chip", line)]
    if kind in ("ADD_TAG", "ADD_ORDER_TAG"):
        return [_part("text", "Add status note"), *chips(action.get("value"))]
    if kind == "SET_MULTI_TAGS":
        return [_part("text", "Add status notes"), *chips(action.get("value"))]
    return [_part("text", _text(action.get("type")))]


class RulesDraft(PageContract):
    """The rule engine's rules, stored under config_data["rules"]."""

    def __init__(self, rules: list, analysis_df=None, tag_categories: dict | None = None):
        self.analysis_df = analysis_df
        # ponytail: the stored dict, which the Tag categories page writes only
        # when it is collected. A tag added there may not be among the
        # suggestions yet; the field takes any text, so it is still typeable.
        self._tag_categories = tag_categories or {}
        self._next_uid = 0
        self.rules = [
            self._loaded(rule)
            for rule in RuleEngine.execution_order(
                [copy.deepcopy(r) for r in rules or [] if isinstance(r, dict)]
            )
        ]
        self.filter = ""
        self.open_uid: str | None = None

    # --- the model ---------------------------------------------------------

    def _uid(self) -> str:
        self._next_uid += 1
        return str(self._next_uid)

    def _loaded(self, stored: dict) -> dict:
        steps = stored.get("steps")
        if not (isinstance(steps, list) and steps):
            # The old format: one step's worth of keys at the rule's root.
            steps = [stored]
        return {
            "uid": self._uid(),
            "name": _text(stored.get("name")),
            "level": "order" if stored.get("level") == "order" else "article",
            "enabled": stored.get("enabled", True) is not False,
            "steps": [_loaded_step(s) for s in steps if isinstance(s, dict)]
            or [_empty_step()],
            "extra": {k: v for k, v in stored.items() if k not in _RULE_KEYS},
        }

    def _stored(self, rule: dict, priority: int | None = None) -> dict:
        """One rule as the profile holds it. Save and Test both build through
        here, so a test runs exactly what Save would store."""
        stored = {"name": rule["name"]}
        if priority is not None:
            stored["priority"] = priority
        stored["level"] = rule["level"]
        if not rule["enabled"]:
            # Only when off: a rule that is on is written as it always was.
            stored["enabled"] = False
        stored["steps"] = copy.deepcopy(rule["steps"])
        stored.update(copy.deepcopy(rule["extra"]))
        return stored

    def _rule(self, uid: str) -> dict | None:
        return next((rule for rule in self.rules if rule["uid"] == uid), None)

    def _step(self, uid: str, s: str) -> tuple[dict | None, dict | None]:
        rule = self._rule(uid)
        return rule, (None if rule is None else _at(rule["steps"], s))

    def _level_rules(self, level: str) -> list[dict]:
        return [rule for rule in self.rules if rule["level"] == level]

    def _place(self, rule: dict, position: int) -> None:
        """Put a rule that is not in the list at `position` among the rules
        of its level. Article rules come first, as they run first."""
        before = 0 if rule["level"] == "article" else len(self._level_rules("article"))
        self.rules.insert(before + position, rule)

    def _fields(self, level: str) -> list[str]:
        return [f for _label, fields in rule_fields(level, self.analysis_df) for f in fields]

    def configured_tags(self) -> list[str]:
        """Every tag the tag categories name, sorted. The analyser's own
        system tags are left out on purpose: offering them invites rules that
        fight it. The field takes any text, so they stay typeable."""
        tags = set()
        for category in _normalize_tag_categories(self._tag_categories).values():
            tags.update(category.get("tags", []))
        return sorted(tags)

    def _has_analysis(self) -> bool:
        return self.analysis_df is not None and not self.analysis_df.empty

    def _resolvable(self, field: str, level: str) -> bool:
        """Whether the engine can evaluate a condition on this field. It fails
        one it cannot closed, so the rule quietly stops firing."""
        if not field:
            return False
        if field in self._fields(level):
            return True
        if not self._has_analysis():
            # The offered list is then only a guess at the columns, and a
            # client's own column would be flagged falsely. An order field on
            # an article rule never resolves, whatever the data.
            return field not in RuleEngine.ORDER_LEVEL_FIELDS
        return False

    def _iso_date(self, value) -> str:
        return iso_date(_text(value))

    # --- the edits ---------------------------------------------------------

    # action -> (the types of its arguments, the method that applies it)
    _ACTIONS: ClassVar[dict[str, tuple[tuple, str]]] = {
        "filter": ((str,), "_set_filter"),
        "open": ((str,), "_open"),
        "close": ((), "_close"),
        "reveal": ((str,), "_reveal"),
        "rule_add": ((), "_rule_add"),
        "rule_duplicate": ((str,), "_rule_duplicate"),
        "rule_delete": ((str,), "_rule_delete"),
        "rule_move": ((str, str), "_rule_move"),
        "rule_move_to": ((str, str), "_rule_move_to"),
        "rule_enabled": ((str, bool), "_rule_enabled"),
        "rule_name": ((str, str), "_rule_name"),
        "rule_level": ((str, str), "_rule_level"),
        "step_add": ((str,), "_step_add"),
        "step_remove": ((str, str), "_step_remove"),
        "step_match": ((str, str, str), "_step_match"),
        "cond_add": ((str, str), "_cond_add"),
        "cond_remove": ((str, str, str), "_cond_remove"),
        "cond_field": ((str, str, str, str), "_cond_field"),
        "cond_operator": ((str, str, str, str), "_cond_operator"),
        "cond_value": ((str, str, str, str), "_cond_value"),
        "action_add": ((str, str), "_action_add"),
        "action_remove": ((str, str, str), "_action_remove"),
        "action_type": ((str, str, str, str), "_action_type"),
        "action_param": ((str, str, str, str, str), "_action_param"),
    }

    def apply(self, action: str, args) -> bool:
        known = self._ACTIONS.get(action)
        if known is None or not _shaped(args, *known[0]):
            return False
        return bool(getattr(self, known[1])(*args))

    def _set_filter(self, text: str) -> bool:
        if text == self.filter:
            return False
        self.filter = text
        return True

    def _open(self, uid: str) -> bool:
        if self._rule(uid) is None or self.open_uid == uid:
            return False
        self.open_uid = uid
        return True

    def _close(self) -> bool:
        if self.open_uid is None:
            return False
        self.open_uid = None
        return True

    def _reveal(self, key: str) -> bool:
        found = _KEY_UID.match(key)
        return bool(found) and self._open(found.group(1))

    def _rule_add(self) -> bool:
        rule = {
            "uid": self._uid(),
            "name": NEW_RULE_NAME,
            "level": "article",
            "enabled": True,
            "steps": [_empty_step()],
            "extra": {},
        }
        self._place(rule, len(self._level_rules("article")))
        self.open_uid = rule["uid"]
        return True

    def _rule_duplicate(self, uid: str) -> bool:
        rule = self._rule(uid)
        if rule is None:
            return False
        twin = copy.deepcopy(rule)
        twin["uid"] = self._uid()
        twin["name"] = f"{rule['name']} copy".strip()
        self.rules.insert(self.rules.index(rule) + 1, twin)
        return True

    def _rule_delete(self, uid: str) -> bool:
        rule = self._rule(uid)
        if rule is None:
            return False
        self.rules.remove(rule)
        if self.open_uid == uid:
            self.open_uid = None
        return True

    def _rule_move(self, uid: str, direction: str) -> bool:
        rule = self._rule(uid)
        if rule is None or direction not in ("up", "down"):
            return False
        position = self._level_rules(rule["level"]).index(rule)
        target = position + (-1 if direction == "up" else 1)
        return target >= 0 and self._rule_move_to(uid, str(target))

    def _rule_move_to(self, uid: str, position: str) -> bool:
        rule = self._rule(uid)
        if rule is None or not position.isdigit():
            return False
        group = self._level_rules(rule["level"])
        target = int(position)
        if target >= len(group) or target == group.index(rule):
            return False
        self.rules.remove(rule)
        self._place(rule, target)
        return True

    def _rule_enabled(self, uid: str, on: bool) -> bool:
        rule = self._rule(uid)
        if rule is None or rule["enabled"] == on:
            return False
        rule["enabled"] = on
        return True

    def _rule_name(self, uid: str, text: str) -> bool:
        rule = self._rule(uid)
        if rule is None or rule["name"] == text:
            return False
        rule["name"] = text
        return True

    def _rule_level(self, uid: str, level: str) -> bool:
        rule = self._rule(uid)
        if rule is None or level not in LEVELS or rule["level"] == level:
            return False
        self.rules.remove(rule)
        rule["level"] = level
        self._place(rule, len(self._level_rules(level)))
        return True

    def _step_add(self, uid: str) -> bool:
        rule = self._rule(uid)
        if rule is None:
            return False
        rule["steps"].append(_empty_step())
        return True

    def _step_remove(self, uid: str, s: str) -> bool:
        rule, step = self._step(uid, s)
        if step is None or s == "0":
            return False
        rule["steps"].remove(step)
        return True

    def _step_match(self, uid: str, s: str, match: str) -> bool:
        _rule, step = self._step(uid, s)
        if step is None or match not in ("ALL", "ANY") or step["match"] == match:
            return False
        step["match"] = match
        return True

    def _cond_add(self, uid: str, s: str) -> bool:
        rule, step = self._step(uid, s)
        if step is None:
            return False
        step["conditions"].append(
            {
                "field": self._fields(rule["level"])[0],
                "operator": CONDITION_OPERATORS[0],
                "value": "",
            }
        )
        return True

    def _condition(self, uid: str, s: str, c: str) -> tuple[dict | None, dict | None]:
        rule, step = self._step(uid, s)
        return rule, (None if step is None else _at(step["conditions"], c))

    def _cond_remove(self, uid: str, s: str, c: str) -> bool:
        _rule, step = self._step(uid, s)
        condition = None if step is None else _at(step["conditions"], c)
        if condition is None:
            return False
        del step["conditions"][int(c)]
        return True

    def _cond_field(self, uid: str, s: str, c: str, field: str) -> bool:
        rule, condition = self._condition(uid, s, c)
        if (
            condition is None
            or field not in self._fields(rule["level"])
            or condition["field"] == field
        ):
            return False
        condition["field"] = field
        return True

    def _cond_operator(self, uid: str, s: str, c: str, operator: str) -> bool:
        _rule, condition = self._condition(uid, s, c)
        if (
            condition is None
            or operator not in CONDITION_OPERATORS
            or condition["operator"] == operator
        ):
            return False
        if value_kind(operator) != value_kind(condition["operator"]):
            # A date is no use to a text operator, and the other way round.
            condition["value"] = ""
        condition["operator"] = operator
        return True

    def _cond_value(self, uid: str, s: str, c: str, text: str) -> bool:
        _rule, condition = self._condition(uid, s, c)
        if condition is None or condition["value"] == text:
            return False
        condition["value"] = text
        return True

    def _default_action(self, kind: str) -> dict:
        first = self._fields("article")[0]
        defaults = {
            "ADD_INTERNAL_TAG": {"value": ""},
            "REMOVE_INTERNAL_TAG": {"value": ""},
            "SET_STATUS": {"value": NOT_FULFILLABLE},
            "COPY_FIELD": {"source": first, "target": ""},
            "CALCULATE": {
                "operation": "add",
                "field1": first,
                "field2": first,
                "target": "",
            },
            "ALERT_NOTIFICATION": {"message": "", "severity": "info"},
            "ADD_PRODUCT": {"sku": "", "quantity": 1},
        }
        return {"type": kind, **defaults[kind]}

    def _action_add(self, uid: str, s: str) -> bool:
        _rule, step = self._step(uid, s)
        if step is None:
            return False
        step["actions"].append(self._default_action(ACTION_TYPES[0]))
        return True

    def _action(self, uid: str, s: str, a: str) -> tuple[dict | None, dict | None]:
        _rule, step = self._step(uid, s)
        return step, (None if step is None else _at(step["actions"], a))

    def _action_remove(self, uid: str, s: str, a: str) -> bool:
        step, action = self._action(uid, s, a)
        if action is None:
            return False
        del step["actions"][int(a)]
        return True

    def _action_type(self, uid: str, s: str, a: str, kind: str) -> bool:
        step, action = self._action(uid, s, a)
        if action is None or kind not in ACTION_TYPES or _kind(action) == kind:
            return False
        step["actions"][int(a)] = self._default_action(kind)
        return True

    def _action_param(self, uid: str, s: str, a: str, name: str, text: str) -> bool:
        _step, action = self._action(uid, s, a)
        if action is None:
            return False
        spec = next(
            (p for p in ACTION_PARAMS.get(_kind(action), ()) if p[0] == name), None
        )
        if spec is None:
            return False
        value = text
        if spec[1] == "field" and text not in self._fields("article"):
            return False
        if spec[1] == "choice" and text not in dict(_CHOICES[name]):
            return False
        if spec[1] == "number" and _valid_quantity(text):
            value = int(text.strip())
        if name in action and action[name] == value and type(action[name]) is type(value):
            return False
        action[name] = value
        return True

    # --- what is wrong, and what blocks a save -----------------------------

    def _condition_report(self, rule: dict, condition: dict) -> tuple[str, str, bool]:
        """(problem, hint, whether it blocks a save) for one condition row."""
        field, operator = condition["field"], condition["operator"]
        value = _text(condition["value"])
        # condition_error's alone, so Save refuses exactly what is marked.
        error = condition_error(operator, value)
        if error:
            return error, "", True
        if not field:
            return NO_FIELD, "", False
        if not self._resolvable(field, rule["level"]):
            unread = (
                f"“{field}” is not a field an {rule['level']} rule can read, "
                "so this condition never matches."
            )
            return unread, "", False
        if operator not in CONDITION_OPERATORS:
            if not operator:
                return NO_OPERATOR, "", False
            unknown = (
                f"“{operator}” is not an operator this version knows, "
                "so this condition never matches."
            )
            return unknown, "", False
        if value_kind(operator) == "date" and not self._iso_date(value):
            return NO_DATE, "", False
        if operator in LIST_OPERATORS:
            return "", _plural(validate_list(value)[1], "item"), False
        return "", "", False

    def _action_report(self, action: dict) -> tuple[str, str, bool]:
        """(problem, hint, whether it blocks a save) for one action row."""
        kind = _kind(action)
        if kind == "ADD_PRODUCT":
            if not _valid_quantity(action.get("quantity", 1)):
                return QUANTITY_PROBLEM, "", True
            return "", "", False
        if kind == "SET_STATUS":
            return "", HOLD_HINT, False
        if kind in ("ADD_TAG", "ADD_ORDER_TAG"):
            return "", RETIRED_ONE, False
        if kind == "SET_MULTI_TAGS":
            return "", RETIRED_MANY, False
        if kind not in ACTION_PARAMS:
            return UNKNOWN_ACTION, "", False
        return "", "", False

    def _blocking(self, rule: dict) -> list[tuple[int, str, int, str, str]]:
        """(step, "condition" or "action", row, message, data-key), counted
        from 1, for every row of a rule that blocks a save."""
        uid, found = rule["uid"], []
        for s, step in enumerate(rule["steps"]):
            for c, condition in enumerate(step["conditions"]):
                problem, _hint, blocks = self._condition_report(rule, condition)
                if blocks:
                    key = f"rule-{uid}-s{s}-c{c}-value"
                    found.append((s + 1, "condition", c + 1, problem, key))
            for a, action in enumerate(step["actions"]):
                problem, _hint, blocks = self._action_report(action)
                if blocks:
                    key = f"rule-{uid}-s{s}-a{a}-quantity"
                    found.append((s + 1, "action", a + 1, problem, key))
        return found

    def _first_blocked(self) -> tuple[int, dict, tuple] | None:
        for position, rule in enumerate(self.rules):
            blocking = self._blocking(rule)
            if blocking:
                return position, rule, blocking[0]
        return None

    def blocker(self) -> str | None:
        blocked = self._first_blocked()
        if blocked is None:
            return None
        position, rule, _row = blocked
        return f"Fix rule “{rule['name']}”" if rule["name"] else f"Fix rule {position + 1:02d}"

    def blocker_key(self) -> str:
        blocked = self._first_blocked()
        return "" if blocked is None else blocked[2][4]

    def validate(self) -> tuple[bool, list[str]]:
        """Refuse to save a rule the page marks red (AUDIT-03-5)."""
        errors = [
            f"{called}, step {s}, {row} {n}: {message}"
            for position, rule in enumerate(self.rules)
            for called in [f"Rule “{rule['name']}”" if rule["name"] else f"Rule {position + 1:02d}"]
            for s, row, n, message, _key in self._blocking(rule)
        ]
        return not errors, errors

    # --- the contract ------------------------------------------------------

    def collect(self) -> dict:
        return {
            "rules": [
                self._stored(rule, priority=position + 1)
                for position, rule in enumerate(self.rules)
            ]
        }

    def _untestable(self, rule: dict) -> str:
        """Why Test cannot run this rule; "" when it can."""
        if not self._has_analysis():
            return TEST_NO_ANALYSIS
        if not any(step["conditions"] for step in rule["steps"]):
            return TEST_NO_CONDITION
        if self._blocking(rule):
            return TEST_BLOCKED
        return ""

    def test_config(self, uid: str) -> dict | None:
        """The rule as Test runs it: what Save would store, without its
        place in the list and whether or not it is on. None when it cannot
        be tested."""
        rule = self._rule(uid)
        if rule is None or self._untestable(rule):
            return None
        stored = self._stored(rule)
        stored.pop("enabled", None)
        return stored

    # --- the view ----------------------------------------------------------

    def _summary(self, rule: dict) -> list[dict]:
        lines = []
        for s, step in enumerate(rule["steps"]):
            join = "or" if step["match"] == "ANY" else "and"
            when = []
            for c, condition in enumerate(step["conditions"]):
                if c:
                    when.append(_part("join", join))
                when.append(_part("bold", condition["field"]))
                when.append(_part("text", condition["operator"]))
                value = _text(condition["value"])
                if value_kind(condition["operator"]) != "none" and value != "":
                    when.append(_part("chip", value))
            then = []
            for a, action in enumerate(step["actions"]):
                if a:
                    then.append(_part("join", "and"))
                then.extend(_action_parts(action))
            lines.append(
                {
                    "label": "And when" if s else "When",
                    "parts": when or [_part("muted", NO_CONDITION)],
                }
            )
            lines.append({"label": "Then", "parts": then or [_part("muted", NO_ACTION)]})
        return lines

    def _row_problem(self, rule: dict) -> str:
        blocking = self._blocking(rule)
        if not blocking:
            return ""
        s, row, n, message, _key = blocking[0]
        where = f"{row.capitalize()} {n}"
        if len(rule["steps"]) > 1:
            where = f"Step {s}, {row} {n}"
        return f"{where}: {message}"

    def _condition_view(self, rule: dict, condition: dict) -> dict:
        field, operator = condition["field"], condition["operator"]
        problem, hint, blocks = self._condition_report(rule, condition)
        kind = value_kind(operator)
        resolvable = self._resolvable(field, rule["level"])
        offered = field in self._fields(rule["level"])
        suggestions = []
        if kind == "text" and operator in EQUALITY_OPERATORS and self._has_analysis():
            suggestions = get_unique_column_values(self.analysis_df, field)
        text = _text(condition["value"])
        return {
            "field": field,
            # A stored field the level does not offer: listed first, and kept.
            "extra_field": None
            if offered or not field
            else {"value": field, "note": "" if resolvable else NOT_AVAILABLE},
            "field_invalid": not resolvable,
            "operator": operator,
            "extra_operator": None if operator in CONDITION_OPERATORS else operator,
            "value": {
                "kind": kind,
                "text": self._iso_date(text) if kind == "date" else text,
                "placeholder": _PLACEHOLDER.get(operator, "Value"),
                "suggestions": suggestions[:SUGGESTION_LIMIT],
            },
            "problem": problem,
            "hint": hint,
            "invalid": blocks,
        }

    def _param_view(self, action: dict, spec: tuple, blocks: bool) -> dict:
        name, kind, placeholder, lead = spec
        value = _text(action.get(name))
        options, extra = [], None
        if kind == "suggest":
            options = self.configured_tags()
        elif kind == "field":
            options = self._fields("article")
            if value and value not in options:
                extra = value
        elif kind == "choice":
            options = [{"value": v, "label": label} for v, label in _CHOICES[name]]
        return {
            "name": name,
            "kind": kind,
            "value": value,
            "placeholder": placeholder,
            "lead": lead,
            "options": options,
            "extra": extra,
            "invalid": blocks and kind == "number",
        }

    def _action_view(self, action: dict) -> dict:
        kind = _kind(action)
        problem, hint, blocks = self._action_report(action)
        label = ACTION_LABELS.get(kind, _text(action.get("type")))
        return {
            "type": kind,
            "label": label,
            # A type the menu does not offer is listed on this row only.
            "extra_type": None
            if kind in ACTION_TYPES
            else {"value": kind, "label": label},
            "params": [
                self._param_view(action, spec, blocks)
                for spec in ACTION_PARAMS.get(kind, ())
            ],
            "problem": problem,
            "hint": hint,
        }

    def _step_view(self, rule: dict, s: int, step: dict) -> dict:
        several = len(rule["steps"]) > 1
        note = ""
        if several and s:
            note = (
                f"Runs only if step {s} matched."
                if rule["level"] == "order"
                else f"Checks only the lines step {s} matched."
            )
        return {
            "title": f"Step {s + 1}" if several else "",
            "note": note,
            "removable": s > 0,
            "match": {
                "show": len(step["conditions"]) > 1,
                "options": [
                    {"value": value, "label": label, "checked": step["match"] == value}
                    for value, label in (("ALL", "All"), ("ANY", "Any"))
                ],
                "tail": "of these match",
            },
            "conditions": [self._condition_view(rule, c) for c in step["conditions"]],
            "actions": [self._action_view(a) for a in step["actions"]],
        }

    def _editor(self, rule: dict) -> dict:
        return {
            "level": {
                "options": [
                    {
                        "value": level,
                        "label": LEVEL_LABEL[level],
                        "checked": rule["level"] == level,
                    }
                    for level in LEVELS
                ],
                "hint": LEVEL_HINT[rule["level"]],
            },
            "field_groups": [
                {"label": label, "fields": fields}
                for label, fields in rule_fields(rule["level"], self.analysis_df)
            ],
            "operators": list(CONDITION_OPERATORS),
            "action_types": [
                {"value": kind, "label": ACTION_LABELS[kind]} for kind in ACTION_TYPES
            ],
            "steps": [
                self._step_view(rule, s, step) for s, step in enumerate(rule["steps"])
            ],
        }

    def _row(self, position: int, rule: dict, filtering: bool) -> dict:
        group = self._level_rules(rule["level"])
        place = group.index(rule)
        is_open = rule["uid"] == self.open_uid
        untestable = self._untestable(rule)
        return {
            "uid": rule["uid"],
            "num": f"{position + 1:02d}",
            "name": rule["name"],
            # What the row calls the rule: a rule can be saved with no name.
            "label": rule["name"] or UNNAMED,
            "on": rule["enabled"],
            "open": is_open,
            "switch_title": "Turn off" if rule["enabled"] else "Turn on",
            "badge": "" if rule["enabled"] else "Off",
            "can_up": not filtering and place > 0,
            "can_down": not filtering and place < len(group) - 1,
            "can_drag": not filtering and len(group) > 1,
            "move_title": CLEAR_FILTER if filtering else "",
            "can_test": not untestable,
            "test_title": untestable,
            "summary": self._summary(rule),
            "wide_labels": len(rule["steps"]) > 1,
            "problem": self._row_problem(rule),
            "editor": self._editor(rule) if is_open else None,
        }

    def view(self) -> dict:
        needle = self.filter.strip().lower()
        both = bool(self._level_rules("article")) and bool(self._level_rules("order"))
        groups = []
        for level in LEVELS:
            rows = [
                self._row(position, rule, bool(needle))
                for position, rule in enumerate(self.rules)
                if rule["level"] == level
                and (
                    not needle
                    or needle in rule["name"].lower()
                    or rule["uid"] == self.open_uid
                )
            ]
            if rows:
                label, note = GROUPS[level] if both else ("", "")
                groups.append({"level": level, "label": label, "note": note, "rows": rows})
        on = sum(1 for rule in self.rules if rule["enabled"])
        return {
            "page": "rules",
            "title": "Rules",
            "subtitle": SUBTITLE,
            # With no rule the empty state holds the button.
            "action": ADD_RULE if self.rules else "",
            "rules": {
                "empty": None
                if self.rules
                else {"title": EMPTY_TITLE, "text": EMPTY_TEXT, "action": ADD_RULE},
                "filter": self.filter,
                "filter_placeholder": "Filter by name",
                "filtering": bool(needle),
                "count": f"{_plural(len(self.rules), 'rule')} · {on} on",
                "no_hits": f"No rules named “{self.filter.strip()}”."
                if self.rules and not groups
                else "",
                "groups": groups,
            },
        }
