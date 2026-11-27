"""Numeric reference built from values the agent has already seen.

One exponential moving average and one moving spread per entity. The
reference is read on the decision step and updated only afterwards, so
today's book cannot leak into today's token or into today's felt outcome.

The value field, the token prefix and the entity prefix are parameters.
This module does not know which domain supplied them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Mapping, Optional, Sequence, Tuple

from ._common import is_finite_number


SCALE_EPS = 1e-6
ACCEPTED_BASE_REWARD = 0.4
DEFAULT_MEMORY_ALPHA = 0.1
DEFAULT_BUCKET_Z = 0.5
DEFAULT_REWARD_GAIN = 0.3

LevelReference = Tuple[float, float]


@dataclass
class _Level:
    ema: float
    spread: float


class NumericMemory:
    """EMA level and EMA absolute deviation, one pair per entity id."""

    def __init__(
        self,
        alpha: float = DEFAULT_MEMORY_ALPHA,
        *,
        value_field: str = "value",
        token_prefix: str = "level",
        entity_prefix: str = "entity",
        record_key: str = "levels",
        nested_field: str = "offers",
    ):
        alpha_value = float(alpha)
        if not 0.0 < alpha_value <= 1.0:
            raise ValueError(
                f"memory alpha must be in (0, 1], got {alpha!r}"
            )
        self.alpha = alpha_value
        self.value_field = str(value_field)
        self.token_prefix = str(token_prefix)
        self.entity_prefix = str(entity_prefix)
        self.record_key = str(record_key)
        self.nested_field = str(nested_field)
        self._levels: Dict[str, _Level] = {}

    def reference(self, entity_id: object) -> Optional[LevelReference]:
        state = self._levels.get(str(entity_id))
        if state is None:
            return None
        return (state.ema, state.spread)

    def snapshot(self) -> Dict[str, LevelReference]:
        """Copy of the reference as it stands before today's update."""
        return {
            key: (state.ema, state.spread)
            for key, state in self._levels.items()
        }

    def update(self, entity_id: object, values: Sequence[float]) -> None:
        """Fold values into the reference. The first sample sets the level only."""
        state = self._levels.get(str(entity_id))
        for raw in values:
            if not is_finite_number(raw):
                continue
            value = float(raw)
            if state is None:
                state = _Level(ema=value, spread=0.0)
                self._levels[str(entity_id)] = state
                continue
            delta = value - state.ema
            state.ema = (1.0 - self.alpha) * state.ema + self.alpha * value
            state.spread = (1.0 - self.alpha) * state.spread + self.alpha * abs(delta)

    def observe_day(
        self,
        entity_ids: Iterable[object],
        book: Optional[Mapping],
        paid: Optional[Tuple[object, float]] = None,
    ) -> None:
        """Record one step's visible values, then a paid value if any."""
        paid_id = None
        paid_value = None
        if paid is not None and is_finite_number(paid[1]):
            paid_id = str(paid[0])
            paid_value = float(paid[1])
        seen = set()
        for entity_id in entity_ids:
            key = str(entity_id)
            seen.add(key)
            values = list(self.visible_values(book, entity_id))
            if paid_id == key and paid_value is not None:
                values.append(paid_value)
            if values:
                self.update(key, values)
        if paid_id is not None and paid_id not in seen and paid_value is not None:
            self.update(paid_id, [paid_value])

    def visible_values(
        self,
        book: Optional[Mapping],
        entity_id: object,
    ) -> list[float]:
        return collect_values(
            book,
            entity_id,
            value_field=self.value_field,
            nested_field=self.nested_field,
        )

    def to_dict(self) -> Dict[str, object]:
        return {
            "alpha": self.alpha,
            self.record_key: {
                key: {"ema": state.ema, "spread": state.spread}
                for key, state in self._levels.items()
            },
        }

    @classmethod
    def from_dict(
        cls,
        data: object,
        *,
        alpha: Optional[float] = None,
    ) -> "NumericMemory":
        """Restore a reference. A missing or empty document stays empty."""
        stored_alpha = None
        rows: object = None
        memory = cls(alpha=DEFAULT_MEMORY_ALPHA if alpha is None else alpha)
        if isinstance(data, Mapping):
            stored_alpha = data.get("alpha")
            rows = data.get(memory.record_key)
        if alpha is None:
            alpha = (
                float(stored_alpha)
                if is_finite_number(stored_alpha)
                else DEFAULT_MEMORY_ALPHA
            )
            memory = cls(alpha=alpha)
        if not isinstance(rows, Mapping):
            return memory
        for key, row in rows.items():
            if not isinstance(row, Mapping) or "ema" not in row:
                continue
            ema = row.get("ema")
            spread = row.get("spread", 0.0)
            if not is_finite_number(ema) or not is_finite_number(spread):
                continue
            memory._levels[str(key)] = _Level(
                ema=float(ema),
                spread=max(0.0, float(spread)),
            )
        return memory


