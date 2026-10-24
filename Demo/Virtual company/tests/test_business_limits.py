"""Procurement role: the budget is a business limit of the body.

The limit mechanics (clip, block, shortage episodes, notices) are tested
domain-free in ``test_body_business_limits.py``. Here: the role declares
the budget so that an order never spends money that is not there.
"""

from __future__ import annotations

from pathlib import Path

from nowa_body.business_limits import apply_limits, parse_business_limits
from mcp_body.world_state import WorldState
from nowa_body.role_config import load_role_config

ORDER = "mcp__drivemcp__create_purchase_order"
BUDGET = "mcp__drivemcp__get_budget"
SUPPLIERS = "mcp__drivemcp__get_suppliers"
PROCUREMENT_CONFIG = str(
    Path(__file__).resolve().parents[1] / "src" / "nowa_roles" / "procurement" / "config.yaml"
)
ORDER_PARAMS = {"sku": "sku-a", "qty": 200, "supplier_id": "sup-1"}


def _budget():
    return parse_business_limits(load_role_config(PROCUREMENT_CONFIG).business_limits)


def _world(remaining):
    world = WorldState()
    world.update_from_read(BUDGET, {"status": "ok", "remaining": remaining})
    world.update_from_read(SUPPLIERS, {"status": "ok", "suppliers": {
        "sup-1": {"unit_price": 10.0}, "sup-2": {"unit_price": 8.5}}})
    return world


class TestProcurementBudget:

    def test_role_declares_the_budget(self):
        limits = _budget()
        assert [limit.name for limit in limits] == ["budget"]
        assert limits[0].tools == (ORDER,)
        assert limits[0].on_exceed == "clip"
        assert limits[0].consequence == "budget_protected"

    def test_order_is_shrunk_to_the_money_left_at_the_bound_suppliers_price(self):
        params, checks = apply_limits(_budget(), ORDER, ORDER_PARAMS, _world(1234.0))
        assert [c.verdict for c in checks] == ["clipped"] and params["qty"] == 123
        params, _checks = apply_limits(_budget(), ORDER, dict(ORDER_PARAMS, supplier_id="sup-2"), _world(1234.0))
        assert params["qty"] == 145

    def test_no_money_no_order(self):
        _params, checks = apply_limits(_budget(), ORDER, ORDER_PARAMS, _world(0.0))
        assert checks[0].blocked and checks[0].reason == "nothing_left"
