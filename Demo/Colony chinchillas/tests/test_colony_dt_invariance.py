"""Issue #39 items A, C, D, and E. Decision rate, relief band, sleep trap, metabolism.

Item B is not implemented. An unmet need keeps spending energy when the
animal cannot act on it, including during a real sleep bout. That cost is
per simulated second, so 1x and 10x lose the same energy for the same gap.
"""

from __future__ import annotations

import random

import pytest

from colony_agent import (
    HUNGER_ACCUMULATION_PER_S,
    HUNGER_AVAILABILITY_THRESHOLD,
    HUNGER_NEED_THRESHOLD,
    SLEEP_WAKEFULNESS_THRESHOLD,
    THIRST_ACCUMULATION_PER_S,
    THIRST_AVAILABILITY_THRESHOLD,
    THIRST_CRITICAL_THRESHOLD,
    THIRST_NEED_THRESHOLD,
    ChinchillaAgent,
)
from colony_gui.app import format_speed_status_line
from colony_gui.colony_gui import ColonyGUI
from colony_gui.i18n import reset_language, set_language
from colony_storage import ColonyStorage
from config_colony import (
    COLONY_MAX_LIFESPAN_AGE_S,
    COLONY_MAX_LIFESPAN_STEPS,
    UNMET_THIRST_ENERGY_PER_S,
)
from genome import GenomeVector
from shared_resources import SharedResources
from simulation_runner import SimulationRunner

# Nominal UI step at speed 1. Load widens the base to 0.25 s before * speed,
# so a live 10x tick is 2.5 s. See colony_gui.app.SIM_MAX_STEP_S.
UI_DT_1X = 1.0 / 12.0
UI_DT_1X_LOAD = 0.25
UI_DT_10X = 0.25 * 10.0


def _one(seed: int = 1) -> tuple[SimulationRunner, ChinchillaAgent]:
    runner = SimulationRunner(death_journal_path=f"/tmp/colony-dt-{seed}.jsonl")
    agent = ChinchillaAgent(sex="F", rng_seed=seed, physiology_as_policy=True)
    runner.add_agent(agent)
    return runner, agent


def _decision_dts(duration_s: float, dt: float, *, agents: int = 1) -> list[float]:
    calls: list[float] = []
    original = ChinchillaAgent.sim_step

    def wrapped(self: ChinchillaAgent, step_dt: float) -> None:
        calls.append(float(step_dt))
        original(self, step_dt)

    state = random.getstate()
    random.seed(1)
    ChinchillaAgent.sim_step = wrapped  # type: ignore[method-assign]
    try:
        runner = SimulationRunner(death_journal_path="/tmp/colony-dt-decisions.jsonl")
        for index in range(agents):
            runner.add_agent(
                ChinchillaAgent(sex="F" if index % 2 == 0 else "M", rng_seed=index + 1)
            )
        runner.run_for(duration_s, dt=dt)
    finally:
        ChinchillaAgent.sim_step = original  # type: ignore[method-assign]
        random.setstate(state)
    return calls


def test_a_large_tick_splits_into_quarter_second_decisions() -> None:
    calls = _decision_dts(UI_DT_10X, UI_DT_10X)
    assert len(calls) == 10
    assert abs(sum(calls) - UI_DT_10X) < 1e-9
    assert all(step <= SimulationRunner.MAX_TICK_DT + 1e-12 for step in calls)


def test_a_decision_rate_matches_at_1x_load_and_10x() -> None:
    """Load-adapted 1x is one 0.25 s decision. 10x must take the same ones."""
    duration_s = 5.0
    one_x = _decision_dts(duration_s, UI_DT_1X_LOAD)
    ten_x = _decision_dts(duration_s, UI_DT_10X)
    assert len(one_x) == len(ten_x) == int(duration_s / UI_DT_1X_LOAD)
    assert max(one_x) <= UI_DT_1X_LOAD + 1e-12
    assert max(ten_x) <= UI_DT_1X_LOAD + 1e-12
    assert abs(sum(one_x) - duration_s) < 1e-6
    assert abs(sum(ten_x) - duration_s) < 1e-6


