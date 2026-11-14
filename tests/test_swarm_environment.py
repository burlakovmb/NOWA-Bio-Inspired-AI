import random
from unittest.mock import MagicMock

import pytest

from fitness import FitnessEvaluator
from genome import GenomeVector
from swarm import (
    MIN_AGENT_DISTANCE,
    SLEEPING_SIGNAL_FACTOR,
    Position3D,
    SocialSignal,
    SpaceBounds,
    SwarmConfig,
    SwarmEnvironment,
    SwarmState,
)


def _make_agent(
    agent_id: str,
    *,
    axes=None,
    wakefulness: float = 0.1,
    genome=None,
):
    agent = MagicMock()
    agent.agent_id = agent_id
    agent.genome = genome
    agent.affective_space = MagicMock()
    agent.affective_space.axes = dict(axes or {})
    agent.wakefulness = MagicMock()
    agent.wakefulness.wakefulness = wakefulness
    agent.sleep.return_value = {"cycles": 1}
    agent.step.return_value = "act"
    agent.observe_external_input = MagicMock()
    return agent


def _build_env(**config_kwargs) -> SwarmEnvironment:
    return SwarmEnvironment(
        config=SwarmConfig(**config_kwargs),
        fitness_evaluator=FitnessEvaluator(),
        rng=random.Random(42),
    )


def test_tc_01_position3d_distance():
    a = Position3D(0.0, 0.0, 0.0)
    b = Position3D(3.0, 4.0, 0.0)
    assert a.distance_to(b) == pytest.approx(5.0, abs=1e-9)
    assert a.distance_to(a) == 0.0


def test_tc_02_spacebounds_2d_mode():
    bounds_2d = SpaceBounds(z_min=5.0, z_max=5.0)
    bounds_3d = SpaceBounds(z_min=0.0, z_max=50.0)
    assert bounds_2d.is_2d() is True
    assert bounds_3d.is_2d() is False


def test_tc_03_exclusion_principle_on_random_add():
    env = _build_env(bounds=SpaceBounds(x_max=100.0, y_max=100.0))
    for i in range(10):
        env.add_agent(_make_agent(f"a{i}"))

    positions = [env.get_position(f"a{i}") for i in range(10)]
    for i in range(len(positions)):
        for j in range(i + 1, len(positions)):
            assert positions[i].distance_to(positions[j]) >= (MIN_AGENT_DISTANCE - 1e-9)


def test_tc_04_sleeping_agent_is_visible():
    env = _build_env(
        bounds=SpaceBounds(x_max=100.0, y_max=100.0),
        base_perception_radius=50.0,
    )
    sleeper = _make_agent("sleeper", axes={"valence": 0.5, "arousal": 0.3, "stress": 0.2, "curiosity": 0.4})
    observer = _make_agent("observer")

    env.add_agent(sleeper, position=Position3D(10.0, 0.0, 0.0))
    env.add_agent(observer, position=Position3D(0.0, 0.0, 0.0))
    env._slots["sleeper"].is_sleeping = True

    nearby_ids = [agent.agent_id for agent, _ in env.get_agents_in_radius("observer", include_sleeping=True)]
    assert "sleeper" in nearby_ids


def test_tc_05_sleeping_source_emits_weaker_signal():
    env = _build_env(
        bounds=SpaceBounds(x_max=100.0, y_max=100.0),
        base_perception_radius=50.0,
        signal_decay_factor=0.0,
    )

    active_source = _make_agent(
        "active",
        axes={"valence": 1.0, "arousal": 1.0, "stress": 1.0, "curiosity": 1.0},
    )
    sleeping_source = _make_agent(
        "sleeping",
        axes={"valence": 1.0, "arousal": 1.0, "stress": 1.0, "curiosity": 1.0},
    )
    receiver = _make_agent("receiver")

    env.add_agent(active_source, position=Position3D(5.0, 0.0, 0.0))
    env.add_agent(sleeping_source, position=Position3D(-5.0, 0.0, 0.0))
    env.add_agent(receiver, position=Position3D(0.0, 0.0, 0.0))
    env._slots["sleeping"].is_sleeping = True

    signals = env.collect_signals_for_agent("receiver")
    sig_active = next(signal for signal in signals if signal.source_agent_id == "active")
    sig_sleeping = next(signal for signal in signals if signal.source_agent_id == "sleeping")

    assert sig_sleeping.signal_strength < sig_active.signal_strength
    assert (sig_sleeping.signal_strength / sig_active.signal_strength) == pytest.approx(
        SLEEPING_SIGNAL_FACTOR,
        abs=1e-9,
    )
    assert sig_sleeping.source_is_sleeping is True
    assert sig_active.source_is_sleeping is False


