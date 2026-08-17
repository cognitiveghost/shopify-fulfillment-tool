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
            logger.warning(f"[REPORT FILTERS] Incomplete filter, matches nothing: {filt}")
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
