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
    _SKIP = frozenset({"script", "style", "title"})

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
