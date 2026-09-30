# Fulfilment Owns `shared/` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `shopify-fulfillment-tool/shared/` the canonical source and have packing-tool pull a pinned
copy of it, reversing today's direction.

**Architecture:** This is still a copy-and-check model, now running the other way. packing-tool gets a
sync script that mirrors this repo's `shared/` and records the source commit in
`scripts/shared_synced_from.txt`. packing-tool's CI diffs its `shared/` against this repo at that
commit. The unit tests of `shared/` modules, the `shared/` lint, the edit-guard hook and every
ownership statement move to match.

**Tech Stack:** Python 3.14, stdlib (`shutil`, `subprocess`), pytest, ruff, GitHub Actions, bash (hook).

**Spec:** `docs/superpowers/specs/2026-09-30-shared-canonical-swap-design.md` (this repo). Read it first.

## Global Constraints

- Two worktrees, same branch name `dr/12-can-we-swap-shared-fodler-make-a-fulfilm`:
  - FT = `/home/gloopy/Desktop/Projects/shopify-fulfillment-tool/.claude/worktrees/dr-12` (this repo)
  - PT = `/home/gloopy/Desktop/Projects/packing-tool/.claude/worktrees/dr-12`
  Never `cd` to either main checkout.
- Git: `/usr/bin/git -C <worktree> ...`, one plain git command per Bash call, no `;`/`&&` chaining,
  no `$VAR` paths. Commit with `git commit -F <absolute path to a message file>` (write the message
  file under `/home/gloopy/.claude/jobs/<job>/tmp/` or another scratch dir). End every commit
  message with the attribution lines the session gives you.
- Tests: FT is `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q [paths]` run from FT; PT is
  `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q [paths]` run from PT. Any other form is refused by
  a hook. Write test files with Write/Edit, never with a Bash heredoc containing "pytest".
- Lint: FT `.venv/bin/ruff check .` (after Task 2 there is no `--exclude shared`); PT
  `.venv/bin/ruff check . --exclude shared` (after Task 6).
- `graphify update .` in a worktree after its code changes (the post-commit hook also does it).
- Historical files under `docs/superpowers/` and existing ADRs are records: do not edit them.
- No new dependencies.

## Review Focus

1. **The source is not a git checkout** (someone passes a plain folder or a zip extract): the sync
   must refuse with exit 1 and leave `packing-tool/shared/` untouched. It must not crash with a
   traceback, and it must not copy half the files first. Pinned by
   `test_a_source_that_is_not_a_git_checkout_is_refused` (Task 5).
2. **An untracked file in the source `shared/`** (a new module not committed yet): it would be copied
   but is absent at the pinned SHA, so CI would go red for a reason nobody can see. It must count as
   dirty. Pinned by `test_an_untracked_file_in_the_source_counts_as_dirty` (Task 5).
