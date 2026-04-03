"""
IAT-patch CoCreateFreeThreadedMarshaler and RegisterDragDrop in Qt6Gui.dll.

Qt unconditionally registers every top-level window as an OLE drop target.
On machines with Chinese security/IME software (360, Tencent, Sogou, etc.)
that hooks COM, the QWindowsOleDropTarget constructor crashes.

Root cause: Qt6Gui.dll DELAY-LOADS CoCreateFreeThreadedMarshaler and
RegisterDragDrop from ole32.dll.  The delay-load IAT initially holds the
address of __delayLoadHelper2 (not the real function), so:
  - Regular IAT address scan finds nothing (real addresses aren't there yet)
  - Security software hooks the real functions after they're first resolved

Fix: parse the Delay Import Directory (data directory index 13), find the
two functions by name in the delay-load INT, and overwrite the corresponding
delay-load IAT entries with our no-op stubs.  Doing this before QApplication
means the delay-load thunk (jmp [iat_entry]) jumps straight to our stub the
first time Qt calls either function, bypassing the hooked implementation.

All memory reads use ReadProcessMemory so a bad address returns None instead
of a C-level ACCESS_VIOLATION that Python try/except cannot catch.

Call apply() AFTER importing PyQt6 (loads Qt6Gui.dll) but BEFORE QApplication.
"""
from __future__ import annotations
import ctypes
import struct
import sys
import logging

_log = logging.getLogger(__name__)
_STUBS: list = []


# ── safe memory read ──────────────────────────────────────────────────────────

def _rpmem(proc: int, addr: int, size: int) -> bytes | None:
    """ReadProcessMemory wrapper — returns None on failure, never crashes."""
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


# ── IAT entry patcher ─────────────────────────────────────────────────────────

def _patch_iat_entry(iat_addr: int, ptr_size: int,
                     stub_addr: int, fn_name: bytes) -> bool:
    """VirtualProtect → write stub_addr → restore protection. Returns success."""
    old_prot = ctypes.c_uint32(0)
    PAGE_READWRITE = 0x04
    if not ctypes.windll.kernel32.VirtualProtect(
            ctypes.c_void_p(iat_addr), ptr_size,
            PAGE_READWRITE, ctypes.byref(old_prot)):
        _log.warning("_fix_win_ole: VirtualProtect failed for %s", fn_name.decode())
        return False
    cur_rpmem = _rpmem(int(ctypes.windll.kernel32.GetCurrentProcess
                          if False else 0), iat_addr, ptr_size)  # unused
    t = ctypes.c_uint64 if ptr_size == 8 else ctypes.c_uint32
    old_val = t.from_address(iat_addr).value
    t.from_address(iat_addr).value = stub_addr
    ctypes.windll.kernel32.VirtualProtect(
        ctypes.c_void_p(iat_addr), ptr_size, old_prot, ctypes.byref(old_prot))
    _log.info("_fix_win_ole: patched %s  0x%x → 0x%x",
              fn_name.decode(), old_val, stub_addr)
    return True


# ── walk an INT/IAT pair, patch matching names ────────────────────────────────

def _walk_and_patch(proc: int, base: int,
                    int_rva: int, iat_rva: int, ptr_size: int,
                    remaining: set[bytes],
                    target_stubs: dict[bytes, int]) -> None:
    """Walk OriginalFirstThunk (INT) for names; patch FirstThunk (IAT) by position."""
    if not int_rva or not iat_rva:
        return
    fmt = '<Q' if ptr_size == 8 else '<I'
    ordinal_bit = (1 << 63) if ptr_size == 8 else (1 << 31)
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
                if _patch_iat_entry(iat_addr, ptr_size,
                                    target_stubs[fn_name], fn_name):
                    remaining.discard(fn_name)
        idx += 1


# ── main entry point ──────────────────────────────────────────────────────────

