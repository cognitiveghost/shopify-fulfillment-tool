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
    """Validate a 'start-end' range exactly as the rule engine will read it.

    Valid means rules._parse_range accepts it, so the page and the engine
    can't disagree (AUDIT-03-9). A reversed range is an error, not a warning:
    the engine refuses it. The third slot is kept for callers and is None.

    Examples:
        >>> validate_range("10-100")
        (True, None, None)
        >>> validate_range("-10-0")
        (True, None, None)
        >>> validate_range("100-10")[0]
        False
    """
    from shopify_tool.rules import RANGE_PATTERN, _parse_range

    text = str(range_str or "").strip()
    if not text:
        return (False, "Range cannot be empty", None)
    if not RANGE_PATTERN.match(text):
        return (False, "Invalid format. Use: start-end (e.g., 10-100)", None)
    if _parse_range(text) is None:
        return (False, "Start is greater than end. Write the smaller number first, for example 10-100.", None)
    return (True, None, None)


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


_NUMERIC_OPERATORS = {
    "is greater than", "is less than",
    "is greater than or equal", "is less than or equal",
}


def condition_error(operator: str, value: str) -> str | None:
    """The error the Rules page shows in red for this condition, or None.

    RulesPage._perform_validation marks red exactly this, and Save refuses
    it, so the two can't disagree (AUDIT-03-5).
    """
    if operator in ("matches regex", "does not match regex"):
        ok, msg = validate_regex(value)
        return None if ok else msg
    if operator in ("between", "not between"):
        ok, msg, _ = validate_range(value)
        return None if ok else msg
    if operator in ("in list", "not in list"):
        ok, _count, msg = validate_list(value)
        return None if ok else msg
    if operator in _NUMERIC_OPERATORS:
        ok, msg = validate_numeric(value)
        return None if ok else msg
    return None