3. **`__pycache__` in the source** (always present after any test run): it must not be copied, and
   it must not make the source look dirty (the source's `.gitignore` covers it). Pinned in
   `test_mirrors_the_source_and_pins_its_commit` (Task 5).
4. **A file deleted or renamed upstream**: it must disappear from packing-tool's copy, not linger.
   Pinned by the stale-file assertion in `test_mirrors_the_source_and_pins_its_commit` (Task 5).
5. **A moved test that silently depended on a packing-tool autouse fixture** (QSettings isolation,
   root-logger cleanup): in FT it would pass alone and then leak into the rest of the suite. Task 3
   runs the full FT suite, not just the moved files, and Task 3 Step 5 says what to do on a failure.

---

### Task 1: Flip the edit-guard hook

**Files:**
- Modify: `/home/gloopy/.claude/hooks/shared-guard.sh` (outside both repos; the owner authorised
  this edit, question 27). It is not in git, so there is nothing to commit.

**Interfaces:**
- Produces: Edit/Write to `FT/shared/*` is allowed and Edit/Write to `PT/shared/*` is blocked. Tasks
  4 and 6 depend on this.

- [ ] **Step 1: Check that the hook blocks FT today**

Run: `echo '{"tool_input":{"file_path":"/home/gloopy/Desktop/Projects/shopify-fulfillment-tool/.claude/worktrees/dr-12/shared/README.md"}}' | /home/gloopy/.claude/hooks/shared-guard.sh; echo "exit=$?"`
Expected: a `BLOCKED by shared-guard` message and `exit=2`.

- [ ] **Step 2: Replace the file's whole contents**

```bash
#!/usr/bin/env bash
# PreToolUse(Edit|Write): packing-tool's shared/ is a synced copy of
# shopify-fulfillment-tool/shared/ (the canonical source since 2026-09-30,
# ADR 0017 there). A hand edit there is silently overwritten by the next
# sync, and CI's drift check only catches it after a PR is open.
#
# ponytail: Edit/Write only. A Bash write (sed -i, a heredoc) is not caught,
# on purpose: scripts/sync_shared.py writes there legitimately.
set -uo pipefail
p=$(jq -r '.tool_input.file_path // empty' 2>/dev/null)
case "$p" in
  */packing-tool/shared/*|*/packing-tool/.claude/worktrees/*/shared/*) ;;
  *) exit 0 ;;
esac
cat >&2 <<MSG
BLOCKED by shared-guard: $p is a synced copy — the next sync overwrites it.
Edit the same file in shopify-fulfillment-tool/shared/ (the canonical source),
then from packing-tool run: .venv/bin/python scripts/sync_shared.py [/path/to/shopify-fulfillment-tool]
(the path argument is needed from a worktree).
MSG
exit 2
```

Keep the file executable (`ls -l` shows `x`). If the Write tool reset the mode, run
`chmod +x /home/gloopy/.claude/hooks/shared-guard.sh`.

- [ ] **Step 3: Verify both directions**

Run: `echo '{"tool_input":{"file_path":"/home/gloopy/Desktop/Projects/shopify-fulfillment-tool/.claude/worktrees/dr-12/shared/README.md"}}' | /home/gloopy/.claude/hooks/shared-guard.sh; echo "exit=$?"`
Expected: no output, `exit=0`.

Run: `echo '{"tool_input":{"file_path":"/home/gloopy/Desktop/Projects/packing-tool/.claude/worktrees/dr-12/shared/README.md"}}' | /home/gloopy/.claude/hooks/shared-guard.sh; echo "exit=$?"`
Expected: `BLOCKED by shared-guard` and `exit=2`.

Run: `echo '{"tool_input":{"file_path":"/home/gloopy/Desktop/Projects/packing-tool/shared/theme.py"}}' | /home/gloopy/.claude/hooks/shared-guard.sh; echo "exit=$?"`
Expected: `exit=2`.

---

### Task 2 (FT): Lint covers `shared/`

**Files:**
- Modify: `ruff.toml` (top of file)
- Modify: `.github/workflows/build_release.yml:49-50` (the `Lint (ruff)` step)
- Modify: `CLAUDE.md` gate line (`Gate: ... ruff check . --exclude shared`)
- Modify (auto-fix): `gui/components/error_banner.py`, `gui/log_entry.py`, `gui/theme_manager.py`,
  `gui/ui_manager.py`, `shopify_tool/pdf_processor.py`

- [ ] **Step 1: See the failure you are fixing**

Run from FT: `.venv/bin/ruff check shared --output-format concise`
Expected: `shared/components/toast.py:76:45: F821 Undefined name 'Toast'` (1 error).

- [ ] **Step 2: Match packing-tool's ruff target**

At the very top of `ruff.toml`, before `# Project-wide rule decisions`, add:

```toml
# Matches CI and release builds (Python 3.14).
target-version = "py314"

```

- [ ] **Step 3: Apply the auto-fixes the new target reveals**

Run from FT: `.venv/bin/ruff check . --fix`
Expected: 7 fixes (UP037/UP045/UP017) in the five files listed above, then `All checks passed!`.
Read the diff (`/usr/bin/git -C <FT> diff --stat`). Only those five files and `ruff.toml` should change.

- [ ] **Step 4: Drop `--exclude shared` from CI and the gate**

In `.github/workflows/build_release.yml` change

```yaml
      - name: Lint (ruff)
        run: ruff check . --exclude shared
```
to
```yaml
      - name: Lint (ruff)
        # No --exclude shared: this repo owns shared/ (ADR 0017).
        run: ruff check .
```

In `CLAUDE.md` change `plus \`ruff check . --exclude shared\`.` to `plus \`ruff check .\`.`

- [ ] **Step 5: Run the gate**

Run: `.venv/bin/ruff check .` then `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: ruff clean, suite green. The auto-fixes are annotation-only, so tests must not change.

- [ ] **Step 6: Commit**

`git add ruff.toml .github/workflows/build_release.yml CLAUDE.md gui/components/error_banner.py gui/log_entry.py gui/theme_manager.py gui/ui_manager.py shopify_tool/pdf_processor.py`
(one `git -C <FT> add ...` call), then commit with the message `lint: cover shared/ (py314 target, as packing-tool)`.

---

### Task 3 (FT): The `shared/` unit tests move here

**Files:**
- Create in FT `tests/` (copied byte-for-byte from `PT/tests/`): `test_assets.py`,
  `test_brand_icon.py`, `test_components_card.py`, `test_components_confirm_dialog.py`,
  `test_components_filterbar.py`, `test_components_overflow.py`, `test_components_toast.py`,
  `test_excepthook.py`, `test_logger.py`, `test_navrail.py`, `test_shared_theme_buttons.py`,
  `test_shared_theme_widgets.py`, `test_state_panel.py`, `test_statcard.py`, `test_status_style.py`,
  `test_stats_manager.py`, `test_style_lint.py`, `test_theme_css_vars.py` (18 files)
- Replace: FT `tests/test_ui_assets.py` with `PT/tests/test_ui_assets.py` (PT's is a superset: adds
  the `toggle-off`/`toggle-on` icons and two `glyph_url` non-square tests)
- Modify: FT `tests/conftest.py` (add `import re` and `_rule_block`)

The PT copies are deleted in Task 6, not here. Until then both repos run them, which is harmless.

**Interfaces:**
- Produces: `tests/conftest.py::_rule_block(sheet: str, selector: str) -> str`, imported as
  `from conftest import _rule_block` by the two `test_shared_theme_*` files. `tests/` is not a
  package, so pytest puts `tests/` on `sys.path` and that import resolves.

- [ ] **Step 1: Copy the files**

Run from FT, one `cp` with all 19 sources:
`cp /home/gloopy/Desktop/Projects/packing-tool/.claude/worktrees/dr-12/tests/{test_assets,test_brand_icon,test_components_card,test_components_confirm_dialog,test_components_filterbar,test_components_overflow,test_components_toast,test_excepthook,test_logger,test_navrail,test_shared_theme_buttons,test_shared_theme_widgets,test_state_panel,test_statcard,test_status_style,test_stats_manager,test_style_lint,test_theme_css_vars,test_ui_assets}.py tests/`

Before copying, confirm that none of the 18 new names already exists in FT `tests/` apart from
`test_ui_assets.py` (checked on 2026-09-30: none do).

- [ ] **Step 2: Run them before the helper exists, to see the failure**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_shared_theme_buttons.py tests/test_shared_theme_widgets.py`
Expected: collection error `ImportError: cannot import name '_rule_block' from 'conftest'`.

- [ ] **Step 3: Add `_rule_block` to FT's conftest**

In FT `tests/conftest.py`, add `import re` to the stdlib import block (after `import os`). Then add
this function directly after the `os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")` line:

```python
def _rule_block(sheet: str, selector: str) -> str:
    """The text of one QSS rule, from `selector` at the start of a
    (possibly indented) line to the next `}`. Used by theme tests to assert
    on one rule without matching substrings that happen to appear elsewhere
    in the sheet.

    `selector` need only be the first entry of a comma-separated compound
    selector (e.g. "QLineEdit" matches "QLineEdit, QTextEdit {"), and a
    trailing `:` or other pseudo-state suffix on the line excludes it, so a
    plain-selector lookup does not accidentally match its own `:focus` rule.
    """
    pattern = re.compile(rf"^[ \t]*{re.escape(selector)}(?=[,\s])", re.MULTILINE)
    match = pattern.search(sheet)
    if not match:
        raise AssertionError(f"no rule block found for selector {selector!r}")
    start = match.start()
    end = sheet.index("}", start) + 1
    return sheet[start:end]
```

