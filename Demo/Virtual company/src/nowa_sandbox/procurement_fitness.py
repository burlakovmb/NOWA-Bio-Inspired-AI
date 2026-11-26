"""Fitness evaluation for a single agent's sandbox performance."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional

from ._common import clamp, safe_float


PROCUREMENT_CRITERIA = [
    "cost_efficiency",
    "stockout_avoidance",
    "budget_discipline",
    "supplier_diversification",
    "decision_consistency",
    "reaction_to_risk_events",
]

# v1.1 two-stage curriculum. The split is by whether a criterion depends on
# supplier_id meaning the same thing from one quarter to the next.
#
# Stage 1a ("trade school") runs against freshly randomized suppliers every
# quarter, so only identity-independent competence can be measured: reading
# cheap/expensive and safe/risky off observable attributes.
STAGE_1A_CRITERIA = [
    "cost_efficiency",
    "stockout_avoidance",
    "budget_discipline",
    "reaction_to_risk_events",
]

# Stage 1b ("internship") runs against persistent suppliers, which is the only
# setting where loyalty to a particular counterparty is a meaningful thing to
# score at all.
STAGE_1B_CRITERIA = [
    "decision_consistency",
    "supplier_diversification",
]

STAGE_CRITERIA = {"1a": STAGE_1A_CRITERIA, "1b": STAGE_1B_CRITERIA}

# Stage 1b must not buy relationship metrics by letting Stage 1a competence
# rot: a criterion may sit no lower than this fraction of its 1a baseline.
NON_REGRESSION_FLOOR = 0.9

GRADUATION_THRESHOLDS = {
    "cost_efficiency": 0.60,
    "stockout_avoidance": 0.85,
    "budget_discipline": 0.95,
    "supplier_diversification": 0.40,
    "decision_consistency": 0.60,
    "reaction_to_risk_events": 0.50,
}

# Price multipliers are drawn from this band; cost_efficiency maps it to [0,1].
MARKET_PRICE_FLOOR = 0.85
MARKET_PRICE_CEILING = 1.15

# Budget headroom below which budget_discipline starts being penalized.
BUDGET_SAFETY_MARGIN = 0.10

# Days after a risk event during which a corrective order still counts.
RISK_REACTION_WINDOW_DAYS = 5

# External surprises the agent can still do something about. Stockout is an
# *outcome* (already scored by stockout_avoidance); counting every shortfall
# day as a risk that needs a fresh order turns Stage 1b non-regression into
# a lottery once the motor covers 30 days per fill.
EXTERNAL_RISK_TYPES = frozenset({"supplier_defaulted", "demand_shock"})

# Agent chose to act, even if the motor correctly skipped a redundant order.
ORDER_INTENT_ACTIONS = frozenset({
    "place_order",
    "place_order_reliable_supplier",
    "place_order_cheap_supplier",
    "urgent_reorder",
    "diversify_supplier",
})

# place_order outcomes that mean the agent really reached out to the market.
ORDER_SUBMITTED_STATUSES = frozenset({"accepted", "rejected"})


@dataclass
class ProcurementFitnessVector:
    cost_efficiency: float
    stockout_avoidance: float
    budget_discipline: float
    supplier_diversification: float
    decision_consistency: float
    reaction_to_risk_events: float
    n_days: int
    n_orders: int

    def as_dict(self) -> Dict[str, float]:
        return {c: getattr(self, c) for c in PROCUREMENT_CRITERIA}


def _result_of(entry: Any) -> Mapping:
    result = (entry or {}).get("result")
    return result if isinstance(result, Mapping) else {}


def _n_reachable_suppliers(world: Any, product_id: Any) -> Optional[int]:
    """Live suppliers that can fill ``product_id``. ``None`` = unconstrained market."""
    offers = getattr(world, "offers", None) or {}
    if not offers:
        return None
    getter = getattr(world, "offers_for_product", None)
    if callable(getter):
        product_offers = list(getter(product_id) or [])
    else:
        pid = str(product_id or "")
        product_offers = [offer for (p, _), offer in offers.items() if p == pid]
    suppliers = getattr(world, "suppliers", None) or {}
    reachable = 0
    for offer in product_offers:
        sid = getattr(offer, "supplier_id", None)
        if sid is None and isinstance(offer, Mapping):
            sid = offer.get("supplier_id")
        supplier = suppliers.get(sid)
        if supplier is None or getattr(supplier, "is_defaulted", False):
            continue
        reachable += 1
    return reachable


def _accepted_orders(decision_log: List[dict]) -> List[dict]:
    """Decision-log entries that actually resulted in an accepted order.

    Keyed off the world's response rather than the action label: the agent
    picks between several ordering strategies ("urgent_reorder",
    "place_order_cheap_supplier", ...), so matching a literal "place_order"
    action would silently score every real run as if it had bought nothing.
    """
    return [
        entry for entry in (decision_log or [])
        if _result_of(entry).get("status") == "accepted"
    ]


def _order_attempts(decision_log: List[dict]) -> List[dict]:
    """Entries where the agent actually tried to order.

    Accepted and rejected world submits both count, and so does an order
    strategy whose motor skipped a redundant fill: the agent chose to act.
    """
    attempts = []
    for entry in decision_log or []:
        action = (entry or {}).get("action")
        if action in ORDER_INTENT_ACTIONS:
            attempts.append(entry)
        elif _result_of(entry).get("status") in ORDER_SUBMITTED_STATUSES:
            attempts.append(entry)
    return attempts


class ProcurementFitnessEvaluator:
    """Score one agent's quarter of simulated work.

    Analogous to FitnessEvaluator from the evolutionary project, adapted for a
    single agent instead of a population. Thresholds can be overridden (e.g.
    from configs/default_world.yaml) instead of being hardcoded, because
    calibration needs to move them.
    """

    def __init__(
        self,
        thresholds: Optional[Mapping[str, float]] = None,
        stage: str = "1a",
        normalize_stockout_difficulty: bool = False,
        cost_vs_chance_floor_delta: Optional[float] = None,
    ):
        if stage not in STAGE_CRITERIA:
            raise ValueError(
                f"unknown stage {stage!r}; expected one of {sorted(STAGE_CRITERIA)}"
            )
        self.stage = stage
        self.normalize_stockout_difficulty = bool(normalize_stockout_difficulty)
        from .stage_baseline import (
            COST_VS_CHANCE_FLOOR_DELTA,
            clamp_cost_vs_chance_floor_delta,
        )

        raw_delta = (
            COST_VS_CHANCE_FLOOR_DELTA
            if cost_vs_chance_floor_delta is None
            else cost_vs_chance_floor_delta
        )
        self.cost_vs_chance_floor_delta = clamp_cost_vs_chance_floor_delta(raw_delta)
        merged = dict(GRADUATION_THRESHOLDS)
        for criterion, value in dict(thresholds or {}).items():
            if criterion in merged:
                merged[criterion] = clamp(safe_float(value, merged[criterion]), 0.0, 1.0)
        self.thresholds: Dict[str, float] = merged

    @property
    def gating_criteria(self) -> List[str]:
        """Criteria that actually decide graduation at the current stage."""
        return list(STAGE_CRITERIA[self.stage])

    def evaluate(
        self,
        world: Any,
        decision_log: List[dict],
    ) -> ProcurementFitnessVector:
        """Score a finished quarter.

        decision_log entries look like::

            {"day": int, "action": "place_order"|"wait_and_monitor",
             "supplier_id": str|None, "product_id": str|None,
             "qty": float|None, "result": dict|None}

        and are collected daily by the training loop.
        """
        decision_log = list(decision_log or [])
        return ProcurementFitnessVector(
            cost_efficiency=self._cost_efficiency(world, decision_log),
            stockout_avoidance=self._stockout_avoidance(world),
            budget_discipline=self._budget_discipline(world),
            supplier_diversification=self._supplier_diversification(
                decision_log, world
            ),
            decision_consistency=self._decision_consistency(decision_log),
            reaction_to_risk_events=self._reaction_to_risk_events(world, decision_log),
            n_days=int(getattr(world, "day", 0)),
            n_orders=len(decision_log),
        )

    # -----------------------------------------------------------
    # Individual criteria
    # -----------------------------------------------------------

    def _cost_efficiency(self, world: Any, decision_log: List[dict]) -> float:
        """1.0 = bought at or below the fair market price, 0.0 = systematic overpay.

        Legacy RNG worlds store a relative ``base_price_multiplier`` in
        ``[MARKET_PRICE_FLOOR, MARKET_PRICE_CEILING]``. Curriculum worlds use
        absolute ``SupplierOffer.unit_price`` values (e.g. 5 / 30 / 50), so
        scoring must be relative to the offers available for each product —
        otherwise absolute prices clamp the criterion to 0.
        """
        orders = _accepted_orders(decision_log)
        if not orders:
            return 0.5  # no data — neutral, not a punishment

        offers = getattr(world, "offers", None) or {}
        if offers:
            return self._cost_efficiency_from_offers(world, orders)

        suppliers = getattr(world, "suppliers", {}) or {}
        price_ratios = []
        for order in orders:
            supplier = suppliers.get(order.get("supplier_id"))
            if supplier is not None:
                price_ratios.append(safe_float(supplier.base_price_multiplier, 1.0))

        if not price_ratios:
            return 0.5

        avg_ratio = sum(price_ratios) / len(price_ratios)
        span = MARKET_PRICE_CEILING - MARKET_PRICE_FLOOR
        if span <= 0:
            return 0.5
        score = 1.0 - ((avg_ratio - MARKET_PRICE_FLOOR) / span)
        return clamp(score, 0.0, 1.0)

    def _cost_efficiency_from_offers(
        self, world: Any, orders: List[dict]
    ) -> float:
        """Score paid offer prices vs other offers for the same product."""
        scores: List[float] = []
        for order in orders:
            pid = str(order.get("product_id") or "")
            sid = str(order.get("supplier_id") or "")
            if not pid or not sid:
                continue
            product_offers = []
            if hasattr(world, "offers_for_product"):
                product_offers = list(world.offers_for_product(pid) or [])
            if not product_offers:
                continue
            prices = [max(0.01, safe_float(o.unit_price, 0.01)) for o in product_offers]
            lo = min(prices)
            hi = max(prices)

            paid = None
            result = _result_of(order)
            if "unit_price" in result:
                paid = safe_float(result.get("unit_price"), 0.0) or None
            if paid is None and hasattr(world, "get_offer"):
                offer = world.get_offer(pid, sid)
                if offer is not None:
                    paid = safe_float(offer.unit_price, 0.0) or None
            if paid is None or paid <= 0:
                continue

            if hi <= lo + 1e-12:
                # Sole offer for the SKU = paid the market rate for that product.
                scores.append(1.0)
            else:
                # 1.0 at cheapest available, 0.0 at most expensive.
                scores.append(clamp(1.0 - ((paid - lo) / (hi - lo)), 0.0, 1.0))

        if not scores:
            return 0.5
        return clamp(sum(scores) / len(scores), 0.0, 1.0)

    def chance_cost_efficiency(self, world: Any, decision_log: List[dict]) -> float:
        """Expected cost score of a uniform random supplier at the same orders.

        For each accepted order the agent actually placed, average the
        per-supplier score over every supplier available for that SKU, on
        the same scale as :meth:`_cost_efficiency` /
        :meth:`_cost_efficiency_from_offers`, then average those order
        scores the same way the agent score is averaged. No orders uses
        the same neutral 0.5 as an empty quarter.
        """
        orders = _accepted_orders(decision_log)
        if not orders:
            return 0.5
        offers = getattr(world, "offers", None) or {}
        if offers:
            return self._chance_cost_efficiency_from_offers(world, orders)
        return self._chance_cost_efficiency_from_multipliers(world, orders)

    def _chance_cost_efficiency_from_multipliers(
        self, world: Any, orders: List[dict]
    ) -> float:
        """Legacy roster: every supplier can fill every SKU. Quote noise ignored."""
        suppliers = getattr(world, "suppliers", {}) or {}
        pool = [
            safe_float(getattr(supplier, "base_price_multiplier", 1.0), 1.0)
            for supplier in suppliers.values()
        ]
        if not pool:
            return 0.5
        expected_ratio = sum(pool) / len(pool)
        ratios = []
        for order in orders:
            if suppliers.get(order.get("supplier_id")) is not None:
                ratios.append(expected_ratio)
        if not ratios:
            return 0.5
        avg_ratio = sum(ratios) / len(ratios)
        span = MARKET_PRICE_CEILING - MARKET_PRICE_FLOOR
        if span <= 0:
            return 0.5
        score = 1.0 - ((avg_ratio - MARKET_PRICE_FLOOR) / span)
        return clamp(score, 0.0, 1.0)

    def _chance_cost_efficiency_from_offers(
        self, world: Any, orders: List[dict]
    ) -> float:
        """Mean offer-score of every offer for the ordered SKU, then mean over orders."""
        scores: List[float] = []
        for order in orders:
            pid = str(order.get("product_id") or "")
            sid = str(order.get("supplier_id") or "")
            if not pid or not sid:
                continue
            product_offers = []
            if hasattr(world, "offers_for_product"):
                product_offers = list(world.offers_for_product(pid) or [])
            if not product_offers:
                continue
            prices = [
                max(0.01, safe_float(o.unit_price, 0.01)) for o in product_offers
            ]
            lo = min(prices)
            hi = max(prices)
            paid = None
            result = _result_of(order)
            if "unit_price" in result:
                paid = safe_float(result.get("unit_price"), 0.0) or None
            if paid is None and hasattr(world, "get_offer"):
                offer = world.get_offer(pid, sid)
                if offer is not None:
                    paid = safe_float(offer.unit_price, 0.0) or None
            if paid is None or paid <= 0:
                continue
            if hi <= lo + 1e-12:
                order_scores = [1.0]
            else:
                order_scores = [
                    clamp(1.0 - ((price - lo) / (hi - lo)), 0.0, 1.0)
                    for price in prices
                ]
            scores.append(sum(order_scores) / len(order_scores))
        if not scores:
            return 0.5
        return clamp(sum(scores) / len(scores), 0.0, 1.0)

    def _stockout_avoidance(self, world: Any) -> float:
        """Fraction of demand met without stockout; optionally difficulty-normalized.

        ``normalize_stockout_difficulty=False`` (default, Q3b path): raw score,
        identical to v1.0–v1.2.

        ``normalize_stockout_difficulty=True`` (Q3a diagnostic): divide by the
        world's theoretical maximum so a hard world does not cap a perfect
        agent below 1.0.
        """
        products = list((getattr(world, "products", {}) or {}).values())
        day = int(getattr(world, "day", 0))
        total_demand_estimate = sum(
            safe_float(p.base_demand_per_day, 0.0) * day for p in products
        )
        total_stockout = sum(
            safe_float(p.cumulative_stockout_units, 0.0) for p in products
        )
        if total_demand_estimate <= 0:
            return 1.0
        stockout_ratio = total_stockout / total_demand_estimate
        # x5 penalty keeps the criterion sensitive to small shortfalls.
        raw_score = clamp(1.0 - min(1.0, stockout_ratio * 5.0), 0.0, 1.0)

        if not self.normalize_stockout_difficulty:
            return raw_score

        from .world_difficulty import estimate_difficulty

        theoretical_max = estimate_difficulty(world).stockout_theoretical_max()
        if theoretical_max <= 0.0:
            return raw_score
        return min(1.0, raw_score / theoretical_max)

    def _budget_discipline(self, world: Any) -> float:
        if getattr(world, "bankrupt", False):
            return 0.0

        initial_budget = safe_float(getattr(world, "initial_budget", 0.0), 0.0)
        if initial_budget <= 0:
            return 0.0

        min_budget_ratio_observed = 1.0
        for snapshot in getattr(world, "history", []) or []:
            ratio = safe_float(snapshot.get("budget"), 0.0) / initial_budget
            min_budget_ratio_observed = min(min_budget_ratio_observed, ratio)

        if min_budget_ratio_observed >= BUDGET_SAFETY_MARGIN:
            return 1.0
        return clamp(min_budget_ratio_observed / BUDGET_SAFETY_MARGIN, 0.0, 1.0)

    def _supplier_diversification(
        self, decision_log: List[dict], world: Any = None
    ) -> float:
        """Share of orders that is not a forced single-source monopoly.

        Curriculum worlds may pin a SKU to one supplier (jars → supplier_001).
        Counting those fills as monopoly punishes the agent for a constraint
        it cannot break, and Stage 1b then never clears the 0.40 gate.
        Only SKUs with two or more reachable counterparties are scored.
        """
        orders = _accepted_orders(decision_log)
        if len(orders) < 2:
            return 0.5

        contestable: List[dict] = []
        saw_offer_graph = False
        for order in orders:
            n_options = _n_reachable_suppliers(world, order.get("product_id"))
            if n_options is None:
                contestable.append(order)
                continue
            saw_offer_graph = True
            if n_options >= 2:
                contestable.append(order)

        if saw_offer_graph and not contestable:
            return 1.0

        scored = contestable if contestable else orders
        supplier_counts = Counter(d.get("supplier_id") for d in scored)
        n_suppliers_used = len(supplier_counts)
        n_total_orders = len(scored)
        max_share = max(supplier_counts.values()) / n_total_orders

        # Ideal: several suppliers used, none dominating.
        diversity_score = 1.0 - max_share
        supplier_count_bonus = min(1.0, n_suppliers_used / 3.0)
        return clamp(0.6 * diversity_score + 0.4 * supplier_count_bonus, 0.0, 1.0)

    def _decision_consistency(self, decision_log: List[dict]) -> float:
        """Similar situations should produce similar decisions.

        High variance of supplier choice for the same product means chaotic,
        unpredictable behaviour and scores low.
        """
        orders = _accepted_orders(decision_log)
        if len(orders) < 4:
            return 0.5

        by_product = defaultdict(list)
        for order in orders:
            by_product[order.get("product_id")].append(order)

        consistency_scores = []
        for product_orders in by_product.values():
            if len(product_orders) < 2:
                continue
            suppliers_used = [o.get("supplier_id") for o in product_orders]
            most_common_count = Counter(suppliers_used).most_common(1)[0][1]
            consistency_scores.append(most_common_count / len(suppliers_used))

        if not consistency_scores:
            return 0.5
        return clamp(sum(consistency_scores) / len(consistency_scores), 0.0, 1.0)

    def _reaction_to_risk_events(self, world: Any, decision_log: List[dict]) -> float:
        """After an *actionable* external risk, the agent should try to act.

        Demand shocks that the warehouse already absorbs are not scored: the
        right move is to wait. Stockouts are scored by ``stockout_avoidance``.
        A quarter with nothing to react to is a vacuous pass (1.0), not 0.5 —
        0.5 sits below the typical Stage 1b non-regression floor (~0.545).
        """
        risk_days = set()
        for snapshot in getattr(world, "history", []) or []:
            events = snapshot.get("events", []) or []
            day = snapshot.get("day")
            types_by_product = {}
            defaulted = False
            for event in events:
                etype = (event or {}).get("type")
                if etype == "supplier_defaulted":
                    defaulted = True
                elif etype in EXTERNAL_RISK_TYPES or etype == "stockout":
                    pid = (event or {}).get("product_id")
                    types_by_product.setdefault(pid, set()).add(etype)
            if defaulted:
                risk_days.add(day)
            for kinds in types_by_product.values():
                if "demand_shock" in kinds and "stockout" in kinds:
                    risk_days.add(day)

        if not risk_days:
            return 1.0

        action_days = {
            d.get("day") for d in _order_attempts(decision_log)
            if d.get("day") is not None
        }

        responded = 0
        for risk_day in risk_days:
            if risk_day is None:
                continue
            if any(
                risk_day <= ad <= risk_day + RISK_REACTION_WINDOW_DAYS
                for ad in action_days
            ):
                responded += 1

        return clamp(responded / len(risk_days), 0.0, 1.0)

    # -----------------------------------------------------------
    # Graduation
    # -----------------------------------------------------------

    def graduation_report(self, vector: ProcurementFitnessVector) -> dict:
        """Score every criterion, but let only the current stage's ones gate.

        All six always appear in the report, so a run stays fully diagnosable;
        ``gating`` marks which of them ``all_passed`` was actually computed
        from. The rest are monitored: they are expected not to collapse, which
        is enforced separately by :meth:`check_non_regression`.
        """
        active = set(STAGE_CRITERIA[self.stage])
        criteria_results: Dict[str, dict] = {}
        for criterion, threshold in self.thresholds.items():
            value = safe_float(getattr(vector, criterion, 0.0), 0.0)
            criteria_results[criterion] = {
                "value": round(value, 4),
                "threshold": threshold,
                "passed": value >= threshold,
                "gating": criterion in active,
            }

        gating_results = [r for r in criteria_results.values() if r["gating"]]
        report: Dict[str, Any] = dict(criteria_results)
        report["stage"] = self.stage
        report["all_passed"] = bool(gating_results) and all(
            r["passed"] for r in gating_results
        )
        report["n_days"] = vector.n_days
        report["n_orders"] = vector.n_orders
        return report

    def check_non_regression(
        self,
        vector: ProcurementFitnessVector,
        stage_1a_baseline: Mapping[str, float],
        stage_1a_spread_iqr: Optional[Mapping[str, float]] = None,
        cost_vs_chance: Optional[float] = None,
        cost_vs_chance_median: Optional[float] = None,
        cost_vs_chance_iqr: Optional[float] = None,
    ) -> Dict[str, bool]:
        """Verify Stage 1a competence survived into Stage 1b.

        ``stage_1a_baseline`` holds the typical (median) Stage 1a scores.
        When ``stage_1a_spread_iqr`` is provided, each criterion's floor is
        the volatility-aware :func:`non_regression_floor` (v1.2) so noisy
        criteria are not punished for swings that were already normal in
        Stage 1a. Without spread data the classic
        ``baseline * NON_REGRESSION_FLOOR`` bar is kept.

        A criterion absent from the baseline gets a floor of 0.0, i.e. it is
        reported as passing rather than blocking on missing data.

        When ``cost_vs_chance_median`` is set, ``cost_efficiency`` is judged
        on ``cost_vs_chance`` against
        ``max(min(0.9*median, median-IQR), δ)``. δ is
        ``cost_vs_chance_floor_delta`` (default 0.03). Baselines written
        before the normalized fields keep the raw cost check.
        """
        from .stage_baseline import non_regression_floor

        baseline = stage_1a_baseline or {}
        spread = stage_1a_spread_iqr or {}
        result: Dict[str, bool] = {}
        for criterion in STAGE_1A_CRITERIA:
            if (
                criterion == "cost_efficiency"
                and cost_vs_chance_median is not None
            ):
                current = safe_float(
                    cost_vs_chance
                    if cost_vs_chance is not None
                    else getattr(vector, criterion, 0.0),
                    0.0,
                )
                median_value = safe_float(cost_vs_chance_median, 0.0)
                floor = non_regression_floor(
                    median_value,
                    safe_float(cost_vs_chance_iqr, 0.0),
                    base_multiplier=NON_REGRESSION_FLOOR,
                    lower_bound=self.cost_vs_chance_floor_delta,
                )
                result[criterion] = current >= floor
                continue
            current = safe_float(getattr(vector, criterion, 0.0), 0.0)
            if criterion not in baseline:
                result[criterion] = True
                continue
            median_value = safe_float(baseline.get(criterion), 0.0)
            if criterion in spread:
                floor = non_regression_floor(
                    median_value,
                    safe_float(spread.get(criterion), 0.0),
                    base_multiplier=NON_REGRESSION_FLOOR,
                )
            else:
                floor = median_value * NON_REGRESSION_FLOOR
            result[criterion] = current >= floor
        return result


__all__ = [
    "ProcurementFitnessEvaluator",
    "ProcurementFitnessVector",
    "PROCUREMENT_CRITERIA",
    "GRADUATION_THRESHOLDS",
    "STAGE_1A_CRITERIA",
    "STAGE_1B_CRITERIA",
    "STAGE_CRITERIA",
    "NON_REGRESSION_FLOOR",
]
