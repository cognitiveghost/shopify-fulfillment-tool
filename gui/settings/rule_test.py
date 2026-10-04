"""Test rule: one rule, as edited, run on a copy of the analysis (phase 8 spec
section 6).

run_rule_test returns everything the Test panel draws, sentences included.
It counts orders, lists the first few that match with what they matched on
and what the rule changed, and leaves the analysis as it found it. No widget:
SettingsWebHost runs it on a worker thread.
"""

import numpy as np
import pandas as pd

from gui.pandas_model import cell_display_text
from shopify_tool.rules import RuleEngine
from shopify_tool.stock_ledger import NOT_FULFILLABLE
from shopify_tool.tag_manager import parse_tags

LIMIT = 5
# How many of an order's values Matched on spells out before it trails off.
VALUES_SHOWN = 3
HEADS = ["Order", "Matched on", "Change"]
NO_CHANGE = "No change"
NO_CHANGE_NOTE = "No change: the analysis already has the saved rules applied."
NO_MATCH = "No order in this analysis matches."
FAILED = "The rule test didn’t finish. Details are in Logs."
# The order fields the engine works out as a number. The others (has_sku and
# its kin) answer yes or no about the condition's own value.
NUMERIC_ORDER_FIELDS = (
    "item_count",
    "total_quantity",
    "unique_sku_count",
    "max_quantity",
    "order_volumetric_weight",
)
# Written by a hold beside the status: its reason code, not a change to show.
_UNLISTED = ("Internal_Tags", "Order_Fulfillment_Status", "System_note")


def _order_keys(df: pd.DataFrame) -> pd.Series:
    """What tells one order from the next: its number, or the line itself in
    a frame that has none."""
    if "Order_Number" in df.columns:
        return df["Order_Number"]
    return pd.Series(df.index.astype(str), index=df.index)


def _orders_text(count: int) -> str:
    return "1 order" if count == 1 else f"{count} orders"


def _view(rule: dict, session: str, status: str, **drawn) -> dict:
    """One state of the panel. Every state carries every key, so the page
    never has to ask whether one is there."""
    view = {
        "status": status,
        "title": f"Test “{rule.get('name', '')}”",
        "intro": {
            "lead": "Runs this rule, as edited, against the analysis in "
            if session
            else "Runs this rule, as edited, against the last analysis",
            "session": session,
            "tail": ". Orders aren’t changed.",
        },
        "message": "",
        "matched": "",
        "total": "",
        "heads": HEADS,
        "rows": [],
        "more": "",
        "empty": "",
        "note": "",
    }
    view.update(drawn)
    return view


def running_view(rule: dict, df: pd.DataFrame, session: str = "") -> dict:
    total = _order_keys(df).nunique(dropna=False)
    return _view(rule, session, "running", message=f"Testing {_orders_text(total)}…")


def failed_view(rule: dict, session: str = "") -> dict:
    return _view(rule, session, "failed", message=FAILED)


def _number(value) -> str:
    number = float(value)
    return str(int(number)) if number.is_integer() else str(round(number, 2))


def _matched_on(rule: dict, engine: RuleEngine, order: pd.DataFrame, lines: pd.DataFrame) -> str:
    """What the rule's conditions read on this order: `field: value` for each
    field, once, in the rule's order."""
    order_rule = rule.get("level") == "order"
    parts, seen = [], set()
    for step in rule.get("steps", []):
        for condition in step.get("conditions", []):
            field = condition.get("field")
            if not field or field in seen:
                continue
            seen.add(field)
            if field in order.columns:
                values = list(dict.fromkeys(cell_display_text(v) or "empty" for v in lines[field]))
                # "; " and not ", ": a value can hold commas (Tags: VIP, repeat).
                shown = "; ".join(values[:VALUES_SHOWN])
                if len(values) > VALUES_SHOWN:
                    shown += "; …"
                parts.append(f"{field}: {shown}")
            elif order_rule and field in NUMERIC_ORDER_FIELDS:
                worked_out = getattr(engine, RuleEngine.ORDER_LEVEL_FIELDS[field])(order, None)
                parts.append(f"{field}: {_number(worked_out)}")
            elif order_rule and field in RuleEngine.ORDER_LEVEL_FIELDS:
                parts.append(f"{field}: {cell_display_text(condition.get('value'))}")
    return " · ".join(parts)


