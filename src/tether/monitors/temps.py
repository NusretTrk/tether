"""
CPU temp via direct ATKACPI driver calls (same interface G-Helper uses
internally) — standard WMI thermal-zone queries return a fake value on this
board, and MSR-based tools need a legacy kernel driver HVCI blocks. This
route needs neither admin nor HVCI. GPU temp/fan via nvidia-smi. Both ported
unchanged from the original bot.py — already debugged against real hardware.
"""
from __future__ import annotations

import ctypes
import logging
import subprocess

from tether.platform.capabilities import CAPABILITIES

log = logging.getLogger(__name__)

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

if CAPABILITIES.hardware_temps:
    from ctypes import wintypes

_ATK_CONTROL_CODE = 0x0022240C
_ATK_DSTS = 0x53545344
_ATK_INIT = 0x54494E49
_ATK_TEMP_CPU = 0x00120094

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True) if CAPABILITIES.hardware_temps else None
if _kernel32 is not None:
    _kernel32.CreateFileW.restype = wintypes.HANDLE
    _kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
        wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    _kernel32.DeviceIoControl.argtypes = [
        wintypes.HANDLE, wintypes.DWORD,
        wintypes.LPVOID, wintypes.DWORD,
        wintypes.LPVOID, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID,
    ]
    _ATK_INVALID_HANDLE = wintypes.HANDLE(-1).value
else:
    _ATK_INVALID_HANDLE = -1


def _atk_call(handle, method_id: int, args: bytes) -> bytes:
    in_buf = method_id.to_bytes(4, "little") + len(args).to_bytes(4, "little") + args
    in_arr = ctypes.create_string_buffer(in_buf, len(in_buf))
    out_arr = ctypes.create_string_buffer(16)
    bytes_returned = wintypes.DWORD(0)
    ok = _kernel32.DeviceIoControl(
        handle, _ATK_CONTROL_CODE, in_arr, len(in_buf), out_arr, 16,
        ctypes.byref(bytes_returned), None,
    )
    if not ok:
        raise OSError(f"ATKACPI DeviceIoControl failed, error={ctypes.get_last_error()}")
    return out_arr.raw


def get_cpu_temp() -> int | None:
    """ASUS ATKACPI only. Returns None elsewhere, which callers already
    render as "unavailable"."""
    if not CAPABILITIES.hardware_temps:
        return None
    handle = _kernel32.CreateFileW(
        r"\\.\ATKACPI", 0x80000000 | 0x40000000, 1 | 2, None, 3, 0x80, None,
    )
    if handle == _ATK_INVALID_HANDLE:
        log.warning("ATKACPI device unavailable (not an ASUS ACPI board?)")
        return None
    try:
        _atk_call(handle, _ATK_INIT, b"\x00" * 8)
        args = _ATK_TEMP_CPU.to_bytes(4, "little") + (0).to_bytes(4, "little")
        out = _atk_call(handle, _ATK_DSTS, args)
        raw = int.from_bytes(out[0:4], "little", signed=True)
        return raw - 65536
    except Exception as e:
        log.warning("ATKACPI read failed: %s", e)
        return None
    finally:
        _kernel32.CloseHandle(handle)


def get_gpu_temp() -> tuple[float | None, str | None]:
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=temperature.gpu,fan.speed", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=10,
            creationflags=_NO_WINDOW,
        )
        temp_str, fan_str = [p.strip() for p in result.stdout.strip().split(",")]
        return float(temp_str), fan_str
    except Exception as e:
        log.warning("nvidia-smi failed: %s", e)
        return None, None
