"""scripts/build_guide_server.py seeds a throwaway server folder from the replay fixtures (user guides, Task 4)."""

import json

import pytest

from scripts.build_guide_server import build


def _json(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    dest = tmp_path_factory.mktemp("guide") / "srv"
    build(dest)
    return dest


def test_builds_clients_sessions_and_packer_files(server):
    clients = server / "Clients"
    assert _json(clients / "CLIENT_ALMA" / "client_config.json")["client_name"] == "Alma Derm"
    assert _json(clients / "CLIENT_HERBAR" / "client_config.json")["client_name"] == "Herbar"

    for client_id, expected in (("ALMA", 3), ("HERBAR", 2)):
        sessions = [p for p in (server / "Sessions" / f"CLIENT_{client_id}").iterdir() if p.is_dir()]
        assert len(sessions) == expected
        for session in sessions:
            assert list((session / "packing_lists").glob("*.json"))

    packer = _json(clients / "CLIENT_ALMA" / "packer_config.json")
    assert packer["client_id"] == "ALMA"
    assert packer["client_name"] == "Alma Derm"
    assert packer["sku_mapping"]

    workers = _json(server / "Workers" / "workers.json")["workers"]
    assert len(workers) == 3
    for worker in workers:
        assert {"id", "name", "created_at"} <= worker.keys()


def test_refuses_non_empty_dest(tmp_path):
    dest = tmp_path / "srv"
    dest.mkdir()
    keep = dest / "keep.txt"
    keep.write_text("mine", encoding="utf-8")

    with pytest.raises((SystemExit, ValueError)):
        build(dest)

    assert keep.read_text(encoding="utf-8") == "mine"
