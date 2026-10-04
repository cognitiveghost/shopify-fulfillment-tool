"""WeightDraft: the Weight page's values, with no widget (phase 9 spec section 5)."""

import copy

import pandas as pd
import pytest

from gui.settings.contract import FileProblem
from gui.settings.weight_state import (
    DIVISOR_PROBLEM,
    NO_NAME_HINT,
    NO_SKU_HINT,
    NUMBER_PROBLEM,
    PRODUCT_LIMIT,
    WeightDraft,
    number_text,
    parse_number,
)

CONFIG = {
    "volumetric_divisor": 5000,
    "products": {
        "SKU1": {"name": "Widget", "length_cm": 10.0, "width_cm": 5.0, "height_cm": 2.0, "no_packaging": False},
        "SKU2": {"name": "Gadget", "length_cm": 0.0, "width_cm": 0.0, "height_cm": 0.0, "no_packaging": True, "note": "kept"},
    },
    "boxes": [{"name": "Small", "length_cm": 20.0, "width_cm": 15.0, "height_cm": 10.0}],
    "legacy_weight_key": 123,
}
MAPPINGS = {"stock": {"Артикул": "SKU", "Име": "Product_Name"}}


def draft(config=None, mappings=None):
    return WeightDraft(copy.deepcopy(CONFIG if config is None else config), mappings or MAPPINGS, "auto")


def products(d):
    return d.view()["weight"]["products"]["rows"]


def boxes(d):
    return d.view()["weight"]["boxes"]["rows"]


def _csv(tmp_path, text, name="file.csv"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("stored", "text"), [(12.0, "12"), (12.5, "12.5"), (0, ""), (0.0, ""), (None, ""), ("", ""), ("7", "7"), ("abc", "abc")]
)
def test_a_stored_dimension_reads_without_a_trailing_zero(stored, text):
    assert number_text(stored) == text


@pytest.mark.parametrize(
    ("text", "number"),
    [("", 0.0), (" 12 ", 12.0), ("12,5", 12.5), ("0", 0.0), ("-1", None), ("abc", None), ("nan", None), ("inf", None)],
)
def test_a_typed_dimension_is_a_number_zero_or_more(text, number):
    assert parse_number(text) == number


def test_it_loads_the_divisor_the_products_and_the_boxes():
    d = draft()
    view = d.view()["weight"]
    assert view["divisor"]["value"] == "5000"
    assert view["divisor"]["problem"] == ""
    assert [(p["uid"], p["sku"], p["name"], p["l"], p["w"], p["h"]) for p in products(d)] == [
        ("1", "SKU1", "Widget", "10", "5", "2"),
        ("2", "SKU2", "Gadget", "", "", ""),
    ]
    assert products(d)[0]["weight"] == "0.02 kg"
    assert products(d)[1]["weight"] == ""
    assert products(d)[1]["no_packaging"] is True
    assert [(b["uid"], b["name"], b["weight"]) for b in boxes(d)] == [("3", "Small", "0.6 kg")]
    assert view["products"]["count"] == "2 products, 1 with no size"


def test_an_empty_config_loads_as_the_defaults():
    d = WeightDraft({}, {}, "auto")
    view = d.view()["weight"]
    assert view["divisor"]["value"] == "6000"
    assert view["products"]["empty"] == "No products yet. Add one, or import them from a CSV."
    assert view["products"]["can_export"] is False
    assert view["boxes"]["empty"] == "No boxes yet."
    assert d.collect() == {"weight_config": {"volumetric_divisor": 6000, "products": {}, "boxes": []}}


def test_an_unedited_draft_collects_what_it_was_given_into_the_live_dict():
    live = copy.deepcopy(CONFIG)
    d = WeightDraft(live, MAPPINGS, "auto")
    d.mark_clean()
    assert d.collect() == {"weight_config": CONFIG}
    assert d.collect()["weight_config"] is live
    assert not d.is_dirty()


