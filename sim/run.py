"""Run the two-PC simulation: python -m sim.run [scenario ...] --packing-tool PATH [--list]."""

import argparse
import sys
import traceback
from datetime import datetime
from pathlib import Path

from sim import invariants, scenarios
from sim.world import REPO, World


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("names", nargs="*", help="scenarios to run (default: all)")
    parser.add_argument("--packing-tool", type=Path, default=REPO.parent / "packing-tool")
    parser.add_argument("--list", action="store_true", help="list scenarios and exit")
    args = parser.parse_args(argv)
    if args.list:
        print("\n".join(scenarios.ALL))
        return 0
    unknown = [n for n in args.names if n not in scenarios.ALL]
    if unknown:
        parser.error(f"unknown scenario(s): {', '.join(unknown)}")
    packing_tool = args.packing_tool.resolve()
    if not (packing_tool / ".venv" / "bin" / "python").exists():
        parser.error(f"no packing-tool venv at {packing_tool}; pass --packing-tool")

    out = REPO / "sim-out" / datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    report = [f"# Simulation run {out.name}\n"]
    found = 0
    for name in args.names or list(scenarios.ALL):
        world = World(out / name, packing_tool, name)
        try:
            scenarios.ALL[name](world)
        except Exception:
            world.findings.append("scenario aborted:\n" + traceback.format_exc(limit=6))
        finally:
            world.close()
        world.findings += invariants.check_all(world.server, frozenset(world.killed_pids))
        verdict = "FIND" if world.findings else "PASS"
        found += bool(world.findings)
        print(f"{verdict} {name}", flush=True)
        report.append(f"## {verdict} {name}\n\n{(scenarios.ALL[name].__doc__ or '').strip()}\n")
        report += [f"- {f}".replace("\n", "\n  ") for f in world.findings]
        if world.findings:
            for log in sorted((out / name / "pcs").glob("*/stderr.log")):
                tail = log.read_text(encoding="utf-8", errors="replace").splitlines()[-15:]
                report.append(f"\n{log.parent.name} stderr tail:\n\n```\n" + "\n".join(tail) + "\n```")
        report.append(f"\nLogs: `{(out / name / 'pcs').relative_to(REPO)}/*/stderr.log`, events: `events.jsonl`\n")
    (out / "report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"report: {out / 'report.md'}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
