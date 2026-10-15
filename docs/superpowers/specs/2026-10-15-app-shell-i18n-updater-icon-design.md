# App shell: EN/BG localisation, GitHub-release updater, Packer sidebar mark

Status: approved design (dev-runner run 94, task dr-34). Both repos:
`shopify-fulfillment-tool` (Fulfilment, canonical `shared/`) and `packing-tool` (Packer).
ADRs: 0021 (localisation), 0022 (updater), both in Fulfilment's `docs/adr/`.
No mockup exists for this task; section 6 lists every UI surface and its wording.

## 1. Owner's decisions

| Question | Answer |
|---|---|
| Where the language is stored | Per PC in both apps (QSettings), like the theme. No per-worker language. |
| What is translated | On-screen text only. Files written to the server, exports, reports and logs stay as they are. |
| On a newer release | Offer it: a check at startup shows an **Update to X.Y.Z** button; the operator picks the moment. "Check for updates…" checks on demand. |
| Where the apps run from | Mixed / unknown: handle a per-PC folder and a folder on the server share, and refuse safely when the folder cannot be replaced. |
| Design | Approved as posted (English-text keys, restart to apply, `.cmd` swap with rename retry and `.previous` rollback, `scan-barcode` sidebar mark). |

## 2. Facts the design rests on

- No i18n exists in either app. Text is hard-coded English in three places: Qt widgets
  (about 190 call sites in Fulfilment, 70 in Packer), web pages (`gui/web/*.html|js`),
  and sentences built in Python and pushed to pages (Fulfilment `gui/tools_state.py`,
  `gui/setup_state.py`, `gui/settings/`; Packer `gui/setup_payload.py`,
  `gui/sessions_payload.py`, `gui/app_bridge.py`, `gui/packer_bridge.py`).
- Fulfilment's ERP stock export (`shopify_tool/stock_export.py:16-25`) already has
  Bulgarian headers marked "Do not reorder/rename". It is a file, so it is out of scope.
- Packer's `gui/packer_bridge.py:149-151` drives logic by matching English note text
  ("Repeat", "Cannot fulfill"). Logic keeps matching the raw value; only display is translated.
- Both apps keep per-PC preferences in QSettings: Fulfilment
  `QSettings("ShopifyFulfillmentTool", "FulfillmentApp")` (`gui/theme_manager.py:143`),
  Packer `QSettings("PackingTool", "Theme")` (`gui/theme.py:41`).
- Both sidebars (`gui/components/sidebar.py` in each repo) have a footer with a
  Light | Dark segment (`theme_segment`), and both command bars have a shared
  `OverflowMenu` holding "Server connection…" (Fulfilment `gui/ui_manager.py:379`,
  Packer `gui/main_window.py:502`).
- Both repos are public. A release is a PyInstaller onedir folder zipped at the zip root:
  `FulfilmentTool-<v>.zip` (exe `FulfilmentTool.exe`) and `PackerAssistant-<v>.zip`
  (exe `PackerAssistant.exe`), each with `<zip name>.sha256`. Tags are bare versions
  (`2.3.1`; older ones have four parts, `1.3.10.2`). `__version__` is `"dev"` in the repo
  and stamped by the release build. Install today is "unzip and run"; Packer keeps
  `config.ini` next to the exe.
- Neither app makes HTTP requests today. Windows will not replace a running exe, and
  will not rename a folder while any process (on any PC, over SMB) has a file in it open.
- Packer's window, taskbar and exe icon is already the Packer Assistant logo
  (`main.py:27`, `main.spec:34`). The duplicate is the **sidebar mark**: Packer's
  `gui/components/sidebar.py:377` draws Lucide `package`, Fulfilment's glyph. The
  Packer Assistant logo's glyph is Lucide `scan-barcode`, which is not yet in
  `shared/assets/icons/`.

## 3. Localisation

### 3.1 `shared/i18n.py`

