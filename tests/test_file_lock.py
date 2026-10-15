"""The advisory file lock the shared JSON files take (shared/file_lock.py; Audit 10, part A)."""

import pytest

from shared import file_lock
from shared.file_lock import FileLockError, locked_file


def test_a_second_handle_waits_then_gives_up(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{}", encoding="utf-8")
    with open(path, "r+") as first, open(path, "r+") as second, locked_file(first), pytest.raises(
        FileLockError, match="within 0.2 seconds"
    ), locked_file(second, timeout=0.2, retry_delay=0.02):
        pytest.fail("the second handle must not get the lock while the first holds it")


def test_the_lock_is_free_again_once_released(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{}", encoding="utf-8")
    with open(path, "r+") as first, open(path, "r+") as second:
        with locked_file(first):
            pass
        with locked_file(second, timeout=0.5):
            second.write("ok")


def test_the_lock_is_released_when_the_body_raises(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{}", encoding="utf-8")
    with open(path, "r+") as first, open(path, "r+") as second:
        with pytest.raises(RuntimeError), locked_file(first):
            raise RuntimeError("boom")
        with locked_file(second, timeout=0.5):
            pass


class _FakeMsvcrt:
    """msvcrt.locking that fails `failures` times, then succeeds; records every call."""

    LK_NBLCK = 2
    LK_UNLCK = 0

    def __init__(self, failures):
        self.failures = failures
        self.calls = []

    def locking(self, fd, mode, nbytes):
        self.calls.append(mode)
        if mode == self.LK_NBLCK and self.failures > 0:
            self.failures -= 1
            raise OSError("locked by another process")


def _as_windows(monkeypatch, fake):
    monkeypatch.setattr(file_lock, "WINDOWS_LOCKING_AVAILABLE", True)
    monkeypatch.setattr(file_lock, "msvcrt", fake, raising=False)


def test_windows_branch_retries_until_the_lock_is_free_and_unlocks(tmp_path, monkeypatch):
    fake = _FakeMsvcrt(failures=2)
    _as_windows(monkeypatch, fake)
    with open(tmp_path / "f", "w") as handle, locked_file(handle, timeout=2, retry_delay=0.01):
        pass
    assert fake.calls == [fake.LK_NBLCK, fake.LK_NBLCK, fake.LK_NBLCK, fake.LK_UNLCK]


def test_windows_branch_times_out_and_never_unlocks_a_lock_it_did_not_get(tmp_path, monkeypatch):
    fake = _FakeMsvcrt(failures=10**6)
    _as_windows(monkeypatch, fake)
    with open(tmp_path / "f", "w") as handle, pytest.raises(FileLockError), locked_file(
        handle, timeout=0.1, retry_delay=0.01
    ):
        pass
    assert fake.LK_UNLCK not in fake.calls


def test_an_unlock_error_is_ignored(tmp_path, monkeypatch):
    class Flaky(_FakeMsvcrt):
        def locking(self, fd, mode, nbytes):
            if mode == self.LK_UNLCK:
                raise OSError("handle closed")

    _as_windows(monkeypatch, Flaky(failures=0))
    with open(tmp_path / "f", "w") as handle, locked_file(handle):
        pass  # no exception from the finally block


def test_without_any_locking_support_it_is_a_no_op(tmp_path, monkeypatch):
    monkeypatch.setattr(file_lock, "WINDOWS_LOCKING_AVAILABLE", False)
    monkeypatch.setattr(file_lock, "UNIX_LOCKING_AVAILABLE", False)
    with open(tmp_path / "f", "w") as first, open(tmp_path / "f", "w") as second, locked_file(first), \
            locked_file(second):
        pass


@pytest.mark.filterwarnings("ignore::RuntimeWarning")  # runpy: the module is already imported
def test_the_modules_own_self_check_passes(capsys):
    import runpy

    runpy.run_module("shared.file_lock", run_name="__main__")
    assert "file_lock self-check OK" in capsys.readouterr().out