def _tags(lines: pd.DataFrame) -> list[str]:
    if "Internal_Tags" not in lines.columns:
        return []
    return list(dict.fromkeys(tag for value in lines["Internal_Tags"] for tag in parse_tags(value)))


def _texts(lines: pd.DataFrame, column: str) -> np.ndarray:
    return np.array([cell_display_text(value) for value in lines[column]], dtype=object)


def _change(before: pd.DataFrame, after: pd.DataFrame, added: pd.DataFrame) -> str:
    """What the rule did to one order, from its lines before and after."""
    was, now = _tags(before), _tags(after)
    parts = [f"+ {tag}" for tag in now if tag not in was]
    parts += [f"− {tag}" for tag in was if tag not in now]

    status = "Order_Fulfillment_Status"
    if status in before.columns and status in after.columns:
        changed = _texts(before, status) != _texts(after, status)
        if changed.any():
            value = _texts(after, status)[changed][0]
            # A rule can only hold an order (spec 2026-09-26 D3).
            parts.append("Held" if value == NOT_FULFILLABLE else f"{status} → {value}")

    for column in after.columns:
        if column in _UNLISTED:
            continue
        shown = _texts(after, column)
        if column in before.columns:
            changed = _texts(before, column) != shown
        else:
            # A column the rule made: empty on every line it did not write.
            changed = shown != ""
        if changed.any():
            parts.append(f"{column} → {shown[changed][0]}")

    for _label, line in added.iterrows():
        sku = cell_display_text(line.get("SKU"))
        parts.append(f"+ {sku} ×{cell_display_text(line.get('Quantity'))}")
    return ", ".join(parts) or NO_CHANGE


def run_rule_test(rule: dict, df: pd.DataFrame, session: str = "", limit: int = LIMIT) -> dict:
    """Run `rule` on a copy of `df` and say which orders it matched.

    The rule runs whether or not it is stored as on. `df` is not changed.
    """
    engine = RuleEngine([{key: value for key, value in rule.items() if key != "enabled"}])
    after = engine.apply(df.copy())
    # apply() only ever appends: the first len(df) rows of `after` are df's
    # rows in order, and any below them are lines the rule added.
    existing, added = after.iloc[: len(df)], after.iloc[len(df) :]
    matched = engine.matched_rows.to_numpy(dtype=bool)

    codes, orders = pd.factorize(_order_keys(df), use_na_sentinel=False)
    hit = pd.unique(codes[matched])
    added_keys = _order_keys(added).to_numpy() if len(added) else np.array([], dtype=object)

    rows = []
    for code in hit[:limit]:
        of_order = codes == code
        lines = of_order if rule.get("level") == "order" else of_order & matched
        change = _change(df[of_order], existing[of_order], added[added_keys == orders[code]])
        rows.append(
            {
                "order": cell_display_text(orders[code]),
                "why": _matched_on(rule, engine, df[of_order], df[lines]),
                "change": change,
                "changed": change != NO_CHANGE,
            }
        )

    more = len(hit) - len(rows)
    total = len(orders)
    return _view(
        rule,
        session,
        "done",
        matched=str(len(hit)),
        total="of 1 order matches" if total == 1 else f"of {total} orders match",
        rows=rows,
        more=f"and {more} more" if more else "",
        empty="" if len(hit) else NO_MATCH,
        note=NO_CHANGE_NOTE if any(not row["changed"] for row in rows) else "",
    )
