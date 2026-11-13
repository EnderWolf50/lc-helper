"""lc-helper's windows kept just above the game's in the z-order: in front of the game, behind what is in front of it.

Windows raises a window of a process that is not in the foreground only into the topmost band; HWND_TOP from the
background leaves the z-order as it was (MaaFramework source/MaaWin32ControlUnit/Input/AnchoredTouchInput.cpp, its
comment on HWND_TOP). So a window goes to the top of the normal band by HWND_TOPMOST then HWND_NOTOPMOST, as
MaaFramework's ForegroundUtils.h does, and right above a game that is not on top by going after the window above it.
"""

import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32")
user32.GetWindow.restype = user32.GetAncestor.restype = wintypes.HWND
user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                wintypes.UINT]
WinEventProc = ctypes.WINFUNCTYPE(None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND, wintypes.LONG, wintypes.LONG,
                                  wintypes.DWORD, wintypes.DWORD)
user32.SetWinEventHook.restype = wintypes.HANDLE
user32.SetWinEventHook.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.HMODULE, WinEventProc, wintypes.DWORD,
                                   wintypes.DWORD, wintypes.DWORD]
user32.UnhookWinEvent.argtypes = [wintypes.HANDLE]

GW_HWNDPREV, GA_ROOT = 3, 2
GWL_EXSTYLE, WS_EX_TOPMOST = -20, 0x0008
HWND_TOPMOST, HWND_NOTOPMOST = -1, -2
STILL = 0x0001 | 0x0002 | 0x0010 | 0x0200  # SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_NOOWNERZORDER
EVENT_SYSTEM_FOREGROUND = 0x0003
WINEVENT_OUTOFCONTEXT, WINEVENT_SKIPOWNPROCESS = 0x0000, 0x0002


class Win32:
    """The z-order as Windows keeps it."""

    def above(self, hwnd):
        return user32.GetWindow(hwnd, GW_HWNDPREV)

    def topmost(self, hwnd):
        return bool(user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOPMOST)

    def put(self, hwnd, after):
        user32.SetWindowPos(hwnd, after, 0, 0, 0, 0, STILL)


def place_above(hwnd, game, ours=(), z=None):
    """hwnd just above game, not activated: on top of every window only while game is. ours are lc-helper's other
    windows, which may sit between them already."""
    z = z or Win32()
    above = z.above(game)
    while above and above in ours:
        above = z.above(above)
    if above == hwnd:
        return
    if not above or z.topmost(above):  # game tops the normal band: hwnd goes to its top
        z.put(hwnd, HWND_TOPMOST)
        z.put(hwnd, HWND_NOTOPMOST)
    else:
        z.put(hwnd, above)


def root(hwnd):
    """The top-level window hwnd is part of: what comes to the foreground."""
    return user32.GetAncestor(hwnd, GA_ROOT) if hwnd else None


class Foreground:
    """Calls on_change(hwnd) each time a window of another process comes to the foreground, on the thread that made
    it, which must run a message loop (Qt's)."""

    def __init__(self, on_change):
        self.proc = WinEventProc(lambda hook, event, hwnd, *_: self.told(on_change, hwnd))  # kept: Windows calls it
        self.hook = user32.SetWinEventHook(EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_FOREGROUND, None, self.proc, 0, 0,
                                           WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS)

    @staticmethod
    def told(on_change, hwnd):
        try:
            on_change(hwnd)
        except Exception as e:  # an exception cannot cross back into Windows' call
            print(f"lc-helper: following the game failed: {e}")

    def close(self):
        if self.hook:
            user32.UnhookWinEvent(self.hook)
            self.hook = None
