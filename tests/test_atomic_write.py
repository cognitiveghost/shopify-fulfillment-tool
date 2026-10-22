"""replace_with_retry: rides out a reader holding the target on the share."""

import os

import pytest

from shared import atomic_write
from shared.atomic_write import replace_with_retry


def test_replace_with_retry_gives_up_on_a_lasting_lock(tmp_path, monkeypatch):
    src, dst = tmp_path / "a.tmp", tmp_path / "a.json"
    src.write_text("x", encoding="utf-8")
    sleeps = []

    def always_locked(*args, **kwargs):
        raise PermissionError(13, "being used by another process")

    monkeypatch.setattr(os, "replace", always_locked)
    monkeypatch.setattr(atomic_write.time, "sleep", sleeps.append)

    with pytest.raises(PermissionError):
        replace_with_retry(src, dst)
    assert 3 <= sum(sleeps) <= 6


def test_replace_with_retry_does_not_retry_other_errors(tmp_path, monkeypatch):
    calls = []

    def missing(src, dst, *args, **kwargs):
        calls.append(1)
        raise FileNotFoundError(2, "gone")

    monkeypatch.setattr(os, "replace", missing)
    monkeypatch.setattr(atomic_write.time, "sleep", lambda s: None)

    with pytest.raises(FileNotFoundError):
        replace_with_retry(tmp_path / "a.tmp", tmp_path / "a.json")
    assert len(calls) == 1


def test_temp_file_does_not_match_a_json_scan(tmp_path, monkeypatch):
    # Packing lists are found by `*.json`; a temp file must not be one.
    seen = []
    real = os.replace

    def spy(src, dst, *args, **kwargs):
        seen.extend(p.name for p in tmp_path.glob("*.json"))
        return real(src, dst, *args, **kwargs)

    monkeypatch.setattr(os, "replace", spy)
    atomic_write.atomic_write_json(tmp_path / "ALL.json", {"orders": []})
    assert seen == []
