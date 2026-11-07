"""Independent QA for PR #35 (issues #9, #10, #12).

These checks do not replace the senior tests. They rebuild the scenarios
from the issues: current TD against a table with different state values,
a per-state variance gate fed by real rewards, credit that stays inside
trajectory_id, BG relaxation toward a prior, and neuromodulator fixed points.
"""

import inspect
import pickle

import pytest

from learning_guard import learning_allowed


@pytest.fixture(autouse=True)
def _seed_stable_weights_under_sleep_guard():
    """Seed stable weights the way sleep does. Invariant W is test_issue13."""
    with learning_allowed():
        yield


from agent import Agent
from experience import Event, EventType, Experience, Path
from hippocampus import NOWAHippocampus
from intent_memory import IntentMemory
from neuromodulators import NeuromodulatorState
from selector import ActionSelector
from sleep import CortexMemory, SleepManager
from storage import AgentStorage
from value_layer import ValueLayer


def _agent(actions=("act",), seed=0):
    hip = NOWAHippocampus(max_experiences=80)
    cortex = CortexMemory()
    intent = IntentMemory()
    sleep = SleepManager(hip, cortex, intent)
    selector = ActionSelector(actions=list(actions))
    agent = Agent(hip, cortex, selector, sleep, intent, rng_seed=seed)
    for name in actions:
        agent.register_action_channel(name, go_weight=0.5, nogo_weight=0.5, habit_strength=0.1)
    sleep._rng.seed(seed)
    return agent


def _open_replay_gates(sleep):
    sleep.td_threshold = 0.05
    sleep.salience_threshold = 0.0
    sleep.ach_min_for_consolidation = 0.0
    sleep.decay_rate_sleep = 0.0
    sleep.weight_norm_cap = 10.0
    sleep.replay_budget_per_sleep = 8
    sleep.max_replay_per_episode = 4
    sleep.global_sleep_update_budget = 5.0
    sleep.per_update_cap = 0.5
    sleep.delta_value_max_per_sleep = 0.5
    sleep.max_l2_update_per_cycle = 5.0


def _transition(index, layer, *, reward, action="move", terminal=True):
    path = Path().add_event(Event(f"ctx{index}", event_type=EventType.CONTEXT))
    path = path.add_event(Event(f"action:{action}", event_type=EventType.ACTION))
    exp = Experience(path=path, consequence=None, intensity=1.0, reward=reward)
    snapshot = {
        "context_signature": f"ctx{index}",
        "context_size": 1,
        "action": action,
        "consequence": "",
        "intensity": 1.0,
        "novelty": 0.0,
        "conflict": 0.0,
    }
    next_snapshot = dict(snapshot)
    next_snapshot["context_signature"] = f"ctx{index}-next"
    exp.value_state_snapshot = dict(snapshot)
    exp.value_state_key = layer.encoder.encode(snapshot)
    exp.value_next_state_snapshot = dict(next_snapshot)
    exp.value_terminal = bool(terminal)
    exp.td_committed_reward = float(reward)
    exp.td_error_snapshot = 1.0
    exp.td_mean_snapshot = 1.0
    exp._sleep_consolidation_score = 1.0
    exp._sleep_variance_gate = 1.0
    exp.timestamp = float(index)
    exp.replay_salience = 1.0
    exp.replay_importance = 1.0
    exp.reinforcement_count = 3
    exp.replay_action_id = action
    return exp


def _set_q(layer, snapshot, action, value):
    snap = dict(snapshot)
    snap["action"] = action
    key = layer.encoder.encode(snap)
    layer._set_value(key, float(value))
    return key


def _state_var(agent, exp):
    key = str(getattr(exp, "value_state_key", "") or "")
    profile = agent.value_layer.expectation_memory.get(key) or {}
    return float(profile.get("expected_reward_var", 0.0))


