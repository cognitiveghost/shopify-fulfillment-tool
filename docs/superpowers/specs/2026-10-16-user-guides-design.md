# User guides for Fulfilment and Packing Tool — design

Run 97, task dr/35. Branch `dr/35-shared-packer-tool-user-guides-for-shopi` in both repos.
No mockup applies. The guides follow the apps as they are on `origin/main`: client management #377, EN/BG #378,
and packing-tool #205.

## Intent

Warehouse staff and the lead learn both apps by being shown around. The goal is two written guides they can read on
their own, one per app, in English and Bulgarian. Both guides share one look and one way of writing. The owner can
edit the text without developer tools, and a script re-takes the screenshots whenever the UI changes.

## Decided by the owner (run 97, question 83)

| Topic | Decision |
|---|---|
| Format | Markdown source in each repo (`docs/user-guide/`). One shared stylesheet, plus a script that builds a printable PDF for the server folder or for printing. |
| Language | EN and BG. English is written first, then Bulgarian. The screenshots are rendered in each language. The owner reviews the BG wording. |
| Audience | Part 1 covers daily work for operators and packers, task by task. Part 2 covers client setup and settings for the lead/admin. |
| Screenshots | Rendered by a script, offscreen, from anonymised production data with real client names. They are re-run after any UI change. |
| Help link (spec approval, question 84) | Approved with an in-app Help entry in both apps that opens the guide PDF (section 10). |

## Goals

- `docs/user-guide/en.md` and `docs/user-guide/bg.md` in **each** repo, each with Part 1 and Part 2.
- Every screenshot comes from a script. Re-running the script after a UI change refreshes all images in both
  languages, and the Markdown does not change.
- One stylesheet and one build command produce a PDF for each guide and language. The command and the style are the
  same in both repos.
- The screenshots show client names from the Server snapshot, such as ALMA "Alma Derm" and HERBAR "Herbar". The
  products are real. Customers and order numbers are anonymised.

## Non-goals

- Developer documentation. README, ADRs and CONTEXT.md stay as they are.
- Committing the PDFs. They are build output and gitignored. The owner builds them and puts them on the server.
- Dark-theme screenshots or several window sizes. The guides use light theme at 1366×768, the warehouse minimum.
- Windows-native renders. The Linux offscreen font differs slightly from Segoe UI, and the owner accepted that.

## Anti-goals (a failure even if it "works")

- **Any customer PII in the repo.** Both repos are public. No raw file from `~/Desktop/Server./` is read by the
  render scripts or copied into the repo. The only data source is the already-anonymised `tests/replay/fixtures/`.
- Screenshots with fake data where real data is easy to get, such as "ACME", "Widget A" or the synthetic frames
  from the i18n renders.
- UI labels in the guide that differ from the app. In `bg.md`, every button, tab and field name quotes the app's
  Bulgarian catalogue exactly (`locales/` in each repo), and in `en.md` the English source string.
- A guide that tours every widget. Part 1 answers "how do I do my job today". Part 2 covers only what the lead needs
  to set up a client.
- A BG file that drifts from EN, for example one with a section or a screenshot the other lacks.

## Constraints

