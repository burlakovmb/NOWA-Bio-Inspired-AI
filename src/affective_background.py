"""
Affective Background Field (Phase 3.75)

Maintains a slow-changing background field derived from durable affective traces.
This is a non-decisional, inertial state used for future phases.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Dict, Iterable, Optional, Any


def _clamp(value: float, min_v: float = 0.0, max_v: float = 1.0) -> float:
    try:
        v = float(value)
    except Exception:
        v = 0.0
    return max(min_v, min(max_v, v))


@dataclass
class AffectiveBackgroundField:
    """
    Slow-changing background field derived from affective traces.

    Does NOT:
    - generate affect signals
    - influence action selection
    - modify neuromodulators
    """

    base_inertia: float = 8.0
    k_life: float = 1.5
    base_decay: float = 0.01
    k_decay: float = 0.7
    base_sharpness: float = 1.0
    k_comp: float = 2.5
    noise_scale: float = 0.03
    rng: Optional[random.Random] = None
    background: Dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.rng is None:
            self.rng = random.Random()
        # Initialize known components
        for key in ("anxiety", "tension", "satisfaction", "interest"):
            self.background.setdefault(self._bg_key(key), 0.0)

    def update(
        self,
        traces: Dict[str, float],
        wakefulness: float,
        lifetime_progress: float,
        time_elapsed: float = 1.0,
    ) -> Dict[str, float]:
        """
        Update background field from traces.

        Args:
            traces: dict {trace_type: intensity}
            wakefulness: [0..1] affects noise only
            lifetime_progress: [0..1] affects dynamics only
            time_elapsed: Simulated seconds. Decay is ``(1 - rate) ** seconds``.
        """
        from learning_guard import guard_owned_writer

        if not guard_owned_writer(self, "AffectiveBackgroundField.update"):
            return dict(self.background)
        wakefulness = _clamp(wakefulness, 0.0, 1.0)
        lifetime_progress = _clamp(lifetime_progress, 0.0, 1.0)
        try:
            steps = float(time_elapsed)
        except (TypeError, ValueError):
            steps = 1.0
        if steps != steps or steps < 0.0 or steps == float("inf"):
            steps = 0.0

        inertia = self.base_inertia * (1.0 + lifetime_progress * self.k_life)
        update_rate = 1.0 / (1.0 + max(0.0, inertia))

        decay_rate = self.base_decay * (1.0 - lifetime_progress * self.k_decay)
        decay_rate = max(0.0, decay_rate)
        decay_factor = (1.0 - decay_rate) ** steps

        sharpness = self.base_sharpness * (1.0 + lifetime_progress * self.k_comp)

        target = self._apply_competition(traces, sharpness)

        noise_amp = self.noise_scale * (1.0 - wakefulness)

        keys = set(self.background.keys())
        for trace_type in target.keys():
            keys.add(self._bg_key(trace_type))

        for key in keys:
            trace_type = key.replace("background_", "", 1)
            tgt = float(target.get(trace_type, 0.0))
            current = float(self.background.get(key, 0.0))
            # Decay existing background
            current *= decay_factor
            # Move toward target with inertia
            current += (tgt - current) * update_rate
            # Add unbiased noise (wakefulness only)
            if noise_amp > 0.0:
                current += (self.rng.random() * 2.0 - 1.0) * noise_amp
            self.background[key] = _clamp(current, 0.0, 1.0)

        return dict(self.background)

    def update_from_traces(
        self,
        traces: Iterable[Any],
        wakefulness: float,
        lifetime_progress: float,
        time_elapsed: float = 1.0,
    ) -> Dict[str, float]:
        """Update from iterable of trace objects (AffectiveTrace-like)."""
        trace_dict: Dict[str, float] = {}
        for t in traces or []:
            try:
                trace_type = getattr(t, "trace_type", None) or getattr(t, "type", None) or t.get("type")
                intensity = getattr(t, "intensity", None)
                if intensity is None and isinstance(t, dict):
                    intensity = t.get("intensity", 0.0)
                if trace_type:
                    trace_dict[str(trace_type)] = float(intensity or 0.0)
            except Exception:
                continue
        return self.update(trace_dict, wakefulness, lifetime_progress, time_elapsed=time_elapsed)

    def snapshot(self) -> Dict[str, float]:
        return dict(self.background)

    def to_dict(self) -> dict:
        return {
            "background": dict(self.background),
            "base_inertia": self.base_inertia,
            "k_life": self.k_life,
            "base_decay": self.base_decay,
            "k_decay": self.k_decay,
            "base_sharpness": self.base_sharpness,
            "k_comp": self.k_comp,
            "noise_scale": self.noise_scale,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AffectiveBackgroundField":
        inst = cls(
            base_inertia=float(data.get("base_inertia", 8.0)),
            k_life=float(data.get("k_life", 1.5)),
            base_decay=float(data.get("base_decay", 0.01)),
            k_decay=float(data.get("k_decay", 0.7)),
            base_sharpness=float(data.get("base_sharpness", 1.0)),
            k_comp=float(data.get("k_comp", 2.5)),
            noise_scale=float(data.get("noise_scale", 0.03)),
        )
        bg = data.get("background", {}) or {}
        for k, v in bg.items():
            try:
                inst.background[str(k)] = _clamp(float(v), 0.0, 1.0)
            except Exception:
                continue
        return inst

    @staticmethod
    def _bg_key(trace_type: str) -> str:
        return f"background_{trace_type}"

    @staticmethod
    def _apply_competition(traces: Dict[str, float], sharpness: float) -> Dict[str, float]:
        values = {k: _clamp(v, 0.0, 1.0) for k, v in (traces or {}).items()}
        total = sum(values.values())
        if total <= 0.0:
            return {k: 0.0 for k in values.keys()}

        weights = {}
        for k, v in values.items():
            weights[k] = math.exp(v * sharpness)
        sum_w = sum(weights.values()) or 1.0

        target = {}
        for k, w in weights.items():
            target[k] = _clamp((w / sum_w) * total, 0.0, 1.0)
        return target