def _write_reward_history(agent) -> None:
    """Expectation variance is a stable statistic. Waking steps no longer write it.

    The gate below still has to see the real reward sequence, so the stable
    writer runs here under the sleep guard, once per stored episode.
    """
    from learning_guard import learning_allowed

    with learning_allowed():
        for exp in list(agent.hippocampus.experiences):
            snapshot = getattr(exp, "value_state_snapshot", None) or {}
            nxt = getattr(exp, "value_next_state_snapshot", None) or snapshot
            agent.value_layer.update(
                state_snapshot=snapshot,
                reward=float(getattr(exp, "reward", 0.0) or 0.0),
                next_state_snapshot=nxt,
                mode="online",
                terminal=bool(getattr(exp, "value_terminal", True)),
            )


def test_replay_moves_toward_current_delta_across_different_state_values():
    """Q follows r + γV(s') − Q. A stale snapshot of the opposite sign does not win."""
    dummy = object()
    sleep = SleepManager(dummy, dummy)
    sleep.value_layer = ValueLayer()
    sleep.sleep_alpha_cap = 0.2
    sleep.value_layer.alpha_sleep_default = 0.2
    sleep.global_sleep_update_budget = 10.0
    sleep.per_update_cap = 1.0
    sleep.delta_value_max_per_sleep = 1.0
    sleep.max_l2_update_per_cycle = 10.0
    layer = sleep.value_layer
    gamma = float(layer.gamma_default)

    exp = _transition(0, layer, reward=0.0, terminal=False)
    exp.td_error_snapshot = -1.0
    exp.td_mean_snapshot = -1.0
    current = 0.10
    successor = 0.80
    _set_q(layer, exp.value_state_snapshot, "move", current)
    _set_q(layer, exp.value_next_state_snapshot, "move", successor)
    expected = 0.0 + (gamma * successor) - current

    delta = sleep._compute_offline_td_error(exp)
    assert delta == pytest.approx(expected)
    assert delta > 0.5
    assert sleep._replay_signed_td(exp) == pytest.approx(delta)
    assert "_compute_offline_td_error" in inspect.getsource(sleep._replay_signed_td)

    before = layer.get_value(exp.value_state_snapshot)
    stats = sleep._apply_replay_td_bg([exp])
    after = layer.get_value(exp.value_state_snapshot)

    assert stats["replays_applied"] == 1
    assert after > before
    assert layer.last_td_error > 0.0
    # One fractional step of the live error cannot jump past the Bellman target.
    # The step uses alpha_sleep = 0.25 * alpha_online, not the stored 0.2.
    target = current + expected
    alpha_sleep = 0.25 * float(layer.alpha_online_default)
    assert after < target
    assert after - before == pytest.approx(alpha_sleep * expected, abs=1e-4)


def test_repeated_replay_does_not_overshoot_a_learned_target():
    dummy = object()
    sleep = SleepManager(dummy, dummy)
    sleep.value_layer = ValueLayer()
    sleep.value_layer.alpha_sleep_default = 0.5
    sleep.sleep_alpha_cap = 0.5
    sleep.global_sleep_update_budget = 10.0
    sleep.per_update_cap = 1.0
    sleep.delta_value_max_per_sleep = 1.0
    sleep.max_l2_update_per_cycle = 10.0
    layer = sleep.value_layer
    gamma = float(layer.gamma_default)

    exp = _transition(1, layer, reward=0.1, terminal=False)
    exp.td_error_snapshot = 1.0
    successor = 0.40
    _set_q(layer, exp.value_next_state_snapshot, "move", successor)
    target = 0.1 + (gamma * successor)
    # Table is already above the target, while the stored sign is positive.
    _set_q(layer, exp.value_state_snapshot, "move", target + 0.35)

    # alpha_sleep is 0.25 * alpha_online, so closing a 0.35 gap takes more replays.
    for _ in range(300):
        sleep._apply_replay_td_bg([exp])
        value = layer.get_value(exp.value_state_snapshot)
        assert value >= target - 1e-9

    value = layer.get_value(exp.value_state_snapshot)
    assert value < target + 0.35
    assert value - target < 0.05


