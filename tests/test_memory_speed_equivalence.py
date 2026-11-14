"""Optimized memory paths must match the unsimplified formulas.

Indexing, shared decay factors, and the recall sum are implementation
details. These tests are the reference: set Jaccard, the closed-form decay
gap, a full eviction sort, and one impulse per recalled episode.
"""

import math
import random

import pytest

from affective_space import AXES, AffectiveSpace
from agent import Agent
from experience import Event, EventType, Path
from hippocampus import NOWAHippocampus
from intent_memory import IntentMemory
from selector import ActionSelector
from sleep import CortexMemory, SleepManager


def _reference_decay_factor(elapsed: float, half_life: float, decay_rate: float) -> float:
    if elapsed <= 0.0:
        return 1.0
    steps = elapsed / half_life
    half_life_factor = 0.5 ** steps
    if decay_rate > 0.0:
        factor = (0.90 * half_life_factor) + (0.10 * ((1.0 - decay_rate) ** steps))
    else:
        factor = half_life_factor if half_life_factor <= 1.0 else 1.0
    return min(1.0, max(0.0, factor))


def _build_agent(actions=("go", "stop"), capacity=64):
    hip = NOWAHippocampus(max_experiences=capacity)
    cortex = CortexMemory()
    intent = IntentMemory()
    sleep = SleepManager(hip, cortex, intent)
    selector = ActionSelector(actions=list(actions))
    agent = Agent(hip, cortex, selector, sleep, intent)
    for action in actions:
        agent.register_action_channel(action, go_weight=0.4, nogo_weight=0.4, habit_strength=0.1)
    sleep._rng.seed(0)
    return agent


def _path(*tokens: str) -> Path:
    path = Path()
    for token in tokens:
        kind = EventType.ACTION if token.startswith("action:") else EventType.CONTEXT
        path = path.add_event(Event(token, event_type=kind))
    return path


def test_decay_matches_closed_form_per_episode_and_shared_stamp(monkeypatch):
    monkeypatch.setattr("hippocampus.time.time", lambda: 1_700_000_000.0)
    hip = NOWAHippocampus(activation_decay_half_life=3600.0, decay_rate=0.015, activation_threshold=0.0)
    hip.store(_path("ctx:a", "action:go"), intensity=1.0, reward=0.2)
    hip.store(_path("ctx:b", "action:stop"), intensity=0.8, reward=-0.4)
    now = hip.signatures[0].last_decay_ts
    # Distinct gaps. One shared factor per timestamp must still match the formula.
    hip.signatures[0].last_decay_ts = now - 2.5
    hip.signatures[1].last_decay_ts = now - 0.25
    hip.experiences[0].activation_energy = 0.8
    hip.signatures[0].activation_weight = 0.8
    hip.experiences[1].activation_energy = 0.6
    hip.signatures[1].activation_weight = 0.6
    expected = [
        0.8 * _reference_decay_factor(2.5, 3600.0, 0.015),
        0.6 * _reference_decay_factor(0.25, 3600.0, 0.015),
    ]

    hip._apply_decay()

    for exp, sig, target in zip(hip.experiences, hip.signatures, expected):
        assert exp.activation_energy == pytest.approx(target, abs=1e-12)
        assert sig.activation_weight == pytest.approx(target, abs=1e-12)


def test_decay_one_gap_matches_formula_and_is_not_a_coarser_grid(monkeypatch):
    monkeypatch.setattr("hippocampus.time.time", lambda: 1_700_000_000.0)
    """A 2.5s gap is the closed form for 2.5s, not ten rounded 0.25s buckets.

    Ten real applications of the 0.25s factor are a different sampling of the
    same formula. Both must match that formula exactly; the implementation
    must not substitute one for the other.
    """
    half_life = 10.0
    rate = 0.2
    hip = NOWAHippocampus(
        activation_decay_half_life=half_life,
        decay_rate=rate,
        activation_threshold=0.0,
    )
    hip.store(_path("ctx:gap", "action:go"))
    start = hip.signatures[0].last_decay_ts
    hip.signatures[0].last_decay_ts = start - 2.5
    hip.signatures[0].activation_weight = 1.0
    hip.experiences[0].activation_energy = 1.0
    hip._apply_decay()
    assert hip.signatures[0].activation_weight == pytest.approx(
        _reference_decay_factor(2.5, half_life, rate),
        abs=1e-12,
    )

    stepped = 1.0
    for _ in range(10):
        stepped *= _reference_decay_factor(0.25, half_life, rate)
    # The blend is not a pure exponential, so splitting the gap is a different
    # curve. Guard that we did not silently replace the 2.5s form with it.
    assert hip.signatures[0].activation_weight != pytest.approx(stepped, abs=1e-6)


