# Tag Categories: Remove Ukrainian Defaults + Dialog Audit — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Ukrainian-localized tag-category defaults with English ones from a single source of truth, migrate existing client configs safely, and fix nine defects found in a full audit of `gui/tag_categories_dialog.py`.

**Architecture:** One `DEFAULT_TAG_CATEGORIES` constant in `shopify_tool/tag_manager.py` replaces three duplicated hardcoded blocks. A new exact-match-guarded migration relabels existing configs without touching tags. The dialog fixes are independent of the defaults work and are ordered so the signal-safety fix (Task 4) lands before the change that depends on it (Task 5).

**Tech Stack:** Python 3, PySide6, pytest, pandas. Desktop app, Windows-only in production, developed on Linux.

**Spec:** `docs/superpowers/specs/2026-08-14-tag-categories-design.md`

## Global Constraints

- Run everything through the repo venv: `.venv/bin/python`. Bare `python`/`python3`/`ruff` are not on PATH on this machine.
- Full test command: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest`
- Single test: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_x.py::test_y -v`
- Lint: `.venv/bin/ruff check . --exclude shared`
- **Never hand-edit anything under `shared/`** — it is one-way synced from `../packing-tool`.
- **No hardcoded colors in stylesheets.** Use `theme_manager` tokens. The existing literal `#9E9E9E` values in this dialog are pre-approved exceptions carrying `ponytail:` comments explaining why (persisted config defaults and swatch fills, not text colors) — leave those comments in place and do not add new literals without the same justification.
- The Bulgarian stock-export column names (`Артикул`, `Мярка`, `Брой`, `Годност`, `Партида`) are an external CSV format. **Do not touch them.** Only tag-category *labels* are being de-localized.
- Do not bump the version string. This change does not warrant it.
- Commit after every task. Do not use `--no-verify`, `--force`, or `--no-gpg-sign`.

**English label mapping (exact values, used verbatim in Tasks 1 and 2):**

| category id | old (Ukrainian) | new (English) |
|---|---|---|
| `packaging` | `Пакетаж` | `Packaging` |
| `priority` | `Пріоритет` | `Priority` |
| `status` | `Статус` | `Status` |
| `order_type` | `Тип замовлення` | `Order Type` |
| `accessories` | `Додатки` | `Accessories` |
| `delivery` | `Кур'єр/Доставка` | `Delivery` |
| `custom` | `Інші` | `Other` |

Note `Кур'єр/Доставка` contains U+2019 (right single quotation mark), not an ASCII apostrophe. Copy it verbatim from this table or from `shopify_tool/profile_manager.py:455`.

---

## File Structure

| File | Responsibility | Tasks |
|---|---|---|
| `shopify_tool/tag_manager.py` | Add `DEFAULT_TAG_CATEGORIES` constant; tighten validator | 1, 10 |
| `shopify_tool/profile_migrations.py` | Consume the constant in two places; add the relabel migration | 1, 2 |
| `shopify_tool/profile_manager.py` | Consume the constant; register the new migration | 1, 2 |
| `gui/tag_categories_dialog.py` | All nine dialog fixes | 3–9 |
| `tests/test_tag_categories_defaults.py` | **New.** Defaults constant + relabel migration tests | 1, 2 |
| `tests/test_tag_categories_dialog.py` | Existing (1 test). Gains dialog regression tests | 3–10 |

---

## Task 1: Single source of truth for the default categories

**Files:**
- Modify: `shopify_tool/tag_manager.py` (add constant near top, after imports)
- Modify: `shopify_tool/profile_migrations.py:134-187` and `:274-305`
- Modify: `shopify_tool/profile_manager.py:416-469`
- Test: `tests/test_tag_categories_defaults.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: `shopify_tool.tag_manager.DEFAULT_TAG_CATEGORIES` — a `dict` of shape `{"version": 2, "categories": {<id>: {"label": str, "color": str, "order": int, "tags": list[str], "sku_writeoff": {"enabled": bool, "mappings": dict}}}}`. Task 2 imports it.

- [ ] **Step 1: Write the failing test**

Create `tests/test_tag_categories_defaults.py`:

```python
"""Default tag categories: one source of truth, no Ukrainian localization."""

import re

from shopify_tool.profile_manager import ProfileManager
from shopify_tool.tag_manager import DEFAULT_TAG_CATEGORIES, validate_tag_categories_v2

CYRILLIC = re.compile(r"[Ѐ-ӿ]")

EXPECTED_LABELS = {
    "packaging": "Packaging",
    "priority": "Priority",
    "status": "Status",
    "order_type": "Order Type",
    "accessories": "Accessories",
    "delivery": "Delivery",
    "custom": "Other",
}


def test_default_categories_have_english_labels():
    labels = {k: v["label"] for k, v in DEFAULT_TAG_CATEGORIES["categories"].items()}
    assert labels == EXPECTED_LABELS


def test_default_categories_contain_no_cyrillic():
    assert not CYRILLIC.search(str(DEFAULT_TAG_CATEGORIES))


def test_delivery_seeds_no_tags():
    assert DEFAULT_TAG_CATEGORIES["categories"]["delivery"]["tags"] == []


def test_non_delivery_tag_lists_are_unchanged():
    cats = DEFAULT_TAG_CATEGORIES["categories"]
    assert cats["packaging"]["tags"] == ["SMALL_BAG", "LARGE_BAG", "BOX", "NO_BOX", "BOX+ANY"]
    assert cats["priority"]["tags"] == ["URGENT", "HIGH_VALUE", "DOUBLE_TRACK"]
    assert cats["status"]["tags"] == ["CHECKED", "PROBLEM", "VERIFIED"]
    assert cats["order_type"]["tags"] == ["RETAIL", "WHOLESALE", "RETURN", "EXCHANGE"]
    assert cats["accessories"]["tags"] == ["STICKER", "BUSINESS_CARD", "GIFT_BOX"]
    assert cats["custom"]["tags"] == []