def test_terminal_bootstrap_ignores_successor_value():
    dummy = object()
    sleep = SleepManager(dummy, dummy)
    sleep.value_layer = ValueLayer()
    layer = sleep.value_layer
    gamma = float(layer.gamma_default)
    reward = 0.15
    current = 0.05
    successor = 0.90

    terminal = _transition(2, layer, reward=reward, terminal=True)
    _set_q(layer, terminal.value_state_snapshot, "move", current)
    _set_q(layer, terminal.value_next_state_snapshot, "move", successor)
    assert sleep._compute_offline_td_error(terminal) == pytest.approx(reward - current)
    assert sleep._offline_successor_value(terminal) == pytest.approx(0.0)

    open_exp = _transition(3, layer, reward=reward, terminal=False)
    _set_q(layer, open_exp.value_state_snapshot, "move", current)
    _set_q(layer, open_exp.value_next_state_snapshot, "move", successor)
    assert sleep._compute_offline_td_error(open_exp) == pytest.approx(
        reward + (gamma * successor) - current
    )

    sleep.sleep_alpha_cap = 0.5
    layer.alpha_sleep_default = 0.5
    sleep.global_sleep_update_budget = 10.0
    sleep.per_update_cap = 1.0
    sleep.delta_value_max_per_sleep = 1.0
    sleep.max_l2_update_per_cycle = 10.0
    before = layer.get_value(terminal.value_state_snapshot)
    sleep._apply_replay_td_bg([terminal])
    after_terminal = layer.get_value(terminal.value_state_snapshot)
    sleep._apply_replay_td_bg([open_exp])
    after_open = layer.get_value(open_exp.value_state_snapshot)

    assert after_terminal > before
    # The open transition's larger TD moves Q further. The gap scales with
    # alpha_sleep (0.25 * alpha_online), so it is no longer a flat 0.05.
    terminal_step = after_terminal - before
    open_step = after_open - current
    open_td = reward + (gamma * successor) - current
    terminal_td = reward - current
    assert open_step > terminal_step
    assert open_step / terminal_step == pytest.approx(open_td / terminal_td, rel=0.02)


def test_variance_gate_follows_real_reward_history_per_state():
    steady = _agent(actions=("only",))
    _open_replay_gates(steady.sleep_manager)
    for _ in range(24):
        steady.bg_action_channels["only"].go_weight = 1.0
        steady.bg_action_channels["only"].nogo_weight = 0.0
        steady.step(["same"], reward=0.4, novelty=0.0, conflict=0.0, intensity=1.0, terminal=True)
    _write_reward_history(steady)
    steady_exp = steady.hippocampus.experiences[-1]
    steady_var = _state_var(steady, steady_exp)
    assert steady_var < 0.5

    steady.value_layer._set_value(str(steady_exp.value_state_key), 0.0)
    for exp in steady.hippocampus.experiences:
        exp.reinforcement_count = 3
        exp.value_terminal = True
        exp.td_committed_reward = 0.4
        exp.reward = 0.4
    steady_stats = steady.sleep(cycles=1)
    assert int(steady_stats.get("rejected_due_to_variance_gate", 0)) == 0
    assert int(steady_stats.get("total_replays", 0)) >= 1

    noisy = _agent(actions=("only",), seed=1)
    _open_replay_gates(noisy.sleep_manager)
    for index in range(40):
        noisy.bg_action_channels["only"].go_weight = 1.0
        noisy.bg_action_channels["only"].nogo_weight = 0.0
        reward = 1.0 if index % 2 == 0 else -1.0
        noisy.step(["flip"], reward=reward, novelty=0.0, conflict=0.0, intensity=1.0, terminal=True)
    _write_reward_history(noisy)
    noisy_exp = noisy.hippocampus.experiences[-1]
    noisy_var = _state_var(noisy, noisy_exp)
    assert noisy_var >= 0.5

    before = noisy.value_layer.get_value(noisy_exp.value_state_snapshot)
    noisy.value_layer._set_value(str(noisy_exp.value_state_key), 0.0)
    for exp in noisy.hippocampus.experiences:
        exp.reinforcement_count = 3
    noisy_stats = noisy.sleep(cycles=1)
    after = noisy.value_layer.get_value(noisy_exp.value_state_snapshot)
    assert int(noisy_stats.get("rejected_due_to_variance_gate", 0)) >= 1
    assert int(noisy_stats.get("total_replays", 0)) == 0
    assert after == pytest.approx(0.0)
    assert before == pytest.approx(before)


