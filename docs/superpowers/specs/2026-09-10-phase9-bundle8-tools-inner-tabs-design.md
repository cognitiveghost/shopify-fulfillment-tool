# Phase 9 Bundle 8 — Tools loses its inner tabs

**Date:** 2026-09-10
**Item:** 9.22, alone
**Todoist:** bundle `6hQXj6vc5gcvWxQV`, item `6hQVj53cx9qmJWXV`
**Artboards:** D5, D5b and D5c. This spec works from the roadmap
(`docs/superpowers/plans/2026-09-03-phase9-roadmap.md` § 9.22) and the Todoist
brief, not from the canvas, as the phase parent instructs. §9 lists the
departures.

**Classification:** architectural. The page's layout moves to `ToolsWidget`, a
duplicated settings block becomes one component, and the page gains a width
breakpoint. There is no new dependency, no `shared/` change and no new token.

---

## 1. What ships today

`ToolsWidget` (`gui/tools_widget.py`, 54 lines) is a `QTabWidget` inside the
rail's Tools destination, with two tabs:

| Tab | Widget | Group boxes |
|---|---|---|
| Reference Labels | `ReferenceLabelsWidget` | File Selection, Output Settings, Processing |
| Barcode Generator | `BarcodeGeneratorWidget` | Packing List Selection, Options, Generate Barcodes |

Both widgets carry the same **print options** block, about 80 lines each. The
copies differ only in the settings scope (`reference_labels` or
`barcode_generator`) and one tooltip. Each block holds five controls: a
print-mode combo, a Raw ZPL target, a rotate checkbox, a label-size pair and a
driver-printer combo. All five are always visible, and
`_update_zpl_controls_enabled` greys out four of them depending on the mode.

`BarcodeGeneratorWidget.generate_btn` has a hardcoded `status_success` green
stylesheet. It is a primary button drawn by hand, outside the role system.

No code outside the two widgets and `ToolsWidget` reads their controls. The one
exception is `tests/test_reports_sku_labels_removed.py`, which reads the source
of `ToolsWidget._init_ui` with `inspect.getsource`. **The method name
`_init_ui` must survive.**

---

## 2. The page

```
┌ Tools page (1310 wide at 1366) ─────────────────────────────────────────┐
│ 12 ┌ Card: Reference labels ───────┐ 12 ┌ Card: Barcode labels ──────┐ 12│
│    │ title, one-line description   │    │ title, one-line description│   │
│    │ Labels PDF     [Select PDF…] n│    │ Packing list  [combo][Refr]│   │
│    │ Mapping CSV    [Select CSV…] n│    │               142 orders…  │   │
│    │ Output folder  path  [Change…]│    │ Output folder path         │   │
│    │                ☑ Auto-open    │    │               ☑ QR  ☑ Auto │   │
│    │ ▸ Prints through the dialog…  │    │ ▸ Prints raw ZPL to …      │   │
│    │           (stretch)           │    │          (stretch)         │   │
│    │ status / progress             │    │ status / progress          │   │
│    │          [Print…] [Process]   │    │ [QR…][Print…] [Generate]   │   │
│    └───────────────────────────────┘    └────────────────────────────┘   │
│                              (stretch)                                    │
└──────────────────────────────────────────────────────────────────────────┘
```

- **Scroll area.** `ToolsWidget` holds a `QScrollArea` with `widgetResizable`,
  `NoFrame` and `ScrollBarAlwaysOff` on the horizontal axis. Its content widget
  has a `QVBoxLayout` holding one `QBoxLayout`, the **card row**, and a trailing
  stretch.
- **Card row.** Two `Card(margins=(16, 16, 16, 16), spacing=12)` sit in the row
  at stretch 1 each. The row has 12px spacing (`spacing_md`) and 12px content
  margins. 12 + 637 + 12 + 637 + 12 = 1310, so side by side is the 1366 case.
- **Widgets inside cards.** Each widget goes into its card through
  `Card.add_widget`, the way the setup card adds its `FormSection`. The widgets
  are plain `QWidget`s with zero margins and paint no background of their own.
- **Side by side.** A horizontal box gives every item the full row height, so
  the two cards come out equal in height. Each widget puts a stretch above its
  action row, so both action rows sit on one baseline. Extra page height goes to
  the trailing stretch, not into the cards.
