from __future__ import annotations
import json
import logging
import threading
from pathlib import Path
from abc import ABC, abstractmethod


class TransportServer(ABC):
    """Abstract base: a server that reads lines into a FrameBuffer."""

    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...


class FrameBuffer:
    """
    Accepts raw JSON lines from the Named Pipe and appends them to a JSONL file.
    Thread-safe: ingest() may be called from a reader thread.
    """

    def __init__(self, output_path: str) -> None:
        self._output_path = Path(output_path)
        self._lock = threading.Lock()
        self._count = 0
        self._file = None

    @property
    def frame_count(self) -> int:
        return self._count

    def open(self) -> None:
        with self._lock:
            self._file = open(self._output_path, "w", encoding="utf-8", buffering=1)

    def close(self) -> None:
        with self._lock:
            if self._file:
                self._file.flush()
                self._file.close()
                self._file = None

    def ingest(self, line: str) -> None:
        """Parse one JSON line and write to disk. Raises json.JSONDecodeError on bad input."""
        line = line.strip()
        if not line:
            return
        record = json.loads(line)  # validates JSON; raises on error
        with self._lock:
            if self._file:
                self._file.write(json.dumps(record, ensure_ascii=False) + "\n")
                self._count += 1


class PipeServer(TransportServer):
    """
    Opens a Windows Named Pipe server and reads lines into a FrameBuffer.
    Runs on a background daemon thread.
    NOTE: The actual pipe I/O uses Windows-only APIs (kernel32).
    On non-Windows platforms, this class exists but start() is a no-op with a warning.
    """

    PIPE_NAME = r"\\.\pipe\WorldEngineData"
    BUFFER_SIZE = 65536

    def __init__(self, frame_buffer: FrameBuffer) -> None:
        self._buffer = frame_buffer
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        import platform
        if platform.system() != "Windows":
            print("[PipeServer] Warning: Named pipes are Windows-only. Server not started.")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3.0)

    def _run(self) -> None:
        import ctypes
        import ctypes.wintypes as wt

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        PIPE_ACCESS_INBOUND = 0x00000001
        PIPE_TYPE_MESSAGE   = 0x00000004
        PIPE_READMODE_MESSAGE = 0x00000002
        PIPE_WAIT           = 0x00000000
        INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

        handle = kernel32.CreateNamedPipeW(
            self.PIPE_NAME,
            PIPE_ACCESS_INBOUND,
            PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT,
            1,
            self.BUFFER_SIZE,
            self.BUFFER_SIZE,
            0,
            None,
        )
        if handle == INVALID_HANDLE_VALUE:
            raise OSError(f"CreateNamedPipe failed: {ctypes.get_last_error()}")

        try:
            kernel32.ConnectNamedPipe(handle, None)
            buf = ctypes.create_string_buffer(self.BUFFER_SIZE)
            leftovers = b""
            while not self._stop_event.is_set():
                read = wt.DWORD(0)
                ok = kernel32.ReadFile(handle, buf, self.BUFFER_SIZE, ctypes.byref(read), None)
                if not ok or read.value == 0:
                    break
                data = leftovers + buf.raw[: read.value]
                *lines, leftovers = data.split(b"\n")
                for raw in lines:
                    try:
                        self._buffer.ingest(raw.decode("utf-8") + "\n")
                    except Exception as e:
                        logging.getLogger(__name__).error("PipeServer ingest error: %s", e)
        finally:
            kernel32.CloseHandle(handle)


class TCPServer(TransportServer):
    """
    Listens on localhost:port, accepts one client, reads JSON lines into FrameBuffer.
    Uses non-blocking I/O + select so it never blocks the calling thread.
    Designed for adapters that cannot use Windows Named Pipes (e.g. CET Lua, SKSE C++).
    """

    def __init__(self, frame_buffer: FrameBuffer, port: int = 27015) -> None:
        self._buffer = frame_buffer
        self._port = port
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="TCPServer")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3.0)

    def _run(self) -> None:
        import socket
        import select

        log = logging.getLogger(__name__)
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", self._port))
        server.listen(1)
        server.setblocking(False)
        client: socket.socket | None = None
        leftover = b""

        try:
            while not self._stop_event.is_set():
                if client is None:
                    r, _, _ = select.select([server], [], [], 0.05)
                    if r:
                        client, addr = server.accept()
                        client.setblocking(False)
                        leftover = b""
                        log.info("TCPServer: client connected from %s", addr)
                    continue

                r, _, _ = select.select([client], [], [], 0.05)
                if not r:
                    continue

                try:
                    data = client.recv(65536)
                except OSError as exc:
                    log.warning("TCPServer recv error: %s", exc)
                    client.close()
                    client = None
                    continue

                if not data:
                    log.info("TCPServer: client disconnected")
                    client.close()
                    client = None
                    continue

                chunk = leftover + data
                *lines, leftover = chunk.split(b"\n")
                for raw in lines:
                    decoded = raw.decode("utf-8", errors="replace").strip()
                    if not decoded:
                        continue
                    try:
                        self._buffer.ingest(decoded + "\n")
                    except Exception as exc:
                        log.error("TCPServer ingest error: %s", exc)
        finally:
            if client:
                client.close()
            server.close()
