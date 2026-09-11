# Phase 9 Bundle 10 — Settings saves once, Reports becomes a list — Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans (inline, in this
> session — no subagents) to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Settings has no page that writes by itself. It marks and names
unsaved pages, guards closing, and routes its feedback through toast, banner
and inline messages. The Reports page is two drag-orderable lists plus one
editor with a live match count.

**Architecture:** `SettingsPage` gains `snapshot()` / `mark_clean()` /
`is_dirty()`. The default compares `collect()` output, so no page needs signal
wiring. `SettingsWindow` polls the visible page every 400 ms and re-checks
every page before the close guard. Column Config leaves Settings entirely.
`ReportsPage` keeps configs in a keyed store whose order is the list order,
and builds one `ReportEditor` at a time. The match count reuses
`shopify_tool.report_filters` so it cannot disagree with the generated file.

**Tech Stack:** Python 3, PySide6, pandas, pytest (offscreen Qt).

**Spec:** `docs/superpowers/specs/2026-09-10-phase9-bundle10-settings-reports-design.md`.
Read it first. Every copy string below is quoted from it; if the two
disagree, the spec wins.

## Global Constraints

- Work only in the worktree `.claude/worktrees/worktree-phase9-bundle10-settings-reports`, branch `worktree-phase9-bundle10-settings-reports`. PR-only; never commit to `main`.
- Run Python as `.venv/bin/python`. Bare `python` is not on PATH. Tests: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest <path> -q`.
- Git on this VM: use `/usr/bin/git add …` and `/usr/bin/git commit -m "…"` as **separate** commands. `&&` chains, heredocs and plain `git` are refused by the worktree guard. End every commit message with the line `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` (pass it as a second `-m`).
- Write files with the Write/Edit tools. The write hook strips an import whose usage does not exist yet, so **add the usage first, then the import**. It also reformats whole files.
- Never edit `shared/` (owned by `packing-tool`). Everything needed already exists there: `icon`, `on_theme_changed`, `font_css`, `set_button_role`, `current_tokens`.
- No hardcoded colours. Every colour is a token read inside an `on_theme_changed(widget, lambda tokens: …)` closure (ADR 0003).
- No `QMessageBox` may remain in `gui/settings/`, nor in `actions_handler.open_settings_window`. `tests/test_message_routes.py` enforces this.
- In tests the dialog is never shown. Assert `widget.isHidden()`, **never** `isVisible()`, which is always False for children of an unshown window.
- A `QPushButton` label containing `&` must be written `&&` ("Save && close"); a single `&` is a mnemonic marker.
- Inside Settings, Save is the only `primary` button except the close guard's "Save & close", which appears only while Save is hidden. Every other button gets a role (`secondary`, `ghost` or `danger`), per `tests/test_settings_button_roles.py`.
- Lint: `.venv/bin/ruff check . --exclude shared` must be clean before the last commit.

---

### Task 0: Environment

- [ ] **Step 1:** Run `./scripts/setup_venv.sh` from the worktree root.
- [ ] **Step 2:** Run `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q -x` and note the pass count (1500 on `main` at `2767a0e`). Expected: all pass. If anything fails before you have changed a file, stop and record it in `~/automation/claude-roadmap-runner/state.md`.

---

### Task 1: The unsaved-page contract

**Files:**
- Modify: `gui/settings/base.py` (whole file)
- Modify: `gui/settings/mappings.py` (`_MappingPageBase`, `OrdersMappingPage.collect`)
- Modify: `gui/settings/sets.py` (`collect`, module docstring)
- Test: `tests/test_settings_page_contract.py`, `tests/test_settings_page_mappings.py`, `tests/test_settings_page_sets.py`

**Interfaces:**
- Produces: `SettingsPage.snapshot() -> str`, `SettingsPage.mark_clean() -> None`, `SettingsPage.is_dirty() -> bool`, `gui.settings.base.UNCOLLECTABLE = "<uncollectable>"`. `SetsPage.collect() -> {"set_decoders": <the live dict>}`.

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_settings_page_contract.py`:

```python
class _OneValuePage(SettingsPage):
    def __init__(self):
        super().__init__()
        self.value = 1

    def collect(self):
        return {"key": self.value}


def test_a_page_is_never_unsaved_before_mark_clean():
    QApplication.instance() or QApplication([])
    page = _OneValuePage()
    page.value = 2
    assert page.is_dirty() is False


def test_an_edit_reads_unsaved_and_reverting_it_reads_clean():
    QApplication.instance() or QApplication([])
    page = _OneValuePage()
    page.mark_clean()
    page.value = 2
    assert page.is_dirty() is True
    page.value = 1
    assert page.is_dirty() is False


def test_a_collect_that_raises_reads_unsaved(monkeypatch):
    QApplication.instance() or QApplication([])
    page = _OneValuePage()
    page.mark_clean()

    def boom():
        raise ValueError("half-typed")

    monkeypatch.setattr(page, "collect", boom)
    assert page.is_dirty() is True
```

Append to `tests/test_settings_page_mappings.py` (it already has a `qapp` fixture; import `json` at the top if absent):

```python
def test_editing_orders_mapping_leaves_stock_mapping_clean(qapp, monkeypatch):
    """Both pages return the same live column_mappings dict; comparing
    collect() would mark Stock unsaved whenever Orders changed."""
    column_mappings = {
        "version": 2,
        "orders": {"Name": "Order_Number", "Lineitem sku": "SKU", "Lineitem quantity": "Quantity"},
        "stock": {"Article": "SKU", "Available": "Stock"},
    }
    orders = OrdersMappingPage(column_mappings, {})
    stock = StockMappingPage(column_mappings)
    orders.mark_clean()
    stock.mark_clean()

    changed = {**orders.mapping_widget.get_mappings(), "Extra": "Product_Name"}
    monkeypatch.setattr(orders.mapping_widget, "get_mappings", lambda: changed)
    orders.collect()  # writes the orders sub-key into the shared dict

    assert orders.is_dirty() is True
    assert stock.is_dirty() is False
```

In `tests/test_settings_page_sets.py`, **replace** `test_sets_page_contributes_nothing_to_collect` with:

```python
def test_sets_page_collects_the_live_dict(qapp):
    decoders = {"SET-A": [{"sku": "X", "quantity": 2}]}
    page = SetsPage(decoders)
    assert page.collect() == {"set_decoders": decoders}
    assert page.collect()["set_decoders"] is decoders
    assert page.validate() == (True, [])
```

- [ ] **Step 2: Run them and confirm they fail.** Run `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_page_contract.py tests/test_settings_page_mappings.py tests/test_settings_page_sets.py -q`. Expected: FAIL (`AttributeError: … 'mark_clean'`, and the Sets collect assertion).

- [ ] **Step 3: Implement.** Replace `gui/settings/base.py` with:

```python
"""The contract between SettingsWindow and its pages."""

import json

from PySide6.QtWidgets import QWidget

UNCOLLECTABLE = "<uncollectable>"


class SettingsPage(QWidget):
    """One page in the settings window.

    The window builds each page, shows it in the nav stack, and on save
    calls validate() then collect() on every page in turn. No page writes to
    disk by itself: Save is the one write, and Cancel discards.

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

    def snapshot(self) -> str:
        """This page's values as one comparable string.

        Override only when collect() returns a dict another page also writes
        into (see _MappingPageBase): otherwise an edit on that page marks
        this one unsaved too.
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

In `gui/settings/mappings.py`, add `import json` at the top. Add this method to `_MappingPageBase`, right after `_collect_column_mappings`:

```python
    def snapshot(self) -> str:
        """Only this page's own mapping.

        column_mappings is one live dict shared by both mapping pages, so the
        default snapshot of collect() would mark both unsaved when either
        changes.
        """
        return json.dumps(self.mapping_widget.get_mappings(), sort_keys=True, default=str)
```

In `OrdersMappingPage`, split the courier-building loop out of `collect()`, and add a `snapshot` override:

```python
    def _courier_rows(self) -> dict:
        new_couriers = {}
        for row_refs in self.courier_mapping_widgets:
            courier_code = row_refs["courier_code"].text().strip()
            patterns_str = row_refs["patterns"].text().strip()
            if courier_code and patterns_str:
                patterns = [p.strip() for p in patterns_str.split(",") if p.strip()]
                new_couriers[courier_code] = {
                    "patterns": patterns,
                    "case_sensitive": False,
                }
        return new_couriers

    def snapshot(self) -> str:
        return json.dumps([super().snapshot(), self._courier_rows()], sort_keys=True, default=str)

    def collect(self) -> dict:
        # Same live-dict contract as column_mappings: clear-and-refill in
        # place so a deleted courier code does not survive the shell's merge.
        new_couriers = self._courier_rows()
        self.courier_mappings.clear()
        self.courier_mappings.update(new_couriers)

        return {
            "column_mappings": self._collect_column_mappings(),
            "courier_mappings": self.courier_mappings,
        }
```

In `gui/settings/sets.py`, add to `SetsPage` (after `__init__`):

```python
    def collect(self) -> dict:
        return {"set_decoders": self.set_decoders}
```

and replace the module docstring with:

```python
"""Sets/bundles: SKUs decoded into their component SKUs at fulfillment time.

Every Add/Edit/Delete/Import mutates the set_decoders dict handed in at
construction -- the same object the window holds under
config_data["set_decoders"] -- and collect() returns that dict. Nothing
reaches disk until the window's Save.
"""
```

- [ ] **Step 4: Run the tests and confirm they pass.** Run the command from Step 2. Expected: PASS. Then run `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_roundtrip.py -q`. Expected: PASS.

- [ ] **Step 5: Commit.**

```
/usr/bin/git add gui/settings/base.py gui/settings/mappings.py gui/settings/sets.py tests/test_settings_page_contract.py tests/test_settings_page_mappings.py tests/test_settings_page_sets.py
/usr/bin/git commit -m "Settings pages can tell whether they have unsaved changes (9.23)" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: Column Config leaves Settings

