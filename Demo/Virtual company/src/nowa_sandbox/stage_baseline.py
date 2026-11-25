"""Stage 1a baseline: what Stage 1b is not allowed to regress below.

v1.2: the default is the **median across all quarters** (typical performance),
not the mean of the last few successful ones (peak performance). Peak-based
baselines produced a floor that flagged normal Stage 1a volatility as
regression once suppliers became persistent.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from ._common import safe_float
from .procurement_fitness import STAGE_1A_CRITERIA


BASELINE_QUARTERS = 5
"""Trailing successful quarters used by the legacy ``mean_best`` method."""

MIN_QUARTERS_FOR_BASELINE = 15
"""Below this, a median is too noisy to trust as a Stage 1b floor reference."""

HIGH_VOLATILITY_IQR = 0.3
"""IQR above this is flagged as high quarter-to-quarter volatility."""

COST_VS_CHANCE_FLOOR_DELTA = 0.03
"""Lower bound of the normalized cost floor (``cost_vs_chance``).

A degenerate or near-zero Stage 1a baseline must not let a random policy
pass the Stage 1b guard. Allowed range is 0.02–0.05.
"""

COST_VS_CHANCE_FLOOR_DELTA_MIN = 0.02
COST_VS_CHANCE_FLOOR_DELTA_MAX = 0.05

BASELINE_METHODS = ("median_all", "mean_best")


def clamp_cost_vs_chance_floor_delta(value: Any) -> float:
    """Keep δ inside the allowed 0.02–0.05 band."""
    delta = safe_float(value, COST_VS_CHANCE_FLOOR_DELTA)
    return min(
        COST_VS_CHANCE_FLOOR_DELTA_MAX,
        max(COST_VS_CHANCE_FLOOR_DELTA_MIN, delta),
    )


def _world_summary_of(quarter: Any) -> Mapping[str, Any]:
    """Read ``world_summary`` from a JSON record or a QuarterResult."""
    if isinstance(quarter, Mapping):
        summary = quarter.get("world_summary")
        return summary if isinstance(summary, Mapping) else {}
    summary = getattr(quarter, "world_summary", None)
    return summary if isinstance(summary, Mapping) else {}


def _cost_vs_chance_values(quarters: Sequence[Any]) -> List[float]:
    """Normalized savings present on a quarter. Missing keys are skipped."""
    values: List[float] = []
    for quarter in quarters:
        summary = _world_summary_of(quarter)
        if "cost_vs_chance" not in summary:
            continue
        values.append(safe_float(summary.get("cost_vs_chance"), 0.0))
    return values


def _fitness_of(quarter: Any) -> Mapping[str, Any]:
    """Read the fitness mapping from a JSON record or a QuarterResult."""
    if isinstance(quarter, Mapping):
        fitness = quarter.get("fitness")
        if isinstance(fitness, Mapping):
            return fitness
        return {}
    fitness = getattr(quarter, "fitness", None)
    as_dict = getattr(fitness, "as_dict", None)
    return as_dict() if callable(as_dict) else {}


def _graduated(quarter: Any) -> bool:
    if isinstance(quarter, Mapping):
        graduation = quarter.get("graduation")
    else:
        graduation = getattr(quarter, "graduation", None)
    return bool((graduation or {}).get("all_passed")) if isinstance(
        graduation, Mapping
    ) else False


def _quarter_index(quarter: Any, fallback: int) -> int:
    if isinstance(quarter, Mapping):
        value = quarter.get("quarter_index")
    else:
        value = getattr(quarter, "quarter_index", None)
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def successful_quarters(quarters: Sequence[Any]) -> List[Any]:
    """Quarters whose graduation report said all gating criteria passed."""
    return [q for q in (quarters or []) if _graduated(q)]


def _iqr(values: Sequence[float]) -> float:
    """Interquartile range; 0.0 for fewer than two samples."""
    if len(values) < 2:
        return 0.0
    ordered = sorted(values)
    n = len(ordered)
    q1 = ordered[n // 4]
    q3 = ordered[(3 * n) // 4]
    return float(q3 - q1)


def non_regression_floor(
    median_value: float,
    iqr: float,
    base_multiplier: float = 0.9,
    clip_at_zero: bool = True,
    lower_bound: Optional[float] = None,
) -> float:
    """Volatility-aware floor for a single Stage 1a criterion (spec v1.2).

    Stable criteria (IQR near 0) keep the classic ``median * 0.9`` bar.
    Volatile ones relax toward ``median - iqr``, so swings that already
    happened throughout Stage 1a are not treated as Stage 1b regression.

    Raw criteria clip at 0. Normalized savings (``cost_vs_chance``) pass
    ``lower_bound=δ`` instead: ``max(min(0.9*median, median-IQR), δ)``.
    δ stops a random policy from clearing a degenerate near-zero baseline.
    """
    median_value = safe_float(median_value, 0.0)
    iqr = max(0.0, safe_float(iqr, 0.0))
    base_multiplier = safe_float(base_multiplier, 0.9)
    strict_floor = median_value * base_multiplier
    volatility_floor = median_value - iqr
    floor = min(strict_floor, volatility_floor)
    if lower_bound is not None:
        return max(safe_float(lower_bound, 0.0), floor)
    if clip_at_zero:
        return max(0.0, floor)
    return floor


def compute_stage_1a_baseline(
    quarters: Sequence[Any],
    method: str = "median_all",
    last_n: int = BASELINE_QUARTERS,
) -> Dict[str, Any]:
    """Build a Stage 1a baseline payload.

    ``method="median_all"`` (default, v1.2): median and IQR across **all**
    quarters. Requires at least :data:`MIN_QUARTERS_FOR_BASELINE` samples.

    ``method="mean_best"`` (legacy v1.1): mean of the last ``last_n``
    successful quarters. Kept for side-by-side diagnostics only — never feed
    this into the non-regression guard (constraint B1).
    """
    quarters = list(quarters or [])
    if not quarters:
        raise ValueError("cannot compute a baseline from zero quarters")

    if method not in BASELINE_METHODS:
        raise ValueError(
            f"unknown baseline method {method!r}; expected one of {BASELINE_METHODS}"
        )

    if method == "mean_best":
        return _compute_mean_best(quarters, last_n=last_n)
    return _compute_median_all(quarters)


def _compute_median_all(quarters: List[Any]) -> Dict[str, Any]:
    if len(quarters) < MIN_QUARTERS_FOR_BASELINE:
        raise ValueError(
            f"Only {len(quarters)} quarters available; need at least "
            f"{MIN_QUARTERS_FOR_BASELINE} for a median baseline stable "
            f"enough to gate Stage 1b. Run more Stage 1a quarters."
        )

    baseline: Dict[str, float] = {}
    spread: Dict[str, float] = {}
    for criterion in STAGE_1A_CRITERIA:
        values = [
            safe_float(_fitness_of(q).get(criterion), 0.0) for q in quarters
        ]
        baseline[criterion] = round(statistics.median(values), 4)
        spread[criterion] = round(_iqr(values), 4)

    passed_count = len(successful_quarters(quarters))
    payload: Dict[str, Any] = {
        "stage_1a_baseline": baseline,
        "stage_1a_spread_iqr": spread,
        "method": "median_all",
        "n_quarters_used": len(quarters),
        "n_quarters_passed": passed_count,
        "from_successful_quarters": passed_count > 0,
        "computed_from_quarters": [
            _quarter_index(q, i) for i, q in enumerate(quarters, start=1)
        ],
    }
    normalized = _cost_vs_chance_values(quarters)
    if len(normalized) >= MIN_QUARTERS_FOR_BASELINE:
        payload["cost_vs_chance_median"] = round(statistics.median(normalized), 4)
        payload["cost_vs_chance_iqr"] = round(_iqr(normalized), 4)
    return payload


def _compute_mean_best(quarters: List[Any], last_n: int) -> Dict[str, Any]:
    """Legacy v1.1 cherry-pick — diagnostic comparison only (B1)."""
    good = successful_quarters(quarters)
    from_successful = bool(good)
    selected = (good or quarters)[-max(1, int(last_n)):]

    baseline: Dict[str, float] = {}
    spread: Dict[str, float] = {}
    for criterion in STAGE_1A_CRITERIA:
        values = [
            safe_float(_fitness_of(q).get(criterion), 0.0) for q in selected
        ]
        baseline[criterion] = round(sum(values) / len(values), 4)
        spread[criterion] = round(_iqr(values), 4)

    return {
        "stage_1a_baseline": baseline,
        "stage_1a_spread_iqr": spread,
        "method": "mean_best",
        "n_quarters_used": len(selected),
        "n_quarters_passed": len(good),
        "from_successful_quarters": from_successful,
        "computed_from_quarters": [
            _quarter_index(q, i) for i, q in enumerate(selected, start=1)
        ],
    }


def save_baseline(
    path: str,
    payload: Mapping[str, Any],
    source: Optional[str] = None,
) -> Dict[str, Any]:
    """Write a baseline payload, tagging where it came from."""
    record = dict(payload)
    if source is not None:
        record["source"] = source
    if record.get("method") == "mean_best":
        raise ValueError(
            "Refusing to write a baseline computed with method=mean_best. "
            "This method reflects peak performance from cherry-picked "
            "quarters and produces a non-regression floor that flags normal "
            "Stage 1a variance as regression (see patch v1.2). "
            "Use method=median_all."
        )
    output = Path(path)
    if output.parent and not output.parent.exists():
        output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return record


def load_baseline_bundle(path: str) -> Dict[str, Any]:
    """Load medians, IQR spread and metadata for the non-regression guard."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))

    if isinstance(data, list):
        # v1.1.1 NR4 first: refuse a run that never graduated, before the
        # median-length check, so the error message stays actionable.
        if not successful_quarters(data):
            raise ValueError(
                f"{path} contains no graduated Stage 1a quarters. "
                f"Refusing to build a non-regression baseline from failed "
                f"quarters — this would guard Stage 1b against nothing. "
                f"Run more Stage 1a quarters, or use "
                f"stage1a_report.py --write-baseline on a run that "
                f"actually graduated."
            )
        payload = compute_stage_1a_baseline(data, method="median_all")
        payload["source"] = path
        return payload

    if isinstance(data, Mapping):
        nested = data.get("stage_1a_baseline")
        source = nested if isinstance(nested, Mapping) else data
        baseline = {
            criterion: safe_float(source.get(criterion), 0.0)
            for criterion in STAGE_1A_CRITERIA
            if criterion in source
        }
        if baseline:
            spread_raw = data.get("stage_1a_spread_iqr") or {}
            spread = {
                criterion: safe_float(spread_raw.get(criterion), 0.0)
                for criterion in STAGE_1A_CRITERIA
                if criterion in baseline
            }
            bundle = {
                "stage_1a_baseline": baseline,
                "stage_1a_spread_iqr": spread,
                "method": str(data.get("method") or "median_all"),
                "n_quarters_used": data.get("n_quarters_used"),
                "n_quarters_passed": data.get("n_quarters_passed"),
                "from_successful_quarters": bool(
                    data.get("from_successful_quarters", True)
                ),
                "computed_from_quarters": list(
                    data.get("computed_from_quarters") or []
                ),
                "source": path,
            }
            if "cost_vs_chance_median" in data:
                bundle["cost_vs_chance_median"] = safe_float(
                    data.get("cost_vs_chance_median"), 0.0
                )
                bundle["cost_vs_chance_iqr"] = safe_float(
                    data.get("cost_vs_chance_iqr"), 0.0
                )
            return bundle

    raise ValueError(
        f"{path} contains no Stage 1a baseline: expected a run result list, "
        "a mapping with a 'stage_1a_baseline' key, or a bare criterion mapping"
    )


def load_baseline(path: str) -> Dict[str, float]:
    """Load only the point estimates (medians). Prefer :func:`load_baseline_bundle`."""
    return dict(load_baseline_bundle(path)["stage_1a_baseline"])


__all__ = [
    "BASELINE_QUARTERS",
    "BASELINE_METHODS",
    "HIGH_VOLATILITY_IQR",
    "COST_VS_CHANCE_FLOOR_DELTA",
    "MIN_QUARTERS_FOR_BASELINE",
    "clamp_cost_vs_chance_floor_delta",
    "compute_stage_1a_baseline",
    "load_baseline",
    "load_baseline_bundle",
    "non_regression_floor",
    "save_baseline",
    "successful_quarters",
]
