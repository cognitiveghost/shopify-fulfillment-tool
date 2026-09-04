"""First run: the shell with nothing configured.

Every test here points the app at a path that does not exist, which is what
an unreachable UNC share looks like from inside ProfileManager.
"""

import pytest
from PySide6.QtWidgets import QApplication

from shopify_tool.profile_manager import NetworkError, ProfileManager


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def unreachable(tmp_path, monkeypatch):
    """A path under a file, so mkdir cannot succeed and neither can a touch."""
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("")
    path = blocker / "server"
    monkeypatch.setenv("FULFILLMENT_SERVER_PATH", str(path))
    return path


def test_the_default_still_refuses_to_construct(unreachable):
    # The existing contract is unchanged for every caller that does not ask.
    with pytest.raises(NetworkError):
        ProfileManager()


def test_require_connection_false_returns_a_usable_object(unreachable):
    manager = ProfileManager(require_connection=False)
    assert manager.is_network_available is False
    # Every path it publishes is still a real Path, so no call site becomes
    # None-unsafe and no None-guard is written anywhere.
    assert manager.base_path.name == "server"
    assert manager.clients_dir.parent == manager.base_path


def test_a_reachable_share_is_unaffected_by_the_keyword(tmp_path, monkeypatch):
    monkeypatch.setenv("FULFILLMENT_SERVER_PATH", str(tmp_path))
    assert ProfileManager(require_connection=False).is_network_available is True
