"""QA for PR #33 / issues #3, #4, #5, #6, #7, #8, #11.

These checks are the QA pass. They do not change product behavior.
A failure here is a defect against the issue DoD, not a fixture tweak.
"""

from __future__ import annotations

import json
import math
import os
import random
import subprocess
import sys
from pathlib import Path

import pytest

from learning_guard import learning_allowed

from agent import Agent
from basal_ganglia import NO_ACTION
from cortex import CortexMemory
from hippocampus import NOWAHippocampus
from intent_memory import IntentMemory
from selector import ActionSelector
from sleep import SleepManager

_SRC = Path(__file__).resolve().parents[1] / "src"
_CHANCE = 1.0 / 3.0
_MIN_ACCURACY = 0.60
_MIN_CONTEXT = 0.50


def _build_agent(actions, seed: int = 0, capacity: int = 40) -> Agent:
    hippocampus = NOWAHippocampus(max_experiences=capacity)
    cortex = CortexMemory()
    intent_memory = IntentMemory()
    sleep_manager = SleepManager(hippocampus, cortex, intent_memory)
    selector = ActionSelector(actions=list(actions))
    agent = Agent(
        hippocampus,
        cortex,
        selector,
        sleep_manager,
        intent_memory,
        rng_seed=seed,
    )
    random.seed(seed)
    return agent


def _q(agent: Agent, context, action, intensity: float = 1.0) -> float:
    snapshot = agent._build_value_state_snapshot(
        context_events=list(context),
        action=action,
        consequence=None,
        intensity=intensity,
        novelty=0.0,
        conflict=0.0,
    )
    return float(agent.value_layer.get_value(snapshot))


def _effective(agent: Agent, context, action, intensity: float = 1.0) -> float:
    snapshot = agent._build_value_state_snapshot(
        context_events=list(context),
        action=action,
        consequence=None,
        intensity=intensity,
        novelty=0.0,
        conflict=0.0,
    )
    return float(agent.effective_action_value(snapshot, action))


def _habit_strength(agent: Agent, context, action) -> float:
    memory = agent.intent_memory
    signature = memory._compute_context_signature(list(context))
    trace = memory.traces.get(f"{action}:{signature}")
    if trace is None:
        return 0.0
    return float(trace.strength)


def _run_bandit(
    actions,
    best: dict,
    seed: int,
    train_trials: int = 240,
    eval_trials: int = 80,
    noise: float = 0.0,
    noise_kind: str = "none",
    flip_prob: float = 0.0,
    frozen_eval: bool = False,
):
    """Contextual bandit. noise_kind: none | uniform | gauss | flip."""
    agent = _build_agent(actions, seed=seed, capacity=80)
    contexts = list(best.keys())
    noise_rng = random.Random(seed + 17_077)

    def _reward(context: str, action: str) -> float:
        base = 1.0 if action == best[context] else -1.0
        if noise_kind == "uniform":
            base = base + noise_rng.uniform(-noise, noise)
        elif noise_kind == "gauss":
            base = base + noise_rng.gauss(0.0, noise)
        elif noise_kind == "flip" and noise_rng.random() < flip_prob:
            base = -base
        return max(-1.0, min(1.0, base))

    def _credit(context: str, action: str, reward: float) -> None:
        # Public feedback API only accepts a quantized rating. Continuous
        # noise is applied through the same outcome helpers step()/feedback
        # use, so the learning rule itself is what is measured.
        if noise_kind in {"uniform", "gauss"}:
            episode = agent.hippocampus.get_experience(agent.last_episode_id)
            episode.reward = float(reward)
            # Same labile writer as step()/feedback. Stable weights wait for sleep.
            agent._record_known_outcome(
                context_events=[context],
                action_id=action,
                outcome=float(reward),
                episode=episode,
                state_snapshot=getattr(episode, "value_state_snapshot", None),
                next_state_snapshot=getattr(episode, "value_next_state_snapshot", None),
                next_context_events=list(getattr(episode, "value_next_context_events", None) or [context]),
                terminal=True,
            )
            return
        rating = 2 if reward > 0.0 else -2
        agent.apply_feedback_to_last_experience(
            rating,
            context_events=[context],
            action_id=action,
        )

    def _episode(context: str, learn: bool) -> bool:
        action = agent.step([context], terminal=True, decision_only=not learn)
        correct = action == best[context]
        if learn:
            _credit(context, action, _reward(context, action))
        return bool(correct)

    for trial in range(train_trials):
        _episode(contexts[trial % len(contexts)], learn=True)
        # Stable Q is learned only in sleep. The accuracy bar is unchanged.
        if (trial + 1) % 20 == 0:
            agent.sleep(cycles=3)

    per_context = {context: {"hits": 0, "total": 0} for context in contexts}
    hits = 0
    for trial in range(eval_trials):
        context = contexts[trial % len(contexts)]
        correct = _episode(context, learn=not frozen_eval)
        hits += int(correct)
        per_context[context]["hits"] += int(correct)
        per_context[context]["total"] += 1
    accuracy = hits / float(eval_trials)
    context_accuracy = {
        context: bucket["hits"] / float(bucket["total"])
        for context, bucket in per_context.items()
    }
    return {
        "accuracy": accuracy,
        "per_context": context_accuracy,
        "min_context": min(context_accuracy.values()),
        "best": best,
        "seed": seed,
        "noise_kind": noise_kind,
        "noise": noise,
        "flip_prob": flip_prob,
        "frozen_eval": frozen_eval,
    }


