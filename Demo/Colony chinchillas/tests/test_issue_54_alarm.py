"""Issue #54 part 2: colony affect time and bounded alarm contagion."""

from __future__ import annotations

import json
import random
from pathlib import Path

from agent_knowledge import KnownAgent
from colony_agent import (
    ALARM_REFRACTORY_S,
    ChinchillaAgent,
)
from colony_storage import ColonyStorage
from simulation_runner import SimulationRunner

# Same nominal steps as test_colony_dt_invariance: load-adapted 1x is one
# 0.25 s decision, 10x is a 2.5 s frame split into those decisions.
UI_DT_1X_LOAD = 0.25
UI_DT_10X = 2.5


def _link(observer: ChinchillaAgent, target: ChinchillaAgent, affinity: float) -> None:
    observer.knowledge[target.agent_id] = KnownAgent(
        agent_id=target.agent_id,
        name=target.name,
        sex=target.sex,
        last_seen_position=target.position,
        last_seen_time=observer.sim_time,
        familiarity=0.8,
        affinity=affinity,
        relationship_type="acquaintance",
    )


def _colony(*agents: ChinchillaAgent) -> None:
    group = list(agents)
    for agent in group:
        agent.colony = group


def _spike(caller: ChinchillaAgent, level: float = 0.9) -> None:
    """Anchor the recent level, then jump. The jump is the bark."""
    caller._anchor_alarm_stress()
    caller.affective_space.axes["stress"] = level


def _positive_affect_steps(agent: ChinchillaAgent, dt: float, ticks: int) -> list[tuple[float, bool]]:
    seen: list[tuple[float, bool]] = []
    original = agent.affective_space.step

    def wrapped(**kwargs: object) -> dict:
        elapsed = float(kwargs.get("time_elapsed", 1.0))  # type: ignore[arg-type]
        asleep = bool(kwargs.get("asleep", False))
        seen.append((elapsed, asleep))
        return original(**kwargs)

    agent.affective_space.step = wrapped  # type: ignore[method-assign]
    for _ in range(ticks):
        agent.sim_step(dt)
    return [(elapsed, asleep) for elapsed, asleep in seen if elapsed > 1e-9]


def test_awake_affect_advances_once_per_tick() -> None:
    agent = ChinchillaAgent(sex="F", rng_seed=3, physiology_as_policy=False)
    agent.colony = [agent]
    agent.hunger = 0.1
    agent.thirst = 0.1
    positive = _positive_affect_steps(agent, 0.25, 1)
    assert positive == [(0.25, False)]


def test_sleep_recovers_stress_with_one_asleep_advance_per_tick() -> None:
    agent = ChinchillaAgent(sex="F", rng_seed=4, physiology_as_policy=False)
    agent.colony = [agent]
    agent.is_sleeping = True
    agent._sleep_entered_by_need = True
    agent.wakefulness.wakefulness = 0.9
    agent.hunger = 0.1
    agent.thirst = 0.1
    agent.affective_space.axes["stress"] = 0.8
    agent.affective_space.baseline["stress"] = 0.05
    start = agent.stress
    ticks = 8
    dt = 0.25
    positive = _positive_affect_steps(agent, dt, ticks)
    assert agent.is_sleeping
    assert positive == [(dt, True)] * ticks
    assert agent.stress < start - 0.05


def test_known_caller_still_stronger_than_unknown() -> None:
    caller = ChinchillaAgent(sex="F", position="floor", rng_seed=1)
    known = ChinchillaAgent(sex="M", position="floor", rng_seed=2)
    stranger = ChinchillaAgent(sex="F", position="floor", rng_seed=3)
    _colony(caller, known, stranger)
    _link(known, caller, affinity=0.4)
    _spike(caller)
    known_start = known.stress
    stranger_start = stranger.stress
    known._perceive_alarm_calls()
    stranger._perceive_alarm_calls()
    assert known.stress - known_start > stranger.stress - stranger_start
    assert known.knowledge[caller.agent_id].last_seen_affect == "fearful"


def test_alarm_does_not_reach_a_distant_zone() -> None:
    caller = ChinchillaAgent(sex="F", position="floor", rng_seed=1)
    far = ChinchillaAgent(sex="M", position="door", rng_seed=2)
    _colony(caller, far)
    _spike(caller)
    start = far.stress
    far._perceive_alarm_calls()
    assert far.stress == start
    assert caller._alarm_emit_count == 1


def test_sleeper_does_not_emit_and_hears_less() -> None:
    caller = ChinchillaAgent(sex="M", position="floor", rng_seed=1)
    awake = ChinchillaAgent(sex="F", position="floor", rng_seed=2)
    asleep = ChinchillaAgent(sex="F", position="floor", rng_seed=3)
    _colony(caller, awake, asleep)
    asleep.is_sleeping = True
    _spike(asleep)
    assert asleep._is_emitting_alarm() is False
    assert asleep._alarm_emit_count == 0

    _spike(caller)
    awake_start = awake.stress
    asleep_start = asleep.stress
    awake._perceive_alarm_calls()
    asleep._perceive_alarm_calls()
    awake_delta = awake.stress - awake_start
    asleep_delta = asleep.stress - asleep_start
    assert awake_delta > 0.0
    assert 0.0 < asleep_delta < awake_delta


def test_habituation_weakens_a_repeated_caller() -> None:
    caller = ChinchillaAgent(sex="M", position="floor", rng_seed=1)
    listener = ChinchillaAgent(sex="F", position="floor", rng_seed=2)
    _colony(caller, listener)
    _spike(caller)
    start = listener.stress
    listener._perceive_alarm_calls()
    first = listener.stress - start

    later = caller.sim_time + ALARM_REFRACTORY_S + 1.0
    caller.sim_time = later
    listener.sim_time = later
    caller.affective_space.axes["stress"] = 0.1
    _spike(caller, 0.9)
    before = listener.stress
    listener._perceive_alarm_calls()
    second = listener.stress - before
    assert first > 0.0
    assert second < first


