"""
CSV utility functions for delimiter detection and validation.
"""
import csv
import os
import re
import logging
from typing import Tuple, Any, List, Optional, Dict
import pandas as pd

logger = logging.getLogger(__name__)


def order_number_sort_key(s) -> int:
    """Return a numeric sort key for an order-number string.

    Extracts the last run of digits so that "#1009" < "#1010" < "#1011"
    instead of the lexicographic "#1009" < "#101" < "#1010".
    Returns 0 for strings with no digits.
    """
    nums = re.findall(r'\d+', str(s))
    return int(nums[-1]) if nums else 0


def detect_csv_delimiter(file_path: str, encoding: str = 'utf-8-sig') -> Tuple[str, str]:
    """
    Automatically detect CSV delimiter.

    Uses multiple methods with fallback:
    1. csv.Sniffer (standard library)
    2. Manual counting (most reliable)
    3. pandas sep=None (optional)

    Args:
        file_path: Path to CSV file
        encoding: File encoding (default: utf-8-sig)

    Returns:
        tuple: (delimiter, detection_method)
            delimiter: Detected delimiter character
            detection_method: String describing how it was detected

    Example:
        >>> delimiter, method = detect_csv_delimiter("orders.csv")
        >>> print(f"Detected: {delimiter} using {method}")
        Detected: , using sniffer
    """
    # Method 1: csv.Sniffer (fast and reliable for standard formats)
    try:
        with open(file_path, 'r', encoding=encoding) as f:
            sample = f.read(2048)  # Read first 2KB
            sniffer = csv.Sniffer()
            delimiter = sniffer.sniff(sample).delimiter

            # Validate: delimiter should be a common CSV delimiter
            # Reject unusual delimiters that might be false positives (like ':' from timestamps)
            common_delimiters = [',', ';', '\t', '|']
            if delimiter in common_delimiters and sample.count(delimiter) > 0:
                logger.info(f"Delimiter detected using csv.Sniffer: '{delimiter}'")
                return delimiter, 'sniffer'
            else:
                logger.debug(f"csv.Sniffer detected unusual delimiter '{delimiter}', trying manual detection")
    except Exception as e:
        logger.debug(f"csv.Sniffer failed: {e}")

    # Method 2: Manual counting (most reliable fallback)
    try:
        with open(file_path, 'r', encoding=encoding) as f:
            # Read first 5 lines to get better sample
            lines = [f.readline() for _ in range(5)]
            first_line = lines[0]

            # Count common delimiters
            delimiters = {
                ',': first_line.count(','),
                ';': first_line.count(';'),
                '\t': first_line.count('\t'),
                '|': first_line.count('|')
            }

            # Check consistency across multiple lines
            for line in lines[1:]:
                for delim in delimiters:
                    if line.count(delim) != delimiters[delim]:
                        # Not consistent - reduce confidence
                        delimiters[delim] = 0

            # Find delimiter with highest consistent count
            if max(delimiters.values()) > 0:
                detected = max(delimiters, key=delimiters.get)
                logger.info(f"Delimiter detected by counting: '{detected}' ({delimiters[detected]} occurrences)")
                return detected, 'counting'
    except Exception as e:
        logger.debug(f"Manual counting failed: {e}")

    # Method 3: pandas auto-detection (can be slow for large files)
    try:
        df = pd.read_csv(file_path, sep=None, engine='python',
                        encoding=encoding, nrows=2)

        if len(df.columns) > 1:
            # Try to infer delimiter from loaded data
            with open(file_path, 'r', encoding=encoding) as f:
                first_line = f.readline()
                for delim in [',', ';', '\t', '|']:
                    if first_line.count(delim) >= len(df.columns) - 1:
                        logger.info(f"Delimiter detected using pandas: '{delim}'")
                        return delim, 'pandas'
    except Exception as e:
        logger.debug(f"Pandas auto-detection failed: {e}")

    # Fallback: return comma (most common)
    logger.warning(f"Could not detect delimiter for {file_path}, using default comma")
    return ',', 'default'


