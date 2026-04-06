import pandas as pd
import re
from functools import lru_cache
from typing import Optional


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


def _op_contains(series_val, rule_val):
    """Returns True where the series string contains the rule string (case-insensitive)."""
    if pd.api.types.is_numeric_dtype(series_val):
        return pd.Series(False, index=series_val.index)
    return series_val.str.contains(rule_val, case=False, na=False)


def _op_not_contains(series_val, rule_val):
    """Returns True where the series string does not contain the rule string (case-insensitive)."""
    if pd.api.types.is_numeric_dtype(series_val):
        return pd.Series(True, index=series_val.index)
    return ~series_val.str.contains(rule_val, case=False, na=False)


def _op_greater_than(series_val, rule_val):
    """Returns True where the series value is greater than the numeric rule value."""
    return pd.to_numeric(series_val, errors="coerce") > float(rule_val)


def _op_less_than(series_val, rule_val):
    """Returns True where the series value is less than the numeric rule value."""
    return pd.to_numeric(series_val, errors="coerce") < float(rule_val)


def _op_greater_than_or_equal(series_val, rule_val):
    """Returns True where the series value is >= numeric rule value."""
    return pd.to_numeric(series_val, errors="coerce") >= float(rule_val)


def _op_less_than_or_equal(series_val, rule_val):
    """Returns True where the series value is <= numeric rule value."""
    return pd.to_numeric(series_val, errors="coerce") <= float(rule_val)


def _op_starts_with(series_val, rule_val):
    """Returns True where the series string starts with the rule string."""
    if pd.api.types.is_numeric_dtype(series_val):
        return pd.Series(False, index=series_val.index)
    return series_val.str.startswith(rule_val, na=False)


def _op_ends_with(series_val, rule_val):
    """Returns True where the series string ends with the rule string."""
    if pd.api.types.is_numeric_dtype(series_val):
        return pd.Series(False, index=series_val.index)
    return series_val.str.endswith(rule_val, na=False)


def _op_is_empty(series_val, rule_val):
    """Returns True where the series value is null or an empty string."""
    return series_val.isnull() | (series_val == "")


def _op_is_not_empty(series_val, rule_val):
    """Returns True where the series value is not null and not an empty string."""
    return series_val.notna() & (series_val != "")


# --- Helper Functions for New Operators ---


