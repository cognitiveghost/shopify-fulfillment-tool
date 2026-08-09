# Packaging-Unlock & Perf/Architecture Audit — Design

## Context

`28eb210`/`52c49da` (merged to `main`) switched the Windows release from a single
`pyinstaller --onefile` `.exe` to `--onedir` (zipped folder), driven by `blabel`/WeasyPrint
needing GTK/Pango DLLs for the new HTML/Jinja2 label rendering — a single-file exe can't
self-extract a DLL tree reliably. `gui_main.py` now does explicit `os.add_dll_directory()`
setup (`configure_frozen_weasyprint_env()`) before any Qt import.

This doc answers two questions raised after that shift: (1) what does onedir packaging
concretely unlock that onefile didn't, and (2) independent of packaging, what GUI/backend
improvements are worth pulling forward, given the app already has a 20-task phased roadmap
(Phase 5-7, Todoist section `Roadmap — Shopify Tool`) that doesn't yet cover them.

Scope: `shopify-fulfillment-tool` only (not `packing-tool`). This is an audit/reprioritization
doc, not an implementation plan — each track below gets its own `writing-plans` pass when
picked up, same as Phase 1-7 already do.

## What onedir concretely unlocks

Onefile's self-extraction model makes any dependency needing its own native shared libraries
(DLLs alongside the interpreter, not just importable `.pyd`s) fragile — that's the literal
reason blabel/WeasyPrint forced this migration. Onedir removes that constraint. Concretely:

1. **`pypdf` → `pikepdf` becomes low-risk** (Track B below) — previously deferred specifically
   because bundling another native dependency into a onefile exe was risky.
2. **Startup time**: onefile self-extracts to a temp directory on every launch; onedir runs
   directly from already-unpacked files. Not measured on a warehouse PC yet, but very likely a
   free win — worth a stopwatch check next time someone's on a production machine.
3. **Windows SmartScreen/AV friction**: a folder of recognizable exe+DLLs reads as less
   suspicious to Defender than a packed self-extracting single binary — plausibly less
   "unknown publisher" friction when rolling updates out to warehouse PCs. Minor, unverified,
   but real.

No other current or near-term dependency has a comparable native-library story — this list is
intentionally short rather than padded.

## What's explicitly out of scope here

Phase 5 (table/stats UX), Phase 6 (client settings unification), Phase 7 (session lifecycle
& cross-tool sync) already cover 20 UI/UX refactor tasks in the Todoist roadmap. This doc does
not re-propose any of them — see Roadmap reprioritization below for how the three tracks below
interleave with that existing queue instead of duplicating it.

## Track A — Analysis-run freeze (quick-fix/spike, not an epic)

**Problem**: existing backlog item ("Optimisation: Analysis run" — UI freezes a couple seconds
on every analysis run, regardless of batch size) was never folded into a phase.

**Root-cause hypothesis**: `core.run_full_analysis` already runs off the main thread
(`gui/actions_handler.py:171`, via `QThreadPool`/`Worker`), so this isn't a "forgot to
background it" bug. "No matter size of batch" points at a **fixed-cost synchronous step**
rather than something that scales with data — most likely `on_analysis_complete`
(`gui/actions_handler.py:194`), which runs on the main thread (it's a Qt signal handler) and
performs `StatsManager` network I/O over the UNC file share (`gui/actions_handler.py:228`)
after the worker already returned. Needs confirming with profiling/logging timestamps, not
assumed as final — that's the job of the `systematic-debugging` skill when this is picked up.

**Why it matters most**: this runs on every analysis, on every warehouse PC, every day — the
highest-frequency interaction in the whole app. Higher daily impact than any single Phase
5/6/7 window redesign.

**Track type**: quick-fix/spike per the repo's own workflow guide — root-cause fix, regression
test, PR. No separate spec/plan needed; `systematic-debugging` skill handles it directly.

## Track B — `pypdf` → `pikepdf` migration

**Scope**: `shopify_tool/pdf_processor.py`'s Reference Labels overlay (`create_reference_overlay()`,
currently `pypdf.PdfReader`/`PdfWriter`) moves to `pikepdf`, which wraps the native `qpdf`
library — better handling of malformed/varied courier-provided PDFs, which is exactly what
this overlay job deals with (stamping a barcode onto PDF pages courier software produced, not
this app).

**Why it was deferred**: explicitly named in `docs/superpowers/specs/2026-08-07-blabel-label-rendering-design.md`'s
non-goals as "independent of this patch" — never scheduled anywhere since. The blocker was
packaging risk (another native dependency in a onefile exe); that blocker is gone now that the
GTK-DLL-bundling pattern exists and is proven in production CI.

**Track type**: small, self-contained epic. Not urgent enough to jump the queue alone —
opportunistic, do whenever Reference Labels (D-2) gets touched again.

## Track C — Structural split ahead of Phase 6's UI pass

**Problem**: `gui/settings_window_pyside.py` (3595 lines), `gui/actions_handler.py` (2131
lines), and `shopify_tool/profile_manager.py` (1872 lines) are the three largest files in the
codebase. Phase 6 already flags "two competing client-settings windows" as fragments of one
settings surface that grew organically — that's a symptom of the same file, not a separate
problem.

**Why this should come before, not after, Phase 6's UI work**: redesigning UI inside a
3595-line file multiplies the risk and review cost of every subsequent edit in that area.
Splitting first (module boundaries, one settings surface instead of two windows) makes Phase
6's actual "fresh UI look" tasks smaller and safer diffs.

**Track type**: epic — `brainstorming` → spec → `writing-plans` → plan, same as Phase 6 itself
would need. This is a reordering of Phase 6's existing scope, not new scope: the "resolve
duplicate client-settings windows" task already in Phase 6
(`Profile manager: review logic/backend, resolve duplicate client-settings windows`) is
effectively Track C — this doc recommends doing that task *first*, before Phase 6's other four
UI-focused tasks.

## Roadmap reprioritization

Recommended queue order, replacing the current flat Phase 5 → 6 → 7:

1. **Track A** (quick-fix, do now — cheap, highest daily-use payoff)
2. **Track C** (Phase 6's settings-split task, pulled forward — structural work before UI work
   lands on top of it)
3. **Phase 5** (table/stats UX — unaffected by A/C, can run independently)
4. **Phase 6, remaining tasks** (UI pass on the now-split settings surface: Mappings, Rule
   engine, Tag categories, Packing list/Stock export settings)
5. **Track B** (opportunistic — whenever Reference Labels/D-2 is next touched)
6. **Phase 7** (unchanged — already last, riskiest, needs `packing-tool` cross-repo state)

## Next steps

This doc is the record of the audit and the reprioritization decision. Todoist gets updated to
match (Track A/B/C added, Phase 6 reordered). Each track still gets its own implementation pass
when picked up — Track A goes straight to `systematic-debugging` (no spec needed), Tracks B and
C go through `brainstorming` → `writing-plans` individually when started, same pattern as
Phase 1-7 already use.
