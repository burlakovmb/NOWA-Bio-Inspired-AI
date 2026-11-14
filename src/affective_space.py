"""
Affective Core + Phase 4.

Canonical state:
- A(t) in R^N over canonical axes in [-1.0, 1.0]
- single continuously updated state vector used by decision readout

Compatibility:
- legacy phase-4 axes (pleasure/pain/...) are accepted on input
- legacy dynamic parameters (decay/inertia/noise/fall_rate) are supported
  as optional additive terms without changing canonical storage
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple


AXES = (
    "valence",
    "arousal",
    "dominance",
    "stress",
    "trust",
    "curiosity",
    "stability",
    "attachment",
)


def mapped_event_tokens(event_name: str, entry: Optional[Dict[str, Any]] = None) -> List[str]:
    """Context tokens for one mapping row (valence/arousal/tags). Used by body and sandbox."""
    payload = entry if isinstance(entry, dict) else {}
    tokens = [f"event:{event_name}"]
    try:
        valence = float(payload.get("valence", 0.0))
    except (TypeError, ValueError):
        valence = 0.0
    try:
        arousal = float(payload.get("arousal", 0.5))
    except (TypeError, ValueError):
        arousal = 0.5
    if valence > 0.5:
        tokens.append("valence:very_positive")
    elif valence > 0.15:
        tokens.append("valence:positive")
    elif valence < -0.5:
        tokens.append("valence:very_negative")
    elif valence < -0.15:
        tokens.append("valence:negative")
    else:
        tokens.append("valence:neutral")
    if arousal > 0.6:
        tokens.append("arousal:high")
    for tag in payload.get("tags", []) or []:
        label = str(tag).strip()
        if label:
            tokens.append(f"domain:{label}")
    return tokens

LEGACY_AXES = (
    "pleasure",
    "pain",
    "arousal",
    "relaxation",
    "attachment",
    "rejection",
    "focus",
    "vulnerability",
)

OPPOSING_PAIRS = (
    ("valence", "stress"),
    ("trust", "stress"),
    ("dominance", "stress"),
    ("curiosity", "stability"),
)

DECISION_DIMENSIONS = (
    "risk",
    "response_speed",
    "word_choice",
    "empathy",
    "goal_priority",
)

RANK_WEIGHT_KEYS = (
    "caution",
    "cost_aversion",
    "speed_seek",
    "reliability",
    "novelty_seek",
    "assertiveness",
)

_OUTCOME_STATUS_VECTORS: Dict[str, Dict[str, float]] = {
    "accepted": {"valence": 0.4, "stress": -0.1, "trust": 0.2, "arousal": 0.1, "curiosity": 0.0},
    "success": {"valence": 0.4, "stress": -0.1, "trust": 0.2, "arousal": 0.1, "curiosity": 0.0},
    "ok": {"valence": 0.4, "stress": -0.1, "trust": 0.2, "arousal": 0.1, "curiosity": 0.0},
    "rejected": {"valence": -0.4, "stress": 0.4, "trust": -0.2, "arousal": 0.3, "curiosity": 0.0},
    "failed": {"valence": -0.4, "stress": 0.4, "trust": -0.2, "arousal": 0.3, "curiosity": 0.0},
    "error": {"valence": -0.4, "stress": 0.4, "trust": -0.2, "arousal": 0.3, "curiosity": 0.0},
    "timeout": {"valence": -0.1, "stress": 0.2, "trust": -0.1, "arousal": 0.2, "curiosity": 0.2},
    "unknown": {"valence": -0.1, "stress": 0.2, "trust": -0.1, "arousal": 0.2, "curiosity": 0.2},
}

DEFAULT_DECISION_MATRIX: Dict[str, Dict[str, float]] = {
    "risk": {"valence": 0.35, "dominance": 0.35, "stress": -0.75, "trust": 0.2},
    "response_speed": {"arousal": 0.7, "stress": 0.2, "stability": -0.3},
    "word_choice": {"valence": 0.5, "stress": -0.4, "trust": 0.3},
    "empathy": {"trust": 0.65, "attachment": 0.45, "stress": -0.45, "dominance": -0.2},
    "goal_priority": {"dominance": 0.45, "stability": 0.35, "curiosity": 0.35, "stress": -0.25},
}

_ALLOWED_IMPULSE_SOURCES = {"external", "memory", "internal"}

_LEGACY_VECTOR_MAP: Dict[str, Dict[str, float]] = {
    "pleasure": {"valence": 1.0, "trust": 0.25, "stability": 0.2},
    "pain": {"valence": -1.0, "stress": 1.0},
    "arousal": {"arousal": 1.0},
    "relaxation": {"stability": 1.0, "arousal": -0.45, "stress": -0.25},
    "attachment": {"attachment": 1.0, "trust": 0.45},
    "rejection": {"trust": -1.0, "stress": 0.55, "attachment": -0.1},
    "focus": {"dominance": 0.8, "curiosity": 0.4},
    "vulnerability": {"stability": -0.9, "stress": 0.6, "dominance": -0.35},
}

_LEGACY_PARAM_AXIS: Dict[str, str] = {
    "pleasure": "valence",
    "pain": "stress",
    "arousal": "arousal",
    "relaxation": "stability",
    "attachment": "attachment",
    "rejection": "trust",
    "focus": "dominance",
    "vulnerability": "stress",
}

_CORE_TO_LEGACY_PARAM: Dict[str, str] = {
    "valence": "pleasure",
    "stress": "pain",
    "arousal": "arousal",
    "stability": "relaxation",
    "attachment": "attachment",
    "trust": "rejection",
    "dominance": "focus",
    "curiosity": "focus",
}

DEFAULT_AFFECTIVE_DECAY: Dict[str, float] = {
    "valence": 0.92,
    "arousal": 0.80,
    "dominance": 0.97,
    "stress": 0.75,
    "curiosity": 0.78,
    "trust": 0.95,
}

# Axis leak is per second. Allostatic baseline is not: acquisition over 6 h,
# recovery toward the genetic setpoint 4x slower (24 h). Sleep speeds
# clearance and recovery, not the acquisition of load.
BASELINE_ADAPT_TAU_S = 6.0 * 3600.0
DEFAULT_BASELINE_ADAPT_RATE = 1.0 / BASELINE_ADAPT_TAU_S
BASELINE_RECOVERY_RATE_RATIO = 0.25
SLEEP_RECOVERY_SCALE = 4.0


def _clamp(value: Any, min_v: float, max_v: float) -> float:
    try:
        v = float(value)
    except Exception:
        v = 0.0
    return max(min_v, min(max_v, v))

def _pow_unit(base: float, exponent: float) -> float:
    if exponent == 0.0:
        return 1.0
    if base <= 1e-15:
        return 0.0 if exponent > 0.0 else 1.0
    if abs(base - 1.0) <= 1e-15:
        return 1.0
    return math.exp(exponent * math.log(base))


def _pow_unit_deriv(base: float, exponent: float) -> float:
    """``exponent * base ** (exponent - 1)`` for a repeated eigenvalue."""
    if exponent == 0.0:
        return 0.0
    if base <= 1e-15:
        return 1.0 if abs(exponent - 1.0) <= 1e-15 else 0.0
    if abs(base - 1.0) <= 1e-15:
        return exponent
    return exponent * math.exp((exponent - 1.0) * math.log(base))


def _relax_deviation(
    deviation: float,
    baseline_deviation: float,
    dt: float,
    retention: float,
    adapt_gain: float,
    recover_gain: float,
) -> Tuple[float, float]:
    """Apply the one-second allostatic map ``dt`` times.

    One second is the legacy step: retention toward baseline, adaptation
    toward the axis, recovery toward the setpoint. Powering that map by
    ``dt`` makes one step of ``dt`` seconds match ``dt`` steps of 1 s.
    """
    if dt <= 0.0:
        return deviation, baseline_deviation
    retain = _clamp(retention, 0.0, 0.999)
    gain = _clamp(adapt_gain, 0.0, 1.0)
    recover = _clamp(recover_gain, 0.0, 1.0)
    keep = 1.0 - recover
    m00 = retain
    m01 = 1.0 - retain
    m10 = keep * gain * retain
    m11 = keep * (1.0 - gain * retain)
    trace = m00 + m11
    det = m00 * m11 - m01 * m10
    disc = trace * trace - 4.0 * det
    if disc < 0.0:
        disc = 0.0
    gap = math.sqrt(disc)
    mid = 0.5 * trace
    high = mid + 0.5 * gap
    low = mid - 0.5 * gap
    if gap < 1e-8:
        coef = _pow_unit_deriv(high, dt)
        low_pow = _pow_unit(high, dt)
        low = high
    else:
        high_pow = _pow_unit(high, dt)
        low_pow = _pow_unit(low, dt)
        coef = (high_pow - low_pow) / (high - low)
    beta = low_pow - coef * low
    return (
        (coef * m00 + beta) * deviation + (coef * m01) * baseline_deviation,
        (coef * m10) * deviation + (coef * m11 + beta) * baseline_deviation,
    )


def _uniform_value(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, dict):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _zero_vector() -> Dict[str, float]:
    return {axis: 0.0 for axis in AXES}


def _vector_l2_norm(vector: Dict[str, float]) -> float:
    return math.sqrt(sum(float(vector.get(axis, 0.0)) ** 2 for axis in AXES))


def _vector_l1_mean_abs(vector: Dict[str, float]) -> float:
    if not AXES:
        return 0.0
    return sum(abs(float(vector.get(axis, 0.0))) for axis in AXES) / float(len(AXES))


def _normalize_matrix(weights: Optional[Dict[str, Dict[str, float]]]) -> Dict[str, Dict[str, float]]:
    matrix: Dict[str, Dict[str, float]] = {}
    source = weights if isinstance(weights, dict) else {}
    for dim in DECISION_DIMENSIONS:
        row_src = source.get(dim, {})
        row = dict(DEFAULT_DECISION_MATRIX.get(dim, {}))
        if isinstance(row_src, dict):
            for axis, value in row_src.items():
                if axis in AXES:
                    row[axis] = float(value)
        matrix[dim] = row
    return matrix


def _core_to_legacy_axes(core_axes: Dict[str, float]) -> Dict[str, float]:
    valence = _clamp(core_axes.get("valence", 0.0), -1.0, 1.0)
    arousal = _clamp(core_axes.get("arousal", 0.0), -1.0, 1.0)
    dominance = _clamp(core_axes.get("dominance", 0.0), -1.0, 1.0)
    stress = _clamp(core_axes.get("stress", 0.0), -1.0, 1.0)
    trust = _clamp(core_axes.get("trust", 0.0), -1.0, 1.0)
    curiosity = _clamp(core_axes.get("curiosity", 0.0), -1.0, 1.0)
    stability = _clamp(core_axes.get("stability", 0.0), -1.0, 1.0)
    attachment = _clamp(core_axes.get("attachment", 0.0), -1.0, 1.0)

    pleasure = _clamp(max(0.0, valence), 0.0, 1.0)
    pain = _clamp(max(0.0, -valence) + (0.35 * max(0.0, stress)), 0.0, 1.0)
    arousal_legacy = _clamp((arousal + 1.0) / 2.0, 0.0, 1.0)
    relaxation = _clamp((stability + 1.0) / 2.0 - (0.25 * abs(arousal)), 0.0, 1.0)
    attachment_legacy = _clamp(max(0.0, attachment), 0.0, 1.0)
    rejection = _clamp(max(0.0, -trust) + (0.2 * max(0.0, stress)), 0.0, 1.0)
    focus = _clamp(max(0.0, dominance) + max(0.0, curiosity), 0.0, 1.0)
    vulnerability = _clamp(max(0.0, -stability) + (0.35 * max(0.0, stress)), 0.0, 1.0)

    return {
        "pleasure": pleasure,
        "pain": pain,
        "arousal": arousal_legacy,
        "relaxation": relaxation,
        "attachment": attachment_legacy,
        "rejection": rejection,
        "focus": focus,
        "vulnerability": vulnerability,
    }


@dataclass(frozen=True)
class EmotionalImpulse:
    """Transient operator that influences A(t) at one step."""

    vector: Dict[str, float]
    intensity: float = 1.0
    source: str = "external"

    def __post_init__(self) -> None:
        source = str(self.source).strip().lower()
        if source not in _ALLOWED_IMPULSE_SOURCES:
            source = "external"
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "intensity", _clamp(self.intensity, 0.0, 1.0))
        object.__setattr__(self, "vector", dict(self.vector or {}))
        core = self._build_core_vector()
        object.__setattr__(self, "_core_vector", core)
        object.__setattr__(self, "_core_values", tuple(core[axis] for axis in AXES))
        object.__setattr__(self, "_core_magnitude", _vector_l1_mean_abs(core))

    def _build_core_vector(self) -> Dict[str, float]:
        raw = _zero_vector()
        for key, value in (self.vector or {}).items():
            if key in AXES:
                raw[key] += _clamp(value, -1.0, 1.0)
                continue
            if key not in _LEGACY_VECTOR_MAP:
                continue
            val_legacy = _clamp(value, -1.0, 1.0)
            for axis, weight in _LEGACY_VECTOR_MAP[key].items():
                raw[axis] += val_legacy * float(weight)

        gain = _clamp(self.intensity, 0.0, 1.0)
        return {axis: _clamp(raw[axis] * gain, -1.0, 1.0) for axis in AXES}

    def to_core_vector(self) -> Dict[str, float]:
        core = self._core_vector
        if core is None:
            values = self._core_values
            core = {AXES[index]: values[index] for index in range(len(AXES))}
            object.__setattr__(self, "_core_vector", core)
        return core

    def magnitude(self) -> float:
        return self._core_magnitude

    @classmethod
    def from_core(
        cls,
        core: Dict[str, float],
        magnitude: float,
        intensity: float,
        source: str = "memory",
        vector: Optional[Dict[str, float]] = None,
    ) -> "EmotionalImpulse":
        """Build an impulse whose core vector is already the canonical one."""
        values = tuple(float(core.get(axis, 0.0)) for axis in AXES)
        return cls.from_values(values, magnitude, intensity, source=source, vector=vector, core=core)

    @classmethod
    def from_values(
        cls,
        values: Tuple[float, ...],
        magnitude: float,
        intensity: float,
        source: str = "memory",
        vector: Optional[Dict[str, float]] = None,
        core: Optional[Dict[str, float]] = None,
        raw: Optional[Tuple[float, ...]] = None,
    ) -> "EmotionalImpulse":
        """Build an impulse from canonical axis values without re-reading a snapshot."""
        impulse = object.__new__(cls)
        if vector is None and core is not None:
            shown = dict(core)
        elif vector is None:
            shown = {AXES[index]: values[index] for index in range(len(AXES))}
        else:
            # Recall keeps the snapshot by reference. The scaled copy is a new dict.
            shown = vector if raw is not None else dict(vector)
        object.__setattr__(impulse, "vector", shown)
        object.__setattr__(impulse, "intensity", intensity)
        object.__setattr__(impulse, "source", source)
        object.__setattr__(impulse, "_core_values", values)
        object.__setattr__(impulse, "_core_vector", core)
        object.__setattr__(impulse, "_core_magnitude", magnitude)
        object.__setattr__(impulse, "_raw_values", raw)
        return impulse


@dataclass(slots=True)
class EmotionalTrace:
    """
    Stored emotional memory snapshot.

    A trace does not modify A(t) directly. It can generate a recall impulse.
    """

    snapshot_vector: Dict[str, float]
    intensity: float = 1.0
    timestamp: float = field(default_factory=time.time)
    decay_rate: float = 0.05
    # Precomputed axis sum. Not part of equality; rebuilt in __post_init__.
    _raw_axes: Dict[str, float] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        self.snapshot_vector = dict(self.snapshot_vector or {})
        self.intensity = _clamp(self.intensity, 0.0, 1.0)
        self.decay_rate = max(0.0, float(self.decay_rate or 0.0))
        self.timestamp = float(self.timestamp or time.time())
        self._raw_axes = self._snapshot_raw_axes(self.snapshot_vector)

    @staticmethod
    def _snapshot_raw_axes(snapshot: Dict[str, float]) -> Dict[str, float]:
        """Pre-intensity axis sum. Scaling by intensity matches EmotionalImpulse."""
        raw = _zero_vector()
        for key, value in (snapshot or {}).items():
            if key in AXES:
                raw[key] += _clamp(value, -1.0, 1.0)
                continue
            mapped = _LEGACY_VECTOR_MAP.get(key)
            if not mapped:
                continue
            val_legacy = _clamp(value, -1.0, 1.0)
            for axis, weight in mapped.items():
                raw[axis] += val_legacy * float(weight)
        return raw

    def decayed_intensity(self, now: Optional[float] = None) -> float:
        ts_now = float(now if now is not None else time.time())
        dt = max(0.0, ts_now - float(self.timestamp))
        return _clamp(self.intensity * math.exp(-self.decay_rate * dt), 0.0, 1.0)

    def to_impulse(self, k: float = 0.25, now: Optional[float] = None) -> EmotionalImpulse:
        gain = _clamp(k, 0.1, 0.4)
        decayed = self.decayed_intensity(now=now)
        intensity = _clamp(gain * decayed, 0.0, 1.0)
        raw = self._raw_axes
        values = []
        raw_values = []
        magnitude_sum = 0.0
        for axis in AXES:
            base = raw[axis]
            raw_values.append(base)
            value = base * intensity
            if value < -1.0:
                value = -1.0
            elif value > 1.0:
                value = 1.0
            values.append(value)
            magnitude_sum += value if value >= 0.0 else -value
        return EmotionalImpulse.from_values(
            tuple(values),
            magnitude_sum / float(len(AXES) or 1),
            intensity,
            vector=self.snapshot_vector,
            raw=tuple(raw_values),
        )

    def __getstate__(self):
        return {
            "snapshot_vector": dict(self.snapshot_vector or {}),
            "intensity": self.intensity,
            "timestamp": self.timestamp,
            "decay_rate": self.decay_rate,
            "_raw_axes": dict(self._raw_axes),
        }

    def __setstate__(self, state):
        """Accept a main ``__dict__`` or the slotted ``(None, slot_dict)`` payload."""
        from experience import _pickle_state_dict

        payload = _pickle_state_dict(state)
        snapshot = payload.get("snapshot_vector", {})
        try:
            snapshot = dict(snapshot or {})
        except (TypeError, ValueError):
            snapshot = {}
        try:
            intensity = float(payload.get("intensity", 1.0))
        except (TypeError, ValueError):
            intensity = 1.0
        try:
            timestamp = float(payload.get("timestamp", 0.0) or 0.0)
        except (TypeError, ValueError):
            timestamp = 0.0
        try:
            decay_rate = float(payload.get("decay_rate", 0.05) or 0.0)
        except (TypeError, ValueError):
            decay_rate = 0.05
        object.__setattr__(self, "snapshot_vector", snapshot)
        object.__setattr__(self, "intensity", _clamp(intensity, 0.0, 1.0))
        object.__setattr__(self, "timestamp", timestamp)
        object.__setattr__(self, "decay_rate", max(0.0, decay_rate))
        raw = payload.get("_raw_axes")
        if not isinstance(raw, dict) or any(axis not in raw for axis in AXES):
            raw = self._snapshot_raw_axes(snapshot)
        else:
            raw = dict(raw)
        object.__setattr__(self, "_raw_axes", raw)


@dataclass
class AffectiveSpace:
    """Canonical affective core state A(t)."""

    axes: Dict[str, float] = field(default_factory=dict)
    baseline: Dict[str, float] = field(default_factory=dict)
    # Genetic setpoint b0. Dynamics never write it; baseline relaxes toward it.
    baseline_setpoint: Dict[str, float] = field(default_factory=dict)
    alpha: float = 0.85
    axis_decay: Any = field(default_factory=dict)
    affective_decay: Optional[Any] = None
    lambda_reg: float = 0.05
    baseline_adapt_rate: float = DEFAULT_BASELINE_ADAPT_RATE
    norm_cap_base: float = 1.5
    norm_cap_max: float = 2.2
    norm_cap_adapt_rate: float = 0.06
    norm_cap_release_rate: float = 0.02
    norm_cap_global_release_rate: float = 0.005

    # Legacy optional dynamics retained for backward compatibility.
    legacy_compat_weight: float = 0.0
    decay: Dict[str, float] = field(default_factory=dict)
    inertia: Dict[str, float] = field(default_factory=dict)
    noise_sigma: Dict[str, float] = field(default_factory=dict)
    fall_rate: Dict[str, float] = field(default_factory=dict)

    decision_matrix: Dict[str, Dict[str, float]] = field(default_factory=dict)
    rng: Optional[random.Random] = None
    timestamp: float = field(default_factory=time.time)
    last_axes: Dict[str, float] = field(default_factory=dict)
    last_noise_sigma: Dict[str, float] = field(default_factory=dict)
    last_external_mean_impulse: float = 0.0
    dynamic_norm_cap: Optional[float] = None

    def __post_init__(self) -> None:
        if self.rng is None:
            self.rng = random.Random()

        self.axes = self._fill_state_vector(self.axes, default_value=0.0)
        self.baseline = self._fill_state_vector(self.baseline, default_value=0.0)
        raw_setpoint = self.baseline_setpoint if isinstance(self.baseline_setpoint, dict) else {}
        if raw_setpoint:
            self.baseline_setpoint = self._fill_state_vector(raw_setpoint, default_value=0.0)
            for axis in AXES:
                if axis not in raw_setpoint:
                    self.baseline_setpoint[axis] = float(self.baseline.get(axis, 0.0))
        else:
            self.baseline_setpoint = dict(self.baseline)
        for axis in AXES:
            self.baseline_setpoint[axis] = _clamp(self.baseline_setpoint[axis], -1.0, 1.0)
        self.alpha = _clamp(self.alpha, 0.7, 0.95)
        axis_decay_source: Any = self.axis_decay
        if self.affective_decay is not None:
            if isinstance(axis_decay_source, dict) and isinstance(self.affective_decay, dict):
                merged_axis_decay = dict(axis_decay_source)
                merged_axis_decay.update(self.affective_decay)
                axis_decay_source = merged_axis_decay
            elif _uniform_value(self.affective_decay) is not None:
                axis_decay_source = self.affective_decay
            elif not axis_decay_source:
                axis_decay_source = self.affective_decay
        self.axis_decay = self._fill_axis_decay(axis_decay_source, fallback=self.alpha)
        self.affective_decay = dict(self.axis_decay)
        self.lambda_reg = _clamp(self.lambda_reg, 0.01, 0.1)
        self.baseline_adapt_rate = _clamp(self.baseline_adapt_rate, 0.0, 0.2)
        self.norm_cap_base = max(1.0, float(self.norm_cap_base or 1.5))
        self.norm_cap_max = max(self.norm_cap_base, float(self.norm_cap_max or self.norm_cap_base))
        self.norm_cap_adapt_rate = _clamp(self.norm_cap_adapt_rate, 0.0, 0.5)
        self.norm_cap_release_rate = _clamp(self.norm_cap_release_rate, 0.0, 0.5)
        self.norm_cap_global_release_rate = _clamp(self.norm_cap_global_release_rate, 0.0, 0.5)
        if self.dynamic_norm_cap is None:
            self.dynamic_norm_cap = self.norm_cap_base
        self.dynamic_norm_cap = _clamp(self.dynamic_norm_cap, self.norm_cap_base, self.norm_cap_max)

        self.legacy_compat_weight = _clamp(self.legacy_compat_weight, 0.0, 1.0)
        self.decay = self._fill_params(self.decay, default_value=0.0, min_v=0.0, max_v=1.0)
        self.inertia = self._fill_params(self.inertia, default_value=0.0, min_v=0.0, max_v=1.0)
        self.noise_sigma = self._fill_params(self.noise_sigma, default_value=0.0, min_v=0.0, max_v=1.0)
        self.fall_rate = self._fill_params(self.fall_rate, default_value=None, min_v=0.0, max_v=1.0)
        for axis in AXES:
            if self.fall_rate.get(axis) is None:
                self.fall_rate[axis] = self.decay.get(axis, 0.0)

        self.decision_matrix = _normalize_matrix(self.decision_matrix)
        self.last_external_mean_impulse = _clamp(self.last_external_mean_impulse, 0.0, 1.0)

        if not self.last_axes:
            self.last_axes = dict(self.axes)

        self._enforce_norm_cap()

    @staticmethod
    def _fill_state_vector(values: Any, default_value: float) -> Dict[str, float]:
        result = _zero_vector()
        scalar = _uniform_value(values)
        if scalar is not None:
            scalar_v = _clamp(scalar, -1.0, 1.0)
            for axis in AXES:
                result[axis] = scalar_v
            return result

        src = values if isinstance(values, dict) else {}
        for key, value in (src or {}).items():
            if key in AXES:
                result[key] += _clamp(value, -1.0, 1.0)
                continue
            if key not in _LEGACY_VECTOR_MAP:
                continue
            legacy_value = _clamp(value, -1.0, 1.0)
            for axis, weight in _LEGACY_VECTOR_MAP[key].items():
                result[axis] += legacy_value * float(weight)

        for axis in AXES:
            if axis not in result:
                result[axis] = default_value
            result[axis] = _clamp(result.get(axis, default_value), -1.0, 1.0)
        return result

    @staticmethod
    def _fill_params(values: Any, default_value: Optional[float], min_v: float, max_v: float) -> Dict[str, float]:
        result: Dict[str, float] = {axis: default_value for axis in AXES}
        scalar = _uniform_value(values)
        if scalar is not None:
            scalar_v = _clamp(scalar, min_v, max_v)
            for axis in AXES:
                result[axis] = scalar_v
            return result

        src = values if isinstance(values, dict) else {}
        for key, value in (src or {}).items():
            axis = key
            if axis not in AXES:
                axis = _LEGACY_PARAM_AXIS.get(str(key), "")
            if axis not in AXES:
                continue
            if value is None:
                result[axis] = None
                continue
            result[axis] = _clamp(value, min_v, max_v)
        return result

    @staticmethod
    def _fill_axis_decay(values: Any, fallback: float) -> Dict[str, float]:
        fallback_v = _clamp(fallback, 0.0, 0.999)
        result: Dict[str, float] = {axis: fallback_v for axis in AXES}
        for axis, value in DEFAULT_AFFECTIVE_DECAY.items():
            if axis in result:
                result[axis] = _clamp(value, 0.0, 0.999)

        scalar = _uniform_value(values)
        if scalar is not None:
            scalar_v = _clamp(scalar, 0.0, 0.999)
            for axis in AXES:
                result[axis] = scalar_v
            return result

        src = values if isinstance(values, dict) else {}
        for key, value in (src or {}).items():
            axis = key
            if axis not in AXES:
                axis = _LEGACY_PARAM_AXIS.get(str(key), "")
            if axis not in AXES:
                continue
            if value is None:
                continue
            result[axis] = _clamp(value, 0.0, 0.999)
        return result

    def _update_dynamic_norm_cap(self, impulse_norm: float, dt: float, wakefulness: float) -> None:
        if self.norm_cap_max <= self.norm_cap_base:
            self.dynamic_norm_cap = self.norm_cap_base
            return

        cap = float(self.dynamic_norm_cap or self.norm_cap_base)
        dt_v = max(0.0, float(dt))
        if dt_v <= 0.0:
            self.dynamic_norm_cap = _clamp(cap, self.norm_cap_base, self.norm_cap_max)
            return

        current_norm = _vector_l2_norm(self.axes)
        utilization = current_norm / max(1e-9, cap)
        pressure = max(0.0, float(impulse_norm))
        pressure_ratio = pressure / max(1e-9, self.norm_cap_base)
        wake = _clamp(wakefulness, 0.0, 1.0)

        cap_span = max(1e-9, self.norm_cap_max - self.norm_cap_base)
        cap_ratio = _clamp((cap - self.norm_cap_base) / cap_span, 0.0, 1.0)
        headroom = max(0.0, 1.0 - cap_ratio)

        grow_trigger = max(0.0, pressure_ratio - 0.85) + max(0.0, utilization - 0.8)
        grow = self.norm_cap_adapt_rate * grow_trigger * dt_v * (1.0 + (0.3 * wake)) * headroom

        relax_trigger = max(0.0, 0.75 - pressure_ratio)
        relax = self.norm_cap_release_rate * relax_trigger * dt_v
        global_relax = self.norm_cap_global_release_rate * max(0.0, cap - self.norm_cap_base) * dt_v

        cap = cap + grow - relax - global_relax
        self.dynamic_norm_cap = _clamp(cap, self.norm_cap_base, self.norm_cap_max)

    def _enforce_norm_cap(self) -> None:
        norm = _vector_l2_norm(self.axes)
        cap = max(1e-6, float(self.dynamic_norm_cap or self.norm_cap_base))
        if norm <= cap or norm <= 0.0:
            return
        scale = cap / norm
        for axis in AXES:
            self.axes[axis] = _clamp(float(self.axes.get(axis, 0.0)) * scale, -1.0, 1.0)

    def _normalize_impulse_payload(self, payload: Any, default_source: str) -> List[EmotionalImpulse]:
        if payload is None:
            return []
        if isinstance(payload, EmotionalImpulse):
            return [payload]
        if isinstance(payload, dict):
            if "vector" in payload:
                return [
                    EmotionalImpulse(
                        vector=dict(payload.get("vector", {})),
                        intensity=_clamp(payload.get("intensity", 1.0), 0.0, 1.0),
                        source=str(payload.get("source", default_source)),
                    )
                ]
            return [EmotionalImpulse(vector=payload, intensity=1.0, source=default_source)]

        if isinstance(payload, (list, tuple)):
            out: List[EmotionalImpulse] = []
            for item in payload:
                out.extend(self._normalize_impulse_payload(item, default_source=default_source))
            return out
        return []

    @staticmethod
    def _sum_impulses(impulses: Iterable[EmotionalImpulse]) -> Tuple[Dict[str, float], List[float]]:
        width = len(AXES)
        acc = [0.0] * width
        magnitudes: List[float] = []
        for impulse in impulses:
            values = getattr(impulse, "_core_values", None)
            if not values:
                vec = impulse.to_core_vector()
                values = tuple(float(vec.get(axis, 0.0)) for axis in AXES)
            magnitudes.append(impulse.magnitude() if hasattr(impulse, "magnitude") else _vector_l1_mean_abs(impulse.to_core_vector()))
            for index in range(width):
                acc[index] += values[index]
        return {AXES[index]: acc[index] for index in range(width)}, magnitudes

    @staticmethod
    def _scale_vector(vector: Dict[str, float], scale: float) -> Dict[str, float]:
        factor = max(0.0, float(scale))
        return {axis: float(vector.get(axis, 0.0)) * factor for axis in AXES}

    def _apply_recall_constraints(
        self,
        recall_impulses: List[EmotionalImpulse],
        mean_external: float,
        external_vector: Dict[str, float],
    ) -> Dict[str, float]:
        constrained: List[EmotionalImpulse] = []

        reference_external = max(0.0, float(mean_external))
        if reference_external <= 0.0:
            reference_external = max(0.0, float(self.last_external_mean_impulse))

        # Per impulse: RecallImpulse <= 0.3 * mean(ExternalImpulse)
        per_impulse_cap = 0.3 * reference_external if reference_external > 0.0 else 0.15

        for impulse in recall_impulses:
            mag = impulse.magnitude()
            if mag <= 0.0 or per_impulse_cap <= 0.0 or mag <= per_impulse_cap:
                constrained.append(impulse)
                continue
            scale = per_impulse_cap / mag
            new_intensity = _clamp(float(impulse.intensity) * scale, 0.0, 1.0)
            raw_values = getattr(impulse, "_raw_values", None)
            if raw_values:
                scaled_values = []
                magnitude_sum = 0.0
                for base in raw_values:
                    value = base * new_intensity
                    if value < -1.0:
                        value = -1.0
                    elif value > 1.0:
                        value = 1.0
                    scaled_values.append(value)
                    magnitude_sum += value if value >= 0.0 else -value
                constrained.append(
                    EmotionalImpulse.from_values(
                        tuple(scaled_values),
                        magnitude_sum / float(len(AXES) or 1),
                        new_intensity,
                        source=impulse.source,
                        vector=dict(impulse.vector or {}),
                        raw=raw_values,
                    )
                )
                continue
            constrained.append(
                EmotionalImpulse(
                    vector=dict(impulse.vector or {}),
                    intensity=new_intensity,
                    source=impulse.source,
                )
            )

        recall_vector, _ = self._sum_impulses(constrained)
        return self._cap_recall_norm(recall_vector, external_vector)

    def create_trace(self, intensity: float = 1.0, decay_rate: float = 0.05, timestamp: Optional[float] = None) -> EmotionalTrace:
        return EmotionalTrace(
            snapshot_vector=dict(self.axes),
            intensity=_clamp(intensity, 0.0, 1.0),
            timestamp=float(timestamp if timestamp is not None else time.time()),
            decay_rate=max(0.0, float(decay_rate)),
        )

    def constrained_recall_from_experiences(
        self,
        experiences,
        *,
        mean_external: float = 0.0,
        external_vector: Optional[Dict[str, float]] = None,
        k: float = 0.25,
        now: Optional[float] = None,
    ) -> Dict[str, float]:
        """Sum recall traces with the same per-impulse and total caps as ``step``.

        One pass, no impulse object per episode. The result is the recall
        vector ``step`` would have produced from ``trace.to_impulse`` calls.
        """
        reference_external = max(0.0, float(mean_external))
        if reference_external <= 0.0:
            reference_external = max(0.0, float(self.last_external_mean_impulse))
        per_impulse_cap = 0.3 * reference_external if reference_external > 0.0 else 0.15
        gain = _clamp(k, 0.1, 0.4)
        ts_now = float(now if now is not None else time.time())
        width = len(AXES)
        acc = [0.0] * width
        any_trace = False
        for exp in experiences:
            trace = getattr(exp, "emotional_trace", None)
            if not isinstance(trace, EmotionalTrace):
                continue
            any_trace = True
            dt = ts_now - float(trace.timestamp)
            if dt < 0.0:
                dt = 0.0
            decayed = trace.intensity * math.exp(-trace.decay_rate * dt)
            if decayed < 0.0:
                decayed = 0.0
            elif decayed > 1.0:
                decayed = 1.0
            intensity = gain * decayed
            if intensity < 0.0:
                intensity = 0.0
            elif intensity > 1.0:
                intensity = 1.0
            raw = trace._raw_axes
            values = []
            magnitude_sum = 0.0
            for axis in AXES:
                value = raw[axis] * intensity
                if value < -1.0:
                    value = -1.0
                elif value > 1.0:
                    value = 1.0
                values.append(value)
                magnitude_sum += value if value >= 0.0 else -value
            mag = magnitude_sum / float(width or 1)
            if mag > per_impulse_cap > 0.0:
                new_intensity = intensity * (per_impulse_cap / mag)
                if new_intensity < 0.0:
                    new_intensity = 0.0
                elif new_intensity > 1.0:
                    new_intensity = 1.0
                values = []
                for axis in AXES:
                    value = raw[axis] * new_intensity
                    if value < -1.0:
                        value = -1.0
                    elif value > 1.0:
                        value = 1.0
                    values.append(value)
            for index in range(width):
                acc[index] += values[index]
        if not any_trace:
            return None
        recall_vector = {AXES[index]: acc[index] for index in range(width)}
        external = external_vector if external_vector is not None else _zero_vector()
        return self._cap_recall_norm(recall_vector, external)

    def _cap_recall_norm(self, recall_vector: Dict[str, float], external_vector: Dict[str, float]) -> Dict[str, float]:
        ext_norm = _vector_l2_norm(external_vector)
        rec_norm = _vector_l2_norm(recall_vector)
        if rec_norm <= 0.0:
            return recall_vector
        if ext_norm > 0.0:
            max_recall_norm = (2.0 / 3.0) * ext_norm
        else:
            max_recall_norm = 0.3
        if rec_norm > max_recall_norm > 0.0:
            return self._scale_vector(recall_vector, max_recall_norm / rec_norm)
        return recall_vector

    def recall_trace(self, trace: EmotionalTrace, k: float = 0.25, now: Optional[float] = None) -> EmotionalImpulse:
        if not isinstance(trace, EmotionalTrace):
            return EmotionalImpulse(vector={}, intensity=0.0, source="memory")
        return trace.to_impulse(k=k, now=now)

    def decision_bias(self, matrix: Optional[Dict[str, Dict[str, float]]] = None) -> Dict[str, float]:
        weights = _normalize_matrix(matrix if matrix is not None else self.decision_matrix)
        out: Dict[str, float] = {}
        for dim in DECISION_DIMENSIONS:
            row = weights.get(dim, {})
            value = 0.0
            for axis in AXES:
                value += float(row.get(axis, 0.0)) * float(self.axes.get(axis, 0.0))
            out[dim] = _clamp(value, -1.0, 1.0)
        return out

    @staticmethod
    def outcome_impulse(status: str, magnitude: float = 1.0) -> EmotionalImpulse:
        """Map an MCP/status envelope token onto a canonical EmotionalImpulse."""
        key = str(status or "unknown").strip().lower()
        vector = dict(_OUTCOME_STATUS_VECTORS.get(key) or _OUTCOME_STATUS_VECTORS["unknown"])
        intensity = _clamp(magnitude, 0.0, 1.0)
        return EmotionalImpulse(vector=vector, intensity=intensity, source="external")

    def rank_weights(self) -> Dict[str, float]:
        """Derived ranking weights in [0, 1] for body/schema binding. Pure readout."""
        bias = self.decision_bias()
        stress = _clamp(self.axes.get("stress", 0.0), -1.0, 1.0)
        valence = _clamp(self.axes.get("valence", 0.0), -1.0, 1.0)
        trust = _clamp(self.axes.get("trust", 0.0), -1.0, 1.0)
        arousal = _clamp(self.axes.get("arousal", 0.0), -1.0, 1.0)
        stability = _clamp(self.axes.get("stability", 0.0), -1.0, 1.0)
        attachment = _clamp(self.axes.get("attachment", 0.0), -1.0, 1.0)
        curiosity = _clamp(self.axes.get("curiosity", 0.0), -1.0, 1.0)
        dominance = _clamp(self.axes.get("dominance", 0.0), -1.0, 1.0)
        risk = _clamp(bias.get("risk", 0.0), -1.0, 1.0)
        response_speed = _clamp(bias.get("response_speed", 0.0), -1.0, 1.0)
        goal_priority = _clamp(bias.get("goal_priority", 0.0), -1.0, 1.0)

        def _weight(value: float) -> float:
            signed = _clamp(value, -1.0, 1.0)
            return _clamp(signed, 0.0, 1.0)

        caution_raw = 0.5 + 0.5 * _clamp(stress - 0.5 * valence + 0.3 * (1.0 - trust), -1.0, 1.0)
        caution = _clamp(caution_raw, 0.0, 1.0)
        cost_aversion = _weight(0.4 - 0.6 * risk + 0.4 * caution)
        speed_seek = _weight(
            0.5 + 0.7 * response_speed + 0.3 * max(0.0, arousal) - 0.2 * stability
        )
        reliability = _weight(0.5 + 0.5 * trust + 0.3 * attachment - 0.4 * risk)
        novelty_seek = _weight(0.5 + 0.7 * curiosity - 0.4 * stress)
        assertiveness = _weight(0.5 + 0.6 * dominance + 0.3 * goal_priority)
        return {
            "caution": caution,
            "cost_aversion": cost_aversion,
            "speed_seek": speed_seek,
            "reliability": reliability,
            "novelty_seek": novelty_seek,
            "assertiveness": assertiveness,
        }

    def legacy_axes_snapshot(self) -> Dict[str, float]:
        return _core_to_legacy_axes(self.axes)

    def legacy_params_snapshot(self, values: Optional[Dict[str, float]] = None) -> Dict[str, float]:
        src = dict(values or {})
        mapped: Dict[str, float] = {name: 0.0 for name in LEGACY_AXES}
        for axis in AXES:
            legacy_name = _CORE_TO_LEGACY_PARAM.get(axis)
            if not legacy_name:
                continue
            v = _clamp(src.get(axis, 0.0), 0.0, 1.0)
            mapped[legacy_name] = max(mapped[legacy_name], v)
        return mapped

    def snapshot(self) -> Dict[str, Any]:
        """Return immutable snapshot of current affective core state."""
        return {
            "axes": dict(self.axes),
            "legacy_axes": self.legacy_axes_snapshot(),
            "baseline": dict(self.baseline),
            "baseline_setpoint": dict(self.baseline_setpoint),
            "alpha": self.alpha,
            "axis_decay": dict(self.axis_decay),
            "affective_decay": dict(self.axis_decay),
            "lambda_reg": self.lambda_reg,
            "baseline_adapt_rate": self.baseline_adapt_rate,
            "timestamp": self.timestamp,
            "speed": self.speed(),
            "axis_conflict": self.axis_conflict(),
            "state_norm": _vector_l2_norm(self.axes),
            "norm_cap_current": float(self.dynamic_norm_cap or self.norm_cap_base),
            "norm_cap_base": self.norm_cap_base,
            "norm_cap_max": self.norm_cap_max,
            "norm_cap_global_release_rate": self.norm_cap_global_release_rate,
            "legacy_compat_weight": self.legacy_compat_weight,
            "decision_bias": self.decision_bias(),
        }

    def to_dict(self) -> dict:
        return {
            "axes": dict(self.axes),
            "baseline": dict(self.baseline),
            "baseline_setpoint": dict(self.baseline_setpoint),
            "alpha": self.alpha,
            "axis_decay": dict(self.axis_decay),
            "affective_decay": dict(self.axis_decay),
            "lambda_reg": self.lambda_reg,
            "baseline_adapt_rate": self.baseline_adapt_rate,
            "norm_cap_base": self.norm_cap_base,
            "norm_cap_max": self.norm_cap_max,
            "norm_cap_adapt_rate": self.norm_cap_adapt_rate,
            "norm_cap_release_rate": self.norm_cap_release_rate,
            "norm_cap_global_release_rate": self.norm_cap_global_release_rate,
            "dynamic_norm_cap": float(self.dynamic_norm_cap or self.norm_cap_base),
            "legacy_compat_weight": self.legacy_compat_weight,
            "decay": dict(self.decay),
            "inertia": dict(self.inertia),
            "noise_sigma": dict(self.noise_sigma),
            "fall_rate": dict(self.fall_rate),
            "decision_matrix": dict(self.decision_matrix),
            "timestamp": self.timestamp,
            "last_external_mean_impulse": self.last_external_mean_impulse,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AffectiveSpace":
        baseline = data.get("baseline", {})
        setpoint = data.get("baseline_setpoint", None)
        if not isinstance(setpoint, dict):
            setpoint = baseline
        inst = cls(
            axes=data.get("axes", {}),
            baseline=baseline,
            baseline_setpoint=setpoint,
            alpha=data.get("alpha", 0.85),
            axis_decay=data.get("axis_decay", data.get("affective_decay", {})),
            affective_decay=data.get("affective_decay"),
            lambda_reg=data.get("lambda_reg", data.get("lambda", 0.05)),
            baseline_adapt_rate=data.get("baseline_adapt_rate", DEFAULT_BASELINE_ADAPT_RATE),
            norm_cap_base=data.get("norm_cap_base", 1.5),
            norm_cap_max=data.get("norm_cap_max", data.get("norm_cap_base", 2.2)),
            norm_cap_adapt_rate=data.get("norm_cap_adapt_rate", 0.06),
            norm_cap_release_rate=data.get("norm_cap_release_rate", 0.02),
            norm_cap_global_release_rate=data.get("norm_cap_global_release_rate", 0.005),
            dynamic_norm_cap=data.get("dynamic_norm_cap"),
            legacy_compat_weight=data.get("legacy_compat_weight", 0.0),
            decay=data.get("decay", {}),
            inertia=data.get("inertia", {}),
            noise_sigma=data.get("noise_sigma", {}),
            fall_rate=data.get("fall_rate", {}),
            decision_matrix=data.get("decision_matrix", {}),
        )
        inst.timestamp = float(data.get("timestamp", time.time()))
        inst.last_external_mean_impulse = _clamp(data.get("last_external_mean_impulse", 0.0), 0.0, 1.0)
        return inst

    def axis_conflict(self) -> float:
        """Return internal conflict score based on co-activation of opposing tendencies."""
        conflicts: List[float] = []
        for axis_a, axis_b in OPPOSING_PAIRS:
            a = max(0.0, float(self.axes.get(axis_a, 0.0)))
            b = max(0.0, float(self.axes.get(axis_b, 0.0)))
            conflicts.append(_clamp(a * b, 0.0, 1.0))
        core_conflict = (sum(conflicts) / float(len(conflicts))) if conflicts else 0.0

        legacy = self.legacy_axes_snapshot()
        legacy_pairs = (
            ("pleasure", "pain"),
            ("arousal", "relaxation"),
            ("attachment", "rejection"),
        )
        legacy_conflicts = [min(float(legacy.get(a, 0.0)), float(legacy.get(b, 0.0))) for a, b in legacy_pairs]
        legacy_conflict = sum(legacy_conflicts) / float(len(legacy_conflicts)) if legacy_conflicts else 0.0

        return _clamp(max(core_conflict, legacy_conflict), 0.0, 1.0)

    def get_background_modifiers(self, background: Optional[Dict[str, float]]) -> Tuple[float, float, float]:
        """Return modifiers (decay, inertia, noise) derived from background field."""
        if not background:
            return 1.0, 1.0, 1.0
        values: List[float] = []
        for value in (background or {}).values():
            try:
                values.append(_clamp(value, 0.0, 1.0))
            except Exception:
                continue
        if not values:
            return 1.0, 1.0, 1.0
        level = sum(values) / float(len(values))
        decay_mult = max(0.4, 1.0 - 0.3 * level)
        inertia_mult = 1.0 + 0.3 * level
        noise_mult = 1.0 + 0.2 * level
        return decay_mult, inertia_mult, noise_mult

    def _noise_gain(self, wakefulness: float, uncertainty: float, conflict: float) -> float:
        wake = _clamp(wakefulness, 0.0, 1.0)
        uncertain = _clamp(uncertainty, 0.0, 1.0)
        conflict_v = _clamp(conflict, 0.0, 1.0)
        internal = self.axis_conflict()
        return 1.0 + (0.6 * wake) + (0.6 * uncertain) + (0.6 * conflict_v) + (0.4 * internal)

    def step(
        self,
        inputs: Optional[Dict[str, float]] = None,
        external_impulses: Optional[Any] = None,
        recall_impulses: Optional[Any] = None,
        recall_vector: Optional[Dict[str, float]] = None,
        internal_impulses: Optional[Any] = None,
        time_elapsed: float = 1.0,
        wakefulness: float = 0.0,
        uncertainty: float = 0.0,
        conflict: float = 0.0,
        background: Optional[Dict[str, float]] = None,
        asleep: bool = False,
    ) -> Dict[str, float]:
        """
        Update affective core over ``time_elapsed`` simulated seconds.

        ``axis_decay`` is retention per second. One second also applies the
        homeostat, so the multiplier raised to ``dt`` is
        ``clamp(axis_decay - lambda_reg, 0, 0.999)``. At ``dt=1`` this is
        the legacy step. ``time_elapsed=0`` adds impulses and does not
        decay, drift the baseline, or move the norm cap.

        Baseline tracks the lived axis at ``baseline_adapt_rate`` (per
        second) and relaxes toward the fixed setpoint ``baseline_setpoint``.
        ``asleep=True`` clears the axis and restores the setpoint
        ``SLEEP_RECOVERY_SCALE`` times faster. Impulses are applied after
        the decay, as an event at the end of the interval.
        """
        try:
            dt = float(0.0 if time_elapsed is None else time_elapsed)
        except (TypeError, ValueError):
            dt = 0.0
        if not math.isfinite(dt) or dt < 0.0:
            dt = 0.0

        external_payload = external_impulses if external_impulses is not None else inputs
        ext_list = self._normalize_impulse_payload(external_payload, default_source="external")
        rec_list = self._normalize_impulse_payload(recall_impulses, default_source="memory")
        int_list = self._normalize_impulse_payload(internal_impulses, default_source="internal")

        ext_vector, ext_mags = self._sum_impulses(ext_list)
        mean_external = (sum(ext_mags) / float(len(ext_mags))) if ext_mags else 0.0
        if mean_external > 0.0:
            self.last_external_mean_impulse = _clamp(mean_external, 0.0, 1.0)

        if recall_vector is not None:
            rec_vector = {axis: float(recall_vector.get(axis, 0.0)) for axis in AXES}
        else:
            rec_vector = self._apply_recall_constraints(
                recall_impulses=rec_list,
                mean_external=mean_external,
                external_vector=ext_vector,
            )
        int_vector, _ = self._sum_impulses(int_list)
        combined_impulse = {
            axis: float(ext_vector.get(axis, 0.0)) + float(rec_vector.get(axis, 0.0)) + float(int_vector.get(axis, 0.0))
            for axis in AXES
        }
        self._update_dynamic_norm_cap(
            impulse_norm=_vector_l2_norm(combined_impulse),
            dt=dt,
            wakefulness=wakefulness,
        )

        decay_mult, inertia_mult, noise_mult = self.get_background_modifiers(background)
        noise_gain = self._noise_gain(wakefulness=wakefulness, uncertainty=uncertainty, conflict=conflict)
        compat_weight = _clamp(self.legacy_compat_weight, 0.0, 1.0)
        sleep_scale = SLEEP_RECOVERY_SCALE if asleep else 1.0
        adapt_gain = _clamp(self.baseline_adapt_rate, 0.0, 1.0)
        recover_rate = _clamp(self.baseline_adapt_rate * BASELINE_RECOVERY_RATE_RATIO, 0.0, 1.0)
        if sleep_scale == 1.0:
            recover_gain = recover_rate
        else:
            recover_gain = 1.0 - (1.0 - recover_rate) ** sleep_scale
        coupling = adapt_gain * (1.0 - recover_gain)

        self.last_axes = dict(self.axes)
        self.last_noise_sigma = {}
        relaxed_axis: Dict[str, float] = {}
        relaxed_baseline: Dict[str, float] = {}

        for axis in AXES:
            current = float(self.axes.get(axis, 0.0))
            baseline = float(self.baseline.get(axis, 0.0))
            setpoint = float(self.baseline_setpoint.get(axis, baseline))
            ext = float(ext_vector.get(axis, 0.0))
            rec = float(rec_vector.get(axis, 0.0))
            internal = float(int_vector.get(axis, 0.0))
            axis_decay_factor = _clamp(self.axis_decay.get(axis, self.alpha), 0.0, 0.999)
            retention = _clamp(axis_decay_factor - float(self.lambda_reg), 0.0, 0.999)
            if sleep_scale != 1.0:
                retention = retention ** sleep_scale

            if compat_weight > 0.0 and dt > 0.0:
                decay = float(self.decay.get(axis, 0.0)) * decay_mult
                inertia = float(self.inertia.get(axis, 0.0)) * inertia_mult
                sigma = float(self.noise_sigma.get(axis, 0.0)) * noise_mult * noise_gain
                noise = self.rng.normalvariate(0.0, sigma) if sigma > 0.0 else 0.0
                compat_delta = ((-decay * current + inertia + noise) * dt) * compat_weight
            else:
                sigma = 0.0
                compat_delta = 0.0

            deviation, baseline_deviation = _relax_deviation(
                current - setpoint,
                baseline - setpoint,
                dt,
                retention,
                adapt_gain,
                recover_gain,
            )
            relaxed_axis[axis] = setpoint + deviation
            relaxed_baseline[axis] = setpoint + baseline_deviation
            self.axes[axis] = relaxed_axis[axis] + ext + rec + internal + compat_delta
            self.last_noise_sigma[axis] = sigma

        for axis in AXES:
            self.axes[axis] = _clamp(self.axes[axis], -1.0, 1.0)
        self._enforce_norm_cap()
        if dt > 0.0:
            for axis in AXES:
                delta = float(self.axes[axis]) - relaxed_axis[axis]
                self.baseline[axis] = _clamp(relaxed_baseline[axis] + coupling * delta, -1.0, 1.0)

        self.timestamp = time.time()
        return dict(self.axes)

    def apply_impulses(
        self,
        inputs: Optional[Dict[str, float]] = None,
        external_impulses: Optional[Any] = None,
        recall_impulses: Optional[Any] = None,
        recall_vector: Optional[Dict[str, float]] = None,
        internal_impulses: Optional[Any] = None,
    ) -> Dict[str, float]:
        """Add impulses with no time advance (``time_elapsed=0``)."""
        return self.step(
            inputs=inputs,
            external_impulses=external_impulses,
            recall_impulses=recall_impulses,
            recall_vector=recall_vector,
            internal_impulses=internal_impulses,
            time_elapsed=0.0,
        )

    def advance(
        self,
        time_elapsed: float = 1.0,
        wakefulness: float = 0.0,
        uncertainty: float = 0.0,
        conflict: float = 0.0,
        background: Optional[Dict[str, float]] = None,
        asleep: bool = False,
    ) -> Dict[str, float]:
        """Advance retention and allostasis by simulated seconds. No impulses."""
        return self.step(
            time_elapsed=time_elapsed,
            wakefulness=wakefulness,
            uncertainty=uncertainty,
            conflict=conflict,
            background=background,
            asleep=asleep,
        )

    def speed(self) -> float:
        """Return speed V = |A(t) - A(t-1)| (L1 norm)."""
        if not self.last_axes:
            return 0.0
        return sum(abs(float(self.axes.get(axis, 0.0)) - float(self.last_axes.get(axis, 0.0))) for axis in AXES)

    def distance_to(self, other: Any, weights: Optional[Dict[str, float]] = None) -> float:
        """Return weighted distance D(A,B)=sum_i w_i * |A_i-B_i|."""
        other_axes: Dict[str, float]
        if isinstance(other, AffectiveSpace):
            other_axes = dict(other.axes)
        elif isinstance(other, dict):
            payload = other.get("axes", other)
            if not isinstance(payload, dict):
                payload = {}
            other_axes = self._fill_state_vector(payload, default_value=0.0)
        else:
            other_axes = _zero_vector()

        weights = weights or {}
        total = 0.0
        for axis in AXES:
            weight = float(weights.get(axis, 1.0))
            total += weight * abs(float(self.axes.get(axis, 0.0)) - float(other_axes.get(axis, 0.0)))
        return total

    def obsessiveness(self, axis: str) -> float:
        """
        Return obsessiveness estimate:
        high inertia + low fall_rate + high focus proxy.
        """
        canonical_axis = axis if axis in AXES else _LEGACY_PARAM_AXIS.get(axis, "")
        if canonical_axis not in AXES:
            return 0.0
        inertia = _clamp(self.inertia.get(canonical_axis, 0.0), 0.0, 1.0)
        fall = _clamp(self.fall_rate.get(canonical_axis, 0.0), 0.0, 1.0)
        focus_proxy = _clamp((self.axes.get("dominance", 0.0) + self.axes.get("curiosity", 0.0) + 2.0) / 4.0, 0.0, 1.0)
        score = (inertia + (1.0 - fall) + focus_proxy) / 3.0
        return _clamp(score, 0.0, 1.0)

    def obsessiveness_map(self) -> Dict[str, float]:
        """Return obsessiveness per canonical axis."""
        return {axis: self.obsessiveness(axis) for axis in AXES}
