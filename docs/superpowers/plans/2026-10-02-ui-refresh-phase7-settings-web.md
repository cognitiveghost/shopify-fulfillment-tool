# UI refresh phase 7: Client settings pages on the web kit. Implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Draw General, Orders mapping and Stock mapping on the web kit inside the Client settings dialog,
restyle the dialog's Qt frame to the approved mockup, and make Save behave as the mockup draws it (live only
when a page is unsaved; the dialog stays open).

**Architecture:** The dialog stays a `QDialog` whose nav, search and footer are Qt widgets. One
`QWebEngineView` (`SettingsWebHost`) sits in the page stack and draws three pages. Each of those pages is a
*draft* (`gui/settings/page_state.py`, no Qt): it holds the page's values, takes edits through
`apply(action, args)`, words everything the page shows in `view()`, and meets the same contract as a Qt page
(`PageContract`), so `SettingsWindow` saves and marks it like any other. The web page (`gui/web/settings.js`)
renders one `state` map and reports each edit through `SettingsBridge.edit`. Rules, Sets, Weight, Reports and
Tag categories are not touched.

**Tech Stack:** Python 3.14, PySide6 (Qt widgets, QtWebEngine, QWebChannel), pandas, plain CSS and
JavaScript (no build step, no framework), pytest + pytest-qt driving a real Chromium offscreen.

**Spec:** `docs/superpowers/specs/2026-10-02-ui-refresh-phase7-settings-web-design.md`. Read it whole before
starting; this plan argues from it. Copy (every label, sentence and empty state) is in spec §4.6 and is
verbatim. Mockup: `docs/design/ui-refresh/mockups/client-settings.html` (render:
`mockups/renders/client-settings.png`). To read exact values, unpack the bundle with the script in
`docs/design/ui-refresh/mockups/README.md`.

**Every code block in this plan was run before the plan was written**, in a scratch copy of the repo at
7fd0049 (code identical to `origin/main` at d7aac72). This document was generated from that copy: each
"Create" block is the file as it ran, and each "find exactly / Replace with" pair was applied to the file as
the earlier tasks left it. There, each task's own tests passed at the point the task ends, `ruff check .`
passed, and the whole suite passed at the end but for the baseline failures below. The dialog was rendered in
both themes and compared with the mockup. If a block fails for you, suspect a typo in transcription, or a
change on `main` since d7aac72, before you suspect the design, and say what differed.

## Global Constraints

- Work in `/home/gloopy/Desktop/Projects/shopify-fulfillment-tool/.claude/worktrees/dr-19` on branch
  `dr/19-ui-refresh-phase-7-client-settings-on-th`. Never `cd` anywhere else. If `.venv` is missing, run
  `./scripts/setup_venv.sh`.
- Run tests only as `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q <paths>`. A hook blocks any
  other Bash text containing the word "pytest", so write test files with Write/Edit, never with heredocs.
- Git: `/usr/bin/git`, one plain command per Bash call, with no `;`, `&&` or `$VAR`. Commit with
  `/usr/bin/git commit -F <absolute path to a message file>`; write the message file under your job's tmp
  dir. End every message with the attribution lines your session is given.
- **Transcribe code blocks exactly.** A block headed "Create" is the whole file. A pair headed "find
  exactly" / "Replace with" is one Edit: the first block is the `old_string`, the second the `new_string`,
  and the first occurs once in the file at the moment you reach it. Apply a file's edits in the order
  given. "append at the end of the file" means: Read the file, then Edit its last lines to add the block
  after them. An appended block begins with the blank lines that separate it from what is above: leave
  exactly two blank lines between the file's old last line and the block's first line of code.
- No hex, colour name, `rgb()`, px font size (that includes the `font:` shorthand), `transition`,
  `transform`, gradient or `opacity` in any file under `gui/` (`shared/style_lint.py`, enforced by
  `tests/test_style_literals_guard.py`). `box-shadow` only as `var(--card-shadow)`,
  `var(--overlay-shadow)` or `none`, and only in a `.css` file. Never set `element.style.*` to a colour
  from JavaScript: use a class. In Python, a colour is always a theme token (`tokens.status_danger`).
- The lint reads a colour word after a colour property up to the next `;`. So every CSS declaration ends
  with `;`, including the last one in a rule.
- CSS custom properties from the theme are hyphenated: the token `surface_raised` is
  `var(--surface-raised)`. Type sizes are `var(--type-caption-size)`, `--type-body-size`,
  `--type-label-size`, `--type-heading-size`. The mono face is `var(--font-family-mono)`.
- ADR 0018: a decorative line (card edge, divider) is `--border-subtle`. The edge of a button, an input or
  a box the eye must find is `--border`.
- **Everything from a CSV or the profile goes through `esc()` before it reaches `innerHTML`** in
  `settings.js`: column names, first-row values, courier texts, file names. A column name can hold `<`,
  `"` or anything else. Controls are found by comparing `dataset.key`, never by building a selector from
  a name.
- **The page sends strings and booleans only.** A row index travels as a string (`"2"`). A JavaScript
  number arrives in Python as a float, and the drafts drop it.
- **A draft imports no Qt.** `gui/settings/page_state.py` and `gui/settings/contract.py` must stay
  importable with no `QApplication`.
- A page that owns a dict of the config mutates and returns the live dict it was given
  (`gui/settings/contract.py`). `column_mappings` is one live dict shared by both mapping drafts; each
  writes only its own sub-key. `courier_mappings` is cleared and refilled in place.
- `Expiry_Date` and `Batch` are the exact internal names `_build_fifo_lots()` reads
  (`shopify_tool/analysis.py`). Do not rename them.
- `shared/` changes by one file only: `shared/assets/icons/circle-alert.svg` (Task 11). Never edit
  `packing-tool/shared/`.
- No `pyproject.toml`. No new dependency. No direct commit to `main`.
- `ruff check .` must pass after every task.
- The page names are `General`, `Orders mapping`, `Stock mapping`, `Rules`, `Sets`, `Weight`, `Reports`,
  `Tag categories` (Task 1 renames three of them). The nav, `initial_page`, `QSettings` and the tests all
  use these exact strings.

## Baseline

On this dev VM three tests fail before any change, and they are not yours:
`tests/test_label_printing.py::TestImageToZpl::test_black_pixels_become_set_bits`,
`::test_invert_flips_the_polarity` and `::test_rotate_and_invert_compose`. Every other test passes on
7fd0049. Every test that passes there must pass after every task, unless the task rewrites or deletes it
and says so. The whole suite takes about eight minutes; run it twice, at the end of Task 10 (the first task
that deletes files) and in Task 13. Each other task runs the files it names.

Chromium prints `SharedImageManager::ProduceMemory` and `libEGL` lines while the web tests run. They are
noise, not failures.

## Review Focus

The inputs the spec implies and a person will meet, most likely first. Each has its test in the task that
owns the code.

1. **A CSV column whose name holds a quote, markup or non-ASCII text** (`Gift "note" <b>`, `Артикул`). It is
   drawn as text, and its chip and menu still work. Tests:
   `test_a_column_name_with_quotes_in_it_still_works` (Task 8), `test_it_detects_a_semicolon_file` (Task 2).
2. **An edit made while a save is still writing.** The dialog stays usable during the write. The write
   carries what Save collected, and the later edit still reads unsaved afterwards. Test:
   `test_an_edit_made_while_the_write_runs_stays_unsaved` (Task 12).
3. **The file loaded on Setup is gone or unreadable when the dialog opens** (a dropped share, a file moved
   since). The mapping page says no CSV has been read; nothing is raised. Test:
   `test_a_mapping_page_opens_with_the_file_loaded_on_setup` (Task 10).
4. **A profile that carries values this page has no control for**: a Pipe or hand-edited delimiter, a
   legacy courier entry (`{"dhl": "DHL"}`), a mapped column the read file lacks, an internal name with no
   row. Each survives a save. Tests: `test_pipe_opens_as_other_and_is_kept`,
   `test_a_hand_edited_value_survives_a_round_trip` (Task 4);
   `test_an_internal_name_with_no_row_is_carried_through`,
   `test_a_saved_column_the_file_lacks_stays_and_says_so` (Task 5);
   `test_a_legacy_entry_loads_as_a_row_and_is_saved_in_the_new_shape` (Task 6).
5. **A profile that opens with a required column already unmapped.** The nav marks the page and the footer
   names it, and the page does not read unsaved. Test:
   `test_a_profile_that_opens_with_a_required_column_unmapped_is_marked` (Task 11).

Also covered where it lives: a CSV with a header and no rows (`test_a_file_with_no_rows_has_columns_and_no_first_row`,
Task 2); junk sent to the bridge (`test_an_edit_it_does_not_know_is_dropped`, Tasks 4 to 6;
`test_an_edit_whose_arguments_are_not_a_list_is_dropped`, Task 8); a client config whose additional columns
cannot be read (`test_an_unreadable_client_config_leaves_the_stored_list_alone`, Task 6); Ctrl+S pressed
before the 400ms poll saw the edit (`test_ctrl_s_saves_an_edit_the_poll_has_not_seen`, Task 12).

## File map

| File | Task | What it is |
|---|---|---|
| `gui/settings/window.py` | 1, 10, 11, 12 | The dialog: names, the drafts and the host, the frame, the footer and Save |
| `gui/setup_state.py`, `gui/ui_manager.py`, `gui/actions_handler.py`, `gui/settings/weight.py` | 1 | The renamed pages' names |
| `shopify_tool/csv_utils.py` | 2 | `read_csv_preview` |
| `gui/settings/contract.py` (new), `gui/settings/base.py` | 3, 12 | `PageContract`; `SettingsPage(PageContract, QWidget)` |
| `gui/settings/page_state.py` (new) | 4, 5, 6 | `FileColumns`, `GeneralDraft`, `MappingDraft`, `StockDraft`, `OrdersDraft` |
| `gui/web/kit.css`, `tests/web/kit_sheet.html` | 7 | The page anatomy |
| `gui/settings/bridge.py` (new) | 8 | `SettingsBridge`, `mount_settings_page` |
| `gui/web/settings.html`, `settings.css`, `settings.js` (new) | 8 | The page |
| `gui/settings/web_host.py` (new) | 9 | `SettingsWebHost`, `read_file_columns` |
| `gui/settings/general.py`, `gui/settings/mappings.py`, `gui/column_mapping_widget.py` | 10 | Deleted |
| `gui/theme_manager.py` | 11 | The nav's QSS |
| `shared/assets/icons/circle-alert.svg` (new) | 11 | The alert glyph |
| `docs/design/ui-refresh/roadmap.md`, `docs/adr/0016-…md`, `CONTEXT.md`, renders | 13 | Docs |

Tests: `tests/test_csv_utils_preview.py` (2), `tests/test_settings_page_contract.py` (3, 12),
`tests/test_settings_draft_general.py` (4), `tests/test_settings_draft_mapping.py` (5),
`tests/test_settings_draft_orders.py` (6), `tests/test_web_kit.py` (7), `tests/test_settings_bridge.py` and
`tests/test_settings_web_page.py` (8), `tests/test_settings_web_host.py` (9), `tests/test_settings_roundtrip.py`
(1, 10, 12), `tests/test_settings_nav.py` (1, 11), `tests/test_settings_unsaved.py` (12),
`tests/test_settings_footer.py` (12). The spec's §10 names one draft test file,
`tests/test_settings_page_state.py`; this plan splits it into the three `test_settings_draft_*.py` files, one
per task.

---

### Task 1: The pages take the mockup's names

The mockup writes page and group names in sentence case. They are keys as well as labels (the nav, the
stored last page, `initial_page`, the Setup card's "Open …" link), so every use changes together.

**Files:**
- Modify: `gui/settings/window.py`, `gui/setup_state.py`, `gui/ui_manager.py`, `gui/actions_handler.py`,
  `gui/settings/weight.py`
- Test: `tests/test_settings_nav.py`, `tests/test_settings_roundtrip.py`, `tests/test_file_handler.py`,
  `tests/test_file_slot.py`, `tests/test_setup_page.py`, `tests/test_session_setup_layout.py`,
  `tests/test_results_screen.py`, `tests/test_setup_state.py`

**Interfaces:**
- Produces: the page names `"Orders mapping"`, `"Stock mapping"`, `"Tag categories"`; the group names
  `"Data"`, `"Fulfilment logic"`, `"Output"`, `"Organization"`, shown as written (no upper-casing).
  `gui.setup_state.MAPPING_PAGE == {"orders": "Orders mapping", "stock": "Stock mapping"}`.

- [ ] **Step 1: Change the tests to the new names**

In `tests/test_file_handler.py`, replace every `Orders Mapping` with `Orders mapping` (Edit with `replace_all`).

In `tests/test_file_handler.py`, replace every `Stock Mapping` with `Stock mapping` (Edit with `replace_all`).

In `tests/test_file_slot.py`, replace every `Orders Mapping` with `Orders mapping` (Edit with `replace_all`).

In `tests/test_file_slot.py`, replace every `Stock Mapping` with `Stock mapping` (Edit with `replace_all`).

In `tests/test_setup_page.py`, replace every `Orders Mapping` with `Orders mapping` (Edit with `replace_all`).

In `tests/test_session_setup_layout.py`, replace every `Orders Mapping` with `Orders mapping` (Edit with `replace_all`).

In `tests/test_results_screen.py`, replace every `Orders Mapping` with `Orders mapping` (Edit with `replace_all`).

In `tests/test_setup_state.py`, replace every `Orders Mapping` with `Orders mapping` (Edit with `replace_all`).

In `tests/test_settings_roundtrip.py`, replace every `Orders Mapping` with `Orders mapping` (Edit with `replace_all`).

In `tests/test_settings_roundtrip.py`, replace every `Stock Mapping` with `Stock mapping` (Edit with `replace_all`).

In `tests/test_settings_roundtrip.py`, replace every `"Tag Categories"` with `"Tag categories"` (Edit with `replace_all`).

In `tests/test_settings_nav.py`, replace every `Orders Mapping` with `Orders mapping` (Edit with `replace_all`).

In `tests/test_settings_nav.py`, find exactly:

```python
    assert [h.text() for h in headers] == [
        "DATA",
        "FULFILLMENT LOGIC",
        "OUTPUT",
        "ORGANIZATION",
    ]
```

Replace with:

```python
    assert [h.text() for h in headers] == [
        "Data",
        "Fulfilment logic",
        "Output",
        "Organization",
    ]
```

In `tests/test_settings_nav.py`, find exactly:

```python
    assert _headers(window) == {
        "DATA": True,
        "FULFILLMENT LOGIC": False,
        "OUTPUT": True,
        "ORGANIZATION": True,
    }
```

Replace with:

```python
    assert _headers(window) == {
        "Data": True,
        "Fulfilment logic": False,
        "Output": True,
        "Organization": True,
    }
```


- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_settings_nav.py tests/test_settings_roundtrip.py tests/test_file_slot.py tests/test_setup_state.py`

Expected: failures. The tests now ask for the new names and the window still has the old ones.

- [ ] **Step 3: Rename in the code**

In `gui/settings/window.py`, find exactly:

```python
    "Orders Mapping": ["columns", "csv", "headers", "courier", "carrier", "shipping"],
    "Stock Mapping": ["columns", "csv", "headers", "expiry", "batch", "lot", "fifo"],
```

Replace with:

```python
    "Orders mapping": ["columns", "csv", "headers", "courier", "carrier", "shipping"],
    "Stock mapping": ["columns", "csv", "headers", "expiry", "batch", "lot", "fifo"],
```

In `gui/settings/window.py`, find exactly:

```python
    "Tag Categories": ["tags", "labels", "colours", "colors", "writeoff", "sku"],
```

Replace with:

```python
    "Tag categories": ["tags", "labels", "colours", "colors", "writeoff", "sku"],
```

In `gui/settings/window.py`, find exactly:

```python
        ("Data", ["General", "Orders Mapping", "Stock Mapping"]),
        ("Fulfillment Logic", ["Rules", "Sets", "Weight"]),
        ("Output", ["Reports"]),
        ("Organization", ["Tag Categories"]),
```

Replace with:

```python
        ("Data", ["General", "Orders mapping", "Stock mapping"]),
        ("Fulfilment logic", ["Rules", "Sets", "Weight"]),
        ("Output", ["Reports"]),
        ("Organization", ["Tag categories"]),
```

In `gui/settings/window.py`, find exactly:

```python
            "Orders Mapping",
        )
```

Replace with:

```python
            "Orders mapping",
        )
```

In `gui/settings/window.py`, find exactly:

```python
            "Stock Mapping",
        )
```

Replace with:

```python
            "Stock mapping",
        )
```

In `gui/settings/window.py`, find exactly:

```python
            "Tag Categories",
        )
```

Replace with:

```python
            "Tag categories",
        )
```

In `gui/settings/window.py`, find exactly:

```python
            header = QListWidgetItem(group_name.upper())
```

Replace with:

```python
            header = QListWidgetItem(group_name)
```

In `gui/setup_state.py`, find exactly:

```python
MAPPING_PAGE = {"orders": "Orders Mapping", "stock": "Stock Mapping"}
```

Replace with:

```python
MAPPING_PAGE = {"orders": "Orders mapping", "stock": "Stock mapping"}
```

In `gui/ui_manager.py`, find exactly:

```python
            lambda: actions().open_settings_window(page="Orders Mapping")
```

Replace with:

```python
            lambda: actions().open_settings_window(page="Orders mapping")
```

In `gui/actions_handler.py`, find exactly:

```python
            page (str, optional): Nav entry to open on, e.g. "Orders Mapping".
```

Replace with:

```python
            page (str, optional): Nav entry to open on, e.g. "Orders mapping".
```

In `gui/settings/weight.py`, find exactly:

```python
                    "Check the column mappings under Settings → Stock Mapping, "
```

Replace with:

```python
                    "Check the column mappings under Settings → Stock mapping, "
```


- [ ] **Step 4: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_settings_nav.py tests/test_settings_roundtrip.py tests/test_file_handler.py tests/test_file_slot.py tests/test_setup_page.py tests/test_session_setup_layout.py tests/test_results_screen.py tests/test_setup_state.py`

Expected: all pass.

Then check nothing still uses an old name:
`rg -n "Orders Mapping|Stock Mapping|FULFILLMENT LOGIC" gui tests` should print nothing, and
`rg -n '"Tag Categories"' gui/settings tests` should print nothing. (`gui/tag_categories_dialog.py` keeps its
own window titles; leave them.)

- [ ] **Step 5: Lint and commit**

Run: `.venv/bin/ruff check .` Expected: `All checks passed!`

Stage the five `gui/` files and the eight test files named above and commit. Message subject:
`Settings: page and group names in the mockup's sentence case`.

---

### Task 2: `read_csv_preview`

A mapping page shows each column's first value. This reads a CSV's header and one row.

**Files:**
- Modify: `shopify_tool/csv_utils.py`
- Test: `tests/test_csv_utils_preview.py` (new)

**Interfaces:**
- Produces: `shopify_tool.csv_utils.read_csv_preview(file_path: str, encoding: str = 'utf-8-sig') ->
  tuple[list[str], dict[str, str]]`: the column names in file order, and `{column: first row's value}` as
  text (`""` for an empty cell, `{}` when the file has no data row). It raises what reading the file raises.

- [ ] **Step 1: Write the failing test**

Create `tests/test_csv_utils_preview.py`:

```python
"""read_csv_preview: a file's columns and its first row, for the mapping pages
(phase 7 spec section 4.1)."""

from shopify_tool.csv_utils import read_csv_preview


def _write(tmp_path, text, encoding="utf-8"):
    path = tmp_path / "orders.csv"
    path.write_text(text, encoding=encoding)
    return str(path)


def test_it_returns_the_columns_in_file_order_and_the_first_row(tmp_path):
    path = _write(tmp_path, "Name,Lineitem sku,Qty\n#1001,ABC-1,2\n#1002,XYZ-9,1\n")
    assert read_csv_preview(path) == (
        ["Name", "Lineitem sku", "Qty"],
        {"Name": "#1001", "Lineitem sku": "ABC-1", "Qty": "2"},
    )


def test_it_detects_a_semicolon_file(tmp_path):
    path = _write(tmp_path, "Артикул;Наличност\nABC-1;40\nXYZ-9;3\n")
    assert read_csv_preview(path) == (
        ["Артикул", "Наличност"],
        {"Артикул": "ABC-1", "Наличност": "40"},
    )


def test_it_detects_a_tab_file(tmp_path):
    path = _write(tmp_path, "Sku\tAvailable\nABC-1\t40\nXYZ-9\t3\n")
    headers, first = read_csv_preview(path)
    assert headers == ["Sku", "Available"]
    assert first == {"Sku": "ABC-1", "Available": "40"}


def test_values_stay_text_and_an_empty_cell_is_an_empty_string(tmp_path):
    """A SKU of 00123 must not turn into 123, nor an empty cell into nan."""
    path = _write(tmp_path, "Sku,Note,Stock\n00123,,7\n00124,x,8\n")
    assert read_csv_preview(path)[1] == {"Sku": "00123", "Note": "", "Stock": "7"}


def test_a_file_with_no_rows_has_columns_and_no_first_row(tmp_path):
    path = _write(tmp_path, "Name,Lineitem sku\n")
    assert read_csv_preview(path) == (["Name", "Lineitem sku"], {})


def test_a_byte_order_mark_is_not_part_of_the_first_column(tmp_path):
    path = _write(tmp_path, "Name,Qty\n#1,2\n#2,3\n", encoding="utf-8-sig")
    assert read_csv_preview(path)[0] == ["Name", "Qty"]
```

- [ ] **Step 2: Run it and see it fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_csv_utils_preview.py`

Expected: an error at collection, `ImportError: cannot import name 'read_csv_preview'`.

- [ ] **Step 3: Write the function**

In `shopify_tool/csv_utils.py`, find exactly:

```python
def validate_delimiter(file_path: str, delimiter: str, encoding: str = 'utf-8-sig') -> bool:
```

Replace with:

```python
def read_csv_preview(
    file_path: str, encoding: str = 'utf-8-sig'
) -> tuple[list[str], dict[str, str]]:
    """A CSV's column names and its first data row, as text.

    For the settings pages that show which column holds what. The delimiter
    is detected, as in read_csv_headers. Two rows are all it reads. A file
    with a header and no rows gives an empty dict.

    Returns:
        (column names in file order, {column: the first row's value}); an
        empty cell is "".
    """
    delimiter, _method = detect_csv_delimiter(file_path, encoding)
    frame = pd.read_csv(
        file_path,
        sep=delimiter,
        encoding=encoding,
        nrows=1,
        dtype=str,
        keep_default_na=False,
    )
    headers = [str(column) for column in frame.columns]
    if frame.empty:
        return headers, {}
    return headers, {
        column: str(value) for column, value in zip(headers, frame.iloc[0], strict=True)
    }


def validate_delimiter(file_path: str, delimiter: str, encoding: str = 'utf-8-sig') -> bool:
```


- [ ] **Step 4: Run the test**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_csv_utils_preview.py`

Expected: 6 passed.

- [ ] **Step 5: Lint and commit**

Run: `.venv/bin/ruff check .` Expected: `All checks passed!`

Stage `shopify_tool/csv_utils.py tests/test_csv_utils_preview.py` and commit. Message subject:
`csv_utils: read_csv_preview, a file's columns and its first row`.

---

### Task 3: `PageContract`, the page contract with no widget

`SettingsPage` is a `QWidget` that carries the contract the window saves through. A draft has no widget, so
the contract moves to a class of its own and `SettingsPage` inherits it.

**Files:**
- Create: `gui/settings/contract.py`
- Modify: `gui/settings/base.py` (replace the whole file)
- Test: `tests/test_settings_page_contract.py`

**Interfaces:**
- Produces: `gui.settings.contract.PageContract` with `collect() -> dict`, `validate() -> tuple[bool,
  list[str]]`, `blocker() -> str | None`, `blocker_key() -> str`, `snapshot() -> str`, `mark_clean()`,
  `is_dirty() -> bool`; `gui.settings.contract.UNCOLLECTABLE`. `gui.settings.base.SettingsPage(PageContract,
  QWidget)` and `gui.settings.base.UNCOLLECTABLE` keep their import paths.

- [ ] **Step 1: Add the failing tests**

In `tests/test_settings_page_contract.py`, find exactly:

```python
from gui.settings.base import SettingsPage
```

Replace with:

```python
from gui.settings.base import SettingsPage
from gui.settings.contract import PageContract
```

In `tests/test_settings_page_contract.py`, append at the end of the file:

```python


def test_a_page_blocks_nothing_by_default():
    QApplication.instance() or QApplication([])
    page = SettingsPage()
    assert page.blocker() is None
    assert page.blocker_key() == ""


class _OneValueDraft(PageContract):
    def __init__(self):
        self.value = 1

    def collect(self):
        return {"key": self.value}


def test_the_contract_needs_no_widget():
    """A draft is a page with no QWidget: the same unsaved check, no QApplication."""
    draft = _OneValueDraft()
    assert draft.is_dirty() is False
    draft.mark_clean()
    draft.value = 2
    assert draft.is_dirty() is True
    assert draft.validate() == (True, [])


def test_a_qt_page_is_a_contract_and_a_widget():
    from PySide6.QtWidgets import QWidget

    assert issubclass(SettingsPage, PageContract)
    assert issubclass(SettingsPage, QWidget)
```


- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_settings_page_contract.py`

Expected: an error at collection, `ModuleNotFoundError: No module named 'gui.settings.contract'`.

- [ ] **Step 3: Write the contract**

Create `gui/settings/contract.py`:

```python
"""What SettingsWindow asks of a settings page, with no widget attached.

A Qt page is a QWidget that meets this (gui/settings/base.py). A draft meets
it with no widget at all (gui/settings/page_state.py): its values are drawn
by the web page. The window saves and marks both the same way. No Qt import.
"""

import json

UNCOLLECTABLE = "<uncollectable>"


class PageContract:
    """One page in the settings window.

    On save the window calls validate() then collect() on every page in turn.
    No page writes to disk by itself: Save is the one write, and Cancel
    discards.

    collect() returns {config_key: value}, and each value REPLACES
    config_data[key] outright -- the window does not merge. A page that
    owns a dict sub-tree must therefore mutate and return the live dict it
    was constructed with, so keys it does not render survive the save.
    Returning a freshly built dict silently drops them.

    collect() runs at any time, not only during a save: the window's
    unsaved check calls it every few hundred milliseconds. A page mutating
    its live dict mid-edit is fine -- config_data is a deep copy that only
    reaches disk through Save, which re-collects every page after all of
    them validate -- but collect() must have no other side effects.
    """

    def collect(self) -> dict:
        """The config keys this page owns. Each value replaces config_data[key]."""
        return {}

    def validate(self) -> tuple[bool, list[str]]:
        """(ok, error messages). A False here blocks the save."""
        return True, []

    def blocker(self) -> str | None:
        """What stops a save right now, as the words that fit
        "<blocker> in <page> to save."

        None when nothing does. Checked on every edit, so it must be cheap. A
        page whose checks are not cheap returns None and reports through
        validate() when Save is pressed.
        """
        return None

    def blocker_key(self) -> str:
        """The data-key of the control blocker() is about; "" when the page
        has none to point at."""
        return ""

    def snapshot(self) -> str:
        """This page's values as one comparable string.

        Override only when collect() returns a dict another page also writes
        into (see MappingDraft): otherwise an edit on that page marks this
        one unsaved too.
        """
        return json.dumps(self.collect(), sort_keys=True, default=str)

    def mark_clean(self) -> None:
        """Take the current values as the ones the page opened with."""
        self._clean_snapshot = self._safe_snapshot()

    def is_dirty(self) -> bool:
        """Whether the values differ from the ones taken at mark_clean()."""
        clean = getattr(self, "_clean_snapshot", None)
        return clean is not None and self._safe_snapshot() != clean

    def _safe_snapshot(self) -> str:
        try:
            return self.snapshot()
        except Exception:
            # A half-typed value collect() cannot parse is still an unsaved edit.
            return UNCOLLECTABLE
```

Replace the whole of `gui/settings/base.py` with:

```python
"""The contract between SettingsWindow and its Qt pages."""

from PySide6.QtWidgets import QWidget

from gui.settings.contract import UNCOLLECTABLE, PageContract

__all__ = ["UNCOLLECTABLE", "SettingsPage"]


class SettingsPage(PageContract, QWidget):
    """A settings page that is a widget: the window shows it in the nav stack.

    Everything the window asks of it is PageContract (gui/settings/contract.py).
    """
```

- [ ] **Step 4: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_settings_page_contract.py tests/test_settings_roundtrip.py tests/test_settings_unsaved.py`

Expected: all pass. Every Qt page still imports `SettingsPage` from `gui.settings.base` and behaves as before.

- [ ] **Step 5: Lint and commit**

Run: `.venv/bin/ruff check .` Expected: `All checks passed!`

Stage `gui/settings/contract.py gui/settings/base.py tests/test_settings_page_contract.py` and commit.
Message subject: `Settings: the page contract no longer needs a widget`.

---

### Task 4: `GeneralDraft`

The General page's values: two delimiters and the low-stock threshold (spec §4.2).

**Files:**
- Create: `gui/settings/page_state.py`
- Test: `tests/test_settings_draft_general.py` (new)

**Interfaces:**
- Consumes: `PageContract` (Task 3).
- Produces, in `gui.settings.page_state`:
  - `FileColumns(name: str, columns: tuple[str, ...], first_row: dict[str, str] = {}, loaded: bool = False)`,
    a frozen dataclass.
  - `GeneralDraft(settings: dict, client: str)` with `apply(action: str, args) -> bool`, `view() -> dict`,
    `delimiter(kind) -> str`, and the contract. Actions: `("delimiter", [kind, mode])`,
    `("delimiter_char", [kind, text])`, `("threshold", [text])`. `kind` is `"stock"` or `"orders"`; `mode` is
    `"auto"`, `"comma"`, `"semicolon"`, `"tab"` or `"other"`.
  - `_shaped(args, *kinds) -> bool`, used by every draft.
  - Constants `DELIMITER_PROBLEM`, `THRESHOLD_PROBLEM`, `THRESHOLD_HINT`, `KINDS`, `OTHER`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_settings_draft_general.py`:

```python
"""GeneralDraft: the General page's values, with no widget (phase 7 spec section 4.2)."""

import pytest

from gui.settings.page_state import (
    DELIMITER_PROBLEM,
    THRESHOLD_PROBLEM,
    GeneralDraft,
)


def _draft(**stored):
    settings = {
        "stock_csv_delimiter": "auto",
        "orders_csv_delimiter": "auto",
        "low_stock_threshold": 5,
    }
    settings.update(stored)
    return GeneralDraft(settings, "ACME"), settings


def _delimiter(draft, kind):
    rows = {row["kind"]: row for row in draft.view()["general"]["delimiters"]}
    return rows[kind]


def _checked(draft, kind):
    return [o["value"] for o in _delimiter(draft, kind)["options"] if o["checked"]]


# --- what it opens with ------------------------------------------------------


def test_it_round_trips_its_settings_untouched():
    draft, settings = _draft(stock_csv_delimiter=";", orders_csv_delimiter=",")
    before = dict(settings)
    assert draft.collect() == {"settings": before}


def test_collect_updates_the_live_dict_and_keeps_keys_it_does_not_draw():
    """The window assigns collect()'s value over config_data["settings"]: a
    fresh dict would drop repeat_detection_days and anything a later build adds."""
    draft, settings = _draft(repeat_detection_days=30, delimiter_auto_migrated=True)
    draft.apply("threshold", ["9"])
    collected = draft.collect()["settings"]
    assert collected is settings
    assert settings["low_stock_threshold"] == 9
    assert settings["repeat_detection_days"] == 30
    assert settings["delimiter_auto_migrated"] is True


def test_missing_keys_fall_back_to_auto_and_five():
    draft = GeneralDraft({}, "ACME")
    assert draft.collect()["settings"] == {
        "stock_csv_delimiter": "auto",
        "orders_csv_delimiter": "auto",
        "low_stock_threshold": 5,
    }


@pytest.mark.parametrize(
    ("stored", "mode"),
    [("auto", "auto"), (",", "comma"), (";", "semicolon"), ("\t", "tab")],
)
def test_a_named_delimiter_opens_on_its_segment(stored, mode):
    draft, _settings = _draft(stock_csv_delimiter=stored)
    assert _checked(draft, "stock") == [mode]
    assert draft.delimiter("stock") == stored
    assert _delimiter(draft, "stock")["other"] is False


