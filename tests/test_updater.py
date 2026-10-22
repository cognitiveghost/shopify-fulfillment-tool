import hashlib
import os
import zipfile

import pytest

from shared import relaunch, updater
from shared.updater import AppIdentity, Release, UpdateError

APP = AppIdentity("owner/repo", "FulfilmentTool", "FulfilmentTool.exe")


def _payload(tag="2.4.0", assets=("FulfilmentTool-2.4.0.zip", "FulfilmentTool-2.4.0.zip.sha256")):
    return {
        "tag_name": tag,
        "html_url": f"https://github.com/owner/repo/releases/tag/{tag}",
        "assets": [{"name": n, "browser_download_url": f"https://dl/{n}"} for n in assets],
    }


@pytest.mark.parametrize("text, expected", [
    ("2.3.1", (2, 3, 1)), ("v2.4", (2, 4)), ("1.3.10.2", (1, 3, 10, 2)),
    ("dev", None), ("", None), ("2.x", None), (None, None),
])
def test_parse_version(text, expected):
    assert updater.parse_version(text) == expected


def test_a_newer_release_is_offered():
    release = updater.newer_release(APP, "2.3.1", fetch=lambda url: _payload())
    assert release == Release(
        "2.4.0", "https://github.com/owner/repo/releases/tag/2.4.0",
        "https://dl/FulfilmentTool-2.4.0.zip", "https://dl/FulfilmentTool-2.4.0.zip.sha256",
    )


def test_the_api_url_is_the_repos_latest_release():
    urls = []
    updater.newer_release(APP, "2.3.1", fetch=lambda url: urls.append(url) or _payload())
    assert urls == ["https://api.github.com/repos/owner/repo/releases/latest"]


@pytest.mark.parametrize("current, payload", [
    ("2.4.0", _payload()),                                   # same
    ("2.10.0", _payload()),                                  # older (numeric, not text, compare)
    ("dev", _payload()),                                     # dev build
    ("2.3.1", _payload(tag="nightly")),                      # tag does not parse
    ("2.3.1", _payload(assets=("FulfilmentTool-2.4.0.zip",))),  # no .sha256
    ("2.3.1", _payload(assets=("Other-2.4.0.zip", "Other-2.4.0.zip.sha256"))),
])
def test_nothing_is_offered(current, payload):
    assert updater.newer_release(APP, current, fetch=lambda url: payload) is None


def test_a_v_prefixed_tag_finds_assets_named_without_it():
    payload = _payload(tag="v2.4.0")
    release = updater.newer_release(APP, "2.3.1", fetch=lambda url: payload)
    assert release.version == "2.4.0"


def test_fetch_errors_surface_as_update_error():
    def boom(url):
        raise UpdateError("Network down")
    with pytest.raises(UpdateError):
        updater.newer_release(APP, "2.3.1", fetch=boom)


def test_install_blocker(tmp_path):
    app_dir = tmp_path / "FulfilmentTool"
    app_dir.mkdir()
    assert updater.install_blocker(app_dir, frozen=False) == updater.NOT_RELEASED
    assert updater.install_blocker(app_dir, frozen=True) is None


@pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0, reason="chmod is not a lock here")
def test_install_blocker_read_only_parent(tmp_path):
    parent = tmp_path / "ro"
    app_dir = parent / "FulfilmentTool"
    app_dir.mkdir(parents=True)
    parent.chmod(0o555)
    try:
        assert updater.install_blocker(app_dir, frozen=True) == updater.NO_PERMISSION.format(folder=parent)
    finally:
        parent.chmod(0o755)


def test_is_server_copy_unc():
    from pathlib import PureWindowsPath
    assert updater.is_server_copy(PureWindowsPath(r"\\server\share\FulfilmentTool"))


def _release_zip(tmp_path, with_exe=True):
    path = tmp_path / "src.zip"
    with zipfile.ZipFile(path, "w") as zf:
        if with_exe:
            zf.writestr("FulfilmentTool.exe", b"exe")
        zf.writestr("_internal/lib.dll", b"dll")
    return path


def _fakes(zip_path, digest=None):
    data = zip_path.read_bytes()
    digest = digest or hashlib.sha256(data).hexdigest()

    def download(url, dest, progress):
        dest.write_bytes(data)
        progress(100)

    return download, (lambda url: f"{digest}  FulfilmentTool-2.4.0.zip\n")


RELEASE = Release("2.4.0", "page", "zip", "sha")


def test_stage_extracts_beside_the_app(tmp_path):
    app_dir = tmp_path / "FulfilmentTool"
    app_dir.mkdir()
    download, read = _fakes(_release_zip(tmp_path))
    seen = []
    staged = updater.stage(RELEASE, APP, app_dir, seen.append, download=download, read=read)
    assert staged == tmp_path / "FulfilmentTool.update"
    assert (staged / "FulfilmentTool.exe").read_bytes() == b"exe"
    assert (staged / "_internal" / "lib.dll").is_file()
    assert seen[-1] == 100


