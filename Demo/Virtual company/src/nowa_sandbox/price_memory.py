"""Per-SKU price reference built from what the agent has already seen.

The reference is an exponential moving average and a moving spread of visible
supplier quotes and prices the agent actually paid. It is read on the decision
day and updated only afterwards, so today's book cannot leak into today's
token or into today's felt cost.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Mapping, Optional, Sequence, Tuple

from ._common import is_finite_number


PRICE_SCALE_EPS = 1e-6
ACCEPTED_BASE_REWARD = 0.4
DEFAULT_PRICE_MEMORY_ALPHA = 0.1
DEFAULT_PRICE_BUCKET_Z = 0.5
DEFAULT_PRICE_REWARD_GAIN = 0.3

PriceReference = Tuple[float, float]


@dataclass
class _SkuPrice:
    ema: float
    spread: float


class PriceMemory:
    """EMA level and EMA absolute deviation, one pair per product id."""

    def __init__(self, alpha: float = DEFAULT_PRICE_MEMORY_ALPHA):
        alpha_value = float(alpha)
        if not 0.0 < alpha_value <= 1.0:
            raise ValueError(
                f"price memory alpha must be in (0, 1], got {alpha!r}"
            )
        self.alpha = alpha_value
        self._skus: Dict[str, _SkuPrice] = {}

    def reference(self, product_id: object) -> Optional[PriceReference]:
        state = self._skus.get(str(product_id))
        if state is None:
            return None
        return (state.ema, state.spread)

    def snapshot(self) -> Dict[str, PriceReference]:
        """Copy of the reference as it stands before today's update."""
        return {
            sku: (state.ema, state.spread) for sku, state in self._skus.items()
        }

    def update(self, product_id: object, prices: Sequence[float]) -> None:
        """Fold prices into the reference. First sample sets the level only."""
        state = self._skus.get(str(product_id))
        for price in prices:
            if not is_finite_number(price):
                continue
            value = float(price)
            if state is None:
                state = _SkuPrice(ema=value, spread=0.0)
                self._skus[str(product_id)] = state
                continue
            # Deviation from the reference that was current before this sample.
            delta = value - state.ema
            state.ema = (1.0 - self.alpha) * state.ema + self.alpha * value
            state.spread = (1.0 - self.alpha) * state.spread + self.alpha * abs(delta)

    def observe_day(
        self,
        product_ids: Iterable[object],
        supplier_obs: Optional[Mapping],
        paid: Optional[Tuple[object, float]] = None,
    ) -> None:
        """Record one day's visible quotes, then a paid unit price if any."""
        paid_pid = None
        paid_price = None
        if paid is not None and is_finite_number(paid[1]):
            paid_pid = str(paid[0])
            paid_price = float(paid[1])
        seen = set()
        for product_id in product_ids:
            key = str(product_id)
            seen.add(key)
            prices = list(visible_unit_prices(supplier_obs, product_id))
            if paid_pid == key and paid_price is not None:
                prices.append(paid_price)
            if prices:
                self.update(key, prices)
        if paid_pid is not None and paid_pid not in seen and paid_price is not None:
            self.update(paid_pid, [paid_price])

    def to_dict(self) -> Dict[str, object]:
        return {
            "alpha": self.alpha,
            "skus": {
                sku: {"ema": state.ema, "spread": state.spread}
                for sku, state in self._skus.items()
            },
        }

    @classmethod
    def from_dict(
        cls,
        data: object,
        *,
        alpha: Optional[float] = None,
    ) -> "PriceMemory":
        """Restore a reference. A missing or empty document stays empty."""
        stored_alpha = None
        skus: object = None
        if isinstance(data, Mapping):
            stored_alpha = data.get("alpha")
            skus = data.get("skus")
        if alpha is None:
            alpha = (
                float(stored_alpha)
                if is_finite_number(stored_alpha)
                else DEFAULT_PRICE_MEMORY_ALPHA
            )
        memory = cls(alpha=alpha)
        if not isinstance(skus, Mapping):
            return memory
        for sku, row in skus.items():
            if not isinstance(row, Mapping) or "ema" not in row:
                continue
            ema = row.get("ema")
            spread = row.get("spread", 0.0)
            if not is_finite_number(ema) or not is_finite_number(spread):
                continue
            memory._skus[str(sku)] = _SkuPrice(
                ema=float(ema),
                spread=max(0.0, float(spread)),
            )
        return memory


