"""Tests for SandboxTrainer."""

import inspect
from types import SimpleNamespace

import pytest

from nowa_sandbox.procurement_motor_adapter import ProcurementMotorAdapter
from nowa_sandbox.procurement_world import ProcurementWorld, ProcurementWorldConfig
from nowa_sandbox.training_loop import (
    SandboxTrainer,
    SandboxTrainingResult,
)


TINY_CONFIG = dict(
    initial_budget=10_000.0, n_products=2, n_suppliers=2, days_per_quarter=15,
)


def _config(**overrides):
    params = dict(TINY_CONFIG)
    params.update(overrides)
    return ProcurementWorldConfig(**params)


class _ScriptedAgent:
    """Agent stub that replays a fixed action sequence."""

    def __init__(self, actions):
        self.actions = list(actions)
        self.calls = 0
        self.sleep_manager = _CountingSleepManager()

    def step(self, context_events, reward=0.0, intensity=1.0, novelty=0.0):
        action = self.actions[self.calls % len(self.actions)]
        self.calls += 1
        return action


class _CountingSleepManager:
    def __init__(self):
        self.cycles = 0

    def sleep_cycle(self):
        self.cycles += 1
        return {"patterns_consolidated": 0}


class _StepOnlyAgent:
    """Agent whose step() accepts nothing but the context (edge case E4)."""

    def __init__(self):
        self.contexts = []

    def step(self, context_events):
        self.contexts.append(list(context_events))
        return "wait_and_monitor"


class _NoStepAgent:
    """Agent that does not implement step() at all (edge case E4)."""


class TestSandboxTrainerBasic:

    def test_run_quarters_returns_result(
        self, sandbox_agent, encoder, fitness_evaluator
    ):
        trainer = SandboxTrainer(
            sandbox_agent, encoder, fitness_evaluator, sleep_every_n_days=5
        )
        result = trainer.run_quarters(
            n_quarters=2,
            world_config=_config(seed=1),
            stop_on_graduation=False,
        )
        assert isinstance(result, SandboxTrainingResult)
        assert len(result.quarters) == 2

    def test_each_quarter_has_fitness(
        self, sandbox_agent, encoder, fitness_evaluator
    ):
        trainer = SandboxTrainer(sandbox_agent, encoder, fitness_evaluator)
        result = trainer.run_quarters(n_quarters=1, world_config=_config(seed=1))
        assert result.quarters[0].fitness is not None
        assert result.quarters[0].graduation is not None

    def test_minimal_configuration_does_not_raise(
        self, sandbox_agent, encoder, fitness_evaluator
    ):
        """Acceptance criterion: n_products=1, n_suppliers=1, days=10."""
        trainer = SandboxTrainer(sandbox_agent, encoder, fitness_evaluator)
        config = ProcurementWorldConfig(
            initial_budget=5_000.0, n_products=1, n_suppliers=1,
            days_per_quarter=10, seed=1,
        )
        result = trainer.run_quarters(n_quarters=1, world_config=config)
        assert len(result.quarters) == 1

    def test_stop_on_graduation_halts_early(
        self, sandbox_agent, encoder, fitness_evaluator
    ):
        trainer = SandboxTrainer(sandbox_agent, encoder, fitness_evaluator)
        result = trainer.run_quarters(
            n_quarters=8, world_config=_config(days_per_quarter=10, seed=1),
            stop_on_graduation=True,
        )
        if result.graduated:
            assert len(result.quarters) == result.graduated_at_quarter

    def test_progress_callback_invoked(
        self, sandbox_agent, encoder, fitness_evaluator
    ):
        calls = []
        trainer = SandboxTrainer(sandbox_agent, encoder, fitness_evaluator)
        trainer.run_quarters(
            n_quarters=2, world_config=_config(days_per_quarter=10, seed=1),
            progress_callback=lambda i, total: calls.append((i, total)),
            stop_on_graduation=False,
        )
        assert len(calls) == 2
        assert calls[0] == (1, 2)

    def test_zero_quarters_returns_empty_result(
        self, sandbox_agent, encoder, fitness_evaluator
    ):
        trainer = SandboxTrainer(sandbox_agent, encoder, fitness_evaluator)
        result = trainer.run_quarters(n_quarters=0, world_config=_config(seed=1))
        assert result.quarters == []
        assert result.graduated is False


