"""Issue #79: local habituating fear tone, no stress self-loops in conflict or reward."""

from __future__ import annotations

import json
import math
from pathlib import Path

from agent_knowledge import KnownAgent
from colony_agent import (
    BOWL_CROWD_CONFLICT,
    EAT_RELIEF,
    FEAR_CONTAGION_CONFLICT,
    FEAR_CONTAGION_EXPOSURE_TAU_S,
    FEAR_CONTAGION_FLOOR,
    FEAR_CONTAGION_RECOVERY_TAU_S,
    ChinchillaAgent,
)
from colony_storage import ColonyStorage
from shared_resources import SharedResources
from simulation_runner import SimulationRunner


def _link(observer: ChinchillaAgent, target: ChinchillaAgent) -> None:
    observer.knowledge[target.agent_id] = KnownAgent(
        agent_id=target.agent_id,
        name=target.name,
        sex=target.sex,
        last_seen_position=target.position,
        last_seen_time=observer.sim_time,
        familiarity=0.8,
        affinity=0.3,
        relationship_type="acquaintance",
    )


def _colony(*agents: ChinchillaAgent) -> None:
    group = list(agents)
    for agent in group:
        agent.colony = group
        agent.resources = SharedResources()


def _fearful(agent: ChinchillaAgent, level: float = 0.85) -> None:
    """High tone with the rise window anchored, so this is not a bark."""
    agent.affective_space.axes["stress"] = level
    agent._anchor_alarm_stress()


def _pair(listener_zone: str, other_zone: str) -> tuple[ChinchillaAgent, ChinchillaAgent]:
    listener = ChinchillaAgent(sex="F", position=listener_zone, rng_seed=79, physiology_as_policy=True)
    other = ChinchillaAgent(sex="M", position=other_zone, rng_seed=80, physiology_as_policy=True)
    _colony(listener, other)
    _link(listener, other)
    _fearful(other)
    listener._perceive()
    return listener, other


def test_fearful_tone_conflicts_only_in_the_same_zone() -> None:
    distant, _far = _pair("floor", "door")
    adjacent, _near = _pair("floor", "house")
    contact, _same = _pair("floor", "floor")

    assert distant._compute_conflict() == 0.0
    assert adjacent._compute_conflict() == 0.0
    assert contact._compute_conflict() == FEAR_CONTAGION_CONFLICT

    # A stranger in the same zone is unknown_nearby, not contact. Novelty
    # already carries that cue; conflict does not take it a second time.
    stranger = ChinchillaAgent(sex="M", position="floor", rng_seed=81, physiology_as_policy=True)
    listener = ChinchillaAgent(sex="F", position="floor", rng_seed=82, physiology_as_policy=True)
    _colony(listener, stranger)
    _fearful(stranger)
    listener._perceive()
    assert any(item.category == "unknown_nearby" for item in listener.perceived_others)
    assert listener._compute_novelty() == 0.4
    assert listener._compute_conflict() == 0.0


def test_constant_fearful_neighbour_habituates_with_host_time() -> None:
    total_s = 120.0

    def gain_after(dt: float) -> float:
        listener, _other = _pair("floor", "floor")
        assert listener._compute_conflict(0.0) == FEAR_CONTAGION_CONFLICT
        steps = int(round(total_s / dt))
        conflict = 0.0
        for _ in range(steps):
            conflict = listener._compute_conflict(dt)
        return conflict

    fine = gain_after(0.25)
    coarse = gain_after(1.0)
    expected = FEAR_CONTAGION_CONFLICT * (
        FEAR_CONTAGION_FLOOR
        + (1.0 - FEAR_CONTAGION_FLOOR) * math.exp(-total_s / FEAR_CONTAGION_EXPOSURE_TAU_S)
    )
    assert abs(fine - coarse) < 1e-9
    assert abs(fine - expected) < 1e-8
    assert FEAR_CONTAGION_CONFLICT * FEAR_CONTAGION_FLOOR <= fine < FEAR_CONTAGION_CONFLICT

    listener, other = _pair("floor", "floor")
    for _ in range(int(total_s / 0.25)):
        listener._compute_conflict(0.25)
    faded = listener._fear_contagion[other.agent_id][0]
    other.affective_space.axes["stress"] = 0.1
    other._anchor_alarm_stress()
    listener._perceive()
    assert listener._compute_conflict(0.0) == 0.0
    quiet_s = 120.0
    for _ in range(int(quiet_s / 0.25)):
        listener._compute_conflict(0.25)
    restored = listener._fear_contagion[other.agent_id][0]
    recovered = 1.0 - (1.0 - faded) * math.exp(-quiet_s / FEAR_CONTAGION_RECOVERY_TAU_S)
    assert restored > faded
    assert abs(restored - recovered) < 1e-8
    assert restored <= 1.0

    # A long single step reaches the floor and does not cross it.
    listener, _other = _pair("floor", "floor")
    floored = listener._compute_conflict(10_000.0)
    assert abs(floored - FEAR_CONTAGION_CONFLICT * FEAR_CONTAGION_FLOOR) < 1e-9


