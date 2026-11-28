"""K01: with physiology owned by the policy, a constant rest colony loses.

The historical body still feeds and breeds when the core is replaced, so the
check turns PHYSIOLOGY_AS_POLICY on. Seeded RNGs only; no PYTHONHASHSEED.
"""

from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path

COLONY_SRC = Path(__file__).resolve().parents[1] / "Demo" / "Colony chinchillas" / "src"
if str(COLONY_SRC) not in sys.path:
    sys.path.insert(0, str(COLONY_SRC))

from agent_knowledge import KnownAgent  # noqa: E402
from colony_agent import ChinchillaAgent  # noqa: E402
from colony_storage import ColonyStorage  # noqa: E402
from config_colony import ESTRUS_DURATION_S, HEAT_CYCLE_LENGTH_S, MATURITY_AGE_S  # noqa: E402
from shared_resources import SharedResources  # noqa: E402
from simulation_runner import SimulationRunner  # noqa: E402

_NAME = re.compile(r"^G[0-9]+A[0-9]+S[MFU]$")
_SURVIVAL_STEPS = 30
_REPRO_STEPS = 40
# A held action occupies the first bouts, so courtship lands later than one offer per tick.
_CORE_REPRO_STEPS = 160


def _episode_after_bout(agent: ChinchillaAgent, *, dt: float = 0.1, limit_s: float = 180.0):
    spent = 0.0
    while not agent.hippocampus.experiences and spent < limit_s:
        if agent.mortality_system.is_dead():
            break
        agent.sim_step(dt)
        spent += dt
    assert agent.hippocampus.experiences, "the bout did not commit an episode"
    return agent.hippocampus.experiences[-1]


def _survival_agent(seed: int, policy: str | None) -> ChinchillaAgent:
    random.seed(seed)
    agent = ChinchillaAgent(
        sex="F",
        name="Luna",
        rng_seed=seed,
        physiology_as_policy=True,
        age=MATURITY_AGE_S,
        is_mature=True,
    )
    agent.replaced_policy_action = policy
    agent.hunger = 0.8
    agent.thirst = 0.75
    agent.wakefulness.wakefulness = 0.2
    agent.energy = 1.0
    agent.resources = SharedResources()
    agent.colony = [agent]
    return agent


def _run_until(agent: ChinchillaAgent, steps: int, dt: float = 1.0) -> int:
    for index in range(steps):
        if agent.mortality_system.is_dead():
            return index
        agent.sim_step(dt)
    return steps


def _link(left: ChinchillaAgent, right: ChinchillaAgent) -> None:
    left.knowledge[right.agent_id] = KnownAgent(
        agent_id=right.agent_id,
        name=right.name,
        sex=right.sex,
        last_seen_position=right.position,
        last_seen_time=0.0,
        familiarity=0.6,
        affinity=0.5,
        relationship_type="acquaintance",
    )
    right.knowledge[left.agent_id] = KnownAgent(
        agent_id=left.agent_id,
        name=left.name,
        sex=left.sex,
        last_seen_position=left.position,
        last_seen_time=0.0,
        familiarity=0.6,
        affinity=0.5,
        relationship_type="acquaintance",
    )


def _pair(seed: int, policy: str | None) -> tuple[ChinchillaAgent, ChinchillaAgent]:
    random.seed(seed)
    resources = SharedResources()
    female = ChinchillaAgent(
        sex="F",
        name="Luna",
        rng_seed=seed,
        physiology_as_policy=True,
        age=MATURITY_AGE_S + 10.0,
        is_mature=True,
        position="floor",
    )
    male = ChinchillaAgent(
        sex="M",
        name="Milo",
        rng_seed=seed + 1,
        physiology_as_policy=True,
        age=MATURITY_AGE_S + 10.0,
        is_mature=True,
        position="floor",
    )
    for agent in (female, male):
        agent.replaced_policy_action = policy
        agent.hunger = 0.2
        agent.thirst = 0.2
        agent.wakefulness.wakefulness = 0.1
        agent.energy = 1.0
        agent.resources = resources
        agent.social_drive = 0.9
        agent.lived_steps = 200
        agent.reproductive_system.reproductive_drive = 0.9
    female.colony = [female, male]
    male.colony = [female, male]
    female.heat_cycle._elapsed = HEAT_CYCLE_LENGTH_S - ESTRUS_DURATION_S + 5.0
    female.heat_cycle.update(0.0)
    _link(female, male)
    return female, male


def test_policy_flag_defaults_on_and_context_includes_need_bins() -> None:
    agent = ChinchillaAgent(sex="F", name="Luna")
    assert agent.physiology_as_policy is True
    events = agent._build_context_events()
    assert any(event.startswith("hunger_bin:") for event in events)
    assert any(event.startswith("thirst_bin:") for event in events)
    assert any(event.startswith("wake_bin:") for event in events)


