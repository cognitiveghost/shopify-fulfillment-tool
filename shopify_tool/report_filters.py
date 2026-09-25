"""Single source of truth for evaluating report filters.

Packing lists, stock exports, the generation dialog's preview and the JSON
handed to Packing Tool all filter the analysis DataFrame by the same saved
filter config. They used to do it two different ways -- both writers shared a
copy-pasted pandas ``.query()`` string builder, and the GUI had its own
per-operator implementation -- so the same config could yield different rows in
the XLSX, the .xls and the preview.

Worse, the query-string builder could only evaluate ``==`` and ``!=`` of the
five operators the settings UI offered. ``in`` produced no file under a
"Report saved" message, ``contains`` raised a SyntaxError, and ``not in``
silently emitted the rows it was told to exclude.

This module replaces it. Operators are evaluated by the same OPERATOR_MAP
functions the rule engine uses, so the vocabulary is consistent across the app
and there is one implementation to keep correct.
"""

import logging

import pandas as pd

from shopify_tool import rules
from shopify_tool.stock_ledger import FULFILLABLE, in_fulfillable_order
from shopify_tool.tag_manager import has_tag

logger = logging.getLogger(__name__)

# Operator names written by older builds of the settings UI. Normalised on
# read rather than migrated on disk: client configs live on a shared file
# server and may be written by a mix of app versions, so the evaluator has to
# understand both spellings anyway. Normalising here means no write path and
# no migration to get wrong.
LEGACY_OPERATOR_ALIASES = {
    "==": "equals",
    "!=": "does not equal",
    "in": "in list",
    "not in": "not in list",
    "contains": "contains",
}

# Internal_Tags holds a serialized tag list -- a JSON string in production,
# occasionally a native list. Substring matching against the raw value is
# wrong: "contains Gift" would match ["NoGift"]. These operators get
# tag-membership semantics instead, via tag_manager.has_tag which accepts
# either form.
_TAG_COLUMN = "Internal_Tags"
_TAG_MEMBERSHIP_OPERATORS = {"contains", "equals"}
_TAG_ABSENCE_OPERATORS = {"does not contain", "does not equal"}


def normalize_operator(operator):
    """Returns the rules-engine name for a stored operator."""
    return LEGACY_OPERATOR_ALIASES.get(operator, operator)


def fulfillable_only(df):
    """Restricts ``df`` to fulfillable orders.

    Every report covers fulfillable orders and nothing else. Both file
    writers applied this inline while the preview and the JSON handed to
    Packing Tool did not, so the same config could report -- and hand the
    sibling app -- orders the warehouse's own file excluded. Sharing the
    evaluator is not enough; the four paths have to filter the same input.

    A frame without the status column matches nothing, for the same reason a
    filter on a missing column does: it is not an analysis frame, and a
    report that quietly contains rows no one vouched for is worse than one
    that is visibly empty.

    An order ships whole or not at all: one blocked SKU line holds back the
    lines beside it (AUDIT-04-6).
    """
    if df is None or df.empty:
        return df
    if "Order_Fulfillment_Status" not in df.columns:
        logger.warning(
            "[REPORT FILTERS] No Order_Fulfillment_Status column, matches nothing"
        )
        return df.iloc[0:0].copy()
    ready = df["Order_Fulfillment_Status"].eq(FULFILLABLE)
    if "Order_Number" not in df.columns:
        return df[ready]
    return df[ready & in_fulfillable_order(df)]


def _tag_mask(series, operator, value):
    """Boolean mask for a filter on the Internal_Tags column."""
    present = series.apply(lambda cell: has_tag(cell, value))
    return present if operator in _TAG_MEMBERSHIP_OPERATORS else ~present


def apply_report_filters(df, filters):
    """Filters ``df`` by a report config's filter list.

    A filter that cannot be evaluated -- unknown operator, missing column --
    matches nothing rather than being skipped. Skipping widens the result set,
    which is the exact failure this module exists to remove: a packing list
    that quietly contains rows the configuration excluded is worse than one
    that is visibly empty.

    Args:
        df (pd.DataFrame): The frame to filter.
        filters (list[dict] | None): Filter dicts with 'field', 'operator' and
            'value' keys. Operators may use either the rules-engine names or
            the legacy symbols; both are understood.

    Returns:
        pd.DataFrame: A filtered copy. Filters combine with AND.
    """
    if df is None or df.empty or not filters:
        return df.copy() if df is not None else df

    mask = pd.Series(True, index=df.index)

    for filt in filters:
        field = filt.get("field")
        operator = normalize_operator(filt.get("operator"))
        value = filt.get("value")

        if not field or not operator:
            logger.warning(
                f"[REPORT FILTERS] Incomplete filter, matches nothing: {filt}"
            )
            return df.iloc[0:0].copy()

        if field not in df.columns:
            logger.warning(
                f"[REPORT FILTERS] Field '{field}' is not a column, matches nothing"
            )
            return df.iloc[0:0].copy()

        if field == _TAG_COLUMN and operator in (
            _TAG_MEMBERSHIP_OPERATORS | _TAG_ABSENCE_OPERATORS
        ):
            mask &= _tag_mask(df[field], operator, value)
            continue

        func_name = rules.OPERATOR_MAP.get(operator)
        if func_name is None:
            logger.warning(
                f"[REPORT FILTERS] Unknown operator '{operator}', matches nothing"
            )
            return df.iloc[0:0].copy()

        op_func = getattr(rules, func_name)
        mask &= op_func(df[field], value)

    return df[mask].copy()


def match_counts(filtered):
    """(distinct orders, rows) in an already-filtered frame.

    Falls back to the first column when there is no Order_Number, as the
    report dialog's preview always has.
    """
    if filtered is None or filtered.empty:
        return (0, 0)
    order_col = (
        "Order_Number" if "Order_Number" in filtered.columns else filtered.columns[0]
    )
    return (int(filtered[order_col].nunique()), len(filtered))


def count_matches(df, filters):
    """(orders, rows) a report with these filters would contain.

    None when there is no analysis to count against. Counts over
    fulfillable orders only, exactly as the generated file does.
    """
    if df is None or df.empty:
        return None
    return match_counts(apply_report_filters(fulfillable_only(df), filters))


def parse_sku_list(skus):
    """exclude_skus from a report config: a list, or comma-separated text
    typed into settings. Values are stripped; blanks dropped."""
    if isinstance(skus, str):
        skus = skus.split(",")
    elif not isinstance(skus, list):
        return []
    return [str(s).strip() for s in skus if s is not None and str(s).strip()]


def exclude_skus(df, skus):
    """Drops the rows whose SKU is excluded. The packing list XLSX and the
    JSON for Packing Tool both call this, so they can't disagree
    (AUDIT-04-4). SKUs compare through normalize_sku_for_matching, so "07"
    also excludes 7 and "7.0". A row with no SKU is never excluded."""
    wanted = parse_sku_list(skus)
    if not wanted or df is None or df.empty or "SKU" not in df.columns:
        return df
    from shopify_tool.csv_utils import normalize_sku_for_matching

    targets = {normalize_sku_for_matching(s) for s in wanted}
    has_sku = df["SKU"].notna()
    normalized = df["SKU"].where(has_sku, "").astype(str).map(normalize_sku_for_matching)
    return df[~(has_sku & normalized.isin(targets))]
