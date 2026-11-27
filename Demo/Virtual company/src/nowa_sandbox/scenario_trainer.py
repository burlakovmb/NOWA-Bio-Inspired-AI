"""Quarter loop that talks only to a :class:`scenario.Scenario`.

Sleep, the agent step and checkpoint-friendly result objects live here.
Domain nouns do not.
"""

from __future__ import annotations

import inspect
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional

from .scenario import Scenario, render_fitness_line
from .stage_mechanics import (
    GRADUATION_MIN_STREAK,
    action_counts,
    current_qualifying_streak,
    ensure_stage_start,
    period_qualifies,
)


@dataclass
class QuarterResult:
    quarter_index: int
    fitness: Any
    graduation: dict
    world_summary: dict
    processing_time_s: float
    non_regression: Optional[Dict[str, bool]] = None
    """Later stage only: per-criterion result of the baseline guard."""

    @property
    def regressed_criteria(self) -> List[str]:
        return sorted(
            name for name, ok in (self.non_regression or {}).items() if not ok
        )


@dataclass
class SandboxTrainingResult:
    quarters: List[QuarterResult] = field(default_factory=list)
    graduated: bool = False
    graduated_at_quarter: Optional[int] = None
    # First later-stage period. Roster boundaries are counted from here.
    # None on an early-stage result and on checkpoints written before
    # set rotation.
    stage_1b_start_quarter: Optional[int] = None
    # Set by the trainer from the active scenario. Absent on a result built
    # by hand or loaded from a checkpoint that has not been resumed yet.
    fitness_line: Optional[Callable[[Any], str]] = field(
        default=None, repr=False, compare=False
    )

    def summary(self) -> str:
        lines = ["=== Sandbox Training Summary ==="]
        render = self.fitness_line or render_fitness_line
        for i, quarter in enumerate(self.quarters):
            status = "PASS" if quarter.graduation.get("all_passed") else "..."
            regressed = quarter.regressed_criteria
            streak = current_qualifying_streak(self.quarters[: i + 1])
            lines.append(
                f"Quarter {quarter.quarter_index}: [{status}] "
                f"{render(quarter.fitness)}"
                f"qualifying_streak={streak}"
                + (f"  REGRESSED: {', '.join(regressed)}" if regressed else "")
            )
        if self.graduated:
            lines.append(f"\nGRADUATED at quarter {self.graduated_at_quarter}")
        else:
            lines.append("\nNOT YET GRADUATED - continue training")
        return "\n".join(lines)

    @property
    def longest_graduation_streak(self) -> int:
        longest = streak = 0
        for quarter in self.quarters:
            if period_qualifies(quarter):
                streak += 1
                longest = max(longest, streak)
            else:
                streak = 0
        return longest

    def graduation_sustained(self, min_streak: int = GRADUATION_MIN_STREAK) -> bool:
        return self.longest_graduation_streak >= max(1, int(min_streak))

    def regressed_quarters(self) -> List[int]:
        return [
            quarter.quarter_index
            for quarter in self.quarters
            if quarter.graduation.get("all_passed") and quarter.regressed_criteria
        ]


