from datetime import datetime
from pathlib import Path

import pandas as pd
from anonymise import (
    OrderMap,
    clean_config,
    config_of_day,
    mask_text,
    orders_frame,
    packing_doc,
    rule_words,
)
from replay import first_difference


def test_order_map_keeps_prefix_length_and_order():
    omap = OrderMap(["#1500", "#1203", "#987", "BG-77"])
    assert omap.map("#1203") == "#1001"
    assert omap.map("#1500") == "#1002"
    assert omap.map("#987") == "#101"
    assert omap.map("BG-77") == "BG-11"
    assert omap.map("") == ""


def test_order_map_without_digits_and_whitespace():
    omap = OrderMap(["ABC", " #12 "])
    assert omap.map("ABC") == "ORD1"
    assert omap.map("#12") == omap.map(" #12 ") == "#11"


CONFIG = {"column_mappings": {"orders": {"Name": "Order_Number", "Shipping Name": "Customer",
                                         "Notes": "Notes", "Lineitem sku": "SKU"},
                              "additional_columns": [{"csv_name": "Financial Status", "enabled": True}]},
          "inventory_memory": {"skus": {}}, "last_updated": "x", "updated_by": "PC"}


def test_orders_frame_keeps_only_mapped_columns_and_masks_people():
    raw = pd.DataFrame({"Name": ["#12", "#12"], "Shipping Name": ["Real Person", ""],
                        "Notes": ["call me", ""], "Lineitem sku": ["A", "B"], "Email": ["a@b.c", ""],
                        "Financial Status": ["paid", "paid"], "_source_file": ["shop.csv", "shop.csv"]})
    out = orders_frame(raw, CONFIG, OrderMap(["#12"]))
    assert list(out.columns) == ["Name", "Shipping Name", "Notes", "Lineitem sku", "Financial Status", "_source_file"]
    assert list(out["Name"]) == ["#11", "#11"]
    assert list(out["Shipping Name"]) == ["Customer", ""]
    assert list(out["Notes"]) == ["Note", ""]


def test_packing_doc_maps_numbers_and_masks_notes():
    doc = {"analyzed_at": "t", "orders": [{"order_number": "#12", "notes": "call me", "items": []},
                                         {"order_number": "#13", "notes": "", "items": []},
                                         {"order_number": "#14", "notes": "nan", "items": []}]}
    out = packing_doc(doc, OrderMap(["#12", "#13", "#14"]))
    assert [o["order_number"] for o in out["orders"]] == ["#11", "#12", "#13"]
    assert [o["notes"] for o in out["orders"]] == ["Note", "", "nan"]  # "nan" is an empty cell, no words
    assert doc["orders"][0]["order_number"] == "#12"  # input untouched


def test_clean_config_drops_derived_and_machine_keys():
    assert set(clean_config(CONFIG)) == {"column_mappings"}


def test_config_of_day_takes_the_first_backup_after_the_session():
    created = datetime.fromisoformat("2026-10-05T11:07:09+03:00")
    b = [(datetime(2026, 10, 5, 9), Path("b1")), (datetime(2026, 10, 5, 12), Path("b2")),
         (datetime(2026, 10, 6, 9), Path("b3"))]
    assert config_of_day(b, Path("cur"), created) == (Path("b2"), True)
    assert config_of_day(b[1:], Path("cur"), created) == (Path("b2"), False)  # older ones rotated away
    assert config_of_day(b[:1], Path("cur"), created) == (Path("cur"), True)  # nothing saved since


def test_first_difference_ignores_time_stamps_and_names_the_changed_order():
    base = {"analyzed_at": "t1", "total_orders": 1,
            "orders": [{"order_number": "#11", "items": [{"sku": "A", "quantity": 1}]}]}
    same = {**base, "analyzed_at": "t2"}
    assert first_difference(base, same) is None
    changed = {**base, "orders": [{"order_number": "#11", "items": [{"sku": "A", "quantity": 2}]}]}
    message = first_difference(base, changed)
    assert "#11" in message and "items" in message


RULES = {"rules": [{"steps": [{"conditions": [{"field": "Notes", "operator": "contains", "value": "LUX"},
                                                {"field": "SKU", "operator": "equals", "value": "A"}]}]}]}


def test_rule_words_finds_the_values_rules_compare_a_field_with():
    assert rule_words(RULES, "Notes") == ["LUX"]
    assert rule_words(RULES, "Customer") == []


def test_mask_text_keeps_only_what_a_rule_reads():
    assert mask_text("please make it lux, call Real Person", "Note", ["LUX"]) == "lux"
    assert mask_text("call Real Person", "Note", ["LUX"]) == "Note"
    assert mask_text("", "Note", ["LUX"]) == ""


def test_orders_frame_and_packing_doc_mask_notes_alike_when_a_rule_reads_them():
    config = {**CONFIG, **RULES}
    raw = pd.DataFrame({"Name": ["#12"], "Shipping Name": [""], "Notes": ["LUX for Real Person"],
                        "Lineitem sku": ["A"], "Financial Status": ["paid"], "_source_file": ["s.csv"]})
    omap = OrderMap(["#12"])
    assert list(orders_frame(raw, config, omap)["Notes"]) == ["LUX"]
    doc = {"orders": [{"order_number": "#12", "notes": "LUX for Real Person", "items": []}]}
    assert packing_doc(doc, omap, rule_words(config, "Notes"))["orders"][0]["notes"] == "LUX"
