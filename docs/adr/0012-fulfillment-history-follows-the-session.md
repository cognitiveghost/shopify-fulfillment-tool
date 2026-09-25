# 0012 — Fulfillment history follows the session, and detection compares sessions, not dates

**Status:** Accepted, 2026-09-25
**Context:** `docs/superpowers/specs/2026-09-25-phase14-bundle3-repeat-history-design.md`,
`docs/audit/02-repeat-orders.md` (AUDIT-02-1 to -4)

## Context

`fulfillment_history.csv` held one row per order: the date a run first found
it fulfillable. Detection flagged an order when that date, or the Packer's
packed date, was before a cutoff of "today minus (window − 1)". With the
production window of 1, that meant anything dated before today.

That design had two failures, both caused by the date being the only thing
detection knew about a row:

- It could not tell this session's own rows from another session's. The date
  rule existed so a re-run of today's export would not flag its own orders.
  As a side effect, every other session run the same day was invisible, even
  one the Packer had already packed (AUDIT-02-1).
- History was written once, from the run's plan. An order a person marked
  fulfillable never reached it, and an order held after the run stayed in it
  (AUDIT-02-3, -4).

## Decision

1. **Every history row names the session that wrote it** (`Session` column).
   Rows written before this change have no session and keep the old date rule.
2. **A session's rows are its current fulfillable orders.** They are rewritten
   whenever the session state is saved (the run, and every edit after it):
   rows from other sessions are kept, this session's rows are replaced. An
   order keeps the date this session first recorded it.
3. **Detection compares sessions, whatever the date.** An order is a Repeat
   when a history row names a different session, a Packer row names any
   session (this one included, since packed means packed), or a legacy row
   predates today.
4. **Only live sessions count.** A row whose session is stored as
   `abandoned`, or no longer exists, is ignored. That lets a redo be
   discarded by marking the old session Abandoned.
5. **The repeat window setting is removed.** Any earlier sighting counts,
   however old. That was already the effective behaviour at the production
   value of 1.

## Alternatives rejected

- **Same day: packed only.** Same-day history from another session would not
  count, only Packer rows. This keeps redo sessions quiet with no new habit.
  It was rejected because an afternoon export would miss orders on a morning
  list that has not been packed yet, which is exactly the double shipment the
  flag exists to stop.
- **Every other session, abandoned or not.** The simplest rule, but it would
  have flagged all 34 production same-day re-appearances, every one of which
  followed an unpacked redo. A flag that is wrong that often trains people
  to ship past it.
- **Keep the window as a look-back limit.** It needed a large default to
  avoid shrinking today's unlimited look-back, and no client has asked to
  forget old orders.

## Consequences

- The redo workflow gains one step: mark the old session Abandoned in the
  Session Browser. Otherwise its orders show Repeat in the new session.
- An abandoned session that was packed after all no longer protects its
  orders through history or the Packer signal. Abandoned is a claim that
  nothing shipped from it.
- The history file is rewritten on every edit, on the GUI thread, under a
  lock-sidecar (`fulfillment_history.csv.lock`) with an atomic replace. A
  failed write is logged and heals on the next save, because each save
  rewrites the session's full set of rows.
- An unreadable history file is never written over. The run warns, and
  detection runs without history rather than losing it (AUDIT-02-6).
- The file grows by one row per order per session instead of one per order.
  At production volumes that is a few thousand rows a year.
