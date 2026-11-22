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
        # The bite lands only at the bowl and the waterer. Pin them there
        # for this accounting tick; the walk itself is covered below.
        eater.position = "bowl_pellets"
        eater._last_position_change_time = eater.sim_time
        drinker.position = "waterer"
        drinker._last_position_change_time = drinker.sim_time
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


def _hungry(
    *,
    position: str,
    pellets: float = 1.0,
    hay: float = 1.0,
    water: float = 1.0,
    seed: int = 80,
    hunger: float = 0.9,
    thirst: float = 0.9,
) -> ChinchillaAgent:
    """Agent allowed to step once. sim_time is inside the move window and short of unstick."""
    agent = ChinchillaAgent(sex="F", rng_seed=seed, physiology_as_policy=True, position=position)
    agent.resources = SharedResources(food_pellets=pellets, hay=hay, water=water)
    agent.colony = [agent]
    agent.hunger = hunger
    agent.thirst = thirst
    agent.energy = 1.0
    agent.is_sleeping = False
    agent.current_action = "explore"
    agent.sim_time = 5.0
    agent._last_position_change_time = 0.0
    return agent


def test_eat_from_house_or_wheel_walks_and_does_not_take_food() -> None:
    """Not at a bowl yet: one eat step moves closer and leaves both bowls alone.

    ``floor`` is one hop from either bowl, so that start is the arrival tick
    below. ``house`` and ``wheel`` still have a hop in between.
    """
    for start in ("house", "wheel"):
        agent = _hungry(position=start, seed=90)
        agent._food_source_preference = "food_pellets"
        hunger = agent.hunger
        before = dict(agent.affective_space.axes)
        agent._interpret_action("eat")
        assert agent.position == "floor"
        assert agent.resources.food_pellets == 1.0
        assert agent.resources.hay == 1.0
        assert agent.hunger == hunger
        assert agent.affective_space.axes == pytest.approx(before)


def test_eat_from_the_floor_arrives_and_takes_one_portion() -> None:
    agent = _hungry(position="floor", seed=91)
    agent._food_source_preference = "food_pellets"
    agent._interpret_action("eat")
    assert agent.position == "bowl_pellets"
    assert agent.resources.food_pellets == pytest.approx(1.0 - BITE)
    assert agent.resources.hay == 1.0
    assert agent.hunger == pytest.approx(0.9 - EAT_RELIEF)


def test_eat_at_the_pellet_bowl_takes_only_pellets_even_if_hay_is_preferred() -> None:
    agent = _hungry(position="bowl_pellets", seed=92)
    agent._food_source_preference = "hay"
    agent._interpret_action("eat")
    assert agent.position == "bowl_pellets"
    assert agent.resources.food_pellets == pytest.approx(1.0 - BITE)
    assert agent.resources.hay == 1.0
    assert agent.hunger == pytest.approx(0.9 - EAT_RELIEF)


def test_eat_at_the_hay_bowl_takes_only_hay() -> None:
    agent = _hungry(position="bowl_hay", seed=93)
    agent._food_source_preference = "food_pellets"
    agent._interpret_action("eat")
    assert agent.position == "bowl_hay"
    assert agent.resources.hay == pytest.approx(1.0 - BITE)
    assert agent.resources.food_pellets == 1.0
    assert agent.hunger == pytest.approx(0.9 - EAT_RELIEF)


def test_empty_favorite_is_left_for_the_other_bowl_and_eaten_there() -> None:
    agent = _hungry(position="floor", pellets=0.0, hay=1.0, seed=94)
    agent._food_source_preference = "food_pellets"
    agent._interpret_action("eat")
    assert agent.position == "bowl_hay"
    assert agent.resources.food_pellets == 0.0
    assert agent.resources.hay == pytest.approx(1.0 - BITE)
    assert agent.hunger == pytest.approx(0.9 - EAT_RELIEF)


def test_standing_at_an_empty_bowl_walks_to_the_other_and_eats() -> None:
    agent = _hungry(position="bowl_pellets", pellets=0.0, hay=1.0, seed=95)
    agent._food_source_preference = "food_pellets"
    agent._interpret_action("eat")
    assert agent.position == "bowl_hay"
    assert agent.resources.food_pellets == 0.0
    assert agent.resources.hay == pytest.approx(1.0 - BITE)
    assert agent.hunger == pytest.approx(0.9 - EAT_RELIEF)


def test_thin_bowl_is_not_eaten_and_the_other_bowl_is() -> None:
    """0.05 is not enough to bite. The other bowl, above that line, is."""
    agent = _hungry(position="bowl_pellets", pellets=0.05, hay=1.0, seed=96)
    agent._interpret_action("eat")
    assert agent.position == "bowl_hay"
    assert agent.resources.food_pellets == 0.05
    assert agent.resources.hay == pytest.approx(1.0 - BITE)
    assert agent.hunger == pytest.approx(0.9 - EAT_RELIEF)


def test_both_bowls_empty_keeps_the_no_food_impulse_and_takes_nothing() -> None:
    refused = _hungry(position="bowl_pellets", pellets=0.0, hay=0.0, seed=97)
    twin = _hungry(position="bowl_pellets", pellets=0.0, hay=0.0, seed=97)
    refused._interpret_action("eat")
    twin._apply_affect_impulse(stress=0.2, valence=-0.3, intensity=0.8)
    assert refused.position == "bowl_pellets"
    assert refused.resources.food_pellets == 0.0
    assert refused.resources.hay == 0.0
    assert refused.hunger == 0.9
    assert refused.affective_space.axes == pytest.approx(twin.affective_space.axes)


