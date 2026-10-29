"""Process-local RSS and explicitly device-wide GPU usage for interview benchmarks."""

import ctypes
import os
import subprocess


def process_memory():
    if os.name != "nt":
        return {"rss_bytes": None, "note": "RSS collector implemented for Windows"}
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
            "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
    values = Counters()
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(values), ctypes.sizeof(values)):
        raise ctypes.WinError(ctypes.get_last_error())
    return {"rss_bytes": values.WorkingSetSize, "peak_rss_bytes": values.PeakWorkingSetSize}


def gpu_memory():
    try:
        value = subprocess.check_output(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                                        text=True, timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return {"device_used_mib": [int(line) for line in value.splitlines()],
                "scope": "whole GPU including desktop and other processes; not process VRAM"}
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        return {"device_used_mib": None, "error": str(exc)}
