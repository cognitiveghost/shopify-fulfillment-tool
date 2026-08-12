# UI Design System Track 3 — Component Library & Layout Conventions — Design

Implements Track 3 of `docs/superpowers/specs/2026-08-11-ui-design-system-vision-design.md`,
consuming Track 1's `TYPE_SCALE` (PR #268) and Track 2's `icon()` (PR #269).

## What changed since the vision doc was written

Two of the vision doc's three Track 3 items rest on premises that no longer hold. Both
were re-checked against the code on 2026-08-12 and the scope below reflects the answers,
not the original framing.

**`FormSection`'s motivating example is gone.** The vision doc justifies it as replacing
"the `QGroupBox` + `QVBoxLayout` + redundant-`QLabel` pattern the 2026-08-11 Phase 5 doc
flagged in the Add Product dialog". PR #267 already rewrote that dialog to a single
`QFormLayout` (`gui/add_product_dialog.py:66-100`) — the three stacked group boxes do not
exist anymore. Its only remaining consumer is Track 4's Settings Hub, which is blocked on
Track C. **Decision: `FormSection` is deferred to Track 4**, so its API is shaped by a real
consumer rather than guessed at with no caller.

**The stated button-placement convention fights the platform.** The vision doc specifies
"primary action bottom-right, cancel/secondary bottom-left in every dialog". This app is
Windows-only, and the Windows convention groups commit buttons together at the bottom
right — which is exactly what `QDialogButtonBox` produces under Qt's `WinLayout`, along
with Esc→reject, Enter→default, and correct keyboard traversal order. Four files in `gui/`
already use it. **Decision: the convention is "use `QDialogButtonBox`", overriding the
vision doc's left/right split.** This makes the convention a deletion rather than a new
helper widget: converting a hand-rolled footer removes code.

Both decisions were confirmed by the user before this document was written.

## Scope

Three deliverables.

### 1. `Card` — `gui/components/card.py`

`gui/ui_manager.py` builds three near-identical elevated containers:

| builder | line | margins | spacing | min width | rows |
|---|---|---|---|---|---|
| `_make_stat_card` | 1588 | 12,8,12,8 | 2 | — | `display`, `caption` (wrapped) |
| `_make_courier_card` | 1610 | 12,8,12,8 | 1 | 100 | `display`, `caption`, `caption` |
| `_make_tag_card` | 1637 | 6,4,6,4 | 2 | 60 | `label` + badge fill, `caption` (wrapped) |

Every one is `QFrame(StyledPanel, Raised)` + `QVBoxLayout` + N centre-aligned `QLabel`s at
a `TYPE_SCALE` role. The differences are per-instance data, not different widgets.

```python
class Card(QFrame):
    def __init__(self, *, min_width: int = 0,
                 margins: tuple[int, int, int, int] = (12, 8, 12, 8),
                 spacing: int = 2, parent=None) -> None: ...

    def add_text(self, text: str, role: str = "body", *,
                 wrap: bool = False, css: str = "") -> QLabel: ...
```

`add_text` returns the `QLabel` because two of the three call sites keep a handle to
update the value live (`stat_card_labels`). `role` goes through `font_css()`, so an
unknown role raises `KeyError` at construction — same rule Track 1 and Track 2 set.
`css` appends caller-specific declarations, which exists solely for the tag card's
coloured count badge.

`margins` and `min_width` are constructor arguments rather than a `compact`/`normal` mode:
the tag card is deliberately dense (60px wide, inside a horizontal scroll strip), and
widening it to the stat card's padding would be a visible regression in the Statistics
tab. `_make_courier_card`'s `spacing=1` is not preserved — one pixel does not earn an
argument, and it takes the default 2.

**`ClientCard` is not migrated.** It shares the word "card" and nothing else: it is an
interactive list item with a fixed 70px height, hover and active states, a custom
`border-radius` and a left accent border, all driven from its own QSS and a
`theme_changed` hook. Folding it and a static stat tile into one base would mean picking
one of two genuinely different looks. Recorded here so it does not read as an oversight
later.

### 2. Dialog footers → `QDialogButtonBox`

Six `QDialog` subclasses lack `QDialogButtonBox`. Four have a real footer and convert:

| dialog | current footer | becomes |
|---|---|---|
| `add_product_dialog.AddProductDialog` | `_create_buttons`, `addStretch` + Cancel + Add Product | `Cancel` + `AcceptRole` button retitled "Add Product" |
| `column_config_dialog.ColumnConfigDialog` | Reset to Default / Cancel / Apply (`:1050-1059`) | `Reset` + `Cancel` + `Apply`-as-accept |
| `groups_management_dialog` | single Close (`:105`) | `QDialogButtonBox.Close` |
| `rule_test_dialog` | single Close (`:95`) | `QDialogButtonBox.Close` |

Two do **not** convert, because they have no footer — their buttons are in-body actions,
not commit buttons: `report_selection_dialog` (Generate Report / Generate Writeoff Report
Only, each inside its own content section) and `profile_manager_dialog` (Add New… /
Rename… / Delete, a list toolbar). `column_config_dialog.ColumnConfigPanel:264-268` is
likewise a panel body inside a `QWidget`, not a dialog footer, and is left alone.

The conversion also drops `AddProductDialog`'s inline override on its primary button
(`background-color: {theme.accent_blue}; color: white; padding: 8px 16px`). A button box's
default button already carries the style's own emphasis, and `color: white` is a hardcoded
colour of the kind `CLAUDE.md` forbids.

**The convention is enforced by a guard, not by documentation.** A new
`tests/test_dialog_button_guard.py` fails when any file defining a `QDialog` subclass
wires a `QPushButton` straight to `self.accept`/`self.reject`. This mirrors
`tests/test_icon_usage_guard.py`, which exists for the same reason: without it the next
dialog someone adds hand-rolls its own footer and the convention decays one widget at a
time. It carries that guard's meta-assertion too — a regex guard that matches nothing
passes vacuously forever, so the test asserts it can still see the call sites it is
meant to police.

### 3. Header icon buttons

`gui/ui_manager.py:166` and `:182` still render `"☰"` and `"⚙"` as button text — the two
Track 2 deliberately left alone. They become `icon("menu")` and `icon("settings")`, with
`menu.svg` and `settings.svg` vendored from Lucide 1.31.0 per `gui/assets/README.md`
(pin the tag; Lucide renames glyphs between releases).

`connection_btn` is currently a local in `_create_global_header`. It becomes
`self.mw.connection_btn` so it can join `UIManager._BUTTON_ICONS` and pick up the
`theme_changed` refresh; otherwise its icon would keep the old theme's colour after a
toggle. `tests/test_icon_usage_guard.test_ui_managers_icon_tables_are_vendored` then
covers both names with no new test.

Both buttons keep their tooltips and lose their text.

## Testing

- `tests/test_components_card.py` — construct a `Card`, assert the layout's margins and
  the point size `add_text` resolves from `TYPE_SCALE`, assert `css` is appended rather
  than replacing the role's font declarations, and assert an unknown role raises
  `KeyError`. No window needed.
- `tests/test_dialog_button_guard.py` — the source guard above, plus its
  can-actually-see-call-sites assertion.
- `tests/test_main_window_statistics.py` already drives `update_statistics_tab` through
  `stat_card_labels`; it must still pass unchanged, which is what proves the three
  migrated builders kept their label handles.
- Existing `tests/test_add_product_dialog.py` covers the converted dialog's behaviour and
  must pass without modification beyond whatever the button lookup requires.

Gate: `QT_QPA_PLATFORM=offscreen python -m pytest` and `ruff check . --exclude shared`,
using `.venv/bin/` binaries — bare `python`/`ruff` are not on `PATH` on this machine.

## Deliberately not in this track

- **`FormSection`** — deferred to Track 4, see above.
- **A global spacing/margin token scale.** Track 1 shipped `TYPE_SCALE` only. `Card` keeps
  its margins as its own defaults; a shared scale waits until a second component wants the
  same numbers, rather than being invented for one.
- **`ClientCard` migration** — see above.
- **`_BUTTON_ICONS` attribute-name validation**, the Minor left open by Track 2. It needs a
  real `MainWindow` fixture to hang an assertion on; `tests/` still has none
  (`test_main_window_statistics.py` uses a `_FakeMainWindow` stub), and Track 3 does not
  introduce one. Re-checked 2026-08-12, still deferred — next candidate is Track 4.
- **Any edit to `shared/theme.py`**, which is sync-owned by `packing-tool`.
