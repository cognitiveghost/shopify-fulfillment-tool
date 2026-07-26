"""
Validation module for rule conditions.

Provides real-time validation for different operator types:
- Regex pattern validation
- Date format validation
- Range format validation
- List format validation

Reuses helpers from shopify_tool.rules for consistency between
validation and execution.
"""

import logging

logger = logging.getLogger(__name__)


def validate_regex(pattern: str) -> tuple[bool, str | None]:
    """
    Validate regex pattern using rule engine's safe compiler.

    Args:
        pattern: Regex pattern string to validate

    Returns:
        Tuple of (is_valid, error_message)
        - is_valid: True if pattern is valid, False otherwise
        - error_message: None if valid, error description if invalid

    Examples:
        >>> validate_regex("^SKU-\\d{4}$")
        (True, None)
        >>> validate_regex("(unclosed")
        (False, "Invalid regex syntax")
    """
    from shopify_tool.rules import _compile_regex_safe

    if not pattern or not pattern.strip():
        return (False, "Regex pattern cannot be empty")

    compiled = _compile_regex_safe(pattern)
    if compiled is None:
        return (False, "Invalid regex syntax")

    return (True, None)


def validate_date(date_str: str) -> tuple[bool, str | None]:
    """
    Validate date string using rule engine's safe parser.

    Supports multiple formats:
    - ISO: "2024-01-30"
    - European slash: "30/01/2024"
    - European dot: "30.01.2024"
    - Timestamp: "2026-01-14 18:56:50 +0200"

    Args:
        date_str: Date string to validate

    Returns:
        Tuple of (is_valid, error_message)
        - is_valid: True if date is valid, False otherwise
        - error_message: None if valid, error description if invalid

    Examples:
        >>> validate_date("2024-01-30")
        (True, None)
        >>> validate_date("invalid")
        (False, "Invalid date format. Use: YYYY-MM-DD, DD/MM/YYYY, or DD.MM.YYYY")
    """
    from shopify_tool.rules import _parse_date_safe

    if not date_str or not str(date_str).strip():
        return (False, "Date cannot be empty")

    parsed = _parse_date_safe(date_str)
    if parsed is None:
        return (False, "Invalid date format. Use: YYYY-MM-DD, DD/MM/YYYY, or DD.MM.YYYY")

    return (True, None)


def validate_range(range_str: str) -> tuple[bool, str | None, str | None]:
    """
    Validate range string using rule engine's parser.

    Format: "start-end" (e.g., "10-100")

    Args:
        range_str: Range string to validate

    Returns:
        Tuple of (is_valid, error_message, warning_message)
        - is_valid: True if range format is valid, False otherwise
        - error_message: None if valid, error description if invalid
        - warning_message: Warning if start > end (valid format but suspicious)

    Examples:
        >>> validate_range("10-100")
        (True, None, None)
        >>> validate_range("100-10")
        (True, None, "Warning: Start (100.0) > End (10.0)")
        >>> validate_range("invalid")
        (False, "Invalid format. Use: start-end (e.g., 10-100)", None)
    """
    if not range_str or not str(range_str).strip():
        return (False, "Range cannot be empty", None)

    # Manual parsing to detect reversed ranges
    try:
        parts = str(range_str).strip().split("-")
        if len(parts) != 2:
            return (False, "Invalid format. Use: start-end (e.g., 10-100)", None)

        start = float(parts[0].strip())
        end = float(parts[1].strip())

        if start > end:
            return (True, None, f"Warning: Start ({start}) > End ({end})")

        return (True, None, None)

    except ValueError:
        return (False, "Invalid format. Use: start-end (e.g., 10-100)", None)


def validate_list(list_str: str) -> tuple[bool, int, str | None]:
    """
    Validate and count list items.

    List format: "Value1, Value2, Value3"
    - Comma-separated values
    - Spaces are auto-trimmed
    - Case-insensitive matching (in rule execution)

    Args:
        list_str: Comma-separated list string

    Returns:
        Tuple of (is_valid, item_count, error_message)
        - is_valid: True if list is valid, False otherwise
        - item_count: Number of non-empty items in list
        - error_message: None if valid, error description if invalid

    Examples:
        >>> validate_list("A, B, C")
        (True, 3, None)
        >>> validate_list(" A , B ")
        (True, 2, None)
        >>> validate_list("")
        (False, 0, "List cannot be empty")
    """
    if not list_str or not str(list_str).strip():
        return (False, 0, "List cannot be empty")

    # Split, trim, count non-empty items
    items = [item.strip() for item in str(list_str).split(",") if item.strip()]

    if not items:
        return (False, 0, "No valid items in list")

    return (True, len(items), None)


def validate_numeric(value_str: str) -> tuple[bool, str | None]:
    """
    Validate that a string can be converted to a number.

    Used for numeric operators like "is greater than", "is less than", etc.

    Args:
        value_str: String to validate as numeric

    Returns:
        Tuple of (is_valid, error_message)
        - is_valid: True if can be converted to number, False otherwise
        - error_message: None if valid, error description if invalid

    Examples:
        >>> validate_numeric("123")
        (True, None)
        >>> validate_numeric("123.45")
        (True, None)
        >>> validate_numeric("abc")
        (False, "Value must be a number")
    """
    if not value_str or not str(value_str).strip():
        return (False, "Value cannot be empty")

    try:
        float(value_str)
        return (True, None)
    except ValueError:
        return (False, "Value must be a number")
