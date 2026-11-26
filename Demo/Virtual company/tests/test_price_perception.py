"""Coarse price tokens and felt cost of an accepted order (issue #76 task 2)."""

from types import SimpleNamespace

import pytest

from nowa_sandbox.price_memory import (
    ACCEPTED_BASE_REWARD,
    PriceMemory,
    classify_price_band,
    felt_accepted_reward,
    visible_unit_prices,
)
from nowa_sandbox.procurement_fitness import ProcurementFitnessEvaluator
from nowa_sandbox.procurement_motor_adapter import OrderParams
from nowa_sandbox.procurement_world import ProcurementWorld, ProcurementWorldConfig
from nowa_sandbox.sandbox_checkpoint import load_checkpoint, save_checkpoint
from nowa_sandbox.sandbox_encoder import SandboxEncoder
from nowa_sandbox.training_loop import SandboxTrainer, SandboxTrainingResult


def _alert_world():
    class World:
        base_price_multiplier = 1.0
        offers = {"sku": 10.0}

        def observe_stock_levels(self):
            return {"sku": {"below_reorder_point": True}}

        def observe_budget_status(self):
            return {"utilization_ratio": 0.1}

        def observe_supplier_quote(self, *args, **kwargs):
            raise AssertionError("encoder must use the quote book it was given")

    return World()


def _book(*prices, status="ok"):
    offers = {}
    for index, price in enumerate(prices):
        offers[f"s{index}"] = {
            "offers": {"sku": {"status": status, "unit_price": price}}
        }
    return offers


def _mixed_book():
    return {
        "hidden": {
            "offers": {
                "sku": {
                    "status": "unavailable",
                    "unit_price": 1.0,
                    "base_price_multiplier": 99.0,
                }
            }
        },
        "visible": {
            "offers": {
                "sku": {
                    "status": "ok",
                    "unit_price": 10.5,
                    "base_price_multiplier": 3.0,
                }
            }
        },
    }


def _assert_no_raw_numbers(tokens):
    for token in tokens:
        _, _, value = token.partition(":")
        with pytest.raises(ValueError):
            float(value)


def _trainer(agent=None):
    return SandboxTrainer(
        agent if agent is not None else SimpleNamespace(),
        SandboxEncoder(),
        ProcurementFitnessEvaluator(),
        price_reward_gain=0.3,
    )


class TestPriceTokens:

    def test_bands_at_the_threshold(self):
        encoder = SandboxEncoder()
        world = _alert_world()
        reference = {"sku": (10.0, 1.0)}
        # z = (mean - 10) / 1. ±0.5 is still average; just outside is a band.
        cases = [
            (10.5, "average"),
            (10.5 + 1e-4, "expensive"),
            (9.5, "average"),
            (9.5 - 1e-4, "cheap"),
        ]
        for price, band in cases:
            tokens = encoder.encode_daily_context(
                world, {"events": []}, _book(price), reference
            )
            assert f"price:sku:{band}" in tokens
            _assert_no_raw_numbers(tokens)

    def test_first_observation_is_average(self):
        encoder = SandboxEncoder()
        tokens = encoder.encode_daily_context(
            _alert_world(), {"events": []}, _book(1.0), None
        )
        assert "price:sku:average" in tokens
        assert classify_price_band([1.0], None, 0.5) == "average"

    def test_without_supplier_obs_matches_previous_tokens(self):
        encoder = SandboxEncoder()
        world = _alert_world()
        plain = encoder.encode_daily_context(world, {"events": []})
        explicit = encoder.encode_daily_context(world, {"events": []}, None, {"sku": (1.0, 1.0)})
        assert plain == explicit
        assert not any(token.startswith("price:") for token in plain)
        assert "product:sku" in plain

    def test_flag_off_omits_price_tokens(self):
        encoder = SandboxEncoder()
        world = _alert_world()
        plain = encoder.encode_daily_context(world, {"events": []})
        off = encoder.encode_daily_context(
            world,
            {"events": []},
            _book(1.0),
            {"sku": (10.0, 1.0)},
            price_perception=False,
        )
        assert off == plain
        assert not any(token.startswith("price:") for token in off)

    def test_hidden_world_fields_do_not_change_the_token(self):
        encoder = SandboxEncoder()
        world = _alert_world()
        book = _mixed_book()
        reference = {"sku": (10.0, 1.0)}
        first = encoder.encode_daily_context(world, {"events": []}, book, reference)
        world.base_price_multiplier = 80.0
        world.offers = {"sku": 0.01}
        book["visible"]["offers"]["sku"]["base_price_multiplier"] = 0.0
        second = encoder.encode_daily_context(world, {"events": []}, book, reference)
        assert first == second
        assert "price:sku:average" in first
        assert visible_unit_prices(book, "sku") == [10.5]

    def test_non_ok_quotes_are_ignored(self):
        encoder = SandboxEncoder()
        tokens = encoder.encode_daily_context(
            _alert_world(),
            {"events": []},
            _book(1.0, status="unavailable"),
            {"sku": (10.0, 1.0)},
        )
        assert "price:sku:average" in tokens


