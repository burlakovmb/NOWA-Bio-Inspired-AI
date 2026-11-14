"""Sandbox training loop for the procurement agent."""

from __future__ import annotations

import inspect
import time
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Dict, List, Mapping, Optional

from ._common import ensure_core_src_on_path
from .procurement_fitness import ProcurementFitnessEvaluator, ProcurementFitnessVector
from .procurement_hippocampus_seeder import ProcurementHippocampusSeeder
from .procurement_motor_adapter import OrderParams, ProcurementMotorAdapter
from .procurement_world import (
    ProcurementWorld,
    ProcurementWorldConfig,
    VirtualSupplier,
)
from .sandbox_encoder import SandboxEncoder

ensure_core_src_on_path()
from affective_space import AffectiveSpace  # noqa: E402


GRADUATION_MIN_STREAK = 3
"""Section 26.7 / v1.1.1: Stage 1b graduation must hold for this many
consecutive *qualifying* quarters, not trigger on the first lucky pass."""


def _quarter_qualifies(quarter: "QuarterResult") -> bool:
    """A quarter counts toward the graduation streak only if it passed
    and did not buy that pass by regressing Stage 1a competence.

    For Stage 1a runs ``non_regression`` is always ``None`` (no baseline),
    so the check is a no-op and only ``all_passed`` matters — Stage 1a
    behaviour stays unchanged (patch v1.1.1 NR1).
    """
    if not (quarter.graduation or {}).get("all_passed"):
        return False
    if quarter.non_regression is None:
        return True
    return not any(ok is False for ok in quarter.non_regression.values())


def _stage_of_quarter(quarter: "QuarterResult") -> Optional[str]:
    return (quarter.graduation or {}).get("stage")


def _current_qualifying_streak(
    quarters: List["QuarterResult"],
    stage: Optional[str] = None,
) -> int:
    """Trailing run of qualifying quarters, recomputed from history.

    Kept as a pure function of ``result.quarters`` so a checkpoint resume
    gets the right answer for free — never trainer-local mutable state
    (patch v1.1.1 NR2).

    Inherited Stage 1a quarters must not pad a Stage 1b streak: resuming
    1a → 1b with two trailing 1a passes would otherwise graduate on the
    first lucky 1b quarter.
    """
    qs = list(quarters or [])
    if stage is None and qs:
        stage = _stage_of_quarter(qs[-1])
    streak = 0
    for quarter in reversed(qs):
        q_stage = _stage_of_quarter(quarter)
        if stage and q_stage and q_stage != stage:
            break
        if _quarter_qualifies(quarter):
            streak += 1
        else:
            break
    return streak


@dataclass
class QuarterResult:
    quarter_index: int
    fitness: ProcurementFitnessVector
    graduation: dict
    world_summary: dict
    processing_time_s: float
    non_regression: Optional[Dict[str, bool]] = None
    """Stage 1b only: per-criterion result of the Stage 1a non-regression guard."""

    @property
    def regressed_criteria(self) -> List[str]:
        return sorted(c for c, ok in (self.non_regression or {}).items() if not ok)


