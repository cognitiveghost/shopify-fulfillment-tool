# Audit 02 — Repeat orders, inventory memory, packed-order check

Scope: repeat detection (`analysis._detect_repeated_orders`), the history
file (`core._load_history_data`, `_merge_fulfillment_history`, the write in
`_save_results_and_reports`), the Packing Tool signal (`packed_orders.py`),
`sequential_order.py`, inventory memory (`core.build_inventory_snapshot`,
`ProfileManager.save_inventory_memory`, the memory-mode load), `stock_export.py`,
`sku_writeoff.py`, and where the Repeat mark is shown (results document,
packing list, Packing Tool). Packing Tool was read, not changed: where it
records packed orders (`ProgressPublisher`, `SessionManager.update_session_metadata`)
and what it loads. Proof tests: `tests/audit/test_02_repeat_orders.py`.
Audited against `origin/main` at `f9f5aab`.

## 1. Verdict

**No, not yet.** The owner cannot yet rely on the Repeat flag to stop an
order shipping twice. The flag works in the common case: an order the run
found fulfillable, seen again on a **later day**, is flagged. It has three
gaps that can let a shipped order through unflagged:

- An order handled earlier **the same day** is never flagged, even if the
  Packer has already packed it (AUDIT-02-1).
- Raising the repeat window setting, as its tooltip suggests, makes detection
  **narrower**, not wider (AUDIT-02-2).
- One unreadable read of the history file replaces the whole history with the
  current run's orders (AUDIT-02-6).

History also records what the run *planned*, not what shipped. Orders a person
marks fulfillable never reach it, and orders held after the run are flagged as
repeats later (AUDIT-02-3, -4). The Repeat mark stops at the results screen,
where its column is hidden by default. It is not on the printed packing list
or on labels, and the Packer shows it only when the order has no customer note
(AUDIT-02-8).

In the 39 production sessions, **no order was packed twice by the Packer**.
Every same-day re-appearance followed a session that was never packed, so the
same-day gap did not cost a shipment in this data.

Inventory memory is off for all three clients, and every memory finding is
latent. It must not be switched on as it stands. A run without a stock file
reads no history and saves neither memory nor history (AUDIT-02-9).

## 2. Findings

| id | severity | summary | where | proof test | status |
|---|---|---|---|---|---|
| AUDIT-02-1 | critical | An order packed or run earlier today, in another session, is never flagged Repeat | `shopify_tool/analysis.py:873` | `test_order_packed_earlier_today_in_another_session_is_flagged` | confirmed |
| AUDIT-02-2 | critical (latent) | Raising the repeat window hides recent repeats; the setting works backwards to its tooltip | `shopify_tool/analysis.py:873`, `gui/settings/general.py:84` | `test_raising_the_repeat_window_still_flags_yesterdays_order` | confirmed |
| AUDIT-02-3 | high | An order a person marks fulfillable never reaches history; only the Packer signal can flag it later | `shopify_tool/core.py:1207` | `test_order_marked_fulfillable_by_a_person_is_flagged_next_day` | confirmed |
| AUDIT-02-4 | high | An order the run found fulfillable is recorded as fulfilled even if it is held or never shipped, and is flagged Repeat later | `shopify_tool/core.py:1207` | `test_order_held_after_analysis_is_not_a_repeat_next_day` | confirmed |
| AUDIT-02-5 | high (latent) | Numeric order numbers never match the Packer signal (number vs text) | `shopify_tool/analysis.py:893`, `shopify_tool/packed_orders.py:98` | `test_numeric_order_number_packed_yesterday_is_flagged` | confirmed |
| AUDIT-02-6 | critical | If the history file can't be read, it is replaced by this run's orders alone | `shopify_tool/core.py:770`–`780`, `:1236` | `test_unreadable_history_is_not_overwritten` | confirmed |
| AUDIT-02-7 | high | Two PCs running one client at once lose one side's history rows | `shopify_tool/core.py:1236` | `test_concurrent_runs_keep_both_sides_history` | confirmed |
| AUDIT-02-8 | high (cross-repo) | The Repeat mark doesn't reach the packing list or labels, and the Packer shows it only when the order has no note | `shopify_tool/packing_lists.py:198`, `packing-tool/gui/packer_bridge.py:147` | `test_packing_list_marks_a_repeat_order` | confirmed |
| AUDIT-02-9 | critical (latent) | A run without a stock file (inventory memory) reads no history and saves no memory, history or session files | `shopify_tool/core.py:744`, `:1065` | `test_memory_mode_run_reads_history`, `test_memory_mode_run_writes_memory_and_history` | confirmed |
| AUDIT-02-10 | high (latent) | Memory keeps one row's stock for a SKU listed on several stock rows | `shopify_tool/core.py:949`, `:980` | `test_memory_seed_sums_a_sku_listed_on_several_rows` | confirmed |

