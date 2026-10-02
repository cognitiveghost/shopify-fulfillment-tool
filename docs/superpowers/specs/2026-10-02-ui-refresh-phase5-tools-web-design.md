# UI refresh phase 5: Tools on the web tier

**Task:** dev-runner run 47, Todoist 6hfx8cqwQMmxr9GM: "UI refresh phase 5: move Tools to the web tier".
Brief: `docs/design/ui-refresh/roadmap.md`, phase 5. Depends on phase 2 (merged, #356).
**Path:** architectural. It adds a fourth web view and a fourth bridge, replaces both Qt tool widgets, and
gives the reference-label run a counted progress and cancel contract.
**Mockup followed:** `docs/design/ui-refresh/mockups/tools.html` (all five states, both themes). Every
departure is in §10.

## 1. What this task delivers

1. The Tools page as a web page on the kit: `gui/web/tools.html`, `tools.css`, `tools.js` (§5).
2. `ToolsBridge`, and one pure function that builds everything the page draws (§3, §4).
3. Two tool objects, `ReferenceTool` and `BarcodeTool`, holding what the two Qt widgets knew and did (§6).
4. Input files checked when they are picked, with the problem shown under the file's own field (§6.2).
5. Counted progress and Cancel for Reference labels; barcode rendering off the GUI thread (§7).
6. Print mode as the mockup draws it, with the settings it does not draw behind a "Label setup" fold (§5.5).
7. One kit component, `.select`, and two disabled states (§5.8).
8. Docs: `CONTEXT.md`, ADR 0016, `roadmap.md` (§12).

## 2. Owner's decisions (2026-10-02, run 47)

| Question | Answer |
|---|---|
| Print settings the mockup does not draw (label size, rotate, invert, the driver dialog's printer) | The mockup's row, plus one collapsed "Label setup" line under it that states the values and opens to them. The printer menu also shows in Driver mode |
| How far progress goes | Honest per tool. Reference labels gets a count and Cancel. Barcode labels says "Writing 120 barcode labels…" with no count and no Cancel, and its render moves off the GUI thread |
| What Print does | It prints what exists. Reference: live after a run. Barcode: live whenever the selected list has a label PDF on disk |
| Change… on the Barcode output folder | Not built. The folder stays fixed and is shown as read-only text |
| The design (§3 to §11) | Approved. A picked PDF and CSV are cleared when the session changes |

The fourth `QWebEngineView` follows the owner's phase 3 decision: build on the Linux numbers (about 31 MB
and at most 0.15 s a view, phase 3 spec §2). The Windows check stays with the release.

**What the code does that the mockup does not know** (the facts behind the answers):

- The mapping CSV is read by position (columns 1, 2, 3 and 7). Its header row is skipped and never checked.
- Matching a page to a reference is the run itself, so nothing is matched before Process.
- Barcode labels are one WeasyPrint call for the whole PDF. It reports nothing and cannot be interrupted.
  Today it runs on the GUI thread, in the completion slot.
- A packing list's label PDFs live in `<session>/barcodes/<list>/`. Regenerating the list deletes them there
  (`invalidate_label_pdfs`).

## 3. Architecture

```
ReferenceTool / BarcodeTool ──► tools_state(...) ──► ToolsBridge.state ──► tools.js render()
   (facts, runs, print)           (pure, a dict)       (one Property)       (draws all of it)
tools.js ──► ToolsBridge slot ──► Signal ──► ToolsWidget ──► the tool ──► changed ──► push again
```

- **Python owns every fact and every sentence.** `tools_state` returns one dict: the session, both cards'
  rows, each print block, each footer's reason, and what is enabled. The page renders it. The page's own
  state is which menu is open, which Label setup fold is open, and the toast timer.
- **A tool is not a widget.** Each is a `QObject` that holds its picks, runs its work on a `Worker`, and
  emits `changed`. `ToolsWidget` hosts the view and connects the bridge to the tools. The tools are tested
  with no web view; the page is tested with states built by hand.

### 3.1 Files

| File | What it is |
|---|---|
| `gui/tools_state.py` (new) | `PickedFile`, `ToolRun`, `ReferenceFacts`, `PackingList`, `BarcodeFacts`, `PrintFacts`, `tools_state(...)`, `apply_print_edit(...)`. No Qt import |
| `gui/tools_bridge.py` (new) | `ToolsBridge(PageBridge)`, `mount_tools_page(view)` |
| `gui/reference_tool.py` (new) | `ReferenceTool(QObject)` |
| `gui/barcode_tool.py` (new) | `BarcodeTool(QObject)`, `read_packing_lists(...)` |
| `gui/tools_widget.py` (rewritten) | `ToolsWidget(QWidget)`: the view, the wiring, `sync()` |
| `gui/web/tools.html`, `tools.css`, `tools.js` (new) | The page |
| `gui/web/kit.css` | `.select`; `.segment:disabled`; `.field:disabled` |
| `gui/setup_state.py` | `session_meta(client, session, now)` is extracted; both states call it |
| `gui/ui_manager.py` | Tab 4 joins `_WEB_PAGES`; `refresh_tools()`; the chip rule |
| `gui/main_window_pyside.py` | `web_toast` knows tab 4; the banner's two requests |
| `gui/pdf_printing.py` | One error sentence reworded (§6.5) |
| `gui/components/__init__.py` | `PrintOptions` leaves the exports |
| `shopify_tool/pdf_processor.py` | `ProcessingCancelled`, `READING`, `STAMPING`, `SAVING`, `pdf_page_count`, counted progress, `rows` in the CSV mapping |
| `shopify_tool/barcode_processor.py` | `packing_list_orders`, `generate_list_labels` |
| `tests/conftest.py` | `print_settings_store` patches `gui.pdf_printing` |
| Deleted | `gui/reference_labels_widget.py`, `gui/barcode_generator_widget.py`, `gui/components/print_options.py` |

`FormSection`, `row_widget`, `InlineMessage` and `ElidedLabel` stay: Client settings still uses them.

### 3.2 `ToolsBridge`: the catalogue

Channel name `tools`. Add a member here before adding it to the code. `tool` is `"reference"` or
`"barcode"`; a slot drops any other value.

| member | direction | meaning |
|---|---|---|
| `state` Property (`QVariantMap`, notify `stateChanged`) | Python → JS | Everything the page draws (§4) |
| `themeCss`, `toastRaised(text, action)` | Python → JS | From `PageBridge`. On this page a true flag means "offer Open folder" |
| `chooseFile(kind)` → `fileRequested(str)` | JS → Python | Open the file dialog. `kind` is `"pdf"` or `"csv"` |
| `clearFile(kind)` → `clearRequested(str)` | JS → Python | Replace: empty that pick |
| `changeFolder()` → `folderRequested()` | JS → Python | Reference labels' Change… |
| `setOption(tool, name, on)` → `optionChanged(str, str, bool)` | JS → Python | `("reference", "open_pdf")`, `("barcode", "open_pdf")`, `("barcode", "qr")`; any other pair is dropped |
| `setPrint(tool, key, value)` → `printChanged(str, str, object)` | JS → Python | One print setting (§4.5). An unknown key is dropped |
| `chooseList(name)` → `listChosen(str)` | JS → Python | Select a packing list by name |
| `refreshLists()` → `listsRequested()` | JS → Python | Refresh |
| `run(tool)` → `runRequested(str)` | JS → Python | Process labels, or Generate barcode labels |
| `cancel()` → `cancelRequested()` | JS → Python | Cancel the reference run |
| `printLabels(tool, what)` → `printRequested(str, str)` | JS → Python | `what` is `"labels"` or `"qr"`; `("reference", "qr")` is dropped |
| `openFolder()` → `folderOpenRequested()` | JS → Python | The toast's action |
| `newSession()` → `newSessionRequested()` | JS → Python | The banner's primary |
| `openRecent()` → `recentRequested()` | JS → Python | The banner's secondary |

`setPrint` is `@Slot(str, str, "QVariant")`. `set_state(state: dict)` emits `stateChanged` only when the dict
differs from the last one. The page names a packing list by its name and a printer by its name. Nothing it
sends is used as a path.

## 4. The state

### 4.1 Inputs (`gui/tools_state.py`)

```python
@dataclass(frozen=True)
class PickedFile:
    name: str                                  # the file's name, as the row shows it
    count: int | None = None                   # pages, or CSV rows; None with a problem
    problem: tuple[str, str] | None = None     # (title, text)

@dataclass(frozen=True)
class ToolRun:
    label: str                                 # READING, STAMPING, SAVING, or Barcode's sentence
    done: int = 0
    total: int = 0                             # 0: this run has no count
    cancelling: bool = False

@dataclass(frozen=True)
class ReferenceFacts:
    pdf: PickedFile | None = None
    csv: PickedFile | None = None
    folder: str = ""                           # the output folder's full path; "" with no session
    open_pdf: bool = True
    run: ToolRun | None = None
    result: dict | None = None                 # process_reference_labels' result for these inputs
    has_output: bool = False                   # a processed PDF Print can send

@dataclass(frozen=True)
class PackingList:
    name: str
    count: int | None                          # Fulfillable orders; None when the file can't be read
    has_labels: bool = False                   # its barcode PDF is on disk
    has_qr: bool = False                       # its QR PDF is on disk

@dataclass(frozen=True)
class BarcodeFacts:
    lists: tuple[PackingList, ...] = ()
    loading: bool = False
    analysed: bool = True                      # the window holds analysis data
    selected: str = ""                         # a list's name
    folder: str = ""                           # the selected list's label folder; "" with none
    qr: bool = False
    open_pdf: bool = True
    run: ToolRun | None = None
    result: dict | None = None                 # generate_list_labels' result for the selected list

@dataclass(frozen=True)
class PrintFacts:
    settings: dict                             # load_print_settings(scope)
    printers: tuple[str, ...] = ()             # installed printer names

def tools_state(*, client: str, session: SessionFacts | None, reference: ReferenceFacts,
                reference_print: PrintFacts, barcode: BarcodeFacts, barcode_print: PrintFacts,
                now: datetime) -> dict
```

`SessionFacts` is `gui.setup_state`'s.

### 4.2 Output

```python
{
  "session": {"name": "2026-09-30_1", "meta": "ACME · opened 14:02"},        # {} with none
  "banner": False,                                                           # True with no session
  "reference": {
    "quiet": False, "locked": False,
    "pdf": row, "csv": row,
    "folder": {"text": "…\\2026-09-30_1\\reference_labels", "title": "<full path>", "muted": False},
    "open_pdf": True,
    "print": print_block,
    "run": {} | {"label": "Stamping labels", "count": "40 of 120", "bar": True, "percent": 66,
                 "cancel": {"label": "Cancel", "enabled": True, "title": ""}},
    "reason": "120 pages, 120 CSV rows.", "tone": "",                        # "" | "danger" | "warning"
    "can_run": True,
    "print_button": {"label": "Print…", "title": "Process labels first", "enabled": False},
  },
  "barcode": {
    "quiet": False, "locked": False,
    "list": {"name": "DHL", "meta": "120 Fulfillable", "placeholder": ""},
    "lists": [{"name": "DHL", "meta": "120", "checked": True}, ...],
    "folder": {"text": "…\\barcodes\\DHL", "title": "<full path>", "muted": False},
    "qr": False, "open_pdf": True,
    "print": print_block,
    "run": {} | {"label": "Writing 120 barcode labels…", "count": "", "bar": False, "percent": 0,
                 "cancel": {}},
    "reason": "Saves to …\\barcodes\\DHL.", "tone": "",
    "can_run": True,
    "print_button": {"label": "Print", "title": "Send to Zebra ZD421", "enabled": True},
    "qr_button": {} | {"label": "Print QR labels", "title": "...", "enabled": False},
  },
}
row = {} | {"name": "dhl-labels-30-09.pdf", "meta": "120 pages", "problem": {} | {"title", "text"}}
print_block = {
  "mode": "driver" | "raw_zpl",
  "printer": {"value": "", "label": "Windows default", "placeholder": False},
  "printers": [{"value": "", "label": "Windows default", "checked": True}, ...],
  "help": "...", "help_tone": "" | "danger",
  "setup": {} | {"summary": "152.4 × 101.6 mm, rotated 90°", "target": "Zebra ZD421",
                 "width": 152.4, "height": 101.6, "rotate": True, "invert": False, "size_hint": "..."},
}
```

**Session.** `meta` is `setup_state.session_meta(client, session, now)`: "{client} · opened {time}", or
"{client} · analysed {time}" once analysed; the client alone with no timestamp.

**Numbers** use a comma for thousands ("1,204").

**A short path** is "…" + the separator + the path's last two parts, joined by `os.sep` ("…\2026-09-30_1\
reference_labels" on Windows). The full path is the `title`. With no session, `text` is "Session folder",
`title` is "" and `muted` is true. With a session and no packing list, Barcode's `text` is "Choose a packing
list", muted.

### 4.3 Reference labels

`quiet = session is None`. `locked = run is not None`.
`pdf_ok` and `csv_ok`: the file is picked and has no problem.
`can_run = not quiet and not locked and pdf_ok and csv_ok`.

A `row`'s `meta` is "{count} pages" ("1 page") or "{count} rows" ("1 row"), and "Problem" when the file has
one.

| situation, first match | reason | tone |
|---|---|---|
| no session, or running | "" | |
| the PDF has a problem | "Fix the labels PDF to process." | danger |
| the CSV has a problem | "Fix the mapping CSV to process." | danger |
| no PDF and no CSV | "Choose the labels PDF and mapping CSV." | |
| no PDF | "Choose the labels PDF." | |
| no CSV | "Choose the mapping CSV." | |
| a result whose `reference_run_warning` is not `None` | that warning | warning |
| a result | "{matched} of {pages} labels matched." With unmatched pages: "{matched} of {pages} labels matched, {unmatched} unmatched." With `name_matched`: that sentence, then " {n} matched by name only." | |
| ready | "{pages} pages, {rows} CSV rows." | |

**Run.** The running footer is worded here, so the page decides nothing. A run with a count
(`total > 0`): `label` is the phase ("Saving…" for `SAVING`), `count` is "{done} of {total}" ("" while
saving), `bar` is true, and `percent` runs across both counted phases so the bar never goes back: `done` for
`READING`, `total + done` for `STAMPING`, `2 * total` for `SAVING`, each times 100 and floor-divided by
`2 * total`. `cancel` is the button: its label is "Cancel", or "Cancelling…" while cancelling; it is enabled
while the phase is `READING` or `STAMPING` and the run is not cancelling; its title is "Saving can't be
cancelled" while saving. A run with no count (Barcode): `label` is the sentence, `count` is "", `bar` is
false and `cancel` is `{}`.

**Print.** `target_ok` is true in Driver mode, and in Raw ZPL mode when the target is not blank.
`enabled = has_output and not quiet and not locked and target_ok`.
`label` is "Print…" in Driver mode and "Print" in Raw ZPL.

| situation, first match | title |
|---|---|
| no output yet | "Process labels first" |
| Raw ZPL with no target | "Choose a printer under Print mode" |
| Raw ZPL | "Send to {target}" |
| Driver | "Open the print dialog" |

### 4.4 Barcode labels

`quiet = session is None`. `locked = run is not None`. `cur` is the list named `selected`, or none.
`can_run = not quiet and not locked and analysed and cur is not None and bool(cur.count)`.

`list`: with `cur`, its name and "{count} Fulfillable" ("Unreadable" when the count is `None`). Without:
`placeholder` is "Reading packing lists…" while the first load is running, "Choose a packing list" when
there are lists and none is selected, else "No packing lists". `lists` carries each list's name, its count as
text ("—" when `None`) and whether it is the selected one. With no session `lists` is `[]`. A reload while
lists are on screen changes nothing until its result arrives.

| situation, first match | reason | tone |
|---|---|---|
| no session, or running | "" | |
| loading, with no lists yet | "Reading packing lists…" | |
| no lists | "No packing lists in this session yet. Generate one on Results, then Refresh." | |
| not analysed | "This session has no analysis loaded. Run it on Setup." | |
| no list selected | "Choose a packing list." | |
| `cur.count is None` | "This packing list couldn't be read. Details are in Logs." | danger |
| `cur.count == 0` | "No Fulfillable orders in this list." | |
| a result with `failed` | "{labels} labels written, {failed} order numbers couldn't be encoded. Details are in Logs." ("1 label", "1 order number") | warning |
| a result with `qr_failed` | "Barcode labels written. The QR labels failed; details are in Logs." | warning |
| `cur.has_labels` | "Generating again replaces the labels in {short folder}." | |
| otherwise | "Saves to {short folder}." With `qr` ticked: "Saves to {short folder}, with QR labels." | |

Here `{short folder}` is "…" + separator + `barcodes` + separator + the list's name.

**Print.** `print_button.enabled = cur is not None and cur.has_labels and not locked and target_ok`. Its
label and title follow §4.3, with "Generate this list's labels first" when there is no PDF. `qr_button` is
`{}` unless a list is selected and either `qr` is ticked or `cur.has_qr`. Its label is "Print QR labels…" or
"Print QR labels", it is enabled on the same rule with `cur.has_qr`, and its no-PDF title is "Generate with
QR labels ticked first".

### 4.5 The print block

`noun` is "stamped labels" for Reference and "barcode labels" for Barcode. The settings dict is
`gui.pdf_printing.load_print_settings`'s; its keys and the two scope names (`reference_labels`,
`barcode_generator`) do not change, so every PC keeps what it has saved.

