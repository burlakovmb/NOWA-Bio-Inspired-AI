"""Issue #28 item 5: one snapshot per tick read through a symmetric zone adjacency matrix.

The adjacency is symmetric, every animal perceives the colony as it stood at the start of the tick (so the turn
order does not change what it perceives), the turn order comes from the colony's seeded generator, and a seeded
colony repeats its trajectory.
"""

from __future__ import annotations

import random
import time

from colony_agent import ChinchillaAgent
from sensor_system import ADJACENCY, ADJACENT_ZONES, NEIGHBOURS, ZONES
from simulation_runner import SimulationRunner
from zone_snapshot import ZoneSnapshot


def _colony(seed: int, count: int, journal: str) -> SimulationRunner:
    random.seed(seed)
    runner = SimulationRunner(death_journal_path=journal, seed=seed)
    for index in range(count):
        runner.add_agent(
            ChinchillaAgent(
                sex="F" if index % 2 == 0 else "M",
                name=f"z{index}",
                agent_id=f"issue28-{seed}-{index}",
                rng_seed=seed * 100 + index,
            )
        )
    return runner


def test_adjacency_is_symmetric_and_matches_the_matrix() -> None:
    for zone, near in ADJACENT_ZONES.items():
        for other in near:
            assert zone in ADJACENT_ZONES[other], f"{zone} -> {other} is one-way"
    for row, zone in enumerate(ZONES):
        assert ADJACENCY[row][row] == 1
        for col, other in enumerate(ZONES):
            assert ADJACENCY[row][col] == ADJACENCY[col][row]
            assert ADJACENCY[row][col] == (1 if row == col or other in ADJACENT_ZONES[zone] else 0)
        assert NEIGHBOURS[zone] == tuple(sorted(ADJACENT_ZONES[zone]))


def test_snapshot_rows_match_a_scan_of_the_colony(tmp_path) -> None:
    runner = _colony(3, 10, str(tmp_path / "d.jsonl"))
    zones = list(ZONES)
    for index, animal in enumerate(runner.agents):
        animal.position = zones[index % len(zones)]
    snapshot = ZoneSnapshot(runner.agents)
    for zone in ZONES:
        expected = [a for a in runner.agents if a.position == zone or a.position in ADJACENT_ZONES[zone]]
        assert snapshot.near(zone) == expected


def test_an_alarm_given_during_a_tick_is_heard_on_the_next(tmp_path) -> None:
    runner = _colony(5, 2, str(tmp_path / "d.jsonl"))
    caller, listener = runner.agents
    caller.position = listener.position = "floor"
    caller.is_sleeping = listener.is_sleeping = False
    snapshot = ZoneSnapshot(runner.agents)  # taken before the call starts
    caller._apply_affect_impulse(stress=0.9, intensity=1.0)
    caller.sim_time += 0.1
    assert caller._is_emitting_alarm()
    listener._zone_snapshot = snapshot
    assert listener._audible_alarm_calls() == []
    listener._zone_snapshot = ZoneSnapshot(runner.agents)  # the next tick's snapshot
    assert [call[0] for call in listener._audible_alarm_calls()] == [caller]
    listener._zone_snapshot = None


def test_turn_order_uses_the_colony_generator_not_the_module_one(tmp_path) -> None:
    left = _colony(11, 6, str(tmp_path / "a.jsonl"))
    right = _colony(11, 6, str(tmp_path / "b.jsonl"))
    random.seed(999)  # the module-level generator differs; the turn order must not
    order_left = [a.agent_id for a in left._turn_order(ZoneSnapshot(left.agents))]
    random.seed(12345)
    order_right = [a.agent_id for a in right._turn_order(ZoneSnapshot(right.agents))]
    assert order_left == order_right


def test_animal_at_a_contested_resource_steps_first(tmp_path) -> None:
    runner = _colony(13, 4, str(tmp_path / "d.jsonl"))
    for animal in runner.agents:
        animal.position = "floor"
    runner.agents[2].position = "bowl_pellets"
    order = runner._turn_order(ZoneSnapshot(runner.agents))
    assert order[0] is runner.agents[2]


def test_same_seed_same_trajectory(tmp_path, monkeypatch) -> None:
    # The core reads the wall clock (affect decay), so on a loaded machine two runs drift apart; tie it to the
    # simulated time, then the two runs must match exactly.
    clock = [1_700_000_000.0]
    monkeypatch.setattr(time, "time", lambda: clock[0])
    runs = []
    for name in ("a", "b"):
        clock[0] = 1_700_000_000.0
        runner = _colony(7, 6, str(tmp_path / f"{name}.jsonl"))
        rows = []
        for _ in range(150):
            clock[0] += SimulationRunner.SIM_DT
            runner.tick(SimulationRunner.SIM_DT)
            rows.append(tuple((a.agent_id, a.position, a.current_action, a.stress) for a in runner.agents))
        runs.append(rows)
    assert runs[0] == runs[1]