def test_bonded_partner_buffers_the_impulse() -> None:
    caller = ChinchillaAgent(sex="M", position="floor", rng_seed=1)
    alone = ChinchillaAgent(sex="F", position="floor", rng_seed=2)
    buffered = ChinchillaAgent(sex="F", position="floor", rng_seed=3)
    partner = ChinchillaAgent(sex="M", position="floor", rng_seed=4)
    _colony(caller, alone, buffered, partner)
    _link(buffered, partner, affinity=0.8)
    _spike(caller)
    alone_start = alone.stress
    buffered_start = buffered.stress
    alone._perceive_alarm_calls()
    buffered._perceive_alarm_calls()
    assert alone.stress - alone_start > buffered.stress - buffered_start


def test_alarm_state_roundtrip_and_old_save_does_not_bark(tmp_path: Path) -> None:
    agent = ChinchillaAgent(sex="F", name="Ada", rng_seed=5, is_mature=True)
    agent._alarm_refractory_until = 40.0
    agent._alarm_emit_count = 3
    agent._alarm_habituation["other"] = (0.4, 12.0)
    runner = SimulationRunner(death_journal_path=tmp_path / "deaths.jsonl")
    runner.add_agent(agent)
    storage = ColonyStorage(save_dir=tmp_path)
    loaded = storage.load_colony(storage.save_colony(runner, "alarm.json"))
    restored = loaded.agents[0]
    assert restored._alarm_refractory_until == 40.0
    assert restored._alarm_emit_count == 3
    assert restored._alarm_habituation["other"][0] == 0.4

    path = Path(storage.save_colony(runner, "legacy.json"))
    payload = json.loads(path.read_text(encoding="utf-8"))
    saved = payload["agents"][0]
    saved["runtime"].pop("alarm")
    saved["affect"]["stress"] = 0.9
    path.write_text(json.dumps(payload), encoding="utf-8")
    legacy = storage.load_colony(path).agents[0]
    assert legacy.stress == 0.9
    assert legacy._is_emitting_alarm() is False
    assert legacy._alarm_emit_count == 0


def _scripted_alarm_listener(dt: float, duration_s: float = 30.0) -> tuple[int, float]:
    random.seed(54)
    runner = SimulationRunner(death_journal_path="/tmp/colony-alarm-dt.jsonl")
    caller = ChinchillaAgent(sex="M", position="floor", rng_seed=1, physiology_as_policy=False)
    listener = ChinchillaAgent(sex="F", position="floor", rng_seed=2, physiology_as_policy=False)
    runner.add_agent(caller)
    runner.add_agent(listener)
    for agent in (caller, listener):
        agent._interpret_action = lambda action: None  # type: ignore[method-assign]
        agent._social_step = lambda: None  # type: ignore[method-assign]
    marks = (2.0, 20.0)
    fired: set[float] = set()
    original = caller.sim_step

    def wrapped(step_dt: float) -> None:
        original(step_dt)
        for mark in marks:
            if mark in fired or caller.sim_time + 1e-9 < mark:
                continue
            fired.add(mark)
            caller.affective_space.axes["stress"] = 0.05
            _spike(caller, 0.9)

    caller.sim_step = wrapped  # type: ignore[method-assign]
    runner.run_for(duration_s, dt=dt)
    return caller._alarm_emit_count, listener.stress


def test_alarm_matches_at_1x_load_and_10x() -> None:
    one_x = _scripted_alarm_listener(UI_DT_1X_LOAD)
    ten_x = _scripted_alarm_listener(UI_DT_10X)
    assert one_x[0] == ten_x[0] == 2
    assert abs(one_x[1] - ten_x[1]) < 1e-4


def test_fed_colony_does_not_lock_stress_or_alarm_for_120s() -> None:
    random.seed(54)
    runner = SimulationRunner(death_journal_path="/tmp/colony-issue-54-headless.jsonl")
    for index in range(9):
        runner.add_agent(
            ChinchillaAgent(
                sex="F" if index % 2 == 0 else "M",
                rng_seed=index + 1,
                is_mature=True,
            )
        )
    stuck_samples = 0
    all_audible_samples = 0
    samples = 0
    duration = 120.0
    dt = 0.25
    remaining = duration
    while remaining > 1e-9:
        runner.tick(min(dt, remaining))
        remaining -= dt
        living = [agent for agent in runner.agents if agent.current_action != "dead"]
        samples += 1
        if not living:
            break
        if all(0.75 <= agent.stress <= 0.86 for agent in living):
            stuck_samples += 1
        audible = 0
        for agent in living:
            if (
                not agent.is_sleeping
                and agent._alarm_call_open
                and agent.sim_time <= agent._alarm_event_until + 1e-9
            ):
                audible += 1
        if audible == len(living) and len(living) > 1:
            all_audible_samples += 1

    living = [agent for agent in runner.agents if agent.current_action != "dead"]
    assert len(living) == 9
    assert samples > 0
    assert stuck_samples == 0
    assert all_audible_samples == 0
    mean_stress = sum(agent.stress for agent in living) / len(living)
    assert mean_stress < 0.7
    emits = sum(agent._alarm_emit_count for agent in living)
    # A bout cannot repeat inside the refractory window. 120 s / 15 s is
    # eight bouts per animal; the old loop was one bark per tick.
    assert emits < len(living) * (duration / ALARM_REFRACTORY_S)
    assert runner.resources.food_pellets > 0.0
    assert runner.resources.water > 0.0
    assert all(agent.energy > 0.2 for agent in living)
