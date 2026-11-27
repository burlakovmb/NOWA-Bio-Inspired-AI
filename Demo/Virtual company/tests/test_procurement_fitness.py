"""Tests for ProcurementFitnessEvaluator."""

from dataclasses import replace

import pytest

from nowa_sandbox.procurement_fitness import (
    GRADUATION_THRESHOLDS,
    PROCUREMENT_CRITERIA,
    ProcurementFitnessEvaluator,
)
from nowa_sandbox.procurement_world import ProcurementWorld, ProcurementWorldConfig


def _order(supplier_id, product_id, day=1, status="accepted"):
    return {
        "day": day,
        "action": "place_order",
        "supplier_id": supplier_id,
        "product_id": product_id,
        "result": {"status": status},
    }


class TestFitnessVectorStructure:

    def test_evaluate_returns_all_criteria(self, small_world, fitness_evaluator):
        small_world.tick()
        vector = fitness_evaluator.evaluate(small_world, [])
        for criterion in PROCUREMENT_CRITERIA:
            assert hasattr(vector, criterion)
            value = getattr(vector, criterion)
            assert 0.0 <= value <= 1.0, f"{criterion}={value} out of [0,1]"

    def test_empty_decision_log_gives_neutral_scores(self, small_world, fitness_evaluator):
        for _ in range(10):
            small_world.tick()
        vector = fitness_evaluator.evaluate(small_world, [])
        assert vector.cost_efficiency == 0.5
        assert vector.supplier_diversification == 0.5

    def test_untouched_world_does_not_raise(self, small_world, fitness_evaluator):
        vector = fitness_evaluator.evaluate(small_world, [])
        for criterion in PROCUREMENT_CRITERIA:
            assert 0.0 <= getattr(vector, criterion) <= 1.0

    def test_as_dict_exposes_six_criteria(self, small_world, fitness_evaluator):
        vector = fitness_evaluator.evaluate(small_world, [])
        assert set(vector.as_dict().keys()) == set(PROCUREMENT_CRITERIA)

    def test_decision_log_without_result_key_does_not_raise(
        self, small_world, fitness_evaluator
    ):
        """Edge case E10: wait_and_monitor records carry no result."""
        small_world.tick()
        log = [
            {"day": 1, "action": "wait_and_monitor"},
            {"day": 2, "action": "place_order"},
        ]
        vector = fitness_evaluator.evaluate(small_world, log)
        assert 0.0 <= vector.cost_efficiency <= 1.0

    def test_rejected_orders_are_not_counted_as_purchases(
        self, small_world, fitness_evaluator
    ):
        supplier_id = next(iter(small_world.suppliers.keys()))
        log = [_order(supplier_id, "product_000", status="rejected") for _ in range(6)]
        vector = fitness_evaluator.evaluate(small_world, log)
        assert vector.supplier_diversification == 0.5


