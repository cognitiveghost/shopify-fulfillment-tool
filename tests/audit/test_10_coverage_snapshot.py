"""Audit 10: production snapshot findings and bugs found by the coverage pass.

Report: docs/audit/10-coverage-and-snapshot.md. Every AUDIT-10-k test was committed failing, as
xfail(strict=True), before its fix removed the marker. Fixtures are synthetic; the production replay
lives in tests/replay/.
"""
from pathlib import Path

import pandas as pd
import pytest

from shopify_tool import report_jobs


@pytest.mark.parametrize(
    ("report_type", "filename", "expected"),
    [("packing_lists", "ALL.xls", "ALL.xlsx"), ("stock_exports", "ERP", "ERP.xls")],
)
def test_report_names_already_normalised(report_type, filename, expected, tmp_path):
    out = report_jobs._output_file(report_type, "X", {"output_filename": filename}, tmp_path)
    assert Path(out).name == expected


@pytest.mark.xfail(strict=True, reason="AUDIT-10-1: .XLSX is not normalised")
@pytest.mark.parametrize(
    ("report_type", "filename", "expected"),
    [
        ("packing_lists", "MASKS.XLSX", "MASKS.xlsx"),
        ("packing_lists", "ALL", "ALL.xlsx"),
        ("packing_lists", "ALL.v2", "ALL.v2.xlsx"),
        ("stock_exports", "ERP.XLS", "ERP.xls"),
        ("stock_exports", "ERP.xlsx", "ERP.xls"),
    ],
)
def test_audit_10_1_report_names_get_one_lower_case_extension(report_type, filename, expected, tmp_path):
    out = report_jobs._output_file(report_type, "X", {"output_filename": filename}, tmp_path)
    assert Path(out).name == expected


@pytest.mark.xfail(strict=True, reason="AUDIT-10-1: .XLSX fails in pd.ExcelWriter")
def test_audit_10_1_an_upper_case_name_still_writes_the_packing_list(tmp_path):
    frame = pd.DataFrame(
        {"Order_Number": ["#1001"], "SKU": ["A"], "Quantity": [1], "Stock": [5],
         "Order_Fulfillment_Status": ["Fulfillable"], "Shipping_Provider": ["DHL"],
         "Destination_Country": ["BG"], "Warehouse_Name": ["W-A"], "Product_Name": ["PA"],
         "Internal_Tags": ["[]"]}
    )
    config = {"name": "MASKS", "report_type": "packing_lists", "output_filename": "MASKS.XLSX", "filters": []}
    outcome = report_jobs.generate_report(config, tmp_path, frame, {}, "s")
    assert not outcome.failed
    assert (tmp_path / "packing_lists" / "MASKS.xlsx").exists()
    assert (tmp_path / "packing_lists" / "MASKS.json").exists()