English source text is the key (gettext convention). English needs no catalogue; a
missing entry falls back to English.

```python
LANGUAGES = {"en": "English", "bg": "Български"}   # code -> its own name
DEFAULT_LANGUAGE = "en"

def set_language(code: str, catalogue_files: list[Path]) -> None
    # Loads each file that exists (later files win) into the active catalogue.
    # Unknown code -> "en" with an empty catalogue, logged at WARNING.
def language() -> str
def _(text: str, **values) -> str
    # catalogue.get(text, text); str.format(**values) only when values are given.
def _n(one: str, other: str, n: int, **values) -> str
    # Picks the form for n (1 -> one, else other), formats with n=n and **values.
    # Catalogue entry for a plural is keyed by `one` and holds [one_bg, other_bg].
def N_(text: str) -> str
    # Returns text unchanged. Marks a module-level constant for the key scanner.
def catalogue() -> dict
    # The active catalogue, for the web bridge.
def month_abbr(month: int) -> str
    # _() of N_("Jan") ... N_("Dec"); replaces strftime("%b").
def catalogue_files(app_root: Path, code: str) -> list[Path]
    # [shared/assets/locales/<code>.json, <app_root>/locales/<code>.json]
```

Plural rule: two forms (one, other), which covers English and Bulgarian.
`# ponytail: two plural forms; a language with more (ru, pl) needs a plural rule per language.`

Catalogue files are JSON objects `{"English text": "Bulgarian text", "one": ["една", "много"]}`,
UTF-8, sorted keys, `ensure_ascii=False`, two-space indent:

- `shared/assets/locales/bg.json` — keys used in `shared/` (already bundled with `shared/assets`).
- `locales/bg.json` at each repo root — keys used by that app. Needs a build entry (section 7).

Rules every wrapped string follows:

1. **Translate at display, never identity.** Dict keys, enum values, page keys, saved
   values, values matched by logic, log messages and exception text stay English. Wrap
   only where text is handed to the screen.
2. **No `_()` at import time.** `set_language` runs in `main()` after modules are
   imported. A module-level constant is written `N_("...")` and wrapped at the point of
   display: `label.setText(_(SAVED_LINE))`.
3. **Whole sentences with named placeholders.** `_("{n} of {m} labels matched", n=a, m=b)`,
   never concatenation (Packer `setup_payload.py:63` "Last active " + day is rewritten).
4. **Backend exception detail stays English** (it is also logged). The dialog or toast
   that frames it is translated: `_("Could not start the session: {detail}", detail=str(e))`.
5. Brand names (Fulfilment Tool, Packer Assistant, Shopify) are not wrapped.

### 3.2 Web tier

- `shared/web_page.py` `PageBridge` gains two constant Qt properties read once at load:
  `language` (str) and `strings` (str: `json.dumps(catalogue())`).
- `shared/web/page.js` gains `applyStrings(bridge)`, called by each page once its
  `QWebChannel` bridge is ready (before the first render):
  - sets `document.documentElement.lang` to `bridge.language`;
  - for every `[data-i18n]` element, the key is its `textContent` with whitespace runs
    collapsed to one space and trimmed; the text is replaced when the catalogue has it;
  - for every `[data-i18n-attr]` element (a comma list such as `placeholder,title,aria-label`),
    each named attribute's value is a key and is replaced likewise;
  - defines globals `t(text, vars)` and `tn(one, other, n, vars)` with the same
    semantics as `_` / `_n` (`{name}` placeholders).
- `data-i18n` goes only on elements whose content is plain text. Mixed markup is split
  into spans first.
- JS-built text uses `t()` / `tn()`. Python-built text arrives already translated.

### 3.3 Switching language

- Both sidebars get a **language segment** under the theme segment: two checkable
  buttons labelled with the code, `EN` and `BG`, tooltips `English` and `Български`,
  styled exactly like `theme_segment` (reuse its object name rules; new object name
  `LanguageSegment`). In the collapsed rail it hides with the theme segment (Fulfilment `sidebar.py:191-193`).
  Built from `LANGUAGES`, so a third language adds a third button.
  `# ponytail: a segment of codes; a dropdown when there are more than three languages.`
