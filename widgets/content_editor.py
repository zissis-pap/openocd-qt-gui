"""Content Editor widget — read-modify-erase-write flash variables."""

import os
import json
import tempfile
import struct
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QGroupBox, QProgressBar, QSizePolicy,
    QFileDialog, QMessageBox, QSplitter, QComboBox
)
from PyQt5.QtCore import Qt, pyqtSignal, QThread
from PyQt5.QtGui import QFont, QColor

from openocd_client import SyncClient
from mcu_config import DEFAULT_FLASH_BASE

# Re-use helpers from memory_viewer
from widgets.memory_viewer import _parse_mdw, _find_sector


_COL_NUM  = 0
_COL_ADDR = 1
_COL_NAME = 2
_COL_SIZE = 3
_COL_DATA = 4
_NUM_COLS = 5
_HEADERS  = ["#", "Address", "Name", "Size (bytes)", "Data"]

_DATA_FMTS = ("Default", "Hex", "Decimal", "ASCII")

# Qt item data roles
_ROLE_ORIGINAL = Qt.UserRole        # bytes: last value read from flash
_ROLE_MODIFIED = Qt.UserRole + 1    # bytes: current parsed edit (for format switching)

_COLOR_UNCHANGED = QColor("#88aaff")
_COLOR_MODIFIED  = QColor("#66ff66")
_COLOR_PLACEHOLDER = QColor("#888888")


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _format_value(raw: bytes, fmt: str = "Default") -> str:
    """Format raw bytes for the Data column display.

    'Default' — Decimal for 1-2 bytes, Hex for 3-4, ASCII for >4.
    'Hex'     — 0x-prefixed, zero-padded; space-separated dump for >4 bytes.
    'Decimal' — unsigned little-endian integer.
    'ASCII'   — quoted string; '.' substituted for non-printable bytes.
    """
    if fmt == "Default":
        n = len(raw)
        if n <= 2:
            fmt = "Decimal"
        elif n <= 4:
            fmt = "Hex"
        else:
            fmt = "ASCII"

    has_printable = any(0x20 <= b <= 0x7E for b in raw)
    ascii_str = "".join(chr(b) if 0x20 <= b <= 0x7E else "." for b in raw)

    if fmt == "ASCII":
        return f'"{ascii_str}"'

    if fmt == "Decimal":
        if len(raw) <= 8:
            val = int.from_bytes(raw, "little")
            suffix = f'  "{ascii_str}"' if has_printable else ""
            return f"{val}{suffix}"
        return " ".join(str(b) for b in raw)

    # Hex
    if len(raw) <= 4:
        val     = int.from_bytes(raw, "little")
        hex_str = f"0x{val:0{len(raw) * 2}X}"
        suffix  = f'  "{ascii_str}"' if has_printable else ""
        return f"{hex_str}{suffix}"
    if has_printable:
        return f'"{ascii_str}"'
    return " ".join(f"{b:02X}" for b in raw)


def _parse_data(data_str: str, size: int, fmt: str = "Default") -> bytes:
    """Convert a user-entered data string to raw bytes of exactly *size* bytes."""
    s = data_str.strip()

    # Quoted string → treat as ASCII regardless of fmt
    if s.startswith('"') and s.endswith('"') and len(s) >= 2:
        inner = s[1:-1]
        raw = inner.encode("utf-8", errors="replace")
        if len(raw) < size:
            raw = raw + b"\x00" * (size - len(raw))
        return raw[:size]

    if fmt == "ASCII":
        raw = s.encode("utf-8", errors="replace")
        if len(raw) < size:
            raw = raw + b"\x00" * (size - len(raw))
        return raw[:size]

    if not s:
        raise ValueError("Empty data field")

    # Strip trailing ASCII annotation appended by _format_value (e.g. '55  "7"' → '55')
    s_num = s.split('"')[0].strip() or s

    # Integer literal (0x…, decimal)
    try:
        val = int(s_num, 0)
        return val.to_bytes(size, "little")
    except (ValueError, OverflowError):
        pass

    # Space-separated hex bytes
    parts = s_num.split()
    if len(parts) > 1:
        raw = bytes(int(p, 16) for p in parts)
    else:
        p = s_num
        if len(p) % 2:
            p = "0" + p
        raw = bytes.fromhex(p)

    if len(raw) < size:
        raw = raw + b"\x00" * (size - len(raw))
    return raw[:size]