def test_defaults_pass_their_own_validator():
    is_valid, errors = validate_tag_categories_v2(DEFAULT_TAG_CATEGORIES)
    assert is_valid, errors
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_tag_categories_defaults.py -v`

Expected: FAIL — `ImportError: cannot import name 'DEFAULT_TAG_CATEGORIES'`.

- [ ] **Step 3: Add the constant**

In `shopify_tool/tag_manager.py`, immediately after the imports and before `def parse_tags`:

```python
DEFAULT_TAG_CATEGORIES = {
    "version": 2,
    "categories": {
        "packaging": {
            "label": "Packaging",
            "color": "#4CAF50",
            "order": 1,
            "tags": ["SMALL_BAG", "LARGE_BAG", "BOX", "NO_BOX", "BOX+ANY"],
            "sku_writeoff": {"enabled": False, "mappings": {}},
        },
        "priority": {
            "label": "Priority",
            "color": "#FF9800",
            "order": 2,
            "tags": ["URGENT", "HIGH_VALUE", "DOUBLE_TRACK"],
            "sku_writeoff": {"enabled": False, "mappings": {}},
        },
        "status": {
            "label": "Status",
            "color": "#2196F3",
            "order": 3,
            "tags": ["CHECKED", "PROBLEM", "VERIFIED"],
            "sku_writeoff": {"enabled": False, "mappings": {}},
        },
        "order_type": {
            "label": "Order Type",
            "color": "#9C27B0",
            "order": 4,
            "tags": ["RETAIL", "WHOLESALE", "RETURN", "EXCHANGE"],
            "sku_writeoff": {"enabled": False, "mappings": {}},
        },
        "accessories": {
            "label": "Accessories",
            "color": "#E91E63",
            "order": 5,
            "tags": ["STICKER", "BUSINESS_CARD", "GIFT_BOX"],
            "sku_writeoff": {"enabled": False, "mappings": {}},
        },
        "delivery": {
            "label": "Delivery",
            "color": "#FF5722",
            "order": 6,
            "tags": [],
            "sku_writeoff": {"enabled": False, "mappings": {}},
        },
        # ponytail: 'custom' is the fallback bucket get_tag_category() returns
        # for any unrecognized tag. order 999 keeps it last; the dialog's order
        # spinbox maxes out at 999, so do not raise this value.
        "custom": {
            "label": "Other",
            "color": "#9E9E9E",
            "order": 999,
            "tags": [],
            "sku_writeoff": {"enabled": False, "mappings": {}},
        },
    },
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_tag_categories_defaults.py -v`

Expected: PASS (5 tests).

- [ ] **Step 5: Write the failing deep-copy test**

The constant is module-level and mutable. Both consumers write it into a config
dict that later gets edited and saved — handing out the shared object would let
one client's edits leak into every other client. Append to
`tests/test_tag_categories_defaults.py`:

```python
def test_migration_does_not_hand_out_the_shared_constant():
    from shopify_tool.profile_migrations import migrate_add_tag_categories

    config_a = {}
    config_b = {}
    migrate_add_tag_categories("A", config_a)
    migrate_add_tag_categories("B", config_b)

    config_a["tag_categories"]["categories"]["packaging"]["tags"].append("LEAKED")

    assert "LEAKED" not in config_b["tag_categories"]["categories"]["packaging"]["tags"]
    assert "LEAKED" not in DEFAULT_TAG_CATEGORIES["categories"]["packaging"]["tags"]
```

- [ ] **Step 6: Run it to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_tag_categories_defaults.py::test_migration_does_not_hand_out_the_shared_constant -v`

Expected: FAIL — `migrate_add_tag_categories` still builds its own Ukrainian literal, so `config_b` has `Пакетаж` and no leak, but the *label* assertions in the earlier tests will not yet reflect it. If this specific test passes for the wrong reason (both configs still get independent literals), that is fine — it must still pass after Step 7, which is the point.

- [ ] **Step 7: Replace the three hardcoded blocks**

In `shopify_tool/profile_migrations.py`, add `import copy` to the imports and
`from shopify_tool.tag_manager import DEFAULT_TAG_CATEGORIES`.

Replace the whole literal assigned in `migrate_add_tag_categories` (`:134-187`) with:

```python
    config["tag_categories"] = copy.deepcopy(DEFAULT_TAG_CATEGORIES)
```

In `migrate_tag_categories_v1_to_v2`, replace the three backfill literals
(`:274-305`) with lookups into the constant. The three `if` blocks become:

```python
    # Add new default categories if missing
    _defaults = DEFAULT_TAG_CATEGORIES["categories"]
    for category_id in ("order_type", "accessories", "delivery"):
        if category_id not in migrated_categories:
            migrated_categories[category_id] = copy.deepcopy(_defaults[category_id])
            migrated_categories[category_id]["order"] = order_counter
            order_counter += 1
            logger.info(f"Added '{category_id}' category for CLIENT_{client_id}")
```

In `shopify_tool/profile_manager.py`, add `import copy` if not already present,
add `DEFAULT_TAG_CATEGORIES` to the existing
`from shopify_tool.tag_manager import ...` line (create the import if there is
none), and replace the literal at `:416-469` with:

```python
            "tag_categories": copy.deepcopy(DEFAULT_TAG_CATEGORIES),
```

Watch for a circular import: `tag_manager` imports only `hashlib`, `json`,
`functools` and `pandas`, so importing it from `profile_manager` and
`profile_migrations` is safe. If Python reports a cycle, the cause is something
else you introduced — do not "fix" it by inlining the constant back.

- [ ] **Step 8: Add the new-profile test**

Append to `tests/test_tag_categories_defaults.py`:

```python
def test_new_client_config_has_english_labels(tmp_path):
    pm = ProfileManager(str(tmp_path))
    config = pm._default_client_config("001", "Test Client")

    labels = {k: v["label"] for k, v in config["tag_categories"]["categories"].items()}
    assert labels == EXPECTED_LABELS
    assert not CYRILLIC.search(str(config["tag_categories"]))
```

If `ProfileManager.__init__` or `_default_client_config` has a different
signature, adapt the call — read the actual definitions rather than guessing.
The assertion is what matters, not the construction boilerplate.

- [ ] **Step 9: Run the full new test file and the existing suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_tag_categories_defaults.py tests/test_profile_manager.py -v`

Expected: all PASS. If an existing `test_profile_manager.py` test asserts a
Ukrainian label, update that assertion to the English one — that is a genuine
expectation change, not a regression.

- [ ] **Step 10: Commit**

```bash
git add shopify_tool/tag_manager.py shopify_tool/profile_migrations.py shopify_tool/profile_manager.py tests/test_tag_categories_defaults.py
git commit -m "Phase 6 — Tag categories: one English default block, replacing three Ukrainian copies"
```

---

## Task 2: Relabel migration for existing client configs

**Files:**
- Modify: `shopify_tool/profile_migrations.py` (add constant + function at end)
- Modify: `shopify_tool/profile_manager.py:589` (register in the migration chain)
- Test: `tests/test_tag_categories_defaults.py` (append)

**Interfaces:**
- Consumes: `DEFAULT_TAG_CATEGORIES` from Task 1.
- Produces: `shopify_tool.profile_migrations.migrate_tag_category_labels_to_english(client_id: str, config: dict) -> bool` — mutates `config` in place, returns `True` iff at least one label changed.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_tag_categories_defaults.py`:

```python
UKRAINIAN_CONFIG = {
    "tag_categories": {
        "version": 2,
        "categories": {
            "packaging": {
                "label": "Пакетаж", "color": "#4CAF50", "order": 1,
                "tags": ["SMALL_BAG", "BOX"],
                "sku_writeoff": {"enabled": True,
                                 "mappings": {"BOX": [{"sku": "PKG-BOX", "quantity": 1.0}]}},
            },
            "delivery": {
                "label": "Кур'єр/Доставка", "color": "#FF5722", "order": 6,
                "tags": ["NOVA_POSHTA", "UKRPOSHTA"],
                "sku_writeoff": {"enabled": False, "mappings": {}},
            },
            "custom": {
                "label": "Інші", "color": "#9E9E9E", "order": 999, "tags": [],
                "sku_writeoff": {"enabled": False, "mappings": {}},
            },
        },
    }
}


def _ukrainian_config():
    import copy as _copy
    return _copy.deepcopy(UKRAINIAN_CONFIG)


def test_relabels_untouched_ukrainian_defaults():
    from shopify_tool.profile_migrations import migrate_tag_category_labels_to_english

    config = _ukrainian_config()
    assert migrate_tag_category_labels_to_english("001", config) is True

    cats = config["tag_categories"]["categories"]
    assert cats["packaging"]["label"] == "Packaging"
    assert cats["delivery"]["label"] == "Delivery"
    assert cats["custom"]["label"] == "Other"


def test_user_renamed_label_is_preserved():
    from shopify_tool.profile_migrations import migrate_tag_category_labels_to_english

    config = _ukrainian_config()
    config["tag_categories"]["categories"]["packaging"]["label"] = "Boxes & Bags"

    assert migrate_tag_category_labels_to_english("001", config) is True

    cats = config["tag_categories"]["categories"]
    assert cats["packaging"]["label"] == "Boxes & Bags"
    assert cats["delivery"]["label"] == "Delivery"


def test_migration_is_idempotent():
    from shopify_tool.profile_migrations import migrate_tag_category_labels_to_english

    config = _ukrainian_config()
    assert migrate_tag_category_labels_to_english("001", config) is True
    snapshot = str(config)
    assert migrate_tag_category_labels_to_english("001", config) is False
    assert str(config) == snapshot


def test_migration_never_touches_tags_colors_orders_or_writeoff():
    from shopify_tool.profile_migrations import migrate_tag_category_labels_to_english

    config = _ukrainian_config()
    before = {
        cid: (c["tags"], c["color"], c["order"], c["sku_writeoff"])
        for cid, c in _ukrainian_config()["tag_categories"]["categories"].items()
    }

    migrate_tag_category_labels_to_english("001", config)

    for cid, cat in config["tag_categories"]["categories"].items():
        assert (cat["tags"], cat["color"], cat["order"], cat["sku_writeoff"]) == before[cid]
    # the Ukrainian carrier tags specifically survive
    assert config["tag_categories"]["categories"]["delivery"]["tags"] == [
        "NOVA_POSHTA", "UKRPOSHTA"
    ]


def test_migration_tolerates_malformed_configs():
    from shopify_tool.profile_migrations import migrate_tag_category_labels_to_english

    for config in (
        {},
        {"tag_categories": {}},
        {"tag_categories": {"packaging": {"label": "Пакетаж"}}},  # v1 shape
        {"tag_categories": {"version": 2, "categories": "not a dict"}},
        {"tag_categories": {"version": 2, "categories": {"packaging": "not a dict"}}},
    ):
        assert migrate_tag_category_labels_to_english("001", config) is False
```

- [ ] **Step 2: Run to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_tag_categories_defaults.py -v -k migration or relabel or renamed`

Expected: FAIL — `ImportError: cannot import name 'migrate_tag_category_labels_to_english'`.

- [ ] **Step 3: Implement the migration**

Append to `shopify_tool/profile_migrations.py`:

```python
# The labels shipped as defaults before the tag-category de-localization.
# A label is rewritten only when it still matches its entry here exactly --
# anything the user renamed themselves is left alone.
_UKRAINIAN_DEFAULT_LABELS = {
    "packaging": "Пакетаж",
    "priority": "Пріоритет",
    "status": "Статус",
    "order_type": "Тип замовлення",
    "accessories": "Додатки",
    "delivery": "Кур'єр/Доставка",
    "custom": "Інші",
}


def migrate_tag_category_labels_to_english(client_id: str, config: dict) -> bool:
    """Replace untouched Ukrainian default category labels with English ones.

    Relabels only. Tags, colors, orders and sku_writeoff config are never
    touched, so tags already applied to orders keep working. A label the user
    renamed is left as-is.

    Returns:
        bool: True if at least one label was rewritten.
    """
    categories = config.get("tag_categories", {})
    if not isinstance(categories, dict):
        return False
    categories = categories.get("categories", {})
    if not isinstance(categories, dict):
        return False

    english = DEFAULT_TAG_CATEGORIES["categories"]
    changed = False

    for category_id, old_label in _UKRAINIAN_DEFAULT_LABELS.items():
        category = categories.get(category_id)
        if not isinstance(category, dict):
            continue
        if category.get("label") != old_label:
            continue
        category["label"] = english[category_id]["label"]
        changed = True

    if changed:
        logger.info(f"Relabeled tag categories to English for CLIENT_{client_id}")

    return changed
```

Note the v1-shape case in the test (`{"tag_categories": {"packaging": {...}}}`)
returns `False` because there is no `"categories"` key — that is correct. This
migration is registered *after* `migrate_tag_categories_v1_to_v2`, so a real v1
config is already v2-shaped by the time this runs.

- [ ] **Step 4: Run to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_tag_categories_defaults.py -v`

Expected: all PASS.

- [ ] **Step 5: Register the migration in the chain**

Add the import alongside the others at `:30-34`:

```python
    migrate_tag_category_labels_to_english,
```

In `load_shopify_config`, after the existing call at `:590-592`, add:

```python
            migrated_tag_labels = migrate_tag_category_labels_to_english(
                client_id, config
            )
```

and extend the `or` chain at `:596-603` so it reads:

```python
            if (
                migrated_mappings
                or migrated_delimiters
                or migrated_tag_categories
                or migrated_tag_categories_v2
                or migrated_tag_labels
                or migrated_weight
                or migrated_inv_memory
            ):
```

Note the enclosing method is `load_shopify_config`, not `load_client_config` —
check which one the test in Step 6 should call.

- [ ] **Step 6: Write the end-to-end load test**

Append to `tests/test_tag_categories_defaults.py`:

```python
def test_loading_a_ukrainian_config_relabels_it(tmp_path):
    """The migration reaches real configs through load_client_config()."""
    import json

    pm = ProfileManager(str(tmp_path))
    # Build a client config on disk with the old Ukrainian labels, then load it.
    # Adapt the path/creation calls to ProfileManager's real API.
    config = pm._default_client_config("001", "Test Client")
    config["tag_categories"] = _ukrainian_config()["tag_categories"]

    path = pm.get_client_config_path("001")
    path_obj = __import__("pathlib").Path(path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)
    path_obj.write_text(json.dumps(config), encoding="utf-8")

    loaded = pm.load_client_config("001")
    labels = {k: v["label"] for k, v in loaded["tag_categories"]["categories"].items()}
    assert labels["packaging"] == "Packaging"
    assert labels["delivery"] == "Delivery"
```

`get_client_config_path` is a guess at the accessor name — **read
`profile_manager.py` and use the real one.** If constructing a config on disk is
awkward, call `migrate_tag_category_labels_to_english` through whatever function
`load_client_config` delegates migrations to; the point of this test is that the
migration is actually wired into the load path, not that it works in isolation
(Steps 1–4 already cover that).

- [ ] **Step 7: Run the full suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest`

Expected: all PASS. A failure in an unrelated test file means you broke an
import — investigate before continuing.

- [ ] **Step 8: Commit**

```bash
git add shopify_tool/profile_migrations.py shopify_tool/profile_manager.py tests/test_tag_categories_defaults.py
git commit -m "Phase 6 — Tag categories: migrate untouched Ukrainian labels to English on load"
```

---

## Task 3: Validator rejects empty labels

Done before the dialog fixes because Task 4's tests are clearer when the
validator can express "this label is broken".

**Files:**
- Modify: `shopify_tool/tag_manager.py` (inside `validate_tag_categories_v2`)
- Test: `tests/test_tag_manager.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `validate_tag_categories_v2` now returns an error string containing `"empty label"` for a blank/whitespace-only label. Signature unchanged: `(config: dict) -> tuple[bool, list[str]]`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tag_manager.py`:

```python
def test_validator_rejects_empty_category_label():
    from shopify_tool.tag_manager import validate_tag_categories_v2

    config = {
        "version": 2,
        "categories": {
            "packaging": {
                "label": "", "color": "#4CAF50", "order": 1, "tags": [],
                "sku_writeoff": {"enabled": False, "mappings": {}},
            }
        },
    }
    is_valid, errors = validate_tag_categories_v2(config)
    assert is_valid is False
    assert any("empty label" in e for e in errors)


def test_validator_rejects_whitespace_only_label():
    from shopify_tool.tag_manager import validate_tag_categories_v2

    config = {
        "version": 2,
        "categories": {
            "packaging": {
                "label": "   ", "color": "#4CAF50", "order": 1, "tags": [],
                "sku_writeoff": {"enabled": False, "mappings": {}},
            }
        },
    }
    is_valid, errors = validate_tag_categories_v2(config)
    assert is_valid is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_tag_manager.py -v -k label`

Expected: FAIL — `assert True is False`, because a present-but-empty `label` passes the current `field not in category_config` check.

- [ ] **Step 3: Implement**

In `validate_tag_categories_v2`, directly after the existing required-fields
loop (the `for field in required_fields:` block), add:

```python
        label = category_config.get("label")
        if isinstance(label, str) and not label.strip():
            errors.append(f"Category '{category_id}' has an empty label")
```

- [ ] **Step 4: Run to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_tag_manager.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add shopify_tool/tag_manager.py tests/test_tag_manager.py
git commit -m "Phase 6 — Tag categories: validator rejects empty category labels"
```

---

## Task 4: Fix the label-wiping list rebuild (the data-loss bug)

**Files:**
- Modify: `gui/tag_categories_dialog.py` — `_load_categories` (`:270-294`)
- Test: `tests/test_tag_categories_dialog.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `_load_categories()` no longer emits `currentItemChanged` during the rebuild. Task 5 depends on this.

**Background (read before implementing):** `_load_categories()` begins with
`self.categories_list.clear()`. Qt drains the list one row at a time, emitting
`currentItemChanged` repeatedly as the current item walks down; each non-None
emission reaches `_on_category_selected` and **reassigns
`self.current_category_id`**. The final emission has `current is None`, which
calls `_set_editor_enabled(False)` *before* `current_category_id` is cleared, and
that method calls `label_input.clear()` with signals live → `textChanged` →
`_on_editor_changed` → `_save_editor_to_working_copy()` writes `label = ""`.

The category that gets blanked is the **penultimate** one in sorted order, not
the selected one, and this fires on both the `+ New` and `Delete` paths. Do not
write a test that names a specific victim — assert that *all* labels are
unchanged.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_tag_categories_dialog.py`. Match the existing file's
fixture/imports style — read it first.

```python
def _sample_categories():
    return {
        "version": 2,
        "categories": {
            "packaging": {
                "label": "Packaging", "color": "#4CAF50", "order": 1,
                "tags": ["BOX"],
                "sku_writeoff": {"enabled": False, "mappings": {}},
            },
            "priority": {
                "label": "Priority", "color": "#FF9800", "order": 2,
                "tags": ["URGENT"],
                "sku_writeoff": {"enabled": True,
                                 "mappings": {"URGENT": [{"sku": "S1", "quantity": 2.0}]}},
            },
            "status": {
                "label": "Status", "color": "#2196F3", "order": 3,
                "tags": ["CHECKED"],
                "sku_writeoff": {"enabled": False, "mappings": {}},
            },
        },
    }


def _labels(panel):
    return {k: v["label"] for k, v in panel.working_categories["categories"].items()}


def test_rebuilding_the_list_preserves_every_label(qtbot):
    from gui.tag_categories_dialog import TagCategoriesPanel

    panel = TagCategoriesPanel(_sample_categories())
    qtbot.addWidget(panel)
    panel.categories_list.setCurrentRow(0)

    panel._load_categories()

    assert _labels(panel) == {
        "packaging": "Packaging", "priority": "Priority", "status": "Status"
    }


def test_adding_a_category_preserves_every_existing_label(qtbot):
    from gui.tag_categories_dialog import TagCategoriesPanel

    panel = TagCategoriesPanel(_sample_categories())
    qtbot.addWidget(panel)
    panel.categories_list.setCurrentRow(0)

    cats = panel.working_categories["categories"]
    cats["extra"] = {
        "label": "Extra", "color": "#9E9E9E", "order": 4, "tags": [],
        "sku_writeoff": {"enabled": False, "mappings": {}},
    }
    panel._load_categories()

    assert _labels(panel)["packaging"] == "Packaging"
    assert _labels(panel)["priority"] == "Priority"
    assert _labels(panel)["status"] == "Status"


def test_deleting_a_category_preserves_the_survivors_labels(qtbot):
    from gui.tag_categories_dialog import TagCategoriesPanel

    panel = TagCategoriesPanel(_sample_categories())
    qtbot.addWidget(panel)
    panel.categories_list.setCurrentRow(0)

    del panel.working_categories["categories"]["packaging"]
    panel.current_category_id = None
    panel._load_categories()

    assert _labels(panel) == {"priority": "Priority", "status": "Status"}


def test_rebuild_preserves_tags_colors_orders_and_writeoff(qtbot):
    from gui.tag_categories_dialog import TagCategoriesPanel

    expected = _sample_categories()["categories"]
    panel = TagCategoriesPanel(_sample_categories())
    qtbot.addWidget(panel)
    panel.categories_list.setCurrentRow(0)

    panel._load_categories()

    for cid, cat in panel.working_categories["categories"].items():
        assert cat["tags"] == expected[cid]["tags"]
        assert cat["color"] == expected[cid]["color"]
        assert cat["order"] == expected[cid]["order"]
        assert cat["sku_writeoff"] == expected[cid]["sku_writeoff"]
```

`pytest-qt` is available (`requirements-dev.txt`, and `tests/test_rule_test_dialog.py`
already uses `qtbot`), so the `qtbot` fixture works as written. Leave the
existing module-scoped autouse `qapp` fixture at the top of
`tests/test_tag_categories_dialog.py` in place — it does not conflict.

- [ ] **Step 2: Run to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_tag_categories_dialog.py -v`

Expected: the first three FAIL with a label equal to `''`. The fourth should
already PASS — it pins the corruption scope so a future "fix" cannot widen it.

- [ ] **Step 3: Implement the guard**

Add `QSignalBlocker` to the `PySide6.QtCore` import line in
`gui/tag_categories_dialog.py`.

Then wrap the body of `_load_categories`:

```python
    def _load_categories(self):
        """Load categories into the list widget.

        The whole rebuild runs with the list's signals blocked. Qt drains
        currentItemChanged repeatedly during clear(), and those emissions reach
        _on_category_selected, which reassigns current_category_id and then
        clears the editor fields -- whose textChanged handlers write the now-empty
        editor back over a real category's label. Blocking here is the single
        place that closes every variant of that path.
        """
        blocker = QSignalBlocker(self.categories_list)  # noqa: F841

        self.categories_list.clear()
        ...  # rest of the existing body unchanged
```

`QSignalBlocker` unblocks when it is garbage-collected at function exit. If you
prefer an explicit form, use `self.categories_list.blockSignals(True)` /
`blockSignals(False)` in a `try/finally` — either is fine, but the `try/finally`
is required if you take that route, so an exception mid-rebuild cannot leave the
widget permanently silent.

- [ ] **Step 4: Run to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_tag_categories_dialog.py -v`

Expected: all PASS, including the pre-existing
`test_deleting_a_category_does_not_mutate_the_caller_s_dict`.

- [ ] **Step 5: Check the selection side effects**

Blocking `currentItemChanged` means `_on_category_selected` no longer runs during
a rebuild — so after `_load_categories()`, `current_category_id` keeps its
pre-rebuild value and the editor keeps showing the old category. Verify the two
callers still behave:

- `_on_new_category` explicitly calls `setCurrentItem` on the new category after
  the rebuild (`:685-689`), which fires the signal normally (the blocker is gone
  by then) and loads it into the editor. Correct.
- `_on_delete_category` sets `current_category_id = None` then calls
  `_set_editor_enabled(False)` after the rebuild (`:712-715`). Correct.

Add a test pinning the first:

```python
def test_new_category_becomes_the_selected_one(qtbot):
    from gui.tag_categories_dialog import TagCategoriesPanel

    panel = TagCategoriesPanel(_sample_categories())
    qtbot.addWidget(panel)
    panel.categories_list.setCurrentRow(0)

    cats = panel.working_categories["categories"]
    cats["extra"] = {
        "label": "Extra", "color": "#9E9E9E", "order": 4, "tags": [],
        "sku_writeoff": {"enabled": False, "mappings": {}},
    }
    panel._load_categories()
    for i in range(panel.categories_list.count()):
        item = panel.categories_list.item(i)
        if item.data(Qt.UserRole) == "extra":
            panel.categories_list.setCurrentItem(item)
            break

    assert panel.current_category_id == "extra"
    assert panel.label_input.text() == "Extra"
```

Import `Qt` from `PySide6.QtCore` in the test file if it is not already there.

- [ ] **Step 6: Run the full suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest`

Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add gui/tag_categories_dialog.py tests/test_tag_categories_dialog.py
git commit -m "Phase 6 — Tag categories dialog: rebuilding the list no longer blanks a category's label"
```

---

## Task 5: Re-blend list row colors on theme change

**Files:**
- Modify: `gui/tag_categories_dialog.py` — `_on_theme_changed` (`:370-376`)
- Test: `tests/test_tag_categories_dialog.py`

**Interfaces:**
- Consumes: Task 4's signal-blocked `_load_categories`. **Do not attempt this before Task 4** — calling `_load_categories()` from a theme handler on unfixed code triggers the label wipe.

- [ ] **Step 1: Write the failing test**

`_load_categories` blends each category color 45/55 against
`theme.background`. After a theme switch the rows keep the old blend.

```python
def test_theme_change_reblends_row_backgrounds(qtbot):
    from gui.tag_categories_dialog import TagCategoriesPanel
    from gui.theme_manager import get_theme_manager

    panel = TagCategoriesPanel(_sample_categories())
    qtbot.addWidget(panel)
    before = panel.categories_list.item(0).background().color().name()

    tm = get_theme_manager()
    current = tm.get_current_theme()
    tm.set_theme("dark" if getattr(current, "name", "") != "dark" else "light")

    after = panel.categories_list.item(0).background().color().name()
    assert after != before
    assert _labels(panel)["priority"] == "Priority"
```

Read `gui/theme_manager.py` for the real theme-switching API and theme names —
`set_theme("dark")` is a guess. If switching themes in a test is impractical,
call `panel._on_theme_changed()` directly after monkeypatching the theme, and
assert the row background matches a freshly computed blend.

- [ ] **Step 2: Run to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_tag_categories_dialog.py -v -k theme`

Expected: FAIL — `assert after != before`, both identical.

- [ ] **Step 3: Implement**

```python
    def _on_theme_changed(self):
        """Handle theme changes."""
        self.theme = get_theme_manager().get_current_theme()
        if self.current_category_id:
            self.color_display.setStyleSheet(
                f"border: 1px solid {self.theme.border}; background-color: {self.current_color};"
            )
        # Row backgrounds are blended against theme.background, so they are
        # stale until the list is rebuilt. Safe because _load_categories blocks
        # the list's signals (see Task 4).
        self._load_categories()
```

Note `_load_categories` clears the list, so the visual selection is lost on a
theme switch while `current_category_id` is retained. If that is jarring,
reselect the current category after the rebuild — but only if a test shows it
matters; do not add the code speculatively.

- [ ] **Step 4: Run to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_tag_categories_dialog.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gui/tag_categories_dialog.py tests/test_tag_categories_dialog.py
git commit -m "Phase 6 — Tag categories dialog: re-blend category row colors on theme change"
```

---

## Task 6: Removing a tag drops its writeoff mappings

**Files:**
- Modify: `gui/tag_categories_dialog.py` — `_on_remove_tag` (`:522-531`)
- Test: `tests/test_tag_categories_dialog.py`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing new; behavior change only.

**Background:** `_on_remove_tag` removes the item from `tags_list`, but
`_save_editor_to_working_copy` rebuilds `mappings` from
`writeoff_mappings_table`, whose rows for the removed tag are still present. The
saved config keeps a mapping keyed by a tag the category no longer has. It can
never fire, and nothing reports it.

- [ ] **Step 1: Write the failing test**

```python
def test_removing_a_tag_drops_its_writeoff_mappings(qtbot):
    from gui.tag_categories_dialog import TagCategoriesPanel

    panel = TagCategoriesPanel(_sample_categories())
    qtbot.addWidget(panel)

    # select 'priority', which has tag URGENT with a writeoff mapping
    for i in range(panel.categories_list.count()):
        item = panel.categories_list.item(i)
        if item.data(Qt.UserRole) == "priority":
            panel.categories_list.setCurrentItem(item)
            break
    assert panel.current_category_id == "priority"
    assert panel.writeoff_mappings_table.rowCount() == 1

    panel.tags_list.setCurrentRow(0)  # URGENT
    panel._on_remove_tag()

    saved = panel.get_categories()["categories"]["priority"]
    assert saved["tags"] == []
    assert saved["sku_writeoff"]["mappings"] == {}
```

- [ ] **Step 2: Run to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_tag_categories_dialog.py -v -k writeoff_mappings`

Expected: FAIL — `mappings` still contains `{"URGENT": [...]}`.

- [ ] **Step 3: Implement**

Replace `_on_remove_tag` with:

```python
    def _on_remove_tag(self):
        """Handle remove tag button click.

        Also drops any writeoff mapping rows keyed by the removed tags --
        _save_editor_to_working_copy rebuilds mappings from the table, so rows
        left behind here would persist as mappings for a tag the category no
        longer has.
        """
        selected_items = self.tags_list.selectedItems()
        if not selected_items:
            return

        removed = {item.text() for item in selected_items}

        for item in selected_items:
            self.tags_list.takeItem(self.tags_list.row(item))

        for row in reversed(range(self.writeoff_mappings_table.rowCount())):
            tag_item = self.writeoff_mappings_table.item(row, 0)
            if tag_item is not None and tag_item.text() in removed:
                self.writeoff_mappings_table.removeRow(row)

        self._on_editor_changed()
```

- [ ] **Step 4: Run to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_tag_categories_dialog.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gui/tag_categories_dialog.py tests/test_tag_categories_dialog.py
git commit -m "Phase 6 — Tag categories dialog: removing a tag also removes its writeoff mappings"
```

---

## Task 7: Category ID validation rejects non-ASCII

**Files:**
- Modify: `gui/tag_categories_dialog.py` — `_on_new_category` (`:651-657`)
- Test: `tests/test_tag_categories_dialog.py`

**Background:** `category_id.replace("_", "").isalnum()` is `True` for any Unicode
letter, so `категорія` and `café` pass a check whose message promises "lowercase
letters, numbers, and underscores".

The ID is entered through `QInputDialog.getText`, so the test must drive the
validation logic rather than the modal. Extract the check into a small helper and
test that directly — do not try to script a modal dialog.

- [ ] **Step 1: Write the failing test**

```python
def test_category_id_validation_rejects_non_ascii():
    from gui.tag_categories_dialog import is_valid_category_id

    assert is_valid_category_id("my_category") is True
    assert is_valid_category_id("cat2") is True
    assert is_valid_category_id("категорія") is False
    assert is_valid_category_id("café") is False
    assert is_valid_category_id("") is False
    assert is_valid_category_id("___") is False
    assert is_valid_category_id("has space") is False
    assert is_valid_category_id("UPPER") is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_tag_categories_dialog.py -v -k category_id`

Expected: FAIL — `ImportError: cannot import name 'is_valid_category_id'`.

- [ ] **Step 3: Implement**

Add at module level in `gui/tag_categories_dialog.py`, after `logger = ...`:

```python
_VALID_CATEGORY_ID = re.compile(r"^[a-z0-9][a-z0-9_]*$")


def is_valid_category_id(category_id: str) -> bool:
    """Category IDs are ASCII lowercase, digits and underscores, not all-underscore.

    str.isalnum() -- which this used to rely on -- is True for any Unicode
    letter, so it accepted 'категорія' under a message promising ASCII.
    """
    if not _VALID_CATEGORY_ID.match(category_id):
        return False
    return bool(category_id.replace("_", ""))
```

Add `import re` to the imports.

Then in `_on_new_category`, replace:

```python
        if not category_id.replace("_", "").isalnum():
```

with:

```python
        if not is_valid_category_id(category_id):
```

Leave the surrounding empty-check and the warning message as they are — the
message already describes exactly what the new check enforces.

- [ ] **Step 4: Run to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_tag_categories_dialog.py -v`

Expected: PASS. Note `UPPER` returns False, and `_on_new_category` lowercases
before validating, so a user typing `UPPER` still gets `upper` — the test asserts
the helper's contract, not the dialog's.

- [ ] **Step 5: Commit**

```bash
git add gui/tag_categories_dialog.py tests/test_tag_categories_dialog.py
git commit -m "Phase 6 — Tag categories dialog: category IDs must be ASCII, as the message already claimed"
```

---

## Task 8: New categories get an unused display order

**Files:**
- Modify: `gui/tag_categories_dialog.py` — `_on_new_category` (`:672`)
- Test: `tests/test_tag_categories_dialog.py`

**Background:** `"order": len(categories) + 1` collides after any deletion. With
the seven defaults, delete two and the next new category gets an order already in
use; the sort between them then falls back to dict insertion order.

Constraint: `custom` carries the sentinel `order: 999` and the editor's spinbox
maximum is also `999`, so a naive `max(orders) + 1` produces `1000`, which the
spinbox cannot represent. Pick the lowest unused order at or above 1, ignoring
the 999 sentinel.

- [ ] **Step 1: Write the failing test**

```python
def test_new_category_order_is_unused_after_deletions():
    from gui.tag_categories_dialog import next_available_order

    assert next_available_order([1, 2, 3, 999]) == 4
    assert next_available_order([1, 3, 999]) == 2      # fills the gap
    assert next_available_order([999]) == 1
    assert next_available_order([]) == 1
    assert next_available_order([1, 2, 3, 4, 5, 6, 999]) == 7


def test_new_category_order_never_exceeds_the_spinbox_maximum():
    from gui.tag_categories_dialog import next_available_order

    assert next_available_order(list(range(1, 999))) <= 999
```

- [ ] **Step 2: Run to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_tag_categories_dialog.py -v -k order`

Expected: FAIL — `ImportError: cannot import name 'next_available_order'`.

- [ ] **Step 3: Implement**

Add at module level, next to `is_valid_category_id`:

```python
# The editor's order spinbox maxes out at this value, and 'custom' uses it as a
# keep-me-last sentinel.
_MAX_CATEGORY_ORDER = 999


def next_available_order(existing_orders) -> int:
    """Lowest unused display order in [1, 999].

    Not len(categories) + 1 -- that collides with a live order as soon as any
    category has been deleted, and the resulting sort falls back to dict order.
    """
    taken = {o for o in existing_orders if isinstance(o, int)}
    for candidate in range(1, _MAX_CATEGORY_ORDER + 1):
        if candidate not in taken:
            return candidate
    return _MAX_CATEGORY_ORDER
```

In `_on_new_category`, replace `"order": len(categories) + 1,` with:

```python
            "order": next_available_order(
                c.get("order") for c in categories.values() if isinstance(c, dict)
            ),
```

- [ ] **Step 4: Run to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_tag_categories_dialog.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gui/tag_categories_dialog.py tests/test_tag_categories_dialog.py
git commit -m "Phase 6 — Tag categories dialog: new categories get an unused display order"
```

---

## Task 9: Writeoff quantity cells are read-only; duplicate mappings rejected; swatch resets

Three small independent fixes, batched because each is a few lines and none
warrants its own review gate.

**Files:**
- Modify: `gui/tag_categories_dialog.py` — `_load_category_into_editor` (`:362-364`), `_on_add_mapping` (`:602-618`), `_set_editor_enabled` (`:396-402`)
- Test: `tests/test_tag_categories_dialog.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_writeoff_quantity_cells_are_not_editable(qtbot):
    from PySide6.QtCore import Qt as _Qt
    from gui.tag_categories_dialog import TagCategoriesPanel

    panel = TagCategoriesPanel(_sample_categories())
    qtbot.addWidget(panel)
    for i in range(panel.categories_list.count()):
        item = panel.categories_list.item(i)
        if item.data(_Qt.UserRole) == "priority":
            panel.categories_list.setCurrentItem(item)
            break

    for col in range(3):
        cell = panel.writeoff_mappings_table.item(0, col)
        assert not (cell.flags() & _Qt.ItemIsEditable)


def test_duplicate_tag_and_sku_mapping_is_rejected(qtbot):
    from gui.tag_categories_dialog import mapping_row_exists

    rows = [("URGENT", "S1"), ("URGENT", "S2")]
    assert mapping_row_exists(rows, "URGENT", "S1") is True
    assert mapping_row_exists(rows, "URGENT", "S3") is False
    assert mapping_row_exists(rows, "OTHER", "S1") is False


def test_deselecting_resets_the_color_swatch(qtbot):
    from gui.tag_categories_dialog import TagCategoriesPanel

    panel = TagCategoriesPanel(_sample_categories())
    qtbot.addWidget(panel)
    panel.categories_list.setCurrentRow(0)
    assert panel.current_color == "#4CAF50"

    panel._set_editor_enabled(False)

    assert panel.current_color == "#9E9E9E"
```

- [ ] **Step 2: Run to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_tag_categories_dialog.py -v -k "quantity_cells or duplicate_tag or color_swatch"`

Expected: all three FAIL.

- [ ] **Step 3: Make quantity cells read-only**

The table is only ever populated through the Add Mapping dialog, which uses a
`QDoubleSpinBox` — so the free-text path exists only by accident, and its
`float()` failure is swallowed with a silent `1.0` fallback in
`_save_editor_to_working_copy`. Making the cells non-editable makes that
fallback unreachable rather than silent.

There are two row-insertion sites: `_load_category_into_editor` (`:362-364`) and
`_on_add_mapping` (`:614-616`). Add a helper next to the other module-level
functions:

```python
def _read_only_item(text: str) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
    return item
```

and use it at both sites in place of the bare `QTableWidgetItem(...)` calls, e.g.:

```python
                self.writeoff_mappings_table.setItem(row_position, 0, _read_only_item(tag))
                self.writeoff_mappings_table.setItem(row_position, 1, _read_only_item(item["sku"]))
                self.writeoff_mappings_table.setItem(
                    row_position, 2, _read_only_item(f"{item['quantity']:.2f}")
                )
```

Leave the `try/except ValueError` fallback in `_save_editor_to_working_copy` in
place as a belt-and-braces guard for configs edited outside the app.

- [ ] **Step 4: Reject duplicate (tag, SKU) mapping rows**

Add at module level:

```python
def mapping_row_exists(rows, tag: str, sku: str) -> bool:
    """True if this exact tag+SKU pair is already mapped.

    Several different SKUs per tag is the intended feature; the same SKU twice
    just doubles the deduction.
    """
    return (tag, sku) in {(t, s) for t, s in rows}
```

In `_on_add_mapping`, after the `if not sku:` guard and before inserting the row:

```python
            existing = [
                (
                    self.writeoff_mappings_table.item(r, 0).text(),
                    self.writeoff_mappings_table.item(r, 1).text(),
                )
                for r in range(self.writeoff_mappings_table.rowCount())
                if self.writeoff_mappings_table.item(r, 0)
                and self.writeoff_mappings_table.item(r, 1)
            ]
            if mapping_row_exists(existing, tag, sku):
                QMessageBox.warning(
                    self,
                    "Duplicate Mapping",
                    f"'{sku}' is already mapped to tag '{tag}'.",
                )
                return
```

- [ ] **Step 5: Reset the swatch on deselect**

In `_set_editor_enabled`, inside the existing `if not enabled:` block, after
`self.label_input.clear()`:

```python
            # ponytail: same literal neutral swatch fill as the editor default —
            # see _create_category_editor_panel for why no theme token fits.
            self.current_color = "#9E9E9E"
            self.color_display.setStyleSheet(
                f"border: 1px solid {self.theme.border}; background-color: {self.current_color};"
            )
```

- [ ] **Step 6: Run to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_tag_categories_dialog.py -v`

Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add gui/tag_categories_dialog.py tests/test_tag_categories_dialog.py
git commit -m "Phase 6 — Tag categories dialog: read-only quantity cells, no duplicate mappings, swatch resets"
```

---

## Task 10: Pin the writeoff-checkbox signal behavior, then run the gate

**Files:**
- Test: `tests/test_tag_categories_dialog.py`

**Background:** `_on_writeoff_enabled_changed` compares an `int` state against
`Qt.Checked`. This works under PySide6's IntEnum semantics, and `stateChanged` is
deprecated in Qt6 in favour of `checkStateChanged`. The spec's decision is to pin
the current behavior with a test rather than rewrite a working signal — so a
future PySide6 upgrade that changes the semantics fails loudly here instead of
silently disabling the writeoff table.

- [ ] **Step 1: Write the test**

```python
def test_writeoff_checkbox_toggles_the_mappings_table(qtbot):
    from PySide6.QtCore import Qt as _Qt
    from gui.tag_categories_dialog import TagCategoriesPanel

    panel = TagCategoriesPanel(_sample_categories())
    qtbot.addWidget(panel)
    for i in range(panel.categories_list.count()):
        item = panel.categories_list.item(i)
        if item.data(_Qt.UserRole) == "packaging":
            panel.categories_list.setCurrentItem(item)
            break

    assert panel.writeoff_enabled_checkbox.isChecked() is False
    assert panel.writeoff_mappings_table.isEnabled() is False

    panel.writeoff_enabled_checkbox.setChecked(True)
    assert panel.writeoff_mappings_table.isEnabled() is True
    assert panel.add_mapping_btn.isEnabled() is True

    panel.writeoff_enabled_checkbox.setChecked(False)
    assert panel.writeoff_mappings_table.isEnabled() is False
```

- [ ] **Step 2: Run it**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_tag_categories_dialog.py -v -k writeoff_checkbox`

Expected: PASS immediately. This one is a characterization test, not a
regression test — it is not supposed to fail first. **If it fails**, the
`int`/`Qt.Checked` comparison is genuinely broken on this PySide6 version and
becomes a real bug to fix: change the handler to
`enabled = self.writeoff_enabled_checkbox.isChecked()` and ignore the `state`
argument.

- [ ] **Step 3: Run the repo gate**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
.venv/bin/ruff check . --exclude shared
```

Expected: all tests pass, ruff clean. Fix anything ruff flags in files this plan
touched. Do not "fix" pre-existing warnings in unrelated files.

- [ ] **Step 4: Verify no Cyrillic is left in the tag-category paths**

```bash
grep -nP '[\x{0400}-\x{04FF}]' shopify_tool/tag_manager.py gui/tag_categories_dialog.py
grep -nP '[\x{0400}-\x{04FF}]' shopify_tool/profile_manager.py
```

Expected: nothing from the first command. The second still shows the Bulgarian
stock-export column names in `column_mappings` (`Артикул`, `Име`, `Наличност`,
`Годност`, `Партида`) — **that is correct and must stay.** The only Cyrillic
left in `profile_migrations.py` should be `_UKRAINIAN_DEFAULT_LABELS` and the
stock `column_mappings` default, both intentional.

- [ ] **Step 5: Update the knowledge graph**

```bash
graphify update .
```

- [ ] **Step 6: Commit**

```bash
git add tests/test_tag_categories_dialog.py
git commit -m "Phase 6 — Tag categories dialog: pin writeoff checkbox toggle behavior"
```

---

## Self-Review Notes

**Spec coverage:**

| Spec section | Task |
|---|---|
| Part 1 — one source of truth | 1 |
| Part 1 — deep-copy requirement | 1 (Steps 5–7) |
| Part 2 — relabel migration | 2 |
| Part 2 — registered in the chain | 2 (Steps 5–6) |
| Part 3.A — label wipe | 4 |
| Part 3.B — theme re-blend | 5 |
| Part 3.C — orphaned mappings | 6 |
| Part 3.D — non-ASCII IDs | 7 |
| Part 3.E — order collision | 8 |
| Part 3.F — stale swatch | 9 |
| Part 3.G — quantity free text | 9 |
| Part 3.H — duplicate mappings | 9 |
| Part 3.I — empty-label validation | 3 |
| Considered-and-not-changed: `__getattr__`, apply/save asymmetry | no task, by design |
| Considered-and-not-changed: `Qt.Checked` comparison | 10 (characterization test) |

**Ordering constraints:** Task 5 requires Task 4. Task 2 requires Task 1. Task 3
before Task 4 (clearer failures). Tasks 6–9 are independent of each other.

**Names introduced, used consistently throughout:**
`DEFAULT_TAG_CATEGORIES`, `migrate_tag_category_labels_to_english`,
`_UKRAINIAN_DEFAULT_LABELS`, `is_valid_category_id`, `next_available_order`,
`mapping_row_exists`, `_read_only_item`, `_MAX_CATEGORY_ORDER`,
`_VALID_CATEGORY_ID`.

**Resolved during planning** (no longer guesses): `pytest-qt` is in
`requirements-dev.txt` and `qtbot` is already used in
`tests/test_rule_test_dialog.py`; the migration chain lives in
`load_shopify_config` at `profile_manager.py:587-603` and its save decision is an
explicit `or` chain, quoted verbatim in Task 2 Step 5.

**Known guesses the implementer must still verify against real code** (each is
flagged inline at its step): `ProfileManager.__init__` /
`_default_client_config` / `get_client_config_path` signatures (Tasks 1, 2), and
the theme-switching API in `gui/theme_manager.py` (Task 5). Read the real code;
do not implement against the guess.
