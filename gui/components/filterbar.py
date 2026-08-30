"""Search field, removable filter chips, and a result count.

The chip is private and deliberately not shared.theme.StatusChip: a filter
chip is interactive and dismissible, a status chip is a read-only badge.
Sharing them would mean one widget with a `clickable` flag, which is the
abstraction this phase keeps deleting.
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QWidget

from gui.theme_manager import font_css, get_theme_manager, set_button_role


class _FilterChip(QPushButton):
    """`Courier: DPD  x` -- clicking anywhere on it dismisses the filter."""

    def __init__(self, text: str, parent=None) -> None:
        super().__init__(f"{text}  ×", parent)
        set_button_role(self, "ghost")
        self.setStyleSheet(font_css("caption"))


class FilterBar(QWidget):
    """Emits; it does not filter. The caller owns the model."""

    searchChanged = Signal(str)
    filterRemoved = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._apply_theme()
        get_theme_manager().theme_changed.connect(self._apply_theme)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.search_field = QLineEdit(self)
        self.search_field.setPlaceholderText("Search")
        self.search_field.setClearButtonEnabled(True)
        self.search_field.textChanged.connect(self.searchChanged.emit)
        layout.addWidget(self.search_field, 1)

        self._chips: dict[str, _FilterChip] = {}
        self._chip_layout = QHBoxLayout()
        self._chip_layout.setContentsMargins(0, 0, 0, 0)
        self._chip_layout.setSpacing(4)
        layout.addLayout(self._chip_layout)

        self.count_label = QLabel("", self)
        self.count_label.setStyleSheet(font_css("caption"))
        layout.addWidget(self.count_label)

    def _apply_theme(self) -> None:
        theme = get_theme_manager().get_current_theme()
        self.setStyleSheet(f"FilterBar {{ background-color: {theme.surface}; }}")

    def add_filter(self, key: str, text: str) -> None:
        """Add or replace the chip for `key`."""
        if key in self._chips:
            self.remove_filter(key)
        chip = _FilterChip(text, self)
        chip.clicked.connect(lambda _checked=False, k=key: self._dismiss(k))
        self._chips[key] = chip
        self._chip_layout.addWidget(chip)

    def remove_filter(self, key: str) -> None:
        """Drop a chip without emitting. Silent when the key is absent."""
        chip = self._chips.pop(key, None)
        if chip is None:
            return
        self._chip_layout.removeWidget(chip)
        chip.setParent(None)
        chip.deleteLater()

    def _dismiss(self, key: str) -> None:
        self.remove_filter(key)
        self.filterRemoved.emit(key)

    def chip(self, key: str) -> _FilterChip:
        return self._chips[key]

    def filter_keys(self) -> list[str]:
        return list(self._chips)

    def set_count(self, text: str) -> None:
        self.count_label.setText(text)
