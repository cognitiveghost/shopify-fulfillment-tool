import os
import logging
import pandas as pd
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List
from . import analysis, packing_lists, stock_export
from .rules import RuleEngine
from .utils import get_persistent_data_path
from .csv_utils import normalize_sku
from .session_manager import SessionManagerError
import numpy as np

SYSTEM_TAGS = ["Repeat", "Priority", "Error"]

logger = logging.getLogger("ShopifyToolLogger")


def _normalize_unc_path(path):
    """Normalizes a path, which is especially useful for UNC paths on Windows."""
    if not path:
        return path
    # os.path.normpath will convert / to \ on Windows and handle other inconsistencies
    return os.path.normpath(path)


def _get_sku_dtype_dict(column_mappings: dict, file_type: str) -> dict:
    """
    Get dtype dictionary to force SKU columns to string type during CSV loading.

    This prevents pandas from auto-detecting numeric SKUs as float64, which
    causes "5170" to become "5170.0" after string conversion.

    Args:
        column_mappings: Column mappings from config
        file_type: 'orders' or 'stock'

    Returns:
        dict: dtype specification for pd.read_csv() (e.g., {"Lineitem sku": str})

    Examples:
        >>> mappings = {"orders": {"Lineitem sku": "SKU"}}
        >>> _get_sku_dtype_dict(mappings, "orders")
        {"Lineitem sku": str}
    """
    mappings = column_mappings.get(file_type, {})

    # Find all CSV column names that map to SKU
    sku_columns = [csv_col for csv_col, internal_name in mappings.items()
                   if internal_name == "SKU"]

    # Create dtype dict: {column_name: str}
    dtype_dict = {col: str for col in sku_columns}

    if dtype_dict:
        logger.info(f"Forcing string dtype for {file_type} SKU columns: {list(dtype_dict.keys())}")

    return dtype_dict


def build_packing_order_data(order_number: str, group: pd.DataFrame) -> Dict[str, Any]:
    """Build canonical order metadata dict for Packer-tool JSON integration.

    Used by both analysis_data.json and packing list JSON generators
    to ensure consistent metadata across both communication files.
    Backwards-compat aliases (courier, status, shipping_country) are
    always included so both JSON files are structurally identical.

    Args:
        order_number: The order number string
        group: DataFrame group containing all rows for this order

    Returns:
        Dict[str, Any]: Canonical order metadata including all required fields for Packer-tool
    """
    first_row = group.iloc[0]

    # Parse Internal_Tags: "[]" JSON string → Python list
    tags_raw = first_row.get("Internal_Tags", "[]") or "[]"
    try:
        internal_tags: List[str] = json.loads(tags_raw) if isinstance(tags_raw, str) else []
    except (json.JSONDecodeError, TypeError):
        internal_tags = []

    # Parse Tags: "tag1, tag2" CSV string → list
    tags_value = first_row.get("Tags", "") or ""
    tags_list: List[str] = [t.strip() for t in str(tags_value).split(',') if t.strip()] if str(tags_value).strip() else []

    # Optional Order_Min_Box (only present if weight config is active)
    # pd.isna() handles None, float('nan'), pd.NaT from pandas mixed-type columns
    min_box_raw = first_row.get("Order_Min_Box", None)
    order_min_box: Optional[str] = (
        str(min_box_raw)
        if min_box_raw is not None and not pd.isna(min_box_raw) and str(min_box_raw) != ""
        else None
    )

    shipping_provider: str = str(first_row.get("Shipping_Provider", "") or "")
    fulfillment_status: str = str(first_row.get("Order_Fulfillment_Status", "Unknown") or "Unknown")
    destination_country: str = str(first_row.get("Destination_Country", "") or "")

    # Build items list with safe Quantity conversion (guards against NaN / non-numeric)
    items: List[Dict[str, Any]] = []
    for _, row in group.iterrows():
        warehouse_name = row.get("Warehouse_Name", "")
        if not warehouse_name or warehouse_name == "N/A":
            warehouse_name = row.get("Product_Name", "")

        qty_raw = row.get("Quantity", 0)
        try:
            quantity: int = int(qty_raw) if qty_raw is not None and not pd.isna(qty_raw) else 0
        except (ValueError, TypeError):
            quantity = 0

        items.append({
            "sku": str(row.get("SKU", "")),
            "product_name": str(warehouse_name),
            "quantity": quantity,
            "order_fulfillment_status": str(row.get("Order_Fulfillment_Status", "") or ""),
            "status_note": str(row.get("Status_Note", "") or ""),
            "system_note": str(row.get("System_note", "") or ""),
        })

    return {
        "order_number": str(order_number),
        "order_type": str(first_row.get("Order_Type", "") or ""),
        # Canonical fields
        "shipping_provider": shipping_provider,
        "order_fulfillment_status": fulfillment_status,
        "destination_country": destination_country,
        # Backwards-compat aliases — always present so both JSON files are
        # structurally identical regardless of which generator produced them
        "courier": shipping_provider,
        "status": fulfillment_status,
        "shipping_country": destination_country,
        # Metadata fields
        "tags": tags_list,
        "notes": str(first_row.get("Notes", "") or ""),
        "system_note": str(first_row.get("System_note", "") or ""),
        "internal_tags": internal_tags,
        "order_min_box": order_min_box,
        "items": items,
    }


