from __future__ import annotations

import json
import math
from pathlib import Path

from colony_agent import ChinchillaAgent
from colony_storage import ColonyStorage
from genome import GenomeVector
from simulation_runner import SimulationRunner


def _find_agent(agents: list[ChinchillaAgent], agent_id: str) -> ChinchillaAgent:
    for agent in agents:
        if agent.agent_id == agent_id:
            return agent
    raise AssertionError(f"Agent not found: {agent_id}")


def test_storage_roundtrip_preserves_runner_and_links(tmp_path: Path) -> None:
    runner = SimulationRunner()
    a0 = ChinchillaAgent(sex="F", position="floor")
    a1 = ChinchillaAgent(sex="M", position="floor")
    runner.add_agent(a0)
    runner.add_agent(a1)
    runner.run_for(15.0, dt=1.0)
    a0._try_acquire_resource("wheel")
    runner._refill_enabled = False

    storage = ColonyStorage(save_dir=tmp_path)
    saved_path = storage.save_colony(runner, "roundtrip.json")
    loaded = storage.load_colony(saved_path)

    assert len(loaded.agents) == 2
    assert loaded.sim_time == runner.sim_time
    assert loaded._refill_enabled is False
    assert loaded.resources.wheel_lock == runner.resources.wheel_lock

    loaded_ids = {agent.agent_id for agent in loaded.agents}
    expected_ids = {a0.agent_id, a1.agent_id}
    assert loaded_ids == expected_ids

    for agent in loaded.agents:
        assert agent.resources is loaded.resources
        assert agent.colony is loaded.agents
        assert hasattr(agent, "hippocampus")
        assert not hasattr(agent, "affect")


def test_storage_preserves_pending_offspring(tmp_path: Path) -> None:
    runner = SimulationRunner()
    mother = ChinchillaAgent(sex="F", is_mature=True, position="house")
    father = ChinchillaAgent(sex="M", is_mature=True, position="house")
    runner.add_agent(mother)
    runner.add_agent(father)

    offspring = ChinchillaAgent(
        sex="F",
        age=0.0,
        generation=1,
        parents=(mother.agent_id, father.agent_id),
        is_mature=False,
    )
    mother.pending_offspring_list.append(offspring)

    storage = ColonyStorage(save_dir=tmp_path)
    saved_path = storage.save_colony(runner, "pending.json")
    loaded = storage.load_colony(saved_path)

    loaded_mother = _find_agent(loaded.agents, mother.agent_id)
    assert len(loaded_mother.pending_offspring_list) == 1
    loaded_child = loaded_mother.pending_offspring_list[0]
    assert loaded_child.parents[0] == loaded_mother.agent_id
    assert loaded_child.resources is loaded.resources
    assert loaded_child.colony is loaded.agents


def test_storage_list_and_delete(tmp_path: Path) -> None:
    runner = SimulationRunner()
    runner.add_agent(ChinchillaAgent(sex="F"))

    storage = ColonyStorage(save_dir=tmp_path)
    storage.save_colony(runner, "first.json")
    storage.save_colony(runner, "second.json")

    names = {item["name"] for item in storage.get_save_files()}
    assert {"first.json", "second.json"}.issubset(names)

    deleted = storage.delete_save("first.json")
    assert deleted is True
    names_after = {item["name"] for item in storage.get_save_files()}
    assert "first.json" not in names_after


def test_storage_preserves_extended_death_log_fields(tmp_path: Path) -> None:
    runner = SimulationRunner()
    runner._death_log = [
        {
            "agent_id": "a-1",
            "sim_time": 12.5,
            "cause_of_death": "exhaustion",
            "recorded_at_utc": "2026-04-07T12:00:00+00:00",
            "energy": 0.01,
        }
    ]
    storage = ColonyStorage(save_dir=tmp_path)
    saved_path = storage.save_colony(runner, "deathlog.json")

    loaded = storage.load_colony(saved_path)
    assert loaded._death_log
    entry = loaded._death_log[0]
    assert entry["agent_id"] == "a-1"
    assert entry["sim_time"] == 12.5
    assert entry["cause_of_death"] == "exhaustion"
    assert entry["recorded_at_utc"] == "2026-04-07T12:00:00+00:00"
    assert entry["energy"] == 0.01

def _close(actual: float, expected: float) -> None:
    assert math.isclose(float(actual), float(expected), rel_tol=0.0, abs_tol=1e-6)


