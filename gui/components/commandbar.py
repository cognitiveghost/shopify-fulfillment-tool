"""The one-row bar across the top of every screen.

Client selector, New session, Open recent, and the open session's name as a
chip. It holds no screen's action: each page draws its own primary. While a
run is going it names the step beside a disabled "Running…" (phase 3 spec
section 8). Replaces the sidebar of 70px client cards with a dropdown.
"""

import enum

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QIcon,
    QPainter,
    QPixmap,
    QStandardItem,
    QStandardItemModel,
)
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLayout,
    QMenu,
    QPushButton,
    QToolButton,
    QWidget,
)

from gui.theme_manager import font_css, get_theme_manager, set_button_role
from shared.components.overflow import OverflowMenu, overflow_button
from shared.icons import icon
from shared.theme import on_theme_changed

BAR_HEIGHT = 48
_CLIENT_NAME_WIDTH = 200


class BarState(enum.Enum):
    """What the bar knows about: no client, no session, a session, a run.

    It decides what is enabled and whether the chip and the step readout
    show. Which screen is showing is set_screen's, separately.
    """

    NO_CLIENT = "no_client"
    NO_SESSION = "no_session"
    SESSION = "session"
    RUNNING = "running"


# What a dropdown row is, at Qt.UserRole. The payload at Qt.UserRole + 1 is a
# client id for ROW_CLIENT and the action's own label for ROW_ACTION.
ROW_SECTION = "section"
ROW_CLIENT = "client"
ROW_ACTION = "action"

_DOT_PX = 10  # matches StatusDot's default diameter
_NEW_CLIENT = "New client…"
_MANAGE_GROUPS = "Manage groups…"
_REFRESH = "Refresh clients"
_ACTIONS = (_REFRESH, _NEW_CLIENT, _MANAGE_GROUPS)

# The ladder, widest trigger first. Qt's own elision has no order and would
# take the session ID first because it is the longest string in the row --
# and an elided ID is a wrong ID.
_LADDER = (
    (1100, "spacer"),  # inter-group spacer collapses to 8px
    (900, "client"),  # client name elides inside its 200px
    (700, "step"),  # the step readout drops its name, keeps the count
    (500, "new_session"),  # New Session goes icon-only
)


class _ClientCombo(QComboBox):
    """A client picker the wheel and the arrow keys cannot misfire.

    QComboBox emits activated() for a wheel notch and for Up/Down on a closed
    box, not only for a pick from the popup -- and the action rows live in the
    same model as the clients. So an idle scroll over the bar opened the modal
    create-client dialog, and one row earlier switched client, which reloads
    the config and clears the undo history. Disabling the rows does not help:
    QComboBox navigation only tests Qt.ItemIsEnabled.
    """

    def wheelEvent(self, event) -> None:
        event.ignore()  # a client switch is never a scroll gesture

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Up, Qt.Key_Down) and not self.view().isVisible():
            self._step(-1 if event.key() == Qt.Key_Up else 1)
            return
        super().keyPressEvent(event)

    def _step(self, delta: int) -> None:
        """Move to the next client row. setCurrentIndex, never activated()."""
        model = self.model()
        i = self.currentIndex() + delta
        while 0 <= i < model.rowCount():
            if model.item(i).data(Qt.UserRole) == ROW_CLIENT:
                self.setCurrentIndex(i)
                return
            i += delta


