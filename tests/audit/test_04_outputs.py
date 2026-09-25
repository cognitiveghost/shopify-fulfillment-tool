"""Audit 04: outputs (packing lists, stock exports, reference labels, barcodes).

Report: docs/audit/04-outputs.md. Every AUDIT-04-k test fails because of the
bug it names and is marked xfail(strict=True); the fix removes the marker.
The unmarked tests pin what the audit verified correct. Fixtures are
synthetic and only reproduce the shape of the production data.
"""

import csv
import json
from io import BytesIO
from unittest.mock import MagicMock

import pandas as pd
import pypdf
import pytest
from reportlab.pdfgen import canvas

from gui.actions_handler import ActionsHandler
from shopify_tool import pdf_processor, stock_export
from shopify_tool.barcode_processor import (
    generate_barcodes_batch,
    generate_code128_labels_pdf,
    generate_qr_labels_pdf,
)
from shopify_tool.packing_lists import create_packing_list
from shopify_tool.pdf_processor import (
    load_csv_mapping,
    match_reference,
    process_reference_labels,
    sort_pages_by_reference,
)
from shopify_tool.stock_export import create_stock_export
from shopify_tool.tag_manager import merge_tags

FF, NF = "Fulfillable", "Not Fulfillable"


def frame(rows):
    """Analysis-shaped frame from (order, sku, qty, status) tuples."""
    return pd.DataFrame({
        "Order_Number": [r[0] for r in rows],
        "SKU": [r[1] for r in rows],
        "Quantity": [r[2] for r in rows],
        "Order_Fulfillment_Status": [r[3] for r in rows],
        "Product_Name": [f"P-{r[1]}" for r in rows],
        "Warehouse_Name": [f"W-{r[1]}" for r in rows],
        "Shipping_Provider": ["DHL"] * len(rows),
        "Destination_Country": ["BG"] * len(rows),
        "Internal_Tags": ["[]"] * len(rows),
        "Status_Note": [""] * len(rows),
        "System_note": [""] * len(rows),
    })


def xlsx_lines(path):
    x = pd.read_excel(path, dtype={"Order_Number": str, "SKU": str})
    return x.groupby(["Order_Number", "SKU"])["Quantity"].sum().to_dict()


def json_lines(path):
    lines = {}
    for order in json.loads(path.read_text(encoding="utf-8"))["orders"]:
        for item in order["items"]:
            key = (order["order_number"], item["sku"])
            lines[key] = lines.get(key, 0) + item["quantity"]
    return lines


def export_totals(path):
    e = pd.read_excel(path, dtype={"Артикул": str})
    return e.groupby("Артикул")["Брой"].sum().to_dict()


def handler_for(df):
    """ActionsHandler over a stand-in main window: the real report path
    (XLSX + JSON for Packing Tool) with no session bookkeeping."""
    mw = MagicMock()
    mw.analysis_results_df = df
    mw.session_path = None
    return ActionsHandler(mw)


def packing_config(**extra):
    return {"name": "ALL", "output_filename": "ALL.xlsx",
            "filters": [{"field": "Order_Fulfillment_Status", "operator": "==",
                         "value": "Fulfillable"}], **extra}


def label(order, tag="N/A", seq=1):
    return {"order_number": order, "safe_order_number": order, "sequential_num": seq,
            "courier": "DHL", "country": "BG", "tag": tag, "item_count": 1}


def pdf_pages(path):
    return len(pypdf.PdfReader(str(path)).pages)


def text_pdf(path, page_texts):
    """A courier-label stand-in: one page per text, text extractable by pypdf."""
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(288, 432))
    for text in page_texts:
        for i, line in enumerate(text.split("\n")):
            c.drawString(20, 400 - 14 * i, line)
        c.showPage()
    c.save()
    path.write_bytes(buf.getvalue())
    return path


