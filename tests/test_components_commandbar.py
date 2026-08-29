from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton

from gui.components.commandbar import ROW_ACTION, ROW_CLIENT, ROW_SECTION, CommandBar


def _rows(bar):
    """(kind, payload, text) per row, in display order."""
    model = bar.client_selector.model()
    out = []
    for i in range(model.rowCount()):
        item = model.item(i)
        out.append((item.data(Qt.UserRole), item.data(Qt.UserRole + 1), item.text()))
    return out


def _client_rows(bar):
    return [t for k, _p, t in _rows(bar) if k == ROW_CLIENT]


def test_clients_populate_the_selector(qapp):
    bar = CommandBar()
    bar.set_clients(["Acme", "Globex"])
    assert _client_rows(bar) == ["Acme", "Globex"]


def test_set_clients_does_not_emit_while_repopulating(qapp):
    bar = CommandBar()
    seen = []
    bar.clientChanged.connect(seen.append)
    bar.set_clients(["Acme", "Globex"])
    assert seen == []


def test_choosing_a_client_emits_its_name(qapp):
    bar = CommandBar()
    bar.set_clients(["Acme", "Globex"])
    seen = []
    bar.clientChanged.connect(seen.append)
    bar.set_current_client("Globex")
    assert seen == ["Globex"]


def test_session_id_is_shown_verbatim(qapp):
    bar = CommandBar()
    bar.set_session("PL-2026-08-27-004")
    assert bar.session_label.text() == "PL-2026-08-27-004"


def test_status_uses_a_shared_status_chip(qapp):
    from shared.theme import StatusChip

    bar = CommandBar()
    bar.set_status("status_success", "Completed")
    assert isinstance(bar.status_chip, StatusChip)
    assert bar.status_chip.text() == "Completed"


def test_the_action_button_is_the_screens_one_primary(qapp):
    bar = CommandBar()
    button = bar.set_action("Start Packing")
    assert button.property("role") == "primary"
    assert button.text() == "Start Packing"


def test_the_action_emits_actionTriggered(qapp):
    bar = CommandBar()
    button = bar.set_action("Start Packing")
    seen = []
    bar.actionTriggered.connect(lambda: seen.append(1))
    button.click()
    assert seen == [1]


def test_set_action_called_twice_relabels_one_button(qapp):
    bar = CommandBar()
    first = bar.set_action("Start Packing")
    second = bar.set_action("Resume Packing")
    assert first is second
    assert second.text() == "Resume Packing"


DATA = {
    "special_groups": {"pinned": {"name": "Pinned"}, "all": {"name": "All Clients"}},
    "custom_groups": [{"id": "g1", "name": "Retail", "color": "#2196F3"}],
    "all_clients": ["A", "B", "Q"],
    "pinned_client_ids": {"A"},
    "group_members": {"g1": ["A", "B"]},
    "card_data": {c: {"ui_settings": {"custom_color": "#4CAF50"}} for c in "ABQ"},
}


def test_the_dropdown_is_pinned_then_groups_then_the_rest(qapp):
    bar = CommandBar()
    bar.set_clients_from(DATA)

    assert [(k, t) for k, _p, t in _rows(bar)] == [
        (ROW_SECTION, "Pinned"),
        (ROW_CLIENT, "A"),
        (ROW_SECTION, "Retail"),
        (ROW_CLIENT, "A"),
        (ROW_CLIENT, "B"),
        (ROW_SECTION, "All Clients"),
        (ROW_CLIENT, "Q"),
        (ROW_ACTION, "Refresh clients"),
        (ROW_ACTION, "New client…"),
        (ROW_ACTION, "Manage groups…"),
    ]


def test_section_captions_cannot_be_chosen(qapp):
    bar = CommandBar()
    bar.set_clients_from(DATA)
    model = bar.client_selector.model()

    captions = [i for i in range(model.rowCount())
                if model.item(i).data(Qt.UserRole) == ROW_SECTION]
    assert captions
    for i in captions:
        assert not model.item(i).isEnabled()


def test_every_client_row_carries_its_own_colour(qapp):
    bar = CommandBar()
    bar.set_clients_from(DATA)
    model = bar.client_selector.model()

    for i in range(model.rowCount()):
        if model.item(i).data(Qt.UserRole) == ROW_CLIENT:
            assert not model.item(i).icon().isNull()


def test_rebuilding_does_not_duplicate_rows_or_emit(qapp):
    bar = CommandBar()
    seen = []
    bar.clientChanged.connect(seen.append)

    bar.set_clients_from(DATA)
    before = _rows(bar)
    bar.set_clients_from(DATA)

    assert _rows(bar) == before
    assert seen == []


def test_choosing_an_action_row_does_not_change_the_client(qapp):
    bar = CommandBar()
    bar.set_clients_from(DATA)
    bar.set_current_client("Q")
    chosen = []
    bar.clientChanged.connect(chosen.append)
    opened = []
    bar.manageGroupsRequested.connect(lambda: opened.append(True))

    rows = _rows(bar)
    action_row = next(i for i, (k, _p, t) in enumerate(rows)
                      if k == ROW_ACTION and t == "Manage groups…")
    bar.client_selector.activated.emit(action_row)

    assert opened == [True]
    assert bar.current_client() == "Q"
    assert chosen == []


