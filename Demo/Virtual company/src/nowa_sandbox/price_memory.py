"""Per-SKU price reference built from what the agent has already seen.

Thin binding of :class:`numeric_memory.NumericMemory` onto procurement:
the numeric field is ``unit_price``, tokens are ``price:{id}:{band}``,
and entity tokens are ``product:{id}``. Checkpoint documents still use
the ``skus`` key.
"""

from __future__ import annotations

from typing import Mapping, Optional, Sequence

from .numeric_memory import (
    ACCEPTED_BASE_REWARD,
    DEFAULT_BUCKET_Z,
    DEFAULT_MEMORY_ALPHA,
    DEFAULT_REWARD_GAIN,
    SCALE_EPS,
    LevelReference,
    NumericMemory,
    band_token,
    classify_band,
    collect_values,
    felt_reward,
    lookup_reference,
    perceived_entity_ids,
)


PRICE_SCALE_EPS = SCALE_EPS
DEFAULT_PRICE_MEMORY_ALPHA = DEFAULT_MEMORY_ALPHA
DEFAULT_PRICE_BUCKET_Z = DEFAULT_BUCKET_Z
DEFAULT_PRICE_REWARD_GAIN = DEFAULT_REWARD_GAIN

PriceReference = LevelReference


class PriceMemory(NumericMemory):
    """EMA level and EMA absolute deviation, one pair per product id."""

    def __init__(self, alpha: float = DEFAULT_PRICE_MEMORY_ALPHA):
        alpha_value = float(alpha)
        if not 0.0 < alpha_value <= 1.0:
            raise ValueError(
                f"price memory alpha must be in (0, 1], got {alpha!r}"
            )
        super().__init__(
            alpha=alpha_value,
            value_field="unit_price",
            token_prefix="price",
            entity_prefix="product",
            record_key="skus",
        )

    def reference(self, product_id: object) -> Optional[PriceReference]:
        return super().reference(product_id)

    def update(self, product_id: object, prices: Sequence[float]) -> None:
        super().update(product_id, prices)

    def observe_day(
        self,
        product_ids,
        supplier_obs,
        paid=None,
    ) -> None:
        super().observe_day(product_ids, supplier_obs, paid)


def visible_unit_prices(supplier_obs, product_id: object) -> list[float]:
    """Unit prices of status-ok quotes for one SKU, in observation order."""
    return collect_values(
        supplier_obs,
        product_id,
        value_field="unit_price",
    )


def lookup_price_reference(
    references: Optional[Mapping],
    product_id: object,
) -> Optional[PriceReference]:
    return lookup_reference(references, product_id)


def classify_price_band(
    prices: Sequence[float],
    reference: Optional[PriceReference],
    z_threshold: float,
    eps: float = PRICE_SCALE_EPS,
) -> str:
    """cheap / average / expensive. No reference or no quotes → average."""
    return classify_band(prices, reference, z_threshold, eps=eps)


def price_context_token(
    product_id: object,
    supplier_obs,
    reference: Optional[PriceReference],
    z_threshold: float,
) -> str:
    return band_token(
        product_id,
        supplier_obs,
        reference,
        z_threshold,
        token_prefix="price",
        value_field="unit_price",
    )


def perceived_product_ids(context_events) -> list[str]:
    """Product ids that already entered context as ``product:{pid}``."""
    return perceived_entity_ids(context_events, "product")


def felt_accepted_reward(
    unit_price: object,
    reference: Optional[PriceReference],
    *,
    gain: float,
    enabled: bool,
    eps: float = PRICE_SCALE_EPS,
) -> float:
    """Accepted-order reward. Disabled or unknown reference stays at 0.4."""
    return felt_reward(
        unit_price,
        reference,
        gain=gain,
        enabled=enabled,
        eps=eps,
    )


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
