from __future__ import annotations

import math
import time
from collections import deque
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Dict, List, Mapping, Optional, Tuple

from simulation_utility import compute_drive_utility_components
from basal_ganglia import NO_ACTION


# GUI and diagnostics read the latest organism tick. Older ticks repeat
# state that the drive and energy systems already hold. The counter below
# stays equal to the number of steps, which snapshot reports as tick_count.
TICK_HISTORY_RETAIN = 1
# failure_log keeps the most recent soft failures for inspection and the save
# (issue #28): enough to see what went wrong lately, bounded over a long life.
FAILURE_LOG_RETAIN = 256

DRIVE_NAMES: Tuple[str, ...] = (
    "curiosity",
    "social_drive",
    "goal_tension",
    "exploration",
    "energy_need",
)

AXES: Tuple[str, ...] = (
    "valence",
    "arousal",
    "dominance",
    "stress",
    "trust",
    "curiosity",
    "stability",
    "attachment",
)

IMPULSE_TEMPLATES: Dict[str, Dict[str, float]] = {
    "curiosity": {"curiosity": 1.0, "dominance": 0.3},
    "social_drive": {"trust": 0.9, "attachment": 0.7},
    "goal_tension": {"dominance": 1.0, "stress": 0.4},
    "exploration": {"curiosity": 1.0, "arousal": 0.6},
    "energy_need": {"stress": 0.8, "arousal": -0.3},
}

AGENT_MODES: Tuple[str, ...] = ("IDLE", "ACTIVE", "REFLECTION")

PHYSIOLOGY_MODES: Tuple[str, ...] = (
    "idle",
    "passive",
    "internal_processing",
    "speaking",
    "low_energy",
)

DEFAULT_PHYSIOLOGY_LOADS: Dict[str, float] = {
    "idle": 0.06,
    "passive": 0.18,
    "internal_processing": 0.34,
    "speaking": 0.24,
    "low_energy": 0.08,
}


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _clamp(value: Any, lo: float, hi: float) -> float:
    v = _f(value, lo)
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


def _l1(vector: Mapping[str, Any]) -> float:
    return sum(abs(_f(vector.get(k, 0.0))) for k in AXES)


def _l2(vector: Mapping[str, Any]) -> float:
    return math.sqrt(sum(_f(vector.get(k, 0.0)) ** 2 for k in AXES))


def _scaled(vector: Mapping[str, Any], factor: float) -> Dict[str, float]:
    s = max(0.0, _f(factor, 0.0))
    return {k: _f(vector.get(k, 0.0)) * s for k in AXES}


class OrganismInvariantError(RuntimeError):
    pass


@dataclass(frozen=True)
class DriveRule:
    accumulation_rate: float = 0.01
    discharge_rate: float = 0.001
    decay_rate: float = 0.001
    affect_weights: Dict[str, float] = field(default_factory=dict)
    overload_gain: float = 0.0


def default_drive_rules() -> Dict[str, DriveRule]:
    return {
        "curiosity": DriveRule(0.020, 0.001, 0.001, {"curiosity": 0.025, "stress": -0.005, "stability": 0.004}),
        "social_drive": DriveRule(0.010, 0.0015, 0.0010, {"trust": 0.020, "attachment": 0.014, "stress": -0.010}),
        "goal_tension": DriveRule(0.012, 0.0010, 0.0015, {"dominance": 0.018, "stability": 0.006, "stress": 0.010}),
        "exploration": DriveRule(0.011, 0.0012, 0.0012, {"curiosity": 0.020, "dominance": 0.008, "stress": -0.005}),
        "energy_need": DriveRule(0.004, 0.0010, 0.0010, {"stress": 0.008, "arousal": 0.004}),
    }


@dataclass
class OrganismHardLimits:
    max_internal_cycles_per_window: int = 8
    internal_cycles_window_seconds: float = 60.0
    max_active_memory_recalls: int = 6
    max_speech_events_per_interval: int = 5
    speech_interval_seconds: float = 30.0
    energy_floor_threshold: float = 0.05
    drive_thresholds: Dict[str, float] = field(default_factory=dict)


class DriveSystem:
    def __init__(
        self,
        rules: Optional[Mapping[str, DriveRule]] = None,
        initial_drives: Optional[Mapping[str, float]] = None,
        overload_start: float = 0.80,
        energy_need_coupling: float = 0.35,
    ) -> None:
        self.rules = default_drive_rules()
        if rules:
            for name, rule in rules.items():
                if name in DRIVE_NAMES and isinstance(rule, DriveRule):
                    self.rules[name] = rule
        self.drives = {name: 0.0 for name in DRIVE_NAMES}
        if initial_drives:
            for name, value in initial_drives.items():
                if name in self.drives:
                    self.drives[name] = _clamp(value, 0.0, 1.0)
        self.overload_start = _clamp(overload_start, 0.5, 0.99)
        self.energy_need_coupling = _clamp(energy_need_coupling, 0.0, 1.0)
        self.last_unclamped_values = dict(self.drives)

    def snapshot(self) -> Dict[str, float]:
        return dict(self.drives)

    def set_drive(self, name: str, value: float) -> None:
        if name in self.drives:
            self.drives[name] = _clamp(value, 0.0, 1.0)

    def apply_discharge(self, name: str, amount: float) -> None:
        if name in self.drives:
            self.drives[name] = _clamp(self.drives[name] - max(0.0, _f(amount)), 0.0, 1.0)

    def update(
        self,
        dt: float,
        affect_snapshot: Optional[Mapping[str, Any]] = None,
        discharge_overrides: Optional[Mapping[str, float]] = None,
        energy_level: Optional[float] = None,
    ) -> Dict[str, float]:
        dt_v = max(0.0, _f(dt))
        if dt_v <= 0.0:
            return dict(self.drives)

        snap = dict(affect_snapshot or {})
        axes = snap.get("axes", snap)
        if not isinstance(axes, Mapping):
            axes = {}
        overrides = dict(discharge_overrides or {})

        unclamped: Dict[str, float] = {}
        for name in DRIVE_NAMES:
            rule = self.rules[name]
            cur = _f(self.drives.get(name, 0.0))
            affect_term = sum(_f(axes.get(axis, 0.0)) * _f(w) for axis, w in rule.affect_weights.items()) * dt_v
            acc = _f(rule.accumulation_rate) * dt_v
            dis = (_f(rule.discharge_rate) + _f(overrides.get(name, 0.0))) * dt_v
            dec = _f(rule.decay_rate) * dt_v
            raw = cur + acc + affect_term - dis - dec
            if name == "energy_need" and energy_level is not None:
                target = _clamp(1.0 - _f(energy_level, 1.0), 0.0, 1.0)
                raw = (1.0 - self.energy_need_coupling) * raw + self.energy_need_coupling * target
            unclamped[name] = raw
            self.drives[name] = _clamp(raw, 0.0, 1.0)

        self.last_unclamped_values = unclamped
        return dict(self.drives)

    def select_highest_trigger(
        self,
        weights: Optional[Mapping[str, float]],
        default_threshold: float,
        per_drive_thresholds: Optional[Mapping[str, float]] = None,
    ) -> Tuple[Optional[str], float]:
        w = dict(weights or {})
        t = dict(per_drive_thresholds or {})
        threshold_default = _f(default_threshold, 0.0)

        best_drive = None
        best_score = float("-inf")
        for name in DRIVE_NAMES:
            score = _f(self.drives.get(name, 0.0)) * _f(w.get(name, 1.0), 1.0)
            threshold = _f(t.get(name, threshold_default), threshold_default)
            if score > threshold and score > best_score:
                best_score = score
                best_drive = name
        return (best_drive, best_score if best_drive is not None else 0.0)

