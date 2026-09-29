"""Orchestrator side: a temp server, simulated PCs as subprocesses, and the RPC to them."""

import json
import os
import queue
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path

from sim import data

REPO = Path(__file__).resolve().parent.parent

PACKER_CONFIG = """[Network]
FileServerPath = {server}
ConnectionTimeout = 5
LocalCachePath = {cache}

[Logging]
LogLevel = INFO
LogRetentionDays = 30
MaxLogSizeMB = 10

[General]
Environment = development
DebugMode = true

[UI]
RememberLastClient = true
AutoRefreshInterval = 0
"""


class OpFailed(Exception):
    """An op raised inside the agent; the message carries its traceback."""


class AgentDied(Exception):
    """The agent process exited or stopped answering."""


@dataclass
class Reply:
    result: object
    events: list = field(default_factory=list)

    def saw(self, kind: str, text: str = "") -> bool:
        return any(
            e["kind"] == kind and text.lower() in f"{e.get('title', '')}\n{e.get('text', '')}".lower()
            for e in self.events
        )

    def told_operator(self) -> bool:
        """A dialog, toast or error banner: something a person at the PC would see."""
        return any(e["kind"] in ("dialog", "toast", "error_banner") for e in self.events)


class PC:
    def __init__(self, world: "World", name: str, app: str):
        self.world, self.name, self.app = world, name, app
        pc_dir = world.run_dir / "pcs" / name
        home = pc_dir / "home"
        (home / ".config").mkdir(parents=True, exist_ok=True)
        env = {
            **os.environ,
            "COMPUTERNAME": name, "USERNAME": f"user-{name}",
            "HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config"),
            "QT_QPA_PLATFORM": "offscreen", "QTWEBENGINE_DISABLE_SANDBOX": "1",
            "FULFILLMENT_SERVER_PATH": str(world.server), "SIM_FAST_CLOCK": "1",
        }
        if app == "fulfilment":
            python, cwd, extra = REPO / ".venv" / "bin" / "python", REPO, []
        else:
            config = pc_dir / "config.ini"
            config.write_text(PACKER_CONFIG.format(server=world.server, cache=home / "cache"), encoding="utf-8")
            python, cwd, extra = world.packing_tool / ".venv" / "bin" / "python", world.packing_tool, ["--config", str(config)]
            # cwd comes first on sys.path under -m, so packing-tool's gui/shared win over this repo's.
            env["PYTHONPATH"] = os.pathsep.join(p for p in (str(REPO), env.get("PYTHONPATH")) if p)
        self._stderr = (pc_dir / "stderr.log").open("ab")
        self.proc = subprocess.Popen(
            [str(python), "-m", f"sim.agent_{app}", *extra],
            cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self._stderr,
            text=True, encoding="utf-8",
        )
        self.pid = self.proc.pid
        self._lines: queue.Queue = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()
        self._next_id = 0
        self._pending: list[str] = []

    def _read(self) -> None:
        for line in self.proc.stdout:
            self._lines.put(line)
        self._lines.put(None)

    def send(self, op: str, **args) -> None:
        self._next_id += 1
        self._pending.append(op)
        try:
            self.proc.stdin.write(json.dumps({"id": self._next_id, "op": op, "args": args}) + "\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise AgentDied(f"{self.name} is gone ({exc})") from exc

    def receive(self, timeout: float = 30) -> Reply:
        op = self._pending.pop(0)
        try:
            line = self._lines.get(timeout=timeout)
        except queue.Empty:
            self.kill()
            raise AgentDied(f"{self.name} did not answer {op} within {timeout}s") from None
        if line is None:
            raise AgentDied(f"{self.name} exited during {op} (code {self.proc.poll()})")
        msg = json.loads(line)
        reply = Reply(msg["result"], msg["events"])
        self.world.note_events(self.name, op, reply.events)
        if not msg["ok"]:
            raise OpFailed(f"{self.name} {op} failed:\n{msg['error']}")
        return reply

    def call(self, op: str, timeout: float = 30, **args) -> Reply:
        self.send(op, **args)
        return self.receive(timeout)

    def kill(self) -> None:
        if self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait()
            self.world.killed_pids.add(self.pid)

    def quit(self) -> None:
        """A clean exit: says yes to any close-time question."""
        if self.proc.poll() is None:
            try:
                self.call("quit", timeout=30, answers={"": "yes"})
                self.proc.wait(timeout=15)
            except (AgentDied, OpFailed, subprocess.TimeoutExpired):
                self.kill()


class World:
    def __init__(self, run_dir: Path, packing_tool: Path, scenario: str = ""):
        self.run_dir, self.packing_tool, self.scenario = run_dir, packing_tool, scenario
        self.server = run_dir / "server"
        self.server.mkdir(parents=True)
        self.inputs = data.write_inputs(run_dir / "inputs")
        self.findings: list[str] = []
        self.killed_pids: set[int] = set()
        self.pcs: list[PC] = []
        self._events = (run_dir / "events.jsonl").open("a", encoding="utf-8")

    def spawn(self, name: str, app: str) -> PC:
        pc = PC(self, name, app)
        self.pcs.append(pc)
        pc.call("ping", timeout=90)  # startup events (first-run prompts, import errors) land here
        return pc

    def note_events(self, pc: str, op: str, events: list) -> None:
        for event in events:
            self._events.write(json.dumps({"scenario": self.scenario, "pc": pc, "op": op, **event}) + "\n")
            if event["kind"] == "exception" or event.get("unexpected"):
                self.findings.append(f"{pc} {op}: {event['kind']}: {event.get('title', '')} {event['text'][:1500]}")
        self._events.flush()

    def expect(self, cond, message: str) -> None:
        if not cond:
            self.findings.append(message)

    def close(self) -> None:
        for pc in self.pcs:
            pc.quit()
        self._events.close()

    def server_offline(self) -> None:
        """Nothing under the server can be read, listed or created, and the folder stays in place so an
        app that mkdirs its way back in cannot resurrect a phantom server (as a vanished UNC share can't)."""
        self.server.chmod(0o000)

    def server_online(self) -> None:
        self.server.chmod(0o755)

    @staticmethod
    def readonly(path: Path) -> None:
        for p in [path, *path.rglob("*")]:
            p.chmod(0o555 if p.is_dir() else 0o444)

    @staticmethod
    def writable(path: Path) -> None:
        for p in [path, *path.rglob("*")]:
            p.chmod(0o755 if p.is_dir() else 0o644)
