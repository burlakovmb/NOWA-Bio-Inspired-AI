"""Headless run controller for the procurement sandbox lab GUI.

Owns threading, soft-stop between quarters, checkpointing, multi-seed sweeps
and Stage 1a report/baseline writes — so the tkinter layer stays thin.
"""

from __future__ import annotations

import argparse
import random
import threading
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from nowa_sandbox.procurement_fitness import (
    PROCUREMENT_CRITERIA,
    ProcurementFitnessEvaluator,
)
from nowa_sandbox.run_sandbox import (
    DEMO_ROOT,
    _resolve_baseline,
    _stage_of,
    resolve_config,
    resolve_config_path,
)
from nowa_sandbox.sandbox_agent_factory import (
    create_procurement_agent,
    seed_professional_intuition,
)
from nowa_sandbox.sandbox_checkpoint import (
    load_checkpoint,
    restore_agent,
    save_checkpoint,
)
from nowa_sandbox.sandbox_config import SandboxConfig
from nowa_sandbox.sandbox_encoder import SandboxEncoder
from nowa_sandbox.sandbox_observer import SandboxObserver
from nowa_sandbox.stage1a_report import (
    check_readiness,
    pick_baseline_run,
    summarize_run,
)
from nowa_sandbox.stage_baseline import save_baseline
from nowa_sandbox.training_loop import (
    GRADUATION_MIN_STREAK,
    SandboxTrainer,
    SandboxTrainingResult,
    _current_qualifying_streak,
)
from nowa_sandbox.quarter_diagnostics import nr_floors_from_baseline


LogFn = Callable[[str], None]
QuarterFn = Callable[[Dict[str, Any]], None]
DoneFn = Callable[[Optional[SandboxTrainingResult], Optional[BaseException]], None]


@dataclass
class RunSpec:
    """Parameters for one Stage 1a/1b training run."""

    stage: str = "1a"
    seed: int = 42
    quarters: int = 30
    days_per_quarter: Optional[int] = None
    budget: Optional[float] = None
    products: Optional[int] = None
    suppliers: Optional[int] = None
    sleep_every: Optional[int] = None
    demand_shock_probability: Optional[float] = None
    supplier_default_probability: Optional[float] = None
    max_lead_time_days: Optional[int] = None
    max_demand_per_day: Optional[float] = None
    min_supplier_reliability: Optional[float] = None
    config_path: str = "configs/default_world.yaml"
    baseline_from: Optional[str] = None
    resume_from: Optional[str] = None
    output: str = "results/sandbox_run.json"
    checkpoint: Optional[str] = "checkpoints/sandbox_run.ckpt"
    stop_on_graduation: bool = False
    seed_intuition: bool = True
    threshold_overrides: Dict[str, float] = field(default_factory=dict)
    quarter_overrides: Dict[int, Dict[str, Any]] = field(default_factory=dict)
    curriculum: Optional[Any] = None
    max_cycles: int = 500


@dataclass
class SweepSpec:
    """Multi-seed Stage 1a sweep."""

    seeds: List[int] = field(default_factory=lambda: [1, 7, 42, 100, 200])
    quarters: int = 30
    config_path: str = "configs/default_world.yaml"
    stop_on_graduation: bool = False
    output_template: str = "results/stage1a_lab_seed{seed}.json"
    checkpoint_template: str = "checkpoints/stage1a_lab_seed{seed}.ckpt"


def quarter_to_record(quarter: Any) -> Dict[str, Any]:
    """Normalize a QuarterResult (or dict) for the GUI table/charts."""
    return SandboxObserver._as_record(quarter)


def records_from_result(result: Optional[SandboxTrainingResult]) -> List[Dict[str, Any]]:
    if result is None:
        return []
    return [quarter_to_record(q) for q in result.quarters]


