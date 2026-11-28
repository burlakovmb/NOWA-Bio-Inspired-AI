"""Procurement facade over the domain-neutral scenario trainer.

Public construction stays ``SandboxTrainer(agent, encoder, fitness, ...)``.
The day and quarter loops live in :mod:`scenario_trainer` and call
:class:`procurement_scenario.ProcurementScenario`.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable, Dict, List, Mapping, Optional

from ._common import ensure_core_src_on_path
from .decision_consistency import ConsistencyConfig
from .price_memory import (
    DEFAULT_PRICE_BUCKET_Z,
    DEFAULT_PRICE_MEMORY_ALPHA,
    DEFAULT_PRICE_REWARD_GAIN,
    PriceMemory,
    felt_accepted_reward,
)
from .procurement_fitness import (
    DEFAULT_CONSISTENCY,
    ProcurementFitnessEvaluator,
    ProcurementFitnessVector,
)
from .procurement_hippocampus_seeder import ProcurementHippocampusSeeder
from .procurement_motor_adapter import OrderParams, ProcurementMotorAdapter
from .procurement_scenario import ProcurementScenario
from .procurement_world import (
    ProcurementWorld,
    ProcurementWorldConfig,
    VirtualSupplier,
    quarter_world_seed,
)
from .sandbox_encoder import SandboxEncoder
from .scenario_trainer import (
    QuarterResult,
    SandboxTrainingResult,
    ScenarioTrainer,
)
from .stage_mechanics import (
    GRADUATION_MIN_STREAK,
    current_qualifying_streak as _current_qualifying_streak,
    period_qualifies as _quarter_qualifies,
)

ensure_core_src_on_path()
from affective_space import AffectiveSpace  # noqa: E402


__all__ = [
    "SandboxTrainer",
    "SandboxTrainingResult",
    "QuarterResult",
    "GRADUATION_MIN_STREAK",
    "_quarter_qualifies",
    "_current_qualifying_streak",
]


class SandboxTrainer(ScenarioTrainer):
    """Buyer trainer. The loop is generic; these methods are the plugin leaves."""

    def __init__(
        self,
        agent: Any,
        encoder: SandboxEncoder,
        fitness_evaluator: ProcurementFitnessEvaluator,
        sleep_every_n_days: int = 7,
        stage_1a_baseline: Optional[Mapping[str, float]] = None,
        stage_1a_spread_iqr: Optional[Mapping[str, float]] = None,
        verbose_pipeline: bool = False,
        pipeline_logger: Optional[Callable[[str], None]] = None,
        supplier_set_count: int = 4,
        quarters_per_supplier_set: int = 5,
        cost_vs_chance_median: Optional[float] = None,
        cost_vs_chance_iqr: Optional[float] = None,
        price_perception: bool = True,
        price_memory_alpha: float = DEFAULT_PRICE_MEMORY_ALPHA,
        price_bucket_z: float = DEFAULT_PRICE_BUCKET_Z,
        price_reward_gain: float = DEFAULT_PRICE_REWARD_GAIN,
        consistency: Optional[ConsistencyConfig] = None,
    ):
        self.encoder = encoder
        self.fitness_evaluator = fitness_evaluator
        self.stage_1a_baseline = dict(stage_1a_baseline or {})
        self.stage_1a_spread_iqr = dict(stage_1a_spread_iqr or {})
        self.supplier_set_count = max(1, int(supplier_set_count))
        self.quarters_per_supplier_set = max(1, int(quarters_per_supplier_set))
        self.cost_vs_chance_median = cost_vs_chance_median
        self.cost_vs_chance_iqr = cost_vs_chance_iqr
        self.price_perception = bool(price_perception)
        self.price_memory_alpha = float(price_memory_alpha)
        self.price_bucket_z = float(price_bucket_z)
        self.price_reward_gain = float(price_reward_gain)
        self.consistency = (
            DEFAULT_CONSISTENCY if consistency is None else consistency
        )
        self.price_memory = PriceMemory(alpha=self.price_memory_alpha)
        # Stage 1b roster. Kept on the trainer, not in a local, so a
        # checkpointed run calling run_quarters(n_quarters=1) in a loop keeps
        # the same counterparties from one call to the next.
        self.carried_suppliers: Optional[Dict[str, VirtualSupplier]] = None
        self.motor_adapter = ProcurementMotorAdapter()
        self._seeder = ProcurementHippocampusSeeder()
        self._last_reward: float = 0.0
        self._quarter_order_counts: Dict[str, int] = {}
        self._quarter_strategy_counts: Dict[str, int] = {}
        self.scenario = ProcurementScenario(self)
        super().__init__(
            agent,
            self.scenario,
            sleep_every_n_days=sleep_every_n_days,
            verbose_pipeline=verbose_pipeline,
            pipeline_logger=pipeline_logger,
        )

    def run_quarters(
        self,
        n_quarters: int = 20,
        world_config: Optional[ProcurementWorldConfig] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        stop_on_graduation: bool = True,
        initial_result: Optional[SandboxTrainingResult] = None,
        carry_suppliers: bool = False,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> SandboxTrainingResult:
        """Run ``n_quarters`` additional quarters, appending to prior results.

        ``carry_suppliers`` is the Stage 1b mode: see
        :meth:`run_stage1b_persistent`.
        """
        return super().run_quarters(
            n_quarters=n_quarters,
            world_config=world_config,
            progress_callback=progress_callback,
            stop_on_graduation=stop_on_graduation,
            initial_result=initial_result,
            carry_roster=carry_suppliers,
            should_stop=should_stop,
        )

    def run_curriculum_cycles(
        self,
        curriculum: Any,
        *,
        world_config: Optional[ProcurementWorldConfig] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        stop_on_graduation: bool = True,
        initial_result: Optional[SandboxTrainingResult] = None,
        carry_suppliers: bool = False,
        should_stop: Optional[Callable[[], bool]] = None,
        max_cycles: Optional[int] = None,
    ) -> SandboxTrainingResult:
        return super().run_curriculum_cycles(
            curriculum,
            world_config=world_config,
            progress_callback=progress_callback,
            stop_on_graduation=stop_on_graduation,
            initial_result=initial_result,
            carry_roster=carry_suppliers,
            should_stop=should_stop,
            max_cycles=max_cycles,
        )

    def run_stage1b_persistent(
        self,
        n_quarters: int = 20,
        world_config: Optional[ProcurementWorldConfig] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        stop_on_graduation: bool = True,
        initial_result: Optional[SandboxTrainingResult] = None,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> SandboxTrainingResult:
        """Stage 1b: the roster survives inside a set, then a new set is drawn.

        The world is still rebuilt every quarter, so days, budget and pending
        orders reset. Inside a set, identity and history carry over.
        """
        config = replace(
            world_config or ProcurementWorldConfig(), persistent_suppliers=True
        )
        return super().run_quarters(
            n_quarters=n_quarters,
            world_config=config,
            progress_callback=progress_callback,
            stop_on_graduation=stop_on_graduation,
            initial_result=initial_result,
            carry_roster=True,
            should_stop=should_stop,
        )

    def _non_regression_for(
        self,
        fitness: ProcurementFitnessVector,
        cost_vs_chance: Optional[float] = None,
    ) -> Optional[Dict[str, bool]]:
        """Guard Stage 1a competence, but only where there is a baseline to guard.

        When the baseline recorded a normalized-savings median, cost is
        compared on ``cost_vs_chance``. Older baselines omit that median and
        keep the raw ``cost_efficiency`` check.
        """
        if self.fitness_evaluator.stage != "1b" or not self.stage_1a_baseline:
            return None
        extra: Dict[str, Any] = {}
        if self.cost_vs_chance_median is not None:
            extra["cost_vs_chance"] = cost_vs_chance
            extra["cost_vs_chance_median"] = self.cost_vs_chance_median
            extra["cost_vs_chance_iqr"] = self.cost_vs_chance_iqr
        return self.fitness_evaluator.check_non_regression(
            fitness,
            self.stage_1a_baseline,
            stage_1a_spread_iqr=self.stage_1a_spread_iqr or None,
            **extra,
        )

    @staticmethod
    def _config_for_quarter(
        world_config: Optional[ProcurementWorldConfig],
        quarter_index: int,
    ) -> ProcurementWorldConfig:
        """Give every quarter its own reproducible world (constraint V1).

        A set base seed becomes ``base * 1000 + quarter``; ``None`` stays the
        quarter index. Curriculum worlds still come from ``build_world``.
        """
        if world_config is None:
            return ProcurementWorldConfig(seed=quarter_world_seed(None, quarter_index))
        return replace(
            world_config,
            seed=quarter_world_seed(world_config.seed, quarter_index),
        )

    def _intent_to_action_type(self, action_intent: Any) -> str:
        if isinstance(action_intent, str):
            candidate = action_intent
        elif action_intent is None:
            candidate = "wait_and_monitor"
        else:
            candidate = ""
            for attr in ("action_type", "action", "label", "name"):
                value = getattr(action_intent, attr, None)
                if isinstance(value, str):
                    candidate = value
                    break
        if candidate in self.motor_adapter.SUPPLIER_STRATEGIES:
            return candidate
        return "wait_and_monitor"

    def _apply_order_feedback(self, last_order_result: dict) -> dict:
        """Apply AffectiveSpace.outcome_impulse; do not touch the value layer."""
        result = dict((last_order_result or {}).get("result") or {})
        status = result.get("status", "unknown")
        if status == "accepted":
            # Saved on the decision day. A missing key is an old caller with
            # no reference, not an invitation to read today's memory.
            reference = None
            if (
                isinstance(last_order_result, dict)
                and "price_reference" in last_order_result
            ):
                reference = last_order_result.get("price_reference")
            reward = self._felt_accepted_reward(result, reference)
        elif status == "rejected":
            reason = result.get("reason", "unknown")
            reward = -0.5 if reason == "insufficient_budget" else -0.3
        else:
            reward = 0.0

        impulse = None
        key = str(status or "").strip().lower()
        if key in ("accepted", "success", "ok", "rejected", "failed", "error"):
            impulse = AffectiveSpace.outcome_impulse(key, 1.0)
            space = getattr(self.agent, "affective_space", None)
            step_fn = getattr(space, "step", None)
            if callable(step_fn):
                try:
                    step_fn(external_impulses=[impulse], time_elapsed=0.0)
                except TypeError:
                    try:
                        step_fn(inputs=dict(getattr(impulse, "vector", {}) or {}))
                    except Exception:
                        pass
        self._last_reward = reward
        return {
            "status": status,
            "reward": reward,
            "inputs": dict(getattr(impulse, "vector", {}) or {}) if impulse is not None else {},
        }

    def _store_order_experience(
        self,
        context_events: List[str],
        order_params: OrderParams,
        order_result: dict,
    ) -> None:
        """Store the agent's concrete order episode for later sleep replay."""
        hippocampus = getattr(self.agent, "hippocampus", None)
        store_fn = getattr(hippocampus, "store", None)
        if not callable(store_fn):
            return
        status = str((order_result or {}).get("status", "unknown"))
        if status == "accepted":
            reference = self.price_memory.reference(str(order_params.product_id))
            reward = self._felt_accepted_reward(order_result, reference)
        else:
            reward = -0.3
        episode_tokens = list(context_events) + [
            f"supplier:{order_params.supplier_id}",
            f"product:{order_params.product_id}",
            f"result:{status}",
        ]
        try:
            path = self._seeder._build_path(
                episode_tokens, action=order_params.strategy
            )
            consequence_label = (
                "order_accepted" if status == "accepted" else "order_rejected"
            )
            consequence = self._seeder._build_consequence(consequence_label)
            stored = store_fn(
                path,
                consequence=consequence,
                intensity=abs(reward),
                reward=reward,
            )
        except Exception:
            return
        record_fn = getattr(self.agent, "_record_known_outcome", None)
        if stored is not None and callable(record_fn):
            action_id = str(order_params.strategy)
            stored.replay_action_id = action_id
            stored.context_events = list(context_events)
            record_fn(
                context_events=list(context_events),
                action_id=action_id,
                outcome=reward,
                episode=stored,
                intensity=abs(reward),
            )

    def _felt_accepted_reward(self, result: dict, reference) -> float:
        """Shared accepted-order reward for feedback and hippocampal store."""
        return felt_accepted_reward(
            (result or {}).get("unit_price"),
            reference,
            gain=self.price_reward_gain,
            enabled=self.price_perception,
        )

    def checkpoint_metadata(self) -> Dict[str, Any]:
        """Trainer state carried beside the agent checkpoint."""
        return {
            "carried_suppliers": self.carried_suppliers,
            "price_memory": self.price_memory.to_dict(),
        }

    def restore_checkpoint_metadata(self, metadata: Optional[Mapping[str, Any]]) -> None:
        """Restore trainer state. A checkpoint without price memory stays empty."""
        meta = dict(metadata or {})
        self.carried_suppliers = meta.get("carried_suppliers")
        self.price_memory = PriceMemory.from_dict(
            meta.get("price_memory"),
            alpha=self.price_memory_alpha,
        )

    @staticmethod
    def _prepare_stock_observation(world: ProcurementWorld) -> Dict[str, dict]:
        """Add projected stock to the read-only sensory snapshot."""
        stock = {
            str(pid): dict(info or {})
            for pid, info in world.observe_stock_levels().items()
        }
        inbound: Dict[str, float] = {}
        for order in world.observe_pending_orders():
            pid = str((order or {}).get("product_id") or "")
            if not pid:
                continue
            try:
                qty = float((order or {}).get("qty", 0.0))
            except (TypeError, ValueError):
                qty = 0.0
            inbound[pid] = inbound.get(pid, 0.0) + max(0.0, qty)
        for pid, info in stock.items():
            try:
                current = float(info.get("quantity", 0.0))
                reorder = float(info.get("reorder_point", 0.0))
            except (TypeError, ValueError):
                current, reorder = 0.0, 0.0
            projected = current + inbound.get(pid, 0.0)
            info["inbound_quantity"] = inbound.get(pid, 0.0)
            info["projected_quantity"] = projected
            info["projected_below_reorder_point"] = projected < reorder
            replenishment = reorder
            if "replenishment_point" in info:
                try:
                    replenishment = max(
                        reorder, float(info.get("replenishment_point", reorder))
                    )
                except (TypeError, ValueError):
                    replenishment = reorder
            info["projected_below_replenishment_point"] = projected < replenishment
        return stock

    @staticmethod
    def _prepare_supplier_observation(
        world: ProcurementWorld, stock_obs: Dict[str, dict]
    ) -> Dict[str, dict]:
        """Attach product quotes without exposing mutable world internals."""
        directory = {
            str(sid): dict(info or {})
            for sid, info in world.observe_supplier_directory().items()
        }
        for sid, info in directory.items():
            offers = {}
            for product_id in stock_obs:
                quote = world.observe_supplier_quote(sid, product_id, 1.0)
                if (quote or {}).get("status") == "ok":
                    offers[product_id] = dict(quote)
            info["offers"] = offers
        return directory

    def _log_pipeline_decision(
        self,
        day: int,
        context_events: List[str],
        activated_count: int,
        action_type: str,
        order_params: Optional[OrderParams],
        order_result: Optional[dict],
    ) -> None:
        self._emit_pipeline(
            f"[Day {day:3d}] context={len(context_events)} tokens | "
            f"activated={activated_count} memories | action={action_type}"
        )
        if order_params is not None:
            self._emit_pipeline(
                "         -> MotorAdapter: "
                f"{order_params.supplier_id}, {order_params.product_id}, "
                f"qty={order_params.qty:.1f}, confidence={order_params.confidence:.2f}"
            )
            status = (order_result or {}).get("status", "unknown")
            cost = (order_result or {}).get("cost")
            suffix = f" (cost={cost:.2f})" if isinstance(cost, (int, float)) else ""
            self._emit_pipeline(f"         -> place_order: {status}{suffix}")

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
