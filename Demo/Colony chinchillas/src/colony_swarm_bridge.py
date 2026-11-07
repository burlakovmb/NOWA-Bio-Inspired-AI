"""Bridge between colony runner and generic SwarmEnvironment."""

from __future__ import annotations

import random
import sys
from pathlib import Path
from typing import Any, Optional

ROOT_SRC_PATH = Path(__file__).resolve().parents[3] / "src"
if str(ROOT_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_SRC_PATH))

from fitness import FitnessEvaluator
from reproduction import MIN_COMPATIBILITY_THRESHOLD, compute_compatibility
from swarm import Position3D, SpaceBounds, SwarmConfig, SwarmEnvironment, SwarmState

COLONY_SWARM_VERSION = "1.0"
MIN_AGENT_DISTANCE_COLONY = 0.5
ZONE_JITTER_RANGE = 3.0
DEFAULT_ZONE = "floor"
DEFAULT_3D = Position3D(50.0, 50.0, 0.0)

ZONE_POSITIONS_3D: dict[str, Position3D] = {
    "floor": Position3D(50.0, 50.0, 0.0),
    "house": Position3D(20.0, 20.0, 0.0),
    "wheel": Position3D(80.0, 50.0, 0.0),
    "shelf_lower": Position3D(80.0, 30.0, 15.0),
    "shelf_mid": Position3D(80.0, 30.0, 30.0),
    "shelf_upper": Position3D(80.0, 30.0, 45.0),
    "dustbath": Position3D(30.0, 70.0, 0.0),
    "corner": Position3D(10.0, 90.0, 0.0),
    "bowl_pellets": Position3D(50.0, 80.0, 0.0),
    "bowl_hay": Position3D(60.0, 80.0, 0.0),
    "waterer": Position3D(70.0, 80.0, 0.0),
    "litter": Position3D(10.0, 50.0, 0.0),
    "bars": Position3D(10.0, 10.0, 0.0),
    "door": Position3D(5.0, 10.0, 0.0),
    "toy": Position3D(40.0, 30.0, 0.0),
    "mineral": Position3D(35.0, 30.0, 0.0),
}

