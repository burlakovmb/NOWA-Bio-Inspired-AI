"""Regression tests for patch v1.1.1: Stage 1b graduation needs a clean streak.

Built directly from the v1.1 run that exposed the gap — Stage 1b reported
``GRADUATED`` on the strength of ``all_passed`` alone while
``stockout_avoidance`` was regressed in every one of the 20 Stage 1b quarters.
"""

from __future__ import annotations

from typing import List, Optional

import pytest

from nowa_sandbox.procurement_fitness import (
    PROCUREMENT_CRITERIA,
    ProcurementFitnessEvaluator,
    ProcurementFitnessVector,
)
from nowa_sandbox.procurement_world import ProcurementWorldConfig
from nowa_sandbox.sandbox_encoder import SandboxEncoder
from nowa_sandbox.training_loop import (
    GRADUATION_MIN_STREAK,
    QuarterResult,
    SandboxTrainer,
    SandboxTrainingResult,
    _current_qualifying_streak,
    _quarter_qualifies,
)


def _fake_quarter(index, all_passed, non_regression=None, stage="1b"):
    vector = ProcurementFitnessVector(
        cost_efficiency=0.5,
        stockout_avoidance=0.5,
        budget_discipline=1.0,
        supplier_diversification=0.5,
        decision_consistency=0.5,
        reaction_to_risk_events=0.5,
        n_days=90,
        n_orders=90,
    )
    return QuarterResult(
        quarter_index=index,
        fitness=vector,
        graduation={"all_passed": all_passed, "stage": stage},
        world_summary={},
        processing_time_s=0.0,
        non_regression=non_regression,
    )


def _clean_guard():
    return {
        "cost_efficiency": True,
        "stockout_avoidance": True,
        "budget_discipline": True,
        "reaction_to_risk_events": True,
    }


class TestQuarterQualifies:

    def test_fails_all_passed_disqualifies(self):
        q = _fake_quarter(
            1, all_passed=False, non_regression={"stockout_avoidance": True}
        )
        assert _quarter_qualifies(q) is False

    def test_regressed_criterion_disqualifies_even_if_all_passed(self):
        """The exact bug: all_passed=True but stockout_avoidance regressed."""
        q = _fake_quarter(
            31,
            all_passed=True,
            non_regression={
                "cost_efficiency": False,
                "stockout_avoidance": False,
                "budget_discipline": True,
                "reaction_to_risk_events": True,
            },
        )
        assert _quarter_qualifies(q) is False

    def test_all_passed_with_clean_non_regression_qualifies(self):
        q = _fake_quarter(1, all_passed=True, non_regression=_clean_guard())
        assert _quarter_qualifies(q) is True

    def test_stage_1a_none_non_regression_qualifies_on_all_passed_alone(self):
        """Stage 1a has no baseline; non_regression is None by design."""
        q = _fake_quarter(1, all_passed=True, non_regression=None)
        assert _quarter_qualifies(q) is True

    def test_empty_non_regression_mapping_still_qualifies(self):
        q = _fake_quarter(1, all_passed=True, non_regression={})
        assert _quarter_qualifies(q) is True


class TestQualifyingStreak:

    def test_streak_resets_on_disqualifying_quarter(self):
        quarters = [
            _fake_quarter(1, True, {"stockout_avoidance": True}),
            _fake_quarter(2, True, {"stockout_avoidance": True}),
            _fake_quarter(3, True, {"stockout_avoidance": False}),
        ]
        assert _current_qualifying_streak(quarters) == 0

    def test_streak_counts_trailing_run_only(self):
        quarters = [
            _fake_quarter(1, True, {"stockout_avoidance": False}),
            _fake_quarter(2, True, {"stockout_avoidance": True}),
            _fake_quarter(3, True, {"stockout_avoidance": True}),
        ]
        assert _current_qualifying_streak(quarters) == 2

    def test_reproduces_actual_run_never_reaches_min_streak(self):
        """Sequence from the real Stage 1b run (quarters 31-50).

        ``all_passed`` pattern is T T F T F F T T F T T T F F T F F T F F,
        with ``stockout_avoidance`` regressed in all 20. Under the old rule
        the max streak was 2; under the fix the qualifying streak is always 0.
        """
        all_passed_pattern = [
            True, True, False, True, False, False, True, True, False,
            True, True, True, False, False, True, False, False, True,
            False, False,
        ]
        quarters = [
            _fake_quarter(
                31 + i,
                all_passed,
                {
                    "cost_efficiency": True,
                    "stockout_avoidance": False,
                    "budget_discipline": True,
                    "reaction_to_risk_events": True,
                },
            )
            for i, all_passed in enumerate(all_passed_pattern)
        ]
        assert _current_qualifying_streak(quarters) == 0
        assert max(
            _current_qualifying_streak(quarters[: i + 1])
            for i in range(len(quarters))
        ) == 0

    def test_empty_history_is_zero(self):
        assert _current_qualifying_streak([]) == 0
        assert _current_qualifying_streak(None) == 0

    def test_inherited_stage_1a_quarters_do_not_pad_stage_1b_streak(self):
        """Resuming 1a → 1b with two trailing 1a passes is not a streak of 3."""
        quarters = [
            _fake_quarter(1, True, None, stage="1a"),
            _fake_quarter(2, True, None, stage="1a"),
            _fake_quarter(3, True, _clean_guard(), stage="1b"),
        ]
        assert _current_qualifying_streak(quarters) == 1
        assert _current_qualifying_streak(quarters, stage="1b") == 1
        assert _current_qualifying_streak(quarters[:2], stage="1a") == 2