**Files:**
- Modify: `gui/settings/window.py` (the `SETTINGS_NAV_GROUPS` "Data" row, the `_add_page(_ColumnConfigPage…)` line, delete `class _ColumnConfigPage`, drop the imports it alone used: `FormSection`, `QLabel`)
- Modify: `tests/test_settings_roundtrip.py` (`test_window_registers_every_page`)
- Modify: `tests/test_message_routes.py` (re-own the `gui/column_config_dialog.py` entry)
- Modify: docstrings in `gui/components/form_section.py` (line ~9), `tests/test_column_config_dialog.py` (`test_the_panels_apply_button_is_not_a_primary`), `tests/test_settings_nav.py` (module docstring says "Nine pages")

- [ ] **Step 1: Write the failing test.** In `tests/test_settings_roundtrip.py`, change the expected list in `test_window_registers_every_page` to:

```python
    assert list(window._page_index_by_name) == [
        "General", "Rules", "Reports",
        "Orders Mapping", "Stock Mapping",
        "Sets", "Weight", "Tag Categories",
    ]
```

- [ ] **Step 2: Run it and confirm it fails.** Run `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_roundtrip.py::test_window_registers_every_page -q`. Expected: FAIL (extra "Column Config").

- [ ] **Step 3: Implement.**
  - Set `("Data", ["General", "Orders Mapping", "Stock Mapping"]),` in `SETTINGS_NAV_GROUPS`.
  - Delete the line `self._add_page(_ColumnConfigPage(self.parent()), "Column Config")` and the whole `_ColumnConfigPage` class.
  - Remove the now-unused `FormSection` and `QLabel` imports; ruff will flag any leftover.
  - In `tests/test_message_routes.py`, change the value for `("gui/column_config_dialog.py", "*")` to `"Bundle 13 (9.16) replaces ColumnConfigPanel"`.
  - In `gui/components/form_section.py`, remove `window.py's _ColumnConfigPage` from the docstring's list of users.
  - In `tests/test_column_config_dialog.py`, change the docstring of `test_the_panels_apply_button_is_not_a_primary` to: "In ColumnConfigDialog the panel's Apply is hidden in favour of the button box's, which is the dialog's one primary."
  - In `tests/test_settings_nav.py`'s docstring, change "Nine pages" to "Eight pages".

- [ ] **Step 4: Run the tests and confirm they pass.** Run `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_roundtrip.py tests/test_settings_nav.py tests/test_message_routes.py tests/test_column_config_dialog.py tests/test_settings_button_roles.py -q`. Expected: PASS.

- [ ] **Step 5: Commit.**

```
/usr/bin/git add gui/settings/window.py gui/components/form_section.py tests/test_settings_roundtrip.py tests/test_message_routes.py tests/test_column_config_dialog.py tests/test_settings_nav.py
/usr/bin/git commit -m "Column Config leaves Settings; Results' Configure Columns is its one entry (9.23)" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: The window marks unsaved pages and guards closing

**Files:**
- Modify: `gui/settings/window.py`
- Create: `tests/test_settings_unsaved.py`

**Interfaces:**
- Consumes: `SettingsPage.mark_clean/is_dirty` (Task 1).
- Produces:
  - `gui.settings.window.unsaved_summary(names: list[str]) -> str`
  - `SettingsWindow.refresh_dirty() -> list[str]`
  - `SettingsWindow._pages_by_name: dict[str, SettingsPage]`
  - `SettingsWindow._select_page(name: str) -> None`
  - `SettingsWindow._nav_page_names() -> list[str]`
  - widgets `_unsaved_label`, `_footer`, `_close_guard`, `_close_guard_label`, `keep_editing_button`, `discard_button`, `save_and_close_button`
  - `_dirty_poll: QTimer`, `_poll_current_page()`, `_hide_close_guard()`

- [ ] **Step 1: Write the failing tests.** Create `tests/test_settings_unsaved.py`:

```python
"""Settings knows which pages have unsaved changes, and closing never drops
them silently. Fixtures (window, started_workers, no_modals) come from
conftest.py."""
from PySide6.QtWidgets import QFileDialog

from gui.settings.window import unsaved_summary


def _nav_item(win, name):
    nav = win._settings_nav
    return next(
        nav.item(r) for r in range(nav.count())
        if nav.item(r).text() == name and nav.item(r).data(0x0100) is not None
    )


def _edit_sets(win):
    win._pages_by_name["Sets"].set_decoders["SET-NEW"] = [{"sku": "A", "quantity": 1}]


def test_unsaved_summary_names_up_to_two_pages():
    assert unsaved_summary([]) == ""
    assert unsaved_summary(["Sets"]) == "Unsaved changes on Sets"
    assert unsaved_summary(["Sets", "Reports"]) == "Unsaved changes on Sets and Reports"
    assert unsaved_summary(["General", "Sets", "Reports"]) == "Unsaved changes on 3 pages"


def test_a_fresh_window_has_no_unsaved_pages(window):
    assert window.refresh_dirty() == []
    assert window._unsaved_label.text() == ""


def test_an_edit_marks_its_nav_row_and_the_footer(window):
    _edit_sets(window)
    assert window.refresh_dirty() == ["Sets"]
    assert _nav_item(window, "Sets").toolTip() == "Unsaved changes"
    assert _nav_item(window, "General").toolTip() == ""
    assert window._unsaved_label.text() == "Unsaved changes on Sets"


def test_reverting_an_edit_clears_the_mark(window):
    _edit_sets(window)
    window.refresh_dirty()
    del window._pages_by_name["Sets"].set_decoders["SET-NEW"]
    assert window.refresh_dirty() == []
    assert _nav_item(window, "Sets").toolTip() == ""


def test_the_poll_checks_the_page_on_screen(window):
    assert window._dirty_poll.isActive()
    window._select_page("Sets")
    _edit_sets(window)
    window._poll_current_page()
    assert window._unsaved_label.text() == "Unsaved changes on Sets"


def test_cancel_with_nothing_unsaved_closes(window):
    closed = []
    window.rejected.connect(lambda: closed.append(True))
    window.reject()
    assert closed == [True]


def test_cancel_with_unsaved_pages_shows_the_close_guard_instead(window):
    closed = []
    window.rejected.connect(lambda: closed.append(True))
    _edit_sets(window)
    window.reject()
    assert closed == []
    assert not window._close_guard.isHidden()
    assert window._footer.isHidden()
    assert window._close_guard_label.text() == (
        "Unsaved changes on Sets. Closing now discards them."
    )
    assert window.save_and_close_button.text() == "Save && close"


def test_keep_editing_and_escape_both_restore_the_footer(window):
    _edit_sets(window)
    window.reject()
    window.keep_editing_button.click()
    assert window._close_guard.isHidden()
    assert not window._footer.isHidden()

    window.reject()
    window.reject()  # Esc while the guard is up keeps editing
    assert window._close_guard.isHidden()


def test_cancel_then_discard_leaves_the_profile_unwritten(
    window, started_workers, monkeypatch, tmp_path
):
    """9.23 done-when: import sets, Cancel, Discard -> nothing written."""
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName",
        staticmethod(lambda *a, **k: (str(tmp_path / "sets.csv"), "")),
    )
    monkeypatch.setattr(
        "gui.settings.sets.import_sets_from_csv",
        lambda path: {"SET-X": [{"sku": "A", "quantity": 2}]},
    )
    monkeypatch.setattr("gui.settings.sets.toast", lambda *a, **k: None)
    closed = []
    window.rejected.connect(lambda: closed.append(True))

    window._pages_by_name["Sets"]._import_sets_from_csv(replace=True)
    window.reject()
    window.discard_button.click()

    assert closed == [True]
    assert started_workers == []
    window.profile_manager.save_shopify_config.assert_not_called()


def test_save_and_close_saves(window, started_workers):
    _edit_sets(window)
    window.reject()
    window.save_and_close_button.click()
    assert len(started_workers) == 1
    assert window._close_guard.isHidden()


def test_closing_stops_the_poll(window):
    window.done(0)
    assert not window._dirty_poll.isActive()
```

Note that `test_cancel_then_discard_leaves_the_profile_unwritten` calls `_import_sets_from_csv(replace=True)`, which Task 6 introduces. Until then, give that one test `@pytest.mark.xfail(reason="Task 6", strict=True)` with `import pytest` at the top, and remove the mark in Task 6.

- [ ] **Step 2: Run them and confirm they fail.** Run `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_unsaved.py -q`. Expected: FAIL (`ImportError: unsaved_summary`).

- [ ] **Step 3: Implement in `gui/settings/window.py`.**

Module level, after `logger`:

```python
NAV_ICON_PX = 12
UNSAVED_DOT_PX = 8
DIRTY_POLL_MS = 400


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

In `__init__`, next to `self._pages: list[SettingsPage] = []`, add:

```python
        self._pages_by_name: dict[str, SettingsPage] = {}
        self._unsaved: set[str] = set()
```

After creating `self._settings_nav`, add `self._settings_nav.setIconSize(QSize(NAV_ICON_PX, NAV_ICON_PX))`.

In `_add_page`, add `self._pages_by_name[name] = page`.

Replace `main_layout.addWidget(button_box)` with the footer and the close guard:

```python
        self._unsaved_label = QLabel("")
        on_theme_changed(
            self._unsaved_label,
            lambda tokens: self._unsaved_label.setStyleSheet(
                f"{font_css('body')} color: {tokens.text_secondary};"
            ),
        )
        self._footer = QWidget()
        footer_row = QHBoxLayout(self._footer)
        footer_row.setContentsMargins(0, 0, 0, 0)
        footer_row.addWidget(self._unsaved_label, 1)
        footer_row.addWidget(button_box)
        main_layout.addWidget(self._footer)

        # The close guard replaces the footer in place: the pages it names are
        # on screen beside it, so it is not a message box.
        self._close_guard = QWidget()
        guard_row = QHBoxLayout(self._close_guard)
        guard_row.setContentsMargins(0, 0, 0, 0)
        self._close_guard_label = QLabel("")
        self._close_guard_label.setWordWrap(True)
        guard_row.addWidget(self._close_guard_label, 1)
        self.keep_editing_button = QPushButton("Keep editing")
        set_button_role(self.keep_editing_button, "ghost")
        self.keep_editing_button.clicked.connect(self._hide_close_guard)
        self.discard_button = QPushButton("Discard")
        set_button_role(self.discard_button, "danger")
        self.discard_button.clicked.connect(self._discard)
        # "&&": a single "&" is a Qt mnemonic and would underline the "c".
        self.save_and_close_button = QPushButton("Save && close")
        set_button_role(self.save_and_close_button, "primary")
        self.save_and_close_button.clicked.connect(self.save_settings)
        for button in (self.keep_editing_button, self.discard_button, self.save_and_close_button):
            guard_row.addWidget(button)
        self._close_guard.hide()
        main_layout.addWidget(self._close_guard)
```

At the very **end** of `__init__` (after the `resize`):

```python
        for page in self._pages:
            page.mark_clean()
        on_theme_changed(self._settings_nav, self._rebuild_nav_marks)
        # ponytail: polls the visible page's snapshot (one collect() plus one
        # json.dumps) every 400ms. Ceiling: a page whose snapshot costs tens of
        # milliseconds makes the dialog stutter; upgrade to a per-page
        # `edited` signal then.
        self._dirty_poll = QTimer(self)
        self._dirty_poll.setInterval(DIRTY_POLL_MS)
        self._dirty_poll.timeout.connect(self._poll_current_page)
        self._dirty_poll.start()
```

New methods, and a replacement `reject`:

```python
    def _nav_page_names(self) -> list[str]:
        return [name for _group, names in self.SETTINGS_NAV_GROUPS for name in names]

    def _select_page(self, name: str) -> None:
        for row in range(self._settings_nav.count()):
            item = self._settings_nav.item(row)
            if item.text() == name and item.data(Qt.ItemDataRole.UserRole) is not None:
                self._settings_nav.setCurrentRow(row)
                return

    def refresh_dirty(self) -> list[str]:
        """Re-check every page; return the unsaved page names in nav order."""
        self._unsaved = {name for name, page in self._pages_by_name.items() if page.is_dirty()}
        self._render_unsaved()
        return [name for name in self._nav_page_names() if name in self._unsaved]

    def _poll_current_page(self) -> None:
        page = self.tab_widget.currentWidget()
        name = next((n for n, p in self._pages_by_name.items() if p is page), None)
        if name is None:
            return
        if page.is_dirty() != (name in self._unsaved):
            self._unsaved ^= {name}
            self._render_unsaved()

    def _render_unsaved(self) -> None:
        names = [name for name in self._nav_page_names() if name in self._unsaved]
        summary = unsaved_summary(names)
        self._unsaved_label.setText(summary)
        self._close_guard_label.setText(f"{summary}. Closing now discards them." if names else "")
        self._apply_nav_marks()

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
        for row in range(self._settings_nav.count()):
            item = self._settings_nav.item(row)
            if item.data(Qt.ItemDataRole.UserRole) is None:
                continue  # group header
            unsaved = item.text() in self._unsaved
            item.setIcon(self._unsaved_icon if unsaved else self._clean_icon)
            item.setToolTip("Unsaved changes" if unsaved else "")
            item.setData(
                Qt.ItemDataRole.AccessibleTextRole,
                f"{item.text()}, unsaved changes" if unsaved else item.text(),
            )

    def reject(self):
        if self._is_saving:
            return
        # isHidden, not isVisible: children of a dialog that was never shown
        # (every test) report invisible.
        if not self._close_guard.isHidden():
            self._hide_close_guard()
            return
        if self.refresh_dirty():
            self._show_close_guard()
            return
        super().reject()

    def _show_close_guard(self) -> None:
        self._footer.hide()
        self._close_guard.show()
        self.save_and_close_button.setFocus()

    def _hide_close_guard(self) -> None:
        self._close_guard.hide()
        self._footer.show()

    def _discard(self) -> None:
        self._hide_close_guard()
        super().reject()

    def done(self, result):
        self._dirty_poll.stop()
        super().done(result)
```

Add `self._hide_close_guard()` as the first line of `save_settings`.

Imports to add, **after** the usages above exist:
- `from PySide6.QtCore import QRectF, QSize, QTimer`
- `from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap`
- `QLabel` and `QWidget` from `PySide6.QtWidgets`
- `from shared.theme import font_css, on_theme_changed`

(`QDialog.closeEvent` calls `reject()` and ignores the close if the dialog is still visible, so the title-bar close is guarded with no extra code.)

- [ ] **Step 4: Run the tests and confirm they pass.** Run `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_unsaved.py tests/test_settings_roundtrip.py tests/test_settings_nav.py tests/test_settings_button_roles.py -q`. Expected: PASS, with the one xfail.

- [ ] **Step 5: Commit.**

```
/usr/bin/git add gui/settings/window.py tests/test_settings_unsaved.py
/usr/bin/git commit -m "Settings marks unsaved pages and guards closing inline (9.23)" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: Save feedback takes its routes

**Files:**
- Modify: `gui/settings/window.py` (layout around the stack, `save_settings`, `_on_save_settings_result`, `_on_save_settings_error`, `_on_settings_nav_changed`)
- Modify: `gui/actions_handler.py` (`open_settings_window`, lines ~368-404)
- Modify: `tests/test_message_routes.py` (delete the `open_settings_window` and `gui/settings/window.py` entries from `OWNED`)
- Test: `tests/test_settings_roundtrip.py`

**Interfaces:**
- Consumes: `_select_page`, `_nav_page_names`, `_hide_close_guard` (Task 3); `toast(source, text)` from `gui.components.toast`; `show_error(source, headline, what_to_do)` from `gui.components.error_banner`; `InlineMessage` (`show_message(text)`, `clear()`) from `gui.components.inline_message`.
- Produces: `SettingsWindow._validation_message: InlineMessage`.

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_settings_roundtrip.py`:

```python
def test_a_validation_failure_selects_the_page_and_says_so_inline(
    window, no_modals, started_workers, monkeypatch
):
    mappings = window._pages_by_name["Orders Mapping"]
    monkeypatch.setattr(mappings, "validate", lambda: (False, ["Map the SKU column."]))

    window.save_settings()

    assert no_modals == []
    assert started_workers == []
    assert window._settings_nav.currentItem().text() == "Orders Mapping"
    assert window._validation_message.text() == "Map the SKU column."
    assert not window._validation_message.isHidden()


def test_changing_page_clears_the_validation_message(window, monkeypatch):
    mappings = window._pages_by_name["Orders Mapping"]
    monkeypatch.setattr(mappings, "validate", lambda: (False, ["Map the SKU column."]))
    window.save_settings()

    window._select_page("Sets")

    assert window._validation_message.isHidden()


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


def test_a_failed_write_shows_a_banner_and_stays_open(window, monkeypatch):
    errors = []
    monkeypatch.setattr(
        "gui.settings.window.show_error",
        lambda source, headline, what: errors.append((headline, what)),
    )
    accepted = []
    window.accepted.connect(lambda: accepted.append(True))

    window._on_save_settings_result(False)

    assert errors == [(
        "Settings weren't saved",
        "The profile may be open on another PC, or the server can't be reached. "
        "Wait a few seconds, then press Save again.",
    )]
    assert accepted == []
    assert window.save_button.isEnabled()


def test_a_crashed_write_points_to_logs(window, monkeypatch):
    errors = []
    monkeypatch.setattr(
        "gui.settings.window.show_error",
        lambda source, headline, what: errors.append((headline, what)),
    )
    window._on_save_settings_error((ValueError, ValueError("disk"), "tb"))
    assert errors == [("Settings weren't saved", "Details are in Logs.")]
```

- [ ] **Step 2: Run them and confirm they fail.** Run `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_roundtrip.py -q`. Expected: FAIL (no `_validation_message`, `toast` not a module attribute).

- [ ] **Step 3: Implement.**

In `SettingsWindow.__init__`, replace the two lines that create and add `self.tab_widget` with:

```python
        page_column = QVBoxLayout()
        self._validation_message = InlineMessage()
        page_column.addWidget(self._validation_message)
        self.tab_widget = QStackedWidget()
        page_column.addWidget(self.tab_widget, 1)
        content_layout.addLayout(page_column, 1)
```

In `_on_settings_nav_changed`, add `self._validation_message.clear()` as its first line.

Replace `save_settings`, `_on_save_settings_result` and `_on_save_settings_error` with:

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
            show_error(self, "Settings weren't saved", "A value couldn't be read. Details are in Logs.")
            return

        # Save to server via ProfileManager (background -- avoids blocking the
        # GUI thread on the lock-contention retry sleep)
        self.save_button.setEnabled(False)
        self.save_button.setText("Saving...")
        self._is_saving = True

        worker = Worker(self.profile_manager.save_shopify_config, self.client_id, self.config_data)
        worker.signals.result.connect(self._on_save_settings_result)
        worker.signals.error.connect(self._on_save_settings_error)
        # Keep a strong reference until the worker finishes -- a bare local var
        # is garbage-collected the instant this method returns, which (in this
        # PySide6 build) destroys the QRunnable's unparented signals object
        # before its queued result reaches the main thread. See
        # MainWindow._client_load_worker for the verified repro.
        self._save_worker = worker
        QThreadPool.globalInstance().start(worker)

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
        _exctype, value, tb = error
        logger.error(f"Failed to save settings: {value}\n{tb}")
        self._is_saving = False
        self.save_button.setEnabled(True)
        self.save_button.setText("Save")
        show_error(self, "Settings weren't saved", "Details are in Logs.")
