"""Shared colony resources with simple lock semantics."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class SharedResources:
    """Passive state for resources accessible by all agents."""

    food_pellets: float = 1.0
    hay: float = 1.0
    water: float = 1.0
    wheel_lock: str | None = None
    dustbath_lock: str | None = None
    house_occupants: list[str] = field(default_factory=list)
    shelf_occupants: dict[str, list[str]] = field(
        default_factory=lambda: {
            "shelf_lower": [],
            "shelf_mid": [],
            "shelf_upper": [],
        }
    )
    last_refill_time: float = 0.0

    def acquire_exclusive(self, resource: str, agent_id: str) -> bool:
        """Acquire exclusive resource lock if available."""
        if resource == "wheel":
            if self.wheel_lock in (None, agent_id):
                self.wheel_lock = agent_id
                return True
            return False
        if resource == "dustbath":
            if self.dustbath_lock in (None, agent_id):
                self.dustbath_lock = agent_id
                return True
            return False
        raise ValueError(f"Unsupported exclusive resource: {resource}")

    def release_exclusive(self, resource: str, agent_id: str) -> None:
        """Release exclusive lock when owned by given agent."""
        if resource == "wheel" and self.wheel_lock == agent_id:
            self.wheel_lock = None
        elif resource == "dustbath" and self.dustbath_lock == agent_id:
            self.dustbath_lock = None

    def consume_food(
        self,
        amount: float,
        *,
        primary: str | None = None,
        strict: bool = False,
    ) -> bool:
        """
        Consume food from pellets/hay with optional primary preference.

        If `primary` is not provided and both sources are available, consumption
        starts with an equal split and then uses the source with remaining stock.

        `strict=False` keeps that shared-pool behavior and returns False only
        when both pools are empty. `strict=True` takes only from `primary`
        and does not top up from the other bowl. It returns False when that
        bowl cannot provide a bite.
        """
        try:
            requested = max(0.0, float(amount))
        except Exception:
            requested = 0.0
        if requested <= 0.0:
            return True

        pellets = max(0.0, float(self.food_pellets))
        hay = max(0.0, float(self.hay))
        if (pellets + hay) <= 0.0:
            return False

        requested = min(requested, pellets + hay)
        remaining = requested

        def _take_from(source: str, amount_to_take: float) -> float:
            if amount_to_take <= 0.0:
                return 0.0
            if source == "hay":
                current = max(0.0, float(self.hay))
                taken = min(current, amount_to_take)
                self.hay = max(0.0, current - taken)
                return taken
            current = max(0.0, float(self.food_pellets))
            taken = min(current, amount_to_take)
            self.food_pellets = max(0.0, current - taken)
            return taken

        if strict:
            if primary not in {"food_pellets", "hay"}:
                return False
            return _take_from(str(primary), remaining) > 0.0

        if primary in {"food_pellets", "hay"}:
            order = [str(primary), "hay" if primary == "food_pellets" else "food_pellets"]
            for source in order:
                remaining -= _take_from(source, remaining)
                if remaining <= 1e-9:
                    break
            return True

        # Equal-priority mode when no preference is provided.
        half = remaining * 0.5
        remaining -= _take_from("food_pellets", half)
        remaining -= _take_from("hay", half)
        if remaining > 1e-9:
            pellets_left = max(0.0, float(self.food_pellets))
            hay_left = max(0.0, float(self.hay))
            first = "food_pellets" if pellets_left >= hay_left else "hay"
            second = "hay" if first == "food_pellets" else "food_pellets"
            remaining -= _take_from(first, remaining)
            if remaining > 1e-9:
                _take_from(second, remaining)
        return True
