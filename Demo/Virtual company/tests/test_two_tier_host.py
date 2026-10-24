"""Virtual company host contract for two-tier plasticity (issue #13).

The employee runtime passes host time as ``dt``, tells the core how long the
employee stays awake between sleeps, files lessons into the labile tier only,
and consolidates through ``Agent.sleep``.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from body_support import make_test_runtime

from nowa_body.feedback_loop import store_lesson
from nowa_body.employee_session import spawn_employee_agent
from nowa_body.sleep_scheduler import SleepScheduler, configure_plasticity

DAY = datetime(2026, 10, 5, 9, 0, 0)  # Monday 09:00, outside the sleep window
NIGHT = datetime(2026, 10, 6, 3, 0, 0)
TICK = timedelta(minutes=15)
ORDER = "mcp__test__do"
CONTEXT = ["event:stock_critical_low"]


@pytest.fixture(autouse=True)
def fail_if_waking_learning_error_was_caught(monkeypatch):
    """Strict mode. A swallowed ``WakingLearningError`` fails the test."""
    monkeypatch.setenv("NOWA_STRICT_LEARNING", "1")
    import learning_guard

    raised: list = []
    original = learning_guard.WakingLearningError

    class _CountingWakingLearningError(original):
        def __init__(self, *args):
            raised.append(" ".join(str(item) for item in args))
            super().__init__(*args)

    monkeypatch.setattr(learning_guard, "WakingLearningError", _CountingWakingLearningError)
    yield
    if raised:
        pytest.fail("WakingLearningError was raised and caught: " + " | ".join(raised))


def _nightly_scheduler() -> SleepScheduler:
    return SleepScheduler(
        circadian_window=(2, 5),
        fatigue_threshold=None,
        min_ticks_between_sleep=0,
        min_interval_s=6 * 3600.0,
    )


def _runtime():
    scheduler = _nightly_scheduler()
    agent = spawn_employee_agent("buyer")
    configure_plasticity(agent, scheduler)
    return make_test_runtime(agent=agent, sleep_scheduler=scheduler)


def _obs():
    return {"tool_results": {"mcp__test__get": {"status": "ok"}}}


class TestExpectedWakeInterval:
    def test_nightly_employee_is_awake_a_day(self):
        assert _nightly_scheduler().expected_wake_interval_s() == 24 * 3600.0

    def test_fatigue_trigger_bounds_it_by_the_anti_thrash_interval(self):
        scheduler = SleepScheduler(fatigue_threshold=0.85, min_interval_s=3600.0)
        assert scheduler.expected_wake_interval_s() == 3600.0

    def test_lab_counts_ticks(self):
        scheduler = SleepScheduler(fatigue_threshold=0.85, min_ticks_between_sleep=120)
        assert scheduler.expected_wake_interval_s(seconds_per_tick=30.0) == 3600.0

    def test_core_agent_gets_the_interval(self):
        agent = spawn_employee_agent("buyer")
        assert configure_plasticity(agent, _nightly_scheduler()) == 24 * 3600.0
        assert agent.plasticity.expected_wake_interval_s == 24 * 3600.0

    def test_agent_without_two_tier_core_is_left_alone(self):
        assert configure_plasticity(object(), _nightly_scheduler()) is None

    def test_employee_is_spawned_with_the_interval(self):
        agent = spawn_employee_agent("buyer", _nightly_scheduler())
        assert agent.plasticity.expected_wake_interval_s == 24 * 3600.0

    def test_lab_agent_is_spawned_with_the_interval(self):
        from nowa_body.lab_session import LabSettings, create_lab_agent

        settings = LabSettings(agent_id="lab", fatigue_threshold=0.85, min_ticks_between_sleep=120,
                               seconds_per_tick=30.0)
        agent = create_lab_agent(settings)
        assert agent.backend == "core"
        inner = object.__getattribute__(agent, "_inner")
        assert inner.plasticity.expected_wake_interval_s == 3600.0


class TestHostClockAndSleep:
    def test_waking_ticks_move_the_host_clock_by_dt_not_the_wall_clock(self):
        runtime = _runtime()
        agent = runtime.agent
        start = float(agent._host_clock_s)
        for index in range(4):
            runtime.run_cycle(_obs(), now=DAY + index * TICK)
        assert float(agent._host_clock_s) - start == pytest.approx(3 * TICK.total_seconds())
        assert not getattr(agent, "_dt_warning_sent", False)

    def test_simulated_tick_length_wins_over_the_cycle_clock(self):
        runtime = _runtime()
        runtime.simulated_tick_seconds = 60.0
        start = float(runtime.agent._host_clock_s)
        runtime.run_cycle(_obs(), now=DAY)
        runtime.run_cycle(_obs(), now=DAY + timedelta(hours=5))
        assert float(runtime.agent._host_clock_s) - start == pytest.approx(120.0)

    def test_day_writes_labile_only_and_the_night_consolidates(self):
        from learning_guard import labile_snapshot, stable_fingerprint

        runtime = _runtime()
        agent = runtime.agent
        runtime.run_cycle(_obs(), now=DAY)
        before = stable_fingerprint(agent)
        lesson = store_lesson(agent, CONTEXT, ORDER, 0.8, consequence="stock_restored")
        runtime.run_cycle(_obs(), now=DAY + TICK)
        assert stable_fingerprint(agent) == before
        assert lesson.td_outcome_committed and lesson.td_committed_reward == 0.8
        assert labile_snapshot(agent)

        result = runtime.run_cycle(_obs(), now=NIGHT)
        assert result["slept"] is True
        assert stable_fingerprint(agent) != before
        assert getattr(lesson, "consolidated", False) is True

    def test_a_lesson_is_consolidated_once(self):
        runtime = _runtime()
        agent = runtime.agent
        runtime.run_cycle(_obs(), now=DAY)
        lesson = store_lesson(agent, CONTEXT, ORDER, 0.8, consequence="stock_restored")
        assert runtime.run_cycle(_obs(), now=NIGHT)["slept"] is True
        assert lesson.consolidated is True
        assert lesson not in agent.sleep_manager._select_two_tier_batch()
