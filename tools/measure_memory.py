"""Private memory of the real lc-helper window 8 s after it shows (maalc ADR 0009's measure), with no emulator.

Usage: uv run python tools/measure_memory.py [ui-only]   ui-only skips loading MaaFramework's OCR

The worker is launch_check's: its scan and connect never reach adb. Without ui-only, the startup OCR warm-up runs
as usual, so the number includes MaaFramework and the OCR model.
"""

import ctypes
import sys
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from PySide6.QtCore import QTimer  # noqa: E402

from lc_helper import app as ui  # noqa: E402
import launch_check  # noqa: E402


class PMC(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
        (n, ctypes.c_size_t) for n in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                                       "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage",
                                       "PagefileUsage", "PeakPagefileUsage", "PrivateUsage")]


def memory_mb():
    """(private, working set) of this process in MB."""
    k32, psapi = ctypes.WinDLL("kernel32"), ctypes.WinDLL("psapi")
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
    pmc = PMC()
    pmc.cb = ctypes.sizeof(PMC)
    assert psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb)
    return pmc.PrivateUsage / 2**20, pmc.WorkingSetSize / 2**20


class Measured(launch_check.Watched):
    def do_warm(self):
        if "ui-only" not in sys.argv:
            super().do_warm()


def main():
    real_show = ui.Window.show

    def show(self):
        real_show(self)

        def report():
            private, ws = memory_mb()
            print(f"{'ui-only' if 'ui-only' in sys.argv else 'ui+ocr'}: private {private:.0f} MB, "
                  f"working set {ws:.0f} MB, 8 s after the window showed", flush=True)
            self.close()
        QTimer.singleShot(8000, report)

    ui.Window.show = show
    ui.main(worker_factory=Measured)


if __name__ == "__main__":
    main()