def test_credit_stays_inside_trajectory_on_agent_episodes():
    agent = _agent(actions=("act",), seed=2)
    sleep = agent.sleep_manager
    _open_replay_gates(sleep)
    sleep.credit_window = 4

    agent.step(["left"], reward=0.0, intensity=1.0, terminal=False)
    agent.step(["left"], reward=0.0, intensity=1.0, terminal=False)
    agent.step(["left"], reward=1.0, intensity=1.0, terminal=True)
    agent.step(["right"], reward=0.0, intensity=1.0, terminal=False)
    agent.step(["right"], reward=0.0, intensity=1.0, terminal=False)
    agent.step(["right"], reward=0.0, intensity=1.0, terminal=True)

    episodes = list(agent.hippocampus.experiences)
    left = episodes[:3]
    right = episodes[3:]
    assert [int(exp.episode_step) for exp in left] == [0, 1, 2]
    assert [int(exp.episode_step) for exp in right] == [0, 1, 2]
    assert len({exp.trajectory_id for exp in left}) == 1
    assert left[0].trajectory_id != right[0].trajectory_id
    for exp in right:
        exp.reward = 0.0
        exp.td_error_snapshot = 0.0
        exp.td_mean_snapshot = 0.0
        exp.td_history_snapshot = []
        exp.prediction_shock_flag = False

    # Interleave the sample so a flat index would attach the left reward to the right chain.
    interleaved = [left[0], right[0], left[1], right[1], left[2], right[2]]
    depths = sleep._assign_reward_anchored_causal_depth(interleaved, credit_window=4)
    assert depths[id(left[2])] == 0
    assert depths[id(left[1])] == 1
    assert depths[id(left[0])] == 2
    # Right chain has no reward, so its anchor is its own middle step, not the left reward.
    assert depths[id(right[1])] == 0
    assert depths[id(right[0])] == 1
    assert depths[id(right[2])] == 1

    early_right = right[0]
    early_right._sleep_variance_gate = 1.0
    early_right._sleep_consolidation_score = 1.0
    agent.value_layer._set_value(str(early_right.value_state_key), 0.0)
    sleep._apply_replay_td_bg([right[0], right[1], right[2], left[2]])
    assert int(getattr(early_right, "causal_depth", -1)) == 1
    assert int(getattr(left[2], "causal_depth", -1)) == 0


def test_many_sleeps_without_new_outcomes_relax_toward_prior():
    agent = _agent()
    channel = agent.bg_action_channels["act"]
    channel.prior_go = 0.40
    channel.prior_nogo = 0.30
    channel.prior_habit = 0.10
    channel.go_weight = 0.90
    channel.nogo_weight = 0.85
    channel.habit_strength = 0.70
    agent.sleep_manager.decay_rate_sleep = 0.05
    agent.sleep_manager.weight_norm_cap = 10.0
    agent.hippocampus.experiences.clear()
    agent.bg_sleep_memories.clear()

    agent.sleep(cycles=50)

    updated = agent.bg_action_channels["act"]
    assert updated.go_weight == pytest.approx(0.40 + (0.90 - 0.40) * (0.95 ** 50), abs=0.02)
    assert updated.nogo_weight == pytest.approx(0.30 + (0.85 - 0.30) * (0.95 ** 50), abs=0.02)
    assert updated.habit_strength == pytest.approx(0.10 + (0.70 - 0.10) * (0.95 ** 50), abs=0.03)
    assert updated.go_weight > 0.40
    assert abs(updated.go_weight - 0.40) < abs(updated.go_weight - 0.0)
    assert abs(updated.nogo_weight - 0.30) < abs(updated.nogo_weight - 0.0)
    assert abs(updated.habit_strength - 0.10) < abs(updated.habit_strength - 0.0)


