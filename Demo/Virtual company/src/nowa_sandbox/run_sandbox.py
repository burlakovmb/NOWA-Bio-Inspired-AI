"""CLI runner for sandbox training."""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

if __package__ in (None, ""):  # pragma: no cover - direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nowa_sandbox.procurement_fitness import ProcurementFitnessEvaluator
from nowa_sandbox.procurement_world import ProcurementWorldConfig
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
from nowa_sandbox.stage_baseline import load_baseline_bundle
from nowa_sandbox.training_loop import SandboxTrainer, SandboxTrainingResult


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run NOWA procurement sandbox training."
    )
    parser.add_argument("--config", default=None, help="path to a sandbox YAML config")
    parser.add_argument(
        "--stage",
        choices=["1a", "1b"],
        default=None,
        help="1a: rotating suppliers, general strategy. "
             "1b: persistent suppliers, relationship building. "
             "Requires a prior 1a graduation baseline (see --baseline-from).",
    )
    parser.add_argument(
        "--baseline-from",
        default=None,
        help="Stage 1a result or baseline JSON, required when --stage=1b "
             "for the non-regression guard.",
    )
    parser.add_argument("--quarters", type=int, default=None)
    parser.add_argument("--days-per-quarter", type=int, default=None)
    parser.add_argument("--budget", type=float, default=None)
    parser.add_argument("--products", type=int, default=None)
    parser.add_argument("--suppliers", type=int, default=None)
    parser.add_argument("--sleep-every", type=int, default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument(
        "--supplier-sets",
        type=int,
        default=None,
        help="Stage 1b: how many supplier sets to plan (default 4). "
             "Each set is drawn from that quarter's world seed.",
    )
    parser.add_argument(
        "--quarters-per-supplier-set",
        type=int,
        default=None,
        help="Stage 1b: quarters a supplier set stays before the next draw "
             "(default 5), counted from the first Stage 1b quarter.",
    )
    parser.add_argument("--output", default="results/sandbox_run.json")
    parser.add_argument(
        "--checkpoint",
        default=None,
        help="write a resumable checkpoint after every quarter",
    )
    parser.add_argument(
        "--resume-from",
        default=None,
        help="continue training from an existing checkpoint",
    )
    parser.add_argument(
        "--no-stop-on-graduation",
        action="store_true",
        help="keep training after all criteria pass",
    )
    parser.add_argument(
        "--no-seed-intuition",
        action="store_true",
        help="start with an empty hippocampus instead of seeded business episodes",
    )
    parser.add_argument(
        "--verbose-pipeline",
        action="store_true",
        help="log daily NOWA activation, action, motor, and feedback diagnostics",
    )
    parser.add_argument("--quiet", action="store_true")
    return parser


DEMO_ROOT = Path(__file__).resolve().parents[2]


def resolve_config_path(raw: Optional[str]) -> Optional[str]:
    """Resolve ``--config`` against the cwd first, then the demo root.

    Without the fallback, ``--config configs/default_world.yaml`` only works
    when invoked from the demo root, which is an easy trap given the runner
    also works as ``python -m nowa_sandbox.run_sandbox`` from ``src/``.
    """
    if raw is None:
        return None
    if Path(raw).exists():
        return raw
    fallback = DEMO_ROOT / raw
    return str(fallback) if fallback.exists() else raw


def _stage_of(result: Optional[SandboxTrainingResult]) -> Optional[str]:
    """Which curriculum stage a previous run's last quarter was scored under.

    Returns None for results predating v1.1, whose reports carry no stage; such
    a checkpoint is treated as continuing whatever stage is now requested.
    """
    quarters = getattr(result, "quarters", None) or []
    if not quarters:
        return None
    return (quarters[-1].graduation or {}).get("stage")


def _resolve_baseline(
    args: argparse.Namespace, stage: str, log
) -> Dict[str, Any]:
    """Load the Stage 1a baseline bundle Stage 1b must not regress below.

    Returns medians plus IQR spread (v1.2). Stage 1a does not use one.
    Stage 1b without one would run the relationship criteria unguarded, so
    it is refused rather than silently downgraded.
    """
    if args.baseline_from:
        bundle = load_baseline_bundle(resolve_config_path(args.baseline_from))
        baseline = bundle.get("stage_1a_baseline") or {}
        spread = bundle.get("stage_1a_spread_iqr") or {}
        method = bundle.get("method") or "median_all"
        parts = [f"{k}={v:.3f}" for k, v in sorted(baseline.items())]
        if spread:
            parts.append(
                "IQR=" + ",".join(
                    f"{k}:{spread[k]:.3f}" for k in sorted(spread)
                )
            )
        log(f"[Init] Stage 1a baseline ({method}) from {args.baseline_from}: "
            + ", ".join(parts))
        return bundle

    if stage == "1b":
        raise SystemExit(
            "--stage 1b requires --baseline-from: the non-regression guard "
            "needs the Stage 1a criteria medians to compare against. Produce "
            "one with:\n"
            "  python -m nowa_sandbox.stage1a_report results/stage1a_seed*.json "
            "--write-baseline results/stage_1a_baseline.json"
        )
    return {}


def resolve_config(args: argparse.Namespace) -> SandboxConfig:
    """Load YAML defaults, then apply explicit CLI overrides on top."""
    config = SandboxConfig.load(resolve_config_path(args.config))

    if args.budget is not None:
        config.world.initial_budget = float(args.budget)
    if args.products is not None:
        config.world.n_products = int(args.products)
    if args.suppliers is not None:
        config.world.n_suppliers = int(args.suppliers)
    if args.days_per_quarter is not None:
        config.world.days_per_quarter = int(args.days_per_quarter)
    if args.seed is not None:
        config.world.seed = int(args.seed)
        config.training.seed = int(args.seed)
    if args.quarters is not None:
        config.training.n_quarters = int(args.quarters)
    if args.sleep_every is not None:
        config.training.sleep_every_n_days = max(1, int(args.sleep_every))
    if args.no_stop_on_graduation:
        config.training.stop_on_graduation = False
    if args.no_seed_intuition:
        config.training.seed_intuition = False
    if args.stage is not None:
        config.training.stage = args.stage
    if getattr(args, "supplier_sets", None) is not None:
        config.training.supplier_set_count = max(1, int(args.supplier_sets))
    if getattr(args, "quarters_per_supplier_set", None) is not None:
        config.training.quarters_per_supplier_set = max(
            1, int(args.quarters_per_supplier_set)
        )
    return config


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    config = resolve_config(args)
    log = _make_logger(args.quiet)

    rng = random.Random(config.training.seed)
    log(f"[Init] Creating procurement agent (seed={config.training.seed})...")
    resuming = bool(args.resume_from)
    agent = create_procurement_agent(
        "procurement_agent_001",
        rng=rng,
        # A resumed agent restores its own hippocampus, which already contains
        # the seed corpus from the original run. Pre-seeding here would stack a
        # second copy of the professional episodes on top of the restored ones.
        seed_intuition=config.training.seed_intuition and not resuming,
    )

    initial_result: Optional[SandboxTrainingResult] = None
    checkpoint = None
    if args.resume_from:
        checkpoint = load_checkpoint(args.resume_from)
        restored = restore_agent(checkpoint, agent)
        log(f"[Resume] {checkpoint.summary()}")
        if not restored:
            log("[Resume] WARNING: agent memory could not be restored; "
                "continuing with a fresh agent brain.")
            if config.training.seed_intuition:
                n_seeded = seed_professional_intuition(agent)
                log(f"[Resume] Seeded {n_seeded} professional intuition "
                    "episode(s) into the fresh brain.")
        previous_stage = _stage_of(checkpoint.result)
        if previous_stage not in (None, config.training.stage):
            # Moving 1a -> 1b is the intended path, but the inherited flags
            # describe the previous stage's criteria. Left alone they would
            # report a Stage 1a graduation as if it were Stage 1b's, and with
            # stop_on_graduation they would end the new stage after one quarter.
            log(f"[Resume] stage {previous_stage} -> {config.training.stage}: "
                "graduation status reset, the new stage is judged on its own "
                "criteria.")
            checkpoint.result.graduated = False
            checkpoint.result.graduated_at_quarter = None
        elif checkpoint.graduated:
            log("[Resume] WARNING: this agent already graduated at quarter "
                f"{checkpoint.graduated_at_quarter}. Continuing will keep "
                "training an already-graduated agent.")
        if checkpoint.rng_state is not None:
            try:
                rng.setstate(checkpoint.rng_state)
            except (TypeError, ValueError):
                log("[Resume] WARNING: RNG state incompatible; using a fresh RNG.")
        initial_result = checkpoint.result

    encoder = SandboxEncoder()
    fitness_evaluator = ProcurementFitnessEvaluator(
        thresholds=config.graduation_thresholds,
        stage=config.training.stage,
        cost_vs_chance_floor_delta=config.stage_baseline.cost_vs_chance_floor_delta,
    )
    log(f"[Init] Curriculum stage {config.training.stage} "
        f"(gating on {', '.join(fitness_evaluator.gating_criteria)})")

    baseline_bundle = _resolve_baseline(args, config.training.stage, log)
    trainer = SandboxTrainer(
        agent,
        encoder,
        fitness_evaluator,
        sleep_every_n_days=config.training.sleep_every_n_days,
        stage_1a_baseline=baseline_bundle.get("stage_1a_baseline") or {},
        stage_1a_spread_iqr=baseline_bundle.get("stage_1a_spread_iqr") or {},
        verbose_pipeline=args.verbose_pipeline,
        pipeline_logger=log,
        supplier_set_count=config.training.supplier_set_count,
        quarters_per_supplier_set=config.training.quarters_per_supplier_set,
        cost_vs_chance_median=baseline_bundle.get("cost_vs_chance_median"),
        cost_vs_chance_iqr=baseline_bundle.get("cost_vs_chance_iqr"),
    )
    if checkpoint is not None:
        trainer.carried_suppliers = (checkpoint.metadata or {}).get(
            "carried_suppliers"
        )

    def progress(q: int, total: int) -> None:
        log(f"[Training] Quarter {q}/{total}...")

    result = _run_training(
        trainer=trainer,
        agent=agent,
        config=config,
        initial_result=initial_result,
        progress=progress,
        checkpoint_path=args.checkpoint,
        rng=rng,
    )

    log("")
    log(result.summary())

    observer = SandboxObserver()
    observer.record_all(result.quarters)

    output_path = Path(args.output)
    observer.to_json(str(output_path))
    log(f"\n[Output] Wrote {output_path}")

    if args.checkpoint:
        log(f"[Output] Checkpoint at {args.checkpoint}")

    return 0


def _run_training(
    trainer: SandboxTrainer,
    agent: Any,
    config: SandboxConfig,
    initial_result: Optional[SandboxTrainingResult],
    progress,
    checkpoint_path: Optional[str],
    rng: random.Random,
) -> SandboxTrainingResult:
    """Run the requested quarters, checkpointing after each one when asked."""
    # Stage 1b differs only in that suppliers survive between quarters; both
    # paths take the same arguments so checkpointing works identically.
    run = (
        trainer.run_stage1b_persistent
        if config.training.stage == "1b"
        else trainer.run_quarters
    )

    if not checkpoint_path:
        return run(
            n_quarters=config.training.n_quarters,
            world_config=config.world,
            progress_callback=progress,
            stop_on_graduation=config.training.stop_on_graduation,
            initial_result=initial_result,
        )

    result = initial_result or SandboxTrainingResult()
    planned_total = len(result.quarters) + max(0, config.training.n_quarters)

    def progress_against_plan(q_idx: int, _partial_total: int) -> None:
        progress(q_idx, planned_total)

    for _ in range(max(0, config.training.n_quarters)):
        quarters_before = len(result.quarters)
        result = run(
            n_quarters=1,
            world_config=config.world,
            progress_callback=progress_against_plan,
            stop_on_graduation=config.training.stop_on_graduation,
            initial_result=result,
        )
        # Carrying the roster in the checkpoint keeps supplier identity intact
        # across a resume; without it Stage 1b would quietly become Stage 1a.
        save_checkpoint(
            checkpoint_path, agent, result, rng=rng,
            metadata={"carried_suppliers": trainer.carried_suppliers},
        )
        if len(result.quarters) == quarters_before:
            break
        if result.graduated and config.training.stop_on_graduation:
            break
    return result


def _make_logger(quiet: bool):
    def log(message: str) -> None:
        if not quiet:
            # Flushed: a 30-quarter run takes minutes and piped stdout would
            # otherwise show nothing until the very end.
            print(message, flush=True)
    return log


if __name__ == "__main__":
    raise SystemExit(main())
