"""Body lessons: outcomes filed under the situation, through the two-tier core.

``store_lesson`` / ``BusinessAgentRuntime.teach``, approval feedback filed
under ``ContextualProposedAction.context_events``, strict ``param_bindings``
and ``token_rules.generic_tokens``. Domain-free: any role, any MCP server;
the platform ``mcp_body`` is used unchanged.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent_factory import AgentConfig, AgentFactory
from learning_guard import labile_snapshot, stable_fingerprint
from mcp_body import (
    ApprovalGate,
    CapabilityRisk,
    MCPCapability,
    MCPToolRegistry,
    WAIT_AND_MONITOR,
    WorldState,
)
from mcp_body.approval_gate import ApprovalRecord, ApprovalStatus
from nowa_body.business_event_encoder import BusinessEventEncoder
from nowa_body.feedback_loop import UNJUDGED_INTENSITY, apply_feedback_to_agent, store_lesson
from nowa_body.runtime import STRICT_MISS_LESSON_REWARD, BusinessAgentRuntime, ContextualProposedAction
from nowa_body.strict_binder import StrictSchemaBinder

WRITE = "mcp__desk__reserve_slot"
READ = "mcp__desk__get_queue"
CONTEXT = ["event:queue_full", "domain:desk"]


@pytest.fixture(autouse=True)
def strict_learning(monkeypatch):
    """A stable write while awake raises instead of being skipped."""
    monkeypatch.setenv("NOWA_STRICT_LEARNING", "1")


def _agent():
    return AgentFactory(AgentConfig(actions=[WAIT_AND_MONITOR])).spawn_default(agent_id="clerk")


def _names(episode):
    return [getattr(event, "name", "") for event in episode.path.events]


def _write_schema():
    return {
        "type": "object",
        "required": ["slot_id", "count"],
        "properties": {"slot_id": {"type": "string"}, "count": {"type": "number"}},
    }


def _capability(**overrides):
    params = dict(
        tool_id=WRITE,
        server_name="desk",
        display_name="Reserve slot",
        description="WRITE reservation",
        risk_level=CapabilityRisk.LOW_WRITE,
        requires_approval=False,
        input_schema=_write_schema(),
    )
    params.update(overrides)
    return MCPCapability(**params)


STRICT_BINDINGS = {
    "slot_id": {"path": "entities.items.0.id", "strict": True},
    "count": {"path": "entities.items.0.suggested", "strict": True},
}


def _world_with_free_slots():
    world = WorldState()
    world.update_from_read(READ, {"status": "ok", "slots": {"S1": {"count": 4.0}}})
    return world


def _record(status, decided_by="supervisor", context=tuple(CONTEXT)):
    proposed = ContextualProposedAction(
        action_id="a-1", agent_id="clerk", tool_id=WRITE,
        tool_params={"slot_id": "S1", "count": 2},
        risk_level=CapabilityRisk.LOW_WRITE, intent_summary=WRITE,
        context_events=list(context),
    )
    executed = status != ApprovalStatus.REJECTED
    return ApprovalRecord(
        proposed_action=proposed, status=status, submitted_at=0.0, decided_at=0.0,
        decided_by=decided_by, executed=executed,
        execution_result={"status": "accepted"} if executed else None,
    )


class _ActingAgent:
    """Minimal agent: always proposes the WRITE, stores episodes."""

    def __init__(self):
        self.hippocampus = SimpleNamespace(experiences=[], store=self._store)
        self.selector = SimpleNamespace(actions=[])
        self.affective_space = None
        self.agent_id = "clerk"

    def _store(self, path, consequence=None, intensity=1.0, reward=0.0, **_kwargs):
        episode = SimpleNamespace(path=path, consequence=consequence, intensity=intensity, reward=reward)
        self.hippocampus.experiences.append(episode)
        return episode

    def step(self, events, decision_only=True):
        return WRITE

    def register_action_channel(self, *args, **kwargs):
        return None


def _runtime(agent=None, **kwargs):
    registry = MCPToolRegistry("clerk")
    registry.register(_capability())
    return BusinessAgentRuntime(
        agent=agent or _ActingAgent(),
        tool_registry=registry,
        approval_gate=ApprovalGate(mcp_executor=lambda *_a, **_k: {"status": "accepted"},
                                   capability_lookup=registry.get),
        encoder=BusinessEventEncoder(),
        **kwargs,
    )


class TestStoreLesson:

    def test_files_context_action_and_consequence(self):
        agent = _agent()
        episode = store_lesson(agent, CONTEXT, WRITE, 0.7, consequence="slot_reserved")
        names = _names(episode)
        assert "event:queue_full" in names and f"action:{WRITE}" in names
        assert episode.reward == pytest.approx(0.7)
        assert episode.intensity == pytest.approx(0.7)
        assert getattr(episode.consequence, "name", "") == "slot_reserved"

    def test_outcome_goes_to_the_labile_tier_only(self):
        agent = _agent()
        before = stable_fingerprint(agent)
        episode = store_lesson(agent, CONTEXT, WRITE, 0.7)
        assert stable_fingerprint(agent) == before
        assert labile_snapshot(agent)
        assert episode.td_outcome_committed is True
        assert episode.td_committed_reward == pytest.approx(0.7)

    def test_reward_is_continuous_and_clamped(self):
        agent = _agent()
        assert store_lesson(agent, CONTEXT, WRITE, 0.35).td_committed_reward == pytest.approx(0.35)
        assert store_lesson(agent, CONTEXT, WRITE, 3.0).reward == pytest.approx(1.0)
        assert store_lesson(agent, CONTEXT, WRITE, -3.0).reward == pytest.approx(-1.0)

    def test_agent_without_a_two_tier_core_still_stores(self):
        agent = _ActingAgent()
        episode = store_lesson(agent, CONTEXT, WAIT_AND_MONITOR, 0.5)
        assert episode is agent.hippocampus.experiences[-1]
        assert f"action:{WAIT_AND_MONITOR}" in _names(episode)

    def test_agent_without_memory_gets_none(self):
        assert store_lesson(SimpleNamespace(), CONTEXT, WRITE, 0.5) is None

    def test_runtime_teach_is_the_same_path(self):
        agent = _agent()
        runtime = _runtime(agent=agent)
        episode = runtime.teach(CONTEXT, WAIT_AND_MONITOR, 0.6, consequence="mentor")
        assert f"action:{WAIT_AND_MONITOR}" in _names(episode)
        assert episode.td_outcome_committed is True


class TestApprovalFeedback:

    def test_approval_is_filed_under_the_decision_context(self):
        agent = _agent()
        apply_feedback_to_agent(agent, _record(ApprovalStatus.APPROVED), BusinessEventEncoder())
        episode = agent.hippocampus.experiences[-1]
        names = _names(episode)
        assert "event:queue_full" in names and f"action:{WRITE}" in names
        assert episode.reward == pytest.approx(1.0)
        assert episode.td_outcome_committed is True

    def test_rejection_is_a_lesson_to_wait(self):
        agent = _agent()
        apply_feedback_to_agent(agent, _record(ApprovalStatus.REJECTED), BusinessEventEncoder())
        episode = agent.hippocampus.experiences[-1]
        names = _names(episode)
        assert f"action:{WAIT_AND_MONITOR}" in names and f"action:{WRITE}" not in names
        assert episode.reward > 0.0
        assert getattr(episode.consequence, "name", "") == "call_rejected"

    def test_unjudged_execution_is_faint_and_unrewarded(self):
        agent = _agent()
        record = _record(ApprovalStatus.APPROVED, decided_by="system:read_only_auto")
        apply_feedback_to_agent(agent, record, BusinessEventEncoder())
        episode = agent.hippocampus.experiences[-1]
        assert episode.intensity == pytest.approx(UNJUDGED_INTENSITY)
        assert episode.reward == pytest.approx(0.0)
        assert not getattr(episode, "td_outcome_committed", False)


class TestStrictBindings:

    def test_strict_binding_does_not_guess(self):
        binder = StrictSchemaBinder()
        params = binder.bind(_capability(), _world_with_free_slots(), param_bindings=STRICT_BINDINGS)
        assert params is None
        assert binder.last_strict_miss == "slot_id"

    def test_without_strict_the_binder_still_guesses(self):
        loose = {name: {"path": spec["path"]} for name, spec in STRICT_BINDINGS.items()}
        binder = StrictSchemaBinder()
        params = binder.bind(_capability(), _world_with_free_slots(), param_bindings=loose)
        assert params is not None and params["slot_id"] == "S1"
        assert binder.last_strict_miss is None

    def test_strict_binding_reads_its_path(self):
        world = _world_with_free_slots()
        world.update_from_read(READ, {"status": "ok", "items": [{"id": "S9", "suggested": 3}]})
        params = StrictSchemaBinder().bind(_capability(), world, param_bindings=STRICT_BINDINGS)
        assert params == {"slot_id": "S9", "count": 3}

    def test_runtime_files_waiting_was_right_on_a_strict_miss(self):
        runtime = _runtime(param_bindings=STRICT_BINDINGS)
        result = runtime.run_cycle({"tool_results": {READ: {"status": "ok", "slots": {"S1": {"count": 4.0}}}}})
        assert result["bind_failed"] is True and result["strict_miss"] == "slot_id"
        episode = runtime.agent.hippocampus.experiences[-1]
        assert f"action:{WAIT_AND_MONITOR}" in _names(episode)
        assert episode.reward == pytest.approx(STRICT_MISS_LESSON_REWARD)
        assert getattr(episode.consequence, "name", "") == "nothing_to_bind"


class TestGenericTokens:

    MAPPING = {"queue_full": {"valence": -0.4, "arousal": 0.6, "tags": ["desk"]}}
    RESULTS = {READ: {"status": "ok", "state": "queue_full", "slots": {"S1": {"count": 4.0}}}}

    def _tokens(self, **rules):
        world = WorldState()
        world.update_from_read(READ, self.RESULTS[READ])
        encoder = BusinessEventEncoder(affective_mapping=self.MAPPING, token_rules=rules)
        tokens, _impulses = encoder.encode(world, self.RESULTS)
        return tokens

    def test_default_keeps_generic_tokens(self):
        tokens = self._tokens()
        assert any(token.startswith(("tool:", "status:", "field:", "entity:")) for token in tokens)
        assert "event:queue_full" in tokens

    def test_off_keeps_only_named_events(self):
        tokens = self._tokens(generic_tokens=False)
        assert "event:queue_full" in tokens
        assert not any(token.startswith(("tool:", "status:", "field:", "entity:")) for token in tokens)
