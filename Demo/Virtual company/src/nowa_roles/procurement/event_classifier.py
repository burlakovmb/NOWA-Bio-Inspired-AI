"""Map procurement MCP READ results onto named business events."""

from __future__ import annotations

from typing import Any, Dict, List


def classify_procurement_events(tool_id: str, result: dict) -> list:
    """Role-specific: raw MCP payload → named events from an affective mapping."""
    if not isinstance(result, dict):
        return []

    events: List[str] = []
    tool_tail = str(tool_id).split("__")[-1]

    if "stock" in tool_tail or "stock_levels" in tool_tail or "products" in result or "stock" in result:
        events.extend(_stock_events(result))
    if "supplier" in tool_tail or "suppliers" in result:
        events.extend(_supplier_events(result))
    if "budget" in tool_tail or "remaining" in result or "utilization_ratio" in result:
        events.extend(_budget_events(result))

    # A READ that answered "ok" is not a deal: only a WRITE outcome (an
    # accepted document) closes one.
    status = str(result.get("status") or "").strip().lower()
    is_write_outcome = status == "accepted" or "document_number" in result
    if status in ("urgent", "critical"):
        events.append("stock_critical_low")
    elif is_write_outcome and status in ("accepted", "success", "ok"):
        events.append("deal_closed_favorable")
    elif is_write_outcome and status in ("rejected", "failed", "error"):
        events.append("supplier_defaulted")
    elif status == "timeout":
        events.append("order_arrived_late")

    # No named event, no token: a bare tool name ("get_budget") would sit in
    # every context and let a lesson from a calm day answer a stockout.
    return events


def _as_product_map(result: Dict[str, Any]) -> Dict[str, dict]:
    for key in ("stock", "products", "stock_levels", "items"):
        payload = result.get(key)
        if isinstance(payload, dict):
            return {
                str(pid): info
                for pid, info in payload.items()
                if isinstance(info, dict)
            }
    if result and all(isinstance(v, dict) for v in result.values() if v is not None):
        skip = {"status", "reason", "tool_id"}
        return {
            str(pid): info
            for pid, info in result.items()
            if pid not in skip and isinstance(info, dict)
        }
    return {}


def _as_float(value: Any) -> Any:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _stock_events(result: Dict[str, Any]) -> List[str]:
    """One stock event per read, the most urgent one.

    ``stock_critical_low`` — a position is below its reorder point and nothing
    already inbound covers it; ``stock_low_covered`` — below the point, but
    the projected quantity (on hand + inbound) is back above it, so an order
    is already on its way; ``stock_ok`` — every position is above its point.
    """
    products = _as_product_map(result)
    if not products:
        return []
    covered = False
    for info in products.values():
        below = bool(info.get("below_reorder_point"))
        if "below_replenishment_point" in info:
            below = below or bool(info.get("below_replenishment_point"))
        qty_f = _as_float(info.get("quantity", info.get("projected_quantity")))
        if not (below or (qty_f is not None and qty_f <= 0)):
            continue
        projected = _as_float(info.get("projected_quantity"))
        reorder_point = _as_float(info.get("reorder_point"))
        if projected is not None and reorder_point is not None and projected > reorder_point:
            covered = True
            continue
        return ["stock_critical_low"]
    return ["stock_low_covered"] if covered else ["stock_ok"]


def _supplier_events(result: Dict[str, Any]) -> List[str]:
    suppliers = result.get("suppliers", result)
    if not isinstance(suppliers, dict):
        return []
    for info in suppliers.values():
        if not isinstance(info, dict):
            continue
        if info.get("is_defaulted") is True or str(info.get("status") or "").lower() == "defaulted":
            return ["supplier_defaulted"]
    return []


def _budget_events(result: Dict[str, Any]) -> List[str]:
    try:
        utilization = float(result.get("utilization_ratio", 0.0) or 0.0)
    except (TypeError, ValueError):
        utilization = 0.0
    remaining = result.get("remaining")
    try:
        remaining_f = float(remaining) if remaining is not None else None
    except (TypeError, ValueError):
        remaining_f = None
    if remaining_f is not None and remaining_f <= 0:
        return ["budget_exceeded"]
    if utilization > 0.9:
        return ["budget_exceeded"]
    return []