def _create_analysis_data_for_packing(final_df: pd.DataFrame) -> Dict[str, Any]:
    """Create analysis_data.json structure for Packing Tool integration.

    This function extracts relevant data from the analysis DataFrame and
    formats it in a structure that the Packing Tool can consume.

    Args:
        final_df (pd.DataFrame): The final analysis DataFrame

    Returns:
        Dict[str, Any]: Dictionary containing analysis data in Packing Tool format
    """
    try:
        # Group by Order_Number to get order-level data
        orders_data = []
        grouped = final_df.groupby("Order_Number")

        for order_number, group in grouped:
            orders_data.append(build_packing_order_data(str(order_number), group))

        # Calculate statistics
        total_orders = len(orders_data)
        fulfillable_orders = len([o for o in orders_data if o["order_fulfillment_status"] == "Fulfillable"])
        not_fulfillable_orders = total_orders - fulfillable_orders

        analysis_data = {
            "analyzed_at": datetime.now().isoformat(),
            "total_orders": total_orders,
            "fulfillable_orders": fulfillable_orders,
            "not_fulfillable_orders": not_fulfillable_orders,
            "orders": orders_data
        }

        return analysis_data

    except KeyError as e:
        logger.error(f"Missing required column in DataFrame for packing analysis: {e}")
        return {
            "analyzed_at": datetime.now().isoformat(),
            "total_orders": 0,
            "fulfillable_orders": 0,
            "not_fulfillable_orders": 0,
            "orders": [],
            "error": f"Missing required column: {e}"
        }
    except (ValueError, TypeError) as e:
        logger.error(f"Invalid data type in DataFrame for packing analysis: {e}")
        return {
            "analyzed_at": datetime.now().isoformat(),
            "total_orders": 0,
            "fulfillable_orders": 0,
            "not_fulfillable_orders": 0,
            "orders": [],
            "error": f"Invalid data type: {e}"
        }
    except AttributeError as e:
        logger.error(f"Invalid DataFrame object for packing analysis: {e}")
        return {
            "analyzed_at": datetime.now().isoformat(),
            "total_orders": 0,
            "fulfillable_orders": 0,
            "not_fulfillable_orders": 0,
            "orders": [],
            "error": f"Invalid DataFrame: {e}"
        }
    except Exception as e:
        logger.error(f"Unexpected error creating analysis data for packing: {e}", exc_info=True)
        return {
            "analyzed_at": datetime.now().isoformat(),
            "total_orders": 0,
            "fulfillable_orders": 0,
            "not_fulfillable_orders": 0,
            "orders": [],
            "error": str(e)
        }


def _validate_dataframes(orders_df, stock_df, config):
    """Validates that the required columns are present in the dataframes.

    Checks the orders and stock DataFrames against the required CSV column names
    from the column mappings configuration.

    Args:
        orders_df (pd.DataFrame): The DataFrame containing order data.
        stock_df (pd.DataFrame): The DataFrame containing stock data.
        config (dict): The application configuration dictionary, which contains
            the 'column_mappings' with 'orders' and 'stock' dictionaries
            mapping CSV column names to internal names.

    Returns:
        list[str]: A list of error messages. If the list is empty,
                   validation passed.
    """
    errors = []
    column_mappings = config.get("column_mappings", {})

    # Define which internal names are required
    REQUIRED_INTERNAL_ORDERS = ["Order_Number", "SKU", "Quantity", "Shipping_Method"]
    REQUIRED_INTERNAL_STOCK = ["SKU", "Stock"]

    # Get mappings (v2 format)
    orders_mappings = column_mappings.get("orders", {})
    stock_mappings = column_mappings.get("stock", {})

    # For backward compatibility: check if v1 format and migrate
    if not orders_mappings and "orders_required" in column_mappings:
        # V1 format detected - use default Shopify mappings
        logger.warning("V1 column_mappings detected in validation, using default Shopify mappings")
        orders_mappings = {
            "Name": "Order_Number",
            "Lineitem sku": "SKU",
            "Lineitem quantity": "Quantity",
            "Shipping Method": "Shipping_Method"
        }
        stock_mappings = {
            "Артикул": "SKU",
            "Наличност": "Stock"
        }

    # Build reverse mapping (internal_name -> csv_column_name)
    internal_to_csv_orders = {v: k for k, v in orders_mappings.items()}
    internal_to_csv_stock = {v: k for k, v in stock_mappings.items()}

    # Check orders DataFrame for required columns
    for internal_name in REQUIRED_INTERNAL_ORDERS:
        csv_column = internal_to_csv_orders.get(internal_name)
        if csv_column is None:
            errors.append(f"Missing mapping for required field '{internal_name}' in orders configuration")
        elif csv_column not in orders_df.columns:
            errors.append(f"Missing required column in Orders file: '{csv_column}' (needed for {internal_name})")

    # Check stock DataFrame for required columns
    for internal_name in REQUIRED_INTERNAL_STOCK:
        csv_column = internal_to_csv_stock.get(internal_name)
        if csv_column is None:
            errors.append(f"Missing mapping for required field '{internal_name}' in stock configuration")
        elif csv_column not in stock_df.columns:
            errors.append(f"Missing required column in Stock file: '{csv_column}' (needed for {internal_name})")

    return errors


def validate_csv_headers(file_path, required_columns, delimiter=","):
    """Quickly validates if a CSV file contains the required column headers.

    This function reads only the header row of a CSV file to check for the
    presence of required columns without loading the entire file into memory.

    Args:
        file_path (str): The path to the CSV file.
        required_columns (list[str]): A list of CSV column names that must be present.
            These should be the actual column names from the CSV file, not internal names.
        delimiter (str, optional): The delimiter used in the CSV file.
            Defaults to ",".

    Returns:
        tuple[bool, list[str]]: A tuple containing:
            - bool: True if all required columns are present, False otherwise.
            - list[str]: A list of missing columns. An empty list if all are
              present. Returns a list with an error message on file read
              errors.
    """
    if not required_columns:
        return True, []

    try:
        headers = pd.read_csv(file_path, nrows=0, delimiter=delimiter, encoding='utf-8-sig').columns.tolist()
        missing_columns = [col for col in required_columns if col not in headers]

        if not missing_columns:
            return True, []
        else:
            return False, missing_columns

    except FileNotFoundError:
        return False, [f"File not found at path: {file_path}"]
    except pd.errors.ParserError as e:
        logger.error(f"Parser error validating CSV '{file_path}': {e}", exc_info=True)
        return False, [f"Could not parse file. It might be corrupt or not a valid CSV. Error: {e}"]
    except Exception as e:
        logger.error(f"Unexpected error validating CSV headers for {file_path}: {e}", exc_info=True)
        return False, [f"An unexpected error occurred: {e}"]


