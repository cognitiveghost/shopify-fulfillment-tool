"""Audit 03: rule engine.

Report: docs/audit/03-rule-engine.md. Every AUDIT-03-k test fails because of
the bug it names and is marked xfail(strict=True); the fix removes the marker.
The unmarked tests pin what the audit verified correct. Fixtures are
synthetic and only reproduce the shape of the production configs.
"""

import pandas as pd
import pytest

from gui.rule_test_dialog import RuleTestDialog
from gui.rule_validator import validate_range
from gui.settings.rules import RulesPage
from shopify_tool import core
from shopify_tool.report_filters import fulfillable_only
from shopify_tool.rules import (
    RuleEngine,
    _op_contains,
    _op_date_before,
    _op_does_not_match_regex,
    _parse_range,
)
from shopify_tool.tag_manager import parse_tags


def frame(rows):
    """Analysis-shaped frame: (order, sku, qty) tuples, all Fulfillable."""
    return pd.DataFrame({
        "Order_Number": [r[0] for r in rows],
        "SKU": [r[1] for r in rows],
        "Quantity": [r[2] for r in rows],
        "Product_Name": [f"P-{r[1]}" for r in rows],
        "Order_Fulfillment_Status": ["Fulfillable"] * len(rows),
        "Status_Note": [""] * len(rows),
        "Internal_Tags": ["[]"] * len(rows),
    })


def rule(conditions, actions, level="order", match="ALL", name="r", **extra):
    return {"name": name, "level": level, **extra,
            "steps": [{"conditions": conditions, "match": match, "actions": actions}]}


def cond(field, operator, value=""):
    return {"field": field, "operator": operator, "value": value}


def tag(value):
    return {"type": "ADD_INTERNAL_TAG", "value": value}


def tags_by_order(df):
    return {
        str(o): sorted({t for v in g["Internal_Tags"] for t in parse_tags(v)})
        for o, g in df.groupby("Order_Number")
    }


# --- Findings ---------------------------------------------------------------


def test_order_level_set_status_holds_the_whole_order():
    df = frame([("#1", "A", 4), ("#1", "B", 3), ("#2", "A", 1)])
    hold = rule([cond("total_quantity", "is greater than or equal", "7")],
                [{"type": "SET_STATUS", "value": "Not Fulfillable"}])

    out = RuleEngine([hold]).apply(df)

    # Every report and the Packing Tool hand-off read fulfillable_only().
    assert "#1" not in set(fulfillable_only(out)["Order_Number"])


def _run_with_bonus(tmp_path, bonus_stock):
    (tmp_path / "orders.csv").write_text(
        "Name,Lineitem sku,Lineitem quantity,Shipping Method\n"
        "#1,A,1,DHL\n#2,A,1,DHL\n", encoding="utf-8")
    (tmp_path / "stock.csv").write_text(
        f"Артикул,Име,Наличност\nA,Alpha,5\nGIFT,Gift,{bonus_stock}\n", encoding="utf-8")
    config = {
        "column_mappings": {
            "orders": {"Name": "Order_Number", "Lineitem sku": "SKU",
                       "Lineitem quantity": "Quantity", "Shipping Method": "Shipping_Method"},
            "stock": {"Артикул": "SKU", "Име": "Product_Name", "Наличност": "Stock"},
        },
        "settings": {},
        "rules": [rule([cond("SKU", "equals", "A")],
                       [{"type": "ADD_PRODUCT", "sku": "GIFT", "quantity": 1}],
                       level="article")],
    }
    orders_df, stock_df = core._load_and_validate_files(
        str(tmp_path / "stock.csv"), str(tmp_path / "orders.csv"), ",", ",", config)
    history = pd.DataFrame(columns=["Order_Number", "Execution_Date"])
    final_df = core._run_analysis_and_rules(orders_df, stock_df, history, config)[0]
    return final_df, stock_df


@pytest.mark.xfail(strict=True, reason="AUDIT-03-2: ADD_PRODUCT lines skip the stock simulation")
def test_add_product_cannot_promise_more_stock_than_exists(tmp_path):
    final_df, _ = _run_with_bonus(tmp_path, bonus_stock=1)

    shipped = fulfillable_only(final_df)
    assert shipped.loc[shipped["SKU"] == "GIFT", "Quantity"].sum() <= 1


@pytest.mark.xfail(strict=True, reason="AUDIT-03-2: ADD_PRODUCT lines neither read nor reduce the stock file")
def test_add_product_is_counted_in_final_stock(tmp_path):
    # 5 in stock, 2 given away. Today both lines say Final_Stock 0: GIFT is on
    # no order, so the engine never finds it and falls back to 0.
    final_df, _ = _run_with_bonus(tmp_path, bonus_stock=5)

    gift = final_df[final_df["SKU"] == "GIFT"]
    assert len(gift) == 2
    assert (gift["Final_Stock"] == 3).all()


