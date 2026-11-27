"""Domain-neutral scenario: observe, tokens, call, outcome.

The trainer speaks only these types. A second domain subclasses
:class:`Scenario` and leaves this module alone.
"""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence


@dataclass(frozen=True)
class Observation:
    """Read-only snapshot. ``payload`` is opaque to the trainer."""

    payload: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Call:
    """One tool call. ``raw`` is the domain object the scenario itself built."""

    tool: Optional[str]
    arguments: Mapping[str, Any]
    raw: Any = None


@dataclass(frozen=True)
class Outcome:
    """What the world returned, plus an optional delayed-feedback bundle."""

    result: Optional[Mapping[str, Any]] = None
    pending: Optional[Mapping[str, Any]] = None


class Scenario(ABC):
    """Hooks the trainer calls. World stepping defaults match a tick/day world.

    Override the world hooks if the domain does not use ``tick``, ``day``,
    ``history`` and ``bankrupt``. KPI names never appear here.
    """

    # --- world cycle -------------------------------------------------------

    def halted(self, world: Any) -> bool:
        return bool(getattr(world, "bankrupt", False))

    def previous_tick(self, world: Any) -> Mapping[str, Any]:
        history = getattr(world, "history", None) or []
        if history:
            return history[-1]
        return {"events": []}

    def advance(self, world: Any) -> None:
        world.tick()

    def day(self, world: Any) -> int:
        return int(getattr(world, "day", 0))

    def world_summary(self, world: Any) -> dict:
        summary = getattr(world, "summary", None)
        if callable(summary):
            return dict(summary())
        return {}

    def period_length(self, config: Any) -> int:
        return int(getattr(config, "days_per_quarter", 0))

    # --- decision ----------------------------------------------------------

    def observe(self, world: Any) -> Observation:
        raise NotImplementedError

    def encode(
        self,
        world: Any,
        tick_result: Mapping[str, Any],
        observation: Observation,
    ) -> list:
        raise NotImplementedError

    def action_label(self, intent: Any) -> str:
        raise NotImplementedError

    def resolve(
        self,
        action: str,
        observation: Observation,
        agent: Any,
    ) -> Optional[Call]:
        raise NotImplementedError

    def apply(
        self,
        world: Any,
        call: Call,
        observation: Observation,
    ) -> Outcome:
        raise NotImplementedError

    def store(self, tokens: Sequence[str], call: Call, outcome: Outcome) -> None:
        return None

    def note(self, action: str, call: Call, outcome: Outcome) -> None:
        return None

    def remember(
        self,
        tokens: Sequence[str],
        observation: Observation,
        call: Optional[Call],
        outcome: Optional[Outcome],
    ) -> None:
        return None

    def row(
        self,
        *,
        day: int,
        action: str,
        call: Optional[Call],
        outcome: Optional[Outcome],
        tokens: Sequence[str],
    ) -> dict:
        raise NotImplementedError

    def trace(
        self,
        host: Any,
        world: Any,
        tokens: Sequence[str],
        activated: int,
        action: str,
        call: Optional[Call],
        outcome: Optional[Outcome],
    ) -> None:
        return None

    def apply_feedback(self, pending: Mapping[str, Any]) -> dict:
        return {}

    def begin_period(self) -> None:
        return None

    # --- score and roster --------------------------------------------------

    def evaluate(self, world: Any, decision_log: list) -> Any:
        raise NotImplementedError

    def graduation_report(self, fitness: Any) -> dict:
        raise NotImplementedError

    def summary_extras(
        self,
        world: Any,
        decision_log: list,
        fitness: Any,
        period_index: int,
        result: Any,
        carry_roster: bool,
        labels: Mapping[str, Any],
    ) -> dict:
        return {}

    def non_regression(self, fitness: Any, summary: Mapping[str, Any]) -> Optional[dict]:
        return None

    def config_for_step(self, world_config: Any, period_index: int) -> Any:
        raise NotImplementedError

    def open_period(
        self,
        config: Any,
        period_index: int,
    ) -> tuple:
        """Return ``(world, labels)``. ``labels`` is copied into the summary."""
        raise NotImplementedError

    def stage_name(self) -> str:
        return "1a"

    def minimum_streak(self) -> int:
        return 1

    def has_roster(self) -> bool:
        return False

    def drop_roster(self) -> None:
        return None

    def apply_roster(self, world: Any) -> None:
        return None

    def capture_roster(self, world: Any) -> None:
        return None

    def roster_boundary(self, period_index: int, stage_start: int) -> bool:
        return False


__all__ = [
    "Call",
    "Observation",
    "Outcome",
    "Scenario",
]
