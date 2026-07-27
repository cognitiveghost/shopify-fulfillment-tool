# UI Responsiveness on Slow File Server — Design

## Problem

The app's only persistence is a network file server (UNC share), and it's slow. Several
user-facing actions block the GUI thread while they do file-server IO:

- **Session browser**: already loads sessions off the GUI thread (`SessionLoaderWorker` in
  `gui/session_browser_widget.py:33`), but `SessionManager.list_client_sessions()`
  (`shopify_tool/session_manager.py:207-247`) does a full `iterdir()` over the client's session
  directory and opens **one JSON file per session** every single call — no cache, no index.
  `showEvent()` (`gui/session_browser_widget.py:546`) also re-triggers this on every time the
  widget becomes visible, even with nothing changed.
- **Client switching**: `on_client_changed()` (`gui/main_window_pyside.py:804-881`) runs
  synchronously on the GUI thread and reads the same client's config three times (once via
  `profile_manager.load_shopify_config()` at line 829, again via `self.load_client_config()` at
  line 841 — explicitly commented "for backward compatibility" — and again inside
  `table_config_manager.load_config()` at line 845). It also calls
  `ui_manager.refresh_recent_sessions()` (`gui/ui_manager.py:339-350`), which calls the same
  unpaginated `list_client_sessions()` from above and throws away all but 5 results.
- **Sidebar refresh**: `ClientSidebar.refresh()` (`gui/client_sidebar.py:292-395`) runs
  synchronously (wait-cursor only) and calls `profile_manager.load_client_config()` — which has
  **no cache** — once per client for pin-status, again per client per custom group for group
  membership, and again per client when building each card: O(N) to O(G·N) uncached network
  reads per refresh.
- **Config save**: `_save_and_accept()` (`gui/client_settings_dialog.py:599-633`) and the
  Client Settings "Save" handler (`gui/settings_window_pyside.py:3228`) call
  `profile_manager.save_client_config()` / `save_shopify_config()` directly and synchronously.
  Those methods retry on lock contention up to 5 times with `time.sleep(0.5)`
  (`shopify_tool/profile_manager.py`, `save_shopify_config()`/`save_client_config()`) — up to
  ~2.5s of blocking sleep on the GUI thread in the worst case — and do a synchronous backup
  copy + prune before the write.

Scale: dozens of clients, hundreds of sessions per client, 1-3 concurrent users. This does not
justify new infrastructure (a local DB mirror, a caching service) — it justifies applying
patterns already proven in this codebase more consistently, plus one small incremental index.

## Goals

1. Session browser's default view loads in roughly one file read, not N.
2. "Switch client" and "save config" don't freeze the GUI.
3. No new dependencies, no new architectural layer, no data migration.

## Non-goals

- Physically moving old sessions into an `Archive/` folder. An index makes the same "fast
  default view, browse older on demand" outcome achievable without moving any files, and
  without touching every place that currently references a session path.
- A local disk/sqlite mirror of file-server state. Overkill at hundreds of sessions and
  1-3 concurrent users; revisit only if scale grows an order of magnitude.
- Merging `profile_manager.py`'s hand-rolled atomic write with `shared/atomic_write.py`'s
  `atomic_write_json()`. Real duplication, found during investigation, but unrelated to this
  goal — separate follow-up.