def collect_values(
    book: Optional[Mapping],
    entity_id: object,
    *,
    value_field: str,
    nested_field: str = "offers",
) -> list[float]:
    """Finite values of status-ok quotes for one entity, in observation order."""
    if not isinstance(book, Mapping):
        return []
    entity_text = str(entity_id)
    values: list[float] = []
    for info in book.values():
        if not isinstance(info, Mapping):
            continue
        nested = info.get(nested_field)
        if not isinstance(nested, Mapping):
            continue
        quote = nested.get(entity_id)
        if quote is None:
            quote = nested.get(entity_text)
        if not isinstance(quote, Mapping):
            continue
        if quote.get("status") != "ok":
            continue
        raw = quote.get(value_field)
        if not is_finite_number(raw):
            continue
        values.append(float(raw))
    return values


def lookup_reference(
    references: Optional[Mapping],
    entity_id: object,
) -> Optional[LevelReference]:
    if not isinstance(references, Mapping):
        return None
    raw = references.get(entity_id)
    if raw is None:
        raw = references.get(str(entity_id))
    if not isinstance(raw, (tuple, list)) or len(raw) < 2:
        return None
    ema, spread = raw[0], raw[1]
    if not is_finite_number(ema) or not is_finite_number(spread):
        return None
    return (float(ema), float(spread))


def classify_band(
    values: Sequence[float],
    reference: Optional[LevelReference],
    z_threshold: float,
    eps: float = SCALE_EPS,
) -> str:
    """cheap / average / expensive. No reference or no quotes means average."""
    if not values or reference is None:
        return "average"
    mean_today = sum(values) / float(len(values))
    ema, spread = reference
    z_value = (mean_today - float(ema)) / max(float(spread), eps)
    threshold = float(z_threshold)
    if z_value < -threshold:
        return "cheap"
    if z_value > threshold:
        return "expensive"
    return "average"


def band_token(
    entity_id: object,
    book: Optional[Mapping],
    reference: Optional[LevelReference],
    z_threshold: float,
    *,
    token_prefix: str,
    value_field: str,
    nested_field: str = "offers",
) -> str:
    band = classify_band(
        collect_values(
            book,
            entity_id,
            value_field=value_field,
            nested_field=nested_field,
        ),
        reference,
        z_threshold,
    )
    return f"{token_prefix}:{entity_id}:{band}"


def perceived_entity_ids(
    context_events: Optional[Iterable[str]],
    entity_prefix: str,
) -> list[str]:
    """Entity ids that already entered context as ``{prefix}:{id}``."""
    prefix = f"{entity_prefix}:"
    found: list[str] = []
    seen = set()
    for token in context_events or []:
        if not isinstance(token, str) or not token.startswith(prefix):
            continue
        entity_id = token[len(prefix):]
        if not entity_id or entity_id in seen:
            continue
        seen.add(entity_id)
        found.append(entity_id)
    return found


def felt_reward(
    paid_value: object,
    reference: Optional[LevelReference],
    *,
    gain: float,
    enabled: bool,
    eps: float = SCALE_EPS,
) -> float:
    """Accepted-call reward. Disabled or unknown reference stays at the base.

    ``base + gain * clip(-(paid - ema) / max(spread, eps), -1, 1)``.
    """
    if (
        not enabled
        or reference is None
        or not is_finite_number(paid_value)
    ):
        return ACCEPTED_BASE_REWARD
    ema, spread = reference
    if not is_finite_number(ema):
        return ACCEPTED_BASE_REWARD
    scale = max(float(spread) if is_finite_number(spread) else 0.0, eps)
    z_paid = (float(paid_value) - float(ema)) / scale
    clipped = max(-1.0, min(1.0, -z_paid))
    return ACCEPTED_BASE_REWARD + float(gain) * clipped


__all__ = [
    "ACCEPTED_BASE_REWARD",
    "DEFAULT_BUCKET_Z",
    "DEFAULT_MEMORY_ALPHA",
    "DEFAULT_REWARD_GAIN",
    "SCALE_EPS",
    "LevelReference",
    "NumericMemory",
    "band_token",
    "classify_band",
    "collect_values",
    "felt_reward",
    "lookup_reference",
    "perceived_entity_ids",
]
