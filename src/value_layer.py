"""
Phase 5.0 / 5.0.1 - Value Layer with TD error learning.

This layer is intentionally isolated:
- Reads only state snapshots and scalar reward
- Learns V(s) with TD(0): delta = r + gamma * V(s_next) - V(s)
- Does not modify affective background / semantic layers / regulation
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple
from functools import lru_cache


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _clamp(value: float, min_value: float, max_value: float) -> float:
    if value < min_value:
        return min_value
    if value > max_value:
        return max_value
    return value

# Phase 5.A: alpha_sleep ≤ 0.25 · alpha_online. The ratio is applied, not only stored.
ALPHA_SLEEP_RATIO_MAX = 0.25


def alpha_sleep_ratio_value(ratio: float) -> float:
    return min(ALPHA_SLEEP_RATIO_MAX, max(0.0, _safe_float(ratio, ALPHA_SLEEP_RATIO_MAX)))


def derived_alpha_sleep(alpha_online: float, ratio: float = ALPHA_SLEEP_RATIO_MAX) -> float:
    online = max(0.0, _safe_float(alpha_online, 0.0))
    return online * alpha_sleep_ratio_value(ratio)


def effective_alpha_sleep(
    alpha_online: float,
    alpha_sleep: Optional[float],
    ratio: float = ALPHA_SLEEP_RATIO_MAX,
) -> float:
    """Sleep step from alpha_online * ratio, never above the spec ceiling.

    ``alpha_sleep is None`` means derive. A finite stored rate may only be
    tighter than that derived rate.
    """
    derived = derived_alpha_sleep(alpha_online, ratio)
    if alpha_sleep is None:
        return derived
    stored = _safe_float(alpha_sleep, derived)
    if not math.isfinite(stored) or stored < 0.0:
        return derived
    return min(stored, derived)


def discounted_value_bound(gamma: float, reward_abs_max: float = 1.0) -> float:
    """Largest |discounted return| of a reward bounded by ``reward_abs_max``.

    |sum_k gamma^k * r| ≤ R / (1 - gamma) for |r| ≤ R and gamma in [0, 0.999].
    Unit rewards (feedback and offline replay) use R = 1, so gamma = 0.95
    yields 20. Reward magnitudes themselves are not rescaled.
    """
    gamma_raw = _safe_float(gamma, 0.95)
    if not math.isfinite(gamma_raw):
        gamma_raw = 0.95
    gamma_v = _clamp(gamma_raw, 0.0, 0.999)
    reward_raw = _safe_float(reward_abs_max, 1.0)
    if not math.isfinite(reward_raw) or reward_raw < 0.0:
        reward_raw = 1.0
    return reward_raw / max(1e-9, 1.0 - gamma_v)


def _sigmoid(value: float) -> float:
    x = _safe_float(value, 0.0)
    if x >= 0.0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def _normalize_shock_fields(profile: Mapping[str, Any]) -> Tuple[float, bool]:
    shock_raw = profile.get("prediction_shock", 0.0)
    shock_flag_raw = profile.get("prediction_shock_flag", None)
    if isinstance(shock_raw, bool):
        shock_score = 1.0 if shock_raw else 0.0
        shock_flag_default = shock_raw
    else:
        shock_score = _clamp(_safe_float(shock_raw, 0.0), 0.0, 1.0)
        shock_flag_default = shock_score >= 0.5
    if shock_flag_raw is None:
        shock_flag = shock_flag_default
    else:
        shock_flag = bool(shock_flag_raw)
    return float(shock_score), bool(shock_flag)


def _normalize_vector(values: List[float]) -> List[float]:
    if not values:
        return []
    norm_sq = sum(float(v) * float(v) for v in values)
    if norm_sq <= 0.0:
        return [0.0 for _ in values]
    norm = math.sqrt(norm_sq)
    return [float(v) / norm for v in values]


def _tokenize_text(text: str) -> List[str]:
    cleaned = str(text or "").strip().casefold()
    if not cleaned:
        return []
    return re.findall(r"[^\W_]+", cleaned, flags=re.UNICODE)


@lru_cache(maxsize=8192)
def _word_hash_unit_vector(token: str, dims: int) -> Tuple[float, ...]:
    # Cached hashed unit vectors per token/dimension to avoid repeated sha256 work.
    values: List[float] = []
    for idx in range(int(dims)):
        digest = hashlib.sha256(f"{token}:{idx}".encode("utf-8")).digest()
        integer = int.from_bytes(digest[:4], "big")
        values.append((integer / 0xFFFFFFFF) * 2.0 - 1.0)
    normed = _normalize_vector(values)
    return tuple(normed)


@lru_cache(maxsize=4096)
def _hash_text_vector(text: str, dims: int = 8) -> Tuple[float, ...]:
    dims_i = max(1, int(_safe_float(dims, 8.0)))
    tokens = _tokenize_text(text)
    if not tokens:
        return tuple([0.0 for _ in range(dims_i)])
    summed = [0.0 for _ in range(dims_i)]
    for token in tokens:
        word_vector = _word_hash_unit_vector(token, dims_i)
        for idx, value in enumerate(word_vector):
            summed[idx] += float(value)
    mean_vector = [value / float(len(tokens)) for value in summed]
    normed = _normalize_vector(mean_vector)
    return tuple(normed)


def _vector_from_normalized(
    normalized: Mapping[str, Any], feature_keys: Tuple[str, ...]
) -> List[float]:
    vector: List[float] = []
    for key in feature_keys:
        value = normalized.get(key)
        if isinstance(value, (int, float)):
            vector.append(float(value))
        else:
            vector.extend(_hash_text_vector(value))
    return vector


def _cosine_similarity(left: List[float], right: List[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for l_val, r_val in zip(left, right):
        dot += l_val * r_val
        left_norm += l_val * l_val
        right_norm += r_val * r_val
    if left_norm <= 0.0 or right_norm <= 0.0:
        return 0.0
    return _clamp(dot / math.sqrt(left_norm * right_norm), 0.0, 1.0)


def _similarity_bucket_key(vector: List[float], bits: int) -> str:
    if not vector:
        return ""
    bits_v = max(1, int(bits))
    chunk = max(1, int(math.ceil(len(vector) / float(bits_v))))
    parts: List[str] = []
    for i in range(bits_v):
        start = i * chunk
        end = min(len(vector), start + chunk)
        if start >= len(vector):
            parts.append("0")
            continue
        segment = vector[start:end]
        mean_v = sum(float(v) for v in segment) / float(len(segment))
        parts.append("1" if mean_v >= 0.0 else "0")
    return "".join(parts)


def _quantile(values: List[float], q: float) -> float:
    cleaned = [float(v) for v in values if v is not None]
    if not cleaned:
        return 0.0
    sorted_values = sorted(cleaned)
    q_v = _clamp(_safe_float(q, 0.5), 0.0, 1.0)
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    index_f = q_v * float(len(sorted_values) - 1)
    lo = int(math.floor(index_f))
    hi = int(math.ceil(index_f))
    if lo == hi:
        return float(sorted_values[lo])
    alpha = index_f - float(lo)
    return float((1.0 - alpha) * sorted_values[lo] + alpha * sorted_values[hi])


def state_similarity(
    state_left: Mapping[str, Any],
    state_right: Mapping[str, Any],
    *,
    encoder: Optional["StateEncoder"] = None,
) -> float:
    encoder = encoder or StateEncoder()
    left_vector = _vector_from_normalized(encoder.normalize(state_left), encoder.feature_keys)
    right_vector = _vector_from_normalized(encoder.normalize(state_right), encoder.feature_keys)
    return _cosine_similarity(left_vector, right_vector)


@dataclass
class StateEncoder:
    """
    Deterministic state encoder.

    Uses only the provided state snapshot.
    """

    rounding: int = 3
    max_text_length: int = 80
    feature_keys: Tuple[str, ...] = (
        "context_signature",
        "context_size",
        "action",
        "consequence",
        "intensity",
        "novelty",
        "conflict",
    )

    def normalize(self, state_snapshot: Mapping[str, Any]) -> Dict[str, Any]:
        source = dict(state_snapshot or {})
        normalized: Dict[str, Any] = {}

        for key in self.feature_keys:
            value = source.get(key)
            if key in ("context_size", "intensity", "novelty", "conflict"):
                normalized[key] = round(_safe_float(value), self.rounding)
            else:
                normalized[key] = self._normalize_text(value)

        return normalized

    def encode(self, state_snapshot: Mapping[str, Any]) -> str:
        normalized = self.normalize(state_snapshot)
        payload = json.dumps(
            normalized,
            sort_keys=True,
            ensure_ascii=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _normalize_text(self, value: Any) -> str:
        if value is None:
            return ""
        text = str(value).strip()
        if len(text) > self.max_text_length:
            text = text[: self.max_text_length]
        return text


@dataclass
class DopaminergicTDLayer:
    """
    Dopaminergic TD-error profile with phasic/tonic separation.

    Notes:
    - Stress amplifies negative phasic responses (dip) via `stress_dip_gain`.
    - Tonic dopamine follows phasic mean through a slow low-pass filter.
    """

    delta_max: float = 1.0
    tonic_baseline: float = 0.1
    tonic_level: float = 0.1
    tonic_slow_rate: float = 0.01
    phasic_mean: float = 0.0
    exploration_coupling_fraction: float = 0.2
    stress_dip_gain: float = 0.35
    exploration_unfreeze_floor: float = 0.02
    tonic_target_base: float = 0.1

    def __post_init__(self) -> None:
        self.delta_max = _clamp(_safe_float(self.delta_max, 1.0), 0.05, 10.0)
        self.tonic_baseline = _clamp(_safe_float(self.tonic_baseline, 0.1), 0.0, 1.0)
        self.tonic_level = _clamp(
            _safe_float(self.tonic_level, self.tonic_baseline),
            0.0,
            1.0,
        )
        # Spec: tonic baseline drift should be slow (~0.01 per update).
        self.tonic_slow_rate = _clamp(_safe_float(self.tonic_slow_rate, 0.01), 0.0001, 0.2)
        self.phasic_mean = _clamp(_safe_float(self.phasic_mean, 0.0), -1.0, 1.0)
        self.tonic_target_base = _clamp(
            _safe_float(self.tonic_target_base, self.tonic_baseline),
            0.0,
            1.0,
        )
        # Spec: exploration modulation must be <= 0.2 of baseline.
        self.exploration_coupling_fraction = _clamp(
            _safe_float(self.exploration_coupling_fraction, 0.2),
            0.0,
            0.2,
        )
        self.stress_dip_gain = _clamp(_safe_float(self.stress_dip_gain, 0.35), 0.0, 1.0)
        self.exploration_unfreeze_floor = _clamp(
            _safe_float(self.exploration_unfreeze_floor, 0.02),
            0.0,
            0.05,
        )

    def update_tonic_from_cer(self, stress_level: float) -> float:
        """
        CER stress regulates tonic baseline target, not an instant tonic jump.
        """
        stress = _clamp(_safe_float(stress_level, 0.0), 0.0, 1.0)
        self.tonic_target_base = _clamp(
            self.tonic_baseline * (1.0 - (0.35 * stress)),
            0.0,
            1.0,
        )
        return self.tonic_target_base

    def compute_td_error(
        self,
        reward: float,
        value_current: float,
        value_next: float,
        gamma: float,
        delta_max: Optional[float] = None,
        cer_stress_level: Optional[float] = None,
    ) -> Dict[str, float]:
        gamma_v = _clamp(_safe_float(gamma, 0.95), 0.0, 0.999)
        current_v = _safe_float(value_current, 0.0)
        next_v = _safe_float(value_next, 0.0)
        reward_v = _safe_float(reward, 0.0)
        stress_v = _clamp(_safe_float(cer_stress_level, 0.0), 0.0, 1.0)

        delta = reward_v + (gamma_v * next_v) - current_v
        delta_modulated = delta
        if delta_modulated < 0.0 and self.stress_dip_gain > 0.0:
            delta_modulated = delta_modulated * (1.0 + (self.stress_dip_gain * stress_v))
        max_abs = _clamp(_safe_float(delta_max, self.delta_max), 0.05, 10.0)
        delta_clipped = _clamp(delta_modulated, -max_abs, max_abs)
        abs_delta = abs(delta_clipped)
        if delta_clipped > 1e-12:
            delta_sign = 1
        elif delta_clipped < -1e-12:
            delta_sign = -1
        else:
            delta_sign = 0

        # Slow tonic adaptation from phasic mean (spec: k ~= 0.01).
        self.update_tonic_from_cer(stress_v)
        self.phasic_mean = _clamp(
            self.phasic_mean + (self.tonic_slow_rate * (delta_clipped - self.phasic_mean)),
            -1.0,
            1.0,
        )
        tonic_target = _clamp(self.tonic_target_base + self.phasic_mean, 0.0, 1.0)
        self.tonic_level = _clamp(
            self.tonic_level + (self.tonic_slow_rate * (tonic_target - self.tonic_level)),
            0.0,
            1.0,
        )

        return {
            "delta": float(delta),
            "delta_modulated": float(delta_modulated),
            "delta_clipped": float(delta_clipped),
            "abs_delta": float(abs_delta),
            "delta_sign": int(delta_sign),
            "phasic_burst": float(delta_clipped),
            "mean_phasic": float(self.phasic_mean),
            "tonic_target": float(tonic_target),
            "tonic_level": float(self.tonic_level),
        }

    def compute_exploration_delta(self, delta_sign: int, baseline_exploration: float) -> float:
        """
        Positive burst lowers exploration, negative dip increases it.
        """
        baseline = max(0.0, _safe_float(baseline_exploration, 0.0))
        if baseline <= 1e-9:
            delta_cap = float(self.exploration_unfreeze_floor)
        else:
            delta_cap = baseline * float(self.exploration_coupling_fraction)
        if int(delta_sign) > 0:
            return -delta_cap
        if int(delta_sign) < 0:
            return delta_cap
        return 0.0


@dataclass
class ValueLayer:
    """
    Tabular value layer with bounded TD updates.
    """

    max_states: int = 50_000
    similarity_k: int = 3
    similarity_threshold: float = 0.85
    similarity_max_scan: int = 500
    similarity_bucket_bits: int = 12
    similarity_bucket_radius: int = 1
    similarity_index_max_candidates: int = 512
    similarity_confidence_transfer: float = 0.5
    similarity_transfer_quantile: float = 0.5
    # Legacy alias kept for backward compatibility with old saves/callers.
    alpha_default: float = 0.03
    alpha_online_default: float = 0.03
    # None derives alpha_sleep from alpha_online * alpha_sleep_ratio (spec ≤ 0.25).
    alpha_sleep_default: Optional[float] = None
    alpha_sleep_ratio: float = ALPHA_SLEEP_RATIO_MAX
    # Phase 6.1 ACh settings.
    ach_alpha_gain: float = 0.4
    alpha_online_soft_cap: float = 0.15
    gamma_default: float = 0.95
    dopamine_scale: float = 0.5
    reward_scale: float = 1.0
    max_update_l2: float = 0.1
    td_clip_online: float = 1.0
    adaptive_td_clip_enabled: bool = True
    td_clip_target_rate: float = 0.2
    td_clip_adapt_rate: float = 0.05
    td_clip_ema_beta: float = 0.05
    td_clip_min_online: float = 0.05
    td_clip_max_online: float = 3.0
    # Phase 5 EDPC (Expectation-Driven Predictive Consolidation).
    expectation_ema_beta: float = 0.10
    expectation_var_ema_beta: float = 0.10
    confirmation_threshold: float = 0.15
    confirmation_decay: float = 0.90
    confidence_k1: float = 0.45
    confidence_k2: float = 4.0
    stability_growth_rate: float = 0.03
    stability_decay_rate: float = 0.08
    stability_damping: float = 0.80
    shock_confidence_threshold: float = 0.75
    shock_delta_threshold: float = 0.60
    shock_plasticity_boost: float = 0.60
    shock_replay_gain: float = 1.0
    shock_frequency_beta: float = 0.05
    alpha_trajectory_window: int = 256
    td_layer: DopaminergicTDLayer = field(default_factory=DopaminergicTDLayer)
    encoder: StateEncoder = field(default_factory=StateEncoder)

    values: "OrderedDict[str, float]" = field(default_factory=OrderedDict)
    expectation_memory: "OrderedDict[str, Dict[str, float]]" = field(default_factory=OrderedDict)
    last_update_ts: Optional[float] = None
    last_state_key: str = ""
    last_next_state_key: str = ""
    last_td_error: float = 0.0
    last_value: float = 0.0
    last_dopamine_delta: float = 0.0
    last_reward_raw: float = 0.0
    last_reward_scaled: float = 0.0
    last_delta_raw: float = 0.0
    last_delta_modulated: float = 0.0
    last_delta_clipped: float = 0.0
    last_td_was_clipped: bool = False
    last_td_clip_value_used: float = 1.0
    last_abs_delta: float = 0.0
    last_delta_sign: int = 0
    last_tonic_level: float = 0.1
    last_exploration_delta: float = 0.0
    online_td_clip_count: int = 0
    online_td_clip_updates: int = 0
    online_td_clip_frequency: float = 0.0
    online_td_clip_frequency_ema: float = 0.0
    last_alpha_effective: float = 0.0
    last_acetylcholine: float = 0.0
    last_expected_reward_mean: float = 0.0
    last_expected_reward_var: float = 0.0
    last_confirmation_count: float = 0.0
    last_confidence_score: float = 0.0
    last_stability_score: float = 0.0
    last_surprise: float = 0.0
    last_prediction_shock: bool = False
    last_replay_priority: float = 0.0
    last_consolidation_weight: float = 0.0
    shock_count_total: int = 0
    shock_frequency_ema: float = 0.0
    alpha_effective_trajectory: List[float] = field(default_factory=list)
    update_count: int = 0
    online_update_count: int = 0
    sleep_update_count: int = 0

    last_error_likelihood: float = 0.0
    last_prediction_shock_score: float = 0.0
    last_similar_state_count: int = 0
    last_similarity_scan_count: int = 0

    _similarity_bucket_index: Dict[str, "OrderedDict[str, Mapping[str, Any]]"] = field(
        default_factory=dict, init=False, repr=False
    )
    _similarity_key_to_bucket: Dict[str, str] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        legacy_alpha = _safe_float(self.alpha_default, 0.03)
        online_alpha = _safe_float(self.alpha_online_default, legacy_alpha)
        # If only legacy alpha was customized, preserve it.
        if math.isclose(online_alpha, 0.03, abs_tol=1e-12) and not math.isclose(
            legacy_alpha,
            0.03,
            abs_tol=1e-12,
        ):
            online_alpha = legacy_alpha

        self.alpha_online_soft_cap = _clamp(
            _safe_float(self.alpha_online_soft_cap, 0.15),
            0.1,
            0.3,
        )
        self.similarity_k = max(1, min(5, int(_safe_float(self.similarity_k, 3))))
        self.similarity_threshold = _clamp(
            _safe_float(self.similarity_threshold, 0.85),
            0.0,
            1.0,
        )
        self.similarity_max_scan = max(0, int(_safe_float(self.similarity_max_scan, 500)))
        self.similarity_bucket_bits = max(4, min(32, int(_safe_float(self.similarity_bucket_bits, 12))))
        self.similarity_bucket_radius = max(0, min(1, int(_safe_float(self.similarity_bucket_radius, 1))))
        self.similarity_index_max_candidates = max(
            16,
            int(_safe_float(self.similarity_index_max_candidates, 512)),
        )
        self.similarity_confidence_transfer = _clamp(
            _safe_float(self.similarity_confidence_transfer, 0.5),
            0.05,
            1.0,
        )
        self.similarity_transfer_quantile = _clamp(
            _safe_float(self.similarity_transfer_quantile, 0.5),
            0.0,
            1.0,
        )
        self.ach_alpha_gain = _clamp(_safe_float(self.ach_alpha_gain, 0.4), 0.0, 2.0)
        self.alpha_online_default = _clamp(online_alpha, 0.001, float(self.alpha_online_soft_cap))
        self.alpha_default = float(self.alpha_online_default)
        self.alpha_sleep_ratio = alpha_sleep_ratio_value(self.alpha_sleep_ratio)
        # None means derive from the live alpha_online * ratio. Do not bake that
        # product here: AgentFactory writes gene lr_alpha_online after construction,
        # and a stored 0.0075 would then cap every faster gene. An explicit rate is
        # kept as a request and capped later by effective_alpha_sleep.
        if self.alpha_sleep_default is not None:
            stored_sleep = _safe_float(self.alpha_sleep_default, -1.0)
            if not math.isfinite(stored_sleep) or stored_sleep < 0.0:
                self.alpha_sleep_default = None
            else:
                self.alpha_sleep_default = stored_sleep
        self.gamma_default = _clamp(_safe_float(self.gamma_default, 0.95), 0.0, 0.999)
        self.dopamine_scale = _clamp(_safe_float(self.dopamine_scale, 0.5), 0.0, 2.0)
        self.reward_scale = _clamp(_safe_float(self.reward_scale, 1.0), 1e-6, 1000.0)
        self.max_update_l2 = _clamp(_safe_float(self.max_update_l2, 0.1), 0.001, 1.0)
        self.td_clip_online = _clamp(_safe_float(self.td_clip_online, 1.0), 0.05, 1.0)
        self.adaptive_td_clip_enabled = bool(self.adaptive_td_clip_enabled)
        self.td_clip_target_rate = _clamp(_safe_float(self.td_clip_target_rate, 0.2), 0.01, 0.9)
        self.td_clip_adapt_rate = _clamp(_safe_float(self.td_clip_adapt_rate, 0.05), 0.001, 0.5)
        self.td_clip_ema_beta = _clamp(_safe_float(self.td_clip_ema_beta, 0.05), 0.001, 1.0)
        self.td_clip_min_online = _clamp(_safe_float(self.td_clip_min_online, 0.05), 0.01, 1.0)
        self.td_clip_max_online = _clamp(_safe_float(self.td_clip_max_online, 1.0), 0.05, 1.0)
        if self.td_clip_max_online < self.td_clip_min_online:
            self.td_clip_max_online = self.td_clip_min_online
        self.td_clip_online = _clamp(self.td_clip_online, self.td_clip_min_online, self.td_clip_max_online)
        if not isinstance(self.td_layer, DopaminergicTDLayer):
            self.td_layer = DopaminergicTDLayer(delta_max=self.td_clip_online)
        self.td_layer.delta_max = _clamp(_safe_float(self.td_layer.delta_max, self.td_clip_online), 0.05, 10.0)
        self.last_reward_raw = _safe_float(self.last_reward_raw, 0.0)
        self.last_reward_scaled = _safe_float(self.last_reward_scaled, 0.0)
        self.last_delta_raw = _safe_float(self.last_delta_raw, 0.0)
        self.last_delta_modulated = _safe_float(self.last_delta_modulated, self.last_delta_raw)
        self.last_delta_clipped = _safe_float(self.last_delta_clipped, 0.0)
        self.last_td_was_clipped = bool(self.last_td_was_clipped)
        self.last_td_clip_value_used = _clamp(
            _safe_float(self.last_td_clip_value_used, self.td_clip_online),
            self.td_clip_min_online,
            self.td_clip_max_online,
        )
        self.last_abs_delta = max(0.0, _safe_float(self.last_abs_delta, 0.0))
        self.last_delta_sign = int(_safe_float(self.last_delta_sign, 0.0))
        self.last_tonic_level = _clamp(_safe_float(self.last_tonic_level, self.td_layer.tonic_level), 0.0, 1.0)
        self.last_exploration_delta = _safe_float(self.last_exploration_delta, 0.0)
        self.online_td_clip_count = max(0, int(_safe_float(self.online_td_clip_count, 0.0)))
        self.online_td_clip_updates = max(0, int(_safe_float(self.online_td_clip_updates, 0.0)))
        if self.online_td_clip_updates > 0:
            self.online_td_clip_frequency = _clamp(
                _safe_float(self.online_td_clip_frequency, self.online_td_clip_count / float(self.online_td_clip_updates)),
                0.0,
                1.0,
            )
        else:
            self.online_td_clip_frequency = 0.0
        self.online_td_clip_frequency_ema = _clamp(_safe_float(self.online_td_clip_frequency_ema, 0.0), 0.0, 1.0)
        self.online_update_count = max(0, int(_safe_float(self.online_update_count, 0.0)))
        self.sleep_update_count = max(0, int(_safe_float(self.sleep_update_count, 0.0)))
        stored_total = max(0, int(_safe_float(self.update_count, 0.0)))
        split_total = self.online_update_count + self.sleep_update_count
        self.update_count = max(stored_total, split_total)
        self.expectation_ema_beta = _clamp(_safe_float(self.expectation_ema_beta, 0.10), 0.01, 1.0)
        self.expectation_var_ema_beta = _clamp(_safe_float(self.expectation_var_ema_beta, 0.10), 0.01, 1.0)
        self.confirmation_threshold = max(0.0, _safe_float(self.confirmation_threshold, 0.15))
        self.confirmation_decay = _clamp(_safe_float(self.confirmation_decay, 0.90), 0.0, 1.0)
        self.confidence_k1 = max(0.0, _safe_float(self.confidence_k1, 0.45))
        self.confidence_k2 = max(0.0, _safe_float(self.confidence_k2, 4.0))
        self.stability_growth_rate = max(0.0, _safe_float(self.stability_growth_rate, 0.03))
        self.stability_decay_rate = max(0.0, _safe_float(self.stability_decay_rate, 0.08))
        self.stability_damping = _clamp(_safe_float(self.stability_damping, 0.80), 0.0, 1.0)
        self.shock_confidence_threshold = _clamp(
            _safe_float(self.shock_confidence_threshold, 0.75),
            0.0,
            1.0,
        )
        self.shock_delta_threshold = max(0.0, _safe_float(self.shock_delta_threshold, 0.60))
        self.shock_plasticity_boost = max(0.0, _safe_float(self.shock_plasticity_boost, 0.60))
        self.shock_replay_gain = max(0.0, _safe_float(self.shock_replay_gain, 1.0))
        self.shock_frequency_beta = _clamp(_safe_float(self.shock_frequency_beta, 0.05), 0.001, 1.0)
        self.alpha_trajectory_window = max(16, int(_safe_float(self.alpha_trajectory_window, 256)))
        if not isinstance(self.expectation_memory, OrderedDict):
            converted_memory: "OrderedDict[str, Dict[str, float]]" = OrderedDict()
            raw_memory = self.expectation_memory if isinstance(self.expectation_memory, Mapping) else {}
            for key, profile in dict(raw_memory or {}).items():
                if not isinstance(profile, Mapping):
                    continue
                expected_mean = _safe_float(profile.get("expected_reward_mean"), 0.0)
                shock_score, shock_flag = _normalize_shock_fields(profile)
                error_likelihood = _clamp(
                    _safe_float(profile.get("error_likelihood"), shock_score),
                    0.0,
                    1.0,
                )
                converted_profile = {
                    "expected_reward_mean": expected_mean,
                    "expected_reward_var": max(0.0, _safe_float(profile.get("expected_reward_var"), 0.0)),
                    "confirmation_count": max(0.0, _safe_float(profile.get("confirmation_count"), 0.0)),
                    "confidence_score": _clamp(_safe_float(profile.get("confidence_score"), 0.0), 0.0, 1.0),
                    "stability_score": _clamp(_safe_float(profile.get("stability_score"), 0.0), 0.0, 1.0),
                    "surprise": max(0.0, _safe_float(profile.get("surprise"), 0.0)),
                    "prediction_shock": shock_score,
                    "prediction_shock_flag": bool(shock_flag),
                    "error_likelihood": error_likelihood,
                    "replay_priority": max(0.0, _safe_float(profile.get("replay_priority"), 0.0)),
                    "consolidation_weight": _clamp(
                        _safe_float(profile.get("consolidation_weight"), 0.0),
                        0.0,
                        1.0,
                    ),
                    "shock_replay_boost": max(1.0, _safe_float(profile.get("shock_replay_boost"), 1.0)),
                    "predicted_value": _safe_float(profile.get("predicted_value"), expected_mean),
                    "last_updated_step": int(_safe_float(profile.get("last_updated_step"), 0.0)),
                }
                state_vector = profile.get("state_vector")
                if isinstance(state_vector, list) and state_vector:
                    converted_profile["state_vector"] = [float(x) for x in state_vector]
                state_features = profile.get("state_features")
                if isinstance(state_features, Mapping):
                    converted_profile["state_features"] = dict(state_features)
                converted_memory[str(key)] = converted_profile
            self.expectation_memory = converted_memory
        while len(self.expectation_memory) > self.max_states:
            self.expectation_memory.popitem(last=False)
        self._rebuild_similarity_index()
        self.last_expected_reward_mean = _safe_float(self.last_expected_reward_mean, 0.0)
        self.last_expected_reward_var = max(0.0, _safe_float(self.last_expected_reward_var, 0.0))
        self.last_confirmation_count = max(0.0, _safe_float(self.last_confirmation_count, 0.0))
        self.last_confidence_score = _clamp(_safe_float(self.last_confidence_score, 0.0), 0.0, 1.0)
        self.last_stability_score = _clamp(_safe_float(self.last_stability_score, 0.0), 0.0, 1.0)
        self.last_surprise = max(0.0, _safe_float(self.last_surprise, 0.0))
        self.last_prediction_shock = bool(self.last_prediction_shock)
        self.last_prediction_shock_score = _clamp(
            _safe_float(self.last_prediction_shock_score, 1.0 if self.last_prediction_shock else 0.0),
            0.0,
            1.0,
        )
        self.last_error_likelihood = _clamp(_safe_float(self.last_error_likelihood, 0.0), 0.0, 1.0)
        self.last_similar_state_count = max(0, int(_safe_float(self.last_similar_state_count, 0.0)))
        self.last_similarity_scan_count = max(0, int(_safe_float(self.last_similarity_scan_count, 0.0)))
        self.last_replay_priority = max(0.0, _safe_float(self.last_replay_priority, 0.0))
        self.last_consolidation_weight = _clamp(
            _safe_float(self.last_consolidation_weight, 0.0),
            0.0,
            1.0,
        )
        self.shock_count_total = max(0, int(_safe_float(self.shock_count_total, 0.0)))
        self.shock_frequency_ema = _clamp(_safe_float(self.shock_frequency_ema, 0.0), 0.0, 1.0)
        if not isinstance(self.alpha_effective_trajectory, list):
            self.alpha_effective_trajectory = []
        self.alpha_effective_trajectory = [
            _safe_float(value, self.last_alpha_effective) for value in self.alpha_effective_trajectory[-self.alpha_trajectory_window :]
        ]

    def _clip_update_delta(self, update_delta: float) -> float:
        delta = _safe_float(update_delta, 0.0)
        if not math.isfinite(delta):
            return 0.0
        limit = float(self.max_update_l2)
        if abs(delta) > limit:
            return math.copysign(limit, delta)
        return delta

    def _backup_delta(
        self,
        reward: float,
        value_current: float,
        value_next: float,
        gamma: float,
        alpha: float,
        td_clip: float,
        cer_stress: float,
    ) -> float:
        """Size of one TD backup, without touching tonic or phasic state."""
        delta = _safe_float(reward, 0.0) + (_safe_float(gamma, 0.0) * _safe_float(value_next, 0.0))
        delta -= _safe_float(value_current, 0.0)
        stress = _clamp(_safe_float(cer_stress, 0.0), 0.0, 1.0)
        if delta < 0.0 and float(self.td_layer.stress_dip_gain) > 0.0:
            delta = delta * (1.0 + (float(self.td_layer.stress_dip_gain) * stress))
        clipped = _clamp(delta, -abs(float(td_clip)), abs(float(td_clip)))
        return self._clip_update_delta(float(alpha) * clipped)

    def update(
        self,
        state_snapshot: Mapping[str, Any],
        reward: float,
        next_state_snapshot: Mapping[str, Any],
        gamma: float = 0.95,
        alpha: Optional[float] = None,
        timestamp: Optional[float] = None,
        stability_index: Optional[float] = None,
        mode: str = "online",
        acetylcholine: Optional[float] = None,
        acetylcholine_baseline: Optional[float] = None,
        acc_learning_boost: Optional[float] = None,
        cer_stress_level: Optional[float] = None,
        exploration_baseline: Optional[float] = None,
        reward_scale: Optional[float] = None,
        terminal: bool = False,
        bootstrap_value: Optional[float] = None,
        prior_value: Optional[float] = None,
        replaced_reward: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Update V(s) using TD error.

        Returns:
            {
              "value": float,
              "td_error": float,
              "state_key": str
            }
        """
        # Waking callers must not reach this writer. Agent steps record the
        # outcome on the labile tier. ``mode="online"`` remains the stable
        # TD implementation used by sleep-scoped tests until expectation
        # profiles move into replay.
        from learning_guard import assert_learning_allowed

        if not assert_learning_allowed("ValueLayer.update"):
            return {
                "value": self.last_value,
                "td_error": self.last_td_error,
                "state_key": self.last_state_key,
                "mode": "skipped",
                "skipped": True,
            }

        mode_v = str(mode or "online").strip().lower()
        if mode_v not in {"online", "sleep"}:
            mode_v = "online"

        ts = _safe_float(timestamp, time.time())
        if mode_v == "online" and self.last_update_ts is not None and ts == self.last_update_ts:
            return {
                "value": self.last_value,
                "td_error": self.last_td_error,
                "reward_raw": self.last_reward_raw,
                "reward_scaled": self.last_reward_scaled,
                "delta": self.last_delta_raw,
                "delta_modulated": self.last_delta_modulated,
                "delta_clipped": self.last_delta_clipped,
                "td_was_clipped": bool(self.last_td_was_clipped),
                "td_clip_value": float(self.last_td_clip_value_used),
                "td_clip_frequency": float(self.online_td_clip_frequency),
                "td_clip_frequency_ema": float(self.online_td_clip_frequency_ema),
                "abs_delta": self.last_abs_delta,
                "delta_sign": int(self.last_delta_sign),
                "phasic_burst": self.last_delta_clipped,
                "phasic_delta": self.last_delta_clipped,
                "mean_phasic": float(getattr(self.td_layer, "phasic_mean", 0.0)),
                "tonic_level": self.last_tonic_level,
                "exploration_delta": float(self.last_exploration_delta),
                "affective_impulse": {
                    "valence": _clamp(math.tanh(float(self.last_td_error or 0.0)) * 0.15, -1.0, 1.0),
                    "stress": _clamp(max(0.0, -float(self.last_td_error or 0.0)) * 0.15, 0.0, 1.0),
                    "curiosity": _clamp(abs(float(self.last_td_error or 0.0)) * 0.15, 0.0, 1.0),
                },
                "state_key": self.last_state_key,
                "mode": mode_v,
                "alpha_effective": float(self.last_alpha_effective),
                "acetylcholine": float(self.last_acetylcholine),
                "expected_reward_mean": float(self.last_expected_reward_mean),
                "expected_reward_var": float(self.last_expected_reward_var),
                "confirmation_count": float(self.last_confirmation_count),
                "confidence_score": float(self.last_confidence_score),
                "stability_score": float(self.last_stability_score),
                "surprise": float(self.last_surprise),
                "prediction_shock": bool(self.last_prediction_shock),
                "prediction_shock_score": float(self.last_prediction_shock_score),
                "error_likelihood": float(self.last_error_likelihood),
                "replay_priority": float(self.last_replay_priority),
                "consolidation_weight": float(self.last_consolidation_weight),
                "shock_replay_boost": float(
                    1.0 + (self.shock_replay_gain if self.last_prediction_shock else 0.0)
                ),
            }

        gamma_v = _clamp(_safe_float(gamma, self.gamma_default), 0.0, 0.999)
        acc_boost = _clamp(_safe_float(acc_learning_boost, 1.0), 0.5, 1.6)
        cer_stress = _clamp(_safe_float(cer_stress_level, 0.0), 0.0, 1.0)
        stress_scale = max(0.2, 1.0 - (0.5 * cer_stress))
        if mode_v == "sleep":
            alpha_default = effective_alpha_sleep(
                self.alpha_online_default,
                self.alpha_sleep_default,
                self.alpha_sleep_ratio,
            )
        else:
            alpha_default = self.alpha_online_default
        alpha_input = _safe_float(alpha, alpha_default) * acc_boost * stress_scale
        reward_raw = _safe_float(reward)
        reward_scale_v = _clamp(_safe_float(reward_scale, self.reward_scale), 1e-6, 1000.0)
        reward_v = reward_raw * reward_scale_v

        state_key = self.encoder.encode(state_snapshot or {})
        next_state_key = self.encoder.encode(next_state_snapshot or {})
        state_vector = self._state_vector_from_snapshot(state_snapshot)

        stored_current = self._get_value(state_key)
        # A revised rating replaces one backup inside the current Q.
        # The TD of that backup is still measured from the value that
        # existed before the backup, but the table is not rewritten from it.
        revising = prior_value is not None and replaced_reward is not None
        # Unit-reward return bound 1/(1-γ). Do not rescale the reward.
        value_bound = self.value_abs_bound()
        if revising:
            current_value = _clamp(_safe_float(prior_value), -value_bound, value_bound)
        else:
            current_value = stored_current
        next_value = self._get_value(next_state_key)
        if bool(terminal):
            next_value = 0.0
        elif bootstrap_value is not None:
            # max_a Q(s', a) for the real successor, not the unread action="" key.
            next_value = _clamp(_safe_float(bootstrap_value), -value_bound, value_bound)

        td_clip = min(1.0, float(self.td_clip_online)) if mode_v == "online" else 1.0
        td_profile = self.td_layer.compute_td_error(
            reward=reward_v,
            value_current=current_value,
            value_next=next_value,
            gamma=gamma_v,
            delta_max=td_clip,
            cer_stress_level=cer_stress,
        )
        td_raw = float(td_profile["delta"])
        td_modulated = float(td_profile.get("delta_modulated", td_raw))
        td_error = float(td_profile["delta_clipped"])
        td_was_clipped = abs(td_modulated - td_error) > 1e-12
        abs_delta = float(td_profile["abs_delta"])
        delta_sign = int(td_profile["delta_sign"])
        phasic_burst = float(td_profile["phasic_burst"])
        mean_phasic = float(td_profile.get("mean_phasic", getattr(self.td_layer, "phasic_mean", 0.0)))
        tonic_level = float(td_profile.get("tonic_level", getattr(self.td_layer, "tonic_level", self.last_tonic_level)))
        exploration_delta = self.td_layer.compute_exploration_delta(
            delta_sign=delta_sign,
            baseline_exploration=_safe_float(exploration_baseline, 0.1),
        )
        if mode_v == "online":
            expectation_profile = self._update_expectation_profile(
                state_key=state_key,
                reward=reward_raw,
                delta_raw=td_raw,
                step_marker=ts,
                state_snapshot=state_snapshot,
                state_vector=state_vector,
            )
        else:
            expectation_profile = self._get_expectation_profile(
                state_key,
                state_snapshot=state_snapshot,
            )
            self._set_last_expectation_metrics(expectation_profile)
            self.last_prediction_shock = False
        confidence_score = _clamp(
            _safe_float(expectation_profile.get("confidence_score"), self.last_confidence_score),
            0.0,
            1.0,
        )
        stability_score = _clamp(
            _safe_float(expectation_profile.get("stability_score"), self.last_stability_score),
            0.0,
            1.0,
        )
        shock_score, shock_flag = _normalize_shock_fields(expectation_profile)
        prediction_shock_score = float(shock_score)
        prediction_shock = bool(shock_flag) if mode_v == "online" else False
        error_likelihood = _clamp(
            _safe_float(expectation_profile.get("error_likelihood"), prediction_shock_score),
            0.0,
            1.0,
        )
        replay_priority = max(0.0, _safe_float(expectation_profile.get("replay_priority"), 0.0))
        consolidation_weight = _clamp(
            _safe_float(expectation_profile.get("consolidation_weight"), 0.0),
            0.0,
            1.0,
        )
        shock_replay_boost = max(
            1.0,
            _safe_float(
                expectation_profile.get("shock_replay_boost"),
                1.0 + (self.shock_replay_gain if prediction_shock else 0.0),
            ),
        )
        alpha_v = self._resolve_alpha(
            alpha=alpha_input,
            stability_index=stability_index,
            mode=mode_v,
            acetylcholine=acetylcholine,
            acetylcholine_baseline=acetylcholine_baseline,
            confidence_score=confidence_score,
            stability_score=stability_score,
            prediction_shock=prediction_shock,
        )

        update_delta = self._clip_update_delta(alpha_v * td_error)
        applied_delta = update_delta
        if revising:
            old_delta = self._backup_delta(
                reward=_safe_float(replaced_reward) * reward_scale_v,
                value_current=current_value,
                value_next=next_value,
                gamma=gamma_v,
                alpha=alpha_v,
                td_clip=td_clip,
                cer_stress=cer_stress,
            )
            applied_delta = update_delta
            update_delta = update_delta - old_delta
            new_value = _clamp(stored_current + update_delta, -value_bound, value_bound)
        else:
            new_value = _clamp(stored_current + update_delta, -value_bound, value_bound)
        self._set_value(state_key, new_value)

        self.last_update_ts = ts
        self.last_state_key = state_key
        self.last_next_state_key = next_state_key
        self.last_td_error = td_error
        self.last_reward_raw = reward_raw
        self.last_reward_scaled = reward_v
        self.last_delta_raw = td_raw
        self.last_delta_modulated = td_modulated
        self.last_delta_clipped = td_error
        self.last_td_was_clipped = bool(td_was_clipped)
        self.last_td_clip_value_used = float(td_clip)
        self.last_abs_delta = abs_delta
        self.last_delta_sign = delta_sign
        self.last_tonic_level = tonic_level
        self.last_exploration_delta = float(exploration_delta)
        self.last_value = new_value
        self.last_applied_delta = float(applied_delta)
        self.last_dopamine_delta = self.compute_dopamine_delta(td_error=td_error)
        self.last_prediction_shock = bool(prediction_shock)
        self.last_prediction_shock_score = float(prediction_shock_score)
        self.last_error_likelihood = float(error_likelihood)
        self.last_replay_priority = float(replay_priority)
        self.last_consolidation_weight = float(consolidation_weight)
        self._track_and_adapt_td_clip(mode=mode_v, was_clipped=td_was_clipped)
        self._increment_update_counters(mode_v)
        self._append_alpha_trajectory(alpha_v)

        return {
            "value": new_value,
            "td_error": td_error,
            "reward_raw": reward_raw,
            "reward_scaled": reward_v,
            "delta": td_raw,
            "delta_modulated": td_modulated,
            "delta_clipped": td_error,
            "td_was_clipped": bool(td_was_clipped),
            "td_clip_value": float(td_clip),
            "td_clip_frequency": float(self.online_td_clip_frequency),
            "td_clip_frequency_ema": float(self.online_td_clip_frequency_ema),
            "abs_delta": abs_delta,
            "delta_sign": delta_sign,
            "phasic_burst": phasic_burst,
            "phasic_delta": phasic_burst,
            "mean_phasic": mean_phasic,
            "tonic_level": tonic_level,
            "exploration_delta": float(exploration_delta),
            "affective_impulse": {
                "valence": _clamp(math.tanh(float(td_error)) * 0.15, -1.0, 1.0),
                "stress": _clamp(max(0.0, -float(td_error)) * 0.15, 0.0, 1.0),
                "curiosity": _clamp(abs(float(td_error)) * 0.15, 0.0, 1.0),
            },
            "state_key": state_key,
            "mode": mode_v,
            "alpha_effective": float(alpha_v),
            "acetylcholine": float(self.last_acetylcholine),
            "expected_reward_mean": float(self.last_expected_reward_mean),
            "expected_reward_var": float(self.last_expected_reward_var),
            "confirmation_count": float(self.last_confirmation_count),
            "confidence_score": float(confidence_score),
            "stability_score": float(stability_score),
            "surprise": float(self.last_surprise),
            "prediction_shock": bool(prediction_shock),
            "prediction_shock_score": float(prediction_shock_score),
            "error_likelihood": float(error_likelihood),
            "replay_priority": float(replay_priority),
            "consolidation_weight": float(consolidation_weight),
            "shock_replay_boost": float(shock_replay_boost),
        }

    def get_value(self, state_snapshot: Mapping[str, Any]) -> float:
        state_key = self.encoder.encode(state_snapshot or {})
        return self._get_value(state_key)

    def compute_dopamine_delta(self, td_error: float, scale: Optional[float] = None) -> float:
        scale_v = _safe_float(scale, self.dopamine_scale)
        return _clamp(_safe_float(td_error) * scale_v, -0.1, 0.1)

    def compute_exploration_coupling(
        self,
        td_error: float,
        baseline_exploration: float,
    ) -> float:
        if td_error > 1e-12:
            delta_sign = 1
        elif td_error < -1e-12:
            delta_sign = -1
        else:
            delta_sign = 0
        return self.td_layer.compute_exploration_delta(
            delta_sign=delta_sign,
            baseline_exploration=baseline_exploration,
        )

    def snapshot(self) -> Dict[str, Any]:
        confidence_values = [
            _clamp(_safe_float(profile.get("confidence_score"), 0.0), 0.0, 1.0)
            for profile in self.expectation_memory.values()
            if isinstance(profile, Mapping)
        ]
        stability_values = [
            _clamp(_safe_float(profile.get("stability_score"), 0.0), 0.0, 1.0)
            for profile in self.expectation_memory.values()
            if isinstance(profile, Mapping)
        ]
        return {
            "value": float(self.last_value),
            "last_td_error": float(self.last_td_error),
            "last_reward_raw": float(self.last_reward_raw),
            "last_reward_scaled": float(self.last_reward_scaled),
            "last_delta_raw": float(self.last_delta_raw),
            "last_delta_modulated": float(self.last_delta_modulated),
            "last_delta_clipped": float(self.last_delta_clipped),
            "last_td_was_clipped": bool(self.last_td_was_clipped),
            "last_td_clip_value_used": float(self.last_td_clip_value_used),
            "last_abs_delta": float(self.last_abs_delta),
            "last_delta_sign": int(self.last_delta_sign),
            "last_tonic_level": float(self.last_tonic_level),
            "last_exploration_delta": float(self.last_exploration_delta),
            "online_td_clip_count": int(self.online_td_clip_count),
            "online_td_clip_updates": int(self.online_td_clip_updates),
            "online_td_clip_frequency": float(self.online_td_clip_frequency),
            "online_td_clip_frequency_ema": float(self.online_td_clip_frequency_ema),
            "last_state_key": self.last_state_key,
            "last_next_state_key": self.last_next_state_key,
            "last_dopamine_delta": float(self.last_dopamine_delta),
            "state_count": int(len(self.values)),
            "max_states": int(self.max_states),
            "similarity_k": int(self.similarity_k),
            "similarity_threshold": float(self.similarity_threshold),
            "similarity_max_scan": int(self.similarity_max_scan),
            "similarity_bucket_bits": int(self.similarity_bucket_bits),
            "similarity_bucket_radius": int(self.similarity_bucket_radius),
            "similarity_index_max_candidates": int(self.similarity_index_max_candidates),
            "similarity_confidence_transfer": float(self.similarity_confidence_transfer),
            "similarity_transfer_quantile": float(self.similarity_transfer_quantile),
            "alpha_default": float(self.alpha_default),
            "alpha_online_default": float(self.alpha_online_default),
            "alpha_sleep_default": (
                None if self.alpha_sleep_default is None else float(self.alpha_sleep_default)
            ),
            "alpha_sleep_ratio": float(alpha_sleep_ratio_value(self.alpha_sleep_ratio)),
            "ach_alpha_gain": float(self.ach_alpha_gain),
            "alpha_online_soft_cap": float(self.alpha_online_soft_cap),
            "gamma_default": float(self.gamma_default),
            "reward_scale": float(self.reward_scale),
            "max_update_l2": float(self.max_update_l2),
            "td_clip_online": float(self.td_clip_online),
            "adaptive_td_clip_enabled": bool(self.adaptive_td_clip_enabled),
            "td_clip_target_rate": float(self.td_clip_target_rate),
            "td_clip_adapt_rate": float(self.td_clip_adapt_rate),
            "td_clip_ema_beta": float(self.td_clip_ema_beta),
            "td_clip_min_online": float(self.td_clip_min_online),
            "td_clip_max_online": float(self.td_clip_max_online),
            "td_delta_max": float(self.td_layer.delta_max),
            "td_tonic_baseline": float(self.td_layer.tonic_baseline),
            "td_tonic_level": float(self.td_layer.tonic_level),
            "td_tonic_slow_rate": float(self.td_layer.tonic_slow_rate),
            "td_phasic_mean": float(self.td_layer.phasic_mean),
            "td_tonic_target_base": float(self.td_layer.tonic_target_base),
            "exploration_coupling_fraction": float(self.td_layer.exploration_coupling_fraction),
            "stress_dip_gain": float(self.td_layer.stress_dip_gain),
            "exploration_unfreeze_floor": float(self.td_layer.exploration_unfreeze_floor),
            "last_alpha_effective": float(self.last_alpha_effective),
            "last_acetylcholine": float(self.last_acetylcholine),
            "last_expected_reward_mean": float(self.last_expected_reward_mean),
            "last_expected_reward_var": float(self.last_expected_reward_var),
            "last_confirmation_count": float(self.last_confirmation_count),
            "last_confidence_score": float(self.last_confidence_score),
            "last_stability_score": float(self.last_stability_score),
            "last_surprise": float(self.last_surprise),
            "last_prediction_shock": bool(self.last_prediction_shock),
            "last_prediction_shock_score": float(self.last_prediction_shock_score),
            "last_error_likelihood": float(self.last_error_likelihood),
            "last_replay_priority": float(self.last_replay_priority),
            "last_consolidation_weight": float(self.last_consolidation_weight),
            "last_similar_state_count": int(self.last_similar_state_count),
            "last_similarity_scan_count": int(self.last_similarity_scan_count),
            "expectation_memory_size": int(len(self.expectation_memory)),
            "confidence_distribution": self._distribution_summary(confidence_values),
            "stability_distribution": self._distribution_summary(stability_values),
            "shock_count_total": int(self.shock_count_total),
            "shock_frequency_ema": float(self.shock_frequency_ema),
            "shock_frequency": float(self.shock_count_total) / float(max(1, self.online_update_count)),
            "effective_alpha_trajectory": [float(value) for value in self.alpha_effective_trajectory],
            "update_count": int(self.update_count),
            "online_update_count": int(self.online_update_count),
            "sleep_update_count": int(self.sleep_update_count),
            "last_update_ts": self.last_update_ts,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_states": int(self.max_states),
            "similarity_k": int(self.similarity_k),
            "similarity_threshold": float(self.similarity_threshold),
            "similarity_max_scan": int(self.similarity_max_scan),
            "similarity_bucket_bits": int(self.similarity_bucket_bits),
            "similarity_bucket_radius": int(self.similarity_bucket_radius),
            "similarity_index_max_candidates": int(self.similarity_index_max_candidates),
            "similarity_confidence_transfer": float(self.similarity_confidence_transfer),
            "similarity_transfer_quantile": float(self.similarity_transfer_quantile),
            "alpha_default": float(self.alpha_default),
            "alpha_online_default": float(self.alpha_online_default),
            "alpha_sleep_default": (
                None if self.alpha_sleep_default is None else float(self.alpha_sleep_default)
            ),
            "alpha_sleep_ratio": float(alpha_sleep_ratio_value(self.alpha_sleep_ratio)),
            "ach_alpha_gain": float(self.ach_alpha_gain),
            "alpha_online_soft_cap": float(self.alpha_online_soft_cap),
            "gamma_default": float(self.gamma_default),
            "dopamine_scale": float(self.dopamine_scale),
            "reward_scale": float(self.reward_scale),
            "max_update_l2": float(self.max_update_l2),
            "td_clip_online": float(self.td_clip_online),
            "adaptive_td_clip_enabled": bool(self.adaptive_td_clip_enabled),
            "td_clip_target_rate": float(self.td_clip_target_rate),
            "td_clip_adapt_rate": float(self.td_clip_adapt_rate),
            "td_clip_ema_beta": float(self.td_clip_ema_beta),
            "td_clip_min_online": float(self.td_clip_min_online),
            "td_clip_max_online": float(self.td_clip_max_online),
            "expectation_ema_beta": float(self.expectation_ema_beta),
            "expectation_var_ema_beta": float(self.expectation_var_ema_beta),
            "confirmation_threshold": float(self.confirmation_threshold),
            "confirmation_decay": float(self.confirmation_decay),
            "confidence_k1": float(self.confidence_k1),
            "confidence_k2": float(self.confidence_k2),
            "stability_growth_rate": float(self.stability_growth_rate),
            "stability_decay_rate": float(self.stability_decay_rate),
            "stability_damping": float(self.stability_damping),
            "shock_confidence_threshold": float(self.shock_confidence_threshold),
            "shock_delta_threshold": float(self.shock_delta_threshold),
            "shock_plasticity_boost": float(self.shock_plasticity_boost),
            "shock_replay_gain": float(self.shock_replay_gain),
            "shock_frequency_beta": float(self.shock_frequency_beta),
            "alpha_trajectory_window": int(self.alpha_trajectory_window),
            "td_layer": {
                "delta_max": float(self.td_layer.delta_max),
                "tonic_baseline": float(self.td_layer.tonic_baseline),
                "tonic_level": float(self.td_layer.tonic_level),
                "tonic_slow_rate": float(self.td_layer.tonic_slow_rate),
                "phasic_mean": float(self.td_layer.phasic_mean),
                "tonic_target_base": float(self.td_layer.tonic_target_base),
                "exploration_coupling_fraction": float(self.td_layer.exploration_coupling_fraction),
                "stress_dip_gain": float(self.td_layer.stress_dip_gain),
                "exploration_unfreeze_floor": float(self.td_layer.exploration_unfreeze_floor),
            },
            "encoder": {
                "rounding": int(self.encoder.rounding),
                "max_text_length": int(self.encoder.max_text_length),
                "feature_keys": list(self.encoder.feature_keys),
            },
            "values": [[key, float(value)] for key, value in self.values.items()],
            "expectation_memory": [
                [str(key), dict(profile)]
                for key, profile in self.expectation_memory.items()
                if isinstance(profile, Mapping)
            ],
            "last_update_ts": self.last_update_ts,
            "last_state_key": self.last_state_key,
            "last_next_state_key": self.last_next_state_key,
            "last_td_error": float(self.last_td_error),
            "last_reward_raw": float(self.last_reward_raw),
            "last_reward_scaled": float(self.last_reward_scaled),
            "last_value": float(self.last_value),
            "last_dopamine_delta": float(self.last_dopamine_delta),
            "last_delta_raw": float(self.last_delta_raw),
            "last_delta_modulated": float(self.last_delta_modulated),
            "last_delta_clipped": float(self.last_delta_clipped),
            "last_td_was_clipped": bool(self.last_td_was_clipped),
            "last_td_clip_value_used": float(self.last_td_clip_value_used),
            "last_abs_delta": float(self.last_abs_delta),
            "last_delta_sign": int(self.last_delta_sign),
            "last_tonic_level": float(self.last_tonic_level),
            "last_exploration_delta": float(self.last_exploration_delta),
            "online_td_clip_count": int(self.online_td_clip_count),
            "online_td_clip_updates": int(self.online_td_clip_updates),
            "online_td_clip_frequency": float(self.online_td_clip_frequency),
            "online_td_clip_frequency_ema": float(self.online_td_clip_frequency_ema),
            "last_alpha_effective": float(self.last_alpha_effective),
            "last_acetylcholine": float(self.last_acetylcholine),
            "last_expected_reward_mean": float(self.last_expected_reward_mean),
            "last_expected_reward_var": float(self.last_expected_reward_var),
            "last_confirmation_count": float(self.last_confirmation_count),
            "last_confidence_score": float(self.last_confidence_score),
            "last_stability_score": float(self.last_stability_score),
            "last_surprise": float(self.last_surprise),
            "last_prediction_shock": bool(self.last_prediction_shock),
            "last_prediction_shock_score": float(self.last_prediction_shock_score),
            "last_error_likelihood": float(self.last_error_likelihood),
            "last_replay_priority": float(self.last_replay_priority),
            "last_consolidation_weight": float(self.last_consolidation_weight),
            "last_similar_state_count": int(self.last_similar_state_count),
            "last_similarity_scan_count": int(self.last_similarity_scan_count),
            "shock_count_total": int(self.shock_count_total),
            "shock_frequency_ema": float(self.shock_frequency_ema),
            "alpha_effective_trajectory": [float(value) for value in self.alpha_effective_trajectory],
            "update_count": int(self.update_count),
            "online_update_count": int(self.online_update_count),
            "sleep_update_count": int(self.sleep_update_count),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ValueLayer":
        raw = dict(data or {})
        encoder_data = dict(raw.get("encoder") or {})

        feature_keys = encoder_data.get("feature_keys")
        if not isinstance(feature_keys, (list, tuple)):
            feature_keys = list(StateEncoder().feature_keys)

        encoder = StateEncoder(
            rounding=int(encoder_data.get("rounding", 3)),
            max_text_length=int(encoder_data.get("max_text_length", 80)),
            feature_keys=tuple(str(x) for x in feature_keys),
        )

        legacy_alpha = float(raw.get("alpha_default", raw.get("alpha_online_default", 0.03)))
        td_layer_data = dict(raw.get("td_layer") or {})
        td_layer = DopaminergicTDLayer(
            delta_max=float(td_layer_data.get("delta_max", raw.get("td_clip_online", 1.0))),
            tonic_baseline=float(td_layer_data.get("tonic_baseline", 0.1)),
            tonic_level=float(td_layer_data.get("tonic_level", td_layer_data.get("tonic_baseline", 0.1))),
            tonic_slow_rate=float(td_layer_data.get("tonic_slow_rate", 0.01)),
            phasic_mean=float(td_layer_data.get("phasic_mean", 0.0)),
            tonic_target_base=float(
                td_layer_data.get(
                    "tonic_target_base",
                    td_layer_data.get("tonic_baseline", 0.1),
                )
            ),
            exploration_coupling_fraction=float(
                td_layer_data.get("exploration_coupling_fraction", 0.2)
            ),
            stress_dip_gain=float(td_layer_data.get("stress_dip_gain", 0.35)),
            exploration_unfreeze_floor=float(td_layer_data.get("exploration_unfreeze_floor", 0.02)),
        )

        inst = cls(
            max_states=int(raw.get("max_states", 50_000)),
            similarity_k=int(raw.get("similarity_k", 3)),
            similarity_threshold=float(raw.get("similarity_threshold", 0.85)),
            similarity_max_scan=int(raw.get("similarity_max_scan", 500)),
            similarity_bucket_bits=int(raw.get("similarity_bucket_bits", 12)),
            similarity_bucket_radius=int(raw.get("similarity_bucket_radius", 1)),
            similarity_index_max_candidates=int(raw.get("similarity_index_max_candidates", 512)),
            similarity_confidence_transfer=float(raw.get("similarity_confidence_transfer", 0.5)),
            similarity_transfer_quantile=float(raw.get("similarity_transfer_quantile", 0.5)),
            alpha_default=legacy_alpha,
            alpha_online_default=float(raw.get("alpha_online_default", legacy_alpha)),
            alpha_sleep_default=(
                None
                if raw.get("alpha_sleep_default") is None
                else float(raw.get("alpha_sleep_default"))
            ),
            alpha_sleep_ratio=float(raw.get("alpha_sleep_ratio", ALPHA_SLEEP_RATIO_MAX)),
            ach_alpha_gain=float(raw.get("ach_alpha_gain", 0.4)),
            alpha_online_soft_cap=float(raw.get("alpha_online_soft_cap", 0.15)),
            gamma_default=float(raw.get("gamma_default", 0.95)),
            dopamine_scale=float(raw.get("dopamine_scale", 0.5)),
            reward_scale=float(raw.get("reward_scale", 1.0)),
            max_update_l2=float(raw.get("max_update_l2", 0.1)),
            td_clip_online=float(raw.get("td_clip_online", 1.0)),
            adaptive_td_clip_enabled=bool(raw.get("adaptive_td_clip_enabled", True)),
            td_clip_target_rate=float(raw.get("td_clip_target_rate", 0.2)),
            td_clip_adapt_rate=float(raw.get("td_clip_adapt_rate", 0.05)),
            td_clip_ema_beta=float(raw.get("td_clip_ema_beta", 0.05)),
            td_clip_min_online=float(raw.get("td_clip_min_online", 0.05)),
            td_clip_max_online=float(raw.get("td_clip_max_online", 3.0)),
            expectation_ema_beta=float(raw.get("expectation_ema_beta", 0.10)),
            expectation_var_ema_beta=float(raw.get("expectation_var_ema_beta", 0.10)),
            confirmation_threshold=float(raw.get("confirmation_threshold", 0.15)),
            confirmation_decay=float(raw.get("confirmation_decay", 0.90)),
            confidence_k1=float(raw.get("confidence_k1", 0.45)),
            confidence_k2=float(raw.get("confidence_k2", 4.0)),
            stability_growth_rate=float(raw.get("stability_growth_rate", 0.03)),
            stability_decay_rate=float(raw.get("stability_decay_rate", 0.08)),
            stability_damping=float(raw.get("stability_damping", 0.80)),
            shock_confidence_threshold=float(raw.get("shock_confidence_threshold", 0.75)),
            shock_delta_threshold=float(raw.get("shock_delta_threshold", 0.60)),
            shock_plasticity_boost=float(raw.get("shock_plasticity_boost", 0.60)),
            shock_replay_gain=float(raw.get("shock_replay_gain", 1.0)),
            shock_frequency_beta=float(raw.get("shock_frequency_beta", 0.05)),
            alpha_trajectory_window=int(raw.get("alpha_trajectory_window", 256)),
            td_layer=td_layer,
            encoder=encoder,
        )

        values_data = raw.get("values") or []
        if isinstance(values_data, dict):
            values_data = list(values_data.items())

        from learning_guard import initializing

        with initializing():
            for item in values_data:
                if not isinstance(item, (list, tuple)) or len(item) != 2:
                    continue
                state_key = str(item[0])
                value_bound = inst.value_abs_bound()
                value = _clamp(_safe_float(item[1]), -value_bound, value_bound)
                inst._set_value(state_key, value)
        expectation_data = raw.get("expectation_memory") or []
        if isinstance(expectation_data, Mapping):
            expectation_data = list(expectation_data.items())
        for item in expectation_data:
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                continue
            state_key = str(item[0])
            profile = item[1]
            if not isinstance(profile, Mapping):
                continue
            expected_mean = _safe_float(profile.get("expected_reward_mean"), 0.0)
            shock_score, shock_flag = _normalize_shock_fields(profile)
            error_likelihood = _clamp(
                _safe_float(profile.get("error_likelihood"), shock_score),
                0.0,
                1.0,
            )
            converted_profile = {
                "expected_reward_mean": expected_mean,
                "expected_reward_var": max(0.0, _safe_float(profile.get("expected_reward_var"), 0.0)),
                "confirmation_count": max(0.0, _safe_float(profile.get("confirmation_count"), 0.0)),
                "confidence_score": _clamp(_safe_float(profile.get("confidence_score"), 0.0), 0.0, 1.0),
                "stability_score": _clamp(_safe_float(profile.get("stability_score"), 0.0), 0.0, 1.0),
                "surprise": max(0.0, _safe_float(profile.get("surprise"), 0.0)),
                "prediction_shock": shock_score,
                "prediction_shock_flag": bool(shock_flag),
                "error_likelihood": error_likelihood,
                "replay_priority": max(0.0, _safe_float(profile.get("replay_priority"), 0.0)),
                "consolidation_weight": _clamp(_safe_float(profile.get("consolidation_weight"), 0.0), 0.0, 1.0),
                "shock_replay_boost": max(1.0, _safe_float(profile.get("shock_replay_boost"), 1.0)),
                "predicted_value": _safe_float(profile.get("predicted_value"), expected_mean),
                "last_updated_step": int(_safe_float(profile.get("last_updated_step"), 0.0)),
            }
            state_vector = profile.get("state_vector")
            if isinstance(state_vector, list) and state_vector:
                converted_profile["state_vector"] = [float(x) for x in state_vector]
            state_features = profile.get("state_features")
            if isinstance(state_features, Mapping):
                converted_profile["state_features"] = dict(state_features)
            inst.expectation_memory[state_key] = converted_profile
            inst.expectation_memory.move_to_end(state_key)
        while len(inst.expectation_memory) > inst.max_states:
            inst.expectation_memory.popitem(last=False)

        inst.last_update_ts = raw.get("last_update_ts")
        inst.last_state_key = str(raw.get("last_state_key", ""))
        inst.last_next_state_key = str(raw.get("last_next_state_key", ""))
        inst.last_td_error = _clamp(_safe_float(raw.get("last_td_error")), -1.0, 1.0)
        inst.last_reward_raw = _safe_float(raw.get("last_reward_raw"), 0.0)
        inst.last_reward_scaled = _safe_float(raw.get("last_reward_scaled"), inst.last_reward_raw)
        _value_bound = inst.value_abs_bound()
        inst.last_value = _clamp(_safe_float(raw.get("last_value")), -_value_bound, _value_bound)
        inst.last_dopamine_delta = _clamp(
            _safe_float(raw.get("last_dopamine_delta")),
            -0.1,
            0.1,
        )
        inst.last_delta_raw = _safe_float(raw.get("last_delta_raw"), inst.last_td_error)
        inst.last_delta_modulated = _safe_float(raw.get("last_delta_modulated"), inst.last_delta_raw)
        inst.last_delta_clipped = _safe_float(raw.get("last_delta_clipped"), inst.last_td_error)
        inst.last_td_was_clipped = bool(raw.get("last_td_was_clipped", False))
        inst.last_td_clip_value_used = _clamp(
            _safe_float(raw.get("last_td_clip_value_used"), inst.td_clip_online),
            inst.td_clip_min_online,
            inst.td_clip_max_online,
        )
        inst.last_abs_delta = max(0.0, _safe_float(raw.get("last_abs_delta"), abs(inst.last_td_error)))
        inst.last_delta_sign = int(
            _safe_float(
                raw.get(
                    "last_delta_sign",
                    1 if inst.last_td_error > 1e-12 else (-1 if inst.last_td_error < -1e-12 else 0),
                ),
                0.0,
            )
        )
        inst.last_tonic_level = _clamp(
            _safe_float(raw.get("last_tonic_level"), inst.td_layer.tonic_level),
            0.0,
            1.0,
        )
        inst.last_exploration_delta = _safe_float(raw.get("last_exploration_delta"), 0.0)
        inst.online_td_clip_count = max(0, int(_safe_float(raw.get("online_td_clip_count"), 0.0)))
        inst.online_td_clip_updates = max(0, int(_safe_float(raw.get("online_td_clip_updates"), 0.0)))
        inst.online_td_clip_frequency = _clamp(
            _safe_float(
                raw.get(
                    "online_td_clip_frequency",
                    (inst.online_td_clip_count / float(inst.online_td_clip_updates))
                    if inst.online_td_clip_updates > 0
                    else 0.0,
                )
            ),
            0.0,
            1.0,
        )
        inst.online_td_clip_frequency_ema = _clamp(
            _safe_float(raw.get("online_td_clip_frequency_ema"), inst.online_td_clip_frequency),
            0.0,
            1.0,
        )
        inst.last_alpha_effective = _clamp(
            _safe_float(raw.get("last_alpha_effective"), _safe_float(raw.get("alpha_online_default"), 0.03)),
            0.001,
            float(inst.alpha_online_soft_cap),
        )
        inst.last_acetylcholine = _clamp(_safe_float(raw.get("last_acetylcholine")), 0.0, 1.0)
        inst.last_expected_reward_mean = _safe_float(raw.get("last_expected_reward_mean"), 0.0)
        inst.last_expected_reward_var = max(0.0, _safe_float(raw.get("last_expected_reward_var"), 0.0))
        inst.last_confirmation_count = max(0.0, _safe_float(raw.get("last_confirmation_count"), 0.0))
        inst.last_confidence_score = _clamp(_safe_float(raw.get("last_confidence_score"), 0.0), 0.0, 1.0)
        inst.last_stability_score = _clamp(_safe_float(raw.get("last_stability_score"), 0.0), 0.0, 1.0)
        inst.last_surprise = max(0.0, _safe_float(raw.get("last_surprise"), 0.0))
        inst.last_prediction_shock = bool(raw.get("last_prediction_shock", False))
        inst.last_prediction_shock_score = _clamp(
            _safe_float(raw.get("last_prediction_shock_score"), 1.0 if inst.last_prediction_shock else 0.0),
            0.0,
            1.0,
        )
        inst.last_error_likelihood = _clamp(_safe_float(raw.get("last_error_likelihood"), 0.0), 0.0, 1.0)
        inst.last_replay_priority = max(0.0, _safe_float(raw.get("last_replay_priority"), 0.0))
        inst.last_consolidation_weight = _clamp(
            _safe_float(raw.get("last_consolidation_weight"), 0.0),
            0.0,
            1.0,
        )
        inst.last_similar_state_count = max(
            0, int(_safe_float(raw.get("last_similar_state_count"), 0.0))
        )
        inst.last_similarity_scan_count = max(
            0, int(_safe_float(raw.get("last_similarity_scan_count"), 0.0))
        )
        inst.shock_count_total = max(0, int(_safe_float(raw.get("shock_count_total"), 0.0)))
        inst.shock_frequency_ema = _clamp(_safe_float(raw.get("shock_frequency_ema"), 0.0), 0.0, 1.0)
        trajectory = raw.get("alpha_effective_trajectory", [])
        if isinstance(trajectory, list):
            inst.alpha_effective_trajectory = [
                _safe_float(value, inst.last_alpha_effective) for value in trajectory[-inst.alpha_trajectory_window :]
            ]
        else:
            inst.alpha_effective_trajectory = []
        legacy_updates = int(raw.get("update_count", 0))
        inst.online_update_count = int(raw.get("online_update_count", legacy_updates))
        inst.sleep_update_count = int(raw.get("sleep_update_count", 0))
        split_total = max(0, int(inst.online_update_count)) + max(0, int(inst.sleep_update_count))
        inst.update_count = max(legacy_updates, split_total)
        inst._rebuild_similarity_index()
        return inst

    def describe_brief(self, max_lines: int = 2) -> str:
        if len(self.values) <= 0:
            return "Value Layer: cold start (no states)"
        return (
            f"V={self.last_value:+.2f}, δ={self.last_td_error:+.2f}, "
            f"DAΔ={self.last_dopamine_delta:+.2f}, states={len(self.values)}"
        )

    def _resolve_alpha(
        self,
        alpha: Optional[float],
        stability_index: Optional[float],
        mode: str,
        acetylcholine: Optional[float] = None,
        acetylcholine_baseline: Optional[float] = None,
        confidence_score: Optional[float] = None,
        stability_score: Optional[float] = None,
        prediction_shock: bool = False,
    ) -> float:
        if mode == "sleep":
            # Spec: alpha_sleep ≤ 0.25 · alpha_online. A stored default may only be tighter.
            derived = derived_alpha_sleep(self.alpha_online_default, self.alpha_sleep_ratio)
            alpha_default = effective_alpha_sleep(
                self.alpha_online_default,
                self.alpha_sleep_default,
                self.alpha_sleep_ratio,
            )
            alpha_cap = derived
            alpha_floor = 0.0
        else:
            online_cap = max(0.1, float(self.alpha_online_soft_cap))
            self.alpha_online_default = _clamp(
                _safe_float(self.alpha_online_default, self.alpha_default),
                0.001,
                online_cap,
            )
            self.alpha_default = float(self.alpha_online_default)
            alpha_default = self.alpha_online_default
            alpha_cap = online_cap
            alpha_floor = 0.001

        if alpha_cap < alpha_floor:
            alpha_cap = alpha_floor
        alpha_v = _clamp(_safe_float(alpha, alpha_default), alpha_floor, alpha_cap)
        if stability_index is not None:
            # Under instability lower the learning rate to avoid runaway updates.
            stability = _clamp(_safe_float(stability_index, 1.0), 0.0, 1.0)
            scale = max(0.2, stability)
            alpha_v = _clamp(alpha_v * scale, alpha_floor, alpha_cap)

        ach_v = _clamp(_safe_float(acetylcholine, 0.0), 0.0, 1.0)
        if mode != "sleep":
            # Phase 6.1: only online alpha is modulated by ACh.
            ach_baseline_v = _clamp(_safe_float(acetylcholine_baseline, 0.1), 0.0, 1.0)
            ach_effective = max(0.0, ach_v - ach_baseline_v)
            ach_gain = _clamp(_safe_float(self.ach_alpha_gain, 0.4), 0.0, 2.0)
            alpha_v = alpha_v * (1.0 + (ach_gain * ach_effective))
            alpha_v = _clamp(alpha_v, alpha_floor, alpha_cap)
            if ach_v > 0.9:
                # Safety: enforce soft cap in very high ACh regime.
                alpha_v = min(alpha_v, alpha_cap)

        # EDPC selective plasticity:
        # stable and highly confident expectations should adapt slower.
        confidence_v = _clamp(_safe_float(confidence_score, 0.0), 0.0, 1.0)
        expectation_stability_v = _clamp(_safe_float(stability_score, 0.0), 0.0, 1.0)
        damping = _clamp(_safe_float(self.stability_damping, 0.80), 0.0, 1.0)
        selective_factor = 1.0 - (confidence_v * expectation_stability_v * damping)
        selective_factor = _clamp(selective_factor, 0.05, 1.0)
        alpha_v = _clamp(alpha_v * selective_factor, alpha_floor, alpha_cap)

        if bool(prediction_shock):
            shock_boost = max(0.0, _safe_float(self.shock_plasticity_boost, 0.60))
            alpha_v = _clamp(alpha_v * (1.0 + shock_boost), alpha_floor, alpha_cap)

        self.last_alpha_effective = float(alpha_v)
        self.last_acetylcholine = float(ach_v)
        return alpha_v

    def _default_expectation_profile(self) -> Dict[str, float]:
        return {
            "expected_reward_mean": 0.0,
            "expected_reward_var": 0.0,
            "confirmation_count": 0.0,
            "confidence_score": 0.0,
            "stability_score": 0.0,
            "surprise": 0.0,
            "prediction_shock": 0.0,
            "prediction_shock_flag": False,
            "error_likelihood": 0.0,
            "replay_priority": 0.0,
            "consolidation_weight": 0.0,
            "shock_replay_boost": 1.0,
            "predicted_value": 0.0,
            "last_updated_step": 0,
        }

    def _state_vector_from_snapshot(self, state_snapshot: Optional[Mapping[str, Any]]) -> List[float]:
        if isinstance(state_snapshot, Mapping):
            vector_override = state_snapshot.get("state_vector")
            if isinstance(vector_override, list) and vector_override:
                return [float(x) for x in vector_override]
            normalized = self.encoder.normalize(state_snapshot)
            return _vector_from_normalized(normalized, self.encoder.feature_keys)
        return []

    def _profile_state_vector(self, profile: Mapping[str, Any]) -> Optional[List[float]]:
        state_vector = profile.get("state_vector")
        if isinstance(state_vector, list) and state_vector:
            return [float(x) for x in state_vector]
        state_features = profile.get("state_features")
        if isinstance(state_features, Mapping):
            return _vector_from_normalized(state_features, self.encoder.feature_keys)
        return None

    def _bucket_neighbors(self, bucket_key: str) -> List[str]:
        if not bucket_key:
            return []
        radius = max(0, min(1, int(self.similarity_bucket_radius)))
        if radius <= 0:
            return [bucket_key]
        neighbors = [bucket_key]
        for idx, ch in enumerate(bucket_key):
            flipped = "1" if ch == "0" else "0"
            neighbors.append(f"{bucket_key[:idx]}{flipped}{bucket_key[idx + 1:]}")
        return neighbors

    def _remove_similarity_index_entry(self, state_key: str) -> None:
        key = str(state_key)
        bucket_key = self._similarity_key_to_bucket.pop(key, "")
        if not bucket_key:
            return
        bucket = self._similarity_bucket_index.get(bucket_key)
        if isinstance(bucket, OrderedDict):
            bucket.pop(key, None)
            if not bucket:
                self._similarity_bucket_index.pop(bucket_key, None)

    def _upsert_similarity_index_entry(self, state_key: str, profile: Mapping[str, Any]) -> None:
        key = str(state_key)
        self._remove_similarity_index_entry(key)
        vector = self._profile_state_vector(profile)
        if not vector:
            return
        bucket_key = _similarity_bucket_key(vector, int(self.similarity_bucket_bits))
        if not bucket_key:
            return
        bucket = self._similarity_bucket_index.setdefault(bucket_key, OrderedDict())
        bucket[key] = profile
        bucket.move_to_end(key)
        self._similarity_key_to_bucket[key] = bucket_key

    def _rebuild_similarity_index(self) -> None:
        self._similarity_bucket_index = {}
        self._similarity_key_to_bucket = {}
        for state_key, profile in self.expectation_memory.items():
            if not isinstance(profile, Mapping):
                continue
            self._upsert_similarity_index_entry(str(state_key), profile)

    def _find_similar_profiles(self, state_snapshot: Mapping[str, Any]) -> List[Tuple[float, Mapping[str, Any]]]:
        vector = self._state_vector_from_snapshot(state_snapshot)
        if not vector:
            self.last_similarity_scan_count = 0
            return []

        max_scan = max(1, int(self.similarity_max_scan))
        max_candidates = max(1, min(int(self.similarity_index_max_candidates), max_scan))
        bucket_key = _similarity_bucket_key(vector, int(self.similarity_bucket_bits))
        candidate_profiles: List[Tuple[str, Mapping[str, Any]]] = []
        seen_keys = set()

        for probe_bucket in self._bucket_neighbors(bucket_key):
            bucket = self._similarity_bucket_index.get(probe_bucket)
            if not isinstance(bucket, OrderedDict):
                continue
            for state_key, profile in reversed(list(bucket.items())):
                key = str(state_key)
                if key in seen_keys:
                    continue
                if not isinstance(profile, Mapping):
                    continue
                candidate_profiles.append((key, profile))
                seen_keys.add(key)
                if len(candidate_profiles) >= max_candidates:
                    break
            if len(candidate_profiles) >= max_candidates:
                break

        if not candidate_profiles:
            items = list(self.expectation_memory.items())
            if len(items) > max_scan:
                items = items[-max_scan:]
            candidate_profiles = [
                (str(key), profile)
                for key, profile in reversed(items)
                if isinstance(profile, Mapping)
            ]

        matches: List[Tuple[float, Mapping[str, Any]]] = []
        scanned = 0
        for _, profile in candidate_profiles:
            candidate_vector = self._profile_state_vector(profile)
            if not candidate_vector:
                continue
            similarity = _cosine_similarity(vector, candidate_vector)
            scanned += 1
            if similarity >= float(self.similarity_threshold):
                matches.append((similarity, profile))

        self.last_similarity_scan_count = int(scanned)
        matches.sort(key=lambda item: item[0], reverse=True)
        k = max(1, int(self.similarity_k))
        return matches[:k]

    def _get_expectation_profile(
        self,
        state_key: str,
        *,
        state_snapshot: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, float]:
        profile = self.expectation_memory.get(str(state_key), None)
        if not isinstance(profile, Mapping):
            if isinstance(state_snapshot, Mapping):
                similar_profiles = self._find_similar_profiles(state_snapshot)
            else:
                similar_profiles = []

            if not similar_profiles:
                self.last_similar_state_count = 0
                return self._default_expectation_profile()

            weight_total = sum(weight for weight, _ in similar_profiles)
            if weight_total <= 0.0:
                self.last_similar_state_count = 0
                return self._default_expectation_profile()

            def _wmean(key: str, default: float = 0.0) -> float:
                return sum(
                    float(weight) * _safe_float(profile.get(key), default)
                    for weight, profile in similar_profiles
                ) / float(weight_total)

            expected_mean = _wmean("expected_reward_mean", 0.0)
            shock_score = _clamp(_wmean("prediction_shock", 0.0), 0.0, 1.0)
            error_likelihood = _clamp(_wmean("error_likelihood", shock_score), 0.0, 1.0)
            similarity_mean = _clamp(weight_total / float(len(similar_profiles)), 0.0, 1.0)
            transfer_gain = _clamp(
                _safe_float(self.similarity_confidence_transfer, 0.5),
                0.05,
                1.0,
            )
            transfer_quantile = _clamp(
                _safe_float(self.similarity_transfer_quantile, 0.5),
                0.0,
                1.0,
            )
            confidence_values = [
                _clamp(_safe_float(profile.get("confidence_score"), 0.0), 0.0, 1.0)
                for _, profile in similar_profiles
            ]
            stability_values = [
                _clamp(_safe_float(profile.get("stability_score"), 0.0), 0.0, 1.0)
                for _, profile in similar_profiles
            ]
            confidence_anchor = _quantile(confidence_values, transfer_quantile)
            stability_anchor = _quantile(stability_values, transfer_quantile)
            transferred_confidence = similarity_mean * transfer_gain * confidence_anchor
            transferred_stability = similarity_mean * transfer_gain * stability_anchor
            self.last_similar_state_count = len(similar_profiles)
            return {
                "expected_reward_mean": expected_mean,
                "expected_reward_var": max(0.0, _wmean("expected_reward_var", 0.0)),
                "confirmation_count": 0.0,
                "confidence_score": _clamp(transferred_confidence, 0.0, 1.0),
                "stability_score": _clamp(transferred_stability, 0.0, 1.0),
                "surprise": max(0.0, _wmean("surprise", 0.0)),
                "prediction_shock": shock_score,
                "prediction_shock_flag": bool(shock_score >= 0.5),
                "error_likelihood": error_likelihood,
                "replay_priority": max(0.0, _wmean("replay_priority", 0.0) * similarity_mean),
                "consolidation_weight": _clamp(
                    _wmean("consolidation_weight", 0.0) * similarity_mean,
                    0.0,
                    1.0,
                ),
                "shock_replay_boost": max(1.0, _wmean("shock_replay_boost", 1.0)),
                "predicted_value": _wmean("predicted_value", expected_mean),
                "last_updated_step": int(_wmean("last_updated_step", 0.0)),
            }

        self.last_similar_state_count = 0
        self.last_similarity_scan_count = 0
        expected_mean = _safe_float(profile.get("expected_reward_mean"), 0.0)
        shock_score, shock_flag = _normalize_shock_fields(profile)
        predicted_value = _safe_float(profile.get("predicted_value"), expected_mean)
        error_likelihood = _clamp(
            _safe_float(profile.get("error_likelihood"), shock_score),
            0.0,
            1.0,
        )
        return {
            "expected_reward_mean": expected_mean,
            "expected_reward_var": max(0.0, _safe_float(profile.get("expected_reward_var"), 0.0)),
            "confirmation_count": max(0.0, _safe_float(profile.get("confirmation_count"), 0.0)),
            "confidence_score": _clamp(_safe_float(profile.get("confidence_score"), 0.0), 0.0, 1.0),
            "stability_score": _clamp(_safe_float(profile.get("stability_score"), 0.0), 0.0, 1.0),
            "surprise": max(0.0, _safe_float(profile.get("surprise"), 0.0)),
            "prediction_shock": shock_score,
            "prediction_shock_flag": bool(shock_flag),
            "error_likelihood": error_likelihood,
            "replay_priority": max(0.0, _safe_float(profile.get("replay_priority"), 0.0)),
            "consolidation_weight": _clamp(_safe_float(profile.get("consolidation_weight"), 0.0), 0.0, 1.0),
            "shock_replay_boost": max(1.0, _safe_float(profile.get("shock_replay_boost"), 1.0)),
            "predicted_value": predicted_value,
            "last_updated_step": int(_safe_float(profile.get("last_updated_step"), 0.0)),
        }

    def _set_last_expectation_metrics(self, profile: Mapping[str, Any]) -> None:
        self.last_expected_reward_mean = _safe_float(profile.get("expected_reward_mean"), 0.0)
        self.last_expected_reward_var = max(0.0, _safe_float(profile.get("expected_reward_var"), 0.0))
        self.last_confirmation_count = max(0.0, _safe_float(profile.get("confirmation_count"), 0.0))
        self.last_confidence_score = _clamp(_safe_float(profile.get("confidence_score"), 0.0), 0.0, 1.0)
        self.last_stability_score = _clamp(_safe_float(profile.get("stability_score"), 0.0), 0.0, 1.0)
        self.last_surprise = max(0.0, _safe_float(profile.get("surprise"), 0.0))
        shock_score, shock_flag = _normalize_shock_fields(profile)
        self.last_prediction_shock = bool(shock_flag)
        self.last_prediction_shock_score = float(shock_score)
        self.last_error_likelihood = _clamp(
            _safe_float(profile.get("error_likelihood"), shock_score),
            0.0,
            1.0,
        )
        self.last_replay_priority = max(0.0, _safe_float(profile.get("replay_priority"), 0.0))
        self.last_consolidation_weight = _clamp(
            _safe_float(profile.get("consolidation_weight"), 0.0),
            0.0,
            1.0,
        )

    def _update_expectation_profile(
        self,
        state_key: str,
        reward: float,
        delta_raw: float,
        step_marker: Optional[float] = None,
        state_snapshot: Optional[Mapping[str, Any]] = None,
        state_vector: Optional[List[float]] = None,
    ) -> Dict[str, float]:
        key = str(state_key)
        previous = self._get_expectation_profile(key, state_snapshot=state_snapshot)
        reward_v = _safe_float(reward, 0.0)
        delta_abs = abs(_safe_float(delta_raw, 0.0))

        mean_prev = _safe_float(previous.get("expected_reward_mean"), reward_v)
        var_prev = max(0.0, _safe_float(previous.get("expected_reward_var"), 0.0))
        confirmation_prev = max(0.0, _safe_float(previous.get("confirmation_count"), 0.0))
        stability_prev = _clamp(_safe_float(previous.get("stability_score"), 0.0), 0.0, 1.0)
        error_prev = _clamp(_safe_float(previous.get("error_likelihood"), 0.0), 0.0, 1.0)

        mean_new = ((1.0 - self.expectation_ema_beta) * mean_prev) + (self.expectation_ema_beta * reward_v)
        centered = reward_v - mean_new
        var_new = ((1.0 - self.expectation_var_ema_beta) * var_prev) + (
            self.expectation_var_ema_beta * (centered ** 2)
        )
        if delta_abs < self.confirmation_threshold:
            confirmation_new = confirmation_prev + 1.0
        else:
            confirmation_new = confirmation_prev * self.confirmation_decay

        confidence_drive = (self.confidence_k1 * confirmation_new) - (self.confidence_k2 * var_new)
        confidence_new = _clamp(_sigmoid(confidence_drive), 0.0, 1.0)
        surprise = delta_abs * confidence_new
        prediction_shock_score = _clamp(_safe_float(surprise, 0.0), 0.0, 1.0)
        prediction_shock_flag = bool(
            confidence_new >= self.shock_confidence_threshold and delta_abs >= self.shock_delta_threshold
        )
        if prediction_shock_flag or prediction_shock_score >= 0.8:
            # High shock slightly lowers confidence to reflect uncertainty.
            confidence_drop = min(0.03, 0.05 * prediction_shock_score)
            confidence_new = max(0.0, confidence_new - confidence_drop)
        stability_new = _clamp(
            stability_prev
            + (self.stability_growth_rate * confidence_new)
            - (self.stability_decay_rate * surprise),
            0.0,
            1.0,
        )
        if prediction_shock_score >= 0.8:
            stability_new = min(stability_new, stability_prev)

        error_likelihood = _clamp((error_prev * 0.95) + (prediction_shock_score * 0.05), 0.0, 1.0)
        replay_priority = delta_abs * (1.0 + (1.0 if prediction_shock_flag else 0.0)) * (1.0 - stability_new)
        consolidation_weight = _clamp((0.65 * confidence_new) + (0.35 * stability_new), 0.0, 1.0)
        shock_replay_boost = 1.0 + (self.shock_replay_gain if prediction_shock_flag else 0.0)
        last_step = int(_safe_float(step_marker, float(self.update_count)))

        if state_vector is None and isinstance(state_snapshot, Mapping):
            state_vector = self._state_vector_from_snapshot(state_snapshot)
        state_features = self.encoder.normalize(state_snapshot) if isinstance(state_snapshot, Mapping) else None

        profile = {
            "expected_reward_mean": float(mean_new),
            "expected_reward_var": float(max(0.0, var_new)),
            "confirmation_count": float(max(0.0, confirmation_new)),
            "confidence_score": float(confidence_new),
            "stability_score": float(stability_new),
            "surprise": float(max(0.0, surprise)),
            "prediction_shock": float(prediction_shock_score),
            "prediction_shock_flag": bool(prediction_shock_flag),
            "error_likelihood": float(error_likelihood),
            "replay_priority": float(max(0.0, replay_priority)),
            "consolidation_weight": float(consolidation_weight),
            "shock_replay_boost": float(max(1.0, shock_replay_boost)),
            "predicted_value": float(mean_new),
            "last_updated_step": int(last_step),
        }
        if isinstance(state_vector, list) and state_vector:
            profile["state_vector"] = [float(x) for x in state_vector]
        if isinstance(state_features, Mapping):
            profile["state_features"] = dict(state_features)
        self.expectation_memory[key] = profile
        self.expectation_memory.move_to_end(key)
        self._upsert_similarity_index_entry(key, profile)
        while len(self.expectation_memory) > self.max_states:
            removed_key, _ = self.expectation_memory.popitem(last=False)
            self._remove_similarity_index_entry(str(removed_key))

        self._set_last_expectation_metrics(profile)
        shock_obs = 1.0 if prediction_shock_flag else 0.0
        self.shock_frequency_ema = _clamp(
            ((1.0 - self.shock_frequency_beta) * self.shock_frequency_ema)
            + (self.shock_frequency_beta * shock_obs),
            0.0,
            1.0,
        )
        if prediction_shock_flag:
            self.shock_count_total += 1
        return profile

    def _append_alpha_trajectory(self, alpha_value: float) -> None:
        self.alpha_effective_trajectory.append(float(alpha_value))
        if len(self.alpha_effective_trajectory) > self.alpha_trajectory_window:
            self.alpha_effective_trajectory = self.alpha_effective_trajectory[-self.alpha_trajectory_window :]

    def _distribution_summary(self, values: List[float]) -> Dict[str, float]:
        cleaned = [_clamp(_safe_float(value), 0.0, 1.0) for value in list(values or [])]
        if not cleaned:
            return {"count": 0, "mean": 0.0, "min": 0.0, "max": 0.0}
        return {
            "count": int(len(cleaned)),
            "mean": float(sum(cleaned) / float(len(cleaned))),
            "min": float(min(cleaned)),
            "max": float(max(cleaned)),
        }

    def _track_and_adapt_td_clip(self, mode: str, was_clipped: bool) -> None:
        if mode != "online":
            return

        self.online_td_clip_updates += 1
        if was_clipped:
            self.online_td_clip_count += 1

        if self.online_td_clip_updates > 0:
            self.online_td_clip_frequency = _clamp(
                self.online_td_clip_count / float(self.online_td_clip_updates),
                0.0,
                1.0,
            )
        else:
            self.online_td_clip_frequency = 0.0

        ema_beta = _clamp(_safe_float(self.td_clip_ema_beta, 0.05), 0.001, 1.0)
        observed = 1.0 if was_clipped else 0.0
        self.online_td_clip_frequency_ema = _clamp(
            ((1.0 - ema_beta) * float(self.online_td_clip_frequency_ema)) + (ema_beta * observed),
            0.0,
            1.0,
        )

        if not bool(self.adaptive_td_clip_enabled):
            return

        target = _clamp(_safe_float(self.td_clip_target_rate, 0.2), 0.01, 0.9)
        adapt_rate = _clamp(_safe_float(self.td_clip_adapt_rate, 0.05), 0.001, 0.5)
        deadband = 0.02
        clip_current = _clamp(
            _safe_float(self.td_clip_online, 1.0),
            _safe_float(self.td_clip_min_online, 0.05),
            _safe_float(self.td_clip_max_online, 3.0),
        )
        clip_min = _clamp(_safe_float(self.td_clip_min_online, 0.05), 0.01, 10.0)
        clip_max = _clamp(_safe_float(self.td_clip_max_online, 1.0), clip_min, 1.0)

        ema = float(self.online_td_clip_frequency_ema)
        if ema > (target + deadband):
            scale = 1.0 + (adapt_rate * (ema - target))
            clip_next = clip_current * scale
        elif ema < (target - deadband):
            scale = max(0.5, 1.0 - (adapt_rate * (target - ema)))
            clip_next = clip_current * scale
        else:
            clip_next = clip_current

        self.td_clip_online = _clamp(clip_next, clip_min, clip_max)

    def _increment_update_counters(self, mode: str) -> None:
        if mode == "sleep":
            self.sleep_update_count += 1
        else:
            self.online_update_count += 1
        self.update_count = self.online_update_count + self.sleep_update_count

    def value_abs_bound(self, gamma: Optional[float] = None) -> float:
        """Largest |V| that can hold the discounted return of a unit reward.

        The bound follows ``gamma_default``. A larger ``gamma`` widens it.
        Reward magnitudes are left unchanged.
        """
        bound = discounted_value_bound(self.gamma_default, 1.0)
        if gamma is not None:
            bound = max(bound, discounted_value_bound(gamma, 1.0))
        return bound

    def _get_value(self, state_key: str) -> float:
        if state_key in self.values:
            bound = self.value_abs_bound()
            value = _clamp(_safe_float(self.values[state_key]), -bound, bound)
            self.values.move_to_end(state_key)
            return value
        return 0.0

    def _set_value(self, state_key: str, value: float) -> None:
        from learning_guard import assert_learning_allowed

        if not assert_learning_allowed("ValueLayer._set_value"):
            return
        bound = self.value_abs_bound()
        self.values[state_key] = _clamp(_safe_float(value), -bound, bound)
        self.values.move_to_end(state_key)
        while len(self.values) > self.max_states:
            removed_key, _ = self.values.popitem(last=False)
            if removed_key in self.expectation_memory:
                self.expectation_memory.pop(removed_key, None)
                self._remove_similarity_index_entry(str(removed_key))


__all__ = ["StateEncoder", "DopaminergicTDLayer", "ValueLayer", "state_similarity"]