| mode | `printers` | `printer` | `help` |
|---|---|---|---|
| `driver` | "Windows default" (value ""), then each installed printer, then the saved `driver_printer_name` if it is set and not installed | the saved name, or "Windows default" | "Prints {noun} through the Windows print dialog. Saved for this PC." |
| `raw_zpl` | each installed printer, then the saved `raw_zpl_target` if it is set and not installed | the saved target; with none, label "Choose a printer" and `placeholder` true | "Sends {noun} straight to the label printer as ZPL, no dialog. Saved for this PC." With no target: "Raw ZPL needs a printer. Choose the one the labels go to.", tone danger |

`setup` is `{}` in Driver mode. In Raw ZPL it carries the four values and `summary`: the size as
"{w:g} × {h:g} mm" when both are above 0, else "the PDF's page size"; then ", rotated 90°" and ", colours
inverted" when set. `size_hint` is the tooltip the Qt spin boxes carried, per tool:

- Reference: "Physical label size as loaded in the printer, e.g. 152.4 x 101.6 for 6x4in shipping labels.
  0 disables fitting and uses each page's own PDF size."
- Barcode: "Physical label size as loaded in the printer, e.g. 68 x 38 for this flow's default label stock.
  0 disables fitting and uses the generated PDF's own page size."

```python
def apply_print_edit(settings: dict, key: str, value) -> dict | None
```