def test_policy_flag_off_keeps_historical_context_and_forces_sleep() -> None:
    agent = ChinchillaAgent(sex="M", name="Milo", physiology_as_policy=False)
    agent.colony = [agent]
    agent.resources = SharedResources()
    events = agent._build_context_events()
    assert agent.physiology_as_policy is False
    assert not any(event.startswith("hunger_bin:") for event in events)
    agent.wakefulness.wakefulness = 0.85
    before = float(agent.wakefulness.wakefulness)
    agent.sim_step(0.1)
    assert agent.is_sleeping is True
    assert float(agent.wakefulness.wakefulness) < before


def test_physiology_flag_is_saved_loaded_and_inherited(tmp_path: Path) -> None:
    runner = SimulationRunner(death_journal_path=tmp_path / "deaths.jsonl")
    gated = ChinchillaAgent(sex="F", name="Luna", physiology_as_policy=False)
    policy = ChinchillaAgent(sex="M", name="Milo", physiology_as_policy=True)
    runner.add_agent(gated)
    runner.add_agent(policy)

    storage = ColonyStorage(save_dir=tmp_path)
    saved_path = Path(storage.save_colony(runner, "flags.json"))
    loaded = storage.load_colony(saved_path)
    by_id = {agent.agent_id: agent for agent in loaded.agents}
    assert by_id[gated.agent_id].physiology_as_policy is False
    assert by_id[policy.agent_id].physiology_as_policy is True

    payload = json.loads(saved_path.read_text(encoding="utf-8"))
    for row in payload["agents"]:
        assert "physiology_as_policy" in row["runtime"]
        row["runtime"].pop("physiology_as_policy")
    legacy_path = tmp_path / "legacy.json"
    legacy_path.write_text(json.dumps(payload), encoding="utf-8")
    legacy = storage.load_colony(legacy_path)
    assert all(agent.physiology_as_policy is True for agent in legacy.agents)

    gated.is_mature = True
    gated._current_mate_id = policy.agent_id
    child = gated._create_offspring(policy)
    assert child.physiology_as_policy is False
    policy_child = policy._create_offspring(None)
    assert policy_child.physiology_as_policy is True


def test_policy_mode_does_not_force_eat_and_still_reports_reflexes() -> None:
    resting = ChinchillaAgent(sex="M", name="Milo", rng_seed=3, physiology_as_policy=True)
    resting.replaced_policy_action = "rest"
    resting.colony = [resting]
    resting.resources = SharedResources()
    resting.hunger = 0.95
    resting.thirst = 0.1
    resting.wakefulness.wakefulness = 0.1
    resting.sim_step(0.1)
    assert resting.current_action == "rest"

    alarmed = ChinchillaAgent(sex="F", name="Luna", rng_seed=4, physiology_as_policy=True)
    alarmed.replaced_policy_action = "rest"
    alarmed.colony = [alarmed]
    alarmed.resources = SharedResources()
    alarmed.affective_space.axes["stress"] = 0.95
    alarmed.sim_step(0.1)
    assert alarmed.current_action == "hide"
    episode = _episode_after_bout(alarmed)
    assert bool(getattr(episode, "overridden", False)) is True
    assert str(getattr(episode, "override_source", "")).startswith("reflex:")


def test_rest_policy_loses_survival_and_reproduction_to_the_core() -> None:
    core = _survival_agent(7, None)
    rest = _survival_agent(7, "rest")
    core_steps = _run_until(core, _SURVIVAL_STEPS)
    rest_steps = _run_until(rest, _SURVIVAL_STEPS)

    assert core.mortality_system.is_dead() is False
    assert core_steps == _SURVIVAL_STEPS
    assert rest.mortality_system.is_dead() is True
    assert rest.mortality_system.cause_of_death == "exhaustion"
    assert rest_steps < _SURVIVAL_STEPS
    assert rest.sim_time < core.sim_time
    assert core.energy > 0.5
    assert rest.energy < 0.1

    core_female, core_male = _pair(11, None)
    rest_female, rest_male = _pair(11, "rest")
    core_births = 0
    for step in range(_CORE_REPRO_STEPS):
        if not core_female.pending_offspring_list:
            core_male.sim_step(1.0)
            core_female.sim_step(1.0)
        if step < _REPRO_STEPS:
            rest_male.sim_step(1.0)
            rest_female.sim_step(1.0)
        if core_female.is_pregnant and core_female.gestation_timer > 2.0:
            # Product gestation stays 300s. This only lets the test see a birth.
            core_female.gestation_timer = 1.0
        if core_female.pending_offspring_list and core_births == 0:
            core_births = len(core_female.pending_offspring_list)
    assert core_female.is_pregnant or core_births > 0
    assert rest_female.is_pregnant is False
    assert rest_female.pending_offspring_list == []
    assert core_male.mortality_system.is_dead() is False
    assert core_female.mortality_system.is_dead() is False
    assert rest_male.mortality_system.is_dead() is False
    assert rest_female.mortality_system.is_dead() is False
    assert core_births >= 1
    assert rest_female.sim_time >= float(_REPRO_STEPS) - 1e-6
    for child in core_female.pending_offspring_list:
        assert _NAME.match(child.name)