class TestQuarterIsolation:

    def test_each_quarter_uses_a_distinct_seed(
        self, sandbox_agent, encoder, fitness_evaluator
    ):
        """Constraint V1: new world per quarter, reproducible but varied."""
        trainer = SandboxTrainer(sandbox_agent, encoder, fitness_evaluator)
        seeds = [
            trainer._config_for_quarter(_config(seed=1), q).seed for q in range(1, 5)
        ]
        assert seeds == [1001, 1002, 1003, 1004]

    def test_seedless_config_falls_back_to_quarter_index(
        self, sandbox_agent, encoder, fitness_evaluator
    ):
        trainer = SandboxTrainer(sandbox_agent, encoder, fitness_evaluator)
        assert trainer._config_for_quarter(_config(seed=None), 3).seed == 3
        assert trainer._config_for_quarter(None, 4).seed == 4

    def test_seeds_1_through_5_do_not_share_a_world_in_quarters_1_through_60(
        self, sandbox_agent, encoder, fitness_evaluator
    ):
        """seed * 1000 + quarter: no shared world across seeds 1..5, quarters 1..60.

        The old ``base + quarter - 1`` formula made seed 2 quarter 30 the
        same world as seed 1 quarter 31.
        """
        trainer = SandboxTrainer(sandbox_agent, encoder, fitness_evaluator)
        seen = {}
        for seed in range(1, 6):
            for quarter in range(1, 61):
                cfg = trainer._config_for_quarter(
                    _config(seed=seed, n_products=2, n_suppliers=3, days_per_quarter=1),
                    quarter,
                )
                world = ProcurementWorld(cfg)
                fingerprint = (
                    tuple(
                        round(product.base_demand_per_day, 6)
                        for product in world.products.values()
                    ),
                    tuple(
                        round(supplier.base_price_multiplier, 6)
                        for supplier in world.suppliers.values()
                    ),
                )
                seen[(seed, quarter)] = (cfg.seed, fingerprint)

        world_seeds = [seen[(seed, quarter)][0] for seed in range(1, 6) for quarter in range(1, 61)]
        assert len(world_seeds) == len(set(world_seeds))
        for quarter in range(1, 61):
            fingerprints = [seen[(seed, quarter)][1] for seed in range(1, 6)]
            assert len(set(fingerprints)) == 5
        assert seen[(2, 30)][0] != seen[(1, 31)][0]
        assert seen[(2, 30)][1] != seen[(1, 31)][1]

    def test_quarters_produce_different_worlds(
        self, sandbox_agent, encoder, fitness_evaluator
    ):
        trainer = SandboxTrainer(sandbox_agent, encoder, fitness_evaluator)
        result = trainer.run_quarters(
            n_quarters=3, world_config=_config(seed=1), stop_on_graduation=False
        )
        summaries = [q.world_summary["total_holding_cost"] for q in result.quarters]
        assert len(set(summaries)) == 3

    def test_bankruptcy_in_one_quarter_does_not_break_the_next(
        self, sandbox_agent, encoder, fitness_evaluator
    ):
        trainer = SandboxTrainer(sandbox_agent, encoder, fitness_evaluator)
        config = ProcurementWorldConfig(
            initial_budget=1.0, n_products=2, n_suppliers=1,
            days_per_quarter=20, seed=1,
        )
        result = trainer.run_quarters(
            n_quarters=3, world_config=config, stop_on_graduation=False
        )
        assert len(result.quarters) == 3
        assert all(q.world_summary["bankrupt"] for q in result.quarters)

    def test_quarter_stops_early_on_bankruptcy(
        self, sandbox_agent, encoder, fitness_evaluator
    ):
        trainer = SandboxTrainer(sandbox_agent, encoder, fitness_evaluator)
        config = ProcurementWorldConfig(
            initial_budget=1.0, n_products=2, n_suppliers=1,
            days_per_quarter=90, seed=1,
        )
        result = trainer.run_quarters(n_quarters=1, world_config=config)
        assert result.quarters[0].world_summary["day"] < 90