```

Then add the imports: `from gui.components.error_banner import show_error`, `from gui.components.inline_message import InlineMessage`, `from gui.components.toast import toast`. Remove `QMessageBox` from the `PySide6.QtWidgets` import.

In `gui/actions_handler.py` `open_settings_window`, replace the whole `if settings_win.exec():` block with:

```python
        if settings_win.exec():
            # The window has already toasted "Settings saved".
            try:
                self.mw.active_profile_config = (
                    self.mw.profile_manager.load_shopify_config(
                        self.mw.current_client_id
                    )
                )

                self.log.info("Re-validating files with updated settings...")
                if self.mw.orders_file_path:
                    self.mw.file_handler.validate_file("orders")
                if self.mw.stock_file_path:
                    self.mw.file_handler.validate_file("stock")

                self.log.info("Settings updated and files re-validated successfully")

            except Exception:
                self.log.exception("Error updating config after save")
                show_error(
                    self.mw,
                    "Settings were saved but didn't reload",
                    "Restart the app to use them. Details are in Logs.",
                )
```

In `tests/test_message_routes.py`, delete the `open_settings_window` entry and the `("gui/settings/window.py", "*")` entry from `OWNED`.

- [ ] **Step 4: Run the tests and confirm they pass.** Run `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_roundtrip.py tests/test_settings_unsaved.py tests/test_message_routes.py tests/test_actions_handler.py tests/test_generate_reports_dialog.py -q`. Expected: PASS (1 xfail).

- [ ] **Step 5: Commit.**

```
/usr/bin/git add gui/settings/window.py gui/actions_handler.py tests/test_settings_roundtrip.py tests/test_message_routes.py
/usr/bin/git commit -m "Settings save feedback becomes a toast, a banner or an inline message (9.23)" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: Nav search, and a nav that cannot hide a page

**Files:**
- Modify: `gui/settings/window.py`
- Test: `tests/test_settings_nav.py`

**Interfaces:**
- Produces: module constant `SETTINGS_SEARCH_KEYWORDS: dict[str, list[str]]`; `SettingsWindow.filter_nav(text: str) -> list[str]` (visible page names, in nav order); `_nav_search: QLineEdit`; `_no_match_label: QLabel`; `_select_first_visible_page()`.

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_settings_nav.py` (add `import pytest` and `from gui.settings.window import SETTINGS_SEARCH_KEYWORDS` to its imports):

```python
def _headers(win):
    nav = win._settings_nav
    return {
        nav.item(r).text(): nav.item(r).isHidden()
        for r in range(nav.count())
        if nav.item(r).data(Qt.ItemDataRole.UserRole) is None
    }


def test_search_matches_a_keyword(window):
    assert window.filter_nav("box") == ["Weight"]


def test_search_matches_a_page_name_ignoring_case(window):
    assert window.filter_nav("SETS") == ["Sets"]


def test_a_group_with_no_match_hides_its_header(window):
    window.filter_nav("box")
    assert _headers(window) == {
        "DATA": True, "FULFILLMENT LOGIC": False, "OUTPUT": True, "ORGANIZATION": True,
    }


def test_no_match_says_so_and_clearing_restores_every_page(window):
    assert window.filter_nav("zzz") == []
    assert not window._no_match_label.isHidden()
    assert len(window.filter_nav("")) == 8
    assert window._no_match_label.isHidden()


def test_enter_opens_the_first_match(window):
    window._nav_search.setText("courier")
    window._nav_search.returnPressed.emit()
    assert window._settings_nav.currentItem().text() == "Orders Mapping"


def test_every_nav_page_has_search_keywords():
    listed = sorted(n for _g, names in SettingsWindow.SETTINGS_NAV_GROUPS for n in names)
    assert sorted(SETTINGS_SEARCH_KEYWORDS) == listed


def test_a_nav_name_with_no_page_fails_construction(
    qapp, no_modals, started_workers, make_settings_config
):
    class Broken(SettingsWindow):
        SETTINGS_NAV_GROUPS = [*SettingsWindow.SETTINGS_NAV_GROUPS, ("Extra", ["Nope"])]

    with pytest.raises(ValueError):
        Broken(client_id="M", client_config=make_settings_config(), profile_manager=Mock())


def test_an_empty_nav_group_fails_construction(
    qapp, no_modals, started_workers, make_settings_config
):
    class Broken(SettingsWindow):
        SETTINGS_NAV_GROUPS = [*SettingsWindow.SETTINGS_NAV_GROUPS, ("Empty", [])]

    with pytest.raises(ValueError):
        Broken(client_id="M", client_config=make_settings_config(), profile_manager=Mock())
```

- [ ] **Step 2: Run them and confirm they fail.** Run `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_nav.py -q`. Expected: FAIL (`ImportError: SETTINGS_SEARCH_KEYWORDS`).

- [ ] **Step 3: Implement.**

Module level in `window.py`:

```python
# Page name -> words a person might search for that are not in the name.
SETTINGS_SEARCH_KEYWORDS: dict[str, list[str]] = {
    "General": ["delimiter", "csv", "low stock", "threshold", "repeat"],
    "Orders Mapping": ["columns", "csv", "headers", "courier", "carrier", "shipping"],
    "Stock Mapping": ["columns", "csv", "headers", "expiry", "batch", "lot", "fifo"],
    "Rules": ["conditions", "actions", "tags", "status", "priority", "automation"],
    "Sets": ["bundles", "kits", "components", "decoder"],
    "Weight": ["volumetric", "divisor", "dimensions", "boxes", "packaging", "kg"],
    "Reports": ["packing list", "stock export", "filters", "output", "writeoff"],
    "Tag Categories": ["tags", "labels", "colours", "colors", "writeoff", "sku"],
}
```

In `__init__`, replace `content_layout.addWidget(self._settings_nav)` with a nav column:

```python
        nav_column = QVBoxLayout()
        self._nav_search = QLineEdit()
        self._nav_search.setPlaceholderText("Search settings")
        self._nav_search.setClearButtonEnabled(True)
        self._nav_search.setFixedWidth(170)
        self._nav_search.textChanged.connect(self.filter_nav)
        self._nav_search.returnPressed.connect(self._select_first_visible_page)
        nav_column.addWidget(self._nav_search)
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
        QShortcut(QKeySequence(QKeySequence.StandardKey.Find), self).activated.connect(
            self._nav_search.setFocus
        )
```

At the top of `_build_settings_nav`, and delete its `if page_name not in self._page_index_by_name: continue`:

```python
        listed = self._nav_page_names()
        problems = []
        if any(not names for _group, names in self.SETTINGS_NAV_GROUPS):
            problems.append("a nav group has no pages")
        if sorted(listed) != sorted(self._page_index_by_name):
            problems.append(f"nav lists {sorted(listed)} but pages are {sorted(self._page_index_by_name)}")
        if sorted(SETTINGS_SEARCH_KEYWORDS) != sorted(listed):
            problems.append("SETTINGS_SEARCH_KEYWORDS does not name exactly the nav's pages")
        if problems:
            # A page missing from the nav is unreachable, and nothing else says so.
            raise ValueError("; ".join(problems))
```

New methods:

```python
    def filter_nav(self, text: str) -> list[str]:
        """Show nav rows whose name or keywords contain `text`; return them."""
        query = text.strip().casefold()
        visible: list[str] = []
        header, header_has_rows = None, False
        for row in range(self._settings_nav.count()):
            item = self._settings_nav.item(row)
            if item.data(Qt.ItemDataRole.UserRole) is None:
                if header is not None:
                    header.setHidden(not header_has_rows)
                header, header_has_rows = item, False
                continue
            name = item.text()
            haystack = [name, *SETTINGS_SEARCH_KEYWORDS[name]]
            match = not query or any(query in word.casefold() for word in haystack)
            item.setHidden(not match)
            if match:
                visible.append(name)
                header_has_rows = True
        if header is not None:
            header.setHidden(not header_has_rows)
        self._no_match_label.setHidden(not query or bool(visible))
        return visible

    def _select_first_visible_page(self) -> None:
        for row in range(self._settings_nav.count()):
            item = self._settings_nav.item(row)
            if item.data(Qt.ItemDataRole.UserRole) is not None and not item.isHidden():
                self._settings_nav.setCurrentRow(row)
                return
```

Imports, after the usages exist: `QLineEdit` from `PySide6.QtWidgets`; `QKeySequence` and `QShortcut` from `PySide6.QtGui`.

- [ ] **Step 4: Run the tests and confirm they pass.** Run `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_nav.py tests/test_settings_unsaved.py tests/test_settings_roundtrip.py -q`. Expected: PASS (1 xfail).

- [ ] **Step 5: Commit.**

```
/usr/bin/git add gui/settings/window.py tests/test_settings_nav.py
/usr/bin/git commit -m "Settings nav gains search, and refuses a group that hides a page (9.23)" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: Sets page messages take their routes

**Files:**
- Modify: `gui/settings/sets.py`
- Modify: `tests/test_message_routes.py` (delete the `("gui/settings/sets.py", "*")` entry)
- Modify: `tests/test_settings_unsaved.py` (remove the xfail mark from Task 3)
- Test: `tests/test_settings_page_sets.py`