def test_pipe_opens_as_other_and_is_kept():
    draft, _settings = _draft(orders_csv_delimiter="|")
    assert _checked(draft, "orders") == ["other"]
    assert _delimiter(draft, "orders")["char"] == "|"
    assert draft.collect()["settings"]["orders_csv_delimiter"] == "|"


def test_a_hand_edited_value_survives_a_round_trip():
    draft, _settings = _draft(stock_csv_delimiter="||")
    assert draft.collect()["settings"]["stock_csv_delimiter"] == "||"
    assert draft.blocker() is None


# --- edits -------------------------------------------------------------------


def test_choosing_a_segment_changes_what_is_saved():
    draft, _settings = _draft()
    assert draft.apply("delimiter", ["orders", "semicolon"]) is True
    assert draft.collect()["settings"]["orders_csv_delimiter"] == ";"
    assert draft.collect()["settings"]["stock_csv_delimiter"] == "auto"


def test_other_takes_the_typed_character():
    draft, _settings = _draft()
    draft.apply("delimiter", ["stock", "other"])
    draft.apply("delimiter_char", ["stock", "|"])
    assert draft.collect()["settings"]["stock_csv_delimiter"] == "|"


def test_the_other_character_is_remembered_across_segments():
    draft, _settings = _draft(stock_csv_delimiter="|")
    draft.apply("delimiter", ["stock", "comma"])
    draft.apply("delimiter", ["stock", "other"])
    assert draft.delimiter("stock") == "|"


def test_the_threshold_is_saved_as_a_number():
    draft, _settings = _draft()
    draft.apply("threshold", [" 12 "])
    assert draft.collect()["settings"]["low_stock_threshold"] == 12


def test_an_edit_that_changes_nothing_reports_nothing():
    draft, _settings = _draft()
    assert draft.apply("delimiter", ["stock", "auto"]) is False
    assert draft.apply("threshold", ["5"]) is False
    assert draft.apply("delimiter_char", ["stock", ""]) is False


@pytest.mark.parametrize(
    ("action", "args"),
    [
        ("delimiter", ["stock", "pipe"]),
        ("delimiter", ["cats", "auto"]),
        ("delimiter", ["stock"]),
        ("delimiter", "stock"),
        ("delimiter_char", ["cats", "|"]),
        ("delimiter_char", ["stock", 7]),
        ("threshold", [5]),
        ("threshold", []),
        ("nope", []),
    ],
)
def test_an_edit_it_does_not_know_is_dropped(action, args):
    draft, settings = _draft()
    before = dict(settings)
    assert draft.apply(action, args) is False
    assert draft.collect()["settings"] == before


# --- what blocks a save ------------------------------------------------------


def test_nothing_blocks_a_fresh_page():
    draft, _settings = _draft()
    assert draft.blocker() is None
    assert draft.blocker_key() == ""
    assert draft.validate() == (True, [])


def test_other_with_no_character_blocks_the_save():
    draft, _settings = _draft()
    draft.apply("delimiter", ["orders", "other"])
    assert draft.blocker() == "Set Orders CSV delimiter"
    assert draft.blocker_key() == "char-orders"
    assert draft.validate() == (False, [f"Orders CSV delimiter: {DELIMITER_PROBLEM}"])
    row = _delimiter(draft, "orders")
    assert row["problem"] == DELIMITER_PROBLEM
    assert row["hint"] == ""


@pytest.mark.parametrize("text", ["", "abc", "-1", "2.5", "1 2"])
def test_a_threshold_that_is_not_a_whole_number_blocks_the_save(text):
    draft, _settings = _draft()
    draft.apply("threshold", [text])
    assert draft.blocker() == "Set Low-stock threshold"
    assert draft.blocker_key() == "threshold"
    assert draft.validate() == (False, [f"Low-stock threshold: {THRESHOLD_PROBLEM}"])
    assert draft.view()["general"]["threshold"]["problem"] == THRESHOLD_PROBLEM


def test_the_first_problem_on_the_page_is_the_one_named():
    draft, _settings = _draft()
    draft.apply("threshold", ["x"])
    draft.apply("delimiter", ["stock", "other"])
    assert draft.blocker() == "Set Stock CSV delimiter"
    assert len(draft.validate()[1]) == 2


def test_zero_is_a_threshold():
    draft, _settings = _draft()
    draft.apply("threshold", ["0"])
    assert draft.blocker() is None
    assert draft.collect()["settings"]["low_stock_threshold"] == 0


# --- unsaved -----------------------------------------------------------------


def test_an_edit_reads_unsaved_and_undoing_it_reads_clean():
    draft, _settings = _draft()
    draft.mark_clean()
    assert draft.is_dirty() is False
    draft.apply("delimiter", ["stock", "tab"])
    assert draft.is_dirty() is True
    draft.apply("delimiter", ["stock", "auto"])
    assert draft.is_dirty() is False


def test_a_half_typed_threshold_reads_unsaved():
    draft, _settings = _draft()
    draft.mark_clean()
    draft.apply("threshold", [""])
    assert draft.is_dirty() is True


# --- what the page draws -----------------------------------------------------


def test_the_view_names_the_page_and_the_client():
    view = _draft()[0].view()
    assert view["page"] == "general"
    assert view["title"] == "General"
    assert view["subtitle"] == (
        "How ACME's files are read, and when stock counts as low."
    )
    assert view["action"] == ""
    assert view["general"]["csv_text"] == (
        "The character that separates columns in ACME's files."
    )
    assert view["general"]["alerts_text"] == (
        "When a SKU is flagged as low stock in Results."
    )


def test_the_view_lists_stock_then_orders_with_five_segments_each():
    rows = _draft()[0].view()["general"]["delimiters"]
    assert [row["kind"] for row in rows] == ["stock", "orders"]
    assert [row["label"] for row in rows] == [
        "Stock CSV delimiter",
        "Orders CSV delimiter",
    ]
    assert [o["label"] for o in rows[0]["options"]] == [
        "Auto",
        "Comma",
        "Semicolon",
        "Tab",
        "Other",
    ]


@pytest.mark.parametrize(
    ("stored", "hint"),
    [
        ("auto", "Detected for each file as it is read."),
        (",", "Every file is split on commas."),
        (";", "Every file is split on semicolons."),
        ("\t", "Every file is split on tabs."),
        ("|", "Every file is split on “|”."),
    ],
)
def test_the_hint_says_how_files_are_split(stored, hint):
    draft, _settings = _draft(stock_csv_delimiter=stored)
    assert _delimiter(draft, "stock")["hint"] == hint


def test_the_threshold_view_carries_the_text_as_typed():
    draft, _settings = _draft()
    draft.apply("threshold", ["1x"])
    threshold = draft.view()["general"]["threshold"]
    assert threshold["value"] == "1x"
    assert threshold["unit"] == "units"
    assert threshold["hint"].startswith("A SKU is low when fewer than this are left")
```

- [ ] **Step 2: Run it and see it fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_settings_draft_general.py`

Expected: an error at collection, `ModuleNotFoundError: No module named 'gui.settings.page_state'`.

- [ ] **Step 3: Write the draft**

Create `gui/settings/page_state.py`:

```python
"""The values behind the settings pages the web tier draws (phase 7 spec section 4).

A draft is a settings page with no widget. It holds one page's values, takes
the page's edits through apply(), and meets PageContract, so SettingsWindow
saves and marks it exactly as it does a Qt page. view() is everything the web
page draws, sentences included: the page computes nothing. No Qt import.

apply(action, args) returns whether anything changed. The actions are the
spec's section 3.4: add one there before adding it here. The page sends
strings and booleans only; an edit of any other shape is dropped.
"""

import re
from dataclasses import dataclass, field

from gui.settings.contract import PageContract


@dataclass(frozen=True)
class FileColumns:
    """A CSV's header and first row, as a mapping page shows them."""

    name: str  # the file's name, as the card shows it
    columns: tuple[str, ...]  # the header row, in file order
    first_row: dict[str, str] = field(default_factory=dict)  # "" when empty
    loaded: bool = False  # True: the file loaded on Setup. False: picked here


def _shaped(args, *kinds: type) -> bool:
    """Whether `args` is a list of exactly these types, in order."""
    return (
        isinstance(args, list)
        and len(args) == len(kinds)
        and all(type(arg) is kind for arg, kind in zip(args, kinds, strict=True))
    )


# --- General -----------------------------------------------------------------

KINDS = ("stock", "orders")
DELIMITER_LABEL = {"stock": "Stock CSV delimiter", "orders": "Orders CSV delimiter"}
OTHER = "other"
# The segments, in order: (the name the page sends, the label, the character).
DELIMITER_MODES = (
    ("auto", "Auto", "auto"),
    ("comma", "Comma", ","),
    ("semicolon", "Semicolon", ";"),
    ("tab", "Tab", "\t"),
    (OTHER, "Other", None),
)
_MODE_OF = {char: name for name, _label, char in DELIMITER_MODES if char}
_CHAR_OF = {name: char for name, _label, char in DELIMITER_MODES if char}
_SPLIT_ON = {"comma": "commas", "semicolon": "semicolons", "tab": "tabs"}

DELIMITER_PROBLEM = "Type the character that separates the columns."
THRESHOLD_HINT = (
    "A SKU is low when fewer than this are left after the session's orders "
    "are allocated."
)
THRESHOLD_PROBLEM = "Type a whole number, 0 or more."
_WHOLE = re.compile(r"[0-9]+")


class GeneralDraft(PageContract):
    """Delimiters and the low-stock threshold, stored under config_data["settings"]."""

    def __init__(self, settings: dict, client: str):
        # Held by reference so collect() can update it in place: the window
        # assigns collect()'s value straight over config_data[key], so a fresh
        # dict here would drop every key this page does not draw.
        self._settings = settings
        self.client = client
        self.mode: dict[str, str] = {}
        self.char: dict[str, str] = {}
        for kind in KINDS:
            stored = settings.get(f"{kind}_csv_delimiter", "auto")
            # Pipe, and any hand-edited value, open as Other: kept, not rewritten.
            self.mode[kind] = _MODE_OF.get(stored, OTHER)
            self.char[kind] = "" if stored in _MODE_OF else str(stored)
        self.threshold = str(settings.get("low_stock_threshold", 5))

    def apply(self, action: str, args) -> bool:
        if action == "delimiter" and _shaped(args, str, str):
            kind, mode = args
            known = mode == OTHER or mode in _CHAR_OF
            if kind not in KINDS or not known or self.mode[kind] == mode:
                return False
            self.mode[kind] = mode
            return True
        if action == "delimiter_char" and _shaped(args, str, str):
            kind, text = args
            if kind not in KINDS or self.char[kind] == text:
                return False
            self.char[kind] = text
            return True
        if action == "threshold" and _shaped(args, str):
            if self.threshold == args[0]:
                return False
            self.threshold = args[0]
            return True
        return False

    def delimiter(self, kind: str) -> str:
        """What is stored for `kind`: "auto", or the character."""
        mode = self.mode[kind]
        return self.char[kind] if mode == OTHER else _CHAR_OF[mode]

    def _problems(self) -> list[tuple[str, str, str]]:
        """(blocker, data-key, sentence) for each value that cannot be saved."""
        found = [
            (f"Set {DELIMITER_LABEL[kind]}", f"char-{kind}", DELIMITER_PROBLEM)
            for kind in KINDS
            if self.mode[kind] == OTHER and not self.char[kind]
        ]
        if not _WHOLE.fullmatch(self.threshold.strip()):
            found.append(("Set Low-stock threshold", "threshold", THRESHOLD_PROBLEM))
        return found

    def blocker(self) -> str | None:
        problems = self._problems()
        return problems[0][0] if problems else None

    def blocker_key(self) -> str:
        problems = self._problems()
        return problems[0][1] if problems else ""

    def validate(self) -> tuple[bool, list[str]]:
        problems = self._problems()
        return not problems, [
            f"{blocker.removeprefix('Set ')}: {sentence}"
            for blocker, _key, sentence in problems
        ]

    def collect(self) -> dict:
        self._settings.update(
            {
                "stock_csv_delimiter": self.delimiter("stock"),
                "orders_csv_delimiter": self.delimiter("orders"),
                "low_stock_threshold": int(self.threshold.strip()),
            }
        )
        return {"settings": self._settings}

    def _delimiter_view(self, kind: str) -> dict:
        mode = self.mode[kind]
        missing = mode == OTHER and not self.char[kind]
        if mode == "auto":
            hint = "Detected for each file as it is read."
        elif mode == OTHER:
            hint = "" if missing else f"Every file is split on “{self.char[kind]}”."
        else:
            hint = f"Every file is split on {_SPLIT_ON[mode]}."
        return {
            "kind": kind,
            "label": DELIMITER_LABEL[kind],
            "options": [
                {"value": name, "label": label, "checked": name == mode}
                for name, label, _char in DELIMITER_MODES
            ],
            "other": mode == OTHER,
            "char": self.char[kind],
            "hint": hint,
            "problem": DELIMITER_PROBLEM if missing else "",
        }

    def view(self) -> dict:
        bad_threshold = not _WHOLE.fullmatch(self.threshold.strip())
        return {
            "page": "general",
            "title": "General",
            "subtitle": (
                f"How {self.client}'s files are read, and when stock counts as low."
            ),
            "action": "",
            "general": {
                "csv_text": (
                    f"The character that separates columns in {self.client}'s files."
                ),
                "alerts_text": "When a SKU is flagged as low stock in Results.",
                "delimiters": [self._delimiter_view(kind) for kind in KINDS],
                "threshold": {
                    "value": self.threshold,
                    "unit": "units",
                    "hint": THRESHOLD_HINT,
                    "problem": THRESHOLD_PROBLEM if bad_threshold else "",
                },
            },
        }
```

- [ ] **Step 4: Run the test**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_settings_draft_general.py`

Expected: all pass.

- [ ] **Step 5: Lint and commit**

Run: `.venv/bin/ruff check .` Expected: `All checks passed!`

Stage `gui/settings/page_state.py tests/test_settings_draft_general.py` and commit. Message subject:
`Settings: GeneralDraft, the General page's values with no widget`.

---

### Task 5: `MappingDraft` and `StockDraft`

One CSV's column mapping (spec §4.3): which column holds each field, read from and written to
`{csv column: internal name}`.

**Files:**
- Modify: `gui/settings/page_state.py`
- Test: `tests/test_settings_draft_mapping.py` (new)

**Interfaces:**
- Consumes: `PageContract`, `FileColumns`, `_shaped` (Tasks 3, 4).
- Produces, in `gui.settings.page_state`:
  - `MappingField(name, label, required=False, hint="", example="")`, a frozen dataclass, and
    `FIELDS: dict[str, tuple[MappingField, ...]]` keyed `"orders"` and `"stock"`.
  - `MappingDraft(kind: str, column_mappings: dict, client: str, file: FileColumns | None = None)` with
    `chosen: dict[str, str]` (internal name → column, `""` for none), `file`, `set_file(file)`,
    `apply("column", [field, column]) -> bool`, `mappings() -> dict`, `view() -> dict`, the contract, and
    the hooks `_column_taken(column)`, `_mapping_view() -> dict`, `_write_mapping() -> dict` that
    `OrdersDraft` extends.
  - `StockDraft(column_mappings: dict, client: str, file: FileColumns | None = None)`.
  - Constants `READ_ACTION`, `NOT_IN_FILE`, `MAPPING_TITLE`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_settings_draft_mapping.py`:

```python
"""MappingDraft and StockDraft: a CSV's column mapping, with no widget
(phase 7 spec section 4.3)."""

import pytest

from gui.settings.page_state import (
    FIELDS,
    NOT_IN_FILE,
    FileColumns,
    MappingDraft,
    StockDraft,
)

ORDERS = {
    "Name": "Order_Number",
    "Lineitem sku": "SKU",
    "Lineitem quantity": "Quantity",
    "Shipping Method": "Shipping_Method",
    "Lineitem name": "Product_Name",
}
STOCK = {"Article": "SKU", "Available": "Stock", "Годност": "Expiry_Date"}

ORDERS_FILE = FileColumns(
    name="orders-30-09.csv",
    columns=(
        "Name",
        "Lineitem sku",
        "Lineitem quantity",
        "Shipping Method",
        "Lineitem name",
        "Tags",
        "Discount Code",
    ),
    first_row={
        "Name": "#10482",
        "Lineitem sku": "ACM-TEE-BLK-M",
        "Lineitem quantity": "2",
        "Shipping Method": "DHL Express Worldwide",
        "Lineitem name": "Tee, black, M",
        "Tags": "VIP, repeat",
        "Discount Code": "",
    },
    loaded=True,
)


def _mappings(orders=None, stock=None):
    return {
        "version": 2,
        "orders": dict(ORDERS if orders is None else orders),
        "stock": dict(STOCK if stock is None else stock),
    }


def _orders(file=ORDERS_FILE, **kwargs):
    live = _mappings(**kwargs)
    return MappingDraft("orders", live, "ACME", file), live


def _field(draft, name):
    return next(f for f in draft.view()["mapping"]["fields"] if f["name"] == name)


# --- what it opens with ------------------------------------------------------


def test_the_orders_page_has_the_profiles_twelve_fields_required_first():
    assert [f.name for f in FIELDS["orders"]] == [
        "Order_Number",
        "SKU",
        "Quantity",
        "Shipping_Method",
        "Product_Name",
        "Shipping_Country",
        "Tags",
        "Notes",
        "Total_Price",
        "Subtotal",
        "Customer",
        "Created_At",
    ]
    assert [f.name for f in FIELDS["orders"] if f.required] == [
        "Order_Number",
        "SKU",
        "Quantity",
        "Shipping_Method",
    ]


def test_the_stock_page_has_rows_for_the_lot_tracking_fields():
    """Expiry_Date and Batch are the names _build_fifo_lots() reads. A page
    with no row for them once deleted both mappings on every save."""
    assert [f.name for f in FIELDS["stock"]] == [
        "SKU",
        "Stock",
        "Product_Name",
        "Expiry_Date",
        "Batch",
    ]
    assert [f.name for f in FIELDS["stock"] if f.required] == ["SKU", "Stock"]


def test_it_reads_each_fields_column_from_the_stored_mapping():
    draft, _live = _orders()
    assert draft.chosen["Order_Number"] == "Name"
    assert draft.chosen["Product_Name"] == "Lineitem name"
    assert draft.chosen["Tags"] == ""


def test_it_round_trips_a_stored_mapping_untouched():
    draft, live = _orders()
    assert draft.collect() == {"column_mappings": live}
    assert live["orders"] == ORDERS
    assert live["stock"] == STOCK
    assert live["version"] == 2


def test_a_mapping_that_is_not_a_dict_opens_empty():
    live = {"orders": None, "stock": STOCK}
    draft = MappingDraft("orders", live, "ACME")
    assert set(draft.chosen.values()) == {""}


def test_an_internal_name_with_no_row_is_carried_through():
    draft, live = _orders(orders={**ORDERS, "Phone": "Shipping_Phone"})
    draft.collect()
    assert live["orders"]["Phone"] == "Shipping_Phone"


def test_stock_lot_mappings_round_trip():
    live = _mappings(stock={**STOCK, "Партида": "Batch"})
    draft = StockDraft(live, "ACME")
    draft.collect()
    assert live["stock"]["Годност"] == "Expiry_Date"
    assert live["stock"]["Партида"] == "Batch"


# --- choosing a column -------------------------------------------------------


def test_choosing_a_column_maps_it():
    draft, live = _orders()
    assert draft.apply("column", ["Tags", "Tags"]) is True
    draft.collect()
    assert live["orders"]["Tags"] == "Tags"


def test_not_imported_removes_an_optional_mapping():
    draft, live = _orders()
    assert draft.apply("column", ["Product_Name", ""]) is True
    draft.collect()
    assert "Lineitem name" not in live["orders"]


def test_a_required_field_cannot_be_set_to_not_imported():
    draft, _live = _orders()
    assert draft.apply("column", ["SKU", ""]) is False
    assert draft.chosen["SKU"] == "Lineitem sku"


def test_a_column_another_field_holds_moves():
    """The profile stores one field per column: {column: field}."""
    draft, live = _orders()
    assert draft.apply("column", ["Tags", "Lineitem name"]) is True
    assert draft.chosen["Tags"] == "Lineitem name"
    assert draft.chosen["Product_Name"] == ""
    draft.collect()
    assert live["orders"]["Lineitem name"] == "Tags"


def test_taking_a_required_fields_column_leaves_it_missing():
    draft, _live = _orders()
    draft.apply("column", ["Tags", "Shipping Method"])
    assert draft.chosen["Shipping_Method"] == ""
    assert draft.blocker() == "Map Shipping method"


@pytest.mark.parametrize(
    "args",
    [
        ["Tags", "No Such Column"],
        ["No_Such_Field", "Tags"],
        ["Tags"],
        ["Tags", 3],
        "Tags",
    ],
)
def test_an_edit_it_does_not_know_is_dropped(args):
    draft, _live = _orders()
    before = dict(draft.chosen)
    assert draft.apply("column", args) is False
    assert draft.chosen == before


def test_an_unknown_action_is_dropped():
    draft, _live = _orders()
    assert draft.apply("courier_add", []) is False


def test_choosing_the_column_already_chosen_reports_nothing():
    draft, _live = _orders()
    assert draft.apply("column", ["SKU", "Lineitem sku"]) is False


def test_nothing_can_be_chosen_before_a_file_is_read():
    draft, _live = _orders(file=None)
    assert draft.apply("column", ["Tags", "Tags"]) is False
    assert draft.apply("column", ["Product_Name", ""]) is False


def test_reading_a_file_changes_no_mapping():
    draft, _live = _orders(file=None)
    before = dict(draft.chosen)
    draft.set_file(FileColumns("other.csv", ("A", "B"), {"A": "1", "B": "2"}))
    assert draft.chosen == before
    assert draft.view()["mapping"]["columns"] == ["A", "B"]


# --- one live dict, two drafts -----------------------------------------------


def test_both_drafts_write_into_one_live_dict_in_either_order():
    for first in ("orders", "stock"):
        live = _mappings()
        orders = MappingDraft("orders", live, "ACME", ORDERS_FILE)
        stock = StockDraft(live, "ACME")
        orders.apply("column", ["Tags", "Tags"])
        drafts = [orders, stock] if first == "orders" else [stock, orders]
        for draft in drafts:
            assert draft.collect()["column_mappings"] is live
        assert live["orders"]["Tags"] == "Tags"
        assert live["stock"] == STOCK


def test_an_edit_on_orders_leaves_stock_clean():
    live = _mappings()
    orders = MappingDraft("orders", live, "ACME", ORDERS_FILE)
    stock = StockDraft(live, "ACME")
    orders.mark_clean()
    stock.mark_clean()
    orders.apply("column", ["Tags", "Tags"])
    orders.collect()
    assert orders.is_dirty() is True
    assert stock.is_dirty() is False


# --- what blocks a save ------------------------------------------------------


def test_nothing_blocks_a_complete_mapping():
    draft, _live = _orders()
    assert draft.blocker() is None
    assert draft.blocker_key() == ""
    assert draft.validate() == (True, [])


def test_a_required_field_with_no_column_blocks_the_save():
    orders = {k: v for k, v in ORDERS.items() if v != "Shipping_Method"}
    draft, _live = _orders(orders=orders)
    assert draft.blocker() == "Map Shipping method"
    assert draft.blocker_key() == "field-Shipping_Method"
    assert draft.validate() == (
        False,
        [
            (
                "Shipping method is required. Choose the column that holds it, "
                "e.g. Shipping Method."
            )
        ],
    )
    row = _field(draft, "Shipping_Method")
    assert row["problem"] == (
        "Shipping method is required. Choose the column that holds it, e.g."
    )
    assert row["example"] == "Shipping Method"


def test_with_no_file_the_problem_says_to_read_one_first():
    orders = {k: v for k, v in ORDERS.items() if v != "SKU"}
    draft, _live = _orders(file=None, orders=orders)
    row = _field(draft, "SKU")
    assert row["problem"] == (
        "SKU is required. Use Read columns from CSV…, then choose its column."
    )
    assert row["example"] == ""
    assert draft.validate()[1] == [row["problem"]]


def test_the_first_missing_field_in_page_order_is_the_one_named():
    draft, _live = _orders(orders={"Name": "Order_Number"})
    assert draft.blocker() == "Map SKU"
    assert len(draft.validate()[1]) == 3


def test_an_optional_field_never_has_a_problem():
    draft, _live = _orders()
    assert _field(draft, "Tags")["problem"] == ""


# --- what the page draws -----------------------------------------------------


def test_the_view_names_the_page_and_its_action():
    view = _orders()[0].view()
    assert view["page"] == "orders"
    assert view["title"] == "Orders mapping"
    assert view["subtitle"] == "Which column of ACME's orders CSV holds each field."
    assert view["action"] == "Read columns from CSV…"

    stock = StockDraft(_mappings(), "ACME").view()
    assert stock["page"] == "stock"
    assert stock["title"] == "Stock mapping"
    assert stock["subtitle"] == "Which column of ACME's stock CSV holds each field."
    assert "couriers" not in stock["mapping"]
    assert "additional" not in stock["mapping"]


def test_the_source_sentence_says_where_the_columns_came_from():
    loaded, _live = _orders()
    assert loaded.view()["mapping"]["source"] == {
        "lead": "Columns read from",
        "file": "orders-30-09.csv",
        "tail": ", the file loaded on Setup.",
    }
    picked, _live = _orders(file=FileColumns("picked.csv", ("Name",)))
    assert picked.view()["mapping"]["source"] == {
        "lead": "Columns read from",
        "file": "picked.csv",
        "tail": ".",
    }
    none, _live = _orders(file=None)
    assert none.view()["mapping"]["source"] == {
        "lead": "No CSV has been read. Use Read columns from CSV… to change a field.",
        "file": "",
        "tail": "",
    }


def test_the_view_says_whether_a_column_can_be_picked_and_lists_them():
    with_file = _orders()[0].view()["mapping"]
    assert with_file["can_pick"] is True
    assert with_file["columns"] == list(ORDERS_FILE.columns)
    without = _orders(file=None)[0].view()["mapping"]
    assert without["can_pick"] is False
    assert without["columns"] == []


def test_held_names_the_field_that_holds_each_chosen_column():
    held = _orders()[0].view()["mapping"]["held"]
    assert held == {
        "Name": "Order number",
        "Lineitem sku": "SKU",
        "Lineitem quantity": "Quantity",
        "Shipping Method": "Shipping method",
        "Lineitem name": "Product name",
    }


def test_a_field_row_carries_its_column_and_the_first_rows_value():
    row = _field(_orders()[0], "Order_Number")
    assert row == {
        "name": "Order_Number",
        "label": "Order number",
        "required": True,
        "column": "Name",
        "placeholder": "Choose column",
        "sample": "#10482",
        "sample_missing": False,
        "problem": "",
        "example": "",
        "hint": "",
    }


def test_an_unmapped_optional_field_reads_not_imported():
    row = _field(_orders()[0], "Tags")
    assert row["column"] == ""
    assert row["placeholder"] == "Not imported"
    assert row["sample"] == ""


def test_a_saved_column_the_file_lacks_stays_and_says_so():
    draft, live = _orders(orders={**ORDERS, "Old Notes": "Notes"})
    row = _field(draft, "Notes")
    assert row["column"] == "Old Notes"
    assert row["sample"] == NOT_IN_FILE
    assert row["sample_missing"] is True
    draft.collect()
    assert live["orders"]["Old Notes"] == "Notes"


def test_with_no_file_a_row_has_its_column_and_no_sample():
    row = _field(_orders(file=None)[0], "Order_Number")
    assert row["column"] == "Name"
    assert row["sample"] == ""
    assert row["sample_missing"] is False


def test_the_lot_fields_explain_themselves():
    draft = StockDraft(_mappings(), "ACME")
    assert _field(draft, "Expiry_Date")["hint"].startswith(
        "When mapped, stock is allocated oldest expiry first"
    )
    assert _field(draft, "Batch")["hint"].startswith("Lot or batch number.")
    assert _field(draft, "SKU")["hint"] == ""
```

- [ ] **Step 2: Run it and see it fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_settings_draft_mapping.py`

Expected: an error at collection, `ImportError: cannot import name 'FIELDS'`.

- [ ] **Step 3: Write the drafts**

In `gui/settings/page_state.py`, find exactly:

```python
import re
from dataclasses import dataclass, field
```

Replace with:

```python
import json
import re
from dataclasses import dataclass, field
```

In `gui/settings/page_state.py`, append at the end of the file:

