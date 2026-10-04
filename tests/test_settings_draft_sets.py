"""SetsDraft: the Sets page's values, with no widget (phase 9 spec section 4)."""

import copy

import pytest

from gui.settings.contract import FileProblem
from gui.settings.sets_state import (
    DUPLICATE_SKU,
    LIST_LIMIT,
    NO_COMPONENT,
    NO_SKU,
    QUANTITY_PROBLEM,
    SetsDraft,
)

SETS = {
    "SET-A": [{"sku": "HAT", "quantity": 1}, {"sku": "SCARF", "quantity": 2}],
    "SET-B": [{"sku": "MUG", "quantity": 1, "note": "kept"}],
}


def draft(stored=None):
    return SetsDraft(copy.deepcopy(SETS if stored is None else stored))


def rows(d):
    return d.view()["sets"]["rows"]


def test_it_loads_the_sets_in_stored_order_with_uids_from_one():
    d = draft()
    assert [(row["uid"], row["sku"]) for row in rows(d)] == [("1", "SET-A"), ("2", "SET-B")]
    assert rows(d)[0]["chips"] == ["HAT ×1", "SCARF ×2"]
    assert d.view()["sets"]["count"] == "2 sets"
    assert d.view()["action"] == "Add set"


def test_odd_stored_values_load_without_raising():
    d = draft({"S": "not a list", "T": ["not a dict", {"sku": "A", "quantity": 2.0}], "U": [{"sku": "B", "quantity": "3"}]})
    assert [row["chips"] for row in rows(d)] == [[], ["A ×2"], ["B ×3"]]


def test_an_unedited_draft_collects_what_it_was_given_into_the_live_dict():
    live = copy.deepcopy(SETS)
    d = SetsDraft(live)
    d.mark_clean()
    assert d.collect() == {"set_decoders": SETS}
    assert d.collect()["set_decoders"] is live
    assert not d.is_dirty()


def test_a_components_extra_key_survives():
    d = draft()
    d.apply("comp_quantity", ["2", "0", "4"])
    assert d.collect()["set_decoders"]["SET-B"] == [{"sku": "MUG", "quantity": 4, "note": "kept"}]


def test_open_close_and_filter_change_nothing_that_is_saved():
    d = draft()
    d.mark_clean()
    assert d.apply("open", ["2"])
    assert not d.apply("open", ["2"])
    assert not d.apply("open", ["9"])
    assert rows(d)[1]["open"] and rows(d)[1]["editor"]["components"][0]["sku"] == "MUG"
    assert d.apply("filter", ["scarf"])
    # The filter matches a component; the open set is always listed.
    assert [row["sku"] for row in rows(d)] == ["SET-A", "SET-B"]
    assert d.apply("close", [])
    assert not d.apply("close", [])
    assert [row["sku"] for row in rows(d)] == ["SET-A"]
    assert not d.is_dirty()


def test_a_filter_with_no_hit_says_so():
    d = draft()
    d.apply("filter", [" zzz "])
    assert rows(d) == []
    assert d.view()["sets"]["no_hits"] == "No set matches “zzz”."


def test_set_add_puts_an_open_empty_set_first():
    d = draft()
    assert d.apply("set_add", [])
    first = rows(d)[0]
    assert (first["uid"], first["sku"], first["label"], first["open"]) == ("3", "", "New set", True)
    assert first["editor"]["components"] == [{"sku": "", "quantity": "1", "problem": "", "invalid": False}]


def test_the_edits_change_the_set():
    d = draft()
    assert d.apply("set_sku", ["1", "SET-Z"])
    assert not d.apply("set_sku", ["1", "SET-Z"])
    assert d.apply("comp_add", ["1"])
    assert d.apply("comp_sku", ["1", "2", "GLOVE"])
    assert d.apply("comp_quantity", ["1", "2", "5"])
    assert d.apply("comp_remove", ["1", "0"])
    assert d.collect()["set_decoders"]["SET-Z"] == [
        {"sku": "SCARF", "quantity": 2},
        {"sku": "GLOVE", "quantity": 5},
    ]
    assert d.apply("set_delete", ["1"])
    assert list(d.collect()["set_decoders"]) == ["SET-B"]


@pytest.mark.parametrize(
    ("action", "args"),
    [
        ("set_sku", ["9", "X"]),
        ("set_sku", ["1"]),
        ("set_sku", ["1", 5]),
        ("comp_remove", ["1", "7"]),
        ("comp_remove", ["1", "x"]),
        ("comp_sku", ["1", "9", "X"]),
        ("set_delete", ["9"]),
        ("comp_add", ["9"]),
        ("nonsense", []),
        ("set_add", "not a list"),
    ],
)
def test_an_edit_it_cannot_apply_is_dropped(action, args):
    d = draft()
    d.mark_clean()
    assert not d.apply(action, args)
    assert not d.is_dirty()


def test_a_set_with_no_sku_blocks_the_save():
    d = draft()
    d.apply("set_add", [])
    assert d.blocker() == "Fix the new set"
    assert d.blocker_key() == "set-3-sku"
    row = rows(d)[0]
    assert row["problem"] == NO_SKU
    assert row["editor"]["sku_problem"] == NO_SKU
    assert row["editor"]["components_problem"] == NO_COMPONENT
    assert d.validate() == (False, [f"New set: {NO_SKU}", f"New set: {NO_COMPONENT}"])


