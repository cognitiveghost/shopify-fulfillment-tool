"""Core fulfillment simulation accuracy (priority #1: order dataframe accuracy).

Uses the REAL default Shopify/Bulgarian-ERP column names (column_mappings=None)
so these tests exercise exactly the code path production traffic takes.
"""
import pandas as pd
import pytest

from shopify_tool import analysis


def _orders(rows):
    defaults = {"Name": "", "Lineitem sku": "", "Lineitem quantity": 1, "Shipping Method": "Standard"}
    return pd.DataFrame([{**defaults, **r} for r in rows])


def _stock(rows):
    defaults = {"Артикул": "", "Име": "", "Наличност": 0}
    return pd.DataFrame([{**defaults, **r} for r in rows])


def _history(rows=None):
    rows = rows or []
    return pd.DataFrame(rows, columns=["Order_Number", "Execution_Date"])


def _run(orders_df, stock_df, history_df=None, **kwargs):
    if history_df is None:
        history_df = _history()
    return analysis.run_analysis(stock_df, orders_df, history_df, **kwargs)


class TestBasicFulfillment:
    def test_sufficient_stock_is_fulfillable_and_deducts_exactly(self):
        orders = _orders([{"Name": "#1001", "Lineitem sku": "A1", "Lineitem quantity": 3}])
        stock = _stock([{"Артикул": "A1", "Наличност": 10}])
        final_df, _present, _missing, _stats = _run(orders, stock)
        row = final_df.iloc[0]
        assert row["Order_Fulfillment_Status"] == "Fulfillable"
        assert row["Stock"] == 10
        assert row["Final_Stock"] == 7

    def test_insufficient_stock_is_not_fulfillable_with_reason(self):
        orders = _orders([{"Name": "#1001", "Lineitem sku": "A1", "Lineitem quantity": 5}])
        stock = _stock([{"Артикул": "A1", "Наличност": 3}])
        final_df, *_ = _run(orders, stock)
        row = final_df.iloc[0]
        assert row["Order_Fulfillment_Status"] == "Not Fulfillable"
        assert "Insufficient stock" in row["System_note"]
        assert row["Final_Stock"] == 3  # untouched -- order wasn't fulfilled

    def test_zero_stock_reason_says_out_of_stock(self):
        orders = _orders([{"Name": "#1001", "Lineitem sku": "A1", "Lineitem quantity": 1}])
        stock = _stock([{"Артикул": "A1", "Наличност": 0}])
        final_df, *_ = _run(orders, stock)
        assert "Out of stock" in final_df.iloc[0]["System_note"]

    def test_sku_absent_from_stock_file_entirely_is_not_fulfillable(self):
        orders = _orders([{"Name": "#1001", "Lineitem sku": "GHOST", "Lineitem quantity": 1}])
        stock = _stock([{"Артикул": "A1", "Наличност": 10}])
        final_df, *_ = _run(orders, stock)
        assert final_df.iloc[0]["Order_Fulfillment_Status"] == "Not Fulfillable"

    def test_all_or_nothing_partial_order_not_fulfillable(self):
        # Order needs A1(ok) + A2(short) -- whole order must fail, not partially ship.
        orders = _orders([
            {"Name": "#1001", "Lineitem sku": "A1", "Lineitem quantity": 1},
            {"Name": "#1001", "Lineitem sku": "A2", "Lineitem quantity": 5},
        ])
        stock = _stock([
            {"Артикул": "A1", "Наличност": 10},
            {"Артикул": "A2", "Наличност": 1},
        ])
        final_df, *_ = _run(orders, stock)
        assert (final_df["Order_Fulfillment_Status"] == "Not Fulfillable").all()
        # Neither SKU should have been decremented since the order didn't ship.
        assert final_df[final_df["SKU"] == "A1"].iloc[0]["Final_Stock"] == 10