def test_activate_matches_full_similarity_scan_including_borderline(monkeypatch):
    monkeypatch.setattr("hippocampus.time.time", lambda: 1_700_000_000.0)
    hip = NOWAHippocampus(max_experiences=32, activation_similarity_threshold=0.20)
    for index in range(12):
        hip.store(_path(f"ctx:{index % 4}", "food", f"tag:{index}", "action:go"), reward=0.1 * index)
    # A query that only partly overlaps, so the early upper bound is in play.
    query = ["ctx:1", "food", "other"]
    for exp in hip.experiences:
        exp.activation_energy = 0.0
    for sig in hip.signatures:
        sig.activation_weight = 0.0

    activated = hip.activate(query)

    features = hip._sanitize_features(query)
    drive = hip._build_drive_vector(intensity=1.0)
    tokens = hip._build_context_tokens(features)
    context = hip._encode_context_vector(features, drive, hip.signatures[0].last_decay_ts, context_tokens=tokens)
    qmask, qcount = hip._bits_for(features, hip._feature_bits)
    tmask, tcount = hip._bits_for(tokens, hip._token_bits)
    ranked = []
    for exp, sig in zip(hip.experiences, hip.signatures):
        similarity = hip._fast_similarity(
            qmask, qcount, drive, context, tokens, tmask, tcount, sig
        )
        ranked.append((similarity, exp))
    expected = [exp for similarity, exp in ranked if similarity >= hip.activation_similarity_threshold]
    expected.sort(key=lambda exp: next(sim for sim, item in ranked if item is exp), reverse=True)
    assert activated == expected
    for similarity, exp in ranked:
        if similarity >= hip.activation_similarity_threshold:
            assert exp.activation_energy == pytest.approx(similarity, abs=1e-12)


def test_capacity_drop_matches_full_score_sort_and_keeps_earlier_tie():
    hip = NOWAHippocampus(max_experiences=8, novelty_capacity_bias=0.55, activation_threshold=0.0)
    for name in ("a", "b", "c", "d", "e"):
        hip.store(_path(f"ctx:{name}", "action:go"), reward=0.0)
    # Equal scores except list position. The later episode is the victim.
    for exp, sig in zip(hip.experiences, hip.signatures):
        exp.reinforcement_count = 1
        exp.activation_energy = 0.5
        exp.last_activated = 10.0
        sig.activation_weight = 0.5
        sig.feature_set = {"ctx:same", "action:go"}
        hip._stamp_signature(sig)
    hip._nov_valid = False
    hip.max_experiences = 4
    hip._sync_novelty_cache()

    def rank_key(index, exp, sig):
        scale = hip.novelty_sensitivity_scale
        base = 1.0 - float(sig._nov_max)
        novelty = min(1.0, max(0.0, base * scale))
        bias = hip.novelty_capacity_bias
        blend = ((1.0 - bias) * sig.activation_weight) + (bias * novelty)
        return (blend, novelty, exp.reinforcement_count, exp.last_activated, -index)

    ranked = [
        (rank_key(index, exp, sig), index, exp)
        for index, (exp, sig) in enumerate(zip(hip.experiences, hip.signatures))
    ]
    ranked.sort(reverse=True)
    overflow = len(hip.experiences) - hip.max_experiences
    expected = [item[2] for item in list(reversed(ranked))[:overflow]]

    hip._enforce_capacity()

    assert hip.last_evicted == expected
    assert len(hip.experiences) == 4
    # Equal keys keep the earlier episode: the dropped ones are the tail.
    assert [exp.last_activated for exp in hip.last_evicted] == [10.0] * overflow


def test_recall_sum_matches_one_impulse_per_episode():
    space = AffectiveSpace()
    space.axes = {axis: 0.1 for axis in AXES}
    experiences = []
    for index in range(6):
        trace = space.create_trace(intensity=0.4 + 0.1 * (index % 3))
        trace.timestamp -= 30.0 * index
        experiences.append(type("Exp", (), {"emotional_trace": trace})())
    now = 10_000.0
    fast = space.constrained_recall_from_experiences(experiences, now=now)
    impulses = [exp.emotional_trace.to_impulse(now=now) for exp in experiences]
    slow = space._apply_recall_constraints(impulses, 0.0, {axis: 0.0 for axis in AXES})
    assert fast is not None
    for axis in AXES:
        assert fast[axis] == pytest.approx(slow[axis], abs=1e-12)


