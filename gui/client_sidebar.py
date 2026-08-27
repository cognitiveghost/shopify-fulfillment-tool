"""Client Sidebar Widget with collapsible sections and group management.

This widget provides a sidebar for client navigation with:
- Collapsible animation (250px ↔ 40px)
- Sections: Pinned, Custom Groups, All Clients
- Context menu for per-client actions
- Group management dialog
"""

import logging

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QSettings,
    Qt,
    QThreadPool,
    Signal,
)
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from gui.client_card import ClientCard
from gui.client_settings_dialog import ClientCreationDialog, ClientSettingsDialog
from gui.groups_management_dialog import GroupsManagementDialog
from gui.theme_manager import apply_font, font_css, get_theme_manager
from gui.worker import Worker
from shopify_tool.groups_manager import GroupsManager
from shopify_tool.profile_manager import ProfileManager

logger = logging.getLogger(__name__)


class CollapsedClientIndicator(QWidget):
    """Widget showing active client initial in colored circle when sidebar is collapsed."""

    def __init__(self, client_id: str, color: str, parent=None):
        """Initialize collapsed indicator.

        Args:
            client_id: Client ID (e.g., "M")
            color: Hex color for circle (e.g., theme.accent_green)
            parent: Parent widget
        """
        super().__init__(parent)
        self.client_id = client_id
        self.color = QColor(color)
        self.setFixedSize(40, 40)

    def paintEvent(self, event):
        """Draw colored circle with client initial."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw circle
        painter.setBrush(self.color)
        painter.setPen(QPen(Qt.NoPen))
        painter.drawEllipse(5, 5, 30, 30)

        # Draw initial
        painter.setPen(QColor(Qt.white))
        apply_font(painter, "heading")
        painter.drawText(5, 5, 30, 30, Qt.AlignCenter, self.client_id[0].upper())


class SectionWidget(QWidget):
    """Widget for a collapsible section (Pinned, Group, All Clients)."""

    def __init__(self, title: str, color: str | None = None, parent=None):
        """Initialize section widget.

        Args:
            title: Section title
            color: Header color (hex), or None to use theme default
            parent: Parent widget
        """
        super().__init__(parent)
        self.title = title
        # Use theme border color as default if no color specified
        if color is None:
            theme = get_theme_manager().get_current_theme()
            color = theme.border
        self.color = color

        # Create layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(4)

        # Header
        header = QLabel(title)
        theme = get_theme_manager().get_current_theme()
        header.setStyleSheet(f"""
            QLabel {{
                background-color: {color};
                color: {theme.on_accent};
                padding: 6px 8px;
                {font_css('body', bold=True)}
            }}
        """)
        layout.addWidget(header)

        # Container for client cards
        self.cards_layout = QVBoxLayout()
        self.cards_layout.setSpacing(4)
        self.cards_layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(self.cards_layout)

    def add_card(self, card: ClientCard):
        """Add client card to section.

        Args:
            card: ClientCard widget
        """
        self.cards_layout.addWidget(card)

    def clear_cards(self):
        """Remove all client cards from section."""
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def card_count(self) -> int:
        """Get number of cards in section.

        Returns:
            Number of cards
        """
        return self.cards_layout.count()


class ClientSidebar(QWidget):
    """Main sidebar widget for client navigation and management.

    Features:
    - Collapsible: 250px (expanded) ↔ 40px (collapsed)
    - Sections: Pinned, Custom Groups, All Clients
    - Header: Refresh + Manage Groups buttons
    - Context menu: Pin, Edit, Move to Group, Delete
    - Track all ClientCard instances for active state highlighting

    Signals:
        client_selected: Emitted when client is selected (client_id: str)
        refresh_requested: Emitted when manual refresh requested
    """

    client_selected = Signal(str)  # client_id
    refresh_requested = Signal()

    EXPANDED_WIDTH = 250
    COLLAPSED_WIDTH = 40
    ANIMATION_DURATION = 200  # milliseconds

    # Class variable for testing - set to False to disable async loading in tests
    def __init__(
        self,
        profile_manager: ProfileManager,
        groups_manager: GroupsManager,
        parent=None
    ):
        """Initialize ClientSidebar.

        Args:
            profile_manager: ProfileManager instance
            groups_manager: GroupsManager instance
            parent: Parent widget
        """
        super().__init__(parent)
        self.profile_manager = profile_manager
        self.groups_manager = groups_manager
        self.is_expanded = True
        self.active_client_id = None
        self._refresh_workers = set()  # keeps in-flight refresh Workers alive

        # Track all ClientCard instances (for highlighting across sections)
        self.client_cards: dict[str, list[ClientCard]] = {}

        self.setFixedWidth(self.EXPANDED_WIDTH)

        # Load expanded state from settings
        settings = QSettings("ShopifyTool", "ClientSidebar")
        self.is_expanded = settings.value("expanded", True, type=bool)

        self._setup_ui()
        self.refresh()

        # Connect to theme changes
        theme_manager = get_theme_manager()
        theme_manager.theme_changed.connect(self._update_styles)

        # Apply initial styles
        self._update_styles()

        # Apply initial state without animation
        if not self.is_expanded:
            self.setFixedWidth(self.COLLAPSED_WIDTH)

    def _setup_ui(self):
        """Create sidebar layout."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header (always visible)
        self._create_header(main_layout)

        # Scroll area for sections (hidden when collapsed)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setFrameShape(QScrollArea.NoFrame)

        # Container for sections
        self.sections_container = QWidget()
        self.sections_layout = QVBoxLayout(self.sections_container)
        self.sections_layout.setContentsMargins(0, 0, 0, 0)
        self.sections_layout.setSpacing(8)
        self.sections_layout.addStretch()

        self.scroll_area.setWidget(self.sections_container)
        main_layout.addWidget(self.scroll_area, 1)

        # Collapsed indicator (hidden when expanded)
        self.collapsed_indicator = None

    def _create_header(self, layout: QVBoxLayout):
        """Create sidebar header.

        Args:
            layout: Parent layout to add header to
        """
        self.header_widget = QWidget()
        # Style will be set in _update_styles()
        header_layout = QVBoxLayout(self.header_widget)
        header_layout.setContentsMargins(4, 4, 4, 4)
        header_layout.setSpacing(4)

        # Row 1: Title + Toggle button
        row1 = QHBoxLayout()

        self.title_label = QLabel("Clients")
        # Style will be set in _update_styles()
        row1.addWidget(self.title_label)

        row1.addStretch()

        self.toggle_btn = QPushButton("◀")
        self.toggle_btn.setFixedSize(24, 24)
        self.toggle_btn.setToolTip("Collapse sidebar")
        self.toggle_btn.clicked.connect(self.toggle_expanded)
        row1.addWidget(self.toggle_btn)

        header_layout.addLayout(row1)

        # Row 2: Refresh + Create + Manage Groups buttons
        row2 = QHBoxLayout()

        self.refresh_btn = QPushButton("⟳")
        self.refresh_btn.setFixedSize(30, 24)
        self.refresh_btn.setToolTip("Refresh client list")
        self.refresh_btn.clicked.connect(self.refresh)
        row2.addWidget(self.refresh_btn)

        # NEW: Create button
        self.create_btn = QPushButton("+ Create")
        self.create_btn.setToolTip("Create new client")
        self.create_btn.clicked.connect(self._open_create_client_dialog)
        row2.addWidget(self.create_btn)

        self.manage_groups_btn = QPushButton("Manage Groups")
        self.manage_groups_btn.setToolTip("Create/edit/delete groups")
        self.manage_groups_btn.clicked.connect(self._open_groups_dialog)
        row2.addWidget(self.manage_groups_btn, 1)

        header_layout.addLayout(row2)

        layout.addWidget(self.header_widget)

    def _gather_refresh_data(self) -> dict:
        """All the file-server IO refresh() needs, with zero Qt object
        construction -- safe to run in a background Worker.
        """
        groups_data = self.groups_manager.load_groups()
        special_groups = groups_data.get("special_groups", {})
        custom_groups = self.groups_manager.list_groups()
        all_clients = self.profile_manager.list_clients()

        pinned_client_ids = set()
        card_data = {}
        for client_id in all_clients:
            ui_settings = self.profile_manager.get_ui_settings(client_id)
            if ui_settings.get("is_pinned", False):
                pinned_client_ids.add(client_id)
            card_data[client_id] = self.profile_manager.get_client_config_extended(client_id)

        group_members = {}
        for group in custom_groups:
            group_id = group.get("id")
            group_members[group_id] = self.groups_manager.get_clients_in_group(
                group_id, self.profile_manager
            )

        return {
            "special_groups": special_groups,
            "custom_groups": custom_groups,
            "all_clients": all_clients,
            "pinned_client_ids": pinned_client_ids,
            "group_members": group_members,
            "card_data": card_data,
        }

    def refresh(self):
        """Refresh client list and rebuild sections.

        Data gathering runs off the GUI thread (Worker); section/card widget
        construction stays on the GUI thread (Qt requirement) and happens in
        _apply_refresh_data() once the data is ready.
        """
        self.refresh_btn.setEnabled(False)
        worker = Worker(self._gather_refresh_data)
        worker.signals.result.connect(self._apply_refresh_data)
        worker.signals.error.connect(self._on_refresh_error)
        # Keep a strong reference until the worker finishes -- a bare local
        # var is garbage-collected the instant this method returns, which (in
        # this PySide6 build) destroys the QRunnable's unparented signals
        # object before its queued result reaches the main thread. See
        # MainWindow._client_load_worker for the verified repro. Tracked in a
        # set, not a single slot: a second refresh before this one finishes
        # must not drop the first worker's reference out from under it.
        self._refresh_workers.add(worker)
        worker.signals.finished.connect(lambda: self._refresh_workers.discard(worker))
        QThreadPool.globalInstance().start(worker)

    def _on_refresh_error(self, error):
        _exctype, value, tb = error
        logger.error(f"Sidebar refresh failed: {value}\n{tb}")
        self.refresh_btn.setEnabled(True)
        QMessageBox.warning(self, "Refresh Error", f"Failed to refresh sidebar:\n{value!s}")

    def _apply_refresh_data(self, data: dict):
        """Build section/card widgets from already-fetched data (main thread only)."""
        import time

        theme = get_theme_manager().get_current_theme()

        try:
            overall_start = time.time()
            logger.info("Applying sidebar refresh data")

            self.setUpdatesEnabled(False)

            while self.sections_layout.count() > 1:
                item = self.sections_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            self.client_cards.clear()

            all_clients = data["all_clients"]
            special_groups = data["special_groups"]
            custom_groups = data["custom_groups"]
            clients_in_sections = set()

            # 1. Pinned section
            pinned_config = special_groups.get("pinned", {})
            pinned_section = self._create_pinned_section(all_clients, pinned_config, data)
            if pinned_section.card_count() > 0:
                self.sections_layout.insertWidget(self.sections_layout.count() - 1, pinned_section)
                clients_in_sections.update(self._get_section_client_ids(pinned_section))

            # 2. Custom groups
            for group in custom_groups:
                group_id = group.get("id")
                group_name = group.get("name", "Unknown")
                group_color = group.get("color", theme.accent_blue)
                group_section = self._create_group_section(group_id, group_name, group_color, all_clients, data)
                if group_section.card_count() > 0:
                    self.sections_layout.insertWidget(self.sections_layout.count() - 1, group_section)
                    clients_in_sections.update(self._get_section_client_ids(group_section))

            # 3. All Clients section
            all_config = special_groups.get("all", {})
            remaining_clients = [c for c in all_clients if c not in clients_in_sections]
            if remaining_clients:
                all_section = self._create_all_section(remaining_clients, all_config, data)
                self.sections_layout.insertWidget(self.sections_layout.count() - 1, all_section)

            self.setUpdatesEnabled(True)

            if self.active_client_id:
                self.set_active_client(self.active_client_id)

            overall_elapsed = (time.time() - overall_start) * 1000
            logger.info(
                f"Sidebar refresh applied: {len(all_clients)} clients, "
                f"{len(custom_groups)} groups in {overall_elapsed:.1f}ms"
            )

        except Exception as e:
            self.setUpdatesEnabled(True)
            logger.exception("Failed to apply sidebar refresh data")
            QMessageBox.warning(self, "Refresh Error", f"Failed to refresh sidebar:\n{e!s}")
        finally:
            self.refresh_btn.setEnabled(True)

    def _create_pinned_section(self, all_clients: list[str], config: dict, data: dict) -> SectionWidget:
        """Create Pinned section.

        Args:
            all_clients: List of all client IDs
            config: Pinned section config
            data: Pre-fetched data from _gather_refresh_data()

        Returns:
            SectionWidget with pinned clients
        """
        theme = get_theme_manager().get_current_theme()
        section = SectionWidget(
            config.get("name", "Pinned"),
            config.get("color", theme.accent_orange)
        )

        for client_id in all_clients:
            if client_id in data["pinned_client_ids"]:
                card = self._create_client_card(client_id, data)
                section.add_card(card)

        return section

    def _create_group_section(
        self,
        group_id: str,
        group_name: str,
        group_color: str,
        all_clients: list[str],
        data: dict,
    ) -> SectionWidget:
        """Create custom group section.

        Args:
            group_id: Group UUID
            group_name: Group display name
            group_color: Group color (hex)
            all_clients: List of all client IDs
            data: Pre-fetched data from _gather_refresh_data()

        Returns:
            SectionWidget with group clients
        """
        section = SectionWidget(group_name, group_color)

        clients_in_group = data["group_members"].get(group_id, [])

        for client_id in clients_in_group:
            if client_id in all_clients:
                card = self._create_client_card(client_id, data)
                section.add_card(card)

        return section

    def _create_all_section(self, clients: list[str], config: dict, data: dict) -> SectionWidget:
        """Create All Clients section.

        Args:
            clients: List of client IDs to include
            config: All section config
            data: Pre-fetched data from _gather_refresh_data()

        Returns:
            SectionWidget with all clients
        """
        # Use theme border color as default for "All Clients" section
        theme = get_theme_manager().get_current_theme()
        default_color = theme.border

        section = SectionWidget(
            config.get("name", "All Clients"),
            config.get("color", default_color)
        )

        for client_id in clients:
            card = self._create_client_card(client_id, data)
            section.add_card(card)

        return section

    def _create_client_card(self, client_id: str, data: dict) -> ClientCard:
        """Create ClientCard for a client.

        Args:
            client_id: Client ID
            data: Pre-fetched data from _gather_refresh_data()

        Returns:
            ClientCard instance
        """
        config = data["card_data"][client_id]

        client_name = config.get("client_name", f"CLIENT_{client_id}")
        metadata = config.get("metadata", {})
        ui_settings = config.get("ui_settings", {})

        is_active = (client_id == self.active_client_id)

        card = ClientCard(
            client_id=client_id,
            client_name=client_name,
            metadata=metadata,
            ui_settings=ui_settings,
            is_active=is_active
        )

        # Connect signals
        card.client_selected.connect(self.client_selected.emit)
        card.context_menu_requested.connect(self._show_context_menu)

        # Track card
        if client_id not in self.client_cards:
            self.client_cards[client_id] = []
        self.client_cards[client_id].append(card)

        return card

    def _get_section_client_ids(self, section: SectionWidget) -> list[str]:
        """Get list of client IDs in a section.

        Args:
            section: SectionWidget

        Returns:
            List of client IDs
        """
        client_ids = []
        for i in range(section.cards_layout.count()):
            widget = section.cards_layout.itemAt(i).widget()
            if isinstance(widget, ClientCard):
                client_ids.append(widget.client_id)
        return client_ids

    def set_active_client(self, client_id: str):
        """Set active client and highlight cards.

        Args:
            client_id: Client ID to set as active
        """
        # Update collapsed indicator if collapsed
        if not self.is_expanded and self.collapsed_indicator:
            theme = get_theme_manager().get_current_theme()
            self.collapsed_indicator.deleteLater()
            config = self.profile_manager.get_client_config_extended(client_id)
            ui_settings = config.get("ui_settings", {})
            color = ui_settings.get("custom_color", theme.accent_green)
            self.collapsed_indicator = CollapsedClientIndicator(client_id, color)
            self.layout().insertWidget(1, self.collapsed_indicator)

        # Deactivate all cards
        for cards_list in self.client_cards.values():
            for card in cards_list:
                card.set_active(False)

        # Activate new client cards
        if client_id in self.client_cards:
            for card in self.client_cards[client_id]:
                card.set_active(True)

        self.active_client_id = client_id
        logger.info(f"Active client set to: {client_id}")

    def toggle_expanded(self):
        """Toggle sidebar expanded/collapsed state with animation."""
        target_width = self.COLLAPSED_WIDTH if self.is_expanded else self.EXPANDED_WIDTH

        # Create animation
        animation = QPropertyAnimation(self, b"maximumWidth")
        animation.setDuration(self.ANIMATION_DURATION)
        animation.setStartValue(self.width())
        animation.setEndValue(target_width)
        animation.setEasingCurve(QEasingCurve.InOutCubic)

        # Update minimum width too
        min_animation = QPropertyAnimation(self, b"minimumWidth")
        min_animation.setDuration(self.ANIMATION_DURATION)
        min_animation.setStartValue(self.width())
        min_animation.setEndValue(target_width)
        min_animation.setEasingCurve(QEasingCurve.InOutCubic)

        # Show/hide sections and header elements
        if self.is_expanded:
            # Collapsing: Hide content BEFORE animation starts
            self._set_collapsed_state(True)
        else:
            # Expanding: Show content AFTER animation completes
            animation.finished.connect(lambda: self._set_collapsed_state(False))

        animation.start()
        min_animation.start()

        # Store references to prevent garbage collection
        self._animation = animation
        self._min_animation = min_animation

        # Toggle state
        self.is_expanded = not self.is_expanded

        # Save state
        settings = QSettings("ShopifyTool", "ClientSidebar")
        settings.setValue("expanded", self.is_expanded)

        # Update toggle button
        self.toggle_btn.setText("▶" if not self.is_expanded else "◀")
        self.toggle_btn.setToolTip("Expand sidebar" if not self.is_expanded else "Collapse sidebar")

    def _set_collapsed_state(self, collapsed: bool):
        """Set UI elements for collapsed/expanded state.

        Args:
            collapsed: True if collapsed, False if expanded
        """
        if collapsed:
            # Hide sections and header elements
            self.scroll_area.hide()
            self.title_label.hide()
            self.refresh_btn.hide()
            self.create_btn.hide()
            self.manage_groups_btn.hide()

            # Show collapsed indicator
            if self.active_client_id:
                theme = get_theme_manager().get_current_theme()
                config = self.profile_manager.get_client_config_extended(self.active_client_id)
                ui_settings = config.get("ui_settings", {})
                color = ui_settings.get("custom_color", theme.accent_green)
                self.collapsed_indicator = CollapsedClientIndicator(self.active_client_id, color)
                self.layout().insertWidget(1, self.collapsed_indicator)
        else:
            # Show sections and header elements
            self.scroll_area.show()
            self.title_label.show()
            self.refresh_btn.show()
            self.create_btn.show()
            self.manage_groups_btn.show()

            # Hide collapsed indicator
            if self.collapsed_indicator:
                self.collapsed_indicator.deleteLater()
                self.collapsed_indicator = None

    def _show_context_menu(self, client_id: str, position: QPoint):
        """Show context menu for client.

        Args:
            client_id: Client ID
            position: Global position for menu
        """
        menu = QMenu(self)

        # Get current settings
        ui_settings = self.profile_manager.get_ui_settings(client_id)
        is_pinned = ui_settings.get("is_pinned", False)

        # Pin/Unpin action
        pin_action = menu.addAction("Unpin" if is_pinned else "Pin to Top")
        pin_action.triggered.connect(lambda: self._toggle_pin(client_id))

        # Edit action
        edit_action = menu.addAction("Edit Settings...")
        edit_action.triggered.connect(lambda: self._edit_client(client_id))

        # Move to Group submenu
        move_menu = menu.addMenu("Move to Group")
        move_menu.addAction("(No group)").triggered.connect(
            lambda: self._move_to_group(client_id, None)
        )

        groups = self.groups_manager.list_groups()
        for group in groups:
            group_id = group.get("id")
            group_name = group.get("name", "Unknown")
            move_menu.addAction(group_name).triggered.connect(
                lambda checked, gid=group_id: self._move_to_group(client_id, gid)
            )

        menu.addSeparator()

        # Delete action
        delete_action = menu.addAction("Delete Client...")
        delete_action.triggered.connect(lambda: self._delete_client(client_id))

        menu.exec(position)

    def _toggle_pin(self, client_id: str):
        """Toggle pin status for client.

        Args:
            client_id: Client ID
        """
        try:
            ui_settings = self.profile_manager.get_ui_settings(client_id)
            new_pin_state = not ui_settings.get("is_pinned", False)

            self.profile_manager.update_ui_settings(client_id, {"is_pinned": new_pin_state})

            logger.info(f"Toggled pin for CLIENT_{client_id}: {new_pin_state}")
            self.refresh()

        except Exception as e:
            logger.exception("Failed to toggle pin")
            QMessageBox.warning(self, "Error", f"Failed to toggle pin:\n{e!s}")

    def _edit_client(self, client_id: str):
        """Open edit dialog for client.

        Args:
            client_id: Client ID
        """
        dialog = ClientSettingsDialog(
            client_id=client_id,
            profile_manager=self.profile_manager,
            groups_manager=self.groups_manager,
            parent=self
        )

        if dialog.exec():
            # Refresh sidebar after changes
            self.refresh()

    def _move_to_group(self, client_id: str, group_id: str | None):
        """Move client to a different group.

        Args:
            client_id: Client ID
            group_id: Group UUID or None for no group
        """
        try:
            self.profile_manager.update_ui_settings(client_id, {"group_id": group_id})

            group_name = "No group" if group_id is None else "group"
            logger.info(f"Moved CLIENT_{client_id} to {group_name}")
            self.refresh()

        except Exception as e:
            logger.exception("Failed to move client to group")
            QMessageBox.warning(self, "Error", f"Failed to move client:\n{e!s}")

    def _delete_client(self, client_id: str):
        """Delete client after confirmation.

        Args:
            client_id: Client ID
        """
        reply = QMessageBox.question(
            self,
            "Delete Client",
            f"Delete CLIENT_{client_id}?\n\n"
            f"This will remove all configuration and session data.\n"
            f"This action cannot be undone!",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            try:
                # Delete client (would need to be implemented in ProfileManager)
                QMessageBox.information(
                    self,
                    "Not Implemented",
                    "Client deletion is not yet implemented.\n"
                    "Please manually delete the client directory on the server."
                )

            except Exception as e:
                logger.exception("Failed to delete client")
                QMessageBox.critical(self, "Error", f"Failed to delete client:\n{e!s}")

    def _open_groups_dialog(self):
        """Open groups management dialog."""
        dialog = GroupsManagementDialog(
            groups_manager=self.groups_manager,
            profile_manager=self.profile_manager,
            parent=self
        )

        if dialog.exec():
            # Refresh sidebar after changes
            self.refresh()

    def _open_create_client_dialog(self):
        """Open dialog for creating new client."""
        dialog = ClientCreationDialog(
            profile_manager=self.profile_manager,
            groups_manager=self.groups_manager,
            parent=self
        )

        if dialog.exec():
            # Get the created client ID
            created_client_id = dialog.client_id_input.text().strip().upper()

            # Refresh sidebar to show new client
            self.refresh()

            # Set as active and highlight
            self.set_active_client(created_client_id)

            # Emit signal so main window can switch to it
            self.client_selected.emit(created_client_id)

            logger.info(f"Created and selected new client: CLIENT_{created_client_id}")

    def _update_styles(self):
        """Update sidebar styles based on current theme."""
        theme = get_theme_manager().get_current_theme()
        is_dark = get_theme_manager().is_dark_theme()
        button_hover = theme.button_hover_dark if is_dark else theme.button_hover_light

        # Update header widget background
        if hasattr(self, 'header_widget'):
            self.header_widget.setStyleSheet(f"background-color: {theme.background_elevated};")

        # Update title label
        if hasattr(self, 'title_label'):
            self.title_label.setStyleSheet(f"{font_css('label')} color: {theme.text};")

        # Update header buttons with explicit theme-aware styling
        button_style = f"""
            QPushButton {{
                background-color: {theme.accent_blue};
                color: {theme.on_accent};
                border: 1px solid {theme.border};
                border-radius: 6px;
                padding: 4px 8px;
                {font_css('body')}
            }}
            QPushButton:hover {{
                background-color: {button_hover};
            }}
            QPushButton:pressed {{
                background-color: {theme.accent_blue};
            }}
        """

        if hasattr(self, 'create_btn'):
            self.create_btn.setStyleSheet(button_style)

        if hasattr(self, 'manage_groups_btn'):
            self.manage_groups_btn.setStyleSheet(button_style)
