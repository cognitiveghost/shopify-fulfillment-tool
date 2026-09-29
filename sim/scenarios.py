"""The scenarios. Each takes a fresh World and records what it finds through world.expect."""

import time
from pathlib import Path

from sim.data import CLIENT, COURIERS
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


def analysed_session(world: World):
    """PC-A creates the client and a session, analyses the synthetic inputs and makes the DHL and DPD lists."""
    a = fulfilment_pc(world, "PC-A", create=True)
    session = a.call("new_session").result["session_path"]
    a.call("set_inputs", orders=str(world.inputs.orders), stock=str(world.inputs.stock))
    a.call("run_analysis", timeout=150)
    lists = a.call("generate_packing_lists", couriers=list(COURIERS)).result["lists"]
    world.expect(lists == ["DHL_Orders", "DPD_Orders"], f"packing lists generated: {lists}")
    return a, session


def stale_save(world: World) -> None:
    """Two PCs edit one session: the second PC's stale save is refused visibly, the first PC's edit survives."""
    a, session = analysed_session(world)
    d = fulfilment_pc(world, "PC-D")
    d.call("open_session", session_path=session)
    fulfillable = [o["order"] for o in a.call("orders").result if o["status"] == "Fulfillable"]
    x, y = fulfillable[0], fulfillable[1]
    a.call("set_fulfillable", order=x, value=False)
    r = d.call("set_fulfillable", order=y, value=False)
    world.expect(r.told_operator(), "PC-D's edit to a session PC-A had changed was not refused visibly")
    e = fulfilment_pc(world, "PC-E")
    e.call("open_session", session_path=session)
    status = {o["order"]: o["status"] for o in e.call("orders").result}
    world.expect(status.get(x) != "Fulfillable", f"PC-A's hold on {x} was lost (status {status.get(x)})")
    world.expect(status.get(y) == "Fulfillable", f"PC-D's stale edit to {y} was saved (status {status.get(y)})")


def config_race(world: World) -> None:
    """Two PCs save the client config 20 times each, interleaved: it always parses and ends as one writer's value."""
    a = fulfilment_pc(world, "PC-A", create=True)
    d = fulfilment_pc(world, "PC-D")
    for i in range(20):
        a.send("save_client_setting", key="low_stock_threshold", value=100 + i)
        d.send("save_client_setting", key="low_stock_threshold", value=200 + i)
        a.receive()
        d.receive()
    final = a.call("client_setting", key="low_stock_threshold").result["value"]
    world.expect(final in (119, 219), f"final low_stock_threshold {final} is neither writer's last value")


def killed_mid_analysis(world: World) -> None:
    """PC-A dies 0.2 s into an analysis; PC-D can still open the session without an exception."""
    a = fulfilment_pc(world, "PC-A", create=True)
    session = a.call("new_session").result["session_path"]
    a.call("set_inputs", orders=str(world.inputs.orders), stock=str(world.inputs.stock))
    a.send("run_analysis")
    time.sleep(0.2)
    a.kill()
    d = fulfilment_pc(world, "PC-D")
    d.call("open_session", session_path=session)  # exceptions surface as findings through the events


def packer_pc(world: World, name: str):
    return world.spawn(name, "packer")


def list_args(session: str, list_name: str) -> dict:
    return {"client_id": CLIENT, "session_path": session, "list_name": list_name}


def pack_all(pc) -> list[str]:
    """Pack every order of the open list that is not packed yet; returns the completed orders."""
    state = pc.call("state").result
    for order in state["all"]:
        if order not in state["completed"]:
            pc.call("pack_order", order=order)
    return pc.call("state").result["completed"]


def pipeline(world: World) -> None:
    """PC-A analyses and makes lists; PC-B packs all of DHL; PC-A's next session on the same orders
    flags every order the first session found fulfillable as a repeat (ADR 0012), and nothing else."""
    a, session = analysed_session(world)
    fulfillable = {o["order"] for o in a.call("orders").result if o["status"] == "Fulfillable"}
    b = packer_pc(world, "PC-B")
    started = b.call("start_list", **list_args(session, "DHL_Orders")).result["started"]
    world.expect(started, "PC-B could not start DHL_Orders")
    if not started:
        return
    packed = pack_all(b)
    b.call("end_session")
    b.quit()
    a.call("new_session")
    a.call("set_inputs", orders=str(world.inputs.orders), stock=str(world.inputs.stock))
    a.call("run_analysis", timeout=150)
    repeats = {o["order"] for o in a.call("orders").result if o["repeat"]}
    world.expect(set(packed) <= repeats, f"packed on PC-B but not flagged repeat: {sorted(set(packed) - repeats)}")
    world.expect(repeats == fulfillable, f"repeats differ from session 1's fulfillable orders: {sorted(repeats ^ fulfillable)}")


ALL = {
    "pipeline": pipeline,
    "same_day_sessions": same_day_sessions,
    "stale_save": stale_save,
    "config_race": config_race,
    "killed_mid_analysis": killed_mid_analysis,
}
