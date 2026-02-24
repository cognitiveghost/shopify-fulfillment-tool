# Shopify Fulfillment Tool

**Version:** 1.8.9.6 (Pre-release)
**Status:** Active development
**Platform:** Windows 10/11
**Last Updated:** 2026-02-24

---

## Overview

The Shopify Fulfillment Tool is a desktop application for warehouse order fulfillment against Shopify order exports. It loads an orders CSV and a stock CSV, simulates fulfillment against available stock, applies configurable business rules, and generates packing lists and stock writeoff exports. All data is stored on a centralized Windows file server, enabling multi-PC warehouse operations.

The application is used daily by warehouse staff to determine which orders can be shipped, prioritize multi-item orders, tag and route orders to couriers, and produce formatted packing lists for each courier/route.

---

## Features

### Core

- Multi-client support — separate configuration and session history per client
- Session management — each analysis run creates a timestamped session directory on the file server
- Order analysis — stock simulation that prioritizes multi-item orders to maximize complete shipments
- Rule engine — configurable conditions and actions for automatic order tagging, routing, and product adjustment (18+ operators, 10+ action types, real-time validation)
- Sets decoding — automatic expansion of product bundles into component SKUs
- Manual product addition — add items on the fly with live recalculation
- Repeated orders detection — cross-session detection of repeat customers
- Undo/redo — session-based undo management for fulfillment toggles

### Reports and Exports

- Packing lists — Excel reports filtered by courier or other criteria, with JSON copies for Packing Tool integration
- Stock exports — aggregated writeoff quantities by SKU (.xlsx and .xls)
- Barcode labels — Code-128 thermal labels (68mm x 38mm, Citizen CL-E300, 203 DPI) generated as PNG and PDF
- Reference labels — PDF processing for courier label PDFs with reference number overlay and automatic page sorting

### Tools

- Weight and packaging engine — volumetric weight calculation, box assignment, CSV import/export for product weights and box dimensions
- Statistics — session and cross-session fulfillment statistics with per-courier breakdown
- Dark/light theme support

### User Interface

- Tabbed workflow: Session Setup, Analysis Results, Session Browser, Information, Tools
- Interactive analysis table with sorting, filtering, column customization, and context menu
- Collapsible client sidebar with group management
- Tag management panel for per-order tagging
- Background processing for long operations (barcode generation, analysis)

---

## Architecture

### File Server Structure

All data is stored on a centralized Windows file server. The path is configured via the `FULFILLMENT_SERVER_PATH` environment variable (or defaults to the production UNC path).

```text
\\Server\Share\0UFulfilment\
├── Clients\
│   └── CLIENT_{ID}\
│       ├── client_config.json        # General client settings and UI preferences
│       ├── shopify_config.json       # Rules, packing lists, couriers, column mappings
│       └── backups\                  # Automatic config backups (last 10 versions)
│
├── Sessions\
│   └── CLIENT_{ID}\
│       └── 2025-11-05_1\            # Timestamped session folder
│           ├── session_info.json    # Session metadata
│           ├── input\               # Uploaded orders and stock CSV files
│           ├── analysis\            # Analysis results (XLSX + JSON)
│           ├── packing_lists\       # Packing list reports (XLSX + JSON)
│           ├── stock_exports\       # Stock writeoff exports (XLS)
│           └── barcodes\            # Generated barcode labels
│
├── Stats\
│   └── global_stats.json            # Cross-tool unified statistics
│
└── Logs\
    └── shopify_tool\                # Application logs
```

### Core Components

- **ProfileManager** (`shopify_tool/profile_manager.py`) — client configuration with caching, file locking, and automatic backups
- **SessionManager** (`shopify_tool/session_manager.py`) — session lifecycle on the file server
- **StatsManager** (`shared/stats_manager.py`) — unified statistics for Shopify and Packing tools
- **Analysis Engine** (`shopify_tool/analysis.py`) — fulfillment simulation and stock allocation
- **Rule Engine** (`shopify_tool/rules.py`) — configurable conditions/actions for order processing
- **WeightCalculator** (`shopify_tool/weight_calculator.py`) — volumetric weight and box assignment
- **BarcodeProcessor** (`shopify_tool/barcode_processor.py`) — Code-128 label generation