# ---------------------------------------------------------------------------
# Worker threads
# ---------------------------------------------------------------------------

class ContentEditorWorker(QThread):
    log      = pyqtSignal(str)
    progress = pyqtSignal(int)
    finished = pyqtSignal(bool, str)

    def __init__(self, host, port, variables, parent=None):
        """variables: list of (addr: int, name: str, size: int, data: bytes)"""
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
            client.send("reset halt")
            self.log.emit("[INFO] Target reset and halted")

            patch_map: dict[int, int] = {}
            for addr, name, size, data in self._variables:
                for i, b in enumerate(data[:size]):
                    patch_map[addr + i] = b

            if not patch_map:
                self.finished.emit(False, "No bytes to write.")
                return

            info = client.send("flash info 0")

            sectors: dict[int, int] = {}
            for byte_addr in patch_map:
                sec_start, sec_size = _find_sector(info, byte_addr)
                sectors[sec_start] = sec_size

            total = len(sectors)
            done  = 0

            for sec_start, sec_size in sorted(sectors.items()):
                self.log.emit(
                    f"[INFO] Sector 0x{sec_start:08x}  size 0x{sec_size:x} bytes"
                )

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

                for byte_addr, new_byte in patch_map.items():
                    if sec_start <= byte_addr < sec_start + sec_size:
                        raw[byte_addr - sec_start] = new_byte

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

            self.finished.emit(
                True,
                f"Store complete: {len(self._variables)} variable(s) across "
                f"{total} sector(s) updated."
            )


class ReadCurrentWorker(QThread):
    """Read current flash/RAM values; emits raw bytes per variable."""
    value_ready = pyqtSignal(int, bytes)   # (row_index, raw_bytes)
    log         = pyqtSignal(str)
    finished    = pyqtSignal(bool, str)

    def __init__(self, host, port, variables, parent=None):
        """variables: list of (row_idx: int, addr: int, size: int)"""
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
                    self.value_ready.emit(row_idx, bytes(raw[:size]))
            self.finished.emit(True, "Read complete.")
        except Exception as e:
            self.finished.emit(False, str(e))


# ---------------------------------------------------------------------------
# Widget
# ---------------------------------------------------------------------------