**Interfaces:**
- Produces: `SetsPage.import_button: QPushButton` (with a menu), `SetsPage.export_button: QPushButton`, `SetsPage._import_sets_from_csv(replace: bool)`, `SetEditorDialog.sku_message: InlineMessage`, `SetEditorDialog.components_message: InlineMessage`.

- [ ] **Step 1: Write the failing tests.** In `tests/test_settings_page_sets.py`, replace `test_sets_page_delete_mutates_the_live_dict_in_place` and append the rest:

```python
from PySide6.QtWidgets import QFileDialog

from gui.settings.sets import SetEditorDialog


def _patch_open(monkeypatch, tmp_path, imported):
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName",
        staticmethod(lambda *a, **k: (str(tmp_path / "sets.csv"), "")),
    )
    monkeypatch.setattr("gui.settings.sets.import_sets_from_csv", lambda path: imported)


def test_delete_is_immediate_and_lands_on_the_live_dict(qapp):
    """No confirm: the window's Cancel undoes it."""
    set_decoders = {"SET-A": [{"sku": "X", "quantity": 2}]}
    page = SetsPage(set_decoders)
    page._delete_set("SET-A")
    assert set_decoders == {}


def test_the_import_menu_offers_merge_and_replace(qapp):
    page = SetsPage({})
    assert [a.text() for a in page.import_button.menu().actions()] == [
        "Add and update sets…", "Replace all sets…",
    ]


def test_merge_import_keeps_existing_sets_and_toasts(qapp, monkeypatch, tmp_path):
    toasts = []
    monkeypatch.setattr("gui.settings.sets.toast", lambda source, text, **k: toasts.append(text))
    _patch_open(monkeypatch, tmp_path, {"SET-B": [{"sku": "Y", "quantity": 1}]})
    decoders = {"SET-A": [{"sku": "X", "quantity": 2}]}
    page = SetsPage(decoders)

    page._import_sets_from_csv(replace=False)

    assert sorted(decoders) == ["SET-A", "SET-B"]
    assert toasts == ["Imported 1 sets from sets.csv"]


def test_replace_import_drops_existing_sets(qapp, monkeypatch, tmp_path):
    toasts = []
    monkeypatch.setattr("gui.settings.sets.toast", lambda source, text, **k: toasts.append(text))
    _patch_open(monkeypatch, tmp_path, {"SET-B": [{"sku": "Y", "quantity": 1}]})
    decoders = {"SET-A": [{"sku": "X", "quantity": 2}]}
    page = SetsPage(decoders)

    page._import_sets_from_csv(replace=True)

    assert sorted(decoders) == ["SET-B"]
    assert toasts == ["Replaced all sets with 1 from sets.csv"]


def test_an_empty_csv_shows_a_banner(qapp, monkeypatch, tmp_path):
    errors = []
    monkeypatch.setattr(
        "gui.settings.sets.show_error",
        lambda source, headline, what: errors.append((headline, what)),
    )
    _patch_open(monkeypatch, tmp_path, {})
    page = SetsPage({})

    page._import_sets_from_csv(replace=False)

    assert errors == [(
        "No sets found in sets.csv",
        "Each row needs Set_SKU, Component_SKU and Component_Quantity.",
    )]


def test_export_is_disabled_until_there_is_a_set(qapp):
    page = SetsPage({})
    assert not page.export_button.isEnabled()
    page.set_decoders["SET-A"] = [{"sku": "X", "quantity": 1}]
    page._populate_sets_table()
    assert page.export_button.isEnabled()


def test_export_toasts(qapp, monkeypatch, tmp_path):
    toasts = []
    monkeypatch.setattr("gui.settings.sets.toast", lambda source, text, **k: toasts.append(text))
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName",
        staticmethod(lambda *a, **k: (str(tmp_path / "out.csv"), "")),
    )
    monkeypatch.setattr("gui.settings.sets.export_sets_to_csv", lambda decoders, path: None)
    page = SetsPage({"SET-A": [{"sku": "X", "quantity": 1}]})

    page._export_sets_to_csv()

    assert toasts == ["Exported 1 sets to out.csv"]


def test_the_set_editor_explains_problems_inline(qapp):
    dialog = SetEditorDialog()
    dialog._validate_and_save()
    assert dialog.sku_message.text() == "Enter the set's SKU."
    assert not dialog.sku_message.isHidden()

    dialog.set_sku_edit.setText("SET-A")
    assert dialog.sku_message.isHidden()

    dialog._validate_and_save()  # one empty component row
    assert dialog.components_message.text() == "Add at least one component with a SKU."
```

(Keep the existing `QMessageBox` import only if something else in the file still uses it; ruff will say.)

- [ ] **Step 2: Run them and confirm they fail.** Run `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_page_sets.py -q`. Expected: FAIL.

- [ ] **Step 3: Implement in `gui/settings/sets.py`.**

Buttons row in `SetsPage.__init__`: replace the import and export button blocks with:

```python
        self.import_button = QPushButton("Import from CSV")
        set_button_role(self.import_button, "secondary")
        import_menu = QMenu(self.import_button)
        merge_action = import_menu.addAction("Add and update sets…")
        merge_action.triggered.connect(lambda _checked=False: self._import_sets_from_csv(replace=False))
        replace_action = import_menu.addAction("Replace all sets…")
        replace_action.triggered.connect(lambda _checked=False: self._import_sets_from_csv(replace=True))
        self.import_button.setMenu(import_menu)
        buttons_layout.addWidget(self.import_button)

        self.export_button = QPushButton("Export to CSV")
        set_button_role(self.export_button, "secondary")
        self.export_button.clicked.connect(self._export_sets_to_csv)
        buttons_layout.addWidget(self.export_button)
```

At the end of `_populate_sets_table`: `self.export_button.setEnabled(bool(self.set_decoders))`.

Replace `_add_set_dialog`, `_edit_set_dialog`, `_delete_set`, `_import_sets_from_csv` and `_export_sets_to_csv` with:

```python
    def _add_set_dialog(self):
        dialog = SetEditorDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            set_sku, components = dialog.get_set_definition()
            self.set_decoders[set_sku] = components
            self._populate_sets_table()

    def _edit_set_dialog(self, set_sku):
        current_components = self.set_decoders.get(set_sku, [])
        dialog = SetEditorDialog(set_sku=set_sku, components=current_components, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_set_sku, new_components = dialog.get_set_definition()
            if new_set_sku != set_sku:
                del self.set_decoders[set_sku]
            self.set_decoders[new_set_sku] = new_components
            self._populate_sets_table()

    def _delete_set(self, set_sku):
        """No confirm: the settings window's Cancel undoes it."""
        del self.set_decoders[set_sku]
        self._populate_sets_table()

    def _import_sets_from_csv(self, replace: bool):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Import Sets from CSV", "", "CSV Files (*.csv);;All Files (*)"
        )
        if not file_path:
            return
        name = Path(file_path).name
        try:
            imported_sets = import_sets_from_csv(file_path)
        except Exception:
            logger.exception(f"Failed to import sets from {file_path}")
            show_error(self, "The sets weren't imported", "Details are in Logs.")
            return
        if not imported_sets:
            show_error(
                self,
                f"No sets found in {name}",
                "Each row needs Set_SKU, Component_SKU and Component_Quantity.",
            )
            return

        if replace:
            self.set_decoders.clear()
        self.set_decoders.update(imported_sets)
        self._populate_sets_table()
        if replace:
            toast(self, f"Replaced all sets with {len(imported_sets)} from {name}")
        else:
            toast(self, f"Imported {len(imported_sets)} sets from {name}")

    def _export_sets_to_csv(self):
        """Disabled while there are no sets (see _populate_sets_table)."""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Sets to CSV", "sets_export.csv", "CSV Files (*.csv);;All Files (*)"
        )
        if not file_path:
            return
        try:
            export_sets_to_csv(self.set_decoders, file_path)
        except Exception:
            logger.exception(f"Failed to export sets to {file_path}")
            show_error(self, "The sets weren't exported", "Details are in Logs.")
            return
        toast(self, f"Exported {len(self.set_decoders)} sets to {Path(file_path).name}")
```

In `SetEditorDialog.__init__`, right after `layout.addLayout(sku_layout)`:

```python
        self.sku_message = InlineMessage()
        layout.addWidget(self.sku_message)
        self.set_sku_edit.textChanged.connect(self.sku_message.clear)
```

and right after `layout.addWidget(self.components_table)`:

```python
        self.components_message = InlineMessage()
        layout.addWidget(self.components_message)
```

Replace `_validate_and_save` with the version below, and delete every `print(f"[DEBUG]…")` line in `get_set_definition`:

```python
    def _validate_and_save(self):
        """Explain problems under the field they name; accept when there are none."""
        self.sku_message.clear()
        self.components_message.clear()
        if not self.set_sku_edit.text().strip():
            self.sku_message.show_message("Enter the set's SKU.")
            return
        if not self.get_set_definition()[1]:
            self.components_message.show_message("Add at least one component with a SKU.")
            return
        self.accept()
```

Imports, after the usages exist: `import logging` and `from pathlib import Path`; `QMenu` in the `PySide6.QtWidgets` import, with `QMessageBox` removed; `from gui.components.error_banner import show_error`; `from gui.components.inline_message import InlineMessage`; `from gui.components.toast import toast`. Add `logger = logging.getLogger(__name__)` after the imports.

In `tests/test_message_routes.py`, delete the `("gui/settings/sets.py", "*")` entry. In `tests/test_settings_unsaved.py`, remove the `xfail` mark (and `import pytest` if now unused).

- [ ] **Step 4: Run the tests and confirm they pass.** Run `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_page_sets.py tests/test_settings_unsaved.py tests/test_message_routes.py tests/test_settings_button_roles.py -q`. Expected: PASS, no xfail.

