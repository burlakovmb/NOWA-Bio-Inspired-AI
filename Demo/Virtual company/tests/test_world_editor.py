"""Tests for world snapshot / per-quarter overrides."""

from nowa_sandbox.procurement_world import ProcurementWorldConfig
from nowa_sandbox.world_editor import (
    apply_world_overrides,
    build_world_for_quarter,
    snapshot_world,
)


def test_build_world_for_quarter_is_deterministic():
    cfg = ProcurementWorldConfig(
        n_products=3, n_suppliers=2, days_per_quarter=10, seed=42
    )
    a = build_world_for_quarter(cfg, 3)
    b = build_world_for_quarter(cfg, 3)
    assert snapshot_world(a)["products"][0]["base_demand_per_day"] == (
        snapshot_world(b)["products"][0]["base_demand_per_day"]
    )
    assert a.config.seed == 42003  # 42 * 1000 + 3


def test_apply_overrides_changes_price_and_budget():
    cfg = ProcurementWorldConfig(
        n_products=2, n_suppliers=2, days_per_quarter=5, seed=7
    )
    world = build_world_for_quarter(cfg, 1)
    sid = next(iter(world.suppliers))
    apply_world_overrides(
        world,
        {
            "budget": 12345.0,
            "suppliers": [
                {
                    "supplier_id": sid,
                    "base_price_multiplier": 0.5,
                    "reliability": 0.99,
                }
            ],
        },
    )
    assert world.budget == 12345.0
    assert abs(world.suppliers[sid].base_price_multiplier - 0.5) < 1e-9


def test_snapshot_includes_offers_for_curriculum_world():
    from nowa_sandbox.world_curriculum import WorldCurriculum

    cur = WorldCurriculum.from_template(n_quarters=1)
    world = cur.build_world(1, days_per_quarter=5, seed=3)
    snap = snapshot_world(world)
    assert "offers" in snap
    assert len(snap["offers"]) == 1
    assert snap["offers"][0]["product_id"] == "product_001"
