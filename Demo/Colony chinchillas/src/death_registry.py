"""Death registry, memorial snapshots and lineage nodes."""

from __future__ import annotations

import json
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

REGISTRY_VERSION = "1.1"
MAX_MEMORIALS_IN_MEMORY = 500
REGISTRY_FILENAME = "death_registry.json"


@dataclass
class LineageNode:
    """One node in the rendered lineage tree."""

    agent_id: str
    display_name: str
    sex: str
    generation: int
    parents: tuple[str | None, str | None]
    own_offspring: list[str]
    is_alive: bool
    cause_of_death: str
    age: float
    total_offspring: int
    generation_index: int
    tree_x: float = 0.0
    tree_y: float = 0.0


@dataclass
class AgentMemorial:
    """Complete snapshot of an agent captured at the moment of death."""

    agent_id: str
    name: str
    sex: str
    generation: int
    parents: tuple[str | None, str | None]
    generation_index: int

    birth_sim_time: float
    death_sim_time: float
    age_at_death: float
    lived_steps: int
    cause_of_death: str

    own_offspring: list[str]
    total_offspring: int

    final_stress: float
    final_valence: float
    final_arousal: float
    final_attachment: float
    final_curiosity: float
    final_trust: float
    final_dominance: float
    final_energy: float
    final_social_drive: float

    final_dopamine: float
    final_serotonin: float
    final_norepinephrine: float
    final_cortisol: float
    final_acetylcholine: float

    final_wakefulness: float
    final_vitality: float
    final_hippocampus_size: int
    final_cortex_patterns: int
    final_mean_td_error: float

    genome_genes: dict[str, float]
    genome_generation: int
    genome_lineage_id: str

    known_agents_count: int
    bonded_count: int
    kin_count: int
    mate_count: int
    total_interactions: int
    positive_interactions: int
    negative_interactions: int


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        casted = float(value)
    except Exception:
        return float(default)
    if casted != casted or casted in (float("inf"), float("-inf")):
        return float(default)
    return casted


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    try:
        return str(value)
    except Exception:
        return default


def _safe_parent_tuple(value: Any) -> tuple[str | None, str | None]:
    raw = value
    if not isinstance(raw, (tuple, list)):
        return (None, None)
    if len(raw) < 2:
        raw = list(raw) + [None] * (2 - len(raw))
    left = None if raw[0] in (None, "") else _safe_str(raw[0], "")
    right = None if raw[1] in (None, "") else _safe_str(raw[1], "")
    return (left, right)


def _safe_str_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    out: list[str] = []
    for item in value:
        text = _safe_str(item, "")
        if text:
            out.append(text)
    return out


def _safe_genome_genes(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, float] = {}
    for key, gene in value.items():
        out[_safe_str(key, "")] = _safe_float(gene, 0.0)
    return out


def _safe_mean(values: Any, default: float = 0.0) -> float:
    if not isinstance(values, (list, tuple)):
        return float(default)
    cleaned = [_safe_float(item, 0.0) for item in values]
    if not cleaned:
        return float(default)
    return float(sum(cleaned) / len(cleaned))


def _display_name(
    *,
    raw_name: str,
    generation: int,
    generation_index: int,
    fallback_agent_id: str,
) -> str:
    if raw_name:
        return raw_name
    if generation_index > 0:
        return f"G{max(0, int(generation))}A{generation_index}"
    return fallback_agent_id


