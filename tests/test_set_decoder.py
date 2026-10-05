"""Set/bundle decode accuracy (priority: set decode accuracy)."""
import pandas as pd
import pytest

from shopify_tool.set_decoder import (
    _components,
    decode_sets_in_orders,
    export_sets_to_csv,
    import_sets_from_csv,
)


def _orders(rows):
    return pd.DataFrame(rows)


class TestDecodeSetsInOrders:
    def test_regular_sku_passes_through_with_tracking_columns(self):
        df = _orders([{"Order_Number": "#1", "SKU": "A1", "Quantity": 2}])
        result = decode_sets_in_orders(df, {})
        assert result.loc[0, "SKU"] == "A1"
        assert result.loc[0, "Quantity"] == 2
        assert result.loc[0, "Original_SKU"] == "A1"
        assert result.loc[0, "Original_Quantity"] == 2
        assert result.loc[0, "Is_Set_Component"] == False

    def test_set_expands_into_components_with_multiplied_quantity(self):
        df = _orders([{"Order_Number": "#1", "SKU": "SET-A", "Quantity": 2}])
        set_decoders = {
            "SET-A": [
                {"sku": "HAT", "quantity": 1},
                {"sku": "GLOVES", "quantity": 3},
            ]
        }
        result = decode_sets_in_orders(df, set_decoders)
        assert len(result) == 2

        hat = result[result["SKU"] == "HAT"].iloc[0]
        assert hat["Quantity"] == 2 * 1
        assert hat["Original_SKU"] == "SET-A"
        assert hat["Original_Quantity"] == 2
        assert hat["Is_Set_Component"] == True

        gloves = result[result["SKU"] == "GLOVES"].iloc[0]
        assert gloves["Quantity"] == 2 * 3

    def test_mixed_set_and_regular_items(self):
        df = _orders([
            {"Order_Number": "#1", "SKU": "SET-A", "Quantity": 1},
            {"Order_Number": "#1", "SKU": "PLAIN", "Quantity": 5},
        ])
        set_decoders = {"SET-A": [{"sku": "COMP", "quantity": 2}]}
        result = decode_sets_in_orders(df, set_decoders)
        assert len(result) == 2
        assert set(result["SKU"]) == {"COMP", "PLAIN"}
        plain = result[result["SKU"] == "PLAIN"].iloc[0]
        assert plain["Quantity"] == 5
        assert plain["Is_Set_Component"] == False

    def test_component_with_zero_quantity_is_skipped(self):
        df = _orders([{"Order_Number": "#1", "SKU": "SET-A", "Quantity": 1}])
        set_decoders = {"SET-A": [
            {"sku": "GOOD", "quantity": 1},
            {"sku": "BAD", "quantity": 0},
        ]}
        result = decode_sets_in_orders(df, set_decoders)
        assert list(result["SKU"]) == ["GOOD"]

    def test_no_set_decoders_is_noop_passthrough(self):
        df = _orders([{"Order_Number": "#1", "SKU": "A1", "Quantity": 4}])
        result = decode_sets_in_orders(df, {})
        assert list(result["SKU"]) == ["A1"]
        assert list(result["Quantity"]) == [4]

    def test_empty_dataframe_returns_empty_with_tracking_columns(self):
        df = pd.DataFrame({"SKU": [], "Quantity": []})
        result = decode_sets_in_orders(df, {"SET-A": [{"sku": "X", "quantity": 1}]})
        assert result.empty
        assert "Original_SKU" in result.columns
        assert "Is_Set_Component" in result.columns

    def test_nested_sets_are_recursively_expanded(self):
        """A component that is itself a set SKU is expanded too (AUDIT-06-4, D3)."""
        df = _orders([{"Order_Number": "#1", "SKU": "OUTER", "Quantity": 1}])
        set_decoders = {
            "OUTER": [{"sku": "INNER-SET", "quantity": 1}],
            "INNER-SET": [{"sku": "LEAF", "quantity": 1}],
        }
        result = decode_sets_in_orders(df, set_decoders)
        assert list(result["SKU"]) == ["LEAF"]

    def test_set_with_all_invalid_components_does_not_drop_the_order_line(self):
        df = _orders([{"Order_Number": "#1", "SKU": "SET-BROKEN", "Quantity": 1}])
        set_decoders = {"SET-BROKEN": [{"sku": "", "quantity": 1}]}
        result = decode_sets_in_orders(df, set_decoders)
        # Expect the order line to survive in some form (e.g. as the original
        # set SKU) rather than disappearing entirely.
        assert len(result) == 1


