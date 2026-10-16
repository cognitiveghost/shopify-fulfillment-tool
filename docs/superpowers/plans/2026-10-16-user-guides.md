# User Guides Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Two end-user guides, one for Fulfilment and one for Packing Tool, each in EN and BG. They are Markdown with
scripted screenshots, share one PDF build and stylesheet, and both apps get a **User guide** ⋯ menu item (and F1)
that opens the PDF from the server.

**Architecture:** `shared/guide/` (canonical in Fulfilment, synced to packing-tool) holds the PDF build, the
stylesheet, the writing conventions and the Help opener. A Fulfilment script seeds a throwaway server folder from
the anonymised replay fixtures. A render script in each repo drives the real app against a temp copy of that folder
and writes PNGs into `docs/user-guide/img/<lang>/`. The guides are `docs/user-guide/en.md` and `bg.md` in each repo.

**Tech Stack:** PySide6 / QtWebEngine (offscreen renders), Python-Markdown (new, dev-only), WeasyPrint (existing),
pytest + pytest-qt.

**Spec:** `docs/superpowers/specs/2026-10-16-user-guides-design.md` (Fulfilment repo, this branch). Read it first,
especially sections 3 (style and conventions), 5–7 (screens and outlines) and 10 (Help entry).

**Worktrees:**
- Fulfilment (tasks 1–8): `/home/gloopy/Desktop/Projects/shopify-fulfillment-tool/.claude/worktrees/dr-35`.
- Packing Tool (tasks 9–12): `/home/gloopy/Desktop/Projects/packing-tool/.claude/worktrees/dr-35`.
- Both are on branch `dr/35-shared-packer-tool-user-guides-for-shopi`.

## Global Constraints

