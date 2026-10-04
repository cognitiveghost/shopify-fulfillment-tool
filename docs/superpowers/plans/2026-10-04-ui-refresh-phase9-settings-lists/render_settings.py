"""Render the Client settings dialog's phase 9 pages, each as a PNG of the
whole dialog (phase 9 plan, Task 9). Run from the repo root:

    QT_QPA_PLATFORM=offscreen PYTHONPATH=. .venv/bin/python \
        docs/superpowers/plans/2026-10-04-ui-refresh-phase9-settings-lists/render_settings.py \
        docs/design/ui-refresh/renders/phase9

The log line "The client config's additional columns couldn't be read" is the
mocked profile manager, not a failure. This file is deleted with its folder
at the end of Task 9.
"""

import copy
import os
import sys
from pathlib import Path
from unittest.mock import Mock

os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")

import pandas as pd
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from gui.settings.window import SettingsWindow
from gui.theme_manager import get_theme_manager

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)

CONFIG = {
    "settings": {"stock_csv_delimiter": "auto", "orders_csv_delimiter": "auto", "low_stock_threshold": 5},
    "rules": [],
    "packing_list_configs": [
        {
            "name": "DHL",
            "output_filename": "DHL.xlsx",
            "filters": [{"field": "Shipping_Provider", "operator": "equals", "value": "DHL"}],
            "exclude_skus": ["CARD-THANKS"],
            "columns": ["Order_Number", "SKU", "Quantity"],
        },
        {"name": "DPD", "output_filename": "", "filters": [], "exclude_skus": []},
    ],
    "stock_export_configs": [{"name": "Daily write-off", "output_filename": "daily.xls", "filters": []}],
    "column_mappings": {
        "version": 2,
        "orders": {
            "Name": "Order_Number",
            "Lineitem sku": "SKU",
            "Lineitem quantity": "Quantity",
            "Shipping Method": "Shipping_Method",
        },
        "stock": {"Артикул": "SKU", "Наличност": "Stock"},
        "additional_columns": [],
    },
    "courier_mappings": {},
    "set_decoders": {
        "SET-WINTER": [{"sku": "HAT-001", "quantity": 1}, {"sku": "SCARF-02", "quantity": 1}, {"sku": "GLOVE-7", "quantity": 2}],
        "SET-GIFT": [{"sku": "CARD-01", "quantity": 1}, {"sku": "BOX-S", "quantity": 1}],
        "SET-BIG": [{"sku": f"PART-{n:02d}", "quantity": 1} for n in range(9)],
    },
    "weight_config": {
        "volumetric_divisor": 6000,
        "products": {
            "TEE-01": {"name": "T-shirt, black", "length_cm": 30.0, "width_cm": 20.0, "height_cm": 2.0, "no_packaging": False},
            "MUG-02": {"name": "Mug", "length_cm": 12.0, "width_cm": 10.0, "height_cm": 10.0, "no_packaging": False},
            "POSTER": {"name": "Poster tube", "length_cm": 0.0, "width_cm": 0.0, "height_cm": 0.0, "no_packaging": True},
        },
        "boxes": [
            {"name": "S", "length_cm": 20.0, "width_cm": 15.0, "height_cm": 10.0},
            {"name": "M", "length_cm": 30.0, "width_cm": 25.0, "height_cm": 15.0},
        ],
    },
    "tag_categories": {
        "version": 2,
        "categories": {
            "packaging": {
                "label": "Packaging",
                "color": "#4CAF50",
                "order": 1,
                "tags": ["BOX", "BAG", "FRAGILE"],
                "sku_writeoff": {"enabled": True, "mappings": {"BOX": [{"sku": "PKG-BOX-S", "quantity": 1.0}], "BAG": [{"sku": "PKG-BAG", "quantity": 1.0}]}},
            },
            "priority": {"label": "Priority", "color": "#FF9800", "order": 2, "tags": ["VIP", "URGENT"]},
            "empty": {"label": "Returns", "color": "#2196F3", "order": 3, "tags": []},
        },
    },
}
FRAME = pd.DataFrame(
    {
        "Order_Number": ["#1", "#1", "#2", "#3"],
        "SKU": ["TEE-01", "MUG-02", "MUG-02", "TEE-01"],
        "Quantity": [1, 2, 1, 1],
        "Shipping_Provider": ["DHL", "DHL", "DPD", "DHL"],
        "Order_Fulfillment_Status": ["Fulfillable"] * 4,
        "Internal_Tags": ["[]"] * 4,
    }
)


def wait(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def shot(win, name):
    wait(700)
    win.grab().save(str(OUT / f"{name}.png"))
    print("wrote", name)


def make(page, config=None):
    win = SettingsWindow(
        client_id="ACME",
        client_config=copy.deepcopy(CONFIG if config is None else config),
        profile_manager=Mock(),
        analysis_df=FRAME,
        initial_page=page,
        session_name="2026-10-04_1",
    )
    win.resize(1180, 760)
    win.show()
    wait(2500)
    return win


def edits(win, *calls):
    for action, args in calls:
        win._web_host.bridge.edit(action, args)


def run(theme):
    get_theme_manager().set_theme(theme)

    win = make("Sets")
    shot(win, f"{theme}-sets")
    if theme == "light":
        edits(win, ("open", ["2"]), ("comp_quantity", ["2", "1", "x"]))
        shot(win, "light-sets-open-problem")
        empty = copy.deepcopy(CONFIG)
        empty["set_decoders"] = {}
        win.close()
        win = make("Sets", empty)
        shot(win, "light-sets-empty")
    win.close()

    win = make("Weight")
    shot(win, f"{theme}-weight")
    if theme == "light":
        edits(win, ("product_text", ["1", "w", "wide"]), ("product_add", []), ("product_text", ["6", "l", "3"]))
        shot(win, "light-weight-problem")
    win.close()

    win = make("Reports")
    if theme == "light":
        shot(win, "light-reports")
    edits(win, ("open", ["1"]))
    shot(win, f"{theme}-reports-open")
    win.close()

    win = make("Tag categories")
    if theme == "light":
        shot(win, "light-tags")
    edits(win, ("open", ["1"]))
    shot(win, f"{theme}-tags-open")
    if theme == "light":
        edits(win, ("map_add", ["1"]), ("tag_add", ["1", "vip"]))
        shot(win, "light-tags-refused")
    win.close()


app = QApplication.instance() or QApplication(sys.argv)
for theme in ("light", "dark"):
    run(theme)
