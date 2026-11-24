"""Per-quarter graduation / NR diagnostics for the lab GUI and CLI."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence

from nowa_sandbox.procurement_fitness import (
    GRADUATION_THRESHOLDS,
    NON_REGRESSION_FLOOR,
    PROCUREMENT_CRITERIA,
    STAGE_1A_CRITERIA,
    STAGE_CRITERIA,
)
from nowa_sandbox.stage_baseline import non_regression_floor


# Exact score when all accepted orders go to one supplier:
# 0.6*(1-1) + 0.4*(1/3).
SINGLE_SUPPLIER_SCORE = 0.6 * 0.0 + 0.4 * (1.0 / 3.0)
MONOPOLY_TOLERANCE = 0.015


@dataclass
class CriterionDiagnosis:
    criterion: str
    value: float
    threshold: float
    gating: bool
    passed_gate: bool
    nr_floor: Optional[float] = None
    nr_ok: Optional[bool] = None


@dataclass
class QuarterDiagnosis:
    quarter_index: Any
    stage: str
    all_passed: bool
    qualifies: bool
    monopoly: bool
    gate_failures: List[str] = field(default_factory=list)
    nr_failures: List[str] = field(default_factory=list)
    criteria: List[CriterionDiagnosis] = field(default_factory=list)
    action_counts: Dict[str, int] = field(default_factory=dict)
    verdict_key: str = "diag.verdict.unknown"
    verdict_args: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "quarter_index": self.quarter_index,
            "stage": self.stage,
            "all_passed": self.all_passed,
            "qualifies": self.qualifies,
            "monopoly": self.monopoly,
            "gate_failures": list(self.gate_failures),
            "nr_failures": list(self.nr_failures),
            "action_counts": dict(self.action_counts),
            "verdict_key": self.verdict_key,
            "verdict_args": dict(self.verdict_args),
            "criteria": [
                {
                    "criterion": c.criterion,
                    "value": c.value,
                    "threshold": c.threshold,
                    "gating": c.gating,
                    "passed_gate": c.passed_gate,
                    "nr_floor": c.nr_floor,
                    "nr_ok": c.nr_ok,
                }
                for c in self.criteria
            ],
        }


def is_single_supplier_monopoly(diversification: float) -> bool:
    return abs(float(diversification) - SINGLE_SUPPLIER_SCORE) <= MONOPOLY_TOLERANCE


def nr_floors_from_baseline(
    baseline: Optional[Mapping[str, float]] = None,
    spread_iqr: Optional[Mapping[str, float]] = None,
    cost_vs_chance_median: Optional[float] = None,
    cost_vs_chance_iqr: Optional[float] = None,
) -> Dict[str, float]:
    """Effective Stage 1a non-regression floors (empty if no baseline).

    When a normalized-savings median is present, the ``cost_efficiency``
    floor is that series' unclipped floor. The displayed key stays
    ``cost_efficiency`` so the six-criterion guard keeps its names.
    """
    baseline = dict(baseline or {})
    spread = dict(spread_iqr or {})
    floors: Dict[str, float] = {}
    for criterion in STAGE_1A_CRITERIA:
        if criterion == "cost_efficiency" and cost_vs_chance_median is not None:
            floors[criterion] = non_regression_floor(
                float(cost_vs_chance_median),
                float(0.0 if cost_vs_chance_iqr is None else cost_vs_chance_iqr),
                base_multiplier=NON_REGRESSION_FLOOR,
                clip_at_zero=False,
            )
            continue
        if criterion not in baseline:
            continue
        median = float(baseline[criterion])
        if criterion in spread:
            floors[criterion] = non_regression_floor(
                median,
                float(spread[criterion]),
                base_multiplier=NON_REGRESSION_FLOOR,
            )
        else:
            floors[criterion] = median * NON_REGRESSION_FLOOR
    return floors


def diagnose_quarter(
    record: Mapping[str, Any],
    *,
    thresholds: Optional[Mapping[str, float]] = None,
    nr_floors: Optional[Mapping[str, float]] = None,
    stage: Optional[str] = None,
) -> QuarterDiagnosis:
    """Explain why a quarter did or did not contribute to graduation."""
    graduation = dict(record.get("graduation") or {})
    fitness = dict(record.get("fitness") or {})
    nr = record.get("non_regression")
    world = dict(record.get("world_summary") or {})

    resolved_stage = str(stage or graduation.get("stage") or "1a").strip()
    if resolved_stage not in STAGE_CRITERIA:
        resolved_stage = "1a"
    gating = set(STAGE_CRITERIA[resolved_stage])

    thresh = dict(GRADUATION_THRESHOLDS)
    thresh.update({k: float(v) for k, v in dict(thresholds or {}).items()})
    for key in PROCUREMENT_CRITERIA:
        entry = graduation.get(key)
        if isinstance(entry, Mapping) and "threshold" in entry:
            thresh[key] = float(entry["threshold"])

    floors = dict(nr_floors or {})
    # A loaded Stage 1a baseline file must not paint NR failures onto 1a
    # quarters, where the trainer never ran the non-regression guard.
    if resolved_stage != "1b" and not isinstance(nr, Mapping):
        floors = {}
    criteria: List[CriterionDiagnosis] = []
    gate_failures: List[str] = []
    for key in PROCUREMENT_CRITERIA:
        entry = graduation.get(key) if isinstance(graduation.get(key), Mapping) else {}
        value = float((entry or {}).get("value", fitness.get(key, 0.0)) or 0.0)
        threshold = float((entry or {}).get("threshold", thresh.get(key, 0.0)))
        is_gating = bool((entry or {}).get("gating", key in gating))
        passed = bool((entry or {}).get("passed", value >= threshold))
        if is_gating and not passed:
            gate_failures.append(key)

        nr_floor = floors.get(key)
        nr_ok: Optional[bool] = None
        if isinstance(nr, Mapping) and key in nr:
            nr_ok = bool(nr[key])
        elif nr_floor is not None and key in STAGE_1A_CRITERIA:
            nr_ok = value >= float(nr_floor)

        criteria.append(
            CriterionDiagnosis(
                criterion=key,
                value=value,
                threshold=threshold,
                gating=is_gating,
                passed_gate=passed,
                nr_floor=float(nr_floor) if nr_floor is not None else None,
                nr_ok=nr_ok,
            )
        )

    nr_failures = [c.criterion for c in criteria if c.nr_ok is False]
    all_passed = bool(graduation.get("all_passed"))
    if not graduation and gating:
        all_passed = not gate_failures

    if nr is None and not floors:
        qualifies = all_passed
        nr_failures = []
    else:
        qualifies = all_passed and not nr_failures

    diversif = next(
        (c.value for c in criteria if c.criterion == "supplier_diversification"),
        float(fitness.get("supplier_diversification", 0.0) or 0.0),
    )
    monopoly = is_single_supplier_monopoly(diversif)

    action_counts: Dict[str, int] = {}
    raw_actions = world.get("action_counts")
    if isinstance(raw_actions, Mapping):
        action_counts = {str(k): int(v) for k, v in raw_actions.items()}

    verdict_key, verdict_args = _verdict(
        resolved_stage=resolved_stage,
        all_passed=all_passed,
        qualifies=qualifies,
        monopoly=monopoly,
        gate_failures=gate_failures,
        nr_failures=nr_failures,
    )

    return QuarterDiagnosis(
        quarter_index=record.get("quarter_index"),
        stage=resolved_stage,
        all_passed=all_passed,
        qualifies=qualifies,
        monopoly=monopoly,
        gate_failures=gate_failures,
        nr_failures=nr_failures,
        criteria=criteria,
        action_counts=action_counts,
        verdict_key=verdict_key,
        verdict_args=verdict_args,
    )


def format_diagnosis_text(
    diagnosis: QuarterDiagnosis,
    *,
    translate=None,
    criterion_label=None,
) -> str:
    """Plain-text panel body. ``translate(key, **kwargs)`` optional."""

    def t(key: str, **kwargs: Any) -> str:
        if translate is None:
            return key.format(**kwargs) if kwargs else key
        return translate(key, **kwargs)

    def label(cid: str) -> str:
        if criterion_label is not None:
            return criterion_label(cid)
        return cid

    lines = [
        t("diag.header", q=diagnosis.quarter_index, stage=diagnosis.stage),
        t(
            "diag.verdict_line",
            text=t(diagnosis.verdict_key, **diagnosis.verdict_args),
        ),
        "",
    ]
    if diagnosis.monopoly:
        lines.append(t("diag.monopoly_flag", score=f"{SINGLE_SUPPLIER_SCORE:.3f}"))
    lines.append(
        t(
            "diag.flags",
            all_passed=t("yes") if diagnosis.all_passed else t("no"),
            qualifies=t("yes") if diagnosis.qualifies else t("no"),
        )
    )
    if diagnosis.gate_failures:
        lines.append(
            t(
                "diag.gate_fail",
                items=", ".join(label(c) for c in diagnosis.gate_failures),
            )
        )
    if diagnosis.nr_failures:
        lines.append(
            t(
                "diag.nr_fail",
                items=", ".join(label(c) for c in diagnosis.nr_failures),
            )
        )
    lines.append("")
    lines.append(t("diag.table_header"))
    for c in diagnosis.criteria:
        gate_mark = "G" if c.gating else " "
        ok = "OK" if c.passed_gate else "FAIL"
        nr = ""
        if c.nr_ok is not None:
            floor = c.nr_floor if c.nr_floor is not None else 0.0
            nr = " NR:OK" if c.nr_ok else f" NR:FAIL(>={floor:.3f})"
        elif c.nr_floor is not None:
            nr = f" NR:>={c.nr_floor:.3f}"
        lines.append(
            f"  [{gate_mark}] {label(c.criterion):<28} "
            f"{c.value:.3f} / {c.threshold:.2f}  {ok}{nr}"
        )
    if diagnosis.action_counts:
        lines.append("")
        lines.append(t("diag.actions_header"))
        for action, count in sorted(
            diagnosis.action_counts.items(), key=lambda kv: (-kv[1], kv[0])
        ):
            lines.append(f"  {action}: {count}")
    return "\n".join(lines)


def _verdict(
    *,
    resolved_stage: str,
    all_passed: bool,
    qualifies: bool,
    monopoly: bool,
    gate_failures: Sequence[str],
    nr_failures: Sequence[str],
) -> tuple:
    if qualifies:
        return "diag.verdict.qualifies", {}
    if all_passed and nr_failures:
        return "diag.verdict.nr_blocks", {"items": ", ".join(nr_failures)}
    if monopoly and "supplier_diversification" in gate_failures:
        return "diag.verdict.monopoly", {}
    if gate_failures:
        return "diag.verdict.gate_fail", {
            "items": ", ".join(gate_failures),
            "stage": resolved_stage,
        }
    return "diag.verdict.unknown", {}


__all__ = [
    "CriterionDiagnosis",
    "MONOPOLY_TOLERANCE",
    "QuarterDiagnosis",
    "SINGLE_SUPPLIER_SCORE",
    "diagnose_quarter",
    "format_diagnosis_text",
    "is_single_supplier_monopoly",
    "nr_floors_from_baseline",
]
