# App shell: EN/BG localisation, GitHub updater, Packer mark — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Both apps switch between English and Bulgarian (per PC, applied on restart), offer and install newer GitHub releases, and Packer's sidebar mark shows the Packer Assistant glyph.

**Architecture:** New `shared/` modules in Fulfilment (canonical): `i18n.py` (English-text-keyed catalogues), `i18n_check.py` (key and bare-literal scanners for tests), `relaunch.py` (run a command once the app has quit), `updater.py` (GitHub release check, download, stage, swap script), `update_flow.py` (the Qt flow around it), `components/language_segment.py` (the EN | BG switch). The web tier gets the catalogue through `PageBridge.strings`, and `shared/web/page.js` translates `data-i18n` elements and provides `t()`/`tn()`. Each app wires these into its `main()`, sidebar footer and overflow menu, then wraps its UI text. Packer receives `shared/` through `scripts/sync_shared.py`.

**Tech Stack:** Python 3.11+ stdlib (`json`, `ast`, `html.parser`, `urllib.request`, `hashlib`, `zipfile`, `subprocess`), PySide6 (Qt widgets, QtWebEngine, QWebChannel), pytest + pytest-qt.

**Spec:** `docs/superpowers/specs/2026-10-15-app-shell-i18n-updater-icon-design.md` (Fulfilment repo). ADRs 0021 and 0022. Read the spec's sections 3.1 (rules 1–5) and 3.6 (glossary) before any wrapping task.

## Repos and worktrees

- **F** = Fulfilment, worktree `/home/gloopy/Desktop/Projects/shopify-fulfillment-tool/.claude/worktrees/dr-34`
- **P** = Packer, worktree `/home/gloopy/Desktop/Projects/packing-tool/.claude/worktrees/dr-34`
- Both on branch `dr/34-shared-packer-tool-app-shell-en-bg-local`. Every path below is relative to the repo named in the task's heading.

## Commands (run from the task's repo root)

- One test file: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/<file>.py`
- Gate F: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` (about 10 minutes; run it in the background) then `.venv/bin/ruff check .`
- Gate P: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` then `.venv/bin/ruff check . --exclude shared`
- If `.venv` is missing in a worktree: `ln -s /home/gloopy/Desktop/Projects/<repo>/.venv .venv`
- Git: `/usr/bin/git`, one plain command per Bash call (no `&&`, `;`, `$VAR`). Commit with `/usr/bin/git commit -F <absolute path to a message file>`. Every commit message ends with:
  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01HYR6BKNh7pToEMqAgJihDb
  ```
- The pytest-guard hook blocks Bash text containing "pytest" other than the plain run form above, so write test files with Write/Edit.
- After code changes in F: `graphify update .`

## Global Constraints

- English source text is the key. English has no catalogue; a missing key falls back to English.
- Catalogues: `shared/assets/locales/bg.json` (keys used in `shared/`), `locales/bg.json` at each repo root (keys used by the app). JSON object, UTF-8, `sort_keys=True`, `ensure_ascii=False`, `indent=2`, trailing newline. A plural entry is keyed by its English singular and holds a 2-item list `[one, other]`.
- Rule 1: translate at display, never identity. Dict keys, enum values, page keys, saved values, values matched by logic, log messages and exception text stay English.
- Rule 2: no `_()` at import time. Module-level UI constants are written `N_("...")` and wrapped at display: `_(CONSTANT)`.
- Rule 3: whole sentences with named placeholders: `_("{n} of {m} labels matched", n=a, m=b)`. Never build a sentence by concatenation.
- Rule 4: backend exception detail stays English; the framing is translated: `_("Could not start the session: {detail}", detail=str(e))`.
- Rule 5: brand names (Fulfilment Tool, Packer Assistant, Shopify) are not wrapped.
- Bulgarian follows the spec's glossary (section 3.6): imperative singular on buttons ("Запази"), sentence case.
- `shopify_tool/` and `packing_tool/` (backend) are not wrapped. Files, exports, reports and logs are not translated. `shopify_tool/stock_export.py` is never touched.
- Language is stored per PC: F `QSettings("ShopifyFulfillmentTool", "FulfillmentApp")` key `language`; P `QSettings("PackingTool", "Language")` key `language`. Values: `"en"`, `"bg"`. Default `"en"`.
- No new dependency. No hardcoded colours: theme tokens only (`t.accent_fill`, `t.on_accent`, `t.surface`, `t.text`, …).
- No UI calls from background threads: threads emit Qt signals only.
- Never hand-edit `P/shared/`. It changes only through `P/scripts/sync_shared.py`.
- Never edit `F/shared/` after Task 9 except where a later task says so. If one must, re-run Task 18's sync before P work continues.

## Review Focus

1. **A UI string still English in BG** — an operator in BG sees no stray English except brand names and backend error detail. Pinned by the bare-literal guard (Tasks 2, 9–16, 19–22) and by the BG renders (Tasks 17, 23).
2. **A translated value reaching logic or a file** — e.g. Packer matching "Repeat" or a settings page keyed by its translated name. Pinned by the tests in Tasks 13 and 22, which run the affected behaviour with `set_language("bg", …)` active.
3. **Release asset or network surprises** — no `.zip` or `.sha256` asset, a tag like `v2.4.0`, an older tag, GitHub unreachable, a 403 rate limit. Expected: no button and no noise on the startup check; a clear toast on a manual check. Pinned in Task 5 (`newer_release`) and Task 6 (`UpdateFlow`).
4. **The app folder cannot be replaced** — read-only parent, a server copy open on another PC, a crash mid-download. Expected: a refusal with the release link, the old copy restarting, and the next start reporting the failure; never a half-swapped folder. Pinned in Task 5 (`install_blocker`, `leftover`, `swap_script` order).
5. **A close the app vetoes after "Restart now" / "Update and restart"** — Packer asks about an open session and the operator cancels. Expected: no second copy starts; the update stays armed for the next quit. Pinned in Task 4 (`on_quit` fires only on `aboutToQuit`) and Task 6.

## File structure

F (`shared/` is canonical):

| File | Responsibility |
|---|---|
| `shared/i18n.py` (new) | Active language and catalogue; `_`, `_n`, `N_`, `month_abbr`, `set_language`, `catalogue_files` |
| `shared/i18n_check.py` (new) | Scanners for tests: keys in Python/HTML/JS, bare literals in Python/HTML/JS, placeholders |
| `shared/relaunch.py` (new) | `on_quit(argv, update=False)`, `relaunch_argv()` |
| `shared/updater.py` (new) | Pure update logic: versions, GitHub query, staging, swap script, leftovers |
| `shared/update_flow.py` (new) | `Updater` (thread + signals) and `UpdateFlow` (button, dialogs, toasts) |
| `shared/components/language_segment.py` (new) | `LanguageSegment` widget, `switch_language()` |
| `shared/web_page.py` | `PageBridge.language` / `PageBridge.strings` |
| `shared/web/page.js` | `applyStrings`, `t`, `tn` |
| `shared/assets/locales/bg.json` (new) | BG for `shared/` keys |
| `shared/assets/icons/scan-barcode.svg`, `download.svg` (new) | Lucide glyphs |
| `locales/bg.json` (new) | BG for F's `gui/` keys |
| `tests/test_i18n.py`, `test_i18n_check.py`, `test_relaunch.py`, `test_updater.py`, `test_update_flow.py`, `test_language_segment.py`, `test_page_strings.py`, `test_i18n_catalogue.py` (new) | |
| `scripts/render_i18n.py` (new) | BG renders of F's main pages |

P: `locales/bg.json`, `tests/test_i18n_catalogue.py`, wiring in `main.py`, `gui/components/sidebar.py`, `gui/main_window.py`, `main.spec`, the workflow, and wrapped text in `gui/`.

---

## Part 1 — shared/ (F)

### Task 1: `shared/i18n.py`

**Files:**
- Create: `shared/i18n.py`, `shared/assets/locales/bg.json`
- Test: `tests/test_i18n.py`

**Interfaces:**
- Produces: `LANGUAGES: dict[str, str]`, `DEFAULT_LANGUAGE = "en"`, `set_language(code: str, files: list[Path]) -> None`, `language() -> str`, `_(text: str, **values) -> str`, `_n(one: str, other: str, n: int, **values) -> str`, `N_(text: str) -> str`, `catalogue() -> dict`, `month_abbr(month: int) -> str`, `catalogue_files(app_root: Path, code: str) -> list[Path]`, `SHARED_LOCALES: Path`.

- [ ] **Step 1: Write the failing test** `tests/test_i18n.py`

```python
import json

import pytest

from shared import i18n
from shared.i18n import N_, _, _n


@pytest.fixture(autouse=True)
def english_after():
    yield
    i18n.set_language("en", [])


def _cat(tmp_path, name, data):
    path = tmp_path / name
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def test_english_is_the_key_and_the_fallback(tmp_path):
    assert _("Save") == "Save"
    i18n.set_language("bg", [_cat(tmp_path, "a.json", {"Save": "Запази"})])
    assert i18n.language() == "bg"
    assert _("Save") == "Запази"
    assert _("Not translated") == "Not translated"


def test_placeholders_are_filled_after_lookup(tmp_path):
    i18n.set_language("bg", [_cat(tmp_path, "a.json", {"{n} of {m}": "{n} от {m}"})])
    assert _("{n} of {m}", n=2, m=5) == "2 от 5"
    assert _("{n} left", n=3) == "3 left"


def test_text_without_values_is_not_formatted():
    assert _("Use {braces} literally") == "Use {braces} literally"


def test_plurals_pick_one_or_other(tmp_path):
    assert _n("{n} order", "{n} orders", 1) == "1 order"
    assert _n("{n} order", "{n} orders", 3) == "3 orders"
    i18n.set_language("bg", [_cat(tmp_path, "a.json", {"{n} order": ["{n} поръчка", "{n} поръчки"]})])
    assert _n("{n} order", "{n} orders", 1) == "1 поръчка"
    assert _n("{n} order", "{n} orders", 0) == "0 поръчки"


def test_later_files_win_and_missing_files_are_skipped(tmp_path):
    first = _cat(tmp_path, "a.json", {"Save": "A", "Close": "Затвори"})
    second = _cat(tmp_path, "b.json", {"Save": "Запази"})
    i18n.set_language("bg", [first, tmp_path / "missing.json", second])
    assert _("Save") == "Запази"
    assert _("Close") == "Затвори"


def test_a_corrupt_file_is_skipped_not_fatal(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    i18n.set_language("bg", [bad, _cat(tmp_path, "b.json", {"Save": "Запази"})])
    assert _("Save") == "Запази"


def test_unknown_language_falls_back_to_english(tmp_path):
    i18n.set_language("xx", [_cat(tmp_path, "a.json", {"Save": "?"})])
    assert i18n.language() == "en"
    assert _("Save") == "Save"
    assert i18n.catalogue() == {}


def test_english_loads_no_catalogue(tmp_path):
    i18n.set_language("en", [_cat(tmp_path, "a.json", {"Save": "?"})])
    assert _("Save") == "Save"


def test_n_marker_returns_text_unchanged():
    assert N_("Saved.") == "Saved."


def test_month_abbr_is_translated():
    assert i18n.month_abbr(1) == "Jan"
    assert i18n.month_abbr(12) == "Dec"
    i18n.set_language("bg", [i18n.SHARED_LOCALES / "bg.json"])
    assert i18n.month_abbr(10) == "окт"


def test_catalogue_files_are_shared_then_app(tmp_path):
    files = i18n.catalogue_files(tmp_path, "bg")
    assert files == [i18n.SHARED_LOCALES / "bg.json", tmp_path / "locales" / "bg.json"]


def test_languages_name_themselves():
    assert i18n.LANGUAGES == {"en": "English", "bg": "Български"}
```

