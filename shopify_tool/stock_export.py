import logging
import pandas as pd

logger = logging.getLogger("ShopifyToolLogger")

# Canonical column layout for the warehouse ERP's column auto-detection.
# This MUST match the ERP import template exactly (see screenshot in PR):
#   A=Артикул  B=<blank spacer>  C=Мярка  D=Брой  E=Годност  F=Партида
# The blank column (index 1) is an intentional spacer the ERP format expects;
# Годност/Партида are always present (empty when no lot tracking) so the layout
# is identical for every export. Do not reorder/rename — the ERP detects columns
# by position/header.
BLANK_COL = ""
QTY_COL = "Брой"
STOCK_EXPORT_COLUMNS = ["Артикул", BLANK_COL, "Мярка", QTY_COL, "Годност", "Партида"]
UNIT_VALUE = "брой"


def _empty_export_df() -> pd.DataFrame:
    """Empty export frame carrying the full canonical column layout."""
    return pd.DataFrame(columns=STOCK_EXPORT_COLUMNS)


def _finalize_export_df(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce a built export frame to the canonical ERP column layout.

    Accepts frames that use the legacy ``Колич`` quantity name or that omit the
    blank spacer / lot columns, and returns a frame with exactly
    :data:`STOCK_EXPORT_COLUMNS` in order. Idempotent.
    """
    df = df.copy()
    if "Колич" in df.columns:
        df = df.rename(columns={"Колич": QTY_COL})
    if QTY_COL not in df.columns:
        df[QTY_COL] = 0
    df["Мярка"] = UNIT_VALUE
    for col in ("Годност", "Партида"):
        if col not in df.columns:
            df[col] = ""
    df[BLANK_COL] = ""
    return df[STOCK_EXPORT_COLUMNS].reset_index(drop=True)


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
        DataFrame with the canonical layout (:data:`STOCK_EXPORT_COLUMNS`).
    """
    lot_rows_data: dict = {}  # (sku, expiry, batch) → total qty
    no_lot_skus: dict = {}  # sku → total qty
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
            records.append(
                {
                    "Артикул": sku,
                    QTY_COL: int(qty),
                    "Годност": expiry,
                    "Партида": batch,
                }
            )
    for sku, qty in no_lot_skus.items():
        if qty > 0:
            records.append(
                {
                    "Артикул": sku,
                    QTY_COL: int(qty),
                    "Годност": "",
                    "Партида": "",
                }
            )

    if not records:
        return _empty_export_df()
    return _finalize_export_df(pd.DataFrame(records))


def create_stock_export(
    analysis_df,
    output_file,
    report_name="Stock Export",
    filters=None,
    apply_writeoff=False,
    tag_categories=None,
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
    4.  **DataFrame Creation**: Every export uses the canonical ERP column layout
        (:data:`STOCK_EXPORT_COLUMNS`) so the warehouse system auto-detects the
        columns — Артикул, a blank spacer, Мярка, Брой, Годност, Партида.
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
            logger.warning(
                f"Report '{report_name}': No items found matching the criteria."
            )
            # Still create an empty file with the canonical headers
            export_df = _empty_export_df()
        elif has_lot_details:
            # Per-lot aggregation for warehouse write-off precision
            logger.info(
                f"Report '{report_name}': Using per-lot aggregation (FIFO lot tracking active)."
            )
            export_df = _expand_lot_summary(filtered_items)
            export_df = export_df[export_df[QTY_COL] > 0].reset_index(drop=True)
            if export_df.empty:
                logger.warning(
                    f"Report '{report_name}': No items with positive quantity after lot expansion."
                )
            else:
                logger.info(
                    f"Found {len(export_df)} lot rows to write for report '{report_name}'."
                )
        else:
            # Summarize quantities by SKU
            sku_summary = (
                filtered_items.groupby("SKU")["Quantity"]
                .sum()
                .astype(int)
                .reset_index()
            )
            sku_summary = sku_summary[sku_summary["Quantity"] > 0]

            if sku_summary.empty:
                logger.warning(
                    f"Report '{report_name}': No items with a positive quantity to export."
                )
                export_df = _empty_export_df()
            else:
                logger.info(
                    f"Found {len(sku_summary)} unique SKUs to write for report '{report_name}'."
                )

                # Create base export with product SKUs
                export_df = _finalize_export_df(
                    pd.DataFrame(
                        {
                            "Артикул": sku_summary["SKU"],
                            QTY_COL: sku_summary["Quantity"],
                        }
                    )
                )

        # Add packaging materials if writeoff enabled (runs for both lot and non-lot paths)
        if apply_writeoff and tag_categories:
            logger.info(f"Calculating packaging materials for report '{report_name}'")
            from shopify_tool.sku_writeoff import calculate_writeoff_quantities

            # Calculate packaging materials needed from FILTERED items
            writeoff_df = calculate_writeoff_quantities(filtered_items, tag_categories)

            if not writeoff_df.empty:
                # Convert packaging materials to the canonical export layout
                packaging_rows = _finalize_export_df(
                    pd.DataFrame(
                        {
                            "Артикул": writeoff_df["SKU"],
                            QTY_COL: writeoff_df["Writeoff_Quantity"].astype(int),
                        }
                    )
                )

                # APPEND packaging materials as additional rows
                export_df = pd.concat([export_df, packaging_rows], ignore_index=True)

                logger.info(
                    f"Added {len(packaging_rows)} packaging SKUs to export "
                    f"(total: {packaging_rows[QTY_COL].sum()} units)"
                )
            else:
                logger.info(
                    "No packaging materials required (no writeoff mappings triggered)"
                )

        # Guard against any path that bypassed _finalize_export_df
        export_df = _finalize_export_df(export_df)

        # Save to an .xls file using direct xlwt (pandas dropped xlwt engine support)
        import xlwt

        workbook = xlwt.Workbook()
        sheet = workbook.add_sheet("Sheet1")
        for col_num, value in enumerate(export_df.columns):
            sheet.write(0, col_num, value)
        # enumerate, not iterrows() index: export_df may carry a gapped index
        # (e.g. from the Quantity > 0 filter), which would skip/misplace rows.
        for row_num, (_, row) in enumerate(export_df.iterrows()):
            for col_num, value in enumerate(row):
                sheet.write(row_num + 1, col_num, value)
        workbook.save(output_file)
        logger.info(
            f"Stock export '{report_name}' created successfully at '{output_file}'."
        )

    except Exception as e:
        logger.error(f"Error while creating stock export '{report_name}': {e}")


def merge_session_stock_exports(
    session_paths: list, client_id: str = ""
) -> pd.DataFrame:
    """Merge fulfillable order quantities from multiple sessions.

    Reads analysis/current_state.pkl from each session directory and extracts
    quantities from orders with Order_Fulfillment_Status == 'Fulfillable', grouped by SKU.

    Args:
        session_paths: List of path-like objects, each pointing to a session directory.
        client_id: For logging.

    Returns:
        DataFrame with the canonical export layout (:data:`STOCK_EXPORT_COLUMNS`),
        summed across all sessions and sorted by Артикул.
    """
    from pathlib import Path

    all_dfs = []
    for session_path in session_paths:
        session_path = Path(session_path)
        analysis_dir = session_path / "analysis"
        pkl_file = analysis_dir / "current_state.pkl"
        xlsx_file = analysis_dir / "current_state.xlsx"

        df = None
        if pkl_file.exists():
            try:
                df = pd.read_pickle(pkl_file)
            except Exception as e:
                logger.warning(
                    f"[merge_stock client={client_id}] pkl unreadable in {session_path.name}, trying xlsx: {e}"
                )

        if df is None and xlsx_file.exists():
            try:
                df = pd.read_excel(xlsx_file)
            except Exception as e:
                logger.warning(f"Could not read {xlsx_file}: {e}")

        if df is None:
            logger.warning(
                f"[merge_stock client={client_id}] No readable state file in {session_path.name}/analysis"
            )
            continue

        if "Order_Fulfillment_Status" not in df.columns:
            logger.warning(
                f"[merge_stock client={client_id}] No Order_Fulfillment_Status in {session_path.name}"
            )
            continue

        fulfillable = df[df["Order_Fulfillment_Status"] == "Fulfillable"].copy()
        all_dfs.append(fulfillable)
        logger.info(
            f"[merge_stock client={client_id}] {len(fulfillable)} fulfillable rows from {session_path.name}"
        )

    if not all_dfs:
        return _empty_export_df()

    combined = pd.concat(all_dfs, ignore_index=True)

    # Always total by SKU alone here, even when individual sessions used lot
    # tracking (Lot_Details/Годност/Партида): sessions in this merge are
    # already fulfilled/closed, so the specific batch each one drew from is
    # historical record-keeping, not something a cross-session total can
    # attribute to one row anyway. Per-lot precision for a single session's
    # own write-off still comes from create_stock_export(), which is
    # unaffected by this function. Splitting the SAME SKU across multiple
    # rows here (one per distinct expiry/batch) previously contradicted this
    # function's own contract of "grouped by SKU... summed across sessions".
    sku_summary = (
        combined.groupby("SKU")["Quantity"]
        .sum()
        .astype(int)
        .reset_index()
    )
    sku_summary = sku_summary[sku_summary["Quantity"] > 0]
    if sku_summary.empty:
        return _empty_export_df()

    result = _finalize_export_df(
        pd.DataFrame(
            {
                "Артикул": sku_summary["SKU"],
                QTY_COL: sku_summary["Quantity"],
            }
        )
    )
    return result.sort_values("Артикул").reset_index(drop=True)
