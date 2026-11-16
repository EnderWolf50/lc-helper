"""The resource package seam: lock file, sync into a folder (src/lc_helper/package.py).

The server is a dict of url -> bytes behind the `fetch` argument, so no test touches the network.
"""

import hashlib
import json
import re

import pytest

from lc_helper import package
from lc_helper.paths import ROOT

SOURCE = "https://example.test/pkg"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def serve(version="2026.1.1", files=None, **manifest):
    """A fake server holding one package: {url: bytes} plus the manifest of its files."""
    files = files or {
        "data/event_table.json": b'{"events": []}',
        "data/gift_icons/9001.webp": b"gift-icon",
        "data/gift_icons/9002.webp": b"another-icon",
        "data/theme_packs.yaml": b"lc-helper never reads this",
        "image/Battle/BattleStart.png": b"start",
        "image/Map/Unused.png": b"unused",
    }
    body = {"version": version, "client": "9.9.9", "format": package.FORMAT, "template": package.TEMPLATE,
            "sources": [SOURCE], **manifest,
            "files": {p: {"size": len(d), "sha256": sha(d)} for p, d in sorted(files.items())}}
    served = {f"{SOURCE}/{version}/{p}": d for p, d in files.items()}
    served[f"{SOURCE}/{version}/manifest.json"] = json.dumps(body).encode()
    return served


class Server:
    def __init__(self, served):
        self.served, self.requests = served, []

    def __call__(self, url):
        self.requests.append(url)
        if url not in self.served:
            raise OSError(f"404 {url}")
        return self.served[url]

    def files(self):
        return [u for u in self.requests if not u.endswith("manifest.json")]


def only_icons_and_table(path):
    return path.startswith("data/gift_icons/") or path == "data/event_table.json"


def listing(dest):
    return sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file())


def test_sync_downloads_the_manifest_and_only_the_wanted_files(tmp_path):
    server = Server(serve())
    package.sync(tmp_path, SOURCE, "2026.1.1", fetch=server, wanted=only_icons_and_table)
    assert listing(tmp_path) == ["data/event_table.json", "data/gift_icons/9001.webp", "data/gift_icons/9002.webp",
                                 "manifest.json"]
    assert (tmp_path / "data/gift_icons/9001.webp").read_bytes() == b"gift-icon"
    assert package.manifest(tmp_path)["version"] == "2026.1.1"


def test_a_rerun_downloads_no_file(tmp_path):
    package.sync(tmp_path, SOURCE, "2026.1.1", fetch=Server(serve()), wanted=only_icons_and_table)
    again = Server(serve())
    package.sync(tmp_path, SOURCE, "2026.1.1", fetch=again, wanted=only_icons_and_table)
    assert again.files() == []


def test_a_rerun_repairs_a_file_that_is_cut_short_or_gone(tmp_path):
    package.sync(tmp_path, SOURCE, "2026.1.1", fetch=Server(serve()), wanted=only_icons_and_table)
    (tmp_path / "data/gift_icons/9001.webp").write_bytes(b"gift")
    (tmp_path / "data/event_table.json").unlink()
    again = Server(serve())
    package.sync(tmp_path, SOURCE, "2026.1.1", fetch=again, wanted=only_icons_and_table)
    assert (tmp_path / "data/gift_icons/9001.webp").read_bytes() == b"gift-icon"
    assert (tmp_path / "data/event_table.json").read_bytes() == b'{"events": []}'
    assert sorted(u.rsplit("/", 1)[1] for u in again.files()) == ["9001.webp", "event_table.json"]


def test_a_file_that_fails_its_hash_leaves_nothing_behind(tmp_path):
    served = serve()
    served[f"{SOURCE}/2026.1.1/data/gift_icons/9002.webp"] = b"tampered!!!!"  # same size as the real file
    with pytest.raises(package.PackageError, match="9002.webp"):
        package.sync(tmp_path, SOURCE, "2026.1.1", fetch=Server(served), wanted=only_icons_and_table)
    assert listing(tmp_path) == []