class TestPrioritization:
    def test_multi_first_favors_multi_item_order_over_earlier_single_item_order(self):
        # Only 5 units of A1 exist. #1001 (single item, needs 5) is numerically first,
        # but #1002 (2-item order, needs 5 of A1 + 1 of B1) should win under multi_first.
        orders = _orders([
            {"Name": "#1001", "Lineitem sku": "A1", "Lineitem quantity": 5},
            {"Name": "#1002", "Lineitem sku": "A1", "Lineitem quantity": 5},
            {"Name": "#1002", "Lineitem sku": "B1", "Lineitem quantity": 1},
        ])
        stock = _stock([
            {"Артикул": "A1", "Наличност": 5},
            {"Артикул": "B1", "Наличност": 5},
        ])
        final_df, *_ = _run(orders, stock, mode="multi_first")
        status_by_order = final_df.groupby("Order_Number")["Order_Fulfillment_Status"].first()
        assert status_by_order["#1002"] == "Fulfillable"
        assert status_by_order["#1001"] == "Not Fulfillable"

    def test_fifo_mode_favors_older_order_number_regardless_of_item_count(self):
        orders = _orders([
            {"Name": "#1001", "Lineitem sku": "A1", "Lineitem quantity": 5},
            {"Name": "#1002", "Lineitem sku": "A1", "Lineitem quantity": 5},
            {"Name": "#1002", "Lineitem sku": "B1", "Lineitem quantity": 1},
        ])
        stock = _stock([
            {"Артикул": "A1", "Наличност": 5},
            {"Артикул": "B1", "Наличност": 5},
        ])
        final_df, *_ = _run(orders, stock, mode="fifo")
        status_by_order = final_df.groupby("Order_Number")["Order_Fulfillment_Status"].first()
        assert status_by_order["#1001"] == "Fulfillable"
        assert status_by_order["#1002"] == "Not Fulfillable"

    def test_priority_tie_break_uses_numeric_not_lexicographic_order_sort(self):
        # Only 1 unit total; #9 and #10 both single-item -- numeric sort must pick #9
        # first (lexicographic sort would incorrectly rank "#10" before "#9").
        orders = _orders([
            {"Name": "#10", "Lineitem sku": "A1", "Lineitem quantity": 1},
            {"Name": "#9", "Lineitem sku": "A1", "Lineitem quantity": 1},
        ])
        stock = _stock([{"Артикул": "A1", "Наличност": 1}])
        final_df, *_ = _run(orders, stock, mode="fifo")
        status_by_order = final_df.groupby("Order_Number")["Order_Fulfillment_Status"].first()
        assert status_by_order["#9"] == "Fulfillable"
        assert status_by_order["#10"] == "Not Fulfillable"


class TestSkuNormalizationAcrossFiles:
    def test_float_artifact_sku_matches_between_orders_and_stock(self):
        # Orders CSV keeps SKU string "5170"; stock CSV has it exported as a
        # bare number that pandas would read as float unless dtype forced --
        # normalize_sku must make both converge so the merge doesn't silently
        # produce a stock-less (Not Fulfillable) result for a real match.
        orders = _orders([{"Name": "#1", "Lineitem sku": "5170", "Lineitem quantity": 1}])
        stock = _stock([{"Артикул": 5170.0, "Наличност": 10}])
        final_df, *_ = _run(orders, stock)
        assert final_df.iloc[0]["Order_Fulfillment_Status"] == "Fulfillable"
        assert final_df.iloc[0]["SKU"] == "5170"

    def test_leading_zero_sku_preserved_and_matched(self):
        orders = _orders([{"Name": "#1", "Lineitem sku": "07", "Lineitem quantity": 1}])
        stock = _stock([{"Артикул": "07", "Наличност": 10}])
        final_df, *_ = _run(orders, stock)
        assert final_df.iloc[0]["SKU"] == "07"
        assert final_df.iloc[0]["Order_Fulfillment_Status"] == "Fulfillable"


