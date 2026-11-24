"""World entity snapshots and curriculum quarter helpers for the lab GUI."""

from __future__ import annotations

from dataclasses import asdict, replace
from typing import Any, Dict, List, Mapping, Optional, Sequence

from nowa_sandbox.procurement_world import (
    ProcurementWorld,
    ProcurementWorldConfig,
    SupplierOffer,
    VirtualProduct,
    VirtualSupplier,
    offer_key,
    quarter_world_seed,
)
from nowa_sandbox.world_curriculum import empty_quarter


PRODUCT_EDIT_FIELDS = (
    "base_demand_per_day",
    "demand_volatility",
    "holding_cost_per_unit",
    "stockout_penalty_per_unit",
    "current_stock",
    "reorder_point",
)

SUPPLIER_EDIT_FIELDS = (
    "reputation",
    "is_defaulted",
)

OFFER_EDIT_FIELDS = (
    "unit_price",
    "lead_time_days",
    "reliability",
    "price_volatility",
)

# Legacy fields kept for older override JSON / tests.
LEGACY_SUPPLIER_EDIT_FIELDS = (
    "reliability",
    "base_price_multiplier",
    "price_volatility",
    "lead_time_days",
    "reputation",
    "is_defaulted",
)


def snapshot_world(world: ProcurementWorld) -> Dict[str, Any]:
    """Serialize products / suppliers / offers / budget for UI and result JSON."""
    return {
        "seed": getattr(world.config, "seed", None),
        "day": int(world.day),
        "budget": float(world.budget),
        "initial_budget": float(world.initial_budget),
        "bankrupt": bool(world.bankrupt),
        "products": [asdict(p) for p in world.products.values()],
        "suppliers": [asdict(s) for s in world.suppliers.values()],
        "offers": [asdict(o) for o in world.offers.values()],
    }


def build_world_for_quarter(
    base_config: ProcurementWorldConfig,
    quarter_index: int,
    *,
    overrides: Optional[Mapping[str, Any]] = None,
) -> ProcurementWorld:
    """Deterministic world for quarter Q, then apply overrides.

    RNG seed is ``quarter_world_seed`` (``base * 1000 + quarter``, or the
    quarter index when the base seed is unset). An overrides payload that
    already carries products, suppliers and offers is built from that spec;
    the seed only drives shocks.
    """
    if overrides and (
        overrides.get("offers") is not None
        or (
            overrides.get("products")
            and overrides.get("suppliers")
            and "offers" in overrides
        )
    ):
        seed = quarter_world_seed(base_config.seed, quarter_index)
        return ProcurementWorld.from_quarter_spec(
            overrides,
            days_per_quarter=base_config.days_per_quarter,
            seed=seed,
            persistent_suppliers=base_config.persistent_suppliers,
            demand_shock_probability=base_config.demand_shock_probability,
            supplier_default_probability=base_config.supplier_default_probability,
        )

    seed = quarter_world_seed(base_config.seed, quarter_index)
    cfg = replace(base_config, seed=seed)
    world = ProcurementWorld(cfg)
    if overrides:
        apply_world_overrides(world, overrides)
    return world


def apply_world_overrides(
    world: ProcurementWorld, overrides: Mapping[str, Any]
) -> None:
    """Patch live world entities from a GUI / JSON override payload.

    When ``offers`` is present, rebuild offer map (and optionally replace
    products/suppliers wholesale if full rows are provided).
    """
    if "budget" in overrides and overrides["budget"] is not None:
        world.budget = float(overrides["budget"])
    if "initial_budget" in overrides and overrides["initial_budget"] is not None:
        world.initial_budget = float(overrides["initial_budget"])

    for row in overrides.get("products") or []:
        if not isinstance(row, Mapping):
            continue
        pid = str(row.get("product_id") or "")
        product = world.products.get(pid)
        if product is None:
            # Allow adding products in curriculum-style payloads.
            if not pid:
                continue
            world.products[pid] = VirtualProduct(
                product_id=pid,
                base_demand_per_day=float(row.get("base_demand_per_day", 10.0)),
                demand_volatility=float(row.get("demand_volatility", 0.15)),
                holding_cost_per_unit=float(row.get("holding_cost_per_unit", 1.0)),
                stockout_penalty_per_unit=float(
                    row.get("stockout_penalty_per_unit", 10.0)
                ),
                current_stock=float(row.get("current_stock", 100.0)),
                reorder_point=float(row.get("reorder_point", 50.0)),
            )
            product = world.products[pid]
        for key in PRODUCT_EDIT_FIELDS:
            if key not in row or row[key] is None:
                continue
            setattr(product, key, float(row[key]))

    for row in overrides.get("suppliers") or []:
        if not isinstance(row, Mapping):
            continue
        sid = str(row.get("supplier_id") or "")
        supplier = world.suppliers.get(sid)
        if supplier is None:
            if not sid:
                continue
            world.suppliers[sid] = VirtualSupplier(
                supplier_id=sid,
                reliability=float(row.get("reliability", 0.9)),
                base_price_multiplier=float(row.get("base_price_multiplier", 1.0)),
                price_volatility=float(row.get("price_volatility", 0.05)),
                lead_time_days=int(row.get("lead_time_days", 5)),
                reputation=float(row.get("reputation", 0.5)),
                is_defaulted=bool(row.get("is_defaulted", False)),
            )
            supplier = world.suppliers[sid]
        for key in LEGACY_SUPPLIER_EDIT_FIELDS:
            if key not in row or row[key] is None:
                continue
            if key == "lead_time_days":
                setattr(supplier, key, int(row[key]))
            elif key == "is_defaulted":
                setattr(supplier, key, bool(row[key]))
            else:
                setattr(supplier, key, float(row[key]))

    if "offers" in overrides:
        world.offers.clear()
        for row in overrides.get("offers") or []:
            if not isinstance(row, Mapping):
                continue
            pid = str(row.get("product_id") or "").strip()
            sid = str(row.get("supplier_id") or "").strip()
            if not pid or not sid:
                continue
            if pid not in world.products or sid not in world.suppliers:
                continue
            offer = SupplierOffer(
                product_id=pid,
                supplier_id=sid,
                unit_price=float(row.get("unit_price", 1.0)),
                lead_time_days=int(row.get("lead_time_days", 5)),
                reliability=float(row.get("reliability", 0.9)),
                price_volatility=float(row.get("price_volatility", 0.05)),
            )
            world.offers[offer_key(pid, sid)] = offer


def overrides_from_tables(
    products: Sequence[Mapping[str, Any]],
    suppliers: Sequence[Mapping[str, Any]],
    *,
    budget: Optional[float] = None,
    offers: Optional[Sequence[Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Build a quarter / overrides payload from editable table rows."""
    payload: Dict[str, Any] = {
        "products": [dict(r) for r in products],
        "suppliers": [dict(r) for r in suppliers],
        "offers": [dict(r) for r in (offers or [])],
    }
    if budget is not None:
        payload["budget"] = float(budget)
    return payload


def empty_override_store() -> Dict[int, Dict[str, Any]]:
    return {}


__all__ = [
    "PRODUCT_EDIT_FIELDS",
    "SUPPLIER_EDIT_FIELDS",
    "OFFER_EDIT_FIELDS",
    "LEGACY_SUPPLIER_EDIT_FIELDS",
    "apply_world_overrides",
    "build_world_for_quarter",
    "empty_override_store",
    "overrides_from_tables",
    "snapshot_world",
]
