"""RuleTestDialog before/after frame alignment.

RuleEngine.apply() can add columns (CALCULATE/COPY_FIELD targets) and append
rows (ADD_PRODUCT, concatenated with ignore_index). The dialog diffs
df_before against df_after, so every one of those shape changes used to
either raise or silently report nothing.
"""
import pandas as pd
import pytest

from gui.rule_test_dialog import RuleTestDialog


@pytest.fixture
def analysis_df():
    """Analysis-shaped: Status_Note and Internal_Tags already exist.

    analysis.py:1097 and :1103 initialise both on every real analysis, so a
    fixture without them tests a frame production never produces.
    """
    return pd.DataFrame({
        "Order_Number": ["1001", "1002", "1003"],
        "SKU": ["A", "B", "A"],
        "Quantity": [1, 2, 3],
        "Total_Price": [10.0, 20.0, 30.0],
        "Product_Name": ["Pa", "Pb", "Pa"],
        "Warehouse_Name": ["Wa", "Wb", "Wa"],
        "Order_Fulfillment_Status": ["Ready", "Not Ready", "Ready"],
        "Status_Note": ["", "", ""],
        "Internal_Tags": ["[]", "[]", "[]"],
    })


def _rule(*actions):
    """Single-step rule matching the two 'Ready' rows."""
    return {
        "name": "t",
        "enabled": True,
        "steps": [{
            "match": "ALL",
            "conditions": [{
                "field": "Order_Fulfillment_Status",
                "operator": "equals",
                "value": "Ready",
            }],
            "actions": list(actions),
        }],
    }


def _open(qtbot, rule, df):
    dialog = RuleTestDialog(rule, df)
    qtbot.addWidget(dialog)
    return dialog


class TestNoCrashOnShapeChange:
    def test_add_tag_is_unaffected(self, qtbot, analysis_df, no_modals):
        """Baseline: passes today. Status_Note already exists, so nothing
        about the frame's shape changes."""
        dialog = _open(qtbot, _rule({"type": "ADD_TAG", "value": "hello"}), analysis_df)
        assert no_modals == []
        assert dialog.matched_count == 2

    def test_calculate_target_column_does_not_crash(self, qtbot, analysis_df, no_modals):
        """CALCULATE creates its target at rules.py:1190, so the column is in
        df_after and not in df_before."""
        dialog = _open(qtbot, _rule({
            "type": "CALCULATE", "operation": "multiply",
            "field1": "Quantity", "field2": "Total_Price",
            "target": "Line_Total",
        }), analysis_df)
        assert no_modals == []
        assert dialog.matched_count == 2

    def test_copy_field_target_column_does_not_crash(self, qtbot, analysis_df, no_modals):
        dialog = _open(qtbot, _rule({
            "type": "COPY_FIELD", "source": "SKU", "target": "SKU_Copy",
        }), analysis_df)
        assert no_modals == []
        assert dialog.matched_count == 2

    def test_add_product_with_a_tag_does_not_crash(self, qtbot, analysis_df, no_modals):
        """ADD_PRODUCT appends rows with ignore_index, so a boolean mask built
        on df_before.index no longer aligns with df_after."""
        _open(qtbot, _rule(
            {"type": "ADD_PRODUCT", "sku": "B", "quantity": 1},
            {"type": "ADD_TAG", "value": "bonus"},
        ), analysis_df)
        assert no_modals == []


class TestAddedRowsAreReported:
    def test_add_product_alone_reports_the_added_rows(self, qtbot, analysis_df, no_modals):
        """Two matched rows each spawn one product row. Reporting 0 tells the
        user a working rule does nothing."""
        dialog = _open(qtbot, _rule(
            {"type": "ADD_PRODUCT", "sku": "B", "quantity": 1},
        ), analysis_df)
        assert no_modals == []
        assert len(dialog.added_rows) == 2
        assert dialog.matched_count == 2


class TestEngineOrderingAssumption:
    def test_added_rows_are_appended_not_interleaved(self, qtbot, analysis_df, no_modals):
        """_align_frames slices df_after positionally, which is only correct
        while apply() appends. If the engine ever reorders or drops rows, this
        fails here instead of silently mispairing rows in the preview."""
        dialog = _open(qtbot, _rule(
            {"type": "ADD_PRODUCT", "sku": "B", "quantity": 1},
        ), analysis_df)
        n = len(dialog.df_before)
        original = dialog.df_after.iloc[:n]
        assert list(original["Order_Number"]) == list(dialog.df_before["Order_Number"])
        assert list(original["SKU"]) == list(dialog.df_before["SKU"])
