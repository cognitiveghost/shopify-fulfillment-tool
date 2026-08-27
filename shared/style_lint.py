"""Fails the build on a colour literal, a pixel font size, or a read of a
frozen appearance alias in widget code.

An ast walk, not a grep. Every false positive found while measuring the
2026-08-27 baseline lived in a comment or a docstring -- `commit #216`,
`"#1001" -> "1001"`, `(e.g. "#c0392b" or "red")` -- and ast drops both for
free. A line-based regex would need a per-line suppression on each of them,
which rots the first time someone writes a new comment.

Scope note: shared/theme.py is never scanned. It is the one file where a
colour literal belongs.

What this does NOT see (measured 2026-08-27, deliberately out of scope for
8.3 -- these are colours passed as *values*, not written into a stylesheet
string, and converting the ~22 remaining sites is its own roadmap item):

  * a bare colour name or hex handed to a constructor -- `QColor("red")`,
    `QBrush("#fff")`, `QPen(...)`;
  * a numeric channel triple -- `QColor(150, 150, 150)`, `QColor(0xFF, 0, 0)`;
  * a Qt colour enum -- `Qt.gray`, `Qt.GlobalColor.darkGreen`;
  * a colour passed as a widget kwarg -- `foreground="white"`;
  * a declaration assembled at runtime rather than written as one literal --
    `"color: " + name`, `"color: %s" % name`, `str.join`, or an f-string whose
    colour is split across fragments;
  * a `.qss` file (neither repo ships one).

Two false positives are latent rather than fixed: a colour name inside an
image path (`background: url(:/icons/red.png)`) and an attribute named after
a frozen alias on a non-theme object (`self.background`). Neither occurs in
either repo today; `# style-lint: allow` handles them if one appears.
"""
from __future__ import annotations

import ast
import re
import sys
from collections.abc import Iterable
from pathlib import Path

ALLOW_MARKER = "style-lint: allow"

# A 6- or 3-digit hex, refusing to match the front of a longer digit run so
# order numbers ("#1001") and PR references stay clean.
_HEX = re.compile(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})(?![0-9a-fA-F])")

# The full CSS named-colour set, matched only after a colour-bearing property
# name, so prose ("Status: green means shipped") is not a hit. `transparent`
# and `currentColor` are absent on purpose: neither pins a palette value.
# The list is static data -- being short here only buys false negatives.
_COLOR_NAMES = (
    "aliceblue|antiquewhite|aqua|aquamarine|azure|beige|bisque|black|"
    "blanchedalmond|blue|blueviolet|brown|burlywood|cadetblue|chartreuse|"
    "chocolate|coral|cornflowerblue|cornsilk|crimson|cyan|darkblue|"
    "darkcyan|darkgoldenrod|darkgray|darkgreen|darkgrey|darkkhaki|"
    "darkmagenta|darkolivegreen|darkorange|darkorchid|darkred|darksalmon|"
    "darkseagreen|darkslateblue|darkslategray|darkslategrey|"
    "darkturquoise|darkviolet|deeppink|deepskyblue|dimgray|dimgrey|"
    "dodgerblue|firebrick|floralwhite|forestgreen|fuchsia|gainsboro|"
    "ghostwhite|gold|goldenrod|gray|green|greenyellow|grey|honeydew|"
    "hotpink|indianred|indigo|ivory|khaki|lavender|lavenderblush|"
    "lawngreen|lemonchiffon|lightblue|lightcoral|lightcyan|"
    "lightgoldenrodyellow|lightgray|lightgreen|lightgrey|lightpink|"
    "lightsalmon|lightseagreen|lightskyblue|lightslategray|"
    "lightslategrey|lightsteelblue|lightyellow|lime|limegreen|linen|"
    "magenta|maroon|mediumaquamarine|mediumblue|mediumorchid|"
    "mediumpurple|mediumseagreen|mediumslateblue|mediumspringgreen|"
    "mediumturquoise|mediumvioletred|midnightblue|mintcream|mistyrose|"
    "moccasin|navajowhite|navy|oldlace|olive|olivedrab|orange|orangered|"
    "orchid|palegoldenrod|palegreen|paleturquoise|palevioletred|"
    "papayawhip|peachpuff|peru|pink|plum|powderblue|purple|rebeccapurple|"
    "red|rosybrown|royalblue|saddlebrown|salmon|sandybrown|seagreen|"
    "seashell|sienna|silver|skyblue|slateblue|slategray|slategrey|snow|"
    "springgreen|steelblue|tan|teal|thistle|tomato|turquoise|violet|"
    "wheat|white|whitesmoke|yellow|yellowgreen"
)
_COLOR_PROPERTY = (
    r"\b(?:color|background|background-color|border|border-\w+|outline"
    r"|outline-\w+|fill|stroke|selection-color|selection-background-color"
    r"|gridline-color|alternate-background-color)\s*:"
)
_CSS_NAME = re.compile(_COLOR_PROPERTY + r"[^;]*?\b(" + _COLOR_NAMES + r")\b")

# rgb()/rgba()/hsl()/hsla() pin a value just as hard as a hex does.
_CSS_FUNC = re.compile(_COLOR_PROPERTY + r"[^;]*?\b(rgba?|hsla?)\s*\(")

# `font-size: 13px` and the `font:` shorthand that hides one.
_PX_FONT = re.compile(r"\bfont(?:-size)?\s*:[^;]*?\b[\d.]+\s*px")

# shared/theme.py::_ALIAS_PAIRS, left column. Nothing under a scanned tree
# reads these; shared/theme.py itself is unscanned and is kept clean by hand.
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


def _line_of(node: ast.Constant, offset: int) -> int:
    """The source line a match at `offset` within the string actually sits on.

    A triple-quoted stylesheet is one ast node but many lines; reporting the
    opening line for all of them sends the reader to the wrong place.
    """
    return node.lineno + node.value.count("\n", 0, offset)


def _scan_file(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    tree = ast.parse(source, filename=str(path))
    docstrings = _docstring_node_ids(tree)
    # A call target -- widget.palette().background() -- is not a token read.
    call_targets = {id(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}

    def suppressed(*linenos: int) -> bool:
        # The finding's own line, or -- for a multi-line string, where the
        # marker cannot go inside the stylesheet text -- its opening line.
        return any(ALLOW_MARKER in lines[ln - 1] for ln in linenos
                   if 0 < ln <= len(lines))

    found: list[tuple[int, str, str]] = []
    for node in ast.walk(tree):
        lineno = getattr(node, "lineno", None)
        if lineno is None:
            continue
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and id(node) not in docstrings):
            for kind, rx, group in (("hex", _HEX, 0), ("css-name", _CSS_NAME, 1),
                                    ("css-func", _CSS_FUNC, 1),
                                    ("px-font", _PX_FONT, 0)):
                for m in rx.finditer(node.value):
                    ln = _line_of(node, m.start())
                    if not suppressed(ln, node.lineno):
                        found.append((ln, kind, m.group(group)))
        elif (isinstance(node, ast.Attribute) and node.attr in FROZEN_ALIASES
                and id(node) not in call_targets and not suppressed(lineno)):
            found.append((lineno, "alias", node.attr))

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
