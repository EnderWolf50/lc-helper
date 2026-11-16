"""Which resource package a start uses, and the update it checks for (src/lc_helper/startup.py).

The packages are folders in tmp_path, the server a dict behind `fetch` (tests/package_server.py): no test touches the
network, and no test reads the real .local.
"""

import json
import threading
import time

import pytest
from package_server import SOURCE, Server, serve

from lc_helper import package, paths, startup

EVERYTHING = {
    "data/event_table.json": b'{"events": []}',
    "data/gift_icons/9001.webp": b"gift-icon",
    "image/Battle/BattleStart.png": b"start",
}


def install(folder, version="2026.1.1", files=None, **manifest):
    """A package of `version` in folder, as the build's fetch_resource leaves it."""
    served = serve(version, files=files or EVERYTHING, **manifest)
    package.sync(folder, SOURCE, version, fetch=Server(served), wanted=lambda p: True)
    return folder


def publish(version, files=None, **manifest):
    """The server after maalc-resource published `version`: main's manifest is that version's."""
    served = serve(version, files=files or EVERYTHING, **manifest)
    served[f"{SOURCE}/main/manifest.json"] = served[f"{SOURCE}/{version}/manifest.json"]
    return Server(served)


@pytest.fixture
def where(tmp_path):
    class Where:
        bundled = tmp_path / "bundled"
        downloaded = tmp_path / "local" / "resource"
        lines = []

        def run(self, server, offline=False, **kwargs):
            self.lines.clear()
            return startup.run(offline=offline, bundled=self.bundled, downloaded=self.downloaded, fetch=server,
                               log=self.lines.append, **kwargs)

        def version(self, folder):
            return package.manifest(folder)["version"]

    return Where()


def test_offline_the_bundled_package_is_used_and_nothing_is_fetched(where):
    install(where.bundled)
    server = publish("2026.1.2")
    assert where.run(server, offline=True) == where.bundled
    assert server.requests == []
    assert not where.downloaded.exists()
    assert len(where.lines) == 1 and "2026.1.1" in where.lines[0] and "bundled" in where.lines[0]


def test_a_newer_package_is_downloaded_checked_and_used(where):
    install(where.bundled)
    server = publish("2026.1.2", files={**EVERYTHING, "data/event_table.json": b'{"events": [1]}'})
    assert where.run(server) == where.downloaded
    assert where.version(where.downloaded) == "2026.1.2"
    assert (where.downloaded / "data/event_table.json").read_bytes() == b'{"events": [1]}'
    assert (where.downloaded / "data/gift_icons/9001.webp").read_bytes() == b"gift-icon"
    assert (where.downloaded / "LICENSE").read_bytes() == b"licence of 2026.1.2"
    assert [u.rsplit("/", 1)[1] for u in server.files()] == ["event_table.json"]  # the rest was the bundled files
    assert where.version(where.bundled) == "2026.1.1"  # the bundled copy is never written to
    assert "2026.1.1" in " ".join(where.lines) and "2026.1.2" in " ".join(where.lines)


def test_the_same_or_an_older_remote_changes_nothing(where):
    install(where.bundled, "2026.1.2")
    for remote in ("2026.1.2", "2026.1.1"):
        server = publish(remote)
        assert where.run(server) == where.bundled
        assert server.files() == [] and not where.downloaded.exists()


def test_a_second_publish_of_a_day_is_newer_than_the_first(where):
    install(where.bundled, "2026.1.1")
    assert where.run(publish("2026.1.1.2")) == where.downloaded


def test_the_downloaded_package_is_used_while_it_is_newer_than_the_bundled_one(where):
    install(where.bundled, "2026.1.1")
    install(where.downloaded, "2026.1.3")
    server = publish("2026.1.3")
    assert where.run(server) == where.downloaded
    assert server.files() == []


def test_a_new_lc_helper_with_a_newer_bundled_package_leaves_the_old_download_behind(where):
    install(where.bundled, "2026.2.1")
    install(where.downloaded, "2026.1.3")
    assert where.run(publish("2026.2.1")) == where.bundled


def test_the_next_season_replaces_the_download_with_one_built_on_the_newest_copy(where):
    install(where.bundled, "2026.1.1")
    install(where.downloaded, "2026.1.2", files={**EVERYTHING, "data/gift_icons/9002.webp": b"old only"})
    assert where.run(publish("2026.1.3")) == where.downloaded
    assert where.version(where.downloaded) == "2026.1.3"
    assert not (where.downloaded / "data/gift_icons/9002.webp").exists()
    assert sorted(p.name for p in where.downloaded.parent.iterdir()) == ["resource"]  # no staging copy left