def test_walking_to_food_does_not_apply_the_no_food_impulse() -> None:
    agent = _hungry(position="house", seed=98)
    before = dict(agent.affective_space.axes)
    agent._interpret_action("eat")
    assert agent.position == "floor"
    assert agent.resources.food_pellets == 1.0
    assert agent.resources.hay == 1.0
    assert agent.hunger == 0.9
    assert agent.affective_space.axes == pytest.approx(before)


def test_strict_consume_does_not_top_up_the_other_bowl() -> None:
    short = SharedResources(food_pellets=0.004, hay=1.0)
    assert short.consume_food(0.02, primary="food_pellets", strict=True) is True
    assert short.food_pellets == 0.0
    assert short.hay == 1.0

    empty = SharedResources(food_pellets=0.0, hay=1.0)
    assert empty.consume_food(0.02, primary="food_pellets", strict=True) is False
    assert empty.food_pellets == 0.0
    assert empty.hay == 1.0

    shared = SharedResources(food_pellets=0.004, hay=1.0)
    assert shared.consume_food(0.02, primary="food_pellets", strict=False) is True
    assert shared.food_pellets == 0.0
    assert shared.hay == pytest.approx(1.0 - 0.016)

    enough = SharedResources(food_pellets=1.0, hay=1.0)
    assert enough.consume_food(0.02, primary="food_pellets", strict=False) is True
    assert enough.food_pellets == pytest.approx(0.98)
    assert enough.hay == 1.0


def test_drink_while_still_at_bowl_hay_does_not_take_water() -> None:
    """bowl_hay is not the waterer. With the move interval closed, nothing is drunk."""
    agent = _hungry(position="bowl_hay", seed=99)
    agent.sim_time = 0.0
    agent._last_position_change_time = 0.0
    agent._interpret_action("drink")
    assert agent.position == "bowl_hay"
    assert agent.resources.water == 1.0
    assert agent.thirst == 0.9


def test_drink_from_the_floor_stops_at_bowl_hay_without_taking_water() -> None:
    agent = _hungry(position="floor", seed=100)
    agent._interpret_action("drink")
    assert agent.position == "bowl_hay"
    assert agent.resources.water == 1.0
    assert agent.thirst == 0.9


def test_drink_arriving_from_bowl_hay_takes_one_portion() -> None:
    agent = _hungry(position="bowl_hay", seed=101)
    agent._interpret_action("drink")
    assert agent.position == "waterer"
    assert agent.resources.water == pytest.approx(1.0 - BITE)
    assert agent.thirst == pytest.approx(0.9 - DRINK_RELIEF)


def test_drink_at_the_waterer_takes_one_portion() -> None:
    agent = _hungry(position="waterer", seed=102)
    agent._interpret_action("drink")
    assert agent.position == "waterer"
    assert agent.resources.water == pytest.approx(1.0 - BITE)
    assert agent.thirst == pytest.approx(0.9 - DRINK_RELIEF)


def test_policy_mode_bites_at_moderate_hunger() -> None:
    """The 0.50 availability line no longer refuses a bite the core already chose."""
    agent = _hungry(position="bowl_pellets", hunger=0.3, thirst=0.3, seed=103)
    agent._interpret_action("eat")
    assert agent.resources.food_pellets == pytest.approx(1.0 - BITE)
    assert agent.hunger == 0.0
    agent.position = "waterer"
    agent._interpret_action("drink")
    assert agent.resources.water == pytest.approx(1.0 - BITE)
    assert agent.thirst == 0.0


def test_policy_satiety_does_not_bite() -> None:
    agent = _hungry(position="bowl_pellets", hunger=0.02, thirst=0.02, seed=104)
    agent._interpret_action("eat")
    assert agent.resources.food_pellets == 1.0
    assert agent.resources.hay == 1.0
    assert agent.hunger == 0.02
    agent.position = "waterer"
    agent._interpret_action("drink")
    assert agent.resources.water == 1.0
    assert agent.thirst == 0.02


def test_non_policy_homeostatic_swap_still_uses_the_availability_line() -> None:
    """Without the policy, a mild eat/drink is still replaced by explore."""
    mild = ChinchillaAgent(sex="F", rng_seed=105, physiology_as_policy=False)
    mild.hunger = 0.2
    mild.thirst = 0.2
    mild.wakefulness.wakefulness = 0.1
    mild.energy = 1.0
    assert mild._apply_homeostatic_action_policy("eat") == "explore"
    assert mild._apply_homeostatic_action_policy("drink") == "explore"

    # Acquire itself never had this gate when the policy is off, including
    # below the satiety floor. The swap above is what keeps a mild animal away.
    mild.resources = SharedResources()
    mild.colony = [mild]
    mild.position = "bowl_pellets"
    mild.hunger = 0.01
    assert mild._try_acquire_resource("food_pellets") is True
    mild.position = "waterer"
    mild.thirst = 0.01
    assert mild._try_acquire_resource("water") is True
