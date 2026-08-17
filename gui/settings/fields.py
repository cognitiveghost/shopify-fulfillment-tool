"""Field and operator vocabularies shared by the settings pages.

Imports nothing from this package: pages import from here, never the
reverse, so there is no cycle back through window.py.
"""

from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton, QWidget

from gui.theme_manager import set_button_role
from gui.wheel_ignore_combobox import WheelIgnoreComboBox

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


def _delete_filter_row(row_widget, ref_list, ref_dict):
    row_widget.deleteLater()
    ref_list.remove(ref_dict)


def _on_filter_criteria_changed(filter_refs, analysis_df, initial_value=None):
    """Dynamically changes the filter's value widget based on other selections.

    For example, if the operator is '==' and the field is 'Order_Type',
    this method will create a QComboBox with unique values from the
    DataFrame ('Single', 'Multi') instead of a plain QLineEdit.

    Args:
        filter_refs (dict): A dictionary of widget references for the filter row.
        analysis_df (pd.DataFrame): The current analysis DataFrame, used to
            populate dropdown values.
        initial_value (any, optional): The value to set in the newly
            created widget. Defaults to None.
    """
    field = filter_refs["field"].currentText()
    op = filter_refs["op"].currentText()

    if filter_refs["value_widget"]:
        filter_refs["value_widget"].deleteLater()

    # analysis_df is None until an analysis has been run. The old operator
    # names never matched here, so this branch was dead and the None never
    # reached .empty; it does now.
    use_combobox = (
        op in ["equals", "does not equal"]
        and analysis_df is not None
        and not analysis_df.empty
        and field in analysis_df.columns
    )

    if use_combobox:
        try:
            unique_values = analysis_df[field].dropna().unique().tolist()
            unique_values = sorted([str(v) for v in unique_values])
            new_widget = WheelIgnoreComboBox()
            new_widget.addItems(unique_values)
            if initial_value and str(initial_value) in unique_values:
                new_widget.setCurrentText(str(initial_value))
        except Exception:
            new_widget = QLineEdit()
            new_widget.setText(str(initial_value) if initial_value else "")
    else:
        new_widget = QLineEdit()
        placeholder = "Value"
        if op in ["in list", "not in list"]:
            placeholder = "Values, comma-separated"
        new_widget.setPlaceholderText(placeholder)
        text_value = ",".join(initial_value) if isinstance(initial_value, list) else (initial_value or "")
        new_widget.setText(str(text_value))

    filter_refs["value_layout"].insertWidget(2, new_widget, 1)
    filter_refs["value_widget"] = new_widget


def add_filter_row(parent_widget_refs, fields, operators, analysis_df, config=None):
    """Adds a new row of widgets for a single filter criterion.

    Shared by the Packing Lists and Stock Exports pages.

    Args:
        parent_widget_refs (dict): Widget references for the parent report.
        fields (list[str]): The list of columns to show in the field dropdown.
        operators (list[str]): The list of operators to show.
        analysis_df (pd.DataFrame): The current analysis DataFrame, used to
            populate dropdown values.
        config (dict, optional): The configuration for a pre-existing
            filter. If None, creates a new, blank filter.
    """
    if not isinstance(config, dict):
        config = {}
    # A saved field the offered list does not contain must still be offered.
    # setCurrentText is a silent no-op on a non-editable combo, so without
    # this the row would render as fields[0] and be written back that way on
    # the next save -- silently repointing the filter at another column. The
    # list is short of the full set whenever no analysis has been run yet,
    # which is every app start, so this is the common case rather than the
    # exotic one.
    saved_field = config.get("field")
    if saved_field and saved_field not in fields:
        fields = [*fields, saved_field]

    row_layout = QHBoxLayout()
    field_combo = WheelIgnoreComboBox()
    field_combo.addItems(fields)
    op_combo = WheelIgnoreComboBox()
    op_combo.addItems(operators)
    value_edit = QLineEdit()
    delete_btn = QPushButton("X")
    set_button_role(delete_btn, "secondary")

    row_layout.addWidget(field_combo)
    row_layout.addWidget(op_combo)
    row_layout.addWidget(value_edit, 1)

    field_combo.setCurrentText(config.get("field", fields[0]))
    op_combo.setCurrentText(config.get("operator", operators[0]))
    val = config.get("value", "")

    row_widget = QWidget()
    row_widget.setLayout(row_layout)

    filter_refs = {
        "widget": row_widget,
        "field": field_combo,
        "op": op_combo,
        "value_widget": None,
        "value_layout": row_layout,
    }

    # Connect signals before setting initial value to trigger the handler
    field_combo.currentTextChanged.connect(
        lambda: _on_filter_criteria_changed(filter_refs, analysis_df)
    )
    op_combo.currentTextChanged.connect(
        lambda: _on_filter_criteria_changed(filter_refs, analysis_df)
    )

    _on_filter_criteria_changed(filter_refs, analysis_df, initial_value=val)  # Set initial widget and value

    row_layout.addWidget(delete_btn)
    parent_widget_refs["filters_layout"].addWidget(row_widget)
    parent_widget_refs["filters"].append(filter_refs)
    delete_btn.clicked.connect(
        lambda: _delete_filter_row(row_widget, parent_widget_refs["filters"], filter_refs)
    )