@pytest.mark.parametrize("break_it", [
    lambda folder: (folder / "manifest.json").write_text("{not json"),
    lambda folder: (folder / "manifest.json").unlink(),
    lambda folder: (folder / "manifest.json").write_text(json.dumps({"version": "2027.1.1", "format": 9, "template": 1,
                                                                    "files": {}})),
])
def test_a_download_without_a_manifest_this_code_reads_is_not_used(where, break_it):
    install(where.bundled)
    install(where.downloaded, "2026.1.5")
    break_it(where.downloaded)
    assert where.run(Server({}), offline=True) == where.bundled


@pytest.mark.parametrize("what", ["offline", "http", "garbage", "timeout"])
def test_a_check_that_fails_keeps_the_copy_at_hand_and_logs_one_line(where, what):
    install(where.bundled)
    release = threading.Event()
    served = publish("2026.1.2").served
    if what == "offline":
        def server(url):
            raise OSError("getaddrinfo failed")
    elif what == "http":
        server = Server({})
    elif what == "garbage":
        server = Server({f"{SOURCE}/main/manifest.json": b"<html>"})
    else:
        def server(url):
            release.wait(5)
            return served[url]
    try:
        started = time.monotonic()
        assert where.run(server, seconds=0.2) == where.bundled
        assert time.monotonic() - started < 3
    finally:
        release.set()
    assert not where.downloaded.exists()
    assert sum("kept" in line for line in where.lines) == 1


def test_a_failed_download_keeps_the_download_that_was_there_and_leaves_nothing_half_done(where):
    install(where.bundled, "2026.1.1")
    install(where.downloaded, "2026.1.2")
    served = publish("2026.1.3", files={**EVERYTHING, "data/event_table.json": b'{"events": [3]}'}).served
    served[f"{SOURCE}/2026.1.3/data/event_table.json"] = b'{"events": [4]}'  # a file that fails its sha256
    before = {p: p.read_bytes() for p in where.downloaded.rglob("*") if p.is_file()}
    assert where.run(Server(served)) == where.downloaded
    assert {p: p.read_bytes() for p in where.downloaded.rglob("*") if p.is_file()} == before
    assert sorted(p.name for p in where.downloaded.parent.iterdir()) == ["resource"]
    assert sum("kept" in line and "event_table.json" in line for line in where.lines) == 1


def test_a_download_that_dies_half_way_leaves_no_download_at_all(where):
    install(where.bundled)
    served = publish("2026.1.2", files={"data/event_table.json": b"a", "image/Battle/BattleStart.png": b"b"}).served
    del served[f"{SOURCE}/2026.1.2/image/Battle/BattleStart.png"]
    assert where.run(Server(served)) == where.bundled
    assert not where.downloaded.exists() and sorted(p.name for p in where.downloaded.parent.iterdir()) == []
    assert where.version(where.bundled) == "2026.1.1"


def test_a_download_that_takes_longer_than_its_budget_is_given_up(where):
    install(where.bundled)
    assert where.run(publish("2026.1.2", files={"data/event_table.json": b"new"}), download_seconds=0) == where.bundled
    assert not where.downloaded.exists()
    assert sum("kept" in line for line in where.lines) == 1


def test_a_data_part_of_a_format_it_does_not_know_is_skipped_and_the_images_apply(where):
    install(where.bundled)
    server = publish("2026.1.2", format=2, files={"data/event_table.json": b'{"events": [9]}',
                                                  "image/Battle/BattleStart.png": b"start 2"})
    assert where.run(server) == where.downloaded
    assert (where.downloaded / "data/event_table.json").read_bytes() == b'{"events": []}'
    assert (where.downloaded / "image/Battle/BattleStart.png").read_bytes() == b"start 2"
    assert any("format 2" in line for line in where.lines)


def test_a_package_that_nothing_of_is_known_changes_nothing(where):
    install(where.bundled)
    assert where.run(publish("2026.1.2", format=2, template=2)) == where.bundled
    assert not where.downloaded.exists()
    assert any("format 2" in line for line in where.lines)


def test_a_manifest_without_sources_turns_the_check_off(where):
    install(where.bundled, sources=[])
    server = publish("2026.1.2")
    assert where.run(server) == where.bundled
    assert server.requests == []
    assert any("no source" in line for line in where.lines)


def test_the_next_source_is_tried_when_the_first_does_not_answer(where):
    other = "https://mirror.test/pkg"
    install(where.bundled, sources=["https://dead.test/pkg", other])
    served = publish("2026.1.2").served
    mirrored = {url.replace(SOURCE, other): data for url, data in served.items()}
    assert where.run(Server(mirrored)) == where.downloaded


