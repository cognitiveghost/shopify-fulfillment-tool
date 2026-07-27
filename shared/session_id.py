"""Canonical session_id derivation shared between Packing Tool and Shopify
Tool, so a record written by one and a record written by the other for the
same real-world session carry the exact same session_id string.
"""
from pathlib import Path


def derive_session_id(session_path: str | Path) -> str:
    """Derive a session_id from a session directory path.

    Both apps must call this instead of building their own session_id.
    Shopify Tool already used the folder name (Path(session_path).name);
    Packing Tool used to fall back, in one code path, to
    f"{current_session_path}_{current_packing_list}", which never matched
    Shopify Tool's value for the same real-world session.
    """
    return Path(session_path).name
