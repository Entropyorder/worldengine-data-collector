"""
IAT-patch CoCreateFreeThreadedMarshaler and RegisterDragDrop.

QWindowsOleDropTarget (which calls these functions) lives in the Qt Windows
platform plugin — qwindows.dll — NOT in Qt6Gui.dll.  qwindows.dll is loaded
when QApplication() is constructed, so apply() must be called AFTER creating
QApplication but BEFORE showing any window.

All memory reads use ReadProcessMemory so a bad address returns None instead
of a C-level ACCESS_VIOLATION that Python try/except cannot catch.
"""
from __future__ import annotations
import ctypes
import struct
import sys
import logging

_log = logging.getLogger(__name__)
_STUBS: list = []

# Candidate DLLs that may contain the OLE drop-target calls.
# qwindows.dll (platform plugin) is the primary target;
# Qt6Gui.dll is kept as fallback.
_CANDIDATE_DLLS = ["qwindows.dll", "Qt6Gui.dll"]


def _rpmem(proc: int, addr: int, size: int) -> bytes | None:
    if size <= 0:
        return b""
    buf = (ctypes.c_char * size)()
    nread = ctypes.c_size_t(0)
    ok = ctypes.windll.kernel32.ReadProcessMemory(
        ctypes.c_void_p(proc), ctypes.c_void_p(addr),
        buf, ctypes.c_size_t(size), ctypes.byref(nread),
    )
    return bytes(buf) if ok and nread.value >= size else None


def _cstr(proc: int, addr: int, maxlen: int = 128) -> bytes:
    d = _rpmem(proc, addr, maxlen)
    return d.split(b"\x00")[0] if d else b""


def _walk_and_patch(proc: int, base: int,
                    int_rva: int, iat_rva: int, ptr_size: int,
                    remaining: set[bytes],
                    target_stubs: dict[bytes, int],
                    dll_label: str) -> None:
    """Walk INT for names; patch IAT by position."""
    if not int_rva or not iat_rva:
        return
    fmt = '<Q' if ptr_size == 8 else '<I'
    ordinal_bit = (1 << 63) if ptr_size == 8 else (1 << 31)
    PAGE_READWRITE = 0x04
    idx = 0
    while remaining:
        entry = _rpmem(proc, base + int_rva + idx * ptr_size, ptr_size)
        if not entry:
            break
        val = struct.unpack_from(fmt, entry)[0]
        if val == 0:
            break
        if not (val & ordinal_bit):
            ibn_rva = val & (ordinal_bit - 1)
            fn_name = _cstr(proc, base + ibn_rva + 2, 96)
            if fn_name in remaining:
                iat_addr = base + iat_rva + idx * ptr_size
                iat_data = _rpmem(proc, iat_addr, ptr_size)
                old_val = struct.unpack_from(fmt, iat_data)[0] if iat_data else 0
                stub_addr = target_stubs[fn_name]
                old_prot = ctypes.c_uint32(0)
                if ctypes.windll.kernel32.VirtualProtect(
                        ctypes.c_void_p(iat_addr), ptr_size,
                        PAGE_READWRITE, ctypes.byref(old_prot)):
                    t = ctypes.c_uint64 if ptr_size == 8 else ctypes.c_uint32
                    t.from_address(iat_addr).value = stub_addr
                    ctypes.windll.kernel32.VirtualProtect(
                        ctypes.c_void_p(iat_addr), ptr_size,
                        old_prot, ctypes.byref(old_prot))
                    _log.info("_fix_win_ole: patched %s in %s (0x%x→0x%x)",
                              fn_name.decode(), dll_label, old_val, stub_addr)
                    remaining.discard(fn_name)
                else:
                    _log.warning("_fix_win_ole: VirtualProtect failed for %s in %s",
                                 fn_name.decode(), dll_label)
        idx += 1


