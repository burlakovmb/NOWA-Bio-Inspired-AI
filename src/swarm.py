"""
Swarm environment for package E v2.1.

The environment is a physical 3D space with local social signaling and
autonomous sleep/wake dynamics for agents.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import math
import random
import warnings
from typing import Any, Callable, Dict, List, Mapping, MutableMapping, Optional, Sequence, Set, Tuple

from ecology import EcologyLayer
from fitness import FitnessEvaluator, FitnessVector
from mortality import BASE_LIFESPAN_STEPS
from reproduction import (
    MIN_COMPATIBILITY_THRESHOLD,
    REPRODUCTION_ENERGY_COST,
    compute_compatibility,
)


SWARM_VERSION = "2.2"
_LOG = logging.getLogger(__name__)
MAX_POPULATION_SIZE = 256
MIN_POPULATION_SIZE = 2
MIN_AGENT_DISTANCE = 0.1
SIGNAL_MIN_STRENGTH = 0.01
MAX_SOCIAL_SIGNAL_GAIN = 0.5
SLEEP_HYSTERESIS_FACTOR = 0.7
SLEEPING_SIGNAL_FACTOR = 0.3
WAKE_SIGNAL_THRESHOLD = 0.6
SOCIAL_SIGNAL_AXES = ["valence", "arousal", "stress", "curiosity"]


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        casted = float(value)
    except (TypeError, ValueError):
        return float(fallback)
    if math.isnan(casted) or math.isinf(casted):
        return float(fallback)
    return casted


@dataclass(frozen=True)
class Position3D:
    x: float
    y: float
    z: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "x", float(self.x))
        object.__setattr__(self, "y", float(self.y))
        object.__setattr__(self, "z", float(self.z))

    def distance_to(self, other: "Position3D") -> float:
        return math.sqrt(
            (self.x - other.x) ** 2
            + (self.y - other.y) ** 2
            + (self.z - other.z) ** 2
        )

    def to_tuple(self) -> Tuple[float, float, float]:
        return (self.x, self.y, self.z)

    @classmethod
    def random(cls, bounds: "SpaceBounds", rng: random.Random) -> "Position3D":
        return cls(
            x=rng.uniform(bounds.x_min, bounds.x_max),
            y=rng.uniform(bounds.y_min, bounds.y_max),
            z=rng.uniform(bounds.z_min, bounds.z_max),
        )

    @classmethod
    def origin(cls) -> "Position3D":
        return cls(0.0, 0.0, 0.0)


@dataclass(frozen=True)
class SpaceBounds:
    """Bounds of a 3D space."""

    x_min: float = 0.0
    x_max: float = 100.0
    y_min: float = 0.0
    y_max: float = 100.0
    z_min: float = 0.0
    z_max: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "x_min", float(self.x_min))
        object.__setattr__(self, "x_max", float(self.x_max))
        object.__setattr__(self, "y_min", float(self.y_min))
        object.__setattr__(self, "y_max", float(self.y_max))
        object.__setattr__(self, "z_min", float(self.z_min))
        object.__setattr__(self, "z_max", float(self.z_max))

        if self.x_min > self.x_max:
            raise ValueError("x_min must be <= x_max")
        if self.y_min > self.y_max:
            raise ValueError("y_min must be <= y_max")
        if self.z_min > self.z_max:
            raise ValueError("z_min must be <= z_max")

    def is_2d(self) -> bool:
        return self.z_min == self.z_max

    def contains(self, pos: Position3D) -> bool:
        return (
            self.x_min <= pos.x <= self.x_max
            and self.y_min <= pos.y <= self.y_max
            and self.z_min <= pos.z <= self.z_max
        )

    def clamp(self, pos: Position3D) -> Position3D:
        return Position3D(
            x=_clamp(pos.x, self.x_min, self.x_max),
            y=_clamp(pos.y, self.y_min, self.y_max),
            z=_clamp(pos.z, self.z_min, self.z_max),
        )

    def volume(self) -> float:
        dx = max(0.0, self.x_max - self.x_min)
        dy = max(0.0, self.y_max - self.y_min)
        dz = max(0.0, self.z_max - self.z_min)
        if self.is_2d():
            return dx * dy
        return dx * dy * dz


@dataclass(frozen=True)
class SocialSignal:
    source_agent_id: str
    valence: float
    arousal: float
    stress: float
    curiosity: float
    signal_strength: float
    source_is_sleeping: bool
    distance: float
    step: int


def _should_sleep(agent: Any, config: "SwarmConfig") -> bool:
    wakefulness = getattr(getattr(agent, "wakefulness", None), "wakefulness", None)
    if wakefulness is None:
        return False
    return _safe_float(wakefulness, 0.0) >= _safe_float(config.sleep_threshold, 0.7)


def _check_wake_signal(
    incoming_signals: List[SocialSignal],
    threshold: float = WAKE_SIGNAL_THRESHOLD,
) -> bool:
    total_stress = sum(
        _safe_float(signal.stress, 0.0) * _safe_float(signal.signal_strength, 0.0)
        for signal in incoming_signals
    )
    return total_stress >= _safe_float(threshold, WAKE_SIGNAL_THRESHOLD)


@dataclass
class AgentSlot:
    agent: Any
    position: Position3D
    perception_radius: float
    is_sleeping: bool = False
    sleep_started_step: int = 0


@dataclass(frozen=True)
class SwarmState:
    step: int
    agent_count: int
    sleeping_count: int
    active_count: int
    diversity: float
    mean_wakefulness: float
    social_signals_sent: int
    bounds: SpaceBounds
    resource_level: float = 0.0
    resource_share: float = 1.0
    births_this_step: int = 0
    deaths_this_step: int = 0
    total_births: int = 0
    total_deaths: int = 0


@dataclass
class SwarmConfig:
    bounds: SpaceBounds = field(default_factory=SpaceBounds)

    # Signal physics
    signal_decay_factor: float = 0.01
    base_perception_radius: float = 20.0
    social_signal_gain: float = 0.05

    # Sleep
    sleep_threshold: float = 0.7
    wake_signal_threshold: float = 0.6

    # Context and reward
    context_events_fn: Optional[Callable[..., Sequence[str]]] = None
    reward_fn: Optional[Callable[..., float]] = None

    # Ecology
    total_resources: float = 1000.0
    resource_regen_rate: float = 0.1
    resource_per_agent_base: float = 10.0

    # Reproduction/evolution
    mutation_rate: float = 0.05
    sigma_scale: float = 1.0
    crossover_mode: str = "arithmetic"
    epigenome_noise: float = 0.1
    base_lifespan_steps: int = BASE_LIFESPAN_STEPS

    # Population
    initial_population_size: int = 20

    # General
    max_steps_per_generation: int = 200


class SwarmEnvironment:
    def __init__(
        self,
        config: SwarmConfig,
        fitness_evaluator: FitnessEvaluator,
        rng: Optional[random.Random] = None,
        factory: Optional[Any] = None,
    ):
        self.config = config
        self.fitness_evaluator = fitness_evaluator
        self.factory = factory
        self.ecology = EcologyLayer(
            total_resources=_safe_float(getattr(config, "total_resources", 1000.0), 1000.0),
            resource_regen_rate=_safe_float(getattr(config, "resource_regen_rate", 0.1), 0.1),
            resource_per_agent_base=_safe_float(getattr(config, "resource_per_agent_base", 10.0), 10.0),
            current_resources=_safe_float(getattr(config, "total_resources", 1000.0), 1000.0),
        )
        self.global_step: int = 0
        self._slots: Dict[str, AgentSlot] = {}
        self._rng = rng if rng is not None else random.Random()
        self._last_social_signals_sent: int = 0
        self._last_resource_share: float = 1.0
        self.births_this_step: int = 0
        self.deaths_this_step: int = 0
        self.total_births: int = 0
        self.total_deaths: int = 0

    def _agent_id(self, agent: Any) -> str:
        candidate = getattr(agent, "agent_id", None)
        if candidate is None:
            return f"agent_{id(agent)}"
        return str(candidate)

    def _get_agent_component(self, agent: Any, name: str) -> Any:
        """
        Return explicitly attached agent component.

        Using __dict__ avoids false positives with MagicMock dynamic attributes.
        """
        raw = getattr(agent, "__dict__", None)
        if isinstance(raw, dict) and name in raw:
            return raw.get(name)
        return None

    def _is_colliding(
        self,
        position: Position3D,
        ignore_agent_id: Optional[str] = None,
    ) -> bool:
        for other_id, other_slot in self._slots.items():
            if ignore_agent_id is not None and other_id == ignore_agent_id:
                continue
            if position.distance_to(other_slot.position) < MIN_AGENT_DISTANCE:
                return True
        return False

    def _find_free_position(self, preferred: Position3D) -> Position3D:
        bounds = self.config.bounds
        candidate = bounds.clamp(preferred)
        if not self._is_colliding(candidate):
            return candidate

        for attempt in range(1, 512):
            radius = MIN_AGENT_DISTANCE * (1.0 + 0.35 * float(attempt))
            if bounds.is_2d():
                angle = (2.0 * math.pi * float(attempt % 32) / 32.0) + self._rng.uniform(-0.05, 0.05)
                shifted = Position3D(
                    candidate.x + math.cos(angle) * radius,
                    candidate.y + math.sin(angle) * radius,
                    bounds.z_min,
                )
            else:
                theta = self._rng.uniform(0.0, 2.0 * math.pi)
                phi = self._rng.uniform(0.0, math.pi)
                shifted = Position3D(
                    candidate.x + radius * math.sin(phi) * math.cos(theta),
                    candidate.y + radius * math.sin(phi) * math.sin(theta),
                    candidate.z + radius * math.cos(phi),
                )
            shifted = bounds.clamp(shifted)
            if not self._is_colliding(shifted):
                return shifted

        for _ in range(4096):
            random_candidate = Position3D.random(bounds, self._rng)
            if not self._is_colliding(random_candidate):
                return random_candidate

        raise RuntimeError("Unable to place agent without collisions")

    def _get_perception_radius(self, agent: Any) -> float:
        factor = 1.0
        genome = getattr(agent, "genome", None)
        genes = getattr(genome, "genes", None)
        if isinstance(genes, Mapping):
            factor = _safe_float(genes.get("dr_perception_radius_factor"), factor)
        elif hasattr(agent, "perception_radius_factor"):
            factor = _safe_float(getattr(agent, "perception_radius_factor"), factor)
        radius = _safe_float(self.config.base_perception_radius, 20.0) * max(0.0, factor)
        return max(0.0, radius)

    def _get_wakefulness_value(self, agent: Any) -> float:
        wakefulness = getattr(getattr(agent, "wakefulness", None), "wakefulness", None)
        return _safe_float(wakefulness, 0.0)

    def _get_affective_axes(self, agent: Any) -> Dict[str, float]:
        raw = getattr(getattr(agent, "affective_space", None), "axes", {}) or {}
        if not isinstance(raw, Mapping):
            return {axis: 0.0 for axis in SOCIAL_SIGNAL_AXES}
        return {
            "valence": _clamp(_safe_float(raw.get("valence"), 0.0), -1.0, 1.0),
            "arousal": _clamp(_safe_float(raw.get("arousal"), 0.0), 0.0, 1.0),
            "stress": _clamp(_safe_float(raw.get("stress"), 0.0), 0.0, 1.0),
            "curiosity": _clamp(_safe_float(raw.get("curiosity"), 0.0), 0.0, 1.0),
        }

    def _resolve_context_events(
        self,
        agent_id: str,
        agent: Any,
        context_override: Optional[Dict[str, List[str]]],
        incoming_signals: Optional[Sequence[SocialSignal]] = None,
    ) -> List[str]:
        if incoming_signals is None:
            incoming_signals = []

        if context_override and agent_id in context_override:
            values = context_override.get(agent_id) or []
            return [str(item) for item in values]

        fn = self.config.context_events_fn
        if not callable(fn):
            return self._default_context_events(agent_id, agent, incoming_signals)

        attempts: Tuple[Tuple[Any, ...], ...] = (
            (agent, incoming_signals, self, self.global_step),
            (agent, incoming_signals, self),
            (agent, incoming_signals),
            (agent, self),
            (agent,),
            (agent_id,),
            (),
        )
        for args in attempts:
            try:
                values = fn(*args)
                if values is None:
                    return self._default_context_events(agent_id, agent, incoming_signals)
                if isinstance(values, str):
                    return [values]
                return [str(item) for item in values]
            except TypeError:
                continue
            except Exception:
                return self._default_context_events(agent_id, agent, incoming_signals)
        return self._default_context_events(agent_id, agent, incoming_signals)

    def _default_context_events(
        self,
        agent_id: str,
        agent: Any,
        incoming_signals: Sequence[SocialSignal],
    ) -> List[str]:
        events: List[str] = []

        slot = self._slots.get(str(agent_id))
        if slot is not None and slot.is_sleeping:
            events.append("agent_sleeping")
        else:
            events.append("agent_active")

        wakefulness = self._get_wakefulness_value(agent)
        sleep_threshold = _safe_float(self.config.sleep_threshold, 0.7)
        wake_threshold_low = sleep_threshold * SLEEP_HYSTERESIS_FACTOR

        if wakefulness >= sleep_threshold:
            events.append("wakefulness_high")
        elif wakefulness < wake_threshold_low:
            events.append("wakefulness_low")
        else:
            events.append("wakefulness_mid")

        if incoming_signals:
            events.append("social_signal_present")
            if any(signal.source_is_sleeping for signal in incoming_signals):
                events.append("social_sleeping_neighbor")

            total_stress = sum(
                _safe_float(signal.stress, 0.0) * _safe_float(signal.signal_strength, 0.0)
                for signal in incoming_signals
            )
            if total_stress >= _safe_float(self.config.wake_signal_threshold, WAKE_SIGNAL_THRESHOLD):
                events.append("social_stress_high")

        return events

    def _resolve_reward(
        self,
        agent: Any,
        context_events: Sequence[str],
        incoming_signals: Sequence[SocialSignal],
    ) -> float:
        fn = self.config.reward_fn
        if not callable(fn):
            return 0.0

        attempts: Tuple[Tuple[Any, ...], ...] = (
            (agent, context_events, incoming_signals, self),
            (agent, context_events, incoming_signals),
            (agent, context_events),
            (agent,),
            (),
        )
        for args in attempts:
            try:
                return _clamp(_safe_float(fn(*args), 0.0), -1.0, 1.0)
            except TypeError:
                continue
            except Exception:
                return 0.0
        return 0.0

    def _invoke_agent_sleep(self, agent: Any, cycles: int = 1) -> None:
        sleep_fn = getattr(agent, "sleep", None)
        if not callable(sleep_fn):
            return
        try:
            sleep_fn(cycles=cycles)
            return
        except TypeError:
            pass
        try:
            sleep_fn(cycles)
            return
        except TypeError:
            pass
        sleep_fn()

    def _invoke_agent_step(
        self,
        agent: Any,
        context_events: List[str],
        reward: float,
    ) -> None:
        step_fn = getattr(agent, "step", None)
        if not callable(step_fn):
            return
        try:
            step_fn(context_events, reward=reward)
            return
        except TypeError:
            pass
        try:
            step_fn(context_events)
            return
        except TypeError:
            pass
        step_fn()

    def add_agent(
        self,
        agent: Any,
        position: Optional[Position3D] = None,
    ) -> Position3D:
        agent_id = self._agent_id(agent)
        if agent_id in self._slots:
            warnings.warn(
                f"Agent with id '{agent_id}' already exists; keeping existing slot",
                RuntimeWarning,
                stacklevel=2,
            )
            return self._slots[agent_id].position

        # Cap first, then one publication. A placement failure raises
        # before the slot exists, so the caller cannot observe a partial add.
        if len(self._slots) >= MAX_POPULATION_SIZE:
            raise ValueError(f"Population limit reached ({MAX_POPULATION_SIZE})")

        target = position if position is not None else Position3D.random(self.config.bounds, self._rng)
        assigned = self._find_free_position(target)
        perception_radius = self._get_perception_radius(agent)

        self._slots[agent_id] = AgentSlot(
            agent=agent,
            position=assigned,
            perception_radius=perception_radius,
        )

        setter = getattr(agent, "set_environment_interface", None)
        if callable(setter):
            try:
                setter(self)
            except Exception:
                pass

        return assigned

    def remove_agent(self, agent_id: str) -> Optional[Any]:
        slot = self._slots.pop(str(agent_id), None)
        if slot is None:
            return None
        return slot.agent

    def move_agent(self, agent_id: str, new_position: Position3D) -> bool:
        key = str(agent_id)
        slot = self._slots.get(key)
        if slot is None:
            return False
        if not self.config.bounds.contains(new_position):
            return False
        if self._is_colliding(new_position, ignore_agent_id=key):
            return False
        slot.position = new_position
        return True

    def get_agent(self, agent_id: str) -> Optional[Any]:
        slot = self._slots.get(str(agent_id))
        if slot is None:
            return None
        return slot.agent

    def get_position(self, agent_id: str) -> Optional[Position3D]:
        slot = self._slots.get(str(agent_id))
        if slot is None:
            return None
        return slot.position

    def get_all_agents(self) -> List[Any]:
        return [self._slots[agent_id].agent for agent_id in sorted(self._slots)]

    def replace_population(self, agents: List[Any]) -> None:
        if len(agents) > MAX_POPULATION_SIZE:
            raise ValueError(f"Population size exceeds limit ({MAX_POPULATION_SIZE})")
        self._slots.clear()
        for agent in agents:
            self.add_agent(agent, position=None)

    def get_agents_in_radius(
        self,
        agent_id: str,
        radius: Optional[float] = None,
        include_sleeping: bool = True,
    ) -> List[Tuple[Any, float]]:
        source_id = str(agent_id)
        source = self._slots.get(source_id)
        if source is None:
            return []

        limit = source.perception_radius if radius is None else max(0.0, _safe_float(radius, 0.0))
        nearby: List[Tuple[Any, float]] = []
        # Iterate without sorting to avoid O(n log n) cost per-agent; collect
        # nearby agents then sort only that smaller list by distance.
        for other_id, other_slot in self._slots.items():
            if other_id == source_id:
                continue
            if not include_sleeping and other_slot.is_sleeping:
                continue
            try:
                distance = source.position.distance_to(other_slot.position)
            except Exception:
                # Skip malformed positions rather than failing.
                continue
            if distance <= limit:
                nearby.append((other_slot.agent, distance))

        nearby.sort(key=lambda item: (item[1], self._agent_id(item[0])))
        return nearby

    def collect_signals_for_agent(self, agent_id: str) -> List[SocialSignal]:
        target_id = str(agent_id)
        target_slot = self._slots.get(target_id)
        if target_slot is None:
            return []

        signals: List[SocialSignal] = []
        for source_agent, distance in self.get_agents_in_radius(target_id, include_sleeping=True):
            source_id = self._agent_id(source_agent)
            source_slot = self._slots.get(source_id)
            if source_slot is None:
                continue

            base_strength = 1.0
            if source_slot.is_sleeping:
                base_strength = SLEEPING_SIGNAL_FACTOR

            decay_factor = max(0.0, _safe_float(self.config.signal_decay_factor, 0.01))
            strength = base_strength / (1.0 + (distance ** 2) * decay_factor)
            if strength < SIGNAL_MIN_STRENGTH:
                continue

            axes = self._get_affective_axes(source_slot.agent)
            signals.append(
                SocialSignal(
                    source_agent_id=source_id,
                    valence=axes["valence"],
                    arousal=axes["arousal"],
                    stress=axes["stress"],
                    curiosity=axes["curiosity"],
                    signal_strength=_clamp(strength, 0.0, 1.0),
                    source_is_sleeping=source_slot.is_sleeping,
                    distance=distance,
                    step=self.global_step,
                )
            )

        signals.sort(key=lambda item: (-item.signal_strength, item.distance, item.source_agent_id))
        return signals

    def apply_social_signal(
        self,
        agent: Any,
        signal: SocialSignal,
        gain: float,
    ) -> None:
        try:
            effective_gain = _clamp(_safe_float(gain, 0.0), 0.0, MAX_SOCIAL_SIGNAL_GAIN)
            agent_id = self._agent_id(agent)
            slot = self._slots.get(agent_id)
            if slot is not None and slot.is_sleeping:
                effective_gain *= 0.5
            effective_gain = _clamp(effective_gain, 0.0, MAX_SOCIAL_SIGNAL_GAIN)
            if effective_gain <= 0.0:
                return

            payload = {
                "valence": _safe_float(signal.valence, 0.0) * signal.signal_strength * effective_gain,
                "arousal": _safe_float(signal.arousal, 0.0) * signal.signal_strength * effective_gain,
                "stress": _safe_float(signal.stress, 0.0) * signal.signal_strength * effective_gain,
                "curiosity": _safe_float(signal.curiosity, 0.0) * signal.signal_strength * effective_gain,
                "source_is_sleeping": bool(signal.source_is_sleeping),
            }
            uncertainty = _clamp(1.0 - _safe_float(signal.signal_strength, 0.0), 0.0, 1.0)

            observe_fn = getattr(agent, "observe_external_input", None)
            if callable(observe_fn):
                observe_fn(
                    source=f"social:{signal.source_agent_id}",
                    payload=payload,
                    uncertainty=uncertainty,
                )
                return

            affective_space = getattr(agent, "affective_space", None)
            if affective_space is None:
                return

            step_fn = getattr(affective_space, "step", None)
            if callable(step_fn):
                step_fn(inputs=payload, uncertainty=uncertainty)
                return

            axes = getattr(affective_space, "axes", None)
            if not isinstance(axes, MutableMapping):
                return

            axes["valence"] = _clamp(
                _safe_float(axes.get("valence"), 0.0) + payload["valence"],
                -1.0,
                1.0,
            )
            for axis in ("arousal", "stress", "curiosity"):
                axes[axis] = _clamp(
                    _safe_float(axes.get(axis), 0.0) + _safe_float(payload.get(axis), 0.0),
                    0.0,
                    1.0,
                )
        except Exception:
            return

    def _update_agent_vitality(self, agent: Any, resource_share: float) -> None:
        """Update per-agent life subsystems using local state snapshots."""
        energy = _safe_float(
            getattr(getattr(getattr(agent, "autonomous_runtime", None), "energy_system", None), "energy", 0.0),
            0.0,
        )
        affective_axes = getattr(getattr(agent, "affective_space", None), "axes", {}) or {}
        valence = _safe_float(getattr(affective_axes, "get", lambda *_: 0.0)("valence", 0.0), 0.0)
        cortisol = _safe_float(getattr(getattr(agent, "neuromodulators", None), "cortisol", 0.0), 0.0)
        lived_steps = max(0, int(_safe_float(getattr(agent, "lived_steps", 0), 0.0)))

        try:
            reproductive = self._get_agent_component(agent, "reproductive_system")
            if reproductive is not None and hasattr(reproductive, "update"):
                reproductive.update(
                    energy=_clamp(energy, 0.0, 1.0),
                    valence=_clamp(valence, -1.0, 1.0),
                    cortisol=_clamp(cortisol, 0.0, 1.0),
                    lived_steps=lived_steps,
                    resource_share=_clamp(_safe_float(resource_share, 0.0), 0.0, 1.0),
                )
        except Exception:
            pass

        mortality = self._get_agent_component(agent, "mortality_system")
        if mortality is None or not hasattr(mortality, "update"):
            return
        history = getattr(agent, "cortisol_history", None)
        if isinstance(history, list) and history:
            cortisol_values = [_clamp(_safe_float(item, cortisol), 0.0, 1.0) for item in history]
            cortisol_mean = sum(cortisol_values) / float(len(cortisol_values))
        else:
            cortisol_mean = _clamp(cortisol, 0.0, 1.0)
        energy_v = _clamp(energy, 0.0, 1.0)
        wake_v = self._get_wakefulness_value(agent)
        age_s = getattr(agent, "age", None)
        try:
            mortality.update(
                energy=energy_v,
                wakefulness=wake_v,
                lived_steps=lived_steps,
                cortisol_mean=cortisol_mean,
                biological_age_s=age_s,
                dt_s=1.0,
            )
        except (TypeError, ValueError, AttributeError, ArithmeticError, RuntimeError) as exc:
            _LOG.warning(
                "mortality update failed for agent %s; death check continues: %s",
                self._agent_id(agent),
                exc,
                exc_info=True,
            )
            fallback = getattr(mortality, "apply_if_already_lethal", None)
            if not callable(fallback):
                return
            try:
                fallback(
                    energy=energy_v,
                    wakefulness=wake_v,
                    lived_steps=lived_steps,
                    biological_age_s=age_s if isinstance(age_s, (int, float)) else None,
                )
            except (TypeError, ValueError, AttributeError, ArithmeticError, RuntimeError) as follow_exc:
                _LOG.warning(
                    "mortality lethal fallback failed for agent %s: %s",
                    self._agent_id(agent),
                    follow_exc,
                    exc_info=True,
                )

    def _check_mortality(self, agent: Any) -> bool:
        """Remove dead agents and update death counters."""
        try:
            mortality = self._get_agent_component(agent, "mortality_system")
            if mortality is None or not hasattr(mortality, "is_dead"):
                return False
            if not bool(mortality.is_dead()):
                return False
            agent_id = self._agent_id(agent)
            if agent_id not in self._slots:
                return False
            self.remove_agent(agent_id)
            self.deaths_this_step += 1
            self.total_deaths += 1
            return True
        except Exception:
            return False

    def _build_reproduction_snapshot(self, agent: Any, genome_distance: Optional[float]) -> Dict[str, Any]:
        affective_axes = getattr(getattr(agent, "affective_space", None), "axes", {}) or {}
        reproductive = self._get_agent_component(agent, "reproductive_system")
        return {
            "genome_distance": _clamp(_safe_float(genome_distance, 0.3), 0.0, 1.0)
            if genome_distance is not None
            else None,
            "valence": _clamp(_safe_float(getattr(affective_axes, "get", lambda *_: 0.0)("valence", 0.0), 0.0), -1.0, 1.0),
            "cortisol": _clamp(_safe_float(getattr(getattr(agent, "neuromodulators", None), "cortisol", 0.0), 0.0), 0.0, 1.0),
            "reproductive_drive": _clamp(
                _safe_float(getattr(reproductive, "reproductive_drive", 0.0), 0.0),
                0.0,
                1.0,
            ),
        }

    def _check_reproduction_pairs(self) -> None:
        """Scan local neighborhoods for ready mating pairs in deterministic order."""
        if self.factory is None:
            return
        if len(self._slots) >= MAX_POPULATION_SIZE:
            return

        paired_ids: Set[str] = set()
        ordered_ids = sorted(self._slots)
        for agent_id in ordered_ids:
            if agent_id in paired_ids:
                continue
            slot = self._slots.get(agent_id)
            if slot is None:
                continue
            agent_a = slot.agent
            reproductive_a = self._get_agent_component(agent_a, "reproductive_system")
            if reproductive_a is None or not hasattr(reproductive_a, "is_ready"):
                continue
            try:
                if not bool(reproductive_a.is_ready()):
                    continue
            except Exception:
                continue

            neighbors = self.get_agents_in_radius(agent_id, include_sleeping=False)
            neighbors = sorted(neighbors, key=lambda item: self._agent_id(item[0]))
            for neighbor, _distance in neighbors:
                neighbor_id = self._agent_id(neighbor)
                if neighbor_id in paired_ids or neighbor_id == agent_id:
                    continue
                if neighbor_id not in self._slots:
                    continue
                reproductive_b = self._get_agent_component(neighbor, "reproductive_system")
                if reproductive_b is None or not hasattr(reproductive_b, "is_ready"):
                    continue
                try:
                    if not bool(reproductive_b.is_ready()):
                        continue
                except Exception:
                    continue

                genome_a = getattr(agent_a, "genome", None)
                genome_b = getattr(neighbor, "genome", None)
                genome_distance: Optional[float] = None
                if genome_a is not None and genome_b is not None and hasattr(genome_a, "distance"):
                    try:
                        genome_distance = _clamp(_safe_float(genome_a.distance(genome_b), 0.3), 0.0, 1.0)
                    except Exception:
                        genome_distance = None

                snapshot_a = self._build_reproduction_snapshot(agent_a, genome_distance)
                snapshot_b = self._build_reproduction_snapshot(neighbor, genome_distance)
                compatibility = compute_compatibility(snapshot_a, snapshot_b)
                if compatibility < MIN_COMPATIBILITY_THRESHOLD:
                    continue

                self._reproduce(agent_a, neighbor)
                paired_ids.add(agent_id)
                paired_ids.add(neighbor_id)
                break

    def _reproduce(self, parent_a: Any, parent_b: Any) -> Optional[Any]:
        """Create one child from two parents and place it near the parent midpoint."""
        if self.factory is None:
            return None
        if len(self._slots) >= MAX_POPULATION_SIZE:
            return None

        try:
            genome_a = self.factory.extract_genome(parent_a)
            genome_b = self.factory.extract_genome(parent_b)
        except Exception:
            return None

        crossover_mode = str(getattr(self.config, "crossover_mode", "arithmetic") or "arithmetic").strip().lower()
        mutation_rate = _clamp(_safe_float(getattr(self.config, "mutation_rate", 0.05), 0.05), 0.0, 1.0)
        sigma_scale = _clamp(_safe_float(getattr(self.config, "sigma_scale", 1.0), 1.0), 0.1, 5.0)
        epigenome_noise = _clamp(_safe_float(getattr(self.config, "epigenome_noise", 0.1), 0.1), 0.0, 1.0)

        try:
            child_genome, _ = genome_a.crossover(genome_b, alpha=0.5, mode=crossover_mode, rng=self._rng)
        except Exception:
            try:
                child_genome, _ = genome_a.crossover(genome_b, alpha=0.5, mode="arithmetic", rng=self._rng)
            except Exception:
                return None
        try:
            child_genome = child_genome.mutate(rate=mutation_rate, sigma_scale=sigma_scale, rng=self._rng)
        except Exception:
            return None

        child_epigenome = None
        try:
            epigenome_a = self.factory.extract_epigenome(parent_a)
            epigenome_b = self.factory.extract_epigenome(parent_b)
            if epigenome_a is not None and epigenome_b is not None and hasattr(epigenome_a, "blend"):
                child_epigenome = epigenome_a.blend(epigenome_b, alpha=0.5, rng=self._rng)
        except Exception:
            child_epigenome = None

        base_child_id = f"child_{self.global_step}_{self.total_births + self.births_this_step}"
        child_id = base_child_id
        suffix = 1
        while child_id in self._slots:
            child_id = f"{base_child_id}_{suffix}"
            suffix += 1

        try:
            child = self.factory.spawn(
                genome=child_genome,
                epigenome=child_epigenome,
                epigenome_noise=epigenome_noise,
                rng=self._rng,
                agent_id=child_id,
            )
        except Exception:
            return None

        # Library-level safety: ensure the child has parent metadata and
        # inherit sensible attributes when possible.
        try:
            mother_id = str(getattr(parent_a, "agent_id", "") or "")
            father_id = str(getattr(parent_b, "agent_id", "") or "")
            try:
                child.parents = (mother_id or None, father_id or None)
            except Exception:
                # assignment may not be supported; ignore
                pass
        except Exception:
            mother_id = ""
            father_id = ""

        # Propagate generation if the attribute exists
        try:
            pa_gen = int(getattr(parent_a, "generation", 0) or 0)
            pb_gen = int(getattr(parent_b, "generation", 0) or 0)
            if hasattr(child, "generation"):
                child.generation = max(pa_gen, pb_gen) + 1
        except Exception:
            pass

        # Update genome inheritance meta if available
        try:
            if hasattr(child, "genome_inheritance_meta") and isinstance(child.genome_inheritance_meta, dict):
                child.genome_inheritance_meta.update({
                    "mode": "recombined",
                    "mother_id": mother_id,
                    "father_id": father_id,
                })
        except Exception:
            pass

        # If the child supports NOWA-specific inheritance, invoke it safely.
        try:
            inherit_fn = getattr(child, "_inherit_nowa_from", None) or getattr(child, "_inherit_from", None)
            if callable(inherit_fn):
                try:
                    inherit_fn(parent_a, parent_b)
                except Exception:
                    try:
                        inherit_fn(parent_a, None)
                    except Exception:
                        pass
        except Exception:
            pass

        position_a = self.get_position(self._agent_id(parent_a))
        position_b = self.get_position(self._agent_id(parent_b))
        if position_a is not None and position_b is not None:
            jitter = max(1.0, MIN_AGENT_DISTANCE * 4.0)
            target = Position3D(
                x=((position_a.x + position_b.x) * 0.5) + self._rng.uniform(-jitter, jitter),
                y=((position_a.y + position_b.y) * 0.5) + self._rng.uniform(-jitter, jitter),
                z=((position_a.z + position_b.z) * 0.5) + self._rng.uniform(-jitter, jitter),
            )
            child_position = self.config.bounds.clamp(target)
        else:
            child_position = Position3D.random(self.config.bounds, self._rng)

        try:
            self.add_agent(child, position=child_position)
        except Exception:
            return None

        for parent in (parent_a, parent_b):
            try:
                reproductive = self._get_agent_component(parent, "reproductive_system")
                if reproductive is not None and hasattr(reproductive, "register_reproduction"):
                    reproductive.register_reproduction(self.global_step)
            except Exception:
                pass
            try:
                energy_system = getattr(getattr(parent, "autonomous_runtime", None), "energy_system", None)
                if energy_system is not None and hasattr(energy_system, "energy"):
                    current_energy = _clamp(_safe_float(getattr(energy_system, "energy", 0.0), 0.0), 0.0, 1.0)
                    energy_system.energy = _clamp(current_energy - REPRODUCTION_ENERGY_COST, 0.0, 1.0)
            except Exception:
                pass

        self.births_this_step += 1
        self.total_births += 1
        return child

    def tick(
        self,
        dt: float = 1.0,
        context_override: Optional[Dict[str, List[str]]] = None,
    ) -> SwarmState:
        del dt  # reserved for future physical dynamics

        self.births_this_step = 0
        self.deaths_this_step = 0
        social_signals_sent = 0
        ordered_ids = sorted(self._slots)

        for agent_id in ordered_ids:
            slot = self._slots.get(agent_id)
            if slot is None:
                continue
            agent = slot.agent

            try:
                woke_this_tick = False
                incoming_signals: List[SocialSignal] = []
                signals_already_applied = False

                if slot.is_sleeping:
                    incoming_signals = self.collect_signals_for_agent(agent_id)
                    social_signals_sent += len(incoming_signals)
                    for signal in incoming_signals:
                        self.apply_social_signal(agent, signal, self.config.social_signal_gain)
                    signals_already_applied = True

                    wake_by_signal = _check_wake_signal(
                        incoming_signals,
                        threshold=self.config.wake_signal_threshold,
                    )
                    wakefulness_value = self._get_wakefulness_value(agent)
                    wake_by_hysteresis = (
                        wakefulness_value
                        < (_safe_float(self.config.sleep_threshold, 0.7) * SLEEP_HYSTERESIS_FACTOR)
                    )

                    if wake_by_signal or wake_by_hysteresis:
                        slot.is_sleeping = False
                        slot.sleep_started_step = 0
                        woke_this_tick = True
                    else:
                        self._invoke_agent_sleep(agent, cycles=1)
                        continue

                if not woke_this_tick and _should_sleep(agent, self.config):
                    slot.is_sleeping = True
                    slot.sleep_started_step = self.global_step
                    self._invoke_agent_sleep(agent, cycles=1)
                    continue

                if not signals_already_applied:
                    incoming_signals = self.collect_signals_for_agent(agent_id)
                    social_signals_sent += len(incoming_signals)
                    for signal in incoming_signals:
                        self.apply_social_signal(agent, signal, self.config.social_signal_gain)

                context_events = self._resolve_context_events(
                    agent_id,
                    agent,
                    context_override,
                    incoming_signals=incoming_signals,
                )
                reward = self._resolve_reward(agent, context_events, incoming_signals)
                self._invoke_agent_step(agent, context_events, reward)
            except Exception as exc:
                warnings.warn(
                    f"Swarm tick skipped failing agent '{agent_id}': {exc}",
                    RuntimeWarning,
                    stacklevel=2,
                )
                continue

        try:
            self._last_resource_share = self.ecology.consume(len(self._slots))
        except Exception:
            self._last_resource_share = 1.0

        for agent_id in sorted(list(self._slots)):
            slot = self._slots.get(agent_id)
            if slot is None:
                continue
            agent = slot.agent
            try:
                self._update_agent_vitality(agent, self._last_resource_share)
            except (TypeError, ValueError, AttributeError, ArithmeticError, RuntimeError) as exc:
                _LOG.warning(
                    "vitality update failed for agent %s: %s",
                    agent_id,
                    exc,
                    exc_info=True,
                )
            self._check_mortality(agent)

        self._check_reproduction_pairs()
        self._last_social_signals_sent = social_signals_sent
        self.global_step += 1
        return self.get_swarm_state()

    def run_generation(
        self,
        steps: Optional[int] = None,
        dt: float = 1.0,
    ) -> List[SwarmState]:
        count = self.config.max_steps_per_generation if steps is None else max(0, int(steps))
        return [self.tick(dt=dt) for _ in range(count)]

    def get_diversity(self) -> float:
        genomes: List[Any] = []
        for slot in self._slots.values():
            genome = getattr(slot.agent, "genome", None)
            if genome is not None and hasattr(genome, "distance"):
                genomes.append(genome)

        if len(genomes) < 2:
            return 0.0

        distances: List[float] = []
        for i in range(len(genomes)):
            for j in range(i + 1, len(genomes)):
                try:
                    distances.append(max(0.0, _safe_float(genomes[i].distance(genomes[j]), 0.0)))
                except Exception:
                    continue
        if not distances:
            return 0.0
        return sum(distances) / float(len(distances))

    def get_swarm_state(self) -> SwarmState:
        agent_count = len(self._slots)
        sleeping_count = sum(1 for slot in self._slots.values() if slot.is_sleeping)
        active_count = agent_count - sleeping_count

        wakefulness_values = [
            self._get_wakefulness_value(slot.agent)
            for slot in self._slots.values()
        ]
        mean_wakefulness = (
            sum(wakefulness_values) / float(len(wakefulness_values))
            if wakefulness_values
            else 0.0
        )

        return SwarmState(
            step=self.global_step,
            agent_count=agent_count,
            sleeping_count=sleeping_count,
            active_count=active_count,
            diversity=self.get_diversity(),
            mean_wakefulness=mean_wakefulness,
            social_signals_sent=self._last_social_signals_sent,
            bounds=self.config.bounds,
            resource_level=_safe_float(getattr(self.ecology, "current_resources", 0.0), 0.0),
            resource_share=_clamp(_safe_float(self._last_resource_share, 1.0), 0.0, 1.0),
            births_this_step=int(self.births_this_step),
            deaths_this_step=int(self.deaths_this_step),
            total_births=int(self.total_births),
            total_deaths=int(self.total_deaths),
        )

    def evaluate_all(self) -> List[FitnessVector]:
        vectors: List[FitnessVector] = []
        for agent_id in sorted(self._slots):
            agent = self._slots[agent_id].agent
            try:
                vectors.append(self.fitness_evaluator.evaluate(agent))
            except Exception as exc:
                warnings.warn(
                    f"Fitness evaluation failed for '{agent_id}': {exc}",
                    RuntimeWarning,
                    stacklevel=2,
                )
                continue
        return vectors

    def get_sleeping_agents(self) -> List[str]:
        return sorted([agent_id for agent_id, slot in self._slots.items() if slot.is_sleeping])

    def get_active_agents(self) -> List[str]:
        return sorted([agent_id for agent_id, slot in self._slots.items() if not slot.is_sleeping])

    def get_nearest_agents(
        self,
        position: Position3D,
        k: int = 5,
        include_sleeping: bool = True,
    ) -> List[Tuple[Any, float]]:
        if k <= 0:
            return []

        nearby: List[Tuple[Any, float]] = []
        for agent_id, slot in self._slots.items():
            if not include_sleeping and slot.is_sleeping:
                continue
            nearby.append((slot.agent, position.distance_to(slot.position)))
        nearby.sort(key=lambda item: (item[1], self._agent_id(item[0])))
        return nearby[: int(k)]

    def get_spatial_density(self, position: Position3D, radius: float) -> float:
        r = max(0.0, _safe_float(radius, 0.0))
        if r <= 0.0:
            return 0.0

        count = 0
        for slot in self._slots.values():
            if position.distance_to(slot.position) <= r:
                count += 1

        if self.config.bounds.is_2d():
            area = math.pi * (r ** 2)
            if area <= 0.0:
                return 0.0
            return count / area

        volume = (4.0 / 3.0) * math.pi * (r ** 3)
        if volume <= 0.0:
            return 0.0
        return count / volume


__all__ = [
    "SWARM_VERSION",
    "MAX_POPULATION_SIZE",
    "MIN_POPULATION_SIZE",
    "MIN_AGENT_DISTANCE",
    "SIGNAL_MIN_STRENGTH",
    "MAX_SOCIAL_SIGNAL_GAIN",
    "SLEEP_HYSTERESIS_FACTOR",
    "SLEEPING_SIGNAL_FACTOR",
    "WAKE_SIGNAL_THRESHOLD",
    "SOCIAL_SIGNAL_AXES",
    "Position3D",
    "SpaceBounds",
    "SocialSignal",
    "AgentSlot",
    "SwarmState",
    "SwarmConfig",
    "SwarmEnvironment",
    "_should_sleep",
    "_check_wake_signal",
]
