import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from shopify_tool.stock_export import prepare_export_path

NOW = datetime(2026, 9, 25, 14, 5, tzinfo=UTC)


def touch(d, *names):
    for n in names:
        (d / n).write_bytes(b"x")


def test_name_is_stem_date_and_minute(tmp_path):
    out = prepare_export_path(str(tmp_path / "ALL_ORDERS_ALMADERM.xls"), NOW)
    assert Path(out).name == "ALL_ORDERS_ALMADERM_2026-09-25_1405.xls"


def test_a_legacy_datestamp_in_the_stem_is_replaced(tmp_path):
    out = prepare_export_path(str(tmp_path / "ALL_2026-09-24.xls"), NOW)
    assert Path(out).name == "ALL_2026-09-25_1405.xls"


def test_every_earlier_version_moves_to_old(tmp_path):
    touch(tmp_path, "ALL.xls", "ALL_2026-09-24.xls", "ALL_2026-09-24_0900.xls",
          "ALL_2026-09-24_0900_packaging.xls", "ALL_DHL.xls", "notes.txt")
    prepare_export_path(str(tmp_path / "ALL.xls"), NOW)
    assert sorted(p.name for p in (tmp_path / "old").iterdir()) == [
        "ALL.xls", "ALL_2026-09-24.xls", "ALL_2026-09-24_0900.xls",
        "ALL_2026-09-24_0900_packaging.xls"]
    # Review Focus 1: another report sharing the prefix stays.
    assert sorted(p.name for p in tmp_path.iterdir() if p.is_file()) == ["ALL_DHL.xls", "notes.txt"]


def test_regex_characters_in_the_name_are_literal(tmp_path):
    touch(tmp_path, "ALL (DHL)+.xls", "ALL (DHL)+_2026-09-24_0900.xls", "ALL DHL.xls")
    out = prepare_export_path(str(tmp_path / "ALL (DHL)+.xls"), NOW)
    assert Path(out).name == "ALL (DHL)+_2026-09-25_1405.xls"
    assert sorted(p.name for p in (tmp_path / "old").iterdir()) == [
        "ALL (DHL)+.xls", "ALL (DHL)+_2026-09-24_0900.xls"]


def test_same_minute_re_export_archives_the_first(tmp_path):
    # Review Focus 2.
    touch(tmp_path, "ALL_2026-09-25_1405.xls")
    (tmp_path / "old").mkdir()
    touch(tmp_path / "old", "ALL_2026-09-25_1405.xls")
    out = prepare_export_path(str(tmp_path / "ALL.xls"), NOW)
    assert not Path(out).exists()
    assert (tmp_path / "old" / "ALL_2026-09-25_1405.xls").exists()


def test_a_locked_earlier_version_raises(tmp_path, monkeypatch):
    touch(tmp_path, "ALL.xls")

    def locked(src, dst):
        raise PermissionError(13, "in use", src)

    monkeypatch.setattr(os, "replace", locked)
    with pytest.raises(PermissionError):
        prepare_export_path(str(tmp_path / "ALL.xls"), NOW)
