"""QA pass for PR #37 (labile tier, learning guard, host clock).

Independent of tests/test_issue13_two_tier.py. Sleep capture, kappa, replay
priorities, exactly-once and habit EMA are out of scope (PR B).
"""

from __future__ import annotations

import logging
import math
import os

import pytest

from agent import Agent
from cortex import CortexMemory
from external_interaction_layer import Feedback
from hippocampus import NOWAHippocampus
from intent_memory import IntentMemory
from labile_layer import PlasticityConfig
from learning_guard import WakingLearningError, labile_snapshot, stable_fingerprint
from selector import ActionSelector
from sleep import SleepManager


def _agent(actions=("red", "green", "blue"), seed=0, wake_s=1000.0, capacity=40):
    hippocampus = NOWAHippocampus(max_experiences=capacity)
    cortex = CortexMemory()
    memory = IntentMemory()
    sleep_manager = SleepManager(hippocampus, cortex, memory)
    selector = ActionSelector(actions=list(actions))
    return Agent(
        hippocampus,
        cortex,
        selector,
        sleep_manager,
        memory,
        rng_seed=seed,
        plasticity_config=PlasticityConfig(expected_wake_interval_s=wake_s),
    )


def _q_rows(snap):
    return [(row["state_key"], row["action"], row["value"]) for row in snap["q"]]


def _channel_rows(snap):
    return [(row["action"], row["go"], row["nogo"]) for row in snap["channels"]]


def _assert_q_rows_close(left, right, *, abs: float = 1e-12) -> None:
    assert len(left) == len(right)
    for left_row, right_row in zip(left, right):
        assert left_row[0] == right_row[0]
        assert left_row[1] == right_row[1]
        assert left_row[2] == pytest.approx(right_row[2], abs=abs, rel=0)


def _assert_channel_rows_close(left, right, *, abs: float = 1e-12) -> None:
    assert len(left) == len(right)
    for left_row, right_row in zip(left, right):
        assert left_row[0] == right_row[0]
        assert left_row[1] == pytest.approx(right_row[1], abs=abs, rel=0)
        assert left_row[2] == pytest.approx(right_row[2], abs=abs, rel=0)


def test_fingerprint_holds_across_a_waking_day():
    """Rewards, override, revised feedback, queued external feedback."""
    agent = _agent(seed=1)
    before = stable_fingerprint(agent)
    visits_before = dict(agent._action_visit_counts)
    go_before = float(agent.bg_action_channels["red"].go_weight)
    for index in range(12):
        context = ["north"] if index % 2 == 0 else ["south"]
        decided = agent.step(context, decision_only=True, reward=None, dt=1.0)
        executed = "red" if index % 2 == 0 else "green"
        episode_id = agent.commit_executed_transition(
            action=executed,
            reward=1.0 if executed == "red" else -0.5,
            context_events=context,
            decided_action=decided,
            overridden=executed != decided,
            override_source="qa-override",
            terminal=True,
            dt=0.5,
        )
        agent.apply_feedback_to_last_experience(
            2 if executed == "red" else -2,
            context_events=context,
            action_id=executed,
            episode_id=episode_id,
        )
        agent.apply_feedback_to_last_experience(
            -2,
            context_events=context,
            action_id=executed,
            episode_id=episode_id,
        )
    agent._apply_external_feedback_learning(
        Feedback(reward=0.6, signal={"qa": True}, success_probability=0.8, latency=0.0),
        predicted_reward={"red": 0.1},
    )
    assert stable_fingerprint(agent) == before
    assert agent._action_visit_counts == visits_before
    assert float(agent.bg_action_channels["red"].go_weight) == pytest.approx(go_before)
    assert agent.value_layer.online_update_count == 0
    assert all(float(trace.strength) == 0.0 for trace in agent.intent_memory.traces.values())
    assert agent._pending_external_learning
    assert agent.labile.max_abs_q(agent._host_clock_s) <= 0.2 + 1e-12
    assert agent.labile.max_abs_channel(agent._host_clock_s) <= 0.1 + 1e-12


