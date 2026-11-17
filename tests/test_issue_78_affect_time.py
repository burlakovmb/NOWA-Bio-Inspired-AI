"""Issue #78: affect drive is rate × dt, regulation is sign-correct, one advance per tick."""

from affective_space import AffectiveSpace, _relax_deviation
from agent import Agent
from autonomous_organism import (
    AutonomousOrganismAgent,
    DriveSystem,
    InternalSimulationLoop,
    SpeechGovernor,
)
from cortex import CortexMemory
from hippocampus import NOWAHippocampus
from intent_memory import IntentMemory
from selector import ActionSelector
from sleep import SleepManager


# A mild negative outcome stays off the norm cap. The old per-tick kick
# then pins stress near 0.8 at dt=0.1 and near 0.15 at dt=1. rate × dt
# keeps the three trajectories within this band. The residual is the
# legacy placement: the whole drive for a tick is added after retention,
# so a 1 s step and ten 0.1 s steps are not bit-identical.
DT_INVARIANCE_TOLERANCE = 0.08
HORIZON_S = 10.0


def _agent():
    hip = NOWAHippocampus(max_experiences=8)
    cortex = CortexMemory()
    intent = IntentMemory()
    sleep = SleepManager(hip, cortex, intent)
    selector = ActionSelector(actions=["go", "stop"])
    agent = Agent(hip, cortex, selector, sleep, intent, rng_seed=7)
    agent.register_action_channel("go", go_weight=0.4, nogo_weight=0.4, habit_strength=0.1)
    agent.register_action_channel("stop", go_weight=0.4, nogo_weight=0.4, habit_strength=0.1)
    agent.affective_space.legacy_compat_weight = 0.0
    agent.affective_space.constrained_recall_from_experiences = lambda experiences: {}
    agent._recall_impulses_from_experiences = lambda experiences: []
    return agent


def _commit(agent, dt, *, reward, conflict, intensity=1.0):
    agent.step(["nest"], decision_only=True, dt=dt, conflict=conflict, intensity=intensity)
    agent.commit_executed_transition(
        "go",
        reward=reward,
        context_events=["nest"],
        conflict=conflict,
        intensity=intensity,
        novelty=0.0,
    )


def _record(space):
    calls = []
    original = space.step

    def wrapped(**kwargs):
        calls.append(float(kwargs.get("time_elapsed", 1.0)))
        return original(**kwargs)

    space.step = wrapped
    return calls


def _organism(space, *, curiosity=0.02, threshold=1.0, relevance=0.0):
    loop = InternalSimulationLoop(
        affective_core=space,
        cognitive_core=None,
        decision_engine=None,
        memory_system=None,
        threshold=threshold,
    )
    return AutonomousOrganismAgent(
        affective_core=space,
        cognitive_core=None,
        decision_engine=type("D", (), {
            "speech_relevance": lambda self, active_drive=None, internal_result=None: relevance,
            "generate_speech": lambda self, active_drive=None, internal_result=None: "",
            "evaluate_internal": lambda self, active_drive=None, hypotheses=None, recalls=None: {
                "relevance_score": relevance,
                "confidence": 0.5,
            },
        })(),
        memory_system=type("M", (), {"recall_by_drive": lambda self, active_drive, limit=6: [], "update_memory_decay": lambda self, dt: None})(),
        drive_system=DriveSystem(initial_drives={"curiosity": curiosity}),
        internal_loop=loop,
        speech_governor=SpeechGovernor(),
        internal_trigger_threshold=threshold,
        time_fn=lambda: 0.0,
    )


def test_derived_stress_over_fixed_time_is_invariant_to_dt():
    stresses = []
    for dt in (0.1, 0.25, 1.0):
        agent = _agent()
        steps = int(round(HORIZON_S / dt))
        for _ in range(steps):
            _commit(agent, dt, reward=-0.05, conflict=0.0, intensity=1.0)
        stresses.append(float(agent.affective_space.axes["stress"]))
    spread = max(stresses) - min(stresses)
    assert spread < DT_INVARIANCE_TOLERANCE, (stresses, spread)
    assert min(stresses) > 0.08


