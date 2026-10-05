import logging
import os
import sys
import tempfile
import time

logging.disable(logging.CRITICAL)
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[3]))
import pandas as pd

from shopify_tool.set_decoder import decode_sets_in_orders, import_sets_from_csv

n = 15000
df = pd.DataFrame({"Order_Number": [f"#{i//3}" for i in range(n)], "SKU": ["SET-1", "A", "B"] * (n // 3),
                   "Quantity": [1] * n, **{f"c{k}": "x" for k in range(15)}})
s = time.perf_counter(); out = decode_sets_in_orders(df, {"SET-1": [{"sku": "A", "quantity": 1}, {"sku": "C", "quantity": 2}]})
print(f"decode 15,000 rows (5,000 sets): {time.perf_counter()-s:.2f}s -> {len(out)} rows")
p = os.path.join(tempfile.mkdtemp(), "sets.csv")
__import__("pathlib").Path(p).write_text("Set_SKU,Component_SKU,Component_Quantity\nSET-1 ,A ,2\n")
sets = import_sets_from_csv(p)
print("imported keys:", list(sets), sets)
out = decode_sets_in_orders(pd.DataFrame({"Order_Number": ["#1"], "SKU": ["SET-1"], "Quantity": [1]}), sets)
print("order SET-1 expanded:", bool(out["Is_Set_Component"].any()))