def test_a_nominal_10x_does_not_collapse_to_one_decision() -> None:
    """Speed 10 on the 1/12 s base is a 10/12 s frame, still decided at <= 0.25 s."""
    nominal_10x = UI_DT_1X * 10.0
    calls = _decision_dts(nominal_10x, nominal_10x)
    assert len(calls) >= 4
    assert all(step <= SimulationRunner.MAX_TICK_DT + 1e-12 for step in calls)
    assert abs(sum(calls) - nominal_10x) < 1e-6


def test_c_eat_and_drink_relieve_before_the_penalty() -> None:
    resources = SharedResources(food_pellets=1.0, hay=1.0, water=1.0)
    hungry = ChinchillaAgent(sex="F", rng_seed=3, physiology_as_policy=True)
    hungry.resources = resources
    hungry.colony = [hungry]
    hungry.hunger = (HUNGER_AVAILABILITY_THRESHOLD + HUNGER_NEED_THRESHOLD) / 2.0
    hungry.thirst = 0.1
    hungry.energy = 0.9
    assert HUNGER_AVAILABILITY_THRESHOLD <= hungry.hunger < HUNGER_NEED_THRESHOLD

    ate = hungry._try_acquire_resource("food_pellets")
    energy_after_eat = hungry.energy
    hungry._apply_unmet_need_cost(UI_DT_10X)

    assert ate is True
    assert hungry.hunger < HUNGER_AVAILABILITY_THRESHOLD
    assert hungry.energy == energy_after_eat

    blocked = ChinchillaAgent(sex="M", rng_seed=4, physiology_as_policy=True)
    blocked.resources = SharedResources(food_pellets=1.0, hay=1.0, water=1.0)
    blocked.colony = [blocked]
    blocked.hunger = HUNGER_AVAILABILITY_THRESHOLD - 0.02
    blocked.thirst = THIRST_AVAILABILITY_THRESHOLD - 0.02
    hunger_before = blocked.hunger
    thirst_before = blocked.thirst
    assert blocked._try_acquire_resource("food_pellets") is False
    assert blocked._try_acquire_resource("water") is False
    assert blocked.hunger == hunger_before
    assert blocked.thirst == thirst_before

    thirsty = ChinchillaAgent(sex="F", rng_seed=5, physiology_as_policy=True)
    thirsty.resources = SharedResources(food_pellets=1.0, hay=1.0, water=1.0)
    thirsty.colony = [thirsty]
    thirsty.thirst = (THIRST_AVAILABILITY_THRESHOLD + THIRST_NEED_THRESHOLD) / 2.0
    thirsty.hunger = 0.1
    assert thirsty._try_acquire_resource("water") is True
    assert thirsty.thirst < THIRST_AVAILABILITY_THRESHOLD


def test_c_penalty_still_starts_at_the_need_threshold_for_both_steps() -> None:
    drops = []
    for dt in (UI_DT_1X, UI_DT_10X):
        agent = ChinchillaAgent(sex="F", rng_seed=6, physiology_as_policy=True)
        agent.hunger = HUNGER_NEED_THRESHOLD
        agent.thirst = 0.1
        agent.current_action = "explore"
        agent.energy = 0.8
        agent._apply_unmet_need_cost(dt)
        drops.append(0.8 - agent.energy)
    assert drops[1] == pytest.approx(drops[0] * (UI_DT_10X / UI_DT_1X))


def test_d_voluntary_sleep_does_not_trap_at_either_speed() -> None:
    for dt in (UI_DT_1X, UI_DT_10X):
        agent = ChinchillaAgent(sex="F", rng_seed=7, physiology_as_policy=True)
        agent.colony = [agent]
        agent.resources = SharedResources()
        agent.wakefulness.wakefulness = 0.51
        agent.is_sleeping = False
        agent._sleep_entered_by_need = False
        agent.replaced_policy_action = "sleep"
        agent.thirst = 0.3
        agent.hunger = 0.3

        agent.sim_step(dt)

        assert agent.is_sleeping is False
        assert agent._sleep_entered_by_need is False
        assert agent.current_action == "rest"
        assert agent.wakefulness.total_sleep_time == 0.0
        assert agent._should_continue_sleeping() is False