For detailed architecture information, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## Installation

### Prerequisites

- Python 3.9+
- Windows 10/11
- Network access to the file server at `\\192.168.88.101\Z_GreenDelivery\WAREHOUSE\0UFulfilment\`

### Production Setup

```bash
git clone https://github.com/cognitiveclodfr/shopify-fulfillment-tool.git
cd shopify-fulfillment-tool
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python gui_main.py
```

The application connects to the production file server automatically if `FULFILLMENT_SERVER_PATH` is not set.

### Development Setup

For local development without access to the production server:

```bash
python scripts/setup_dev_env.py
```

This creates a local mock server structure with test client profiles and sample data.

Then set the environment variable before launching:

```cmd
# CMD
set FULFILLMENT_SERVER_PATH=D:\Dev\fulfillment-server-mock
python gui_main.py

# PowerShell
$env:FULFILLMENT_SERVER_PATH='D:\Dev\fulfillment-server-mock'
python gui_main.py
```

Or use the convenience launcher:

```cmd
START_DEV.bat
```

See [README_DEV.md](README_DEV.md) for full development setup instructions.

---

## Usage Workflow

### Basic Steps

1. **Select client** — choose a client from the sidebar; configuration loads automatically
2. **Create session** — click "Create New Session" to create a timestamped session directory on the server
3. **Load files** — upload the Shopify orders CSV and the current stock CSV
4. **Run analysis** — the engine cleans the data, prioritizes orders, simulates stock allocation, applies rules, and produces statistics; results appear in the table color-coded by status (fulfillable / not fulfillable / repeat)
5. **Generate reports** — create packing lists per courier and stock exports

### Settings

Open **Client Settings** to configure:

- **Rules** — automation rules with conditions and actions
- **Packing Lists** — courier-specific list configurations and SKU exclusions
- **Stock Exports** — export format configuration
- **Mappings** — CSV column name mappings for different data sources
- **Weight** — product weights and box dimensions (CSV import/export supported)

---

## Configuration

### Config Files

Stored on the file server per client:

- `client_config.json` — general settings, UI preferences, table layout
- `shopify_config.json` — V2 format with column mappings, courier patterns, tag categories, rules, packing list definitions, set decoders

### Required CSV Columns

**Orders file:**

```text
Name                - Order number
Lineitem sku        - Product SKU
Lineitem quantity   - Quantity ordered
Shipping Method     - Shipping method
Shipping Country    - Destination country
Tags                - Order tags
Notes               - Order notes
```

**Stock file:**

```text
Артикул            - Product SKU
Наличност          - Available quantity
```

Column names can be remapped in Client Settings → Mappings if your CSV uses different headers. Cyrillic headers are supported.

---

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=shopify_tool --cov=gui --cov-report=html

# GUI tests (offscreen mode for CI)
pytest tests/gui/ -v
```

The test suite uses pytest with pytest-qt for GUI components. Tests run in offscreen mode and do not require a display or server connection.

---

## Documentation

| Document | Description |
| -------- | ----------- |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design, data flow, component overview |
| [docs/API.md](docs/API.md) | API reference for all modules and classes |
| [docs/FUNCTIONS.md](docs/FUNCTIONS.md) | Detailed function catalog with parameters and examples |
| [README_DEV.md](README_DEV.md) | Development environment setup and workflow |

---

## Integration with Packing Tool

The Shopify Fulfillment Tool integrates with a separate Packing Tool (warehouse execution system) through the shared file server. Packing lists are exported as both XLSX and JSON. The JSON format includes order metadata fields consumed by the Packing Tool.

Both tools write to the same `Stats/global_stats.json` for unified statistics tracking.

---

## Contributing

1. Create a feature branch: `git checkout -b feature/your-feature-name`
2. Follow PEP 8 style guidelines
3. Add type hints to all new functions
4. Write tests for new functionality (target: existing coverage maintained)
5. Run the test suite and linter before submitting: `pytest tests/ -v && ruff check shopify_tool/ gui/`
6. Use conventional commit messages: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`

---

## License

Proprietary software developed for internal warehouse operations.