class TestResume:

    def test_initial_result_continues_numbering(
        self, sandbox_agent, encoder, fitness_evaluator
    ):
        trainer = SandboxTrainer(sandbox_agent, encoder, fitness_evaluator)
        config = _config(days_per_quarter=10, seed=1)
        first = trainer.run_quarters(
            n_quarters=2, world_config=config, stop_on_graduation=False
        )
        second = trainer.run_quarters(
            n_quarters=2, world_config=config, stop_on_graduation=False,
            initial_result=first,
        )
        assert len(second.quarters) == 4
        assert [q.quarter_index for q in second.quarters] == [1, 2, 3, 4]

    def test_resume_reports_total_against_plan(
        self, sandbox_agent, encoder, fitness_evaluator
    ):
        trainer = SandboxTrainer(sandbox_agent, encoder, fitness_evaluator)
        config = _config(days_per_quarter=10, seed=1)
        first = trainer.run_quarters(
            n_quarters=1, world_config=config, stop_on_graduation=False
        )
        calls = []
        trainer.run_quarters(
            n_quarters=2, world_config=config, stop_on_graduation=False,
            initial_result=first,
            progress_callback=lambda i, total: calls.append((i, total)),
        )
        assert calls == [(2, 3), (3, 3)]


class TestAgentInterfaceAdaptation:

    def test_agent_without_step_defaults_to_waiting(
        self, encoder, fitness_evaluator
    ):
        """Edge case E4."""
        trainer = SandboxTrainer(_NoStepAgent(), encoder, fitness_evaluator)
        result = trainer.run_quarters(
            n_quarters=1, world_config=_config(days_per_quarter=10, seed=1)
        )
        assert len(result.quarters) == 1
        assert all(
            d["action"] == "wait_and_monitor" for d in trainer.last_decision_log
        )

    def test_context_only_step_signature_is_supported(
        self, encoder, fitness_evaluator
    ):
        agent = _StepOnlyAgent()
        trainer = SandboxTrainer(agent, encoder, fitness_evaluator)
        trainer.run_quarters(
            n_quarters=1, world_config=_config(days_per_quarter=10, seed=1)
        )
        assert len(agent.contexts) == 10
        assert all(isinstance(t, str) for ctx in agent.contexts for t in ctx)

    def test_decision_step_does_not_receive_waking_reward(
        self, encoder, fitness_evaluator
    ):
        received = []

        class _RewardCapturingAgent:
            sleep_manager = None

            def step(self, context_events, reward=0.0, intensity=1.0, novelty=0.0):
                received.append(reward)
                return "wait_and_monitor"

        trainer = SandboxTrainer(_RewardCapturingAgent(), encoder, fitness_evaluator)
        trainer.run_quarters(
            n_quarters=1, world_config=_config(days_per_quarter=20, seed=1)
        )
        assert len(received) == 20
        assert all(r == 0.0 for r in received)

    def test_unknown_action_does_not_break_the_loop(
        self, encoder, fitness_evaluator
    ):
        """Edge case E9."""
        agent = _ScriptedAgent(["teleport_inventory"])
        trainer = SandboxTrainer(agent, encoder, fitness_evaluator)
        trainer.run_quarters(
            n_quarters=1, world_config=_config(days_per_quarter=10, seed=1)
        )
        assert all(
            d["action"] == "wait_and_monitor" and d["result"] is None
            for d in trainer.last_decision_log
        )

    def test_decision_only_flag_is_passed_when_supported(
        self, encoder, fitness_evaluator
    ):
        """R3: waking step is asked for a decision, not a store/value update."""
        flags = []

        class _DecisionOnlyAgent:
            sleep_manager = None

            def step(self, context_events, decision_only=False):
                flags.append(decision_only)
                return "wait_and_monitor"

        trainer = SandboxTrainer(_DecisionOnlyAgent(), encoder, fitness_evaluator)
        trainer.run_quarters(
            n_quarters=1, world_config=_config(days_per_quarter=4, seed=1)
        )
        assert flags
        assert all(flag is True for flag in flags)

    def test_kwargs_step_also_receives_decision_only(
        self, encoder, fitness_evaluator
    ):
        flags = []

        class _KwargsAgent:
            sleep_manager = None

            def step(self, context_events, **kwargs):
                flags.append(kwargs.get("decision_only"))
                return "wait_and_monitor"

        trainer = SandboxTrainer(_KwargsAgent(), encoder, fitness_evaluator)
        trainer.run_quarters(
            n_quarters=1, world_config=_config(days_per_quarter=3, seed=1)
        )
        assert flags
        assert all(flag is True for flag in flags)

    def test_accepts_decision_only_introspection(self, encoder, fitness_evaluator):
        trainer = SandboxTrainer(_NoStepAgent(), encoder, fitness_evaluator)
        assert trainer._accepts_decision_only(
            lambda context_events, decision_only=False: None
        )
        assert trainer._accepts_decision_only(lambda context_events, **kwargs: None)
        assert not trainer._accepts_decision_only(lambda context_events: None)
        assert not trainer._accepts_decision_only(
            lambda context_events, reward=0.0: None
        )

    def test_agent_step_makes_exactly_one_call_even_when_typeerror_is_raised(
        self, encoder, fitness_evaluator
    ):
        """Introspection, not try/retry: an inner TypeError must not re-enter step()."""
        calls = []

        class _ExplodingAgent:
            sleep_manager = None

            def step(self, context_events, decision_only=False):
                calls.append({"decision_only": decision_only, "ctx": list(context_events)})
                raise TypeError("selector exploded after the decision started")

        trainer = SandboxTrainer(_ExplodingAgent(), encoder, fitness_evaluator)
        with pytest.raises(TypeError, match="selector exploded"):
            trainer._agent_step(["event:stock_critical_low"])
        assert calls == [
            {"decision_only": True, "ctx": ["event:stock_critical_low"]}
        ]
        source = inspect.getsource(SandboxTrainer._agent_step)
        assert "except TypeError" not in source

    def test_legacy_surrogate_decision_helpers_are_gone(self, encoder, fitness_evaluator):
        trainer = SandboxTrainer(_NoStepAgent(), encoder, fitness_evaluator)
        for name in (
            "_pick_priority_product",
            "_pick_supplier",
            "_decide_quantity",
            "_agent_decide",
            "_execute_action",
        ):
            assert not hasattr(trainer, name)
            assert not hasattr(SandboxTrainer, name)