def visible_unit_prices(
    supplier_obs: Optional[Mapping],
    product_id: object,
) -> list[float]:
    """Unit prices of status-ok quotes for one SKU, in observation order."""
    if not isinstance(supplier_obs, Mapping):
        return []
    pid_text = str(product_id)
    prices: list[float] = []
    for info in supplier_obs.values():
        if not isinstance(info, Mapping):
            continue
        offers = info.get("offers")
        if not isinstance(offers, Mapping):
            continue
        quote = offers.get(product_id)
        if quote is None:
            quote = offers.get(pid_text)
        if not isinstance(quote, Mapping):
            continue
        if quote.get("status") != "ok":
            continue
        unit_price = quote.get("unit_price")
        if not is_finite_number(unit_price):
            continue
        prices.append(float(unit_price))
    return prices


def lookup_price_reference(
    references: Optional[Mapping],
    product_id: object,
) -> Optional[PriceReference]:
    if not isinstance(references, Mapping):
        return None
    raw = references.get(product_id)
    if raw is None:
        raw = references.get(str(product_id))
    if not isinstance(raw, (tuple, list)) or len(raw) < 2:
        return None
    ema, spread = raw[0], raw[1]
    if not is_finite_number(ema) or not is_finite_number(spread):
        return None
    return (float(ema), float(spread))


def classify_price_band(
    prices: Sequence[float],
    reference: Optional[PriceReference],
    z_threshold: float,
    eps: float = PRICE_SCALE_EPS,
) -> str:
    """cheap / average / expensive. No reference or no quotes → average."""
    if not prices or reference is None:
        return "average"
    mean_today = sum(prices) / float(len(prices))
    ema, spread = reference
    z_value = (mean_today - float(ema)) / max(float(spread), eps)
    threshold = float(z_threshold)
    if z_value < -threshold:
        return "cheap"
    if z_value > threshold:
        return "expensive"
    return "average"


def price_context_token(
    product_id: object,
    supplier_obs: Optional[Mapping],
    reference: Optional[PriceReference],
    z_threshold: float,
) -> str:
    band = classify_price_band(
        visible_unit_prices(supplier_obs, product_id),
        reference,
        z_threshold,
    )
    return f"price:{product_id}:{band}"


def perceived_product_ids(context_events: Optional[Iterable[str]]) -> list[str]:
    """Product ids that already entered context as ``product:{pid}``."""
    found: list[str] = []
    seen = set()
    for token in context_events or []:
        if not isinstance(token, str) or not token.startswith("product:"):
            continue
        product_id = token[len("product:"):]
        if not product_id or product_id in seen:
            continue
        seen.add(product_id)
        found.append(product_id)
    return found


def felt_accepted_reward(
    unit_price: object,
    reference: Optional[PriceReference],
    *,
    gain: float,
    enabled: bool,
    eps: float = PRICE_SCALE_EPS,
) -> float:
    """Accepted-order reward. Disabled or unknown reference stays at 0.4.

    ``0.4 + gain * clip(-(unit_price - ema) / max(spread, eps), -1, 1)``.
    """
    if (
        not enabled
        or reference is None
        or not is_finite_number(unit_price)
    ):
        return ACCEPTED_BASE_REWARD
    ema, spread = reference
    if not is_finite_number(ema):
        return ACCEPTED_BASE_REWARD
    scale = max(float(spread) if is_finite_number(spread) else 0.0, eps)
    z_paid = (float(unit_price) - float(ema)) / scale
    clipped = max(-1.0, min(1.0, -z_paid))
    return ACCEPTED_BASE_REWARD + float(gain) * clipped


__all__ = [
    "ACCEPTED_BASE_REWARD",
    "DEFAULT_PRICE_BUCKET_Z",
    "DEFAULT_PRICE_MEMORY_ALPHA",
    "DEFAULT_PRICE_REWARD_GAIN",
    "PRICE_SCALE_EPS",
    "PriceMemory",
    "classify_price_band",
    "felt_accepted_reward",
    "lookup_price_reference",
    "perceived_product_ids",
    "price_context_token",
    "visible_unit_prices",
]
