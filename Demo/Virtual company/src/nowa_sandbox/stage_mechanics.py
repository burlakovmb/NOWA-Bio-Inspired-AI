"""Stage graduation, streaks and non-regression.

Criterion names and KPI formulas stay in the scenario. This module only
decides which of the supplied criteria gate a stage, how a report is shaped,
and whether a later stage fell through a baseline floor.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

from ._common import clamp, is_finite_number, safe_float


GRADUATION_MIN_STREAK = 3
"""A later stage must hold this many consecutive qualifying periods."""


def merge_thresholds(
    raw: Optional[Mapping[str, Any]],
    defaults: Optional[Mapping[str, float]],
) -> Dict[str, float]:
    """Load criterion thresholds without assuming a fixed set of names.

    When ``defaults`` is a mapping, unknown keys are dropped and missing
    keys keep the default. When ``defaults`` is ``None``, every finite key
    in ``raw`` is kept.
    """
    if defaults is None:
        merged: Dict[str, float] = {}
        for name, value in dict(raw or {}).items():
            if not is_finite_number(value):
                continue
            merged[str(name)] = clamp(safe_float(value, 0.0), 0.0, 1.0)
        return merged
    merged = {str(name): float(value) for name, value in dict(defaults).items()}
    for name, value in dict(raw or {}).items():
        if name in merged:
            merged[str(name)] = clamp(safe_float(value, merged[str(name)]), 0.0, 1.0)
    return merged


def graduation_report(
    vector: Any,
    thresholds: Mapping[str, float],
    stage: str,
    gating: Sequence[str],
) -> dict:
    """Score every supplied criterion. Only ``gating`` decides ``all_passed``."""
    active = set(gating)
    criteria_results: Dict[str, dict] = {}
    for criterion, threshold in thresholds.items():
        value = safe_float(getattr(vector, criterion, 0.0), 0.0)
        criteria_results[criterion] = {
            "value": round(value, 4),
            "threshold": threshold,
            "passed": value >= threshold,
            "gating": criterion in active,
        }
    gating_results = [row for row in criteria_results.values() if row["gating"]]
    report: Dict[str, Any] = dict(criteria_results)
    report["stage"] = stage
    report["all_passed"] = bool(gating_results) and all(
        row["passed"] for row in gating_results
    )
    report["n_days"] = getattr(vector, "n_days", 0)
    report["n_orders"] = getattr(vector, "n_orders", 0)
    return report


def check_non_regression(
    vector: Any,
    monitored: Sequence[str],
    baseline: Optional[Mapping[str, float]],
    spread: Optional[Mapping[str, float]] = None,
    *,
    normalized_name: Optional[str] = None,
    normalized_value: Optional[float] = None,
    normalized_median: Optional[float] = None,
    normalized_spread: Optional[float] = None,
    normalized_floor_delta: float = 0.03,
    floor_fraction: float = 0.9,
) -> Dict[str, bool]:
    """Compare ``monitored`` criteria with a baseline.

    A criterion missing from the baseline passes. When ``normalized_median``
    is set, ``normalized_name`` is judged on ``normalized_value`` instead of
    the raw attribute.
    """
    from .stage_baseline import non_regression_floor

    known = baseline or {}
    spread_map = spread or {}
    result: Dict[str, bool] = {}
    for criterion in monitored:
        if criterion == normalized_name and normalized_median is not None:
            current = safe_float(
                normalized_value
                if normalized_value is not None
                else getattr(vector, criterion, 0.0),
                0.0,
            )
            median_value = safe_float(normalized_median, 0.0)
            floor = non_regression_floor(
                median_value,
                safe_float(normalized_spread, 0.0),
                base_multiplier=floor_fraction,
                lower_bound=normalized_floor_delta,
            )
            result[criterion] = current >= floor
            continue
        current = safe_float(getattr(vector, criterion, 0.0), 0.0)
        if criterion not in known:
            result[criterion] = True
            continue
        median_value = safe_float(known.get(criterion), 0.0)
        if criterion in spread_map:
            floor = non_regression_floor(
                median_value,
                safe_float(spread_map.get(criterion), 0.0),
                base_multiplier=floor_fraction,
            )
        else:
            floor = median_value * floor_fraction
        result[criterion] = current >= floor
    return result


def period_qualifies(period: Any) -> bool:
    """A period counts toward the streak when it passed and did not regress.

    ``non_regression is None`` means there is nothing to guard, so only
    ``all_passed`` matters.
    """
    if not (getattr(period, "graduation", None) or {}).get("all_passed"):
        return False
    guard = getattr(period, "non_regression", None)
    if guard is None:
        return True
    return not any(ok is False for ok in guard.values())


def stage_of_period(period: Any) -> Optional[str]:
    return (getattr(period, "graduation", None) or {}).get("stage")


def current_qualifying_streak(
    periods: Sequence[Any],
    stage: Optional[str] = None,
) -> int:
    """Trailing run of qualifying periods, recomputed from history."""
    items = list(periods or [])
    if stage is None and items:
        stage = stage_of_period(items[-1])
    streak = 0
    for period in reversed(items):
        period_stage = stage_of_period(period)
        if stage and period_stage and period_stage != stage:
            break
        if period_qualifies(period):
            streak += 1
        else:
            break
    return streak


def ensure_stage_start(
    result: Any,
    start_index: int,
    has_roster: bool,
) -> None:
    """Record the first later-stage period, including after a resume.

    No marker and no roster: this period opens the stage. No marker but a
    restored roster: anchor at period 1 so the restored roster stays until
    the next boundary.
    """
    if getattr(result, "stage_1b_start_quarter", None) is not None:
        return
    if has_roster:
        result.stage_1b_start_quarter = 1
    else:
        result.stage_1b_start_quarter = int(start_index)


def roster_period_boundary(
    period_index: int,
    stage_start: int,
    period: int,
) -> bool:
    """True on the first period of each roster set, counted from stage start."""
    period = max(1, int(period))
    offset = int(period_index) - int(stage_start)
    return offset >= 0 and offset % period == 0


def action_counts(decision_log: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for entry in decision_log or []:
        action = str((entry or {}).get("action") or "unknown")
        counts[action] = counts.get(action, 0) + 1
    return counts


__all__ = [
    "GRADUATION_MIN_STREAK",
    "action_counts",
    "check_non_regression",
    "current_qualifying_streak",
    "ensure_stage_start",
    "graduation_report",
    "merge_thresholds",
    "period_qualifies",
    "roster_period_boundary",
    "stage_of_period",
]
