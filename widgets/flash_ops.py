"""Flash operations widget — Halt/Erase/Program/Verify/Reset/Read."""

import os
import tempfile
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog, QProgressBar, QGroupBox,
    QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSignal, QThread

from openocd_client import SyncClient
from mcu_config import DEFAULT_FLASH_BASE


class FlashWorker(QThread):
    progress = pyqtSignal(int)
    log = pyqtSignal(str)
    finished = pyqtSignal(bool, str)   # (success, message)

    def __init__(self, host, port, commands, parent=None):
        super().__init__(parent)
        self._host = host
        self._port = port
        self._commands = commands   # list of (label, cmd_string)

    def run(self):
        total = len(self._commands)
        try:
            with SyncClient(self._host, self._port) as client:
                for i, (label, cmd) in enumerate(self._commands):
                    self.log.emit(f"[>>] {label}: {cmd}")
                    response = client.send(cmd)
                    if response:
                        self.log.emit(response)
                    # check for error keywords
                    if any(k in response.lower() for k in ("error", "failed", "fault")):
                        self.finished.emit(False, f"{label} failed: {response[:200]}")
                        return
                    pct = int((i + 1) / total * 100)
                    self.progress.emit(pct)
            self.finished.emit(True, "Done")
        except Exception as e:
            self.finished.emit(False, str(e))


class FlashOpsWidget(QWidget):
    sig_log = pyqtSignal(str)
    sig_verify_requested = pyqtSignal(str, int)  # (file_path, base_addr)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._host = "localhost"
        self._port = 4444
        self._worker = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # File selection
        file_grp = QGroupBox("Firmware File")
        file_layout = QHBoxLayout(file_grp)
        self._file_edit = QLineEdit()
        self._file_edit.setPlaceholderText("Select .bin/.elf/.hex/.s19 file...")
        file_layout.addWidget(self._file_edit)
        btn_browse = QPushButton("Browse")
        btn_browse.clicked.connect(self._browse_file)
        file_layout.addWidget(btn_browse)
        layout.addWidget(file_grp)

        # Address / options
        addr_grp = QGroupBox("Options")
        form = QFormLayout(addr_grp)
        form.setSpacing(4)
        self._addr_edit = QLineEdit(hex(DEFAULT_FLASH_BASE))
        self._addr_edit.setToolTip("Base address for binary files")
        form.addRow("Base address:", self._addr_edit)
        layout.addWidget(addr_grp)

        # Operation buttons grid
        ops_grp = QGroupBox("Operations")
        grid = QGridLayout(ops_grp)
        grid.setSpacing(6)

        ops = [
            ("Halt",         self._op_halt,       0, 0),
            ("Erase",        self._op_erase,      0, 1),
            ("Program",      self._op_program,    1, 0),
            ("Verify",       self._op_verify,     1, 1),
            ("Reset & Run",  self._op_reset,      2, 0),
            ("Read Flash",   self._op_read,       2, 1),
        ]
        self._op_buttons = []
        for label, slot, row, col in ops:
            btn = QPushButton(label)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.clicked.connect(slot)
            grid.addWidget(btn, row, col)
            self._op_buttons.append(btn)
        layout.addWidget(ops_grp)

        # Read flash options (shown when Read Flash is used)
        read_grp = QGroupBox("Read Flash Options")
        read_form = QFormLayout(read_grp)
        self._read_addr_edit = QLineEdit(hex(DEFAULT_FLASH_BASE))
        read_form.addRow("Start address:", self._read_addr_edit)
        self._read_size_edit = QLineEdit("0x10000")
        read_form.addRow("Size (bytes):", self._read_size_edit)
        layout.addWidget(read_grp)

        # Progress bar
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        layout.addWidget(self._progress)

        layout.addStretch()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_connection(self, host: str, port: int):
        self._host = host
        self._port = port

    # ------------------------------------------------------------------
    # Operation slots
    # ------------------------------------------------------------------

    def _op_halt(self):
        self._run_commands([("Halt", "halt")])

    def _op_erase(self):
        addr = self._addr_edit.text().strip() or hex(DEFAULT_FLASH_BASE)
        cmds = [
            ("Halt", "halt"),
            ("Erase", f"flash erase_address pad {addr} 0x20000"),
        ]
        self._run_commands(cmds)

    def _op_program(self):
        path = self._file_edit.text().strip()
        if not path:
            self.sig_log.emit("[ERROR] No firmware file selected.")
            return
        addr = self._addr_edit.text().strip() or hex(DEFAULT_FLASH_BASE)
        # program command with verify
        cmds = [
            ("Halt", "halt"),
            ("Program", f'program "{path}" {addr} verify'),
        ]
        self._run_commands(cmds)

    def _op_verify(self):
        path = self._file_edit.text().strip()
        if not path:
            self.sig_log.emit("[ERROR] No firmware file selected.")
            return
        try:
            addr = int(self._addr_edit.text().strip(), 0)
        except ValueError:
            addr = DEFAULT_FLASH_BASE
        self.sig_verify_requested.emit(path, addr)

    def _op_reset(self):
        self._run_commands([("Reset & Run", "reset run")])

    def _op_read(self):
        addr = self._read_addr_edit.text().strip() or hex(DEFAULT_FLASH_BASE)
        size = self._read_size_edit.text().strip() or "0x10000"
        out_path, _ = QFileDialog.getSaveFileName(
            self, "Save Flash Image", "flash_dump.bin",
            "Binary Files (*.bin);;All Files (*)"
        )
        if not out_path:
            return
        self._run_commands([
            ("Halt", "halt"),
            ("Read Flash", f'dump_image "{out_path}" {addr} {size}'),
        ])

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Firmware File", "",
            "Firmware Files (*.bin *.elf *.hex *.s19);;All Files (*)"
        )
        if path:
            self._file_edit.setText(path)

    def _run_commands(self, commands):
        if self._worker and self._worker.isRunning():
            self.sig_log.emit("[WARN] An operation is already in progress.")
            return
        self._set_buttons_enabled(False)
        self._progress.setValue(0)
        self._worker = FlashWorker(self._host, self._port, commands)
        self._worker.log.connect(self.sig_log)
        self._worker.progress.connect(self._progress.setValue)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_finished(self, success: bool, message: str):
        self._set_buttons_enabled(True)
        if success:
            self.sig_log.emit(f"[INFO] Operation completed successfully.")
            self._progress.setValue(100)
        else:
            self.sig_log.emit(f"[ERROR] {message}")
            self._progress.setValue(0)

    def _set_buttons_enabled(self, enabled: bool):
        for btn in self._op_buttons:
            btn.setEnabled(enabled)
