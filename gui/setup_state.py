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

from shared.i18n import N_, _, month_abbr
from shopify_tool.core import ANALYSIS_STEPS

FILE_HEADER = {
    "orders": N_("The orders file's header row"),
    "stock": N_("The stock file's header row"),
}
MAPPING_PAGE = {"orders": N_("Orders mapping"), "stock": N_("Stock mapping")}
# How an internal column name reads in a sentence.
_INTERNAL = {
    "Order_Number": N_("order number"),
    "SKU": N_("SKU"),
    "Quantity": N_("quantity"),
    "Shipping_Method": N_("shipping method"),
    "Stock": N_("stock"),
}
_DELIMITERS = {
    ",": N_("Comma  ,"),
    ";": N_("Semicolon  ;"),
    "\t": N_("Tab"),
    "|": N_("Pipe  |"),
    "mixed": N_("Mixed"),
}
_STRATEGY = {"multi_first": N_("Multi-item first"), "fifo": N_("Oldest first")}
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
            return _(_INTERNAL.get(mapped, mapped or column))

        header = _(FILE_HEADER[self.kind])
        if len(self.missing_columns) == 1:
            column = self.missing_columns[0]
            title = _("No {name} column", name=internal(column))
            text = _(
                "{header} has no “{column}” column, which is mapped to {name}.",
                header=header,
                column=column,
                name=internal(column),
            )
        else:
            listed = ", ".join(
                _("“{column}” ({name})", column=c, name=internal(c))
                for c in self.missing_columns
            )
            title = _(
                "{count} mapped columns missing", count=len(self.missing_columns)
            )
            text = _("{header} has none of: {listed}.", header=header, listed=listed)
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
        "fix_label": _("Open {page}", page=_(fix_page)) if fix_page else "",
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


def _num(value) -> str:
    return _DASH if value is None else f"{value:,}"


def _stamp(moment: datetime) -> str:
    """"%d %b %H:%M", with the month through month_abbr (strftime is English)."""
    return f"{moment:%d} {month_abbr(moment.month)} {moment:%H:%M}"


def _when(moment: datetime, now: datetime) -> str:
    local = moment.astimezone()
    if local.date() == now.astimezone().date():
        return local.strftime("%H:%M")
    return _stamp(local)


def session_meta(client: str, session: SessionFacts, now: datetime) -> str:
    """What a page head says beside the session chip: "ACME · opened 14:02",
    "ACME · analysed 14:06" once analysed, the client alone with no time.
    Setup and Tools both draw it."""
    moment = session.analysed or session.opened
    if not moment:
        return client
    when = _when(moment, now)
    if session.analysed is not None:
        return _("{client} · analysed {when}", client=client, when=when)
    return _("{client} · opened {when}", client=client, when=when)


def _stat(key: str, value) -> dict:
    return {"k": key, "v": _num(value), "muted": value is None}


def _card(slot: FileSlot, covered: bool) -> dict:
    if slot.path is None:
        return {
            "state": "missing",
            "badge": _("From memory") if covered else _("Missing"),
            "badge_tone": "neutral",
            "name": "",
            "is_folder": False,
            "parts": [],
            "note": "",
            "stats": [],
            "problem": {},
        }
    delimiter = _(_DELIMITERS.get(slot.delimiter, slot.delimiter))
    problem = slot.problem or {}
    return {
        "state": "loaded" if slot.is_valid else "problem",
        "badge": _("Loaded") if slot.is_valid else _("Problem"),
        "badge_tone": "success" if slot.is_valid else "danger",
        "name": slot.name,
        "is_folder": slot.is_folder,
        "parts": [{"name": p["name"], "rows": _num(p["rows"])} for p in slot.parts],
        "note": slot.note,
        "stats": [
            _stat(_("Rows"), slot.rows),
            _stat(_("Orders") if slot.kind == "orders" else _("SKUs"), slot.keys),
            {"k": _("Delimiter"), "v": delimiter or _DASH, "muted": not delimiter},
        ],
        "problem": (
            {key: problem[key] for key in ("title", "text", "fix_label")}
            if problem
            else {}
        ),
    }


