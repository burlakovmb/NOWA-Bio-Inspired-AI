"""Mind checkpoint (``mind.nowa``) and session sidecar for an employee."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Sequence

from nowa_body._compat import ensure_core_src_on_path

from .employee_config import employee_dir
from .mcp_capability import parse_risk

MIND_NAME = "mind.nowa"
MIND_TMP_NAME = "mind.nowa.tmp"
SIDECAR_NAME = "session_sidecar.json"


class CheckpointError(Exception):
    """Raised when the mind document cannot be written or is unreadable."""


def mind_path(employees_root: Any, agent_id: str) -> Path:
    return employee_dir(employees_root, agent_id) / MIND_NAME


def sidecar_path(employees_root: Any, agent_id: str) -> Path:
    return employee_dir(employees_root, agent_id) / SIDECAR_NAME


def memory_is_empty(agent: Any) -> bool:
    hip = getattr(agent, "hippocampus", None)
    experiences = getattr(hip, "experiences", None)
    if experiences is None:
        return True
    try:
        return len(list(experiences)) == 0
    except TypeError:
        return not bool(experiences)


def episode_count(agent: Any) -> int:
    hip = getattr(agent, "hippocampus", None)
    experiences = getattr(hip, "experiences", None)
    if experiences is None:
        return 0
    try:
        return len(list(experiences))
    except TypeError:
        return 0


def _agent_parts(agent: Any) -> tuple:
    hip = getattr(agent, "hippocampus", None)
    if hip is None:
        hip = SimpleNamespace(experiences=[])
        try:
            agent.hippocampus = hip
        except Exception:
            pass
    cortex = getattr(agent, "cortex", None)
    if cortex is None:
        cortex = SimpleNamespace(patterns={})
        try:
            agent.cortex = cortex
        except Exception:
            pass
    selector = getattr(agent, "selector", None)
    if selector is None:
        selector = SimpleNamespace(
            actions=[],
            confidence_threshold=0.0,
            action_metadata={},
        )
        try:
            agent.selector = selector
        except Exception:
            pass
    return hip, cortex, selector


def save_mind(agent: Any, path: Any) -> None:
    """Atomic save via ``AgentStorage.save_agent(..., agent=)``."""
    ensure_core_src_on_path()
    from state_codec import (
        AGENT_STATE_FORMAT,
        AGENT_STATE_SCHEMA_VERSION,
        dump_state,
        load_state,
    )
    from storage import AgentStorage

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.parent / MIND_TMP_NAME
    hip, cortex, selector = _agent_parts(agent)
    storage = AgentStorage(save_dir=str(target.parent))
    try:
        storage.save_agent(
            hip,
            cortex,
            selector,
            affect_state=getattr(agent, "affect_state", None),
            sleep_manager=getattr(agent, "sleep_manager", None),
            neuromodulators=getattr(agent, "neuromodulators", None),
            affective_space=getattr(agent, "affective_space", None),
            value_layer=getattr(agent, "value_layer", None),
            conflict_arbitration=getattr(agent, "conflict_arbitration", None),
            intent_memory=getattr(agent, "intent_memory", None),
            filename=MIND_TMP_NAME,
            agent=agent,
        )
        # Keep the employee-owned extension inside the same atomic checkpoint.
        intent = getattr(agent, "intent_memory", None)
        if intent is not None and callable(getattr(intent, "to_dict", None)):
            state = load_state(
                tmp,
                expected_format=AGENT_STATE_FORMAT,
                supported_versions=(AGENT_STATE_SCHEMA_VERSION,),
            )
            state["vc_intent_memory"] = intent.to_dict()
            dump_state(
                tmp,
                state,
                format_id=AGENT_STATE_FORMAT,
                schema_version=AGENT_STATE_SCHEMA_VERSION,
            )
        os.replace(str(tmp), str(target))
    except Exception as exc:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        raise CheckpointError(str(exc)) from exc


def load_mind(agent: Any, path: Any) -> None:
    ensure_core_src_on_path()
    from state_codec import (
        AGENT_STATE_FORMAT,
        AGENT_STATE_SCHEMA_VERSION,
        load_state,
    )
    from storage import AgentStorage

    target = Path(path)
    if not target.is_file():
        raise CheckpointError(f"mind checkpoint not found: {target}")
    hip, cortex, selector = _agent_parts(agent)
    storage = AgentStorage(save_dir=str(target.parent))
    try:
        storage.load_agent(
            hip,
            cortex,
            selector,
            filepath=str(target),
            affect_state=getattr(agent, "affect_state", None),
            sleep_manager=getattr(agent, "sleep_manager", None),
            neuromodulators=getattr(agent, "neuromodulators", None),
            affective_space=getattr(agent, "affective_space", None),
            value_layer=getattr(agent, "value_layer", None),
            conflict_arbitration=getattr(agent, "conflict_arbitration", None),
            intent_memory=getattr(agent, "intent_memory", None),
            agent=agent,
        )
        state = load_state(
            target,
            expected_format=AGENT_STATE_FORMAT,
            supported_versions=(AGENT_STATE_SCHEMA_VERSION,),
        )
        if isinstance(state, dict) and "vc_intent_memory" in state:
            from intent_memory import IntentMemory
            from learning_guard import initializing

            # Loading is restoration, not a waking learning update.
            with initializing():
                agent.intent_memory = IntentMemory.from_dict(state["vc_intent_memory"])
                manager = getattr(agent, "sleep_manager", None)
                if manager is not None:
                    manager.intent_memory = agent.intent_memory
    except Exception as exc:
        raise CheckpointError(str(exc)) from exc


def world_state_to_dict(world_state: Any) -> Dict[str, Any]:
    if world_state is None:
        return {}
    return {
        "results": dict(getattr(world_state, "results", {}) or {}),
        "entities": dict(getattr(world_state, "entities", {}) or {}),
        "scalars": dict(getattr(world_state, "scalars", {}) or {}),
        "updated_at": dict(getattr(world_state, "updated_at", {}) or {}),
        "running_stats": dict(getattr(world_state, "running_stats", {}) or {}),
        "max_depth": int(getattr(world_state, "max_depth", 6) or 6),
        "collection_owner": dict(getattr(world_state, "_collection_owner", {}) or {}),
    }


def apply_world_state_dict(world_state: Any, data: Optional[Dict[str, Any]]) -> None:
    if world_state is None or not isinstance(data, dict):
        return
    world_state.results = dict(data.get("results") or {})
    world_state.entities = dict(data.get("entities") or {})
    world_state.scalars = dict(data.get("scalars") or {})
    world_state.updated_at = dict(data.get("updated_at") or {})
    world_state.running_stats = dict(data.get("running_stats") or {})
    if data.get("max_depth") is not None:
        try:
            world_state.max_depth = int(data["max_depth"])
        except (TypeError, ValueError):
            pass
    world_state._collection_owner = dict(data.get("collection_owner") or {})


def pending_to_list(gate: Any) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    queue = getattr(gate, "pending_queue", None) or {}
    for action_id, record in list(queue.items()):
        proposed = getattr(record, "proposed_action", None)
        if proposed is None:
            continue
        risk = getattr(proposed, "risk_level", None)
        rows.append({
            "action_id": str(action_id),
            "agent_id": str(getattr(proposed, "agent_id", "") or ""),
            "tool_id": str(getattr(proposed, "tool_id", "") or ""),
            "tool_params": dict(getattr(proposed, "tool_params", {}) or {}),
            "risk_level": getattr(risk, "value", str(risk or "high_write")),
            "intent_summary": str(getattr(proposed, "intent_summary", "") or ""),
            "requires_approval": bool(getattr(proposed, "requires_approval", True)),
            "submitted_at": float(getattr(record, "submitted_at", 0.0) or 0.0),
            "status": "pending",
        })
    return rows


def restore_pending(gate: Any, rows: Optional[List[Dict[str, Any]]]) -> None:
    if gate is None or not rows:
        return
    ensure_core_src_on_path()
    from mcp_body.approval_gate import ApprovalRecord, ApprovalStatus
    from mcp_body.proposed_action import ProposedAction

    for row in rows:
        if not isinstance(row, dict):
            continue
        action_id = str(row.get("action_id") or "").strip()
        if not action_id:
            continue
        proposed = ProposedAction(
            action_id=action_id,
            agent_id=str(row.get("agent_id") or ""),
            tool_id=str(row.get("tool_id") or ""),
            tool_params=dict(row.get("tool_params") or {}),
            risk_level=parse_risk(row.get("risk_level")),
            intent_summary=str(row.get("intent_summary") or ""),
            requires_approval=bool(row.get("requires_approval", True)),
        )
        record = ApprovalRecord(
            proposed_action=proposed,
            status=ApprovalStatus.PENDING,
            submitted_at=float(row.get("submitted_at") or 0.0),
        )
        gate.pending_queue[action_id] = record


def prune_restored_pending(
    gate: Any,
    capabilities: Sequence[Any],
    *,
    role_fingerprint: str = "",
    saved_fingerprint: str = "",
) -> int:
    """Drop sidecar WRITE that should not sit in the live queue.

    Stop always persists pending. Start used to restore it blindly, so a
    restart (or a role where approval was turned off) brought the old cards
    back. Drop when the role fingerprint changed, the organ is gone, or the
    live capability no longer requires approval. Do not auto-execute leftovers.
    """
    queue = getattr(gate, "pending_queue", None)
    if not isinstance(queue, dict) or not queue:
        return 0
    if saved_fingerprint and role_fingerprint and saved_fingerprint != role_fingerprint:
        dropped = len(queue)
        queue.clear()
        return dropped
    by_id = {str(getattr(cap, "tool_id", "") or ""): cap for cap in capabilities}
    dropped = 0
    for action_id, record in list(queue.items()):
        proposed = getattr(record, "proposed_action", None)
        tool_id = str(getattr(proposed, "tool_id", "") or "")
        cap = by_id.get(tool_id)
        if cap is None or not bool(getattr(cap, "requires_approval", True)):
            queue.pop(action_id, None)
            dropped += 1
    return dropped


def save_sidecar(path: Any, payload: Dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(target))


def load_sidecar(path: Any) -> Dict[str, Any]:
    target = Path(path)
    if not target.is_file():
        return {}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def delete_memory_files(employees_root: Any, agent_id: str) -> None:
    for path in (mind_path(employees_root, agent_id), sidecar_path(employees_root, agent_id)):
        try:
            if path.is_file():
                path.unlink()
        except OSError:
            continue


def iso_now() -> str:
    return datetime.now().isoformat(timespec="seconds")


__all__ = [
    "CheckpointError",
    "MIND_NAME",
    "SIDECAR_NAME",
    "apply_world_state_dict",
    "delete_memory_files",
    "episode_count",
    "iso_now",
    "load_mind",
    "load_sidecar",
    "memory_is_empty",
    "mind_path",
    "pending_to_list",
    "prune_restored_pending",
    "restore_pending",
    "save_mind",
    "save_sidecar",
    "sidecar_path",
    "world_state_to_dict",
]
