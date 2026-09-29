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

Python 3.14 on the dev machine, in CI and in release builds.

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
