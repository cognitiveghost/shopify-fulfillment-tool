"""A one-line label that elides instead of growing.

A word-wrapped QLabel breaks only at spaces, so a UNC session path's minimum
width is the whole path -- wide enough to push a Tools card past the
viewport. This label asks for no width at all and elides the middle of its
text to whatever width it is given, keeping both the share and the file name
visible. The full string is always the tooltip.
"""

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtWidgets import QLabel, QSizePolicy


class ElidedLabel(QLabel):
    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(parent)
        self._full = ""
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setText(text)

    def setText(self, text: str) -> None:
        self._full = text
        self.setToolTip(text)
        self._elide()

    def full_text(self) -> str:
        return self._full

    def minimumSizeHint(self) -> QSize:
        return QSize(0, super().minimumSizeHint().height())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._elide()

    def changeEvent(self, event) -> None:
        # A stylesheet that makes the text bold changes its width.
        super().changeEvent(event)
        if event.type() == QEvent.FontChange:
            self._elide()

    def _elide(self) -> None:
        width = self.contentsRect().width()
        shown = (
            self.fontMetrics().elidedText(self._full, Qt.ElideMiddle, width)
            if width > 0
            else self._full
        )
        QLabel.setText(self, shown)