```python


# --- column mapping ----------------------------------------------------------

READ_ACTION = "Read columns from CSV…"
NOT_IN_FILE = "Not in this file"
MAPPING_TITLE = {"orders": "Orders mapping", "stock": "Stock mapping"}


@dataclass(frozen=True)
class MappingField:
    """One internal field a CSV column can be mapped to."""

    name: str  # the internal name the analysis reads
    label: str
    required: bool = False
    hint: str = ""
    example: str = ""  # a column that usually holds it; required fields only


# Expiry_Date and Batch are the exact internal names _build_fifo_lots() looks
# for (shopify_tool/analysis.py): renaming them here silently turns FIFO lot
# allocation off.
FIELDS: dict[str, tuple[MappingField, ...]] = {
    "orders": (
        MappingField("Order_Number", "Order number", True, example="Name"),
        MappingField("SKU", "SKU", True, example="Lineitem sku"),
        MappingField("Quantity", "Quantity", True, example="Lineitem quantity"),
        MappingField(
            "Shipping_Method", "Shipping method", True, example="Shipping Method"
        ),
        MappingField("Product_Name", "Product name"),
        MappingField("Shipping_Country", "Country"),
        MappingField("Tags", "Tags"),
        MappingField("Notes", "Notes"),
        MappingField("Total_Price", "Total price"),
        MappingField("Subtotal", "Subtotal"),
        MappingField("Customer", "Customer"),
        MappingField("Created_At", "Created at"),
    ),
    "stock": (
        MappingField("SKU", "SKU", True, example="Артикул"),
        MappingField("Stock", "Quantity", True, example="Наличност"),
        MappingField("Product_Name", "Product name"),
        MappingField(
            "Expiry_Date",
            "Expiry date",
            hint=(
                "When mapped, stock is allocated oldest expiry first, and each "
                "packing list row shows its lot. Reads YYMMDD, YYYYMMDD, DDMMYY "
                "and MMYY."
            ),
        ),
        MappingField(
            "Batch",
            "Batch",
            hint=(
                "Lot or batch number. Shown per lot on packing lists, and keeps "
                "separate deliveries of one SKU apart."
            ),
        ),
    ),
}


class MappingDraft(PageContract):
    """One CSV's column mapping, stored as {csv column: internal name}.

    Both mapping drafts hold the SAME live config_data["column_mappings"] dict
    and write only their own sub-key into it, in place. Never clear() it and
    never rebuild it: whichever draft collect()s second would wipe the other's
    sub-key.
    """

    def __init__(
        self,
        kind: str,
        column_mappings: dict,
        client: str,
        file: FileColumns | None = None,
    ):
        self.kind = kind
        self.column_mappings = column_mappings
        self.client = client
        self.file = file
        self.fields = FIELDS[kind]
        by_internal = {internal: column for column, internal in self._stored().items()}
        self.chosen = {f.name: by_internal.get(f.name, "") for f in self.fields}

    def _stored(self) -> dict:
        stored = self.column_mappings.get(self.kind)
        return stored if isinstance(stored, dict) else {}

    def _field(self, name: str) -> MappingField | None:
        return next((f for f in self.fields if f.name == name), None)

    def set_file(self, file: FileColumns) -> None:
        """Offer this file's columns. It changes no mapping."""
        self.file = file

    def apply(self, action: str, args) -> bool:
        if action != "column" or not _shaped(args, str, str):
            return False
        name, column = args
        target = self._field(name)
        if target is None or self.file is None:
            return False
        if column == "":
            if target.required:
                return False
        elif column not in self.file.columns:
            return False
        if self.chosen[name] == column:
            return False
        if column:
            # The profile stores one field per column, so the column moves.
            for other in self.chosen:
                if self.chosen[other] == column:
                    self.chosen[other] = ""
            self._column_taken(column)
        self.chosen[name] = column
        return True

    def _column_taken(self, column: str) -> None:
        """A field now holds `column`. OrdersDraft lets go of it elsewhere."""

    def mappings(self) -> dict:
        """{csv column: internal name}, as stored.

        Entries for internal names this page has no row for are carried
        through untouched: dropping them is how the Expiry_Date and Batch
        mappings that drive FIFO were once deleted on every save. A field
        with no column is left out.
        """
        managed = {f.name for f in self.fields}
        result = {
            column: internal
            for column, internal in self._stored().items()
            if internal not in managed
        }
        for f in self.fields:
            if self.chosen[f.name]:
                result[self.chosen[f.name]] = f.name
        return result

    def _write_mapping(self) -> dict:
        """Write this draft's sub-key into the live dict and return the dict."""
        self.column_mappings["version"] = 2
        self.column_mappings[self.kind] = self.mappings()
        return self.column_mappings

    def collect(self) -> dict:
        return {"column_mappings": self._write_mapping()}

    def snapshot(self) -> str:
        """Only this draft's own mapping: column_mappings is one live dict
        shared by both mapping drafts, so a snapshot of collect() would mark
        both unsaved when either changes."""
        return json.dumps(self.mappings(), sort_keys=True, default=str)

    def _missing(self) -> MappingField | None:
        return next(
            (f for f in self.fields if f.required and not self.chosen[f.name]), None
        )

    def blocker(self) -> str | None:
        missing = self._missing()
        return f"Map {missing.label}" if missing else None

    def blocker_key(self) -> str:
        missing = self._missing()
        return f"field-{missing.name}" if missing else ""

    def _problem(self, f: MappingField) -> tuple[str, str]:
        """(sentence, example): the page draws the example in the mono face
        and closes the sentence after it."""
        if not f.required or self.chosen[f.name]:
            return "", ""
        if self.file is None:
            return (
                f"{f.label} is required. Use {READ_ACTION}, then choose its column.",
                "",
            )
        return f"{f.label} is required. Choose the column that holds it, e.g.", f.example

    def validate(self) -> tuple[bool, list[str]]:
        problems = []
        for f in self.fields:
            sentence, example = self._problem(f)
            if sentence:
                problems.append(f"{sentence} {example}." if example else sentence)
        return not problems, problems

    def _source(self) -> dict:
        if self.file is None:
            return {
                "lead": f"No CSV has been read. Use {READ_ACTION} to change a field.",
                "file": "",
                "tail": "",
            }
        return {
            "lead": "Columns read from",
            "file": self.file.name,
            "tail": ", the file loaded on Setup." if self.file.loaded else ".",
        }

    def _field_view(self, f: MappingField) -> dict:
        column = self.chosen[f.name]
        lacking = bool(column) and self.file is not None and column not in self.file.columns
        if lacking:
            sample = NOT_IN_FILE
        elif column and self.file is not None:
            sample = self.file.first_row.get(column, "")
        else:
            sample = ""
        problem, example = self._problem(f)
        return {
            "name": f.name,
            "label": f.label,
            "required": f.required,
            "column": column,
            "placeholder": "Choose column" if f.required else "Not imported",
            "sample": sample,
            "sample_missing": lacking,
            "problem": problem,
            "example": example,
            "hint": f.hint,
        }

    def _mapping_view(self) -> dict:
        labels = {f.name: f.label for f in self.fields}
        return {
            "kind": self.kind,
            "source": self._source(),
            "can_pick": self.file is not None,
            "columns": list(self.file.columns) if self.file is not None else [],
            "held": {
                column: labels[name] for name, column in self.chosen.items() if column
            },
            "fields": [self._field_view(f) for f in self.fields],
        }

    def view(self) -> dict:
        return {
            "page": self.kind,
            "title": MAPPING_TITLE[self.kind],
            "subtitle": (
                f"Which column of {self.client}'s {self.kind} CSV holds each field."
            ),
            "action": READ_ACTION,
            "mapping": self._mapping_view(),
        }


class StockDraft(MappingDraft):
    """Stock CSV columns, including the two that drive FIFO lot allocation."""

    def __init__(
        self, column_mappings: dict, client: str, file: FileColumns | None = None
    ):
        super().__init__("stock", column_mappings, client, file)
```


- [ ] **Step 4: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_settings_draft_mapping.py tests/test_settings_draft_general.py`

Expected: all pass.

- [ ] **Step 5: Lint and commit**

Run: `.venv/bin/ruff check .` Expected: `All checks passed!`

Stage `gui/settings/page_state.py tests/test_settings_draft_mapping.py` and commit. Message subject:
`Settings: MappingDraft and StockDraft, a CSV's column mapping with no widget`.

---

### Task 6: `OrdersDraft`: courier names and additional columns

The Orders mapping page's two extra cards (spec §4.4).

**Files:**
- Modify: `gui/settings/page_state.py`
- Test: `tests/test_settings_draft_orders.py` (new)

**Interfaces:**
- Consumes: `MappingDraft` and its hooks (Task 5); `shopify_tool.csv_utils.discover_additional_columns`
  (already in the repo).
- Produces, in `gui.settings.page_state`:
  - `OrdersDraft(column_mappings: dict, courier_mappings: dict, client: str,
    fallback_additional_columns=None, file: FileColumns | None = None)` with `courier_rows:
    list[list[str]]` (`[text, code]`), `entries: list[dict]`, `additional_known: bool`, `couriers() -> dict`.
    Actions beyond `column`: `("courier_add", [])`, `("courier_pattern", [index, text])`,
    `("courier_code", [index, code])`, `("courier_remove", [index])`, `("column_add", [name])`,
    `("column_remove", [name])`, `("column_fill", [name, on])`. `index` is a string of digits; `on` is a bool.
  - `ADDITIONAL_COLUMNS_UNREADABLE`, the sentinel the window passes as `fallback_additional_columns` when
    the client config could not be read.
  - Constants `COURIER_TEXT`, `COURIER_EMPTY`, `ADDITIONAL_TEXT`, `ADDITIONAL_EMPTY`, `ADDITIONAL_UNKNOWN`,
    `NOT_FILLED_DOWN`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_settings_draft_orders.py`:

```python
"""OrdersDraft: courier names and additional columns, with no widget
(phase 7 spec section 4.4)."""

import copy

import pytest

from gui.settings.page_state import (
    ADDITIONAL_COLUMNS_UNREADABLE,
    ADDITIONAL_UNKNOWN,
    COURIER_EMPTY,
    NOT_IN_FILE,
    FileColumns,
    OrdersDraft,
    StockDraft,
)

ORDERS = {
    "Name": "Order_Number",
    "Lineitem sku": "SKU",
    "Lineitem quantity": "Quantity",
    "Shipping Method": "Shipping_Method",
}
COURIERS = {
    "DHL": {"patterns": ["dhl", "DHL Express"], "case_sensitive": False},
    "DPD": {"patterns": ["dpd"], "case_sensitive": False},
}
FILE = FileColumns(
    name="orders-30-09.csv",
    columns=(
        "Name",
        "Lineitem sku",
        "Lineitem quantity",
        "Shipping Method",
        "Notes",
        "Discount Code",
    ),
    first_row={"Name": "#10482", "Notes": "leave at door"},
    loaded=True,
)


def _entry(name, enabled=True, order_level=True, exists=True):
    return {
        "csv_name": name,
        "internal_name": name.replace(" ", "_"),
        "enabled": enabled,
        "is_order_level": order_level,
        "exists_in_df": exists,
    }


def _draft(additional=None, couriers=None, file=FILE, fallback=None, key=True):
    live = {"version": 2, "orders": dict(ORDERS), "stock": {"Article": "SKU"}}
    if key:
        live["additional_columns"] = copy.deepcopy(additional or [])
    live_couriers = copy.deepcopy(COURIERS if couriers is None else couriers)
    draft = OrdersDraft(live, live_couriers, "ACME", fallback, file)
    return draft, live, live_couriers


def _rows(draft):
    return [(row["text"], row["code"]) for row in draft.view()["mapping"]["couriers"]["rows"]]


def _additional(draft):
    return draft.view()["mapping"]["additional"]


def _names(items):
    return [item["name"] for item in items]


# --- courier names -----------------------------------------------------------


def test_each_stored_pattern_is_a_row():
    draft, _live, _couriers = _draft()
    assert _rows(draft) == [("dhl", "DHL"), ("DHL Express", "DHL"), ("dpd", "DPD")]
    assert draft.view()["mapping"]["couriers"]["codes"] == ["DHL", "DPD"]


def test_courier_names_round_trip_untouched():
    draft, _live, couriers = _draft()
    before = copy.deepcopy(couriers)
    assert draft.collect()["courier_mappings"] is couriers
    assert couriers == before


def test_a_legacy_entry_loads_as_a_row_and_is_saved_in_the_new_shape():
    """{"dhl": "DHL"} is still matched by the analysis; the old page dropped it."""
    draft, _live, couriers = _draft(couriers={"dhl": "DHL", "speedy": "Speedy"})
    assert _rows(draft) == [("dhl", "DHL"), ("speedy", "Speedy")]
    draft.collect()
    assert couriers == {
        "DHL": {"patterns": ["dhl"], "case_sensitive": False},
        "Speedy": {"patterns": ["speedy"], "case_sensitive": False},
    }


def test_no_mappings_shows_the_empty_sentence_and_no_rows():
    draft, _live, couriers = _draft(couriers={})
    view = draft.view()["mapping"]["couriers"]
    assert view["rows"] == []
    assert view["empty"] == COURIER_EMPTY
    draft.collect()
    assert couriers == {}


def test_a_new_row_is_saved_once_it_has_both_sides():
    draft, _live, couriers = _draft()
    assert draft.apply("courier_add", []) is True
    assert _rows(draft)[-1] == ("", "")
    draft.collect()
    assert "" not in couriers and len(couriers) == 2

    draft.apply("courier_pattern", ["3", "evri"])
    draft.collect()
    assert len(couriers) == 2

    draft.apply("courier_code", ["3", " Evri "])
    draft.collect()
    assert couriers["Evri"] == {"patterns": ["evri"], "case_sensitive": False}
    assert list(couriers) == ["DHL", "DPD", "Evri"]


def test_a_row_given_an_existing_courier_joins_its_patterns():
    draft, _live, couriers = _draft()
    draft.apply("courier_add", [])
    draft.apply("courier_pattern", ["3", "dpd classic"])
    draft.apply("courier_code", ["3", "DPD"])
    draft.collect()
    assert couriers["DPD"]["patterns"] == ["dpd", "dpd classic"]


def test_removing_a_couriers_last_row_removes_the_courier():
    """The live dict is cleared and refilled: an update() would leave DPD behind."""
    draft, _live, couriers = _draft()
    assert draft.apply("courier_remove", ["2"]) is True
    draft.collect()
    assert list(couriers) == ["DHL"]


def test_a_repeated_text_is_saved_once_and_spaces_are_trimmed():
    draft, _live, couriers = _draft()
    draft.apply("courier_add", [])
    draft.apply("courier_pattern", ["3", "  dhl  "])
    draft.apply("courier_code", ["3", "DHL"])
    draft.collect()
    assert couriers["DHL"]["patterns"] == ["dhl", "DHL Express"]


def test_the_typed_text_is_kept_as_typed_in_the_view():
    draft, _live, _couriers = _draft()
    draft.apply("courier_pattern", ["0", "dhl "])
    assert _rows(draft)[0] == ("dhl ", "DHL")


@pytest.mark.parametrize(
    ("action", "args"),
    [
        ("courier_pattern", ["9", "x"]),
        ("courier_pattern", ["-1", "x"]),
        ("courier_pattern", ["one", "x"]),
        ("courier_pattern", [0, "x"]),
        ("courier_code", ["0", "   "]),
        ("courier_code", ["0"]),
        ("courier_remove", ["9"]),
        ("courier_remove", []),
        ("courier_add", ["x"]),
        ("column_add", ["No Such Column"]),
        ("column_remove", ["No Such Column"]),
        ("column_fill", ["Notes", "yes"]),
        ("nope", []),
    ],
)
def test_an_edit_it_does_not_know_is_dropped(action, args):
    draft, _live, _couriers = _draft(additional=[_entry("Notes")])
    before = draft.snapshot()
    assert draft.apply(action, args) is False
    assert draft.snapshot() == before


def test_it_still_takes_column_edits():
    draft, live, _couriers = _draft()
    assert draft.apply("column", ["Notes", "Notes"]) is True
    draft.collect()
    assert live["orders"]["Notes"] == "Notes"


# --- additional columns: where the list comes from (ADR 0006) ----------------


def test_without_the_key_the_old_client_config_list_is_shown():
    draft, _live, _couriers = _draft(key=False, fallback=[_entry("Notes")])
    assert _names(_additional(draft)["chips"]) == ["Notes"]


def test_the_mappings_key_wins_over_the_fallback():
    draft, _live, _couriers = _draft(
        additional=[_entry("Notes")], fallback=[_entry("Discount Code")]
    )
    assert _names(_additional(draft)["chips"]) == ["Notes"]


def test_a_stored_entry_gets_every_key_it_lacks():
    draft, live, _couriers = _draft(additional=[{"csv_name": "Gift Note"}], file=None)
    draft.collect()
    assert live["additional_columns"] == [
        {
            "csv_name": "Gift Note",
            "internal_name": "Gift_Note",
            "enabled": False,
            "is_order_level": True,
            "exists_in_df": True,
        }
    ]


def test_an_unreadable_client_config_leaves_the_stored_list_alone():
    draft, live, _couriers = _draft(key=False, fallback=ADDITIONAL_COLUMNS_UNREADABLE)
    assert _additional(draft)["notice"] == ADDITIONAL_UNKNOWN
    assert _additional(draft)["chips"] == []
    draft.collect()
    assert "additional_columns" not in live


def test_keeping_a_column_after_an_unreadable_config_saves_again():
    draft, live, _couriers = _draft(key=False, fallback=ADDITIONAL_COLUMNS_UNREADABLE)
    assert draft.apply("column_add", ["Notes"]) is True
    assert _additional(draft)["notice"] == ""
    draft.collect()
    assert [e["csv_name"] for e in live["additional_columns"]] == ["Notes"]


# --- additional columns: keeping and letting go ------------------------------


def test_reading_a_file_offers_its_unmapped_columns_and_stores_nothing():
    draft, live, _couriers = _draft()
    additional = _additional(draft)
    assert additional["chips"] == []
    assert _names(additional["candidates"]) == ["Discount Code", "Notes"]
    assert additional["group"] == "Unmapped columns in orders-30-09.csv"
    assert additional["empty"] == "None kept."
    draft.collect()
    assert live["additional_columns"] == []


def test_keeping_a_candidate_stores_it_enabled_and_filled_down():
    draft, live, _couriers = _draft()
    assert draft.apply("column_add", ["Discount Code"]) is True
    assert _additional(draft)["chips"] == [
        {"name": "Discount Code", "note": "", "fill": True}
    ]
    assert _names(_additional(draft)["candidates"]) == ["Notes"]
    draft.collect()
    assert live["additional_columns"] == [
        {
            "csv_name": "Discount Code",
            "internal_name": "Discount_Code",
            "enabled": True,
            "is_order_level": True,
            "exists_in_df": True,
        }
    ]


def test_removing_a_chip_turns_the_entry_off_and_keeps_it():
    draft, live, _couriers = _draft(additional=[_entry("Notes")])
    assert draft.apply("column_remove", ["Notes"]) is True
    assert _additional(draft)["chips"] == []
    assert "Notes" in _names(_additional(draft)["candidates"])
    draft.collect()
    assert live["additional_columns"][0]["enabled"] is False
    assert draft.apply("column_remove", ["Notes"]) is False


def test_a_column_turned_off_earlier_can_be_kept_again():
    draft, _live, _couriers = _draft(additional=[_entry("Notes", enabled=False)])
    assert draft.apply("column_add", ["Notes"]) is True
    assert len(draft.entries) == 1
    assert draft.entries[0]["enabled"] is True
    assert draft.apply("column_add", ["Notes"]) is False


def test_fill_down_is_the_order_level_flag():
    draft, live, _couriers = _draft(additional=[_entry("Notes")])
    assert draft.apply("column_fill", ["Notes", False]) is True
    assert _additional(draft)["chips"] == [
        {"name": "Notes", "note": "not filled down", "fill": False}
    ]
    draft.collect()
    assert live["additional_columns"][0]["is_order_level"] is False
    assert draft.apply("column_fill", ["Notes", False]) is False


def test_a_kept_column_the_file_lacks_says_so():
    draft, _live, _couriers = _draft(
        additional=[_entry("Gift Note", order_level=False)]
    )
    assert _additional(draft)["chips"] == [
        {"name": "Gift Note", "note": f"{NOT_IN_FILE}, not filled down", "fill": False}
    ]


def test_with_no_file_only_columns_turned_off_earlier_are_offered():
    draft, _live, _couriers = _draft(
        additional=[_entry("Notes"), _entry("Gift Note", enabled=False)], file=None
    )
    additional = _additional(draft)
    assert additional["chips"] == [{"name": "Notes", "note": "", "fill": True}]
    assert additional["candidates"] == [{"name": "Gift Note", "note": ""}]
    assert additional["group"] == "Turned off earlier"


def test_the_add_button_says_why_it_has_nothing_to_offer():
    none_read, _live, _couriers = _draft(file=None)
    assert _additional(none_read)["add_title"] == (
        "Use Read columns from CSV… to list the file's unmapped columns."
    )
    all_used, _live, _couriers = _draft(
        additional=[_entry("Notes"), _entry("Discount Code")]
    )
    assert _additional(all_used)["add_title"] == (
        "Every column in this file is mapped or kept."
    )
    some, _live, _couriers = _draft()
    assert _additional(some)["add_title"] == ""


def test_mapping_a_kept_column_to_a_field_lets_go_of_it():
    """A column is a field or an additional column, never both."""
    draft, live, _couriers = _draft(additional=[_entry("Notes")])
    draft.apply("column", ["Notes", "Notes"])
    assert _additional(draft)["chips"] == []
    assert "Notes" not in _names(_additional(draft)["candidates"])
    draft.collect()
    assert live["additional_columns"][0]["enabled"] is False
    assert live["orders"]["Notes"] == "Notes"


# --- unsaved -----------------------------------------------------------------


def test_each_kind_of_edit_reads_unsaved():
    for action, args in [
        ("column", ["Notes", "Notes"]),
        ("courier_remove", ["0"]),
        ("column_add", ["Notes"]),
    ]:
        draft, _live, _couriers = _draft()
        draft.mark_clean()
        draft.apply(action, args)
        assert draft.is_dirty() is True, action


def test_an_empty_new_row_is_not_an_unsaved_change():
    """Only what would be written counts: a row with one side is not saved."""
    draft, _live, _couriers = _draft()
    draft.mark_clean()
    draft.apply("courier_add", [])
    assert draft.is_dirty() is False


def test_an_edit_on_orders_leaves_stock_clean():
    draft, live, _couriers = _draft()
    stock = StockDraft(live, "ACME")
    draft.mark_clean()
    stock.mark_clean()
    draft.apply("column_add", ["Notes"])
    draft.collect()
    assert draft.is_dirty() is True
    assert stock.is_dirty() is False
```

- [ ] **Step 2: Run it and see it fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_settings_draft_orders.py`

Expected: an error at collection, `ImportError: cannot import name 'ADDITIONAL_COLUMNS_UNREADABLE'`.

- [ ] **Step 3: Write the draft**

In `gui/settings/page_state.py`, find exactly:

```python
from gui.settings.contract import PageContract
```

Replace with:

```python
import pandas as pd

from gui.settings.contract import PageContract
from shopify_tool.csv_utils import discover_additional_columns
```

In `gui/settings/page_state.py`, append at the end of the file:

```python


# --- orders: courier names and additional columns ----------------------------

ADDITIONAL_COLUMNS_UNREADABLE = object()
"""Passed as `fallback_additional_columns` when the client config could not be
read, so the draft can tell "there are none" from "we don't know" (ADR 0006).
Saving the first over the second would discard the profile's real list."""

COURIER_TEXT = (
    "A shipping method that contains the text on the left is filed under the "
    "courier on the right. Anything else keeps its own name."
)
COURIER_EMPTY = "No courier names yet. The built-in ones apply: DHL, DPD and PostOne."
ADDITIONAL_TEXT = (
    "Orders columns with no field, carried through the analysis under their own names."
)
ADDITIONAL_EMPTY = "None kept."
ADDITIONAL_UNKNOWN = (
    "The saved list couldn't be read, so saving leaves it as it is. "
    "Add a column to replace it."
)
NOT_FILLED_DOWN = "not filled down"


def _is_entry(value) -> bool:
    return isinstance(value, dict) and bool(value.get("csv_name"))


def _additional_entry(value: dict) -> dict:
    """A stored entry with every key discover_additional_columns reads."""
    name = str(value["csv_name"])
    return {
        "csv_name": name,
        "internal_name": value.get("internal_name")
        or name.strip().replace(" ", "_").replace("-", "_"),
        "enabled": bool(value.get("enabled", False)),
        "is_order_level": bool(value.get("is_order_level", True)),
        "exists_in_df": value.get("exists_in_df", True),
    }


def _courier_rows(courier_mappings) -> list[list[str]]:
    """One [text, code] row per stored pattern, in stored order.

    A legacy entry is {pattern: code}: the analysis still matches it, so it
    loads as a row instead of being dropped on the next save.
    """
    rows: list[list[str]] = []
    if not isinstance(courier_mappings, dict):
        return rows
    for code, data in courier_mappings.items():
        if isinstance(data, dict):
            rows.extend([str(text), str(code)] for text in data.get("patterns") or [])
        elif isinstance(data, str):
            rows.append([str(code), data])
    return rows


class OrdersDraft(MappingDraft):
    """Orders CSV columns, the courier names that resolve the shipping method
    those columns carry, and the additional columns kept beside them."""

    def __init__(
        self,
        column_mappings: dict,
        courier_mappings: dict,
        client: str,
        fallback_additional_columns=None,
        file: FileColumns | None = None,
    ):
        super().__init__("orders", column_mappings, client, file)
        self.courier_mappings = courier_mappings
        self.courier_rows = _courier_rows(courier_mappings)

        # ADR 0006: the list lives in column_mappings; a profile not saved
        # since Bundle 13 still has it only in the client config.
        source = (
            column_mappings.get("additional_columns")
            if "additional_columns" in column_mappings
            else fallback_additional_columns
        )
        # A client config that could not be read means the stored list is
        # unknown, not empty: collect() must leave it alone, not save [] over it.
        self.additional_known = source is not ADDITIONAL_COLUMNS_UNREADABLE
        if not self.additional_known:
            source = []
        self.entries = [_additional_entry(e) for e in (source or []) if _is_entry(e)]

    # --- edits ---------------------------------------------------------------

    def _row(self, text: str) -> int | None:
        if text.isdecimal() and int(text) < len(self.courier_rows):
            return int(text)
        return None

    def _entry(self, name: str) -> dict | None:
        return next((e for e in self.entries if e["csv_name"] == name), None)

    def apply(self, action: str, args) -> bool:
        if action == "column":
            return super().apply(action, args)
        if action == "courier_add" and _shaped(args):
            self.courier_rows.append(["", ""])
            return True
        if action in ("courier_pattern", "courier_code") and _shaped(args, str, str):
            row = self._row(args[0])
            side = 0 if action == "courier_pattern" else 1
            value = args[1] if side == 0 else args[1].strip()
            if row is None or (side == 1 and not value):
                return False
            if self.courier_rows[row][side] == value:
                return False
            self.courier_rows[row][side] = value
            return True
        if action == "courier_remove" and _shaped(args, str):
            row = self._row(args[0])
            if row is None:
                return False
            del self.courier_rows[row]
            return True
        if action == "column_add" and _shaped(args, str):
            return self._keep(args[0])
        if action == "column_remove" and _shaped(args, str):
            entry = self._entry(args[0])
            if entry is None or not entry["enabled"]:
                return False
            entry["enabled"] = False
            return True
        if action == "column_fill" and _shaped(args, str, bool):
            entry = self._entry(args[0])
            if entry is None or entry["is_order_level"] == args[1]:
                return False
            entry["is_order_level"] = args[1]
            return True
        return False

    def _keep(self, name: str) -> bool:
        """Keep a candidate: turn its entry on, or store a discovered one."""
        candidate = next(
            (e for e in self._discovered() if e["csv_name"] == name and not e["enabled"]),
            None,
        )
        if candidate is None:
            return False
        entry = self._entry(name)
        if entry is None:
            self.entries.append({**candidate, "enabled": True})
        else:
            entry["enabled"] = True
        # What the operator keeps supersedes a list that could not be read.
        self.additional_known = True
        return True

    def _column_taken(self, column: str) -> None:
        entry = self._entry(column)
        if entry is not None:
            entry["enabled"] = False

    # --- what is saved -------------------------------------------------------

    def couriers(self) -> dict:
        """courier_mappings as stored: codes in the order their first row
        appears. A row missing its text or its courier is left out."""
        result: dict[str, dict] = {}
        for text, code in self.courier_rows:
            text, code = text.strip(), code.strip()
            if not text or not code:
                continue
            patterns = result.setdefault(
                code, {"patterns": [], "case_sensitive": False}
            )["patterns"]
            if text not in patterns:
                patterns.append(text)
        return result

    def collect(self) -> dict:
        # Same live-dict contract as column_mappings: clear and refill in
        # place, so a removed courier does not survive the save.
        couriers = self.couriers()
        self.courier_mappings.clear()
        self.courier_mappings.update(couriers)

        mappings = self._write_mapping()
        if self.additional_known:
            mappings["additional_columns"] = [dict(e) for e in self.entries]
        return {"column_mappings": mappings, "courier_mappings": self.courier_mappings}

    def snapshot(self) -> str:
        return json.dumps(
            [super().snapshot(), self.couriers(), self.entries],
            sort_keys=True,
            default=str,
        )

    # --- what the page draws -------------------------------------------------

    def _discovered(self) -> list[dict]:
        """Every additional column there is to show.

        With a file read: its unmapped columns and the stored entries, each
        saying whether the file has it. With none: the stored entries. Nothing
        here is stored until the operator keeps it.
        """
        if self.file is None:
            return [dict(e) for e in self.entries]
        return discover_additional_columns(
            pd.DataFrame(columns=list(self.file.columns)),
            {"orders": self.mappings()},
            self.entries,
        )

    def _additional_view(self) -> dict:
        read = self.file is not None
        chips, candidates = [], []
        for entry in self._discovered():
            lacking = read and not entry["exists_in_df"]
            if entry["enabled"]:
                notes = [NOT_IN_FILE] if lacking else []
                if not entry["is_order_level"]:
                    notes.append(NOT_FILLED_DOWN)
                chips.append(
                    {
                        "name": entry["csv_name"],
                        "note": ", ".join(notes),
                        "fill": bool(entry["is_order_level"]),
                    }
                )
            else:
                candidates.append(
                    {"name": entry["csv_name"], "note": NOT_IN_FILE if lacking else ""}
                )
        if candidates:
            add_title = ""
        elif read:
            add_title = "Every column in this file is mapped or kept."
        else:
            add_title = f"Use {READ_ACTION} to list the file's unmapped columns."
        return {
            "text": ADDITIONAL_TEXT,
            "chips": chips,
            "candidates": candidates,
            "group": (
                f"Unmapped columns in {self.file.name}" if read else "Turned off earlier"
            ),
            "empty": ADDITIONAL_EMPTY,
            "notice": "" if self.additional_known else ADDITIONAL_UNKNOWN,
            "add_title": add_title,
        }

    def _couriers_view(self) -> dict:
        codes: list[str] = []
        for _text, code in self.courier_rows:
            if code and code not in codes:
                codes.append(code)
        return {
            "text": COURIER_TEXT,
            "rows": [{"text": text, "code": code} for text, code in self.courier_rows],
            "codes": codes,
            "empty": COURIER_EMPTY,
        }

    def _mapping_view(self) -> dict:
        view = super()._mapping_view()
        view["couriers"] = self._couriers_view()
        view["additional"] = self._additional_view()
        return view
```


- [ ] **Step 4: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_settings_draft_orders.py tests/test_settings_draft_mapping.py tests/test_settings_draft_general.py`

Expected: all pass (119 in the scratch copy).

- [ ] **Step 5: Lint and commit**

Run: `.venv/bin/ruff check .` Expected: `All checks passed!`

Stage `gui/settings/page_state.py tests/test_settings_draft_orders.py` and commit. Message subject:
`Settings: OrdersDraft, courier names and additional columns with no widget`.

---

### Task 7: The page anatomy in the kit

The components phases 8 and 9 reuse (spec §5.6): a split page head, a card head, a label/control row, a
hint, a problem line, a chip, and the invalid edge.

**Files:**
- Modify: `gui/web/kit.css`, `tests/web/kit_sheet.html`
- Test: `tests/test_web_kit.py`

**Interfaces:**
- Produces the classes `.page-head.split`, `.page-head-text`, `.page-sub`, `.card-head`, `.card-head-text`,
  `.card-title`, `.card-text`, `.card-row`, `.card-label`, `.card-control`, `.hint`, `.problem`, `.chip`,
  `.chip-remove`, `.select.invalid`, `.field.invalid`.

- [ ] **Step 1: Draw the components on the sheet and add the failing tests**

In `tests/web/kit_sheet.html`, find exactly:

```html
</main>
<script>document.getElementById("c-mixed").indeterminate = true;</script>
```

Replace with:

```html
  <div class="page-head split" style="grid-column: 1 / -1">
    <div class="page-head-text">
      <span class="page-title">Orders mapping</span>
      <span id="p-sub" class="page-sub">Which column of ACME's orders CSV holds each field.</span>
    </div>
    <button class="btn secondary" type="button">Read columns from CSV…</button>
  </div>
  <section class="card" style="grid-column: 1 / -1; gap: 0; padding: 0">
    <div id="k-head" class="card-head">
      <div class="card-head-text">
        <span id="k-title" class="card-title">Stock alerts</span>
        <span id="k-text" class="card-text">When a SKU is flagged as low stock in Results.</span>
      </div>
      <button class="btn secondary" type="button">Add name</button>
    </div>
    <div id="k-row" class="card-row">
      <span id="k-label" class="card-label">Low-stock threshold</span>
      <div class="card-control">
        <div class="row">
          <input id="k-field-invalid" class="field invalid" type="text" value="1x" style="width: 72px">
          <button id="k-select-invalid" class="select invalid" type="button" aria-haspopup="menu" aria-expanded="false" style="width: 240px"><span class="select-value placeholder">Choose column</span><svg class="glyph" viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg></button>
        </div>
        <span id="k-hint" class="hint">A SKU is low when fewer than this are left.</span>
        <span id="k-problem" class="problem"><svg class="glyph" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20M12 8v4M12 16h.01"/></svg><span>Type a whole number, 0 or more.</span></span>
      </div>
    </div>
    <div class="card-row">
      <span class="card-label">Additional columns</span>
      <div class="card-control">
        <div class="row">
          <span id="k-chip" class="chip mono">Notes<button id="k-chip-remove" class="chip-remove" type="button" aria-label="Remove"><svg class="glyph" viewBox="0 0 24 24" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg></button></span>
        </div>
      </div>
    </div>
  </section>
</main>
<script>document.getElementById("c-mixed").indeterminate = true;</script>
```

In `tests/test_web_kit.py`, append at the end of the file:

```python


# --- the settings page anatomy (phase 7 spec section 5.6) --------------------


@THEMES
def test_a_split_page_head_stacks_a_secondary_sentence_under_the_title(qtbot, theme):
    view = _sheet(qtbot, theme)
    assert _style(qtbot, view, "#p-sub", "color") == _rgb(theme.text_secondary)
    assert _style(qtbot, view, ".page-head-text", "flexDirection") == "column"
    assert _style(qtbot, view, ".page-head.split", "alignItems") == "flex-start"


@THEMES
def test_a_card_head_has_a_bold_title_and_a_secondary_sentence(qtbot, theme):
    view = _sheet(qtbot, theme)
    assert _style(qtbot, view, "#k-title", "fontWeight") == "700"
    assert _style(qtbot, view, "#k-text", "color") == _rgb(theme.text_secondary)
    assert _style(qtbot, view, "#k-head", "paddingTop") == "14px"
    assert _style(qtbot, view, "#k-head", "paddingLeft") == "16px"


