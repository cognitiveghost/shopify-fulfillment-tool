"""OrdersDraft: courier names and additional columns, with no widget
(phase 7 spec section 4.4)."""

import copy

import pytest

from gui.settings.page_state import (
    ADDITIONAL_COLUMNS_UNREADABLE,
    ADDITIONAL_UNKNOWN,
    COURIER_EMPTY,
    NOT_IN_FILE,
    FileColumns,
    OrdersDraft,
    StockDraft,
)

ORDERS = {
    "Name": "Order_Number",
    "Lineitem sku": "SKU",
    "Lineitem quantity": "Quantity",
    "Shipping Method": "Shipping_Method",
}
COURIERS = {
    "DHL": {"patterns": ["dhl", "DHL Express"], "case_sensitive": False},
    "DPD": {"patterns": ["dpd"], "case_sensitive": False},
}
FILE = FileColumns(
    name="orders-30-09.csv",
    columns=(
        "Name",
        "Lineitem sku",
        "Lineitem quantity",
        "Shipping Method",
        "Notes",
        "Discount Code",
    ),
    first_row={"Name": "#10482", "Notes": "leave at door"},
    loaded=True,
)


def _entry(name, enabled=True, order_level=True, exists=True):
    return {
        "csv_name": name,
        "internal_name": name.replace(" ", "_"),
        "enabled": enabled,
        "is_order_level": order_level,
        "exists_in_df": exists,
    }


def _draft(additional=None, couriers=None, file=FILE, fallback=None, key=True):
    live = {"version": 2, "orders": dict(ORDERS), "stock": {"Article": "SKU"}}
    if key:
        live["additional_columns"] = copy.deepcopy(additional or [])
    live_couriers = copy.deepcopy(COURIERS if couriers is None else couriers)
    draft = OrdersDraft(live, live_couriers, "ACME", fallback, file)
    return draft, live, live_couriers


def _rows(draft):
    return [(row["text"], row["code"]) for row in draft.view()["mapping"]["couriers"]["rows"]]


def _additional(draft):
    return draft.view()["mapping"]["additional"]


def _names(items):
    return [item["name"] for item in items]


# --- courier names -----------------------------------------------------------


def test_each_stored_pattern_is_a_row():
    draft, _live, _couriers = _draft()
    assert _rows(draft) == [("dhl", "DHL"), ("DHL Express", "DHL"), ("dpd", "DPD")]
    assert draft.view()["mapping"]["couriers"]["codes"] == ["DHL", "DPD"]


def test_courier_names_round_trip_untouched():
    draft, _live, couriers = _draft()
    before = copy.deepcopy(couriers)
    assert draft.collect()["courier_mappings"] is couriers
    assert couriers == before


def test_a_legacy_entry_loads_as_a_row_and_is_saved_in_the_new_shape():
    """{"dhl": "DHL"} is still matched by the analysis; the old page dropped it."""
    draft, _live, couriers = _draft(couriers={"dhl": "DHL", "speedy": "Speedy"})
    assert _rows(draft) == [("dhl", "DHL"), ("speedy", "Speedy")]
    draft.collect()
    assert couriers == {
        "DHL": {"patterns": ["dhl"], "case_sensitive": False},
        "Speedy": {"patterns": ["speedy"], "case_sensitive": False},
    }


def test_no_mappings_shows_the_empty_sentence_and_no_rows():
    draft, _live, couriers = _draft(couriers={})
    view = draft.view()["mapping"]["couriers"]
    assert view["rows"] == []
    assert view["empty"] == COURIER_EMPTY
    draft.collect()
    assert couriers == {}


def test_a_new_row_is_saved_once_it_has_both_sides():
    draft, _live, couriers = _draft()
    assert draft.apply("courier_add", []) is True
    assert _rows(draft)[-1] == ("", "")
    draft.collect()
    assert "" not in couriers and len(couriers) == 2

    draft.apply("courier_pattern", ["3", "evri"])
    draft.collect()
    assert len(couriers) == 2

    draft.apply("courier_code", ["3", " Evri "])
    draft.collect()
    assert couriers["Evri"] == {"patterns": ["evri"], "case_sensitive": False}
    assert list(couriers) == ["DHL", "DPD", "Evri"]


def test_a_row_given_an_existing_courier_joins_its_patterns():
    draft, _live, couriers = _draft()
    draft.apply("courier_add", [])
    draft.apply("courier_pattern", ["3", "dpd classic"])
    draft.apply("courier_code", ["3", "DPD"])
    draft.collect()
    assert couriers["DPD"]["patterns"] == ["dpd", "dpd classic"]