def _assert_beats(report: dict, min_accuracy: float = _MIN_ACCURACY, min_context: float = _MIN_CONTEXT) -> None:
    assert report["accuracy"] >= min_accuracy, (
        f"accuracy {report['accuracy']:.3f} < {min_accuracy:.3f}; "
        f"per context {report['per_context']}; case {report}"
    )
    assert report["min_context"] >= min_context, (
        f"a context stayed near chance: {report['per_context']}; case {report}"
    )


_EXTRA_CASES = (
    {"actions": ("red", "green", "blue"), "best": {"north": "green", "south": "blue"}},
    {"actions": ("red", "green", "blue"), "best": {"north": "red", "south": "red"}},
    {"actions": ("left", "stay", "right"), "best": {"day": "stay", "night": "left"}},
    {"actions": ("red", "green", "blue"), "best": {"north": "blue", "south": "blue"}},
)


def test_qa_bandit_extra_seeds_mappings_and_frozen_eval():
    """DoD #32: above chance for seeds and mappings the PR suite does not run.

    Eval here is frozen (decision_only): the official test keeps training
    during the measurement window.
    """
    failures = []
    for seed in (2, 3, 5, 8, 13, 21, 42):
        for case in _EXTRA_CASES:
            report = _run_bandit(
                case["actions"],
                case["best"],
                seed=seed,
                frozen_eval=True,
            )
            if report["accuracy"] < _MIN_ACCURACY or report["min_context"] < _MIN_CONTEXT:
                failures.append(report)
    assert not failures, "frozen bandit below chance:\n" + "\n".join(
        json.dumps(item, ensure_ascii=False) for item in failures
    )


def test_qa_bandit_extra_pythonhashseeds():
    """At least five PYTHONHASHSEED values outside the PR set {0, 1, 7}."""
    if os.environ.get("NOWA_QA_HASH_WORKER") == "1":
        payload = json.loads(os.environ["NOWA_QA_HASH_CASE"])
        report = _run_bandit(
            payload["actions"],
            payload["best"],
            seed=int(payload["seed"]),
            frozen_eval=True,
        )
        _assert_beats(report)
        return

    repo = Path(__file__).resolve().parents[1]
    cases = (
        {"actions": ["red", "green", "blue"], "best": {"north": "green", "south": "red"}, "seed": 4},
        {"actions": ["red", "green", "blue"], "best": {"north": "blue", "south": "green"}, "seed": 9},
    )
    failures = []
    for hash_seed in ("2", "3", "4", "11", "99"):
        for case in cases:
            env = os.environ.copy()
            env["PYTHONHASHSEED"] = hash_seed
            env["NOWA_QA_HASH_WORKER"] = "1"
            env["NOWA_QA_HASH_CASE"] = json.dumps(case)
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "tests/test_qa_issue32_reward_learning.py::test_qa_bandit_extra_pythonhashseeds",
                    "-q",
                    "--tb=line",
                ],
                cwd=str(repo),
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode != 0:
                tail = ((completed.stdout or "") + "\n" + (completed.stderr or ""))[-1500:]
                failures.append(f"PYTHONHASHSEED={hash_seed} case={case['best']}\n{tail}")
    assert not failures, "hash-seed bandit failed:\n\n" + "\n---\n".join(failures)