def test_d_need_bout_continues_until_resume_threshold() -> None:
    for dt in (UI_DT_1X, UI_DT_10X):
        agent = ChinchillaAgent(sex="M", rng_seed=8, physiology_as_policy=True)
        agent.colony = [agent]
        agent.resources = SharedResources()
        agent.wakefulness.wakefulness = 0.60
        agent.is_sleeping = True
        agent._sleep_entered_by_need = True
        agent.current_action = "sleep"
        agent.thirst = 0.2
        agent.hunger = 0.2

        assert agent._should_continue_sleeping() is True
        agent.sim_step(dt)
        assert agent.is_sleeping is True
        assert agent._sleep_entered_by_need is True
        assert agent.wakefulness.wakefulness < 0.60


def test_d_penalty_band_thirst_wakes_a_need_bout_at_both_speeds() -> None:
    """The cost reaches exhaustion before the higher critical-need constants."""
    for dt in (UI_DT_1X, UI_DT_10X):
        for thirst in (THIRST_NEED_THRESHOLD, THIRST_CRITICAL_THRESHOLD):
            agent = ChinchillaAgent(sex="F", rng_seed=9, physiology_as_policy=True)
            agent.colony = [agent]
            agent.resources = SharedResources(food_pellets=1.0, hay=1.0, water=1.0)
            agent.wakefulness.wakefulness = 0.60
            agent.is_sleeping = True
            agent._sleep_entered_by_need = True
            agent.current_action = "sleep"
            agent.thirst = thirst
            agent.hunger = 0.2

            agent.sim_step(dt)

            assert agent.is_sleeping is False
            assert agent._sleep_entered_by_need is False
            assert agent._should_continue_sleeping() is False


def test_d_critical_sleep_still_outranks_thirst() -> None:
    agent = ChinchillaAgent(sex="M", rng_seed=10, physiology_as_policy=True)
    agent.wakefulness.wakefulness = SLEEP_WAKEFULNESS_THRESHOLD + 0.22
    agent.thirst = THIRST_CRITICAL_THRESHOLD
    agent.hunger = 0.2
    agent.is_sleeping = True
    agent._sleep_entered_by_need = True
    assert agent.wakefulness.wakefulness >= 0.9
    assert agent._must_wake_to_drink_or_eat() is False
    assert agent._should_continue_sleeping() is True


def test_unmet_need_still_costs_energy_while_asleep() -> None:
    """Item B stays: a real bout does not suspend the unmet-need cost."""
    for dt in (UI_DT_1X_LOAD, UI_DT_10X):
        agent = ChinchillaAgent(sex="F", rng_seed=11, physiology_as_policy=True)
        agent.thirst = (THIRST_NEED_THRESHOLD + THIRST_CRITICAL_THRESHOLD) / 2.0
        agent.hunger = 0.2
        agent.wakefulness.wakefulness = 0.60
        agent.is_sleeping = True
        agent._sleep_entered_by_need = True
        agent.current_action = "sleep"
        agent.energy = 0.8

        agent._apply_unmet_need_cost(dt)

        assert agent.energy == pytest.approx(0.8 - UNMET_THIRST_ENERGY_PER_S * dt)


def test_e_hunger_and_thirst_match_across_step_sizes() -> None:
    def needs_after(dt: float) -> tuple[float, float, float]:
        agent = ChinchillaAgent(sex="F", rng_seed=12, physiology_as_policy=True)
        agent.resources = SharedResources()
        agent.colony = [agent]
        agent.hunger = 0.2
        agent.thirst = 0.2
        elapsed = 0.0
        duration = 10.0
        while elapsed < duration - 1e-12:
            step = min(dt, duration - elapsed)
            agent._resource_metabolism_step(step)
            elapsed += step
        return agent.hunger, agent.thirst, agent._metabolism_tick

    fine = needs_after(0.1)
    coarse = needs_after(UI_DT_10X)
    assert coarse[0] == pytest.approx(fine[0])
    assert coarse[1] == pytest.approx(fine[1])
    assert coarse[2] == pytest.approx(fine[2])
    assert fine[0] == pytest.approx(0.2 + 10.0 * HUNGER_ACCUMULATION_PER_S)
    assert fine[1] == pytest.approx(0.2 + 10.0 * THIRST_ACCUMULATION_PER_S)


