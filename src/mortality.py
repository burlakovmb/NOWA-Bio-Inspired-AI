"""Autonomous aging and death dynamics for emergent evolution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


MORTALITY_VERSION = "1.0"
BASE_LIFESPAN_STEPS = 5000
BASE_LIFESPAN_AGE_S = float(BASE_LIFESPAN_STEPS)


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        casted = float(value)
    except (TypeError, ValueError):
        return float(fallback)
    if casted != casted or casted in (float("inf"), float("-inf")):
        return float(fallback)
    return casted


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(fallback)


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, float(value)))


@dataclass
class MortalitySystem:
    """Autonomous subsystem handling senescence and irreversible death."""

    max_lifespan_steps: int = BASE_LIFESPAN_STEPS
    max_lifespan_age_s: float | None = None
    critical_energy_threshold: float = 0.05
    critical_wakefulness_threshold: float = 0.95
    senescence_start_fraction: float = 0.7
    senescence_vitality_loss_rate: float = 0.001
    vitality: float = 1.0
    senescence_rate: float = 0.0
    cause_of_death: str = ""
    death_step: int = -1

    def __post_init__(self) -> None:
        self.max_lifespan_steps = max(1, _safe_int(self.max_lifespan_steps, BASE_LIFESPAN_STEPS))
        if self.max_lifespan_age_s is None:
            self.max_lifespan_age_s = None
        else:
            self.max_lifespan_age_s = max(
                1e-9,
                _safe_float(self.max_lifespan_age_s, float(self.max_lifespan_steps)),
            )
        self.critical_energy_threshold = _clamp(
            _safe_float(self.critical_energy_threshold, 0.05),
            0.0,
            1.0,
        )
        self.critical_wakefulness_threshold = _clamp(
            _safe_float(self.critical_wakefulness_threshold, 0.95),
            0.0,
            1.0,
        )
        self.senescence_start_fraction = _clamp(
            _safe_float(self.senescence_start_fraction, 0.7),
            0.0,
            1.0,
        )
        self.senescence_vitality_loss_rate = _clamp(
            _safe_float(self.senescence_vitality_loss_rate, 0.001),
            0.0,
            1.0,
        )
        self.vitality = _clamp(_safe_float(self.vitality, 1.0), 0.0, 1.0)
        self.senescence_rate = _clamp(_safe_float(self.senescence_rate, 0.0), 0.0, 1.0)
        self.cause_of_death = str(self.cause_of_death or "")
        self.death_step = _safe_int(self.death_step, -1)

    def is_dead(self) -> bool:
        """Return whether death has already occurred."""
        return self.death_step >= 0

    def get_age_fraction(self, lived_steps: int, biological_age_s: float | None = None) -> float:
        """Return normalized age in [0, 1]."""
        if biological_age_s is not None and self.max_lifespan_age_s is not None:
            age = max(0.0, _safe_float(biological_age_s, 0.0))
            denominator = max(1e-9, self.max_lifespan_age_s)
        else:
            age = float(max(0, _safe_int(lived_steps, 0)))
            denominator = float(max(1, _safe_int(self.max_lifespan_steps, BASE_LIFESPAN_STEPS)))
        return _clamp(age / denominator, 0.0, 1.0)

    def _register_death(self, cause: str, lived_steps: int) -> bool:
        self.cause_of_death = str(cause or "")
        self.death_step = max(0, _safe_int(lived_steps, 0))
        return True

    def update(
        self,
        energy: float,
        wakefulness: float,
        lived_steps: int,
        cortisol_mean: float,
        biological_age_s: float | None = None,
        dt_s: float = 1.0,
    ) -> bool:
        """
        Update one step of aging and mortality.

        Returns True only on the step where the death condition was detected.
        """
        if self.is_dead():
            return False

        age_steps = max(0, _safe_int(lived_steps, 0))
        energy_v = _clamp(_safe_float(energy, 0.0), 0.0, 1.0)
        wake_v = _clamp(_safe_float(wakefulness, 0.0), 0.0, 1.0)
        cortisol_v = _clamp(_safe_float(cortisol_mean, 0.0), 0.0, 1.0)
        dt_v = max(0.0, _safe_float(dt_s, 1.0))
        age_metric = max(0.0, _safe_float(biological_age_s, 0.0)) if biological_age_s is not None else None
        age_fraction = self.get_age_fraction(age_steps, biological_age_s=age_metric)
        if age_fraction >= self.senescence_start_fraction:
            remaining = max(1e-9, 1.0 - self.senescence_start_fraction)
            self.senescence_rate = _clamp(
                (age_fraction - self.senescence_start_fraction) / remaining,
                0.0,
                1.0,
            )
            self.vitality -= (
                self.senescence_rate
                * self.senescence_vitality_loss_rate
                * (1.0 + cortisol_v)
                * dt_v
            )
            self.vitality = _clamp(self.vitality, 0.0, 1.0)
        else:
            self.senescence_rate = 0.0
            self.vitality = _clamp(self.vitality, 0.0, 1.0)

        cause = self._lethal_cause(
            energy_v=energy_v,
            wake_v=wake_v,
            age_steps=age_steps,
            age_metric=age_metric,
        )
        if cause:
            return self._register_death(cause, age_steps)
        return False

    def apply_if_already_lethal(
        self,
        energy: float,
        wakefulness: float,
        lived_steps: int,
        biological_age_s: float | None = None,
    ) -> bool:
        """Record death when ``update`` raised before it could do so.

        Senescence does not advance here. A bookkeeping error must not
        erase exhaustion, sleep debt, old age, or vitality that is already
        zero — those still kill.
        """
        if self.is_dead():
            return True
        age_steps = max(0, _safe_int(lived_steps, 0))
        energy_v = _clamp(_safe_float(energy, 0.0), 0.0, 1.0)
        wake_v = _clamp(_safe_float(wakefulness, 0.0), 0.0, 1.0)
        age_metric = (
            max(0.0, _safe_float(biological_age_s, 0.0))
            if biological_age_s is not None
            else None
        )
        cause = self._lethal_cause(
            energy_v=energy_v,
            wake_v=wake_v,
            age_steps=age_steps,
            age_metric=age_metric,
        )
        if cause:
            return self._register_death(cause, age_steps)
        return False

    def _lethal_cause(
        self,
        *,
        energy_v: float,
        wake_v: float,
        age_steps: int,
        age_metric: float | None,
    ) -> str:
        if energy_v <= self.critical_energy_threshold:
            return "exhaustion"
        if wake_v >= self.critical_wakefulness_threshold:
            return "sleep_deprivation"
        if self.max_lifespan_age_s is None:
            if age_steps >= self.max_lifespan_steps:
                return "old_age"
        elif age_metric is not None and age_metric >= self.max_lifespan_age_s:
            return "old_age"
        if self.vitality <= 0.0:
            return "senescence"
        return ""

    def snapshot(self) -> Dict[str, Any]:
        """Return a snapshot of current mortality subsystem state."""
        return {
            "version": MORTALITY_VERSION,
            "max_lifespan_steps": int(self.max_lifespan_steps),
            "max_lifespan_age_s": (
                None if self.max_lifespan_age_s is None else float(self.max_lifespan_age_s)
            ),
            "critical_energy_threshold": float(self.critical_energy_threshold),
            "critical_wakefulness_threshold": float(self.critical_wakefulness_threshold),
            "senescence_start_fraction": float(self.senescence_start_fraction),
            "senescence_vitality_loss_rate": float(self.senescence_vitality_loss_rate),
            "vitality": float(self.vitality),
            "senescence_rate": float(self.senescence_rate),
            "cause_of_death": str(self.cause_of_death),
            "death_step": int(self.death_step),
        }

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to JSON-compatible dictionary."""
        return self.snapshot()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MortalitySystem":
        """Restore subsystem state from dictionary."""
        payload = data if isinstance(data, dict) else {}
        max_lifespan_steps = _safe_int(payload.get("max_lifespan_steps"), BASE_LIFESPAN_STEPS)
        raw_lifespan_age_s = payload.get("max_lifespan_age_s")
        max_lifespan_age_s = None
        if raw_lifespan_age_s is not None:
            max_lifespan_age_s = _safe_float(raw_lifespan_age_s, float(max_lifespan_steps))
        return cls(
            max_lifespan_steps=max_lifespan_steps,
            max_lifespan_age_s=max_lifespan_age_s,
            critical_energy_threshold=_safe_float(payload.get("critical_energy_threshold"), 0.05),
            critical_wakefulness_threshold=_safe_float(payload.get("critical_wakefulness_threshold"), 0.95),
            senescence_start_fraction=_safe_float(payload.get("senescence_start_fraction"), 0.7),
            senescence_vitality_loss_rate=_safe_float(payload.get("senescence_vitality_loss_rate"), 0.001),
            vitality=_safe_float(payload.get("vitality"), 1.0),
            senescence_rate=_safe_float(payload.get("senescence_rate"), 0.0),
            cause_of_death=str(payload.get("cause_of_death", "") or ""),
            death_step=_safe_int(payload.get("death_step"), -1),
        )


__all__ = [
    "MORTALITY_VERSION",
    "BASE_LIFESPAN_STEPS",
    "MortalitySystem",
]
