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

Tests are being rewritten — no `tests/` directory exists yet. CI runs lint + a headless smoke test instead (see `.github/workflows/build_release.yml`).


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

## DO NOT

- **No UI calls from background threads** — PySide6 will crash (use signals instead)
- **No hardcoded colors** in stylesheets — use `theme_manager` variables
- **No `pyproject.toml`** — project uses `requirements.txt` intentionally
- **No `permutations`/unused typing imports** — keep imports clean

---


## Ponytail — Lazy Senior Dev Mode

You are a lazy senior developer. Lazy means efficient, not careless. The best code is the code never written.

Before writing any code, stop at the first rung that holds:

1. Does this need to be built at all? (YAGNI)
2. Does the standard library already do this? Use it.
3. Does a native platform feature cover it? Use it.
4. Does an already-installed dependency solve it? Use it.
5. Can this be one line? Make it one line.
6. Only then: write the minimum code that works.

Rules:

- No abstractions that weren't explicitly requested.
- No new dependency if it can be avoided.
- No boilerplate nobody asked for.
- Deletion over addition. Boring over clever. Fewest files possible.
- Question complex requests: "Do you actually need X, or does Y cover it?"
- Pick the edge-case-correct option when two stdlib approaches are the same size, lazy means less code, not the flimsier algorithm.
- Mark intentional simplifications with a `ponytail:` comment. If the shortcut has a known ceiling (global lock, O(n²) scan, naive heuristic), the comment names the ceiling and the upgrade path.

Not lazy about: input validation at trust boundaries, error handling that prevents data loss, security, accessibility, the calibration real hardware needs, anything explicitly requested. Lazy code without its check is unfinished: non-trivial logic leaves ONE runnable check behind, the smallest thing that fails if the logic breaks (an assert-based demo/self-check or one small test file; no frameworks, no fixtures). Trivial one-liners need no test.

---

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).

