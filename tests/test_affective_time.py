"""Time-correct affective dynamics: decay**dt, impulse/advance split, b0."""

import json
from pathlib import Path

from affective_space import (
    AXES,
    DEFAULT_BASELINE_ADAPT_RATE,
    AffectiveSpace,
    EmotionalImpulse,
)
from agent import Agent
from cortex import CortexMemory
from hippocampus import NOWAHippocampus
from intent_memory import IntentMemory
from selector import ActionSelector
from sleep import SECONDS_PER_SLEEP_CYCLE, SleepManager
from storage import AgentStorage


def _space(**overrides) -> AffectiveSpace:
    params = {
        "axes": {"valence": 0.5, "stress": 0.4},
        "baseline": {"valence": 0.2, "stress": 0.1},
        "baseline_setpoint": {"valence": 0.0, "stress": 0.0},
        "baseline_adapt_rate": 0.0,
        "legacy_compat_weight": 0.0,
    }
    params.update(overrides)
    return AffectiveSpace(**params)


def test_one_second_step_matches_legacy_and_dt_powers_retention():
    space = _space(lambda_reg=0.05)
    retention = space.axis_decay["valence"] - space.lambda_reg
    space.step(
        external_impulses=[EmotionalImpulse(vector={"valence": 0.2}, intensity=1.0, source="external")],
        time_elapsed=1.0,
    )
    expected = 0.2 + retention * (0.5 - 0.2) + 0.2
    assert abs(space.axes["valence"] - expected) < 1e-9

    longer = _space(lambda_reg=0.05)
    two = _space(lambda_reg=0.05)
    longer.advance(2.0)
    two.advance(1.0)
    two.advance(1.0)
    powered = 0.2 + (retention ** 2) * (0.5 - 0.2)
    assert abs(longer.axes["valence"] - powered) < 1e-9
    assert abs(longer.axes["valence"] - two.axes["valence"]) < 1e-9
    assert abs(longer.baseline["valence"] - 0.2) < 1e-12


def test_impulse_only_does_not_move_time():
    space = _space()
    baseline = dict(space.baseline)
    setpoint = dict(space.baseline_setpoint)
    cap = float(space.dynamic_norm_cap)
    space.apply_impulses(
        external_impulses=[EmotionalImpulse(vector={"stress": 0.25}, intensity=1.0, source="external")]
    )
    assert abs(space.axes["stress"] - 0.65) < 1e-9
    assert abs(space.axes["valence"] - 0.5) < 1e-12
    for axis in AXES:
        assert abs(space.baseline[axis] - baseline[axis]) < 1e-12
        assert abs(space.baseline_setpoint[axis] - setpoint[axis]) < 1e-12
    assert abs(float(space.dynamic_norm_cap) - cap) < 1e-12

    other = _space()
    other.step(
        external_impulses=[EmotionalImpulse(vector={"stress": 0.25}, intensity=1.0, source="external")],
        time_elapsed=0.0,
    )
    assert abs(other.axes["stress"] - space.axes["stress"]) < 1e-12


def test_advance_without_impulses_only_relaxes():
    space = _space(lambda_reg=0.05)
    retention = space.axis_decay["stress"] - space.lambda_reg
    space.advance(1.0)
    expected = 0.1 + retention * (0.4 - 0.1)
    assert abs(space.axes["stress"] - expected) < 1e-9


def test_sustained_stress_does_not_drag_baseline_within_30s():
    space = AffectiveSpace(baseline_setpoint={"stress": 0.0})
    assert abs(space.baseline_adapt_rate - DEFAULT_BASELINE_ADAPT_RATE) < 1e-15
    for _ in range(30):
        space.step(
            external_impulses=[EmotionalImpulse(vector={"stress": 1.0}, intensity=1.0, source="external")],
            time_elapsed=1.0,
        )
    assert space.axes["stress"] > 0.5
    assert space.baseline["stress"] < 0.05
    assert abs(space.baseline_setpoint["stress"]) < 1e-12


def test_baseline_returns_toward_setpoint_without_stressors():
    space = AffectiveSpace(
        axes={"stress": 0.7, "valence": -0.4},
        baseline={"stress": 0.7, "valence": -0.4},
        baseline_setpoint={"stress": 0.0, "valence": 0.1},
    )
    space.advance(48.0 * 3600.0)
    assert space.baseline["stress"] < 0.25
    assert abs(space.baseline["valence"] - 0.1) < abs(-0.4 - 0.1)
    assert abs(space.baseline_setpoint["stress"]) < 1e-12
    assert abs(space.baseline_setpoint["valence"] - 0.1) < 1e-12


def test_sleep_relaxes_faster_than_wake_for_the_same_time():
    def run(asleep: bool) -> AffectiveSpace:
        space = AffectiveSpace(
            axes={"stress": 0.8},
            baseline={"stress": 0.55},
            baseline_setpoint={"stress": 0.0},
            baseline_adapt_rate=0.02,
            legacy_compat_weight=0.0,
        )
        space.advance(3.0, asleep=asleep)
        return space

    wake = run(False)
    asleep = run(True)
    assert abs(asleep.axes["stress"] - asleep.baseline["stress"]) < abs(wake.axes["stress"] - wake.baseline["stress"])
    assert abs(asleep.baseline["stress"]) < abs(wake.baseline["stress"])