@pytest.mark.parametrize("value, cell, expected", [
    ("Mask + Box", "Mask + Box Set", True),   # '+' is a quantifier
    (".", "ABC", False),                      # '.' matches any character
    ("(2)", "Set 2", False),                  # parentheses are a group
])
def test_contains_is_literal(value, cell, expected):
    assert bool(_op_contains(pd.Series([cell]), value).iloc[0]) is expected


def test_contains_with_a_bracket_does_not_crash_the_run():
    df = frame([("#1", "A", 1)])
    r = rule([cond("Product_Name", "contains", "(")], [tag("X")], level="article")
    RuleEngine([r]).apply(df)


def test_invalid_negative_regex_matches_nothing():
    result = _op_does_not_match_regex(pd.Series(["A", "B"]), "(")
    assert not result.any()


@pytest.mark.xfail(strict=True, reason="AUDIT-03-5: Save accepts a rule the validator marks as an error")
def test_rules_page_refuses_to_save_an_invalid_rule(qtbot):
    bad = rule([cond("SKU", "matches regex", "(")], [tag("X")], level="article")
    page = RulesPage([bad], pd.DataFrame({"Order_Number": ["#1"], "SKU": ["A"]}))
    qtbot.addWidget(page)

    ok, _errors = page.validate()
    assert not ok


def test_date_operators_read_shopify_timestamps():
    created_at = pd.Series(["2026-01-14 18:56:50 +0200"])
    assert bool(_op_date_before(created_at, "2026-02-01").iloc[0])


def test_negative_operator_means_the_same_on_sku_and_has_sku():
    df = frame([("#1", "A", 1), ("#1", "GIFT", 1)])
    by_field = rule([cond("SKU", "does not equal", "GIFT")], [tag("NO_GIFT")])
    by_has_sku = rule([cond("has_sku", "does not equal", "GIFT")], [tag("NO_GIFT")])

    a = tags_by_order(RuleEngine([by_field]).apply(df.copy()))
    b = tags_by_order(RuleEngine([by_has_sku]).apply(df.copy()))
    assert a == b


@pytest.mark.xfail(strict=True, reason="AUDIT-03-8: rule test dialog previews the already-ruled frame")
def test_rule_test_dialog_reports_rows_the_saved_rule_already_tagged(qtbot, no_modals):
    r = rule([cond("SKU", "equals", "A")], [tag("T")], level="article")
    # What the dialog is given: the results of a run that already applied r.
    analysed = RuleEngine([r]).apply(frame([("#1", "A", 1), ("#2", "B", 1)]))

    dialog = RuleTestDialog(r, analysed)
    qtbot.addWidget(dialog)
    assert dialog.matched_count == 1


@pytest.mark.xfail(strict=True, reason="AUDIT-03-9: validator accepts a reversed range the engine refuses")
@pytest.mark.parametrize("value", ["100-10", "-10-0"])
def test_range_validator_agrees_with_engine(value):
    assert validate_range(value)[0] is (_parse_range(value) is not None)


@pytest.mark.xfail(strict=True, reason="AUDIT-03-10: rule test drops ADD_PRODUCT's quantity")
def test_rule_test_config_keeps_add_product_quantity(qtbot):
    r = rule([cond("SKU", "equals", "A")],
             [{"type": "ADD_PRODUCT", "sku": "GIFT", "quantity": 3}], level="article")
    page = RulesPage([r], pd.DataFrame({"Order_Number": ["#1"], "SKU": ["A"]}))
    qtbot.addWidget(page)

    tested = page._build_rule_config_from_widgets(page.rule_widgets[0])
    assert tested["steps"][0]["actions"][0].get("quantity") == 3


def test_lowercase_match_all_is_all_on_order_rules():
    df = frame([("#1", "A", 1)])
    r = rule([cond("has_sku", "equals", "A"), cond("has_sku", "equals", "B")],
             [tag("AB")], match="all")
    assert tags_by_order(RuleEngine([r]).apply(df)) == {"#1": []}


def test_rules_page_shows_rules_in_execution_order(qtbot):
    second = rule([cond("SKU", "equals", "A")], [tag("X")], level="article", name="runs second", priority=2)
    first = rule([cond("SKU", "equals", "A")], [tag("Y")], level="article", name="runs first", priority=1)
    page = RulesPage([second, first], pd.DataFrame({"Order_Number": ["#1"], "SKU": ["A"]}))
    qtbot.addWidget(page)

    engine_order = [r["name"] for r in RuleEngine([second, first]).rules]
    shown = [w["name_edit"].text() for w in page.rule_widgets]
    assert shown == engine_order


# --- Verified correct -------------------------------------------------------