class TestNoSkuHandling:
    def test_blank_sku_row_marked_not_fulfillable_and_tagged(self):
        orders = _orders([{"Name": "#1", "Lineitem sku": None, "Lineitem quantity": 1}])
        stock = _stock([{"Артикул": "A1", "Наличност": 10}])
        final_df, *_ = _run(orders, stock)
        row = final_df.iloc[0]
        assert row["SKU"] == "NO_SKU"
        assert row["Order_Fulfillment_Status"] == "Not Fulfillable"
        assert "[NO_SKU]" in row["System_note"]

    def test_no_sku_row_does_not_double_deduct_sibling_row_stock(self):
        orders = _orders([
            {"Name": "#1", "Lineitem sku": "A1", "Lineitem quantity": 2},
            {"Name": "#1", "Lineitem sku": None, "Lineitem quantity": 1},  # e.g. a shipping fee line
        ])
        stock = _stock([{"Артикул": "A1", "Наличност": 10}])
        final_df, *_ = _run(orders, stock)
        a1_row = final_df[final_df["SKU"] == "A1"].iloc[0]
        no_sku_row = final_df[final_df["SKU"] == "NO_SKU"].iloc[0]
        # NO_SKU rows are excluded from stock simulation entirely (they're
        # metadata lines, not pickable items), so A1 is deducted by exactly its
        # own quantity -- no phantom deduction from the NO_SKU line.
        assert a1_row["Final_Stock"] == 8
        # Documents actual (non-obvious) behavior: the Not-Fulfillable override
        # for missing-SKU rows is applied PER ROW, not propagated to the whole
        # order -- a real, stock-sufficient item on the same order still ships.
        assert a1_row["Order_Fulfillment_Status"] == "Fulfillable"
        assert no_sku_row["Order_Fulfillment_Status"] == "Not Fulfillable"


class TestRepeatDetection:
    def test_order_executed_yesterday_is_marked_repeat_with_default_window(self):
        import datetime
        yesterday = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        orders = _orders([{"Name": "#1", "Lineitem sku": "A1", "Lineitem quantity": 1}])
        stock = _stock([{"Артикул": "A1", "Наличност": 10}])
        history = _history([{"Order_Number": "#1", "Execution_Date": yesterday}])
        final_df, *_ = _run(orders, stock, history, repeat_window_days=1)
        assert final_df.iloc[0]["System_note"] == "Repeat"

    def test_order_executed_today_is_not_marked_repeat_with_default_window(self):
        import datetime
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        orders = _orders([{"Name": "#1", "Lineitem sku": "A1", "Lineitem quantity": 1}])
        stock = _stock([{"Артикул": "A1", "Наличност": 10}])
        history = _history([{"Order_Number": "#1", "Execution_Date": today}])
        final_df, *_ = _run(orders, stock, history, repeat_window_days=1)
        assert final_df.iloc[0]["System_note"] != "Repeat"

    def test_unrelated_order_number_not_flagged(self):
        import datetime
        yesterday = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        orders = _orders([{"Name": "#2", "Lineitem sku": "A1", "Lineitem quantity": 1}])
        stock = _stock([{"Артикул": "A1", "Наличност": 10}])
        history = _history([{"Order_Number": "#1", "Execution_Date": yesterday}])
        final_df, *_ = _run(orders, stock, history, repeat_window_days=1)
        assert final_df.iloc[0]["System_note"] != "Repeat"


class TestSetDecoderIntegration:
    def test_set_expands_and_deducts_component_stock_not_set_sku(self):
        orders = _orders([{"Name": "#1", "Lineitem sku": "KIT", "Lineitem quantity": 2}])
        stock = _stock([
            {"Артикул": "HAT", "Наличност": 10},
            {"Артикул": "GLOVES", "Наличност": 10},
        ])
        column_mappings = {
            "orders": {"Name": "Order_Number", "Lineitem sku": "SKU", "Lineitem quantity": "Quantity", "Shipping Method": "Shipping_Method"},
            "stock": {"Артикул": "SKU", "Име": "Product_Name", "Наличност": "Stock"},
            "set_decoders": {"KIT": [{"sku": "HAT", "quantity": 1}, {"sku": "GLOVES", "quantity": 3}]},
        }
        final_df, *_ = analysis.run_analysis(stock, orders, _history(), column_mappings=column_mappings)
        assert set(final_df["SKU"]) == {"HAT", "GLOVES"}
        hat = final_df[final_df["SKU"] == "HAT"].iloc[0]
        gloves = final_df[final_df["SKU"] == "GLOVES"].iloc[0]
        assert hat["Quantity"] == 2 and hat["Final_Stock"] == 8
        assert gloves["Quantity"] == 6 and gloves["Final_Stock"] == 4
        assert hat["Order_Fulfillment_Status"] == "Fulfillable"


