from gui.components.commandbar import CommandBar


def test_clients_populate_the_selector(qapp):
    bar = CommandBar()
    bar.set_clients(["Acme", "Globex"])
    assert bar.client_selector.count() == 2
    assert bar.current_client() == "Acme"


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
    bar.client_selector.setCurrentIndex(1)
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