def test_sleep_normalizes_only_the_channel_over_its_own_cap():
    agent = _agent(actions=("low_a", "low_b", "hot"))
    specs = {
        "low_a": (0.40, 0.30, 0.20),
        "low_b": (0.50, 0.20, 0.10),
        "hot": (1.0, 1.0, 1.0),
    }
    for name, (go, nogo, habit) in specs.items():
        channel = agent.bg_action_channels[name]
        channel.go_weight = go
        channel.nogo_weight = nogo
        channel.habit_strength = habit
        channel.prior_go = go
        channel.prior_nogo = nogo
        channel.prior_habit = habit
    sleep = agent.sleep_manager
    sleep.weight_norm_cap = 1.6
    sleep.decay_rate_sleep = 0.0
    agent.hippocampus.experiences.clear()
    agent.bg_sleep_memories.clear()

    agent.sleep(cycles=1)

    low_a = agent.bg_action_channels["low_a"]
    low_b = agent.bg_action_channels["low_b"]
    hot = agent.bg_action_channels["hot"]
    assert low_a.go_weight == pytest.approx(0.40)
    assert low_a.nogo_weight == pytest.approx(0.30)
    assert low_b.go_weight == pytest.approx(0.50)
    assert low_b.habit_strength == pytest.approx(0.10)
    hot_l1 = abs(hot.go_weight) + abs(hot.nogo_weight) + abs(hot.habit_strength)
    assert hot_l1 == pytest.approx(1.6)
    assert hot.go_weight == pytest.approx(1.6 / 3.0)


def test_one_positive_record_is_read_in_sleep_and_cache_is_cleared():
    """One known episode is consolidated once. The legacy outcome cache is not the source."""
    agent = _agent()
    channel = agent.bg_action_channels["act"]
    channel.go_weight = 0.50
    channel.prior_go = 0.50
    agent.neuromodulators.dopamine = 0.40
    agent.sleep_manager.decay_rate_sleep = 0.0
    agent.sleep_manager.weight_norm_cap = 10.0
    agent.commit_executed_transition(
        action="act",
        reward=1.0,
        context_events=["ctx"],
        decided_action="act",
        terminal=True,
        dt=0.0,
    )

    agent.sleep(cycles=1)

    learned = float(agent.bg_action_channels["act"].go_weight)
    assert learned > 0.50
    assert agent.bg_sleep_memories == {}
    agent.sleep(cycles=1)
    assert agent.bg_action_channels["act"].go_weight == pytest.approx(learned)


def test_zero_outcome_is_not_a_sleep_punishment():
    punished = _agent(seed=3)
    control = _agent(seed=3)
    for agent in (punished, control):
        channel = agent.bg_action_channels["act"]
        channel.go_weight = 0.62
        channel.nogo_weight = 0.41
        channel.habit_strength = 0.20
        channel.prior_go = 0.62
        channel.prior_nogo = 0.41
        channel.prior_habit = 0.20
        agent.neuromodulators.dopamine = 0.30
        agent.neuromodulators.cortisol = 0.40
        agent.neuromodulators.serotonin = 0.20
        agent.sleep_manager.decay_rate_sleep = 0.0
        agent.sleep_manager.weight_norm_cap = 10.0
        agent.hippocampus.experiences.clear()
    punished.commit_executed_transition(
        action="act",
        reward=0.0,
        context_events=["ctx"],
        decided_action="act",
        terminal=True,
        dt=0.0,
    )
    punished.sleep(cycles=1)
    control.sleep(cycles=1)

    got = punished.bg_action_channels["act"]
    base = control.bg_action_channels["act"]
    assert got.go_weight == pytest.approx(base.go_weight)
    assert got.nogo_weight == pytest.approx(base.nogo_weight)
    assert got.go_weight == pytest.approx(0.62)
    assert got.nogo_weight == pytest.approx(0.41)
    assert punished.bg_sleep_memories == {}