def apply() -> None:
    if sys.platform != "win32":
        return

    _log.info("_fix_win_ole: apply() starting")

    kernel32 = ctypes.WinDLL("kernel32")
    kernel32.GetModuleHandleW.restype  = ctypes.c_void_p
    kernel32.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
    kernel32.GetCurrentProcess.restype  = ctypes.c_void_p
    kernel32.GetCurrentProcess.argtypes = []

    hmod = kernel32.GetModuleHandleW("Qt6Gui.dll")
    if not hmod:
        _log.warning("_fix_win_ole: Qt6Gui.dll not loaded — skipping")
        return

    proc = kernel32.GetCurrentProcess()
    base = int(hmod)
    _log.info("_fix_win_ole: Qt6Gui.dll base=0x%x", base)

    # ── Build stubs ───────────────────────────────────────────────────────────
    @ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p,
                        ctypes.POINTER(ctypes.c_void_p))
    def _stub_ftm(pUnkOuter, ppunkMarshal):
        if ppunkMarshal:
            ppunkMarshal[0] = None
        return 0  # S_OK

    @ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p)
    def _stub_rdd(hwnd, pDropTarget):
        return 0  # S_OK

    _STUBS.extend([_stub_ftm, _stub_rdd])

    target_stubs: dict[bytes, int] = {
        b"CoCreateFreeThreadedMarshaler":
            ctypes.cast(_stub_ftm, ctypes.c_void_p).value or 0,
        b"RegisterDragDrop":
            ctypes.cast(_stub_rdd, ctypes.c_void_p).value or 0,
    }
    remaining = set(target_stubs.keys())

    # ── Parse DOS → NT headers ────────────────────────────────────────────────
    dos = _rpmem(proc, base, 0x40)
    if not dos or dos[:2] != b'MZ':
        _log.warning("_fix_win_ole: bad DOS header"); return

    e_lfanew = struct.unpack_from('<I', dos, 0x3C)[0]
    if _rpmem(proc, base + e_lfanew, 4) != b'PE\x00\x00':
        _log.warning("_fix_win_ole: bad PE sig"); return

    opt2 = _rpmem(proc, base + e_lfanew + 24, 2)
    if not opt2:
        return
    magic = struct.unpack_from('<H', opt2)[0]
    if magic == 0x010B:      # PE32
        dd_base = e_lfanew + 24 + 0x60
        ptr_size = 4
    elif magic == 0x020B:    # PE32+
        dd_base = e_lfanew + 24 + 0x70
        ptr_size = 8
    else:
        _log.warning("_fix_win_ole: unknown PE magic 0x%04x", magic); return

    # Data directory[N] = dd_base + N*8  →  RVA(4) + Size(4)
    def _dd_rva(idx: int) -> int:
        d = _rpmem(proc, base + dd_base + idx * 8, 4)
        return struct.unpack_from('<I', d)[0] if d else 0

    # ── 1. Regular import directory (index 1) ─────────────────────────────────
    import_rva = _dd_rva(1)
    if import_rva:
        desc_off = import_rva
        while remaining:
            desc = _rpmem(proc, base + desc_off, 20)
            if not desc:
                break
            orig, _, _, name_rva, first = struct.unpack_from('<IIIII', desc)
            if orig == 0 and name_rva == 0:
                break
            dll = _cstr(proc, base + name_rva, 64).lower()
            _log.debug("_fix_win_ole: import  %s  INT=0x%x IAT=0x%x", dll, orig, first)
            _walk_and_patch(proc, base, orig, first, ptr_size, remaining, target_stubs)
            desc_off += 20

    if not remaining:
        _log.info("_fix_win_ole: done via regular imports, remaining=0")
        return

    # ── 2. Delay import directory (index 13) ──────────────────────────────────
    # Qt6Gui.dll delay-loads CoCreateFreeThreadedMarshaler and RegisterDragDrop.
    # The delay-load IAT initially holds __delayLoadHelper2 addresses (not the
    # real function addresses), so address-based scans find nothing.
    # We patch by name through the delay-load INT instead.
    delay_rva = _dd_rva(13)
    _log.info("_fix_win_ole: delay-import dir RVA=0x%x", delay_rva)

    if delay_rva:
        desc_off = delay_rva
        while remaining:
            # IMAGE_DELAYLOAD_DESCRIPTOR = 8 DWORDs = 32 bytes
            desc = _rpmem(proc, base + desc_off, 32)
            if not desc:
                break
            (attrs, dll_name_rva, _hmod, iat_rva,
             int_rva, _biat, _uiat, _ts) = struct.unpack_from('<8I', desc)
            if dll_name_rva == 0 and iat_rva == 0:
                break  # null terminator

            dll = _cstr(proc, base + dll_name_rva, 64).lower()
            _log.info("_fix_win_ole: delay   %s  INT=0x%x IAT=0x%x attrs=0x%x",
                      dll, int_rva, iat_rva, attrs)
            _walk_and_patch(proc, base, int_rva, iat_rva,
                            ptr_size, remaining, target_stubs)
            desc_off += 32

    for fn in remaining:
        _log.warning("_fix_win_ole: FAILED to patch %s", fn.decode())

    _log.info("_fix_win_ole: done, remaining=%d", len(remaining))