class TestCourierMapping:
    @pytest.mark.parametrize("method, expected", [
        ("DHL Express", "DHL"),
        ("dpd classic", "DPD"),
        ("International Shipping", "PostOne"),
        ("Local Pickup", "Local Pickup"),
    ])
    def test_legacy_fallback_rules(self, method, expected):
        assert analysis._generalize_shipping_method(method, None) == expected

    def test_new_format_pattern_mapping(self):
        mappings = {"DHL": {"patterns": ["dhl", "dhl express"]}}
        assert analysis._generalize_shipping_method("DHL Express 24h", mappings) == "DHL"

    def test_nan_method_returns_unknown(self):
        assert analysis._generalize_shipping_method(float("nan"), None) == "Unknown"

    def test_blank_method_returns_unknown(self):
        assert analysis._generalize_shipping_method("   ", None) == "Unknown"


class TestRecalculateStatistics:
    def test_counts_and_write_off_totals(self):
        orders = _orders([
            {"Name": "#1", "Lineitem sku": "A1", "Lineitem quantity": 2},
            {"Name": "#2", "Lineitem sku": "A1", "Lineitem quantity": 5},
        ])
        stock = _stock([{"Артикул": "A1", "Наличност": 3}])
        final_df, *_ = _run(orders, stock)
        stats = analysis.recalculate_statistics(final_df)
        assert stats["total_orders_completed"] == 1
        assert stats["total_orders_not_completed"] == 1
        assert stats["total_items_to_write_off"] == 2
        assert stats["total_items_not_to_write_off"] == 5

    def test_missing_required_column_raises(self):
        with pytest.raises(ValueError):
            analysis.recalculate_statistics(pd.DataFrame({"foo": [1]}))

    def test_courier_stats_grouped_correctly(self):
        orders = _orders([
            {"Name": "#1", "Lineitem sku": "A1", "Lineitem quantity": 1, "Shipping Method": "DHL Express"},
            {"Name": "#2", "Lineitem sku": "A1", "Lineitem quantity": 1, "Shipping Method": "DPD"},
        ])
        stock = _stock([{"Артикул": "A1", "Наличност": 10}])
        final_df, *_ = _run(orders, stock)
        stats = analysis.recalculate_statistics(final_df)
        couriers = {c["courier_id"]: c["orders_assigned"] for c in stats["couriers_stats"]}
        assert couriers == {"DHL": 1, "DPD": 1}


class TestToggleOrderFulfillment:
    def _base_df(self):
        orders = _orders([{"Name": "#1", "Lineitem sku": "A1", "Lineitem quantity": 3}])
        stock = _stock([{"Артикул": "A1", "Наличност": 10}])
        final_df, *_ = _run(orders, stock)
        return final_df

    def test_unfulfill_returns_stock(self):
        df = self._base_df()
        assert df.iloc[0]["Order_Fulfillment_Status"] == "Fulfillable"
        assert df.iloc[0]["Final_Stock"] == 7
        ok, err, updated = analysis.toggle_order_fulfillment(df, "#1")
        assert ok is True
        assert err is None
        assert updated.iloc[0]["Order_Fulfillment_Status"] == "Not Fulfillable"
        assert updated.iloc[0]["Final_Stock"] == 10

    def test_force_fulfill_succeeds_when_stock_available(self):
        orders = _orders([
            {"Name": "#1", "Lineitem sku": "A1", "Lineitem quantity": 20},  # unfulfillable
        ])
        stock = _stock([{"Артикул": "A1", "Наличност": 10}])
        final_df, *_ = _run(orders, stock)
        assert final_df.iloc[0]["Order_Fulfillment_Status"] == "Not Fulfillable"

        # Top up final stock manually (simulating another order freeing stock) then force-fulfill.
        final_df.loc[final_df["SKU"] == "A1", "Final_Stock"] = 25
        ok, _err, updated = analysis.toggle_order_fulfillment(final_df, "#1")
        assert ok is True
        assert updated.iloc[0]["Order_Fulfillment_Status"] == "Fulfillable"
        assert updated.iloc[0]["Final_Stock"] == 5

    def test_force_fulfill_fails_cleanly_when_stock_insufficient(self):
        orders = _orders([{"Name": "#1", "Lineitem sku": "A1", "Lineitem quantity": 20}])
        stock = _stock([{"Артикул": "A1", "Наличност": 10}])
        final_df, *_ = _run(orders, stock)
        ok, err, updated = analysis.toggle_order_fulfillment(final_df, "#1")
        assert ok is False
        assert "Insufficient stock" in err
        assert updated.iloc[0]["Order_Fulfillment_Status"] == "Not Fulfillable"
        assert updated.iloc[0]["Final_Stock"] == 10  # unchanged

    def test_unknown_order_number_returns_false(self):
        df = self._base_df()
        ok, err, _updated = analysis.toggle_order_fulfillment(df, "#DOES-NOT-EXIST")
        assert ok is False
        assert "not found" in err.lower()

    def test_none_dataframe_returns_false(self):
        ok, _err, _updated = analysis.toggle_order_fulfillment(None, "#1")
        assert ok is False


