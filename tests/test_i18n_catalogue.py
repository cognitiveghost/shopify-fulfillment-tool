"""Every on-screen string has Bulgarian, and no UI text bypasses _() (ADR 0021)."""

import json
from pathlib import Path

import pytest

from shared import i18n_check as c

ROOT = Path(__file__).resolve().parent.parent
SHARED_BG = ROOT / "shared" / "assets" / "locales" / "bg.json"
APP_BG = ROOT / "locales" / "bg.json"

SHARED_PY = [p for p in c.files(ROOT / "shared", "*.py") if p.name != "i18n_check.py"]
APP_PY = c.files(ROOT / "gui", "*.py") + [ROOT / "gui_main.py"]
APP_HTML = c.files(ROOT / "gui" / "web", "*.html")
APP_JS = c.files(ROOT / "gui" / "web", "*.js")

# Every Python file is scanned for Qt-call literals. The scanner cannot see text
# kept in dicts (the *_state.py modules feeding the web pages); those are wrapped
# by hand in Tasks 13-15, and the HTML/JS lists below are filled there too.
GUARDED_PY: list[Path] = SHARED_PY + APP_PY
GUARDED_HTML: list[Path] = []
GUARDED_JS: list[Path] = []
# Text that is never translated, with the reason.
ALLOW = {
    "Fulfilment Tool",   # brand
    "Packer Assistant",  # brand
    "Shopify",           # brand
    "Ctrl+S",            # keyboard shortcut, shown as typed
    "{APP_NAME} {__version__}",  # window title: the brand and the version, nothing to translate
}


def _load(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _shared_keys():
    return c.python_keys(SHARED_PY)


def _app_keys():
    keys = c.python_keys(APP_PY)
    keys.update(c.html_keys(APP_HTML))
    keys.update(c.js_keys(APP_JS))
    return keys


@pytest.mark.parametrize("keys, catalogue", [
    (_shared_keys, SHARED_BG), (_app_keys, APP_BG),
])
def test_every_key_has_bulgarian(keys, catalogue):
    merged = {**_load(SHARED_BG), **_load(catalogue)}
    missing = sorted(k for k in keys() if k not in merged)
    assert not missing, f"No BG entry in {catalogue.name}: {missing}"


@pytest.mark.parametrize("keys, catalogue", [
    (_shared_keys, SHARED_BG), (_app_keys, APP_BG),
])
def test_no_orphan_entries(keys, catalogue):
    orphans = sorted(set(_load(catalogue)) - set(keys()))
    assert not orphans, f"{catalogue} has entries nothing uses: {orphans}"


@pytest.mark.parametrize("keys, catalogue", [
    (_shared_keys, SHARED_BG), (_app_keys, APP_BG),
])
def test_entries_are_well_formed(keys, catalogue):
    used = keys()
    for key, value in _load(catalogue).items():
        if used.get(key):  # plural
            assert isinstance(value, list) and len(value) == 2, key
            forms = value
        else:
            assert isinstance(value, str) and value.strip(), key
            forms = [value]
        for form in forms:
            assert c.placeholders(form) == c.placeholders(key), key


def test_catalogues_are_sorted_and_formatted():
    for path in (SHARED_BG, APP_BG):
        text = path.read_text(encoding="utf-8")
        assert text == json.dumps(json.loads(text), ensure_ascii=False, sort_keys=True, indent=2) + "\n", path


def test_no_bare_ui_literals():
    found = (c.bare_python_literals(GUARDED_PY, ALLOW)
             + c.bare_html_text(GUARDED_HTML, ALLOW)
             + c.bare_js_literals(GUARDED_JS, ALLOW))
    assert not found, "Wrap these in _() / data-i18n / t():\n" + "\n".join(found)
