import re

from lc_helper.paths import ROOT

PIN = ROOT / ".github/maalc-commit"


def test_the_pinned_maalc_commit_is_one_full_sha():
    """CI checks out this commit of maalc for tests/screens; the file holds nothing else, so moving it is a one-line edit."""
    lines = PIN.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert re.fullmatch(r"[0-9a-f]{40}", lines[0])