def test_qa_bandit_reward_noise_still_beats_chance():
    """Magnitude noise and occasional sign flips must stay above chance."""
    base = {"actions": ("red", "green", "blue"), "best": {"north": "red", "south": "green"}}
    reports = [
        _run_bandit(base["actions"], base["best"], seed=5, noise=0.35, noise_kind="uniform", frozen_eval=True),
        _run_bandit(base["actions"], base["best"], seed=6, noise=0.5, noise_kind="gauss", frozen_eval=True),
        _run_bandit(base["actions"], base["best"], seed=7, flip_prob=0.10, noise_kind="flip", frozen_eval=True),
    ]
    # Sign-preserving uniform noise uses the same DoD bar as the clean bandit.
    _assert_beats(reports[0])
    # Flips are harder; still required to beat a random policy, not the 0.60 bar.
    _assert_beats(reports[1], min_accuracy=0.45, min_context=0.35)
    _assert_beats(reports[2], min_accuracy=0.45, min_context=0.35)


def test_qa_same_seed_is_deterministic():
    """Two runs with the same rng_seed and random.seed match action for action."""

    def _trace(seed: int):
        agent = _build_agent(("red", "green", "blue"), seed=seed)
        actions = []
        for trial in range(40):
            context = "north" if trial % 2 == 0 else "south"
            action = agent.step([context], terminal=True)
            actions.append(action)
            rating = 2 if action == ("red" if context == "north" else "green") else -2
            agent.apply_feedback_to_last_experience(
                rating,
                context_events=[context],
                action_id=action,
            )
        return actions

    first = _trace(11)
    assert first == _trace(11)
    # A different seed may still share a prefix when the rewarded action
    # quickly dominates softmax. Equality of the same seed is the contract.


def test_qa_pythonhashseed_does_not_change_a_seeded_trace():
    """C02: the same seed must not depend on process-salted hash()."""
    script = r"""
import json, random, sys
from pathlib import Path
sys.path.insert(0, str(Path("src").resolve()))
from agent import Agent
from cortex import CortexMemory
from hippocampus import NOWAHippocampus
from intent_memory import IntentMemory
from selector import ActionSelector
from sleep import SleepManager

def build(seed):
    hip = NOWAHippocampus(max_experiences=40)
    cortex = CortexMemory()
    memory = IntentMemory()
    agent = Agent(hip, cortex, ActionSelector(actions=["red", "green", "blue"]), SleepManager(hip, cortex, memory), memory, rng_seed=seed)
    random.seed(seed)
    return agent

agent = build(5)
actions = []
for trial in range(25):
    context = "north" if trial % 2 == 0 else "south"
    action = agent.step([context], terminal=True)
    actions.append(action)
    rating = 2 if (context == "north" and action == "red") or (context == "south" and action == "green") else -2
    agent.apply_feedback_to_last_experience(rating, context_events=[context], action_id=action)
print(json.dumps(actions))
"""
    traces = []
    for hash_seed in ("0", "1", "7", "12345"):
        env = os.environ.copy()
        env["PYTHONHASHSEED"] = hash_seed
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=str(Path(__file__).resolve().parents[1]),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr[-1500:]
        traces.append(json.loads(completed.stdout.strip().splitlines()[-1]))
    assert traces[0] == traces[1] == traces[2] == traces[3]


def test_qa_feedback_addresses_episode_id_at_several_capacities():
    """C03: 0 mismatches, including capacity 1, and a stale id must not retarget."""
    for capacity in (1, 2, 40):
        agent = _build_agent(("keep", "drop"), seed=1, capacity=capacity)
        mismatches = 0
        for trial in range(120):
            context = f"ctx-{trial % 5}"
            action = agent.step([context])
            episode_id = agent.last_episode_id
            stored = agent.hippocampus.get_experience(episode_id)
            assert stored is not None
            rating = 2 if trial % 2 == 0 else -2
            tail = agent.hippocampus.experiences[-1]
            tail_reward_before = getattr(tail, "reward", None)
            tail_id = getattr(tail, "episode_id", None)
            result = agent.apply_feedback_to_last_experience(
                rating,
                context_events=[context],
                action_id=action,
                episode_id=episode_id,
            )
            expected = 1.0 if rating > 0 else -1.0
            if result["updated"] is not True or abs(float(stored.reward) - expected) > 1e-9:
                mismatches += 1
            if tail_id != episode_id and getattr(tail, "reward", None) != tail_reward_before:
                mismatches += 1
        assert mismatches == 0, f"capacity {capacity} mismatches {mismatches}"
        assert len(agent.hippocampus.experiences) <= capacity

    agent = _build_agent(("keep", "drop"), seed=2, capacity=1)
    first = agent.step(["old"])
    first_id = agent.last_episode_id
    agent.apply_feedback_to_last_experience(2, context_events=["old"], action_id=first, episode_id=first_id)
    agent.step(["new"])
    new_id = agent.last_episode_id
    other = agent.hippocampus.get_experience(new_id)
    reward_before = float(other.reward)
    missed = agent.apply_feedback_to_last_experience(
        -2,
        context_events=["old"],
        action_id=first,
        episode_id=first_id,
    )
    assert missed["updated"] is False
    assert abs(float(other.reward) - reward_before) < 1e-9
    assert agent.hippocampus.get_experience(first_id) is None


