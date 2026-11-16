"""The resource package seam: lock file, sync into a folder (src/lc_helper/package.py).

The server is a dict of url -> bytes behind the `fetch` argument, so no test touches the network.
"""

import json
import re
import threading
import time

import pytest
from package_server import LICENCES, SOURCE, Server, serve

from lc_helper import package
from lc_helper.paths import ROOT


def only_icons_and_table(path):
    return path.startswith("data/gift_icons/") or path == "data/event_table.json"


def only_icons_and_table_and_start(path):
    return only_icons_and_table(path) or path == "image/Battle/BattleStart.png"


def listing(dest):
    return sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file() and p.name not in LICENCES)


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


def test_newest_reads_the_manifest_of_main():
    served = serve("2026.1.5")
    served[f"{SOURCE}/main/manifest.json"] = served[f"{SOURCE}/2026.1.5/manifest.json"]
    found = package.newest(SOURCE, fetch=Server(served))
    assert found["version"] == "2026.1.5" and found["format"] == package.FORMAT


@pytest.mark.parametrize("body", [b"not json", b"[]", b'{"version": 5, "format": 1, "template": 1, "files": {}}',
                                  b'{"version": "1", "format": "1", "template": 1, "files": {}}',
                                  b'{"version": "1", "format": 1, "template": 1, "files": []}'])
def test_newest_refuses_what_is_not_a_manifest(body):
    with pytest.raises(package.PackageError, match="main/manifest.json"):
        package.newest(SOURCE, fetch=Server({f"{SOURCE}/main/manifest.json": body}))


def test_newest_gives_up_when_the_server_does_not_answer():
    with pytest.raises(package.PackageError, match="main/manifest.json"):
        package.newest(SOURCE, fetch=Server({}))


def test_newest_stops_waiting_after_its_deadline():
    release = threading.Event()

    def hangs(url):
        release.wait(5)
        return b"{}"
    try:
        started = time.monotonic()
        with pytest.raises(package.PackageError, match="timed out"):
            package.newest(SOURCE, fetch=hangs, seconds=0.2)
        assert time.monotonic() - started < 2
    finally:
        release.set()


def test_versions_compare_as_numbers_not_text():
    key = package.version_key
    assert key("2026.11.16") < key("2026.11.16.2") < key("2026.11.17") < key("2026.12.1")
    assert key("2026.9.30") < key("2026.11.2")
    with pytest.raises(package.PackageError):
        key("main")


def test_sync_brings_the_licence_and_notice_the_package_carries(tmp_path):
    package.sync(tmp_path, SOURCE, "2026.1.1", fetch=Server(serve()), wanted=only_icons_and_table)
    assert (tmp_path / "LICENSE").read_bytes() == b"licence of 2026.1.1"
    assert (tmp_path / "NOTICE.md").read_bytes() == b"notice of 2026.1.1"


def test_a_rerun_of_the_same_version_does_not_fetch_the_licence_again(tmp_path):
    package.sync(tmp_path, SOURCE, "2026.1.1", fetch=Server(serve()), wanted=only_icons_and_table)
    again = Server(serve())
    package.sync(tmp_path, SOURCE, "2026.1.1", fetch=again, wanted=only_icons_and_table)
    assert [u for u in again.requests if u.endswith(LICENCES)] == []


def test_another_version_brings_its_own_licence_and_a_lost_one_is_fetched_again(tmp_path):
    package.sync(tmp_path, SOURCE, "2026.1.1", fetch=Server(serve()), wanted=only_icons_and_table)
    package.sync(tmp_path, SOURCE, "2026.1.2", fetch=Server(serve("2026.1.2")), wanted=only_icons_and_table)
    assert (tmp_path / "LICENSE").read_bytes() == b"licence of 2026.1.2"
    (tmp_path / "NOTICE.md").unlink()
    package.sync(tmp_path, SOURCE, "2026.1.2", fetch=Server(serve("2026.1.2")), wanted=only_icons_and_table)
    assert (tmp_path / "NOTICE.md").read_bytes() == b"notice of 2026.1.2"


@pytest.mark.parametrize("name", LICENCES)
@pytest.mark.parametrize("body", [b"", None])
def test_an_empty_or_missing_licence_fails_the_sync_and_changes_nothing(tmp_path, name, body):
    package.sync(tmp_path, SOURCE, "2026.1.1", fetch=Server(serve()), wanted=only_icons_and_table)
    newer = serve("2026.1.2", files={"data/event_table.json": b'{"events": [1]}'})
    if body is None:
        del newer[f"{SOURCE}/2026.1.2/{name}"]
    else:
        newer[f"{SOURCE}/2026.1.2/{name}"] = body
    with pytest.raises(package.PackageError, match=name):
        package.sync(tmp_path, SOURCE, "2026.1.2", fetch=Server(newer), wanted=only_icons_and_table)
    assert package.manifest(tmp_path)["version"] == "2026.1.1"
    assert (tmp_path / "LICENSE").read_bytes() == b"licence of 2026.1.1"
    assert (tmp_path / "data/event_table.json").read_bytes() == b'{"events": []}'


def test_a_part_of_a_version_the_program_does_not_know_is_skipped_and_the_other_part_applies(tmp_path):
    package.sync(tmp_path, SOURCE, "2026.1.1", fetch=Server(serve()), wanted=only_icons_and_table_and_start)
    newer = serve("2026.1.2", format=99, files={"data/event_table.json": b'{"events": [1]}',
                                                "image/Battle/BattleStart.png": b"start 2"})
    said = []
    package.sync(tmp_path, SOURCE, "2026.1.2", fetch=Server(newer), wanted=only_icons_and_table_and_start,
                 on_skip=said.append)
    assert (tmp_path / "data/event_table.json").read_bytes() == b'{"events": []}'  # kept, not replaced
    assert (tmp_path / "data/gift_icons/9001.webp").exists()  # nor deleted for being absent from the new manifest
    assert (tmp_path / "image/Battle/BattleStart.png").read_bytes() == b"start 2"
    info = package.manifest(tmp_path)
    assert info["version"] == "2026.1.2" and info["format"] == package.FORMAT and info["template"] == package.TEMPLATE
    assert info["files"]["data/event_table.json"] == json.loads(serve()[f'{SOURCE}/2026.1.1/manifest.json'])["files"]["data/event_table.json"]
    assert len(said) == 1 and "format" in said[0] and "99" in said[0]


def test_a_template_version_the_program_does_not_know_skips_the_images_only(tmp_path):
    package.sync(tmp_path, SOURCE, "2026.1.1", fetch=Server(serve()), wanted=only_icons_and_table_and_start)
    newer = serve("2026.1.2", template=7, files={"data/event_table.json": b'{"events": [1]}',
                                                 "image/Battle/BattleStart.png": b"start 2"})
    package.sync(tmp_path, SOURCE, "2026.1.2", fetch=Server(newer), wanted=only_icons_and_table_and_start,
                 on_skip=lambda line: None)
    assert (tmp_path / "data/event_table.json").read_bytes() == b'{"events": [1]}'
    assert (tmp_path / "image/Battle/BattleStart.png").read_bytes() == b"start"
    assert not (tmp_path / "data/gift_icons/9001.webp").exists()  # the new data part does not list it


def test_a_skipped_part_with_nothing_to_keep_is_refused(tmp_path):
    with pytest.raises(package.PackageError, match="format"):
        package.sync(tmp_path, SOURCE, "2026.1.1", fetch=Server(serve(format=99)), wanted=only_icons_and_table_and_start,
                     on_skip=lambda line: None)
    assert listing(tmp_path) == []