class TestDecisionLogCompatibility:
    """The evaluator must score the logs the training loop actually writes.

    The loop records the agent's strategy label ("urgent_reorder", ...), never
    a literal "place_order", so scoring must key off the world's response.
    """

    STRATEGY_ACTIONS = [
        "place_order_reliable_supplier",
        "place_order_cheap_supplier",
        "urgent_reorder",
        "diversify_supplier",
    ]

    @pytest.mark.parametrize("action", STRATEGY_ACTIONS)
    def test_strategy_labelled_orders_are_counted(
        self, small_world, fitness_evaluator, action
    ):
        supplier_id = next(iter(small_world.suppliers.keys()))
        log = [
            {
                "day": i, "action": action, "supplier_id": supplier_id,
                "product_id": "product_000", "qty": 10.0,
                "result": {"status": "accepted"},
            }
            for i in range(6)
        ]
        vector = fitness_evaluator.evaluate(small_world, log)
        assert vector.cost_efficiency != 0.5
        assert vector.supplier_diversification != 0.5
        assert vector.decision_consistency == 1.0

    def test_real_training_log_moves_order_dependent_criteria(
        self, encoder, fitness_evaluator
    ):
        from nowa_sandbox.training_loop import SandboxTrainer

        class _AlwaysOrders:
            sleep_manager = None

            def step(self, context_events, reward=0.0, intensity=1.0, novelty=0.0):
                return "place_order_cheap_supplier"

        trainer = SandboxTrainer(_AlwaysOrders(), encoder, fitness_evaluator)
        result = trainer.run_quarters(
            n_quarters=1,
            world_config=ProcurementWorldConfig(
                initial_budget=200_000.0, n_products=3, n_suppliers=3,
                days_per_quarter=60, seed=1,
            ),
        )
        accepted = [
            d for d in trainer.last_decision_log
            if isinstance(d.get("result"), dict)
            and d.get("result", {}).get("status") == "accepted"
        ]
        assert len(accepted) > 5, "precondition: the agent must have bought something"
        vector = result.quarters[0].fitness
        assert vector.cost_efficiency != 0.5
        assert vector.supplier_diversification != 0.5

    def test_no_action_records_are_not_orders(self, small_world, fitness_evaluator):
        log = [
            {"day": i, "action": "teleport", "result": {"status": "no_action"}}
            for i in range(6)
        ]
        vector = fitness_evaluator.evaluate(small_world, log)
        assert vector.cost_efficiency == 0.5
        assert vector.supplier_diversification == 0.5

    def test_none_result_records_are_not_orders(self, small_world, fitness_evaluator):
        """v2.0 wait/no-resolve days log result=None instead of status=no_action."""
        log = [
            {
                "day": i,
                "action": "wait_and_monitor",
                "supplier_id": None,
                "product_id": None,
                "qty": None,
                "result": None,
            }
            for i in range(6)
        ]
        vector = fitness_evaluator.evaluate(small_world, log)
        assert vector.cost_efficiency == 0.5
        assert vector.supplier_diversification == 0.5

    def test_unfulfilled_attempts_are_not_purchases_but_are_reactions(
        self, fitness_evaluator
    ):
        world = _world_with_events(
            [{"type": "supplier_defaulted", "supplier_id": "supplier_000"}]
        )
        log = [
            {
                "day": 3, "action": "urgent_reorder",
                "supplier_id": "supplier_000", "product_id": "product_000",
                "result": {"status": "rejected", "reason": "insufficient_budget"},
            }
        ]
        vector = fitness_evaluator.evaluate(world, log)
        assert vector.reaction_to_risk_events == 1.0
        assert vector.cost_efficiency == 0.5  # nothing was actually bought


class TestBudgetDiscipline:

    def test_full_score_when_budget_never_low(self, small_world, fitness_evaluator):
        small_world.tick()
        vector = fitness_evaluator.evaluate(small_world, [])
        assert vector.budget_discipline == 1.0

    def test_zero_score_on_bankruptcy(self, bankrupt_world, fitness_evaluator):
        vector = fitness_evaluator.evaluate(bankrupt_world, [])
        assert bankrupt_world.bankrupt is True
        assert vector.budget_discipline == 0.0

    def test_partial_score_when_budget_dips_low(self, fitness_evaluator):
        world = ProcurementWorld(ProcurementWorldConfig(
            initial_budget=1_000.0, n_products=2, n_suppliers=1, seed=2,
        ))
        world.tick()
        world.budget = 40.0  # 4% of the initial budget
        world.history[-1]["budget"] = 40.0
        vector = fitness_evaluator.evaluate(world, [])
        assert 0.0 < vector.budget_discipline < 1.0


class TestStockoutAvoidance:

    def test_no_stockouts_scores_one(self, small_world, fitness_evaluator):
        small_world.tick()
        for product in small_world.products.values():
            product.cumulative_stockout_units = 0.0
        vector = fitness_evaluator.evaluate(small_world, [])
        assert vector.stockout_avoidance == 1.0

    def test_massive_stockouts_score_zero(self, small_world, fitness_evaluator):
        small_world.tick()
        for product in small_world.products.values():
            product.cumulative_stockout_units = 10_000_000.0
        vector = fitness_evaluator.evaluate(small_world, [])
        assert vector.stockout_avoidance == 0.0

    def test_world_without_products_scores_one(self, fitness_evaluator):
        world = ProcurementWorld(ProcurementWorldConfig(n_products=0, seed=1))
        world.tick()
        vector = fitness_evaluator.evaluate(world, [])
        assert vector.stockout_avoidance == 1.0