class TestFeltReward:

    def test_sign_and_bounds(self):
        gain = 0.3
        reference = (10.0, 1.0)
        cheaper = felt_accepted_reward(9.0, reference, gain=gain, enabled=True)
        dearer = felt_accepted_reward(11.0, reference, gain=gain, enabled=True)
        assert cheaper > ACCEPTED_BASE_REWARD
        assert dearer < ACCEPTED_BASE_REWARD
        floor = felt_accepted_reward(1_000.0, (1.0, 1.0), gain=gain, enabled=True)
        ceiling = felt_accepted_reward(0.0, (100.0, 1.0), gain=gain, enabled=True)
        assert floor == pytest.approx(ACCEPTED_BASE_REWARD - gain)
        assert ceiling == pytest.approx(ACCEPTED_BASE_REWARD + gain)

    def test_no_reference_or_flag_off_stays_flat(self):
        reference = (10.0, 1.0)
        assert felt_accepted_reward(1.0, None, gain=0.3, enabled=True) == pytest.approx(0.4)
        assert (
            felt_accepted_reward(1.0, reference, gain=0.3, enabled=False)
            == pytest.approx(0.4)
        )
        assert (
            felt_accepted_reward(None, reference, gain=0.3, enabled=True)
            == pytest.approx(0.4)
        )

    def test_store_and_feedback_share_the_decision_day_reference(self, sandbox_agent):
        trainer = _trainer(sandbox_agent)
        reference = (10.0, 1.0)
        trainer.price_memory = PriceMemory.from_dict(
            {"skus": {"product_000": {"ema": 10.0, "spread": 1.0}}},
            alpha=trainer.price_memory_alpha,
        )
        params = OrderParams(
            supplier_id="supplier_000",
            product_id="product_000",
            qty=2.0,
            strategy="urgent_reorder",
            confidence=0.8,
        )
        result = {"status": "accepted", "unit_price": 9.0}
        trainer._store_order_experience(["product:product_000"], params, result)
        stored = sandbox_agent.hippocampus.experiences[-1].td_committed_reward
        trainer.price_memory = PriceMemory.from_dict(
            {"skus": {"product_000": {"ema": 1.0, "spread": 1.0}}},
            alpha=0.1,
        )
        world = SimpleNamespace(base_price_multiplier=50.0, offers={"product_000": 0.01})
        feedback = trainer._apply_order_feedback(
            {
                "result": dict(result),
                "price_reference": reference,
                "world": world,
            }
        )
        world.base_price_multiplier = 0.01
        world.offers = {"product_000": 999.0}
        again = trainer._apply_order_feedback(
            {
                "result": dict(result),
                "price_reference": reference,
                "world": world,
            }
        )
        assert stored == pytest.approx(feedback["reward"])
        assert again["reward"] == pytest.approx(feedback["reward"])
        assert stored > 0.4
        assert stored == pytest.approx(
            felt_accepted_reward(9.0, reference, gain=0.3, enabled=True)
        )

    def test_rejected_rewards_are_unchanged(self, sandbox_agent):
        trainer = _trainer(sandbox_agent)
        budget = trainer._apply_order_feedback(
            {"result": {"status": "rejected", "reason": "insufficient_budget"}}
        )
        other = trainer._apply_order_feedback(
            {"result": {"status": "rejected", "reason": "supplier_defaulted"}}
        )
        assert budget["reward"] == pytest.approx(-0.5)
        assert other["reward"] == pytest.approx(-0.3)
        params = OrderParams(
            supplier_id="supplier_000",
            product_id="product_000",
            qty=1.0,
            strategy="urgent_reorder",
            confidence=0.5,
        )
        before = len(sandbox_agent.hippocampus.experiences)
        trainer._store_order_experience(
            ["product:product_000"],
            params,
            {"status": "rejected", "reason": "supplier_defaulted", "unit_price": 1.0},
        )
        stored = sandbox_agent.hippocampus.experiences[-1]
        assert len(sandbox_agent.hippocampus.experiences) == before + 1
        assert stored.td_committed_reward == pytest.approx(-0.3)

    def test_flag_off_store_ignores_a_known_reference(self, sandbox_agent):
        trainer = _trainer(sandbox_agent)
        trainer.price_perception = False
        trainer.price_memory = PriceMemory.from_dict(
            {"skus": {"product_000": {"ema": 10.0, "spread": 1.0}}},
            alpha=0.1,
        )
        params = OrderParams(
            supplier_id="supplier_000",
            product_id="product_000",
            qty=1.0,
            strategy="urgent_reorder",
            confidence=0.5,
        )
        trainer._store_order_experience(
            ["product:product_000"],
            params,
            {"status": "accepted", "unit_price": 1.0},
        )
        reward = sandbox_agent.hippocampus.experiences[-1].td_committed_reward
        assert reward == pytest.approx(0.4)