def _parse_date_safe(date_str: str) -> Optional[pd.Timestamp]:
    """Safely parse date string with multiple format support.

    Tries 3 common date formats in sequence:
    1. YYYY-MM-DD (ISO format)
    2. DD/MM/YYYY (European format)
    3. DD.MM.YYYY (European format with dots)

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

    # Try multiple formats
    formats = ["%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y"]

    for fmt in formats:
        try:
            return pd.to_datetime(date_str, format=fmt)
        except (ValueError, TypeError):
            continue

    logger.warning(f"[RULE ENGINE] Invalid rule date format: '{date_str}'")
    return None


@lru_cache(maxsize=128)
def _compile_regex_safe(pattern: str) -> Optional[re.Pattern]:
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


def _parse_range(range_str: str) -> Optional[tuple[float, float]]:
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

    # Split on dash
    parts = range_str.split("-")
    if len(parts) != 2:
        logger.warning(f"[RULE ENGINE] Invalid range format: '{range_str}' (expected 'start-end')")
        return None

    try:
        start = float(parts[0].strip())
        end = float(parts[1].strip())

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
        logger.info(f"[RULE ENGINE] Using string comparison for 'between' operator")
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
    import logging
    logger = logging.getLogger(__name__)

    rule_date = _parse_date_safe(rule_val)
    if rule_date is None:
        return pd.Series([False] * len(series_val), index=series_val.index, dtype=bool)

    # Normalize to ignore time
    rule_date = rule_date.normalize()

    # Parse series dates with multiple format attempts
    series_dates = pd.Series([None] * len(series_val), index=series_val.index)
    for idx, val in series_val.items():
        parsed = _parse_date_safe(val)
        if parsed is not None:
            series_dates[idx] = parsed

    # Create boolean result
    result = pd.Series([False] * len(series_val), index=series_val.index, dtype=bool)
    valid_mask = series_dates.notna()

    if valid_mask.any():
        valid_dates = pd.to_datetime(series_dates[valid_mask])
        result.loc[valid_mask] = valid_dates.dt.normalize() < rule_date

    return result


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
    import logging
    logger = logging.getLogger(__name__)

    rule_date = _parse_date_safe(rule_val)
    if rule_date is None:
        return pd.Series([False] * len(series_val), index=series_val.index, dtype=bool)

    # Normalize to ignore time
    rule_date = rule_date.normalize()

    # Parse series dates with multiple format attempts
    series_dates = pd.Series([None] * len(series_val), index=series_val.index)
    for idx, val in series_val.items():
        parsed = _parse_date_safe(val)
        if parsed is not None:
            series_dates[idx] = parsed

    # Create boolean result
    result = pd.Series([False] * len(series_val), index=series_val.index, dtype=bool)
    valid_mask = series_dates.notna()

    if valid_mask.any():
        valid_dates = pd.to_datetime(series_dates[valid_mask])
        result.loc[valid_mask] = valid_dates.dt.normalize() > rule_date

    return result


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
    import logging
    logger = logging.getLogger(__name__)

    rule_date = _parse_date_safe(rule_val)
    if rule_date is None:
        return pd.Series([False] * len(series_val), index=series_val.index, dtype=bool)

    # Normalize to ignore time
    rule_date = rule_date.normalize()

    # Parse series dates with multiple format attempts
    series_dates = pd.Series([None] * len(series_val), index=series_val.index)
    for idx, val in series_val.items():
        parsed = _parse_date_safe(val)
        if parsed is not None:
            series_dates[idx] = parsed

    # Create boolean result
    result = pd.Series([False] * len(series_val), index=series_val.index, dtype=bool)
    valid_mask = series_dates.notna()

    if valid_mask.any():
        valid_dates = pd.to_datetime(series_dates[valid_mask])
        result.loc[valid_mask] = valid_dates.dt.normalize() == rule_date

    return result


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
    logger = logging.getLogger(__name__)

    compiled_pattern = _compile_regex_safe(rule_val)
    if compiled_pattern is None:
        return pd.Series([False] * len(series_val), index=series_val.index)

    # Use pandas vectorized string contains with regex
    return series_val.astype(str).str.contains(rule_val, na=False, regex=True)


def _op_does_not_match_regex(series_val, rule_val):
    """Returns True where the series value does NOT match the regex pattern.

    Args:
        series_val: pandas Series to check
        rule_val: Regex pattern string

    Returns:
        pd.Series[bool]: True where value does NOT match pattern
    """
    return ~_op_matches_regex(series_val, rule_val)


class RuleEngine:
    """Applies a set of configured rules to a DataFrame of order data."""

    # Define order-level fields and their calculation methods
    ORDER_LEVEL_FIELDS = {
        "item_count": "_calculate_item_count",
        "total_quantity": "_calculate_total_quantity",
        "unique_sku_count": "_calculate_unique_sku_count",
        "max_quantity": "_calculate_max_quantity",
        "has_sku": "_check_has_sku",
        "has_product": "_check_has_product",
        "order_volumetric_weight": "_calculate_order_volumetric_weight",
        "all_no_packaging": "_calculate_all_no_packaging",
        "order_min_box": "_get_order_min_box",
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

    def __init__(self, rules_config):
        """Initializes the RuleEngine with priority-sorted rules.

        Args:
            rules_config (list[dict]): A list of dictionaries, where each
                dictionary represents a single rule. A rule consists of
                conditions and actions. Optional 'priority' field controls
                execution order (lower number = higher priority = executes first).
        """
        import logging
        logger = logging.getLogger(__name__)

        if not rules_config:
            self.rules = []
            return

        # Normalize: add default priority to rules without it
        self.rules = self._normalize_priorities(rules_config)

        # Normalize: convert old single-step format to steps array
        for rule in self.rules:
            self._normalize_steps(rule)

        # Sort by priority (lower number = higher priority = executes first)
        self.rules = sorted(self.rules, key=lambda r: r.get("priority", 1000))

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

        The DataFrame is modified in place.

        Args:
            df (pd.DataFrame): The order data DataFrame to process.

        Returns:
            pd.DataFrame: The modified DataFrame.
        """
        import logging
        logger = logging.getLogger(__name__)

        logger.info(f"[RULE ENGINE] Starting rule application with {len(self.rules) if self.rules else 0} rules")

        if not self.rules or not isinstance(self.rules, list):
            logger.warning("[RULE ENGINE] No rules to apply")
            return df

        # Create columns for actions if they don't exist
        self._prepare_df_for_actions(df)

        # Збирати нові рядки з ADD_PRODUCT actions
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
                    actions = step.get("actions", [])
                    logger.info(f"[RULE ENGINE] Step {step_idx+1}: Executing {len(actions)} actions")
                    new_rows = self._execute_actions(df, current_matches, actions)
                    all_new_rows.extend(new_rows)
                else:
                    logger.info(f"[RULE ENGINE] Step {step_idx+1}: No matches, stopping")
                    break

        # Apply order-level rules with multi-step support
        if order_rules and "Order_Number" in df.columns:
            for order_number in df["Order_Number"].unique():
                order_mask = df["Order_Number"] == order_number
                order_df = df[order_mask]

                for rule in order_rules:
                    rule_name = rule.get("name", "Unnamed")
                    priority = rule.get("priority", 1000)
                    steps = rule.get("steps", [])
                    logger.info(f"[RULE ENGINE] Applying order rule: {rule_name} (Priority: {priority}, Steps: {len(steps)})")

                    # Track which rows in order are still eligible (for narrowing)
                    order_eligible_mask = order_mask.copy()

                    for step_idx, step in enumerate(steps):
                        # Evaluate conditions on eligible order rows
                        eligible_df = df[order_eligible_mask]
                        if eligible_df.empty:
                            break

                        matches = self._evaluate_order_conditions(
                            eligible_df,
                            step.get("conditions", []),
                            step.get("match", "ALL")
                        )

                        if not matches:
                            logger.info(f"[RULE ENGINE] Order {order_number} step {step_idx+1}: No match, stopping")
                            break

                        # Separate actions by scope
                        actions = step.get("actions", [])
                        apply_to_all_actions = []
                        apply_to_first_actions = []

                        for action in actions:
                            action_type = action.get("type", "").upper()
                            if action_type == "ADD_TAG":
                                apply_to_all_actions.append(action)
                            else:
                                apply_to_first_actions.append(action)

                        # Apply to all rows of order
                        if apply_to_all_actions:
                            new_rows = self._execute_actions(df, order_eligible_mask, apply_to_all_actions)
                            all_new_rows.extend(new_rows)

                        # Apply to first row only
                        if apply_to_first_actions:
                            first_row_index = eligible_df.index[0]
                            first_row_mask = pd.Series(False, index=df.index)
                            first_row_mask[first_row_index] = True
                            new_rows = self._execute_actions(df, first_row_mask, apply_to_first_actions)
                            all_new_rows.extend(new_rows)

        # Додати всі нові рядки з ADD_PRODUCT actions
        if all_new_rows:
            new_df = pd.DataFrame(all_new_rows)
            df = pd.concat([df, new_df], ignore_index=True)
            logger.info(f"[RULE ENGINE] Added {len(all_new_rows)} new product rows to DataFrame")

        return df

    def _prepare_df_for_actions(self, df):
        """Ensures the DataFrame has the columns required for rule actions.

        Scans all rules to find out which columns will be modified or created
        by the actions (e.g., 'Status_Note', 'Internal_Tags'). If these columns
        do not already exist in the DataFrame, they are created and initialized
        with a default value. This prevents errors when an action tries to
        modify a non-existent column.

        Args:
            df (pd.DataFrame): The DataFrame to prepare.
        """
        # Determine which columns are needed by scanning actions in all rule steps
        needed_columns = set()
        for rule in self.rules:
            for step in rule.get("steps", []):
                for action in step.get("actions", []):
                    action_type = action.get("type", "").upper()
                    if action_type in ["ADD_TAG", "ADD_ORDER_TAG"]:
                        needed_columns.add("Status_Note")
                    elif action_type == "ADD_INTERNAL_TAG":
                        needed_columns.add("Internal_Tags")
                    elif action_type == "COPY_FIELD":
                        target = action.get("target")
                        if target:
                            needed_columns.add(target)
                    elif action_type == "CALCULATE":
                        target = action.get("target")
                        if target:
                            needed_columns.add(target)
                    # SET_STATUS uses existing Order_Fulfillment_Status column

        # Add only the necessary columns if they don't already exist
        if "Status_Note" in needed_columns and "Status_Note" not in df.columns:
            df["Status_Note"] = ""
        if "Internal_Tags" in needed_columns and "Internal_Tags" not in df.columns:
            df["Internal_Tags"] = "[]"

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
            field = cond.get("field")
            operator = cond.get("operator")
            value = cond.get("value")

            # Skip separator fields (from UI)
            if field and field.startswith("---"):
                logger.info(f"[RULE ENGINE] Skipping separator field: {field}")
                continue

            # Check conditions
            if not field:
                logger.warning(f"[RULE ENGINE] Condition missing field: {cond}")
                continue
            if not operator:
                logger.warning(f"[RULE ENGINE] Condition missing operator: {cond}")
                continue
            if field not in df.columns:
                logger.warning(f"[RULE ENGINE] Field '{field}' not in DataFrame columns: {list(df.columns)}")
                continue
            if operator not in OPERATOR_MAP:
                logger.warning(f"[RULE ENGINE] Operator '{operator}' not in OPERATOR_MAP: {list(OPERATOR_MAP.keys())}")
                continue

            op_func_name = OPERATOR_MAP[operator]
            op_func = globals()[op_func_name]

            logger.info(f"[RULE ENGINE] Evaluating condition: {field} {operator} {value}")

            # Log data types and sample values
            logger.info(f"[RULE ENGINE] Field '{field}' dtype: {df[field].dtype}")
            logger.info(f"[RULE ENGINE] Rule value type: {type(value).__name__}, value: {repr(value)}")
            unique_vals = df[field].dropna().unique()[:5]
            logger.info(f"[RULE ENGINE] Sample values in '{field}': {list(unique_vals)}")

            result = op_func(df[field], value)
            matches_count = result.sum()
            logger.info(f"[RULE ENGINE] Condition matched {matches_count} rows")

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

    def _execute_actions(self, df, matches, actions):
        """Executes actions, modifying DataFrame in-place.

        Applies the specified actions (e.g., adding a tag, setting a status)
        to the rows of the DataFrame that are marked as `True` in the `matches`
        Series.

        Args:
            df (pd.DataFrame): The DataFrame to be modified.
            matches (pd.Series[bool]): A boolean Series indicating which rows
                to apply the actions to.
            actions (list[dict]): A list of action dictionaries to execute.

        Returns:
            list[dict]: List of new rows to add (from ADD_PRODUCT actions).
        """
        import logging
        logger = logging.getLogger(__name__)

        new_rows = []  # Збирати нові рядки тут

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
                new_notes = current_notes.apply(lambda n: _append_to_note(n, value))
                df.loc[matches, "Status_Note"] = new_notes

            elif action_type == "ADD_ORDER_TAG":
                # Add tag to Status_Note (for order-level tagging)
                current_notes = df.loc[matches, "Status_Note"].fillna("").astype(str)
                new_notes = current_notes.apply(lambda n: _append_to_note(n, value))
                df.loc[matches, "Status_Note"] = new_notes

            elif action_type == "ADD_INTERNAL_TAG":
                # Add tag to Internal_Tags column using tag_manager
                from shopify_tool.tag_manager import add_tag

                current_tags = df.loc[matches, "Internal_Tags"]
                new_tags = current_tags.apply(lambda t: add_tag(t, value))
                df.loc[matches, "Internal_Tags"] = new_tags

            elif action_type == "SET_STATUS":
                df.loc[matches, "Order_Fulfillment_Status"] = value

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
                    df[target] = ""

                df.loc[matches, target] = df.loc[matches, source]
                logger.info(f"[RULE ENGINE] Copied {source} -> {target} for {matches.sum()} rows")

            elif action_type == "SET_MULTI_TAGS":
                tags_value = action.get("tags") or action.get("value")

                if not tags_value:
                    logger.warning(f"[RULE ENGINE] SET_MULTI_TAGS missing tags/value")
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

                def add_multiple_tags(note):
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
                    logger.warning(f"[RULE ENGINE] ALERT_NOTIFICATION missing message")
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
                    logger.warning(f"[RULE ENGINE] CALCULATE fields not found in DataFrame")
                    continue

                # Створити target column якщо не існує
                if target not in df.columns:
                    df[target] = 0.0

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
                    logger.warning(f"[RULE ENGINE] ADD_PRODUCT missing SKU")
                    continue

                try:
                    quantity = int(quantity)
                except (ValueError, TypeError):
                    logger.warning(f"[RULE ENGINE] ADD_PRODUCT invalid quantity: {quantity}")
                    continue

                if quantity <= 0:
                    logger.warning(f"[RULE ENGINE] ADD_PRODUCT quantity must be positive")
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

    def _evaluate_order_conditions(self, order_df, conditions, match_type):
        """
        Evaluate conditions on order-level (entire order group).

        Args:
            order_df: DataFrame rows for single order
            conditions: List of condition dicts
            match_type: "ALL" or "ANY"

        Returns:
            bool: True if conditions met
        """
        results = []

        for condition in conditions:
            field = condition.get("field")
            operator = condition.get("operator")
            value = condition.get("value")

            if not all([field, operator]):
                continue

            # Skip separator fields (from UI)
            if field and field.startswith("---"):
                continue

            # Check if this is an order-level field
            if field in self.ORDER_LEVEL_FIELDS:
                # Calculate order-level metric
                calc_method_name = self.ORDER_LEVEL_FIELDS[field]
                calc_method = getattr(self, calc_method_name)

                # Methods that apply operator internally and return bool directly
                if field in ("has_sku", "has_product", "all_no_packaging", "order_min_box"):
                    field_value = calc_method(order_df, value, operator)
                    result = field_value
                else:
                    # For numeric fields: wrap in Series, use global operator
                    field_value = calc_method(order_df, None)
                    if operator not in OPERATOR_MAP:
                        result = False
                    else:
                        scalar_series = pd.Series([field_value])
                        op_func = globals()[OPERATOR_MAP[operator]]
                        result = bool(op_func(scalar_series, value).iloc[0])

            else:
                # Regular article-level field - check if ANY row matches
                if field not in order_df.columns or operator not in OPERATOR_MAP:
                    result = False
                else:
                    op_func = globals()[OPERATOR_MAP[operator]]
                    series_result = op_func(order_df[field], value)
                    result = series_result.any()  # At least one row matches

            results.append(result)

        if not results:
            return False

        # Combine results based on match type
        if match_type == "ALL":
            return all(results)
        else:  # ANY
            return any(results)

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

    def _calculate_all_no_packaging(self, order_df, rule_value, operator="equals"):
        """Evaluate all_no_packaging against rule value + operator.

        Reads the pre-computed All_No_Packaging column and applies the operator
        so rules can test both True and False explicitly.
        E.g. {"field": "all_no_packaging", "operator": "equals", "value": "true"}
             {"field": "all_no_packaging", "operator": "equals", "value": "false"}

        Requires enrich_dataframe_with_weights() to have been called before apply().
        Returns False if the column is not present.
        """
        if "All_No_Packaging" not in order_df.columns:
            return False
        raw = order_df["All_No_Packaging"].iloc[0]
        bool_val = raw if isinstance(raw, bool) else str(raw).lower() in ("true", "1", "yes")
        # Represent as string for operator comparison ("true"/"false")
        col_str = "true" if bool_val else "false"
        if operator not in OPERATOR_MAP:
            return False
        op_func = globals()[OPERATOR_MAP[operator]]
        result_series = op_func(pd.Series([col_str]), str(rule_value).lower().strip())
        return bool(result_series.iloc[0])

    def _get_order_min_box(self, order_df, rule_value, operator="equals"):
        """Return bool: True if Order_Min_Box matches the condition.

        Reads the pre-computed Order_Min_Box column (populated by
        enrich_dataframe_with_weights). Applies operator internally
        like has_sku/has_product since it returns a bool directly.
        """
        if "Order_Min_Box" not in order_df.columns:
            return False
        box_value = str(order_df["Order_Min_Box"].iloc[0])
        if operator not in OPERATOR_MAP:
            return False
        op_func = globals()[OPERATOR_MAP[operator]]
        result_series = op_func(pd.Series([box_value]), rule_value)
        return bool(result_series.iloc[0])

    def _check_has_sku(self, order_df, sku_value, operator="equals"):
        """Check if order contains SKU matching the condition.

        Uses all operators from the global OPERATOR_MAP.

        Args:
            order_df: DataFrame rows for single order
            sku_value: Value to match against
            operator: String operator (any from OPERATOR_MAP)

        Returns:
            bool: True if condition matches
                  - For positive operators: True if ANY SKU matches
                  - For negative operators: True if ALL SKUs match (i.e., NONE have the value)
        """
        if "SKU" not in order_df.columns or not sku_value:
            return False

        sku_series = order_df["SKU"]

        if operator not in OPERATOR_MAP:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"[RULE ENGINE] Unknown operator '{operator}' for has_sku, using 'equals'")
            operator = "equals"

        op_func = globals()[OPERATOR_MAP[operator]]
        result_series = op_func(sku_series, sku_value)

        # For negative operators, ALL SKUs must match (i.e., NONE have the unwanted value)
        # For positive operators, ANY SKU can match
        negative_operators = [
            "does not equal", "does not contain", "not in list",
            "not between", "does not match regex",
        ]
        if operator in negative_operators:
            return result_series.all()
        else:
            return result_series.any()

    def _check_has_product(self, order_df, product_value, operator="equals"):
        """Check if order contains Product_Name matching the condition.

        Same logic as _check_has_sku but operates on Product_Name column.

        Args:
            order_df: DataFrame rows for single order
            product_value: Value to match against
            operator: String operator (any from OPERATOR_MAP)

        Returns:
            bool: True if condition matches
        """
        if "Product_Name" not in order_df.columns or not product_value:
            return False

        product_series = order_df["Product_Name"]

        if operator not in OPERATOR_MAP:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"[RULE ENGINE] Unknown operator '{operator}' for has_product, using 'equals'")
            operator = "equals"

        op_func = globals()[OPERATOR_MAP[operator]]
        result_series = op_func(product_series, product_value)

        negative_operators = [
            "does not equal", "does not contain", "not in list",
            "not between", "does not match regex",
        ]
        if operator in negative_operators:
            return result_series.all()
        else:
            return result_series.any()
