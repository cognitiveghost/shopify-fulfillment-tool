"""The widget that shows the settings pages the web tier draws (phase 7 spec
section 6.5, phase 8 spec section 6.2).

One web view for every settings page. The window keeps the drafts in its page
list; this widget shows one of them at a time, hands the page's edits to it,
and says when it changed. It also runs Test rule (on a worker, since one order
rule over a whole analysis can take seconds) and the CSV imports and exports
of the pages that have them (phase 9 spec section 8).
"""

import logging

from PySide6.QtCore import QThreadPool, Signal
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QFileDialog, QVBoxLayout, QWidget

from gui.components import show_error
from gui.settings.bridge import mount_settings_page
from gui.settings.contract import FileProblem
from gui.settings.page_state import MappingDraft, read_file_columns
from gui.settings.rule_test import failed_view, run_rule_test, running_view
from gui.settings.rules_state import RulesDraft
from gui.worker import Worker

logger = logging.getLogger(__name__)

CSV_FILTER = "CSV Files (*.csv);;All Files (*)"


def _tested(token: int, uid: str, rule: dict, analysis_df, session: str) -> tuple[int, dict]:
    """The test, as the worker thread runs it: (token, the panel's view).

    It never raises. A test that fails is a view too, so the one signal the
    host listens to always arrives.
    """
    try:
        view = run_rule_test(rule, analysis_df, session)
    except Exception:
        logger.exception("The rule test didn't finish")
        view = failed_view(rule, session)
    return token, {"uid": uid, **view}


