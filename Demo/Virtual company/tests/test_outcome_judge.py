"""Delayed consequences: the procurement outcome judge and its runtime hook.

Once nobody reviews orders, the world is the teacher: a delivery that lifts
the position back above its reorder point rewards the order the buyer placed
alone, an empty shelf the buyer waited on teaches "here, order".
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from body_support import make_test_runtime

from mcp_body.approval_gate import ApprovalRecord, ApprovalStatus
from mcp_body.mcp_capability import CapabilityRisk
from nowa_body.runtime import ContextualProposedAction as ProposedAction
from nowa_body.role_config import build_outcome_judge, load_role_config
from nowa_roles.procurement.outcome_judge import (
    MISSED_STOCKOUT_REWARD,
    ORDER_LATE_REWARD,
    ORDER_PAID_OFF_REWARD,
    ProcurementOutcomeJudge,
)

ORDER = "mcp__drivemcp__create_purchase_order"
WAIT = "wait_and_monitor"
T0 = datetime(2026, 10, 5, 8, 0, 0)
CRIT = ["event:stock_critical_low"]
PROCUREMENT_CONFIG = str(
    Path(__file__).resolve().parents[1] / "src" / "nowa_roles" / "procurement" / "config.yaml"
)


def _obs(qty, reorder=100, inbound=0.0, remaining=5000.0):
    return {"tool_results": {
        "mcp__drivemcp__get_stock_levels": {"status": "ok", "stock": {"sku-a": {
            "quantity": qty, "reorder_point": reorder, "below_reorder_point": qty < reorder,
            "inbound": inbound, "projected_quantity": qty + inbound}}},
        "mcp__drivemcp__get_budget": {"status": "ok", "remaining": remaining},
    }}


def _executed(decided_by="system:read_only_auto", status="accepted"):
    proposed = ProposedAction(
        action_id="a-1", agent_id="buyer", tool_id=ORDER,
        tool_params={"sku": "sku-a", "qty": 200, "supplier_id": "sup-1"},
        risk_level=CapabilityRisk.MEDIUM_WRITE, intent_summary=ORDER, context_events=CRIT,
    )
    record = ApprovalRecord(
        proposed_action=proposed, status=ApprovalStatus.APPROVED, submitted_at=0.0,
        decided_at=0.0, decided_by=decided_by, executed=True,
        execution_result={"status": status, "document_number": "PO-1"} if status == "accepted"
        else {"status": status},
    )
    return {"tool_id": ORDER, "executed": True, "record": record, "context_events": CRIT}


def _wait(context=CRIT):
    return {"tool_id": WAIT, "waited": True, "context_events": list(context)}


class TestOrderConsequences:
    def test_delivery_that_closes_the_deficit_rewards_the_order(self):
        judge = ProcurementOutcomeJudge()
        assert judge.observe(_obs(40), _executed(), T0) == []
        assert judge.observe(_obs(30, inbound=200), _wait(["event:stock_low_covered"]), T0 + timedelta(days=1)) == []
        lessons = judge.observe(_obs(230), _wait(["event:stock_ok"]), T0 + timedelta(days=3))
        assert lessons == [(CRIT, ORDER, ORDER_PAID_OFF_REWARD, "order_paid_off")]
        assert judge.open_orders == []

    def test_shelf_empty_before_delivery_rewards_less(self):
        judge = ProcurementOutcomeJudge()
        judge.observe(_obs(40), _executed(), T0)
        judge.observe(_obs(0, inbound=200), _wait(), T0 + timedelta(days=2))
        lessons = judge.observe(_obs(200), _wait(), T0 + timedelta(days=3))
        assert lessons == [(CRIT, ORDER, ORDER_LATE_REWARD, "order_arrived_late")]

    def test_budget_is_not_judged(self):
        # The body's budget limit keeps such orders out of the ERP; if one
        # got through, it is still judged by its delivery, not by money.
        judge = ProcurementOutcomeJudge()
        assert judge.observe(_obs(40, remaining=0.0), _executed(), T0) == []
        assert [order["sku"] for order in judge.open_orders] == ["sku-a"]

    def test_person_approved_orders_are_left_to_the_person(self):
        judge = ProcurementOutcomeJudge()
        judge.observe(_obs(40), _executed(decided_by="supervisor"), T0)
        assert judge.open_orders == []

    def test_failed_write_is_not_tracked(self):
        judge = ProcurementOutcomeJudge()
        judge.observe(_obs(40), _executed(status="error"), T0)
        assert judge.open_orders == []

    def test_undelivered_order_expires_without_a_lesson(self):
        judge = ProcurementOutcomeJudge(horizon=timedelta(days=2))
        judge.observe(_obs(40), _executed(), T0)
        assert judge.observe(_obs(40), _wait(), T0 + timedelta(days=3)) == []
        assert judge.open_orders == []


class TestMissedStockout:
    def test_empty_shelf_after_waiting_on_the_deficit_teaches_order(self):
        judge = ProcurementOutcomeJudge()
        judge.observe(_obs(40), _wait(), T0)
        lessons = judge.observe(_obs(0), _wait(["event:stock_ok"]), T0 + timedelta(hours=8))
        assert lessons == [(CRIT, ORDER, MISSED_STOCKOUT_REWARD, "missed_stockout")]
        # one lesson per stockout, not one per tick
        assert judge.observe(_obs(0), _wait(), T0 + timedelta(hours=9)) == []

    def test_no_lesson_without_money(self):
        judge = ProcurementOutcomeJudge()
        judge.observe(_obs(40, remaining=0.0), _wait(), T0)
        assert judge.observe(_obs(0, remaining=0.0), _wait(), T0 + timedelta(hours=8)) == []

    def test_small_change_on_the_budget_is_not_money(self):
        judge = ProcurementOutcomeJudge()
        obs = _obs(40, remaining=6.0)
        obs["tool_results"]["mcp__drivemcp__get_suppliers"] = {
            "status": "ok", "suppliers": {"sup-1": {"unit_price": 10.0}}}
        judge.observe(obs, _wait(), T0)
        later = _obs(0, remaining=6.0)
        later["tool_results"]["mcp__drivemcp__get_suppliers"] = obs["tool_results"]["mcp__drivemcp__get_suppliers"]
        assert judge.observe(later, _wait(), T0 + timedelta(hours=8)) == []

    def test_no_lesson_when_a_delivery_is_on_its_way(self):
        judge = ProcurementOutcomeJudge()
        judge.observe(_obs(40), _wait(), T0)
        assert judge.observe(_obs(0, inbound=200), _wait(), T0 + timedelta(hours=8)) == []

    def test_no_lesson_when_the_buyer_never_saw_the_deficit(self):
        judge = ProcurementOutcomeJudge()
        assert judge.observe(_obs(0), {"tool_id": ORDER, "bind_failed": True}, T0) == []


class _FixedJudge:
    def __init__(self, lessons):
        self.lessons = lessons
        self.calls = 0

    def observe(self, observations, result, now):
        self.calls += 1
        return self.lessons


class TestRuntimeHook:
    def test_runtime_files_judge_lessons_as_episodes(self):
        runtime = make_test_runtime()
        runtime.outcome_judge = _FixedJudge([(CRIT, ORDER, 0.6, "order_paid_off")])
        before = len(runtime.agent.hippocampus.experiences)
        result = runtime.run_cycle({"tool_results": {}}, now=T0)
        assert result["lessons"] == ["order_paid_off"]
        stored = runtime.agent.hippocampus.experiences[before:]
        assert any(getattr(e.consequence, "name", "") == "order_paid_off" for e in stored)

    def test_broken_judge_does_not_break_the_cycle(self):
        class Broken:
            def observe(self, *_a):
                raise RuntimeError("boom")

        runtime = make_test_runtime()
        runtime.outcome_judge = Broken()
        result = runtime.run_cycle({"tool_results": {}}, now=T0)
        assert "lessons" not in result


class TestRoleWiring:
    def test_procurement_role_ships_without_a_judge(self):
        # The budget is a body rule; the judge stays available but off.
        assert build_outcome_judge(load_role_config(PROCUREMENT_CONFIG)) is None

    def test_role_that_names_the_judge_builds_it(self, tmp_path):
        import yaml

        raw = yaml.safe_load(Path(PROCUREMENT_CONFIG).read_text(encoding="utf-8"))
        raw["outcome_judge"] = "nowa_roles.procurement.outcome_judge:ProcurementOutcomeJudge"
        path = tmp_path / "config.yaml"
        path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
        assert isinstance(build_outcome_judge(load_role_config(str(path))), ProcurementOutcomeJudge)