def _genome_with(**overrides: float) -> GenomeVector:
    genes = dict(GenomeVector.default().genes)
    genes.update(overrides)
    return GenomeVector(genes=genes, generation=2, lineage_id="line-65")


def test_storage_roundtrip_keeps_genome_temperament_and_lineage(tmp_path: Path) -> None:
    genome = _genome_with(
        af_decay_stress=0.88,
        af_lambda_reg=0.09,
        dr_social_drive_baseline=0.40,
        dr_social_threshold=0.62,
        nm_decay_half_life=150.0,
    )
    agent = ChinchillaAgent(
        sex="F",
        name="Mira",
        age=120.0,
        generation=2,
        genome=genome,
        is_mature=True,
    )
    agent.energy = 0.37
    agent.social_drive = 0.15
    agent.neuromodulators.dopamine = 0.61
    agent.neuromodulators.cortisol = 0.44
    agent.genome_inheritance_meta = {
        "mode": "recombined",
        "mother_id": "mom-1",
        "father_id": "dad-1",
        "mother_name": "Ada",
        "father_name": "Lin",
        "lineage_id": "line-65",
        "crossover_mode": "uniform",
        "mutation_rate": 0.05,
        "top_shifted_genes": [{"gene": "af_decay_stress", "midpoint_shift": 0.04}],
    }

    runner = SimulationRunner()
    runner.add_agent(agent)
    storage = ColonyStorage(save_dir=tmp_path)
    loaded = storage.load_colony(storage.save_colony(runner, "genome.json"))
    restored = loaded.agents[0]

    _close(restored.affective_space.axis_decay["stress"], 0.88)
    _close(restored.affective_space.lambda_reg, 0.09)
    _close(restored.neuromodulators.DECAY_HALF_LIFE, 150.0)
    _close(restored.autonomous_runtime.hard_limits.drive_thresholds["social_drive"], 0.62)
    _close(restored.social_drive, 0.15)
    _close(restored.energy, 0.37)
    _close(restored.neuromodulators.dopamine, 0.61)
    _close(restored.neuromodulators.cortisol, 0.44)
    assert restored.genome_inheritance_meta["mode"] == "recombined"
    assert restored.genome_inheritance_meta["crossover_mode"] == "uniform"
    assert restored.genome_inheritance_meta["mother_id"] == "mom-1"
    assert restored.genome_inheritance_meta["father_name"] == "Lin"
    assert restored.genome_inheritance_meta["top_shifted_genes"] == [
        {"gene": "af_decay_stress", "midpoint_shift": 0.04}
    ]


def test_storage_old_save_without_new_fields_reapplies_genome(tmp_path: Path) -> None:
    genome = _genome_with(af_decay_stress=0.88, dr_social_drive_baseline=0.40)
    agent = ChinchillaAgent(sex="M", name="Old", genome=genome, is_mature=True)
    agent.energy = 0.42
    agent.social_drive = 0.31

    runner = SimulationRunner()
    runner.add_agent(agent)
    storage = ColonyStorage(save_dir=tmp_path)
    path = Path(storage.save_colony(runner, "legacy.json"))
    payload = json.loads(path.read_text(encoding="utf-8"))
    saved_agent = payload["agents"][0]
    saved_agent.pop("genome_inheritance_meta", None)
    saved_agent["runtime"].pop("neuromodulator_levels", None)
    path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = storage.load_colony(path)
    restored = loaded.agents[0]
    _close(restored.affective_space.axis_decay["stress"], 0.88)
    _close(restored.social_drive, 0.31)
    _close(restored.energy, 0.42)
    assert restored.genome_inheritance_meta == {}
    assert restored.genome is not None


def test_storage_old_save_without_genome_loads(tmp_path: Path) -> None:
    agent = ChinchillaAgent(sex="F", name="Plain", is_mature=False)
    agent.energy = 0.58

    runner = SimulationRunner()
    runner.add_agent(agent)
    storage = ColonyStorage(save_dir=tmp_path)
    path = Path(storage.save_colony(runner, "nogenome.json"))
    payload = json.loads(path.read_text(encoding="utf-8"))
    saved_agent = payload["agents"][0]
    saved_agent.pop("genome", None)
    saved_agent.pop("genome_inheritance_meta", None)
    saved_agent["runtime"].pop("neuromodulator_levels", None)
    path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = storage.load_colony(path)
    restored = loaded.agents[0]
    assert restored.genome is None
    assert restored.genome_inheritance_meta == {}
    _close(restored.affective_space.axis_decay["stress"], 0.75)
    _close(restored.energy, 0.58)
