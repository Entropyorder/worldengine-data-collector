"""
IAT-patch CoCreateFreeThreadedMarshaler and RegisterDragDrop in Qt6Gui.dll.

Qt unconditionally registers every top-level window as an OLE drop target.
On machines with Chinese security/IME software that hooks COM (360, Tencent
Security, Sogou IME, etc.), the QWindowsOleDropTarget constructor crashes
inside CoCreateFreeThreadedMarshaler or RegisterDragDrop.

Strategy: locate IAT entries by PE name (position-based, not value-based).
This works even when security software has already replaced IAT entries with
their own hook addresses — we overwrite whatever is there with our stub.

All memory reads use ReadProcessMemory so bad addresses return None instead
of causing a C-level ACCESS_VIOLATION (which Python try/except cannot catch).

Call apply() AFTER importing PyQt6 (loads Qt6Gui.dll) but BEFORE QApplication.
"""
from __future__ import annotations
import ctypes
import struct
import sys
import logging

_log = logging.getLogger(__name__)
_STUBS: list = []


def _rpmem(proc: int, addr: int, size: int) -> bytes | None:
    """ReadProcessMemory wrapper — returns None on any failure, never crashes."""
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


def _read_cstr(proc: int, addr: int, maxlen: int = 128) -> bytes:
    """Read a null-terminated byte string via ReadProcessMemory."""
    data = _rpmem(proc, addr, maxlen)
    if not data:
        return b""
    return data.split(b"\x00")[0]


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
    @ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
    def _stub_ftm(pUnkOuter, ppunkMarshal):
        if ppunkMarshal:
            ppunkMarshal[0] = None
        return 0  # S_OK

    @ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p)
    def _stub_rdd(hwnd, pDropTarget):
        return 0  # S_OK

    _STUBS.extend([_stub_ftm, _stub_rdd])

    target_stubs: dict[bytes, int] = {
        b"CoCreateFreeThreadedMarshaler": ctypes.cast(_stub_ftm, ctypes.c_void_p).value or 0,
        b"RegisterDragDrop":              ctypes.cast(_stub_rdd, ctypes.c_void_p).value or 0,
    }
    remaining = set(target_stubs.keys())

    # ── Parse DOS → PE ────────────────────────────────────────────────────────
    dos = _rpmem(proc, base, 0x40)
    if not dos or dos[:2] != b'MZ':
        _log.warning("_fix_win_ole: invalid DOS header")
        return

    e_lfanew = struct.unpack_from('<I', dos, 0x3C)[0]
    if _rpmem(proc, base + e_lfanew, 4) != b'PE\x00\x00':
        _log.warning("_fix_win_ole: invalid PE signature")
        return

    # Optional header: e_lfanew+24; magic tells us PE32 vs PE32+
    opt2 = _rpmem(proc, base + e_lfanew + 24, 2)
    if not opt2:
        return
    magic = struct.unpack_from('<H', opt2)[0]
    if magic == 0x010B:      # PE32  (32-bit)
        import_dd_off = e_lfanew + 24 + 0x68
        ptr_size = 4
    elif magic == 0x020B:    # PE32+ (64-bit)
        import_dd_off = e_lfanew + 24 + 0x78
        ptr_size = 8
    else:
        _log.warning("_fix_win_ole: unknown PE magic 0x%04x", magic)
        return

    idd = _rpmem(proc, base + import_dd_off, 8)
    if not idd:
        return
    import_rva = struct.unpack_from('<I', idd)[0]
    if not import_rva:
        _log.warning("_fix_win_ole: no import directory")
        return

    fmt_ptr = '<Q' if ptr_size == 8 else '<I'
    PAGE_READWRITE = 0x04

    # ── Walk all IMAGE_IMPORT_DESCRIPTORs (20 bytes each) ────────────────────
    desc_rva = import_rva
    while remaining:
        desc = _rpmem(proc, base + desc_rva, 20)
        if not desc:
            break
        orig_thunk_rva, _, _, name_rva, first_thunk_rva = struct.unpack_from('<IIIII', desc)
        if orig_thunk_rva == 0 and name_rva == 0:
            break  # null terminator

        dll_name = _read_cstr(proc, base + name_rva, 64).lower()
        _log.debug("_fix_win_ole: import DLL=%s orig=0x%x iat=0x%x",
                   dll_name, orig_thunk_rva, first_thunk_rva)

        # Use INT (OriginalFirstThunk) for name lookup — it always has RVAs to
        # IMAGE_IMPORT_BY_NAME, unlike FirstThunk which holds resolved addresses.
        # If INT is missing (rare, bound import), we cannot do name-based lookup
        # for this descriptor — skip it.
        if not orig_thunk_rva:
            _log.debug("_fix_win_ole: %s has no INT, skipping name lookup", dll_name)
            desc_rva += 20
            continue

        idx = 0
        while remaining:
            int_entry = _rpmem(proc, base + orig_thunk_rva + idx * ptr_size, ptr_size)
            if not int_entry:
                break
            thunk_val = struct.unpack_from(fmt_ptr, int_entry)[0]
            if thunk_val == 0:
                break  # end of this DLL's import list

            ordinal_bit = (1 << 63) if ptr_size == 8 else (1 << 31)
            if not (thunk_val & ordinal_bit):
                # IMAGE_IMPORT_BY_NAME: 2-byte Hint then null-terminated name
                ibn_rva = thunk_val & (ordinal_bit - 1)
                fn_name = _read_cstr(proc, base + ibn_rva + 2, 64)
                if fn_name in remaining:
                    # Found it — patch FirstThunk[idx] regardless of current value
                    iat_addr = base + first_thunk_rva + idx * ptr_size
                    iat_cur = _rpmem(proc, iat_addr, ptr_size)
                    cur_val = struct.unpack_from(fmt_ptr, iat_cur)[0] if iat_cur else 0
                    stub_addr = target_stubs[fn_name]
                    old_prot = ctypes.c_uint32(0)
                    if ctypes.windll.kernel32.VirtualProtect(
                            ctypes.c_void_p(iat_addr), ptr_size,
                            PAGE_READWRITE, ctypes.byref(old_prot)):
                        # from_address is safe: page just made writable
                        t = ctypes.c_uint64 if ptr_size == 8 else ctypes.c_uint32
                        t.from_address(iat_addr).value = stub_addr
                        ctypes.windll.kernel32.VirtualProtect(
                            ctypes.c_void_p(iat_addr), ptr_size,
                            old_prot, ctypes.byref(old_prot))
                        _log.info("_fix_win_ole: patched %s (was 0x%x → 0x%x) dll=%s",
                                  fn_name.decode(), cur_val, stub_addr, dll_name.decode())
                        remaining.discard(fn_name)
                    else:
                        _log.warning("_fix_win_ole: VirtualProtect failed for %s",
                                     fn_name.decode())
            idx += 1

        desc_rva += 20

    # ── Fallback: address-based scan if name-based missed anything ────────────
    if remaining:
        _log.info("_fix_win_ole: name-based missed %s, trying address scan",
                  [n.decode() for n in remaining])
        _address_scan_fallback(proc, base, remaining, target_stubs)

    for fn_name in remaining:
        _log.warning("_fix_win_ole: FAILED to patch %s", fn_name.decode())

    _log.info("_fix_win_ole: done, remaining=%d", len(remaining))


