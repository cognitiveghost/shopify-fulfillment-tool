"""Packing lists and stock exports: one list per kind, one editor at a time.

List order is config order, and GenerateReportsDialog renders each config
array in order -- so dragging a report here sets the order it generates in.
Two lists rather than one grouped list: the kinds are separate config keys,
and a drag between them is impossible by construction.
"""

import itertools

from PySide6.QtCore import QSignalBlocker, Qt
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
from gui.theme_manager import set_button_role
from shared.icons import icon
from shared.theme import font_css, on_theme_changed

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
                heading,
                lambda _tokens, h=heading: h.setStyleSheet(
                    font_css("label", bold=True)
                ),
            )
            heading_row.addWidget(heading, 1)
            add_button = QPushButton()
            add_button.setToolTip(add_label)
            add_button.setAccessibleName(add_label)
            set_button_role(add_button, "ghost")
            on_theme_changed(
                add_button, lambda _tokens, b=add_button: b.setIcon(icon("plus"))
            )
            add_button.clicked.connect(
                lambda _checked=False, k=kind: self.add_report(k)
            )
            heading_row.addWidget(add_button)
            column_layout.addLayout(heading_row)

            reports = QListWidget()
            reports.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
            reports.setDefaultDropAction(Qt.DropAction.MoveAction)
            reports.setSizeAdjustPolicy(
                QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents
            )
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

        # A report with a dozen filters is taller than a warehouse screen.
        editor_host = QWidget()
        self._editor_layout = QVBoxLayout(editor_host)
        self._editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_scroll = QScrollArea()
        editor_scroll.setWidgetResizable(True)
        editor_scroll.setFrameShape(QFrame.Shape.NoFrame)
        editor_scroll.setWidget(editor_host)
        layout.addWidget(editor_scroll, 1)
        # Secondary: inside Settings, Save is the only primary.
        self._empty = StatePanel(
            "No reports yet",
            "Add a packing list or a stock export, then generate it from Results after an analysis.",
            action_text="Add packing list",
            action_role="secondary",
        )
        self._empty.button.clicked.connect(
            lambda _checked=False: self.add_report(PACKING_LISTS)
        )
        self._editor_layout.addWidget(self._empty)

        for config in packing_configs or []:
            self._append(PACKING_LISTS, config)
        for config in stock_configs or []:
            self._append(STOCK_EXPORTS, config)
        self._select_first()

    def add_report(self, kind, config=None) -> ReportEditor:
        """Append a report to `kind`, open it, and return its editor."""
        item = self._append(
            kind, config or {"name": "", "output_filename": "", "filters": []}
        )
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
        probe = ReportEditor(
            kind, config, self.analysis_df, match_cache=self._match_cache
        )
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
                with QSignalBlocker(other):
                    other.setCurrentRow(-1)
                    other.clearSelection()
        self._show(kind, item.data(Qt.ItemDataRole.UserRole))

    def _show(self, kind, key) -> None:
        if key == self._editor_key:
            return  # a drag re-emits currentItemChanged for the same report
        self._stash()
        self._drop_editor()
        editor = ReportEditor(
            kind, self._store[key], self.analysis_df, match_cache=self._match_cache
        )
        editor.name_edit.textChanged.connect(lambda text, k=key: self._rename(k, text))
        editor.delete_button.clicked.connect(
            lambda _checked=False, k=key: self._delete(k)
        )
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
        with QSignalBlocker(reports):
            reports.takeItem(row)
            reports.setCurrentRow(-1)
        if reports.count():
            reports.setCurrentRow(min(row, reports.count() - 1))
        else:
            self._select_first()

    def _select_first(self) -> None:
        for reports in self._lists.values():
            if reports.count():
                with QSignalBlocker(reports):
                    reports.setCurrentRow(-1)
                reports.setCurrentRow(0)
                return
        self._drop_editor()
        self._empty.show()
