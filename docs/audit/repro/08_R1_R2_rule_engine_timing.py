import logging
import sys
import time

logging.disable(logging.CRITICAL)
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[3]))
import pandas as pd

from shopify_tool.analysis import run_analysis
from shopify_tool.rules import RuleEngine

n = 5000  # orders, 3 lines each
orders = pd.DataFrame({
    "Name": [f"#{i}" for i in range(n) for _ in range(3)],
    "Lineitem sku": ["A", "B", "C"] * n,
    "Lineitem quantity": [1] * (3 * n),
    "Shipping Method": ["DHL"] * (3 * n),
    "Shipping Country": ["BG"] * (3 * n),
})
stock = pd.DataFrame({"Артикул": ["A", "B", "C"], "Име": list("abc"), "Наличност": [10**6] * 3})
df, _ = run_analysis(stock, orders, pd.DataFrame({"Order_Number": []}))
df["Created_At_Test"] = "2026-10-01 10:00:00 +0200"
print("frame:", df.shape)

def t(label, rules):
    d = df.copy(); s = time.perf_counter(); RuleEngine(rules).apply(d)
    print(f"{label}: {time.perf_counter() - s:.2f}s")

t("article rule, contains -> ADD_TAG", [{"name": "a", "level": "article", "conditions": [{"field": "SKU", "operator": "equals", "value": "A"}], "actions": [{"type": "ADD_TAG", "value": "x"}]}])
t("article rule, date before (Shopify timestamp)", [{"name": "d", "level": "article", "conditions": [{"field": "Created_At_Test", "operator": "date before", "value": "2026-10-02"}], "actions": [{"type": "ADD_TAG", "value": "old"}]}])
t("order rule, item_count > 1 -> ADD_TAG (all orders match)", [{"name": "o", "level": "order", "conditions": [{"field": "item_count", "operator": "is greater than", "value": "1"}], "actions": [{"type": "ADD_TAG", "value": "multi"}]}])
t("order rule, has_sku = Z (no order matches)", [{"name": "o2", "level": "order", "conditions": [{"field": "has_sku", "operator": "equals", "value": "Z"}], "actions": [{"type": "ADD_TAG", "value": "z"}]}])
