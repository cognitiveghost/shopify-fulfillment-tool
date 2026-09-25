# 0013 — Rules settle stock after the simulation; they don't re-run it

**Status:** Accepted, 2026-09-26
**Context:** `docs/superpowers/specs/2026-09-26-phase14-bundle5-rule-engine-design.md` §2

## Context

The run simulates stock allocation first and applies rules second
(`core._run_analysis_and_rules`). Rules read what the simulation produced
(status, `Order_Min_Box`, tags), so they can't simply move in front of it.
Two rule actions change stock, though: `SET_STATUS` holds an order that
already holds stock, and `ADD_PRODUCT` adds lines that were never allocated
(AUDIT-03-1, AUDIT-03-2).

## Decision

After the rules run, one settle step (`core._settle_rule_changes`) corrects
the frame through the stock ledger (ADR 0010):

1. Bonus lines get their SKU's opening stock from the stock file. A SKU the
   stock file doesn't list counts as 0, which matches how the simulation
   treats it.
2. Every still-fulfillable order with a bonus line gives up its draw and
   claims it again, whole, in the simulation's priority order. An order that
   can't be covered is held and gets the simulation's reason string.
3. `with_stock_left` re-derives Stock left, which also returns the stock of
   every order a rule held.

Freed stock is not offered to orders the simulation already held, which
matches a manual hold. `SET_STATUS` can only hold, never set Fulfillable.

## Consequences

- An order a rule holds stays Not Fulfillable even if a later order could now
  ship. The operator can mark a waiting order fulfillable by hand.
- Moving rules in front of the simulation, or re-running the simulation
  after them, was rejected. The first breaks every rule that reads a
  simulation output. The second makes a hold silently promote orders nobody
  asked about.
- A new rule action that changes rows or statuses doesn't need its own stock
  arithmetic. The settle step and the ledger cover it.
