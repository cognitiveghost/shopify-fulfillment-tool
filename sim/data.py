"""Deterministic synthetic Shopify orders and stock for the simulation. Never production data.

Headers follow ProfileManager._create_default_shopify_config's default column mapping.
"""

import csv
import random
from dataclasses import dataclass
from pathlib import Path

CLIENT = "SIM"
COURIERS = ("DHL", "DPD")
_METHOD = {"DHL": "DHL Express", "DPD": "DPD Bulgaria"}
ORDER_HEADERS = [
    "Name", "Lineitem sku", "Lineitem quantity", "Lineitem name", "Shipping Method", "Shipping Country",
    "Tags", "Notes", "Total", "Subtotal", "Shipping Name", "Created at",
]
STOCK_HEADERS = ["Артикул", "Име", "Наличност"]
SKUS = [f"SIM-{i:03d}" for i in range(1, 13)]
OUT_OF_STOCK = SKUS[-1]
N_ORDERS = 40


@dataclass(frozen=True)
class Inputs:
    orders: Path
    stock: Path


def write_inputs(folder: Path) -> Inputs:
    """40 orders over 12 SKUs, alternating DHL/DPD; every 5th is two lines, every 7th has
    quantity 3, and orders 8, 19 and 30 want only the out-of-stock SKU."""
    rng = random.Random(0)
    folder.mkdir(parents=True, exist_ok=True)
    rows = []
    for i in range(N_ORDERS):
        courier = COURIERS[i % 2]
        skus = [OUT_OF_STOCK] if i in (7, 18, 29) else rng.sample(SKUS[:-1], 2 if i % 5 == 0 else 1)
        for sku in skus:
            rows.append({
                "Name": f"#{1001 + i}", "Lineitem sku": sku, "Lineitem quantity": 3 if i % 7 == 0 else 1,
                "Lineitem name": f"Product {sku}", "Shipping Method": _METHOD[courier],
                "Shipping Country": "BG", "Tags": "", "Notes": "", "Total": "10.00", "Subtotal": "10.00",
                "Shipping Name": f"Customer {i}", "Created at": f"2026-09-01 10:{i:02d}:00 +0300",
            })
    orders = folder / "orders_export.csv"
    with orders.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=ORDER_HEADERS)
        writer.writeheader()
        writer.writerows(rows)
    stock = folder / "stock.csv"
    with stock.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(STOCK_HEADERS)
        for sku in SKUS:
            writer.writerow([sku, f"Product {sku}", 0 if sku == OUT_OF_STOCK else 500])
    return Inputs(orders=orders, stock=stock)
