"""Field and operator vocabularies shared by the settings pages.

Imports nothing from this package: pages import from here, never the
reverse, so there is no cycle back through window.py. No Qt import.
"""

FILTERABLE_COLUMNS: list[str] = [
    "Order_Number",
    "Order_Type",
    "SKU",
    "Product_Name",
    "Stock_Alert",
    "Order_Fulfillment_Status",
    "Shipping_Provider",
    "Destination_Country",
    "Tags",
    "System_note",
    "Status_Note",
    "Total Price",
    "Quantity",
]

CONDITION_OPERATORS: list[str] = [
    "equals",
    "does not equal",
    "contains",
    "does not contain",
    "is greater than",
    "is less than",
    "is greater than or equal",
    "is less than or equal",
    "starts with",
    "ends with",
    "is empty",
    "is not empty",
    "in list",
    "not in list",
    "between",
    "not between",
    "date before",
    "date after",
    "date equals",
    "matches regex",
    "does not match regex",
]

ACTION_TYPES: list[str] = [
    "ADD_INTERNAL_TAG",
    "REMOVE_INTERNAL_TAG",
    "SET_STATUS",
    "COPY_FIELD",
    "CALCULATE",
    "ALERT_NOTIFICATION",
    "ADD_PRODUCT",
]

# Still executed by the rule engine, but no longer offered when building a
# new rule: all three append to the free-text Status_Note column despite
# their names, and the first two are the same code path. A rule already
# using one keeps working and round-trips through save unchanged; the
# editor flags it instead. See
# docs/superpowers/specs/2026-08-14-rule-actions-internal-tags-design.md.
LEGACY_ACTION_TYPES: list[str] = ["ADD_TAG", "ADD_ORDER_TAG", "SET_MULTI_TAGS"]


# Report filters use the rule engine's vocabulary. The old five-symbol list
# (==, !=, in, not in, contains) is still understood when reading saved
# configs -- see shopify_tool/report_filters.LEGACY_OPERATOR_ALIASES -- but
# new configs are written with these names.
REPORT_FILTER_OPERATORS: list[str] = list(CONDITION_OPERATORS)


def report_filter_fields(analysis_df) -> list[str]:
    """Columns offered in a report filter's field dropdown and column picker.

    Sourced from the analysis DataFrame so Internal_Tags and any additional
    CSV columns the client configured are filterable, falling back to the
    static list when no analysis has been run yet. Always sorted, so the
    column picker's order -- and therefore a saved config's column order --
    does not depend on which branch produced the list.
    """
    if analysis_df is not None and not analysis_df.empty:
        return sorted(analysis_df.columns.tolist())
    return sorted(FILTERABLE_COLUMNS)