def test_qa_empty_memory_missing_reward_and_zero_reward():
    agent = _build_agent(("only",), seed=3, capacity=5)
    assert agent.hippocampus.experiences == []
    before = int(agent.value_layer.online_update_count)
    action = agent.step(["cold"])
    assert action == "only"
    assert int(agent.value_layer.online_update_count) == before
    assert agent.last_episode_id
    assert float(agent.hippocampus.get_experience(agent.last_episode_id).reward) == 0.0

    empty = agent.apply_feedback_to_last_experience(2, episode_id="missing-id")
    assert empty["updated"] is False
    assert abs(_q(agent, ["cold"], "only")) < 1e-9

    none_feedback = _build_agent(("only",), seed=3)
    none_result = none_feedback.apply_feedback_to_last_experience(2)
    assert none_result["updated"] is False

    known_zero = _build_agent(("only",), seed=4)
    zero_before = int(known_zero.value_layer.online_update_count)
    known_zero.step(["z"], reward=0.0, terminal=True)
    assert int(known_zero.value_layer.online_update_count) == zero_before
    stored_zero = known_zero.hippocampus.get_experience(known_zero.last_episode_id)
    assert bool(getattr(stored_zero, "td_outcome_committed", False)) is True
    assert math.isfinite(_effective(known_zero, ["z"], "only"))

    bad = _build_agent(("only",), seed=4)
    bad_before = int(bad.value_layer.online_update_count)
    bad.step(["z"], reward="not-a-number", terminal=True)
    assert int(bad.value_layer.online_update_count) == bad_before


def test_qa_terminal_bootstrap_is_zero_and_one_update_per_known_reward():
    agent = _build_agent(("go",), seed=1, capacity=20)
    agent.step(["start"], reward=1.0, terminal=True)
    once = int(agent.value_layer.online_update_count)
    terminal_q = _effective(agent, ["start"], "go")
    assert math.isfinite(terminal_q)
    assert terminal_q > 0.0
    assert _q(agent, ["start"], "go") == 0.0

    # Same reward delivered again through feedback must not stack a second backup.
    agent.apply_feedback_to_last_experience(
        2,
        context_events=["start"],
        action_id="go",
        episode_id=agent.last_episode_id,
    )
    assert int(agent.value_layer.online_update_count) == once
    assert abs(_effective(agent, ["start"], "go") - terminal_q) < 1e-9

    successor = _build_agent(("go",), seed=1, capacity=30)
    for _ in range(30):
        action = successor.step(["goal"], reward=1.0, terminal=True)
    assert _effective(successor, ["goal"], action) > 0.05
    successor.sleep(cycles=3)
    # Three replay cycles with alpha_sleep = 0.25 * alpha_online land near
    # 0.066. See test_td_transition. Two cycles stay near 0.044.
    assert _q(successor, ["goal"], action) > 0.05
    open_loop = _build_agent(("go",), seed=1, capacity=30)
    open_loop.step(
        ["goal"],
        reward=0.0,
        terminal=False,
    )
    # Non-terminal bootstrap of an unseen successor is 0, so one zero-reward
    # step must not invent value. A later rewarded successor is covered above.
    assert abs(_q(open_loop, ["goal"], "go")) < 1e-6