class ContentEditorWidget(QWidget):
    sig_log = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._host        = "localhost"
        self._port        = 4444
        self._worker      = None
        self._read_worker = None
        self._setup_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_connection(self, host: str, port: int):
        self._host = host
        self._port = port

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        splitter = QSplitter(Qt.Vertical)
        splitter.setChildrenCollapsible(False)

        # ── Variable table ───────────────────────────────────────────────
        tbl_grp  = QGroupBox("Variables")
        tbl_vbox = QVBoxLayout(tbl_grp)
        tbl_vbox.setSpacing(4)

        # Format selector row
        fmt_row = QHBoxLayout()
        fmt_row.addWidget(QLabel("Data format:"))
        self._fmt_data_combo = QComboBox()
        self._fmt_data_combo.addItems(_DATA_FMTS)
        self._fmt_data_combo.setFixedWidth(90)
        self._fmt_data_combo.currentTextChanged.connect(self._on_data_fmt_changed)
        fmt_row.addWidget(self._fmt_data_combo)
        fmt_row.addStretch()
        tbl_vbox.addLayout(fmt_row)

        # Table
        self._table = QTableWidget(0, _NUM_COLS)
        self._table.setHorizontalHeaderLabels(_HEADERS)
        self._table.setFont(QFont("Monospace", 9))

        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(_COL_NUM,  QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(_COL_ADDR, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(_COL_NAME, QHeaderView.Stretch)
        hdr.setSectionResizeMode(_COL_SIZE, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(_COL_DATA, QHeaderView.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setMinimumHeight(120)
        self._table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._table.cellChanged.connect(self._on_cell_changed)
        tbl_vbox.addWidget(self._table)

        # Button row
        btn_row = QHBoxLayout()
        self._btn_save = QPushButton("Save Set…")
        self._btn_save.setFixedWidth(90)
        self._btn_save.clicked.connect(self._save_set)
        btn_row.addWidget(self._btn_save)

        self._btn_load = QPushButton("Load Set…")
        self._btn_load.setFixedWidth(90)
        self._btn_load.clicked.connect(self._load_set)
        btn_row.addWidget(self._btn_load)

        btn_row.addStretch()

        self._btn_add = QPushButton("Add Row")
        self._btn_add.setFixedWidth(90)
        self._btn_add.clicked.connect(self._add_row)
        btn_row.addWidget(self._btn_add)

        self._btn_remove = QPushButton("Remove Row")
        self._btn_remove.setFixedWidth(100)
        self._btn_remove.clicked.connect(self._remove_row)
        btn_row.addWidget(self._btn_remove)
        tbl_vbox.addLayout(btn_row)

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

        ctrl_row = QHBoxLayout()
        self._btn_read_current = QPushButton("Read Values")
        self._btn_read_current.setFixedHeight(32)
        self._btn_read_current.setToolTip("Read current flash values for all variables")
        self._btn_read_current.clicked.connect(self._do_read_current)
        ctrl_row.addWidget(self._btn_read_current)

        self._btn_store = QPushButton("Store")
        self._btn_store.setFixedHeight(32)
        self._btn_store.setStyleSheet(
            "QPushButton { font-weight: bold; background-color: #2a5a2a; color: #ccffcc; }"
            "QPushButton:disabled { background-color: #333; color: #777; }"
        )
        self._btn_store.clicked.connect(self._do_store)
        ctrl_row.addWidget(self._btn_store)

        self._status_label = QLabel("Ready")
        self._status_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._status_label.setStyleSheet("padding: 0 8px; color: #aaaaaa;")
        ctrl_row.addWidget(self._status_label)
        store_vbox.addLayout(ctrl_row)

        splitter.addWidget(store_grp)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([500, 120])

        layout.addWidget(splitter)

    # ------------------------------------------------------------------
    # Table helpers
    # ------------------------------------------------------------------

    def _make_num_item(self, n: int) -> QTableWidgetItem:
        item = QTableWidgetItem(str(n))
        item.setFlags(Qt.ItemIsEnabled)
        item.setTextAlignment(Qt.AlignCenter)
        item.setForeground(_COLOR_PLACEHOLDER)
        return item

    def _make_data_item(self, raw: bytes) -> QTableWidgetItem:
        """Create an editable Data cell pre-populated with the flash value."""
        fmt  = self._fmt_data_combo.currentText()
        text = _format_value(raw, fmt)
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignCenter)
        item.setForeground(_COLOR_UNCHANGED)
        item.setData(_ROLE_ORIGINAL, raw)
        return item

    def _make_placeholder_item(self, text: str = "—") -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignCenter)
        item.setForeground(_COLOR_PLACEHOLDER)
        return item

    def _add_row(self):
        self._table.blockSignals(True)
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._table.setItem(row, _COL_NUM, self._make_num_item(row + 1))
        for col, text in (
            (_COL_ADDR, hex(DEFAULT_FLASH_BASE)),
            (_COL_NAME, ""),
            (_COL_SIZE, "4"),
        ):
            item = QTableWidgetItem(text)
            item.setTextAlignment(
                Qt.AlignLeft | Qt.AlignVCenter if col == _COL_NAME
                else Qt.AlignCenter
            )
            self._table.setItem(row, col, item)
        self._table.setItem(row, _COL_DATA, self._make_placeholder_item())
        self._table.blockSignals(False)

    def _remove_row(self):
        rows = sorted(
            {idx.row() for idx in self._table.selectedIndexes()},
            reverse=True
        )
        self._table.blockSignals(True)
        for row in rows:
            self._table.removeRow(row)
        self._renumber_rows()
        self._table.blockSignals(False)

    def _renumber_rows(self):
        for row in range(self._table.rowCount()):
            item = self._table.item(row, _COL_NUM)
            if item:
                item.setText(str(row + 1))
            else:
                self._table.setItem(row, _COL_NUM, self._make_num_item(row + 1))

    # ------------------------------------------------------------------
    # Cell change / format handling
    # ------------------------------------------------------------------

    def _on_cell_changed(self, row: int, col: int):
        if col == _COL_DATA:
            self._check_data_modified(row)

    def _check_data_modified(self, row: int):
        """Compare current cell text to original flash value; update colour."""
        item = self._table.item(row, _COL_DATA)
        if not item:
            return
        original = item.data(_ROLE_ORIGINAL)
        if not isinstance(original, (bytes, bytearray)):
            return  # no flash baseline → nothing to compare

        size_item = self._table.item(row, _COL_SIZE)
        if not size_item:
            return
        try:
            size = int(size_item.text().strip(), 0)
            fmt  = self._fmt_data_combo.currentText()
            current_raw = _parse_data(item.text().strip(), size, fmt)
        except Exception:
            return

        self._table.blockSignals(True)
        if current_raw != bytes(original)[:size]:
            item.setForeground(_COLOR_MODIFIED)
            item.setData(_ROLE_MODIFIED, current_raw)
        else:
            item.setForeground(_COLOR_UNCHANGED)
            item.setData(_ROLE_MODIFIED, None)
        self._table.blockSignals(False)

    def _on_data_fmt_changed(self, fmt: str):
        """Reformat all Data cells when the format selector changes."""
        self._table.blockSignals(True)
        for row in range(self._table.rowCount()):
            item = self._table.item(row, _COL_DATA)
            if not item:
                continue
            original = item.data(_ROLE_ORIGINAL)
            if not isinstance(original, (bytes, bytearray)):
                continue
            # Use modified bytes if the cell was edited, else original
            modified = item.data(_ROLE_MODIFIED)
            raw_to_show = modified if isinstance(modified, (bytes, bytearray)) else original
            item.setText(_format_value(bytes(raw_to_show), fmt))
            if isinstance(modified, (bytes, bytearray)) and modified != bytes(original):
                item.setForeground(_COLOR_MODIFIED)
            else:
                item.setForeground(_COLOR_UNCHANGED)
        self._table.blockSignals(False)

    # ------------------------------------------------------------------
    # Flash read
    # ------------------------------------------------------------------

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
                self._table.setItem(row, _COL_DATA,
                                    self._make_placeholder_item("err"))
                continue
            specs.append((row, addr, size))
            self._table.setItem(row, _COL_DATA,
                                self._make_placeholder_item("…"))

        if not specs:
            self.sig_log.emit("[WARN] No valid variables to read.")
            return

        self._btn_read_current.setEnabled(False)
        self._read_worker = ReadCurrentWorker(
            self._host, self._port, specs, parent=self
        )
        self._read_worker.log.connect(self.sig_log)
        self._read_worker.value_ready.connect(self._on_value_ready)
        self._read_worker.finished.connect(self._on_read_finished)
        self._read_worker.start()

    def _on_value_ready(self, row: int, raw: bytes):
        self._table.setItem(row, _COL_DATA, self._make_data_item(raw))

    def _on_read_finished(self, ok: bool, msg: str):
        self._btn_read_current.setEnabled(True)
        if not ok:
            self.sig_log.emit(f"[ERROR] Read values failed: {msg}")

    # ------------------------------------------------------------------
    # Save / Load
    # ------------------------------------------------------------------

    def _cell_text(self, row: int, col: int) -> str:
        item = self._table.item(row, col)
        return item.text() if item else ""

    def _collect_rows(self) -> list:
        rows = []
        for row in range(self._table.rowCount()):
            rows.append({
                "address": self._cell_text(row, _COL_ADDR),
                "name":    self._cell_text(row, _COL_NAME),
                "size":    self._cell_text(row, _COL_SIZE),
                "data":    self._cell_text(row, _COL_DATA),
            })
        return rows

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

        self._table.blockSignals(True)
        self._table.setRowCount(0)
        for n, entry in enumerate(rows, start=1):
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, _COL_NUM, self._make_num_item(n))
            for col, key in (
                (_COL_ADDR, "address"),
                (_COL_NAME, "name"),
                (_COL_SIZE, "size"),
            ):
                text = str(entry.get(key, ""))
                item = QTableWidgetItem(text)
                item.setTextAlignment(
                    Qt.AlignLeft | Qt.AlignVCenter if col == _COL_NAME
                    else Qt.AlignCenter
                )
                self._table.setItem(row, col, item)
            self._table.setItem(row, _COL_DATA, self._make_placeholder_item())
        self._table.blockSignals(False)

        self.sig_log.emit(f"[INFO] Loaded {len(rows)} variable(s) from {path}")
        self._do_read_current()   # populate Data with current flash contents

    # ------------------------------------------------------------------
    # Store
    # ------------------------------------------------------------------

    def _do_store(self):
        if self._worker and self._worker.isRunning():
            return

        variables = []
        errors    = []
        fmt       = self._fmt_data_combo.currentText()

        for row in range(self._table.rowCount()):
            addr_item = self._table.item(row, _COL_ADDR)
            name_item = self._table.item(row, _COL_NAME)
            size_item = self._table.item(row, _COL_SIZE)
            data_item = self._table.item(row, _COL_DATA)

            if not all([addr_item, size_item, data_item]):
                errors.append(f"Row {row + 1}: missing fields")
                continue

            addr_str = addr_item.text().strip()
            name_str = (name_item.text().strip() if name_item else "") or f"var_{row + 1}"
            size_str = size_item.text().strip()
            data_str = data_item.text().strip()

            if data_str in ("—", "…", "err", ""):
                errors.append(f"Row {row + 1}: no data value (read flash first)")
                continue

            # Skip rows that have a flash baseline but are unchanged (blue cells)
            original = data_item.data(_ROLE_ORIGINAL)
            modified = data_item.data(_ROLE_MODIFIED)
            if isinstance(original, (bytes, bytearray)) and not isinstance(modified, (bytes, bytearray)):
                continue  # value matches flash — nothing to write

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
                data = _parse_data(data_str, size, fmt)
            except Exception as e:
                errors.append(f"Row {row + 1}: invalid data — {e}")
                continue

            variables.append((addr, name_str, size, data))

        if errors:
            msg = "  ".join(errors)
            self.sig_log.emit(f"[ERROR] {msg}")
            self._status_label.setText("Validation failed — see log")
            self._status_label.setStyleSheet("padding: 0 8px; color: #ff6666;")
            return

        if not variables:
            self.sig_log.emit("[WARN] No modified variables to write. Edit a value (green) before storing.")
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
            self._do_read_current()   # re-read to confirm write and clear green
        else:
            self.sig_log.emit(f"[ERROR] {msg}")
            self._status_label.setText(f"Failed: {msg}")
            self._status_label.setStyleSheet("padding: 0 8px; color: #ff6666;")
