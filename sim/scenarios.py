"""The scenarios. Each takes a fresh World and records what it finds through world.expect."""

import json
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
        for pc, r in (("PC-A", a.receive()), ("PC-D", d.receive())):
            world.expect(r.result["saved"], f"{pc}'s save {i} of the client config failed")
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
    flags every order the first session found fulfillable as a repeat (ADR 0012), and nothing else.

    Session 1's own history already flags every packed order, so this cannot show Fulfilment reading
    the Packer's signal; invariant 6 checks that the signal is written."""
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


def lock_race(world: World) -> None:
    """PC-B and PC-C open the same list at the same moment: exactly one gets it, the other is told
    it is open on another PC."""
    a, session = analysed_session(world)
    a.quit()
    b, c = packer_pc(world, "PC-B"), packer_pc(world, "PC-C")
    b.send("start_list", answers={"another PC": "ok"}, **list_args(session, "DHL_Orders"))
    c.send("start_list", answers={"another PC": "ok"}, **list_args(session, "DHL_Orders"))
    rb, rc = b.receive(60), c.receive(60)
    got = (rb.result["started"], rc.result["started"])
    world.expect(sorted(got) == [False, True], f"started: PC-B={got[0]} PC-C={got[1]}")
    loser = rc if got[0] else rb
    # Every sim PC shares one hostname, so the dialog cannot name the owning PC: match the wording.
    world.expect(loser.saw("dialog", "another PC"), "the PC that lost the race was not told the list is open elsewhere")
    for pc, started in ((b, got[0]), (c, got[1])):
        if started:
            pc.call("end_session", timeout=60)


def crash_takeover(world: World) -> None:
    """PC-B packs 5 orders and is killed; after the lock goes stale PC-C takes the list over, keeps
    those 5 and finishes it, every order completed exactly once."""
    a, session = analysed_session(world)
    a.quit()
    b = packer_pc(world, "PC-B")
    b.call("start_list", **list_args(session, "DHL_Orders"))
    orders = b.call("state").result["all"]
    for order in orders[:5]:
        b.call("pack_order", order=order)
    time.sleep(2)  # let the async state writer land: a crash inside that window is a separate question
    b.kill()
    time.sleep(5)  # STALE_TIMEOUT (4 s under SIM_FAST_CLOCK) + 1
    c = packer_pc(world, "PC-C")
    r = c.call("start_list", answers={"stale": "yes"}, **list_args(session, "DHL_Orders"))
    world.expect(r.result["started"], "PC-C could not take over the stale list")
    if not r.result["started"]:
        return
    resumed = c.call("state").result["completed"]
    world.expect(set(orders[:5]) <= set(resumed), f"orders lost in the crash: {sorted(set(orders[:5]) - set(resumed))}")
    done = pack_all(c)
    world.expect(sorted(done) == sorted(orders), f"after takeover completed {len(done)} of {len(orders)}")
    c.call("end_session", timeout=60)


def parallel_lists(world: World) -> None:
    """PC-B packs DHL while PC-C packs DPD, one order each in turn: both lists' orders reach the packed signal."""
    a, session = analysed_session(world)
    a.quit()
    b, c = packer_pc(world, "PC-B"), packer_pc(world, "PC-C")
    for pc, name in ((b, "DHL_Orders"), (c, "DPD_Orders")):
        started = pc.call("start_list", **list_args(session, name)).result["started"]
        world.expect(started, f"{pc.name} could not start {name}")
        if not started:
            return
    ob, oc = b.call("state").result["all"], c.call("state").result["all"]
    for i in range(max(len(ob), len(oc))):
        if i < len(ob):
            b.call("pack_order", order=ob[i])
        if i < len(oc):
            c.call("pack_order", order=oc[i])
    b.call("end_session", timeout=60)
    c.call("end_session", timeout=60)
    b.quit()
    c.quit()
    progress = json.loads((Path(session) / "session_info.json").read_text(encoding="utf-8")).get("packing_progress", {})
    for name, orders in (("DHL_Orders", ob), ("DPD_Orders", oc)):
        signal = set((progress.get(name) or {}).get("completed_orders", []))
        world.expect(signal == set(orders), f"{name}: packed signal holds {len(signal)} of {len(orders)} orders")


def server_vanishes_mid_pack(world: World) -> None:
    """The server goes away while PC-B packs: PC-B is told, nothing crashes, and once the server is back
    packing continues with the pre-outage order kept."""
    a, session = analysed_session(world)
    a.quit()
    b = packer_pc(world, "PC-B")
    b.call("start_list", **list_args(session, "DHL_Orders"))
    orders = b.call("state").result["all"]
    b.call("pack_order", order=orders[0])
    time.sleep(2)
    world.server_offline()
    try:
        r1 = b.call("pack_order", order=orders[1])
        time.sleep(3)  # heartbeat (1 s) and async writes hit the missing server; their events ride on the next reply
        r2 = b.call("state")
        world.expect(r1.told_operator() or r2.told_operator(),
                     "PC-B kept packing with the server gone and was not told")
    finally:
        world.server_online()
    if not b.call("state").result["active"]:  # a lost lock tears the list down by design
        b.call("start_list", answers={"stale": "yes"}, **list_args(session, "DHL_Orders"))
    st = b.call("state").result
    world.expect(orders[0] in st["completed"], f"{orders[0]}, packed before the outage, was lost")
    if st["active"]:
        b.call("pack_order", order=next(o for o in orders if o not in st["completed"]))
        b.call("end_session", timeout=60)


def readonly_end(world: World) -> None:
    """The session folder turns read-only before PC-B ends its list: PC-B is told, nothing crashes, no
    partial files; once writable again the list ends cleanly with its packed orders kept."""
    a, session = analysed_session(world)
    a.quit()
    b = packer_pc(world, "PC-B")
    b.call("start_list", **list_args(session, "DHL_Orders"))
    orders = b.call("state").result["all"]
    for order in orders[:2]:
        b.call("pack_order", order=order)
    time.sleep(2)
    world.readonly(Path(session))
    try:
        r = b.call("end_session", timeout=60, answers={"end failed": "ok"})
        world.expect(r.told_operator(), "ending a list on a read-only share told the operator nothing")
    finally:
        world.writable(Path(session))
    if b.call("state").result["active"]:
        world.expect(b.call("end_session", timeout=60).result["ended"], "the list would not end once writable")
    state_file = Path(session) / "packing" / "DHL_Orders" / "packing_state.json"
    kept = [c["order_number"] for c in json.loads(state_file.read_text(encoding="utf-8")).get("completed", [])]
    world.expect(set(orders[:2]) <= set(kept), f"packed orders lost: {sorted(set(orders[:2]) - set(kept))}")


ALL = {
    "pipeline": pipeline,
    "same_day_sessions": same_day_sessions,
    "stale_save": stale_save,
    "config_race": config_race,
    "killed_mid_analysis": killed_mid_analysis,
    "lock_race": lock_race,
    "crash_takeover": crash_takeover,
    "parallel_lists": parallel_lists,
    "server_vanishes_mid_pack": server_vanishes_mid_pack,
    "readonly_end": readonly_end,
}
