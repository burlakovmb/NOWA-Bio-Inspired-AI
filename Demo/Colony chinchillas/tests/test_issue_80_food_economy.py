"""Issue #80: shared food and water leave the bowl only when someone eats or drinks."""

from __future__ import annotations

import pytest

from colony_agent import (
    DRINK_RELIEF,
    EAT_RELIEF,
    HUNGER_ACCUMULATION_PER_S,
    HUNGER_AVAILABILITY_THRESHOLD,
    RESOURCE_MISSING_ENERGY_PENALTY_PER_S,
    THIRST_ACCUMULATION_PER_S,
    THIRST_AVAILABILITY_THRESHOLD,
    WATER_MISSING_ENERGY_PENALTY_PER_S,
    ChinchillaAgent,
)
from config_colony import RESOURCE_CONSUMPTION_MULTIPLIER
from shared_resources import SharedResources
from simulation_runner import SimulationRunner

# Bite size in _try_acquire_resource. Not the removed passive sip.
BITE = 0.003 * RESOURCE_CONSUMPTION_MULTIPLIER


class _Intake:
    def __init__(self) -> None:
        self.food: list[float] = []
        self.water: list[float] = []

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        original = ChinchillaAgent._try_acquire_resource

        def _tracked(agent: ChinchillaAgent, resource: str) -> bool:
            resources = agent.resources
            if resources is None:
                return original(agent, resource)
            food_before = float(resources.food_pellets) + float(resources.hay)
            water_before = float(resources.water)
            acquired = original(agent, resource)
            if resource == "food_pellets":
                taken = food_before - (float(resources.food_pellets) + float(resources.hay))
                if taken > 0.0:
                    self.food.append(taken)
            elif resource == "water":
                taken = water_before - float(resources.water)
                if taken > 0.0:
                    self.water.append(taken)
            return acquired

        monkeypatch.setattr(ChinchillaAgent, "_try_acquire_resource", _tracked)


def _quiet(sex: str, seed: int) -> ChinchillaAgent:
    agent = ChinchillaAgent(sex=sex, rng_seed=seed, physiology_as_policy=True)
    agent.wakefulness.wakefulness = 0.0
    agent.energy = 1.0
    agent.hunger = 0.05
    agent.thirst = 0.05
    agent.is_sleeping = False
    agent.current_action = "explore"
    agent.replaced_policy_action = "explore"
    return agent


def _executed(agent: ChinchillaAgent) -> list[str]:
    actions: list[str] = []
    for experience in agent.hippocampus.experiences:
        action = getattr(experience, "executed_action", None)
        if action:
            actions.append(str(action))
    return actions


def test_awake_animals_below_the_need_do_not_drain_the_bowls() -> None:
    runner = SimulationRunner()
    agents = [_quiet("F", 80), _quiet("M", 81), _quiet("F", 82)]
    for agent in agents:
        runner.add_agent(agent)

    pellets = float(runner.resources.food_pellets)
    hay = float(runner.resources.hay)
    water = float(runner.resources.water)

    for _ in range(24):
        runner._tick_once(1.0)

    assert runner.sim_time == pytest.approx(24.0)
    assert runner.resources.food_pellets == pellets
    assert runner.resources.hay == hay
    assert runner.resources.water == water
    for agent in agents:
        assert agent.is_sleeping is False
        assert agent.hunger < HUNGER_AVAILABILITY_THRESHOLD
        assert agent.thirst < THIRST_AVAILABILITY_THRESHOLD
        assert "eat" not in _executed(agent)
        assert "drink" not in _executed(agent)
        assert agent.hunger == pytest.approx(0.05 + 24.0 * HUNGER_ACCUMULATION_PER_S)
        assert agent.thirst == pytest.approx(0.05 + 24.0 * THIRST_ACCUMULATION_PER_S)


def test_empty_colony_does_not_drain_the_bowls() -> None:
    runner = SimulationRunner()
    pellets = float(runner.resources.food_pellets)
    hay = float(runner.resources.hay)
    water = float(runner.resources.water)

    runner.run_for(30.0, dt=1.0)

    assert runner.agents == []
    assert runner.sim_time == pytest.approx(30.0)
    assert runner.resources.food_pellets == pellets
    assert runner.resources.hay == hay
    assert runner.resources.water == water


