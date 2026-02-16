"""OpenOCD subprocess lifecycle management."""

import subprocess
import threading
from PyQt5.QtCore import QObject, pyqtSignal, QTimer


class OpenOCDManager(QObject):
    log_line = pyqtSignal(str)
    started = pyqtSignal(int)   # emits PID
    stopped = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._process = None
        self._stdout_thread = None
        self._stderr_thread = None
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._check_process)
        self._poll_timer.setInterval(500)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self, executable, interface_cfg, target_cfg, telnet_port=4444,
              tcl_port=6666, extra_args=None):
        if self._process is not None:
            self.error.emit("OpenOCD is already running.")
            return

        cmd = [
            executable,
            "-f", interface_cfg,
            "-f", target_cfg,
            "-c", f"telnet_port {telnet_port}",
            "-c", f"tcl_port {tcl_port}",
        ]
        if extra_args:
            cmd.extend(extra_args)

        self.log_line.emit(f"[INFO] Starting: {' '.join(cmd)}")
        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError:
            self.error.emit(f"OpenOCD executable not found: {executable}")
            self._process = None
            return
        except Exception as e:
            self.error.emit(f"Failed to start OpenOCD: {e}")
            self._process = None
            return

        self._stdout_thread = threading.Thread(
            target=self._read_stream,
            args=(self._process.stdout, "stdout"),
            daemon=True,
        )
        self._stderr_thread = threading.Thread(
            target=self._read_stream,
            args=(self._process.stderr, "stderr"),
            daemon=True,
        )
        self._stdout_thread.start()
        self._stderr_thread.start()
        self._poll_timer.start()
        self.started.emit(self._process.pid)

    def stop(self):
        if self._process is None:
            return
        self.log_line.emit("[INFO] Stopping OpenOCD...")
        try:
            self._process.terminate()
            self._process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self._process.kill()
        except Exception as e:
            self.error.emit(f"Error stopping OpenOCD: {e}")
        finally:
            self._cleanup()

    @property
    def is_running(self):
        return self._process is not None and self._process.poll() is None

    @property
    def pid(self):
        if self._process:
            return self._process.pid
        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read_stream(self, stream, name):
        try:
            for line in stream:
                stripped = line.rstrip("\n")
                if stripped:
                    self.log_line.emit(stripped)
        except Exception:
            pass

    def _check_process(self):
        if self._process and self._process.poll() is not None:
            exit_code = self._process.returncode
            self.log_line.emit(f"[INFO] OpenOCD exited with code {exit_code}")
            self._cleanup()

    def _cleanup(self):
        self._poll_timer.stop()
        self._process = None
        self.stopped.emit()