def test_e_sim_step_needs_match_at_1x_and_10x_when_not_eating() -> None:
    def run(dt: float) -> tuple[float, float, float]:
        runner, agent = _one(13)
        agent.replaced_policy_action = "explore"
        agent.hunger = 0.25
        agent.thirst = 0.22
        agent.wakefulness.wakefulness = 0.0
        runner.run_for(12.0, dt=dt)
        return agent.hunger, agent.thirst, agent.energy

    one_x = run(UI_DT_1X)
    ten_x = run(UI_DT_10X)
    assert ten_x[0] == pytest.approx(one_x[0], abs=1e-9)
    assert ten_x[1] == pytest.approx(one_x[1], abs=1e-9)
    assert ten_x[2] == pytest.approx(one_x[2], abs=0.02)


def test_seed7_founders_do_not_die_of_exhaustion_at_10x() -> None:
    state = random.getstate()
    random.seed(7)
    try:
        runner = SimulationRunner(death_journal_path="/tmp/colony-dt-seed7.jsonl")
        genome_rng = random.Random(7)
        agents = []
        for index in range(4):
            agent = ChinchillaAgent(
                sex="F" if index % 2 == 0 else "M",
                generation=0,
                genome=GenomeVector.random(genome_rng),
                physiology_as_policy=True,
                rng_seed=70 + index,
            )
            runner.add_agent(agent)
            agents.append(agent)
        runner.run_for(600.0, dt=UI_DT_10X)
    finally:
        random.setstate(state)

    assert runner.total_deaths == 0
    assert runner.sim_time == pytest.approx(600.0)
    for agent in agents:
        assert agent.mortality_system.cause_of_death != "exhaustion"
        assert agent.energy > 0.08


def test_founders_survive_the_same_interval_at_1x_and_10x() -> None:
    def live(dt: float) -> tuple[int, float, float]:
        state = random.getstate()
        random.seed(7)
        try:
            runner = SimulationRunner(death_journal_path=f"/tmp/colony-dt-pair-{dt}.jsonl")
            genome_rng = random.Random(7)
            agents = []
            for index in range(4):
                agent = ChinchillaAgent(
                    sex="F" if index % 2 == 0 else "M",
                    generation=0,
                    genome=GenomeVector.random(genome_rng),
                    physiology_as_policy=True,
                    rng_seed=70 + index,
                )
                runner.add_agent(agent)
                agents.append(agent)
            runner.run_for(90.0, dt=dt)
        finally:
            random.setstate(state)
        assert runner.total_deaths == 0
        return (
            runner.total_deaths,
            min(agent.energy for agent in agents),
            max(agent.hunger for agent in agents),
        )

    one_x = live(UI_DT_1X)
    ten_x = live(UI_DT_10X)
    assert one_x[0] == ten_x[0] == 0
    assert one_x[1] > 0.2
    assert ten_x[1] > 0.2


def test_sleep_flag_and_body_carry_roundtrip(tmp_path) -> None:
    runner, agent = _one(14)
    agent._sleep_entered_by_need = True
    agent._body_step_carry = 0.04
    agent.is_sleeping = True
    storage = ColonyStorage(save_dir=tmp_path)
    loaded = storage.load_colony(storage.save_colony(runner, "dt.json"))
    restored = loaded.agents[0]
    assert restored._sleep_entered_by_need is True
    assert restored._body_step_carry == pytest.approx(0.04)
    assert restored.is_sleeping is True


