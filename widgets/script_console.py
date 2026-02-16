"""TCL script console widget — interactive command input + multi-line editor."""

import os
from collections import deque
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTextEdit, QPlainTextEdit, QLineEdit, QPushButton,
    QToolBar, QAction, QFileDialog, QLabel, QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSignal, QThread
from PyQt5.QtGui import QFont, QColor, QTextCharFormat, QTextCursor, QKeyEvent

from openocd_client import SyncClient

_MAX_HISTORY = 100


class ScriptWorker(QThread):
    line_ready = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(self, host, port, commands, parent=None):
        super().__init__(parent)
        self._host = host
        self._port = port
        self._commands = commands  # list of strings

    def run(self):
        try:
            with SyncClient(self._host, self._port) as client:
                for cmd in self._commands:
                    cmd = cmd.strip()
                    if not cmd or cmd.startswith("#"):
                        continue
                    self.line_ready.emit(f">> {cmd}")
                    resp = client.send(cmd)
                    if resp:
                        self.line_ready.emit(resp)
            self.finished.emit(True, "")
        except Exception as e:
            self.finished.emit(False, str(e))


class HistoryLineEdit(QLineEdit):
    """QLineEdit with up/down arrow command history navigation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._history = deque(maxlen=_MAX_HISTORY)
        self._history_pos = -1
        self._saved_text = ""

    def add_to_history(self, cmd: str):
        if cmd and (not self._history or self._history[-1] != cmd):
            self._history.append(cmd)
        self._history_pos = -1

    def keyPressEvent(self, event: QKeyEvent):
        history_list = list(self._history)
        if event.key() == Qt.Key_Up:
            if self._history_pos == -1:
                self._saved_text = self.text()
            if self._history_pos < len(history_list) - 1:
                self._history_pos += 1
                self.setText(history_list[-(self._history_pos + 1)])
        elif event.key() == Qt.Key_Down:
            if self._history_pos > 0:
                self._history_pos -= 1
                self.setText(history_list[-(self._history_pos + 1)])
            elif self._history_pos == 0:
                self._history_pos = -1
                self.setText(self._saved_text)
        else:
            super().keyPressEvent(event)


class ScriptConsoleWidget(QWidget):
    sig_log = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._host = "localhost"
        self._port = 4444
        self._worker = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        splitter = QSplitter(Qt.Vertical)

        # --- Top half: interactive console ---
        console_widget = QWidget()
        console_layout = QVBoxLayout(console_widget)
        console_layout.setContentsMargins(0, 0, 0, 0)
        console_layout.setSpacing(4)

        console_layout.addWidget(QLabel("<b>Interactive Console</b>"))

        self._output = QTextEdit()
        self._output.setReadOnly(True)
        mono = QFont("Monospace", 9)
        self._output.setFont(mono)
        console_layout.addWidget(self._output)

        input_row = QHBoxLayout()
        self._input = HistoryLineEdit()
        self._input.setPlaceholderText("Enter TCL command...")
        self._input.returnPressed.connect(self._send_command)
        input_row.addWidget(self._input)
        btn_send = QPushButton("Send")
        btn_send.clicked.connect(self._send_command)
        input_row.addWidget(btn_send)
        console_layout.addLayout(input_row)
        splitter.addWidget(console_widget)

        # --- Bottom half: script editor ---
        editor_widget = QWidget()
        editor_layout = QVBoxLayout(editor_widget)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(4)

        editor_label_row = QHBoxLayout()
        editor_label_row.addWidget(QLabel("<b>Script Editor</b>"))
        editor_label_row.addStretch()

        btn_load = QPushButton("Load Script")
        btn_load.clicked.connect(self._load_script)
        editor_label_row.addWidget(btn_load)

        btn_save = QPushButton("Save Script")
        btn_save.clicked.connect(self._save_script)
        editor_label_row.addWidget(btn_save)

        btn_run = QPushButton("Run Script")
        btn_run.setStyleSheet("background-color: #2a5a2a; color: white;")
        btn_run.clicked.connect(self._run_script)
        editor_label_row.addWidget(btn_run)
        editor_layout.addLayout(editor_label_row)

        self._editor = QPlainTextEdit()
        self._editor.setFont(mono)
        self._editor.setPlaceholderText(
            "# Enter multi-line TCL script here\n# Lines starting with # are comments\nhalt\n"
        )
        editor_layout.addWidget(self._editor)
        splitter.addWidget(editor_widget)

        splitter.setSizes([300, 200])
        layout.addWidget(splitter)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_connection(self, host: str, port: int):
        self._host = host
        self._port = port

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _send_command(self):
        cmd = self._input.text().strip()
        if not cmd:
            return
        self._input.add_to_history(cmd)
        self._input.clear()
        self._run_commands([cmd])

    def _run_script(self):
        text = self._editor.toPlainText()
        lines = [l for l in text.splitlines() if l.strip() and not l.strip().startswith("#")]
        if not lines:
            return
        self._run_commands(lines)

    def _run_commands(self, commands):
        if self._worker and self._worker.isRunning():
            self._append_output("[WARN] Already running a script.", "#ffdd55")
            return
        self._worker = ScriptWorker(self._host, self._port, commands)
        self._worker.line_ready.connect(self._on_line)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_line(self, line: str):
        if line.startswith(">>"):
            color = "#88aaff"
        elif any(k in line.lower() for k in ("error", "failed")):
            color = "#ff5555"
        else:
            color = "#e0e0e0"
        self._append_output(line, color)
        self.sig_log.emit(line)

    def _on_finished(self, ok: bool, msg: str):
        if not ok:
            self._append_output(f"[ERROR] {msg}", "#ff5555")
            self.sig_log.emit(f"[ERROR] Script failed: {msg}")

    def _append_output(self, text: str, color: str = "#e0e0e0"):
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        cursor = self._output.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(text + "\n", fmt)
        self._output.setTextCursor(cursor)
        self._output.ensureCursorVisible()

    def _load_script(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Script", "",
            "TCL Scripts (*.tcl);;All Files (*)"
        )
        if path:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self._editor.setPlainText(f.read())
            except Exception as e:
                self.sig_log.emit(f"[ERROR] Could not load script: {e}")

    def _save_script(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Script", "script.tcl",
            "TCL Scripts (*.tcl);;All Files (*)"
        )
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(self._editor.toPlainText())
            except Exception as e:
                self.sig_log.emit(f"[ERROR] Could not save script: {e}")
