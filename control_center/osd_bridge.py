from __future__ import annotations
import ctypes
import platform
from pathlib import Path

SHMEM_NAME = "WorldEngineCapture_SharedMem"
SHMEM_SIZE = 4096

# SharedFrameSync layout offsets (must match dx_capture/include/shared_protocol.h exactly)
# int64  frame_index        offset 0
# double present_time_ms    offset 8
# float  game_fps           offset 16
# int32  capture_active     offset 20
# int32  reserved           offset 24
# char[64] session_id       offset 28
# char[256] output_path     offset 92

OFFSET_FRAME_INDEX    = 0
OFFSET_PRESENT_TIME   = 8
OFFSET_GAME_FPS       = 16
OFFSET_CAPTURE_ACTIVE = 20
OFFSET_SESSION_ID     = 28
OFFSET_OUTPUT_PATH    = 92


class OsdBridge:
    """
    Reads/writes the shared memory segment created by dx_capture.dll.
    All methods are no-ops on non-Windows platforms.
    """

    def __init__(self) -> None:
        self._handle = None
        self._view = None
        self._is_windows = platform.system() == "Windows"

    def open(self) -> bool:
        """Open existing shared memory created by dx_capture.dll. Returns True on success."""
        if not self._is_windows:
            return False
        import ctypes.wintypes as wt
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        FILE_MAP_ALL_ACCESS = 0x000F001F
        self._handle = kernel32.OpenFileMappingW(FILE_MAP_ALL_ACCESS, False, SHMEM_NAME)
        if not self._handle:
            return False
        self._view = kernel32.MapViewOfFile(self._handle, FILE_MAP_ALL_ACCESS, 0, 0, SHMEM_SIZE)
        return bool(self._view)

    def close(self) -> None:
        if not self._is_windows:
            return
        kernel32 = ctypes.WinDLL("kernel32")
        if self._view:
            kernel32.UnmapViewOfFile(self._view)
            self._view = None
        if self._handle:
            kernel32.CloseHandle(self._handle)
            self._handle = None

    def set_capture_active(self, active: bool) -> None:
        if not self._view:
            return
        val = ctypes.c_int32(1 if active else 0)
        ctypes.memmove(self._view + OFFSET_CAPTURE_ACTIVE, ctypes.addressof(val), 4)

    def set_session(self, session_id: str, output_path: str) -> None:
        if not self._view:
            return
        sid = session_id.encode("utf-8")[:63] + b"\x00"
        ctypes.memmove(self._view + OFFSET_SESSION_ID, sid, len(sid))
        pth = output_path.encode("utf-8")[:255] + b"\x00"
        ctypes.memmove(self._view + OFFSET_OUTPUT_PATH, pth, len(pth))

    def read_game_fps(self) -> float:
        if not self._view:
            return 0.0
        val = ctypes.c_float()
        ctypes.memmove(ctypes.addressof(val), self._view + OFFSET_GAME_FPS, 4)
        return val.value

    def read_frame_index(self) -> int:
        if not self._view:
            return 0
        val = ctypes.c_int64()
        ctypes.memmove(ctypes.addressof(val), self._view + OFFSET_FRAME_INDEX, 8)
        return val.value
