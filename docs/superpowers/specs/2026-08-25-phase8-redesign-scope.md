# Phase 8 — UI/UX redesign scoping

**Status:** awaiting design sign-off from the user. No implementation until that lands —
the roadmap task makes consultation an explicit, non-optional requirement.

This document is deliberately *not* a design spec. It is the survey + decomposition that
has to exist before a design spec can be written, so the design conversation starts from
facts instead of from a re-survey.

---

## Survey (2026-08-25)

### Shopify Tool — the reference implementation

| | |
|---|---|
| UI code | `gui/`, 22.5K lines across ~30 modules |
| Largest modules | `actions_handler.py` 2159, `ui_manager.py` 1881, `main_window_pyside.py` 1598 |
| Assets | `gui/assets/` — 19 Lucide SVG icons + Inter (Regular/Bold) |
| Asset loaders | `gui/icons.py`, `gui/fonts.py` |
| Shared widgets | `gui/components/` — only `card.py`, `form_section.py` |
| Build | PyInstaller `--onedir`, `--add-data "gui/assets;gui/assets"`, asset presence verified in CI |

### Packing Tool — structurally behind

| | |
|---|---|
| UI code | flat `src/`, 15.8K lines; `src/main.py` alone is 2771 lines |
| Assets | none — no icon set, no bundled font; styling via loose `src/*.qss` |
| Build | PyInstaller **onefile** (`main.spec`, single `EXE`, no `COLLECT`) |
| Theme | consumes `shared/theme.py` through a thin `src/theme.py` shim |

The task line *"Packer Tool should be built like the Shopify Tool, with a folder-assets
structure"* therefore means three separate things: onefile → onedir, flat `src/` → a `gui/`
package, and introducing `gui/assets/` with an icon + font set. Only the third is cosmetic.

### Theme system

`shared/theme.py` (448 lines) exposes **20 tokens** — `background`, `background_elevated`,
`text`/`text_secondary`/`text_disabled`/`text_placeholder`, `border`/`border_subtle`,
`hover`, `active_background`/`active_border`, `button_hover_light`/`button_hover_dark`,
four `accent_*`, two font families.

Notable gaps for a redesign: no elevation scale beyond one step, no semantic status tokens
(success/warning/danger/info as *roles* rather than raw accents), no spacing or radius
scale, no typographic scale.

`shared/` is **owned by `packing-tool`**. Every token change is edited there and pulled in
via `python scripts/sync_shared.py`. Any palette work is a packing-tool change first,
shopify-tool second — never the reverse.

### Hardcoded-colour debt

- shopify-tool `gui/`: **61** hits
- packing-tool `src/`: **64** hits

125 total violations of the repo's no-hardcoded-colours rule. This is mechanical cleanup,
independent of any design decision, and it is a prerequisite for a palette retune having
any visible effect.

---

## Proposed decomposition

Phase 8 is far too large for one A→B→C cycle. Proposed split into six roadmap items, each
getting its own cycle and its own worktree. Ordering is dependency-driven.

| # | Item | Depends on | Why separate |
|---|---|---|---|
| 8.1 | **Design system spec** — token set, palette (light+dark), spacing/radius/type scales, component inventory | user sign-off | Pure design. Produces the contract every later item builds against. |
| 8.2 | **Token expansion in `shared/theme.py`** + `sync_shared.py` into shopify-tool | 8.1 | Single shared-module change, landed once, both apps pick it up. |
| 8.3 | **Hardcoded-colour eradication** (125 hits, both repos) + lint rule to prevent regression | 8.2 | Mechanical, high-volume, zero design risk. Good Sonnet work. |
| 8.4 | **Packing Tool structural migration** — onefile → onedir, `src/` → `gui/` package, `gui/assets/` with icons + Inter | none (can run parallel to 8.1–8.3) | Structural refactor + build change. Riskiest item; must not be entangled with visual churn. |
| 8.5 | **Component library** — grow `gui/components/` past `card`/`form_section`, shared across both apps | 8.2, 8.4 | Needs the tokens *and* packing-tool's `gui/` package to exist. |
| 8.6 | **Layout/positioning pass + presentation debt** — per-screen restyle, incl. the three known debts below | 8.5 | The visible payoff. Everything above is groundwork. |

Known presentation debt folded into 8.6 (carried from the roadmap task):
- Session Browser status column — raw combobox, hardcoded `blue`/`darkgreen`/`red`.
- Comments column — inline `QLineEdit` per row, unused in practice (0 of 42 real sessions).
  Worth removing or rethinking rather than restyling.
- `ColumnConfigPanel` list collapse (~70px, 2–4 rows) — same scroll-area starvation as
  `docs/superpowers/specs/2026-08-23-session-setup-layout-design.md`.

---

## Open questions for the user

These three shape everything downstream and are expensive to undo, so 8.1 does not start
until they are answered.

**Q1 — How far does the palette move?**
- (a) Keep the current 20 tokens and palette; only fix the 125 violations. Cheapest, but
  "fresh colour palettes" in the task implies more.
- (b) *Recommended.* Keep the current hues as a base, expand the token set (elevation,
  semantic status roles, spacing/radius/type scales) and retune light/dark for contrast.
- (c) Full rebrand — new brand hue, both themes redrawn from scratch.

**Q2 — How deep does the Packing Tool restructure go?**
- (a) *Recommended.* Full parity: onedir + `gui/` package + `gui/assets/`, as the task
  literally asks. Real refactor of a 2771-line `main.py`; own cycle, own risk budget.
- (b) Assets only: add `gui/assets/` and the loaders, leave flat `src/` and onefile alone.
  Much cheaper, but the two apps stay structurally divergent.

**Q3 — Does layout actually change, or is this a restyle?**
- (a) Restyle in place — same screens, same navigation, new tokens and spacing.
- (b) *Recommended.* Restyle plus targeted layout fixes only where there is a known defect
  (the three debts above), leaving navigation structure alone.
- (c) Rework navigation/tab structure too. Highest risk; retrains warehouse users who use
  this daily.

A one-line answer per question is enough to unblock 8.1.
