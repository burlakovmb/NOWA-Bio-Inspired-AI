#!/usr/bin/env python3
"""Issue #28 acceptance bench for the colony tick: determinism per seed and colony dynamics.

From the repository root, with the colony demo's dependencies installed:

    python tools/bench_issue_28_colony.py [--seeds 8] [--animals 12] [--minutes 20] [--json out.json]

Per seed a colony of ``--animals`` runs for ``--minutes`` of simulated time. Every 60 s one awake animal, chosen by
the seed, is scared (a stress impulse of 0.8): the colony has no predator, so this stands in for one. Per seed:

- deaths, births;
- mean stress over all animals and ticks;
- food intake (the drop of pellets and hay in the bowls, refills not counted);
- reaction time: from the scare to the first other animal hearing an alarm call, in simulated seconds, and from the
  scare to the first neighbour of the scared animal (same or next zone) hiding or fleeing;
- alarm cascade: the number of other animals calling within 20 s after the scare;
- a digest of the trajectory (every animal's zone and action every tick), to compare runs. Stress is left out:
  the core's decay partly follows the wall clock, so it differs in the last digits between runs.

Randomness is seeded the same way on any tree: the module-level ``random`` (which the NOWA core samples actions
from, issue #14, and which the old tick shuffled), each animal's ``rng_seed``, and the runner's ``seed`` where the
runner takes one.
"""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import random
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
from sensor_system import is_same_or_adjacent  # noqa: E402
from simulation_runner import SimulationRunner  # noqa: E402

SCARE_EVERY_S = 60.0
SCARE_STRESS = 0.8
CASCADE_WINDOW_S = 20.0
FEAR_ACTIONS = frozenset({"hide", "flee"})


def _calling(animal) -> bool:
    """Is the animal calling now, read without sampling its alarm state."""
    return bool(getattr(animal, "_alarm_call_open", False)) and float(animal.sim_time) <= float(
        getattr(animal, "_alarm_event_until", -1.0)) + 1e-9


def run(seed: int, animals: int, minutes: float, folder: str, sim_clock: bool = False) -> dict:
    real_time = time.time
    clock = [1_700_000_000.0]
    if sim_clock:
        # The core reads the wall clock (affect decay, timestamps), so a run depends on how fast the machine is.
        # With --sim-clock time.time() follows the simulated time instead, which makes a seeded run repeatable.
        time.time = lambda: clock[0]
    try:
        return _run(seed, animals, minutes, folder, clock)
    finally:
        time.time = real_time


def _run(seed: int, animals: int, minutes: float, folder: str, clock: list) -> dict:
    random.seed(seed)
    kwargs = {"death_journal_path": str(Path(folder) / f"deaths-{seed}.jsonl")}
    if "seed" in inspect.signature(SimulationRunner.__init__).parameters:
        kwargs["seed"] = seed
    runner = SimulationRunner(**kwargs)
    for index in range(animals):
        animal = ChinchillaAgent(
            sex="F" if index % 2 == 0 else "M", agent_id=f"s{seed}-a{index:02d}", rng_seed=seed * 1000 + index
        )
        runner.add_agent(animal)

    eaten = 0.0
    food = runner.resources.food_pellets + runner.resources.hay
    scare_rng = random.Random(seed + 7)
    digest = hashlib.sha256()
    stress_sum, stress_n = 0.0, 0
    reactions, cascades = [], []
    open_scares = []  # [time, scared id, heard after, callers, neighbour ids, fled after]
    fled = []
    next_scare = SCARE_EVERY_S
    end = minutes * 60.0
    while runner.sim_time < end:
        if runner.sim_time >= next_scare:
            awake = [a for a in runner.agents if not a.is_sleeping]
            if awake:
                target = awake[scare_rng.randrange(len(awake))]
                target._apply_affect_impulse(stress=SCARE_STRESS, intensity=1.0)
                near = {a.agent_id for a in runner.agents if a is not target and a.current_action not in FEAR_ACTIONS and is_same_or_adjacent(target.position, a.position)}
                open_scares.append([runner.sim_time, target.agent_id, None, set(), near, None])
            next_scare += SCARE_EVERY_S
        clock[0] += SimulationRunner.SIM_DT
        runner.tick(SimulationRunner.SIM_DT)
        now = runner.sim_time
        # Food taken this tick: the drop in the bowls' stock. A refill raises it and is not counted.
        left = runner.resources.food_pellets + runner.resources.hay
        eaten += max(0.0, food - left)
        food = left
        for animal in runner.agents:
            stress_sum += float(animal.stress)
            stress_n += 1
            digest.update(f"{animal.agent_id}|{animal.position}|{animal.current_action};".encode())
        for scare in open_scares:
            t0, scared, reacted, callers, near, ran = scare
            if now - t0 > CASCADE_WINDOW_S:
                continue
            callers.update(a.agent_id for a in runner.agents if a.agent_id != scared and _calling(a))
            if reacted is None and any(
                a.agent_id != scared and getattr(a, "_alarm_heard_this_tick", False) for a in runner.agents
            ):
                scare[2] = now - t0
            if ran is None and any(a.agent_id in near and a.current_action in FEAR_ACTIONS for a in runner.agents):
                scare[5] = now - t0
    for t0, _scared, reacted, callers, near, ran in open_scares:
        if end - t0 >= CASCADE_WINDOW_S:
            cascades.append(len(callers))
            if reacted is not None:
                reactions.append(reacted)
            if near and ran is not None:
                fled.append(ran)
    return {
        "seed": seed,
        "deaths": runner.total_deaths,
        "births": runner.total_births,
        "mean_stress": round(stress_sum / max(1, stress_n), 4),
        "food_intake": round(eaten, 4),
        "scares": len(cascades),
        "reaction_s_median": round(statistics.median(reactions), 2) if reactions else None,
        "heard_share": round(len(reactions) / max(1, len(cascades)), 2),
        "cascade_mean": round(statistics.mean(cascades), 2) if cascades else None,
        "flee_s_median": round(statistics.median(fled), 2) if fled else None,
        "fled": len(fled),
        "digest": digest.hexdigest()[:16],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seeds", type=int, default=8)
    parser.add_argument("--first-seed", type=int, default=1)
    parser.add_argument("--animals", type=int, default=12)
    parser.add_argument("--minutes", type=float, default=20.0)
    parser.add_argument("--json", default=None)
    parser.add_argument("--sim-clock", action="store_true", help="time.time() follows the simulated time")
    args = parser.parse_args(argv)
    rows = []
    with tempfile.TemporaryDirectory() as folder:
        for seed in range(args.first_seed, args.first_seed + args.seeds):
            rows.append(run(seed, args.animals, args.minutes, folder, args.sim_clock))
            print(json.dumps(rows[-1]), flush=True)
    if args.json:
        Path(args.json).write_text(json.dumps(rows, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
