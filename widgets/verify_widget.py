"""Verify widget — side-by-side flash vs firmware comparison."""

import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QProgressBar, QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSignal, QThread
from PyQt5.QtGui import QFont, QColor

from openocd_client import SyncClient
from widgets.memory_viewer import _parse_mdw

_GREEN = QColor("#1e5c1e")
_AMBER = QColor("#6b4b00")

# Column layout:
#  0       : Address
#  1-16    : Flash hex bytes
#  17      : Flash ASCII
#  18-33   : File hex bytes
#  34      : File ASCII
_COL_ADDR        = 0
_COL_FLASH_START = 1
_COL_FLASH_ASCII = 17
_COL_FILE_START  = 18
_COL_FILE_ASCII  = 34
_TOTAL_COLS      = 35
_BYTES_PER_ROW   = 16


class VerifyWorker(QThread):
    progress   = pyqtSignal(int)
    data_ready = pyqtSignal(bytes)
    error      = pyqtSignal(str)

    def __init__(self, host, port, base_addr, length, parent=None):
        super().__init__(parent)
        self._host = host
        self._port = port
        self._base_addr = base_addr
        self._length = length

    def run(self):
        words = (self._length + 3) // 4
        try:
            with SyncClient(self._host, self._port) as client:
                raw = bytearray()
                chunk = 64
                addr = self._base_addr
                remaining = words
                total = words
                while remaining > 0:
                    n = min(chunk, remaining)
                    resp = client.send(f"mdw 0x{addr:08x} {n}")
                    raw.extend(_parse_mdw(resp))
                    addr += n * 4
                    remaining -= n
                    done = total - remaining
                    self.progress.emit(int(done / total * 100))
            self.data_ready.emit(bytes(raw[: self._length]))
        except Exception as e:
            self.error.emit(str(e))


class VerifyWidget(QWidget):
    sig_log = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._host = "localhost"
        self._port = 4444
        self._worker = None
        self._file_bytes = b""
        self._base_addr = 0
        self._file_path = ""
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self._summary = QLabel("No verification run yet.")
        self._summary.setWordWrap(True)
        layout.addWidget(self._summary)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        # Build table
        self._table = QTableWidget()
        mono = QFont("Monospace", 9)
        self._table.setFont(mono)
        self._table.setColumnCount(_TOTAL_COLS)

        headers = (
            ["Address"]
            + [f"F{i:02X}" for i in range(_BYTES_PER_ROW)]
            + ["Flash ASCII"]
            + [f"B{i:02X}" for i in range(_BYTES_PER_ROW)]
            + ["File ASCII"]
        )
        self._table.setHorizontalHeaderLabels(headers)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(_COL_ADDR, QHeaderView.ResizeToContents)
        for c in range(_COL_FLASH_START, _COL_FLASH_ASCII):
            hdr.setSectionResizeMode(c, QHeaderView.Fixed)
            self._table.setColumnWidth(c, 26)
        hdr.setSectionResizeMode(_COL_FLASH_ASCII, QHeaderView.ResizeToContents)
        for c in range(_COL_FILE_START, _COL_FILE_ASCII):
            hdr.setSectionResizeMode(c, QHeaderView.Fixed)
            self._table.setColumnWidth(c, 26)
        hdr.setSectionResizeMode(_COL_FILE_ASCII, QHeaderView.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self._table)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_connection(self, host: str, port: int):
        self._host = host
        self._port = port

    def start_verify(self, file_path: str, base_addr: int):
        if self._worker and self._worker.isRunning():
            self.sig_log.emit("[WARN] Verify already in progress.")
            return
        if not os.path.isfile(file_path):
            self.sig_log.emit(f"[ERROR] File not found: {file_path}")
            return
        with open(file_path, "rb") as f:
            self._file_bytes = f.read()
        self._base_addr = base_addr
        self._file_path = file_path

        self._progress.setValue(0)
        self._progress.setVisible(True)
        self._summary.setText(f"Reading flash at 0x{base_addr:08X} ({len(self._file_bytes)} bytes)…")
        self._table.setRowCount(0)

        self._worker = VerifyWorker(
            self._host, self._port, base_addr, len(self._file_bytes)
        )
        self._worker.progress.connect(self._progress.setValue)
        self._worker.data_ready.connect(self._on_data_ready)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_data_ready(self, flash_bytes: bytes):
        self._progress.setVisible(False)
        self._populate_table(flash_bytes, self._file_bytes)

    def _on_error(self, msg: str):
        self._progress.setVisible(False)
        self.sig_log.emit(f"[ERROR] Verify read failed: {msg}")
        self._summary.setText(f"[ERROR] {msg}")

    def _populate_table(self, flash_bytes: bytes, file_bytes: bytes):
        length = max(len(flash_bytes), len(file_bytes))
        rows = (length + _BYTES_PER_ROW - 1) // _BYTES_PER_ROW

        match_count = 0
        differ_count = 0

        self._table.blockSignals(True)
        self._table.setRowCount(rows)

        for row in range(rows):
            offset = row * _BYTES_PER_ROW
            addr = self._base_addr + offset

            # Address cell
            addr_item = QTableWidgetItem(f"0x{addr:08X}")
            addr_item.setForeground(QColor("#88aaff"))
            self._table.setItem(row, _COL_ADDR, addr_item)

            flash_ascii = ""
            file_ascii  = ""

            for col in range(_BYTES_PER_ROW):
                idx = offset + col
                fb = flash_bytes[idx] if idx < len(flash_bytes) else None
                bb = file_bytes[idx]  if idx < len(file_bytes)  else None

                matched = (fb == bb)
                if fb is not None and bb is not None:
                    if matched:
                        match_count += 1
                    else:
                        differ_count += 1
                bg = _GREEN if matched else _AMBER

                # Flash byte cell
                if fb is not None:
                    fi = QTableWidgetItem(f"{fb:02X}")
                    fi.setTextAlignment(Qt.AlignCenter)
                    fi.setBackground(bg)
                    self._table.setItem(row, _COL_FLASH_START + col, fi)
                    flash_ascii += chr(fb) if 32 <= fb < 127 else "."
                else:
                    self._table.setItem(row, _COL_FLASH_START + col, QTableWidgetItem(""))
                    flash_ascii += " "

                # File byte cell
                if bb is not None:
                    bi = QTableWidgetItem(f"{bb:02X}")
                    bi.setTextAlignment(Qt.AlignCenter)
                    bi.setBackground(bg)
                    self._table.setItem(row, _COL_FILE_START + col, bi)
                    file_ascii += chr(bb) if 32 <= bb < 127 else "."
                else:
                    self._table.setItem(row, _COL_FILE_START + col, QTableWidgetItem(""))
                    file_ascii += " "

            # ASCII columns
            fa_item = QTableWidgetItem(flash_ascii)
            fa_item.setForeground(QColor("#88dd88"))
            self._table.setItem(row, _COL_FLASH_ASCII, fa_item)

            ba_item = QTableWidgetItem(file_ascii)
            ba_item.setForeground(QColor("#88dd88"))
            self._table.setItem(row, _COL_FILE_ASCII, ba_item)

        self._table.blockSignals(False)

        fname = os.path.basename(self._file_path)
        total = match_count + differ_count
        self._summary.setText(
            f"{fname} vs 0x{self._base_addr:08X} — {total} bytes | "
            f"{match_count} match  {differ_count} differ"
        )
        self.sig_log.emit(
            f"[INFO] Verify: {match_count}/{total} bytes match, "
            f"{differ_count} differ."
        )
