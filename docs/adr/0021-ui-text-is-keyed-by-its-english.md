# 0021: UI text is keyed by its English, and a language applies on restart

**Status:** Accepted, 2026-10-15
**Context:** `docs/superpowers/specs/2026-10-15-app-shell-i18n-updater-icon-design.md` (section 3). Owner
decisions, runner questions 80 and 81.

## Context

Both tools need English and Bulgarian, with room for more languages. Their text lives in three places: Qt
widgets, web pages (HTML and JS), and sentences Python builds and pushes to the pages. Qt's own `tr()` and
Linguist tooling reach only the first. gettext reaches only Python and adds a `.po`/`.mo` build step. Each
warehouse PC picks one language. Nobody needs to switch language mid-shift.

## Decision

`shared/i18n.py` translates by English source text: `_("Start packing")`, with JSON catalogues per language
(`shared/assets/locales/<code>.json` plus `locales/<code>.json` per app). English has no catalogue, and a
missing entry falls back to English. Web pages get the same catalogue through `PageBridge.strings`. In the
pages, `data-i18n` marks text and `t()` translates JS-built strings. The language is a per-PC QSettings value
and applies on restart: nothing is re-translated live.

Only on-screen text is translated. Identity values, files written to the server, exports, logs and backend
exception detail stay English, so a PC in either language reads what any other PC wrote.

## Consequences

- Code stays readable and English is always complete. Editing an English string orphans its translation. The
  catalogue test fails on that, and on any key with no translation.
- `_()` must not run at import time, because the language is set later in `main()`. Module constants use
  `N_()` and are wrapped where they are shown.
- A bare-literal test keeps new UI text from bypassing `_()`.
- Live switching would need every Qt widget to rebuild its text. Choosing restart avoided that work. Adding
  live switching later means a `retranslate()` per widget.
- Two plural forms only. Adding a language with more (Russian, Polish) needs a plural rule per language.
