"""The update offer around shared/updater.py (spec section 4.2, ADR 0022).

Updater does the network and disk work on a thread and reports through
signals only. UpdateFlow owns one sidebar button: hidden until a newer
release exists, then "Update to X", then download progress, then the swap
is armed and the window closes.
"""

from __future__ import annotations

import logging
import sys
import threading
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QToolButton, QWidget

from shared.components.confirm_dialog import ConfirmDialog
from shared.i18n import _
from shared.icons import icon
from shared.updater import (
    NO_PERMISSION,
    NOT_RELEASED,
    AppIdentity,
    Release,
    UpdateError,
    arm_install,
    install_blocker,
    is_server_copy,
    leftover,
    newer_release,
    parse_version,
    stage,
    staging_dir,
)

_log = logging.getLogger(__name__)


def ask(window, *, title: str, body: str, verb: str) -> bool:
    return ConfirmDialog(window, title=title, body=body, verb=verb).exec() == QDialog.Accepted


class Updater(QObject):
    available = Signal(object)
    upToDate = Signal(str)
    progress = Signal(int)
    staged = Signal(object)
    failed = Signal(str)

    def __init__(self, app: AppIdentity, version: str, app_dir: Path, parent=None):
        super().__init__(parent)
        self._app, self._version, self._app_dir = app, version, app_dir

    def _run(self, work) -> None:
        def body():
            try:
                work()
            except UpdateError as exc:
                self.failed.emit(_(exc.message, **exc.values))
            except Exception as exc:  # a thread must report, not die
                _log.exception("Update step failed")
                self.failed.emit(str(exc))
        threading.Thread(target=body, daemon=True).start()

    def check(self, manual: bool) -> None:
        def work():
            release = newer_release(self._app, self._version)
            if release is not None:
                self.available.emit(release)
            elif manual:
                self.upToDate.emit(self._version)
        self._run(work)

    def install(self, release: Release) -> None:
        def work():
            stage(release, self._app, self._app_dir, self.progress.emit)
            self.staged.emit(release)
        self._run(work)


class UpdateFlow(QObject):
    def __init__(self, window: QWidget, button: QToolButton, toast: Callable[[str], None],
                 app: AppIdentity, version: str, app_dir: Path | None = None,
                 frozen: bool | None = None, updater: Updater | None = None):
        super().__init__(window)
        self._window, self._button, self._toast = window, button, toast
        self._app, self._version = app, version
        self._app_dir = app_dir or Path(sys.executable).parent
        self._frozen = getattr(sys, "frozen", False) if frozen is None else frozen
        self._updater = updater or Updater(app, version, self._app_dir, self)
        self._release: Release | None = None
        self._manual = False
        self._installing = False
        button.hide()
        if button.icon().isNull():  # a sidebar tints its own
            button.setIcon(icon("download"))
        button.clicked.connect(self._on_click)
        self._updater.available.connect(self._on_available)
        self._updater.upToDate.connect(self._on_up_to_date)
        self._updater.progress.connect(self._on_progress)
        self._updater.staged.connect(self._on_staged)
        self._updater.failed.connect(self._on_failed)

    def _can_check(self) -> bool:
        return self._frozen and parse_version(self._version) is not None

    def start(self) -> None:
        version = leftover(self._app_dir)
        if version:
            self._toast(_("Update to {version} didn't finish: the app folder was in use. "
                          "Is it open on another PC?", version=version))
        if self._can_check():
            self._manual = False
            self._updater.check(manual=False)

    def check_now(self) -> None:
        if not self._can_check():
            self._toast(_(NOT_RELEASED))
            return
        self._manual = True
        self._updater.check(manual=True)

    def _show_offer(self) -> None:
        self._button.setText(_("Update to {version}", version=self._release.version))
        self._button.setToolTip(_("A new version is available"))
        self._button.setEnabled(True)
        self._button.show()

    def _on_available(self, release: Release) -> None:
        self._release = release
        self._show_offer()
        if self._manual:
            self._toast(_("Version {version} is available", version=release.version))

    def _on_up_to_date(self, version: str) -> None:
        self._toast(_("You have the latest version ({version})", version=version))

    def _on_failed(self, message: str) -> None:
        if self._installing:
            self._installing = False
            self._toast(message)
            self._show_offer()
        elif self._manual:
            self._toast(_("Couldn't check for updates: {message}", message=message))
        else:
            _log.info("Update check failed: %s", message)

    def _on_click(self) -> None:
        release = self._release
        if release is None:
            return
        reason = install_blocker(self._app_dir, self._frozen)
        if reason:
            # install_blocker returns English; translate from its constant.
            shown = (_(NOT_RELEASED) if reason == NOT_RELEASED
                     else _(NO_PERMISSION, folder=self._app_dir.parent))
            if ask(self._window, title=_("Can't update this copy"),
                   body=_("{reason} Download it from the release page instead.", reason=shown),
                   verb=_("Open release page")):
                QDesktopServices.openUrl(QUrl(release.page_url))
            return
        note = (_("This copy runs from the server: close it on every PC first.")
                if is_server_copy(self._app_dir) else "")
        body = _("The app downloads the update, then closes and restarts. What's new: {url} {note}",
                 url=release.page_url, note=note).rstrip()
        if ask(self._window, title=_("Update to {version}?", version=release.version),
               body=body, verb=_("Update and restart")):
            self._installing = True
            self._button.setEnabled(False)
            self._updater.install(release)

    def _on_progress(self, percent: int) -> None:
        self._button.setText(_("Downloading… {n}%", n=percent))

    def _on_staged(self, release: Release) -> None:
        self._installing = False
        arm_install(self._app_dir, staging_dir(self._app_dir), self._app.exe_name, release.version)
        self._button.setText(_("Update installs when you close the app"))
        self._window.close()