def _validate_and_prepare_inputs(
    stock_file_path: Optional[str],
    orders_file_path: Optional[str],
    output_dir_path: str,
    client_id: Optional[str],
    session_manager: Optional[Any],
    session_path: Optional[str]
) -> Tuple[bool, Optional[str], str, Optional[str]]:
    """Validates inputs and prepares session/working paths.

    Determines whether to use session-based or legacy workflow mode,
    creates or validates session directory, and copies input files
    to session if needed.

    Args:
        stock_file_path: Path to stock CSV file or None for test mode
        orders_file_path: Path to orders CSV file or None for test mode
        output_dir_path: Legacy output directory path
        client_id: Client identifier for session mode
        session_manager: SessionManager instance for session mode
        session_path: Existing session path or None to create new

    Returns:
        Tuple of (use_session_mode, working_path, error_message, session_path)
        where error_message is None on success

    Raises:
        Exception: Propagated from session operations
    """
    logger.debug("Validating and preparing inputs...")

    # Determine if using session-based workflow
    use_session_mode = session_manager is not None and client_id is not None

    # Handle session path based on workflow mode
    if use_session_mode:
        # If session_path not provided, create a new session
        if session_path is None:
            try:
                logger.info(f"Creating new session for client: {client_id}")
                session_path = session_manager.create_session(client_id)
                logger.info(f"Session created at: {session_path}")
            except SessionManagerError as e:
                error_msg = f"Failed to create session for client {client_id}: {e}"
                logger.error(error_msg, exc_info=True)
                raise ValueError(error_msg)
            except (OSError, PermissionError) as e:
                error_msg = f"File system error creating session for client {client_id}: {e}"
                logger.error(error_msg, exc_info=True)
                raise ValueError(error_msg)

        working_path = session_path
        logger.info(f"Using session-based workflow for client: {client_id}")
        logger.info(f"Session path: {working_path}")
    else:
        # Legacy mode: use output_dir_path
        working_path = output_dir_path
        logger.debug("Using legacy workflow mode")

    # Copy input files to session if in session mode
    if use_session_mode and stock_file_path and orders_file_path:
        try:
            # Copy input files to session/input/
            input_dir = session_manager.get_input_dir(working_path)

            # Copy with standardized names
            orders_dest = Path(input_dir) / "orders_export.csv"
            stock_dest = Path(input_dir) / "inventory.csv"

            logger.info(f"Copying orders file to: {orders_dest}")
            shutil.copy2(orders_file_path, orders_dest)

            logger.info(f"Copying stock file to: {stock_dest}")
            shutil.copy2(stock_file_path, stock_dest)

            # Update session info with input file names
            session_manager.update_session_info(working_path, {
                "orders_file": "orders_export.csv",
                "stock_file": "inventory.csv"
            })

            logger.info("Input files copied to session directory")
        except FileNotFoundError as e:
            error_msg = f"Input file not found during session setup: {e}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        except PermissionError as e:
            error_msg = f"Permission denied copying files to session directory: {e}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        except SessionManagerError as e:
            error_msg = f"Session manager error during setup: {e}"
            logger.error(error_msg, exc_info=True)
            raise ValueError(error_msg)
        except OSError as e:
            error_msg = f"File system error during session setup (disk full or invalid path?): {e}"
            logger.error(error_msg, exc_info=True)
            raise ValueError(error_msg)

    return use_session_mode, working_path, None, session_path


