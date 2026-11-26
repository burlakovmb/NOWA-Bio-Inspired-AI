#!/usr/bin/env python3
"""Issue #28 bench: cost of recording the deaths of one colony tick.

From the repository root, with the colony demo's dependencies installed:

    python tools/bench_issue_28.py [--agents 48] [--deaths 4] [--ticks 20] [--memorials 400]

A runner holds ``--agents`` animals and a death registry that already keeps ``--memorials`` memorials and saves to a
temporary folder. Each measured tick kills ``--deaths`` animals and records them the way ``SimulationRunner.tick``
does; the dead are replaced so every tick starts from the same population. Prints the median wall time of the
death handling per tick, and the number of registry writes per tick. On a tree without the batched path the
deaths are recorded one by one, as the old tick did.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "src", ROOT / "Demo" / "Colony chinchillas" / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from colony_agent import ChinchillaAgent  # noqa: E402
from simulation_runner import SimulationRunner  # noqa: E402


def _animal(index):
    agent = ChinchillaAgent(sex="F" if index % 2 == 0 else "M", rng_seed=index + 1)
    agent.agent_id = f"a{index:04d}"
    agent.generation = 1 + index % 3
    return agent


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--agents", type=int, default=48)
    parser.add_argument("--deaths", type=int, default=4)
    parser.add_argument("--ticks", type=int, default=20)
    parser.add_argument("--memorials", type=int, default=400)
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory() as folder:
        runner = SimulationRunner(death_journal_path=str(Path(folder) / "deaths.jsonl"))
        spare = [_animal(index) for index in range(args.agents + args.deaths)]
        for agent in spare[: args.agents]:
            runner.add_agent(agent)
        templates = [_animal(10_000 + index) for index in range(7)]
        registry = runner.death_registry
        save_dir, registry._save_dir = registry._save_dir, None  # fill in memory, the same way on any tree
        for index in range(args.memorials):  # a registry that has seen a long life
            old = templates[index % len(templates)]
            old.agent_id = f"old{index:05d}"  # register_death copies what it needs into the memorial
            registry.register_death(old, float(index), {})
        registry._save_dir = save_dir
        registry.autosave()

        writes = []
        original = runner.death_registry.autosave
        runner.death_registry.autosave = lambda: (writes.append(1), original())[1]
        batched = hasattr(runner, "_handle_agent_deaths")
        times = []
        for tick in range(args.ticks):
            victims = [agent.agent_id for agent in runner.agents[: args.deaths]]
            start = time.perf_counter()
            if batched:
                runner._handle_agent_deaths(victims)
            else:
                for agent_id in victims:
                    runner._handle_agent_death(agent_id)
            times.append((time.perf_counter() - start) * 1000.0)
            for index in range(args.deaths):  # refill so every tick starts from the same population
                fresh = _animal(args.agents + index)
                fresh.agent_id = f"t{tick:03d}-{index}"
                runner.add_agent(fresh)

    print(json.dumps({
        "path": "batched" if batched else "one-by-one",
        "agents": args.agents, "deaths_per_tick": args.deaths, "memorials": args.memorials,
        "median_ms_per_tick": round(statistics.median(times), 2),
        "registry_writes_per_tick": round(len(writes) / args.ticks, 2),
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