@dataclass
class SandboxTrainingResult:
    quarters: List[QuarterResult] = field(default_factory=list)
    graduated: bool = False
    graduated_at_quarter: Optional[int] = None

    def summary(self) -> str:
        lines = ["=== Sandbox Training Summary ==="]
        for i, q in enumerate(self.quarters):
            status = "PASS" if q.graduation.get("all_passed") else "..."
            regressed = q.regressed_criteria
            # Trailing qualifying streak as of this quarter — required by
            # v1.1.1 so a Stage 1b log shows why graduation did or did not fire.
            streak = _current_qualifying_streak(self.quarters[: i + 1])
            lines.append(
                f"Quarter {q.quarter_index}: [{status}] "
                f"cost_eff={q.fitness.cost_efficiency:.2f} "
                f"stockout_avoid={q.fitness.stockout_avoidance:.2f} "
                f"budget_disc={q.fitness.budget_discipline:.2f} "
                f"diversif={q.fitness.supplier_diversification:.2f} "
                f"consist={q.fitness.decision_consistency:.2f} "
                f"risk_react={q.fitness.reaction_to_risk_events:.2f} "
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
        """Longest run of consecutive *qualifying* quarters.

        Qualifying means ``all_passed`` and no Stage 1a regression (v1.1.1).
        For Stage 1a, where ``non_regression`` is always ``None``, this is
        identical to counting ``all_passed`` alone.
        """
        longest = streak = 0
        for quarter in self.quarters:
            if _quarter_qualifies(quarter):
                streak += 1
                longest = max(longest, streak)
            else:
                streak = 0
        return longest

    def graduation_sustained(
        self, min_streak: int = GRADUATION_MIN_STREAK
    ) -> bool:
        return self.longest_graduation_streak >= max(1, int(min_streak))

    def regressed_quarters(self) -> List[int]:
        """Passing quarters that bought their pass by losing Stage 1a ground."""
        return [
            q.quarter_index for q in self.quarters
            if q.graduation.get("all_passed") and q.regressed_criteria
        ]


class SandboxTrainer:
    """Orchestrate the training of one agent inside a ProcurementWorld.

    Compared with the Warriner demo, where NOWAColony.run_stimulus() pushed one
    stimulus through many agents, here one agent lives through many consecutive
    days in one continuous world — a fundamentally different regime (an
    episodic sequence rather than independent stimuli).
    """

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
    ):
        self.agent = agent
        self.encoder = encoder
        self.fitness_evaluator = fitness_evaluator
        self.sleep_every_n_days = max(1, int(sleep_every_n_days))
        plasticity = getattr(self.agent, "plasticity", None)
        if plasticity is not None and hasattr(plasticity, "expected_wake_interval_s"):
            # Same object Agent and load_agent bind onto the sleep manager.
            plasticity.expected_wake_interval_s = self.sleep_every_n_days * 86400.0
        self.stage_1a_baseline = dict(stage_1a_baseline or {})
        self.stage_1a_spread_iqr = dict(stage_1a_spread_iqr or {})
        self.last_decision_log: List[dict] = []
        # Stage 1b supplier continuity. Kept on the trainer, not in a local, so
        # that a checkpointed run calling run_quarters(n_quarters=1) in a loop
        # keeps the same counterparties from one call to the next.
        self.carried_suppliers: Optional[Dict[str, VirtualSupplier]] = None
        self.motor_adapter = ProcurementMotorAdapter()
        self._seeder = ProcurementHippocampusSeeder()
        self._last_reward: float = 0.0
        self.verbose_pipeline = bool(verbose_pipeline)
        self.pipeline_logger = pipeline_logger
        self._quarter_order_counts: Dict[str, int] = {}
        self._quarter_strategy_counts: Dict[str, int] = {}
        # Optional per-quarter entity overrides from the lab World tab.
        self.quarter_overrides: Dict[int, Dict[str, Any]] = {}
        # Authored curriculum (products/suppliers/offers per quarter).
        self.curriculum: Optional[Any] = None
        self.max_cycles: int = 500

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

        ``initial_result`` lets a checkpointed run continue from quarter N+1
        instead of starting over. ``carry_suppliers`` is the Stage 1b mode: see
        :meth:`run_stage1b_persistent`, which is the intended entry point.

        When ``self.curriculum`` is set, worlds are built from the authored
        plan: curriculum quarter ``((i-1) mod N)+1`` for global step ``i``.
        """
        result = initial_result or SandboxTrainingResult()
        start_index = len(result.quarters) + 1
        total = len(result.quarters) + max(0, int(n_quarters))
        curriculum = self.curriculum
        n_cur = int(getattr(curriculum, "n_quarters", 0) or 0) if curriculum else 0

        for offset in range(max(0, int(n_quarters))):
            if should_stop is not None and should_stop():
                break
            q_idx = start_index + offset
            if progress_callback:
                progress_callback(q_idx, total)

            start = time.perf_counter()
            config = self._config_for_quarter(world_config, q_idx)
            curriculum_q = None
            cycle = None
            if curriculum is not None and n_cur > 0:
                curriculum_q, cycle = curriculum.curriculum_quarter_for_step(q_idx)
                world = curriculum.build_world(
                    curriculum_q,
                    days_per_quarter=config.days_per_quarter,
                    seed=config.seed,
                    persistent_suppliers=config.persistent_suppliers,
                    demand_shock_probability=config.demand_shock_probability,
                    supplier_default_probability=config.supplier_default_probability,
                    base_config=config,
                )
            else:
                world = ProcurementWorld(config)
                overrides = (self.quarter_overrides or {}).get(q_idx)
                if overrides:
                    from nowa_sandbox.world_editor import apply_world_overrides

                    apply_world_overrides(world, overrides)

            if carry_suppliers and self.carried_suppliers:
                world.carry_supplier_state(self.carried_suppliers)

            decision_log = self._run_single_quarter(world, config.days_per_quarter)
            self.last_decision_log = decision_log
            if carry_suppliers:
                self.carried_suppliers = world.export_supplier_state()

            fitness = self.fitness_evaluator.evaluate(world, decision_log)
            graduation = self.fitness_evaluator.graduation_report(fitness)

            summary = world.summary()
            summary["action_counts"] = _action_counts(decision_log)
            summary["supplier_order_counts"] = dict(self._quarter_order_counts)
            summary["strategy_counts"] = dict(self._quarter_strategy_counts)
            if curriculum_q is not None:
                summary["curriculum_quarter"] = int(curriculum_q)
                summary["cycle"] = int(cycle or 1)
            try:
                from nowa_sandbox.world_editor import snapshot_world

                summary["entities"] = snapshot_world(world)
            except Exception:
                pass

            quarter_result = QuarterResult(
                quarter_index=q_idx,
                fitness=fitness,
                graduation=graduation,
                world_summary=summary,
                processing_time_s=time.perf_counter() - start,
                non_regression=self._non_regression_for(fitness),
            )
            result.quarters.append(quarter_result)

            # Stage 1b needs a sustained clean streak (v1.1.1). Stage 1a keeps
            # the single-quarter all_passed rule via min_streak=1 (NR1).
            min_streak = (
                GRADUATION_MIN_STREAK
                if self.fitness_evaluator.stage == "1b"
                else 1
            )
            streak = _current_qualifying_streak(
                result.quarters, stage=self.fitness_evaluator.stage
            )
            if streak >= min_streak and not result.graduated:
                result.graduated = True
                # First quarter of the qualifying streak, not the last (NR3).
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
        world_config: Optional[ProcurementWorldConfig] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        stop_on_graduation: bool = True,
        initial_result: Optional[SandboxTrainingResult] = None,
        carry_suppliers: bool = False,
        should_stop: Optional[Callable[[], bool]] = None,
        max_cycles: Optional[int] = None,
    ) -> SandboxTrainingResult:
        """Cycle curriculum quarters 1→N→1→… until graduation, stop, or max_cycles."""
        self.curriculum = curriculum
        n = int(getattr(curriculum, "n_quarters", 0) or 0)
        if n < 1:
            raise ValueError("curriculum must contain at least one quarter")
        cycles = int(max_cycles if max_cycles is not None else self.max_cycles)
        n_steps = max(1, cycles) * n
        return self.run_quarters(
            n_quarters=n_steps,
            world_config=world_config,
            progress_callback=progress_callback,
            stop_on_graduation=stop_on_graduation,
            initial_result=initial_result,
            carry_suppliers=carry_suppliers,
            should_stop=should_stop,
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
        """Stage 1b: same loop, but the suppliers survive between quarters.

        The world is still rebuilt every quarter, so days, budget and pending
        orders reset as before (spec 26.6.1 keeps budget per-quarter); only
        supplier identity and history carry over, which is what makes
        ``decision_consistency`` and ``supplier_diversification`` meaningful.
        """
        config = replace(
            world_config or ProcurementWorldConfig(), persistent_suppliers=True
        )
        return self.run_quarters(
            n_quarters=n_quarters,
            world_config=config,
            progress_callback=progress_callback,
            stop_on_graduation=stop_on_graduation,
            initial_result=initial_result,
            carry_suppliers=True,
            should_stop=should_stop,
        )

    def _non_regression_for(
        self, fitness: ProcurementFitnessVector
    ) -> Optional[Dict[str, bool]]:
        """Guard Stage 1a competence, but only where there is a baseline to guard."""
        if self.fitness_evaluator.stage != "1b" or not self.stage_1a_baseline:
            return None
        return self.fitness_evaluator.check_non_regression(
            fitness,
            self.stage_1a_baseline,
            stage_1a_spread_iqr=self.stage_1a_spread_iqr or None,
        )

    @staticmethod
    def _config_for_quarter(
        world_config: Optional[ProcurementWorldConfig],
        quarter_index: int,
    ) -> ProcurementWorldConfig:
        """Give every quarter its own reproducible world (constraint V1).

        Without this, a caller-supplied config would replay the identical world
        every quarter (fixed seed) or an unreproducible one (seed=None).
        """
        if world_config is None:
            return ProcurementWorldConfig(seed=quarter_index)
        base_seed = world_config.seed
        if base_seed is None:
            return replace(world_config, seed=quarter_index)
        return replace(world_config, seed=int(base_seed) + quarter_index - 1)

    def _run_single_quarter(self, world: ProcurementWorld, n_days: int) -> List[dict]:
        """Run one quarter through the full NOWA decision pipeline."""
        decision_log: List[dict] = []
        last_order_result: Optional[dict] = None
        self._quarter_order_counts = {}
        self._quarter_strategy_counts = {}

        for _ in range(max(0, int(n_days))):
            if world.bankrupt:
                break

            tick_result = world.history[-1] if world.history else {"events": []}
            context_events = self.encoder.encode_daily_context(world, tick_result)

            if last_order_result is not None:
                feedback = self._apply_order_feedback(last_order_result)
                self._log_pipeline_feedback(feedback)
                last_order_result = None

            activation_before = self._activation_snapshot()
            action_intent = self._agent_step(context_events, dt=86400.0)
            action_type = self._intent_to_action_type(action_intent)
            activated_count = self._activated_since(activation_before)

            stock_obs = self._prepare_stock_observation(world)
            supplier_obs = self._prepare_supplier_observation(world, stock_obs)
            order_params = self.motor_adapter.resolve(
                action_type=action_type,
                stock_obs=stock_obs,
                supplier_obs=supplier_obs,
                budget_obs=world.observe_budget_status(),
                hippocampus=getattr(self.agent, "hippocampus", None),
            )

            order_result = None
            if order_params is not None:
                order_result = world.place_order(
                    order_params.supplier_id,
                    order_params.product_id,
                    order_params.qty,
                )
                last_order_result = {
                    "params": order_params,
                    "result": order_result,
                    "world_state": world.observe_budget_status(),
                }
                self._store_order_experience(
                    context_events, order_params, order_result
                )
                if (order_result or {}).get("status") == "accepted":
                    sid = order_params.supplier_id
                    self._quarter_order_counts[sid] = (
                        self._quarter_order_counts.get(sid, 0) + 1
                    )
                    self._quarter_strategy_counts[action_type] = (
                        self._quarter_strategy_counts.get(action_type, 0) + 1
                    )

            decision_log.append({
                "day": world.day,
                "action": action_type,
                "supplier_id": order_params.supplier_id if order_params else None,
                "product_id": order_params.product_id if order_params else None,
                "qty": order_params.qty if order_params else None,
                "confidence": order_params.confidence if order_params else None,
                "result": order_result,
            })
            self._log_pipeline_decision(
                world.day,
                context_events,
                activated_count,
                action_type,
                order_params,
                order_result,
            )

            world.tick()
            if world.day % self.sleep_every_n_days == 0:
                self._agent_sleep()

        if last_order_result is not None:
            feedback = self._apply_order_feedback(last_order_result)
            self._log_pipeline_feedback(feedback)

        return decision_log

    def _agent_step(self, context_events: List[str], dt: float = 86400.0) -> Any:
        """Let the agent run its hippocampus→selector→BG→thalamus pipeline.

        Asks for a decision only, when the agent supports it: this loop records
        the concrete order episode and the affective consequence itself, so a
        waking store/value update inside ``step`` would duplicate the episode
        and label it before the outcome is known.

        Exactly one call is made. A ``TypeError`` raised from inside the agent
        is indistinguishable from a signature mismatch, and retrying it could
        repeat side effects the first attempt already applied, so support is
        decided by introspection instead.
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

        ``**kwargs`` counts as support: an agent that swallows unknown keywords
        (the sandbox fallback agent, test wrappers) has no waking learning to
        skip, so passing the flag is harmless there.
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
            reward = 0.4
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
        reward = 0.4 if status == "accepted" else -0.3
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

    def _activation_snapshot(self) -> Dict[int, float]:
        experiences = getattr(
            getattr(self.agent, "hippocampus", None), "experiences", []
        ) or []
        return {
            id(exp): float(getattr(exp, "last_activated", 0.0) or 0.0)
            for exp in list(experiences)
        }

    def _activated_since(self, before: Dict[int, float]) -> int:
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
        """Emit one diagnostic line.

        Kept ASCII-only on purpose: the CLI logger prints straight to a console
        that is cp1251/cp866 on a stock Russian Windows, where a single "→"
        aborts the whole run with UnicodeEncodeError mid-quarter.
        """
        if not self.verbose_pipeline:
            return
        if callable(self.pipeline_logger):
            self.pipeline_logger(message)
        else:
            print(message, flush=True)

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

    def _log_pipeline_feedback(self, feedback: dict) -> None:
        inputs = dict((feedback or {}).get("inputs") or {})
        if not inputs:
            return
        rendered = ", ".join(f"{key} {value:+.1f}" for key, value in inputs.items())
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
        if sleep_manager is not None and callable(getattr(sleep_manager, "sleep_cycle", None)):
            sleep_manager.sleep_cycle()


def _action_counts(decision_log: List[dict]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for entry in decision_log or []:
        action = str((entry or {}).get("action") or "unknown")
        counts[action] = counts.get(action, 0) + 1
    return counts


__all__ = [
    "SandboxTrainer",
    "SandboxTrainingResult",
    "QuarterResult",
    "GRADUATION_MIN_STREAK",
    "_quarter_qualifies",
    "_current_qualifying_streak",
]
