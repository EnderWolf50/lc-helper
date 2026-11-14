from functools import cache

import pytest
from PySide6.QtGui import QFontDatabase, QGuiApplication

from lc_helper import palette, vision
from sync_maalc import maalc_dir


@pytest.fixture(autouse=True)
def no_application_fonts():
    """Each test starts with the offscreen platform's own fonts, which are none: the overlay registers maalc's face
    (palette.display_family), and with no other font there it would stand in for every family, the window's too."""
    yield
    if QGuiApplication.instance():
        palette.display_loaded.cache_clear()
        QFontDatabase.removeAllApplicationFonts()


@pytest.fixture(scope="session")
def screens():
    """maalc's tests/screens: 1280x720 live captures of every game screen maalc reads."""
    try:
        folder = maalc_dir() / "tests/screens"
    except SystemExit as e:
        pytest.skip(str(e))
    return folder


@cache
def _load(path):
    return vision.imread(path)


@pytest.fixture(scope="session")
def screen(screens):
    return lambda name: _load(screens / name).copy()