def test_start_sets_the_folder_the_readers_use(where, monkeypatch):
    install(where.bundled)
    monkeypatch.setattr(paths, "PACKAGE", where.bundled)
    folder = startup.start(["lc-helper.exe", "--offline"], bundled=where.bundled, downloaded=where.downloaded,
                           log=lambda line: None)
    assert folder == where.bundled and paths.PACKAGE == where.bundled
    install(where.downloaded, "2026.1.9")
    startup.start(["lc-helper.exe", "--offline"], bundled=where.bundled, downloaded=where.downloaded, log=lambda line: None)
    assert paths.PACKAGE == where.downloaded


def test_self_test_does_not_touch_the_network(where):
    install(where.bundled)
    server = publish("2026.1.2")
    startup.start(["lc-helper.exe", "--self-test"], bundled=where.bundled, downloaded=where.downloaded, fetch=server,
                  log=lambda line: None)
    assert server.requests == []


def test_the_log_keeps_its_last_lines_and_never_grows_without_end(tmp_path):
    log = tmp_path / "resource.log"
    for i in range(startup.LOG_LINES + startup.LOG_SLACK + 30):
        startup.append_log(log, f"line {i}")
    lines = log.read_text(encoding="utf-8").splitlines()
    assert len(lines) <= startup.LOG_LINES + startup.LOG_SLACK
    assert lines[-1].endswith(f"line {startup.LOG_LINES + startup.LOG_SLACK + 29}")


def test_a_download_that_hangs_on_one_file_is_given_up_at_its_budget(where):
    install(where.bundled)
    served = publish("2026.1.2", files={"data/event_table.json": b"new"}).served
    release = threading.Event()

    def server(url):
        if url.endswith("event_table.json"):
            release.wait(5)
        return served[url]
    try:
        started = time.monotonic()
        assert where.run(server, download_seconds=0.3) == where.bundled
        assert time.monotonic() - started < 3
    finally:
        release.set()
    assert not where.downloaded.exists()
    assert sum("kept" in line for line in where.lines) == 1


def test_a_swap_that_fails_leaves_the_download_that_was_there(where, monkeypatch):
    install(where.bundled, "2026.1.1")
    install(where.downloaded, "2026.1.2")
    real = type(where.downloaded).rename

    def rename(self, target):
        if self.name == "resource.new":
            raise PermissionError("another process holds a file of it")
        return real(self, target)
    monkeypatch.setattr(type(where.downloaded), "rename", rename)
    got = where.run(publish("2026.1.3"))
    assert got == where.downloaded and where.version(got) == "2026.1.2"
    assert sorted(p.name for p in where.downloaded.parent.iterdir()) == ["resource"]
    assert sum("kept" in line for line in where.lines) == 1


def test_a_start_killed_between_the_two_renames_finds_its_download_again(where):
    install(where.bundled, "2026.1.1")
    install(where.downloaded.parent / "resource.old", "2026.1.2")  # the folder moved aside; nothing moved in yet
    (where.downloaded.parent / "resource.new").mkdir()
    assert where.run(publish("2026.1.2")) == where.downloaded
    assert where.version(where.downloaded) == "2026.1.2"
    assert sorted(p.name for p in where.downloaded.parent.iterdir()) == ["resource"]


def test_the_success_line_names_the_version_that_was_replaced(where):
    install(where.bundled, "2026.1.1")
    install(where.downloaded, "2026.1.2")
    where.run(publish("2026.1.3"))
    assert any("2026.1.2 -> 2026.1.3" in line for line in where.lines)


def test_only_one_process_holds_the_lock_at_a_time(tmp_path):
    first = startup.acquire(tmp_path / "resource.lock")
    assert first is not None
    assert startup.acquire(tmp_path / "resource.lock") is None
    startup.release(first)
    again = startup.acquire(tmp_path / "resource.lock")
    assert again is not None
    startup.release(again)


def test_a_start_while_another_lc_helper_runs_reads_the_package_and_swaps_nothing(where):
    install(where.bundled, "2026.1.1")
    install(where.downloaded, "2026.1.2")
    server = publish("2026.1.3")
    lines = []
    running = startup.acquire(where.downloaded.parent / "resource.lock")
    try:
        got = startup.start(["lc-helper.exe"], bundled=where.bundled, downloaded=where.downloaded, fetch=server,
                            log=lines.append, lock=where.downloaded.parent / "resource.lock")
    finally:
        startup.release(running)
    assert got == where.downloaded and where.version(got) == "2026.1.2"
    assert server.requests == []
    assert any("another lc-helper" in line for line in lines)