def test_one_second_steps_match_ten_second_steps():
    def initial() -> AffectiveSpace:
        return AffectiveSpace(
            axes={axis: 0.15 + 0.07 * index for index, axis in enumerate(AXES)},
            baseline={axis: -0.2 + 0.04 * index for index, axis in enumerate(AXES)},
            baseline_setpoint={axis: 0.03 * ((-1) ** index) for index, axis in enumerate(AXES)},
            legacy_compat_weight=0.0,
        )

    fine = initial()
    coarse = initial()
    steps = 20
    for _ in range(steps):
        fine.advance(1.0)
    for _ in range(steps // 10):
        coarse.advance(10.0)
    for axis in AXES:
        assert abs(fine.axes[axis] - coarse.axes[axis]) < 1e-9
        assert abs(fine.baseline[axis] - coarse.baseline[axis]) < 1e-9
        assert abs(fine.baseline_setpoint[axis] - coarse.baseline_setpoint[axis]) < 1e-12


def test_decision_only_recall_advances_affect_once():
    hip = NOWAHippocampus(max_experiences=8)
    cortex = CortexMemory()
    intent = IntentMemory()
    sleep = SleepManager(hip, cortex, intent)
    selector = ActionSelector(actions=["go", "stop"])
    agent = Agent(hip, cortex, selector, sleep, intent)
    agent.register_action_channel("go", go_weight=0.4, nogo_weight=0.4, habit_strength=0.1)
    agent.register_action_channel("stop", go_weight=0.4, nogo_weight=0.4, habit_strength=0.1)

    calls = []
    original = agent.affective_space.step

    def wrapped(**kwargs):
        calls.append(float(kwargs.get("time_elapsed", 1.0)))
        return original(**kwargs)

    agent.affective_space.step = wrapped
    agent.affective_space.constrained_recall_from_experiences = lambda experiences: {"stress": 0.25}

    agent.step(["nest"], decision_only=True, dt=1.0)
    assert calls == [0.0]

    agent.commit_executed_transition("go", reward=0.0, context_events=["nest"])
    assert [value for value in calls if value > 0.0] == [1.0]
    assert calls.count(0.0) == 1


def test_decision_only_recall_dt_zero_commit_keeps_zero_elapsed():
    hip = NOWAHippocampus(max_experiences=8)
    cortex = CortexMemory()
    intent = IntentMemory()
    sleep = SleepManager(hip, cortex, intent)
    selector = ActionSelector(actions=["go", "stop"])
    agent = Agent(hip, cortex, selector, sleep, intent)
    agent.register_action_channel("go", go_weight=0.4, nogo_weight=0.4, habit_strength=0.1)
    agent.register_action_channel("stop", go_weight=0.4, nogo_weight=0.4, habit_strength=0.1)

    calls = []
    original = agent.affective_space.step

    def wrapped(**kwargs):
        calls.append(float(kwargs.get("time_elapsed", 1.0)))
        return original(**kwargs)

    agent.affective_space.step = wrapped
    agent.affective_space.constrained_recall_from_experiences = lambda experiences: {"stress": 0.25}

    agent.step(["nest"], decision_only=True, dt=0)
    agent.commit_executed_transition("go", reward=0.0, context_events=["nest"])
    assert calls == [0.0, 0.0]


def test_setpoint_roundtrip_and_missing_field(tmp_path):
    hip = NOWAHippocampus()
    cortex = CortexMemory()
    selector = ActionSelector(actions=["a"])
    space = AffectiveSpace(
        axes={"stress": 0.4, "valence": 0.2},
        baseline={"stress": 0.3, "valence": 0.1},
        baseline_setpoint={"stress": -0.2, "valence": 0.05},
    )
    storage = AgentStorage(save_dir=str(tmp_path))
    path = storage.save_agent(hip, cortex, selector, affective_space=space, filename="mind.nowa")

    restored = AffectiveSpace()
    storage.load_agent(hip, cortex, selector, path, affective_space=restored)
    assert abs(restored.baseline_setpoint["stress"] - (-0.2)) < 1e-9
    assert abs(restored.baseline_setpoint["valence"] - 0.05) < 1e-9
    assert abs(restored.baseline["stress"] - 0.3) < 1e-9

    document = json.loads(Path(path).read_text(encoding="utf-8"))

    def strip(node):
        if isinstance(node, dict):
            node.pop("baseline_setpoint", None)
            for value in node.values():
                strip(value)
        elif isinstance(node, list):
            for item in node:
                strip(item)

    strip(document)
    Path(path).write_text(json.dumps(document), encoding="utf-8")
    bare = AffectiveSpace()
    storage.load_agent(hip, cortex, selector, path, affective_space=bare)
    assert abs(bare.baseline["stress"] - 0.3) < 1e-9
    assert abs(bare.baseline_setpoint["stress"] - bare.baseline["stress"]) < 1e-9
    assert abs(bare.baseline_setpoint["valence"] - bare.baseline["valence"]) < 1e-9


def test_sleep_affective_time_sums_to_the_real_duration():
    class Recorder:
        def __init__(self):
            self.calls = []
            self.axes = {}

        def step(self, **kwargs):
            self.calls.append((float(kwargs.get("time_elapsed", -1.0)), bool(kwargs.get("asleep", False))))

    hip = NOWAHippocampus(max_experiences=4)
    cortex = CortexMemory()
    manager = SleepManager(hip, cortex)
    manager.affective_space = Recorder()
    manager.deep_sleep(cycles=3, sleep_duration_seconds=90.0)
    assert manager.affective_space.calls == [(30.0, True), (30.0, True), (30.0, True)]
    assert abs(sum(item[0] for item in manager.affective_space.calls) - 90.0) < 1e-9

    direct = Recorder()
    manager.affective_space = direct
    manager.sleep_cycle()
    assert direct.calls == [(SECONDS_PER_SLEEP_CYCLE, True)]
