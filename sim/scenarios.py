"""The scenarios. Each takes a fresh World and records what it finds through world.expect."""

from pathlib import Path

from sim.data import CLIENT
from sim.world import World


def fulfilment_pc(world: World, name: str, create: bool = False):
    pc = world.spawn(name, "fulfilment")
    if create:
        pc.call("create_client", client_id=CLIENT)
    pc.call("select_client", client_id=CLIENT)
    return pc


def same_day_sessions(world: World) -> None:
    """Two fulfilment PCs create a session at the same moment: two distinct sessions, both intact."""
    a = fulfilment_pc(world, "PC-A", create=True)
    d = fulfilment_pc(world, "PC-D")
    a.send("new_session")
    d.send("new_session")
    pa, pd = a.receive().result["session_path"], d.receive().result["session_path"]
    world.expect(pa and pd and pa != pd, f"new sessions collided: A={pa} D={pd}")
    for path in (pa, pd):
        if path:
            world.expect((Path(path) / "session_info.json").exists(), f"{path} has no session_info.json")


ALL = {
    "same_day_sessions": same_day_sessions,
}
