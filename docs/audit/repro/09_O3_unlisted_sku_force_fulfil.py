import logging
import sys

logging.disable(logging.CRITICAL)
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[3]))
import pandas as pd

from shopify_tool import stock_ledger
from shopify_tool.analysis import run_analysis

orders = pd.DataFrame({"Name": ["#1"], "Lineitem sku": ["X"], "Lineitem quantity": [3],
                       "Shipping Method": ["DHL"], "Shipping Country": ["BG"]})
stock = pd.DataFrame({"Артикул": ["A"], "Име": ["a"], "Наличност": [5]})
df, _ = run_analysis(stock, orders, pd.DataFrame({"Order_Number": []}))
print(df[["Order_Number", "SKU", "Stock", "Final_Stock", "Order_Fulfillment_Status"]].to_string())
print("shortfall:", stock_ledger.shortfall(df, "#1"))
print("claim:", stock_ledger.claim(df, ["#1"]))
