"""A fulfilment PC. Run as `.venv/bin/python -m sim.agent_fulfilment` with cwd = this repo."""

from pathlib import Path

from sim import agent_common as ac


def main() -> None:
    from PySide6.QtWidgets import QApplication

    app = QApplication([])  # noqa: F841 - must outlive the window
    ac.install_capture()
    import gui.session_browser_widget as browser
    from gui.main_window_pyside import MainWindow

    browser.SessionBrowserWidget.USE_ASYNC = False  # as tests/audit/test_05_sessions_sweep.py
    mw = MainWindow()
    mw.resize(1100, 900)
    mw.show()
    QApplication.processEvents()
    ac.capture_calls("shared.components.toast", "toast", "toast")
    ac.capture_calls("gui.components.error_banner", "show_error", "error_banner")
    ac.capture_logs()

    def create_client(client_id: str) -> dict:
        return {"created": bool(mw.profile_manager.create_client_profile(client_id, f"Client {client_id}"))}

    def select_client(client_id: str) -> dict:
        mw.current_client_id = client_id
        mw.load_client_config(client_id)
        return {"client_id": mw.current_client_id}

    def new_session() -> dict:
        mw.actions_handler.create_new_session()
        return {"session_path": str(mw.session_path) if mw.session_path else None}

    def open_session(session_path: str) -> dict:
        mw.load_existing_session(session_path)
        return {"session_path": str(mw.session_path) if mw.session_path else None}

    def set_inputs(orders: str, stock: str) -> dict:
        mw.orders_file_path, mw.stock_file_path = orders, stock
        return {}

    def run_analysis() -> dict:
        mw.actions_handler.run_analysis()
        ac.pump_until(lambda: not getattr(mw, "_analysis_running", False), 120, "analysis")
        df = mw.analysis_results_df
        return {"orders": 0 if df is None else int(df["Order_Number"].nunique())}

    def generate_packing_lists(couriers: list[str]) -> dict:
        batch = [
            {
                "report_type": "packing_lists",
                "name": f"{c}_Orders",
                "output_filename": f"{c}_Orders.xlsx",
                "filters": [{"field": "Shipping_Provider", "operator": "==", "value": c}],
            }
            for c in couriers
        ]
        mw.actions_handler._generate_reports(batch, mw.session_path)
        return {"lists": sorted(p.stem for p in (Path(mw.session_path) / "packing_lists").glob("*.json"))}

    def set_fulfillable(order: str, value: bool) -> dict:
        mw.actions_handler.set_order_fulfillable(order, value)
        return {}

    def orders() -> list:
        df = mw.analysis_results_df
        if df is None:
            return []
        return [
            {
                "order": str(number),
                "status": str(group["Order_Fulfillment_Status"].iloc[0]),
                # the app's rule (shopify_tool/packing_lists.py): any row notes a repeat it can fulfil
                "repeat": any(
                    "Repeat" in note and not note.startswith("Cannot fulfill")
                    for note in group["System_note"].fillna("").astype(str)
                ),
            }
            for number, group in df.groupby("Order_Number")
        ]

    def save_client_setting(key: str, value) -> dict:
        config = mw.profile_manager.load_shopify_config(mw.current_client_id)
        config.setdefault("settings", {})[key] = value
        return {"saved": bool(mw.profile_manager.save_shopify_config(mw.current_client_id, config))}

    def client_setting(key: str) -> dict:
        config = mw.profile_manager.load_shopify_config(mw.current_client_id) or {}
        return {"value": config.get("settings", {}).get(key)}

    def quit_() -> dict:
        mw.close()
        return {}

    ac.serve({
        "create_client": create_client, "select_client": select_client, "new_session": new_session,
        "open_session": open_session, "set_inputs": set_inputs, "run_analysis": run_analysis,
        "generate_packing_lists": generate_packing_lists, "set_fulfillable": set_fulfillable,
        "orders": orders, "save_client_setting": save_client_setting, "client_setting": client_setting,
        "quit": quit_,
    })


if __name__ == "__main__":
    main()
