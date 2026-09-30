# Fulfilment Tool becomes the canonical `shared/` source

Date: 2026-09-30. Task: dev-runner run 31 (Todoist 6hfq5Fxv3xV2RV3v).
Classification: architectural (moves code ownership between two repos and flips their sync contract).

## Why

The UI redesign (ADR 0016, the 2026-09-30 UI-refresh audit) is done in this repo first and adopted
by packing-tool later. Today `packing-tool/shared/` is canonical and this repo gets a one-way copy,
so every redesign change to `shared/` would have to start in packing-tool. The owner wants the
reverse: author `shared/` here, and packing-tool pulls it when it is ready.

## Success criteria

1. `shopify-fulfillment-tool/shared/` is edited directly. Nothing here overwrites it.
2. packing-tool has `scripts/sync_shared.py`, which mirrors this repo's `shared/` into its own and
   records the source commit.
3. packing-tool can lag behind this repo for as long as it likes without CI going red. A hand edit to
   `packing-tool/shared/` still fails packing-tool's CI.
4. The unit tests of `shared/` modules run in this repo.
5. No doc, comment, docstring, CI job or hook still says packing-tool is canonical.

## Facts this design rests on (checked 2026-09-30)

- The two `shared/` folders are byte-identical (`diff -rq -x __pycache__`). No open PR in either repo
  touches `shared/`. So the cutover starts from equal copies.
- Both repos are public, so each one's CI can check out the other without a token.
- This repo's CI (`.github/workflows/build_release.yml`) has a `shared-sync-check` job that diffs
  against packing-tool `main`, and the `version` job lists it in `needs:`. Lint runs
  `ruff check . --exclude shared`.
- `ruff check shared` here fails with one F821 (`shared/components/toast.py:76`, a forward reference
  that is legal on Python 3.14). packing-tool's `ruff.toml` has `target-version = "py314"` and this
  repo's does not. With `py314` added here, `shared/` is clean and 7 auto-fixable UP0xx findings
  appear in `gui/` and `shopify_tool/` (`ruff check . --fix` clears them).
- `~/.claude/hooks/shared-guard.sh` (outside both repos, a PreToolUse Edit|Write hook) blocks edits to
  this repo's `shared/` and allows packing-tool's.
- Merges are squash merges. GitHub keeps `refs/pull/N/head`, so a PR-branch commit stays fetchable by
  SHA after its branch is deleted.

## Decisions (owner answers, question 27)

- **Drift check:** pinned to a synced SHA. Lag is allowed, and a hand edit still fails.
- **Tests:** the tests that cover only `shared/` move to this repo.
- **Guard hook:** the Stage C implementer flips `~/.claude/hooks/shared-guard.sh`.
- **Design:** approved as a clean cutover.

## Design

### 1. Sync script moves to packing-tool

This repo's `scripts/sync_shared.py` is deleted. packing-tool gets a new `scripts/sync_shared.py`:

```
python scripts/sync_shared.py [/path/to/shopify-fulfillment-tool]
```

- The default source is the sibling `../shopify-fulfillment-tool`. From a worktree the path must be
  passed, the same as today.
- Refuse (exit 1, message on stderr) if `<src>/shared` is missing, or if `git -C <src> status
  --porcelain -- shared` prints anything. A dirty source would make the recorded SHA lie.
- **Mirror, not copy:** delete `packing-tool/shared/` and `shutil.copytree` the source, ignoring
  `__pycache__`. Today's script only copies files over, so a file renamed or deleted upstream would
  linger. The redesign will rename things.
- Write `git -C <src> rev-parse HEAD` (40 hex chars and a newline) to
  `packing-tool/scripts/shared_synced_from.txt`. That file sits outside `shared/`, so `shared/` stays
  a pure copy and `diff -r` stays exact.
- Print the SHA and the number of files copied. If the SHA is not pushed yet, CI fails at the checkout
  step, which is loud enough. The script does not check this.

### 2. Drift check moves to packing-tool, pinned

- This repo deletes the `shared-sync-check` job and removes it from `version.needs`.
- packing-tool's `build-release.yml` gains a `shared-sync-check` job:
  1. check out packing-tool;
  2. read the SHA from `scripts/shared_synced_from.txt` into a step output;
  3. check out `cognitiveghost/shopify-fulfillment-tool` at `ref: <sha>` into
     `fulfilment-ref`, with `persist-credentials: false`;
  4. `diff -r -x __pycache__ shared fulfilment-ref/shared`. On a difference, print
     `::error::shared/ differs from shopify-fulfillment-tool/shared/ at <sha>. Never hand-edit
     packing-tool/shared/: change it in shopify-fulfillment-tool, then run scripts/sync_shared.py.`
     and exit 1.
- Wire it into the release gate the way this repo does: the `version` job's `needs: [verify]` becomes
  `needs: [verify, shared-sync-check]`.

### 3. Lint follows ownership

- This repo: CI runs `ruff check .` (no `--exclude shared`), and `ruff.toml` gains
  `target-version = "py314"` with the same comment packing-tool uses. Run `ruff check . --fix` for
  the 7 UP0xx findings. The CLAUDE.md gate line drops `--exclude shared`.
- packing-tool: CI runs `ruff check . --exclude shared`. Its comment "No --exclude shared: this repo
  owns shared/." becomes "shared/ is a synced copy of shopify-fulfillment-tool's; it is linted there."

### 4. Tests move to this repo

Move these 18 packing-tool test files to this repo's `tests/` unchanged (`git rm` there, add here). They
import only `shared.*`, PySide6 and the stdlib:

