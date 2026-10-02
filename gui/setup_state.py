"""Everything the Setup page draws, built in one place (phase 3 spec section 4).

Python owns every fact and every sentence: setup_state() returns one dict and
gui/web/setup.js renders it. No Qt in this module, so the whole rule set runs
under plain pytest.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from shopify_tool.core import ANALYSIS_STEPS

FILE_NOUN = {"orders": "orders file", "stock": "stock file"}
MAPPING_PAGE = {"orders": "Orders mapping", "stock": "Stock mapping"}
# How an internal column name reads in a sentence.
_INTERNAL = {
    "Order_Number": "order number",
    "SKU": "SKU",
    "Quantity": "quantity",
    "Shipping_Method": "shipping method",
    "Stock": "stock",
}
_DELIMITERS = {
    ",": "Comma  ,",
    ";": "Semicolon  ;",
    "\t": "Tab",
    "|": "Pipe  |",
    "mixed": "Mixed",
}
_STRATEGY = {"multi_first": "Multi-item first", "fifo": "Oldest first"}
_DASH = "—"


def _noop() -> None:
    pass


@dataclass
class FileSlot:
    """One of the two input files: where it is and whether it can be used.

    The only thing that knows whether its file is usable. Every mutator ends
    by calling on_change(), which is how the page hears about it.
    """

    kind: str  # "orders" | "stock"
    on_change: Callable[[], None] = _noop
    path: Path | None = None
    is_valid: bool = False
    name: str = ""
    is_folder: bool = False
    rows: int | None = None
    keys: int | None = None  # distinct orders, or distinct SKUs
    delimiter: str = ""  # the character; "mixed"; "" when unknown
    parts: list = field(default_factory=list)  # {"name", "rows"} per merged CSV
    note: str = ""
    problem: dict | None = None  # {"title", "text", "fix_page", "fix_label"}
    missing_columns: list = field(default_factory=list)
    present_columns: list = field(default_factory=list)

    def _reset(self, path) -> None:
        self.path = Path(path) if path is not None else None
        self.is_valid = False
        self.name = self.path.name if self.path is not None else ""
        self.is_folder = False
        self.rows = None
        self.keys = None
        self.delimiter = ""
        self.parts = []
        self.note = ""
        self.problem = None
        self.missing_columns = []
        self.present_columns = []

    def set_loaded(
        self, path, *, rows=None, keys=None, delimiter="", parts=(), note="", name=""
    ) -> None:
        self._reset(path)
        self.is_valid = True
        self.rows = rows
        self.keys = keys
        self.delimiter = delimiter
        self.parts = list(parts)
        self.is_folder = bool(self.parts)
        self.note = note
        if name:
            self.name = name
        self.on_change()

    def set_invalid(
        self, path, missing, present, names=None, *, rows=None, delimiter=""
    ) -> None:
        """The file is readable but lacks columns the mapping needs.

        `names` maps each missing CSV column to the internal name it is
        mapped to, so the sentence can say what the column is for.
        """
        self._reset(path)
        self.missing_columns = list(missing)
        self.present_columns = list(present)
        self.rows = rows
        self.delimiter = delimiter
        names = names or {}

        def internal(column: str) -> str:
            mapped = names.get(column, "")
            return _INTERNAL.get(mapped, mapped or column)

        file = FILE_NOUN[self.kind]
        if len(self.missing_columns) == 1:
            column = self.missing_columns[0]
            title = f"No {internal(column)} column"
            text = (
                f"The {file}'s header row has no “{column}” column, "
                f"which is mapped to {internal(column)}."
            )
        else:
            listed = ", ".join(f"“{c}” ({internal(c)})" for c in self.missing_columns)
            title = f"{len(self.missing_columns)} mapped columns missing"
            text = f"The {file}'s header row has none of: {listed}."
        self.problem = _problem(title, text, MAPPING_PAGE[self.kind])
        self.on_change()

    def set_problem(self, path, title: str, text: str, fix_page: str = "") -> None:
        self._reset(path)
        self.problem = _problem(title, text, fix_page)
        self.on_change()

    def clear(self) -> None:
        self._reset(None)
        self.on_change()


def _problem(title: str, text: str, fix_page: str) -> dict:
    return {
        "title": title,
        "text": text,
        "fix_page": fix_page,
        "fix_label": f"Open {fix_page}" if fix_page else "",
    }


@dataclass(frozen=True)
class SessionFacts:
    name: str
    opened: datetime | None
    analysed: datetime | None


@dataclass(frozen=True)
class MemoryFacts:
    on: bool
    skus: int
    session: str
    updated: datetime | None


@dataclass(frozen=True)
class RunFacts:
    running: bool = False
    step: int = 0
    cancelling: bool = False


def _n(value) -> str:
    return _DASH if value is None else f"{value:,}"


def _when(moment: datetime, now: datetime) -> str:
    local = moment.astimezone()
    if local.date() == now.astimezone().date():
        return local.strftime("%H:%M")
    return local.strftime("%d %b %H:%M")


def session_meta(client: str, session: SessionFacts, now: datetime) -> str:
    """What a page head says beside the session chip: "ACME · opened 14:02",
    "ACME · analysed 14:06" once analysed, the client alone with no time.
    Setup and Tools both draw it."""
    moment = session.analysed or session.opened
    verb = "analysed" if session.analysed is not None else "opened"
    return f"{client} · {verb} {_when(moment, now)}" if moment else client


def _stat(key: str, value) -> dict:
    return {"k": key, "v": _n(value), "muted": value is None}


def _card(slot: FileSlot, covered: bool) -> dict:
    if slot.path is None:
        return {
            "state": "missing",
            "badge": "From memory" if covered else "Missing",
            "badge_tone": "neutral",
            "name": "",
            "is_folder": False,
            "parts": [],
            "note": "",
            "stats": [],
            "problem": {},
        }
    delimiter = _DELIMITERS.get(slot.delimiter, slot.delimiter)
    problem = slot.problem or {}
    return {
        "state": "loaded" if slot.is_valid else "problem",
        "badge": "Loaded" if slot.is_valid else "Problem",
        "badge_tone": "success" if slot.is_valid else "danger",
        "name": slot.name,
        "is_folder": slot.is_folder,
        "parts": [{"name": p["name"], "rows": _n(p["rows"])} for p in slot.parts],
        "note": slot.note,
        "stats": [
            _stat("Rows", slot.rows),
            _stat("Orders" if slot.kind == "orders" else "SKUs", slot.keys),
            {"k": "Delimiter", "v": delimiter or _DASH, "muted": not delimiter},
        ],
        "problem": (
            {key: problem[key] for key in ("title", "text", "fix_label")}
            if problem
            else {}
        ),
    }


def _problem_row(slot: FileSlot) -> str:
    title = (slot.problem or {}).get("title", "")
    return f"Problem: {title[:1].lower()}{title[1:]}"


def setup_state(
    *,
    connected: bool,
    client: str,
    server_path: str,
    session: SessionFacts | None,
    orders: FileSlot,
    stock: FileSlot,
    memory: MemoryFacts,
    strategy: str,
    run: RunFacts,
    now: datetime,
) -> dict:
    """The one map the Setup page draws. Spec section 4.2 and 4.3."""
    if not connected and session is None:
        view = "unreachable"
    elif not client:
        view = "no_client"
    elif session is None:
        view = "no_session"
    else:
        view = "setup"

    strategy = strategy if strategy in _STRATEGY else "multi_first"
    strategy_title = _STRATEGY[strategy]
    strategy_words = strategy_title[:1].lower() + strategy_title[1:]

    orders_problem = orders.path is not None and not orders.is_valid
    stock_problem = stock.path is not None and not stock.is_valid
    memory_covers = memory.on and memory.skus > 0 and stock.path is None
    stock_ok = stock.is_valid or memory_covers
    ready = orders.is_valid and stock_ok
    analysed = session is not None and session.analysed is not None

    order_count, line_count = _n(orders.keys), _n(orders.rows)
    sku_count = _n(memory.skus if memory_covers else stock.keys)
    stock_phrase = (
        f"last run's stock for {sku_count} SKUs"
        if memory_covers
        else f"stock for {sku_count} SKUs"
    )

    if orders_problem:
        headline = "The orders file needs fixing before this can run"
    elif stock_problem:
        headline = "The stock file needs fixing before this can run"
    elif ready:
        headline = (
            f"{order_count} orders, {line_count} lines, {stock_phrase}, {strategy_words}"
        )
    elif orders.is_valid:
        headline = f"{order_count} orders, {line_count} lines, waiting for the stock file"
    elif stock_ok:
        headline = (
            f"{stock_phrase[:1].upper()}{stock_phrase[1:]}, waiting for the orders file"
        )
    else:
        headline = "Load both files to see what this run will do"

    if orders.is_valid:
        orders_row = f"{order_count} orders · {line_count} lines"
    elif orders_problem:
        orders_row = _problem_row(orders)
    else:
        orders_row = "Not loaded"

    if stock.is_valid:
        stock_row = f"Stock file · {sku_count} SKUs"
    elif memory_covers:
        stock_row = f"From {memory.session or 'memory'} · {sku_count} SKUs"
    elif stock_problem:
        stock_row = _problem_row(stock)
    else:
        stock_row = "Not loaded"

    tone = ""
    if run.running:
        reason = ""
    elif orders_problem:
        reason = "Fix the orders file to run."
    elif stock_problem:
        reason = "Fix the stock file to run."
    elif not orders.is_valid and not stock_ok:
        reason = "Load the orders and stock files to run."
    elif not orders.is_valid:
        reason = "Load the orders file to run."
    elif not stock_ok:
        reason = "Load the stock file to run."
    elif not connected:
        reason = "Server unreachable. Files stay loaded; Retry is in the sidebar."
        tone = "danger"
    elif analysed:
        reason = "Running again replaces this session's results."
    else:
        reason = "Results open when it finishes."

    if session is None:
        session_out = {}
    else:
        session_out = {
            "name": session.name,
            "title": "Session" if analysed else "New session",
            "meta": session_meta(client, session, now),
        }

    if not memory.on:
        previous = ""
    elif memory.skus > 0:
        bits = [f"Previous run {memory.session}".strip()]
        if memory.updated is not None:
            bits.append(memory.updated.astimezone().strftime("%d %b %H:%M"))
        bits.append(f"{_n(memory.skus)} SKUs")
        previous = " · ".join(bits)
    else:
        previous = "Nothing is remembered yet. The first run needs a stock file."

    last = len(ANALYSIS_STEPS) - 1
    step = min(max(int(run.step), 0), last)

    return {
        "view": view,
        "client": client,
        "server_path": server_path,
        "session": session_out,
        "files": {
            "orders": _card(orders, False),
            "stock": _card(stock, memory_covers),
        },
        "memory": {
            "on": memory.on,
            "text": (
                f"When on, a run with no stock file starts from the stock {client}'s "
                "previous run left. A loaded stock file is always used as it is."
            ),
            "previous": previous,
        },
        "strategy": strategy,
        "summary": {
            "headline": headline,
            "ready": ready,
            "rows": [
                {"k": "Orders", "v": orders_row, "muted": not orders.is_valid},
                {"k": "Stock", "v": stock_row, "muted": not stock_ok},
                {"k": "Strategy", "v": strategy_title, "muted": False},
            ],
            "reason": reason,
            "reason_tone": tone,
        },
        "run": {
            "enabled": (
                connected and session is not None and not run.running and ready
            ),
            "running": run.running,
            "locked": run.running,
            "step": step,
            "steps": len(ANALYSIS_STEPS),
            "step_name": ANALYSIS_STEPS[step] if run.running else "",
            "can_cancel": run.running and not run.cancelling and step < last,
            "cancelling": run.running and run.cancelling,
        },
    }