def test_the_edits_change_what_is_saved():
    d = draft()
    assert d.apply("divisor", ["6000"])
    assert d.apply("product_text", ["1", "l", "12,5"])
    assert not d.apply("product_text", ["1", "l", "12,5"])
    assert d.apply("product_text", ["1", "name", " Big widget "])
    assert d.apply("product_no_packaging", ["1", True])
    assert not d.apply("product_no_packaging", ["1", True])
    assert d.apply("box_text", ["3", "h", "12"])
    saved = d.collect()["weight_config"]
    assert saved["volumetric_divisor"] == 6000
    assert saved["products"]["SKU1"] == {
        "name": "Big widget", "length_cm": 12.5, "width_cm": 5.0, "height_cm": 2.0, "no_packaging": True,
    }
    assert saved["products"]["SKU2"]["note"] == "kept"
    assert saved["boxes"][0]["height_cm"] == 12.0
    assert saved["legacy_weight_key"] == 123


def test_add_and_remove():
    d = draft()
    assert d.apply("product_add", [])
    assert products(d)[0]["uid"] == "4"
    assert products(d)[0]["sku"] == ""
    assert d.apply("box_add", [])
    assert boxes(d)[-1]["uid"] == "5"
    # A row with no SKU or no name is not saved.
    assert list(d.collect()["weight_config"]["products"]) == ["SKU1", "SKU2"]
    assert len(d.collect()["weight_config"]["boxes"]) == 1
    assert d.apply("product_remove", ["1"])
    assert d.apply("box_remove", ["3"])
    assert not d.apply("box_remove", ["3"])
    assert list(d.collect()["weight_config"]["products"]) == ["SKU2"]


@pytest.mark.parametrize(
    ("action", "args"),
    [
        ("divisor", [6000]),
        ("product_text", ["1", "no_packaging", "x"]),
        ("product_text", ["9", "l", "1"]),
        ("box_text", ["3", "sku", "x"]),
        ("product_no_packaging", ["1", "yes"]),
        ("product_remove", ["9"]),
        ("reveal", ["box-3-l"]),
        ("reveal", ["product-9-l"]),
        ("nonsense", []),
    ],
)
def test_an_edit_it_cannot_apply_is_dropped(action, args):
    d = draft()
    d.mark_clean()
    assert not d.apply(action, args)
    assert not d.is_dirty()


@pytest.mark.parametrize("text", ["", "0", "100001", "6000.5", "abc"])
def test_a_divisor_that_is_not_a_whole_number_in_range_blocks(text):
    d = draft()
    d.apply("divisor", [text])
    assert d.blocker() == "Set Divisor"
    assert d.blocker_key() == "divisor"
    assert d.view()["weight"]["divisor"]["problem"] == DIVISOR_PROBLEM
    assert d.validate() == (False, [f"Divisor: {DIVISOR_PROBLEM}"])
    assert products(d)[0]["weight"] == ""
    assert d.collect()["weight_config"]["volumetric_divisor"] == text


def test_a_dimension_that_is_not_a_number_blocks_and_marks_its_field():
    d = draft()
    d.apply("product_text", ["1", "w", "wide"])
    assert d.blocker() == "Fix product “SKU1”"
    assert d.blocker_key() == "product-1-w"
    row = products(d)[0]
    assert (row["problem"], row["invalid"], row["weight"]) == (NUMBER_PROBLEM, ["w"], "")
    assert d.validate() == (False, [f"Product “SKU1”: {NUMBER_PROBLEM}"])
    assert d.collect()["weight_config"]["products"]["SKU1"]["width_cm"] == "wide"

    d = draft()
    d.apply("box_text", ["3", "l", "-4"])
    assert d.blocker() == "Fix box “Small”"
    assert d.blocker_key() == "box-3-l"
    assert boxes(d)[0]["invalid"] == ["l"]


def test_a_sku_listed_twice_blocks_the_later_row():
    d = draft()
    d.apply("product_text", ["2", "sku", " SKU1 "])
    assert d.blocker() == "Fix product “SKU1”"
    assert d.blocker_key() == "product-2-sku"
    assert products(d)[0]["problem"] == ""
    assert (products(d)[1]["problem"], products(d)[1]["invalid"]) == ("SKU1 is in the list twice.", ["sku"])


