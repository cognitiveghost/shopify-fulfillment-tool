# Audit 09: set decoding, Packing Tool JSON, stock ledger and exports

Report only, no product code changed. Scope: `set_decoder.py`, `core.build_packing_order_data` and
`_create_analysis_data_for_packing`, the report generation path in `gui/actions_handler.py`,
`stock_ledger.py`, `stock_export.py` and `sku_writeoff.py`. Audit 04 already covered the exports' column
layout and filters, so this pass looks at correctness gaps and speed.

Evidence tags: **[confirmed-run]** reproduced with a script on the repo's `.venv` (Python 3.14, pandas
3.0.6); **[confirmed-read]** follows directly from the code; **[unconfirmed]** depends on something not
checked here.

Baseline on the benchmark frame (5,000 orders × 3 lines, no sets, no rules):

| Operation | Time |
|---|---|
| `analysis.run_analysis` | 2.29 s |
| `stock_ledger.with_stock_left` (every edit) | 0.03 s |
| `toggle_order_fulfillment` (one order) | 0.05 s |
| `core.with_order_fields` (every refresh) | 0.02 s |
| `recalculate_statistics` | 0.07 s |

The per-edit computation is cheap. The per-edit slowness on the share is the I/O from Audit 07 H2, not
pandas.

## Summary

| # | Sev | Area | Finding |
|---|-----|------|---------|
| O1 | High | speed | Set decoding takes 17.7 s on 15,000 lines, on every run that has any sets defined |
| O2 | High | speed | The Packing Tool JSON builder takes 12.7 s for 5,000 orders: in every run's save step, and per packing list on the GUI thread |
| O3 | Med | ledger | Force-fulfil and bulk "mark fulfillable" ignore SKUs missing from the stock file |
| O4 | Med | sets | Set CSV import keeps surrounding spaces, so a set like `SET-1 ` is silently never expanded |
| O5 | Med | multi-PC | Packing-list JSON is written non-atomically, and a failed `analysis_data.json` build writes an empty session |
| O6–O8 | Low | exports | See bottom |

---

## High

### O1. Set decoding copies every row in Python [confirmed-run]

`decode_sets_in_orders` (`set_decoder.py:102-154`) walks `iterrows()` over **every** order line and
`row.copy()`s each one, set or not. It then builds the result with `pd.DataFrame(list_of_series)`.
Repro: 15,000 lines with 18 columns, one set in a third of them:

```
decode 15,000 rows (5,000 sets): 17.67s -> 20000 rows
```

That is 7.7 times the whole rest of the analysis (2.29 s). It runs whenever a client has any set
defined (`analysis.py:529-546`). **Fix direction:** split the frame into set and non-set lines, leave
non-set lines untouched, and expand set lines with a merge against a flattened `(set, component, qty)`
table built once from `_components`.

### O2. The Packing Tool JSON builder is slow, and on the GUI thread for reports [confirmed-run, confirmed-read]

`build_packing_order_data` (`core.py:89-192`) runs `is_fulfillable(group, ...)` and `iterrows()` per
order. Repro: `_create_analysis_data_for_packing` takes **12.73 s for 5,000 orders**, about 2.5 ms per
order:

- It runs in every analysis save step (`core.py:1367`), so it is part of every run's wall time.
- Packing lists build their JSON with the same function (`gui/actions_handler.py:655-675`, `:800`).
  `_generate_reports` runs straight from the dialog's `reportsSelected` signal, **on the GUI thread**
  (`:600-616`). A 2,000-order packing list freezes the window for about 5 s before any file I/O.

**Fix direction:** compute fulfillable orders once for the frame (`stock_ledger.fulfillable_orders(df)`,
then membership per order), build the items with `to_dict("records")` per group, and move report
generation to a `Worker`.

---

## Medium

### O3. Force-fulfil ignores SKUs that aren't in the stock file [confirmed-run]

`stock_ledger.stock_left` only covers SKUs "listed" in the stock file (`Final_Stock` not null), and
`_short` skips any SKU not in it (`stock_ledger.py:107-128`). The run itself treats an unlisted SKU as
0 stock and holds the order. Repro: one order for 3 × `X`, where the stock file only lists `A`:

```
  Order_Number SKU  Stock  Final_Stock Order_Fulfillment_Status
0           #1   X    0.0          NaN          Not Fulfillable
shortfall: []
claim: (['#1'], [])
```

So the toggle (`analysis.toggle_order_fulfillment`) and bulk "mark fulfillable"
(`ActionsHandler.bulk_change_status` → `claim`) mark it Fulfillable with no warning, and it goes onto
packing lists and the stock export. ADR 0010 defines Stock left "for every SKU listed in the stock
file" and says nothing about unlisted ones. **Needs an owner decision:** treat unlisted as 0 (match the
run), or keep it allowed and warn.

### O4. Set import keeps spaces, and the decoder never normalises keys [confirmed-run]

`import_sets_from_csv` reads with `dtype=str` and stores `Set_SKU` and `Component_SKU` as written
(`set_decoder.py:203-256`). The decoder looks sets up with `sku in set_decoders`, against order SKUs
that `normalize_sku` has already trimmed (`analysis.py:487-489`).

```
imported keys: ['SET-1 '] {'SET-1 ': [{'sku': 'A ', 'quantity': 2}]}
order SET-1 expanded: False
```

The set line then goes to allocation as an unknown SKU and the order is held for no visible reason. The
component `A ` would not match stock `A` either. The import also reads without `utf-8-sig`, so an Excel
CSV with a BOM fails with "missing required columns". **Fix direction:** `normalize_sku` both keys on
import and when building the decoder lookup.

### O5. Packing Tool files written non-atomically [confirmed-read]

Packing-list JSON is written with `open(json_path, "w")` (`gui/actions_handler.py:802-803`), next to the
XLSX that Packing Tool on another PC opens. Audit 07 M2 covers the same pattern for
`analysis_data.json`. Separately, `_create_analysis_data_for_packing` catches every error and returns
`{"orders": [], "total_orders": 0, "error": ...}` (`core.py:232-271`). That gets saved as the session's
`analysis_data.json` and its counts, while the run reports success, so Packing Tool sees an empty
session. **Fix direction:** use `atomic_write_json`, and let a build failure fail the save step.

---

## Low

- **O6** Write-off dedupes `(order, tag)` with `Order_Number.astype(str)` and no strip
  (`sku_writeoff.py:168-187`), while every other order key in the codebase is stripped, so `1001` and
  `1001 ` count twice. [confirmed-read]
- **O7** The non-lot stock export groups by the raw `SKU` (`stock_export.py:293`), but `_check_totals`
  groups by the stripped SKU. Whitespace variants become two ERP rows and still pass the check.
  [confirmed-read]
- **O8** `prepare_export_path` stamps to the minute. A second re-export in the same minute moves the
  previous file to `old/` under a name that already exists there, overwriting the earlier archived
  copy (`stock_export.py:182-194`). [confirmed-read]

## Suggested order

1. O1 and O2: the largest wall-time cost in a run, and O2 also freezes the GUI.
2. O4: small, with the repro as its test.
3. O3: after the owner decides on unlisted SKUs.
4. O5, then the low items.
