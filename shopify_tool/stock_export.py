import logging
import pandas as pd

logger = logging.getLogger("ShopifyToolLogger")


def _expand_lot_summary(filtered_items: pd.DataFrame) -> pd.DataFrame:
    """Aggregate fulfilled quantities per (SKU, expiry, batch) lot for write-off requests.

    When Lot_Details is present in the analysis DataFrame this function replaces
    the simple SKU-level groupby, producing one row per unique (SKU, Годност, Партида)
    combination across all fulfillable orders.  Items with no lot info fall back to
    SKU-only aggregation with empty Годност/Партида values.

    Args:
        filtered_items: Fulfillable order rows from the analysis DataFrame.
                        Must have a 'Lot_Details' column.

    Returns:
        DataFrame with columns: Артикул, Годност, Партида, Наличност
    """
    lot_rows_data: dict = {}   # (sku, expiry, batch) → total qty
    no_lot_skus: dict = {}     # sku → total qty
    # The simulation allocates at the (order, SKU) level — all DataFrame rows for the
    # same (order, SKU) pair carry an identical Lot_Details object representing the full
    # allocation for that pair.  Without this guard we would count the same allocation
    # once per duplicate row instead of once per (order, SKU).
    seen_order_sku: set = set()

    for _, row in filtered_items.iterrows():
        sku = row["SKU"]
        lot_details = row.get("Lot_Details")
        if lot_details and isinstance(lot_details, list) and len(lot_details) > 0:
            order_key = (row.get("Order_Number", ""), sku)
            if order_key in seen_order_sku:
                continue
            seen_order_sku.add(order_key)
            for entry in lot_details:
                expiry = entry.get("expiry") or ""
                if expiry == "1":
                    expiry = ""
                batch = entry.get("batch") or ""
                if batch == "1":
                    batch = ""
                qty = entry.get("qty_allocated", 0)
                key = (sku, expiry, batch)
                lot_rows_data[key] = lot_rows_data.get(key, 0) + qty
        else:
            qty = row.get("Quantity", 0)
            no_lot_skus[sku] = no_lot_skus.get(sku, 0) + qty

    records = []
    for (sku, expiry, batch), qty in lot_rows_data.items():
        if qty > 0:
            records.append({"Артикул": sku, "Годност": expiry, "Партида": batch, "Наличност": int(qty)})
    for sku, qty in no_lot_skus.items():
        if qty > 0:
            records.append({"Артикул": sku, "Годност": "", "Партида": "", "Наличност": int(qty)})

    if not records:
        return pd.DataFrame(columns=["Артикул", "Годност", "Партида", "Наличност"])
    return pd.DataFrame(records)


