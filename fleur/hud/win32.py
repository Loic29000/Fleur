"""Accès aux fenêtres Windows (via ctypes, sans dépendance).

Sur un autre système, les fonctions renvoient des valeurs neutres pour que
le reste du programme fonctionne (HUD flottant, tests).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

IS_WINDOWS = sys.platform == "win32"


@dataclass
class WindowInfo:
    hwnd: int
    title: str


@dataclass
class Rect:
    x: int
    y: int
    width: int
    height: int


if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    _EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [_EnumWindowsProc, wintypes.LPARAM]
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    user32.GetForegroundWindow.restype = wintypes.HWND
    _SetWindowLongPtr = getattr(user32, "SetWindowLongPtrW", None) or user32.SetWindowLongW
    _SetWindowLongPtr.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
    _SetWindowLongPtr.restype = ctypes.c_void_p
    GWLP_HWNDPARENT = -8


def list_windows() -> list[WindowInfo]:
    if not IS_WINDOWS:
        return []
    result: list[WindowInfo] = []

    def callback(hwnd, _lparam):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                result.append(WindowInfo(int(hwnd), buf.value))
        return True

    user32.EnumWindows(_EnumWindowsProc(callback), 0)
    return result


def find_table_window(table_name: str, extra: str = "") -> WindowInfo | None:
    """Cherche la fenêtre dont le titre contient le nom de la table."""
    needle = table_name.lower()
    extra = extra.lower()
    matches = [
        w for w in list_windows()
        if needle in w.title.lower() and (not extra or extra in w.title.lower())
        and "fleur" not in w.title.lower()
    ]
    if not matches:
        return None
    # préfère le titre le plus court (évite les fenêtres "Historique - Nice 05 ...")
    return min(matches, key=lambda w: len(w.title))


def is_window(hwnd: int) -> bool:
    return bool(IS_WINDOWS and user32.IsWindow(hwnd))


def is_minimized(hwnd: int) -> bool:
    return bool(IS_WINDOWS and user32.IsIconic(hwnd))


def client_rect(hwnd: int) -> Rect | None:
    """Zone cliente de la fenêtre en pixels physiques écran."""
    if not IS_WINDOWS:
        return None
    rect = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        return None
    origin = wintypes.POINT(0, 0)
    if not user32.ClientToScreen(hwnd, ctypes.byref(origin)):
        return None
    return Rect(origin.x, origin.y, rect.right - rect.left, rect.bottom - rect.top)


def set_owner(child_hwnd: int, owner_hwnd: int) -> bool:
    """Rend `child` propriété de `owner` : il reste au-dessus de la table,
    suit son ordre d'empilement et disparaît quand elle est réduite."""
    if not IS_WINDOWS:
        return False
    _SetWindowLongPtr(child_hwnd, GWLP_HWNDPARENT, owner_hwnd)
    return True
