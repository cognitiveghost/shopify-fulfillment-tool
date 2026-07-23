# Shopify Fulfillment Tool

**Version:** 1.9.9.1
**Status:** Active development
**Platform:** Windows 10/11/Ubuntu
**Last Updated:** 2026-07-23

---

## Overview

The Shopify Fulfillment Tool is a desktop application for warehouse order fulfillment against Shopify order exports. It loads an orders CSV and a stock CSV, simulates fulfillment against available stock, applies configurable business rules, and generates packing lists and stock writeoff exports. All data is stored on a centralized Windows file server, enabling multi-PC warehouse operations.

The application is used daily by warehouse staff to determine which orders can be shipped, covering the full data flow through warehouse operations.

---

## Architecture

Data is stored on a centralized Windows file server (`Clients/`, `Sessions/`, `Stats/`, `Logs/`), located via the `FULFILLMENT_SERVER_PATH` environment variable (defaults to the production UNC path if unset).

For the full component map, data flow, and file-server layout, query the `graphify-out/` knowledge graph (`graphify query`/`graphify explain`, see `CLAUDE.md`) rather than hand-maintained docs.

---

## Installation

Requires Python 3.14. Production use also requires network access to the file server at `\\192.168.88.101\_Fulfilment_\0UFulfilment\`.

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
python run_dev.py
```

This points `FULFILLMENT_SERVER_PATH` at a local `dev-server/` folder (created automatically) and launches the app against it.

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

Tests are being rewritten; no `tests/` suite exists yet. CI runs lint (`ruff`) and a headless smoke test (`CI=1 python run_dev.py`) — see `.github/workflows/build_release.yml`.

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
5. Run the linter before submitting: `ruff check .`
6. Use conventional commit messages: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`

---

## License

Proprietary software developed for internal warehouse operations.
