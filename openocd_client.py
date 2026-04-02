"""Telnet client for OpenOCD command interface (port 4444)."""

import socket
import threading
import queue
import time
from PyQt5.QtCore import QObject, pyqtSignal, QThread


_PROMPT = b"> "
_RECV_CHUNK = 4096
_CONNECT_TIMEOUT = 5.0
_RECV_TIMEOUT = 10.0


class OpenOCDClient(QObject):
    """Runs in a dedicated QThread. Commands are sent via send_command()
    and results arrive on the response_ready signal."""

    response_ready = pyqtSignal(str, str)   # (cmd_id, response)
    error = pyqtSignal(str)
    connected = pyqtSignal()
    disconnected = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sock = None
        self._cmd_queue = queue.Queue()
        self._running = False
        self._lock = threading.Lock()
        self._worker_thread = None

    # ------------------------------------------------------------------
    # Public API (thread-safe, callable from main thread)
    # ------------------------------------------------------------------

    def connect_to_server(self, host="localhost", port=4444):
        if self._running:
            return
        self._running = True
        self._worker_thread = threading.Thread(
            target=self._run_loop,
            args=(host, port),
            daemon=True,
        )
        self._worker_thread.start()

    def send_command(self, cmd_id: str, cmd: str):
        """Queue a command. Response arrives on response_ready signal."""
        self._cmd_queue.put((cmd_id, cmd))

    def disconnect(self):
        self._running = False
        self._cmd_queue.put(None)   # wake up blocked get()
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass

    @property
    def is_connected(self):
        return self._sock is not None and self._running

    # ------------------------------------------------------------------
    # Internal worker loop (runs in background thread)
    # ------------------------------------------------------------------

    def _run_loop(self, host, port):
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.settimeout(_CONNECT_TIMEOUT)
            self._sock.connect((host, port))
            self._sock.settimeout(_RECV_TIMEOUT)
            # consume initial prompt
            self._read_until_prompt()
            self.connected.emit()
        except Exception as e:
            self.error.emit(f"Cannot connect to OpenOCD at {host}:{port} — {e}")
            self._sock = None
            self._running = False
            return

        while self._running:
            try:
                item = self._cmd_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            if item is None:
                break
            cmd_id, cmd = item
            try:
                response = self._send_raw(cmd)
                self.response_ready.emit(cmd_id, response)
            except Exception as e:
                self.error.emit(f"Command error: {e}")
                break

        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
        self._sock = None
        self._running = False
        self.disconnected.emit()

    def _send_raw(self, cmd: str) -> str:
        payload = (cmd.strip() + "\n").encode("utf-8")
        self._sock.sendall(payload)
        return self._read_until_prompt()

    def _read_until_prompt(self) -> str:
        buf = b""
        while True:
            chunk = self._sock.recv(_RECV_CHUNK)
            if not chunk:
                raise ConnectionError("Connection closed by OpenOCD")
            buf += chunk
            if buf.endswith(_PROMPT):
                # strip trailing prompt and decode
                result = buf[: -len(_PROMPT)].decode("utf-8", errors="replace")
                return result.strip()


class OpenOCDProbeWorker(QThread):
    """Probe whether OpenOCD's telnet port is already listening on startup."""
    detected = pyqtSignal(str, int)   # (host, port) — emitted only on success

    def __init__(self, host="localhost", port=4444):
        super().__init__()
        self._host = host
        self._port = port

    def run(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1.0)
            s.connect((self._host, self._port))
            s.close()
            self.detected.emit(self._host, self._port)
        except Exception:
            pass   # not running — silent


class ShutdownWorker(QThread):
    """Send 'shutdown' to an external OpenOCD instance via a temporary connection."""
    done = pyqtSignal(bool, str)   # (success, message)

    def __init__(self, host="localhost", port=4444):
        super().__init__()
        self._host = host
        self._port = port

    def run(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3.0)
            sock.connect((self._host, self._port))
            sock.settimeout(5.0)
            # consume initial prompt
            buf = b""
            while not buf.endswith(_PROMPT):
                chunk = sock.recv(_RECV_CHUNK)
                if not chunk:
                    break
                buf += chunk
            sock.sendall(b"shutdown\n")
            # drain response until server closes the connection
            try:
                while True:
                    chunk = sock.recv(_RECV_CHUNK)
                    if not chunk:
                        break
            except Exception:
                pass
            sock.close()
            self.done.emit(True, "OpenOCD shutdown command sent successfully.")
        except Exception as e:
            self.done.emit(False, str(e))


class SyncClient:
    """Simple synchronous client for use in worker threads (FlashWorker, etc.)."""

    def __init__(self, host="localhost", port=4444):
        self._host = host
        self._port = port
        self._sock = None

    def connect(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.settimeout(_CONNECT_TIMEOUT)
        self._sock.connect((self._host, self._port))
        self._sock.settimeout(_RECV_TIMEOUT)
        self._read_until_prompt()

    def send(self, cmd: str) -> str:
        if self._sock is None:
            raise RuntimeError("Not connected")
        payload = (cmd.strip() + "\n").encode("utf-8")
        self._sock.sendall(payload)
        return self._read_until_prompt()

    def close(self):
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    def _read_until_prompt(self) -> str:
        buf = b""
        while True:
            chunk = self._sock.recv(_RECV_CHUNK)
            if not chunk:
                raise ConnectionError("Connection closed")
            buf += chunk
            if buf.endswith(_PROMPT):
                result = buf[: -len(_PROMPT)].decode("utf-8", errors="replace")
                return result.strip()

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *_):
        self.close()
