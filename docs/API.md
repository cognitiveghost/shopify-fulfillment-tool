# Shopify Fulfillment Tool - API Reference

## Table of Contents

- [Backend API (shopify_tool)](#backend-api-shopify_tool)
  - [core](#module-core)
  - [analysis](#module-analysis)
  - [rules](#module-rules)
  - [packing_lists](#module-packing_lists)
  - [stock_export](#module-stock_export)
  - [utils](#module-utils)
  - [logger_config](#module-logger_config)
- [Frontend API (gui)](#frontend-api-gui)
  - [main_window_pyside](#module-main_window_pyside)
  - [settings_window_pyside](#module-settings_window_pyside)
  - [actions_handler](#module-actions_handler)
  - [ui_manager](#module-ui_manager)
  - [file_handler](#module-file_handler)
  - [report_builder_window_pyside](#module-report_builder_window_pyside)
  - [pandas_model](#module-pandas_model)
  - [profile_manager_dialog](#module-profile_manager_dialog)
  - [report_selection_dialog](#module-report_selection_dialog)
  - [worker](#module-worker)
  - [log_handler](#module-log_handler)
- [Modules Added After v1.8.6.0](#modules-added-after-v1860)

Note: this document covers modules present at v1.8.6.0. Modules added in subsequent releases are listed in the appendix at the end with brief descriptions.

---

# Backend API (shopify_tool)

## Module: core

**Location**: `shopify_tool/core.py`

**Purpose**: Orchestrates the entire fulfillment analysis process, validates data, generates reports, and manages the fulfillment history.

### Constants

```python
SYSTEM_TAGS = ["Repeat", "Priority", "Error"]
```
System-defined tags that can be applied to orders.

### Functions

#### `run_full_analysis(stock_file_path, orders_file_path, output_dir_path, stock_delimiter, config)`

Orchestrates the entire fulfillment analysis process.

**Parameters**:
- `stock_file_path` (str | None): Path to the stock data CSV file
- `orders_file_path` (str | None): Path to the Shopify orders export CSV file
- `output_dir_path` (str): Path to the directory where the output report will be saved
- `stock_delimiter` (str): The delimiter used in the stock CSV file
- `config` (dict): The application configuration dictionary

**Returns**: `tuple[bool, str | None, pd.DataFrame | None, dict | None]`
- `bool`: True for success, False for failure
- `str | None`: Result message (output file path on success, error message on failure)
- `pd.DataFrame | None`: The final analysis DataFrame if successful
- `dict | None`: Calculated statistics if successful

**Workflow**:
1. Loads stock and order data from CSV files
2. Validates required columns
3. Loads historical fulfillment data
4. Runs fulfillment simulation
5. Applies stock alerts and custom rules
6. Saves detailed analysis report to Excel
7. Updates fulfillment history

**Example**:
```python
success, output_path, df, stats = run_full_analysis(
    stock_file_path="inventory.csv",
    orders_file_path="orders_export.csv",
    output_dir_path="output/session_1",
    stock_delimiter=";",
    config=app_config
)
```

#### `validate_csv_headers(file_path, required_columns, delimiter=",")`

Quickly validates if a CSV file contains the required column headers.

**Parameters**:
- `file_path` (str): The path to the CSV file
- `required_columns` (list[str]): A list of column names that must be present
- `delimiter` (str, optional): The delimiter used in the CSV file. Defaults to ","

**Returns**: `tuple[bool, list[str]]`
- `bool`: True if all required columns are present
- `list[str]`: List of missing columns (empty if all present)

**Notes**:
- Only reads the header row, not the entire file
- Returns error information for file not found or parser errors

#### `create_packing_list_report(analysis_df, report_config)`

Generates a single packing list report based on a report configuration.

**Parameters**:
- `analysis_df` (pd.DataFrame): The main analysis DataFrame
- `report_config` (dict): Report configuration with filters, output filename, excluded SKUs

**Returns**: `tuple[bool, str]`
- `bool`: True for success, False for failure
- `str`: Success/error message

**Report Config Structure**:
```python
{
    "name": "DHL Packing List",
    "output_filename": "dhl_packing.xlsx",
    "filters": [
        {"field": "Shipping_Provider", "operator": "==", "value": "DHL"}
    ],
    "exclude_skus": ["EXCLUDED-SKU-1", "EXCLUDED-SKU-2"]
}
```

#### `create_stock_export_report(analysis_df, report_config)`

Generates a single stock export report based on a configuration.

**Parameters**:
- `analysis_df` (pd.DataFrame): The main analysis DataFrame
- `report_config` (dict): Report configuration

**Returns**: `tuple[bool, str]`
- `bool`: Success flag
- `str`: Status message

#### `get_unique_column_values(df, column_name)`

Extracts unique, sorted, non-null values from a DataFrame column.

**Parameters**:
- `df` (pd.DataFrame): The DataFrame to extract values from
- `column_name` (str): The name of the column

**Returns**: `list[str]`
- Sorted list of unique string-converted values, or empty list if column doesn't exist

### Internal Functions

#### `_normalize_unc_path(path)`

Normalizes a path, especially useful for UNC paths on Windows.

**Parameters**:
- `path` (str): The path to normalize

**Returns**: `str` - Normalized path

#### `_validate_dataframes(orders_df, stock_df, config)`

Validates that required columns are present in the dataframes.

**Parameters**:
- `orders_df` (pd.DataFrame): The DataFrame containing order data
- `stock_df` (pd.DataFrame): The DataFrame containing stock data
- `config` (dict): The application configuration dictionary

**Returns**: `list[str]` - List of error messages (empty if validation passed)

---

## Module: analysis

**Location**: `shopify_tool/analysis.py`

**Purpose**: Performs the core fulfillment analysis and simulation, calculating which orders can be fulfilled based on available stock.

### Functions

#### `run_analysis(stock_df, orders_df, history_df, column_mappings=None, courier_mappings=None)`

Performs the core fulfillment analysis and simulation.

**Parameters**:
- `stock_df` (pd.DataFrame): DataFrame with stock levels for each SKU (columns will be mapped using column_mappings)
- `orders_df` (pd.DataFrame): DataFrame with order line items (columns will be mapped using column_mappings)
- `history_df` (pd.DataFrame): DataFrame with previously fulfilled order numbers (requires 'Order_Number' column)
- `column_mappings` (dict, optional): Dictionary with 'orders' and 'stock' keys mapping CSV columns to internal names. If None, uses default Shopify/Bulgarian mappings.
- `courier_mappings` (dict, optional): Dictionary mapping courier patterns to standardized codes. Supports new format ({"DHL": {"patterns": ["dhl"]}}) and legacy format ({"dhl": "DHL"}). If None, uses hardcoded fallback rules.

**Returns**: `tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]`
- `final_df`: Main DataFrame with detailed results for every line item
- `summary_present_df`: Summary of SKUs that will be fulfilled
- `summary_missing_df`: Summary of SKUs in unfulfillable orders
- `stats`: Dictionary containing key statistics

**Algorithm**:
1. **Data Cleaning**: Standardizes columns, fills missing values
2. **Prioritization**: Multi-item orders first to maximize complete order fulfillment
3. **Simulation**: Iterates through orders, allocates stock
4. **Enrichment**: Adds shipping provider, order type, repeat status
5. **Summary Generation**: Creates fulfillment and missing item summaries

**Output Columns**:
- `Order_Number`: Order identifier
- `Order_Type`: "Single" or "Multi" item order
- `SKU`: Product SKU
- `Product_Name`: Product name
- `Quantity`: Quantity ordered
- `Stock`: Initial stock level
- `Final_Stock`: Stock level after simulation
- `Stock_Alert`: Low stock warning
- `Order_Fulfillment_Status`: "Fulfillable" or "Not Fulfillable"
- `Shipping_Provider`: Standardized carrier name
- `Destination_Country`: Destination (for international)
- `System_note`: System-generated notes (e.g., "Repeat")
- `Status_Note`: User/rule-defined notes

#### `recalculate_statistics(df)`

Calculates statistics based on the provided analysis DataFrame.

**Parameters**:
- `df` (pd.DataFrame): The main analysis DataFrame

**Returns**: `dict` with keys:
- `total_orders_completed` (int)
- `total_orders_not_completed` (int)
- `total_items_to_write_off` (int)
- `total_items_not_to_write_off` (int)
- `couriers_stats` (list[dict] | None): Per-courier statistics

**Courier Stats Structure**:
```python
{
    "courier_id": "DHL",
    "orders_assigned": 45,
    "repeated_orders_found": 3
}
```

#### `toggle_order_fulfillment(df, order_number)`

Manually toggles the fulfillment status of an order and recalculates stock.

**Parameters**:
- `df` (pd.DataFrame): The main analysis DataFrame
- `order_number` (str): The order number to toggle

**Returns**: `tuple[bool, str | None, pd.DataFrame]`
- `success` (bool): True if toggle was successful
- `error_message` (str | None): Error message if failed
- `updated_df` (pd.DataFrame): Modified DataFrame

**Behavior**:
- **Fulfillable → Not Fulfillable**: Returns stock to pool, increases Final_Stock
- **Not Fulfillable → Fulfillable**: Force-fulfill if stock available, decreases Final_Stock
- Validates stock availability before force-fulfill

### Internal Functions

#### `_generalize_shipping_method(method, courier_mappings=None)`

Standardizes raw shipping method names to consistent format using configurable mappings.

**Parameters**:
- `method` (str | float): Raw shipping method string or NaN
- `courier_mappings` (dict, optional): Courier mappings configuration. Supports:
  - New format: `{"DHL": {"patterns": ["dhl", "dhl express"]}}`
  - Legacy format: `{"dhl": "DHL"}`
  - If None or empty, uses hardcoded fallback rules

**Returns**: `str` - Standardized shipping provider name

**Default Fallback Mappings (when courier_mappings is None)**:
- "dhl" → "DHL"
- "dpd" → "DPD"
- "international shipping" → "PostOne"
- Unknown → Title case
- NaN → "Unknown"

**Dynamic Mapping Examples**:
- `method="fedex overnight"`, `courier_mappings={"FedEx": {"patterns": ["fedex"]}}` → "FedEx"
- `method="econt express"`, `courier_mappings={"Econt": {"patterns": ["econt"]}}` → "Econt"
- `method="dhl"`, `courier_mappings={"dhl": "DHL"}` (legacy) → "DHL"

---

## Module: rules

**Location**: `shopify_tool/rules.py`

**Purpose**: Implements a configurable rule engine to process and modify order data based on user-defined conditions and actions.

### Constants

```python
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
    # NEW (v1.9.0): List operators
    "in list": "_op_in_list",
    "not in list": "_op_not_in_list",
    # NEW (v1.9.0): Range operators
    "between": "_op_between",
    "not between": "_op_not_between",
    # NEW (v1.9.0): Date operators
    "date before": "_op_date_before",
    "date after": "_op_date_after",
    "date equals": "_op_date_equals",
    # NEW (v1.9.0): Regex operator
    "matches regex": "_op_matches_regex",
}
```

### Classes

#### `RuleEngine`

Applies a set of configured rules to a DataFrame of order data.

##### Constructor

```python
def __init__(self, rules_config)
```

**Parameters**:
- `rules_config` (list[dict]): List of rule configurations

**Rule Configuration Structure**:
```python
{
    "name": "High Value Orders",
    "match": "ALL",  # or "ANY"
    "conditions": [
        {
            "field": "Total Price",
            "operator": "is greater than",
            "value": "100"
        }
    ],
    "actions": [
        {
            "type": "ADD_TAG",
            "value": "HighValue"
        },
        {
            "type": "ADD_INTERNAL_TAG",
            "value": "priority:high"
        }
    ]
}
```

**Rule Priority System**:

Rules support an optional `priority` field to control execution order:

- **Type**: `int`
- **Default**: `1000` (if not specified)
- **Lower values = higher priority** (execute first)
- **Per-Level**: Article rules and order rules have separate priority sequences

**Example with Priority**:
```json
{
  "rules": [
    {
      "name": "Calculate Total First",
      "priority": 1,
      "level": "article",
      "match": "ALL",
      "conditions": [{"field": "Quantity", "operator": "is greater than", "value": "0"}],
      "actions": [{
        "type": "CALCULATE",
        "operation": "multiply",
        "field1": "Quantity",
        "field2": "Unit_Price",
        "target": "Total_Price"
      }]
    },
    {
      "name": "Tag Based on Total",
      "priority": 2,
      "level": "article",
      "match": "ALL",
      "conditions": [{"field": "Total_Price", "operator": "is greater than", "value": "100"}],
      "actions": [{"type": "ADD_TAG", "value": "HIGH-VALUE"}]
    }
  ]
}
```

**Execution Order**:
- Rules are sorted by priority before execution (lower number = executes first)
- Article rules always execute before order rules (separate phases)
- Within each level (article/order), rules execute in priority order
- Rules without `priority` field automatically receive 1000, 1001, 1002... (executed last)

**Priority Gaps**:
- Priority values like 1, 5, 10, 20 are allowed (no need for sequential numbering)
- Gaps enable inserting new rules without renumbering existing ones

**Backward Compatibility**:
- Existing configs without `priority` field continue to work
- Rules are automatically assigned default priorities preserving their original order

##### Methods

###### `apply(df)`

Applies all configured rules to the given DataFrame.

**Parameters**:
- `df` (pd.DataFrame): The order data DataFrame to process

**Returns**: `pd.DataFrame` - The modified DataFrame

**Process**:
1. Prepares DataFrame columns for actions
2. For each rule:
   - Evaluates conditions
   - Executes actions on matching rows
3. Returns modified DataFrame

###### `_prepare_df_for_actions(df)` (Internal)

Ensures the DataFrame has columns required for rule actions.

**Parameters**:
- `df` (pd.DataFrame): DataFrame to prepare

**Columns Added**:
- `Priority`: Default "Normal"
- `_is_excluded`: Default False
- `Status_Note`: Default ""

###### `_get_matching_rows(df, rule)` (Internal)

Evaluates a rule's conditions and finds all matching rows.

**Parameters**:
- `df` (pd.DataFrame): DataFrame to evaluate
- `rule` (dict): Rule configuration

**Returns**: `pd.Series[bool]` - Boolean series indicating matching rows

**Match Types**:
- `ALL`: All conditions must be true (AND logic)
- `ANY`: At least one condition must be true (OR logic)

###### `_execute_actions(df, matches, actions)` (Internal)

Executes a list of actions on matching rows.

**Parameters**:
- `df` (pd.DataFrame): DataFrame to modify
- `matches` (pd.Series[bool]): Boolean series of rows to modify
- `actions` (list[dict]): List of action configurations

**Active Action Types** (as of v1.9.0):
- `ADD_TAG`: Appends value to Status_Note column
- `ADD_ORDER_TAG`: Appends value to Status_Note (order-level only)
- `ADD_INTERNAL_TAG`: Adds structured tag to Internal_Tags JSON column (recommended for metadata)
- `SET_STATUS`: Changes Order_Fulfillment_Status

**Deprecated Action Types** (removed in v1.9.0):
The following action types have been removed: `SET_PRIORITY`, `EXCLUDE_FROM_REPORT`, `SET_PACKAGING_TAG`, `EXCLUDE_SKU`.
If encountered, these actions will log a warning and be skipped. Use `ADD_INTERNAL_TAG` for structured metadata instead.

**Migration Examples**:
- `SET_PRIORITY: "High"` → `ADD_INTERNAL_TAG: "priority:high"`
- `EXCLUDE_FROM_REPORT` → `ADD_INTERNAL_TAG: "exclude_from_report"`
- `SET_PACKAGING_TAG: "BOX"` → `ADD_INTERNAL_TAG: "packaging:box"`

### Operator Functions

All operator functions return a boolean pandas Series.

#### `_op_equals(series_val, rule_val)`
Returns True where series value equals rule value.

#### `_op_not_equals(series_val, rule_val)`
Returns True where series value does not equal rule value.

#### `_op_contains(series_val, rule_val)`
Returns True where series string contains rule string (case-insensitive).

#### `_op_not_contains(series_val, rule_val)`
Returns True where series string does not contain rule string.

#### `_op_greater_than(series_val, rule_val)`
Returns True where numeric series value > rule value.

#### `_op_less_than(series_val, rule_val)`
Returns True where numeric series value < rule value.

#### `_op_starts_with(series_val, rule_val)`
Returns True where series string starts with rule string.

#### `_op_ends_with(series_val, rule_val)`
Returns True where series string ends with rule string.

#### `_op_is_empty(series_val, rule_val)`
Returns True where series value is null or empty string.

#### `_op_is_not_empty(series_val, rule_val)`
Returns True where series value is not null and not empty.

### New Operators (v1.9.0)

The rule engine now supports 10 additional operators for more advanced filtering and matching capabilities.

#### List Operators

##### `_op_in_list(series_val, rule_val)`
Returns True where the series value matches any item in a comma-separated list.

**Features**:
- Case-insensitive matching
- Automatic whitespace trimming
- Handles multiple values: `"DHL, PostOne, DPD"`

**Example**:
```python
{
    "field": "Shipping_Provider",
    "operator": "in list",
    "value": "DHL, PostOne, FedEx"
}
```

##### `_op_not_in_list(series_val, rule_val)`
Returns True where the series value does NOT match any item in the list.

**Example**:
```python
{
    "field": "Shipping_Provider",
    "operator": "not in list",
    "value": "DPD, UPS"
}
```

#### Range Operators

##### `_op_between(series_val, rule_val)`
Returns True where the series value falls within an inclusive numeric range.

**Format**: `"start-end"` (e.g., `"10-100"`)

**Features**:
- Inclusive boundaries (10 and 100 both match in "10-100")
- Supports floats: `"5.5-15.5"`
- Falls back to string comparison for non-numeric values
- Validates range order (rejects reversed ranges like "100-10")

**Example**:
```python
{
    "field": "Total_Price",
    "operator": "between",
    "value": "50-150"
}
```

##### `_op_not_between(series_val, rule_val)`
Returns True where the series value does NOT fall within the range.

**Example**:
```python
{
    "field": "Total_Price",
    "operator": "not between",
    "value": "50-150"
}
```

#### Date Operators

All date operators support multiple date formats and ignore time components:

**Supported Formats**:
- ISO format: `YYYY-MM-DD` (e.g., `"2024-01-30"`)
- European slash: `DD/MM/YYYY` (e.g., `"30/01/2024"`)
- European dot: `DD.MM.YYYY` (e.g., `"30.01.2024"`)

##### `_op_date_before(series_val, rule_val)`
Returns True where the series date is before the rule date.

**Example**:
```python
{
    "field": "Order_Date",
    "operator": "date before",
    "value": "2024-01-30"
}
```

##### `_op_date_after(series_val, rule_val)`
Returns True where the series date is after the rule date.

**Example**:
```python
{
    "field": "Order_Date",
    "operator": "date after",
    "value": "2024-01-01"
}
```

##### `_op_date_equals(series_val, rule_val)`
Returns True where the series date equals the rule date (time component ignored).

**Example**:
```python
{
    "field": "Order_Date",
    "operator": "date equals",
    "value": "30/01/2024"
}
```

#### Regex Operator

##### `_op_matches_regex(series_val, rule_val)`
Returns True where the series value matches a regular expression pattern.

**Features**:
- Full regex syntax support
- Pattern caching with LRU cache (maxsize=128) for performance
- Invalid patterns log warnings and return False

**Example**:
```python
{
    "field": "SKU",
    "operator": "matches regex",
    "value": "^SKU-\\d{4}$"  # Matches "SKU-1234", "SKU-5678", etc.
}
```

**Common Patterns**:
- Starts with: `^PREFIX`
- Ends with: `SUFFIX$`
- Contains digits: `\\d+`
- Alphanumeric: `[A-Za-z0-9]+`
- Phone numbers: `^\\d{3}-\\d{3}-\\d{4}$`

### Error Handling (v1.9.0)

All new operators handle invalid inputs gracefully:

**List Operators**:
- Empty string → Returns False (no matches)
- Whitespace only → Returns False

**Range Operators**:
- Reversed range ("100-10") → Logs warning, returns False
- Missing start/end ("10-", "-100") → Logs warning, returns False
- Non-numeric values → Logs warning, returns False
- Invalid format ("invalid") → Logs warning, returns False

**Date Operators**:
- Invalid format ("not-a-date") → Logs warning, returns False
- Invalid month/day ("2024-13-45") → Logs warning, returns False
- Empty string → Returns False (no warning)

**Regex Operator**:
- Invalid pattern ("[invalid") → Logs warning, returns False
- Unclosed groups ("(?P<invalid") → Logs warning, returns False
- Invalid quantifiers ("*invalid") → Logs warning, returns False

All warnings are logged with `[RULE ENGINE]` prefix for easy filtering.

### Performance Notes (v1.9.0)

- **Regex patterns** are cached using `@lru_cache(maxsize=128)` to avoid recompilation
- **Vectorized operations** ensure efficient processing of large datasets
- **Date parsing** happens row-by-row only for date operators to support multiple formats
- Expected performance: <1 second for 100 orders, <30 seconds for 10,000 orders

---

## Module: packing_lists

**Location**: `shopify_tool/packing_lists.py`

**Purpose**: Creates formatted packing lists in Excel format based on filtered analysis data.

### Functions

#### `create_packing_list(analysis_df, output_file, report_name="Packing List", filters=None, exclude_skus=None)`

Creates a versatile, formatted packing list in an Excel .xlsx file.

**Parameters**:
- `analysis_df` (pd.DataFrame): Main analysis DataFrame
- `output_file` (str): Full path where the output .xlsx file will be saved
- `report_name` (str, optional): Name of the report for logging. Defaults to "Packing List"
- `filters` (list[dict], optional): List of filter conditions. Defaults to None
- `exclude_skus` (list[str], optional): List of SKUs to exclude. Defaults to None

**Filter Structure**:
```python
{
    "field": "Shipping_Provider",
    "operator": "==",  # "==", "!=", "in", "not in", "contains"
    "value": "DHL"
}
```

**Features**:
1. **Filtering**: Includes only 'Fulfillable' orders matching criteria
2. **Exclusion**: Can exclude specific SKUs
3. **Sorting**: By shipping provider, order number, and SKU
4. **Formatting**:
   - Custom headers with timestamp and filename
   - Borders grouping items by order
   - Auto-adjusted column widths
   - Print settings for A4 landscape

**Output Columns**:
- Destination_Country (only on first item of order)
- Order_Number
- SKU
- Product_Name
- Quantity
- Shipping_Provider (in header as timestamp)

**Excel Features**:
- Bold headers with gray background
- Borders grouping order items
- Center-aligned country and quantity
- Repeated headers on each page
- Landscape orientation
- Fit to 1 page wide

---

## Module: stock_export

**Location**: `shopify_tool/stock_export.py`

**Purpose**: Creates stock export files for inventory management and courier integration.

### Functions

#### `create_stock_export(analysis_df, output_file, report_name="Stock Export", filters=None)`

Creates a stock export .xls file from scratch.

**Parameters**:
- `analysis_df` (pd.DataFrame): Main analysis DataFrame
- `output_file` (str): Full path where the new .xls file will be saved
- `report_name` (str, optional): Name of the report for logging. Defaults to "Stock Export"
- `filters` (list[dict], optional): List of filter conditions. Defaults to None

**Process**:
1. Filters 'Fulfillable' orders by criteria
2. Summarizes total quantity per SKU
3. Creates DataFrame with columns: 'Артикул' (SKU), 'Наличност' (Quantity)
4. Saves to .xls format

**Features**:
- Template-free generation
- Aggregation by SKU
- Fallback to direct xlwt if pandas engine fails
- Creates empty file with headers if no data matches

**Output Format**:
```
Артикул      | Наличност
-------------|----------
SKU-123      | 15
SKU-456      | 8
```

---

## Module: utils

**Location**: `shopify_tool/utils.py`

**Purpose**: Provides utility functions for path handling and resource management.

### Functions

#### `get_persistent_data_path(filename)`

Gets the full path to a file in a persistent application data directory.

**Parameters**:
- `filename` (str): The name of the file (e.g., "history.csv")

**Returns**: `str` - Absolute path to the file

**Directory Locations**:
- **Windows**: `%APPDATA%/ShopifyFulfillmentTool/`
- **Linux/macOS**: `~/.local/share/ShopifyFulfillmentTool/`

**Features**:
- Creates directory if it doesn't exist
- Falls back to current directory on permission error
- Logs errors appropriately

**Example**:
```python
history_path = get_persistent_data_path("fulfillment_history.csv")
# Returns: C:/Users/User/AppData/Roaming/ShopifyFulfillmentTool/fulfillment_history.csv
```

#### `resource_path(relative_path)`

Gets the absolute path to a resource, for both dev and PyInstaller environments.

**Parameters**:
- `relative_path` (str): Path relative to application root (e.g., "data/templates/template.xls")

**Returns**: `str` - Absolute path to the resource

**Behavior**:
- **Development**: Resolves relative to current working directory
- **PyInstaller Bundle**: Resolves relative to `sys._MEIPASS` (temp directory)

**Example**:
```python
template_path = resource_path("data/templates/packing_list.xls")
```

---

## Module: logger_config

**Location**: `shopify_tool/logger_config.py`

**Purpose**: Configures and initializes centralized logging for the entire application.

### Functions

#### `setup_logging()`

Configures and initializes the logging for the entire application.

**Returns**: `logging.Logger` - The configured logger instance

**Configuration**:
- **Logger Name**: "ShopifyToolLogger"
- **Level**: INFO
- **Handlers**:
  1. **RotatingFileHandler**:
     - File: `logs/app_history.log`
     - Max Size: 1MB
     - Backup Count: 5
     - Format: `%(asctime)s - %(levelname)s - %(message)s (%(filename)s:%(lineno)d)`
  2. **StreamHandler** (console):
     - Format: `%(levelname)s: %(message)s`

**Features**:
- Prevents duplicate handlers on multiple calls
- Creates `logs/` directory if it doesn't exist
- UTF-8 encoding for file handler

**Example**:
```python
from shopify_tool.logger_config import setup_logging
logger = setup_logging()
logger.info("Application started")
```

---

## Module: profile_manager

**Location**: `shopify_tool/profile_manager.py`

**Purpose**: Manages client-specific configurations on centralized file server with caching, file locking, and automatic backups.

### Classes

#### `ProfileManager`

Manages client profiles and centralized configuration on file server.

##### Constructor

```python
def __init__(self, base_path: str)
```

**Parameters**:
- `base_path` (str): Root path on file server (e.g., `\\\\192.168.88.101\\Z_GreenDelivery\\WAREHOUSE\\0UFulfilment`)

**Raises**:
- `NetworkError`: If file server is not accessible

**Attributes**:
- `base_path` (Path): Root path on file server
- `clients_dir` (Path): Directory containing client profiles (`Clients/`)
- `sessions_dir` (Path): Directory containing session data (`Sessions/`)
- `stats_dir` (Path): Directory for statistics (`Stats/`)
- `logs_dir` (Path): Directory for centralized logs (`Logs/shopify_tool/`)
- `connection_timeout` (int): Timeout for network operations in seconds
- `is_network_available` (bool): Whether file server is accessible

##### Class Attributes

```python
_config_cache: Dict[str, Tuple[Dict, datetime]] = {}  # Shared cache
CACHE_TIMEOUT_SECONDS = 60  # Cache valid for 1 minute
```

##### Methods

###### `validate_client_id(client_id: str) -> Tuple[bool, str]` (Static)

Validate client ID format.

**Rules**:
- Not empty
- Max 20 characters
- Only alphanumeric and underscore
- No "CLIENT_" prefix (added automatically)
- Not a Windows reserved name

**Returns**: `Tuple[bool, str]`
- `(True, "")` if valid
- `(False, "error description")` if invalid

**Example**:
```python
is_valid, error_msg = ProfileManager.validate_client_id("M")
if not is_valid:
    print(f"Invalid: {error_msg}")
```

###### `list_clients() -> List[str]`

Get list of available client IDs.

**Returns**: `List[str]` - List of client IDs without CLIENT_ prefix (e.g., `["M", "A", "B"]`)

###### `create_client_profile(client_id: str, client_name: str) -> bool`

Create a new client profile with default configuration.

**Creates**:
```
Clients/CLIENT_{ID}/
├── client_config.json      # General config
├── shopify_config.json     # Shopify-specific config
└── backups/                # Config backups
```

**Parameters**:
- `client_id` (str): Client ID (e.g., "M")
- `client_name` (str): Full client name (e.g., "M Cosmetics")

**Returns**: `bool` - True if created, False if already exists

**Raises**:
- `ValidationError`: If client_id is invalid
- `ProfileManagerError`: If creation fails

###### `load_client_config(client_id: str) -> Optional[Dict]`

Load general configuration for a client.

**Returns**: `Optional[Dict]` - Configuration dictionary or None if not found

###### `load_shopify_config(client_id: str) -> Optional[Dict]`

Load Shopify configuration for a client with caching.

Uses time-based caching (60 seconds) to reduce network round-trips.

**Returns**: `Optional[Dict]` - Shopify configuration or None if not found

###### `save_shopify_config(client_id: str, config: Dict) -> bool`

Save Shopify configuration with file locking and backup.

Uses platform-specific file locking to prevent concurrent write conflicts.
Creates automatic backup before saving.

**Parameters**:
- `client_id` (str): Client ID
- `config` (Dict): Configuration to save

**Returns**: `bool` - True if saved successfully

**Raises**:
- `ProfileManagerError`: If save fails or file is locked

**Example**:
```python
config = profile_mgr.load_shopify_config("M")
config["settings"]["low_stock_threshold"] = 10
profile_mgr.save_shopify_config("M", config)
```

###### `get_client_directory(client_id: str) -> Path`

Get path to client's directory.

**Returns**: `Path` - Path to client directory

###### `client_exists(client_id: str) -> bool`

Check if client profile exists.

**Returns**: `bool` - True if client exists

---

## Module: session_manager

**Location**: `shopify_tool/session_manager.py`

**Purpose**: Manages the lifecycle of client-specific fulfillment sessions including creation, metadata management, and querying.

### Classes

#### `SessionManager`

Manages client-specific fulfillment sessions.

##### Constructor

```python
def __init__(self, profile_manager)
```

**Parameters**:
- `profile_manager`: ProfileManager instance for accessing file server paths

**Attributes**:
- `profile_manager`: ProfileManager instance
- `sessions_root` (Path): Root directory for all sessions

##### Class Attributes

```python
SESSION_SUBDIRS = ["input", "analysis", "packing_lists", "stock_exports"]
VALID_STATUSES = ["active", "completed", "abandoned"]
```

##### Methods

###### `create_session(client_id: str) -> str`

Create a new session for a client.

Creates a timestamped directory with format `{YYYY-MM-DD_N}` where N is
an incrementing number for multiple sessions on the same day.

**Directory Structure**:
```
Sessions/CLIENT_{ID}/{YYYY-MM-DD_N}/
├── session_info.json       # Session metadata
├── input/                  # Source files
├── analysis/               # Analysis results
├── packing_lists/          # Generated packing lists
└── stock_exports/          # Stock exports
```

**Parameters**:
- `client_id` (str): Client ID (e.g., "M")

**Returns**: `str` - Full path to created session directory

**Raises**:
- `SessionManagerError`: If session creation fails

**Example**:
```python
session_mgr = SessionManager(profile_mgr)
session_path = session_mgr.create_session("M")
# Returns: "\\\\server\\...\\Sessions\\CLIENT_M\\2025-11-05_1"
```

###### `get_session_path(client_id: str, session_name: str) -> Path`

Get full path to a session directory.

**Parameters**:
- `client_id` (str): Client ID
- `session_name` (str): Session name (e.g., "2025-11-05_1")

**Returns**: `Path` - Full path to session directory

###### `list_client_sessions(client_id: str, status_filter: Optional[str] = None) -> List[Dict]`

List all sessions for a client.

**Parameters**:
- `client_id` (str): Client ID
- `status_filter` (str, optional): Filter by status ("active", "completed", "abandoned")

**Returns**: `List[Dict]` - List of session info dictionaries, sorted by creation date (newest first)

Each dict contains:
- `session_name`: Session directory name
- `status`: Session status
- `created_at`: ISO timestamp
- `client_id`: Client ID
- `created_by_tool`: "shopify"
- `pc_name`: Computer name
- `session_path`: Full path

**Example**:
```python
sessions = session_mgr.list_client_sessions("M", status_filter="active")
for session in sessions:
    print(f"{session['session_name']}: {session['status']}")
```

###### `get_session_info(session_path: str) -> Optional[Dict]`

Load session metadata from session_info.json.

**Parameters**:
- `session_path` (str): Full path to session directory

**Returns**: `Optional[Dict]` - Session info dictionary or None if not found

###### `update_session_status(session_path: str, status: str) -> bool`

Update session status in session_info.json.

**Parameters**:
- `session_path` (str): Full path to session directory
- `status` (str): New status ("active", "completed", "abandoned")

**Returns**: `bool` - True if updated successfully

**Raises**:
- `SessionManagerError`: If status is invalid or update fails

###### `update_session_info(session_path: str, updates: Dict) -> bool`

Update session metadata with arbitrary fields.

**Parameters**:
- `session_path` (str): Full path to session directory
- `updates` (Dict): Dictionary of fields to update

**Returns**: `bool` - True if updated successfully

**Example**:
```python
session_mgr.update_session_info(
    session_path,
    {
        "analysis_completed": True,
        "packing_lists_generated": ["DHL", "DPD"]
    }
)
```

###### `get_session_subdirectory(session_path: str, subdir_name: str) -> Path`

Get path to a session subdirectory.

**Parameters**:
- `session_path` (str): Full path to session directory
- `subdir_name` (str): Subdirectory name ("input", "analysis", "packing_lists", "stock_exports")

**Returns**: `Path` - Full path to subdirectory

**Raises**:
- `SessionManagerError`: If subdirectory doesn't exist or invalid name

###### Helper Methods

```python
def get_input_dir(session_path: str) -> Path
def get_analysis_dir(session_path: str) -> Path
def get_packing_lists_dir(session_path: str) -> Path
def get_stock_exports_dir(session_path: str) -> Path
```

Get paths to specific session subdirectories.

###### `session_exists(client_id: str, session_name: str) -> bool`

Check if a session exists.

**Returns**: `bool` - True if session exists

###### `delete_session(session_path: str) -> bool`

Delete a session directory.

**WARNING**: This permanently deletes all session data.

**Returns**: `bool` - True if deleted successfully

**Raises**:
- `SessionManagerError`: If deletion fails

---

## Module: stats_manager (Unified)

**Location**: `shared/stats_manager.py`

**Purpose**: Unified statistics tracking for both Shopify Tool and Packing Tool with centralized storage and concurrent access support.

### Classes

#### `StatsManager`

Manages centralized statistics stored in `Stats/global_stats.json` on file server.

##### Constructor

```python
def __init__(
    self,
    base_path: str,
    max_retries: int = 5,
    retry_delay: float = 0.1
)
```

**Parameters**:
- `base_path` (str): Path to 0UFulfilment directory (e.g., `\\\\server\\...\\0UFulfilment`)
- `max_retries` (int): Maximum retry attempts for locked files
- `retry_delay` (float): Delay in seconds between retries

**Attributes**:
- `base_path` (Path): Base path to 0UFulfilment directory
- `stats_file` (Path): Path to `Stats/global_stats.json`
- `max_retries` (int): Maximum retry attempts
- `retry_delay` (float): Delay between retries

##### Methods

###### `record_analysis(client_id: str, session_id: str, orders_count: int, metadata: Optional[Dict] = None) -> None`

Record an analysis completion from Shopify Tool.

**Parameters**:
- `client_id` (str): Client identifier (e.g., "M", "A", "B")
- `session_id` (str): Session identifier (e.g., "2025-11-05_1")
- `orders_count` (int): Number of orders analyzed
- `metadata` (Optional[Dict]): Additional metadata (e.g., fulfillable_orders, courier_breakdown)

**Example**:
```python
stats_mgr.record_analysis(
    client_id="M",
    session_id="2025-11-05_1",
    orders_count=150,
    metadata={
        "fulfillable_orders": 142,
        "courier_breakdown": {"DHL": 80, "DPD": 62}
    }
)
```

###### `record_packing(client_id: str, session_id: str, worker_id: Optional[str], orders_count: int, items_count: int, metadata: Optional[Dict] = None) -> None`

Record a packing session completion from Packing Tool.

**Parameters**:
- `client_id` (str): Client identifier
- `session_id` (str): Session identifier
- `worker_id` (Optional[str]): Worker identifier (e.g., "001", "002")
- `orders_count` (int): Number of orders packed
- `items_count` (int): Number of items packed
- `metadata` (Optional[Dict]): Additional metadata (e.g., duration, timestamps)

**Example**:
```python
stats_mgr.record_packing(
    client_id="M",
    session_id="2025-11-05_1",
    worker_id="001",
    orders_count=142,
    items_count=450,
    metadata={
        "start_time": "2025-11-05T10:00:00",
        "end_time": "2025-11-05T12:30:00",
        "duration_seconds": 9000
    }
)
```

###### `get_global_stats() -> Dict[str, Any]`

Get global statistics summary.

**Returns**: `Dict[str, Any]` with keys:
- `total_orders_analyzed` (int): Total orders analyzed by Shopify Tool
- `total_orders_packed` (int): Total orders packed by Packing Tool
- `total_sessions` (int): Total packing sessions
- `last_updated` (str): Last update timestamp

**Example**:
```python
stats = stats_mgr.get_global_stats()
print(f"Total analyzed: {stats['total_orders_analyzed']}")
print(f"Total packed: {stats['total_orders_packed']}")
```

###### `get_client_stats(client_id: str) -> Dict[str, Any]`

Get statistics for a specific client.

**Parameters**:
- `client_id` (str): Client identifier

**Returns**: `Dict[str, Any]` with keys:
- `orders_analyzed` (int): Orders analyzed for this client
- `orders_packed` (int): Orders packed for this client
- `sessions` (int): Packing sessions for this client

###### `get_all_clients_stats() -> Dict[str, Dict[str, Any]]`

Get statistics for all clients.

**Returns**: `Dict[str, Dict[str, Any]]` - Dictionary mapping client IDs to their statistics

###### `get_analysis_history(client_id: Optional[str] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]`

Get analysis history with optional filtering.

**Parameters**:
- `client_id` (Optional[str]): Filter by client ID (None for all clients)
- `limit` (Optional[int]): Maximum number of records to return (newest first)

**Returns**: `List[Dict[str, Any]]` - List of analysis records

Each record contains:
- `timestamp`: ISO timestamp
- `client_id`: Client ID
- `session_id`: Session ID
- `orders_count`: Number of orders
- `metadata`: Optional additional data

###### `get_packing_history(client_id: Optional[str] = None, worker_id: Optional[str] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]`

Get packing history with optional filtering.

**Parameters**:
- `client_id` (Optional[str]): Filter by client ID
- `worker_id` (Optional[str]): Filter by worker ID
- `limit` (Optional[int]): Maximum number of records

**Returns**: `List[Dict[str, Any]]` - List of packing records

###### `reset_stats() -> None`

Reset all statistics to default values.

**WARNING**: This will delete all historical data. Use with caution.

### Exceptions

#### `ProfileManagerError`
Base exception for ProfileManager errors.

#### `NetworkError(ProfileManagerError)`
Raised when file server is not accessible.

#### `ValidationError(ProfileManagerError)`
Raised when validation fails.

#### `SessionManagerError`
Base exception for SessionManager errors.

#### `StatsManagerError`
Base exception for StatsManager errors.

#### `FileLockError(StatsManagerError)`
Raised when file locking fails.

---

# Frontend API (gui)

## Module: main_window_pyside

**Location**: `gui/main_window_pyside.py`

**Purpose**: Main application window that orchestrates the UI, data, and user interactions.

### Classes

#### `MainWindow(QMainWindow)`

The main window for the Shopify Fulfillment Tool application.

##### Attributes

- `session_path` (str): Directory path for current work session
- `config` (dict): Application's configuration settings
- `config_path` (str): Path to user's config.json file
- `active_profile_name` (str): Name of currently active profile
- `active_profile_config` (dict): Configuration of active profile
- `orders_file_path` (str): Path to loaded orders CSV
- `stock_file_path` (str): Path to loaded stock CSV
- `analysis_results_df` (pd.DataFrame): Main DataFrame with analysis results
- `analysis_stats` (dict): Statistics derived from analysis
- `threadpool` (QThreadPool): Thread pool for background tasks
- `proxy_model` (QSortFilterProxyModel): Proxy for filtering/sorting table
- `ui_manager` (UIManager): Handles UI widget creation/state
- `file_handler` (FileHandler): Manages file selection/loading
- `actions_handler` (ActionsHandler): Handles user actions

##### Methods

###### `__init__(self)`

Initializes the MainWindow, sets up UI, and connects signals.

**Setup Process**:
1. Initializes core attributes
2. Loads/migrates configuration
3. Creates UI widgets
4. Connects signals
5. Sets up logging
6. Attempts to restore previous session

###### Profile Management

```python
def set_active_profile(self, profile_name)
```
Switches the application to a different settings profile.

```python
def create_profile(self, name, base_profile_name="Default")
```
Creates a new profile by copying an existing one.

```python
def rename_profile(self, old_name, new_name)
```
Renames an existing profile.

```python
def delete_profile(self, name)
```
Deletes a settings profile (prevents deleting last profile).

```python
def update_profile_combo(self)
```
Updates the profile dropdown with current list of profiles.

###### UI Update Methods

```python
def filter_table(self)
```
Applies current filter settings to results table view.

```python
def clear_filter(self)
```
Clears the filter input text box.

```python
def update_statistics_tab(self)
```
Populates the 'Statistics' tab with latest analysis data.

```python
def log_activity(self, op_type, desc)
```
Adds a new entry to the 'Activity Log' table.

**Parameters**:
- `op_type` (str): Type of operation (e.g., "Session", "Analysis")
- `desc` (str): Description of the activity

###### Event Handlers

```python
def on_table_double_clicked(self, index)
```
Handles double-click events on results table (toggles order status).

```python
def show_context_menu(self, pos)
```
Shows a context menu for the results table view.

**Context Menu Actions**:
- Change Status
- Add Tag Manually
- Remove Item from Order
- Remove Entire Order
- Copy Order Number
- Copy SKU

###### Session Management

```python
def load_session(self)
```
Loads a previous session from pickle file if available.

```python
def closeEvent(self, event)
```
Handles application window close event, saves session data.

###### Internal Methods

```python
def _init_and_load_config(self)
```
Initializes and loads application configuration, handles migration.

```python
def _save_config(self)
```
Saves the entire configuration object to config.json.

```python
def _update_all_views(self)
```
Central slot to refresh all UI components after data changes.

```python
def connect_signals(self)
```
Connects all UI widget signals to their corresponding slots.

```python
def setup_logging(self)
```
Sets up Qt-based logging handler.

---

## Module: settings_window_pyside

**Location**: `gui/settings_window_pyside.py`

**Purpose**: Dialog window for viewing and editing all application settings.

### Classes

#### `SettingsWindow(QDialog)`

A dialog window for configuring all aspects of the application.

##### Constants

```python
FILTERABLE_COLUMNS = [
    "Order_Number", "Order_Type", "SKU", "Product_Name",
    "Stock_Alert", "Order_Fulfillment_Status", "Shipping_Provider",
    "Destination_Country", "Tags", "System_note", "Status_Note", "Total Price"
]

FILTER_OPERATORS = ["==", "!=", "in", "not in", "contains"]

CONDITION_OPERATORS = [
    "equals", "does not equal", "contains", "does not contain",
    "is greater than", "is less than", "starts with", "ends with",
    "is empty", "is not empty"
]

ACTION_TYPES = [
    "ADD_TAG", "ADD_ORDER_TAG", "ADD_INTERNAL_TAG", "SET_STATUS"
]
```

##### Attributes

- `config_data` (dict): Deep copy of application configuration
- `analysis_df` (pd.DataFrame): Current analysis DataFrame
- `rule_widgets` (list): References to rule UI widgets
- `packing_list_widgets` (list): References to packing list UI widgets
- `stock_export_widgets` (list): References to stock export UI widgets
- `column_mapping_widgets` (dict): References to column mapping inputs
- `courier_mapping_widgets` (list): References to courier mapping rows

##### Methods

###### `__init__(self, parent, config, analysis_df=None)`

Initializes the SettingsWindow.

**Parameters**:
- `parent` (QWidget): Parent widget
- `config` (dict): Application configuration dictionary
- `analysis_df` (pd.DataFrame, optional): Current analysis DataFrame

###### Tab Creation

```python
def create_general_tab(self)
```
Creates 'General & Paths' settings tab.

```python
def create_rules_tab(self)
```
Creates 'Rules' tab for automation rules.

```python
def create_packing_lists_tab(self)
```
Creates 'Packing Lists' tab for report configurations.

```python
def create_stock_exports_tab(self)
```
Creates 'Stock Exports' tab for export configurations.

```python
def create_mappings_tab(self)
```
Creates 'Mappings' tab for column and courier mappings.

###### Widget Management

```python
def add_rule_widget(self, config=None)
```
Adds a new group of widgets for creating/editing a single rule.

```python
def add_condition_row(self, rule_widget_refs, config=None)
```
Adds a new row of widgets for a single condition within a rule.

```python
def add_action_row(self, rule_widget_refs, config=None)
```
Adds a new row of widgets for a single action within a rule.

```python
def add_packing_list_widget(self, config=None)
```
Adds a new group of widgets for a single packing list configuration.

```python
def add_stock_export_widget(self, config=None)
```
Adds a new group of widgets for a single stock export configuration.

```python
def add_filter_row(self, parent_widget_refs, fields, operators, config=None)
```
Adds a new row of widgets for a single filter criterion (generic helper).

```python
def add_courier_mapping_row(self, original_name="", standardized_name="")
```
Adds a new row for a single courier mapping.

###### Dynamic UI Handlers

```python
def _on_rule_condition_changed(self, condition_refs, initial_value=None)
```
Dynamically changes the rule's value widget based on field/operator selections.

```python
def _on_filter_criteria_changed(self, filter_refs, initial_value=None)
```
Dynamically changes the filter's value widget based on selections.

###### Save Method

```python
def save_settings(self)
```
Saves all settings from the UI back into the config dictionary.

**Process**:
1. Reads all UI widget values
2. Reconstructs config_data dictionary
3. Accepts dialog if successful
4. Shows error message if validation fails

---

## Module: actions_handler

**Location**: `gui/actions_handler.py`

**Purpose**: Handles application logic triggered by user actions from the UI.

### Classes

#### `ActionsHandler(QObject)`

Handles application logic triggered by user actions.

##### Signals

```python
data_changed = Signal()
```
Emitted whenever the main analysis DataFrame is modified.

##### Attributes

- `mw` (MainWindow): Reference to main window instance
- `log` (logging.Logger): Logger for this class

##### Methods

###### `__init__(self, main_window)`

Initializes the ActionsHandler.

###### Session Management

```python
def create_new_session(self)
```
Creates a new, unique, date-stamped session folder for output files.

**Process**:
1. Gets base output directory from config
2. Creates dated session folder with incrementing ID
3. Enables file loading buttons
4. Logs activity

###### Analysis Operations

```python
def run_analysis(self)
```
Triggers main fulfillment analysis in a background thread.

**Process**:
1. Validates session exists
2. Sets UI to busy state
3. Creates Worker for `core.run_full_analysis()`
4. Connects signals for completion/error
5. Starts worker in threadpool

```python
def on_analysis_complete(self, result)
```
Handles the 'result' signal from analysis worker thread.

**Parameters**:
- `result` (tuple): The tuple returned by `run_full_analysis()`

###### Report Generation

```python
def open_report_selection_dialog(self, report_type)
```
Opens a dialog to select and generate a pre-configured report.

**Parameters**:
- `report_type` (str): "packing_lists" or "stock_exports"

```python
def run_report_logic(self, report_type, report_config)
```
Triggers report generation in a background thread.

**Parameters**:
- `report_type` (str): Type of report to generate
- `report_config` (dict): Configuration for selected report

```python
def on_report_generation_complete(self, result)
```
Handles the 'result' signal from report generation worker.

###### Data Manipulation

```python
def toggle_fulfillment_status_for_order(self, order_number)
```
Toggles the fulfillment status of all items in a given order.

**Parameters**:
- `order_number` (str): The order number to modify

```python
def add_tag_manually(self, order_number)
```
Opens a dialog to add a manual tag to an order's 'Status_Note'.

**Parameters**:
- `order_number` (str): The order number to add tag to

```python
def remove_item_from_order(self, row_index)
```
Removes a single item (row) from the analysis DataFrame.

**Parameters**:
- `row_index` (int): The integer index of the row to remove

```python
def remove_entire_order(self, order_number)
```
Removes all rows associated with a given order number.

**Parameters**:
- `order_number` (str): The order number to remove completely

###### Dialog Management

```python
def open_settings_window(self)
```
Opens the settings dialog window for the active profile.

```python
def open_report_builder_window(self)
```
Opens the custom report builder dialog window.

###### Error Handling

```python
def on_task_error(self, error)
```
Handles the 'error' signal from any worker thread.

**Parameters**:
- `error` (tuple): Exception type, value, and traceback

---

## Module: ui_manager

**Location**: `gui/ui_manager.py`

**Purpose**: Handles the creation, layout, and state of all UI widgets.

### Classes

#### `UIManager`

Manages all UI widget creation and state updates.

##### Attributes

- `mw` (MainWindow): Reference to main window instance
- `log` (logging.Logger): Logger for this class

##### Methods

###### `__init__(self, main_window)`

Initializes the UIManager.

###### Main Creation

```python
def create_widgets(self)
```
Creates and lays out all widgets in the main window.

**Hierarchy**:
1. Session group
2. Files group
3. Actions layout (Reports + Main actions)
4. Tab view (logs, data, statistics)

###### Group Creators (Internal)

```python
def _create_session_group(self)
```
Creates the 'Session' QGroupBox.

```python
def _create_files_group(self)
```
Creates the 'Load Data' QGroupBox.

```python
def _create_reports_group(self)
```
Creates the 'Reports' QGroupBox.

```python
def _create_main_actions_group(self)
```
Creates the 'Actions' QGroupBox with main buttons.

```python
def _create_actions_layout(self)
```
Creates the QHBoxLayout containing Reports and Actions groups.

###### Tab Creators (Internal)

```python
def _create_tab_view(self)
```
Creates the main QTabWidget for displaying data and logs.

```python
def _create_activity_log_tab(self)
```
Creates the 'Activity Log' tab with QTableWidget.

```python
def _create_data_view_tab(self)
```
Creates the 'Analysis Data' tab with filter controls and table.

```python
def create_statistics_tab(self, tab_widget)
```
Creates and lays out UI elements for 'Statistics' tab.

**Parameters**:
- `tab_widget` (QWidget): Parent widget to populate

###### State Management

```python
def set_ui_busy(self, is_busy)
```
Enables or disables key UI elements based on application state.

**Parameters**:
- `is_busy` (bool): If True, disables interactive widgets

**Effects**:
- Disables/enables run analysis button
- Disables/enables report buttons (if data loaded)

```python
def update_results_table(self, data_df)
```
Populates the main results table with new data from DataFrame.

**Parameters**:
- `data_df` (pd.DataFrame): DataFrame with analysis results

**Process**:
1. Creates PandasModel from DataFrame
2. Sets up QSortFilterProxyModel
3. Configures table view
4. Resizes columns to contents

---

## Module: file_handler

**Location**: `gui/file_handler.py`

**Purpose**: Handles file selection dialogs, validation, and loading logic.

### Classes

#### `FileHandler`

Manages file I/O operations initiated by the user.

##### Attributes

- `mw` (MainWindow): Reference to main window instance
- `log` (logging.Logger): Logger for this class

##### Methods

###### `__init__(self, main_window)`

Initializes the FileHandler.

###### File Selection

```python
def select_orders_file(self)
```
Opens a file dialog for user to select orders CSV file.

**Process**:
1. Opens file dialog
2. Updates file path and label
3. Validates file headers
4. Checks if ready for analysis

```python
def select_stock_file(self)
```
Opens a file dialog for user to select stock CSV file.

**Process**:
Same as `select_orders_file()` but for stock file.

###### Validation

```python
def validate_file(self, file_type)
```
Validates that a selected CSV file contains required headers.

**Parameters**:
- `file_type` (str): "orders" or "stock"

**Process**:
1. Gets required columns from config
2. Calls `core.validate_csv_headers()`
3. Updates status label (valid/invalid)
4. Sets tooltip with details on failure

```python
def check_files_ready(self)
```
Checks if both orders and stock files are selected and valid.

**Effect**: Enables 'Run Analysis' button if both files valid.

---

## Module: report_builder_window_pyside

**Location**: `gui/report_builder_window_pyside.py`

**Purpose**: Dialog window for creating custom reports from analysis data.

### Classes

#### `ReportBuilderWindow(QDialog)`

A dialog for building custom reports with user-selected columns and filters.

##### Attributes

- `df` (pd.DataFrame): Analysis DataFrame used as source
- `column_vars` (dict): Maps column names to QCheckBox widgets

##### Methods

###### `__init__(self, dataframe, parent=None)`

Initializes the ReportBuilderWindow.

**Parameters**:
- `dataframe` (pd.DataFrame): Source DataFrame for report
- `parent` (QWidget, optional): Parent widget

**UI Structure**:
1. **Step 1**: Column selection (checkboxes for all columns)
2. **Step 2**: Optional filter (single filter with field, operator, value)
3. **Step 3**: Generate and save button

###### `generate_custom_report(self)`

Generates and saves the custom report based on user selections.

**Process**:
1. Collects selected columns
2. Applies filter if specified
3. Creates filtered DataFrame
4. Opens save dialog
5. Saves to Excel file
6. Logs activity and shows success message

**Supported Operators**:
- `==`, `!=`, `>`, `<`: Numeric/string comparison
- `contains`: String containment (case-insensitive)

---

## Module: pandas_model

**Location**: `gui/pandas_model.py`

**Purpose**: Qt model to interface a pandas DataFrame with QTableView.

### Classes

#### `PandasModel(QAbstractTableModel)`

A Qt model wrapper around a pandas DataFrame.

##### Attributes

- `_dataframe` (pd.DataFrame): Underlying pandas DataFrame
- `colors` (dict): Maps status strings to QColor objects

**Color Mapping**:
```python
{
    "Fulfillable": QColor("#2E8B57"),        # SeaGreen
    "NotFulfillable": QColor("#B22222"),     # FireBrick
    "SystemNoteHighlight": QColor("#DAA520") # GoldenRod
}
```

##### Methods

###### `__init__(self, dataframe, parent=None)`

Initializes the PandasModel.

**Parameters**:
- `dataframe` (pd.DataFrame): The pandas DataFrame to model
- `parent` (QObject, optional): Parent object

###### Qt Model Methods

```python
def rowCount(self, parent=QModelIndex())
```
Returns number of rows in the model.

```python
def columnCount(self, parent=QModelIndex())
```
Returns number of columns in the model.

```python
def data(self, index, role=Qt.ItemDataRole.DisplayRole)
```
Returns data for a given model index and role.

**Roles Handled**:
- `DisplayRole`: Text to display in cell
- `BackgroundRole`: Background color based on status/system_note

**Color Priority**:
1. System_note → GoldenRod
2. "Fulfillable" → SeaGreen
3. "Not Fulfillable" → FireBrick

```python
def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole)
```
Returns header data for given section and orientation.

###### Utility Methods

```python
def get_column_index(self, column_name)
```
Returns numerical index of a column from its string name.

**Parameters**:
- `column_name` (str): Name of the column

**Returns**: `int | None` - Column index or None if not found

```python
def set_column_order_and_visibility(self, all_columns_in_order, visible_columns)
```
Reorders and filters columns in underlying DataFrame.

**Parameters**:
- `all_columns_in_order` (list[str]): All column names in desired order
- `visible_columns` (list[str]): Columns that should remain visible

**Note**: This method seems partially obsolete as visibility is now handled by view/proxy.

---

## Module: profile_manager_dialog

**Location**: `gui/profile_manager_dialog.py`

**Purpose**: Dialog for managing settings profiles (add, rename, delete).

### Classes

#### `ProfileManagerDialog(QDialog)`

Dialog interface for profile management.

##### Attributes

- `parent` (MainWindow): Reference to main window
- `list_widget` (QListWidget): Widget displaying list of profiles

##### Methods

###### `__init__(self, parent)`

Initializes the ProfileManagerDialog.

**Parameters**:
- `parent` (MainWindow): Main window instance

**UI Structure**:
- List of profiles
- Buttons: Add New, Rename, Delete

###### `populate_profiles(self)`

Clears and repopulates the list of profiles from main config.

###### `add_profile(self)`

Handles 'Add New' button click.

**Process**:
1. Prompts for new profile name
2. Calls `parent.create_profile()` with active profile as base
3. Repopulates list
4. Switches to new profile

###### `rename_profile(self)`

Handles 'Rename' button click.

**Process**:
1. Gets selected profile
2. Prompts for new name
3. Calls `parent.rename_profile()`
4. Refreshes UI

###### `delete_profile(self)`

Handles 'Delete' button click.

**Process**:
1. Confirms deletion with user
2. Calls `parent.delete_profile()`
3. Refreshes UI

---

## Module: report_selection_dialog

**Location**: `gui/report_selection_dialog.py`

**Purpose**: Dialog that dynamically creates buttons for selecting pre-configured reports.

### Classes

#### `ReportSelectionDialog(QDialog)`

Dialog for selecting from configured reports.

##### Signals

```python
reportSelected = Signal(dict)
```
Emitted when a report button is clicked.

**Payload**: Report configuration dictionary

##### Methods

###### `__init__(self, report_type, reports_config, parent=None)`

Initializes the ReportSelectionDialog.

**Parameters**:
- `report_type` (str): Type of reports (e.g., "packing_lists")
- `reports_config` (list[dict]): List of report configurations
- `parent` (QWidget, optional): Parent widget

**UI**: Creates a button for each report in `reports_config`.

###### `on_report_button_clicked(self, report_config)`

Handles click of any report button.

**Parameters**:
- `report_config` (dict): Configuration of clicked report

**Action**: Emits `reportSelected` signal and closes dialog.

---

## Module: worker

**Location**: `gui/worker.py`

**Purpose**: Generic, reusable worker thread for background task execution.

### Classes

#### `WorkerSignals(QObject)`

Defines signals available from a running worker thread.

##### Signals

```python
finished = Signal()
```
Emitted when task is done, regardless of outcome.

```python
error = Signal(tuple)
```
Emitted when exception occurs. Carries exception info `(exctype, value, traceback)`.

```python
result = Signal(object)
```
Emitted when task completes successfully. Carries return value.

#### `Worker(QRunnable)`

A generic worker that runs a function in the background.

##### Attributes

- `fn` (callable): Function to execute in background
- `args` (tuple): Positional arguments for function
- `kwargs` (dict): Keyword arguments for function
- `signals` (WorkerSignals): Signals object

##### Methods

###### `__init__(self, fn, *args, **kwargs)`

Initializes the Worker.

**Parameters**:
- `fn` (callable): Function to execute
- `*args`: Positional arguments
- `**kwargs`: Keyword arguments

###### `run(self)`

Executes the target function in background thread.

**Process**:
1. Calls `fn(*args, **kwargs)`
2. Emits `error` signal if exception occurs
3. Emits `result` signal on success
4. Always emits `finished` signal

**Usage Example**:
```python
worker = Worker(core.run_full_analysis, stock_path, orders_path, output_dir, ";", config)
worker.signals.result.connect(self.on_analysis_complete)
worker.signals.error.connect(self.on_error)
worker.signals.finished.connect(self.on_finished)
threadpool.start(worker)
```

---

## Module: log_handler

**Location**: `gui/log_handler.py`

**Purpose**: Custom logging handler that emits Qt signals for log records.

### Classes

#### `QtLogHandler(logging.Handler, QObject)`

Bridges Python logging framework with Qt signal/slot mechanism.

##### Signals

```python
log_message_received = Signal(str)
```
Emitted with formatted log message for each record.

##### Methods

###### `__init__(self, parent=None)`

Initializes the QtLogHandler.

**Initialization Order**:
1. Initialize QObject
2. Initialize logging.Handler

###### `emit(self, record)`

Formats and emits a log record as a Qt signal.

**Parameters**:
- `record` (logging.LogRecord): Log record to process

**Process**:
1. Formats record into string
2. Emits `log_message_received` signal

**Usage Example**:
```python
log_handler = QtLogHandler()
log_handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
logging.getLogger().addHandler(log_handler)
log_handler.log_message_received.connect(text_widget.appendPlainText)
```

---

## Entry Point

### Module: gui_main

**Location**: `gui_main.py`

**Purpose**: Main entry point for the Shopify Fulfillment Tool application.

### Functions

#### `main()`

Sets up and runs the Qt application.

**Process**:
1. Checks for pytest or CI environment
2. Sets platform to 'offscreen' if in test/CI mode
3. Creates QApplication
4. Instantiates MainWindow
5. Shows window (unless in offscreen mode)
6. Starts event loop

**Environment Detection**:
- Checks `sys.modules` for pytest
- Checks `CI` environment variable
- Sets Qt platform accordingly

**Example**:
```python
if __name__ == "__main__":
    main()
```

---

## Modules Added After v1.8.6.0

The following modules were added after this document was last fully reviewed (v1.8.6.0 / 2026-01-22). Each module has inline docstrings; a full API section for each is pending a future documentation pass.

### Backend (shopify_tool/)

**profile_manager.py** — client configuration management; CRUD for client profiles, caching with 60-second TTL, file locking, automatic backups.

**session_manager.py** — session lifecycle; creates timestamped session directories, manages `session_info.json`, tracks session status.

**barcode_processor.py** — Code-128 barcode label generation; produces PNG labels and combined PDFs for thermal printers.

**barcode_history.py** — tracks barcode generation history per session.

**sequential_order.py** — manages independent sequential numbering per packing list for barcode labels.

**pdf_processor.py** — reference labels PDF processor; applies reference number overlays and sorts pages.

**reference_labels_history.py** — tracks reference label processing history.

**weight_calculator.py** — volumetric weight calculation and box assignment from configured box list; supports CSV import/export for products and boxes.

**undo_manager.py** — session-scoped undo/redo for fulfillment status changes.

**set_decoder.py** — expands product bundle SKUs into individual component SKUs.

**tag_manager.py** — tag add/remove operations on order rows.

**groups_manager.py** — client group management; organizes clients into named groups.

**sku_writeoff.py** — stock writeoff calculations for export.

**csv_utils.py** — CSV loading, delimiter detection, and encoding handling utilities.

### Frontend (gui/)

**client_sidebar.py** — collapsible client selector with group management; replaces the flat client dropdown.

**client_card.py** — individual client card widget used within the sidebar.

**session_browser_widget.py** — historical session browser tab; loads and displays past session data.

**tag_management_panel.py** — toggleable sidebar panel for per-order tag editing.

**barcode_generator_widget.py** — full UI for barcode generation; integrates with barcode_processor via background worker.

**reference_labels_widget.py** — UI for reference labels PDF processing.

**tools_widget.py** — container tab for Tools (Barcode Generator, Reference Labels).

**table_config_manager.py** — column visibility, ordering, and width persistence per client.

**theme_manager.py** — dark/light theme switching.

**order_group_delegate.py** — paints visual borders between different orders in multi-line table views.

**tag_delegate.py** — renders tag badges within table cells on top of row background colors.

**bulk_operations_toolbar.py** — toolbar for batch operations on selected analysis rows.

**wheel_ignore_combobox.py** — QComboBox subclass that ignores scroll wheel to prevent accidental value changes.

**rule_validator.py** — real-time rule condition/action validation logic.

**rule_test_dialog.py** — dialog for testing a rule against sample order data.

**background_worker.py** — extended background task support (QRunnable-based).

**groups_management_dialog.py** — dialog for managing client groups.

**client_settings_dialog.py** — per-client settings dialog.

**column_config_dialog.py** — dialog for configuring visible columns per client.

**column_mapping_widget.py** — CSV column mapping UI within settings.

**add_product_dialog.py** — dialog for manually adding a product to the analysis.

**tag_categories_dialog.py** — dialog for editing tag category definitions.

**selection_helper.py** — table row selection utilities.

**checkbox_delegate.py** — checkbox rendering delegate for table cells.

---

Document version: 1.8.9.6
Last updated: 2026-02-24