@THEMES
def test_a_card_row_is_a_label_column_and_a_control_under_a_hairline(qtbot, theme):
    view = _sheet(qtbot, theme)
    assert _style(qtbot, view, "#k-row", "borderTopColor") == _rgb(theme.border_subtle)
    assert _style(qtbot, view, "#k-row", "borderTopWidth") == "1px"
    assert _style(qtbot, view, "#k-row", "gridTemplateColumns").startswith("180px ")
    assert _style(qtbot, view, "#k-label", "width") == "180px"


@THEMES
def test_a_hint_is_secondary_and_a_problem_is_the_danger_colour(qtbot, theme):
    view = _sheet(qtbot, theme)
    assert _style(qtbot, view, "#k-hint", "color") == _rgb(theme.text_secondary)
    assert _style(qtbot, view, "#k-problem", "color") == _rgb(theme.status_danger)


@THEMES
def test_a_chip_is_a_raised_value_with_a_control_edge(qtbot, theme):
    view = _sheet(qtbot, theme)
    assert _style(qtbot, view, "#k-chip", "backgroundColor") == _rgb(theme.surface_raised)
    assert _style(qtbot, view, "#k-chip", "borderTopColor") == _rgb(theme.border)
    assert _style(qtbot, view, "#k-chip", "height") == "26px"
    assert _style(qtbot, view, "#k-chip-remove", "width") == "20px"


@THEMES
def test_an_invalid_field_and_select_take_the_danger_edge(qtbot, theme):
    view = _sheet(qtbot, theme)
    for selector in ("#k-field-invalid", "#k-select-invalid"):
        assert _style(qtbot, view, selector, "borderTopColor") == _rgb(
            theme.status_danger
        )
```


- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_web_kit.py`

Expected: the twelve new tests fail (six tests, two themes): the classes have no rules yet. The older kit
tests still pass.

- [ ] **Step 3: Add the components to the kit**

In `gui/web/kit.css`, find exactly:

```css
/* --- focus --------------------------------------------------------------- */

.btn:focus-visible,
```

Replace with:

```css
/* --- settings page anatomy (phase 7) ------------------------------------- */

/* A head with its title and sentence stacked, and an action on the right. */
.page-head.split { align-items: flex-start; gap: 16px; min-height: 44px; }
.page-head-text { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.page-sub { color: var(--text-secondary); }

/* A card's title and its sentence, with room for an action on the right. */
.card-head { display: flex; align-items: flex-start; gap: 12px; padding: 14px 16px 12px; }
.card-head-text { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.card-title { font-size: var(--type-label-size); font-weight: 700; }
.card-text { color: var(--text-secondary); }

/* A label column and a control column, under a rule: the card's head, or
   the row before, sits above it. */
.card-row {
  display: grid;
  grid-template-columns: 180px minmax(0, 1fr);
  gap: 16px;
  padding: 12px 16px;
  border-top: 1px solid var(--border-subtle);
}
.card-label { line-height: var(--control-height); }
.card-control { display: flex; flex-direction: column; gap: 6px; min-width: 0; }

/* Under a control: what it does, or what is wrong with it. */
.hint { font-size: var(--type-caption-size); color: var(--text-secondary); }
.problem { display: flex; align-items: flex-start; gap: 6px; color: var(--status-danger); }
.problem > .glyph { margin-top: 2px; stroke-width: 2; }

/* A kept value that can be let go. */
.chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 26px;
  padding: 0 4px 0 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface-raised);
}
.chip-remove {
  display: grid;
  place-items: center;
  width: 20px;
  height: 20px;
  padding: 0;
  border: 0;
  border-radius: var(--radius);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
}
.chip-remove:hover { background: var(--hover); }
.chip-remove:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 1px; }

.select.invalid,
.field.invalid { border-color: var(--status-danger); }

/* --- focus --------------------------------------------------------------- */

.btn:focus-visible,
```


- [ ] **Step 4: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_web_kit.py tests/test_style_literals_guard.py`

Expected: all pass (51 in the scratch copy).

- [ ] **Step 5: Lint and commit**

Run: `.venv/bin/ruff check .` Expected: `All checks passed!`

Stage `gui/web/kit.css tests/web/kit_sheet.html tests/test_web_kit.py` and commit. Message subject:
`Web kit: the settings page anatomy`.

---

### Task 8: The bridge and the page

`SettingsBridge` (spec §3.3) and the page that draws all three drafts (spec §5).

**Files:**
- Create: `gui/settings/bridge.py`, `gui/web/settings.html`, `gui/web/settings.css`, `gui/web/settings.js`
- Test: `tests/test_settings_bridge.py` (new), `tests/test_settings_web_page.py` (new)

**Interfaces:**
- Consumes: the drafts' `view()` and `apply()` (Tasks 4 to 6); the kit classes (Task 7);
  `gui.web_page.PageBridge`, `mount_page`, `WEB_DIR`, `THEME_MARKER` (already in the repo).
- Produces:
  - `gui.settings.bridge.SettingsBridge(PageBridge)`: `state` Property (`QVariantMap`), `set_state(dict)`,
    signals `stateChanged()`, `problemFocusRequested(str)`, `editRequested(str, list)`,
    `readColumnsRequested()`, slots `edit(action, args)` and `readColumns()`.
  - `gui.settings.bridge.mount_settings_page(view) -> SettingsBridge`, `PAGE`, `CHANNEL_NAME = "settings"`.
  - The page's `data-key`s: `read-columns`, `segment-{kind}-{mode}`, `char-{kind}`, `threshold`,
    `field-{internal}`, `field-{internal}-item-{n}` and `-item-none`, `courier-add`, `courier-text-{n}`,
    `courier-code-{n}`, `courier-code-{n}-item-{i}`, `courier-new-{n}`, `courier-remove-{n}`, `column-add`,
    `column-add-item-{n}`, `chip:{name}`, `chip-fill:{name}`, `chip-remove:{name}`.
  - `document.documentElement.dataset.bridge === "ready"` once the channel is up, and `dataset.renders`, a
    count the tests wait on.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_settings_bridge.py`:

```python
"""The settings pages' bridge (phase 7 spec section 3.3)."""

import pytest
from PySide6.QtWidgets import QApplication

from gui.settings.bridge import SettingsBridge
from gui.web_page import PageBridge


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


def _caught(signal):
    seen = []
    signal.connect(lambda *args: seen.append(args))
    return seen


def test_it_is_a_page_bridge():
    assert issubclass(SettingsBridge, PageBridge)


def test_the_state_notifies_only_when_it_changes():
    bridge = SettingsBridge()
    seen = _caught(bridge.stateChanged)
    bridge.set_state({"page": "general"})
    bridge.set_state({"page": "general"})
    bridge.set_state({"page": "orders"})
    assert len(seen) == 2
    assert bridge.state == {"page": "orders"}


def test_an_edit_carries_its_action_and_its_arguments():
    bridge = SettingsBridge()
    seen = _caught(bridge.editRequested)
    bridge.edit("delimiter", ["stock", "comma"])
    bridge.edit("courier_add", [])
    bridge.edit("column_fill", ["Notes", False])
    assert seen == [
        ("delimiter", ["stock", "comma"]),
        ("courier_add", []),
        ("column_fill", ["Notes", False]),
    ]


@pytest.mark.parametrize("args", ["stock", None, 3, {"kind": "stock"}])
def test_an_edit_whose_arguments_are_not_a_list_is_dropped(args):
    bridge = SettingsBridge()
    seen = _caught(bridge.editRequested)
    bridge.edit("delimiter", args)
    assert seen == []


def test_read_columns_emits_its_signal():
    bridge = SettingsBridge()
    seen = _caught(bridge.readColumnsRequested)
    bridge.readColumns()
    assert seen == [()]
```

Create `tests/test_settings_web_page.py`:

```python
"""The settings pages, driven through a real Chromium (phase 7 spec section 5).

The page is a renderer: every test pushes a view built by a draft and reads
the DOM back, or clicks and reads what the bridge was sent. 868x560 is the
page area a 1100x600 dialog gives. Never mark skip.
"""

import copy
import json

import pytest
from PySide6.QtWebEngineWidgets import QWebEngineView
from test_results_bridge import _eval, _rgb, _until_js

from gui.settings.bridge import PAGE, mount_settings_page
from gui.settings.page_state import (
    ADDITIONAL_COLUMNS_UNREADABLE,
    ADDITIONAL_UNKNOWN,
    COURIER_EMPTY,
    DELIMITER_PROBLEM,
    THRESHOLD_PROBLEM,
    FileColumns,
    GeneralDraft,
    OrdersDraft,
    StockDraft,
)
from gui.theme_manager import get_theme_manager
from gui.web_page import THEME_MARKER

ORDERS = {
    "Name": "Order_Number",
    "Lineitem sku": "SKU",
    "Lineitem quantity": "Quantity",
    "Shipping Method": "Shipping_Method",
    "Lineitem name": "Product_Name",
}
COURIERS = {
    "DHL": {"patterns": ["dhl", "DHL Express"], "case_sensitive": False},
    "DPD": {"patterns": ["dpd"], "case_sensitive": False},
}
FILE = FileColumns(
    name="orders-30-09.csv",
    columns=(
        "Name",
        "Lineitem sku",
        "Lineitem quantity",
        "Shipping Method",
        "Lineitem name",
        "Notes",
        "Discount Code",
    ),
    first_row={
        "Name": "#10482",
        "Lineitem sku": "ACM-TEE-BLK-M",
        "Lineitem quantity": "2",
        "Shipping Method": "DHL Express Worldwide",
        "Lineitem name": "Tee, black, M",
        "Notes": "leave at door",
    },
    loaded=True,
)


def _entry(name, enabled=True, order_level=True):
    return {
        "csv_name": name,
        "internal_name": name.replace(" ", "_"),
        "enabled": enabled,
        "is_order_level": order_level,
        "exists_in_df": True,
    }


def general(**stored):
    settings = {
        "stock_csv_delimiter": "auto",
        "orders_csv_delimiter": "auto",
        "low_stock_threshold": 5,
    }
    settings.update(stored)
    return GeneralDraft(settings, "ACME")


def orders(mapping=None, couriers=None, additional=None, file=FILE, fallback=None):
    live = {
        "version": 2,
        "orders": dict(ORDERS if mapping is None else mapping),
        "stock": {"Article": "SKU", "Available": "Stock"},
        "additional_columns": copy.deepcopy(additional or []),
    }
    if fallback is not None:
        del live["additional_columns"]
    return OrdersDraft(
        live, copy.deepcopy(COURIERS if couriers is None else couriers), "ACME", fallback, file
    )


def stock(file=None):
    live = {"version": 2, "orders": dict(ORDERS), "stock": {"Article": "SKU", "Available": "Stock"}}
    return StockDraft(live, "ACME", file)


@pytest.fixture
def page(qtbot):
    view = QWebEngineView()
    qtbot.addWidget(view)
    bridge = mount_settings_page(view)
    view.resize(868, 560)
    view.show()
    _until_js(qtbot, view, "document.documentElement.dataset.bridge === 'ready'")
    return view, bridge


def _renders(qtbot, view):
    return _eval(qtbot, view, "Number(document.documentElement.dataset.renders || 0)")


def _show(qtbot, view, bridge, draft):
    """Push a draft's view and wait for the page to have drawn it."""
    before = _renders(qtbot, view)
    bridge.set_state(draft.view())
    _until_js(
        qtbot, view, f"Number(document.documentElement.dataset.renders) > {before}"
    )


def _wired(qtbot, view, bridge, draft):
    """Show `draft` and answer the page's edits the way the host does."""
    seen = []

    def on_edit(action, args):
        seen.append((action, args))
        if draft.apply(action, args):
            bridge.set_state(draft.view())

    bridge.editRequested.connect(on_edit)
    _show(qtbot, view, bridge, draft)
    return seen


def _text(qtbot, view, selector):
    return _eval(
        qtbot, view, f"document.querySelector({selector!r}).textContent.trim()"
    )


def _texts(qtbot, view, selector):
    return json.loads(
        _eval(
            qtbot,
            view,
            "JSON.stringify(Array.from(document.querySelectorAll("
            f"{selector!r})).map((el) => el.textContent.trim()))",
        )
    )


def _count(qtbot, view, selector):
    return _eval(qtbot, view, f"document.querySelectorAll({selector!r}).length")


def _click(qtbot, view, selector):
    _eval(qtbot, view, f"document.querySelector({selector!r}).click(); true")


def _style(qtbot, view, selector, prop):
    return _eval(
        qtbot, view, f"getComputedStyle(document.querySelector({selector!r})).{prop}"
    )


def _attr(qtbot, view, selector, name):
    return _eval(
        qtbot, view, f"document.querySelector({selector!r}).getAttribute({name!r})"
    )


def _prop(qtbot, view, selector, name):
    return _eval(qtbot, view, f"document.querySelector({selector!r}).{name}")


def _type(qtbot, view, selector, text):
    """Type into a field as keystrokes do: focus it, set the text, fire input."""
    _eval(
        qtbot,
        view,
        "(function () {"
        f" const el = document.querySelector({selector!r});"
        " el.focus();"
        f" el.value = {json.dumps(text)};"
        " el.dispatchEvent(new Event('input', { bubbles: true }));"
        " return true; })()",
    )


def _keydown(qtbot, view, key, selector=None):
    target = f"document.querySelector({selector!r})" if selector else "document"
    _eval(
        qtbot,
        view,
        f"{target}.dispatchEvent(new KeyboardEvent('keydown', "
        f"{{key: {key!r}, bubbles: true, cancelable: true}})); true",
    )


def _active(qtbot, view):
    return _eval(qtbot, view, "document.activeElement.dataset.key || ''")


def _key(name):
    return f'[data-key="{name}"]'


# --- the files ---------------------------------------------------------------


def test_the_page_carries_the_theme_marker_exactly_once():
    assert PAGE.read_text(encoding="utf-8").count(THEME_MARKER) == 1


def test_the_page_links_the_kit_before_its_own_stylesheet():
    html = PAGE.read_text(encoding="utf-8")
    assert html.index('href="kit.css"') < html.index('href="settings.css"')


# --- frame -------------------------------------------------------------------


def test_the_head_has_the_title_and_the_subtitle_and_no_action_on_general(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, general())
    assert _text(qtbot, view, ".page-title") == "General"
    assert _text(qtbot, view, ".page-sub") == (
        "How ACME's files are read, and when stock counts as low."
    )
    assert _count(qtbot, view, _key("read-columns")) == 0


def test_the_page_is_a_centred_column_on_the_sunken_plane(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, general())
    theme = get_theme_manager().get_current_theme()
    assert _style(qtbot, view, "body", "backgroundColor") == _rgb(theme.surface_sunken)
    assert _style(qtbot, view, ".settings-page", "maxWidth") == "860px"
    assert _style(qtbot, view, ".settings-page .card", "backgroundColor") == _rgb(
        theme.surface
    )


def test_a_mapping_page_offers_read_columns(qtbot, page):
    view, bridge = page
    seen = []
    bridge.readColumnsRequested.connect(lambda: seen.append(True))
    _show(qtbot, view, bridge, orders())
    assert _text(qtbot, view, _key("read-columns")) == "Read columns from CSV…"
    _click(qtbot, view, _key("read-columns"))
    qtbot.waitUntil(lambda: seen == [True])


# --- General -----------------------------------------------------------------


def test_general_draws_two_cards_with_their_rows(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, general())
    assert _texts(qtbot, view, ".card-title") == ["CSV files", "Stock alerts"]
    assert _texts(qtbot, view, ".card-label") == [
        "Stock CSV delimiter",
        "Orders CSV delimiter",
        "Low-stock threshold",
    ]
    assert _texts(qtbot, view, '[data-row="delimiter-stock"] .segment') == [
        "Auto",
        "Comma",
        "Semicolon",
        "Tab",
        "Other",
    ]
    assert _text(qtbot, view, '[data-row="delimiter-stock"] .hint') == (
        "Detected for each file as it is read."
    )
    assert _prop(qtbot, view, _key("threshold"), "value") == "5"
    assert _text(qtbot, view, '[data-row="threshold"] .control-line span') == "units"


def test_the_stored_delimiter_is_the_checked_segment(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, general(orders_csv_delimiter=";"))
    assert _attr(qtbot, view, _key("segment-orders-semicolon"), "aria-checked") == "true"
    assert _attr(qtbot, view, _key("segment-orders-auto"), "aria-checked") == "false"
    assert _attr(qtbot, view, _key("segment-stock-auto"), "aria-checked") == "true"


def test_clicking_a_segment_reports_the_delimiter(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, general())
    _click(qtbot, view, _key("segment-orders-semicolon"))
    qtbot.waitUntil(lambda: seen == [("delimiter", ["orders", "semicolon"])])
    _until_js(
        qtbot,
        view,
        "document.querySelector('[data-key=\"segment-orders-semicolon\"]')"
        ".getAttribute('aria-checked') === 'true'",
    )
    assert _text(qtbot, view, '[data-row="delimiter-orders"] .hint') == (
        "Every file is split on semicolons."
    )


def test_other_shows_a_one_character_field_and_says_when_it_is_empty(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, general())
    assert _count(qtbot, view, _key("char-stock")) == 0
    _click(qtbot, view, _key("segment-stock-other"))
    _until_js(qtbot, view, "!!document.querySelector('[data-key=\"char-stock\"]')")
    assert _attr(qtbot, view, _key("char-stock"), "maxlength") == "1"
    assert _text(qtbot, view, '[data-row="delimiter-stock"] .problem') == DELIMITER_PROBLEM
    assert "invalid" in _attr(qtbot, view, _key("char-stock"), "class")

    _type(qtbot, view, _key("char-stock"), "|")
    qtbot.waitUntil(lambda: seen[-1] == ("delimiter_char", ["stock", "|"]))
    _until_js(
        qtbot,
        view,
        "!document.querySelector('[data-row=\"delimiter-stock\"] .problem')",
    )
    assert _text(qtbot, view, '[data-row="delimiter-stock"] .hint') == (
        "Every file is split on “|”."
    )


def test_typing_a_threshold_reports_every_keystroke_and_keeps_the_caret(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, general())
    _type(qtbot, view, _key("threshold"), "12")
    qtbot.waitUntil(lambda: seen == [("threshold", ["12"])])
    assert _active(qtbot, view) == "threshold"
    assert _prop(qtbot, view, _key("threshold"), "value") == "12"


def test_a_bad_threshold_marks_the_field_and_says_why(qtbot, page):
    view, bridge = page
    _wired(qtbot, view, bridge, general())
    _type(qtbot, view, _key("threshold"), "1x")
    _until_js(qtbot, view, "!!document.querySelector('[data-row=\"threshold\"] .problem')")
    assert _text(qtbot, view, '[data-row="threshold"] .problem') == THRESHOLD_PROBLEM
    assert "invalid" in _attr(qtbot, view, _key("threshold"), "class")
    assert _count(qtbot, view, '[data-row="threshold"] .hint') == 0
    # The field being typed in keeps what the operator sees.
    assert _prop(qtbot, view, _key("threshold"), "value") == "1x"
    assert _active(qtbot, view) == "threshold"


def test_left_and_right_move_between_segments(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, general())
    _eval(qtbot, view, "document.querySelector('[data-key=\"segment-stock-auto\"]').focus(); true")
    _keydown(qtbot, view, "ArrowRight", _key("segment-stock-auto"))
    assert _active(qtbot, view) == "segment-stock-comma"
    _keydown(qtbot, view, "ArrowLeft", _key("segment-stock-comma"))
    _keydown(qtbot, view, "ArrowLeft", _key("segment-stock-auto"))
    assert _active(qtbot, view) == "segment-stock-other"


# --- the Fields card ---------------------------------------------------------


def test_the_fields_card_says_where_its_columns_came_from(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, orders())
    assert _text(qtbot, view, '[data-card="fields"] .card-text') == (
        "Columns read from orders-30-09.csv, the file loaded on Setup."
    )
    assert _text(qtbot, view, '[data-card="fields"] .card-text .mono') == "orders-30-09.csv"
    assert _texts(qtbot, view, ".field-heads span") == ["Field", "", "CSV column", "First row"]


def test_a_field_row_shows_its_label_its_column_and_the_first_rows_value(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, orders())
    assert _count(qtbot, view, ".field-row[data-field]") == 12
    assert _count(qtbot, view, ".field-required") == 4
    row = '[data-field="Order_Number"]'
    assert _text(qtbot, view, f"{row} .field-label") == "Order number"
    assert _text(qtbot, view, f"{row} .select-value") == "Name"
    assert "mono" in _attr(qtbot, view, f"{row} .select-value", "class")
    assert _text(qtbot, view, f"{row} .field-sample") == "#10482"
    assert _text(qtbot, view, '[data-field="Tags"] .select-value') == "Not imported"


def test_with_no_file_the_menus_are_disabled_and_the_card_says_so(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, orders(file=None))
    assert _text(qtbot, view, '[data-card="fields"] .card-text') == (
        "No CSV has been read. Use Read columns from CSV… to change a field."
    )
    assert _prop(qtbot, view, _key("field-Order_Number"), "disabled") is True
    _click(qtbot, view, _key("field-Order_Number"))
    assert _count(qtbot, view, ".menu") == 0


def test_a_field_menu_lists_the_files_columns_and_who_holds_them(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, orders())
    _click(qtbot, view, _key("field-Tags"))
    assert _texts(qtbot, view, ".field-menu .menu-label") == [
        "Not imported",
        *FILE.columns,
    ]
    assert _attr(qtbot, view, _key("field-Tags-item-none"), "aria-checked") == "true"
    assert _text(qtbot, view, f"{_key('field-Tags-item-0')} .menu-hint") == "Order number"
    assert _count(qtbot, view, f"{_key('field-Tags-item-5')} .menu-hint") == 0
    assert _attr(qtbot, view, _key("field-Tags"), "aria-expanded") == "true"


def test_a_required_fields_menu_has_no_not_imported_and_no_note_on_its_own_column(
    qtbot, page
):
    view, bridge = page
    _show(qtbot, view, bridge, orders())
    _click(qtbot, view, _key("field-SKU"))
    assert _texts(qtbot, view, ".field-menu .menu-label") == list(FILE.columns)
    assert _attr(qtbot, view, _key("field-SKU-item-1"), "aria-checked") == "true"
    assert _count(qtbot, view, f"{_key('field-SKU-item-1')} .menu-hint") == 0


def test_picking_a_column_reports_it_closes_the_menu_and_keeps_focus(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, orders())
    _click(qtbot, view, _key("field-Tags"))
    _click(qtbot, view, _key("field-Tags-item-5"))
    qtbot.waitUntil(lambda: seen == [("column", ["Tags", "Notes"])])
    _until_js(
        qtbot,
        view,
        "document.querySelector('[data-field=\"Tags\"] .select-value')"
        ".textContent === 'Notes'",
    )
    assert _count(qtbot, view, ".menu") == 0
    assert _active(qtbot, view) == "field-Tags"
    assert _text(qtbot, view, '[data-field="Tags"] .field-sample') == "leave at door"


def test_a_required_field_with_no_column_is_marked_and_says_what_to_do(qtbot, page):
    view, bridge = page
    mapping = {k: v for k, v in ORDERS.items() if v != "Shipping_Method"}
    _show(qtbot, view, bridge, orders(mapping=mapping))
    row = '[data-field="Shipping_Method"]'
    assert "invalid" in _attr(qtbot, view, f"{row} .select", "class")
    assert _text(qtbot, view, f"{row} .select-value") == "Choose column"
    theme = get_theme_manager().get_current_theme()
    assert _style(qtbot, view, f"{row} .select-value", "color") == _rgb(theme.status_danger)
    assert _text(qtbot, view, f"{row} .problem") == (
        "Shipping method is required. Choose the column that holds it, "
        "e.g. Shipping Method."
    )
    assert _text(qtbot, view, f"{row} .problem .mono") == "Shipping Method"


def test_a_saved_column_the_file_lacks_is_kept_and_listed_first(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, orders(mapping={**ORDERS, "Old Notes": "Notes"}))
    row = '[data-field="Notes"]'
    assert _text(qtbot, view, f"{row} .select-value") == "Old Notes"
    assert _text(qtbot, view, f"{row} .field-sample") == "Not in this file"
    _click(qtbot, view, _key("field-Notes"))
    assert _texts(qtbot, view, ".field-menu .menu-label")[:2] == ["Not imported", "Old Notes"]
    assert _text(qtbot, view, f"{_key('field-Notes-item-0')} .menu-hint") == "Not in this file"
    assert _attr(qtbot, view, _key("field-Notes-item-0"), "aria-checked") == "true"


def test_the_stock_page_has_only_the_fields_card_and_its_hints(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, stock())
    assert _texts(qtbot, view, ".card-title") == ["Fields"]
    assert _count(qtbot, view, ".field-row[data-field]") == 5
    assert _text(qtbot, view, '[data-field="Batch"] .hint').startswith("Lot or batch number.")


# --- menus -------------------------------------------------------------------


def test_escape_and_an_outside_click_close_the_menu(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, orders())
    _click(qtbot, view, _key("field-Tags"))
    assert _count(qtbot, view, ".menu") == 1
    _keydown(qtbot, view, "Escape")
    assert _count(qtbot, view, ".menu") == 0
    assert _active(qtbot, view) == "field-Tags"

    _click(qtbot, view, _key("field-Tags"))
    _click(qtbot, view, ".page-title")
    assert _count(qtbot, view, ".menu") == 0


def test_escape_with_no_menu_open_is_left_for_the_dialog(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, orders())
    prevented = _eval(
        qtbot,
        view,
        "(function () { const e = new KeyboardEvent('keydown', "
        "{key: 'Escape', bubbles: true, cancelable: true});"
        " document.dispatchEvent(e); return e.defaultPrevented; })()",
    )
    assert prevented is False


def test_only_one_menu_is_open_at_a_time(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, orders())
    _click(qtbot, view, _key("field-Tags"))
    _click(qtbot, view, _key("field-Notes"))
    assert _count(qtbot, view, ".menu") == 1
    assert _count(qtbot, view, '[data-field="Notes"] .menu') == 1


def test_arrow_keys_walk_the_open_menu(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, orders())
    _click(qtbot, view, _key("field-SKU"))
    _keydown(qtbot, view, "ArrowDown")
    assert _active(qtbot, view) == "field-SKU-item-0"
    _keydown(qtbot, view, "ArrowDown")
    assert _active(qtbot, view) == "field-SKU-item-1"
    _keydown(qtbot, view, "ArrowUp")
    _keydown(qtbot, view, "ArrowUp")
    assert _active(qtbot, view) == "field-SKU-item-6"


def test_changing_page_closes_the_menu_and_returns_to_the_top(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, orders())
    _click(qtbot, view, _key("field-Tags"))
    _eval(qtbot, view, "document.getElementById('settings').scrollTop = 200; true")
    _show(qtbot, view, bridge, general())
    assert _count(qtbot, view, ".menu") == 0
    assert _eval(qtbot, view, "document.getElementById('settings').scrollTop") == 0
    assert _attr(qtbot, view, ".settings-page", "data-page") == "general"


def test_a_menu_closes_when_the_state_takes_its_opener_away(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, orders())
    _click(qtbot, view, _key("field-Tags"))
    _show(qtbot, view, bridge, orders(file=None))
    assert _count(qtbot, view, ".menu") == 0


# --- Courier names -----------------------------------------------------------


def test_courier_rows_show_the_text_and_the_courier(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, orders())
    assert _text(qtbot, view, '[data-card="couriers"] .card-title') == "Courier names"
    assert _texts(qtbot, view, ".courier-heads span") == [
        "Shipping method contains",
        "",
        "Courier",
        "",
    ]
    assert _count(qtbot, view, ".courier-row[data-courier]") == 3
    assert _prop(qtbot, view, _key("courier-text-1"), "value") == "DHL Express"
    assert _text(qtbot, view, _key("courier-code-2")) == "DPD"


def test_no_courier_rows_shows_the_empty_sentence(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, orders(couriers={}))
    assert _text(qtbot, view, '[data-card="couriers"] .card-empty') == COURIER_EMPTY
    assert _count(qtbot, view, ".courier-heads") == 0


def test_typing_a_courier_text_reports_the_row(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, orders())
    _type(qtbot, view, _key("courier-text-2"), "dpd classic")
    qtbot.waitUntil(lambda: seen == [("courier_pattern", ["2", "dpd classic"])])
    assert _active(qtbot, view) == "courier-text-2"


def test_add_name_adds_a_row_and_puts_the_caret_in_it(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, orders())
    _click(qtbot, view, _key("courier-add"))
    qtbot.waitUntil(lambda: seen == [("courier_add", [])])
    _until_js(qtbot, view, "document.querySelectorAll('.courier-row[data-courier]').length === 4")
    _until_js(qtbot, view, "document.activeElement.dataset.key === 'courier-text-3'")
    assert _text(qtbot, view, _key("courier-code-3")) == "Choose courier"


def test_the_courier_menu_lists_the_couriers_in_use_and_takes_a_new_one(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, orders())
    _click(qtbot, view, _key("courier-code-2"))
    assert _texts(qtbot, view, ".courier-menu .menu-label") == ["DHL", "DPD"]
    assert _attr(qtbot, view, _key("courier-code-2-item-1"), "aria-checked") == "true"
    assert _attr(qtbot, view, _key("courier-new-2"), "placeholder") == "New courier"

    _click(qtbot, view, _key("courier-code-2-item-0"))
    qtbot.waitUntil(lambda: seen == [("courier_code", ["2", "DHL"])])
    _until_js(
        qtbot,
        view,
        "document.querySelector('[data-key=\"courier-code-2\"]').textContent.trim() === 'DHL'",
    )
    assert _count(qtbot, view, ".menu") == 0

    _click(qtbot, view, _key("courier-code-0"))
    _eval(
        qtbot,
        view,
        "document.querySelector('[data-key=\"courier-new-0\"]').value = 'Evri'; true",
    )
    _keydown(qtbot, view, "Enter", _key("courier-new-0"))
    qtbot.waitUntil(lambda: seen[-1] == ("courier_code", ["0", "Evri"]))
    _until_js(
        qtbot,
        view,
        "document.querySelector('[data-key=\"courier-code-0\"]').textContent.trim() === 'Evri'",
    )
    assert _count(qtbot, view, ".menu") == 0
    assert _active(qtbot, view) == "courier-code-0"


def test_removing_a_courier_row_reports_its_index(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, orders())
    _click(qtbot, view, _key("courier-remove-0"))
    qtbot.waitUntil(lambda: seen == [("courier_remove", ["0"])])
    _until_js(qtbot, view, "document.querySelectorAll('.courier-row[data-courier]').length === 2")
    assert _prop(qtbot, view, _key("courier-text-0"), "value") == "DHL Express"


# --- Additional columns ------------------------------------------------------


def test_kept_columns_are_chips_with_their_notes(qtbot, page):
    view, bridge = page
    additional = [_entry("Notes"), _entry("Gift Note", order_level=False)]
    _show(qtbot, view, bridge, orders(additional=additional))
    assert _texts(qtbot, view, ".chip-name") == ["Notes", "Gift Note"]
    assert _texts(qtbot, view, ".chip-note") == ["Not in this file, not filled down"]
    assert _count(qtbot, view, ".chips-empty") == 0


def test_no_kept_columns_says_none_kept(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, orders())
    assert _text(qtbot, view, ".chips-empty") == "None kept."


def test_add_column_lists_the_candidates_and_keeping_one_makes_a_chip(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, orders())
    _click(qtbot, view, _key("column-add"))
    assert _text(qtbot, view, ".add-menu .menu-group") == (
        "Unmapped columns in orders-30-09.csv"
    )
    assert _texts(qtbot, view, ".add-menu .menu-label") == ["Discount Code", "Notes"]
    _click(qtbot, view, _key("column-add-item-1"))
    qtbot.waitUntil(lambda: seen == [("column_add", ["Notes"])])
    _until_js(qtbot, view, "document.querySelectorAll('.chip-name').length === 1")
    assert _texts(qtbot, view, ".chip-name") == ["Notes"]
    assert _count(qtbot, view, ".menu") == 0


def test_add_column_is_disabled_and_says_why_when_there_is_nothing_to_add(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, orders(file=None))
    assert _prop(qtbot, view, _key("column-add"), "disabled") is True
    assert _attr(qtbot, view, _key("column-add"), "title") == (
        "Use Read columns from CSV… to list the file's unmapped columns."
    )


def test_removing_a_chip_reports_its_column(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, orders(additional=[_entry("Notes")]))
    _click(qtbot, view, ".chip-remove")
    qtbot.waitUntil(lambda: seen == [("column_remove", ["Notes"])])
    _until_js(qtbot, view, "document.querySelectorAll('.chip-name').length === 0")


def test_a_chips_menu_toggles_fill_down(qtbot, page):
    view, bridge = page
    seen = _wired(qtbot, view, bridge, orders(additional=[_entry("Notes")]))
    _click(qtbot, view, ".chip-name")
    item = '[data-chip="Notes"] .menu-item'
    assert _text(qtbot, view, item) == "Fill down onto every line of the order"
    assert _attr(qtbot, view, item, "aria-checked") == "true"
    _click(qtbot, view, item)
    qtbot.waitUntil(lambda: seen == [("column_fill", ["Notes", False])])
    _until_js(
        qtbot,
        view,
        "document.querySelector('[data-chip=\"Notes\"] .menu-item')"
        ".getAttribute('aria-checked') === 'false'",
    )
    assert _texts(qtbot, view, ".chip-note") == ["not filled down"]


def test_a_column_name_with_quotes_in_it_still_works(qtbot, page):
    """A key can hold a column's name, and a column's name can hold anything."""
    view, bridge = page
    name = 'Gift "note" <b>'
    seen = _wired(qtbot, view, bridge, orders(additional=[_entry(name)]))
    assert _texts(qtbot, view, ".chip-name") == [name]
    _click(qtbot, view, ".chip-name")
    assert _count(qtbot, view, ".chip-anchor .menu") == 1
    _keydown(qtbot, view, "Escape")
    assert _eval(qtbot, view, "document.activeElement.className") == "chip-name mono"
    _click(qtbot, view, ".chip-remove")
    qtbot.waitUntil(lambda: seen == [("column_remove", [name])])


def test_an_unreadable_list_shows_the_notice(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, orders(fallback=ADDITIONAL_COLUMNS_UNREADABLE))
    assert _text(qtbot, view, ".card-notice") == ADDITIONAL_UNKNOWN


# --- the footer's link -------------------------------------------------------


def test_a_problem_focus_request_focuses_that_control(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, general(low_stock_threshold="x"))
    bridge.problemFocusRequested.emit("threshold")
    _until_js(qtbot, view, "document.activeElement.dataset.key === 'threshold'")


# --- theme -------------------------------------------------------------------


def test_the_page_follows_a_theme_change_without_a_reload(qtbot, page):
    view, bridge = page
    _show(qtbot, view, bridge, general())
    manager = get_theme_manager()
    start = manager.get_current_theme().name
    other = "dark" if start == "light" else "light"
    try:
        manager.set_theme(other)
        surface = _rgb(manager.get_current_theme().surface)
        _until_js(
            qtbot,
            view,
            "getComputedStyle(document.querySelector('.card')).backgroundColor"
            f" === {surface!r}",
        )
        assert _text(qtbot, view, ".page-title") == "General"
    finally:
        manager.set_theme(start)
```

- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_settings_bridge.py tests/test_settings_web_page.py`

Expected: errors at collection, `ModuleNotFoundError: No module named 'gui.settings.bridge'`.

- [ ] **Step 3: Write the bridge**

Create `gui/settings/bridge.py`:

```python
"""The settings pages' bridge (phase 7 spec section 3.3).

Python pushes one `state` map, built by a draft's view() (gui/settings/
page_state.py); the page draws it and reports each edit through edit(). The
catalogue is the spec's section 3.3: add a member there before adding it here.

Nothing the page sends is used as a path.
"""

from PySide6.QtCore import Property, Signal, Slot
from PySide6.QtWebEngineWidgets import QWebEngineView

from gui.web_page import WEB_DIR, PageBridge, mount_page

PAGE = WEB_DIR / "settings.html"
CHANNEL_NAME = "settings"


class SettingsBridge(PageBridge):
    """The settings pages' one channel object."""

    stateChanged = Signal()
    # JS-facing: focus the control with this data-key and scroll it into view.
    problemFocusRequested = Signal(str)
    # Python-facing. JS reports through the slots below and never connects to
    # these, so nothing it sends can echo back into the page.
    editRequested = Signal(str, list)
    readColumnsRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state: dict = {}

    # --- out: Python -> JS -------------------------------------------------

    def _get_state(self) -> dict:
        return self._state

    state = Property("QVariantMap", _get_state, notify=stateChanged)

    def set_state(self, state: dict) -> None:
        if state == self._state:
            return
        self._state = state
        self.stateChanged.emit()

    # --- in: JS -> Python --------------------------------------------------

    @Slot(str, "QVariant")
    def edit(self, action, args) -> None:
        # The draft checks the action and every argument; this only refuses
        # what is not a list at all.
        if isinstance(args, list):
            self.editRequested.emit(str(action), args)

    @Slot()
    def readColumns(self) -> None:
        self.readColumnsRequested.emit()


def mount_settings_page(view: QWebEngineView) -> SettingsBridge:
    """Load the settings page into `view` and return the bridge it talks to."""
    bridge = SettingsBridge(view)
    mount_page(view, bridge, PAGE, CHANNEL_NAME)
    return bridge
```

- [ ] **Step 4: Write the page**

Create `gui/web/settings.html`:

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Client settings</title>
<!-- gui/web_page.py writes theme_css_vars() over the marker before the page
     loads, then settings.js keeps it current from the bridge. -->
<style id="theme-vars">/* theme-vars */</style>
<link rel="stylesheet" href="kit.css">
<link rel="stylesheet" href="settings.css">
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<script src="settings.js" defer></script>
</head>
<body>
<main id="settings"></main>
</body>
</html>
```

Create `gui/web/settings.css`:

```css
/* The Client settings pages the web tier draws: General, Orders mapping and
   Stock mapping (phase 7 spec section 5). Layout only: every component is the
   kit's. Every colour is a token from theme_css_vars(). */

#settings {
  height: 100%;
  overflow: auto;
}

.settings-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 860px;
  margin: 0 auto;
  padding: 20px 24px 32px;
}
.settings-page > .card { display: flex; flex-direction: column; }

/* --- General ------------------------------------------------------------- */

.control-line {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: var(--control-height);
}
.other-char { width: 36px; padding: 0; font-weight: 700; text-align: center; }
.threshold { width: 72px; text-align: right; }

/* --- the Fields card ----------------------------------------------------- */

.field-row,
.courier-row {
  display: grid;
  column-gap: 12px;
  row-gap: 6px;
  align-items: center;
  padding: 8px 16px;
  border-top: 1px solid var(--border-subtle);
}
.field-row { grid-template-columns: 180px 16px 240px minmax(0, 1fr); }
.courier-row { grid-template-columns: 280px 16px 160px minmax(0, 1fr); }

.field-heads,
.courier-heads {
  padding: 6px 16px;
  font-size: var(--type-caption-size);
  font-weight: 700;
  color: var(--text-secondary);
}

.field-name { display: flex; align-items: center; gap: 6px; min-width: 0; }
.field-label { font-weight: 700; }
.field-required { font-size: var(--type-caption-size); color: var(--text-secondary); }
.arrow { color: var(--text-secondary); stroke-width: 1.5; }

.field-row .select { width: 240px; }
.field-row .select-value { font-weight: 400; }
.select-value.danger { color: var(--status-danger); }
.field-menu { width: 240px; min-width: 0; max-height: 240px; }
.field-menu .menu-label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.field-sample {
  min-width: 0;
  overflow: hidden;
  color: var(--text-secondary);
  white-space: nowrap;
  text-overflow: ellipsis;
}
.field-sample.missing { font-family: var(--font-family); }
.field-below { grid-column: 3 / 5; }

/* --- Courier names ------------------------------------------------------- */

.courier-row .field { width: 100%; }
.courier-row .select { width: 160px; }
.courier-row .btn.icon { justify-self: end; color: var(--text-secondary); }
.courier-menu { min-width: 160px; }
.new-courier { width: 100%; }

.card-empty {
  padding: 12px 16px 14px;
  border-top: 1px solid var(--border-subtle);
  color: var(--text-secondary);
}

/* --- Additional columns -------------------------------------------------- */

.card-notice { padding: 0 16px 12px; color: var(--text-secondary); }
.chips {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 12px 16px 14px;
  border-top: 1px solid var(--border-subtle);
}
.chips-empty { color: var(--text-secondary); }
.chip-anchor { display: inline-flex; }
.chip-name { padding: 0; border: 0; background: transparent; cursor: pointer; }
.chip-name:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 1px; }
.chip-note {
  padding-left: 4px;
  font-size: var(--type-caption-size);
  color: var(--text-secondary);
}
/* The button sits at the card's right edge: its menu opens leftwards. */
.add-menu { left: auto; right: 0; }
```

Create `gui/web/settings.js`:

```javascript
// The Client settings pages the web tier draws: General, Orders mapping and
// Stock mapping (phase 7 spec section 5). Python holds every value and words
// every sentence (gui/settings/page_state.py) and sends one page's view as
// bridge.state; this file renders it and reports each edit through
// bridge.edit(action, args). Nothing is validated or computed here. The page's
// own state is which menu is open.
"use strict";

// Lucide glyphs, each as one path.
const GLYPH = {
  chevron: "m6 9 6 6 6-6",
  check: "M20 6 9 17l-5-5",
  x: "M18 6 6 18M6 6l12 12",
  plus: "M5 12h14M12 5v14",
  alert: "M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0M12 8v4M12 16h.01",
  arrowLeft: "M19 12H5M12 19l-7-7 7-7",
  arrowRight: "M5 12h14M12 5l7 7-7 7",
};

const els = {};
const page = { bridge: null, state: null, renders: 0 };
// menu: "field-<internal name>", "courier-code-<row>", "column-add",
// "chip:<column>", or null. shown: the page the last render drew. pending: a
// data-key to focus once the state that creates it arrives.
const view = { menu: null, shown: null, pending: null };

function esc(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function svg(path, cls) {
  return `<svg class="${cls}" viewBox="0 0 24 24" aria-hidden="true"><path d="${path}"/></svg>`;
}

function off(disabled) {
  return disabled ? " disabled" : "";
}

function own(map, key) {
  return Object.prototype.hasOwnProperty.call(map, key);
}

// --- what every page shares --------------------------------------------------

function head(s) {
  const action = s.action
    ? `<button class="btn secondary" type="button" data-act="read" data-key="read-columns">${svg(GLYPH.plus, "glyph")}${esc(s.action)}</button>`
    : "";
  return `<div class="page-head split">
    <div class="page-head-text"><span class="page-title">${esc(s.title)}</span><span class="page-sub">${esc(s.subtitle)}</span></div>
    ${action}
  </div>`;
}

// `text` and `action` are markup: the caller escapes what it puts in them.
function cardHead(title, text, action) {
  return `<div class="card-head">
    <div class="card-head-text"><span class="card-title">${title}</span><span class="card-text">${text}</span></div>
    ${action || ""}
  </div>`;
}

function problemLine(text, extra, cls) {
  return `<span class="problem${cls ? ` ${cls}` : ""}" role="alert">${svg(GLYPH.alert, "glyph")}<span>${esc(text)}${extra || ""}</span></span>`;
}

// Under a control: the problem when there is one, else the hint.
function below(problem, hint) {
  if (problem) return problemLine(problem);
  return hint ? `<span class="hint">${esc(hint)}</span>` : "";
}

function menuItem(act, data, label, hint, checked, key, mono) {
  const attrs = Object.keys(data)
    .map((name) => ` data-${name}="${esc(data[name])}"`)
    .join("");
  const meta = hint ? `<span class="menu-hint">${esc(hint)}</span>` : "";
  return `<button class="menu-item" type="button" role="menuitemradio" aria-checked="${Boolean(checked)}" data-act="${act}"${attrs} data-key="${esc(key)}">${svg(GLYPH.check, "check")}<span class="menu-label${mono ? " mono" : ""}">${esc(label)}</span>${meta}</button>`;
}

// --- General -----------------------------------------------------------------

function delimiterRow(d) {
  const segments = d.options
    .map(
      (o) =>
        `<button class="segment" type="button" role="radio" aria-checked="${Boolean(o.checked)}" tabindex="${o.checked ? 0 : -1}" data-act="delimiter" data-kind="${d.kind}" data-value="${o.value}" data-key="segment-${d.kind}-${o.value}">${esc(o.label)}</button>`,
    )
    .join("");
  const other = d.other
    ? `<input class="field mono other-char${d.problem ? " invalid" : ""}" type="text" maxlength="1" value="${esc(d.char)}" aria-label="Delimiter character" data-input="delimiter_char" data-kind="${d.kind}" data-key="char-${d.kind}">`
    : "";
  return `<div class="card-row" data-row="delimiter-${d.kind}">
    <span class="card-label">${esc(d.label)}</span>
    <div class="card-control">
      <div class="control-line"><div class="segmented" role="radiogroup" aria-label="${esc(d.label)}">${segments}</div>${other}</div>
      ${below(d.problem, d.hint)}
    </div>
  </div>`;
}

function generalPage(g) {
  const t = g.threshold;
  return `<section class="card" data-card="csv">
    ${cardHead("CSV files", esc(g.csv_text))}
    ${g.delimiters.map(delimiterRow).join("")}
  </section>
  <section class="card" data-card="alerts">
    ${cardHead("Stock alerts", esc(g.alerts_text))}
    <div class="card-row" data-row="threshold">
      <span class="card-label">Low-stock threshold</span>
      <div class="card-control">
        <div class="control-line"><input class="field mono threshold${t.problem ? " invalid" : ""}" type="text" inputmode="numeric" value="${esc(t.value)}" aria-label="Low-stock threshold" data-input="threshold" data-key="threshold"><span>${esc(t.unit)}</span></div>
        ${below(t.problem, t.hint)}
      </div>
    </div>
  </section>`;
}

// --- the Fields card ---------------------------------------------------------

function fieldMenu(m, f) {
  const items = [];
  if (!f.required) {
    items.push(menuItem("column", { field: f.name, value: "" }, f.placeholder, "", !f.column, `field-${f.name}-item-none`, false));
  }
  // A saved column the file lacks is still the choice: it is listed first.
  const columns = f.sample_missing ? [f.column].concat(m.columns) : m.columns;
  columns.forEach((column, n) => {
    let note = "";
    if (f.sample_missing && n === 0) note = f.sample;
    else if (own(m.held, column) && m.held[column] !== f.label) note = m.held[column];
    items.push(menuItem("column", { field: f.name, value: column }, column, note, column === f.column, `field-${f.name}-item-${n}`, true));
  });
  return `<div class="menu field-menu" role="menu">${items.join("")}</div>`;
}

function fieldRow(m, f) {
  const menuName = `field-${f.name}`;
  const open = view.menu === menuName;
  const bad = Boolean(f.problem);
  const value = f.column
    ? `<span class="select-value mono">${esc(f.column)}</span>`
    : `<span class="select-value placeholder${bad ? " danger" : ""}">${esc(f.placeholder)}</span>`;
  const required = f.required ? `<span class="field-required">Required</span>` : "";
  let under = "";
  if (f.problem) {
    const example = f.example ? ` <span class="mono">${esc(f.example)}</span>.` : "";
    under = problemLine(f.problem, example, "field-below");
  } else if (f.hint) {
    under = `<span class="hint field-below">${esc(f.hint)}</span>`;
  }
  return `<div class="field-row" data-field="${esc(f.name)}">
    <div class="field-name"><span class="field-label">${esc(f.label)}</span>${required}</div>
    ${svg(GLYPH.arrowLeft, "glyph arrow")}
    <div class="menu-anchor">
      <button class="select${bad ? " invalid" : ""}" type="button" aria-haspopup="menu" aria-expanded="${open}" aria-label="${esc(f.label)} column" data-act="menu" data-menu="${menuName}" data-key="${menuName}"${off(!m.can_pick)}>${value}${svg(GLYPH.chevron, "glyph")}</button>
      ${open ? fieldMenu(m, f) : ""}
    </div>
    <span class="field-sample mono${f.sample_missing ? " missing" : ""}" title="${esc(f.sample)}">${esc(f.sample)}</span>
    ${under}
  </div>`;
}

function fieldsCard(m) {
  const src = m.source;
  const file = src.file ? ` <span class="mono">${esc(src.file)}</span>` : "";
  return `<section class="card" data-card="fields">
    ${cardHead("Fields", `${esc(src.lead)}${file}${esc(src.tail)}`)}
    <div class="field-row field-heads"><span>Field</span><span></span><span>CSV column</span><span>First row</span></div>
    ${m.fields.map((f) => fieldRow(m, f)).join("")}
  </section>`;
}

// --- Courier names -----------------------------------------------------------

function courierMenu(c, row, n) {
  const items = c.codes
    .map((code, i) => menuItem("courier-code", { index: n, value: code }, code, "", code === row.code, `courier-code-${n}-item-${i}`, false))
    .join("");
  const rule = c.codes.length ? `<div class="menu-separator"></div>` : "";
  return `<div class="menu courier-menu" role="menu">${items}${rule}<input class="field new-courier" type="text" placeholder="New courier" aria-label="New courier" data-new-courier="${n}" data-key="courier-new-${n}"></div>`;
}

function courierRow(c, row, n) {
  const menuName = `courier-code-${n}`;
  const open = view.menu === menuName;
  const value = row.code
    ? `<span class="select-value">${esc(row.code)}</span>`
    : `<span class="select-value placeholder">Choose courier</span>`;
  return `<div class="courier-row" data-courier="${n}">
    <input class="field mono" type="text" value="${esc(row.text)}" placeholder="dhl express" aria-label="Shipping method contains" data-input="courier_pattern" data-index="${n}" data-key="courier-text-${n}">
    ${svg(GLYPH.arrowRight, "glyph arrow")}
    <div class="menu-anchor">
      <button class="select" type="button" aria-haspopup="menu" aria-expanded="${open}" aria-label="Courier" data-act="menu" data-menu="${menuName}" data-key="${menuName}">${value}${svg(GLYPH.chevron, "glyph")}</button>
      ${open ? courierMenu(c, row, n) : ""}
    </div>
    <button class="btn ghost icon" type="button" title="Remove" aria-label="Remove" data-act="courier-remove" data-index="${n}" data-key="courier-remove-${n}">${svg(GLYPH.x, "glyph")}</button>
  </div>`;
}

function couriersCard(c) {
  const add = `<button class="btn secondary" type="button" data-act="courier-add" data-key="courier-add">Add name</button>`;
  const body = c.rows.length
    ? `<div class="courier-row courier-heads"><span>Shipping method contains</span><span></span><span>Courier</span><span></span></div>${c.rows.map((row, n) => courierRow(c, row, n)).join("")}`
    : `<div class="card-empty">${esc(c.empty)}</div>`;
  return `<section class="card" data-card="couriers">
    ${cardHead("Courier names", esc(c.text), add)}
    ${body}
  </section>`;
}

// --- Additional columns ------------------------------------------------------

function chip(item) {
  const menuName = `chip:${item.name}`;
  const open = view.menu === menuName;
  const note = item.note ? `<span class="chip-note">${esc(item.note)}</span>` : "";
  const menu = open
    ? `<div class="menu" role="menu"><button class="menu-item" type="button" role="menuitemcheckbox" aria-checked="${Boolean(item.fill)}" data-act="column-fill" data-name="${esc(item.name)}" data-key="${esc(`chip-fill:${item.name}`)}">${svg(GLYPH.check, "check")}<span class="menu-label">Fill down onto every line of the order</span></button></div>`
    : "";
  return `<span class="menu-anchor chip-anchor" data-chip="${esc(item.name)}">
    <span class="chip"><button class="chip-name mono" type="button" aria-haspopup="menu" aria-expanded="${open}" data-act="menu" data-menu="${esc(menuName)}" data-key="${esc(menuName)}">${esc(item.name)}</button>${note}<button class="chip-remove" type="button" title="Remove" aria-label="Remove ${esc(item.name)}" data-act="column-remove" data-name="${esc(item.name)}" data-key="${esc(`chip-remove:${item.name}`)}">${svg(GLYPH.x, "glyph")}</button></span>
    ${menu}
  </span>`;
}

function additionalCard(a) {
  const open = view.menu === "column-add";
  const items = a.candidates
    .map((candidate, n) => menuItem("column-add", { name: candidate.name }, candidate.name, candidate.note, false, `column-add-item-${n}`, true))
    .join("");
  const menu = open
    ? `<div class="menu add-menu" role="menu"><div class="menu-group">${esc(a.group)}</div>${items}</div>`
    : "";
  const add = `<div class="menu-anchor">
      <button class="btn secondary" type="button" aria-haspopup="menu" aria-expanded="${open}" title="${esc(a.add_title)}" data-act="menu" data-menu="column-add" data-key="column-add"${off(!a.candidates.length)}>Add column</button>
      ${menu}
    </div>`;
  const notice = a.notice ? `<div class="card-notice">${esc(a.notice)}</div>` : "";
  const chips = a.chips.length
    ? a.chips.map(chip).join("")
    : `<span class="chips-empty">${esc(a.empty)}</span>`;
  return `<section class="card" data-card="additional">
    ${cardHead("Additional columns", esc(a.text), add)}
    ${notice}
    <div class="chips">${chips}</div>
  </section>`;
}

function mappingPage(m) {
  return (
    fieldsCard(m) +
    (m.couriers ? couriersCard(m.couriers) : "") +
    (m.additional ? additionalCard(m.additional) : "")
  );
}

// --- render ------------------------------------------------------------------

// A menu whose opener a new state removed or disabled must not stay open.
function menuStillOpens(s) {
  const name = view.menu;
  const m = s.mapping;
  if (!m) return false;
  if (name.startsWith("field-")) {
    return m.can_pick && m.fields.some((f) => `field-${f.name}` === name);
  }
  if (name.startsWith("courier-code-")) {
    return Boolean(m.couriers) && Number(name.slice("courier-code-".length)) < m.couriers.rows.length;
  }
  if (name === "column-add") {
    return Boolean(m.additional) && m.additional.candidates.length > 0;
  }
  if (name.startsWith("chip:")) {
    return Boolean(m.additional) && m.additional.chips.some((item) => `chip:${item.name}` === name);
  }
  return false;
}

function keyOf(node) {
  return node.dataset ? node.dataset.key : undefined;
}

// Bring `old` to match `fresh`, keeping every node that is still the same
// control. Every keystroke in a field comes back as a new state: the field
// being typed in must stay the node the caret is in, with the text the
// operator sees, and a press that began on a button must find that button
// there at its release.
function morph(old, fresh) {
  const was = Array.from(old.childNodes);
  const now = Array.from(fresh.childNodes);
  now.forEach((node, n) => {
    const at = was[n];
    if (!at) {
      old.appendChild(node);
    } else if (at.nodeName !== node.nodeName || keyOf(at) !== keyOf(node)) {
      old.replaceChild(node, at);
    } else if (at.nodeType !== Node.ELEMENT_NODE) {
      if (at.data !== node.data) at.data = node.data;
    } else {
      for (const name of at.getAttributeNames()) {
        if (!node.hasAttribute(name)) at.removeAttribute(name);
      }
      for (const name of node.getAttributeNames()) {
        const value = node.getAttribute(name);
        if (at.getAttribute(name) !== value) at.setAttribute(name, value);
      }
      if (at.nodeName === "INPUT") {
        // The attributes are only the defaults once a field has been used.
        if (at !== document.activeElement) at.value = node.value;
      } else {
        morph(at, node);
      }
    }
  });
  was.slice(now.length).forEach((node) => node.remove());
}

// By comparison, not by selector: a key can hold a column's name, and a
// column's name can hold any character.
function byKey(key) {
  return Array.from(els.root.querySelectorAll("[data-key]")).find((el) => el.dataset.key === key) || null;
}

function focusKey(key) {
  const el = byKey(key);
  if (!el || el.disabled) return false;
  el.focus();
  return true;
}

function render() {
  const s = page.state;
  if (!s || !s.page) return;
  if (s.page !== view.shown) {
    view.menu = null;
    view.pending = null;
  }
  if (view.menu !== null && !menuStillOpens(s)) view.menu = null;
  const active = document.activeElement;
  const key = active ? keyOf(active) : null;
  const fresh = document.createElement("template");
  fresh.innerHTML =
    `<div class="settings-page" data-page="${esc(s.page)}">` +
    head(s) +
    (s.general ? generalPage(s.general) : "") +
    (s.mapping ? mappingPage(s.mapping) : "") +
    "</div>";
  morph(els.root, fresh.content);
  if (s.page !== view.shown) {
    view.shown = s.page;
    els.root.scrollTop = 0;
  } else if (key && keyOf(document.activeElement) !== key) {
    // Where the layout itself changed, the focused control is a new node.
    focusKey(key);
  }
  if (view.pending !== null && focusKey(view.pending)) view.pending = null;
  page.renders += 1;
  document.documentElement.dataset.renders = String(page.renders);
}

// --- input -------------------------------------------------------------------

function closeMenu(focus) {
  const menu = view.menu;
  if (menu === null) return;
  view.menu = null;
  render();
  focusKey(focus || menu);
}

function onClick(event) {
  const el = event.target.closest("[data-act]");
  const bridge = page.bridge;
  if (!el || el.disabled || !bridge) return;
  const data = el.dataset;
  switch (data.act) {
    case "read": bridge.readColumns(); break;
    case "delimiter": bridge.edit("delimiter", [data.kind, data.value]); break;
    case "menu":
      view.menu = view.menu === data.menu ? null : data.menu;
      render();
      focusKey(data.menu);
      break;
    case "column":
      bridge.edit("column", [data.field, data.value]);
      closeMenu();
      break;
    case "courier-add":
      // The new row is the next index: focus its text once it arrives.
      view.pending = `courier-text-${page.state.mapping.couriers.rows.length}`;
      bridge.edit("courier_add", []);
      break;
    case "courier-code":
      bridge.edit("courier_code", [data.index, data.value]);
      closeMenu();
      break;
    case "courier-remove": bridge.edit("courier_remove", [data.index]); break;
    case "column-add":
      bridge.edit("column_add", [data.name]);
      closeMenu();
      break;
    case "column-remove": bridge.edit("column_remove", [data.name]); break;
    case "column-fill":
      bridge.edit("column_fill", [data.name, el.getAttribute("aria-checked") !== "true"]);
      break;
  }
}

// A text field reports every keystroke: the unsaved mark and Save follow the
// typing, and Python answers with a state the render folds in around the caret.
function onInput(event) {
  const el = event.target;
  const bridge = page.bridge;
  if (!bridge || !el.dataset || !el.dataset.input) return;
  const data = el.dataset;
  if (data.input === "threshold") bridge.edit("threshold", [el.value]);
  else if (data.input === "delimiter_char") bridge.edit("delimiter_char", [data.kind, el.value]);
  else if (data.input === "courier_pattern") bridge.edit("courier_pattern", [data.index, el.value]);
}

function onKey(event) {
  const target = event.target;
  if (event.key === "Escape") {
    // With no menu open the page leaves Escape alone, and the dialog takes it.
    if (view.menu === null) return;
    event.preventDefault();
    closeMenu();
    return;
  }
  if (event.key === "Enter" && target.dataset && target.dataset.newCourier !== undefined) {
    event.preventDefault();
    if (page.bridge) page.bridge.edit("courier_code", [target.dataset.newCourier, target.value]);
    closeMenu();
    return;
  }
  const vertical = event.key === "ArrowUp" || event.key === "ArrowDown";
  if (vertical && view.menu !== null) {
    // Up and Down walk the open menu, from its opener or from an item.
    const items = Array.from(els.root.querySelectorAll(".menu .menu-item, .menu .new-courier"));
    if (!items.length) return;
    const at = items.indexOf(document.activeElement);
    const step = event.key === "ArrowUp" ? -1 : 1;
    const next = at < 0 ? (step > 0 ? 0 : items.length - 1) : (at + step + items.length) % items.length;
    event.preventDefault();
    items[next].focus();
    return;
  }
  // Left and Right move between a delimiter's segments; Space and Enter are
  // the button's own.
  const segment = target.closest ? target.closest(".segment") : null;
  if (!segment || (event.key !== "ArrowLeft" && event.key !== "ArrowRight")) return;
  const group = Array.from(segment.parentElement.querySelectorAll(".segment"));
  const step = event.key === "ArrowLeft" ? -1 : 1;
  event.preventDefault();
  group[(group.indexOf(segment) + step + group.length) % group.length].focus();
}

// The footer's link: put the operator on the control that blocks the save.
function focusProblem(key) {
  const el = byKey(key);
  if (!el) return;
  el.scrollIntoView({ block: "center" });
  if (!el.disabled) el.focus();
}

// --- boot --------------------------------------------------------------------

function bind() {
  els.root = document.getElementById("settings");
  els.themeVars = document.getElementById("theme-vars");
  els.root.addEventListener("click", onClick);
  els.root.addEventListener("input", onInput);
  document.addEventListener("keydown", onKey);
  // After the page's own handler: a click anywhere but a menu's anchor closes
  // the open menu.
  document.addEventListener("click", (event) => {
    if (view.menu === null || event.target.closest(".menu-anchor")) return;
    view.menu = null;
    render();
  });
  // A file dropped on the page must not navigate the view. It loads nothing.
  document.addEventListener("dragover", (event) => event.preventDefault());
  document.addEventListener("drop", (event) => event.preventDefault());
}

bind();

new QWebChannel(qt.webChannelTransport, function (channel) {
  const bridge = channel.objects.settings;
  page.bridge = bridge;
  els.themeVars.textContent = bridge.themeCss;
  bridge.themeCssChanged.connect(() => { els.themeVars.textContent = bridge.themeCss; });
  bridge.stateChanged.connect(() => { page.state = bridge.state; render(); });
  bridge.problemFocusRequested.connect((key) => focusProblem(key));
  page.state = bridge.state;
  render();
  window.settingsBridge = bridge;
  document.documentElement.dataset.bridge = "ready";
});
```

`morph` is the Tools page's (`gui/web/tools.js`), without the checkbox line. It is copied, not shared: each
page's script stands alone, as the other four do.

- [ ] **Step 5: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_settings_bridge.py tests/test_settings_web_page.py tests/test_style_literals_guard.py`

Expected: all pass (51 in the two new files in the scratch copy).

- [ ] **Step 6: Lint and commit**

Run: `.venv/bin/ruff check .` Expected: `All checks passed!`

Stage the four new files under `gui/` and the two test files and commit. Message subject:
`Settings: the bridge and the web page for General and the two mappings`.

---

### Task 9: `SettingsWebHost`

The widget that holds the view (spec §6.5): it draws one draft at a time, hands the page's edits to it, and
opens the file dialog for Read columns from CSV….

**Files:**
- Create: `gui/settings/web_host.py`
- Test: `tests/test_settings_web_host.py` (new)

**Interfaces:**
- Consumes: `mount_settings_page` (Task 8); the drafts (Tasks 4 to 6); `read_csv_preview` (Task 2);
  `gui.components.show_error` (already in the repo).
- Produces, in `gui.settings.web_host`:
  - `read_file_columns(path, loaded: bool) -> FileColumns`. It raises what reading the file raises.
  - `SettingsWebHost(drafts: dict, parent=None)`, a `QWidget`, with `drafts`, `view`, `bridge`,
    `show_page(key: str)`, `focus_problem(key: str)`, and the signal `edited()`. `drafts` is keyed
    `"general"`, `"orders"`, `"stock"`; the first key is the page it opens on.

- [ ] **Step 1: Write the failing test**

Create `tests/test_settings_web_host.py`:

```python
"""SettingsWebHost: one web view, three drafts (phase 7 spec section 6.5).

Nothing here waits for Chromium: the bridge's state is read on the Python
side, and the page's requests are made by calling the bridge's slots.
"""

import pytest
from PySide6.QtWidgets import QFileDialog

from gui.settings.page_state import (
    FileColumns,
    GeneralDraft,
    OrdersDraft,
    StockDraft,
)
from gui.settings.web_host import SettingsWebHost, read_file_columns


