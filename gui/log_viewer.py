"""One page, two log sources, a tail that follows.

Activity and Execution used to be two widgets on two sub-tabs. They are one
QTreeView now: the source switch swaps LogBufferModel's visible buffer rather
than swapping widgets, so the level filter, the search box and follow-tail
all keep working no matter which source is on screen.

Spec: docs/superpowers/specs/2026-09-07-phase9-bundle7-info-becomes-logs-design.md
"""

import logging

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from gui.components import show_error
from gui.log_filter import LogFilterProxy
from gui.log_follow import FollowState
from gui.log_model import COL_LEVEL, COL_MESSAGE, COL_SOURCE, COL_TIME, LogBufferModel
from gui.status_edge_delegate import StatusEdgeDelegate
from gui.theme_manager import get_theme_manager
from shared.theme import font_css, on_theme_changed, set_button_role

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

        source_group_widget = QWidget(self)
        source_group_widget.setObjectName("logs-source-group")
        source_row = QHBoxLayout(source_group_widget)
        source_row.setContentsMargins(0, 0, 0, 0)
        self._source_group = QButtonGroup(self)
        for source in (LogBufferModel.ACTIVITY, LogBufferModel.EXECUTION):
            button = QPushButton(source, self)
            button.setCheckable(True)
            button.setChecked(source == self.model.current_source())
            button.clicked.connect(lambda _c, s=source: self.set_source(s))
            self._source_group.addButton(button)
            source_row.addWidget(button)
        row.addWidget(source_group_widget)

        divider = QFrame(self)
        divider.setFrameShape(QFrame.VLine)
        divider.setFixedWidth(1)
        row.addWidget(divider)
        self._control_divider = divider

        level_group_widget = QWidget(self)
        level_group_widget.setObjectName("logs-level-group")
        level_row = QHBoxLayout(level_group_widget)
        level_row.setContentsMargins(0, 0, 0, 0)
        self._level_group = QButtonGroup(self)
        for label, floor in _LEVEL_FLOORS:
            button = QPushButton(label, self)
            button.setCheckable(True)
            button.setChecked(floor == logging.NOTSET)
            button.clicked.connect(lambda _c, f=floor: self.proxy.set_level_floor(f))
            self._level_group.addButton(button)
            level_row.addWidget(button)
        row.addWidget(level_group_widget)

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
        header.setSectionResizeMode(COL_MESSAGE, QHeaderView.Stretch)

        # Interactive with a measured starting width, never ResizeToContents:
        # that mode re-queries every row on each insert, so a live log costs
        # O(buffer) per arriving entry -- measured at ~31ms per append at 2200
        # rows and ~52ms at 4800, which is a visible freeze during the burst
        # an analysis run produces. All three columns are bounded anyway, and
        # a fixed width is what lets SOURCE elide rather than widen.
        metrics = QFontMetrics(self.view.font())
        for column, sample in (
            (COL_TIME, "00:00:00"),
            (COL_LEVEL, "WARNING"),
            (COL_SOURCE, "shopify_tool.engine"),
        ):
            header.setSectionResizeMode(column, QHeaderView.Interactive)
            self.view.setColumnWidth(column, metrics.horizontalAdvance(sample) + 24)
        self.view.setTextElideMode(Qt.ElideRight)

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
        # And per-pixel vertical scrolling needs a total pixel height, which
        # without uniform rows it can only get by measuring every row in the
        # buffer -- 40ms per arriving entry at 4800 rows, against 0.6ms with
        # uniform rows. Wrapped rows therefore scroll per item: a wrapped log
        # is one you are reading, not one you are watching stream past.
        self.view.setVerticalScrollMode(
            QTreeView.ScrollPerItem if on else QTreeView.ScrollPerPixel
        )
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
        source = self.model.current_source()
        path, _filter = QFileDialog.getSaveFileName(
            self,
            "Save log as text",
            f"{source.lower()}-log.txt",
            "Text files (*.txt);;All files (*)",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as handle:
                # Oldest first on disk: the screen shows newest-first because
                # the newest line is the one you came to read, but a saved log
                # is read top to bottom like every other log file.
                for entry in reversed(self.model.entries()):
                    ts = entry.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                    handle.write(
                        f"{ts}  {entry.level_name:<8} {entry.source}  {entry.message}\n"
                    )
        except OSError as error:
            # Operators save to UNC shares that go away mid-write. An
            # unhandled OSError out of a Qt slot takes the app down rather
            # than telling anyone which file failed.
            logging.getLogger(__name__).warning(
                "Could not save log to %s: %s", path, error
            )
            show_error(
                self,
                "The log wasn't saved",
                f"{path} couldn't be written. Choose another folder and save again.",
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
        self._control_divider.setStyleSheet(
            f"background: {theme.border}; border: none;"
        )
        toggle_css = (
            "QPushButton:checked {"
            f"background: {theme.selection_bg};"
            f"border: 1px solid {theme.selection_border};"
            f"color: {theme.text};"
            "}"
        )
        for button in (*self._source_group.buttons(), *self._level_group.buttons()):
            button.setStyleSheet(toggle_css)
