"""Memory viewer widget — hex dump with read/write via OpenOCD."""

import struct
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QGroupBox, QCheckBox, QSpinBox, QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSignal, QThread, QTimer
from PyQt5.QtGui import QFont, QColor

from openocd_client import SyncClient
from mcu_config import DEFAULT_FLASH_BASE

_COLS_PER_ROW = 16


class MemReadWorker(QThread):
    data_ready = pyqtSignal(int, bytes)   # (start_addr, raw_bytes)
    log = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, host, port, address, size, parent=None):
        super().__init__(parent)
        self._host = host
        self._port = port
        self._address = address
        self._size = size

    def run(self):
        words = (self._size + 3) // 4
        try:
            with SyncClient(self._host, self._port) as client:
                raw_bytes = bytearray()
                # Read in chunks of 64 words to avoid too-long output lines
                chunk_words = 64
                addr = self._address
                remaining = words
                while remaining > 0:
                    n = min(chunk_words, remaining)
                    cmd = f"mdw 0x{addr:08x} {n}"
                    resp = client.send(cmd)
                    chunk = self._parse_mdw(resp)
                    raw_bytes.extend(chunk)
                    addr += n * 4
                    remaining -= n
                self.data_ready.emit(self._address, bytes(raw_bytes[: self._size]))
        except Exception as e:
            self.error.emit(str(e))

    def _parse_mdw(self, text: str) -> bytes:
        """Parse OpenOCD mdw output into raw bytes (little-endian words)."""
        result = bytearray()
        for line in text.splitlines():
            parts = line.split(":")
            if len(parts) < 2:
                continue
            hex_parts = parts[1].split()
            for h in hex_parts:
                try:
                    word = int(h, 16)
                    result.extend(struct.pack("<I", word))
                except ValueError:
                    pass
        return bytes(result)


class MemWriteWorker(QThread):
    log = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(self, host, port, address, value_word, parent=None):
        super().__init__(parent)
        self._host = host
        self._port = port
        self._address = address
        self._value = value_word

    def run(self):
        try:
            with SyncClient(self._host, self._port) as client:
                cmd = f"mww 0x{self._address:08x} 0x{self._value:08x}"
                resp = client.send(cmd)
                if resp:
                    self.log.emit(resp)
                self.finished.emit(True, "Write OK")
        except Exception as e:
            self.finished.emit(False, str(e))