class TestImportExportSetsRoundTrip:
    def test_export_then_import_round_trip(self, tmp_path):
        set_decoders = {
            "SET-A": [{"sku": "COMP-1", "quantity": 1}, {"sku": "COMP-2", "quantity": 2}],
            "SET-B": [{"sku": "COMP-3", "quantity": 1}],
        }
        csv_path = tmp_path / "sets.csv"
        export_sets_to_csv(set_decoders, str(csv_path))
        result = import_sets_from_csv(str(csv_path))
        assert result == set_decoders

    def test_import_rejects_missing_columns(self, tmp_path):
        csv_path = tmp_path / "bad.csv"
        csv_path.write_text("Set_SKU,Component_SKU\nSET-A,COMP-1\n", encoding="utf-8")
        with pytest.raises(ValueError):
            import_sets_from_csv(str(csv_path))

    def test_import_rejects_non_positive_quantity(self, tmp_path):
        csv_path = tmp_path / "bad.csv"
        csv_path.write_text(
            "Set_SKU,Component_SKU,Component_Quantity\nSET-A,COMP-1,0\n", encoding="utf-8"
        )
        with pytest.raises(ValueError):
            import_sets_from_csv(str(csv_path))

    def test_import_dedupes_duplicate_pairs_keeping_last(self, tmp_path):
        csv_path = tmp_path / "dupe.csv"
        csv_path.write_text(
            "Set_SKU,Component_SKU,Component_Quantity\n"
            "SET-A,COMP-1,1\n"
            "SET-A,COMP-1,9\n",
            encoding="utf-8",
        )
        result = import_sets_from_csv(str(csv_path))
        assert result == {"SET-A": [{"sku": "COMP-1", "quantity": 9}]}

    def test_export_empty_raises(self, tmp_path):
        with pytest.raises(ValueError):
            export_sets_to_csv({}, str(tmp_path / "out.csv"))


# the pre-D implementation, frozen to pin behaviour
def _decode_reference(orders_df, set_decoders):
    if orders_df.empty:
        orders_df["Original_SKU"] = orders_df["SKU"] if "SKU" in orders_df.columns else None
        orders_df["Original_Quantity"] = orders_df["Quantity"] if "Quantity" in orders_df.columns else None
        orders_df["Is_Set_Component"] = False
        return orders_df

    if not set_decoders:
        orders_df["Original_SKU"] = orders_df["SKU"]
        orders_df["Original_Quantity"] = orders_df["Quantity"]
        orders_df["Is_Set_Component"] = False
        return orders_df

    expanded_rows = []
    for _idx, row in orders_df.iterrows():
        sku = row["SKU"]
        quantity = row["Quantity"]
        if sku in set_decoders:
            components = set_decoders[sku]
            if not components:
                new_row = row.copy()
                new_row["Original_SKU"] = sku
                new_row["Original_Quantity"] = quantity
                new_row["Is_Set_Component"] = False
                expanded_rows.append(new_row)
                continue
            valid_components_added = 0
            for component_sku, component_total in _components(sku, quantity, set_decoders, {sku}):
                new_row = row.copy()
                new_row["SKU"] = component_sku
                new_row["Quantity"] = component_total
                new_row["Original_SKU"] = sku
                new_row["Original_Quantity"] = quantity
                new_row["Is_Set_Component"] = True
                expanded_rows.append(new_row)
                valid_components_added += 1
            if valid_components_added == 0:
                new_row = row.copy()
                new_row["Original_SKU"] = sku
                new_row["Original_Quantity"] = quantity
                new_row["Is_Set_Component"] = False
                expanded_rows.append(new_row)
        else:
            new_row = row.copy()
            new_row["Original_SKU"] = sku
            new_row["Original_Quantity"] = quantity
            new_row["Is_Set_Component"] = False
            expanded_rows.append(new_row)

    if not expanded_rows:
        result_df = orders_df.copy()
        result_df["Original_SKU"] = None
        result_df["Original_Quantity"] = None
        result_df["Is_Set_Component"] = False
        return result_df.iloc[0:0]

    return pd.DataFrame(expanded_rows)


SETS_MIXED = {
    "S2": [{"sku": "A", "quantity": 1}, {"sku": "B", "quantity": 2}],
    "SN": [{"sku": "S2", "quantity": 3}, {"sku": "C", "quantity": 1}],  # nested
    "NECTAR": [{"sku": "NECTAR", "quantity": 1}, {"sku": "EXTRA", "quantity": 1}],  # lists itself
    "PARENT": [{"sku": "NECTAR", "quantity": 2}, {"sku": "EXTRA", "quantity": 1}],
    "X": [{"sku": "Y", "quantity": 1}],  # X -> Y -> X
    "Y": [{"sku": "X", "quantity": 1}, {"sku": "D", "quantity": 2}],
    "EMPTY": [],
    "BAD": [{"sku": "", "quantity": 1}, {"sku": "Z", "quantity": 0}],
}

ORDERS = pd.DataFrame(
    {
        "Order_Number": ["#1", "#1", "#2", "#2", "#2", "#3", "#3", "#3", "#4", "#4", "#4", "#4"],
        "SKU": ["P1", "S2", "SN", "NECTAR", "PARENT", "X", "EMPTY", "BAD", None, "S2", "S2", "P2"],
        "Quantity": [1, 2, 1, 1, 1, 1, 1, 1, 1, 2.0, float("nan"), 3],
        "Product_Name": [f"name {i}" for i in range(12)],
    },
    index=[10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21],
)


@pytest.mark.parametrize("sets", [SETS_MIXED, {}], ids=["sets", "no-sets"])
def test_decoding_matches_the_reference(sets):
    out = decode_sets_in_orders(ORDERS.copy(), sets)
    ref = _decode_reference(ORDERS.copy(), sets)
    pd.testing.assert_frame_equal(out, ref, check_dtype=False)  # index labels and row order included