@dataclass
class EnergySystem:
    energy: float = 1.0
    fatigue: float = 0.0
    cognitive_cost: float = 0.035
    base_decay: float = 0.0
    recovery_rate: float = 0.030
    low_threshold: float = 0.25
    floor_threshold: float = 0.05
    suppress_internal_cycles: bool = False

    def __post_init__(self) -> None:
        self.energy = _clamp(self.energy, 0.0, 1.0)
        self.fatigue = _clamp(self.fatigue, 0.0, 1.0)
        self.suppress_internal_cycles = self.energy < max(self.low_threshold, self.floor_threshold)

    def update(self, dt: float, cognitive_load: float = 1.0, rest_time: float = 0.0) -> Dict[str, float]:
        dt_v = max(0.0, _f(dt))
        spent = (
            max(0.0, _f(self.base_decay)) * dt_v
            + max(0.0, _f(self.cognitive_cost)) * max(0.0, _f(cognitive_load)) * dt_v
        )
        # Use an exponential recovery factor so that recovery is bounded and
        # approaches full energy asymptotically. This prevents long rests from
        # instantly refilling agents while still providing realistic recovery.
        rate = max(0.0, _f(self.recovery_rate))
        rest = max(0.0, _f(rest_time))
        # factor in [0,1): fraction of deficit recovered this interval
        factor = 1.0 - math.exp(-rate * rest) if rate > 0.0 and rest > 0.0 else 0.0
        deficit = max(0.0, 1.0 - self.energy)
        recovered = deficit * factor
        prev_energy = self.energy
        prev_fatigue = self.fatigue
        self.energy = _clamp(self.energy - spent + recovered, 0.0, 1.0)
        # Fatigue reduction scales with recovered energy (kept similar factor).
        self.fatigue = _clamp(self.fatigue + spent - 0.6 * recovered, 0.0, 1.0)
        self.suppress_internal_cycles = self.energy < max(self.low_threshold, self.floor_threshold)
        return {
            "energy": self.energy,
            "fatigue": self.fatigue,
            "spent": spent,
            "recovered": recovered,
            "energy_delta": self.energy - prev_energy,
            "fatigue_delta": self.fatigue - prev_fatigue,
            "suppress_internal_cycles": self.suppress_internal_cycles,
        }

    def consume_internal_cycle(self, cycle_cost: float = 1.0) -> None:
        spent = max(0.0, _f(self.cognitive_cost)) * max(0.0, _f(cycle_cost))
        self.energy = _clamp(self.energy - spent, 0.0, 1.0)
        self.fatigue = _clamp(self.fatigue + spent, 0.0, 1.0)
        self.suppress_internal_cycles = self.energy < max(self.low_threshold, self.floor_threshold)

    def recover(self, rest_time: float) -> None:
        # Use bounded exponential recovery: recover a fraction of the missing
        # energy (deficit) according to rate and rest duration.
        rate = max(0.0, _f(self.recovery_rate))
        rest = max(0.0, _f(rest_time))
        factor = 1.0 - math.exp(-rate * rest) if rate > 0.0 and rest > 0.0 else 0.0
        deficit = max(0.0, 1.0 - self.energy)
        recovered = deficit * factor
        self.energy = _clamp(self.energy + recovered, 0.0, 1.0)
        self.fatigue = _clamp(self.fatigue - 0.5 * recovered, 0.0, 1.0)
        self.suppress_internal_cycles = self.energy < max(self.low_threshold, self.floor_threshold)

    def snapshot(self) -> Dict[str, Any]:
        return {
            "energy": self.energy,
            "fatigue": self.fatigue,
            "suppress_internal_cycles": self.suppress_internal_cycles,
        }


@dataclass
class SpeechGovernor:
    communication_threshold: float = 0.55
    relevance_minimum: float = 0.40
    cooldown_seconds: float = 5.0
    max_speech_events_per_interval: int = 5
    speech_interval_seconds: float = 30.0
    affect_overload_threshold: float = 0.70
    max_discharge_strength: float = 0.35
    last_speech_time: float = float("-inf")
    _speech_events: Deque[float] = field(default_factory=deque)

    def _prune(self, now: float) -> None:
        window = max(1e-6, _f(self.speech_interval_seconds, 1.0))
        while self._speech_events and now - self._speech_events[0] > window:
            self._speech_events.popleft()

    def evaluate_permission(self, now: float, communication_drive: float, relevance_score: float) -> Tuple[bool, str]:
        now_v = _f(now)
        self._prune(now_v)
        if _f(communication_drive) <= _f(self.communication_threshold):
            return False, "communication_threshold"
        if _f(relevance_score) <= _f(self.relevance_minimum):
            return False, "relevance_threshold"
        if now_v - _f(self.last_speech_time, float("-inf")) < _f(self.cooldown_seconds):
            return False, "cooldown"
        if len(self._speech_events) >= max(1, int(self.max_speech_events_per_interval)):
            return False, "interval_limit"
        return True, "ok"

    def register_speech(self, now: float) -> None:
        now_v = _f(now)
        self._prune(now_v)
        self._speech_events.append(now_v)
        self.last_speech_time = now_v

    def snapshot(self) -> Dict[str, Any]:
        return {
            "last_speech_time": self.last_speech_time,
            "events_in_window": len(self._speech_events),
        }

    def regulate_affect(self, affect_overload: float) -> Dict[str, float]:
        """
        Protective affect regulation path.
        This is explicitly non-motivational: it reduces affect overload and does
        not create or rank drives.
        """
        overload = _clamp(_f(affect_overload), 0.0, 1.0)
        threshold = _clamp(self.affect_overload_threshold, 0.0, 0.99)
        if overload <= threshold:
            return {
                "regulation_active": 0.0,
                "discharge_intensity": 0.0,
                "reduce_affect": 0.0,
                "reduce_overload": 0.0,
            }

        intensity = _clamp((overload - threshold) / max(1e-6, 1.0 - threshold), 0.0, 1.0)
        strength = max(0.0, _f(self.max_discharge_strength)) * intensity
        return {
            "regulation_active": 1.0,
            "discharge_intensity": intensity,
            "reduce_affect": strength,
            "reduce_overload": intensity * 0.6,
        }