def _result_status(entry):
    result = (entry or {}).get("result")
    if not isinstance(result, dict):
        return None
    return result.get("status")


class TestMotorAndPipelineRegression:
    """Former trainer-private action helpers now live on MotorAdapter + sensors."""

    def test_every_order_strategy_resolves_a_supplier_from_world_sensors(
        self, encoder, fitness_evaluator
    ):
        trainer = SandboxTrainer(_NoStepAgent(), encoder, fitness_evaluator)
        world = ProcurementWorld(_config(n_suppliers=3, seed=6))
        for product in world.products.values():
            product.current_stock = 0.0
            product.reorder_point = max(float(product.reorder_point), 50.0)
        stock = trainer._prepare_stock_observation(world)
        suppliers = trainer._prepare_supplier_observation(world, stock)
        budget = world.observe_budget_status()
        hippocampus = SimpleNamespace(experiences=[])
        for action, method in ProcurementMotorAdapter.SUPPLIER_STRATEGIES.items():
            params = trainer.motor_adapter.resolve(
                action, stock, suppliers, budget, hippocampus
            )
            if method is None:
                assert params is None
            else:
                assert params is not None
                assert params.supplier_id in world.suppliers
                assert params.qty > 0

    def test_no_supplier_available_yields_empty_order(
        self, encoder, fitness_evaluator
    ):
        agent = _ScriptedAgent(["urgent_reorder"])
        trainer = SandboxTrainer(agent, encoder, fitness_evaluator)
        world = ProcurementWorld(_config(seed=6))
        for product in world.products.values():
            product.current_stock = 0.0
            product.reorder_point = product.current_stock + 1
        for supplier in world.suppliers.values():
            supplier.is_defaulted = True
        log = trainer._run_single_quarter(world, n_days=5)
        assert log
        assert all(entry["result"] is None for entry in log)
        assert all(entry["supplier_id"] is None for entry in log)

    def test_no_product_needing_attention_yields_empty_order(
        self, encoder, fitness_evaluator
    ):
        agent = _ScriptedAgent(["urgent_reorder"])
        trainer = SandboxTrainer(agent, encoder, fitness_evaluator)
        world = ProcurementWorld(_config(seed=6))
        for product in world.products.values():
            product.reorder_point = 0.0
            product.current_stock = 1_000.0
        log = trainer._run_single_quarter(world, n_days=5)
        assert log
        assert all(entry["result"] is None for entry in log)

    def test_ordering_agent_produces_accepted_orders(
        self, encoder, fitness_evaluator
    ):
        agent = _ScriptedAgent(["urgent_reorder"])
        trainer = SandboxTrainer(agent, encoder, fitness_evaluator)
        trainer.run_quarters(
            n_quarters=1,
            world_config=_config(
                days_per_quarter=60, initial_budget=200_000.0, seed=1
            ),
        )
        accepted = [
            entry
            for entry in trainer.last_decision_log
            if _result_status(entry) == "accepted"
        ]
        assert accepted
        assert all(entry.get("supplier_id") and entry.get("qty") for entry in accepted)

    def test_inbound_stock_suppresses_duplicate_reorders(
        self, encoder, fitness_evaluator
    ):
        """Stock already in transit must count toward the reorder decision."""
        trainer = SandboxTrainer(_NoStepAgent(), encoder, fitness_evaluator)
        world = ProcurementWorld(
            _config(n_products=1, n_suppliers=1, seed=6, initial_budget=200_000.0)
        )
        product = next(iter(world.products.values()))
        product.current_stock = 0.0
        product.reorder_point = 100.0
        hippocampus = SimpleNamespace(experiences=[])

        stock = trainer._prepare_stock_observation(world)
        suppliers = trainer._prepare_supplier_observation(world, stock)
        first = trainer.motor_adapter.resolve(
            "urgent_reorder",
            stock,
            suppliers,
            world.observe_budget_status(),
            hippocampus,
        )
        assert first is not None
        assert first.product_id == product.product_id

        placed = world.place_order(first.supplier_id, first.product_id, 500)
        assert placed.get("status") == "accepted"
        stock_after = trainer._prepare_stock_observation(world)
        suppliers_after = trainer._prepare_supplier_observation(world, stock_after)
        second = trainer.motor_adapter.resolve(
            "urgent_reorder",
            stock_after,
            suppliers_after,
            world.observe_budget_status(),
            hippocampus,
        )
        assert second is None

    def test_inbound_quantities_aggregate_per_product(
        self, encoder, fitness_evaluator
    ):
        trainer = SandboxTrainer(_NoStepAgent(), encoder, fitness_evaluator)
        world = ProcurementWorld(
            _config(n_products=2, n_suppliers=1, seed=6, initial_budget=200_000.0)
        )
        world.place_order("supplier_000", "product_000", 30)
        world.place_order("supplier_000", "product_000", 20)
        stock = trainer._prepare_stock_observation(world)
        assert stock["product_000"]["inbound_quantity"] == 50
        assert stock["product_001"]["inbound_quantity"] == 0
        assert stock["product_000"]["projected_quantity"] == pytest.approx(
            stock["product_000"]["quantity"] + 50
        )

    def test_eager_agent_does_not_bankrupt_itself_by_reordering(
        self, encoder, fitness_evaluator
    ):
        """Regression: daily reordering during lead time used to cause bankruptcy."""
        agent = _ScriptedAgent(["place_order_reliable_supplier"])
        trainer = SandboxTrainer(agent, encoder, fitness_evaluator)
        result = trainer.run_quarters(
            n_quarters=1,
            world_config=ProcurementWorldConfig(
                initial_budget=100_000.0, n_products=10, n_suppliers=5,
                days_per_quarter=90, seed=1,
            ),
        )
        summary = result.quarters[0].world_summary
        assert summary["bankrupt"] is False
        assert summary["n_orders_placed"] < 90

    def test_quantity_uses_thirty_day_coverage_when_demand_is_sensed(
        self, encoder, fitness_evaluator
    ):
        """Stock sensors expose demand, so the motor covers 30 days of usage."""
        trainer = SandboxTrainer(_NoStepAgent(), encoder, fitness_evaluator)
        world = ProcurementWorld(_config(seed=6, initial_budget=1_000_000.0))
        product = next(iter(world.products.values()))
        product.current_stock = 0.0
        product.reorder_point = 100.0
        stock = trainer._prepare_stock_observation(world)
        suppliers = trainer._prepare_supplier_observation(world, stock)
        params = trainer.motor_adapter.resolve(
            "urgent_reorder",
            stock,
            suppliers,
            world.observe_budget_status(),
            SimpleNamespace(experiences=[]),
        )
        assert params is not None
        assert "base_demand_per_day" in stock[product.product_id]
        assert params.qty == pytest.approx(
            round(product.base_demand_per_day * 30.0, 1)
        )

    def test_quantity_covers_thirty_days_when_demand_is_observed(
        self, encoder, fitness_evaluator
    ):
        """v1.3 30-day coverage survives on MotorAdapter when sensors expose demand."""
        trainer = SandboxTrainer(_NoStepAgent(), encoder, fitness_evaluator)
        world = ProcurementWorld(_config(seed=6, initial_budget=1_000_000.0))
        product = next(iter(world.products.values()))
        product.current_stock = 0.0
        product.reorder_point = 100.0
        stock = trainer._prepare_stock_observation(world)
        stock[product.product_id]["base_demand_per_day"] = product.base_demand_per_day
        suppliers = trainer._prepare_supplier_observation(world, stock)
        params = trainer.motor_adapter.resolve(
            "urgent_reorder",
            stock,
            suppliers,
            world.observe_budget_status(),
            SimpleNamespace(experiences=[]),
        )
        assert params is not None
        assert params.qty == pytest.approx(
            round(product.base_demand_per_day * 30.0, 1)
        )