class TestCostEfficiency:

    def test_cheap_supplier_orders_score_higher(self, small_world, fitness_evaluator):
        suppliers = list(small_world.suppliers.values())
        cheap = min(suppliers, key=lambda s: s.base_price_multiplier)
        expensive = max(suppliers, key=lambda s: s.base_price_multiplier)

        if cheap.supplier_id == expensive.supplier_id:
            pytest.skip("Not enough supplier price diversity in this seed")

        product_id = next(iter(small_world.products.keys()))
        cheap_vector = fitness_evaluator.evaluate(
            small_world, [_order(cheap.supplier_id, product_id)]
        )
        expensive_vector = fitness_evaluator.evaluate(
            small_world, [_order(expensive.supplier_id, product_id)]
        )
        assert cheap_vector.cost_efficiency >= expensive_vector.cost_efficiency

    def test_identical_price_multipliers_do_not_divide_by_zero(
        self, small_world, fitness_evaluator
    ):
        """Edge case E7."""
        for supplier in small_world.suppliers.values():
            supplier.base_price_multiplier = 1.0
        supplier_ids = list(small_world.suppliers.keys())
        log = [_order(sid, "product_000") for sid in supplier_ids]
        vector = fitness_evaluator.evaluate(small_world, log)
        assert 0.0 <= vector.cost_efficiency <= 1.0

    def test_unknown_supplier_in_log_gives_neutral_score(
        self, small_world, fitness_evaluator
    ):
        vector = fitness_evaluator.evaluate(
            small_world, [_order("ghost_supplier", "product_000")]
        )
        assert vector.cost_efficiency == 0.5

    def test_absolute_offer_prices_do_not_force_zero_cost(self, fitness_evaluator):
        """Curriculum unit prices (30/50) must not clamp cost_efficiency to 0."""
        world = ProcurementWorld.from_quarter_spec(
            {
                "budget": 100_000.0,
                "products": [
                    {
                        "product_id": "Банка 1 литр",
                        "base_demand_per_day": 10.0,
                        "demand_volatility": 0.15,
                        "holding_cost_per_unit": 1.0,
                        "stockout_penalty_per_unit": 10.0,
                        "current_stock": 200.0,
                        "reorder_point": 50.0,
                    }
                ],
                "suppliers": [
                    {"supplier_id": "supplier_001", "reputation": 0.5},
                    {"supplier_id": "supplier_002", "reputation": 0.5},
                ],
                "offers": [
                    {
                        "product_id": "Банка 1 литр",
                        "supplier_id": "supplier_001",
                        "unit_price": 30.0,
                        "lead_time_days": 5,
                        "reliability": 0.9,
                        "price_volatility": 0.05,
                    },
                    {
                        "product_id": "Банка 1 литр",
                        "supplier_id": "supplier_002",
                        "unit_price": 50.0,
                        "lead_time_days": 5,
                        "reliability": 0.9,
                        "price_volatility": 0.05,
                    },
                ],
            },
            days_per_quarter=5,
            seed=1,
        )
        cheap = fitness_evaluator.evaluate(
            world, [_order("supplier_001", "Банка 1 литр")]
        )
        expensive = fitness_evaluator.evaluate(
            world, [_order("supplier_002", "Банка 1 литр")]
        )
        assert cheap.cost_efficiency == pytest.approx(1.0)
        assert expensive.cost_efficiency == pytest.approx(0.0)

    def test_sole_offer_scores_full_cost_efficiency(self, fitness_evaluator):
        world = ProcurementWorld.from_quarter_spec(
            {
                "budget": 100_000.0,
                "products": [
                    {
                        "product_id": "Пакет",
                        "base_demand_per_day": 15.0,
                        "demand_volatility": 0.15,
                        "holding_cost_per_unit": 1.0,
                        "stockout_penalty_per_unit": 10.0,
                        "current_stock": 100.0,
                        "reorder_point": 50.0,
                    }
                ],
                "suppliers": [{"supplier_id": "supplier_002", "reputation": 0.5}],
                "offers": [
                    {
                        "product_id": "Пакет",
                        "supplier_id": "supplier_002",
                        "unit_price": 5.0,
                        "lead_time_days": 3,
                        "reliability": 0.9,
                        "price_volatility": 0.05,
                    }
                ],
            },
            days_per_quarter=5,
            seed=1,
        )
        vector = fitness_evaluator.evaluate(
            world, [_order("supplier_002", "Пакет")]
        )
        assert vector.cost_efficiency == pytest.approx(1.0)