def test_a_sku_another_set_has_blocks_the_later_one():
    d = draft()
    d.apply("set_sku", ["2", " SET-A "])
    assert d.blocker() == "Fix set “SET-A”"
    assert d.blocker_key() == "set-2-sku"
    assert rows(d)[0]["problem"] == ""
    assert rows(d)[1]["problem"] == DUPLICATE_SKU


def test_a_set_with_no_named_component_blocks():
    d = draft()
    d.apply("comp_sku", ["2", "0", "  "])
    assert d.blocker_key() == "set-2-comp-add"
    assert rows(d)[1]["problem"] == NO_COMPONENT


@pytest.mark.parametrize("text", ["0", "10000", "1.5", "two", "", "-1"])
def test_a_quantity_that_is_not_a_whole_number_in_range_blocks(text):
    d = draft()
    d.apply("open", ["1"])
    d.apply("comp_quantity", ["1", "1", text])
    assert d.blocker() == "Fix set “SET-A”"
    assert d.blocker_key() == "set-1-c1-quantity"
    part = rows(d)[0]["editor"]["components"][1]
    assert (part["problem"], part["invalid"]) == (QUANTITY_PROBLEM, True)
    assert d.validate() == (False, [f"Set “SET-A”: {QUANTITY_PROBLEM}"])
    # collect() does not raise: the value is written as typed.
    assert d.collect()["set_decoders"]["SET-A"][1]["quantity"] == text


def test_nothing_blocks_an_unedited_draft():
    d = draft()
    assert d.blocker() is None
    assert d.blocker_key() == ""
    assert d.validate() == (True, [])


def test_reveal_opens_the_set_a_key_belongs_to():
    d = draft()
    assert d.apply("reveal", ["set-2-c0-quantity"])
    assert rows(d)[1]["open"]
    assert not d.apply("reveal", ["rule-2-name"])


def test_a_row_lists_six_chips_and_counts_the_rest():
    d = draft({"BIG": [{"sku": f"C{n}", "quantity": 1} for n in range(9)]})
    row = rows(d)[0]
    assert len(row["chips"]) == 6
    assert row["more_chips"] == "+3 more"


def test_the_list_stops_at_the_limit_and_says_so():
    d = draft({f"S{n}": [{"sku": "A", "quantity": 1}] for n in range(LIST_LIMIT + 2)})
    assert len(rows(d)) == LIST_LIMIT
    assert d.view()["sets"]["more"] == f"Showing {LIST_LIMIT} of {LIST_LIMIT + 2}. Filter to find the rest."


def test_with_no_set_the_page_shows_the_empty_state():
    d = draft({})
    view = d.view()
    assert view["action"] == ""
    assert view["sets"]["empty"]["title"] == "No sets yet"
    assert view["sets"]["can_export"] is False
    assert view["sets"]["count"] == "0 sets"


def _csv(tmp_path, text, name="sets.csv"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_a_merge_import_updates_a_listed_set_and_appends_a_new_one(tmp_path):
    d = draft()
    d.apply("open", ["1"])
    path = _csv(tmp_path, "Set_SKU,Component_SKU,Component_Quantity\nSET-A,CAP,3\nSET-C,BAG,1\n")
    assert d.import_csv("sets-merge", path) == ("Imported 2 sets from sets.csv", False)
    assert d.collect()["set_decoders"] == {
        "SET-A": [{"sku": "CAP", "quantity": 3}],
        "SET-B": [{"sku": "MUG", "quantity": 1, "note": "kept"}],
        "SET-C": [{"sku": "BAG", "quantity": 1}],
    }
    assert d.open_uid is None


def test_a_replace_import_drops_every_other_set(tmp_path):
    d = draft()
    path = _csv(tmp_path, "Set_SKU,Component_SKU,Component_Quantity\nSET-C,BAG,1\n")
    assert d.import_csv("sets-replace", path) == ("Replaced all sets with 1 from sets.csv", False)
    assert list(d.collect()["set_decoders"]) == ["SET-C"]


def test_a_file_with_no_sets_is_a_problem_the_operator_can_act_on(tmp_path):
    d = draft()
    path = _csv(tmp_path, "Set_SKU,Component_SKU,Component_Quantity\n", "empty.csv")
    with pytest.raises(FileProblem) as raised:
        d.import_csv("sets-merge", path)
    assert raised.value.headline == "No sets found in empty.csv"
    assert raised.value.detail == "Each row needs Set_SKU, Component_SKU and Component_Quantity."
    assert list(d.collect()["set_decoders"]) == ["SET-A", "SET-B"]


def test_a_file_with_the_wrong_columns_raises_and_changes_nothing(tmp_path):
    d = draft()
    with pytest.raises(ValueError):
        d.import_csv("sets-merge", _csv(tmp_path, "a,b\n1,2\n"))
    assert list(d.collect()["set_decoders"]) == ["SET-A", "SET-B"]


def test_export_writes_what_would_be_saved(tmp_path):
    d = draft()
    out = tmp_path / "out.csv"
    assert d.export_csv("sets", out) == "Exported 2 sets to out.csv"
    again = SetsDraft({})
    again.import_csv("sets-merge", out)
    assert again.collect()["set_decoders"] == {
        "SET-A": [{"sku": "HAT", "quantity": 1}, {"sku": "SCARF", "quantity": 2}],
        "SET-B": [{"sku": "MUG", "quantity": 1}],
    }


def test_an_unknown_kind_is_refused():
    d = draft()
    with pytest.raises(ValueError):
        d.import_csv("boxes", "x.csv")
    with pytest.raises(ValueError):
        d.export_csv("boxes", "x.csv")