- [ ] **Step 5: Commit.**

```
/usr/bin/git add gui/settings/sets.py tests/test_settings_page_sets.py tests/test_settings_unsaved.py tests/test_message_routes.py
/usr/bin/git commit -m "Sets messages become toasts, banners and inline messages; import picks merge or replace up front (9.23)" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 7: One match count for the dialog and the editor

**Files:**
- Modify: `shopify_tool/report_filters.py` (append two functions)
- Modify: `gui/report_selection_dialog.py` (`_update_preview`)
- Test: `tests/test_report_filters.py`

**Interfaces:**
- Produces: `match_counts(filtered) -> tuple[int, int]` and `count_matches(df, filters) -> tuple[int, int] | None`, both in `shopify_tool.report_filters`.

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_report_filters.py` (add `count_matches, match_counts` to its import):

```python
def test_count_matches_is_none_without_an_analysis():
    assert count_matches(None, []) is None
    assert count_matches(pd.DataFrame(), []) is None


def test_count_matches_counts_fulfillable_orders_and_rows():
    frame = pd.DataFrame({
        "Order_Number": ["1", "1", "2", "3"],
        "SKU": ["A", "B", "A", "A"],
        "Order_Fulfillment_Status": ["Fulfillable", "Fulfillable", "Fulfillable", "Not Fulfillable"],
    })
    assert count_matches(frame, []) == (2, 3)
    assert count_matches(frame, [{"field": "SKU", "operator": "equals", "value": "A"}]) == (2, 2)


def test_match_counts_of_an_empty_frame_is_zero():
    assert match_counts(pd.DataFrame()) == (0, 0)
```

- [ ] **Step 2: Run them and confirm they fail.** Run `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_report_filters.py -q`. Expected: FAIL (`ImportError`).

- [ ] **Step 3: Implement.** Append to `shopify_tool/report_filters.py`:

```python
def match_counts(filtered):
    """(distinct orders, rows) in an already-filtered frame.

    Falls back to the first column when there is no Order_Number, as the
    report dialog's preview always has.
    """
    if filtered is None or filtered.empty:
        return (0, 0)
    order_col = "Order_Number" if "Order_Number" in filtered.columns else filtered.columns[0]
    return (int(filtered[order_col].nunique()), len(filtered))


def count_matches(df, filters):
    """(orders, rows) a report with these filters would contain.

    None when there is no analysis to count against. Counts over
    fulfillable orders only, exactly as the generated file does.
    """
    if df is None or df.empty:
        return None
    return match_counts(apply_report_filters(fulfillable_only(df), filters))
```

In `gui/report_selection_dialog.py` `_update_preview`, replace the block from `filtered = self.apply_filters_fn(...)` through `self._preview_cache[cache_key] = (num_orders, len(filtered))` with:

```python
                    filtered = self.apply_filters_fn(self.analysis_df, filters)
                    self._preview_cache[cache_key] = match_counts(filtered)
```

and add `from shopify_tool.report_filters import match_counts` to its imports.

- [ ] **Step 4: Run the tests and confirm they pass.** Run `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_report_filters.py tests/test_generate_reports_dialog.py -q`. Expected: PASS.

- [ ] **Step 5: Commit.**

```
/usr/bin/git add shopify_tool/report_filters.py gui/report_selection_dialog.py tests/test_report_filters.py
/usr/bin/git commit -m "One match count for the report preview and the report editor (9.24)" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 8: Filter rows report edits, delete with an icon, and keep legacy values

**Files:**
- Modify: `gui/settings/fields.py` (`_delete_filter_row`, `_on_filter_criteria_changed`, `add_filter_row`)
- Test: `tests/test_settings_page_reports.py`

**Interfaces:**
- Produces: `add_filter_row(parent_widget_refs, fields, operators, analysis_df, config=None, on_change=None)`. `on_change: Callable[[], None]` runs after a field or operator change, on every value edit, and after removal.

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_settings_page_reports.py` (add `import pandas as pd`, `from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget`, and `from gui.settings.fields import REPORT_FILTER_OPERATORS, add_filter_row`):

```python
def test_a_saved_equals_value_the_analysis_lacks_survives_a_load_and_save():
    """The value combo's twin of the field-combo trap: a saved "UPS" on a
    frame that only has DHL and DPD rendered as "DHL" and was saved back."""
    frame = pd.DataFrame({
        "Order_Number": ["1", "2"],
        "Shipping_Provider": ["DHL", "DPD"],
        "Order_Fulfillment_Status": ["Fulfillable", "Fulfillable"],
    })
    config = [{
        "name": "ups",
        "output_filename": "ups.xlsx",
        "filters": [{"field": "Shipping_Provider", "operator": "equals", "value": "UPS"}],
        "exclude_skus": [],
    }]
    page = ReportsPage(config, [], analysis_df=frame)

    saved = page.collect()["packing_list_configs"][0]["filters"][0]

    assert saved["value"] == "UPS"


def test_a_filter_row_reports_value_edits_and_its_removal():
    host = QWidget()
    refs = {"filters_layout": QVBoxLayout(host), "filters": []}
    calls = []
    add_filter_row(
        refs, ["SKU"], REPORT_FILTER_OPERATORS, None,
        {"field": "SKU", "operator": "contains", "value": "A"},
        on_change=lambda: calls.append(1),
    )
    calls.clear()

    refs["filters"][0]["value_widget"].setText("AB")
    assert calls

    calls.clear()
    delete = refs["filters"][0]["widget"].findChildren(QPushButton)[0]
    assert delete.text() == ""
    assert delete.accessibleName() == "Remove filter"
    assert delete.property("role") == "ghost"
    delete.click()
    assert calls
    assert refs["filters"] == []
```

- [ ] **Step 2: Run them and confirm they fail.** Run `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_page_reports.py -q`. Expected: FAIL (`TypeError: unexpected keyword 'on_change'`, and the value lands as "DHL").

- [ ] **Step 3: Implement in `gui/settings/fields.py`.**

```python
def _delete_filter_row(row_widget, ref_list, ref_dict, on_change=None):
    row_widget.deleteLater()
    ref_list.remove(ref_dict)
    if on_change is not None:
        on_change()
```

In `_on_filter_criteria_changed(filter_refs, analysis_df, initial_value=None, on_change=None)`, change the combobox branch to:

```python
    if use_combobox:
        try:
            unique_values = analysis_df[field].dropna().unique().tolist()
            unique_values = sorted([str(v) for v in unique_values])
            # A saved value the frame no longer contains must still be offered:
            # setCurrentText is a silent no-op otherwise, and the first value
            # would be written back in its place.
            if initial_value not in (None, "") and str(initial_value) not in unique_values:
                unique_values.append(str(initial_value))
            new_widget = WheelIgnoreComboBox()
            new_widget.addItems(unique_values)
            if initial_value not in (None, ""):
                new_widget.setCurrentText(str(initial_value))
        except Exception:
            new_widget = QLineEdit()
            new_widget.setText(str(initial_value) if initial_value else "")
```

After `filter_refs["value_widget"] = new_widget`, append:

```python
    if on_change is not None:
        edited = (
            new_widget.currentTextChanged
            if isinstance(new_widget, QComboBox)
            else new_widget.textChanged
        )
        edited.connect(lambda _text: on_change())
        on_change()
```

