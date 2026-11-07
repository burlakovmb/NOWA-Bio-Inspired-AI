"""Regression for issue #9: sleep value replay must follow the current TD error."""

import pytest

from learning_guard import learning_allowed


@pytest.fixture(autouse=True)
def _seed_stable_weights_under_sleep_guard():
    """Seed stable values the way sleep does. Invariant W is test_issue13."""
    with learning_allowed():
        yield


from agent import Agent
from experience import Event, EventType, Experience, Path
from hippocampus import NOWAHippocampus
from intent_memory import IntentMemory
from selector import ActionSelector
from sleep import CortexMemory, SleepManager
from value_layer import ValueLayer


def _sleep_with_layer() -> SleepManager:
    dummy = object()
    sleep = SleepManager(dummy, dummy)
    sleep.value_layer = ValueLayer()
    sleep._rng.seed(0)
    sleep.global_sleep_update_budget = 10.0
    sleep.delta_value_max_per_sleep = 1.0
    sleep.per_update_cap = 1.0
    sleep.max_l2_update_per_cycle = 10.0
    sleep.value_cap = 1.0
    sleep.sleep_alpha_cap = 0.5
    sleep.value_layer.alpha_sleep_default = 0.5
    return sleep


def _transition(index: int, layer: ValueLayer, *, reward: float, action: str = "move") -> Experience:
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
    exp.value_state_snapshot = dict(snapshot)
    exp.value_state_key = layer.encoder.encode(snapshot)
    exp.value_next_state_snapshot = dict(snapshot)
    exp.value_terminal = True
    exp.td_error_snapshot = 1.0
    exp.td_mean_snapshot = 1.0
    exp._sleep_consolidation_score = 1.0
    exp._sleep_variance_gate = 1.0
    exp.timestamp = float(index)
    exp.replay_salience = 1.0
    exp.replay_importance = 1.0
    exp.reinforcement_count = 3
    return exp


def test_offline_td_helper_recomputes_and_ignores_stale_snapshot():
    sleep = _sleep_with_layer()
    exp = _transition(0, sleep.value_layer, reward=0.0)
    exp.td_error_snapshot = 5.0
    exp.value_terminal = True
    sleep.value_layer._set_value(exp.value_state_key, 0.25)

    delta = sleep._compute_offline_td_error(exp)

    assert delta == pytest.approx(-0.25)


def test_replay_follows_current_td_not_stale_sign():
    sleep = _sleep_with_layer()
    exp = _transition(0, sleep.value_layer, reward=0.0)
    exp.td_error_snapshot = 1.0
    exp.td_mean_snapshot = 1.0
    sleep.value_layer._set_value(exp.value_state_key, 0.4)
    before = sleep.value_layer.get_value(exp.value_state_snapshot)

    stats = sleep._apply_replay_td_bg([exp])
    after = sleep.value_layer.get_value(exp.value_state_snapshot)

    assert stats["replays_applied"] == 1
    assert after < before
    assert sleep.value_layer.last_td_error < 0.0


def test_repeated_replay_approaches_target_without_sign_overshoot():
    sleep = _sleep_with_layer()
    sleep.value_layer.alpha_sleep_default = 0.5
    exp = _transition(1, sleep.value_layer, reward=0.2)
    exp.td_error_snapshot = 1.0
    target = 0.2

    # alpha_sleep is 0.25 * alpha_online, so the approach to 0.2 takes
    # more replays than the old uncapped 0.5 step.
    for _ in range(250):
        sleep._apply_replay_td_bg([exp])

    value = sleep.value_layer.get_value(exp.value_state_snapshot)
    assert value <= target + 1e-9
    assert value > 0.16


def test_priority_uses_current_abs_delta_not_stored_snapshot():
    sleep = _sleep_with_layer()
    stale = _transition(0, sleep.value_layer, reward=0.0)
    stale.td_error_snapshot = 1.0
    stale.td_mean_snapshot = 1.0
    sleep.value_layer._set_value(stale.value_state_key, 0.0)

    live = _transition(1, sleep.value_layer, reward=0.0)
    live.td_error_snapshot = 0.05
    live.td_mean_snapshot = 0.05
    sleep.value_layer._set_value(live.value_state_key, 0.8)

    assert sleep._compute_replay_priority(live) > sleep._compute_replay_priority(stale)


def test_between_state_spread_does_not_block_replay():
    hip = NOWAHippocampus(max_experiences=100)
    cortex = CortexMemory()
    intent = IntentMemory()
    sleep = SleepManager(hip, cortex, intent)
    selector = ActionSelector(actions=["act"])
    agent = Agent(hip, cortex, selector, sleep, intent, rng_seed=0)
    agent.register_action_channel("act", go_weight=0.4, nogo_weight=0.4, habit_strength=0.1)
    sleep._rng.seed(0)
    sleep.instability_variance_threshold = 0.1
    sleep.td_threshold = 0.05
    sleep.salience_threshold = 0.0
    sleep.ach_min_for_consolidation = 0.0
    sleep.decay_rate_sleep = 0.0

    agent.step(["ctx_spread"], reward=0.8, novelty=0.0, conflict=0.0, intensity=1.0)
    for exp in hip.experiences:
        exp.reinforcement_count = 3
    agent.value_layer._set_value("v0", -1.0)
    agent.value_layer._set_value("v1", 1.0)
    agent.value_layer._set_value("v2", -1.0)
    agent.value_layer._set_value("v3", 1.0)

    stats = agent.sleep(cycles=1)

    assert float(stats.get("value_variance_ratio", 0.0)) >= 1.0
    assert stats["total_replays"] >= 1
    assert int(stats.get("rejected_due_to_variance_gate", 0)) == 0