def validate_delimiter(file_path: str, delimiter: str, encoding: str = 'utf-8-sig') -> bool:
    """
    Validate that a delimiter works for a CSV file.

    Args:
        file_path: Path to CSV file
        delimiter: Delimiter to test
        encoding: File encoding

    Returns:
        bool: True if delimiter is valid, False otherwise
    """
    try:
        df = pd.read_csv(file_path, delimiter=delimiter,
                        encoding=encoding, nrows=2)

        # Valid if:
        # 1. More than 1 column
        # 2. Headers don't contain the delimiter (would indicate wrong delimiter)
        if len(df.columns) > 1:
            for col in df.columns:
                if delimiter in str(col):
                    return False
            return True
        return False
    except Exception:
        return False


def suggest_delimiter_fix(file_path: str, failed_delimiter: str,
                         encoding: str = 'utf-8-sig') -> Tuple[str, str]:
    """
    Suggest alternative delimiter when current one fails.

    Args:
        file_path: Path to CSV file
        failed_delimiter: Delimiter that didn't work
        encoding: File encoding

    Returns:
        tuple: (suggested_delimiter, confidence)
            confidence: 'high', 'medium', 'low'
    """
    detected, method = detect_csv_delimiter(file_path, encoding)

    if method in ['sniffer', 'counting']:
        confidence = 'high'
    elif method == 'pandas':
        confidence = 'medium'
    else:
        confidence = 'low'

    return detected, confidence


def normalize_sku(sku: Any) -> str:
    """
    Normalize SKU to standard string format.

    Handles common SKU data type issues:
    - Float conversion artifacts (5170.0 → "5170")
    - Whitespace (strips leading/trailing spaces)
    - Alphanumeric SKUs (preserved as-is)
    - None/NaN values (returns empty string)
    - **PRESERVES leading zeros** (e.g., "07" stays "07", not "7")

    This function is critical for ensuring SKU matching works correctly
    when pandas auto-detects numeric SKUs as float64 during CSV loading.

    IMPORTANT: Leading zeros are preserved to maintain compatibility with
    warehouse management systems that use them (e.g., "07", "0042").

    Args:
        sku: SKU value to normalize (can be str, int, float, or NaN)

    Returns:
        str: Normalized SKU string

    Examples:
        >>> normalize_sku(5170.0)
        "5170"
        >>> normalize_sku("5170.0")
        "5170"
        >>> normalize_sku("5170")
        "5170"
        >>> normalize_sku(" 5170 ")
        "5170"
        >>> normalize_sku("ABC-123")
        "ABC-123"
        >>> normalize_sku("07")
        "07"
        >>> normalize_sku("07.0")
        "07"
        >>> normalize_sku(None)
        ""
        >>> normalize_sku(pd.NA)
        ""

    Note:
        This function only removes the .0 suffix from float conversion.
        Leading zeros are preserved. To ensure proper handling, always
        use dtype=str when loading CSV files with SKU columns.
    """
    if pd.isna(sku):
        return ""

    sku_str = str(sku).strip()

    if not sku_str:
        return ""

    # Remove .0 suffix from float conversion (e.g., "5170.0" → "5170")
    # This preserves leading zeros (e.g., "07.0" → "07", not "7")
    if sku_str.endswith('.0'):
        return sku_str[:-2]

    return sku_str


