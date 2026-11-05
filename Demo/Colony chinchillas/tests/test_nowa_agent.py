from __future__ import annotations

from unittest.mock import patch

from colony_behavior_profile import load_colony_behavior_profile
from colony_agent import (
    SLEEP_RECOVERY_DURATION_FACTOR,
    ChinchillaAgent,
    WHEEL_RUN_MAX_CONTINUOUS_S,
)
from config_colony import COLONY_MAX_LIFESPAN_AGE_S, COLONY_MAX_LIFESPAN_STEPS
from shared_resources import SharedResources


def test_tc01_agent_has_full_nowa_stack() -> None:
    agent = ChinchillaAgent(sex="F", name="Луна")

    assert hasattr(agent, "affective_space")
    assert hasattr(agent, "neuromodulators")
    assert hasattr(agent, "value_layer")
    assert hasattr(agent, "hippocampus")
    assert hasattr(agent, "basal_ganglia")
    assert hasattr(agent, "decision_arbitrator")
    assert hasattr(agent, "wakefulness")

    assert agent.sex == "F"
    assert agent.name == "Луна"
    assert isinstance(agent.knowledge, dict)
    assert agent.is_pregnant is False


def test_tc02_affect_properties_are_projected_from_affective_space() -> None:
    agent = ChinchillaAgent(sex="M")

    assert 0.0 <= agent.stress <= 1.0
    assert -1.0 <= agent.valence <= 1.0
    assert 0.0 <= agent.arousal <= 1.0

    initial_stress = agent.stress
    agent._apply_affect_impulse(stress=0.3, intensity=0.8)
    assert agent.stress >= initial_stress


def test_tc03_affect_state_removed() -> None:
    agent = ChinchillaAgent(sex="F")

    assert not hasattr(agent, "affect")
    _ = agent.stress
    _ = agent.valence
    _ = agent.boredom
    _ = agent.energy


def test_tc04_sim_step_calls_base_agent_step() -> None:
    agent = ChinchillaAgent(sex="M")
    agent.colony = []
    agent.resources = SharedResources()

    step_calls: list[dict] = []
    with patch.object(
        agent.__class__.__bases__[0],
        "step",
        side_effect=lambda *a, **kw: step_calls.append(kw) or "explore",
    ):
        agent.sim_step(0.1)

    assert len(step_calls) == 1
    assert "context_events" in step_calls[0]


def test_tc05_hippocampus_accumulates_experience() -> None:
    agent = ChinchillaAgent(sex="F")
    agent.colony = []
    agent.resources = SharedResources()

    initial_count = len(agent.hippocampus.experiences)
    for _ in range(5):
        agent.sim_step(0.1)

    assert len(agent.hippocampus.experiences) > initial_count


def test_tc06_sleep_triggered_by_high_wakefulness() -> None:
    agent = ChinchillaAgent(sex="M", physiology_as_policy=False)
    agent.colony = []
    agent.resources = SharedResources()
    agent.wakefulness._wakefulness = 0.85
    before = float(agent.wakefulness.wakefulness)
    agent.sim_step(0.1)

    assert agent.is_sleeping is True
    assert float(agent.wakefulness.wakefulness) < before


def test_tc07_inherit_neuromodulators_from_parents() -> None:
    mother = ChinchillaAgent(sex="F")
    father = ChinchillaAgent(sex="M")

    mother.neuromodulators.serotonin = 0.8
    father.neuromodulators.serotonin = 0.4

    child = ChinchillaAgent(sex="F", age=0.0)
    child._inherit_nowa_from(mother, father)

    assert 0.3 <= child.neuromodulators.serotonin <= 0.9


def test_tc08_compute_affect_tone_uses_affective_space() -> None:
    agent = ChinchillaAgent(sex="F")
    agent.colony = []
    agent.resources = SharedResources()

    agent._apply_affect_impulse(stress=0.8, intensity=1.0)
    for _ in range(3):
        agent.sim_step(0.05)

    tone = agent._compute_affect_tone()
    assert tone in {"fearful", "excited", "calm", "aggressive", "sleeping"}


def test_tc09_context_events_include_position() -> None:
    agent = ChinchillaAgent(sex="M", position="wheel")
    agent.colony = []
    agent.resources = SharedResources()
    agent._perceive()

    events = agent._build_context_events()
    assert any("zone:wheel" in event for event in events)