def _extract_memorial(
    agent: Any,
    *,
    birth_sim_time: float,
    death_sim_time: float,
    generation_index_map: dict[str, int],
) -> AgentMemorial:
    """
    Extract all meaningful fields from an agent using getattr fallbacks.

    Must never raise.
    """

    agent_id = _safe_str(getattr(agent, "agent_id", ""), "")
    name = _safe_str(getattr(agent, "name", ""), "")
    sex = _safe_str(getattr(agent, "sex", ""), "")
    generation = _safe_int(getattr(agent, "generation", 0), 0)
    parents = _safe_parent_tuple(getattr(agent, "parents", (None, None)))
    generation_index = _safe_int(generation_index_map.get(agent_id, 0), 0)

    age_at_death = _safe_float(getattr(agent, "age", 0.0), 0.0)
    lived_steps = _safe_int(getattr(agent, "lived_steps", 0), 0)
    mortality = getattr(agent, "mortality_system", None)
    cause_of_death = _safe_str(getattr(mortality, "cause_of_death", ""), "")
    vitality = _safe_float(getattr(mortality, "vitality", 0.0), 0.0)
    own_offspring = _safe_str_list(getattr(agent, "own_offspring", []))
    reproductive = getattr(agent, "reproductive_system", None)
    total_offspring = _safe_int(getattr(reproductive, "total_offspring", 0), 0)

    affective_axes = getattr(getattr(agent, "affective_space", None), "axes", {}) or {}
    final_stress = _safe_float(affective_axes.get("stress", 0.0), 0.0)
    final_valence = _safe_float(affective_axes.get("valence", 0.0), 0.0)
    final_arousal = _safe_float(affective_axes.get("arousal", 0.0), 0.0)
    final_attachment = _safe_float(affective_axes.get("attachment", 0.0), 0.0)
    final_curiosity = _safe_float(affective_axes.get("curiosity", 0.0), 0.0)
    final_trust = _safe_float(affective_axes.get("trust", 0.0), 0.0)
    final_dominance = _safe_float(affective_axes.get("dominance", 0.0), 0.0)
    final_energy = _safe_float(getattr(agent, "energy", 0.0), 0.0)
    final_social_drive = _safe_float(getattr(agent, "social_drive", 0.0), 0.0)

    neuromodulators = getattr(agent, "neuromodulators", None)
    final_dopamine = _safe_float(getattr(neuromodulators, "dopamine", 0.0), 0.0)
    final_serotonin = _safe_float(getattr(neuromodulators, "serotonin", 0.0), 0.0)
    final_norepinephrine = _safe_float(getattr(neuromodulators, "norepinephrine", 0.0), 0.0)
    final_cortisol = _safe_float(getattr(neuromodulators, "cortisol", 0.0), 0.0)
    final_acetylcholine = _safe_float(getattr(neuromodulators, "acetylcholine", 0.0), 0.0)

    wakefulness = getattr(agent, "wakefulness", None)
    final_wakefulness = _safe_float(getattr(wakefulness, "wakefulness", 0.0), 0.0)

    hippocampus = getattr(agent, "hippocampus", None)
    cortex = getattr(agent, "cortex", None)
    final_hippocampus_size = _safe_int(len(getattr(hippocampus, "experiences", []) or []), 0)
    final_cortex_patterns = _safe_int(len(getattr(cortex, "patterns", []) or []), 0)
    final_mean_td_error = _safe_mean(getattr(agent, "td_error_history", []), 0.0)

    genome = getattr(agent, "genome", None)
    genome_genes = _safe_genome_genes(getattr(genome, "genes", {}) or {})
    genome_generation = _safe_int(getattr(genome, "generation", 0), 0)
    genome_lineage_id = _safe_str(getattr(genome, "lineage_id", ""), "")

    knowledge = getattr(agent, "knowledge", {}) or {}
    if not isinstance(knowledge, dict):
        knowledge = {}
    known_agents_count = len(knowledge)
    bonded_count = 0
    kin_count = 0
    mate_count = 0
    total_interactions = 0
    positive_interactions = 0
    negative_interactions = 0
    for known in knowledge.values():
        rel = _safe_str(getattr(known, "relationship_type", ""), "")
        if rel == "bonded":
            bonded_count += 1
        if rel == "kin":
            kin_count += 1
        is_mate = bool(getattr(known, "is_mate", False))
        if rel == "mate" or is_mate:
            mate_count += 1
        total_interactions += _safe_int(len(getattr(known, "interaction_history", []) or []), 0)
        positive_interactions += _safe_int(getattr(known, "positive_count", 0), 0)
        negative_interactions += _safe_int(getattr(known, "negative_count", 0), 0)

    return AgentMemorial(
        agent_id=agent_id,
        name=name,
        sex=sex,
        generation=generation,
        parents=parents,
        generation_index=generation_index,
        birth_sim_time=_safe_float(birth_sim_time, 0.0),
        death_sim_time=_safe_float(death_sim_time, 0.0),
        age_at_death=age_at_death,
        lived_steps=lived_steps,
        cause_of_death=cause_of_death,
        own_offspring=own_offspring,
        total_offspring=total_offspring,
        final_stress=final_stress,
        final_valence=final_valence,
        final_arousal=final_arousal,
        final_attachment=final_attachment,
        final_curiosity=final_curiosity,
        final_trust=final_trust,
        final_dominance=final_dominance,
        final_energy=final_energy,
        final_social_drive=final_social_drive,
        final_dopamine=final_dopamine,
        final_serotonin=final_serotonin,
        final_norepinephrine=final_norepinephrine,
        final_cortisol=final_cortisol,
        final_acetylcholine=final_acetylcholine,
        final_wakefulness=final_wakefulness,
        final_vitality=vitality,
        final_hippocampus_size=final_hippocampus_size,
        final_cortex_patterns=final_cortex_patterns,
        final_mean_td_error=final_mean_td_error,
        genome_genes=genome_genes,
        genome_generation=genome_generation,
        genome_lineage_id=genome_lineage_id,
        known_agents_count=known_agents_count,
        bonded_count=bonded_count,
        kin_count=kin_count,
        mate_count=mate_count,
        total_interactions=total_interactions,
        positive_interactions=positive_interactions,
        negative_interactions=negative_interactions,
    )


