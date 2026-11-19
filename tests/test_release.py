import zipfile

import pytest

import release

PYPROJECT = '[project]\nname = "lc-helper"\nversion = "0.2.0"\n\n[tool.ruff]\ntarget-version = "py312"\n'


def test_a_version_is_three_numbers():
    release.check_version("0.3.0")
    for bad in ("v0.3.0", "0.3", "0.3.0-rc1", ""):
        with pytest.raises(SystemExit):
            release.check_version(bad)


def test_the_bump_changes_only_the_project_version():
    text = release.bumped(PYPROJECT, "0.3.0")
    assert text == PYPROJECT.replace('version = "0.2.0"', 'version = "0.3.0"')
    assert release.version_of(text) == "0.3.0"


def test_a_pyproject_without_one_version_line_is_refused():
    with pytest.raises(SystemExit):
        release.bumped("[project]\nname = 'x'\n", "0.3.0")


def test_the_zip_leaves_out_the_built_apps_own_settings(tmp_path):
    app = tmp_path / "lc-helper"
    (app / "_internal").mkdir(parents=True)
    (app / "lc-helper.exe").write_bytes(b"exe")
    (app / "_internal/base.dll").write_bytes(b"dll")
    (app / ".local").mkdir()
    (app / ".local/settings.json").write_text("{}")
    out = tmp_path / "out.zip"
    assert release.pack(app, out) == 2
    assert sorted(zipfile.ZipFile(out).namelist()) == ["lc-helper/_internal/base.dll", "lc-helper/lc-helper.exe"]
