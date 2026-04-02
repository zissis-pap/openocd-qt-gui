"""Content Editor widget — read-modify-erase-write flash variables."""

import os
import json
import tempfile
import struct
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QGroupBox, QProgressBar, QSizePolicy,
    QFileDialog, QMessageBox, QSplitter
)
from PyQt5.QtCore import Qt, pyqtSignal, QThread, QSize
from PyQt5.QtGui import QFont, QColor

from openocd_client import SyncClient
from mcu_config import DEFAULT_FLASH_BASE

# Re-use helpers from memory_viewer
from widgets.memory_viewer import _parse_mdw, _find_sector


_COL_ADDR  = 0
_COL_NAME  = 1
_COL_SIZE  = 2
_COL_DATA  = 3
_COL_CURR  = 4
_NUM_COLS  = 5
_HEADERS   = ["Address", "Name", "Size (bytes)", "Data (hex)", "Current Value"]


def _format_value(raw: bytes) -> str:
    """Format raw bytes for display in the Current Value column.

    • 1–4 bytes: zero-padded hex (0xNN…) matching the variable width,
      plus quoted ASCII when at least one byte is printable.
      Data type: little-endian unsigned integer, hex representation.
    • >4 bytes: quoted ASCII string ('.' for non-printable bytes); falls back
      to a space-separated hex byte dump when no byte is printable.
    """
    has_printable = any(0x20 <= b <= 0x7E for b in raw)
    ascii_ = "".join(chr(b) if 0x20 <= b <= 0x7E else "." for b in raw)

    if len(raw) <= 4:
        val     = int.from_bytes(raw, "little")
        hex_str = f"0x{val:0{len(raw) * 2}X}"
        if has_printable:
            return f'{hex_str}  "{ascii_}"'
        return hex_str
    else:
        if has_printable:
            return f'"{ascii_}"'
        return " ".join(f"{b:02X}" for b in raw)


def _format_data(raw: bytes) -> str:
    """Format raw bytes as a zero-padded hex string for the Data column."""
    if len(raw) <= 8:
        val = int.from_bytes(raw, "little")
        return f"0x{val:0{len(raw) * 2}X}"
    return " ".join(f"{b:02X}" for b in raw)


def _parse_data(data_str: str, size: int) -> bytes:
    """Convert a data string to raw bytes of the given size.

    Accepts:
      • Integer literals: "0xDEADBEEF", "12345", "0b1010"  → little-endian
      • Space-separated hex bytes: "DE AD BE EF"
      • Continuous hex bytes: "DEADBEEF"
    """
    s = data_str.strip()
    if not s:
        raise ValueError("Empty data field")

    # Integer literal (0x…, 0b…, 0o…, or plain decimal)
    try:
        val = int(s, 0)
        return val.to_bytes(size, "little")
    except (ValueError, OverflowError):
        pass

    # Space-separated hex bytes
    parts = s.split()
    if len(parts) > 1:
        raw = bytes(int(p, 16) for p in parts)
    else:
        # Continuous hex string e.g. "DEADBEEF"
        if len(s) % 2:
            s = "0" + s
        raw = bytes.fromhex(s)

    if len(raw) < size:
        raw = raw + b"\x00" * (size - len(raw))
    return raw[:size]