def normalize_sku_for_matching(sku: Any) -> str:
    """
    Normalize SKU for fuzzy matching (e.g., exclude SKU comparisons).

    This is more aggressive than normalize_sku():
    - Removes leading zeros for NUMERIC SKUs (e.g., "07" → "7")
    - Preserves alphanumeric SKUs as-is
    - Handles float artifacts

    Use this function when you want "07" to match with 7, "7", or "07".

    Args:
        sku: SKU value to normalize for matching

    Returns:
        str: Normalized SKU string

    Examples:
        >>> normalize_sku_for_matching(7)
        "7"
        >>> normalize_sku_for_matching("07")
        "7"
        >>> normalize_sku_for_matching("07.0")
        "7"
        >>> normalize_sku_for_matching("0042")
        "42"
        >>> normalize_sku_for_matching("ABC-123")
        "ABC-123"
        >>> normalize_sku_for_matching("01-DM-0379")
        "01-DM-0379"

    Note:
        Use this for exclude_skus filtering, not for main data!
        Main data should use normalize_sku() to preserve leading zeros.
    """
    # First apply standard normalization (handles .0 suffix, whitespace, NaN)
    normalized = normalize_sku(sku)

    if not normalized:
        return normalized

    try:
        # Try to parse as pure number and remove leading zeros
        # "07" → 7 → "7"
        # "0042" → 42 → "42"
        return str(int(float(normalized)))
    except (ValueError, TypeError):
        # Not a pure number (alphanumeric), return as-is
        # "ABC-123" stays "ABC-123"
        # "01-DM-0379" stays "01-DM-0379" (contains non-numeric)
        return normalized


def merge_csv_files(
    file_paths: List[str],
    delimiter: str,
    encoding: str = 'utf-8-sig',
    dtype_dict: Optional[Dict] = None,
    add_source_column: bool = True,
    remove_duplicates: bool = False,
    duplicate_keys: Optional[List[str]] = None
) -> pd.DataFrame:
    """
    Merge multiple CSV files into single DataFrame.

    Args:
        file_paths: List of CSV file paths to merge
        delimiter: CSV delimiter (e.g., "," or ";")
        encoding: File encoding (default: utf-8-sig)
        dtype_dict: Column dtype specs (e.g., {"Lineitem sku": str})
        add_source_column: Add _source_file column for tracking
        remove_duplicates: Remove duplicate rows after merge
        duplicate_keys: Columns to check for duplicates (CSV column names)

    Returns:
        pd.DataFrame: Merged DataFrame

    Raises:
        ValueError: If file_paths is empty
        Exception: If any file fails to load

    Example:
        >>> files = ["shop1.csv", "shop2.csv", "shop3.csv"]
        >>> merged = merge_csv_files(
        ...     files,
        ...     delimiter=",",
        ...     dtype_dict={"Lineitem sku": str},
        ...     remove_duplicates=True,
        ...     duplicate_keys=["Name", "Lineitem sku"]
        ... )
        >>> print(len(merged))
        470  # After removing 5 duplicates
    """
    if not file_paths:
        raise ValueError("No files provided for merging")

    logger.info(f"Starting merge of {len(file_paths)} files")
    dataframes = []

    for filepath in file_paths:
        try:
            df = pd.read_csv(
                filepath,
                delimiter=delimiter,
                encoding=encoding,
                dtype=dtype_dict
            )

            # Add source tracking column
            if add_source_column:
                df['_source_file'] = os.path.basename(filepath)

            dataframes.append(df)
            logger.info(f"✓ Loaded {len(df)} rows from {os.path.basename(filepath)}")

        except Exception as e:
            logger.error(f"✗ Failed to load {os.path.basename(filepath)}: {e}")
            raise Exception(f"Failed to load {os.path.basename(filepath)}: {e}")

    # Concatenate all DataFrames
    merged_df = pd.concat(dataframes, ignore_index=True)
    logger.info(f"Merged {len(dataframes)} files → {len(merged_df)} total rows")

    # Remove duplicates if requested
    if remove_duplicates:
        original_count = len(merged_df)

        if duplicate_keys:
            # Ensure duplicate_keys is a list of strings, not pandas Index or other type
            if hasattr(duplicate_keys, 'tolist'):
                # Convert pandas Index/Series to list
                duplicate_keys = duplicate_keys.tolist()
            elif not isinstance(duplicate_keys, list):
                # Convert any other iterable to list
                duplicate_keys = list(duplicate_keys)

            # Validate that all keys exist in merged_df columns
            missing_keys = [key for key in duplicate_keys if key not in merged_df.columns]
            if missing_keys:
                logger.warning(f"Duplicate keys not found in data: {missing_keys}")
                # Filter to only existing columns
                duplicate_keys = [key for key in duplicate_keys if key in merged_df.columns]

            if duplicate_keys:
                logger.info(f"Checking duplicates on columns: {duplicate_keys}")
                try:
                    merged_df = merged_df.drop_duplicates(
                        subset=duplicate_keys,
                        keep='first'
                    )
                except Exception as e:
                    logger.error(f"Error removing duplicates with keys {duplicate_keys}: {e}")
                    raise
            else:
                logger.warning("No valid duplicate keys found, skipping duplicate removal")
        else:
            # Check duplicates across all columns (excluding _source_file if present)
            # We exclude _source_file because it's just for tracking and shouldn't affect duplicate detection
            cols_to_check = [col for col in merged_df.columns if col != '_source_file']
            if cols_to_check:
                merged_df = merged_df.drop_duplicates(subset=cols_to_check, keep='first')
            else:
                # Fallback if somehow no columns left
                merged_df = merged_df.drop_duplicates(keep='first')

        removed = original_count - len(merged_df)
        if removed > 0:
            logger.info(f"Removed {removed} duplicate rows")

    return merged_df