- Gate per repo: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`, then `ruff check .`. Run `graphify update .`
  after code changes in Fulfilment.
- Git: `/usr/bin/git`, one plain command per Bash call, and commit with `git commit -F <absolute message file>`.
  Messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Push the branch after each task.
- Never hand-edit `packing-tool/shared/`. Sync it with packing-tool's `scripts/sync_shared.py`.
- UI strings go through `_()` from `shared.i18n`, with the Bulgarian added to the catalogue (ADR 0021). The Help
  strings go in the **shared** catalogue `shared/assets/locales/bg.json`.
- No customer PII in either repo; both are public. The only data source is `tests/replay/fixtures/`. Never read
  `~/Desktop/Server./` or `~/Desktop/production info/`.
- Render scripts redirect both `QSettings.Format.NativeFormat` and `IniFormat` to a temp dir before any app import,
  and only ever point the app at a folder under `tempfile.gettempdir()`.
- Screenshots: light theme, 1366×768, whole window unless a dialog alone is clearer. Image names are identical in
  EN and BG; only the folder differs.
- `markdown` and `weasyprint` are imported inside functions in `shared/guide/build.py` only. `shared/guide/help.py`
  must not import `build.py`.
- PDFs are build output: `docs/user-guide/*.pdf` is gitignored and never committed.
- No hardcoded colours in Qt code. The guide CSS takes its colours from `shared.theme.LIGHT_THEME` at build time.

## Review Focus

1. The guide PDF is missing on the server, or the server is unreachable. **User guide** shows a warning naming the
   expected folder and never raises (task 1 test `test_open_guide_missing_warns`).
2. The app runs in BG but only `<app>-en.pdf` is on the server. The English file opens (task 1 test
   `test_guide_pdf_falls_back_to_en`).
3. A guide references an image that is not there, for example after a rename in the render script. The build stops
   and names the file (task 3 test `test_missing_image_raises`), and the integrity test fails in CI (tasks 6, 12).
4. `bg.md` drifts from `en.md`, with a section or a screenshot missing. The parity test fails (tasks 7, 12).
5. A seed or render is pointed at a non-empty or non-temp folder, such as the real server. It refuses (task 4 test
   `test_refuses_non_empty_dest`; task 5 and task 10 guard step).

---

## Fulfilment repo

### Task 1: Help opener in `shared/guide/help.py`

**Files:**
- Create: `shared/guide/__init__.py` (empty), `shared/guide/help.py`
- Modify: `shared/assets/locales/bg.json` (two entries)
- Test: `tests/test_guide_help.py`

**Interfaces:**
- Produces: `guide_pdf(server_root: str | Path, app: str) -> Path | None` and
  `open_guide(parent: QWidget | None, server_root: str | Path, app: str) -> None`. `app` is `"fulfilment"` or
  `"packing-tool"`. The files are named `<server_root>/Guides/<app>-<lang>.pdf`.

- [ ] **Step 1: Write the failing tests** in `tests/test_guide_help.py`:
  - `test_guide_pdf_language_file`: `tmp_path/Guides/fulfilment-bg.pdf` exists and the language is `bg` (set
    through `shared.i18n.set_language("bg", i18n.catalogue_files(ROOT, "bg"))`; restore `en` in a `finally` or
    fixture). The function returns that path.
  - `test_guide_pdf_falls_back_to_en`: only `fulfilment-en.pdf` exists and the language is `bg`. The function
    returns the EN path.
  - `test_guide_pdf_none_when_missing`: there is no `Guides/` folder, and the function returns `None`.
  - `test_open_guide_opens_file`: monkeypatch `QDesktopServices.openUrl`. It is called once with
    `QUrl.fromLocalFile(str(path))`.
  - `test_open_guide_missing_warns`: monkeypatch `QMessageBox.warning`. It is called once, the message contains
    `str(Path(server_root) / "Guides")`, and `openUrl` is not called.
- [ ] **Step 2: Run** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_guide_help.py -q`. Expected:
  FAIL (module missing).
- [ ] **Step 3: Implement `shared/guide/help.py`.** The guide language is `shared.i18n.language()`. The warning title
  is `_("User guide")` and its text is `_("The user guide was not found in {folder}.", folder=...)`. Add to
  `shared/assets/locales/bg.json`:
  - `"User guide": "Ръководство"`
  - `"The user guide was not found in {folder}.": "Ръководството не е намерено в {folder}."`
  Keep the file's existing key order and style.
- [ ] **Step 4: Run** the tests again, and also `tests/test_i18n_catalogue.py`. Expected: PASS.
- [ ] **Step 5: Commit** "Help opener for the user guide (shared/guide/help.py)", then push.

### Task 2: Fulfilment ⋯ menu item and F1

**Files:**
- Modify: `gui/ui_manager.py` `_populate_overflow` (~line 388) and the main-window shortcut setup (find where Ctrl+1…5
  are bound, with `rg -n "QShortcut" gui/`)
- Modify: `gui/shortcuts_dialog.py`, adding a row for F1 if the dialog lists global shortcuts
- Test: `tests/test_shell.py` (add to it; it already tests the overflow menu)

**Interfaces:**
- Consumes: `open_guide(parent, server_root, app)` from task 1.

- [ ] **Step 1: Write the failing test** `test_overflow_has_user_guide`: build the main window the way the
  existing overflow tests in `tests/test_shell.py` do. Monkeypatch `gui.ui_manager.open_guide` (import it into
  `ui_manager` by name) to record calls. Find the action whose text is `"User guide"` in the overflow menu,
  `trigger()` it, and assert one call with
  `(main_window, str(main_window.profile_manager.base_path), "fulfilment")`. Also assert that the item comes
  directly before the "Server connection…" item.
- [ ] **Step 2: Run** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_shell.py -q`. Expected: the
  new test FAILs.
- [ ] **Step 3: Implement.** Add `menu.add_item(_("User guide"), self._open_user_guide)` in the "THIS PC" section,
  before "Server connection…". `_open_user_guide` calls
  `open_guide(self.mw, str(self.mw.profile_manager.base_path), "fulfilment")`. Bind
  `QShortcut(QKeySequence("F1"), self.mw)` to the same method. If `ShortcutsDialog` lists shortcuts, add an F1 row
  labelled `_("User guide")`.
- [ ] **Step 4: Run** the full gate. Expected: PASS.
- [ ] **Step 5: Commit** "User guide in the ⋯ menu and on F1", then push.

### Task 3: PDF build, stylesheet and writing conventions

**Files:**
- Create: `shared/guide/build.py`, `shared/guide/guide.css`, `shared/guide/README.md`
- Modify: `requirements-dev.txt` (add `markdown>=3.7  # user guide build (shared/guide/build.py)`), `.gitignore`
  (add `docs/user-guide/*.pdf`)
- Test: `tests/test_guide_build.py`

**Interfaces:**
- Produces:
  - `build_html(md_path: Path) -> str`, a full HTML document.
  - `build_pdf(md_path: Path, out: Path | None = None) -> Path`. The default `out` is `md_path.with_suffix(".pdf")`.
  - CLI: `.venv/bin/python -m shared.guide.build <guide.md> [--out <file.pdf>]`.

- [ ] **Step 1: Install** with `.venv/bin/python -m pip install "markdown>=3.7"`.
- [ ] **Step 2: Write the failing tests** in `tests/test_guide_build.py`. Each writes a tiny guide into `tmp_path`:
  `# Title\n\n## Part\n\n![Cap](img/en/a.png)\n`, plus a real 4×4 PNG made with `QImage(4, 4, ...).save(...)`.
  - `test_build_pdf_writes_pdf`: the output file's bytes start with `b"%PDF"`.
  - `test_missing_image_raises`: with the PNG deleted, `build_pdf` raises `FileNotFoundError`, and the message
    contains `img/en/a.png`.
  - `test_html_uses_theme_colours`: `build_html` contains `LIGHT_THEME.accent_fill` and `LIGHT_THEME.text`
    (`from shared.theme import LIGHT_THEME`).
  - `test_html_has_title_and_toc`: the HTML contains `<title>Title</title>` and an element with class `toc`.
- [ ] **Step 3: Run** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_guide_build.py -q`. Expected:
  FAIL.
- [ ] **Step 4: Implement `build.py`.**
  - `markdown.markdown(text, extensions=["extra", "toc", "sane_lists"])`. Insert the TOC with the `toc` extension's
    `[TOC]` marker, or use `md.toc`, in a `<nav class="toc">`.
  - The title is the first `# ` line. The cover shows the title, the language (the file stem), today's date, and
    `git rev-parse --short HEAD` when available (ignore failures).
  - Check every `<img src>` relative to `md_path.parent` before rendering. Raise `FileNotFoundError` naming the src.
  - The CSS is `guide.css` text with a `:root { --accent: …; --text: …; --text-secondary: …; --border: …;
    --surface-sunken: … }` block in front. The values come from `LIGHT_THEME` fields `accent_fill`, `text`,
    `text_secondary`, `border_subtle` and `surface_sunken`.
  - Use `weasyprint.HTML(string=html, base_url=str(md_path.parent)).write_pdf(out)`.
- [ ] **Step 5: Write `guide.css`** to spec section 3:
  - A4 `@page` with margins and a footer `counter(page)`, plus a running header with the title. The cover page has
    none.
  - Body about 11pt sans-serif.
  - `h2 { break-before: page }`.
  - `img` at full width with `1px solid var(--border)` and `break-inside: avoid`. A `figure`/caption style; the
    `extra` extension puts the alt text in `alt`, so show the caption with a `p:has(img)` rule or a small
    post-processing step in `build_html` that wraps each image in `<figure>` with a `<figcaption>` taken from its alt.
  - Blockquote admonitions with a left border in `var(--accent)`.
  - The CSS uses only `var(--…)` colours and no literal hex.
- [ ] **Step 6: Write `shared/guide/README.md`.** It covers how to edit a guide (any editor or the GitHub web
  editor), the writing conventions (spec section 3, copied as a list), how to re-render the screenshots (the two
  render commands), and how to build the four PDFs and where they go on the server:
  ```
  .venv/bin/python -m shared.guide.build docs/user-guide/en.md --out "<server>/Guides/fulfilment-en.pdf"
  .venv/bin/python -m shared.guide.build docs/user-guide/bg.md --out "<server>/Guides/fulfilment-bg.pdf"
  # in packing-tool: same with packing-tool-en.pdf / packing-tool-bg.pdf
  ```
  It also says that **User guide** (F1) in each app opens `Guides/<app>-<language>.pdf` and falls back to English.
- [ ] **Step 7: Run** the tests and the gate. Expected: PASS.
- [ ] **Step 8: Commit** "Shared user-guide build and stylesheet (shared/guide)", then push.

### Task 4: Seed a guide server folder from the replay fixtures

**Files:**
- Create: `scripts/build_guide_server.py`
- Test: `tests/test_build_guide_server.py`

**Interfaces:**
- Produces: `build(dest: Path) -> None` and CLI `.venv/bin/python scripts/build_guide_server.py <dest>`. The result
  is a server-layout folder:
  - `Clients/CLIENT_ALMA/` and `Clients/CLIENT_HERBAR/`, each with `client_config.json`, `shopify_config.json` and
    `packer_config.json`.
  - `Sessions/CLIENT_<id>/<session>/`, each with `session_info.json`, `analysis/analysis_data.json` and
    `packing_lists/*.json|.xlsx`.
  - `Workers/workers.json`.
  Tasks 5 and 10 consume it.

- [ ] **Step 1: Write the failing tests** (mark the module `pytest.mark.slow` only if the repo already uses that
  marker; check `pytest.ini`/`conftest.py`):
  - `test_builds_clients_sessions_and_packer_files`: `build(tmp_path / "srv")`. Then assert:
    - `client_config.json["client_name"]` is `"Alma Derm"` for ALMA and `"Herbar"` for HERBAR.
    - ALMA has 3 session folders and HERBAR has 2, each with at least one `packing_lists/*.json`.
    - `packer_config.json` has `client_id`, `client_name` and a non-empty `sku_mapping`.
    - `Workers/workers.json["workers"]` has 3 entries with `id`, `name` and `created_at`.
  - `test_refuses_non_empty_dest`: a dest with a file in it makes `build` raise `SystemExit` or `ValueError`, and the
    file is untouched.
- [ ] **Step 2: Run** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_build_guide_server.py -q`.
  Expected: FAIL.
- [ ] **Step 3: Implement**, using only the headless code paths. Model it on `tests/replay/replay.py`.
  - `pm = ProfileManager(base_path=str(dest))`, then `pm.create_client_profile("ALMA", "Alma Derm")` and the same for
    `("HERBAR", "Herbar")`.
  - Pick the newest `tests/replay/fixtures/<id>/config/*.json` by the latest session's `meta.json["config"]`. Turn on
    inventory memory in it the way the app's setting does (find the key with `rg -n "inventory_memory" shopify_tool/`),
    then call `pm.save_shopify_config(id, cfg, backup=False)`.
  - For the last 3 ALMA and last 2 HERBAR fixture sessions (sorted by name), in order:
    - Seed the client's inventory memory from `memory_baseline.json` (`pm.save_inventory_memory`; check its signature).
    - `SessionManager(pm).create_session(id)`, then copy `orders.csv` into the session's `input/`.
    - `core.run_full_analysis(None, orders_path, None, stock_delim, orders_delim, cfg, client_id=id,
      session_manager=sm, profile_manager=pm, session_path=session_path)`. Check the exact parameters at
      `shopify_tool/core.py:1569`.
    - `report_jobs.generate_reports(batch, session_path, final_df, cfg.get("tag_categories", {}), session_id, sm)`
      with one batch entry per `meta.json["packing_lists"]` stem. Build each entry like `replay._report_config` plus
      `"report_type": "packing_lists"`.
    - If a session's analysis raises, print the reason, skip it, and take the next older one. The counts in the test
      must still hold.
  - `packer_config.json`: `{"client_id", "client_name", "sku_mapping": {<barcode>: <sku>}}` with 2–3 pairs. Each
    barcode is a made-up 13-digit EAN, and each SKU is a real SKU from that client's newest packing list.
  - `Workers/workers.json`: `{"workers": [{"id": "worker_001", "name": "Desislava", "created_at": <iso>}, …], "version":
    "1.3.0"}`, with three fictional names (Desislava, Georgi, Maria).
- [ ] **Step 4: Run** the tests. Expected: PASS. Then run the CLI into `/tmp/guide-server-check`, list the tree, and
  delete it.
- [ ] **Step 5: Commit** "Seed a guide server folder from the replay fixtures", then push.

### Task 5: Fulfilment screenshot script

**Files:**
- Create: `scripts/render_guide.py`
- Create: `docs/user-guide/img/en/*.png` and `docs/user-guide/img/bg/*.png` (generated)

**Interfaces:**
- Consumes: `build(dest)` from task 4 (import from `scripts/build_guide_server.py` via `sys.path`).
- Produces: the PNG names in spec section 5's table. Tasks 6 and 7 reference them exactly.

- [ ] **Step 1: Write the script.**
  - Copy the module header of `scripts/render_i18n.py` (lines 1–75): offscreen, `sys.path`, the temp dir, both
    QSettings redirects, the QtWebEngine import order, `pump`, `wait_js` and `save`. Do not import that file.
  - Arguments: `--lang en|bg` (required), `--server <dir>` (optional), and
    `--out` (default `docs/user-guide/img/<lang>`).
  - Set `FULFILLMENT_SERVER_PATH` to `TMP / "server"`. With `--server`, `shutil.copytree` it there. Without it, call
    `build(TMP / "server")`. Guard: `assert Path(os.environ["FULFILLMENT_SERVER_PATH"]).resolve().is_relative_to(Path(tempfile.gettempdir()).resolve())`.
  - Language and theme are set as in `render_i18n.main()` (`i18n.set_language`, `set_theme("light")`). Window size is
    1366×768. Each PNG is `out / f"{name}.png"`, with no theme suffix.
  - Frames, in spec section 5 order:
    - Select client ALMA through the client selector.
    - `client-menu`: `bar.client_selector.popup`; see `tests/test_client_popup.py`.
    - `setup-empty`, then `setup-loaded`: load the newest ALMA session's `input/` orders file the way the drop slot
      does (find the setup bridge's load method in `gui/setup_bridge.py`).
    - `results`: `MainWindow.load_existing_session(<newest ALMA session path>)`, then wait for paint
      (`show_results_when_painted`, `main_window_pyside.py:480`).
    - `add-product`, `reports`, `client-new` and `client-archived`: construct the dialog, call `show()`, settle, grab
      the dialog, then close it.
    - `browse`, `tools`, `logs`: switch tabs with `main_tabs.setCurrentIndex`.
    - `settings-<page>` for each page: `SettingsWindow` built as `actions_handler.py:476-514` does, including the
      `profile` payload. Use `_select_page` with page slugs `profile`, `general`, `mappings`, `rules`, `sets`,
      `weight`, `reports` and `tags`.
    - `language`: open the overflow menu with `popup()` and grab the window.
  - End with `os._exit(code)`, as `render_i18n.py` does.
- [ ] **Step 2: Run** `.venv/bin/python scripts/render_guide.py --lang en`, then `--lang bg`. Expected: one PNG per
  name in each folder.
- [ ] **Step 3: Look at every PNG** with the Read tool. Check that each shows the intended state with real ALMA data,
  that BG frames show Bulgarian, and that no frame is blank or shows a loading state. Fix and re-run until they
  pass. Do not open `~/Desktop/Server./`.
- [ ] **Step 4: Run** the gate. Commit the script and both PNG folders: "Fulfilment user-guide screenshots". Then
  push.

### Task 6: Fulfilment guide, English

**Files:**
- Create: `docs/user-guide/en.md`
- Test: `tests/test_guide_build.py` (add an integrity test)

**Interfaces:**
- Consumes: the PNG names from task 5 and the conventions in `shared/guide/README.md`.

- [ ] **Step 1: Write the failing test** `test_fulfilment_guide_images_exist`. For each of `docs/user-guide/en.md`
  and `bg.md` that exists, every `![...](path)` path resolves to a file under `docs/user-guide/`. Also assert that
  `en.md` exists.
- [ ] **Step 2: Write `en.md`** to spec section 7's outline. Title: `# Fulfilment — User guide`. Then
  `## Part 1 — Daily work` and `## Part 2 — Setting up`, with one `###` per numbered item or bullet.
  - Write each section from its screenshot and the code behind it, for example the Results tab from
    `gui/web/results.js`, statuses from `CONTEXT.md`, and settings pages from `gui/settings/`. Do not write from
    memory.
  - Quote UI labels in **bold**, exactly as in the app's English source strings.
  - The troubleshooting section uses only messages that exist in the code. Find each with `rg`.
  - Section 1 explains the hand-off: the packing lists Fulfilment makes are what Packing Tool opens.
  - End with a short "Getting help" line: **User guide** in ⋯ or F1 opens this guide.
- [ ] **Step 3: Build the PDF** with `.venv/bin/python -m shared.guide.build docs/user-guide/en.md --out /tmp/fulfilment-en.pdf`.
  Expected: it writes the file. Spot-check pages 1–3 with the Read tool (`pages: "1-3"`).
- [ ] **Step 4: Run** the gate. Commit "Fulfilment user guide (EN)", then push.

### Task 7: Fulfilment guide, Bulgarian, and parity check

**Files:**
- Create: `docs/user-guide/bg.md`
- Test: `tests/test_guide_build.py` (add a parity test)

- [ ] **Step 1: Write the failing test** `test_fulfilment_guide_bg_matches_en`. The image basenames in `bg.md`, in
  order, equal those in `en.md`. The count of lines starting `## ` equals that in `en.md`, and so does the count of
  lines starting `### `. Every image path in `bg.md` starts with `img/bg/` and every one in `en.md` starts with
  `img/en/`.
- [ ] **Step 2: Write `bg.md`** as a section-by-section translation of `en.md`. Title: `# Fulfilment — Ръководство`.
  - Every UI label is the app's Bulgarian, looked up in `locales/bg.json` or `shared/assets/locales/bg.json` by its
    English key. When a label has no catalogue entry, keep the English and list it in the commit message.
  - Use plain, everyday Bulgarian for warehouse staff, addressing the reader formally ("Вие" forms, imperative
    "Изберете", "Натиснете").
- [ ] **Step 3: Run** the tests. Build `/tmp/fulfilment-bg.pdf` and spot-check that Cyrillic renders (no boxes).
- [ ] **Step 4: Run** the gate, then `graphify update .`. Commit "Fulfilment user guide (BG)", then push.

### Task 8: Fulfilment wrap-up check

- [ ] **Step 1:** Run the full gate and `ruff check .`. Both must be clean.
- [ ] **Step 2:** Run `/usr/bin/git status --short`. No PDF and no seeded server folder is tracked.
- [ ] **Step 3:** Push. Record the branch HEAD sha with `/usr/bin/git rev-parse HEAD`; task 9 syncs from it.

## Packing Tool repo

All commands from here run in `/home/gloopy/Desktop/Projects/packing-tool/.claude/worktrees/dr-35`. If `.venv` is
missing there, `ln -s /home/gloopy/Desktop/Projects/packing-tool/.venv .venv`.

### Task 9: Sync `shared/`, the ⋯ menu item and F1

**Files:**
- Modify (via sync only): `shared/**`, `scripts/shared_synced_from.txt`
- Modify: `requirements-dev.txt` (add `markdown>=3.7` and `weasyprint>=70`, each with a short comment), `.gitignore`
  (add `docs/user-guide/*.pdf`)
- Modify: `gui/main_window.py` `_init_overflow` (~line 525)
- Test: `tests/test_shell.py`

**Interfaces:**
- Consumes: `open_guide(parent, server_root, app)` from `shared.guide.help`.

- [ ] **Step 1:** Run `.venv/bin/python scripts/sync_shared.py /home/gloopy/Desktop/Projects/shopify-fulfillment-tool/.claude/worktrees/dr-35`.
  Expected: `shared/guide/` appears, and `scripts/shared_synced_from.txt` holds task 8's sha. Commit the sync on its
  own: "Sync shared/ (user guide build and Help opener)".
- [ ] **Step 2: Write the failing test** `test_overflow_has_user_guide` in `tests/test_shell.py`, built the way that
  file's existing window tests are. Monkeypatch `gui.main_window.open_guide`, trigger the `"User guide"` action, and
  assert one call with `(window, str(window.profile_manager.base_path), "packing-tool")`. The item comes before
  "Server connection…".
- [ ] **Step 3: Run** `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_shell.py -q`. Expected: FAIL.
- [ ] **Step 4: Implement.** In `_init_overflow`, `menu.add_item(_("User guide"), self._open_user_guide)` goes first.
  `_open_user_guide` calls `open_guide(self, str(self.profile_manager.base_path), "packing-tool")`. Add
  `QShortcut(QKeySequence("F1"), self)` bound to the same method.
- [ ] **Step 5: Run** the full gate, including packing-tool's i18n guard tests. Expected: PASS. Commit "User guide in
  the ⋯ menu and on F1", then push.

### Task 10: Packing Tool screenshot script

**Files:**
- Create: `scripts/render_guide.py`
- Create: `docs/user-guide/img/en/*.png` and `docs/user-guide/img/bg/*.png` (generated)

**Interfaces:**
- Consumes: a folder from Fulfilment's `scripts/build_guide_server.py` (task 4).
- Produces: the PNG names in spec section 6's table.

- [ ] **Step 1: Seed** the folder with
  `/home/gloopy/Desktop/Projects/shopify-fulfillment-tool/.claude/worktrees/dr-35/.venv/bin/python /home/gloopy/Desktop/Projects/shopify-fulfillment-tool/.claude/worktrees/dr-35/scripts/build_guide_server.py /tmp/guide-server`.
- [ ] **Step 2: Write the script.**
  - Reuse `scripts/render_args.py` for `--lang` and `--size`, and add `--server` (required) and `--out` (default
    `docs/user-guide/img/<lang>`).
  - Copy the harness from `scripts/render_shell.py`:
    - The double QSettings redirect before app imports.
    - Pop `FULFILLMENT_SERVER_PATH`.
    - `shutil.copytree(args.server, TMP / "server")`, then a temp `config.ini` with `FileServerPath`.
    - The "server must be inside the temp dir" refusal.
    - The `settle()` paint wait.
    - `window.grab().save()`.
  - Drive `MainWindow(config_path=...)` **without** `skip_worker_selection`. The real entry points:
    - `workers`: the frame at startup.
    - `_on_worker_chosen("worker_001", "Desislava")`.
    - Select client ALMA: `client_combo.setCurrentIndex(client_combo.findData("ALMA"))`.
    - `packing`.
    - `packer-start`: `_handle_start_packing_from_browser({...})` for the newest ALMA session's list. Read
      `gui/main_window.py:2328` for the dict keys.
    - `packer-scanning`: `on_scanner_input(<order number>)`, then about half of its SKUs. Use the barcodes the order
      expects; read them from the packing-list JSON, or map through `packer_config.json`.
    - `packer-extra`: scan an already fully packed SKU of that order again.
    - `packer-nomatch`: `on_scanner_input("0000000000000")`.
    - `packer-force`: look for a line with quantity > 5 in the seeded lists. If one exists, open that order and call
      `bridge.forceItem(<row>)`. Otherwise copy the injected state from `scripts/render_packer_mode.py` (~line 164),
      and add a `# ponytail:` comment saying why.
    - `packer-complete`: start the smallest list and scan every order in full, calling `processEvents` after the last
      scan because the dialog is deferred.
    - `statistics`: grab while a list is open.
    - `sessions`, then `session-details`: open the completed run.
    - `sku-mapping`: the setup document's SKU mapping page.
    - `quick-map`: open it from Packer Mode with an order open. Find the entry at `gui/main_window.py:2029-2054`.
  - End with `os._exit(code)`.
- [ ] **Step 3: Run** with `--server /tmp/guide-server --lang en`, then `--lang bg`. Look at every PNG with the Read
  tool and check each frame's state against spec section 6. The real-flow frames must show real ALMA products. Fix
  and re-run until they pass.
- [ ] **Step 4:** Delete `/tmp/guide-server`. Run the gate. Commit the script and both PNG folders: "Packing Tool
  user-guide screenshots". Then push.

### Task 11: Packing Tool guide, English

**Files:**
- Create: `docs/user-guide/en.md`
- Test: `tests/test_user_guide.py`

- [ ] **Step 1: Write the failing test** `test_guide_images_exist`. It checks the same thing as Fulfilment's
  `test_fulfilment_guide_images_exist`, against this repo's `docs/user-guide/`. It needs only `re` and `pathlib`, and
  must not import `shared.guide.build`.
- [ ] **Step 2: Write `en.md`** to spec section 7's Packing Tool outline. Title: `# Packing Tool — User guide`, with
  the same Part 1/Part 2 skeleton.
  - Write each section from its screenshot and the code: `gui/web/packer.js` for statuses, `CONTEXT.md` for terms,
    and `gui/setup_pages.py` for SKU mapping.
  - Explain Extra, No match and Force in plain words, as the app actually behaves: Extra means an item of this order
    that is already fully packed, and No match means a barcode not in this order or the mapping.
  - Section 1 says the lists come from Fulfilment.
  - End with the same "Getting help" line.
- [ ] **Step 3: Build** with `.venv/bin/python -m shared.guide.build docs/user-guide/en.md --out /tmp/packing-tool-en.pdf`
  (this needs `pip install markdown weasyprint` in this venv if missing). Spot-check it.
- [ ] **Step 4: Run** the gate. Commit "Packing Tool user guide (EN)", then push.

### Task 12: Packing Tool guide, Bulgarian, and parity check

**Files:**
- Create: `docs/user-guide/bg.md`
- Test: `tests/test_user_guide.py` (add `test_guide_bg_matches_en`, with the same assertions as Fulfilment's
  `test_fulfilment_guide_bg_matches_en`)

- [ ] **Step 1: Write the failing parity test**, then run it. Expected: FAIL.
- [ ] **Step 2: Write `bg.md`** by the rules of task 7 step 2. Labels come from `locales/bg.json` and
  `shared/assets/locales/bg.json`. Title: `# Packing Tool — Ръководство`.
- [ ] **Step 3: Run** the tests. Build `/tmp/packing-tool-bg.pdf` and spot-check the Cyrillic.
- [ ] **Step 4: Run** the full gate. Commit "Packing Tool user guide (BG)", then push.

## After task 12

Stage C opens the Fulfilment PR first, then the packing-tool PR, and states the packing-tool sync dependency in both.
The PR bodies give the owner the four build commands from `shared/guide/README.md` and the server folder
`<server>/Guides/`.