Returns a new settings dict, or `None` for an edit that is not one of these:

| key | value | writes |
|---|---|---|
| `mode` | `"driver"` or `"raw_zpl"` | `print_mode` |
| `printer` | a string | `driver_printer_name` in Driver mode, `raw_zpl_target` in Raw ZPL |
| `target` | a string, stripped | `raw_zpl_target` |
| `width`, `height` | a number; clamped to 0 to 500, rounded to one decimal | `raw_zpl_label_width_mm`, `raw_zpl_label_height_mm` |
| `rotate`, `invert` | a bool | `raw_zpl_rotate`, `raw_zpl_invert` |

A `bool` is not a number here, and a number is not a bool.

## 5. The page

Geometry is the mockup's at 1366×768 unless §10 says otherwise. Colours are kit tokens; the border mapping
is phase 2's (ADR 0018): a hairline is `--border-subtle`, a control's edge is `--border`.

### 5.1 Frame

`#tools` fills the view, scrolls (`overflow: auto`), has padding `20px 24px` and is a column with a 12px
gap. `_WEB_PAGES` becomes `frozenset({0, 1, 2, 4})`, so the page area's inset is 0 on Tools.

1. A kit `.page-head`: `.page-title` "Tools"; with a session, a `.code` chip with its name and `.page-meta`.
2. With `banner`: a kit `.banner.neutral`. The folder glyph (20px, `--text-secondary`); the title "Open a
   session to use these tools"; the text "Both tools read the session's files and save into its folder.
   Print modes can be set now; they're saved on this PC."; **New session** (primary) → `newSession()` and
   **Open recent** (secondary) → `openRecent()`.
