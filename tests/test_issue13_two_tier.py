"""Two-tier plasticity: labile tier plus sleep consolidation.

Core tests construct Agent directly. Capture, exactly-once, replay
priority and lost-episode rules are the sleep half of issue #13.
"""

from __future__ import annotations

import logging
import math
import os
import subprocess
import sys

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


def _build_agent(actions, seed=0, capacity=80, wake_s=1000.0):
    hippocampus = NOWAHippocampus(max_experiences=capacity)
    cortex = CortexMemory()
    memory = IntentMemory()
    sleep_manager = SleepManager(hippocampus, cortex, memory)
    selector = ActionSelector(actions=list(actions))
    agent = Agent(
        hippocampus,
        cortex,
        selector,
        sleep_manager,
        memory,
        rng_seed=seed,
        plasticity_config=PlasticityConfig(expected_wake_interval_s=wake_s),
    )
    return agent


def _assert_labile_q_rows_close(rows_left, rows_right, *, abs: float = 1e-12) -> None:
    assert len(rows_left) == len(rows_right)
    for row_left, row_right in zip(rows_left, rows_right):
        assert row_left["state_key"] == row_right["state_key"]
        assert row_left["action"] == row_right["action"]
        assert row_left["value"] == pytest.approx(row_right["value"], abs=abs, rel=0)
        assert row_left["updated_at"] == pytest.approx(row_right["updated_at"], abs=abs, rel=0)


def _assert_labile_channels_close(rows_left, rows_right, *, abs: float = 1e-12) -> None:
    assert len(rows_left) == len(rows_right)
    for row_left, row_right in zip(rows_left, rows_right):
        assert row_left["action"] == row_right["action"]
        assert row_left["go"] == pytest.approx(row_right["go"], abs=abs, rel=0)
        assert row_left["nogo"] == pytest.approx(row_right["nogo"], abs=abs, rel=0)
        assert row_left["updated_at"] == pytest.approx(row_right["updated_at"], abs=abs, rel=0)


def _assert_bg_channel_map_close(left, right, *, abs: float = 1e-9) -> None:
    assert left.keys() == right.keys()
    for name in left:
        left_tuple = left[name]
        right_tuple = right[name]
        assert len(left_tuple) == len(right_tuple)
        for left_value, right_value in zip(left_tuple, right_tuple):
            assert left_value == pytest.approx(right_value, abs=abs, rel=0)


def _positive_strengths(agent):
    traces = getattr(agent.intent_memory, "traces", {}) or {}
    return {
        key: float(trace.strength)
        for key, trace in traces.items()
        if float(getattr(trace, "strength", 0.0)) > 0.0
    }


def test_stable_fingerprint_is_unchanged_across_waking_calls():
    """Invariant W: rewards, overrides, feedback revisions and external hooks."""
    agent = _build_agent(("red", "green", "blue"), seed=3)
    before = stable_fingerprint(agent)
    for index in range(40):
        context = ["north" if index % 2 == 0 else "south"]
        decided = agent.step(context, decision_only=True, reward=None, dt=1.0)
        executed = "red" if index % 3 else "green"
        episode_id = agent.commit_executed_transition(
            action=executed,
            reward=1.0 if executed == "red" else -1.0,
            context_events=context,
            decided_action=decided,
            overridden=executed != decided,
            override_source="test-override",
            terminal=True,
            dt=0.0,
        )
        assert episode_id
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
        Feedback(reward=0.8, signal={"ok": True}, success_probability=0.9, latency=0.0),
        predicted_reward={"red": 0.2},
    )
    assert stable_fingerprint(agent) == before
    assert agent.value_layer.online_update_count == 0
    assert _positive_strengths(agent) == {}
    with pytest.raises(WakingLearningError):
        agent.value_layer.update(
            state_snapshot={"context_signature": "north", "action": "red"},
            reward=1.0,
            next_state_snapshot={"context_signature": "north", "action": ""},
            mode="online",
        )
    with pytest.raises(WakingLearningError):
        agent.intent_memory.apply_outcome(["north"], "red", 1.0)
    with pytest.raises(WakingLearningError):
        agent.bg_action_channels["red"].update_weights(go_delta=0.1)
    with pytest.raises(WakingLearningError):
        agent.external_interaction_layer.apply_learning_hooks(
            feedback=Feedback(reward=1.0, signal={}, success_probability=1.0, latency=0.0),
            strategies={"red": 0.5, "green": 0.5},
        )


