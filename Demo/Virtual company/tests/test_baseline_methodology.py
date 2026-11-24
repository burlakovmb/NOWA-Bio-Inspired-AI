"""Regression-anchored on the actual seed1 run: stockout_avoidance
ranged 0.000-1.000 across 30 quarters with no visible learning trend."""

import statistics

import pytest

from nowa_sandbox.procurement_fitness import (
    NON_REGRESSION_FLOOR,
    ProcurementFitnessEvaluator,
    ProcurementFitnessVector,
)
from nowa_sandbox.stage_baseline import (
    MIN_QUARTERS_FOR_BASELINE,
    compute_stage_1a_baseline,
    non_regression_floor,
    save_baseline,
)


SEED1_STOCKOUT_AVOIDANCE = [
    0.000, 0.745, 0.000, 0.178, 0.456, 0.936, 0.197, 0.419, 0.995, 0.204,
    0.481, 0.835, 0.376, 0.000, 0.000, 0.000, 0.096, 0.000, 0.897, 0.741,
    0.000, 0.716, 1.000, 0.216, 0.090, 0.919, 0.448, 0.000, 0.000, 0.398,
]


def _fake_quarters(stockout_values, passed_indices=None):
    passed_indices = passed_indices or set()
    return [
        {
            "quarter_index": i + 1,
            "fitness": {
                "cost_efficiency": 0.6,
                "stockout_avoidance": v,
                "budget_discipline": 1.0,
                "reaction_to_risk_events": 0.6,
            },
            "graduation": {"all_passed": (i + 1) in passed_indices},
        }
        for i, v in enumerate(stockout_values)
    ]


class TestMedianVsMeanOfBest:

    def test_median_baseline_far_below_mean_of_best(self):
        """The exact discrepancy that caused the false regression signal:
        cherry-picked best-5 mean was 0.9493, but median across all 30
        quarters is much lower."""
        quarters = _fake_quarters(
            SEED1_STOCKOUT_AVOIDANCE,
            passed_indices={6, 9, 19, 23, 26},
        )
        payload = compute_stage_1a_baseline(quarters)
        median_value = payload["stage_1a_baseline"]["stockout_avoidance"]
        old_mean_of_best = statistics.mean(
            [SEED1_STOCKOUT_AVOIDANCE[i - 1] for i in (6, 9, 19, 23, 26)]
        )
        assert median_value < old_mean_of_best - 0.3, (
            f"median={median_value:.4f} should be well below the old "
            f"cherry-picked mean={old_mean_of_best:.4f}"
        )
        assert payload["method"] == "median_all"
        assert payload["n_quarters_used"] == 30

    def test_raises_below_minimum_quarters(self):
        quarters = _fake_quarters(SEED1_STOCKOUT_AVOIDANCE[:10])
        with pytest.raises(ValueError, match="at least"):
            compute_stage_1a_baseline(quarters)

    def test_high_iqr_flagged_in_spread(self):
        quarters = _fake_quarters(SEED1_STOCKOUT_AVOIDANCE)
        payload = compute_stage_1a_baseline(quarters)
        assert payload["stage_1a_spread_iqr"]["stockout_avoidance"] > 0.3

    def test_mean_best_still_available_for_diagnostics(self):
        quarters = _fake_quarters(
            SEED1_STOCKOUT_AVOIDANCE,
            passed_indices={6, 9, 19, 23, 26},
        )
        payload = compute_stage_1a_baseline(quarters, method="mean_best", last_n=5)
        assert payload["method"] == "mean_best"
        assert payload["stage_1a_baseline"]["stockout_avoidance"] == pytest.approx(
            statistics.mean(
                [SEED1_STOCKOUT_AVOIDANCE[i - 1] for i in (6, 9, 19, 23, 26)]
            ),
            abs=1e-3,
        )

    def test_refuses_to_save_mean_best_as_guard_baseline(self, tmp_path):
        quarters = _fake_quarters(SEED1_STOCKOUT_AVOIDANCE[:5], passed_indices={1})
        payload = compute_stage_1a_baseline(quarters, method="mean_best")
        with pytest.raises(ValueError, match="mean_best"):
            save_baseline(str(tmp_path / "bad.json"), payload)


