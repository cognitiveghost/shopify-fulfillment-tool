# Repo Cleanup, Versioning and Releases Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Both apps get a Release button, a version taken from the git tag and shown in the title bar, new display
names and logos, attested release zips, clean docs and dependencies, and aligned CI and GitHub settings.

**Architecture:**
- **Two PRs, packing-tool first**, because it owns `shared/`, where the logos and `brand_icon()` live. The Shopify
  PR syncs `shared/` from the packing-tool worktree.
- **Each repo keeps its one workflow file**, with a new `workflow_dispatch` trigger that runs version → build →
  release.
- **A small `scripts/release_version.py`, identical in both repos**, works out the next tag and stamps it into the
  package's `__version__ = "dev"` line before PyInstaller runs.

**Tech Stack:** PySide6, PyInstaller, GitHub Actions (`actions/attest-build-provenance`, `gh release`), pytest,
ruff, Pillow (only for the one-off `.ico` render).

**Spec:** `docs/superpowers/specs/2026-09-28-repo-cleanup-and-releases-design.md` (this repo). Read it first.

## Worktrees and paths

- `S` = `/home/gloopy/Desktop/Projects/shopify-fulfillment-tool/.claude/worktrees/dr-5` (branch
  `dr/5-chore-clean-up-both-repos-shopify-tool-p`, already pushed with the spec and this plan)
- `P` = `/home/gloopy/Desktop/Projects/packing-tool/.claude/worktrees/dr-5` (same branch name, at `origin/main`)
- Both have a working `.venv` symlink. The Shopify venv (`S/.venv`) has Pillow; the packing venv does not.
- `S` and `P` are shorthand in this plan only. The worktree guard refuses `$VAR` paths, so always type the full
  absolute path in commands.

## Global Constraints

- **Names:** the display names are exactly `Fulfilment Tool` and `Packer Assistant`.
  - exe base names: `FulfilmentTool`, `PackerAssistant`
  - release zips: `FulfilmentTool-<version>.zip`, `PackerAssistant-<version>.zip`
  - PR gate zips: `FulfilmentTool-gate.zip`, `PackerAssistant-gate.zip`
- **Versions:**
  - Tags are unprefixed SemVer (`2.0.0`), and the first release of each repo is `2.0.0`.
  - In the repo the version is always `__version__ = "dev"`. Nothing else carries an app version: no README line,
    no CLAUDE.md line, no second `__version__`.
- **Never change any `QSettings(...)` organisation/application string.** Saved theme, geometry and client choices
  depend on them.
- **Never change these `"1.3.0"` strings in packing-tool.** They are data-format versions:
  - `packer_logic.py`
  - `worker_manager.py`
  - `gui/main_window.py:1547`
  - `session_history_manager.py`
  - `exceptions.py`

  The one exception is `SessionLockManager.app_version`.
- **Do not hand-edit anything under `S/shared/`.** Edit `P/shared/`, then sync.
- **Git (dev VM guard):**
  - Use `/usr/bin/git`, one plain git command per Bash call, with no `&&`, `;`, `$VAR`, xargs or `cd … &&`.
    Use `git -C <abs path>`.
  - Commit with `/usr/bin/git -C <repo> commit -F <abs path to message file>`, and write the message file with
    the Write tool. End every message with the attribution lines from your session's system reminder.
