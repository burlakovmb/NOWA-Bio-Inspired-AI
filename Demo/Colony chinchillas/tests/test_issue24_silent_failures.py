"""Regressions for silent colony failures (issue 24)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from colony_agent import ChinchillaAgent, _colony_max_lifespan_age_s
from colony_storage import ColonyStorage
from genome import GENE_REGISTRY, GenomeVector
from simulation_runner import SimulationRunner
import swarm as swarm_module


def _genome(lineage: str, **overrides: float) -> GenomeVector:
    genes = {key: descriptor.default for key, descriptor in GENE_REGISTRY.items()}
    genes.update(overrides)
    return GenomeVector(genes=genes, generation=0, lineage_id=lineage)


def _identity_mutate(self, rate=0.05, sigma_scale=1.0, rng=None):
    del rate, sigma_scale, rng
    return self


def test_dead_father_still_contributes_conception_genome(monkeypatch) -> None:
    mother_genome = _genome("mother", lt_max_lifespan_factor=0.5, wk_accumulation_factor=0.5)
    father_genome = _genome("father", lt_max_lifespan_factor=2.0, wk_accumulation_factor=2.0)
    mother = ChinchillaAgent(
        sex="F",
        is_mature=True,
        genome=mother_genome,
        generation=2,
        rng_seed=1,
    )
    father = ChinchillaAgent(
        sex="M",
        is_mature=True,
        genome=father_genome,
        generation=5,
        rng_seed=2,
    )
    mother.colony = [mother, father]
    father.colony = [mother, father]

    mother._start_pregnancy(father.agent_id)

    assert mother._conception_father_genome is not None
    assert mother._conception_father_genome is not father.genome
    assert mother._conception_father_genome.genes["lt_max_lifespan_factor"] == pytest.approx(2.0)

    # The father dies and his live genome is gone before parturition.
    father.genome = mother_genome
    mother.colony = [mother]
    monkeypatch.setattr(GenomeVector, "mutate", _identity_mutate)

    mother._give_birth()

    assert mother.pending_offspring_list
    assert mother._conception_father_genome is None
    for child in mother.pending_offspring_list:
        assert child.genome is not None
        assert child.parents == (mother.agent_id, father.agent_id)
        assert child.generation == 6
        assert child.genome_inheritance_meta["mode"] == "recombined"
        assert child.genome_inheritance_meta["mother_id"] == mother.agent_id
        assert child.genome_inheritance_meta["father_id"] == father.agent_id
        assert child.genome.genes["lt_max_lifespan_factor"] == pytest.approx(1.25)
        assert child.genome.genes["wk_accumulation_factor"] == pytest.approx(1.25)
        assert child.genome.distance(mother_genome) > 0.0
        assert child.genome.distance(father_genome) > 0.0


def test_birth_without_any_genome_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    mother = ChinchillaAgent(sex="F", is_mature=True, rng_seed=3)
    mother.colony = [mother]
    mother.is_pregnant = True
    mother._current_mate_id = "father-already-gone"

    with caplog.at_level(logging.WARNING, logger="colony_agent"):
        mother._give_birth()

    assert mother.pending_offspring_list
    assert "without a recombined genome" in caplog.text
    for child in mother.pending_offspring_list:
        assert child.genome is None
        assert child.parents[1] == "father-already-gone"


def test_mortality_exception_is_logged_and_does_not_grant_immortality(
    caplog: pytest.LogCaptureFixture,
) -> None:
    agent = ChinchillaAgent(sex="M", is_mature=True, age=5.0, rng_seed=4)
    agent.energy = 0.9
    agent.wakefulness.wakefulness = 0.2
    real_update = agent.mortality_system.update
    calls = {"n": 0}

    def flaky(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("mortality sensor glitch")
        return real_update(**kwargs)

    agent.mortality_system.update = flaky

    with caplog.at_level(logging.WARNING, logger="colony_agent"):
        agent._age_step(1.0)

    assert calls["n"] == 1
    assert agent.mortality_system.is_dead() is False
    assert "mortality update failed" in caplog.text

    agent.energy = 0.0
    agent._age_step(1.0)

    assert agent.mortality_system.is_dead() is True
    assert agent.mortality_system.cause_of_death == "exhaustion"
    assert agent.current_action == "dead"


def test_lethal_state_still_kills_when_mortality_update_raises(
    caplog: pytest.LogCaptureFixture,
) -> None:
    agent = ChinchillaAgent(sex="F", is_mature=True, age=5.0, rng_seed=5)
    agent.energy = 0.0
    agent.wakefulness.wakefulness = 0.2

    def boom(**kwargs):
        raise RuntimeError("mortality broke")

    agent.mortality_system.update = boom

    with caplog.at_level(logging.WARNING, logger="colony_agent"):
        agent._age_step(1.0)

    assert "mortality update failed" in caplog.text
    assert agent.mortality_system.is_dead() is True
    assert agent.mortality_system.cause_of_death == "exhaustion"
    assert agent.current_action == "dead"


def test_add_agent_over_population_limit_creates_no_duplicates(monkeypatch) -> None:
    monkeypatch.setattr(swarm_module, "MAX_POPULATION_SIZE", 1)
    runner = SimulationRunner()
    first = ChinchillaAgent(sex="F", rng_seed=6)
    second = ChinchillaAgent(sex="M", rng_seed=7)
    runner.add_agent(first)

    with pytest.raises(ValueError, match="Population limit"):
        runner.add_agent(second)

    assert [agent.agent_id for agent in runner.agents] == [first.agent_id]
    swarm_ids = [agent.agent_id for agent in runner.swarm.get_all_agents()]
    assert swarm_ids == [first.agent_id]
    assert second.agent_id not in swarm_ids


def test_spawn_at_population_limit_does_not_duplicate_offspring(
    monkeypatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(swarm_module, "MAX_POPULATION_SIZE", 1)
    runner = SimulationRunner()
    mother = ChinchillaAgent(sex="F", is_mature=True, rng_seed=8)
    runner.add_agent(mother)
    child = ChinchillaAgent(sex="M", is_mature=False, generation=1, rng_seed=9)
    mother.pending_offspring_list.append(child)

    with caplog.at_level(logging.WARNING, logger="simulation_runner"):
        runner._spawn_pending_offspring()

    runner_ids = [agent.agent_id for agent in runner.agents]
    swarm_ids = [agent.agent_id for agent in runner.swarm.get_all_agents()]
    assert runner_ids == [mother.agent_id]
    assert swarm_ids == [mother.agent_id]
    assert len(runner_ids) == len(set(runner_ids))
    assert len(swarm_ids) == len(set(swarm_ids))
    assert child.agent_id not in runner_ids
    assert child.agent_id not in swarm_ids
    assert "was not admitted" in caplog.text
    assert runner.births_this_step == 0
    assert runner.total_births == 0


def test_placement_failure_rolls_back_before_the_colony_list_changes(monkeypatch) -> None:
    runner = SimulationRunner()
    agent = ChinchillaAgent(sex="F", rng_seed=10)

    def boom(_preferred):
        raise RuntimeError("Unable to place agent without collisions")

    monkeypatch.setattr(runner.swarm._swarm, "_find_free_position", boom)

    with pytest.raises(RuntimeError, match="Unable to place"):
        runner.add_agent(agent)

    assert runner.agents == []
    assert runner.swarm.get_all_agents() == []


def test_save_load_keeps_genome_cap_and_conception_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mother_genome = _genome("mother", lt_max_lifespan_factor=0.5)
    father_genome = _genome("father", lt_max_lifespan_factor=2.0)
    mother = ChinchillaAgent(
        sex="F",
        is_mature=True,
        genome=mother_genome,
        generation=2,
        rng_seed=11,
        name="mother-save",
    )
    father = ChinchillaAgent(
        sex="M",
        is_mature=True,
        genome=father_genome,
        generation=5,
        rng_seed=12,
        name="father-save",
    )
    mother.colony = [mother, father]
    mother._start_pregnancy(father.agent_id)
    mother.gestation_timer = 40.0

    runner = SimulationRunner()
    runner.add_agent(mother)
    storage = ColonyStorage(save_dir=tmp_path)
    loaded = storage.load_colony(storage.save_colony(runner, "pregnancy.json"))

    assert len(loaded.agents) == 1
    restored = loaded.agents[0]
    assert restored.is_pregnant is True
    assert restored.gestation_timer == pytest.approx(40.0)
    assert restored.genome is not None
    assert restored._conception_father_genome is not None
    assert restored.genome.genes["lt_max_lifespan_factor"] == pytest.approx(0.5)
    assert restored._conception_father_genome.genes["lt_max_lifespan_factor"] == pytest.approx(2.0)
    assert restored._conception_father_id == father.agent_id
    assert restored._conception_father_name == father.name
    assert restored._conception_father_generation == 5
    assert restored.mortality_system.max_lifespan_age_s == pytest.approx(
        _colony_max_lifespan_age_s(restored.genome)
    )
    assert restored.mortality_system.max_lifespan_age_s == pytest.approx(
        mother.mortality_system.max_lifespan_age_s
    )

    monkeypatch.setattr(GenomeVector, "mutate", _identity_mutate)
    restored._give_birth()

    assert restored.pending_offspring_list
    child = restored.pending_offspring_list[0]
    assert child.genome is not None
    assert child.parents[1] == father.agent_id
    assert child.generation == 6
    assert child.genome.genes["lt_max_lifespan_factor"] == pytest.approx(1.25)
    assert child.genome_inheritance_meta["mode"] == "recombined"
    assert child.mortality_system.max_lifespan_age_s == pytest.approx(
        _colony_max_lifespan_age_s(child.genome)
    )


def test_old_save_without_genome_fields_loads(tmp_path: Path) -> None:
    runner = SimulationRunner()
    agent = ChinchillaAgent(
        sex="F",
        is_mature=True,
        genome=_genome("stripped", lt_max_lifespan_factor=2.0),
        rng_seed=13,
    )
    runner.add_agent(agent)
    storage = ColonyStorage(save_dir=tmp_path)
    path = Path(storage.save_colony(runner, "legacy.json"))
    payload = json.loads(path.read_text(encoding="utf-8"))
    for item in payload["agents"]:
        item.pop("genome", None)
        reproduction = item.get("reproduction", {})
        for key in (
            "conception_father_genome",
            "conception_father_id",
            "conception_father_name",
            "conception_father_generation",
        ):
            reproduction.pop(key, None)
    path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = storage.load_colony(path)
    restored = loaded.agents[0]
    assert restored.agent_id == agent.agent_id
    assert restored.genome is None
    assert restored._conception_father_genome is None
    assert restored._conception_father_id is None
    assert restored._conception_father_generation == 0
    assert restored.mortality_system.max_lifespan_age_s == pytest.approx(
        _colony_max_lifespan_age_s(None)
    )


def test_reproductive_update_failure_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    agent = ChinchillaAgent(sex="F", is_mature=True, age=20.0, rng_seed=14)
    agent.reproductive_system.reproductive_drive = 0.4
    agent.energy = 0.8
    agent.lived_steps = 20

    def boom(**_kwargs):
        raise RuntimeError("reproductive broke")

    agent.reproductive_system.update = boom
    with caplog.at_level(logging.WARNING, logger="colony_agent"):
        agent._age_step(1.0)

    assert "reproductive update failed" in caplog.text
    assert agent.reproductive_system.reproductive_drive == pytest.approx(0.4)
    assert agent.mortality_system.is_dead() is False


def test_reproductive_update_still_runs_when_it_succeeds() -> None:
    agent = ChinchillaAgent(sex="M", is_mature=True, age=20.0, rng_seed=15)
    agent.reproductive_system.reproductive_drive = 0.4
    agent.lived_steps = 10
    agent.energy = 0.8

    agent._age_step(1.0)

    assert agent.reproductive_system.reproductive_drive == pytest.approx(0.0)