def test_a_row_that_will_not_be_saved_says_so_without_blocking():
    d = draft()
    d.apply("product_add", [])
    assert products(d)[0]["hint"] == ""
    d.apply("product_text", ["4", "l", "3"])
    assert products(d)[0]["hint"] == NO_SKU_HINT
    d.apply("box_add", [])
    d.apply("box_text", ["5", "w", "3"])
    assert boxes(d)[-1]["hint"] == NO_NAME_HINT
    assert d.blocker() is None
    assert d.validate() == (True, [])


def test_the_filter_keeps_matches_and_rows_with_no_sku():
    d = draft()
    d.apply("product_add", [])
    assert d.apply("product_filter", ["gadg"])
    assert [p["sku"] for p in products(d)] == ["", "SKU2"]
    d.apply("product_filter", ["zzz"])
    d.apply("product_remove", ["4"])
    assert products(d) == []
    assert d.view()["weight"]["products"]["no_hits"] == "No product matches “zzz”."


def test_the_list_stops_at_the_limit_and_reveal_lists_a_row_past_it():
    many = {f"S{n:04d}": {"name": "", "length_cm": 1, "width_cm": 1, "height_cm": 1} for n in range(PRODUCT_LIMIT + 5)}
    d = draft({"volumetric_divisor": 6000, "products": many, "boxes": []})
    view = d.view()["weight"]["products"]
    assert len(view["rows"]) == PRODUCT_LIMIT
    assert view["more"] == f"Showing {PRODUCT_LIMIT} of {PRODUCT_LIMIT + 5}. Filter to find the rest."
    assert view["count"] == f"{PRODUCT_LIMIT + 5} products"
    last = str(PRODUCT_LIMIT + 5)
    assert d.apply("reveal", [f"product-{last}-l"])
    assert not d.apply("reveal", [f"product-{last}-l"])
    assert products(d)[-1]["uid"] == last
    assert len(products(d)) == PRODUCT_LIMIT + 1


def test_a_stock_csv_adds_the_skus_not_listed_with_their_names(tmp_path):
    d = draft()
    path = _csv(tmp_path, "Артикул;Име;Наличност\nSKU1;Widget;4\nNEW-1;New one;2\nNEW-1;Again;1\n;;\n")
    assert d.import_csv("products-stock", path) == ("Added 1. Skipped 1 already existing.", False)
    assert [(p["sku"], p["name"]) for p in products(d)] == [("SKU1", "Widget"), ("SKU2", "Gadget"), ("NEW-1", "New one")]


def test_a_stock_csv_falls_back_to_a_common_sku_column(tmp_path):
    d = draft(mappings={"stock": {}})
    path = _csv(tmp_path, "SKU,Qty\nA1,1\n")
    assert d.import_csv("products-stock", path)[0] == "Added 1. Skipped 0 already existing."


def test_a_stock_csv_with_no_sku_column_is_a_problem_the_operator_can_act_on(tmp_path):
    d = draft(mappings={"stock": {}})
    with pytest.raises(FileProblem) as raised:
        d.import_csv("products-stock", _csv(tmp_path, "Code,Qty\nA1,1\n"))
    assert raised.value.headline == "No SKU column found"
    assert raised.value.detail == "Check the Stock mapping page, then import again."


DIMS = "SKU;Name;L (cm);W (cm);H (cm);No Packaging\nSKU1;Renamed;11;6;3;yes\nNEW-2;Fresh;1,5;2;x;\n"


def test_a_dimensions_csv_adds_new_skus_and_skips_listed_ones(tmp_path):
    d = draft()
    path = _csv(tmp_path, DIMS)
    assert d.import_csv("products-dims", path) == ("Added 1. Skipped 1 already in the table.", True)
    assert [(p["sku"], p["name"], p["l"], p["w"], p["h"]) for p in products(d)] == [
        ("SKU1", "Widget", "10", "5", "2"),
        ("SKU2", "Gadget", "", "", ""),
        ("NEW-2", "Fresh", "1.5", "2", ""),
    ]


def test_update_them_takes_the_files_values_for_listed_skus(tmp_path):
    d = draft()
    path = _csv(tmp_path, DIMS)
    d.import_csv("products-dims", path)
    assert d.import_csv("products-dims", path, update=True) == ("Added 0. Updated 2.", False)
    first = products(d)[0]
    assert (first["name"], first["l"], first["w"], first["h"], first["no_packaging"]) == ("Renamed", "11", "6", "3", True)


