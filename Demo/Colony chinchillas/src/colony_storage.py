"""Persistence helpers for colony simulation state."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agent_knowledge import HearsayItem, InteractionEpisode, KnownAgent
from colony_agent import ChinchillaAgent, _colony_max_lifespan_age_s
from genome import GenomeVector
from heat_cycle import HeatCycle
from learning_guard import initializing
from shared_resources import SharedResources
from social_layer import PendingOffer

if TYPE_CHECKING:
    from simulation_runner import SimulationRunner


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _i(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


class ColonyStorage:
    """Save/load utility for full colony runner state."""

    SCHEMA_VERSION = 1

    def __init__(self, save_dir: str | Path = "Demo/Colony chinchillas/saves") -> None:
        self.save_dir = Path(save_dir)
        self.save_dir.mkdir(parents=True, exist_ok=True)

    def save_colony(
        self,
        runner: SimulationRunner,
        filename: str | None = None,
    ) -> str:
        """Serialize current colony state to JSON and return file path."""
        if filename is None:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"colony_{stamp}.json"
        if not filename.endswith(".json"):
            filename = f"{filename}.json"

        payload = {
            "schema_version": self.SCHEMA_VERSION,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "runner": {
                "sim_time": _f(runner.sim_time),
                "refill_enabled": bool(getattr(runner, "_refill_enabled", True)),
                "death_log": list(getattr(runner, "_death_log", [])),
            },
            "resources": self._serialize_resources(runner.resources),
            "agents": [self._serialize_agent(agent) for agent in runner.agents],
        }

        path = self.save_dir / filename
        with path.open("w", encoding="utf-8") as fp:
            json.dump(payload, fp, ensure_ascii=False, indent=2)
        return str(path)

    def save(
        self,
        runner: SimulationRunner,
        path: str | Path,
    ) -> str:
        """
        Compatibility wrapper matching GUI spec naming.

        Accepts either plain filename or full path.
        """
        target = Path(path)
        if target.is_absolute() or target.parent != Path("."):
            save_dir = target.parent
            save_dir.mkdir(parents=True, exist_ok=True)
            scoped = ColonyStorage(save_dir=save_dir)
            return scoped.save_colony(runner, target.name)
        return self.save_colony(runner, target.name)

    def load_colony(self, filepath: str | Path) -> SimulationRunner:
        """Load colony state from JSON file into a new SimulationRunner."""
        from simulation_runner import SimulationRunner

        path = Path(filepath)
        with path.open("r", encoding="utf-8") as fp:
            payload = json.load(fp)

        runner = SimulationRunner()
        runner.sim_time = _f(payload.get("runner", {}).get("sim_time", 0.0))
        runner._refill_enabled = bool(payload.get("runner", {}).get("refill_enabled", True))
        raw_death_log = list(payload.get("runner", {}).get("death_log", []) or [])
        runner._death_log = []
        for item in raw_death_log:
            if not isinstance(item, dict):
                continue
            normalized = dict(item)
            normalized["agent_id"] = str(item.get("agent_id", ""))
            normalized["sim_time"] = _f(item.get("sim_time", 0.0), 0.0)
            if "cause_of_death" in item:
                normalized["cause_of_death"] = str(item.get("cause_of_death", ""))
            if "recorded_at_utc" in item:
                normalized["recorded_at_utc"] = str(item.get("recorded_at_utc", ""))
            runner._death_log.append(normalized)
        runner.resources = self._deserialize_resources(payload.get("resources", {}))

        agents_raw = payload.get("agents", []) or []
        runner.agents = []
        for item in agents_raw:
            agent = self._deserialize_agent(item, runner.resources)
            runner.add_agent(agent)
            self._bind_pending_context(agent, runner.agents, runner.resources)

        return runner

    def load(self, path: str | Path) -> SimulationRunner:
        """Compatibility wrapper matching GUI spec naming."""
        return self.load_colony(path)

    def get_save_files(self) -> list[dict[str, str]]:
        """Return saved colony files sorted by modification time desc."""
        files: list[dict[str, str]] = []
        for path in self.save_dir.glob("*.json"):
            stat = path.stat()
            files.append(
                {
                    "name": path.name,
                    "path": str(path),
                    "modified": datetime.fromtimestamp(
                        stat.st_mtime, tz=timezone.utc
                    ).isoformat(),
                }
            )
        files.sort(key=lambda item: item["modified"], reverse=True)
        return files

    def delete_save(self, filename: str) -> bool:
        """Delete one save file by name."""
        path = self.save_dir / filename
        if not path.exists():
            return False
        path.unlink()
        return True

    def _serialize_resources(self, resources: SharedResources) -> dict[str, Any]:
        return {
            "food_pellets": _f(resources.food_pellets, 1.0),
            "hay": _f(resources.hay, 1.0),
            "water": _f(resources.water, 1.0),
            "wheel_lock": resources.wheel_lock,
            "dustbath_lock": resources.dustbath_lock,
            "house_occupants": list(resources.house_occupants),
            "shelf_occupants": {
                key: list(value) for key, value in dict(resources.shelf_occupants).items()
            },
            "last_refill_time": _f(resources.last_refill_time, 0.0),
        }

    def _deserialize_resources(self, payload: dict[str, Any]) -> SharedResources:
        return SharedResources(
            food_pellets=_f(payload.get("food_pellets", 1.0), 1.0),
            hay=_f(payload.get("hay", 1.0), 1.0),
            water=_f(payload.get("water", 1.0), 1.0),
            wheel_lock=payload.get("wheel_lock"),
            dustbath_lock=payload.get("dustbath_lock"),
            house_occupants=list(payload.get("house_occupants", []) or []),
            shelf_occupants={
                key: list(value)
                for key, value in dict(payload.get("shelf_occupants", {})).items()
            }
            or {"shelf_lower": [], "shelf_mid": [], "shelf_upper": []},
            last_refill_time=_f(payload.get("last_refill_time", 0.0), 0.0),
        )

    def _serialize_agent(self, agent: ChinchillaAgent) -> dict[str, Any]:
        return {
            "identity": {
                "agent_id": agent.agent_id,
                "name": agent.name,
                "sex": agent.sex,
                "age": _f(agent.age),
                "generation": _i(agent.generation),
                "parents": [agent.parents[0], agent.parents[1]],
            },
            "runtime": {
                "position": agent.position,
                "sim_time": _f(agent.sim_time),
                "current_action": agent.current_action,
                "is_sleeping": bool(agent.is_sleeping),
                "frustration_events": list(agent.frustration_events),
                "social_drive": _f(agent.social_drive),
                "energy": _f(agent.energy),
                "neuromodulator_levels": self._serialize_neuromodulator_levels(agent),
                "lived_steps": _i(getattr(agent, "lived_steps", 0)),
                "hippocampus_experience_count": _i(len(getattr(agent.hippocampus, "experiences", []))),
                "scent_signature": agent.scent_signature,
                "offer_cooldowns": {
                    key: _f(value) for key, value in dict(agent._offer_cooldowns).items()
                },
                "exclusive_action_timer": _f(agent._exclusive_action_timer),
                "metabolism_tick": _f(agent._metabolism_tick),
                "body_step_carry": _f(getattr(agent, "_body_step_carry", 0.0)),
                "sleep_entered_by_need": bool(getattr(agent, "_sleep_entered_by_need", False)),
                "alarm": agent._export_alarm_state(),
                "pending_offer": self._serialize_pending_offer(agent.pending_offer),
                "physiology_as_policy": bool(getattr(agent, "physiology_as_policy", True)),
            },
            "affect": {
                "stress": _f(agent.stress),
                "arousal": _f(agent.arousal),
                "dominance": _f(agent.dominance_level),
                "valence": _f(agent.valence),
                "boredom": _f(agent.boredom),
                "attachment": _f(agent.attachment_level),
            },
            "genome": self._serialize_genome(getattr(agent, "genome", None)),
            "genome_inheritance_meta": self._serialize_inheritance_meta(
                getattr(agent, "genome_inheritance_meta", None)
            ),
            "reproduction": {
                "is_mature": bool(agent.is_mature),
                "is_pregnant": bool(agent.is_pregnant),
                "gestation_timer": _f(agent.gestation_timer),
                "current_mate_id": agent._current_mate_id,
                "own_offspring": list(agent.own_offspring),
                "heat_cycle": self._serialize_heat_cycle(agent.heat_cycle),
                "conception_father_id": getattr(agent, "_conception_father_id", None),
                "conception_father_name": str(getattr(agent, "_conception_father_name", "") or ""),
                "conception_father_generation": _i(getattr(agent, "_conception_father_generation", 0)),
                "conception_father_genome": self._serialize_genome(
                    getattr(agent, "_conception_father_genome", None)
                ),
                "pending_offspring_list": [
                    self._serialize_agent(child) for child in agent.pending_offspring_list
                ],
            },
            "knowledge": {
                key: self._serialize_known(known) for key, known in agent.knowledge.items()
            },
        }

    def _deserialize_agent(
        self,
        payload: dict[str, Any],
        resources: SharedResources,
    ) -> ChinchillaAgent:
        identity = dict(payload.get("identity", {}))
        runtime = dict(payload.get("runtime", {}))
        affect = dict(payload.get("affect", {}))
        reproduction = dict(payload.get("reproduction", {}))

        parents_raw = list(identity.get("parents", [None, None]) or [None, None])
        if len(parents_raw) < 2:
            parents_raw = (parents_raw + [None, None])[:2]

        agent = ChinchillaAgent(
            sex=str(identity.get("sex", "F")),
            name=str(identity.get("name", "Unknown")),
            agent_id=str(identity.get("agent_id", "")) or None,
            age=_f(identity.get("age", 0.0)),
            generation=_i(identity.get("generation", 0)),
            parents=(parents_raw[0], parents_raw[1]),
            colony=[],
            resources=resources,
            is_mature=bool(reproduction.get("is_mature", False)),
            position=str(runtime.get("position", "floor")),
        )

        # Restoring a saved individual is host initialization, not waking learning.
        with initializing():
            self._restore_saved_agent(agent, runtime, affect, reproduction, payload, resources)
        return agent

    def _restore_saved_agent(
        self,
        agent: ChinchillaAgent,
        runtime: dict[str, Any],
        affect: dict[str, Any],
        reproduction: dict[str, Any],
        payload: dict[str, Any],
        resources: SharedResources,
    ) -> None:
        agent.sim_time = _f(runtime.get("sim_time", 0.0))
        agent.current_action = str(runtime.get("current_action", "idle"))
        agent.is_sleeping = bool(runtime.get("is_sleeping", False))
        agent.frustration_events = list(runtime.get("frustration_events", []) or [])
        agent.social_drive = _f(runtime.get("social_drive", 0.45), 0.45)
        agent.energy = _f(runtime.get("energy", 1.0), 1.0)
        if "neuromodulator_levels" in runtime:
            self._restore_neuromodulator_levels(agent, runtime.get("neuromodulator_levels"))
        agent.lived_steps = _i(runtime.get("lived_steps", getattr(agent, "lived_steps", 0)))
        agent._loaded_chain_history = list(runtime.get("chain_history", []) or [])
        agent.scent_signature = str(runtime.get("scent_signature", agent.scent_signature))
        agent._offer_cooldowns = {
            str(key): _f(value)
            for key, value in dict(runtime.get("offer_cooldowns", {})).items()
        }
        agent._exclusive_action_timer = _f(runtime.get("exclusive_action_timer", 0.0))
        agent._metabolism_tick = _f(runtime.get("metabolism_tick", 0.0))
        agent._body_step_carry = _f(runtime.get("body_step_carry", 0.0))
        agent._sleep_entered_by_need = bool(runtime.get("sleep_entered_by_need", False))
        agent.pending_offer = self._deserialize_pending_offer(runtime.get("pending_offer"))
        if "physiology_as_policy" in runtime:
            agent.physiology_as_policy = bool(runtime.get("physiology_as_policy"))

        stress = _clamp(_f(affect.get("stress", 0.1), 0.1), 0.0, 1.0)
        arousal = _clamp(_f(affect.get("arousal", 0.3), 0.3), 0.0, 1.0)
        dominance = _clamp(_f(affect.get("dominance", 0.5), 0.5), 0.0, 1.0)
        valence = _clamp(_f(affect.get("valence", 0.0), 0.0), -1.0, 1.0)
        boredom = _clamp(_f(affect.get("boredom", 0.2), 0.2), 0.0, 1.0)
        attachment = _clamp(_f(affect.get("attachment", 0.0), 0.0), 0.0, 1.0)
        agent.affective_space.axes["stress"] = stress
        agent.affective_space.axes["arousal"] = arousal
        agent.affective_space.axes["dominance"] = dominance
        agent.affective_space.axes["valence"] = valence
        agent.affective_space.axes["attachment"] = attachment
        agent.affective_space.axes["curiosity"] = _clamp(1.0 - boredom, 0.0, 1.0)
        # Missing on saves from before alarm bouts were stored. Anchor at the
        # restored level so a high saved stress is not treated as a fresh spike.
        if "alarm" in runtime:
            agent._restore_alarm_state(runtime.get("alarm"))
        else:
            agent._anchor_alarm_stress()

        agent.is_pregnant = bool(reproduction.get("is_pregnant", False))
        agent.gestation_timer = _f(reproduction.get("gestation_timer", 0.0), 0.0)
        agent._current_mate_id = reproduction.get("current_mate_id")
        agent.own_offspring = list(reproduction.get("own_offspring", []) or [])
        # Absent on saves written before genomes were stored. None keeps the
        # constructor default: no genome, colony lifespan cap.
        agent.genome = self._deserialize_genome(payload.get("genome"))
        agent.mortality_system.max_lifespan_age_s = _colony_max_lifespan_age_s(agent.genome)
        # Genotype is re-applied from the saved genome. Momentary energy,
        # social drive, and neuromodulator levels are put back afterwards.
        self._apply_saved_genome(agent)
        if "genome_inheritance_meta" in payload:
            agent.genome_inheritance_meta = self._deserialize_inheritance_meta(
                payload.get("genome_inheritance_meta")
            )
        agent._conception_father_genome = self._deserialize_genome(
            reproduction.get("conception_father_genome")
        )
        raw_father_id = reproduction.get("conception_father_id")
        if raw_father_id is None:
            agent._conception_father_id = None
        else:
            agent._conception_father_id = str(raw_father_id).strip() or None
        agent._conception_father_name = str(reproduction.get("conception_father_name") or "")
        agent._conception_father_generation = _i(reproduction.get("conception_father_generation"), 0)
        agent.heat_cycle = self._deserialize_heat_cycle(reproduction.get("heat_cycle"), agent.sex)
        agent.pending_offspring_list = [
            self._deserialize_agent(child_payload, resources)
            for child_payload in list(reproduction.get("pending_offspring_list", []) or [])
        ]

        knowledge_payload = dict(payload.get("knowledge", {}))
        agent.knowledge = {
            str(key): self._deserialize_known(dict(item))
            for key, item in knowledge_payload.items()
        }

    def _serialize_genome(self, genome: GenomeVector | None) -> dict[str, Any] | None:
        if genome is None:
            return None
        to_dict = getattr(genome, "to_dict", None)
        if not callable(to_dict):
            return None
        try:
            payload = to_dict()
        except (TypeError, ValueError, AttributeError):
            return None
        if not isinstance(payload, dict):
            return None
        return payload

    def _deserialize_genome(self, payload: Any) -> GenomeVector | None:
        if not isinstance(payload, dict):
            return None
        try:
            return GenomeVector.from_dict(payload)
        except (TypeError, ValueError, AttributeError):
            return None

    def _serialize_inheritance_meta(self, meta: Any) -> dict[str, Any]:
        if not isinstance(meta, dict) or not meta:
            return {}
        try:
            encoded = json.loads(json.dumps(meta))
        except (TypeError, ValueError):
            return {}
        if not isinstance(encoded, dict):
            return {}
        return encoded

    def _deserialize_inheritance_meta(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        try:
            encoded = json.loads(json.dumps(payload))
        except (TypeError, ValueError):
            return {}
        if not isinstance(encoded, dict):
            return {}
        return encoded

    def _serialize_neuromodulator_levels(self, agent: ChinchillaAgent) -> dict[str, float]:
        neuromodulators = getattr(agent, "neuromodulators", None)
        if neuromodulators is None:
            return {}
        levels: dict[str, float] = {}
        for name in ("dopamine", "norepinephrine", "serotonin", "cortisol", "acetylcholine"):
            if not hasattr(neuromodulators, name):
                continue
            levels[name] = _f(getattr(neuromodulators, name))
        return levels

    def _restore_neuromodulator_levels(self, agent: ChinchillaAgent, payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        neuromodulators = getattr(agent, "neuromodulators", None)
        if neuromodulators is None:
            return
        restored = False
        for name in ("dopamine", "norepinephrine", "serotonin", "cortisol", "acetylcholine"):
            if name not in payload:
                continue
            try:
                setattr(neuromodulators, name, _f(payload.get(name)))
            except (TypeError, ValueError, AttributeError):
                continue
            restored = True
        if restored and hasattr(neuromodulators, "_clamp_all"):
            try:
                neuromodulators._clamp_all()
            except Exception:
                pass

    def _apply_saved_genome(self, agent: ChinchillaAgent) -> None:
        """Write genotype onto the agent, then put momentary state back.

        ``_apply_genome_to_agent`` rebuilds the autonomous runtime and sets
        drive baselines. Energy, the current social drive, and neuromodulator
        concentrations are phenotype and stay at the values already restored
        from the save.
        """
        genome = getattr(agent, "genome", None)
        to_agent_params = getattr(genome, "to_agent_params", None)
        if genome is None or not callable(to_agent_params):
            return
        try:
            params = to_agent_params()
        except Exception:
            return
        if not isinstance(params, dict):
            return

        energy = float(agent.energy)
        social_drive = float(agent.social_drive)
        levels = self._serialize_neuromodulator_levels(agent)
        try:
            from agent_factory import AgentConfig, AgentFactory

            with initializing():
                AgentFactory(
                    AgentConfig(actions=list(getattr(agent, "base_abilities", ()) or ()))
                )._apply_genome_to_agent(agent, params)
        except Exception:
            pass
        agent.energy = energy
        agent.social_drive = social_drive
        self._restore_neuromodulator_levels(agent, levels)

    def _serialize_pending_offer(self, pending: PendingOffer | None) -> dict[str, Any] | None:
        if pending is None:
            return None
        return {
            "offer_type": pending.offer_type,
            "target_id": pending.target_id,
            "started_at": _f(pending.started_at),
        }

    def _deserialize_pending_offer(self, payload: dict[str, Any] | None) -> PendingOffer | None:
        if not payload:
            return None
        return PendingOffer(
            offer_type=str(payload.get("offer_type", "")),
            target_id=str(payload.get("target_id", "")),
            started_at=_f(payload.get("started_at", 0.0)),
        )

    def _serialize_heat_cycle(self, heat_cycle: HeatCycle | None) -> dict[str, Any] | None:
        if heat_cycle is None:
            return None
        return {
            "value": _f(heat_cycle.value),
            "phase": heat_cycle.phase,
            "cycle_length_s": _f(heat_cycle.cycle_length_s),
            "estrus_duration": _f(heat_cycle.estrus_duration),
            "elapsed": _f(getattr(heat_cycle, "_elapsed", 0.0)),
        }

    def _deserialize_heat_cycle(
        self, payload: dict[str, Any] | None, sex: str
    ) -> HeatCycle | None:
        if sex != "F":
            return None
        if payload is None:
            return None
        cycle = HeatCycle(
            value=_f(payload.get("value", 0.0)),
            phase=str(payload.get("phase", "anestrus")),
            cycle_length_s=_f(payload.get("cycle_length_s", 600.0), 600.0),
            estrus_duration=_f(payload.get("estrus_duration", 60.0), 60.0),
        )
        cycle._elapsed = _f(payload.get("elapsed", 0.0), 0.0)
        return cycle

    def _serialize_known(self, known: KnownAgent) -> dict[str, Any]:
        return {
            "agent_id": known.agent_id,
            "name": known.name,
            "sex": known.sex,
            "last_seen_position": known.last_seen_position,
            "last_seen_time": _f(known.last_seen_time),
            "position_confidence": _f(known.position_confidence),
            "affinity": _f(known.affinity),
            "dominance_felt": _f(known.dominance_felt),
            "trust": _f(known.trust),
            "interaction_history": [
                {
                    "time": _f(ep.time),
                    "interaction_type": ep.interaction_type,
                    "initiated_by": ep.initiated_by,
                    "outcome": ep.outcome,
                    "affect_delta": _f(ep.affect_delta),
                    "context": ep.context,
                }
                for ep in list(known.interaction_history)
            ],
            "positive_count": _i(known.positive_count),
            "negative_count": _i(known.negative_count),
            "hearsay": [
                {
                    "subject_id": item.subject_id,
                    "source_id": item.source_id,
                    "content": item.content,
                    "time_heard": _f(item.time_heard),
                    "confidence": _f(item.confidence),
                    "hops": _i(item.hops, 1),
                }
                for item in known.hearsay
            ],
            "relationship_type": known.relationship_type,
            "familiarity": _f(known.familiarity),
            "memory_confidence": _f(known.memory_confidence),
            "is_mate": bool(known.is_mate),
            "shared_offspring": list(known.shared_offspring),
            "last_seen_affect": known.last_seen_affect,
        }

    def _deserialize_known(self, payload: dict[str, Any]) -> KnownAgent:
        known = KnownAgent(
            agent_id=str(payload.get("agent_id", "")),
            name=str(payload.get("name", "")),
            sex=str(payload.get("sex", "U")),
            last_seen_position=str(payload.get("last_seen_position", "unknown")),
            last_seen_time=_f(payload.get("last_seen_time", 0.0), 0.0),
            position_confidence=_f(payload.get("position_confidence", 1.0), 1.0),
            affinity=_f(payload.get("affinity", 0.0), 0.0),
            dominance_felt=_f(payload.get("dominance_felt", 0.0), 0.0),
            trust=_f(payload.get("trust", 0.5), 0.5),
            positive_count=_i(payload.get("positive_count", 0), 0),
            negative_count=_i(payload.get("negative_count", 0), 0),
            relationship_type=str(payload.get("relationship_type", "stranger")),
            familiarity=_f(payload.get("familiarity", 0.0), 0.0),
            memory_confidence=_f(payload.get("memory_confidence", 1.0), 1.0),
            is_mate=bool(payload.get("is_mate", False)),
            shared_offspring=list(payload.get("shared_offspring", []) or []),
            last_seen_affect=str(payload.get("last_seen_affect", "calm")),
        )

        for ep_payload in list(payload.get("interaction_history", []) or []):
            known.interaction_history.append(
                InteractionEpisode(
                    time=_f(ep_payload.get("time", 0.0), 0.0),
                    interaction_type=str(ep_payload.get("interaction_type", "")),
                    initiated_by=str(ep_payload.get("initiated_by", "self")),
                    outcome=str(ep_payload.get("outcome", "completed")),
                    affect_delta=_f(ep_payload.get("affect_delta", 0.0), 0.0),
                    context=str(ep_payload.get("context", "idle")),
                )
            )

        known.hearsay = [
            HearsayItem(
                subject_id=str(item.get("subject_id", "")),
                source_id=str(item.get("source_id", "")),
                content=str(item.get("content", "")),
                time_heard=_f(item.get("time_heard", 0.0), 0.0),
                confidence=_f(item.get("confidence", 0.0), 0.0),
                hops=_i(item.get("hops", 1), 1),
            )
            for item in list(payload.get("hearsay", []) or [])
        ]

        return known

    def _bind_pending_context(
        self,
        agent: ChinchillaAgent,
        colony: list[ChinchillaAgent],
        resources: SharedResources,
    ) -> None:
        for offspring in agent.pending_offspring_list:
            offspring.colony = colony
            offspring.resources = resources
            self._bind_pending_context(offspring, colony, resources)
