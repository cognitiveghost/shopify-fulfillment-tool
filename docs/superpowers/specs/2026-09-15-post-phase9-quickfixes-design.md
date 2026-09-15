# After Phase 9 — quick fixes and check

**Todoist:** parent `6hWGF3XHC9Qww8j3` (Roadmap), four subtasks:
`6hWGG6753QC539WV` (sniffer), `6hWGGF33wMJ2FJ43` (inventory memory),
`6hWGGMp4qxhpMJPV` (barcodes), `6hWGGWfFpxqRFp8V` (logs tab switch).
**Brief:** 12 Windows-build screenshots on the parent task, plus the four
subtask descriptions. The screenshots carry no annotations — the defects below
were read off them.
**Canvas:** Claude Design project *Fulfilment System v2*
`75385f2c-4be2-446c-8e9d-bf90ee063ff7`, readable from this VM through
`DesignSync` (no `/design-login` needed this time — earlier bundles recorded
that it was; that is no longer true).

Classification: **bounded**, but wide. Two unrelated kinds of work are in one
batch — a data-integrity bug and a list of unfinished UI surfaces. §7 asks how
the user wants them sequenced.

---

## 1. The finding that matters: client config saves are not atomic

Screenshots 6 and 7 (Logs tab) show, within the same second:

```
ERROR  Failed to save with Windows lock — FileNotFoundError: [Errno 2] ...\CLIENT_TEST\client_config.tmp
ERROR  Failed to save with Windows lock — PermissionError: [WinError 32] The process cannot access
       the file because it is being used by another process
ERROR  Invalid JSON in client config for CLIENT_ALMA — JSONDecodeError: Extra data: line 112 column 2 (char 2908)
ERROR  Invalid JSON in client config for CLIENT_ALMA — JSONDecodeError: Expecting value: line 1 column 1 (char 0)
WARNING The column layout wasn't saved: Failed to save client config after 5 attempts
```

`Extra data: line 112 column 2` is a **corrupted config on the share** — a
shorter document written over a longer one, old tail surviving. This is data
loss, not log noise.

### Root cause

`shopify_tool/profile_manager.py:900` `_save_with_windows_lock` (and its Unix
twin at :955, and `shopify_tool/groups_manager.py:247`) hand-roll an atomic
write and get three things wrong:

1. **The temp file has a fixed name.** `file_path.with_suffix(".tmp")` →
   every writer uses the identical `client_config.tmp`. Two savers race: one's
   `shutil.move` takes the file the other still holds. That is the
   `FileNotFoundError` and the `WinError 32`, exactly.
2. **The lock is on the wrong file.** `msvcrt.locking` is applied to the temp
   file, which nobody else reads. The contended resource is
   `client_config.json`, which is never locked. The lock is theatre — and it
   locks a byte range of a still-empty file using the *new* content's length.
3. **`shutil.move` is not atomic onto an existing destination.** On Windows
   `os.rename` refuses an existing target, so `shutil.move` falls back to
   `copy2` + `unlink` — a plain byte copy into the live file. Interrupt it, or
   write fewer bytes than the file already held, and the destination is left
   half-old/half-new. That is the `Extra data` corruption.

The retry loop, the 5-second timeout and the "attempt n/5" spam
(`profile_manager.py:1126`) all exist to paper over this.

### The fix is a deletion

`shared/atomic_write.py` **already does this correctly** —
`tempfile.mkstemp` in the destination directory (unique name) +
`Path.replace()` (`os.replace`, genuinely atomic on Windows) + bounded retries
+ temp cleanup. It is already vendored here and already used by
`shared/stats_manager.py`.

So: route the three call sites through `atomic_write_json` and delete
`_save_with_windows_lock`, `_save_with_unix_lock`, the retry/timeout loop and
the `msvcrt`/`fcntl` imports — roughly 150 lines, replaced by one call.

**`shared/` needs no change, so no `packing-tool` sync is involved.**

Open policy question in §7 Q3: `os.replace` removes corruption but leaves
last-writer-wins between two warehouse PCs.

---

## 2. Settings changes don't apply until the client is reloaded