- [ ] **Step 2: Run it.** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_i18n.py` → FAIL (`ImportError: cannot import name 'i18n'`).

- [ ] **Step 3: Implement** `shared/i18n.py`

```python
"""On-screen text in this PC's language (ADR 0021).

English source text is the key: `_("Save")`. English has no catalogue, and a
key with no entry shows its English. Only text handed to the screen is wrapped;
identity values, files, logs and exception text stay English.

`set_language` runs in each app's main(), after modules are imported, so `_()`
must not run at import time: a module-level constant is `N_("...")` and is
wrapped where it is shown.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

LANGUAGES = {"en": "English", "bg": "Български"}
DEFAULT_LANGUAGE = "en"
SHARED_LOCALES = Path(__file__).resolve().parent / "assets" / "locales"


def N_(text: str) -> str:
    """Marks a constant for the key scanner; returns it unchanged."""
    return text


_MONTHS = (
    N_("Jan"), N_("Feb"), N_("Mar"), N_("Apr"), N_("May"), N_("Jun"),
    N_("Jul"), N_("Aug"), N_("Sep"), N_("Oct"), N_("Nov"), N_("Dec"),
)

_log = logging.getLogger(__name__)
_language = DEFAULT_LANGUAGE
_catalogue: dict = {}


def catalogue_files(app_root: Path, code: str) -> list[Path]:
    """The shared catalogue, then the app's: later files win."""
    return [SHARED_LOCALES / f"{code}.json", Path(app_root) / "locales" / f"{code}.json"]


def set_language(code: str, files: list[Path]) -> None:
    global _language, _catalogue
    if code not in LANGUAGES:
        _log.warning("Unknown language %r; using %s", code, DEFAULT_LANGUAGE)
        code = DEFAULT_LANGUAGE
    merged: dict = {}
    if code != DEFAULT_LANGUAGE:
        for path in files:
            if not path.is_file():
                continue
            try:
                merged.update(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError) as exc:
                _log.warning("Skipping catalogue %s: %s", path, exc)
    _language, _catalogue = code, merged


def language() -> str:
    return _language


def catalogue() -> dict:
    return _catalogue


def _(text: str, **values) -> str:
    found = _catalogue.get(text)
    out = found if isinstance(found, str) else text
    return out.format(**values) if values else out


def _n(one: str, other: str, n: int, **values) -> str:
    # ponytail: two plural forms; a language with more (ru, pl) needs a plural rule per language.
    found = _catalogue.get(one)
    forms = found if isinstance(found, list) and len(found) == 2 else [one, other]
    return forms[0 if n == 1 else 1].format(n=n, **values)


def month_abbr(month: int) -> str:
    """Replaces strftime("%b"), which is English whatever the language."""
    return _(_MONTHS[month - 1])