class ScenarioTrainer:
    """Run periods by calling the scenario. The agent loop stays here."""

    def __init__(
        self,
        agent: Any,
        scenario: Scenario,
        sleep_every_n_days: int = 7,
        verbose_pipeline: bool = False,
        pipeline_logger: Optional[Callable[[str], None]] = None,
    ):
        self.agent = agent
        self.scenario = scenario
        self.sleep_every_n_days = max(1, int(sleep_every_n_days))
        plasticity = getattr(self.agent, "plasticity", None)
        if plasticity is not None and hasattr(plasticity, "expected_wake_interval_s"):
            plasticity.expected_wake_interval_s = self.sleep_every_n_days * 86400.0
        self.verbose_pipeline = bool(verbose_pipeline)
        self.pipeline_logger = pipeline_logger
        self.last_decision_log: List[dict] = []
        self.quarter_overrides: Dict[int, Dict[str, Any]] = {}
        self.curriculum: Optional[Any] = None
        self.max_cycles: int = 500

    def run_quarters(
        self,
        n_quarters: int = 20,
        world_config: Any = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        stop_on_graduation: bool = True,
        initial_result: Optional[SandboxTrainingResult] = None,
        carry_roster: bool = False,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> SandboxTrainingResult:
        """Run ``n_quarters`` additional periods, appending to prior results."""
        result = initial_result or SandboxTrainingResult()
        scenario = self.scenario
        result.fitness_line = scenario.fitness_line
        start_index = len(result.quarters) + 1
        total = len(result.quarters) + max(0, int(n_quarters))

        for offset in range(max(0, int(n_quarters))):
            if should_stop is not None and should_stop():
                break
            period_index = start_index + offset
            if carry_roster:
                ensure_stage_start(
                    result, start_index, scenario.has_roster()
                )
            if progress_callback:
                progress_callback(period_index, total)

            started = time.perf_counter()
            config = scenario.config_for_step(world_config, period_index)
            world, labels = scenario.open_period(config, period_index)

            if carry_roster and scenario.roster_boundary(
                period_index,
                int(result.stage_1b_start_quarter or period_index),
            ):
                scenario.drop_roster()
            if carry_roster and scenario.has_roster():
                scenario.apply_roster(world)

            decision_log = self._run_single_quarter(
                world, n_days=scenario.period_length(config)
            )
            self.last_decision_log = decision_log
            if carry_roster:
                scenario.capture_roster(world)

            fitness = scenario.evaluate(world, decision_log)
            graduation = scenario.graduation_report(fitness)
            summary = scenario.world_summary(world)
            summary["action_counts"] = action_counts(decision_log)
            summary.update(dict(labels or {}))
            summary.update(scenario.summary_extras(
                world,
                decision_log,
                fitness,
                period_index,
                result,
                carry_roster,
                labels,
            ))
            quarter_result = QuarterResult(
                quarter_index=period_index,
                fitness=fitness,
                graduation=graduation,
                world_summary=summary,
                processing_time_s=time.perf_counter() - started,
                non_regression=scenario.non_regression(fitness, summary),
            )
            result.quarters.append(quarter_result)

            min_streak = scenario.minimum_streak()
            streak = current_qualifying_streak(
                result.quarters, stage=scenario.stage_name()
            )
            if streak >= min_streak and not result.graduated:
                result.graduated = True
                result.graduated_at_quarter = (
                    quarter_result.quarter_index - min_streak + 1
                )
                if stop_on_graduation:
                    break

        return result

    def run_curriculum_cycles(
        self,
        curriculum: Any,
        *,
        world_config: Any = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        stop_on_graduation: bool = True,
        initial_result: Optional[SandboxTrainingResult] = None,
        carry_roster: bool = False,
        should_stop: Optional[Callable[[], bool]] = None,
        max_cycles: Optional[int] = None,
    ) -> SandboxTrainingResult:
        """Cycle curriculum periods until graduation, stop, or ``max_cycles``."""
        self.curriculum = curriculum
        n = int(getattr(curriculum, "n_quarters", 0) or 0)
        if n < 1:
            raise ValueError("curriculum must contain at least one quarter")
        cycles = int(max_cycles if max_cycles is not None else self.max_cycles)
        n_steps = max(1, cycles) * n
        # Call this class, not a subclass wrapper that renames ``carry_roster``.
        return ScenarioTrainer.run_quarters(self,
            n_quarters=n_steps,
            world_config=world_config,
            progress_callback=progress_callback,
            stop_on_graduation=stop_on_graduation,
            initial_result=initial_result,
            carry_roster=carry_roster,
            should_stop=should_stop,
        )

    def _run_single_quarter(self, world: Any, n_days: int) -> List[dict]:
        """One period: observe, decide, call, remember, advance, sleep."""
        decision_log: List[dict] = []
        pending = None
        scenario = self.scenario
        scenario.begin_period()

        for _ in range(max(0, int(n_days))):
            if scenario.halted(world):
                break

            tick_result = scenario.previous_tick(world)
            if pending is not None:
                feedback = scenario.apply_feedback(pending)
                self._log_pipeline_feedback(feedback)
                pending = None

            observation = scenario.observe(world)
            tokens = scenario.encode(world, tick_result, observation)
            activation_before = self._activation_snapshot()
            intent = self._agent_step(tokens, dt=86400.0)
            action = scenario.action_label(intent)
            activated = self._activated_since(activation_before)
            call = scenario.resolve(action, observation, self.agent)
            outcome = None
            if call is not None:
                outcome = scenario.apply(world, call, observation)
                pending = outcome.pending
                scenario.store(tokens, call, outcome)
                scenario.note(action, call, outcome)
            scenario.remember(tokens, observation, call, outcome)
            decision_log.append(scenario.row(
                day=scenario.day(world),
                action=action,
                call=call,
                outcome=outcome,
                tokens=tokens,
            ))
            scenario.trace(
                self, world, tokens, activated, action, call, outcome
            )
            scenario.advance(world)
            if scenario.day(world) % self.sleep_every_n_days == 0:
                self._agent_sleep()

        if pending is not None:
            feedback = scenario.apply_feedback(pending)
            self._log_pipeline_feedback(feedback)
        return decision_log

    def _agent_step(self, context_events: List[str], dt: float = 86400.0) -> Any:
        """One decision. Exactly one ``step`` call; support is introspected.

        A ``TypeError`` raised inside the agent is indistinguishable from a
        signature mismatch, and retrying it could repeat side effects the
        first attempt already applied.
        """
        step_fn = getattr(self.agent, "step", None)
        if not callable(step_fn):
            advance = getattr(self.agent, "advance_time", None)
            if callable(advance):
                advance(float(dt))
            return "wait_and_monitor"
        kwargs: Dict[str, Any] = {}
        if self._accepts_decision_only(step_fn):
            kwargs["decision_only"] = True
        if self._accepts_parameter(step_fn, "dt"):
            kwargs["dt"] = float(dt)
        else:
            advance = getattr(self.agent, "advance_time", None)
            if callable(advance):
                advance(float(dt))
        result = step_fn(context_events, **kwargs)
        if result is not None:
            return result
        for attr in ("last_intent", "last_action", "current_action"):
            value = getattr(self.agent, attr, None)
            if value is not None:
                return value
        return "wait_and_monitor"

    @staticmethod
    def _accepts_parameter(step_fn: Callable[..., Any], name: str) -> bool:
        """Only an explicit parameter proves support; **kwargs may ignore dt."""
        try:
            parameter = inspect.signature(step_fn).parameters.get(name)
        except (TypeError, ValueError):
            return False
        return parameter is not None and parameter.kind in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        )

    @staticmethod
    def _accepts_decision_only(step_fn: Callable[..., Any]) -> bool:
        """Whether ``step_fn`` takes a ``decision_only`` keyword argument.

        ``**kwargs`` counts as support: an agent that swallows unknown
        keywords has no waking learning to skip, so passing the flag is
        harmless there.
        """
        try:
            parameters = inspect.signature(step_fn).parameters
        except (TypeError, ValueError):
            return False
        for param in parameters.values():
            if param.kind is inspect.Parameter.VAR_KEYWORD:
                return True
            if param.name == "decision_only" and param.kind in (
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            ):
                return True
        return False

    def _activation_snapshot(self) -> Dict[int, float]:
        experiences = getattr(
            getattr(self.agent, "hippocampus", None), "experiences", []
        ) or []
        return {
            id(exp): float(getattr(exp, "last_activated", 0.0) or 0.0)
            for exp in list(experiences)
        }

    def _activated_since(self, before: Mapping[int, float]) -> int:
        experiences = getattr(
            getattr(self.agent, "hippocampus", None), "experiences", []
        ) or []
        return sum(
            1
            for exp in list(experiences)
            if id(exp) in before
            and float(getattr(exp, "last_activated", 0.0) or 0.0) > before[id(exp)]
        )

    def _emit_pipeline(self, message: str) -> None:
        """Emit one diagnostic line. ASCII only: some consoles are not UTF-8."""
        if not self.verbose_pipeline:
            return
        if callable(self.pipeline_logger):
            self.pipeline_logger(message)
        else:
            print(message, flush=True)

    def _log_pipeline_feedback(self, feedback: dict) -> None:
        inputs = dict((feedback or {}).get("inputs") or {})
        if not inputs:
            return
        rendered = ", ".join(
            f"{key} {value:+.1f}" for key, value in inputs.items()
        )
        self._emit_pipeline(f"         -> affective_feedback: {rendered}")

    def _agent_sleep(self) -> None:
        sleep_fn = getattr(self.agent, "sleep", None)
        if callable(sleep_fn):
            if self._accepts_parameter(sleep_fn, "cycles"):
                sleep_fn(cycles=1)
            else:
                sleep_fn()
            return
        sleep_manager = getattr(self.agent, "sleep_manager", None)
        if sleep_manager is not None and callable(
            getattr(sleep_manager, "sleep_cycle", None)
        ):
            sleep_manager.sleep_cycle()


__all__ = [
    "GRADUATION_MIN_STREAK",
    "QuarterResult",
    "SandboxTrainingResult",
    "ScenarioTrainer",
]
