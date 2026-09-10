"""One page, two log sources, a tail that follows.

Activity and Execution used to be two widgets on two sub-tabs. They are one
QTreeView now: the source switch swaps LogBufferModel's visible buffer rather
than swapping widgets, so the level filter, the search box and follow-tail
all keep working no matter which source is on screen.

Spec: docs/superpowers/specs/2026-09-07-phase9-bundle7-info-becomes-logs-design.md
"""

import logging

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from gui.log_filter import LogFilterProxy
from gui.log_follow import FollowState
from gui.log_model import LogBufferModel
from gui.status_edge_delegate import StatusEdgeDelegate
from gui.theme_manager import get_theme_manager
from shared.theme import font_css, on_theme_changed, set_button_role

_MESSAGE_COLUMN = 3

_LEVEL_FLOORS = (
    ("All", logging.NOTSET),
    ("Info", logging.INFO),
    ("Warning", logging.WARNING),
    ("Error", logging.ERROR),
)


class LogViewer(QWidget):
    """One viewer over `LogBufferModel`'s two sources."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._settings = QSettings("ShopifyFulfillmentTool", "FulfillmentApp")

        self.model = LogBufferModel()
        self.proxy = LogFilterProxy()
        self.proxy.setSourceModel(self.model)
        self.follow = FollowState()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self._build_control_row())
        layout.addWidget(self._build_view())
        layout.addLayout(self._build_footer_row())

        wrap = bool(self._settings.value("logs/wrap", False, type=bool))
        self.set_wrap(wrap)
        self._sync_footer()

        on_theme_changed(self, lambda _tokens: self._apply_theme())

    # -- construction ---------------------------------------------------

    def _build_control_row(self):
        row = QHBoxLayout()

        self._source_group = QButtonGroup(self)
        for source in (LogBufferModel.ACTIVITY, LogBufferModel.EXECUTION):
            button = QPushButton(source, self)
            button.setCheckable(True)
            button.setChecked(source == self.model.current_source())
            button.clicked.connect(lambda _c, s=source: self.set_source(s))
            self._source_group.addButton(button)
            row.addWidget(button)

        self._level_group = QButtonGroup(self)
        for label, floor in _LEVEL_FLOORS:
            button = QPushButton(label, self)
            button.setCheckable(True)
            button.setChecked(floor == logging.NOTSET)
            button.clicked.connect(lambda _c, f=floor: self.proxy.set_level_floor(f))
            self._level_group.addButton(button)
            row.addWidget(button)

        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText("Search logs…")
        self.search_input.textChanged.connect(self.proxy.set_search)
        row.addWidget(self.search_input, stretch=1)

        self.wrap_toggle = QCheckBox("Wrap", self)
        self.wrap_toggle.toggled.connect(self.set_wrap)
        row.addWidget(self.wrap_toggle)

        self.save_button = QPushButton("Save as text", self)
        set_button_role(self.save_button, "ghost")
        self.save_button.clicked.connect(self._save_as_text)
        row.addWidget(self.save_button)

        return row

    def _build_view(self):
        self.view = QTreeView(self)
        self.view.setRootIsDecorated(False)
        self.view.setModel(self.proxy)
        self.view.setItemDelegate(StatusEdgeDelegate(self.view))
        self.view.setAlternatingRowColors(False)
        self.view.setVerticalScrollMode(QTreeView.ScrollPerPixel)
        self.view.setHorizontalScrollMode(QTreeView.ScrollPerPixel)
        self.view.setSelectionBehavior(QTreeView.SelectRows)
        self.view.setEditTriggers(QTreeView.NoEditTriggers)

        header = self.view.header()
        header.setSectionResizeMode(_MESSAGE_COLUMN, QHeaderView.Stretch)
        for column in range(_MESSAGE_COLUMN):
            header.setSectionResizeMode(column, QHeaderView.ResizeToContents)

        self.view.verticalScrollBar().valueChanged.connect(self._on_scrolled)
        return self.view

    def _build_footer_row(self):
        row = QHBoxLayout()
        self.footer_label = QLabel("", self)
        self.jump_button = QPushButton("Jump to latest", self)
        set_button_role(self.jump_button, "ghost")
        self.jump_button.clicked.connect(self._jump_to_latest)
        row.addWidget(self.footer_label)
        row.addWidget(self.jump_button)
        row.addStretch()
        self.footer_label.hide()
        self.jump_button.hide()
        return row

    # -- the interface callers actually use ------------------------------

    def append(self, entry, source):
        self.model.append(entry, source)
        if source == self.model.current_source():
            self.follow.appended()
            if self.follow.following:
                self.view.scrollToTop()  # newest-first: the tail is the top
            self._sync_footer()

    def set_source(self, source):
        self.model.set_source(source)
        self.follow.jumped_to_latest()
        self.view.scrollToTop()
        self._sync_footer()

    def set_wrap(self, on: bool):
        # Uniform heights and word wrap are mutually exclusive: a wrapped row
        # is taller than its neighbours by definition.
        self.view.setWordWrap(on)
        self.view.setUniformRowHeights(not on)
        self._settings.setValue("logs/wrap", on)
        if self.wrap_toggle.isChecked() != on:
            self.wrap_toggle.setChecked(on)

    # -- follow-tail ------------------------------------------------------

    def _on_scrolled(self, _value):
        bar = self.view.verticalScrollBar()
        # Newest-first, so the tail is the TOP of the view.
        self.follow.scrolled(at_bottom=bar.value() == bar.minimum())
        self._sync_footer()

    def _sync_footer(self):
        pending = self.follow.pending
        visible = pending > 0
        self.footer_label.setVisible(visible)
        self.jump_button.setVisible(visible)
        if visible:
            noun = "entry" if pending == 1 else "entries"
            self.footer_label.setText(f"{pending} new {noun}")

    def _jump_to_latest(self):
        self.follow.jumped_to_latest()
        self.view.scrollToTop()
        self._sync_footer()

    # -- save as text -------------------------------------------------------

    def _save_as_text(self):
        path, _filter = QFileDialog.getSaveFileName(self, "Save log as text")
        if not path:
            return
        with open(path, "w", encoding="utf-8") as handle:
            for entry in self.model.entries():
                ts = entry.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                handle.write(
                    f"{ts}  {entry.level_name:<8} {entry.source}  {entry.message}\n"
                )

    # -- theme --------------------------------------------------------------

    def _apply_theme(self):
        theme = get_theme_manager().get_current_theme()
        self.footer_label.setStyleSheet(
            f"color: {theme.text_secondary}; {font_css('body')}"
        )
        self.search_input.setStyleSheet(
            f"color: {theme.text}; background: {theme.surface}; "
            f"border: 1px solid {theme.border};"
        )