- Clicking the language that is not active saves it to the app's QSettings under key
  `language`, then asks with the shared `ConfirmDialog`:
  title `Restart to switch language?`, body `The new language applies after a restart.`,
  verb `Restart now`. Accept arms a relaunch (3.4) and closes the main window; cancel
  leaves the choice saved for the next start. The segment shows the saved choice.
- `main()` in each app reads the saved language and calls `set_language` before the
  main window is built.

### 3.4 `shared/relaunch.py`

`on_quit(argv: list[str], *, update: bool = False)` stores one command and connects
`QCoreApplication.aboutToQuit` once; on quit it starts the command detached:
`subprocess.Popen(argv, close_fds=True, creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP)`
on Windows (plus `CREATE_NO_WINDOW` for an update command), `start_new_session=True` elsewhere.
An `update=True` command is never replaced by a plain one, because the update script
relaunches the app itself. `relaunch_argv()` returns `[sys.executable, *sys.argv[1:]]` when
frozen, else `[sys.executable, *sys.argv]`. The relaunch fires only if the app really quits,
so a close the app vetoes (a Packer session prompt) starts no second copy.

### 3.5 Guard tests

`shared/i18n_check.py` (no Qt import) provides, for both repos' tests:

- `python_keys(paths) -> set` — AST scan: first argument of `_()` and `N_()`, and the
  first argument of `_n()` (plural), where the argument is a string literal.
- `html_keys(paths)` — `html.parser`: normalised text of `data-i18n` elements and values of
  attributes named by `data-i18n-attr`.
- `js_keys(paths)` — regex for `t("…")`, `t('…')`, `tn("…"`.
- `bare_python_literals(paths, allow) -> list[str]` — AST: a string literal containing a
  letter passed as first argument to `setText`, `setToolTip`, `setWindowTitle`,
  `setPlaceholderText`, `setStatusTip`, `addItem`, `add_item`, `show_message`, `toast`,
  `QLabel`, `QPushButton`, `QToolButton`, `QCheckBox`, `QRadioButton`, `QGroupBox`,
  `QAction`, or as `title=`/`body=`/`verb=` to `ConfirmDialog`. Returns `file:line`.
- `bare_html_text(paths, allow)` — text nodes with a letter that are not inside a
  `data-i18n` element (and not in `<script>`/`<style>`).
- `placeholders(text) -> set` of `{name}` fields.

Tests (Fulfilment `tests/test_i18n_catalogue.py`, Packer `tests/test_i18n_catalogue.py`):

1. Every key found in the scanned code has an entry in the merged catalogue.
2. Each catalogue file has no key its own scope does not use (no orphans).
3. Each BG value has the same placeholders as its key; plural values are 2-item lists.
4. No bare literals in the scanned Python and HTML (allowlist kept in the test, each
   entry with a reason: brand names, glyph-only strings).

Scope: Fulfilment scans `shared/` against `shared/assets/locales/bg.json`, and `gui/`
against `locales/bg.json`. Packer scans `gui/` against its `locales/bg.json`
(Packer does not test `shared/`). `shopify_tool/` and `packing_tool/` are not scanned:
backend text stays English (3.1 rule 4).

### 3.6 Bulgarian text

Written to this glossary and reviewed by the owner in the PR. Imperative singular on buttons
("Запази"), sentence case.

