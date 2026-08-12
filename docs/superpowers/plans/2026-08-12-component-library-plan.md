# UI Design System Track 3 — Component Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Runner note:** the roadmap runner's Stage B declines the subagent-driven option and stays in-session with `superpowers:executing-plans`.

**Goal:** Give `gui/` its first shared component (`Card`) and one enforced dialog-footer convention (`QDialogButtonBox`), and finish the two header icon buttons Track 2 left as plain text.

**Architecture:** A new `gui/components/` package holds `Card`, a `QFrame` subclass that collapses the three hand-rolled elevated-container builders in `ui_manager.py`. Dialog footers move to Qt's own `QDialogButtonBox`, which places buttons per platform and wires Esc/Enter for free; a source-scanning guard test keeps new dialogs from hand-rolling their own. The `☰`/`⚙` header buttons become `icon("menu")`/`icon("settings")` and join `UIManager._BUTTON_ICONS` so they re-theme on toggle.

**Tech Stack:** Python 3, PySide6, pytest. No new dependencies.

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-08-12-component-library-design.md`. Read it before Task 1 — it records *why* `FormSection` is deferred and why the vision doc's left/right button convention was overridden.
- **Never hand-edit anything under `shared/`** — it is one-way synced from `../packing-tool` and the next sync silently overwrites it.
- **No hardcoded colours** in stylesheets. Use `gui/theme_manager.py` tokens (`theme.text`, `theme.text_secondary`, …). Never `#666`, `color: gray`, `color: white`.
- **Font sizes come from `TYPE_SCALE`** via `font_css(role)` / `apply_font(widget, role)` in `gui/theme_manager.py`. Never inline a raw `font-size:` declaration.
- **Icons come from `gui.icons.icon(name)`.** Never `QStyle.SP_*`. New glyph names must be vendored as SVG under `gui/assets/icons/` from **Lucide 1.31.0** (pin the tag — Lucide renames glyphs between releases; `filter` became `funnel` in 2025).
- **Python is not on `PATH` on this machine.** Use the absolute venv paths below — bare `python`/`ruff` fail with "command not found", and the system `python3` has no PySide6. The venv lives in the **main checkout**, not the worktree.
  - Tests: `QT_QPA_PLATFORM=offscreen /home/cognitiveghost/Desktop/Projects/shopify-fulfillment-tool/.venv/bin/python -m pytest`
  - Lint: `/home/cognitiveghost/Desktop/Projects/shopify-fulfillment-tool/.venv/bin/ruff check . --exclude shared`
- **No direct commits to `main`.** All work lands on `worktree-component-library` via PR.
- Run `graphify update .` once at the end (per `CLAUDE.md`), not per task.

---

### Task 1: `Card` component

**Files:**
- Create: `gui/components/__init__.py`
- Create: `gui/components/card.py`
- Test: `tests/test_components_card.py`

