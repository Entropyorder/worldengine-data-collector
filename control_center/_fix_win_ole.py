"""
IAT-patch CoCreateFreeThreadedMarshaler and RegisterDragDrop in Qt6Gui.dll.

Qt unconditionally registers every top-level window as an OLE drop target.
On some Windows machines (common with Chinese security/input-method software that
hooks COM), the QWindowsOleDropTarget constructor crashes inside
CoCreateFreeThreadedMarshaler or RegisterDragDrop with STATUS_ACCESS_VIOLATION.

Since this app does not use drag-and-drop at all, we replace both functions in
Qt6Gui.dll's IAT with harmless stubs.  The stubs return S_OK and set the
out-pointer to NULL so Qt's IUnknown::QueryInterface handles the "no free-
threaded marshaler" case gracefully.

Call apply() AFTER importing PyQt6 (which loads Qt6Gui.dll) but BEFORE
creating QApplication.
"""
from __future__ import annotations
import ctypes
import struct
import sys
import logging

_log = logging.getLogger(__name__)

# Keep stubs alive for the lifetime of the process
_STUBS: list = []


def apply() -> None:
    if sys.platform != "win32":
        return

    hmod = ctypes.windll.kernel32.GetModuleHandleW("Qt6Gui.dll")
    if not hmod:
        _log.warning("_fix_win_ole: Qt6Gui.dll not loaded yet — skipping patch")
        return

    # ── Build stubs ───────────────────────────────────────────────────────────
    @ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
    def _stub_ftm(pUnkOuter, ppunkMarshal):
        """No-op CoCreateFreeThreadedMarshaler: sets *ppunkMarshal=NULL, returns S_OK."""
        if ppunkMarshal:
            ppunkMarshal[0] = None
        return 0  # S_OK

    @ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p)
    def _stub_rdd(hwnd, pDropTarget):
        """No-op RegisterDragDrop: returns S_OK without registering."""
        return 0  # S_OK

    _STUBS.extend([_stub_ftm, _stub_rdd])

    # ── Get real addresses from ole32.dll ─────────────────────────────────────
    ole32 = ctypes.WinDLL("ole32.dll")
    targets: dict[int, tuple[str, int]] = {}
    for fn_name, stub in [
        ("CoCreateFreeThreadedMarshaler", _stub_ftm),
        ("RegisterDragDrop",              _stub_rdd),
    ]:
        real_addr  = ctypes.cast(getattr(ole32, fn_name), ctypes.c_void_p).value
        stub_addr  = ctypes.cast(stub,                    ctypes.c_void_p).value
        targets[real_addr] = (fn_name, stub_addr)

    # ── Get SizeOfImage from PE header ────────────────────────────────────────
    try:
        e_lfanew       = struct.unpack('<I', bytes((ctypes.c_char * 4).from_address(hmod + 0x3C)))[0]
        size_of_image  = struct.unpack('<I', bytes((ctypes.c_char * 4).from_address(hmod + e_lfanew + 0x50)))[0]
    except Exception:
        size_of_image = 16 * 1024 * 1024  # fallback: 16 MB

    # ── Scan module pages for IAT pointer values ──────────────────────────────
    class _MBI(ctypes.Structure):
        _fields_ = [
            ("BaseAddress",       ctypes.c_uint64),
            ("AllocationBase",    ctypes.c_uint64),
            ("AllocationProtect", ctypes.c_uint32),
            ("_pad1",             ctypes.c_uint32),
            ("RegionSize",        ctypes.c_uint64),
            ("State",             ctypes.c_uint32),
            ("Protect",           ctypes.c_uint32),
            ("Type",              ctypes.c_uint32),
            ("_pad2",             ctypes.c_uint32),
        ]

    PAGE_SIZE      = 0x1000
    PAGE_READWRITE = 0x04
    MEM_COMMIT     = 0x1000

    remaining = set(targets.keys())
    offset = 0

    while offset < size_of_image and remaining:
        mbi = _MBI()
        if not ctypes.windll.kernel32.VirtualQuery(
                ctypes.c_void_p(hmod + offset),
                ctypes.byref(mbi),
                ctypes.sizeof(mbi)):
            offset += PAGE_SIZE
            continue

        region = int(mbi.RegionSize)
        is_committed = (mbi.State == MEM_COMMIT)
        is_readable  = mbi.Protect not in (0x00, 0x01) and not (mbi.Protect & 0x100)

        if is_committed and is_readable:
            scan_len = min(region, size_of_image - offset)
            for off in range(0, scan_len - 7, 8):
                scan_addr = hmod + offset + off
                try:
                    val = ctypes.c_uint64.from_address(scan_addr).value
                except Exception:
                    continue

                if val in remaining:
                    fn_name, stub_addr = targets[val]
                    old_prot = ctypes.c_uint32(0)
                    ok = ctypes.windll.kernel32.VirtualProtect(
                        ctypes.c_void_p(scan_addr), 8, PAGE_READWRITE,
                        ctypes.byref(old_prot))
                    if ok:
                        ctypes.c_uint64.from_address(scan_addr).value = stub_addr
                        ctypes.windll.kernel32.VirtualProtect(
                            ctypes.c_void_p(scan_addr), 8, old_prot,
                            ctypes.byref(old_prot))
                        _log.info("_fix_win_ole: patched %s at Qt6Gui+0x%x", fn_name, offset + off)
                        remaining.discard(val)

        offset += max(region, PAGE_SIZE)

    for real_addr in remaining:
        fn_name, _ = targets[real_addr]
        _log.warning("_fix_win_ole: could NOT find %s in Qt6Gui.dll IAT", fn_name)
