# 0010 — Stock left is derived after every edit, not adjusted by each verb

**Status:** Accepted, 2026-09-25
**Context:** `docs/superpowers/specs/2026-09-25-phase14-bundle1-stock-ledger-design.md` §2

## Context

The run writes Stock left (`Final_Stock`) once. After that, each edit verb
adjusted it with its own arithmetic: toggle added or subtracted, add product
re-checked and re-deducted the whole order, and bulk status, the five removal
verbs and every undo handler didn't touch it. Audit 01 found four high
findings (AUDIT-01-1 to -4) that were all this one design failing in a
different place. Production sessions already carry the damage: 12 SKUs in
ALMADERM 2026-07-01_2 and 3 in WATERDROP 2026-07-20_3.

## Decision

**Stock left is a function of the frame.** For every SKU listed in the stock
file, it is opening `Stock` minus the quantities on the SKU lines of
fulfillable orders. `shopify_tool/stock_ledger.with_stock_left` recomputes it:

- after every edit that changes a status or removes or adds rows;
- after every undo;
- when a saved session opens.

A verb changes rows and statuses, and never does stock arithmetic itself. A
check for whether an order can be marked fulfillable reads the same function,
with that order's own draw released.

## Consequences

- An undo handler only has to restore rows and statuses. Stock left follows.
- A saved session damaged by the old model is corrected the moment it opens.
  Its screen can then disagree with the XLSX report it saved earlier.
- A frame whose statuses were set without stock moving is re-derived too,
  for example by a run-time `SET_STATUS` rule (AUDIT-03-1). The first edit or
  the next open changes Stock left for SKUs the person didn't touch. That is
  the correction, not a new bug.
- Each edit does one pass over the frame. That is cheap at session sizes (a
  few thousand rows).
- Do not add incremental `Final_Stock +=` / `-=` code to a new verb. Write the
  rows, then call `with_stock_left`.
