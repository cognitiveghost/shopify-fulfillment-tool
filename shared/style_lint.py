"""Fails the build on a colour literal, a pixel font size, or a read of a
frozen appearance alias in widget code.

An ast walk, not a grep. Every false positive found while measuring the
2026-08-27 baseline lived in a comment or a docstring -- `commit #216`,
`"#1001" -> "1001"`, `(e.g. "#c0392b" or "red")` -- and ast drops both for
free. A line-based regex would need a per-line suppression on each of them,
which rots the first time someone writes a new comment.

Scope note: shared/theme.py is never scanned. It is the one file where a
colour literal belongs.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from typing import Iterable

ALLOW_MARKER = "style-lint: allow"

# A 6- or 3-digit hex, refusing to match the front of a longer digit run so
# order numbers ("#1001") and PR references stay clean.
_HEX = re.compile(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})(?![0-9a-fA-F])")

# CSS colour keywords, matched only after a colour-bearing property name, so
# prose ("Status: green means shipped") is not a hit. `transparent` and
# `currentColor` are absent on purpose: neither pins a palette value.
_COLOR_NAMES = (
    "white|black|red|green|blue|gray|grey|yellow|orange|darkgreen|darkred|"
    "lightgray|lightgrey|silver|purple|cyan|magenta|brown|pink|navy|teal|"
    "lime|maroon|olive|aqua|fuchsia|darkblue|lightblue"
)
_CSS_NAME = re.compile(
    r"\b(?:color|background|background-color|border|border-\w+|outline|outline-\w+"
    r"|fill|stroke|selection-color|selection-background-color|gridline-color"
    r"|alternate-background-color)\s*:[^;]*?\b(" + _COLOR_NAMES + r")\b"
)

_PX_FONT = re.compile(r"font-size\s*:\s*[\d.]+\s*px")

# shared/theme.py::_ALIAS_PAIRS, left column. Read-only for existing code
# until this task; zero reads afterwards.
FROZEN_ALIASES = frozenset({
    "background", "background_elevated",
    "accent_blue", "accent_green", "accent_orange", "accent_red",
    "active_background", "active_border",
    "button_hover_light", "button_hover_dark",
})


def _docstring_node_ids(tree: ast.AST) -> set[int]:
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                ids.add(id(body[0].value))
    return ids


def _scan_file(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    tree = ast.parse(source, filename=str(path))
    docstrings = _docstring_node_ids(tree)
    # A call target -- widget.palette().background() -- is not a token read.
    call_targets = {id(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}

    found: list[tuple[int, str, str]] = []
    for node in ast.walk(tree):
        lineno = getattr(node, "lineno", None)
        if lineno is None or ALLOW_MARKER in lines[lineno - 1]:
            continue
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and id(node) not in docstrings):
            for m in _HEX.finditer(node.value):
                found.append((node.lineno, "hex", m.group()))
            for m in _CSS_NAME.finditer(node.value):
                found.append((node.lineno, "css-name", m.group(1)))
            for m in _PX_FONT.finditer(node.value):
                found.append((node.lineno, "px-font", m.group()))
        elif (isinstance(node, ast.Attribute) and node.attr in FROZEN_ALIASES
                and id(node) not in call_targets):
            found.append((node.lineno, "alias", node.attr))

    return [f"{path}:{ln}: {kind}: {text}" for ln, kind, text in sorted(found)]


def find_style_literals(paths: Iterable[Path]) -> list[str]:
    """Every offending site under `paths`, sorted, one string per finding.

    A path may be a file or a directory; directories are walked recursively
    so a package added later cannot escape the guard silently.
    """
    files: list[Path] = []
    for p in (Path(x) for x in paths):
        files.extend(sorted(p.rglob("*.py")) if p.is_dir() else [p])
    out: list[str] = []
    for f in sorted(set(files)):
        out.extend(_scan_file(f))
    return out


if __name__ == "__main__":
    findings = find_style_literals(sys.argv[1:] or ["."])
    for line in findings:
        print(line)
    print(f"{len(findings)} finding(s)")
    sys.exit(1 if findings else 0)