def test_removing_a_couriers_last_row_removes_the_courier():
    """The live dict is cleared and refilled: an update() would leave DPD behind."""
    draft, _live, couriers = _draft()
    assert draft.apply("courier_remove", ["2"]) is True
    draft.collect()
    assert list(couriers) == ["DHL"]


def test_a_repeated_text_is_saved_once_and_spaces_are_trimmed():
    draft, _live, couriers = _draft()
    draft.apply("courier_add", [])
    draft.apply("courier_pattern", ["3", "  dhl  "])
    draft.apply("courier_code", ["3", "DHL"])
    draft.collect()
    assert couriers["DHL"]["patterns"] == ["dhl", "DHL Express"]


def test_the_typed_text_is_kept_as_typed_in_the_view():
    draft, _live, _couriers = _draft()
    draft.apply("courier_pattern", ["0", "dhl "])
    assert _rows(draft)[0] == ("dhl ", "DHL")


@pytest.mark.parametrize(
    ("action", "args"),
    [
        ("courier_pattern", ["9", "x"]),
        ("courier_pattern", ["-1", "x"]),
        ("courier_pattern", ["one", "x"]),
        ("courier_pattern", [0, "x"]),
        ("courier_code", ["0", "   "]),
        ("courier_code", ["0"]),
        ("courier_remove", ["9"]),
        ("courier_remove", []),
        ("courier_add", ["x"]),
        ("column_add", ["No Such Column"]),
        ("column_remove", ["No Such Column"]),
        ("column_fill", ["Notes", "yes"]),
        ("nope", []),
    ],
)
def test_an_edit_it_does_not_know_is_dropped(action, args):
    draft, _live, _couriers = _draft(additional=[_entry("Notes")])
    before = draft.snapshot()
    assert draft.apply(action, args) is False
    assert draft.snapshot() == before


def test_it_still_takes_column_edits():
    draft, live, _couriers = _draft()
    assert draft.apply("column", ["Notes", "Notes"]) is True
    draft.collect()
    assert live["orders"]["Notes"] == "Notes"


# --- additional columns: where the list comes from (ADR 0006) ----------------


def test_without_the_key_the_old_client_config_list_is_shown():
    draft, _live, _couriers = _draft(key=False, fallback=[_entry("Notes")])
    assert _names(_additional(draft)["chips"]) == ["Notes"]


def test_the_mappings_key_wins_over_the_fallback():
    draft, _live, _couriers = _draft(
        additional=[_entry("Notes")], fallback=[_entry("Discount Code")]
    )
    assert _names(_additional(draft)["chips"]) == ["Notes"]


def test_a_stored_entry_gets_every_key_it_lacks():
    draft, live, _couriers = _draft(additional=[{"csv_name": "Gift Note"}], file=None)
    draft.collect()
    assert live["additional_columns"] == [
        {
            "csv_name": "Gift Note",
            "internal_name": "Gift_Note",
            "enabled": False,
            "is_order_level": True,
            "exists_in_df": True,
        }
    ]


def test_an_unreadable_client_config_leaves_the_stored_list_alone():
    draft, live, _couriers = _draft(key=False, fallback=ADDITIONAL_COLUMNS_UNREADABLE)
    assert _additional(draft)["notice"] == ADDITIONAL_UNKNOWN
    assert _additional(draft)["chips"] == []
    draft.collect()
    assert "additional_columns" not in live


def test_keeping_a_column_after_an_unreadable_config_saves_again():
    draft, live, _couriers = _draft(key=False, fallback=ADDITIONAL_COLUMNS_UNREADABLE)
    assert draft.apply("column_add", ["Notes"]) is True
    assert _additional(draft)["notice"] == ""
    draft.collect()
    assert [e["csv_name"] for e in live["additional_columns"]] == ["Notes"]


# --- additional columns: keeping and letting go ------------------------------


def test_reading_a_file_offers_its_unmapped_columns_and_stores_nothing():
    draft, live, _couriers = _draft()
    additional = _additional(draft)
    assert additional["chips"] == []
    assert _names(additional["candidates"]) == ["Discount Code", "Notes"]
    assert additional["group"] == "Unmapped columns in orders-30-09.csv"
    assert additional["empty"] == "None kept."
    draft.collect()
    assert live["additional_columns"] == []


