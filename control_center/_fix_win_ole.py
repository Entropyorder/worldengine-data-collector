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

Memory reads use ReadProcessMemory (never from_address) so that a bad address
returns None rather than causing a C-level ACCESS_VIOLATION.
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
    """Read `size` bytes at `addr` in `proc` via ReadProcessMemory.
    Returns None on any failure instead of crashing."""
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

    stub_for: dict[bytes, int] = {
        b"CoCreateFreeThreadedMarshaler": ctypes.cast(_stub_ftm, ctypes.c_void_p).value or 0,
        b"RegisterDragDrop":              ctypes.cast(_stub_rdd, ctypes.c_void_p).value or 0,
    }
    remaining = set(stub_for.keys())

    # ── Parse DOS header ──────────────────────────────────────────────────────
    dos = _rpmem(proc, base, 0x40)
    if dos is None or dos[:2] != b'MZ':
        _log.warning("_fix_win_ole: bad DOS header at 0x%x", base)
        return

    e_lfanew = struct.unpack_from('<I', dos, 0x3C)[0]

    pe_sig = _rpmem(proc, base + e_lfanew, 4)
    if pe_sig != b'PE\x00\x00':
        _log.warning("_fix_win_ole: bad PE signature")
        return

    # Optional header starts at e_lfanew + 24 (4-byte sig + 20-byte COFF header)
    opt_hdr = _rpmem(proc, base + e_lfanew + 24, 2)
    if opt_hdr is None:
        return
    magic = struct.unpack_from('<H', opt_hdr)[0]
    if magic == 0x010B:     # PE32
        import_dir_rva_off = e_lfanew + 24 + 0x68
        ptr_size = 4
    elif magic == 0x020B:   # PE32+ (64-bit)
        import_dir_rva_off = e_lfanew + 24 + 0x78
        ptr_size = 8
    else:
        _log.warning("_fix_win_ole: unknown PE magic 0x%04x", magic)
        return

    idd = _rpmem(proc, base + import_dir_rva_off, 8)
    if idd is None:
        _log.warning("_fix_win_ole: could not read import data directory")
        return
    import_rva, _ = struct.unpack_from('<II', idd)
    if import_rva == 0:
        _log.warning("_fix_win_ole: import directory RVA is zero")
        return

    # ── Walk IMAGE_IMPORT_DESCRIPTOR array (20 bytes each) ───────────────────
    desc_rva = import_rva
    found_ole32 = False
    while remaining:
        desc = _rpmem(proc, base + desc_rva, 20)
        if desc is None:
            break
        orig_thunk_rva, _, _, name_rva, first_thunk_rva = struct.unpack_from('<IIIII', desc)
        if orig_thunk_rva == 0 and name_rva == 0:
            break  # null terminator — end of import table

        dll_name_buf = _rpmem(proc, base + name_rva, 32)
        dll_name = (dll_name_buf or b"").split(b'\x00')[0].lower()
        if dll_name != b"ole32.dll":
            desc_rva += 20
            continue

        found_ole32 = True
        _log.info("_fix_win_ole: found ole32.dll import descriptor")

        # Walk import name table (OriginalFirstThunk) and IAT (FirstThunk) in parallel
        thunk_rva = orig_thunk_rva if orig_thunk_rva else first_thunk_rva
        ordinal_flag = 0x8000000000000000 if ptr_size == 8 else 0x80000000
        fmt = '<Q' if ptr_size == 8 else '<I'

        idx = 0
        while remaining:
            thunk_data = _rpmem(proc, base + thunk_rva + idx * ptr_size, ptr_size)
            if thunk_data is None:
                break
            thunk_val = struct.unpack_from(fmt, thunk_data)[0]
            if thunk_val == 0:
                break  # end of this DLL's import list

            if not (thunk_val & ordinal_flag):
                # IMAGE_IMPORT_BY_NAME: 2-byte hint then null-terminated name
                by_name = _rpmem(proc, base + (thunk_val & ~ordinal_flag) + 2, 64)
                if by_name:
                    fn_name = by_name.split(b'\x00')[0]
                    if fn_name in remaining:
                        iat_entry_addr = base + first_thunk_rva + idx * ptr_size
                        old_prot = ctypes.c_uint32(0)
                        PAGE_READWRITE = 0x04
                        ok = ctypes.windll.kernel32.VirtualProtect(
                            ctypes.c_void_p(iat_entry_addr), ptr_size,
                            PAGE_READWRITE, ctypes.byref(old_prot))
                        if ok:
                            # from_address is safe here: address validated by
                            # ReadProcessMemory above, and page is now writable.
                            stub_addr = stub_for[fn_name]
                            t = ctypes.c_uint64 if ptr_size == 8 else ctypes.c_uint32
                            t.from_address(iat_entry_addr).value = stub_addr
                            ctypes.windll.kernel32.VirtualProtect(
                                ctypes.c_void_p(iat_entry_addr), ptr_size,
                                old_prot, ctypes.byref(old_prot))
                            _log.info("_fix_win_ole: patched %s at IAT 0x%x",
                                      fn_name.decode(), iat_entry_addr)
                            remaining.discard(fn_name)
                        else:
                            _log.warning("_fix_win_ole: VirtualProtect failed for %s",
                                         fn_name.decode())
            idx += 1

        desc_rva += 20

    if not found_ole32:
        _log.warning("_fix_win_ole: ole32.dll not found in Qt6Gui.dll import table")

    for fn_name in remaining:
        _log.warning("_fix_win_ole: could NOT patch %s", fn_name.decode())

    _log.info("_fix_win_ole: apply() done, remaining=%d", len(remaining))
