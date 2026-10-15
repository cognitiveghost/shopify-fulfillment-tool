"""Archive, restore and delete a client (spec A1, ADR 0020)."""

import json

import pytest

from shopify_tool import profile_manager as pm_module
from shopify_tool.profile_manager import ProfileManagerError


def _make(pm, cid="ACME", name="Acme Ltd"):
    assert pm.create_client_profile(cid, name)
    return cid


def _session(pm, cid, name="2026-10-15_1"):
    d = pm.sessions_dir / f"CLIENT_{cid}" / name
    d.mkdir(parents=True)
    return d


def test_archive_moves_both_folders_out_of_the_list(profile_manager):
    pm = profile_manager
    cid = _make(pm)
    _session(pm, cid)
    pm.archive_client(cid)
    assert not (pm.clients_dir / "CLIENT_ACME").exists()
    assert (pm.clients_dir / "_archive" / "CLIENT_ACME" / "client_config.json").exists()
    assert (pm.sessions_dir / "_archive" / "CLIENT_ACME" / "2026-10-15_1").is_dir()
    assert "ACME" not in pm.list_clients()


def test_archive_stamps_when_and_where(profile_manager):
    pm = profile_manager
    cid = _make(pm)
    pm.archive_client(cid)
    cfg = json.loads(
        (pm.clients_dir / "_archive" / "CLIENT_ACME" / "client_config.json").read_text("utf-8")
    )
    assert cfg["archived_at"]
    assert "archived_by" in cfg


def test_archive_refuses_a_missing_client(profile_manager):
    with pytest.raises(ProfileManagerError, match="CLIENT_NOPE does not exist"):
        profile_manager.archive_client("NOPE")


def test_archive_refuses_when_an_archived_copy_exists(profile_manager):
    pm = profile_manager
    cid = _make(pm)
    (pm.clients_dir / "_archive" / "CLIENT_ACME").mkdir(parents=True)
    with pytest.raises(ProfileManagerError, match="An archived CLIENT_ACME already exists"):
        pm.archive_client(cid)
    assert (pm.clients_dir / "CLIENT_ACME").is_dir()


def test_a_client_rename_refused_reads_open_on_another_pc(profile_manager, monkeypatch):
    pm = profile_manager
    cid = _make(pm)

    def refuse(src, dst):
        raise PermissionError("in use")

    monkeypatch.setattr(pm_module.os, "rename", refuse)
    with pytest.raises(ProfileManagerError, match="open on another PC"):
        pm.archive_client(cid)


def test_a_failed_sessions_move_puts_the_client_back(profile_manager, monkeypatch):
    pm = profile_manager
    cid = _make(pm)
    _session(pm, cid)
    real = pm_module.os.rename

    def flaky(src, dst):
        if "Sessions" in str(src) and "_archive" in str(dst):
            raise PermissionError("in use")
        return real(src, dst)

    monkeypatch.setattr(pm_module.os, "rename", flaky)
    with pytest.raises(ProfileManagerError, match="open on another PC"):
        pm.archive_client(cid)
    assert (pm.clients_dir / "CLIENT_ACME").is_dir()
    assert not (pm.clients_dir / "_archive" / "CLIENT_ACME").exists()


def test_restore_brings_both_back_and_drops_the_stamp(profile_manager):
    pm = profile_manager
    cid = _make(pm)
    _session(pm, cid)
    pm.archive_client(cid)
    pm.restore_client(cid)
    assert "ACME" in pm.list_clients()
    assert (pm.sessions_dir / "CLIENT_ACME" / "2026-10-15_1").is_dir()
    cfg = json.loads((pm.clients_dir / "CLIENT_ACME" / "client_config.json").read_text("utf-8"))
    assert "archived_at" not in cfg and "archived_by" not in cfg


def test_restore_refuses_when_a_live_client_has_the_id(profile_manager):
    pm = profile_manager
    cid = _make(pm)
    pm.archive_client(cid)
    (pm.clients_dir / "CLIENT_ACME").mkdir()
    with pytest.raises(ProfileManagerError, match="A live CLIENT_ACME exists"):
        pm.restore_client(cid)


def test_restore_refuses_when_a_stale_save_recreated_the_sessions_folder(profile_manager):
    pm = profile_manager
    cid = _make(pm)
    _session(pm, cid)
    pm.archive_client(cid)
    _session(pm, cid)  # another PC saved into its open session after the archive
    with pytest.raises(ProfileManagerError, match="exists again"):
        pm.restore_client(cid)
    assert (pm.clients_dir / "_archive" / "CLIENT_ACME").is_dir()
    assert "ACME" not in pm.list_clients()


def test_list_archived_clients(profile_manager):
    pm = profile_manager
    assert pm.list_archived_clients() == []
    _make(pm, "ZED", "Zed Co")
    _make(pm, "ACME", "Acme Ltd")
    pm.archive_client("ZED")
    pm.archive_client("ACME")
    listed = pm.list_archived_clients()
    assert [c["client_id"] for c in listed] == ["ACME", "ZED"]
    assert listed[0]["client_name"] == "Acme Ltd"
    assert listed[0]["archived_at"]


def test_list_archived_survives_a_broken_config(profile_manager):
    pm = profile_manager
    d = pm.clients_dir / "_archive" / "CLIENT_BAD"
    d.mkdir(parents=True)
    (d / "client_config.json").write_text("{not json", "utf-8")
    assert pm.list_archived_clients() == [
        {"client_id": "BAD", "client_name": "BAD", "archived_at": ""}
    ]


def test_has_sessions_counts_folders_not_files(profile_manager):
    pm = profile_manager
    cid = _make(pm)
    assert not pm.client_has_sessions(cid)
    (pm.sessions_dir / "CLIENT_ACME" / "sessions_index.json").write_text("[]", "utf-8")
    assert not pm.client_has_sessions(cid)
    _session(pm, cid)
    assert pm.client_has_sessions(cid)


def test_delete_removes_an_empty_client(profile_manager):
    pm = profile_manager
    cid = _make(pm)
    pm.delete_client(cid)
    assert not (pm.clients_dir / "CLIENT_ACME").exists()
    assert not (pm.sessions_dir / "CLIENT_ACME").exists()


def test_delete_refuses_a_client_with_sessions(profile_manager):
    pm = profile_manager
    cid = _make(pm)
    _session(pm, cid)
    with pytest.raises(ProfileManagerError, match="has sessions. Archive it instead"):
        pm.delete_client(cid)
    assert (pm.clients_dir / "CLIENT_ACME").is_dir()


def test_delete_refuses_a_missing_client(profile_manager):
    with pytest.raises(ProfileManagerError, match="CLIENT_NOPE does not exist"):
        profile_manager.delete_client("NOPE")
