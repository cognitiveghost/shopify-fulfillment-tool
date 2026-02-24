# Shopify Fulfillment Tool - Architecture Documentation

## Table of Contents

- [Overview](#overview)
- [System Architecture](#system-architecture)
- [Technology Stack](#technology-stack)
- [Project Structure](#project-structure)
- [Data Flow](#data-flow)
- [Core Components](#core-components)
- [Design Patterns](#design-patterns)
- [Threading Model](#threading-model)
- [Server Architecture](#server-architecture)
- [Configuration Management](#configuration-management)

---

## Overview

The Shopify Fulfillment Tool is a desktop application built with Python and PySide6 (Qt for Python) that automates order fulfillment for Shopify e-commerce operations. It loads orders and stock exports as CSV files, simulates stock allocation, applies configurable business rules, and produces packing lists and stock writeoff exports.

The application follows a three-layer MVC architecture with clear separation between business logic (backend), user interface (frontend), and file server data storage.

---

## System Architecture

```text
┌─────────────────────────────────────────┐
│         Presentation Layer              │
│    (PySide6 GUI - gui/ directory)       │
│  - Main Window                          │
│  - Dialogs & Widgets                    │
│  - Event Handlers                       │
└────────────┬────────────────────────────┘
             │
             │ Qt Signals/Slots
             │
┌────────────▼────────────────────────────┐
│       Business Logic Layer              │
│  (shopify_tool/ directory)              │
│  - Core Analysis Engine                 │
│  - Rule Engine                          │
│  - Report Generators                    │
│  - Barcode & PDF Processors             │
│  - Weight Calculator                    │
└────────────┬────────────────────────────┘
             │
             │ pandas DataFrames / JSON / File I/O
             │
┌────────────▼────────────────────────────┐
│         Data Layer                      │
│  - CSV File I/O                         │
│  - Excel Report Generation              │
│  - Configuration (JSON)                 │
│  - Session Persistence (JSON)           │
│  - Windows File Server (UNC paths)      │
└─────────────────────────────────────────┘
```

---

## Technology Stack

### Core

- **Python 3.9+** — main programming language
- **PySide6 (Qt 6)** — GUI framework
- **pandas** — data manipulation and analysis
- **numpy** — numerical computations

### Data Processing

- **openpyxl** — modern Excel file creation (.xlsx)
- **xlsxwriter** — Excel file creation with advanced formatting
- **xlwt / xlrd / xlutils** — legacy Excel format support (.xls)

### Image and PDF

- **python-barcode** — Code-128 barcode generation
- **Pillow** — image processing for barcode labels
- **pypdf** — PDF reading and page manipulation
- **reportlab** — PDF generation for reference label overlays

### Development Tools

- **pytest** — testing framework
- **pytest-qt** — Qt testing utilities
- **pytest-mock** — mocking for tests
- **ruff** — code linting and formatting
- **PyInstaller** — executable packaging

### Utilities

- **python-dateutil** — date/time parsing
- **pytz** — timezone support

---

## Project Structure

```text
shopify-fulfillment-tool/
|
├── shopify_tool/               # Backend business logic
│   ├── core.py                 # Orchestration and validation
│   ├── analysis.py             # Fulfillment simulation engine
│   ├── rules.py                # Configurable rule engine
│   ├── packing_lists.py        # Packing list generation
│   ├── stock_export.py         # Stock export generation
│   ├── profile_manager.py      # Client configuration management
│   ├── session_manager.py      # Session lifecycle management
│   ├── undo_manager.py         # Session-based undo/redo
│   ├── barcode_processor.py    # Code-128 label generation
│   ├── barcode_history.py      # Barcode generation history
│   ├── sequential_order.py     # Sequential numbering per packing list
│   ├── pdf_processor.py        # Reference labels PDF processing
│   ├── reference_labels_history.py  # Reference labels history
│   ├── weight_calculator.py    # Volumetric weight and box assignment
│   ├── set_decoder.py          # Product bundle expansion
│   ├── tag_manager.py          # Tag operations
│   ├── groups_manager.py       # Client group management
│   ├── sku_writeoff.py         # Stock writeoff operations
│   ├── csv_utils.py            # CSV processing utilities
│   ├── utils.py                # General utilities
│   └── logger_config.py        # Logging configuration
|
├── gui/                        # Frontend UI components
│   ├── main_window_pyside.py   # Main application window
│   ├── ui_manager.py           # UI widget creation and layout
│   ├── actions_handler.py      # Business logic integration
│   ├── file_handler.py         # File selection and validation
│   ├── worker.py               # Background thread worker (QRunnable)
│   ├── background_worker.py    # Extended background task support
│   ├── settings_window_pyside.py    # Client settings dialog
│   ├── client_sidebar.py            # Collapsible client selector with groups
│   ├── client_card.py               # Client card widget
│   ├── session_browser_widget.py    # Historical session browser
│   ├── tag_management_panel.py      # Per-order tag editing panel
│   ├── barcode_generator_widget.py  # Barcode generation UI
│   ├── reference_labels_widget.py   # Reference labels PDF processing UI
│   ├── tools_widget.py              # Tools tab container
│   ├── table_config_manager.py      # Column visibility/ordering persistence
│   ├── theme_manager.py             # Dark/light theme management
│   ├── pandas_model.py              # Qt table model for DataFrames
│   ├── order_group_delegate.py      # Visual border between order groups
│   ├── tag_delegate.py              # Tag badge rendering in table cells
│   ├── checkbox_delegate.py         # Checkbox cell delegate
│   ├── bulk_operations_toolbar.py   # Batch operations toolbar
│   ├── selection_helper.py          # Table selection utilities
│   ├── wheel_ignore_combobox.py     # Scroll-wheel-safe combo box
│   ├── column_config_dialog.py      # Column configuration dialog
│   ├── column_mapping_widget.py     # CSV column mapping UI
│   ├── add_product_dialog.py        # Manual product addition dialog
│   ├── groups_management_dialog.py  # Client groups management
│   ├── client_settings_dialog.py    # Per-client settings
│   ├── rule_test_dialog.py          # Rule testing dialog
│   ├── rule_validator.py            # Real-time rule validation
│   ├── tag_categories_dialog.py     # Tag categories editor
│   ├── profile_manager_dialog.py    # Profile management
│   ├── report_selection_dialog.py   # Report picker
│   ├── log_handler.py               # Qt logging handler
│   └── log_viewer.py                # Log viewing widget
|
├── shared/                     # Shared utilities (cross-tool)
│   └── stats_manager.py        # Unified statistics for Shopify + Packing tools
|
├── tests/                      # Test suite (pytest)
│   ├── test_analysis.py
│   ├── test_core.py
│   ├── test_rules.py
│   ├── test_packing_lists.py
│   ├── test_stock_export.py
│   └── ...
|
├── scripts/                    # Development and setup scripts
│   ├── setup_dev_env.py        # Local mock server setup
│   ├── test_dev_env.py         # Environment validation
│   └── create_comprehensive_test_data.py
|
├── docs/                       # Documentation
│   ├── ARCHITECTURE.md         # This file
│   ├── API.md                  # API reference
│   └── FUNCTIONS.md            # Function catalog
|
├── gui_main.py                 # Application entry point
├── requirements.txt            # Production dependencies
├── requirements-dev.txt        # Development dependencies
├── pyproject.toml              # Project configuration
├── START_DEV.bat               # Development launcher (Windows)
└── README.md                   # Project overview
```

---

## Data Flow

### 1. Setup Flow

```text
User selects client
    -> ProfileManager loads shopify_config.json + client_config.json
    -> SessionManager creates timestamped session directory
    -> User uploads Orders CSV + Stock CSV
    -> Files copied to session/input/
```

### 2. Analysis Flow

```text
Input CSV files
    |
    v
core.run_full_analysis()
    |
    v
analysis.run_analysis() <-- Fulfillment history
    |-- _clean_and_prepare_data()
    |-- _prioritize_orders()        (multi-item first)
    |-- _simulate_fulfillment()     (stock allocation)
    |-- _calculate_final_stock()
    |-- _merge_results_to_dataframe()
    |-- _generate_summary_reports()
    |
    v
rules.RuleEngine.apply() <-- Client rule configuration
    |-- Match conditions (18+ operators)
    |-- Execute actions (10+ action types)
    |
    v
Output: DataFrame + statistics
    |
    v
Save to session/analysis/ (XLSX + JSON)
```

### 3. Report Generation Flow

```text
Analysis DataFrame
    |
    v
Filter by packing list / stock export criteria
    |
    v
Apply formatting (borders, colors, print settings)
    |
    v
Generate Excel -> session/packing_lists/ or session/stock_exports/
Generate JSON  -> session/packing_lists/ (for Packing Tool)
```

### 4. Barcode Generation Flow

```text
User selects packing list configuration
    |
    v
BarcodeProcessor reads analysis DataFrame
    |
    v
Sequential numbering (sequential_order.py) -- per packing list
    |
    v
Code-128 barcode rendered per order (python-barcode + Pillow)
    |
    v
PNG labels assembled into PDF (reportlab)
    |
    v
Output: session/barcodes/{PackingListName}/
```

---

## Core Components

### Backend (shopify_tool/)

**core.py** — orchestration layer

- Entry point for all backend operations
- Coordinates file I/O, validation, analysis, and report generation
- Key functions: `run_full_analysis()`, `validate_csv_headers()`, `create_packing_list_report()`, `create_stock_export_report()`

**analysis.py** — fulfillment simulation engine

- Simulates stock allocation against orders
- Multi-item order prioritization for completion rate maximization
- Key functions: `run_analysis()`, `recalculate_statistics()`, `toggle_order_fulfillment()`

**rules.py** — rule engine

- Configurable conditions (18+ operators: equals, contains, greater_than, in_list, between, matches_regex, has_sku, etc.)
- Configurable actions (10+ types: ADD_TAG, SET_STATUS, SET_PRIORITY, ADD_PRODUCT, EXCLUDE_FROM_REPORT, etc.)
- Priority ordering, real-time validation, multi-step rules
- Order-level and line-level field support

**profile_manager.py** — client configuration

- Client profile CRUD on the file server
- Configuration caching (60-second TTL) and file locking
- Automatic backups (last 10 versions per client)
- Instance-level metadata cache to prevent cross-client contamination

**session_manager.py** — session lifecycle

- Creates timestamped session directories (`{YYYY-MM-DD_N}`)
- Manages `session_info.json` metadata
- Session status tracking (active / completed / abandoned)

**weight_calculator.py** — packaging engine

- Calculates volumetric weight per order
- Assigns boxes from a configured box list
- CSV import/export for product weights and box dimensions

**barcode_processor.py** — Code-128 label generator

- Generates 68mm x 38mm labels for Citizen CL-E300 thermal printer (203 DPI)
- 8 data fields per label; PNG + PDF output
- Sequential numbering per packing list via `sequential_order.py`

**pdf_processor.py** — reference labels processor

- Adds reference number overlays to courier label PDFs
- CSV-based mapping (PostOne ID to Reference Number)
- 3-step matching: PostOne ID, Tracking, Name
- Automatic page sorting by reference number

**undo_manager.py** — undo/redo system

- Session-scoped undo/redo for fulfillment status changes
- Diff-based history tracking

### Frontend (gui/)

**main_window_pyside.py** — main application window

- Orchestrates all tabs and delegates to specialized handlers
- Tabs: Session Setup, Analysis Results, Session Browser, Information (Statistics/Logs), Tools

**ui_manager.py** — UI widget creation and layout management

**actions_handler.py** — business logic integration; connects UI events to backend

**client_sidebar.py** — collapsible client selector with group management

**session_browser_widget.py** — historical session browser

**tag_management_panel.py** — per-order tag editing sidebar

**barcode_generator_widget.py** — barcode generation UI with background processing

**reference_labels_widget.py** — reference labels PDF processing UI

**table_config_manager.py** — column visibility, ordering, and width persistence per client

**theme_manager.py** — dark/light theme switching

**pandas_model.py** — Qt table model for pandas DataFrames; row coloring by fulfillment status

**order_group_delegate.py** — visual border separators between multi-line orders

**settings_window_pyside.py** — client settings dialog (Rules, Packing Lists, Stock Exports, Mappings, Weight tabs)

**rule_validator.py / rule_test_dialog.py** — real-time rule validation and testing

**worker.py / background_worker.py** — QRunnable-based background task execution

### Shared (shared/)

**stats_manager.py** — unified statistics tracking for Shopify Tool and Packing Tool; writes to `Stats/global_stats.json` on the file server with file locking for multi-PC concurrent access.

---

## Design Patterns

**Model-View-Controller** — pandas DataFrames as Model, PySide6 widgets as View, handler classes as Controller.

**Observer / Qt Signals-Slots** — `data_changed` and similar signals propagate state changes across components without tight coupling.

**Strategy** — rule engine operators are interchangeable strategy functions selected at runtime.

**Worker / QRunnable** — long operations (analysis, barcode generation) run in `QThreadPool` worker threads; results returned via signals.

**Facade** — `core.py` provides a simplified interface to the backend subsystems.

**Pipeline** — analysis splits into sequential phase functions; each phase transforms data for the next.

---

## Threading Model

The main (GUI) thread handles all UI updates and user interaction. Long-running operations run in `QThreadPool` worker threads:

- Analysis worker — `core.run_full_analysis()`
- Report workers — packing list and stock export generation
- Barcode worker — Code-128 label generation

Worker threads communicate back to the main thread exclusively via Qt signals (`finished`, `result`, `error`). DataFrames are not modified from multiple threads simultaneously.

---

## Server Architecture

### Centralized File Server Structure

```text
\\Server\Share\0UFulfilment\
|
├── Clients/
│   └── CLIENT_{ID}/
│       ├── client_config.json      # General settings and UI preferences
│       ├── shopify_config.json     # Rules, packing lists, couriers, column mappings
│       └── backups/                # Automatic config backups (last 10)
|
├── Sessions/
│   └── CLIENT_{ID}/
│       └── 2025-11-05_1/
│           ├── session_info.json   # Session metadata and status
│           ├── input/              # Uploaded orders and stock CSV files
│           ├── analysis/           # Analysis results (XLSX + JSON)
│           ├── packing_lists/      # Packing list reports (XLSX + JSON)
│           ├── stock_exports/      # Stock writeoff exports (XLS)
│           └── barcodes/           # Generated barcode labels (PNG + PDF)
|
├── Stats/
│   └── global_stats.json           # Cross-tool unified statistics
|
└── Logs/
    └── shopify_tool/               # Application logs
```

The server path defaults to `\\192.168.88.101\Z_GreenDelivery\WAREHOUSE\0UFulfilment\`. Setting the `FULFILLMENT_SERVER_PATH` environment variable overrides this for local development.

### Integration with Packing Tool

Both tools share the same file server. The Shopify Tool writes packing list JSON to `session/packing_lists/`; the Packing Tool reads from the same location. Both tools write to `Stats/global_stats.json` for unified statistics.

---

## Configuration Management

### shopify_config.json (V2 format)

```json
{
  "column_mappings": {
    "version": 2,
    "order_number": "Name",
    "sku": "Lineitem sku",
    "quantity": "Lineitem quantity"
  },
  "rules": [...],
  "packing_lists": [...],
  "stock_exports": [...],
  "courier_patterns": {...},
  "tag_categories": {...},
  "set_decoders": [...]
}
```

### client_config.json

```json
{
  "client_name": "...",
  "ui_settings": {
    "table_view": {...}
  }
}
```

### Config Lifecycle

1. `ProfileManager.load_shopify_config()` — reads from file server, caches for 60 seconds
2. Settings dialog edits in memory
3. `ProfileManager.save_shopify_config()` — writes with file lock, creates backup before overwrite

### Deprecated

Local config at `%APPDATA%/ShopifyFulfillmentTool/config.json` was the pre-v1.7 format. It is no longer used; all configuration is server-based since Phase 1 (v1.7.0).

---

## Error Handling

Validation occurs in three layers:

1. **Pre-validation** — CSV header check before loading full file
2. **Data validation** — required column presence after loading
3. **Type validation** — data type conversions with specific exception types

Error feedback surfaces through status bar messages, message boxes for critical errors, and detailed logs in the Information tab.

---

## Testing Strategy

Tests mirror the source structure in the `tests/` directory. Common patterns:

- `tmp_path` fixtures for isolated file operations
- Mock file server via `FULFILLMENT_SERVER_PATH` pointing to a temp directory
- In-memory DataFrames via `config["test_stock_df"]` for analysis tests
- `pytest-qt` with offscreen rendering for GUI component tests

---

## Build and Deployment

```bash
# Development
python gui_main.py

# Run tests
pytest tests/ -v

# Build executable
pyinstaller --onefile --windowed gui_main.py
```

---

Document version: 1.8.9.6
Last updated: 2026-02-24
