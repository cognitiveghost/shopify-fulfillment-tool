# Repo cleanup, versioning and releases (both repos)

Task: dev-runner run 8, Todoist 6hfQgHX8VJ28m6xv, "chore: clean up both repos".
Covers `shopify-fulfillment-tool` (this repo) and `packing-tool`. Two PRs, packing-tool first.

## Why

- **The version in the code is invented.** `shopify_tool/__init__.py`, `gui_main.py`, `README.md` and `CLAUDE.md`
  all say `1.9.9.1`; the latest release is `1.9.11.0`. packing-tool has no app version in code; its README says
  `1.3.2.0`; the latest release is `1.3.10.2`. No window, dialog or log shows a version. The Shopify window title
  still reads "Shopify Fulfillment Tool - New Architecture".
- **Releases are hand-typed.** The owner makes a release in the GitHub UI with a 4-part tag (`1.3.2.0.2` exists).
  CI then builds and attaches the zip.
- **The docs are mostly shipped history.** Shopify has 49 plans, 42 specs and 6 audits; packing-tool has
  15 plans/specs, 3 audits and the `docs/design/phase10` mockup. Both READMEs are wrong: they say "no tests"
  (there are 144 and 62 test files), clone from the old `cognitiveclodfr` org, and name the wrong Python and version.
- **The two repos' CI has drifted.** packing-tool runs its tests only on Windows, triggers on `master`/`develop`,
  and builds on `release: published` where Shopify uses `created`.
- **GitHub has no templates, Dependabot config or branch protection.** Both repos are public, so the dependency
  graph is already on.

## Decisions (owner answers, run 8, questions 8–10)

| Topic | Decision |
|---|---|
| Release automation | A **Release button**: `workflow_dispatch` with `bump` = patch/minor/major and `prerelease`. |
| Numbering | **SemVer**. Both repos' first clean release is **2.0.0**. |
| Docs | Delete `docs/superpowers/` and `docs/audit/` in both repos, plus packing-tool's `docs/design/phase10/`. Keep `docs/adr/`, `docs/agents/`, `CONTEXT.md`. |
| GitHub extras | PR template, issue forms, Dependabot, and a `main` ruleset. All four. |
| Logos | Claude draws them: a Lucide glyph on a coloured rounded tile. |
| Signing | **Attestation only**: GitHub build provenance and a SHA256 per zip. No code-signing certificate. |
| Names | "**Fulfilment Tool**" and "**Packer Assistant**", in titles, README, and the exe and zip names. |

## 1. Version and release

**One source: the git tag.** In the repo, each app package holds `__version__ = "dev"`:

- `shopify_tool/__init__.py`. Also delete the `Version: 1.9.9.1` docstring line there, and the duplicate
  `__version__` in `gui_main.py`.
- `packing_tool/__init__.py`, as a new line.

The release build rewrites that one line to the release number before PyInstaller runs. Nothing else in either
repo carries the app version. The version lines in both READMEs and CLAUDE.md are deleted, along with Shopify
CLAUDE.md's "Version Management" section.

**Where the version shows:**
- The main window title: `Fulfilment Tool 2.0.0` / `Packer Assistant 2.0.0`, or `… dev` when run from source.
- One startup log line.
- packing-tool's lock files: `SessionLockManager.app_version` becomes `__version__` instead of the hardcoded
  `"1.3.0"`. Nothing reads that field; it only records who held the lock.

**Leave these alone.** The `"1.3.0"` strings in packing-tool's `packer_logic.py`, `worker_manager.py`,
`main_window.py` and `session_history_manager.py` are **data-format versions** of JSON files the two apps
exchange, not the app version. The same goes for `shared/__init__.py`'s `__version__ = '2.0.0'` and
`REGISTRY_VERSION`.

**`scripts/release_version.py`** is one small file, identical in both repos. It is not in `shared/`, because
`shared/` is bundled into the app. It has two functions:

- `next_version(tags, bump) -> str`: takes the newest tag (by date) of the form `\d+(\.\d+){2,}`, reads its
  first three numbers, and bumps it. Newest, not highest: 2025's tags go up to `12.1.9` (Shopify) and `5.0.0`
  (packing), older than the 1.x line. With no matching tag it starts from `0.0.0`. It raises if the result is
  already a tag. `major` on `1.9.11.0` gives `2.0.0`; `patch` gives `1.9.12`. `1.3.2.0.2` reads as `(1,3,2)`.
- `stamp(path, version)`: replaces the single `__version__ = "…"` line, and raises unless exactly one line matched.
  A missed stamp would otherwise ship a "dev" build silently.

It has a CLI: `python scripts/release_version.py next <bump>` prints the version, and
`python scripts/release_version.py stamp <file> <version>` rewrites the file. Tests import it as
`scripts.release_version`: `python -m pytest` puts the repo root on `sys.path`, and packing-tool's `pytest.ini`
has `pythonpath = .`.

**The workflow.** Each repo keeps its one workflow file, and the Release button is a new trigger on it:
- `on.workflow_dispatch.inputs`: `bump` is a choice (patch/minor/major, default patch); `prerelease` is a boolean
  (default false).
- The `release:` trigger is removed. A release made by hand in the GitHub UI now builds nothing, and the README says
  so.
- Jobs on a dispatch, in order:
  1. The existing test job (plus `shared-sync-check` in Shopify).
  2. **version** (ubuntu): only from `refs/heads/main`. Checks out with full history and tags, then runs
     `next_version`.
  3. **build** (windows): runs `stamp` on the package `__init__.py`, then PyInstaller. The build also runs for a
     PR that carries the `windows-build` label; that build is not stamped, so its title reads `dev`.
  4. **release** (ubuntu): downloads the zip, writes `<zip>.sha256`, runs `actions/attest-build-provenance` on the
     zip, then runs `gh release create <v> <zip> <zip>.sha256 --target <sha> --title <v> --generate-notes`, adding
     `--prerelease` when asked. The release is created last, so a failed build leaves no tag.
- Why one workflow and not a separate `release.yml` fired by the `release` event: a release created with
  `GITHUB_TOKEN` does not trigger other workflows.
- Tags stay unprefixed (`2.0.0`), as the existing tags are.

## 2. Names, titles, logos

