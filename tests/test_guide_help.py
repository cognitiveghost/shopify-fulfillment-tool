"""Help opener: the user guide PDF on the server, in the app's language."""

from pathlib import Path

import pytest
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox

from shared import i18n
from shared.guide import help as guide_help

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def bulgarian():
    i18n.set_language("bg", i18n.catalogue_files(ROOT, "bg"))
    yield
    i18n.set_language("en", [])


def _guide(server_root: Path, name: str) -> Path:
    path = server_root / "Guides" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF-1.4\n")
    return path


def test_guide_pdf_language_file(tmp_path, bulgarian):
    expected = _guide(tmp_path, "fulfilment-bg.pdf")

    assert guide_help.guide_pdf(tmp_path, "fulfilment") == expected


def test_guide_pdf_falls_back_to_en(tmp_path, bulgarian):
    expected = _guide(tmp_path, "fulfilment-en.pdf")

    assert guide_help.guide_pdf(tmp_path, "fulfilment") == expected


def test_guide_pdf_none_when_missing(tmp_path):
    assert guide_help.guide_pdf(tmp_path, "fulfilment") is None


def test_open_guide_opens_file(tmp_path, monkeypatch):
    path = _guide(tmp_path, "fulfilment-en.pdf")
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url) or True)

    guide_help.open_guide(None, tmp_path, "fulfilment")

    assert len(opened) == 1
    assert opened[0].toLocalFile() == str(path)


def test_open_guide_missing_warns(tmp_path, monkeypatch):
    warnings = []
    opened = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args))
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url) or True)

    guide_help.open_guide(None, tmp_path, "fulfilment")

    assert len(warnings) == 1
    assert str(Path(tmp_path) / "Guides") in warnings[0][2]
    assert not opened


def test_open_guide_warns_when_nothing_opens_it(tmp_path, monkeypatch):
    path = _guide(tmp_path, "fulfilment-en.pdf")
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args))
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: False)

    guide_help.open_guide(None, tmp_path, "fulfilment")

    assert len(warnings) == 1
    assert str(path) in warnings[0][2]


def test_guide_pdf_error_on_language_file_still_tries_en(tmp_path, bulgarian, monkeypatch):
    expected = _guide(tmp_path, "fulfilment-en.pdf")
    real_is_file = Path.is_file

    def flaky(self):
        if self.name == "fulfilment-bg.pdf":
            raise OSError("share hiccup")
        return real_is_file(self)

    monkeypatch.setattr(Path, "is_file", flaky)

    assert guide_help.guide_pdf(tmp_path, "fulfilment") == expected