class InternalSimulationLoop:
    def __init__(
        self,
        affective_core: Any,
        cognitive_core: Any,
        decision_engine: Any,
        memory_system: Any,
        threshold: float = 0.35,
        drive_weights: Optional[Mapping[str, float]] = None,
        max_internal_cycles_per_window: int = 8,
        window_seconds: float = 60.0,
        max_active_memory_recalls: int = 6,
        recall_energy_share_limit: float = 0.4,
        failure_logger: Optional[Callable[[str, Optional[Mapping[str, Any]]], None]] = None,
        basal_ganglia: Any = None,
        thalamic_gate: Any = None,
        neuromodulator_state: Any = None,
        habit_strength_provider: Optional[Callable[[List[str]], Mapping[str, Any]]] = None,
    ) -> None:
        self.affective_core = affective_core
        self.cognitive_core = cognitive_core
        self.decision_engine = decision_engine
        self.memory_system = memory_system
        self.threshold = _clamp(threshold, 0.0, 1.0)
        self.drive_weights = {name: 1.0 for name in DRIVE_NAMES}
        if drive_weights:
            for name, value in drive_weights.items():
                if name in self.drive_weights:
                    self.drive_weights[name] = max(0.0, _f(value, 1.0))
        self.max_internal_cycles_per_window = max(1, int(max_internal_cycles_per_window))
        self.window_seconds = max(1e-6, _f(window_seconds, 1.0))
        self.max_active_memory_recalls = max(1, int(max_active_memory_recalls))
        self.recall_energy_share_limit = _clamp(recall_energy_share_limit, 0.0, 0.9)
        self.failure_logger = failure_logger
        self.basal_ganglia = basal_ganglia
        self.thalamic_gate = thalamic_gate
        self.neuromodulator_state = neuromodulator_state
        self.habit_strength_provider = habit_strength_provider
        self.cycle_timestamps: Deque[float] = deque()
        self.last_result: Dict[str, Any] = {}

    def _prune_cycles(self, now: float) -> None:
        while self.cycle_timestamps and now - self.cycle_timestamps[0] > self.window_seconds:
            self.cycle_timestamps.popleft()

    def _as_list(self, value: Any) -> List[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, tuple):
            return list(value)
        return [value]

    def _recall(self, active_drive: str) -> List[Any]:
        m = self.memory_system
        if m is None:
            return []
        result: Any = None
        try:
            if hasattr(m, "recall_by_drive"):
                result = m.recall_by_drive(active_drive, limit=self.max_active_memory_recalls)
            elif hasattr(m, "recall"):
                try:
                    result = m.recall(active_drive=active_drive, limit=self.max_active_memory_recalls)
                except TypeError:
                    result = m.recall(self.max_active_memory_recalls)
            elif hasattr(m, "activate"):
                result = m.activate([active_drive])
            elif hasattr(m, "experiences"):
                result = list(getattr(m, "experiences", []))[-self.max_active_memory_recalls :]
        except Exception:
            result = None
        return self._as_list(result)[: self.max_active_memory_recalls]

    def _extract_vector(self, item: Any) -> Dict[str, float]:
        if isinstance(item, Mapping):
            for key in ("impulse", "affect_vector", "vector", "axes", "snapshot_vector"):
                maybe = item.get(key)
                if isinstance(maybe, Mapping):
                    return {axis: _f(maybe.get(axis, 0.0)) for axis in AXES}
            return {axis: _f(item.get(axis, 0.0)) for axis in AXES}
        for key in ("impulse", "affect_vector", "vector", "axes", "snapshot_vector"):
            maybe = getattr(item, key, None)
            if isinstance(maybe, Mapping):
                return {axis: _f(maybe.get(axis, 0.0)) for axis in AXES}
        return {axis: 0.0 for axis in AXES}

    def _build_recall_impulse(self, recalls: List[Any]) -> Dict[str, float]:
        if not recalls:
            return {axis: 0.0 for axis in AXES}
        agg = {axis: 0.0 for axis in AXES}
        useful = 0
        for item in recalls:
            vec = self._extract_vector(item)
            if _l1(vec) <= 0.0:
                continue
            useful += 1
            for axis in AXES:
                agg[axis] += _f(vec.get(axis, 0.0))
        if useful == 0:
            return {
                "curiosity": min(0.12, 0.015 * len(recalls)),
                "valence": 0.0,
                "arousal": 0.0,
                "dominance": 0.0,
                "stress": 0.0,
                "trust": 0.0,
                "stability": 0.0,
                "attachment": 0.0,
            }
        avg = {axis: agg[axis] / float(useful) for axis in AXES}
        return _scaled(avg, min(0.35, 0.08 + 0.02 * len(recalls)))

    def _build_internal_impulse(self, active_drive: str, hypothesis_count: int, decision: Mapping[str, Any]) -> Dict[str, float]:
        tpl = IMPULSE_TEMPLATES.get(active_drive, {"curiosity": 0.5})
        confidence = _clamp(decision.get("confidence", 0.5), 0.0, 1.0)
        relevance = _clamp(decision.get("relevance_score", decision.get("relevance", 0.5)), 0.0, 1.0)
        scale = (0.10 + 0.02 * min(6, hypothesis_count)) * (0.7 + 0.3 * confidence) * (0.75 + 0.25 * relevance)
        out = {axis: 0.0 for axis in AXES}
        for axis, weight in tpl.items():
            out[axis] = _clamp(_f(weight) * scale, -1.0, 1.0)
        return out

    def _enforce_recall_share(self, internal_impulse: Mapping[str, Any], recall_impulse: Mapping[str, Any]) -> Tuple[Dict[str, float], float]:
        ei = _l1(internal_impulse)
        er = _l1(recall_impulse)
        if ei <= 0.0 or er <= 0.0:
            return {axis: _f(recall_impulse.get(axis, 0.0)) for axis in AXES}, 0.0
        max_recall = (self.recall_energy_share_limit / max(1e-6, 1.0 - self.recall_energy_share_limit)) * ei
        if er > max_recall > 0.0:
            rec = _scaled(recall_impulse, max_recall / er)
        else:
            rec = {axis: _f(recall_impulse.get(axis, 0.0)) for axis in AXES}
        share = _l1(rec) / max(1e-6, _l1(rec) + ei)
        return rec, share

    def _apply_impulses(self, dt: float, internal_impulse: Mapping[str, Any], recall_impulse: Mapping[str, Any]) -> bool:
        core = self.affective_core
        if core is None:
            if callable(self.failure_logger):
                self.failure_logger(
                    "internal_affect_apply_failed",
                    {"reason": "affective_core_missing"},
                )
            return False
        try:
            if hasattr(core, "step"):
                # Imagined outcome is an event. Retention for this slice
                # already ran in update_affect; do not integrate dt again.
                core.step(
                    external_impulses=None,
                    recall_impulses={"vector": dict(recall_impulse), "intensity": 1.0, "source": "memory"},
                    internal_impulses={"vector": dict(internal_impulse), "intensity": 1.0, "source": "internal"},
                    time_elapsed=0.0,
                )
                return True
            if hasattr(core, "apply_impulse"):
                core.apply_impulse({"vector": dict(recall_impulse), "intensity": 1.0, "source": "memory"})
                core.apply_impulse({"vector": dict(internal_impulse), "intensity": 1.0, "source": "internal"})
                return True
            if callable(self.failure_logger):
                self.failure_logger(
                    "internal_affect_apply_failed",
                    {"reason": "interface_unsupported"},
                )
        except Exception as err:
            if callable(self.failure_logger):
                self.failure_logger(
                    "internal_affect_apply_failed",
                    {"reason": "exception", "error": str(err)},
                )
            return False
        return False

    def _read_affect_snapshot(self) -> Dict[str, Any]:
        if self.affective_core is None or not hasattr(self.affective_core, "snapshot"):
            return {"axes": {}}
        try:
            snap = self.affective_core.snapshot()
        except Exception:
            snap = {}
        if not isinstance(snap, Mapping):
            snap = {}
        axes = snap.get("axes", {})
        if not isinstance(axes, Mapping):
            axes = {}
        out = dict(snap)
        out["axes"] = {axis: _f(axes.get(axis, 0.0)) for axis in AXES}
        return out

    def _simulation_budget(self, recalls: List[Any]) -> int:
        # Budget follows recall-cap contract and is always >= 1.
        based_on_recalls = len(list(recalls or []))
        if based_on_recalls <= 0:
            based_on_recalls = 1
        return max(1, min(self.max_active_memory_recalls, based_on_recalls))

    def _generate_hypotheses(self, active_drive: str, recalls: List[Any]) -> List[Any]:
        hypotheses: List[Any] = []
        try:
            if self.cognitive_core and hasattr(self.cognitive_core, "generate_hypotheses"):
                hypotheses = self._as_list(
                    self.cognitive_core.generate_hypotheses(active_drive=active_drive, recalls=list(recalls))
                )
        except Exception:
            hypotheses = []
        return list(hypotheses or [])

    def _extract_action_name(self, hypothesis: Any, active_drive: str) -> str:
        if isinstance(hypothesis, str):
            return hypothesis
        if isinstance(hypothesis, Mapping):
            for key in ("action", "proposed_action", "candidate_action", "hypothesis", "h", "name"):
                value = hypothesis.get(key)
                if value is not None:
                    text = str(value).strip()
                    if text:
                        return text
        text = str(getattr(hypothesis, "action", "") or "").strip()
        if text:
            return text
        return f"{active_drive}:variant"

    def _read_neuromodulators(self, hypothetical_state: Mapping[str, Any]) -> Dict[str, float]:
        source = hypothetical_state.get("neuromodulators")
        if source is None:
            source = self.neuromodulator_state
        if isinstance(source, Mapping):
            return {
                "dopamine": max(0.0, _f(source.get("dopamine", 0.0))),
                "cortisol": max(0.0, _f(source.get("cortisol", 0.0))),
                "norepinephrine": max(0.0, _f(source.get("norepinephrine", 0.0))),
            }
        return {
            "dopamine": max(0.0, _f(getattr(source, "dopamine", 0.0))),
            "cortisol": max(0.0, _f(getattr(source, "cortisol", 0.0))),
            "norepinephrine": max(0.0, _f(getattr(source, "norepinephrine", 0.0))),
        }

    def _read_habit_strengths(self, action_ids: List[str]) -> Dict[str, float]:
        if not callable(self.habit_strength_provider):
            return {}
        try:
            out = self.habit_strength_provider(list(action_ids or []))
        except Exception:
            return {}
        if not isinstance(out, Mapping):
            return {}
        return {
            str(aid): max(0.0, _f(out.get(aid, 0.0)))
            for aid in list(action_ids or [])
        }

    def _select_via_bg_pipeline(self, hypothetical_state: Mapping[str, Any], pressure_vector: Mapping[str, Any]) -> str:
        if self.basal_ganglia is None or self.thalamic_gate is None:
            return ""

        pressures = {
            str(action_id): _f(value, 0.0)
            for action_id, value in dict(pressure_vector or {}).items()
        }
        if not pressures:
            return ""

        neuromodulators = self._read_neuromodulators(hypothetical_state)
        axes = dict(hypothetical_state.get("axes", {}) or {})
        if not axes:
            axes = dict(((hypothetical_state.get("affect_snapshot") or {}).get("axes", {}) or {}))
        aversive_signal = max(0.0, _f(axes.get("stress", 0.0)))

        habits = self._read_habit_strengths(list(pressures.keys()))
        try:
            gated = self.basal_ganglia.process(
                pressure_vector=pressures,
                dopamine_level=neuromodulators["dopamine"],
                cortisol_level=neuromodulators["cortisol"],
                norepinephrine_level=neuromodulators["norepinephrine"],
                habit_strengths=habits,
                aversive_signal=aversive_signal,
            )
            return str(
                self.thalamic_gate.select(
                    gated_scores=gated,
                    norepinephrine_level=neuromodulators["norepinephrine"],
                )
            )
        except Exception:
            return ""

    def _propose_action(self, hypothetical_state: Mapping[str, Any], hypothesis: Optional[Any] = None) -> str:
        core = self.cognitive_core
        if not core:
            return ""
        inferred = self._extract_action_name(hypothesis, str(hypothetical_state.get("active_drive", "state"))) if hypothesis is not None else ""

        # Primary path: compute hypothetical pressures, then pass through BG + thalamic gate.
        try:
            if hasattr(core, "compute_pressures"):
                recalls = self._as_list(hypothetical_state.get("recalls", []))
                patterns = self._as_list(hypothetical_state.get("cortical_patterns", []))
                pressure = hypothetical_state.get("intent_pressure")
                if not isinstance(pressure, Mapping):
                    drive = str(hypothetical_state.get("active_drive", "")).strip()
                    pressure = {drive: 1.0} if drive else None
                pressure_vector = core.compute_pressures(
                    recalls,
                    patterns,
                    intent_pressure=pressure,
                    affect_modifier=_clamp(hypothetical_state.get("affect_modifier", 1.0), 0.1, 2.0),
                    temporal_chains_bias=hypothetical_state.get("temporal_chains_bias"),
                    prediction_pressure=hypothetical_state.get("prediction_pressure"),
                )
                if isinstance(pressure_vector, Mapping):
                    pressure_map = {str(aid): _f(v, 0.0) for aid, v in dict(pressure_vector).items()}
                    if inferred:
                        pressure_map[inferred] = pressure_map.get(inferred, 0.0) + 0.25
                    selected = self._select_via_bg_pipeline(hypothetical_state, pressure_map)
                    if selected:
                        return selected
        except Exception:
            pass

        # Strictly hypothetical proposal path; never call selector on live state.
        try:
            if hasattr(core, "propose"):
                out = core.propose(hypothetical_state)
                if isinstance(out, str):
                    if self.basal_ganglia is not None and self.thalamic_gate is not None:
                        selected = self._select_via_bg_pipeline(hypothetical_state, {str(out): 1.0})
                        if selected:
                            return selected
                    return out
                if isinstance(out, Mapping):
                    return self._extract_action_name(out, str(hypothetical_state.get("active_drive", "state")))
        except Exception:
            pass

        try:
            if hasattr(core, "choose"):
                recalls = self._as_list(hypothetical_state.get("recalls", []))
                patterns = self._as_list(hypothetical_state.get("cortical_patterns", []))
                pressure = hypothetical_state.get("intent_pressure")
                if not isinstance(pressure, Mapping):
                    drive = str(hypothetical_state.get("active_drive", "")).strip()
                    pressure = {drive: 1.0} if drive else None
                out = core.choose(
                    recalls,
                    patterns,
                    intent_pressure=pressure,
                    affect_modifier=_clamp(hypothetical_state.get("affect_modifier", 1.0), 0.1, 2.0),
                )
                if isinstance(out, str):
                    selected = self._select_via_bg_pipeline(hypothetical_state, {str(out): 1.0})
                    if selected:
                        return selected
                    return out
                if isinstance(out, Mapping):
                    return self._extract_action_name(out, str(hypothetical_state.get("active_drive", "state")))
        except Exception:
            pass
        if inferred:
            return inferred
        return ""

    def _get_action_effect(self, proposed_action: str, active_drive: str) -> Dict[str, Any]:
        effect: Dict[str, Any] = {
            "axes": {},
            "drives": {},
            "active_drive_delta": -0.10,
        }
        core = self.cognitive_core
        if core is not None:
            try:
                if hasattr(core, "get_action_effect"):
                    incoming = core.get_action_effect(proposed_action)
                    if isinstance(incoming, Mapping):
                        effect.update(dict(incoming))
                elif hasattr(core, "get_action_metadata"):
                    meta = core.get_action_metadata(proposed_action)
                    if isinstance(meta, Mapping):
                        incoming = meta.get("predicted_effect", {})
                        if isinstance(incoming, Mapping):
                            effect.update(dict(incoming))
            except Exception:
                pass

        axes = {}
        for axis, delta in dict(effect.get("axes", {}) or {}).items():
            if axis in AXES:
                axes[axis] = _clamp(_f(delta), -1.0, 1.0)
        drives = {}
        for drive, delta in dict(effect.get("drives", {}) or {}).items():
            if drive in DRIVE_NAMES:
                drives[drive] = _f(delta)
        active_delta = _f(effect.get("active_drive_delta", -0.10), -0.10)
        if active_drive in DRIVE_NAMES and active_drive not in drives:
            drives[active_drive] = drives.get(active_drive, 0.0) + active_delta

        return {
            "axes": axes,
            "drives": drives,
            "active_drive_delta": active_delta,
        }

    def _simulate_action(self, hypothetical_state: Mapping[str, Any], proposed_action: str) -> Dict[str, Any]:
        state = dict(hypothetical_state)
        state["proposed_action"] = str(proposed_action)

        drives_before = dict(state.get("drives", {}) or {})
        if not drives_before:
            drives_before = {name: 0.0 for name in DRIVE_NAMES}
        drives = dict(drives_before)
        active_drive = str(state.get("active_drive", ""))

        effect = self._get_action_effect(proposed_action, active_drive)
        drive_delta = dict(effect.get("drives", {}) or {})
        for drive_name, delta in drive_delta.items():
            if drive_name in drives:
                drives[drive_name] = _clamp(_f(drives.get(drive_name, 0.0)) + _f(delta), 0.0, 1.0)

        if active_drive in DRIVE_NAMES and active_drive not in drive_delta:
            drives[active_drive] = _clamp(_f(drives.get(active_drive, 0.0)) + _f(effect.get("active_drive_delta", -0.10)), 0.0, 1.0)
        state["drives"] = drives
        state["drives_before"] = drives_before

        axes = dict(state.get("axes", {}) or {})
        if not axes:
            axes = dict(((state.get("affect_snapshot") or {}).get("axes", {}) or {}))
        axes_before = dict(axes)
        axis_delta = dict(effect.get("axes", {}) or {})
        for axis, delta in axis_delta.items():
            if axis in AXES:
                axes[axis] = _clamp(_f(axes.get(axis, 0.0)) + _f(delta), -1.0, 1.0)
        state["axes"] = axes
        state["axes_before"] = axes_before
        state["predicted_effect"] = {
            "axes": axis_delta,
            "drives": drive_delta,
            "active_drive_delta": _f(effect.get("active_drive_delta", -0.10)),
        }
        return state

    def _evaluate_hypothetical_state(
        self,
        hypothetical_state: Mapping[str, Any],
        proposed_action: str,
        hypothesis: Optional[Any],
        recalls: List[Any],
    ) -> Tuple[float, Dict[str, Any]]:
        profiles = getattr(self.decision_engine, "drive_utility_profiles", None)
        components = compute_drive_utility_components(
            hypothetical_state,
            drive_utility_profiles=profiles,
        )
        heuristic_score = _clamp(_f(components.get("utility", 0.0)), 0.0, 1.0)

        decision: Dict[str, Any] = {
            "relevance_score": _clamp(_f(components.get("relevance_hint", heuristic_score)), 0.0, 1.0),
            "confidence": _clamp(
                _f((hypothesis or {}).get("confidence", components.get("confidence_hint", 0.55)) if isinstance(hypothesis, Mapping) else components.get("confidence_hint", 0.55)),
                0.0,
                1.0,
            ),
            "utility": heuristic_score,
            "best_action": str(proposed_action),
            "drive_relief": _clamp(_f(components.get("drive_relief", 0.0)), 0.0, 1.0),
            "axes_score": _clamp(_f(components.get("axes_score", 0.0)), 0.0, 1.0),
            "effect_energy": _clamp(_f(components.get("effect_energy", 0.0)), 0.0, 1.0),
        }

        engine = self.decision_engine
        if engine is None:
            return heuristic_score, decision

        try:
            out: Any = None
            if hasattr(engine, "evaluate"):
                out = engine.evaluate(dict(hypothetical_state))
            elif hasattr(engine, "evaluate_internal"):
                try:
                    out = engine.evaluate_internal(hypothetical_state=dict(hypothetical_state))
                except TypeError:
                    out = engine.evaluate_internal(
                        active_drive=hypothetical_state.get("active_drive"),
                        hypotheses=[hypothesis] if hypothesis is not None else [],
                        recalls=list(recalls),
                        hypothetical_state=dict(hypothetical_state),
                    )
            elif callable(engine):
                engine_name = str(getattr(engine, "__name__", "") or "")
                if engine_name == "choose":
                    if callable(self.failure_logger):
                        self.failure_logger(
                            "decision_engine_choose_disallowed",
                            {"reason": "choose_cannot_be_evaluator"},
                        )
                    out = None
                else:
                    out = engine(dict(hypothetical_state))

            if isinstance(out, Mapping):
                decision.update(dict(out))
                utility_raw = decision.get("utility", decision.get("score", heuristic_score))
                utility_engine = _clamp(_f(utility_raw, heuristic_score), 0.0, 1.0)
                decision["utility"] = _clamp(0.65 * utility_engine + 0.35 * heuristic_score, 0.0, 1.0)
                decision["confidence"] = _clamp(_f(decision.get("confidence", 0.55), 0.55), 0.0, 1.0)
                decision["relevance_score"] = _clamp(
                    _f(decision.get("relevance_score", decision.get("relevance", decision["utility"])), decision["utility"]),
                    0.0,
                    1.0,
                )
                if "best_action" not in decision:
                    decision["best_action"] = str(proposed_action)
                return _clamp(_f(decision.get("utility", heuristic_score), heuristic_score), 0.0, 1.0), decision

            if isinstance(out, str):
                if callable(self.failure_logger):
                    self.failure_logger(
                        "decision_engine_returned_action_instead_of_utility",
                        {"action": str(out)},
                    )
                decision["best_action"] = str(proposed_action)
                decision["utility"] = heuristic_score
                decision["relevance_score"] = heuristic_score
                return heuristic_score, decision
        except TypeError:
            if callable(self.failure_logger):
                self.failure_logger(
                    "internal_decision_eval_failed",
                    {"reason": "signature_mismatch"},
                )
        except Exception as err:
            if callable(self.failure_logger):
                self.failure_logger(
                    "internal_decision_eval_failed",
                    {"reason": "exception", "error": str(err)},
                )

        return heuristic_score, decision

    def run_cycle(
        self,
        active_drive: str,
        now: float,
        dt: float = 1.0,
        live_drives: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        now_v = _f(now)
        self._prune_cycles(now_v)
        if len(self.cycle_timestamps) >= self.max_internal_cycles_per_window:
            self.last_result = {
                "triggered": False,
                "limit_reached": True,
                "active_drive": active_drive,
                "window_count": len(self.cycle_timestamps),
            }
            return dict(self.last_result)

        recalls = self._recall(active_drive)
        budget = self._simulation_budget(recalls)
        if budget <= 0:
            raise OrganismInvariantError("InternalSimulationLoop requires simulation_budget > 0")

        affect_snapshot = self._read_affect_snapshot()
        drives_seed = {name: 0.0 for name in DRIVE_NAMES}
        if isinstance(live_drives, Mapping):
            for name in DRIVE_NAMES:
                if name in live_drives:
                    drives_seed[name] = _clamp(_f(live_drives.get(name, 0.0)), 0.0, 1.0)
        if active_drive in drives_seed and drives_seed[active_drive] <= 0.0:
            # Conservative fallback when live drive snapshot is unavailable.
            drives_seed[active_drive] = _clamp(max(self.threshold, 0.35), 0.0, 1.0)
        current_state: Dict[str, Any] = {
            "active_drive": active_drive,
            "recalls": list(recalls),
            "cortical_patterns": [],
            "intent_pressure": {active_drive: 1.0},
            "affect_modifier": 1.0,
            "drives": drives_seed,
            "drives_source": "live_snapshot" if isinstance(live_drives, Mapping) else "seed_default",
            "axes": dict(affect_snapshot.get("axes", {}) or {}),
            "affect_snapshot": affect_snapshot,
            "timestamp": now_v,
            "dt": max(1e-6, _f(dt, 1.0)),
        }

        hypotheses = self._generate_hypotheses(active_drive, recalls)[:budget]
        generated_by_core = len(hypotheses)

        # If explicit hypotheses are unavailable, generate candidates directly from
        # cognitive_core on hypothetical-state copies.
        if not hypotheses:
            generated_actions: List[Dict[str, Any]] = []
            for i in range(budget):
                hypothetical_state = deepcopy(current_state)
                hypothetical_state["variant_index"] = i
                proposed_action = str(self._propose_action(hypothetical_state)).strip()
                if proposed_action:
                    generated_actions.append(
                        {
                            "action": proposed_action,
                            "confidence": 0.55,
                            "source": "selector",
                        }
                    )
            hypotheses = generated_actions

        fallback_used = False
        if not hypotheses:
            fallback_used = True
            hypotheses = [{"action": f"{active_drive}:fallback", "confidence": 0.35, "source": "fallback"}]

        variants: List[Dict[str, Any]] = []
        for i, hypothesis in enumerate(hypotheses[:budget]):
            hypothetical_state = deepcopy(current_state)
            hypothetical_state["variant_index"] = i
            proposed_action = str(self._propose_action(hypothetical_state, hypothesis=hypothesis)).strip()
            if not proposed_action:
                continue
            simulated_state = self._simulate_action(hypothetical_state, proposed_action)
            utility, decision = self._evaluate_hypothetical_state(simulated_state, proposed_action, hypothesis, recalls)
            variants.append(
                {
                    "index": i,
                    "proposed_action": proposed_action,
                    "utility": _clamp(_f(utility, 0.0), 0.0, 1.0),
                    "decision": dict(decision or {}),
                }
            )

        if not variants:
            variants = [
                {
                    "index": 0,
                    "proposed_action": f"{active_drive}:fallback",
                    "utility": 0.0,
                    "decision": {
                        "relevance_score": 0.0,
                        "confidence": 0.0,
                        "utility": 0.0,
                        "best_action": f"{active_drive}:fallback",
                    },
                }
            ]
            fallback_used = True

        best = max(
            variants,
            key=lambda item: (
                _f(item.get("utility", 0.0)),
                _f((item.get("decision", {}) or {}).get("confidence", 0.0)),
            ),
        )
        best_action = str(best.get("proposed_action", ""))
        decision = dict(best.get("decision", {}) or {})
        decision.setdefault("best_action", best_action)
        decision["confidence"] = _clamp(_f(decision.get("confidence", 0.0)), 0.0, 1.0)
        decision["relevance_score"] = _clamp(
            _f(decision.get("relevance_score", decision.get("relevance", decision["confidence"]))),
            0.0,
            1.0,
        )
        decision["utility"] = _clamp(_f(decision.get("utility", best.get("utility", 0.0))), 0.0, 1.0)

        internal_impulse = self._build_internal_impulse(active_drive, len(variants), decision)
        recall_impulse_raw = self._build_recall_impulse(recalls)
        recall_impulse, recall_share = self._enforce_recall_share(internal_impulse, recall_impulse_raw)
        applied = self._apply_impulses(dt, internal_impulse, recall_impulse)
        self.cycle_timestamps.append(now_v)

        self.last_result = {
            "triggered": True,
            "limit_reached": False,
            "active_drive": active_drive,
            "recall_count": len(recalls),
            "hypothesis_count": len(hypotheses),
            "generated_hypotheses": generated_by_core,
            "fallback_used": bool(fallback_used),
            # Output contract for simulation consumers.
            "best_action": best_action,
            "confidence": decision["confidence"],
            "evaluated_variants": len(variants),
            "decision": decision,
            "internal_impulse_energy": _l1(internal_impulse),
            "recall_impulse_energy": _l1(recall_impulse),
            "total_impulse_energy": _l1(internal_impulse) + _l1(recall_impulse),
            "recall_impulse_share": recall_share,
            "affect_applied": applied,
        }
        return dict(self.last_result)

class AutonomousOrganismAgent:
    def __init__(
        self,
        affective_core: Any,
        cognitive_core: Any,
        decision_engine: Any,
        memory_system: Any,
        drive_system: Optional[DriveSystem] = None,
        energy_system: Optional[EnergySystem] = None,
        internal_loop: Optional[InternalSimulationLoop] = None,
        speech_governor: Optional[SpeechGovernor] = None,
        hard_limits: Optional[OrganismHardLimits] = None,
        drive_weights: Optional[Mapping[str, float]] = None,
        internal_trigger_threshold: float = 0.35,
        speech_cooldown_seconds: float = 5.0,
        time_fn: Optional[Callable[[], float]] = None,
    ) -> None:
        self.affective_core = affective_core
        self.cognitive_core = cognitive_core
        self.decision_engine = decision_engine
        self.memory_system = memory_system
        self.time_fn = time_fn or time.time

        self.hard_limits = hard_limits or OrganismHardLimits()
        self.drive_system = drive_system or DriveSystem()
        self.energy_system = energy_system or EnergySystem()
        self.energy_system.floor_threshold = _clamp(self.hard_limits.energy_floor_threshold, 0.0, 1.0)

        self.internal_loop = internal_loop or InternalSimulationLoop(
            affective_core=self.affective_core,
            cognitive_core=self.cognitive_core,
            decision_engine=self.decision_engine,
            memory_system=self.memory_system,
            threshold=internal_trigger_threshold,
            drive_weights=drive_weights,
            max_internal_cycles_per_window=self.hard_limits.max_internal_cycles_per_window,
            window_seconds=self.hard_limits.internal_cycles_window_seconds,
            max_active_memory_recalls=self.hard_limits.max_active_memory_recalls,
            recall_energy_share_limit=0.4,
            failure_logger=self._record_failure,
        )
        if hasattr(self.internal_loop, "failure_logger"):
            self.internal_loop.failure_logger = self._record_failure
        self.speech_governor = speech_governor or SpeechGovernor(
            cooldown_seconds=speech_cooldown_seconds,
            max_speech_events_per_interval=self.hard_limits.max_speech_events_per_interval,
            speech_interval_seconds=self.hard_limits.speech_interval_seconds,
        )

        self.tick_history: List[Dict[str, Any]] = []
        # Inspectors read the latest tick. The count is every organism step,
        # including ticks that were dropped from the retained tail.
        self._completed_ticks = 0
        self.failure_log: List[Dict[str, Any]] = []
        self._deadlock_ticks = 0
        self._dt_min = 0.05
        self._dt_max = 1.0
        self._physiology_loads = dict(DEFAULT_PHYSIOLOGY_LOADS)
        self.agent_mode: str = "IDLE"
        self._last_regulation: Dict[str, Any] = {
            "regulation_active": False,
            "affect_overload": 0.0,
            "discharge_intensity": 0.0,
            "reduce_affect": 0.0,
            "reduce_overload": 0.0,
            "affect_applied": False,
        }

        self._affect_interface_ok = hasattr(self.affective_core, "snapshot") and (
            hasattr(self.affective_core, "step") or hasattr(self.affective_core, "apply_impulse")
        )
        if not self._affect_interface_ok:
            self._record_failure(
                "affect_mutation_outside_interface",
                {"reason": "invalid_affective_core_interface"},
            )

    def _record_failure(self, mode: str, details: Optional[Mapping[str, Any]] = None) -> None:
        self.failure_log.append(
            {
                "timestamp": self.time_fn(),
                "failure_mode": str(mode),
                "details": dict(details or {}),
            }
        )
        self._trim_failure_log()

    def _trim_failure_log(self) -> None:
        extra = len(self.failure_log) - FAILURE_LOG_RETAIN
        if extra > 0:
            del self.failure_log[:extra]

    def _sanitize_dt(self, dt: float) -> Tuple[float, float]:
        raw_dt = _f(dt, 0.0)
        if not math.isfinite(raw_dt):
            raw_dt = 0.0

        dt_v = raw_dt
        reason = ""
        if raw_dt <= 0.0:
            dt_v = self._dt_min
            reason = "non_positive"
        elif raw_dt < self._dt_min:
            dt_v = self._dt_min
            reason = "too_small"
        elif raw_dt > self._dt_max:
            dt_v = self._dt_max
            reason = "too_large"

        if reason:
            self._record_failure(
                "dt_anomaly",
                {
                    "reason": reason,
                    "input_dt": raw_dt,
                    "used_dt": dt_v,
                    "dt_min": self._dt_min,
                    "dt_max": self._dt_max,
                },
            )
        return dt_v, raw_dt

    def _build_physiology_profile(
        self,
        *,
        active_drive: Optional[str],
        internal_cycle_triggered: bool,
        speech_event: bool,
    ) -> Dict[str, Any]:
        low_energy = bool(
            self.energy_system.suppress_internal_cycles
            or self.energy_system.energy <= self.energy_system.low_threshold
        )

        if speech_event:
            mode = "speaking"
            base_load = _f(self._physiology_loads.get("speaking"), 0.24)
            rest_time = 0.0
        elif internal_cycle_triggered:
            mode = "internal_processing"
            base_load = _f(self._physiology_loads.get("internal_processing"), 0.34)
            rest_time = 0.0
        elif low_energy:
            mode = "low_energy"
            base_load = _f(self._physiology_loads.get("low_energy"), 0.08)
            rest_time = 1.0
        elif active_drive is not None:
            mode = "passive"
            base_load = _f(self._physiology_loads.get("passive"), 0.18)
            rest_time = 0.30
        else:
            mode = "idle"
            base_load = _f(self._physiology_loads.get("idle"), 0.06)
            rest_time = 1.0

        internal_component = 0.28 if internal_cycle_triggered else 0.0
        speech_component = 0.18 if speech_event else 0.0
        cognitive_load = _clamp(base_load + internal_component + speech_component, 0.0, 1.0)
        if not internal_cycle_triggered and not speech_event:
            cognitive_load = min(cognitive_load, 0.29)
        if mode in ("idle", "low_energy"):
            rest_time = max(1.0, rest_time)

        return {
            "mode": mode if mode in PHYSIOLOGY_MODES else "idle",
            "cognitive_load": cognitive_load,
            "rest_time": max(0.0, rest_time),
            "components": {
                "base": base_load,
                "internal": internal_component,
                "speech": speech_component,
            },
            "low_energy": low_energy,
        }

    def _read_affect(self) -> Dict[str, Any]:
        try:
            snap = self.affective_core.snapshot()
        except Exception:
            snap = {}
        if not isinstance(snap, Mapping):
            snap = {}
        axes = snap.get("axes", {})
        if not isinstance(axes, Mapping):
            axes = {}
        out = dict(snap)
        out["axes"] = dict(axes)
        out["state_norm"] = _f(snap.get("state_norm"), _l2(axes))
        out["norm_cap_current"] = max(1e-6, _f(snap.get("norm_cap_current"), 1.0))
        return out

    def _estimate_affect_overload(self, affect_snapshot: Mapping[str, Any]) -> float:
        norm = _f(affect_snapshot.get("state_norm"), 0.0)
        cap = max(1e-6, _f(affect_snapshot.get("norm_cap_current"), 1.0))
        ratio = norm / cap
        return _clamp((ratio - 0.80) / 0.20, 0.0, 1.0)

    def _estimate_uncertainty(self, affect_snapshot: Mapping[str, Any]) -> float:
        axes = dict(affect_snapshot.get("axes", {}) or {})
        stability = _clamp((_f(axes.get("stability", 0.0)) + 1.0) * 0.5, 0.0, 1.0)
        stress = _clamp(abs(_f(axes.get("stress", 0.0))), 0.0, 1.0)
        curiosity = _clamp((_f(axes.get("curiosity", 0.0)) + 1.0) * 0.5, 0.0, 1.0)
        return _clamp(0.5 * (1.0 - stability) + 0.3 * stress + 0.2 * curiosity, 0.0, 1.0)

    def _estimate_prediction_error(self, affect_snapshot: Mapping[str, Any], internal_result: Mapping[str, Any]) -> float:
        if isinstance(internal_result, Mapping) and "prediction_error" in internal_result:
            return _clamp(_f(internal_result.get("prediction_error", 0.0)), 0.0, 1.0)
        axes = dict(affect_snapshot.get("axes", {}) or {})
        stress = _clamp(abs(_f(axes.get("stress", 0.0))), 0.0, 1.0)
        valence_penalty = _clamp(-_f(axes.get("valence", 0.0)), 0.0, 1.0)
        return _clamp(0.65 * stress + 0.35 * valence_penalty, 0.0, 1.0)

    def _update_agent_mode(
        self,
        *,
        active_drive: Optional[str],
        drives: Mapping[str, Any],
        affect_snapshot: Mapping[str, Any],
        internal_result: Mapping[str, Any],
    ) -> Dict[str, float]:
        social_stimulus = _clamp(_f(drives.get("social_drive", 0.0)), 0.0, 1.0)
        goal_stimulus = _clamp(_f(drives.get("goal_tension", 0.0)), 0.0, 1.0)
        exploration_stimulus = _clamp(_f(drives.get("exploration", 0.0)), 0.0, 1.0)
        external_stimulation = max(social_stimulus, goal_stimulus, exploration_stimulus)

        prediction_error = self._estimate_prediction_error(affect_snapshot, internal_result)
        uncertainty = self._estimate_uncertainty(affect_snapshot)

        if (
            external_stimulation < 0.25
            and prediction_error >= 0.55
            and uncertainty >= 0.50
        ):
            self.agent_mode = "REFLECTION"
        elif active_drive is not None:
            self.agent_mode = "ACTIVE"
        else:
            self.agent_mode = "IDLE"

        return {
            "external_stimulation": external_stimulation,
            "prediction_error": prediction_error,
            "uncertainty": uncertainty,
        }

    def regulate_affect(self, dt: float, affect_snapshot: Mapping[str, Any]) -> Dict[str, Any]:
        overload = self._estimate_affect_overload(affect_snapshot)
        regulation = self.speech_governor.regulate_affect(overload)
        is_active = bool(_f(regulation.get("regulation_active", 0.0)) > 0.0)

        if not is_active:
            self._last_regulation = {
                "regulation_active": False,
                "affect_overload": overload,
                "discharge_intensity": 0.0,
                "reduce_affect": 0.0,
                "reduce_overload": 0.0,
                "affect_applied": False,
            }
            return dict(self._last_regulation)

        intensity = _clamp(_f(regulation.get("discharge_intensity", 0.0)), 0.0, 1.0)
        reduce_affect = _clamp(_f(regulation.get("reduce_affect", 0.0)), 0.0, 1.0)
        try:
            dt_v = float(dt)
        except (TypeError, ValueError):
            dt_v = 0.0
        if not math.isfinite(dt_v) or dt_v < 0.0:
            dt_v = 0.0

        # Acute negative feedback while the state norm is past capacity.
        # 0.45 is the existing discharge fraction: at reduce_affect=1 it
        # removes 45% of (axis - setpoint) per second. The sign is the
        # deviation, so both sides of the setpoint move toward it. This is
        # an impulse, not a second integration; update_affect owns time.
        axes = dict(affect_snapshot.get("axes", {}) or {})
        setpoints = dict(getattr(self.affective_core, "baseline_setpoint", {}) or {})
        pulse: Dict[str, float] = {}
        if dt_v > 0.0 and reduce_affect > 0.0:
            for axis, value in axes.items():
                deviation = _f(value, 0.0) - _f(setpoints.get(axis, 0.0), 0.0)
                if deviation == 0.0:
                    continue
                pulse[str(axis)] = -0.45 * reduce_affect * deviation * dt_v

        applied = False
        if pulse:
            payload = {
                "vector": pulse,
                "intensity": max(0.1, intensity),
                "source": "internal",
            }
            try:
                core = self.affective_core
                if hasattr(core, "apply_impulses"):
                    core.apply_impulses(internal_impulses=payload)
                    applied = True
                elif hasattr(core, "step"):
                    core.step(
                        external_impulses=None,
                        recall_impulses=None,
                        internal_impulses=payload,
                        time_elapsed=0.0,
                    )
                    applied = True
            except Exception as err:
                self._record_failure("affect_regulation_failed", {"reason": "exception", "error": str(err)})

        self._last_regulation = {
            "regulation_active": True,
            "affect_overload": overload,
            "discharge_intensity": intensity,
            "reduce_affect": reduce_affect,
            "reduce_overload": _clamp(_f(regulation.get("reduce_overload", 0.0)), 0.0, 1.0),
            "affect_applied": applied,
        }
        return dict(self._last_regulation)

    def update_affect(self, dt: float) -> None:
        """Integrate affect once for this organism slice.

        A cognitive commit of the same host interval leaves
        ``affect_time_credit_s`` on the core. Those seconds are already
        in the leak and the allostatic map; a body slice only spends the
        credit and does not run the map again. Without a credit, this
        call is the interval's single advance.
        """
        core = self.affective_core
        if not hasattr(core, "step"):
            return
        try:
            dt_v = max(0.0, _f(dt, 0.0))
            credit = float(getattr(core, "affect_time_credit_s", 0.0) or 0.0)
            if not math.isfinite(credit) or credit < 0.0:
                credit = 0.0
            if credit > 0.0:
                if credit + 1e-8 >= dt_v:
                    try:
                        core.affect_time_credit_s = max(0.0, credit - dt_v)
                    except Exception:
                        pass
                    return
                dt_v = dt_v - credit
                try:
                    core.affect_time_credit_s = 0.0
                except Exception:
                    pass
            if dt_v <= 1e-12:
                return
            core.step(
                external_impulses=None,
                recall_impulses=None,
                internal_impulses=None,
                time_elapsed=dt_v,
            )
        except Exception:
            pass

    def update_memory_decay(self, dt: float) -> None:
        if not self.memory_system:
            return
        for method in ("update_memory_decay", "decay_over_time", "decay", "update_decay"):
            if hasattr(self.memory_system, method):
                try:
                    getattr(self.memory_system, method)(max(0.0, _f(dt)))
                    return
                except Exception:
                    return

    def update_baseline(self, dt: float) -> None:
        if not self.cognitive_core:
            return
        for method in ("update_baseline", "tick_baseline", "update_internal_baseline"):
            if hasattr(self.cognitive_core, method):
                try:
                    getattr(self.cognitive_core, method)(max(0.0, _f(dt)))
                    return
                except Exception:
                    return

    def evaluate_drive_thresholds(self) -> Tuple[Optional[str], float]:
        return self.drive_system.select_highest_trigger(
            weights=self.internal_loop.drive_weights,
            default_threshold=self.internal_loop.threshold,
            per_drive_thresholds=self.hard_limits.drive_thresholds,
        )

    def _speech_relevance(self, active_drive: Optional[str], internal_result: Mapping[str, Any]) -> float:
        if self.decision_engine and hasattr(self.decision_engine, "speech_relevance"):
            try:
                return _clamp(
                    self.decision_engine.speech_relevance(
                        active_drive=active_drive,
                        internal_result=dict(internal_result),
                    ),
                    0.0,
                    1.0,
                )
            except Exception:
                pass
        if isinstance(internal_result, Mapping):
            top_level_relevance = internal_result.get("relevance_score", internal_result.get("confidence"))
            if top_level_relevance is not None:
                return _clamp(top_level_relevance, 0.0, 1.0)
        decision = internal_result.get("decision", {})
        if isinstance(decision, Mapping):
            return _clamp(
                decision.get("relevance_score", decision.get("relevance", 0.0)),
                0.0,
                1.0,
            )
        if active_drive:
            return _clamp(self.drive_system.drives.get(active_drive, 0.0), 0.0, 1.0)
        return 0.0

    def _speak(self, active_drive: Optional[str], internal_result: Mapping[str, Any]) -> str:
        if self.decision_engine:
            for method in ("generate_speech", "speak", "compose_speech"):
                if hasattr(self.decision_engine, method):
                    try:
                        out = getattr(self.decision_engine, method)(
                            active_drive=active_drive,
                            internal_result=dict(internal_result),
                        )
                        if isinstance(out, str):
                            return out
                    except Exception:
                        continue
        return f"[speech:{active_drive or 'none'}]"

    def _verify_invariants(self, tick: Mapping[str, Any]) -> None:
        if not self._affect_interface_ok:
            raise OrganismInvariantError("AffectiveCore interface invalid")
        for name, value in self.drive_system.drives.items():
            if value < 0.0 or value > 1.0:
                raise OrganismInvariantError(f"Drive out of bounds: {name}={value}")
        if "self_reflection" in self.drive_system.drives or "emotional_discharge" in self.drive_system.drives:
            raise OrganismInvariantError("Deprecated meta-drives are present in drive system")
        if self.agent_mode not in AGENT_MODES:
            raise OrganismInvariantError(f"Invalid agent_mode: {self.agent_mode}")
        if self.energy_system.energy < 0.0 or self.energy_system.energy > 1.0:
            raise OrganismInvariantError("Energy out of bounds")
        if self.energy_system.fatigue < 0.0 or self.energy_system.fatigue > 1.0:
            raise OrganismInvariantError("Fatigue out of bounds")
        if not tick.get("internal_cycle_triggered") and tick.get("active_drive") is not None:
            result = dict(getattr(self.internal_loop, "last_result", {}) or {})
            if not bool(result.get("limit_reached", False)):
                raise OrganismInvariantError("Active drive selected without internal cycle")
        if not tick.get("speech_event"):
            speech_component = _f((tick.get("load_components") or {}).get("speech", 0.0))
            if speech_component > 1e-8:
                raise OrganismInvariantError("Speech load applied without speech event")
        if not tick.get("internal_cycle_triggered") and not tick.get("speech_event"):
            if _f(tick.get("cognitive_load", 0.0)) >= 0.3:
                raise OrganismInvariantError("Idle/no-cycle cognitive load too high")
        if tick.get("speech_event"):
            events = list(self.speech_governor._speech_events)
            if len(events) >= 2 and events[-1] - events[-2] < self.speech_governor.cooldown_seconds:
                raise OrganismInvariantError("Speech cooldown violated")

    def organism_step(self, dt: float) -> Dict[str, Any]:
        dt_v, dt_input = self._sanitize_dt(dt)
        now = _f(self.time_fn())

        self.update_affect(dt_v)
        self.update_memory_decay(dt_v)
        self.update_baseline(dt_v)

        affect = self._read_affect()
        regulation = self.regulate_affect(dt_v, affect)
        affect = self._read_affect()
        drives = self.drive_system.update(dt_v, affect_snapshot=affect, energy_level=self.energy_system.energy)
        runaway = {
            k: v
            for k, v in self.drive_system.last_unclamped_values.items()
            if v < 0.0 or v > 1.0
        }
        if runaway:
            self._record_failure("drive_runaway_growth", {"unclamped": runaway})

        active_drive = None
        active_score = 0.0
        internal_result: Dict[str, Any] = {}
        triggered = False

        if not self.energy_system.suppress_internal_cycles:
            active_drive, active_score = self.evaluate_drive_thresholds()

        if active_drive is not None:
            internal_result = self.internal_loop.run_cycle(
                active_drive=active_drive,
                now=now,
                dt=dt_v,
                live_drives=drives,
            )
            triggered = bool(internal_result.get("triggered"))
            if triggered:
                self.drive_system.apply_discharge(active_drive, 0.18 * dt_v)
            elif internal_result.get("limit_reached"):
                self._record_failure(
                    "infinite_internal_cycle_loop",
                    {
                        "active_drive": active_drive,
                        "window_count": len(self.internal_loop.cycle_timestamps),
                },
            )

        mode_signals = self._update_agent_mode(
            active_drive=active_drive,
            drives=drives,
            affect_snapshot=affect,
            internal_result=internal_result,
        )

        comm = _clamp(self.drive_system.drives.get("social_drive", 0.0), 0.0, 1.0)
        relevance = self._speech_relevance(active_drive, internal_result)

        speech_event = False
        speech_output = ""
        allowed, reason = self.speech_governor.evaluate_permission(
            now=now,
            communication_drive=comm,
            relevance_score=relevance,
        )
        if allowed:
            speech_event = True
            speech_output = self._speak(active_drive, internal_result)
            self.speech_governor.register_speech(now)
            self.drive_system.apply_discharge("social_drive", 0.22 * dt_v)
        elif (
            comm > self.speech_governor.communication_threshold
            and relevance > self.speech_governor.relevance_minimum
            and reason in ("cooldown", "interval_limit")
        ):
            self._record_failure(
                "speech_spam",
                {
                    "reason": reason,
                    "communication_drive": comm,
                    "relevance_score": relevance,
                },
            )

        physiology = self._build_physiology_profile(
            active_drive=active_drive,
            internal_cycle_triggered=triggered,
            speech_event=speech_event,
        )
        energy_update = self.energy_system.update(
            dt_v,
            cognitive_load=_f(physiology.get("cognitive_load", 0.0)),
            rest_time=_f(physiology.get("rest_time", 0.0)),
        )

        if physiology.get("mode") in ("idle", "low_energy") and _f(energy_update.get("fatigue_delta", 0.0)) > 1e-8:
            self._record_failure(
                "idle_fatigue_non_recovering",
                {
                    "mode": physiology.get("mode"),
                    "fatigue_delta": _f(energy_update.get("fatigue_delta", 0.0)),
                    "cognitive_load": _f(physiology.get("cognitive_load", 0.0)),
                    "rest_time": _f(physiology.get("rest_time", 0.0)),
                },
            )

        if self.energy_system.energy <= self.energy_system.floor_threshold and self.energy_system.suppress_internal_cycles:
            self._deadlock_ticks += 1
            if self._deadlock_ticks >= 8:
                self._record_failure(
                    "energy_deadlock",
                    {
                        "deadlock_ticks": self._deadlock_ticks,
                        "energy": self.energy_system.energy,
                    },
                )
        else:
            self._deadlock_ticks = 0

        drives_snapshot = self.drive_system.snapshot()

        tick = {
            "timestamp": now,
            "dt": dt_v,
            "dt_input": dt_input,
            "dt_clamped": abs(dt_input - dt_v) > 1e-9,
            "active_drive": active_drive,
            "active_drive_score": active_score,
            "energy_level": self.energy_system.energy,
            "speech_event": speech_event,
            "speech_output": speech_output,
            "speech_reason": reason,
            "internal_cycle_triggered": triggered,
            "agent_mode": self.agent_mode,
            "mode_signals": dict(mode_signals),
            "regulation": dict(regulation),
            "physiology_mode": str(physiology.get("mode", "idle")),
            "cognitive_load": _f(physiology.get("cognitive_load", 0.0)),
            "rest_time": _f(physiology.get("rest_time", 0.0)),
            "load_components": dict(physiology.get("components", {}) or {}),
            "recall_impulse_share": _f(internal_result.get("recall_impulse_share", 0.0)),
            "drives": drives_snapshot,
            "energy_update": dict(energy_update),
            "energy_snapshot": self.energy_system.snapshot(),
        }
        self._completed_ticks = int(getattr(self, "_completed_ticks", 0)) + 1
        self.tick_history.append(tick)
        extra = len(self.tick_history) - TICK_HISTORY_RETAIN
        if extra > 0:
            del self.tick_history[:extra]

        try:
            self._verify_invariants(tick)
        except OrganismInvariantError as err:
            self._record_failure("invariant_violation", {"error": str(err)})
            raise

        return tick

    def run_for_steps(self, steps: int, dt: float = 1.0) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for _ in range(max(0, int(steps))):
            out.append(self.organism_step(dt))
        return out

    def snapshot(self) -> Dict[str, Any]:
        return {
            "drives": self.drive_system.snapshot(),
            "energy": self.energy_system.snapshot(),
            "agent_mode": self.agent_mode,
            "regulation": dict(self._last_regulation),
            "tick_count": max(int(getattr(self, "_completed_ticks", 0)), len(self.tick_history)),
            "failures": list(self.failure_log),
            "speech": self.speech_governor.snapshot(),
        }


class LifeLoopController:
    def __init__(
        self,
        organism: AutonomousOrganismAgent,
        min_interval_seconds: float = 0.05,
        time_fn: Optional[Callable[[], float]] = None,
        sleep_fn: Optional[Callable[[float], None]] = None,
    ) -> None:
        self.organism = organism
        self.time_fn = time_fn or time.time
        self.sleep_fn = sleep_fn or time.sleep
        self.min_interval_seconds = max(1e-6, _f(min_interval_seconds, 0.05))
        now = _f(self.time_fn())
        self.t_current = now
        self.t_last_tick = now
        self.dt = self.min_interval_seconds
        self.alive = True
        self.tick_count = 0

    def tick(self, now: Optional[float] = None) -> Dict[str, Any]:
        current = _f(self.time_fn() if now is None else now)
        dt = current - self.t_last_tick
        if dt <= 0.0:
            dt = self.min_interval_seconds
        self.t_current = current
        self.dt = dt
        self.t_last_tick = current
        self.tick_count += 1
        return self.organism.organism_step(dt)

    def run(self, max_ticks: Optional[int] = None, max_duration_seconds: Optional[float] = None) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        start = _f(self.time_fn())
        tick_limit = None if max_ticks is None else max(0, int(max_ticks))
        duration_limit = None if max_duration_seconds is None else max(0.0, _f(max_duration_seconds))

        self.alive = True
        while self.alive:
            loop_start = _f(self.time_fn())
            out.append(self.tick(now=loop_start))

            if tick_limit is not None and len(out) >= tick_limit:
                break
            if duration_limit is not None and _f(self.time_fn()) - start >= duration_limit:
                break

            elapsed = _f(self.time_fn()) - loop_start
            sleep_for = max(0.0, self.min_interval_seconds - elapsed)
            if sleep_for > 0.0:
                self.sleep_fn(sleep_for)

        return out

    def stop(self) -> None:
        self.alive = False


__all__ = [
    "AGENT_MODES",
    "AutonomousOrganismAgent",
    "DRIVE_NAMES",
    "DriveRule",
    "DriveSystem",
    "EnergySystem",
    "InternalSimulationLoop",
    "LifeLoopController",
    "OrganismHardLimits",
    "OrganismInvariantError",
    "SpeechGovernor",
]
