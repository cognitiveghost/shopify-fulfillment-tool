# Client management, client-switch freeze, Results push — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Archive / restore / delete clients, a filterable name+ID client dropdown, client creation that can copy
another client's settings, a Client › Profile settings page; a client switch that does not freeze and says it
is loading; `order_payload` in one pass (#365).

**Architecture:** Backend lifecycle on `ProfileManager` (folder moves into `_archive/`, ADR 0020). The dropdown
keeps its `QStandardItemModel` and gains a delegate plus a private filter popup in `commandbar.py`. The profile
page is one more web-tier settings draft (`profile_state.py` + `settings_profile.js`) on the existing
`SettingsWindow`. The client switch moves its write-queue flush into the existing load worker.

**Tech Stack:** Python 3.11+ (CI 3.11, dev VM 3.14), PySide6 + QtWebEngine, pandas, pytest + pytest-qt.

**Spec:** `docs/superpowers/specs/2026-10-15-client-management-and-switch-freezes-design.md` — read the section a
task names before starting it. ADR: `docs/adr/0020-an-archived-client-is-a-moved-folder.md`.

## Global Constraints

- Gate: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` and `ruff check .` both clean.
- Run one test file: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/<file>.py -q`. A pytest-guard hook
  blocks other shapes of pytest commands in Bash; write test files with Write/Edit, never `cat >`.
- Git: `/usr/bin/git`, **one plain git command per Bash call** (no `&&`, no `;`). Commit with
  `/usr/bin/git commit -F <absolute path to a message file>`; write the message file under
  `/home/gloopy/.claude/jobs/17a888f5/tmp/` (or your own job tmp dir). End every message with the
  `Co-Authored-By:` line the session gives you.
- No hardcoded colours in Qt stylesheets or JS: Qt uses `get_theme_manager().get_current_theme()` tokens
  (`theme.text_primary`, `theme.text_secondary`, `theme.border`, `theme.background`, `theme.status_error`); web
  uses the CSS variables already in `settings.css`/`kit.css`. A client's own `custom_color` is user data, allowed.
- No UI calls from worker threads: a `Worker` (`gui/worker.py`) returns data; the GUI applies it in a slot
  connected to `signals.result`. Keep a strong reference to every `Worker` until `finished` (see the long comment
  in `MainWindow.on_client_changed`).
- Copy rules: sentence case, the client is written `CLIENT_X` in messages, no exclamation marks.
- `shared/` is canonical here (ADR 0017); only Task 1 touches it.
- packing-tool is not changed.
- After the last task: `graphify update .`.

## Review Focus

1. A client name shared by two clients: picking the second must still switch (Task 8 test
   `test_two_clients_with_one_name_still_switch`).
2. Archive when the sessions folder rename fails: the client folder must be back where it was (Task 2 test
   `test_a_failed_sessions_move_puts_the_client_back`).
3. A second client pick while the first is still loading: the bar stays in its loading state for the second
   and the first result is dropped (Task 7 test `test_a_superseded_switch_keeps_the_bar_loading`).
4. Filter text that matches nothing: action rows stay reachable and Enter does not switch client (Task 9 test
   `test_a_filter_matching_nothing_keeps_the_actions_and_enter_does_nothing`).
5. Startup with a remembered last client that has since been archived: opens on "Choose a client", no error
   (Task 15 test `test_a_remembered_archived_client_opens_on_choose_a_client`).

---

## File map

| File | Change |
|---|---|
| `shared/components/confirm_dialog.py` | `require_text` option (Task 1) |
| `shopify_tool/profile_manager.py` | archive / restore / list archived / has sessions / delete (Task 2); create with `ui_settings`, `copy_from`, archived-ID refusal (Task 3) |
| `gui/orders_view.py` | one-pass `order_payload`, `orders_frame(ready=)` (Task 4) |
| `shopify_tool/session_manager.py` | `_refresh_index` reads outside the lock (Task 5) |
| `gui/components/commandbar.py` | loading state, empty-ID reset, index signal (Task 6); name rows, delegate, no duplicates, Archived action (Task 8); filter popup (Task 9) |
| `gui/main_window_pyside.py` | switch order, `wait=`/`reset=` flags, timing line (Task 7); wiring (Tasks 14, 15) |
| `gui/client_directory.py` | `archived_ids` + `last_data`, `editClientRequested`, creation dialog inputs (Tasks 10, 14) |
| `gui/client_settings_dialog.py` | creation dialog: copy-from, live check (Task 10); delete `ClientSettingsDialog` (Task 14); `ArchivedClientsDialog` (Task 15) |
| `gui/settings/profile_state.py` (new) | `ProfileDraft` (Task 11) |
| `gui/web/settings_profile.js` (new), `gui/web/settings.js`, `gui/web/settings.html`, `gui/settings/bridge.py`, `gui/settings/web_host.py` | Profile page (Task 12) |
| `gui/settings/window.py` | Profile nav, save both files, Archive/Delete (Task 13) |
| `gui/actions_handler.py` | `open_settings_window(client_id=)` (Task 14) |
| `CONTEXT.md` | glossary (Task 16) |

---

### Task 1: `ConfirmDialog(require_text=...)`

Spec: A5.

**Files:**
- Modify: `shared/components/confirm_dialog.py`
- Test: `tests/test_components_confirm_dialog.py` (append)

**Interfaces:**
- Produces: `ConfirmDialog(parent, *, title, body, verb, require_text: str | None = None)`, attribute
  `confirm_input: QLineEdit | None`; `ConfirmDialog.ask(parent, *, title, body, verb, require_text=None) -> bool`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_components_confirm_dialog.py`)

```python
def test_without_require_text_there_is_no_field_and_the_verb_is_live(qapp):
    dialog = _dialog()
    assert dialog.confirm_input is None
    assert dialog.verb_button.isEnabled()


def test_require_text_keeps_the_verb_off_until_the_exact_text_is_typed(qapp):
    dialog = ConfirmDialog(
        None, title="Delete CLIENT_X for good?", body="Gone.", verb="Delete",
        require_text="X",
    )
    assert dialog.confirm_input is not None
    assert dialog.confirm_input.placeholderText() == "Type X to confirm"
    assert not dialog.verb_button.isEnabled()
    dialog.confirm_input.setText("x")
    assert not dialog.verb_button.isEnabled()  # case-sensitive
    dialog.confirm_input.setText(" X ")
    assert dialog.verb_button.isEnabled()  # stripped
    dialog.confirm_input.setText("XY")
    assert not dialog.verb_button.isEnabled()
```

- [ ] **Step 2: Run, expect FAIL** — `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_components_confirm_dialog.py -q` → `AttributeError: confirm_input` / `TypeError: unexpected keyword`.

- [ ] **Step 3: Implement.** In `__init__` add `require_text: str | None = None` after `verb`. After
  `layout.addWidget(self.body_label)` add:

```python
        self.confirm_input = None
        if require_text is not None:
            self.confirm_input = QLineEdit(self)
            self.confirm_input.setPlaceholderText(f"Type {require_text} to confirm")
            layout.addWidget(self.confirm_input)
```

  After the verb button is created and added (after `apply_dialog_button_roles`), add:

```python
        if self.confirm_input is not None:
            self.verb_button.setEnabled(False)
            self.confirm_input.textChanged.connect(
                lambda text: self.verb_button.setEnabled(text.strip() == require_text)
            )
```

  Import `QLineEdit` from `PySide6.QtWidgets`. `ask` gains `require_text: str | None = None` and passes it on.

- [ ] **Step 4: Run, expect PASS** (same command; the old tests in the file stay green).
- [ ] **Step 5: Commit** `feat(shared): ConfirmDialog can require typed confirmation`. The PR body later says
  this is additive and needs no packing-tool work.

---

### Task 2: Archive, restore, delete on `ProfileManager`

Spec: A1. ADR 0020.

**Files:**
- Modify: `shopify_tool/profile_manager.py` (new methods after `list_clients`, ~line 328)
- Test: `tests/test_client_archive.py` (new)

**Interfaces:**
- Consumes: fixture `profile_manager` (`tests/conftest.py:52`, a real ProfileManager on `tmp_path`);
  `create_client_profile(client_id, client_name) -> bool`; `ProfileManagerError`.
- Produces:
  - `archive_client(client_id: str) -> None`
  - `restore_client(client_id: str) -> None`
  - `list_archived_clients() -> list[dict]` — `{"client_id", "client_name", "archived_at"}` sorted by ID
  - `client_has_sessions(client_id: str) -> bool`
  - `delete_client(client_id: str) -> None`
  - all raise `ProfileManagerError` with the operator-facing messages below.

- [ ] **Step 1: Write the failing tests** — `tests/test_client_archive.py`:

```python
"""Archive, restore and delete a client (spec A1, ADR 0020)."""

import json

import pytest

from shopify_tool import profile_manager as pm_module
from shopify_tool.profile_manager import ProfileManagerError


def _make(pm, cid="ACME", name="Acme Ltd"):
    assert pm.create_client_profile(cid, name)
    return cid


def _session(pm, cid, name="2026-10-15_1"):
    d = pm.sessions_dir / f"CLIENT_{cid}" / name
    d.mkdir(parents=True)
    return d


def test_archive_moves_both_folders_out_of_the_list(profile_manager):
    pm = profile_manager
    cid = _make(pm)
    _session(pm, cid)
    pm.archive_client(cid)
    assert not (pm.clients_dir / "CLIENT_ACME").exists()
    assert (pm.clients_dir / "_archive" / "CLIENT_ACME" / "client_config.json").exists()
    assert (pm.sessions_dir / "_archive" / "CLIENT_ACME" / "2026-10-15_1").is_dir()
    assert "ACME" not in pm.list_clients()


def test_archive_stamps_when_and_where(profile_manager):
    pm = profile_manager
    cid = _make(pm)
    pm.archive_client(cid)
    cfg = json.loads(
        (pm.clients_dir / "_archive" / "CLIENT_ACME" / "client_config.json").read_text("utf-8")
    )
    assert cfg["archived_at"]
    assert "archived_by" in cfg


def test_archive_refuses_a_missing_client(profile_manager):
    with pytest.raises(ProfileManagerError, match="CLIENT_NOPE does not exist"):
        profile_manager.archive_client("NOPE")


def test_archive_refuses_when_an_archived_copy_exists(profile_manager):
    pm = profile_manager
    cid = _make(pm)
    (pm.clients_dir / "_archive" / "CLIENT_ACME").mkdir(parents=True)
    with pytest.raises(ProfileManagerError, match="An archived CLIENT_ACME already exists"):
        pm.archive_client(cid)
    assert (pm.clients_dir / "CLIENT_ACME").is_dir()


def test_a_client_rename_refused_reads_open_on_another_pc(profile_manager, monkeypatch):
    pm = profile_manager
    cid = _make(pm)

    def refuse(src, dst):
        raise PermissionError("in use")

    monkeypatch.setattr(pm_module.os, "rename", refuse)
    with pytest.raises(ProfileManagerError, match="open on another PC"):
        pm.archive_client(cid)


def test_a_failed_sessions_move_puts_the_client_back(profile_manager, monkeypatch):
    pm = profile_manager
    cid = _make(pm)
    _session(pm, cid)
    real = pm_module.os.rename

    def flaky(src, dst):
        if "Sessions" in str(src) and "_archive" in str(dst):
            raise PermissionError("in use")
        return real(src, dst)

    monkeypatch.setattr(pm_module.os, "rename", flaky)
    with pytest.raises(ProfileManagerError, match="open on another PC"):
        pm.archive_client(cid)
    assert (pm.clients_dir / "CLIENT_ACME").is_dir()
    assert not (pm.clients_dir / "_archive" / "CLIENT_ACME").exists()


def test_restore_brings_both_back_and_drops_the_stamp(profile_manager):
    pm = profile_manager
    cid = _make(pm)
    _session(pm, cid)
    pm.archive_client(cid)
    pm.restore_client(cid)
    assert "ACME" in pm.list_clients()
    assert (pm.sessions_dir / "CLIENT_ACME" / "2026-10-15_1").is_dir()
    cfg = json.loads((pm.clients_dir / "CLIENT_ACME" / "client_config.json").read_text("utf-8"))
    assert "archived_at" not in cfg and "archived_by" not in cfg


def test_restore_refuses_when_a_live_client_has_the_id(profile_manager):
    pm = profile_manager
    cid = _make(pm)
    pm.archive_client(cid)
    (pm.clients_dir / "CLIENT_ACME").mkdir()
    with pytest.raises(ProfileManagerError, match="A live CLIENT_ACME exists"):
        pm.restore_client(cid)


def test_list_archived_clients(profile_manager):
    pm = profile_manager
    assert pm.list_archived_clients() == []
    _make(pm, "ZED", "Zed Co")
    _make(pm, "ACME", "Acme Ltd")
    pm.archive_client("ZED")
    pm.archive_client("ACME")
    listed = pm.list_archived_clients()
    assert [c["client_id"] for c in listed] == ["ACME", "ZED"]
    assert listed[0]["client_name"] == "Acme Ltd"
    assert listed[0]["archived_at"]


def test_list_archived_survives_a_broken_config(profile_manager):
    pm = profile_manager
    d = pm.clients_dir / "_archive" / "CLIENT_BAD"
    d.mkdir(parents=True)
    (d / "client_config.json").write_text("{not json", "utf-8")
    assert pm.list_archived_clients() == [
        {"client_id": "BAD", "client_name": "BAD", "archived_at": ""}
    ]


def test_has_sessions_counts_folders_not_files(profile_manager):
    pm = profile_manager
    cid = _make(pm)
    assert not pm.client_has_sessions(cid)
    (pm.sessions_dir / "CLIENT_ACME" / "sessions_index.json").write_text("[]", "utf-8")
    assert not pm.client_has_sessions(cid)
    _session(pm, cid)
    assert pm.client_has_sessions(cid)


def test_delete_removes_an_empty_client(profile_manager):
    pm = profile_manager
    cid = _make(pm)
    pm.delete_client(cid)
    assert not (pm.clients_dir / "CLIENT_ACME").exists()
    assert not (pm.sessions_dir / "CLIENT_ACME").exists()


def test_delete_refuses_a_client_with_sessions(profile_manager):
    pm = profile_manager
    cid = _make(pm)
    _session(pm, cid)
    with pytest.raises(ProfileManagerError, match="has sessions. Archive it instead"):
        pm.delete_client(cid)
    assert (pm.clients_dir / "CLIENT_ACME").is_dir()
```

- [ ] **Step 2: Run, expect FAIL** — `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_client_archive.py -q` → `AttributeError: 'ProfileManager' object has no attribute 'archive_client'`.

- [ ] **Step 3: Implement** in `shopify_tool/profile_manager.py` (all imports already exist: `os`, `shutil`,
  `json`, `datetime`, `atomic_write_json`):

```python
    ARCHIVE_DIR = "_archive"

    def _lifecycle_paths(self, client_id: str):
        name = f"CLIENT_{client_id}"
        return (
            self.clients_dir / name,
            self.clients_dir / self.ARCHIVE_DIR / name,
            self.sessions_dir / name,
            self.sessions_dir / self.ARCHIVE_DIR / name,
        )

    def _forget_client(self, client_id: str) -> None:
        self._config_cache.pop(f"{self.base_path}::shopify_{client_id}", None)
        self._config_cache.pop(f"{self.base_path}::client_{client_id}", None)
        self.invalidate_metadata_cache(client_id)

    def _move_client(self, client_id, src_c, dst_c, src_s, dst_s, verb):
        """Move the client folder, then its sessions folder; undo the first
        move when the second fails (ADR 0020)."""
        label = f"CLIENT_{client_id}"
        busy = f"{label} is open on another PC. Close it there, then try again."
        dst_c.parent.mkdir(parents=True, exist_ok=True)
        dst_s.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.rename(src_c, dst_c)
        except OSError as e:
            raise ProfileManagerError(busy) from e
        if src_s.exists():
            try:
                os.rename(src_s, dst_s)
            except OSError as e:
                try:
                    os.rename(dst_c, src_c)
                except OSError:
                    logger.error(f"{label} half {verb}: {dst_c} should be at {src_c}")
                    raise ProfileManagerError(
                        f"{label} is half {verb}: move {dst_c} back to {src_c} by hand."
                    ) from e
                raise ProfileManagerError(busy) from e

    def _edit_config_file(self, path: Path, change: Callable[[dict], None]) -> None:
        """Best effort: the folder move is the act, the stamp is a note."""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            change(data)
            atomic_write_json(path, data)
        except Exception:
            logger.warning(f"Could not update {path}", exc_info=True)

    def archive_client(self, client_id: str) -> None:
        live_c, arch_c, live_s, arch_s = self._lifecycle_paths(client_id)
        label = f"CLIENT_{client_id}"
        if not live_c.is_dir():
            raise ProfileManagerError(f"{label} does not exist.")
        if arch_c.exists() or arch_s.exists():
            raise ProfileManagerError(
                f"An archived {label} already exists. Restore or delete it first."
            )
        self._move_client(client_id, live_c, arch_c, live_s, arch_s, "archived")

        def stamp(data):
            data["archived_at"] = datetime.now().astimezone().isoformat()
            data["archived_by"] = os.environ.get("COMPUTERNAME", "Unknown")

        self._edit_config_file(arch_c / "client_config.json", stamp)
        self._forget_client(client_id)
        logger.info(f"Archived {label}")

    def restore_client(self, client_id: str) -> None:
        live_c, arch_c, live_s, arch_s = self._lifecycle_paths(client_id)
        label = f"CLIENT_{client_id}"
        if live_c.exists():
            raise ProfileManagerError(
                f"A live {label} exists. Rename or archive it before restoring."
            )
        if not arch_c.is_dir():
            raise ProfileManagerError(f"{label} is not archived.")
        self._move_client(client_id, arch_c, live_c, arch_s, live_s, "restored")

        def unstamp(data):
            data.pop("archived_at", None)
            data.pop("archived_by", None)

        self._edit_config_file(live_c / "client_config.json", unstamp)
        self._forget_client(client_id)
        logger.info(f"Restored {label}")

    def list_archived_clients(self) -> list[dict]:
        root = self.clients_dir / self.ARCHIVE_DIR
        if not root.is_dir():
            return []
        found = []
        for d in sorted(root.iterdir(), key=lambda p: p.name):
            if not (d.is_dir() and d.name.startswith("CLIENT_")):
                continue
            cid = d.name[len("CLIENT_"):]
            try:
                cfg = json.loads((d / "client_config.json").read_text(encoding="utf-8"))
            except Exception:
                cfg = {}
            found.append(
                {
                    "client_id": cid,
                    "client_name": cfg.get("client_name") or cid,
                    "archived_at": cfg.get("archived_at") or "",
                }
            )
        return found

    def client_has_sessions(self, client_id: str) -> bool:
        d = self.sessions_dir / f"CLIENT_{client_id}"
        return d.is_dir() and any(p.is_dir() for p in d.iterdir())

    def delete_client(self, client_id: str) -> None:
        live_c, _arch_c, live_s, _arch_s = self._lifecycle_paths(client_id)
        label = f"CLIENT_{client_id}"
        if self.client_has_sessions(client_id):
            raise ProfileManagerError(f"{label} has sessions. Archive it instead.")
        try:
            shutil.rmtree(live_c)
            if live_s.exists():
                shutil.rmtree(live_s)
        except OSError as e:
            raise ProfileManagerError(
                f"{label} couldn't be deleted: a file in it is open. "
                "Close it on every PC, then try again."
            ) from e
        self._forget_client(client_id)
        logger.info(f"Deleted {label}")
```

  Check `self.sessions_dir` / `self.clients_dir` are the attribute names used by `create_client_profile`
  (they are: `profile_manager.py:356, 388`). If `invalidate_metadata_cache` has a different signature than
  `(client_id=None)`, adapt the call (it is at line ~1287).

- [ ] **Step 4: Run, expect PASS.** Also run `tests/test_profile_manager.py` (still green).
- [ ] **Step 5: Commit** `feat: archive, restore and delete clients (ADR 0020)`.

---

### Task 3: `create_client_profile(ui_settings=, copy_from=)` and archived IDs

Spec: A3 › Backend, A1 › Creating a client with an archived ID.

**Files:**
- Modify: `shopify_tool/profile_manager.py:330-400` (`create_client_profile`)
- Test: `tests/test_client_create.py` (new)

**Interfaces:**
- Consumes: Task 2's `ARCHIVE_DIR`, `archive_client`.
- Produces: `create_client_profile(client_id: str, client_name: str, ui_settings: dict | None = None,
  copy_from: str | None = None) -> bool`. False when the ID is live or archived, or `copy_from` can't be loaded.

- [ ] **Step 1: Write the failing tests** — `tests/test_client_create.py`:

```python
"""Creating a client: look in one write, settings copied from another (spec A3)."""

import json


def _client_cfg(pm, cid):
    return json.loads((pm.clients_dir / f"CLIENT_{cid}" / "client_config.json").read_text("utf-8"))


def _shopify_cfg(pm, cid):
    return json.loads((pm.clients_dir / f"CLIENT_{cid}" / "shopify_config.json").read_text("utf-8"))


def test_ui_settings_land_in_the_first_write(profile_manager):
    pm = profile_manager
    ok = pm.create_client_profile(
        "ACME", "Acme", ui_settings={"is_pinned": True, "group_id": "g1", "custom_color": "#123456"}
    )
    assert ok
    ui = _client_cfg(pm, "ACME")["ui_settings"]
    assert ui["is_pinned"] is True
    assert ui["group_id"] == "g1"
    assert ui["custom_color"] == "#123456"
    # defaults still present (table_view etc.)
    assert set(pm._get_default_ui_settings()) <= set(ui)


def test_an_archived_id_cannot_be_reused(profile_manager):
    pm = profile_manager
    assert pm.create_client_profile("ACME", "Acme")
    pm.archive_client("ACME")
    assert pm.create_client_profile("ACME", "Acme again") is False
    assert not (pm.clients_dir / "CLIENT_ACME").exists()


def test_copy_from_takes_every_setting_but_identity_and_stock_memory(profile_manager):
    pm = profile_manager
    assert pm.create_client_profile("SRC", "Source")
    src = _shopify_cfg(pm, "SRC")
    src["rules"] = [{"name": "r1"}]
    src["settings"]["low_stock_threshold"] = 9
    src["inventory_memory"]["skus"] = {"A": 3}
    src["custom_key"] = {"kept": True}
    pm.save_shopify_config("SRC", src)

    assert pm.create_client_profile("NEW", "New Co", copy_from="SRC")
    new = _shopify_cfg(pm, "NEW")
    assert new["client_id"] == "NEW"
    assert new["client_name"] == "New Co"
    assert new["created_at"] != src["created_at"]
    assert new["rules"] == [{"name": "r1"}]
    assert new["settings"]["low_stock_threshold"] == 9
    assert new["custom_key"] == {"kept": True}
    default_memory = pm._create_default_shopify_config("NEW", "New Co")["inventory_memory"]
    assert new["inventory_memory"]["skus"] == default_memory["skus"]


def test_copy_from_a_missing_client_creates_nothing(profile_manager):
    pm = profile_manager
    assert pm.create_client_profile("NEW", "New Co", copy_from="GHOST") is False
    assert not (pm.clients_dir / "CLIENT_NEW").exists()
```

  If `save_shopify_config` stamps or migrates fields so `created_at` is equal by chance, keep the other
  asserts and drop only that line. Check `load_shopify_config` returns None (not raises) for a missing client;
  if it raises, catch `ProfileManagerError` in the implementation and return False.

- [ ] **Step 2: Run, expect FAIL** (`TypeError: unexpected keyword argument 'ui_settings'`).

- [ ] **Step 3: Implement.** Signature `create_client_profile(self, client_id, client_name, ui_settings=None,
  copy_from=None)`; update the docstring Args. After `client_dir = ...`:

```python
        if client_dir.exists() or (self.clients_dir / self.ARCHIVE_DIR / f"CLIENT_{client_id}").exists():
            logger.warning(f"Client profile already exists (live or archived): CLIENT_{client_id}")
            return False

        shopify_config = self._create_default_shopify_config(client_id, client_name)
        if copy_from:
            source = self.load_shopify_config(copy_from.upper())
            if not source:
                logger.warning(f"Can't copy settings from CLIENT_{copy_from}: not loaded")
                return False
            fresh = shopify_config
            shopify_config = copy.deepcopy(source)
            for key in ("client_id", "client_name", "created_at", "inventory_memory"):
                shopify_config[key] = fresh[key]
```

  Remove the later `shopify_config = self._create_default_shopify_config(...)` line (it is now built above).
  Add `"ui_settings": {**self._get_default_ui_settings(), **(ui_settings or {})},` to the `client_config` dict.

- [ ] **Step 4: Run, expect PASS**; also `tests/test_profile_manager.py` and `tests/test_client_profile_update.py`.
- [ ] **Step 5: Commit** `feat: create a client with its look in one write, optionally copying settings`.

---

### Task 4: `order_payload` in one pass (#365)

Spec: C.

**Files:**
- Modify: `gui/orders_view.py` (`orders_frame` ~line 210, `order_payload` lines 298-366)
- Test: `tests/test_order_payload_equivalence.py` (new)

**Interfaces:**
- Produces: `orders_frame(df, ready: set | None = None)`; `order_payload(df)` unchanged in signature and output.

- [ ] **Step 1: Measure before.** `QT_QPA_PLATFORM=offscreen .venv/bin/python scripts/stress_ui.py` (≈75 s).
  Note the "Results, 10 000 orders pushed" Python-side ms in your report (dev VM baseline 6 888 ms).

- [ ] **Step 2: Write the equivalence test.** `tests/test_order_payload_equivalence.py` holds a verbatim copy of
  today's `order_payload` as `_reference` and compares it with the new one. Copy the current body of
  `order_payload` from `gui/orders_view.py:298-366` **before editing it**, rename it `_reference`, and import
  the helpers it uses from `gui.orders_view` (`orders_frame`, `classify_columns`, `order_verdict`,
  `_json_value`, `_iso_or_none`, `_per_order_any`, `_STOCK_CODES`, `ORDER_KEY`, `FULFILLABLE`,
  `NOT_FULFILLABLE`, `parse_tags`, `stock_ledger` — import each from wherever `orders_view.py` imports it).
  Then:

```python
import json

import numpy as np
import pandas as pd
import pytest

from gui.orders_view import order_payload
from test_order_payload import _analysis_frame


def _random_frame(seed: int, with_optional: bool) -> pd.DataFrame:
    rng = np.random.RandomState(seed)
    n = 300
    keys = [f"#{1000 + k}" for k in rng.randint(0, 80, size=n)]  # orders interleaved
    df = pd.DataFrame(
        {
            "Order_Number": keys,
            "Order_Fulfillment_Status": rng.choice(["Fulfillable", "Not Fulfillable"], size=n),
            "SKU": rng.choice(["A", "B", "C", "TS-1"], size=n),
            "Quantity": rng.randint(1, 5, size=n),
            "Stock": rng.choice([0.0, 1.0, 5.0, np.nan], size=n),
            "System_note": rng.choice(["", "Cannot fulfill: B short"], size=n),
            "Notes": rng.choice(["", "call", np.nan], size=n),
            "Total_Price": rng.choice([10.5, np.nan, 3.0], size=n),
        }
    )
    if with_optional:
        df["Has_SKU"] = rng.choice([True, False], size=n, p=[0.9, 0.1])
        df["Stock_Alert"] = rng.choice(["", "Low"], size=n)
        df["Internal_Tags"] = rng.choice(["", "VIP", "VIP, Gift"], size=n)
    return df


FRAMES = [
    lambda: _analysis_frame(),
    lambda: _random_frame(1, True),
    lambda: _random_frame(2, False),
]


@pytest.mark.parametrize("make", FRAMES)
def test_the_one_pass_payload_matches_the_groupby_one(make):
    df = make()
    expected = json.dumps(_reference(df.copy()), sort_keys=False, default=str)
    actual = json.dumps(order_payload(df.copy()), sort_keys=False, default=str)
    assert actual == expected
```

  Comparing the JSON strings pins key order as well as values. Run it now: it must PASS against today's code
  (it compares the code with itself). If a frame makes `_reference` raise, remove that frame and say so.

- [ ] **Step 3: Rewrite `order_payload`.** Replace the `for key, group in df.groupby(...)` block with:

```python
    keys = df[ORDER_KEY].tolist()
    records = df[line_level].to_dict("records")
    has_status = "Order_Fulfillment_Status" in df.columns
    notes = df["System_note"].tolist() if "System_note" in df.columns else None
    skus = df["SKU"].tolist() if "SKU" in df.columns else None
    has_skus = df["Has_SKU"].tolist() if "Has_SKU" in df.columns else None
    # ponytail: one pass into plain lists (#365); groupby slices cost ~0.7 ms an order.
    per_order: dict = {}
    for i, key in enumerate(keys):
        if pd.isna(key):  # groupby drops a missing key; so do we
            continue
        bucket = per_order.get(key)
        if bucket is None:
            bucket = per_order[key] = ([], [], [], [])
        bucket[0].append({k: _json_value(v) for k, v in records[i].items()})
        if notes is not None:
            bucket[1].append(notes[i])
        if skus is not None:
            bucket[2].append(skus[i])
        if has_skus is not None:
            bucket[3].append(has_skus[i])
    lines, verdicts = {}, {}
    for key, (rows, key_notes, key_skus, key_has) in per_order.items():
        lines[key] = rows
        if has_status:
            status = FULFILLABLE if str(key).strip() in ready else NOT_FULFILLABLE
        else:
            status = ""
        verdicts[key] = order_verdict(status, key_notes, key_skus, key_has)
```

  `ready` must be computed before `orders_frame`: move `ready = stock_ledger.fulfillable_orders(df)` to the top
  of the function and call `orders = orders_frame(df, ready=ready)`. In `orders_frame`, add the parameter
  `ready: set | None = None` and replace its own `stock_ledger.fulfillable_orders(df)` call (~line 248) with
  `ready if ready is not None else stock_ledger.fulfillable_orders(df)`. Check what type
  `fulfillable_orders` returns and annotate with that type instead of `set` if it differs.
  If `_json_value` of a record value differs from the old `map(_json_value, row)` output for a pandas
  `Timestamp`/numpy scalar (the equivalence test tells you), use
  `df[line_level].itertuples(index=False, name=None)` with `dict(zip(line_level, map(_json_value, row)))` instead
  of `to_dict("records")`: it is still one pass.

- [ ] **Step 4: Run** the new test plus `tests/test_order_payload.py tests/test_order_verdict.py
  tests/test_results_summary.py tests/test_results_bridge.py tests/test_orders_view.py` — all PASS.
- [ ] **Step 5: Measure after** with `scripts/stress_ui.py`; put before/after in the commit message body and
  in your report.
- [ ] **Step 6: Commit** `perf: order_payload groups once into plain lists (#365)`.

---

### Task 5: Session index reads changed sessions outside the lock

Spec: B4.

**Files:**
- Modify: `shopify_tool/session_manager.py:434-466` (`_refresh_index`)
- Test: `tests/test_session_manager.py` (append, near `test_a_legacy_index_without_mtimes_is_refreshed_once` at ~line 385; read that test first and reuse its setup helpers)

**Interfaces:** none new.

- [ ] **Step 1: Write the failing test.** Using the legacy-index setup of the neighbouring test, wrap
  `_exclusive_lock` and `_index_entry` to count `_index_entry` calls while the lock is held:

```python
def test_a_legacy_refresh_reads_sessions_outside_the_lock(<same fixtures as the legacy test>, monkeypatch):
    # <build the same legacy index the neighbouring test builds: N sessions, no _dir_mtime>
    held = {"now": False, "reads_under_lock": 0}
    real_lock = manager._exclusive_lock
    real_entry = manager._index_entry

    import contextlib

    @contextlib.contextmanager
    def lock(path):
        with real_lock(path):
            held["now"] = True
            try:
                yield
            finally:
                held["now"] = False

    def entry(*args, **kwargs):
        if held["now"]:
            held["reads_under_lock"] += 1
        return real_entry(*args, **kwargs)

    monkeypatch.setattr(manager, "_exclusive_lock", lock)
    monkeypatch.setattr(manager, "_index_entry", entry)
    sessions = manager.list_client_sessions(<client id>)
    assert len(sessions) == <N>
    assert held["reads_under_lock"] == 0
```

  Replace the `<…>` with the neighbouring test's names. If `_exclusive_lock` is a module function rather than a
  method, patch it on the module (`monkeypatch.setattr(session_manager_module, "_exclusive_lock", lock)`).

- [ ] **Step 2: Run, expect FAIL** (`reads_under_lock == N`).
- [ ] **Step 3: Implement.**

```python
        listing = self._listing(client_sessions_dir)
        if self._index_matches(listing, entries):
            return entries

        # The slow part -- one session_info.json per changed folder -- runs
        # without the lock. Under it, an entry read here is used only when its
        # folder's mtime has not moved since.
        known = {e.get("session_name"): e for e in entries}
        pre = {}
        for name, dir_mtime in listing.items():
            entry = known.get(name)
            if entry is None or entry.get("_dir_mtime") != dir_mtime:
                pre[name] = (dir_mtime, self._index_entry(client_sessions_dir / name, dir_mtime))

        with self._exclusive_lock(self._index_lock_path(client_sessions_dir)):
            current = self._read_index(client_sessions_dir) or []
            listing = self._listing(client_sessions_dir)
            by_name = {e.get("session_name"): e for e in current}
            refreshed = []
            for name, dir_mtime in listing.items():
                entry = by_name.get(name)
                if entry is None or entry.get("_dir_mtime") != dir_mtime:
                    early = pre.get(name)
                    if early is not None and early[0] == dir_mtime:
                        entry = early[1]
                    else:
                        entry = self._index_entry(client_sessions_dir / name, dir_mtime)
                refreshed.append(entry)
            if refreshed != current:
                self._write_index(client_sessions_dir, refreshed)
        return refreshed
```

  Keep the method's docstring, adding one sentence: "Changed sessions are read before the lock is taken."
- [ ] **Step 4: Run** `tests/test_session_manager.py` — all PASS.
- [ ] **Step 5: Commit** `perf: the session index reads changed sessions outside its lock`.

---

### Task 6: Command bar — loading state, empty client, index signal

Spec: B1; A2 › Rows (last bullet); A6 (empty ID).

**Files:**
- Modify: `gui/components/commandbar.py` (`__init__` ~150-190, `set_current_client` 451, `_refresh` 509)
- Test: `tests/test_commandbar_states.py` (append)

**Interfaces:**
- Produces: `CommandBar.set_client_loading(loading: bool, name: str = "") -> None`;
  `CommandBar.loading_label: QLabel`; `set_current_client("")` clears the box.

- [ ] **Step 1: Write the failing tests** (append; reuse the file's imports):

```python
def test_loading_a_client_disables_the_session_actions_and_says_so(qapp):
    bar = CommandBar()
    bar.set_clients(["Acme"])
    bar.set_state(BarState.NO_SESSION)
    bar.set_client_loading(True, "Acme")
    assert not bar.session_button.isEnabled()
    assert not bar.new_session_button.isEnabled()
    assert bar.client_selector.isEnabled()
    assert bar.loading_label.text() == "Loading Acme…"
    assert not bar.loading_label.isHidden()
    bar.set_client_loading(False)
    assert bar.session_button.isEnabled()
    assert bar.new_session_button.isEnabled()
    assert bar.loading_label.isHidden()


def test_an_empty_client_id_clears_the_box(qapp):
    bar = CommandBar()
    bar.set_clients(["Acme"])
    bar.set_current_client("Acme")
    bar.set_current_client("")
    assert bar.current_client() == ""
    assert bar.client_selector.currentIndex() == -1
```

- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.**
  - In `__init__`: `self._client_loading = False`; create `self.loading_label = QLabel(self)` placed right
    after `session_button` in the layout, hidden, styled
    `on_theme_changed(self.loading_label, lambda t=None, l=self.loading_label: l.setStyleSheet(f"color: {get_theme_manager().get_current_theme().text_secondary};"))`
    — copy how other labels in this file get their theme colour (look for an existing `on_theme_changed`
    + `setStyleSheet` pair and match it).
  - Replace `self.client_selector.currentTextChanged.connect(self._on_client_changed)` with
    `self.client_selector.currentIndexChanged.connect(self._on_client_changed)` and rename the slot's parameter
    `_text` to `_index` (it ignores it).
  - `set_client_loading`:

```python
    def set_client_loading(self, loading: bool, name: str = "") -> None:
        """While a client's settings load: no session can be started or opened."""
        self._client_loading = loading
        self.loading_label.setText(f"Loading {name}…" if loading else "")
        self.loading_label.setVisible(loading)
        self._refresh()
```

  - In `_refresh`: `usable = state in (...) and not self._client_loading`.
  - At the top of `set_current_client`:

```python
        if not client_id:
            self._restore_client = ""
            self._announced = ""
            self.client_selector.setCurrentIndex(-1)
            return
```

- [ ] **Step 4: Run** `tests/test_commandbar_states.py tests/test_components_commandbar.py tests/test_shell.py` — PASS.
- [ ] **Step 5: Commit** `feat: the command bar shows a client loading and can clear its client`.

---

### Task 7: The client switch — flush in the worker, reset once, timing line

Spec: B2, B3.

**Files:**
- Modify: `gui/main_window_pyside.py` — `load_client_config` (279), `_load_client_data` (587),
  `on_client_changed` (604), `_on_client_data_loaded` (646), `show_recent_sessions` (~698),
  `_on_client_data_load_error` (~708), `_reset_session_state` (1052)
- Test: `tests/test_client_switch.py` (new); keep `tests/test_save_session_queue.py` green

**Interfaces:**
- Consumes: Task 6 `command_bar.set_client_loading(loading, name)`.
- Produces: `_reset_session_state(self, wait: bool = True)`; `load_client_config(self, client_id, reset: bool = True)`;
  `_load_client_data(client_id) -> (shopify_config, column_settings, timings: dict)`;
  `self._switch_started: tuple[str, float] | None`, `self._switch_apply_end: float | None`.

- [ ] **Step 1: Write the failing tests.** Find how `tests/test_shell.py` and `tests/test_save_session_queue.py`
  build a `MainWindow` (fixture names, how they stub the server and the write queue) and use the same fixture.
  `tests/test_client_switch.py`:

```python
"""A client switch does not wait on the GUI thread (spec B2, B3)."""

import logging
import threading


def test_the_switch_returns_before_a_slow_write_finishes(<window fixture>, qtbot):
    win = <window>
    gate = threading.Event()
    win.write_queue.submit(lambda: gate.wait(5))  # use the queue's real enqueue method name
    calls = []
    real = win._reset_session_state
    win._reset_session_state = lambda wait=True: (calls.append(wait), real(wait=wait))[1]
    win.on_client_changed("<a client the fixture has>")
    assert calls == [False]          # returned without waiting
    gate.set()
    qtbot.waitUntil(lambda: not win.command_bar._client_loading, timeout=5000)
    assert calls == [False]          # load_client_config did not reset a second time


def test_the_switch_logs_one_timing_line(<window fixture>, qtbot, caplog):
    win = <window>
    caplog.set_level(logging.INFO)
    win.on_client_changed("<client>")
    qtbot.waitUntil(lambda: "Client switch to CLIENT_" in caplog.text, timeout=5000)
    line = next(r.getMessage() for r in caplog.records if "Client switch to" in r.getMessage())
    for part in ("flush", "read", "apply", "sessions", "total"):
        assert f"{part} " in line and " ms" in line


def test_a_superseded_switch_keeps_the_bar_loading(<window fixture>, qtbot):
    win = <window>
    win.on_client_changed("<client A>")
    win.on_client_changed("<client B>")
    # A's result arrives first or is discarded; the bar must stay loading until B applies.
    win._on_client_data_loaded("<client A>", ({"x": 1}, {}, {"flush_ms": 0, "read_ms": 0}))
    assert win.command_bar._client_loading
    qtbot.waitUntil(lambda: not win.command_bar._client_loading, timeout=5000)
    assert win.current_client_id == "<client B>"
```

  Fill `<…>` from the fixture you reuse. The write queue's enqueue method is in
  `gui/session_write_queue.py` (class `SessionWriteQueue`); use its real name.

- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.**
  - `_reset_session_state(self, wait: bool = True)`: wrap the flush block in `if wait:`. Add to the docstring:
    "A client switch passes wait=False and flushes in its load worker instead (spec B2)."
  - `load_client_config(self, client_id, reset: bool = True)`: guard its `self._reset_session_state()` call with
    `if reset:`.
  - `_load_client_data`:

```python
    def _load_client_data(self, client_id: str):
        """Worker-thread IO for a client switch: drain the last session's
        writes, then read this client's configs (spec B2)."""
        t0 = time.perf_counter()
        queue = getattr(self, "write_queue", None)
        if queue is not None and not queue.flush(timeout=10):
            logger.warning(f"Background writes still pending while switching clients: {queue.pending()}")
        t1 = time.perf_counter()
        shopify_config = self.profile_manager.load_shopify_config(client_id)
        client_config = self.profile_manager.load_client_config(client_id) or {}
        column_settings = normalize_column_settings(
            (client_config.get("ui_settings") or {}).get("results_columns")
        )
        t2 = time.perf_counter()
        timings = {"flush_ms": round((t1 - t0) * 1000), "read_ms": round((t2 - t1) * 1000)}
        return shopify_config, column_settings, timings
```

    (`import time` at the top if missing.)
  - `on_client_changed`: after `self.current_client_id = client_id` add

```python
        self._switch_started = (client_id, time.perf_counter())
        self._switch_timings = None
        self.command_bar.set_client_loading(True, self.command_bar.client_selector.currentText() or client_id)
        self._reset_session_state(wait=False)
        self.session_path = None
        self.update_session_info_label()
```

    (keep the existing `hasattr(self, "command_bar")` guards' style.)
  - `_on_client_data_loaded`: unpack `shopify_config, column_settings, timings = result`; record
    `apply_start = time.perf_counter()` first. Keep the stale check **before** touching the bar. In the
    `not shopify_config` branch and the `except` branch call `self.command_bar.set_client_loading(False)`. In
    the try body: `self.load_client_config(client_id, reset=False)`, delete the second
    `self._reset_session_state()` and the two lines after it (`session_path`, `update_session_info_label` now
    run in `on_client_changed`), keep the rest, then at the end:

```python
            self.command_bar.set_client_loading(False)
            self._switch_apply_end = time.perf_counter()
            self._switch_timings = dict(timings, apply_ms=round((self._switch_apply_end - apply_start) * 1000))
```

  - `_on_client_data_load_error`: inside `if client_id == self.current_client_id:` also
    `self.command_bar.set_client_loading(False)`.
  - `show_recent_sessions`: after the existing stale check, before filling the picker:

```python
        started = getattr(self, "_switch_started", None)
        timings = getattr(self, "_switch_timings", None)
        if started and timings and started[0] == client_id:
            now = time.perf_counter()
            logger.info(
                f"Client switch to CLIENT_{client_id}: flush {timings['flush_ms']} ms, "
                f"read {timings['read_ms']} ms, apply {timings['apply_ms']} ms, "
                f"sessions {round((now - self._switch_apply_end) * 1000)} ms, "
                f"total {round((now - started[1]) * 1000)} ms"
            )
            self._switch_started = None
```

  - Initialise `self._switch_started = None`, `self._switch_timings = None`, `self._switch_apply_end = None`
    in `__init__` next to `self._client_load_workers`.
  - Search the repo for other unpackings of `_load_client_data`'s result (`rg "_load_client_data"`), e.g.
    `scripts/stress_ui.py`, and update them to three values.
- [ ] **Step 4: Run** `tests/test_client_switch.py tests/test_save_session_queue.py tests/test_shell.py` — PASS.
- [ ] **Step 5: Commit** `fix: a client switch waits for writes off the GUI thread and shows it is loading`.

---

### Task 8: Dropdown rows — name + muted ID, no duplicates, Archived clients action

Spec: A2 › Rows, A2 › "Archived clients…" action.

**Files:**
- Modify: `gui/components/commandbar.py` (constants ~55-63, `set_clients_from` 287-348, `_add_client`,
  `_on_row_activated`, signals at the class top)
- Test: `tests/test_components_commandbar.py` (update `test_the_dropdown_is_pinned_then_groups_then_the_rest`,
  `test_no_clients_means_no_separator_above_the_actions`; append new tests)

**Interfaces:**
- Produces: `ROLE_CLIENT_ID = Qt.UserRole + 2`; `CommandBar.archivedClientsRequested = Signal()`;
  `_ACTIONS = (_REFRESH, _NEW_CLIENT, _MANAGE_GROUPS, _ARCHIVED)` with `_ARCHIVED = "Archived clients…"`;
  `_ClientRowDelegate(QStyledItemDelegate)` installed on `client_selector.view()`.

- [ ] **Step 1: Update and add tests.** In `test_the_dropdown_is_pinned_then_groups_then_the_rest` drop the
  duplicate `(ROW_CLIENT, "A")` under Retail and append `(ROW_ACTION, "Archived clients…")`. In
  `test_no_clients_means_no_separator_above_the_actions` expect `[ROW_ACTION] * 4`. Append:

```python
def _data(**names):
    return {
        "special_groups": {},
        "custom_groups": [],
        "all_clients": list(names),
        "pinned_client_ids": set(),
        "group_members": {},
        "card_data": {cid: {"client_name": n, "ui_settings": {}} for cid, n in names.items()},
    }


def test_a_row_shows_the_client_name_and_keeps_the_id_as_payload(qapp):
    bar = CommandBar()
    bar.set_clients_from(_data(ACME="Acme Ltd"))
    kinds = _rows(bar)
    assert (ROW_CLIENT, "ACME", "Acme Ltd") in kinds
    item = next(bar.client_selector.model().item(i) for i in range(len(kinds)) if kinds[i][0] == ROW_CLIENT)
    assert item.data(ROLE_CLIENT_ID) == "ACME"


def test_a_blank_name_falls_back_to_the_id(qapp):
    bar = CommandBar()
    bar.set_clients_from(_data(ACME=""))
    assert _client_rows(bar) == ["ACME"]


def test_two_clients_with_one_name_still_switch(qapp):
    bar = CommandBar()
    bar.set_clients_from(_data(A1="Same", A2="Same"))
    seen = []
    bar.clientChanged.connect(seen.append)
    bar.set_current_client("A1")
    bar.set_current_client("A2")
    assert seen == ["A1", "A2"]


def test_the_archived_clients_row_asks_for_the_list(qapp):
    bar = CommandBar()
    bar.set_clients_from(_data(ACME="Acme"))
    asked = []
    bar.archivedClientsRequested.connect(lambda: asked.append(True))
    row = next(i for i, (k, _p, t) in enumerate(_rows(bar)) if t == "Archived clients…")
    bar.client_selector.activated.emit(row)
    assert asked == [True]
```

  Import `ROLE_CLIENT_ID` from `gui.components.commandbar`.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.**
  - `_add_client`: `name = (data["card_data"].get(client_id, {}).get("client_name") or "").strip() or client_id`;
    `QStandardItem(name)`; keep `UserRole`/`UserRole + 1`; add `item.setData(client_id, ROLE_CLIENT_ID)`.
  - `set_clients_from`: when building group sections, skip members already in `listed`
    (`members = [c for c in ... if c in data["all_clients"] and c not in listed]`). Fix the docstring: "A pinned
    client is listed only under Pinned."
  - `_ARCHIVED` constant, added to `_ACTIONS`; `archivedClientsRequested = Signal()` beside
    `manageGroupsRequested`; in `_on_row_activated` add `elif label == _ARCHIVED: self.archivedClientsRequested.emit()`
    before the final `else`.
  - Delegate:

```python
class _ClientRowDelegate(QStyledItemDelegate):
    """A client row: its name, then its ID in the secondary text colour."""

    def paint(self, painter, option, index):
        if index.data(Qt.UserRole) != ROW_CLIENT:
            super().paint(painter, option, index)
            return
        name = index.data(Qt.DisplayRole) or ""
        cid = index.data(ROLE_CLIENT_ID) or ""
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)
        text_rect = style.subElementRect(QStyle.SE_ItemViewItemText, opt, opt.widget)
        theme = get_theme_manager().get_current_theme()
        painter.save()
        painter.setPen(QColor(theme.text_primary))
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, name)
        if cid and cid != name:
            used = opt.fontMetrics.horizontalAdvance(name + "  ")
            painter.setPen(QColor(theme.text_secondary))
            painter.drawText(text_rect.adjusted(used, 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft, cid)
        painter.restore()
```

    Install with `self.client_selector.view().setItemDelegate(_ClientRowDelegate(self.client_selector))` in
    `__init__`. Import what is missing (`QStyledItemDelegate`, `QStyleOptionViewItem`, `QStyle`, `QApplication`,
    `QColor`, `get_theme_manager` — check how this file already imports the theme). Selected rows: if
    `option.state & QStyle.State_Selected`, use the palette's highlighted-text colour for the name instead of
    `text_primary` (read it from `opt.palette.highlightedText().color()`).
  - Render check: write a throwaway script (not committed) that builds a `CommandBar` with `_data(ACME="Acme
    Ltd", B="B")`, calls `bar.client_selector.showPopup()`, grabs `bar.client_selector.view().grab()` and saves a
    PNG under your job tmp dir, in light and dark (`get_theme_manager().set_theme(...)` — check the method name).
    Look at both images; the ID must be visibly muted and readable.
- [ ] **Step 4: Run** `tests/test_components_commandbar.py tests/test_commandbar_states.py tests/test_shell.py tests/test_client_directory.py` — PASS.
- [ ] **Step 5: Commit** `feat: the client dropdown shows names with muted IDs, once each`.

---

### Task 9: The filter popup

Spec: A2 › The filter popup.

**Files:**
- Modify: `gui/components/commandbar.py` (`_ClientCombo.showPopup/hidePopup`, new `_ClientFilter`, `_ClientPopup`;
  the context-menu hookup in `CommandBar.__init__` ~154 and `_on_row_context_menu` ~432)
- Test: `tests/test_client_popup.py` (new)

**Interfaces:**
- Consumes: Task 8 `ROLE_CLIENT_ID`, `_ClientRowDelegate`, row kinds.
- Produces: `_ClientCombo.popup: _ClientPopup | None` (the open popup), `_ClientPopup.filter_edit: QLineEdit`,
  `_ClientPopup.list_view: QListView`, `_ClientPopup.proxy: _ClientFilter`.

- [ ] **Step 1: Write the failing tests** — `tests/test_client_popup.py`:

```python
"""The client list filters as you type (spec A2)."""

from PySide6.QtCore import Qt

from gui.components.commandbar import ROW_ACTION, ROW_CLIENT, ROW_SECTION, CommandBar

DATA = {
    "special_groups": {},
    "custom_groups": [{"id": "g", "name": "Retail"}],
    "all_clients": ["ACME", "BETA", "ZED"],
    "pinned_client_ids": set(),
    "group_members": {"g": ["ACME", "BETA"]},
    "card_data": {
        "ACME": {"client_name": "Acme Ltd", "ui_settings": {}},
        "BETA": {"client_name": "Beta", "ui_settings": {}},
        "ZED": {"client_name": "Zed Shop", "ui_settings": {}},
    },
}


def _open(qtbot):
    bar = CommandBar()
    qtbot.addWidget(bar)
    bar.show()
    bar.set_clients_from(DATA)
    bar.client_selector.showPopup()
    popup = bar.client_selector.popup
    assert popup is not None and popup.isVisible()
    return bar, popup


def _visible(popup):
    p = popup.proxy
    return [(p.index(r, 0).data(Qt.UserRole), p.index(r, 0).data(Qt.DisplayRole)) for r in range(p.rowCount())]


def test_the_popup_opens_with_an_empty_focused_filter(qtbot):
    _bar, popup = _open(qtbot)
    assert popup.filter_edit.text() == ""
    assert popup.filter_edit.placeholderText() == "Filter clients"


def test_typing_keeps_matching_clients_and_their_section(qtbot):
    _bar, popup = _open(qtbot)
    popup.filter_edit.setText("acm")
    rows = _visible(popup)
    assert (ROW_SECTION, "Retail") in rows
    assert (ROW_CLIENT, "Acme Ltd") in rows
    assert (ROW_CLIENT, "Beta") not in rows
    assert (ROW_SECTION, "All Clients") not in rows  # its only client, Zed, is hidden
    assert any(k == ROW_ACTION for k, _t in rows)


def test_the_filter_matches_the_id_too(qtbot):
    _bar, popup = _open(qtbot)
    popup.filter_edit.setText("zed")
    assert (ROW_CLIENT, "Zed Shop") in _visible(popup)


def test_enter_picks_the_first_visible_client(qtbot):
    bar, popup = _open(qtbot)
    seen = []
    bar.clientChanged.connect(seen.append)
    popup.filter_edit.setText("beta")
    qtbot.keyClick(popup.filter_edit, Qt.Key_Return)
    assert seen == ["BETA"]
    assert not popup.isVisible()


def test_a_filter_matching_nothing_keeps_the_actions_and_enter_does_nothing(qtbot):
    bar, popup = _open(qtbot)
    seen = []
    bar.clientChanged.connect(seen.append)
    popup.filter_edit.setText("qqq")
    rows = _visible(popup)
    assert not any(k == ROW_CLIENT for k, _t in rows)
    assert sum(k == ROW_ACTION for k, _t in rows) == 4
    qtbot.keyClick(popup.filter_edit, Qt.Key_Return)
    assert seen == []


def test_down_skips_sections(qtbot):
    _bar, popup = _open(qtbot)
    qtbot.keyClick(popup.filter_edit, Qt.Key_Down)
    current = popup.list_view.currentIndex()
    assert current.data(Qt.UserRole) in (ROW_CLIENT, ROW_ACTION)


def test_escape_closes_without_a_change(qtbot):
    bar, popup = _open(qtbot)
    seen = []
    bar.clientChanged.connect(seen.append)
    qtbot.keyClick(popup.filter_edit, Qt.Key_Escape)
    assert not popup.isVisible()
    assert seen == []


def test_an_action_row_still_works_from_the_popup(qtbot):
    bar, popup = _open(qtbot)
    asked = []
    bar.createClientRequested.connect(lambda: asked.append(True))
    popup.filter_edit.setText("zzz")
    proxy = popup.proxy
    row = next(r for r in range(proxy.rowCount()) if proxy.index(r, 0).data(Qt.DisplayRole) == "New client…")
    popup.pick(proxy.index(row, 0))
    assert asked == [True]
```

- [ ] **Step 2: Run, expect FAIL** (`AttributeError: popup`).
- [ ] **Step 3: Implement.**

```python
class _ClientFilter(QSortFilterProxyModel):
    """Clients whose name or ID holds the text; a caption while it still has
    one; the divider and the actions always."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._text = ""

    def set_text(self, text: str) -> None:
        self._text = text.strip().casefold()
        self.invalidateFilter()

    def _client_matches(self, row: int) -> bool:
        index = self.sourceModel().index(row, 0)
        name = (index.data(Qt.DisplayRole) or "").casefold()
        cid = (index.data(ROLE_CLIENT_ID) or "").casefold()
        return self._text in name or self._text in cid

    def filterAcceptsRow(self, row, parent) -> bool:
        if not self._text:
            return True
        model = self.sourceModel()
        kind = model.index(row, 0).data(Qt.UserRole)
        if kind == ROW_CLIENT:
            return self._client_matches(row)
        if kind == ROW_SECTION and model.index(row, 0).data(Qt.DisplayRole):
            nxt = row + 1
            while nxt < model.rowCount() and model.index(nxt, 0).data(Qt.UserRole) == ROW_CLIENT:
                if self._client_matches(nxt):
                    return True
                nxt += 1
            return False
        return True  # blank divider, actions


class _ClientPopup(QFrame):
    """The open client list: a filter field over the combo's own rows."""

    _MIN_WIDTH = 280
    _MAX_HEIGHT = 420

    def __init__(self, combo: "_ClientCombo"):
        super().__init__(combo, Qt.Popup)
        self.combo = combo
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        self.filter_edit = QLineEdit(self)
        self.filter_edit.setPlaceholderText("Filter clients")
        self.filter_edit.setClearButtonEnabled(True)
        self.proxy = _ClientFilter(self)
        self.proxy.setSourceModel(combo.model())
        self.list_view = QListView(self)
        self.list_view.setModel(self.proxy)
        self.list_view.setItemDelegate(_ClientRowDelegate(self.list_view))
        self.list_view.setUniformItemSizes(True)
        layout.addWidget(self.filter_edit)
        layout.addWidget(self.list_view)
        self.filter_edit.textChanged.connect(self._on_text)
        self.filter_edit.installEventFilter(self)
        self.list_view.clicked.connect(self.pick)

    def _pickable(self, index) -> bool:
        return index.isValid() and index.data(Qt.UserRole) in (ROW_CLIENT, ROW_ACTION)

    def _first_client(self):
        for r in range(self.proxy.rowCount()):
            index = self.proxy.index(r, 0)
            if index.data(Qt.UserRole) == ROW_CLIENT:
                return index
        return QModelIndex()

    def _on_text(self, text: str) -> None:
        self.proxy.set_text(text)
        self.list_view.setCurrentIndex(self._first_client())

    def _step(self, delta: int) -> None:
        r = self.list_view.currentIndex().row()
        r = -1 if r < 0 and delta > 0 else (self.proxy.rowCount() if r < 0 else r)
        r += delta
        while 0 <= r < self.proxy.rowCount():
            index = self.proxy.index(r, 0)
            if self._pickable(index):
                self.list_view.setCurrentIndex(index)
                return
            r += delta

    def eventFilter(self, obj, event) -> bool:
        if obj is self.filter_edit and event.type() == QEvent.KeyPress:
            key = event.key()
            if key in (Qt.Key_Down, Qt.Key_Up):
                self._step(1 if key == Qt.Key_Down else -1)
                return True
            if key in (Qt.Key_Return, Qt.Key_Enter):
                index = self.list_view.currentIndex()
                if not self._pickable(index):
                    index = self._first_client()
                if index.isValid():
                    self.pick(index)
                return True
            if key == Qt.Key_Escape:
                self.close()
                return True
        return super().eventFilter(obj, event)

    def pick(self, index) -> None:
        if not self._pickable(index):
            return
        row = self.proxy.mapToSource(index).row()
        self.close()
        if index.data(Qt.UserRole) == ROW_CLIENT:
            self.combo.setCurrentIndex(row)
        self.combo.activated.emit(row)

    def open_under(self) -> None:
        combo = self.combo
        self.filter_edit.clear()
        width = max(combo.width(), self._MIN_WIDTH)
        rows = max(self.proxy.rowCount(), 1)
        height = min(self.list_view.sizeHintForRow(0) * rows + self.filter_edit.sizeHint().height() + 16,
                     self._MAX_HEIGHT)
        self.setGeometry(QRect(combo.mapToGlobal(combo.rect().bottomLeft()), QSize(width, height)))
        current = self.proxy.mapFromSource(combo.model().index(combo.currentIndex(), 0))
        if current.isValid():
            self.list_view.setCurrentIndex(current)
        self.show()
        self.filter_edit.setFocus()
```

  In `_ClientCombo`:

```python
    popup = None
    on_popup = None  # CommandBar sets it to wire the context menu onto the popup's list

    def showPopup(self) -> None:
        if self.popup is None:
            self.popup = _ClientPopup(self)
            if self.on_popup is not None:
                self.on_popup(self.popup)
        self.popup.open_under()

    def hidePopup(self) -> None:
        if self.popup is not None and self.popup.isVisible():
            self.popup.close()
        super().hidePopup()
```

  Context menu (right-click a client row opens the per-client menu): in `CommandBar.__init__` replace the three
  lines that wire `view = self.client_selector.view()` with

```python
        self._wire_context_menu(self.client_selector.view())
        self.client_selector.on_popup = lambda popup: self._wire_context_menu(popup.list_view)
```

  and add

```python
    def _wire_context_menu(self, view) -> None:
        view.setContextMenuPolicy(Qt.CustomContextMenu)
        view.customContextMenuRequested.connect(
            lambda pos, v=view: self._on_row_context_menu(pos, v)
        )
```

  Change `_on_row_context_menu(self, position)` to `_on_row_context_menu(self, position, view)`: drop its own
  `view = self.client_selector.view()` line, and after `index = view.indexAt(position)` map a proxy index to the
  source row: `row = view.model().mapToSource(index).row() if isinstance(view.model(), QSortFilterProxyModel)
  else index.row()`, then `item = self.client_selector.model().item(row)`. Add a test to `tests/test_client_popup.py`:
  `bar.clientMenuRequested` fires with `"ACME"` when `popup.list_view.customContextMenuRequested` is emitted with
  the position of ACME's row (`popup.list_view.visualRect(proxy_index).center()`).

  Imports: `QSortFilterProxyModel, QModelIndex, QEvent, QRect, QSize` from `PySide6.QtCore`; `QFrame, QLineEdit,
  QListView, QVBoxLayout` from `PySide6.QtWidgets` (some may already be imported).

  Theming: the popup is parented to the combo, so the app-wide QSS rule `QComboBox QAbstractItemView` (see
  `tests/test_components_commandbar.py::test_the_popup_scrollbar_is_themed_not_native`) reaches its list. Give
  the frame a border with a theme token through `on_theme_changed` exactly as other widgets in this file do
  (`QFrame { background: {theme.background}; border: 1px solid {theme.border}; }`).
  Render it like Task 8 (filter "ac", light + dark), save PNGs in your job tmp dir, and look at them.
- [ ] **Step 4: Run** `tests/test_client_popup.py tests/test_components_commandbar.py tests/test_shell.py` — PASS.
- [ ] **Step 5: Commit** `feat: type to filter the client list`.

---

### Task 10: Creation dialog — copy settings from, live ID check

Spec: A3 › Dialog.

**Files:**
- Modify: `gui/client_settings_dialog.py` (`ClientCreationDialog`, lines 40-208), `gui/client_directory.py`
  (`gather` 38-72, `open_create_client_dialog` 176)
- Test: `tests/test_client_creation_dialog.py` (new). Move the existing creation-dialog tests out of
  `tests/test_client_settings_dialog.py` into this file (keep them passing; Task 14 deletes the old file).

**Interfaces:**
- Consumes: Task 3 `create_client_profile(..., ui_settings=, copy_from=)`.
- Produces: `ClientCreationDialog(profile_manager, groups_manager=None, parent=None, clients: list[tuple[str, str]]
  | None = None, archived_ids: list[str] | None = None)`; attributes `copy_combo: QComboBox`,
  `create_button: QPushButton`. `ClientDirectory.gather()` result gains `"archived_ids": list[str]`;
  `ClientDirectory.last_data: dict | None` (the last gathered dict).

- [ ] **Step 1: Write the failing tests** — `tests/test_client_creation_dialog.py` (plus the moved tests):

```python
from gui.client_settings_dialog import ClientCreationDialog


def _dialog(pm, **kw):
    return ClientCreationDialog(
        profile_manager=pm,
        clients=kw.get("clients", [("SRC", "Source Co")]),
        archived_ids=kw.get("archived_ids", ["OLD"]),
    )


def test_copy_from_lists_defaults_then_clients(qapp, profile_manager):
    d = _dialog(profile_manager)
    assert [d.copy_combo.itemText(i) for i in range(d.copy_combo.count())] == ["Defaults", "Source Co  (SRC)"]
    assert d.copy_combo.itemData(0) is None
    assert d.copy_combo.itemData(1) == "SRC"


def test_the_id_is_checked_as_you_type(qapp, profile_manager):
    d = _dialog(profile_manager)
    d.client_id_input.setText("src")
    assert "CLIENT_SRC already exists." in d.client_id_error.text()
    assert not d.create_button.isEnabled()
    d.client_id_input.setText("old")
    assert "CLIENT_OLD is archived. Restore it from Archived clients." in d.client_id_error.text()
    d.client_id_input.setText("bad id!")
    assert d.client_id_error.text()  # validate_client_id's own message
    assert not d.create_button.isEnabled()
    d.client_id_input.setText("NEW")
    assert d.client_id_error.text() == ""
    assert d.create_button.isEnabled()


def test_create_writes_look_and_copied_settings_at_once(qapp, profile_manager):
    pm = profile_manager
    assert pm.create_client_profile("SRC", "Source Co")
    d = _dialog(pm)
    d.client_id_input.setText("NEW")
    d.client_name_input.setText("New Co")
    d.copy_combo.setCurrentIndex(1)
    d.pin_checkbox.setChecked(True)
    d.validate_and_accept()
    assert pm.get_ui_settings("NEW")["is_pinned"] is True
    assert pm.load_shopify_config("NEW")["client_name"] == "New Co"
```

  `client_id_error` is the existing `InlineMessage` (see `gui/components/inline_message.py` for how to read its
  text — if it has no `text()`, read its inner label the way the old tests in `test_client_settings_dialog.py` do,
  and use that in these asserts). `create_button` is the dialog's OK/Create button — find it in the dialog's
  `QDialogButtonBox` and store it as an attribute.

- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.**
  - Constructor gains `clients=None, archived_ids=None`; stores `self._live = {cid.upper() for cid, _n in clients or []}`
    and `self._archived = {a.upper() for a in archived_ids or []}`.
  - Add the **Copy settings from** `QComboBox` row after Client Name: `addItem("Defaults", None)` then for each
    `(cid, name)` `addItem(f"{name}  ({cid})" if name and name != cid else cid, cid)`.
  - `self.client_id_input.textChanged.connect(self._check_id)`:

```python
    def _check_id(self, text: str) -> None:
        cid = text.strip().upper()
        problem = ""
        if cid:
            ok, message = ProfileManager.validate_client_id(cid)
            if not ok:
                problem = message
            elif cid in self._live:
                problem = f"CLIENT_{cid} already exists."
            elif cid in self._archived:
                problem = f"CLIENT_{cid} is archived. Restore it from Archived clients."
        if problem:
            self.client_id_error.show_message(problem)
        else:
            self.client_id_error.clear()  # use InlineMessage's real clear/hide method
        self.create_button.setEnabled(bool(cid) and not problem)
```

    Call `self._check_id("")` at the end of `__init__` (Create starts disabled).
  - `validate_and_accept`: call `self.profile_manager.create_client_profile(client_id, client_name,
    ui_settings={"is_pinned": ..., "group_id": self.group_combo.currentData(), "custom_color": self.current_color},
    copy_from=self.copy_combo.currentData())` and delete the separate `update_ui_settings` call. Keep the error
    handling. The False branch message becomes "CLIENT_X already exists or is archived."
  - `ClientDirectory.gather()`: add `"archived_ids": [c["client_id"] for c in self.profile_manager.list_archived_clients()]`.
    In `__init__` set `self.last_data = None` and connect `self.loaded.connect(self._remember)` with
    `def _remember(self, data): self.last_data = data`.
  - `open_create_client_dialog`: pass
    `clients=[(cid, (data["card_data"].get(cid, {}).get("client_name") or cid)) for cid in data["all_clients"]]`
    and `archived_ids=data.get("archived_ids", [])` where `data = self.last_data or {"all_clients": [], "card_data": {}}`.
- [ ] **Step 4: Run** `tests/test_client_creation_dialog.py tests/test_client_settings_dialog.py tests/test_client_directory.py` — PASS.
- [ ] **Step 5: Commit** `feat: new clients can copy another client's settings; the ID is checked as you type`.

---

### Task 11: `ProfileDraft`

Spec: A4 › `ProfileDraft`.

**Files:**
- Create: `gui/settings/profile_state.py`
- Test: `tests/test_settings_draft_profile.py` (new; mirror the style of `tests/test_settings_draft_general.py`)

**Interfaces:**
- Consumes: `PageContract` from `gui/settings/contract.py`.
- Produces: `ProfileDraft(client_id: str, client_config: dict, groups: list[dict], stats: dict, has_sessions: bool)`
  with `apply(action, args) -> bool`, `collect() -> {}`, `blocker() -> str | None`, `blocker_key() -> str`,
  `snapshot() -> str`, `profile_updates() -> dict | None`, `mark_clean(snapshot=None)`, `view() -> dict`.
  Edit actions: `"profile_name" [text]`, `"profile_group" [group_id or ""]`, `"profile_colour" [hex]`,
  `"profile_pin" []`.

- [ ] **Step 1: Write the failing tests:**

```python
from gui.settings.profile_state import ProfileDraft

CONFIG = {
    "client_id": "ACME",
    "client_name": "Acme Ltd",
    "ui_settings": {"is_pinned": False, "group_id": "g1", "custom_color": "#112233"},
}
GROUPS = [{"id": "g1", "name": "Retail"}, {"id": "g2", "name": "Wholesale"}]
STATS = {"total_sessions": 3, "last_session_date": "2026-10-14", "last_accessed": None}


def _draft(has_sessions=True):
    return ProfileDraft("ACME", CONFIG, GROUPS, STATS, has_sessions)


def test_nothing_changed_means_no_profile_update():
    assert _draft().profile_updates() is None
    assert _draft().collect() == {}


def test_edits_become_one_profile_update():
    d = _draft()
    assert d.apply("profile_name", ["Acme Group"])
    assert d.apply("profile_group", [""])
    assert d.apply("profile_colour", ["#abcdef"])
    assert d.apply("profile_pin", [])
    assert d.profile_updates() == {
        "client_name": "Acme Group",
        "ui_settings": {"group_id": None, "custom_color": "#abcdef", "is_pinned": True},
    }


def test_a_repeat_or_unknown_edit_changes_nothing():
    d = _draft()
    assert not d.apply("profile_name", ["Acme Ltd"])
    assert not d.apply("profile_group", ["g1"])
    assert not d.apply("nope", [])
    assert not d.apply("profile_name", [3])


def test_an_empty_name_blocks_the_save():
    d = _draft()
    d.apply("profile_name", ["  "])
    assert d.blocker() == "Set Client name"
    assert d.blocker_key() == "profile-name"


def test_the_snapshot_follows_the_edits_and_mark_clean_resets():
    d = _draft()
    before = d.snapshot()
    d.apply("profile_pin", [])
    assert d.snapshot() != before
    d.mark_clean()
    assert d.profile_updates() is None


def test_the_view_carries_the_fields_stats_and_danger_actions():
    v = _draft(has_sessions=True).view()
    assert v["page"] == "profile" and v["title"] == "Profile"
    p = v["profile"]
    assert p["name"]["value"] == "Acme Ltd"
    assert p["client_id"] == "ACME"
    assert [o["label"] for o in p["groups"]] == ["No group", "Retail", "Wholesale"]
    assert [o["checked"] for o in p["groups"]] == [False, True, False]
    assert p["colour"] == "#112233" and p["pinned"] is False
    assert p["stats"] == [
        {"label": "Sessions", "value": "3"},
        {"label": "Last session", "value": "2026-10-14"},
        {"label": "Last accessed", "value": "Unknown"},
    ]
    assert p["delete"]["enabled"] is False
    assert "can only be archived" in p["delete"]["hint"]
    assert _draft(has_sessions=False).view()["profile"]["delete"]["enabled"] is True
```

- [ ] **Step 2: Run, expect FAIL** (module missing).
- [ ] **Step 3: Implement** `gui/settings/profile_state.py`. Read `PageContract` in `gui/settings/contract.py`
  for `mark_clean`/`current_snapshot` semantics first (lines 80-100) and keep them: store the clean snapshot
  string and compare with it.

```python
"""The Client > Profile page: name, group, colour, pin (spec A4).

Owns no shopify_config.json key: collect() is empty and the window writes
profile_updates() to client_config.json. No Qt import.
"""

import json

from gui.settings.contract import PageContract

NO_GROUP = "No group"


def _shaped(args, *types) -> bool:
    return isinstance(args, list) and len(args) == len(types) and all(
        isinstance(a, t) for a, t in zip(args, types)
    )


class ProfileDraft(PageContract):
    def __init__(self, client_id, client_config, groups, stats, has_sessions):
        ui = client_config.get("ui_settings") or {}
        self.client_id = client_id
        self.groups = list(groups)
        self.stats = stats or {}
        self.has_sessions = bool(has_sessions)
        self.name = str(client_config.get("client_name") or client_id)
        self.group_id = ui.get("group_id") or None
        self.colour = str(ui.get("custom_color") or "")
        self.pinned = bool(ui.get("is_pinned", False))
        self._clean = self.snapshot()

    def apply(self, action, args) -> bool:
        if action == "profile_name" and _shaped(args, str):
            if args[0] == self.name:
                return False
            self.name = args[0]
            return True
        if action == "profile_group" and _shaped(args, str):
            value = args[0] or None
            if value == self.group_id:
                return False
            self.group_id = value
            return True
        if action == "profile_colour" and _shaped(args, str):
            if args[0] == self.colour:
                return False
            self.colour = args[0]
            return True
        if action == "profile_pin" and args == []:
            self.pinned = not self.pinned
            return True
        return False

    def collect(self) -> dict:
        return {}

    def blocker(self):
        return "Set Client name" if not self.name.strip() else None

    def blocker_key(self) -> str:
        return "profile-name"

    def snapshot(self) -> str:
        return json.dumps([self.name, self.group_id, self.colour, self.pinned])

    def mark_clean(self, snapshot=None) -> None:
        self._clean = snapshot if snapshot is not None else self.snapshot()

    def profile_updates(self):
        if self.snapshot() == self._clean:
            return None
        return {
            "client_name": self.name.strip(),
            "ui_settings": {
                "group_id": self.group_id,
                "custom_color": self.colour,
                "is_pinned": self.pinned,
            },
        }

    def _stat(self, key, empty):
        value = self.stats.get(key)
        return empty if value in (None, "") else str(value)

    def view(self) -> dict:
        cid = self.client_id
        return {
            "page": "profile",
            "title": "Profile",
            "subtitle": f"How {self.name.strip() or cid} appears in the client list.",
            "action": "",
            "profile": {
                "name": {"value": self.name, "problem": "Enter a name." if not self.name.strip() else ""},
                "client_id": cid,
                "groups": [{"value": "", "label": NO_GROUP, "checked": self.group_id is None}]
                + [
                    {"value": g.get("id", ""), "label": g.get("name", "Unknown"), "checked": g.get("id") == self.group_id}
                    for g in self.groups
                ],
                "colour": self.colour,
                "pinned": self.pinned,
                "stats": [
                    {"label": "Sessions", "value": self._stat("total_sessions", "0")},
                    {"label": "Last session", "value": self._stat("last_session_date", "Never")},
                    {"label": "Last accessed", "value": self._stat("last_accessed", "Unknown")},
                ],
                "archive": {
                    "label": "Archive client…",
                    "hint": f"Hides {cid} in Fulfilment and Packing. Its sessions are kept and it can be "
                    "restored from Archived clients.",
                },
                "delete": {
                    "label": "Delete client…",
                    "enabled": not self.has_sessions,
                    "hint": f"{cid} has sessions, so it can only be archived."
                    if self.has_sessions
                    else f"Removes {cid} and its folders for good.",
                },
            },
        }
```

  If `PageContract.mark_clean`/`current_snapshot` have a different contract (the window calls
  `page.current_snapshot()` and `page.mark_clean(snapshot)`), make `ProfileDraft` satisfy that contract exactly
  — read the base class and `tests/test_settings_page_contract.py`, and add `ProfileDraft` to any parametrised
  list of drafts there.
- [ ] **Step 4: Run** `tests/test_settings_draft_profile.py tests/test_settings_page_contract.py` — PASS.
- [ ] **Step 5: Commit** `feat: a Profile settings draft for a client's name, group, colour and pin`.

---

### Task 12: The Profile web page

Spec: A4 › Web page.

**Files:**
- Create: `gui/web/settings_profile.js`
- Modify: `gui/web/settings.html` (script tag), `gui/web/settings.js` (`LIST_PAGES`), `gui/settings/bridge.py`
  (signal + slot), `gui/settings/web_host.py` (re-emit), `gui/web/settings.css` (only if a needed style is missing)
- Test: `tests/test_settings_profile_page.py` (new; copy the `page` fixture and helpers pattern from
  `tests/test_settings_lists_page.py` lines 1-121)

**Interfaces:**
- Consumes: Task 11 `ProfileDraft.view()` keys.
- Produces: `SettingsBridge.clientActionRequested = Signal(str)`, slot `clientAction(kind: str)`;
  `SettingsWebHost.clientActionRequested = Signal(str)`; JS functions `profilePage(p)`, `profileClick(data, el,
  bridge) -> bool`, `profileInput(data, el, bridge) -> bool`.

- [ ] **Step 1: Write the failing tests** (Chromium-driven, like `test_settings_lists_page.py`; never skip):
  1. pushing `ProfileDraft(...).view()` draws the name field (`[data-key="profile-name"]` value "Acme Ltd"), the
     ID text, three stat rows, and two danger buttons; Delete is `disabled` when `has_sessions=True`;
  2. typing in the name field sends `edit("profile_name", ["Acme G"])` (use the file's `_type` helper and read
     what the bridge got, as the lists tests do);
  3. clicking the pin switch sends `edit("profile_pin", [])`;
  4. choosing "Wholesale" in the group menu sends `edit("profile_group", ["g2"])`;
  5. setting the colour input (`el.value = "#abcdef"; el.dispatchEvent(new Event("input", {bubbles: true}))`
     via `_eval`) sends `edit("profile_colour", ["#abcdef"])`;
  6. clicking Archive emits `clientActionRequested("archive")` on the bridge; clicking an enabled Delete emits
     `clientActionRequested("delete")`.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.**
  - `bridge.py`: `clientActionRequested = Signal(str)` beside the other signals;
    `@Slot(str) def clientAction(self, kind): if kind in ("archive", "delete"): self.clientActionRequested.emit(kind)`.
  - `web_host.py`: `clientActionRequested = Signal(str)`; where the host connects the bridge's other signals,
    connect `bridge.clientActionRequested` to `self.clientActionRequested.emit`.
  - `settings_profile.js` (header comment like `settings_tags.js`'s; uses `esc`, `svg`, `GLYPH`, `menuItem`,
    `ruleSelect`, `under`/`problemLine`, `off` exactly as `settings_tags.js` does):

```javascript
// The Client > Profile page (spec A4). settings.js renders and routes; this
// file draws what bridge.state holds under `profile`. Python holds every
// value and words every sentence (gui/settings/profile_state.py).
"use strict";

function profilePage(p) {
  const group = p.groups.find((o) => o.checked) || p.groups[0];
  const groupMenu = () =>
    p.groups
      .map((o, n) => menuItem("profile-group", { value: o.value }, o.label, "", o.checked, `profile-group-item-${n}`))
      .join("");
  const stats = p.stats
    .map((s) => `<div class="stat-row"><dt>${esc(s.label)}</dt><dd>${esc(s.value)}</dd></div>`)
    .join("");
  return `<section class="settings-section">
    <div class="editor-line"><span class="editor-label">Name</span><div class="editor-content">
      <input class="field${p.name.problem ? " invalid" : ""}" type="text" value="${esc(p.name.value)}" aria-label="Client name" data-input="profile_name" data-key="profile-name">
      ${p.name.problem ? problemLine(p.name.problem) : ""}
    </div></div>
    <div class="editor-line"><span class="editor-label">Client ID</span><div class="editor-content"><span class="mono">${esc(p.client_id)}</span></div></div>
    <div class="editor-line"><span class="editor-label">Group</span><div class="editor-content">
      ${ruleSelect("profile-group", "Group", group.label, false, groupMenu, "profile-group")}
    </div></div>
    <div class="editor-line"><span class="editor-label">Colour</span><div class="editor-content">
      <input type="color" value="${esc(p.colour || "#000000")}" aria-label="Client colour" data-input="profile_colour" data-key="profile-colour">
    </div></div>
    <div class="editor-line"><span class="editor-label">Pinned</span><div class="editor-content">
      <button class="switch" type="button" role="switch" aria-checked="${Boolean(p.pinned)}" aria-label="Pinned" data-act="profile-pin" data-key="profile-pin"><span class="switch-knob"></span></button>
    </div></div>
  </section>
  <section class="settings-section"><h2 class="section-title">Statistics</h2><dl class="stats">${stats}</dl></section>
  <section class="settings-section danger"><h2 class="section-title">Danger zone</h2>
    <div class="editor-line"><div class="editor-content">
      <button class="btn secondary" type="button" data-act="profile-archive" data-key="profile-archive">${esc(p.archive.label)}</button>
      <span class="hint">${esc(p.archive.hint)}</span>
    </div></div>
    <div class="editor-line"><div class="editor-content">
      <button class="btn secondary" type="button" data-act="profile-delete" data-key="profile-delete"${off(!p.delete.enabled)}>${esc(p.delete.label)}</button>
      <span class="hint">${esc(p.delete.hint)}</span>
    </div></div>
  </section>`;
}

function profileClick(data, el, bridge) {
  switch (data.act) {
    case "profile-pin": bridge.edit("profile_pin", []); return true;
    case "profile-group": bridge.edit("profile_group", [data.value]); closeMenu(); return true;
    case "profile-archive": bridge.clientAction("archive"); return true;
    case "profile-delete": bridge.clientAction("delete"); return true;
  }
  return false;
}

function profileInput(data, el, bridge) {
  if (data.input === "profile_name") { bridge.edit("profile_name", [el.value]); return true; }
  if (data.input === "profile_colour") { bridge.edit("profile_colour", [el.value]); return true; }
  return false;
}
```

    Check the real signatures of `menuItem`, `ruleSelect`, `problemLine`, `off` in `settings.js`/
    `settings_rules.js` before using them and adapt the calls (e.g. how `menuItem` puts `data-value`); match
    the class names the existing pages use (`settings-section`, `editor-line`, `section-title` — use whatever the
    General and Tags pages actually emit; add a CSS rule to `settings.css` only for `dl.stats`, using existing
    CSS variables).
  - `settings.html`: `<script src="settings_profile.js" defer></script>` after `settings_tags.js`, before
    `settings.js`.
  - `settings.js`: add `profile: [profilePage, profileClick, profileInput],` to `LIST_PAGES`.
  - Render check: open the page with a `ProfileDraft` view in both themes, grab the view to PNGs in your job tmp
    dir, look at them.
- [ ] **Step 4: Run** `tests/test_settings_profile_page.py tests/test_settings_lists_page.py tests/test_settings_web_page.py tests/test_settings_bridge.py` — PASS.
- [ ] **Step 5: Commit** `feat: the Client > Profile settings page`.

---

### Task 13: `SettingsWindow` — Profile nav, one save for both files, Archive/Delete

Spec: A4 › Navigation, Saving, Archive / Delete from the page.

**Files:**
- Modify: `gui/settings/window.py` (constants 70-95, `SETTINGS_NAV_GROUPS` 135, `__init__` 145-345,
  `save_settings` 822-880, `_on_save_settings_result`)
- Test: `tests/test_settings_profile_window.py` (new); update `tests/test_settings_nav.py` only where the first
  entry is asserted

**Interfaces:**
- Consumes: Task 11 `ProfileDraft`; Task 12 `SettingsWebHost.clientActionRequested`; Task 1
  `ConfirmDialog.ask(..., require_text=)`.
- Produces: `SettingsWindow(..., profile: dict | None = None)` where `profile = {"client_config": dict,
  "groups": list, "stats": dict, "has_sessions": bool}`; attributes `removed_client: str | None` (`"archived"` /
  `"deleted"`), `profile_saved: bool`.

- [ ] **Step 1: Write the failing tests.** Build the window the way `tests/test_settings_nav.py`'s `window`
  fixture does, adding `profile=PROFILE`; use a real `profile_manager` fixture where a save is checked:
  1. with `profile`, the nav's first group is "Client" with "Profile"; without it, "Profile" is absent;
  2. editing only the Profile name and pressing Save calls `save_shopify_config` and then
     `update_client_profile(client_id, name="New", ui_settings={...})` (monkeypatch both on the profile manager to
     record calls and return True); `profile_saved` is True after the result;
  3. Save with no Profile edit does not call `update_client_profile`;
  4. `save_shopify_config` returning False → `update_client_profile` not called and the existing error is shown;
  5. `_on_client_action("archive")` with `ConfirmDialog.ask` monkeypatched to return True sets
     `removed_client == "archived"` and the dialog result is `Rejected`; with `ask` returning False nothing
     changes;
  6. `_on_client_action("delete")` passes `require_text=<client id>` to `ConfirmDialog.ask`.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.**
  - Constants: `SETTINGS_SEARCH_KEYWORDS["Profile"] = ["name", "group", "colour", "color", "pin", "archive",
    "delete"]`; `WEB_PAGE_KEYS["Profile"] = "profile"`; `SETTINGS_NAV_GROUPS` gets `("Client", ["Profile"])`
    first.
  - `__init__`: new keyword `profile=None`; `self.removed_client = None`; `self.profile_saved = False`;
    `self._profile_draft = None`. When `profile` is given, build
    `ProfileDraft(client_id, profile["client_config"], profile["groups"], profile["stats"], profile["has_sessions"])`,
    put it in `drafts["profile"]` and add `"Profile"` first to the tuple the pages are added in. When `profile`
    is None, the nav must not show "Profile": filter `SETTINGS_NAV_GROUPS` in `_build_settings_nav` (or wherever
    it iterates them) to page names in `self._pages_by_name`. Connect
    `self._web_host.clientActionRequested.connect(self._on_client_action)`.
  - `save_settings`: replace the `Worker(self.profile_manager.save_shopify_config, self.client_id, written)` with

```python
        profile = self._profile_draft.profile_updates() if self._profile_draft else None
        self._saving_profile = profile is not None
        worker = Worker(self._save_all, self.client_id, written, profile)
```

    and add

```python
    def _save_all(self, client_id, written, profile) -> bool:
        """Worker thread: the settings file, then the profile when it changed."""
        if not self.profile_manager.save_shopify_config(client_id, written):
            return False
        if profile is None:
            return True
        return bool(
            self.profile_manager.update_client_profile(
                client_id, name=profile["client_name"], ui_settings=profile["ui_settings"]
            )
        )
```

    In `_on_save_settings_result`, on success: `if self._saving_profile: self.profile_saved = True`.
  - `_on_client_action`:

```python
    def _on_client_action(self, kind: str) -> None:
        label = f"CLIENT_{self.client_id}"
        lost = " Unsaved changes in this window will be lost." if self.refresh_dirty() else ""
        if kind == "archive":
            ok = ConfirmDialog.ask(
                self,
                title=f"Archive {label}?",
                body="It disappears from the client list in Fulfilment and Packing on every PC. "
                "Sessions are kept. Restore it from Archived clients." + lost,
                verb="Archive",
            )
        elif kind == "delete":
            ok = ConfirmDialog.ask(
                self,
                title=f"Delete {label} for good?",
                body="Its settings and empty session folder are removed. This can't be undone." + lost,
                verb="Delete",
                require_text=self.client_id,
            )
        else:
            return
        if ok:
            self.removed_client = "archived" if kind == "archive" else "deleted"
            self.done(QDialog.Rejected)
```

    Import `ConfirmDialog` the way `gui/main_window_pyside.py` does (`from gui.components import ConfirmDialog`)
    and `ProfileDraft` from `gui.settings.profile_state`. Check `refresh_dirty()` returns something truthy for
    unsaved pages; if it returns a list, `bool(list)` is right.
  - If closing via `done()` triggers the close guard for unsaved edits, bypass it for this path (set a flag the
    guard checks, e.g. `self._discarding = True`, whichever mechanism `reject`/`closeEvent` already uses).
- [ ] **Step 4: Run** `tests/test_settings_profile_window.py tests/test_settings_nav.py tests/test_settings_footer.py tests/test_settings_unsaved.py tests/test_settings_roundtrip.py` — PASS.
- [ ] **Step 5: Commit** `feat: Client settings edits the profile and can archive or delete the client`.

---

### Task 14: Open Profile for any client; retire `ClientSettingsDialog`

Spec: A4 › Callers.

**Files:**
- Modify: `gui/actions_handler.py:459-530` (`open_settings_window`), `gui/client_directory.py` (`menu_for`,
  `_edit_client`, imports, new signal), `gui/main_window_pyside.py` (~353-376 wiring)
- Delete: `ClientSettingsDialog` class from `gui/client_settings_dialog.py`; `tests/test_client_settings_dialog.py`
  (its creation-dialog tests were moved in Task 10 — check nothing else in it is still needed)
- Test: `tests/test_settings_entry_points.py` (update), `tests/test_client_directory.py` (append)

**Interfaces:**
- Consumes: Task 13 `SettingsWindow(profile=...)`, `.removed_client`, `.profile_saved`; Task 2
  `client_has_sessions`.
- Produces: `ActionsHandler.open_settings_window(page: str | None = None, client_id: str | None = None)`;
  `ClientDirectory.editClientRequested = Signal(str)`; calls `MainWindow.remove_client(client_id, kind)` (Task 15).

- [ ] **Step 1: Write the failing tests.**
  - `tests/test_client_directory.py`: the menu's "Edit Settings..." action emits `editClientRequested("ACME")`
    (build the menu with `menu_for("ACME", parent)`, find the action by text, `trigger()` it).
  - `tests/test_settings_entry_points.py`: read it first; replace any assertion about `ClientSettingsDialog`
    with: `open_settings_window(page="Profile", client_id="OTHER")` builds `SettingsWindow` with
    `client_id="OTHER"`, `initial_page="Profile"` and a `profile` dict holding `client_config`, `groups`,
    `stats`, `has_sessions` (monkeypatch `SettingsWindow` in `gui.actions_handler` with a recorder whose
    `exec()` returns 0, as the file's other tests do).
  - Append there: when the recorder sets `removed_client = "archived"`, `mw.remove_client` is called with
    `("OTHER", "archived")`; when `profile_saved` is True, `mw.client_directory.refresh` is called.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.**
  - `open_settings_window(self, page=None, client_id=None)`: `client_id = client_id or self.mw.current_client_id`;
    use it everywhere the method used `self.mw.current_client_id` for loading and building. Also load
    `client_config = self.mw.profile_manager.load_client_config(client_id) or {}`,
    `groups = self.mw.groups_manager.list_groups()`,
    `stats = self.mw.profile_manager.calculate_metadata(client_id)`,
    `has_sessions = self.mw.profile_manager.client_has_sessions(client_id)` in the same try block as the
    existing config load; pass `profile={...}`. `loaded_files` and `analysis_df`/`session_name` are passed only
    when `client_id == self.mw.current_client_id` (else `None`).
  - After `exec()`:

```python
        if settings_win.removed_client:
            self.mw.remove_client(client_id, settings_win.removed_client)
            return
        if settings_win.profile_saved:
            self.mw.client_directory.refresh()
        if saved and client_id == self.mw.current_client_id:
            ...existing reload/revalidate block...
```

    (keep `settings_win.deleteLater()` before these.)
  - `ClientDirectory`: `editClientRequested = Signal(str)`; `_edit_client(client_id, parent)` becomes
    `self.editClientRequested.emit(client_id)`; drop the `ClientSettingsDialog` import.
  - `MainWindow` wiring: `self.client_directory.editClientRequested.connect(lambda cid:
    self.actions_handler.open_settings_window(page="Profile", client_id=cid))`.
  - Delete `ClientSettingsDialog` and fix the module docstring (no "Advanced tab"). `rg ClientSettingsDialog`
    must return nothing.
- [ ] **Step 4: Run** `tests/test_settings_entry_points.py tests/test_client_directory.py tests/test_client_creation_dialog.py tests/test_shell.py` — PASS.
- [ ] **Step 5: Commit** `refactor: Edit Settings opens Client settings on Profile; the old dialog goes`.

---

### Task 15: Remove a client, Archived clients dialog, wiring

Spec: A6.

**Files:**
- Modify: `gui/main_window_pyside.py` (new `remove_client`, `open_archived_clients`; wire
  `command_bar.archivedClientsRequested`), `gui/client_settings_dialog.py` (new `ArchivedClientsDialog`)
- Test: `tests/test_client_removal.py` (new)

**Interfaces:**
- Consumes: Task 2 methods; Task 6 `set_current_client("")`; Task 7 `_reset_session_state(wait=)`; Task 8
  `archivedClientsRequested`.
- Produces: `MainWindow.remove_client(client_id: str, kind: str) -> None` (`kind` in `"archived"`, `"deleted"`);
  `MainWindow.open_archived_clients() -> None`; `ArchivedClientsDialog(clients: list[dict], restore: Callable[[str],
  None], parent=None)` with `table: QTableWidget`, `restore_button: QPushButton`, `empty_label: QLabel`,
  `remove_row(client_id)`.

- [ ] **Step 1: Write the failing tests** (reuse the MainWindow fixture Task 7 used; a real `profile_manager`
  under it so the folder moves happen in `tmp_path`):

```python
def test_archiving_the_current_client_clears_it_and_moves_the_folders(<window>, qtbot):
    win = <window>; cid = <current client id>
    win.remove_client(cid, "archived")
    assert win.current_client_id is None
    assert win.command_bar.current_client() == ""
    qtbot.waitUntil(lambda: (win.profile_manager.clients_dir / "_archive" / f"CLIENT_{cid}").exists(), timeout=5000)


def test_a_refused_archive_shows_its_reason(<window>, qtbot, monkeypatch):
    shown = []
    monkeypatch.setattr("gui.main_window_pyside.show_error", lambda _w, h, d: shown.append((h, d)))
    from shopify_tool.profile_manager import ProfileManagerError
    monkeypatch.setattr(<window>.profile_manager, "archive_client",
                        lambda cid: (_ for _ in ()).throw(ProfileManagerError("CLIENT_X is open on another PC. Close it there, then try again.")))
    <window>.remove_client("X", "archived")
    qtbot.waitUntil(lambda: shown, timeout=5000)
    assert shown[0] == ("CLIENT_X wasn't archived", "CLIENT_X is open on another PC. Close it there, then try again.")


def test_the_archived_dialog_lists_and_restores(qapp):
    restored = []
    from gui.client_settings_dialog import ArchivedClientsDialog
    d = ArchivedClientsDialog(
        [{"client_id": "OLD", "client_name": "Old Co", "archived_at": "2026-10-01T10:00:00+03:00"}],
        restore=restored.append,
    )
    assert d.table.rowCount() == 1
    assert d.table.item(0, 0).text() == "OLD"
    d.table.selectRow(0)
    d.restore_button.click()
    assert restored == ["OLD"]


def test_the_archived_dialog_says_when_there_are_none(qapp):
    from gui.client_settings_dialog import ArchivedClientsDialog
    d = ArchivedClientsDialog([], restore=lambda cid: None)
    assert d.empty_label.text() == "No archived clients."
    assert not d.restore_button.isEnabled()


def test_a_remembered_archived_client_opens_on_choose_a_client(qapp):
    from gui.components.commandbar import CommandBar
    bar = CommandBar()
    bar.set_current_client("GONE")  # remembered before the list arrives
    bar.set_clients_from({"special_groups": {}, "custom_groups": [], "all_clients": ["ACME"],
                          "pinned_client_ids": set(), "group_members": {}, "card_data": {}})
    assert bar.current_client() == ""
    assert bar.client_selector.currentIndex() == -1
```

  (Write the second test with a normal `def raise_(cid): raise ProfileManagerError(...)` instead of the generator
  trick if you prefer.) Also check how the app restores the last client at startup (`rg "last_client|restore_client"
  gui/`); if it calls `on_client_changed` with a client absent from the list, add a guard there that skips an ID not
  in `client_directory.last_data["all_clients"]`, and a test for it.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.**
  - `remove_client`:

```python
    def remove_client(self, client_id: str, kind: str) -> None:
        """Archive or delete a client (spec A6). The folder move runs in a
        worker after this PC's pending writes, so nothing here holds a file in it."""
        if client_id == self.current_client_id:
            self._reset_session_state(wait=False)
            self.session_path = None
            self.current_client_id = None
            self.command_bar.set_current_client("")
            self.command_bar.set_recent_sessions([])
            self.update_ui_state()
        act = self.profile_manager.archive_client if kind == "archived" else self.profile_manager.delete_client

        def run():
            self.write_queue.flush(timeout=10)
            act(client_id)
            return client_id, kind

        worker = Worker(run)
        worker.signals.result.connect(self._on_client_removed)
        worker.signals.error.connect(
            lambda error, cid=client_id, k=kind: self._on_client_remove_error(cid, k, error)
        )
        self._client_load_workers.add(worker)
        worker.signals.finished.connect(lambda: self._client_load_workers.discard(worker))
        self.threadpool.start(worker)

    def _on_client_removed(self, result) -> None:
        client_id, kind = result
        toast(self, f"CLIENT_{client_id} {kind}.")
        self.client_directory.refresh()

    def _on_client_remove_error(self, client_id, kind, error) -> None:
        _exctype, value, _tb = error
        verb = "archived" if kind == "archived" else "deleted"
        headline = f"CLIENT_{client_id} wasn't {verb}"
        if isinstance(value, ProfileManagerError):
            logger.warning(f"{headline}: {value}")
            show_error(self, headline, str(value))
        else:
            logger.error(headline, exc_info=value)
            show_error(self, headline, "Details are in Logs.")
        self.client_directory.refresh()
```

    Import `ProfileManagerError` from `shopify_tool.profile_manager` if not imported. Check `toast`'s real
    signature (`gui/components`); match how this file already calls it. `write_queue` may be absent in some test
    setups: use `getattr(self, "write_queue", None)` and skip the flush when None.
  - `open_archived_clients`: a `Worker(self.profile_manager.list_archived_clients)`; on result open
    `ArchivedClientsDialog(clients, restore=self._restore_client_from_dialog, parent=self)` with `exec()`;
    `_restore_client_from_dialog(cid)` runs `restore_client` in a `Worker`; on result:
    `dialog.remove_row(cid)` (keep a reference `self._archived_dialog`), `toast(self, f"CLIENT_{cid} restored.")`,
    `self.client_directory.refresh()`; on `ProfileManagerError`: `show_error(self, f"CLIENT_{cid} wasn't
    restored", str(value))`. Wire `self.command_bar.archivedClientsRequested.connect(self.open_archived_clients)`
    next to the other bar signals (~line 365).
  - `ArchivedClientsDialog` (in `gui/client_settings_dialog.py`): title "Archived clients"; `QTableWidget` 3
    columns "Client ID", "Name", "Archived" (date part of `archived_at`, `archived_at[:10]`), select rows, single
    selection, no edit triggers; `empty_label` "No archived clients." shown when the list is empty (table hidden);
    `restore_button` "Restore" enabled only with a selected row, calls `restore(selected_id)`; Close button via
    `QDialogButtonBox` with `apply_dialog_button_roles` (see how `ClientCreationDialog` builds its buttons);
    `remove_row(client_id)` removes that row and shows `empty_label` when none are left. Theme tokens only.
- [ ] **Step 4: Run** `tests/test_client_removal.py tests/test_client_switch.py tests/test_shell.py tests/test_dialog_button_guard.py` — PASS.
- [ ] **Step 5: Commit** `feat: archive and delete a client from the app; restore from Archived clients`.

---

### Task 16: Glossary, full gate, graph

Spec: Glossary.

**Files:**
- Modify: `CONTEXT.md`

- [ ] **Step 1:** Add the two entries from the spec's Glossary section to `CONTEXT.md`, in alphabetical position
  (read the surrounding entries and match their format):
  - **Archived client** — a client whose folders were moved into `Clients/_archive/` and `Sessions/_archive/`.
    Neither tool lists it; Archived clients… restores it. Not the session status "archived".
  - **Client profile** — a client's name, group, colour and pin, kept in `client_config.json` and edited on
    Client settings › Profile. Its fulfilment settings are in `shopify_config.json`.
- [ ] **Step 2:** Full gate, in the background (≈10 min): `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
  then `ruff check .`. Known: 3 `test_label_printing` ZPL tests also fail on main; report them, don't fix them.
  Fix anything else this branch broke.
- [ ] **Step 3:** `graphify update .`
- [ ] **Step 4: Commit** `docs: glossary for archived clients and the client profile`.