3. `.tool-cards`: a grid, `repeat(2, minmax(0, 1fr))`, gap 16px, `align-items: start`. At a page width
   under 900px it is one column.

The rail offers Tools only with a reachable server and a client (`_refresh_nav`), so the page needs no
no-client and no unreachable view.

### 5.2 A tool card

A `.card.tool-card` with `data-tool`, a column.

- **Head** (padding `14px 16px 12px`, gap 2): the title in label size, bold; the subtitle in
  `--text-secondary`.
  - "Reference labels": "Stamps each courier label PDF with its order's reference number."
  - "Barcode labels": "One barcode label for every Fulfillable order in a packing list. Each list gets its
    own folder."
- **Rows:** kit `.form-row`s. Inside a tool card the row is `112px minmax(0, 1fr)`, gap 12, padding
  `10px 16px`, with a `--border-subtle` rule above every row; the `.form-label` is regular weight,
  `--text-secondary`, and as tall as a control so it sits on the control's line. These overrides are in
  `tools.css`.
- **Footer** (`.tool-foot`: flex, gap 8, `min-height: 56px`, padding `12px 16px`, a `--border-subtle` rule
  above): §5.6.

The card's own edge never changes: a problem is flagged under its field, as the mockup draws it.

### 5.3 Reference labels' rows

- **Labels PDF** and **Mapping CSV**, the same shape:
  - nothing picked: one secondary button, "Choose PDF…" or "Choose CSV…" → `chooseFile(kind)`;
  - picked: the file glyph, the name in mono bold with ellipsis (its `title` is the name), the `meta` in mono
    caption `--text-secondary`, a spacer, and a compact secondary **Replace** → `clearFile(kind)`;
  - with a problem: the glyph and the `meta` ("Problem", bold) are `--status-danger`, and under the row a
    kit `.banner.danger` (radius 8) holds the alert glyph, the title in bold `--status-danger`, the text, and
    a `.btn.link` "Choose another PDF" or "Choose another CSV" → `chooseFile(kind)`.
- **Output folder:** `folder.text` in mono with ellipsis (`--text-disabled` when muted), a spacer, a
  secondary **Change…** → `changeFolder()`. Under it a checkbox, "Open the PDF when it's ready" →
  `setOption("reference", "open_pdf", checked)`.
- **Print mode:** §5.5.

### 5.4 Barcode labels' rows

- **Packing list:** a kit `.select` that fills the row, then a secondary **Refresh** with the refresh glyph
  → `refreshLists()`. The select shows `list.name` in bold and `list.meta` in mono caption, or the
  placeholder. Its menu (kit `.menu`, as wide as the select) opens under it: a `.menu-group` "Packing lists
  in {session name}", then one `.menu-item` per list (`role="menuitemradio"`, `aria-checked`) with the name,
  the count as a `.menu-hint` in mono, and the kit `.check`. Choosing one calls `chooseList(name)` and closes
  the menu. The select is disabled when `lists` is empty.
- **Output folder:** `folder.text`, as in §5.3, with no button. Under it two checkboxes in one wrapping row
  (gap 16): "Add QR labels (order number)" → `setOption("barcode", "qr", …)` and "Open the PDF when it's
  ready" → `setOption("barcode", "open_pdf", …)`.
- **Print mode:** §5.5.

### 5.5 The Print mode row

1. One wrapping line (gap 8): a kit `.segmented` (`role="radiogroup"`) with two `.segment`s
   (`role="radio"`), **Driver** and **Raw ZPL** → `setPrint(tool, "mode", …)`; then a kit `.select` that
   takes the rest of the line, with the printer glyph and `printer.label` in bold (`--text-placeholder` when
   it is the placeholder). Its menu lists `printers` as `menuitemradio`s → `setPrint(tool, "printer", value)`.
2. `help` in caption, `--text-secondary`, or `--status-danger` when its tone is danger.
3. In Raw ZPL only, the **Label setup** fold: a `.btn.link`-style button (`aria-expanded`) with a chevron
   (right when closed, down when open: two paths, no rotation), the words "Label setup" and `setup.summary`
   in `--text-secondary`. Open, it shows a small grid (`88px minmax(0, 1fr)`, gap `8px 12px`):
   - **Target:** a kit `.field`, text, placeholder "Printer name, or \\server\printer" →
     `setPrint(tool, "target", value)`;
   - **Label size:** two kit `.field`s, `type="number"`, `min="0" max="500" step="0.1"`, 72px wide, with
     "×" between and "mm" after; a value of 0 shows as empty with the placeholder "PDF"; both carry
     `size_hint` as their `title` → `setPrint(tool, "width" | "height", number)`;
   - a checkbox "Rotate 90°" → `setPrint(tool, "rotate", checked)`;
   - a checkbox "Invert colours", `title` "Tick if labels print white on black." →
     `setPrint(tool, "invert", checked)`.

   A text or number field reports on `change` (blur or Enter), never per keystroke. An empty number is 0.

Print mode stays live with no session. While the card is `locked`, the segments, the select, the fold's
fields and its checkboxes are `disabled`.

### 5.6 The footer

**Idle:** the reason (`.tool-reason`: flex 1, caption size, `--text-secondary`; `--status-danger` or
`--status-warning` by tone), then the buttons, right-aligned, primary last:

- Reference: **Print…** / **Print** (secondary; `print_button`) → `printLabels("reference", "labels")`;
  **Process labels** (primary; `disabled` unless `can_run`) → `run("reference")`.
- Barcode: when `qr_button` is not empty, **Print QR labels…** (secondary) → `printLabels("barcode", "qr")`;
  **Print…** / **Print** (secondary) → `printLabels("barcode", "labels")`; **Generate barcode labels**
  (primary; `disabled` unless `can_run`) → `run("barcode")`.

Each print button carries its `title`. Both cards draw their own primary.

**Running** (`run` is not empty): a column (flex 1, gap 6) holding `run.label` in bold, followed by " — "
and `run.count` in mono when there is a count; under it, when `run.bar`, a track (4px high, radius 2,
`--border-subtle`) whose fill (`--accent-fill`) is `run.percent` wide. Then, when `run.cancel` is not empty,
a secondary button with its label, its title and its enabled flag → `cancel()`. A Barcode run is therefore
its sentence alone: no track and no button.

### 5.7 What quiet and locked disable