def test_rewarded_action_becomes_more_likely_inside_clamps():
    agent = _agent(("red", "green", "blue"), seed=1)
    agent.deliberative_planning_enabled = False
    agent.imagination_enabled = False
    agent.step(["north"], decision_only=True, dt=0.0)
    before = float(agent.thalamic_gate.last_probabilities.get("red", 0.0))
    for _ in range(40):
        agent.commit_executed_transition(
            action="red",
            reward=1.0,
            context_events=["north"],
            decided_action="red",
            overridden=False,
            terminal=True,
            dt=0.0,
        )
        assert agent.labile.max_abs_q(agent._host_clock_s) <= 0.2 + 1e-12
        assert agent.labile.max_abs_channel(agent._host_clock_s) <= 0.1 + 1e-12
    agent.step(["north"], decision_only=True, dt=0.0)
    after = float(agent.thalamic_gate.last_probabilities.get("red", 0.0))
    assert after > before
    # One enormous TD error cannot move L_Q by more than the step clamp,
    # and one enormous reward cannot move a channel past its amplitude.
    huge = agent.labile.apply_outcome(
        episode_id="qa-huge",
        state_key="qa-state",
        action="red",
        reward=100.0,
        td_error=100.0,
        now=agent._host_clock_s,
        g_da=1.0,
    )
    assert abs(float(huge["q_delta"])) <= 0.05 + 1e-12
    assert abs(float(huge["go_delta"])) <= 0.1 + 1e-12
    assert abs(float(huge["nogo_delta"])) <= 0.1 + 1e-12
    assert agent.labile.max_abs_q(agent._host_clock_s) <= 0.2 + 1e-12
    assert agent.labile.max_abs_channel(agent._host_clock_s) <= 0.1 + 1e-12


def test_decay_after_five_tau_and_time_slicing():
    agent = _agent(("red", "green"), seed=2, wake_s=1000.0)
    agent.commit_executed_transition(
        action="red",
        reward=1.0,
        context_events=["north"],
        decided_action="red",
        terminal=True,
        dt=0.0,
    )
    initial = agent.labile.max_abs_q(agent._host_clock_s)
    assert initial > 0.0
    tau = agent.plasticity.resolved_tau_s()
    assert tau == pytest.approx(1000.0)
    agent.advance_time(5.0 * tau)
    remaining = agent.labile.max_abs_q(agent._host_clock_s)
    assert remaining < 0.01 * initial

    def _arm(target):
        target.commit_executed_transition(
            action="red",
            reward=1.0,
            context_events=["north"],
            decided_action="red",
            terminal=True,
            dt=0.0,
        )

    whole = _agent(("red", "green"), seed=3)
    sliced = _agent(("red", "green"), seed=3)
    _arm(whole)
    _arm(sliced)
    span = 8.0
    whole.advance_time(span)
    for _ in range(4):
        sliced.advance_time(span / 4.0)
    left = labile_snapshot(whole)
    right = labile_snapshot(sliced)
    for left_row, right_row in zip(left["q"], right["q"]):
        assert left_row["value"] == pytest.approx(right_row["value"], abs=1e-12, rel=0)
        assert left_row["updated_at"] == pytest.approx(right_row["updated_at"], abs=1e-12, rel=0)
    for left_row, right_row in zip(left["channels"], right["channels"]):
        assert left_row["go"] == pytest.approx(right_row["go"], abs=1e-12, rel=0)
        assert left_row["nogo"] == pytest.approx(right_row["nogo"], abs=1e-12, rel=0)
    assert stable_fingerprint(whole) == stable_fingerprint(sliced)


def test_tau_default_is_3600_and_warns_once(caplog):
    hippocampus = NOWAHippocampus(max_experiences=8)
    cortex = CortexMemory()
    memory = IntentMemory()
    sleep_manager = SleepManager(hippocampus, cortex, memory)
    selector = ActionSelector(actions=["go"])
    with caplog.at_level(logging.WARNING, logger="nowa.plasticity"):
        agent = Agent(hippocampus, cortex, selector, sleep_manager, memory, rng_seed=0)
        agent.plasticity.resolved_tau_s()
        agent.plasticity.resolved_wake_interval_s()
    warnings = [
        rec
        for rec in caplog.records
        if "falling back to 3600" in rec.message
    ]
    assert len(warnings) == 1
    assert agent.plasticity.resolved_tau_s() == pytest.approx(3600.0)
    assert agent.plasticity.resolved_wake_interval_s() == pytest.approx(3600.0)