```

Create `shared/assets/locales/bg.json`:

```json
{
  "Apr": "апр",
  "Aug": "авг",
  "Dec": "дек",
  "Feb": "фев",
  "Jan": "яну",
  "Jul": "юли",
  "Jun": "юни",
  "Mar": "мар",
  "May": "май",
  "Nov": "ное",
  "Oct": "окт",
  "Sep": "сеп"
}
```

- [ ] **Step 4: Run it.** Same command → all pass.
- [ ] **Step 5: Commit** `shared/i18n.py shared/assets/locales/bg.json tests/test_i18n.py`, message `i18n: shared catalogue lookup keyed by English (ADR 0021)`.

---

### Task 2: `shared/i18n_check.py` (scanners for the guard tests)

**Files:**
- Create: `shared/i18n_check.py`
- Test: `tests/test_i18n_check.py`

**Interfaces:**
- Consumes: nothing (no Qt import, no `shared.i18n` import).
- Produces (all take `paths: Iterable[Path]`; a `Keys` is `dict[str, bool]`, key → is-plural):
  - `python_keys(paths) -> Keys`: first arg of `_(…)` and `N_(…)` (plural False) and of `_n(…)` (plural True), string literals only.
  - `html_keys(paths) -> Keys`: normalised text of each `data-i18n` element; each attribute value named by `data-i18n-attr`.
  - `js_keys(paths) -> Keys`: `t("…")`/`t('…')` (False) and `tn("…"`/`tn('…'` (True).
  - `bare_python_literals(paths, allow: set[str]) -> list[str]`, `bare_html_text(paths, allow) -> list[str]`, `bare_js_literals(paths, allow) -> list[str]`: each item is `"path:line: text"`. A literal is skipped when its text is in `allow`.
  - `placeholders(text: str) -> set[str]`.
  - `files(root: Path, pattern: str) -> list[Path]`: sorted `root.rglob(pattern)`, skipping `__pycache__`.

- [ ] **Step 1: Write the failing test** `tests/test_i18n_check.py`

```python
from shared import i18n_check as c


def _write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_python_keys(tmp_path):
    src = _write(tmp_path, "a.py", (
        'from shared.i18n import _, _n, N_\n'
        'X = N_("Saved.")\n'
        'def f(n, name):\n'
        '    label.setText(_("Save"))\n'
        '    _n("{n} order", "{n} orders", n)\n'
        '    _(name)\n'
    ))
    assert c.python_keys([src]) == {"Saved.": False, "Save": False, "{n} order": True}


def test_html_keys_collapse_whitespace(tmp_path):
    page = _write(tmp_path, "p.html", (
        '<button data-i18n>  Start\n   packing </button>'
        '<input data-i18n-attr="placeholder,title" placeholder="Search" title="Find a SKU">'
        '<p data-i18n>Ready &amp; waiting</p>'
    ))
    assert c.html_keys([page]) == {
        "Start packing": False, "Search": False, "Find a SKU": False, "Ready & waiting": False,
    }


def test_js_keys(tmp_path):
    js = _write(tmp_path, "p.js", (
        'el.textContent = t("Save");\n'
        "x = t('Close', {a: 1});\n"
        'y = tn("{n} order", "{n} orders", n);\n'
        'z = format("Save");\n'
    ))
    assert c.js_keys([js]) == {"Save": False, "Close": False, "{n} order": True}


def test_bare_python_literals(tmp_path):
    src = _write(tmp_path, "a.py", (
        'label.setText("Save")\n'
        'label.setText(_("Save"))\n'
        'QLabel("Name:", self)\n'
        'button.setToolTip(f"Open {name}")\n'
        'label.setText("")\n'
        'label.setText("—")\n'
        'ConfirmDialog(self, title="Delete?", body=_("Gone."), verb=_("Delete"))\n'
        'label.setText("Fulfilment Tool")\n'
        'QMessageBox.warning(self, "Oops", _("Bad"))\n'
        'toast(self, "Saved")\n'
    ))
    found = c.bare_python_literals([src], allow={"Fulfilment Tool"})
    assert found == [
        f"{src}:1: Save",
        f"{src}:3: Name:",
        f"{src}:4: Open {{name}}",
        f"{src}:7: Delete?",
        f"{src}:9: Oops",
        f"{src}:10: Saved",
    ]


def test_bare_html_text(tmp_path):
    page = _write(tmp_path, "p.html", (
        '<html><head><title>Logs</title><style>a{}</style></head><body>'
        '<h1 data-i18n>Logs</h1><p>Loose text</p><span>12</span>'
        '<script>var a = "x";</script></body></html>'
    ))
    assert c.bare_html_text([page], allow=set()) == [f"{page}:1: Loose text"]


def test_bare_js_literals(tmp_path):
    js = _write(tmp_path, "p.js", (
        'a.textContent = "Saved";\n'
        'a.textContent = t("Saved");\n'
        'a.title = "Open";\n'
        'a.placeholder = \'Search\';\n'
        'a.setAttribute("aria-label", "Close");\n'
        'a.className = "row";\n'
        'a.textContent = "";\n'
    ))
    assert c.bare_js_literals([js], allow=set()) == [
        f"{js}:1: Saved", f"{js}:3: Open", f"{js}:4: Search", f"{js}:5: Close",
    ]


def test_placeholders():
    assert c.placeholders("{n} of {m} labels") == {"n", "m"}
    assert c.placeholders("No fields") == set()


def test_files_skip_pycache(tmp_path):
    (tmp_path / "__pycache__").mkdir()
    _write(tmp_path, "a.py", "")
    (tmp_path / "__pycache__" / "b.py").write_text("", encoding="utf-8")
    assert c.files(tmp_path, "*.py") == [tmp_path / "a.py"]
```

- [ ] **Step 2: Run it** → FAIL (no module).

- [ ] **Step 3: Implement** `shared/i18n_check.py`

```python
"""Scanners behind the localisation guard tests (ADR 0021). No Qt.

Keys: what `_()`, `N_()`, `_n()` (Python), `data-i18n` (HTML) and `t()`/`tn()`
(JS) look up. Bare literals: UI text handed to the screen without them.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterable
from html.parser import HTMLParser
from pathlib import Path

Keys = dict[str, bool]  # key -> is a plural

# Calls whose first positional argument is on-screen text.
_TEXT_CALLS = {
    "setText", "setToolTip", "setWindowTitle", "setPlaceholderText", "setStatusTip",
    "addItem", "add_item", "add_section", "show_message",
    "QLabel", "QPushButton", "QToolButton", "QCheckBox", "QRadioButton", "QGroupBox", "QAction",
}
# Calls whose positional arguments after the first are on-screen text
# (toast(source, text), addTab(widget, name), QMessageBox.warning(parent, title, body)).
_TEXT_AFTER_FIRST = {
    "toast", "addTab", "insertTab", "setTabText", "question", "information", "warning",
    "critical", "getText", "getItem", "setHorizontalHeaderItem",
}
# Keyword arguments that are on-screen text, on any call (ConfirmDialog and friends).
_TEXT_KEYWORDS = {"title", "body", "verb", "action_text"}
_LETTER = re.compile(r"[^\W\d_]")
_FIELD = re.compile(r"\{(\w+)\}")
_JS_KEY = re.compile(r"""\b(tn|t)\(\s*(["'])((?:\\.|(?!\2).)*)\2""")
_JS_BARE = re.compile(
    r"""(?:\.(?:textContent|innerText|title|placeholder)\s*=\s*|"""
    r"""setAttribute\(\s*["'](?:aria-label|title|placeholder)["']\s*,\s*)(["'])((?:\\.|(?!\1).)*)\1"""
)


def files(root: Path, pattern: str) -> list[Path]:
    return sorted(p for p in Path(root).rglob(pattern) if "__pycache__" not in p.parts)


def placeholders(text: str) -> set[str]:
    return set(_FIELD.findall(text))


def _name(func: ast.expr) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _calls(paths: Iterable[Path]):
    for path in paths:
        tree = ast.parse(Path(path).read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                yield path, node


def python_keys(paths: Iterable[Path]) -> Keys:
    keys: Keys = {}
    for _path, call in _calls(paths):
        name = _name(call.func)
        if name in ("_", "N_", "_n") and call.args:
            arg = call.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                keys[arg.value] = name == "_n"
    return keys


def _literal_text(node: ast.expr) -> str | None:
    """The text of a bare str literal or f-string ({…} for each field)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(
            v.value if isinstance(v, ast.Constant) else "{" + ast.unparse(v.value) + "}"
            for v in node.values
        )
    return None


def bare_python_literals(paths: Iterable[Path], allow: set[str]) -> list[str]:
    found = []
    for path, call in _calls(paths):
        candidates = []
        name = _name(call.func)
        if name in _TEXT_CALLS and call.args:
            candidates.append(call.args[0])
        if name in _TEXT_AFTER_FIRST:
            candidates += call.args[1:]
        candidates += [k.value for k in call.keywords if k.arg in _TEXT_KEYWORDS]
        for node in candidates:
            text = _literal_text(node)
            if text and _LETTER.search(text) and text not in allow:
                found.append(f"{path}:{node.lineno}: {text}")
    return found


class _Html(HTMLParser):
    _SKIP = {"script", "style", "title"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.keys: Keys = {}
        self.bare: list[tuple[int, str]] = []
        self._stack: list[tuple[str, bool]] = []  # (tag, translated)
        self._buffer: list[str] = []

    def _inside(self, test) -> bool:
        return any(test(tag, translated) for tag, translated in self._stack)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        for name in (attrs.get("data-i18n-attr") or "").split(","):
            value = attrs.get(name.strip())
            if value:
                self.keys[value] = False
        if tag in ("input", "img", "br", "meta", "link", "hr"):
            return
        self._stack.append((tag, "data-i18n" in attrs))
        if "data-i18n" in attrs:
            self._buffer = []

    def handle_endtag(self, tag):
        if not any(name == tag for name, _tr in self._stack):
            return  # a void or stray end tag
        while self._stack:
            name, translated = self._stack.pop()
            if translated:
                key = " ".join("".join(self._buffer).split())
                if key:
                    self.keys[key] = False
            if name == tag:
                break

    def handle_data(self, data):
        if self._inside(lambda tag, tr: tr):
            self._buffer.append(data)
        elif not self._inside(lambda tag, tr: tag in self._SKIP) and _LETTER.search(data):
            self.bare.append((self.getpos()[0], " ".join(data.split())))


def _parse_html(path: Path) -> _Html:
    parser = _Html()
    parser.feed(Path(path).read_text(encoding="utf-8"))
    parser.close()
    return parser


def html_keys(paths: Iterable[Path]) -> Keys:
    keys: Keys = {}
    for path in paths:
        keys.update(_parse_html(path).keys)
    return keys


def bare_html_text(paths: Iterable[Path], allow: set[str]) -> list[str]:
    found = []
    for path in paths:
        for line, text in _parse_html(path).bare:
            if text not in allow:
                found.append(f"{path}:{line}: {text}")
    return found


def js_keys(paths: Iterable[Path]) -> Keys:
    keys: Keys = {}
    for path in paths:
        for fn, _q, text in _JS_KEY.findall(Path(path).read_text(encoding="utf-8")):
            keys[text] = fn == "tn"
    return keys


def bare_js_literals(paths: Iterable[Path], allow: set[str]) -> list[str]:
    found = []
    for path in paths:
        for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
            for _q, text in _JS_BARE.findall(line):
                if _LETTER.search(text) and text not in allow:
                    found.append(f"{path}:{number}: {text}")
    return found
```

- [ ] **Step 4: Run it** → pass. If `test_bare_html_text`'s line number differs, the parser is right and the fixture is one line: keep the fixture single-line.
- [ ] **Step 5: Commit** `shared/i18n_check.py tests/test_i18n_check.py`, message `i18n: key and bare-literal scanners for the guard tests`.

---

### Task 3: Web tier: `PageBridge.language` / `.strings`, `page.js` `applyStrings`/`t`/`tn`, and F's pages call it

**Files:**
- Modify: `shared/web_page.py` (class `PageBridge`, around lines 37–97), `shared/web/page.js`
- Modify: `gui/web/browse.js:598`, `results.js:870`, `settings.js:632`, `setup.js:391`, `logs.js:443`, `tools.js:554` (each page's bridge-ready callback)
- Create: `tests/fixtures/i18n_page.html`
- Test: `tests/test_page_strings.py`

**Interfaces:**
- Consumes: `shared.i18n.language()`, `shared.i18n.catalogue()`.
- Produces: Qt properties `PageBridge.language: str` and `PageBridge.strings: str` (JSON), both `constant=True`. JS globals `applyStrings(bridge)`, `t(text, vars)`, `tn(one, other, n, vars)`.

- [ ] **Step 1: Failing test.** Create `tests/fixtures/i18n_page.html` (create `tests/fixtures/` if absent):

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<style id="theme-vars">/* theme-vars */</style>
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<script src="../../shared/web/page.js" defer></script>
<script defer>
document.addEventListener("DOMContentLoaded", () => {
  new QWebChannel(qt.webChannelTransport, (channel) => {
    const bridge = channel.objects.bridge;
    applyStrings(bridge);
    document.getElementById("built").textContent = t("{n} of {m}", {n: 2, m: 5});
    document.getElementById("plural").textContent = tn("{n} order", "{n} orders", 3);
    document.documentElement.dataset.bridge = "ready";
  });
});
</script>
</head>
<body>
<button id="save" data-i18n> Save
  now </button>
<input id="search" data-i18n-attr="placeholder,title" placeholder="Search" title="Find">
<p id="missing" data-i18n>Not translated</p>
<p id="built"></p><p id="plural"></p>
</body>
</html>
```

Then `tests/test_page_strings.py`:

```python
import json
from pathlib import Path

import pytest
from PySide6.QtWebEngineWidgets import QWebEngineView
from test_results_bridge import _eval, _until_js

from gui.theme_manager import get_theme_manager
from shared import i18n
from shared.web_page import PageBridge, mount_page

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "i18n_page.html"
BG = {
    "Save now": "Запази сега",
    "Search": "Търси",
    "Find": "Намери",
    "{n} of {m}": "{n} от {m}",
    "{n} order": ["{n} поръчка", "{n} поръчки"],
}


@pytest.fixture
def page(qtbot, tmp_path):
    catalogue = tmp_path / "bg.json"
    catalogue.write_text(json.dumps(BG, ensure_ascii=False), encoding="utf-8")
    i18n.set_language("bg", [catalogue])
    view = QWebEngineView()
    qtbot.addWidget(view)
    bridge = PageBridge(view)
    mount_page(view, bridge, FIXTURE, "bridge", tokens=lambda: get_theme_manager().tokens())
    _until_js(qtbot, view, "document.documentElement.dataset.bridge === 'ready'")
    yield view
    i18n.set_language("en", [])


def test_bridge_carries_language_and_catalogue(tmp_path):
    i18n.set_language("bg", [])
    bridge = PageBridge()
    assert bridge.property("language") == "bg"
    assert json.loads(bridge.property("strings")) == {}
    i18n.set_language("en", [])


def test_marked_text_and_attributes_are_translated(qtbot, page):
    assert _eval(qtbot, page, "document.getElementById('save').textContent") == "Запази сега"
    assert _eval(qtbot, page, "document.getElementById('search').placeholder") == "Търси"
    assert _eval(qtbot, page, "document.getElementById('search').title") == "Намери"
    assert _eval(qtbot, page, "document.getElementById('missing').textContent") == "Not translated"
    assert _eval(qtbot, page, "document.documentElement.lang") == "bg"


def test_js_built_text_uses_t_and_tn(qtbot, page):
    assert _eval(qtbot, page, "document.getElementById('built').textContent") == "2 от 5"
    assert _eval(qtbot, page, "document.getElementById('plural').textContent") == "3 поръчки"
```

The fixture's `../../shared/web/page.js` resolves from `tests/fixtures/` to the repo's `shared/web/page.js` (mount_page uses the page's folder as base URL). Before running, check `mount_page`'s `tokens` argument against how `gui/logs_bridge.py` `mount_logs_page` calls it, and pass the same callable. The `get_theme_manager().tokens()` above is a guess: use whatever `mount_logs_page` passes.

- [ ] **Step 2: Run it** → FAIL (`language` property missing).

- [ ] **Step 3: Implement.** In `shared/web_page.py` add `import json` and `from shared import i18n`, and inside `PageBridge` (after the `themeCss` property):

```python
    # The page's language, read once at load (ADR 0021): a language applies
    # on restart, so these never change while the page lives.
    def _get_language(self) -> str:
        return i18n.language()

    language = Property(str, _get_language, constant=True)

    def _get_strings(self) -> str:
        return json.dumps(i18n.catalogue(), ensure_ascii=False)

    strings = Property(str, _get_strings, constant=True)
```

Append to `shared/web/page.js`:

```js
// The page in the PC's language (shared/i18n.py, ADR 0021). English text is the
// key; a key the catalogue lacks shows its English. Call applyStrings(bridge)
// once the bridge is ready and before the page first draws.
let STRINGS = {};

function formatText(text, vars) {
  if (!vars) return text;
  return text.replace(/\{(\w+)\}/g, (field, name) => (name in vars ? String(vars[name]) : field));
}

function t(text, vars) {
  const found = STRINGS[text];
  return formatText(typeof found === "string" ? found : text, vars);
}

function tn(one, other, n, vars) {
  const found = STRINGS[one];
  const forms = Array.isArray(found) && found.length === 2 ? found : [one, other];
  return formatText(n === 1 ? forms[0] : forms[1], Object.assign({ n }, vars));
}

function applyStrings(bridge) {
  STRINGS = JSON.parse(bridge.strings || "{}");
  document.documentElement.lang = bridge.language || "en";
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.textContent.replace(/\s+/g, " ").trim());
  });
  document.querySelectorAll("[data-i18n-attr]").forEach((el) => {
    for (const name of el.dataset.i18nAttr.split(",")) {
      const attr = name.trim();
      if (el.hasAttribute(attr)) el.setAttribute(attr, t(el.getAttribute(attr)));
    }
  });
}
```

In each of F's six page scripts, inside the QWebChannel callback, add `applyStrings(bridge);` as the first line after `const bridge = …` (before anything draws). Example for `gui/web/logs.js`: the callback that ends with `reportPaints(bridge);` at line 443 — put `applyStrings(bridge);` right after the line that obtains `bridge` from `channel.objects`.

- [ ] **Step 4: Run** `tests/test_page_strings.py` and the six page tests (`tests/test_logs_page.py tests/test_browse_page.py` and the results/settings/setup/tools page tests: `ls tests | grep -E "page|bridge"`) → pass (English is unchanged).
- [ ] **Step 5: Commit**, message `i18n: pages get the catalogue through PageBridge and translate data-i18n`.

---

### Task 4: `shared/relaunch.py`

**Files:**
- Create: `shared/relaunch.py`
- Test: `tests/test_relaunch.py`

**Interfaces:**
- Produces: `on_quit(argv: list[str], *, update: bool = False) -> None`, `relaunch_argv() -> list[str]`, `pending() -> list[str] | None` (for tests), `_start(argv, update)` (patched in tests).

- [ ] **Step 1: Failing test** `tests/test_relaunch.py`

```python
import sys

import pytest
from PySide6.QtCore import QCoreApplication

from shared import relaunch


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    started = []
    monkeypatch.setattr(relaunch, "_start", lambda argv, update: started.append((argv, update)))
    relaunch._reset()
    yield started
    relaunch._reset()


def test_nothing_runs_until_the_app_quits(qapp, clean):
    relaunch.on_quit(["app.exe"])
    assert clean == []
    QCoreApplication.instance().aboutToQuit.emit()
    assert clean == [(["app.exe"], False)]


def test_runs_once(qapp, clean):
    relaunch.on_quit(["app.exe"])
    relaunch.on_quit(["app.exe"])
    QCoreApplication.instance().aboutToQuit.emit()
    QCoreApplication.instance().aboutToQuit.emit()
    assert clean == [(["app.exe"], False)]


def test_an_update_is_never_replaced_by_a_plain_relaunch(qapp, clean):
    relaunch.on_quit(["cmd", "/c", "swap.cmd"], update=True)
    relaunch.on_quit(["app.exe"])
    assert relaunch.pending() == ["cmd", "/c", "swap.cmd"]
    QCoreApplication.instance().aboutToQuit.emit()
    assert clean == [(["cmd", "/c", "swap.cmd"], True)]


def test_an_update_replaces_a_plain_relaunch(qapp, clean):
    relaunch.on_quit(["app.exe"])
    relaunch.on_quit(["cmd", "/c", "swap.cmd"], update=True)
    assert relaunch.pending() == ["cmd", "/c", "swap.cmd"]


def test_relaunch_argv(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["gui_main.py", "--x"])
    monkeypatch.setattr(sys, "executable", "/py")
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert relaunch.relaunch_argv() == ["/py", "gui_main.py", "--x"]
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert relaunch.relaunch_argv() == ["/py", "--x"]
```

(`qapp` is pytest-qt's fixture.)

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** `shared/relaunch.py`

```python
"""Run one command after the app has really quit (ADR 0021, ADR 0022).

A restart for a new language and an update's swap script both wait for
QCoreApplication.aboutToQuit, so a close the app vetoes starts nothing.
An update's command is never replaced by a plain relaunch: its script
starts the app itself.
"""

from __future__ import annotations

import subprocess
import sys

from PySide6.QtCore import QCoreApplication

_pending: list[str] | None = None
_is_update = False
_connected = False


def relaunch_argv() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, *sys.argv[1:]]
    return [sys.executable, *sys.argv]


def on_quit(argv: list[str], *, update: bool = False) -> None:
    global _pending, _is_update, _connected
    if _is_update and not update:
        return
    _pending, _is_update = list(argv), update
    if not _connected:
        QCoreApplication.instance().aboutToQuit.connect(_fire)
        _connected = True


def pending() -> list[str] | None:
    return _pending


def _fire() -> None:
    global _pending
    if _pending is None:
        return
    argv, _pending = _pending, None
    _start(argv, _is_update)


def _start(argv: list[str], update: bool) -> None:
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        if update:
            flags |= subprocess.CREATE_NO_WINDOW
        subprocess.Popen(argv, close_fds=True, creationflags=flags)
    else:
        subprocess.Popen(argv, close_fds=True, start_new_session=True)


def _reset() -> None:
    """Tests only."""
    global _pending, _is_update
    _pending, _is_update = None, False
```

- [ ] **Step 4: Run** → pass.
- [ ] **Step 5: Commit**, message `relaunch: run a command once the app has quit`.

---

### Task 5: `shared/updater.py` (pure logic)

**Files:**
- Create: `shared/updater.py`
- Test: `tests/test_updater.py`

**Interfaces:**
- Consumes: `shared.relaunch.on_quit`.
- Produces: `AppIdentity(repo, asset_prefix, exe_name)`, `Release(version, page_url, zip_url, sha_url)`, `UpdateError(Exception)`, `parse_version(text) -> tuple[int, ...] | None`, `fetch_json(url) -> dict`, `fetch_to(url, dest: Path, progress) -> None`, `fetch_text(url) -> str`, `newer_release(app, current, fetch=fetch_json) -> Release | None`, `install_blocker(app_dir, frozen) -> str | None`, `is_server_copy(app_dir) -> bool`, `staging_dir(app_dir) -> Path`, `stage(release, app, app_dir, progress, download=fetch_to, read=fetch_text) -> Path`, `swap_script(app_dir, staged, exe_name, pid, version) -> str`, `arm_install(app_dir, staged, exe_name, version) -> Path`, `leftover(app_dir) -> str | None`.

The strings in this module are returned as **English** messages, and `UpdateFlow` (Task 6) translates them at display. So the messages are module-level `N_()` constants, and Task 6 calls `_()` on them. Rule 2 means `_()` never runs here.

- [ ] **Step 1: Failing test** `tests/test_updater.py`

```python
import hashlib
import os
import zipfile

import pytest

from shared import relaunch, updater
from shared.updater import AppIdentity, Release, UpdateError

APP = AppIdentity("owner/repo", "FulfilmentTool", "FulfilmentTool.exe")


def _payload(tag="2.4.0", assets=("FulfilmentTool-2.4.0.zip", "FulfilmentTool-2.4.0.zip.sha256")):
    return {
        "tag_name": tag,
        "html_url": f"https://github.com/owner/repo/releases/tag/{tag}",
        "assets": [{"name": n, "browser_download_url": f"https://dl/{n}"} for n in assets],
    }


@pytest.mark.parametrize("text, expected", [
    ("2.3.1", (2, 3, 1)), ("v2.4", (2, 4)), ("1.3.10.2", (1, 3, 10, 2)),
    ("dev", None), ("", None), ("2.x", None), (None, None),
])
def test_parse_version(text, expected):
    assert updater.parse_version(text) == expected


def test_a_newer_release_is_offered():
    release = updater.newer_release(APP, "2.3.1", fetch=lambda url: _payload())
    assert release == Release(
        "2.4.0", "https://github.com/owner/repo/releases/tag/2.4.0",
        "https://dl/FulfilmentTool-2.4.0.zip", "https://dl/FulfilmentTool-2.4.0.zip.sha256",
    )


def test_the_api_url_is_the_repos_latest_release():
    urls = []
    updater.newer_release(APP, "2.3.1", fetch=lambda url: urls.append(url) or _payload())
    assert urls == ["https://api.github.com/repos/owner/repo/releases/latest"]


@pytest.mark.parametrize("current, payload", [
    ("2.4.0", _payload()),                                   # same
    ("2.10.0", _payload()),                                  # older (numeric, not text, compare)
    ("dev", _payload()),                                     # dev build
    ("2.3.1", _payload(tag="nightly")),                      # tag does not parse
    ("2.3.1", _payload(assets=("FulfilmentTool-2.4.0.zip",))),  # no .sha256
    ("2.3.1", _payload(assets=("Other-2.4.0.zip", "Other-2.4.0.zip.sha256"))),
])
def test_nothing_is_offered(current, payload):
    assert updater.newer_release(APP, current, fetch=lambda url: payload) is None


def test_a_v_prefixed_tag_finds_assets_named_without_it():
    payload = _payload(tag="v2.4.0")
    release = updater.newer_release(APP, "2.3.1", fetch=lambda url: payload)
    assert release.version == "2.4.0"


def test_fetch_errors_surface_as_update_error():
    def boom(url):
        raise UpdateError("Network down")
    with pytest.raises(UpdateError):
        updater.newer_release(APP, "2.3.1", fetch=boom)


def test_install_blocker(tmp_path):
    app_dir = tmp_path / "FulfilmentTool"
    app_dir.mkdir()
    assert updater.install_blocker(app_dir, frozen=False) == updater.NOT_RELEASED
    assert updater.install_blocker(app_dir, frozen=True) is None


@pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0, reason="chmod is not a lock here")
def test_install_blocker_read_only_parent(tmp_path):
    parent = tmp_path / "ro"
    app_dir = parent / "FulfilmentTool"
    app_dir.mkdir(parents=True)
    parent.chmod(0o555)
    try:
        assert updater.install_blocker(app_dir, frozen=True) == updater.NO_PERMISSION.format(folder=parent)
    finally:
        parent.chmod(0o755)


def test_is_server_copy_unc():
    from pathlib import PureWindowsPath
    assert updater.is_server_copy(PureWindowsPath(r"\\server\share\FulfilmentTool"))


def _release_zip(tmp_path, with_exe=True):
    path = tmp_path / "src.zip"
    with zipfile.ZipFile(path, "w") as zf:
        if with_exe:
            zf.writestr("FulfilmentTool.exe", b"exe")
        zf.writestr("_internal/lib.dll", b"dll")
    return path


def _fakes(zip_path, digest=None):
    data = zip_path.read_bytes()
    digest = digest or hashlib.sha256(data).hexdigest()

    def download(url, dest, progress):
        dest.write_bytes(data)
        progress(100)

    return download, (lambda url: f"{digest}  FulfilmentTool-2.4.0.zip\n")


RELEASE = Release("2.4.0", "page", "zip", "sha")


def test_stage_extracts_beside_the_app(tmp_path):
    app_dir = tmp_path / "FulfilmentTool"
    app_dir.mkdir()
    download, read = _fakes(_release_zip(tmp_path))
    seen = []
    staged = updater.stage(RELEASE, APP, app_dir, seen.append, download=download, read=read)
    assert staged == tmp_path / "FulfilmentTool.update"
    assert (staged / "FulfilmentTool.exe").read_bytes() == b"exe"
    assert (staged / "_internal" / "lib.dll").is_file()
    assert seen[-1] == 100


def test_stage_rejects_a_bad_checksum_and_cleans_up(tmp_path):
    app_dir = tmp_path / "FulfilmentTool"
    app_dir.mkdir()
    download, read = _fakes(_release_zip(tmp_path), digest="0" * 64)
    with pytest.raises(UpdateError):
        updater.stage(RELEASE, APP, app_dir, lambda p: None, download=download, read=read)
    assert not (tmp_path / "FulfilmentTool.update").exists()


def test_stage_rejects_a_zip_without_the_exe(tmp_path):
    app_dir = tmp_path / "FulfilmentTool"
    app_dir.mkdir()
    download, read = _fakes(_release_zip(tmp_path, with_exe=False))
    with pytest.raises(UpdateError):
        updater.stage(RELEASE, APP, app_dir, lambda p: None, download=download, read=read)
    assert not (tmp_path / "FulfilmentTool.update").exists()


def test_stage_replaces_an_old_staging_folder(tmp_path):
    app_dir = tmp_path / "FulfilmentTool"
    app_dir.mkdir()
    old = tmp_path / "FulfilmentTool.update"
    old.mkdir()
    (old / "stale.txt").write_text("x")
    download, read = _fakes(_release_zip(tmp_path))
    staged = updater.stage(RELEASE, APP, app_dir, lambda p: None, download=download, read=read)
    assert not (staged / "stale.txt").exists()


def test_swap_script_steps_in_order(tmp_path):
    from pathlib import PureWindowsPath as W
    text = updater.swap_script(
        W(r"C:\Apps\Fulfil 100%"), W(r"C:\Apps\Fulfil 100%.update"), "FulfilmentTool.exe", 4242, "2.4.0"
    )
    order = [
        'tasklist /FI "PID eq 4242"',
        'rd /s /q "C:\\Apps\\Fulfil 100%%.previous"',
        'ren "C:\\Apps\\Fulfil 100%%" "Fulfil 100%%.previous"',
        'ren "C:\\Apps\\Fulfil 100%%.update" "Fulfil 100%%"',
        'robocopy "C:\\Apps\\Fulfil 100%%.previous" "C:\\Apps\\Fulfil 100%%" /E /XC /XN /XO',
        'start "" "C:\\Apps\\Fulfil 100%%\\FulfilmentTool.exe"',
    ]
    positions = [text.index(step) for step in order]
    assert positions == sorted(positions)
    assert "failed.txt" in text and "2.4.0" in text
    assert "if %n% geq 60" in text


def test_arm_install_writes_the_script_and_arms_on_quit(tmp_path, qapp):
    relaunch._reset()
    app_dir = tmp_path / "FulfilmentTool"
    staged = tmp_path / "FulfilmentTool.update"
    app_dir.mkdir()
    staged.mkdir()
    script = updater.arm_install(app_dir, staged, "FulfilmentTool.exe", "2.4.0")
    assert script == tmp_path / "FulfilmentTool.update.cmd"
    assert script.read_text(encoding="utf-8").startswith("@echo off")
    assert relaunch.pending() == ["cmd", "/c", str(script)]
    relaunch._reset()


def test_leftover_reports_a_failed_swap_and_cleans_up(tmp_path):
    app_dir = tmp_path / "FulfilmentTool"
    staged = tmp_path / "FulfilmentTool.update"
    app_dir.mkdir()
    staged.mkdir()
    (staged / "failed.txt").write_text("2.4.0\n")
    (tmp_path / "FulfilmentTool.update.cmd").write_text("x")
    assert updater.leftover(app_dir) == "2.4.0"
    assert not staged.exists()
    assert not (tmp_path / "FulfilmentTool.update.cmd").exists()


def test_leftover_removes_a_half_download_silently(tmp_path):
    app_dir = tmp_path / "FulfilmentTool"
    app_dir.mkdir()
    (tmp_path / "FulfilmentTool.update").mkdir()
    assert updater.leftover(app_dir) is None
    assert not (tmp_path / "FulfilmentTool.update").exists()


def test_leftover_nothing(tmp_path):
    app_dir = tmp_path / "FulfilmentTool"
    app_dir.mkdir()
    assert updater.leftover(app_dir) is None
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** `shared/updater.py`

```python
"""Find, fetch and stage a newer GitHub release; swap it in after exit (ADR 0022).

Pure logic plus stdlib I/O. No Qt here except through shared.relaunch; the
flow around it (thread, button, dialogs) is shared/update_flow.py.
Messages are English constants, translated where they are shown.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import shutil
import tempfile
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePath

from shared import relaunch
from shared.i18n import N_

API = "https://api.github.com/repos/{repo}/releases/latest"
TIMEOUT_S = 5
CHUNK = 1 << 20
RENAME_TRIES = 60

NOT_RELEASED = N_("Updates install only in the released app.")
NO_PERMISSION = N_("No permission to write to {folder}.")
BAD_CHECKSUM = N_("The download is damaged (checksum mismatch).")
NO_EXE = N_("The download does not contain {exe}.")
NO_CONNECTION = N_("Could not reach GitHub: {detail}")


@dataclass(frozen=True)
class AppIdentity:
    repo: str
    asset_prefix: str
    exe_name: str


@dataclass(frozen=True)
class Release:
    version: str
    page_url: str
    zip_url: str
    sha_url: str


class UpdateError(Exception):
    """`args[0]` is an English message constant, `values` its fields."""

    def __init__(self, message: str, **values):
        super().__init__(message)
        self.message, self.values = message, values


def parse_version(text) -> tuple[int, ...] | None:
    if not isinstance(text, str):
        return None
    parts = text.strip().removeprefix("v").split(".")
    if not all(p.isdigit() for p in parts):
        return None
    return tuple(int(p) for p in parts)


def _get(url: str, accept: str):
    request = urllib.request.Request(
        url, headers={"Accept": accept, "User-Agent": "shared-updater"}
    )
    try:
        return urllib.request.urlopen(request, timeout=TIMEOUT_S)
    except (urllib.error.URLError, OSError) as exc:
        raise UpdateError(NO_CONNECTION, detail=str(exc)) from exc


def fetch_json(url: str) -> dict:
    with _get(url, "application/vnd.github+json") as response:
        try:
            return json.loads(response.read().decode("utf-8"))
        except ValueError as exc:
            raise UpdateError(NO_CONNECTION, detail=str(exc)) from exc


def fetch_text(url: str) -> str:
    with _get(url, "application/octet-stream") as response:
        return response.read().decode("utf-8", "replace")


def fetch_to(url: str, dest: Path, progress: Callable[[int], None]) -> None:
    with _get(url, "application/octet-stream") as response, open(dest, "wb") as out:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        while chunk := response.read(CHUNK):
            out.write(chunk)
            done += len(chunk)
            if total:
                progress(min(99, done * 100 // total))
    progress(100)


def newer_release(app: AppIdentity, current: str, fetch=fetch_json) -> Release | None:
    mine = parse_version(current)
    if mine is None:
        return None
    data = fetch(API.format(repo=app.repo))
    tag = str(data.get("tag_name", ""))
    theirs = parse_version(tag)
    if theirs is None or theirs <= mine:
        return None
    version = tag.strip().removeprefix("v")
    urls = {a.get("name"): a.get("browser_download_url") for a in data.get("assets", [])}
    zip_name = f"{app.asset_prefix}-{version}.zip"
    if not urls.get(zip_name) or not urls.get(zip_name + ".sha256"):
        return None
    return Release(version, str(data.get("html_url", "")), urls[zip_name], urls[zip_name + ".sha256"])


def install_blocker(app_dir: Path, frozen: bool) -> str | None:
    """English reason this copy cannot update itself, or None."""
    if not frozen:
        return NOT_RELEASED
    parent = Path(app_dir).parent
    try:
        with tempfile.NamedTemporaryFile(dir=parent):
            pass
    except OSError:
        return NO_PERMISSION.format(folder=parent)
    return None


def is_server_copy(app_dir: PurePath) -> bool:
    text = str(app_dir)
    if text.startswith("\\\\") or text.startswith("//"):
        return True
    if os.name == "nt" and len(text) > 1 and text[1] == ":":
        DRIVE_REMOTE = 4
        return ctypes.windll.kernel32.GetDriveTypeW(text[:2] + "\\") == DRIVE_REMOTE
    return False


def staging_dir(app_dir: Path) -> Path:
    return Path(app_dir).parent / f"{Path(app_dir).name}.update"


def stage(release, app, app_dir, progress, download=fetch_to, read=fetch_text) -> Path:
    staged = staging_dir(app_dir)
    shutil.rmtree(staged, ignore_errors=True)
    fd, name = tempfile.mkstemp(suffix=".zip")
    os.close(fd)
    archive = Path(name)
    try:
        download(release.zip_url, archive, progress)
        expected = (read(release.sha_url).split() or [""])[0].lower()
        digest = hashlib.sha256()
        with open(archive, "rb") as handle:
            while chunk := handle.read(CHUNK):
                digest.update(chunk)
        if digest.hexdigest() != expected:
            raise UpdateError(BAD_CHECKSUM)
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(staged)
        if not (staged / app.exe_name).is_file():
            raise UpdateError(NO_EXE, exe=app.exe_name)
        return staged
    except BaseException:
        shutil.rmtree(staged, ignore_errors=True)
        raise
    finally:
        archive.unlink(missing_ok=True)


def _q(path) -> str:
    """A path for a .cmd line: quoted, % doubled."""
    return '"' + str(path).replace("%", "%%") + '"'


def swap_script(app_dir, staged, exe_name: str, pid: int, version: str) -> str:
    previous = app_dir.parent / f"{app_dir.name}.previous"
    name = app_dir.name.replace("%", "%%")
    exe = app_dir / exe_name
    return "\r\n".join([
        "@echo off",
        "rem Written by shared/updater.py (ADR 0022): swaps in a new release after the app exits.",
        ":waitpid",
        f'tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul && (timeout /t 1 /nobreak >nul & goto waitpid)',
        f"if exist {_q(previous)} rd /s /q {_q(previous)}",
        "set n=0",
        ":rename",
        f'ren {_q(app_dir)} "{name}.previous" 2>nul && goto swap',
        "set /a n+=1",
        f"if %n% geq {RENAME_TRIES} goto fail",
        "timeout /t 1 /nobreak >nul",
        "goto rename",
        ":swap",
        f'ren {_q(staged)} "{name}"',
        f"robocopy {_q(previous)} {_q(app_dir)} /E /XC /XN /XO /NFL /NDL /NJH /NJS >nul",
        f'start "" {_q(exe)}',
        '(goto) 2>nul & del "%~f0"',
        ":fail",
        f"echo {version}> {_q(staged / 'failed.txt')}",
        f'start "" {_q(exe)}',
        "exit /b 1",
        "",
    ])


def arm_install(app_dir: Path, staged: Path, exe_name: str, version: str) -> Path:
    script = Path(app_dir).parent / f"{Path(app_dir).name}.update.cmd"
    text = swap_script(Path(app_dir), Path(staged), exe_name, os.getpid(), version)
    script.write_text(text, encoding="utf-8", newline="")
    relaunch.on_quit(["cmd", "/c", str(script)], update=True)
    return script


def leftover(app_dir: Path) -> str | None:
    """At startup: the version a failed swap left behind, after cleaning up."""
    staged = staging_dir(app_dir)
    script = Path(app_dir).parent / f"{Path(app_dir).name}.update.cmd"
    marker = staged / "failed.txt"
    version = marker.read_text(encoding="utf-8").strip() if marker.is_file() else None
    shutil.rmtree(staged, ignore_errors=True)
    script.unlink(missing_ok=True)
    return version or None
```

Notes:
- `swap_script` takes `PurePath` objects so tests can pass `PureWindowsPath`. Use `app_dir.parent` and `app_dir.name`, which work on both.
- `leftover` must run before `check()` at startup (Task 6).

- [ ] **Step 4: Run** → pass. Run `.venv/bin/ruff check shared/updater.py`.
- [ ] **Step 5: Commit**, message `updater: find, verify and stage a GitHub release; swap script (ADR 0022)`.

---

### Task 6: `shared/update_flow.py` (thread, button, dialogs, toasts) and the two icons

**Files:**
- Create: `shared/update_flow.py`, `shared/assets/icons/scan-barcode.svg`, `shared/assets/icons/download.svg`
- Modify: `tests/test_ui_assets.py` (`EXPECTED_ICONS`: add `"scan-barcode", "download"`), `shared/assets/locales/bg.json`
- Test: `tests/test_update_flow.py`

**Interfaces:**
- Consumes: Task 5 (`newer_release`, `stage`, `arm_install`, `install_blocker`, `is_server_copy`, `leftover`, `UpdateError`, `Release`, `AppIdentity`), `shared.i18n._`, `shared.components.confirm_dialog.ConfirmDialog`, `shared.icons.icon`.
- Produces:
  - `class Updater(QObject)` with signals `available(object)` (a `Release`), `upToDate(str)`, `progress(int)`, `staged(object)`, `failed(str)`, and methods `check(manual: bool)` and `install(release)`. Work runs on `threading.Thread(daemon=True)`; results are emitted as signals (queued to the GUI thread).
  - `class UpdateFlow(QObject)`: `UpdateFlow(window: QWidget, button: QToolButton, toast: Callable[[str], None], app: AppIdentity, version: str, app_dir: Path | None = None, frozen: bool | None = None, updater: Updater | None = None)`. Methods `start()` (runs `leftover` then a silent check) and `check_now()` (manual). It owns the button's text, visibility, enabled state and click.
  - `ask(window, *, title, body, verb) -> bool` (module function wrapping `ConfirmDialog(...).exec() == QDialog.Accepted`), patched in tests.

Behaviour (spec 4.2):

| Event | Effect |
|---|---|
| `start()` | `v = leftover(app_dir)` → if `v`: toast `_("Update to {version} didn't finish: the app folder was in use. Is it open on another PC?", version=v)`. Then `updater.check(manual=False)` unless `parse_version(version)` is None or not frozen. |
| `available(r)` | button text `_("Update to {version}", version=r.version)`, tooltip `_("A new version is available")`, icon `download`, visible, enabled. If manual: toast `_("Version {version} is available", version=r.version)`. |
| `upToDate(v)` (manual only) | toast `_("You have the latest version ({version})", version=v)` |
| `failed(msg)` | manual check: toast `_("Couldn't check for updates: {message}", message=msg)`. Install: toast `msg`, button back to `Update to …`, enabled. Silent check: nothing (logged at INFO). |
| click, blocker | `ask(window, title=_("Can't update this copy"), body=_(reason) + " " + _("Download it from the release page instead."), verb=_("Open release page"))` → accepted: `QDesktopServices.openUrl(QUrl(r.page_url))`. |
| click, ok | `ask(window, title=_("Update to {version}?", …), body=_("The app downloads the update, then closes and restarts. What's new: {url}", url=r.page_url)` + (server copy: `" " + _("This copy runs from the server: close it on every PC first.")`), `verb=_("Update and restart"))` → accepted: `updater.install(r)`, button disabled. |
| `progress(n)` | button text `_("Downloading… {n}%", n=n)` |
| `staged(r)` | `arm_install(app_dir, staging_dir(app_dir), app.exe_name, r.version)`, button text `_("Update installs when you close the app")`, then `window.close()`. |
| manual check, not released | toast `_(NOT_RELEASED)`, no thread. |

`failed` messages come from `UpdateError`: the thread emits `_(exc.message, **exc.values)`, so the message is translated on the GUI side. `_()` is pure dict lookup and safe to call from the thread. Any other exception in the thread is logged and emitted as `failed(str(exc))`.

`app_dir` defaults to `Path(sys.executable).parent`, and `frozen` to `getattr(sys, "frozen", False)`.

- [ ] **Step 1: Icons.** Create `shared/assets/icons/scan-barcode.svg` in the same format as `package.svg`:

```xml
<svg
  xmlns="http://www.w3.org/2000/svg"
  width="24"
  height="24"
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="2"
  stroke-linecap="round"
  stroke-linejoin="round"
>
  <path d="M3 7V5a2 2 0 0 1 2-2h2" />
  <path d="M17 3h2a2 2 0 0 1 2 2v2" />
  <path d="M21 17v2a2 2 0 0 1-2 2h-2" />
  <path d="M7 21H5a2 2 0 0 1-2-2v-2" />
  <path d="M8 7v10" />
  <path d="M12 7v10" />
  <path d="M17 7v10" />
</svg>
```

and `shared/assets/icons/download.svg`:

```xml
<svg
  xmlns="http://www.w3.org/2000/svg"
  width="24"
  height="24"
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="2"
  stroke-linecap="round"
  stroke-linejoin="round"
>
  <path d="M12 15V3" />
  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
  <path d="m7 10 5 5 5-5" />
</svg>
```

Add both names to `EXPECTED_ICONS` in `tests/test_ui_assets.py`. Run `tests/test_ui_assets.py tests/test_icons.py tests/test_icon_usage_guard.py`. If the usage guard requires every vendored icon to be used, it passes once Task 7 uses `download` and Task 19 uses `scan-barcode`. In that case add `scan-barcode` to the guard's allowlist with the reason "used by packing-tool's sidebar mark".

- [ ] **Step 2: Failing test** `tests/test_update_flow.py`

```python
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
    f, fake, button, toasts, *_ = flow
    f.start()
    assert fake.checks == [False]
    assert button.isHidden()


def test_start_reports_a_failed_swap_first(flow):
    f, fake, button, toasts, _a, app_dir, _w = flow
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
    f, fake, button, toasts, *_ = flow
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
    f, fake, button, toasts, asked, *_ = flow
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
    f, fake, button, toasts, asked, app_dir, window = flow
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
    f = update_flow.UpdateFlow(window, button, [].append, APP, "2.3.1",
                               app_dir=tmp_path / "x", frozen=False, updater=fake)
    fake.available.emit(R)
    button.click()
    assert asked[0]["verb"] == "Open release page"
    assert opened == ["https://page"]
    assert fake.installs == []


def test_server_copy_warns_in_the_confirm(flow, monkeypatch):
    f, fake, button, toasts, asked, *_ = flow
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
```

- [ ] **Step 3: Run** → FAIL.
- [ ] **Step 4: Implement** `shared/update_flow.py`

```python
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
            except Exception as exc:  # noqa: BLE001 -- a thread must report, not die
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
                   body=shown + " " + _("Download it from the release page instead."),
                   verb=_("Open release page")):
                QDesktopServices.openUrl(QUrl(release.page_url))
            return
        body = _("The app downloads the update, then closes and restarts. What's new: {url}",
                 url=release.page_url)
        if is_server_copy(self._app_dir):
            body += " " + _("This copy runs from the server: close it on every PC first.")
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
```

Add the BG entries for every string in `shared/updater.py` and `shared/update_flow.py` to `shared/assets/locales/bg.json`, using the glossary. Example entries:

```json
"A new version is available": "Има нова версия",
"Can't update this copy": "Това копие не може да се актуализира",
"Could not reach GitHub: {detail}": "Няма връзка с GitHub: {detail}",
"Couldn't check for updates: {message}": "Проверката за актуализации не успя: {message}",
"Download it from the release page instead.": "Изтеглете я от страницата на версията.",
"Downloading… {n}%": "Изтегляне… {n}%",
"No permission to write to {folder}.": "Няма права за запис в {folder}.",
"Open release page": "Отвори страницата на версията",
"The app downloads the update, then closes and restarts. What's new: {url}": "Приложението изтегля актуализацията, затваря се и се стартира отново. Какво ново: {url}",
"The download does not contain {exe}.": "Изтегленият файл не съдържа {exe}.",
"The download is damaged (checksum mismatch).": "Изтегленият файл е повреден (контролната сума не съвпада).",
"This copy runs from the server: close it on every PC first.": "Това копие се стартира от сървъра: първо го затворете на всички компютри.",
"Update and restart": "Актуализирай и рестартирай",
"Update installs when you close the app": "Актуализацията ще се инсталира, когато затворите приложението",
"Update to {version}": "Актуализирай до {version}",
"Update to {version}?": "Актуализиране до {version}?",
"Update to {version} didn't finish: the app folder was in use. Is it open on another PC?": "Актуализацията до {version} не завърши: папката на приложението беше заета. Отворено ли е на друг компютър?",
"Updates install only in the released app.": "Актуализации се инсталират само в издадената версия на приложението.",
"Version {version} is available": "Налична е версия {version}",
"You have the latest version ({version})": "Имате последната версия ({version})"
```

Keep the file sorted (`json.dump(..., sort_keys=True, ensure_ascii=False, indent=2)`).

- [ ] **Step 5: Run** `tests/test_update_flow.py tests/test_updater.py tests/test_ui_assets.py` → pass.
- [ ] **Step 6: Commit**, message `updater: UpdateFlow (button, confirm, progress) and the download/scan-barcode icons`.

---

### Task 7: `shared/components/language_segment.py`

**Files:**
- Create: `shared/components/language_segment.py`
- Modify: `shared/assets/locales/bg.json`. Do **not** export it from `shared/components/__init__.py`: `update_flow` imports `shared.components.confirm_dialog`, and an export there makes a circular import. Import it as `from shared.components.language_segment import …`.
- Test: `tests/test_language_segment.py`

**Interfaces:**
- Consumes: `shared.i18n.LANGUAGES`, `_`; `shared.relaunch.on_quit`, `relaunch_argv`; `ConfirmDialog`; `shared.update_flow.ask` (reuse it).
- Produces:
  - `class LanguageSegment(QFrame)`: object name `LanguageSegment`; one checkable `QToolButton` per `LANGUAGES` code, text = code upper-cased (`EN`, `BG`), tooltip = the language's own name, in an exclusive `QButtonGroup`, fixed height 24 (P passes `height=ITEM_HEIGHT`). Signal `languageRequested(str)`, emitted only for a language other than the checked one. `set_language(code)` checks the button without emitting. Constructor `LanguageSegment(parent=None, *, height: int = 24)`. The buttons are reachable as `segment.buttons: dict[str, QToolButton]`.
  - `switch_language(window: QWidget, settings: QSettings, code: str) -> bool`: saves `settings.setValue("language", code)`, then `ask(window, title=_("Restart to switch language?"), body=_("The new language applies after a restart."), verb=_("Restart now"))`. On accept it calls `on_quit(relaunch_argv())` and `window.close()`, and returns True. Cancel returns False and leaves the choice saved.

- [ ] **Step 1: Failing test** `tests/test_language_segment.py`

```python
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
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** Call `update_flow.ask` through the module (`from shared import update_flow` … `update_flow.ask(...)`) so the test's monkeypatch reaches it.

```python
"""EN | BG: the PC's language, applied on restart (ADR 0021).

Styled by the sidebar that hosts it, like its theme segment: the sidebar's
sheet names #LanguageSegment next to #ThemeSegment.
"""

from __future__ import annotations

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QSizePolicy, QToolButton, QWidget

from shared import update_flow
from shared.i18n import LANGUAGES, _
from shared.relaunch import on_quit, relaunch_argv


class LanguageSegment(QFrame):
    # ponytail: a segment of codes; a dropdown when there are more than three languages.
    languageRequested = Signal(str)

    def __init__(self, parent=None, *, height: int = 24):
        super().__init__(parent)
        self.setObjectName("LanguageSegment")
        self.setFixedHeight(height)
        row = QHBoxLayout(self)
        row.setContentsMargins(2, 2, 2, 2)
        row.setSpacing(2)
        group = QButtonGroup(self)
        group.setExclusive(True)
        self.buttons: dict[str, QToolButton] = {}
        self._current = ""
        for code, name in LANGUAGES.items():
            button = QToolButton(self)
            button.setText(code.upper())
            button.setToolTip(name)
            button.setCheckable(True)
            button.setToolButtonStyle(Qt.ToolButtonTextOnly)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            group.addButton(button)
            row.addWidget(button)
            button.clicked.connect(lambda _c=False, c=code: self._clicked(c))
            self.buttons[code] = button

    def set_language(self, code: str) -> None:
        self._current = code
        if code in self.buttons:
            self.buttons[code].setChecked(True)

    def _clicked(self, code: str) -> None:
        if code != self._current:
            self.languageRequested.emit(code)


def switch_language(window: QWidget, settings: QSettings, code: str) -> bool:
    settings.setValue("language", code)
    if not update_flow.ask(window, title=_("Restart to switch language?"),
                           body=_("The new language applies after a restart."),
                           verb=_("Restart now")):
        return False
    on_quit(relaunch_argv())
    window.close()
    return True
```

The segment keeps showing the saved choice after a cancel. The host calls `segment.set_language(code)` after `switch_language` returns, whatever the result.

BG entries: `"Restart to switch language?": "Рестартиране за смяна на езика?"`, `"The new language applies after a restart.": "Новият език се прилага след рестартиране."`, `"Restart now": "Рестартирай сега"`.

- [ ] **Step 4: Run** → pass.
- [ ] **Step 5: Commit**, message `i18n: EN | BG segment and restart-to-apply`.

---

### Task 8: F wiring: language at startup, sidebar segment, Update button, overflow item, build

**Files:**
- Modify: `gui_main.py` (`main()`, before `MainWindow()`), `gui/components/sidebar.py` (footer around lines 83–110, `set_expanded` 189–200, stylesheet around 243–265), `gui/ui_manager.py` (sidebar wiring near line 202; overflow near 379), `gui/main_window_pyside.py` (create the flow after the window is built), `tests/conftest.py` (clean the `language` key and reset `i18n`), `.github/workflows/build_release.yml` (lines 130–158)
- Create: `locales/bg.json` (`{}` plus the keys this task adds)
- Test: `tests/test_i18n_wiring.py` (new), `tests/test_i18n_catalogue.py` (new)

**Interfaces:**
- Consumes: Tasks 1, 2, 6, 7.
- Produces: `gui_main.APP_ROOT: Path`, `gui_main.apply_saved_language() -> str`, `Sidebar.language_segment: LanguageSegment`, `Sidebar.update_button: QToolButton` (object name `UpdateButton`), `Sidebar.languageRequested = Signal(str)`, `MainWindow.update_flow: UpdateFlow`. Also the catalogue guard test that Tasks 9–17 extend: `tests/test_i18n_catalogue.py` with the module-level list `GUARDED_PY`, `GUARDED_HTML`, `GUARDED_JS` (files the bare-literal guard covers) and `ALLOW` (allowlist).

- [ ] **Step 1: Catalogue guard test** `tests/test_i18n_catalogue.py` (every key in code has a BG entry, no orphans, placeholders match). Later tasks add files to the `GUARDED_*` lists.

```python
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

# Files whose UI text is fully wrapped. Each wrapping task adds its files; Task 17
# replaces the lists with every file (SHARED_PY + APP_PY, APP_HTML, APP_JS).
GUARDED_PY: list[Path] = [ROOT / "shared" / "components" / "language_segment.py",
                          ROOT / "shared" / "update_flow.py"]
GUARDED_HTML: list[Path] = []
GUARDED_JS: list[Path] = []
# Text that is never translated, with the reason.
ALLOW = {
    "Fulfilment Tool",   # brand
    "Packer Assistant",  # brand
    "Shopify",           # brand
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
```

Plural-key placeholders: for `_n("{n} order", "{n} orders", n)` the key is `"{n} order"`, and both BG forms must carry `{n}`. Correct as written.

Run it now. It fails until `locales/bg.json` exists and is formatted, and `shared/assets/locales/bg.json` must already pass from Tasks 1, 6 and 7. Create `locales/bg.json` as `{}\n`. Then re-format the shared file if needed with:
`.venv/bin/python -c "import json,pathlib;p=pathlib.Path('shared/assets/locales/bg.json');p.write_text(json.dumps(json.loads(p.read_text(encoding='utf-8')),ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')"`

- [ ] **Step 2: conftest.** In `tests/conftest.py`, add `"language"` to the keys removed by `clean_nav_setting` (line ~328). Add an autouse fixture:

```python
@pytest.fixture(autouse=True)
def english_ui():
    """shared.i18n is process-global: a test that switched to BG must not leak it."""
    from shared import i18n, relaunch
    yield
    i18n.set_language("en", [])
    relaunch._reset()
```

- [ ] **Step 3: Failing wiring test** `tests/test_i18n_wiring.py`

```python
from PySide6.QtCore import QSettings

import gui_main
from shared import i18n


def test_saved_language_is_applied_before_the_window(monkeypatch):
    QSettings("ShopifyFulfillmentTool", "FulfillmentApp").setValue("language", "bg")
    assert gui_main.apply_saved_language() == "bg"
    assert i18n.language() == "bg"
    assert i18n._("Restart now") == "Рестартирай сега"


def test_default_is_english():
    QSettings("ShopifyFulfillmentTool", "FulfillmentApp").remove("language")
    assert gui_main.apply_saved_language() == "en"


def test_sidebar_has_language_segment_and_hidden_update_button(qtbot):
    from gui.components.sidebar import Sidebar
    bar = Sidebar()
    qtbot.addWidget(bar)
    bar.show()
    assert bar.language_segment.buttons["en"].isChecked()
    assert bar.update_button.objectName() == "UpdateButton"
    assert bar.update_button.isHidden()
    bar.set_expanded(False)
    assert bar.language_segment.isHidden()


def test_sidebar_language_click_is_forwarded(qtbot):
    from gui.components.sidebar import Sidebar
    bar = Sidebar()
    qtbot.addWidget(bar)
    with qtbot.waitSignal(bar.languageRequested) as blocker:
        bar.language_segment.buttons["bg"].click()
    assert blocker.args == ["bg"]
```

Add one more test in the same file that builds the main window the way `tests/test_main_window*.py` or `tests/test_gui_main_env_setup.py` already does. Assert that `window.update_flow` exists, and that the overflow menu has an item `Check for updates…`. Copy the construction from the nearest existing main-window test; do not invent one.

- [ ] **Step 4: Implement.**

`gui_main.py`:

```python
from PySide6.QtCore import QSettings
from shared import i18n

APP_ROOT = Path(__file__).resolve().parent


def apply_saved_language() -> str:
    code = str(QSettings("ShopifyFulfillmentTool", "FulfillmentApp").value("language", i18n.DEFAULT_LANGUAGE))
    i18n.set_language(code, i18n.catalogue_files(APP_ROOT, code))
    return i18n.language()
```

In `main()`, call `apply_saved_language()` right after `QApplication(sys.argv)` and before the theme and `MainWindow()`. (`Path` may need importing.)

`gui/components/sidebar.py`:
- Add the signal `languageRequested = Signal(str)`.
- In the footer, right after `footer.addWidget(self.theme_segment)`:
  ```python
  self.language_segment = LanguageSegment(self.footer)
  self.language_segment.set_language(i18n.language())
  self.language_segment.languageRequested.connect(self.languageRequested.emit)
  footer.addWidget(self.language_segment)
  ```
- Before `self.settings_button` (the top of the footer):
  ```python
  self.update_button = QToolButton(self.footer)
  self.update_button.setObjectName("UpdateButton")
  self.update_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
  self.update_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
  self.update_button.hide()
  footer.addWidget(self.update_button)
  ```
- `set_expanded`: add `self.language_segment` to the tuple hidden when collapsed. Set `update_button`'s style to icon-only when collapsed, the same way `settings_button` is handled.
- Stylesheet: change each `#ThemeSegment` selector to `#ThemeSegment, #LanguageSegment` (and `#ThemeSegment QToolButton…` to `#ThemeSegment QToolButton…, #LanguageSegment QToolButton…`). Add:
  `f"#UpdateButton {{ background-color: {t.accent_fill}; color: {t.on_accent}; border: none; border-radius: 6px; padding: 4px 8px; {font_css('caption', bold=True)} }}"`
  `f"#UpdateButton:hover {{ background-color: {t.accent_fill_hover}; }}"`
  `f"#UpdateButton:disabled {{ background-color: {t.accent_fill_active}; color: {t.on_accent}; }}"`
  Check that `accent_fill_active` exists in `shared/theme.py` ThemeTokens (line ~101). If it doesn't, use `accent_fill`.
- In the restyle method (where `self.mark.setPixmap` etc. are set), set `self.update_button.setIcon(icon("download", color=t.on_accent))`. `UpdateFlow` keeps an icon that is already set.

`gui/ui_manager.py`:
- Next to `sidebar.themeRequested.connect(switch_theme)` (line ~202):
  ```python
  settings = QSettings("ShopifyFulfillmentTool", "FulfillmentApp")
  def on_language(code):
      switch_language(self.mw, settings, code)
      sidebar.language_segment.set_language(str(settings.value("language", "en")))
  sidebar.languageRequested.connect(on_language)
  ```
  The segment shows the saved choice, while the window stays in the old language until the restart.
- In the overflow menu's "THIS PC" section, after "Server connection…": `menu.add_item(_("Check for updates…"), lambda: self.mw.update_flow.check_now())`.

`gui/main_window_pyside.py`: after the UI is built (after `ui_manager` creates the sidebar), add:

```python
self.update_flow = UpdateFlow(
    self, self.sidebar.update_button, lambda text: toast(self, text),
    AppIdentity("cognitiveghost/shopify-fulfillment-tool", "FulfilmentTool", "FulfilmentTool.exe"),
    __version__,
)
self.update_flow.start()
```

Find the attribute that holds the sidebar (`grep -n "Sidebar(" gui/*.py`) and the existing `toast` import (`gui/components/__init__.py:21`). `start()` with `__version__ == "dev"` and not frozen does nothing, so tests make no network call.

Wrap the new strings this task adds in `gui/` (`"Check for updates…"`) with `_()`. Add BG to `locales/bg.json`: `"Check for updates…": "Провери за актуализации…"`.

`.github/workflows/build_release.yml`: in the pyinstaller command, add `--add-data "locales;locales"` after `--add-data "shared/web;shared/web"`. In "Verify bundled assets shipped", add `"bg.json", "scan-barcode.svg", "download.svg"` to the `foreach` list.

- [ ] **Step 5: Run** `tests/test_i18n_wiring.py tests/test_i18n_catalogue.py` and the sidebar/commandbar/ui tests (`ls tests | grep -E "sidebar|commandbar|ui_manager|main_window"`) → pass.
- [ ] **Step 6: Commit**, message `F: language at startup, EN | BG segment, Update button, Check for updates`.

---

### Task 9: Wrap `shared/` UI text

**Files:**
- Modify: every `shared/**/*.py` with on-screen text. Find them with
  `.venv/bin/python -c "from pathlib import Path; from shared import i18n_check as c; print('\n'.join(c.bare_python_literals([p for p in c.files(Path('shared'),'*.py') if p.name!='i18n_check.py'], set())))"`.
  Expect `shared/server_connection.py` (about 15), `shared/components/toast.py`, `confirm_dialog.py`, `state_panel.py`, `filterbar.py`, `overflow.py`, `card.py`, `shared/navrail.py`. Also check `shared/web/page.js`: does it hold any user text? Wrap any with `t()`.
- Modify: `shared/assets/locales/bg.json`, `tests/test_i18n_catalogue.py` (`GUARDED_PY += SHARED_PY`)

Procedure:
1. Run the command above and keep the list.
2. For each hit, apply rules 1–5. A text argument becomes `_("…")`. A module-level constant becomes `N_("…")` and is wrapped at display with `_(CONST)`. An f-string becomes `_("… {name} …", name=value)`. A string that is not UI (an object name, a key) is a false positive: add it to `ALLOW` with a `# reason` comment only if it really is text that must not change. Prefer restructuring so the scanner doesn't see it.
3. `ConfirmDialog._VERBS_THAT_NAME_NO_ACT` compares the English verb: leave it. A translated verb never matches, which is fine.
4. Add each new key with its BG text (glossary) to `shared/assets/locales/bg.json`, then re-sort (the one-liner in Task 8 Step 1).
5. In `tests/test_i18n_catalogue.py` set `GUARDED_PY = SHARED_PY + [...]`, keeping the existing entries.

- [ ] **Step 1:** List the hits (above).
- [ ] **Step 2:** Wrap them and add the BG entries.
- [ ] **Step 3: Test.** `tests/test_i18n_catalogue.py` passes. Run every test that names a touched module (`ls tests | grep -E "toast|confirm|state_panel|filterbar|overflow|card|navrail|server_connection"`): English output is unchanged, so they must pass untouched. A test that compares text it built at import time may need nothing; if one fails, the string was wrapped at import time (rule 2). Fix the code, not the test.
- [ ] **Step 4: Commit**, message `i18n: shared/ widgets and dialogs go through _()`.

---

### Tasks 10–12: Wrap F's Qt widget text

One procedure, three file groups. Each is its own task and commit, and each adds its files to `GUARDED_PY`.

**Procedure for each group** (same as Task 9, for `gui/` files, with `locales/bg.json`):
1. `.venv/bin/python -c "from pathlib import Path; from shared import i18n_check as c; print('\n'.join(c.bare_python_literals([Path(p) for p in '''<files>'''.split()], set())))"`
2. Also read each file for text the scanner cannot see. It sees literals passed directly to the calls it knows. It does not see text kept in a dict or list and passed later, `QMessageBox.question(self, "Title", "Body")` positional args beyond the first, `QInputDialog` labels, table headers (`setHorizontalHeaderLabels([...])`), or tab titles (`addTab(w, "Name")`). Wrap those too. Search each file for `"[A-Z][a-z]` to catch them.
3. Identity vs display: `SETTINGS_SEARCH_KEYWORDS` and `WEB_PAGE_KEYS` in `gui/settings/window.py` are keyed by English page names. Keep the keys English and wrap the name where the nav row is drawn: `_(name)` with each page name declared as `N_("Profile")` etc. at its definition. Settings search must match the translated name and the English keywords: search over `_(name)` plus the keyword list.
4. Dates: replace `strftime` `%b` with `i18n.month_abbr(dt.month)`.
5. Add BG entries, keep `locales/bg.json` sorted, and add the group's files to `GUARDED_PY`.
6. Run `tests/test_i18n_catalogue.py` and the tests of every touched module → pass.

**Task 10 files:** `gui/settings/window.py`, `gui/client_settings_dialog.py`, `gui/groups_management_dialog.py`, `gui/client_directory.py`, and any other file under `gui/settings/` with hits.
Commit: `i18n: F settings window and client dialogs`.

**Task 11 files:** `gui/report_selection_dialog.py`, `gui/add_product_dialog.py`, `gui/shortcuts_dialog.py`, `gui/barcode_tool.py`, `gui/reference_tool.py`, `gui/session_browser_widget.py`, `gui/pdf_printing.py`, `gui/file_handler.py`.
Commit: `i18n: F dialogs and tools`.

**Task 12 files:** every remaining `gui/*.py` and `gui/components/*.py` with hits, including `gui/components/sidebar.py`, `gui/components/commandbar.py`, `gui/ui_manager.py`, `gui/main_window_pyside.py`, `gui/actions_handler.py` (toast and dialog text only; the session/analysis logic is untouched), `gui/tools_widget.py`, `gui/logs_widget.py`, `gui/orders_view.py`, `gui/pandas_model.py` (only if it shows fixed header text; column names that come from data are not wrapped). After this task `GUARDED_PY` = `SHARED_PY + APP_PY`.
Commit: `i18n: F shell, command bar and remaining widgets`.

Review Focus 2 test (put it in Task 10): in `tests/test_i18n_wiring.py` add a test that sets `i18n.set_language("bg", i18n.catalogue_files(gui_main.APP_ROOT, "bg"))`, builds the `SettingsWindow` the way its existing tests do, and opens the "Rules" page by clicking its nav row. Assert the page shown is the rules page (by its `WEB_PAGE_KEYS` key, `"rules"`), i.e. navigation still works when the visible names are Bulgarian.

---

### Tasks 13–15: Wrap F's web pages

**Procedure for each page group:**
1. HTML: put `data-i18n` on every element whose content is plain UI text. Split mixed markup (`<p>Drop a file or <b>browse</b></p>`) into spans, each with `data-i18n`. Put `data-i18n-attr="placeholder,title,aria-label"` (only the attributes present) on elements with such attributes. Leave `<title>` alone.
2. JS: wrap every UI string with `t("…")`, `t("… {x} …", {x: v})` or `tn("{n} order", "{n} orders", n)`. Find them with `rg -n "\"[A-Z][a-z]|'[A-Z][a-z]|\`[A-Z]" gui/web/<page>*.js` and also check template literals (`` `…${x}…` `` that make visible text become `t("…{x}…", {x})`). Leave CSS classes, ids, keys, event names, `data-*` values and values sent back to Python alone. Strings matched in logic stay English: translate where they are drawn.
3. Python that builds page text (bridges, `*_state.py`): wrap with `_()` at the point the text is put into the bridge's payload.
4. Add BG entries to `locales/bg.json` (sorted). Add the HTML to `GUARDED_HTML`, the JS to `GUARDED_JS` and the Python to `GUARDED_PY`.
5. Run `tests/test_i18n_catalogue.py` and the page's tests (`ls tests | grep <page>`) → pass. Then render the page once in BG to check that nothing outside the catalogue is still English. In the page's existing test file, add one test that calls `i18n.set_language("bg", i18n.catalogue_files(gui_main.APP_ROOT, "bg"))` before mounting the page, and asserts one known element's text is Bulgarian.

**Task 13:** `gui/web/setup.html`, `setup.js`, `tools.html`, `tools.js`, `logs.html`, `logs.js`; Python: `gui/setup_bridge.py`, `gui/setup_state.py` (`"%d %b %H:%M"` → `month_abbr`), `gui/tools_bridge.py`, `gui/tools_state.py` (`tools_state.py:232-237` "N of M labels matched" → `_n`/`_` with placeholders), `gui/logs_bridge.py`, `gui/log_entry.py` (display text only; log records stay English).
Commit: `i18n: F setup, tools and logs pages`.

**Task 14:** `gui/web/browse.html`, `browse.js`, `results.html`, `results.js`, `columns.js`, `bulk.js`, `pane.js`; Python: `gui/browse_bridge.py`, `gui/browse_state.py`, `gui/results_bridge.py`. Column headers that are Shopify/CSV field names from data are not translated. Fixed headers the app defines are.
Commit: `i18n: F browse and results pages`.

**Task 15:** `gui/web/settings.html`, `settings.js`, `settings_profile.js`, `settings_reports.js`, `settings_rules.js`, `settings_sets.js`, `settings_tags.js`, `settings_weight.js`; Python: `gui/settings/bridge.py` and any `gui/settings/*.py` that pushes text. Rule condition/action names that are saved to client config stay English as values: translate the label shown in the dropdown, not the stored value. `SAVED_LINE` in `gui/settings/window.py` becomes `N_()` and is shown as `_(SAVED_LINE)`.
Commit: `i18n: F settings pages`.

---

### Task 16: F guard on everything

**Files:** `tests/test_i18n_catalogue.py`.

- [ ] Set `GUARDED_PY = SHARED_PY + APP_PY`, `GUARDED_HTML = APP_HTML`, `GUARDED_JS = APP_JS`. Run it. Each hit is either wrapped now (with its BG entry) or added to `ALLOW` with a reason.
- [ ] Run the full F gate in the background and ruff. Pre-existing failures to ignore: 3 `TestImageToZpl` tests in `tests/test_label_printing.py`. Record any other failure: run it on `origin/main` too before calling it pre-existing.
- [ ] Commit: `i18n: F bare-literal guard covers every file`.

### Task 17: F renders in Bulgarian and fixes

**Files:**
- Create: `scripts/render_i18n.py`, `docs/design/i18n-renders/fulfilment/*.png`
- Modify: whatever widget or CSS clips Bulgarian text

- [ ] Write `scripts/render_i18n.py`. Argparse `--lang` (default `bg`), `--theme` (`light|dark`), `--out` (default `docs/design/i18n-renders/fulfilment`). Steps:
  - set `QT_QPA_PLATFORM=offscreen`;
  - redirect QSettings with `QSettings.setPath(QSettings.NativeFormat, QSettings.UserScope, tmp)` and the same for `IniFormat`, plus `FULFILLMENT_SERVER_PATH` to a temp dir, **before** any app import touches QSettings;
  - `i18n.set_language(args.lang, i18n.catalogue_files(ROOT, args.lang))`;
  - build `MainWindow` the way `tests/test_gui_main_env_setup.py` does and `resize(1366, 768)`;
  - for each sidebar destination (iterate the nav rail's items), select it, wait for its page to paint (`shared.web_page.when_painted` on the page's bridge, or process events for 1.5 s), and save `window.grab().save(out/f"{i:02d}-{name}-{theme}.png")`;
  - also open the Settings window and grab it once per settings page.
  Pages with no session show their empty state, which covers the shell, setup, tools, logs and settings. The Results and Browse pages are also rendered with data: mount each standalone in a 1366×768 `QWebEngineView` with the sample payload its tests use (`tests/test_results_bridge.py`, `tests/test_browse_page.py` fixtures; import their helpers) and grab the view.
- [ ] Run it for `--theme light` and `--theme dark`. Look at every PNG (Read tool). For each clipped, overlapping or elided-to-nothing label: let it wrap (`setWordWrap(True)`, CSS `white-space: normal`) or elide with a tooltip. Never shrink fonts, and never change the English layout's sizes unless the English still fits.
- [ ] Re-render, re-check, and commit the PNGs, the script and the fixes: `i18n: Bulgarian renders of Fulfilment and layout fixes`.
- [ ] Push F: `/usr/bin/git push origin dr/34-shared-packer-tool-app-shell-en-bg-local`. Part 2 syncs from this pushed head.

---

## Part 2 — Packer (P)

### Task 18: Sync `shared/`, catalogue scaffolding, language at startup, build

**Files:**
- Modify: `shared/` (by the sync script only), `scripts/shared_synced_from.txt`, `main.py`, `main.spec`, `.github/workflows/build-release.yml`, `tests/conftest.py`, `gui/web/app.js:923`, `gui/web/packer.js:345`, `gui/web/setup.js:679`
- Create: `locales/bg.json`, `tests/test_i18n_catalogue.py`, `tests/test_i18n_wiring.py`

- [ ] **Step 1: Sync.** Check that F's branch is pushed (`/usr/bin/git -C /home/gloopy/Desktop/Projects/shopify-fulfillment-tool/.claude/worktrees/dr-34 status -sb` shows no "ahead"). Then from P:
  `.venv/bin/python scripts/sync_shared.py /home/gloopy/Desktop/Projects/shopify-fulfillment-tool/.claude/worktrees/dr-34`.
  If it refuses because the source HEAD does not contain the pinned commit (P's pin can be a squash-merged SHA, see the project notes), re-run with `--force`. Confirm `scripts/shared_synced_from.txt` now holds F's branch head SHA. Run P's full suite once. A `shared/` change can break P (renamed tokens, new required args). Fix P's code, never `shared/`.
  Commit the sync alone: `shared: sync from Fulfilment dr/34 (i18n, updater, relaunch)`.
- [ ] **Step 2: Catalogue test.** Create `tests/test_i18n_catalogue.py` as in F's Task 8 Step 1, with these differences:
  - `SHARED_BG = ROOT / "shared" / "assets" / "locales" / "bg.json"` is only merged for lookups. P has no shared-scope tests: drop the `_shared_keys` parametrisations and keep `(_app_keys, APP_BG)` only.
  - `APP_PY = c.files(ROOT / "gui", "*.py") + [ROOT / "main.py"]`, with `APP_HTML`/`APP_JS` from `gui/web`.
  - `GUARDED_PY = []`, `GUARDED_HTML = []`, `GUARDED_JS = []` to start; `ALLOW` the same.
  Create `locales/bg.json` as `{}\n`.
- [ ] **Step 3: conftest.** Add the same `english_ui` autouse fixture as F (Task 8 Step 2). P's conftest already redirects QSettings to a temp dir (lines ~94–106).
- [ ] **Step 4: Wiring test** `tests/test_i18n_wiring.py`:

```python
from PySide6.QtCore import QSettings

import main
from shared import i18n


def test_saved_language_is_applied():
    QSettings("PackingTool", "Language").setValue("language", "bg")
    assert main.apply_saved_language() == "bg"
    assert i18n._("Restart now") == "Рестартирай сега"


def test_default_is_english():
    QSettings("PackingTool", "Language").remove("language")
    assert main.apply_saved_language() == "en"
```

  `main.py` runs its app only under `if __name__ == "__main__":`, so importing it is safe.
- [ ] **Step 5: Implement.** In `main.py`, at module level:

```python
from pathlib import Path

from PySide6.QtCore import QSettings

from shared import i18n

APP_ROOT = Path(__file__).resolve().parent


def apply_saved_language() -> str:
    code = str(QSettings("PackingTool", "Language").value("language", i18n.DEFAULT_LANGUAGE))
    i18n.set_language(code, i18n.catalogue_files(APP_ROOT, code))
    return i18n.language()
```

  Then call `apply_saved_language()` right after `app = QApplication(sys.argv)`.
  In each of `gui/web/app.js`, `packer.js` and `setup.js`, add `applyStrings(bridge);` first in the QWebChannel callback, as in F's Task 3.
  `main.spec`: add `('locales', 'locales'),` to `datas`. `.github/workflows/build-release.yml`: add `"bg.json", "scan-barcode.svg", "download.svg"` to the bundle verify list (near line 169; read the step and match its form).
- [ ] **Step 6: Run** the two new test files and the three page test files (`ls tests | grep -E "app_page|packer|setup"`) → pass.
- [ ] **Step 7: Commit**, message `P: language at startup, catalogue guard, pages apply strings`.

### Task 19: P sidebar: mark, language segment, Update button, overflow item

**Files:** `gui/components/sidebar.py` (mark at line 377; footer 131–238; `_segment_button` 249; stylesheet ~343–376; collapse handling), `gui/main_window.py` (sidebar wiring ~393, overflow ~502, `_toast` 589, window construction), `locales/bg.json`, `tests/test_i18n_wiring.py`.

- [ ] **Step 1: Failing tests** (append to `tests/test_i18n_wiring.py`). Build the sidebar and the main window the way P's existing tests do (`ls tests | grep -E "sidebar|main_window"`; copy their construction).
  - Sidebar mark: `Sidebar._restyle` (or wherever line 377 lives) renders `icon("scan-barcode", color=t.on_accent)`. Test: patch `gui.components.sidebar.icon` with a recorder, trigger the restyle the way the existing sidebar test does, and assert `"scan-barcode"` was requested and `"package"` was not.
  - `bar.language_segment.buttons["en"].isChecked()`. Click BG → `bar.languageRequested` emits `"bg"`.
  - `bar.update_button.objectName() == "UpdateButton"` and hidden.
  - In collapsed mode `language_segment` hides, like `theme_segment`.
  - Main window: `window.update_flow` exists, and the overflow menu contains `Check for updates…`.
- [ ] **Step 2: Implement**, mirroring F's Task 8 Step 4:
  - mark: `icon("package", color=t.on_accent)` → `icon("scan-barcode", color=t.on_accent)`;
  - `LanguageSegment(self.footer, height=ITEM_HEIGHT)` after the theme segment; `languageRequested` signal forwarded;
  - `update_button` at the top of the footer (above `sku_button`), with the same `#UpdateButton` style rules and the `#LanguageSegment` selector alongside every `#ThemeSegment` selector; `download` icon tinted `on_accent` in the restyle;
  - `MainWindow`: `sidebar.languageRequested` → `switch_language(self, QSettings("PackingTool", "Language"), code)` then `sidebar.language_segment.set_language(saved)`;
  - overflow: `menu.add_item(_("Check for updates…"), lambda: self.update_flow.check_now())` after "Server connection…";
  - `self.update_flow = UpdateFlow(self, self.sidebar.update_button, self._toast, AppIdentity("cognitiveghost/packing-tool", "PackerAssistant", "PackerAssistant.exe"), __version__)` from `packing_tool`, then `self.update_flow.start()` after the window is built. `self._toast` takes `(message, role="success")`, so passing it as a one-argument callable works.
  - BG: `"Check for updates…": "Провери за актуализации…"` in `locales/bg.json`.
- [ ] **Step 3: Run** the sidebar, main window and i18n tests → pass.
- [ ] **Step 4: Commit**, message `P: Packer Assistant mark, EN | BG segment, Update button`.

### Task 20: Wrap P's Qt widget text

Same procedure as F's Tasks 10–12, against `locales/bg.json`, adding files to `GUARDED_PY`. Files: `gui/components/sidebar.py`, `gui/command_bar.py`, `gui/packer_mode_widget.py`, `gui/main_window.py` (dialogs at `:739`, `:974-978`, `:1605-1609` frame `str(e)` per rule 4), and every other `gui/*.py` the scanner reports. `packing_tool/` is not wrapped.
Commit: `i18n: P shell and widgets`.

### Task 21: Wrap P's app document (Packing, Statistics, Sessions, Session details)

Same procedure as F's Tasks 13–15. Files: `gui/web/app.html`, `gui/web/app.js`, `gui/app_bridge.py` (`:41-42`), `gui/sessions_payload.py` (about 47 sentences), `gui/sessions_page.py`, and any `gui/*_payload.py` the app document uses. Statuses stored in session files (`completed`, `incomplete`, `paused`) stay English as values; their labels are translated.
Commit: `i18n: P app document pages`.

### Task 22: Wrap P's Packer Mode and setup document

Same procedure. Files: `gui/web/packer.html`, `packer.js`, `gui/packer_bridge.py`, `gui/web/setup.html`, `setup.js`, `gui/setup_payload.py` (`:63` "Last active " + day → one sentence per case: `_("Last active today")`, `_("Last active yesterday")`, `_("Last active {date}", date=…)`; the same for any other concatenation).

`gui/packer_bridge.py:149-151` matches note text `"Repeat"` / `"Cannot fulfill"` to drive logic. Keep that comparison on the raw English value. Translate only where the note is displayed. Review Focus 2 test (add to `tests/test_i18n_wiring.py` or the packer bridge test file): with `i18n.set_language("bg", i18n.catalogue_files(main.APP_ROOT, "bg"))` active, run the existing scenario that exercises the Repeat / Cannot-fulfill branch (copy it from the packer bridge tests) and assert the same outcome as in English.
Commit: `i18n: P Packer Mode and setup pages`.

### Task 23: P guard on everything, renders, gate, push

- [ ] Set `GUARDED_PY = APP_PY`, `GUARDED_HTML = APP_HTML`, `GUARDED_JS = APP_JS`, and fix every hit.
- [ ] Add `--lang` to P's render scripts. Each `scripts/render_*.py` parses args through `scripts/render_args.py`: add `--lang` (default `en`) there, and call `i18n.set_language(args.lang, i18n.catalogue_files(ROOT, args.lang))` where each script sets up the app, before it builds windows. Render every screen in `bg`, light and dark, into `docs/design/i18n-renders/packer/`. Look at every PNG and fix clipping as in Task 17.
- [ ] Gate P: the full suite and `ruff check . --exclude shared`. `scripts/coverage_check.py` gates (app 85%, each page script 80%) assume the full suite.
- [ ] Commit `i18n: P guard covers every file; Bulgarian renders`, then push P: `/usr/bin/git push -u origin dr/34-shared-packer-tool-app-shell-en-bg-local`.

## After the PRs (Stage C, not Stage B)

- F's PR body states: Packer needs the shared sync. List the Windows checks (spec section 8): update round trip on a local folder, a server copy open on a second PC, HTTPS from the frozen build, language restart in the frozen build. Ask the owner to review the Bulgarian (`locales/bg.json`, `shared/assets/locales/bg.json`, and the renders).
- P's PR is a draft until F's merges. Then: fresh clone of GitHub `main` → `scripts/sync_shared.py <clone> --force` → commit → mark ready.