def create_stock_export(
    analysis_df,
    output_file,
    report_name="Stock Export",
    filters=None,
    apply_writeoff=False,
    tag_categories=None
):
    """Creates a stock export .xls file from scratch.

    This function generates a stock export file programmatically using pandas,
    eliminating the need for a physical template file. The structure is
    hard-coded to ensure consistency.

    Key steps in the process:
    1.  **Filtering**: It filters the main analysis DataFrame to include only
        'Fulfillable' orders that match the provided filter criteria.
    2.  **Summarization**: It summarizes the filtered data, calculating the total
        quantity for each unique SKU.
    3.  **Packaging Materials (Optional)**: If enabled, calculates and adds
        packaging material SKUs based on Internal Tags (e.g., BOX → PKG-BOX-SMALL).
    4.  **DataFrame Creation**: It creates a new DataFrame with the required
        columns: 'Артикул' (for SKU) and 'Наличност' (for quantity).
    5.  **Saving**: The new DataFrame is saved to the specified .xls output file.

    Args:
        analysis_df (pd.DataFrame): The main DataFrame from the fulfillment
            analysis.
        output_file (str): The full path where the new .xls file will be saved.
        report_name (str, optional): The name of the report, used for logging.
            Defaults to "Stock Export".
        filters (list[dict], optional): A list of dictionaries defining filter
            conditions to apply before summarizing the data. Defaults to None.
        apply_writeoff (bool, optional): If True, adds packaging material SKUs
            to the export based on Internal Tags and configured mappings.
            Defaults to False.
        tag_categories (dict, optional): Tag categories config (required if
            apply_writeoff=True). Contains sku_writeoff mappings that define
            which packaging SKUs to add for each tag.
    """
    try:
        logger.info(f"--- Creating report: '{report_name}' ---")

        # Build the query string to filter the DataFrame
        query_parts = ["Order_Fulfillment_Status == 'Fulfillable'"]
        if filters:
            for f in filters:
                field = f.get("field")
                operator = f.get("operator")
                value = f.get("value")

                if not all([field, operator, value is not None]):
                    logger.warning(f"Skipping invalid filter: {f}")
                    continue

                # Correctly quote string values for the query
                if isinstance(value, str):
                    formatted_value = repr(value)
                else:
                    # For lists (for 'in'/'not in') and numbers, no extra quotes are needed.
                    formatted_value = value

                query_parts.append(f"`{field}` {operator} {formatted_value}")

        full_query = " & ".join(query_parts)
        filtered_items = analysis_df.query(full_query).copy()

        # Detect whether lot tracking data is present
        has_lot_details = (
            "Lot_Details" in filtered_items.columns
            and filtered_items["Lot_Details"].notna().any()
        )

        if filtered_items.empty:
            logger.warning(f"Report '{report_name}': No items found matching the criteria.")
            # Still create an empty file with headers
            if has_lot_details:
                export_df = pd.DataFrame(columns=["Артикул", "Годност", "Партида", "Наличност"])
            else:
                export_df = pd.DataFrame(columns=["Артикул", "Наличност"])
        elif has_lot_details:
            # Per-lot aggregation for warehouse write-off precision
            logger.info(f"Report '{report_name}': Using per-lot aggregation (FIFO lot tracking active).")
            export_df = _expand_lot_summary(filtered_items)
            export_df = export_df[export_df["Наличност"] > 0].reset_index(drop=True)
            if export_df.empty:
                logger.warning(f"Report '{report_name}': No items with positive quantity after lot expansion.")
            else:
                logger.info(f"Found {len(export_df)} lot rows to write for report '{report_name}'.")
        else:
            # Summarize quantities by SKU
            sku_summary = filtered_items.groupby("SKU")["Quantity"].sum().astype(int).reset_index()
            sku_summary = sku_summary[sku_summary["Quantity"] > 0]

            if sku_summary.empty:
                logger.warning(f"Report '{report_name}': No items with a positive quantity to export.")
                export_df = pd.DataFrame(columns=["Артикул", "Наличност"])
            else:
                logger.info(f"Found {len(sku_summary)} unique SKUs to write for report '{report_name}'.")

                # Create base export with product SKUs
                export_df = pd.DataFrame({
                    "Артикул": sku_summary["SKU"],
                    "Наличност": sku_summary["Quantity"]
                })

        # Add packaging materials if writeoff enabled (runs for both lot and non-lot paths)
        if apply_writeoff and tag_categories:
            logger.info(f"Calculating packaging materials for report '{report_name}'")
            from shopify_tool.sku_writeoff import calculate_writeoff_quantities

            # Calculate packaging materials needed from FILTERED items
            writeoff_df = calculate_writeoff_quantities(filtered_items, tag_categories)

            if not writeoff_df.empty:
                # Convert packaging materials to stock export format
                packaging_rows = pd.DataFrame({
                    "Артикул": writeoff_df["SKU"],
                    "Наличност": writeoff_df["Writeoff_Quantity"].astype(int)
                })
                # When lot columns are present, add empty lot fields for packaging rows
                if has_lot_details:
                    packaging_rows["Годност"] = ""
                    packaging_rows["Партида"] = ""
                    packaging_rows = packaging_rows[["Артикул", "Годност", "Партида", "Наличност"]]

                # APPEND packaging materials as additional rows
                export_df = pd.concat([export_df, packaging_rows], ignore_index=True)

                logger.info(
                    f"Added {len(packaging_rows)} packaging SKUs to export "
                    f"(total: {packaging_rows['Наличност'].sum()} units)"
                )
            else:
                logger.info("No packaging materials required (no writeoff mappings triggered)")

        # Save to an .xls file
        try:
            with pd.ExcelWriter(output_file, engine="xlwt") as writer:
                export_df.to_excel(writer, index=False, sheet_name="Sheet1")
            logger.info(f"Stock export '{report_name}' created successfully at '{output_file}'.")
        except Exception as e:
            # Fallback for environments where xlwt might not be properly registered
            if "No Excel writer 'xlwt'" in str(e):
                logger.warning("Pandas failed to find 'xlwt' engine. Trying direct save with xlwt.")
                import xlwt
                workbook = xlwt.Workbook()
                sheet = workbook.add_sheet('Sheet1')

                # Write header
                for col_num, value in enumerate(export_df.columns):
                    sheet.write(0, col_num, value)

                # Write data
                for row_num, row in export_df.iterrows():
                    for col_num, value in enumerate(row):
                        sheet.write(row_num + 1, col_num, value)

                workbook.save(output_file)
                logger.info(
                    f"Stock export '{report_name}' created successfully at '{output_file}' using direct xlwt save."
                )
            else:
                raise e

    except Exception as e:
        logger.error(f"Error while creating stock export '{report_name}': {e}")
