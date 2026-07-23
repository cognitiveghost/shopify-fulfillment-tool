#!/usr/bin/env python3
"""Local dev runner: launches the app against a throwaway local dev-server."""
import os
from pathlib import Path

DEV_SERVER = Path(__file__).parent / "dev-server"
DEV_SERVER.mkdir(exist_ok=True)
os.environ.setdefault("FULFILLMENT_SERVER_PATH", str(DEV_SERVER))

from gui_main import main

if __name__ == "__main__":
    main()