class TestSupplierDiversification:

    def test_single_supplier_scores_low(self, small_world, fitness_evaluator):
        supplier_id = next(iter(small_world.suppliers.keys()))
        product_id = next(iter(small_world.products.keys()))
        log = [_order(supplier_id, product_id) for _ in range(6)]
        vector = fitness_evaluator.evaluate(small_world, log)
        assert vector.supplier_diversification < 0.5

    def test_multiple_suppliers_scores_higher(self, small_world, fitness_evaluator):
        supplier_ids = list(small_world.suppliers.keys())
        if len(supplier_ids) < 2:
            pytest.skip("Need at least 2 suppliers")
        product_id = next(iter(small_world.products.keys()))
        log = [
            _order(supplier_ids[i % len(supplier_ids)], product_id)
            for i in range(6)
        ]
        vector_diverse = fitness_evaluator.evaluate(small_world, log)

        single_log = [_order(supplier_ids[0], product_id) for _ in range(6)]
        vector_single = fitness_evaluator.evaluate(small_world, single_log)

        assert vector_diverse.supplier_diversification > vector_single.supplier_diversification

    def test_single_sourced_skus_do_not_block_stage_1b_diversity(
        self, fitness_evaluator
    ):
        """Jars only have supplier_001; packet split should still clear 0.40."""
        world = ProcurementWorld.from_quarter_spec(
            {
                "budget": 100_000.0,
                "products": [
                    {"product_id": "Банка 1 литр", "base_demand_per_day": 10.0},
                    {"product_id": "Банка 3 литра", "base_demand_per_day": 6.0},
                    {"product_id": "Пакет", "base_demand_per_day": 15.0},
                ],
                "suppliers": [
                    {"supplier_id": "supplier_001"},
                    {"supplier_id": "supplier_002"},
                    {"supplier_id": "supplier_003"},
                ],
                "offers": [
                    {"product_id": "Банка 1 литр", "supplier_id": "supplier_001"},
                    {"product_id": "Банка 3 литра", "supplier_id": "supplier_001"},
                    {"product_id": "Пакет", "supplier_id": "supplier_002"},
                    {"product_id": "Пакет", "supplier_id": "supplier_003"},
                ],
            }
        )
        log = (
            [_order("supplier_001", "Банка 1 литр") for _ in range(4)]
            + [_order("supplier_001", "Банка 3 литра") for _ in range(2)]
            + [_order("supplier_002", "Пакет"), _order("supplier_003", "Пакет")]
        )
        vector = fitness_evaluator.evaluate(world, log)
        assert vector.supplier_diversification >= 0.40


