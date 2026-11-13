from functools import cache

import pytest

from lc_helper import vision
from sync_maalc import maalc_dir


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