| English | Bulgarian |
|---|---|
| order / orders | поръчка / поръчки |
| SKU | SKU |
| product, item | артикул |
| stock | наличност |
| session | сесия |
| client | клиент |
| packing list | списък за опаковане |
| packing / packer | опаковане / опаковчик |
| courier | куриер |
| barcode | баркод |
| label | етикет |
| tag | таг |
| worker | работник |
| report | отчет |
| settings | настройки |
| rule | правило |
| set (bundle) | комплект |
| weight | тегло |
| write-off | отписване |
| expiry / batch | годност / партида |
| analysis / run analysis | анализ / стартирай анализа |
| server / server connection | сървър / връзка със сървъра |
| update (n.) / Update to X | актуализация / Актуализирай до X |
| restart | рестартирай |
| Light / Dark | Светла / Тъмна |
| Save / Cancel / Close / Delete | Запази / Отказ / Затвори / Изтрий |
| Archive / Restore | Архивирай / Възстанови |

Dates: numeric formats stay; `%b` month names go through `month_abbr`. Numbers keep today's
formatting. Bulgarian runs about 25% longer: section 8 renders the main screens in BG.

## 4. Updater

### 4.1 `shared/updater.py`

```python
@dataclass(frozen=True)
class AppIdentity:
    repo: str           # "cognitiveghost/shopify-fulfillment-tool"
    asset_prefix: str   # "FulfilmentTool"
    exe_name: str       # "FulfilmentTool.exe"

@dataclass(frozen=True)
class Release:
    version: str        # "2.4.0"
    page_url: str       # html_url, the "What's new" link
    zip_url: str        # browser_download_url of <prefix>-<version>.zip
    sha_url: str        # browser_download_url of <prefix>-<version>.zip.sha256

def parse_version(text) -> tuple[int, ...] | None   # "2.3.1" -> (2,3,1); "v2.3" -> (2,3); "dev"/junk -> None
def newer_release(app, current, fetch_json=...) -> Release | None
    # GET https://api.github.com/repos/<repo>/releases/latest (prereleases excluded by the API),
    # headers Accept: application/vnd.github+json, User-Agent: <asset_prefix>-updater, 5 s timeout.
    # None when current or tag does not parse, tag is not newer, or either asset is missing.
    # Network/JSON errors raise UpdateError(message).
def install_blocker(app_dir: Path, frozen: bool) -> str | None
    # "Updates install only in the released app." when not frozen;
    # "No permission to write to {parent}." when a probe file cannot be created in app_dir's parent.
def is_server_copy(app_dir: Path) -> bool   # UNC path (\\server\...) or a mapped network drive (GetDriveTypeW == 4)
def stage(release, app, app_dir, progress: Callable[[int], None], fetch=...) -> Path
    # Downloads the zip to a temp file in 1 MiB chunks reporting 0..100,
    # checks SHA-256 against the first token of the .sha256 asset,
    # wipes and extracts to <parent>/<app_dir.name>.update/, checks <exe_name> is at its root,
    # deletes the temp zip. Any failure removes the staging folder and raises UpdateError.
def swap_script(app_dir: Path, staged: Path, exe_name: str, pid: int) -> str   # .cmd text, 4.3
def arm_install(app_dir, staged, exe_name) -> Path
    # Writes <parent>/<app_dir.name>.update.cmd and calls relaunch.on_quit(["cmd", "/c", script], update=True).
def leftover(app_dir: Path) -> str | None
    # At startup: if <name>.update/failed.txt exists, returns its version line and removes the staging
    # folder and script; if a staging folder exists without the marker (a crash mid-download), removes it.
```

`class Updater(QObject)` runs network work on a `threading.Thread(daemon=True)` and talks
to the UI only through queued signals (no UI calls from the thread):
`available(Release)`, `upToDate(str)` (current version), `progress(int)`,
`staged(Release)`, `failed(str)`. Methods: `check(manual: bool)`, `install(Release)`.
A check is silent on failure unless `manual`. It never runs when `parse_version(__version__)`
is `None` (dev builds) or the app is not frozen; a manual check then says
`Updates are checked only in the released app.`

### 4.2 Flow

1. Startup: `leftover()` first; a failure marker shows a toast
   `Update to {version} didn't finish: the app folder was in use. Is it open on another PC?`
   Then `check(manual=False)` in the background.