def _problem_row(slot: FileSlot) -> str:
    title = (slot.problem or {}).get("title", "")
    return _("Problem: {problem}", problem=f"{title[:1].lower()}{title[1:]}")


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
    strategy_title = _(_STRATEGY[strategy])
    strategy_words = strategy_title[:1].lower() + strategy_title[1:]

    orders_problem = orders.path is not None and not orders.is_valid
    stock_problem = stock.path is not None and not stock.is_valid
    memory_covers = memory.on and memory.skus > 0 and stock.path is None
    stock_ok = stock.is_valid or memory_covers
    ready = orders.is_valid and stock_ok
    analysed = session is not None and session.analysed is not None

    order_count, line_count = _num(orders.keys), _num(orders.rows)
    sku_count = _num(memory.skus if memory_covers else stock.keys)
    if memory_covers:
        stock_phrase = _("last run's stock for {skus} SKUs", skus=sku_count)
    else:
        stock_phrase = _("stock for {skus} SKUs", skus=sku_count)

    if orders_problem:
        headline = _("The orders file needs fixing before this can run")
    elif stock_problem:
        headline = _("The stock file needs fixing before this can run")
    elif ready:
        headline = _(
            "{orders} orders, {lines} lines, {stock}, {strategy}",
            orders=order_count,
            lines=line_count,
            stock=stock_phrase,
            strategy=strategy_words,
        )
    elif orders.is_valid:
        headline = _(
            "{orders} orders, {lines} lines, waiting for the stock file",
            orders=order_count,
            lines=line_count,
        )
    elif stock_ok:
        headline = _(
            "{stock}, waiting for the orders file",
            stock=stock_phrase[:1].upper() + stock_phrase[1:],
        )
    else:
        headline = _("Load both files to see what this run will do")

    if orders.is_valid:
        orders_row = _(
            "{orders} orders · {lines} lines", orders=order_count, lines=line_count
        )
    elif orders_problem:
        orders_row = _problem_row(orders)
    else:
        orders_row = _("Not loaded")

    if stock.is_valid:
        stock_row = _("Stock file · {skus} SKUs", skus=sku_count)
    elif memory_covers:
        stock_row = _(
            "From {session} · {skus} SKUs",
            session=memory.session or _("memory"),
            skus=sku_count,
        )
    elif stock_problem:
        stock_row = _problem_row(stock)
    else:
        stock_row = _("Not loaded")

    tone = ""
    if run.running:
        reason = ""
    elif orders_problem:
        reason = _("Fix the orders file to run.")
    elif stock_problem:
        reason = _("Fix the stock file to run.")
    elif not orders.is_valid and not stock_ok:
        reason = _("Load the orders and stock files to run.")
    elif not orders.is_valid:
        reason = _("Load the orders file to run.")
    elif not stock_ok:
        reason = _("Load the stock file to run.")
    elif not connected:
        reason = _("Server unreachable. Files stay loaded; Retry is in the sidebar.")
        tone = "danger"
    elif analysed:
        reason = _("Running again replaces this session's results.")
    else:
        reason = _("Results open when it finishes.")

    if session is None:
        session_out = {}
    else:
        session_out = {
            "name": session.name,
            "title": _("Session") if analysed else _("New session"),
            "meta": session_meta(client, session, now),
        }

    if not memory.on:
        previous = ""
    elif memory.skus > 0:
        bits = [_("Previous run {session}", session=memory.session).strip()]
        if memory.updated is not None:
            bits.append(_stamp(memory.updated.astimezone()))
        bits.append(_("{skus} SKUs", skus=_num(memory.skus)))
        previous = " · ".join(bits)
    else:
        previous = _("Nothing is remembered yet. The first run needs a stock file.")

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
            "text": _(
                "When on, a run with no stock file starts from the stock {client}'s "
                "previous run left. A loaded stock file is always used as it is.",
                client=client,
            ),
            "previous": previous,
        },
        "strategy": strategy,
        "summary": {
            "headline": headline,
            "ready": ready,
            "rows": [
                {"k": _("Orders"), "v": orders_row, "muted": not orders.is_valid},
                {"k": _("Stock"), "v": stock_row, "muted": not stock_ok},
                {"k": _("Strategy"), "v": strategy_title, "muted": False},
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
