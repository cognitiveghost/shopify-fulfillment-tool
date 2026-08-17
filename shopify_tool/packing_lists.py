import logging
import os
from datetime import datetime

import pandas as pd

from .csv_utils import normalize_sku_for_matching, order_number_sort_key
from shopify_tool.report_filters import apply_report_filters

logger = logging.getLogger("ShopifyToolLogger")


def _expand_lot_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Expand packing list rows that span multiple lots into one row per lot.

    For rows where Lot_Details is None or empty the row is kept as-is with
    Lot_Expiry="" and Lot_Batch="".

    For rows where Lot_Details is a list of lot dicts the row is duplicated
    once per lot entry, with Quantity replaced by qty_allocated and
    Lot_Expiry / Lot_Batch populated from the dict.

    Destination_Country de-duplication must be re-applied by the caller
    AFTER calling this function (expansion changes row count per order).

    Args:
        df: Sorted packing list DataFrame with optional Lot_Details column.

    Returns:
        New DataFrame with Lot_Expiry and Lot_Batch columns added.
    """
    rows = []
    # The simulation allocates at the (order, SKU) level — all DataFrame rows for the
    # same (order, SKU) pair carry an identical Lot_Details object representing the full
    # allocation for that pair.  Without this guard we would emit duplicate lot rows
    # once per duplicate row instead of once per (order, SKU).
    seen_order_sku: set = set()
    for _, row in df.iterrows():
        lot_details = row.get("Lot_Details")
        if lot_details and isinstance(lot_details, list) and len(lot_details) > 0:
            order_key = (row.get("Order_Number", ""), row.get("SKU", ""))
            if order_key in seen_order_sku:
                continue
            seen_order_sku.add(order_key)
            for entry in lot_details:
                new_row = row.copy()
                new_row["Quantity"] = entry.get("qty_allocated", new_row["Quantity"])
                expiry = entry.get("expiry") or ""
                new_row["Lot_Expiry"] = "" if expiry == "1" else expiry
                batch = entry.get("batch") or ""
                new_row["Lot_Batch"] = "" if batch == "1" else batch
                rows.append(new_row)
        else:
            new_row = row.copy()
            new_row["Lot_Expiry"] = ""
            new_row["Lot_Batch"] = ""
            rows.append(new_row)
    if not rows:
        result = df.copy()
        result["Lot_Expiry"] = ""
        result["Lot_Batch"] = ""
        return result
    return pd.DataFrame(rows).reset_index(drop=True)


def create_packing_list(analysis_df, output_file, report_name="Packing List",
                        filters=None, exclude_skus=None, columns=None):
    """Creates a versatile, formatted packing list in an Excel .xlsx file.

    This function takes the main analysis DataFrame and generates a packing list
    based on a set of filters. The resulting list is sorted for efficient
    warehouse picking and formatted for clarity.

    Key steps in the process:
    1.  **Filtering**: It filters the main DataFrame to include only 'Fulfillable'
        orders that match the provided filter criteria (e.g., by shipping provider).
    2.  **Exclusion**: It can exclude specific SKUs from the final list, which is
        useful for items that are packed separately.
    3.  **Sorting**: The list is sorted by shipping provider, order number, and SKU
        to group items logically for picking.
    4.  **Formatting**: It generates an Excel file with advanced formatting:
        -   Custom headers, with one header containing the report's generation
            timestamp and another the filename for reference.
        -   Borders are used to visually group line items belonging to the same order.
        -   Column widths are auto-adjusted to fit content.
        -   Print settings are configured for A4 landscape with repeated headers.
    5.  **Data Transformation**: The 'Destination_Country' is shown only for the
        first item of an order to reduce clutter.

    Args:
        analysis_df (pd.DataFrame): The main DataFrame from the fulfillment
            analysis, containing all order line items and their statuses.
        output_file (str): The full path where the output .xlsx file will be
            saved.
        report_name (str, optional): The name of the report, used for logging.
            Defaults to "Packing List".
        filters (list[dict], optional): A list of dictionaries, where each
            dictionary defines a filter condition. Each filter dict should have
            'field', 'operator', and 'value' keys. Defaults to None.
        exclude_skus (list[str], optional): A list of SKUs to exclude from the
            packing list. Defaults to None.
        columns (list[str], optional): The columns to print, in order. None
            keeps the default layout. Columns not present in the data are
            dropped with a warning rather than raising.
    """
    try:
        logger.info(f"--- Creating report: '{report_name}' ---")

        # Packing lists only ever contain fulfillable orders; the report's own
        # filters narrow it further. Both go through the shared evaluator so
        # the XLSX, the JSON and the dialog preview cannot disagree.
        fulfillable = analysis_df[
            analysis_df["Order_Fulfillment_Status"] == "Fulfillable"
        ]
        filtered_orders = apply_report_filters(fulfillable, filters)

        # Exclude specified SKUs if any are provided
        if exclude_skus and not filtered_orders.empty:
            logger.info(f"[EXCLUDE_SKUS] Received exclude list: {exclude_skus}")
            logger.info(f"[EXCLUDE_SKUS] Total items before exclusion: {len(filtered_orders)}")

            # Show unique SKUs in DataFrame for debugging
            unique_skus = filtered_orders["SKU"].unique().tolist()
            logger.info(f"[EXCLUDE_SKUS] Unique SKUs in DataFrame: {unique_skus[:20]}...")  # Show first 20

            # Normalize both DataFrame SKU column and exclude_skus for fuzzy matching
            # Use normalize_sku_for_matching to allow "07" to match with 7, "7", or "07"
            # This is different from normalize_sku which preserves leading zeros for main data
            sku_column_normalized = filtered_orders["SKU"].apply(normalize_sku_for_matching)
            exclude_skus_normalized = [normalize_sku_for_matching(s) for s in exclude_skus]

            logger.info(f"[EXCLUDE_SKUS] Normalized exclude list: {exclude_skus_normalized}")
            logger.info(f"[EXCLUDE_SKUS] Sample normalized DataFrame SKUs: {sku_column_normalized.unique().tolist()[:20]}...")

            # Create mask for items to keep (NOT in exclude list)
            mask = ~sku_column_normalized.isin(exclude_skus_normalized)
            filtered_orders = filtered_orders[mask]

            excluded_count = (~mask).sum()
            logger.info(f"[EXCLUDE_SKUS] Excluded {excluded_count} items. Remaining: {len(filtered_orders)}")

        if filtered_orders.empty:
            logger.warning(f"Report '{report_name}': No orders found matching the criteria.")
            return

        logger.info(f"Found {filtered_orders['Order_Number'].nunique()} orders for the report.")

        # Fill NaN values to avoid issues during processing
        for col in ["Destination_Country", "Warehouse_Name", "Product_Name", "SKU"]:
            if col in filtered_orders.columns:
                filtered_orders[col] = filtered_orders[col].fillna("")

        # Use Warehouse_Name if available, otherwise fall back to Product_Name
        # This ensures backward compatibility with tests and old data
        if "Warehouse_Name" not in filtered_orders.columns:
            if "Product_Name" in filtered_orders.columns:
                logger.info("Warehouse_Name not found, using Product_Name as fallback")
                filtered_orders["Warehouse_Name"] = filtered_orders["Product_Name"]
            else:
                logger.warning("Neither Warehouse_Name nor Product_Name found, using empty string")
                filtered_orders["Warehouse_Name"] = ""

        # Sort by provider priority, then numeric order number, then SKU.
        # order_number_sort_key avoids lexicographic issues ("#9" vs "#10").
        provider_map = {"DHL": 0, "PostOne": 1, "DPD": 2}
        filtered_orders = filtered_orders.copy()
        filtered_orders["sort_priority"] = filtered_orders["Shipping_Provider"].map(provider_map).fillna(3)
        filtered_orders["_order_sort"] = filtered_orders["Order_Number"].apply(order_number_sort_key)
        sorted_list = filtered_orders.sort_values(by=["sort_priority", "_order_sort", "SKU"])
        sorted_list = sorted_list.drop(columns=["_order_sort"])

        # Detect whether lot tracking data is present
        has_lot_details = (
            "Lot_Details" in sorted_list.columns
            and sorted_list["Lot_Details"].notna().any()
        )

        if has_lot_details:
            # Expand lot rows BEFORE destination-country deduplication so the
            # dedup correctly picks only the first row of each (now expanded) order
            sorted_list = _expand_lot_rows(sorted_list)
            sorted_list["Destination_Country"] = sorted_list["Destination_Country"].where(
                ~sorted_list["Order_Number"].duplicated(), ""
            )
            columns_for_print = [
                "Destination_Country",
                "Order_Number",
                "SKU",
                "Warehouse_Name",
                "Quantity",
                "Lot_Expiry",
                "Lot_Batch",
                "Shipping_Provider",
            ]
        else:
            # Show destination country only for the first item of an order
            sorted_list["Destination_Country"] = sorted_list["Destination_Country"].where(
                ~sorted_list["Order_Number"].duplicated(), ""
            )
            default_columns = [
                "Destination_Country",
                "Order_Number",
                "SKU",
                "Warehouse_Name",  # From stock file - actual warehouse product names (or Product_Name fallback)
                "Quantity",
                "Shipping_Provider",
            ]
            if columns:
                columns_for_print = [c for c in columns if c in sorted_list.columns]
                missing = [c for c in columns if c not in sorted_list.columns]
                if missing:
                    logger.warning(f"Configured columns not in the data, skipped: {missing}")
                if not columns_for_print:
                    logger.warning("No configured column exists in the data; using the default layout")
                    columns_for_print = default_columns
            else:
                columns_for_print = default_columns

        print_list = sorted_list[columns_for_print]

        # Borders group the rows of one order. Read the boundaries off the
        # full frame -- the user may not have chosen to print Order_Number.
        order_boundaries = (
            sorted_list["Order_Number"].ne(sorted_list["Order_Number"].shift()).cumsum()
        )

        generation_timestamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        output_filename = os.path.basename(output_file)

        # The timestamp and the filename ride on two column headers when those
        # columns are printed -- that is the established look. With a custom
        # column set they may be absent, so the same metadata also goes into
        # the Excel print header, where it cannot be lost.
        rename_map = {
            col: label
            for col, label in (
                ("Shipping_Provider", generation_timestamp),
                ("Warehouse_Name", output_filename),
            )
            if col in print_list.columns
        }
        print_list = print_list.rename(columns=rename_map)

        logger.info("Creating Excel file...")
        with pd.ExcelWriter(output_file, engine="xlsxwriter") as writer:
            sheet_name = os.path.splitext(output_filename)[0]
            print_list.to_excel(writer, sheet_name=sheet_name, index=False)

            workbook = writer.book
            worksheet = writer.sheets[sheet_name]

            # --- Excel Formatting ---
            header_format = workbook.add_format(
                {
                    "bold": True,
                    "font_size": 10,
                    "align": "center",
                    "valign": "vcenter",
                    "border": 2,
                    "bg_color": "#F2F2F2",
                }
            )

            for col_num, value in enumerate(print_list.columns):
                worksheet.write(0, col_num, value, header_format)

            # Define cell formats for different row positions (top, middle, bottom of an order)
            formats = {
                "top": {"top": 2, "left": 1, "right": 1, "bottom": 1, "bottom_color": "#DCDCDC"},
                "middle": {"left": 1, "right": 1, "bottom": 1, "bottom_color": "#DCDCDC"},
                "bottom": {"bottom": 2, "left": 1, "right": 1},
                "full": {"border": 2},
            }
            cell_formats = {}
            for key, base_props in formats.items():
                props_default = {**base_props, "valign": "vcenter"}
                cell_formats[key] = workbook.add_format(props_default)
                props_centered = {**props_default, "align": "center"}
                cell_formats[key + "_centered"] = workbook.add_format(props_centered)

            # Apply borders to group items by order number
            for row_num in range(len(print_list)):
                is_top = (row_num == 0) or (order_boundaries.iloc[row_num] != order_boundaries.iloc[row_num - 1])
                is_bottom = (row_num == len(print_list) - 1) or (
                    order_boundaries.iloc[row_num] != order_boundaries.iloc[row_num + 1]
                )

                row_type = "full" if is_top and is_bottom else "top" if is_top else "bottom" if is_bottom else "middle"

                for col_num, col_name in enumerate(print_list.columns):
                    original_col_name = columns_for_print[col_num]
                    fmt_key = (
                        row_type + "_centered"
                        if original_col_name in ["Destination_Country", "Quantity", "Lot_Expiry", "Lot_Batch"]
                        else row_type
                    )
                    worksheet.write(row_num + 1, col_num, print_list.iloc[row_num, col_num], cell_formats[fmt_key])

            # Auto-adjust column widths
            for i, col in enumerate(print_list.columns):
                max_len = max(print_list[col].astype(str).map(len).max(), len(col)) + 2
                original_col_name = columns_for_print[i]
                if original_col_name == "Destination_Country":
                    max_len = 5
                elif original_col_name == "Warehouse_Name":
                    max_len = min(max_len, 45)
                elif original_col_name == "SKU":
                    max_len = min(max_len, 25)
                elif original_col_name == "Lot_Expiry":
                    max_len = 10
                elif original_col_name == "Lot_Batch":
                    max_len = min(max_len, 14)
                worksheet.set_column(i, i, max_len)

            # Set print settings
            worksheet.set_paper(9)  # A4 paper
            worksheet.set_header(f"&L{output_filename}&R{generation_timestamp}")
            worksheet.set_landscape()
            worksheet.repeat_rows(0)  # Repeat header row
            worksheet.fit_to_pages(1, 0)  # Fit to 1 page wide

        logger.info(f"Report '{report_name}' created successfully.")

    except Exception:
        logger.exception("ERROR while creating packing list")
        raise