def mapping_csv(path, rows):
    """Shipments CSV: col 0 PostOne id, 1 tracking, 2 reference, 6 name."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["postone", "tracking", "ref", "c3", "c4", "c5", "name"])
        for postone, tracking, ref, name in rows:
            w.writerow([postone, tracking, ref, "", "", "", name])
    return path


# --- Findings ---------------------------------------------------------------


@pytest.mark.xfail(strict=True, reason="AUDIT-04-1: labels after an untagged order are dropped from the PDF")
def test_barcode_pdf_has_a_page_for_every_label(tmp_path):
    out = generate_code128_labels_pdf(
        [label("#1", "BOX"), label("#2", ""), label("#3", "BOX")], tmp_path / "b.pdf")
    assert pdf_pages(out) == 3


@pytest.mark.xfail(strict=True, reason="AUDIT-04-1: labels after an untagged order are dropped from the PDF")
def test_qr_pdf_has_a_page_for_every_label(tmp_path):
    out = generate_qr_labels_pdf(
        [label("#1", "BOX"), label("#2", ""), label("#3", "BOX")], tmp_path / "q.pdf")
    assert pdf_pages(out) == 3


@pytest.mark.xfail(strict=True, reason="AUDIT-04-1: an order with no internal tags yields an empty tag and truncates the PDF")
def test_orders_without_internal_tags_all_get_a_label(tmp_path):
    # The barcode tab's own path: tags merged per order, then batched.
    orders = pd.DataFrame({
        "Order_Number": ["#1", "#2", "#3"], "Shipping_Provider": "DHL",
        "Destination_Country": "BG", "item_count": 1,
        "Internal_Tags": [merge_tags(["[]"])] * 3,
    })
    records = [r for r in generate_barcodes_batch(orders) if r["success"]]
    out = generate_code128_labels_pdf(records, tmp_path / "b.pdf")
    assert pdf_pages(out) == 3


@pytest.mark.xfail(strict=True, reason="AUDIT-04-2: a failed stock export write is reported as success")
def test_stock_export_write_failure_is_not_silent(tmp_path, monkeypatch):
    def locked(*_args, **_kwargs):
        raise PermissionError("file is open in the ERP")

    monkeypatch.setattr(stock_export, "_write_xls", locked)
    with pytest.raises(PermissionError):
        create_stock_export(frame([("#1", "A", 1, FF)]), str(tmp_path / "e.xls"))


@pytest.mark.xfail(strict=True, reason="AUDIT-04-3: an empty packing list leaves the previous XLSX/JSON in place")
def test_regenerating_an_empty_packing_list_replaces_the_old_files(tmp_path):
    df = frame([("#1", "A", 1, FF), ("#2", "B", 2, FF)])
    handler = handler_for(df)
    handler._generate_single_report("packing_lists", packing_config(), tmp_path)
    assert (tmp_path / "packing_lists" / "ALL.json").exists()

    # Every order is held afterwards, then the list is generated again.
    handler.mw.analysis_results_df = df.assign(Order_Fulfillment_Status=NF)
    handler._generate_single_report("packing_lists", packing_config(), tmp_path)

    # Neither file may still hand out the held orders.
    out = tmp_path / "packing_lists"
    assert not (out / "ALL.json").exists() or json_lines(out / "ALL.json") == {}
    assert not (out / "ALL.xlsx").exists() or xlsx_lines(out / "ALL.xlsx") == {}


@pytest.mark.xfail(strict=True, reason="AUDIT-04-4: exclude_skus matches differently in the XLSX and the JSON")
def test_packing_list_json_excludes_the_same_skus_as_the_xlsx(tmp_path):
    df = frame([("#1", "7", 1, FF), ("#1", "B", 1, FF)])
    handler_for(df)._generate_single_report(
        "packing_lists", packing_config(exclude_skus=["07"]), tmp_path)
    out = tmp_path / "packing_lists"
    assert json_lines(out / "ALL.json") == xlsx_lines(out / "ALL.xlsx")


@pytest.mark.xfail(strict=True, reason="AUDIT-04-5: distinct order numbers sanitise to the same barcode value")
def test_distinct_orders_never_share_a_barcode_value():
    orders = pd.DataFrame({
        "Order_Number": ["#1001/2", "#1001 2", "#10012"], "Shipping_Provider": "DHL",
        "Destination_Country": "BG", "Internal_Tags": "[]", "item_count": 1,
    })
    encoded = [r["safe_order_number"] for r in generate_barcodes_batch(orders) if r["success"]]
    assert len(encoded) == len(set(encoded))


@pytest.mark.xfail(strict=True, reason="AUDIT-04-6: outputs take an order's fulfillable lines even when another SKU line is blocked")
def test_packing_list_never_lists_part_of_an_order(tmp_path):
    df = frame([("#1", "A", 1, FF), ("#1", "GIFT", 1, NF), ("#2", "C", 1, FF)])
    create_packing_list(df, str(tmp_path / "p.xlsx"))
    listed = {o for o, _ in xlsx_lines(tmp_path / "p.xlsx")}
    assert "#1" not in listed or ("#1", "GIFT") in xlsx_lines(tmp_path / "p.xlsx")


@pytest.mark.xfail(strict=True, reason="AUDIT-04-6: outputs take an order's fulfillable lines even when another SKU line is blocked")
def test_stock_export_never_writes_off_part_of_an_order(tmp_path):
    df = frame([("#1", "A", 1, FF), ("#1", "GIFT", 1, NF), ("#2", "C", 1, FF)])
    create_stock_export(df, str(tmp_path / "e.xls"))
    assert export_totals(tmp_path / "e.xls") == {"C": 1}


@pytest.mark.xfail(strict=True, reason="AUDIT-04-7: name fallback is a substring match, first CSV row wins")
def test_name_fallback_picks_the_exact_customer(tmp_path):
    mapping = load_csv_mapping(mapping_csv(tmp_path / "m.csv", [
        ("", "", "100", "Ivan Petrov"),
        ("", "", "200", "Ivan Petrova"),
    ]))
    page = "Recipient:\nIvan Petrova\nSofia"
    assert match_reference(page, mapping)["ref"] == "200"


@pytest.mark.xfail(strict=True, reason="AUDIT-04-7: two customers with one name share whichever reference was read last")
def test_name_fallback_refuses_an_ambiguous_name(tmp_path):
    mapping = load_csv_mapping(mapping_csv(tmp_path / "m.csv", [
        ("", "", "100", "Maria Ivanova"),
        ("", "", "200", "Maria Ivanova"),
    ]))
    assert match_reference("Recipient:\nMaria Ivanova", mapping) is None


@pytest.mark.xfail(strict=True, reason="AUDIT-04-8: a reference stamped on two pages is not reported")
def test_reference_run_reports_a_reference_on_two_pages(tmp_path):
    pdf = text_pdf(tmp_path / "in.pdf", ["P1234567890 A", "P1234567890 B"])
    csv_path = mapping_csv(tmp_path / "m.csv", [("P1234567890", "", "100", "Ann Lee")])
    out = tmp_path / "out"
    out.mkdir()
    result = process_reference_labels(str(pdf), str(csv_path), str(out))
    assert result.get("duplicate_refs") == ["100"]


@pytest.mark.xfail(strict=True, reason="AUDIT-04-8: a reference with no courier page is not reported")
def test_reference_run_reports_a_reference_without_a_page(tmp_path):
    pdf = text_pdf(tmp_path / "in.pdf", ["P1234567890"])
    csv_path = mapping_csv(tmp_path / "m.csv", [
        ("P1234567890", "", "100", "Ann Lee"),
        ("P2234567890", "", "200", "Bob Stone"),
    ])
    out = tmp_path / "out"
    out.mkdir()
    result = process_reference_labels(str(pdf), str(csv_path), str(out))
    assert result.get("missing_refs") == ["200"]


@pytest.mark.xfail(strict=True, reason="AUDIT-04-9: a page whose stamp failed is still counted as matched")
def test_unstamped_page_is_not_counted_as_matched(tmp_path, monkeypatch):
    def broken(*_args, **_kwargs):
        raise RuntimeError("overlay failed")

    monkeypatch.setattr(pdf_processor, "_stamp_reference", broken)
    pdf = text_pdf(tmp_path / "in.pdf", ["P1234567890"])
    csv_path = mapping_csv(tmp_path / "m.csv", [("P1234567890", "", "100", "Ann Lee")])
    out = tmp_path / "out"
    out.mkdir()
    assert process_reference_labels(str(pdf), str(csv_path), str(out))["matched"] == 0


@pytest.mark.xfail(strict=True, reason="AUDIT-04-10: configured columns are ignored when lot tracking is active")
def test_configured_columns_apply_with_lot_tracking(tmp_path):
    df = frame([("#1", "A", 2, FF)])
    df["Lot_Details"] = [[{"qty_allocated": 2, "expiry": "2027-01", "batch": "L1"}]]
    create_packing_list(df, str(tmp_path / "p.xlsx"), columns=["Order_Number", "SKU", "Quantity"])
    assert "Destination_Country" not in pd.read_excel(tmp_path / "p.xlsx").columns


@pytest.mark.xfail(strict=True, reason="AUDIT-04-11: tracking-shaped references sort by an embedded digit run")
def test_tracking_shaped_reference_sorts_after_numeric_references():
    pages = [{"ref": r, "original_order": i} for i, r in enumerate(["#1002", "HW1ABC2DEF", "#1001"])]
    assert [p["ref"] for p in sort_pages_by_reference(pages)] == ["#1001", "#1002", "HW1ABC2DEF"]


# --- Verified correct -------------------------------------------------------


def test_packing_list_xlsx_and_json_carry_exactly_the_fulfillable_lines(tmp_path):
    df = frame([
        ("#10", "A", 2, FF), ("#10", "B", 1, FF), ("#9", "A", 1, FF),
        ("#11", "C", 5, NF), ("#12", "A", 1, FF), ("#12", "A", 3, FF),
    ])
    handler_for(df)._generate_single_report("packing_lists", packing_config(), tmp_path)
    out = tmp_path / "packing_lists"
    expected = {("#10", "A"): 2, ("#10", "B"): 1, ("#9", "A"): 1, ("#12", "A"): 4}
    assert xlsx_lines(out / "ALL.xlsx") == expected
    assert json_lines(out / "ALL.json") == expected
    header = json.loads((out / "ALL.json").read_text(encoding="utf-8"))
    assert (header["total_orders"], header["total_items"]) == (3, 8)


def test_packing_list_is_in_numeric_order_number_order(tmp_path):
    df = frame([("#10", "A", 1, FF), ("#9", "A", 1, FF), ("#100", "A", 1, FF)])
    create_packing_list(df, str(tmp_path / "p.xlsx"))
    listed = pd.read_excel(tmp_path / "p.xlsx", dtype={"Order_Number": str})["Order_Number"]
    assert listed.tolist() == ["#9", "#10", "#100"]


def test_packing_list_lot_rows_keep_the_order_quantity(tmp_path):
    lots = [{"qty_allocated": 3, "expiry": "2027-01", "batch": "L1"},
            {"qty_allocated": 1, "expiry": "2027-06", "batch": "L2"}]
    df = frame([("#1", "A", 2, FF), ("#1", "A", 2, FF)])
    df["Lot_Details"] = [lots, lots]  # one allocation object per (order, SKU)
    create_packing_list(df, str(tmp_path / "p.xlsx"))
    assert xlsx_lines(tmp_path / "p.xlsx") == {("#1", "A"): 4}


def test_stock_export_totals_equal_fulfillable_quantities(tmp_path):
    df = frame([("#1", "A", 2, FF), ("#2", "A", 1, FF), ("#2", "B", 4, FF), ("#3", "B", 9, NF)])
    create_stock_export(df, str(tmp_path / "e.xls"))
    assert export_totals(tmp_path / "e.xls") == {"A": 3, "B": 4}


def test_stock_export_lot_rows_sum_to_the_allocation(tmp_path):
    lots = [{"qty_allocated": 3, "expiry": "2027-01", "batch": "L1"},
            {"qty_allocated": 1, "expiry": "2027-06", "batch": "L2"}]
    df = frame([("#1", "A", 2, FF), ("#1", "A", 2, FF)])
    df["Lot_Details"] = [lots, lots]
    create_stock_export(df, str(tmp_path / "e.xls"))
    e = pd.read_excel(tmp_path / "e.xls", dtype={"Артикул": str})
    assert e["Брой"].tolist() == [3, 1]


def test_barcode_value_is_the_order_number_unchanged():
    numbers = ["#1001", "#BG10129", "00123", "1001", "#1001-2", "A_b-9"]
    orders = pd.DataFrame({
        "Order_Number": numbers, "Shipping_Provider": "DHL",
        "Destination_Country": "BG", "Internal_Tags": "[]", "item_count": 1,
    })
    records = generate_barcodes_batch(orders)
    assert [r["safe_order_number"] for r in records] == numbers
    assert [r["sequential_num"] for r in records] == list(range(1, len(numbers) + 1))


def test_reference_strip_barcode_encodes_the_reference_exactly(monkeypatch):
    seen = []
    real = pdf_processor.code128.Code128

    def spy(value, **kwargs):
        seen.append(value)
        return real(value, **kwargs)

    monkeypatch.setattr(pdf_processor.code128, "Code128", spy)
    for ref in ("#107480", "00042", "123456"):
        pdf_processor.create_reference_overlay(ref, 288, 432)
    assert seen == ["#107480", "00042", "123456"]


def test_postone_id_beats_the_name_fallback(tmp_path):
    mapping = load_csv_mapping(mapping_csv(tmp_path / "m.csv", [
        ("P1234567890", "", "100", "Ann Lee"),
        ("P2234567890", "", "200", "Ann Lee Smith"),
    ]))
    assert match_reference("P2234567890\nAnn Lee Smith", mapping)["ref"] == "200"


def test_reference_run_sorts_pages_by_reference_and_keeps_every_page(tmp_path):
    pdf = text_pdf(tmp_path / "in.pdf", ["P2000000000", "no id here", "P1000000000"])
    csv_path = mapping_csv(tmp_path / "m.csv", [
        ("P1000000000", "", "#9", "Ann Lee"),
        ("P2000000000", "", "#10", "Bob Stone"),
    ])
    out = tmp_path / "out"
    out.mkdir()
    result = process_reference_labels(str(pdf), str(csv_path), str(out))
    assert (result["matched"], result["unmatched"]) == (2, 1)
    texts = [p.extract_text() for p in pypdf.PdfReader(result["output_file"]).pages]
    assert ["REF: #9" in texts[0], "REF: #10" in texts[1], "REF" not in texts[2]] == [True, True, True]