@pytest.fixture
def host(qtbot):
    mappings = {
        "version": 2,
        "orders": {
            "Name": "Order_Number",
            "Lineitem sku": "SKU",
            "Lineitem quantity": "Quantity",
            "Shipping Method": "Shipping_Method",
        },
        "stock": {"Article": "SKU", "Available": "Stock"},
        "additional_columns": [],
    }
    drafts = {
        "general": GeneralDraft({"low_stock_threshold": 5}, "ACME"),
        "orders": OrdersDraft(mappings, {}, "ACME"),
        "stock": StockDraft(mappings, "ACME"),
    }
    widget = SettingsWebHost(drafts)
    qtbot.addWidget(widget)
    return widget


def _edits(host):
    seen = []
    host.edited.connect(lambda: seen.append(True))
    return seen


def _pick(monkeypatch, path):
    asked = []

    def choose(parent, title, start, filters):
        asked.append((title, filters))
        return str(path), ""

    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(choose))
    return asked


def _errors(monkeypatch):
    seen = []
    monkeypatch.setattr(
        "gui.settings.web_host.show_error",
        lambda parent, headline, what: seen.append((headline, what)),
    )
    return seen


def test_it_opens_on_the_first_draft(host):
    assert host.bridge.state["page"] == "general"


def test_show_page_draws_that_draft(host):
    host.show_page("stock")
    assert host.bridge.state["page"] == "stock"
    assert host.bridge.state["title"] == "Stock mapping"


def test_an_edit_reaches_the_draft_is_drawn_and_is_announced(host):
    seen = _edits(host)
    host.bridge.edit("threshold", ["9"])
    assert host.drafts["general"].threshold == "9"
    assert host.bridge.state["general"]["threshold"]["value"] == "9"
    assert seen == [True]


def test_an_edit_that_changes_nothing_is_not_announced(host):
    seen = _edits(host)
    host.bridge.edit("threshold", ["5"])
    host.bridge.edit("no_such_action", [])
    assert seen == []


def test_an_edit_goes_to_the_page_that_is_showing(host):
    host.show_page("orders")
    host.bridge.edit("threshold", ["9"])
    assert host.drafts["general"].threshold == "5"
    host.bridge.edit("courier_add", [])
    assert host.drafts["orders"].courier_rows == [["", ""]]


def test_read_columns_offers_the_chosen_files_columns(host, monkeypatch, tmp_path):
    path = tmp_path / "picked.csv"
    path.write_text("Name,Lineitem sku,Notes\n#1,ABC,leave at door\n", encoding="utf-8")
    asked = _pick(monkeypatch, path)
    seen = _edits(host)
    host.show_page("orders")

    host.bridge.readColumns()

    assert asked == [("Select Orders CSV", "CSV Files (*.csv);;All Files (*)")]
    assert host.drafts["orders"].file == FileColumns(
        "picked.csv",
        ("Name", "Lineitem sku", "Notes"),
        {"Name": "#1", "Lineitem sku": "ABC", "Notes": "leave at door"},
        False,
    )
    assert host.drafts["stock"].file is None
    mapping = host.bridge.state["mapping"]
    assert mapping["can_pick"] is True
    assert mapping["source"] == {
        "lead": "Columns read from",
        "file": "picked.csv",
        "tail": ".",
    }
    assert seen == [True]


def test_read_columns_changes_no_mapping(host, monkeypatch, tmp_path):
    path = tmp_path / "picked.csv"
    path.write_text("A,B\n1,2\n", encoding="utf-8")
    _pick(monkeypatch, path)
    host.show_page("orders")
    before = dict(host.drafts["orders"].chosen)
    host.bridge.readColumns()
    assert host.drafts["orders"].chosen == before


def test_a_cancelled_dialog_changes_nothing(host, monkeypatch):
    _pick(monkeypatch, "")
    seen = _edits(host)
    host.show_page("stock")
    host.bridge.readColumns()
    assert host.drafts["stock"].file is None
    assert seen == []


def test_a_file_that_cannot_be_read_says_so_and_changes_nothing(
    host, monkeypatch, tmp_path
):
    _pick(monkeypatch, tmp_path / "gone.csv")
    errors = _errors(monkeypatch)
    seen = _edits(host)
    host.show_page("orders")
    host.bridge.readColumns()
    assert errors == [("The column names couldn't be read", "Details are in Logs.")]
    assert host.drafts["orders"].file is None
    assert seen == []


def test_an_empty_file_cannot_be_read(host, monkeypatch, tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("", encoding="utf-8")
    _pick(monkeypatch, path)
    errors = _errors(monkeypatch)
    host.show_page("orders")
    host.bridge.readColumns()
    assert errors == [("The column names couldn't be read", "Details are in Logs.")]


def test_general_has_no_columns_to_read(host, monkeypatch, tmp_path):
    asked = _pick(monkeypatch, tmp_path / "x.csv")
    host.bridge.readColumns()
    assert asked == []


def test_focus_problem_asks_the_page_for_that_control(host):
    seen = []
    host.bridge.problemFocusRequested.connect(seen.append)
    host.focus_problem("threshold")
    assert seen == ["threshold"]


def test_read_file_columns_names_the_file_and_marks_where_it_came_from(tmp_path):
    path = tmp_path / "stock-30-09.csv"
    path.write_text("Артикул;Наличност\nABC;4\nXYZ;9\n", encoding="utf-8")
    assert read_file_columns(path, loaded=True) == FileColumns(
        "stock-30-09.csv",
        ("Артикул", "Наличност"),
        {"Артикул": "ABC", "Наличност": "4"},
        True,
    )
```

- [ ] **Step 2: Run it and see it fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_settings_web_host.py`

Expected: an error at collection, `ModuleNotFoundError: No module named 'gui.settings.web_host'`.

- [ ] **Step 3: Write the host**

Create `gui/settings/web_host.py`:

```python
"""The widget that shows the settings pages the web tier draws (phase 7 spec
section 6.5).

One web view for General, Orders mapping and Stock mapping. The window keeps
the three drafts in its page list, like any other page; this widget shows one
of them at a time, hands the page's edits to it, and says when it changed.
"""

import logging
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QFileDialog, QVBoxLayout, QWidget

from gui.components import show_error
from gui.settings.bridge import mount_settings_page
from gui.settings.page_state import FileColumns, MappingDraft
from shopify_tool.csv_utils import read_csv_preview

logger = logging.getLogger(__name__)


def read_file_columns(path, loaded: bool) -> FileColumns:
    """A CSV's header and first row. Raises what reading the file raises."""
    headers, first_row = read_csv_preview(str(path))
    return FileColumns(Path(path).name, tuple(headers), first_row, loaded)


class SettingsWebHost(QWidget):
    """One web view and the drafts it draws, keyed "general", "orders", "stock".

    Signals:
        edited: a draft's values, or the file it reads columns from, changed
    """

    edited = Signal()

    def __init__(self, drafts: dict, parent=None):
        super().__init__(parent)
        self.drafts = drafts
        self._current = next(iter(drafts))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.view = QWebEngineView(self)
        self.bridge = mount_settings_page(self.view)
        layout.addWidget(self.view, 1)

        self.bridge.editRequested.connect(self._on_edit)
        self.bridge.readColumnsRequested.connect(self._read_columns)
        self._push()

    def show_page(self, key: str) -> None:
        """Draw the draft under `key`."""
        self._current = key
        self._push()

    def focus_problem(self, key: str) -> None:
        """Put the operator on the control with this data-key."""
        self.view.setFocus()
        self.bridge.problemFocusRequested.emit(key)

    def _push(self) -> None:
        self.bridge.set_state(self.drafts[self._current].view())

    def _on_edit(self, action: str, args: list) -> None:
        if not self.drafts[self._current].apply(action, args):
            # Nothing changed: a repeat of the current value, or an edit the
            # draft does not know.
            logger.debug(f"Settings edit changed nothing: {action} {args!r}")
            return
        self._push()
        self.edited.emit()

    def _read_columns(self) -> None:
        """Offer a chosen CSV's columns on the mapping page that is showing.

        Reads the header and one row, and detects the delimiter itself, so
        this does not depend on the delimiter General currently shows, which
        may hold an edit the operator has not saved yet.
        """
        draft = self.drafts[self._current]
        if not isinstance(draft, MappingDraft):
            return
        path, _filter = QFileDialog.getOpenFileName(
            self,
            f"Select {draft.kind.capitalize()} CSV",
            "",
            "CSV Files (*.csv);;All Files (*)",
        )
        if not path:
            return
        try:
            file = read_file_columns(path, loaded=False)
        except Exception:
            logger.exception("Failed to read column names from CSV")
            show_error(
                self, "The column names couldn't be read", "Details are in Logs."
            )
            return
        draft.set_file(file)
        self._push()
        self.edited.emit()
```

- [ ] **Step 4: Run the test**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_settings_web_host.py`

Expected: 13 passed.

- [ ] **Step 5: Lint and commit**

Run: `.venv/bin/ruff check .` Expected: `All checks passed!`

Stage `gui/settings/web_host.py tests/test_settings_web_host.py` and commit. Message subject:
`Settings: SettingsWebHost, one web view for three drafts`.

---

### Task 10: The dialog hosts the drafts; the three Qt pages go

`SettingsWindow` builds the three drafts and one host, registers each draft under its page name, and the
stack shows the host for all three. The Qt General and mapping pages, their widget and their tests are
deleted: the draft tests of Tasks 4 to 6 carry their cases.

**Files:**
- Modify: `gui/settings/window.py`, `gui/actions_handler.py`
- Delete: `gui/settings/general.py`, `gui/settings/mappings.py`, `gui/column_mapping_widget.py`,
  `tests/test_settings_page_general.py`, `tests/test_settings_page_mappings.py`,
  `tests/test_settings_additional_columns.py`
- Test: `tests/test_settings_roundtrip.py`, `tests/test_settings_button_roles.py`,
  `tests/test_results_data_fields.py`, `tests/test_actions_handler.py`

**Interfaces:**
- Consumes: the drafts, `ADDITIONAL_COLUMNS_UNREADABLE` (Tasks 4 to 6); `SettingsWebHost`,
  `read_file_columns` (Task 9); `PageContract` (Task 3).
- Produces, on `SettingsWindow`:
  - a new keyword argument `loaded_files: dict | None = None` (`{"orders": path, "stock": path}`);
  - `_web_host: SettingsWebHost`; `gui.settings.window.WEB_PAGE_KEYS` (`{"General": "general",
    "Orders mapping": "orders", "Stock mapping": "stock"}`);
  - `_add_page(page, name, widget=None)`; `_pages` and `_pages_by_name` now hold `PageContract`s (three of
    them drafts); `_page_index_by_name[name]` is the stack index of the widget that shows the page, so the
    three web pages share one index;
  - `_poll_page(name)`, and `_on_web_edit()`, connected to the host's `edited`.

- [ ] **Step 1: Change the tests**

In `tests/test_settings_roundtrip.py`, find exactly:

```python
    """Guards the live-reference contract OrdersMappingPage depends on.

    `courier_mappings` holds a variable set of keys, and the shell's merge is
    `dict.update()`, which never drops one. OrdersMappingPage only gets away
    with this because window.py hands it the *live* sub-dict, which it clears
    and refills in place. Hand it a copy instead and this test fails while
    every page-level test stays green.
    """
    mappings = window._pages[window._page_index_by_name["Orders mapping"]]
    for row_refs in list(mappings.courier_mapping_widgets):
        mappings._delete_courier_row(row_refs)
```

Replace with:

```python
    """Guards the live-reference contract OrdersDraft depends on.

    `courier_mappings` holds a variable set of keys, and the shell's merge is
    `dict.update()`, which never drops one. OrdersDraft only gets away with
    this because window.py hands it the *live* sub-dict, which it clears and
    refills in place. Hand it a copy instead and this test fails while every
    draft-level test stays green.
    """
    mappings = window._pages_by_name["Orders mapping"]
    while mappings.courier_rows:
        mappings.apply("courier_remove", ["0"])
```

In `tests/test_settings_roundtrip.py`, find exactly:

```python
    Blind spot to know about: General and Weight hold the *live* sub-dict
    (see gui/settings/base.py), so for those two this compares an object to
    a deepcopy of itself and a dropped key still shows up. Their key coverage
    lives in test_settings_page_{general,weight}.py, which detach the page
    from the live dict first. Every other page builds a fresh dict, so this
    still bites for them.
```

Replace with:

```python
    Blind spot to know about: General and Weight hold the *live* sub-dict
    (see gui/settings/contract.py), so for those two this compares an object
    to a deepcopy of itself and a dropped key still shows up. Their key
    coverage lives in test_settings_draft_general.py and
    test_settings_page_weight.py, which detach the page from the live dict
    first. Every other page builds a fresh dict, so this still bites for them.
```

In `tests/test_settings_roundtrip.py`, append at the end of the file:

```python


def test_the_three_web_pages_share_one_widget_in_the_stack(window):
    """General and both mappings are drafts: the stack shows one host for all
    three, and the nav tells the host which to draw."""
    host = window._web_host
    for name, key in (
        ("General", "general"),
        ("Orders mapping", "orders"),
        ("Stock mapping", "stock"),
    ):
        window._select_page(name)
        assert window.tab_widget.currentWidget() is host
        assert host.bridge.state["page"] == key
    window._select_page("Sets")
    assert window.tab_widget.currentWidget() is window._pages_by_name["Sets"]


def test_an_edit_on_a_web_page_marks_it_unsaved_at_once(window):
    window._select_page("General")
    window._web_host.bridge.edit("threshold", ["9"])
    assert window._unsaved == {"General"}
    window._web_host.bridge.edit("threshold", ["5"])
    assert window._unsaved == set()


def test_a_web_page_edit_is_what_gets_saved(window, no_modals, started_workers):
    window._select_page("Orders mapping")
    window._web_host.bridge.edit("courier_add", [])
    window._web_host.bridge.edit("courier_pattern", ["2", "evri"])
    window._web_host.bridge.edit("courier_code", ["2", "Evri"])
    window._select_page("General")
    window._web_host.bridge.edit("delimiter", ["orders", "tab"])

    window.save_settings()

    assert no_modals == []
    assert len(started_workers) == 1
    assert window.config_data["courier_mappings"]["Evri"] == {
        "patterns": ["evri"],
        "case_sensitive": False,
    }
    assert window.config_data["settings"]["orders_csv_delimiter"] == "\t"


def test_a_mapping_page_opens_with_the_file_loaded_on_setup(
    qapp, no_modals, started_workers, make_settings_config, tmp_path
):
    orders = tmp_path / "orders-30-09.csv"
    orders.write_text("Name,Lineitem sku\n#1,ABC\n", encoding="utf-8")
    win = SettingsWindow(
        client_id="M",
        client_config=make_settings_config(),
        profile_manager=Mock(),
        loaded_files={"orders": str(orders), "stock": str(tmp_path / "gone.csv")},
    )
    drafts = win._web_host.drafts
    assert drafts["orders"].file.name == "orders-30-09.csv"
    assert drafts["orders"].file.loaded is True
    assert drafts["orders"].file.columns == ("Name", "Lineitem sku")
    # A file that cannot be read is no file, and nothing is raised.
    assert drafts["stock"].file is None
    assert win.refresh_dirty() == []
    win.deleteLater()


def test_with_no_loaded_files_the_mapping_pages_have_no_file(window):
    assert window._web_host.drafts["orders"].file is None
    assert window._web_host.drafts["stock"].file is None
```

In `tests/test_settings_button_roles.py`, find exactly:

```python
    unmarked = []
    for page in window._pages:
        for button in page.findChildren(QPushButton):
            if button.property("role") is None:
                unmarked.append(f"{type(page).__name__}: {button.text()!r}")
```

Replace with:

```python
    unmarked = []
    # The stack's widgets, not _pages: three pages are drafts with no widget.
    for index in range(window.tab_widget.count()):
        page = window.tab_widget.widget(index)
        for button in page.findChildren(QPushButton):
            if button.property("role") is None:
                unmarked.append(f"{type(page).__name__}: {button.text()!r}")
```

In `tests/test_results_data_fields.py`, find exactly:

```python
    from gui.settings.mappings import OrdersMappingPage

    assert {"Customer", "Created_At"} <= set(OrdersMappingPage.OPTIONAL_FIELDS)
```

Replace with:

```python
    from gui.settings.page_state import FIELDS

    optional = {f.name for f in FIELDS["orders"] if not f.required}
    assert {"Customer", "Created_At"} <= optional
```

In `tests/test_actions_handler.py`, find exactly:

```python
    mw = SimpleNamespace(
        current_client_id="M", profile_manager=profile_manager, analysis_results_df=None
    )

    ActionsHandler(mw).open_settings_window()

    assert headlines == ["Settings were saved but didn't reload"]
```

Replace with:

```python
    mw = SimpleNamespace(
        current_client_id="M",
        profile_manager=profile_manager,
        analysis_results_df=None,
        orders_file_path=None,
        stock_file_path=None,
    )

    ActionsHandler(mw).open_settings_window()

    assert headlines == ["Settings were saved but didn't reload"]


def test_the_settings_window_is_told_which_files_are_loaded(monkeypatch):
    seen = {}

    def window(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(exec=lambda: False)

    monkeypatch.setattr("gui.actions_handler.SettingsWindow", window)
    profile_manager = Mock()
    profile_manager.load_shopify_config.return_value = {"settings": {}}
    mw = SimpleNamespace(
        current_client_id="M",
        profile_manager=profile_manager,
        analysis_results_df=None,
        orders_file_path="/data/orders.csv",
        stock_file_path=None,
    )

    ActionsHandler(mw).open_settings_window(page="Orders mapping")

    assert seen["loaded_files"] == {"orders": "/data/orders.csv", "stock": None}
    assert seen["initial_page"] == "Orders mapping"
```


- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_settings_roundtrip.py tests/test_results_data_fields.py tests/test_actions_handler.py`

Expected: failures. The window has no `_web_host`, takes no `loaded_files`, and its Orders page is still the
Qt one.

- [ ] **Step 3: Host the drafts and delete the Qt pages**

In `gui/settings/window.py`, find exactly:

```python
from gui.settings.base import SettingsPage
from gui.settings.general import GeneralPage
from gui.settings.mappings import (
    ADDITIONAL_COLUMNS_UNREADABLE,
    OrdersMappingPage,
    StockMappingPage,
)
from gui.settings.reports import ReportsPage
from gui.settings.rules import RulesPage
from gui.settings.sets import SetsPage
from gui.settings.weight import WeightPage
```

Replace with:

```python
from gui.settings.base import SettingsPage
from gui.settings.contract import PageContract
from gui.settings.page_state import (
    ADDITIONAL_COLUMNS_UNREADABLE,
    GeneralDraft,
    OrdersDraft,
    StockDraft,
)
from gui.settings.reports import ReportsPage
from gui.settings.rules import RulesPage
from gui.settings.sets import SetsPage
from gui.settings.web_host import SettingsWebHost, read_file_columns
from gui.settings.weight import WeightPage
```

In `gui/settings/window.py`, find exactly:

```python
    "Tag categories": ["tags", "labels", "colours", "colors", "writeoff", "sku"],
}
```

Replace with:

```python
    "Tag categories": ["tags", "labels", "colours", "colors", "writeoff", "sku"],
}

# Nav name -> the key SettingsWebHost draws that page under (phase 7). Every
# other page is a Qt widget.
WEB_PAGE_KEYS: dict[str, str] = {
    "General": "general",
    "Orders mapping": "orders",
    "Stock mapping": "stock",
}
```

In `gui/settings/window.py`, find exactly:

```python
        analysis_df=None,
        parent=None,
        initial_page=None,
    ):
```

Replace with:

```python
        analysis_df=None,
        parent=None,
        initial_page=None,
        loaded_files=None,
    ):
```

In `gui/settings/window.py`, find exactly:

```python
                which page answers the user's problem says so; everyone else
                gets the last page they were on. Defaults to None.
        """
```

Replace with:

```python
                which page answers the user's problem says so; everyone else
                gets the last page they were on. Defaults to None.
            loaded_files (dict, optional): {"orders": path, "stock": path} for
                the files loaded on Setup. A mapping page opens with that
                file's columns. Defaults to None.
        """
```

In `gui/settings/window.py`, find exactly:

```python
        self._page_index_by_name = {}
        self._pages: list[SettingsPage] = []
        self._pages_by_name: dict[str, SettingsPage] = {}
        self._unsaved: set[str] = set()

        # Create all tabs (unchanged call order/method names)
        self._add_page(GeneralPage(self.config_data.get("settings", {})), "General")
        self._add_page(
```

Replace with:

```python
        self._page_index_by_name = {}
        self._pages: list[PageContract] = []
        self._pages_by_name: dict[str, PageContract] = {}
        self._unsaved: set[str] = set()

        # The three pages the web tier draws are drafts: pages with no widget.
        # One host widget shows whichever of them the nav selects.
        client = str(self.client_id)
        column_mappings = self.config_data.get("column_mappings", {})
        drafts = {
            "general": GeneralDraft(self.config_data.get("settings", {}), client),
            "orders": OrdersDraft(
                column_mappings,
                self.config_data.get("courier_mappings", {}),
                client,
                fallback_additional_columns=self._stored_additional_columns(),
                file=self._loaded_file(loaded_files, "orders"),
            ),
            "stock": StockDraft(
                column_mappings, client, file=self._loaded_file(loaded_files, "stock")
            ),
        }
        self._web_host = SettingsWebHost(drafts)
        self._web_host.edited.connect(self._on_web_edit)

        # Create all tabs (unchanged call order/method names)
        self._add_page(drafts["general"], "General", self._web_host)
        self._add_page(
```

In `gui/settings/window.py`, find exactly:

```python
        self._add_page(
            OrdersMappingPage(
                self.config_data.get("column_mappings", {}),
                self.config_data.get("courier_mappings", {}),
                fallback_additional_columns=self._stored_additional_columns(),
            ),
            "Orders mapping",
        )
        self._add_page(
            StockMappingPage(self.config_data.get("column_mappings", {})),
            "Stock mapping",
        )
```

Replace with:

```python
        self._add_page(drafts["orders"], "Orders mapping", self._web_host)
        self._add_page(drafts["stock"], "Stock mapping", self._web_host)
```

In `gui/settings/window.py`, find exactly:

```python
    def _add_page(self, page: SettingsPage, name: str) -> None:
        """Register a settings page under `name`. Tracked in _pages so
        save_settings validates and collects from it.

        Replaces the old `self.tab_widget.addTab(page, name)` calls — the
        10-tab horizontal strip is replaced by a grouped left-nav
        (_build_settings_nav) that looks up pages by this same name.
        """
        self._pages.append(page)
        self._pages_by_name[name] = page
        self.tab_widget.addWidget(page)
        self._page_index_by_name[name] = self.tab_widget.count() - 1
```

Replace with:

```python
    def _add_page(self, page: PageContract, name: str, widget=None) -> None:
        """Register a settings page under `name`. Tracked in _pages so
        save_settings validates and collects from it.

        `widget` is what the stack shows for it: the page itself when it is a
        Qt page, the web host when it is a draft. The grouped left-nav
        (_build_settings_nav) looks pages up by this same name.
        """
        widget = page if widget is None else widget
        self._pages.append(page)
        self._pages_by_name[name] = page
        if self.tab_widget.indexOf(widget) < 0:
            self.tab_widget.addWidget(widget)
        self._page_index_by_name[name] = self.tab_widget.indexOf(widget)

    @staticmethod
    def _loaded_file(loaded_files, kind: str):
        """The columns of the file loaded on Setup, or None.

        A file that cannot be read is no file: the mapping page then says no
        CSV has been read, and the operator can pick one.
        """
        path = (loaded_files or {}).get(kind)
        if not path:
            return None
        try:
            return read_file_columns(path, loaded=True)
        except Exception:
            logger.exception(f"The loaded {kind} file's columns couldn't be read")
            return None

    def _on_web_edit(self) -> None:
        """A draft changed: its unsaved mark follows at once, with no poll."""
        changed = False
        for name in WEB_PAGE_KEYS:
            if self._pages_by_name[name].is_dirty() != (name in self._unsaved):
                self._unsaved ^= {name}
                changed = True
        if changed:
            self._render_unsaved()
```

In `gui/settings/window.py`, find exactly:

```python
        index = current.data(Qt.ItemDataRole.UserRole)
        if index is not None:
            self.tab_widget.setCurrentIndex(index)
```

Replace with:

```python
        index = current.data(Qt.ItemDataRole.UserRole)
        if index is not None:
            if current.text() in WEB_PAGE_KEYS:
                self._web_host.show_page(WEB_PAGE_KEYS[current.text()])
            self.tab_widget.setCurrentIndex(index)
```

In `gui/settings/window.py`, find exactly:

```python
    def _on_settings_nav_changed(self, current, _previous):
        self._validation_message.clear()
        # The page being left may hold an edit the 400ms poll hasn't seen.
        self._poll_current_page()
```

Replace with:

```python
    def _on_settings_nav_changed(self, current, previous):
        self._validation_message.clear()
        # The page being left may hold an edit the 400ms poll hasn't seen.
        if previous is not None:
            self._poll_page(previous.text())
```

In `gui/settings/window.py`, find exactly:

```python
    def _poll_current_page(self) -> None:
        page = self.tab_widget.currentWidget()
        name = next((n for n, p in self._pages_by_name.items() if p is page), None)
        if name is None:
            return
```

Replace with:

```python
    def _poll_current_page(self) -> None:
        item = self._settings_nav.currentItem()
        if item is not None:
            self._poll_page(item.text())

    def _poll_page(self, name: str) -> None:
        # By the nav's name, not the stack's widget: three pages share one.
        page = self._pages_by_name.get(name)
        if page is None:
            return
```

Delete `gui/settings/general.py` (`/usr/bin/git rm gui/settings/general.py`).

Delete `gui/settings/mappings.py` (`/usr/bin/git rm gui/settings/mappings.py`).

Delete `gui/column_mapping_widget.py` (`/usr/bin/git rm gui/column_mapping_widget.py`).

Delete `tests/test_settings_page_general.py` (`/usr/bin/git rm tests/test_settings_page_general.py`).

Delete `tests/test_settings_page_mappings.py` (`/usr/bin/git rm tests/test_settings_page_mappings.py`).

Delete `tests/test_settings_additional_columns.py` (`/usr/bin/git rm tests/test_settings_additional_columns.py`).

In `gui/actions_handler.py`, find exactly:

```python
            parent=self.mw,
            initial_page=page,
        )
```

Replace with:

```python
            parent=self.mw,
            initial_page=page,
            loaded_files={
                "orders": self.mw.orders_file_path,
                "stock": self.mw.stock_file_path,
            },
        )
```


`_on_settings_nav_changed` used to check the page being left by asking the stack for its current widget,
before the stack switched. Three pages now share one widget, so it asks by the previous nav row's name
instead. `tests/test_settings_unsaved.py::test_leaving_a_page_checks_it_before_the_next_poll` guards it.

- [ ] **Step 4: Run the settings tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_settings_roundtrip.py tests/test_settings_nav.py tests/test_settings_unsaved.py tests/test_settings_button_roles.py tests/test_results_data_fields.py tests/test_settings_window_weight_quick_add.py tests/test_settings_entry_points.py tests/test_actions_handler.py`

Expected: all pass.

Then check nothing still imports what was deleted:
`rg -n "settings.general|settings.mappings|column_mapping_widget|ColumnMappingWidget|GeneralPage|OrdersMappingPage|StockMappingPage" gui tests shopify_tool`
should print nothing.

- [ ] **Step 5: Run the whole suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`

Expected: only the three baseline failures.

- [ ] **Step 6: Lint and commit**

Run: `.venv/bin/ruff check .` Expected: `All checks passed!`

Stage `gui/settings/window.py gui/actions_handler.py` and the four changed test files, plus the six
deletions (`/usr/bin/git rm` stages each), and commit. Message subject:
`Settings: General and the two mappings are drafts on one web view`.

---

### Task 11: The frame, to the mockup

The nav, the search, the marks and the dialog's layout (spec §6.1, §6.2). The footer's status line and Save
are Task 12; this task gives the footer its height, its margins and its rule.

**Files:**
- Create: `shared/assets/icons/circle-alert.svg`
- Modify: `gui/settings/window.py`, `gui/theme_manager.py`
- Test: `tests/test_settings_nav.py`, `tests/test_ui_assets.py`

**Interfaces:**
- Consumes: `PageContract.blocker()` (Task 3); `_web_host`, `WEB_PAGE_KEYS`, `_on_web_edit` (Task 10);
  `shared.icons.icon(name, color)` (already in the repo).
- Produces, on `SettingsWindow`:
  - `_blocked: dict[str, str]` (page name → its `blocker()`), recomputed by `_refresh_status()`, which
    `_on_web_edit()` and the constructor call;
  - `_nav_panel` (a `QFrame` named `settingsNavPanel`), `_marks` (the four mark icons), `_NavDelegate`;
  - module constants `NAV_MARGIN_PX`, `NAV_ROW_PX`, `NAV_GROUP_PX`, `NAV_MARK_PX`, `NAV_MARKS_WIDTH_PX`,
    `FOOTER_HEIGHT_PX`, `FOOTER_MARGIN_PX`, `PAGE_MARGIN_PX`;
  - the window title `Client settings · {client_id}`.

- [ ] **Step 1: Add the failing tests**

In `tests/test_ui_assets.py`, find exactly:

```python
    "panel-left-close", "panel-left-open", "sun", "moon", "server",
]
```

Replace with:

```python
    "panel-left-close", "panel-left-open", "sun", "moon", "server",
    "circle-alert",
]
```

In `tests/test_settings_nav.py`, find exactly:

```python
from PySide6.QtCore import QSettings, Qt
from PySide6.QtTest import QTest
```

Replace with:

```python
from PySide6.QtCore import QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QStyleOptionViewItem
```

In `tests/test_settings_nav.py`, find exactly:

```python
    assert window.filter_nav("zzz") == []
    assert not window._no_match_label.isHidden()
```

Replace with:

```python
    assert window.filter_nav("zzz") == []
    assert not window._no_match_label.isHidden()
    assert window._no_match_label.text() == "No settings match “zzz”."
```

In `tests/test_settings_nav.py`, append at the end of the file:

```python


# --- the frame, to the mockup (phase 7 spec section 6) ------------------------


def _page_row(win, name):
    nav = win._settings_nav
    return next(r for r in range(nav.count()) if nav.item(r).text() == name)


def test_the_title_bar_names_the_window_and_the_client(window):
    assert window.windowTitle() == "Client settings · M"


def test_the_nav_is_a_232px_column_of_30px_rows(window):
    from gui.settings.window import NAV_MARGIN_PX

    nav = window._settings_nav
    assert nav.width() + 2 * NAV_MARGIN_PX >= 232
    assert nav.item(_page_row(window, "General")).sizeHint().height() == 30
    assert nav.item(_page_row(window, "Data")).sizeHint().height() == 28
    assert window._nav_panel.objectName() == "settingsNavPanel"
    assert nav.parentWidget() is window._nav_panel


def test_only_the_open_page_reads_bold(window):
    nav = window._settings_nav
    window._select_page("Sets")
    bold = [
        nav.item(r).text()
        for r in range(nav.count())
        if nav.item(r).font().bold()
        and nav.item(r).data(Qt.ItemDataRole.UserRole) is not None
    ]
    assert bold == ["Sets"]


def test_a_rows_marks_are_drawn_at_its_right_edge(window):
    nav = window._settings_nav
    option = QStyleOptionViewItem()
    nav.itemDelegate().initStyleOption(
        option, nav.model().index(_page_row(window, "General"), 0)
    )
    assert option.decorationPosition == QStyleOptionViewItem.Position.Right


def _mark_pixel(win, name, x):
    from gui.settings.window import NAV_MARK_PX, NAV_MARKS_WIDTH_PX

    item = win._settings_nav.item(_page_row(win, name))
    image = item.icon().pixmap(NAV_MARKS_WIDTH_PX, NAV_MARK_PX).toImage()
    return image.pixelColor(x, NAV_MARK_PX // 2)


def test_the_unsaved_dot_is_the_text_colour(window):
    from gui.settings.window import NAV_MARKS_WIDTH_PX
    from gui.theme_manager import get_theme_manager

    assert _mark_pixel(window, "General", NAV_MARKS_WIDTH_PX - 4).alpha() == 0
    window._select_page("General")
    window._web_host.bridge.edit("threshold", ["9"])
    dot = _mark_pixel(window, "General", NAV_MARKS_WIDTH_PX - 4)
    assert dot.name() == get_theme_manager().get_current_theme().text.lower()
    # The alert's place stays empty.
    assert _mark_pixel(window, "General", 1).alpha() == 0


def test_a_page_that_blocks_the_save_carries_the_alert(window):
    from PySide6.QtGui import QColor

    from gui.theme_manager import get_theme_manager

    window._select_page("General")
    window._web_host.bridge.edit("threshold", ["x"])
    item = window._settings_nav.item(_page_row(window, "General"))
    assert item.toolTip() == "Needs attention, Unsaved changes"
    assert item.data(Qt.ItemDataRole.AccessibleTextRole) == (
        "General, needs attention, unsaved changes"
    )
    danger = QColor(get_theme_manager().get_current_theme().status_danger)
    edge = _mark_pixel(window, "General", 1)
    assert edge.alpha() > 0
    assert abs(edge.red() - danger.red()) < 40

    window._web_host.bridge.edit("threshold", ["5"])
    assert item.toolTip() == ""
    assert _mark_pixel(window, "General", 1).alpha() == 0


def test_a_profile_that_opens_with_a_required_column_unmapped_is_marked(
    qapp, no_modals, started_workers, make_settings_config
):
    config = make_settings_config()
    del config["column_mappings"]["orders"]["Shipping Method"]
    win = SettingsWindow(client_id="M", client_config=config, profile_manager=Mock())
    assert win._blocked == {"Orders mapping": "Map Shipping method"}
    item = win._settings_nav.item(_page_row(win, "Orders mapping"))
    assert item.toolTip() == "Needs attention"
    assert win.refresh_dirty() == []
    win.deleteLater()


def test_the_dialog_has_no_margins_and_a_qt_page_keeps_its_own(window):
    from gui.settings.window import FOOTER_HEIGHT_PX, PAGE_MARGIN_PX

    margins = window.layout().contentsMargins()
    assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (
        0,
        0,
        0,
        0,
    )
    assert window._pages_by_name["Sets"].contentsMargins().left() == PAGE_MARGIN_PX
    assert window._web_host.contentsMargins().left() == 0
    assert window._footer.height() == FOOTER_HEIGHT_PX == 60
```


- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_settings_nav.py tests/test_ui_assets.py`

Expected: failures. The title, the row heights, the marks and `circle-alert.svg` are not there yet.

- [ ] **Step 3: Add the glyph**

Create `shared/assets/icons/circle-alert.svg` (Lucide 1.31.0, the tag `shared/assets/README.md` pins):

```xml
<svg
  xmlns="http://www.w3.org/2000/svg"
  width="24"
  height="24"
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="2"
  stroke-linecap="round"
  stroke-linejoin="round"
>
  <circle cx="12" cy="12" r="10" />
  <line x1="12" x2="12" y1="8" y2="12" />
  <line x1="12" x2="12.01" y1="16" y2="16" />
</svg>
```

- [ ] **Step 4: Restyle the frame**

In `gui/settings/window.py`, find exactly:

```python
from PySide6.QtCore import QRectF, QSettings, QSize, Qt, QThreadPool, QTimer
from PySide6.QtGui import QColor, QIcon, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
```

Replace with:

```python
from PySide6.QtCore import QRect, QRectF, QSettings, QSize, Qt, QThreadPool, QTimer
from PySide6.QtGui import QColor, QIcon, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStackedWidget,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)
```

In `gui/settings/window.py`, find exactly:

```python
from gui.worker import Worker
from shared.theme import font_css, on_theme_changed
```

Replace with:

```python
from gui.worker import Worker
from shared.icons import icon
from shared.theme import font_css, on_theme_changed
```

In `gui/settings/window.py`, find exactly:

```python
NAV_ICON_PX = 12
NAV_MIN_WIDTH_PX = 170
NAV_SEARCH_PLACEHOLDER = "Search settings"
# Clear button, frame and text margins the placeholder has to share the field with.
NAV_SEARCH_CHROME_PX = 44
UNSAVED_DOT_PX = 8
DIRTY_POLL_MS = 400
```

Replace with:

```python
# The mockup's nav (phase 7 spec section 6.2): a 232px column, 12px of air
# around a list of 30px rows.
NAV_MARGIN_PX = 12
NAV_MIN_WIDTH_PX = 208
NAV_ROW_PX = 30
NAV_GROUP_PX = 28
NAV_SEARCH_PLACEHOLDER = "Search settings"
# Clear button, frame and text margins the placeholder has to share the field with.
NAV_SEARCH_CHROME_PX = 44
# A row's marks sit at its right edge: the alert, then the unsaved dot.
NAV_MARK_PX = 14
NAV_MARKS_WIDTH_PX = 28
UNSAVED_DOT_PX = 7
FOOTER_HEIGHT_PX = 60
FOOTER_MARGIN_PX = 16
# The air around a Qt page. The web host sits flush: its page has its own.
PAGE_MARGIN_PX = 12
DIRTY_POLL_MS = 400
```

In `gui/settings/window.py`, find exactly:

```python
def unsaved_summary(names: list[str]) -> str:
```

Replace with:

```python
class _NavDelegate(QStyledItemDelegate):
    """Puts a nav row's marks at its right edge: the item's icon is drawn
    after the text, where the mockup has the unsaved dot."""

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.decorationPosition = QStyleOptionViewItem.Position.Right
        option.decorationAlignment = (
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )


def unsaved_summary(names: list[str]) -> str:
```

In `gui/settings/window.py`, find exactly:

```python
        self.setWindowTitle(f"Settings - CLIENT_{self.client_id}")
```

Replace with:

```python
        self.setWindowTitle(f"Client settings · {self.client_id}")
```

In `gui/settings/window.py`, find exactly:

```python
        main_layout = QVBoxLayout(self)
        content_layout = QHBoxLayout()
        main_layout.addLayout(content_layout)

        self._settings_nav = QListWidget()
        self._settings_nav.setObjectName("settingsNav")
        self._settings_nav.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._settings_nav.setIconSize(QSize(NAV_ICON_PX, NAV_ICON_PX))

        nav_column = QVBoxLayout()
        self._nav_search = QLineEdit()
```

Replace with:

```python
        # No margins of the dialog's own: the nav panel, the web host and the
        # footer each run to its edges, as the mockup's do.
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        main_layout.addLayout(content_layout, 1)

        self._settings_nav = QListWidget()
        self._settings_nav.setObjectName("settingsNav")
        self._settings_nav.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._settings_nav.setIconSize(QSize(NAV_MARKS_WIDTH_PX, NAV_MARK_PX))
        self._settings_nav.setItemDelegate(_NavDelegate(self._settings_nav))
        self._blocked: dict[str, str] = {}

        self._nav_panel = QFrame()
        self._nav_panel.setObjectName("settingsNavPanel")
        nav_column = QVBoxLayout(self._nav_panel)
        nav_column.setContentsMargins(
            NAV_MARGIN_PX, NAV_MARGIN_PX, NAV_MARGIN_PX, NAV_MARGIN_PX
        )
        nav_column.setSpacing(NAV_MARGIN_PX)
        self._nav_search = QLineEdit()
```

In `gui/settings/window.py`, find exactly:

```python
        # The column is as wide as the placeholder needs, never narrower than
        # the Phase 9 width. A hard 170 clipped "Search settings" under Segoe
        # UI, which is wider than the Linux dev font -- so measure, don't guess.
```

Replace with:

```python
        # The column is as wide as the placeholder needs, never narrower than
        # the mockup's. A hard 170 once clipped "Search settings" under Segoe
        # UI, which is wider than the Linux dev font -- so measure, don't guess.
```

In `gui/settings/window.py`, find exactly:

```python
        self._no_match_label = QLabel("No page matches")
        on_theme_changed(
            self._no_match_label,
            lambda tokens: self._no_match_label.setStyleSheet(
                f"{font_css('caption')} color: {tokens.text_secondary};"
            ),
        )
        self._no_match_label.hide()
        nav_column.addWidget(self._no_match_label)
        nav_column.addWidget(self._settings_nav, 1)
        content_layout.addLayout(nav_column)
```

Replace with:

```python
        self._no_match_label = QLabel("")
        self._no_match_label.setWordWrap(True)
        self._no_match_label.setFixedWidth(nav_width)
        on_theme_changed(
            self._no_match_label,
            lambda tokens: self._no_match_label.setStyleSheet(
                f"{font_css('body')} color: {tokens.text_secondary};"
            ),
        )
        self._no_match_label.hide()
        nav_column.addWidget(self._no_match_label)
        nav_column.addWidget(self._settings_nav, 1)
        content_layout.addWidget(self._nav_panel)
```

In `gui/settings/window.py`, find exactly:

```python
        page_column = QVBoxLayout()
        self._validation_message = InlineMessage()
        page_column.addWidget(self._validation_message)
```

Replace with:

```python
        page_column = QVBoxLayout()
        page_column.setContentsMargins(0, 0, 0, 0)
        page_column.setSpacing(0)
        self._validation_message = InlineMessage()
        self._validation_message.setContentsMargins(
            PAGE_MARGIN_PX, PAGE_MARGIN_PX, PAGE_MARGIN_PX, 0
        )
        page_column.addWidget(self._validation_message)
```

In `gui/settings/window.py`, find exactly:

```python
        self._footer = QWidget()
        footer_row = QHBoxLayout(self._footer)
        footer_row.setContentsMargins(0, 0, 0, 0)
        footer_row.addWidget(self._unsaved_label, 1)
        footer_row.addWidget(button_box)
        main_layout.addWidget(self._footer)
```

Replace with:

```python
        footer_rule = QFrame()
        footer_rule.setFixedHeight(1)
        on_theme_changed(
            footer_rule,
            lambda tokens: footer_rule.setStyleSheet(
                f"background-color: {tokens.border_subtle};"
            ),
        )
        main_layout.addWidget(footer_rule)

        self._footer = QWidget()
        self._footer.setFixedHeight(FOOTER_HEIGHT_PX)
        footer_row = QHBoxLayout(self._footer)
        footer_row.setContentsMargins(FOOTER_MARGIN_PX, 0, FOOTER_MARGIN_PX, 0)
        footer_row.addWidget(self._unsaved_label, 1)
        footer_row.addWidget(button_box)
        main_layout.addWidget(self._footer)
```

In `gui/settings/window.py`, find exactly:

```python
        self._close_guard = QWidget()
        guard_row = QHBoxLayout(self._close_guard)
        guard_row.setContentsMargins(0, 0, 0, 0)
```

Replace with:

```python
        self._close_guard = QWidget()
        self._close_guard.setFixedHeight(FOOTER_HEIGHT_PX)
        guard_row = QHBoxLayout(self._close_guard)
        guard_row.setContentsMargins(FOOTER_MARGIN_PX, 0, FOOTER_MARGIN_PX, 0)
```

In `gui/settings/window.py`, find exactly:

```python
        for page in self._pages:
            page.mark_clean()
        on_theme_changed(self._settings_nav, self._rebuild_nav_marks)
```

Replace with:

```python
        for page in self._pages:
            page.mark_clean()
        on_theme_changed(self._settings_nav, self._rebuild_nav_marks)
        # A profile can open with a required column already unmapped.
        self._refresh_status()
```

In `gui/settings/window.py`, find exactly:

```python
        widget = page if widget is None else widget
        self._pages.append(page)
```

Replace with:

```python
        if widget is None:
            widget = page
            widget.setContentsMargins(
                PAGE_MARGIN_PX, PAGE_MARGIN_PX, PAGE_MARGIN_PX, PAGE_MARGIN_PX
            )
        self._pages.append(page)
```

In `gui/settings/window.py`, find exactly:

```python
    def _on_web_edit(self) -> None:
        """A draft changed: its unsaved mark follows at once, with no poll."""
        changed = False
        for name in WEB_PAGE_KEYS:
            if self._pages_by_name[name].is_dirty() != (name in self._unsaved):
                self._unsaved ^= {name}
                changed = True
        if changed:
            self._render_unsaved()
```

Replace with:

```python
    def _on_web_edit(self) -> None:
        """A draft changed: its marks follow at once, with no poll."""
        self._refresh_status()

    def _refresh_status(self) -> None:
        """Re-check what an edit on a web page can change: the drafts' unsaved
        state, and what blocks the save. Both are cheap, so every edit runs it."""
        for name in WEB_PAGE_KEYS:
            if self._pages_by_name[name].is_dirty() != (name in self._unsaved):
                self._unsaved ^= {name}
        self._blocked = {
            name: blocker
            for name in self._nav_page_names()
            if (blocker := self._pages_by_name[name].blocker())
        }
        self._render_unsaved()
```

In `gui/settings/window.py`, find exactly:

```python
        for group_name, page_names in self.SETTINGS_NAV_GROUPS:
            header = QListWidgetItem(group_name)
            header.setFlags(Qt.ItemFlag.NoItemFlags)
            apply_font(header, "caption", bold=True)
            self._settings_nav.addItem(header)
            for page_name in page_names:
                item = QListWidgetItem(page_name)
```

Replace with:

```python
        for group_name, page_names in self.SETTINGS_NAV_GROUPS:
            header = QListWidgetItem(group_name)
            header.setFlags(Qt.ItemFlag.NoItemFlags)
            header.setSizeHint(QSize(0, NAV_GROUP_PX))
            header.setTextAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom
            )
            apply_font(header, "caption", bold=True)
            self._settings_nav.addItem(header)
            for page_name in page_names:
                item = QListWidgetItem(page_name)
                item.setSizeHint(QSize(0, NAV_ROW_PX))