- [ ] **Step 4: Run the moved files**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_assets.py tests/test_brand_icon.py tests/test_components_card.py tests/test_components_confirm_dialog.py tests/test_components_filterbar.py tests/test_components_overflow.py tests/test_components_toast.py tests/test_excepthook.py tests/test_logger.py tests/test_navrail.py tests/test_shared_theme_buttons.py tests/test_shared_theme_widgets.py tests/test_state_panel.py tests/test_statcard.py tests/test_status_style.py tests/test_stats_manager.py tests/test_style_lint.py tests/test_theme_css_vars.py tests/test_ui_assets.py`
Expected: all pass.

- [ ] **Step 5: Run the whole FT suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: green.

If a moved test fails here but passed in Step 4, it is leaking state that a PT autouse fixture used
to clean up. PT has three such fixtures in `tests/conftest.py`: `_clear_fulfillment_server_path_env`,
`_isolate_qsettings` and `_reset_root_logger_handlers`. Fix the leak inside the moved test file with
a module-local fixture that copies the matching PT fixture. Do not add an FT-wide autouse fixture.
If a moved test needs a PT-only module or fixture that cannot be satisfied (for example `packing_tool.*`
or `loaded_logic`), delete it from FT, leave it in PT (Task 6 must then not delete it), and record
that with `runner <run> note`.

- [ ] **Step 6: Lint and commit**

Run `.venv/bin/ruff check .` (clean). Then `git add tests/` and commit with the message
`test: shared/ unit tests move here from packing-tool`.

---

### Task 4 (FT): This repo becomes canonical (script, CI, words, ADR)

**Files:**
- Delete: `scripts/sync_shared.py`
- Modify: `.github/workflows/build_release.yml` (delete the `shared-sync-check` job, lines ~59-78;
  `version.needs` becomes `[verify]`)
- Modify: `CLAUDE.md`, `CONTEXT.md` (the `**Canonical source**` entry under `## Repos`)
- Modify: `gui/theme_manager.py` (docstrings of `role_stylesheet`, ~line 225, and the density QSS
  function, ~line 283)
