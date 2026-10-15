import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QWidget

from shared import relaunch, update_flow
from shared.components.language_segment import LanguageSegment, switch_language


@pytest.fixture
def settings(tmp_path):
    return QSettings(str(tmp_path / "s.ini"), QSettings.IniFormat)


def test_buttons_are_codes_with_native_names(qtbot):
    seg = LanguageSegment()
    qtbot.addWidget(seg)
    assert [b.text() for b in seg.buttons.values()] == ["EN", "BG"]
    assert seg.buttons["bg"].toolTip() == "Български"
    assert seg.objectName() == "LanguageSegment"


def test_clicking_the_other_language_requests_it(qtbot):
    seg = LanguageSegment()
    qtbot.addWidget(seg)
    seg.set_language("en")
    with qtbot.waitSignal(seg.languageRequested) as blocker:
        seg.buttons["bg"].click()
    assert blocker.args == ["bg"]


def test_clicking_the_current_language_requests_nothing(qtbot):
    seg = LanguageSegment()
    qtbot.addWidget(seg)
    seg.set_language("en")
    with qtbot.assertNotEmitted(seg.languageRequested):
        seg.buttons["en"].click()


def test_switch_saves_and_restarts_on_accept(qtbot, settings, monkeypatch):
    relaunch._reset()
    window = QWidget()
    qtbot.addWidget(window)
    window.show()
    asked = []
    monkeypatch.setattr(update_flow, "ask", lambda w, **kw: asked.append(kw) or True)
    assert switch_language(window, settings, "bg") is True
    assert settings.value("language") == "bg"
    assert asked[0]["verb"] == "Restart now"
    assert relaunch.pending() is not None
    assert not window.isVisible()
    relaunch._reset()


def test_switch_cancel_keeps_the_choice_for_next_start(qtbot, settings, monkeypatch):
    relaunch._reset()
    window = QWidget()
    qtbot.addWidget(window)
    window.show()
    monkeypatch.setattr(update_flow, "ask", lambda w, **kw: False)
    assert switch_language(window, settings, "bg") is False
    assert settings.value("language") == "bg"
    assert relaunch.pending() is None
    assert window.isVisible()