- The repo gates still pass: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` and `ruff check .`.
- `shared/` is canonical in Fulfilment. Packing Tool gets `shared/guide/` through `scripts/sync_shared.py`, never
  by hand.
- Render scripts redirect **both** QSettings formats, and point the app only at a temp server folder (see the
  packing-tool gotcha in its CLAUDE notes: a render once wrote fake clients into the real saved server).
- Neither app gains a runtime dependency. `markdown` (Python-Markdown) is added to `requirements-dev.txt` in both
  repos. `weasyprint` is already a Fulfilment runtime dependency, and Packing Tool adds it to `requirements-dev.txt`.

## Design

### 1. Files

```
shopify-fulfillment-tool/
  shared/guide/__init__.py
  shared/guide/build.py          # Markdown -> HTML -> PDF, shared by both repos
  shared/guide/guide.css         # the one stylesheet (screen + print)
  shared/guide/README.md         # how to edit and rebuild a guide; writing conventions
  scripts/build_guide_server.py  # anonymised fixtures -> throwaway server folder (both apps read it)
  scripts/render_guide.py        # Fulfilment screenshots, --lang en|bg
  docs/user-guide/en.md
  docs/user-guide/bg.md
  docs/user-guide/img/en/*.png
  docs/user-guide/img/bg/*.png
  tests/test_guide_build.py      # build module + guide integrity checks

packing-tool/
  shared/guide/...               # synced, not hand-edited
  scripts/render_guide.py        # Packing Tool screenshots, --server <folder> --lang en|bg
  docs/user-guide/en.md, bg.md, img/en/, img/bg/
  tests/test_user_guide.py       # guide integrity checks
```

`.gitignore` in both repos adds `docs/user-guide/*.pdf`.

### 2. Build: `python -m shared.guide.build <guide.md> [--out <file.pdf>] [--title "..."]`

- Python-Markdown with the `extra`, `toc` and `sane_lists` extensions turns the file into HTML.
- The HTML is wrapped in a page skeleton with `guide.css` inlined. The page has a cover with the title, the
  language, the build date, and the short git commit when one is available. A table of contents comes from the
  `##`/`###` headings. Image `src`s resolve against the Markdown file's folder.
- WeasyPrint writes the PDF. The default output is `<guide stem>` beside the source, for example
  `docs/user-guide/en.pdf`, and the title comes from the first `#` heading.
- A missing image is an error, so the build stops and names the file. A guide with a dead picture never gets
  printed.
- `markdown` and `weasyprint` are imported inside the function, not at module top. Nothing in the frozen app imports
  `shared.guide`.

### 3. Style: `guide.css` and the writing conventions

The stylesheet uses A4 paged media: margins, page numbers in the footer, the guide title in the header, and no
header on the cover. The body is a readable sans-serif at about 11pt. Screenshots run full column width with a thin
border and a caption. They avoid breaking across pages, and every `##` starts a new page.

Colours are taken by value from `shared/theme.py`'s light theme: accent, text and border. The CSS cannot import
Python, so `build.py` reads the tokens from `shared.theme` and writes them into the CSS as variables at build time.
The guide therefore matches the app's look and never hardcodes a colour.

Admonitions are three blockquote forms: `> **Tip:**`, `> **Note:**` and `> **Important:**`. Each gets a
left-border colour.

Writing conventions, kept in `shared/guide/README.md` and followed in all four files:

- Second person, imperative, short numbered steps. One task per `###` section.
- UI labels are in **bold** and quoted exactly as the app shows them in that language.
- Each image line is `![<caption>](img/<lang>/<name>.png)`. The `<name>` is the same in EN and BG. Only the folder
  differs.
- The heading skeleton (part → task) is identical in both languages, so `bg.md` is a line-for-line translation of
  `en.md`.
- The README also explains how to edit a guide: change the `.md` on GitHub or in any editor, then run the build
  command. Re-run the render script only when the UI changed.

### 4. Data: `scripts/build_guide_server.py <dest>` (Fulfilment)

This script builds a fresh server folder from `tests/replay/fixtures/` with the real headless code paths only. It
refuses to run when `<dest>` exists and is non-empty.

1. `ProfileManager(base_path=dest)`, then `create_client_profile` for **ALMA "Alma Derm"** and **HERBAR "Herbar"**.
   The script then calls `save_shopify_config` with the fixture's latest `config/<hash>.json`.
2. Stock comes from the session's `memory_baseline.json`, through the client's inventory memory, as the app does
   when no stock file is loaded (`core.py` ~770 and ~1660). Inventory memory is turned on in the saved config.
3. For each of the last 3 ALMA sessions and the last 2 HERBAR sessions, in date order:
   `SessionManager.create_session` → copy `orders.csv` into `input/` → `core.run_full_analysis` →
   `report_jobs.generate_reports` for each list in the fixture's `meta.json`. This yields real `session_info.json`,
   `analysis/` and `packing_lists/*.json|.xlsx`.
4. For Packing Tool it writes `Clients/CLIENT_<id>/packer_config.json` (`client_id`, `client_name`, and a
   `sku_mapping` with 2–3 barcode→SKU pairs taken from the fixture's SKUs). It also writes `Workers/workers.json`
   with three fictional first names.

The folder is used for renders and then thrown away. It is never committed.

### 5. Fulfilment screenshots: `scripts/render_guide.py --lang en|bg [--server <dir>]`

The script copies the harness from `scripts/render_i18n.py`: `pump`, `wait_js`, `settle` and `save`, plus the
QSettings redirect and the temp `FULFILLMENT_SERVER_PATH`. It does not import that file, because the import has
side effects. Without `--server` it builds the folder with `build_guide_server.py` into a temp dir. With `--server`
it copies that folder to a temp dir first, because the app writes to the server.

It drives the real `MainWindow`. At light theme and 1366×768 it saves one PNG per guide image into
`docs/user-guide/img/<lang>/`:

| name | state |
|---|---|
| `start` | main window just opened, client ALMA |
| `client-menu` | client selector popup open |
| `setup-empty` | Setup tab, new session, nothing loaded |
| `setup-loaded` | Setup tab, orders file loaded |
| `results` | Results tab with a real analysed session (`load_existing_session`) |
| `add-product` | Add Product dialog (`show()`, not `exec()`) |
| `reports` | Generate Reports dialog |
| `browse` | Browse tab listing the seeded sessions |
| `tools` | Tools tab |
| `logs` | Logs tab |
| `client-new` | Client creation dialog |
| `client-archived` | Archived clients dialog |
| `settings-<page>` | each Settings page: profile, general, mappings, rules, sets, weight, reports, tags |
| `language` | the language segment / overflow menu with language and updates |

Blocking dialogs are shown with `show()`, and menus with `popup()`, then grabbed. A name the guide does not end up
using is dropped from the table and the script together.

### 6. Packing Tool screenshots: `scripts/render_guide.py --server <dir> --lang en|bg` (packing-tool)

`--server` is the folder from step 4, and the script always copies it to a temp dir first. It uses the harness from
`scripts/render_shell.py`: the double QSettings redirect, a temp `config.ini` with `FileServerPath`, the
`settle`/`shoot` pattern and `render_args`. It drives `MainWindow(config_path=...)` through the **real** flows, not
injected bridge state:

| name | state | how |
|---|---|---|
| `workers` | Worker selection at startup | window without `skip_worker_selection` |
| `packing` | Packing page, client ALMA, seeded lists | `_on_worker_chosen`, client combo |
| `packer-start` | Packer Mode waiting for an order | `_handle_start_packing_from_browser` |
| `packer-scanning` | order part-scanned | `on_scanner_input(order no.)` then some SKU barcodes |
| `packer-extra` | Extra: a fully packed SKU scanned again | `on_scanner_input` |
| `packer-nomatch` | No match: unknown barcode | `on_scanner_input("0000000000000")` |
| `packer-force` | Force confirm question | real order line with qty > 5 if the data has one, otherwise the injected state used by `render_packer_mode.py` |
| `packer-complete` | session complete | scan every order of the smallest list |
| `statistics` | Statistics with a list open | after the runs above |
| `sessions` | Sessions page with a complete and an in-progress run | |
| `session-details` | Session details of the complete run | |
| `sku-mapping` | SKU mapping page with the seeded pairs | |
| `quick-map` | quick map opened from Packer Mode | |

Barcodes come from the seeded data, as in a real day. Statistics is drawn only while a list is open, so it is
grabbed before the list closes.

### 7. Guide outlines

**Fulfilment.** Part 1, daily work:

1. What the app does, and how its packing lists reach Packing Tool.
2. Starting the app: server connection, language, updates.
3. Choosing a client.
4. A new session: load the orders and the stock.
5. Run the analysis.
6. Read the results: statuses, filters, Add Product.
7. Make the packing lists and the stock exports.
8. Open an earlier session in Browse.
9. Tools: reference labels and barcodes.
10. Logs.
11. When something goes wrong: server unreachable, session locked by another PC, unknown SKU. Each comes from a
    real message in the app.

Part 2, setting up:

- Create, archive, restore and delete a client, and use groups and pins.
- The Settings pages in order: Profile, General, Orders/Stock mapping, Rules, Sets, Weight, Reports, Tag categories.

**Packing Tool.** Part 1, daily work:

1. What the app does: it packs the lists Fulfilment made.
2. Start, and choose who you are (worker).
3. Choose a client and a packing list, then start.
4. Packer Mode: scan the order, then the items. What Extra, No match and Force mean. Skip an order and finish.
5. Leave and come back: saved progress, and a list open on another PC (take over a stale lock).
6. End the session, Statistics, Sessions and Session details.
7. Updates, language, and when something goes wrong.

Part 2, setting up:

- Workers.
- SKU mapping, including quick map from Packer Mode.

Each section is a few numbered steps plus at most one or two screenshots. The prose is written from the rendered
image and the code behind it, not from memory.

### 8. Tests

`tests/test_guide_build.py` (Fulfilment):

- Building a two-line Markdown file that has one image gives a PDF starting with `%PDF`.
- A missing image raises an error.
- The theme colours appear in the generated CSS.
- In `docs/user-guide/`, every image referenced in `en.md` and `bg.md` exists.
- `en.md` and `bg.md` reference the same image names in the same order, and have the same number of `##`/`###`
  headings.

`tests/test_user_guide.py` (packing-tool) runs the last two checks against its own guide. It does not import
`shared.guide.build` (no PDF dependency in its CI).

The render scripts are verified by running them. They have no unit tests, which matches the existing render scripts.

### 9. Delivery

- **Fulfilment PR first.** It holds `shared/guide/`, the seed and render scripts, the Fulfilment guide, and the
  images.
- **Packing-tool PR second.** It syncs `shared/` from the Fulfilment branch commit (the same cross-repo pattern as
  dr/34), and holds its render script, guide and images.
- PDFs are not committed. The README states the build commands. The Stage C report gives the owner the four commands
  that produce the four PDFs.

### 10. Help entry in both apps

- `shared/guide/help.py` holds:
  - `guide_pdf(server_root, app) -> Path | None`. `app` is `"fulfilment"` or `"packing-tool"`. It returns
    `<server_root>/Guides/<app>-<lang>.pdf` for the current `shared.i18n.language()`. If that file is missing it
    falls back to `<app>-en.pdf`. If neither exists it returns `None`.
  - `open_guide(parent, server_root, app)`. This opens the file with `QDesktopServices.openUrl(QUrl.fromLocalFile(...))`,
    which uses the PC's PDF viewer. On `None` it shows a warning that names the folder the guide was expected in.
    The message is wrapped in `_()`.
  - The module imports nothing from `build.py`, so the frozen apps never pull in `markdown` or `weasyprint`.
- Each app gets one more ⋯ menu item, **User guide** (`_("User guide")`), as the first item of its "this PC" items:
  - Fulfilment: `gui/ui_manager.py` `_populate_overflow`, placed before "Server connection…".
  - Packing Tool: `gui/main_window.py` `_init_overflow`, placed before "Server connection…".
  Both pass the app's current server root. `F1` opens it too, through a `QShortcut` on the main window.
- The two new strings go in the **shared** catalogue `shared/assets/locales/bg.json`: "User guide" and the
  not-found message. In BG they read "Ръководство" and "Ръководството не е намерено в {folder}."
- `shared/guide/README.md` documents the server location and the file names, for example
  `Guides/fulfilment-bg.pdf`. The build command writes those names through `--out`.
- Tests (Fulfilment, `tests/test_guide_help.py`): `guide_pdf` returns the language file, falls back to EN, and
  returns `None` when neither file exists. The test uses a temp dir and sets the language with `shared.i18n`.
  A pytest-qt test checks that the Fulfilment overflow menu has the item and that triggering it calls
  `open_guide`, with `open_guide` monkeypatched. Packing-tool gets the same menu test.
- `ShortcutsDialog` lists F1 if it lists global shortcuts.

## Left to the builder

- The exact Markdown extensions beyond `extra`/`toc`, and the CSS details within the style rules above.
- Which fixture sessions to seed, if the "last 3 / last 2" rule hits one that fails analysis. Skip it and take the
  next one.
- Screenshot crops. Whole window by default. A dialog may be grabbed on its own when the window behind it adds
  nothing.
- Fictional worker names, and the 2–3 SKU mapping pairs.

## Calls made in this design (not asked of the owner)

- The PDF pipeline is Python-Markdown plus WeasyPrint. WeasyPrint is already installed, and Python-Markdown is a new
  dev-only dependency. The other options were pandoc (not installed) and Qt's markdown (inline styles fight a shared
  stylesheet).
- The shared style lives in `shared/guide/` and reaches packing-tool through the existing sync.
- Light theme, 1366×768, and one screenshot set per language.
- Screenshot data comes from `tests/replay/fixtures/` only, never the raw Server snapshot. The client names are the
  real ALMA/HERBAR display names. Workers are fictional.
- PDFs are gitignored build output.
- The Help entry opens the PDF from the server folder (`<server>/Guides/`), not one bundled with the app. That needs no release-build change, and a guide fix reaches every PC without a release. The cost is that the owner copies the PDFs there after building them.
