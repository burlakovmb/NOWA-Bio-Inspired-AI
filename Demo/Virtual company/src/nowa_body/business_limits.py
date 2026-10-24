"""Business limits a role declares: rules of the body, not of judgement.

Architectural invariants (``hard_constraints``) cannot be configured away.
These can: a role names them in ``config.yaml`` under ``business_limits``.
A limit guards some WRITE tools with an amount still available in the world
(read from a world-state path) and, when it can price the call, the call's
cost (a quantity parameter times a unit price read from the world):

* the call fits: it goes on unchanged;
* it does not fit and the limit says ``on_exceed: clip``: the quantity is
  shrunk to what the available amount allows;
* nothing fits, or ``on_exceed: block``: the call never reaches the approval
  gate. The first block of a shortage episode files "here, wait" (if the
  limit gives a lesson reward) and notifies the host; later blocks of the same
  episode are silent. The episode ends when a call fits again or the
  available amount grows.

An unknown amount blocks the call: a limit that cannot be read is not passed.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

BLOCK = "block"
CLIP = "clip"

_PLACEHOLDER = re.compile(r"\{([^{}]+)\}")


@dataclass(frozen=True)
class BusinessLimit:
    name: str
    tools: Tuple[str, ...]
    available_path: str
    qty_param: str = ""
    unit_price_path: str = ""
    on_exceed: str = BLOCK
    min_qty: float = 1.0
    lesson_reward: float = 0.0
    consequence: str = "limit_protected"

    def guards(self, tool_id: str) -> bool:
        return not self.tools or str(tool_id) in self.tools


@dataclass
class LimitCheck:
    name: str
    verdict: str  # "ok" | "clipped" | "blocked"
    params: Dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    available: Optional[float] = None
    cost: Optional[float] = None

    @property
    def blocked(self) -> bool:
        return self.verdict == "blocked"


def parse_business_limits(raw: Any) -> List[BusinessLimit]:
    """Read the ``business_limits`` list of a role config; skip malformed rows."""
    limits: List[BusinessLimit] = []
    for index, row in enumerate(raw if isinstance(raw, list) else []):
        if not isinstance(row, dict):
            continue
        available = str(row.get("available") or row.get("available_path") or "").strip()
        if not available:
            continue
        tools = row.get("tools") or []
        if isinstance(tools, str):
            tools = [tools]
        cost = row.get("cost") if isinstance(row.get("cost"), dict) else {}
        on_exceed = str(row.get("on_exceed") or BLOCK).strip().lower()
        limits.append(BusinessLimit(
            name=str(row.get("name") or f"limit_{index}"),
            tools=tuple(str(t) for t in tools),
            available_path=available,
            qty_param=str(cost.get("qty_param") or "").strip(),
            unit_price_path=str(cost.get("unit_price") or "").strip(),
            on_exceed=on_exceed if on_exceed in (BLOCK, CLIP) else BLOCK,
            min_qty=_as_float(row.get("min_qty"), 1.0),
            lesson_reward=_as_float(row.get("lesson_reward"), 0.0),
            consequence=str(row.get("consequence") or "limit_protected"),
        ))
    return limits


def available_amount(limit: BusinessLimit, world_state: Any) -> Optional[float]:
    """What the world says is still available under ``limit``; None if unread."""
    return _as_float(_resolve(world_state, limit.available_path), None)


def check_limit(limit: BusinessLimit, params: Dict[str, Any], world_state: Any) -> LimitCheck:
    """Fit one bound call into one limit. ``params`` is never mutated."""
    params = dict(params or {})
    available = available_amount(limit, world_state)
    if available is None:
        return LimitCheck(limit.name, "blocked", params, reason="limit_unknown")
    if available <= 0:
        return LimitCheck(limit.name, "blocked", params, reason="nothing_left", available=available)

    qty = _as_float(params.get(limit.qty_param), None) if limit.qty_param else None
    price_path = _fill(limit.unit_price_path, params) if limit.unit_price_path else ""
    price = _as_float(_resolve(world_state, price_path), None) if price_path else None
    if qty is None or price is None or price <= 0:
        # Cannot price the call: only "something is left" can be checked.
        return LimitCheck(limit.name, "ok", params, available=available)

    cost = qty * price
    if cost <= available:
        return LimitCheck(limit.name, "ok", params, available=available, cost=cost)
    if limit.on_exceed == CLIP:
        fitted = math.floor(available / price)
        if fitted >= limit.min_qty:
            clipped = dict(params)
            clipped[limit.qty_param] = fitted
            return LimitCheck(limit.name, "clipped", clipped, reason="clipped_to_available",
                              available=available, cost=fitted * price)
    return LimitCheck(limit.name, "blocked", params, reason="over_available",
                      available=available, cost=cost)


def apply_limits(
    limits: List[BusinessLimit], tool_id: str, params: Dict[str, Any], world_state: Any
) -> Tuple[Dict[str, Any], List[LimitCheck]]:
    """Run every limit that guards ``tool_id``; stop at the first block."""
    checks: List[LimitCheck] = []
    current = dict(params or {})
    for limit in limits or []:
        if not limit.guards(tool_id):
            continue
        result = check_limit(limit, current, world_state)
        checks.append(result)
        if result.blocked:
            break
        current = result.params
    return current, checks


def _fill(template: str, params: Dict[str, Any]) -> str:
    missing = []

    def sub(match: "re.Match[str]") -> str:
        value = params.get(match.group(1))
        if value is None:
            missing.append(match.group(1))
            return ""
        return str(value)

    filled = _PLACEHOLDER.sub(sub, template)
    return "" if missing else filled


def _resolve(world_state: Any, path: str) -> Any:
    if not path:
        return None
    resolve = getattr(world_state, "resolve_path", None)
    if not callable(resolve):
        return None
    try:
        return resolve(path)
    except Exception:
        return None


def _as_float(value: Any, default: Optional[float]) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default