`test_assets.py`, `test_brand_icon.py`, `test_components_card.py`,
`test_components_confirm_dialog.py`, `test_components_filterbar.py`, `test_components_overflow.py`,
`test_components_toast.py`, `test_excepthook.py`, `test_logger.py`, `test_navrail.py`,
`test_shared_theme_buttons.py`, `test_shared_theme_widgets.py`, `test_state_panel.py`,
`test_statcard.py`, `test_status_style.py`, `test_stats_manager.py`, `test_style_lint.py`,
`test_theme_css_vars.py`.

Adjustments:
- `test_shared_theme_buttons.py` and `test_shared_theme_widgets.py` do `from conftest import
  _rule_block`. Copy `_rule_block` (with its docstring and the `re` import) from packing-tool's
  `tests/conftest.py` into this repo's `tests/conftest.py`. No other packing-tool test uses it,
  so remove it (and `re`, if nothing else there uses it) from packing-tool's `conftest.py`.
- `test_ui_assets.py` exists in both repos. packing-tool's is a superset (two more icons,
  `toggle-off` and `toggle-on`, plus two `glyph_url` non-square tests). Replace this repo's with
  packing-tool's and delete packing-tool's.
- Update any docstring in a moved file that says packing-tool is canonical.

These stay in packing-tool, because they exercise packing-tool code as well as `shared/`:
`test_theme.py` and `test_theme_notifier.py` (use `gui.theme`), `test_type_scale.py` (has
`test_packing_tool_ships_at_the_desk_default`), `test_metadata_utils.py` (imports
`packing_tool.session_manager`), `test_style_literals_guard.py` (scans packing-tool's source),
`test_session_registry.py`, `test_json_cache.py`, `test_atomic_write.py` (uses the `loaded_logic`
PackerLogic fixture).

Before moving, check whether any fixture a moved test uses by name (not by import) is defined in
packing-tool's `conftest.py` and missing here. `qapp` exists in both.

### 5. Guard hook flips

`~/.claude/hooks/shared-guard.sh` becomes:

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

This is the first implementation step. Once it lands, the `shared/` doc edits below are made in this
repo, which is now editable, and they reach packing-tool through the new sync script. The hook is
global, so any other session editing packing-tool's `shared/` is blocked from that moment on. That is
intended.

### 6. Words

Every statement of ownership flips. Find them with
`rg -n "sync_shared|canonical|packing-tool/shared|sync-owned|synced copy" --glob '!docs/superpowers/**' --glob '!graphify-out/**'`
in both worktrees. Known sites:

- this repo: `CLAUDE.md` ("Shared Module", Theme System bullet, the Tooling bullet "Edits to `shared/`
  are blocked here", gate line), `CONTEXT.md` ("Canonical source" entry becomes: `shopify-fulfillment-tool`.
  Every `shared/` change is authored here, and packing-tool receives it through its
  `scripts/sync_shared.py`, one-way.), `gui/theme_manager.py` comments around lines 225 and 283,
  `tests/test_theme_button_roles.py`, `tests/test_style_literals_guard.py`, `tests/test_type_scale.py`
  docstrings;
- `shared/` (edited here, synced across): `README.md` ("The sync rule" and "Tests" sections),
  `__init__.py`, `components/__init__.py`;
- packing-tool: `CLAUDE.md` ("Shared Module" section, graphify bullet), `README.md` line 60, any
  moved-test references.

Historical specs and plans under `docs/superpowers/` are left alone. They are records.

### 7. ADR

`docs/adr/0017-fulfilment-owns-shared.md` in this repo, in the house ADR style (read 0016 first). It
records: the redesign-first reason, the pinned-SHA drift check and why a check against `main` was
rejected (packing-tool PRs would go red on every upstream change while it deliberately lags), and
mirror-instead-of-copy. packing-tool's CLAUDE.md links to it by repo and path.

## Order of work and PRs

1. Flip the hook (§5).
2. **This repo, branch `dr/12-can-we-swap-shared-fodler-make-a-fulfilm`:** words (§6, this repo and
   `shared/`), ADR, delete the sync script, delete the CI job, lint change, moved tests. Push.
3. **packing-tool, same branch name in its worktree:** new sync script, then run it against this
   repo's worktree (the pushed head from step 2). That brings over the `shared/` doc edits and writes
   `scripts/shared_synced_from.txt`. Then the CI job, lint change, test removals and words. Push.
4. Two PRs. Merge this repo's first. packing-tool's pin points at a commit on this repo's PR branch,
   which stays fetchable through `refs/pull/N/head` after the squash merge. The next routine sync
   re-pins to a `main` commit.

## Testing

- The new sync script gets one test in packing-tool, `tests/test_sync_shared.py`. It builds a
  throwaway git repo in `tmp_path` with a `shared/` folder, one commit, and a stale file planted in
  a fake destination. It runs `main()` with `argv` patched and the destination and pin paths
  monkeypatched, then asserts: the destination matches the source, the stale file is gone,
  `__pycache__` is not copied, the pin file holds the commit SHA, and a dirty source returns 1 and
  leaves the destination untouched. To make this seam testable, the script's module-level
  `DEST`/`PIN` paths are read inside `main()` from module globals, so the test can monkeypatch them.
- Both repos' gates pass: this repo runs pytest plus `ruff check .`, and packing-tool runs pytest
  plus `ruff check . --exclude shared`.
- `diff -rq -x __pycache__` of the two worktrees' `shared/` prints nothing after step 3.
- The CI drift job is verified by the packing-tool PR's own CI run.

## Out of scope

- Any actual redesign change to `shared/`.
- Retiring the copy entirely (a package, a git submodule). This keeps the proven copy-and-check
  model and only reverses its direction.
