# ADR 0003 — A widget re-styles by re-running its closure, not by re-polishing

Status: accepted · 2026-09-03 · supersedes nothing · consumed by Bundle 1 (the
theme-repaint quick fix), and by every later bundle that styles a widget
directly

## Context

Switching the theme leaves stale colour on screen. The roadmap item that
records the bug (Todoist `6hQVj7QQ7wg4xH8V`) diagnoses it as a Qt repaint
fault and prescribes the standard remedy:

> item delegates hold stale brushes, `QIcon`/`QPixmap` snapshots taken at build
> time never re-render, and a `QTableView` viewport is not repolished by a
> stylesheet reassignment alone.
> Fix: `style().unpolish()` + `polish()` + `viewport().update()` driven off the
> existing `theme_changed` signal.

That diagnosis was tested before it was built on, because it prescribes work
across every widget in the app. It is wrong on this codebase, in a way that
matters: the prescribed fix cannot repair the actual fault, and the faults it
repairs do not exist here.

## What was measured

A throwaway probe (PySide6 6.11.1, offscreen) built a `QTableView` with a
delegate that records each `paint()`, plus a `QLabel` styled the way ~53 call
sites in `gui/` style theirs — one interpolated string, set once at build time.
It then switched the application stylesheet.

| Question | Result |
|---|---|
| Does `app.setStyleSheet()` alone repaint the table viewport? | **Yes** — 6 cell paints; the delegate redrew |
| Does the widget's own stylesheet update? | **No** — still carries the old hex |
| Does `unpolish()`/`polish()`/`update()` change either answer? | **No** — viewport already repainted; owned sheet still stale |

Two facts follow, and both cut work rather than adding it.

**The delegate half of the diagnosis is empty.** Every delegate in this repo
reads the theme at paint time — `status_edge_delegate.py:52`,
`session_row_delegates.py:59/74/131`, `tag_delegate.py` — and none caches a
brush. Qt already repaints the viewport on an application stylesheet change,
so those delegates redraw correctly today. There is no bug to fix and no
repolish walk to write.

**The real fault is a stale string, and no amount of polishing touches it.**
`QApplication::setStyleSheet` re-polishes the widget tree, but a widget-level
`setStyleSheet(f"color: {theme.text}")` is a *literal* that was interpolated
once at build time. Re-polishing re-applies that same literal. The old hex is
in the string, not in a cache.

There are 53 such theme-derived widget stylesheets across 14 files; 15 of them
also interpolate `font_css(...)`, so they go stale on a **density** change as
well as a theme change. One further stale artifact exists and is real:
`session_browser_widget.py:448` hands a `QIcon` snapshot to a model item, and a
snapshot does not follow a toggle. `ui_manager._refresh_icons()` already solves
that shape for the rail and the three toolbar buttons.

## Options considered

| Option | Verdict |
|---|---|
| `unpolish()`/`polish()`/`viewport().update()` walk, as prescribed | **Rejected** — measured to fix nothing that is broken and to leave the actual fault untouched |
| Give each of the 14 files an `_apply_theme()` and subscribe it | Works, but re-writes the connect / initial-apply / disconnect-on-destroy trio 14 times — the per-widget patch the item itself argues against |
| Delete every per-widget stylesheet, move the rules into `build_stylesheet` | Correct end state, ~53 call sites and a large behavioural diff. Not Bundle 1's job; later bundles can take files as they touch them |
| **Re-run the styling closure on change, behind one shared helper** | **Chosen** |

## Decision

`shared/theme.py` gains one function:

```python
def on_theme_changed(widget, apply) -> None:
    """Run apply(tokens) now, and again whenever the rendering inputs change,
    for as long as `widget` lives."""
```

A call site stops interpolating a string once and starts handing over the
recipe:

```python
# before — goes stale on the next toggle
label.setStyleSheet(f"color: {theme.text_secondary};")

# after — re-runs itself
on_theme_changed(label, lambda t: label.setStyleSheet(f"color: {t.text_secondary};"))
```

It subscribes to `shared.theme.theme_notifier`, which both apps already emit
through their apply path, so it works in `packing-tool` and here with no shim
involvement. It disconnects on the widget's `destroyed` signal — the same
lifetime dance `ui_manager._connect_theme_change` open-codes today, which is
deleted in favour of this.

Density is folded in at the one place that owns it. `shared.set_density()` is
deliberately pure — "no QSettings, no restyle, no Qt" — and stays that way;
`ThemeManager.set_density()` already persists and repaints, and gains the one
line that announces it. So the signal's meaning widens from "the theme changed"
to "the inputs you rendered from changed", which is what every listener
actually wants. The name does not change: renaming it would touch call sites
for no gain.

## Consequences

- The fix is a mechanism plus conversions, not a sweep. Bundle 1 converts the
  surfaces its completion criterion names — the results table, the session
  browser and Settings — and the stale icon at
  `session_browser_widget.py:448`. The rest convert as later bundles touch
  their files.
- A converted call site costs one line and reads as the same rule it replaced,
  so this does not become a thing to remember.
- `on_theme_changed` earns its place by the deletion test: remove it and the
  connect / apply-now / disconnect-on-destroy trio reappears at every call
  site. `_connect_theme_change` was the first copy of it.
- No repolish walk ships. The measured result is the reason, and this ADR is
  where a future reader finds it before writing one.