class _ScriptedFitnessEvaluator(ProcurementFitnessEvaluator):
    """Yields a predetermined sequence of fitness vectors / guard outcomes.

    Used to drive the trainer without a live agent cognition loop: the world
    still ticks, but graduation decisions come entirely from this script.
    """

    def __init__(self, script, stage="1b"):
        super().__init__(stage=stage)
        self._script = list(script)
        self._index = 0

    def evaluate(self, world, decision_log):
        if self._index >= len(self._script):
            raise AssertionError("script exhausted")
        vector, _guard = self._script[self._index]
        self._index += 1
        return vector

    def graduation_report(self, vector):
        report = super().graduation_report(vector)
        # Honour the scripted all_passed so we can force relationship gates
        # independently of the numeric thresholds when needed.
        return report

    def check_non_regression(self, vector, stage_1a_baseline, stage_1a_spread_iqr=None, **_extra):
        # The trainer already advanced _index in evaluate; look one back.
        _, guard = self._script[self._index - 1]
        return dict(guard) if guard is not None else None


def _passing_vector(**overrides):
    values = {c: 1.0 for c in PROCUREMENT_CRITERIA}
    values.update(overrides)
    return ProcurementFitnessVector(**values, n_days=10, n_orders=5)


class _WaitAgent:
    def step(self, context_events=None, **kwargs):
        return "wait_and_monitor"

    def sleep_cycle(self, *args, **kwargs):
        return {}


def _run_scripted(script, stage="1b", stop_on_graduation=True, initial=None):
    evaluator = _ScriptedFitnessEvaluator(script, stage=stage)
    # Any non-empty baseline so _non_regression_for actually calls the guard.
    baseline = {
        "cost_efficiency": 0.75,
        "stockout_avoidance": 0.95,
        "budget_discipline": 1.0,
        "reaction_to_risk_events": 0.8,
    } if stage == "1b" else None
    trainer = SandboxTrainer(
        _WaitAgent(),
        SandboxEncoder(),
        evaluator,
        sleep_every_n_days=5,
        stage_1a_baseline=baseline,
    )
    config = ProcurementWorldConfig(
        initial_budget=10_000.0,
        n_products=1,
        n_suppliers=1,
        days_per_quarter=3,
        seed=1,
    )
    return trainer.run_quarters(
        n_quarters=len(script),
        world_config=config,
        stop_on_graduation=stop_on_graduation,
        initial_result=initial,
    )