def test_feedback_idempotency_replacement_and_unknown_id():
    def _run(ratings, gap_s=0.0):
        agent = _agent(("go",), seed=4, wake_s=1000.0)
        agent.step(["bin"], reward=None, terminal=True, dt=0.0)
        episode_id = agent.last_episode_id
        first = True
        for rating in ratings:
            if not first and gap_s:
                agent.advance_time(gap_s)
            first = False
            agent.apply_feedback_to_last_experience(
                rating,
                context_events=["bin"],
                action_id="go",
                episode_id=episode_id,
            )
        return agent

    once = _run((2,))
    repeated = _run((2, 2, 2))
    _assert_q_rows_close(_q_rows(labile_snapshot(once)), _q_rows(labile_snapshot(repeated)))
    assert len(labile_snapshot(repeated)["contributions"]) == 1
    snap_before = labile_snapshot(repeated)
    again = repeated.apply_feedback_to_last_experience(
        2, context_events=["bin"], action_id="go", episode_id=repeated.last_episode_id
    )
    assert again["updated"] is True
    assert labile_snapshot(repeated)["q"] == snap_before["q"]

    # A changed rating, including after decay, matches one application of the
    # new rating at that same host time. The old contribution is not stacked.
    replaced = _run((2, -2), gap_s=50.0)
    direct = _agent(("go",), seed=4, wake_s=1000.0)
    direct.step(["bin"], reward=None, terminal=True, dt=0.0)
    direct.advance_time(50.0)
    direct.apply_feedback_to_last_experience(
        -2,
        context_events=["bin"],
        action_id="go",
        episode_id=direct.last_episode_id,
    )
    _assert_q_rows_close(
        _q_rows(labile_snapshot(replaced)),
        _q_rows(labile_snapshot(direct)),
    )
    _assert_channel_rows_close(
        _channel_rows(labile_snapshot(replaced)),
        _channel_rows(labile_snapshot(direct)),
    )

    frozen = labile_snapshot(replaced)
    missing = replaced.apply_feedback_to_last_experience(-2, episode_id="missing-episode")
    assert missing["updated"] is False
    assert labile_snapshot(replaced)["q"] == frozen["q"]
    assert stable_fingerprint(replaced) == stable_fingerprint(direct)


def test_save_load_legacy_empty_and_decay_continues(tmp_path):
    from storage import AgentStorage

    agent = _agent(("go", "stop"), seed=5, wake_s=1000.0)
    agent.step(["bin"], reward=1.0, terminal=True, dt=1.0)
    agent.advance_time(10.0)
    before = labile_snapshot(agent)
    assert before["q"]
    storage = AgentStorage(save_dir=str(tmp_path))
    path = storage.save_agent(
        agent.hippocampus,
        agent.cortex,
        agent.selector,
        value_layer=agent.value_layer,
        sleep_manager=agent.sleep_manager,
        agent=agent,
        filename="qa-labile.pkl",
    )
    restored = _agent(("go", "stop"), seed=5, wake_s=50.0)
    storage.load_agent(
        restored.hippocampus,
        restored.cortex,
        restored.selector,
        path,
        value_layer=restored.value_layer,
        sleep_manager=restored.sleep_manager,
        agent=restored,
    )
    assert restored.plasticity.expected_wake_interval_s == pytest.approx(1000.0)
    assert restored._host_clock_s == pytest.approx(agent._host_clock_s)
    agent.advance_time(30.0)
    restored.advance_time(30.0)
    _assert_q_rows_close(
        _q_rows(labile_snapshot(restored)),
        _q_rows(labile_snapshot(agent)),
    )
    assert labile_snapshot(restored)["q"][0]["value"] < before["q"][0]["value"]

    bare = storage.save_agent(
        agent.hippocampus,
        agent.cortex,
        agent.selector,
        agent=agent,
        filename="qa-legacy-src.pkl",
    )
    from storage import read_agent_state, write_agent_state

    payload = read_agent_state(bare)
    for key in ("labile_layer", "plasticity_config", "host_clock_s"):
        payload.pop(key, None)
    stripped = tmp_path / "qa-stripped.pkl"
    write_agent_state(stripped, payload)
    empty = _agent(("go",), seed=5, wake_s=1000.0)
    empty.step(["old"], reward=1.0, terminal=True, dt=0.0)
    assert empty.labile.max_abs_q(empty._host_clock_s) > 0.0
    kept_q = labile_snapshot(empty)["q"]
    kept_clock = empty._host_clock_s
    kept_labile = empty.labile
    storage.load_agent(
        empty.hippocampus,
        empty.cortex,
        empty.selector,
        str(stripped),
        agent=empty,
    )
    assert labile_snapshot(empty)["q"] == kept_q
    assert empty._host_clock_s == pytest.approx(kept_clock)
    assert empty.labile is kept_labile