- **Stacked.** Each card takes its size hint, and the trailing stretch absorbs
  the rest.
- **Breakpoint.** `resizeEvent` calls `_apply_width(self.width())`. Below
  `_STACK_BELOW = 1180` it sets `QBoxLayout.TopToBottom`; at 1180 or wider it
  sets `LeftToRight`. It calls `setDirection` only when the direction actually
  changes. It never uses a `QStackedLayout`, which would fork the widgets.
- **Minimum widths.** Nothing inside a card may set a minimum width that stops
  both cards fitting at 1180, which allows (1180 − 36) / 2 = 572px per card.
  The shipped `packing_list_combo.setMinimumWidth(250)` and
  `select_*_btn.setMinimumWidth(150)` are deleted; the label gutter keeps the
  fields aligned instead.
- **Paths elide, they do not wrap.** A word-wrapped `QLabel` can only break at
  spaces, and a UNC session path has none. Its minimum width is therefore the
  whole path, which is wider than 572px, so it would push a card past the
  viewport, where `ScrollBarAlwaysOff` clips it. The path and file-name labels
  (`output_dir_label` in both widgets, `pdf_label`, `csv_label`) become
  `ElidedLabel` (`gui/components/elided_label.py`): a `QLabel` whose minimum
  width is 0, which elides the middle of its text (`Qt.ElideMiddle`, so the
  share and the file name both stay visible), and which carries the full text
  as its tooltip. `full_text()` returns the unelided string. The app has no
  eliding label today; `status_edge_delegate.py` elides inside a delegate,
  which is not reusable for a widget.
- **Deleted.** The `QTabWidget` import, `sub_tabs` and the 5px margins.

`_create_tab5_tools` in `gui/ui_manager.py` is unchanged except for its
docstring, which still calls the Barcode Generator a placeholder.

---

## 3. Each card

Each widget replaces its three `QGroupBox` builders with one `FormSection`,
with the title and description listed below. Both cards and the print options
use `label_width=120`, so the fields in both cards start at the same inset.
The order inside a card is fixed: **inputs → print options → stretch → status →
actions.**

### Reference labels (`ReferenceLabelsWidget`)

| Row | Field |
|---|---|
| title | `Reference labels` |
| description | `Stamps each courier label with its order's reference number.` |
| `Labels PDF` | `select_pdf_btn` (`Select PDF…`) and `pdf_label`, in one `QHBoxLayout` |
| `Mapping CSV` | `select_csv_btn` (`Select CSV…`) and `csv_label` |
| `Output folder` | `output_dir_label` and `change_dir_btn` (`Change…`) |
| *(no label)* | `auto_open_checkbox`, reading `Open the PDF when it's ready` |

Below the rows come `PrintOptions("reference_labels", …)` and a stretch. The
status block holds `progress_bar` (hidden) and a left-aligned `status_label`.
The right-aligned action row holds `print_btn` (`Print…`), then `process_btn`
(`Process Labels`).

### Barcode labels (`BarcodeGeneratorWidget`)

| Row | Field |
|---|---|
| title | `Barcode labels` |
| description | `One label for every Fulfillable order in a packing list. Each list gets its own folder.` |
| `Packing list` | `packing_list_combo` and `Refresh` |
| *(no label)* | `order_count_label` |
| `Output folder` | `output_dir_label` |
| *(no label)* | `add_qr_checkbox` (`Add QR labels (order number)`) and `auto_open_pdf_checkbox` (`Open the PDF when it's ready`) |

Below the rows come `PrintOptions("barcode_generator", …)`, a stretch and the
same status block. The action row holds `print_qr_btn` (`Print QR labels…`),
`print_btn` (`Print…`) and `generate_btn` (`Generate Barcode Labels`).

The old info label ("Barcodes will be generated for…") becomes the section
description. `generate_btn`'s hand-drawn green stylesheet is **deleted**; §5
gives the button its role.

### What does not change

- **Attributes.** Every attribute that the existing tests' `_FakeWidget`s
  reference keeps its name and behaviour.
- **Methods.** Every processing, generation, printing, session and readiness
  method keeps its behaviour. That covers `_update_process_button`,
  `_on_packing_list_changed`, `_on_processing_complete`,
  `_on_generation_complete`, the workers and `_on_print_clicked`.