class TestSleepScheduling:

    def test_sleep_happens_only_on_boundaries(self, encoder, fitness_evaluator):
        agent = _ScriptedAgent(["wait_and_monitor"])
        trainer = SandboxTrainer(agent, encoder, fitness_evaluator, sleep_every_n_days=7)
        trainer.run_quarters(
            n_quarters=1, world_config=_config(days_per_quarter=21, seed=1)
        )
        assert agent.sleep_manager.cycles == 3

    def test_sleep_interval_longer_than_quarter_never_sleeps(
        self, encoder, fitness_evaluator
    ):
        """Edge case E8."""
        agent = _ScriptedAgent(["wait_and_monitor"])
        trainer = SandboxTrainer(agent, encoder, fitness_evaluator, sleep_every_n_days=500)
        trainer.run_quarters(
            n_quarters=1, world_config=_config(days_per_quarter=15, seed=1)
        )
        assert agent.sleep_manager.cycles == 0

    def test_zero_sleep_interval_is_clamped_to_daily(self, encoder, fitness_evaluator):
        agent = _ScriptedAgent(["wait_and_monitor"])
        trainer = SandboxTrainer(agent, encoder, fitness_evaluator, sleep_every_n_days=0)
        assert trainer.sleep_every_n_days == 1
        trainer.run_quarters(
            n_quarters=1, world_config=_config(days_per_quarter=5, seed=1)
        )
        assert agent.sleep_manager.cycles == 5