def _patch_dll(dll_name: str, proc: int,
               remaining: set[bytes],
               target_stubs: dict[bytes, int]) -> None:
    """Try to patch the two target functions inside `dll_name`."""
    kernel32 = ctypes.WinDLL("kernel32")
    kernel32.GetModuleHandleW.restype  = ctypes.c_void_p
    kernel32.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]

    hmod = kernel32.GetModuleHandleW(dll_name)
    if not hmod:
        _log.debug("_fix_win_ole: %s not loaded, skipping", dll_name)
        return

    base = int(hmod)
    _log.info("_fix_win_ole: scanning %s @ 0x%x", dll_name, base)

    # DOS → NT headers
    dos = _rpmem(proc, base, 0x40)
    if not dos or dos[:2] != b'MZ':
        return
    e_lfanew = struct.unpack_from('<I', dos, 0x3C)[0]
    if _rpmem(proc, base + e_lfanew, 4) != b'PE\x00\x00':
        return

    opt2 = _rpmem(proc, base + e_lfanew + 24, 2)
    if not opt2:
        return
    magic = struct.unpack_from('<H', opt2)[0]
    if magic == 0x010B:
        dd_base = e_lfanew + 24 + 0x60
        ptr_size = 4
    elif magic == 0x020B:
        dd_base = e_lfanew + 24 + 0x70
        ptr_size = 8
    else:
        return

    def _dd_rva(idx: int) -> int:
        d = _rpmem(proc, base + dd_base + idx * 8, 4)
        return struct.unpack_from('<I', d)[0] if d else 0

    # Regular import directory (index 1)
    import_rva = _dd_rva(1)
    if import_rva:
        off = import_rva
        while remaining:
            desc = _rpmem(proc, base + off, 20)
            if not desc:
                break
            orig, _, _, name_rva, first = struct.unpack_from('<IIIII', desc)
            if orig == 0 and name_rva == 0:
                break
            src_dll = _cstr(proc, base + name_rva, 64).lower()
            _log.debug("_fix_win_ole:   import %s  INT=0x%x IAT=0x%x", src_dll, orig, first)
            _walk_and_patch(proc, base, orig, first, ptr_size,
                            remaining, target_stubs, dll_name)
            off += 20

    if not remaining:
        return

    # Delay import directory (index 13)
    delay_rva = _dd_rva(13)
    _log.info("_fix_win_ole:   delay-import RVA=0x%x in %s", delay_rva, dll_name)
    if delay_rva:
        off = delay_rva
        while remaining:
            desc = _rpmem(proc, base + off, 32)
            if not desc:
                break
            (attrs, dll_name_rva, _, iat_rva,
             int_rva, _, _, _) = struct.unpack_from('<8I', desc)
            if dll_name_rva == 0 and iat_rva == 0:
                break
            src_dll = _cstr(proc, base + dll_name_rva, 64).lower()
            _log.info("_fix_win_ole:   delay %s  INT=0x%x IAT=0x%x",
                      src_dll, int_rva, iat_rva)
            _walk_and_patch(proc, base, int_rva, iat_rva, ptr_size,
                            remaining, target_stubs, dll_name)
            off += 32


def apply() -> None:
    if sys.platform != "win32":
        return

    _log.info("_fix_win_ole: apply() starting")

    # Build stubs once (kept alive in _STUBS)
    if not _STUBS:
        @ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p,
                            ctypes.POINTER(ctypes.c_void_p))
        def _stub_ftm(pUnkOuter, ppunkMarshal):
            if ppunkMarshal:
                ppunkMarshal[0] = None
            return 0

        @ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p)
        def _stub_rdd(hwnd, pDropTarget):
            return 0

        _STUBS.extend([_stub_ftm, _stub_rdd])

    target_stubs: dict[bytes, int] = {
        b"CoCreateFreeThreadedMarshaler":
            ctypes.cast(_STUBS[0], ctypes.c_void_p).value or 0,
        b"RegisterDragDrop":
            ctypes.cast(_STUBS[1], ctypes.c_void_p).value or 0,
    }
    remaining = set(target_stubs.keys())

    kernel32 = ctypes.WinDLL("kernel32")
    kernel32.GetCurrentProcess.restype  = ctypes.c_void_p
    kernel32.GetCurrentProcess.argtypes = []
    proc = kernel32.GetCurrentProcess()

    for dll_name in _CANDIDATE_DLLS:
        if not remaining:
            break
        _patch_dll(dll_name, proc, remaining, target_stubs)

    # Inline hook fallback: for any function still unpatched after IAT scan
    # (e.g. CoCreateFreeThreadedMarshaler loaded via GetProcAddress at runtime).
    # x64: MOV RAX, <stub_addr> (10 bytes) + JMP RAX (2 bytes) = 12 bytes
    PAGE_EXECUTE_READWRITE = 0x40
    for fn_name in list(remaining):
        dll_name_for_fn = {
            b"CoCreateFreeThreadedMarshaler": "ole32.dll",
            b"RegisterDragDrop":              "ole32.dll",
        }.get(fn_name)
        if not dll_name_for_fn:
            _log.warning("_fix_win_ole: no DLL known for %s, skipping inline hook",
                         fn_name.decode())
            continue
        try:
            dll = ctypes.WinDLL(dll_name_for_fn)
            fn_ptr = ctypes.cast(
                getattr(dll, fn_name.decode()),
                ctypes.c_void_p,
            ).value
            if not fn_ptr:
                _log.warning("_fix_win_ole: GetProcAddress returned NULL for %s",
                             fn_name.decode())
                continue
            stub_addr = target_stubs[fn_name]
            patch = b'\x48\xB8' + struct.pack('<Q', stub_addr) + b'\xFF\xE0'
            old_prot = ctypes.c_uint32(0)
            if ctypes.windll.kernel32.VirtualProtect(
                    ctypes.c_void_p(fn_ptr), len(patch),
                    PAGE_EXECUTE_READWRITE, ctypes.byref(old_prot)):
                ctypes.memmove(fn_ptr, patch, len(patch))
                ctypes.windll.kernel32.VirtualProtect(
                    ctypes.c_void_p(fn_ptr), len(patch),
                    old_prot, ctypes.byref(old_prot))
                remaining.discard(fn_name)
                _log.info("_fix_win_ole: inline-patched %s @ 0x%x → stub 0x%x",
                          fn_name.decode(), fn_ptr, stub_addr)
            else:
                _log.warning("_fix_win_ole: VirtualProtect(RWX) failed for %s @ 0x%x",
                             fn_name.decode(), fn_ptr)
        except Exception as exc:
            _log.warning("_fix_win_ole: inline hook failed for %s: %s",
                         fn_name.decode(), exc)

    for fn in remaining:
        _log.warning("_fix_win_ole: FAILED to patch %s", fn.decode())

    _log.info("_fix_win_ole: done, remaining=%d", len(remaining))
