"""Field and operator vocabularies shared by the settings pages.

Imports nothing from this package: pages import from here, never the
reverse, so there is no cycle back through window.py.
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
]

FILTER_OPERATORS: list[str] = ["==", "!=", "in", "not in", "contains"]

# Order-level fields are grouped first, with the separator rows the combo
# boxes render as non-selectable headers.
ORDER_LEVEL_FIELDS: list[str] = [
    "--- ORDER-LEVEL FIELDS ---",
    "item_count",
    "total_quantity",
    "has_sku",
    "Has_SKU",
    "--- ARTICLE-LEVEL FIELDS ---",
]

CONDITION_FIELDS: list[str] = ORDER_LEVEL_FIELDS + FILTERABLE_COLUMNS

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
    "ADD_TAG",
    "ADD_ORDER_TAG",
    "ADD_INTERNAL_TAG",
    "SET_STATUS",
    "COPY_FIELD",
    "CALCULATE",
    "SET_MULTI_TAGS",
    "ALERT_NOTIFICATION",
    "ADD_PRODUCT",
]