| control | `quiet` (no session) | `locked` (this card is running) |
|---|---|---|
| Choose, Replace, Change…, the file problem's link | disabled | disabled |
| The packing list select, Refresh | disabled | disabled |
| The option checkboxes | disabled, label `--text-disabled` | disabled |
| The mode segments, the printer select, the Label setup fields | live | disabled |
| The Label setup fold button | live | live |
| Print, Print QR, the primary | disabled (by the state's flags) | replaced by the running footer |

The other card is not touched by one card's run.

### 5.8 Kit additions (`gui/web/kit.css`, and the kit sheet)

| class | what it is |
|---|---|
| `.select` | A button that shows a value and opens a menu: flex, gap 8, `--control-height`, padding `0 8px 0 10px`, radius 8, `1px solid var(--border)`, `--surface`, text left. `.select-value`: flex 1, bold, one line with ellipsis; `.select-value.placeholder`: regular weight, `--text-placeholder`. `.select-meta`: mono caption, `--text-secondary`. It ends in the chevron glyph, `--text-secondary`. `[aria-expanded="true"]`: a `--text` edge. `:disabled`: `--control-disabled-bg`, `1px dashed var(--border)`, `--text-disabled` (value, meta and glyph), `cursor: not-allowed` |
| `.segment:disabled` | `cursor: default`; an unchecked one is `--text-disabled` |
| `.field:disabled` | `--control-disabled-bg`, `1px dashed var(--border)`, `--text-disabled`, `cursor: not-allowed` |

`.select` joins the kit's `:focus-visible` rule. `tests/web/kit_sheet.html` gains a `.select` with a value
and a meta, one with a placeholder, one open and one disabled; a disabled segmented control; a disabled
`.field`.

The labelled checkbox (`.option`: a `<label>` wrapping a kit checkbox and its text, gap 8) and the progress
track are in `tools.css`: one page uses them.

### 5.9 Menus, toast and keyboard

**Menus.** One menu is open at a time; the page holds which. A `.select` click toggles its menu. A click
outside any `.menu-anchor`, Escape, or choosing an item closes it; Escape returns focus to the select. Up and
Down move focus between the items of the open menu and wrap. A state push leaves an open menu open.

**Toast.** The kit `.toast`: the text, **Open folder** (`.toast-action`, shown when the flag is true) →
`openFolder()`, and a dismiss button (`id="toast-dismiss"`). It hides after 4 s, or 8 s when it carries the
action. A new toast replaces the old one.

**Keyboard.** Every control is a real `<button>`, `<input>` or `<label>`, in document order: the banner's
buttons, then each card top to bottom. Left and Right move focus between the two mode segments; Space and
Enter choose. Nothing traps focus.

**Redraw.** A reference run pushes a state several times a second, so a state can arrive while a button is
held down or a field is being typed in. The page builds each state's markup whole, then brings the DOM to
match it node by node, keeping every node that is still the same control (same tag, same `data-key`). A press
finds its button still there at the release, so the click lands, Cancel included; a focused field keeps what
was typed and its caret, because it is the same node. Only where the layout itself changed is a control a new
node, and focus is then found again by its `data-key`. (Found in review: replacing the DOM whole, as Setup
does, dropped any click held across a push, and turned "152." in a number field into "152".)

**Dropped files.** The page cancels `dragover` and `drop` on the document, so a file dropped on it does not
navigate the view. It loads nothing.

## 6. The tools

### 6.1 `ToolsWidget` (`gui/tools_widget.py`)

Holds the view, the bridge, `ReferenceTool` and `BarcodeTool`.

- `bridge` is public: `MainWindow.web_toast` reads it.
- Signals `new_session_requested` and `recent_requested` repeat the bridge's two banner requests.
- `ToolsWidget(main_window, parent=None, pool=None)`: `pool` is handed to both tools (§6.2).
- `sync()`: reads `mw.session_path`. When it differs from the last one seen, it calls `set_session(path)` on
  both tools, and when the widget is visible and there is a session it calls `barcode.reload()`. Then it
  pushes. With an unchanged session it touches no file, so it is safe to call often.
- `_push()`: builds `tools_state` from both tools' `facts()`, the two `PrintFacts`, `mw.current_client_id`,
  and `mw.session_facts` (the session is `None` with no `session_path`, and `SessionFacts(name, None, None)`
  when the facts are for another session), and calls `bridge.set_state`.
- The installed printers (`installed_printers()`, which is `QPrinterInfo.availablePrinterNames()`) and both
  tools' saved settings are read when the widget is built and again on every `showEvent`, and kept; a push
  reads neither.
- `showEvent`: reads those, calls `sync()`, and with a session calls `barcode.reload()`.
- Each tool's `changed` is connected to `_push`.
- `printChanged(tool, key, value)`: applies `apply_print_edit` to that tool's kept settings, and when the
  result is not `None` keeps it, saves it and pushes.
- The widget and both tools call `gui.pdf_printing` through the module (`pdf_printing.print_pdf(...)`), so
  the `print_settings_store` fixture patches one place.
- A tool's `toast(text, folder)`: when this widget is visible and `folder` is not empty, the widget keeps
  the folder and calls `bridge.raise_toast(text, True)`. Otherwise it calls `gui.components.toast(self,
  text)`, so the page that is showing draws it.
- `folderOpenRequested`: opens the kept folder with `QDesktopServices.openUrl`.

### 6.2 `ReferenceTool` (`gui/reference_tool.py`)

```python
class ReferenceTool(QObject):
    changed = Signal()
    toast = Signal(str, str)                   # text, folder to offer ("" for none)

    def __init__(self, host: QWidget, pool: QThreadPool | None = None)
    # host: the parent for dialogs and error banners. pool: where a run's Worker
    # starts; the global pool when None. Tests pass one that only captures it.
    def facts(self) -> ReferenceFacts
    def set_session(self, session_path: str | None) -> None
    def choose(self, kind: str) -> None        # the file dialog, then load()
    def load(self, kind: str, path: str) -> None
    def clear(self, kind: str) -> None
    def change_folder(self) -> None
    def set_open_pdf(self, on: bool) -> None
    def start(self) -> None
    def cancel(self) -> None
    def print_output(self) -> None
```

- `set_session`: clears both picks, the result and the output. The folder becomes
  `Path(session_path) / "reference_labels"`, or `None`. It reads nothing from the share.
- `load("pdf", path)`: `pdf_processor.pdf_page_count(path)` gives the count. `InvalidPDFError` gives the
  problem ("This PDF can't be read", "Check that it isn't damaged, then choose it again.").
- `load("csv", path)`: `pdf_processor.load_csv_mapping(path)["rows"]` gives the count. `InvalidCSVError`
  gives the problem ("This CSV has no usable rows", "Each row needs the PostOne export's columns: PostOne ID
  (1st), Tracking (2nd), Reference (3rd) and Name (7th).").
- Any `load` or `clear` drops the result and the output: they described the inputs before.
- `change_folder`: `QFileDialog.getExistingDirectory`; the choice lasts until the session changes.
- `start`: does nothing unless both files are good, a folder is set and no run is going. It starts a
  `Worker` that makes the folder (`mkdir(parents=True, exist_ok=True)`) and calls
  `process_reference_labels` with `progress_callback=self._report`. The tool keeps a reference to the worker
  until it finishes: a `Worker` held only by a local is collected before its queued result arrives (the note
  in `gui/main_window_pyside.py` where the client-load worker starts).
- `_report(done, total, label)` runs on the worker thread. It raises `ProcessingCancelled` when cancel is
  set. Otherwise it emits a private signal, at most every 100 ms except for the last call of a phase
  (`done == total`), and the slot stores the `ToolRun` and emits `changed`.
- `cancel`: while running, sets the event and the `cancelling` flag, and emits `changed`.
- On a result: stores it, sets the output to `result["output_file"]`, opens the PDF when `open_pdf` is on,
  and, when `reference_run_warning(result)` is `None`, emits `toast("{pages} labels saved to {short
  folder}", folder)`. A warning stays in the footer and raises no toast, as today.
- On an error: `ProcessingCancelled` emits `toast("Processing cancelled", "")`. `InvalidPDFError`,
  `InvalidCSVError` and `MappingError` call `show_error(host, "The PDF wasn't processed", …)` with today's
  three sentences. An `OSError` from making the folder says "Can't reach this session's folder. Check the
  server connection." Anything else says "Details are in Logs."
- `print_output`: `print_pdf(host, output, load_print_settings("reference_labels"))`.
- Opening a PDF that will not open keeps today's error: "The PDF didn't open", "Open it manually: {path}".

`# ponytail:` the two checks in `load` run on the GUI thread. Both read a file the operator has just picked
in a dialog. Move them to a worker if a pick from the share ever stalls the window.

### 6.3 `BarcodeTool` (`gui/barcode_tool.py`)

```python
def read_packing_lists(session_path: str, analysis_df) -> list[tuple[PackingList, frozenset]]

class BarcodeTool(QObject):
    changed = Signal()
    toast = Signal(str, str)

    def __init__(self, host: QWidget, analysis: Callable[[], pd.DataFrame | None],
                 pool: QThreadPool | None = None)      # pool: as ReferenceTool's
    def facts(self) -> BarcodeFacts
    def set_session(self, session_path: str | None) -> None
    def reload(self) -> None
    def choose(self, name: str) -> None
    def set_option(self, name: str, on: bool) -> None      # "qr" | "open_pdf"
    def start(self) -> None
    def print_labels(self, what: str) -> None              # "labels" | "qr"
```

- `read_packing_lists` runs on a worker. It lists `<session>/packing_lists/*.xlsx`, sorted by stem, leaving
  out Excel's lock files (`~$name.xlsx`). For each
  it reads the order numbers with `barcode_processor.packing_list_orders(path)`, through a module cache
  keyed by path and checked against the file's mtime (the pattern in CLAUDE.md, "File caching"). The count
  is the number of distinct `Order_Number`s of `fulfillable_only(analysis_df)` that are in the list; it is
  `None` when the file cannot be read (logged) or there is no analysis frame. `has_labels` and `has_qr` are
  whether `barcode_pdf_path` and `qr_pdf_path` exist. A missing `packing_lists` folder gives `[]`.
- `reload`: with no session, or while a load is running, it does nothing. Otherwise it sets `loading`,
  emits `changed`, and starts the worker. A result that arrives after the session changed is dropped. The
  selection is kept when a list of that name is still there, else it moves to the first list. `analysed` is
  whether `analysis()` is not `None`. A load that fails outright (the share is gone) clears `loading` and
  calls `show_error(host, "The packing lists weren't read", "Check the server connection, then Refresh.")`.
- `choose(name)`: selects a list that exists; drops the last result.
- `start`: does nothing unless a list with a count above 0 is selected and no run is going. When the list's
  barcode PDF exists it asks first, with today's `ConfirmDialog` ("Replace barcodes for {list}?", "The
  existing PDF is overwritten with {n} new barcodes. This cannot be undone.", "Replace barcodes"). It builds
  the list's rows (`fulfillable_only(analysis())` filtered to the list's order numbers) on the GUI thread,
  as today, and starts a `Worker` on `generate_list_labels(rows, folder, name, qr=…, progress=…)`. The
  folder and the name are arguments, so a session change during the run cannot redirect it.
- The run starts as `ToolRun("Preparing {n} labels…")`. The `progress(label)` callback emits a signal; the
  slot stores `ToolRun(label)` and emits `changed`.
- On a result: when it is for the open session, stores it and updates that list's `has_labels` and `has_qr`.
  It opens the barcode PDF and the QR PDF when `open_pdf` is on, and, when a barcode PDF was written, emits
  the toast: "{labels} barcode labels saved to {short folder}", followed by ". QR labels too." when a QR PDF
  was written. A result with `failed` or `qr_failed` also shows in the footer (§4.4).
- On an error: `show_error(host, "The barcode PDF wasn't created", "Details are in Logs.")`.
- `print_labels`: `print_pdf(host, path, load_print_settings("barcode_generator"))` with the selected
  list's barcode or QR PDF path.

### 6.4 The shell

- `gui/ui_manager.py`: `_WEB_PAGES = frozenset({0, 1, 2, 4})`. `set_screen(chip=index not in (0, 4),
  meta=index == 1)`: the Tools page head draws the chip. `refresh_tools()` calls `mw.tools_widget.sync()`
  when the widget exists, and `refresh_setup()` ends by calling it: every client, session and connection
  change already passes through `refresh_setup`.
- `gui/main_window_pyside.py`: `web_toast` answers tab 4 with `tools_widget.bridge`.
  `tools_widget.new_session_requested` → `actions_handler.create_new_session`;
  `tools_widget.recent_requested` → `command_bar.session_button.showMenu()`.

### 6.5 Printing

`gui/pdf_printing.py` keeps its three functions. With Raw ZPL and no target Print is disabled, so
`_print_pdf_raw_zpl_mode`'s guard is a backstop; its sentence becomes "Choose a printer under Print mode,
then print again."

## 7. Runs

### 7.1 `shopify_tool/pdf_processor.py`

```python
READING, STAMPING, SAVING = "Reading labels", "Stamping labels", "Saving"

class ProcessingCancelled(PDFProcessorError):
    """Raised by a progress callback to stop a run before it saves."""

def pdf_page_count(pdf_path) -> int            # raises InvalidPDFError: unreadable, or no pages
```

`load_csv_mapping` adds `"rows"` to the dict it returns: the data rows it used.

`process_reference_labels` keeps its signature. `progress_callback(done, total, label)` is now called:

1. `(i, pages, READING)` after each page's text is read, `i` from 1 (`_page_texts` takes the callback);
2. `(i, pages, STAMPING)` after each page is stamped or kept unstamped, `i` from 1;
3. `(pages, pages, SAVING)` once, immediately before `out.save`.

The percent-of-100 calls and their messages go. A callback may raise `ProcessingCancelled`; it passes
through the function's own handlers (it is a `PDFProcessorError`), and the source PDF is closed. Nothing is
written before `out.save` and nothing is called after the `SAVING` call returns, so a cancelled run leaves no
file and a run that has begun saving always finishes.

### 7.2 `shopify_tool/barcode_processor.py`

```python
def packing_list_orders(xlsx_path) -> frozenset
```

The `Order_Number` values of a packing list workbook, as `pd.read_excel` gives them, without blanks. It
raises `ValueError` when the sheet has no `Order_Number` column.

```python
def generate_list_labels(orders_df, folder, list_stem, *, qr=False,
                         progress: Callable[[str], None] | None = None) -> dict
```

The body of today's `_generate_barcodes_worker` (one row per order with its item count and merged tags,
sorted with `sort_for_packing_list`, then `generate_barcodes_batch`), followed by the two renders that
today run in the completion slot:

