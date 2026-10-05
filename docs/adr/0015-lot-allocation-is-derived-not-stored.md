# 0015 — Lot allocation is derived from the frame, like Stock left

**Status:** Accepted, 2026-09-28
Amended 2026-10-05 (AUDIT-07-M1): draw order and netting of negative stock rows.
**Context:** `docs/audit/06-second-pass.md` AUDIT-06-1,
`docs/superpowers/specs/2026-09-28-data-layer-second-review-design.md` §2.
Extends ADR 0010. Supersedes the rejected alternative of ADR 0014 (owner,
2026-09-28, when merging the two): ADR 0014's blank labels applied to units
the run never allocated, and with derived lots every unit the opening lots
cover has one. ADR 0014's output side stands: `stock_ledger.lot_parts` fits
each line's own lots to its `Quantity`, and the stock export refuses totals
that differ from the lines.

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
session's opening lots.** `analysis.with_lots(df, lots, mode)` draws undated,
unbatched lots first, then dated or batched lots, earliest expiry first, for the
fulfillable orders. It takes them in the run's
priority order (`_prioritize_orders`, the client's `analysis_mode`) and the
lines of each order in row order. Each line gets its own list, which sums to its
`Quantity`. Units the lots can't cover get one entry with expiry `"1"`, the
existing "no lot" marker. Held orders and no-SKU lines get `None`.

The opening lots are rebuilt from the session's own `input/inventory.csv`
(`core.session_lot_table`). The run reads the same file. The opening lots net
negative stock rows: each against the lot with the same expiry and batch first,
any remainder in draw order, so a SKU's lots sum to its stock total.

Lots are derived:
- at the end of the run, after rules settle (`core._run_analysis_and_rules`);
- on every view refresh (`MainWindow._update_all_views`), which every edit,
  undo and session open goes through.

Consumers read each row's own list through `stock_ledger.lot_parts` and
never dedupe. A Manual line's lots are derived like any other line's.

## Consequences

- Add product, remove item, holds, force-fulfil, bulk verbs and undo need no
  lot code. The next refresh re-derives.
- Which order gets which lot can change after an edit: the earliest lots go to
  the orders that ship now. The export's per-lot totals don't depend on order
  sequence, only on the total demand per SKU.
- A session whose `input/inventory.csv` is gone, or a memory-mode session, has
  no lots. It exports with blank expiry/batch, and quantities stay right.
- The 2026-10-05 amendment moved which lots ship first: undated, unbatched
  stock used to ship last and now ships first, so for every client with lot
  columns the lot labels on packing lists and stock exports changed. Lots never
  promise more than the SKU total, so a lot column no longer changes which
  orders are fulfillable.
- `expiry_dt` is stored as an ISO string, so rows stay JSON-serialisable
  (undo history, AUDIT-01-12).
- Do not attach `Lot_Details` in a new verb, or share one list between rows.
  Write the rows. The refresh derives the lots.
