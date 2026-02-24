# Shopify Fulfillment Tool - Functions Catalog

## Table of Contents

- [Backend Functions](#backend-functions)
  - [core.py](#corepy)
  - [analysis.py](#analysispy)
  - [rules.py](#rulespy)
  - [packing_lists.py](#packing_listspy)
  - [stock_export.py](#stock_exportpy)
  - [utils.py](#utilspy)
  - [logger_config.py](#logger_configpy)
- [Frontend Functions](#frontend-functions)
  - [Main Window](#main-window)
  - [Settings Window](#settings-window)
  - [Actions Handler](#actions-handler)
  - [UI Manager](#ui-manager)
  - [File Handler](#file-handler)
  - [Other Dialogs](#other-dialogs)
  - [Utility Classes](#utility-classes)
- [Modules Added After v1.8.6.0](#modules-added-after-v1860)

Note: this document covers modules present at v1.8.6.0. Modules added in subsequent releases are listed in the appendix at the end with brief descriptions.

---

# Backend Functions

## core.py

### Primary Functions

#### `run_full_analysis(stock_file_path, orders_file_path, output_dir_path, stock_delimiter, config)`

**Purpose**: Main orchestrator for the complete fulfillment analysis workflow.

**Location**: `shopify_tool/core.py:97`

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `stock_file_path` | str \| None | Path to stock CSV file (or None for testing) |
| `orders_file_path` | str \| None | Path to orders CSV file (or None for testing) |
| `output_dir_path` | str | Directory where output report will be saved |
| `stock_delimiter` | str | Delimiter used in stock CSV (typically ";") |
| `config` | dict | Application configuration with all settings |

**Returns**: `tuple[bool, str | None, pd.DataFrame | None, dict | None]`
- **Element 0** (bool): Success flag
- **Element 1** (str | None): Output file path on success, error message on failure
- **Element 2** (pd.DataFrame | None): Final analysis DataFrame
- **Element 3** (dict | None): Statistics dictionary

**Workflow Steps**:
1. **Data Loading** (lines 136-154):
   - Normalizes UNC paths for Windows network shares
   - Loads CSV files into pandas DataFrames
   - Or uses test DataFrames from config if provided

2. **Validation** (lines 157-161):
   - Checks for required columns using `_validate_dataframes()`
   - Returns error list if validation fails

3. **History Loading** (lines 164-171):
   - Loads fulfillment history from persistent data path
   - Creates new history if file doesn't exist

4. **Analysis Execution** (line 175):
   - Calls `analysis.run_analysis()` with stock, orders, and history

5. **Stock Alerts** (lines 179-182):
   - Applies low stock threshold from config
   - Marks items with stock below threshold

6. **Rule Engine** (lines 185-190):
   - Loads rules from config
   - Applies RuleEngine to tag/prioritize orders

7. **Excel Report Generation** (lines 193-219):
   - Creates multi-sheet Excel workbook
   - Applies formatting and highlighting
   - Adds report generation timestamp

8. **History Update** (lines 222-232):
   - Extracts newly fulfilled orders
   - Updates fulfillment history file
   - Prevents duplicate entries

**Error Handling**:
- File not found: Returns (False, error_message, None, None)
- Missing columns: Returns (False, validation_errors, None, None)
- Any exception: Caught by calling code (typically in Worker thread)

**Example Usage**:
```python
config = load_config()
success, output_path, df, stats = run_full_analysis(
    stock_file_path="/path/to/stock.csv",
    orders_file_path="/path/to/orders.csv",
    output_dir_path="/path/to/output",
    stock_delimiter=";",
    config=config
)

if success:
    print(f"Analysis complete! Report saved to: {output_path}")
    print(f"Completed orders: {stats['total_orders_completed']}")
else:
    print(f"Analysis failed: {output_path}")
```

**Testing Mode**:
When `stock_file_path` and `orders_file_path` are None, the function:
- Uses `config['test_stock_df']` and `config['test_orders_df']`
- Uses `config['test_history_df']` or creates empty history
- Skips Excel generation
- Returns (True, None, final_df, stats)

---

#### `validate_csv_headers(file_path, required_columns, delimiter=",")`

**Purpose**: Quick validation of CSV file headers without loading entire file.

**Location**: `shopify_tool/core.py:56`

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `file_path` | str | Path to the CSV file to validate |
| `required_columns` | list[str] | List of column names that must be present |
| `delimiter` | str | CSV delimiter (default: ",") |

**Returns**: `tuple[bool, list[str]]`
- **Element 0** (bool): True if all required columns present
- **Element 1** (list[str]): List of missing columns (empty if all present)

**Algorithm**:
1. Reads only first row using `pandas.read_csv(nrows=0)`
2. Extracts column names from DataFrame
3. Checks each required column
4. Returns validation result

**Error Cases**:
| Error Type | Returns |
|------------|---------|
| FileNotFoundError | `(False, ["File not found at path: {path}"])` |
| Parser Error | `(False, ["Could not parse file..."])` |
| Other Exception | `(False, ["An unexpected error occurred: {e}"])` |

**Performance**:
- **Fast**: Only reads headers, not data
- **Memory efficient**: Doesn't load entire file
- **Ideal for**: Pre-flight validation before loading large files

**Example Usage**:
```python
required_orders_cols = ["Name", "Lineitem sku", "Lineitem quantity"]
is_valid, missing = validate_csv_headers(
    file_path="orders_export.csv",
    required_columns=required_orders_cols,
    delimiter=","
)

if is_valid:
    print("File is valid, ready to load")
else:
    print(f"Missing columns: {', '.join(missing)}")
```

---

#### `create_packing_list_report(analysis_df, report_config)`

**Purpose**: Generates a single packing list report based on configuration.

**Location**: `shopify_tool/core.py:239`

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `analysis_df` | pd.DataFrame | Main analysis DataFrame with all order data |
| `report_config` | dict | Report configuration dictionary |

**Report Config Structure**:
```python
{
    "name": "DHL Express Packing List",
    "output_filename": "/path/to/output/dhl_packing.xlsx",
    "filters": [
        {
            "field": "Shipping_Provider",
            "operator": "==",
            "value": "DHL"
        },
        {
            "field": "Order_Type",
            "operator": "==",
            "value": "Multi"
        }
    ],
    "exclude_skus": ["SKU-TO-EXCLUDE", "ANOTHER-SKU"]
}
```

**Returns**: `tuple[bool, str]`
- **Element 0** (bool): Success flag
- **Element 1** (str): Success message with file path OR error description

**Process**:
1. **Directory Creation** (line 262): Creates output directory if needed
2. **Delegation** (lines 264-270): Calls `packing_lists.create_packing_list()`
3. **Error Handling**: Catches KeyError, PermissionError, and general exceptions

**Error Messages**:
- **KeyError**: "Configuration error: Missing key {key}"
- **PermissionError**: "Permission denied. Could not write report to '{filename}'"
- **General**: "Failed to create report. See logs for details."

**Example Usage**:
```python
report_cfg = {
    "name": "DHL Orders",
    "output_filename": "output/dhl_list.xlsx",
    "filters": [{"field": "Shipping_Provider", "operator": "==", "value": "DHL"}],
    "exclude_skus": []
}

success, message = create_packing_list_report(analysis_df, report_cfg)
print(message)
```

---

#### `create_stock_export_report(analysis_df, report_config)`

**Purpose**: Generates a single stock export report.

**Location**: `shopify_tool/core.py:310`

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `analysis_df` | pd.DataFrame | Main analysis DataFrame |
| `report_config` | dict | Export configuration |

**Report Config Structure**:
```python
{
    "name": "DHL Stock Export",
    "output_filename": "/path/to/output/dhl_stock.xls",
    "filters": [
        {
            "field": "Shipping_Provider",
            "operator": "==",
            "value": "DHL"
        }
    ]
}
```

**Returns**: `tuple[bool, str]`
- **Element 0** (bool): Success flag
- **Element 1** (str): Status message

**Process**:
1. Ensures output directory exists (lines 326-328)
2. Calls `stock_export.create_stock_export()` (lines 330-335)
3. Handles errors and logs appropriately

**Example Usage**:
```python
export_cfg = {
    "name": "DHL Stock",
    "output_filename": "output/dhl_stock.xls",
    "filters": [{"field": "Shipping_Provider", "operator": "==", "value": "DHL"}]
}

success, message = create_stock_export_report(analysis_df, export_cfg)
```

---

#### `get_unique_column_values(df, column_name)`

**Purpose**: Utility to extract unique values from a DataFrame column.

**Location**: `shopify_tool/core.py:290`

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `df` | pd.DataFrame | Source DataFrame |
| `column_name` | str | Name of column to extract from |

**Returns**: `list[str]`
- Sorted list of unique string-converted values
- Empty list if column doesn't exist or DataFrame is empty

**Process**:
1. Checks if DataFrame is empty or column doesn't exist
2. Drops NaN values
3. Gets unique values
4. Converts to strings
5. Sorts alphabetically
6. Returns list (returns [] on any exception)

**Example Usage**:
```python
providers = get_unique_column_values(df, "Shipping_Provider")
# Returns: ["DHL", "DPD", "PostOne"]

countries = get_unique_column_values(df, "Destination_Country")
# Returns: ["Austria", "Germany", "Switzerland"]
```

**Use Cases**:
- Populating dropdown menus in settings
- Dynamic filter value suggestions
- Data exploration

---

### Internal Helper Functions

#### `_normalize_unc_path(path)`

**Purpose**: Normalizes paths, especially UNC paths on Windows.

**Location**: `shopify_tool/core.py:15`

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `path` | str | Path to normalize |

**Returns**: `str` - Normalized path

**Notes**:
- Uses `os.path.normpath()` for consistent path formatting
- Converts `/` to `\` on Windows
- Handles UNC paths (\\server\share) correctly
- Returns input unchanged if path is None or empty

---

#### `_validate_dataframes(orders_df, stock_df, config)`

**Purpose**: Validates presence of required columns in DataFrames.

**Location**: `shopify_tool/core.py:23`

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `orders_df` | pd.DataFrame | Orders DataFrame to validate |
| `stock_df` | pd.DataFrame | Stock DataFrame to validate |
| `config` | dict | Config with 'column_mappings' |

**Returns**: `list[str]` - List of error messages (empty if validation passed)

**Configuration Structure**:
```python
{
    "column_mappings": {
        "orders_required": ["Name", "Lineitem sku", "Lineitem quantity"],
        "stock_required": ["Артикул", "Наличност"]
    }
}
```

**Error Format**:
- "Missing required column in Orders file: '{column}'"
- "Missing required column in Stock file: '{column}'"

---

## analysis.py

### Primary Analysis Function

#### `run_analysis(stock_df, orders_df, history_df, column_mappings=None, courier_mappings=None)`

**Purpose**: Core fulfillment simulation engine that determines which orders can be fulfilled.

**Location**: `shopify_tool/analysis.py:77`

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `stock_df` | pd.DataFrame | Stock levels (will be mapped using column_mappings) |
| `orders_df` | pd.DataFrame | Order line items (will be mapped using column_mappings) |
| `history_df` | pd.DataFrame | Previously fulfilled orders ('Order_Number') |
| `column_mappings` | dict \| None | Optional CSV to internal column name mappings |
| `courier_mappings` | dict \| None | Optional courier pattern to code mappings |

**Column Mappings Structure**:
```python
column_mappings = {
    "orders": {
        "Name": "Order_Number",
        "Lineitem sku": "SKU",
        "Lineitem quantity": "Quantity",
        "Shipping Method": "Shipping_Method"
    },
    "stock": {
        "Артикул": "SKU",
        "Име": "Product_Name",
        "Наличност": "Stock"
    }
}
```

**Courier Mappings Structure** (see `_generalize_shipping_method()` for details):
```python
courier_mappings = {
    "DHL": {"patterns": ["dhl", "dhl express"]},
    "FedEx": {"patterns": ["fedex", "federal express"]},
    "Econt": {"patterns": ["econt"]}
}
```

**Returns**: `tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]`
1. **final_df**: Complete analysis with all columns
2. **summary_present_df**: Aggregate of items to fulfill
3. **summary_missing_df**: Aggregate of missing items
4. **stats**: Statistics dictionary

**Algorithm Flow**:

**Phase 1: Data Cleaning (lines 78-107)**
```python
# Forward-fill order-level columns
orders_df["Name"] = orders_df["Name"].ffill()
orders_df["Shipping Method"] = orders_df["Shipping Method"].ffill()

# Rename columns to standard names
rename_map = {
    "Name": "Order_Number",
    "Lineitem sku": "SKU",
    "Lineitem quantity": "Quantity"
}

# Drop rows without SKU
orders_clean_df = orders_clean_df.dropna(subset=["SKU"])

# Clean and deduplicate stock
stock_clean_df = stock_clean_df.drop_duplicates(subset=["SKU"], keep="first")
```

**Phase 2: Order Prioritization (lines 110-116)**
```python
# Count items per order
order_item_counts = orders_clean_df.groupby("Order_Number").size()

# Sort: Multi-item orders first, then alphabetically
prioritized_orders = sort_values(
    by=["item_count", "Order_Number"],
    ascending=[False, True]  # Most items first
)
```

**Why prioritize multi-item orders?**
- Maximizes number of complete orders shipped
- Better customer satisfaction (complete orders vs partial)
- More efficient warehouse operations

**Phase 3: Fulfillment Simulation (lines 118-136)**
```python
live_stock = {sku: quantity for sku, quantity in stock_df}

for order_number in prioritized_orders:
    order_items = get_items_for_order(order_number)

    # Check if ALL items are available
    can_fulfill = True
    for item in order_items:
        if required_qty > live_stock.get(sku, 0):
            can_fulfill = False
            break

    # If yes, deduct from stock
    if can_fulfill:
        fulfillment_results[order_number] = "Fulfillable"
        for item in order_items:
            live_stock[item.SKU] -= item.Quantity
    else:
        fulfillment_results[order_number] = "Not Fulfillable"
```

**Phase 4: Final Stock Calculation (lines 138-139)**
```python
final_stock_levels = pd.Series(live_stock, name="Final_Stock")
# Final_Stock = what remains after all fulfillable orders are processed
```

**Phase 5: Data Enrichment (lines 142-156)**
```python
# Add calculated fields
final_df["Order_Type"] = np.where(item_count > 1, "Multi", "Single")
final_df["Shipping_Provider"] = final_df["Shipping Method"].apply(_generalize_shipping_method)
final_df["System_note"] = np.where(
    Order_Number.isin(history_df["Order_Number"]),
    "Repeat",
    ""
)
```

**Phase 6: Summary Generation (lines 186-206)**

**Summary_Present** (items to fulfill):
```python
present_df = final_df[final_df["Order_Fulfillment_Status"] == "Fulfillable"]
summary_present_df = present_df.groupby(["SKU", "Product_Name"])["Quantity"].sum()
# Example: {"SKU-123": 15, "SKU-456": 8}
```

**Summary_Missing** (items that blocked orders):
```python
not_fulfilled_df = final_df[status == "Not Fulfillable"]
truly_missing_df = not_fulfilled_df[Quantity > Stock]  # Only truly out-of-stock
summary_missing_df = truly_missing_df.groupby(["SKU", "Product_Name"])["Quantity"].sum()
```

**Phase 7: Statistics (line 209)**
```python
stats = recalculate_statistics(final_df)
```

**Output DataFrame Columns**:
| Column | Type | Description |
|--------|------|-------------|
| Order_Number | str | Order identifier |
| Order_Type | str | "Single" or "Multi" |
| SKU | str | Product SKU |
| Product_Name | str | Product name |
| Quantity | int | Quantity ordered |
| Stock | int | Initial stock level |
| Final_Stock | int | Stock after simulation |
| Stock_Alert | str | Low stock warning (set by core) |
| Order_Fulfillment_Status | str | "Fulfillable" or "Not Fulfillable" |
| Shipping_Provider | str | Standardized carrier |
| Destination_Country | str | For international orders |
| Shipping Method | str | Original shipping method |
| Tags | str | Order tags from Shopify |
| Notes | str | Order notes |
| System_note | str | System notes (Repeat, etc.) |
| Status_Note | str | Rule-generated notes |
| Total Price | float | Order total (if present) |

**Performance Characteristics**:
- **Time Complexity**: O(n * m) where n = orders, m = avg items per order
- **Space Complexity**: O(s + o) where s = stock rows, o = order rows
- **Optimized with**: pandas vectorized operations, dictionary lookups

---

#### `recalculate_statistics(df)`

**Purpose**: Aggregates analysis data into summary statistics.

**Location**: `shopify_tool/analysis.py:214`

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `df` | pd.DataFrame | Main analysis DataFrame with Order_Fulfillment_Status |

**Returns**: `dict`

**Output Structure**:
```python
{
    "total_orders_completed": 145,
    "total_orders_not_completed": 23,
    "total_items_to_write_off": 582,
    "total_items_not_to_write_off": 96,
    "couriers_stats": [
        {
            "courier_id": "DHL",
            "orders_assigned": 89,
            "repeated_orders_found": 5
        },
        {
            "courier_id": "DPD",
            "orders_assigned": 56,
            "repeated_orders_found": 2
        }
    ]
}
```

**Calculation Details**:

**Orders**:
```python
completed = df[df["Order_Fulfillment_Status"] == "Fulfillable"]["Order_Number"].nunique()
not_completed = df[df["Order_Fulfillment_Status"] == "Not Fulfillable"]["Order_Number"].nunique()
```

**Items**:
```python
items_to_write_off = df[status == "Fulfillable"]["Quantity"].sum()
items_not_to_write_off = df[status == "Not Fulfillable"]["Quantity"].sum()
```

**Courier Stats**:
```python
for provider in completed_orders["Shipping_Provider"].unique():
    group = completed_orders[completed_orders["Shipping_Provider"] == provider]
    courier_data = {
        "courier_id": provider,
        "orders_assigned": group["Order_Number"].nunique(),
        "repeated_orders_found": group[group["System_note"] == "Repeat"]["Order_Number"].nunique()
    }
```

**Notes**:
- Returns `None` for `couriers_stats` if no orders completed
- Fills NA values in Shipping_Provider with "Unknown"
- Uses `int()` conversion for JSON serialization compatibility

---

#### `toggle_order_fulfillment(df, order_number)`

**Purpose**: Manually overrides order fulfillment status and recalculates stock.

**Location**: `shopify_tool/analysis.py:263`

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `df` | pd.DataFrame | Main analysis DataFrame |
| `order_number` | str | Order number to toggle |

**Returns**: `tuple[bool, str | None, pd.DataFrame]`
- **Element 0** (bool): Success flag
- **Element 1** (str | None): Error message (None on success)
- **Element 2** (pd.DataFrame): Updated DataFrame

**Behavior Matrix**:
| Current Status | Action | Stock Change | Result |
|----------------|--------|--------------|---------|
| Fulfillable | Un-fulfill | +Quantity | Not Fulfillable |
| Not Fulfillable | Force-fulfill | -Quantity | Fulfillable (if stock available) |

**Algorithm**:

**Un-fulfill Case** (lines 296-306):
```python
if current_status == "Fulfillable":
    # Return stock to pool
    for each SKU in order:
        df[df["SKU"] == sku, "Final_Stock"] += quantity

    # Update status
    df[df["Order_Number"] == order_number, "Order_Fulfillment_Status"] = "Not Fulfillable"
```

**Force-fulfill Case** (lines 308-341):
```python
if current_status == "Not Fulfillable":
    # Pre-flight check
    for each SKU in order:
        if needed_qty > current_final_stock:
            return (False, "Insufficient stock for SKUs: {lacking_skus}", df)

    # If check passes, deduct stock
    for each SKU in order:
        df[df["SKU"] == sku, "Final_Stock"] -= quantity

    # Update status
    df[df["Order_Number"] == order_number, "Order_Fulfillment_Status"] = "Fulfillable"
```

**Edge Case Handling**:
- **Order not found**: Returns (False, "Order number not found.", df)
- **Insufficient stock**: Returns (False, "Cannot force fulfill. Insufficient stock...", df)
- **Unlisted SKUs**: Creates new rows with 0 initial stock (lines 333-339)

**Example Usage**:
```python
# User double-clicks order in UI
success, error, updated_df = toggle_order_fulfillment(df, "ORDER-12345")

if success:
    # Update UI with new DataFrame
    display_updated_data(updated_df)
else:
    # Show error to user
    show_error_message(error)
```

---

### Internal Helper Functions

#### `_generalize_shipping_method(method, courier_mappings=None)`

**Purpose**: Standardizes shipping method names to consistent carrier names using configurable mappings.

**Location**: `shopify_tool/analysis.py:5`

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `method` | str \| float | Raw shipping method from orders file |
| `courier_mappings` | dict \| None | Optional courier mappings configuration |

**Returns**: `str` - Standardized shipping provider name

**Courier Mappings Formats**:

The function supports two configuration formats for backward compatibility:

**New Format (Preferred)**:
```python
courier_mappings = {
    "DHL": {
        "patterns": ["dhl", "dhl express", "dhl_standard"]
    },
    "FedEx": {
        "patterns": ["fedex", "federal express"]
    },
    "Econt": {
        "patterns": ["econt"]
    }
}
```

**Legacy Format**:
```python
courier_mappings = {
    "dhl": "DHL",
    "dpd": "DPD",
    "speedy": "Speedy"
}
```

**Mapping Logic**:
```python
# Handle NaN and empty values
if pd.isna(method) or not str(method).strip():
    return "Unknown"

method_lower = str(method).lower()

# If courier_mappings provided, use dynamic mapping
if courier_mappings:
    for courier_code, mapping_data in courier_mappings.items():
        if isinstance(mapping_data, dict):
            # New format
            for pattern in mapping_data.get("patterns", []):
                if pattern.lower() in method_lower:
                    return courier_code
        else:
            # Legacy format
            if courier_code.lower() in method_lower:
                return mapping_data

# Fallback to hardcoded rules if no mappings or no match
if not courier_mappings:
    if "dhl" in method_lower:
        return "DHL"
    if "dpd" in method_lower:
        return "DPD"
    if "international shipping" in method_lower:
        return "PostOne"

# No match found - return title-cased version
return str(method).title()
```

**Examples with Dynamic Mappings**:
| Input | Courier Mappings | Output |
|-------|------------------|--------|
| "fedex overnight" | `{"FedEx": {"patterns": ["fedex"]}}` | "FedEx" |
| "econt express" | `{"Econt": {"patterns": ["econt"]}}` | "Econt" |
| "dhl express" | `{"dhl": "DHL"}` (legacy) | "DHL" |
| "custom courier" | `{}` | "Custom Courier" |
| "dhl standard" | `None` (fallback) | "DHL" |

**Examples with Fallback (No Mappings)**:
| Input | Output |
|-------|--------|
| "DHL Express 12:00" | "DHL" |
| "dpd standard" | "DPD" |
| "International Shipping" | "PostOne" |
| "local pickup" | "Local Pickup" |
| NaN | "Unknown" |
| "" | "Unknown" |

**Use Cases**:
- Grouping orders by carrier for packing lists
- Generating courier-specific statistics
- Filtering orders for specific carriers
- Supporting client-specific courier configurations
- Enabling custom courier integrations through Settings UI

---

## rules.py

### Rule Engine Class

#### `RuleEngine.__init__(rules_config)`

**Purpose**: Initializes rule engine with configuration.

**Location**: `shopify_tool/rules.py:92`

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `rules_config` | list[dict] | List of rule definitions |

**Rule Structure**:
```python
{
    "name": "High Value Orders",
    "match": "ALL",  # "ALL" (AND) or "ANY" (OR)
    "conditions": [
        {
            "field": "Total Price",
            "operator": "is greater than",
            "value": "100"
        },
        {
            "field": "Destination_Country",
            "operator": "equals",
            "value": "Germany"
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

---

#### `RuleEngine.apply(df)`

**Purpose**: Main entry point - applies all rules to DataFrame.

**Location**: `shopify_tool/rules.py:102`

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `df` | pd.DataFrame | Order data DataFrame |

**Returns**: `pd.DataFrame` - Modified DataFrame

**Algorithm**:
```python
def apply(df):
    # 1. Prepare columns
    _prepare_df_for_actions(df)

    # 2. For each rule
    for rule in self.rules:
        # Get matching rows
        matches = _get_matching_rows(df, rule)

        # Execute actions on matches
        if matches.any():
            _execute_actions(df, matches, rule["actions"])

    return df
```

**Example with Multiple Rules**:
```python
rules = [
    {
        "name": "Tag Repeat Orders",
        "match": "ALL",
        "conditions": [{"field": "System_note", "operator": "equals", "value": "Repeat"}],
        "actions": [{"type": "ADD_TAG", "value": "REPEAT_CUSTOMER"}]
    },
    {
        "name": "Flag International",
        "match": "ANY",
        "conditions": [
            {"field": "Destination_Country", "operator": "equals", "value": "Austria"},
            {"field": "Destination_Country", "operator": "equals", "value": "Switzerland"}
        ],
        "actions": [{"type": "ADD_TAG", "value": "INTERNATIONAL"}]
    }
]

engine = RuleEngine(rules)
processed_df = engine.apply(orders_df)
```

**Example with Dependent Rules (Using Priority)**:

When one rule creates data that another rule uses, set priorities to control execution order:

```python
# Scenario: Calculate total price, then tag expensive orders

rules = [
    {
        "name": "Calculate Total Price",
        "priority": 1,  # Execute FIRST
        "level": "article",
        "match": "ALL",
        "conditions": [
            {"field": "Quantity", "operator": "is greater than", "value": "0"}
        ],
        "actions": [
            {
                "type": "CALCULATE",
                "operation": "multiply",
                "field1": "Quantity",
                "field2": "Unit_Price",
                "target": "Total_Price"
            }
        ]
    },
    {
        "name": "Tag Expensive Orders",
        "priority": 2,  # Execute SECOND (after Total_Price is calculated)
        "level": "article",
        "match": "ALL",
        "conditions": [
            {"field": "Total_Price", "operator": "is greater than", "value": "100"}
        ],
        "actions": [
            {"type": "ADD_TAG", "value": "EXPENSIVE"}
        ]
    }
]

engine = RuleEngine(rules)
processed_df = engine.apply(orders_df)

# Result: Rule 1 calculates Total_Price column first,
#         then Rule 2 checks Total_Price and tags rows > 100
```

**Priority System**:
- **Lower number = higher priority = executes first** (1, 2, 3, ...)
- Rules without `priority` field get default 1000 (executed last)
- Article rules and order rules have **separate priority sequences**
- Execution order:
  1. Rule 1 (Priority 1) calculates `Total_Price` column
  2. Rule 2 (Priority 2) checks `Total_Price` and tags accordingly

Without priorities, Rule 2 might execute before Rule 1, causing the condition to fail because `Total_Price` doesn't exist yet.

---

#### `RuleEngine._prepare_df_for_actions(df)`

**Purpose**: Ensures required columns exist before applying actions.

**Location**: `shopify_tool/rules.py:133`

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `df` | pd.DataFrame | DataFrame to prepare |

**Process**:
1. Scans all rules to determine needed columns
2. Adds columns if they don't exist:
   - `Priority`: Default "Normal"
   - `_is_excluded`: Default False
   - `Status_Note`: Default ""

**Column Requirements by Action** (Active Actions Only):
| Action Type | Required Column | Default Value |
|-------------|-----------------|---------------|
| ADD_TAG | Status_Note | "" |
| ADD_ORDER_TAG | Status_Note | "" |
| ADD_INTERNAL_TAG | Internal_Tags | "[]" |
| SET_STATUS | Order_Fulfillment_Status | (existing) |

---

#### `RuleEngine._get_matching_rows(df, rule)`

**Purpose**: Evaluates rule conditions to find matching rows.

**Location**: `shopify_tool/rules.py:167`

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `df` | pd.DataFrame | DataFrame to evaluate |
| `rule` | dict | Rule configuration |

**Returns**: `pd.Series[bool]` - Boolean mask of matching rows

**Algorithm for "ALL" (AND) Logic**:
```python
condition_results = []

# Evaluate each condition
for condition in rule["conditions"]:
    field = condition["field"]
    operator = condition["operator"]
    value = condition["value"]

    # Get operator function
    op_func = globals()[OPERATOR_MAP[operator]]

    # Apply to column
    result = op_func(df[field], value)
    condition_results.append(result)

# Combine with AND
final_mask = pd.concat(condition_results, axis=1).all(axis=1)
```

**Algorithm for "ANY" (OR) Logic**:
```python
# Same as above, but:
final_mask = pd.concat(condition_results, axis=1).any(axis=1)
```

**Example**:
```python
rule = {
    "match": "ALL",
    "conditions": [
        {"field": "Order_Type", "operator": "equals", "value": "Multi"},
        {"field": "Total Price", "operator": "is greater than", "value": "50"}
    ]
}

matches = _get_matching_rows(df, rule)
# Returns: Series([False, True, True, False, ...])
```

---

#### `RuleEngine._execute_actions(df, matches, actions)`

**Purpose**: Executes actions on matching rows.

**Location**: `shopify_tool/rules.py:214`

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `df` | pd.DataFrame | DataFrame to modify (in-place) |
| `matches` | pd.Series[bool] | Boolean mask of rows to modify |
| `actions` | list[dict] | List of actions to execute |

**Action Types and Behavior**:

> **Note:** As of v1.9.0, `SET_PRIORITY`, `EXCLUDE_FROM_REPORT`, `SET_PACKAGING_TAG`, and `EXCLUDE_SKU` have been deprecated. Use `ADD_INTERNAL_TAG` for structured metadata.

**Active Action Types:**

**1. ADD_TAG**:
```python
# Appends to Status_Note column, prevents duplicates
current_notes = df.loc[matches, "Status_Note"]
new_notes = current_notes.apply(lambda note:
    note if value in note.split(", ") else f"{note}, {value}" if note else value
)
df.loc[matches, "Status_Note"] = new_notes
```

**2. ADD_ORDER_TAG**:
```python
# Appends to Status_Note (order-level only, applies to first row)
# Same behavior as ADD_TAG but used in order-level rules
current_notes = df.loc[matches, "Status_Note"]
new_notes = current_notes.apply(lambda note:
    note if value in note.split(", ") else f"{note}, {value}" if note else value
)
df.loc[matches, "Status_Note"] = new_notes
```

**3. ADD_INTERNAL_TAG** (Recommended):
```python
# Adds structured tag to Internal_Tags JSON column
from shopify_tool.tag_manager import add_tag
current_tags = df.loc[matches, "Internal_Tags"]
new_tags = current_tags.apply(lambda t: add_tag(t, value))
df.loc[matches, "Internal_Tags"] = new_tags
```

**4. SET_STATUS**:
```python
df.loc[matches, "Order_Fulfillment_Status"] = value
```

**Migration Examples:**
- `SET_PRIORITY: "High"` → `ADD_INTERNAL_TAG: "priority:high"`
- `EXCLUDE_FROM_REPORT` → `ADD_INTERNAL_TAG: "exclude_from_report"`
- `SET_PACKAGING_TAG: "BOX"` → `ADD_INTERNAL_TAG: "packaging:box"`

---

### Order-Level Field Methods

#### `RuleEngine._check_has_sku(order_df, sku_value, operator)`

**Purpose**: Check if order contains SKU matching the condition.

**Location**: `shopify_tool/rules.py:531`

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `order_df` | pd.DataFrame | DataFrame rows for single order |
| `sku_value` | str | Value to match against SKUs |
| `operator` | str | String operator (equals, starts with, contains, etc.) |

**Returns**: `bool` - True if ANY SKU in order matches condition

**Supported Operators**:
- `equals` - Exact match
- `does not equal` - Not equal
- `contains` - SKU contains substring
- `does not contain` - SKU does not contain substring
- `starts with` - SKU starts with prefix
- `ends with` - SKU ends with suffix
- `is empty` - SKU is null or empty
- `is not empty` - SKU is not null and not empty

**Algorithm**:
```python
def _check_has_sku(order_df, sku_value, operator="equals"):
    # 1. Validate inputs
    if "SKU" not in order_df.columns or not sku_value:
        return False

    # 2. Get SKU series from order
    sku_series = order_df["SKU"]

    # 3. Map operator to function
    operator_map = {
        "equals": _op_equals,
        "starts with": _op_starts_with,
        "contains": _op_contains,
        # ... other operators
    }

    # 4. Apply operator function
    op_func = operator_map[operator]
    result_series = op_func(sku_series, sku_value)

    # 5. Return True if ANY SKU matches
    return result_series.any()
```

**Examples**:

**Example 1: Exact Match**
```python
# Check if order has specific SKU
has_specific = _check_has_sku(order_df, "01-FACE-1001", "equals")
# Returns True if order contains SKU "01-FACE-1001"
```

**Example 2: Prefix Match**
```python
# Check if order has SKU starting with "01-"
has_box_sku = _check_has_sku(order_df, "01-", "starts with")
# Returns True if order contains any SKU starting with "01-"
# e.g., "01-FACE-1001", "01-ADD-5001", etc.
```

**Example 3: Substring Match**
```python
# Check if order has any mask SKU
has_mask = _check_has_sku(order_df, "02-FACE-", "contains")
# Returns True if order contains any SKU with "02-FACE-" in it
```

**Use Cases**:

**Packaging Detection**:
```python
# Rule: Orders with SKUs starting with "01-" use boxes
rules = [{
    "name": "Box Items Only",
    "level": "order",
    "conditions": [
        {"field": "has_sku", "operator": "starts with", "value": "01-"}
    ],
    "actions": [
        {"type": "ADD_ORDER_TAG", "value": "BOX_ONLY"}
    ]
}]
```

**Mixed Order Detection**:
```python
# Rule: Orders with both "01-" and "02-" SKUs are mixed
rules = [{
    "name": "Mixed Packaging",
    "level": "order",
    "match": "ALL",
    "conditions": [
        {"field": "has_sku", "operator": "starts with", "value": "01-"},
        {"field": "has_sku", "operator": "starts with", "value": "02-"}
    ],
    "actions": [
        {"type": "ADD_ORDER_TAG", "value": "MIXED"}
    ]
}]
```

**Negative Matching**:
```python
# Rule: Orders without specific SKUs
rules = [{
    "name": "No Masks",
    "level": "order",
    "conditions": [
        {"field": "has_sku", "operator": "does not contain", "value": "02-FACE-"}
    ],
    "actions": [
        {"type": "ADD_ORDER_TAG", "value": "NO_MASKS"}
    ]
}]
```

**Backward Compatibility**:
- Default operator is "equals" for existing rules
- Existing rules without operator parameter continue to work
- Unknown operators fallback to "equals" with warning log

---

### Operator Functions

All operators return `pd.Series[bool]`.

#### `_op_equals(series_val, rule_val)`

**Location**: `shopify_tool/rules.py:38`

**Returns**: `series_val == rule_val`

**Example**:
```python
result = _op_equals(df["Order_Type"], "Multi")
# Series([False, True, True, False])
```

---

#### `_op_not_equals(series_val, rule_val)`

**Location**: `shopify_tool/rules.py:43`

**Returns**: `series_val != rule_val`

---

#### `_op_contains(series_val, rule_val)`

**Location**: `shopify_tool/rules.py:48`

**Returns**: `series_val.str.contains(rule_val, case=False, na=False)`

**Features**:
- Case-insensitive
- Handles NaN values (returns False for NaN)
- Requires string column

**Example**:
```python
result = _op_contains(df["Tags"], "priority")
# Matches "Priority", "PRIORITY", "high-priority", etc.
```

---

#### `_op_not_contains(series_val, rule_val)`

**Location**: `shopify_tool/rules.py:54`

**Returns**: `~series_val.str.contains(rule_val, case=False, na=False)`

---

#### `_op_greater_than(series_val, rule_val)`

**Location**: `shopify_tool/rules.py:59`

**Returns**: `pd.to_numeric(series_val, errors="coerce") > float(rule_val)`

**Features**:
- Converts both series and value to numeric
- Invalid values become NaN (errors="coerce")
- NaN comparisons return False

---

#### `_op_less_than(series_val, rule_val)`

**Location**: `shopify_tool/rules.py:64`

**Returns**: `pd.to_numeric(series_val, errors="coerce") < float(rule_val)`

---

#### `_op_starts_with(series_val, rule_val)`

**Location**: `shopify_tool/rules.py:69`

**Returns**: `series_val.str.startswith(rule_val, na=False)`

**Example**:
```python
result = _op_starts_with(df["SKU"], "DHL-")
# Matches "DHL-123", "DHL-456", but not "123-DHL"
```

---

#### `_op_ends_with(series_val, rule_val)`

**Location**: `shopify_tool/rules.py:74`

**Returns**: `series_val.str.endswith(rule_val, na=False)`

---

#### `_op_is_empty(series_val, rule_val)`

**Location**: `shopify_tool/rules.py:79`

**Returns**: `series_val.isnull() | (series_val == "")`

**Matches**:
- NaN values
- Empty strings ""
- Does NOT match whitespace-only strings

---

#### `_op_is_not_empty(series_val, rule_val)`

**Location**: `shopify_tool/rules.py:84`

**Returns**: `series_val.notna() & (series_val != "")`

---

### New Helper Functions (v1.9.0)

#### `_parse_date_safe(date_str)`

**Purpose**: Safely parse date strings with multiple format support.

**Location**: `shopify_tool/rules.py:~150`

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `date_str` | str | Date string to parse |

**Returns**: `Optional[pd.Timestamp]` - Parsed timestamp or None if invalid

**Supported Formats**:
1. ISO format: `YYYY-MM-DD` (e.g., "2024-01-30")
2. European slash: `DD/MM/YYYY` (e.g., "30/01/2024")
3. European dot: `DD.MM.YYYY` (e.g., "30.01.2024")

**Features**:
- Tries formats sequentially
- Returns None for invalid dates
- Logs warnings for unparseable dates with `[RULE ENGINE]` prefix

**Example**:
```python
date1 = _parse_date_safe("2024-01-30")  # pd.Timestamp('2024-01-30')
date2 = _parse_date_safe("30/01/2024")  # pd.Timestamp('2024-01-30')
date3 = _parse_date_safe("invalid")     # None (logs warning)
```

---

#### `_compile_regex_safe(pattern)`

**Purpose**: Safely compile regex patterns with LRU caching for performance.

**Location**: `shopify_tool/rules.py:~190`

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `pattern` | str | Regular expression pattern |

**Returns**: `Optional[re.Pattern]` - Compiled pattern or None if invalid

**Features**:
- **LRU Cache**: `@lru_cache(maxsize=128)` to avoid recompiling patterns
- Validates pattern before compilation
- Returns None for invalid patterns
- Logs warnings for regex errors

**Example**:
```python
pattern = _compile_regex_safe(r"^SKU-\d{4}$")  # Compiled pattern
invalid = _compile_regex_safe("[invalid")       # None (logs warning)

# Cached - no recompilation on second call
pattern2 = _compile_regex_safe(r"^SKU-\d{4}$")  # Returns cached result
```

---

#### `_parse_range(range_str)`

**Purpose**: Parse range strings in "start-end" format.

**Location**: `shopify_tool/rules.py:~218`

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `range_str` | str | Range string (e.g., "10-100") |

**Returns**: `Optional[tuple[float, float]]` - (start, end) tuple or None if invalid

**Features**:
- Validates range format
- Converts to floats (supports decimals: "5.5-15.5")
- Rejects reversed ranges (e.g., "100-10")
- Logs warnings for invalid inputs

**Example**:
```python
range1 = _parse_range("10-100")     # (10.0, 100.0)
range2 = _parse_range("5.5-15.5")   # (5.5, 15.5)
range3 = _parse_range("100-10")     # None (logs warning: reversed)
range4 = _parse_range("invalid")    # None (logs warning)
```

---

### New Operator Functions (v1.9.0)

#### `_op_in_list(series_val, rule_val)`

**Purpose**: Check if series value matches any item in comma-separated list.

**Location**: `shopify_tool/rules.py:~260`

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `series_val` | pd.Series | Column values to check |
| `rule_val` | str | Comma-separated list (e.g., "DHL,PostOne,FedEx") |

**Returns**: `pd.Series[bool]` - True where value is in list

**Features**:
- Case-insensitive matching
- Automatic whitespace trimming
- Handles empty values gracefully

**Example**:
```python
result = _op_in_list(df["Courier"], "DHL, PostOne, FedEx")
# Matches "dhl", "DHL", " PostOne ", etc.
```

---

#### `_op_not_in_list(series_val, rule_val)`

**Purpose**: Check if series value does NOT match any item in list.

**Location**: `shopify_tool/rules.py:~290`

**Returns**: `pd.Series[bool]` - Inverse of `_op_in_list()`

---

#### `_op_between(series_val, rule_val)`

**Purpose**: Check if series value falls within inclusive numeric range.

**Location**: `shopify_tool/rules.py:~315`

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `series_val` | pd.Series | Column values to check |
| `rule_val` | str | Range in format "start-end" (e.g., "10-100") |

**Returns**: `pd.Series[bool]` - True where value is in [start, end]

**Features**:
- Inclusive boundaries (10 and 100 both match in "10-100")
- Tries numeric comparison first
- Falls back to string comparison for non-numeric values
- Uses `_parse_range()` helper for validation

**Example**:
```python
result = _op_between(df["Price"], "50-150")
# Matches 50, 75, 100, 150 (inclusive)
```

---

#### `_op_not_between(series_val, rule_val)`

**Purpose**: Check if series value does NOT fall within range.

**Location**: `shopify_tool/rules.py:~345`

**Returns**: `pd.Series[bool]` - Inverse of `_op_between()`

---

#### `_op_date_before(series_val, rule_val)`

**Purpose**: Check if series date is before rule date.

**Location**: `shopify_tool/rules.py:~370`

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `series_val` | pd.Series | Column with date values |
| `rule_val` | str | Date string (e.g., "2024-01-30") |

**Returns**: `pd.Series[bool]` - True where date < rule date

**Features**:
- Supports multiple date formats (uses `_parse_date_safe()`)
- Ignores time components (normalizes to midnight)
- Handles invalid dates gracefully (returns False)

**Example**:
```python
result = _op_date_before(df["Order_Date"], "2024-01-30")
# Matches dates before January 30, 2024
```

---

#### `_op_date_after(series_val, rule_val)`

**Purpose**: Check if series date is after rule date.

**Location**: `shopify_tool/rules.py:~410`

**Returns**: `pd.Series[bool]` - True where date > rule date

**Features**: Same as `_op_date_before()`

---

#### `_op_date_equals(series_val, rule_val)`

**Purpose**: Check if series date equals rule date (time ignored).

**Location**: `shopify_tool/rules.py:~450`

**Returns**: `pd.Series[bool]` - True where date == rule date

**Features**: Same as `_op_date_before()`

**Example**:
```python
result = _op_date_equals(df["Order_Date"], "30/01/2024")
# Matches "2024-01-30", "30/01/2024", "30.01.2024" (all normalized)
```

---

#### `_op_matches_regex(series_val, rule_val)`

**Purpose**: Check if series value matches regular expression pattern.

**Location**: `shopify_tool/rules.py:~520`

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `series_val` | pd.Series | Column values to check |
| `rule_val` | str | Regular expression pattern |

**Returns**: `pd.Series[bool]` - True where value matches pattern

**Features**:
- Full regex syntax support
- Uses `_compile_regex_safe()` for caching
- Invalid patterns return False (with warning)
- Vectorized with `series.str.contains()`

**Example**:
```python
# Match SKUs with format "SKU-####"
result = _op_matches_regex(df["SKU"], r"^SKU-\d{4}$")
# Matches "SKU-1234", "SKU-5678", etc.

# Match phone numbers
result = _op_matches_regex(df["Phone"], r"^\d{3}-\d{3}-\d{4}$")
# Matches "123-456-7890"
```

**Common Patterns**:
- Starts with: `^PREFIX`
- Ends with: `SUFFIX$`
- Contains digits: `\d+`
- Alphanumeric: `[A-Za-z0-9]+`
- Optional groups: `(pattern)?`

---

## packing_lists.py

#### `create_packing_list(analysis_df, output_file, report_name="Packing List", filters=None, exclude_skus=None)`

**Purpose**: Creates a formatted packing list Excel file for warehouse operations.

**Location**: `shopify_tool/packing_lists.py:9`

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `analysis_df` | pd.DataFrame | Main analysis DataFrame |
| `output_file` | str | Full path for output .xlsx file |
| `report_name` | str | Name for logging (default: "Packing List") |
| `filters` | list[dict] | Optional filter criteria |
| `exclude_skus` | list[str] | Optional SKUs to exclude |

**Process Flow**:

**1. Build Query String (lines 48-69)**:
```python
query_parts = ["Order_Fulfillment_Status == 'Fulfillable'"]

for f in filters:
    field = f["field"]
    operator = f["operator"]
    value = f["value"]

    # Handle string values
    if isinstance(value, str):
        formatted_value = repr(value)  # Adds quotes

    query_parts.append(f"`{field}` {operator} {formatted_value}")

full_query = " & ".join(query_parts)
filtered_orders = analysis_df.query(full_query)
```

**2. SKU Exclusion (lines 73-75)**:
```python
if exclude_skus:
    filtered_orders = filtered_orders[~filtered_orders["SKU"].isin(exclude_skus)]
```

**3. Sorting (lines 88-90)**:
```python
# Priority map for main carriers
provider_map = {"DHL": 0, "PostOne": 1, "DPD": 2}
filtered_orders["sort_priority"] = filtered_orders["Shipping_Provider"].map(provider_map).fillna(3)

# Sort by priority, then order number, then SKU
sorted_list = filtered_orders.sort_values(by=["sort_priority", "Order_Number", "SKU"])
```

**4. Destination Country Handling (lines 93-95)**:
```python
# Show country only on first item of each order
sorted_list["Destination_Country"] = sorted_list["Destination_Country"].where(
    ~sorted_list["Order_Number"].duplicated(), ""
)
```

**5. Excel Formatting (lines 115-186)**:

**Header Formatting**:
```python
header_format = workbook.add_format({
    "bold": True,
    "font_size": 10,
    "align": "center",
    "valign": "vcenter",
    "border": 2,
    "bg_color": "#F2F2F2"
})
```

**Border Grouping by Order**:
```python
# Detect order boundaries
order_boundaries = print_list["Order_Number"].ne(print_list["Order_Number"].shift()).cumsum()

for row_num in range(len(print_list)):
    is_top = (row_num == 0) or (boundaries[row_num] != boundaries[row_num - 1])
    is_bottom = (row_num == last) or (boundaries[row_num] != boundaries[row_num + 1])

    # Apply appropriate border style
    row_type = "full" if (is_top and is_bottom) else \
               "top" if is_top else \
               "bottom" if is_bottom else \
               "middle"

    worksheet.write(row_num + 1, col_num, value, formats[row_type])
```

**Column Width Adjustment** (lines 170-179):
```python
for col in columns:
    max_len = max(data[col].str.len().max(), len(col)) + 2

    # Special handling
    if col == "Destination_Country":
        max_len = 5  # Fixed narrow width
    elif col == "Product_Name":
        max_len = min(max_len, 45)  # Cap at 45

    worksheet.set_column(i, i, max_len)
```

**Print Settings** (lines 182-185):
```python
worksheet.set_paper(9)          # A4
worksheet.set_landscape()        # Landscape orientation
worksheet.repeat_rows(0)         # Repeat header on each page
worksheet.fit_to_pages(1, 0)    # Fit to 1 page wide
```

**Output Structure**:
```
┌──────────┬──────────────┬──────────┬─────────────────┬──────────┬────────────────┐
│ Country  │ Order_Number │   SKU    │  Product_Name   │ Quantity │   Timestamp    │
├══════════╪══════════════╪══════════╪═════════════════╪══════════╪════════════════┤
│   DE     │  #1001       │ SKU-123  │ Product A       │    2     │ DHL            │
│          │  #1001       │ SKU-456  │ Product B       │    1     │                │
├──────────┼──────────────┼──────────┼─────────────────┼──────────┼────────────────┤
│   AT     │  #1002       │ SKU-789  │ Product C       │    3     │ DHL            │
└──────────┴──────────────┴──────────┴─────────────────┴──────────┴────────────────┘
```

**Features**:
- **Visual Grouping**: Thick borders between orders
- **Efficient Picking**: Sorted by carrier → order → SKU
- **Space Optimization**: Country shown once per order
- **Print-Ready**: A4 landscape with repeated headers

---

## stock_export.py

#### `create_stock_export(analysis_df, output_file, report_name="Stock Export", filters=None)`

**Purpose**: Creates stock export file for inventory management systems.

**Location**: `shopify_tool/stock_export.py:7`

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `analysis_df` | pd.DataFrame | Main analysis DataFrame |
| `output_file` | str | Full path for output .xls file |
| `report_name` | str | Name for logging |
| `filters` | list[dict] | Optional filter criteria |

**Process Flow**:

**1. Filtering (lines 36-57)**:
```python
query_parts = ["Order_Fulfillment_Status == 'Fulfillable'"]

for f in filters:
    query_parts.append(f"`{field}` {operator} {formatted_value}")

full_query = " & ".join(query_parts)
filtered_items = analysis_df.query(full_query)
```

**2. SKU Aggregation (lines 65-66)**:
```python
sku_summary = filtered_items.groupby("SKU")["Quantity"].sum().astype(int)
sku_summary = sku_summary[sku_summary["Quantity"] > 0]
```

**3. DataFrame Creation (lines 74-79)**:
```python
export_df = pd.DataFrame({
    "Артикул": sku_summary["SKU"],
    "Наличност": sku_summary["Quantity"]
})
```

**4. Excel Generation (lines 82-108)**:

**Primary Method** (pandas/xlwt):
```python
with pd.ExcelWriter(output_file, engine="xlwt") as writer:
    export_df.to_excel(writer, index=False, sheet_name="Sheet1")
```

**Fallback Method** (direct xlwt):
```python
if "No Excel writer 'xlwt'" in str(e):
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
```

**Output Format** (.xls):
```
Артикул    | Наличност
-----------|----------
SKU-001    | 25
SKU-002    | 13
SKU-003    | 8
```

**Use Cases**:
- Courier stock file generation
- Inventory system updates
- Warehouse management imports
- ERP system integration

---

## utils.py

#### `get_persistent_data_path(filename)`

**Purpose**: Returns path to file in persistent app data directory.

**Location**: `shopify_tool/utils.py:8`

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `filename` | str | Name of file (e.g., "config.json") |

**Returns**: `str` - Full absolute path to file

**Platform-Specific Paths**:
```python
# Windows
%APPDATA%/ShopifyFulfillmentTool/{filename}
# C:/Users/Username/AppData/Roaming/ShopifyFulfillmentTool/config.json

# Linux/macOS
~/.local/share/ShopifyFulfillmentTool/{filename}
# /home/username/.local/share/ShopifyFulfillmentTool/config.json
```

**Implementation**:
```python
def get_persistent_data_path(filename):
    # Get platform-specific app data directory
    app_data_path = os.getenv("APPDATA") or os.path.expanduser("~")
    app_dir = os.path.join(app_data_path, "ShopifyFulfillmentTool")

    # Create directory if it doesn't exist
    try:
        os.makedirs(app_dir, exist_ok=True)
    except OSError as e:
        logger.error(f"Could not create AppData directory: {e}")
        app_dir = "."  # Fallback to current directory

    return os.path.join(app_dir, filename)
```

**Common Usage**:
```python
config_path = get_persistent_data_path("config.json")
history_path = get_persistent_data_path("fulfillment_history.csv")
session_path = get_persistent_data_path("session_data.pkl")
```

---

#### `resource_path(relative_path)`

**Purpose**: Gets absolute path to bundled resource (dev or PyInstaller).

**Location**: `shopify_tool/utils.py:43`

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `relative_path` | str | Path relative to app root |

**Returns**: `str` - Absolute path to resource

**Behavior**:
```python
def resource_path(relative_path):
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        # Development mode - use current directory
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)
```

**Environment Handling**:
| Environment | Base Path | Example Result |
|-------------|-----------|----------------|
| Development | `/app/project/` | `/app/project/data/templates/file.xls` |
| PyInstaller | `C:/Temp/_MEIxxx/` | `C:/Temp/_MEIxxx/data/templates/file.xls` |

**Common Usage**:
```python
# Loading bundled templates
template_path = resource_path("data/templates/packing_list.xls")

# Loading default config
config_path = resource_path("config.json")

# Loading icons
icon_path = resource_path("assets/icon.png")
```

---

## logger_config.py

#### `setup_logging()`

**Purpose**: Configures centralized logging for entire application.

**Location**: `shopify_tool/logger_config.py:6`

**Returns**: `logging.Logger` - Configured logger instance

**Configuration**:

**Logger Setup**:
```python
logger = logging.getLogger("ShopifyToolLogger")
logger.setLevel(logging.INFO)
```

**File Handler**:
```python
log_file = "logs/app_history.log"

file_handler = RotatingFileHandler(
    log_file,
    maxBytes=1024 * 1024,  # 1 MB
    backupCount=5,
    encoding="utf-8"
)
file_handler.setLevel(logging.INFO)

file_formatter = logging.Formatter(
    "%(asctime)s - %(levelname)s - %(message)s (%(filename)s:%(lineno)d)"
)
file_handler.setFormatter(file_formatter)
```

**Stream Handler** (Console):
```python
stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.INFO)

stream_formatter = logging.Formatter("%(levelname)s: %(message)s")
stream_handler.setFormatter(stream_formatter)
```

**Log Rotation**:
- Max file size: 1 MB
- Backup files: 5
- Total storage: ~6 MB

**Log Files**:
```
logs/
├── app_history.log       (current)
├── app_history.log.1     (previous)
├── app_history.log.2
├── app_history.log.3
├── app_history.log.4
└── app_history.log.5     (oldest)
```

**Format Examples**:

**File Log**:
```
2025-11-04 10:23:45 - INFO - Analysis complete (core.py:233)
2025-11-04 10:23:46 - ERROR - Missing column: SKU (core.py:47)
```

**Console Log**:
```
INFO: Analysis complete
ERROR: Missing column: SKU
```

**Usage**:
```python
from shopify_tool.logger_config import setup_logging

logger = setup_logging()
logger.info("Application started")
logger.error("An error occurred", exc_info=True)
```

---

# Frontend Functions

## Main Window

### Primary Methods

#### `MainWindow.__init__()`

**Purpose**: Initializes main application window and all subsystems.

**Location**: `gui/main_window_pyside.py:51`

**Initialization Sequence**:
```python
1. Set window properties
2. Initialize core attributes
3. Load/migrate configuration
4. Create handlers (ui_manager, file_handler, actions_handler)
5. Build UI widgets
6. Connect signals
7. Setup logging
8. Attempt session restoration
9. Update profile dropdown
```

**Key Attributes Initialized**:
```python
self.session_path = None
self.config = {}
self.active_profile_name = None
self.analysis_results_df = pd.DataFrame()
self.threadpool = QThreadPool()
self.proxy_model = QSortFilterProxyModel()
```

---

#### `MainWindow.set_active_profile(profile_name)`

**Purpose**: Switches application to a different settings profile.

**Location**: `gui/main_window_pyside.py:260`

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `profile_name` | str | Name of profile to activate |

**Process**:
```python
1. Validate profile exists
2. Update active_profile_name
3. Load profile config
4. Save config to persist choice
5. Reset analysis data
6. Refresh all UI views
```

**Side Effects**:
- Clears current analysis results
- Resets statistics
- Updates profile dropdown
- Logs profile switch

---

#### `MainWindow.filter_table()`

**Purpose**: Applies filter settings to results table.

**Location**: `gui/main_window_pyside.py:340`

**Process**:
```python
text = self.filter_input.text()
column_index = self.filter_column_selector.currentIndex()

# -1 for "All Columns", otherwise specific column
filter_column = column_index - 1

case_sensitivity = Qt.CaseSensitive if self.case_sensitive_checkbox.isChecked() \
                   else Qt.CaseInsensitive

self.proxy_model.setFilterKeyColumn(filter_column)
self.proxy_model.setFilterCaseSensitivity(case_sensitivity)
self.proxy_model.setFilterRegularExpression(text)
```

**Features**:
- Search all columns or specific column
- Case-sensitive or case-insensitive
- Regular expression support
- Real-time filtering as user types

---

#### `MainWindow.show_context_menu(pos)`

**Purpose**: Shows context menu for table row operations.

**Location**: `gui/main_window_pyside.py:448`

**Context Menu Actions**:
```python
[
    "Change Status",              # Toggle fulfillment
    "Add Tag Manually...",        # Custom tag
    "---",                        # Separator
    "Remove Item {SKU} from Order",
    "Remove Entire Order {Order_Number}",
    "---",
    "Copy Order Number",
    "Copy SKU"
]
```

---

### Session Management

#### `MainWindow.load_session()`

**Purpose**: Restores previous session from pickle file.

**Location**: `gui/main_window_pyside.py:518`

**Process**:
```python
if session_file exists:
    Ask user: "Restore previous session?"

    if yes:
        Load pickle file
        Extract:
            - analysis_results_df
            - visible_columns
        Update UI
        Log restoration

    Delete session file
```

---

#### `MainWindow.closeEvent(event)`

**Purpose**: Saves session data when application closes.

**Location**: `gui/main_window_pyside.py:499`

**Saved Data**:
```python
session_data = {
    "dataframe": self.analysis_results_df,
    "visible_columns": self.visible_columns
}

pickle.dump(session_data, file)
```

---

## Settings Window

### Dynamic Widget Creation

#### `SettingsWindow.add_rule_widget(config=None)`

**Purpose**: Creates UI for a single rule configuration.

**Location**: `gui/settings_window_pyside.py:188`

**UI Structure**:
```
┌─ Rule: "High Value Orders" ────────────────┐
│  Match: [ALL v] conditions                 │
│                                             │
│  ┌─ IF ────────────────────────────────┐  │
│  │  [Total Price v] [> v] [100    ]    │  │
│  │  [+ Add Condition]                   │  │
│  └─────────────────────────────────────┘  │
│                                             │
│  ┌─ THEN perform these actions: ────────┐ │
│  │  [ADD_TAG v] [HighValue]             │ │
│  │  [+ Add Action]                       │ │
│  └──────────────────────────────────────┘ │
│                                             │
│  [Delete Rule]                             │
└─────────────────────────────────────────────┘
```

---

#### `SettingsWindow._on_rule_condition_changed(condition_refs, initial_value=None)`

**Purpose**: Dynamically changes condition value widget based on field/operator.

**Location**: `gui/settings_window_pyside.py:304`

**Logic**:
```python
field = condition_refs["field"].currentText()
operator = condition_refs["op"].currentText()

# No value widget for these operators
if operator in ["is_empty", "is_not_empty"]:
    return

# Use dropdown if:
# - Operator is "equals" or "does not equal"
# - Field exists in analysis DataFrame
# - DataFrame is not empty
use_combobox = (
    operator in ["equals", "does not equal"]
    and field in analysis_df.columns
)

if use_combobox:
    unique_values = get_unique_column_values(analysis_df, field)
    widget = QComboBox()
    widget.addItems([""] + unique_values)
else:
    widget = QLineEdit()
    widget.setPlaceholderText("Value")
```

**Example**:
- Field: "Order_Type", Operator: "equals" → Dropdown: ["", "Single", "Multi"]
- Field: "Total Price", Operator: "is greater than" → Text input
- Field: "Notes", Operator: "is empty" → No widget

---

## Actions Handler

### Primary Action Methods

#### `ActionsHandler.create_new_session()`

**Purpose**: Creates dated session folder for output files.

**Location**: `gui/actions_handler.py:51`

**Process**:
```python
base_dir = config["paths"]["output_dir_stock"]
date_str = datetime.now().strftime("%Y-%m-%d")

session_id = 1
while True:
    session_path = f"{base_dir}/{date_str}_session_{session_id}"
    if not os.path.exists(session_path):
        break
    session_id += 1

os.makedirs(session_path)
self.mw.session_path = session_path

# Enable file loading buttons
self.mw.load_orders_btn.setEnabled(True)
self.mw.load_stock_btn.setEnabled(True)
```

**Example Sessions**:
```
output/
├── 2025-11-04_session_1/
├── 2025-11-04_session_2/
└── 2025-11-04_session_3/
```

---

#### `ActionsHandler.run_analysis()`

**Purpose**: Executes main analysis in background thread.

**Location**: `gui/actions_handler.py:78`

**Threading**:
```python
worker = Worker(
    core.run_full_analysis,
    self.mw.stock_file_path,
    self.mw.orders_file_path,
    self.mw.session_path,
    stock_delimiter,
    self.mw.active_profile_config
)

worker.signals.result.connect(self.on_analysis_complete)
worker.signals.error.connect(self.on_task_error)
worker.signals.finished.connect(lambda: self.mw.ui_manager.set_ui_busy(False))

self.mw.threadpool.start(worker)
```

---

#### `ActionsHandler.toggle_fulfillment_status_for_order(order_number)`

**Purpose**: Manually toggles order status and updates UI.

**Location**: `gui/actions_handler.py:236`

**Process**:
```python
success, error, updated_df = toggle_order_fulfillment(
    self.mw.analysis_results_df,
    order_number
)

if success:
    self.mw.analysis_results_df = updated_df
    self.data_changed.emit()  # Triggers UI refresh

    new_status = updated_df.loc[
        updated_df["Order_Number"] == order_number,
        "Order_Fulfillment_Status"
    ].iloc[0]

    self.mw.log_activity("Manual Edit", f"Order {order_number} → {new_status}")
else:
    QMessageBox.critical(self.mw, "Error", error)
```

---

## UI Manager

#### `UIManager.create_widgets()`

**Purpose**: Constructs entire UI widget hierarchy.

**Location**: `gui/ui_manager.py:37`

**Widget Hierarchy**:
```
MainWindow
└─ Central Widget
   ├─ Session Group
   │  ├─ Create New Session Button
   │  └─ Session Path Label
   │
   ├─ Files Group
   │  ├─ Load Orders Button + Path Label + Status
   │  └─ Load Stock Button + Path Label + Status
   │
   ├─ Reports Group
   │  ├─ Create Packing List
   │  ├─ Create Stock Export
   │  └─ Report Builder
   │
   ├─ Actions Group
   │  ├─ Profile Selector
   │  ├─ Run Analysis (large button)
   │  └─ Open Profile Settings
   │
   └─ Tab View
      ├─ Execution Log (QPlainTextEdit)
      ├─ Activity Log (QTableWidget)
      ├─ Analysis Data (QTableView + Filters)
      └─ Statistics (QGridLayout)
```

---

#### `UIManager.set_ui_busy(is_busy)`

**Purpose**: Manages UI state during long operations.

**Location**: `gui/ui_manager.py:250`

**State Changes**:
```python
if is_busy:
    # Disable during operation
    run_analysis_button.setEnabled(False)
    packing_list_button.setEnabled(False)
    stock_export_button.setEnabled(False)
    report_builder_button.setEnabled(False)
else:
    # Re-enable based on state
    run_analysis_button.setEnabled(True)

    is_data_loaded = not analysis_results_df.empty
    packing_list_button.setEnabled(is_data_loaded)
    stock_export_button.setEnabled(is_data_loaded)
    report_builder_button.setEnabled(is_data_loaded)
```

---

## File Handler

#### `FileHandler.validate_file(file_type)`

**Purpose**: Validates CSV headers and updates UI indicators.

**Location**: `gui/file_handler.py:61`

**Process**:
```python
# Get configuration
if file_type == "orders":
    path = self.mw.orders_file_path
    label = self.mw.orders_file_status_label
    required_cols = config["column_mappings"]["orders_required"]
    delimiter = ","
else:  # stock
    path = self.mw.stock_file_path
    label = self.mw.stock_file_status_label
    required_cols = config["column_mappings"]["stock_required"]
    delimiter = config["settings"]["stock_csv_delimiter"]

# Validate
is_valid, missing = core.validate_csv_headers(path, required_cols, delimiter)

# Update UI
if is_valid:
    label.setText("✓")
    label.setStyleSheet("color: green; font-weight: bold;")
    label.setToolTip("File is valid.")
else:
    label.setText("✗")
    label.setStyleSheet("color: red; font-weight: bold;")
    label.setToolTip(f"Missing columns: {', '.join(missing)}")
```

---

## Other Dialogs

### Report Builder Window

#### `ReportBuilderWindow.generate_custom_report()`

**Purpose**: Creates custom report with user-selected columns and filter.

**Location**: `gui/report_builder_window_pyside.py:85`

**Process**:
```python
# 1. Get selected columns
selected_columns = [col for col, checkbox in column_vars.items()
                   if checkbox.isChecked()]

# 2. Apply filter if specified
filter_col = self.filter_column_combo.currentText()
operator = self.filter_op_combo.currentText()
value = self.filter_value_edit.text()

if value:
    if operator == "==":
        filtered_df = df[df[filter_col] == value]
    elif operator == "contains":
        filtered_df = df[df[filter_col].str.contains(value, case=False)]
    # ... other operators

# 3. Select columns
report_df = filtered_df[selected_columns]

# 4. Save to Excel
save_path = QFileDialog.getSaveFileName(...)
report_df.to_excel(save_path, index=False)
```

---

## Utility Classes

### Worker (Background Task Execution)

#### `Worker.run()`

**Purpose**: Executes function in background thread with error handling.

**Location**: `gui/worker.py:53`

**Process**:
```python
@Slot()
def run(self):
    try:
        result = self.fn(*self.args, **self.kwargs)
    except Exception:
        exctype, value = sys.exc_info()[:2]
        tb = traceback.format_exc()
        self.signals.error.emit((exctype, value, tb))
    else:
        self.signals.result.emit(result)
    finally:
        self.signals.finished.emit()
```

**Signal Flow**:
```
Worker.run()
    ↓
Try execute fn()
    ↓
Success → signals.result.emit(return_value)
Failure → signals.error.emit((type, value, traceback))
    ↓
Always → signals.finished.emit()
```

---

### PandasModel (DataFrame Display)

#### `PandasModel.data(index, role)`

**Purpose**: Provides data to QTableView with custom styling.

**Location**: `gui/pandas_model.py:50`

**Role Handling**:

**DisplayRole** (Text):
```python
value = self._dataframe.iloc[row, column]
return "" if pd.isna(value) else str(value)
```

**BackgroundRole** (Row Color):
```python
# Priority: System_note > Fulfillment Status
if "System_note" in columns and value != "":
    return QColor("#DAA520")  # GoldenRod (Repeat orders)

status = row["Order_Fulfillment_Status"]
if status == "Fulfillable":
    return QColor("#2E8B57")  # SeaGreen
elif status == "Not Fulfillable":
    return QColor("#B22222")  # FireBrick
```

---

## Modules Added After v1.8.6.0

The following modules were added after this document was last fully reviewed (v1.8.6.0 / 2026-01-22). Each module has inline docstrings; detailed function entries are pending a future documentation pass.

### Backend (shopify_tool/)

**profile_manager.py** — client configuration management; CRUD for client profiles on the file server, 60-second config cache, file locking, automatic backups (last 10 per client).

**session_manager.py** — session lifecycle; creates timestamped directories, manages `session_info.json`, tracks session status.

**barcode_processor.py** — Code-128 label generation; produces 68mm x 38mm PNG labels and combined PDFs for thermal printers; key function: `generate_barcodes(df, packing_list_config, output_dir, sequential_map)`.

**barcode_history.py** — tracks barcode generation runs per session.

**sequential_order.py** — manages independent sequential numbering per packing list for barcode labels.

**pdf_processor.py** — reference labels processor; overlays reference numbers on courier PDF pages, sorts by reference; key function: `process_reference_labels(pdf_path, mapping_csv_path, output_path)`.

**reference_labels_history.py** — tracks reference label processing runs.

**weight_calculator.py** — volumetric weight calculation and box assignment from a configured box list; supports CSV import/export for product weights and box dimensions.

**undo_manager.py** — session-scoped undo/redo for order fulfillment status changes; key functions: `record_change()`, `undo()`, `redo()`.

**set_decoder.py** — expands bundle SKUs into component SKUs using the configured set decoder rules.

**tag_manager.py** — add/remove tag operations on order DataFrame rows.

**groups_manager.py** — client group management; organizes clients into named groups in the configuration.

**sku_writeoff.py** — stock writeoff calculations for stock export generation.

**csv_utils.py** — CSV loading with automatic delimiter detection and encoding handling utilities.

### Frontend (gui/)

**client_sidebar.py** — collapsible client selector with group management.

**session_browser_widget.py** — historical session browser; loads and displays past session metadata and files.

**tag_management_panel.py** — toggleable panel for per-order tag editing (add predefined or custom tags, remove tags).

**barcode_generator_widget.py** — UI for barcode generation integrated with `barcode_processor` via background worker.

**reference_labels_widget.py** — UI for reference labels PDF processing.

**tools_widget.py** — container tab that hosts Barcode Generator and Reference Labels widgets.

**table_config_manager.py** — persists column visibility, ordering, and width per client.

**theme_manager.py** — applies dark/light theme to the application.

**order_group_delegate.py** — paints visual border separators between different orders in multi-line table views.

**tag_delegate.py** — renders tag badges within table cells on top of row background colors.

**bulk_operations_toolbar.py** — toolbar for batch actions on selected analysis table rows.

**wheel_ignore_combobox.py** — `QComboBox` subclass that ignores the scroll wheel to prevent accidental value changes.

**rule_validator.py** — real-time validation of rule condition/action fields in the settings UI.

**rule_test_dialog.py** — dialog for testing a rule against a sample order.

**background_worker.py** — extended `QRunnable`-based background task support.

**column_config_dialog.py** — dialog for configuring visible columns per client.

**column_mapping_widget.py** — CSV column mapping widget within client settings.

**add_product_dialog.py** — dialog for manually adding a product row to the analysis.

**groups_management_dialog.py** — dialog for managing client groups.

**tag_categories_dialog.py** — dialog for editing tag category definitions.

**selection_helper.py** — table row selection utilities.

**checkbox_delegate.py** — checkbox rendering delegate for table cells.

---

Document version: 1.8.9.6
Last updated: 2026-02-24
