# Phase 8 roadmap — UI/UX redesign, mockup-driven

**Date:** 2026-08-26
**Design contract:** `docs/superpowers/specs/2026-08-26-phase8-unified-design-system.md`
**Replaces:** the 2026-08-25 decomposition (8.1–8.6) and its three scope/spec docs, all
deleted in this commit. The old plan was written before the mockups existed; it planned a
design conversation that has now happened in Claude Design instead.

**Written for the cron runner** (`~/automation/claude-roadmap-runner/`). Every item below
is sized for one A→B→C cycle and states its Stage A / B / C content explicitly, because the
runner does *exactly one stage of one task per tick* and starts each stage from a fresh
context. §4 is a fully worked example of one item moving through the pipeline.

---

## 1. What survived the replan

The old plan is not uniformly dead — checking `origin/main` before rewriting it turned up
one item already shipped and one already correct:

| old item | verdict |
|---|---|
| 8.1 design spec + nav map | **superseded.** The mockups are the design conversation. Docs deleted. |
| 8.2 token expansion | **shipped** — PR #294 is on `main` @ `56e3553`. Only a six-token delta remains (spec §3). Its plan doc is deleted as shipped-work debris. |
| 8.3 hardcoded-colour eradication | **unchanged.** 125 hits; the mockups do not touch it. |
| 8.4 packing-tool structural migration | **unchanged.** Structural, not visual. |
| 8.5 component library | **re-derived.** Old list was defect-driven guesswork; the mockups name the six components that actually appear on a screen (spec §5). |
| 8.6 layout/nav | **split.** Ungated shell screens (1d/1e/1f) separate from the gated Analysis Results direction. |

Numbering restarts to avoid collision with the deleted items' Todoist history.

---

## 2. Items

Dependency-ordered. **Only 8.8 is gated on a user decision** — everything else can run the
moment its dependency merges.

| # | item | depends on | repo | stage-A model note |
|---|---|---|---|---|
| **8.0** | Pick the Analysis Results direction: 1a / 1b / 1c | — | — | **Human decision. Not an agent task.** |
| **8.1** | Token delta + contrast class-fix | — | packing → sync | small, high-value; do first |
| **8.2** | Type scale `display_xl` + desk/floor density | 8.1 | shopify | |
| **8.3** | Hardcoded-colour + hardcoded-size eradication + lint rule | 8.2 | both | mechanical, high volume |
| **8.4** | Packing Tool structural migration | — | packing | riskiest; runs parallel to 8.1–8.3 |
| **8.5** | Component library — the six from spec §5 | 8.2, 8.4 | shopify → shared | |
| **8.6** | Shell: NavRail + CommandBar wired into both apps | 8.5 | both | nav commits separate from restyle |
| **8.7** | Screens 1d Session Setup, 1e Session Browser, 1f Tools | 8.6 | shopify | expect this to split further |
| **8.8** | Analysis Results, per the 8.0 decision | 8.0, 8.7 | shopify | **blocked until 8.0 answered** |
| **8.9** | Packing Tool screens: Packer Mode, Session Browser, dialogs | 8.5, 8.4 | packing | Parcker §12–14 |

### 8.1 — Token delta + contrast class-fix

Authored in **`packing-tool/shared/theme.py`**, pulled here with
`python scripts/sync_shared.py`. Never the reverse — `shared/` is owned by packing-tool.

The whole change is spec §3, items 1–7: add `surface_sunken`, move dark `surface` to
`#101014`, add `accent_fill_hover` / `accent_fill_active`, re-point `button_hover_*`,
extend `_COLOR_FIELDS`, and — the part that matters — make `validate_theme` loop
`on_accent` over all three fills and every foreground over all four planes.

> **This fixes a live AA failure.** `button_hover_dark #2D9FE8` behind white label text is
> **2.90:1** on `main` today. `shared/theme.py:309` already carries a `ponytail:` comment
> naming the gap; delete it as part of the fix.

- **Stage A** — no brainstorm needed; the design is settled in spec §2/C1 and §2/C4 with
  measured ratios. Write the plan straight from spec §3. If Stage A finds itself
  re-deriving hex values, it is doing the wrong thing.
- **Stage B** — edit packing-tool's `shared/theme.py`, run `sync_shared.py`, extend
  `tests/test_theme_contrast.py` with the §7 tests 1 and 2.
- **Stage C** — review that the alias re-point did not change any *light*-theme rendering
  (`button_hover_light` was already `#005A9E`, so light is a no-op — say so in the PR).

**Acceptance:** spec §7 tests 1 and 2 pass in both repos. `git grep '#2D9FE8'` is empty.

### 8.2 — Type scale + density

`gui/theme_manager.py` only; no `shared/` change, so no sync.

