"""Open the built lc-helper.exe in offline mode (no adb, no game window), and report how long until its window shows,
its private memory, and a screenshot of the window; then close it the way the ✕ button does (WM_CLOSE).

Usage: uv run python tools/exe_check.py [path to lc-helper.exe]   (default dist/lc-helper/lc-helper.exe)
"""

import ctypes
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
user32, k32, psapi = ctypes.WinDLL("user32"), ctypes.WinDLL("kernel32"), ctypes.WinDLL("psapi")
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
k32.OpenProcess.restype = wintypes.HANDLE
WM_CLOSE, PROCESS_QUERY = 0x0010, 0x0400 | 0x0010


def windows_of(pid):
    found = []

    def visit(hwnd, _):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd):
            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            if rect.right - rect.left > 100:
                found.append((hwnd, rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top))
        return True
    user32.EnumWindows(WNDENUMPROC(visit), 0)
    return found


def private_mb(pid):
    sys.path.insert(0, str(ROOT / "tools"))
    from measure_memory import PMC
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
    handle = k32.OpenProcess(PROCESS_QUERY, False, pid)
    pmc = PMC()
    pmc.cb = ctypes.sizeof(PMC)
    psapi.GetProcessMemoryInfo(handle, ctypes.byref(pmc), pmc.cb)
    k32.CloseHandle(handle)
    return pmc.PrivateUsage / 2**20


def main():
    exe = sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "dist/lc-helper/lc-helper.exe")
    result = Path(exe).parent / ".local/self-test.txt"
    result.unlink(missing_ok=True)
    t0 = time.perf_counter()
    code = subprocess.run([exe, "--self-test"], timeout=60).returncode
    print(f"--self-test exit code {code} in {time.perf_counter() - t0:.1f} s:")
    print(result.read_text(encoding="utf-8").strip() if result.is_file() else "  (no result file)")
    t0 = time.perf_counter()
    proc = subprocess.Popen([exe, "--offline"])
    shown = None
    while time.perf_counter() - t0 < 20 and proc.poll() is None:
        if wins := windows_of(proc.pid):
            shown = time.perf_counter() - t0
            break
        time.sleep(0.05)
    if shown is None:
        print(f"no window within 20 s; exit code {proc.poll()}")
        proc.kill()
        return
    print(f"window shown {shown:.2f} s after start: {wins[0][1:]}")
    time.sleep(8)
    print(f"private memory 8 s later: {private_mb(proc.pid):.0f} MB")
    hwnd = windows_of(proc.pid)[0][0]
    print(snapshot(hwnd))
    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
    try:
        print(f"closed, exit code {proc.wait(10)}")
    except subprocess.TimeoutExpired:
        proc.kill()
        print(f"did not close within 10 s (window still visible: {bool(user32.IsWindowVisible(hwnd))}); killed")


def snapshot(hwnd):
    """The window's own pixels (MaaFramework's background capture of that one window), never the screen around it."""
    import cv2
    from maa.controller import Win32Controller
    from maa.define import MaaWin32InputMethodEnum, MaaWin32ScreencapMethodEnum

    ctl = Win32Controller(hwnd, MaaWin32ScreencapMethodEnum.PrintWindow, MaaWin32InputMethodEnum.PostMessage,
                          MaaWin32InputMethodEnum.PostMessage)
    ctl.set_screenshot_use_raw_size(True)
    ctl.post_connection().wait()
    image = ctl.post_screencap().wait().get()
    out = ROOT / ".local/evidence/exe-offline.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(cv2.imencode(".png", image)[1].tobytes())
    return out


if __name__ == "__main__":
    main()