"Latent" means no production client triggers it today: all three run with a
window of 1, none has numeric order numbers, and none has inventory memory
enabled.

## 3. Findings in detail

### Where the mark comes from

An order is flagged **Repeat** when its number is in either of two sources
with a date **before** the cutoff:

1. **History** — `CLIENT_X/fulfillment_history.csv`. Every run appends each
   order it found fulfillable, dated today, and keeps the earliest date
   per order.
2. **The Packer signal** — `completed_orders` in each session's
   `session_info.json` `packing_progress`, dated by the list's `started_at`.
   Packing Tool publishes it while packing, not only at End session
   (`ProgressPublisher`), so a paused or crashed list still counts.

The two sources can disagree. History says "a run found this fulfillable".
The Packer signal says "this was packed". AUDIT-02-3 and -4 are the two
directions of that disagreement.

### AUDIT-02-1 — Same-day repeats are never flagged (critical)

**What goes wrong.** The cutoff is `today - (window - 1)` days, and a source
date must be strictly earlier. With the window at 1, anything dated today
is ignored, including an order the Packer finished this morning in a
different session.

**Scenario.** The morning session packs #1. At noon a new export is loaded
into a second session, and it still lists #1 because Shopify has not been
marked fulfilled yet. #1 is fulfillable and unflagged, so it goes onto the
afternoon packing list and ships twice.

**Root cause.** Neither source records which session a row came from. The
date is the only way detection can skip the current session's own records,
so that re-running the same export doesn't flag every order. That rule is
right and is pinned by
`test_rerunning_the_same_export_today_does_not_flag_its_own_orders`. But it
blinds detection to every other session run the same day.

**Production evidence.** ALMADERM had 20 same-day re-appearances and HERBAR
14, none flagged. In every one, the earlier session was a redo that was never
packed (ALMADERM 2026-07-02_1 → _2; HERBAR 2026-07-16_1 and 2026-07-17_1 →
2026-07-17_2), so nothing shipped twice. The mechanism is the same when the
earlier session *was* packed.

### AUDIT-02-2 — The repeat window works backwards (critical, latent)

**What goes wrong.** The tooltip says "Orders fulfilled within this many days
are marked as 'Repeat'… Increase for longer detection window". The code
treats the number as a **minimum age**: with 7, anything fulfilled in the last
6 days is ignored. Raising the setting to catch more repeats hides the
recent ones, which are the ones that matter.

**Scenario.** Window 7. #1 shipped yesterday and reappears today, and it is
not flagged.

**Production evidence: 0 exposure.** All three clients and every saved
config backup use 1.

### AUDIT-02-3 — A person's Mark fulfillable never reaches history (high)

**What goes wrong.** History is written once, inside the run, from the run's
own statuses (`core.py:1207`). Toggle and bulk Mark fulfillable
change the status later and never touch history. Such an order can only be
flagged later through the Packer signal.

**Scenario.** Stock covers one of #1 and #2, and the run picks #1. A person
holds #1 and ships #2 instead. Tomorrow's export still lists #2, and nothing
flags it unless the Packer packed it. The test proves the no-Packer case.
`test_order_packed_on_an_earlier_day_is_flagged_even_without_history` proves
the Packer case works.