- Modify: `tests/test_theme_button_roles.py` (module docstring), `tests/test_style_literals_guard.py`
  (`test_every_detection_path_survived_the_shared_sync`), `tests/test_type_scale.py` (module docstring),
  `tests/test_stats_manager.py` (moved in Task 3: fix any line that calls packing-tool canonical)
- Modify: `shared/README.md`, `shared/__init__.py`, `shared/components/__init__.py`. These are
  editable now because of Task 1.
- Create: `docs/adr/0017-fulfilment-owns-shared.md`

- [ ] **Step 1: Delete the sync script and the CI drift job**

`git -C <FT> rm scripts/sync_shared.py`. In `build_release.yml`, delete the whole
`shared-sync-check:` job (from `  shared-sync-check:` down to the blank line before `  version:`), and
change `    needs: [verify, shared-sync-check]` to `    needs: [verify]`. Then check that nothing
else refers to it: `grep -n "shared-sync-check\|sync_shared" .github/workflows/build_release.yml`
should print nothing.

- [ ] **Step 2: CLAUDE.md**

Replace the whole `## Shared Module (\`shared/\`)` section (heading through the last bullet, before
the next `---`) with:

```markdown
## Shared Module (`shared/`)

`shared/` (theme, components, icons, fonts, navrail, logger, stats, file locking, atomic writes,
session IDs) is used identically by this repo and `../packing-tool`. **This copy is the canonical
source** (ADR 0017).

- Edit shared behavior **here**, directly, and test it here: `tests/` holds the `shared/` unit tests.
- packing-tool adopts changes when it is ready. From packing-tool it runs
  `python scripts/sync_shared.py [/path/to/shopify-fulfillment-tool]`, which mirrors this `shared/` and
  records the commit in `scripts/shared_synced_from.txt`. Its CI fails if its copy differs from
  `shared/` at that commit.
- A `shared/` change reaches Packing Tool at its next sync. When a change will need packing-tool work
  (a renamed token, a removed component), say so in the PR.
- Never hand-edit `packing-tool/shared/`. The next sync overwrites it, and a hook blocks it.
```

Also in `CLAUDE.md`:
- The graphify bullet: replace the sentence that begins `This matters even more here` with
  `This repo is the canonical source for \`shared/\`, so a stale graph here also feeds wrong
  assumptions into packing-tool work.`
- `a new colour, spacing or type token goes in \`shared/theme.py\` (via packing-tool, see below), and both themes must`
  becomes `a new colour, spacing or type token goes in \`shared/theme.py\` (here; packing-tool picks it up at its next sync), and both themes must`.
- `- Edits to \`shared/\` are blocked here: edit packing-tool, then run \`sync_shared.py <path>\`.`
  becomes `- Edits to \`packing-tool/shared/\` are blocked by a hook: edit \`shared/\` here; packing-tool syncs it.`

- [ ] **Step 3: CONTEXT.md**

Replace the `**Canonical source**` entry (3 lines under `## Repos`) with:

```markdown
**Canonical source** — `shopify-fulfillment-tool`. Every `shared/` change is
authored here; packing-tool receives it through its own `scripts/sync_shared.py`,
one-way, pinned to a commit. A `shared/` file edited in packing-tool is
overwritten by its next sync.
```

- [ ] **Step 4: Comments and docstrings that name the old owner**

`gui/theme_manager.py`, `role_stylesheet` docstring, becomes:

```python
    """QSS this app layers on after shared.theme's sheet.

    The button hierarchy used to live here, back when shared/theme.py was
    owned by packing-tool and could not be edited from this repo. 8.5 moved
    it into shared/theme.py's build_stylesheet so both apps read one
    definition. What is left is genuinely shopify-only chrome.
    """
```

The density function's docstring: replace
`QPushButton. shared/theme.py is sync-owned by packing-tool -- change it\n    there and re-run scripts/sync_shared.py, never here.`
with `QPushButton. A change to that base size belongs in shared/theme.py, not\n    here, so both apps get it.` (keep the indentation and the paragraph that follows).

`tests/test_theme_button_roles.py` docstring: delete the parenthetical
`(authored in\npacking-tool, pulled in by scripts/sync_shared.py)` so it reads
`8.5 moved the button-role QSS into shared.theme.build_stylesheet so both apps read one\ndefinition; gui.theme_manager re-exports set_button_role for existing callers.`

`tests/test_style_literals_guard.py`: rename `test_every_detection_path_survived_the_shared_sync` to
`test_every_detection_path_reaches_the_guard` and replace its docstring with:

```python
    """style_lint.py's own unit tests are tests/test_style_lint.py. This is
    one offender per rule seen through this repo's guard, so a rule that stops
    firing fails here too, not only in the unit tests."""
```

`tests/test_type_scale.py` docstring: `catches shared/theme.py drifting\nunder us (it is sync-owned by packing-tool), and`
becomes `catches shared/theme.py and this app's scale drifting\napart, and`.

