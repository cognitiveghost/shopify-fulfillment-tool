# Changelog

All notable changes to the Shopify Fulfillment Tool are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [1.8.9.6] - 2026-02-24 — Packer-tool JSON metadata expansion

Tag: [1.8.9.6](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/releases/tag/1.8.9.6)
| Commit: [27ad180](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/commit/27ad180)
| PR: [#224](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/pull/224)

- Added canonical order fields to packer-tool JSON output — order metadata in packing list JSON now follows a fixed schema consumed by the Packing Tool

---

## [1.8.9.5] - 2026-02-20 — Volumetric weight engine and Weight tab CSV import/export

Tag: [1.8.9.5](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/releases/tag/1.8.9.5)
| Commit: [d91e764](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/commit/d91e764)

Tag 1.8.9.4 points to the same commit.

- Added volumetric weight and packaging engine (`shopify_tool/weight_calculator.py`) — calculates volumetric weight per order and assigns boxes from the configured box list (PR [#220](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/pull/220))
- Added CSV import and export for the Weight tab — Products and Boxes tables support bulk editing via CSV (PR [#223](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/pull/223))

---

## [1.8.9.3] - 2026-02-15 — Statistics page redesign

Tag: [1.8.9.3](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/releases/tag/1.8.9.3)
| Commit: [75137db](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/commit/75137db)
| PR: [#221](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/pull/221)

- Changed statistics page layout to stat cards — each metric displayed as a distinct card with label and value
- Fixed window focus regression that caused the main window to lose focus after certain operations

---

## [1.8.9.2] - 2026-02-10 — Pre-release stability

Tag: [1.8.9.2](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/releases/tag/1.8.9.2)
| Commit: [3582d20](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/commit/3582d20)
| PR: [#219](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/pull/219)

Tag 1.8.9.1 points to the same commit.

- Fixed table rendering performance — reduced repaints on large datasets
- Fixed various UX issues identified during internal testing
- Test suite expanded to 660 passing tests ([6121f62](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/commit/6121f62))

---

## [1.8.9.0] - 2026-02-01 — UI optimization, dark theme, per-client CSV columns

Tag: [1.8.9.0](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/releases/tag/1.8.9.0)
| Commit: [a83d3d9](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/commit/a83d3d9)

- Added dark/black theme support, toggleable via Settings (PR [#214](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/pull/214))
- Added per-client dynamic CSV column configuration — each client defines which columns to display and use (PR [#210](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/pull/210))
- Added table customization — column visibility, ordering, and width persist per client (PR [#209](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/pull/209))
- Added split Session Setup layout — Orders and Stock setup areas separated (PR [#215](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/pull/215))
- Added bulk operations for the Analysis Results table (PR [#203](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/pull/203))
- Added courier statistics improvements (PR [#218](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/pull/218))
- Added internal tags improvements Phase 2 (PR [#212](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/pull/212))
- Fixed 11 critical bugs: undo system, tag handling, statistics, and barcode issues (PR [#213](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/pull/213))
- Fixed pandas StringDtype detection — `dtype` shows as `'str'` not `'string'` ([3b2cc03](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/commit/3b2cc03))
- Fixed pandas compatibility issues in tests and Excel export ([1a0ef2e](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/commit/1a0ef2e))

Note: PR [#216](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/pull/216) (server performance optimization) was reverted ([fd1bf83](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/commit/fd1bf83)) due to regressions.

---

## [1.8.6.3] - 2026-01-30 — Rule engine overhaul

Tag: [1.8.6.3](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/releases/tag/1.8.6.3)
| Commit: [6f39b24](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/commit/6f39b24)

- Added 10 new condition operators ([caac9ec](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/commit/caac9ec))
- Added 5 new action types ([4d8b810](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/commit/4d8b810))
- Added rule priority system — rules execute in defined order ([084e5dd](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/commit/084e5dd))
- Added real-time rule validation in settings ([9443592](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/commit/9443592))
- Added rule testing dialog with order-level field support ([6947d88](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/commit/6947d88))
- Added multi-step rules and order-level fields in conditions (PR [#211](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/pull/211))
- Extended `has_sku` order-level field to support multiple string operators ([94b40c5](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/commit/94b40c5))
- Fixed ADD_PRODUCT action using incorrect product data from stock ([8089c4a](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/commit/8089c4a))
- Fixed negative operator logic for `has_sku` — now uses `.all()` instead of `.any()` ([e0a0263](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/commit/e0a0263))
- Removed deprecated action types to simplify the rule UI ([ec3a791](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/commit/ec3a791))

---

## [1.8.6.2] - 2026-01-28 — Client sidebar, groups, profile manager fix

Tag: [1.8.6.2](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/releases/tag/1.8.6.2)
| Commit: [fe213ea](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/commit/fe213ea)

- Added collapsible client sidebar with group management — clients can be organized into named groups ([9c08a6c](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/commit/9c08a6c))
- Added groups management to ProfileManager and extended client config ([3d1b84e](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/commit/3d1b84e))
- Added UI polish and performance enhancements ([a683479](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/commit/a683479))
- Fixed ProfileManager metadata cache — changed from class-level to instance-level to prevent cross-instance contamination ([fe213ea](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/commit/fe213ea))

---

## [1.8.6.1] - 2026-01-25 — Collapsible sidebar phase 1

Tag: [1.8.6.1](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/releases/tag/1.8.6.1)
| Commit: [bf52179](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/commit/bf52179)

- Added collapsible client sidebar initial implementation
- Fixed test imports after `client_selector_widget` rename

---

## [1.8.6.0] - 2026-01-22 — Barcode Generator and stability fixes

Tag: [1.8.6.0](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/releases/tag/1.8.6.0)
| Commit: [29a7f35](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/commit/29a7f35)

Consolidation release: Barcode Generator (Feature #5), Reference Labels processor (Feature #4), and critical stability fixes.

- Added Barcode Generator — Code-128 labels for thermal printers, 68mm x 38mm, optimized for Citizen CL-E300 at 203 DPI ([a8b4360](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/commit/a8b4360)); 8 fields per label (Sequential#, Items, Country, Tag, Order#, Courier, Date, Barcode); PNG + PDF output via background QThreadPool; per-packing-list subdirectories with independent sequential numbering; new modules: `shopify_tool/barcode_processor.py`, `shopify_tool/sequential_order.py`, `gui/barcode_generator_widget.py`
- Added Reference Labels PDF Processor — reference number overlay on courier label PDFs ([4a3ff02](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/commit/4a3ff02)); CSV-based mapping; 3-step matching (PostOne ID, Tracking, Name); automatic page sorting; new modules: `shopify_tool/pdf_processor.py`, `gui/reference_labels_widget.py`
- Added subtotal field support, date-based repeat detection, NO_SKU handling ([4416125](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/commit/4416125))
- Added new dependencies: `python-barcode>=0.15.1`, `Pillow>=10.0.0`, `pypdf>=4.0.0`, `reportlab>=4.0.0`
- Fixed barcode font loading error via ImageWriter monkey patch ([39c967e](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/commit/39c967e))
- Fixed item_count to sum Quantity instead of counting rows ([5bb81d8](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/commit/5bb81d8))
- Fixed sequential numbering to be independent per packing list ([bceae1a](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/commit/bceae1a))
- Fixed JSON tags parsing in barcode data ([47766f8](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/commit/47766f8))
- Fixed Order Rules field parameter not preserved on reload ([cc37840](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/commit/cc37840))
- Fixed critical Windows file locking for configurations with 70+ sets ([ab16ba4](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/commit/ab16ba4))
- Fixed date-based repeat detection logic ([7a18afb](https://github.com/cognitiveclodfr/shopify-fulfillment-tool/commit/7a18afb))

---

## [1.8.1] - 2025-11-18 — UX improvements

- Added Tag Management Panel — toggleable sidebar for per-order tag editing; add predefined or custom tags, remove tags (`gui/tag_management_panel.py`)
- Added visual order grouping — `OrderGroupDelegate` draws borders between different orders in multi-line views (`gui/order_group_delegate.py`)
- Added detailed unfulfillable reasons — `System_note` now shows the specific SKU and stock shortage for each failed order
- Changed report success dialogs to 5-second status bar messages (non-blocking)
- Changed rule engine field discovery to dynamic — all DataFrame columns available as condition fields, not a hardcoded list
- Fixed TagDelegate rendering — tag badges now display on top of row background colors (fulfillment status visible through tags)

---

## [1.8.0] - 2025-11-17 — Performance and refactoring

- Removed all `df.iterrows()` calls in the analysis engine; replaced with vectorized `groupby` and `apply` (10-50x faster for stock check and deduction)
- Refactored `core.py::run_full_analysis()` from 422 lines (complexity 56) into 5 focused phase functions
- Refactored `analysis.py::run_analysis()` from 364 lines (complexity 42) into 7 focused phase functions
- Added `WheelIgnoreComboBox` — prevents accidental dropdown changes on scroll; applied across Settings, Reports, and Column Mapping
- Fixed critical bare `except` clause in `gui/session_browser_widget.py` — replaced with specific exception types
- Fixed 15+ broad `Exception` catches in `core.py` and `profile_manager.py` with specific types
- Tests: 55 passing (100%)

---

## [1.7.1] - 2025-11-10 — Post-migration stable release

- Added unit tests for ProfileManager, SessionManager, StatsManager
- Fixed JSON packing list copy now correctly applies `exclude_skus` (matching XLSX output)
- Cleaned repository structure; removed legacy files
- Updated requirements with accurate dependency versions

---

## [1.7.0] - 2025-11-04 — Phase 1: unified server architecture

- Added ProfileManager — multi-client configuration management on the file server
- Added SessionManager — server-based session lifecycle
- Added StatsManager — unified statistics for Shopify and Packing tools
- Added JSON export for Packing Tool integration
- Migrated from local storage to centralized file server (`\\192.168.88.101\Z_GreenDelivery\WAREHOUSE\0UFulfilment\`)
- Centralized logging under `Logs/shopify_tool/`

---

## [1.6.x] — Legacy local storage

Local storage architecture with basic order analysis, simple report generation, and manual client management. Superseded by Phase 1 server migration in v1.7.0.

---

## Version numbering

This project uses a four-part version scheme: `MAJOR.MINOR.PATCH.BUILD`. Pre-release builds carry incremental BUILD numbers before a stable MINOR is declared.
