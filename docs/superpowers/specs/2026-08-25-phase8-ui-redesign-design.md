# Phase 8 — UI/UX redesign of Shopify Tool + Packer Tool

**Status:** design / brainstorm. **One question is open for the user** (visual
direction, §6) — Phase 8's own brief makes consulting the user a hard
requirement, not a courtesy.

**Todoist:** `6hM87j3HVcc576vV` (no subtasks — this document proposes them).
**Branch:** `worktree-phase8-ui-redesign`.

---

## 1. What the brief actually asks for

Three things, from the Todoist task:

1. A modern, optimised design for **both** apps.
2. The Packer Tool "built like the Shopify Tool, with a folder-assets structure".
3. **Consult the user about design before implementing.**

Plus the presentation debt Phase 7 deliberately pushed here:

- Session Browser status combobox with hardcoded `color: blue/darkgreen/red`.
- Session Browser comments column — an inline `QLineEdit` per row, used by
  0 of 42 real sessions. Worth deleting or rethinking, not restyling.
- `ColumnConfigPanel` list collapse (~70px, 2–4 rows) — the same
  scroll-area-starvation failure mode as the Session Setup fix.

## 2. Where the two apps actually stand (measured, not assumed)

Rendered headless at the app's own default 1100×900 (`w.grab()` under
`QT_QPA_PLATFORM=offscreen`). Screenshots of all five tabs in both themes were
produced for this pass; the findings below are read off them.

**Shopify Tool** — `gui/`, 22 463 LOC across 34 modules.

| Asset | State |
|---|---|
| Theme tokens | `shared/theme.py` (448 lines), 18 colour tokens, both themes |
| Font | Inter Regular/Bold embedded in `gui/assets/fonts/` |
| Icons | 18 Lucide SVGs in `gui/assets/icons/`, recoloured via `gui/icons.py` |
| Components | **two** — `gui/components/card.py` (57 LOC), `form_section.py` (80 LOC) |
| Hardcoded hex | 41 occurrences across 8 modules (worst: `pandas_model.py`, 15) |

**Packer Tool** — `src/`, 18 036 LOC, `main.py` alone is 2 771 lines.

| Asset | State |
|---|---|
| Theme tokens | consumes the same `shared/theme.py` via a 36-line `src/theme.py` shim |
| Font | none |
| Icons | none |
| Components | none — no `components/`, no `assets/` |
| Hardcoded hex | 61 occurrences across 8 modules, + 3 named colours |

So "build the Packer like the Shopify Tool" means, concretely: give it the
`assets/{icons,fonts}` + `components/` layout it has no equivalent of, and
retire 64 hardcoded colours in favour of tokens it already imports.

### What the screenshots show

The dominant visual fact is not layout — it is **two token values**:

```python
DARK_THEME = ThemeTokens(
    background="#000000",   # pure black
    border="#FFFFFF",       # pure white
```

Every card, every table header cell, every group box is a 1px pure-white
rectangle on pure black. The app reads as a wireframe. On top of that:

- **Disabled controls are invisible.** `text_disabled="#444444"` on `#000000`
  is 2.4:1. "Run Analysis" and "Add Product to Order" render as empty boxes.
- **Nested cards double their borders** — `Load Data` > `Orders File` draws two
  concentric white frames 8px apart.
- **No surface hierarchy.** `background_elevated` exists as a token but
  `build_stylesheet()` never paints a card with it, so nothing is "raised".
- **The action row has no rank.** Analysis Results puts eight equally-flat
  buttons in one strip, and the only visually-primary control in it is the
  *theme toggle* ("Light Mode"), which outranks "Generate Reports".
- **Duplicated actions.** `Add Product to Order`, `Generate Reports` and
  `Settings` appear on both Session Setup and Analysis Results.
- **Empty states are afterthoughts.** "No analysis data" sits *outside* the
  table frame in 8pt text; Session Browser has no empty state at all.
- **The client sidebar header is broken** — the title, a stray unlabelled
  checkbox and a `⋮` button collide at the top-left on every tab.
- Roughly 25% of Session Setup's height is dead space below the last card.

## 3. The architectural finding that shapes everything

Both apps already consume one stylesheet builder: `shared/theme.py`
(`build_stylesheet` / `build_palette` / `ThemeTokens`). It is byte-identical in
both repos.

And `scripts/sync_shared.py` walks `SOURCE.rglob("*")`, creating destination
subdirectories and using `shutil.copy2`. **It already carries nested folders and
binary files with no change.** So `shared/assets/icons/*.svg`,
`shared/assets/fonts/*.ttf` and `shared/components/*.py` would sync between the
repos for free.

Consequence: the great majority of "redesign both apps" is *one file in
`shared/`*, not two parallel restyling efforts. That is the cheap path and this
design takes it.

**Direction of ownership — decided, flagged.** `shared/` is canonical in
**packing-tool** and one-way synced into shopify-fulfillment-tool. So the design
system must be *authored* in packing-tool even though the Shopify Tool is the
visual reference. This reads backwards against the brief's wording ("Packer
built like the Shopify Tool") but matches the result it asks for, and is the
only option that does not fork Inter and the icon set into two drifting copies.
Reversible if you disagree — say so and each repo keeps its own `assets/`.