1. `progress("Writing {n} barcode labels…")`, then `generate_code128_labels_pdf(successful,
   barcode_pdf_path(folder, list_stem))`. A failure raises `BarcodeGenerationError`.
2. With `qr`: `progress("Writing {n} QR labels…")`, then `generate_qr_labels_pdf(...)`. A failure is logged
   and reported as `qr_failed`; the barcode PDF stands.

`n` is the number of successful records. With none, nothing is rendered. It returns:

```python
{"list": list_stem, "folder": str(folder), "labels": n, "failed": <failed records>,
 "pdf": <path or None>, "qr_pdf": <path or None>, "qr_failed": bool}
```

## 8. Deleted

- `gui/reference_labels_widget.py`, `gui/barcode_generator_widget.py`, `gui/components/print_options.py`
  (with `print_summary` and `LABEL_WIDTH`), and `PrintOptions` in `gui/components/__init__.py`.
- In `gui/tools_widget.py`: `primary_holder`, the event filter, the width breakpoint. Each card draws its
  own primary now, as the mockup does.
- The signals nothing listened to: `processing_complete`, `generation_complete`.
- Tests of what is gone: `test_tools_cards.py`, `test_tools_theme.py`, `test_reference_labels_widget.py`,
  `test_barcode_generator_widget.py`, `test_print_options.py`, `test_print_summary.py`. `test_tools_page.py`
  is rewritten as the page's test (§11).

