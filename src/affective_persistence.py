"""
Affective Persistence (Phase 3.5)

Implements durable affective traces that persist over time, decay slowly,
and accumulate when similar affect signals repeat. This module is strictly
non-decisional: it does NOT select actions or directly influence the selector.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Any, List


@dataclass
class AffectiveTrace:
    """Single affective trace entry."""

    trace_type: str
    intensity: float
    decay_rate: float
    age: float
    source: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "type": self.trace_type,
            "intensity": float(self.intensity),
            "decay_rate": float(self.decay_rate),
            "age": float(self.age),
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AffectiveTrace":
        return cls(
            trace_type=data.get("type", "unknown"),
            intensity=float(data.get("intensity", 0.0)),
            decay_rate=float(data.get("decay_rate", 0.02)),
            age=float(data.get("age", 0.0)),
            source=data.get("source"),
        )


class AffectivePersistenceLayer:
    """
    Maintains durable affective traces (Phase 3.5).

    Reads:
    - affect dimensions (valence, arousal, threat, curiosity)
    - neuromodulators (for retention bias; low serotonin preserves traces)
    - temporal summaries (T1/T2) for baseline-relative effects

    Does NOT:
    - initiate actions
    - directly influence selector
    - control wakefulness
    """

    def __init__(
        self,
        default_decay_rate: float = 0.02,
        decay_rate_range: tuple = (0.01, 0.05),
        accumulation_gain: float = 0.35,
        min_intensity: float = 0.001,
    ):
        self.default_decay_rate = self._clamp(default_decay_rate, *decay_rate_range)
        self.decay_rate_range = decay_rate_range
        self.accumulation_gain = accumulation_gain
        self.min_intensity = min_intensity
        self._traces: Dict[str, AffectiveTrace] = {}

    def update(
        self,
        affect_state: Any,
        neuromodulators: Optional[Any] = None,
        temporal_levels: Optional[Dict[str, Dict[str, float]]] = None,
        time_elapsed: float = 1.0,
    ) -> None:
        """
        Update traces: decay and accumulate from current affect signals.

        Args:
            affect_state: AffectiveState-like object
            neuromodulators: NeuromodulatorState-like object (optional)
            temporal_levels: Dict from TemporalLevels.get_levels() (optional)
            time_elapsed: Simulated seconds. The decay exponent is per second.
        """
        if affect_state is None:
            return

        # 1) Decay existing traces
        self._decay_traces(time_elapsed=time_elapsed)

        # 2) Compute new affect signals to accumulate
        signals = self._compute_signals(affect_state, temporal_levels=temporal_levels)

        # 3) Accumulate traces for active signals
        for trace_type, signal in signals.items():
            if signal <= 0.05:
                continue
            self._accumulate_trace(trace_type, signal, neuromodulators)

        # 4) Prune tiny traces
        self._prune_traces()

    def _accumulate_trace(self, trace_type: str, signal: float, neuromodulators: Optional[Any]) -> None:
        trace = self._traces.get(trace_type)
        if trace is None:
            trace = AffectiveTrace(
                trace_type=trace_type,
                intensity=0.0,
                decay_rate=self.default_decay_rate,
                age=0.0,
                source=None,
            )
            self._traces[trace_type] = trace

        retention_factor = 1.0
        try:
            serotonin = float(getattr(neuromodulators, "serotonin", 0.1))
            # Low serotonin increases retention
            retention_factor += max(0.0, 0.1 - serotonin) * 2.0
        except Exception:
            pass

        # Non-linear accumulation: stronger traces accumulate faster
        non_linear = 1.0 + min(1.0, trace.intensity) * 0.5

        increment = signal * self.accumulation_gain * retention_factor * non_linear
        trace.intensity = self._clamp(trace.intensity + increment, 0.0, 1.0)

    def _decay_traces(self, time_elapsed: float = 1.0) -> None:
        try:
            steps = float(time_elapsed)
        except (TypeError, ValueError):
            steps = 1.0
        if steps != steps or steps < 0.0 or steps == float("inf"):
            steps = 0.0
        for trace in self._traces.values():
            decay_rate = self._clamp(trace.decay_rate, *self.decay_rate_range)
            decay_factor = (1.0 - decay_rate) ** steps
            trace.intensity *= decay_factor
            trace.age += steps

    def _prune_traces(self) -> None:
        to_delete = [k for k, t in self._traces.items() if t.intensity < self.min_intensity]
        for k in to_delete:
            del self._traces[k]

    def _compute_signals(
        self,
        affect_state: Any,
        temporal_levels: Optional[Dict[str, Dict[str, float]]] = None,
    ) -> Dict[str, float]:
        valence = float(getattr(affect_state, "valence", 0.0))
        arousal = float(getattr(affect_state, "arousal", 0.0))
        threat = float(getattr(affect_state, "threat", 0.0))
        curiosity = float(getattr(affect_state, "curiosity", 0.0))
        if temporal_levels:
            for key in ("T0_current", "T0", "T1_mean", "T2_baseline"):
                bucket = temporal_levels.get(key) or {}
                if not isinstance(bucket, dict):
                    continue
                if "stress" in bucket:
                    try:
                        threat = max(0.0, float(bucket.get("stress", threat)))
                    except Exception:
                        pass
                if "curiosity" in bucket:
                    try:
                        curiosity = float(bucket.get("curiosity", curiosity))
                    except Exception:
                        pass
                if "valence" in bucket:
                    try:
                        valence = float(bucket.get("valence", valence))
                    except Exception:
                        pass
                break

        baseline = {}
        t1_mean = {}
        if temporal_levels:
            baseline = temporal_levels.get("T2_baseline", {}) or {}
            t1_mean = temporal_levels.get("T1_mean", {}) or {}

        base_valence = float(baseline.get("valence", 0.0))
        base_threat = float(baseline.get("threat", 0.0))
        base_curiosity = float(baseline.get("curiosity", 0.0))
        t1_curiosity = float(t1_mean.get("curiosity", curiosity))

        dv = valence - base_valence
        dt = threat - base_threat

        # Primary trace signals
        anxiety = self._clamp(threat + max(0.0, dt) * 0.5, 0.0, 1.0)
        tension = self._clamp((arousal * 0.4) + (max(0.0, dt) * 0.4) + (max(0.0, -dv) * 0.2), 0.0, 1.0)
        satisfaction = self._clamp(max(0.0, valence) + max(0.0, dv) * 0.5, 0.0, 1.0)
        interest = self._clamp(curiosity + max(0.0, (t1_curiosity - base_curiosity)) * 0.4, 0.0, 1.0)

        return {
            "anxiety": anxiety,
            "tension": tension,
            "satisfaction": satisfaction,
            "interest": interest,
        }

    def get_trace(self, trace_type: str) -> Optional[AffectiveTrace]:
        return self._traces.get(trace_type)

    def get_traces(self) -> List[AffectiveTrace]:
        return list(self._traces.values())

    def snapshot(self) -> List[dict]:
        return [t.to_dict() for t in self.get_traces()]

    def to_dict(self) -> dict:
        return {
            "traces": self.snapshot(),
            "default_decay_rate": self.default_decay_rate,
            "decay_rate_range": list(self.decay_rate_range),
            "accumulation_gain": self.accumulation_gain,
            "min_intensity": self.min_intensity,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AffectivePersistenceLayer":
        layer = cls(
            default_decay_rate=float(data.get("default_decay_rate", 0.02)),
            decay_rate_range=tuple(data.get("decay_rate_range", (0.01, 0.05))),
            accumulation_gain=float(data.get("accumulation_gain", 0.35)),
            min_intensity=float(data.get("min_intensity", 0.001)),
        )
        traces = data.get("traces", []) or []
        for t in traces:
            try:
                trace = AffectiveTrace.from_dict(t)
                layer._traces[trace.trace_type] = trace
            except Exception:
                continue
        return layer

    @staticmethod
    def _clamp(value: float, min_v: float, max_v: float) -> float:
        return max(min_v, min(max_v, float(value)))