def test_sleep_increases_stable_q_and_go_of_rewarded_action():
    agent = _agent(("go", "stop"), seed=6, wake_s=1000.0)
    agent.deliberative_planning_enabled = False
    agent.imagination_enabled = False
    for _ in range(12):
        agent.commit_executed_transition(
            action="go",
            reward=1.0,
            context_events=["north"],
            decided_action="go",
            terminal=True,
            dt=0.0,
        )
    snapshot = agent._build_value_state_snapshot(
        context_events=["north"],
        action="go",
        consequence=None,
        intensity=1.0,
        novelty=0.0,
        conflict=0.0,
    )
    assert float(agent.value_layer.get_value(snapshot)) == pytest.approx(0.0)
    assert float(agent.bg_action_channels["go"].go_weight) == pytest.approx(0.5)
    agent.sleep(cycles=3)
    assert float(agent.value_layer.get_value(snapshot)) > 0.0
    assert float(agent.bg_action_channels["go"].go_weight) > 0.5


def test_strict_guard_raises_and_production_skips_once(caplog, monkeypatch):
    agent = _agent(("go",), seed=7)
    before = stable_fingerprint(agent)
    with pytest.raises(WakingLearningError):
        agent.value_layer.update(
            state_snapshot={"context_signature": "bin", "action": "go"},
            reward=1.0,
            next_state_snapshot={"context_signature": "bin", "action": ""},
            mode="online",
        )
    assert stable_fingerprint(agent) == before

    monkeypatch.delenv("NOWA_STRICT_LEARNING", raising=False)
    monkeypatch.setenv("NOWA_STRICT_LEARNING", "0")
    # The guard reads the environment on each call. Clear the once-log so
    # this process can observe the production warning.
    import learning_guard

    learning_guard._SKIP_LOGGED.clear()
    with caplog.at_level(logging.WARNING, logger="nowa.learning"):
        first = agent.value_layer.update(
            state_snapshot={"context_signature": "bin", "action": "go"},
            reward=1.0,
            next_state_snapshot={"context_signature": "bin", "action": ""},
            mode="online",
        )
        second = agent.value_layer.update(
            state_snapshot={"context_signature": "bin", "action": "go"},
            reward=1.0,
            next_state_snapshot={"context_signature": "bin", "action": ""},
            mode="online",
        )
    assert first.get("skipped") is True
    assert second.get("skipped") is True
    assert stable_fingerprint(agent) == before
    warnings = [rec for rec in caplog.records if "ValueLayer.update skipped" in rec.message]
    assert len(warnings) == 1
    # Restore the suite default for any later test in this process.
    os.environ["NOWA_STRICT_LEARNING"] = "1"


def test_step_treats_nan_as_unknown_and_inf_as_unit():
    unknown = _agent(("go",), seed=8)
    unknown.step(["bin"], reward=float("nan"), terminal=True, dt=0.0)
    episode = unknown.hippocampus.get_experience(unknown.last_episode_id)
    assert bool(getattr(episode, "td_outcome_committed", False)) is False
    assert labile_snapshot(unknown)["q"] == []

    positive = _agent(("go",), seed=8)
    positive.step(["bin"], reward=float("inf"), terminal=True, dt=0.0)
    stored = positive.hippocampus.get_experience(positive.last_episode_id)
    assert float(stored.reward) == pytest.approx(1.0)
    assert positive.labile.max_abs_q(positive._host_clock_s) > 0.0

    negative = _agent(("go",), seed=8)
    negative.step(["bin"], reward=float("-inf"), terminal=True, dt=0.0)
    stored_neg = negative.hippocampus.get_experience(negative.last_episode_id)
    assert float(stored_neg.reward) == pytest.approx(-1.0)