def test_stage_rejects_a_bad_checksum_and_cleans_up(tmp_path):
    app_dir = tmp_path / "FulfilmentTool"
    app_dir.mkdir()
    download, read = _fakes(_release_zip(tmp_path), digest="0" * 64)
    with pytest.raises(UpdateError):
        updater.stage(RELEASE, APP, app_dir, lambda p: None, download=download, read=read)
    assert not (tmp_path / "FulfilmentTool.update").exists()


def test_stage_rejects_a_zip_without_the_exe(tmp_path):
    app_dir = tmp_path / "FulfilmentTool"
    app_dir.mkdir()
    download, read = _fakes(_release_zip(tmp_path, with_exe=False))
    with pytest.raises(UpdateError):
        updater.stage(RELEASE, APP, app_dir, lambda p: None, download=download, read=read)
    assert not (tmp_path / "FulfilmentTool.update").exists()


def test_stage_replaces_an_old_staging_folder(tmp_path):
    app_dir = tmp_path / "FulfilmentTool"
    app_dir.mkdir()
    old = tmp_path / "FulfilmentTool.update"
    old.mkdir()
    (old / "stale.txt").write_text("x")
    download, read = _fakes(_release_zip(tmp_path))
    staged = updater.stage(RELEASE, APP, app_dir, lambda p: None, download=download, read=read)
    assert not (staged / "stale.txt").exists()


def test_swap_script_steps_in_order(tmp_path):
    from pathlib import PureWindowsPath as W
    text = updater.swap_script(
        W(r"C:\Apps\Fulfil 100%"), W(r"C:\Apps\Fulfil 100%.update"), "FulfilmentTool.exe", 4242, "2.4.0"
    )
    order = [
        'cd /d "%SystemRoot%"',
        'tasklist /FI "PID eq 4242"',
        'rd /s /q "C:\\Apps\\Fulfil 100%%.previous"',
        'ren "C:\\Apps\\Fulfil 100%%" "Fulfil 100%%.previous"',
        'ren "C:\\Apps\\Fulfil 100%%.update" "Fulfil 100%%"',
        'robocopy "C:\\Apps\\Fulfil 100%%.previous" "C:\\Apps\\Fulfil 100%%" /E /XC /XN /XO',
        'if errorlevel 8',
        'start "" /D "C:\\Apps\\Fulfil 100%%" "C:\\Apps\\Fulfil 100%%\\FulfilmentTool.exe"',
    ]
    positions = [text.index(step) for step in order]
    assert positions == sorted(positions)
    assert "failed.txt" in text and "2.4.0" in text
    assert "if %n% geq 60" in text
    assert "timeout" not in text  # needs console input the hidden console lacks
    assert '|| (ren "C:\\Apps\\Fulfil 100%%.previous" "Fulfil 100%%" & goto fail)' in text


def test_arm_install_writes_the_script_and_arms_on_quit(tmp_path, qapp):
    relaunch._reset()
    app_dir = tmp_path / "FulfilmentTool"
    staged = tmp_path / "FulfilmentTool.update"
    app_dir.mkdir()
    staged.mkdir()
    script = updater.arm_install(app_dir, staged, "FulfilmentTool.exe", "2.4.0")
    assert script == tmp_path / "FulfilmentTool.update.cmd"
    assert script.read_text(encoding="utf-8").startswith("@echo off")
    assert relaunch.pending() == f'cmd /d /s /c ""{script}""'
    relaunch._reset()


def test_leftover_reports_a_failed_swap_and_cleans_up(tmp_path):
    app_dir = tmp_path / "FulfilmentTool"
    staged = tmp_path / "FulfilmentTool.update"
    app_dir.mkdir()
    staged.mkdir()
    (staged / "failed.txt").write_text("2.4.0\n")
    (tmp_path / "FulfilmentTool.update.cmd").write_text("x")
    assert updater.leftover(app_dir) == "2.4.0"
    assert not staged.exists()
    assert not (tmp_path / "FulfilmentTool.update.cmd").exists()


def test_leftover_removes_a_half_download_silently(tmp_path):
    app_dir = tmp_path / "FulfilmentTool"
    app_dir.mkdir()
    (tmp_path / "FulfilmentTool.update").mkdir()
    assert updater.leftover(app_dir) is None
    assert not (tmp_path / "FulfilmentTool.update").exists()


def test_leftover_nothing(tmp_path):
    app_dir = tmp_path / "FulfilmentTool"
    app_dir.mkdir()
    assert updater.leftover(app_dir) is None