class TestSummaryOutput:

    def test_summary_returns_string(
        self, sandbox_agent, encoder, fitness_evaluator
    ):
        trainer = SandboxTrainer(sandbox_agent, encoder, fitness_evaluator)
        result = trainer.run_quarters(
            n_quarters=1, world_config=_config(days_per_quarter=10, seed=1)
        )
        summary = result.summary()
        assert isinstance(summary, str)
        assert "Quarter 1" in summary

    def test_summary_reports_non_graduation(
        self, sandbox_agent, encoder, fitness_evaluator
    ):
        trainer = SandboxTrainer(sandbox_agent, encoder, fitness_evaluator)
        result = trainer.run_quarters(
            n_quarters=1, world_config=_config(days_per_quarter=10, seed=1)
        )
        expected = "GRADUATED" if result.graduated else "NOT YET GRADUATED"
        assert expected in result.summary()

    def test_empty_result_summary_does_not_raise(self):
        assert "Sandbox Training Summary" in SandboxTrainingResult().summary()


class TestLeadTimeReplenishment:
    def test_purchase_data_world_can_clear_stockout_gate(
        self, encoder, fitness_evaluator
    ):
        """ROP below lead-time demand used to cap stockout_avoidance ~0.81.

        A prompt reorderer on worlds/purchase_data.json must now clear 0.85.
        """
        from pathlib import Path

        from nowa_sandbox.world_curriculum import WorldCurriculum

        path = Path(__file__).resolve().parents[1] / "worlds" / "purchase_data.json"
        cur = WorldCurriculum.load_json(path)
        trainer = SandboxTrainer(
            _ScriptedAgent(["urgent_reorder"]),
            encoder,
            fitness_evaluator,
            sleep_every_n_days=99,
        )
        result = trainer.run_curriculum_cycles(
            cur,
            world_config=_config(
                days_per_quarter=90,
                initial_budget=100_000.0,
                seed=42,
                supplier_default_probability=0.0,
                demand_shock_probability=0.0,
            ),
            stop_on_graduation=False,
            max_cycles=1,
        )
        assert len(result.quarters) == 1
        assert result.quarters[0].fitness.stockout_avoidance >= 0.85


