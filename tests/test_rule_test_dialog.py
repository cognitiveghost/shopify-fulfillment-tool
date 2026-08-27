"""RuleTestDialog before/after frame alignment.

RuleEngine.apply() can add columns (CALCULATE/COPY_FIELD targets) and append
rows (ADD_PRODUCT, concatenated with ignore_index). The dialog diffs
df_before against df_after, so every one of those shape changes used to
either raise or silently report nothing.
"""
import pandas as pd
import pytest

from gui.rule_test_dialog import RuleTestDialog
from gui.theme_manager import get_theme_manager


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

    def test_add_product_alone_explains_the_empty_preview(self, qtbot, analysis_df, no_modals):
        """The preview table shows *before* rows, so an ADD_PRODUCT-only rule
        has nothing to put in it. Rendering it blank reads as broken -- say why
        it is empty and where the added rows are."""
        dialog = _open(qtbot, _rule(
            {"type": "ADD_PRODUCT", "sku": "B", "quantity": 1},
        ), analysis_df)
        assert no_modals == []
        assert dialog.preview_table.rowCount() == 1
        assert "2 rows added by the rule" in dialog.preview_table.item(0, 0).text()
        # The added rows still show up where they belong.
        assert dialog.after_table.rowCount() == 2

    def test_summary_percentage_never_exceeds_total_rows(self, qtbot, analysis_df, no_modals):
        """Added rows have no denominator to belong to -- counting them in the
        percentage rendered "4 rows affected (133.3% of 3 total rows)"."""
        dialog = _open(qtbot, _rule(
            {"type": "ADD_PRODUCT", "sku": "B", "quantity": 1},
            {"type": "ADD_TAG", "value": "bonus"},
        ), analysis_df)
        assert no_modals == []
        assert dialog.matched_count == 4
        assert dialog.changed_count == 2
        assert "2 of 3 existing rows, 66.7%" in dialog.match_summary_label.text()


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


class TestZeroResultsAreChanges:
    def test_calculate_result_of_zero_counts_as_changed(self, qtbot, analysis_df, no_modals):
        """A legitimate CALCULATE result of 0 is a change, not a seed value.

        The old detector filtered out `!= 0` to hide CALCULATE's 0.0 seed, and
        hid every real zero result with it. The seed is NaN now, so a real 0 is
        distinguishable and must be counted.
        """
        df = analysis_df.copy()
        df["Total_Price"] = 0.0          # every product is now legitimately 0

        dialog = _open(qtbot, _rule({
            "type": "CALCULATE", "operation": "multiply",
            "field1": "Quantity", "field2": "Total_Price",
            "target": "Line_Total",
        }), df)

        assert no_modals == []
        # Rows 0 and 2 match and get a real result of 0.0; row 1 stays NaN.
        assert dialog.changed_count == 2
        assert pd.isna(dialog.df_after.loc[1, "Line_Total"])


class TestActionTypeCaseIsNormalized:
    """RuleEngine uppercases action types (shopify_tool/rules.py:917, :1051),
    so a lowercase type executes. The dialog must explain it, not go silent."""

    def test_lowercase_type_still_gets_its_explanation(
        self, qtbot, analysis_df, no_modals
    ):
        rule = _rule({"type": "set_status", "value": "Ready"})
        dialog = _open(qtbot, rule, analysis_df)
        assert no_modals == []
        assert "Sets Order_Fulfillment_Status" in dialog.actions_label.text()

    def test_mixed_case_copy_field_still_gets_its_explanation(
        self, qtbot, analysis_df, no_modals
    ):
        rule = _rule({"type": "Copy_Field", "source": "SKU", "target": "Status_Note"})
        dialog = _open(qtbot, rule, analysis_df)
        assert no_modals == []
        text = dialog.actions_label.text()
        assert "Copies 'SKU' to 'Status_Note'" in text

    def test_uppercase_type_is_unchanged(self, qtbot, analysis_df, no_modals):
        """Baseline: passes today."""
        rule = _rule({"type": "SET_STATUS", "value": "Ready"})
        dialog = _open(qtbot, rule, analysis_df)
        assert no_modals == []
        assert "Sets Order_Fulfillment_Status" in dialog.actions_label.text()


