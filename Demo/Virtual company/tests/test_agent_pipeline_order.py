"""Pipeline order and B7/B8/B9 constraints (spec §11, patch v1.1 §2)."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

from nowa_body.approval_gate import ApprovalStatus
from nowa_body.mcp_capability import CapabilityRisk

from body_support import (
    make_test_agent,
    make_test_agent_that_always_acts,
    make_test_runtime,
)


def test_runtime_calls_step_before_bind():
    agent = make_test_agent_that_always_acts()
    runtime = make_test_runtime(agent=agent)
    call_order = []
    original_step = agent.step
    original_bind = runtime.schema_binder.bind

    def tracked_step(*args, **kwargs):
        call_order.append("agent.step")
        return original_step(*args, **kwargs)

    def tracked_bind(*args, **kwargs):
        call_order.append("schema_binder.bind")
        return original_bind(*args, **kwargs)

    agent.step = tracked_step
    runtime.schema_binder.bind = tracked_bind
    runtime.run_cycle({"tool_results": {}, "agent_id": "a"})
    assert call_order == ["agent.step", "schema_binder.bind"]


def test_runtime_passes_decision_only_true():
    agent = make_test_agent_that_always_acts()
    runtime = make_test_runtime(agent=agent)
    runtime.run_cycle({"tool_results": {}, "agent_id": "a"})
    assert agent.step_calls
    assert agent.step_calls[0]["decision_only"] is True


def test_feedback_applied_only_after_real_execution(monkeypatch):
    """B7: apply_feedback_to_agent must not run before record.executed."""
    calls = []

    def _capture(agent, record, encoder):
        calls.append(record.executed)

    monkeypatch.setattr("nowa_body.runtime.apply_feedback_to_agent", _capture)

    executed_agent = make_test_agent_that_always_acts()
    executed_runtime = make_test_runtime(
        agent=executed_agent, requires_approval=False
    )
    executed_runtime.run_cycle({"tool_results": {}, "agent_id": "a"})
    assert calls == [True]

    calls.clear()
    pending_agent = make_test_agent_that_always_acts()
    pending_runtime = make_test_runtime(
        agent=pending_agent,
        requires_approval=True,
        risk_level=CapabilityRisk.MEDIUM_WRITE,
    )
    pending_runtime.run_cycle({"tool_results": {}, "agent_id": "a"})
    assert calls == []


def test_human_reject_does_not_execute_but_records_feedback_after_decision():
    agent = make_test_agent_that_always_acts()
    runtime = make_test_runtime(
        agent=agent,
        requires_approval=True,
        risk_level=CapabilityRisk.MEDIUM_WRITE,
    )
    n_before = len(agent.hippocampus.experiences)
    result = runtime.run_cycle({"tool_results": {}, "agent_id": "a"})
    assert result["approval_status"] == ApprovalStatus.PENDING.value
    assert n_before == len(agent.hippocampus.experiences)
    record = runtime.complete_approval(
        result["proposed"].action_id,
        ApprovalStatus.REJECTED,
        decided_by="boss",
        rejection_reason="no",
    )
    assert record.executed is False
    assert len(agent.hippocampus.experiences) == n_before + 1


class TestTickSensorCaching:
    def test_sensor_fetcher_not_called_every_tick(self):
        runtime = make_test_runtime(sensor_refresh_interval_s=300.0)
        fetcher = MagicMock(return_value={"tool_results": {}})
        for _ in range(10):
            runtime.tick(fetcher)
        assert fetcher.call_count == 1  # only the first tick refreshes

    def test_sensor_fetcher_called_after_interval_elapses(self):
        runtime = make_test_runtime(sensor_refresh_interval_s=0.0)
        fetcher = MagicMock(return_value={"tool_results": {}})
        runtime.tick(fetcher)
        runtime.tick(fetcher)
        assert fetcher.call_count == 2  # zero interval => refresh every tick

    def test_sensor_fetcher_called_when_interval_passes(self):
        runtime = make_test_runtime(sensor_refresh_interval_s=60.0)
        fetcher = MagicMock(return_value={"tool_results": {}})
        t0 = datetime(2026, 1, 1, 12, 0, 0)
        runtime.tick(fetcher, now=t0)
        runtime.tick(fetcher, now=t0 + timedelta(seconds=30))
        assert fetcher.call_count == 1
        runtime.tick(fetcher, now=t0 + timedelta(seconds=60))
        assert fetcher.call_count == 2

    def test_wait_and_monitor_does_not_store_episode(self):
        """B8: quiet ticks must not flood the hippocampus."""
        agent = make_test_agent()
        runtime = make_test_runtime(agent=agent)
        n_before = len(agent.hippocampus.experiences)
        for _ in range(100):
            runtime.run_cycle({"tool_results": {}})  # yields wait_and_monitor
        n_after = len(agent.hippocampus.experiences)
        assert n_after == n_before

    def test_action_tick_does_store_episode(self):
        agent = make_test_agent_that_always_acts()
        runtime = make_test_runtime(agent=agent)
        n_before = len(agent.hippocampus.experiences)
        runtime.run_cycle({"tool_results": {"mcp__x__y": {"status": "urgent"}}})
        n_after = len(agent.hippocampus.experiences)
        assert n_after > n_before