class TestFifoLotAllocation:
    def _stock_with_lots(self, rows):
        defaults = {"Артикул": "", "Годност": "", "Партида": "", "Наличност": 0}
        return pd.DataFrame([{**defaults, **r} for r in rows])

    def test_earliest_expiry_lot_consumed_first(self):
        orders = _orders([{"Name": "#1", "Lineitem sku": "A1", "Lineitem quantity": 5}])
        stock = self._stock_with_lots([
            {"Артикул": "A1", "Годност": "270101", "Наличност": 10},  # 2027-01-01, later
            {"Артикул": "A1", "Годност": "260601", "Наличност": 10},  # 2026-06-01, earlier
        ])
        final_df, *_ = _run(orders, stock)
        row = final_df.iloc[0]
        assert row["Order_Fulfillment_Status"] == "Fulfillable"
        lot_details = row["Lot_Details"]
        assert lot_details[0]["expiry"] == "260601"
        assert lot_details[0]["qty_allocated"] == 5

    def test_order_spans_multiple_lots_when_first_lot_insufficient(self):
        orders = _orders([{"Name": "#1", "Lineitem sku": "A1", "Lineitem quantity": 8}])
        stock = self._stock_with_lots([
            {"Артикул": "A1", "Годност": "260601", "Наличност": 5},
            {"Артикул": "A1", "Годност": "270101", "Наличност": 5},
        ])
        final_df, *_ = _run(orders, stock)
        lot_details = final_df.iloc[0]["Lot_Details"]
        assert len(lot_details) == 2
        assert sum(l["qty_allocated"] for l in lot_details) == 8
        assert lot_details[0]["expiry"] == "260601" and lot_details[0]["qty_allocated"] == 5
        assert lot_details[1]["expiry"] == "270101" and lot_details[1]["qty_allocated"] == 3

    def test_total_stock_aggregated_across_lots_for_display(self):
        orders = _orders([{"Name": "#1", "Lineitem sku": "A1", "Lineitem quantity": 1}])
        stock = self._stock_with_lots([
            {"Артикул": "A1", "Годност": "260601", "Наличност": 5},
            {"Артикул": "A1", "Годност": "270101", "Наличност": 5},
        ])
        final_df, *_ = _run(orders, stock)
        assert final_df.iloc[0]["Stock"] == 10


class TestQuantityRobustness:
    """Confirmed bugs: analysis._clean_and_prepare_data's docstring claims it
    "Convert[s] numeric columns (Quantity, Stock)" but no such conversion exists
    anywhere in the module -- correctness relies entirely on pandas' automatic
    CSV dtype inference, which breaks the moment a single row is malformed."""

    def test_single_bad_quantity_value_does_not_crash_whole_batch(self):
        orders = _orders([
            {"Name": "#1", "Lineitem sku": "A1", "Lineitem quantity": 2},
            {"Name": "#2", "Lineitem sku": "A1", "Lineitem quantity": "abc"},
        ])
        stock = _stock([{"Артикул": "A1", "Наличност": 10}])
        final_df, *_ = _run(orders, stock)  # currently raises TypeError
        assert final_df[final_df["Order_Number"] == "#1"].iloc[0]["Order_Fulfillment_Status"] == "Fulfillable"

    def test_blank_quantity_is_flagged_not_silently_treated_as_zero(self):
        orders = _orders([{"Name": "#1", "Lineitem sku": "A1", "Lineitem quantity": None}])
        stock = _stock([{"Артикул": "A1", "Наличност": 10}])
        final_df, *_ = _run(orders, stock)
        assert final_df.iloc[0]["Order_Fulfillment_Status"] == "Not Fulfillable"