def test_allostatic_map_relaxes_both_signs_toward_the_setpoint():
    for deviation in (0.6, -0.6):
        new_deviation, _baseline = _relax_deviation(
            deviation, 0.0, 1.0, 0.70, 1.0 / (6.0 * 3600.0), 0.25 / (6.0 * 3600.0)
        )
        assert abs(new_deviation) < abs(deviation)
        assert new_deviation * deviation > 0.0


def test_regulate_affect_pulls_both_signs_toward_the_setpoint_without_advancing_time():
    for sign in (1.0, -1.0):
        space = AffectiveSpace(
            baseline_setpoint={axis: 0.0 for axis in (
                "valence", "arousal", "dominance", "stress",
                "trust", "curiosity", "stability", "attachment",
            )},
            legacy_compat_weight=0.0,
            baseline_adapt_rate=0.0,
        )
        for axis in list(space.axes):
            space.axes[axis] = 0.9 if axis != "stress" else 0.9 * sign
        calls = _record(space)
        organism = _organism(space)
        before = float(space.axes["stress"])
        result = organism.regulate_affect(1.0, organism._read_affect())
        after = float(space.axes["stress"])
        assert result["regulation_active"] is True
        assert result["affect_applied"] is True
        assert abs(after) < abs(before)
        assert (after - before) * sign < 0.0
        assert calls == [0.0]


def test_organism_tick_advances_affect_once_even_with_overload_and_internal_cycle():
    space = AffectiveSpace(legacy_compat_weight=0.0, baseline_adapt_rate=0.0)
    for axis in list(space.axes):
        space.axes[axis] = 0.9
    calls = _record(space)
    organism = _organism(space, curiosity=1.0, threshold=0.05, relevance=0.0)
    tick = organism.organism_step(0.25)
    positive = [value for value in calls if value > 1e-9]
    assert tick["regulation"]["regulation_active"] is True
    assert tick["internal_cycle_triggered"] is True
    assert positive == [0.25]


def test_commit_plus_body_slices_integrate_the_host_interval_once():
    agent = _agent()
    runtime = agent.init_autonomous_runtime()
    assert runtime is not None
    calls = _record(agent.affective_space)
    _commit(agent, 1.0, reward=-0.2, conflict=0.1)
    for _ in range(4):
        runtime.organism_step(0.25)
    positive = [value for value in calls if value > 1e-9]
    assert positive == [1.0]
    assert abs(sum(positive) - 1.0) < 1e-9


def test_unmet_need_raises_stress_and_cortisol_and_relief_relaxes_them():
    """Negative outcome plus conflict is the core image of an unmet need.

    The colony's hunger variable is not part of the core. What reaches the
    affect and HPA axes is a negative reward and a conflict signal.
    """
    agent = _agent()
    stress_0 = float(agent.affective_space.axes["stress"])
    cort_0 = float(agent.neuromodulators.cortisol)
    for _ in range(8):
        _commit(agent, 1.0, reward=-0.8, conflict=0.5)
    stress_need = float(agent.affective_space.axes["stress"])
    cort_need = float(agent.neuromodulators.cortisol)
    assert stress_need > stress_0 + 0.25
    assert cort_need > cort_0 + 0.2

    for _ in range(12):
        _commit(agent, 1.0, reward=0.4, conflict=0.0)
    stress_fed = float(agent.affective_space.axes["stress"])
    cort_fed = float(agent.neuromodulators.cortisol)
    assert stress_fed < stress_need - 0.25
    assert stress_fed < 0.25
    assert cort_fed < cort_need - 0.2
    assert cort_fed < 0.2


def test_composed_tick_does_not_overdamp_an_unmet_need():
    agent = _agent()
    runtime = agent.init_autonomous_runtime()
    assert runtime is not None
    for _ in range(8):
        _commit(agent, 1.0, reward=-0.8, conflict=0.5)
        for _slice in range(4):
            runtime.organism_step(0.25)
    assert float(agent.affective_space.axes["stress"]) > 0.25
    assert float(agent.neuromodulators.cortisol) > 0.2