class TestGraduationRequiresStreak:

    def test_single_qualifying_quarter_does_not_graduate(self):
        """One good quarter is not enough — GRADUATION_MIN_STREAK requires several."""
        script = [
            (_passing_vector(), _clean_guard()),
            (
                _passing_vector(supplier_diversification=0.0, decision_consistency=0.0),
                {"stockout_avoidance": False, "cost_efficiency": True,
                 "budget_discipline": True, "reaction_to_risk_events": True},
            ),
        ]
        result = _run_scripted(script, stop_on_graduation=True)
        assert result.graduated is False
        assert result.graduated_at_quarter is None
        assert len(result.quarters) == 2

    def test_sustained_streak_graduates_at_streak_start(self):
        """graduated_at_quarter is the FIRST quarter of the streak, not the last."""
        assert GRADUATION_MIN_STREAK == 3
        script = [
            (_passing_vector(), _clean_guard()),
            (_passing_vector(), _clean_guard()),
            (_passing_vector(), _clean_guard()),
        ]
        result = _run_scripted(script, stop_on_graduation=True)
        assert result.graduated is True
        assert result.graduated_at_quarter == 1
        assert len(result.quarters) == 3

    def test_streak_starting_later_reports_its_own_start(self):
        script = [
            (
                _passing_vector(supplier_diversification=0.0),
                {"stockout_avoidance": False, "cost_efficiency": True,
                 "budget_discipline": True, "reaction_to_risk_events": True},
            ),
            (_passing_vector(), _clean_guard()),
            (_passing_vector(), _clean_guard()),
            (_passing_vector(), _clean_guard()),
        ]
        result = _run_scripted(script, stop_on_graduation=True)
        assert result.graduated is True
        assert result.graduated_at_quarter == 2
        assert len(result.quarters) == 4

    def test_all_passed_but_regressed_never_graduates(self):
        """The live-run failure mode: every PASS bought by a stockout regression."""
        script = [
            (
                _passing_vector(),
                {"stockout_avoidance": False, "cost_efficiency": True,
                 "budget_discipline": True, "reaction_to_risk_events": True},
            )
        ] * 5
        result = _run_scripted(script, stop_on_graduation=True)
        assert result.graduated is False
        assert len(result.quarters) == 5

    def test_stage_1a_still_graduates_on_a_single_pass(self):
        """NR1: Stage 1a behaviour is unchanged — one all_passed is enough."""
        script = [(_passing_vector(), None)]
        result = _run_scripted(script, stage="1a", stop_on_graduation=True)
        assert result.graduated is True
        assert result.graduated_at_quarter == 1
        assert len(result.quarters) == 1


class TestResumePreservesStreak:

    def test_two_passing_1a_quarters_plus_one_1b_does_not_graduate(self):
        initial = SandboxTrainingResult(
            quarters=[
                _fake_quarter(1, True, None, stage="1a"),
                _fake_quarter(2, True, None, stage="1a"),
            ]
        )
        continued = _run_scripted(
            [(_passing_vector(), _clean_guard())],
            stage="1b",
            stop_on_graduation=True,
            initial=initial,
        )
        assert continued.graduated is False
        assert _current_qualifying_streak(continued.quarters, stage="1b") == 1

    def test_streak_recomputed_from_history_not_reset_on_resume(self):
        """A checkpoint saved mid-streak must not lose credit on resume."""
        quarters = [
            _fake_quarter(1, True, _clean_guard()),
            _fake_quarter(2, True, _clean_guard()),
        ]
        result = SandboxTrainingResult(quarters=quarters)
        assert _current_qualifying_streak(result.quarters) == 2

        # One more qualifying quarter via the trainer must tip the streak to 3.
        script = [(_passing_vector(), _clean_guard())]
        continued = _run_scripted(
            script, stop_on_graduation=True, initial=result
        )
        assert continued.graduated is True
        assert continued.graduated_at_quarter == 1
        assert len(continued.quarters) == 3

    def test_summary_shows_qualifying_streak_per_quarter(self):
        quarters = [
            _fake_quarter(1, True, _clean_guard()),
            _fake_quarter(2, True, {"stockout_avoidance": False}),
            _fake_quarter(3, True, _clean_guard()),
        ]
        summary = SandboxTrainingResult(quarters=quarters).summary()
        assert "qualifying_streak=1" in summary
        assert "qualifying_streak=0" in summary


class TestNormalizedCostGuard:
    """cost_efficiency is guarded on cost_vs_chance when the baseline has it."""

    def _vector(self, cost_efficiency):
        values = {c: 1.0 for c in PROCUREMENT_CRITERIA}
        values["cost_efficiency"] = cost_efficiency
        return ProcurementFitnessVector(**values, n_days=10, n_orders=5)

    def test_normalized_floor_can_sit_below_zero(self):
        evaluator = ProcurementFitnessEvaluator(stage="1b")
        baseline = {
            "cost_efficiency": 0.9,
            "stockout_avoidance": 0.9,
            "budget_discipline": 1.0,
            "reaction_to_risk_events": 0.8,
        }
        spread = {name: 0.0 for name in baseline}
        # median 0, IQR 0.05 -> unclipped floor = min(0, -0.05) = -0.05.
        # Raw cost 0.9 would clear a 0.9 baseline; the normalized value does not.
        failed = evaluator.check_non_regression(
            self._vector(0.9),
            baseline,
            stage_1a_spread_iqr=spread,
            cost_vs_chance=-0.2,
            cost_vs_chance_median=0.0,
            cost_vs_chance_iqr=0.05,
        )
        assert failed["cost_efficiency"] is False
        assert failed["stockout_avoidance"] is True

        passed = evaluator.check_non_regression(
            self._vector(0.2),
            baseline,
            stage_1a_spread_iqr=spread,
            cost_vs_chance=-0.04,
            cost_vs_chance_median=0.0,
            cost_vs_chance_iqr=0.05,
        )
        assert passed["cost_efficiency"] is True
