"""Issue #80 / first slice of #56: hold the walk to a bowl or the waterer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from colony_agent import TRAVEL_GOAL_TIMEOUT_S, ChinchillaAgent
from agent import Agent
from colony_behavior_profile import UnconditionedReflex
from colony_storage import ColonyStorage
from config_colony import RESOURCE_CONSUMPTION_MULTIPLIER
from shared_resources import SharedResources
from simulation_runner import SimulationRunner

BITE = 0.003 * RESOURCE_CONSUMPTION_MULTIPLIER


def _walker(
    *,
    position: str,
    hunger: float,
    thirst: float,
    policy: bool = True,
    preference: str = "food_pellets",
) -> ChinchillaAgent:
    resources = SharedResources()
    agent = ChinchillaAgent(
        sex="F",
        position=position,
        resources=resources,
        physiology_as_policy=policy,
        rng_seed=7,
    )
    agent.colony = [agent]
    agent.hunger = hunger
    agent.thirst = thirst
    agent.energy = 1.0
    agent.wakefulness.wakefulness = 0.05
    agent.is_sleeping = False
    agent._sleep_entered_by_need = False
    agent._food_source_preference = preference
    agent.affective_space.axes["stress"] = 0.05
    agent.sim_time = 0.0
    agent._last_position_change_time = 0.0
    agent._decision_script: list[str] = []
    return agent


def _install_script(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(self: ChinchillaAgent, *args: object, **kwargs: object) -> str:
        Agent.step(self, *args, **kwargs)
        script = getattr(self, "_decision_script", None)
        if script:
            return str(script.pop(0))
        return "socialize"

    monkeypatch.setattr(ChinchillaAgent, "step", fake)


def _last_source(agent: ChinchillaAgent) -> str | None:
    experiences = agent.hippocampus.experiences
    assert experiences, "the tick did not commit an experience"
    return getattr(experiences[-1], "override_source", None)


@pytest.mark.parametrize("policy", [True, False])
def test_drink_from_floor_holds_across_socialize_and_play(
    monkeypatch: pytest.MonkeyPatch,
    policy: bool,
) -> None:
    _install_script(monkeypatch)
    agent = _walker(position="floor", hunger=0.1, thirst=0.9, policy=policy)
    agent._decision_script = ["drink", "socialize", "play"]

    agent.sim_step(1.25)
    assert agent.position == "bowl_hay"
    assert agent.resources is not None
    assert agent.resources.water == pytest.approx(1.0)
    assert agent._travel_action == "drink"
    assert _last_source(agent) == "homeostatic:travel_drink"

    agent.sim_step(1.25)
    assert agent.position == "waterer"
    assert agent.resources.water == pytest.approx(1.0 - BITE)
    assert agent.thirst < 0.5
    assert agent._travel_action is None
    assert _last_source(agent) == "homeostatic:travel_drink"

    agent.sim_step(1.25)
    assert agent.resources.water == pytest.approx(1.0 - BITE)
    assert _last_source(agent) != "homeostatic:travel_drink"


def test_eat_from_house_holds_until_the_bowl(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_script(monkeypatch)
    agent = _walker(position="house", hunger=0.9, thirst=0.1, preference="food_pellets")
    agent._decision_script = ["eat", "socialize"]

    agent.sim_step(1.25)
    assert agent.position == "floor"
    assert agent._travel_action == "eat"
    assert agent._travel_target == "bowl_pellets"
    assert _last_source(agent) == "homeostatic:travel_eat"
    assert agent.resources is not None
    assert agent.resources.food_pellets == pytest.approx(1.0)

    agent.sim_step(1.25)
    assert agent.position == "bowl_pellets"
    assert agent.resources.food_pellets == pytest.approx(1.0 - BITE)
    assert agent.resources.hay == pytest.approx(1.0)
    assert agent._travel_action is None
    assert _last_source(agent) == "homeostatic:travel_eat"


def test_alarm_call_and_a_different_reflex_cancel_the_walk() -> None:
    agent = _walker(position="floor", hunger=0.1, thirst=0.9)
    agent.sim_time = 5.0
    executed, _, source = agent._resolve_executed_action("drink", ["zone:floor"])
    assert executed == "drink"
    assert source == "homeostatic:travel_drink"

    executed, _, source = agent._resolve_executed_action("socialize", ["alarm_call"])
    assert agent._travel_action is None
    assert executed == "hide"
    assert source == "reflex:panic_hide"

    reflex_agent = _walker(position="floor", hunger=0.1, thirst=0.9)
    reflex_agent.unconditioned_reflexes = (
        UnconditionedReflex(
            reflex_id="test_flee",
            trigger_any=("boom",),
            trigger_all=(),
            action="flee",
            priority=2.0,
            cooldown_s=0.0,
            override_exclusive=True,
        ),
    )
    reflex_agent.sim_time = 5.0
    reflex_agent._resolve_executed_action("drink", [])
    assert reflex_agent._travel_action == "drink"
    executed, _, source = reflex_agent._resolve_executed_action("play", ["boom"])
    assert executed == "flee"
    assert source == "reflex:test_flee"
    assert reflex_agent._travel_action is None


def test_thirst_stress_does_not_cancel_the_walk_and_alarm_still_does() -> None:
    agent = _walker(position="bowl_hay", hunger=0.1, thirst=0.9)
    agent.sim_time = 5.0
    agent._resolve_executed_action("drink", ["zone:bowl_hay"])
    assert agent._travel_action == "drink"

    executed, _, source = agent._resolve_executed_action(
        "socialize",
        ["zone:bowl_hay", "high_stress", "thirst_critical"],
    )
    assert executed == "drink"
    assert source == "homeostatic:travel_drink"
    assert agent._travel_action == "drink"
    assert "panic_hide" not in agent._reflex_last_activation

    executed, _, source = agent._resolve_executed_action("socialize", ["alarm_call"])
    assert executed == "hide"
    assert source == "reflex:panic_hide"
    assert agent._travel_action is None


def test_travel_times_out_after_15_simulated_seconds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = _walker(position="floor", hunger=0.1, thirst=0.9)
    agent.sim_time = 4.0
    executed, _, source = agent._resolve_executed_action("drink", [])
    assert executed == "drink"
    assert agent._travel_started_at == pytest.approx(4.0)

    agent.sim_time = 4.0 + TRAVEL_GOAL_TIMEOUT_S
    executed, _, source = agent._resolve_executed_action("play", [])
    assert executed == "play"
    assert source is None
    assert agent._travel_action is None

    _install_script(monkeypatch)
    walking = _walker(position="floor", hunger=0.1, thirst=0.9)
    walking._decision_script = ["drink"]
    monkeypatch.setattr(ChinchillaAgent, "_move_towards_any", lambda *args, **kwargs: False)
    monkeypatch.setattr(ChinchillaAgent, "_maybe_move_position", lambda *args, **kwargs: None)
    walking.sim_step(1.0)
    assert walking._travel_action == "drink"
    assert walking._travel_started_at == pytest.approx(1.0)
    for _ in range(14):
        walking.sim_step(1.0)
    assert walking.sim_time == pytest.approx(15.0)
    assert walking._travel_action == "drink"
    assert walking.resources is not None
    assert walking.resources.water == pytest.approx(1.0)
    walking.sim_step(1.0)
    assert walking.sim_time == pytest.approx(16.0)
    assert walking._travel_action is None
    assert walking.position == "floor"
    assert walking.resources.water == pytest.approx(1.0)


def test_sleep_clears_the_walk_and_a_sleeper_does_not_bite() -> None:
    agent = _walker(position="floor", hunger=0.9, thirst=0.1)
    agent.sim_time = 3.0
    agent._resolve_executed_action("eat", [])
    assert agent._travel_action == "eat"
    executed, _, source = agent._resolve_executed_action("sleep", [])
    assert executed == "sleep"
    assert agent._travel_action is None
    assert source != "homeostatic:travel_eat"

    assert agent.resources is not None
    agent.is_sleeping = True
    agent.current_action = "sleep"
    agent.position = "bowl_pellets"
    agent.hunger = 0.9
    assert agent._try_acquire_resource("food_pellets") is False
    agent.position = "waterer"
    agent.thirst = 0.9
    assert agent._try_acquire_resource("water") is False
    assert agent.resources.food_pellets == pytest.approx(1.0)
    assert agent.resources.water == pytest.approx(1.0)

    sleeper = _walker(position="house", hunger=0.1, thirst=0.1)
    sleeper._travel_action = "drink"
    sleeper._travel_target = "waterer"
    sleeper._travel_started_at = 0.0
    sleeper.is_sleeping = True
    sleeper._sleep_entered_by_need = True
    sleeper.wakefulness.wakefulness = 0.8
    sleeper.sim_step(1.0)
    assert sleeper.is_sleeping is True
    assert sleeper.current_action == "sleep"
    assert sleeper._travel_action is None
    assert sleeper.resources is not None
    assert sleeper.resources.water == pytest.approx(1.0)
    assert sleeper.resources.food_pellets == pytest.approx(1.0)
    assert sleeper.resources.hay == pytest.approx(1.0)


def test_empty_favorite_bowl_retargets_without_resetting_the_timer() -> None:
    agent = _walker(position="house", hunger=0.9, thirst=0.1, preference="food_pellets")
    agent.sim_time = 2.0
    agent._last_position_change_time = 0.0
    executed, _, source = agent._resolve_executed_action("eat", [])
    assert executed == "eat"
    assert source == "homeostatic:travel_eat"
    assert agent._travel_target == "bowl_pellets"
    started = agent._travel_started_at
    agent._interpret_action("eat")
    agent._finish_travel_goal("eat", 1.0, 1.0, 1.0)
    assert agent.position == "floor"
    assert agent._travel_action == "eat"
    assert agent.resources is not None
    agent.resources.food_pellets = 0.0

    executed, _, source = agent._resolve_executed_action("socialize", ["zone:floor"])
    assert executed == "eat"
    assert source == "homeostatic:travel_eat"
    assert agent._travel_target == "bowl_hay"
    assert agent._travel_started_at == started

    agent.sim_time = 4.0
    pellets_before = agent.resources.food_pellets
    hay_before = agent.resources.hay
    agent._interpret_action("eat")
    agent._finish_travel_goal("eat", 1.0, pellets_before, hay_before)
    assert agent.position == "bowl_hay"
    assert agent.resources.food_pellets == pytest.approx(0.0)
    assert agent.resources.hay == pytest.approx(1.0 - BITE)
    assert agent._travel_action is None


def test_critical_thirst_replaces_a_food_walk() -> None:
    agent = _walker(position="house", hunger=0.9, thirst=0.2)
    agent.sim_time = 2.0
    agent._resolve_executed_action("eat", [])
    assert agent._travel_action == "eat"
    agent.thirst = 0.9
    agent.sim_time = 3.0
    executed, _, source = agent._resolve_executed_action("socialize", [])
    assert executed == "drink"
    assert source == "homeostatic:travel_drink"
    assert agent._travel_action == "drink"
    assert agent._travel_target == "waterer"
    assert agent._travel_started_at == pytest.approx(3.0)


def test_drink_arrives_at_the_same_simulated_time_for_both_steps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_script(monkeypatch)
    arrivals: list[float] = []
    for dt in (0.25, 1.25):
        agent = _walker(position="floor", hunger=0.1, thirst=0.9)
        agent._decision_script = ["drink", "socialize", "play"]
        seen: float | None = None
        for _ in range(40):
            agent.sim_step(dt)
            assert agent.resources is not None
            if agent.resources.water < 1.0 - 1e-9:
                seen = float(agent.sim_time)
                break
        assert seen is not None
        arrivals.append(seen)
        assert agent.position == "waterer"
        assert agent.resources.water == pytest.approx(1.0 - BITE)
    assert abs(arrivals[0] - arrivals[1]) <= 1.25


def test_travel_is_not_saved_and_a_newborn_starts_without_one(tmp_path) -> None:
    runner = SimulationRunner()
    agent = _walker(position="floor", hunger=0.9, thirst=0.9)
    runner.add_agent(agent)
    agent._travel_action = "drink"
    agent._travel_target = "waterer"
    agent._travel_started_at = 3.0

    storage = ColonyStorage(save_dir=tmp_path)
    path = Path(storage.save_colony(runner, "travel.json"))
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert "_travel_action" not in json.dumps(payload)
    loaded = storage.load_colony(path)
    assert len(loaded.agents) == 1
    restored = loaded.agents[0]
    assert restored._travel_action is None
    assert restored._travel_target is None
    assert restored._travel_started_at is None

    child = agent._create_offspring(None)
    assert child._travel_action is None
    assert child._travel_target is None
    assert child._travel_started_at is None

    agent._travel_action = "eat"
    agent._travel_target = "bowl_pellets"
    agent._travel_started_at = 1.0

    class _Dead:
        def update(self, **kwargs: object) -> bool:
            return True

        def is_dead(self) -> bool:
            return True

    agent.mortality_system = _Dead()  # type: ignore[assignment]
    agent._apply_mortality(1.0)
    assert agent.current_action == "dead"
    assert agent._travel_action is None
    assert agent._travel_target is None
    assert agent._travel_started_at is None


def test_satiety_closes_the_walk_on_the_same_tick() -> None:
    eater = _walker(position="bowl_pellets", hunger=0.0, thirst=0.2)
    eater._travel_action = "eat"
    eater._travel_target = "bowl_pellets"
    eater._travel_started_at = 0.0
    eater.replaced_policy_action = "socialize"
    eater.sim_step(1.25)
    assert eater._travel_action is None
    assert eater.resources is not None
    assert eater.resources.food_pellets == pytest.approx(1.0)
    assert eater.resources.hay == pytest.approx(1.0)

    drinker = _walker(position="waterer", hunger=0.2, thirst=0.0)
    drinker._travel_action = "drink"
    drinker._travel_target = "waterer"
    drinker._travel_started_at = 0.0
    drinker.replaced_policy_action = "play"
    drinker.sim_step(1.25)
    assert drinker._travel_action is None
    assert drinker.resources is not None
    assert drinker.resources.water == pytest.approx(1.0)


def test_empty_bowls_close_the_walk_on_the_same_tick() -> None:
    agent = _walker(position="floor", hunger=0.9, thirst=0.1)
    assert agent.resources is not None
    agent.resources.food_pellets = 0.04
    agent.resources.hay = 0.04
    agent._travel_action = "eat"
    agent._travel_target = "bowl_pellets"
    agent._travel_started_at = 0.0
    agent.replaced_policy_action = "socialize"
    agent.sim_step(1.25)
    assert agent._travel_action is None
    assert agent.resources.food_pellets == pytest.approx(0.04)
    assert agent.resources.hay == pytest.approx(0.04)
    assert agent.position == "floor"