ZONE_OCCUPANT_OFFSETS: list[tuple[float, float]] = [
    (0.0, 0.0),
    (2.5, 0.0),
    (-2.5, 0.0),
    (0.0, 2.5),
    (0.0, -2.5),
    (2.5, 2.5),
    (-2.5, 2.5),
    (2.5, -2.5),
]


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class ColonySwarmBridge:
    """
    Integration layer between SimulationRunner and SwarmEnvironment.

    The bridge keeps 3D positions in sync with zone string positions and exposes
    runner-friendly operations for social signals, mortality, and reproduction.
    """

    CAGE_BOUNDS = SpaceBounds(
        x_min=0.0,
        x_max=100.0,
        y_min=0.0,
        y_max=100.0,
        z_min=0.0,
        z_max=50.0,
    )
    BASE_PERCEPTION_RADIUS = 25.0
    SIGNAL_DECAY_FACTOR = 0.008
    SLEEP_THRESHOLD = 0.7
    WAKE_SIGNAL_THRESHOLD = 0.6

    def __init__(
        self,
        factory: Optional[Any] = None,
        rng: Optional[random.Random] = None,
    ) -> None:
        config = SwarmConfig(
            bounds=self.CAGE_BOUNDS,
            base_perception_radius=self.BASE_PERCEPTION_RADIUS,
            signal_decay_factor=self.SIGNAL_DECAY_FACTOR,
            social_signal_gain=0.04,
            sleep_threshold=self.SLEEP_THRESHOLD,
            wake_signal_threshold=self.WAKE_SIGNAL_THRESHOLD,
            total_resources=500.0,
            resource_regen_rate=0.05,
            resource_per_agent_base=8.0,
        )
        self._rng = rng if rng is not None else random.Random()
        self._swarm = SwarmEnvironment(
            config=config,
            fitness_evaluator=FitnessEvaluator(),
            rng=self._rng,
            factory=factory,
        )
        self._zone_occupants: dict[str, list[str]] = {}

    def _agent_id(self, agent: Any) -> str:
        return str(getattr(agent, "agent_id", ""))

    def _zone_for_agent(self, agent: Any) -> str:
        zone = getattr(agent, "position", DEFAULT_ZONE)
        if isinstance(zone, str) and zone:
            return zone
        return DEFAULT_ZONE

    def _seeded_rng(self, key: str) -> random.Random:
        return random.Random(f"{COLONY_SWARM_VERSION}:{key}")

    def _unknown_zone_offset(self, agent_id: str, zone: str) -> tuple[float, float]:
        seeded = self._seeded_rng(f"{zone}:{agent_id}:unknown")
        return (
            seeded.uniform(-ZONE_JITTER_RANGE, ZONE_JITTER_RANGE),
            seeded.uniform(-ZONE_JITTER_RANGE, ZONE_JITTER_RANGE),
        )

    def _overflow_offset(self, agent_id: str, zone: str, index: int) -> tuple[float, float]:
        seeded = self._seeded_rng(f"{zone}:{agent_id}:{index}")
        return (
            seeded.uniform(-ZONE_JITTER_RANGE, ZONE_JITTER_RANGE),
            seeded.uniform(-ZONE_JITTER_RANGE, ZONE_JITTER_RANGE),
        )

    def _position_for_zone(self, zone: str, agent_id: str, index: int) -> Position3D:
        base = ZONE_POSITIONS_3D.get(zone)
        if base is None:
            base = DEFAULT_3D
            dx, dy = self._unknown_zone_offset(agent_id=agent_id, zone=zone)
            return Position3D(
                x=_clamp(base.x + dx, self.CAGE_BOUNDS.x_min, self.CAGE_BOUNDS.x_max),
                y=_clamp(base.y + dy, self.CAGE_BOUNDS.y_min, self.CAGE_BOUNDS.y_max),
                z=base.z,
            )

        if index < len(ZONE_OCCUPANT_OFFSETS):
            dx, dy = ZONE_OCCUPANT_OFFSETS[index]
        else:
            dx, dy = self._overflow_offset(agent_id=agent_id, zone=zone, index=index)

        return Position3D(
            x=_clamp(base.x + dx, self.CAGE_BOUNDS.x_min, self.CAGE_BOUNDS.x_max),
            y=_clamp(base.y + dy, self.CAGE_BOUNDS.y_min, self.CAGE_BOUNDS.y_max),
            z=base.z,
        )

    def _refresh_sleep_states(self) -> None:
        for agent_id, slot in self._swarm._slots.items():
            try:
                slot.is_sleeping = bool(getattr(slot.agent, "is_sleeping", False))
            except Exception:
                slot.is_sleeping = False

    def _genome_distance(self, agent_a: Any, agent_b: Any) -> Optional[float]:
        genome_a = getattr(agent_a, "genome", None)
        genome_b = getattr(agent_b, "genome", None)
        if genome_a is None or genome_b is None or not hasattr(genome_a, "distance"):
            return None
        try:
            return _clamp(float(genome_a.distance(genome_b)), 0.0, 1.0)
        except Exception:
            return None

    def _build_reproduction_snapshot(self, agent: Any, genome_distance: Optional[float]) -> dict[str, Any]:
        affective_axes = getattr(getattr(agent, "affective_space", None), "axes", {}) or {}
        reproductive = getattr(agent, "reproductive_system", None)
        return {
            "genome_distance": genome_distance,
            "valence": _clamp(
                _safe_float(getattr(affective_axes, "get", lambda *_: 0.0)("valence", 0.0), 0.0),
                -1.0,
                1.0,
            ),
            "cortisol": _clamp(
                _safe_float(getattr(getattr(agent, "neuromodulators", None), "cortisol", 0.0), 0.0),
                0.0,
                1.0,
            ),
            "reproductive_drive": _clamp(
                _safe_float(getattr(reproductive, "reproductive_drive", 0.0), 0.0),
                0.0,
                1.0,
            ),
        }

    def _is_reproduction_ready(self, agent: Any) -> bool:
        if bool(getattr(agent, "is_sleeping", False)):
            return False
        reproductive = getattr(agent, "reproductive_system", None)
        if reproductive is None or not hasattr(reproductive, "is_ready"):
            return False
        try:
            return bool(reproductive.is_ready())
        except Exception:
            return False

    def _register_reproduction(self, agent: Any) -> None:
        reproductive = getattr(agent, "reproductive_system", None)
        register = getattr(reproductive, "register_reproduction", None)
        if callable(register):
            try:
                register(int(getattr(agent, "lived_steps", 0)))
            except Exception:
                pass

    def _try_start_pregnancy(self, agent_a: Any, agent_b: Any) -> bool:
        sex_a = str(getattr(agent_a, "sex", ""))
        sex_b = str(getattr(agent_b, "sex", ""))
        mother: Any
        father: Any
        if sex_a == "F" and sex_b == "M":
            mother, father = agent_a, agent_b
        elif sex_a == "M" and sex_b == "F":
            mother, father = agent_b, agent_a
        else:
            return False

        if bool(getattr(mother, "is_pregnant", False)):
            return False

        start = getattr(mother, "_start_pregnancy", None)
        if not callable(start):
            return False

        try:
            start(self._agent_id(father))
        except Exception:
            return False

        self._register_reproduction(mother)
        self._register_reproduction(father)
        return True

    def add_agent(self, agent: Any) -> None:
        zone = self._zone_for_agent(agent)
        agent_id = self._agent_id(agent)
        position = self._position_for_zone(zone=zone, agent_id=agent_id, index=0)
        self._swarm.add_agent(agent, position=position)
        self.sync_positions()

    def get_agent(self, agent_id: str) -> Any:
        return self._swarm.get_agent(str(agent_id))

    def remove_agent(self, agent_id: str) -> None:
        self._swarm.remove_agent(str(agent_id))
        for zone_agents in self._zone_occupants.values():
            while agent_id in zone_agents:
                zone_agents.remove(agent_id)

    def get_all_agents(self) -> list[Any]:
        return self._swarm.get_all_agents()

    def sync_positions(self) -> None:
        try:
            grouped: dict[str, list[Any]] = {}
            for agent in self.get_all_agents():
                grouped.setdefault(self._zone_for_agent(agent), []).append(agent)

            new_zone_occupants: dict[str, list[str]] = {}
            for zone in sorted(grouped):
                zone_agents = sorted(grouped[zone], key=self._agent_id)
                occupant_ids: list[str] = []
                for index, agent in enumerate(zone_agents):
                    agent_id = self._agent_id(agent)
                    if self._swarm.get_agent(agent_id) is None:
                        continue
                    target = self._position_for_zone(zone=zone, agent_id=agent_id, index=index)
                    moved = self._swarm.move_agent(agent_id, target)
                    if not moved:
                        for extra in range(1, 4):
                            retry_target = self._position_for_zone(
                                zone=zone,
                                agent_id=agent_id,
                                index=len(ZONE_OCCUPANT_OFFSETS) + index + extra,
                            )
                            if self._swarm.move_agent(agent_id, retry_target):
                                moved = True
                                break
                    if moved:
                        occupant_ids.append(agent_id)
                new_zone_occupants[zone] = occupant_ids
            self._zone_occupants = new_zone_occupants
            self._refresh_sleep_states()
        except Exception:
            return

    def update_signals(self) -> int:
        self._refresh_sleep_states()
        signals_sent = 0
        for agent in self.get_all_agents():
            agent_id = self._agent_id(agent)
            try:
                signals = self._swarm.collect_signals_for_agent(agent_id)
                for signal in signals:
                    self._swarm.apply_social_signal(agent, signal, self._swarm.config.social_signal_gain)
                signals_sent += len(signals)
            except Exception:
                continue
        self._swarm._last_social_signals_sent = signals_sent
        return signals_sent

    def check_mortality(self) -> list[str]:
        dead_ids: list[str] = []
        for agent in self.get_all_agents():
            agent_id = self._agent_id(agent)
            try:
                mortality = getattr(agent, "mortality_system", None)
                is_dead_fn = getattr(mortality, "is_dead", None)
                if callable(is_dead_fn) and bool(is_dead_fn()):
                    dead_ids.append(agent_id)
            except Exception:
                continue
        for agent_id in dead_ids:
            self.remove_agent(agent_id)
        return dead_ids

    def check_reproduction(self) -> list[Any]:
        if self._swarm.factory is None:
            return []

        self._refresh_sleep_states()
        paired_ids: set[str] = set()
        ordered_agents = sorted(self.get_all_agents(), key=self._agent_id)

        for agent_a in ordered_agents:
            agent_id = self._agent_id(agent_a)
            if agent_id in paired_ids or not self._is_reproduction_ready(agent_a):
                continue

            neighbors = self._swarm.get_agents_in_radius(agent_id, include_sleeping=False)
            neighbors = sorted(neighbors, key=lambda item: self._agent_id(item[0]))

            for neighbor, _distance in neighbors:
                neighbor_id = self._agent_id(neighbor)
                if (
                    neighbor_id in paired_ids
                    or neighbor_id == agent_id
                    or not self._is_reproduction_ready(neighbor)
                ):
                    continue

                genome_distance = self._genome_distance(agent_a, neighbor)
                snapshot_a = self._build_reproduction_snapshot(agent_a, genome_distance)
                snapshot_b = self._build_reproduction_snapshot(neighbor, genome_distance)
                try:
                    compatibility = compute_compatibility(snapshot_a, snapshot_b)
                except Exception:
                    continue
                if compatibility < MIN_COMPATIBILITY_THRESHOLD:
                    continue

                if self._try_start_pregnancy(agent_a, neighbor):
                    paired_ids.add(agent_id)
                    paired_ids.add(neighbor_id)
                    break

        newborns: list[Any] = []
        for agent in ordered_agents:
            pending = getattr(agent, "pending_offspring_list", None)
            if isinstance(pending, list):
                newborns.extend(pending)
        return newborns

    def update_ecology(self, agent_count: int) -> float:
        try:
            share = self._swarm.ecology.consume(agent_count)
        except Exception:
            share = 1.0
        share = _clamp(float(share), 0.0, 1.0)
        self._swarm._last_resource_share = share
        return share

    def get_swarm_state(self) -> SwarmState:
        return self._swarm.get_swarm_state()

    def get_diversity(self) -> float:
        return self._swarm.get_diversity()

    def get_sleeping_agents(self) -> list[str]:
        self._refresh_sleep_states()
        return self._swarm.get_sleeping_agents()
