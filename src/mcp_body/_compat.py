"""Core-import helpers for the platform body layer.

The body package lives in ``src/`` next to the NOWA core, but tests and hosts
may launch from the repository root or from a ``Demo/`` sub-project. These
helpers put the core ``src/`` directory on ``sys.path`` and fall back to
compatible stand-ins when a core module cannot be imported, so the body never
hard-fails on core availability.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path as _FsPath
from typing import Any, Dict, List, Optional, Sequence, Tuple, Type

# Spec §6.6 — used only when the canonical AffectiveSpace cannot be imported.
FALLBACK_OUTCOME_VECTORS: Dict[str, Dict[str, float]] = {
    "accepted": {"valence": 0.4, "stress": -0.1, "trust": 0.2, "arousal": 0.1},
    "success": {"valence": 0.4, "stress": -0.1, "trust": 0.2, "arousal": 0.1},
    "ok": {"valence": 0.4, "stress": -0.1, "trust": 0.2, "arousal": 0.1},
    "rejected": {"valence": -0.4, "stress": 0.4, "trust": -0.2, "arousal": 0.3},
    "failed": {"valence": -0.4, "stress": 0.4, "trust": -0.2, "arousal": 0.3},
    "error": {"valence": -0.4, "stress": 0.4, "trust": -0.2, "arousal": 0.3},
    "timeout": {"valence": -0.1, "stress": 0.2, "trust": -0.1, "arousal": 0.2, "curiosity": 0.2},
    "unknown": {"valence": -0.1, "stress": 0.2, "trust": -0.1, "arousal": 0.2, "curiosity": 0.2},
}


def ensure_core_src_on_path() -> None:
    """Make the repository-level NOWA core modules importable when available."""
    here = _FsPath(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "src" / "agent.py"
        if candidate.exists():
            core_src = str(parent / "src")
            if core_src not in sys.path:
                sys.path.insert(0, core_src)
            return


def safe_float(value: Any, default: float = 0.0) -> float:
    """Convert to float, mapping NaN/inf/garbage onto ``default``."""
    try:
        result = float(value)
    except (TypeError, ValueError):
        return float(default)
    if math.isnan(result) or math.isinf(result):
        return float(default)
    return result


def is_number(value: Any) -> bool:
    """True for real numbers only — bool is not a numeric leaf here."""
    if isinstance(value, bool):
        return False
    if not isinstance(value, (int, float)):
        return False
    return not (math.isnan(float(value)) or math.isinf(float(value)))


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


class _FallbackEventType:
    """EventType-compatible stand-in used when NOWA core is unavailable."""

    def __init__(self, value: str) -> None:
        self.value = value

    def __eq__(self, other: object) -> bool:
        return self.value == getattr(other, "value", other)

    def __hash__(self) -> int:
        return hash(self.value)

    def __repr__(self) -> str:
        return f"EventType.{self.value.upper()}"


class _FallbackEventTypes:
    CONTEXT = _FallbackEventType("context")
    ACTION = _FallbackEventType("action")
    CONSEQUENCE = _FallbackEventType("consequence")
    REALIZATION = _FallbackEventType("realization")


class _FallbackEvent:
    """Event-compatible structure for tests/agents without NOWA core."""

    def __init__(
        self,
        name: str,
        event_type: Any = _FallbackEventTypes.CONTEXT,
        magnitude: float = 1.0,
    ) -> None:
        self.name = name
        self.event_type = event_type
        self.magnitude = magnitude

    def __repr__(self) -> str:
        type_value = getattr(self.event_type, "value", self.event_type)
        return f"{self.name}({type_value}@{self.magnitude})"

    def __str__(self) -> str:
        return str(self.name)

    def __hash__(self) -> int:
        type_value = getattr(self.event_type, "value", self.event_type)
        return hash((self.name, type_value, self.magnitude))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, _FallbackEvent):
            return False
        return self.name == other.name and self.event_type == other.event_type


class _FallbackPath:
    """Path-compatible immutable sequence used when NOWA core is unavailable."""

    def __init__(self, events: Optional[Sequence[Any]] = None) -> None:
        self.events = tuple(events) if events else ()

    def add_event(self, event: Any) -> "_FallbackPath":
        return _FallbackPath(list(self.events) + [event])

    def signature(self) -> Tuple[str, ...]:
        return tuple(getattr(event, "name", str(event)) for event in self.events)

    def matches(self, context_events: List[str]) -> bool:
        names = [getattr(event, "name", str(event)) for event in self.events]
        return all(token in names for token in context_events)

    def __repr__(self) -> str:
        return f"Path({len(self.events)} events)"

    def __hash__(self) -> int:
        return hash(self.signature())

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, _FallbackPath):
            return False
        return self.signature() == other.signature()


def load_experience_types() -> Tuple[Type[Any], Type[Any], Any]:
    """Return ``(Path, Event, EventType)``, falling back if core is missing."""
    ensure_core_src_on_path()
    try:
        from experience import Event, EventType, Path
        return Path, Event, EventType
    except Exception:
        return _FallbackPath, _FallbackEvent, _FallbackEventTypes


def load_affective_types() -> Tuple[Optional[Any], Optional[Any]]:
    """Return ``(AffectiveSpace, EmotionalImpulse)`` or ``(None, None)``.

    The body must keep working when the core affective module cannot be
    imported (partially migrated checkout, syntax error mid-refactor); callers
    then fall back to plain axis-vector dicts, which ``AffectiveSpace.step``
    also accepts once the core is healthy again.
    """
    ensure_core_src_on_path()
    try:
        from affective_space import AffectiveSpace, EmotionalImpulse
        return AffectiveSpace, EmotionalImpulse
    except Exception:
        return None, None


def normalize_status(status: Any) -> str:
    """Normalize an MCP status envelope token to a lowercase key."""
    text = str(status if status is not None else "unknown").strip().lower()
    return text or "unknown"


def outcome_impulse(status: Any, magnitude: float = 1.0) -> Any:
    """Canonical status → impulse mapping (spec §6.6).

    Returns an ``EmotionalImpulse`` when the core is importable, otherwise a
    plain axis-vector dict scaled by ``magnitude``.
    """
    key = normalize_status(status)
    gain = clamp(magnitude, 0.0, 1.0)
    affective_space_cls, _impulse_cls = load_affective_types()
    if affective_space_cls is not None:
        try:
            return affective_space_cls.outcome_impulse(key, gain)
        except Exception:
            pass
    vector = FALLBACK_OUTCOME_VECTORS.get(key) or FALLBACK_OUTCOME_VECTORS["unknown"]
    return {axis: clamp(value * gain, -1.0, 1.0) for axis, value in vector.items()}


def impulse_to_vector(impulse: Any) -> Dict[str, float]:
    """Best-effort axis vector from an impulse object or dict."""
    if impulse is None:
        return {}
    if isinstance(impulse, dict):
        if "vector" in impulse:
            raw = dict(impulse.get("vector") or {})
            gain = clamp(impulse.get("intensity", 1.0), 0.0, 1.0)
            return {k: clamp(safe_float(v) * gain, -1.0, 1.0) for k, v in raw.items()}
        return {k: clamp(safe_float(v), -1.0, 1.0) for k, v in impulse.items()}
    to_core = getattr(impulse, "to_core_vector", None)
    if callable(to_core):
        try:
            return dict(to_core())
        except Exception:
            return {}
    vector = getattr(impulse, "vector", None)
    if isinstance(vector, dict):
        gain = clamp(getattr(impulse, "intensity", 1.0), 0.0, 1.0)
        return {k: clamp(safe_float(v) * gain, -1.0, 1.0) for k, v in vector.items()}
    return {}


def apply_impulses(affective_space: Any, impulses: Any, source: str = "external") -> bool:
    """Push impulses into A(t) with ``time_elapsed=0``. Never raises. Returns success."""
    if affective_space is None or not impulses:
        return False
    step_fn = getattr(affective_space, "step", None)
    if not callable(step_fn):
        return False
    payload = impulses if isinstance(impulses, (list, tuple)) else [impulses]
    kwarg = {
        "external": "external_impulses",
        "memory": "recall_impulses",
        "internal": "internal_impulses",
    }.get(str(source).lower(), "external_impulses")
    try:
        step_fn(**{kwarg: list(payload), "time_elapsed": 0.0})
        return True
    except TypeError:
        pass
    except Exception:
        return False
    merged: Dict[str, float] = {}
    for item in payload:
        for axis, value in impulse_to_vector(item).items():
            merged[axis] = clamp(merged.get(axis, 0.0) + safe_float(value), -1.0, 1.0)
    if not merged:
        return False
    try:
        step_fn(inputs=merged, time_elapsed=0.0)
        return True
    except TypeError:
        try:
            step_fn(inputs=merged)
            return True
        except Exception:
            return False
    except Exception:
        return False