def test_labile_offsets_change_choice_and_stay_inside_clamps():
    agent = _build_agent(("red", "green", "blue"), seed=1)
    agent.deliberative_planning_enabled = False
    agent.imagination_enabled = False
    agent.step(["north"], decision_only=True, dt=0.0)
    before = float(agent.thalamic_gate.last_probabilities.get("red", 0.0))
    for _ in range(100):
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
    assert _positive_strengths(agent) == {}
    assert abs(agent.bg_action_channels["red"].go_weight - 0.5) < 1e-12


def test_waking_outcomes_do_not_change_habit_strength():
    agent = _build_agent(("eat", "hide"), seed=2)
    context = ["zone:floor", "hunger_high"]
    agent.step(context, reward=1.0, terminal=True, dt=1.0)
    agent.apply_feedback_to_last_experience(2, context_events=context, action_id=agent.last_action)
    for trace in agent.intent_memory.traces.values():
        assert float(trace.strength) == 0.0
    assert agent.intent_memory.traces


def test_labile_decays_without_sleep_and_policy_matches_stable():
    agent = _build_agent(("red", "green"), seed=4, wake_s=1000.0)
    agent.deliberative_planning_enabled = False
    agent.imagination_enabled = False
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
    agent.advance_time(5.0 * tau)
    remaining = agent.labile.max_abs_q(agent._host_clock_s)
    assert remaining < 0.01 * initial
    snapshot = agent._build_value_state_snapshot(
        context_events=["north"],
        action="red",
        consequence=None,
        intensity=1.0,
        novelty=0.0,
        conflict=0.0,
    )
    stable = float(agent.value_layer.get_value(snapshot))
    # 5·τ leaves less than 1% of the waking offset, so the policy input
    # matches the stable value at that same tolerance.
    assert abs(agent.effective_action_value(snapshot, "red") - stable) < 0.01 * initial
    go, nogo = agent.labile.effective_channel(
        "red",
        agent.bg_action_channels["red"].go_weight,
        agent.bg_action_channels["red"].nogo_weight,
        agent._host_clock_s,
    )
    initial_go = 0.02 * math.exp(0.0)
    assert abs(go - agent.bg_action_channels["red"].go_weight) < 0.01 * initial_go
    assert abs(nogo - agent.bg_action_channels["red"].nogo_weight) < 0.01 * initial_go


def test_decay_does_not_depend_on_how_time_is_sliced():
    def _arm(agent):
        agent.commit_executed_transition(
            action="red",
            reward=1.0,
            context_events=["north"],
            decided_action="red",
            terminal=True,
            dt=0.0,
        )

    left = _build_agent(("red", "green"), seed=5)
    right = _build_agent(("red", "green"), seed=5)
    _arm(left)
    _arm(right)
    left.advance_time(1.0)
    for _ in range(4):
        right.advance_time(0.25)
    def _close(rows_left, rows_right, fields):
        assert len(rows_left) == len(rows_right)
        for row_left, row_right in zip(rows_left, rows_right):
            for field in fields:
                left_value = row_left[field]
                right_value = row_right[field]
                if isinstance(left_value, float):
                    assert left_value == pytest.approx(right_value, abs=1e-12, rel=0)
                else:
                    assert left_value == right_value

    left_snap = labile_snapshot(left)
    right_snap = labile_snapshot(right)
    _close(left_snap["q"], right_snap["q"], ("state_key", "action", "value", "updated_at"))
    _close(left_snap["channels"], right_snap["channels"], ("action", "go", "nogo", "updated_at"))
    assert stable_fingerprint(left) == stable_fingerprint(right)


def test_feedback_is_idempotent_and_a_changed_rating_replaces():
    def _once(ratings):
        agent = _build_agent(("go",), seed=6)
        agent.step(["bin"], reward=None, terminal=True, dt=0.0)
        episode_id = agent.last_episode_id
        for rating in ratings:
            agent.apply_feedback_to_last_experience(
                rating,
                context_events=["bin"],
                action_id="go",
                episode_id=episode_id,
            )
        return agent

    single = _once((2,))
    repeated = _once((2, 2, 2))
    _assert_labile_q_rows_close(labile_snapshot(single)["q"], labile_snapshot(repeated)["q"])
    assert len(labile_snapshot(repeated)["contributions"]) == 1
    assert stable_fingerprint(single) == stable_fingerprint(repeated)

    replaced = _once((2, -2))
    direct = _once((-2,))
    _assert_labile_q_rows_close(labile_snapshot(replaced)["q"], labile_snapshot(direct)["q"])
    _assert_labile_channels_close(
        labile_snapshot(replaced)["channels"],
        labile_snapshot(direct)["channels"],
    )
    missing = replaced.apply_feedback_to_last_experience(-2, episode_id="missing-episode")
    assert missing["updated"] is False