Subtask `6hWGG6753QC539WV` ("sniffer is not apply changes until you reload a
client"). The delimiter *detection* in `shopify_tool/csv_utils.py` is sound,
and the in-memory snapshot is **not** the culprit — `actions_handler.py:381`
reloads `active_profile_config` after the Settings dialog, and
`file_handler._save_default_delimiter:132` mutates it in place. Both paths
refresh correctly. That hypothesis is disproved; do not re-investigate it.

What is established is that **saves fail silently**:

- `gui/file_handler.py:135` calls `save_shopify_config` and ignores the return
  value. So does every other caller.
- `gui/actions_handler.py:379` — "The window has already toasted *Settings
  saved*" — the toast fires when the dialog is accepted, before the write is
  confirmed. The user is told the save worked whether or not it did.
- The log proves the write really does fail:
  `WARNING The column layout wasn't saved: Failed to save client config after
  5 attempts`.
- Invalidation at `profile_manager.py:676` runs **only on success**, so a
  failed save leaves the pre-edit config cached under a still-matching mtime.

So the value lives in memory, never reaches the share, and the next process to
read the file gets the old one. Whether that is the whole of what the operator
sees is not provable from the screenshots — §1 has to land first, then this is
re-tested on Windows.

Fix: make the write reliable (§1), then make failure visible — check the
return value at every `save_shopify_config` / `save_client_config` call site,
and only toast success after the write actually succeeded.

---

## 3. Inventory memory only remembers SKUs that were ordered

Subtask `6hWGGF33wMJ2FJ43`. `shopify_tool/core.py:1164` builds the snapshot
from `final_df`:

```python
final_stock_dict = final_df.groupby("SKU")["Final_Stock"].last()...
```

`final_df` is the *analysis result* — it only contains SKUs that appear on an
order. Every SKU in the stock file with no orders in the run is absent from
memory. That is the reported "saving only lines that was previously analysed",
and the code matches the report exactly.

Whether memory should cover the whole stock file is a product decision — §7 Q2.

---

## 4. Barcodes — not reproducible from the evidence

Subtask `6hWGGMp4qxhpMJPV` reports "creates only 1 single barcode, no matter
how much orders in packing list". The code does not obviously do this:
`gui/barcode_generator_widget.py:386` builds `unique_orders` by grouping
`self.filtered_orders_df` on `Order_Number`, and that frame is filtered from
the packing list's orders at :305. 18 orders in should be 18 labels out.

Two things are visible in screenshot 8 and worth separating from the report:

- **`Complete: 34 barcodes generated` alongside `18 orders ready for`.** The
  status label (:450) is never cleared when the packing list selection
  changes, so it shows the previous generation's count. A stale label, not a
  generation bug — but it is how a user would come to distrust the number.
- The count label text is clipped (§5, B3), so "18 orders ready for" reads as
  an unfinished sentence.

This one needs a reproduction before it gets a fix — §7 Q4 asks for it.
Guessing here would mean changing working code.

---

## 5. UI defects read off the screenshots

Grouped by where they live. "Canvas" marks the ones to re-check against the
artboards before fixing.

| # | Surface | Defect |
|---|---|---|
| B1 | Results bulk menu (shot 10) | Singular copy is ungrammatical: "Remove a SKU from these 1 order", "Export just these 1 to Excel" |
| B2 | Column manager (shot 11) | `pinned` / `empty` meta text is clipped by the scrollbar — content width ignores the scrollbar |
| B3 | Tools (shot 8) | "18 orders ready for…" clipped; **"Output folder" label with no control beside it** in the Barcode labels card |
| B4 | Settings, General + Reports (shots 4, 5) | Form interior never got the Phase 9 pass: trailing colons on every label, field widths inconsistent (one full-bleed spinbox), native spinbox arrows, "Search settings" placeholder clipped |
| B5 | Settings → Reports (shot 5) | Native light scrollbar; column list clipped mid-row at the bottom edge |
| B6 | Browse (shot 6) | Age column truncates — "24d · archiv…" |
| B7 | Client dropdown (shot 3) | Native scrollbar; actions ("Refresh clients", "New client…", "Manage groups…") sit in the list with no separator; colour dots missing on some entries |
| B8 | Logs (shots 6, 7) | Source switch (Activity/Execution) and level floor (All/Info/Warning/Error) are rendered as one undifferentiated row of identical buttons with no visible checked state — this is subtask `6hWGGWfFpxqRFp8V`, "switching between tabs can confuse info displayed" |
| B9 | Generate Reports (shot 12) | Checkbox style differs from the column manager's; the selected "All" row renders as an edit field |

B4/B5 are one finding, not two: **Phase 9 restyled the Settings shell — left
nav, kind headings, Save/Cancel — but never the form controls inside it.**
Bundle 10's spec covers the Reports pane's headings and only those. Scoping
that is §7 Q5.

B1 and B2 are Bundle 14 and Bundle 13 escapes respectively — both shipped last
week and both are cheap.

---

## 6. What is already right

Worth recording so nobody "fixes" it: the Results table, the stat row, the
detail pane, the session browser and the nav rail all match the canvas. The
shell, spacing rhythm and colour work read as intended on Windows. Phase 9
landed.

---

## 7. Decisions — answered 2026-09-15

1. **Sequencing: everything in one PR.** As the task says, one flow. The plan
   is ordered correctness-first anyway so the important commits land early and
   review can start at the top.
2. **Inventory memory: every SKU in the stock file.** Seed the snapshot from
   the full stock frame, then overlay post-fulfilment `Final_Stock` for the
   SKUs the run touched. A SKU with no orders keeps its real level instead of
   disappearing. Not accumulate-forever — each run's stock file is the truth,
   so a discontinued SKU drops out when it leaves the file.
3. **Two PCs, one config: last writer wins.** Atomic writes make the file
   always-valid JSON, which was the actual harm. No revision stamps, no merge
   pass, no extra network read per save. Recorded in ADR 0008.
4. **Barcodes: fix the stale label, instrument for a repro.** The "1 label"
   report gets no speculative fix. Clear the status label when the packing
   list changes, and log packing list / filtered order count / labels written
   so the next Windows run captures its own evidence.
5. **Settings interior: fix what is broken, not the style.** Clipped
   placeholder, list cut mid-row, native scrollbars, full-bleed spinbox. The
   trailing colons and label styling stay — a full Phase 9 pass on the form
   interior is a bundle, not a quick fix, and is not in this batch.

## 8. Scope after the decisions

In, correctness: §1 atomic config writes; §2 config-snapshot refresh;
§3 inventory memory from the stock file; §4 stale barcode label + diagnostics.

In, UI: B1, B2, B3, B6, B7, B8, B9, and the *broken* half of B4/B5.

Out: the Settings form restyle (colons, label style, field widths beyond the
full-bleed spinbox); any change to the barcode generation path itself; any
change under `shared/`.

Plan: `docs/superpowers/plans/2026-09-15-post-phase9-quickfixes-plan.md`.
