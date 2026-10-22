"""How core reads and rejects its inputs, and what it still writes when a save step fails
(Audit 10, part A). Real CSVs under tmp_path; no Qt."""

import json
from pathlib import Path

import pandas as pd
import pytest

from shopify_tool import core
from shopify_tool.session_manager import SessionManager

MAPPINGS = {
    "orders": {"Name": "Order_Number", "Lineitem sku": "SKU",
               "Lineitem quantity": "Quantity", "Shipping Method": "Shipping_Method"},
    "stock": {"Артикул": "SKU", "Име": "Product_Name", "Наличност": "Stock"},
}
ORDERS = "Name,Lineitem sku,Lineitem quantity,Shipping Method\n#1,A,1,DHL\n#2,B,2,DHL\n"
STOCK = "Артикул,Име,Наличност\nA,Alpha,5\nB,Beta,5\n"


class Profiles:
    """What SessionManager and a run ask a ProfileManager for, memory off."""

    def __init__(self, root):
        self.root = Path(root)

    def get_sessions_root(self):
        return self.root / "Sessions"

    def client_exists(self, _client_id):
        return True

    def invalidate_metadata_cache(self, _client_id):
        pass

    def get_client_directory(self, _client_id):
        path = self.root / "client"
        path.mkdir(exist_ok=True)
        return path

    def get_inventory_memory(self, _client_id):
        return {}

    def load_shopify_config(self, _client_id):
        return {}

    def load_client_config(self, _client_id):
        return {}


@pytest.fixture
def files(tmp_path):
    (tmp_path / "orders.csv").write_text(ORDERS, encoding="utf-8")
    (tmp_path / "stock.csv").write_text(STOCK, encoding="utf-8")
    return tmp_path / "stock.csv", tmp_path / "orders.csv"


def _run(stock, orders, out, config=None, **kwargs):
    return core.run_full_analysis(
        str(stock), str(orders), str(out), ",", ",", config or {"column_mappings": MAPPINGS}, **kwargs
    )


def test_a_run_without_a_client_writes_its_report_where_it_was_told(files, tmp_path):
    stock, orders = files
    ok, path, df, _ = _run(stock, orders, tmp_path / "out")
    assert ok and len(df) == 2
    assert Path(path).parent == tmp_path / "out"
    assert Path(path).exists()


def test_a_missing_file_is_reported(files, tmp_path):
    stock, _ = files
    ok, message, df, stats = _run(stock, tmp_path / "gone.csv", tmp_path / "out")
    assert (ok, df, stats) == (False, None, None)
    assert message.startswith("File not found:")


def test_orders_without_a_required_column_name_the_column(files, tmp_path):
    stock, orders = files
    orders.write_text("Name,Lineitem quantity,Shipping Method\n#1,1,DHL\n", encoding="utf-8")
    ok, message, _, _ = _run(stock, orders, tmp_path / "out")
    assert not ok
    assert message.startswith("Validation error:") and "Lineitem sku" in message


def test_stock_without_a_required_column_names_the_column(files, tmp_path):
    stock, orders = files
    stock.write_text("Артикул,Име\nA,Alpha\n", encoding="utf-8")
    ok, message, _, _ = _run(stock, orders, tmp_path / "out")
    assert not ok and "Наличност" in message


def test_a_cp1251_stock_file_is_refused_with_the_codec_named(files, tmp_path):
    stock, orders = files
    stock.write_bytes("Артикул,Име,Наличност\nA,Алфа,5\n".encode("cp1251"))
    ok, message, _, _ = _run(stock, orders, tmp_path / "out")
    assert not ok and "codec" in message


def test_validate_csv_headers_reports_what_is_missing(files, tmp_path):
    stock, _ = files
    assert core.validate_csv_headers(str(stock), ["Артикул", "Наличност"]) == (True, [])
    assert core.validate_csv_headers(str(stock), ["Артикул", "Цена"]) == (False, ["Цена"])
    assert core.validate_csv_headers(str(stock), []) == (True, [])
    ok, errors = core.validate_csv_headers(str(tmp_path / "gone.csv"), ["x"])
    assert not ok and errors[0].startswith("File not found")


def test_read_csv_headers_never_raises(files, tmp_path):
    stock, _ = files
    assert core.read_csv_headers(str(stock)) == ["Артикул", "Име", "Наличност"]
    assert core.read_csv_headers(str(tmp_path / "gone.csv")) == []
    assert core.read_csv_headers(str(tmp_path)) == []  # a directory


def test_memory_mode_stock_skips_the_csv_name_check():
    orders = pd.DataFrame({"Name": ["#1"], "Lineitem sku": ["A"], "Lineitem quantity": [1],
                           "Shipping Method": ["DHL"]})
    stock = pd.DataFrame({"SKU": ["A"], "Stock": [5]})
    config = {"column_mappings": MAPPINGS}
    assert core._validate_dataframes(orders, stock, config)  # the CSV header names are missing
    assert core._validate_dataframes(orders, stock, {**config, "_stock_from_memory": True}) == []


def test_a_session_run_creates_a_session_and_copies_its_inputs(files, tmp_path):
    stock, orders = files
    sessions = SessionManager(Profiles(tmp_path))
    ok, _, _, _ = _run(stock, orders, tmp_path / "out", client_id="M", session_manager=sessions,
                       profile_manager=sessions.profile_manager)
    assert ok
    (session,) = [p for p in (tmp_path / "Sessions" / "CLIENT_M").iterdir() if p.is_dir()]
    assert (session / "input" / "orders_export.csv").read_text(encoding="utf-8") == ORDERS
    assert (session / "input" / "inventory.csv").read_text(encoding="utf-8") == STOCK
    data = json.loads((session / "analysis" / "analysis_data.json").read_text(encoding="utf-8"))
    assert data["total_orders"] == 2


def test_a_given_session_path_is_reused(files, tmp_path):
    stock, orders = files
    sessions = SessionManager(Profiles(tmp_path))
    session = sessions.create_session("M")
    ok, _, _, _ = _run(stock, orders, tmp_path / "out", client_id="M", session_manager=sessions,
                       profile_manager=sessions.profile_manager, session_path=str(session))
    assert ok
    assert len([p for p in (tmp_path / "Sessions" / "CLIENT_M").iterdir() if p.is_dir()]) == 1
    assert (Path(session) / "analysis" / "analysis_data.json").exists()


def test_a_failed_state_save_still_writes_the_packing_data(files, tmp_path, monkeypatch, caplog):
    stock, orders = files
    sessions = SessionManager(Profiles(tmp_path))
    session = sessions.create_session("M")

    def locked(self, *a, **k):
        raise PermissionError(13, "in use")

    monkeypatch.setattr(pd.DataFrame, "to_pickle", locked)
    with caplog.at_level("ERROR"):
        ok, _, _, _ = _run(stock, orders, tmp_path / "out", client_id="M", session_manager=sessions,
                           profile_manager=sessions.profile_manager, session_path=str(session))
    assert ok
    assert (Path(session) / "analysis" / "analysis_data.json").exists()
    assert any("Could not save the session state files" in r.getMessage() for r in caplog.records)