def test_stress_alone_does_not_create_conflict() -> None:
    agent = ChinchillaAgent(sex="F", position="floor", rng_seed=83, physiology_as_policy=True)
    agent.colony = [agent]
    agent.affective_space.axes["stress"] = 0.95
    agent.current_action = "idle"
    assert agent.stress > 0.5
    assert agent._compute_conflict() == 0.0


def test_bowl_crowding_counts_extra_eaters_in_that_zone() -> None:
    first = ChinchillaAgent(sex="F", position="bowl_pellets", rng_seed=84, physiology_as_policy=True)
    second = ChinchillaAgent(sex="M", position="bowl_pellets", rng_seed=85, physiology_as_policy=True)
    third = ChinchillaAgent(sex="F", position="bowl_hay", rng_seed=86, physiology_as_policy=True)
    _colony(first, second, third)
    for agent in (first, second, third):
        agent.current_action = "eat"
        agent.affective_space.axes["stress"] = 0.1
    assert first._compute_conflict() == BOWL_CROWD_CONFLICT
    third.position = "bowl_pellets"
    assert first._compute_conflict() == BOWL_CROWD_CONFLICT * 2
    second.current_action = "idle"
    third.current_action = "idle"
    assert first._compute_conflict() == 0.0
    first.position = "floor"
    second.position = "bowl_pellets"
    second.current_action = "eat"
    third.position = "bowl_pellets"
    third.current_action = "eat"
    assert first._compute_conflict() == 0.0


def test_alarm_call_label_only_when_a_call_is_heard_this_tick() -> None:
    listener, other = _pair("floor", "floor")
    assert other._compute_affect_tone() == "fearful"
    assert other._is_emitting_alarm() is False
    events = listener._build_context_events()
    assert "alarm_call" not in events

    caller = ChinchillaAgent(sex="M", position="floor", rng_seed=87, physiology_as_policy=True)
    hearer = ChinchillaAgent(sex="F", position="floor", rng_seed=88, physiology_as_policy=True)
    far = ChinchillaAgent(sex="F", position="door", rng_seed=89, physiology_as_policy=True)
    _colony(caller, hearer, far)
    _link(hearer, caller)
    _link(far, caller)
    caller.affective_space.axes["stress"] = 0.1
    caller._anchor_alarm_stress()
    caller.affective_space.axes["stress"] = 0.9
    hearer._perceive()
    far._perceive()
    assert "alarm_call" in hearer._build_context_events()
    assert "alarm_call" not in far._build_context_events()
    hearer._perceive()
    assert "alarm_call" not in hearer._build_context_events()


def _reward(agent: ChinchillaAgent, *, stress: float, hunger: float, food: float, hunger_after: float | None = None) -> float:
    agent.hunger = hunger
    agent.thirst = 0.2
    agent.wakefulness.wakefulness = 0.2
    agent.affective_space.axes["stress"] = stress
    agent.resources = SharedResources(food_pellets=food, hay=food)
    before = agent._physiology_snapshot()
    if hunger_after is not None:
        agent.hunger = hunger_after
    return agent._compute_reward(before=before, executed_action="idle" if hunger_after is None else "eat")


def test_reward_ignores_bowl_level_and_stress() -> None:
    agent = ChinchillaAgent(sex="F", rng_seed=90, physiology_as_policy=True)
    full = _reward(agent, stress=0.9, hunger=0.2, food=1.0)
    empty = _reward(agent, stress=0.9, hunger=0.2, food=0.0)
    calm = _reward(agent, stress=0.0, hunger=0.2, food=1.0)
    assert full == 0.0
    assert empty == full
    assert calm == full

    fed = _reward(agent, stress=0.9, hunger=0.9, food=1.0, hunger_after=0.9 - EAT_RELIEF)
    still_hungry = _reward(agent, stress=0.0, hunger=0.9, food=0.0)
    assert fed > 0.0
    assert still_hungry < 0.0
    assert fed != still_hungry


def test_fear_contagion_save_roundtrip_and_legacy_default(tmp_path: Path) -> None:
    agent = ChinchillaAgent(sex="F", name="Ada", rng_seed=91, is_mature=True, physiology_as_policy=True)
    agent._fear_contagion["neighbour"] = (0.42, 15.0)
    agent._alarm_habituation["other"] = (0.4, 12.0)
    runner = SimulationRunner(death_journal_path=tmp_path / "deaths.jsonl")
    runner.add_agent(agent)
    storage = ColonyStorage(save_dir=tmp_path)
    loaded = storage.load_colony(storage.save_colony(runner, "tone.json"))
    restored = loaded.agents[0]
    assert restored._fear_contagion["neighbour"] == (0.42, 15.0)
    assert restored._alarm_habituation["other"][0] == 0.4

    path = Path(storage.save_colony(runner, "legacy.json"))
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["agents"][0]["runtime"]["alarm"].pop("fear_contagion")
    path.write_text(json.dumps(payload), encoding="utf-8")
    legacy = storage.load_colony(path).agents[0]
    assert legacy._fear_contagion == {}
    assert legacy._alarm_habituation["other"][0] == 0.4

    payload["agents"][0]["runtime"].pop("alarm")
    path.write_text(json.dumps(payload), encoding="utf-8")
    older = storage.load_colony(path).agents[0]
    assert older._fear_contagion == {}
    assert older._alarm_emit_count == 0