**Interfaces:**
- Consumes: `font_css(role)` and `TYPE_SCALE` from `gui/theme_manager.py` (Track 1, PR #268).
- Produces: `gui.components.card.Card`, with
  `Card(*, min_width: int = 0, margins: tuple[int, int, int, int] = (12, 8, 12, 8), spacing: int = 2, parent=None)`
  and `Card.add_text(text: str, role: str = "body", *, wrap: bool = False, css: str = "") -> QLabel`.
  Task 2 is the only consumer.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_components_card.py`:

```python
"""Construction tests for the Card component. No window needed."""
import pytest
from PySide6.QtWidgets import QApplication, QLabel

from gui.components.card import Card
from gui.theme_manager import TYPE_SCALE


@pytest.fixture(scope="module", autouse=True)
def _app():
    yield QApplication.instance() or QApplication([])


def test_defaults_match_the_stat_card_geometry_it_replaces():
    card = Card()
    margins = card.layout().contentsMargins()
    assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (12, 8, 12, 8)
    assert card.layout().spacing() == 2


def test_margins_and_min_width_are_per_instance():
    card = Card(min_width=60, margins=(6, 4, 6, 4))
    margins = card.layout().contentsMargins()
    assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (6, 4, 6, 4)
    assert card.minimumWidth() == 60


def test_add_text_returns_a_label_in_the_layout():
    card = Card()
    label = card.add_text("42", "display")
    assert isinstance(label, QLabel)
    assert label.text() == "42"
    assert card.layout().indexOf(label) == 0


def test_add_text_resolves_the_point_size_from_the_type_scale():
    card = Card()
    label = card.add_text("42", "display")
    assert f"font-size: {TYPE_SCALE['display'].size_pt}pt" in label.styleSheet()


def test_extra_css_is_appended_not_substituted_for_the_role():
    card = Card()
    label = card.add_text("7", "label", css="background-color: #9E9E9E; border-radius: 8px;")
    assert f"font-size: {TYPE_SCALE['label'].size_pt}pt" in label.styleSheet()
    assert "border-radius: 8px;" in label.styleSheet()


def test_wrap_is_off_by_default_and_opt_in():
    card = Card()
    assert card.add_text("x").wordWrap() is False
    assert card.add_text("x", wrap=True).wordWrap() is True


def test_an_unknown_role_raises_rather_than_rendering_at_some_default():
    card = Card()
    with pytest.raises(KeyError):
        card.add_text("x", "headline")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
QT_QPA_PLATFORM=offscreen /home/cognitiveghost/Desktop/Projects/shopify-fulfillment-tool/.venv/bin/python -m pytest tests/test_components_card.py -v
```
Expected: collection error — `ModuleNotFoundError: No module named 'gui.components'`.

- [ ] **Step 3: Create the package**

Create `gui/components/__init__.py`:

```python
"""Shared UI components. See docs/superpowers/specs/2026-08-12-component-library-design.md."""
```

- [ ] **Step 4: Implement `Card`**

Create `gui/components/card.py`:

```python
"""Elevated container for the Statistics tab's stat / courier / tag tiles.

ui_manager.py hand-rolled this same QFrame + centred-label stack three times
(_make_stat_card, _make_courier_card, _make_tag_card). The differences between
them were per-instance data -- margins, minimum width, which TYPE_SCALE role
each row uses -- not three different widgets.

gui/client_card.py is deliberately NOT built on this: it is an interactive list
item with hover/active states, a fixed height and its own border-radius QSS.
See the design doc for that call.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

from gui.theme_manager import font_css


class Card(QFrame):
    """A framed panel holding a vertical stack of centred labels."""

    def __init__(
        self,
        *,
        min_width: int = 0,
        margins: tuple[int, int, int, int] = (12, 8, 12, 8),
        spacing: int = 2,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.setFrameShadow(QFrame.Raised)
        if min_width:
            self.setMinimumWidth(min_width)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*margins)
        layout.setSpacing(spacing)

    def add_text(
        self, text: str, role: str = "body", *, wrap: bool = False, css: str = ""
    ) -> QLabel:
        """Append a centred label at a TYPE_SCALE role and return it.

        The label is returned because callers keep handles to the rows they
        update live (the Statistics tab's stat_card_labels).

        `css` appends caller-specific declarations after the role's font
        rules -- it exists for the tag tile's coloured count badge. An unknown
        `role` raises KeyError out of font_css(), matching the rule Tracks 1
        and 2 set: a typo fails in development, not invisibly in production.
        """
        label = QLabel(text)
        label.setAlignment(Qt.AlignCenter)
        label.setWordWrap(wrap)
        label.setStyleSheet(f"{font_css(role)} {css}".strip())
        self.layout().addWidget(label)
        return label
```

- [ ] **Step 5: Run the tests to verify they pass**

Run:
```bash
QT_QPA_PLATFORM=offscreen /home/cognitiveghost/Desktop/Projects/shopify-fulfillment-tool/.venv/bin/python -m pytest tests/test_components_card.py -v
```
Expected: 7 passed.

- [ ] **Step 6: Lint and commit**

```bash
/home/cognitiveghost/Desktop/Projects/shopify-fulfillment-tool/.venv/bin/ruff check . --exclude shared
git add gui/components tests/test_components_card.py
git commit -m "feat(components): add Card, the shared elevated-container widget"
```

---

### Task 2: Migrate the three `ui_manager` card builders onto `Card`

**Files:**
- Modify: `gui/ui_manager.py:1588-1666` (`_make_stat_card`, `_make_courier_card`, `_make_tag_card`)
- Test: `tests/test_main_window_statistics.py` (existing — must pass unchanged)

**Interfaces:**
- Consumes: `Card` from Task 1.
- Produces: no new public names. `_make_stat_card` keeps returning `tuple[Card, QLabel]` and the other two keep returning the card widget, so `_create_statistics_subtab` and `update_statistics_tab` are untouched.

- [ ] **Step 1: Add the import**

In `gui/ui_manager.py`, add alongside the other `gui.` imports:

```python
from gui.components.card import Card
```

- [ ] **Step 2: Replace the three builders**

Replace `gui/ui_manager.py:1588-1666` in full with:

```python
    def _make_stat_card(self, value: str, label: str) -> tuple:
        """Stat card: large value on top, small label below. Returns (widget, value_label)."""
        card = Card()
        value_lbl = card.add_text(value, "display")
        card.add_text(label, "caption", wrap=True)
        return card, value_lbl

    def _make_courier_card(self, courier_id: str, orders: str, repeated: str) -> Card:
        """Courier card: orders count on top, courier name in middle, repeated below."""
        card = Card(min_width=100)
        card.add_text(orders, "display")
        card.add_text(courier_id, "caption")
        card.add_text(f"{repeated} repeated", "caption")
        return card

    def _make_tag_card(self, tag: str, count: str, color: str | None = None) -> Card:
        """Tag card: colored count badge on top, tag name below."""
        if color is None:
            # ponytail: literal neutral badge-fill default, not a text color —
            # theme.text_secondary differs per theme; this is a background
            # fill, and no theme-invariant neutral-gray token exists.
            color = "#9E9E9E"
        # Denser than the default on purpose: these sit 60px wide in a
        # horizontal scroll strip.
        card = Card(min_width=60, margins=(6, 4, 6, 4))
        card.add_text(
            count,
            "label",
            css=f"color: white; background-color: {color}; border-radius: 8px; padding: 2px 6px;",
        )
        card.add_text(tag, "caption", wrap=True)
        return card
```

Two deliberate differences from the code being replaced, both intended:
- `_make_courier_card`'s `spacing=1` becomes the default `2`. One pixel does not earn a constructor argument.
- The `QFrame` return annotations become `Card`. Update the `QFrame` import only if nothing else in the file uses it — `_create_statistics_subtab` still uses `QFrame.NoFrame`, so **leave the import alone**.

- [ ] **Step 3: Run the statistics tests**

Run:
```bash
QT_QPA_PLATFORM=offscreen /home/cognitiveghost/Desktop/Projects/shopify-fulfillment-tool/.venv/bin/python -m pytest tests/test_main_window_statistics.py -v
```
Expected: PASS. This is the check that matters — it drives `update_statistics_tab` through `stat_card_labels`, so it fails if `_make_stat_card` stopped returning a live label handle.

- [ ] **Step 4: Run the full suite**

Run:
```bash
QT_QPA_PLATFORM=offscreen /home/cognitiveghost/Desktop/Projects/shopify-fulfillment-tool/.venv/bin/python -m pytest
```
Expected: all pass, same count as before this task plus Task 1's 7.

- [ ] **Step 5: Lint and commit**

```bash
/home/cognitiveghost/Desktop/Projects/shopify-fulfillment-tool/.venv/bin/ruff check . --exclude shared
git add gui/ui_manager.py
git commit -m "refactor(statistics): build the stat/courier/tag tiles from Card"
```

---

### Task 3: Dialog footers → `QDialogButtonBox`, with a guard

**Files:**
- Create: `tests/test_dialog_button_guard.py`
- Modify: `gui/add_product_dialog.py:120-145` (`_create_buttons`)
- Modify: `gui/column_config_dialog.py:1046-1088`
- Modify: `gui/groups_management_dialog.py:102-108`
- Modify: `gui/rule_test_dialog.py:91-98`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: no new names. `AddProductDialog.add_btn`, `ColumnConfigDialog.apply_button`, `ColumnConfigDialog.reset_button`, `ColumnConfigDialog.cancel_button` and `GroupsManagementDialog.close_btn` all keep pointing at real buttons, now owned by the button box.

**Why these four and not all six:** `report_selection_dialog` (Generate Report, Generate Writeoff Report Only) and `profile_manager_dialog` (Add New… / Rename… / Delete) have no footer — their buttons are in-body actions. `ColumnConfigPanel:264-268` is a panel body inside a `QWidget`, not a dialog footer. All three are left alone.

- [ ] **Step 1: Write the failing guard test**

Create `tests/test_dialog_button_guard.py`:

```python
"""A guard, not a unit test.

Qt's QDialogButtonBox places commit buttons per platform (on Windows: grouped
bottom-right) and wires Esc->reject / Enter->default for free. Without this
guard the next dialog someone adds hand-rolls its own addStretch() + QPushButton
footer and the convention decays one widget at a time -- the same failure mode
tests/test_icon_usage_guard.py exists to prevent for iconography.
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GUI_DIR = REPO_ROOT / "gui"

_FOOTER_WIRE = re.compile(r"clicked\.connect\(\s*self\.(accept|reject)\s*\)")


def _dialog_files():
    return [p for p in sorted(GUI_DIR.rglob("*.py")) if "QDialog)" in p.read_text(encoding="utf-8")]


def test_no_dialog_hand_rolls_its_footer_buttons():
    offenders = []
    for path in _dialog_files():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _FOOTER_WIRE.search(line):
                offenders.append(f"{path.name}:{lineno}: {line.strip()}")
    assert not offenders, (
        "Use QDialogButtonBox for dialog footers instead of wiring a QPushButton "
        "straight to accept/reject:\n" + "\n".join(offenders)
    )


def test_the_guard_scans_a_nonempty_set_of_dialogs():
    """A scan that finds no files to check passes vacuously forever."""
    assert len(_dialog_files()) >= 6


def test_the_guard_regex_matches_the_pattern_it_polices():
    """And a regex that matches nothing does too. These are the exact lines
    this task removed."""
    assert _FOOTER_WIRE.search("        close_btn.clicked.connect(self.accept)")
    assert _FOOTER_WIRE.search("        cancel_btn.clicked.connect(self.reject)")
    assert _FOOTER_WIRE.search("self.close_btn.clicked.connect( self.accept )")
    assert not _FOOTER_WIRE.search("self.panel.config_applied.connect(self._on_panel_applied)")
    assert not _FOOTER_WIRE.search("box.rejected.connect(self.accept)")
```

- [ ] **Step 2: Run it to verify it fails**

Run:
```bash
QT_QPA_PLATFORM=offscreen /home/cognitiveghost/Desktop/Projects/shopify-fulfillment-tool/.venv/bin/python -m pytest tests/test_dialog_button_guard.py -v
```
Expected: `test_no_dialog_hand_rolls_its_footer_buttons` FAILS listing three offenders — `add_product_dialog.py:128`, `groups_management_dialog.py:105`, `rule_test_dialog.py:95`. The other two tests pass.

- [ ] **Step 3: Convert `AddProductDialog`**

In `gui/add_product_dialog.py`, add `QDialogButtonBox` to the `PySide6.QtWidgets` import list and replace `_create_buttons` (lines 120-145) with:

```python
    def _create_buttons(self):
        """Footer: QDialogButtonBox places the buttons per platform and wires
        Esc->reject for free.

        `accepted` is connected to the validator rather than to accept(), so a
        failed validation keeps the dialog open -- _on_add_clicked calls
        accept() itself once the input is good.
        """
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.add_btn = box.button(QDialogButtonBox.Ok)
        self.add_btn.setText("Add Product")
        box.accepted.connect(self._on_add_clicked)
        box.rejected.connect(self.reject)
        return box
```

The old inline override on the primary button is dropped on purpose: a button box's default button already carries the style's own emphasis, and its `color: white` was a hardcoded colour of the kind `CLAUDE.md` forbids. `QHBoxLayout`, `QWidget` and `QPushButton` may now be unused in this file — check with ruff in Step 8 and remove them from the import list if so.

- [ ] **Step 4: Convert `ColumnConfigDialog`**

In `gui/column_config_dialog.py`, add `QDialogButtonBox` to the `PySide6.QtWidgets` import list, then replace lines 1046-1064 (`# Dialog-level buttons` through `main_layout.addLayout(button_layout)`) with:

```python
        # Dialog-level buttons. Reset and Apply carry ResetRole/ApplyRole, which
        # emit neither accepted nor rejected -- they are wired via clicked.
        button_box = QDialogButtonBox(
            QDialogButtonBox.Reset | QDialogButtonBox.Cancel | QDialogButtonBox.Apply
        )
        self.reset_button = button_box.button(QDialogButtonBox.Reset)
        self.reset_button.setToolTip("Reset all columns to default visibility and order")
        self.reset_button.clicked.connect(self.panel._on_reset)

        self.cancel_button = button_box.button(QDialogButtonBox.Cancel)

        self.apply_button = button_box.button(QDialogButtonBox.Apply)
        self.apply_button.setDefault(True)
        self.apply_button.clicked.connect(self._on_apply)

        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)
```

Keeping the three `self.*_button` assignments is load-bearing, not cosmetic: this class has a `__getattr__` proxy (line 1069) that forwards unknown attributes to `self.panel`, and the panel owns its own `apply_button`/`reset_button` — which this dialog *hides* at lines 1042-1043. Drop the assignments and `dialog.apply_button` silently resolves to a hidden panel button instead of raising.

Then replace `_on_cancel` (lines 1085-1088) with an override of `reject`:

```python
    def reject(self):
        """Revert on Esc as well as on Cancel.

        Previously only the Cancel button reverted; Esc went straight to
        QDialog.reject() and left the table's live view mutated.
        """
        self.panel.revert_config()
        super().reject()
```

- [ ] **Step 5: Convert `GroupsManagementDialog`**

In `gui/groups_management_dialog.py`, add `QDialogButtonBox` to the `PySide6.QtWidgets` import list and replace lines 102-108 with:

```python
        buttons_layout.addStretch()
        layout.addLayout(buttons_layout)

        # Close carries RejectRole, so it emits `rejected` -- but this dialog
        # has always closed via accept(), and callers may read exec()'s result.
        # Preserving accept() keeps that contract; changing it is out of scope.
        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        self.close_btn = button_box.button(QDialogButtonBox.Close)
        button_box.rejected.connect(self.accept)
        layout.addWidget(button_box)
```

The Create/Edit/Delete Group buttons above stay exactly where they are — they are content actions on a toolbar row, and only the Close button moves into the footer.

- [ ] **Step 6: Convert `RuleTestDialog`**

In `gui/rule_test_dialog.py`, add `QDialogButtonBox` to the `PySide6.QtWidgets` import list and replace lines 91-98 with:

```python
        # Close button. Same accept()-not-reject() preservation as
        # groups_management_dialog: this dialog has always closed via accept().
        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(self.accept)
        layout.addWidget(button_box)
```

The hand-rolled `QHBoxLayout` + `addStretch()` + `setMinimumWidth(100)` all go away — the button box handles placement and sizing.

- [ ] **Step 7: Run the guard and the dialog tests**

Run:
```bash
QT_QPA_PLATFORM=offscreen /home/cognitiveghost/Desktop/Projects/shopify-fulfillment-tool/.venv/bin/python -m pytest tests/test_dialog_button_guard.py tests/test_add_product_dialog.py tests/test_column_config_dialog.py -v
```
Expected: all pass. `test_no_dialog_hand_rolls_its_footer_buttons` is now green because all three offending lines are gone.

- [ ] **Step 8: Run the full suite and lint**

Run:
```bash
QT_QPA_PLATFORM=offscreen /home/cognitiveghost/Desktop/Projects/shopify-fulfillment-tool/.venv/bin/python -m pytest
/home/cognitiveghost/Desktop/Projects/shopify-fulfillment-tool/.venv/bin/ruff check . --exclude shared
```
Expected: all tests pass. Ruff will flag any import left unused by the four conversions (`QHBoxLayout`, `QPushButton`, `QWidget` are the likely candidates) — remove exactly those it names, nothing more.

- [ ] **Step 9: Commit**

```bash
git add tests/test_dialog_button_guard.py gui/add_product_dialog.py gui/column_config_dialog.py gui/groups_management_dialog.py gui/rule_test_dialog.py
git commit -m "refactor(dialogs): move footers to QDialogButtonBox and guard the convention"
```

---

### Task 4: Header icon buttons

**Files:**
- Create: `gui/assets/icons/menu.svg`
- Create: `gui/assets/icons/settings.svg`
- Modify: `gui/ui_manager.py:59-63` (`_BUTTON_ICONS`)
- Modify: `gui/ui_manager.py:166-186` (`_create_global_header`)
- Test: `tests/test_icon_usage_guard.py` (existing — covers the new names with no edit)

**Interfaces:**
- Consumes: `icon(name)` from `gui/icons.py` and the `_BUTTON_ICONS` refresh loop at `gui/ui_manager.py:1871`.
- Produces: `MainWindow.connection_btn` (previously a local named `connection_btn`).

- [ ] **Step 1: Vendor the two SVGs**

Download from the pinned Lucide tag into `gui/assets/icons/`:

```bash
curl -fsSL https://raw.githubusercontent.com/lucide-icons/lucide/1.31.0/icons/menu.svg -o gui/assets/icons/menu.svg
curl -fsSL https://raw.githubusercontent.com/lucide-icons/lucide/1.31.0/icons/settings.svg -o gui/assets/icons/settings.svg
```

Verify both landed and contain the token `gui/icons.py` substitutes:

```bash
grep -l currentColor gui/assets/icons/menu.svg gui/assets/icons/settings.svg
```
Expected: both filenames listed. If either 404s, the glyph was renamed — check the tag's icon index rather than falling back to `main`, and record the substitute name in `gui/assets/README.md`.

- [ ] **Step 2: Add both to `_BUTTON_ICONS`**

In `gui/ui_manager.py`, extend the dict at lines 59-63:

```python
    _BUTTON_ICONS: ClassVar[dict[str, str]] = {
        "open_session_folder_button": "folder-open",
        "new_session_btn": "folder-plus",
        "clear_filter_button": "funnel-x",
        "sidebar_toggle_btn": "menu",
        "connection_btn": "settings",
    }
```

- [ ] **Step 3: Run the icon guard to confirm the names are vendored**

Run:
```bash
QT_QPA_PLATFORM=offscreen /home/cognitiveghost/Desktop/Projects/shopify-fulfillment-tool/.venv/bin/python -m pytest tests/test_icon_usage_guard.py -v
```
Expected: PASS — `test_ui_managers_icon_tables_are_vendored` reads `_BUTTON_ICONS` directly, so it covers `menu` and `settings` with no test edit. If Step 1's download failed, this is the test that says so.

- [ ] **Step 4: Drop the text glyphs from the two buttons**

In `gui/ui_manager.py`, replace lines 166-186 (`self.mw.sidebar_toggle_btn = QPushButton("☰")` through `toggle_row.addWidget(connection_btn)`) with:

```python
        # No text: _refresh_icons() sets the icon here and again on every theme
        # toggle, which is why connection_btn has to live on self.mw rather than
        # stay a local -- _BUTTON_ICONS looks its widgets up by attribute name.
        self.mw.sidebar_toggle_btn = QPushButton()
        self.mw.sidebar_toggle_btn.setMaximumWidth(40)
        self.mw.sidebar_toggle_btn.setToolTip("Toggle client sidebar")
        self.mw.sidebar_toggle_btn.clicked.connect(
            lambda: self.mw.client_sidebar.toggle_expanded()
        )
        toggle_row.addWidget(self.mw.sidebar_toggle_btn)

        self.mw.current_client_label = QLabel("No client selected")
        self.mw.current_client_label.setStyleSheet(
            font_css("label")
        )
        toggle_row.addWidget(self.mw.current_client_label)

        toggle_row.addStretch()

        self.mw.connection_btn = QPushButton()
        self.mw.connection_btn.setMaximumWidth(40)
        self.mw.connection_btn.setToolTip("Server Connection settings")
        self.mw.connection_btn.clicked.connect(self._open_connection_settings)
        toggle_row.addWidget(self.mw.connection_btn)
```

Both keep their tooltips — with the text gone, the tooltip is the only label a user gets.

- [ ] **Step 5: Confirm no other reference to the old local**

Run:
```bash
grep -rn "connection_btn" gui/ tests/
```
Expected: only the `_BUTTON_ICONS` entry and the three `self.mw.connection_btn` lines just written. If anything else appears, it was reading a local that never existed outside `_create_global_header` and needs the `self.mw.` prefix too.

- [ ] **Step 6: Run the full suite and lint**

Run:
```bash
QT_QPA_PLATFORM=offscreen /home/cognitiveghost/Desktop/Projects/shopify-fulfillment-tool/.venv/bin/python -m pytest
/home/cognitiveghost/Desktop/Projects/shopify-fulfillment-tool/.venv/bin/ruff check . --exclude shared
```
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add gui/assets/icons/menu.svg gui/assets/icons/settings.svg gui/ui_manager.py
git commit -m "feat(header): replace the plain-text sidebar and settings glyphs with icons"
```

---

### Task 5: Refresh the knowledge graph

**Files:** none tracked by git.

- [ ] **Step 1: Update graphify**

Run from the worktree root:
```bash
graphify update .
```

`CLAUDE.md` requires this right after code changes — a stale graph returns wrong answers about `shared/` ownership and theme delegation silently, with no error. `gui/components/` is a new package, so this run is the one that teaches the graph it exists.

- [ ] **Step 2: Final gate before handing to Stage C**

Run:
```bash
QT_QPA_PLATFORM=offscreen /home/cognitiveghost/Desktop/Projects/shopify-fulfillment-tool/.venv/bin/python -m pytest
/home/cognitiveghost/Desktop/Projects/shopify-fulfillment-tool/.venv/bin/ruff check . --exclude shared
```
Expected: all tests pass (455 before this plan, plus 7 from Task 1 and 3 from Task 3 = 465), ruff clean. Record the actual number — do not assume it.

- [ ] **Step 3: Push**

```bash
git push -u origin worktree-component-library
```

---

## Out of scope, on purpose

Each of these was considered and rejected with a reason; they are listed so a reviewer does not read them as oversights. Full reasoning is in the design doc.

- **`FormSection`** — deferred to Track 4. Its motivating example (the Add Product dialog's three stacked `QGroupBox` sections) was already removed by PR #267, and Track 4's Settings Hub is its only remaining consumer.
- **A global spacing/margin token scale** — `Card` keeps its margins as its own defaults until a second component wants the same numbers.
- **Migrating `ClientCard` onto `Card`** — it is an interactive list item with hover/active states and a fixed height, not a static tile.
- **`report_selection_dialog` / `profile_manager_dialog` footers** — neither has one.
- **`_BUTTON_ICONS` attribute-name validation** — still needs a real `MainWindow` fixture, and `tests/` still has none (`test_main_window_statistics.py` uses a `_FakeMainWindow`). Re-checked 2026-08-12; Track 4 is the next candidate.
- **A version bump** — Tracks 1 and 2 did not bump either; this is pre-release foundation work.
