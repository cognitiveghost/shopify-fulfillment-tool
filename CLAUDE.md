# CLAUDE.md — Fulfilment Tool

## Project Overview
Desktop PySide6 app for warehouse order fulfillment processing against Shopify CSV exports.
Windows 10/11 only. Multi-PC warehouse use via centralized Windows file server (UNC paths). Development happens on Ubuntu Linux; production stays Windows-only.

---

## Run & Test Commands

**First thing in a fresh clone or a fresh worktree:**

```bash
./scripts/setup_venv.sh
```

Provides `.venv` (worktrees symlink the main checkout's — no re-download) and writes the
gitignored `.vscode/` config, so VS Code's F5 and Testing panel work with no manual setup.
Safe to re-run.

Note `python` is **not** on `PATH` on the Linux dev machine, and bare `python3` may resolve
to an interpreter whose `venv` produces no `pip` — always go through `.venv/bin/python` or
the `scripts/` wrappers (`run_app.sh`, `run_tests.sh`).

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

```bash
# Two-PC simulation: real Fulfilment + Packer windows as separate simulated PCs on one temp server
.venv/bin/python -m sim.run --packing-tool ../packing-tool     # all scenarios; --list to list them
```
Findings land in `sim-out/<timestamp>/report.md` (gitignored). A local folder is not an SMB share, so SMB-only
bugs (ADR 0008) are out of its reach. See `docs/superpowers/specs/2026-09-29-two-pc-simulation-harness-design.md`.

CI runs lint + this suite + a headless smoke test (see `.github/workflows/build_release.yml`).


---

## Session Resource Check

Roadmap work on this repo runs on a Claude Pro subscription — token budget is scarcer
than on Max/API plans. Before starting multi-step work (a `brainstorming`/`writing-plans`
pass, a large implementation, anything spanning many tool calls), check current usage:

```bash
claude-monitor --once --output json
```

**Don't add `--plan pro`** — it forces a hardcoded, badly-miscalibrated generic ceiling
(verified ~15-30x too conservative against Claude Code's own official in-app usage panel).
Omitting `--plan` lets `claude-monitor` auto-calibrate a `custom` limit from this account's
real historical usage instead, which tracks much closer to reality. It's still a local
estimate, not an official number — there's no offline source for Anthropic's true usage
percentage on this machine.

Key fields: `limits.five_hour.used_percentage` / `.resets_at` (rolling 5-hour window — the
binding day-to-day constraint), `status.label` (`"limit_hit"` means stop and wait for
`resets_at`). If usage is already high, prefer smaller/shorter-scoped work this session.

An unattended runner using this same check lives outside this repo at
`~/automation/claude-roadmap-runner/` (usage-gated cron dispatcher + a fixed orienting
prompt for overnight roadmap work across this repo and `packing-tool`) — see its
`prompt.md` for the stage-detection convention it uses when resuming work it left
mid-flight.

---

## Shared Module (`shared/`)

`shared/` (theme, logger, stats, file locking, atomic writes, session IDs) is **not owned by this repo**.
It's one-way synced from `../packing-tool/shared/`, the canonical source.

- **Never hand-edit files under `shared/`** — the next sync silently overwrites them.
- To change shared behavior: edit it in `packing-tool`, then run `python scripts/sync_shared.py` from this repo's root.
- `packing-tool` must exist as a sibling directory (`../packing-tool`) for the sync script to find it,
  or pass its path: `python scripts/sync_shared.py /path/to/packing-tool` (needed from a worktree,
  where the sibling default resolves to `.claude/worktrees/packing-tool` and does not exist).

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

## Releases

The git tag is the version. In the repo `shopify_tool/__init__.py` holds `__version__ = "dev"`; the release build
stamps the tag into it (`scripts/release_version.py`). Never hand-edit `__version__` or write a version into docs.
To release: Actions → Test, Build and Release → Run workflow on `main` → pick the bump. Never create a release in
the GitHub UI — nothing builds for it.

## DO NOT

- **No UI calls from background threads** — PySide6 will crash (use signals instead)
- **No hardcoded colors** in stylesheets — use `theme_manager` variables
- **No `pyproject.toml`** — project uses `requirements.txt` intentionally
- **No `permutations`/unused typing imports** — keep imports clean
- **No direct commits to `main`** — this repo is PR-only, with no exception for "trivial"
  docs-only changes. A cleanup commit that lands directly on local `main` never reaches
  `origin` and has to be un-done later (happened to `packing-tool`'s `main` — see
  `packing-tool` PR #158). Always branch + PR, even for a one-file docs change.

---

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

- **Always run `graphify update .` right after modifying code, not just "eventually"** — a stale graph returns wrong answers about `shared/` ownership and theme delegation silently, with no error. This matters even more here than in a single-repo project because `shared/` changes land via `scripts/sync_shared.py` from `packing-tool`, which graphify has no way to see unless you re-run it.

---

## Tooling

- **Use the `context7` MCP server** for PySide6/pytest/pandas API questions instead of answering from memory — library APIs drift between versions.
- **Use the `github` MCP server** for PR/issue/branch operations on this repo instead of shelling out to `gh` when a tool covers it.

---

## Agent skills

### Issue tracker

Issues live in GitHub Issues on `cognitiveghost/shopify-fulfillment-tool` (uses the `gh` CLI). See `docs/agents/issue-tracker.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.

Doc paths cited in code comments that no longer exist (shipped specs, plans, audits) are in git history:
`git log --all -- <path>`.

---

## Working on this repo as an agent

**UI work: the mockup is the brief.** When a task names an approved mockup (a path under `docs/design/` or a Claude
Design artifact URL), read it first and follow it exactly. `frontend-design` decides only what the mockup leaves free:
copy, empty and error states, focus and keyboard affordances, spacing rhythm, small window sizes. This is a PySide6
desktop app:
- a new colour, spacing or type token goes in `shared/theme.py` (via packing-tool, see below), and both themes must
  work;
- reuse `gui/components/` before adding a widget, and say which component you reused;
- web framing (hero sections, scroll reveals) does not apply.

Verify visuals by rendering: `QT_QPA_PLATFORM=offscreen` plus `widget.render(QImage)` saved to a PNG, then look at it.
A spec states which mockup it followed and every departure from it.

Gate: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`, plus `ruff check . --exclude shared`.

**Tooling on the dev VM:**
- Edits to `shared/` are blocked here: edit packing-tool, then run `sync_shared.py <path>`.
- Use `/usr/bin/git`, one plain git command per Bash call. The worktree guard refuses compound commands, `$VAR`
  paths, xargs/find -exec, and any git command chained with `;` or `&&`. `rtk git` is refused.
- Commit with `git commit -F <absolute path to a message file>`.
- Local `main` is stale: branch from, and review against, `origin/main`.
- `gh pr edit` fails (Projects classic). Use `gh api -X PATCH repos/<owner>/<repo>/pulls/N -F body=@file`.
- A worktree's `.venv` may be missing: `ln -s <main checkout>/.venv .venv`.
- The pytest-guard hook blocks Bash text containing "pytest" other than the plain run form, so write test files with
  Write/Edit.
- Production data in `~/Desktop/production info/` is read-only and never committed or quoted. Copy what you need to a
  temp dir first.