- Any change to `packing-tool` or `shared/` (which is one-way synced from `packing-tool` and
  must not be hand-edited from this repo, per this repo's `CLAUDE.md`).

## Cross-tool compatibility (verified, not assumed)

`packing-tool` also reads/writes inside a session folder (`Sessions/CLIENT_{ID}/{session}/`),
via its `SessionManager.update_session_metadata()`
(`packing-tool/src/session_manager.py:671-714`). Confirmed by reading that code and the dev
fixture data:

- It only ever writes a nested `session_info['packing_progress'][list_name]` block. It never
  reads or writes the top-level `status`/`created_at`/`session_name` fields that
  shopify-fulfillment-tool owns and that the new index will track.
- It does not use shopify-fulfillment-tool's `session_info.json.lock` protocol
  (`shopify_tool/session_manager.py:249-276`) — a pre-existing lost-update race between the two
  tools' writes to `session_info.json` exists independent of this work. Out of scope here.
- `packing-tool` maintains its own analogous incremental index,
  `Sessions/CLIENT_{ID}/registry_index.json` (`packing-tool/src/session_registry_manager.py`),
  keyed per packing-list rather than per session, updated via targeted mutation on each event
  with a one-time full-scan migration if the file is missing
  (`SessionRegistryManager.build_from_scan()`, called only from `ensure_registry()` when
  `registry_index.json` doesn't exist yet). This validates the incremental-index approach below
  against the same file server, but its schema doesn't fit shopify-fulfillment-tool's
  per-session listing need, so it isn't reused directly — a separate, differently-named file
  avoids any collision.

Conclusion: `session_index.json` is exclusively owned and written by shopify-fulfillment-tool.
No coordination with `packing-tool` is required for this design; the only concurrency to guard
against is **multiple shopify-fulfillment-tool instances** on different warehouse PCs (a
documented, designed-for scenario per `packing-tool/README.md`).

## Workstream 1 — Session index

Add `Sessions/CLIENT_{ID}/session_index.json`: a JSON array of small per-session summaries
(`session_name`, `created_at`, `status`) maintained incrementally instead of rebuilt from a
folder scan on every read. `session_info.json` has no separate `session_id` field —
`shared/session_id.py::derive_session_id()` defines the session id as the folder name, i.e.
`session_name` — so the index uses `session_name` as its key, matching directory iteration.

- **Write path**: hook index maintenance into the three functions in
  `shopify_tool/session_manager.py` that already own writes to `session_info.json`'s top-level
  fields under the existing `_locked_session_info()` lock — `create_session()` (append an
  entry), `update_session_status()` (update the entry keyed by `session_name`),
  `update_session_info()` (update the entry keyed by `session_name`, only if the update touches
  `status`). Because these are the *only* writers of the fields the index tracks (confirmed
  above), the index can't drift from normal operation. The index file itself gets its own
  sidecar lock (`session_index.json.lock`), following the exact pattern
  `_locked_session_info()` already uses, to stay correct under concurrent writes from multiple
  PCs.
- **Read path**: `list_client_sessions()` reads `session_index.json` directly instead of
  iterating the directory and opening every session's JSON. If the index file doesn't exist
  (first run against existing data), do the current full scan once, write the index, and use it
  from then on — self-healing, no explicit migration script.
- **Staleness guard**: before trusting the index, compare its entry count against a cheap
  `iterdir()` directory count (no JSON opens). On mismatch (manual folder add/delete/restore),
  rebuild the index via the full scan. This keeps the guard itself cheap.
- **Default view / "archive" behavior**: `SessionBrowserWidget` filters the loaded index to the
  last 30 days client-side by default; a "Show older" control lifts the filter over the same
  already-loaded list — no additional file-server round trip, since the whole index is cheap to
  read at this scale.
- Full `statistics` (computed via `calculate_session_statistics()`,
  `shopify_tool/session_manager.py:600-654`) stays lazy — computed only when a session is
  actually opened, not stored in the index, so the index stays small.

## Workstream 2 — Consistent worker usage, caching, dedup

No new pattern. `gui/worker.py`'s `Worker(QRunnable)` + `WorkerSignals` (`result`/`error`/
`finished`, run via `QThreadPool.globalInstance()`) already exists and is used in
`gui/actions_handler.py:171` and others — reuse it for the flows below instead of running them
on the GUI thread. Per this repo's `CLAUDE.md`, no UI calls happen from inside worker `run()`
bodies; results are applied to the UI only from the `result`/`error` signal handlers on the
main thread.

- **Cache `load_client_config()`**: copy the exact mtime-cache shape
  `load_shopify_config()`/`save_shopify_config()` already use (`_config_cache` class dict,
  keyed `f"{base_path}::client_{client_id}"`, invalidated on `save_client_config()`). Removes
  most of the sidebar's and client-switch's redundant reads without adding a new caching
  mechanism.
- **`on_client_changed()`**: move the IO (`load_shopify_config`, `load_client_config`,
  `table_config_manager.load_config`) into one `Worker` call; apply results to the UI from its
  `result` signal. Drop the redundant second `load_client_config()` call currently marked
  "backward compatibility" — with `load_shopify_config()`'s result already available, that
  second load is fetching data already in hand.
- **`ClientSidebar.refresh()`**: move the group/client/pin-status/metadata gathering into a
  `Worker`; apply the built sidebar model to the UI from its `result` signal, replacing the
  wait-cursor.
- **Config save**: wrap `save_client_config()`/`save_shopify_config()` calls in a `Worker`;
  disable the Save button and show a small "Saving…" state until the `finished` signal fires.
  This also removes the up-to-2.5s retry-sleep block as a side effect, since the sleep now
  happens off the GUI thread.
- **One-line fix**: call `profile_manager.invalidate_metadata_cache()` after
  `SessionManager.create_session()` succeeds — currently missing, so a newly created session's
  count doesn't show up in the sidebar for up to `METADATA_CACHE_TIMEOUT_SECONDS` (5 minutes).
- **`showEvent()` fix** (`gui/session_browser_widget.py:546`): only call `refresh_sessions()` if
  a dirty flag is set (set when a session is created/updated for the currently-displayed
  client) rather than unconditionally on every show.

## Error handling

- Index rebuild-on-mismatch (Workstream 1) covers a corrupted or manually-edited index: worst
  case is one full-scan rebuild, not silent wrong data.
- `Worker`'s existing `error` signal path (already wired in current consumers, e.g.
  `gui/actions_handler.py:171`) is reused as-is for the newly-wrapped flows — errors surface via
  the same `QMessageBox`-on-error pattern already in use, not swallowed.
- Background workers follow the existing `BackgroundWorker.cleanup()` lifecycle
  (`gui/background_worker.py:28-192`: disconnect signals → `quit()` → `wait(2000)` →
  `terminate()` fallback → `deleteLater()`) where `BackgroundWorker` is used; `Worker`
  (`QRunnable`) instances are pooled by `QThreadPool` and don't need the same teardown.

## Testing

- Extend `tests/test_session_manager.py`: index built on first run from an existing session
  directory with no index file, updated on `create_session`/`update_session_status`/
  `update_session_info`, rebuilt on a deliberately introduced count mismatch, 30-day filter
  applied correctly.
- Extend `tests/test_profile_manager.py`: `load_client_config()` cache hit on unchanged mtime,
  cache invalidated after `save_client_config()`, mirroring whatever existing test coverage
  `load_shopify_config()`'s cache already has.
- No new test framework or fixtures — extend the existing files with the existing patterns.
