import pytest
from PySide6.QtWidgets import QApplication, QFileDialog

from gui.settings.sets import SetEditorDialog, SetsPage


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_sets_page_collects_the_live_dict(qapp):
    decoders = {"SET-A": [{"sku": "X", "quantity": 2}]}
    page = SetsPage(decoders)
    assert page.collect() == {"set_decoders": decoders}
    assert page.collect()["set_decoders"] is decoders
    assert page.validate() == (True, [])


def test_sets_page_populates_table_from_existing_decoders(qapp):
    set_decoders = {
        "SET-A": [{"sku": "X", "quantity": 2}],
        "SET-B": [],
    }
    page = SetsPage(set_decoders)
    assert page.sets_table.rowCount() == 2


def _patch_open(monkeypatch, tmp_path, imported):
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        staticmethod(lambda *a, **k: (str(tmp_path / "sets.csv"), "")),
    )
    monkeypatch.setattr("gui.settings.sets.import_sets_from_csv", lambda path: imported)


def test_delete_is_immediate_and_lands_on_the_live_dict(qapp):
    """No confirm: the window's Cancel undoes it."""
    set_decoders = {"SET-A": [{"sku": "X", "quantity": 2}]}
    page = SetsPage(set_decoders)
    page._delete_set("SET-A")
    assert set_decoders == {}


def test_the_import_menu_offers_merge_and_replace(qapp):
    page = SetsPage({})
    assert [a.text() for a in page.import_button.menu().actions()] == [
        "Add and update sets…",
        "Replace all sets…",
    ]


def test_merge_import_keeps_existing_sets_and_toasts(qapp, monkeypatch, tmp_path):
    toasts = []
    monkeypatch.setattr(
        "gui.settings.sets.toast", lambda source, text, **k: toasts.append(text)
    )
    _patch_open(monkeypatch, tmp_path, {"SET-B": [{"sku": "Y", "quantity": 1}]})
    decoders = {"SET-A": [{"sku": "X", "quantity": 2}]}
    page = SetsPage(decoders)

    page._import_sets_from_csv(replace=False)

    assert sorted(decoders) == ["SET-A", "SET-B"]
    assert toasts == ["Imported 1 sets from sets.csv"]


def test_replace_import_drops_existing_sets(qapp, monkeypatch, tmp_path):
    toasts = []
    monkeypatch.setattr(
        "gui.settings.sets.toast", lambda source, text, **k: toasts.append(text)
    )
    _patch_open(monkeypatch, tmp_path, {"SET-B": [{"sku": "Y", "quantity": 1}]})
    decoders = {"SET-A": [{"sku": "X", "quantity": 2}]}
    page = SetsPage(decoders)

    page._import_sets_from_csv(replace=True)

    assert sorted(decoders) == ["SET-B"]
    assert toasts == ["Replaced all sets with 1 from sets.csv"]


def test_an_empty_csv_shows_a_banner(qapp, monkeypatch, tmp_path):
    errors = []
    monkeypatch.setattr(
        "gui.settings.sets.show_error",
        lambda source, headline, what: errors.append((headline, what)),
    )
    _patch_open(monkeypatch, tmp_path, {})
    page = SetsPage({})

    page._import_sets_from_csv(replace=False)

    assert errors == [
        (
            "No sets found in sets.csv",
            "Each row needs Set_SKU, Component_SKU and Component_Quantity.",
        )
    ]


def _raise(*_args):
    raise OSError("unreadable")


def test_a_failed_import_shows_a_banner(qapp, monkeypatch, tmp_path):
    errors = []
    monkeypatch.setattr(
        "gui.settings.sets.show_error",
        lambda source, headline, what: errors.append((headline, what)),
    )
    _patch_open(monkeypatch, tmp_path, {})
    monkeypatch.setattr("gui.settings.sets.import_sets_from_csv", _raise)
    decoders = {"SET-A": [{"sku": "X", "quantity": 2}]}
    page = SetsPage(decoders)

    page._import_sets_from_csv(replace=True)

    assert errors == [("The sets weren't imported", "Details are in Logs.")]
    assert list(decoders) == ["SET-A"]


def test_a_failed_export_shows_a_banner(qapp, monkeypatch, tmp_path):
    errors = []
    monkeypatch.setattr(
        "gui.settings.sets.show_error",
        lambda source, headline, what: errors.append((headline, what)),
    )
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        staticmethod(lambda *a, **k: (str(tmp_path / "out.csv"), "")),
    )
    monkeypatch.setattr("gui.settings.sets.export_sets_to_csv", _raise)
    page = SetsPage({"SET-A": [{"sku": "X", "quantity": 1}]})

    page._export_sets_to_csv()

    assert errors == [("The sets weren't exported", "Details are in Logs.")]


def test_export_is_disabled_until_there_is_a_set(qapp):
    page = SetsPage({})
    assert not page.export_button.isEnabled()
    page.set_decoders["SET-A"] = [{"sku": "X", "quantity": 1}]
    page._populate_sets_table()
    assert page.export_button.isEnabled()


def test_export_toasts(qapp, monkeypatch, tmp_path):
    toasts = []
    monkeypatch.setattr(
        "gui.settings.sets.toast", lambda source, text, **k: toasts.append(text)
    )
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        staticmethod(lambda *a, **k: (str(tmp_path / "out.csv"), "")),
    )
    monkeypatch.setattr(
        "gui.settings.sets.export_sets_to_csv", lambda decoders, path: None
    )
    page = SetsPage({"SET-A": [{"sku": "X", "quantity": 1}]})

    page._export_sets_to_csv()

    assert toasts == ["Exported 1 sets to out.csv"]


def test_the_set_editor_explains_problems_inline(qapp):
    dialog = SetEditorDialog()
    dialog._validate_and_save()
    assert dialog.sku_message.text() == "Enter the set's SKU."
    assert not dialog.sku_message.isHidden()

    dialog.set_sku_edit.setText("SET-A")
    assert dialog.sku_message.isHidden()

    dialog._validate_and_save()  # one empty component row
    assert dialog.components_message.text() == "Add at least one component with a SKU."
