# 0018: The contrast floors outrank the mockup palette

**Status:** Accepted, 2026-09-30
**Context:** `docs/superpowers/specs/2026-09-30-ui-refresh-phase1-shell-design.md`, `docs/design/ui-refresh/roadmap.md`.

## Decision

The UI refresh takes the approved mockup's palette (`docs/design/ui-refresh/mockups/component-sheet.html`) into
`shared/theme.py`, with one exception. Where a mockup value falls below a floor in `_MIN_CONTRAST_ON_PLANES`,
the floor wins, and the token gets the lightest grey that clears it (in dark mode, the darkest).

The mockup draws two kinds of line with one colour, so they are split in code:

- **Hairlines** are decorative: card edges, dividers, the sidebar's edge, and the active sidebar item's edge.
  They use `border_subtle`, which takes the mockup's pale `border` value (#E3E3E3 / #34353A). It has no floor.
- **Control edges** identify an input or a button. They use `border`, which is held at 3:1 on every plane.

`text_disabled` (3:1) and `text_placeholder` (4.5:1) are darkened the same way.

## Why

- The mockup's `border` measures 1.28:1 on white, `text_disabled` 2.05:1 and `text_placeholder` 3.45:1. The
  floors are 3.0, 3.0 and 4.5. The floors are there because warehouse operators read these screens on shared
  PCs over RDP, and a disabled control nobody can read turns into a support ticket (see the comment above
  `_MIN_CONTRAST_ON_PLANES`).
- WCAG 1.4.11 asks for 3:1 only on the lines that identify a component. Decorative lines are exempt, so moving
  hairlines to `border_subtle` keeps the mockup's look where the look matters most.
- The owner chose this over lowering the floors (2026-09-30, run 35).

## Consequences

- A screen drawn to the mockup has slightly darker input and button outlines, disabled text and placeholders
  than the mockup does. Each phase's spec lists this as a known departure and does not re-litigate it.
- Any new line in either tier has to pick a side: `border_subtle` for decoration, `border` for a control edge.
- packing-tool's mirrored floor test (`tests/test_theme.py`) needs no change, because no floor moved.

## What would reverse it

A reason to lower a floor that is about readability on the warehouse screens, not about matching a mockup.
