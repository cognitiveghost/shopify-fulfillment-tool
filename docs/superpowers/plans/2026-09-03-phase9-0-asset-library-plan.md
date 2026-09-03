# Plan — 9.0 One asset library, shared by both apps

Spec: `docs/superpowers/specs/2026-09-03-phase9-0-asset-library-design.md`
Decisions: `docs/adr/0002-themed-glyphs-in-qss-image-properties.md`
Glossary: `CONTEXT.md`

Read the spec first. It records what was measured, including two things the
brief gets slightly wrong — `gui/icons.py` is *not* identical between the
repos, and two of the named sub-controls need no glyph.

## Shape of the work

**Two repos, two PRs, packing-tool first** — the same shape as Phase 8.6
(`packing-tool` #169 "(packing-tool half)" then this repo's #306 "(shopify
half)"). `shared/` is authored in `packing-tool` and arrives here only through
`scripts/sync_shared.py`; a `shared/` file hand-edited in this repo is
overwritten by the next sync.

Two worktrees, both named `worktree-phase9-0-asset-library`:

- `packing-tool` — Stages 1–4. Authors everything under `shared/`.
- `shopify-fulfillment-tool` — Stages 5–7. Already exists (this branch);
  receives `shared/` by sync and never hand-edits it.

Run `./scripts/setup_venv.sh` once in each. Tests are
`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest`, lint is
`.venv/bin/ruff check . --exclude shared`. Neither `python` nor `ruff` is on
PATH on this machine.

---

## Stage 1 — Move the library into `packing-tool/shared/` (no behaviour change)

1. `git mv gui/fonts.py shared/fonts.py` — byte-identical between the repos,
   moves unchanged.
2. `git mv gui/icons.py shared/icons.py`, then change its one import:
   `from gui.theme import current_tokens` → `from shared.theme import
   current_tokens`. The body already reads `current_tokens().text`, so only
   the import line moves. (`shared/navrail.py` is the precedent — same import,
   same reason.)
3. `git mv gui/assets shared/assets`.
4. Copy `message-square.svg` in from
   `shopify-fulfillment-tool/gui/assets/icons/` — the shared library is the
   union.
5. Merge the two `gui/assets/README.md` files into `shared/assets/README.md`.
   Keep the shopify one's content (it is the fuller of the two) and fix the
   paths it names: `tests/test_ui_assets.py` and `tests/test_icons.py` are now
   per-repo, and `TYPE_SCALE` lives in `shared/theme.py`, not
   `gui/theme_manager.py`.
6. Repoint importers: `gui/theme.py` (`from gui.fonts import
   load_bundled_fonts` → `from shared.fonts import …`), `gui/main_window.py`,
   `tests/test_assets.py`.

No cycle is introduced: `shared/icons.py` → `shared/theme.py` → nothing back.

**Verify:** full suite green, `ruff` clean, and `gui/assets/`, `gui/icons.py`,
`gui/fonts.py` no longer exist.

## Stage 2 — Vendor the five new glyphs

Download from the pinned tag into `shared/assets/icons/` — all five verified
to return 200 on 2026-09-03:

```
https://raw.githubusercontent.com/lucide-icons/lucide/1.31.0/icons/<name>.svg
```

`plus`, `ellipsis-vertical`, `check`, `chevron-up`, `chevron-down`.

**Pin the tag.** Lucide renames glyphs between releases; `filter` became
`funnel` in 2025 and `filter.svg` 404s on `main`.

Do **not** vendor a radio dot or toggle-knob glyph. Both are circles and QSS
draws circles with `border-radius`; the spec's § 4 records why, and 9.5 owns
that stylesheet.

**Verify:** each new file contains the literal `currentColor`. A glyph with a
baked colour renders black and vanishes against the dark theme — this is what
`test_ui_assets.py`'s second parametrised test asserts, so extending the
inventory list (Stage 4) covers it.

## Stage 3 — `glyph_url()` in `shared/icons.py`

TDD this one; it is the only new logic in 9.0. Read ADR 0002 before writing
it — the two rejected options were measured, not assumed.

Beside `icon()`:

```python
def glyph_url(name: str, color: str | None = None, size: int = 18) -> str:
    """A QSS-ready url("…") token for a themed glyph."""
```

- Substitute `color` (default `current_tokens().text`) into `_source(name)` —
  reuse the existing cached loader, do not add a second one.
- Render one `QPixmap(size, size)` through `QSvgRenderer`, exactly as
  `_render()` does. Do **not** load the SVG through `QPixmap`/`QIcon`: that
  route needs Qt's `qsvg` imageformats plugin, which the frozen build
  deliberately does not collect.
- Write to `QStandardPaths.writableLocation(QStandardPaths.CacheLocation) /
  "glyphs" / f"{name}-{sha[:8]}-{size}.png"`, where `sha` hashes the
  *recoloured* SVG source. Skip the write if the file already exists.
- Return `f'url("{path.as_posix()}")'`.

Tests, in `packing-tool/tests/test_assets.py`:

1. `glyph_url("check")` returns a token whose path exists on disk and is a
   readable PNG.