def test_speed_line_shows_actual_rate_when_sim_lags() -> None:
    runner = SimulationRunner(death_journal_path="/tmp/colony-dt-pace.jsonl")
    gui = ColonyGUI(runner)
    gui.speed = 10.0
    for _ in range(6):
        gui.note_sim_pace(real_dt=0.1, sim_advanced=0.25)
    assert gui.achieved_speed_ratio == pytest.approx(0.25)
    try:
        set_language("en")
        english = format_speed_status_line(
            speed=10.0,
            paused=False,
            audio_enabled=True,
            achieved_ratio=gui.achieved_speed_ratio,
        )
        assert "actual x2.5" in english
        held = format_speed_status_line(
            speed=10.0,
            paused=False,
            audio_enabled=False,
            achieved_ratio=1.0,
        )
        assert "actual" not in held
        set_language("ru")
        russian = format_speed_status_line(
            speed=10.0,
            paused=False,
            audio_enabled=True,
            achieved_ratio=0.25,
        )
        assert "факт x2.5" in russian
    finally:
        reset_language()


def _age_until_old_age(dt: float) -> tuple[float, str, int]:
    """Walk biological age with ``_age_step`` until old age.

    ``_age_step`` is the colony clock that passes ``biological_age_s``.
    It does not increment ``lived_steps``, so equal ages across ``dt``
    are not an accident of equal decision counts.
    """
    agent = ChinchillaAgent(sex="F", rng_seed=1, age=0.0)
    agent.energy = 0.9
    agent.wakefulness.wakefulness = 0.2
    agent.neuromodulators.cortisol = 0.05
    agent.lived_steps = 3
    cap = float(agent.mortality_system.max_lifespan_age_s)
    limit = int(cap / dt) + 3
    steps = 0
    while not agent.mortality_system.is_dead() and steps < limit:
        agent._age_step(dt)
        steps += 1
    assert agent.mortality_system.is_dead() is True
    assert agent.lived_steps == 3
    return float(agent.age), str(agent.mortality_system.cause_of_death), steps


def test_old_age_lifespan_matches_across_dt() -> None:
    cap = float(COLONY_MAX_LIFESPAN_AGE_S)
    fine_dt = 1.0
    coarse_dt = 10.0
    fine_age, fine_cause, fine_steps = _age_until_old_age(fine_dt)
    coarse_age, coarse_cause, coarse_steps = _age_until_old_age(coarse_dt)

    assert fine_cause == coarse_cause == "old_age"
    assert cap <= fine_age < cap + fine_dt + 1e-6
    assert cap <= coarse_age < cap + coarse_dt + 1e-6
    assert abs(fine_age - coarse_age) <= coarse_dt + 1e-6
    assert fine_steps != coarse_steps
    assert fine_steps < COLONY_MAX_LIFESPAN_STEPS
    assert coarse_steps < COLONY_MAX_LIFESPAN_STEPS


def test_runner_old_age_matches_at_nominal_1x_and_10x() -> None:
    """UI frame at 1x is 1/12 s. A 10x frame is 2.5 s and is split.

    Death is the first substep whose biological age reaches the cap.
    The two speeds take different decision counts for that same second.
    """

    def run(frame_dt: float, tag: str) -> tuple[float, int, str]:
        runner = SimulationRunner(death_journal_path=f"/tmp/colony-lifespan-{tag}.jsonl")
        agent = ChinchillaAgent(
            sex="F",
            rng_seed=11,
            age=COLONY_MAX_LIFESPAN_AGE_S - 1.0,
        )
        agent.energy = 0.9
        agent.wakefulness.wakefulness = 0.2
        runner.add_agent(agent)
        for _ in range(30):
            if agent.mortality_system.is_dead():
                break
            runner.tick(frame_dt)
        assert agent.mortality_system.is_dead() is True
        return (
            float(agent.age),
            int(agent.lived_steps),
            str(agent.mortality_system.cause_of_death),
        )

    age_1x, steps_1x, cause_1x = run(UI_DT_1X, "1x")
    age_10x, steps_10x, cause_10x = run(UI_DT_10X, "10x")
    assert cause_1x == cause_10x == "old_age"
    assert abs(age_1x - COLONY_MAX_LIFESPAN_AGE_S) <= UI_DT_1X + 1e-6
    assert abs(age_10x - COLONY_MAX_LIFESPAN_AGE_S) <= SimulationRunner.MAX_TICK_DT + 1e-6
    assert abs(age_1x - age_10x) <= SimulationRunner.MAX_TICK_DT + 1e-6
    assert steps_1x > steps_10x > 0
