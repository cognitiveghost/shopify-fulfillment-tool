"""The Client > Profile page: name, group, colour, pin (spec A4).

Owns no shopify_config.json key: collect() is empty and the window writes
profile_updates() to client_config.json. No Qt import.
"""

import json

from gui.settings.contract import PageContract
from shared.i18n import N_, _

NO_GROUP = N_("No group")


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
        self.mark_clean()  # the page opens clean; PageContract compares against this

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
        return _("Set {what}", what=_("Client name")) if not self.name.strip() else None

    def blocker_key(self) -> str:
        return "profile-name"

    def snapshot(self) -> str:
        # collect() is empty, so the unsaved dot needs the page's own values.
        return json.dumps([self.name, self.group_id, self.colour, self.pinned])

    def profile_updates(self):
        if not self.is_dirty():
            return None
        ui = {"group_id": self.group_id, "is_pinned": self.pinned}
        if self.colour:  # never write an empty colour over the default
            ui["custom_color"] = self.colour
        return {"client_name": self.name.strip(), "ui_settings": ui}

    def _stat(self, key, empty):
        value = self.stats.get(key)
        return empty if value in (None, "") else str(value)

    def view(self) -> dict:
        cid = self.client_id
        return {
            "page": "profile",
            "title": _("Profile"),
            "subtitle": _("How {client} appears in the client list.", client=self.name.strip() or cid),
            "action": "",
            "profile": {
                "name": {
                    "value": self.name,
                    "problem": _("Enter a name.") if not self.name.strip() else "",
                },
                "client_id": cid,
                "groups": [{"value": "", "label": _(NO_GROUP), "checked": self.group_id is None}]
                + [
                    {
                        "value": g.get("id", ""),
                        "label": g.get("name", _("Unknown")),
                        "checked": g.get("id") == self.group_id,
                    }
                    for g in self.groups
                ],
                "colour": self.colour,
                "pinned": self.pinned,
                "stats": [
                    {"label": _("Sessions"), "value": self._stat("total_sessions", "0")},
                    {"label": _("Last session"), "value": self._stat("last_session_date", _("Never"))},
                    {"label": _("Last accessed"), "value": self._stat("last_accessed", _("Unknown"))},
                ],
                "archive": {
                    "label": _("Archive client…"),
                    "hint": _(
                        "Hides {client} in Fulfilment and Packing. Its sessions are kept and it can be "
                        "restored from Archived clients.",
                        client=cid,
                    ),
                },
                "delete": {
                    "label": _("Delete client…"),
                    "enabled": not self.has_sessions,
                    "hint": _("{client} has sessions, so it can only be archived.", client=cid)
                    if self.has_sessions
                    else _("Removes {client} and its folders for good.", client=cid),
                },
            },
        }
