# CLAUDE.md — Shopify Fulfillment Tool

## Project Overview
Desktop PySide6 app for warehouse order fulfillment processing against Shopify CSV exports.
Windows 10/11 only. Multi-PC warehouse use via centralized Windows file server (UNC paths).
Current version: **1.8.9.6** (pre-release).

---

## Run & Test Commands

```bash
# Run application
python gui_main.py

# Run all tests
pytest

# Run fast (skip slow/integration)
pytest -m "not slow and not integration"

# Run GUI tests only
pytest tests/gui/

# Run specific test file
pytest tests/test_rules.py -v

# Run with coverage
pytest --cov=shopify_tool --cov=gui --cov-report=term-missing

# Lint
ruff check .
ruff format .
```

---

## Architecture (3-tier MVC)

```
gui/              <- PySide6 presentation layer (widgets, dialogs, models)
shopify_tool/     <- Business logic (analysis, rules, sessions, exports)
shared/           <- Cross-layer utilities (stats_manager)
tests/            <- 660+ tests (unit, integration, gui)
```

**Key files:**
| File | Role |
|------|------|
| `gui_main.py` | Entry point |
| `gui/main_window_pyside.py` | Main window orchestrator |
| `gui/actions_handler.py` | Event handler bridge (UI → backend) |
| `gui/ui_manager.py` | Widget creation & layout |
| `gui/settings_window_pyside.py` | Per-client settings (rules, mappings, tags, etc.) |
| `shopify_tool/core.py` | Analysis pipeline orchestrator |
| `shopify_tool/analysis.py` | Stock simulation engine |
| `shopify_tool/rules.py` | Rule engine (18+ operators, 10+ action types) |
| `shopify_tool/profile_manager.py` | Per-client config manager (V2 JSON format) |
| `shopify_tool/session_manager.py` | Session lifecycle on file server |
| `shopify_tool/packing_lists.py` | Packing list generation (XLSX + JSON) |
| `shopify_tool/weight_calculator.py` | Volumetric weight & box assignment |
| `shopify_tool/barcode_processor.py` | Code-128 thermal label generation |
| `shopify_tool/pdf_processor.py` | PDF reference label processing |

---

## File Server Architecture

Production uses a centralized Windows UNC path (`FULFILLMENT_SERVER_PATH` env var):
```
\\SERVER\Share\
    Clients\{ClientName}\
        client_config.json       <- UI preferences, theme, table layout
        shopify_config.json      <- V2: rules, couriers, tags, column mappings, weights
    Sessions\{ClientName}\{YYYY-MM-DD_HH-MM}\
        orders.csv, stock.csv, analysis.csv, packing_list.xlsx, ...
    Stats\
        global_stats.json
```

Dev mode: set `FULFILLMENT_SERVER_PATH` to a local directory (see `README_DEV.md` and `scripts/setup_dev_env.py`).

---

## Config Format

Client config uses **V2 JSON format** (`shopify_config.json`). V1 → V2 migration is complete and tested.
- `column_mappings.version == 2`
- `tag_categories.version == 2`
- Automatic backup on every save (last 10 kept by profile_manager)
- File locking implemented in `profile_manager.py` for concurrent multi-PC access

---

## Threading Model

- **Main thread**: UI only — PySide6 crashes if you touch widgets from a worker
- **Background**: `QThread` workers for file I/O, analysis, loading
- Pattern: emit signals back to main thread, never mutate UI widgets from `run()`
- See `gui/background_worker.py`, `gui/worker.py`

```python
class MyWorker(QThread):
    data_loaded = Signal(object)

    def run(self):
        result = expensive_operation()
        self.data_loaded.emit(result)  # safe — crosses thread boundary via signal
```

---

## Theme System

- `gui/theme_manager.py` — dark/light theme via `get_theme_manager()`
- Always use theme variables in stylesheets — never hardcode colors
- Pattern for styled widgets:

```python
theme = get_theme_manager().get_current_theme()
widget.setStyleSheet(f"color: {theme.text_primary}; background: {theme.background};")
```

**Never use:** `#666`, `#999`, `#ccc`, `#444`, `color: gray` etc. — use `theme.text_secondary`, `theme.border`

---

## Key Patterns

### File caching (critical on slow network file servers)
```python
_cache: Dict[str, Tuple[Any, float]] = {}

def get_cached(path):
    current_mtime = os.path.getmtime(path)
    if path in _cache:
        data, cached_mtime = _cache[path]
        if cached_mtime == current_mtime:
            return data.copy()  # cache HIT
    data = load_from_disk(path)
    _cache[path] = (data.copy(), current_mtime)
    return data
```

### QTableView performance (smooth scrolling with large DataFrames)
```python
table.setUniformRowHeights(True)
table.setVerticalScrollMode(QTableView.ScrollPerPixel)
table.setHorizontalScrollMode(QTableView.ScrollPerPixel)
```

### Early exit pattern (common in backend)
```python
if not condition:
    logger.warning("...")
    return  # empty return is fine for early exit
```

---

## Version Management

Version string must be updated in **3 places simultaneously**:
1. `gui_main.py:11` — `__version__ = "X.Y.Z.W"`
2. `shopify_tool/__init__.py:7` — `__version__ = "X.Y.Z.W"`
3. `README.md:3` — `Version: X.Y.Z.W`

Also update `CHANGELOG.md` with release notes under the new version header.

---

## Testing Notes

- Tests run with `pytest` from project root
- CI/headless: `QApplication` uses `offscreen` platform automatically (detected via `"pytest" in sys.modules`)
- Test data: `tests/data/`, `data/test_input/`
- Dev server mock: `scripts/setup_dev_env.py`
- Test markers: `integration`, `slow`, `gui`, `unit`
- Python minimum: 3.10

When adding a new module, add corresponding `tests/test_<module>.py`. Aim for edge cases (empty DataFrame, missing files, network errors).

---

## DO NOT

- **No UI calls from background threads** — PySide6 will crash (use signals instead)
- **No hardcoded colors** in stylesheets — use `theme_manager` variables
- **No `pyproject.toml`** — project uses `requirements.txt` intentionally
- **No changes to `data/templates/*.XLS`** — these are locked Excel templates used by exporters
- **No removing `.gitignore` entries for `Clients/`, `Sessions/`, `Stats/`** — these are live server directories that should never be committed
- **No `permutations`/unused typing imports** — keep imports clean, run `ruff check .` before committing

---

## Untracked Maintenance Scripts (root dir)

- `fix_gray_colors.py` — one-time script to migrate hardcoded colors to theme variables in 10 GUI files (not yet run)
- `fix_imports.py` — one-time script to clean up scattered `theme_manager` imports in 4 GUI files (not yet run)

These target: `barcode_generator_widget.py`, `client_settings_dialog.py`, `column_config_dialog.py`, `column_mapping_widget.py`, `reference_labels_widget.py`, `rule_test_dialog.py`, `tag_categories_dialog.py`, `tag_management_panel.py`, `session_browser_widget.py`, `report_selection_dialog.py`

Run them and delete, or commit to `scripts/` — do not leave them in the root.