Add `display_xl` (28 pt, bold) to `TYPE_SCALE`. Add a density flag with two profiles per
spec §2/C3, defaulting to `desk` in this repo. Add a `tabular_nums()` QSS helper for
numeral columns.

- **Stage A** — one real decision: where the density flag is stored and how a widget reads
  it. Recommend `QSettings` alongside the theme preference and a `ThemeManager.density`
  property, mirroring `get_current_theme()` — the seam already exists.
- **Stage B** — implement; extend `tests/test_type_scale.py`.
- **Stage C** — confirm no widget hardcodes a control height that the flag should own.

**Acceptance:** `font_css('display_xl')` returns 28 pt; switching density changes control
height and `body`/`caption` only — a test asserts colour and radius are untouched.

### 8.3 — Eradication + lint rule

Mechanical, high volume, zero design risk. 125 known colour hits (shopify `gui/` 61,
packing `src/` 64) plus font-size literals. Also migrates `accent_*` call sites to
`status_*` role names.

**Record the exact regex used as the completion measure** — re-greps vary by a few either
way, so chasing the number 125 is a trap.

- **Stage A** — plan the regex and the file batches, not the individual edits.
- **Stage B** — the long stage. Batch by file; run the gate between batches.
- **Stage C** — the lint rule is the deliverable that matters; review it for false
  negatives (CSS keywords, `palette(...)` roles, f-string interpolation).

**Acceptance:** spec §7 tests 3, 4 and 5 pass; lint rule wired into CI.

### 8.4 — Packing Tool structural migration

Full parity with Shopify Tool: PyInstaller onefile → onedir, flat `src/` → a `gui/`
package, and `gui/assets/` with the Lucide set + Inter. The 2 771-line `src/main.py` gets a
real refactor.

**Keep this isolated from every visual item** so a broken Windows build can be bisected
without palette churn in the diff. It is on the critical path for 8.5 and 8.9.

- **Stage A** — the package boundary is the design work. Nothing cosmetic.
- **Stage B** — expect this to be the longest Stage B in the phase. If it does not fit,
  narrow it (assets first, package split second) rather than fanning out to subagents.
- **Stage C** — the Windows build is the review, not the diff.

### 8.5 — Component library

Exactly the six in spec §5: NavRail, CommandBar, StatusChip, StatCard/KpiStrip,
ContextualSelectionBar, FilterBar. **Nothing beyond.** `StatusDot` already exists in
`shared/theme.py` — reuse it, and change it to take a role name rather than a hex string.

Also lands the four-variant button hierarchy (primary / secondary / ghost / danger) as a Qt
property + QSS attribute selector, replacing the global "every `QPushButton` is accent
blue" rule.

- **Stage A** — decide `gui/components/` vs `shared/` for each of the six. StatusChip and
  StatusDot are used by both apps and belong in `shared/`; the rest can start in shopify's
  `gui/components/` and move when 8.9 needs them. Do not pre-move.

### 8.6 — Shell

NavRail (56 px, `surface_sunken`, no border) and CommandBar wired into both apps' main
windows, replacing the tab bar and the 70 px client-card sidebar.

**Two hard guardrails, non-negotiable** (spec §6): navigation commits separate from
cosmetic restyle; structure and labels never change in the same release — the rail ships
with the old labels verbatim.

### 8.7 — Shell screens 1d / 1e / 1f

Valid whichever direction wins 8.0. Expect to split into three cycles — take 1e first, it
carries the presentation debt (status combobox, unused comment column, ColumnConfigPanel
collapse) and so has the highest defect-per-diff ratio.

### 8.8 — Analysis Results *(blocked on 8.0)*

Do not start Stage A until the Todoist 8.0 task is checked off with the chosen direction in
a comment. If a runner tick picks this up while 8.0 is open, **stop and say so** — do not
pick a direction to unblock yourself.

### 8.9 — Packing Tool screens

Parcker §12–14: Packer Mode (the scan verdict uses `display_xl`, floor density),
Session Browser (the seven-state table in spec §4), dialogs. Parcker's migration table
names the exact literals to replace, file by file: `sessions_list_widget.py`,
`client_selector_widget.py`, `worker_selection_dialog.py`, `packer_mode_widget.py`,
`metrics_tab.py`.

One item there is an API change, not a restyle: `show_notification(text, color)` becomes
`show_notification(text, role)`. Callers choosing colours is what makes the palette
unvalidatable at the call site.

---

## 3. Rules the runner must apply to this phase

Beyond the standing `prompt.md` contract:

1. **`shared/theme.py` is authored in `packing-tool`.** Any token change is a packing-tool
   edit plus `python scripts/sync_shared.py` from shopify-fulfillment-tool. Editing
   shopify's copy directly is a defect the sync will silently overwrite.