def test_a_failed_update_keeps_the_files_of_the_version_in_use(tmp_path):
    package.sync(tmp_path, SOURCE, "2026.1.1", fetch=Server(serve()), wanted=only_icons_and_table)
    newer = serve("2026.1.2", files={"data/event_table.json": b'{"events": [1]}', "data/gift_icons/9001.webp": b"new"})
    del newer[f"{SOURCE}/2026.1.2/data/gift_icons/9001.webp"]  # the download dies half way
    with pytest.raises(package.PackageError):
        package.sync(tmp_path, SOURCE, "2026.1.2", fetch=Server(newer), wanted=only_icons_and_table)
    assert package.manifest(tmp_path)["version"] == "2026.1.1"
    assert (tmp_path / "data/event_table.json").read_bytes() == b'{"events": []}'
    assert listing(tmp_path) == ["data/event_table.json", "data/gift_icons/9001.webp", "data/gift_icons/9002.webp",
                                 "manifest.json"]


def test_another_version_replaces_changed_files_and_drops_the_ones_it_no_longer_has(tmp_path):
    package.sync(tmp_path, SOURCE, "2026.1.1", fetch=Server(serve()), wanted=only_icons_and_table)
    newer = serve("2026.1.2", files={"data/event_table.json": b'{"events": [1]}',
                                     "data/gift_icons/9001.webp": b"gift-icon"})
    server = Server(newer)
    package.sync(tmp_path, SOURCE, "2026.1.2", fetch=server, wanted=only_icons_and_table)
    assert listing(tmp_path) == ["data/event_table.json", "data/gift_icons/9001.webp", "manifest.json"]
    assert (tmp_path / "data/event_table.json").read_bytes() == b'{"events": [1]}'
    assert [u.rsplit("/", 1)[1] for u in server.files()] == ["event_table.json"]  # the icon is the same file
    assert package.manifest(tmp_path)["version"] == "2026.1.2"


def test_a_manifest_of_another_version_than_asked_is_refused(tmp_path):
    served = serve("2026.1.1")
    served[f"{SOURCE}/2026.1.3/manifest.json"] = served[f"{SOURCE}/2026.1.1/manifest.json"]
    with pytest.raises(package.PackageError, match="2026.1.3"):
        package.sync(tmp_path, SOURCE, "2026.1.3", fetch=Server(served), wanted=only_icons_and_table)


@pytest.mark.parametrize("field", ["format", "template"])
def test_a_package_of_a_version_the_program_does_not_know_is_refused(tmp_path, field):
    served = serve(**{field: 99})
    with pytest.raises(package.PackageError, match=field):
        package.sync(tmp_path, SOURCE, "2026.1.1", fetch=Server(served), wanted=only_icons_and_table)
    assert listing(tmp_path) == []


def test_a_path_that_leaves_the_folder_is_refused(tmp_path):
    served = serve(files={"data/../../evil.json": b"x"})
    with pytest.raises(package.PackageError, match="evil"):
        package.sync(tmp_path / "pkg", SOURCE, "2026.1.1", fetch=Server(served), wanted=lambda p: True)
    assert not (tmp_path / "evil.json").exists()


def test_lc_helper_wants_what_it_reads_and_nothing_of_the_pipeline():
    wanted = package.used
    assert wanted("data/event_text.json") and wanted("data/gift_icons/9001.webp")
    assert wanted("data/keyword_icons/Burn.webp") and wanted("data/stagger_word.png")
    assert wanted("image/Battle/BattleTurn.png") and wanted("image/Screen/DialogButton.png")
    assert wanted("data/sin_icons/Envy.png") and wanted("data/gift_slot/plate.png")
    assert not wanted("pipeline/mirror_dungeon.json") and not wanted("image/GiftSearch/x.png")


def test_the_lock_names_one_version_and_one_source():
    lock = package.read_lock(ROOT / "resource.lock.json")
    assert re.fullmatch(r"\d{4}\.\d{2}\.\d{2}(\.\d+)?", lock["version"])
    assert lock["source"].startswith("https://raw.githubusercontent.com/")


def test_a_lock_without_a_version_is_refused(tmp_path):
    (tmp_path / "lock.json").write_text('{"source": "https://x"}', encoding="utf-8")
    with pytest.raises(package.PackageError, match="version"):
        package.read_lock(tmp_path / "lock.json")
