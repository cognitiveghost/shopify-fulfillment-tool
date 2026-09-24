# Phase 12 Bundle 3 — Order data integrity, export to packing

**Todoist:** "critical bug Shopify tool" `6hcQ9jrqxVp2gWjV` and its subtask
`6hcQV2R6fhfH4583` ("check what could malform order content from export to
packing"), plus the owner's mid-session request: auto-set the delimiter, with a
manual value only for critical cases.

**Classification:** architectural-lite. The reported bug is a bounded fix, but
the audit and the delimiter change touch the loader, the analysis cleaning, the
settings page and a profile migration.

**Repos:** shopify-fulfillment-tool only. packing-tool was checked and needs no
change (§6).

**Mockup:** none. The only UI change is one settings control and the file
slot's summary line (§4, §5).

---

## 1. Findings (all reproduced on `origin/main` 7f2ef54)

| # | Where | What goes wrong | Severity |
|---|---|---|---|
| F1 | `csv_utils.merge_csv_files` via `file_handler.merge_and_save_files` | Folder merge drops rows duplicated on `(Order_Number, SKU)` across the **whole merged frame**, so a real second order line (`#4148 · 501 ×1` twice in one file) is deleted. Reported bug. | Critical: an item goes unpacked |
| F2 | same, stock side | Stock merge drops rows duplicated on `SKU`. With lot tracking one file holds a SKU once per lot, so every lot after the first is lost. | High |
| F3 | `analysis._clean_and_prepare_data` | `Shipping_Method`, `Shipping_Country`, `Total_Price`, `Subtotal`, `Tags` and order-level additional columns use a bare `ffill()`. An order whose first line has them blank inherits the **previous order's** values: its tags and its courier. Repro: `#4149` with no tags got `vip` / `DHL`. `Customer` and `Created_At` already fill within the order. | Critical: wrong courier, wrong tags, wrong packaging |
| F4 | same, stock cleaning | Stock rows are deduplicated/aggregated **before** `normalize_sku`. `"501 "` and `"501.0"` both survive, both become `501`, and the orders⋈stock merge doubles every order line for that SKU. Repro: `#4148` went from 2 lines to 4, so the packing JSON asks for 2× the units. The lot path's `{normalize_sku(k): v}` also silently overwrites one variant's lots. | High |
| F5 | `file_handler.merge_and_save_files` | The merged file is always written comma-separated, then read back by the analysis with the profile's delimiter (`;` by default for stock). | Medium: load fails |
| F6 | `file_handler` folder scan | `rglob` order is filesystem order, so which file "keeps first" is arbitrary. | Medium |
| F7 | delimiter reads | Slot load and folder validation detect the delimiter; the analysis run, the folder merge and `actions_handler`'s stock re-read use the stored setting. The slot says "Loaded with ';'" while the run reads with ','. | Medium |

Out of scope, noted: a SKU twice **within one** stock file without lot columns
keeps its first row (existing rule, unchanged). After F4 that now also applies to
`"501 "` / `"501.0"` variants, which is correct: they are one SKU.

## 2. Decisions (owner, 2026-09-24)

1. An order number found in two files of a folder merge: **the newest file wins**
   (file modified time; ties broken by filename). All of the order's lines come
   from that one file.
2. Stock folders follow **the same rule** keyed on SKU. Files are overlapping
   snapshots, not separate warehouses, so they are never summed.
3. **All findings ship in this bundle.**
4. The slot summary **states what the merge skipped**, with the real post-merge
   row count.
5. Delimiter: **Auto by default, a fixed character is an override.** Every
   existing profile is **migrated to Auto** once (ADR 0009).

## 3. Folder merge: the owning-file rule (F1, F2, F5, F6)

In a folder merge each key belongs to exactly one file, its **owning file**:
the newest file that contains it. The key is the order number for orders and
the SKU for stock. The merge keeps every row of the owning file for that key and
drops the key's rows from every other file. **A row is never dropped because it
repeats another row in the same file.**

`merge_csv_files` becomes the single home of this rule (a deep module: callers
pass paths and a key column and get a frame back):

```python
def merge_csv_files(
    file_paths: list[str],
    delimiter_setting: str | None, # "auto" or an override character
    kind: str,                     # "orders" | "stock": picks the fallback
    encoding: str = "utf-8-sig",
    dtype_dict: dict | None = None,
    add_source_column: bool = True,
    owner_key: str | None = None,  # CSV column name; None = plain concat
) -> tuple[pd.DataFrame, int]:     # (merged frame, keys skipped from non-owning files)
```

- Files are ranked newest first by `os.path.getmtime`, ties by basename. The
  frame's row order is the ranked file order.
- Each file is read with `resolve_delimiter(path, delimiter_setting, kind)` (§4), so a folder may mix delimiters.
- A key's rows in a non-owning file are dropped; the returned count is the
  number of **distinct keys** dropped that way. A blank order number belongs
  to the order above it in the same file (continuation lines go with their
  order); blank keys at the top of a file are never dropped. Stock keys compare
  as `normalize_sku` values.
- `remove_duplicates` and the whole-row dedupe path are **deleted**. The
  whole-row path would drop two identical real lines, the same bug as F1, and no
  production caller uses it.

`FileHandler.merge_and_save_files`:
- passes `owner_key` = the CSV column mapped to `Order_Number` (orders) or `SKU`
  (stock); `None` if the mapping has none (then a plain concat plus a warning in
  Logs);
- writes the merged file with `sep=","` when the setting is Auto, otherwise with
  the override. The analysis then resolves it back to the same character;
- returns `(merged_path, row_count, skipped_keys)`.

`_FOLDER_REMOVE_DUPLICATES` is deleted; the owning-file rule is not optional.

## 4. Delimiter: Auto with an override (F7)

One resolver in `shopify_tool/csv_utils.py`:

```python
AUTO_DELIMITER = "auto"
FALLBACK_DELIMITERS = {"orders": ",", "stock": ";"}

def resolve_delimiter(path, setting, kind) -> str:
    """The delimiter to read `path` with. An override wins; Auto detects."""
```

- `setting` is an override (any value other than `"auto"`, `""` or `None`) →
  return it unchanged.
- Otherwise call `detect_csv_delimiter(path)`. If its method is `"default"`
  (nothing detected), return `FALLBACK_DELIMITERS[kind]`, else the detected
  character. The fallbacks are today's defaults: `,` for orders, `;` for stock.

Every read of a **user-supplied** orders or stock CSV goes through it:
`core._load_and_validate_files` (all three `read_csv` calls),
`merge_csv_files`, `FileHandler.validate_multiple_files`, `FileHandler.validate_file`
(which today hardcodes `,` for orders), the orders and stock slot loads in
`FileHandler`, `actions_handler`'s stock re-read (~line 1162) and
`gui/settings/weight.py:549`. `run_full_analysis` keeps its signature; its
`stock_delimiter` / `orders_delimiter` arguments now carry the **setting**, and
core resolves per file. Readers that already detect by themselves
(`gui/settings/mappings.py`, weight.py:662/812) are left alone.

**Slot load:** the "Loaded with X — settings say Y · Save as default" toast and
`FileHandler._save_default_delimiter` are deleted. Under Auto there is nothing
to save, and under an override the person chose the character on purpose.

**Settings › General:** each delimiter `QLineEdit` becomes a `QComboBox`:

| Label | Stored value |
|---|---|
| Auto — detect per file | `auto` |
| Comma  , | `,` |
| Semicolon  ; | `;` |
| Tab | `\t` |
| Pipe  \| | `\|` |

A stored value not in the list, for example a hand-edited one, is added as an
extra item showing the raw value, so opening and saving Settings never changes
it. Tooltip for both: "Auto reads each file's own delimiter. Pick a character
only for a client whose files Auto reads wrong."

**Migration:** `migrate_delimiters_to_auto(client_id, config)` in
`profile_migrations.py`, called from `ProfileManager.load_shopify_config` after
`migrate_delimiter_config_v1_to_v2`. It runs once per profile, guarded by
`settings["delimiter_auto_migrated"] = True`: it sets both
`stock_csv_delimiter` and `orders_csv_delimiter` to `"auto"`, sets the marker
and returns True. With the marker present it returns False and never touches
a later override. New-client defaults (`profile_manager.py` ~l.443,
`gui/settings/window.py` ~l.156) become `"auto"` plus the marker.

## 5. Operator-facing copy

Merge confirm (`show_file_preview`), replacing "Duplicates will be removed
(keep first occurrence)":
- orders: "An order found in more than one file is taken from the newest file."
- stock: "A SKU found in more than one file is taken from the newest file."

Slot summary after a folder merge, using the **post-merge** row count:
- `3 files merged · 1 204 rows`
- `+ · 12 overlapping orders skipped` (stock: `overlapping SKUs`) when the
  count > 0; singular "order"/"SKU" when it is 1;
- `+ · 1 skipped` (invalid files) as today.

## 6. Analysis cleaning (F3, F4) and packing-tool

- F3: every order-level fill listed in F3 uses
  `orders_df.groupby("Order_Number")[col].ffill()`, like `Customer` and
  `Created_At` already do. `Order_Number` itself keeps its bare `ffill()`: it is
  the group key.
- F4: at the top of stock cleaning (before the no-lot `drop_duplicates`, the lot
  `_build_fifo_lots` and `groupby`), normalize non-null stock SKUs in place with
  `normalize_sku`. Null SKUs stay null so `dropna` still drops them;
  `normalize_sku(NaN)` returns `""`, which is why only non-null values are
  mapped.
- packing-tool: `PackerLogic.start_order_packing` builds one state row per JSON
  item, and `process_sku_scan` fills the first unfilled row that matches. Two
  items with the same SKU pack correctly. No change.

## 7. Testing seams

| Seam | Proves |
|---|---|
| `csv_utils.merge_csv_files` | a repeat line within one file survives (F1); a lot row per SKU survives (F2); an overlapping order comes whole from the newest file by mtime (`os.utime`); an mtime tie falls to the filename; mixed `,`/`;` files merge; the skipped count counts keys; blank keys never drop |
| `csv_utils.resolve_delimiter` | override is returned untouched; Auto detects `;`; undetectable → fallback |
| `analysis._clean_and_prepare_data` | an untagged order after a tagged one stays untagged, and the same for the courier (F3); `"501 "`/`"501.0"` stock collapses to one SKU (F4) |
| `analysis.run_analysis` | **invariant**: without set decoders, each order has as many final rows as input lines (catches any future row explosion) |
| `core.run_full_analysis` | a `;` orders file loads under `"auto"` with a profile default of `,` |
| `profile_migrations.migrate_delimiters_to_auto` | converts `,`/`;` to auto once; with the marker set, a later `;` override survives |
| `FileHandler.merge_and_save_files` | the merged file is written with `,` under Auto and with the override otherwise; the counts are returned |
| `GeneralPage` | Auto/Tab round-trip; an unknown stored value survives open → collect |

## 8. Not doing

- Per-file delimiter override (one setting per kind is enough; override is rare).
- Summing stock across files (decision 2).
- Changing `keep="first"` for a SKU repeated inside one no-lot stock file.
- Any packing-tool change.