BOX = "^(01|05)"
MASK = "^02-FACE"
ALMADERM_SHAPED = [
    {"name": "BOX+ANY", "level": "order", "priority": 1, "steps": [
        {"conditions": [cond("has_sku", "matches regex", MASK),
                        cond("has_sku", "matches regex", BOX)],
         "match": "ALL", "actions": [tag("MASK+BOX")]},
        {"conditions": [cond("order_min_box", "equals", "REGULAR_BOX")],
         "match": "ALL", "actions": [tag("REGULAR_BOX")]},
    ]},
    {"name": "MASK ONLY", "level": "order", "priority": 2, "steps": [
        {"conditions": [cond("has_sku", "matches regex", MASK),
                        cond("has_sku", "does not match regex", BOX)],
         "match": "ALL", "actions": [tag("MASK_ONLY")]},
        {"conditions": [cond("total_quantity", "is greater than or equal", "2")],
         "match": "ALL", "actions": [tag("MULTIPLE_MASKS")]},
    ]},
    rule([cond("has_sku", "matches regex", BOX),
          cond("has_sku", "does not match regex", MASK)],
         [tag("BOX_ONLY")], name="BOX ONLY", priority=3),
]


def _almaderm_orders():
    df = frame([
        ("#1", "02-FACE-1", 1), ("#1", "01-F", 1),      # mask + box, regular box
        ("#2", "02-FACE-1", 1), ("#2", "05-G", 1),      # mask + box, unknown dims
        ("#3", "02-FACE-1", 2),                          # two masks only
        ("#4", "02-FACE-2", 1),                          # one mask only
        ("#5", "01-B", 3),                               # box only
    ])
    df["Order_Min_Box"] = df["Order_Number"].map(
        {"#1": "REGULAR_BOX", "#2": "UNKNOWN_DIMS"}).fillna("REGULAR_BOX")
    return df


def test_production_shaped_order_rules_tag_the_right_orders():
    out = RuleEngine(ALMADERM_SHAPED).apply(_almaderm_orders())
    assert tags_by_order(out) == {
        "#1": ["MASK+BOX", "REGULAR_BOX"],
        "#2": ["MASK+BOX"],
        "#3": ["MASK_ONLY", "MULTIPLE_MASKS"],
        "#4": ["MASK_ONLY"],
        "#5": ["BOX_ONLY"],
    }
    # Order tags cover every line of the order, not just the first.
    assert out.groupby("Order_Number")["Internal_Tags"].nunique().eq(1).all()


def test_applying_rules_twice_equals_applying_once():
    engine = RuleEngine(ALMADERM_SHAPED)
    once = engine.apply(_almaderm_orders())
    twice = engine.apply(once.copy())
    pd.testing.assert_frame_equal(once, twice)


def test_total_quantity_bands_are_exhaustive_and_exclusive():
    rules = [
        rule([cond("total_quantity", "is greater than or equal", "7")], [tag("LARGE")], priority=1),
        rule([cond("total_quantity", "is less than or equal", "6")], [tag("REGULAR")], priority=2),
    ]
    df = frame([("#6", "A", 4), ("#6", "B", 2), ("#7", "A", 4), ("#7", "B", 3), ("#1", "A", 1)])
    assert tags_by_order(RuleEngine(rules).apply(df)) == {
        "#1": ["REGULAR"], "#6": ["REGULAR"], "#7": ["LARGE"]}


def test_order_min_box_equals_is_exact():
    rules = [rule([cond("order_min_box", "equals", b)], [tag(f"{b}_BOX")]) for b in ("S", "XS")]
    df = frame([("#1", "A", 1), ("#2", "A", 1), ("#3", "A", 1)])
    df["Order_Min_Box"] = df["Order_Number"].map({"#1": "S", "#2": "XS", "#3": "NO_BOX_FITS"})
    assert tags_by_order(RuleEngine(rules).apply(df)) == {
        "#1": ["S_BOX"], "#2": ["XS_BOX"], "#3": []}


def test_unresolvable_condition_blocks_an_all_step():
    df = frame([("#1", "A", 1)])
    r = rule([cond("SKU", "equals", "A"), cond("No_Such_Column", "equals", "x")],
             [tag("X")], level="article")
    assert tags_by_order(RuleEngine([r]).apply(df)) == {"#1": []}


def test_priority_order_and_chaining():
    """Lower priority number runs first; later rules see earlier rules' writes."""
    df = frame([("#1", "A", 1)])
    later = rule([cond("Internal_Tags", "contains", "FIRST")], [tag("SECOND")],
                 level="article", priority=2)
    earlier = rule([cond("SKU", "equals", "A")], [tag("FIRST")], level="article", priority=1)
    assert tags_by_order(RuleEngine([later, earlier]).apply(df)) == {"#1": ["FIRST", "SECOND"]}


def test_legacy_single_step_rule_keeps_its_meaning():
    df = frame([("#1", "A", 1), ("#2", "B", 1)])
    legacy = {"name": "old", "match": "ANY", "conditions": [cond("SKU", "equals", "A")],
              "actions": [tag("OLD")]}
    modern = rule([cond("SKU", "equals", "A")], [tag("OLD")], level="article", match="ANY")
    a = RuleEngine([legacy]).apply(df.copy())
    b = RuleEngine([modern]).apply(df.copy())
    pd.testing.assert_frame_equal(a, b)