def test_save_load_restores_labile_clock_and_config(tmp_path):
    from storage import AgentStorage

    agent = _build_agent(("go", "stop"), seed=7, wake_s=1000.0)
    agent.step(["bin"], reward=1.0, terminal=True, dt=1.0)
    agent.advance_time(10.0)
    storage = AgentStorage(save_dir=str(tmp_path))
    path = storage.save_agent(
        agent.hippocampus,
        agent.cortex,
        agent.selector,
        value_layer=agent.value_layer,
        sleep_manager=agent.sleep_manager,
        agent=agent,
        filename="labile.pkl",
    )
    restored = _build_agent(("go", "stop"), seed=7, wake_s=50.0)
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
    _assert_labile_q_rows_close(labile_snapshot(restored)["q"], labile_snapshot(agent)["q"])
    agent.advance_time(25.0)
    restored.advance_time(25.0)
    _assert_labile_q_rows_close(labile_snapshot(restored)["q"], labile_snapshot(agent)["q"])

    legacy = _build_agent(("go",), seed=1)
    legacy.step(["old"], reward=1.0, terminal=True, dt=0.0)
    # Optional labile fields may be absent. Their absence leaves the live layer.
    bare = storage.save_agent(
        legacy.hippocampus,
        legacy.cortex,
        legacy.selector,
        agent=legacy,
        filename="legacy.pkl",
    )
    from storage import read_agent_state, write_agent_state

    payload = read_agent_state(bare)
    payload.pop("labile_layer", None)
    payload.pop("plasticity_config", None)
    payload.pop("host_clock_s", None)
    stripped = tmp_path / "stripped.pkl"
    write_agent_state(stripped, payload)
    empty = _build_agent(("go",), seed=1, wake_s=1000.0)
    storage.load_agent(
        empty.hippocampus,
        empty.cortex,
        empty.selector,
        str(stripped),
        agent=empty,
    )
    assert labile_snapshot(empty)["q"] == []
    assert empty._host_clock_s == pytest.approx(0.0)

def test_load_rebinds_sleep_manager_and_consolidates_restored_labile(tmp_path):
    """A loaded labile layer is the one sleep consolidates.

    ``load_agent`` replaces ``agent.labile`` and ``agent.plasticity`` when
    the file has them. The manager must see those objects. A file that
    omits ``labile_layer`` keeps the live layer. One undecayed +1 moves
    Go 0.50 -> 0.58 only if the restored tag is captured; a fresh layer
    with no tags leaves the sleep-rate step alone (0.50 -> 0.57).
    """
    from storage import AgentStorage, read_agent_state, write_agent_state

    agent = _build_agent(("go",), seed=1, wake_s=1000.0)
    agent.sleep_manager.decay_rate_sleep = 0.0
    episode_id = agent.commit_executed_transition(
        action="go",
        reward=1.0,
        context_events=["bin"],
        decided_action="go",
        terminal=True,
        dt=0.0,
    )
    assert agent.labile._contributions
    assert agent.sleep_manager.labile is agent.labile

    storage = AgentStorage(save_dir=str(tmp_path))
    path = storage.save_agent(
        agent.hippocampus,
        agent.cortex,
        agent.selector,
        value_layer=agent.value_layer,
        sleep_manager=agent.sleep_manager,
        agent=agent,
        filename="rebind.pkl",
    )
    restored = _build_agent(("go",), seed=9, wake_s=50.0)
    stale_labile = restored.labile
    stale_plasticity = restored.plasticity
    storage.load_agent(
        restored.hippocampus,
        restored.cortex,
        restored.selector,
        path,
        value_layer=restored.value_layer,
        sleep_manager=restored.sleep_manager,
        agent=restored,
    )
    assert restored.labile is not stale_labile
    assert restored.plasticity is not stale_plasticity
    assert restored.sleep_manager.labile is restored.labile
    assert restored.sleep_manager.plasticity is restored.plasticity
    assert restored.labile.config is restored.plasticity
    assert restored.sleep_manager._host_agent is restored
    assert restored.plasticity.expected_wake_interval_s == pytest.approx(1000.0)
    assert restored.labile._contributions
    assert episode_id in restored.labile._contributions

    stats = restored.sleep(cycles=1)
    assert not stats.get("error")
    assert restored.bg_action_channels["go"].go_weight == pytest.approx(0.58, abs=1e-9)
    assert restored.labile._contributions == {}
    assert restored.hippocampus.get_experience(episode_id).consolidated is True
    assert restored.sleep_manager.labile is restored.labile
    assert restored.sleep_manager.plasticity is restored.plasticity
    assert _stable_q(restored, ["bin"], "go") > 0.0

    payload = read_agent_state(path)
    assert isinstance(payload.get("labile_layer"), dict)
    payload.pop("labile_layer", None)
    stripped = tmp_path / "no-labile-layer.pkl"
    write_agent_state(stripped, payload)

    legacy = _build_agent(("go",), seed=3, wake_s=50.0)
    legacy.sleep_manager.decay_rate_sleep = 0.0
    previous_labile = legacy.labile
    storage.load_agent(
        legacy.hippocampus,
        legacy.cortex,
        legacy.selector,
        str(stripped),
        value_layer=legacy.value_layer,
        agent=legacy,
    )
    assert legacy.labile is previous_labile
    assert legacy.labile._contributions == {}
    assert labile_snapshot(legacy)["q"] == []
    assert legacy.sleep_manager.labile is legacy.labile
    assert legacy.sleep_manager.plasticity is legacy.plasticity
    assert legacy.labile.config is legacy.plasticity
    assert legacy.sleep_manager._host_agent is legacy
    assert legacy.plasticity.expected_wake_interval_s == pytest.approx(1000.0)

    legacy_stats = legacy.sleep(cycles=1)
    assert not legacy_stats.get("error")
    assert legacy.bg_action_channels["go"].go_weight == pytest.approx(0.57, abs=1e-9)
    assert legacy.labile._contributions == {}
    assert legacy.sleep_manager.labile is legacy.labile


