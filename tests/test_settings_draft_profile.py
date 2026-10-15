"""ProfileDraft: the Client > Profile page's values, with no widget (spec A4)."""

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
