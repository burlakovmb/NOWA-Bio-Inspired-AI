"""Encode ProcurementWorld observations into NOWA context_events.

Same principle as affective_mapping.yaml in the parent specification, but the
classification is built into code here because the domain is known ahead of
time (unlike the universal BusinessEventEncoder used for real MCP data).
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from .price_memory import (
    DEFAULT_PRICE_BUCKET_Z,
    lookup_price_reference,
    price_context_token,
)

from ._common import clamp, ensure_core_src_on_path, safe_float

ensure_core_src_on_path()
from affective_space import mapped_event_tokens  # noqa: E402


def classify_world_events(tick_result: dict) -> List[str]:
    """Extract named business events from a world.tick() result."""
    event_names: List[str] = []
    for event in (tick_result or {}).get("events", []) or []:
        etype = (event or {}).get("type")
        if etype == "stockout":
            event_names.append("stock_critical_low")
        elif etype == "order_arrived":
            event_names.append(
                "order_arrived_on_time" if event.get("on_time") else "order_arrived_late"
            )
        elif etype == "supplier_defaulted":
            event_names.append("supplier_defaulted")
        elif etype == "demand_shock":
            event_names.append("demand_shock")
        elif etype == "bankruptcy":
            event_names.append("bankruptcy")
    return event_names or ["quiet_day"]


AFFECTIVE_MAPPING: Dict[str, Dict[str, Any]] = {
    "stock_critical_low":     {"valence": -0.7, "arousal": 0.8, "tags": ["procurement", "risk"]},
    "order_arrived_on_time":  {"valence": 0.4,  "arousal": 0.2, "tags": ["procurement", "trust"]},
    "order_arrived_late":     {"valence": -0.3, "arousal": 0.4, "tags": ["procurement", "risk"]},
    "supplier_defaulted":     {"valence": -0.6, "arousal": 0.7, "tags": ["procurement", "risk"]},
    "demand_shock":           {"valence": -0.2, "arousal": 0.6, "tags": ["procurement", "novelty"]},
    "bankruptcy":             {"valence": -0.95, "arousal": 0.95, "tags": ["finance", "critical"]},
    "quiet_day":              {"valence": 0.05, "arousal": 0.1, "tags": ["neutral"]},
    "deal_closed_favorable":  {"valence": 0.7,  "arousal": 0.5, "tags": ["procurement", "success"]},
    "budget_low":             {"valence": -0.5, "arousal": 0.6, "tags": ["finance", "risk"]},
}

NEUTRAL_MAPPING_ENTRY: Dict[str, Any] = {"valence": 0.0, "arousal": 0.3, "tags": []}

# Utilization above which the agent is told the budget is under pressure.
BUDGET_HIGH_UTILIZATION = 0.80
BUDGET_CRITICAL_UTILIZATION = 0.95


class SandboxEncoder:
    """Convert ProcurementWorld observations into agent context_events.

    Three kinds of context reach the agent every day:

    1. Event context: what happened yesterday (stockout, delivery, default).
    2. Situational context: the current stock/budget slice — the agent must
       decide for itself whether to act rather than receive an explicit order.
    3. Opportunity context: budget pressure flags for products needing
       attention.
    """

    def encode_daily_context(
        self,
        world: Any,
        tick_result: dict,
        supplier_obs: Optional[Mapping[str, Any]] = None,
        price_references: Optional[Mapping[str, Any]] = None,
        *,
        price_perception: bool = True,
        price_bucket_z: float = DEFAULT_PRICE_BUCKET_Z,
    ) -> List[str]:
        tokens: List[str] = []

        # 1. Event tokens.
        for event_name in classify_world_events(tick_result):
            tokens.extend(self._event_to_tokens(event_name))

        # 2. Situational tokens — SKUs that need a replenishment now. The
        # agent is not given a full state dump, in the same way a real employee
        # reads an alert dashboard instead of the whole database.
        stock = world.observe_stock_levels()
        show_price = bool(price_perception) and supplier_obs is not None
        for pid, info in stock.items():
            below = bool(info.get("below_reorder_point"))
            if "below_replenishment_point" in info:
                below = below or bool(info.get("below_replenishment_point"))
            if below:
                tokens.append(f"product:{pid}")
                tokens.append("status:below_reorder_point")
                # One coarse band. Quotes come from the observation already
                # built for this day; omitting it keeps the previous tokens.
                if show_price:
                    tokens.append(
                        price_context_token(
                            pid,
                            supplier_obs,
                            lookup_price_reference(price_references, pid),
                            price_bucket_z,
                        )
                    )

        # 3. Budget context — most severe band wins.
        budget = world.observe_budget_status()
        utilization = safe_float(budget.get("utilization_ratio"), 0.0)
        if utilization > BUDGET_CRITICAL_UTILIZATION:
            tokens.append("budget:critical")
        elif utilization > BUDGET_HIGH_UTILIZATION:
            tokens.append("budget:high_utilization")

        return tokens or ["quiet_day"]

    def encode_daily_affect(self, tick_result: dict) -> Dict[str, float]:
        """Aggregate the day's events into scalar affective descriptors.

        Diagnostic since v2.0: the training loop no longer feeds reward or
        intensity into ``agent.step(...)``. The agent decides from context
        tokens alone, and the affective consequence of a concrete order is
        applied separately from the ``place_order`` result. Consolidation
        still happens only during sleep.
        """
        event_names = classify_world_events(tick_result)
        valences = []
        arousals = []
        for name in event_names:
            entry = AFFECTIVE_MAPPING.get(name, NEUTRAL_MAPPING_ENTRY)
            valences.append(safe_float(entry.get("valence"), 0.0))
            arousals.append(safe_float(entry.get("arousal"), 0.3))

        mean_valence = sum(valences) / len(valences) if valences else 0.0
        max_arousal = max(arousals) if arousals else 0.3
        return {
            "valence": clamp(mean_valence, -1.0, 1.0),
            "arousal": clamp(max_arousal, 0.0, 1.0),
            "reward": clamp(mean_valence, -1.0, 1.0),
            "intensity": clamp(0.5 + max_arousal, 0.0, 2.0),
            "novelty": clamp(max_arousal if "demand_shock" in event_names else 0.0, 0.0, 1.0),
        }

    def _event_to_tokens(self, event_name: str) -> List[str]:
        entry = AFFECTIVE_MAPPING.get(event_name, {})
        return mapped_event_tokens(event_name, entry)

    def encode_seed_episode(self, event_name: str) -> Dict[str, Any]:
        """Build one seed episode for pre-loading the hippocampus.

        Analogous to HippocampusSeeder from the Warriner demo, but seeding
        "professional intuition" about business events instead of words.
        """
        entry = AFFECTIVE_MAPPING.get(event_name, NEUTRAL_MAPPING_ENTRY)
        return {
            "event_name": event_name,
            "tokens": self._event_to_tokens(event_name),
            "v": safe_float(entry.get("valence"), 0.0),
            "a": safe_float(entry.get("arousal"), 0.3),
        }


__all__ = [
    "SandboxEncoder",
    "classify_world_events",
    "AFFECTIVE_MAPPING",
    "BUDGET_CRITICAL_UTILIZATION",
    "BUDGET_HIGH_UTILIZATION",
]