class ContentEditorWorker(QThread):
    log      = pyqtSignal(str)
    progress = pyqtSignal(int)
    finished = pyqtSignal(bool, str)

    def __init__(self, host, port, variables, parent=None):
        """
        variables: list of (addr: int, name: str, size: int, data: bytes)
        """
        super().__init__(parent)
        self._host      = host
        self._port      = port
        self._variables = variables

    def run(self):
        try:
            self._do_store()
        except Exception as e:
            self.finished.emit(False, str(e))

    @staticmethod
    def _check_resp(resp: str, context: str):
        if any(k in resp.lower() for k in ("error", "failed", "fault")):
            raise RuntimeError(f"{context} failed: {resp.strip()}")

    def _do_store(self):
        with SyncClient(self._host, self._port) as client:
            client.send("halt")
            self.log.emit("[INFO] Target halted")

            # Build byte-level patch map: {absolute_byte_addr: new_byte_value}
            patch_map: dict[int, int] = {}
            for addr, name, size, data in self._variables:
                for i, b in enumerate(data[:size]):
                    patch_map[addr + i] = b

            if not patch_map:
                self.finished.emit(False, "No bytes to write.")
                return

            # Discover flash layout once
            info = client.send("flash info 0")

            # Collect only the sectors that contain modified bytes
            sectors: dict[int, int] = {}   # {sec_start: sec_size}
            for byte_addr in patch_map:
                sec_start, sec_size = _find_sector(info, byte_addr)
                sectors[sec_start] = sec_size

            total = len(sectors)
            done  = 0

            for sec_start, sec_size in sorted(sectors.items()):
                self.log.emit(
                    f"[INFO] Sector 0x{sec_start:08x}  size 0x{sec_size:x} bytes"
                )

                # ── 1. Read full sector ──────────────────────────────────
                words     = (sec_size + 3) // 4
                raw       = bytearray()
                read_addr = sec_start
                remaining = words
                while remaining > 0:
                    n    = min(64, remaining)
                    resp = client.send(f"mdw 0x{read_addr:08x} {n}")
                    raw.extend(_parse_mdw(resp))
                    read_addr += n * 4
                    remaining -= n

                raw = raw[:sec_size]

                if len(raw) != sec_size:
                    raise RuntimeError(
                        f"Sector read at 0x{sec_start:08x} returned "
                        f"{len(raw)} bytes, expected {sec_size}"
                    )

                # ── 2. Patch only the bytes belonging to this sector ─────
                for byte_addr, new_byte in patch_map.items():
                    if sec_start <= byte_addr < sec_start + sec_size:
                        raw[byte_addr - sec_start] = new_byte

                # ── 3. Write back (erase handled by write_image erase) ───
                self.log.emit(f"[INFO] Programming 0x{sec_start:08x}…")
                with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
                    f.write(bytes(raw))
                    tmp = f.name
                try:
                    resp = client.send(
                        f'flash write_image erase "{tmp}" 0x{sec_start:08x} bin'
                    )
                    if resp:
                        self.log.emit(f"[DBG] {resp.strip()}")
                    self._check_resp(resp, f"flash write_image at 0x{sec_start:08x}")
                finally:
                    os.unlink(tmp)

                done += 1
                self.progress.emit(int(done / total * 100))
                self.log.emit(f"[INFO] Sector 0x{sec_start:08x} done.")

            var_count = len(self._variables)
            self.finished.emit(
                True,
                f"Store complete: {var_count} variable(s) across "
                f"{total} sector(s) updated."
            )


class ReadCurrentWorker(QThread):
    """Read current flash/RAM values for a list of variables."""
    value_ready = pyqtSignal(int, str)   # (row_index, formatted_value)
    log         = pyqtSignal(str)
    finished    = pyqtSignal(bool, str)

    def __init__(self, host, port, variables, parent=None):
        """
        variables: list of (row_idx: int, addr: int, size: int)
        """
        super().__init__(parent)
        self._host      = host
        self._port      = port
        self._variables = variables

    def run(self):
        try:
            with SyncClient(self._host, self._port) as client:
                for row_idx, addr, size in self._variables:
                    words     = (size + 3) // 4
                    raw       = bytearray()
                    read_addr = addr
                    remaining = words
                    while remaining > 0:
                        n    = min(64, remaining)
                        resp = client.send(f"mdw 0x{read_addr:08x} {n}")
                        raw.extend(_parse_mdw(resp))
                        read_addr += n * 4
                        remaining -= n
                    raw = raw[:size]
                    self.value_ready.emit(row_idx, _format_value(bytes(raw)))
            self.finished.emit(True, "Read complete.")
        except Exception as e:
            self.finished.emit(False, str(e))


