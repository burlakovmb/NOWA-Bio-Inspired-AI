"""Delayed consequences of a buyer's own decisions, read from the ERP.

Approval feedback teaches only while a person reviews orders. Once the buyer
works alone, the world is the teacher, but its answer comes days later:

* an order the buyer placed on its own is rewarded when the delivery lifts
  the position back above its reorder point (``order_paid_off``), less if the
  shelf ran empty before it arrived (``order_arrived_late``);
* a shelf that runs empty with nothing inbound while there was money and the
  buyer had waited on that deficit is filed as "here, order"
  (``missed_stockout``) under the situation it waited in.

Money is not judged here: the role's ``business_limits`` keep orders without
budget from reaching the ERP at all (see ``mcp_body/business_limits.py``).

The runtime calls ``observe`` after every decision and files the returned
lessons; orders a person approved are left to the person's verdict.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

ORDER_TOOL = "mcp__drivemcp__create_purchase_order"
SYSTEM_DECIDER_PREFIX = "system:"

ORDER_PAID_OFF_REWARD = 0.6
ORDER_LATE_REWARD = 0.3
MISSED_STOCKOUT_REWARD = 0.8
DEFAULT_HORIZON = timedelta(days=14)

Lesson = Tuple[List[str], str, float, str]


class ProcurementOutcomeJudge:
    def __init__(self, order_tool: str = ORDER_TOOL, horizon: timedelta = DEFAULT_HORIZON):
        self.order_tool = order_tool
        self.horizon = horizon
        self.open_orders: List[Dict[str, Any]] = []
        self.waited_in_deficit: Dict[str, List[str]] = {}
        self.attributed_stockouts: set = set()

    def observe(self, observations: Dict[str, Any], result: Dict[str, Any], now: datetime) -> List[Lesson]:
        stock = _stock_map(observations)
        remaining = _budget_remaining(observations)
        can_buy = _can_buy(remaining, _cheapest_price(observations))
        context = [str(t) for t in (result.get("context_events") or [])]
        lessons: List[Lesson] = []

        record = result.get("record")
        if result.get("executed") and _is_unjudged(record) and _accepted(record):
            params = getattr(getattr(record, "proposed_action", None), "tool_params", None) or {}
            sku = str(params.get("sku") or params.get("product_id") or "")
            if sku:
                self.open_orders.append({
                    "sku": sku,
                    "context": context,
                    "action": str(result.get("tool_id") or self.order_tool),
                    "placed_at": now,
                    "ran_out": False,
                })
                self.waited_in_deficit.pop(sku, None)
        elif result.get("waited") and can_buy:
            for sku, info in stock.items():
                # The lesson belongs to the wait that could still have saved
                # the shelf, not to the tick that found it empty.
                qty = _as_float(info.get("quantity"))
                if _in_deficit(info) and (qty is None or qty > 0):
                    self.waited_in_deficit[sku] = context

        lessons.extend(self._settle_orders(stock, now))
        lessons.extend(self._missed_stockouts(stock, can_buy))
        return lessons

    def _settle_orders(self, stock: Dict[str, dict], now: datetime) -> List[Lesson]:
        lessons: List[Lesson] = []
        still_open = []
        for order in self.open_orders:
            info = stock.get(order["sku"])
            if info is None:
                still_open.append(order)
                continue
            qty = _as_float(info.get("quantity"))
            if qty is not None and qty <= 0:
                order["ran_out"] = True
            if not _below_point(info):
                if order["ran_out"]:
                    lessons.append((order["context"], order["action"], ORDER_LATE_REWARD, "order_arrived_late"))
                else:
                    lessons.append((order["context"], order["action"], ORDER_PAID_OFF_REWARD, "order_paid_off"))
            elif now - order["placed_at"] <= self.horizon:
                still_open.append(order)
        self.open_orders = still_open
        return lessons

    def _missed_stockouts(self, stock: Dict[str, dict], can_buy: bool) -> List[Lesson]:
        lessons: List[Lesson] = []
        ordered = {order["sku"] for order in self.open_orders}
        for sku, info in stock.items():
            qty = _as_float(info.get("quantity"))
            if qty is None or qty > 0:
                self.attributed_stockouts.discard(sku)
                continue
            projected = _as_float(info.get("projected_quantity"))
            if projected is not None and projected > 0:
                continue
            if sku in self.attributed_stockouts or sku in ordered:
                continue
            if not can_buy:
                continue
            context = self.waited_in_deficit.pop(sku, None)
            if context is None:
                continue
            self.attributed_stockouts.add(sku)
            lessons.append((context, self.order_tool, MISSED_STOCKOUT_REWARD, "missed_stockout"))
        return lessons


def _tool_results(observations: Dict[str, Any]) -> Dict[str, Any]:
    results = observations.get("tool_results") if isinstance(observations, dict) else None
    return results if isinstance(results, dict) else {}


def _stock_map(observations: Dict[str, Any]) -> Dict[str, dict]:
    for result in _tool_results(observations).values():
        if not isinstance(result, dict):
            continue
        for key in ("stock", "products", "stock_levels"):
            payload = result.get(key)
            if isinstance(payload, dict):
                return {str(k): v for k, v in payload.items() if isinstance(v, dict)}
    return {}


def _budget_remaining(observations: Dict[str, Any]) -> Optional[float]:
    for result in _tool_results(observations).values():
        if isinstance(result, dict) and "remaining" in result:
            return _as_float(result.get("remaining"))
    return None


def _cheapest_price(observations: Dict[str, Any]) -> Optional[float]:
    prices = []
    for result in _tool_results(observations).values():
        suppliers = result.get("suppliers") if isinstance(result, dict) else None
        if isinstance(suppliers, dict):
            for row in suppliers.values():
                price = _as_float(row.get("unit_price")) if isinstance(row, dict) else None
                if price is not None and price > 0:
                    prices.append(price)
    return min(prices) if prices else None


def _can_buy(remaining: Optional[float], cheapest: Optional[float]) -> bool:
    """Money for at least one unit; small change left on the budget is not money."""
    if remaining is None:
        return True
    return remaining >= cheapest if cheapest is not None else remaining > 0


def _below_point(info: dict) -> bool:
    if "below_reorder_point" in info:
        return bool(info.get("below_reorder_point"))
    qty = _as_float(info.get("quantity"))
    point = _as_float(info.get("reorder_point"))
    return qty is not None and point is not None and qty < point


def _in_deficit(info: dict) -> bool:
    """Below the point and nothing inbound covers it (what the ERP would list)."""
    if not _below_point(info):
        return False
    projected = _as_float(info.get("projected_quantity"))
    point = _as_float(info.get("reorder_point"))
    return projected is None or point is None or projected < point


def _is_unjudged(record: Any) -> bool:
    return str(getattr(record, "decided_by", "") or "").startswith(SYSTEM_DECIDER_PREFIX)


def _accepted(record: Any) -> bool:
    outcome = getattr(record, "execution_result", None)
    if not isinstance(outcome, dict):
        return False
    return str(outcome.get("status") or "").lower() == "accepted" or "document_number" in outcome


def _as_float(value: Any) -> Optional[float]:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