def discover_additional_columns(
    orders_df: pd.DataFrame,
    column_mappings: dict,
    current_additional_columns: List[dict]
) -> List[dict]:
    """
    Discover available additional columns from orders DataFrame.

    Identifies CSV columns that are not in the standard column mappings
    and could be preserved as additional columns for analysis.

    Args:
        orders_df: Orders DataFrame with CSV column names (before mapping)
        column_mappings: Column mappings dict with 'orders' key
        current_additional_columns: Existing additional columns config

    Returns:
        List of dicts with keys:
            - csv_name: Original CSV column name
            - internal_name: Normalized internal name (spaces→underscores)
            - enabled: Current enabled state (from config or False by default)
            - is_order_level: Current order-level flag (from config or True by default)
            - exists_in_df: Whether column exists in current DataFrame

    Example:
        >>> config = {"orders": {"Name": "Order_Number", "SKU": "SKU"}}
        >>> df = pd.DataFrame({"Name": [1], "SKU": ["A"], "Email": ["x@y.com"]})
        >>> result = discover_additional_columns(df, config, [])
        >>> print(result)
        [{'csv_name': 'Email', 'internal_name': 'Email', 'enabled': False,
          'is_order_level': True, 'exists_in_df': True}]
    """
    # Get standard mapped columns
    mapped_columns = set(column_mappings.get("orders", {}).keys())

    # Get critical internal columns that should never be considered "additional"
    critical_internal = {"Order_Number", "SKU", "Quantity", "Shipping_Method"}

    # Get all DataFrame columns
    all_csv_columns = set(orders_df.columns)

    # Find unmapped columns (candidates for additional columns)
    unmapped_columns = all_csv_columns - mapped_columns

    # Build lookup from existing config
    existing_config_map = {col["csv_name"]: col for col in current_additional_columns}

    # Build result list
    discovered = []
    for csv_name in sorted(unmapped_columns):
        # Normalize name: spaces to underscores, strip whitespace
        internal_name = csv_name.strip().replace(" ", "_").replace("-", "_")

        # Skip if conflicts with critical internal columns
        if internal_name in critical_internal:
            logger.debug(f"Skipping column '{csv_name}' - conflicts with critical column")
            continue

        # Get existing config or use defaults
        if csv_name in existing_config_map:
            existing = existing_config_map[csv_name]
            enabled = existing.get("enabled", False)
            is_order_level = existing.get("is_order_level", True)
        else:
            enabled = False  # New columns default to disabled
            is_order_level = True  # Most Shopify columns are order-level

        discovered.append({
            "csv_name": csv_name,
            "internal_name": internal_name,
            "enabled": enabled,
            "is_order_level": is_order_level,
            "exists_in_df": True
        })

    # Also include previously configured columns that don't exist in current CSV
    for csv_name, config in existing_config_map.items():
        if csv_name not in all_csv_columns:
            discovered.append({
                "csv_name": csv_name,
                "internal_name": config["internal_name"],
                "enabled": config.get("enabled", False),
                "is_order_level": config.get("is_order_level", True),
                "exists_in_df": False
            })

    return discovered