def test_eat_and_drink_events_match_the_bowl_on_a_metabolism_tick(monkeypatch) -> None:
    intake = _Intake()
    intake.install(monkeypatch)
    runner = SimulationRunner()
    eater = _quiet("F", 83)
    drinker = _quiet("M", 84)
    runner.add_agent(eater)
    runner.add_agent(drinker)

    start_food = float(runner.resources.food_pellets) + float(runner.resources.hay)
    start_water = float(runner.resources.water)

    def _feed_and_water() -> None:
        eater.hunger = 0.8
        eater.thirst = 0.1
        eater.replaced_policy_action = "eat"
        drinker.hunger = 0.1
        drinker.thirst = 0.8
        drinker.replaced_policy_action = "drink"
        runner._tick_once(1.0)

    _feed_and_water()

    # Same 1 s step: the bite lands, then the metabolism second grows the
    # need. The bowl must lose the bite and nothing from that second.
    assert eater.hunger == pytest.approx(0.8 - EAT_RELIEF + HUNGER_ACCUMULATION_PER_S)
    assert drinker.thirst == pytest.approx(0.8 - DRINK_RELIEF + THIRST_ACCUMULATION_PER_S)
    assert eater._metabolism_tick == pytest.approx(0.0)
    assert intake.food == pytest.approx([BITE])
    assert intake.water == pytest.approx([BITE])
    assert start_food - (float(runner.resources.food_pellets) + float(runner.resources.hay)) == pytest.approx(
        sum(intake.food)
    )
    assert start_water - float(runner.resources.water) == pytest.approx(sum(intake.water))

    for _ in range(8):
        _feed_and_water()

    food_before_idle = float(runner.resources.food_pellets) + float(runner.resources.hay)
    water_before_idle = float(runner.resources.water)
    eater.hunger = 0.1
    eater.thirst = 0.1
    drinker.hunger = 0.1
    drinker.thirst = 0.1
    eater.replaced_policy_action = "explore"
    drinker.replaced_policy_action = "explore"
    runner._tick_once(1.0)

    assert float(runner.resources.food_pellets) + float(runner.resources.hay) == food_before_idle
    assert runner.resources.water == water_before_idle
    assert eater.hunger == pytest.approx(0.1 + HUNGER_ACCUMULATION_PER_S)
    assert drinker.thirst == pytest.approx(0.1 + THIRST_ACCUMULATION_PER_S)

    end_food = float(runner.resources.food_pellets) + float(runner.resources.hay)
    end_water = float(runner.resources.water)
    assert start_food - end_food == pytest.approx(sum(intake.food))
    assert start_water - end_water == pytest.approx(sum(intake.water))
    assert len(intake.food) == 9
    assert len(intake.water) == 9
    assert eater.is_sleeping is False
    assert drinker.is_sleeping is False


def test_hunger_and_thirst_still_accumulate_while_awake() -> None:
    runner = SimulationRunner()
    agent = _quiet("F", 85)
    agent.hunger = 0.2
    agent.thirst = 0.18
    runner.add_agent(agent)

    for _ in range(20):
        runner._tick_once(1.0)

    assert agent.is_sleeping is False
    assert agent.hunger == pytest.approx(0.2 + 20.0 * HUNGER_ACCUMULATION_PER_S)
    assert agent.thirst == pytest.approx(0.18 + 20.0 * THIRST_ACCUMULATION_PER_S)
    assert agent.hunger < HUNGER_AVAILABILITY_THRESHOLD
    assert runner.resources.food_pellets == 1.0
    assert runner.resources.hay == 1.0
    assert runner.resources.water == 1.0


def test_empty_bowls_still_cost_energy_and_are_not_sipped() -> None:
    agent = _quiet("M", 86)
    agent.resources = SharedResources(food_pellets=0.0, hay=0.0, water=0.0)
    agent.colony = [agent]
    agent.hunger = 0.2
    agent.thirst = 0.2
    agent.energy = 0.8
    agent.current_action = "explore"
    agent.is_sleeping = False

    agent._resource_metabolism_step(1.0)

    food_penalty = RESOURCE_MISSING_ENERGY_PENALTY_PER_S * float(RESOURCE_CONSUMPTION_MULTIPLIER)
    water_penalty = WATER_MISSING_ENERGY_PENALTY_PER_S * float(RESOURCE_CONSUMPTION_MULTIPLIER)
    assert agent.resources.food_pellets == 0.0
    assert agent.resources.hay == 0.0
    assert agent.resources.water == 0.0
    assert agent.energy == pytest.approx(0.8 - food_penalty - water_penalty)
    assert agent.hunger == pytest.approx(0.2 + HUNGER_ACCUMULATION_PER_S)
    assert agent.thirst == pytest.approx(0.2 + THIRST_ACCUMULATION_PER_S)


def test_sleep_still_skips_the_empty_bowl_penalty_and_the_bowls() -> None:
    agent = _quiet("F", 87)
    agent.resources = SharedResources(food_pellets=0.0, hay=0.0, water=0.0)
    agent.colony = [agent]
    agent.hunger = 0.2
    agent.thirst = 0.2
    agent.energy = 0.5
    agent.is_sleeping = True
    agent.current_action = "sleep"

    agent._resource_metabolism_step(1.0)

    assert agent.resources.food_pellets == 0.0
    assert agent.resources.hay == 0.0
    assert agent.resources.water == 0.0
    assert agent.energy == 0.5
    assert agent.hunger == pytest.approx(0.2 + HUNGER_ACCUMULATION_PER_S)
    assert agent.thirst == pytest.approx(0.2 + THIRST_ACCUMULATION_PER_S)
