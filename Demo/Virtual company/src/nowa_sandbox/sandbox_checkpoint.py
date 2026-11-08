"""Persistence for long sandbox training runs.

Thirty-plus quarters of ninety days each take hours. A crash must not lose the
agent's hippocampus, consolidated patterns or genome, so state is written after
every quarter rather than only at the end (spec section 22).

The current ProcurementWorld is deliberately NOT saved: every quarter creates a
fresh world by definition (constraint V1).
"""

from __future__ import annotations

import pickle
import random
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from ._common import ensure_core_src_on_path
from .training_loop import SandboxTrainingResult


CHECKPOINT_VERSION = 1


class CheckpointError(RuntimeError):
    """Raised when a checkpoint cannot be written or read."""


@dataclass
class SandboxCheckpoint:
    """Everything needed to resume training from quarter ``last_quarter + 1``."""

    last_quarter: int
    graduated: bool
    graduated_at_quarter: Optional[int]
    result: SandboxTrainingResult
    agent_state_path: Optional[str] = None
    rng_state: Any = None
    genome: Any = None
    created_at: str = ""
    version: int = CHECKPOINT_VERSION
    metadata: Dict[str, Any] = field(default_factory=dict)

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
    return path.with_suffix(path.suffix + ".agent.pkl")


def save_checkpoint(
    path: Any,
    agent: Any,
    result: SandboxTrainingResult,
    rng: Optional[random.Random] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Path:
    """Write agent state plus training history; returns the metadata path."""
    meta_path = Path(path)
    meta_path.parent.mkdir(parents=True, exist_ok=True)

    agent_path = _agent_state_path(meta_path)
    saved_agent = _save_agent_state(agent, agent_path)
    if saved_agent:
        _save_intent_memory_extension(agent, agent_path)

    checkpoint = SandboxCheckpoint(
        last_quarter=len(result.quarters),
        graduated=bool(result.graduated),
        graduated_at_quarter=result.graduated_at_quarter,
        result=result,
        agent_state_path=str(agent_path) if saved_agent else None,
        rng_state=rng.getstate() if rng is not None else None,
        genome=_extract_genome(agent),
        created_at=datetime.now().isoformat(timespec="seconds"),
        metadata=dict(metadata or {}),
    )

    with open(meta_path, "wb") as handle:
        pickle.dump(checkpoint, handle)
    return meta_path


def load_checkpoint(path: Any) -> SandboxCheckpoint:
    """Read a checkpoint written by :func:`save_checkpoint`."""
    meta_path = Path(path)
    if not meta_path.exists():
        raise CheckpointError(f"checkpoint not found: {meta_path}")
    with open(meta_path, "rb") as handle:
        checkpoint = pickle.load(handle)
    if not isinstance(checkpoint, SandboxCheckpoint):
        raise CheckpointError(f"file is not a sandbox checkpoint: {meta_path}")
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
    """Persist learned sandbox habits omitted by core AgentStorage."""
    intent_memory = getattr(agent, "intent_memory", None)
    to_dict = getattr(intent_memory, "to_dict", None)
    if not callable(to_dict):
        return
    with agent_path.open("rb") as handle:
        state = pickle.load(handle)
    if not isinstance(state, dict):
        return
    state["sandbox_intent_memory"] = to_dict()
    with agent_path.open("wb") as handle:
        pickle.dump(state, handle)


def _load_intent_memory_extension(agent: Any, agent_path: Path) -> None:
    """Restore sandbox habits when present; old checkpoint files remain valid."""
    with agent_path.open("rb") as handle:
        state = pickle.load(handle)
    if not isinstance(state, dict) or "sandbox_intent_memory" not in state:
        return
    ensure_core_src_on_path()
    from intent_memory import IntentMemory
    from learning_guard import initializing

    with initializing():
        agent.intent_memory = IntentMemory.from_dict(state["sandbox_intent_memory"])
        manager = getattr(agent, "sleep_manager", None)
        if manager is not None:
            manager.intent_memory = agent.intent_memory


# ---------------------------------------------------------------------
# Agent (de)serialization — AgentStorage first, plain pickle as fallback
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
                    filename=agent_path.name,
                    agent=agent,
                )
                return True
            except Exception:
                pass

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
        with open(agent_path, "wb") as handle:
            pickle.dump(payload, handle)
        return True
    except Exception:
        return False


def _load_agent_state(agent: Any, agent_path: Path) -> bool:
    try:
        with open(agent_path, "rb") as handle:
            payload = pickle.load(handle)
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
            agent=agent,
        )
        _rebind_learning_components(agent)
        return True
    except Exception:
        return False


def _rebind_learning_components(agent: Any) -> None:
    """Keep sleep consolidation pointed at components restored onto the agent."""
    manager = getattr(agent, "sleep_manager", None)
    if manager is None:
        return
    for name in ("labile", "plasticity"):
        current = getattr(agent, name, None)
        if current is not None:
            setattr(manager, name, current)


def _extract_genome(agent: Any) -> Any:
    """Return the genome as-is when it survives a pickle round trip."""
    genome = getattr(agent, "genome", None)
    if genome is None:
        return None
    try:
        pickle.loads(pickle.dumps(genome))
    except Exception:
        to_dict = getattr(genome, "to_dict", None)
        if callable(to_dict):
            try:
                return to_dict()
            except Exception:
                return None
        return None
    return genome


__all__ = [
    "SandboxCheckpoint",
    "CheckpointError",
    "save_checkpoint",
    "load_checkpoint",
    "restore_agent",
    "CHECKPOINT_VERSION",
]