## 9. Errors

| failure | where the operator sees it |
|---|---|
| A picked PDF cannot be opened, or has no pages | Under the Labels PDF field; Process is disabled |
| A picked CSV has no usable rows, or cannot be read | Under the Mapping CSV field; the same |
| A reference run fails | The window's error banner, under the command bar: "The PDF wasn't processed" and what to do |
| A reference run found duplicate or missing REFs | The footer reason, in the warning tone, until an input changes |
| A packing list cannot be read | The list's count reads "Unreadable"; the reason says so; Generate is disabled |
| The packing lists cannot be listed at all | The window's error banner: "The packing lists weren't read" |
| Some order numbers cannot be encoded | The footer reason, in the warning tone; the labels that could be written are |
| The barcode PDF cannot be rendered | The window's error banner: "The barcode PDF wasn't created" |
| The QR PDF cannot be rendered | The footer reason, in the warning tone; the barcode PDF stands |
| Raw ZPL with no printer | The help line, in the danger tone; Print is disabled |
| Printing fails | The window's error banner: "Nothing was printed" (unchanged) |

The error banner is the Qt one in the window's slot above the page, so it is not behind the view.

## 10. Departures from the mockup

| Mockup | Phase 5 | Why |
|---|---|---|
| "No Reference column": "The header row has Order, Tracking and Date" | "This CSV has no usable rows", naming the four column positions | The CSV is read by position; its header is never checked |
| "120 labels, 120 references matched." before a run | "120 pages, 120 CSV rows." before; "118 of 120 labels matched…" after | Matching is the run |
| A PDF is never flagged | A PDF that cannot be opened is flagged under its field | The same check, for free, in place of an error after Process |
| "Writing labels — 40 of 120", a bar and Cancel on Barcode | "Writing 120 barcode labels…", no bar, no Cancel | Owner, §2: one render call |
| "Stamping labels — 40 of 120" as the only phase | "Reading labels", then "Stamping labels", then "Saving…" | Reading the pages is the slower half; one bar spans both |
| Print is live whenever the card is ready; "Process, then open the print dialog" | Print prints what exists | Owner, §2 |
| Change… on Barcode's output folder | Read-only text | Owner, §2 |
| The printer menu only in Raw ZPL | In both modes; "Windows default" first in Driver | Driver mode has a saved printer too (owner, §2) |
| "Zebra ZD421  USB001" | The printer's name only | Qt does not report a printer's port |
| No label size, rotate or invert | The Label setup fold, with a free-text target | Owner, §2. The free-text target keeps a `\\server\printer` path and a dev machine's device path possible |
| "Print QR labels" appears with the checkbox | Also whenever the list has a QR PDF on disk | Print what exists |
| "No packing lists yet. Run analysis, then Refresh." | "…Generate one on Results, then Refresh." | Packing lists are made on Results, not by the analysis |
| The toast's path in mono | One plain sentence | The bridge's toast carries one string |
| A dimmed checkbox (`opacity`) with no session | The kit's disabled checkbox | Opacity is banned (ADR 0016) |
| 28px controls, a 2-column grid at any width | `--control-height`; one column under 900px | The density token; a narrow window |
| The row label is 112px, regular, secondary | The same, as an override of the kit's `.form-row` (160px, bold) | The cards are half the page wide; the kit row was sized for Setup's full-width card |
| The session chip only in the page head | The same: the bar hides its chip on Tools | The page head now exists |
| Segoe UI, Consolas; a 44px bar | Inter and the theme's mono face; 48px | Phases 1 and 3 |

Kept though the mockup does not draw them: the "Replace barcodes for {list}?" confirmation, the duplicate
and missing REF warning, "Cancelling…", the reason lines for an unreadable list and for failed order numbers.

Not in the approved design, and dropped on the facts: the banner's no-client wording. The rail does not
offer Tools without a client.

## 11. Tests (test-first; the seams)