class TestNonRegressionFloorAccountsForVolatility:

    def test_stable_criterion_floor_matches_v1_1(self):
        """budget_discipline sat at 1.0 in every observed quarter — for a
        near-zero IQR criterion, the new floor should match the old
        median * 0.9 behaviour almost exactly."""
        floor = non_regression_floor(median_value=1.0, iqr=0.0)
        assert abs(floor - 0.9) < 1e-6

    def test_volatile_criterion_floor_relaxes(self):
        """stockout_avoidance with a large IQR should get a floor well
        below median * 0.9 — the volatility itself is normal, not a
        regression signal."""
        median_value = statistics.median(SEED1_STOCKOUT_AVOIDANCE)
        iqr = 0.6  # observed magnitude order
        floor = non_regression_floor(median_value, iqr)
        strict_floor = median_value * 0.9
        assert floor < strict_floor

    def test_floor_never_negative(self):
        floor = non_regression_floor(median_value=0.1, iqr=0.5)
        assert floor >= 0.0

    def test_min_quarters_constant(self):
        assert MIN_QUARTERS_FOR_BASELINE == 15


class TestStage1bReinterpretedWithNewFloor:

    def test_stage1b_run_fewer_false_regressions_under_new_floor(self):
        """Re-run the non_regression check for the real Stage 1b quarters
        (31-50) using the volatility-aware floor and confirm fewer
        quarters are flagged as regressed on stockout_avoidance than
        under the old fixed 0.9 multiplier — the point of this patch."""
        stage1b_stockout = [
            0.810, 0.292, 0.761, 0.870, 0.784, 0.840, 0.854, 0.912, 0.860,
            0.803, 0.696, 0.909, 0.994, 0.908, 0.931, 0.827, 0.938, 0.942,
            0.900, 0.925,
        ]
        median_value = statistics.median(SEED1_STOCKOUT_AVOIDANCE)
        iqr = 0.6
        new_floor = non_regression_floor(median_value, iqr)
        old_floor = 0.9493 * 0.9  # v1.1 mean-of-best baseline * 0.9

        old_regressions = sum(1 for v in stage1b_stockout if v < old_floor)
        new_regressions = sum(1 for v in stage1b_stockout if v < new_floor)

        assert new_regressions < old_regressions

    def test_guard_uses_iqr_when_provided(self):
        """Wiring: check_non_regression must honour the volatility floor."""
        evaluator = ProcurementFitnessEvaluator(stage="1b")
        baseline = {
            "cost_efficiency": 0.6,
            "stockout_avoidance": statistics.median(SEED1_STOCKOUT_AVOIDANCE),
            "budget_discipline": 1.0,
            "reaction_to_risk_events": 0.6,
        }
        spread = {
            "cost_efficiency": 0.0,
            "stockout_avoidance": 0.6,
            "budget_discipline": 0.0,
            "reaction_to_risk_events": 0.0,
        }
        # 0.40 is below median*0.9 for the seed1 median (~0.207*0.9) wait —
        # seed1 median of stockout is around 0.3; 0.40 should pass the
        # volatility floor but would fail a cherry-picked 0.949*0.9 floor.
        vector = ProcurementFitnessVector(
            cost_efficiency=0.6,
            stockout_avoidance=0.40,
            budget_discipline=1.0,
            supplier_diversification=0.5,
            decision_consistency=0.5,
            reaction_to_risk_events=0.6,
            n_days=90,
            n_orders=10,
        )
        with_iqr = evaluator.check_non_regression(
            vector, baseline, stage_1a_spread_iqr=spread
        )
        without = evaluator.check_non_regression(vector, baseline)
        # Volatility-aware floor for stockout is ~0 (median - 0.6), so 0.40 passes.
        assert with_iqr["stockout_avoidance"] is True
        # Without IQR, floor = median * 0.9. For seed1 median ~0.3 that is
        # ~0.27 — 0.40 still passes. Use a high baseline to show the difference.
        high_baseline = dict(baseline)
        high_baseline["stockout_avoidance"] = 0.9493
        with_iqr_high = evaluator.check_non_regression(
            vector, high_baseline, stage_1a_spread_iqr=spread
        )
        without_high = evaluator.check_non_regression(vector, high_baseline)
        assert with_iqr_high["stockout_avoidance"] is True
        assert without_high["stockout_avoidance"] is False
        assert without["budget_discipline"] is True
        assert abs(NON_REGRESSION_FLOOR - 0.9) < 1e-9