def _decision_dts(frame_dt: float, max_dt: float = 0.25) -> list:
    """Same split the colony runner uses. One fat step is not the 10x schedule."""
    if frame_dt <= max_dt:
        return [frame_dt]
    steps = int(math.ceil(frame_dt / max_dt))
    piece = frame_dt / steps
    return [piece] * steps


def test_decisions_and_memory_match_at_1x_and_10x_step(monkeypatch):
    """1x load step is dt=0.25. A 10x frame of 2.5s is ten of those decisions.

    Wall time is frozen so decay is not resampled. Actions, episodes, and
    affect must match. An unsplit 2.5s step would feed the affect integrator
    a different dt and is not the accelerated schedule.
    """
    for module in ("hippocampus", "affective_space", "intent_memory", "agent", "experience", "sleep"):
        monkeypatch.setattr(f"{module}.time.time", lambda: 1_700_000_000.0)
    base = [
        ["nest", "food_ok"],
        ["nest", "food_low"],
        ["open", "food_ok"],
        ["open", "stranger"],
        ["nest", "food_ok"],
        ["nest", "water_low"],
    ]
    fine = _decision_dts(0.25)
    accelerated = _decision_dts(2.5)
    assert fine == [0.25]
    assert accelerated == [0.25] * 10
    contexts = [base[index % len(base)] for index in range(len(accelerated))]

    def run(dts: list):
        random.seed(7)
        agent = _build_agent()
        actions = []
        for dt, context in zip(dts, contexts):
            actions.append(
                agent.step(
                    context_events=list(context),
                    reward=0.2,
                    novelty=0.3,
                    conflict=0.1,
                    intensity=1.0,
                    dt=dt,
                )
            )
        hip = agent.hippocampus
        memory = [
            (
                tuple(exp.path.signature()),
                round(float(exp.reward), 6),
                exp.episode_id,
                round(float(sig.activation_weight), 8),
            )
            for exp, sig in zip(hip.experiences, hip.signatures)
        ]
        affect = tuple(round(float(agent.affective_space.axes[axis]), 8) for axis in AXES)
        return actions, memory, affect

    slow_actions, slow_memory, slow_affect = run([0.25] * len(contexts))
    fast_actions, fast_memory, fast_affect = run(accelerated)
    assert fast_actions == slow_actions
    assert fast_memory == slow_memory
    assert fast_affect == slow_affect
    assert len(slow_memory) == len(contexts)


def test_same_seed_repeats_the_same_trajectory(monkeypatch):
    """Dense episode storage must not change a seeded waking trajectory."""
    for module in ("hippocampus", "affective_space", "intent_memory", "agent", "experience", "sleep"):
        monkeypatch.setattr(f"{module}.time.time", lambda: 1_700_000_000.0)

    def once():
        random.seed(11)
        agent = _build_agent()
        actions = []
        for index in range(8):
            actions.append(
                agent.step(
                    context_events=["nest", f"tag:{index % 3}"],
                    reward=0.1 * (index % 2),
                    novelty=0.2,
                    conflict=0.0,
                    intensity=1.0,
                    dt=0.25,
                )
            )
        hip = agent.hippocampus
        memory = [
            (tuple(exp.path.signature()), round(float(sig.activation_weight), 8), exp.episode_id)
            for exp, sig in zip(hip.experiences, hip.signatures)
        ]
        affect = tuple(round(float(agent.affective_space.axes[axis]), 8) for axis in AXES)
        return actions, memory, affect

    assert once() == once()


def test_slotted_episode_and_trace_roundtrip_without_changing_recall(monkeypatch):
    monkeypatch.setattr("hippocampus.time.time", lambda: 1_700_000_000.0)
    monkeypatch.setattr("experience.time.time", lambda: 1_700_000_000.0)
    monkeypatch.setattr("affective_space.time.time", lambda: 1_700_000_000.0)
    hip = NOWAHippocampus(max_experiences=8)
    hip.store(_path("ctx:nest", "action:go"), intensity=0.7, reward=0.3)
    original = hip.experiences[0]
    original.emotional_trace = AffectiveSpace().create_trace(intensity=0.6)
    from state_codec import decode_tree, encode_tree

    restored = decode_tree(encode_tree(original))
    assert restored.path.signature() == original.path.signature()
    assert restored.reward == original.reward
    assert restored.activation_energy == original.activation_energy
    assert restored.emotional_trace.to_impulse(now=1_700_000_000.0).intensity == pytest.approx(
        original.emotional_trace.to_impulse(now=1_700_000_000.0).intensity
    )
    left = Event("ctx:nest", EventType.CONTEXT)
    right = Event("ctx:nest", EventType.CONTEXT)
    assert left.name is right.name
    assert left == right
