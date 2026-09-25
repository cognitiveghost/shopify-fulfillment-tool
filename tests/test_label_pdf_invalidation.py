from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd

import gui.actions_handler as ah
from gui.actions_handler import ActionsHandler
from shopify_tool.barcode_processor import invalidate_label_pdfs


def _config():
    return {"name": "ALL", "output_filename": "ALL.xlsx", "filters": []}


def _df(status="Fulfillable"):
    return pd.DataFrame({
        "Order_Number": ["#1"], "SKU": ["A"], "Quantity": [1],
        "Order_Fulfillment_Status": [status], "Shipping_Provider": ["DHL"],
        "Destination_Country": ["BG"], "Warehouse_Name": ["W"],
        "Product_Name": ["P"], "Internal_Tags": ["[]"],
    })


def _handler(df):
    mw = MagicMock()
    mw.analysis_results_df = df
    mw.session_path = None
    return ActionsHandler(mw)


def test_invalidate_deletes_both_label_pdfs_and_nothing_else(tmp_path):
    d = tmp_path / "barcodes" / "ALL"
    d.mkdir(parents=True)
    for name in ("ALL_barcodes.pdf", "ALL_qr_labels.pdf", "keep.txt"):
        (d / name).write_bytes(b"x")
    removed = invalidate_label_pdfs(tmp_path, "ALL")
    assert sorted(p.name for p in removed) == ["ALL_barcodes.pdf", "ALL_qr_labels.pdf"]
    assert [p.name for p in d.iterdir()] == ["keep.txt"]


def test_invalidate_without_a_barcodes_folder_is_a_no_op(tmp_path):
    assert invalidate_label_pdfs(tmp_path, "ALL") == []


def test_regenerating_a_list_drops_its_label_pdfs(tmp_path):
    d = tmp_path / "barcodes" / "ALL"
    d.mkdir(parents=True)
    (d / "ALL_barcodes.pdf").write_bytes(b"old")
    _handler(_df())._generate_single_report("packing_lists", _config(), tmp_path)
    assert not (d / "ALL_barcodes.pdf").exists()
    assert (tmp_path / "packing_lists" / "ALL.xlsx").exists()


def test_empty_list_says_so_instead_of_report_saved(tmp_path):
    h = _handler(_df())
    h._generate_single_report("packing_lists", _config(), tmp_path)
    h.mw.analysis_results_df = _df("Not Fulfillable")
    h._generate_single_report("packing_lists", _config(), tmp_path)
    msg = h.mw.statusBar.return_value.showMessage.call_args[0][0]
    assert msg == "No orders matched ALL; its old files were removed"


def test_empty_list_with_its_file_open_reports_the_lock(tmp_path, monkeypatch):
    # Review Focus 4: Excel holding ALL.xlsx open on Windows.
    h = _handler(_df())
    h._generate_single_report("packing_lists", _config(), tmp_path)
    h.mw.analysis_results_df = _df("Not Fulfillable")
    real_unlink = Path.unlink

    def locked(self, *a, **k):
        if self.suffix == ".xlsx":
            raise PermissionError(13, "in use", str(self))
        return real_unlink(self, *a, **k)

    monkeypatch.setattr(Path, "unlink", locked)
    shown = MagicMock()
    monkeypatch.setattr(ah, "show_error", shown)
    h._generate_single_report("packing_lists", _config(), tmp_path)
    assert "ALL.xlsx is open in another program" in shown.call_args[0][2]


def test_a_locked_label_pdf_stops_the_run_before_the_list_changes(tmp_path, monkeypatch):
    # A PDF held open in a viewer must not leave a new XLSX beside the old JSON.
    h = _handler(_df())
    h._generate_single_report("packing_lists", _config(), tmp_path)
    xlsx = tmp_path / "packing_lists" / "ALL.xlsx"
    json_file = tmp_path / "packing_lists" / "ALL.json"
    before = (xlsx.read_bytes(), json_file.read_bytes())
    (tmp_path / "barcodes" / "ALL").mkdir(parents=True)
    (tmp_path / "barcodes" / "ALL" / "ALL_barcodes.pdf").write_bytes(b"old")
    real_unlink = Path.unlink

    def locked(self, *a, **k):
        if self.suffix == ".pdf":
            raise PermissionError(13, "in use", str(self))
        return real_unlink(self, *a, **k)

    monkeypatch.setattr(Path, "unlink", locked)
    shown = MagicMock()
    monkeypatch.setattr(ah, "show_error", shown)
    h.mw.analysis_results_df = pd.concat([_df(), _df().assign(Order_Number="#2")])
    h._generate_single_report("packing_lists", _config(), tmp_path)
    assert "ALL_barcodes.pdf is open in another program" in shown.call_args[0][2]
    assert (xlsx.read_bytes(), json_file.read_bytes()) == before
