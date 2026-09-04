# ADR 0001 — Analysis Results renders on a web tier

- **Status:** accepted, 2026-09-03. **Build gate passed, 2026-09-04.**
- **Deciders:** repo owner
- **Scope:** `shopify-fulfillment-tool` only. Packing Tool stays entirely Qt.

## Build gate outcome (2026-09-04)

This decision was conditional on a frozen Windows build actually shipping a
working Chromium. It does. Recorded here because it is the one fact Bundles
11–14 are gated on, and it would otherwise live only in a merged PR body.

- PyInstaller `--onedir --windowed` on `windows-latest` collects
  `QTWebEngineProcess.exe` and its resources. A CI step now guards it on
  every build, so a silent regression fails the build rather than the RDP
  session.
- Qt 6.11.1 / Chromium 140.0.7339.225. Startup 0.43s, view-to-loaded 0.10s
  measured headless.
- **Cost, measured not estimated:** 716 MB / 4,095 files unzipped. The
  shipped zip goes 128 MiB → 294 MiB (+167 MiB, ×2.3). Accepted by the repo
  owner at merge (PR #314).
- Verified on Windows over RDP by the repo owner: build works, gate renders.

## Decision

Analysis Results — and only Analysis Results — renders in a `QWebEngineView`
embedded in the Qt shell. Every other screen in both apps stays Qt + QSS.

## Context

Read this before proposing that Analysis Results move back to `QTableView`.
That proposal is correct on the technical merits and is still rejected; the
reasons are below, and they are not the ones the mockups give.

The Fulfilment System v2 mockups justify the web tier with four Qt
limitations. Three of them are false against this repo:

- **Tabular figures.** Already shipped — `gui/theme_manager.py` calls
  `font.setFeature(QFont.Tag("tnum"), 1)`, and `requirements.txt` pins
  `PySide6>=6.7` in a comment naming that as the reason.
- **Sticky header row.** `QHeaderView` does this natively.
- **312-row scrolling.** A `QTableView` over a model handles 312 rows without
  virtualisation. 200-row tables already ship here.

The fourth — a container query that adds an ADDRESS column above 1600px — is
`resizeEvent` plus `setColumnHidden`.

So the web tier is not bought to obtain CSS features. It is bought because the
Qt Analysis Results screen has now been rebuilt twice (PRs #307, #308) and the
screen is still the app's weakest, and because a third Qt rebuild would be the
same team making the same trade-offs against the same widget. The v2 design
exists to change the angle of attack, and the renderer change is what makes
that change real rather than cosmetic.

The tier is deliberately capped at one screen. The v2 chain originally
allocated two; its own session 4 then deleted Info › Statistics, and the freed
slot is **not** to be spent.

## Consequences

Accepted costs:

- `PySide6-QtWebEngine` — roughly 130 MB and a separate `QTWebEngineProcess.exe`
  that PyInstaller must collect into the `--onedir` build. This repo was already
  forced off `--onefile` once, for WeasyPrint's GTK DLLs. **Proving the frozen
  build launches a `QWebEngineView` over RDP at 1366×768 gates the whole
  track** — it is the first task, alone, before any document is written.
- A `QWebChannel` bridge. Analysis Results carries selection, sort, filter, a
  column manager, per-order actions, bulk actions and Undo, so every one of
  those crosses the Qt↔JS boundary. This is the seam that decides whether the
  tier is maintainable, and the mockups do not mention it.
- Two implementations of anything that must appear on both sides. A Qt child
  window always paints above a `QWebEngineView`, so the Results page emits its
  own toast rather than reusing the Qt one.

Guardrails that keep the two renderers from drifting:

- `shared/theme.py` stays the single source of truth. `theme_css_vars(theme)`
  emits the active theme as CSS custom properties under the same token names,
  and asserts it covered every field in `_COLOR_FIELDS` minus `_ALIAS_PAIRS`.
- **No hex is ever written into a web asset.** `shared/style_lint.py` extends
  its scan to `.css` and `.html`.
- The web tier may only use what Qt also has, plus the two things it exists
  for. `box-shadow`, gradients, transitions, transforms, container opacity and
  px font sizes are banned and linted — each one is a visible seam.
- One mono face across both renderers. Consolas, because a Windows warehouse
  PC already has it. `templates/assets/fonts/` currently ships JetBrains Mono,
  which is a live seam today and shows on every SKU.

## Alternatives considered

**Keep Analysis Results in Qt** (the technically cheaper option). Rejected:
every capability argument favours it, and none of them address why the screen
is weak. Two Qt rebuilds have not fixed it.

**Move more screens to the web tier.** Rejected: the seam is a permanent tax
and every screen that crosses it doubles its own maintenance. One screen, and
the second slot stays unspent even though the design freed it.

**Ship the CSS-feature fixes in Qt and keep the current screen.** Rejected by
the same reasoning as the first alternative — it is a third patch, not a
different screen.
