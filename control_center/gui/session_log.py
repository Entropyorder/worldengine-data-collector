from PyQt6.QtWidgets import QTextEdit
from PyQt6.QtCore import Qt


class SessionLog(QTextEdit):
    """Read-only scrolling log widget."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumHeight(200)
        self.setAcceptDrops(False)          # outer widget
        self.viewport().setAcceptDrops(False)  # QAbstractScrollArea always enables viewport drops

    def append_line(self, msg: str) -> None:
        self.append(msg)
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())
