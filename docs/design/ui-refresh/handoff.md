# UI refresh: handoff notes

## Phases 5–7 (built on the dev VM, runs 47–55)

Judgement calls and gotchas the specs and the roadmap do not carry. The specs are the authority on design; this is
what a session would otherwise learn the hard way.

**The settings document (phase 7), which phases 8–10 join**

- The frame stays Qt (owner decision). A Qt widget cannot be drawn over a web view (ADR 0007), so do not try the
  overlay. One web view sits in the page stack; the frame moves to the web in phase 10, once no Qt page is left.
- A draft is a settings page with no widget (`gui/settings/page_state.py`, no Qt). It meets `PageContract`
  (`gui/settings/contract.py`), so `SettingsWindow` saves and marks it like a Qt page.
- All drafts share ONE host widget in the stack. Anything that asks the stack for "the current page" must ask the
  nav by name instead. This broke the leaving-page unsaved check once.
- The page sends strings and booleans only. A JS number reaches Python as a float, so row indexes travel as
  strings. Enumerations travel by name (`comma`/`semicolon`/`tab`), never as the character.
- Keys that carry user text use a colon (`chip:<name>`) and are found by comparing `dataset.key`, never by a built
  selector: column names can hold quotes and markup.
- Save is live only when a page is unsaved and not blocked; the dialog stays open; the result is Accepted if it
  saved at least once. The worker gets a deep copy, and `mark_clean` takes the snapshot made when the write began,
  so an edit made during the write stays unsaved.
- The footer keeps `QDialogButtonBox` order: `tests/test_dialog_button_guard.py` requires it. Cancel-then-Save is
  a listed departure (phase 7 spec, section 9), due with the web frame in phase 10.
- The dialog and its web view are released with `deleteLater` after `exec`; they leaked per open before.
- Copy follows the code where the mockup disagrees: analysis flags strictly fewer than the threshold, the
  "Courier" field is labelled "Shipping method", courier match says "contains".
- Beyond the phase 7 spec, accepted in PR #361: the file loaded on Setup is split with `resolve_delimiter` over
  the saved setting (`SettingsWindow._loaded_file`).

**Patterns from phases 5 and 6**

- Logic lives in QObjects, not widgets (`ReferenceTool`, `BarcodeTool`), so run-logic tests need no view. Python
  words whole sentences (footers, counts); the page only draws them.
- Slow reads go on a worker. Tools call `gui.pdf_printing` through the module, so one fixture patches it.
- Reusable controls go into `gui/web/kit.css` (and the kit sheet); one-screen pieces stay in that screen's CSS.
- Measure before building a virtual list: 10k log rows filter in 20 ms without one.

**Gotchas**

- The style lint (`tests/test_style_lint.py`) bans `transform` and `transition`, and flags `rotate:`, `scale:` and
  `opacity:` in `.js` too: never end an object key or a ternary branch with one. Swap glyphs instead of rotating.
- ruff DTZ forbids `date.today()` and naive `datetime()`.
- A new icon must be added to `EXPECTED_ICONS` in `tests/test_ui_assets.py`.
- `tests/test_actions_handler.py` builds `mw` as a `SimpleNamespace`; a new attribute read from `mw` must be added
  there.
- `set_theme()` writes the stored theme preference, so a render script restores it. A render script must call
  `apply_theme()`, or the Qt frame renders unstyled.
- `overflow: hidden` clips underscores in mono text until `line-height: 1.5`.
- A log handler's own code must never log (infinite recursion through the root handler).
- `gui/status_edge_delegate.py` is unused in `gui/` and left for its own cleanup.

**The gate**

- On the dev VM three tests fail before any change: `tests/test_label_printing.py::TestImageToZpl`. They are
  baseline there, not yours. Check them on a clean checkout before you start and report what you see.
- Phase 7 ended at 3187 passed.
- Not verifiable offscreen, left for the owner's hand check on Windows and listed in each PR: Esc, Ctrl+S and
  Ctrl+F while focus is inside a web page.
- A phase that changes `shared/` says so in the PR: Packing Tool mirrors it at its next sync.