**Production evidence.** ALMADERM: 74 orders were marked fulfillable by a
person, 36 of them were packed, and **0** reached history. HERBAR had 15 such
orders: 2 were packed and 1 is in history (from another session's run). 8 of
the ALMADERM orders were packed on 2026-07-01 and reappeared on 2026-07-02
unflagged. A person marked them fulfillable again in 2026-07-02_3, a session
that was never packed. The Packer build of that time didn't write
`completed_orders` (0 of 39 sessions carry it), so nothing could have
flagged them. The current Packer would.

### AUDIT-02-4 — History records the plan, not the shipment (high)

**What goes wrong.** Every order the run finds fulfillable is dated into
history, whether or not it ships. That includes orders held or removed after
the run, lists never packed, abandoned redo sessions, and a session reopened
the next day. All of them are flagged Repeat on the next working day, and a
person has to recognise the flag as false or the order never ships.

**Production evidence.** HERBAR: 15 re-appearances were flagged although no
earlier session had packed them. **5 of them were then packed for the first
time** in 2026-07-22_1, so staff shipped past the flag, correctly. The other
10 were blocked by stock anyway. AUDIT-02-3 and -4 share one root cause and
one fix: history should follow what the session ships, not what the run
proposed.

### AUDIT-02-5 — Numeric order numbers miss the Packer signal (high, latent)

Only SKU columns are forced to text at load, so a client whose order numbers
are plain digits gets a numeric `Order_Number`. That shape is real: Phase 12
Bundle 1 fixed bulk actions for it. The packing-list JSON sends
`str(order_number)`, so the Packer records `"12345"`, and
`final_df["Order_Number"].isin(...)` never matches `12345`. History still
works, because it is written and read back as numbers. The Packer signal,
which is the only source that covers AUDIT-02-3, is lost. **0 exposure**: all
production order numbers are `#`-prefixed text.

### AUDIT-02-6 — An unreadable history file is replaced (critical)

**What goes wrong.** `_load_history_data` treats any read failure other than
"file missing" the same way: a parse error, an encoding error, or any
`OSError` from the share. It logs a warning and returns an empty history. The
run then writes "empty + today's orders" over the file. All earlier history is
gone, and every past order stops being flagged.

**Scenario.** One malformed row (a stray field, a hand edit, a half-written
line from an interrupted save) or one network hiccup during the read, and the
next save leaves one day of history. The write is also a plain `to_csv` on
the share, not the atomic write ADR 0008 uses for configs, so an interrupted
save can truncate the file.

**Production evidence.** HERBAR keeps a hand-made
`fulfillment_history.backup.csv`: 226 orders dated 2025-11-27 to 2025-12-09.
The live file starts on exactly 2025-12-09, and **152 of the 226 are missing
from it**. That is consistent with a whole-file loss on that day. The data
can't show the cause.

### AUDIT-02-7 — Concurrent runs lose rows (high)

History is read at step 3 and written at step 5 with no lock. If a second PC
finishes a run for the same client between those two points, the first PC's
write discards the second's rows. The window is the length of one run.
Packed orders are still covered by the Packer signal, so this is high, not
critical. No production evidence is possible, because a lost row leaves no
trace.

### AUDIT-02-8 — The mark stops at the results screen (high, cross-repo)

| where a person decides | Repeat shown? |
|---|---|
| Results document | Filter chip and pane chip. The Repeat **column is hidden by default** (`gui/web/columns.js:35`), and no production client has saved column settings. |
| Printed packing list | No. Neither the default nor the lot layout has a note column (proof test). A client could add `System_note` to its print columns, but none of the three has. |
| Barcode / reference labels | No. Neither reads `System_note`. |
| Packer | `system_note` is shown only as a fallback for `notes` (`packer_bridge.py:147`), so an order with a customer note hides it. |

A Repeat order is still fulfillable, so it flows into every packing list,
label run and stock export like any other order. No production rule, report
filter or print layout mentions `Repeat` or `System_note`. The only reference
is the old Qt table's saved column order. Whether a Repeat should also be held
by default is a business rule, not decided here.

### AUDIT-02-9 — A memory-mode run saves nothing (critical, latent)

With inventory memory on, the GUI allows a run with no stock file and passes
`stock_file_path=None`. Core uses that same `None` as its "test mode" switch
in three places. `_load_history_data` returns an empty history (`:782`), so
**no repeat is flagged from history**. `_save_results_and_reports` returns at
its first line (`:1065`), so **memory is never updated**, and history, the
Excel report, `current_state.pkl`, `analysis_data.json` and the session info
are not written. The input files are not copied into the session either
(`:473`). Every memory-mode run therefore starts from the same stale stock,
with no write-off, and its session has no saved result to reopen.
**0 exposure**: memory is disabled for all three clients.

Once this is fixed, a second risk opens up. Re-running the same session in
memory mode would draw the session's orders from memory twice. Memory is also
written from the run's statuses, so later edits don't reach it, as in
AUDIT-02-3/-4. The fix must handle both. Neither can happen today, so both
are **unproven**.

### AUDIT-02-10 — Memory keeps one row per SKU (high, latent)

`build_inventory_snapshot` seeds every SKU with `groupby("SKU").last()`. A SKU
the run didn't touch, listed on several stock rows (lots or locations), is
remembered at its last row's quantity. `inventory_total_units`, used by the
"wrong client file?" check, counts the same way. The owner ruled in Audit 01
§6 that duplicate rows are summed. SKUs the run touched are correct, because
`Final_Stock` is already the total. **0 exposure** (memory off). WATERDROP
lists 22 SKUs on several rows, so it would be exposed.

## 4. Production check

I copied `production info/` to a scratch directory and worked only on the
copy. It holds 39 sessions: ALMADERM 25, HERBAR 8, WATERDROP 6. For each
session I took the run's statuses and `System_note` from
`fulfillment_analysis.xlsx`, the edited statuses from `current_state.pkl`,
the orders on each packing-list JSON, and the orders completed in each
`packing/*/packing_state.json`. I then followed every order across sessions.

| | ALMADERM | HERBAR | WATERDROP |
|---|---|---|---|
| orders / in more than one session | 610 / 108 | 117 / 52 | 64 / 0 |
| re-appearance after a **packed** earlier session, later day: flagged | 4 of 12 | — | — |
| same, **not** flagged (AUDIT-02-3) | 8 | — | — |
| re-appearance after an unpacked earlier session, same day: not flagged (AUDIT-02-1 mechanism, redo sessions) | 20 | 14 | — |
| re-appearance after an unpacked earlier session, later day: flagged (AUDIT-02-4) | — | 15 (5 then packed for the first time) | — |
| re-appearance, never fulfillable or packed before: not flagged (correct) | 76 | 118 | — |
| flagged although never fulfillable or packed in these sessions: from older history (correct) | — | 6 | — |
| orders packed twice by the Packer | **0** | **0** | **0** |
| orders marked fulfillable by a person / packed / in history | 74 / 36 / 0 | 15 / 2 / 1 | 0 |

The Repeat flag was also set on 15 HERBAR and 8 WATERDROP orders the first
time they appear in these sessions. Their history rows point to sessions
that aren't in this copy. The dates can't be checked: an older build re-dated
history rows on every re-run (ALMADERM rows from a 2026-07-01 run carry
2026-07-02), which `_merge_fulfillment_history` has since **fixed**. I treat
these as history from outside the copy, not as bugs.

**None of these sessions carries `completed_orders`**, because the Packer build
of that time didn't write it. The Packer signal is therefore verified by tests
only, not against production.

## 5. Verified correct

| area | what was checked | test |
|---|---|---|
| Packer signal | An order packed on an earlier day is flagged even when history lacks it. This covers AUDIT-02-3 whenever the Packer is used. | `test_order_packed_on_an_earlier_day_is_flagged_even_without_history` |
| History signal | An order in history from an earlier day is flagged; a fresh one is not. | `test_order_in_history_from_an_earlier_day_is_flagged` |
| Same-session re-run | Re-running today's export doesn't flag its own orders. The AUDIT-02-1 fix must keep this. | `test_rerunning_the_same_export_today_does_not_flag_its_own_orders` |
| History dates | A re-run keeps the earliest date per order. | `test_rerun_keeps_the_earliest_history_date` |
| Packaging write-off | Each tag counts once per order, not once per line, and only for fulfillable orders. | `test_packaging_writeoff_counts_each_tag_once_per_order` |
| Stock export, lot path | Two lines of one SKU share one allocation and are written off once, per lot, including after the session's pickle round-trip. | `test_stock_export_writes_a_repeated_sku_off_once_after_reopen` |
| Packer timing and dates | Completed orders are published while packing; the date comes from `started_at` in the warehouse's local time. | `tests/test_packed_orders.py` (existing) |
| Packer's `analysis_data.json` path | **Unreachable**, closing Audit 01's open item. `load_from_shopify_analysis` is called only from `MainWindow.start_session`, whose only caller is its own stale-lock retry. The Packer packs from the packing-list JSON, which is built from the edited state. | read: `packing-tool/gui/main_window.py:943`, `:2596` |
| Sequential numbering | Numbers are only ever added, never reassigned, so printed labels stay valid across re-runs. | `tests/test_sequential_order.py` (existing) |

## 6. Not covered

- **Stock export imported twice.** Two overlapping stock-export configs, or
  one export imported twice into the ERP, would write stock off twice. That is
  an operator step outside the app, so no test was written.
- **Orders split across two exports in different sessions.** Not tested. The
  folder merge within one session is covered by Audit 01.
- **The "first seen, flagged" orders in §4** can't be traced without the
  sessions that wrote them.
- **Labels** were checked only for whether they show the Repeat mark. Their
  output belongs to Audit 04.
- `analysis_stats.json`'s `repeated_orders_found` counts rows whose note is
  exactly `"Repeat"`. I found no reader that makes this matter, so it is not
  raised.