2. **The ten frozen aliases are read-only.** `background`, `background_elevated`, four
   `accent_*`, `active_background`, `active_border`, `button_hover_light/dark`. Existing
   call sites may keep reading them until 8.3 migrates them; **no new call site may.**
3. **Never re-derive a hex.** Every value is in the spec with a measured contrast ratio. A
   stage that finds itself computing colours is off-plan — re-read the spec instead.
4. **One primary button per screen** is a review item at Stage C, not a style preference.
5. **8.8 is gated.** See above.
6. **Design mockups are readable, not authoritative over the spec.** Where a mockup and
   `2026-08-26-phase8-unified-design-system.md` disagree, the spec wins — it is the merge,
   and the mockups predate it. Raise the disagreement in the Agent Handoff task.

---

## 4. Worked example — 8.1 through the cron pipeline

This is what one complete item looks like end to end. Reuse the shape for the rest.

### Tick 1 — Stage A (Opus)

Dispatcher reads `next_stage: A`, launches Opus.

**`state.md` before:**

```
active_task: none
next_stage: A
worktree: none
pr: none
open_question: none
```

Agent does: Step 0 (reads `state.md`, sees no active task) → Step 0.5 (no PR to reconcile)
→ opens the Roadmap section, takes the topmost unchecked subtask under Phase 8 → creates
the worktree → reads **only** the spec named in the task description → writes the plan.

```bash
cd ~/Desktop/Projects/shopify-fulfillment-tool
git fetch origin
git worktree add .claude/worktrees/worktree-phase8-token-delta \
    -b worktree-phase8-token-delta origin/main
```

Plan lands at `docs/superpowers/plans/2026-08-26-phase8.1-token-delta-plan.md`, committed
and pushed. No brainstorm — the task description says the design is settled.

**`state.md` after:**

```
active_task: 8.1 Token delta + contrast class-fix (todoist <id>)
next_stage: B
worktree: .claude/worktrees/worktree-phase8-token-delta
branch: worktree-phase8-token-delta
plan: docs/superpowers/plans/2026-08-26-phase8.1-token-delta-plan.md
pr: none
open_question: none
```

**Todoist comment on the subtask:**
> Stage A done. Branch `worktree-phase8-token-delta`, plan
> `docs/superpowers/plans/2026-08-26-phase8.1-token-delta-plan.md`. No brainstorm — spec §3
> is the design. Next: Stage B.

**Agent Handoff comment** (judgment only, not status):
> `sync_shared.py` must run from the shopify worktree, not from `main` — PR #294 changed
> it to work from a worktree, so this is fine, but the packing-tool edit happens in
> packing-tool's own checkout first. Two repos, one branch name.

### Tick 2 — Stage B (Sonnet)

Reads `state.md`, sees `next_stage: B`, reuses the **same** worktree. Runs
`superpowers:executing-plans`, declines the offer to switch to
`subagent-driven-development`.

Gate before finishing:

```bash
cd ~/Desktop/Projects/shopify-fulfillment-tool/.claude/worktrees/worktree-phase8-token-delta
QT_QPA_PLATFORM=offscreen python -m pytest
ruff check . --exclude shared
```

Commits **and pushes** — an unpushed Stage B is lost if the VM is rebuilt. Sets
`next_stage: C`.

### Tick 3 — Stage C (Opus)

Same worktree. `superpowers:requesting-code-review` (the one sanctioned subagent), applies
the straightforward fixes, then:

```bash
gh pr create --draft --title "Phase 8.1: token delta + on_accent contrast class-fix" \
  --body "Closes the 2.90:1 hover failure and extends validate_theme to all three fills."
```

Ticks the Todoist subtask, comments the PR link, runs `graphify update .`, sets
`next_stage: A`. **Does not merge.**

### Tick 4 — Stage A again, reconciling

Step 0.5 finds a PR in `state.md`:

```bash
gh pr view <n> --json state,mergedAt
```

- **merged** → close the Agent Handoff task, clear the PR line, pick up 8.2.
- **open** → correct `next_stage` and stop; the user has not merged yet.
- **closed unmerged** → record it and ask before redoing.

### What a Stage-A stop looks like

8.8 is the case this phase will actually hit. The correct behaviour is to end the turn with
the question, not to pick a direction:

> Phase 8.8 (Analysis Results) is gated on task 8.0 — the choice between **1a Ledger**
> (safest, 9 columns, everything maps to an existing widget), **1b Order & detail** (312
> rows instead of 1 842, right-hand detail pane) and **1c Triage** (three lanes + stock
> pressure strip, biggest payoff, new IA). I recommend **1b**: it fixes the unit — which is
> the actual complaint — without the IA rewrite 1c needs. Which direction should 8.8 build?

`state.md` keeps `next_stage: A` and records `open_question:` so the next tick does not
restart the work.