- **Settings scopes.** `reference_labels` and `barcode_generator` are persisted
  `QSettings` keys and stay exactly as they are, even though the visible name
  is now "Barcode labels".

### Empty and error state copy

These strings live in builders and state methods this bundle rewrites.
Message-box copy is left alone, because it belongs to Bundle 9.

| Where | Today | After |
|---|---|---|
| `pdf_label`, empty | `No PDF selected` | `No file chosen` |
| `csv_label`, empty | `No CSV selected` | `No file chosen` |
| `output_dir_label`, no session | `No session selected` | `Open a session to save labels into it` |
| `output_dir_label`, error | `Error accessing session directory` | `Can't reach this session's folder. Check the server connection.` |
| `order_count_label`, no lists | `No packing lists generated yet` | `No packing lists in this session yet. Generate one from Analysis Results.` |
| Barcode `output_dir_label`, no list | `No packing list selected` | `Choose a packing list` |

Button labels keep their names. The floor already knows them, and renaming the
success dialogs that echo them is Bundle 9's job.

---

## 4. Print options — one component

`gui/components/print_options.py` defines `PrintOptions(QWidget)`, exported
from `gui/components/__init__.py`.

**Why a component rather than two edits.** Apply the deletion test: delete the
component and the same 80 lines reappear in both widgets, each copy repeating
the visibility rule, the save wiring and the summary. Two real callers mean the
component earns its keep.

**Interface:**

```python
class PrintOptions(QWidget):
    changed = Signal()                      # after every save
    def __init__(self, scope: str, *, label_size_tooltip: str, parent=None): ...
    def current_settings(self) -> dict      # the dict save_print_settings takes
    def is_open(self) -> bool
    def set_open(self, open_: bool) -> None
    # child handles, kept public for tests:
    #   fold_button, body, print_mode_combo, raw_zpl_target_edit,
    #   raw_zpl_rotate_check, raw_zpl_label_width_spin,
    #   raw_zpl_label_height_spin, driver_printer_combo

def print_summary(settings: dict) -> str   # pure, module level
```

**Structure.** A `QVBoxLayout` holds the **fold button** and, under it, the
**body**: a `FormSection("", label_width=120)` that is hidden while the fold is
closed. The body's rows:

| Row | Visible when |
|---|---|
| `Print mode` — `print_mode_combo` | always |
| `Printer` — `driver_printer_combo` | mode is `driver` |
| `Raw ZPL target` — `raw_zpl_target_edit` | mode is `raw_zpl` |
| `Label size (mm)` — width spin, `×`, height spin | mode is `raw_zpl` |
| *(no label)* — `raw_zpl_rotate_check` (`Rotate 90°`) | mode is `raw_zpl` |

`_update_zpl_controls_visible()` calls `self.body.form.setRowVisible(field, …)`.
That hides a row's label and field together; PySide6 6.11.2 has it. The method
replaces `_update_zpl_controls_enabled`, and **no control is disabled by mode
any more**. A hidden row is simply hidden, and the form reflows on its own.

**Fold button.** A checkable `QToolButton` with
`setToolButtonStyle(Qt.ToolButtonTextBesideIcon)` and `setAutoRaise(True)`.

- **Arrow.** `setArrowType(Qt.RightArrow)` when closed, `Qt.DownArrow` when
  open.
- **Text.** `print_summary(current_settings())`, repeated as the tooltip.
- **Width.** The horizontal size policy is `Ignored`, so a long target can
  never force the card wider; the tooltip carries the full text.
- **Accessibility.** `setAccessibleName("Print options")`.
- **Toggling.** `toggled` connects to `set_open`, which sets the body's
  visibility and the arrow.
- **Initial state.** The fold starts **closed** every time; the state is not
  persisted. The summary exists so that nobody opens the fold to check a value.
- **Motion.** None. QSS has no transitions, and a fold that snaps is honest.

**Saving.** Every edit signal that calls `_save_print_settings` today calls
`self._on_edited` instead. It runs `save_print_settings(scope,
current_settings())`, refreshes the button text and tooltip, and emits
`changed`. The widgets' own `_save_print_settings` methods are deleted.
`print_pdf(…, load_print_settings(scope))` at print time is unchanged, and it
reads what was just saved.