2. `available` → the sidebar footer shows an accent button **Update to {version}**
   (tooltip `A new version is available`; in the collapsed rail an icon-only button with that tooltip,
   Lucide `download`, vendored like `scan-barcode`).
3. Click → `install_blocker` reason, if any, shows a `ConfirmDialog` titled
   `Can't update this copy`, body = reason + `Download it from the release page instead.`,
   verb `Open release page`. Otherwise a `ConfirmDialog` titled `Update to {version}?`, body
   `The app downloads the update, then closes and restarts. What's new: {page_url}` plus, for a
   server copy, `This copy runs from the server: close it on every PC first.`, verb
   `Update and restart`.
4. Accept → `install()`. The button reads `Downloading… {n}%` and is disabled. On `staged`,
   `arm_install()` then the main window's `close()`: the app's normal close path runs (Packer
   ends or saves its session). If the close is vetoed the install stays armed and runs at the
   next quit; the button reads `Update installs when you close the app`.
5. `failed(message)` → toast with the message, the button returns to **Update to {version}**.
6. Overflow menu item `Check for updates…` (beside "Server connection…") runs `check(manual=True)`:
   `available` as above plus a toast `Version {version} is available`; `upToDate` → toast
   `You have the latest version ({version})`; `failed` → toast
   `Couldn't check for updates: {message}`.

### 4.3 The swap script

Written next to the app folder (never inside it), run detached at quit with
`cmd /c`, no window. Paths are quoted; `%` in paths doubled. Steps:

1. Wait for `pid` to exit (`tasklist /FI "PID eq <pid>"` loop, 1 s steps).
2. Remove an existing `<name>.previous` (`rd /s /q`).
3. `ren "<app_dir>" "<name>.previous"`, retried once a second for 60 s. Fails while any
   PC has a file in the folder open; that is the guard for a server copy.
   On timeout: write `<version>` into `<staged>\failed.txt`, start the old exe, exit.
4. `ren "<staged>" "<name>"`.
5. `robocopy "<previous>" "<app_dir>" /E /XC /XN /XO /NFL /NDL /NJH /NJS` — copies only
   files the release does not ship (`config.ini`, anything the operator added). Exit codes
   below 8 are success.
6. `start "" "<app_dir>\<exe_name>"`, then the script deletes itself (`(goto) 2>nul & del "%~f0"`).

`<name>.previous` is the manual rollback: close the app, rename it back.

Launched by `relaunch.on_quit(["cmd", "/c", script], update=True)`, which owns the platform flags (3.4).

### 4.4 App wiring

| | Fulfilment | Packer |
|---|---|---|
| `AppIdentity` | `cognitiveghost/shopify-fulfillment-tool`, `FulfilmentTool`, `FulfilmentTool.exe` | `cognitiveghost/packing-tool`, `PackerAssistant`, `PackerAssistant.exe` |
| version | `shopify_tool.__version__` | `packing_tool.__version__` |
| app dir | `Path(sys.executable).parent` when frozen | same |
| toast | `gui/components/__init__.py:21` `toast(window, text, role=…)` | `MainWindow._toast` (`gui/main_window.py:589`) |

## 5. Packer sidebar mark

Vendor Lucide `scan-barcode.svg` (and `download.svg` for 4.2) into Fulfilment's
`shared/assets/icons/` with the existing LICENSE, add both to `EXPECTED_ICONS` in
`tests/test_ui_assets.py`. Packer `gui/components/sidebar.py:377`:
`icon("package", …)` → `icon("scan-barcode", color=t.on_accent)`. The tile and colours are
unchanged: white glyph on the accent tile, matching the logo.

## 6. UI surfaces (no mockup)