class TestPriceMemory:

    def test_reference_updates_only_after_it_is_read(self):
        memory = PriceMemory(alpha=0.5)
        assert memory.reference("sku") is None
        assert classify_price_band([10.0], memory.reference("sku"), 0.5) == "average"
        used = memory.snapshot()
        memory.update("sku", [10.0])
        assert used == {}
        assert memory.reference("sku") == pytest.approx((10.0, 0.0))
        decision = memory.reference("sku")
        memory.update("sku", [20.0])
        assert decision == pytest.approx((10.0, 0.0))
        assert memory.reference("sku") == pytest.approx((15.0, 5.0))

    def test_day_loop_does_not_peek_at_todays_quotes(self, encoder, fitness_evaluator):
        class Agent:
            sleep_manager = None

            def __init__(self):
                self.contexts = []

            def step(self, context_events, decision_only=False):
                self.contexts.append(list(context_events))
                return "wait_and_monitor"

        world = ProcurementWorld(
            ProcurementWorldConfig(n_products=1, n_suppliers=1, days_per_quarter=2, seed=1)
        )
        product = world.products["product_000"]
        product.current_stock = 0.0
        product.reorder_point = 1_000.0
        product.base_demand_per_day = 0.0
        agent = Agent()
        trainer = SandboxTrainer(
            agent, encoder, fitness_evaluator, sleep_every_n_days=7, price_memory_alpha=0.1
        )

        def _quotes(world, stock_obs):
            return {
                "s1": {"offers": {"product_000": {"status": "ok", "unit_price": 1.0}}},
                "s2": {"offers": {"product_000": {"status": "ok", "unit_price": 100.0}}},
            }

        trainer._prepare_supplier_observation = _quotes
        trainer._run_single_quarter(world, n_days=2)
        assert "price:product_000:average" in agent.contexts[0]
        assert "price:product_000:expensive" in agent.contexts[1]
        assert trainer.price_memory.reference("product_000") is not None

    def test_quotes_then_paid_price_update_after_the_read(self):
        memory = PriceMemory(alpha=1.0)
        book = {"s": {"offers": {"sku": {"status": "ok", "unit_price": 10.0}}}}
        assert memory.reference("sku") is None
        memory.observe_day(["sku"], book, ("sku", 20.0))
        assert memory.reference("sku") == pytest.approx((20.0, 10.0))
        memory.observe_day(["other"], {}, ("paid_only", 7.0))
        assert memory.reference("other") is None
        assert memory.reference("paid_only") == pytest.approx((7.0, 0.0))

    def test_old_checkpoint_without_the_field_loads_empty(
        self, tmp_path, sandbox_agent, encoder, fitness_evaluator
    ):
        path = save_checkpoint(
            tmp_path / "legacy.ckpt",
            sandbox_agent,
            SandboxTrainingResult(),
            metadata={"run_label": "legacy"},
        )
        checkpoint = load_checkpoint(path)
        assert "price_memory" not in checkpoint.metadata
        trainer = SandboxTrainer(sandbox_agent, encoder, fitness_evaluator)
        trainer.price_memory.update("sku", [4.0])
        trainer.carried_suppliers = {"supplier_000": object()}
        trainer.restore_checkpoint_metadata(checkpoint.metadata)
        assert trainer.price_memory.reference("sku") is None
        assert trainer.price_memory.to_dict()["skus"] == {}
        assert trainer.carried_suppliers is None
        assert checkpoint.metadata["run_label"] == "legacy"

    def test_checkpoint_round_trip_keeps_the_reference(
        self, tmp_path, sandbox_agent, encoder, fitness_evaluator
    ):
        trainer = SandboxTrainer(
            sandbox_agent, encoder, fitness_evaluator, price_memory_alpha=0.25
        )
        trainer.price_memory.update("sku", [4.0, 8.0])
        path = save_checkpoint(
            tmp_path / "price.ckpt",
            sandbox_agent,
            SandboxTrainingResult(),
            metadata=trainer.checkpoint_metadata(),
        )
        loaded = load_checkpoint(path)
        fresh = SandboxTrainer(
            sandbox_agent, encoder, fitness_evaluator, price_memory_alpha=0.25
        )
        fresh.restore_checkpoint_metadata(loaded.metadata)
        assert fresh.price_memory.reference("sku") == pytest.approx(
            trainer.price_memory.reference("sku")
        )
        assert PriceMemory.from_dict(None, alpha=0.25).snapshot() == {}