def test_tc10_two_agents_run_without_crashes() -> None:
    resources = SharedResources()
    agent_f = ChinchillaAgent(sex="F", name="Луна", position="floor")
    agent_m = ChinchillaAgent(sex="M", name="Буря", position="floor")

    agent_f.colony = [agent_f, agent_m]
    agent_m.colony = [agent_f, agent_m]
    agent_f.resources = resources
    agent_m.resources = resources

    for _ in range(10):
        agent_f.sim_step(0.1)
        agent_m.sim_step(0.1)

    assert agent_f.sim_time > 0.9
    assert agent_m.sim_time > 0.9


def test_tc11_behavior_profile_loaded_from_colony_datasets() -> None:
    profile = load_colony_behavior_profile()

    assert profile.base_abilities
    assert profile.unconditioned_reflexes
    assert profile.habits
    assert "colony_agent_profile.json" in profile.source_file or profile.source_file == "builtin-default"


def test_tc12_habits_are_bootstrapped_from_datasets() -> None:
    agent = ChinchillaAgent(sex="F")

    stats = agent.intent_memory.get_stats()
    assert stats["total_traces"] >= len(agent.behavior_profile.habits)


def test_tc13_unconditioned_reflex_can_override_selected_action() -> None:
    agent = ChinchillaAgent(sex="M")
    agent.colony = []
    agent.resources = SharedResources()
    agent.affective_space.axes["stress"] = 0.95

    with patch.object(
        agent.__class__.__bases__[0],
        "step",
        return_value="rest",
    ):
        agent.sim_step(0.1)

    assert agent.current_action == "hide"


def test_tc14_colony_old_age_uses_sim_seconds() -> None:
    agent = ChinchillaAgent(sex="F")
    assert agent.mortality_system.max_lifespan_age_s == COLONY_MAX_LIFESPAN_AGE_S
    # Step field remains for snapshots. It is not the old-age criterion.
    assert agent.mortality_system.max_lifespan_steps == COLONY_MAX_LIFESPAN_STEPS


def test_tc15_unstuck_position_moves_agent_after_timeout() -> None:
    agent = ChinchillaAgent(sex="M", position="floor")
    agent.colony = [agent]
    agent.resources = SharedResources()
    agent.current_action = "explore"
    agent.sim_time = 25.0
    agent._last_position_change_time = 0.0
    before = agent.position

    agent._unstick_position()

    assert agent.position != before


def test_tc16_leaving_wheel_releases_lock() -> None:
    resources = SharedResources()
    agent = ChinchillaAgent(sex="F", position="wheel")
    agent.resources = resources
    resources.wheel_lock = agent.agent_id

    agent._set_position("floor")

    assert resources.wheel_lock is None


def test_tc17_unstuck_does_not_move_sleeping_agent() -> None:
    agent = ChinchillaAgent(sex="M", position="bowl_hay")
    agent.colony = [agent]
    agent.resources = SharedResources()
    agent.current_action = "sleep"
    agent.is_sleeping = True
    agent.sim_time = 30.0
    agent._last_position_change_time = 0.0

    agent._unstick_position()

    assert agent.position == "bowl_hay"


def test_tc18_move_towards_any_uses_shortest_path_step() -> None:
    agent = ChinchillaAgent(sex="F", position="waterer")
    agent.colony = [agent]
    agent.resources = SharedResources()
    agent.sim_time = 10.0
    agent._last_position_change_time = 0.0

    moved = agent._move_towards_any(["house"], force=True)

    assert moved is True
    # waterer -> bowl_hay -> floor -> house
    assert agent.position == "bowl_hay"


def test_tc19_run_wheel_blocked_does_not_freeze_in_house() -> None:
    resources = SharedResources()
    resources.wheel_lock = "other-agent"
    agent = ChinchillaAgent(sex="M", position="house")
    agent.colony = [agent]
    agent.resources = resources
    agent.sim_time = 20.0
    agent._last_position_change_time = 0.0

    agent._interpret_action("run_wheel")

    assert agent.position != "house"
    assert agent.position in {"floor", "corner"}