```

In `gui/settings/window.py`, find exactly:

```python
        if header is not None:
            header.setHidden(not header_has_rows)
        self._no_match_label.setHidden(not query or bool(visible))
        return visible
```

Replace with:

```python
        if header is not None:
            header.setHidden(not header_has_rows)
        self._no_match_label.setText(f"No settings match “{text.strip()}”.")
        self._no_match_label.setHidden(not query or bool(visible))
        return visible
```

In `gui/settings/window.py`, find exactly:

```python
        if previous is not None:
            self._poll_page(previous.text())
```

Replace with:

```python
        if previous is not None:
            self._poll_page(previous.text())
        # The row that is open reads bold; a QSS ::item rule cannot set a weight.
        for item in (previous, current):
            if item is not None:
                font = item.font()
                font.setBold(item is current)
                item.setFont(font)
```

In `gui/settings/window.py`, find exactly:

```python
    def _rebuild_nav_marks(self, tokens) -> None:
        dot = QPixmap(NAV_ICON_PX, NAV_ICON_PX)
        dot.fill(Qt.GlobalColor.transparent)
        painter = QPainter(dot)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        # accent_fill: the colour of the Save button the page is waiting for.
        painter.setBrush(QColor(tokens.accent_fill))
        inset = (NAV_ICON_PX - UNSAVED_DOT_PX) / 2
        painter.drawEllipse(QRectF(inset, inset, UNSAVED_DOT_PX, UNSAVED_DOT_PX))
        painter.end()
        blank = QPixmap(NAV_ICON_PX, NAV_ICON_PX)
        blank.fill(Qt.GlobalColor.transparent)
        self._unsaved_icon = QIcon(dot)
        self._clean_icon = QIcon(blank)
        self._apply_nav_marks()

    def _apply_nav_marks(self) -> None:
        for item in self._page_items():
            unsaved = item.text() in self._unsaved
            item.setIcon(self._unsaved_icon if unsaved else self._clean_icon)
            item.setToolTip("Unsaved changes" if unsaved else "")
            item.setData(
                Qt.ItemDataRole.AccessibleTextRole,
                f"{item.text()}, unsaved changes" if unsaved else item.text(),
            )
```

Replace with:

```python
    def _rebuild_nav_marks(self, tokens) -> None:
        """One icon per combination of marks: (unsaved, blocked)."""
        alert = icon("circle-alert", tokens.status_danger)

        def marks(unsaved: bool, blocked: bool) -> QIcon:
            pixmap = QPixmap(NAV_MARKS_WIDTH_PX, NAV_MARK_PX)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            if blocked:
                alert.paint(painter, QRect(0, 0, NAV_MARK_PX, NAV_MARK_PX))
            if unsaved:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(tokens.text))
                painter.drawEllipse(
                    QRectF(
                        NAV_MARKS_WIDTH_PX - UNSAVED_DOT_PX,
                        (NAV_MARK_PX - UNSAVED_DOT_PX) / 2,
                        UNSAVED_DOT_PX,
                        UNSAVED_DOT_PX,
                    )
                )
            painter.end()
            result = QIcon(pixmap)
            # The same pixmap for a selected row: Qt would tint a missing one.
            result.addPixmap(pixmap, QIcon.Mode.Selected)
            return result

        self._marks = {
            (unsaved, blocked): marks(unsaved, blocked)
            for unsaved in (False, True)
            for blocked in (False, True)
        }
        self._apply_nav_marks()

    def _apply_nav_marks(self) -> None:
        for item in self._page_items():
            unsaved = item.text() in self._unsaved
            blocked = item.text() in self._blocked
            item.setIcon(self._marks[(unsaved, blocked)])
            notes = [
                note
                for note, on in (
                    ("Needs attention", blocked),
                    ("Unsaved changes", unsaved),
                )
                if on
            ]
            item.setToolTip(", ".join(notes))
            item.setData(
                Qt.ItemDataRole.AccessibleTextRole,
                ", ".join([item.text(), *(note.lower() for note in notes)]),
            )
```

In `gui/theme_manager.py`, find exactly:

```python
        QListWidget#settingsNav {{
            background-color: {theme.surface};
            border: none;
            border-right: 1px solid {theme.border_subtle};
            outline: none;
        }}
        QListWidget#settingsNav::item {{
            padding: 6px 10px;
            border-radius: {theme.radius}px;
            /* The generic QListWidget::item:selected ring is a `border`
               shorthand, so it wins on all four sides unless this rule
               restates them. This nav marks position, not data selection:
               the bar is left-only, and transparent here so selecting does
               not shift the text. */
            border: 2px solid transparent;
            border-left: 2px solid transparent;
        }}
        QListWidget#settingsNav::item:hover {{ background-color: {theme.hover}; }}
        QListWidget#settingsNav::item:selected {{
            background-color: {theme.selection_bg};
            color: {theme.text};
            border: 2px solid transparent;
            border-left: 2px solid {theme.accent_fill};
        }}
        QListWidget#settingsNav::item:disabled {{
            color: {theme.text_secondary};
            padding-top: 10px;
        }}
```

Replace with:

```python
        /* The settings nav, to the mockup (phase 7 spec section 6.2): a
           surface panel with a hairline on its right, and rows that mark
           position with a sunken fill and no bar. */
        QFrame#settingsNavPanel {{
            background-color: {theme.surface};
            border: none;
            border-right: 1px solid {theme.border_subtle};
        }}
        QListWidget#settingsNav {{
            background-color: transparent;
            border: none;
            outline: none;
        }}
        QListWidget#settingsNav::item {{
            padding: 0px 8px;
            border-radius: 8px;
            color: {theme.text_secondary};
            /* The generic QListWidget::item:selected ring is a `border`
               shorthand, so it wins on all four sides unless this rule
               restates them. Transparent here and when selected, so
               selecting does not shift the text. */
            border: 2px solid transparent;
        }}
        QListWidget#settingsNav::item:hover {{ background-color: {theme.hover}; }}
        QListWidget#settingsNav::item:selected {{
            background-color: {theme.surface_sunken};
            color: {theme.text};
            border: 2px solid transparent;
        }}
        QListWidget#settingsNav::item:disabled {{
            background-color: transparent;
            color: {theme.text_secondary};
            padding: 0px 8px 4px 8px;
        }}
```


- [ ] **Step 5: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_settings_nav.py tests/test_ui_assets.py tests/test_settings_unsaved.py tests/test_settings_roundtrip.py tests/test_settings_button_roles.py tests/test_theme_button_roles.py tests/test_theme_manager_button_roles.py tests/test_icon_usage_guard.py tests/test_style_literals_guard.py`

Expected: all pass.

- [ ] **Step 6: Lint and commit**

Run: `.venv/bin/ruff check .` Expected: `All checks passed!`

Stage `shared/assets/icons/circle-alert.svg gui/settings/window.py gui/theme_manager.py
tests/test_settings_nav.py tests/test_ui_assets.py` and commit. Message subject:
`Settings: the nav, its marks and the dialog's layout to the mockup`.

---

### Task 12: The footer and Save

One status line, Save live only when a page is unsaved and nothing blocks, and a dialog that stays open
after a save (spec §6.3, §6.4).

**Files:**
- Modify: `gui/settings/window.py`, `gui/settings/contract.py`, `gui/actions_handler.py`
- Test: `tests/test_settings_footer.py` (new), `tests/test_settings_unsaved.py`,
  `tests/test_settings_roundtrip.py`, `tests/test_settings_page_contract.py`

**Interfaces:**
- Consumes: `_blocked`, `_refresh_status()` (Task 11); `SettingsWebHost.focus_problem` (Task 9);
  `PageContract.blocker_key()` (Task 3).
- Produces:
  - `PageContract.mark_clean(snapshot: str | None = None)` and `PageContract.current_snapshot() -> str`;
  - `gui.settings.window.SAVED_LINE`; `unsaved_summary(names)` returns `"Unsaved changes in A, B"`;
  - on `SettingsWindow`: `cancel_button`, `_status_icon`, `_render_footer()`, `_open_blocker(name)`,
    `_save_shortcut()`, `_finish()`, `save_settings(then_close: bool = False)`. The dialog's result is
    `Accepted` when it saved at least once, whatever closed it.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_settings_footer.py`:

```python
"""The settings footer, Save and closing (phase 7 spec sections 6.3 and 6.4).

Fixtures (window, started_workers, no_modals, make_settings_config) come from
conftest.py. A web page is edited through the host's bridge, as the page does.
"""

from unittest.mock import Mock

from PySide6.QtWidgets import QDialog

from gui.settings.window import SAVED_LINE, SettingsWindow


def _edit_sets(win):
    win._pages_by_name["Sets"].set_decoders["SET-NEW"] = [{"sku": "A", "quantity": 1}]


def _edit_general(win, text="9"):
    win._select_page("General")
    win._web_host.bridge.edit("threshold", [text])


def _results(win):
    seen = []
    win.finished.connect(seen.append)
    return seen


# --- the status line ---------------------------------------------------------


def test_a_fresh_window_says_nothing_and_cannot_save(window):
    assert window._unsaved_label.text() == ""
    assert window._status_icon.isHidden()
    assert not window.save_button.isEnabled()
    assert window.cancel_button.text() == "Cancel"
    assert window.save_button.toolTip() == "Ctrl+S"


def test_an_unsaved_page_is_named_and_makes_save_live(window):
    _edit_general(window)
    assert window._unsaved_label.text() == "Unsaved changes in General"
    assert not window._status_icon.isHidden()
    assert window.save_button.isEnabled()


def test_every_unsaved_page_is_named_in_nav_order(window):
    _edit_sets(window)
    _edit_general(window)
    window.refresh_dirty()
    assert window._unsaved_label.text() == "Unsaved changes in General, Sets"


def test_undoing_the_edit_empties_the_line_and_disables_save(window):
    _edit_general(window)
    _edit_general(window, "5")
    assert window._unsaved_label.text() == ""
    assert not window.save_button.isEnabled()


def test_a_blocker_takes_the_line_and_disables_save(window):
    _edit_general(window, "x")
    text = window._unsaved_label.text()
    assert text.startswith('Set Low-stock threshold in <a href="General"')
    assert text.endswith(">General</a> to save.")
    assert not window.save_button.isEnabled()
    assert not window.save_and_close_button.isEnabled()

    _edit_general(window, "7")
    assert window._unsaved_label.text() == "Unsaved changes in General"
    assert window.save_button.isEnabled()
    assert window.save_and_close_button.isEnabled()


def test_the_first_blocked_page_in_nav_order_is_the_one_named(
    qapp, no_modals, started_workers, make_settings_config
):
    config = make_settings_config()
    del config["column_mappings"]["orders"]["Shipping Method"]
    win = SettingsWindow(client_id="M", client_config=config, profile_manager=Mock())
    assert "Map Shipping method in" in win._unsaved_label.text()
    assert ">Orders mapping</a>" in win._unsaved_label.text()
    _edit_general(win, "x")
    assert ">General</a>" in win._unsaved_label.text()
    win.deleteLater()


def test_the_lines_link_opens_the_page_and_points_at_the_control(window):
    window._web_host.drafts["general"].apply("threshold", ["x"])
    window._refresh_status()
    window._select_page("Sets")
    asked = []
    window._web_host.bridge.problemFocusRequested.connect(asked.append)

    window._unsaved_label.linkActivated.emit("General")

    assert window._settings_nav.currentItem().text() == "General"
    assert asked == ["threshold"]


def test_a_link_to_no_page_does_nothing(window):
    window._unsaved_label.linkActivated.emit("Nope")
    assert window._settings_nav.currentItem().text() == "General"


# --- Save --------------------------------------------------------------------


def test_save_writes_a_copy_and_the_dialog_stays_open(window, started_workers):
    results = _results(window)
    _edit_general(window)

    window.save_button.click()

    assert len(started_workers) == 1
    assert window.save_button.text() == "Saving…"
    assert not window.save_button.isEnabled()
    written = started_workers[0].args[1]
    assert written == window.config_data
    assert written is not window.config_data
    assert written["settings"]["low_stock_threshold"] == 9

    window._on_save_settings_result(True)

    assert results == []
    assert window._unsaved_label.text() == SAVED_LINE
    assert window.save_button.text() == "Save"
    assert not window.save_button.isEnabled()
    assert window.cancel_button.text() == "Close"
    assert window.refresh_dirty() == []
    assert window._settings_nav.currentItem().toolTip() == ""


def test_an_edit_after_a_save_brings_the_unsaved_line_and_cancel_back(window):
    _edit_general(window)
    window.save_settings()
    window._on_save_settings_result(True)

    _edit_general(window, "11")

    assert window._unsaved_label.text() == "Unsaved changes in General"
    assert window.cancel_button.text() == "Cancel"
    assert window.save_button.isEnabled()
    # Undoing it does not bring "Saved" back: that line is the save's own.
    _edit_general(window, "9")
    assert window._unsaved_label.text() == ""


def test_an_edit_made_while_the_write_runs_stays_unsaved(window, started_workers):
    _edit_general(window)
    window.save_settings()
    _edit_general(window, "12")

    window._on_save_settings_result(True)

    assert started_workers[0].args[1]["settings"]["low_stock_threshold"] == 9
    assert window.refresh_dirty() == ["General"]
    assert window._unsaved_label.text() == "Unsaved changes in General"
    assert window.save_button.isEnabled()


def test_a_failed_write_leaves_the_page_unsaved_and_save_live(window, monkeypatch):
    monkeypatch.setattr("gui.settings.window.show_error", lambda *a: None)
    _edit_general(window)
    window.save_settings()

    window._on_save_settings_result(False)

    assert window._unsaved_label.text() == "Unsaved changes in General"
    assert window.save_button.isEnabled()
    assert window.save_button.text() == "Save"


def test_a_crashed_write_leaves_save_live(window, monkeypatch):
    monkeypatch.setattr("gui.settings.window.show_error", lambda *a: None)
    _edit_general(window)
    window.save_settings()
    window._on_save_settings_error((ValueError, ValueError("disk"), "tb"))
    assert window.save_button.isEnabled()
    assert window.save_button.text() == "Save"


def test_ctrl_s_saves_an_edit_the_poll_has_not_seen(window, started_workers):
    _edit_sets(window)
    assert not window.save_button.isEnabled()
    window._save_shortcut()
    assert len(started_workers) == 1


def test_ctrl_s_does_nothing_with_nothing_to_save_or_a_blocker(window, started_workers):
    window._save_shortcut()
    _edit_general(window, "x")
    window._save_shortcut()
    assert started_workers == []


# --- closing -----------------------------------------------------------------


def test_closing_without_a_save_is_rejected(window):
    results = _results(window)
    window.reject()
    assert results == [QDialog.DialogCode.Rejected]


def test_closing_after_a_save_is_accepted(window):
    results = _results(window)
    _edit_general(window)
    window.save_settings()
    window._on_save_settings_result(True)

    window.reject()

    assert results == [QDialog.DialogCode.Accepted]


def test_discarding_later_edits_after_a_save_is_still_accepted(window):
    """The main window reloads the profile on Accepted: one save is enough."""
    results = _results(window)
    _edit_general(window)
    window.save_settings()
    window._on_save_settings_result(True)
    _edit_general(window, "12")

    window.reject()
    assert results == []
    window.discard_button.click()

    assert results == [QDialog.DialogCode.Accepted]


def test_save_and_close_closes_once_the_write_succeeds(window, started_workers):
    results = _results(window)
    _edit_sets(window)
    window.reject()
    window.save_and_close_button.click()
    assert len(started_workers) == 1
    assert results == []

    window._on_save_settings_result(True)

    assert results == [QDialog.DialogCode.Accepted]


def test_save_and_close_stays_open_when_the_write_fails(window, monkeypatch):
    monkeypatch.setattr("gui.settings.window.show_error", lambda *a: None)
    results = _results(window)
    _edit_sets(window)
    window.reject()
    window.save_and_close_button.click()
    window._on_save_settings_result(False)
    assert results == []

    # A plain Save afterwards does not inherit the close.
    window.save_settings()
    window._on_save_settings_result(True)
    assert results == []


def test_nothing_closes_the_dialog_while_a_write_runs(window):
    results = _results(window)
    _edit_general(window)
    window.save_settings()
    window.reject()
    assert results == []
```

In `tests/test_settings_page_contract.py`, append at the end of the file:

```python


def test_mark_clean_can_take_an_earlier_snapshot():
    """What a save wrote is what is clean, not what is on screen when it ends."""
    draft = _OneValueDraft()
    draft.mark_clean()
    draft.value = 2
    written = draft.current_snapshot()
    draft.value = 3
    draft.mark_clean(written)
    assert draft.is_dirty() is True
    draft.value = 2
    assert draft.is_dirty() is False
```

In `tests/test_settings_unsaved.py`, find exactly:

```python
def test_unsaved_summary_names_up_to_two_pages():
    assert unsaved_summary([]) == ""
    assert unsaved_summary(["Sets"]) == "Unsaved changes on Sets"
    assert unsaved_summary(["Sets", "Reports"]) == "Unsaved changes on Sets and Reports"
    assert (
        unsaved_summary(["General", "Sets", "Reports"]) == "Unsaved changes on 3 pages"
    )
```

Replace with:

```python
def test_unsaved_summary_names_every_page():
    assert unsaved_summary([]) == ""
    assert unsaved_summary(["Sets"]) == "Unsaved changes in Sets"
    assert unsaved_summary(["General", "Sets", "Reports"]) == (
        "Unsaved changes in General, Sets, Reports"
    )
```

In `tests/test_settings_unsaved.py`, replace every `"Unsaved changes on Sets"` with `"Unsaved changes in Sets"` (Edit with `replace_all`).

In `tests/test_settings_unsaved.py`, find exactly:

```python
        "Unsaved changes on Sets. Closing now discards them."
```

Replace with:

```python
        "Unsaved changes in Sets. Closing now discards them."
```

In `tests/test_settings_roundtrip.py`, find exactly:

```python
def test_a_successful_save_toasts_on_the_parent_and_closes(window, monkeypatch):
    toasts = []
    monkeypatch.setattr(
        "gui.settings.window.toast", lambda source, text, **k: toasts.append(text)
    )
    accepted = []
    window.accepted.connect(lambda: accepted.append(True))

    window._on_save_settings_result(True)

    assert toasts == ["Settings saved"]
    assert accepted == [True]
```

Replace with:

```python
def test_a_successful_save_says_so_in_the_footer_and_stays_open(window):
    closed = []
    window.finished.connect(closed.append)

    window.save_settings()
    window._on_save_settings_result(True)

    assert closed == []
    assert window._unsaved_label.text() == "Saved. Applies from the next analysis."
```

In `tests/test_settings_roundtrip.py`, find exactly:

```python
    assert accepted == []
    assert window.save_button.isEnabled()
```

Replace with:

```python
    assert accepted == []
    assert window.save_button.text() == "Save"
```


- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_settings_footer.py tests/test_settings_unsaved.py tests/test_settings_roundtrip.py tests/test_settings_page_contract.py`