def test_per_state_estimate_variance_blocks_that_state_only():
    hip = NOWAHippocampus(max_experiences=100)
    cortex = CortexMemory()
    intent = IntentMemory()
    sleep = SleepManager(hip, cortex, intent)
    selector = ActionSelector(actions=["act"])
    agent = Agent(hip, cortex, selector, sleep, intent, rng_seed=0)
    agent.register_action_channel("act", go_weight=0.4, nogo_weight=0.4, habit_strength=0.1)
    sleep._rng.seed(0)
    sleep.td_threshold = 0.05
    sleep.salience_threshold = 0.0
    sleep.ach_min_for_consolidation = 0.0
    sleep.decay_rate_sleep = 0.0
    sleep.weight_norm_cap = 10.0

    agent.step(["ctx_uncertain"], reward=0.8, novelty=0.0, conflict=0.0, intensity=1.0)
    exp = hip.experiences[-1]
    exp.reinforcement_count = 3
    state_key = str(exp.value_state_key)
    before = agent.value_layer.get_value(exp.value_state_snapshot)
    agent.value_layer.expectation_memory[state_key] = {
        "expected_reward_var": 1.0,
        "confidence_score": 0.0,
        "stability_score": 0.0,
    }

    stats = agent.sleep(cycles=1)
    after = agent.value_layer.get_value(exp.value_state_snapshot)

    assert stats["rejected_due_to_variance_gate"] >= 1
    assert stats["total_replays"] == 0
    assert after == pytest.approx(before)


def test_credit_depth_uses_episode_step_not_sample_index():
    sleep = _sleep_with_layer()
    sleep.credit_window = 6
    experiences = []
    for step in (0, 10, 20):
        exp = _transition(step, sleep.value_layer, reward=0.0 if step < 20 else 1.0)
        exp.trajectory_id = "traj-1"
        exp.episode_step = step
        exp.timestamp = float(step)
        exp.td_error_snapshot = 0.9
        experiences.append(exp)

    depths = sleep._assign_reward_anchored_causal_depth(experiences, credit_window=6)

    assert depths[id(experiences[2])] == 0
    assert depths[id(experiences[1])] == 6
    assert depths[id(experiences[0])] == 6

    before_early = sleep.value_layer.get_value(experiences[0].value_state_snapshot)
    sleep._apply_replay_td_bg(experiences)
    after_early = sleep.value_layer.get_value(experiences[0].value_state_snapshot)
    assert after_early == pytest.approx(before_early)


def test_credit_does_not_cross_trajectory_boundary():
    sleep = _sleep_with_layer()
    early = _transition(0, sleep.value_layer, reward=0.0)
    early.trajectory_id = "traj-a"
    early.episode_step = 0
    early.timestamp = 0.0
    early.td_error_snapshot = 0.0
    later = _transition(1, sleep.value_layer, reward=0.0)
    later.trajectory_id = "traj-a"
    later.episode_step = 3
    later.timestamp = 1.0
    later.td_error_snapshot = 0.0
    other = _transition(2, sleep.value_layer, reward=1.0)
    other.trajectory_id = "traj-b"
    other.episode_step = 0
    other.timestamp = 2.0
    other.td_error_snapshot = 0.2

    depths = sleep._assign_reward_anchored_causal_depth(
        [early, later, other],
        credit_window=6,
    )

    assert depths[id(other)] == 0
    assert depths[id(early)] == 3
    assert depths[id(later)] == 0


def test_agent_records_trajectory_steps_and_splits_on_terminal():
    hip = NOWAHippocampus(max_experiences=20)
    cortex = CortexMemory()
    intent = IntentMemory()
    sleep = SleepManager(hip, cortex, intent)
    selector = ActionSelector(actions=["act"])
    agent = Agent(hip, cortex, selector, sleep, intent, rng_seed=1)
    agent.register_action_channel("act")

    agent.step(["ctx"], reward=0.2, intensity=1.0, terminal=False)
    agent.step(["ctx"], reward=0.2, intensity=1.0, terminal=False)
    agent.step(["ctx"], reward=0.2, intensity=1.0, terminal=True)
    agent.step(["ctx"], reward=0.2, intensity=1.0, terminal=False)

    episodes = list(hip.experiences)
    assert [int(exp.episode_step) for exp in episodes] == [0, 1, 2, 0]
    assert episodes[0].trajectory_id == episodes[1].trajectory_id == episodes[2].trajectory_id
    assert episodes[3].trajectory_id != episodes[0].trajectory_id
