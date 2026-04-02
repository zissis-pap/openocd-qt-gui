"""Server control widget — start/stop OpenOCD, configure interface/ports."""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QComboBox, QPushButton, QFileDialog, QSpinBox
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPalette

from mcu_config import INTERFACE_CONFIGS, DEFAULT_INTERFACE, DEFAULT_TELNET_PORT, DEFAULT_TCL_PORT


class StatusDot(QLabel):
    """Small colored dot showing server status."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(14, 14)
        self.set_stopped()

    def set_running(self):
        self.setStyleSheet(
            "background-color: #44cc44; border-radius: 7px; border: 1px solid #228822;"
        )
        self.setToolTip("Running")

    def set_stopped(self):
        self.setStyleSheet(
            "background-color: #cc4444; border-radius: 7px; border: 1px solid #882222;"
        )
        self.setToolTip("Stopped")

    def set_external(self):
        self.setStyleSheet(
            "background-color: #ccaa00; border-radius: 7px; border: 1px solid #886600;"
        )
        self.setToolTip("Running externally")


class ServerControlWidget(QWidget):
    sig_start = pyqtSignal(str, str, int, int)  # (executable, interface_cfg, telnet_port, tcl_port)
    sig_stop = pyqtSignal()
    sig_connect = pyqtSignal(str, int)          # (host, telnet_port)
    sig_disconnect = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Title
        title = QLabel("<b>OpenOCD Server</b>")
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(4)

        # Executable
        exe_row = QHBoxLayout()
        self._exe_edit = QLineEdit("openocd")
        self._exe_edit.setToolTip("Path to OpenOCD executable")
        exe_row.addWidget(self._exe_edit)
        btn_browse = QPushButton("...")
        btn_browse.setFixedWidth(28)
        btn_browse.clicked.connect(self._browse_exe)
        exe_row.addWidget(btn_browse)
        form.addRow("Executable:", exe_row)

        # Interface
        self._iface_combo = QComboBox()
        for name in INTERFACE_CONFIGS:
            self._iface_combo.addItem(name, INTERFACE_CONFIGS[name])
        self._iface_combo.setCurrentText(DEFAULT_INTERFACE)
        form.addRow("Interface:", self._iface_combo)

        # Telnet port
        self._telnet_spin = QSpinBox()
        self._telnet_spin.setRange(1024, 65535)
        self._telnet_spin.setValue(DEFAULT_TELNET_PORT)
        form.addRow("Telnet port:", self._telnet_spin)

        # TCL port
        self._tcl_spin = QSpinBox()
        self._tcl_spin.setRange(1024, 65535)
        self._tcl_spin.setValue(DEFAULT_TCL_PORT)
        form.addRow("TCL port:", self._tcl_spin)

        layout.addLayout(form)

        # Status row
        status_row = QHBoxLayout()
        self._dot = StatusDot()
        status_row.addWidget(self._dot)
        self._status_label = QLabel("Stopped")
        status_row.addWidget(self._status_label)
        status_row.addStretch()
        self._pid_label = QLabel("")
        self._pid_label.setStyleSheet("color: #888888; font-size: 9pt;")
        status_row.addWidget(self._pid_label)
        layout.addLayout(status_row)

        # Start / Stop buttons
        btn_row = QHBoxLayout()
        self._btn_start = QPushButton("Start")
        self._btn_start.setStyleSheet("background-color: #2a6e2a; color: white;")
        self._btn_start.clicked.connect(self._on_start)
        btn_row.addWidget(self._btn_start)

        self._btn_stop = QPushButton("Stop")
        self._btn_stop.setStyleSheet("background-color: #6e2a2a; color: white;")
        self._btn_stop.setEnabled(False)
        self._btn_stop.clicked.connect(self._on_stop)
        btn_row.addWidget(self._btn_stop)
        layout.addLayout(btn_row)

        # Connect / Disconnect buttons
        conn_row = QHBoxLayout()
        self._btn_connect = QPushButton("Connect")
        self._btn_connect.setEnabled(False)
        self._btn_connect.clicked.connect(self._on_connect)
        conn_row.addWidget(self._btn_connect)

        self._btn_disconnect = QPushButton("Disconnect")
        self._btn_disconnect.setEnabled(False)
        self._btn_disconnect.clicked.connect(self._on_disconnect)
        conn_row.addWidget(self._btn_disconnect)
        layout.addLayout(conn_row)

        layout.addStretch()

    # ------------------------------------------------------------------
    # Public slots
    # ------------------------------------------------------------------

    def on_openocd_detected(self):
        """Called when an already-running OpenOCD instance is found at startup."""
        self._dot.set_external()
        self._status_label.setText("Running (external)")
        self._pid_label.setText("")
        self._btn_connect.setEnabled(True)

    def on_server_started(self, pid: int):
        self._dot.set_running()
        self._status_label.setText("Running")
        self._pid_label.setText(f"PID {pid}")
        self._btn_start.setEnabled(False)
        self._btn_stop.setEnabled(True)
        self._btn_connect.setEnabled(True)

    def on_server_stopped(self):
        self._dot.set_stopped()
        self._status_label.setText("Stopped")
        self._pid_label.setText("")
        self._btn_start.setEnabled(True)
        self._btn_stop.setEnabled(False)
        self._btn_connect.setEnabled(False)
        self._btn_disconnect.setEnabled(False)

    def on_client_connected(self):
        self._btn_connect.setEnabled(False)
        self._btn_disconnect.setEnabled(True)

    def on_client_disconnected(self):
        self._btn_connect.setEnabled(True)
        self._btn_disconnect.setEnabled(False)

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    @property
    def executable(self) -> str:
        return self._exe_edit.text().strip() or "openocd"

    @property
    def interface_cfg(self) -> str:
        return self._iface_combo.currentData()

    @property
    def telnet_port(self) -> int:
        return self._telnet_spin.value()

    @property
    def tcl_port(self) -> int:
        return self._tcl_spin.value()

    # ------------------------------------------------------------------
    # Private slots
    # ------------------------------------------------------------------

    def _on_start(self):
        self.sig_start.emit(
            self.executable,
            self.interface_cfg,
            self.telnet_port,
            self.tcl_port,
        )

    def _on_stop(self):
        self.sig_stop.emit()

    def _on_connect(self):
        self.sig_connect.emit("localhost", self.telnet_port)

    def _on_disconnect(self):
        self.sig_disconnect.emit()

    def _browse_exe(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select OpenOCD Executable", "", "All Files (*)")
        if path:
            self._exe_edit.setText(path)