class TestNormalizedSavingsBaseline:

    def test_floor_for_normalized_savings_is_not_clipped_at_zero(self):
        clipped = non_regression_floor(0.0, 0.2)
        open_floor = non_regression_floor(0.0, 0.2, clip_at_zero=False)
        assert clipped == 0.0
        assert open_floor == pytest.approx(-0.2)

    def test_median_baseline_stores_cost_vs_chance_when_present(self):
        values = [0.02 * (i - 7) for i in range(15)]
        quarters = []
        for i, value in enumerate(values, start=1):
            quarters.append({
                "quarter_index": i,
                "fitness": {
                    "cost_efficiency": 0.6,
                    "stockout_avoidance": 0.9,
                    "budget_discipline": 1.0,
                    "reaction_to_risk_events": 0.6,
                },
                "graduation": {"all_passed": True},
                "world_summary": {"cost_vs_chance": value},
            })
        payload = compute_stage_1a_baseline(quarters)
        assert payload["cost_vs_chance_median"] == pytest.approx(
            round(statistics.median(values), 4)
        )
        assert "cost_vs_chance_iqr" in payload
        assert set(payload["stage_1a_baseline"]) == {
            "cost_efficiency",
            "stockout_avoidance",
            "budget_discipline",
            "reaction_to_risk_events",
        }

    def test_quarters_without_cost_vs_chance_omit_the_normalized_keys(self):
        payload = compute_stage_1a_baseline(
            _fake_quarters(SEED1_STOCKOUT_AVOIDANCE)
        )
        assert "cost_vs_chance_median" not in payload
        assert "cost_vs_chance_iqr" not in payload

    def test_old_baseline_file_loads_and_keeps_the_raw_cost_guard(self, tmp_path):
        import json

        from nowa_sandbox.stage_baseline import load_baseline_bundle

        path = tmp_path / "old_baseline.json"
        path.write_text(json.dumps({
            "stage_1a_baseline": {
                "cost_efficiency": 0.8,
                "stockout_avoidance": 0.9,
                "budget_discipline": 1.0,
                "reaction_to_risk_events": 0.8,
            },
            "stage_1a_spread_iqr": {
                "cost_efficiency": 0.0,
                "stockout_avoidance": 0.0,
                "budget_discipline": 0.0,
                "reaction_to_risk_events": 0.0,
            },
            "method": "median_all",
        }), encoding="utf-8")
        bundle = load_baseline_bundle(str(path))
        assert "cost_vs_chance_median" not in bundle
        evaluator = ProcurementFitnessEvaluator(stage="1b")
        vector = ProcurementFitnessVector(
            cost_efficiency=0.5,
            stockout_avoidance=0.9,
            budget_discipline=1.0,
            supplier_diversification=0.5,
            decision_consistency=0.5,
            reaction_to_risk_events=0.8,
            n_days=1,
            n_orders=1,
        )
        guard = evaluator.check_non_regression(
            vector,
            bundle["stage_1a_baseline"],
            stage_1a_spread_iqr=bundle["stage_1a_spread_iqr"],
        )
        # 0.5 is below 0.8 * 0.9. No normalized median, so the raw check stands.
        assert guard["cost_efficiency"] is False


