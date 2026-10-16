"""Find, fetch and stage a newer GitHub release; swap it in after exit (ADR 0022).

Pure logic plus stdlib I/O. No Qt here except through shared.relaunch; the
flow around it (thread, button, dialogs) is shared/update_flow.py.
Messages are English constants, translated where they are shown.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import shutil
import tempfile
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePath

from shared import relaunch
from shared.i18n import N_

API = "https://api.github.com/repos/{repo}/releases/latest"
TIMEOUT_S = 5
CHUNK = 1 << 20
RENAME_TRIES = 60

NOT_RELEASED = N_("Updates install only in the released app.")
NOT_CHECKED = N_("Updates are checked only in the released app.")
NO_PERMISSION = N_("No permission to write to {folder}.")
BAD_CHECKSUM = N_("The download is damaged (checksum mismatch).")
NO_EXE = N_("The download does not contain {exe}.")
NO_CONNECTION = N_("Could not reach GitHub: {detail}")


@dataclass(frozen=True)
class AppIdentity:
    repo: str
    asset_prefix: str
    exe_name: str


@dataclass(frozen=True)
class Release:
    version: str
    page_url: str
    zip_url: str
    sha_url: str


class UpdateError(Exception):
    """`args[0]` is an English message constant, `values` its fields."""

    def __init__(self, message: str, **values):
        super().__init__(message)
        self.message, self.values = message, values


def parse_version(text) -> tuple[int, ...] | None:
    if not isinstance(text, str):
        return None
    parts = text.strip().removeprefix("v").split(".")
    if not all(p.isdigit() for p in parts):
        return None
    return tuple(int(p) for p in parts)


def _get(url: str, accept: str):
    request = urllib.request.Request(
        url, headers={"Accept": accept, "User-Agent": "shared-updater"}
    )
    try:
        return urllib.request.urlopen(request, timeout=TIMEOUT_S)
    except (urllib.error.URLError, OSError) as exc:
        raise UpdateError(NO_CONNECTION, detail=str(exc)) from exc


def fetch_json(url: str) -> dict:
    with _get(url, "application/vnd.github+json") as response:
        try:
            return json.loads(response.read().decode("utf-8"))
        except ValueError as exc:
            raise UpdateError(NO_CONNECTION, detail=str(exc)) from exc


def fetch_text(url: str) -> str:
    with _get(url, "application/octet-stream") as response:
        return response.read().decode("utf-8", "replace")


def fetch_to(url: str, dest: Path, progress: Callable[[int], None]) -> None:
    with _get(url, "application/octet-stream") as response, open(dest, "wb") as out:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        while chunk := response.read(CHUNK):
            out.write(chunk)
            done += len(chunk)
            if total:
                progress(min(99, done * 100 // total))
    progress(100)


def newer_release(app: AppIdentity, current: str, fetch=fetch_json) -> Release | None:
    mine = parse_version(current)
    if mine is None:
        return None
    data = fetch(API.format(repo=app.repo))
    tag = str(data.get("tag_name", ""))
    theirs = parse_version(tag)
    if theirs is None or theirs <= mine:
        return None
    version = tag.strip().removeprefix("v")
    urls = {a.get("name"): a.get("browser_download_url") for a in data.get("assets", [])}
    zip_name = f"{app.asset_prefix}-{version}.zip"
    if not urls.get(zip_name) or not urls.get(zip_name + ".sha256"):
        return None
    return Release(version, str(data.get("html_url", "")), urls[zip_name], urls[zip_name + ".sha256"])


def install_blocker(app_dir: Path, frozen: bool) -> str | None:
    """English reason this copy cannot update itself, or None."""
    if not frozen:
        return NOT_RELEASED
    parent = Path(app_dir).parent
    try:
        with tempfile.NamedTemporaryFile(dir=parent):
            pass
    except OSError:
        return NO_PERMISSION.format(folder=parent)
    return None


def is_server_copy(app_dir: PurePath) -> bool:
    text = str(app_dir)
    if text.startswith(("\\\\", "//")):
        return True
    if os.name == "nt" and len(text) > 1 and text[1] == ":":
        DRIVE_REMOTE = 4
        return ctypes.windll.kernel32.GetDriveTypeW(text[:2] + "\\") == DRIVE_REMOTE
    return False


def staging_dir(app_dir: Path) -> Path:
    return Path(app_dir).parent / f"{Path(app_dir).name}.update"


def stage(release, app, app_dir, progress, download=fetch_to, read=fetch_text) -> Path:
    staged = staging_dir(app_dir)
    shutil.rmtree(staged, ignore_errors=True)
    fd, name = tempfile.mkstemp(suffix=".zip")
    os.close(fd)
    archive = Path(name)
    try:
        download(release.zip_url, archive, progress)
        expected = (read(release.sha_url).split() or [""])[0].lower()
        digest = hashlib.sha256()
        with open(archive, "rb") as handle:
            while chunk := handle.read(CHUNK):
                digest.update(chunk)
        if digest.hexdigest() != expected:
            raise UpdateError(BAD_CHECKSUM)
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(staged)
        if not (staged / app.exe_name).is_file():
            raise UpdateError(NO_EXE, exe=app.exe_name)
        return staged
    except BaseException:
        shutil.rmtree(staged, ignore_errors=True)
        raise
    finally:
        archive.unlink(missing_ok=True)


def _q(path) -> str:
    """A path for a .cmd line: quoted, % doubled."""
    return '"' + str(path).replace("%", "%%") + '"'


def swap_script(app_dir, staged, exe_name: str, pid: int, version: str) -> str:
    previous = app_dir.parent / f"{app_dir.name}.previous"
    name = app_dir.name.replace("%", "%%")
    staged_name = staged.name.replace("%", "%%")
    exe = app_dir / exe_name
    return "\r\n".join([
        "@echo off",
        "rem Written by shared/updater.py (ADR 0022): swaps in a new release after the app exits.",
        # Leave the app folder: a cwd inside it blocks the rename. ping, not timeout:
        # timeout needs console input, which a hidden console may not give it.
        'cd /d "%SystemRoot%"',
        ":waitpid",
        f'tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul && (ping -n 2 127.0.0.1 >nul & goto waitpid)',
        f"if exist {_q(previous)} rd /s /q {_q(previous)}",
        "set n=0",
        ":rename",
        f'ren {_q(app_dir)} "{name}.previous" 2>nul && goto swap',
        "set /a n+=1",
        f"if %n% geq {RENAME_TRIES} goto fail",
        "ping -n 2 127.0.0.1 >nul",
        "goto rename",
        ":swap",
        f'ren {_q(staged)} "{name}" || (ren {_q(previous)} "{name}" & goto fail)',
        f"robocopy {_q(previous)} {_q(app_dir)} /E /XC /XN /XO /NFL /NDL /NJH /NJS >nul",
        f'if errorlevel 8 (ren {_q(app_dir)} "{staged_name}" & ren {_q(previous)} "{name}" & goto fail)',
        f'start "" /D {_q(app_dir)} {_q(exe)}',
        '(goto) 2>nul & del "%~f0"',
        ":fail",
        f">{_q(staged / 'failed.txt')} echo {version}",
        f'start "" /D {_q(app_dir)} {_q(exe)}',
        "exit /b 1",
        "",
    ])


def arm_install(app_dir: Path, staged: Path, exe_name: str, version: str) -> Path:
    script = Path(app_dir).parent / f"{Path(app_dir).name}.update.cmd"
    text = swap_script(Path(app_dir), Path(staged), exe_name, os.getpid(), version)
    script.write_text(text, encoding="utf-8", newline="")
    # /s plus doubled quotes: a plain "/c path" breaks on a folder named "App (1)".
    relaunch.on_quit(f'cmd /d /s /c ""{script}""', update=True)
    return script


def leftover(app_dir: Path) -> str | None:
    """At startup: the version a failed swap left behind, after cleaning up."""
    staged = staging_dir(app_dir)
    script = Path(app_dir).parent / f"{Path(app_dir).name}.update.cmd"
    marker = staged / "failed.txt"
    version = marker.read_text(encoding="utf-8").strip() if marker.is_file() else None
    shutil.rmtree(staged, ignore_errors=True)
    script.unlink(missing_ok=True)
    return version or None
