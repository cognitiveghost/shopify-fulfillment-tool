"""One input file: where it is, and whether it can be used.

Before this widget, a file's validity was the string "✓" rendered into a
QLabel, and its missing columns lived only in that label's tooltip.
FileHandler.check_files_ready read the check mark back to decide whether
Run Analysis could be enabled. FileSlot holds those facts as data, and the
three states the file can be in as one widget instead of seven.
"""

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from gui.theme_manager import font_css, get_theme_manager
from shared.theme import on_theme_changed

_EMPTY, _LOADED, _INVALID = 0, 1, 2


class FileSlot(QFrame):
    """A file's three states in one widget: empty, loaded, invalid.

    The invalid state replaces the loaded card in place rather than opening
    a message box: a dismissed modal leaves no trace of which file is
    wrong, and the person who has to fix it is looking at this screen.
    """

    changed = Signal()
    chooseFileRequested = Signal()
    chooseFolderRequested = Signal()
    mapColumnsRequested = Signal()
    pathDropped = Signal(str)

    def __init__(self, title: str, hint: str, parent=None) -> None:
        super().__init__(parent)
        self._title = title
        self.path: Path | None = None
        self.is_valid = False
        self.missing_columns: list[str] = []
        self.present_columns: list[str] = []

        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.NoFrame)

        self._stack = QStackedLayout(self)
        self._stack.setContentsMargins(0, 0, 0, 0)
        self._stack.addWidget(self._build_empty(hint))
        self._stack.addWidget(self._build_loaded())
        self._stack.addWidget(self._build_invalid())
        self._apply_theme()
        self._stack.setCurrentIndex(_EMPTY)
        on_theme_changed(self, lambda _t=None: self._apply_theme())

    # ---- the three faces -------------------------------------------------

    def _build_empty(self, hint: str) -> QWidget:
        page = QWidget(self)
        page.setObjectName("FileSlotEmpty")
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignCenter)

        self._hint = QLabel(hint, page)
        self._hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._hint)

        row = QHBoxLayout()
        row.setAlignment(Qt.AlignCenter)
        self.choose_button = QPushButton("Choose file…", page)
        self.choose_button.clicked.connect(self.chooseFileRequested.emit)
        row.addWidget(self.choose_button)
        self.choose_folder_button = QPushButton("Choose folder…", page)
        self.choose_folder_button.clicked.connect(self.chooseFolderRequested.emit)
        row.addWidget(self.choose_folder_button)
        layout.addLayout(row)
        return page

    def _build_loaded(self) -> QWidget:
        page = QWidget(self)
        page.setObjectName("FileSlotLoaded")
        layout = QVBoxLayout(page)

        self._loaded_name = QLabel("", page)
        layout.addWidget(self._loaded_name)
        self._loaded_summary = QLabel("", page)
        layout.addWidget(self._loaded_summary)

        row = QHBoxLayout()
        self.replace_button = QPushButton("Choose a different file", page)
        self.replace_button.clicked.connect(self.chooseFileRequested.emit)
        row.addWidget(self.replace_button)
        row.addStretch()
        layout.addLayout(row)
        return page

    def _build_invalid(self) -> QWidget:
        page = QWidget(self)
        page.setObjectName("FileSlotInvalid")
        layout = QVBoxLayout(page)

        self._error_headline = QLabel("", page)
        layout.addWidget(self._error_headline)
        self._error_body = QLabel("", page)
        self._error_body.setWordWrap(True)
        layout.addWidget(self._error_body)

        row = QHBoxLayout()
        self.map_columns_button = QPushButton("Map columns…", page)
        self.map_columns_button.clicked.connect(self.mapColumnsRequested.emit)
        row.addWidget(self.map_columns_button)
        self.choose_other_button = QPushButton("Choose a different file", page)
        self.choose_other_button.clicked.connect(self.chooseFileRequested.emit)
        row.addWidget(self.choose_other_button)
        row.addStretch()
        layout.addLayout(row)
        return page

    # ---- state -----------------------------------------------------------

    def set_loaded(self, path, summary: str) -> None:
        self.path = Path(path)
        self.is_valid = True
        self.missing_columns = []
        self.present_columns = []
        self._loaded_name.setText(self.path.name)
        self._loaded_summary.setText(summary)
        self._stack.setCurrentIndex(_LOADED)
        self.changed.emit()

    def set_invalid(self, path, missing: list[str], present: list[str]) -> None:
        self.path = Path(path)
        self.is_valid = False
        self.missing_columns = list(missing)
        self.present_columns = list(present)
        self._error_headline.setText("Nothing can be allocated from this file")
        self._error_body.setText(self._body_text())
        self._stack.setCurrentIndex(_INVALID)
        self.changed.emit()

    def clear(self) -> None:
        self.path = None
        self.is_valid = False
        self.missing_columns = []
        self.present_columns = []
        self._stack.setCurrentIndex(_EMPTY)
        self.changed.emit()

    def error_text(self) -> str:
        """Headline plus body, as one string -- what the tests assert on."""
        return f"{self._error_headline.text()}\n{self._error_body.text()}"

    def _body_text(self) -> str:
        name = self.path.name if self.path else "This file"
        missing = ", ".join(self.missing_columns)
        present = ", ".join(self.present_columns)
        return (
            f"{name} has no column mapped to {missing}. "
            f"Analysis needs one to know what is on hand. "
            f"The file's columns are: {present}."
        )

    # ---- drop ------------------------------------------------------------

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        urls = event.mimeData().urls()
        if urls:
            self.pathDropped.emit(urls[0].toLocalFile())
            event.acceptProposedAction()

    # ---- theme -----------------------------------------------------------

    def _apply_theme(self) -> None:
        theme = get_theme_manager().get_current_theme()
        self._hint.setStyleSheet(
            f"color: {theme.text_secondary}; {font_css('caption')}"
        )
        self._loaded_name.setStyleSheet(font_css("body"))
        self._loaded_summary.setStyleSheet(
            f"color: {theme.text_secondary}; {font_css('caption')}"
        )
        self._error_headline.setStyleSheet(
            f"color: {theme.status_danger}; {font_css('label')}"
        )
        self._error_body.setStyleSheet(font_css("caption"))
        self.setStyleSheet(f"""
            QWidget#FileSlotEmpty {{
                border: 2px dashed {theme.border};
                border-radius: {theme.radius_md}px;
                min-height: 96px;
            }}
            QWidget#FileSlotLoaded {{
                border: 1px solid {theme.border};
                border-radius: {theme.radius_md}px;
            }}
            QWidget#FileSlotInvalid {{
                border: 1px solid {theme.status_danger};
                border-radius: {theme.radius_md}px;
                background-color: {theme.status_danger_bg};
            }}
        """)