def _memorial_from_mapping(payload: dict[str, Any]) -> AgentMemorial:
    return AgentMemorial(
        agent_id=_safe_str(payload.get("agent_id", ""), ""),
        name=_safe_str(payload.get("name", ""), ""),
        sex=_safe_str(payload.get("sex", ""), ""),
        generation=_safe_int(payload.get("generation", 0), 0),
        parents=_safe_parent_tuple(payload.get("parents", (None, None))),
        generation_index=_safe_int(payload.get("generation_index", 0), 0),
        birth_sim_time=_safe_float(payload.get("birth_sim_time", 0.0), 0.0),
        death_sim_time=_safe_float(payload.get("death_sim_time", 0.0), 0.0),
        age_at_death=_safe_float(payload.get("age_at_death", 0.0), 0.0),
        lived_steps=_safe_int(payload.get("lived_steps", 0), 0),
        cause_of_death=_safe_str(payload.get("cause_of_death", ""), ""),
        own_offspring=_safe_str_list(payload.get("own_offspring", [])),
        total_offspring=_safe_int(payload.get("total_offspring", 0), 0),
        final_stress=_safe_float(payload.get("final_stress", 0.0), 0.0),
        final_valence=_safe_float(payload.get("final_valence", 0.0), 0.0),
        final_arousal=_safe_float(payload.get("final_arousal", 0.0), 0.0),
        final_attachment=_safe_float(payload.get("final_attachment", 0.0), 0.0),
        final_curiosity=_safe_float(payload.get("final_curiosity", 0.0), 0.0),
        final_trust=_safe_float(payload.get("final_trust", 0.0), 0.0),
        final_dominance=_safe_float(payload.get("final_dominance", 0.0), 0.0),
        final_energy=_safe_float(payload.get("final_energy", 0.0), 0.0),
        final_social_drive=_safe_float(payload.get("final_social_drive", 0.0), 0.0),
        final_dopamine=_safe_float(payload.get("final_dopamine", 0.0), 0.0),
        final_serotonin=_safe_float(payload.get("final_serotonin", 0.0), 0.0),
        final_norepinephrine=_safe_float(payload.get("final_norepinephrine", 0.0), 0.0),
        final_cortisol=_safe_float(payload.get("final_cortisol", 0.0), 0.0),
        final_acetylcholine=_safe_float(payload.get("final_acetylcholine", 0.0), 0.0),
        final_wakefulness=_safe_float(payload.get("final_wakefulness", 0.0), 0.0),
        final_vitality=_safe_float(payload.get("final_vitality", 0.0), 0.0),
        final_hippocampus_size=_safe_int(payload.get("final_hippocampus_size", 0), 0),
        final_cortex_patterns=_safe_int(payload.get("final_cortex_patterns", 0), 0),
        final_mean_td_error=_safe_float(payload.get("final_mean_td_error", 0.0), 0.0),
        genome_genes=_safe_genome_genes(payload.get("genome_genes", {})),
        genome_generation=_safe_int(payload.get("genome_generation", 0), 0),
        genome_lineage_id=_safe_str(payload.get("genome_lineage_id", ""), ""),
        known_agents_count=_safe_int(payload.get("known_agents_count", 0), 0),
        bonded_count=_safe_int(payload.get("bonded_count", 0), 0),
        kin_count=_safe_int(payload.get("kin_count", 0), 0),
        mate_count=_safe_int(payload.get("mate_count", 0), 0),
        total_interactions=_safe_int(payload.get("total_interactions", 0), 0),
        positive_interactions=_safe_int(payload.get("positive_interactions", 0), 0),
        negative_interactions=_safe_int(payload.get("negative_interactions", 0), 0),
    )