class ContentEditorWidget(QWidget):
    sig_log = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._host         = "localhost"
        self._port         = 4444
        self._worker       = None
        self._read_worker  = None
        self._setup_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_connection(self, host: str, port: int):
        self._host = host
        self._port = port

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        splitter = QSplitter(Qt.Vertical)
        splitter.setChildrenCollapsible(False)

        # ── Variable table ───────────────────────────────────────────────
        tbl_grp = QGroupBox("Variables")
        tbl_vbox = QVBoxLayout(tbl_grp)
        tbl_vbox.setSpacing(4)

        self._table = QTableWidget(0, _NUM_COLS)
        self._table.setHorizontalHeaderLabels(_HEADERS)
        mono = QFont("Monospace", 9)
        self._table.setFont(mono)

        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(_COL_ADDR, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(_COL_NAME, QHeaderView.Stretch)
        hdr.setSectionResizeMode(_COL_SIZE, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(_COL_DATA, QHeaderView.Stretch)
        hdr.setSectionResizeMode(_COL_CURR, QHeaderView.ResizeToContents)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setMinimumHeight(120)
        self._table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._table.cellChanged.connect(self._on_cell_changed)
        tbl_vbox.addWidget(self._table)

        # Add / Remove / Save / Load row buttons
        row_btn_row = QHBoxLayout()
        self._btn_save = QPushButton("Save Set…")
        self._btn_save.setFixedWidth(90)
        self._btn_save.clicked.connect(self._save_set)
        row_btn_row.addWidget(self._btn_save)

        self._btn_load = QPushButton("Load Set…")
        self._btn_load.setFixedWidth(90)
        self._btn_load.clicked.connect(self._load_set)
        row_btn_row.addWidget(self._btn_load)

        row_btn_row.addStretch()

        self._btn_add = QPushButton("Add Row")
        self._btn_add.setFixedWidth(90)
        self._btn_add.clicked.connect(self._add_row)
        row_btn_row.addWidget(self._btn_add)

        self._btn_remove = QPushButton("Remove Row")
        self._btn_remove.setFixedWidth(100)
        self._btn_remove.clicked.connect(self._remove_row)
        row_btn_row.addWidget(self._btn_remove)
        tbl_vbox.addLayout(row_btn_row)

        splitter.addWidget(tbl_grp)

        # ── Store controls ───────────────────────────────────────────────
        store_grp = QGroupBox("Store to Flash")
        store_grp.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        store_vbox = QVBoxLayout(store_grp)
        store_vbox.setSpacing(6)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(True)
        store_vbox.addWidget(self._progress)

        bottom_row = QHBoxLayout()
        self._btn_read_current = QPushButton("Read Values")
        self._btn_read_current.setFixedHeight(32)
        self._btn_read_current.setToolTip("Read current values from flash for all variables")
        self._btn_read_current.clicked.connect(self._do_read_current)
        bottom_row.addWidget(self._btn_read_current)

        self._btn_store = QPushButton("Store")
        self._btn_store.setFixedHeight(32)
        self._btn_store.setStyleSheet(
            "QPushButton { font-weight: bold; background-color: #2a5a2a; color: #ccffcc; }"
            "QPushButton:disabled { background-color: #333; color: #777; }"
        )
        self._btn_store.clicked.connect(self._do_store)
        bottom_row.addWidget(self._btn_store)

        self._status_label = QLabel("Ready")
        self._status_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._status_label.setStyleSheet("padding: 0 8px; color: #aaaaaa;")
        bottom_row.addWidget(self._status_label)
        store_vbox.addLayout(bottom_row)

        splitter.addWidget(store_grp)

        # Give the table most of the space; store panel gets just enough for its contents
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([500, 120])

        layout.addWidget(splitter)

    # ------------------------------------------------------------------
    # Table helpers
    # ------------------------------------------------------------------

    def _add_row(self):
        row = self._table.rowCount()
        self._table.insertRow(row)
        defaults = [hex(DEFAULT_FLASH_BASE), "", "4", "0x00000000"]
        for col, text in enumerate(defaults):
            item = QTableWidgetItem(text)
            item.setTextAlignment(Qt.AlignCenter if col != _COL_NAME else Qt.AlignLeft | Qt.AlignVCenter)
            self._table.setItem(row, col, item)
        self._table.setItem(row, _COL_CURR, self._make_curr_item("—"))

    def _remove_row(self):
        rows = sorted(
            {idx.row() for idx in self._table.selectedIndexes()},
            reverse=True
        )
        for row in rows:
            self._table.removeRow(row)

    def _on_cell_changed(self, row: int, col: int):
        if col in (_COL_SIZE, _COL_DATA):
            self._reformat_data_cell(row)

    def _reformat_data_cell(self, row: int):
        """Parse Size + Data for the given row and rewrite Data as a
        zero-padded hex string matching the variable width."""
        size_item = self._table.item(row, _COL_SIZE)
        data_item = self._table.item(row, _COL_DATA)
        if not size_item or not data_item:
            return
        try:
            size = int(size_item.text().strip(), 0)
            if size <= 0:
                return
            raw = _parse_data(data_item.text().strip(), size)
        except Exception:
            return   # leave as-is if either field is not yet valid
        formatted = _format_data(raw)
        if formatted == data_item.text():
            return   # already correct — avoid triggering cellChanged again
        self._table.blockSignals(True)
        data_item.setText(formatted)
        self._table.blockSignals(False)

    # ------------------------------------------------------------------
    # Current Value column helpers
    # ------------------------------------------------------------------

    def _make_curr_item(self, text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(Qt.ItemIsEnabled)          # read-only
        item.setTextAlignment(Qt.AlignCenter)
        item.setForeground(QColor("#88aaff"))
        return item

    def _do_read_current(self):
        if self._read_worker and self._read_worker.isRunning():
            return

        specs = []
        for row in range(self._table.rowCount()):
            addr_text = self._cell_text(row, _COL_ADDR)
            size_text = self._cell_text(row, _COL_SIZE)
            try:
                addr = int(addr_text, 0)
                size = int(size_text, 0)
                if size <= 0:
                    raise ValueError
            except ValueError:
                self._table.setItem(row, _COL_CURR, self._make_curr_item("err"))
                continue
            specs.append((row, addr, size))
            self._table.setItem(row, _COL_CURR, self._make_curr_item("…"))

        if not specs:
            self.sig_log.emit("[WARN] No valid variables to read.")
            return

        self._btn_read_current.setEnabled(False)
        self._read_worker = ReadCurrentWorker(self._host, self._port, specs, parent=self)
        self._read_worker.log.connect(self.sig_log)
        self._read_worker.value_ready.connect(
            lambda row, val: self._table.setItem(row, _COL_CURR, self._make_curr_item(val))
        )
        self._read_worker.finished.connect(self._on_read_finished)
        self._read_worker.start()

    def _on_read_finished(self, ok: bool, msg: str):
        self._btn_read_current.setEnabled(True)
        if not ok:
            self.sig_log.emit(f"[ERROR] Read values failed: {msg}")

    # ------------------------------------------------------------------
    # Save / Load variable set
    # ------------------------------------------------------------------

    def _collect_rows(self) -> list:
        """Return table contents as a list of dicts (raw text, no validation)."""
        rows = []
        for row in range(self._table.rowCount()):
            rows.append({
                "address": self._cell_text(row, _COL_ADDR),
                "name":    self._cell_text(row, _COL_NAME),
                "size":    self._cell_text(row, _COL_SIZE),
                "data":    self._cell_text(row, _COL_DATA),
            })
        return rows

    def _cell_text(self, row: int, col: int) -> str:
        item = self._table.item(row, col)
        return item.text() if item else ""

    def _save_set(self):
        if self._table.rowCount() == 0:
            QMessageBox.information(self, "Save Set", "No variables to save.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Variable Set", "",
            "Variable Set (*.varset);;JSON Files (*.json);;All Files (*)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._collect_rows(), f, indent=2)
            self.sig_log.emit(f"[INFO] Variable set saved to {path}")
        except Exception as e:
            QMessageBox.critical(self, "Save Failed", str(e))
            self.sig_log.emit(f"[ERROR] Save failed: {e}")

    def _load_set(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Variable Set", "",
            "Variable Set (*.varset);;JSON Files (*.json);;All Files (*)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                rows = json.load(f)
            if not isinstance(rows, list):
                raise ValueError("Expected a JSON array at the top level.")
        except Exception as e:
            QMessageBox.critical(self, "Load Failed", str(e))
            self.sig_log.emit(f"[ERROR] Load failed: {e}")
            return

        self._table.setRowCount(0)
        for entry in rows:
            row = self._table.rowCount()
            self._table.insertRow(row)
            for col, key in enumerate(("address", "name", "size", "data")):
                text = str(entry.get(key, ""))
                item = QTableWidgetItem(text)
                item.setTextAlignment(
                    Qt.AlignLeft | Qt.AlignVCenter
                    if col == _COL_NAME
                    else Qt.AlignCenter
                )
                self._table.setItem(row, col, item)
            self._table.setItem(row, _COL_CURR, self._make_curr_item("—"))

        for row in range(self._table.rowCount()):
            self._reformat_data_cell(row)

        self.sig_log.emit(
            f"[INFO] Loaded {len(rows)} variable(s) from {path}"
        )

    # ------------------------------------------------------------------
    # Store logic
    # ------------------------------------------------------------------

    def _do_store(self):
        if self._worker and self._worker.isRunning():
            return

        variables = []
        errors    = []

        for row in range(self._table.rowCount()):
            addr_item = self._table.item(row, _COL_ADDR)
            name_item = self._table.item(row, _COL_NAME)
            size_item = self._table.item(row, _COL_SIZE)
            data_item = self._table.item(row, _COL_DATA)

            if not all([addr_item, size_item, data_item]):
                errors.append(f"Row {row + 1}: missing fields")
                continue

            addr_str = addr_item.text().strip()
            name_str = (name_item.text().strip() if name_item else "") or f"var_{row}"
            size_str = size_item.text().strip()
            data_str = data_item.text().strip()

            try:
                addr = int(addr_str, 0)
            except ValueError:
                errors.append(f"Row {row + 1}: invalid address '{addr_str}'")
                continue

            try:
                size = int(size_str, 0)
                if size <= 0:
                    raise ValueError("size must be > 0")
            except ValueError as e:
                errors.append(f"Row {row + 1}: invalid size — {e}")
                continue

            try:
                data = _parse_data(data_str, size)
            except Exception as e:
                errors.append(f"Row {row + 1}: invalid data — {e}")
                continue

            variables.append((addr, name_str, size, data))

        if errors:
            msg = "Validation errors:\n" + "\n".join(errors)
            self.sig_log.emit(f"[ERROR] {msg.replace(chr(10), '  ')}")
            self._status_label.setText("Validation failed — see log")
            self._status_label.setStyleSheet("padding: 0 8px; color: #ff6666;")
            return

        if not variables:
            self.sig_log.emit("[WARN] No variables defined.")
            return

        self._progress.setValue(0)
        self._status_label.setText("Working…")
        self._status_label.setStyleSheet("padding: 0 8px; color: #ffdd55;")
        self._btn_store.setEnabled(False)

        self._worker = ContentEditorWorker(
            self._host, self._port, variables, parent=self
        )
        self._worker.log.connect(self.sig_log)
        self._worker.progress.connect(self._progress.setValue)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_finished(self, ok: bool, msg: str):
        self._btn_store.setEnabled(True)
        self._progress.setValue(100 if ok else 0)
        if ok:
            self.sig_log.emit(f"[INFO] {msg}")
            self._status_label.setText(msg)
            self._status_label.setStyleSheet("padding: 0 8px; color: #66ff66;")
            self._do_read_current()
        else:
            self.sig_log.emit(f"[ERROR] {msg}")
            self._status_label.setText(f"Failed: {msg}")
            self._status_label.setStyleSheet("padding: 0 8px; color: #ff6666;")