def test_sleep_rebinds_manager_when_the_agent_layer_was_replaced():
    """``Agent.sleep`` consolidates the agent's current labile layer."""
    from labile_layer import LabileLayer

    agent = _build_agent(("go",), seed=1)
    agent.sleep_manager.decay_rate_sleep = 0.0
    replacement = LabileLayer(agent.plasticity)
    agent.labile = replacement
    assert agent.sleep_manager.labile is not replacement

    stats = agent.sleep(cycles=1)
    assert not stats.get("error")
    assert agent.sleep_manager.labile is replacement
    assert agent.sleep_manager.plasticity is agent.plasticity
    assert agent.sleep_manager._host_agent is agent

def test_load_keeps_a_foreign_sleep_manager_host(tmp_path):
    """A shared manager keeps a host that is not the object passed as ``agent``.

    Tamagochi loads through the cage (``agent=self``) while ``_host_agent``
    stays the cognitive host. Labile and plasticity still move to the
    restored objects; the host pointer is left for the cage's own rewire.
    """
    from storage import AgentStorage

    source = _build_agent(("go",), seed=1, wake_s=1000.0)
    source.commit_executed_transition(
        action="go",
        reward=1.0,
        context_events=["bin"],
        decided_action="go",
        terminal=True,
        dt=0.0,
    )
    storage = AgentStorage(save_dir=str(tmp_path))
    path = storage.save_agent(
        source.hippocampus,
        source.cortex,
        source.selector,
        value_layer=source.value_layer,
        sleep_manager=source.sleep_manager,
        agent=source,
        filename="cage.pkl",
    )

    class _Cage:
        pass

    cognitive = _build_agent(("go",), seed=4, wake_s=1000.0)
    cage = _Cage()
    cage.sleep_manager = cognitive.sleep_manager
    cage.hippocampus = cognitive.hippocampus
    cage.cortex = cognitive.cortex
    cage.selector = cognitive.selector
    cage.value_layer = cognitive.value_layer
    cage.labile = cognitive.labile
    cage.plasticity = cognitive.plasticity
    assert cognitive.sleep_manager._host_agent is cognitive

    storage.load_agent(
        cage.hippocampus,
        cage.cortex,
        cage.selector,
        path,
        value_layer=cage.value_layer,
        sleep_manager=cage.sleep_manager,
        agent=cage,
    )
    assert cage.labile is not cognitive.labile
    assert cage.sleep_manager.labile is cage.labile
    assert cage.sleep_manager.plasticity is cage.plasticity
    assert cage.labile._contributions
    assert cage.sleep_manager._host_agent is cognitive