| Seam | File | Asserts |
|---|---|---|
| State: session and banner | `test_tools_state.py` (new) | With no session: `banner` true, `session` `{}`, both cards `quiet`, folder "Session folder" muted. With one: the meta before and after analysis |
| State: reference | `test_tools_state.py` | Each row of §4.3's reason table from the facts that select it, with its tone; `can_run`; the row `meta`s and problems; the short path; the run's label, count, percent and Cancel for each phase |
| State: barcode | `test_tools_state.py` | Each row of §4.4's reason table; `list` and `lists` for loading, none, one selected, an unreadable one; `can_run`; `qr_button` present and enabled on its rule |
| State: print | `test_tools_state.py` | Both modes' `printers`, `printer`, `help` and tone; a saved name that is not installed is listed; the four `summary` forms; the print button's label, title and `enabled` for every row of §4.3 |
| Print edits | `test_tools_state.py` | `apply_print_edit` for every key; `printer` writes the mode's own key; clamping and rounding; a bad key, a bad mode, a bool as a number and a number as a bool give `None`; the input dict is not changed |
| Bridge | `test_tools_bridge.py` (new) | Each slot emits its signal with its arguments; an unknown tool, kind, option, key or `what` is dropped; `set_state` emits once for a change and not for the same dict |
| PDF processor | `test_pdf_processor.py` | A run calls `progress_callback` with `READING` 1..N, `STAMPING` 1..N, then one `SAVING`; a callback raising `ProcessingCancelled` during `STAMPING` writes no file and raises it; `pdf_page_count` for a good PDF, a damaged one and an empty one; `load_csv_mapping` returns `rows` |
| Barcode processor | `test_barcode_processor.py` | `packing_list_orders` for a good workbook and one with no `Order_Number`; `generate_list_labels` writes the barcode PDF and reports `labels`; with `qr` it writes both and calls `progress` twice; a QR failure sets `qr_failed` and keeps the barcode PDF; a barcode render failure raises; label numbers follow the packing-list order (today's worker tests, moved) |
| Reference tool | `test_reference_tool.py` (new) | `load` sets the count or the problem for each kind and drops the result; `set_session` clears the picks and sets the folder; `start` is a no-op unless ready; a result sets the output and emits the toast, and a warning result emits none; `cancel` makes `_report` raise; a `ProcessingCancelled` error toasts and shows no error banner; each error type's sentence; `print_output` passes the scope's settings |
| Barcode tool | `test_barcode_tool.py` (new) | `read_packing_lists` counts Fulfillable orders, flags an unreadable file, sees the PDFs on disk, and reads an unchanged file once (the cache); `reload` keeps the selection or moves to the first list, and drops a stale result; `start` asks before replacing and stops on No; a result updates `has_labels` and emits the toast; a failed result is kept for the footer; `print_labels` picks the right PDF |
| Widget | `test_tools_widget.py` (new) | `sync()` hands a changed session to both tools and pushes; a print edit saves and pushes; a bad one saves nothing; a toast with a folder while visible reaches the bridge with the flag, and `openFolder` opens that folder; hidden, it goes to the router |
| Page: frame | `test_tools_page.py` (rewritten) | Through a real Chromium: the theme marker once; the kit linked first; the head with and without a session; the banner and its two buttons calling `newSession` and `openRecent`; two cards side by side at 1166 and stacked at 800 |
| Page: reference | `test_tools_page.py` | Choose, Replace and Change… call their slots; a picked row shows name and meta; a problem shows the banner, the danger glyph and meta, and the link calling `chooseFile`; the checkbox calls `setOption`; everything in §5.7's first column is disabled when quiet |
| Page: barcode | `test_tools_page.py` | The select's value and meta, and its placeholder; the menu opens, lists the counts, marks the selected one, and a choice calls `chooseList` and closes; Escape and an outside click close it; Refresh calls `refreshLists`; the QR button appears with `qr_button` |
| Page: print mode | `test_tools_page.py` | A segment click calls `setPrint(tool, "mode", …)`; the printer menu calls `setPrint(tool, "printer", …)`; the help text and its danger colour; the fold opens and closes and stays open across a state push; each fold control calls `setPrint` with a typed value on `change`; an empty number sends 0 |
| Page: footer | `test_tools_page.py` | The reason and its two tones; the primaries' `disabled` and their slots; the print buttons' label, title and `disabled`; a counted run shows the line, the fill's width and Cancel, with Cancel disabled on "Saving"; an uncounted run shows the label alone; a locked card's controls are disabled and the other card's are not |
| Page: toast | `test_tools_page.py` | `raise_toast(text, True)` shows the text and Open folder, which calls `openFolder`; with false the action is hidden; `#toast-dismiss` hides it |
| Kit | `test_web_kit.py` | On the sheet, in both themes: the select's edge, its open edge, its disabled fill and dashed edge, the placeholder's colour; a disabled unchecked segment's colour; a disabled field's fill |
| Shell | `test_shell.py`, `test_toast_router.py` | Tab 4 holds a `ToolsWidget` with a web view; the inset is 0 on Tools; the bar's chip is hidden on Tools and shown on Browse; `refresh_setup` reaches `tools_widget.sync`; on Tools a `toast(window, …)` reaches the tools bridge; the banner's requests reach New session and the recent menu |
| Printing | `test_pdf_printing.py` | The reworded sentence |
| Lint | `test_style_literals_guard.py` | unchanged: `gui/` scans clean with the three new assets |

Every test that pins what this spec changes is rewritten to the new behaviour in the same commit as the
change, never skipped. No test runs a real `Worker` thread: each tool takes the pool its workers start on
(§6.2), and the tests hand it one that captures the worker, then call the worker's function or the tool's
result slot directly.

**Visual check (required, CLAUDE.md):** render the page through `QWebEngineView.grab()` at 1166×720, in
light and dark, in each state: no session, ready (Reference in Driver, Barcode in Raw ZPL), mapping problem,
reference running (stamping, 40 of 120), barcode running, the packing list menu open, Label setup open, and
the done toast. Render the kit sheet in both themes, and `MainWindow` on Tools in both themes for the bar.
Compare with `mockups/renders/tools.png` and the mockup's other states opened in Chrome. Save the light
Ready, the dark Ready, the light Mapping problem and the light No session under
`docs/design/ui-refresh/renders/phase5/` and attach them to the PR.

**Gate:** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` and `ruff check .`, then
`graphify update .`.

## 12. Docs

- `CONTEXT.md`:
  - **Web tier**: Results, Setup, Browse and Tools today.
  - Add **Tools state**: the one map Python builds for the Tools page: the session, each card's rows, its
    print block, its footer's reason and what is enabled. The page draws it and decides nothing.
  - Add **Tool card**: one tool on the Tools page, with its inputs, its print mode and its footer.
  - **Print options**: a tool's print mode, its printer, and its label setup. Stored on the PC.
  - Add **Label setup**: the Raw ZPL settings a tool keeps behind a fold: the target, the label size, rotate
    and invert.
- ADR 0016, Consequences: Tools moved in phase 5 with the fourth bridge, `ToolsBridge`, and a fourth view,
  on the phase 3 measurement.
- `docs/design/ui-refresh/roadmap.md`: phase 5 gets its spec and plan paths and the differences from the
  list (Barcode has no count and no Cancel, Print prints what exists, Barcode's folder is fixed, Label
  setup, the CSV problem's real wording, the chip in the page head on Tools).
- `.github/workflows/build_release.yml`: the bundle check also looks for `tools.html`.

## 13. Out of scope

- Dropping a PDF or a CSV onto a card. A count or Cancel for Barcode (chunked rendering). Change… for
  Barcode's folder. Remembering the two "Open the PDF" checkboxes between launches.
- Logs, Client settings. A printing page in Client settings. The Qt error banner's look. Packing Tool.

## 14. Delivery

One PR on `cognitiveghost/shopify-fulfillment-tool` from `dr/17-ui-refresh-phase-5-move-tools-to-the-web`.
No Packing Tool PR: nothing in `shared/` changes.

The PR body repeats the Windows check phase 3 set for the release build (memory with one more view, and the
time to a drawn page), and adds one for this phase: on a warehouse PC, print one reference label and one
barcode label in each print mode.
