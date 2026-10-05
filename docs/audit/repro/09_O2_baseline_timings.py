import logging
import sys
import time

logging.disable(logging.CRITICAL)
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[3]))
import pandas as pd

from shopify_tool import core, stock_ledger
from shopify_tool.analysis import recalculate_statistics, run_analysis

n = 5000
orders = pd.DataFrame({"Name": [f"#{i}" for i in range(n) for _ in range(3)], "Lineitem sku": ["A", "B", "C"] * n,
    "Lineitem quantity": [1] * (3 * n), "Shipping Method": ["DHL"] * (3 * n), "Shipping Country": ["BG"] * (3 * n)})
stock = pd.DataFrame({"Артикул": ["A", "B", "C"], "Име": list("abc"), "Наличност": [7000] * 3})
def t(label, f):
    s = time.perf_counter(); r = f(); print(f"{label}: {time.perf_counter() - s:.2f}s"); return r
df, _ = t("run_analysis (5,000 orders, 15,000 lines, no sets/rules)", lambda: run_analysis(stock, orders, pd.DataFrame({"Order_Number": []})))
t("_create_analysis_data_for_packing", lambda: core._create_analysis_data_for_packing(df))
t("with_order_fields (every GUI refresh)", lambda: core.with_order_fields(df, {}, None))
t("stock_ledger.with_stock_left (every edit)", lambda: stock_ledger.with_stock_left(df.copy()))
t("recalculate_statistics", lambda: recalculate_statistics(df))
t("toggle one order (shortfall + with_stock_left)", lambda: __import__("shopify_tool.analysis", fromlist=["x"]).toggle_order_fulfillment(df.copy(), "#4999"))