def test_keeping_a_candidate_stores_it_enabled_and_filled_down():
    draft, live, _couriers = _draft()
    assert draft.apply("column_add", ["Discount Code"]) is True
    assert _additional(draft)["chips"] == [
        {"name": "Discount Code", "note": "", "fill": True}
    ]
    assert _names(_additional(draft)["candidates"]) == ["Notes"]
    draft.collect()
    assert live["additional_columns"] == [
        {
            "csv_name": "Discount Code",
            "internal_name": "Discount_Code",
            "enabled": True,
            "is_order_level": True,
            "exists_in_df": True,
        }
    ]


def test_removing_a_chip_turns_the_entry_off_and_keeps_it():
    draft, live, _couriers = _draft(additional=[_entry("Notes")])
    assert draft.apply("column_remove", ["Notes"]) is True
    assert _additional(draft)["chips"] == []
    assert "Notes" in _names(_additional(draft)["candidates"])
    draft.collect()
    assert live["additional_columns"][0]["enabled"] is False
    assert draft.apply("column_remove", ["Notes"]) is False


def test_a_column_turned_off_earlier_can_be_kept_again():
    draft, _live, _couriers = _draft(additional=[_entry("Notes", enabled=False)])
    assert draft.apply("column_add", ["Notes"]) is True
    assert len(draft.entries) == 1
    assert draft.entries[0]["enabled"] is True
    assert draft.apply("column_add", ["Notes"]) is False


def test_fill_down_is_the_order_level_flag():
    draft, live, _couriers = _draft(additional=[_entry("Notes")])
    assert draft.apply("column_fill", ["Notes", False]) is True
    assert _additional(draft)["chips"] == [
        {"name": "Notes", "note": "not filled down", "fill": False}
    ]
    draft.collect()
    assert live["additional_columns"][0]["is_order_level"] is False
    assert draft.apply("column_fill", ["Notes", False]) is False


def test_a_kept_column_the_file_lacks_says_so():
    draft, _live, _couriers = _draft(
        additional=[_entry("Gift Note", order_level=False)]
    )
    assert _additional(draft)["chips"] == [
        {"name": "Gift Note", "note": f"{NOT_IN_FILE}, not filled down", "fill": False}
    ]


def test_with_no_file_only_columns_turned_off_earlier_are_offered():
    draft, _live, _couriers = _draft(
        additional=[_entry("Notes"), _entry("Gift Note", enabled=False)], file=None
    )
    additional = _additional(draft)
    assert additional["chips"] == [{"name": "Notes", "note": "", "fill": True}]
    assert additional["candidates"] == [{"name": "Gift Note", "note": ""}]
    assert additional["group"] == "Turned off earlier"


def test_the_add_button_says_why_it_has_nothing_to_offer():
    none_read, _live, _couriers = _draft(file=None)
    assert _additional(none_read)["add_title"] == (
        "Use Read columns from CSV… to list the file's unmapped columns."
    )
    all_used, _live, _couriers = _draft(
        additional=[_entry("Notes"), _entry("Discount Code")]
    )
    assert _additional(all_used)["add_title"] == (
        "Every column in this file is mapped or kept."
    )
    some, _live, _couriers = _draft()
    assert _additional(some)["add_title"] == ""


def test_mapping_a_kept_column_to_a_field_lets_go_of_it():
    """A column is a field or an additional column, never both."""
    draft, live, _couriers = _draft(additional=[_entry("Notes")])
    draft.apply("column", ["Notes", "Notes"])
    assert _additional(draft)["chips"] == []
    assert "Notes" not in _names(_additional(draft)["candidates"])
    draft.collect()
    assert live["additional_columns"][0]["enabled"] is False
    assert live["orders"]["Notes"] == "Notes"


# --- unsaved -----------------------------------------------------------------


def test_each_kind_of_edit_reads_unsaved():
    for action, args in [
        ("column", ["Notes", "Notes"]),
        ("courier_remove", ["0"]),
        ("column_add", ["Notes"]),
    ]:
        draft, _live, _couriers = _draft()
        draft.mark_clean()
        draft.apply(action, args)
        assert draft.is_dirty() is True, action


def test_an_empty_new_row_is_not_an_unsaved_change():
    """Only what would be written counts: a row with one side is not saved."""
    draft, _live, _couriers = _draft()
    draft.mark_clean()
    draft.apply("courier_add", [])
    assert draft.is_dirty() is False


def test_an_edit_on_orders_leaves_stock_clean():
    draft, live, _couriers = _draft()
    stock = StockDraft(live, "ACME")
    draft.mark_clean()
    stock.mark_clean()
    draft.apply("column_add", ["Notes"])
    draft.collect()
    assert draft.is_dirty() is True
    assert stock.is_dirty() is False