def test_tc_06_sleeping_agent_wakes_from_stress_signal():
    env = _build_env(
        bounds=SpaceBounds(x_max=100.0, y_max=100.0),
        sleep_threshold=0.7,
        wake_signal_threshold=0.6,
        base_perception_radius=50.0,
    )
    sleeper = _make_agent("sleeper", axes={}, wakefulness=0.75)
    alarm = _make_agent(
        "alarm",
        axes={"valence": -1.0, "arousal": 1.0, "stress": 1.0, "curiosity": 0.0},
        wakefulness=0.1,
    )

    env.add_agent(sleeper, position=Position3D(0.0, 0.0, 0.0))
    env.add_agent(alarm, position=Position3D(1.0, 0.0, 0.0))
    env._slots["sleeper"].is_sleeping = True

    env.tick()

    assert env._slots["sleeper"].is_sleeping is False
    assert sleeper.step.called


def test_tc_07_sleeping_agent_does_not_wake_from_weak_signal():
    env = _build_env(
        bounds=SpaceBounds(x_max=100.0, y_max=100.0),
        sleep_threshold=0.7,
        wake_signal_threshold=0.6,
        base_perception_radius=50.0,
        signal_decay_factor=0.1,
    )
    sleeper = _make_agent("sleeper", axes={}, wakefulness=0.75)
    far_alarm = _make_agent(
        "far_alarm",
        axes={"valence": -0.5, "arousal": 0.5, "stress": 0.5, "curiosity": 0.0},
        wakefulness=0.1,
    )

    env.add_agent(sleeper, position=Position3D(0.0, 0.0, 0.0))
    env.add_agent(far_alarm, position=Position3D(40.0, 0.0, 0.0))
    env._slots["sleeper"].is_sleeping = True

    env.tick()

    assert env._slots["sleeper"].is_sleeping is True
    assert not sleeper.step.called


def test_social_signal_fallback_is_an_impulse_without_time():
    env = _build_env(bounds=SpaceBounds(x_max=100.0, y_max=100.0))
    receiver = _make_agent("receiver")
    receiver.observe_external_input = None
    env.add_agent(receiver, position=Position3D(0.0, 0.0, 0.0))
    signal = SocialSignal(
        source_agent_id="src",
        valence=1.0,
        arousal=0.5,
        stress=0.2,
        curiosity=0.1,
        signal_strength=1.0,
        source_is_sleeping=False,
        distance=1.0,
        step=0,
    )
    env.apply_social_signal(receiver, signal, gain=0.2)
    assert receiver.affective_space.step.call_args.kwargs["time_elapsed"] == 0.0


def test_tc_08_sleeping_receiver_applies_half_gain():
    env = _build_env(bounds=SpaceBounds(x_max=100.0, y_max=100.0))
    active_receiver = _make_agent("active_receiver")
    sleeping_receiver = _make_agent("sleeping_receiver")
    env.add_agent(active_receiver, position=Position3D(0.0, 0.0, 0.0))
    env.add_agent(sleeping_receiver, position=Position3D(10.0, 0.0, 0.0))
    env._slots["sleeping_receiver"].is_sleeping = True

    signal = SocialSignal(
        source_agent_id="src",
        valence=1.0,
        arousal=0.5,
        stress=0.2,
        curiosity=0.1,
        signal_strength=1.0,
        source_is_sleeping=False,
        distance=1.0,
        step=0,
    )
    env.apply_social_signal(active_receiver, signal, gain=0.2)
    env.apply_social_signal(sleeping_receiver, signal, gain=0.2)

    active_payload = active_receiver.observe_external_input.call_args.kwargs["payload"]
    sleeping_payload = sleeping_receiver.observe_external_input.call_args.kwargs["payload"]
    assert sleeping_payload["valence"] == pytest.approx(active_payload["valence"] * 0.5, abs=1e-9)


def test_tc_09_agent_falls_asleep_autonomously():
    env = _build_env(bounds=SpaceBounds(x_max=100.0, y_max=100.0), sleep_threshold=0.7)
    tired = _make_agent("tired", axes={}, wakefulness=0.85)
    env.add_agent(tired)

    env.tick()

    assert env._slots["tired"].is_sleeping is True
    assert tired.sleep.called
    assert not tired.step.called


def test_tc_10_agent_wakes_by_hysteresis():
    env = _build_env(
        bounds=SpaceBounds(x_max=100.0, y_max=100.0),
        sleep_threshold=0.7,
        wake_signal_threshold=0.99,
    )
    rested = _make_agent("rested", axes={}, wakefulness=0.85)
    env.add_agent(rested)

    env.tick()  # falls asleep
    assert env._slots["rested"].is_sleeping is True

    rested.wakefulness.wakefulness = 0.35
    env.tick()

    assert env._slots["rested"].is_sleeping is False
    assert rested.step.called


def test_tc_11_genomic_perception_radius():
    env = _build_env(
        bounds=SpaceBounds(x_max=100.0, y_max=100.0),
        base_perception_radius=10.0,
    )

    large_genes = dict(GenomeVector.default().genes)
    large_genes["dr_perception_radius_factor"] = 2.0
    agent_large = _make_agent("large", genome=GenomeVector(genes=large_genes))

    small_genes = dict(GenomeVector.default().genes)
    small_genes["dr_perception_radius_factor"] = 0.5
    agent_small = _make_agent("small", genome=GenomeVector(genes=small_genes))

    env.add_agent(agent_large)
    env.add_agent(agent_small)

    assert env._slots["large"].perception_radius == pytest.approx(20.0, abs=1e-9)
    assert env._slots["small"].perception_radius == pytest.approx(5.0, abs=1e-9)