class MemoryViewerWidget(QWidget):
    sig_log = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._host = "localhost"
        self._port = 4444
        self._current_addr = DEFAULT_FLASH_BASE
        self._current_data = b""
        self._read_worker = None
        self._write_worker = None
        self._auto_timer = QTimer(self)
        self._auto_timer.timeout.connect(self._do_read)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Controls
        ctrl_grp = QGroupBox("Read Memory")
        ctrl_form = QFormLayout(ctrl_grp)
        ctrl_form.setSpacing(4)

        addr_row = QHBoxLayout()
        self._addr_edit = QLineEdit(hex(DEFAULT_FLASH_BASE))
        addr_row.addWidget(self._addr_edit)
        ctrl_form.addRow("Address:", addr_row)

        size_row = QHBoxLayout()
        self._size_edit = QLineEdit("256")
        self._size_edit.setToolTip("Number of bytes to read")
        size_row.addWidget(self._size_edit)
        ctrl_form.addRow("Size (bytes):", size_row)

        btn_row = QHBoxLayout()
        self._btn_read = QPushButton("Read")
        self._btn_read.clicked.connect(self._do_read)
        btn_row.addWidget(self._btn_read)

        self._btn_refresh = QPushButton("Refresh")
        self._btn_refresh.clicked.connect(self._do_read)
        btn_row.addWidget(self._btn_refresh)

        self._auto_check = QCheckBox("Auto-refresh")
        self._auto_check.toggled.connect(self._toggle_auto)
        btn_row.addWidget(self._auto_check)

        self._auto_spin = QSpinBox()
        self._auto_spin.setRange(500, 60000)
        self._auto_spin.setValue(2000)
        self._auto_spin.setSuffix(" ms")
        self._auto_spin.setEnabled(False)
        btn_row.addWidget(self._auto_spin)
        ctrl_form.addRow("", btn_row)
        layout.addWidget(ctrl_grp)

        # Hex table
        self._table = QTableWidget()
        mono = QFont("Monospace", 9)
        self._table.setFont(mono)
        self._table.setColumnCount(_COLS_PER_ROW + 2)   # addr + 16 bytes + ascii
        headers = ["Address"] + [f"{i:02X}" for i in range(_COLS_PER_ROW)] + ["ASCII"]
        self._table.setHorizontalHeaderLabels(headers)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        for c in range(1, _COLS_PER_ROW + 1):
            self._table.horizontalHeader().setSectionResizeMode(c, QHeaderView.Fixed)
            self._table.setColumnWidth(c, 28)
        self._table.horizontalHeader().setSectionResizeMode(_COLS_PER_ROW + 1, QHeaderView.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.cellChanged.connect(self._on_cell_changed)
        layout.addWidget(self._table)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_connection(self, host: str, port: int):
        self._host = host
        self._port = port

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _do_read(self):
        if self._read_worker and self._read_worker.isRunning():
            return
        try:
            addr = int(self._addr_edit.text().strip(), 0)
            size = int(self._size_edit.text().strip(), 0)
        except ValueError:
            self.sig_log.emit("[ERROR] Invalid address or size.")
            return
        self._current_addr = addr
        self._btn_read.setEnabled(False)
        self._read_worker = MemReadWorker(self._host, self._port, addr, size)
        self._read_worker.data_ready.connect(self._populate_table)
        self._read_worker.error.connect(self._on_read_error)
        self._read_worker.start()

    def _on_read_error(self, msg: str):
        self.sig_log.emit(f"[ERROR] Memory read failed: {msg}")
        self._btn_read.setEnabled(True)

    def _populate_table(self, start_addr: int, data: bytes):
        self._current_data = data
        self._btn_read.setEnabled(True)
        rows = (len(data) + _COLS_PER_ROW - 1) // _COLS_PER_ROW

        # Block signals while repopulating
        self._table.blockSignals(True)
        self._table.setRowCount(rows)
        for row in range(rows):
            offset = row * _COLS_PER_ROW
            row_bytes = data[offset: offset + _COLS_PER_ROW]
            addr = start_addr + offset

            # Address column
            addr_item = QTableWidgetItem(f"0x{addr:08X}")
            addr_item.setFlags(Qt.ItemIsEnabled)
            addr_item.setForeground(QColor("#88aaff"))
            self._table.setItem(row, 0, addr_item)

            # Byte columns
            ascii_str = ""
            for col in range(_COLS_PER_ROW):
                if col < len(row_bytes):
                    b = row_bytes[col]
                    item = QTableWidgetItem(f"{b:02X}")
                    item.setTextAlignment(Qt.AlignCenter)
                    # Store actual byte offset for write-back
                    item.setData(Qt.UserRole, addr + col)
                    self._table.setItem(row, col + 1, item)
                    ascii_str += chr(b) if 32 <= b < 127 else "."
                else:
                    self._table.setItem(row, col + 1, QTableWidgetItem(""))
            # ASCII column
            ascii_item = QTableWidgetItem(ascii_str)
            ascii_item.setFlags(Qt.ItemIsEnabled)
            ascii_item.setForeground(QColor("#88dd88"))
            self._table.setItem(row, _COLS_PER_ROW + 1, ascii_item)
        self._table.blockSignals(False)

    def _on_cell_changed(self, row: int, col: int):
        if col == 0 or col == _COLS_PER_ROW + 1:
            return
        item = self._table.item(row, col)
        if not item:
            return
        byte_addr = item.data(Qt.UserRole)
        if byte_addr is None:
            return
        try:
            new_byte = int(item.text().strip(), 16) & 0xFF
        except ValueError:
            return
        # Align to word boundary and write 32-bit word
        word_addr = byte_addr & ~3
        byte_offset_in_word = byte_addr - word_addr
        # Read surrounding bytes from current data if available
        data_offset = byte_addr - self._current_addr
        raw = bytearray(self._current_data[
            (data_offset & ~3): (data_offset & ~3) + 4
        ])
        if len(raw) < 4:
            raw = bytearray(4)
        raw[byte_offset_in_word] = new_byte
        word_val = struct.unpack("<I", bytes(raw[:4]))[0]

        self._write_worker = MemWriteWorker(
            self._host, self._port, word_addr, word_val
        )
        self._write_worker.log.connect(self.sig_log)
        self._write_worker.finished.connect(
            lambda ok, msg: self.sig_log.emit(
                f"[INFO] Write 0x{word_addr:08X}: {msg}" if ok
                else f"[ERROR] Write failed: {msg}"
            )
        )
        self._write_worker.start()

    def _toggle_auto(self, checked: bool):
        self._auto_spin.setEnabled(checked)
        if checked:
            self._auto_timer.start(self._auto_spin.value())
        else:
            self._auto_timer.stop()
