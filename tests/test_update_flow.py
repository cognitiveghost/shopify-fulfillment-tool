from pathlib import Path

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QToolButton, QWidget

from shared import relaunch, update_flow, updater
from shared.updater import AppIdentity, Release

APP = AppIdentity("owner/repo", "FulfilmentTool", "FulfilmentTool.exe")
R = Release("2.4.0", "https://page", "zip", "sha")


class FakeUpdater(QObject):
    available = Signal(object)
    upToDate = Signal(str)
    progress = Signal(int)
    staged = Signal(object)
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        self.checks, self.installs = [], []

    def check(self, manual):
        self.checks.append(manual)

    def install(self, release):
        self.installs.append(release)


@pytest.fixture
def flow(qtbot, tmp_path, monkeypatch):
    relaunch._reset()
    window = QWidget()
    qtbot.addWidget(window)
    button = QToolButton(window)
    toasts, asked = [], []
    monkeypatch.setattr(update_flow, "ask", lambda w, **kw: asked.append(kw) or True)
    app_dir = tmp_path / "FulfilmentTool"
    app_dir.mkdir()
    fake = FakeUpdater()
    f = update_flow.UpdateFlow(window, button, toasts.append, APP, "2.3.1",
                               app_dir=app_dir, frozen=True, updater=fake)
    yield f, fake, button, toasts, asked, app_dir, window
    relaunch._reset()


def test_start_checks_silently_and_hides_the_button(flow):
    f, fake, button, _toasts, *_ = flow
    f.start()
    assert fake.checks == [False]
    assert button.isHidden()


def test_start_reports_a_failed_swap_first(flow):
    f, _fake, _button, toasts, _a, app_dir, _w = flow
    staged = updater.staging_dir(app_dir)
    staged.mkdir()
    (staged / "failed.txt").write_text("2.4.0")
    f.start()
    assert "2.4.0" in toasts[0] and "another PC" in toasts[0]


def test_dev_builds_never_check(qtbot, tmp_path):
    fake = FakeUpdater()
    window = QWidget()
    qtbot.addWidget(window)
    f = update_flow.UpdateFlow(window, QToolButton(window), [].append, APP, "dev",
                               app_dir=tmp_path, frozen=True, updater=fake)
    f.start()
    assert fake.checks == []


def test_available_shows_the_button(flow):
    f, fake, button, toasts, *_ = flow
    f.start()
    fake.available.emit(R)
    assert not button.isHidden()
    assert button.text() == "Update to 2.4.0"
    assert toasts == []


def test_manual_check_toasts_each_outcome(flow):
    f, fake, _button, toasts, *_ = flow
    f.check_now()
    assert fake.checks == [True]
    fake.upToDate.emit("2.3.1")
    fake.failed.emit("Could not reach GitHub: timed out")
    assert toasts == ["You have the latest version (2.3.1)",
                      "Couldn't check for updates: Could not reach GitHub: timed out"]


def test_a_silent_check_failure_says_nothing(flow):
    f, fake, button, toasts, *_ = flow
    f.start()
    fake.failed.emit("Could not reach GitHub: 403")
    assert toasts == [] and button.isHidden()


def test_click_confirms_then_installs_with_progress(flow):
    f, fake, button, _toasts, asked, *_ = flow
    f.start()
    fake.available.emit(R)
    button.click()
    assert asked[0]["verb"] == "Update and restart"
    assert "https://page" in asked[0]["body"]
    assert fake.installs == [R]
    assert not button.isEnabled()
    fake.progress.emit(42)
    assert button.text() == "Downloading… 42%"


def test_staged_arms_the_swap_and_closes(flow, qtbot):
    f, fake, button, _toasts, _asked, app_dir, window = flow
    window.show()
    f.start()
    fake.available.emit(R)
    button.click()
    updater.staging_dir(app_dir).mkdir()
    fake.staged.emit(R)
    assert relaunch.pending()[:2] == ["cmd", "/c"]
    assert button.text() == "Update installs when you close the app"
    assert not window.isVisible()


def test_install_failure_restores_the_button(flow):
    f, fake, button, toasts, *_ = flow
    f.start()
    fake.available.emit(R)
    button.click()
    fake.failed.emit("The download is damaged (checksum mismatch).")
    assert toasts == ["The download is damaged (checksum mismatch)."]
    assert button.isEnabled() and button.text() == "Update to 2.4.0"


def test_a_blocked_copy_offers_the_release_page(qtbot, tmp_path, monkeypatch):
    fake = FakeUpdater()
    window = QWidget()
    qtbot.addWidget(window)
    asked, opened = [], []
    monkeypatch.setattr(update_flow, "ask", lambda w, **kw: asked.append(kw) or True)
    monkeypatch.setattr(update_flow.QDesktopServices, "openUrl", lambda url: opened.append(url.toString()))
    button = QToolButton(window)
    update_flow.UpdateFlow(window, button, [].append, APP, "2.3.1",
                          app_dir=tmp_path / "x", frozen=False, updater=fake)
    fake.available.emit(R)
    button.click()
    assert asked[0]["verb"] == "Open release page"
    assert opened == ["https://page"]
    assert fake.installs == []


def test_server_copy_warns_in_the_confirm(flow, monkeypatch):
    _f, fake, button, _toasts, asked, *_ = flow
    monkeypatch.setattr(update_flow, "is_server_copy", lambda p: True)
    fake.available.emit(R)
    button.click()
    assert "close it on every PC first" in asked[0]["body"]


def test_updater_thread_reports_through_signals(qtbot, monkeypatch):
    monkeypatch.setattr(update_flow, "newer_release", lambda app, current: R)
    real = update_flow.Updater(APP, "2.3.1", Path("/nowhere"))
    with qtbot.waitSignal(real.available, timeout=3000) as blocker:
        real.check(manual=False)
    assert blocker.args == [R]


def test_updater_thread_reports_errors_translated(qtbot, monkeypatch):
    def boom(app, current):
        raise updater.UpdateError(updater.NO_CONNECTION, detail="timed out")
    monkeypatch.setattr(update_flow, "newer_release", boom)
    real = update_flow.Updater(APP, "2.3.1", Path("/nowhere"))
    with qtbot.waitSignal(real.failed, timeout=3000) as blocker:
        real.check(manual=True)
    assert blocker.args == ["Could not reach GitHub: timed out"]
