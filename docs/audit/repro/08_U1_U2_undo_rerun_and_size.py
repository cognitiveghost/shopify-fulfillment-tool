import json
import logging
import sys

logging.disable(logging.CRITICAL)
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[3]))
from types import SimpleNamespace

import pandas as pd

from shopify_tool.analysis import run_analysis
from shopify_tool.undo_manager import UndoManager

orders = pd.DataFrame({"Name": ["#1", "#2", "#3"], "Lineitem sku": ["A", "B", "A"],
                       "Lineitem quantity": [1, 1, 1], "Shipping Method": ["DHL"] * 3,
                       "Shipping Country": ["BG"] * 3})
stock = pd.DataFrame({"Артикул": ["A", "B"], "Име": ["a", "b"], "Наличност": [5, 5]})
hist = pd.DataFrame({"Order_Number": []})
df, _ = run_analysis(stock, orders, hist)

mw = SimpleNamespace(session_path=None, analysis_results_df=df, analysis_stats=None, current_client_id=None)
um = UndoManager(mw)
# operator removes order #2 (as actions_handler.remove_entire_order does)
mask = mw.analysis_results_df["Order_Number"] == "#2"
um.record_operation("remove_order", "Removed order #2", {"order_number": "#2"}, mw.analysis_results_df[mask].copy())
mw.analysis_results_df = mw.analysis_results_df[~mask].reset_index(drop=True)
# operator re-runs the analysis in the same session (same orders file): nothing resets undo
mw.analysis_results_df, _ = run_analysis(stock, orders, hist)
print("can undo after re-run:", um.can_undo())
ok, msg = um.undo()
print(ok, msg)
print("rows for #2 after undo:", int((mw.analysis_results_df["Order_Number"] == "#2").sum()))

# undo history size for one bulk op on a realistic frame
big = pd.concat([df] * 2000, ignore_index=True)
big["Order_Number"] = [f"#{i}" for i in range(len(big))]
for c in range(25):
    big[f"Extra_{c}"] = "some text value"
um2 = UndoManager(SimpleNamespace(session_path=None, analysis_results_df=big, analysis_stats=None, current_client_id=None))
um2.record_operation("bulk_change_status", "bulk", {}, big.copy())
size = len(json.dumps({"operations": um2.operations}, indent=2, ensure_ascii=False, default=str))
print(f"one bulk op over {len(big)} rows x {big.shape[1]} cols -> operations_history.json ~{size/1e6:.1f} MB")
