"""The one-row bar across the top of every screen.

Client selector, session id, status, and exactly one primary action. "One
primary per screen" is enforced structurally: there is a single action button
and it is the only place in the component library that marks a button primary.
Replaces the sidebar of 70px client cards with a dropdown.
"""

import enum

from PySide6.QtCore import QEvent, QPoint, Qt, Signal
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
    QPushButton,
    QToolButton,
    QWidget,
)

from gui.components.overflow import OverflowMenu, overflow_button
from gui.theme_manager import font_css, get_theme_manager, set_button_role
from shared.icons import icon
from shared.theme import StatusChip, on_theme_changed

BAR_HEIGHT = 48
_CLIENT_NAME_WIDTH = 200


class BarState(enum.Enum):
    """What the bar knows about, which decides where the one primary sits.

    Orthogonal to which screen is showing: the state decides *whether* a
    right-hand primary exists, bind_action decides *which button* it is.
    Collapsing the two would leave Generate Reports with no home.
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

_DOT_PX = 10          # matches StatusDot's default diameter
_NEW_CLIENT = "New client…"
_MANAGE_GROUPS = "Manage groups…"
_REFRESH = "Refresh clients"
_ACTIONS = (_REFRESH, _NEW_CLIENT, _MANAGE_GROUPS)

# The ladder, widest trigger first. Qt's own elision has no order and would
# take the session ID first because it is the longest string in the row --
# and an elided ID is a wrong ID.
_LADDER = (
    (1100, "spacer"),      # inter-group spacer collapses to 8px
    (900, "client"),       # client name elides inside its 200px
    (700, "progress"),     # progress drops the phase name, keeps the percent
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
        event.ignore()          # a client switch is never a scroll gesture

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
    actionTriggered = Signal()
    newSessionRequested = Signal()
    openFolderRequested = Signal()
    cancelRequested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        theme = get_theme_manager().get_current_theme()
        self._apply_theme()
        # A widget sheet outranks the app's, so baking the colours in once
        # would leave a light bar over dark pages after a theme toggle.
        get_theme_manager().theme_changed.connect(self._apply_theme)

        self._repopulating = False
        self._restore_client = ""

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
        self.client_selector.currentTextChanged.connect(self._on_client_changed)
        self.client_selector.activated.connect(self._on_row_activated)
        view = self.client_selector.view()
        view.setContextMenuPolicy(Qt.CustomContextMenu)
        view.customContextMenuRequested.connect(self._on_row_context_menu)
        layout.addWidget(self.client_selector)

        self.setFixedHeight(BAR_HEIGHT)
        self.client_selector.setFixedWidth(_CLIENT_NAME_WIDTH)

        self.new_session_button = QPushButton("New Session", self)
        set_button_role(self.new_session_button, "primary")
        self.new_session_button.clicked.connect(self.newSessionRequested.emit)
        self.new_session_button.hide()
        layout.addWidget(self.new_session_button)

        self.session_label = QLabel("", self)
        self.session_label.setStyleSheet(font_css("caption"))
        layout.addWidget(self.session_label)

        # Icon-only: its target is the string to its left. The glyph is
        # re-rendered on a theme change -- a QIcon is a snapshot, and the
        # dark theme's grey is invisible on the light one.
        self.open_folder_button = QToolButton(self)
        self.open_folder_button.setAutoRaise(True)
        self.open_folder_button.setToolTip("Open session folder")
        self.open_folder_button.setIcon(icon("folder-open"))
        on_theme_changed(
            self.open_folder_button,
            lambda _t=None, b=self.open_folder_button: b.setIcon(icon("folder-open")),
        )
        self.open_folder_button.clicked.connect(self.openFolderRequested.emit)
        self.open_folder_button.hide()
        layout.addWidget(self.open_folder_button)

        self.status_chip = StatusChip("text_secondary", "", theme, parent=self)
        self.status_chip.hide()   # an empty chip still paints a tinted pill
        layout.addWidget(self.status_chip)

        self.progress_label = QLabel("", self)
        self.progress_label.setStyleSheet(font_css("caption"))
        self.progress_label.hide()
        layout.addWidget(self.progress_label)

        layout.addStretch()

        self.action_button = QPushButton("", self)
        set_button_role(self.action_button, "primary")
        self.action_button.clicked.connect(self.actionTriggered.emit)
        self.action_button.hide()
        layout.addWidget(self.action_button)

        self.cancel_button = QPushButton("Cancel", self)
        set_button_role(self.cancel_button, "danger")
        self.cancel_button.clicked.connect(self.cancelRequested.emit)
        self.cancel_button.hide()
        layout.addWidget(self.cancel_button)

        self.overflow = OverflowMenu(self)
        self.overflow_button = overflow_button(self.overflow, self)
        layout.addWidget(self.overflow_button)

        self._state = BarState.NO_CLIENT
        self._progress = (0, "")

        self._bound_action = None
        self.action_button.clicked.connect(self._forward_action_click)

    def _apply_theme(self) -> None:
        theme = get_theme_manager().get_current_theme()
        # Type-scoped, not bare: a selector-less sheet is wrapped into `* {}`
        # and a parent's sheet outranks the app's, so `background-color` here
        # would repaint every child -- flattening the button roles the app
        # stylesheet sets. Same reason for the scoping in the other containers.
        self.setStyleSheet(
            f"CommandBar {{ background-color: {theme.surface_raised};"
            f" border-bottom: 1px solid {theme.border_subtle}; }}"
        )

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
                members = [c for c in data["group_members"].get(group.get("id"), [])
                           if c in data["all_clients"]]
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
        item.setFlags(Qt.NoItemFlags)          # a caption, never a choice
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
            if (item.data(Qt.UserRole) == ROW_CLIENT
                    and item.data(Qt.UserRole + 1) == client_id):
                self.client_selector.setCurrentIndex(i)
                return

    def set_session(self, text: str) -> None:
        self.session_label.setText(text)

    def set_status(self, role: str, text: str) -> None:
        self.status_chip.set_status(
            role, text, get_theme_manager().get_current_theme()
        )
        self.status_chip.setVisible(bool(text))

    def set_action(self, label: str) -> QPushButton:
        """Label and reveal the screen's single primary action.

        Drops any bind_action mirroring, and resets what the mirror had set --
        otherwise a set_action screen following a bind_action one inherits the
        old button's tooltip and enabled state, and one click fires both
        actionTriggered and the button that is no longer on screen.
        """
        self._unbind()
        self.action_button.setToolTip("")
        self.action_button.setEnabled(True)
        self.action_button.setText(label)
        self.action_button.show()
        self._refresh()
        return self.action_button

    def _unbind(self) -> None:
        if self._bound_action is not None:
            self._bound_action.removeEventFilter(self)
            self._bound_action = None

    def bind_action(self, button: QPushButton | None) -> None:
        """Mirror a screen's own primary button in the bar's action slot.

        The bound button stays the command: its clicked connections and the
        setEnabled call sites in file_handler and main_window_pyside keep working
        untouched, and the bar is a second presentation of it rather than a
        replacement. Passing None hides the slot, for a screen with no primary.

        ponytail: a hidden QPushButton as the command's model is what QAction
        does properly, but QPushButton cannot consume a QAction -- only
        QToolButton can, via setDefaultAction -- so retrofitting one would change
        the widget class at every call site that touches these three buttons.
        Revisit if a third presentation of the same command ever appears.
        """
        self._unbind()
        if button is None:
            self.action_button.hide()
            self._refresh()
            return
        self._bound_action = button
        button.installEventFilter(self)
        self.action_button.setToolTip(button.toolTip())
        self.action_button.setEnabled(button.isEnabled())
        self.action_button.setText(button.text())
        self.action_button.show()
        self._refresh()

    def _forward_action_click(self) -> None:
        if self._bound_action is not None:
            self._bound_action.click()

    def eventFilter(self, watched, event):
        # QWidget has no enabledChanged signal; this event is Qt's only notice.
        if (watched is self._bound_action
                and event.type() == QEvent.Type.EnabledChange):
            self.action_button.setEnabled(watched.isEnabled())
        return super().eventFilter(watched, event)

    def set_state(self, state: BarState) -> None:
        """Which of the four situations the bar is in. See BarState."""
        self._state = state
        self._refresh()

    def set_progress(self, percent: int, phase: str) -> None:
        self._progress = (percent, phase)
        self._refresh()

    def _refresh(self) -> None:
        """Resolve state and bound button into what is actually visible.

        One method rather than two setters that each hide things: with two,
        whichever ran last won, and ui_manager calls them from a connection
        change and a screen change that do not know about each other.
        """
        state = self._state
        has_session = state in (BarState.SESSION, BarState.RUNNING)

        self.session_label.setVisible(has_session)
        self.open_folder_button.setVisible(has_session)
        self.status_chip.setVisible(has_session and bool(self.status_chip.text()))

        self.new_session_button.setVisible(state is BarState.NO_SESSION)
        self.cancel_button.setVisible(state is BarState.RUNNING)
        self.action_button.setVisible(
            state is BarState.SESSION and bool(self.action_button.text())
        )

        self.progress_label.setVisible(state is BarState.RUNNING)
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

        percent, phase = self._progress
        if "progress" in fired or not phase:
            self.progress_label.setText(f"{percent}%")
        else:
            self.progress_label.setText(f"{phase} {percent}%")

        self.new_session_button.setText(
            "" if "new_session" in fired else "New Session"
        )
