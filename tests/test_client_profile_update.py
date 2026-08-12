"""Regression: a sidebar pin toggle during an open Client Profile dialog
must survive that dialog's save."""
import pytest


def test_update_client_profile_preserves_concurrent_ui_changes(profile_manager):
    profile_manager.create_client_profile("M", "My Client")

    # The dialog opens and reads the config it will later write back.
    stale = profile_manager.load_client_config("M")
    assert stale["ui_settings"]["is_pinned"] is False

    # Meanwhile the sidebar pins the client.
    profile_manager.update_ui_settings("M", {"is_pinned": True})

    # The dialog saves only the fields it owns.
    profile_manager.update_client_profile(
        "M", name="Renamed Co", ui_settings={"custom_color": "#123456"}
    )

    after = profile_manager.load_client_config("M")
    assert after["client_name"] == "Renamed Co"
    assert after["ui_settings"]["custom_color"] == "#123456"
    assert after["ui_settings"]["is_pinned"] is True, "sidebar pin was clobbered"


def test_update_client_profile_rejects_unknown_client(profile_manager):
    from shopify_tool.profile_manager import ProfileManagerError

    with pytest.raises(ProfileManagerError):
        profile_manager.update_client_profile("NOPE", name="x")
