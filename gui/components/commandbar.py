"""The one-row bar across the top of every screen.

Client selector, session id, status, and exactly one primary action. "One
primary per screen" is enforced structurally: there is a single action button
and it is the only place in the component library that marks a button primary.
Replaces the sidebar of 70px client cards with a dropdown.
"""

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QIcon,
    QPainter,
    QPixmap,
    QStandardItem,
    QStandardItemModel,
)
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QWidget

from gui.theme_manager import font_css, get_theme_manager, set_button_role
from shared.theme import StatusChip

# What a dropdown row is, at Qt.UserRole. The payload at Qt.UserRole + 1 is a
# client id for ROW_CLIENT and the action's own label for ROW_ACTION.
ROW_SECTION = "section"
ROW_CLIENT = "client"
ROW_ACTION = "action"

_DOT_PX = 10          # matches StatusDot's default diameter
_NEW_CLIENT = "New client…"
_MANAGE_GROUPS = "Manage groups…"


class CommandBar(QWidget):
    """Emits selections and the action; owns no application state."""

    clientChanged = Signal(str)
    clientMenuRequested = Signal(str, QPoint)
    createClientRequested = Signal()
    manageGroupsRequested = Signal()
    actionTriggered = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        theme = get_theme_manager().get_current_theme()
        # Type-scoped, not bare: a selector-less sheet is wrapped into `* {}`
        # and a parent's sheet outranks the app's, so `background-color` here
        # would repaint every child -- flattening the button roles the app
        # stylesheet sets. Same reason for the scoping in the other containers.
        self.setStyleSheet(
            f"CommandBar {{ background-color: {theme.surface_raised};"
            f" border-bottom: 1px solid {theme.border_subtle}; }}"
        )

        self._repopulating = False
        self._restore_client = ""

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(12)

        self.client_selector = QComboBox(self)
        self.client_selector.setModel(QStandardItemModel(self.client_selector))
        self.client_selector.currentTextChanged.connect(self._on_client_changed)
        self.client_selector.activated.connect(self._on_row_activated)
        view = self.client_selector.view()
        view.setContextMenuPolicy(Qt.CustomContextMenu)
        view.customContextMenuRequested.connect(self._on_row_context_menu)
        layout.addWidget(self.client_selector)

        self.session_label = QLabel("", self)
        self.session_label.setStyleSheet(font_css("caption"))
        layout.addWidget(self.session_label)

        self.status_chip = StatusChip("text_secondary", "", theme, parent=self)
        self.status_chip.hide()   # an empty chip still paints a tinted pill
        layout.addWidget(self.status_chip)

        layout.addStretch()

        self.action_button = QPushButton("", self)
        set_button_role(self.action_button, "primary")
        self.action_button.clicked.connect(self.actionTriggered.emit)
        self.action_button.hide()
        layout.addWidget(self.action_button)

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
        keep = self.current_client()
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

            self._add_action(_NEW_CLIENT)
            self._add_action(_MANAGE_GROUPS)
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

    def _on_client_changed(self, name: str) -> None:
        # Repopulating fires currentTextChanged per removal/insert; a consumer
        # reloading a client per signal would thrash the network file server.
        # An action row landing in the box is not a client change either.
        if self._repopulating:
            return
        if self._row_kind(self.client_selector.currentIndex()) != ROW_CLIENT:
            return
        self._restore_client = name
        self.clientChanged.emit(name)

    def _on_row_activated(self, index: int) -> None:
        """activated() is user-initiated only, so this never fires on a
        programmatic setCurrentIndex."""
        if self._row_kind(index) != ROW_ACTION:
            return
        label = self.client_selector.model().item(index).data(Qt.UserRole + 1)
        # Put the box back on the client the action row displaced.
        if self._restore_client:
            self.set_current_client(self._restore_client)
        if label == _NEW_CLIENT:
            self.createClientRequested.emit()
        else:
            self.manageGroupsRequested.emit()

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
        model = self.client_selector.model()
        for i in range(model.rowCount()):
            item = model.item(i)
            if (item.data(Qt.UserRole) == ROW_CLIENT
                    and item.data(Qt.UserRole + 1) == client_id):
                self.client_selector.setCurrentIndex(i)
                self._restore_client = client_id
                return

    def set_session(self, text: str) -> None:
        self.session_label.setText(text)

    def set_status(self, role: str, text: str) -> None:
        self.status_chip.set_status(
            role, text, get_theme_manager().get_current_theme()
        )
        self.status_chip.setVisible(bool(text))

    def set_action(self, label: str) -> QPushButton:
        """Label and reveal the screen's single primary action."""
        self.action_button.setText(label)
        self.action_button.show()
        return self.action_button