def load_results_json(path: str) -> List[Dict[str, Any]]:
    import json

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [
            dict(row) if isinstance(row, dict) else quarter_to_record(row)
            for row in data
        ]
    if isinstance(data, dict) and isinstance(data.get("quarters"), list):
        return [dict(row) for row in data["quarters"] if isinstance(row, dict)]
    raise ValueError(f"{path} is not a sandbox results list")


class RunController:
    """Background training with cooperative soft-stop between quarters."""

    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._busy = False
        self.last_result: Optional[SandboxTrainingResult] = None
        self.last_error: Optional[BaseException] = None
        self.last_checkpoint: Optional[str] = None
        self.last_output: Optional[str] = None
        self.last_thresholds: Dict[str, float] = {}
        self.last_nr_floors: Dict[str, float] = {}
        self.last_stage: str = "1a"

    @property
    def is_busy(self) -> bool:
        with self._lock:
            return self._busy

    def request_stop(self) -> None:
        """Soft-stop: finish the current quarter, checkpoint, then halt."""
        self._stop.set()

    def start_run(
        self,
        spec: RunSpec,
        *,
        on_log: Optional[LogFn] = None,
        on_quarter: Optional[QuarterFn] = None,
        on_done: Optional[DoneFn] = None,
    ) -> None:
        self._start_thread(
            target=self._run_single,
            args=(spec, on_log, on_quarter, on_done),
            name="sandbox-run",
        )

    def start_sweep(
        self,
        spec: SweepSpec,
        *,
        on_log: Optional[LogFn] = None,
        on_quarter: Optional[QuarterFn] = None,
        on_done: Optional[DoneFn] = None,
    ) -> None:
        self._start_thread(
            target=self._run_sweep,
            args=(spec, on_log, on_quarter, on_done),
            name="sandbox-sweep",
        )

    def write_baseline_report(
        self,
        result_paths: Sequence[str],
        write_baseline_to: Optional[str] = None,
        method: str = "median_all",
    ) -> Dict[str, Any]:
        """Synchronous Stage 1a readiness report (+ optional baseline write)."""
        rows = [summarize_run(path, method=method) for path in result_paths]
        readiness = check_readiness(rows)
        payload: Dict[str, Any] = {
            "rows": rows,
            "readiness": readiness,
            "baseline_path": None,
            "baseline": None,
            "refused": None,
        }
        if write_baseline_to:
            if method == "mean_best":
                payload["refused"] = (
                    "Refusing to write a baseline computed with method=mean_best."
                )
                return payload
            chosen = pick_baseline_run(rows)
            if chosen is None:
                payload["refused"] = "No graduated run: refusing to write a baseline."
                return payload
            if chosen.get("baseline_error") and method == "median_all":
                payload["refused"] = (
                    f"Refusing baseline from {chosen['name']}: "
                    f"{chosen['baseline_error']}"
                )
                return payload
            out = dict(chosen.get("baseline_payload") or {})
            out["stage_1a_baseline"] = chosen["baseline"]
            if chosen.get("spread_iqr"):
                out["stage_1a_spread_iqr"] = chosen["spread_iqr"]
            out["computed_from_quarters"] = chosen["baseline_quarters"]
            out["from_successful_quarters"] = chosen["baseline_from_successful"]
            out["method"] = chosen.get("baseline_method") or method
            save_baseline(write_baseline_to, out, source=chosen["path"])
            payload["baseline_path"] = write_baseline_to
            payload["baseline"] = out
            payload["chosen"] = chosen["name"]
        return payload

    def _start_thread(self, target, args, name: str) -> None:
        with self._lock:
            if self._busy:
                raise RuntimeError("A sandbox run is already in progress")
            self._busy = True
            self._stop.clear()
            self.last_error = None
        self._thread = threading.Thread(
            target=target, args=args, name=name, daemon=True
        )
        self._thread.start()

    def _finish(
        self,
        result: Optional[SandboxTrainingResult],
        error: Optional[BaseException],
        on_done: Optional[DoneFn],
    ) -> None:
        self.last_result = result
        self.last_error = error
        with self._lock:
            self._busy = False
        if on_done is not None:
            on_done(result, error)

    def _log(self, on_log: Optional[LogFn], message: str) -> None:
        if on_log is not None:
            on_log(message)

    def _build_namespace(self, spec: RunSpec) -> argparse.Namespace:
        return argparse.Namespace(
            config=spec.config_path,
            stage=spec.stage,
            baseline_from=spec.baseline_from,
            quarters=spec.quarters,
            days_per_quarter=spec.days_per_quarter,
            budget=spec.budget,
            products=spec.products,
            suppliers=spec.suppliers,
            sleep_every=spec.sleep_every,
            seed=spec.seed,
            output=spec.output,
            checkpoint=spec.checkpoint,
            resume_from=spec.resume_from,
            no_stop_on_graduation=not spec.stop_on_graduation,
            no_seed_intuition=not spec.seed_intuition,
            quiet=True,
        )

    def _prepare_config(self, spec: RunSpec, on_log: Optional[LogFn]) -> SandboxConfig:
        args = self._build_namespace(spec)
        config = resolve_config(args)
        config.training.stop_on_graduation = bool(spec.stop_on_graduation)
        config.training.seed_intuition = bool(spec.seed_intuition)
        config.training.stage = spec.stage
        config.training.seed = int(spec.seed)
        config.training.n_quarters = int(spec.quarters)
        if spec.days_per_quarter is not None:
            config.world.days_per_quarter = int(spec.days_per_quarter)
        if spec.demand_shock_probability is not None:
            config.world.demand_shock_probability = float(spec.demand_shock_probability)
        if spec.supplier_default_probability is not None:
            config.world.supplier_default_probability = float(
                spec.supplier_default_probability
            )
        if spec.max_lead_time_days is not None:
            config.world.max_lead_time_days = int(spec.max_lead_time_days)
        if spec.max_demand_per_day is not None:
            config.world.max_demand_per_day = float(spec.max_demand_per_day)
        if spec.min_supplier_reliability is not None:
            config.world.min_supplier_reliability = float(
                spec.min_supplier_reliability
            )
        config.world.seed = int(spec.seed)
        for key, value in dict(spec.threshold_overrides or {}).items():
            if key in config.graduation_thresholds:
                config.graduation_thresholds[key] = float(value)
        self._log(
            on_log,
            f"[Init] stage={config.training.stage} seed={config.training.seed} "
            f"quarters={config.training.n_quarters} "
            f"stop_on_graduation={config.training.stop_on_graduation}",
        )
        return config

    def _run_single(
        self,
        spec: RunSpec,
        on_log: Optional[LogFn],
        on_quarter: Optional[QuarterFn],
        on_done: Optional[DoneFn],
    ) -> None:
        result: Optional[SandboxTrainingResult] = None
        error: Optional[BaseException] = None
        try:
            result = self._execute_run(spec, on_log=on_log, on_quarter=on_quarter)
        except BaseException as exc:  # noqa: BLE001 - surface to GUI
            error = exc
            self._log(on_log, f"[Error] {exc}")
            self._log(on_log, traceback.format_exc())
        self._finish(result, error, on_done)

    def _run_sweep(
        self,
        sweep: SweepSpec,
        on_log: Optional[LogFn],
        on_quarter: Optional[QuarterFn],
        on_done: Optional[DoneFn],
    ) -> None:
        result: Optional[SandboxTrainingResult] = None
        error: Optional[BaseException] = None
        try:
            for seed in sweep.seeds:
                if self._stop.is_set():
                    self._log(
                        on_log,
                        "[Sweep] Soft-stop requested; remaining seeds skipped.",
                    )
                    break
                spec = RunSpec(
                    stage="1a",
                    seed=int(seed),
                    quarters=int(sweep.quarters),
                    config_path=sweep.config_path,
                    stop_on_graduation=sweep.stop_on_graduation,
                    output=sweep.output_template.format(seed=seed),
                    checkpoint=sweep.checkpoint_template.format(seed=seed),
                    seed_intuition=True,
                )
                self._log(on_log, f"\n===== SWEEP SEED {seed} =====")
                result = self._execute_run(
                    spec, on_log=on_log, on_quarter=on_quarter
                )
            self._log(on_log, "\n[Sweep] Done.")
        except BaseException as exc:  # noqa: BLE001
            error = exc
            self._log(on_log, f"[Error] {exc}")
            self._log(on_log, traceback.format_exc())
        self._finish(result, error, on_done)

    def _execute_run(
        self,
        spec: RunSpec,
        *,
        on_log: Optional[LogFn],
        on_quarter: Optional[QuarterFn],
    ) -> SandboxTrainingResult:
        started = time.perf_counter()
        args = self._build_namespace(spec)
        config = self._prepare_config(spec, on_log)

        output_path = Path(spec.output)
        if not output_path.is_absolute():
            output_path = DEMO_ROOT / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)

        checkpoint_path: Optional[str] = None
        if spec.checkpoint:
            ckpt = Path(spec.checkpoint)
            if not ckpt.is_absolute():
                ckpt = DEMO_ROOT / ckpt
            ckpt.parent.mkdir(parents=True, exist_ok=True)
            checkpoint_path = str(ckpt)

        resume_path = None
        if spec.resume_from:
            resume_path = resolve_config_path(spec.resume_from)
            if resume_path and not Path(resume_path).exists():
                alt = DEMO_ROOT / spec.resume_from
                resume_path = str(alt) if alt.exists() else resume_path

        rng = random.Random(config.training.seed)
        self._log(
            on_log,
            f"[Init] Creating procurement agent (seed={config.training.seed})...",
        )
        agent = create_procurement_agent(
            "procurement_agent_001",
            rng=rng,
            # A resumed agent restores its own hippocampus, which already
            # contains the seed corpus from the original run; pre-seeding here
            # would stack a second copy of the professional episodes on top.
            seed_intuition=config.training.seed_intuition and not resume_path,
        )

        initial_result: Optional[SandboxTrainingResult] = None
        checkpoint = None
        if resume_path:
            checkpoint = load_checkpoint(resume_path)
            restored = restore_agent(checkpoint, agent)
            self._log(on_log, f"[Resume] {checkpoint.summary()}")
            if not restored:
                self._log(
                    on_log,
                    "[Resume] WARNING: agent memory could not be restored.",
                )
                if config.training.seed_intuition:
                    n_seeded = seed_professional_intuition(agent)
                    self._log(
                        on_log,
                        f"[Resume] Seeded {n_seeded} professional intuition "
                        "episode(s) into the fresh brain.",
                    )
            previous_stage = _stage_of(checkpoint.result)
            if previous_stage not in (None, config.training.stage):
                self._log(
                    on_log,
                    f"[Resume] stage {previous_stage} -> {config.training.stage}: "
                    "graduation status reset.",
                )
                checkpoint.result.graduated = False
                checkpoint.result.graduated_at_quarter = None
            if checkpoint.rng_state is not None:
                try:
                    rng.setstate(checkpoint.rng_state)
                except (TypeError, ValueError):
                    self._log(on_log, "[Resume] WARNING: RNG state incompatible.")
            initial_result = checkpoint.result

        encoder = SandboxEncoder()
        fitness_evaluator = ProcurementFitnessEvaluator(
            thresholds=config.graduation_thresholds,
            stage=config.training.stage,
        )
        self._log(
            on_log,
            f"[Init] Curriculum stage {config.training.stage} "
            f"(gating on {', '.join(fitness_evaluator.gating_criteria)})",
        )

        baseline_bundle = _resolve_baseline(
            args, config.training.stage, lambda m: self._log(on_log, m)
        )
        self.last_stage = config.training.stage
        self.last_thresholds = dict(config.graduation_thresholds)
        self.last_nr_floors = nr_floors_from_baseline(
            baseline_bundle.get("stage_1a_baseline") or {},
            baseline_bundle.get("stage_1a_spread_iqr") or {},
            cost_vs_chance_median=baseline_bundle.get("cost_vs_chance_median"),
            cost_vs_chance_iqr=baseline_bundle.get("cost_vs_chance_iqr"),
        )
        trainer = SandboxTrainer(
            agent,
            encoder,
            fitness_evaluator,
            sleep_every_n_days=config.training.sleep_every_n_days,
            stage_1a_baseline=baseline_bundle.get("stage_1a_baseline") or {},
            stage_1a_spread_iqr=baseline_bundle.get("stage_1a_spread_iqr") or {},
            supplier_set_count=config.training.supplier_set_count,
            quarters_per_supplier_set=config.training.quarters_per_supplier_set,
            cost_vs_chance_median=baseline_bundle.get("cost_vs_chance_median"),
            cost_vs_chance_iqr=baseline_bundle.get("cost_vs_chance_iqr"),
        )
        trainer.quarter_overrides = {
            int(k): dict(v) for k, v in dict(spec.quarter_overrides or {}).items()
        }
        curriculum = getattr(spec, "curriculum", None)
        if curriculum is not None:
            trainer.curriculum = curriculum
            trainer.max_cycles = int(getattr(spec, "max_cycles", 500) or 500)
        if checkpoint is not None:
            trainer.carried_suppliers = (checkpoint.metadata or {}).get(
                "carried_suppliers"
            )

        carry = config.training.stage == "1b"
        if carry:
            from dataclasses import replace as _replace

            config.world = _replace(config.world, persistent_suppliers=True)
        result = initial_result or SandboxTrainingResult()

        if curriculum is not None:
            n_cur = int(getattr(curriculum, "n_quarters", 0) or 0)
            if n_cur < 1:
                raise ValueError("curriculum must contain at least one quarter")
            errors = list(curriculum.validate() or [])
            if errors:
                raise ValueError("Invalid curriculum: " + "; ".join(errors[:5]))
            max_cycles = int(getattr(spec, "max_cycles", 500) or 500)
            planned_total = max_cycles * n_cur
            self._log(
                on_log,
                f"[Curriculum] {n_cur} quarter(s), cycle until graduation "
                f"(max_cycles={max_cycles}, planned_cap={planned_total})",
            )
            n_steps = planned_total
        else:
            planned_total = len(result.quarters) + max(0, config.training.n_quarters)
            n_steps = max(0, config.training.n_quarters)

        for _ in range(n_steps):
            if self._stop.is_set():
                self._log(on_log, "[Stop] Soft-stop before next quarter.")
                break

            q_before = len(result.quarters)
            q_idx = q_before + 1
            if curriculum is not None:
                cq, cycle = curriculum.curriculum_quarter_for_step(q_idx)
                self._log(
                    on_log,
                    f"[Training] Step {q_idx} "
                    f"(curriculum Q{cq}, cycle {cycle})...",
                )
            else:
                self._log(on_log, f"[Training] Quarter {q_idx}/{planned_total}...")

            result = trainer.run_quarters(
                n_quarters=1,
                world_config=config.world,
                progress_callback=None,
                stop_on_graduation=config.training.stop_on_graduation,
                initial_result=result,
                carry_suppliers=carry,
                should_stop=self._stop.is_set,
            )

            if checkpoint_path:
                save_checkpoint(
                    checkpoint_path,
                    agent,
                    result,
                    rng=rng,
                    metadata={"carried_suppliers": trainer.carried_suppliers},
                )
                self.last_checkpoint = checkpoint_path

            if len(result.quarters) == q_before:
                break

            latest = result.quarters[-1]
            record = quarter_to_record(latest)
            streak = _current_qualifying_streak(
                result.quarters, stage=self.last_stage
            )
            record["qualifying_streak"] = streak
            record["graduated"] = bool(result.graduated)
            record["graduated_at_quarter"] = result.graduated_at_quarter
            if on_quarter is not None:
                on_quarter(record)

            g = latest.graduation or {}
            mark = "PASS" if g.get("all_passed") else "...."
            cq = (latest.world_summary or {}).get("curriculum_quarter")
            extra = f" curQ={cq}" if cq is not None else ""
            self._log(
                on_log,
                f"  Q{latest.quarter_index} [{mark}] "
                f"cost={latest.fitness.cost_efficiency:.2f} "
                f"stockout={latest.fitness.stockout_avoidance:.2f} "
                f"divers={latest.fitness.supplier_diversification:.2f} "
                f"consist={latest.fitness.decision_consistency:.2f} "
                f"streak={streak}{extra}",
            )

            if result.graduated and config.training.stop_on_graduation:
                self._log(
                    on_log,
                    f"[Graduation] stop_on_graduation at "
                    f"Q{result.graduated_at_quarter}",
                )
                break

            if self._stop.is_set():
                self._log(on_log, "[Stop] Soft-stop honoured after quarter.")
                break

        observer = SandboxObserver()
        observer.record_all(result.quarters)
        observer.to_json(str(output_path))
        self.last_output = str(output_path)
        elapsed = time.perf_counter() - started
        self._log(on_log, "")
        self._log(on_log, result.summary())
        self._log(on_log, f"\n[Output] Wrote {output_path} ({elapsed:.1f}s)")
        if checkpoint_path:
            self._log(on_log, f"[Output] Checkpoint at {checkpoint_path}")
        return result


