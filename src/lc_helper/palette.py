"""The overlay's colours and its face for numerals, maalc's: the hints on the game read as maalc's settings window does,
a warm near-black ground, bronze frames, amber for what is recommended, teal for a gain and crimson for a loss.

INK is maalc's dark theme (gui/src/index.css, :root), each colour under its custom property's name without the dashes:
--line-2 is INK["line-2"]. The numerals are in Barlow Condensed, as maalc sets them (gui/src/main.tsx).
"""

from functools import cache

from PySide6.QtGui import QFontDatabase

from .paths import ASSETS

INK = {
    "bg": "#120e0b",
    "panel": "#1b1510",
    "raise": "#261e16",
    "line": "#3e3125",
    "line-2": "#7a5e46",  # bronze: frames that must read
    "card-line": "#5a4630",  # a tile's frame
    "fg": "#edcda6",  # the game's button text; maalc's focus ring
    "fg-2": "#d6c6ad",
    "muted": "#ab9a82",
    "accent": "#f0a632",  # amber: selected, wanted
    "accent-ink": "#f6b955",
    "keep": "#4fcab7",
    "bad": "#ff7a68",
}
TEXT_FAMILY = "Microsoft JhengHei UI"
# Barlow Condensed's weights, each the family its file names itself: the 600 one is a family of its own, so a weight
# alone would not reach it (assets/fonts/barlow-condensed, committed).
DISPLAY = {600: "Barlow Condensed SemiBold", 700: "Barlow Condensed"}


@cache
def display_loaded():
    folder = ASSETS / "fonts" / "barlow-condensed"
    return all(QFontDatabase.addApplicationFont(str(folder / f"barlow-condensed-latin-{weight}-normal.ttf")) >= 0
               for weight in DISPLAY)


def display_family(weight=700):
    """maalc's condensed face for numerals at weight (600 or 700), its files registered with Qt the first time; the
    text's family when they do not load. Call it once a QGuiApplication exists."""
    return DISPLAY[weight] if display_loaded() else TEXT_FAMILY
