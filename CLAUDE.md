# CLAUDE.md — Shopify Fulfillment Tool

## Project Overview
Desktop PySide6 app for warehouse order fulfillment processing against Shopify CSV exports.
Windows 10/11 only. Multi-PC warehouse use via centralized Windows file server (UNC paths). Development happens on Ubuntu Linux; production stays Windows-only.
Current version: **1.9.9.1** (pre-release).

---

## Run & Test Commands

```bash
# Run application (production server or FULFILLMENT_SERVER_PATH if set)
python gui_main.py

# Run against a local dev server (no production access needed)
python run_dev.py
```

```bash
# Run test suite
QT_QPA_PLATFORM=offscreen python -m pytest
```

CI runs lint + this suite + a headless smoke test (see `.github/workflows/build_release.yml`).


---

## Shared Module (`shared/`)

`shared/` (theme, logger, stats, file locking, atomic writes, session IDs) is **not owned by this repo**.
It's one-way synced from `../packing-tool/shared/`, the canonical source (see `packing-tool/docs/superpowers/specs/2026-07-25-shared-unification-design.md`).

- **Never hand-edit files under `shared/`** — the next sync silently overwrites them.
- To change shared behavior: edit it in `packing-tool`, then run `python scripts/sync_shared.py` from this repo's root.
- `packing-tool` must exist as a sibling directory (`../packing-tool`) for the sync script to find it.

---

## Theme System

- `gui/theme_manager.py` — thin delegate; `get_theme_manager()` still the public API
- Actual color/spacing tokens and stylesheet/palette builders live in `shared/theme.py` — see Shared Module above before editing colors
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

## DO NOT

- **No UI calls from background threads** — PySide6 will crash (use signals instead)
- **No hardcoded colors** in stylesheets — use `theme_manager` variables
- **No `pyproject.toml`** — project uses `requirements.txt` intentionally
- **No `permutations`/unused typing imports** — keep imports clean

---

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

- **Always run `graphify update .` right after modifying code, not just "eventually"** — a stale graph returns wrong answers about `shared/` ownership and theme delegation silently, with no error. This matters even more here than in a single-repo project because `shared/` changes land via `scripts/sync_shared.py` from `packing-tool`, which graphify has no way to see unless you re-run it.

---

## Tooling

- **Use the `context7` MCP server** for PySide6/pytest/pandas API questions instead of answering from memory — library APIs drift between versions.
- **Use the `github` MCP server** for PR/issue/branch operations on this repo instead of shelling out to `gh` when a tool covers it.