def _situation_token_ok(token, product_id):
    text = str(token)
    if text.startswith("status:"):
        return True
    return str(product_id) in text.split(":")[1:]


class _ContextRecordingAgent:
    """Replays actions and keeps the context each day was decided on."""

    def __init__(self, actions):
        self.actions = list(actions)
        self.calls = 0
        self.contexts = []
        self.sleep_manager = None

    def step(self, context_events, reward=0.0, intensity=1.0, novelty=0.0):
        self.contexts.append(list(context_events))
        action = self.actions[self.calls % len(self.actions)]
        self.calls += 1
        return action


class TestDecisionLogSituation:

    def _run(self, encoder, fitness_evaluator, *, price_perception):
        agent = _ContextRecordingAgent(
            ["wait_and_monitor", "place_order_cheap_supplier"]
        )
        trainer = SandboxTrainer(
            agent,
            encoder,
            fitness_evaluator,
            sleep_every_n_days=99,
            price_perception=price_perception,
        )
        result = trainer.run_quarters(
            n_quarters=1,
            world_config=ProcurementWorldConfig(
                initial_budget=500_000.0,
                n_products=3,
                n_suppliers=3,
                days_per_quarter=30,
                seed=1,
            ),
            stop_on_graduation=False,
        )
        return agent, trainer, result

    def test_rows_carry_the_day_context_and_summary_diagnostics(
        self, encoder, fitness_evaluator
    ):
        agent, trainer, result = self._run(
            encoder, fitness_evaluator, price_perception=True
        )
        log = trainer.last_decision_log
        assert len(agent.contexts) == len(log)
        ordered = []
        idle = []
        old_fields = (
            "day", "action", "supplier_id", "product_id",
            "qty", "confidence", "result",
        )
        for entry, context in zip(log, agent.contexts):
            for key in old_fields:
                assert key in entry
            assert "tool" in entry and "entity" in entry
            assert "choice" in entry and "situation" in entry
            if entry["product_id"] is None:
                assert entry["entity"] is None
                assert entry["choice"] is None
                assert entry["tool"] is None
                assert entry["situation"] == []
                idle.append(entry)
                continue
            assert entry["entity"] == entry["product_id"]
            assert entry["choice"] == entry["supplier_id"]
            assert entry["tool"] == "place_order"
            for token in entry["situation"]:
                assert token in context
                assert _situation_token_ok(token, entry["product_id"])
            ordered.append(entry)
        assert ordered, "expected at least one day with an order"
        assert idle, "expected at least one day without an order"
        summary = result.quarters[0].world_summary
        assert "decision_consistency_by_product" in summary
        assert "decision_consistency_situations" in summary
        assert "decision_consistency_decisions_used" in summary

    def test_situation_omits_price_tokens_when_perception_is_off(
        self, encoder, fitness_evaluator
    ):
        _agent, trainer, _result = self._run(
            encoder, fitness_evaluator, price_perception=False
        )
        ordered = [
            entry for entry in trainer.last_decision_log
            if entry["product_id"] is not None
        ]
        assert ordered
        for entry in trainer.last_decision_log:
            assert not any(
                str(token).startswith("price:") for token in entry["situation"]
            )