In `add_filter_row`, add the `on_change=None` parameter (document it in the docstring's Args). Replace the delete button construction with:

```python
    delete_btn = QPushButton()
    delete_btn.setToolTip("Remove filter")
    delete_btn.setAccessibleName("Remove filter")
    set_button_role(delete_btn, "ghost")
    # The asset library has no "x" glyph; adding one is a packing-tool PR.
    on_theme_changed(delete_btn, lambda _tokens, b=delete_btn: b.setIcon(icon("trash-2")))
```

Pass `on_change=on_change` through both `currentTextChanged` lambdas and the initial `_on_filter_criteria_changed(...)` call. Change the delete connection to `lambda: _delete_filter_row(row_widget, parent_widget_refs["filters"], filter_refs, on_change)`.

Imports, after the usages exist: `QComboBox` from `PySide6.QtWidgets`, `from shared.icons import icon`, `from shared.theme import on_theme_changed`.

- [ ] **Step 4: Run the tests and confirm they pass.** Run `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_page_reports.py tests/test_settings_button_roles.py tests/test_settings_roundtrip.py -q`. Expected: PASS.

- [ ] **Step 5: Commit.**

```
/usr/bin/git add gui/settings/fields.py tests/test_settings_page_reports.py
/usr/bin/git commit -m "Report filter rows report edits, delete with an icon, and keep a saved value the analysis lacks (9.24)" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 9: The report editor shows its match count

**Files:**
- Modify: `gui/settings/report_editor.py`
- Test: `tests/test_settings_report_editor.py` (create)

**Interfaces:**
- Consumes: `count_matches` (Task 7); `add_filter_row(..., on_change=)` (Task 8).
- Produces:
  - `ReportEditor(kind, config=None, analysis_df=None, parent=None, *, match_cache: dict | None = None)`
  - `ReportEditor.match_label: QLabel`, `ReportEditor.refresh_match_count() -> None`, `ReportEditor._match_timer: QTimer`
  - module function `match_text(counts: tuple[int, int] | None) -> str`, and constant `CANT_COUNT`
  - `delete_button` text "Delete report"

- [ ] **Step 1: Write the failing tests.** Create `tests/test_settings_report_editor.py`:

```python
"""A report's editor says how many orders its filters match while they are written."""
import pandas as pd
import pytest
from PySide6.QtWidgets import QApplication

from gui.settings import report_editor
from gui.settings.report_editor import PACKING_LISTS, STOCK_EXPORTS, ReportEditor, match_text

ANALYSIS = pd.DataFrame({
    "Order_Number": ["1", "1", "2", "3"],
    "SKU": ["A", "B", "A", "C"],
    "Order_Fulfillment_Status": ["Fulfillable", "Fulfillable", "Fulfillable", "Not Fulfillable"],
})


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


def test_match_text_copy():
    assert match_text(None) == "Run an analysis to see how many orders this report matches."
    assert match_text((0, 0)) == "Matches no orders. Check the filters."
    assert match_text((1, 1)) == "Matches 1 order · 1 row"
    assert match_text((148, 372)) == "Matches 148 orders · 372 rows"


def test_the_editor_counts_matches_when_it_opens():
    config = {"name": "a", "filters": [{"field": "SKU", "operator": "contains", "value": "A"}]}
    editor = ReportEditor(PACKING_LISTS, config, ANALYSIS)
    assert editor.match_label.text() == "Matches 2 orders · 2 rows"


def test_the_count_follows_a_filter_edit():
    config = {"name": "a", "filters": [{"field": "SKU", "operator": "contains", "value": "A"}]}
    editor = ReportEditor(PACKING_LISTS, config, ANALYSIS)

    editor.filters[0]["value_widget"].setText("C")  # C is only on an unfulfillable order
    assert editor._match_timer.isActive()
    editor.refresh_match_count()

    assert editor.match_label.text() == "Matches no orders. Check the filters."


def test_without_an_analysis_the_editor_says_how_to_get_a_count():
    editor = ReportEditor(STOCK_EXPORTS, {}, None)
    assert editor.match_label.text() == "Run an analysis to see how many orders this report matches."


def test_editors_share_one_match_cache(monkeypatch):
    calls = []
    real = report_editor.count_matches
    monkeypatch.setattr(
        "gui.settings.report_editor.count_matches",
        lambda df, filters: calls.append(1) or real(df, filters),
    )
    config = {"name": "a", "filters": [{"field": "SKU", "operator": "contains", "value": "A"}]}
    cache = {}

    ReportEditor(PACKING_LISTS, config, ANALYSIS, match_cache=cache)
    ReportEditor(PACKING_LISTS, config, ANALYSIS, match_cache=cache)

    assert len(calls) == 1


def test_a_filter_that_cannot_be_counted_says_so(monkeypatch):
    def boom(df, filters):
        raise ValueError("bad regex")

    monkeypatch.setattr("gui.settings.report_editor.count_matches", boom)
    editor = ReportEditor(PACKING_LISTS, {"filters": []}, ANALYSIS)
    assert editor.match_label.text() == "Can't count matches for these filters."
```

- [ ] **Step 2: Run them and confirm they fail.** Run `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_report_editor.py -q`. Expected: FAIL (`ImportError: match_text`).

- [ ] **Step 3: Implement in `gui/settings/report_editor.py`.**

Module level:

```python
logger = logging.getLogger(__name__)

MATCH_DEBOUNCE_MS = 300
CANT_COUNT = "Can't count matches for these filters."


def match_text(counts) -> str:
    """Copy for a report's match count; None means no analysis has run."""
    if counts is None:
        return "Run an analysis to see how many orders this report matches."
    orders, rows = counts
    if orders == 0:
        return "Matches no orders. Check the filters."
    return (
        f"Matches {orders} order{'' if orders == 1 else 's'}"
        f" · {rows} row{'' if rows == 1 else 's'}"
    )
```

`__init__` signature becomes `def __init__(self, kind, config=None, analysis_df=None, parent=None, *, match_cache=None):`. Right after `self.filters = []`:

```python
        # Shared by every editor the Reports page builds: the analysis frame is
        # fixed for the settings dialog's lifetime, so an entry never goes stale.
        self._match_cache = match_cache if match_cache is not None else {}
        self._match_warn = False
        self._match_timer = QTimer(self)
        self._match_timer.setSingleShot(True)
        self._match_timer.setInterval(MATCH_DEBOUNCE_MS)
        self._match_timer.timeout.connect(self.refresh_match_count)
```

After `filters_box_layout.addWidget(add_filter_btn, 0, Qt.AlignLeft)`:

```python
        self.match_label = QLabel("")
        self.match_label.setWordWrap(True)
        self.match_label.setToolTip("Counts fulfillable orders, the same as the generated file.")
        on_theme_changed(self.match_label, self._style_match_label)
        filters_box_layout.addWidget(self.match_label)
```

Change `self.delete_button = QPushButton("Delete")` to `QPushButton("Delete report")`. After the `for f_config in config.get("filters", [])` loop at the end of `__init__`, add `self.refresh_match_count()`.

In `_add_filter`, pass `on_change=self._match_timer.start` as the last argument to `add_filter_row`.

New methods:

```python
    def refresh_match_count(self) -> None:
        """Count this report's matches now (the timer calls this after edits)."""
        filters = self.collect()["filters"]
        key = json.dumps(filters, sort_keys=True, default=str)
        try:
            if key not in self._match_cache:
                self._match_cache[key] = count_matches(self.analysis_df, filters)
            counts = self._match_cache[key]
            text, warn = match_text(counts), counts is not None and counts[0] == 0
        except Exception:
            # Debug, not warning: a half-typed regex lands here on every keystroke.
            logger.debug("Couldn't count report matches", exc_info=True)
            text, warn = CANT_COUNT, False
        self._match_warn = warn
        self.match_label.setText(text)
        self._style_match_label(current_tokens())

    def _style_match_label(self, tokens) -> None:
        color = tokens.status_warning if self._match_warn else tokens.text_secondary
        self.match_label.setStyleSheet(f"{font_css('caption')} color: {color};")
```

Imports, after the usages exist: `import json`, `import logging`; `QTimer` from `PySide6.QtCore`; `from shared.theme import current_tokens, font_css, on_theme_changed`; `count_matches` added to the `shopify_tool.report_filters` import.

- [ ] **Step 4: Run the tests and confirm they pass.** Run `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_report_editor.py tests/test_settings_page_reports.py tests/test_settings_roundtrip.py -q`. Expected: PASS.

- [ ] **Step 5: Commit.**

```
/usr/bin/git add gui/settings/report_editor.py tests/test_settings_report_editor.py
/usr/bin/git commit -m "The report editor shows a live match count (9.24)" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 10: Reports becomes two lists and one editor

**Files:**
- Modify: `gui/settings/reports.py` (whole file)
- Test: `tests/test_settings_page_reports.py`

**Interfaces:**
- Consumes: `ReportEditor(..., match_cache=)`, `.name_edit`, `.delete_button`, `.collect()`, `.kind` (Task 9); `StatePanel(title, cause, *, action_text, action_role)` with `.button`.
- Produces: `ReportsPage(packing_configs, stock_configs, analysis_df=None, parent=None)`, `add_report(kind, config=None) -> ReportEditor`, `collect()`. Internals the tests use: `_lists: dict[str, QListWidget]`, `_editor: ReportEditor | None`, `_empty: StatePanel`. Module constant `UNTITLED = "Untitled report"`.

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_settings_page_reports.py` (add `from gui.settings.report_editor import PACKING_LISTS, STOCK_EXPORTS, ReportEditor` and `from gui.settings.reports import UNTITLED`):

```python
def _named(*names):
    return [{**PACKING[0], "name": name} for name in names]


def test_the_page_holds_one_editor_at_a_time():
    page = ReportsPage(PACKING, STOCK, analysis_df=None)

    page._lists[STOCK_EXPORTS].setCurrentRow(0)

    editors = page.findChildren(ReportEditor)
    assert len(editors) == 1
    assert editors[0].kind == STOCK_EXPORTS
    assert page._lists[PACKING_LISTS].currentRow() == -1


def test_an_edit_survives_switching_reports():
    page = ReportsPage(PACKING, STOCK, analysis_df=None)
    page._editor.name_edit.setText("Renamed")

    page._lists[STOCK_EXPORTS].setCurrentRow(0)

    assert page.collect()["packing_list_configs"][0]["name"] == "Renamed"
    assert page._lists[PACKING_LISTS].item(0).text() == "Renamed"


def test_reordering_the_list_reorders_the_config():
    page = ReportsPage(_named("First", "Second"), [], analysis_df=None)
    reports = page._lists[PACKING_LISTS]

    reports.insertItem(0, reports.takeItem(1))

    assert [c["name"] for c in page.collect()["packing_list_configs"]] == ["Second", "First"]


def test_deleting_opens_the_neighbour():
    page = ReportsPage(_named("A", "B", "C"), [], analysis_df=None)
    page._lists[PACKING_LISTS].setCurrentRow(1)

    page._editor.delete_button.click()

    assert [c["name"] for c in page.collect()["packing_list_configs"]] == ["A", "C"]
    assert page._editor.name_edit.text() == "C"


def test_deleting_the_last_report_shows_the_empty_state():
    page = ReportsPage([], STOCK, analysis_df=None)

    page._editor.delete_button.click()

    assert page._editor is None
    assert not page._empty.isHidden()
    assert page.collect() == {"packing_list_configs": [], "stock_export_configs": []}


def test_a_page_with_no_reports_invites_adding_one():
    page = ReportsPage([], [], analysis_df=None)
    assert page._editor is None
    assert not page._empty.isHidden()
    page._empty.button.click()
    assert page._editor is not None
    assert page._editor.kind == PACKING_LISTS


def test_a_new_report_lists_as_untitled_until_named():
    page = ReportsPage([], [], analysis_df=None)
    editor = page.add_report(STOCK_EXPORTS)
    assert page._lists[STOCK_EXPORTS].item(0).text() == UNTITLED
    editor.name_edit.setText("Nightly")
    assert page._lists[STOCK_EXPORTS].item(0).text() == "Nightly"


def test_opening_a_legacy_report_does_not_mark_the_page_unsaved():
    legacy = {
        "name": "legacy", "output_filename": "l.xlsx",
        "filters": [{"field": "SKU", "operator": "!=", "value": "A"}], "exclude_skus": [],
    }
    page = ReportsPage([PACKING[0], legacy], [], analysis_df=None)
    page.mark_clean()

    page._lists[PACKING_LISTS].setCurrentRow(1)

    assert page.is_dirty() is False
```

- [ ] **Step 2: Run them and confirm they fail.** Run `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_page_reports.py -q`. Expected: FAIL (`AttributeError: _lists`).

- [ ] **Step 3: Implement.** Replace `gui/settings/reports.py` with:

```python
"""Packing lists and stock exports: one list per kind, one editor at a time.

List order is config order, and GenerateReportsDialog renders each config
array in order -- so dragging a report here sets the order it generates in.
Two lists rather than one grouped list: the kinds are separate config keys,
and a drag between them is impossible by construction.
"""

import itertools

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractScrollArea,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from gui.components.state_panel import StatePanel
from gui.settings.base import SettingsPage
from gui.settings.report_editor import PACKING_LISTS, STOCK_EXPORTS, ReportEditor
from shared.icons import icon
from shared.theme import font_css, on_theme_changed, set_button_role

KINDS = (
    (PACKING_LISTS, "Packing lists", "Add packing list", "packing_list_configs"),
    (STOCK_EXPORTS, "Stock exports", "Add stock export", "stock_export_configs"),
)
UNTITLED = "Untitled report"
LIST_COLUMN_WIDTH = 240


class ReportsPage(SettingsPage):
    """Owns both packing_list_configs and stock_export_configs."""

    def __init__(self, packing_configs, stock_configs, analysis_df=None, parent=None):
        super().__init__(parent)
        self.analysis_df = analysis_df
        self._store: dict[int, dict] = {}
        self._next_key = itertools.count()
        self._lists: dict[str, QListWidget] = {}
        self._editor: ReportEditor | None = None
        self._editor_key: int | None = None
        self._match_cache: dict = {}

        layout = QHBoxLayout(self)

        column = QWidget()
        column_layout = QVBoxLayout(column)
        column_layout.setContentsMargins(0, 0, 0, 0)
        for kind, title, add_label, _config_key in KINDS:
            heading_row = QHBoxLayout()
            heading = QLabel(title)
            on_theme_changed(
                heading, lambda _tokens, h=heading: h.setStyleSheet(font_css("label", bold=True))
            )
            heading_row.addWidget(heading, 1)
            add_button = QPushButton()
            add_button.setToolTip(add_label)
            add_button.setAccessibleName(add_label)
            set_button_role(add_button, "ghost")
            on_theme_changed(add_button, lambda _tokens, b=add_button: b.setIcon(icon("plus")))
            add_button.clicked.connect(lambda _checked=False, k=kind: self.add_report(k))
            heading_row.addWidget(add_button)
            column_layout.addLayout(heading_row)

            reports = QListWidget()
            reports.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
            reports.setDefaultDropAction(Qt.DropAction.MoveAction)
            reports.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents)
            reports.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            reports.currentItemChanged.connect(
                lambda current, _previous, k=kind: self._on_current_changed(k, current)
            )
            column_layout.addWidget(reports)
            self._lists[kind] = reports

        hint = QLabel("Drag a report to change the order it generates in.")
        hint.setWordWrap(True)
        on_theme_changed(
            hint,
            lambda tokens, h=hint: h.setStyleSheet(
                f"{font_css('caption')} color: {tokens.text_secondary};"
            ),
        )
        column_layout.addWidget(hint)
        column_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setFixedWidth(LIST_COLUMN_WIDTH)
        scroll.setWidget(column)
        layout.addWidget(scroll)

        self._editor_layout = QVBoxLayout()
        layout.addLayout(self._editor_layout, 1)
        # Secondary: inside Settings, Save is the only primary.
        self._empty = StatePanel(
            "No reports yet",
            "Add a packing list or a stock export, then generate it from Results after an analysis.",
            action_text="Add packing list",
            action_role="secondary",
        )
        self._empty.button.clicked.connect(lambda _checked=False: self.add_report(PACKING_LISTS))
        self._editor_layout.addWidget(self._empty)

        for config in packing_configs or []:
            self._append(PACKING_LISTS, config)
        for config in stock_configs or []:
            self._append(STOCK_EXPORTS, config)
        self._select_first()

    def add_report(self, kind, config=None) -> ReportEditor:
        """Append a report to `kind`, open it, and return its editor."""
        item = self._append(kind, config or {"name": "", "output_filename": "", "filters": []})
        self._lists[kind].setCurrentItem(item)
        self._editor.name_edit.setFocus()
        return self._editor

    def collect(self) -> dict:
        self._stash()
        return {
            config_key: [
                self._store[self._lists[kind].item(row).data(Qt.ItemDataRole.UserRole)]
                for row in range(self._lists[kind].count())
            ]
            for kind, _title, _add_label, config_key in KINDS
        }

    def _append(self, kind, config) -> QListWidgetItem:
        key = next(self._next_key)
        # Normalised once, through the editor that will show it: without this,
        # merely opening a report with a legacy operator would mark the page
        # unsaved. ponytail: builds every editor once at open; fine at the
        # handful of reports a client has.
        probe = ReportEditor(kind, config, self.analysis_df, match_cache=self._match_cache)
        self._store[key] = probe.collect()
        probe.deleteLater()
        item = QListWidgetItem(self._store[key]["name"].strip() or UNTITLED)
        item.setData(Qt.ItemDataRole.UserRole, key)
        self._lists[kind].addItem(item)
        return item

    def _on_current_changed(self, kind, item) -> None:
        if item is None:
            return
        for other_kind, other in self._lists.items():
            if other_kind != kind:
                other.blockSignals(True)
                other.setCurrentRow(-1)
                other.clearSelection()
                other.blockSignals(False)
        self._show(kind, item.data(Qt.ItemDataRole.UserRole))

    def _show(self, kind, key) -> None:
        if key == self._editor_key:
            return  # a drag re-emits currentItemChanged for the same report
        self._stash()
        self._drop_editor()
        editor = ReportEditor(kind, self._store[key], self.analysis_df, match_cache=self._match_cache)
        editor.name_edit.textChanged.connect(lambda text, k=key: self._rename(k, text))
        editor.delete_button.clicked.connect(lambda _checked=False, k=key: self._delete(k))
        self._editor, self._editor_key = editor, key
        self._empty.hide()
        self._editor_layout.addWidget(editor)

    def _stash(self) -> None:
        if self._editor is not None:
            self._store[self._editor_key] = self._editor.collect()

    def _drop_editor(self) -> None:
        if self._editor is not None:
            self._editor.setParent(None)
            self._editor.deleteLater()
        self._editor, self._editor_key = None, None

    def _find(self, key) -> tuple[str, int]:
        for kind, reports in self._lists.items():
            for row in range(reports.count()):
                if reports.item(row).data(Qt.ItemDataRole.UserRole) == key:
                    return kind, row
        raise KeyError(key)

    def _rename(self, key, text) -> None:
        kind, row = self._find(key)
        self._lists[kind].item(row).setText(text.strip() or UNTITLED)

    def _delete(self, key) -> None:
        """No confirm and no toast: the settings window's Cancel undoes it."""
        kind, row = self._find(key)
        reports = self._lists[kind]
        self._drop_editor()
        self._store.pop(key)
        reports.blockSignals(True)
        reports.takeItem(row)
        reports.setCurrentRow(-1)
        reports.blockSignals(False)
        if reports.count():
            reports.setCurrentRow(min(row, reports.count() - 1))
        else:
            self._select_first()

    def _select_first(self) -> None:
        for reports in self._lists.values():
            if reports.count():
                reports.blockSignals(True)
                reports.setCurrentRow(-1)
                reports.blockSignals(False)
                reports.setCurrentRow(0)
                return
        self._drop_editor()
        self._empty.show()