def _address_scan_fallback(proc: int, base: int,
                           remaining: set[bytes],
                           target_stubs: dict[bytes, int]) -> None:
    """Scan Qt6Gui.dll pages for the real function addresses as a fallback."""
    ole32 = ctypes.WinDLL("ole32.dll")
    addr_to_name: dict[int, bytes] = {}
    for fn_name in list(remaining):
        try:
            real = ctypes.cast(getattr(ole32, fn_name.decode()), ctypes.c_void_p).value
            if real:
                addr_to_name[real] = fn_name
                _log.info("_fix_win_ole: fallback target %s @ 0x%x", fn_name.decode(), real)
        except Exception as e:
            _log.warning("_fix_win_ole: cannot resolve %s: %s", fn_name.decode(), e)

    if not addr_to_name:
        return

    # Read SizeOfImage
    dos = _rpmem(proc, base, 0x40)
    size_of_image = 32 * 1024 * 1024
    if dos and dos[:2] == b'MZ':
        e_lfanew = struct.unpack_from('<I', dos, 0x3C)[0]
        opt = _rpmem(proc, base + e_lfanew + 24, 0x40)
        if opt and len(opt) >= 0x3A:
            size_of_image = struct.unpack_from('<I', opt, 0x38)[0]

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

    PAGE_READWRITE = 0x04
    MEM_COMMIT     = 0x1000
    offset = 0

    while offset < size_of_image and addr_to_name:
        mbi = _MBI()
        if not ctypes.windll.kernel32.VirtualQuery(
                ctypes.c_void_p(base + offset), ctypes.byref(mbi), ctypes.sizeof(mbi)):
            offset += 0x1000
            continue
        region = int(mbi.RegionSize)
        prot   = mbi.Protect
        readable = (mbi.State == MEM_COMMIT) and prot not in (0, 1) and not (prot & 0x100)
        if readable:
            scan_len = min(region, size_of_image - offset)
            data = _rpmem(proc, base + offset, scan_len)
            if data:
                for off in range(0, len(data) - 7, 8):
                    val = struct.unpack_from('<Q', data, off)[0]
                    if val in addr_to_name:
                        fn_name = addr_to_name[val]
                        scan_addr = base + offset + off
                        stub_addr = target_stubs[fn_name]
                        old_prot = ctypes.c_uint32(0)
                        if ctypes.windll.kernel32.VirtualProtect(
                                ctypes.c_void_p(scan_addr), 8,
                                PAGE_READWRITE, ctypes.byref(old_prot)):
                            ctypes.c_uint64.from_address(scan_addr).value = stub_addr
                            ctypes.windll.kernel32.VirtualProtect(
                                ctypes.c_void_p(scan_addr), 8,
                                old_prot, ctypes.byref(old_prot))
                            _log.info("_fix_win_ole: fallback patched %s at +0x%x",
                                      fn_name.decode(), offset + off)
                            remaining.discard(fn_name)
                            del addr_to_name[val]
        offset += max(region, 0x1000)
