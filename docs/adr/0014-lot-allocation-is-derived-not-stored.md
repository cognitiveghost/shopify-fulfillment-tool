# 0014 — Lot allocation is derived from the frame, like Stock left

**Status:** Accepted, 2026-09-28
**Context:** `docs/audit/06-second-pass.md` AUDIT-06-1,
`docs/superpowers/specs/2026-09-28-data-layer-second-review-design.md` §2.
Extends ADR 0010.

## Context

The run allocated lots (expiry/batch) per (order, SKU) and stored one list
object on every row of that pair. The stock export and the packing list deduped
on that sharing. Each edit broke it differently. Add product and rule bonus
lines copied another line's list. Removing a duplicate line left the pair's
whole allocation behind. An order made fulfillable after the run had no lots.
In production, the REVE 2026-09-28_1 export wrote off the wrong SKU and
quantity.

## Decision

**R3: every SKU line of a fulfillable order owns its lots, derived from the
session's opening lots.** `analysis.with_lots(df, lots, mode)` allocates FIFO
(earliest expiry first) to the fulfillable orders. It takes them in the run's
priority order (`_prioritize_orders`, the client's `analysis_mode`) and the
lines of each order in row order. Each line gets its own list, which sums to its
`Quantity`. Units the lots can't cover get one entry with expiry `"1"`, the
existing "no lot" marker. Held orders and no-SKU lines get `None`.

The opening lots are rebuilt from the session's own `input/inventory.csv`
(`core.session_lot_table`). The run reads the same file.

Lots are derived:
- at the end of the run, after rules settle (`core._run_analysis_and_rules`);
- on every view refresh (`MainWindow._update_all_views`), which every edit,
  undo and session open goes through.

Consumers read each row's own list and never dedupe.

## Consequences

- Add product, remove item, holds, force-fulfil, bulk verbs and undo need no
  lot code. The next refresh re-derives.
- Which order gets which lot can change after an edit: the earliest lots go to
  the orders that ship now. The export's per-lot totals don't depend on order
  sequence, only on the total demand per SKU.
- A session whose `input/inventory.csv` is gone, or a memory-mode session, has
  no lots. It exports with blank expiry/batch, and quantities stay right.
- `expiry_dt` is stored as an ISO string, so rows stay JSON-serialisable
  (undo history, AUDIT-01-12).
- Do not attach `Lot_Details` in a new verb, or share one list between rows.
  Write the rows. The refresh derives the lots.
