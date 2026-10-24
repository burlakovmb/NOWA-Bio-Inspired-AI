"""Regression tests for the procurement-training fixes (docs_VC/05).

Each class pins one break in the chain "seeded profession → live decision →
feedback → sleep": classifier events, decision context in feedback, honest
rewards, strict parameter bindings, recall of the closest lesson, seeds through sleep
and the employee memory half-life.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mcp_body.approval_gate import ApprovalRecord, ApprovalStatus
from mcp_body.mcp_capability import CapabilityRisk, MCPCapability
from mcp_body.world_state import WorldState
from nowa_body.business_event_encoder import BusinessEventEncoder
from nowa_body.employee_config import employee_config_from_mapping, employee_config_to_mapping
from nowa_body.employee_session import spawn_employee_agent
from nowa_body.feedback_loop import UNJUDGED_INTENSITY, apply_feedback_to_agent, approval_to_reward
from nowa_body.role_config import build_seeder, load_role_config
from nowa_body.runtime import ContextualProposedAction
from nowa_body.strict_binder import StrictSchemaBinder
from nowa_roles.procurement.event_classifier import classify_procurement_events

ORDER = "mcp__drivemcp__create_purchase_order"
WAIT = "wait_and_monitor"
PROCUREMENT_CONFIG = str(
    Path(__file__).resolve().parents[1] / "src" / "nowa_roles" / "procurement" / "config.yaml"
)


def _stock(qty, reorder=100, inbound=0.0):
    return {"status": "ok", "stock": {"sku-a": {
        "quantity": qty, "reorder_point": reorder, "below_reorder_point": qty < reorder,
        "inbound": inbound, "projected_quantity": qty + inbound}}}


def _actions(exp):
    return [e.name for e in exp.path.events if e.event_type.value == "action"]


def _record(status, decided_by="supervisor", context=("event:stock_ok",)):
    proposed = ContextualProposedAction(
        action_id="a-1", agent_id="buyer", tool_id=ORDER,
        tool_params={"sku": "sku-a", "qty": 10, "supplier_id": "sup-1"},
        risk_level=CapabilityRisk.MEDIUM_WRITE, intent_summary=ORDER,
        context_events=list(context),
    )
    return ApprovalRecord(
        proposed_action=proposed, status=status, submitted_at=0.0, decided_at=0.0,
        decided_by=decided_by, executed=status != ApprovalStatus.REJECTED,
        execution_result={"status": "accepted"} if status != ApprovalStatus.REJECTED else None,
    )


class TestClassifier:

    def test_uncovered_deficit_is_critical(self):
        assert classify_procurement_events("mcp__x__get_stock_levels", _stock(5)) == ["stock_critical_low"]

    def test_inbound_cover_is_not_critical(self):
        assert classify_procurement_events(
            "mcp__x__get_stock_levels", _stock(5, inbound=200)
        ) == ["stock_low_covered"]

    def test_healthy_stock_is_named(self):
        assert classify_procurement_events("mcp__x__get_stock_levels", _stock(500)) == ["stock_ok"]

    def test_read_ok_is_not_a_deal(self):
        events = classify_procurement_events("mcp__x__get_budget", {"status": "ok", "remaining": 50.0})
        assert "deal_closed_favorable" not in events
        assert events == []

    def test_accepted_write_is_a_deal(self):
        events = classify_procurement_events(ORDER, {"status": "accepted", "document_number": "PO-1"})
        assert events == ["deal_closed_favorable"]


class TestFeedback:

    def test_unjudged_execution_is_not_a_reward(self):
        record = _record(ApprovalStatus.APPROVED, decided_by="system:read_only_auto")
        assert approval_to_reward(record) == 0.0

    def test_human_approval_keeps_full_reward(self):
        assert approval_to_reward(_record(ApprovalStatus.APPROVED)) == 1.0

    def test_approval_is_filed_under_decision_context_and_tagged(self):
        agent = spawn_employee_agent("buyer")
        apply_feedback_to_agent(agent, _record(ApprovalStatus.APPROVED), BusinessEventEncoder())
        stored = agent.hippocampus.experiences[-1]
        assert "event:stock_ok" in set(stored.path.signature())
        assert _actions(stored) == [f"action:{ORDER}"]
        # A known outcome on the continuous scale, marked for sleep capture.
        assert stored.td_outcome_committed is True
        assert stored.td_committed_reward == 1.0
        assert abs(float(stored.td_error_snapshot)) > 0.0

    def test_rejection_is_a_lesson_to_wait(self):
        agent = spawn_employee_agent("buyer")
        apply_feedback_to_agent(agent, _record(ApprovalStatus.REJECTED), BusinessEventEncoder())
        stored = agent.hippocampus.experiences[-1]
        assert _actions(stored) == [f"action:{WAIT}"]
        assert "event:stock_ok" in set(stored.path.signature())
        assert float(stored.reward) > 0.0

    def test_unjudged_execution_is_faint(self):
        agent = spawn_employee_agent("buyer")
        record = _record(ApprovalStatus.APPROVED, decided_by="system:read_only_auto")
        apply_feedback_to_agent(agent, record, BusinessEventEncoder())
        stored = agent.hippocampus.experiences[-1]
        assert float(stored.intensity) == pytest.approx(UNJUDGED_INTENSITY)


class TestStrictBinding:

    @staticmethod
    def _capability():
        return MCPCapability(
            tool_id=ORDER, server_name="drivemcp", display_name="po", description="WRITE",
            risk_level=CapabilityRisk.MEDIUM_WRITE, domain_tags=["procurement"],
            requires_approval=False,
            input_schema={"type": "object", "required": ["sku", "qty"],
                          "properties": {"sku": {"type": "string"}, "qty": {"type": "number"}}},
        )

    BINDINGS = {"sku": {"path": "entities.items.0.id", "strict": True},
                "qty": {"path": "entities.items.0.suggested_qty", "strict": True}}

    def test_binds_from_the_replenishment_list(self):
        world = WorldState()
        world.update_from_read("mcp__x__get_stock_levels", _stock(500))
        world.update_from_read("mcp__x__get_replenishment_needs", {
            "status": "ok", "items": {"sku-b": {"suggested_qty": 40}}})
        params = StrictSchemaBinder().bind(self._capability(), world, param_bindings=self.BINDINGS)
        assert params == {"sku": "sku-b", "qty": 40}

    def test_empty_list_does_not_fall_back_to_guessing(self):
        world = WorldState()
        world.update_from_read("mcp__x__get_stock_levels", _stock(500))
        world.update_from_read("mcp__x__get_replenishment_needs", {"status": "ok", "items": {}})
        binder = StrictSchemaBinder()
        assert binder.bind(self._capability(), world, param_bindings=self.BINDINGS) is None
        assert binder.last_strict_miss == "sku"


class TestRecallWeighting:

    def test_closest_lesson_outweighs_partial_matches(self):
        agent = spawn_employee_agent("buyer")
        build_seeder(load_role_config(PROCUREMENT_CONFIG)).seed_agent(agent)
        context = ["event:stock_low_covered", "valence:neutral", "domain:procurement"]
        exps = agent.hippocampus.activate(context)
        pressure = agent.selector.compute_pressures(exps, [])
        assert pressure.get(WAIT, 0.0) > pressure.get(ORDER, 0.0)


class TestSeedsThroughSleep:

    def test_role_seeds_are_consolidated_by_the_first_sleep(self):
        """Seeds are ordinary episodes: the night moves them into the cortex."""
        agent = spawn_employee_agent("buyer")
        config = load_role_config(PROCUREMENT_CONFIG)
        build_seeder(config).seed_agent(agent)
        assert all(float(getattr(ep, "stability", 0.0)) < 1.0 for ep in agent.hippocampus.experiences)
        before = len(agent.cortex.patterns)
        agent.sleep(cycles=1)
        assert len(agent.cortex.patterns) > before
        assert len(agent.hippocampus.experiences) >= len(config.seed_corpus) - 1


class TestRoleAndEmployeeConfig:

    def test_procurement_role_uses_events_only(self):
        config = load_role_config(PROCUREMENT_CONFIG)
        assert config.token_rules.get("generic_tokens") is False
        assert config.event_classifier_paths

    def test_generic_tokens_can_be_switched_off(self):
        world = WorldState()
        world.update_from_read("mcp__x__get_stock_levels", _stock(5))
        mapping = {"stock_critical_low": {"valence": -0.7, "arousal": 0.8, "tags": ["procurement"]}}
        tokens, _ = BusinessEventEncoder(mapping, token_rules={"generic_tokens": False}).encode(
            world, extra_events=["stock_critical_low"])
        assert tokens and all(not t.startswith(("tool:", "status:", "field:", "entity:")) for t in tokens)
        assert "event:stock_critical_low" in tokens

    def test_memory_half_life_round_trips(self, tmp_path):
        raw = {"agent_id": "buyer", "role_ids": ["procurement"], "memory_half_life_s": 86400}
        config = employee_config_from_mapping(raw, str(tmp_path / "employee.yaml"))
        assert config.memory_half_life_s == 86400.0
        assert employee_config_to_mapping(config)["memory_half_life_s"] == 86400.0

    def test_memory_half_life_defaults_to_core(self, tmp_path):
        raw = {"agent_id": "buyer", "role_ids": ["procurement"]}
        config = employee_config_from_mapping(raw, str(tmp_path / "employee.yaml"))
        assert config.memory_half_life_s is None
        assert yaml.safe_dump(employee_config_to_mapping(config))
