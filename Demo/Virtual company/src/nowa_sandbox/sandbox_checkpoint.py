"""Persistence for long sandbox training runs.

Thirty-plus quarters of ninety days each take hours. A crash must not lose the
agent's hippocampus, consolidated patterns or genome, so state is written after
every quarter rather than only at the end (spec section 22).

The current ProcurementWorld is deliberately NOT saved: every quarter creates a
fresh world by definition (constraint V1).

Checkpoint documents are JSON with a schema version. Pickle files and any other
schema are rejected and never executed.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from ._common import ensure_core_src_on_path

ensure_core_src_on_path()
from state_codec import (  # noqa: E402
    AGENT_STATE_FORMAT,
    AGENT_STATE_SCHEMA_VERSION,
    StateFormatError,
    dump_state,
    load_state,
)
from .procurement_fitness import ProcurementFitnessVector  # noqa: E402
from .procurement_world import VirtualSupplier  # noqa: E402
from .training_loop import QuarterResult, SandboxTrainingResult  # noqa: E402


CHECKPOINT_FORMAT = "nowa-sandbox-checkpoint"
CHECKPOINT_VERSION = 2
LOGGER = logging.getLogger(__name__)


class CheckpointError(RuntimeError):
    """Raised when a checkpoint cannot be written or read."""


class SandboxCheckpoint:
    """Everything needed to resume training from quarter ``last_quarter + 1``."""

    def __init__(
        self,
        last_quarter: int,
        graduated: bool,
        graduated_at_quarter: Optional[int],
        result: SandboxTrainingResult,
        agent_state_path: Optional[str] = None,
        rng_state: Any = None,
        genome: Any = None,
        created_at: str = "",
        version: int = CHECKPOINT_VERSION,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.last_quarter = int(last_quarter)
        self.graduated = bool(graduated)
        self.graduated_at_quarter = graduated_at_quarter
        self.result = result
        self.agent_state_path = agent_state_path
        self.rng_state = rng_state
        self.genome = genome
        self.created_at = created_at
        self.version = int(version)
        self.metadata = dict(metadata or {})

    @property
    def next_quarter(self) -> int:
        return self.last_quarter + 1

    def summary(self) -> str:
        status = (
            f"graduated at quarter {self.graduated_at_quarter}"
            if self.graduated else "not graduated"
        )
        return (
            f"checkpoint v{self.version}: {self.last_quarter} quarter(s) completed, "
            f"{status}, resumes at quarter {self.next_quarter}"
        )


def _agent_state_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".agent.nowa")


def _agent_document(path: Path) -> Any:
    return load_state(
        path,
        expected_format=AGENT_STATE_FORMAT,
        supported_versions=(AGENT_STATE_SCHEMA_VERSION,),
    )


def _write_agent_document(path: Path, state: Any) -> None:
    dump_state(
        path,
        state,
        format_id=AGENT_STATE_FORMAT,
        schema_version=AGENT_STATE_SCHEMA_VERSION,
    )


def save_checkpoint(
    path: Any,
    agent: Any,
    result: SandboxTrainingResult,
    rng: Optional[Any] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Path:
    """Write agent state plus training history; returns the metadata path."""
    meta_path = Path(path)
    meta_path.parent.mkdir(parents=True, exist_ok=True)

    agent_path = _agent_state_path(meta_path)
    try:
        saved_agent = _save_agent_state(agent, agent_path)
        if saved_agent:
            _save_intent_memory_extension(agent, agent_path)
    except StateFormatError as exc:
        raise CheckpointError(str(exc)) from exc

    payload = {
        "last_quarter": len(result.quarters),
        "graduated": bool(result.graduated),
        "graduated_at_quarter": result.graduated_at_quarter,
        "result": _result_to_plain(result),
        "agent_state_path": str(agent_path) if saved_agent else None,
        "rng_state": rng.getstate() if rng is not None else None,
        "genome": _extract_genome(agent),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "metadata": _metadata_to_plain(metadata),
        "version": CHECKPOINT_VERSION,
    }
    try:
        dump_state(
            meta_path,
            payload,
            format_id=CHECKPOINT_FORMAT,
            schema_version=CHECKPOINT_VERSION,
        )
    except StateFormatError as exc:
        raise CheckpointError(str(exc)) from exc
    return meta_path


def load_checkpoint(path: Any) -> SandboxCheckpoint:
    """Read a checkpoint written by :func:`save_checkpoint`."""
    meta_path = Path(path)
    if not meta_path.exists():
        raise CheckpointError(f"checkpoint not found: {meta_path}")
    try:
        payload = load_state(
            meta_path,
            expected_format=CHECKPOINT_FORMAT,
            supported_versions=(CHECKPOINT_VERSION,),
        )
    except StateFormatError as exc:
        raise CheckpointError(str(exc)) from exc
    if not isinstance(payload, dict):
        raise CheckpointError(f"file is not a sandbox checkpoint: {meta_path}")
    try:
        raw_graduated_at = payload.get("graduated_at_quarter")
        graduated_at = None if raw_graduated_at is None else int(raw_graduated_at)
        checkpoint = SandboxCheckpoint(
            last_quarter=int(payload.get("last_quarter") or 0),
            graduated=bool(payload.get("graduated")),
            graduated_at_quarter=graduated_at,
            result=_result_from_plain(payload.get("result")),
            agent_state_path=payload.get("agent_state_path"),
            rng_state=payload.get("rng_state"),
            genome=_genome_from_plain(payload.get("genome")),
            created_at=str(payload.get("created_at") or ""),
            version=CHECKPOINT_VERSION,
            metadata=_metadata_from_plain(payload.get("metadata")),
        )
    except CheckpointError:
        raise
    except (TypeError, ValueError) as exc:
        raise CheckpointError(f"checkpoint {meta_path} could not be restored: {exc}") from exc
    return checkpoint


def restore_agent(checkpoint: SandboxCheckpoint, agent: Any) -> bool:
    """Load saved memory back into ``agent``; returns True when anything loaded."""
    if not checkpoint.agent_state_path:
        return False
    agent_path = Path(checkpoint.agent_state_path)
    if not agent_path.exists():
        return False

    restored = _load_agent_state(agent, agent_path)
    if restored:
        _load_intent_memory_extension(agent, agent_path)
    if restored and checkpoint.genome is not None:
        try:
            agent.genome = checkpoint.genome
        except Exception:
            pass
    return restored


def _save_intent_memory_extension(agent: Any, agent_path: Path) -> None:
    """Add sandbox habits without truncating the live agent file."""
    intent_memory = getattr(agent, "intent_memory", None)
    to_dict = getattr(intent_memory, "to_dict", None)
    if not callable(to_dict):
        return
    state = _agent_document(agent_path)
    if not isinstance(state, dict):
        return
    state["sandbox_intent_memory"] = to_dict()
    _write_agent_document(agent_path, state)


def _load_intent_memory_extension(agent: Any, agent_path: Path) -> None:
    """Restore optional habits; extension failures must not abort base restore."""
    try:
        state = _agent_document(agent_path)
        if not isinstance(state, dict):
            raise ValueError("sandbox checkpoint state must be a mapping")
        if "sandbox_intent_memory" not in state:
            return
        extension = state["sandbox_intent_memory"]
        if not isinstance(extension, dict):
            raise ValueError("sandbox IntentMemory extension must be a mapping")
        traces = extension.get("traces")
        if traces is not None and not isinstance(traces, (list, dict)):
            raise ValueError("sandbox intent traces must be a list or mapping")
        rows = traces.values() if isinstance(traces, dict) else (traces or [])
        for row in rows:
            if not isinstance(row, dict) or any(
                not isinstance(row.get(key), str) or not row[key].strip()
                for key in ("intent_type", "context_signature")
            ):
                # The core skips these rows. Reject the optional extension
                # instead of silently replacing existing habits with less data.
                raise ValueError("sandbox intent trace lacks a valid identity")
        from intent_memory import IntentMemory
        from learning_guard import initializing

        with initializing():
            memory = IntentMemory.from_dict(extension)
            previous = getattr(agent, "intent_memory", None)
            manager = getattr(agent, "sleep_manager", None)
            previous_manager = getattr(manager, "intent_memory", None)
            try:
                agent.intent_memory = memory
                if manager is not None:
                    manager.intent_memory = memory
            except Exception:
                agent.intent_memory = previous
                if manager is not None:
                    manager.intent_memory = previous_manager
                raise
    except Exception as exc:
        LOGGER.warning(
            "Sandbox IntentMemory extension could not be restored (%s); "
            "base memory remains loaded",
            type(exc).__name__,
        )


def _fitness_to_plain(fitness: ProcurementFitnessVector) -> Dict[str, Any]:
    return {
        "cost_efficiency": float(fitness.cost_efficiency),
        "stockout_avoidance": float(fitness.stockout_avoidance),
        "budget_discipline": float(fitness.budget_discipline),
        "supplier_diversification": float(fitness.supplier_diversification),
        "decision_consistency": float(fitness.decision_consistency),
        "reaction_to_risk_events": float(fitness.reaction_to_risk_events),
        "n_days": int(fitness.n_days),
        "n_orders": int(fitness.n_orders),
    }


def _fitness_from_plain(data: Any) -> ProcurementFitnessVector:
    row = dict(data or {})
    return ProcurementFitnessVector(
        cost_efficiency=float(row.get("cost_efficiency", 0.0)),
        stockout_avoidance=float(row.get("stockout_avoidance", 0.0)),
        budget_discipline=float(row.get("budget_discipline", 0.0)),
        supplier_diversification=float(row.get("supplier_diversification", 0.0)),
        decision_consistency=float(row.get("decision_consistency", 0.0)),
        reaction_to_risk_events=float(row.get("reaction_to_risk_events", 0.0)),
        n_days=int(row.get("n_days", 0)),
        n_orders=int(row.get("n_orders", 0)),
    )


def _result_to_plain(result: SandboxTrainingResult) -> Dict[str, Any]:
    quarters = []
    for quarter in list(result.quarters or []):
        quarters.append({
            "quarter_index": int(quarter.quarter_index),
            "fitness": _fitness_to_plain(quarter.fitness),
            "graduation": quarter.graduation,
            "world_summary": quarter.world_summary,
            "processing_time_s": float(quarter.processing_time_s),
            "non_regression": quarter.non_regression,
        })
    return {
        "quarters": quarters,
        "graduated": bool(result.graduated),
        "graduated_at_quarter": result.graduated_at_quarter,
    }


def _result_from_plain(data: Any) -> SandboxTrainingResult:
    row = dict(data or {})
    quarters = []
    for item in list(row.get("quarters") or []):
        if not isinstance(item, dict):
            raise CheckpointError("checkpoint quarter must be a mapping")
        quarters.append(QuarterResult(
            quarter_index=int(item.get("quarter_index", 0)),
            fitness=_fitness_from_plain(item.get("fitness")),
            graduation=dict(item.get("graduation") or {}),
            world_summary=dict(item.get("world_summary") or {}),
            processing_time_s=float(item.get("processing_time_s", 0.0)),
            non_regression=item.get("non_regression"),
        ))
    raw_graduated_at = row.get("graduated_at_quarter")
    return SandboxTrainingResult(
        quarters=quarters,
        graduated=bool(row.get("graduated")),
        graduated_at_quarter=None if raw_graduated_at is None else int(raw_graduated_at),
    )


def _metadata_to_plain(metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    plain: Dict[str, Any] = {}
    for key, value in dict(metadata or {}).items():
        if key == "carried_suppliers" and isinstance(value, dict):
            plain[key] = {
                str(sid): dict(supplier) if isinstance(supplier, dict) else asdict(supplier)
                for sid, supplier in value.items()
            }
        else:
            plain[key] = value
    return plain


def _metadata_from_plain(metadata: Any) -> Dict[str, Any]:
    plain = dict(metadata or {})
    carried = plain.get("carried_suppliers")
    if isinstance(carried, dict):
        restored = {}
        for sid, row in carried.items():
            if isinstance(row, dict):
                restored[str(sid)] = VirtualSupplier(**row)
            else:
                restored[str(sid)] = row
        plain["carried_suppliers"] = restored
    return plain


def _genome_from_plain(data: Any) -> Any:
    if data is None:
        return None
    if not isinstance(data, dict):
        raise CheckpointError("checkpoint genome must be a mapping")
    from genome import GenomeVector

    return GenomeVector.from_dict(data)


# ---------------------------------------------------------------------
# Agent (de)serialization — AgentStorage, then a minimal safe document
# ---------------------------------------------------------------------

def _agent_storage(save_dir: Path) -> Optional[Any]:
    ensure_core_src_on_path()
    try:
        from storage import AgentStorage
    except Exception:
        return None
    try:
        return AgentStorage(save_dir=str(save_dir))
    except Exception:
        return None


def _has_core_components(agent: Any) -> bool:
    hippocampus = getattr(agent, "hippocampus", None)
    cortex = getattr(agent, "cortex", None)
    selector = getattr(agent, "selector", None)
    return (
        hippocampus is not None
        and getattr(cortex, "patterns", None) is not None
        and getattr(selector, "actions", None) is not None
    )


def _save_agent_state(agent: Any, agent_path: Path) -> bool:
    if _has_core_components(agent):
        storage = _agent_storage(agent_path.parent)
        if storage is not None:
            try:
                storage.save_agent(
                    agent.hippocampus,
                    agent.cortex,
                    agent.selector,
                    affect_state=getattr(agent, "affect_state", None),
                    temporal=getattr(agent, "temporal", None),
                    sleep_manager=getattr(agent, "sleep_manager", None),
                    neuromodulators=getattr(agent, "neuromodulators", None),
                    affective_space=getattr(agent, "affective_space", None),
                    value_layer=getattr(agent, "value_layer", None),
                    conflict_arbitration=getattr(agent, "conflict_arbitration", None),
                    intent_memory=getattr(agent, "intent_memory", None),
                    filename=agent_path.name,
                    agent=agent,
                )
                return True
            except StateFormatError:
                raise
            except Exception:
                LOGGER.warning("AgentStorage save failed; trying the minimal agent document")

    return _save_agent_state_minimal(agent, agent_path)


def _save_agent_state_minimal(agent: Any, agent_path: Path) -> bool:
    """Fallback used for the no-core fallback agent."""
    hippocampus = getattr(agent, "hippocampus", None)
    if hippocampus is None:
        return False
    payload = {
        "fallback": True,
        "experiences": list(getattr(hippocampus, "experiences", []) or []),
        "consolidation_cycles": getattr(
            getattr(agent, "sleep_manager", None), "consolidation_cycles", 0
        ),
    }
    try:
        _write_agent_document(agent_path, payload)
        return True
    except StateFormatError:
        raise
    except Exception:
        return False


def _load_agent_state(agent: Any, agent_path: Path) -> bool:
    try:
        payload = _agent_document(agent_path)
    except StateFormatError as exc:
        raise CheckpointError(str(exc)) from exc
    except Exception:
        return False

    if isinstance(payload, dict) and payload.get("fallback"):
        hippocampus = getattr(agent, "hippocampus", None)
        if hippocampus is None:
            return False
        hippocampus.experiences = list(payload.get("experiences") or [])
        return True

    if not _has_core_components(agent):
        return False

    storage = _agent_storage(agent_path.parent)
    if storage is None:
        return False
    try:
        storage.load_agent(
            agent.hippocampus,
            agent.cortex,
            agent.selector,
            str(agent_path),
            affect_state=getattr(agent, "affect_state", None),
            temporal=getattr(agent, "temporal", None),
            sleep_manager=getattr(agent, "sleep_manager", None),
            neuromodulators=getattr(agent, "neuromodulators", None),
            affective_space=getattr(agent, "affective_space", None),
            value_layer=getattr(agent, "value_layer", None),
            conflict_arbitration=getattr(agent, "conflict_arbitration", None),
            intent_memory=getattr(agent, "intent_memory", None),
            agent=agent,
        )
        return True
    except StateFormatError as exc:
        raise CheckpointError(str(exc)) from exc
    except Exception:
        return False


def _extract_genome(agent: Any) -> Any:
    """Return the genome mapping when the object can describe itself."""
    genome = getattr(agent, "genome", None)
    if genome is None:
        return None
    to_dict = getattr(genome, "to_dict", None)
    if not callable(to_dict):
        return None
    try:
        data = to_dict()
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return data


__all__ = [
    "SandboxCheckpoint",
    "CheckpointError",
    "save_checkpoint",
    "load_checkpoint",
    "restore_agent",
    "CHECKPOINT_VERSION",
    "CHECKPOINT_FORMAT",
]