class CommandBar(QWidget):
    """Emits selections and the action; owns no application state."""

    clientChanged = Signal(str)
    clientMenuRequested = Signal(str, QPoint)
    createClientRequested = Signal()
    manageGroupsRequested = Signal()
    refreshRequested = Signal()
    newSessionRequested = Signal()
    sessionChosen = Signal(str)
    browseAllRequested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # A QWidget subclass paints no QSS background without this.
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._apply_theme()
        # A widget sheet outranks the app's, so baking the colours in once
        # would leave a light bar over dark pages after a theme toggle.
        get_theme_manager().theme_changed.connect(self._apply_theme)

        self._repopulating = False
        self._restore_client = ""
        self._show_chip = False
        self._show_meta = False
        self._analysed_text = ""
        self._stock_text = ""
        self._recent: list[tuple[str, str]] = []
        self._session_text = ""
        self._state = BarState.NO_CLIENT
        self._step = (0, 0, "")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(12)
        # The ladder shrinks this bar below its content's natural width when
        # the window narrows. SetDefaultConstraint would instead push that
        # width onto the widget as a hard minimum, so resize() below it (and
        # therefore the ladder's own resizeEvent) would never fire.
        layout.setSizeConstraint(QLayout.SetNoConstraint)

        self.client_selector = _ClientCombo(self)
        self.client_selector.setModel(QStandardItemModel(self.client_selector))
        self.client_selector.setPlaceholderText("Choose a client")
        self.client_selector.currentTextChanged.connect(self._on_client_changed)
        self.client_selector.activated.connect(self._on_row_activated)
        view = self.client_selector.view()
        view.setContextMenuPolicy(Qt.CustomContextMenu)
        view.customContextMenuRequested.connect(self._on_row_context_menu)
        layout.addWidget(self.client_selector)

        self.setFixedHeight(BAR_HEIGHT)
        self.client_selector.setFixedWidth(_CLIENT_NAME_WIDTH)

        # Always there: a session can be started from any screen. Secondary,
        # because the screen's primary is the page's own.
        self.new_session_button = QPushButton("New session", self)
        set_button_role(self.new_session_button, "secondary")
        self.new_session_button.clicked.connect(self.newSessionRequested.emit)
        # A QIcon is a snapshot: re-rendered on a theme change.
        on_theme_changed(
            self.new_session_button,
            lambda _t=None, b=self.new_session_button: b.setIcon(icon("plus")),
        )
        layout.addWidget(self.new_session_button)

        # The route back to yesterday's work. Always reads "Open recent": the
        # open session's name is the chip beside it, or the page's own head.
        self.session_button = QToolButton(self)
        self.session_button.setAutoRaise(True)
        self.session_button.setPopupMode(QToolButton.InstantPopup)
        self.session_button.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.session_button.setText("Open recent")
        self.session_menu = QMenu(self.session_button)
        self.session_button.setMenu(self.session_menu)
        layout.addWidget(self.session_button)

        # The open session's name, never elided: an elided ID is a wrong ID.
        self.session_chip = QLabel("", self)
        self.session_chip.hide()
        layout.addWidget(self.session_chip)

        # Results only: "analysed 14:06 · stock file 19 h old".
        self.meta_label = QLabel("", self)
        self.meta_label.hide()
        layout.addWidget(self.meta_label)

        layout.addStretch()

        # While a run is going: "Step 2 of 4", the step's name, and a button
        # that only says so. Cancel is on the Setup page.
        self.step_count_label = QLabel("", self)
        self.step_count_label.hide()
        layout.addWidget(self.step_count_label)
        self.step_name_label = QLabel("", self)
        self.step_name_label.hide()
        layout.addWidget(self.step_name_label)
        self.running_button = QPushButton("Running…", self)
        set_button_role(self.running_button, "primary")
        self.running_button.setEnabled(False)
        self.running_button.hide()
        layout.addWidget(self.running_button)

        self.overflow = OverflowMenu(self)
        self.overflow_button = overflow_button(self.overflow, self)
        layout.addWidget(self.overflow_button)

        on_theme_changed(self.session_chip, self._style_labels)
        self._refresh()

    def _apply_theme(self) -> None:
        theme = get_theme_manager().get_current_theme()
        # Type-scoped, not bare: a selector-less sheet is wrapped into `* {}`
        # and a parent's sheet outranks the app's, so `background-color` here
        # would repaint every child -- flattening the button roles the app
        # stylesheet sets. Same reason for the scoping in the other containers.
        self.setStyleSheet(
            f"CommandBar {{ background-color: {theme.surface_sunken};"
            f" border-bottom: 1px solid {theme.border_subtle}; }}"
        )

    def _style_labels(self, theme=None) -> None:
        """The chip, the meta text and the step readout.

        Their own sheets rather than the app's: a widget sheet has to be
        re-applied on a theme change.
        """
        theme = theme or get_theme_manager().get_current_theme()
        self.session_button.setStyleSheet(font_css("caption"))
        self.session_chip.setStyleSheet(
            f"QLabel {{ {font_css('caption')}"
            f" font-family: {theme.font_family_mono};"
            f" background-color: {theme.surface_raised};"
            f" border: 1px solid {theme.border};"
            f" border-radius: {theme.radius_md}px;"
            " padding: 0px 8px; min-height: 20px; max-height: 20px; }"
        )
        quiet = f"{font_css('caption')} color: {theme.text_secondary};"
        self.meta_label.setStyleSheet(quiet)
        self.step_count_label.setStyleSheet(
            f"{quiet} font-family: {theme.font_family_mono};"
        )
        self.step_name_label.setStyleSheet(font_css("caption", bold=True))

    def set_screen(self, chip: bool, meta: bool) -> None:
        """Which screen is showing: whether the bar draws the session chip
        (every screen but Setup, whose page head has it) and the analysis age
        (Results)."""
        self._show_chip = bool(chip)
        self._show_meta = bool(meta)
        self._refresh()

    def _refresh_meta(self) -> None:
        """`analysed 14:06 · stock file 19 h old`."""
        parts = [t for t in (self._analysed_text, self._stock_text) if t]
        self.meta_label.setText(" · ".join(t[0].lower() + t[1:] for t in parts))
        has_session = self._state in (BarState.SESSION, BarState.RUNNING)
        self.meta_label.setVisible(self._show_meta and has_session and bool(parts))

    def set_clients(self, names: list[str]) -> None:
        """The flat case: no pins, no groups, just a list."""
        self.set_clients_from(
            {
                "special_groups": {},
                "custom_groups": [],
                "all_clients": list(names),
                "pinned_client_ids": set(),
                "group_members": {},
                "card_data": {},
            }
        )

    def set_clients_from(self, data: dict) -> None:
        """Rebuild the dropdown from ClientDirectory.gather()'s dict.

        Pinned, then each non-empty group, then everyone not yet listed. A
        pinned client that is also in a group appears under both -- that is
        the sidebar's own behaviour, ported rather than corrected.
        """
        # _restore_client, not current_client(): refresh() is async, so a
        # set_current_client() for a client the model does not hold yet must
        # still win when its row finally arrives.
        keep = self._restore_client
        self._repopulating = True
        try:
            model = self.client_selector.model()
            model.clear()
            special = data.get("special_groups", {})
            listed: set[str] = set()

            pinned = [c for c in data["all_clients"] if c in data["pinned_client_ids"]]
            if pinned:
                self._add_section(special.get("pinned", {}).get("name", "Pinned"))
                for client_id in pinned:
                    self._add_client(client_id, data)
                listed.update(pinned)

            for group in data.get("custom_groups", []):
                members = [
                    c
                    for c in data["group_members"].get(group.get("id"), [])
                    if c in data["all_clients"]
                ]
                if not members:
                    continue
                self._add_section(group.get("name", "Unknown"))
                for client_id in members:
                    self._add_client(client_id, data)
                listed.update(members)

            rest = [c for c in data["all_clients"] if c not in listed]
            if rest:
                self._add_section(special.get("all", {}).get("name", "All Clients"))
                for client_id in rest:
                    self._add_client(client_id, data)

            # A blank ROW_SECTION row -- the popup's own non-selectable
            # divider mechanism -- separates the actions from the client
            # list above them. Not QComboBox.insertSeparator(): see
            # _add_action's comment for why. With no clients there is nothing
            # to separate from, and the row would just be a gap above them.
            if self.client_selector.count():
                self._add_section("")
            for label in _ACTIONS:
                self._add_action(label)
            # The first appendRow drags currentIndex to row 0, which is always
            # a section caption -- the bar would show "All Clients" as though
            # the user had chosen it.
            self.client_selector.setCurrentIndex(-1)
        finally:
            self._repopulating = False

        if keep:
            self.set_current_client(keep)

    def _add_section(self, title: str) -> None:
        item = QStandardItem(title)
        item.setData(ROW_SECTION, Qt.UserRole)
        item.setFlags(Qt.NoItemFlags)  # a caption, never a choice
        self.client_selector.model().appendRow(item)

    def _add_client(self, client_id: str, data: dict) -> None:
        settings = data["card_data"].get(client_id, {}).get("ui_settings", {})
        item = QStandardItem(client_id)
        item.setData(ROW_CLIENT, Qt.UserRole)
        item.setData(client_id, Qt.UserRole + 1)
        # The hex is the client's own custom_color, read from disk -- user
        # data, not a literal, so style_lint has nothing to object to.
        colour = settings.get("custom_color")
        if colour:
            item.setIcon(self._dot(colour))
        self.client_selector.model().appendRow(item)

    def _add_action(self, label: str) -> None:
        # No QComboBox.insertSeparator(): it inserts a real, dataless row
        # into the model, which would show up in every row-indexed lookup.
        item = QStandardItem(label)
        item.setData(ROW_ACTION, Qt.UserRole)
        item.setData(label, Qt.UserRole + 1)
        self.client_selector.model().appendRow(item)

    @staticmethod
    def _dot(colour: str) -> QIcon:
        pixmap = QPixmap(_DOT_PX, _DOT_PX)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(colour))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(0, 0, _DOT_PX, _DOT_PX)
        painter.end()
        return QIcon(pixmap)

    def _row_kind(self, index: int) -> str | None:
        item = self.client_selector.model().item(index)
        return None if item is None else item.data(Qt.UserRole)

    def _on_client_changed(self, _text: str) -> None:
        # Repopulating fires currentTextChanged per removal/insert; a consumer
        # reloading a client per signal would thrash the network file server.
        # An action row or a caption landing in the box is not a change either.
        # The id comes from the row's payload, never from the display text.
        if self._repopulating:
            return
        client_id = self.current_client()
        if not client_id:
            return
        self._restore_client = client_id
        self.clientChanged.emit(client_id)

    def _on_row_activated(self, index: int) -> None:
        """activated() is user-initiated only, and _ClientCombo keeps the
        wheel and the arrow keys from ever reaching these rows."""
        if self._row_kind(index) != ROW_ACTION:
            return
        label = self.client_selector.model().item(index).data(Qt.UserRole + 1)
        # Put the box back on the client the action row displaced.
        if self._restore_client:
            self.set_current_client(self._restore_client)
        if label == _NEW_CLIENT:
            self.createClientRequested.emit()
        elif label == _MANAGE_GROUPS:
            self.manageGroupsRequested.emit()
        else:
            self.refreshRequested.emit()

    def _on_row_context_menu(self, position: QPoint) -> None:
        view = self.client_selector.view()
        index = view.indexAt(position)
        if not index.isValid():
            return
        item = self.client_selector.model().item(index.row())
        if item.data(Qt.UserRole) != ROW_CLIENT:
            return
        self.clientMenuRequested.emit(
            item.data(Qt.UserRole + 1), view.viewport().mapToGlobal(position)
        )

    def current_client(self) -> str:
        """The selected client id, or "" when the box is on a non-client row."""
        index = self.client_selector.currentIndex()
        if self._row_kind(index) != ROW_CLIENT:
            return ""
        return self.client_selector.model().item(index).data(Qt.UserRole + 1)

    def set_current_client(self, client_id: str) -> None:
        """Select the first row for this client. Unknown ids are ignored."""
        # Recorded before the search: an id the model does not hold yet is
        # honoured by the next set_clients_from(), not silently dropped.
        self._restore_client = client_id
        model = self.client_selector.model()
        for i in range(model.rowCount()):
            item = model.item(i)
            if (
                item.data(Qt.UserRole) == ROW_CLIENT
                and item.data(Qt.UserRole + 1) == client_id
            ):
                self.client_selector.setCurrentIndex(i)
                return

    def set_recent_sessions(self, items: list[tuple[str, str]]) -> None:
        """Fill the picker. `items` is (display name, session path), newest
        first -- the caller caps the list, because how many sessions are
        "recent" is the screen's decision, not the bar's."""
        self._recent = list(items)
        self.session_menu.clear()
        for name, path in self._recent:
            action = self.session_menu.addAction(name)
            action.setData(path)
            action.triggered.connect(
                lambda _checked=False, p=path: self.sessionChosen.emit(p)
            )
        if self._recent:
            self.session_menu.addSeparator()
        browse = self.session_menu.addAction("Browse all sessions…\tCtrl+3")
        browse.triggered.connect(lambda _checked=False: self.browseAllRequested.emit())
        self._refresh()

    def set_session_text(self, text: str) -> None:
        self._session_text = text
        self._refresh()

    def set_status(self, role: str, text: str) -> None:
        """When the open session was analysed. `role` is kept for the callers
        that pass one; the text is drawn in one quiet colour."""
        self._analysed_text = text
        self._refresh_meta()

    def set_stock_age(self, text: str) -> None:
        self._stock_text = text
        self._refresh_meta()

    def set_state(self, state: BarState) -> None:
        """Which of the four situations the bar is in. See BarState."""
        self._state = state
        self._refresh()

    def set_step(self, index: int, total: int, name: str) -> None:
        """The run's current step: its index in the run's steps, how many
        there are, and its name."""
        self._step = (int(index), int(total), str(name))
        self._refresh()

    def _refresh(self) -> None:
        """Resolve state and screen into what is actually visible.

        One method rather than setters that each hide things: ui_manager
        calls them from a connection change and a screen change that do not
        know about each other.
        """
        state = self._state
        has_session = state in (BarState.SESSION, BarState.RUNNING)
        usable = state in (BarState.NO_SESSION, BarState.SESSION)

        self.new_session_button.setEnabled(usable)
        self.session_button.setEnabled(usable)

        self.session_chip.setText(self._session_text)
        self.session_chip.setVisible(
            has_session and self._show_chip and bool(self._session_text)
        )
        self._refresh_meta()

        running = state is BarState.RUNNING
        self.step_count_label.setVisible(running)
        self.running_button.setVisible(running)
        self._apply_ladder(self.width())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_ladder(self.width())

    def _apply_ladder(self, width: int) -> None:
        fired = {name for trigger, name in _LADDER if width < trigger}

        self.layout().setSpacing(8 if "spacer" in fired else 12)

        self.client_selector.setFixedWidth(
            120 if "client" in fired else _CLIENT_NAME_WIDTH
        )

        index, total, name = self._step
        self.step_count_label.setText(f"Step {index + 1} of {total}" if total else "")
        self.step_name_label.setText(name)
        self.step_name_label.setVisible(
            self._state is BarState.RUNNING and "step" not in fired and bool(name)
        )

        self.new_session_button.setText("" if "new_session" in fired else "New session")
