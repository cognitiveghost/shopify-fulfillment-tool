# Plan — Phase 8.1: shared design-system foundation

Implements subtask **8.1** of
`docs/superpowers/specs/2026-08-25-phase8-ui-redesign-design.md`.

**Why this slice exists separately:** it is the only part of Phase 8 that does
not depend on the open visual-direction question (§6 of the design). Nothing
here changes how the app *looks* — it moves where the design system lives and
retires hardcoded colours. Same pixels, tokenised.

**Branch:** `worktree-phase8-ui-redesign` (already created).
**Repos:** authored in `packing-tool/shared/`, synced into this repo.
Packer worktree needed: `packing-tool/.claude/worktrees/phase8-ui-redesign`
(Stage B must create it — Stage A did not).

**Gate, after every task:**
```
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
.venv/bin/ruff check . --exclude shared
```
Baseline must be recorded by running the suite *before* Task 1 — do not
estimate it.

---

## Task 1 — Break `icons.py`'s dependency on the app-side theme manager

`gui/icons.py` currently does `from .theme_manager import get_theme_manager`
and defaults `color` to the active theme's text colour. `shared/` cannot import
that: `get_theme_manager()` is per-app (QSettings org names differ), and
`shared/theme.py` has no notion of a *current* theme.

Split the responsibility before moving anything:

1. In `gui/icons.py`, make `_source`/`_render` and a **`icon(name, color, sizes)`
   with `color` required** the pure part. No `theme_manager` import.
2. Keep the existing zero-argument-colour convenience where it is used —
   `gui/icons.py` retains a thin `icon()` wrapper that fills `color` from
   `get_theme_manager()` and delegates.

Do not move files in this task. Run the gate; nothing should change.

**Verification:** `grep -rn "theme_manager" gui/icons.py` returns only the
wrapper. Call sites (`grep -rn "icons import icon\|from .icons" gui/ | wc -l`)
are unchanged in count.

## Task 2 — Move the assets into `packing-tool/shared/`

In the **packing-tool** worktree:

```
git mv  <from shopify>  shared/assets/icons/*.svg   # 18 files + LICENSE
git mv  <from shopify>  shared/assets/fonts/*.ttf   # Inter Regular/Bold + OFL.txt
```

(The files do not exist in packing-tool yet — copy them from
`shopify-fulfillment-tool/gui/assets/`, `git add` them there, and delete the
shopify originals in the shopify worktree.)

Add `shared/icons.py` (the pure part from Task 1) and `shared/fonts.py`, with
`ICONS_DIR`/`FONTS_DIR` resolving relative to `shared/`. Move
`gui/components/{card,form_section}.py` to `shared/components/` the same way.

In the **shopify** worktree:

```
.venv/bin/python scripts/sync_shared.py
```

Confirm it carried the subdirectories and binaries — this is the assumption the
whole slice rests on, so check it explicitly:

```
ls shared/assets/icons | wc -l          # expect 19 (18 svg + LICENSE)
ls shared/assets/fonts                  # expect the two .ttf + OFL.txt
cmp shared/assets/fonts/Inter-Bold.ttf ../../../../packing-tool/shared/assets/fonts/Inter-Bold.ttf
```

`sync_shared.py` uses `rglob("*")` + `copy2` and creates parent dirs, so this
should pass with **no change to the script**. If `cmp` fails, stop — the whole
shared-assets premise is wrong and the design needs revisiting.

Update `gui/icons.py`, `gui/fonts.py`, `gui/components/__init__.py` to re-export
from `shared.*` rather than hold the implementation. Keep the `gui.` import
paths working — ~180 call sites reference the theme manager and an unknown
number import `gui.icons`; re-exporting is a two-line change per module versus
touching every call site.

**Verification:** the app still renders. Re-run the headless grab from the
design doc §8 and diff against `dark-0-session-setup.png` — it should be
pixel-identical. A non-identical render means an asset failed to load and the
font silently fell back (`fonts.py` never raises, by design).

## Task 3 — Add the missing tokens

In `packing-tool/shared/theme.py`, extend `ThemeTokens` with what
`build_stylesheet()` needs in 8.3 but does not have. Add fields only; do not
change any existing value — that is 8.2's job. (8.2 is no longer blocked: the
user chose palette **C, Warm slate** — `background="#16181D"`,
`background_elevated="#1F232A"`, `border="#2F343D"`, `active_border="#26A69A"`,
`accent_blue="#3D9BE9"`, light theme derived. Settled; do not re-open it.)

- surface levels: the dataclass has `background` and `background_elevated` but
  nothing between — add `surface` for card fills.
- one spacing scale and one radius value, so 8.3 stops hardcoding both.

`validate_theme()` checks `_COLOR_FIELDS`; add any new colour field to that
tuple or it goes unvalidated.

Sync into shopify. Gate.

## Task 4 — Retire the Shopify Tool's 41 hardcoded colours

41 occurrences across 8 modules; worst is `gui/pandas_model.py` (15).

```
grep -rEn '#[0-9a-fA-F]{3,6}\b' gui/ --include='*.py'
```

Map each to the nearest existing token. Where a colour has no token equivalent
(row-status tints in `pandas_model.py` are the likely case), add a **named
semantic token** in Task 3's style rather than inventing a local constant.

Leave `shared/` alone — packing-tool's own 61 colours are 8.6's job, not this
slice's.

**Verification:** the grep above returns zero hits under `gui/`, and the
pixel-diff from Task 2 still matches. `ruff check . --exclude shared` clean.

## Task 5 — Commit

```
git add docs/ gui/ shared/
git commit -m "Phase 8.1: move the design system into shared/, retire hardcoded colours

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_011jGvmrc2XKHNkyFhTEHnoC"
```

Never `git add -A` — this repo's worktrees do not ignore `.venv`. Check
`git show --stat HEAD` afterwards.

Commit the packing-tool side in its own worktree with the same trailers.

---

## Notes for Stage B

- **Unverified in this plan:** the exact token names Task 3 should add, and
  whether `pandas_model.py`'s colours are status tints or something else. Both
  were left open deliberately — they are cheap to settle by reading the file,
  and guessing them into the plan would just be a confident wrong answer.
- The pixel-diff check in Task 2 is the load-bearing one. An asset move that
  silently falls back to Segoe UI passes every test in the suite.
- `run_dev.py` creates `dev-server/` — do not commit it.
