"""Strict host contract for the procurement sandbox (issue #58)."""

from __future__ import annotations

import logging

import pytest

from nowa_sandbox.training_loop import SandboxTrainer


@pytest.fixture(autouse=True)
def strict_learning(monkeypatch):
    monkeypatch.setenv("NOWA_STRICT_LEARNING", "1")
    import learning_guard

    raised = []
    original = learning_guard.WakingLearningError

    class CountingWakingLearningError(original):
        def __init__(self, *args):
            raised.append(" ".join(map(str, args)))
            super().__init__(*args)

    monkeypatch.setattr(learning_guard, "WakingLearningError", CountingWakingLearningError)
    yield
    if raised:
        pytest.fail("WakingLearningError was raised and caught: " + " | ".join(raised))


def _trainer(agent, encoder, fitness_evaluator, *, sleep_days=3):
    return SandboxTrainer(agent, encoder, fitness_evaluator, sleep_every_n_days=sleep_days)


def test_core_step_uses_one_simulated_day_without_wall_fallback(
    sandbox_agent, encoder, fitness_evaluator, caplog
):
    agent = sandbox_agent
    start = agent._host_clock_s
    trainer = _trainer(agent, encoder, fitness_evaluator)
    with caplog.at_level(logging.WARNING):
        for _ in range(3):
            trainer._agent_step(["event:stock_critical_low"], dt=86400)
    assert agent._host_clock_s - start == pytest.approx(3 * 86400)
    assert not getattr(agent, "_dt_warning_sent", False)
    assert "wall-clock" not in caplog.text.lower()


def test_sleep_schedule_sets_plasticity_interval_without_replacing_config(
    sandbox_agent, encoder, fitness_evaluator
):
    plasticity = sandbox_agent.plasticity
    original = plasticity
    custom_eta = plasticity.eta_labile_q
    _trainer(sandbox_agent, encoder, fitness_evaluator, sleep_days=5)
    assert sandbox_agent.plasticity is original
    assert sandbox_agent.sleep_manager.plasticity is plasticity
    assert sandbox_agent.sleep_manager.labile is sandbox_agent.labile
    assert plasticity.expected_wake_interval_s == 5 * 86400
    assert plasticity.eta_labile_q == custom_eta


def test_core_sleep_consolidates_known_waking_outcome(
    sandbox_agent, encoder, fitness_evaluator
):
    from learning_guard import labile_snapshot, stable_fingerprint

    agent = sandbox_agent
    trainer = _trainer(agent, encoder, fitness_evaluator)
    before = stable_fingerprint(agent)
    channels_before = {
        name: (channel.go_weight, channel.nogo_weight, channel.habit_strength)
        for name, channel in agent.bg_action_channels.items()
    }
    agent.step(["event:stock_critical_low"], reward=0.8, dt=86400)
    awake = stable_fingerprint(agent)
    assert awake == before
    assert labile_snapshot(agent)
    trainer._agent_sleep()
    assert stable_fingerprint(agent) != before
    assert agent.hippocampus.experiences
    assert any(
        (channel.go_weight, channel.nogo_weight, channel.habit_strength)
        != channels_before[name]
        for name, channel in agent.bg_action_channels.items()
    )


def test_real_order_known_reward_enters_labile_then_sleep_consolidates(
    sandbox_agent, encoder, fitness_evaluator
):
    from learning_guard import labile_snapshot, stable_fingerprint
    from nowa_sandbox.procurement_motor_adapter import OrderParams

    agent = sandbox_agent
    trainer = _trainer(agent, encoder, fitness_evaluator)
    before = stable_fingerprint(agent)
    context = ["event:stock_critical_low", "product:product_000"]
    params = OrderParams(
        supplier_id="supplier_000",
        product_id="product_000",
        qty=10.0,
        strategy="urgent_reorder",
        confidence=0.9,
    )
    trainer._store_order_experience(context, params, {"status": "accepted"})
    episode = agent.hippocampus.experiences[-1]
    assert episode.td_outcome_committed is True
    assert episode.td_committed_reward == pytest.approx(0.4)
    assert episode.replay_action_id == "urgent_reorder"
    assert episode.context_events == context
    assert labile_snapshot(agent)
    assert stable_fingerprint(agent) == before

    trainer._agent_sleep()
    assert stable_fingerprint(agent) != before
    assert episode.consolidated is True


def test_plain_stub_with_kwargs_advances_once_via_advance_time(
    encoder, fitness_evaluator
):
    class Stub:
        def __init__(self):
            self.advanced = []
            self.calls = 0

        def advance_time(self, dt):
            self.advanced.append(dt)

        def step(self, events, **kwargs):
            self.calls += 1
            assert "dt" not in kwargs
            return "wait_and_monitor"

    stub = Stub()
    trainer = _trainer(stub, encoder, fitness_evaluator)
    trainer._agent_step([], dt=86400)
    assert stub.advanced == [86400]
    assert stub.calls == 1


def test_agent_without_step_still_advances_its_host_clock(encoder, fitness_evaluator):
    class ClockOnly:
        def __init__(self):
            self.advanced = []

        def advance_time(self, dt):
            self.advanced.append(dt)

    agent = ClockOnly()
    _trainer(agent, encoder, fitness_evaluator)._agent_step([], dt=86400)
    assert agent.advanced == [86400]


def test_inner_typeerror_is_not_retried(encoder, fitness_evaluator):
    class Broken:
        def __init__(self):
            self.calls = 0

        def step(self, events, dt=None, decision_only=False):
            self.calls += 1
            raise TypeError("internal selector failure")

    agent = Broken()
    trainer = _trainer(agent, encoder, fitness_evaluator)
    with pytest.raises(TypeError, match="internal selector failure"):
        trainer._agent_step([], dt=86400)
    assert agent.calls == 1


def test_sleep_uses_agent_method_and_propagates_its_errors(encoder, fitness_evaluator):
    class AgentWithSleep:
        def __init__(self):
            self.slept = 0
            self.sleep_manager = type("Manager", (), {"sleep_cycle": lambda _self: None})()

        def sleep(self):
            self.slept += 1
            raise RuntimeError("sleep failed")

    agent = AgentWithSleep()
    trainer = _trainer(agent, encoder, fitness_evaluator)
    with pytest.raises(RuntimeError, match="sleep failed"):
        trainer._agent_sleep()
    assert agent.slept == 1


def test_legacy_stub_sleep_manager_fallback(encoder, fitness_evaluator):
    class Legacy:
        def __init__(self):
            self.cycles = []
            self.sleep_manager = type("Manager", (), {})()
            self.sleep_manager.sleep_cycle = lambda: self.cycles.append(1)

    agent = Legacy()
    _trainer(agent, encoder, fitness_evaluator)._agent_sleep()
    assert len(agent.cycles) == 1
