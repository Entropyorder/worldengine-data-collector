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

Memory reads use ReadProcessMemory (never bare from_address) so that a bad
address returns None rather than causing a C-level ACCESS_VIOLATION.
The address-based scan handles cases where Qt6Gui.dll imports these functions
from combase.dll instead of ole32.dll (common on Windows 10/11).
"""
from __future__ import annotations
import ctypes
import struct
import sys
import logging

_log = logging.getLogger(__name__)

# Keep stubs alive for the lifetime of the process
_STUBS: list = []


def _rpmem(proc: int, addr: int, size: int) -> bytes | None:
    """Read `size` bytes at `addr` via ReadProcessMemory.
    Returns None on any failure — never raises or crashes."""
    if size <= 0:
        return b""
    buf = (ctypes.c_char * size)()
    nread = ctypes.c_size_t(0)
    ok = ctypes.windll.kernel32.ReadProcessMemory(
        ctypes.c_void_p(proc),
        ctypes.c_void_p(addr),
        buf,
        ctypes.c_size_t(size),
        ctypes.byref(nread),
    )
    if not ok or nread.value < size:
        return None
    return bytes(buf)


def apply() -> None:
    if sys.platform != "win32":
        return

    _log.info("_fix_win_ole: apply() starting")

    kernel32 = ctypes.WinDLL("kernel32")
    kernel32.GetModuleHandleW.restype  = ctypes.c_void_p   # full 64-bit pointer
    kernel32.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
    kernel32.GetCurrentProcess.restype  = ctypes.c_void_p
    kernel32.GetCurrentProcess.argtypes = []

    hmod = kernel32.GetModuleHandleW("Qt6Gui.dll")
    if not hmod:
        _log.warning("_fix_win_ole: Qt6Gui.dll not loaded — skipping patch")
        return

    proc = kernel32.GetCurrentProcess()
    base = int(hmod)
    _log.info("_fix_win_ole: Qt6Gui.dll base=0x%x", base)

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
    # GetProcAddress follows forwarder chains (ole32 → combase on Win10+),
    # so these addresses match whatever Qt6Gui.dll's IAT actually contains
    # at runtime, regardless of which DLL Qt was linked against.
    ole32 = ctypes.WinDLL("ole32.dll")
    targets: dict[int, tuple[str, int]] = {}
    for fn_name, stub in [
        ("CoCreateFreeThreadedMarshaler", _stub_ftm),
        ("RegisterDragDrop",              _stub_rdd),
    ]:
        real_addr = ctypes.cast(getattr(ole32, fn_name), ctypes.c_void_p).value
        stub_addr = ctypes.cast(stub, ctypes.c_void_p).value
        if real_addr and stub_addr:
            targets[real_addr] = (fn_name, stub_addr)
            _log.info("_fix_win_ole: target %s @ 0x%x", fn_name, real_addr)

    if not targets:
        _log.warning("_fix_win_ole: could not resolve ole32 targets")
        return

    # ── Read SizeOfImage from PE header (safe via ReadProcessMemory) ──────────
    size_of_image = 32 * 1024 * 1024  # conservative fallback: 32 MB
    dos = _rpmem(proc, base, 0x40)
    if dos and dos[:2] == b'MZ':
        e_lfanew = struct.unpack_from('<I', dos, 0x3C)[0]
        # SizeOfImage is at optional-header+0x38 for both PE32 and PE32+
        opt_data = _rpmem(proc, base + e_lfanew + 24, 0x3C)
        if opt_data and len(opt_data) >= 0x3C:
            magic = struct.unpack_from('<H', opt_data)[0]
            if magic in (0x010B, 0x020B):
                size_of_image = struct.unpack_from('<I', opt_data, 0x38)[0]
                _log.info("_fix_win_ole: SizeOfImage=0x%x", size_of_image)

    # ── Scan module pages for IAT pointer values ──────────────────────────────
    # VirtualQuery identifies readable committed regions; ReadProcessMemory reads
    # the entire region into a Python bytes buffer for safe address comparison.
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
                ctypes.c_void_p(base + offset),
                ctypes.byref(mbi),
                ctypes.sizeof(mbi)):
            offset += PAGE_SIZE
            continue

        region = int(mbi.RegionSize)
        is_committed = (mbi.State == MEM_COMMIT)
        prot = mbi.Protect
        # Skip PAGE_NOACCESS (0x01), unprotected (0x00), and GUARD pages (0x100)
        is_readable = is_committed and prot not in (0x00, 0x01) and not (prot & 0x100)

        if is_readable:
            scan_len = min(region, size_of_image - offset)
            # Read the entire region at once — safe, returns None if any error
            region_data = _rpmem(proc, base + offset, scan_len)
            if region_data:
                for off in range(0, len(region_data) - 7, 8):
                    val = struct.unpack_from('<Q', region_data, off)[0]
                    if val in remaining:
                        fn_name, stub_addr = targets[val]
                        scan_addr = base + offset + off
                        old_prot = ctypes.c_uint32(0)
                        ok = ctypes.windll.kernel32.VirtualProtect(
                            ctypes.c_void_p(scan_addr), 8, PAGE_READWRITE,
                            ctypes.byref(old_prot))
                        if ok:
                            # from_address is safe here: page just made writable,
                            # address verified by ReadProcessMemory above.
                            ctypes.c_uint64.from_address(scan_addr).value = stub_addr
                            ctypes.windll.kernel32.VirtualProtect(
                                ctypes.c_void_p(scan_addr), 8, old_prot,
                                ctypes.byref(old_prot))
                            _log.info("_fix_win_ole: patched %s at Qt6Gui+0x%x",
                                      fn_name, offset + off)
                            remaining.discard(val)
                        else:
                            _log.warning("_fix_win_ole: VirtualProtect failed for %s", fn_name)

        offset += max(region, PAGE_SIZE)

    for real_addr in remaining:
        fn_name, _ = targets[real_addr]
        _log.warning("_fix_win_ole: could NOT find %s in Qt6Gui.dll IAT", fn_name)

    _log.info("_fix_win_ole: apply() done, remaining=%d", len(remaining))