Expected: an error at collection for the new file, `ImportError: cannot import name 'SAVED_LINE'`, and
failures in the others that name the old wording (`'Unsaved changes on Sets'`).

- [ ] **Step 3: Write the footer and Save**

In `gui/settings/contract.py`, find exactly:

```python
    def mark_clean(self) -> None:
        """Take the current values as the ones the page opened with."""
        self._clean_snapshot = self._safe_snapshot()
```

Replace with:

```python
    def mark_clean(self, snapshot: str | None = None) -> None:
        """Take the current values as the ones the page opened with.

        After a save the window passes the snapshot it took when the write
        began, so an edit made while the write ran still reads unsaved.
        """
        self._clean_snapshot = self._safe_snapshot() if snapshot is None else snapshot

    def current_snapshot(self) -> str:
        """The values right now, for mark_clean() to take later."""
        return self._safe_snapshot()
```

In `gui/settings/window.py`, find exactly:

```python
import json
import logging
```

Replace with:

```python
import html
import json
import logging
```

In `gui/settings/window.py`, find exactly:

```python
from gui.components import toast
from gui.components.error_banner import show_error
```

Replace with:

```python
from gui.components.error_banner import show_error
```

In `gui/settings/window.py`, find exactly:

```python
from shared.theme import font_css, on_theme_changed
```

Replace with:

```python
from shared.theme import current_tokens, font_css, on_theme_changed
```

In `gui/settings/window.py`, find exactly:

```python
FOOTER_HEIGHT_PX = 60
FOOTER_MARGIN_PX = 16
```

Replace with:

```python
FOOTER_HEIGHT_PX = 60
FOOTER_MARGIN_PX = 16
FOOTER_ICON_PX = 16
SAVED_LINE = "Saved. Applies from the next analysis."
```

In `gui/settings/window.py`, find exactly:

```python
def unsaved_summary(names: list[str]) -> str:
    """Footer copy for the unsaved pages, given in nav order."""
    if not names:
        return ""
    if len(names) == 1:
        return f"Unsaved changes on {names[0]}"
    if len(names) == 2:
        return f"Unsaved changes on {names[0]} and {names[1]}"
    return f"Unsaved changes on {len(names)} pages"
```

Replace with:

```python
def unsaved_summary(names: list[str]) -> str:
    """Footer copy for the unsaved pages, given in nav order."""
    return f"Unsaved changes in {', '.join(names)}" if names else ""
```

In `gui/settings/window.py`, find exactly:

```python
        self._save_worker = None  # keeps the in-flight save Worker alive
        self._is_saving = False
```

Replace with:

```python
        self._save_worker = None  # keeps the in-flight save Worker alive
        self._is_saving = False
        self._saved = False  # the last save's line is still what the footer says
        self._saved_once = False  # decides the dialog's result when it closes
        self._close_after_save = False
        self._written_snapshots: list[tuple[PageContract, str]] = []
```

In `gui/settings/window.py`, find exactly:

```python
        button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.save_button = button_box.button(QDialogButtonBox.Save)
        apply_dialog_button_roles(button_box)
        set_button_role(button_box.button(QDialogButtonBox.Cancel), "secondary")
        button_box.accepted.connect(self.save_settings)
        button_box.rejected.connect(self.reject)

        self._unsaved_label = QLabel("")
        on_theme_changed(
            self._unsaved_label,
            lambda tokens: self._unsaved_label.setStyleSheet(
                f"{font_css('body')} color: {tokens.text_secondary};"
            ),
        )
```

Replace with:

```python
        button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.save_button = button_box.button(QDialogButtonBox.Save)
        self.save_button.setToolTip("Ctrl+S")
        self.cancel_button = button_box.button(QDialogButtonBox.Cancel)
        apply_dialog_button_roles(button_box)
        set_button_role(self.cancel_button, "secondary")
        button_box.accepted.connect(self.save_settings)
        button_box.rejected.connect(self.reject)

        # The footer's one status line (phase 7 spec section 6.3): what blocks
        # the save, else the unsaved pages, else the last save. A glyph before it.
        self._status_icon = QLabel()
        self._status_icon.setFixedSize(FOOTER_ICON_PX, FOOTER_ICON_PX)
        self._unsaved_label = QLabel("")
        self._unsaved_label.setTextFormat(Qt.TextFormat.RichText)
        self._unsaved_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.LinksAccessibleByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByKeyboard
        )
        self._unsaved_label.linkActivated.connect(self._open_blocker)
```

In `gui/settings/window.py`, find exactly:

```python
        footer_row.setContentsMargins(FOOTER_MARGIN_PX, 0, FOOTER_MARGIN_PX, 0)
        footer_row.addWidget(self._unsaved_label, 1)
        footer_row.addWidget(button_box)
```

Replace with:

```python
        footer_row.setContentsMargins(FOOTER_MARGIN_PX, 0, FOOTER_MARGIN_PX, 0)
        footer_row.addWidget(self._status_icon)
        footer_row.addWidget(self._unsaved_label, 1)
        footer_row.addWidget(button_box)
```

In `gui/settings/window.py`, find exactly:

```python
        self.save_and_close_button.clicked.connect(self.save_settings)
```

Replace with:

```python
        self.save_and_close_button.clicked.connect(
            lambda: self.save_settings(then_close=True)
        )
```

In `gui/settings/window.py`, find exactly:

```python
        on_theme_changed(self._settings_nav, self._rebuild_nav_marks)
        # A profile can open with a required column already unmapped.
        self._refresh_status()
```

Replace with:

```python
        on_theme_changed(self._settings_nav, self._rebuild_nav_marks)
        on_theme_changed(self._unsaved_label, lambda _tokens: self._render_footer())
        QShortcut(QKeySequence(QKeySequence.StandardKey.Save), self).activated.connect(
            self._save_shortcut
        )
        # A profile can open with a required column already unmapped.
        self._refresh_status()
```

In `gui/settings/window.py`, find exactly:

```python
        for name in WEB_PAGE_KEYS:
            if self._pages_by_name[name].is_dirty() != (name in self._unsaved):
                self._unsaved ^= {name}
        self._blocked = {
            name: blocker
            for name in self._nav_page_names()
            if (blocker := self._pages_by_name[name].blocker())
        }
        self._render_unsaved()
```

Replace with:

```python
        for name in WEB_PAGE_KEYS:
            if self._pages_by_name[name].is_dirty() != (name in self._unsaved):
                self._unsaved ^= {name}
        self._check_blockers()
        self._render_unsaved()

    def _check_blockers(self) -> None:
        self._blocked = {
            name: blocker
            for name in self._nav_page_names()
            if (blocker := self._pages_by_name[name].blocker())
        }
```

In `gui/settings/window.py`, find exactly:

```python
        self._unsaved = {
            name for name, page in self._pages_by_name.items() if page.is_dirty()
        }
        self._render_unsaved()
        return self._unsaved_names()
```

Replace with:

```python
        self._unsaved = {
            name for name, page in self._pages_by_name.items() if page.is_dirty()
        }
        self._check_blockers()
        self._render_unsaved()
        return self._unsaved_names()
```

In `gui/settings/window.py`, find exactly:

```python
    def _render_unsaved(self) -> None:
        names = self._unsaved_names()
        summary = unsaved_summary(names)
        self._unsaved_label.setText(summary)
        self._close_guard_label.setText(
            f"{summary}. Closing now discards them." if names else ""
        )
        self._apply_nav_marks()
```

Replace with:

```python
    def _render_unsaved(self) -> None:
        names = self._unsaved_names()
        if names:
            # An edit after a save: the footer goes back to naming it.
            self._saved = False
        summary = unsaved_summary(names)
        self._close_guard_label.setText(
            f"{summary}. Closing now discards them." if names else ""
        )
        self._apply_nav_marks()
        self._render_footer()

    def _render_footer(self) -> None:
        """The status line, its glyph, and which buttons are live.

        The first that applies: a blocker, the unsaved pages, the last save.
        Save is live only with unsaved pages and no blocker.
        """
        tokens = current_tokens()
        names = self._unsaved_names()
        size = FOOTER_ICON_PX
        pixmap, bold = None, False
        if self._blocked:
            name = next(n for n in self._nav_page_names() if n in self._blocked)
            link = (
                f'<a href="{html.escape(name)}" style="color: {tokens.status_danger};'
                f' font-weight: bold;">{html.escape(name)}</a>'
            )
            text = f"{html.escape(self._blocked[name])} in {link} to save."
            color = tokens.status_danger
            pixmap = icon("circle-alert", tokens.status_danger).pixmap(size, size)
        elif names:
            text = html.escape(unsaved_summary(names))
            color = tokens.text_secondary
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(tokens.text))
            inset = (size - UNSAVED_DOT_PX) / 2
            painter.drawEllipse(QRectF(inset, inset, UNSAVED_DOT_PX, UNSAVED_DOT_PX))
            painter.end()
        elif self._saved:
            text, color, bold = SAVED_LINE, tokens.status_success, True
            pixmap = icon("check", tokens.status_success).pixmap(size, size)
        else:
            text, color = "", tokens.text_secondary
        self._unsaved_label.setText(text)
        self._unsaved_label.setStyleSheet(
            f"{font_css('body', bold=bold)} color: {color};"
        )
        self._status_icon.setVisible(pixmap is not None)
        if pixmap is not None:
            self._status_icon.setPixmap(pixmap)

        can_save = bool(names) and not self._blocked and not self._is_saving
        self.save_button.setEnabled(can_save)
        self.save_and_close_button.setEnabled(not self._blocked)
        self.cancel_button.setText("Close" if self._saved and not names else "Cancel")

    def _open_blocker(self, name: str) -> None:
        """The status line's link: the page that blocks the save, and on a web
        page the control itself."""
        page = self._pages_by_name.get(name)
        if page is None:
            return
        self._select_page(name)
        if name in WEB_PAGE_KEYS and page.blocker_key():
            self._web_host.focus_problem(page.blocker_key())

    def _save_shortcut(self) -> None:
        # The visible Qt page is polled every 400ms: check every page now, so
        # Ctrl+S cannot outrun the poll.
        self.refresh_dirty()
        if self.save_button.isEnabled():
            self.save_settings()
```

In `gui/settings/window.py`, find exactly:

```python
        if self.refresh_dirty():
            self._show_close_guard()
            return
        super().reject()
```

Replace with:

```python
        if self.refresh_dirty():
            self._show_close_guard()
            return
        self._finish()

    def _finish(self) -> None:
        """Close. The result says whether anything was saved while the dialog
        was open, which is what the main window reloads the profile on."""
        self.done(
            QDialog.DialogCode.Accepted
            if self._saved_once
            else QDialog.DialogCode.Rejected
        )
```

In `gui/settings/window.py`, find exactly:

```python
    def _discard(self) -> None:
        self._hide_close_guard()
        super().reject()
```

Replace with:

```python
    def _discard(self) -> None:
        self._hide_close_guard()
        self._finish()
```

In `gui/settings/window.py`, find exactly:

```python
    def save_settings(self):
        """Validate every page, collect them all, and write the profile once.

        Save always writes, even when no page reads unsaved: the unsaved state
        drives warnings only, so a snapshot that misses a field costs a
        warning, never an edit.
        """
        self._hide_close_guard()
        self._validation_message.clear()
        for name in self._nav_page_names():
            ok, errors = self._pages_by_name[name].validate()
            if not ok:
                self._select_page(name)
                self._validation_message.show_message("\n".join(errors))
                return

        try:
            for page in self._pages:
                for key, value in page.collect().items():
                    self.config_data[key] = value
        except Exception:
            logger.exception("Failed to collect settings")
            show_error(
                self,
                "Settings weren't saved",
                "A value couldn't be read. Details are in Logs.",
            )
            return

        # Save to server via ProfileManager (background -- avoids blocking the
        # GUI thread on the lock-contention retry sleep)
        self.save_button.setEnabled(False)
        self.save_button.setText("Saving...")
        self._is_saving = True

        worker = Worker(
            self.profile_manager.save_shopify_config, self.client_id, self.config_data
        )
```

Replace with:

```python
    def save_settings(self, then_close: bool = False):
        """Validate every page, collect them all, and write the profile once.

        Every page is written, whichever of them reads unsaved: the unsaved
        state decides whether Save is live, never what a save contains. The
        dialog stays open afterwards, unless `then_close` (the close guard's
        Save & close).
        """
        self._close_after_save = False
        self._hide_close_guard()
        self._validation_message.clear()
        for name in self._nav_page_names():
            ok, errors = self._pages_by_name[name].validate()
            if not ok:
                self._select_page(name)
                self._validation_message.show_message("\n".join(errors))
                return

        try:
            for page in self._pages:
                for key, value in page.collect().items():
                    self.config_data[key] = value
            # A copy: the dialog stays usable while the write runs, and an
            # edit made meanwhile must not change what is written.
            written = json.loads(json.dumps(self.config_data))
        except Exception:
            logger.exception("Failed to collect settings")
            show_error(
                self,
                "Settings weren't saved",
                "A value couldn't be read. Details are in Logs.",
            )
            return

        # What is clean once this write succeeds: the values it carries, not
        # the ones on screen when it ends.
        self._written_snapshots = [
            (page, page.current_snapshot()) for page in self._pages
        ]
        self._close_after_save = then_close

        # Save to server via ProfileManager (background -- avoids blocking the
        # GUI thread on the lock-contention retry sleep)
        self._is_saving = True
        self.save_button.setText("Saving…")
        self._render_footer()

        worker = Worker(
            self.profile_manager.save_shopify_config, self.client_id, written
        )
```

In `gui/settings/window.py`, find exactly:

```python
    def _on_save_settings_result(self, success: bool):
        self._is_saving = False
        self.save_button.setEnabled(True)
        self.save_button.setText("Save")
        if success:
            # Raised on the parent: this dialog is about to close.
            toast(self.parentWidget() or self, "Settings saved")
            self.accept()
        else:
            show_error(
                self,
                "Settings weren't saved",
                "The profile may be open on another PC, or the server can't be reached. "
                "Wait a few seconds, then press Save again.",
            )

    def _on_save_settings_error(self, error):
        _exctype, value, _tb = error
        logger.error("Failed to save settings", exc_info=value)
        self._is_saving = False
        self.save_button.setEnabled(True)
        self.save_button.setText("Save")
        show_error(self, "Settings weren't saved", "Details are in Logs.")
```

Replace with:

```python
    def _on_save_settings_result(self, success: bool):
        self._is_saving = False
        self.save_button.setText("Save")
        if success:
            for page, snapshot in self._written_snapshots:
                page.mark_clean(snapshot)
            self._saved = True
            self._saved_once = True
            # Re-reads every page: one edited while the write ran is unsaved.
            self.refresh_dirty()
            if self._close_after_save:
                self._finish()
        else:
            self._close_after_save = False
            self._render_footer()
            show_error(
                self,
                "Settings weren't saved",
                "The profile may be open on another PC, or the server can't be reached. "
                "Wait a few seconds, then press Save again.",
            )

    def _on_save_settings_error(self, error):
        _exctype, value, _tb = error
        logger.error("Failed to save settings", exc_info=value)
        self._is_saving = False
        self._close_after_save = False
        self.save_button.setText("Save")
        self._render_footer()
        show_error(self, "Settings weren't saved", "Details are in Logs.")
```

In `gui/actions_handler.py`, find exactly:

```python
            # The window has already toasted "Settings saved".
```

Replace with:

```python
            # It saved at least once while it was open; its footer said so.
```


- [ ] **Step 4: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_settings_footer.py tests/test_settings_unsaved.py tests/test_settings_roundtrip.py tests/test_settings_page_contract.py tests/test_settings_nav.py tests/test_settings_button_roles.py tests/test_settings_window_weight_quick_add.py tests/test_actions_handler.py`

Expected: all pass.

- [ ] **Step 5: Lint and commit**

Run: `.venv/bin/ruff check .` Expected: `All checks passed!`

Stage `gui/settings/window.py gui/settings/contract.py gui/actions_handler.py` and the four test files and
commit. Message subject: `Settings: one status line, and a Save that stays open`.

---

### Task 13: Renders, docs and the gate

**Files:**
- Create: PNGs under `docs/design/ui-refresh/renders/phase7/`
- Modify: `docs/design/ui-refresh/roadmap.md`, `docs/adr/0016-the-web-tier-grows-screen-by-screen.md`,
  `CONTEXT.md`

- [ ] **Step 1: Render the dialog and look at it**

Write this throwaway script as `<your tmp dir>/render_settings.py`:

```python
"""Throwaway: render the Client settings dialog in its phase 7 states.

    QT_QPA_PLATFORM=offscreen PYTHONPATH=. .venv/bin/python render_settings.py <out dir>
"""

import copy
import os
import sys
from pathlib import Path
from unittest.mock import Mock

os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")

from PySide6.QtCore import QEventLoop, QThreadPool, QTimer
from PySide6.QtWidgets import QApplication

from gui.settings.window import SettingsWindow
from gui.theme_manager import get_theme_manager

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)

CONFIG = {
    "settings": {
        "stock_csv_delimiter": "auto",
        "orders_csv_delimiter": ";",
        "low_stock_threshold": 5,
    },
    "rules": [],
    "packing_list_configs": [],
    "stock_export_configs": [],
    "column_mappings": {
        "version": 2,
        "orders": {
            "Name": "Order_Number",
            "Lineitem sku": "SKU",
            "Lineitem quantity": "Quantity",
            "Shipping Method": "Shipping_Method",
            "Lineitem name": "Product_Name",
            "Shipping Country": "Shipping_Country",
            "Tags": "Tags",
            "Old Notes": "Notes",
            "Total": "Total_Price",
            "Shipping Name": "Customer",
            "Created at": "Created_At",
        },
        "stock": {
            "Артикул": "SKU",
            "Наличност": "Stock",
            "Име": "Product_Name",
            "Годност": "Expiry_Date",
        },
        "additional_columns": [
            {
                "csv_name": "Discount Code",
                "internal_name": "Discount_Code",
                "enabled": True,
                "is_order_level": True,
                "exists_in_df": True,
            },
            {
                "csv_name": "Gift Note",
                "internal_name": "Gift_Note",
                "enabled": True,
                "is_order_level": False,
                "exists_in_df": True,
            },
        ],
    },
    "courier_mappings": {
        "DHL": {"patterns": ["dhl", "dhl express"], "case_sensitive": False},
        "DPD": {"patterns": ["dpd"], "case_sensitive": False},
        "Speedy": {"patterns": ["speedy"], "case_sensitive": False},
    },
    "set_decoders": {},
    "weight_config": {"volumetric_divisor": 5000, "products": {}, "boxes": []},
    "tag_categories": {"version": 2, "categories": {}},
}

ORDERS_CSV = (
    "Name,Lineitem sku,Lineitem quantity,Shipping Method,Lineitem name,"
    "Shipping Country,Tags,Total,Shipping Name,Created at,Discount Code,Shipping Phone\n"
    "#10482,ACM-TEE-BLK-M,2,DHL Express Worldwide,\"Tee, black, M\",GB,\"VIP, repeat\","
    "48.00,Jana Novak,2026-09-29 18:04,AUTUMN10,+44 20 7946 0958\n"
)
STOCK_CSV = "Артикул;Наличност;Име;Годност;Партида\nACM-TEE-BLK-M;42;Tee, black, M;270930;L-2409\n"


def settle(ms=500):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def window(files, config=None):
    profile_manager = Mock()
    profile_manager.load_client_config.return_value = {}
    win = SettingsWindow(
        client_id="ACME",
        client_config=copy.deepcopy(config or CONFIG),
        profile_manager=profile_manager,
        loaded_files=files,
    )
    win.resize(1180, 712)
    win.show()
    settle(1500)
    return win


def shot(win, name, theme):
    settle()
    win.grab().save(str(OUT / f"{theme}-{name}.png"))


def edit(win, action, args):
    win._web_host.bridge.edit(action, args)


app = QApplication(sys.argv)
orders = OUT / "acme-orders-30-09.csv"
orders.write_text(ORDERS_CSV, encoding="utf-8")
stock = OUT / "acme-stock-30-09.csv"
stock.write_text(STOCK_CSV, encoding="utf-8")
files = {"orders": str(orders), "stock": str(stock)}

missing = copy.deepcopy(CONFIG)
del missing["column_mappings"]["orders"]["Shipping Method"]

manager = get_theme_manager()
started_as = manager.get_current_theme_name()
for theme in ("light", "dark"):
    manager.set_theme(theme)
    # set_theme does nothing when the theme is already the current one, and
    # only apply_theme puts the app's stylesheet on a bare QApplication.
    manager.apply_theme()

    win = window(files)
    win._select_page("General")
    shot(win, "general", theme)
    edit(win, "delimiter", ["stock", "other"])
    edit(win, "delimiter_char", ["stock", "|"])
    win._pages_by_name["Sets"].set_decoders["SET-1"] = [{"sku": "A", "quantity": 1}]
    win.refresh_dirty()
    shot(win, "general-unsaved", theme)
    win.save_settings()
    QThreadPool.globalInstance().waitForDone()
    settle()
    shot(win, "general-saved", theme)
    win._select_page("Orders mapping")
    shot(win, "orders", theme)
    win._web_host.view.page().runJavaScript(
        "document.getElementById('settings').scrollTop = 100000;"
    )
    shot(win, "orders-lower", theme)
    win._select_page("Stock mapping")
    shot(win, "stock", theme)
    win._select_page("Rules")
    shot(win, "rules-qt", theme)
    win.done(0)
    win.deleteLater()

    win = window(files, missing)
    win._select_page("Orders mapping")
    shot(win, "orders-missing", theme)
    win.done(0)
    win.deleteLater()

    win = window(None)
    win._select_page("Orders mapping")
    shot(win, "orders-no-file", theme)
    win._nav_search.setText("zzz")
    shot(win, "search-no-match", theme)
    win.done(0)
    win.deleteLater()

# set_theme stores the choice for this PC: put back what it was.
manager.set_theme(started_as)
for path in (orders, stock):
    path.unlink()
print(sorted(p.name for p in OUT.iterdir()))
```

Run, from the repo root:
`QT_QPA_PLATFORM=offscreen PYTHONPATH=. .venv/bin/python <your tmp dir>/render_settings.py <your tmp dir>/renders`

It writes twenty PNGs (ten states, two themes). Read each with the Read tool and compare with
`docs/design/ui-refresh/mockups/renders/client-settings.png` and, for the Orders mapping state, with the
mockup opened as its README describes. Check, in both themes:

- `*-general.png`: the nav is a white panel with a hairline on its right; "General" is the open row, on a
  sunken fill, in bold; group names are small, bold and secondary. Two cards, "CSV files" and "Stock
  alerts"; each delimiter is five segments with its hint under it. The footer is empty, Save is disabled
  (dashed), and the other button reads Cancel.
- `*-general-unsaved.png`: Other is chosen for Stock with a one-character field beside it holding `|`. A dot
  sits at the right edge of the General and Sets rows. The footer reads "Unsaved changes in General, Sets"
  after a dot, and Save is filled.
- `*-general-saved.png`: no dots. The footer reads "Saved. Applies from the next analysis." in the success
  colour after a tick, Save is disabled, and the other button reads Close.
- `*-orders.png`: the head has "Read columns from CSV…" on the right. The Fields card names
  `acme-orders-30-09.csv` in the mono face. Twelve rows: a bold label ("Required" beside four), an arrow, a
  240px menu showing the column in mono, and the first row's value. Notes reads `Old Notes` with "Not in this
  file".
- `*-orders-lower.png`: Courier names has its two column heads, four rows (text field, arrow, courier menu,
  ✕) and "Add name". Additional columns has two chips, the second with the note "Not in this file, not
  filled down", and "Add column".
- `*-orders-missing.png`: Shipping method's menu has a danger edge and reads "Choose column"; the sentence
  under it ends with `Shipping Method` in mono. The Orders mapping nav row carries the alert. The footer reads
  "Map Shipping method in Orders mapping to save." in the danger colour with the page name underlined, and
  Save is disabled.
- `*-orders-no-file.png`: the Fields card reads "No CSV has been read. Use Read columns from CSV… to change
  a field." and every menu is disabled.
- `*-stock.png`: one card. Five rows; Expiry date and Batch have a hint under them.
- `*-rules-qt.png`: the Qt Rules page inside the new frame, with its own margins, looking as it did.
- `*-search-no-match.png`: the nav shows only `No settings match “zzz”.`

If anything differs from the mockup beyond the departures in spec §9, fix the CSS or the QSS, re-run the
task's tests, and render again.

Copy eight of the PNGs into the repo with the Bash tool (`mkdir -p docs/design/ui-refresh/renders/phase7`,
then `cp`): `light-general.png`, `light-general-unsaved.png`, `light-general-saved.png`, `light-orders.png`,
`light-orders-lower.png`, `light-orders-missing.png`, `light-stock.png`, `dark-orders-missing.png`. Delete the
script and the rest.

- [ ] **Step 2: Update the roadmap, the ADR and the glossary**

In `docs/design/ui-refresh/roadmap.md`, find exactly:

```markdown
This file turns them into nine phases.
```

Replace with:

```markdown
This file turns them into ten phases.
```

In `docs/design/ui-refresh/roadmap.md`, find exactly:

```markdown
7 to 9 run in sequence.
```

Replace with:

```markdown
7 to 10 run in sequence.
```

In `docs/design/ui-refresh/roadmap.md`, find exactly:

```markdown
| 9 | UI refresh phase 9: Client settings on the web tier: Sets, Weight, Reports, Tag categories | `client-settings.html` (anatomy only) | 8 |
```

Replace with:

```markdown
| 9 | UI refresh phase 9: Client settings on the web tier: Sets, Weight, Reports, Tag categories | `client-settings.html` (anatomy only) | 8 |
| 10 | UI refresh phase 10: Client settings on the web tier: the frame | `client-settings.html` | 9 |
```

In `docs/design/ui-refresh/roadmap.md`, find exactly:

```markdown
### 7. Client settings on the web tier: frame, General, mappings

The modal becomes a `QDialog` that hosts a web view.
```

Replace with:

```markdown
### 7. Client settings on the web tier: frame, General, mappings (built in run 53)

Spec: `docs/superpowers/specs/2026-10-02-ui-refresh-phase7-settings-web-design.md`.
Plan: `docs/superpowers/plans/2026-10-02-ui-refresh-phase7-settings-web.md`.

Built as listed below, with these differences. The frame stays Qt, restyled to the mockup: a Qt page cannot
be drawn over a web view (ADR 0007), so a web frame could not hold the five pages that are still Qt. One
web view sits in the page area and draws General and both mappings; the frame moves in phase 10. The native
title bar stands in for the mockup's header strip. Save is live only when a page is unsaved, and the dialog
stays open after it ("Saved. Applies from the next analysis."). Columns are picked from the file loaded on
Setup, or one read in the dialog, never typed. Courier names is one row per pattern, under "Shipping method
contains". Stock mapping has no Additional columns card. The kit gained the page anatomy: `.card-head`,
`.card-row`, `.hint`, `.problem`, `.chip`.

The modal becomes a `QDialog` that hosts a web view.
```

In `docs/design/ui-refresh/roadmap.md`, find exactly:

```markdown
rule. This is the largest single editor (`gui/settings/rules.py`, about 1,500 lines). Split it again at its
own Stage A if it does not fit one PR.
```

Replace with:

```markdown
rule. This is the largest single editor (`gui/settings/rules.py`, about 1,500 lines). Split it again at its
own Stage A if it does not fit one PR. The page joins the settings document phase 7 built
(`gui/web/settings.*`), with its values in a draft (`gui/settings/page_state.py`).
```

In `docs/design/ui-refresh/roadmap.md`, find exactly:

```markdown
The mockup has no drawing of these pages. They follow the page anatomy from Phase 7, and the spec names each
place where it had to decide something the mockup does not show.
```

Replace with:

```markdown
The mockup has no drawing of these pages. They follow the page anatomy from Phase 7, and the spec names each
place where it had to decide something the mockup does not show.

### 10. Client settings on the web tier: the frame

The nav, the search, the footer and the close guard move into the settings document, and the Qt frame goes.
It waits for 9: a Qt page cannot be drawn over a web view (ADR 0007), so the frame can be web only once no
Qt page is left inside it. The header strip the mockup draws stays out; the native title bar does that job.
```

In `docs/adr/0016-the-web-tier-grows-screen-by-screen.md`, find exactly:

```markdown
  state (source, level, search, wrap, follow, open rows); Python keeps the entries, words every row and
  streams rows in batches, never one message a line.
```

Replace with:

```markdown
  state (source, level, search, wrap, follow, open rows); Python keeps the entries, words every row and
  streams rows in batches, never one message a line.
- Client settings began moving in phase 7 (2026-10-02) with the sixth bridge, `SettingsBridge`, and a sixth
  view, which lives only while the dialog is open. Three pages moved: General, Orders mapping and Stock
  mapping. The dialog's frame stays Qt until its last Qt page has moved, because a Qt page cannot be drawn
  over a web view (ADR 0007). Python owns every value and every sentence of a page, in a draft; the page
  owns which menu is open.
```

In `CONTEXT.md`, find exactly:

```markdown
Every screen today: Session Setup, Analysis Results, Browse, Logs and Tools. The
Client settings window is still Qt; ADR 0016 lets it move in its own tasks. See
ADR 0001 for why Results moved first.
```

Replace with:

```markdown
Every screen today: Session Setup, Analysis Results, Browse, Logs and Tools. In
the Client settings window three pages are web (General, Orders mapping, Stock
mapping); its frame and its other pages are still Qt, and move in their own
tasks (ADR 0016). See ADR 0001 for why Results moved first.
```

In `CONTEXT.md`, find exactly:

```markdown
**Unsaved page** — a settings page whose values differ from the ones it
opened with. The nav marks it, the footer names it, and closing guards it.
Saving writes every page regardless; unsaved is what the operator is warned
about, not what decides the write.

**Close guard** — the row that replaces Save and Cancel when closing Settings
would discard unsaved pages: Keep editing, Discard, Save & close.
Distinguished from a **confirm**, which is a separate dialog; the guard is
inline because the pages it names are on screen beside it.
```

Replace with:

```markdown
**Unsaved page** — a settings page whose values differ from the ones it
opened with, or from the ones last saved. The nav marks it, the footer names
it, and closing guards it. Save is live only while a page is unsaved and
nothing blocks; a save still writes every page.

**Blocker** — what stops a save right now: a required column with no mapping,
a threshold that is not a number. The page's nav row carries an alert, the
footer names it with a link to the page, and Save is disabled until it is
fixed. Distinguished from a page's **validation**, which runs when Save is
pressed and is the only check a Qt page gets.

**Draft** — a settings page with no widget: the values of a page the web tier
draws, the edits it takes, and every sentence it shows
(`gui/settings/page_state.py`). The window saves and marks a draft exactly as
it does a Qt page.

**Close guard** — the row that replaces Save and Cancel when closing Settings
would discard unsaved pages: Keep editing, Discard, Save & close. Save & close
is disabled while a blocker stands. Distinguished from a **confirm**, which is
a separate dialog; the guard is inline because the pages it names are on
screen beside it.
```


- [ ] **Step 3: The gate**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`

Expected: the three baseline failures in `tests/test_label_printing.py::TestImageToZpl` and nothing else
(in the scratch copy: 3 failed, 3181 passed).

Run: `.venv/bin/ruff check .` Expected: `All checks passed!`

Run: `graphify update .` (CLAUDE.md: right after modifying code). `graphify-out/` is not tracked; commit
nothing from it.

- [ ] **Step 4: Commit**

Stage `CONTEXT.md docs/adr/0016-the-web-tier-grows-screen-by-screen.md docs/design/ui-refresh/roadmap.md`
and the eight PNGs under `docs/design/ui-refresh/renders/phase7/`. Commit. Message subject:
`Settings: docs and renders for phase 7`.

For the PR description (Stage C writes it): `shared/` gains one file, `shared/assets/icons/circle-alert.svg`;
Packing Tool gets it at its next sync and needs no work. The sixth `QWebEngineView` lives only while the
dialog is open, and rests on the phase 3 Linux measurement; the Windows check over RDP stays with the
release. Two things to check by hand on Windows, because no offscreen test can: Esc with focus inside the
web page closes the dialog (or shows the close guard), and Ctrl+S and Ctrl+F work from inside it. Departures
from the mockup are spec §9.