def test_tc20_relocate_within_targets_moves_even_if_already_on_target() -> None:
    agent = ChinchillaAgent(sex="F", position="floor")
    agent.colony = [agent]
    agent.resources = SharedResources()
    agent.sim_time = 30.0
    agent._last_position_change_time = 0.0

    moved = agent._move_towards_any(
        ["floor", "toy", "corner"],
        relocate_within_targets=True,
    )

    assert moved is True
    assert agent.position in {"toy", "corner"}


def test_tc21_wheel_owner_is_released_after_timeout() -> None:
    resources = SharedResources()
    agent = ChinchillaAgent(sex="M", position="wheel")
    agent.colony = [agent]
    agent.resources = resources
    resources.wheel_lock = agent.agent_id
    agent._wheel_run_started_at = 0.0
    agent.sim_time = WHEEL_RUN_MAX_CONTINUOUS_S + 0.5

    agent._interpret_action("run_wheel")

    assert resources.wheel_lock != agent.agent_id
    assert agent.position != "wheel"


def test_tc22_rest_can_relocate_when_rng_triggers_move() -> None:
    agent = ChinchillaAgent(sex="F", position="floor")
    agent.colony = [agent]
    agent.resources = SharedResources()
    agent.sim_time = 50.0
    agent._last_position_change_time = 0.0
    agent._rng.random = lambda: 0.0  # type: ignore[method-assign]

    agent._interpret_action("rest")

    assert agent.position in {"house", "dustbath"}


def test_tc23_homeostatic_policy_blocks_sleep_without_need() -> None:
    agent = ChinchillaAgent(sex="M")
    agent.hunger = 0.1
    agent.thirst = 0.1
    agent.wakefulness.wakefulness = 0.1

    resolved = agent._apply_homeostatic_action_policy("sleep")

    assert resolved in {"rest", "explore"}


def test_tc24_homeostatic_policy_forces_drink_on_critical_thirst() -> None:
    agent = ChinchillaAgent(sex="F")
    agent.thirst = 0.95
    agent.hunger = 0.1
    agent.wakefulness.wakefulness = 0.2

    resolved = agent._apply_homeostatic_action_policy("play")

    assert resolved == "drink"


def test_tc25_homeostatic_policy_blocks_eat_without_hunger() -> None:
    agent = ChinchillaAgent(sex="M")
    agent.hunger = 0.1
    agent.thirst = 0.1
    agent.wakefulness.wakefulness = 0.1

    resolved = agent._apply_homeostatic_action_policy("eat")

    assert resolved == "explore"


def test_tc26_eat_and_drink_reduce_internal_needs() -> None:
    resources = SharedResources(food_pellets=1.0, water=1.0)
    agent = ChinchillaAgent(sex="F")
    agent.resources = resources
    agent.hunger = 0.9
    agent.thirst = 0.9

    ate = agent._try_acquire_resource("food_pellets")
    drank = agent._try_acquire_resource("water")

    assert ate is True
    assert drank is True
    assert agent.hunger < 0.9
    assert agent.thirst < 0.9


def test_tc26b_eat_uses_hay_when_pellets_are_empty() -> None:
    resources = SharedResources(food_pellets=0.0, hay=1.0, water=1.0)
    agent = ChinchillaAgent(sex="M")
    agent.resources = resources
    agent.hunger = 0.9

    ate = agent._try_acquire_resource("food_pellets")

    assert ate is True
    assert resources.hay < 1.0
    assert resources.food_pellets == 0.0
    assert agent.hunger < 0.9


def test_tc26c_eat_respects_agent_food_preference_when_both_available() -> None:
    resources = SharedResources(food_pellets=1.0, hay=1.0, water=1.0)
    agent = ChinchillaAgent(sex="F")
    agent.resources = resources
    agent._food_source_preference = "hay"
    agent.hunger = 0.9

    ate = agent._try_acquire_resource("food_pellets")

    assert ate is True
    assert resources.hay < 1.0
    assert resources.food_pellets == 1.0


def test_tc26d_sleeping_agent_does_not_consume_shared_food_or_water() -> None:
    resources = SharedResources(food_pellets=1.0, hay=1.0, water=1.0)
    agent = ChinchillaAgent(sex="F")
    agent.resources = resources
    agent.is_sleeping = True
    agent.current_action = "sleep"
    agent._metabolism_tick = 1.0

    food_before = (resources.food_pellets, resources.hay)
    water_before = resources.water

    agent._resource_metabolism_step(1.0)

    assert (resources.food_pellets, resources.hay) == food_before
    assert resources.water == water_before


