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
        "gui/actions_handler.py",
        "open_settings_window",
    ): "Bundle 10 (9.23) owns settings save feedback",
    ("gui/settings/window.py", "*"): "Bundle 10 (9.23)",
    ("gui/settings/sets.py", "*"): "Bundle 10 (9.23)",
    ("gui/column_config_dialog.py", "*"): "Bundles 10 (9.23) and 13 (9.16)",
    (
        "gui/main_window_pyside.py",
        "_init_managers",
    ): "stays native: no window exists yet",
}

# Not converted yet. Each conversion task deletes its own lines; Task 12
# deletes this set.
PENDING = {
    "gui/add_product_dialog.py",  # Task 9
    "gui/client_settings_dialog.py",  # Task 9
    "gui/groups_management_dialog.py",  # Task 9
    "gui/tag_categories_dialog.py",  # Task 9
    "gui/rule_test_dialog.py",  # Task 9
    "gui/barcode_generator_widget.py",  # Task 10
    "gui/reference_labels_widget.py",  # Task 10
    "gui/pdf_printing.py",  # Task 10
    "gui/session_browser_widget.py",  # Task 10
    "gui/client_directory.py",  # Task 10
    "gui/log_viewer.py",  # Task 10
    "gui/settings/mappings.py",  # Task 11
    "gui/settings/rules.py",  # Task 11
    "gui/settings/weight.py",  # Task 11
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
    assert offenders(ROOT, skip=PENDING) == []


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