def test_set_current_client_selects_the_first_matching_row(qapp):
    bar = CommandBar()
    bar.set_clients_from(DATA)

    bar.set_current_client("B")

    assert bar.current_client() == "B"


def _action_row(bar, label):
    return next(i for i, (k, _p, t) in enumerate(_rows(bar))
                if k == ROW_ACTION and t == label)


def test_the_refresh_row_asks_for_a_refresh(qapp):
    bar = CommandBar()
    bar.set_clients_from(DATA)
    seen = []
    bar.refreshRequested.connect(lambda: seen.append(True))

    bar.client_selector.activated.emit(_action_row(bar, "Refresh clients"))

    assert seen == [True]


def test_a_wheel_notch_never_changes_the_client_or_fires_an_action(qapp):
    """A scroll over the bar used to reload the client -- which clears the
    undo history -- and one row on, to open the modal create dialog."""
    from PySide6.QtCore import QPoint, QPointF
    from PySide6.QtGui import QWheelEvent

    bar = CommandBar()
    bar.set_clients_from(DATA)
    bar.set_current_client("Q")
    chosen, created = [], []
    bar.clientChanged.connect(chosen.append)
    bar.createClientRequested.connect(lambda: created.append(True))

    for delta in (120, -120, -120, -120):
        bar.client_selector.wheelEvent(
            QWheelEvent(
                QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, delta),
                Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False,
            )
        )

    assert bar.current_client() == "Q"
    assert chosen == []
    assert created == []


def test_arrow_keys_on_a_closed_box_step_over_the_action_rows(qapp):
    """Down from the last client used to land on "New client…" and open it."""
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent

    bar = CommandBar()
    bar.set_clients_from(DATA)
    bar.set_current_client("Q")          # the last client row
    created = []
    bar.createClientRequested.connect(lambda: created.append(True))

    down = QKeyEvent(QEvent.KeyPress, Qt.Key_Down, Qt.NoModifier)
    bar.client_selector.keyPressEvent(down)
    assert bar.current_client() == "Q"   # nowhere left to go
    assert created == []

    up = QKeyEvent(QEvent.KeyPress, Qt.Key_Up, Qt.NoModifier)
    bar.client_selector.keyPressEvent(up)
    assert bar.current_client() == "B"


def test_a_fresh_dropdown_shows_no_selection(qapp):
    """Row 0 is always a caption; QComboBox would display it as a choice."""
    bar = CommandBar()
    bar.set_clients_from(DATA)

    assert bar.current_client() == ""
    assert bar.client_selector.currentIndex() == -1


def test_a_selection_made_before_the_rows_arrive_still_wins(qapp):
    """refresh() is async: create-client selects the new id before its row
    exists, and the rebuild must honour it rather than snap back."""
    bar = CommandBar()
    bar.set_clients_from(DATA)
    bar.set_current_client("A")

    bar.set_current_client("NEW")        # not in the model yet
    assert bar.current_client() == "A"

    with_new = dict(DATA, all_clients=[*DATA["all_clients"], "NEW"])
    bar.set_clients_from(with_new)

    assert bar.current_client() == "NEW"


def test_bind_action_mirrors_the_bound_buttons_label_and_state(qapp):
    source = QPushButton("▶ Run Analysis")
    source.setToolTip("Start the fulfillment analysis")
    source.setEnabled(False)

    bar = CommandBar()
    bar.bind_action(source)

    assert bar.action_button.text() == "▶ Run Analysis"
    assert bar.action_button.toolTip() == "Start the fulfillment analysis"
    assert not bar.action_button.isEnabled()
    assert not bar.action_button.isHidden()


def test_a_later_setEnabled_on_the_source_reaches_the_bar(qapp):
    """QWidget has no enabledChanged signal; EnabledChange is the only notice."""
    source = QPushButton("Run")
    source.setEnabled(False)
    bar = CommandBar()
    bar.bind_action(source)

    source.setEnabled(True)

    assert bar.action_button.isEnabled()


def test_the_bars_click_fires_the_bound_buttons_own_connections(qapp):
    source = QPushButton("Run")
    seen = []
    source.clicked.connect(lambda: seen.append(1))
    bar = CommandBar()
    bar.bind_action(source)

    bar.action_button.click()

    assert seen == [1]


def test_binding_none_hides_the_slot(qapp):
    bar = CommandBar()
    bar.bind_action(QPushButton("Run"))
    bar.bind_action(None)
    assert bar.action_button.isHidden()


def test_rebinding_stops_the_old_button_reaching_the_bar(qapp):
    first, second = QPushButton("First"), QPushButton("Second")
    bar = CommandBar()
    bar.bind_action(first)
    bar.bind_action(second)

    first.setEnabled(False)

    assert bar.action_button.text() == "Second"
    assert bar.action_button.isEnabled()


def test_a_theme_toggle_restyles_the_bar(qapp):
    from gui.theme_manager import get_theme_manager

    manager = get_theme_manager()
    bar = CommandBar()
    before = bar.styleSheet()
    manager.toggle_theme()
    try:
        assert bar.styleSheet() != before
    finally:
        manager.toggle_theme()
