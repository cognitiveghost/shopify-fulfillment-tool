# ADR 0005 — The results document owns its view state

- **Status:** accepted, 2026-09-11 (Phase 9 Bundle 12)
- **Deciders:** repo owner, via the Bundle 12 spec
- **Scope:** the web tier's results document and its bridge

## Decision

Sort, search, filter chips, column widths and the selection gesture live in
the page. Python owns the data, which crosses as `orders` and `summary`. It
hears only outcomes (`setSelection`) and commands (`openExport`,
`openScreenMenu`).

The Bundle 11 catalogue's `setSort`, `setFilterText` and `setFilterChips`
slots are removed.

## Context

Bundle 11 fixed a bridge catalogue before any document existed. That
catalogue sent sort and filter state to Python, and its rule 5 ("results come
back as property changes") implied that Python would filter and push the
narrowed `orders` back.

When Bundle 12 came to build the document, nothing in Python read that state.
Reports and exports work on fulfillable orders, not on the view. The
`FulfillmentFilterProxy` that owned filtering in the Qt tier is deleted with
the Qt table. Meanwhile, all 312 orders, each with its lines nested, are
already in the page.

## Consequences

- Filtering a keystroke costs no round-trip. It re-renders about 20 windowed
  rows.
- Filter and sort semantics are tested through Chromium, not in pure Python.
  The KPI numbers stay in Python (`results_summary`), because they count the
  whole session, not the view.
- The selection is filtered in the page before it is reported, so Python never
  sees an order the operator cannot see. A bulk action (Bundle 14) cannot reach
  a hidden row.
- **If a Python feature ever needs what is on screen** ("export what I see"),
  add a slot that reports the visible order numbers. Do not move filtering back
  to Python.

## Alternatives considered

**Python filters and pushes the narrowed `orders`.** This keeps one filter
implementation in pytest's reach. Rejected: it pushes a 312-order payload per
keystroke, it keeps a second copy of the view state for no consumer, and it
makes the selection's "still visible" rule depend on round-trip timing.

**Page filters, and also reports its state to Python.** This is the Bundle 11
catalogue as written. Rejected: three slots with no caller are exactly the
speculative surface this phase keeps deleting. They can be added the day a
consumer exists.
