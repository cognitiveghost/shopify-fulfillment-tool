# 0023 — Repeat means packed

**Status:** Accepted, 2026-10-27
**Context:** `docs/superpowers/specs/2026-10-27-patch-2-4-3-bug-fixes-design.md` (section 5). Owner decision,
runner question 88. Supersedes part of ADR 0012 (rule 3, detection).

## Context

ADR 0012 made an order Repeat when another live session had a fulfillment-history row for it, or the Packer had
packed it. History rows record what a run found fulfillable, so an order that was only analysed, or put on a
packing list and never packed, flagged Repeat in every later session. The owner's rule is narrower: Repeat means
packed before, in the Packer. Anything else is not a repeat.

## Decision

1. **Repeat = packed by the Packer.** An order is Repeat when `packing_progress` `completed_orders` names it in
   any live session, this one included, whether or not that run was ended.
2. **History is a record only.** `fulfillment_history.csv` is still written exactly as before, but detection
   ignores its rows.

## Consequences

- An order analysed or listed but never packed is plain in later sessions.
- Packer completions are written after every order, so an un-ended run already counts.
- The 0012 redo step (mark the old session Abandoned) still matters for packed orders: a live session's packed
  orders stay Repeat until that session is abandoned.