def test_an_update_leaves_alone_what_the_file_has_no_column_for(tmp_path):
    d = draft()
    d.import_csv("products-dims", _csv(tmp_path, "sku,length\nSKU1,99\n"), update=True)
    first = products(d)[0]
    assert (first["name"], first["l"], first["w"]) == ("Widget", "99", "5")


def test_a_dimensions_csv_with_no_sku_column_names_the_columns_it_has(tmp_path):
    d = draft()
    with pytest.raises(FileProblem) as raised:
        d.import_csv("products-dims", _csv(tmp_path, "Code,L\nA,1\n"))
    assert raised.value.headline == "No SKU column found"
    assert raised.value.detail == "Available columns: Code, L. Expected one of: SKU, Артикул, Article, Код."


def test_a_boxes_csv_adds_skips_and_updates(tmp_path):
    d = draft()
    path = _csv(tmp_path, "Box Name;L;W;H\nSmall;21;16;11\nLarge;40;30;20\n")
    assert d.import_csv("boxes", path) == ("Added 1. Skipped 1 already in the table.", True)
    assert [(b["name"], b["l"]) for b in boxes(d)] == [("Small", "20"), ("Large", "40")]
    assert d.import_csv("boxes", path, update=True) == ("Added 0. Updated 2.", False)
    assert boxes(d)[0]["l"] == "21"
    with pytest.raises(FileProblem) as raised:
        d.import_csv("boxes", _csv(tmp_path, "Code,L\nA,1\n", "bad.csv"))
    assert raised.value.headline == "No box name column found"
    assert raised.value.detail == "Available columns: Code, L. Expected one of: Name, Box Name, Size, Box."


def test_the_exports_write_every_row_as_shown(tmp_path):
    d = draft()
    out = tmp_path / "products.csv"
    assert d.export_csv("products", out) == "Exported 2 products."
    written = pd.read_csv(out, sep=";", dtype=str, encoding="utf-8-sig", keep_default_na=False)
    assert list(written.columns) == ["SKU", "Name", "L (cm)", "W (cm)", "H (cm)", "No Packaging"]
    assert written.iloc[0].tolist() == ["SKU1", "Widget", "10", "5", "2", "False"]
    out = tmp_path / "boxes.csv"
    assert d.export_csv("boxes", out) == "Exported 1 boxes."
    written = pd.read_csv(out, sep=";", dtype=str, encoding="utf-8-sig")
    assert written.iloc[0].tolist() == ["Small", "20", "15", "10"]
    # What was exported imports back.
    again = WeightDraft({}, {}, "auto")
    again.import_csv("boxes", out)
    assert again.collect()["weight_config"]["boxes"] == CONFIG["boxes"]


def test_an_unknown_kind_is_refused():
    d = draft()
    with pytest.raises(ValueError):
        d.import_csv("sets-merge", "x.csv")
    with pytest.raises(ValueError):
        d.export_csv("sets", "x.csv")


def test_a_product_being_typed_stays_listed_when_it_stops_matching_the_filter():
    d = draft()
    d.apply("product_filter", ["gadg"])
    d.apply("product_add", [])
    new = products(d)[0]["uid"]
    assert d.apply("product_text", [new, "sku", "TEE-09"])
    assert [p["sku"] for p in products(d)] == ["TEE-09", "SKU2"]
    d.apply("product_text", ["2", "name", "Renamed"])
    assert [p["sku"] for p in products(d)] == ["SKU2"]


def test_a_row_with_no_name_is_called_the_new_one():
    d = draft({"volumetric_divisor": 6000, "products": {}, "boxes": []})
    d.apply("product_add", [])
    d.apply("box_add", [])
    d.apply("product_text", [products(d)[0]["uid"], "l", "x"])
    d.apply("box_text", [boxes(d)[0]["uid"], "l", "x"])
    assert d.validate() == (
        False,
        [f"The new product: {NUMBER_PROBLEM}", f"The new box: {NUMBER_PROBLEM}"],
    )


def test_a_stored_number_is_shown_whole():
    assert number_text(12.34567) == "12.34567"
    assert number_text(0.1 + 0.2) == "0.3"
