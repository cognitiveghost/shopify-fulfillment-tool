# UI/UX Design System — Vision — Design

## Context

Phase 6 (client settings unification) and Phase 7 (session lifecycle & cross-tool sync)
already carry five-plus "fresh look" / "better UI" tasks (Profile manager/client settings,
Mappings, Rule engine, Tag categories, Packing list/Stock export, Session Setup, Session
Browser) with nothing shared to redesign *into* — no type scale, no icon system, no
reusable layout components. This doc is a vision/audit pass (same tier as the 2026-08-09
packaging-unlock audit doc, not a single implementation plan) proposing a small foundation
those tasks can build on, instead of each becoming its own bespoke, inconsistent redesign.

**Scope: `shopify-fulfillment-tool` only, for now.** `shared/theme.py` (the token/stylesheet
system) is synced one-way from `packing-tool` and must never be hand-edited here (see this
repo's `CLAUDE.md`). Everything below therefore layers on top of `ThemeTokens` from within
`gui/theme_manager.py` — the repo-owned customization seam — without touching
`shared/theme.py`. Anything that would genuinely belong upstream (e.g. if the type scale or
icon-color tokens prove useful to `packing-tool` too) is flagged as a future
packing-tool-side change, not attempted here.

**Current state, verified against code** (see also the 2026-08-11 Phase 5 doc, which covers
a separate, narrower set of items and is unaffected by this doc):
- `shared/theme.py`: flat light/dark QSS, hardcoded `font_family = "Segoe UI, sans-serif"`
  (Windows default, never embedded), scattered inline font sizes (e.g. `font-size: 10pt` on
  `QPushButton`), no type-scale concept.
- Zero custom iconography anywhere in `gui/*.py` — the 5 main tabs use OS-native
  `QStyle.SP_*` stock icons (`ui_manager.py:130-134`). No SVG icon set, no consistent visual
  language.
- Zero app/window branding — no `setWindowIcon` call anywhere in `gui_main.py` or
  `main_window_pyside.py`.
- The only bundled font files in the repo (`JetBrainsMono-*.ttf`,
  `shopify_tool/templates/assets/fonts/`) are baked into printed label templates, unrelated
  to the live GUI.
- Phase 6 already names "two competing client-settings windows" as fragments that grew
  organically (`settings_window_pyside.py`, 3595 lines), and separately lists 5 more
  settings-adjacent surfaces, each its own top-level popup window today.

## Decisions made in this brainstorm

- **Iconography**: bundle a free, open SVG icon set (e.g. Lucide, ISC license) rather than
  design custom icons or keep OS-native ones. No new Python dependency — static SVG files,
  recolored at runtime per-theme via `QPixmap` + `QPainter.CompositionMode_SourceIn`
  (standard technique for single-color line icons).
- **Typography**: embed a free, open UI font (e.g. Inter or IBM Plex Sans, SIL OFL) as
  bundled `.ttf` files loaded via `QFontDatabase.addApplicationFont()` at startup — same
  bundling mechanism already proven for `JetBrainsMono` in label templates, applied to the
  live app for the first time — paired with a formal type scale.
- **Settings structure**: consolidate the growing pile of separate settings windows into one
  Settings Hub (left-nav categories + `QStackedWidget` content), directly resolving Phase
  6's flagged "duplicate windows" problem rather than just visually harmonizing N separate
  popups.
- **Layout/placement conventions** ("repositioning buttons and windows"): a documented,
  enforced placement rule (primary action bottom-right, cancel/secondary bottom-left in
  every dialog; consistent header-row/icon-button placement; consistent margins from the
  token scale) that new dialogs follow by default — not a one-off pass over existing
  screens.

## Track 1 — Design tokens & type scale

Add a `TYPE_SCALE` (caption/body/label/heading/title → point sizes + weights) as a local
dict/dataclass in `gui/theme_manager.py`, replacing scattered hardcoded font sizes in
`shared/theme.py`'s QSS and any inline `setStyleSheet` font sizes across `gui/*.py`. Widgets
reference the scale going forward instead of hardcoding sizes. `theme_manager.py`'s
`apply_theme()` uses `dataclasses.replace()` on the `ThemeTokens` it gets from
`shared.theme.get_theme()` to override `font_family`/`font_family_mono` with the embedded
font names (Track 2) before building the stylesheet — `shared/theme.py` itself stays
untouched.

## Track 2 — Iconography & font embedding

- Bundle Lucide (or equivalent open, single-color SVG icon set) under `gui/assets/icons/`.
  Render each icon to a `QPixmap` once per theme color and cache it (standard Qt recolor
  pattern), replacing the `QStyle.SP_*` icons on the 5 main tabs
  (`ui_manager.py:130-140`) and giving dialogs/buttons a consistent icon language for the
  first time.
- Add a real window/app icon (`setWindowIcon` in `gui_main.py`) — one glyph from the bundled
  set is enough for a first pass; a full brand identity/logo is explicitly out of scope
  (see Non-goals).
- Bundle a static open font (e.g. Inter) as `.ttf` files under a new
  `gui/assets/fonts/` (or reuse `shopify_tool/templates/assets/fonts/`'s pattern), loaded
  via `QFontDatabase.addApplicationFont()` in `gui_main.py` at startup, before the theme is
  first applied.

## Track 3 — Component library & layout conventions

A small `gui/components/` module formalizing patterns that already exist ad hoc elsewhere in
the codebase:

- **`Card`** — the elevated-container look already hand-rolled per-widget in the Statistics
  tab's stat cards (`ui_manager.py:1705`, `_create_statistics_subtab`, from PR #221) and in
  `ClientCard` (`gui/client_card.py`). One base widget, reused instead of reimplemented per
  screen.
- **`FormSection`** — replaces the `QGroupBox` + `QVBoxLayout` + redundant-`QLabel` pattern
  the 2026-08-11 Phase 5 doc flagged in the Add Product dialog (three stacked `QGroupBox`
  sections, each repeating what its own title already says) with a single
  `QFormLayout`-based row builder. Any settings panel migrated into Track 4's Hub uses this
  instead of hand-rolled group boxes.
- **Placement conventions** — documented and applied by construction in `Card`/`FormSection`
  usage: primary action bottom-right, cancel/secondary bottom-left in every dialog;
  consistent header-row layout (icon buttons via Track 2 instead of the current plain-text
  `"☰"` sidebar-toggle button in `ui_manager.py:159`); consistent margins/spacing pulled
  from Track 1's tokens instead of per-widget magic numbers. New dialogs follow this by
  default; existing screens adopt it incrementally as they're touched (Track 5).

## Track 4 — Settings Hub

One window: left-nav categories (Client Profile, Mappings, Rule Engine, Tag Categories,
Packing List & Stock Export) + right-side `QStackedWidget` content, built from
`Card`/`FormSection`. Directly resolves Phase 6's flagged "two competing client-settings
windows" and gives every future settings-adjacent feature one obvious home instead of a new
top-level popup each time.

**Direct dependency, not incidental**: Track C from the 2026-08-09 packaging-unlock audit
doc (splitting `settings_window_pyside.py`, 3595 lines, before Phase 6's UI work lands on
top of it) is the structural prerequisite for this Hub — its nav/content-stack shape needs
those module boundaries to exist first. Track C was already recommended to run before Phase
6; this doc doesn't change that recommendation, it explains why Track C matters more than
originally framed (scaffolding for the Hub, not just risk reduction).

## Track 5 — Migration path for Phase 6/7's existing "fresh look" tasks

Once Tracks 1-4 exist, Phase 6's remaining UI tasks (Mappings, Rule engine, Tag categories,
Packing list/Stock export) become "migrate this panel's content into the Hub using
`Card`/`FormSection`" instead of four separate from-scratch redesigns — smaller, more
consistent diffs per item. Phase 7's Session Setup/Session Browser aren't settings surfaces
and aren't required to touch the Hub, but can adopt the tokens/icons/component patterns
opportunistically when next touched. Phase 5's items (already speced separately) are
unaffected and proceed independently.

## Non-goals

- No direct edits to `packing-tool`/`shared/theme.py` — flagged as a future cross-repo
  change if this direction proves out, not attempted here.
- Not re-scoping Phase 5 (separate doc, separate open decision already pending: the
  Manage-Table-Columns `QTreeWidget` vs. `QListWidget`-with-headers call).
- Not the Analysis-run freeze fix (Todoist `6hFm6xj6w9gFFQQV`) — orthogonal correctness bug,
  unaffected by any of this, still highest daily-use priority per the 2026-08-09 audit.
- Not a full rebrand/logo design — one bundled-set glyph covers "the app has no icon
  anywhere"; a real brand identity is a separate, much bigger ask if ever wanted.
- Not migrating every existing window in one shot — foundation (Tracks 1-3) + one flagship
  consumer (Track 4); everything else adopts incrementally as it's touched (Track 5), same
  incremental spirit as Phase 6's existing task-by-task list.

## Recommended sequencing

Extends, rather than replaces, the 2026-08-09 audit's queue:

1. **Track A** (2026-08-09 audit) — Analysis-run freeze fix. Unchanged, do first — highest
   daily-use payoff, orthogonal to everything in this doc.
2. **Tracks 1-3 here** — tokens/type scale, iconography/fonts, component library + layout
   conventions. No dependency on Track C; can start right after Track A.
3. **Track C** (2026-08-09 audit) — settings structural split. Can run in parallel with
   Tracks 1-3; required before Track 4 here.
4. **Track 4 here** — Settings Hub (needs Track C done, consumes Tracks 1-3).
5. **Phase 6, remaining UI tasks** — now smaller: migrate into the Hub (Track 5).
6. **Phase 5** — independent, can interleave anywhere.
7. **Track B** (2026-08-09 audit) — pypdf → pikepdf migration, opportunistic, unchanged.
8. **Phase 7** — last, unchanged; Session Setup/Browser optionally adopt the component
   library.

## Testing

No existing test coverage for theming/iconography/layout (expected — this is visual/UX
work). Whoever implements each track should add what's checkable without a full GUI test
harness: Track 1/2 — a self-check asserting the embedded font registers via
`QFontDatabase.addApplicationFont()` and the type-scale tokens resolve to expected point
sizes (mirrors `shared/theme.py`'s own `__main__` self-check pattern). Track 3 —
`Card`/`FormSection` construction tests with stub data (no full window needed). Track 4 —
a `TableConfigManager`-style state test if the Hub persists its own nav-selection state.

## Next steps

Same as the 2026-08-09 audit doc: this is a vision/audit doc, not one implementation plan.
Each track (1-4 above) is its own future `brainstorming` → spec → `writing-plans` pass when
picked up. Todoist gets updated to reflect these as new Roadmap entries, sequenced per
above, alongside the existing Phase 5/6/7 structure.
