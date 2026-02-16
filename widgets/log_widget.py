"""Scrolling OpenOCD output log widget."""

import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton, QFileDialog
)
from PyQt5.QtGui import QColor, QTextCharFormat, QTextCursor
from PyQt5.QtCore import Qt


class LogWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Toolbar row
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._btn_clear = QPushButton("Clear")
        self._btn_clear.setFixedWidth(70)
        self._btn_clear.clicked.connect(self.clear)
        btn_row.addWidget(self._btn_clear)

        self._btn_save = QPushButton("Save Log")
        self._btn_save.setFixedWidth(80)
        self._btn_save.clicked.connect(self._save_log)
        btn_row.addWidget(self._btn_save)

        layout.addLayout(btn_row)

        # Log text area
        self._text = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setLineWrapMode(QTextEdit.NoWrap)
        font = self._text.font()
        font.setFamily("Monospace")
        font.setPointSize(9)
        self._text.setFont(font)
        layout.addWidget(self._text)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def append_line(self, line: str):
        color = self._classify_color(line)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        cursor = self._text.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(line + "\n", fmt)
        self._text.setTextCursor(cursor)
        self._text.ensureCursorVisible()

    def clear(self):
        self._text.clear()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _classify_color(self, line: str) -> str:
        lower = line.lower()
        if any(k in lower for k in ("error", "err:", "failed", "fail:")):
            return "#ff5555"   # red
        if any(k in lower for k in ("warn", "warning")):
            return "#ffdd55"   # yellow
        if any(k in lower for k in ("info", "debug")):
            return "#aaddff"   # light blue
        return "#e0e0e0"       # default white-ish

    def _save_log(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Log", "", "Text Files (*.txt *.log);;All Files (*)"
        )
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(self._text.toPlainText())
            except Exception as e:
                self.append_line(f"[ERROR] Could not save log: {e}")
