"""Procurement binding of :class:`scenario.Scenario`.

World, motor, encoder, numeric memory and KPI formulas stay where they
are. This class only sequences them so the trainer never names them.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Optional

from .decision_consistency import decision_fields
from .price_memory import perceived_product_ids
from .procurement_world import ProcurementWorld
from .scenario import Call, Observation, Outcome, Scenario
from .stage_mechanics import roster_period_boundary


ORDER_TOOL = "place_order"


class ProcurementScenario(Scenario):
    """Buyer scenario. ``host`` is the SandboxTrainer that owns the leaves."""

    def __init__(self, host: Any):
        self.host = host

    def observe(self, world: Any) -> Observation:
        stock = self.host._prepare_stock_observation(world)
        quotes = self.host._prepare_supplier_observation(world, stock)
        return Observation(payload={
            "stock": stock,
            "quotes": quotes,
            "budget": world.observe_budget_status(),
            "memory_snapshot": self.host.price_memory.snapshot(),
        })

    def encode(self, world, tick_result, observation) -> list:
        payload = observation.payload
        return self.host.encoder.encode_daily_context(
            world,
            tick_result,
            payload["quotes"],
            payload["memory_snapshot"],
            price_perception=self.host.price_perception,
            price_bucket_z=self.host.price_bucket_z,
        )

    def action_label(self, intent: Any) -> str:
        return self.host._intent_to_action_type(intent)

    def resolve(self, action, observation, agent) -> Optional[Call]:
        payload = observation.payload
        params = self.host.motor_adapter.resolve(
            action_type=action,
            stock_obs=payload["stock"],
            supplier_obs=payload["quotes"],
            budget_obs=payload["budget"],
            hippocampus=getattr(agent, "hippocampus", None),
        )
        if params is None:
            return None
        arguments = asdict(params)
        arguments["action"] = action
        return Call(tool=ORDER_TOOL, arguments=arguments, raw=params)

    def apply(self, world, call, observation) -> Outcome:
        params = call.raw
        result = world.place_order(
            params.supplier_id,
            params.product_id,
            params.qty,
        )
        reference = observation.payload["memory_snapshot"].get(
            str(params.product_id)
        )
        pending = {
            "params": params,
            "result": result,
            "world_state": world.observe_budget_status(),
            "price_reference": reference,
        }
        return Outcome(result=result, pending=pending)

    def store(self, tokens, call, outcome) -> None:
        self.host._store_order_experience(list(tokens), call.raw, outcome.result)

    def note(self, action, call, outcome) -> None:
        if (outcome.result or {}).get("status") != "accepted":
            return
        sid = call.raw.supplier_id
        counts = self.host._quarter_order_counts
        counts[sid] = counts.get(sid, 0) + 1
        strategies = self.host._quarter_strategy_counts
        strategies[action] = strategies.get(action, 0) + 1

    def remember(self, tokens, observation, call, outcome) -> None:
        if not self.host.price_perception:
            return
        paid = None
        if (
            call is not None
            and outcome is not None
            and (outcome.result or {}).get("status") == "accepted"
        ):
            paid = (
                call.raw.product_id,
                (outcome.result or {}).get("unit_price"),
            )
        self.host.price_memory.observe_day(
            perceived_product_ids(tokens),
            observation.payload["quotes"],
            paid,
        )

    def row(self, *, day, action, call, outcome, tokens) -> dict:
        params = None if call is None else call.raw
        result = None if outcome is None else outcome.result
        call_for_fields = None
        if params is not None:
            call_for_fields = asdict(params)
            call_for_fields["action"] = action
        return {
            "day": day,
            "action": action,
            "supplier_id": params.supplier_id if params else None,
            "product_id": params.product_id if params else None,
            "qty": params.qty if params else None,
            "confidence": params.confidence if params else None,
            "result": result,
            **decision_fields(
                call_for_fields,
                ORDER_TOOL if params else None,
                tokens,
                self.host.consistency,
            ),
        }

    def trace(self, host, world, tokens, activated, action, call, outcome) -> None:
        params = None if call is None else call.raw
        result = None if outcome is None else outcome.result
        host._log_pipeline_decision(
            self.day(world),
            list(tokens),
            activated,
            action,
            params,
            result,
        )

    def apply_feedback(self, pending) -> dict:
        return self.host._apply_order_feedback(dict(pending))

    def begin_period(self) -> None:
        self.host._quarter_order_counts = {}
        self.host._quarter_strategy_counts = {}

    def evaluate(self, world, decision_log):
        return self.host.fitness_evaluator.evaluate(world, decision_log)

    def graduation_report(self, fitness) -> dict:
        return self.host.fitness_evaluator.graduation_report(fitness)

    def summary_extras(
        self, world, decision_log, fitness, period_index, result, carry_roster, labels,
    ) -> dict:
        extras = {
            "supplier_order_counts": dict(self.host._quarter_order_counts),
            "strategy_counts": dict(self.host._quarter_strategy_counts),
        }
        extras.update(self.host.fitness_evaluator.consistency_diagnostics(decision_log))
        chance = float(
            self.host.fitness_evaluator.chance_cost_efficiency(world, decision_log)
        )
        extras["chance_cost_efficiency"] = chance
        extras["cost_vs_chance"] = float(fitness.cost_efficiency) - chance
        stage_start = getattr(result, "stage_1b_start_quarter", None)
        if carry_roster and stage_start is not None:
            period = self.host.quarters_per_supplier_set
            extras["supplier_set_index"] = int((period_index - int(stage_start)) // period)
            extras["supplier_set_count"] = int(self.host.supplier_set_count)
        extras.update(dict(labels or {}))
        try:
            from nowa_sandbox.world_editor import snapshot_world

            extras["entities"] = snapshot_world(world)
        except Exception:
            pass
        return extras

    def non_regression(self, fitness, summary):
        return self.host._non_regression_for(
            fitness, summary.get("cost_vs_chance")
        )

    def config_for_step(self, world_config, period_index):
        return self.host._config_for_quarter(world_config, period_index)

    def open_period(self, config, period_index):
        host = self.host
        curriculum = host.curriculum
        n_cur = int(getattr(curriculum, "n_quarters", 0) or 0) if curriculum else 0
        labels: dict = {}
        if curriculum is not None and n_cur > 0:
            curriculum_q, cycle = curriculum.curriculum_quarter_for_step(period_index)
            world = curriculum.build_world(
                curriculum_q,
                days_per_quarter=config.days_per_quarter,
                seed=config.seed,
                persistent_suppliers=config.persistent_suppliers,
                demand_shock_probability=config.demand_shock_probability,
                supplier_default_probability=config.supplier_default_probability,
                base_config=config,
            )
            labels["curriculum_quarter"] = int(curriculum_q)
            labels["cycle"] = int(cycle or 1)
            return world, labels
        world = ProcurementWorld(config)
        overrides = (host.quarter_overrides or {}).get(period_index)
        if overrides:
            from nowa_sandbox.world_editor import apply_world_overrides

            apply_world_overrides(world, overrides)
        return world, labels

    def stage_name(self) -> str:
        return self.host.fitness_evaluator.stage

    def minimum_streak(self) -> int:
        from .stage_mechanics import GRADUATION_MIN_STREAK

        if self.stage_name() == "1b":
            return GRADUATION_MIN_STREAK
        return 1

    def has_roster(self) -> bool:
        return bool(self.host.carried_suppliers)

    def drop_roster(self) -> None:
        self.host.carried_suppliers = None

    def apply_roster(self, world) -> None:
        if self.host.carried_suppliers:
            world.carry_supplier_state(self.host.carried_suppliers)

    def capture_roster(self, world) -> None:
        self.host.carried_suppliers = world.export_supplier_state()

    def roster_boundary(self, period_index, stage_start) -> bool:
        return roster_period_boundary(
            period_index,
            stage_start,
            self.host.quarters_per_supplier_set,
        )


__all__ = ["ORDER_TOOL", "ProcurementScenario"]
