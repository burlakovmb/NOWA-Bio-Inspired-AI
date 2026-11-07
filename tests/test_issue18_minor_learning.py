"""Issue #18: fractional feedback, alpha_sleep ratio, V bound vs gamma."""

from __future__ import annotations

import math

import pytest

from agent import Agent
from cortex import CortexMemory
from hippocampus import NOWAHippocampus
from intent_memory import IntentMemory
from learning_guard import learning_allowed
from selector import ActionSelector
from sleep import SleepManager
from value_layer import (
    ValueLayer,
    discounted_value_bound,
    effective_alpha_sleep,
)


def _agent():
    hippocampus = NOWAHippocampus(max_experiences=40)
    cortex = CortexMemory()
    memory = IntentMemory()
    sleep_manager = SleepManager(hippocampus, cortex, memory)
    selector = ActionSelector(actions=["go"])
    return Agent(hippocampus, cortex, selector, sleep_manager, memory, rng_seed=1)


def _state(ctx: str):
    return {
        "context_signature": ctx,
        "context_size": 1,
        "action": "go",
        "consequence": "",
        "intensity": 1.0,
        "novelty": 0.0,
        "conflict": 0.0,
    }


def test_fractional_feedback_is_not_quantized_by_int():
    agent = _agent()
    agent.step(["bin"], reward=None, terminal=True, dt=0.0)
    episode_id = agent.last_episode_id

    # int(1.5) / 2 was 0.5; the fraction must survive.
    applied = agent.apply_feedback_to_last_experience(1.5, episode_id=episode_id)
    assert applied["updated"] is True
    assert applied["reward_signal"] == pytest.approx(0.75)
    stored = agent.hippocampus.get_experience(episode_id)
    assert float(stored.reward) == pytest.approx(0.75)
    assert float(stored.feedback_rating) == pytest.approx(1.5)

    # int(0.7) was 0, which dropped the rating.
    agent.apply_feedback_to_last_experience(0.7, episode_id=episode_id)
    revised = agent.hippocampus.get_experience(episode_id)
    assert float(revised.reward) == pytest.approx(0.35)
    assert float(revised.feedback_rating) == pytest.approx(0.7)


def test_feedback_still_clamps_to_rating_scale_and_rejects_non_numeric():
    agent = _agent()
    rating, reward = agent._coerce_feedback_rating(3.2)
    assert rating == pytest.approx(2.0)
    assert reward == pytest.approx(1.0)
    rating, reward = agent._coerce_feedback_rating(-2.5)
    assert rating == pytest.approx(-2.0)
    assert reward == pytest.approx(-1.0)
    # Whole ratings keep the old reward.
    rating, reward = agent._coerce_feedback_rating(2)
    assert reward == pytest.approx(1.0)
    assert agent._coerce_feedback_rating(float("nan")) is None
    assert agent._coerce_feedback_rating(True) is None
    assert agent._coerce_feedback_rating("nope") is None
    rating, reward = agent._coerce_feedback_rating(float("inf"))
    assert reward == pytest.approx(1.0)
    assert rating == pytest.approx(2.0)


def test_default_alpha_sleep_is_derived_from_online_ratio():
    layer = ValueLayer()
    assert layer.alpha_online_default == pytest.approx(0.03)
    assert layer.alpha_sleep_ratio == pytest.approx(0.25)
    assert layer.alpha_sleep_default == pytest.approx(0.25 * 0.03)
    assert layer.alpha_sleep_default <= 0.25 * layer.alpha_online_default + 1e-12

    # The historical 0.08 default is above the ratio and must be capped.
    explicit = ValueLayer(alpha_online_default=0.03, alpha_sleep_default=0.08)
    assert explicit.alpha_sleep_default == pytest.approx(0.0075)

    # A tighter stored rate is kept.
    tighter = ValueLayer(alpha_online_default=0.03, alpha_sleep_default=0.001)
    assert tighter.alpha_sleep_default == pytest.approx(0.001)


def test_sleep_replay_applies_alpha_sleep_ratio():
    layer = ValueLayer()
    layer.alpha_sleep_default = 0.5
    sleep = SleepManager(object(), object(), object())
    sleep.value_layer = layer
    sleep.alpha_sleep_ratio = 0.25
    sleep.sleep_alpha_cap = 0.5

    effective = sleep._resolved_alpha_sleep(layer, stability_gate=1.0)
    assert effective == pytest.approx(0.25 * layer.alpha_online_default)
    assert effective < 0.5

    sleep.alpha_sleep_ratio = 0.1
    tightened = sleep._resolved_alpha_sleep(layer, stability_gate=1.0)
    assert tightened == pytest.approx(0.1 * layer.alpha_online_default)

    # The ratio itself cannot exceed the spec ceiling of 0.25.
    sleep.alpha_sleep_ratio = 0.9
    capped_ratio = sleep._resolved_alpha_sleep(layer, stability_gate=1.0)
    assert capped_ratio == pytest.approx(0.25 * layer.alpha_online_default)
    assert effective_alpha_sleep(0.03, None, 0.9) == pytest.approx(0.0075)


def test_value_bound_matches_discounted_unit_reward():
    assert discounted_value_bound(0.95, 1.0) == pytest.approx(20.0)
    assert discounted_value_bound(0.0, 1.0) == pytest.approx(1.0)
    layer = ValueLayer()
    assert layer.value_abs_bound() == pytest.approx(20.0)
    layer.gamma_default = 0.5
    assert layer.value_abs_bound() == pytest.approx(2.0)


def test_value_table_can_hold_return_above_unit_clamp():
    layer = ValueLayer()
    with learning_allowed():
        layer.update(_state("s0"), reward=0.0, next_state_snapshot=_state("s1"), timestamp=1.0)
        key = layer.last_state_key
        layer._set_value(key, 5.0)
        assert layer._get_value(key) == pytest.approx(5.0)
        layer._set_value(key, 25.0)
        assert layer._get_value(key) == pytest.approx(20.0)

        restored = ValueLayer.from_dict(layer.to_dict())
        assert restored.get_value(_state("s0")) == pytest.approx(20.0)


def test_constant_unit_reward_value_can_pass_the_old_unit_clamp():
    layer = ValueLayer(
        max_update_l2=1.0,
        td_clip_online=1.0,
        alpha_online_soft_cap=0.3,
        adaptive_td_clip_enabled=False,
    )
    state = _state("same")
    with learning_allowed():
        value = 0.0
        for step in range(1, 12):
            out = layer.update(
                state,
                reward=1.0,
                next_state_snapshot=state,
                gamma=0.95,
                alpha=0.3,
                timestamp=float(step),
                mode="online",
            )
            value = float(out["value"])
    # Old clamp stopped V at 1. The discounted return of a unit reward is 20.
    assert value > 1.0
    assert value <= layer.value_abs_bound() + 1e-9


def test_sleep_value_cap_is_at_least_the_gamma_return():
    layer = ValueLayer()
    sleep = SleepManager(object(), object(), object())
    sleep.value_layer = layer
    sleep.value_cap = 1.0
    assert sleep._resolved_value_cap() == pytest.approx(20.0)

    layer.gamma_default = 0.5
    assert sleep._resolved_value_cap() == pytest.approx(2.0)

    sleep.value_cap = 10.0
    assert sleep._resolved_value_cap() == pytest.approx(10.0)

    # Reward magnitude is not rewritten to (1-γ).
    assert layer.reward_scale == pytest.approx(1.0)
    assert math.isclose(layer.reward_scale, 1.0)