def _load_and_validate_files(
    stock_file_path: Optional[str],
    orders_file_path: Optional[str],
    stock_delimiter: str,
    orders_delimiter: str,
    config: dict
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Loads and validates CSV files.

    Loads stock and orders CSV files, applies proper encoding and
    dtype specifications for SKU columns, and validates required
    columns are present.

    Args:
        stock_file_path: Path to stock CSV or None for test mode
        orders_file_path: Path to orders CSV or None for test mode
        stock_delimiter: Delimiter for stock file
        orders_delimiter: Delimiter for orders file
        config: Configuration dict containing column_mappings and test data

    Returns:
        Tuple of (orders_df, stock_df)

    Raises:
        FileNotFoundError: If input files don't exist
        pd.errors.ParserError: If CSV parsing fails
        UnicodeDecodeError: If encoding is incorrect
        ValueError: If validation fails
    """
    logger.info("Loading data files...")

    if stock_file_path is not None and orders_file_path is not None:
        # Normalize paths to handle UNC paths from network shares correctly
        stock_file_path = _normalize_unc_path(stock_file_path)
        orders_file_path = _normalize_unc_path(orders_file_path)

        if not os.path.exists(stock_file_path) or not os.path.exists(orders_file_path):
            raise FileNotFoundError("One or both input files were not found.")

        # Get dtype specifications to force SKU columns to string
        column_mappings = config.get("column_mappings", {})
        stock_dtype = _get_sku_dtype_dict(column_mappings, "stock")
        orders_dtype = _get_sku_dtype_dict(column_mappings, "orders")

        # Load stock file with error handling
        try:
            logger.info(f"Reading stock file from normalized path: {stock_file_path}")
            stock_df = pd.read_csv(
                stock_file_path,
                delimiter=stock_delimiter,
                encoding='utf-8-sig',
                dtype=stock_dtype
            )
            logger.info(f"Stock data loaded: {len(stock_df)} rows, {len(stock_df.columns)} columns")
        except pd.errors.ParserError as e:
            error_msg = (
                f"Failed to parse stock file. The file may have incorrect delimiter.\n"
                f"Current delimiter: '{stock_delimiter}'\n"
                f"Error: {str(e)}"
            )
            logger.error(error_msg)
            raise
        except FileNotFoundError as e:
            error_msg = f"Stock file not found at path: {stock_file_path}"
            logger.error(error_msg)
            raise
        except PermissionError as e:
            error_msg = f"Permission denied reading stock file: {stock_file_path}"
            logger.error(error_msg)
            raise
        except UnicodeDecodeError as e:
            error_msg = (
                f"Failed to read stock file due to encoding issue.\n"
                f"Please ensure file is UTF-8 encoded.\n"
                f"Error: {str(e)}"
            )
            logger.error(error_msg)
            raise
        except pd.errors.ParserError as e:
            error_msg = f"Failed to parse stock CSV file (corrupted or invalid format): {e}"
            logger.error(error_msg)
            raise
        except Exception as e:
            logger.error(f"Unexpected error loading stock file {stock_file_path}: {e}", exc_info=True)
            raise

        # Load orders file with error handling
        try:
            logger.info(f"Reading orders file from normalized path: {orders_file_path}")
            orders_df = pd.read_csv(
                orders_file_path,
                delimiter=orders_delimiter,
                encoding='utf-8-sig',
                dtype=orders_dtype
            )
            logger.info(f"Orders data loaded: {len(orders_df)} rows, {len(orders_df.columns)} columns")
        except pd.errors.ParserError as e:
            error_msg = (
                f"Failed to parse orders file. The file may have incorrect delimiter.\n"
                f"Current delimiter: '{orders_delimiter}'\n"
                f"Error: {str(e)}"
            )
            logger.error(error_msg)
            raise
        except FileNotFoundError as e:
            error_msg = f"Orders file not found at path: {orders_file_path}"
            logger.error(error_msg)
            raise
        except PermissionError as e:
            error_msg = f"Permission denied reading orders file: {orders_file_path}"
            logger.error(error_msg)
            raise
        except UnicodeDecodeError as e:
            error_msg = (
                f"Failed to read orders file due to encoding issue.\n"
                f"Please ensure file is UTF-8 encoded.\n"
                f"Error: {str(e)}"
            )
            logger.error(error_msg)
            raise
        except pd.errors.ParserError as e:
            error_msg = f"Failed to parse orders CSV file (corrupted or invalid format): {e}"
            logger.error(error_msg)
            raise
        except Exception as e:
            logger.error(f"Unexpected error loading orders file {orders_file_path}: {e}", exc_info=True)
            raise
    else:
        # For testing: allow passing DataFrames directly
        stock_df = config.get("test_stock_df")
        orders_df = config.get("test_orders_df")

    logger.info("Data loaded successfully.")

    # Validate dataframes
    validation_errors = _validate_dataframes(orders_df, stock_df, config)
    if validation_errors:
        error_message = "\n".join(validation_errors)
        logger.error(f"Validation Error: {error_message}")
        raise ValueError(error_message)

    return orders_df, stock_df


def _load_history_data(
    stock_file_path: Optional[str],
    orders_file_path: Optional[str],
    client_id: Optional[str],
    profile_manager: Optional[Any],
    config: dict
) -> pd.DataFrame:
    """Loads fulfillment history from appropriate storage location.

    Determines the correct history file path based on whether profile_manager
    is available (server-based storage) or fallback to local storage.
    Handles various error conditions gracefully.

    Args:
        stock_file_path: Path to stock file (None indicates test mode)
        orders_file_path: Path to orders file (None indicates test mode)
        client_id: Client identifier for server-based storage
        profile_manager: ProfileManager instance for server-based storage
        config: Configuration dict (may contain test_history_df)

    Returns:
        DataFrame with history data (may be empty if no history exists)

    Raises:
        Does not raise - returns empty DataFrame on errors
    """
    logger.info("Loading fulfillment history...")

    # Determine history file location
    if profile_manager and client_id:
        # Server-based storage in client directory
        client_dir = profile_manager.get_client_directory(client_id)
        history_path = client_dir / "fulfillment_history.csv"
        logger.info(f"Using server-based history: {history_path}")
    else:
        # Fallback to local storage for tests/compatibility
        history_path = get_persistent_data_path("fulfillment_history.csv")
        logger.warning("Using local history fallback (no profile manager)")

    # Load history
    if stock_file_path is not None and orders_file_path is not None:
        try:
            if isinstance(history_path, Path):
                history_path_str = str(history_path)
            else:
                history_path_str = history_path

            # Force SKU column to string to prevent dtype issues
            history_dtype = {"SKU": str} if "SKU" in pd.read_csv(
                history_path_str, nrows=0, encoding='utf-8-sig'
            ).columns else {}
            history_df = pd.read_csv(history_path_str, encoding='utf-8-sig', dtype=history_dtype)
            logger.info(f"Loaded {len(history_df)} records from fulfillment history: {history_path}")

            # Apply SKU normalization if SKU column exists
            if not history_df.empty and "SKU" in history_df.columns:
                history_df["SKU"] = history_df["SKU"].apply(normalize_sku)
                logger.debug("Applied SKU normalization to history data")
        except FileNotFoundError:
            history_df = pd.DataFrame(columns=["Order_Number", "Execution_Date"])
            logger.info("No history file found. Starting with empty history.")
        except pd.errors.ParserError as e:
            logger.warning(f"Failed to parse history file: {e}")
            history_df = pd.DataFrame(columns=["Order_Number", "Execution_Date"])
        except UnicodeDecodeError as e:
            logger.warning(f"Encoding error in history file: {e}")
            history_df = pd.DataFrame(columns=["Order_Number", "Execution_Date"])
        except Exception as e:
            logger.warning(f"Could not load history file: {e}")
            history_df = pd.DataFrame(columns=["Order_Number", "Execution_Date"])
    else:
        # Test mode
        history_df = config.get("test_history_df", pd.DataFrame({"Order_Number": []}))

    return history_df


def _run_analysis_and_rules(
    orders_df: pd.DataFrame,
    stock_df: pd.DataFrame,
    history_df: pd.DataFrame,
    config: dict
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    """Runs analysis simulation and applies business rules.

    Executes the core fulfillment analysis, applies low stock alerts,
    and processes custom tagging rules from configuration.

    Args:
        orders_df: Orders DataFrame
        stock_df: Stock DataFrame
        history_df: History DataFrame
        config: Configuration dict with column_mappings, courier_mappings, rules, settings

    Returns:
        Tuple of (final_df, summary_present_df, summary_missing_df, stats)

    Raises:
        Exception: Propagated from analysis.run_analysis()
    """
    logger.info("Running fulfillment simulation...")

    # Get column mappings from config and pass to analysis
    column_mappings = config.get("column_mappings", {})
    # Add set_decoders to column_mappings for set expansion
    if not isinstance(column_mappings, dict):
        column_mappings = {}
    column_mappings["set_decoders"] = config.get("set_decoders", {})

    # Add additional columns from UI settings to column_mappings
    client_config = config.get("_client_config", {})  # Passed from main_window
    ui_settings = client_config.get("ui_settings", {})
    table_view = ui_settings.get("table_view", {})
    additional_columns = table_view.get("additional_columns", [])

    # Inject into column_mappings so analysis receives it
    column_mappings["additional_columns"] = additional_columns
    logger.debug(f"Additional columns config: {len(additional_columns)} columns")
    logger.debug(f"Using column mappings: {column_mappings}")

    # Get courier mappings from config
    courier_mappings = config.get("courier_mappings", {})
    logger.debug(f"Using courier mappings: {courier_mappings}")

    # Get repeat detection window from config
    repeat_window_days = config.get("settings", {}).get("repeat_detection_days", 1)

    # Run core analysis
    final_df, summary_present_df, summary_missing_df, stats = analysis.run_analysis(
        stock_df, orders_df, history_df, column_mappings, courier_mappings,
        repeat_window_days=repeat_window_days
    )
    logger.info("Analysis computation complete.")

    # Debug logging: Verify DataFrame structure
    logger.debug(f"Analysis result columns: {list(final_df.columns)}")
    logger.debug(f"DataFrame shape: {final_df.shape}")
    if not final_df.empty:
        logger.debug(f"Sample row (first): {final_df.iloc[0].to_dict()}")
    if "Order_Fulfillment_Status" in final_df.columns:
        status_counts = final_df["Order_Fulfillment_Status"].value_counts().to_dict()
        logger.debug(f"Order_Fulfillment_Status distribution: {status_counts}")
    else:
        logger.error("CRITICAL: Order_Fulfillment_Status column is missing from analysis result!")

    # Add stock alerts based on config
    low_stock_threshold = config.get("settings", {}).get("low_stock_threshold")
    if low_stock_threshold is not None and "Final_Stock" in final_df.columns:
        logger.info(f"Applying low stock threshold: < {low_stock_threshold}")
        final_df["Stock_Alert"] = np.where(
            final_df["Final_Stock"] < low_stock_threshold,
            "Low Stock",
            ""
        )

    # Enrich DataFrame with volumetric weights before Rule Engine
    weight_config = config.get("weight_config", {})
    if weight_config and weight_config.get("products"):
        from .weight_calculator import enrich_dataframe_with_weights
        final_df = enrich_dataframe_with_weights(final_df, weight_config)

    # Apply the rule engine
    rules = config.get("rules", [])
    if rules:
        logger.info("Applying rule engine...")
        engine = RuleEngine(rules)
        final_df = engine.apply(final_df)
        logger.info("Rule engine application complete.")

    return final_df, summary_present_df, summary_missing_df, stats


def _save_results_and_reports(
    final_df: pd.DataFrame,
    summary_present_df: pd.DataFrame,
    summary_missing_df: pd.DataFrame,
    stats: dict,
    history_df: pd.DataFrame,
    stock_file_path: Optional[str],
    orders_file_path: Optional[str],
    use_session_mode: bool,
    working_path: str,
    output_dir_path: str,
    session_manager: Optional[Any],
    client_id: Optional[str],
    profile_manager: Optional[Any]
) -> Tuple[str, Optional[str]]:
    """Saves all analysis results, reports, and updates history.

    Saves Excel report with analysis results, creates analysis_data.json
    for Packing Tool integration, saves session state files, updates
    session info, and updates fulfillment history.

    Args:
        final_df: Final analysis DataFrame
        summary_present_df: Summary of fulfillable items
        summary_missing_df: Summary of missing items
        stats: Statistics dictionary
        history_df: Current history DataFrame
        stock_file_path: Path to stock file (None for test mode)
        orders_file_path: Path to orders file (None for test mode)
        use_session_mode: Whether using session-based workflow
        working_path: Working directory (session or output path)
        output_dir_path: Legacy output directory
        session_manager: SessionManager instance
        client_id: Client identifier
        profile_manager: ProfileManager instance

    Returns:
        Tuple of (primary_output_path, secondary_output_path)
        In session mode: (session_path, None)
        In legacy mode: (excel_path, None)
        In test mode: (None, None)

    Raises:
        Exception: Propagated from file I/O operations
    """
    # Skip file operations in test mode
    if stock_file_path is None or orders_file_path is None:
        logger.debug("Test mode: skipping file save operations")
        return None, None

    logger.info("Saving analysis report to Excel...")

    # Determine output directory based on mode
    if use_session_mode:
        # Session mode: save to session/analysis/
        analysis_dir = session_manager.get_analysis_dir(working_path)
        output_file_path = str(Path(analysis_dir) / "fulfillment_analysis.xlsx")
        logger.info(f"Session mode: saving to {output_file_path}")
    else:
        # Legacy mode: save to specified output_dir_path
        if not os.path.exists(output_dir_path):
            os.makedirs(output_dir_path)
        output_file_path = os.path.join(output_dir_path, "fulfillment_analysis.xlsx")

    # Save Excel report with multiple sheets
    with pd.ExcelWriter(output_file_path, engine="xlsxwriter") as writer:
        final_df.to_excel(writer, sheet_name="fulfillment_analysis", index=False)
        summary_present_df.to_excel(writer, sheet_name="Summary_Present", index=False)
        summary_missing_df.to_excel(writer, sheet_name="Summary_Missing", index=False)

        workbook = writer.book
        report_info_sheet = workbook.add_worksheet("Report Info")
        generation_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        report_info_sheet.write("A1", "Report Generated On:")
        report_info_sheet.write("B1", generation_time)
        report_info_sheet.set_column("A:B", 25)

        worksheet = writer.sheets["fulfillment_analysis"]
        highlight_format = workbook.add_format({"bg_color": "#FFC7CE", "font_color": "#9C0006"})
        for idx, col in enumerate(final_df.columns):
            try:
                # Convert to string and handle NaN values before calculating length
                col_data = final_df[col]
                # Ensure we have a Series, not DataFrame
                if isinstance(col_data, pd.DataFrame):
                    col_data = col_data.iloc[:, 0]

                col_strings = col_data.astype(str).fillna('')

                # Calculate max length safely
                if len(col_strings) > 0:
                    max_data_len = col_strings.str.len().max()
                    max_len = max(max_data_len, len(str(col))) + 2
                else:
                    max_len = len(str(col)) + 2

                worksheet.set_column(idx, idx, max_len)
            except Exception as e:
                # If column width calculation fails, use default width
                logger.warning(f"Could not calculate width for column '{col}': {e}")
                worksheet.set_column(idx, idx, 15)  # Default width
        for row_num, status in enumerate(final_df["Order_Fulfillment_Status"]):
            if status == "Not Fulfillable":
                worksheet.set_row(row_num + 1, None, highlight_format)
    logger.info(f"Excel report saved to '{output_file_path}'")

    # Save initial state files (current_state.pkl, current_state.xlsx, analysis_stats.json)
    if use_session_mode:
        try:
            logger.info("Saving initial session state files...")

            # Define file paths
            current_state_pkl = Path(analysis_dir) / "current_state.pkl"
            current_state_xlsx = Path(analysis_dir) / "current_state.xlsx"
            stats_json = Path(analysis_dir) / "analysis_stats.json"

            # Save DataFrame to pickle (fast loading)
            logger.info(f"Saving current_state.pkl: {current_state_pkl}")
            final_df.to_pickle(current_state_pkl)

            # Save DataFrame to Excel (backup, human-readable)
            logger.info(f"Saving current_state.xlsx: {current_state_xlsx}")
            final_df.to_excel(current_state_xlsx, index=False)

            # Save statistics to JSON
            logger.info(f"Saving analysis_stats.json: {stats_json}")
            with open(stats_json, 'w', encoding='utf-8') as f:
                json.dump(stats, f, indent=2, ensure_ascii=False)

            logger.info("Initial session state files saved successfully")

        except PermissionError as e:
            logger.error(f"Permission denied saving session state files: {e}")
            # Continue with the workflow even if initial state save fails
        except OSError as e:
            logger.error(f"File system error saving session state (disk full or invalid path?): {e}")
            # Continue with the workflow even if initial state save fails
        except Exception as e:
            logger.error(f"Unexpected error saving initial session state: {e}", exc_info=True)
            # Continue with the workflow even if initial state save fails

    # Session mode: Export analysis_data.json and update session_info
    if use_session_mode:
        try:
            logger.info("Exporting analysis_data.json for Packing Tool integration...")
            analysis_data = _create_analysis_data_for_packing(final_df)

            # Save analysis_data.json
            analysis_data_path = Path(analysis_dir) / "analysis_data.json"
            with open(analysis_data_path, 'w', encoding='utf-8') as f:
                json.dump(analysis_data, f, indent=2, ensure_ascii=False)

            logger.info(f"analysis_data.json saved to: {analysis_data_path}")

            # Update session_info.json with analysis results and statistics
            session_manager.update_session_info(working_path, {
                "analysis_completed": True,
                "analysis_completed_at": datetime.now().isoformat(),
                "total_orders": analysis_data["total_orders"],
                "fulfillable_orders": analysis_data["fulfillable_orders"],
                "not_fulfillable_orders": analysis_data["not_fulfillable_orders"],
                "analysis_report_path": "analysis/analysis_report.xlsx",
                "statistics": {
                    "total_orders": len(final_df["Order_Number"].unique()),
                    "total_items": len(final_df),
                    "packing_lists_count": 0,
                    "packing_lists": []
                }
            })

            logger.info("Session info updated with analysis results and statistics")

        except PermissionError as e:
            logger.error(f"Permission denied exporting analysis data: {e}")
            # Continue with the workflow even if export fails
        except OSError as e:
            logger.error(f"File system error exporting analysis data (disk full or invalid path?): {e}")
            # Continue with the workflow even if export fails
        except SessionManagerError as e:
            logger.error(f"Session manager error updating session info: {e}", exc_info=True)
            # Continue with the workflow even if export fails
        except Exception as e:
            logger.error(f"Unexpected error exporting analysis data: {e}", exc_info=True)
            # Continue with the workflow even if export fails

    # Update fulfillment history
    logger.info("Updating fulfillment history...")
    newly_fulfilled = final_df[final_df["Order_Fulfillment_Status"] == "Fulfillable"][
        ["Order_Number"]
    ].drop_duplicates()

    if not newly_fulfilled.empty:
        newly_fulfilled["Execution_Date"] = datetime.now().strftime("%Y-%m-%d")
        updated_history = pd.concat([history_df, newly_fulfilled]).drop_duplicates(
            subset=["Order_Number"], keep="last"
        )

        # Determine history path (same logic as load)
        if profile_manager and client_id:
            client_dir = profile_manager.get_client_directory(client_id)
            history_path = client_dir / "fulfillment_history.csv"
        else:
            history_path = get_persistent_data_path("fulfillment_history.csv")

        # Save updated history
        try:
            # Ensure parent directory exists
            if isinstance(history_path, Path):
                history_path.parent.mkdir(parents=True, exist_ok=True)
                history_path_str = str(history_path)
            else:
                history_path_str = history_path
                parent_dir = os.path.dirname(history_path_str)
                if parent_dir:
                    os.makedirs(parent_dir, exist_ok=True)

            updated_history.to_csv(history_path_str, index=False)
            logger.info(f"History updated and saved to: {history_path} ({len(newly_fulfilled)} new records)")
        except Exception as e:
            logger.error(f"Failed to save history: {e}")
            # Don't fail the entire analysis if history save fails

    # Return appropriate path based on mode
    if use_session_mode:
        return working_path, None
    else:
        return output_file_path, None


def run_full_analysis(
    stock_file_path,
    orders_file_path,
    output_dir_path,
    stock_delimiter,
    orders_delimiter,
    config,
    client_id: Optional[str] = None,
    session_manager: Optional[Any] = None,
    profile_manager: Optional[Any] = None,
    session_path: Optional[str] = None
):
    """Orchestrates the entire fulfillment analysis process.

    This function serves as the main orchestration point for the analysis workflow,
    delegating to specialized sub-functions for validation, loading, processing,
    analysis, and saving.

    Workflow Steps:
    1. Validate inputs and prepare session/working paths
    2. Load and validate CSV files
    3. Load fulfillment history
    4. Run analysis simulation and apply business rules
    5. Save results, reports, and update history

    Session-Based Workflow (when session_manager and client_id provided):
    - Creates new session OR uses provided session_path
    - Copies input files to session/input/
    - Saves analysis results to session/analysis/
    - Exports analysis_data.json for Packing Tool integration
    - Updates session_info.json with results

    Legacy Workflow:
    - Saves results to specified output_dir_path
    - Maintains backward compatibility

    Args:
        stock_file_path (str | None): Path to the stock data CSV file. Can be
            None for testing purposes if a DataFrame is provided in `config`.
        orders_file_path (str | None): Path to the Shopify orders export CSV
            file. Can be None for testing.
        output_dir_path (str): Path to the directory where the output report
            will be saved (legacy mode). Ignored in session mode.
        stock_delimiter (str): The delimiter used in the stock CSV file.
        orders_delimiter (str): The delimiter used in the orders CSV file.
        config (dict): The application configuration dictionary. It can also
            contain test DataFrames under 'test_stock_df' and
            'test_orders_df' keys.
        client_id (str, optional): Client ID for session-based workflow.
        session_manager (SessionManager, optional): Session manager instance.
        profile_manager (ProfileManager, optional): Profile manager instance.
        session_path (str, optional): Path to existing session directory (new workflow).
            If not provided in session mode, a new session will be created automatically.

    Returns:
        tuple[bool, str | None, pd.DataFrame | None, dict | None]:
            A tuple containing:
            - bool: True for success, False for failure.
            - str | None: A message indicating the result. On success, this
              is the path to the output file (or session path). On failure,
              it's an error message.
            - pd.DataFrame | None: The final analysis DataFrame if successful,
              otherwise None.
            - dict | None: A dictionary of calculated statistics if
              successful, otherwise None.
    """
    logger.info("--- Starting Full Analysis Process ---")

    try:
        # Step 1: Validate and prepare inputs
        logger.info("Step 1: Validating and preparing inputs...")
        use_session_mode, working_path, _, session_path = _validate_and_prepare_inputs(
            stock_file_path,
            orders_file_path,
            output_dir_path,
            client_id,
            session_manager,
            session_path
        )

        # Step 2: Load and validate files
        logger.info("Step 2: Loading and validating CSV files...")
        orders_df, stock_df = _load_and_validate_files(
            stock_file_path,
            orders_file_path,
            stock_delimiter,
            orders_delimiter,
            config
        )

        # Step 3: Load history data
        logger.info("Step 3: Loading fulfillment history...")
        history_df = _load_history_data(
            stock_file_path,
            orders_file_path,
            client_id,
            profile_manager,
            config
        )

        # Step 4: Run analysis and apply rules
        logger.info("Step 4: Running analysis and applying rules...")

        # ALWAYS reload client config from disk to get fresh configuration
        # (GUI may have stale config in memory if user changed settings)
        if profile_manager and client_id:
            logger.info("Reloading fresh client config from disk...")
            client_config = profile_manager.load_client_config(client_id)
            config["_client_config"] = client_config

            # Check if there are additional columns configured
            additional_cols = client_config.get("ui_settings", {}).get("table_view", {}).get("additional_columns", [])
            enabled_cols = [col for col in additional_cols if col.get("enabled", False)]
            logger.info(f"Loaded client config: {len(additional_cols)} additional columns configured, {len(enabled_cols)} enabled")
            if enabled_cols:
                logger.info(f"Enabled additional columns: {[col['csv_name'] for col in enabled_cols]}")
        else:
            logger.warning(f"Cannot load client config: profile_manager={profile_manager is not None}, client_id={client_id}")

        final_df, summary_present_df, summary_missing_df, stats = _run_analysis_and_rules(
            orders_df,
            stock_df,
            history_df,
            config
        )

        # Step 5: Save results and reports
        logger.info("Step 5: Saving results and reports...")
        primary_path, _ = _save_results_and_reports(
            final_df,
            summary_present_df,
            summary_missing_df,
            stats,
            history_df,
            stock_file_path,
            orders_file_path,
            use_session_mode,
            working_path,
            output_dir_path,
            session_manager,
            client_id,
            profile_manager
        )

        # Return success
        logger.info("Analysis completed successfully!")
        return True, primary_path, final_df, stats

    except FileNotFoundError as e:
        error_msg = f"File not found: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return False, error_msg, None, None
    except ValueError as e:
        error_msg = f"Validation error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return False, error_msg, None, None
    except pd.errors.ParserError as e:
        error_msg = f"CSV parsing error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return False, error_msg, None, None
    except Exception as e:
        error_msg = f"Analysis failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return False, error_msg, None, None


def create_packing_list_report(
    analysis_df,
    report_config,
    session_manager: Optional[Any] = None,
    session_path: Optional[str] = None
):
    """Generates a single packing list report based on a report configuration.

    Uses the provided analysis DataFrame and a specific report configuration
    to filter and format a packing list. The resulting report is saved to the
    location specified in the configuration.

    Session Mode: When session_manager and session_path are provided, the report
    is saved to the session's packing_lists/ directory and session_info is updated.

    Args:
        analysis_df (pd.DataFrame): The main analysis DataFrame containing
            fulfillment data.
        report_config (dict): A dictionary from the main config file that
            defines the filters, output filename, excluded SKUs, and other
            settings for this specific report.
        session_manager (SessionManager, optional): Session manager for session-based workflow.
        session_path (str, optional): Path to current session directory.

    Returns:
        tuple[bool, str]: A tuple containing:
            - bool: True for success, False for failure.
            - str: A message indicating the result (e.g., success message with
              file path or an error description).
    """
    report_name = report_config.get("name", "Unknown Report")
    try:
        # Determine output path based on mode
        if session_manager and session_path:
            # Session mode: save to session/packing_lists/
            packing_lists_dir = session_manager.get_packing_lists_dir(session_path)
            # Extract just the filename from the configured path
            original_filename = os.path.basename(report_config["output_filename"])
            output_file = str(Path(packing_lists_dir) / original_filename)
            logger.info(f"Session mode: saving packing list to {output_file}")
        else:
            # Legacy mode: use configured path
            output_file = report_config["output_filename"]
            os.makedirs(os.path.dirname(output_file), exist_ok=True)

        packing_lists.create_packing_list(
            analysis_df=analysis_df,
            output_file=output_file,
            report_name=report_name,
            filters=report_config.get("filters"),
            exclude_skus=report_config.get("exclude_skus"),  # Pass the new parameter
        )

        # Verify file was actually created before updating session info
        if not os.path.exists(output_file):
            error_message = f"Packing list file was not created: {output_file}"
            logger.error(error_message)
            return False, error_message

        # Update session info if in session mode
        if session_manager and session_path:
            try:
                session_info = session_manager.get_session_info(session_path)
                generated_lists = session_info.get("packing_lists_generated", [])
                if original_filename not in generated_lists:
                    generated_lists.append(original_filename)
                    session_manager.update_session_info(session_path, {
                        "packing_lists_generated": generated_lists
                    })
                    logger.info(f"Session info updated: added packing list {original_filename}")
            except Exception as e:
                logger.warning(f"Failed to update session info: {e}")

        success_message = f"Report '{report_name}' created successfully at '{output_file}'."
        return True, success_message
    except KeyError as e:
        error_message = f"Configuration error for report '{report_name}': Missing key {e}."
        logger.error(f"Config error for packing list '{report_name}': {e}", exc_info=True)
        return False, error_message
    except PermissionError:
        output_filename = report_config.get('output_filename', 'N/A')
        error_message = f"Permission denied. Could not write report to '{output_filename}'."
        logger.error(
            f"Permission error creating packing list '{report_name}' at '{output_filename}'", exc_info=True
        )
        return False, error_message
    except Exception as e:
        error_message = f"Failed to create report '{report_name}'. See logs/app_errors.log for details."
        logger.error(f"Error creating packing list '{report_name}': {e}", exc_info=True)
        return False, error_message


def get_unique_column_values(df, column_name):
    """Extracts unique, sorted, non-null values from a DataFrame column.

    Args:
        df (pd.DataFrame): The DataFrame to extract values from.
        column_name (str): The name of the column to get unique values from.

    Returns:
        list[str]: A sorted list of unique string-converted values, or an
                   empty list if the column doesn't exist or an error occurs.
    """
    if df.empty or column_name not in df.columns:
        return []
    try:
        unique_values = df[column_name].dropna().unique().tolist()
        return sorted([str(v) for v in unique_values])
    except Exception:
        return []


def create_stock_export_report(
    analysis_df,
    report_config,
    session_manager: Optional[Any] = None,
    session_path: Optional[str] = None,
    tag_categories: Optional[Dict] = None
):
    """Generates a single stock export report based on a configuration.

    Session Mode: When session_manager and session_path are provided, the report
    is saved to the session's stock_exports/ directory and session_info is updated.

    Args:
        analysis_df (pd.DataFrame): The main analysis DataFrame.
        report_config (dict): The configuration for the specific stock export.
            Can include 'apply_writeoff' key (bool) to enable writeoff deduction.
        session_manager (SessionManager, optional): Session manager for session-based workflow.
        session_path (str, optional): Path to current session directory.
        tag_categories (dict, optional): Tag categories config with writeoff mappings.
            Required if apply_writeoff is enabled in report_config.

    Returns:
        tuple[bool, str]: A tuple containing a success flag and a status message.
    """
    report_name = report_config.get("name", "Untitled Stock Export")
    try:
        # Determine output path based on mode
        if session_manager and session_path:
            # Session mode: save to session/stock_exports/
            stock_exports_dir = session_manager.get_stock_exports_dir(session_path)
            # Extract just the filename from the configured path
            original_filename = os.path.basename(report_config["output_filename"])
            output_filename = str(Path(stock_exports_dir) / original_filename)
            logger.info(f"Session mode: saving stock export to {output_filename}")
        else:
            # Legacy mode: use configured path
            output_filename = report_config["output_filename"]
            # Ensure the output directory exists
            output_dir = os.path.dirname(output_filename)
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)

        filters = report_config.get("filters")
        apply_writeoff = report_config.get("apply_writeoff", False)

        stock_export.create_stock_export(
            analysis_df,
            output_filename,
            report_name=report_name,
            filters=filters,
            apply_writeoff=apply_writeoff,
            tag_categories=tag_categories
        )

        # Verify file was actually created before updating session info
        if not os.path.exists(output_filename):
            error_message = f"Stock export file was not created: {output_filename}"
            logger.error(error_message)
            return False, error_message

        # Update session info if in session mode
        if session_manager and session_path:
            try:
                session_info = session_manager.get_session_info(session_path)
                generated_exports = session_info.get("stock_exports_generated", [])
                if original_filename not in generated_exports:
                    generated_exports.append(original_filename)
                    session_manager.update_session_info(session_path, {
                        "stock_exports_generated": generated_exports
                    })
                    logger.info(f"Session info updated: added stock export {original_filename}")
            except Exception as e:
                logger.warning(f"Failed to update session info: {e}")

        success_message = f"Stock export '{report_name}' created successfully at '{output_filename}'."
        return True, success_message
    except KeyError as e:
        error_message = f"Configuration error for stock export '{report_name}': Missing key {e}."
        logger.error(f"Config error for stock export '{report_name}': {e}", exc_info=True)
        return False, error_message
    except PermissionError:
        error_message = "Permission denied. Could not write stock export."
        logger.error(f"Permission error creating stock export '{report_name}'", exc_info=True)
        return False, error_message
    except Exception as e:
        error_message = f"Failed to create stock export '{report_name}'. See logs for details."
        logger.error(f"Error creating stock export '{report_name}': {e}", exc_info=True)
        return False, error_message


def create_writeoff_report(
    analysis_df: pd.DataFrame,
    report_config: Dict,
    tag_categories: Dict,
    session_manager: Optional[Any] = None,
    session_path: Optional[str] = None
) -> Tuple[bool, str]:
    """Generate standalone SKU writeoff report.

    Session Mode: When session_manager and session_path are provided, the report
    is saved to the session's writeoff_reports/ directory and session_info is updated.

    Args:
        analysis_df: The main analysis DataFrame with Internal_Tags.
        report_config: Configuration for the writeoff report.
            Should include 'name' and 'output_filename' keys.
        tag_categories: Tag categories config with writeoff mappings.
        session_manager: Session manager for session-based workflow (optional).
        session_path: Path to current session directory (optional).

    Returns:
        tuple[bool, str]: Success flag and status message.
    """
    report_name = report_config.get("name", "Writeoff Report")

    try:
        # Determine output path based on mode
        if session_manager and session_path:
            # Session mode: save to session/writeoff_reports/
            writeoff_dir = Path(session_path) / "writeoff_reports"
            writeoff_dir.mkdir(exist_ok=True)
            original_filename = os.path.basename(report_config["output_filename"])
            output_filename = str(writeoff_dir / original_filename)
            logger.info(f"Session mode: saving writeoff report to {output_filename}")
        else:
            # Legacy mode: use configured path
            output_filename = report_config["output_filename"]
            output_dir = os.path.dirname(output_filename)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir)

        # Generate report using sku_writeoff module
        from shopify_tool.sku_writeoff import generate_writeoff_report
        generate_writeoff_report(analysis_df, tag_categories, output_filename)

        # Verify file was created
        if not os.path.exists(output_filename):
            error_message = f"Writeoff report file was not created: {output_filename}"
            logger.error(error_message)
            return False, error_message

        # Update session info if in session mode
        if session_manager and session_path:
            try:
                session_info = session_manager.get_session_info(session_path)
                generated_reports = session_info.get("writeoff_reports_generated", [])
                if original_filename not in generated_reports:
                    generated_reports.append(original_filename)
                    session_manager.update_session_info(session_path, {
                        "writeoff_reports_generated": generated_reports
                    })
                    logger.info(f"Session info updated: added writeoff report {original_filename}")
            except Exception as e:
                logger.warning(f"Failed to update session info: {e}")

        success_message = f"Writeoff report '{report_name}' created successfully at '{output_filename}'."
        return True, success_message

    except KeyError as e:
        error_message = f"Configuration error for writeoff report '{report_name}': Missing key {e}."
        logger.error(f"Config error for writeoff report '{report_name}': {e}", exc_info=True)
        return False, error_message
    except PermissionError:
        error_message = "Permission denied. Could not write writeoff report."
        logger.error(f"Permission error creating writeoff report '{report_name}'", exc_info=True)
        return False, error_message
    except Exception as e:
        error_message = f"Failed to create writeoff report '{report_name}'. See logs for details."
        logger.error(f"Error creating writeoff report '{report_name}': {e}", exc_info=True)
        return False, error_message