def test_missing_dt_warns_once_and_explicit_dt_ignores_wall_clock(caplog, monkeypatch):
    agent = _build_agent(("go",), seed=8)
    monkeypatch.setattr("agent.time.time", lambda: 10_000.0)
    with caplog.at_level(logging.WARNING, logger="nowa.plasticity"):
        agent.step(["bin"], reward=1.0, terminal=True)
        agent.step(["bin"], reward=1.0, terminal=True)
    dt_warnings = [rec for rec in caplog.records if "falling back to the wall clock" in rec.message]
    assert len(dt_warnings) == 1

    clocked = _build_agent(("go",), seed=8)
    monkeypatch.setattr("agent.time.time", lambda: 50_000.0)
    clocked.step(["bin"], reward=1.0, terminal=True, dt=2.5)
    clocked.step(["bin"], reward=-1.0, terminal=True, dt=1.5)
    assert clocked._host_clock_s == pytest.approx(4.0)


def test_tau_follows_expected_wake_interval():
    short = PlasticityConfig(expected_wake_interval_s=1000.0)
    long = PlasticityConfig(expected_wake_interval_s=2000.0)
    assert short.resolved_tau_s() == pytest.approx(1000.0)
    assert long.resolved_tau_s() == pytest.approx(2.0 * short.resolved_tau_s())
    unset = PlasticityConfig()
    assert unset.resolved_wake_interval_s() == pytest.approx(3600.0)
    assert unset.resolved_tau_s() == pytest.approx(3600.0)


def test_eta_q_defaults_to_one_tenth_of_stable_alpha():
    agent = _build_agent(("go",), seed=0)
    alpha = float(agent.value_layer.alpha_default)
    assert agent.plasticity.resolved_eta_q() == pytest.approx(0.1 * alpha)
    assert agent.plasticity.capture_kappa == pytest.approx(0.5)
    assert agent.plasticity.replay_priority_weights == pytest.approx((1.0, 0.5, 0.25, 0.25))