- [ ] **Step 5: `shared/` docs**

`shared/README.md`: replace the `## The sync rule` section body with:

```markdown
**`shopify-fulfillment-tool/shared/` is canonical** (ADR 0017 there).
`packing-tool/shared/` is a one-way copy, refreshed by running
`python scripts/sync_shared.py /path/to/shopify-fulfillment-tool` from
packing-tool's root (the bare sibling default resolves wrongly from a
worktree, so pass the path). The script mirrors this folder and records the
source commit in `packing-tool/scripts/shared_synced_from.txt`; packing-tool's
CI fails if its copy differs from this folder at that commit. A `shared/` file
hand-edited in packing-tool is silently overwritten by the next sync — author
every change here.
```

and the `## Tests` section body with:

```markdown
Each module's own tests live in `shopify-fulfillment-tool/tests/`. packing-tool
keeps the tests that exercise its own use of `shared/` (its `gui.theme`
wiring, its type-scale default, session metadata, the atomic state write).
```

`shared/__init__.py` docstring becomes:

```python
"""
Shared modules for Shopify Fulfillment Tool and Packing Tool.

This package contains unified components that work identically in both
tools. Canonical copy lives in shopify-fulfillment-tool/shared/; mirrored
into packing-tool/shared/ by packing-tool/scripts/sync_shared.py.
"""
```

`shared/components/__init__.py` docstring's second line becomes
`Canonical in shopify-fulfillment-tool; packing-tool receives them via its scripts/sync_shared.py.`

- [ ] **Step 6: ADR 0017**

Create `docs/adr/0017-fulfilment-owns-shared.md`:

```markdown
# 0017 — Fulfilment Tool owns `shared/`; Packing Tool pulls a pinned copy

**Status:** Accepted, 2026-09-30
**Context:** `docs/superpowers/specs/2026-09-30-shared-canonical-swap-design.md`. Reverses the
direction set by packing-tool's shared-unification spec (2026-07-25). ADR 0016's aside that
`shared/style_lint.py` is "owned by packing-tool" is out of date from here on.

## Decision

1. `shopify-fulfillment-tool/shared/` is the canonical source. It is edited, linted and unit-tested
   here.
2. packing-tool mirrors it with its own `scripts/sync_shared.py`, which deletes and re-copies the
   folder and writes the source commit to `scripts/shared_synced_from.txt`.
3. packing-tool's CI checks its `shared/` against this repo **at that pinned commit**, not against
   `main`.

## Why

- The UI redesign (ADR 0016) is done here first and adopted by Packing Tool later. Authoring
  `shared/` in the repo that is not being redesigned meant every redesign change started in the
  wrong place.
- **Pinned, not `main`.** Packing Tool will lag on purpose while the redesign lands. A check against
  `main` would turn every packing-tool PR red whenever `shared/` moved here, until someone synced,
  and that would push people into syncing changes Packing Tool is not ready for. The pin still fails
  a hand edit, which is the one thing the check exists to catch.
- **Mirror, not copy.** The old script only copied files over, so a file renamed or deleted upstream
  would linger in the copy. The redesign renames things.
- A package or a git submodule would retire the copy altogether. Both need build and packaging
  changes in two PyInstaller apps for no gain the copy does not already give.

## Consequences

- A `shared/` change here reaches Packing Tool only when packing-tool syncs. That sync is where
  Packing Tool's breakage shows up, so a PR here that will need packing-tool work says so.
- The sync refuses a source whose `shared/` has uncommitted or untracked changes, because the
  recorded SHA would not match what was copied. The recorded commit must be pushed, or packing-tool's
  CI fails at checkout.
- `~/.claude/hooks/shared-guard.sh` on the dev VM now blocks edits to `packing-tool/shared/`.
```

- [ ] **Step 7: Sweep for anything missed**

Run from FT: `rg -n "sync_shared|packing-tool/shared|sync-owned|synced copy|canonical source" --glob '!docs/superpowers/**' --glob '!graphify-out/**' --glob '!docs/adr/000*' --glob '!docs/adr/001[0-6]*' --glob '!.venv/**'`
Expected: every hit describes the new direction. Fix any that do not.

- [ ] **Step 8: Gate and commit**

Run `.venv/bin/ruff check .` and `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`. Both
must be clean. Then `git add -A` (FT), commit with the message
`Fulfilment Tool becomes the canonical shared/ source (ADR 0017)`, and push:
`/usr/bin/git -C <FT> push`.

---

### Task 5 (PT): The sync script, pulling from Fulfilment

