# Client management, client-switch freeze, Results push — design

Run dr-31 (Todoist 6hjrgvwmhVw3j7pM). Three parts ride together:

- **A.** Client management: archive / restore / delete, a better client dropdown, client creation
  that can copy another client's settings, and one place to edit a client's profile.
- **B.** The client switch no longer freezes the window and says it is loading.
- **C.** GitHub #365: the Results push no longer spends ~0.7 ms per order on the GUI thread.

Owner decisions (2026-10-15, runner questions 77 and 78): archive moves folders into `_archive/`
and delete is only for clients with no sessions; the dropdown gets name + ID without duplicates,
a type-to-filter box and an "Archived clients" list; creation gets "Copy settings from"; the
profile moves onto a Client page in Client settings and the Qt `ClientSettingsDialog` goes.

Mockups: `docs/design/ui-refresh/mockups/app-shell.html` (command bar: "a combo showing the client
name … lists clients grouped by client group, then three actions"). This design follows it and
departs in two places: a fourth action row, **Archived clients…**, and a filter box at the top of
the open list. `client-settings.html` has no client-profile page; the Profile page below reuses the
General page's form layout. No other mockup covers this work.

packing-tool needs **no change**. Both tools list clients as the directories under `Clients/`
whose name starts with `CLIENT_` (`shopify_tool/profile_manager.py:300`,
`packing-tool/packing_tool/profile_manager.py:225`), so a folder inside `Clients/_archive/` is
invisible to both. One `shared/` change (A5, additive) reaches packing-tool at its next sync and
needs no work there.

---

## A1. Archive, restore, delete (backend)

Decision record: `docs/adr/0020-an-archived-client-is-a-moved-folder.md`.

All three live on `ProfileManager` (`shopify_tool/profile_manager.py`). They do file-server IO and
run in a `Worker`, never on the GUI thread.

### Paths

```
Clients/CLIENT_<ID>/              live client
Clients/_archive/CLIENT_<ID>/     archived client (client_config.json gains archived_at, archived_by)
Sessions/CLIENT_<ID>/             live sessions
Sessions/_archive/CLIENT_<ID>/    archived sessions (may not exist: a client with no Sessions dir)
```

`_archive` does not start with `CLIENT_`, so `list_clients()` (and packing-tool's
`get_available_clients()`) skip it with no change.

### `archive_client(client_id) -> None`

1. `client_dir = clients_dir / f"CLIENT_{id}"` must exist, else `ProfileManagerError("CLIENT_X does not exist")`.
2. `clients_dir / "_archive" / f"CLIENT_{id}"` must not exist, else
   `ProfileManagerError("An archived CLIENT_X already exists. Restore or delete it first.")`.
   Same check for `sessions_dir / "_archive" / f"CLIENT_{id}"`.
3. `mkdir(parents=True, exist_ok=True)` both `_archive` dirs.
4. `os.rename(client_dir, archived_client_dir)`. On `OSError` (Windows refuses a rename while
   another PC holds a file inside it open): raise
   `ProfileManagerError("CLIENT_X is open on another PC. Close it there, then try again.")`.
5. If `sessions_dir / f"CLIENT_{id}"` exists: `os.rename` it to the archived sessions dir. On
   `OSError`: rename the client dir back (step 4 undone), then raise the same "open on another PC"
   error. If the undo itself fails, log at ERROR with both paths and raise
   `ProfileManagerError("CLIENT_X is half archived: move <path> back by hand.")`.
6. Stamp `archived_at` (local ISO time, `datetime.now().astimezone().isoformat()`) and
   `archived_by` (`os.environ.get("COMPUTERNAME", "Unknown")`, as `created_by` at `profile_manager.py:373`) into the
   archived `client_config.json` with `atomic_write_json` from `shared/`. A failure here is logged
   at WARNING and does not undo the archive: the folder move is the archive.
7. Drop the client from this ProfileManager's in-memory caches (the mtime caches keyed by path).

### `restore_client(client_id) -> None`

The reverse of archive. Refuse with `ProfileManagerError("A live CLIENT_X exists. Rename or archive
it before restoring.")` when `Clients/CLIENT_X` already exists. Move client dir first, then
sessions dir, with the same undo and error rules as archive. Remove `archived_at`/`archived_by`
from the restored `client_config.json` (best effort, WARNING on failure).

### `list_archived_clients() -> list[dict]`

One dict per `Clients/_archive/CLIENT_*` directory, sorted by ID:
`{"client_id": "X", "client_name": <from its client_config.json, or "X">, "archived_at": <str or "">}`.
A missing `_archive` dir returns `[]`. An unreadable `client_config.json` gives name = ID and
`archived_at = ""`.

### `client_has_sessions(client_id) -> bool`

True when `Sessions/CLIENT_X` exists and holds at least one sub-**directory**. Files (the session
index, its lock) do not count.

### `delete_client(client_id) -> None`

1. Refuse with `ProfileManagerError("CLIENT_X has sessions. Archive it instead.")` when
   `client_has_sessions(id)`.
2. `shutil.rmtree(Clients/CLIENT_X)`, then `shutil.rmtree(Sessions/CLIENT_X)` if it exists. On
   `OSError`: `ProfileManagerError("CLIENT_X couldn't be deleted: a file in it is open. Close it on
   every PC, then try again.")`.
3. Drop it from caches.

Delete works on **live** clients only. An archived client is never deleted from the app.

### Creating a client with an archived ID

`create_client_profile` and the creation dialog's live check (A3) both refuse an ID that exists
under `Clients/_archive/`: "CLIENT_X is archived. Restore it from Archived clients."

### Other PCs

A Fulfilment PC that has the archived client open keeps it until its next write, which fails with
the existing "server can't be reached / open on another PC" error, and its next client-list refresh
drops it. Nothing coordinates that; it is acceptable because archive is rare and deliberate.

### Before archiving or deleting the current client

The window first resets the open session and waits for the write queue (in the same worker,
before the move), so this PC holds no file inside the folder: worker body =
`write_queue.flush(timeout=10)`, then `archive_client(id)` / `delete_client(id)`.

---

## A2. The client dropdown

File: `gui/components/commandbar.py` (`_ClientCombo`, `CommandBar.set_clients_from`,
`_add_client`). Reused component: the existing `_ClientCombo`/`QStandardItemModel`; the popup is
new and private to `commandbar.py` (no new file needed, no `shared/` change).

### Rows

- Each client row's display text (`Qt.DisplayRole`) is the **client name**
  (`card_data[id]["client_name"]`, falling back to the ID when missing or blank). The ID stays the
  payload at `Qt.UserRole + 1`, as today. A new role `Qt.UserRole + 2` holds the ID string for the
  delegate and the filter.
- A `_ClientRowDelegate(QStyledItemDelegate)` set on the popup's list view paints a client row as
  `name` in `theme.text_primary`, then two spaces, then the ID in `theme.text_secondary`. When the
  name equals the ID, the ID is painted once. Section and action rows are painted by the base class.
  Colours come from `get_theme_manager().get_current_theme()` at paint time (both themes work).
- The closed combo shows the name (Qt draws `DisplayRole`).
- **No duplicates**: a client listed under Pinned is not listed again under its group or under All
  Clients. Change the docstring of `set_clients_from` accordingly (it says duplicates are kept).
- Because two clients can share a name, the "client changed" signal must not depend on text: connect
  `currentIndexChanged` instead of `currentTextChanged` to `_on_client_changed` (it already reads the
  ID from the row payload).

### The filter popup

`_ClientCombo.showPopup()` is overridden to open `_ClientPopup` instead of Qt's list:

- `_ClientPopup(QFrame)` with window flag `Qt.Popup`, parented to the combo, positioned at the
  combo's bottom-left (`mapToGlobal(rect().bottomLeft())`), width `max(combo.width(), 280)`, height
  capped at 420 px. Layout: a `QLineEdit` (placeholder "Filter clients", clear button on) above a
  `QListView`. Styled with theme tokens only (`theme.background`, `theme.border`, `theme.text_primary`).
- The list view's model is `_ClientFilter(QSortFilterProxyModel)` over the combo's own model, with
  `_ClientRowDelegate`.
- `_ClientFilter.filterAcceptsRow` with filter text `t` (stripped, casefolded):
  - `t == ""`: accept every row.
  - client row: accept when `t` is in the name or the ID, casefolded.
  - section row with a title: accept when at least one client row after it, up to the next section
    row, is accepted.
  - blank divider row and action rows: always accepted.
- Keys in the line edit: Down/Up move the list's current index over **client and action rows only**
  (skip sections); Enter picks the current row, or the first visible client when none is current;
  Escape closes. Typing resets the current index to the first visible client.
- Picking (click or Enter) a client or action row: map to the source row, `combo.setCurrentIndex(row)`
  for a client row, then `combo.activated.emit(row)` for either kind, then close. So the existing
  `_on_row_activated` (actions) and `_on_client_changed` (clients) paths run unchanged.
- The popup opens with the line edit focused and empty, and the current client's row selected.
- `hidePopup()` closes `_ClientPopup` if it is open.

The keyboard rules of the closed combo (`wheelEvent`, `keyPressEvent`, `_step`) are kept as they are.

### "Archived clients…" action

A fourth action row after Manage groups…: `_ARCHIVED = "Archived clients…"` appended to `_ACTIONS`.
It emits a new `CommandBar.archivedClientsRequested` signal (wired like the other action rows in
`_on_row_activated`). `MainWindow` opens `ArchivedClientsDialog` (A6).

---

## A3. Client creation

File: `gui/client_settings_dialog.py` — `ClientCreationDialog` stays; `ClientSettingsDialog` is
deleted (A4). Backend: `ProfileManager.create_client_profile`.

### Dialog

- Fields, in order: Client ID, Client Name, **Copy settings from**, Group, Colour, Pinned.
- **Copy settings from** is a `QComboBox`: first item "Defaults" (data `None`), then every live
  client as "Name  (ID)" (data = ID). The list comes from the caller (the combo's existing data:
  `ClientDirectory`'s last `gather()` result), so opening the dialog reads nothing from the share.
- **Live ID check**: on every `textChanged` of Client ID, run `ProfileManager.validate_client_id`
  (pure, no IO) and check the uppercased ID against two sets handed in by the caller: live IDs and
  archived IDs. Show the first problem under the field in `theme.status_error` (an
  `InlineMessage` from `gui/components/inline_message.py` if it fits, otherwise a `QLabel`), and
  disable the Create button while there is one. Messages:
  - validation failure: the message `validate_client_id` returns;
  - live duplicate: "CLIENT_X already exists.";
  - archived: "CLIENT_X is archived. Restore it from Archived clients."
- Create runs `create_client_profile` in a `Worker` (it writes to the share); the button reads
  "Creating…" and is disabled until the result.

### Backend

`create_client_profile(client_id, client_name, ui_settings=None, copy_from=None) -> bool`:

- New keyword arguments, both optional so existing callers keep working.
- Refuse (return False, WARNING log) when `Clients/_archive/CLIENT_X` exists, as for a live one.
- `ui_settings` (dict: `is_pinned`, `group_id`, `custom_color`) is merged over
  `_get_default_ui_settings()` and written **inside** `client_config.json["ui_settings"]` in the same
  first write. The dialog's separate `update_ui_settings` call is removed. The existing rmtree
  rollback on failure stays.
- `copy_from` (an ID): load that client's `shopify_config.json` with `load_shopify_config`, deep-copy
  it, then overwrite `client_id`, `client_name`, `created_at` with the new client's values and replace
  `inventory_memory` with the default's `inventory_memory`
  (`_create_default_shopify_config(...)["inventory_memory"]`). Every other key is kept as copied:
  `column_mappings`, `courier_mappings`, `analysis_mode`, `settings`, `rules`, `order_rules`,
  `packing_list_configs`, `stock_export_configs`, `set_decoders`, `packaging_rules`,
  `weight_config`, `tag_categories`, and any key not in this list. When the source can't be loaded,
  return False without creating anything (the folder is not created before the source is read).
- packing-tool's `packer_config.json` is not copied (packing-tool owns it).

---

## A4. The Client › Profile page

Files: `gui/settings/window.py`, a new `gui/settings/profile_state.py`, `gui/settings/web_host.py`,
`gui/web/settings.js`, a new `gui/web/settings_profile.js`, `gui/web/settings.html`,
`gui/web/settings.css` (only if a style is missing), `gui/actions_handler.py`,
`gui/client_directory.py`, `gui/client_settings_dialog.py`.

### Navigation

`SETTINGS_NAV_GROUPS` gains a first group `("Client", ["Profile"])`. `WEB_PAGE_KEYS["Profile"] =
"profile"`. `SETTINGS_SEARCH_KEYWORDS["Profile"] = ["name", "group", "colour", "color", "pin",
"archive", "delete"]`. The remembered-last-page behaviour is unchanged (by name).

### `ProfileDraft` (`gui/settings/profile_state.py`, no Qt import)

A `PageContract`, constructed with `(client_id, client_config: dict, groups: list[dict], stats: dict,
has_sessions: bool)`, where `client_config` is the parsed `client_config.json`, `groups` is
`GroupsManager.list_groups()` and `stats` is `ProfileManager.calculate_metadata(client_id)` (`profile_manager.py:1206`;
keys `total_sessions`, `last_session_date`, `last_accessed`), as the old Statistics tab used.

- Holds `name`, `group_id` (or None), `colour` (hex string), `pinned` (bool).
- `apply(action, args)`: `"profile_name" [text]`, `"profile_group" [group_id or ""]`,
  `"profile_colour" [hex]`, `"profile_pin" []` (toggle). Returns False for a no-op or an unknown
  action, as the other drafts do.
- `blocker()`: `"Set Client name"` when the stripped name is empty; data-key `"profile-name"`.
- `collect()` returns `{}`: this page owns no `shopify_config.json` key.
- `profile_updates() -> dict | None`: `None` when nothing changed since the page opened (or since
  `mark_clean`), else `{"client_name": name, "ui_settings": {"group_id": ..., "custom_color": ...,
  "is_pinned": ...}}`.
- `snapshot()` is overridden to return a JSON string of `(name, group_id, colour, pinned)`, so the
  unsaved dot works even though `collect()` is empty.
- `view()` returns `{"page": "profile", "title": "Profile", "subtitle": "How <name> appears in the
  client list.", "action": "", "profile": {...}}` with: the name field (value, problem), the ID
  (read-only text), the group options (`{"value", "label", "checked"}`, first "No group"), colour,
  pinned, the three stats as `[{"label", "value"}]` (`"Never"` / `"Unknown"` for empty values, as
  the old dialog), and the two danger actions:
  - `archive`: `{"label": "Archive client…", "hint": "Hides <ID> in Fulfilment and Packing. Its
    sessions are kept and it can be restored from Archived clients."}`
  - `delete`: `{"label": "Delete client…", "enabled": not has_sessions, "hint": has_sessions ?
    "<ID> has sessions, so it can only be archived." : "Removes <ID> and its folders for good."}`

The old dialog's "Badges" field is dropped: nothing has shown badges since the sidebar was
replaced. `custom_badges` stays in stored data untouched.

### Web page

`gui/web/settings_profile.js` draws `s.profile` and is loaded in `settings.html` before
`settings.js`; `settings.js` renders it like `generalPage` (`(s.profile ? profilePage(s.profile) :
"")` beside the `s.general` line). Controls, all from the existing kit:

- name: `<input class="field" data-input="profile_name" data-key="profile-name">`;
- group: the existing select/menu pattern (`ruleSelect`/`menuItem`) with act `profile_group`;
- colour: a native `<input type="color" data-input="profile_colour" data-key="profile-colour">`;
- pinned: the existing `switch` button with `data-act="profile-pin"`;
- stats: a read-only definition list;
- a "Danger zone" section with two `btn secondary` buttons, `data-act="profile-archive"` and
  `data-act="profile-delete"` (disabled when `delete.enabled` is false), each with its hint below.

Input and click routing follows what `settings.js` already does for `data-input` and `data-act`
(edit(action, args) to Python). The two danger buttons are not edits: `settings.js` calls a new
bridge slot `clientAction(kind)` (`kind` is `"archive"` or `"delete"`).

### Saving

Save keeps its one worker. `SettingsWindow.save_settings` builds `profile = profile_draft.profile_updates()`
and starts `Worker(self._save_all, self.client_id, written, profile)` where `_save_all` calls
`profile_manager.save_shopify_config(client_id, written)` and, only when that returned True and
`profile` is not None, `profile_manager.update_client_profile(client_id, name=profile["client_name"],
ui_settings=profile["ui_settings"])` (signature at `profile_manager.py:1127`; it merges and saves
once, returns bool). It returns True only when every write it attempted succeeded. On success the window records
`self.profile_saved = profile is not None or self.profile_saved` so the caller knows to refresh the
client list.

### Archive / Delete from the page

`SettingsBridge.clientAction(kind)` → `SettingsWebHost.clientActionRequested(kind)` signal →
`SettingsWindow._on_client_action(kind)`:

1. When any page has unsaved edits (`refresh_dirty()` is truthy), the confirm body ends with
   " Unsaved changes in this window will be lost." No separate guard.
2. Archive: `ConfirmDialog.ask(self, title="Archive CLIENT_X?", body="It disappears from the client
   list in Fulfilment and Packing on every PC. Sessions are kept. Restore it from Archived clients.",
   verb="Archive")`.
3. Delete: `ConfirmDialog.ask(self, title="Delete CLIENT_X for good?", body="Its settings and empty
   session folder are removed. This can't be undone.", verb="Delete", require_text="X")` (A5).
4. On yes: `self.removed_client = kind` (`"archived"` / `"deleted"`), then `self.done(QDialog.Rejected)`
   without saving. The **caller** runs the archive/delete (it owns the write queue), so the window
   does no IO for it.

### Callers

- `ActionsHandler.open_client_settings` (`gui/actions_handler.py:~460`) gains an optional
  `client_id=None` (default: the current client). It builds the `ProfileDraft` inputs: it already
  loads `shopify_config.json`; it also needs `client_config.json`, `list_groups()`, the stats and
  `client_has_sessions` — load them in the same place (they are small reads; the existing load there
  is already on the GUI thread, so this does not make it worse, and B3's log will show it).
- After `exec()`:
  - `settings_win.removed_client` set → `MainWindow.remove_client(client_id, kind)` (A6).
  - `settings_win.profile_saved` → `client_directory.refresh()` so the dropdown shows the new name,
    group, colour, pin.
  - the existing "saved" branch (reload `active_profile_config`, revalidate files) runs only when
    `client_id == current_client_id`.
- `ClientDirectory.menu_for`'s **Edit Settings…** calls `open_client_settings(page="Profile",
  client_id=client_id)` instead of opening `ClientSettingsDialog`.
- `ClientSettingsDialog` and its test file `tests/test_client_settings_dialog.py` are deleted; the
  creation-dialog tests in that file move to `tests/test_client_creation_dialog.py`. Fix
  `tests/test_settings_entry_points.py` to the new entry point.

---

## A5. `ConfirmDialog(require_text=...)` (`shared/components/confirm_dialog.py`)

An optional keyword `require_text: str | None = None` on `__init__` and `ask`. When set, a
`QLineEdit` (placeholder `Type <require_text> to confirm`) sits between the body and the buttons, and
the verb button is enabled only while the field's stripped text equals `require_text` exactly
(case-sensitive). Without it the dialog is unchanged. Test in `tests/` (shared/ tests live here).
Additive: packing-tool needs no work at its next sync. Say so in the PR.

---

## A6. Main window wiring

`gui/main_window_pyside.py`:

- `remove_client(client_id, kind)`: if it is the current client, run `_reset_session_state(wait=False)`
  (B2), set `session_path = None`, `current_client_id = None`, and put the bar back on "Choose a
  client" with `command_bar.set_current_client("")` (Task in the plan adds the empty-ID case if the
  bar does not already handle it: index -1, placeholder shown, `_announced` cleared). Then a `Worker` runs `write_queue.flush(timeout=10)` and `archive_client` /
  `delete_client`. On result: `toast(...)` from `gui.components` (as `main_window_pyside.py:18` imports it) "CLIENT_X archived." / "CLIENT_X deleted." and `client_directory.refresh()`. On `ProfileManagerError`: `show_error(self, "CLIENT_X
  wasn't archived" | "CLIENT_X wasn't deleted", <the error's message>)` and refresh the list anyway.
  Other errors: the same headline, "Details are in Logs."
- `ArchivedClientsDialog` (new, in `gui/client_settings_dialog.py` beside the creation dialog):
  a `QDialog` with a `QTableWidget` (ID, Name, Archived) and a **Restore** button acting on the
  selected row, plus Close. It receives `list_archived_clients()`'s result (loaded in a `Worker`
  before opening; show "No archived clients." when empty). Restore runs `restore_client` in a
  `Worker`; success removes the row, refreshes the dropdown, and toasts "CLIENT_X restored.";
  `ProfileManagerError` shows its message with `show_error`.
- The bar's new `archivedClientsRequested` opens it.
- Startup with a remembered last client that is now archived opens on "Choose a client" with no error
  (the combo has no such row). Add a test.

---

## B. The client switch

Files: `gui/main_window_pyside.py`, `gui/components/commandbar.py`, `gui/ui_manager.py` (the
recent-sessions listing result), `shopify_tool/session_manager.py`.

### B1. Busy state on the bar

`CommandBar.set_client_loading(loading: bool)`. While loading: `session_button` and
`new_session_button` are disabled (fold it into `_refresh()`, where both are enabled today: `usable
and not self._client_loading`), and the step readout shows `Loading <client name>…`. The client combo
stays enabled, so a second pick is possible (the existing stale-result check drops the first).

- `on_client_changed` sets it True.
- `_on_client_data_loaded` sets it False after a successful apply, and also on its error paths.
- `_on_client_data_load_error` sets it False.
- A discarded stale result does **not** touch it (the newer switch owns the state).

### B2. The switch order (flush off the GUI thread, reset once)

`_reset_session_state(self, wait: bool = True)`: the flush runs only when `wait` is True. Every
existing caller keeps the default (session opens within a client keep their AUDIT-07-H2 guarantee).

New order of a client switch:

1. GUI, `on_client_changed`: bar loading on, recent sessions cleared (as today), then
   `_reset_session_state(wait=False)`, `session_path = None`, `update_session_info_label()`.
2. Worker, `_load_client_data`: first `self.write_queue.flush(timeout=10)` (log the existing WARNING
   on False), then the two config reads as today. Return the timings with the data (B3).
3. GUI, `_on_client_data_loaded`: stale check as today, then `load_client_config(client_id,
   reset=False)` — `load_client_config` gains `reset: bool = True` and skips its own
   `_reset_session_state()` call when False — then column settings, `session_browser.set_client`,
   `refresh_recent_sessions`, `update_ui_state()`, bar loading off. The second
   `_reset_session_state()` call that is there today is removed.

Why the flush can move: the queue runs jobs FIFO on its own thread and each job carries its own
session path. The flush only has to finish before this PC opens another session; the first session
open after a switch calls `_reset_session_state()` (wait=True), which finds the queue already drained.

Test seam: `tests/test_save_session_queue.py::test_switching_sessions_waits_for_pending_writes` must
stay green. New tests: a client switch with a slow queued job returns from `on_client_changed`
immediately (the GUI thread does not wait); `load_client_config` → `_reset_session_state` is called
once per switch, not twice.

### B3. Measuring hook

One INFO log line per completed switch, written when the recent-sessions listing for the switched
client arrives (`MainWindow.show_recent_sessions`):

```
Client switch to CLIENT_X: flush 0 ms, read 120 ms, apply 35 ms, sessions 410 ms, total 600 ms
```

- `on_client_changed` stores `self._switch_started = (client_id, time.perf_counter())`.
- `_load_client_data` measures `flush` and `read` with `perf_counter` and returns them as a third
  tuple element `{"flush_ms": int, "read_ms": int}`.
- `_on_client_data_loaded` measures `apply` (from its start to bar-loading-off).
- `show_recent_sessions` measures `sessions` as now minus the end of apply, logs the line for the
  matching client, and clears `_switch_started`. A switch superseded by another logs nothing.

This is the hook for the production timings from a Windows PC: the line lands in the app's normal log.
`refresh_setup` and `session_browser.set_client` are not changed in this run; if the `apply` figure
from production is large, they are the next suspects.

### B4. Session index: read outside the lock

`SessionManager._refresh_index` (`shopify_tool/session_manager.py:434`):

1. Without the lock: `listing = self._listing(dir)`; for each name whose entry in `entries` is
   missing or has a different `_dir_mtime`, build `pre[name] = (dir_mtime, self._index_entry(dir/name,
   dir_mtime))`. This is the slow part (one `session_info.json` read per changed session).
2. With the lock, as today: reread the index and the listing; for each name, keep the current entry
   when its `_dir_mtime` matches; else use `pre[name]` when its recorded mtime equals the listing's;
   else read it now. Write once when different, as today.

A folder changed between steps 1 and 2 is reread under the lock (mtime differs), so the result is
never older than today's. `test_a_legacy_index_without_mtimes_is_refreshed_once` stays green; add a
test that counts `_index_entry` calls made while the lock is held (zero for an unchanged-in-between
legacy index).

---

## C. `order_payload` in one pass (#365)

File: `gui/orders_view.py`. Callers unchanged (`ResultsBridge.set_orders`).

- Replace the `df.groupby(ORDER_KEY, sort=False)` loop: take `records = df[line_level].to_dict("records")`
  plus plain lists `keys = df[ORDER_KEY].tolist()`, and, when present, `df["System_note"].tolist()`,
  `df["SKU"].tolist()`, `df["Has_SKU"].tolist()`. One `for i, key in enumerate(keys)` appends
  `{k: _json_value(v) for k, v in records[i].items()}` to `lines[key]` and the three values to
  per-order lists. Then `order_verdict(status, notes, skus, has_skus)` once per key, from those lists.
- Grouping key equality must match today's `groupby`: group on the same values pandas would. Orders
  appear in first-appearance order (a dict keeps insertion order). A NaN order key is dropped by
  `groupby` today; skip rows whose key is NaN the same way.
- `stock_ledger.fulfillable_orders(df)` runs once: `orders_frame` gains an optional
  `ready: set | None = None` argument used instead of its own call, and `order_payload` passes its
  `ready` in.
- `units`, `unknown_sku`, `low_stock` stay as they are (vectorised already).
- Output must be identical: same keys, same order, same values. Gate: `tests/test_order_payload.py`,
  `tests/test_order_verdict.py`, `tests/test_results_summary.py`, `tests/test_results_bridge.py`,
  `tests/test_orders_view.py`. Add one equivalence test that builds a frame with repeated orders,
  NaN cells and a missing optional column, and compares the new output with a saved expected list.
- Before/after: `scripts/stress_ui.py` ("Results, 10 000 orders pushed", Python side). Before, on the
  dev VM, 2026-10-15: 6 888 ms (order_payload alone 6 706 ms). Put both numbers in the PR.

---

## Glossary (`CONTEXT.md`)

Add:

- **Archived client** — a client whose folders were moved into `Clients/_archive/` and
  `Sessions/_archive/`. Neither tool lists it; Archived clients… restores it. Not the session status
  "archived".
- **Client profile** — a client's name, group, colour and pin, kept in `client_config.json` and edited
  on Client settings › Profile. Its fulfilment settings are in `shopify_config.json`.

## Out of scope

- packing-tool code (no change needed).
- Moving Manage groups into Client settings (owner chose to keep the groups dialog).
- Copying `packer_config.json` on create.
- `refresh_setup` / `session_browser.set_client` main-thread work (wait for B3's numbers).
- The 10 s flush when opening a session within one client (not a client switch).
