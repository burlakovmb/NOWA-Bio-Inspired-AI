"""Approval outcomes and body lessons, filed under the situation they are about.

The platform ``mcp_body.feedback`` stores an approval as "this tool, this
reward". The employee files it under the context the mind decided in
(``ContextualProposedAction.context_events``), turns a rejection into a
lesson about the situation ("here, wait"), and keeps calls nobody judged
faint. ``store_lesson`` is the one path for every lesson: the episode goes to
the hippocampus and its outcome to the core's labile tier, so stable values
change only in sleep. The ACTION label is always ``action:<tool_id>``.
"""

from __future__ import annotations

from typing import Any, List, Optional

from ._compat import ensure_core_src_on_path

ensure_core_src_on_path()

from mcp_body._compat import apply_impulses, load_experience_types, outcome_impulse  # noqa: E402
from mcp_body.approval_gate import ApprovalStatus  # noqa: E402
from mcp_body.feedback import _resolve_action_label  # noqa: E402
from mcp_body.feedback import approval_to_reward as platform_approval_to_reward  # noqa: E402

WAIT_AND_MONITOR = "wait_and_monitor"
SYSTEM_DECIDER_PREFIX = "system:"
# Executed without anyone judging it: remembered, but too faint to pull the
# mind toward repeating it, and not tagged for sleep consolidation.
UNJUDGED_INTENSITY = 0.1


def is_unjudged(record: Any) -> bool:
    """True when the gate executed the call itself (no human decision)."""
    return str(getattr(record, "decided_by", "") or "").startswith(SYSTEM_DECIDER_PREFIX)


def approval_to_reward(record: Any) -> float:
    if record.status == ApprovalStatus.APPROVED and is_unjudged(record):
        return 0.0
    return platform_approval_to_reward(record)


def apply_feedback_to_agent(agent: Any, record: Any, encoder: Any) -> None:
    """Store one ACTION episode labelled ``action:<tool_id>`` and step A(t).

    The episode is filed under the situation the decision was made in plus
    the outcome tokens. A rejection is a lesson about the situation, not
    about the organ: the hippocampus pulls toward whatever action a recalled
    episode holds, whatever its reward sign, so a rejected call is filed as
    "here, wait" instead of a negatively rewarded call that would still pull
    toward calling it.
    """
    reward = approval_to_reward(record)
    execution_result = record.execution_result
    if not isinstance(execution_result, dict):
        execution_result = {"status": record.status.value}

    tool_id = str(getattr(record.proposed_action, "tool_id", "") or "")
    encode_outcome = getattr(encoder, "encode_outcome", None)
    if callable(encode_outcome):
        try:
            tokens, impulse = encode_outcome(
                execution_result.get("status", record.status.value),
                execution_result,
                tool_id=tool_id,
            )
        except TypeError:
            tokens, impulse = encode_outcome(
                getattr(record.proposed_action, "intent_summary", tool_id),
                execution_result,
            )
    else:
        tokens, impulse = ["result:unknown"], outcome_impulse("unknown", 1.0)

    apply_impulses(getattr(agent, "affective_space", None), impulse, source="external")

    context = [str(t) for t in (getattr(record.proposed_action, "context_events", None) or [])]
    outcome_tokens = [str(t) for t in (tokens or []) if not str(t).startswith("action:")]
    action_label = _resolve_action_label(record.proposed_action)

    if record.status == ApprovalStatus.REJECTED:
        _record_bg_outcome(agent, action_label, reward)
        store_lesson(agent, context, WAIT_AND_MONITOR, abs(reward), consequence="call_rejected")
        return

    if is_unjudged(record):
        _store_episode(
            agent,
            context + outcome_tokens,
            action_label,
            reward=0.0,
            intensity=UNJUDGED_INTENSITY,
            consequence="executed",
        )
        return

    store_lesson(
        agent,
        context + outcome_tokens,
        action_label,
        reward,
        consequence="approved" if reward > 0 else "rejected",
    )


def store_lesson(
    agent: Any,
    context_events: List[str],
    action: str,
    reward: float,
    consequence: str = "lesson",
) -> Any:
    """Store ``context → action → consequence`` as an episode with a known outcome.

    A lesson is not necessarily the action of the latest step (a delayed
    verdict, a mentor's correction, imported history), so the body stores the
    episode itself and hands the outcome to the core like any embodied host:
    ``Agent._record_known_outcome`` writes the labile tag on the continuous
    reward and marks the episode for capture in the next sleep. Stable values
    change only in that sleep.
    """
    reward_v = max(-1.0, min(1.0, float(reward)))
    context = [str(token) for token in context_events or []]
    stored = _store_episode(
        agent,
        context,
        action,
        reward=reward_v,
        intensity=abs(reward_v),
        consequence=consequence,
    )
    if stored is None:
        return None
    record = getattr(agent, "_record_known_outcome", None)
    if callable(record):
        # Capture reads the action from the episode; sleep's habit update
        # keys the trace by the situation the lesson is about.
        stored.replay_action_id = str(action)
        stored.context_events = list(context)
        record(
            context_events=list(context),
            action_id=str(action),
            outcome=reward_v,
            episode=stored,
            intensity=float(getattr(stored, "intensity", abs(reward_v)) or abs(reward_v)),
        )
    return stored


def _store_episode(
    agent: Any,
    context_events: List[str],
    action: str,
    reward: float,
    intensity: float,
    consequence: str,
) -> Optional[Any]:
    hippocampus = getattr(agent, "hippocampus", None)
    store_fn = getattr(hippocampus, "store", None)
    if not callable(store_fn):
        return None

    path_cls, event_cls, event_type = load_experience_types()
    path = path_cls()
    for token in context_events or []:
        if str(token).startswith("action:"):
            continue
        path = path.add_event(event_cls(str(token), event_type.CONTEXT))
    action_name = str(action)
    if not action_name.startswith("action:"):
        action_name = f"action:{action_name}"
    path = path.add_event(event_cls(action_name, event_type.ACTION))
    consequence_event = event_cls(str(consequence), event_type.CONSEQUENCE)

    try:
        stored = store_fn(
            path,
            consequence=consequence_event,
            intensity=intensity,
            reward=reward,
        )
    except TypeError:
        try:
            stored = store_fn(path, consequence=consequence_event, intensity=intensity)
        except TypeError:
            try:
                stored = store_fn(path, consequence=consequence_event)
            except Exception:
                return None
        except Exception:
            return None
    except Exception:
        return None

    try:
        affective_space = getattr(agent, "affective_space", None)
        if stored is not None and affective_space is not None:
            create_trace = getattr(affective_space, "create_trace", None)
            if callable(create_trace):
                stored.emotional_trace = create_trace(intensity=min(1.0, abs(reward)))
    except Exception:
        pass
    return stored


def _record_bg_outcome(agent: Any, action_id: str, outcome: float) -> None:
    record_outcome = getattr(agent, "record_action_outcome", None)
    if callable(record_outcome):
        try:
            record_outcome(str(action_id), float(outcome))
        except Exception:
            pass


__all__ = [
    "UNJUDGED_INTENSITY",
    "WAIT_AND_MONITOR",
    "apply_feedback_to_agent",
    "approval_to_reward",
    "is_unjudged",
    "store_lesson",
    "_resolve_action_label",
]
