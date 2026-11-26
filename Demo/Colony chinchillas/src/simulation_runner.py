"""Simulation loop for colony agents."""

from __future__ import annotations

import json
import logging
import math
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from colony_agent import ChinchillaAgent
from colony_renderer import RenderSnapshot, build_snapshot
from colony_swarm_bridge import ColonySwarmBridge
from config_colony import REFILL_DAY_S
from death_registry import DeathRegistry
from birth_registry import BirthRegistry
from colony_gui.utils import canonical_display_name
from shared_resources import SharedResources
from zone_snapshot import ZoneSnapshot

logger = logging.getLogger(__name__)

# Zones where animals contend for something: a bowl, the waterer, the wheel, the dust bath.
CONTESTED_ZONES = frozenset({"bowl_pellets", "bowl_hay", "waterer", "wheel", "dustbath"})


class SimulationRunner:
    """Runs colony simulation without centralized behavior decisions."""

    SIM_DT = 0.1
    # One decision is at most the load-adapted 1x step (``app.SIM_MAX_STEP_S``).
    # A 10x frame passes ``base * 10`` (up to 2.5 s). Splitting that back to
    # this interval keeps the decision rate on the 1x clock. Finer nominal
    # 1x steps (1/12 s) are already under the cap and are not coarsened.
    MAX_TICK_DT = 0.25

    def __init__(
        self,
        factory: Optional[Any] = None,
        death_journal_path: str | Path | None = None,
        seed: int | None = None,
    ) -> None:
        self.agents: list[ChinchillaAgent] = []
        self.resources = SharedResources()
        self.sim_time = 0.0
        self._refill_enabled = True
        # The colony's own generator: the turn-order noise and the swarm. A seed makes a run repeatable; the NOWA
        # core inside each animal still samples actions from the module-level random (issue #14), which the caller
        # seeds for a repeatable run. Without a seed the colony's generator is drawn from the module-level one, so a
        # caller that seeds only that (as the old shuffled tick allowed) still gets a repeatable run.
        self._rng = random.Random(seed if seed is not None else random.random())
        self.swarm = ColonySwarmBridge(factory=factory, rng=random.Random(self._rng.random()))
        self.births_this_step = 0
        self.deaths_this_step = 0
        self.total_births = 0
        self.total_deaths = 0
        self._death_log: list[dict[str, Any]] = []
        self._death_journal_path = self._resolve_death_journal_path(death_journal_path)
        self.death_registry = DeathRegistry(save_dir=self._resolve_save_dir())
        # Separate birth registry: authoritative source of human-readable
        # names captured at birth. Attach to death_registry for downstream
        # consumers that receive only the death registry object.
        self.birth_registry = BirthRegistry(save_dir=self._resolve_save_dir())
        try:
            # optional convenience: allow death_registry to reference birth registry
            setattr(self.death_registry, "birth_registry", self.birth_registry)
        except Exception:
            pass

    def add_agent(self, agent: ChinchillaAgent) -> None:
        agent.colony = self.agents
        agent.resources = self.resources
        agent_id = str(getattr(agent, "agent_id", "") or "")
        if agent_id and any(
            str(getattr(existing, "agent_id", "") or "") == agent_id for existing in self.agents
        ):
            # Already in the colony. Do not append a second entry.
            if self.swarm.get_agent(agent_id) is None:
                self.swarm.add_agent(agent)
            return
        # The swarm decides the cap and the placement. The colony list
        # gains the agent only after that call returns, so a refusal
        # cannot leave a runner entry for the birth fallback to copy.
        self.swarm.add_agent(agent)
        self.agents.append(agent)
        # Compute a canonical display name for the newborn and register the
        # birth in both registries. The canonical name follows GUI format
        # (e.g., G0A1SM) and is computed using the generation index map.
        canonical_name = None
        try:
            gen_index_map = self._build_generation_index_map()
            canonical_name = canonical_display_name(agent, index_map=gen_index_map)
        except Exception:
            canonical_name = None

        # Register birth both in the death registry (for timing) and in the
        # dedicated birth registry for authoritative human-readable names.
        try:
            self.death_registry.register_birth(agent, self.sim_time)
        except Exception:
            pass
        try:
            self.birth_registry.register_birth(agent, self.sim_time, canonical_name=canonical_name)
        except Exception:
            pass

    def tick(self, dt: float) -> None:
        """Advance every living agent by ``dt`` simulated seconds.

        ``dt`` above ``MAX_TICK_DT`` is an even split of ``ceil(dt / MAX_TICK_DT)``
        sub-ticks. Each sub-tick is one decision, so 10x does not skip the
        choices a 1x step of ``MAX_TICK_DT`` would have made. Birth and death
        counters on this call cover the whole interval.
        """
        self.births_this_step = 0
        self.deaths_this_step = 0
        try:
            remaining = float(dt)
        except (TypeError, ValueError):
            remaining = 0.0
        if not math.isfinite(remaining):
            remaining = 0.0
        if remaining <= self.MAX_TICK_DT:
            self._tick_once(remaining)
            return
        steps = int(math.ceil((remaining / self.MAX_TICK_DT) - 1e-12))
        steps = max(1, steps)
        step = remaining / float(steps)
        for _ in range(steps):
            self._tick_once(step)

    def _turn_order(self, snapshot: ZoneSnapshot) -> list[ChinchillaAgent]:
        """Turn order of one tick, which settles contests for a resource (the last food, the wheel) in one pass.

        First the animals already standing at a contested resource, then the more dominant ones, and a tie is
        broken by noise from the colony's seeded generator. Dominance comes from experience: the animal's dominance
        axis plus how dominant it feels over the animals sharing its zone (``dominance_felt``, moved by encounters).
        An animal that loses a contest gets the usual "missed out" event in its own step.
        """
        keyed = []
        for animal in snapshot.order:
            animal_id = str(animal.agent_id)
            zone = snapshot.zone.get(animal_id, str(animal.position))
            felt = [
                float(known.dominance_felt)
                for other in snapshot.near(zone)
                if other is not animal and snapshot.zone.get(str(other.agent_id)) == zone
                for known in (animal.knowledge.get(other.agent_id),)
                if known is not None
            ]
            dominance = float(animal.dominance_level) + (sum(felt) / len(felt) if felt else 0.0)
            at_resource = 0 if zone in CONTESTED_ZONES else 1
            keyed.append(((at_resource, -dominance, self._rng.random()), animal))
        keyed.sort(key=lambda item: item[0])
        return [animal for _key, animal in keyed]

    def _tick_once(self, dt: float) -> None:
        self.sim_time += dt

        self.swarm.sync_positions()
        self.swarm.update_signals()

        # One snapshot per tick (issue #28): every animal perceives the colony as it stood at the start of the tick,
        # through the zone adjacency matrix, so what it perceives does not depend on the turn order.
        snapshot = ZoneSnapshot(self.agents)
        for agent in snapshot.order:
            agent._zone_snapshot = snapshot
        try:
            for agent in self._turn_order(snapshot):
                agent.sim_step(dt)
        finally:
            for agent in snapshot.order:
                agent._zone_snapshot = None

        self.swarm.sync_positions()
        dead_ids = self.swarm.check_mortality()
        self._handle_agent_deaths(dead_ids)

        self.swarm.check_reproduction()
        self._spawn_pending_offspring()
        self.swarm.update_ecology(len(self.agents))
        if self._refill_enabled:
            self._maybe_refill_resources()

    def run_for(self, duration_s: float, dt: float | None = None) -> None:
        step = self.SIM_DT if dt is None else dt
        remaining = duration_s
        while remaining > 0.0:
            self.tick(min(step, remaining))
            remaining -= step

    def _spawn_pending_offspring(self) -> None:
        new_agents: list[ChinchillaAgent] = []
        for agent in self.agents:
            while agent.pending_offspring_list:
                offspring = agent.pending_offspring_list.pop(0)
                offspring.colony = self.agents
                offspring.resources = self.resources
                new_agents.append(offspring)
        admitted = 0
        for offspring in new_agents:
            try:
                self.add_agent(offspring)
            except (ValueError, RuntimeError) as exc:
                logger.warning(
                    "offspring %s was not admitted to the colony: %s",
                    getattr(offspring, "agent_id", ""),
                    exc,
                )
            else:
                admitted += 1
        if admitted:
            self.births_this_step += admitted
            self.total_births += admitted

    def _handle_agent_death(self, agent_id: str) -> None:
        self._handle_agent_deaths([agent_id])

    def _handle_agent_deaths(self, agent_ids) -> None:
        """Record the deaths of one tick (issue #28).

        The generation index map is built once per tick and the registry file is written once, instead of a
        full map rebuild and a full registry rewrite per death. Memorials and journal entries are the same as
        handling the deaths one by one: each death gets the index of its agent among the agents still alive
        at that point, with earlier deaths of the tick already removed.
        """
        agent_ids = [str(agent_id) for agent_id in agent_ids]
        if not agent_ids:
            return
        by_id: dict[str, ChinchillaAgent] = {}
        for agent in self.agents:
            by_id.setdefault(agent.agent_id, agent)  # the first match, as the one-by-one lookup found it
        generation_index_map = self._build_generation_index_map()
        generation_of = {
            str(getattr(agent, "agent_id", "")): int(getattr(agent, "generation", 0) or 0) for agent in self.agents
        }
        removed: set[str] = set()
        registered = False
        for agent_id in agent_ids:
            dead_agent = by_id.get(agent_id) if agent_id not in removed else None
            if dead_agent is not None:
                self.death_registry.register_death(
                    dead_agent, self.sim_time, generation_index_map, autosave=False
                )
                registered = True
                self._drop_from_generation_index(generation_index_map, generation_of, agent_id)
            removed.add(agent_id)
            entry = self._build_death_entry(agent_id=agent_id, agent=dead_agent)
            self._death_log.append(entry)
            self._append_death_entry(entry)
            self.deaths_this_step += 1
            self.total_deaths += 1
        self.agents[:] = [agent for agent in self.agents if agent.agent_id not in removed]
        if registered:
            self.death_registry.autosave()

    @staticmethod
    def _drop_from_generation_index(index_map: dict[str, int], generation_of: dict[str, int], agent_id: str) -> None:
        """Remove a dead agent from the map and close the gap in its generation, as a rebuild would."""
        position = index_map.pop(agent_id, None)
        if position is None:
            return
        generation = generation_of.get(agent_id)
        for other, other_position in index_map.items():
            if other_position > position and generation_of.get(other) == generation:
                index_map[other] = other_position - 1

    def _maybe_refill_resources(self) -> None:
        if self.sim_time - self.resources.last_refill_time < REFILL_DAY_S:
            return
        self.resources.food_pellets = 1.0
        self.resources.hay = 1.0
        self.resources.water = 1.0
        self.resources.last_refill_time = self.sim_time

    def snapshot(self) -> RenderSnapshot:
        return build_snapshot(
            [agent.get_public_state() for agent in self.agents],
            self.resources,
            self.sim_time,
        )

    def _resolve_death_journal_path(self, custom_path: str | Path | None) -> Path:
        if custom_path is not None:
            return Path(custom_path)
        project_root = Path(__file__).resolve().parents[1]
        return project_root / "logs" / "deaths.jsonl"

    def _resolve_save_dir(self) -> Path | None:
        if self._death_journal_path:
            return Path(self._death_journal_path).parent
        return None

    def _build_generation_index_map(self) -> dict[str, int]:
        by_generation: dict[int, list[str]] = {}
        for agent in self.agents:
            agent_id = str(getattr(agent, "agent_id", ""))
            if not agent_id:
                continue
            generation = int(getattr(agent, "generation", 0) or 0)
            by_generation.setdefault(generation, []).append(agent_id)
        out: dict[str, int] = {}
        for generation, agent_ids in by_generation.items():
            for idx, value in enumerate(sorted(set(agent_ids)), start=1):
                out[value] = idx
        return out

    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except Exception:
            return float(default)

    def _build_death_entry(self, *, agent_id: str, agent: ChinchillaAgent | None) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "agent_id": str(agent_id),
            "sim_time": float(self.sim_time),
            "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        if agent is None:
            entry["cause_of_death"] = "unknown"
            return entry

        mortality = getattr(agent, "mortality_system", None)
        wakefulness = getattr(getattr(agent, "wakefulness", None), "wakefulness", 0.0)
        neuromodulators = getattr(agent, "neuromodulators", None)

        entry.update(
            {
                "name": str(getattr(agent, "name", "")),
                "sex": str(getattr(agent, "sex", "")),
                "generation": int(getattr(agent, "generation", 0) or 0),
                "age": self._safe_float(getattr(agent, "age", 0.0), 0.0),
                "lived_steps": int(getattr(agent, "lived_steps", 0) or 0),
                "position": str(getattr(agent, "position", "unknown")),
                "last_action": str(getattr(agent, "current_action", "unknown")),
                "cause_of_death": str(getattr(mortality, "cause_of_death", "") or "unknown"),
                "death_step": int(getattr(mortality, "death_step", -1) or -1),
                "vitality": self._safe_float(getattr(mortality, "vitality", 0.0), 0.0),
                "energy": self._safe_float(getattr(agent, "energy", 0.0), 0.0),
                "wakefulness": self._safe_float(wakefulness, 0.0),
                "stress": self._safe_float(getattr(agent, "stress", 0.0), 0.0),
                "arousal": self._safe_float(getattr(agent, "arousal", 0.0), 0.0),
                "valence": self._safe_float(getattr(agent, "valence", 0.0), 0.0),
                "cortisol": self._safe_float(getattr(neuromodulators, "cortisol", 0.0), 0.0),
            }
        )
        return entry

    def _append_death_entry(self, entry: dict[str, Any]) -> None:
        try:
            path = self._death_journal_path
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fp:
                fp.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            # Logging must not break simulation loop.
            return
