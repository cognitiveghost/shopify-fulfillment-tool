# 0014 — Lot labels follow Quantity

**Status:** Accepted, 2026-09-28
**Context:** `docs/superpowers/specs/2026-09-28-lot-labels-follow-quantity-design.md`

## Context

The run writes each line's FIFO lot allocation (`Lot_Details`) once. ADR 0010
made Stock left a function of the frame after every edit, but nothing kept
lot allocations in step with `Quantity`, and both report writers believed the
lots over the quantity. In REVE 2026-09-28_1, Add product copied another
line's allocation onto two new lines; the stock export wrote 3 for a line of
1 and dropped the other SKU. The packing list would have printed 3 for both.

## Decision

**`Quantity` is the truth; `Lot_Details` only labels it** (R3,
`shopify_tool/stock_ledger.lot_parts`, the only reader for output). Per pair —
one order's lines of one SKU — the pair's quantity is walked through its lots,
clipping each. Units the lots don't cover have no lot label (blank
Годност/Партида). Edit verbs never rewrite `Lot_Details`; Add product gives a
new line none, and R3 ignores any list on a Manual line, since sessions saved
before this fix carry one copied from another SKU. The stock export also refuses to write when its per-SKU totals
differ from the fulfillable lines.

Rejected: allocating real lots at edit time from the session's stock file.
Exact labels, but a second allocator that has to agree with the run's; the
owner chose blank labels (2026-09-28).

## Consequences

- An export's quantities can no longer disagree with the order lines, whatever
  edits came before. A future bug that tries is refused, not written.
- Units added by hand, raised later, or in an order marked fulfillable after
  the run go to the ERP without a lot; the storekeeper picks it.
- A lot is never named for more units than the run allocated from it: labels
  only shrink or disappear.
- Object identity of `Lot_Details` no longer matters (undo, pickle, JSON).