class TestMissingValuesRenderBlank:
    """gui/pandas_model.py:192 renders a missing cell as "", so the dialog the
    user compares against that table must not print the literal text 'nan'."""

    def _texts(self, table):
        return {
            table.item(r, c).text()
            for r in range(table.rowCount())
            for c in range(table.columnCount())
            if table.item(r, c) is not None
        }

    def test_nan_is_not_shown_as_the_word_nan(self, qtbot, analysis_df, no_modals):
        analysis_df.loc[0, "Product_Name"] = float("nan")
        rule = _rule({"type": "ADD_TAG", "value": "T"})
        dialog = _open(qtbot, rule, analysis_df)

        assert no_modals == []
        assert "nan" not in self._texts(dialog.preview_table)
        assert "nan" not in self._texts(dialog.after_table)

    def test_none_is_not_shown_as_the_word_none(self, qtbot, analysis_df, no_modals):
        analysis_df["Lot_Details"] = None
        rule = _rule({"type": "ADD_TAG", "value": "T"})
        dialog = _open(qtbot, rule, analysis_df)

        assert no_modals == []
        assert "None" not in self._texts(dialog.preview_table)

    def test_a_list_valued_column_does_not_crash_the_dialog(
        self, qtbot, analysis_df, no_modals
    ):
        """Lot_Details holds real lists (shopify_tool/analysis.py:1111), and
        _get_display_columns pulls spare columns straight from df.columns.
        pd.isna() on a list returns an array, so an unguarded truth test raises
        'truth value of an array is ambiguous'."""
        analysis_df["Lot_Details"] = [
            [{"lot": "L1", "quantity": 1}, {"lot": "L2", "quantity": 2}],
            [],
            None,
        ]
        rule = _rule({"type": "ADD_TAG", "value": "T"})
        dialog = _open(qtbot, rule, analysis_df)

        # First, and load-bearing: _run_test swallows every exception into a
        # QMessageBox.critical, and the after-table is populated last — so the
        # table assertions below can pass while the dialog blew up behind them.
        assert no_modals == []
        texts = self._texts(dialog.preview_table)
        assert "2 lots" in texts
        assert "nan" not in texts

    def test_a_changed_cell_is_still_highlighted(self, qtbot, analysis_df, no_modals):
        """Baseline for the rewritten diff test: a real change must still tint."""
        rule = _rule({"type": "SET_STATUS", "value": "Shipped"})
        dialog = _open(qtbot, rule, analysis_df)

        assert no_modals == []
        col = [
            dialog.after_table.horizontalHeaderItem(c).text()
            for c in range(dialog.after_table.columnCount())
        ].index("Order_Fulfillment_Status")
        item = dialog.after_table.item(0, col)
        assert item.text() == "Shipped"
        theme = get_theme_manager().get_current_theme()
        assert item.background().color().name().lower() == theme.status_warning_bg.lower()

    def test_an_unchanged_missing_cell_is_not_highlighted(
        self, qtbot, analysis_df, no_modals
    ):
        """NaN != NaN, so a naive object diff tints every missing cell."""
        analysis_df.loc[0, "Product_Name"] = float("nan")
        rule = _rule({"type": "SET_STATUS", "value": "Shipped"})
        dialog = _open(qtbot, rule, analysis_df)

        assert no_modals == []
        col = [
            dialog.after_table.horizontalHeaderItem(c).text()
            for c in range(dialog.after_table.columnCount())
        ].index("Product_Name")
        item = dialog.after_table.item(0, col)
        theme = get_theme_manager().get_current_theme()
        assert item.background().color().name().lower() != theme.status_warning_bg.lower()
