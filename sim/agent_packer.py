"""A packer PC. Run with packing-tool's venv, cwd = packing-tool, PYTHONPATH = this repo:
`python -m sim.agent_packer --config <pc config.ini>`."""

import os
import sys
from pathlib import Path

from sim import agent_common as ac

FAST_CLOCK = os.environ.get("SIM_FAST_CLOCK") == "1"


def main() -> None:
    from PySide6.QtWidgets import QApplication

    config = sys.argv[sys.argv.index("--config") + 1]
    app = QApplication([])  # noqa: F841 - must outlive the window
    ac.install_capture()
    from gui.main_window import MainWindow
    from packing_tool.session_lock_manager import SessionLockManager

    if FAST_CLOCK:  # a crashed PC's lock goes stale in seconds, not minutes
        SessionLockManager.HEARTBEAT_INTERVAL = 1
        SessionLockManager.STALE_TIMEOUT = 4
        original_start = MainWindow._start_heartbeat_timer

        def fast_heartbeat(self):
            original_start(self)
            self.heartbeat_timer.start(1000)

        MainWindow._start_heartbeat_timer = fast_heartbeat

    mw = MainWindow(skip_worker_selection=True, config_path=config)
    pc_name = os.environ["COMPUTERNAME"]
    worker = next((w for w in mw.worker_manager.get_all_workers() if w.name == pc_name), None)
    worker = worker or mw.worker_manager.create_worker(pc_name)
    mw.current_worker_id, mw.current_worker_name = worker.id, worker.name
    mw.show()
    QApplication.processEvents()
    ac.capture_calls("shared.components.toast", "toast", "toast")
    ac.capture_logs()

    def start_list(client_id: str, session_path: str, list_name: str) -> dict:
        mw._handle_start_packing_from_browser({
            "session_path": session_path, "client_id": client_id, "packing_list_name": list_name,
            "list_file": str(Path(session_path) / "packing_lists" / f"{list_name}.json"),
        })
        return {"started": mw.logic is not None}

    def completed() -> list[str]:
        return list(mw.logic.session_packing_state.get("completed_orders", []))

    def pack_order(order: str) -> dict:
        mw.on_scanner_input(order)
        items = mw.logic.orders_data[mw.logic.current_order_number]["items"]
        for item in items:
            for _ in range(int(float(item.get("Quantity", 1)))):  # the packing-list JSON's own key names
                mw.on_scanner_input(str(item["SKU"]))
        ac.pump_until(lambda: mw.logic is None or mw.logic.current_order_number is None, 5, f"closing {order}")
        return {"completed": mw.logic is not None and order in completed()}

    def skip() -> dict:
        mw._on_skip_order()
        return {}

    def end_session() -> dict:
        mw.end_session()
        return {"ended": mw.logic is None}

    def state() -> dict:
        if mw.logic is None:
            return {"active": False, "all": [], "completed": [], "skipped": [], "current": None}
        return {
            "active": True,
            "all": list(mw.logic.orders_data),
            "completed": completed(),
            "skipped": list(mw.logic.session_packing_state.get("skipped_orders", [])),
            "current": mw.logic.current_order_number,
        }

    def quit_() -> dict:
        mw.close()
        return {}

    ac.serve({
        "start_list": start_list, "pack_order": pack_order, "skip": skip,
        "end_session": end_session, "state": state, "quit": quit_,
    })


if __name__ == "__main__":
    main()