def test_tc_12_3d_distance_in_perception():
    env = _build_env(
        bounds=SpaceBounds(x_max=100.0, y_max=100.0, z_max=100.0),
        base_perception_radius=15.0,
    )
    a = _make_agent("a")
    b = _make_agent("b")

    env.add_agent(a, position=Position3D(0.0, 0.0, 0.0))
    env.add_agent(b, position=Position3D(10.0, 0.0, 10.0))

    nearby = env.get_agents_in_radius("a")
    assert any(agent.agent_id == "b" for agent, _ in nearby)


def test_tc_13_get_agents_in_radius_exclude_sleeping():
    env = _build_env(bounds=SpaceBounds(x_max=100.0, y_max=100.0), base_perception_radius=50.0)
    sleeper = _make_agent("sleeper")
    active = _make_agent("active")
    observer = _make_agent("observer")

    env.add_agent(sleeper, position=Position3D(5.0, 0.0, 0.0))
    env.add_agent(active, position=Position3D(-5.0, 0.0, 0.0))
    env.add_agent(observer, position=Position3D(0.0, 0.0, 0.0))
    env._slots["sleeper"].is_sleeping = True

    all_nearby = env.get_agents_in_radius("observer", include_sleeping=True)
    active_only = env.get_agents_in_radius("observer", include_sleeping=False)

    assert len(all_nearby) == 2
    assert len(active_only) == 1
    assert active_only[0][0].agent_id == "active"


def test_tc_14_move_agent_collision():
    env = _build_env(bounds=SpaceBounds(x_max=100.0, y_max=100.0))
    a = _make_agent("a")
    b = _make_agent("b")

    env.add_agent(a, position=Position3D(10.0, 10.0, 0.0))
    env.add_agent(b, position=Position3D(50.0, 50.0, 0.0))

    assert env.move_agent("b", Position3D(10.0, 10.0, 0.0)) is False
    assert env.move_agent("b", Position3D(30.0, 30.0, 0.0)) is True


def test_tc_15_replace_population_keeps_global_step():
    env = _build_env(bounds=SpaceBounds(x_max=100.0, y_max=100.0))
    a = _make_agent("a", axes={}, wakefulness=0.1)
    env.add_agent(a)

    env.tick()
    env.tick()
    assert env.global_step == 2

    new_agents = [_make_agent(f"new_{idx}") for idx in range(3)]
    env.replace_population(new_agents)

    assert env.global_step == 2
    assert len(env.get_all_agents()) == 3


def test_tc_16_get_swarm_state_counts_sleeping():
    env = _build_env(bounds=SpaceBounds(x_max=100.0, y_max=100.0))
    for i in range(4):
        env.add_agent(_make_agent(f"a{i}"))

    env._slots["a0"].is_sleeping = True
    env._slots["a1"].is_sleeping = True
    state = env.get_swarm_state()

    assert state.sleeping_count == 2
    assert state.active_count == 2
    assert state.agent_count == 4


def test_tc_17_run_generation_returns_n_states():
    env = _build_env(bounds=SpaceBounds(x_max=100.0, y_max=100.0))
    env.add_agent(_make_agent("solo", axes={}, wakefulness=0.1))

    states = env.run_generation(steps=5)
    assert len(states) == 5
    assert env.global_step == 5
    assert all(isinstance(state, SwarmState) for state in states)


def test_tc_18_error_in_one_agent_does_not_break_tick():
    env = _build_env(bounds=SpaceBounds(x_max=100.0, y_max=100.0))

    good = _make_agent("good", axes={}, wakefulness=0.1)
    bad = _make_agent("bad", axes={}, wakefulness=0.1)
    bad.step.side_effect = RuntimeError("crash")

    env.add_agent(good)
    env.add_agent(bad)
    state = env.tick()

    assert good.step.called
    assert isinstance(state, SwarmState)


def test_default_context_events_include_wakefulness_high():
    env = _build_env(bounds=SpaceBounds(x_max=100.0, y_max=100.0))
    agent = _make_agent("ctx_agent", wakefulness=0.9)
    env.add_agent(agent)

    events = env._resolve_context_events("ctx_agent", agent, context_override=None, incoming_signals=[])
    assert "wakefulness_high" in events


def test_tick_uses_default_context_when_context_fn_missing():
    env = _build_env(bounds=SpaceBounds(x_max=100.0, y_max=100.0))
    agent = _make_agent("ctx_low", wakefulness=0.2)
    env.add_agent(agent)

    env.tick()

    context_events = agent.step.call_args.args[0]
    assert "wakefulness_low" in context_events
    assert "agent_active" in context_events