| Surface | Where | Reuses |
|---|---|---|
| Language segment `EN | BG` | both sidebar footers, under the theme segment | the theme segment's style and `_segment_button` |
| Restart confirm | after a language click | `shared/components/confirm_dialog.py` |
| Update button | both sidebar footers, above Client settings / the worker block; hidden until `available` | an accent `QToolButton`, theme tokens only |
| Update confirm / blocker | on Update click | `ConfirmDialog` |
| Check for updates… | both overflow menus | `OverflowMenu.add_item` |
| Toasts | 4.2 | each app's toast |

Every new colour comes from theme tokens; both themes are checked in the renders (section 8).

## 7. Build

- Fulfilment `.github/workflows/build_release.yml`: `--add-data "locales;locales"`; add
  `bg.json`, `scan-barcode.svg` and `download.svg` to the "Verify bundled assets shipped" list.
- Packer `main.spec`: `('locales', 'locales')` in `datas`; same additions to its verify step.
- No new dependency: `urllib`, `hashlib`, `zipfile`, `json`, `html.parser`, `ast` are stdlib.
  Frozen Python on Windows reads the Windows certificate store, so HTTPS needs no `certifi`
  (checked on Windows, section 8).

## 8. Testing

Linux (CI and dev VM):

- `shared/i18n.py`: fallback, formatting, plurals, file merge order, unknown language,
  `month_abbr`. `shared/i18n_check.py`: each scanner on small fixture files.
- Guard tests 3.5 in both repos.
- `page.js` `applyStrings`: a QtWebEngine test loads a tiny page with a fake bridge carrying a BG
  catalogue and checks text, attributes, `lang` and `t()`.
- `shared/updater.py`: `parse_version` table; `newer_release` with a fake `fetch_json`
  (newer / same / older / prerelease-free / missing asset / bad JSON); `stage` with a local
  zip and sha (match, mismatch, missing exe); `swap_script` text contains each step and quoted
  paths; `leftover` cases; `install_blocker` on a read-only temp dir; `relaunch.on_quit`
  priority with `QProcess.startDetached` patched.
- Sidebar: language segment emits and saves; the Update button appears on `available`, shows
  progress, and arms install on `staged` (fakes for the updater).
- Default language is `en`, so existing tests that assert English text keep passing.
  `tests/conftest.py` already redirects QSettings in both repos.
- Renders: each main screen of both apps in BG, light and dark, at 1366×768, saved under
  `docs/design/i18n-renders/<app>/` (Fulfilment: a new `scripts/render_i18n.py` that builds
  `MainWindow` offscreen with QSettings redirected to a temp dir, loads a fixture session and
  saves `window.grab()` per page; Packer: its `scripts/render_*.py` with a new `--lang bg` flag). Look at each for clipped or overflowing text;
  fix by wrapping or eliding, never by shrinking fonts.

Windows only (PR checklist for the owner): the update round trip on a local folder
(download, swap, relaunch, `config.ini` kept, `.previous` present); a server copy open on a
second PC (rename times out, old copy restarts, the next start shows the toast); HTTPS from the
frozen build; the language restart in the frozen build.

## 9. Delivery

- Fulfilment PR: all of `shared/` (i18n, i18n_check, relaunch, updater, icons, `page.js`,
  `web_page.py`, `shared/assets/locales/bg.json`), Fulfilment wiring and translations, ADRs 0021 and 0022.
  It says Packer needs the shared sync.
- Packer PR: `python scripts/sync_shared.py <Fulfilment worktree>` from the pushed Fulfilment
  branch head (CI checks out that SHA from GitHub, so the branch must be pushed first), then Packer
  wiring, translations, the sidebar mark. After the Fulfilment PR is squash-merged, re-sync from a
  fresh clone of GitHub `main` with `--force` before merging Packer (the branch SHA disappears with the branch).

## 10. Not doing

Per-worker language; live re-translation; translated files, exports, logs or backend
exception detail; locale number formats; plural rules beyond two forms; silent auto-install;
delta updates; a signed-update check beyond the release's SHA-256 (the repo is the trust root).