class TestChanceCostEfficiency:
    """Analytical chance level on a world with known price multipliers."""

    def test_chance_matches_the_mean_supplier_score(self):
        from nowa_sandbox.procurement_world import ProcurementWorld, ProcurementWorldConfig

        world = ProcurementWorld(ProcurementWorldConfig(
            n_products=1,
            n_suppliers=3,
            days_per_quarter=1,
            seed=1,
            supplier_default_probability=0.0,
        ))
        ordered = sorted(world.suppliers)
        for sid, multiplier in zip(ordered, (0.85, 1.00, 1.15)):
            world.suppliers[sid].base_price_multiplier = multiplier
        product = next(iter(world.products))
        evaluator = ProcurementFitnessEvaluator(stage="1a")

        def entry(sid):
            return {
                "supplier_id": sid,
                "product_id": product,
                "result": {"status": "accepted"},
            }

        # Scores of 0.85 / 1.00 / 1.15 on [0.85, 1.15] are 1, 0.5, 0.
        # Uniform chance is their mean, 0.5, for every accepted order.
        cheap = evaluator._cost_efficiency(world, [entry(ordered[0])])
        chance = evaluator.chance_cost_efficiency(world, [entry(ordered[0])])
        assert cheap == pytest.approx(1.0)
        assert chance == pytest.approx(0.5)
        assert cheap - chance > 0

        expensive = evaluator._cost_efficiency(world, [entry(ordered[2])])
        chance_expensive = evaluator.chance_cost_efficiency(
            world, [entry(ordered[2])]
        )
        assert expensive == pytest.approx(0.0)
        assert chance_expensive == pytest.approx(0.5)
        assert expensive - chance_expensive < 0

        assert evaluator.chance_cost_efficiency(world, []) == pytest.approx(0.5)
        assert evaluator._cost_efficiency(world, []) == pytest.approx(0.5)

    def test_offer_world_chance_is_the_mean_offer_score(self):
        from nowa_sandbox.procurement_world import ProcurementWorld

        spec = {
            "budget": 1000.0,
            "products": [{
                "product_id": "A",
                "base_demand_per_day": 1.0,
                "demand_volatility": 0.0,
                "holding_cost_per_unit": 1.0,
                "stockout_penalty_per_unit": 1.0,
                "current_stock": 10.0,
                "reorder_point": 1.0,
            }],
            "suppliers": [
                {"supplier_id": "cheap", "reputation": 0.5},
                {"supplier_id": "mid", "reputation": 0.5},
                {"supplier_id": "dear", "reputation": 0.5},
            ],
            "offers": [
                {"product_id": "A", "supplier_id": "cheap", "unit_price": 10.0,
                 "lead_time_days": 3, "reliability": 0.9, "price_volatility": 0.0},
                {"product_id": "A", "supplier_id": "mid", "unit_price": 20.0,
                 "lead_time_days": 3, "reliability": 0.9, "price_volatility": 0.0},
                {"product_id": "A", "supplier_id": "dear", "unit_price": 40.0,
                 "lead_time_days": 3, "reliability": 0.9, "price_volatility": 0.0},
            ],
        }
        world = ProcurementWorld.from_quarter_spec(spec, days_per_quarter=1, seed=1)
        evaluator = ProcurementFitnessEvaluator(stage="1a")

        def entry(sid, price):
            return {
                "supplier_id": sid,
                "product_id": "A",
                "result": {"status": "accepted", "unit_price": price},
            }

        # (1 + 2/3 + 0) / 3 = 5/9.
        expected = (1.0 + (2.0 / 3.0) + 0.0) / 3.0
        cheap = evaluator._cost_efficiency(world, [entry("cheap", 10.0)])
        chance = evaluator.chance_cost_efficiency(world, [entry("cheap", 10.0)])
        assert chance == pytest.approx(expected)
        assert cheap - chance > 0
        dear = evaluator._cost_efficiency(world, [entry("dear", 40.0)])
        chance_dear = evaluator.chance_cost_efficiency(world, [entry("dear", 40.0)])
        assert chance_dear == pytest.approx(expected)
        assert dear - chance_dear < 0