**`print_summary` wording.** It reads as a sentence, not as values joined by
dots.

| Settings | Text |
|---|---|
| driver, printer `""` | `Prints through the print dialog to the Windows default printer` |
| driver, printer `Zebra GK420` | `Prints through the print dialog to Zebra GK420` |
| raw_zpl, target `""` | `Raw ZPL needs a printer target. Open to set one.` |
| raw_zpl, target `ZPL-RAW`, size 0 × 0, no rotate | `Prints raw ZPL to ZPL-RAW at the PDF's page size` |
| raw_zpl, target `ZPL-RAW`, 152.4 × 101.6, rotate | `Prints raw ZPL to ZPL-RAW at 152.4 × 101.6 mm, rotated 90°` |

A size is stated only when **both** dimensions are non-zero; otherwise the
summary says "the PDF's page size". Numbers are formatted with `:g`, so `68.0`
renders as `68`.

**Styling.** `build_stylesheet` has no `QToolButton` rule, and `shared/` is not
hand-edited here, so the fold button styles itself. It follows the
`_style_results_overflow` precedent and goes through `on_theme_changed`
(ADR 0003):

```
QToolButton { background-color: transparent; border: 1px solid transparent;
              border-radius: {radius}px; padding: 4px 6px; color: {text_secondary}; }
QToolButton:hover { background-color: {hover}; color: {text}; }
QToolButton:focus { border-color: {focus_ring}; }
```

The transparent background is load-bearing. Without it, the global
`QWidget { background-color: surface }` rule paints a `surface` patch on the
card's `surface_raised` plane.

---

## 5. One primary, and it moves

Each card has one committing action: `process_btn` on the Reference card and
`generate_btn` on the Barcode card. **At most one of the two is `primary` at a
time.** Every other button on the page is secondary.

```python
def primary_holder(reference_ready: bool, barcode_ready: bool,
                   current: str | None) -> str | None:
    """'reference', 'barcode', or None."""
```

| reference_ready | barcode_ready | result |
|---|---|---|
| True | False | `reference` |
| False | True | `barcode` |
| True | True | `current` if it is set, otherwise `reference` |
| False | False | `None`, and both buttons are secondary |

- **Ready** means the card's action button `isEnabled()`. That is already each
  widget's own verdict (`_update_process_button`, `_on_packing_list_changed`),
  so readiness is read, not recomputed.
- **Both ready.** The current holder keeps the primary, so a button never
  changes weight under the cursor because the *other* card became ready.
- **Neither ready.** A disabled primary is one nobody can press, so the page
  shows none.

**Mechanism.** `ToolsWidget` installs itself as an event filter on both action
buttons. On `QEvent.EnabledChange` it recomputes `primary_holder` and calls
`set_button_role(button, "primary" | "secondary")`, but only on a button whose
role actually changes. It also runs once after construction. Neither widget
gains a signal or any knowledge of the other, and every existing `setEnabled`
path, including disable-while-running, is covered without touching it.

During a run, the running card's button is disabled. If the other card is
ready, it takes the primary. That is correct, because it is then the only thing
on the page that can run.

---

## 6. Theme

**No new tokens.** The component reads `text_secondary`, `text`, `hover`,
`focus_ring` and `radius`; the page reads `surface_raised` through the `Card`
rule. Those tokens define both themes.

ADR 0003 applies to the stylesheets this bundle writes **once, at build
time**: each one goes through `on_theme_changed`. That covers the fold button
and, in the Barcode card, `order_count_label` and `output_dir_label`, whose
styles never change after construction.

The **state-driven** stylesheets stay event-time, as they are today. These are
the Reference card's file and output-folder labels (italic when empty, bold
once chosen) and both status labels (success, danger, info). A closure would
re-run the build-time style over a chosen file's bold, so they cannot use one.
Toggling the theme mid-session leaves them stale, exactly as it does today; the
Reference card's output label re-styles on its next `showEvent`.

---

## 7. Testing seams

`row_widget(*widgets, stretch=None)` in `gui/components/form_section.py` lays
several widgets out as one form field: a file button beside its label, a combo
beside Refresh, two checkboxes. It exists so that neither card, nor the print
options' label-size row, hand-rolls a zero-margin `QHBoxLayout` wrapper.