class TestDecisionConsistency:

    def test_few_orders_give_neutral_score(self, small_world, fitness_evaluator):
        log = [_order("supplier_000", "product_000") for _ in range(2)]
        vector = fitness_evaluator.evaluate(small_world, log)
        assert vector.decision_consistency == 0.5

    def test_three_identical_orders_meet_the_situation_minimum(
        self, small_world, fitness_evaluator
    ):
        log = [_order("supplier_000", "product_000") for _ in range(3)]
        vector = fitness_evaluator.evaluate(small_world, log)
        assert vector.decision_consistency == 1.0

    def test_two_situations_score_high_while_by_product_stays_low(
        self, small_world, fitness_evaluator
    ):
        cheap = [
            "price:product_000:cheap",
            "product:product_000",
            "status:below_reorder_point",
        ]
        expensive = [
            "price:product_000:expensive",
            "product:product_000",
            "status:below_reorder_point",
        ]
        log = []
        for _ in range(3):
            entry = _order("supplier_000", "product_000")
            entry["action"] = "place_order_cheap_supplier"
            entry["situation"] = list(cheap)
            log.append(entry)
        for _ in range(3):
            entry = _order("supplier_001", "product_000")
            entry["action"] = "place_order_reliable_supplier"
            entry["situation"] = list(expensive)
            log.append(entry)
        vector = fitness_evaluator.evaluate(small_world, log)
        assert vector.decision_consistency == 1.0
        diagnostics = fitness_evaluator.consistency_diagnostics(log)
        assert diagnostics["decision_consistency_by_product"] == 0.5
        assert diagnostics["decision_consistency_by_product"] < 1.0
        assert diagnostics["decision_consistency_situations"] == 2
        assert diagnostics["decision_consistency_decisions_used"] == 6

    def test_same_supplier_per_product_is_maximally_consistent(
        self, small_world, fitness_evaluator
    ):
        log = [_order("supplier_000", "product_000") for _ in range(6)]
        vector = fitness_evaluator.evaluate(small_world, log)
        assert vector.decision_consistency == 1.0

    def test_alternating_suppliers_score_lower(self, small_world, fitness_evaluator):
        log = [
            _order(f"supplier_{i % 2:03d}", "product_000")
            for i in range(6)
        ]
        supplier_eval = ProcurementFitnessEvaluator(
            consistency=replace(
                fitness_evaluator.consistency, choice_field="supplier_id"
            )
        )
        vector = supplier_eval.evaluate(small_world, log)
        assert vector.decision_consistency < 1.0

    def test_same_strategy_scores_high_while_supplier_by_product_stays_low(
        self, small_world, fitness_evaluator
    ):
        situation = [
            "price:product_000:cheap",
            "product:product_000",
            "status:below_reorder_point",
        ]
        log = []
        for i in range(6):
            entry = _order(f"supplier_{i % 2:03d}", "product_000")
            entry["action"] = "place_order_cheap_supplier"
            entry["situation"] = list(situation)
            log.append(entry)
        vector = fitness_evaluator.evaluate(small_world, log)
        diagnostics = fitness_evaluator.consistency_diagnostics(log)
        assert vector.decision_consistency == 1.0
        assert diagnostics["decision_consistency_situations"] == 1
        assert diagnostics["decision_consistency_decisions_used"] == 6
        assert diagnostics["decision_consistency_by_product"] == 0.5
        assert (
            diagnostics["decision_consistency_by_product"]
            < vector.decision_consistency
        )


def _world_with_events(events, day=3):
    world = ProcurementWorld(ProcurementWorldConfig(
        n_products=2, n_suppliers=2, seed=1,
    ))
    world.day = day
    world.history = [{"day": day, "events": list(events)}]
    return world


class TestReactionToRiskEvents:

    def test_no_risk_events_gives_vacuous_pass(self, small_world, fitness_evaluator):
        vector = fitness_evaluator.evaluate(small_world, [])
        assert vector.reaction_to_risk_events == 1.0

    def test_absorbed_demand_shock_does_not_require_an_order(
        self, fitness_evaluator
    ):
        world = _world_with_events(
            [{"type": "demand_shock", "product_id": "product_000"}]
        )
        vector = fitness_evaluator.evaluate(
            world, [{"day": 3, "action": "wait_and_monitor"}]
        )
        assert vector.reaction_to_risk_events == 1.0

    def test_stockout_alone_is_not_an_external_risk(self, fitness_evaluator):
        world = _world_with_events(
            [{"type": "stockout", "product_id": "product_000", "shortfall": 4.0}]
        )
        vector = fitness_evaluator.evaluate(
            world, [{"day": 3, "action": "wait_and_monitor"}]
        )
        assert vector.reaction_to_risk_events == 1.0

    def test_prompt_reaction_scores_high(self, fitness_evaluator):
        world = _world_with_events(
            [{"type": "supplier_defaulted", "supplier_id": "supplier_000"}]
        )
        log = [_order("supplier_001", "product_000", day=3)]
        vector = fitness_evaluator.evaluate(world, log)
        assert vector.reaction_to_risk_events == 1.0

    def test_order_intent_counts_even_if_motor_skips_submit(self, fitness_evaluator):
        world = _world_with_events(
            [
                {"type": "demand_shock", "product_id": "product_000"},
                {"type": "stockout", "product_id": "product_000", "shortfall": 2.0},
            ]
        )
        vector = fitness_evaluator.evaluate(
            world,
            [{"day": 3, "action": "urgent_reorder", "result": None}],
        )
        assert vector.reaction_to_risk_events == 1.0

    def test_no_reaction_scores_zero(self, fitness_evaluator):
        world = _world_with_events(
            [{"type": "supplier_defaulted", "supplier_id": "supplier_000"}]
        )
        vector = fitness_evaluator.evaluate(
            world, [{"day": 1, "action": "wait_and_monitor"}]
        )
        assert vector.reaction_to_risk_events == 0.0


