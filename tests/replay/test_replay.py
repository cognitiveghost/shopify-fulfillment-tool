"""Today's code reproduces 26 production sessions (spec Part B3; ~/Desktop/Server./findings.md §5).

A failure is a regression or a bug fixed since; decide which before touching an expected file.
Fixtures are anonymised by scripts/build_replay_fixtures.py and hold no customer data.
"""

import json
import re
from pathlib import Path

import pandas as pd
import pytest
from replay import first_difference, replay_session

FIXTURES = Path(__file__).parent / "fixtures"
SESSIONS = sorted(p.parent for p in FIXTURES.glob("*/*/meta.json"))
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
PHONE = re.compile(r"\+\d[\d \-]{8,}")
PATH = re.compile(r"\\\\|\b[A-Za-z]:\\")


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_the_suite_holds_all_26_sessions():
    assert len(SESSIONS) == 26


@pytest.mark.parametrize("session_dir", SESSIONS, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_replay_reproduces_the_stored_result(session_dir, tmp_path):
    analysis_data, lists = replay_session(session_dir, tmp_path)
    diff = first_difference(_read(session_dir / "expected" / "analysis_data.json"), analysis_data)
    assert diff is None, diff
    for stem, doc in lists.items():
        diff = first_difference(_read(session_dir / "expected" / "packing_lists" / f"{stem}.json"), doc)
        assert diff is None, f"{stem}: {diff}"


def test_fixtures_hold_no_pii():
    files = [p for p in FIXTURES.rglob("*") if p.is_file()]
    assert files
    for path in files:
        text = path.read_text(encoding="utf-8")
        for pattern in (EMAIL, PHONE, PATH):
            assert not pattern.search(text), f"{path.relative_to(FIXTURES)} matches {pattern.pattern}"
    for orders in FIXTURES.glob("*/*/orders.csv"):
        config = _read(orders.parent.parent / _read(orders.parent / "meta.json")["config"])
        mappings = config["column_mappings"]
        allowed = set(mappings["orders"]) | {"_source_file"} | {
            c["csv_name"] for c in mappings.get("additional_columns", []) or [] if c.get("enabled")}
        assert set(pd.read_csv(orders, nrows=0).columns) <= allowed, orders
    for history in FIXTURES.glob("*/history.csv"):
        assert set(pd.read_csv(history, nrows=0).columns) <= {"Order_Number", "Execution_Date", "Session"}
