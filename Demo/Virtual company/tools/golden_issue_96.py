"""Capture the issue #96 procurement golden slice on a frozen clock.

The slice is Stage 1a on ``configs/default_world.yaml``: two quarters of ten
days, seeds 42 and 3, price perception on and off. A fifth fixture (one
quarter of ninety days, seed 42, perception on) is optional.

Nondeterminism is frozen the same way in ``--write`` and ``--check``:

- ``PYTHONHASHSEED=0`` (the script re-executes itself when that is not set)
- ``random.seed(42)`` after imports and again immediately before each run
- ``time.time`` fixed at 1700000000.0
- address-space layout frozen (``setarch -R``), because the core walks sets of
  objects and their order follows ``id()``
- unseeded ``random.Random()`` instances get ``(42, n)`` in construction order
  (core sleep and affect generators otherwise read system entropy)

Each case is a fresh process. A later case in the same process does not repeat.

``processing_time_s`` is not part of the payload. Comparison is exact: the
canonical JSON of a fresh capture must equal the fixture bytes.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


FROZEN_RANDOM_SEED = 42
FROZEN_TIME = 1700000000.0
_WORKER_FLAG = "GOLDEN_ISSUE_96_WORKER"

DEMO_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = DEMO_ROOT.parents[1]
FIXTURE_DIR = DEMO_ROOT / "tests" / "fixtures" / "issue_96_golden"
CONFIG_PATH = DEMO_ROOT / "configs" / "default_world.yaml"

# (name, seed, price_perception, days_per_quarter, n_quarters)
SHORT_CASES: Tuple[Tuple[str, int, bool, int, int], ...] = (
    ("seed42_price_on", 42, True, 10, 2),
    ("seed42_price_off", 42, False, 10, 2),
    ("seed3_price_on", 3, True, 10, 2),
    ("seed3_price_off", 3, False, 10, 2),
)
LONG_CASE = ("seed42_q1_d90_price_on", 42, True, 90, 1)


def _ensure_hashseed() -> None:
    if os.environ.get("PYTHONHASHSEED") == "0":
        return
    os.environ["PYTHONHASHSEED"] = "0"
    os.execv(sys.executable, [sys.executable, *sys.argv])


def _install_freeze() -> None:
    """Patch clocks and unseeded ``random.Random()`` before NOWA is imported.

    The core builds private generators with ``random.Random()`` (sleep,
    affect). Those draw system entropy unless they are seeded here, in
    construction order. ``perf_counter`` is a counter for the same reason:
    a real monotonic clock leaks into core bookkeeping.
    """
    step = {"n": 0}
    unseeded = {"n": 0}

    def _clock() -> float:
        step["n"] += 1
        return 1000.0 + step["n"] * 1e-6

    class _FrozenRandom(random.Random):
        def __init__(self, x=None):
            if x is None:
                unseeded["n"] += 1
                x = (FROZEN_RANDOM_SEED, unseeded["n"])
            super().__init__(x)

        def seed(self, a=None, version=2):
            if a is None:
                unseeded["n"] += 1
                a = (FROZEN_RANDOM_SEED, unseeded["n"])
            super().seed(a, version)

    random.Random = _FrozenRandom  # type: ignore[misc]
    time.time = lambda: FROZEN_TIME  # type: ignore[method-assign]
    time.time_ns = lambda: int(FROZEN_TIME * 1_000_000_000)  # type: ignore[method-assign]
    time.perf_counter = _clock  # type: ignore[method-assign]
    time.perf_counter_ns = lambda: int(_clock() * 1_000_000_000)  # type: ignore[method-assign]
    time.monotonic = _clock  # type: ignore[method-assign]
    time.monotonic_ns = lambda: int(_clock() * 1_000_000_000)  # type: ignore[method-assign]


def _worker_env() -> Dict[str, str]:
    """Fresh interpreter, hash seed fixed, no parent test variables.

    A case that shares a process with an earlier case is not stable: the
    90-day quarter repeats only when it is the first run in that process.
    """
    kept = (
        "PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "USER", "LOGNAME",
        "TMPDIR", "TMP", "TEMP",
    )
    env = {key: os.environ[key] for key in kept if key in os.environ}
    env["PYTHONHASHSEED"] = "0"
    env[_WORKER_FLAG] = "1"
    return env


def _bootstrap() -> None:
    for path in (DEMO_ROOT / "src", REPO_ROOT / "src"):
        text = str(path)
        if text not in sys.path:
            sys.path.insert(0, text)


def _canonical(payload: Dict[str, Any]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ) + "\n"


def _parse_args(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="write fixture JSON")
    mode.add_argument("--check", action="store_true", help="compare a fresh capture to fixtures")
    parser.add_argument("--only", default="", help="comma-separated case names")
    parser.add_argument(
        "--include-long",
        action="store_true",
        help="also capture the 90-day quarter (seed 42, perception on)",
    )
    parser.add_argument(
        "--out",
        default="",
        help="fixture directory (default: tests/fixtures/issue_96_golden)",
    )
    return parser.parse_args(argv)


def _selected(args: argparse.Namespace) -> List[Tuple[str, int, bool, int, int]]:
    cases = list(SHORT_CASES)
    if args.include_long:
        cases.append(LONG_CASE)
    if args.only:
        wanted = {name.strip() for name in args.only.split(",") if name.strip()}
        known = {case[0] for case in cases}
        missing = wanted - known
        if missing:
            raise SystemExit(f"unknown case(s): {sorted(missing)}")
        cases = [case for case in cases if case[0] in wanted]
    return cases


def _build_config(seed: int, price_perception: bool, days: int, quarters: int):
    from nowa_sandbox.run_sandbox import build_parser, resolve_config

    argv = [
        "--config", str(CONFIG_PATH),
        "--quarters", str(quarters),
        "--days-per-quarter", str(days),
        "--seed", str(seed),
        "--stage", "1a",
        "--no-stop-on-graduation",
        "--quiet",
    ]
    if not price_perception:
        argv.append("--no-price-perception")
    return resolve_config(build_parser().parse_args(argv))


def _project_row(row: Dict[str, Any], price_tokens: List[str]) -> Dict[str, Any]:
    return {
        "action": row.get("action"),
        "supplier_id": row.get("supplier_id"),
        "product_id": row.get("product_id"),
        "qty": row.get("qty"),
        "result": row.get("result"),
        "situation": list(row.get("situation") or []),
        "price_tokens": list(price_tokens),
    }


def capture_case(
    seed: int,
    price_perception: bool,
    days: int,
    quarters: int,
) -> Dict[str, Any]:
    """Run one frozen slice and return the comparable payload.

    Quarters are executed one at a time so each quarter's decision log can be
    read from ``trainer.last_decision_log``. That is the same loop body as a
    single ``run_quarters(n_quarters=N)`` call with graduation stop disabled.
    """
    from nowa_sandbox.procurement_fitness import ProcurementFitnessEvaluator
    from nowa_sandbox.run_sandbox import create_procurement_agent
    from nowa_sandbox.sandbox_encoder import SandboxEncoder
    from nowa_sandbox.training_loop import SandboxTrainer

    random.seed(FROZEN_RANDOM_SEED)
    config = _build_config(seed, price_perception, days, quarters)
    rng = random.Random(config.training.seed)
    agent = create_procurement_agent(
        "procurement_agent_001",
        rng=rng,
        seed_intuition=config.training.seed_intuition,
    )
    encoder = SandboxEncoder()
    fitness = ProcurementFitnessEvaluator(
        thresholds=config.graduation_thresholds,
        stage=config.training.stage,
        cost_vs_chance_floor_delta=config.stage_baseline.cost_vs_chance_floor_delta,
        consistency=config.consistency,
    )
    trainer = SandboxTrainer(
        agent,
        encoder,
        fitness,
        sleep_every_n_days=config.training.sleep_every_n_days,
        supplier_set_count=config.training.supplier_set_count,
        quarters_per_supplier_set=config.training.quarters_per_supplier_set,
        price_perception=config.training.price_perception,
        price_memory_alpha=config.training.price_memory_alpha,
        price_bucket_z=config.training.price_bucket_z,
        price_reward_gain=config.training.price_reward_gain,
        consistency=config.consistency,
    )

    day_price_tokens: List[List[str]] = []
    original_encode = SandboxEncoder.encode_daily_context

    def _encode(self, *args, **kwargs):
        tokens = original_encode(self, *args, **kwargs)
        day_price_tokens.append(
            [token for token in tokens if isinstance(token, str) and token.startswith("price:")]
        )
        return tokens

    SandboxEncoder.encode_daily_context = _encode  # type: ignore[method-assign]
    try:
        random.seed(FROZEN_RANDOM_SEED)
        result = None
        recorded: List[Dict[str, Any]] = []
        for _ in range(quarters):
            cursor = len(day_price_tokens)
            result = trainer.run_quarters(
                n_quarters=1,
                world_config=config.world,
                stop_on_graduation=False,
                initial_result=result,
            )
            log = list(trainer.last_decision_log)
            tokens = day_price_tokens[cursor:]
            if len(tokens) != len(log):
                raise RuntimeError(
                    f"price-token rows ({len(tokens)}) != decision rows ({len(log)})"
                )
            quarter = result.quarters[-1]
            fitness_vector = quarter.fitness
            recorded.append({
                "quarter_index": quarter.quarter_index,
                "fitness": {
                    "criteria": fitness_vector.as_dict(),
                    "n_days": fitness_vector.n_days,
                    "n_orders": fitness_vector.n_orders,
                },
                "cost_vs_chance": quarter.world_summary.get("cost_vs_chance"),
                "graduation": quarter.graduation,
                "decisions": [
                    _project_row(row, price_tokens)
                    for row, price_tokens in zip(log, tokens)
                ],
            })
    finally:
        SandboxEncoder.encode_daily_context = original_encode  # type: ignore[method-assign]

    return {
        "freeze": {
            "pythonhashseed": "0",
            "random_seed": FROZEN_RANDOM_SEED,
            "time_time": FROZEN_TIME,
        },
        "slice": {
            "config": "configs/default_world.yaml",
            "stage": "1a",
            "seed": seed,
            "n_quarters": quarters,
            "days_per_quarter": days,
            "price_perception": price_perception,
            "stop_on_graduation": False,
        },
        "quarters": recorded,
    }


def _fixture_path(directory: Path, name: str) -> Path:
    return directory / f"{name}.json"


def _run_worker(args: argparse.Namespace) -> int:
    _install_freeze()
    random.seed(FROZEN_RANDOM_SEED)
    _bootstrap()
    cases = _selected(args)
    if len(cases) != 1:
        print("worker expects exactly one case", file=sys.stderr)
        return 2
    _name, seed, price, days, quarters = cases[0]
    sys.stdout.write(_canonical(capture_case(seed, price, days, quarters)))
    return 0


def _python_argv() -> List[str]:
    """Interpreter with ASLR off, so object ids repeat across captures."""
    setarch = shutil.which("setarch")
    if not setarch:
        raise RuntimeError("setarch is required to freeze object-id order")
    return [setarch, os.uname().machine, "-R", sys.executable]


def _capture_text(name: str, include_long: bool) -> str:
    argv = _python_argv() + [str(Path(__file__).resolve()), "--only", name]
    if include_long:
        argv.append("--include-long")
    # ``--write`` / ``--check`` are mutually exclusive and required. The worker
    # ignores the mode and prints the payload; ``--check`` avoids touching files.
    argv.append("--check")
    proc = subprocess.run(
        argv,
        cwd=str(DEMO_ROOT),
        env=_worker_env(),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "worker failed")
    if not proc.stdout.startswith("{"):
        raise RuntimeError("worker stdout is not a payload:\n" + proc.stdout[:400])
    return proc.stdout


def main(argv: Optional[Sequence[str]] = None) -> int:
    if os.environ.get(_WORKER_FLAG) == "1":
        _ensure_hashseed()
        return _run_worker(_parse_args(argv))

    args = _parse_args(argv)
    directory = Path(args.out) if args.out else FIXTURE_DIR
    failures = 0
    for name, _seed, _price, _days, _quarters in _selected(args):
        started = time.perf_counter()
        try:
            text = _capture_text(name, include_long=bool(args.include_long))
        except RuntimeError as exc:
            print(f"FAILED {name}: {exc}")
            failures += 1
            continue
        elapsed = time.perf_counter() - started
        path = _fixture_path(directory, name)
        if args.write:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            print(f"wrote {path} ({elapsed:.1f}s, {len(text)} bytes)")
        else:
            if not path.is_file():
                print(f"MISSING {path}")
                failures += 1
                continue
            expected = path.read_text(encoding="utf-8")
            if expected != text:
                print(f"MISMATCH {name} ({elapsed:.1f}s)")
                failures += 1
            else:
                print(f"ok {name} ({elapsed:.1f}s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