class DeathRegistry:
    """Registry of all agents that ever lived."""

    def __init__(self, save_dir: str | Path | None = None) -> None:
        self._memorials: dict[str, AgentMemorial] = {}
        self._birth_times: dict[str, float] = {}
        self._save_dir: Path | None = Path(save_dir) if save_dir else None

    def register_birth(self, agent: Any, sim_time: float) -> None:
        agent_id = _safe_str(getattr(agent, "agent_id", ""), "")
        if not agent_id:
            return
        self._birth_times[agent_id] = _safe_float(sim_time, 0.0)

    def register_death(
        self,
        agent: Any,
        sim_time: float,
        generation_index_map: dict[str, int],
        autosave: bool = True,
    ) -> AgentMemorial:
        """Record a death. ``autosave=False`` lets a caller write the registry once for several deaths."""
        agent_id = _safe_str(getattr(agent, "agent_id", ""), "")
        birth_sim_time = self.get_birth_time(agent_id)
        memorial = _extract_memorial(
            agent,
            birth_sim_time=birth_sim_time,
            death_sim_time=_safe_float(sim_time, 0.0),
            generation_index_map=generation_index_map,
        )
        if memorial.agent_id:
            self._memorials[memorial.agent_id] = memorial
            if memorial.agent_id not in self._birth_times:
                inferred_birth = max(0.0, memorial.death_sim_time - max(0.0, memorial.age_at_death))
                self._birth_times[memorial.agent_id] = inferred_birth
            self._trim_memorials()
            if autosave and self._save_dir is not None:
                self.autosave()
        return memorial

    def get_memorial(self, agent_id: str) -> AgentMemorial | None:
        return self._memorials.get(str(agent_id))

    def get_all_memorials(self) -> list[AgentMemorial]:
        return sorted(self._memorials.values(), key=lambda item: _safe_float(item.death_sim_time, 0.0))

    def get_recent_memorials(self, n: int = 20) -> list[AgentMemorial]:
        limit = max(0, _safe_int(n, 20))
        ordered = sorted(
            self._memorials.values(),
            key=lambda item: _safe_float(item.death_sim_time, 0.0),
            reverse=True,
        )
        return ordered[:limit] if limit > 0 else []

    def get_birth_time(self, agent_id: str) -> float:
        return _safe_float(self._birth_times.get(str(agent_id), 0.0), 0.0)

    def is_deceased(self, agent_id: str) -> bool:
        return str(agent_id) in self._memorials

    def total_ever_lived(self) -> int:
        return len(self._birth_times)

    def get_children(self, agent_id: str) -> list[str]:
        target = str(agent_id)
        children: list[str] = []
        for memorial in self._memorials.values():
            if memorial.agent_id != target:
                continue
            children.extend(memorial.own_offspring)
        deduped = []
        seen: set[str] = set()
        for child_id in children:
            child = _safe_str(child_id, "")
            if child and child not in seen:
                seen.add(child)
                deduped.append(child)
        return deduped

    def get_lineage_nodes(
        self,
        living_agents: list[Any],
        generation_index_map: dict[str, int],
    ) -> list[LineageNode]:
        nodes: list[LineageNode] = []
        for memorial in self._memorials.values():
            display_name = _display_name(
                raw_name=_safe_str(memorial.name, ""),
                generation=memorial.generation,
                generation_index=memorial.generation_index,
                fallback_agent_id=memorial.agent_id,
            )
            # For the interactive lineage overlay we intentionally suppress
            # parent links when only a single parent is recorded. This avoids
            # drawing lone parent edges for deceased agents while preserving
            # the full memorial data (memorial.parents) used elsewhere.
            raw_parents = memorial.parents if isinstance(memorial.parents, (list, tuple)) else (None, None)
            left = _safe_str(raw_parents[0], "") if len(raw_parents) > 0 else ""
            right = _safe_str(raw_parents[1], "") if len(raw_parents) > 1 else ""
            if left and right:
                parents_for_node = (left, right)
            else:
                parents_for_node = (None, None)

            nodes.append(
                LineageNode(
                    agent_id=memorial.agent_id,
                    display_name=display_name,
                    sex=memorial.sex,
                    generation=memorial.generation,
                    parents=parents_for_node,
                    own_offspring=list(memorial.own_offspring),
                    is_alive=False,
                    cause_of_death=memorial.cause_of_death,
                    age=memorial.age_at_death,
                    total_offspring=memorial.total_offspring,
                    generation_index=memorial.generation_index,
                )
            )

        dead_ids = {item.agent_id for item in nodes}
        for agent in list(living_agents or []):
            agent_id = _safe_str(getattr(agent, "agent_id", ""), "")
            if not agent_id or agent_id in dead_ids:
                continue
            generation = _safe_int(getattr(agent, "generation", 0), 0)
            generation_index = _safe_int(generation_index_map.get(agent_id, 0), 0)
            raw_name = _safe_str(getattr(agent, "name", ""), "")
            display_name = _display_name(
                raw_name=raw_name,
                generation=generation,
                generation_index=generation_index,
                fallback_agent_id=agent_id,
            )
            nodes.append(
                LineageNode(
                    agent_id=agent_id,
                    display_name=display_name,
                    sex=_safe_str(getattr(agent, "sex", ""), ""),
                    generation=generation,
                    parents=_safe_parent_tuple(getattr(agent, "parents", (None, None))),
                    own_offspring=_safe_str_list(getattr(agent, "own_offspring", [])),
                    is_alive=True,
                    cause_of_death="",
                    age=_safe_float(getattr(agent, "age", 0.0), 0.0),
                    total_offspring=_safe_int(
                        getattr(getattr(agent, "reproductive_system", None), "total_offspring", 0),
                        0,
                    ),
                    generation_index=generation_index,
                )
            )

        nodes.sort(
            key=lambda item: (
                _safe_int(item.generation, 0),
                10**9 if _safe_int(item.generation_index, 0) <= 0 else _safe_int(item.generation_index, 0),
                item.agent_id,
            )
        )
        return nodes

    def save(self, path: str | Path) -> None:
        try:
            target = Path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            memorials_payload = [asdict(item) for item in self.get_all_memorials()]
            payload: dict[str, Any] = {
                "version": REGISTRY_VERSION,
                "total_ever_lived": int(self.total_ever_lived()),
                "memorial_count": int(len(self._memorials)),
                "birth_times": {str(key): _safe_float(value, 0.0) for key, value in self._birth_times.items()},
                "memorials": memorials_payload,
            }
            with target.open("w", encoding="utf-8") as fp:
                json.dump(payload, fp, ensure_ascii=False, indent=2)
        except Exception as exc:
            warnings.warn(f"Failed to save death registry to '{path}': {exc}", RuntimeWarning)

    def load(self, path: str | Path) -> None:
        try:
            source = Path(path)
            with source.open("r", encoding="utf-8") as fp:
                payload = json.load(fp)
            if not isinstance(payload, dict):
                raise ValueError("registry payload must be a JSON object")
            birth_times_raw = payload.get("birth_times", {}) or {}
            if not isinstance(birth_times_raw, dict):
                raise ValueError("birth_times must be object")
            memorials_raw = payload.get("memorials", []) or []
            if not isinstance(memorials_raw, list):
                raise ValueError("memorials must be array")

            loaded_birth_times: dict[str, float] = {}
            for key, value in birth_times_raw.items():
                agent_id = _safe_str(key, "")
                if not agent_id:
                    continue
                loaded_birth_times[agent_id] = _safe_float(value, 0.0)

            loaded_memorials: dict[str, AgentMemorial] = {}
            for item in memorials_raw:
                if not isinstance(item, dict):
                    continue
                memorial = _memorial_from_mapping(item)
                if not memorial.agent_id:
                    continue
                loaded_memorials[memorial.agent_id] = memorial
        except Exception as exc:
            warnings.warn(f"Failed to load death registry from '{path}': {exc}", RuntimeWarning)
            return

        for agent_id, birth_sim_time in loaded_birth_times.items():
            self._birth_times.setdefault(agent_id, birth_sim_time)
        for agent_id, memorial in loaded_memorials.items():
            if agent_id not in self._memorials:
                self._memorials[agent_id] = memorial
                self._birth_times.setdefault(agent_id, memorial.birth_sim_time)
        self._trim_memorials()

    def autosave(self) -> None:
        if self._save_dir is None:
            return
        self.save(self._save_dir / REGISTRY_FILENAME)

    def clear(self) -> None:
        self._memorials.clear()
        self._birth_times.clear()

    def summary(self) -> str:
        deceased = len(self._memorials)
        total = self.total_ever_lived()
        living = max(0, total - deceased)
        return f"Registry: {total} ever lived, {deceased} deceased, {living} living"

    def _trim_memorials(self) -> None:
        overflow = len(self._memorials) - MAX_MEMORIALS_IN_MEMORY
        if overflow <= 0:
            return
        ordered = sorted(
            self._memorials.values(),
            key=lambda item: _safe_float(item.death_sim_time, 0.0),
        )
        for memorial in ordered[:overflow]:
            self._memorials.pop(memorial.agent_id, None)


__all__ = [
    "AgentMemorial",
    "DeathRegistry",
    "LineageNode",
    "MAX_MEMORIALS_IN_MEMORY",
    "REGISTRY_FILENAME",
    "REGISTRY_VERSION",
]
