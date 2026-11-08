
import pytest
from learning_guard import learning_allowed

@pytest.fixture(autouse=True)
def _allow_stable_writers_under_test():
    """Direct tests of stable writers. Sleep opens the same guard."""
    with learning_allowed():
        yield

from value_layer import (
    StateEncoder,
    ValueLayer,
    _cosine_similarity,
    _hash_text_vector,
    effective_alpha_sleep,
    state_similarity,
)


def _state(
    ctx: str,
    action: str = "",
    consequence: str = "",
    intensity: float = 1.0,
    novelty: float = 0.0,
    conflict: float = 0.0,
):
    return {
        "context_signature": ctx,
        "context_size": len([item for item in ctx.split("|") if item]),
        "action": action,
        "consequence": consequence,
        "intensity": intensity,
        "novelty": novelty,
        "conflict": conflict,
    }


def test_state_encoder_is_deterministic_and_order_invariant():
    encoder = StateEncoder()
    first = {
        "action": "respond",
        "context_signature": "a|b",
        "context_size": 2,
        "conflict": 0.12349,
        "intensity": 1.00001,
        "novelty": 0.5,
        "consequence": "ok",
        "ignored_noise": 999,
    }
    second = {
        "novelty": 0.5,
        "consequence": "ok",
        "context_size": 2,
        "context_signature": "a|b",
        "action": "respond",
        "intensity": 1.0,
        "conflict": 0.1235,
    }

    assert encoder.encode(first) == encoder.encode(second)


def test_semantic_hash_vector_is_deterministic_and_unit_norm():
    first = _hash_text_vector("consume_food")
    second = _hash_text_vector("consume_food")

    assert first == second
    assert abs(sum(value * value for value in first) - 1.0) < 1e-9


def test_semantic_hash_tokenization_matches_space_and_underscore():
    underscored = _hash_text_vector("eat_food")
    spaced = _hash_text_vector("eat food")

    assert _cosine_similarity(underscored, spaced) > 0.999999


def test_semantic_hash_equals_normalized_mean_of_token_vectors():
    eat = _hash_text_vector("eat")
    food = _hash_text_vector("food")
    combined = _hash_text_vector("eat_food")
    mean = [(left + right) / 2.0 for left, right in zip(eat, food)]
    norm = sum(value * value for value in mean) ** 0.5
    normalized_mean = [value / norm for value in mean]

    for actual, expected in zip(combined, normalized_mean):
        assert abs(actual - expected) < 1e-12


def test_state_similarity_treats_space_and_underscore_as_same_tokens():
    base = _state("", action="eat_food", intensity=0.0)
    spaced = _state("", action="eat food", intensity=0.0)
    unrelated = _state("", action="sleep_now", intensity=0.0)

    assert state_similarity(base, spaced) > state_similarity(base, unrelated)


def test_positive_surprise_increases_value_and_dopamine_delta():
    layer = ValueLayer()
    st = _state("s0", action="act")
    st_next = _state("s1")

    before = layer.get_value(st)
    out = layer.update(st, reward=0.8, next_state_snapshot=st_next, alpha=0.03, gamma=0.95, timestamp=1.0)

    assert out["td_error"] > 0.0
    assert out["value"] > before
    assert layer.compute_dopamine_delta(out["td_error"]) > 0.0


def test_negative_surprise_decreases_value_and_dopamine_delta():
    layer = ValueLayer()
    st = _state("s0", action="act")
    st_next = _state("s1")
    key_st = layer.encoder.encode(st)
    key_next = layer.encoder.encode(st_next)
    layer.values[key_st] = 0.6
    layer.values[key_next] = 0.2

    out = layer.update(st, reward=0.1, next_state_snapshot=st_next, alpha=0.03, gamma=0.95, timestamp=2.0)

    assert out["td_error"] < 0.0
    assert out["value"] < 0.6
    assert layer.compute_dopamine_delta(out["td_error"]) < 0.0


def test_zero_surprise_keeps_state_stable():
    layer = ValueLayer()
    st = _state("s0")
    st_next = _state("s1")
    key_st = layer.encoder.encode(st)
    key_next = layer.encoder.encode(st_next)
    layer.values[key_st] = 0.3
    layer.values[key_next] = 0.3

    gamma = 0.95
    reward = (1.0 - gamma) * 0.3
    out = layer.update(st, reward=reward, next_state_snapshot=st_next, alpha=0.03, gamma=gamma, timestamp=3.0)

    assert abs(out["td_error"]) < 1e-9
    assert abs(out["value"] - 0.3) < 1e-9