def test_snapshot_is_cleared_after_the_tick(tmp_path) -> None:
    runner = _colony(9, 3, str(tmp_path / "d.jsonl"))
    runner.tick(SimulationRunner.SIM_DT)
    assert all(animal._zone_snapshot is None for animal in runner.agents)


_REPEAT_RUN = """
import hashlib, random, sys, time
clock = [1_700_000_000.0]
time.time = lambda: clock[0]  # the core reads the wall clock; here it follows the simulated time
from colony_agent import ChinchillaAgent
from simulation_runner import SimulationRunner
random.seed(21)
runner = SimulationRunner(death_journal_path=sys.argv[1], seed=21)
for index in range(5):
    runner.add_agent(ChinchillaAgent(sex="F" if index % 2 == 0 else "M", name=f"r{index}",
                                     agent_id=f"issue28-r{index}", rng_seed=2100 + index))
digest = hashlib.sha256()
for _ in range(300):
    clock[0] += SimulationRunner.SIM_DT
    runner.tick(SimulationRunner.SIM_DT)
    for a in runner.agents:
        digest.update(f"{a.agent_id}|{a.position}|{a.current_action}|{a.stress:.9f};".encode())
print(digest.hexdigest())
"""


def test_seeded_run_repeats_in_other_processes(tmp_path) -> None:
    """Same seed, two processes with different hash seeds: the same trajectory, stress included.

    The clock is tied to the simulated time because the core reads the wall clock. Before this change the walk
    picked neighbours from sets, so the trajectory depended on PYTHONHASHSEED.
    """
    import os
    import subprocess
    import sys

    digests = []
    for hash_seed in ("0", "7"):
        env = dict(os.environ, PYTHONHASHSEED=hash_seed, PYTHONPATH=os.pathsep.join(sys.path))
        done = subprocess.run(
            [sys.executable, "-c", _REPEAT_RUN, str(tmp_path / f"d{hash_seed}.jsonl")],
            env=env, capture_output=True, text=True, timeout=600, check=True,
        )
        digests.append(done.stdout.strip().splitlines()[-1])
    assert digests[0] == digests[1]


def test_perception_does_not_depend_on_turn_order(tmp_path, monkeypatch) -> None:
    """Two identical colonies step in opposite orders: every animal sees the same animals in the same zones.

    The category may still differ: a social offer made earlier in the tick lets the target know the initiator at once
    (offers are resolved in the initiator's step), so "unknown_nearby" can become "nearby". Without the snapshot the
    zones themselves differed for every animal.
    """
    clock = [1_700_000_000.0]
    monkeypatch.setattr(time, "time", lambda: clock[0])
    seen = []
    for name, flip in (("fwd", False), ("rev", True)):
        clock[0] = 1_700_000_000.0
        runner = _colony(17, 8, str(tmp_path / f"{name}.jsonl"))
        for index, animal in enumerate(runner.agents):
            animal.position = ("floor", "house", "bowl_pellets", "corner")[index % 4]
        order = list(runner.agents)
        monkeypatch.setattr(runner, "_turn_order", lambda snapshot, o=order, f=flip: o[::-1] if f else o)
        clock[0] += SimulationRunner.SIM_DT
        runner.tick(SimulationRunner.SIM_DT)
        seen.append({
            a.agent_id: sorted((p.agent_id, p.public_state.position) for p in a.perceived_others)
            for a in runner.agents
        })
    assert seen[0] == seen[1]


def test_alarm_moves_one_zone_per_tick_whatever_the_turn_order(tmp_path) -> None:
    """A relayed alarm on the chain door - bars - litter moves one zone per tick.

    The relay on the bars is scared during tick 1, as when it hears a caller on the door; its call opens from that
    rise. The listener in the litter hears it in tick 2, whether it reads before or after the relay in tick 1. Without
    the snapshot the order decided it: a listener reading after the relay heard it in the same tick.
    """
    for listener_last in (True, False):
        runner = _colony(23, 2, str(tmp_path / f"c{listener_last}.jsonl"))
        relay, listener = runner.agents
        for animal, zone in ((relay, "bars"), (listener, "litter")):
            animal.position = zone
            animal.is_sleeping = False
            animal.sim_time = 10.0
            animal._anchor_alarm_stress()
        heard = []
        for tick in (1, 2):
            snapshot = ZoneSnapshot(runner.agents)
            for animal in ([relay, listener] if listener_last else [listener, relay]):
                animal._zone_snapshot = snapshot
                if animal is relay and tick == 1:
                    animal._apply_affect_impulse(stress=0.9, intensity=1.0)
                    assert animal._is_emitting_alarm()
                if animal is listener:
                    animal._perceive_alarm_calls()
                    heard.append((tick, animal._alarm_heard_this_tick))
                animal._zone_snapshot = None
            for animal in runner.agents:
                animal.sim_time += SimulationRunner.SIM_DT
        assert heard == [(1, False), (2, True)], (listener_last, heard)
