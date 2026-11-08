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

logger = logging.getLogger(__name__)


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
    ) -> None:
        self.agents: list[ChinchillaAgent] = []
        self.resources = SharedResources()
        self.sim_time = 0.0
        self._refill_enabled = True
        self.swarm = ColonySwarmBridge(factory=factory)
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

    def _tick_once(self, dt: float) -> None:
        self.sim_time += dt

        self.swarm.sync_positions()
        self.swarm.update_signals()

        shuffled = list(self.agents)
        random.shuffle(shuffled)
        for agent in shuffled:
            agent.sim_step(dt)

        self.swarm.sync_positions()
        dead_ids = self.swarm.check_mortality()
        for agent_id in dead_ids:
            self._handle_agent_death(agent_id)

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
        dead_agent = next((agent for agent in self.agents if agent.agent_id == agent_id), None)
        if dead_agent is not None:
            generation_index_map = self._build_generation_index_map()
            self.death_registry.register_death(dead_agent, self.sim_time, generation_index_map)
        self.agents[:] = [agent for agent in self.agents if agent.agent_id != agent_id]
        entry = self._build_death_entry(agent_id=agent_id, agent=dead_agent)
        self._death_log.append(entry)
        self._append_death_entry(entry)
        self.deaths_this_step += 1
        self.total_deaths += 1

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