```

- [ ] **Step 4: Run the tests and confirm they pass.** Run `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_page_reports.py tests/test_settings_report_editor.py tests/test_settings_roundtrip.py tests/test_settings_unsaved.py tests/test_settings_button_roles.py -q`. Expected: PASS. If `test_the_page_holds_one_editor_at_a_time` counts two editors, a probe or a dropped editor still has a parent: fix `_append` / `_drop_editor`, not the test.

- [ ] **Step 5: Commit.**

```
/usr/bin/git add gui/settings/reports.py tests/test_settings_page_reports.py
/usr/bin/git commit -m "Reports becomes two orderable lists and one editor (9.24)" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 11: Verify the whole bundle

- [ ] **Step 1:** Run `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`. Expected: every test passes, roughly 1500 + ~45 new. Paste the summary line into `state.md`.
- [ ] **Step 2:** Run `.venv/bin/ruff check . --exclude shared`. Expected: clean. Fix and commit anything it reports.
- [ ] **Step 3:** Run `rg -n "QMessageBox" gui/settings`. Expected: no output.
- [ ] **Step 4:** Look at it. Run `QT_QPA_PLATFORM=offscreen .venv/bin/python run_dev.py` if a display is available (use the `run` skill otherwise), open Settings, and check, in both themes:
  - editing Sets shows the dot and the footer text
  - Cancel shows the guard
  - Reports shows two lists, one editor and a match count
  - the filter delete is a trash icon

  If no display is available, say so in `state.md` rather than claiming it.
- [ ] **Step 5:** Run `graphify update .`.
- [ ] **Step 6:** Push with `/usr/bin/git push -u origin worktree-phase9-bundle10-settings-reports`, then set `next_stage: C` in `state.md`.