class TestGraduationReport:

    def test_all_passed_requires_all_criteria(self, small_world, fitness_evaluator):
        small_world.tick()
        vector = fitness_evaluator.evaluate(small_world, [])
        report = fitness_evaluator.graduation_report(vector)
        for criterion in PROCUREMENT_CRITERIA:
            assert criterion in report
            assert report[criterion]["threshold"] == GRADUATION_THRESHOLDS[criterion]

    def test_all_passed_false_if_any_criterion_fails(
        self, bankrupt_world, fitness_evaluator
    ):
        vector = fitness_evaluator.evaluate(bankrupt_world, [])
        report = fitness_evaluator.graduation_report(vector)
        assert report["all_passed"] is False
        assert report["budget_discipline"]["passed"] is False

    def test_one_failing_gating_criterion_is_not_graduation(self, fitness_evaluator):
        """Everything else perfect still fails if a gating criterion is at zero."""
        from nowa_sandbox.procurement_fitness import ProcurementFitnessVector

        vector = ProcurementFitnessVector(
            cost_efficiency=1.0,
            stockout_avoidance=1.0,
            budget_discipline=1.0,
            supplier_diversification=1.0,
            decision_consistency=1.0,
            reaction_to_risk_events=0.0,
            n_days=90,
            n_orders=10,
        )
        report = fitness_evaluator.graduation_report(vector)
        assert report["all_passed"] is False
        assert report["reaction_to_risk_events"]["passed"] is False

    def test_everything_passing_graduates(self, fitness_evaluator):
        from nowa_sandbox.procurement_fitness import ProcurementFitnessVector

        vector = ProcurementFitnessVector(
            **{c: 1.0 for c in PROCUREMENT_CRITERIA}, n_days=90, n_orders=10
        )
        report = fitness_evaluator.graduation_report(vector)
        assert report["all_passed"] is True

    def test_report_carries_run_size(self, small_world, fitness_evaluator):
        small_world.tick()
        vector = fitness_evaluator.evaluate(small_world, [])
        report = fitness_evaluator.graduation_report(vector)
        assert report["n_days"] == small_world.day
        assert report["n_orders"] == 0


class TestThresholdOverrides:

    def test_thresholds_can_be_overridden(self):
        evaluator = ProcurementFitnessEvaluator(
            thresholds={"budget_discipline": 0.10}
        )
        assert evaluator.thresholds["budget_discipline"] == 0.10
        assert evaluator.thresholds["cost_efficiency"] == GRADUATION_THRESHOLDS[
            "cost_efficiency"
        ]

    def test_unknown_threshold_keys_are_ignored(self):
        evaluator = ProcurementFitnessEvaluator(thresholds={"made_up": 0.5})
        assert "made_up" not in evaluator.thresholds

    def test_overridden_thresholds_change_graduation(self, small_world):
        from nowa_sandbox.procurement_fitness import ProcurementFitnessVector

        vector = ProcurementFitnessVector(
            **{c: 0.55 for c in PROCUREMENT_CRITERIA}, n_days=90, n_orders=5
        )
        strict = ProcurementFitnessEvaluator()
        lenient = ProcurementFitnessEvaluator(
            thresholds={c: 0.5 for c in PROCUREMENT_CRITERIA}
        )
        assert strict.graduation_report(vector)["all_passed"] is False
        assert lenient.graduation_report(vector)["all_passed"] is True

    def test_module_default_thresholds_are_not_mutated(self):
        evaluator = ProcurementFitnessEvaluator(thresholds={"cost_efficiency": 0.01})
        assert GRADUATION_THRESHOLDS["cost_efficiency"] == 0.60
        assert evaluator.thresholds["cost_efficiency"] == 0.01
