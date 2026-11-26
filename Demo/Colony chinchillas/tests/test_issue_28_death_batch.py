"""Issue #28: the deaths of one tick are recorded in one pass.

The generation index map is built once per tick and the death registry is written once, instead of a map rebuild
and a full registry rewrite per death. The memorials must be the same as handling the deaths one by one, where each
death is indexed among the agents still alive at that point.
"""

from __future__ import annotations

import json

from colony_agent import ChinchillaAgent
from simulation_runner import SimulationRunner

# (agent id, generation); ids are chosen so that the deaths below shift positions inside generation 1
COLONY = (("g1-a", 1), ("g1-b", 1), ("g1-c", 1), ("g1-d", 1), ("g2-a", 2), ("g2-b", 2))
DEATHS = ("g1-b", "g1-d", "g2-a", "g1-a")


def _runner(tmp_path):
    runner = SimulationRunner(death_journal_path=str(tmp_path / "deaths.jsonl"))
    for index, (agent_id, generation) in enumerate(COLONY):
        agent = ChinchillaAgent(sex="F" if index % 2 == 0 else "M", rng_seed=index + 1)
        agent.agent_id = agent_id
        agent.generation = generation
        runner.add_agent(agent)
    return runner


def _one_by_one_indexes(colony, deaths):
    """The indexes the per-death map rebuild gave: 1-based position by id inside the generation, among the living."""
    alive = dict(colony)
    out = {}
    for agent_id in deaths:
        same = sorted(other for other, generation in alive.items() if generation == alive[agent_id])
        out[agent_id] = same.index(agent_id) + 1
        del alive[agent_id]
    return out


def test_batched_deaths_give_the_same_generation_indexes(tmp_path):
    runner = _runner(tmp_path)
    runner._handle_agent_deaths(list(DEATHS))
    expected = _one_by_one_indexes(COLONY, DEATHS)
    got = {agent_id: runner.death_registry.get_memorial(agent_id).generation_index for agent_id in DEATHS}
    assert got == expected == {"g1-b": 2, "g1-d": 3, "g2-a": 1, "g1-a": 1}
    assert sorted(agent.agent_id for agent in runner.agents) == ["g1-c", "g2-b"]
    assert runner.total_deaths == len(DEATHS)


def test_registry_is_written_once_per_tick(tmp_path, monkeypatch):
    runner = _runner(tmp_path)
    writes = []
    original = runner.death_registry.autosave
    monkeypatch.setattr(runner.death_registry, "autosave", lambda: (writes.append(1), original())[1])
    runner._handle_agent_deaths(list(DEATHS))
    assert len(writes) == 1
    journal = (tmp_path / "deaths.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line).get("agent_id") for line in journal] == list(DEATHS)


def test_single_death_path_is_unchanged(tmp_path):
    runner = _runner(tmp_path)
    runner._handle_agent_death("g1-c")
    assert runner.death_registry.get_memorial("g1-c").generation_index == 3
    assert "g1-c" not in {agent.agent_id for agent in runner.agents}


def test_an_id_listed_twice_counts_twice_but_registers_once(tmp_path):
    runner = _runner(tmp_path)
    runner._handle_agent_deaths(["g2-b", "g2-b"])
    assert runner.total_deaths == 2                  # as the one-by-one loop counted it
    assert runner.death_registry.get_memorial("g2-b").generation_index == 2