**Files:**
- Create: `PT/scripts/sync_shared.py`
- Create: `PT/tests/test_sync_shared.py`
- Create (by running the script): `PT/scripts/shared_synced_from.txt`
- Modify (by running the script): `PT/shared/**` (brings over Task 4's `shared/` doc edits)

**Interfaces:**
- Produces: `scripts.sync_shared.main(argv: list[str] | None = None) -> int` (0 = synced, 1 = refused).
  The module globals `DEST: Path` (the `shared/` to overwrite), `PIN: Path` (the SHA file) and
  `DEFAULT_SOURCE: Path` are read inside `main()`, so tests monkeypatch them. Task 6's CI job reads
  `scripts/shared_synced_from.txt`: one line, 40 lowercase hex characters and `\n`.

- [ ] **Step 1: Write the failing tests**

Create `PT/tests/test_sync_shared.py`:

```python
"""scripts/sync_shared.py mirrors shopify-fulfillment-tool/shared/ into this
repo and pins the commit it copied, which CI checks shared/ against."""
import subprocess

import pytest

from scripts import sync_shared


def _git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture
def source(tmp_path):
    """A committed fake Fulfilment checkout, with the same __pycache__
    ignore the real one has."""
    root = tmp_path / "fulfilment"
    (root / "shared" / "components").mkdir(parents=True)
    (root / "shared" / "theme.py").write_text("X = 1\n", encoding="utf-8")
    (root / "shared" / "components" / "card.py").write_text("Y = 2\n", encoding="utf-8")
    (root / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "-m", "init")
    return root


@pytest.fixture
def dest(tmp_path, monkeypatch):
    """This repo's side: a shared/ holding a file the source no longer has."""
    shared = tmp_path / "packing" / "shared"
    shared.mkdir(parents=True)
    (shared / "stale.py").write_text("old\n", encoding="utf-8")
    pin = tmp_path / "packing" / "shared_synced_from.txt"
    monkeypatch.setattr(sync_shared, "DEST", shared)
    monkeypatch.setattr(sync_shared, "PIN", pin)
    return shared, pin


def _files(root):
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


def test_mirrors_the_source_and_pins_its_commit(source, dest):
    shared, pin = dest
    cache = source / "shared" / "__pycache__"
    cache.mkdir()
    (cache / "theme.cpython-314.pyc").write_bytes(b"\0")

    assert sync_shared.main([str(source)]) == 0

    assert _files(shared) == ["components/card.py", "theme.py"]
    assert (shared / "theme.py").read_text(encoding="utf-8") == "X = 1\n"
    assert pin.read_text(encoding="utf-8") == _git(source, "rev-parse", "HEAD") + "\n"


def test_a_modified_source_is_refused_and_nothing_changes(source, dest):
    shared, pin = dest
    (source / "shared" / "theme.py").write_text("X = 2\n", encoding="utf-8")

    assert sync_shared.main([str(source)]) == 1

    assert _files(shared) == ["stale.py"]
    assert not pin.exists()


def test_an_untracked_file_in_the_source_counts_as_dirty(source, dest):
    shared, pin = dest
    (source / "shared" / "new_module.py").write_text("Z = 3\n", encoding="utf-8")

    assert sync_shared.main([str(source)]) == 1

    assert _files(shared) == ["stale.py"]
    assert not pin.exists()


def test_a_source_that_is_not_a_git_checkout_is_refused(tmp_path, dest):
    shared, pin = dest
    plain = tmp_path / "plain"
    (plain / "shared").mkdir(parents=True)
    (plain / "shared" / "theme.py").write_text("X = 1\n", encoding="utf-8")

    assert sync_shared.main([str(plain)]) == 1

    assert _files(shared) == ["stale.py"]
    assert not pin.exists()


def test_a_missing_source_is_refused(tmp_path, dest):
    shared, pin = dest

    assert sync_shared.main([str(tmp_path / "nowhere")]) == 1

    assert _files(shared) == ["stale.py"]
    assert not pin.exists()
```

- [ ] **Step 2: Run them to see them fail**

Run from PT: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q tests/test_sync_shared.py`
Expected: collection error, `ImportError: cannot import name 'sync_shared' from 'scripts'`.

- [ ] **Step 3: Write the script**

Create `PT/scripts/sync_shared.py`:

```python
"""One-way mirror of the canonical shared/ package from
shopify-fulfillment-tool into this repo. shopify-fulfillment-tool/shared/ is
the single source of truth (its docs/adr/0017-fulfilment-owns-shared.md) —
never hand-edit packing-tool/shared/ directly.

Usage:
    python scripts/sync_shared.py [/path/to/shopify-fulfillment-tool]

The argument is only needed from a git worktree, where the sibling-directory
default does not resolve. The copied commit is written to
scripts/shared_synced_from.txt, and CI checks shared/ against the source repo
at that commit, so this repo may lag behind for as long as it likes.
"""
import shutil
import subprocess
import sys
from pathlib import Path

THIS_REPO = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = THIS_REPO.parent / "shopify-fulfillment-tool"
DEST = THIS_REPO / "shared"
PIN = THIS_REPO / "scripts" / "shared_synced_from.txt"


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
    ).stdout


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    root = Path(argv[0]).expanduser().resolve() if argv else DEFAULT_SOURCE
    source = root / "shared"

    if not source.is_dir():
        print(f"Source not found: {source}", file=sys.stderr)
        if not argv:
            print(
                "Expected shopify-fulfillment-tool as a sibling directory of "
                "this repo, or pass its path as an argument.",
                file=sys.stderr,
            )
        return 1

    try:
        dirty = _git(root, "status", "--porcelain", "--", "shared")
        sha = _git(root, "rev-parse", "HEAD").strip()
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"{root} is not a usable git checkout: {exc}", file=sys.stderr)
        return 1
    if dirty:
        print(
            f"{source} has uncommitted or untracked changes; commit them first "
            f"so the recorded commit matches what is copied:\n{dirty}",
            file=sys.stderr,
        )
        return 1

    shutil.rmtree(DEST, ignore_errors=True)
    shutil.copytree(source, DEST, ignore=shutil.ignore_patterns("__pycache__"))
    PIN.write_text(sha + "\n", encoding="utf-8")

    count = sum(1 for p in DEST.rglob("*") if p.is_file())
    print(f"Synced {count} file(s) from {source} at {sha} into {DEST}.")
    print("Push that commit before opening a PR: CI checks out the source at it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q tests/test_sync_shared.py`
Expected: 5 passed.

- [ ] **Step 5: Sync from FT for real**

Make sure Task 4 is committed and pushed and that FT `shared/` is clean. Then run from PT:
`.venv/bin/python scripts/sync_shared.py /home/gloopy/Desktop/Projects/shopify-fulfillment-tool/.claude/worktrees/dr-12`
Expected: `Synced N file(s) ... at <FT HEAD sha> ...`. Then check:
- `cat scripts/shared_synced_from.txt` equals `/usr/bin/git -C <FT> rev-parse HEAD`;
- `diff -rq -x __pycache__ shared /home/gloopy/Desktop/Projects/shopify-fulfillment-tool/.claude/worktrees/dr-12/shared` prints nothing;
- `/usr/bin/git -C <PT> status --short shared` shows only `README.md`, `__init__.py` and
  `components/__init__.py` modified (Task 4's doc edits). Anything else means the copies were not
  identical at the start: stop, and `runner <run> note` it.

- [ ] **Step 6: Lint and commit**

Run `.venv/bin/ruff check .` (PT still lints `shared/` until Task 6; it must pass). Then
`git add scripts/sync_shared.py scripts/shared_synced_from.txt tests/test_sync_shared.py shared` and
commit with the message `sync_shared.py: pull shared/ from shopify-fulfillment-tool, pinned`.

---

### Task 6 (PT): packing-tool becomes the copy (CI, lint, tests, words)

**Files:**
- Modify: `PT/.github/workflows/build-release.yml` (lint step ~line 48; new `shared-sync-check` job;
  `version.needs`)
- Delete from `PT/tests/`: the 18 files Task 3 moved, plus `test_ui_assets.py` (19 files; skip any
  that Task 3 Step 5 sent back)
- Modify: `PT/tests/conftest.py` (remove `_rule_block` and `import re`)
- Modify: `PT/CLAUDE.md` (Shared Module section, graphify bullet), `PT/README.md` (Layout bullet)

- [ ] **Step 1: CI job and lint**

In `build-release.yml`, change the lint step to:

```yaml
      - name: Lint (ruff)
        # shared/ is a synced copy of shopify-fulfillment-tool's; it is linted there.
        run: ruff check . --exclude shared
```

Add this job between `verify:` and `version:`, at the same indentation as those jobs:

```yaml
  shared-sync-check:
    name: Check shared/ matches shopify-fulfillment-tool at the synced commit
    runs-on: ubuntu-latest
    steps:
      - name: Check out this repo
        uses: actions/checkout@v7
        with:
          persist-credentials: false
      - name: Read the synced commit
        id: pin
        run: echo "sha=$(tr -d '[:space:]' < scripts/shared_synced_from.txt)" >> "$GITHUB_OUTPUT"
      - name: Check out shopify-fulfillment-tool at that commit (canonical shared/ source)
        uses: actions/checkout@v7
        with:
          repository: cognitiveghost/shopify-fulfillment-tool
          ref: ${{ steps.pin.outputs.sha }}
          path: fulfilment-ref
          persist-credentials: false
      - name: Diff shared/ against the canonical copy
        run: |
          if ! diff -r -x __pycache__ shared fulfilment-ref/shared; then
            echo "::error::shared/ differs from shopify-fulfillment-tool/shared/ at ${{ steps.pin.outputs.sha }}. Never hand-edit packing-tool/shared/: change it in shopify-fulfillment-tool, then run scripts/sync_shared.py."
            exit 1
          fi

```

Change `version`'s `    needs: [verify]` to `    needs: [verify, shared-sync-check]`.

Simulate the diff step locally from PT:
`diff -r -x __pycache__ shared /home/gloopy/Desktop/Projects/shopify-fulfillment-tool/.claude/worktrees/dr-12/shared; echo "exit=$?"`
Expected: `exit=0`. The job itself is verified by the PR's CI run.

- [ ] **Step 2: Remove the moved tests and the orphaned helper**

One `git -C <PT> rm` call with the 19 paths:
`tests/test_assets.py tests/test_brand_icon.py tests/test_components_card.py tests/test_components_confirm_dialog.py tests/test_components_filterbar.py tests/test_components_overflow.py tests/test_components_toast.py tests/test_excepthook.py tests/test_logger.py tests/test_navrail.py tests/test_shared_theme_buttons.py tests/test_shared_theme_widgets.py tests/test_state_panel.py tests/test_statcard.py tests/test_status_style.py tests/test_stats_manager.py tests/test_style_lint.py tests/test_theme_css_vars.py tests/test_ui_assets.py`

Then run `grep -rn "_rule_block\|\bre\." tests/` in PT. If `_rule_block` has no users left, delete the
function from `tests/conftest.py`, and delete `import re` if nothing else in `conftest.py` uses `re.`.
PT's conftest docstring says `tests/test_logger.py's _reset_root_logger fixture is autouse there`.
That file has moved, so change the sentence to
`shared/logger.py's own tests live in shopify-fulfillment-tool;`, keeping the rest of the
sentence as it is.

- [ ] **Step 3: Words**

`PT/CLAUDE.md`: replace the `## Shared Module (\`shared/\`)` section body with:

```markdown
`shared/` (theme, components, icons, fonts, navrail, logger, stats, file locking, atomic writes,
session IDs) is used identically by this repo and `../shopify-fulfillment-tool`. **That repo's copy is
the canonical source** (its `docs/adr/0017-fulfilment-owns-shared.md`); this one is a pinned mirror.

- **Never hand-edit files under `shared/`**. The next sync overwrites them, CI fails the PR, and a
  hook blocks the edit.
- To change shared behavior: edit it in `shopify-fulfillment-tool`, commit and push, then from this
  repo run `python scripts/sync_shared.py [/path/to/shopify-fulfillment-tool]` (the path is needed from
  a worktree). It mirrors `shared/` and writes the commit to `scripts/shared_synced_from.txt`.
- This repo may lag behind on purpose: sync when Packing Tool is ready for what changed. CI checks
  `shared/` against the pinned commit, not against the other repo's `main`.
- The `shared/` unit tests live in shopify-fulfillment-tool. The tests here cover this app's use of it.
```

In the graphify bullet, replace
`Since this repo is the canonical source for \`shared/\`, a stale graph here is also what feeds wrong assumptions on the shopify-fulfillment-tool side.`
with `\`shared/\` changes land here via \`scripts/sync_shared.py\`, which graphify cannot see until you re-run it.`

`PT/README.md` Layout bullet becomes:
`- \`shared/\`: code shared with Fulfilment Tool, mirrored from its canonical copy in shopify-fulfillment-tool by \`scripts/sync_shared.py\` (see \`CLAUDE.md\`)`

Sweep from PT: `rg -n "sync_shared|canonical source|sync-owned|synced copy" --glob '!docs/superpowers/**' --glob '!graphify-out/**' --glob '!.venv/**' --glob '!shared/**'`.
Every hit must describe the new direction.

- [ ] **Step 4: Gate**

Run from PT: `.venv/bin/ruff check . --exclude shared` then `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q`
Expected: both clean.

- [ ] **Step 5: Commit and push**

`git add -A` (PT), commit with the message `shared/ becomes a pinned mirror of shopify-fulfillment-tool's`,
then `/usr/bin/git -C <PT> push -u origin dr/12-can-we-swap-shared-fodler-make-a-fulfilm`.

---

### Task 7: Final cross-repo check and PRs

- [ ] **Step 1: The two copies are equal and the pin is right**

`diff -rq -x __pycache__ <FT>/shared <PT>/shared` prints nothing. `cat <PT>/scripts/shared_synced_from.txt` equals
the FT commit that contains Task 4 (`/usr/bin/git -C <FT> log -1 --format=%H -- shared`, or any later
FT commit, since Task 4 was the last FT change to `shared/`).

- [ ] **Step 2: Open the PRs, FT first**

FT PR title: `Fulfilment Tool becomes the canonical shared/ source`. PT PR title:
`shared/ becomes a pinned mirror of shopify-fulfillment-tool's`. Each body links the other PR and
the spec, and says: merge FT first. PT's pin points at an FT PR-branch commit, which stays fetchable
through `refs/pull/N/head` after the squash merge, and the next routine sync re-pins to `main`. Report
each PR with `runner <run> pr <owner/repo> <number> <url>`.

- [ ] **Step 3: Watch PT's CI `shared-sync-check` job go green** on its PR run. If the checkout step
  cannot fetch the pinned SHA, FT's branch was not pushed: push it and re-run.
