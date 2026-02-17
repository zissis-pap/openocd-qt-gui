"""Main application window."""

import os
from version import __version__ as VERSION
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QSplitter, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QAction, QFileDialog, QMessageBox,
    QStatusBar, QSizePolicy
)
from PyQt5.QtCore import Qt, QThread
from PyQt5.QtGui import QIcon

from openocd_manager import OpenOCDManager
from openocd_client import OpenOCDClient
from widgets.server_control import ServerControlWidget
from widgets.mcu_selector import MCUSelectorWidget
from widgets.flash_ops import FlashOpsWidget
from widgets.memory_viewer import MemoryViewerWidget
from widgets.script_console import ScriptConsoleWidget
from widgets.log_widget import LogWidget


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OpenOCD Qt GUI")
        self.resize(1100, 750)
        self.setMinimumSize(800, 550)

        self._manager = OpenOCDManager(self)
        self._client = OpenOCDClient()
        self._client_thread = QThread(self)
        self._client.moveToThread(self._client_thread)
        self._client_thread.start()

        self._setup_menu()
        self._setup_central()
        self._setup_statusbar()
        self._connect_signals()

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _setup_menu(self):
        mb = self.menuBar()

        # File menu
        file_menu = mb.addMenu("&File")
        act_open = QAction("Open Firmware...", self)
        act_open.setShortcut("Ctrl+O")
        act_open.triggered.connect(self._open_firmware)
        file_menu.addAction(act_open)
        file_menu.addSeparator()
        act_quit = QAction("&Quit", self)
        act_quit.setShortcut("Ctrl+Q")
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        # View menu
        view_menu = mb.addMenu("&View")
        act_clear_log = QAction("Clear Log", self)
        act_clear_log.triggered.connect(lambda: self._log_widget.clear())
        view_menu.addAction(act_clear_log)

        # Help menu
        help_menu = mb.addMenu("&Help")
        act_about = QAction("&About", self)
        act_about.triggered.connect(self._show_about)
        help_menu.addAction(act_about)

    def _setup_central(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)

        # Vertical splitter: top area + log
        v_split = QSplitter(Qt.Vertical)

        # Top area: left panel + tabs
        top_widget = QWidget()
        top_layout = QHBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(4)

        # Horizontal splitter: left panel | right tabs
        h_split = QSplitter(Qt.Horizontal)

        # --- Left panel ---
        left_widget = QWidget()
        left_widget.setMinimumWidth(220)
        left_widget.setMaximumWidth(320)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        self._server_ctrl = ServerControlWidget()
        left_layout.addWidget(self._server_ctrl)

        self._mcu_selector = MCUSelectorWidget()
        left_layout.addWidget(self._mcu_selector)
        h_split.addWidget(left_widget)

        # --- Right tabs ---
        self._tabs = QTabWidget()

        self._flash_ops = FlashOpsWidget()
        self._tabs.addTab(self._flash_ops, "Flash Ops")

        self._mem_viewer = MemoryViewerWidget()
        self._tabs.addTab(self._mem_viewer, "Memory Viewer")

        self._script_console = ScriptConsoleWidget()
        self._tabs.addTab(self._script_console, "Script Console")

        h_split.addWidget(self._tabs)
        h_split.setStretchFactor(0, 0)
        h_split.setStretchFactor(1, 1)
        h_split.setSizes([250, 850])

        top_layout.addWidget(h_split)
        v_split.addWidget(top_widget)

        # --- Log widget ---
        self._log_widget = LogWidget()
        self._log_widget.setMinimumHeight(120)
        v_split.addWidget(self._log_widget)

        v_split.setStretchFactor(0, 1)
        v_split.setStretchFactor(1, 0)
        v_split.setSizes([530, 200])

        main_layout.addWidget(v_split)

    def _setup_statusbar(self):
        sb = self.statusBar()
        self._status_conn_label = QLabel("  Disconnected  ")
        self._status_conn_label.setStyleSheet(
            "color: #ff6666; font-weight: bold; padding: 2px 6px;"
        )
        sb.addPermanentWidget(self._status_conn_label)

        self._status_mcu_label = QLabel("No target")
        self._status_mcu_label.setStyleSheet("padding: 2px 8px;")
        sb.addPermanentWidget(self._status_mcu_label)

        sb.showMessage("Ready")

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _connect_signals(self):
        # Manager → UI
        self._manager.log_line.connect(self._log_widget.append_line)
        self._manager.started.connect(self._server_ctrl.on_server_started)
        self._manager.started.connect(lambda pid: self.statusBar().showMessage(f"OpenOCD started (PID {pid})"))
        self._manager.stopped.connect(self._server_ctrl.on_server_stopped)
        self._manager.stopped.connect(lambda: self.statusBar().showMessage("OpenOCD stopped"))
        self._manager.error.connect(self._log_widget.append_line)

        # Client → UI
        self._client.connected.connect(self._on_client_connected)
        self._client.disconnected.connect(self._on_client_disconnected)
        self._client.error.connect(self._log_widget.append_line)
        self._client.response_ready.connect(self._on_response)

        # Server control → manager / client
        self._server_ctrl.sig_start.connect(self._start_server)
        self._server_ctrl.sig_stop.connect(self._manager.stop)
        self._server_ctrl.sig_connect.connect(self._client.connect_to_server)
        self._server_ctrl.sig_disconnect.connect(self._client.disconnect)

        # MCU selector
        self._mcu_selector.sig_target_changed.connect(self._on_target_changed)

        # Flash ops log
        self._flash_ops.sig_log.connect(self._log_widget.append_line)
        self._mem_viewer.sig_log.connect(self._log_widget.append_line)
        self._script_console.sig_log.connect(self._log_widget.append_line)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _start_server(self, executable: str, interface_cfg: str, telnet_port: int, tcl_port: int):
        target_cfg = self._mcu_selector.target_config
        if not target_cfg:
            self._log_widget.append_line("[ERROR] Please select a target MCU first.")
            return
        self._manager.start(executable, interface_cfg, target_cfg, telnet_port, tcl_port)

    def _on_client_connected(self):
        self._server_ctrl.on_client_connected()
        self._status_conn_label.setText("  Connected  ")
        self._status_conn_label.setStyleSheet(
            "color: #66ff66; font-weight: bold; padding: 2px 6px;"
        )
        port = self._server_ctrl.telnet_port
        self._flash_ops.set_connection("localhost", port)
        self._mem_viewer.set_connection("localhost", port)
        self._script_console.set_connection("localhost", port)
        self.statusBar().showMessage("Connected to OpenOCD")

    def _on_client_disconnected(self):
        self._server_ctrl.on_client_disconnected()
        self._status_conn_label.setText("  Disconnected  ")
        self._status_conn_label.setStyleSheet(
            "color: #ff6666; font-weight: bold; padding: 2px 6px;"
        )
        self.statusBar().showMessage("Disconnected from OpenOCD")

    def _on_response(self, cmd_id: str, response: str):
        if response:
            self._log_widget.append_line(f"[{cmd_id}] {response}")

    def _on_target_changed(self, name: str, cfg: str):
        self._status_mcu_label.setText(f"Target: {name}")
        self._log_widget.append_line(f"[INFO] Target selected: {name} ({cfg})")

    def _open_firmware(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Firmware File", "",
            "Firmware Files (*.bin *.elf *.hex *.s19);;All Files (*)"
        )
        if path:
            self._tabs.setCurrentWidget(self._flash_ops)
            self._flash_ops._file_edit.setText(path)

    def _show_about(self):
        QMessageBox.about(
            self,
            "About OpenOCD Qt GUI",
            f"<h3>OpenOCD Qt GUI</h3>"
            f"<p><b>Version:</b> {VERSION}</p>"
            "<p>A PyQt5 frontend for OpenOCD debug server.</p>"
            "<p>Supports STM32 device families via ST-Link and other adapters.</p>"
            "<p>OpenOCD must be installed separately.</p>"
            "<hr>"
            "<p><b>Author:</b> Zissis Papadopoulos</p>"
            "<p><b>GitHub:</b> <a href='https://github.com/zissis-pap'>github.com/zissis-pap</a></p>",
        )

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        self._client.disconnect()
        if self._manager.is_running:
            self._manager.stop()
        self._client_thread.quit()
        self._client_thread.wait(2000)
        event.accept()
