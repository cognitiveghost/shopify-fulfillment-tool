# User guide build (`shared/guide`)

Shared by Fulfilment and Packing Tool. Builds the user guide PDFs from the Markdown sources in
`docs/user-guide/`. The app's **User guide** item (and F1) opens `Guides/<app>-<language>.pdf` from the server and
falls back to the English file.

## Editing a guide

Change `en.md` or `bg.md` in any editor or in the GitHub web editor. Keep the two files in step (see the conventions).
Re-run the render script only when the UI changed.

## Writing conventions

- Second person, imperative, short numbered steps. One task per `###` section.
- UI labels are in **bold** and quoted exactly as the app shows them in that language.
- Each image line is `![<caption>](img/<lang>/<name>.png)`. The `<name>` is the same in EN and BG; only the folder
  differs.
- The heading skeleton (part, then task) is identical in both languages, so `bg.md` is a line-for-line translation of
  `en.md`.
- Admonitions are blockquotes: `> **Tip:**`, `> **Note:**` or `> **Important:**`.

## Screenshots

Re-render with the app's render script (both languages, light theme, 1366×768):

```
.venv/bin/python scripts/render_guide.py --lang en
.venv/bin/python scripts/render_guide.py --lang bg
```

Packing Tool: `python scripts/render_guide.py --server <dir> --lang en|bg` in its own repo.

## Building the PDFs

```
.venv/bin/python -m shared.guide.build docs/user-guide/en.md --out "<server>/Guides/fulfilment-en.pdf"
.venv/bin/python -m shared.guide.build docs/user-guide/bg.md --out "<server>/Guides/fulfilment-bg.pdf"
# in packing-tool: same with packing-tool-en.pdf / packing-tool-bg.pdf
```

Without `--out` the PDF is written beside the Markdown file. PDFs are build output and are gitignored. A missing
image stops the build and names the file.