def test_single_update_per_tick_and_value_clamp():
    layer = ValueLayer()
    st = _state("s0")
    st_next = _state("s0")

    first = layer.update(st, reward=10.0, next_state_snapshot=st_next, alpha=0.1, gamma=0.95, timestamp=10.0)
    second = layer.update(st, reward=-10.0, next_state_snapshot=st_next, alpha=0.1, gamma=0.95, timestamp=10.0)

    assert first == second
    assert -1.0 <= first["td_error"] <= 1.0
    assert -1.0 <= first["value"] <= 1.0
    assert layer.update_count == 1
    assert layer.online_update_count == 1
    assert layer.sleep_update_count == 0


def test_alpha_reduces_when_instability_is_high():
    layer = ValueLayer()
    st = _state("s0")
    st_next = _state("s1")

    stable = layer.update(st, reward=1.0, next_state_snapshot=st_next, alpha=0.1, gamma=0.95, timestamp=20.0, stability_index=1.0)
    layer.values[layer.encoder.encode(st)] = 0.0
    unstable = layer.update(st, reward=1.0, next_state_snapshot=st_next, alpha=0.1, gamma=0.95, timestamp=21.0, stability_index=0.2)

    assert abs(unstable["value"]) < abs(stable["value"])


def test_lru_eviction_for_max_states():
    layer = ValueLayer(max_states=3)
    states = [_state(f"s{i}") for i in range(4)]

    for idx in range(4):
        current = states[idx]
        nxt = states[min(idx + 1, 3)]
        layer.update(current, reward=0.2, next_state_snapshot=nxt, timestamp=float(idx + 1))

    assert len(layer.values) == 3
    first_key = layer.encoder.encode(states[0])
    assert first_key not in layer.values


def test_mode_split_counters_and_sleep_not_blocked_by_same_timestamp():
    layer = ValueLayer()
    st = _state("s0")
    st_next = _state("s1")

    layer.update(st, reward=0.5, next_state_snapshot=st_next, timestamp=7.0, mode="online")
    layer.update(st, reward=0.5, next_state_snapshot=st_next, timestamp=7.0, mode="sleep")

    snapshot = layer.snapshot()
    assert snapshot["online_update_count"] == 1
    assert snapshot["sleep_update_count"] == 1
    assert snapshot["update_count"] == 2


def test_online_td_clip_limits_reward_spike():
    layer = ValueLayer(td_clip_online=0.2, max_update_l2=1.0)
    st = _state("s0")
    st_next = _state("s1")

    out = layer.update(
        st,
        reward=1.0,
        next_state_snapshot=st_next,
        gamma=0.0,
        alpha=1.0,
        timestamp=11.0,
        mode="online",
    )
    assert abs(out["td_error"] - 0.2) < 1e-9


def test_sleep_alpha_stays_within_online_ratio():
    layer = ValueLayer(alpha_online_default=0.01, alpha_sleep_default=0.08, max_update_l2=1.0)
    st = _state("s0")
    st_next = _state("s1")
    state_key = layer.encoder.encode(st)

    online = layer.update(
        st,
        reward=1.0,
        next_state_snapshot=st_next,
        gamma=0.0,
        alpha=None,
        timestamp=21.0,
        mode="online",
    )
    layer.values[state_key] = 0.0

    sleep = layer.update(
        st,
        reward=1.0,
        next_state_snapshot=st_next,
        gamma=0.0,
        alpha=None,
        timestamp=22.0,
        mode="sleep",
    )

    # Spec: alpha_sleep ≤ 0.25 * alpha_online. The old 0.08 request is capped at use.
    assert effective_alpha_sleep(
        layer.alpha_online_default,
        layer.alpha_sleep_default,
        layer.alpha_sleep_ratio,
    ) == pytest.approx(0.25 * layer.alpha_online_default)
    assert float(sleep["alpha_effective"]) <= 0.25 * layer.alpha_online_default + 1e-12
    assert abs(sleep["value"]) < abs(online["value"])
