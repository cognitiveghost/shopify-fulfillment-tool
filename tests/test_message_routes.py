"""9.25: every message to the operator takes one of four routes.

A QMessageBox call left in gui/ is a message that skipped the triage. OWNED
names who owns each survivor, so the later bundle that lands deletes its own
line.

Spec: docs/superpowers/specs/2026-09-10-phase9-bundle9-message-boxes-design.md §10
"""

import ast
import fnmatch
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KINDS = {"information", "warning", "critical", "question"}

OWNED = {
    ("gui/actions_handler.py", "bulk_*"): "Bundle 14 (9.17) replaces these chains",
    (
        "gui/main_window_pyside.py",
        "_init_managers",
    ): "stays native: no window exists yet",
}


def _message_box_calls(tree):
    """Yield (enclosing function name, call node) for each message box call."""

    def walk(node, fn):
        for child in ast.iter_child_nodes(node):
            name = (
                child.name
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                else fn
            )
            if isinstance(child, ast.Call):
                f = child.func
                if (
                    (
                        isinstance(f, ast.Attribute)
                        and isinstance(f.value, ast.Name)
                        and f.value.id == "QMessageBox"
                        and f.attr in KINDS
                    )
                    or isinstance(f, ast.Name)
                    and f.id == "QMessageBox"
                ):
                    yield name, child
            yield from walk(child, name)

    yield from walk(tree, "<module>")


def offenders(root, skip=frozenset()):
    found = []
    for path in sorted((root / "gui").rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        if rel in skip:
            continue
        for fn, call in _message_box_calls(ast.parse(path.read_text(encoding="utf-8"))):
            if any(
                rel == file and fnmatch.fnmatch(fn, pattern) for file, pattern in OWNED
            ):
                continue
            found.append(f"{rel}:{call.lineno} in {fn}")
    return found


def test_no_message_box_outside_the_owned_list():
    assert offenders(ROOT) == []


def test_every_owned_entry_still_matches_a_call():
    """A stale entry is an exemption nobody needs: delete it."""
    for (file, pattern), owner in OWNED.items():
        tree = ast.parse((ROOT / file).read_text(encoding="utf-8"))
        assert any(
            fnmatch.fnmatch(fn, pattern) for fn, _ in _message_box_calls(tree)
        ), (file, owner)


def test_the_guard_catches_a_planted_message_box(tmp_path):
    (tmp_path / "gui").mkdir()
    (tmp_path / "gui" / "planted.py").write_text(
        "def save():\n    QMessageBox.information(None, 'Saved', 'Saved successfully!')\n",
        encoding="utf-8",
    )
    assert offenders(tmp_path) == ["gui/planted.py:2 in save"]
