"""Hybrid sleep trigger: circadian window AND Process-S fatigue.

Q-Phase1-1a (closed by reading ``src/wakefulness.py``):

- Process S is ``WakefulnessState._wakefulness``.
- Public readers: ``get_sleep_pressure()`` and the ``wakefulness`` property.
- It does **not** grow from tick counting. It grows only via
  ``update_waking(elapsed_seconds=...)``.
- ``Agent.step()`` already calls ``self.wakefulness.update_waking()`` on
  wall-clock. The runtime also calls ``update_waking`` each cycle so stub
  agents without ``step()`` still accumulate; a second wall-clock call
  after a real ``Agent.step()`` is a no-op (elapsed ≈ 0).
- The agent attribute is ``wakefulness``, not ``wakefulness_state``. This
  scheduler tries both, plus several Process-S accessors, so a naming
  mismatch degrades to circadian-only rather than crashing.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional, Tuple


class SleepScheduler:
    """Decide, once per run_cycle() tick, whether the agent should sleep now.

    Combines two independent signals: a scheduled nightly window, AND an
    early trigger when accumulated waking load crosses a threshold.
    Does not implement sleep pressure itself — reads it from the agent's
    ``WakefulnessState``.
    """

    def __init__(
        self,
        circadian_window: Tuple[int, int] = (2, 5),
        fatigue_threshold: Optional[float] = 0.85,
        min_ticks_between_sleep: int = 3600,
        min_interval_s: Optional[float] = None,
    ) -> None:
        self.circadian_window = circadian_window
        self.fatigue_threshold = (
            None if fatigue_threshold is None else float(fatigue_threshold)
        )
        self.min_ticks_between_sleep = int(min_ticks_between_sleep)
        self.min_interval_s = (
            None if min_interval_s is None else float(min_interval_s)
        )
        self._ticks_since_last_sleep = 0
        self._last_slept_at: Optional[datetime] = None
        self._clock_origin: Optional[datetime] = None

    def should_sleep(self, agent: Any, now: datetime) -> Tuple[bool, str]:
        """Return ``(should_sleep, reason)``.

        ``reason`` is ``"circadian"``, ``"fatigue"``, or ``""``.
        When ``min_interval_s`` is set, anti-thrash uses wall-clock seconds
        (employee host). Otherwise the lab tick counter is used.
        """
        if self.min_interval_s is not None:
            return self._should_sleep_wall(agent, now)
        self._ticks_since_last_sleep += 1
        if self._ticks_since_last_sleep < self.min_ticks_between_sleep:
            return False, ""
        return self._sleep_signals(agent, now)

    def _should_sleep_wall(self, agent: Any, now: datetime) -> Tuple[bool, str]:
        if self._clock_origin is None:
            self._clock_origin = now
        last = self._last_slept_at if self._last_slept_at is not None else self._clock_origin
        elapsed = (now - last).total_seconds()
        if elapsed < float(self.min_interval_s):
            return False, ""
        return self._sleep_signals(agent, now)

    def _sleep_signals(self, agent: Any, now: datetime) -> Tuple[bool, str]:
        if self._in_circadian_window(now):
            return True, "circadian"
        if self.fatigue_threshold is None:
            return False, ""
        pressure = self._read_sleep_pressure(agent)
        if pressure is not None and pressure >= self.fatigue_threshold:
            return True, "fatigue"
        return False, ""

    def expected_wake_interval_s(self, seconds_per_tick: Optional[float] = None) -> float:
        """Typical waking span between two sleeps, in host seconds.

        The core sizes its labile tier by it (``PlasticityConfig``). With the
        nightly window and no fatigue trigger the agent sleeps once a day, or
        less often when the anti-thrash interval is longer. A fatigue trigger
        can only make sleep come sooner, so the anti-thrash interval is then
        the closest bound.
        """
        day = 24 * 3600.0
        if self.min_interval_s is not None:
            floor = float(self.min_interval_s)
        elif seconds_per_tick:
            floor = float(self.min_ticks_between_sleep) * float(seconds_per_tick)
        else:
            floor = 0.0
        if self.fatigue_threshold is None or floor <= 0.0:
            return max(day, floor)
        return floor

    def mark_slept(self, now: Optional[datetime] = None) -> None:
        self._ticks_since_last_sleep = 0
        self._last_slept_at = now if now is not None else datetime.now()

    def _in_circadian_window(self, now: datetime) -> bool:
        start, end = self.circadian_window
        hour = int(now.hour)
        start_h, end_h = int(start), int(end)
        if start_h == end_h:
            return False
        if start_h < end_h:
            return start_h <= hour < end_h
        return hour >= start_h or hour < end_h

    def _read_sleep_pressure(self, agent: Any) -> Optional[float]:
        """Read Process S defensively (Q-Phase1-1a).

        Verified API: ``WakefulnessState.get_sleep_pressure()`` returns
        ``_wakefulness``. Also accepts ``agent.wakefulness`` (core Agent)
        and ``agent.wakefulness_state`` (spec name).
        """
        ws = getattr(agent, "wakefulness_state", None)
        if ws is None:
            ws = getattr(agent, "wakefulness", None)
        if ws is None:
            return None
        for attr in (
            "get_sleep_pressure",
            "process_s",
            "sleep_pressure",
            "homeostatic_pressure",
            "wakefulness",
        ):
            value = getattr(ws, attr, None)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return float(value)
            if callable(value):
                try:
                    result = value()
                except Exception:
                    continue
                if isinstance(result, (int, float)) and not isinstance(result, bool):
                    return float(result)
        return None


def configure_plasticity(
    agent: Any, scheduler: SleepScheduler, seconds_per_tick: Optional[float] = None
) -> Optional[float]:
    """Tell the core how long the agent stays awake between sleeps.

    Set after construction and after every load: the core reads the interval
    lazily, and a checkpoint may carry an older value. Returns the interval,
    or None when the agent has no two-tier core (a lab stub).
    """
    plasticity = getattr(agent, "plasticity", None)
    if plasticity is None or not hasattr(plasticity, "expected_wake_interval_s"):
        return None
    interval = scheduler.expected_wake_interval_s(seconds_per_tick)
    plasticity.expected_wake_interval_s = interval
    return interval