def test_qa_revising_an_older_rating_must_not_clobber_later_updates():
    """C04: one backup per transition. A later correction of an old episode
    must not rewrite the shared Q cell back to that episode's original prior.
    """
    agent = _build_agent(("go",), seed=0, capacity=90)
    first_id = None
    for index in range(70):
        action = agent.step(["bin"], terminal=True)
        episode_id = agent.last_episode_id
        if index == 0:
            first_id = episode_id
        agent.apply_feedback_to_last_experience(
            2,
            context_events=["bin"],
            action_id=action,
            episode_id=episode_id,
        )
    learned = _effective(agent, ["bin"], "go")
    assert learned > 0.15
    agent.apply_feedback_to_last_experience(
        -2,
        context_events=["bin"],
        action_id="go",
        episode_id=first_id,
    )
    revised = _effective(agent, ["bin"], "go")
    assert revised > 0.05, (
        f"revising the first +1 episode collapsed Q from {learned:.4f} to {revised:.4f}. "
        "The backup is rewritten from that episode's original prior and drops later updates of the same Q(s, a)."
    )


def test_qa_repeated_feedback_is_idempotent():
    """The same rating on the same episode must not move habits or Go/NoGo again."""
    agent = _build_agent(("go", "stop"), seed=0)
    action = agent.step(["bin"], terminal=True)
    episode_id = agent.last_episode_id
    agent.apply_feedback_to_last_experience(2, context_events=["bin"], action_id=action, episode_id=episode_id)
    go_once = float(agent.bg_action_channels[action].go_weight)
    nogo_once = float(agent.bg_action_channels[action].nogo_weight)
    habit_once = _habit_strength(agent, ["bin"], action)
    other_go = float(agent.bg_action_channels["stop"].go_weight)
    sleep_once = len(agent.bg_sleep_memories.get(action, []))
    updates_once = int(agent.value_layer.online_update_count)
    q_once = _q(agent, ["bin"], action)

    agent.apply_feedback_to_last_experience(2, context_events=["bin"], action_id=action, episode_id=episode_id)
    assert int(agent.value_layer.online_update_count) == updates_once
    assert abs(_q(agent, ["bin"], action) - q_once) < 1e-9
    assert abs(float(agent.bg_action_channels[action].go_weight) - go_once) < 1e-12
    assert abs(float(agent.bg_action_channels[action].nogo_weight) - nogo_once) < 1e-12
    assert abs(_habit_strength(agent, ["bin"], action) - habit_once) < 1e-12
    assert abs(float(agent.bg_action_channels["stop"].go_weight) - other_go) < 1e-12
    assert len(agent.bg_sleep_memories.get(action, [])) == sleep_once


def test_qa_step_reward_teaches_habits_and_channel():
    """C06/C09: a reward passed to step() is a known outcome, not only a TD target."""
    agent = _build_agent(("go", "stop"), seed=0)
    agent.step(["bin"], reward=1.0, terminal=True)
    assert "go" in agent.bg_action_channels or agent.last_action in agent.bg_action_channels
    action = agent.last_action
    channel = agent.bg_action_channels[action]
    go_eff, _nogo_eff = agent.labile.effective_channel(
        action,
        channel.go_weight,
        channel.nogo_weight,
        agent._host_clock_s,
    )
    assert go_eff > 0.5
    assert float(channel.go_weight) == pytest.approx(0.5)
    assert _habit_strength(agent, ["bin"], action) == 0.0
    # The other channel is not the one that was just rewarded.
    other = "stop" if action == "go" else "go"
    if other in agent.bg_action_channels:
        assert abs(float(agent.bg_action_channels[other].go_weight) - 0.5) < 1e-12


def test_qa_nan_reward_does_not_abort_the_step():
    """Non-finite reward must not escape step() or poison Q."""
    agent = _build_agent(("go",), seed=0)
    agent.step(["bin"], reward=float("nan"), terminal=True)
    stored = agent.hippocampus.get_experience(agent.last_episode_id)
    assert stored is not None
    assert math.isfinite(float(stored.reward))
    assert math.isfinite(_q(agent, ["bin"], "go"))
    pressures = agent.selector.compute_pressures(agent.hippocampus.experiences, [])
    assert all(math.isfinite(value) for value in pressures.values())


def test_qa_inf_reward_does_not_abort_the_step():
    agent = _build_agent(("go",), seed=0)
    agent.step(["bin"], reward=float("inf"), terminal=True)
    stored = agent.hippocampus.get_experience(agent.last_episode_id)
    assert stored is not None
    assert math.isfinite(float(stored.reward))
    assert -1.0 <= float(stored.reward) <= 1.0
    assert math.isfinite(_q(agent, ["bin"], "go"))

    negative = _build_agent(("go",), seed=0)
    negative.step(["bin"], reward=float("-inf"), terminal=True)
    assert math.isfinite(_q(negative, ["bin"], "go"))


