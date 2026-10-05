import logging
import sys

logging.disable(logging.CRITICAL)
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[3]))
import pandas as pd

from shopify_tool.analysis import run_analysis

orders = pd.DataFrame({"Name": ["#1001"], "Lineitem sku": ["A"], "Lineitem quantity": [9],
                       "Shipping Method": ["DHL"], "Shipping Country": ["BG"]})
hist = pd.DataFrame({"Order_Number": []})
def run(stock):
    df, _ = run_analysis(stock, orders.copy(), hist)
    r = df.iloc[0]
    return r["Order_Fulfillment_Status"], r["Stock"], r["Final_Stock"]

no_lots = pd.DataFrame({"Артикул": ["A", "A"], "Име": ["x", "x"], "Наличност": [10, -3]})
lots = no_lots.assign(Годност=["2027-01-01", "2027-02-01"])
print("no lot columns :", run(no_lots))
print("with lot column:", run(lots))
