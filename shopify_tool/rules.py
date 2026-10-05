import copy
import re
import warnings
from functools import lru_cache
from typing import ClassVar

import numpy as np
import pandas as pd

"""Implements a configurable rule engine to process and modify order data.

This module provides a `RuleEngine` class that can apply a series of
user-defined rules to a pandas DataFrame of order data. Rules are defined in a
JSON or dictionary format and can be used to tag orders, change their status,
set priority, and perform other actions based on a set of conditions.

The core components are:
- **Operator Functions**: A set of functions (_op_equals, _op_contains, etc.)
  that perform the actual comparison for rule conditions.
- **OPERATOR_MAP**: A dictionary that maps user-friendly operator names from
  the configuration (e.g., "contains") to their corresponding function.
- **RuleEngine**: A class that takes a list of rule configurations,
  interprets them, and applies the specified actions to the DataFrame rows
  that match the conditions.
"""

# A mapping from user-friendly operator names to internal function names
OPERATOR_MAP = {
    "equals": "_op_equals",
    "does not equal": "_op_not_equals",
    "contains": "_op_contains",
    "does not contain": "_op_not_contains",
    "is greater than": "_op_greater_than",
    "is less than": "_op_less_than",
    "is greater than or equal": "_op_greater_than_or_equal",
    "is less than or equal": "_op_less_than_or_equal",
    "starts with": "_op_starts_with",
    "ends with": "_op_ends_with",
    "is empty": "_op_is_empty",
    "is not empty": "_op_is_not_empty",
    # NEW: List operators
    "in list": "_op_in_list",
    "not in list": "_op_not_in_list",
    # NEW: Range operators
    "between": "_op_between",
    "not between": "_op_not_between",
    # NEW: Date operators
    "date before": "_op_date_before",
    "date after": "_op_date_after",
    "date equals": "_op_date_equals",
    # NEW: Regex operators
    "matches regex": "_op_matches_regex",
    "does not match regex": "_op_does_not_match_regex",
}

# On an order rule a negative operator means *no line* matches the positive
# form, for a line field exactly as for has_sku (spec 2026-09-26 D2).
NEGATIVE_OPERATORS = frozenset({
    "does not equal", "does not contain", "not in list",
    "not between", "does not match regex",
})

# --- Action Helpers ---


def _append_to_note(note: str, value: str) -> str:
    """Append value to a comma-separated Status_Note without duplicates."""
    if value in note.split(", "):
        return note
    return f"{note}, {value}" if note else value


# --- Operator Implementations ---


def _op_equals(series_val, rule_val):
    """Returns True where the series value equals the rule value.

    Handles numeric comparisons by converting rule_val to numeric if series is numeric.
    """
    # If series is numeric, try to convert rule_val to numeric for comparison
    if pd.api.types.is_numeric_dtype(series_val):
        try:
            rule_val_numeric = pd.to_numeric(rule_val, errors='raise')
            return series_val == rule_val_numeric
        except (ValueError, TypeError):
            # If conversion fails, use string comparison
            return series_val.astype(str) == str(rule_val)
    else:
        # For non-numeric series, use direct comparison
        return series_val == rule_val


def _op_not_equals(series_val, rule_val):
    """Returns True where the series value does not equal the rule value.

    Handles numeric comparisons by converting rule_val to numeric if series is numeric.
    """
    # If series is numeric, try to convert rule_val to numeric for comparison
    if pd.api.types.is_numeric_dtype(series_val):
        try:
            rule_val_numeric = pd.to_numeric(rule_val, errors='raise')
            return series_val != rule_val_numeric
        except (ValueError, TypeError):
            # If conversion fails, use string comparison
            return series_val.astype(str) != str(rule_val)
    else:
        # For non-numeric series, use direct comparison
        return series_val != rule_val


def _as_str_series(series_val):
    """Coerce a numeric-dtype Series to string so .str accessors don't crash.

    Non-numeric (object/string) Series are returned unchanged to preserve
    their existing NaN handling via each operator's na=False.
    """
    if pd.api.types.is_numeric_dtype(series_val):
        return series_val.astype(str)
    return series_val


def _op_contains(series_val, rule_val):
    """Returns True where the series string contains the rule string (case-insensitive, literal)."""
    return _as_str_series(series_val).str.contains(rule_val, case=False, na=False, regex=False)


def _op_not_contains(series_val, rule_val):
    """Returns True where the series string does not contain the rule string (case-insensitive, literal)."""
    return ~_op_contains(series_val, rule_val)