def format_readiness_text(report: Dict[str, Any]) -> str:
    """Plain-text summary of a write_baseline_report() payload."""
    readiness = report.get("readiness") or {}
    rows = report.get("rows") or []
    lines = [
        f"{'run':<28} {'grad':>5} {'q*':>4} {'n_ok':>5}",
        "-" * 48,
    ]
    for row in rows:
        q = row.get("first_graduation_quarter")
        lines.append(
            f"{row.get('name', '?'):<28} "
            f"{('yes' if row.get('graduated') else 'no'):>5} "
            f"{(q if q is not None else '-'):>4} "
            f"{row.get('n_graduated_quarters', 0):>5}"
        )
    lines.append("")
    lines.append(
        f"Graduated runs: {readiness.get('n_graduated', 0)}/"
        f"{readiness.get('n_runs', 0)} (need 3)"
    )
    lines.append(f"Graduation quarters: {readiness.get('graduation_quarters')}")
    half = readiness.get("spread_half_width") or 0.0
    lines.append(
        f"Spread ratio: {readiness.get('spread_ratio')} "
        f"(half-width={half:g}; "
        f"{'within' if readiness.get('spread_within_tolerance') else 'outside'} "
        "tolerance)"
    )
    lines.append(
        "READY for Stage 1b"
        if readiness.get("ready_for_stage_1b")
        else "NOT READY for Stage 1b"
    )
    if report.get("refused"):
        lines.append(f"\nBaseline: {report['refused']}")
    elif report.get("baseline_path"):
        lines.append(
            f"\nBaseline from {report.get('chosen')} -> {report['baseline_path']}"
        )
        baseline = (report.get("baseline") or {}).get("stage_1a_baseline") or {}
        for key in PROCUREMENT_CRITERIA:
            if key in baseline:
                lines.append(f"  {key}: {baseline[key]}")
    return "\n".join(lines)


__all__ = [
    "DEMO_ROOT",
    "GRADUATION_MIN_STREAK",
    "RunController",
    "RunSpec",
    "SweepSpec",
    "format_readiness_text",
    "load_results_json",
    "quarter_to_record",
    "records_from_result",
]