### How much is reachable by tokens alone — measured, not guessed

The same two screens were re-rendered under three candidate token sets with
**no stylesheet edits at all** (`dataclasses.replace` on `DARK_THEME`). Result:

- Tokens alone remove the wireframe look — cards stop shouting, text calms down.
  That is ~12 hex values in one shared file, and both apps get it at once.
- Tokens alone do **not** fix: card fills (nothing uses `background_elevated`),
  disabled-state contrast (it gets *worse* as the ground lifts), nested double
  borders, the flat action row, empty states, the broken sidebar header, or any
  spacing.

So the work splits cleanly into a token pass (cheap, shared, immediate) and a
`build_stylesheet()` + per-screen pass (the real work).

## 4. Non-goals

- No functional/behavioural change. Phase 7 scoped the Session Browser's
  behaviour deliberately; this phase touches presentation only.
- No new UI framework, no QML, no widget library dependency.
- No Windows-only styling tricks — dev renders on Linux, prod is Windows.
- Not bumping the version string; that moves at release.

## 5. Proposed decomposition

Phase 8 is an epic. It should become these subtasks, in order — each one
PR-sized, each independently mergeable.

| # | Subtask | Repo(s) | Depends on |
|---|---|---|---|
| **8.1** | **Foundation.** Move `assets/{icons,fonts}` + `components/` into `shared/`; add the missing surface/spacing/radius tokens; retire the Shopify Tool's 41 hardcoded colours. No visual redesign — same look, tokenised. | both (authored in packing) | — |
| **8.2** | **Token pass.** Apply the chosen palette (§6) to `DARK_THEME`/`LIGHT_THEME`. Fix `text_disabled` contrast to ≥4.5:1. | shared | 8.1, §6 answer |
| **8.3** | **Stylesheet pass.** `build_stylesheet()`: paint cards with `background_elevated`, kill nested double borders, one spacing/radius scale, real focus rings. | shared | 8.2 |
| **8.4** | **Shopify screens.** Action-row hierarchy (one primary per screen; move the theme toggle out of it), de-duplicate the three repeated actions, real empty states, fix the client-sidebar header, reclaim the dead space on Session Setup. | shopify | 8.3 |
| **8.5** | **Session Browser presentation.** The Phase 7 debt: status column without hardcoded colours, delete-or-rethink the unused comments column, `ColumnConfigPanel` scroll-area fix. | shopify | 8.3 |
| **8.6** | **Packer Tool adoption.** Icons + Inter + components in the Packer; retire its 61 hardcoded colours + 3 named colours; bring its screens onto the same visual language. | packing | 8.3 |

8.1 is the only slice that is **independent of the §6 answer**, which is why it
has its own plan already (`docs/superpowers/plans/`) — Stage B is not blocked
while the direction question is open.

## 6. OPEN QUESTION — visual direction (blocks 8.2 onward)

Three candidate palettes were rendered on the real app, same screens, token
swap only. PNGs are attached to the Todoist task and in the session output.

| | Ground | Borders | Character |
|---|---|---|---|
| **A — Elevation** | `#111114` / `#1A1A1F` | `#2A2A32`, nearly invisible | Cards read as fills. Cool neutral, brighter blue accent (`#4F8DF7`). Closest to VS Code / Linear. |
| **B — Softened outline** | `#0D0D0F` / `#151518` | `#3A3A44`, still visible | Keeps today's outlined structure and the current `#007ACC` accent — just stops shouting. Smallest change, most familiar to existing users. |
| **C — Warm slate** | `#16181D` / `#1F232A` | `#2F343D` | Lifted blue-grey ground, teal active state (`#26A69A`). Warmest, furthest from today. |

**Recommendation: A.** It is the direction that actually pays off in 8.3 —
surface-fill hierarchy needs a ground light enough to raise a card above, which
`#000000` cannot do and B only barely can. B is the safe pick if warehouse
staff's familiarity with the current look matters more than the redesign.

A fourth answer is fine: "none of these, here's what I want."

## 7. Decisions taken without asking (reversible, recorded)

- Design system authored in `packing-tool/shared/`, synced out (§3).
- Palette candidates constrained to dark theme first; light theme derives.
- The unused comments column is proposed for **deletion** in 8.5, not restyling
  — 0 of 42 sessions use it.
- Screenshot tooling is throwaway (job tmp), not committed; the ~20 lines that
  render a tab headless are trivial to rewrite when next needed.

## 8. Evidence / how to reproduce

```python
os.environ["QT_QPA_PLATFORM"] = "offscreen"
w = MainWindow(); w.resize(1100, 900)
w.main_tabs.setCurrentIndex(i); app.processEvents()
w.grab().save(path)
```

**Gotcha for whoever renders the Packer:** the same approach hangs forever with
zero output — `MainWindow(config_path=...)` reaches a modal on startup, and a
modal under `offscreen` blocks with no diagnostic. Use
`faulthandler.dump_traceback_later(N, exit=True)` to find it, or stub the dialog.