2. **The `as_posix()` rule**: assert `"\\" not in glyph_url("check")`. This is
   the whole reason the rule is written down — measured on PySide6 6.11.1, a
   backslash-spelled path in QSS `image:` draws *nothing*, quoted or not,
   while spaces in the path are fine. `str(Path)` on Windows produces
   backslashes, so the naive spelling is a silent, Windows-only blank glyph
   that no Linux test would ever catch.
3. Two different colours produce two different paths; the same colour twice
   produces the same path (the cache key is the content, so a theme toggle
   needs no invalidation).
4. An unknown name raises `KeyError`, matching `icon()`.

A stylesheet-level test is **not** part of 9.0 — no rule uses `image:` until
9.4 and 9.5. Resist adding one; it would assert a call site that does not
exist yet.

## Stage 4 — packing-tool's tests and build

1. Repoint `tests/test_assets.py` at `shared.icons` / `shared.fonts`.
2. Copy this repo's `tests/test_ui_assets.py` into `packing-tool/tests/`,
   with `ASSETS_DIR` pointing at `shared/assets` and `EXPECTED_ICONS` set to
   the union (17 existing + `message-square` + the five new = 23).
3. Copy this repo's `tests/test_icon_usage_guard.py` in, with `ICONS_DIR`
   pointing at `shared/assets/icons`. Drop its
   `test_ui_managers_icon_tables_are_vendored` case — `UIManager` is
   shopify-only.
   **If the `QStyle.SP_` guard finds offenders in packing-tool, list them in
   the PR body and skip that one test with a reason. Do not retire stock icons
   in this PR** — that is UI change riding in a file move, and it belongs to
   its own task.
4. `main.spec`: `datas=[('gui/assets', 'gui/assets'), …]` →
   `[('shared/assets', 'shared/assets'), …]`.

**Verify:** full suite green, `ruff` clean. Open the packing-tool PR:
*"Phase 9.0 (packing-tool half): one asset library in shared/"*.

---

## Stage 5 — Sync into this repo

From the shopify worktree:

```bash
.venv/bin/python scripts/sync_shared.py /home/cognitiveghost/Desktop/Projects/packing-tool/.claude/worktrees/worktree-phase9-0-asset-library
```

Pass the path explicitly. The sibling default resolves to
`.claude/worktrees/packing-tool` from inside a worktree and does not exist.

`sync_shared.py` needs no change — it already `rglob`s and creates parent
directories, so `shared/assets/**` rides along. It does **not** delete, so
confirm by hand that nothing stale landed.

**Verify:** `shared/icons.py`, `shared/fonts.py` and `shared/assets/` are
present and byte-identical to the packing-tool worktree's.

## Stage 6 — Delete this repo's copies and repoint

1. Delete `gui/icons.py`, `gui/fonts.py`, `gui/assets/`.
2. Repoint the seven importers — `gui_main.py`, `gui/main_window_pyside.py`,
   `gui/session_browser_widget.py`, `gui/theme_manager.py` (`from .fonts
   import load_bundled_fonts` → `from shared.fonts import …`),
   `gui/ui_manager.py`, and the tests under `tests/`.
3. `tests/test_ui_assets.py` and `tests/test_icon_usage_guard.py`: point at
   `shared/assets`, extend `EXPECTED_ICONS` to the same union list as Stage 4.
   Keep `test_ui_managers_icon_tables_are_vendored` — it is shopify's.
4. `tests/test_icons.py`: repoint, and add the same four `glyph_url` cases as
   Stage 3. Duplicated on purpose: `shared/` carries no tests, so each repo
   guards the library it consumes.
5. `.github/workflows/build_release.yml:96`:
   `--add-data "gui/assets;gui/assets"` →
   `--add-data "shared/assets;shared/assets"`. Leave the "Verify bundled
   assets shipped" step alone — it greps the built tree recursively for
   `package.svg` and `Inter-Regular.ttf`, so it keeps working and is what
   proves the move on Windows.

**Verify:** full suite green, `ruff check . --exclude shared` clean, and
`grep -rn "gui.icons\|gui.fonts\|gui/assets" --include=*.py --include=*.yml`
returns nothing outside docs.

## Stage 7 — Finish

`graphify update .` in both repos. Open the shopify PR: *"Phase 9.0 (shopify
half): one asset library in shared/"*, linking the packing-tool PR. Comment
both PR links on Todoist subtask `6hQVhmX52hgwf533`.

---

## Done when

Straight from the roadmap, all four checkable:

1. Both repos import icons and fonts from `shared/`.
2. No `gui/assets/` remains in either.
3. Both guard tests pass in both repos.
4. A frozen build still renders a themed icon — the Windows CI step in
   `build_release.yml`. **This is the one criterion that cannot be checked
   from the Linux dev machine**; it is checked by the release workflow, so do
   not claim it locally.

## Notes for Stage C

- Review both halves. The shopify half's `shared/` diff should be *exactly*
  the packing-tool half's, byte for byte — anything else means a hand-edit,
  which the next sync silently reverts.
- The runner opens one PR per cycle. If both cannot be open at once, push the
  shopify branch, open the packing-tool PR only, and leave the shopify half
  for the next cycle rather than merging out of order.