| Seam | What it proves | Widget? |
|---|---|---|
| `ElidedLabel` | Minimum width is 0 for any text. A long path elides in the middle. `full_text()` and the tooltip keep the whole string. | offscreen |
| `row_widget` | The named widget takes the stretch; with none named, the row packs left | offscreen |
| `print_summary` | Every row of the §4 wording table | no |
| `primary_holder` | Every row of the §5 table | no |
| `PrintOptions` | Closed by default with the body hidden. `set_open(True)` shows the body. `raw_zpl` hides the printer row and shows target, size and rotate; `driver` does the reverse. An edit saves under the component's scope and updates the button text. | offscreen |
| `ReferenceLabelsWidget`, `BarcodeGeneratorWidget` | No `QGroupBox` descendant. Exactly one `PrintOptions`, with the right scope. `generate_btn.styleSheet() == ""`. | offscreen |
| `ToolsWidget` layout | No `QTabWidget` descendant, and two `Card`s. At 1310 wide the row is `LeftToRight` and the scroll content is no wider than the viewport. At 1100 the row is `TopToBottom`. | offscreen: `show()`, `resize()`, `processEvents()`, as in `test_session_setup_layout.py` |
| `ToolsWidget` primary | Readying Reference makes `process_btn` primary. Readying Barcode afterwards leaves the primary where it is. Disabling Reference moves it to `generate_btn`. Disabling both clears it. | offscreen |
| Theme | In both themes, a pixel inside the fold button matches the card's `surface_raised` | offscreen `grab()` |
| Existing tests | `test_reference_labels_widget.py`, `test_barcode_generator_widget.py` and `test_reports_sku_labels_removed.py` pass unmodified | — |

**Settings isolation.** A test that builds real widgets must not touch the
developer's real `QSettings("ShopifyFulfillmentTool", "Printing")`. A
`print_settings_store` fixture in `tests/conftest.py` monkeypatches
`load_print_settings` and `save_print_settings` in
`gui.components.print_options` onto an in-memory dict.

**Main window stand-in.** Tests build widgets with
`SimpleNamespace(session_path=None)` as the main window, which both widgets
already tolerate.

---

## 8. Done when

**9.22:**

- Both cards fit side by side at 1366×768 with no horizontal scroll.
- Raw ZPL hides the driver row.
- The stacked layout appears below 1180px.

**Bundle:**

- All three 9.22 criteria hold.
- The §7 tests exist.
- `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest` passes.
- `ruff check . --exclude shared` is clean.
- `graphify update .` has run.

---

## 9. Departures and decisions not in the brief

1. **Print options become one component (§4).** The brief says both widgets
   "keep their logic". Their processing, generation and printing logic does
   stay. The duplicated settings block moves, because otherwise the brief's own
   visibility rule would be written twice.
2. **"One action" means one committing action.** `Print…` and
   `Print QR labels…` stay beside it as secondaries, enabled by output exactly
   as today. Hiding them until an output exists would change the widgets'
   logic and break three existing tests.
3. **The primary's tie-break is sticky, and "neither ready" means no primary
   (§5).** The brief says the primary moves to "whichever card can actually
   run" and says nothing about both or neither.
4. **The folded row reads as a sentence (§4 table)**, not as
   `Raw ZPL · target · size`. A dot-joined meta string is template chrome, and
   a sentence can name the one missing value (the target) as the thing to do.
5. **Card titles move from title case to sentence case**, and "Barcode
   Generator" becomes "Barcode labels". Button labels keep their names (§3).
6. **The fold does not remember its state.** The brief does not ask for it,
   and the summary makes it unnecessary.
7. **`FileSlot` is not reused for the PDF and CSV inputs.** It models column
   validation and drag-and-drop, which these inputs do not have. Adopting it
   would change input logic the brief says to keep.

---

## 10. Out of scope

- Any `shared/` change, including a `QToolButton` rule in `build_stylesheet`.
  No token or icon is added, so `scripts/sync_shared.py` is not run.
- The `QMessageBox` success, confirm and error dialogs in both widgets, which
  are Bundle 9's (9.25).
- Event-time status-label stylesheets going stale on a theme toggle (§6).
- Renaming classes, files or settings scopes.
- A version bump.