def test_tc26e_sleeping_agent_cannot_directly_eat_or_drink() -> None:
    resources = SharedResources(food_pellets=1.0, hay=1.0, water=1.0)
    agent = ChinchillaAgent(sex="M")
    agent.resources = resources
    agent.hunger = 0.9
    agent.thirst = 0.9
    agent.is_sleeping = True
    agent.current_action = "sleep"

    assert agent._try_acquire_resource("food_pellets") is False
    assert agent._try_acquire_resource("water") is False
    assert resources.food_pellets == 1.0
    assert resources.hay == 1.0
    assert resources.water == 1.0
    assert agent.hunger == 0.9
    assert agent.thirst == 0.9


def test_tc27_homeostatic_policy_prioritizes_more_urgent_need() -> None:
    agent = ChinchillaAgent(sex="F")
    agent.wakefulness.wakefulness = 0.1
    agent.hunger = 0.62
    agent.thirst = 0.8

    resolved = agent._apply_homeostatic_action_policy("play")

    assert resolved == "drink"


def test_tc28_old_age_follows_biological_age_not_decision_steps() -> None:
    young = ChinchillaAgent(sex="F")
    young.resources = SharedResources()
    young.energy = 1.0
    young.wakefulness.wakefulness = 0.2
    young.lived_steps = COLONY_MAX_LIFESPAN_STEPS + 50
    young.age = 10.0

    young._age_step(0.1)

    assert young.mortality_system.is_dead() is False
    assert abs(young.age - 10.1) < 1e-9

    old = ChinchillaAgent(sex="M")
    old.resources = SharedResources()
    old.energy = 1.0
    old.wakefulness.wakefulness = 0.2
    old.lived_steps = 1
    old.age = COLONY_MAX_LIFESPAN_AGE_S - 0.05

    old._age_step(0.1)

    assert old.mortality_system.is_dead() is True
    assert old.mortality_system.cause_of_death == "old_age"
    assert old.lived_steps == 1
    assert old.age >= COLONY_MAX_LIFESPAN_AGE_S


def test_tc29_sleep_has_priority_over_food_and_water_when_critical() -> None:
    agent = ChinchillaAgent(sex="F")
    agent.wakefulness.wakefulness = 0.92
    agent.hunger = 0.97
    agent.thirst = 0.96

    resolved = agent._apply_homeostatic_action_policy("drink")

    assert resolved == "sleep"


def test_tc30_sleep_recovery_runs_before_sleep_deprivation_mortality() -> None:
    agent = ChinchillaAgent(sex="M")
    agent.colony = [agent]
    agent.resources = SharedResources()
    agent.energy = 1.0
    # Recovery on this slice is dt * 22 physiological seconds. Start just
    # above the 0.95 death line so that slice, applied before mortality,
    # is what keeps the animal alive.
    dt = 0.1
    drop = dt * SLEEP_RECOVERY_DURATION_FACTOR / (8.0 * 60.0 * 60.0)
    agent.wakefulness.wakefulness = 0.95 + drop * 0.5
    agent.is_sleeping = True
    agent.current_action = "sleep"

    agent.sim_step(dt)

    assert agent.mortality_system.is_dead() is False
    assert float(agent.wakefulness.wakefulness) < 0.95


def test_tc31_each_chinchilla_has_its_own_nowa_core() -> None:
    mother = ChinchillaAgent(sex="F", rng_seed=1)
    father = ChinchillaAgent(sex="M", rng_seed=2)
    mother.colony = [mother, father]
    father.colony = mother.colony
    child = mother._create_offspring(father)

    minds = (mother, father, child)
    assert len({agent.agent_id for agent in minds}) == 3
    for attr in (
        "hippocampus",
        "cortex",
        "selector",
        "sleep_manager",
        "intent_memory",
        "neuromodulators",
        "affective_space",
        "wakefulness",
        "mortality_system",
    ):
        assert len({id(getattr(agent, attr)) for agent in minds}) == 3, attr