**Display names:**
- "Shopify Fulfillment Tool" becomes "Fulfilment Tool" (the owner's spelling, one *l*).
- "Packer's Assistant" becomes "Packer Assistant".
- Only user-visible strings change: window titles, packing's argparse description, the exe and zip names, and the
  README title. Docstrings and comments that name the other app ("Shopify Tool", "Packing Tool") stay as they are.

**Artifacts:**

| | exe | release zip | PR gate zip |
|---|---|---|---|
| Shopify | `FulfilmentTool.exe` (dir `dist\FulfilmentTool`) | `FulfilmentTool-2.0.0.zip` | `FulfilmentTool-gate.zip` |
| packing | `PackerAssistant.exe` (dir `dist\PackerAssistant`) | `PackerAssistant-2.0.0.zip` | `PackerAssistant-gate.zip` |

**These do not change:**
- repo names and Python package names;
- every `QSettings(...)` organisation/application string (`ShopifyFulfillmentTool`/`FulfillmentApp`, `PackingTool`/…),
  so nobody loses saved theme, geometry or client settings;
- `config.ini` handling.

**Logos** live in `shared/assets/brand/`. They are edited in packing-tool (the canonical `shared/`) and synced to
Shopify:
- `fulfilment-tool.svg` / `.ico`: Lucide `package`, white stroke, on a `#006FBA` rounded tile (`accent_fill`,
  identical in both themes).
- `packer-assistant.svg` / `.ico`: Lucide `scan-barcode`, white stroke, on a `#2C6630` rounded tile (light-theme
  `accent_green`), so the two apps differ in the taskbar.
- **SVG shape:** `viewBox="0 0 24 24"`, a `rect` of the full 24×24 with `rx="5"` filled with the tile colour, and
  the glyph paths inside `<g transform="translate(4.5 4.5) scale(0.625)" stroke="#FFFFFF" stroke-width="2.4" …>`.
  The glyph then fills 15 of 24 units.
- **`.ico`:** rendered from the SVG once, with QSvgRenderer, at 16, 24, 32, 48 and 256 px, and packed with Pillow.
  The script is throwaway and not committed; only the files are.
- **Window icon:** a new `brand_icon(name) -> QIcon` in `shared/icons.py` returns `QIcon(str(BRAND_DIR / f"{name}.ico"))`.
  A probe confirmed that Qt reads every size from a multi-size `.ico`.
  - Shopify's `gui_main.build_app_icon()` returns `brand_icon("fulfilment-tool")`.
  - packing's `main.py` calls `app.setWindowIcon(brand_icon("packer-assistant"))`.
- **Exe icon:** the same `.ico`, given to PyInstaller as `--icon` in Shopify and `icon=` in packing's `main.spec`.
- **Bundle check:** loading `.ico` needs Qt's `qico` imageformat plugin in the frozen build, so the CI "Verify
  bundled assets" step also checks for `qico.dll`.
- `shared/assets/README.md` gains a `brand/` section saying the glyphs are Lucide 1.31.0 (ISC), under the same
  licence as `icons/`.

## 3. Cleanup

**Docs.** Delete `docs/superpowers/` and `docs/audit/` in both repos, and packing-tool's `docs/design/`.
- **Exception:** this spec and its plan stay until this task's PR merges, because the runner's later stages read
  them.
- About 75 code comments cite deleted doc paths (some were already dead). They stay as they are, and each
  CLAUDE.md gains one line: "Doc paths cited in code comments that no longer exist are in git history:
  `git log --all -- <path>`."
- `AUDIT-*` test names keep their IDs.

**Dead code (Shopify):**
- `shopify_tool/barcode_history.py`: nothing imports it.
- `shopify_tool/sequential_order.py` and `tests/test_sequential_order.py`: only its own test imports it.
- `gui/webengine_gate.py`, `tests/test_webengine_gate.py`, and the `--webengine-gate` branch in `gui_main.main()`.
  That is the Phase 9 build gate, marked "Deleted when the gate closes". The phase has shipped. Chromium stays in
  the bundle through `gui/ui_manager.py`'s static QtWebEngine import, and the CI step still checks for
  `QtWebEngineProcess.exe`.

**Dependencies:**
- **Shopify `requirements.txt`:** drop `xlutils`, `six` and `typing_extensions`. Nothing in the code names them;
  `six` still arrives transitively. Keep `xlrd`, `xlsxwriter`, `pytz`, `python-dateutil` and `tzdata`, which pandas
  uses by engine name or at runtime.
- **Shopify `requirements-dev.txt`:** drop the transitive `iniconfig`, `packaging`, `pluggy` and `altgraph`.
- **packing `requirements.txt`:** keeps `PySide6`, `pandas` and `openpyxl`. `pyinstaller` moves to
  `requirements-dev.txt`, which already holds `pytest`, `pytest-qt` and `ruff~=0.16.0`. The build job installs
  both files.

**Files that should not be tracked (packing):** untrack `.claude/settings.local.json` and add
`.claude/settings.local.json` to `.gitignore`. `config.ini` stays tracked, because the app reads it as its
production default.

**READMEs.** Both are rewritten to be short and true:
- what the app does, in a few lines;
- run from source (`scripts/setup_venv.sh` for Shopify; `python main.py` / `run_dev.py` for packing);
- tests (`QT_QPA_PLATFORM=offscreen python -m pytest`) and lint;
- how to release (Actions → the workflow → Run workflow → bump), and a note not to make releases in the GitHub UI;
- how to verify a download (`gh attestation verify <zip> -R cognitiveghost/<repo>`, or compare the `.sha256`);
- Python 3.14 for development and 3.11 for CI and release builds;
- org `cognitiveghost`;
- no version line and no "Last Updated" line.

**CLAUDE.md, both repos:**
- Drop the version facts (Shopify line 6 and the "Version Management" section; packing's "Version per README.md:3").
- Add a short "Releases" section: git tag is the version, via the Release button; never hand-edit `__version__`.
- Replace packing's dead `2026-07-25-shared-unification-design.md` citation (in both CLAUDE.md files) with the
  git-history line.

## 4. CI and GitHub

**packing-tool's workflow matches Shopify's shape:**
- A `verify` job named **"Run Tests"** on ubuntu-latest, Python 3.11, with the same apt line as Shopify for the
  QtWebEngine runtime. It runs `pip install -r requirements.txt -r requirements-dev.txt`, `ruff check .` (packing
  lints `shared/`, because it owns it), `python -c "import main"`, and `python -m pytest` with
  `QT_QPA_PLATFORM=offscreen`.
- Triggers: push to `main`, PRs to `main` (types opened/synchronize/reopened/labeled), and `workflow_dispatch`.
- The Windows build runs on dispatch, or on a PR labelled `windows-build`. That label is created in packing-tool.
- The old `py_compile` step goes: ruff and pytest already cover it.

**New files in both repos:**
- `.github/pull_request_template.md`: What / Why / How tested (checkboxes: tests, ruff, `windows-build` run if the
  bundle is touched) / Release note (one line or "none").
- `.github/ISSUE_TEMPLATE/bug.yml`: what happened, expected, steps, app version (the title bar), which PC/client.
  `feature.yml`: problem, proposal. `config.yml`: `blank_issues_enabled: true`.
- `.github/dependabot.yml`: `pip` and `github-actions`, both weekly, each grouped into a single PR.

**Repo settings**, applied with `gh api` by the implementer (outward-facing; approved in the design):
- `PUT /repos/{r}/vulnerability-alerts` and `PUT /repos/{r}/automated-security-fixes` on both repos.
- A ruleset named `main` on both repos, targeting the default branch:
  - requires a pull request (0 approvals);
  - requires the status checks: **"Run Tests"** on both repos, plus
    **"Check shared/ matches packing-tool (canonical source)"** on Shopify;
  - blocks non-fast-forward pushes and deletion;
  - bypass: RepositoryRole admin (id 5), mode `always`, so the owner can still merge in an emergency.

## 5. Testing

- **`tests/test_release_version.py`, in both repos:**
  - `next_version` cases: major from 4-part, patch from 4-part, 5-part tag, no tags, non-version tags ignored,
    already-existing tag raises.
  - `stamp` cases: rewrites the one line; raises on zero matches.
  - The real package `__init__.py` contains exactly one `__version__ = "dev"` line, so the stamp in CI cannot no-op.
- **Title tests:** the main window's title is `f"{APP_NAME} {__version__}"`. Shopify reuses an existing
  `MainWindow()` test pattern (e.g. `tests/test_first_run.py`); packing uses `tests/test_shell.py`'s `window`
  fixture.
- **Icon tests:**
  - `brand_icon()` for each name is non-null, and its sizes include 16, 32, 48 and 256.
  - Shopify's two `build_app_icon` tests in `tests/test_gui_main_env_setup.py` are rewritten to that: the old
    single-colour assertion no longer holds, because the tile has a white glyph.
  - `test_ui_assets.py` in both repos checks that the four brand files exist.
- **Gate, per repo:** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` and `ruff check .`
  (Shopify: `--exclude shared`).
- **Windows proof:** each PR gets the `windows-build` label. The run must pass its asset check, including
  `qico.dll`. The owner opens the gate zip over RDP to confirm the icon and title; that is the one check Linux
  cannot make.
- The first real release (2.0.0, `bump=major`) is the owner's to press after both PRs merge.

## Order and cross-repo coupling

1. **packing-tool PR** first. It carries the brand assets and `brand_icon()` in `shared/`.
2. **Shopify PR** next. It runs `scripts/sync_shared.py /home/gloopy/Desktop/Projects/packing-tool/.claude/worktrees/dr-5`
   to pull those in. Its `shared-sync-check` job fails until the packing PR merges; that is expected, and the PR
   body says so.
3. **Repo settings last.** Once rulesets exist, both PRs need a green "Run Tests" to merge. That check name is
   produced by each PR's own run.

## Departures from the chat design

- The chat design deleted this task's own spec and plan in the final PR. They now stay until merge, because the
  runner's later stages read them. Deleting them is a follow-up the owner can bundle into the next task.