class SettingsWebHost(QWidget):
    """One web view and the drafts it draws, keyed as SettingsWindow's
    WEB_PAGE_KEYS names them.

    Signals:
        edited: a draft's values, or the file it reads columns from, changed
    """

    edited = Signal()

    def __init__(self, drafts: dict, analysis_df=None, session: str = "", parent=None):
        super().__init__(parent)
        self.drafts = drafts
        self.analysis_df = analysis_df
        self.session = session
        self._current = next(iter(drafts))
        # The Test panel as the page draws it, or None. A test's result is
        # wanted only while its token is still the current one.
        self._test: dict | None = None
        self._test_token = 0
        # ponytail: every worker a test started, kept until the dialog goes.
        # Dropping one while it runs destroys its signals under it. A handful
        # per dialog; prune on `finished` if someone tests by the hundred.
        self._test_workers: list[Worker] = []
        # (kind, path) of the last import that skipped rows it could update:
        # what the toast's "Update them" runs again.
        self._retry: tuple[str, str] | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.view = QWebEngineView(self)
        self.bridge = mount_settings_page(self.view)
        layout.addWidget(self.view, 1)

        self.bridge.editRequested.connect(self._on_edit)
        self.bridge.readColumnsRequested.connect(self._read_columns)
        self.bridge.testRequested.connect(self._start_test)
        self.bridge.testClosed.connect(self._close_test)
        self.bridge.importRequested.connect(self._import)
        self.bridge.exportRequested.connect(self._export)
        self.bridge.toastActionRequested.connect(self._update_import)
        self._push()

    def show_page(self, key: str) -> None:
        """Draw the draft under `key`. A Test panel does not follow."""
        self._current = key
        self._end_test()
        self._retry = None
        self._push()

    def focus_problem(self, key: str) -> None:
        """Put the operator on the control with this data-key. On Rules the
        control is drawn only while its rule is open, so that comes first."""
        if self.drafts[self._current].apply("reveal", [key]):
            self._push()
        self.view.setFocus()
        self.bridge.problemFocusRequested.emit(key)

    def _push(self) -> None:
        state = self.drafts[self._current].view()
        if self._test is not None:
            state = {**state, "test": self._test}
        self.bridge.set_state(state)

    def _start_test(self, uid: str) -> None:
        """Test... on a rule: show the panel, and run the rule on a worker."""
        draft = self.drafts[self._current]
        rule = draft.test_config(uid) if isinstance(draft, RulesDraft) else None
        if rule is None:
            # Not on Rules, or a rule the page draws Test... disabled for.
            return
        self._test_token += 1
        self._test = {"uid": uid, **running_view(rule, self.analysis_df, self.session)}
        self._push()
        worker = Worker(
            _tested, self._test_token, uid, rule, self.analysis_df, self.session
        )
        # A bound method, so the result is delivered on the GUI thread.
        worker.signals.result.connect(self._on_tested)
        self._test_workers.append(worker)
        QThreadPool.globalInstance().start(worker)

    def _on_tested(self, result) -> None:
        token, view = result
        if token != self._test_token or self._test is None:
            # The panel was closed, or another test took its place.
            return
        self._test = view
        self._push()

    def _end_test(self) -> bool:
        """Forget the panel and whatever result is still on its way."""
        self._test_token += 1
        showing = self._test is not None
        self._test = None
        return showing

    def _close_test(self) -> None:
        if self._end_test():
            self._push()

    def _on_edit(self, action: str, args: list) -> None:
        if not self.drafts[self._current].apply(action, args):
            # Nothing changed: a repeat of the current value, or an edit the
            # draft does not know.
            logger.debug(f"Settings edit changed nothing: {action} {args!r}")
            return
        self._push()
        self.edited.emit()

    def _read_columns(self) -> None:
        """Offer a chosen CSV's columns on the mapping page that is showing.

        Reads the header and one row, and detects the delimiter itself, so
        this does not depend on the delimiter General currently shows, which
        may hold an edit the operator has not saved yet.
        """
        draft = self.drafts[self._current]
        if not isinstance(draft, MappingDraft):
            return
        path, _filter = QFileDialog.getOpenFileName(
            self,
            f"Select {draft.kind.capitalize()} CSV",
            "",
            "CSV Files (*.csv);;All Files (*)",
        )
        if not path:
            return
        try:
            file = read_file_columns(path, loaded=False)
        except Exception:
            logger.exception("Failed to read column names from CSV")
            show_error(
                self, "The column names couldn't be read", "Details are in Logs."
            )
            return
        draft.set_file(file)
        self._push()
        self.edited.emit()

    def _import(self, kind: str, path: str | None = None, update: bool = False) -> None:
        """Import a CSV into the page that is showing. `kind` picks one of the
        draft's own imports; the path comes from the dialog, never the page."""
        draft = self.drafts[self._current]
        titles = getattr(draft, "imports", {})
        if kind not in titles:
            return
        if path is None:
            path, _filter = QFileDialog.getOpenFileName(self, titles[kind], "", CSV_FILTER)
            if not path:
                return
        self._retry = None
        try:
            text, can_update = draft.import_csv(kind, path, update)
        except FileProblem as problem:
            show_error(self, problem.headline, problem.detail)
            return
        except Exception:
            logger.exception(f"The {kind} import failed")
            show_error(self, draft.import_failed[kind], "Details are in Logs.")
            # It may have added rows before it failed.
            self._push()
            self.edited.emit()
            return
        if can_update:
            self._retry = (kind, path)
        self._push()
        self.edited.emit()
        # The toast's flag puts "Update them" on it.
        self.bridge.raise_toast(text, can_update)

    def _update_import(self) -> None:
        """The toast's "Update them": the same file again, updating the rows
        the first pass skipped."""
        if self._retry is not None:
            kind, path = self._retry
            self._import(kind, path, update=True)

    def _export(self, kind: str) -> None:
        draft = self.drafts[self._current]
        offered = getattr(draft, "exports", {})
        if kind not in offered:
            return
        title, name = offered[kind]
        path, _filter = QFileDialog.getSaveFileName(self, title, name, CSV_FILTER)
        if not path:
            return
        try:
            text = draft.export_csv(kind, path)
        except Exception:
            logger.exception(f"The {kind} export failed")
            show_error(self, draft.export_failed[kind], "Details are in Logs.")
            return
        self.bridge.raise_toast(text)