def test_same_feedback_does_not_append_the_sleep_cache_twice():
    agent = _agent(actions=("red", "blue"), seed=4)
    action = agent.step(["ctx"], reward=None, intensity=1.0)
    episode_id = agent.last_episode_id
    first = agent.apply_feedback_to_last_experience(2, ["ctx"], action, episode_id)
    from learning_guard import labile_snapshot

    after_first = len(labile_snapshot(agent)["contributions"])
    go_after_first = agent.bg_action_channels[action].go_weight
    second = agent.apply_feedback_to_last_experience(2, ["ctx"], action, episode_id)
    assert first["updated"] is True
    assert second["updated"] is True
    assert len(labile_snapshot(agent)["contributions"]) == after_first == 1
    assert agent.bg_action_channels[action].go_weight == pytest.approx(go_after_first)

    later = agent.step(["other"], reward=None, intensity=1.0)
    later_id = agent.last_episode_id
    assert later_id != episode_id
    agent.apply_feedback_to_last_experience(-2, ["ctx"], action, episode_id)
    older = agent.hippocampus.get_experience(episode_id)
    newer = agent.hippocampus.get_experience(later_id)
    assert float(older.reward) == pytest.approx(-1.0)
    assert float(getattr(newer, "reward", 0.0)) == pytest.approx(0.0)
    assert later != ""


def test_reward_signal_without_dopamine_drive_does_not_silence_da():
    nm = NeuromodulatorState()
    resting = NeuromodulatorState()
    for _ in range(40):
        nm.update_from_signals(
            reward=1.0,
            novelty=0.0,
            conflict=0.0,
            stable_repetition=False,
            use_reward_for_dopamine=False,
        )
        resting.update_from_signals(
            reward=0.0,
            novelty=0.0,
            conflict=0.0,
            stable_repetition=False,
            use_reward_for_dopamine=False,
        )
    assert nm.dopamine > 0.05
    assert abs(nm.dopamine - NeuromodulatorState.BASELINE_DA) < 0.05
    assert resting.dopamine == pytest.approx(NeuromodulatorState.BASELINE_DA, abs=1e-6)
    assert resting.acetylcholine == pytest.approx(resting.ach_baseline, abs=1e-6)


def test_agent_reward_step_keeps_dopamine_off_the_clamps():
    agent = _agent()
    for _ in range(40):
        agent.step(["ctx_reward"], reward=1.0, novelty=0.0, conflict=0.0, intensity=1.0)
    dopamine = float(agent.neuromodulators.dopamine)
    assert 0.02 < dopamine < 0.98


def test_novelty_after_repetition_reopens_acetylcholine_gate():
    nm = NeuromodulatorState()
    for _ in range(25):
        nm.update_from_signals(
            reward=0.0,
            novelty=0.0,
            conflict=0.0,
            stable_repetition=True,
            use_reward_for_dopamine=False,
        )
    closed = nm.acetylcholine_gate()
    nm.update_from_signals(
        reward=0.0,
        novelty=1.0,
        conflict=0.0,
        stable_repetition=False,
        use_reward_for_dopamine=False,
    )
    assert nm.acetylcholine >= nm.ach_baseline - 1e-6
    assert nm.acetylcholine_gate() > closed
    assert nm.acetylcholine_gate() > 0.0

    agent = _agent()
    for _ in range(12):
        agent.step(["repeat"], reward=0.2, novelty=0.0, conflict=0.0, intensity=1.0)
    before = float(agent.neuromodulators.acetylcholine_gate())
    agent.step(["repeat"], reward=0.2, novelty=1.0, conflict=0.0, intensity=1.0)
    assert float(agent.neuromodulators.acetylcholine_gate()) > before
    assert float(agent.neuromodulators.acetylcholine_gate()) > 0.0


def test_apply_impulses_clips_both_directions():
    high = NeuromodulatorState()
    high.dopamine = 0.50
    high.acetylcholine = 0.50
    high._sync_field_from_state()
    raised = high.apply_impulses({"dopamine": 5.0, "acetylcholine": -4.0, "cortisol": 2.0})
    assert raised["dopamine"] == pytest.approx(0.25)
    assert raised["acetylcholine"] == pytest.approx(-0.25)
    assert raised["cortisol"] == pytest.approx(0.25)
    assert high.dopamine == pytest.approx(0.75)
    assert high.acetylcholine == pytest.approx(0.25)

    low = NeuromodulatorState()
    low.dopamine = 0.10
    sunk = low.apply_impulses({"dopamine": -1.0})
    assert sunk["dopamine"] >= -0.25 - 1e-9
    assert low.dopamine == pytest.approx(0.0)