def _safe_float(value):
    """Returns float(value), or None if value is blank/non-numeric."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _op_greater_than(series_val, rule_val):
    """Returns True where the series value is greater than the numeric rule value."""
    threshold = _safe_float(rule_val)
    if threshold is None:
        return pd.Series([False] * len(series_val), index=series_val.index)
    return pd.to_numeric(series_val, errors="coerce") > threshold


def _op_less_than(series_val, rule_val):
    """Returns True where the series value is less than the numeric rule value."""
    threshold = _safe_float(rule_val)
    if threshold is None:
        return pd.Series([False] * len(series_val), index=series_val.index)
    return pd.to_numeric(series_val, errors="coerce") < threshold


def _op_greater_than_or_equal(series_val, rule_val):
    """Returns True where the series value is >= numeric rule value."""
    threshold = _safe_float(rule_val)
    if threshold is None:
        return pd.Series([False] * len(series_val), index=series_val.index)
    return pd.to_numeric(series_val, errors="coerce") >= threshold


def _op_less_than_or_equal(series_val, rule_val):
    """Returns True where the series value is <= numeric rule value."""
    threshold = _safe_float(rule_val)
    if threshold is None:
        return pd.Series([False] * len(series_val), index=series_val.index)
    return pd.to_numeric(series_val, errors="coerce") <= threshold


def _op_starts_with(series_val, rule_val):
    """Returns True where the series string starts with the rule string."""
    return _as_str_series(series_val).str.startswith(rule_val, na=False)


def _op_ends_with(series_val, rule_val):
    """Returns True where the series string ends with the rule string."""
    return _as_str_series(series_val).str.endswith(rule_val, na=False)


def _op_is_empty(series_val, rule_val):
    """Returns True where the series value is null or an empty string."""
    return series_val.isnull() | (series_val == "")


def _op_is_not_empty(series_val, rule_val):
    """Returns True where the series value is not null and not an empty string."""
    return series_val.notna() & (series_val != "")


# --- Helper Functions for New Operators ---


# The formats a date condition accepts, tried in this order. The last two
# carry the offset of a Shopify "Created at" value.
DATE_FORMATS = (
    "%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y",
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z",
)

# What %z accepts at the end of a value: +0200, +02:00, Z (and seconds).
_OFFSET_FORMATS = {
    "%Y-%m-%d %H:%M:%S %z": ("%Y-%m-%d %H:%M:%S", re.compile(
        r"^(?P<rest>.*?)\s+(?P<offset>Z|[+-]\d\d:?[0-5]\d(?::?[0-5]\d(?:\.\d{1,6})?)?)$")),
    "%Y-%m-%dT%H:%M:%S%z": ("%Y-%m-%dT%H:%M:%S", re.compile(
        r"^(?P<rest>.*?)(?P<offset>Z|[+-]\d\d:?[0-5]\d(?::?[0-5]\d(?:\.\d{1,6})?)?)$")),
}


def _parse_date_safe(date_str: str) -> pd.Timestamp | None:
    """Safely parse date string with multiple format support.

    Tries these formats in sequence:
    1. YYYY-MM-DD (ISO format)
    2. DD/MM/YYYY (European format)
    3. DD.MM.YYYY (European format with dots)
    4. Shopify "Created at" (YYYY-MM-DD HH:MM:SS +0200) and its ISO form,
       with or without an offset

    Args:
        date_str: Date string to parse

    Returns:
        pd.Timestamp if successfully parsed, None otherwise

    Example:
        >>> _parse_date_safe("2024-01-30")
        Timestamp('2024-01-30 00:00:00')
        >>> _parse_date_safe("30/01/2024")
        Timestamp('2024-01-30 00:00:00')
        >>> _parse_date_safe("invalid")
        None
    """
    import logging
    logger = logging.getLogger(__name__)

    if not date_str or pd.isna(date_str):
        return None

    date_str = str(date_str).strip()

    # A timestamp is compared by the date as written -- the shop's local
    # date -- so the offset is dropped, not converted (spec 2026-09-26 D9).
    for fmt in DATE_FORMATS:
        try:
            parsed = pd.to_datetime(date_str, format=fmt)
        except (ValueError, TypeError):
            continue
        return parsed.tz_localize(None) if parsed.tzinfo is not None else parsed

    logger.warning(f"[RULE ENGINE] Invalid rule date format: '{date_str}'")
    return None


def _parse_dates(series: pd.Series) -> pd.Series:
    """Parse a whole column of dates: one pandas call per format.

    Accepts exactly what _parse_date_safe accepts, with the same results:
    naive datetimes, the offset of a timestamp dropped (the date as
    written, spec 2026-09-26 D9), NaT where a value is blank or matches no
    format. The offset is cut from the text before parsing, so a column
    whose offsets differ (a DST change) parses instead of raising.

    One WARNING, not one per cell, when some non-blank values are not dates.
    """
    import logging
    logger = logging.getLogger(__name__)

    # Positional throughout: the caller's index labels need not be unique.
    values = pd.Series(series.to_numpy(dtype=object))
    blank = values.map(lambda v: True if _is_na_scalar(v) else not v).astype(bool)
    texts = values[~blank].map(lambda v: str(v).strip())
    parsed = pd.Series(pd.NaT, index=texts.index, dtype="datetime64[ns]")

    for fmt in DATE_FORMATS:
        todo = parsed.isna()
        if not todo.any():
            break
        candidates = texts[todo]
        if fmt in _OFFSET_FORMATS:
            naive_fmt, pattern = _OFFSET_FORMATS[fmt]
            candidates = candidates.str.extract(pattern)["rest"].dropna()
            fmt = naive_fmt
        if candidates.empty:
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            got = pd.to_datetime(candidates, format=fmt, errors="coerce")
        parsed[got.index] = got.astype("datetime64[ns]")

    unparsed = parsed.isna() & texts.ne("")
    if unparsed.any():
        logger.warning(
            f"[RULE ENGINE] {int(unparsed.sum())} values in {series.name!r} are not dates, "
            f"e.g. {values[unparsed.idxmax()]!r}"
        )

    result = pd.Series(pd.NaT, index=values.index, dtype="datetime64[ns]")
    result[parsed.index] = parsed
    return pd.Series(result.to_numpy(), index=series.index, name=series.name)


def _is_na_scalar(value) -> bool:
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):  # a list-like cell
        return False


def _date_compare(series_val, rule_val, compare) -> pd.Series:
    """`compare(column dates, rule date)` by date only; an unparseable cell is False."""
    rule_date = _parse_date_safe(rule_val)
    if rule_date is None:
        return pd.Series(False, index=series_val.index, dtype=bool)
    dates = _parse_dates(series_val).dt.normalize()
    return (compare(dates, rule_date.normalize()) & dates.notna()).astype(bool)


@lru_cache(maxsize=128)
def _compile_regex_safe(pattern: str) -> re.Pattern | None:
    """Safely compile regex pattern with caching.

    Uses LRU cache to avoid recompiling patterns on repeated calls.

    Args:
        pattern: Regex pattern string

    Returns:
        Compiled re.Pattern if valid, None otherwise

    Example:
        >>> pattern = _compile_regex_safe(r"^SKU-\\d{4}$")
        >>> pattern.match("SKU-1234")
        <re.Match object; span=(0, 8), match='SKU-1234'>
    """
    import logging
    logger = logging.getLogger(__name__)

    if not pattern or pd.isna(pattern):
        return None

    try:
        return re.compile(str(pattern))
    except re.error as e:
        logger.warning(f"[RULE ENGINE] Invalid regex pattern '{pattern}': {e}")
        return None


# start-end, each side optionally negative: "10-100", "-10-0", "-10--5".
RANGE_PATTERN = re.compile(r"^(-?\d+(?:\.\d+)?)-(-?\d+(?:\.\d+)?)$")


def _parse_range(range_str: str) -> tuple[float, float] | None:
    """Parse range string in format 'start-end'.

    Args:
        range_str: Range string (e.g., "10-100", "5.5-15.5")

    Returns:
        Tuple of (start, end) as floats if valid, None otherwise

    Example:
        >>> _parse_range("10-100")
        (10.0, 100.0)
        >>> _parse_range("invalid")
        None
    """
    import logging
    logger = logging.getLogger(__name__)

    if not range_str or pd.isna(range_str):
        return None

    range_str = str(range_str).strip()

    # Use regex to support negative numbers: e.g. "-10-0", "-10--5"
    # Pattern: optional minus + digits (+ optional decimal) DASH optional minus + digits
    match = RANGE_PATTERN.match(range_str)
    if not match:
        logger.warning(f"[RULE ENGINE] Invalid range format: '{range_str}' (expected 'start-end')")
        return None

    try:
        start = float(match.group(1))
        end = float(match.group(2))

        # Validate order
        if start > end:
            logger.warning(f"[RULE ENGINE] Invalid range: start ({start}) > end ({end})")
            return None

        return (start, end)
    except (ValueError, TypeError) as e:
        logger.warning(f"[RULE ENGINE] Invalid range values in '{range_str}': {e}")
        return None


# --- New Operator Implementations ---


def _op_in_list(series_val, rule_val):
    """Returns True where the series value is in the comma-separated list.

    Performs case-insensitive matching with automatic whitespace trimming.

    Args:
        series_val: pandas Series to check
        rule_val: Comma-separated string (e.g., "DHL,DPD,PostOne")

    Returns:
        pd.Series[bool]: True where value matches any item in list

    Example:
        >>> series = pd.Series(["DHL", "PostOne", "FedEx"])
        >>> _op_in_list(series, "DHL, PostOne")
        0     True
        1     True
        2    False
        dtype: bool
    """
    import logging
    logger = logging.getLogger(__name__)

    if not rule_val or pd.isna(rule_val):
        logger.warning("[RULE ENGINE] Empty list value for 'in list' operator")
        return pd.Series([False] * len(series_val), index=series_val.index)

    # Parse: split, strip, lowercase
    list_values = [v.strip().lower() for v in str(rule_val).split(",") if v.strip()]

    if not list_values:
        return pd.Series([False] * len(series_val), index=series_val.index)

    # Case-insensitive comparison
    series_lower = series_val.astype(str).str.strip().str.lower()
    return series_lower.isin(list_values)


def _op_not_in_list(series_val, rule_val):
    """Returns True where the series value is NOT in the comma-separated list.

    Performs case-insensitive matching with automatic whitespace trimming.

    Args:
        series_val: pandas Series to check
        rule_val: Comma-separated string (e.g., "DHL,DPD,PostOne")

    Returns:
        pd.Series[bool]: True where value does NOT match any item in list

    Example:
        >>> series = pd.Series(["DHL", "PostOne", "FedEx"])
        >>> _op_not_in_list(series, "DHL, PostOne")
        0    False
        1    False
        2     True
        dtype: bool
    """
    import logging
    logger = logging.getLogger(__name__)

    if not rule_val or pd.isna(rule_val):
        logger.warning("[RULE ENGINE] Empty list value for 'not in list' operator")
        return pd.Series([False] * len(series_val), index=series_val.index)

    list_values = [v.strip().lower() for v in str(rule_val).split(",") if v.strip()]
    if not list_values:
        return pd.Series([False] * len(series_val), index=series_val.index)

    return ~_op_in_list(series_val, rule_val)


def _op_between(series_val, rule_val):
    """Returns True where the series value is between start and end (inclusive).

    Tries numeric comparison first, falls back to string comparison.

    Args:
        series_val: pandas Series to check
        rule_val: Range string in format "start-end" (e.g., "10-100")

    Returns:
        pd.Series[bool]: True where value is in range [start, end]

    Example:
        >>> series = pd.Series([5, 15, 25, 105])
        >>> _op_between(series, "10-100")
        0    False
        1     True
        2     True
        3    False
        dtype: bool
    """
    import logging
    logger = logging.getLogger(__name__)

    range_tuple = _parse_range(rule_val)
    if range_tuple is None:
        return pd.Series([False] * len(series_val), index=series_val.index)

    start, end = range_tuple

    # Try numeric comparison
    series_numeric = pd.to_numeric(series_val, errors="coerce")
    if series_numeric.notna().any():
        # Use numeric comparison where possible
        return (series_numeric >= start) & (series_numeric <= end)
    else:
        # Fallback to string comparison
        logger.info("[RULE ENGINE] Using string comparison for 'between' operator")
        series_str = series_val.astype(str)
        return (series_str >= str(start)) & (series_str <= str(end))


def _op_not_between(series_val, rule_val):
    """Returns True where the series value is NOT between start and end.

    Tries numeric comparison first, falls back to string comparison.

    Args:
        series_val: pandas Series to check
        rule_val: Range string in format "start-end" (e.g., "10-100")

    Returns:
        pd.Series[bool]: True where value is NOT in range [start, end]

    Example:
        >>> series = pd.Series([5, 15, 25, 105])
        >>> _op_not_between(series, "10-100")
        0     True
        1    False
        2    False
        3     True
        dtype: bool
    """
    if _parse_range(rule_val) is None:
        return pd.Series([False] * len(series_val), index=series_val.index)
    return ~_op_between(series_val, rule_val)


def _op_date_before(series_val, rule_val):
    """Returns True where the series date is before the rule date.

    Supports multiple date formats and ignores time components.

    Args:
        series_val: pandas Series with date values
        rule_val: Date string (e.g., "2024-01-30", "30/01/2024")

    Returns:
        pd.Series[bool]: True where date is before rule date

    Example:
        >>> series = pd.Series(["2024-01-15", "2024-02-15"])
        >>> _op_date_before(series, "2024-01-30")
        0     True
        1    False
        dtype: bool
    """
    return _date_compare(series_val, rule_val, lambda dates, day: dates < day)


def _op_date_after(series_val, rule_val):
    """Returns True where the series date is after the rule date.

    Supports multiple date formats and ignores time components.

    Args:
        series_val: pandas Series with date values
        rule_val: Date string (e.g., "2024-01-30", "30/01/2024")

    Returns:
        pd.Series[bool]: True where date is after rule date

    Example:
        >>> series = pd.Series(["2024-01-15", "2024-02-15"])
        >>> _op_date_after(series, "2024-01-30")
        0    False
        1     True
        dtype: bool
    """
    return _date_compare(series_val, rule_val, lambda dates, day: dates > day)


def _op_date_equals(series_val, rule_val):
    """Returns True where the series date equals the rule date.

    Supports multiple date formats and ignores time components.

    Args:
        series_val: pandas Series with date values
        rule_val: Date string (e.g., "2024-01-30", "30/01/2024")

    Returns:
        pd.Series[bool]: True where date equals rule date

    Example:
        >>> series = pd.Series(["2024-01-30", "2024-02-15"])
        >>> _op_date_equals(series, "2024-01-30")
        0     True
        1    False
        dtype: bool
    """
    return _date_compare(series_val, rule_val, lambda dates, day: dates == day)


def _op_matches_regex(series_val, rule_val):
    """Returns True where the series value matches the regex pattern.

    Args:
        series_val: pandas Series to check
        rule_val: Regex pattern string

    Returns:
        pd.Series[bool]: True where value matches pattern

    Example:
        >>> series = pd.Series(["SKU-1234", "SKU-ABCD", "OTHER"])
        >>> _op_matches_regex(series, r"^SKU-\\d{4}$")
        0     True
        1    False
        2    False
        dtype: bool
    """
    import logging
    logging.getLogger(__name__)

    compiled_pattern = _compile_regex_safe(rule_val)
    if compiled_pattern is None:
        return pd.Series([False] * len(series_val), index=series_val.index)

    # pandas warns when the pattern has capture groups (e.g. ^(01|05)); a
    # boolean contains ignores them, so the warning is noise.
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore", "This pattern is interpreted as a regular expression", UserWarning
        )
        return series_val.astype(str).str.contains(rule_val, na=False, regex=True)


def _op_does_not_match_regex(series_val, rule_val):
    """Returns True where the series value does NOT match the regex pattern.

    Args:
        series_val: pandas Series to check
        rule_val: Regex pattern string

    Returns:
        pd.Series[bool]: True where value does NOT match pattern. An invalid
        pattern matches nothing, as in `matches regex` (AUDIT-03-4).
    """
    if _compile_regex_safe(rule_val) is None:
        return pd.Series(False, index=series_val.index)
    return ~_op_matches_regex(series_val, rule_val)


class RuleEngine:
    """Applies a set of configured rules to a DataFrame of order data."""

    # The order-level fields. A numeric field names the method that works out
    # its value for one order (the Rules page's test panel shows it); the
    # yes/no fields have none. A rule evaluates them all over the whole frame
    # in _order_condition_rows.
    ORDER_LEVEL_FIELDS: ClassVar[dict[str, str | None]] = {
        "item_count": "_calculate_item_count",
        "total_quantity": "_calculate_total_quantity",
        "unique_sku_count": "_calculate_unique_sku_count",
        "max_quantity": "_calculate_max_quantity",
        "has_sku": None,
        "has_product": None,
        "order_volumetric_weight": "_calculate_order_volumetric_weight",
        "all_no_packaging": None,
        "order_min_box": None,
    }

    def _normalize_priorities(self, rules):
        """Assigns default priority to rules without priority field.

        Rules without priority get 1000, 1001, 1002... to execute last.
        This ensures backward compatibility with old configs.

        Args:
            rules (list[dict]): List of rule dictionaries

        Returns:
            list[dict]: Rules with priority field added
        """
        default_priority = 1000
        for rule in rules:
            if "priority" not in rule:
                rule["priority"] = default_priority
                default_priority += 1
        return rules

    @staticmethod
    def _normalize_steps(rule):
        """Converts old single-step format to steps array.

        Old format: conditions + actions at root level.
        New format: steps array with conditions + match + actions per step.

        Args:
            rule (dict): Rule dictionary (may be old or new format)

        Returns:
            dict: Rule with 'steps' array guaranteed
        """
        if "steps" not in rule:
            rule["steps"] = [{
                "conditions": rule.get("conditions", []),
                "match": rule.get("match", "ALL"),
                "actions": rule.get("actions", []),
            }]
        return rule

    @staticmethod
    def execution_order(rules):
        """The rules in the order apply() runs them.

        Every article rule before every order rule. Within a level, lower
        priority first; a rule with no priority runs after every prioritised
        one below 1000, in list order (1000, 1001, ...). Stable. The Rules
        page lists rules with this, so what it shows is what runs.
        """
        defaults = iter(range(1000, 1000 + len(rules)))
        keys = [
            (r.get("level") == "order", r["priority"] if "priority" in r else next(defaults))
            for r in rules
        ]
        return [r for _, r in sorted(zip(keys, rules), key=lambda kr: kr[0])]

    def __init__(self, rules_config):
        """Initializes the RuleEngine with priority-sorted rules.

        Args:
            rules_config (list[dict]): A list of dictionaries, where each
                dictionary represents a single rule. A rule consists of
                conditions and actions. Optional 'priority' field controls
                execution order (lower number = higher priority = executes first).
                A rule stored with 'enabled': False is off and never runs;
                a rule with no such key is on.
        """
        import logging
        logger = logging.getLogger(__name__)

        # Deep-copy so we never mutate the caller's config in-place
        rules_working = [
            copy.deepcopy(rule)
            for rule in rules_config or []
            if rule.get("enabled", True) is not False
        ]
        skipped = len(rules_config or []) - len(rules_working)
        if skipped:
            logger.info(f"[RULE ENGINE] Skipped {skipped} rules that are off")

        if not rules_working:
            self.rules = []
            return

        # Normalize: add default priority to rules without it
        self.rules = self._normalize_priorities(rules_working)

        # Normalize: convert old single-step format to steps array
        for rule in self.rules:
            self._normalize_steps(rule)

        # Sort by priority (lower number = higher priority = executes first)
        self.rules = self.execution_order(self.rules)

        logger.info(f"[RULE ENGINE] Loaded {len(self.rules)} rules (sorted by priority)")

    @staticmethod
    def reorder_rules(rules, from_index, to_index):
        """Reorders rules by moving rule from one position to another.

        Args:
            rules (list[dict]): List of rule dictionaries
            from_index (int): Current position (0-based)
            to_index (int): Target position (0-based)

        Returns:
            list[dict]: List with rule moved (priority values unchanged)
        """
        import logging
        logger = logging.getLogger(__name__)

        if not (0 <= from_index < len(rules) and 0 <= to_index < len(rules)):
            logger.warning(f"Invalid reorder indices: from={from_index}, to={to_index}")
            return rules

        rule = rules.pop(from_index)
        rules.insert(to_index, rule)
        logger.info(f"Reordered rules: moved position {from_index} → {to_index}")
        return rules

    def apply(self, df):
        """Applies all configured rules to the given DataFrame.

        This is the main entry point for the engine. It iterates through each
        rule, finds all rows in the DataFrame that match the rule's conditions,
        and then executes the rule's actions on those matching rows.

        Supports both article-level (row-by-row) and order-level (entire order) rules.
        Multi-step rules behave differently by level: article-level steps narrow
        the matched rows progressively, while order-level steps act as sequential
        gates on the whole order.

        The DataFrame is modified in place.

        Args:
            df (pd.DataFrame): The order data DataFrame to process.

        Returns:
            pd.DataFrame: The modified DataFrame.
        """
        import logging
        logger = logging.getLogger(__name__)

        logger.info(f"[RULE ENGINE] Starting rule application with {len(self.rules) if self.rules else 0} rules")

        # Rows some step's actions ran on, on the input's index. The rule
        # test reads it: a diff can't see a write that changed nothing.
        self.matched_rows = pd.Series(False, index=df.index)

        if not self.rules or not isinstance(self.rules, list):
            logger.warning("[RULE ENGINE] No rules to apply")
            return df

        # Create columns for actions if they don't exist
        self._prepare_df_for_actions(df)

        # Rows created by ADD_PRODUCT actions, appended after all rules run.
        all_new_rows = []

        # Separate rules by level
        article_rules = [r for r in self.rules if r.get("level", "article") == "article"]
        order_rules = [r for r in self.rules if r.get("level") == "order"]

        logger.info(f"[RULE ENGINE] {len(article_rules)} article-level rules, {len(order_rules)} order-level rules")

        # Apply article-level rules with multi-step support
        for idx, rule in enumerate(article_rules):
            rule_name = rule.get("name", f"Rule #{idx+1}")
            priority = rule.get("priority", 1000)
            steps = rule.get("steps", [])
            logger.info(f"[RULE ENGINE] Applying article rule #{idx+1}: {rule_name} (Priority: {priority}, Steps: {len(steps)})")

            # Start with all rows eligible
            current_matches = pd.Series(True, index=df.index)

            for step_idx, step in enumerate(steps):
                logger.info(f"[RULE ENGINE] Step {step_idx+1}/{len(steps)}: Conditions: {step.get('conditions', [])}")

                # Evaluate conditions only on currently matching rows
                eligible_df = df[current_matches]
                if eligible_df.empty:
                    logger.info(f"[RULE ENGINE] Step {step_idx+1}: No eligible rows, stopping")
                    break

                step_matches = self._get_matching_rows(eligible_df, step)

                # Map back to full DataFrame index
                full_step_matches = pd.Series(False, index=df.index)
                full_step_matches[step_matches[step_matches].index] = True
                current_matches = current_matches & full_step_matches

                matched_count = current_matches.sum()
                logger.info(f"[RULE ENGINE] Step {step_idx+1}: {matched_count} rows matched (narrowed)")

                # Execute step actions on narrowed rows
                if current_matches.any():
                    self.matched_rows |= current_matches
                    actions = step.get("actions", [])
                    logger.info(f"[RULE ENGINE] Step {step_idx+1}: Executing {len(actions)} actions")
                    new_rows = self._execute_actions(df, current_matches, actions, rule_name)
                    all_new_rows.extend(new_rows)
                else:
                    logger.info(f"[RULE ENGINE] Step {step_idx+1}: No matches, stopping")
                    break

        # Apply order-level rules with multi-step support. Each step is
        # evaluated once over the whole frame: a condition gives one bool per
        # row, the same for every row of an order (_order_step_rows).
        if order_rules and "Order_Number" in df.columns:
            keys = df["Order_Number"]
            codes, uniques = pd.factorize(keys)  # first appearance; NaN is -1
            first_rows = pd.Series(~pd.Series(codes).duplicated().to_numpy(), index=df.index)
            rank = {key: i for i, key in enumerate(uniques)}
            order_rows = []  # (order, rule, step, action, row): today's per-order order

            for rule_idx, rule in enumerate(order_rules):
                rule_name = rule.get("name", "Unnamed")
                steps = rule.get("steps", [])
                logger.info(
                    f"[RULE ENGINE] Applying order rule #{rule_idx+1}: "
                    f"{rule_name} "
                    f"(Priority: {rule.get('priority', 1000)}, "
                    f"Steps: {len(steps)})"
                )

                alive = pd.Series(codes >= 0, index=df.index)
                for step_idx, step in enumerate(steps):
                    # Evaluated after the step before it acted, so a later
                    # step's conditions see what an earlier step wrote.
                    matched = alive & self._order_step_rows(df, keys, step)
                    if not matched.any():
                        logger.debug(
                            f"[RULE ENGINE] Order rule '{rule_name}' step "
                            f"{step_idx+1}: no order matched, stopping"
                        )
                        break

                    self.matched_rows |= matched
                    actions = step.get("actions", [])
                    apply_to_all = [
                        a for a in actions
                        if a.get("type", "").upper() in ("ADD_TAG", "ADD_ORDER_TAG")
                    ]
                    apply_to_first = [
                        a for a in actions
                        if a.get("type", "").upper() not in ("ADD_TAG", "ADD_ORDER_TAG")
                    ]

                    if apply_to_all:
                        all_new_rows.extend(
                            self._execute_actions(df, matched, apply_to_all, rule_name)
                        )
                    # The other actions run once per order, on its first row.
                    for action_idx, action in enumerate(apply_to_first):
                        for row in self._execute_actions(
                            df, matched & first_rows, [action], rule_name
                        ):
                            order = rank.get(row.get("Order_Number"), len(rank))
                            order_rows.append(((order, rule_idx, step_idx, action_idx), row))
                    alive = matched

            # Added rows go by order (first appearance), then rule, step and
            # action, as when each order ran its rules in turn. Stable.
            order_rows.sort(key=lambda key_row: key_row[0])
            all_new_rows.extend(row for _, row in order_rows)

        # Append the rows ADD_PRODUCT actions created.
        if all_new_rows:
            new_df = pd.DataFrame(all_new_rows)
            df = pd.concat([df, new_df], ignore_index=True)
            logger.info(f"[RULE ENGINE] Added {len(all_new_rows)} new product rows to DataFrame")

        return df

    def _prepare_df_for_actions(self, df):
        """Ensures the DataFrame has the columns required for rule actions.

        Scans all rules for the tag columns their actions append to --
        'Status_Note' and 'Internal_Tags' -- and creates them if missing, so an
        action can read-modify-write them without a existence check.

        COPY_FIELD and CALCULATE targets are deliberately NOT created here: each
        handler builds its own target column so it can give it the right dtype
        and leave unmatched rows NaN, neither of which is knowable from here.

        Args:
            df (pd.DataFrame): The DataFrame to prepare.
        """
        # Determine which columns are needed by scanning actions in all rule steps
        needed_columns = set()
        for rule in self.rules:
            for step in rule.get("steps", []):
                for action in step.get("actions", []):
                    action_type = action.get("type", "").upper()
                    if action_type in ["ADD_TAG", "ADD_ORDER_TAG", "SET_MULTI_TAGS"]:
                        needed_columns.add("Status_Note")
                    elif action_type in ("ADD_INTERNAL_TAG", "REMOVE_INTERNAL_TAG"):
                        needed_columns.add("Internal_Tags")
                    # SET_STATUS uses existing Order_Fulfillment_Status column

        # Add only the necessary columns if they don't already exist
        if "Status_Note" in needed_columns and "Status_Note" not in df.columns:
            df["Status_Note"] = ""
        if "Internal_Tags" in needed_columns and "Internal_Tags" not in df.columns:
            df["Internal_Tags"] = "[]"

    def _resolve_condition(self, cond, columns, allow_order_fields):
        """Resolves a condition to (field, operator, value, error).

        A condition the engine cannot evaluate is an error, not something to
        skip. Skipping one drops it out of an ALL-match, which makes the rule
        fire on its remaining conditions and match more rows than written.

        Args:
            cond (dict): The condition, with 'field', 'operator' and 'value'.
            columns: The DataFrame columns available to this condition.
            allow_order_fields (bool): True on the order-level path, where
                ORDER_LEVEL_FIELDS names are computed rather than looked up.

        Returns:
            tuple: (field, operator, value, error). error is None when the
                condition is usable; otherwise it explains why not and the
                other three values must not be used.
        """
        field = cond.get("field")
        operator = cond.get("operator")
        value = cond.get("value")

        if not field:
            return None, None, None, "condition has no field"
        if field.startswith("---"):
            return None, None, None, f"'{field}' is a dropdown separator, not a field"
        if not operator:
            return None, None, None, f"condition on '{field}' has no operator"
        if operator not in OPERATOR_MAP:
            return None, None, None, f"unknown operator '{operator}'"

        if allow_order_fields and field in self.ORDER_LEVEL_FIELDS:
            return field, operator, value, None
        if field not in columns:
            hint = "" if allow_order_fields else " (order-level fields need level: order)"
            return None, None, None, f"field '{field}' is not a column{hint}"

        return field, operator, value, None

    def _get_matching_rows(self, df, rule):
        """Evaluates a rule's conditions and finds all matching rows.

        Combines the results of each individual condition in a rule using
        either "AND" (all conditions must match) or "OR" (any condition can
        match) logic, as specified by the rule's 'match' property.

        Args:
            df (pd.DataFrame): The DataFrame to evaluate.
            rule (dict): The rule dictionary containing the conditions.

        Returns:
            pd.Series[bool]: A boolean Series with the same index as the
                DataFrame, where `True` indicates a row matches the rule's
                conditions.
        """
        import logging
        logger = logging.getLogger(__name__)

        match_type = rule.get("match", "ALL").upper()
        conditions = rule.get("conditions", [])

        if not conditions:
            logger.warning("[RULE ENGINE] No conditions in rule")
            return pd.Series([False] * len(df), index=df.index)

        # Get a boolean Series for each individual condition
        condition_results = []
        for cond in conditions:
            field, operator, value, error = self._resolve_condition(
                cond, df.columns, allow_order_fields=False
            )
            if error:
                logger.warning(
                    f"[RULE ENGINE] Condition cannot be evaluated and is treated "
                    f"as no-match: {error}"
                )
                condition_results.append(pd.Series(False, index=df.index))
                continue

            op_func = globals()[OPERATOR_MAP[operator]]
            logger.debug(
                f"[RULE ENGINE] {field} {operator} {value!r} "
                f"(dtype {df[field].dtype})"
            )
            result = op_func(df[field], value)
            condition_results.append(result)

        if not condition_results:
            logger.warning("[RULE ENGINE] No valid conditions evaluated")
            return pd.Series([False] * len(df), index=df.index)

        # Combine the individual condition results based on the match type
        if match_type == "ALL":
            # ALL (AND logic)
            return pd.concat(condition_results, axis=1).all(axis=1)
        else:
            # ANY (OR logic)
            return pd.concat(condition_results, axis=1).any(axis=1)

    def _execute_actions(self, df, matches, actions, rule_name=None):
        """Executes actions, modifying DataFrame in-place.

        Applies the specified actions (e.g., adding a tag, setting a status)
        to the rows of the DataFrame that are marked as `True` in the `matches`
        Series.

        Args:
            df (pd.DataFrame): The DataFrame to be modified.
            matches (pd.Series[bool]): A boolean Series indicating which rows
                to apply the actions to.
            actions (list[dict]): A list of action dictionaries to execute.
            rule_name (str | None): The rule these actions belong to, recorded
                as the reason when SET_STATUS holds an order.

        Returns:
            list[dict]: List of new rows to add (from ADD_PRODUCT actions).
        """
        import logging
        logger = logging.getLogger(__name__)

        new_rows = []  # Rows to append, collected here.

        for action in actions:
            action_type = action.get("type", "").upper()
            value = action.get("value")

            # Check for deprecated action types
            deprecated_actions = ["SET_PRIORITY", "EXCLUDE_FROM_REPORT", "SET_PACKAGING_TAG", "EXCLUDE_SKU"]
            if action_type in deprecated_actions:
                logger.warning(
                    f"[RULE ENGINE] Deprecated action type '{action_type}' encountered and will be ignored. "
                    f"Recommendation: Use ADD_INTERNAL_TAG for structured metadata instead."
                )
                continue  # Skip execution

            if action_type == "ADD_TAG":
                # Per user feedback, ADD_TAG should modify Status_Note, not Tags
                current_notes = df.loc[matches, "Status_Note"].fillna("").astype(str)
                new_notes = current_notes.apply(lambda n, value=value: _append_to_note(n, value))
                df.loc[matches, "Status_Note"] = new_notes

            elif action_type == "ADD_ORDER_TAG":
                # Add tag to Status_Note (for order-level tagging)
                current_notes = df.loc[matches, "Status_Note"].fillna("").astype(str)
                new_notes = current_notes.apply(lambda n, value=value: _append_to_note(n, value))
                df.loc[matches, "Status_Note"] = new_notes

            elif action_type == "ADD_INTERNAL_TAG":
                # Internal_Tags is order-level -- expand the rule's line-level
                # match to every row of each matched order before writing
                # (see tag_manager.expand_to_order_rows).
                from shopify_tool.tag_manager import add_tag, expand_to_order_rows

                order_mask = expand_to_order_rows(df, matches)
                current_tags = df.loc[order_mask, "Internal_Tags"]
                new_tags = current_tags.apply(lambda t, value=value: add_tag(t, value))
                df.loc[order_mask, "Internal_Tags"] = new_tags

            elif action_type == "REMOVE_INTERNAL_TAG":
                # Order-level like ADD_INTERNAL_TAG -- see the note there. In an
                # order-level rule this lands in the caller's "apply to first
                # row" bucket, which is fine precisely because of this expansion.
                from shopify_tool.tag_manager import expand_to_order_rows, remove_tag

                order_mask = expand_to_order_rows(df, matches)
                current_tags = df.loc[order_mask, "Internal_Tags"]
                new_tags = current_tags.apply(lambda t, value=value: remove_tag(t, value))
                df.loc[order_mask, "Internal_Tags"] = new_tags

            elif action_type == "SET_STATUS":
                # A rule can only hold (spec 2026-09-26 D3), and an order
                # ships whole, so the hold covers every line (D5). The reason
                # makes the pane read it as the run's, not a person's (D8).
                from shopify_tool.stock_ledger import NOT_FULFILLABLE, append_blocker
                from shopify_tool.tag_manager import expand_to_order_rows

                if value != NOT_FULFILLABLE:
                    logger.warning(
                        f"[RULE ENGINE] SET_STATUS can only hold an order; "
                        f"ignoring value {value!r} in rule {rule_name!r}"
                    )
                    continue
                order_mask = (
                    expand_to_order_rows(df, matches)
                    if "Order_Number" in df.columns else matches
                )
                df.loc[order_mask, "Order_Fulfillment_Status"] = NOT_FULFILLABLE
                if "System_note" in df.columns:
                    part = "Held by rule: " + str(rule_name or "unnamed").replace("; ", ", ")
                    df.loc[order_mask, "System_note"] = df.loc[order_mask, "System_note"].apply(
                        lambda n, part=part: append_blocker(n, part)
                    )

            elif action_type == "COPY_FIELD":
                source = action.get("source")
                target = action.get("target")

                if not source or not target:
                    logger.warning(f"[RULE ENGINE] COPY_FIELD missing source or target: {action}")
                    continue

                if source not in df.columns:
                    logger.warning(f"[RULE ENGINE] Source column '{source}' not found")
                    continue

                if target not in df.columns:
                    # Build the column from the source so it takes the source's
                    # dtype. Seeding "" first made it str dtype on pandas 3, and
                    # writing a numeric source into that raises TypeError.
                    # Unmatched rows are NaN -- the rule never wrote them.
                    df[target] = df[source].where(matches)
                else:
                    df.loc[matches, target] = df.loc[matches, source]
                logger.info(f"[RULE ENGINE] Copied {source} -> {target} for {matches.sum()} rows")

            elif action_type == "SET_MULTI_TAGS":
                tags_value = action.get("tags") or action.get("value")

                if not tags_value:
                    logger.warning("[RULE ENGINE] SET_MULTI_TAGS missing tags/value")
                    continue

                # Parse: підтримка list або comma-separated string
                if isinstance(tags_value, list):
                    tags_list = tags_value
                elif isinstance(tags_value, str):
                    tags_list = [t.strip() for t in tags_value.split(",") if t.strip()]
                else:
                    logger.warning(f"[RULE ENGINE] SET_MULTI_TAGS invalid format: {type(tags_value)}")
                    continue

                if not tags_list:
                    continue

                # Додати теги без дублікатів
                current_notes = df.loc[matches, "Status_Note"].fillna("").astype(str)

                def add_multiple_tags(note, tags_list=tags_list):
                    existing = [t.strip() for t in note.split(", ") if t.strip()]
                    for tag in tags_list:
                        if tag not in existing:
                            existing.append(tag)
                    return ", ".join(existing)

                df.loc[matches, "Status_Note"] = current_notes.apply(add_multiple_tags)
                logger.info(f"[RULE ENGINE] Added {len(tags_list)} tags to {matches.sum()} rows")

            elif action_type == "ALERT_NOTIFICATION":
                message = action.get("message")
                severity = action.get("severity", "info").lower()

                if not message:
                    logger.warning("[RULE ENGINE] ALERT_NOTIFICATION missing message")
                    continue

                # Валідація severity
                if severity not in ["info", "warning", "error"]:
                    logger.warning(f"[RULE ENGINE] Invalid severity '{severity}', using 'info'")
                    severity = "info"

                matched_count = matches.sum()
                full_message = f"[RULE ALERT] {message} (matched {matched_count} rows)"

                if severity == "error":
                    logger.error(full_message)
                elif severity == "warning":
                    logger.warning(full_message)
                else:
                    logger.info(full_message)

                # Додатково логувати Order_Number якщо <= 10 співпадінь
                if 0 < matched_count <= 10 and "Order_Number" in df.columns:
                    orders = df.loc[matches, "Order_Number"].unique()
                    logger.info(f"[RULE ALERT] Orders: {', '.join(str(o) for o in orders)}")

            elif action_type == "CALCULATE":
                operation = action.get("operation")
                field1 = action.get("field1")
                field2 = action.get("field2")
                target = action.get("target")

                # Валідація параметрів
                if not all([operation, field1, field2, target]):
                    logger.warning(f"[RULE ENGINE] CALCULATE missing parameters: {action}")
                    continue

                if operation not in ["add", "subtract", "multiply", "divide"]:
                    logger.warning(f"[RULE ENGINE] CALCULATE invalid operation '{operation}'")
                    continue

                if field1 not in df.columns or field2 not in df.columns:
                    logger.warning("[RULE ENGINE] CALCULATE fields not found in DataFrame")
                    continue

                # Створити target column якщо не існує.
                # NaN, not 0.0 -- a row the rule never matched has no result,
                # and a literal 0.0 there is indistinguishable from a real one.
                # float("nan") gives a float64 column without importing numpy
                # (numpy is imported locally in the divide branch below).
                if target not in df.columns:
                    df[target] = float("nan")

                # Конвертувати в числа
                val1 = pd.to_numeric(df.loc[matches, field1], errors='coerce')
                val2 = pd.to_numeric(df.loc[matches, field2], errors='coerce')

                # Виконати операцію
                if operation == "add":
                    result = val1 + val2
                elif operation == "subtract":
                    result = val1 - val2
                elif operation == "multiply":
                    result = val1 * val2
                elif operation == "divide":
                    # Division by zero -> NaN
                    import numpy as np
                    result = val1 / val2.replace(0, np.nan)

                df.loc[matches, target] = result
                valid = result.notna().sum()
                logger.info(f"[RULE ENGINE] CALCULATE {operation}: {field1}, {field2} -> {target} ({valid}/{matches.sum()} valid)")

            elif action_type == "ADD_PRODUCT":
                sku = action.get("sku")
                quantity = action.get("quantity", 1)

                if not sku:
                    logger.warning("[RULE ENGINE] ADD_PRODUCT missing SKU")
                    continue

                try:
                    quantity = int(quantity)
                except (ValueError, TypeError):
                    logger.warning(f"[RULE ENGINE] ADD_PRODUCT invalid quantity: {quantity}")
                    continue

                if quantity <= 0:
                    logger.warning("[RULE ENGINE] ADD_PRODUCT quantity must be positive")
                    continue

                # Знайти цей SKU в DataFrame для отримання product info (з stock файлу)
                existing_product = df[df["SKU"] == sku]
                if not existing_product.empty:
                    # SKU знайдено - взяти дані з існуючого рядка
                    product_info = existing_product.iloc[0]
                    product_name = product_info.get("Product_Name", sku)
                    warehouse_name = product_info.get("Warehouse_Name", sku)
                    stock = product_info.get("Stock", 0)
                    final_stock = product_info.get("Final_Stock", 0)
                    logger.info(f"[RULE ENGINE] ADD_PRODUCT: Found SKU '{sku}' in stock data (Warehouse: {warehouse_name})")
                else:
                    # SKU не знайдено - використати defaults
                    product_name = action.get("product_name", f"Bonus: {sku}")
                    warehouse_name = sku
                    stock = 0
                    final_stock = 0
                    logger.warning(f"[RULE ENGINE] ADD_PRODUCT: SKU '{sku}' not found in stock data, using defaults")

                # Для кожного співпадаючого рядка створити новий продукт
                for idx in df[matches].index:
                    base_row = df.loc[idx].to_dict()

                    new_row = base_row.copy()
                    # Перезаписати product-specific поля з правильними даними
                    new_row["SKU"] = sku
                    new_row["Quantity"] = quantity
                    new_row["Product_Name"] = product_name
                    new_row["Warehouse_Name"] = warehouse_name
                    if "Stock" in new_row:
                        new_row["Stock"] = stock
                    if "Final_Stock" in new_row:
                        new_row["Final_Stock"] = final_stock

                    # Очистити поля які не треба копіювати
                    if "Status_Note" in new_row:
                        new_row["Status_Note"] = ""

                    # Позначити як додано правилом
                    if "Internal_Tags" in new_row:
                        from shopify_tool.tag_manager import add_tag
                        new_row["Internal_Tags"] = add_tag("[]", "rule_added_product")

                    new_rows.append(new_row)

                logger.info(f"[RULE ENGINE] ADD_PRODUCT: Created {len(df[matches])} instances of '{sku}' (Warehouse: {warehouse_name})")

        return new_rows

    def _order_step_rows(self, df: pd.DataFrame, keys: pd.Series, step: dict) -> pd.Series:
        """One bool per row: the step's conditions, combined by its ALL/ANY.

        Every row of an order gets the same answer, and a row whose order
        number is NaN never matches. A condition the engine cannot evaluate
        is no match, with one warning for the step.
        """
        import logging
        logger = logging.getLogger(__name__)

        conditions = step.get("conditions", [])
        if not conditions:
            return pd.Series(False, index=df.index)

        results, errors = [], []
        for condition in conditions:
            field, operator, value, error = self._resolve_condition(
                condition, df.columns, allow_order_fields=True
            )
            if error:
                errors.append(error)
                results.append(np.zeros(len(df), dtype=bool))
                continue
            results.append(self._order_condition_rows(
                df, keys, {"field": field, "operator": operator, "value": value}
            ).to_numpy(dtype=bool))
        if errors:
            logger.warning(
                f"[RULE ENGINE] Order condition cannot be evaluated and is "
                f"treated as no-match: {'; '.join(errors)}"
            )

        if str(step.get("match", "ALL")).upper() == "ALL":
            combined = np.logical_and.reduce(results)
        else:
            combined = np.logical_or.reduce(results)
        return pd.Series(combined & keys.notna().to_numpy(), index=df.index)

    def _order_condition_rows(self, df: pd.DataFrame, keys: pd.Series, condition: dict) -> pd.Series:
        """One bool per row for one usable condition on an order rule.

        The answer is worked out per order and given to each of its rows;
        rows whose order number is NaN get False.
        - Numeric order fields (item_count, total_quantity, unique_sku_count,
          max_quantity) are aggregated per order, then compared.
        - order_volumetric_weight, all_no_packaging and order_min_box read
          the order's first row, NaN included.
        - A line field, has_sku and has_product: a positive operator needs
          one matching line, a negative one needs every line to satisfy it.
        """
        field = condition["field"]
        operator = condition["operator"]
        value = condition.get("value")
        n = len(df)
        codes, _ = pd.factorize(keys)
        alive = codes >= 0
        n_orders = int(codes.max()) + 1 if n else 0
        out = np.zeros(n, dtype=bool)
        if n_orders == 0:
            return pd.Series(out, index=df.index)

        def per_order(answers) -> pd.Series:
            out[alive] = np.asarray(answers, dtype=bool)[codes[alive]]
            return pd.Series(out, index=df.index)

        def first_values(column) -> pd.Series:
            uniq, first = np.unique(codes, return_index=True)
            return pd.Series(df[column].to_numpy()[first[uniq >= 0]])

        def compare(values: pd.Series, rule_value):
            result = globals()[OPERATOR_MAP[operator]](values, rule_value)
            return result.fillna(False).to_numpy(dtype=bool)

        grouped = None
        if field in ("total_quantity", "max_quantity", "unique_sku_count"):
            column = "SKU" if field == "unique_sku_count" else "Quantity"
            if column not in df.columns:
                return per_order(compare(pd.Series(np.zeros(n_orders, dtype=np.int64)), value))
            grouped = pd.Series(df[column].to_numpy()).groupby(codes)

        if field == "item_count":
            sizes = np.bincount(codes[alive], minlength=n_orders)
            return per_order(compare(pd.Series(sizes.astype(np.int64)), value))
        if field == "total_quantity":
            return per_order(compare(grouped.sum().reindex(range(n_orders)), value))
        if field == "max_quantity":
            return per_order(compare(grouped.max().reindex(range(n_orders)), value))
        if field == "unique_sku_count":
            # dropna=False: a line without a SKU counts as one more SKU
            counts = grouped.nunique(dropna=False).reindex(range(n_orders))
            return per_order(compare(counts, value))
        if field == "order_volumetric_weight":
            if "Order_Volumetric_Weight" not in df.columns:
                return per_order(compare(pd.Series(np.zeros(n_orders)), value))
            return per_order(compare(first_values("Order_Volumetric_Weight").astype(float), value))
        if field == "all_no_packaging":
            if "All_No_Packaging" not in df.columns:
                return pd.Series(out, index=df.index)
            texts = first_values("All_No_Packaging").map(
                lambda raw: "true" if (
                    raw if isinstance(raw, bool) else str(raw).lower() in ("true", "1", "yes")
                ) else "false"
            ).astype(object)
            return per_order(compare(texts, str(value).lower().strip()))
        if field == "order_min_box":
            if "Order_Min_Box" not in df.columns:
                return pd.Series(out, index=df.index)
            return per_order(compare(first_values("Order_Min_Box").map(str).astype(object), value))

        # A line field: the operator runs once over the column.
        if field in ("has_sku", "has_product"):
            column = "SKU" if field == "has_sku" else "Product_Name"
            if column not in df.columns or not value:
                return pd.Series(out, index=df.index)
        else:
            column = field
        if operator not in OPERATOR_MAP:
            operator = "equals"
        line_result = globals()[OPERATOR_MAP[operator]](df[column], value)
        lines = codes[alive]
        sizes = np.bincount(lines, minlength=n_orders)
        if operator in NEGATIVE_OPERATORS:
            hits = line_result.fillna(True).to_numpy(dtype=bool)[alive]
            return per_order(np.bincount(lines, weights=hits, minlength=n_orders) == sizes)
        hits = line_result.fillna(False).to_numpy(dtype=bool)[alive]
        return per_order(np.bincount(lines, weights=hits, minlength=n_orders) > 0)

    def _calculate_item_count(self, order_df, sku_value=None):
        """Count unique items (rows) in order."""
        return len(order_df)

    def _calculate_total_quantity(self, order_df, sku_value=None):
        """Sum all quantities in order."""
        if "Quantity" in order_df.columns:
            return order_df["Quantity"].sum()
        return 0

    def _calculate_unique_sku_count(self, order_df, sku_value=None):
        """Count unique SKUs in order."""
        if "SKU" in order_df.columns:
            return len(order_df["SKU"].unique())
        return 0

    def _calculate_max_quantity(self, order_df, sku_value=None):
        """Max quantity of any single line item in order."""
        if "Quantity" in order_df.columns:
            return order_df["Quantity"].max()
        return 0

    def _calculate_order_volumetric_weight(self, order_df, sku_value=None):
        """Return pre-computed order volumetric weight from enriched DataFrame column.

        Requires enrich_dataframe_with_weights() to have been called before apply().
        Returns 0.0 if the column is not present.
        """
        if "Order_Volumetric_Weight" in order_df.columns:
            return float(order_df["Order_Volumetric_Weight"].iloc[0])
        return 0.0