def test_labile_snapshot_is_deterministic_across_pythonhashseed():
    first = _build_agent(("red", "green", "blue"), seed=11)
    second = _build_agent(("red", "green", "blue"), seed=11)
    for agent in (first, second):
        agent.deliberative_planning_enabled = False
        agent.imagination_enabled = False
        for _ in range(8):
            action = agent.step(["north"], terminal=True, dt=1.0)
            reward = 1.0 if action == "red" else -1.0
            agent.apply_feedback_to_last_experience(
                2 if reward > 0 else -2,
                context_events=["north"],
                action_id=action,
            )
    assert labile_snapshot(first) == labile_snapshot(second)

    repo = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    inline = (
        "import json,sys\n"
        "sys.path.insert(0,'src')\n"
        "from labile_layer import PlasticityConfig\n"
        "from agent import Agent\n"
        "from cortex import CortexMemory\n"
        "from hippocampus import NOWAHippocampus\n"
        "from intent_memory import IntentMemory\n"
        "from selector import ActionSelector\n"
        "from sleep import SleepManager\n"
        "from learning_guard import labile_snapshot\n"
        "hip=NOWAHippocampus(max_experiences=40)\n"
        "cortex=CortexMemory(); mem=IntentMemory()\n"
        "sm=SleepManager(hip, cortex, mem)\n"
        "sel=ActionSelector(actions=['red','green','blue'])\n"
        "agent=Agent(hip, cortex, sel, sm, mem, rng_seed=11, plasticity_config=PlasticityConfig(expected_wake_interval_s=1000.0))\n"
        "agent.deliberative_planning_enabled=False\n"
        "agent.imagination_enabled=False\n"
        "for _ in range(6):\n"
        "    action=agent.step(['north'], terminal=True, dt=1.0)\n"
        "    agent.apply_feedback_to_last_experience(2 if action=='red' else -2, context_events=['north'], action_id=action)\n"
        "print(json.dumps(labile_snapshot(agent), sort_keys=True))\n"
    )
    outputs = []
    for hash_seed in ("0", "1", "7"):
        env = os.environ.copy()
        env["PYTHONHASHSEED"] = hash_seed
        env["NOWA_STRICT_LEARNING"] = "1"
        completed = subprocess.run(
            [sys.executable, "-c", inline],
            cwd=repo,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr[-2000:]
        outputs.append(completed.stdout.strip())
    assert outputs[0] == outputs[1] == outputs[2]


def _stable_q(agent, context, action) -> float:
    snapshot = agent._build_value_state_snapshot(
        context_events=list(context),
        action=action,
        consequence=None,
        intensity=1.0,
        novelty=0.0,
        conflict=0.0,
    )
    return float(agent.value_layer.get_value(snapshot))


def _habit(agent, action) -> float:
    traces = getattr(agent.intent_memory, "traces", {}) or {}
    best = 0.0
    for trace in traces.values():
        if str(getattr(trace, "intent_type", "")) != str(action):
            continue
        best = max(best, float(getattr(trace, "strength", 0.0)))
    return best


def test_one_episode_moves_go_by_exactly_0_08_and_replay_writes_only_q():
    """Replay must not add a second Go step on top of capture.

    One terminal +1, decay forced to 0: Go 0.50 -> 0.58 for both
    sleep(cycles=1) and sleep(cycles=3). Q still rises from replay.
    """
    def _run(cycles: int):
        agent = _build_agent(("go",), seed=1)
        agent.sleep_manager.decay_rate_sleep = 0.0
        agent.commit_executed_transition(
            action="go",
            reward=1.0,
            context_events=["bin"],
            decided_action="go",
            terminal=True,
            dt=0.0,
        )
        stats = agent.sleep(cycles=cycles)
        return agent, stats

    once, stats_once = _run(1)
    assert once.bg_action_channels["go"].go_weight == pytest.approx(0.58, abs=1e-9)
    assert _stable_q(once, ["bin"], "go") > 0.0
    assert stats_once["total_replays"] > 0
    assert float(stats_once.get("total_bg_delta_sleep", 0.0)) == pytest.approx(0.0)

    triple, stats_triple = _run(3)
    assert triple.bg_action_channels["go"].go_weight == pytest.approx(0.58, abs=1e-9)
    assert _stable_q(triple, ["bin"], "go") > _stable_q(once, ["bin"], "go")
    assert stats_triple["total_replays"] > stats_once["total_replays"]


def test_direct_replay_does_not_open_the_learning_guard(monkeypatch, caplog):
    agent = _build_agent(("go",), seed=2)
    episode_id = agent.commit_executed_transition(
        action="go",
        reward=1.0,
        context_events=["bin"],
        decided_action="go",
        terminal=True,
        dt=0.0,
    )
    episode = agent.hippocampus.get_experience(episode_id)
    before = stable_fingerprint(agent)
    with pytest.raises(WakingLearningError):
        agent.sleep_manager._apply_replay_td_bg([episode])
    assert stable_fingerprint(agent) == before
    assert _stable_q(agent, ["bin"], "go") == pytest.approx(0.0)
    assert episode.consolidated is not True

    monkeypatch.setenv("NOWA_STRICT_LEARNING", "0")
    with caplog.at_level(logging.WARNING, logger="nowa.learning"):
        skipped = agent.sleep_manager._apply_replay_td_bg([episode])
    assert skipped["replays_applied"] == 0
    assert stable_fingerprint(agent) == before
    assert any("SleepManager._apply_replay_td_bg" in record.message for record in caplog.records)


def test_sleep_moves_stable_q_habits_and_channels_in_the_outcome_direction():
    """Rewarded (c, a) rises; punished falls; consolidated tags are cleared."""
    agent = _build_agent(("go", "stop"), seed=1)
    for _ in range(8):
        agent.commit_executed_transition(
            action="go",
            reward=1.0,
            context_events=["good"],
            decided_action="go",
            terminal=True,
            dt=0.0,
        )
    for _ in range(8):
        agent.commit_executed_transition(
            action="stop",
            reward=-1.0,
            context_events=["bad"],
            decided_action="stop",
            terminal=True,
            dt=0.0,
        )
    go_before = float(agent.bg_action_channels["go"].go_weight)
    nogo_before = float(agent.bg_action_channels["go"].nogo_weight)
    stop_go_before = float(agent.bg_action_channels["stop"].go_weight)
    stop_nogo_before = float(agent.bg_action_channels["stop"].nogo_weight)
    agent.sleep(cycles=3)
    assert _stable_q(agent, ["good"], "go") > 0.0
    assert _stable_q(agent, ["bad"], "stop") < 0.0
    assert float(agent.bg_action_channels["go"].go_weight) > go_before
    assert float(agent.bg_action_channels["go"].nogo_weight) < nogo_before
    assert float(agent.bg_action_channels["stop"].go_weight) < stop_go_before
    assert float(agent.bg_action_channels["stop"].nogo_weight) > stop_nogo_before
    assert _habit(agent, "go") > _habit(agent, "stop")
    assert _habit(agent, "go") > 0.0
    assert agent.labile.max_abs_q(agent._host_clock_s) == pytest.approx(0.0, abs=1e-9)
    assert agent.labile.max_abs_channel(agent._host_clock_s) == pytest.approx(0.0, abs=1e-9)
    for episode in agent.hippocampus.experiences:
        assert bool(getattr(episode, "consolidated", False)) is True
        assert getattr(episode, "episode_id", None) not in agent.labile._contributions


def test_second_sleep_matches_shy_only_control():
    """A second sleep without new episodes does not learn them again."""
    from copy import copy

    from learning_guard import learning_allowed

    agent = _build_agent(("go",), seed=2)
    for _ in range(6):
        agent.commit_executed_transition(
            action="go",
            reward=1.0,
            context_events=["bin"],
            decided_action="go",
            terminal=True,
            dt=0.0,
        )
    agent.sleep(cycles=2)
    control = _build_agent(("go",), seed=2)
    with learning_allowed():
        for key, value in list(agent.value_layer.values.items()):
            control.value_layer._set_value(str(key), float(value))
        for name, channel in agent.bg_action_channels.items():
            other = control.bg_action_channels[name]
            other.go_weight = float(channel.go_weight)
            other.nogo_weight = float(channel.nogo_weight)
            other.habit_strength = float(channel.habit_strength)
            other.prior_go = float(channel.prior_go)
            other.prior_nogo = float(channel.prior_nogo)
            other.prior_habit = float(channel.prior_habit)
    control.intent_memory.traces = {
        key: copy(trace) for key, trace in agent.intent_memory.traces.items()
    }
    agent.sleep_manager._rng.seed(0)
    control.sleep_manager._rng.seed(0)
    agent.sleep(cycles=2)
    control.sleep(cycles=2)

    def _channels(subject):
        return {
            name: (
                float(channel.go_weight),
                float(channel.nogo_weight),
                float(channel.habit_strength),
            )
            for name, channel in subject.bg_action_channels.items()
        }

    _assert_bg_channel_map_close(_channels(agent), _channels(control))
    assert _stable_q(agent, ["bin"], "go") == pytest.approx(_stable_q(control, ["bin"], "go"), abs=1e-9)
    left = {key: float(trace.strength) for key, trace in agent.intent_memory.traces.items()}
    right = {key: float(trace.strength) for key, trace in control.intent_memory.traces.items()}
    assert left.keys() == right.keys()
    for key in left:
        assert left[key] == pytest.approx(right[key], abs=1e-9)


def test_evicted_unconsolidated_episode_does_not_change_stable_q():
    agent = _build_agent(("red", "green"), seed=3, capacity=1)
    agent.commit_executed_transition(
        action="red",
        reward=1.0,
        context_events=["north"],
        decided_action="red",
        terminal=True,
        dt=0.0,
    )
    evicted_id = agent.last_episode_id
    agent.commit_executed_transition(
        action="green",
        reward=1.0,
        context_events=["south"],
        decided_action="green",
        terminal=True,
        dt=0.0,
    )
    assert agent.hippocampus.get_experience(evicted_id) is None
    assert agent.lost_unconsolidated == 1
    assert evicted_id not in agent.labile._contributions
    agent.sleep(cycles=2)
    assert _stable_q(agent, ["north"], "red") == pytest.approx(0.0, abs=1e-9)
    assert _stable_q(agent, ["south"], "green") > 0.0


def test_replay_priority_follows_weights_and_breaks_ties_by_episode_id():
    agent = _build_agent(("go",), seed=4)
    made = []
    for novelty, emotion, reward in ((0.0, 0.0, 1.0), (1.0, 0.0, 0.2), (0.0, 1.0, 0.2)):
        agent.commit_executed_transition(
            action="go",
            reward=reward,
            context_events=["bin"],
            decided_action="go",
            terminal=True,
            novelty=novelty,
            intensity=emotion * 2.0,
            dt=0.0,
        )
        episode = agent.hippocampus.get_experience(agent.last_episode_id)
        episode.novelty = float(novelty)
        episode.emotional_salience = float(emotion)
        made.append(episode)
    order = agent.sleep_manager.consolidation_order(made)
    scores = [agent.sleep_manager.spec_replay_priority(exp) for exp in order]
    assert scores == sorted(scores, reverse=True)
    assert order[0] is made[0]
    # |δ| and |r| match for the last two; novelty outranks emotion at the default weights
    # only if its coefficient wins. Force novelty-only weights and check the order.
    agent.plasticity.replay_priority_weights = (0.0, 0.0, 1.0, 0.0)
    novelty_order = agent.sleep_manager.consolidation_order(made)
    assert novelty_order[0] is made[1]
    agent.plasticity.replay_priority_weights = (0.0, 0.0, 0.0, 0.0)
    tied = agent.sleep_manager.consolidation_order(made)
    assert [exp.episode_id for exp in tied] == sorted(exp.episode_id for exp in made)


def test_waking_guard_blocks_direct_stable_writes():
    agent = _build_agent(("go",), seed=5)
    before = stable_fingerprint(agent)
    channel = agent.bg_action_channels["go"]
    with pytest.raises(WakingLearningError):
        channel.go_weight = 0.9
    with pytest.raises(WakingLearningError):
        agent.value_layer._set_value("state", 0.4)
    with pytest.raises(WakingLearningError):
        agent.bg_learning.apply_sleep_learning(
            [channel],
            {"go": [(1.0, 0.8, 0.1, 0.2)]},
            agent.neuromodulators,
            forget_rate=0.0,
        )
    with pytest.raises(WakingLearningError):
        agent.bg_learning.consolidate_habits([channel], serotonin=1.0)
    agent.register_action_channel("seeded", go_weight=0.8, habit_strength=0.3)
    assert agent.bg_action_channels["seeded"].go_weight == pytest.approx(0.8)
    assert stable_fingerprint(agent) != before
    assert channel.go_weight == pytest.approx(0.5)


def test_feedback_nan_is_unknown_and_inf_is_unit_reward():
    agent = _build_agent(("go",), seed=6)
    agent.step(["bin"], reward=None, terminal=True, dt=0.0)
    episode_id = agent.last_episode_id
    before = labile_snapshot(agent)
    missing = agent.apply_feedback_to_last_experience(float("nan"), episode_id=episode_id)
    assert missing["updated"] is False
    assert labile_snapshot(agent) == before
    applied = agent.apply_feedback_to_last_experience(float("inf"), episode_id=episode_id)
    assert applied["updated"] is True
    assert applied["reward_signal"] == pytest.approx(1.0)
    stored = agent.hippocampus.get_experience(episode_id)
    assert float(stored.reward) == pytest.approx(1.0)
    negative = _build_agent(("go",), seed=6)
    negative.step(["bin"], reward=None, terminal=True, dt=0.0)
    negative.apply_feedback_to_last_experience(float("-inf"), episode_id=negative.last_episode_id)
    assert float(negative.hippocampus.get_experience(negative.last_episode_id).reward) == pytest.approx(-1.0)


def test_labile_visits_transfer_into_stable_counts_during_sleep():
    agent = _build_agent(("go",), seed=7)
    for _ in range(4):
        agent.commit_executed_transition(
            action="go",
            reward=1.0,
            context_events=["bin"],
            decided_action="go",
            terminal=True,
            dt=0.0,
        )
    for _ in range(4):
        agent._record_action_visit(["bin"], "go")
    key = ("bin", "go")
    assert agent.labile.visit_count("bin", "go") == pytest.approx(4.0)
    assert agent._action_visit_counts.get(key, 0) == 0
    agent.sleep(cycles=1)
    assert agent.labile.visit_count("bin", "go") == pytest.approx(0.0)
    assert int(agent._action_visit_counts.get(key, 0)) >= 4


def test_slow_affect_stays_fixed_until_sleep():
    agent = _build_agent(("go",), seed=8)
    before = stable_fingerprint(agent)
    for _ in range(4):
        agent.step(["bin"], reward=1.0, novelty=0.8, conflict=0.6, terminal=True, dt=1.0)
    assert stable_fingerprint(agent) == before
    assert agent.semantic_emotions.snapshot() == []
    assert agent._pending_slow_affect
    agent.sleep(cycles=1)
    assert agent._pending_slow_affect == []
    assert stable_fingerprint(agent) != before


def test_rating_changed_after_consolidation_is_learned_next_sleep():
    agent = _build_agent(("go",), seed=9)
    episode_id = agent.commit_executed_transition(
        action="go",
        reward=1.0,
        context_events=["bin"],
        decided_action="go",
        terminal=True,
        dt=0.0,
    )
    agent.sleep(cycles=1)
    episode = agent.hippocampus.get_experience(episode_id)
    assert bool(episode.consolidated) is True
    first_q = _stable_q(agent, ["bin"], "go")
    agent.apply_feedback_to_last_experience(-2, context_events=["bin"], action_id="go", episode_id=episode_id)
    assert int(episode.outcome_revision) != int(episode.consolidated_revision)
    assert _stable_q(agent, ["bin"], "go") == pytest.approx(first_q)
    agent.sleep(cycles=2)
    assert _stable_q(agent, ["bin"], "go") < first_q
    assert int(episode.consolidated_revision) == int(episode.outcome_revision)
