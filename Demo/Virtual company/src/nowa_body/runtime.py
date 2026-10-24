"""Employee runtime: the platform ``BusinessAgentRuntime`` with the employee's body rules.

The platform runtime (``mcp_body.runtime``) is used as is; this subclass adds
what the Virtual company employee needs on top of it, without changing the
core:

* outcomes are filed under the situation the mind decided in
  (``ContextualProposedAction.context_events``, ``feedback_loop``);
* ``teach`` files a lesson that is not the latest step (body lessons, a
  mentor, history) through ``feedback_loop.store_lesson``;
* a strict binding that finds nothing (``StrictSchemaBinder``) is filed as
  "here, waiting was right".

``_run_decision_cycle`` follows the platform one step by step; a change
there has to be mirrored here.

Deprecated host kwarg ``motor_adapter`` is ignored.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from ._compat import ensure_core_src_on_path

ensure_core_src_on_path()

from mcp_body._compat import apply_impulses  # noqa: E402
from mcp_body.mcp_capability import CapabilityRisk  # noqa: E402
from mcp_body.proposed_action import ProposedAction, new_action_id, summarize_call  # noqa: E402
from mcp_body.runtime import BIND_FAIL_IMPULSE_INTENSITY, WAIT_AND_MONITOR  # noqa: E402
from mcp_body.runtime import BusinessAgentRuntime as PlatformAgentRuntime  # noqa: E402

from .business_event_encoder import BusinessEventEncoder  # noqa: E402
from .feedback_loop import apply_feedback_to_agent, store_lesson  # noqa: E402
from .strict_binder import StrictSchemaBinder  # noqa: E402

# A WRITE intent whose strict binding finds nothing (the source the role
# binds from lists nothing to act on) is filed as "here, waiting was right".
STRICT_MISS_LESSON_REWARD = 0.5


@dataclass
class ContextualProposedAction(ProposedAction):
    # The situation the mind decided in; feedback files the outcome under it.
    context_events: List[str] = field(default_factory=list)


class BusinessAgentRuntime(PlatformAgentRuntime):
    """One ``run_cycle(observations)`` is observe → decide → bind → gate → feedback."""

    def __init__(
        self,
        agent: Any,
        tool_registry: Any,
        approval_gate: Any,
        encoder: Any = None,
        sleep_scheduler: Any = None,
        sensor_refresh_interval_s: float = 300.0,
        simulated_tick_seconds: Optional[float] = None,
        schema_binder: Any = None,
        param_bindings: Optional[Dict[str, Any]] = None,
        field_aliases: Optional[Dict[str, Any]] = None,
        event_classifier: Optional[Callable[..., Any]] = None,
        **host_compat: Any,
    ) -> None:
        super().__init__(
            agent,
            tool_registry,
            approval_gate,
            encoder=encoder or BusinessEventEncoder(),
            sleep_scheduler=sleep_scheduler,
            sensor_refresh_interval_s=sensor_refresh_interval_s,
            simulated_tick_seconds=simulated_tick_seconds,
            schema_binder=schema_binder or StrictSchemaBinder(),
            param_bindings=param_bindings,
            field_aliases=field_aliases,
            event_classifier=event_classifier,
            **host_compat,
        )

    def _run_decision_cycle(self, observations: Dict[str, Any]) -> dict:
        self._ingest_observations(observations)
        context_events, read_impulses = self._build_context(observations)
        apply_impulses(
            getattr(self.agent, "affective_space", None),
            read_impulses,
            source="external",
        )

        step_fn = getattr(self.agent, "step", None)
        if callable(step_fn):
            if self._accepts_decision_only(step_fn):
                action_intent = step_fn(context_events, decision_only=True)
            else:
                action_intent = step_fn(context_events)
        else:
            action_intent = WAIT_AND_MONITOR
        tool_id = self._intent_to_tool_id(action_intent)

        if tool_id == WAIT_AND_MONITOR or not tool_id:
            return {
                "action_type": WAIT_AND_MONITOR,
                "tool_id": WAIT_AND_MONITOR,
                "proposed": None,
                "slept": False,
                "context_events": context_events,
                "waited": True,
            }

        capability = self.tool_registry.get(tool_id)
        if capability is None or capability.risk_level == CapabilityRisk.READ_ONLY:
            return {
                "action_type": tool_id,
                "tool_id": tool_id,
                "proposed": None,
                "slept": False,
                "context_events": context_events,
                "waited": True,
            }

        weights = self._rank_weights()
        params = self.schema_binder.bind(
            capability,
            self.world_state,
            rank_weights=weights,
            hippocampus=getattr(self.agent, "hippocampus", None),
            param_bindings=self.param_bindings,
            field_aliases=self.field_aliases,
        )
        if params is None:
            strict_miss = getattr(self.schema_binder, "last_strict_miss", None)
            if strict_miss:
                self.teach(
                    context_events,
                    WAIT_AND_MONITOR,
                    STRICT_MISS_LESSON_REWARD,
                    consequence="nothing_to_bind",
                )
            apply_impulses(
                getattr(self.agent, "affective_space", None),
                {
                    "vector": {"curiosity": 0.4},
                    "intensity": BIND_FAIL_IMPULSE_INTENSITY,
                    "source": "internal",
                },
                source="internal",
            )
            return {
                "action_type": tool_id,
                "tool_id": tool_id,
                "proposed": None,
                "slept": False,
                "context_events": context_events,
                "waited": True,
                "bind_failed": True,
                "strict_miss": strict_miss or "",
            }

        proposed = ContextualProposedAction(
            action_id=new_action_id(),
            agent_id=self._agent_id(observations),
            tool_id=capability.tool_id,
            tool_params=dict(params),
            risk_level=capability.risk_level,
            intent_summary=summarize_call(capability.tool_id, params),
            affective_context=self._affect_snapshot(),
            estimated_cost_impact=None,
            requires_approval=bool(capability.requires_approval),
            context_events=[str(token) for token in context_events or []],
        )
        record = self.approval_gate.route(proposed)
        if record.executed:
            self._apply_feedback(record)
        return {
            "action_type": tool_id,
            "tool_id": tool_id,
            "proposed": proposed,
            "approval_status": record.status.value,
            "executed": bool(record.executed),
            "record": record,
            "slept": False,
            "context_events": context_events,
            "waited": False,
        }

    def _apply_feedback(self, record: Any) -> None:
        apply_feedback_to_agent(self.agent, record, self.encoder)

    def teach(
        self,
        context_events: List[str],
        action: str,
        reward: float,
        consequence: str = "lesson",
    ) -> Any:
        """File one lesson ``context → action → reward`` from a mentor or history.

        Same storage path as approval feedback: the episode carries the
        situation, the action and a TD tag, so sleep can consolidate it.
        """
        return store_lesson(
            self.agent,
            list(context_events or []),
            str(action or WAIT_AND_MONITOR),
            float(reward),
            consequence=consequence,
        )


__all__ = [
    "WAIT_AND_MONITOR",
    "BusinessAgentRuntime",
    "ContextualProposedAction",
    "STRICT_MISS_LESSON_REWARD",
]