def test_qa_single_action_and_nogo_block():
    single = _build_agent(("only",), seed=1)
    seen = []
    for _ in range(10):
        action = single.step(["ctx"], terminal=True)
        seen.append(action)
        single.apply_feedback_to_last_experience(2, context_events=["ctx"], action_id=action)
    assert seen == ["only"] * 10
    single.sleep(cycles=3)
    assert _q(single, ["ctx"], "only") > 0.05
    habit = _habit_strength(single, ["ctx"], "only")
    assert 0.0 < habit <= 1.0

    blocked = _build_agent(("a", "b"), seed=1)
    blocked.step(["ctx"], decision_only=True)
    for name in ("a", "b"):
        channel = blocked.bg_action_channels[name]
        with learning_allowed():
            channel.go_weight = 0.0
            channel.nogo_weight = 1.0
        blocked._record_action_visit(["ctx"], name)
    blocked.neuromodulators.cortisol = 1.0
    choices = [blocked.step(["ctx"], decision_only=True) for _ in range(15)]
    assert choices == [NO_ACTION] * 15

    # A positive surplus must stay selectable under stress (C09).
    from basal_ganglia import BasalGangliaGate

    gate = BasalGangliaGate(threshold=0.2)
    gated = gate.process(
        pressure_vector={"best": 0.9, "worse": 0.1},
        dopamine_level=0.0,
        cortisol_level=1.0,
        norepinephrine_level=0.2,
        aversive_signal=1.0,
        channel_modulators={
            "best": {"go_weight": 0.8, "nogo_weight": 0.2},
            "worse": {"go_weight": 0.2, "nogo_weight": 0.9},
        },
        visit_counts={"best": 4, "worse": 4},
    )
    assert gated["best"] > 0.0
    assert gate.last_nogo["worse"] > gate.last_nogo["best"]
    calm = BasalGangliaGate(threshold=0.2)
    calm.process(
        pressure_vector={"best": 0.9, "worse": 0.1},
        dopamine_level=0.0,
        cortisol_level=0.0,
        norepinephrine_level=0.2,
        aversive_signal=0.0,
        channel_modulators={
            "best": {"go_weight": 0.8, "nogo_weight": 0.2},
            "worse": {"go_weight": 0.2, "nogo_weight": 0.9},
        },
        visit_counts={"best": 4, "worse": 4},
    )
    assert gate.last_nogo["worse"] > calm.last_nogo["worse"]


def test_qa_untried_action_is_not_dropped_from_softmax():
    from basal_ganglia import BasalGangliaGate, ThalamicGate

    gate = BasalGangliaGate()
    gated = gate.process(
        pressure_vector={"old": 0.8, "new": 0.0},
        dopamine_level=0.1,
        cortisol_level=0.2,
        norepinephrine_level=0.1,
        aversive_signal=0.3,
        visit_counts={"old": 12, "new": 0},
        channel_modulators={
            "old": {"go_weight": 0.7, "nogo_weight": 0.4},
            "new": {"go_weight": 0.5, "nogo_weight": 0.5},
        },
    )
    assert gate.last_uncertainty_bonus["new"] > gate.last_uncertainty_bonus["old"]
    assert gated["new"] > 0.0
    thalamic = ThalamicGate()
    random.seed(0)
    picks = {
        thalamic.select(gated, norepinephrine_level=0.1)
        for _ in range(40)
    }
    assert "new" in picks
    assert NO_ACTION not in picks