- **Tests:**
  - Gate: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` run from the repo root.
  - Lint: `.venv/bin/ruff check . --exclude shared` in Shopify, `.venv/bin/ruff check .` in packing-tool.
  - The pytest-guard hook may refuse a targeted run like `… -m pytest -q tests/test_x.py`. If it does, run the
    plain full-suite form instead.
  - Write test files with Write/Edit, never with shell heredocs.
- **After each repo's code changes are done, run `graphify update .` in that repo.** `graphify-out/` is gitignored,
  so it is never committed.

## Review Focus

1. **Odd tags** (`1.3.2.0.2`, `v3`, `nightly`, `1.2`) and numeric ordering (`1.10.0` above `1.9.0`) must still
   give the right next version. This is pinned in Task 1's parametrised test.
2. **Someone reformats the `__version__` line**, and CI's stamp silently no-ops, shipping a "dev" build. `stamp`
   raises, and `test_the_package_ships_as_dev` fails first (Tasks 1 and 9).
3. **The rename wipes users' saved settings.** Tasks 7 and 15 end with a diff check that no `QSettings(` line
   changed.
4. **The frozen exe starts with a blank icon** because Qt's `qico` plugin was not bundled. The CI asset check
   includes `qico.dll` (Tasks 5 and 13), and the `windows-build` run in Tasks 7 and 15 proves it.
5. **Running from source shows a blank or garbage title.** The title tests assert
   `f"{APP_NAME} {__version__}"`, which is `"… dev"` in the repo (Tasks 2 and 10).

---

# Part A — packing-tool (`P`)

### Task 1: `scripts/release_version.py` (packing-tool)

**Files:**
- Create: `P/scripts/release_version.py`
- Test: `P/tests/test_release_version.py`

**Interfaces:**
- Produces:
  - `next_version(tags: list[str], bump: str) -> str`
  - `stamp(path: str | Path, version: str) -> None`
  - CLI `python scripts/release_version.py next <bump>` prints the version (reads `git tag --list`).
  - CLI `python scripts/release_version.py stamp <file> <version>`.
- Task 5's workflow uses both CLIs, and Task 9 copies this file byte for byte.

- [ ] **Step 1: Write the failing test** at `P/tests/test_release_version.py`:

```python
"""The Release button's version logic (scripts/release_version.py)."""
from pathlib import Path

import pytest

from scripts.release_version import next_version, stamp

ROOT = Path(__file__).resolve().parent.parent
PACKAGE_INIT = ROOT / "packing_tool" / "__init__.py"


@pytest.mark.parametrize(
    "tags, bump, expected",
    [
        (["1.9.11.0", "1.9.10.8"], "major", "2.0.0"),
        (["1.9.11.0", "1.9.10.8"], "patch", "1.9.12"),
        (["1.3.10.2", "1.3.2.0.2"], "minor", "1.4.0"),
        (["2.0.0", "1.9.11.0"], "patch", "2.0.1"),
        (["1.10.0", "1.9.0"], "patch", "1.10.1"),  # numeric, not string, order
        ([], "patch", "0.0.1"),
        (["v3", "nightly", "1.2"], "minor", "0.1.0"),  # non-version tags ignored
    ],
)
def test_next_version(tags, bump, expected):
    assert next_version(tags, bump) == expected


def test_an_unknown_bump_is_refused():
    with pytest.raises(ValueError):
        next_version(["1.0.0"], "huge")


def test_stamp_rewrites_only_the_version_line(tmp_path):
    init = tmp_path / "__init__.py"
    init.write_text('"""Pkg."""\n__version__ = "dev"\nAPP_NAME = "X"\n', encoding="utf-8")
    stamp(init, "2.0.0")
    assert init.read_text(encoding="utf-8") == '"""Pkg."""\n__version__ = "2.0.0"\nAPP_NAME = "X"\n'


def test_stamp_refuses_a_file_without_the_line(tmp_path):
    init = tmp_path / "__init__.py"
    init.write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(ValueError):
        stamp(init, "2.0.0")


def test_the_package_ships_as_dev():
    """CI stamps this exact line. If it drifts, stamp() raises and the
    release fails loudly instead of shipping a build that says "dev"."""
    source = PACKAGE_INIT.read_text(encoding="utf-8")
    assert source.count('__version__ = "dev"') == 1
```

- [ ] **Step 2: Run** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_release_version.py` in `P`.
  Expected: FAIL, `ModuleNotFoundError: scripts.release_version`.

- [ ] **Step 3: Implement** `P/scripts/release_version.py`:

```python
"""Versioning for the Release button (see .github/workflows).

The git tag is the app's only version. `next` picks the tag the release will
get; `stamp` writes it into the package's `__version__ = "dev"` line before
PyInstaller runs.

    python scripts/release_version.py next patch|minor|major
    python scripts/release_version.py stamp <package>/__init__.py <version>
"""
import re
import subprocess
import sys
from pathlib import Path

# Old releases used 4- and 5-part tags (1.9.11.0, 1.3.2.0.2); they count by
# their first three numbers.
_TAG = re.compile(r"\d+(\.\d+){2,}")
_VERSION_LINE = re.compile(r'^__version__ = ".*"$', re.MULTILINE)


def next_version(tags, bump):
    versions = [tuple(int(part) for part in tag.split(".")[:3]) for tag in tags if _TAG.fullmatch(tag)]
    major, minor, patch = max(versions, default=(0, 0, 0))
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    if bump == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"bump must be major, minor or patch, not {bump!r}")


def stamp(path, version):
    path = Path(path)
    text, count = _VERSION_LINE.subn(f'__version__ = "{version}"', path.read_text(encoding="utf-8"))
    if count != 1:
        raise ValueError(f"expected one __version__ line in {path}, found {count}")
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    command, *args = sys.argv[1:]
    if command == "next":
        tags = subprocess.run(
            ["git", "tag", "--list"], capture_output=True, text=True, check=True
        ).stdout.split()
        print(next_version(tags, args[0]))
    elif command == "stamp":
        stamp(args[0], args[1])
    else:
        sys.exit(f"unknown command {command!r}")
```

- [ ] **Step 4: Run the test again.** Expected: every test passes except `test_the_package_ships_as_dev`, which
  fails until Task 2 adds the line. That is expected; Task 2 turns it green. Commit anyway.
- [ ] **Step 5: Commit** `scripts/release_version.py` and `tests/test_release_version.py` with the message
  `feat: release_version script for the Release button`.

### Task 2: App identity: name, version, title, log, lock file (packing-tool)

**Files:**
- Modify:
  - `P/packing_tool/__init__.py` (the whole file is currently one docstring line)
  - `P/gui/main_window.py:217`, plus the imports and the log line after `logger.info("ProfileManager initialized successfully")` (~line 234)
  - `P/packing_tool/session_lock_manager.py:51`
  - `P/main.py`
- Test: `P/tests/test_shell.py` (append), `P/tests/test_session_lock_manager.py` (append)

**Interfaces:**
- Produces:
  - `packing_tool.APP_NAME = "Packer Assistant"`
  - `packing_tool.__version__ = "dev"`
- Task 3 edits `main.py` again (the icon); Task 5 stamps `packing_tool/__init__.py`.

- [ ] **Step 1: Append the failing tests.**

  `P/tests/test_shell.py` (its module-scoped `window` fixture already exists):

```python
def test_the_title_names_the_app_and_its_version(window):
    from packing_tool import APP_NAME, __version__

    assert window.windowTitle() == f"{APP_NAME} {__version__}"
```

  `P/tests/test_session_lock_manager.py`:

```python
def test_a_lock_records_the_running_app_version():
    """Lock files say which build held the session; it used to be a
    hardcoded "1.3.0" whatever the release."""
    from packing_tool import __version__
    from packing_tool.session_lock_manager import SessionLockManager

    assert SessionLockManager(None).app_version == __version__
```

- [ ] **Step 2: Run the full suite.** Expected: these two FAIL (`ImportError: cannot import name 'APP_NAME'`), as
  does `test_the_package_ships_as_dev`.
- [ ] **Step 3: Implement.**

  `P/packing_tool/__init__.py` becomes:

```python
"""Backend package: session, packer logic, and state management."""

APP_NAME = "Packer Assistant"

# The release build stamps the git tag over "dev" (scripts/release_version.py).
# Never hand-edit it.
__version__ = "dev"
```

  In `P/gui/main_window.py`:
  - Add `from packing_tool import APP_NAME, __version__` to the import block.
  - Replace `self.setWindowTitle("Packer's Assistant")` with `self.setWindowTitle(f"{APP_NAME} {__version__}")`.
  - Directly below `logger.info("ProfileManager initialized successfully")`, add
    `logger.info("%s %s", APP_NAME, __version__)`. That is the first log line after logging is set up.

  In `P/packing_tool/session_lock_manager.py`:
  - Add `from packing_tool import __version__` below `from shared.atomic_write import atomic_write_json`.
  - Change `self.app_version = "1.3.0"` to `self.app_version = __version__`.

  In `P/main.py`:
  - Change the docstring to `"""Packer Assistant — entry point."""`.
  - Add `from packing_tool import APP_NAME` after the `gui.theme` import.
  - Change `argparse.ArgumentParser(description="Packer's Assistant")` to
    `argparse.ArgumentParser(description=APP_NAME)`.
- [ ] **Step 4: Run the full suite.** Expected: PASS, including `test_the_package_ships_as_dev`.
- [ ] **Step 5: Commit** with the message `feat: Packer Assistant name and version in title, log and lock files`.

### Task 3: Logos, `brand_icon()`, exe icon (packing-tool, canonical `shared/`)

**Files:**
- Create:
  - `P/shared/assets/brand/fulfilment-tool.svg`, `P/shared/assets/brand/packer-assistant.svg`
  - `P/shared/assets/brand/fulfilment-tool.ico`, `P/shared/assets/brand/packer-assistant.ico` (generated)
- Modify:
  - `P/shared/icons.py` (add `BRAND_DIR` and `brand_icon`)
  - `P/shared/assets/README.md` (a brand section)
  - `P/main.py` (window icon)
  - `P/main.spec` (name and icon)
- Test: `P/tests/test_brand_icon.py` (create), `P/tests/test_ui_assets.py` (append)

**Interfaces:**
- Produces `shared.icons.brand_icon(name: str) -> QIcon`, with names `"fulfilment-tool"` and `"packer-assistant"`.
  It raises `KeyError` on an unknown name. Task 10 uses it via the synced `shared/`.
- Produces `shared.icons.BRAND_DIR: Path`.

- [ ] **Step 1: Write the failing tests.**

  `P/tests/test_brand_icon.py`:

```python
"""The app logos: one multi-size .ico per app, used for the window, the
taskbar and (via PyInstaller --icon) the exe itself."""
import pytest

from shared.icons import brand_icon


@pytest.mark.parametrize(
    "name, tile", [("fulfilment-tool", "#006fba"), ("packer-assistant", "#2c6630")]
)
def test_a_logo_carries_every_windows_size_and_its_tile_colour(qapp, name, tile):
    logo = brand_icon(name)
    assert {16, 32, 48, 256} <= {size.width() for size in logo.availableSizes()}
    # (4, 24) is inside the rounded tile and clear of the glyph.
    assert logo.pixmap(48, 48).toImage().pixelColor(4, 24).name() == tile


def test_an_unknown_logo_is_a_loud_error():
    with pytest.raises(KeyError):
        brand_icon("no-such-app")
```

  Append to `P/tests/test_ui_assets.py`:

```python
@pytest.mark.parametrize("name", ["fulfilment-tool", "packer-assistant"])
@pytest.mark.parametrize("suffix", [".svg", ".ico"])
def test_both_app_logos_are_vendored(name, suffix):
    assert (ASSETS_DIR / "brand" / f"{name}{suffix}").is_file()
```

- [ ] **Step 2: Run the suite.** Expected: the new tests FAIL (`ImportError: brand_icon`, missing files).
- [ ] **Step 3: Write the two SVGs** exactly as below. The glyph paths are Lucide 1.31.0 `package` and
  `scan-barcode`.

  `P/shared/assets/brand/fulfilment-tool.svg`:

```xml
<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">
  <rect width="24" height="24" rx="5" fill="#006FBA"/>
  <g transform="translate(4.5 4.5) scale(0.625)" fill="none" stroke="#FFFFFF" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
    <path d="M11 21.73a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73z"/>
    <path d="M12 22V12"/>
    <polyline points="3.29 7 12 12 20.71 7"/>
    <path d="m7.5 4.27 9 5.15"/>
  </g>
</svg>
```

  `P/shared/assets/brand/packer-assistant.svg`:

```xml
<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">
  <rect width="24" height="24" rx="5" fill="#2C6630"/>
  <g transform="translate(4.5 4.5) scale(0.625)" fill="none" stroke="#FFFFFF" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
    <path d="M3 7V5a2 2 0 0 1 2-2h2"/>
    <path d="M17 3h2a2 2 0 0 1 2 2v2"/>
    <path d="M21 17v2a2 2 0 0 1-2 2h-2"/>
    <path d="M7 21H5a2 2 0 0 1-2-2v-2"/>
    <path d="M8 7v10"/>
    <path d="M12 7v10"/>
    <path d="M17 7v10"/>
  </g>
</svg>
```

- [ ] **Step 4: Generate the `.ico` files.**
  1. Write this throwaway script to your job tmp dir as `make_ico.py`. Do not commit it.

```python
import io
import sys
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

app = QGuiApplication([])
SIZES = (16, 24, 32, 48, 256)
for svg in sorted(Path(sys.argv[1]).glob("*.svg")):
    renderer = QSvgRenderer(str(svg))
    frames = []
    for size in SIZES:
        image = QImage(size, size, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        renderer.render(painter)
        painter.end()
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buf, "PNG")
        frames.append(Image.open(io.BytesIO(bytes(buf.data()))).convert("RGBA"))
    frames[-1].save(svg.with_suffix(".ico"), sizes=[(s, s) for s in SIZES], append_images=frames[:-1])
    print(svg.with_suffix(".ico"))
```

  2. Run it with the Shopify venv, which has Pillow:
     `QT_QPA_PLATFORM=offscreen /home/gloopy/Desktop/Projects/shopify-fulfillment-tool/.venv/bin/python <tmp>/make_ico.py /home/gloopy/Desktop/Projects/packing-tool/.claude/worktrees/dr-5/shared/assets/brand`
  3. Expected: two `.ico` paths are printed, each file about 9–12 KB.
  4. Save a 256 px PNG of each logo to your tmp dir for the PR description. The stage-A prototype of these exact
     SVGs rendered correctly: a white box on blue, and a white barcode-in-brackets on green.

- [ ] **Step 5: Implement `brand_icon`** in `P/shared/icons.py`.

  Below `ICONS_DIR = …`, add:

```python
BRAND_DIR = Path(__file__).resolve().parent / "assets" / "brand"
```

  Then append at the end of the module:

```python
def brand_icon(name: str) -> QIcon:
    """An app's logo, e.g. brand_icon("packer-assistant"), for the window and
    taskbar.

    Loaded straight from the multi-size .ico the exe also carries (PyInstaller
    --icon), so window, taskbar and Explorer show one image. Not themed: it sits
    on the OS shell's own surface. This is the one QIcon built from a file, so
    the frozen build needs Qt's qico imageformat plugin; the CI bundle check
    looks for qico.dll.

    Raises KeyError on an unknown name, like icon().
    """
    path = BRAND_DIR / f"{name}.ico"
    if not path.is_file():
        raise KeyError(f"No bundled logo named {name!r} (looked in {BRAND_DIR})")
    return QIcon(str(path))
```

- [ ] **Step 6: Wire it in.**

  In `P/main.py`:
  - Add `from shared.icons import brand_icon`.
  - Directly after `app = QApplication(sys.argv)`, add `app.setWindowIcon(brand_icon("packer-assistant"))`.

  In `P/main.spec`:
  - Change `name='Packers-Assistant'` to `name='PackerAssistant'`. It appears twice, in `EXE(...)` and
    `COLLECT(...)`.
  - Add `icon='shared/assets/brand/packer-assistant.ico',` to `EXE(...)` after `console=False,`.
  - `shared/assets` is already in `datas`, so the `.ico` files ship without further changes.

- [ ] **Step 7: Document the assets.** Append to `P/shared/assets/README.md`:

```markdown
## brand/ — app logos

`fulfilment-tool` (Lucide `package` on `#006FBA`) and `packer-assistant`
(Lucide `scan-barcode` on `#2C6630`): white Lucide 1.31.0 glyphs (ISC, see
`icons/LICENSE`) on a rounded tile. The `.svg` is the source; the `.ico`
(16/24/32/48/256 px) is rendered from it once with QSvgRenderer + Pillow and is
what both the exe (PyInstaller `--icon`) and `shared.icons.brand_icon()` load.
Re-render the `.ico` whenever the `.svg` changes.
```

- [ ] **Step 8: Run the full suite and ruff.** Expected: PASS. `test_icon_usage_guard` does not match
  `brand_icon(`, because `\bicon\(` needs a word boundary and `_` is a word character.
- [ ] **Step 9: Commit** the four brand files, `shared/icons.py`, `shared/assets/README.md`, `main.py`, `main.spec`
  and the two test files, with the message `feat: Packer Assistant and Fulfilment Tool logos as window and exe icons`.

### Task 4: Cleanup: docs, tracked local settings, requirements (packing-tool)

**Files:**
- Delete: `P/docs/superpowers/`, `P/docs/audit/`, `P/docs/design/`
- Untrack: `P/.claude/settings.local.json`
- Modify: `P/.gitignore`, `P/requirements.txt`, `P/requirements-dev.txt`

- [ ] **Step 1: Delete the docs.** Use one command per call:
  1. `/usr/bin/git -C /home/gloopy/Desktop/Projects/packing-tool/.claude/worktrees/dr-5 rm -r -q docs/superpowers`
  2. `… rm -r -q docs/audit`
  3. `… rm -r -q docs/design`
- [ ] **Step 2: Untrack the local settings.**
  1. Run `/usr/bin/git -C … rm --cached -q .claude/settings.local.json`.
  2. Append to `P/.gitignore`:

```
# Claude Code per-machine settings
.claude/settings.local.json
```

- [ ] **Step 3: Update the requirements.**
  - `P/requirements.txt`: delete the `pyinstaller` line. The file keeps `PySide6` (with its comment), `pandas` and
    `openpyxl`.
  - `P/requirements-dev.txt` becomes:

```
pyinstaller
pytest
pytest-qt
ruff~=0.16.0
```

- [ ] **Step 4: Check nothing live pointed at the deleted docs.** Run
  `grep -rn "docs/design/phase10" --include=*.py --include=*.spec --include=*.yml /home/gloopy/Desktop/Projects/packing-tool/.claude/worktrees/dr-5 | grep -v .venv`.
  - Expected: comment and docstring hits only. They stay (spec §3); Task 6 adds the git-history line to CLAUDE.md.
  - Any hit that *reads* a file at runtime would be a stop-and-note, but none is expected.
- [ ] **Step 5: Run the full suite.** Expected: PASS.
- [ ] **Step 6: Commit** with the message `chore: drop shipped docs, untrack local Claude settings, pyinstaller is a dev dependency`.

### Task 5: CI workflow, templates, Dependabot (packing-tool)

**Files:**
- Replace: `P/.github/workflows/build-release.yml`
- Create:
  - `P/.github/pull_request_template.md`
  - `P/.github/ISSUE_TEMPLATE/bug.yml`, `feature.yml`, `config.yml`
  - `P/.github/dependabot.yml`

**Interfaces:**
- Consumes `scripts/release_version.py` (Task 1) and `packing_tool/__init__.py` (Task 2).
- Produces:
  - the job named **`Run Tests`**, which Task 17's ruleset requires;
  - the artifact `bundle`, which holds `PackerAssistant-<v>.zip` or `PackerAssistant-gate.zip`.

- [ ] **Step 1: Replace `P/.github/workflows/build-release.yml`** with:

```yaml
name: Test, Build and Release

permissions:
  contents: read

on:
  push:
    branches:
      - main
  pull_request:
    branches:
      - main
    # 'labeled' so applying the windows-build label triggers a build on an
    # already-open PR. The default types do not include it.
    types: [opened, synchronize, reopened, labeled]
  # The Release button: Actions -> this workflow -> Run workflow, on main.
  workflow_dispatch:
    inputs:
      bump:
        description: Which part of the version to bump
        type: choice
        options: [patch, minor, major]
        default: patch
      prerelease:
        description: Mark the release as a pre-release
        type: boolean
        default: false

jobs:
  verify:
    name: Run Tests
    runs-on: ubuntu-latest
    steps:
      - name: Check out code
        uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          # QtWebEngine's runtime (NSS and X client libs), the same set as
          # shopify-fulfillment-tool's CI, so the packer document tests drive
          # a real Chromium on every PR.
          sudo apt-get update && sudo apt-get install -y libegl1 libnss3 libnspr4 libxcomposite1 libxdamage1 libxrandr2 libxkbfile1 libxtst6 libxkbcommon0 libgbm1 libasound2t64 libxcb-dri3-0
          python -m pip install --upgrade pip
          pip install -r requirements.txt -r requirements-dev.txt
      - name: Lint (ruff)
        # No --exclude shared: this repo owns shared/.
        run: ruff check .
      - name: Import main module
        run: python -c "import main"
      - name: Run tests
        env:
          QT_QPA_PLATFORM: offscreen
        run: python -m pytest

  version:
    name: Next Version
    needs: [verify]
    # Releases come from main only. On any other branch this job skips, and
    # so do build and release below.
    if: github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    outputs:
      version: ${{ steps.next.outputs.version }}
    steps:
      - name: Check out code with tags
        uses: actions/checkout@v4
        with:
          fetch-depth: 0
          fetch-tags: true
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Pick the next version from the tags
        id: next
        env:
          BUMP: ${{ inputs.bump }}
        run: |
          version=$(python scripts/release_version.py next "$BUMP")
          echo "version=$version" >> "$GITHUB_OUTPUT"

  build:
    name: Build Executable
    needs: [verify, version]
    runs-on: windows-latest
    # A release (version succeeded), or a PR carrying the windows-build label:
    # Windows-only questions (frozen bundles, RDP) cannot be answered from the
    # Ubuntu dev machine, and the repo is public so the minutes are free.
    # always() because version is skipped on PRs, and a skipped need would
    # otherwise skip this job too.
    if: >-
      always() && needs.verify.result == 'success' && (
        needs.version.result == 'success' ||
        (github.event_name == 'pull_request' &&
         contains(github.event.pull_request.labels.*.name, 'windows-build')))
    env:
      VERSION: ${{ needs.version.outputs.version }}
    steps:
      - name: Check out code
        uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt -r requirements-dev.txt
      - name: Stamp the release version
        # PR gate builds skip this and say "dev" in the title.
        if: env.VERSION != ''
        run: python scripts/release_version.py stamp packing_tool/__init__.py $env:VERSION
      - name: Build executable with PyInstaller
        run: pyinstaller main.spec
      - name: Verify bundled assets shipped
        # A missing shared/assets does not degrade: icon() raises during
        # MainWindow construction, and --windowed means the user double-clicks
        # an exe that silently never opens.
        #
        # QtWebEngineProcess.exe and packer.html are the same shape of problem
        # for the order document: PyInstaller's hook-PySide6.QtWebEngineCore is
        # supposed to collect the helper process, and if it silently does not,
        # the only symptom is a dead view discovered over RDP after a full
        # build and a several-hundred-MB download. Fail here instead.
        #
        # qico.dll is Qt's .ico reader: without it brand_icon() loads nothing
        # and the window and taskbar show a blank icon.
        shell: pwsh
        run: |
          foreach ($name in "package.svg", "Inter-Regular.ttf", "QtWebEngineProcess.exe", "packer.html", "packer-assistant.ico", "qico.dll") {
            if (-not (Get-ChildItem -Path "dist\PackerAssistant" -Recurse -Filter $name)) {
              throw "PyInstaller did not bundle $name -- the app would not start."
            }
          }
      - name: Zip the bundle
        shell: pwsh
        run: |
          $name = if ($env:VERSION) { "PackerAssistant-$env:VERSION" } else { "PackerAssistant-gate" }
          Compress-Archive -Path "dist\PackerAssistant\*" -DestinationPath "$name.zip"
      - name: Upload the bundle
        uses: actions/upload-artifact@v4
        with:
          name: bundle
          path: PackerAssistant-*.zip
          # Already a zip; re-compressing several hundred MB buys nothing.
          compression-level: 0

  release:
    name: Publish Release
    # Runs only when version and build both succeeded, i.e. on the Release
    # button. A release made with GITHUB_TOKEN would not trigger another
    # workflow, which is why the build lives in this one.
    needs: [version, build]
    runs-on: ubuntu-latest
    permissions:
      contents: write
      id-token: write
      attestations: write
    env:
      VERSION: ${{ needs.version.outputs.version }}
    steps:
      - name: Download the bundle
        uses: actions/download-artifact@v4
        with:
          name: bundle
      - name: Checksum
        run: sha256sum "PackerAssistant-$VERSION.zip" > "PackerAssistant-$VERSION.zip.sha256"
      - name: Attest build provenance
        uses: actions/attest-build-provenance@v2
        with:
          subject-path: PackerAssistant-${{ needs.version.outputs.version }}.zip
      - name: Create the release
        # Last, so a failed build or attestation leaves no tag behind.
        env:
          GH_TOKEN: ${{ github.token }}
          PRERELEASE: ${{ inputs.prerelease && '--prerelease' || '' }}
        run: >
          gh release create "$VERSION"
          "PackerAssistant-$VERSION.zip" "PackerAssistant-$VERSION.zip.sha256"
          --repo "$GITHUB_REPOSITORY" --target "$GITHUB_SHA"
          --title "$VERSION" --generate-notes $PRERELEASE
```

- [ ] **Step 2: Create `P/.github/pull_request_template.md`:**

```markdown
## What

## Why

## How tested

- [ ] `QT_QPA_PLATFORM=offscreen python -m pytest`
- [ ] `ruff check .`
- [ ] `windows-build` label run passed (only if the bundle, its assets or `main.spec` changed)

## Release note

<!-- One line for the release notes, or "none". -->
```

- [ ] **Step 3: Create the issue forms.**

  `P/.github/ISSUE_TEMPLATE/bug.yml`:

```yaml
name: Bug report
description: Something in the app does not work as it should
labels: [bug]
body:
  - type: input
    id: version
    attributes:
      label: App version
      description: The number in the window title, e.g. 2.0.0
    validations:
      required: true
  - type: input
    id: where
    attributes:
      label: PC and client
      description: Which warehouse PC, and which client were you working on?
  - type: textarea
    id: what
    attributes:
      label: What happened
    validations:
      required: true
  - type: textarea
    id: expected
    attributes:
      label: What you expected
  - type: textarea
    id: steps
    attributes:
      label: Steps to reproduce
      placeholder: "1. ...\n2. ..."
```

  `P/.github/ISSUE_TEMPLATE/feature.yml`:

```yaml
name: Feature request
description: Something the app should do that it does not
labels: [enhancement]
body:
  - type: textarea
    id: problem
    attributes:
      label: Problem
      description: What gets in the way today?
    validations:
      required: true
  - type: textarea
    id: proposal
    attributes:
      label: Proposal
      description: What should happen instead?
```

  `P/.github/ISSUE_TEMPLATE/config.yml`:

```yaml
blank_issues_enabled: true
```

- [ ] **Step 4: Create `P/.github/dependabot.yml`:**

```yaml
version: 2
updates:
  - package-ecosystem: pip
    directory: /
    schedule:
      interval: weekly
    groups:
      python:
        patterns: ["*"]
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: weekly
    groups:
      actions:
        patterns: ["*"]
```

- [ ] **Step 5: Check the YAML parses.** Run
  `.venv/bin/python -c "import sys, yaml; [yaml.safe_load(open(p)) for p in sys.argv[1:]]; print('ok')" .github/workflows/build-release.yml .github/dependabot.yml .github/ISSUE_TEMPLATE/bug.yml .github/ISSUE_TEMPLATE/feature.yml .github/ISSUE_TEMPLATE/config.yml`.
  - Expected: `ok`.
  - If `yaml` is not installed in this venv, use `/home/gloopy/Desktop/Projects/shopify-fulfillment-tool/.venv/bin/python`.
  - If neither has it, skip this step and note that; CI parses the workflow on push anyway.
- [ ] **Step 6: Commit** with the message `ci: Release button, Ubuntu test job, PackerAssistant bundle, templates and Dependabot`.

### Task 6: README and CLAUDE.md (packing-tool)

**Files:** Replace `P/README.md`; modify `P/CLAUDE.md`.

- [ ] **Step 1: Replace `P/README.md`** with:

````markdown
# Packer Assistant

Windows desktop app (PySide6) for the warehouse floor. Open a session prepared by
[Fulfilment Tool](https://github.com/cognitiveghost/shopify-fulfillment-tool), scan an order's barcode, then scan
its items: the app checks every line is packed. Progress is saved after every scan, a session is locked to one PC
at a time with a heartbeat, and both apps share one file server and one statistics file.

## Download

Take the latest zip from [Releases](https://github.com/cognitiveghost/packing-tool/releases), unzip it and run
`PackerAssistant.exe`. The version is in the window title.

Point it at the file server once in **Settings → Server Connection**, or copy `config.ini.example` (shipped in the
zip) to `config.ini` next to the exe and set `FileServerPath`.

To check a download was built by this repo's CI:

```bash
gh attestation verify PackerAssistant-<version>.zip -R cognitiveghost/packing-tool
```

or compare it against the `.sha256` file attached to the same release.

## Run from source

Python 3.14 on the dev machine; CI and release builds use 3.11.

```bash
git clone https://github.com/cognitiveghost/packing-tool.git
cd packing-tool
python -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/python main.py                 # uses config.ini (production share)
.venv/bin/python run_dev.py              # uses ../shopify-fulfillment-tool/dev-server
```

`run_dev.py` needs Fulfilment Tool's `run_dev.py` to have been run once first, to create that dev server.

## Test and lint

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
.venv/bin/ruff check .
```

CI runs both on every PR. Label a PR `windows-build` to also get a frozen Windows build of it as a workflow
artifact.

## Release

Actions → **Test, Build and Release** → **Run workflow** on `main`, then pick `patch`, `minor` or `major`. CI
tests, takes the next version from the tags, builds, attests, and publishes the release with generated notes.

Do not create releases by hand in the GitHub UI: nothing builds for them.

## Layout

- `gui/`: Qt UI; `gui/web/` is the order document (QtWebEngine)
- `packing_tool/`: sessions, scanning logic, locks, state
- `shared/`: code shared with Fulfilment Tool. **This repo is its canonical source** (see `CLAUDE.md`)
- `docs/adr/`: decisions; `CONTEXT.md`: the domain glossary

## Links

- Issues: <https://github.com/cognitiveghost/packing-tool/issues>
- Releases: <https://github.com/cognitiveghost/packing-tool/releases>
````

- [ ] **Step 2: Edit `P/CLAUDE.md`.**
  1. In line 6, delete the sentence ` Version per `README.md:3` (currently 1.3.2.0, pre-release).` so the line
     ends at `development happens on Linux.`
  2. Replace
     ``**This copy is the canonical source** — see\n`docs/superpowers/specs/2026-07-25-shared-unification-design.md`.``
     with `**This copy is the canonical source.**`
  3. Insert this section immediately before `## DO NOT`:

```markdown
## Releases

The git tag is the version. In the repo `packing_tool/__init__.py` holds `__version__ = "dev"`; the release build
stamps the tag into it (`scripts/release_version.py`). Never hand-edit `__version__` or write a version into docs.
To release: Actions → Test, Build and Release → Run workflow on `main` → pick the bump. Never create a release in
the GitHub UI — nothing builds for it.

---

```

  4. Under `### Domain docs`, after the `Single-context: …` line, add a blank line and:

```markdown
Doc paths cited in code comments that no longer exist (shipped specs, plans, audits, mockups) are in git history:
`git log --all -- <path>`.
```

- [ ] **Step 3: Commit** `README.md` and `CLAUDE.md` with the message `docs: README and CLAUDE.md match the repo as it is`.

### Task 7: Gate, push, PR (packing-tool)

- [ ] **Step 1: Run the gate** in `P`:
  - `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` must PASS.
  - `.venv/bin/ruff check .` must be clean.
- [ ] **Step 2: Check settings keys are untouched.**
  Run `/usr/bin/git -C /home/gloopy/Desktop/Projects/packing-tool/.claude/worktrees/dr-5 diff origin/main -G "QSettings\(" --stat`.
  Expected: no output.
- [ ] **Step 3: Update the graph.** Run `graphify update .` in `P`.
- [ ] **Step 4: Push.** Run `/usr/bin/git -C … push -u origin dr/5-chore-clean-up-both-repos-shopify-tool-p`.
- [ ] **Step 5: Create the `windows-build` label**; packing-tool does not have one yet:
  `gh label create windows-build -R cognitiveghost/packing-tool --color 1D76DB --description "Build the frozen Windows bundle for this PR"`
- [ ] **Step 6: Open the PR.**
  - Title: `chore: Packer Assistant 2.0 groundwork — Release button, logo, cleanup`.
  - Body (via `--body-file`):
    - a summary per task;
    - the rendered logo PNGs, or a note that they are in the PR's `windows-build` artifact;
    - "Merge before the shopify-fulfillment-tool PR: that one syncs `shared/` from this one";
    - "After merge: Actions → Test, Build and Release → Run workflow → `major` gives 2.0.0";
    - the 🤖 line from your session's attribution reminder.
  - Command: `gh pr create -R cognitiveghost/packing-tool --base main --head dr/5-chore-clean-up-both-repos-shopify-tool-p --title … --body-file <file> --label windows-build`
- [ ] **Step 7: Wait for CI.** Run `gh pr checks <n> -R cognitiveghost/packing-tool --watch`. Expected: `Run Tests`
  and `Build Executable` both pass.
  - If `Run Tests` fails only on Ubuntu for a reason the Linux dev machine cannot reproduce, note it and stop.
  - If the asset check fails on `qico.dll`, note it and stop. Do not guess a PyInstaller flag.

---

# Part B — shopify-fulfillment-tool (`S`)

### Task 8: Sync `shared/` from the packing-tool worktree

**Files:** Modify `S/shared/**` (via the script only). Test: `S/tests/test_ui_assets.py` (append).

- [ ] **Step 1: Append the failing test** to `S/tests/test_ui_assets.py`:

```python
@pytest.mark.parametrize("name", ["fulfilment-tool", "packer-assistant"])
@pytest.mark.parametrize("suffix", [".svg", ".ico"])
def test_both_app_logos_are_vendored(name, suffix):
    assert (ASSETS_DIR / "brand" / f"{name}{suffix}").is_file()
```

- [ ] **Step 2: Run it.** Expected: FAIL (the files are missing).
- [ ] **Step 3: Sync.** In `S`, run
  `.venv/bin/python scripts/sync_shared.py /home/gloopy/Desktop/Projects/packing-tool/.claude/worktrees/dr-5`.
  Expected: it reports copying `shared/assets/brand/*`, `shared/icons.py` and `shared/assets/README.md`.
- [ ] **Step 4: Run the full suite.** Expected: PASS.
- [ ] **Step 5: Commit** `shared/` and `tests/test_ui_assets.py` with the message
  `chore: sync shared/ from packing-tool (app logos, brand_icon)`.

### Task 9: `scripts/release_version.py` (Shopify)

**Files:** Create `S/scripts/release_version.py` and `S/tests/test_release_version.py`.

**Interfaces:** the same as Task 1. Task 13's workflow calls
`python scripts/release_version.py stamp shopify_tool/__init__.py <v>`.

- [ ] **Step 1: Copy the script.** Run `cp /home/gloopy/Desktop/Projects/packing-tool/.claude/worktrees/dr-5/scripts/release_version.py /home/gloopy/Desktop/Projects/shopify-fulfillment-tool/.claude/worktrees/dr-5/scripts/release_version.py`.
  It must be byte-identical.
- [ ] **Step 2: Write `S/tests/test_release_version.py`.** Its content is Task 1's test file with one line changed:

```python
PACKAGE_INIT = ROOT / "shopify_tool" / "__init__.py"
```

  The full file:

```python
"""The Release button's version logic (scripts/release_version.py)."""
from pathlib import Path

import pytest

from scripts.release_version import next_version, stamp

ROOT = Path(__file__).resolve().parent.parent
PACKAGE_INIT = ROOT / "shopify_tool" / "__init__.py"


@pytest.mark.parametrize(
    "tags, bump, expected",
    [
        (["1.9.11.0", "1.9.10.8"], "major", "2.0.0"),
        (["1.9.11.0", "1.9.10.8"], "patch", "1.9.12"),
        (["1.3.10.2", "1.3.2.0.2"], "minor", "1.4.0"),
        (["2.0.0", "1.9.11.0"], "patch", "2.0.1"),
        (["1.10.0", "1.9.0"], "patch", "1.10.1"),  # numeric, not string, order
        ([], "patch", "0.0.1"),
        (["v3", "nightly", "1.2"], "minor", "0.1.0"),  # non-version tags ignored
    ],
)
def test_next_version(tags, bump, expected):
    assert next_version(tags, bump) == expected


def test_an_unknown_bump_is_refused():
    with pytest.raises(ValueError):
        next_version(["1.0.0"], "huge")


def test_stamp_rewrites_only_the_version_line(tmp_path):
    init = tmp_path / "__init__.py"
    init.write_text('"""Pkg."""\n__version__ = "dev"\nAPP_NAME = "X"\n', encoding="utf-8")
    stamp(init, "2.0.0")
    assert init.read_text(encoding="utf-8") == '"""Pkg."""\n__version__ = "2.0.0"\nAPP_NAME = "X"\n'


def test_stamp_refuses_a_file_without_the_line(tmp_path):
    init = tmp_path / "__init__.py"
    init.write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(ValueError):
        stamp(init, "2.0.0")


def test_the_package_ships_as_dev():
    """CI stamps this exact line. If it drifts, stamp() raises and the
    release fails loudly instead of shipping a build that says "dev"."""
    source = PACKAGE_INIT.read_text(encoding="utf-8")
    assert source.count('__version__ = "dev"') == 1
```

- [ ] **Step 3: Run the suite.** Expected: everything passes except `test_the_package_ships_as_dev`, which Task 10
  fixes.
- [ ] **Step 4: Commit** with the message `feat: release_version script for the Release button`.

### Task 10: App identity and logo (Shopify)

**Files:**
- Modify:
  - `S/shopify_tool/__init__.py` (the whole file)
  - `S/gui_main.py` (delete line 15 `__version__ = "1.9.9.1"`; imports; `build_app_icon` at lines 68-83; the
    startup log at ~line 120)
  - `S/gui/main_window_pyside.py:29` (import) and `:96` (title)
- Test:
  - `S/tests/test_first_run.py` (append)
  - `S/tests/test_gui_main_env_setup.py` (replace the tests at lines 91-140)

**Interfaces:**
- Produces:
  - `shopify_tool.APP_NAME = "Fulfilment Tool"`
  - `shopify_tool.__version__ = "dev"`
  - `gui_main.build_app_icon() -> QIcon`, which is now `brand_icon("fulfilment-tool")`
- Consumes `shared.icons.brand_icon` (Task 8).

- [ ] **Step 1: Write the failing tests.**

  Append to `S/tests/test_first_run.py`; its `offline_window` fixture already exists:

```python
def test_the_title_names_the_app_and_its_version(offline_window):
    from shopify_tool import APP_NAME, __version__

    assert offline_window.windowTitle() == f"{APP_NAME} {__version__}"
```

  In `S/tests/test_gui_main_env_setup.py`, delete `test_app_icon_is_built_in_a_fixed_accent_color` and
  `test_app_icon_carries_the_256px_windows_asks_for` (from line 91 to the end of the file), and append:

```python
def test_app_icon_is_the_fulfilment_tool_logo():
    """The same multi-size .ico the exe carries. 256px is what Alt+Tab and
    Explorer's "Extra large icons" ask for; a missing size is only ever
    upscaled."""
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])

    app_icon = gui_main.build_app_icon()
    assert {16, 32, 48, 256} <= {size.width() for size in app_icon.availableSizes()}
    # (4, 24) is inside the blue tile and clear of the white glyph.
    assert app_icon.pixmap(48, 48).toImage().pixelColor(4, 24).name() == "#006fba"
```

- [ ] **Step 2: Run the suite.** Expected: the title test FAILS (`ImportError: APP_NAME`) and the icon test FAILS
  (wrong pixel colour).
- [ ] **Step 3: Implement.**

  `S/shopify_tool/__init__.py` becomes:

```python
"""Fulfilment Tool backend: analysis, rules, sessions and outputs."""

APP_NAME = "Fulfilment Tool"

# The release build stamps the git tag over "dev" (scripts/release_version.py).
# Never hand-edit it.
__version__ = "dev"
```

  In `S/gui_main.py`:
  - Delete the line `__version__ = "1.9.9.1"` and the blank line after it.
  - Next to `from gui.main_window_pyside import MainWindow` (line 63), add `from shopify_tool import APP_NAME, __version__`.
  - Replace `from shared.icons import icon` with `from shared.icons import brand_icon`. First check with
    `grep -n "icon(" gui_main.py` that `build_app_icon` is the only user of `icon(`. If another user exists, keep
    both imports.
  - Replace the whole `build_app_icon` function with:

```python
def build_app_icon():
    """The window/taskbar icon: the Fulfilment Tool logo, the same multi-size
    .ico PyInstaller puts on the exe (--icon), so every surface shows one image."""
    return brand_icon("fulfilment-tool")
```

  - Replace the startup log call with:

```python
        logging.getLogger(__name__).info(
            "%s %s: startup complete in %.2fs",
            APP_NAME,
            __version__,
            time.perf_counter() - _PROCESS_START,
        )
```

  In `S/gui/main_window_pyside.py`:
  - Change line 29 to `from shopify_tool import APP_NAME, __version__, core, fulfillment_history, session_state`.
  - Change line 96 to `self.setWindowTitle(f"{APP_NAME} {__version__}")`.
- [ ] **Step 4: Run the full suite and ruff.** Expected: PASS and clean. `get_theme_manager` is still used in
  `main()`, so its import stays.
- [ ] **Step 5: Commit** with the message `feat: Fulfilment Tool name, version and logo in title, log and taskbar`.

### Task 11: Remove dead code (Shopify)

**Files:**
- Delete:
  - `S/shopify_tool/barcode_history.py`
  - `S/shopify_tool/sequential_order.py`, `S/tests/test_sequential_order.py`
  - `S/gui/webengine_gate.py`, `S/tests/test_webengine_gate.py`
- Modify: `S/gui_main.py`, deleting the `if "--webengine-gate" in sys.argv:` block in `main()` (about 8 lines with
  its comment).

- [ ] **Step 1: Confirm nothing imports them.** Run
  `grep -rnE "import .*(barcode_history|sequential_order|webengine_gate)|from .*(barcode_history|sequential_order|webengine_gate)" --include=*.py /home/gloopy/Desktop/Projects/shopify-fulfillment-tool/.claude/worktrees/dr-5 | grep -v .venv`.
  - Expected: only `gui_main.py` (the gate block), `tests/test_sequential_order.py` and `tests/test_webengine_gate.py`.
  - Anything else: stop and note it.
- [ ] **Step 2: Delete the files.** Run `/usr/bin/git -C … rm -q <file>` once for each of the five files.
- [ ] **Step 3: Delete the `--webengine-gate` block** from `gui_main.main()`. Check
  `grep -rn "webengine-gate\|webengine_gate" /home/gloopy/Desktop/Projects/shopify-fulfillment-tool/.claude/worktrees/dr-5 --include=*.py --include=*.yml --include=*.md | grep -v "\.venv\|docs/superpowers"`.
  - Expected: no hits in code or workflows.
  - Mentions in `CONTEXT.md` or ADRs may stay; they are history.
- [ ] **Step 4: Run the full suite and ruff.** Expected: PASS.
- [ ] **Step 5: Commit** with the message `chore: remove unused barcode_history, sequential_order and the Phase 9 WebEngine gate`.

### Task 12: Requirements and docs cleanup (Shopify)

**Files:**
- Modify: `S/requirements.txt`, `S/requirements-dev.txt`
- Delete: `S/docs/superpowers/` (except this task's spec and plan) and `S/docs/audit/`

- [ ] **Step 1: Trim the requirements.**
  - `S/requirements.txt`: delete the `xlutils>=…`, `six>=…` and `typing_extensions>=…` lines. Keep everything
    else.
  - `S/requirements-dev.txt`: delete the `# Testing Dependencies (auto-installed by pytest)` heading block and its
    four lines (`iniconfig`, `packaging`, `pluggy`, `altgraph`).
- [ ] **Step 2: Delete the docs in one call**, excluding this task's two files:
  `/usr/bin/git -C /home/gloopy/Desktop/Projects/shopify-fulfillment-tool/.claude/worktrees/dr-5 rm -r -q -- docs/superpowers ":(exclude)docs/superpowers/specs/2026-09-28-repo-cleanup-and-releases-design.md" ":(exclude)docs/superpowers/plans/2026-09-28-repo-cleanup-and-releases-plan.md"`
  - If the guard refuses the pathspec magic, instead run `git rm -r -q docs/superpowers` and then
    `git checkout HEAD -- docs/superpowers/specs/2026-09-28-repo-cleanup-and-releases-design.md docs/superpowers/plans/2026-09-28-repo-cleanup-and-releases-plan.md`.
  - Then run `/usr/bin/git -C … rm -r -q docs/audit`.
  - Check that `ls docs/superpowers/*/` lists exactly those two files.
- [ ] **Step 3: Rebuild and test.**
  1. Run `.venv/bin/pip install -r requirements.txt -r requirements-dev.txt`. It must be a no-op or show only
     already-satisfied packages; the venv is shared, so never uninstall anything.
  2. Run the full suite. Expected: PASS. `tests/audit/` stays; only the reports are deleted.
- [ ] **Step 4: Commit** with the message `chore: drop shipped docs and unused requirements`.

### Task 13: CI workflow, templates, Dependabot (Shopify)

**Files:**
- Replace: `S/.github/workflows/build_release.yml`
- Create:
  - `S/.github/pull_request_template.md`
  - `S/.github/ISSUE_TEMPLATE/bug.yml`, `feature.yml`, `config.yml`
  - `S/.github/dependabot.yml`

**Interfaces:**
- Produces the jobs `Run Tests` and `Check shared/ matches packing-tool (canonical source)`, both required by
  Task 17. Their names stay unchanged.
- Produces the artifact `bundle`.

- [ ] **Step 1: Replace `S/.github/workflows/build_release.yml`** with the file below. The `verify` and
  `shared-sync-check` jobs are copied unchanged from the current file.

```yaml
name: Test, Build and Release

permissions:
  contents: read

on:
  push:
    branches:
      - main
  pull_request:
    branches:
      - main
    # 'labeled' so applying the windows-build label triggers a build on an
    # already-open PR. The default types do not include it.
    types: [opened, synchronize, reopened, labeled]
  # The Release button: Actions -> this workflow -> Run workflow, on main.
  workflow_dispatch:
    inputs:
      bump:
        description: Which part of the version to bump
        type: choice
        options: [patch, minor, major]
        default: patch
      prerelease:
        description: Mark the release as a pre-release
        type: boolean
        default: false

jobs:
  verify:
    name: Run Tests
    runs-on: ubuntu-latest
    steps:
      - name: Check out code
        uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          # Second half: QtWebEngine's runtime (NSS and X client libs), measured
          # with ldd against libQt6WebEngineCore and QtWebEngineProcess, so
          # tests/test_results_bridge.py drives a real Chromium on every PR.
          sudo apt-get update && sudo apt-get install -y libegl1 libpango-1.0-0 libcairo2 libgdk-pixbuf-2.0-0 libnss3 libnspr4 libxcomposite1 libxdamage1 libxrandr2 libxkbfile1 libxtst6 libxkbcommon0 libgbm1 libasound2t64 libxcb-dri3-0
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install -r requirements-dev.txt
      - name: Lint (ruff)
        run: ruff check . --exclude shared
      - name: Smoke test (headless import + construct MainWindow)
        timeout-minutes: 2
        run: CI=1 python run_dev.py
      - name: Run tests
        env:
          QT_QPA_PLATFORM: offscreen
        run: python -m pytest

  shared-sync-check:
    name: Check shared/ matches packing-tool (canonical source)
    runs-on: ubuntu-latest
    steps:
      - name: Check out this repo
        uses: actions/checkout@v4
        with:
          persist-credentials: false
      - name: Check out packing-tool (canonical shared/ source)
        uses: actions/checkout@v4
        with:
          repository: cognitiveghost/packing-tool
          path: packing-tool-ref
          persist-credentials: false
      - name: Diff shared/ against packing-tool/shared/
        run: |
          if ! diff -r shared packing-tool-ref/shared; then
            echo "::error::shared/ has drifted from packing-tool/shared/ (the canonical source). Run scripts/sync_shared.py and commit the result."
            exit 1
          fi

  version:
    name: Next Version
    needs: [verify, shared-sync-check]
    # Releases come from main only. On any other branch this job skips, and
    # so do build and release below.
    if: github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    outputs:
      version: ${{ steps.next.outputs.version }}
    steps:
      - name: Check out code with tags
        uses: actions/checkout@v4
        with:
          fetch-depth: 0
          fetch-tags: true
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Pick the next version from the tags
        id: next
        env:
          BUMP: ${{ inputs.bump }}
        run: |
          version=$(python scripts/release_version.py next "$BUMP")
          echo "version=$version" >> "$GITHUB_OUTPUT"

  build:
    name: Build Executable
    needs: [verify, version]
    runs-on: windows-latest
    # A release (version succeeded), or a PR carrying the windows-build label:
    # Windows-only questions (frozen bundles, RDP) cannot be answered from the
    # Ubuntu dev machine, and the repo is public so the minutes are free.
    # always() because version is skipped on PRs, and a skipped need would
    # otherwise skip this job too.
    if: >-
      always() && needs.verify.result == 'success' && (
        needs.version.result == 'success' ||
        (github.event_name == 'pull_request' &&
         contains(github.event.pull_request.labels.*.name, 'windows-build')))
    env:
      VERSION: ${{ needs.version.outputs.version }}
    steps:
      - name: Check out code
        uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          # PyInstaller is in dev requirements
          pip install -r requirements-dev.txt
      - name: Stamp the release version
        # PR gate builds skip this and say "dev" in the title.
        if: env.VERSION != ''
        run: python scripts/release_version.py stamp shopify_tool/__init__.py $env:VERSION
      - name: Install Pango/GTK runtime (MSYS2)
        shell: cmd
        run: |
          C:\msys64\usr\bin\pacman.exe -S --noconfirm --needed mingw-w64-x86_64-pango
      - name: Build with PyInstaller
        # reportlab.graphics.barcode registers each barcode type (code93,
        # code39, ...) via exec()'d import strings, invisible to PyInstaller's
        # static analysis -- omitting this crashes any frozen build on first
        # barcode import with "ModuleNotFoundError: reportlab.graphics.barcode.code93".
        run: >
          pyinstaller --name FulfilmentTool --onedir --windowed --noconfirm
          --icon shared/assets/brand/fulfilment-tool.ico
          --add-data "shopify_tool/templates;shopify_tool/templates"
          --add-data "shared/assets;shared/assets"
          --add-data "gui/web;gui/web"
          --collect-data blabel
          --collect-submodules reportlab.graphics.barcode
          gui_main.py
      - name: Verify bundled assets shipped
        # A missing shared/assets does not degrade: icon() raises during
        # MainWindow construction, and --windowed means the user double-clicks
        # an exe that silently never opens. This is the only part of the icon
        # work that cannot be tested from the Linux dev machine.
        #
        # QtWebEngineProcess.exe is the same shape of problem for the web tier:
        # PyInstaller's hook-PySide6.QtWebEngineCore is supposed to collect the
        # helper process, and if it silently does not, the only symptom is a
        # dead view discovered over RDP after a 15-minute build and a several-
        # hundred-MB download. Fail here, in the step named for it, instead.
        #
        # qico.dll is Qt's .ico reader: without it brand_icon() loads nothing
        # and the window and taskbar show a blank icon.
        shell: pwsh
        run: |
          foreach ($name in "package.svg", "Inter-Regular.ttf", "QtWebEngineProcess.exe", "results.html", "pikepdf", "fulfilment-tool.ico", "qico.dll") {
            if (-not (Get-ChildItem -Path "dist\FulfilmentTool" -Recurse -Filter $name)) {
              throw "PyInstaller did not bundle $name."
            }
          }
      - name: Bundle GTK DLLs
        shell: pwsh
        run: |
          Copy-Item -Recurse -Path "C:\msys64\mingw64\bin" -Destination "dist\FulfilmentTool\gtk-dlls"
          Copy-Item -Recurse -Path "C:\msys64\mingw64\etc" -Destination "dist\FulfilmentTool\gtk-dlls\etc"
      - name: Report bundle size
        shell: pwsh
        run: |
          $files = Get-ChildItem -Path "dist\FulfilmentTool" -Recurse -File
          $mb = ($files | Measure-Object -Property Length -Sum).Sum / 1MB
          $line = "Frozen bundle: {0:N0} MB across {1:N0} files" -f $mb, $files.Count
          Write-Output $line
          Add-Content -Path $env:GITHUB_STEP_SUMMARY -Value $line
      - name: Zip the bundle
        shell: pwsh
        run: |
          $name = if ($env:VERSION) { "FulfilmentTool-$env:VERSION" } else { "FulfilmentTool-gate" }
          Compress-Archive -Path "dist\FulfilmentTool\*" -DestinationPath "$name.zip"
      - name: Upload the bundle
        uses: actions/upload-artifact@v4
        with:
          name: bundle
          path: FulfilmentTool-*.zip
          # Already a zip; re-compressing several hundred MB buys nothing.
          compression-level: 0

  release:
    name: Publish Release
    # Runs only when version and build both succeeded, i.e. on the Release
    # button. A release made with GITHUB_TOKEN would not trigger another
    # workflow, which is why the build lives in this one.
    needs: [version, build]
    runs-on: ubuntu-latest
    permissions:
      contents: write
      id-token: write
      attestations: write
    env:
      VERSION: ${{ needs.version.outputs.version }}
    steps:
      - name: Download the bundle
        uses: actions/download-artifact@v4
        with:
          name: bundle
      - name: Checksum
        run: sha256sum "FulfilmentTool-$VERSION.zip" > "FulfilmentTool-$VERSION.zip.sha256"
      - name: Attest build provenance
        uses: actions/attest-build-provenance@v2
        with:
          subject-path: FulfilmentTool-${{ needs.version.outputs.version }}.zip
      - name: Create the release
        # Last, so a failed build or attestation leaves no tag behind.
        env:
          GH_TOKEN: ${{ github.token }}
          PRERELEASE: ${{ inputs.prerelease && '--prerelease' || '' }}
        run: >
          gh release create "$VERSION"
          "FulfilmentTool-$VERSION.zip" "FulfilmentTool-$VERSION.zip.sha256"
          --repo "$GITHUB_REPOSITORY" --target "$GITHUB_SHA"
          --title "$VERSION" --generate-notes $PRERELEASE
```

- [ ] **Step 2: Create the templates and Dependabot config** with the same content as Task 5, Steps 2–4, except the
  PR template's lint line reads `ruff check . --exclude shared`:
  - `S/.github/pull_request_template.md`
  - `S/.github/ISSUE_TEMPLATE/bug.yml`
  - `S/.github/ISSUE_TEMPLATE/feature.yml`
  - `S/.github/ISSUE_TEMPLATE/config.yml`
  - `S/.github/dependabot.yml`

  Copy the files from `P` with `cp`, then edit that one line with Edit.
- [ ] **Step 3: Check the YAML parses** as in Task 5, Step 5, with the Shopify paths.
- [ ] **Step 4: Commit** with the message `ci: Release button, FulfilmentTool bundle with logo, templates and Dependabot`.

### Task 14: README and CLAUDE.md (Shopify)

**Files:** Replace `S/README.md`; modify `S/CLAUDE.md`.

- [ ] **Step 1: Replace `S/README.md`** with:

````markdown
# Fulfilment Tool

Windows desktop app (PySide6) that turns a Shopify orders export and a stock export into a fulfilment plan: which
orders can ship, packing lists per courier, stock write-offs and labels. It works against a shared Windows file
server (`Clients/`, `Sessions/`, `Stats/`, `Logs/`), so several warehouse PCs share one set of data. Its sessions
are packed on the floor with [Packer Assistant](https://github.com/cognitiveghost/packing-tool).

## Download

Take the latest zip from [Releases](https://github.com/cognitiveghost/shopify-fulfillment-tool/releases), unzip it
and run `FulfilmentTool.exe`. The version is in the window title.

To check a download was built by this repo's CI:

```bash
gh attestation verify FulfilmentTool-<version>.zip -R cognitiveghost/shopify-fulfillment-tool
```

or compare it against the `.sha256` file attached to the same release.

## Run from source

Python 3.14 on the dev machine; CI and release builds use 3.11.

```bash
git clone https://github.com/cognitiveghost/shopify-fulfillment-tool.git
cd shopify-fulfillment-tool
./scripts/setup_venv.sh          # creates .venv and the VS Code config
.venv/bin/python gui_main.py     # production share, or FULFILLMENT_SERVER_PATH if set
.venv/bin/python run_dev.py      # a local dev-server/ folder instead
```

## Test and lint

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
.venv/bin/ruff check . --exclude shared
```

CI runs both, plus a headless start-up smoke test, on every PR. Label a PR `windows-build` to also get a frozen
Windows build of it as a workflow artifact.

## Release

Actions → **Test, Build and Release** → **Run workflow** on `main`, then pick `patch`, `minor` or `major`. CI
tests, takes the next version from the tags, builds, attests, and publishes the release with generated notes.

Do not create releases by hand in the GitHub UI: nothing builds for them.

## Layout

- `gui/`: Qt UI; `gui/web/` is the results document (QtWebEngine)
- `shopify_tool/`: analysis, rules, sessions, outputs, labels
- `shared/`: synced from packing-tool; never edit it here (see `CLAUDE.md`)
- `docs/adr/`: decisions; `CONTEXT.md`: the domain glossary

## License

Proprietary, for internal warehouse operations.
````

- [ ] **Step 2: Edit `S/CLAUDE.md`.**
  1. Delete line 6, `Current version: **1.9.9.1** (pre-release).`
  2. In the Shared Module section, replace
     `the canonical source (see `packing-tool/docs/superpowers/specs/2026-07-25-shared-unification-design.md`).`
     with `the canonical source.`
  3. Replace the whole `## Version Management` section, from its heading down to (not including) `## DO NOT`, with:

```markdown
## Releases

The git tag is the version. In the repo `shopify_tool/__init__.py` holds `__version__ = "dev"`; the release build
stamps the tag into it (`scripts/release_version.py`). Never hand-edit `__version__` or write a version into docs.
To release: Actions → Test, Build and Release → Run workflow on `main` → pick the bump. Never create a release in
the GitHub UI — nothing builds for it.

```

  4. Under `### Domain docs`, after the `Single-context: …` line, add a blank line and:

```markdown
Doc paths cited in code comments that no longer exist (shipped specs, plans, audits) are in git history:
`git log --all -- <path>`.
```

- [ ] **Step 3: Commit** `README.md` and `CLAUDE.md` with the message `docs: README and CLAUDE.md match the repo as it is`.

### Task 15: Gate, push, PR (Shopify)

- [ ] **Step 1: Run the gate** in `S`:
  - `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` must PASS.
  - `.venv/bin/ruff check . --exclude shared` must be clean.
  - `CI=1 .venv/bin/python run_dev.py` must print `Offscreen application initialized successfully.`
- [ ] **Step 2: Check settings keys are untouched.** Run `/usr/bin/git -C … diff origin/main -G "QSettings\(" --stat -- gui gui_main.py shopify_tool`.
  Expected: no output.
- [ ] **Step 3: Check the version lives in one place.** Run
  `grep -rn "1\.9\.9\.1\|__version__ =" --include=*.py --include=*.md /home/gloopy/Desktop/Projects/shopify-fulfillment-tool/.claude/worktrees/dr-5 | grep -v "\.venv\|docs/superpowers"`.
  - Expected hits:
    - `shopify_tool/__init__.py:… __version__ = "dev"`;
    - `shared/__init__.py`, the shared-module version, which is out of scope;
    - the pattern strings inside `scripts/release_version.py` and `tests/test_release_version.py`.
  - Nothing else.
- [ ] **Step 4: Update the graph and push.** Run `graphify update .`, then
  `/usr/bin/git -C … push`.
- [ ] **Step 5: Open the PR.**
  - Title: `chore: Fulfilment Tool 2.0 groundwork — Release button, logo, cleanup`.
  - Body (via `--body-file`):
    - a summary per task;
    - a link to the packing-tool PR;
    - "`Check shared/ matches packing-tool` fails until the packing-tool PR merges; re-run it after";
    - "After both merge: Run workflow → `major` in each repo gives 2.0.0";
    - the 🤖 line.
  - Command: `gh pr create -R cognitiveghost/shopify-fulfillment-tool --base main --head dr/5-chore-clean-up-both-repos-shopify-tool-p --title … --body-file <file> --label windows-build`
- [ ] **Step 6: Wait for CI.** Run `gh pr checks <n> -R cognitiveghost/shopify-fulfillment-tool --watch`.
  - Expected: `Run Tests` and `Build Executable` pass, and `Check shared/…` fails for the reason above.
  - Any other failure: fix it if it is this plan's mistake; otherwise note it and stop.

---

# Part C — repository settings (both repos)

### Task 16: Dependabot alerts and security updates

- [ ] **Step 1: Turn on vulnerability alerts** for each repo, one call each:
  - `gh api -X PUT repos/cognitiveghost/packing-tool/vulnerability-alerts`
  - `gh api -X PUT repos/cognitiveghost/shopify-fulfillment-tool/vulnerability-alerts`
- [ ] **Step 2: Turn on automated security fixes:**
  - `gh api -X PUT repos/cognitiveghost/packing-tool/automated-security-fixes`
  - `gh api -X PUT repos/cognitiveghost/shopify-fulfillment-tool/automated-security-fixes`
- [ ] **Step 3: Verify.** Run `gh api repos/cognitiveghost/<repo> --jq .security_and_analysis.dependabot_security_updates.status`
  for each repo. Expected: `enabled`.

### Task 17: `main` ruleset

- [ ] **Step 1: Check for an existing ruleset** with `gh api repos/cognitiveghost/<repo>/rulesets` for each repo.
  If one named `main` exists, stop and note it; do not create a duplicate.
- [ ] **Step 2: Write `ruleset-packing.json`** to your job tmp dir:

```json
{
  "name": "main",
  "target": "branch",
  "enforcement": "active",
  "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
  "bypass_actors": [{"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"}],
  "rules": [
    {"type": "deletion"},
    {"type": "non_fast_forward"},
    {"type": "pull_request", "parameters": {
      "required_approving_review_count": 0,
      "dismiss_stale_reviews_on_push": false,
      "require_code_owner_review": false,
      "require_last_push_approval": false,
      "required_review_thread_resolution": false}},
    {"type": "required_status_checks", "parameters": {
      "strict_required_status_checks_policy": false,
      "required_status_checks": [{"context": "Run Tests"}]}}
  ]
}
```

- [ ] **Step 3: Write `ruleset-shopify.json`.** It is the same, except `required_status_checks` is:

```json
[{"context": "Run Tests"}, {"context": "Check shared/ matches packing-tool (canonical source)"}]
```

- [ ] **Step 4: Create both rulesets:**
  - `gh api -X POST repos/cognitiveghost/packing-tool/rulesets --input <tmp>/ruleset-packing.json`
  - `gh api -X POST repos/cognitiveghost/shopify-fulfillment-tool/rulesets --input <tmp>/ruleset-shopify.json`

  Expected: JSON with an `id` for each.
- [ ] **Step 5: Verify.** Run `gh api repos/cognitiveghost/<repo>/rules/branches/main --jq '.[].type'` for each
  repo. Expected: `deletion`, `non_fast_forward`, `pull_request` and `required_status_checks`.

## After this plan

This part is for the owner, not the implementer:
1. Merge the packing-tool PR, then re-run the Shopify PR's `Check shared/…` and merge it.
2. Actions → Test, Build and Release → Run workflow → `major` in each repo. That produces `2.0.0` for both.
3. Point warehouse shortcuts at `FulfilmentTool.exe` / `PackerAssistant.exe`.
4. Deleting this spec and plan is a follow-up; the next task can bundle it.