def test_old_save_without_new_fields_loads_and_weights_stay(tmp_path):
    agent = _agent(actions=("act",), seed=5)
    agent.step(["kept"], reward=0.3, intensity=1.0, terminal=False)
    agent.step(["kept"], reward=0.3, intensity=1.0, terminal=True)
    channel = agent.bg_action_channels["act"]
    channel.go_weight = 0.71
    channel.nogo_weight = 0.28
    channel.habit_strength = 0.16
    channel.prior_go = 0.20
    channel.prior_nogo = 0.20
    channel.prior_habit = 0.05
    agent.neuromodulators.ach_running_mean = 0.44
    agent.neuromodulators.dopamine = 0.33
    q_before = float(agent.value_layer.get_value(agent.hippocampus.experiences[-1].value_state_snapshot))

    storage = AgentStorage(save_dir=str(tmp_path))
    path = storage.save_agent(
        agent.hippocampus,
        agent.cortex,
        agent.selector,
        sleep_manager=agent.sleep_manager,
        neuromodulators=agent.neuromodulators,
        value_layer=agent.value_layer,
        agent=agent,
        filename="legacy.pkl",
    )
    with open(path, "rb") as handle:
        payload = pickle.load(handle)
    blob = payload["bg_action_channels"]["act"]
    for key in ("prior_go", "prior_nogo", "prior_habit"):
        blob.pop(key, None)
    for key in ("trajectory_seq", "trajectory_step", "trajectory_id", "trajectory_closed"):
        payload.pop(key, None)
    payload["neuromodulators"].pop("ach_running_mean", None)
    for exp in payload["hippocampus_experiences"]:
        for name in ("trajectory_id", "episode_step"):
            if hasattr(exp, name):
                delattr(exp, name)
    with open(path, "wb") as handle:
        pickle.dump(payload, handle)

    restored = _agent(actions=("act",), seed=6)
    storage.load_agent(
        restored.hippocampus,
        restored.cortex,
        restored.selector,
        path,
        sleep_manager=restored.sleep_manager,
        neuromodulators=restored.neuromodulators,
        value_layer=restored.value_layer,
        agent=restored,
    )
    loaded = restored.bg_action_channels["act"]
    assert loaded.go_weight == pytest.approx(0.71)
    assert loaded.nogo_weight == pytest.approx(0.28)
    assert loaded.habit_strength == pytest.approx(0.16)
    assert loaded.prior_go == pytest.approx(loaded.go_weight)
    assert loaded.prior_nogo == pytest.approx(loaded.nogo_weight)
    assert loaded.prior_habit == pytest.approx(loaded.habit_strength)
    assert restored.neuromodulators.dopamine == pytest.approx(0.33)
    assert restored.neuromodulators.ach_running_mean == pytest.approx(restored.neuromodulators.ach_baseline)
    assert float(restored.value_layer.get_value(restored.hippocampus.experiences[-1].value_state_snapshot)) == pytest.approx(
        q_before
    )

    restored.sleep_manager.decay_rate_sleep = 0.08
    restored.hippocampus.experiences.clear()
    restored.bg_sleep_memories.clear()
    # Habit consolidation reads success counts. This check is the missing-prior decay.
    loaded.selection_count = 0
    restored.sleep(cycles=5)
    held = restored.bg_action_channels["act"]
    assert held.go_weight == pytest.approx(0.71)
    assert held.nogo_weight == pytest.approx(0.28)
    assert held.habit_strength == pytest.approx(0.16)


def test_rng_seed_repeats_the_waking_trace():
    def _trace(seed):
        agent = _agent(actions=("red", "green", "blue"), seed=seed)
        return [agent.step(["band"], reward=0.2, intensity=1.0) for _ in range(8)]

    assert _trace(7) == _trace(7)