def test_qa_habits_stay_in_unit_interval_across_affect_and_sleep():
    agent = _build_agent(("go", "stop"), seed=2, capacity=60)
    agent.affect_state.valence = 1.0
    agent.affect_state.threat = 0.0
    for _ in range(25):
        action = agent.step(["ctx"], terminal=True)
        rating = 2 if action == "go" else -2
        agent.apply_feedback_to_last_experience(rating, context_events=["ctx"], action_id=action)
    for trace in agent.intent_memory.traces.values():
        assert 0.0 <= float(trace.strength) <= 1.0
        assert math.isfinite(float(trace.strength))
    for channel in agent.bg_action_channels.values():
        assert 0.0 <= float(channel.go_weight) <= 1.0
        assert 0.0 <= float(channel.nogo_weight) <= 1.0
    q_before = _q(agent, ["ctx"], "go")
    assert q_before == pytest.approx(0.0)
    agent.sleep(cycles=3)
    for trace in agent.intent_memory.traces.values():
        assert 0.0 <= float(trace.strength) <= 1.0
        assert math.isfinite(float(trace.strength))
    q_after = _q(agent, ["ctx"], "go")
    assert math.isfinite(q_after)
    # Sleep must consolidate the rewarded sign. The old `or q_before <= 0`
    # was true for every waking agent and did not check the writer.
    assert q_after > 0.0
    assert any(float(trace.strength) > 0.0 for trace in agent.intent_memory.traces.values())


def test_qa_episode_id_survives_a_sequence_reset_like_reload():
    """C03: ids are only unique while _episode_seq keeps growing.

    Save/load does not store the counter. Resetting it the way a fresh
    process does must not make a new step reuse an id that feedback then
    writes onto the older episode.
    """
    agent = _build_agent(("go",), seed=0, capacity=20)
    first_action = agent.step(["old"], terminal=True)
    first_id = agent.last_episode_id
    agent.apply_feedback_to_last_experience(
        2,
        context_events=["old"],
        action_id=first_action,
        episode_id=first_id,
    )
    original = agent.hippocampus.get_experience(first_id)
    assert abs(float(original.reward) - 1.0) < 1e-9

    agent.hippocampus._episode_seq = 0
    agent.hippocampus._episodes_by_id = {}
    new_action = agent.step(["new"], terminal=True)
    new_id = agent.last_episode_id
    # The id issued for the first episode has to keep resolving to that episode.
    assert agent.hippocampus.get_experience(first_id) is original, (
        f"after the counter restarted, get_experience({first_id}) no longer returns the original episode "
        f"(new step issued {new_id})"
    )
    assert new_id != first_id
    reward_before = float(original.reward)
    agent.apply_feedback_to_last_experience(
        -2,
        context_events=["new"],
        action_id=new_action,
        episode_id=new_id,
    )
    assert abs(float(original.reward) - reward_before) < 1e-9
    assert agent.hippocampus.get_experience(first_id) is original


def test_qa_save_load_keeps_episode_identity(tmp_path):
    from storage import AgentStorage

    agent = _build_agent(("go", "stop"), seed=1, capacity=30)
    ids = []
    for index in range(4):
        context = f"c{index}"
        action = agent.step([context], terminal=True)
        agent.apply_feedback_to_last_experience(2, context_events=[context], action_id=action)
        ids.append(agent.last_episode_id)
    q_before = _q(agent, ["c0"], agent.hippocampus.get_experience(ids[0]).replay_action_id)

    storage = AgentStorage(save_dir=str(tmp_path))
    path = storage.save_agent(
        agent.hippocampus,
        agent.cortex,
        agent.selector,
        value_layer=agent.value_layer,
        sleep_manager=agent.sleep_manager,
        agent=agent,
        filename="qa_reward.pkl",
    )
    restored = _build_agent(("go", "stop"), seed=1, capacity=30)
    storage.load_agent(
        restored.hippocampus,
        restored.cortex,
        restored.selector,
        path,
        value_layer=restored.value_layer,
        sleep_manager=restored.sleep_manager,
        agent=restored,
    )
    loaded = restored.hippocampus.get_experience(ids[0])
    assert loaded is not None
    assert abs(float(loaded.reward) - 1.0) < 1e-9
    assert math.isfinite(_q(restored, ["c0"], loaded.replay_action_id))
    assert abs(_q(restored, ["c0"], loaded.replay_action_id) - q_before) < 1e-6

    action = restored.step(["after-load"], terminal=True)
    new_id = restored.last_episode_id
    assert new_id not in ids, (
        f"save/load restarted the episode counter: new id {new_id} collides with {ids}"
    )
    reloaded = restored.hippocampus.get_experience(ids[0])
    assert reloaded is not None
    assert abs(float(reloaded.reward) - 1.0) < 1e-9
    result = restored.apply_feedback_to_last_experience(
        -2,
        context_events=["after-load"],
        action_id=action,
        episode_id=new_id,
    )
    assert result["updated"] is True
    assert abs(float(restored.hippocampus.get_experience(ids[0]).reward) - 1.0) < 1e-9
