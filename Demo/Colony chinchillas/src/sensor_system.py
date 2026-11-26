"""Perception helpers for colony simulation."""

from __future__ import annotations

# Zone adjacency. It is symmetric (issue #28): if A is next to B, B is next to A. The links house-litter,
# floor-shelf_lower and floor-mineral used to be one-way, so one side saw the other but not the reverse.
ADJACENT_ZONES: dict[str, set[str]] = {
    "floor": {"house", "bowl_pellets", "bowl_hay", "wheel", "dustbath", "corner", "toy", "shelf_lower", "mineral"},
    "house": {"floor", "corner", "dustbath", "litter"},
    "wheel": {"floor", "shelf_lower"},
    "shelf_lower": {"wheel", "floor", "shelf_mid"},
    "shelf_mid": {"shelf_lower", "shelf_upper"},
    "shelf_upper": {"shelf_mid"},
    "dustbath": {"floor", "house"},
    "corner": {"floor", "house", "litter"},
    "bowl_pellets": {"floor", "bowl_hay"},
    "bowl_hay": {"floor", "bowl_pellets", "waterer"},
    "waterer": {"bowl_hay"},
    "litter": {"corner", "bars", "house"},
    "bars": {"litter", "door"},
    "door": {"bars"},
    "toy": {"floor"},
    "mineral": {"floor"},
}

# The same neighbours as sorted tuples. Code that picks a neighbour at random iterates these: the order of a set
# depends on PYTHONHASHSEED, so a seeded walk over a set is not reproducible between processes (issue #14).
NEIGHBOURS: dict[str, tuple[str, ...]] = {zone: tuple(sorted(near)) for zone, near in ADJACENT_ZONES.items()}

# Zone adjacency matrix A (issue #28): ZONES[i] is row and column i; A[i][j] = 1 when zone j is zone i or next to it.
ZONES: tuple[str, ...] = tuple(sorted(ADJACENT_ZONES))
ZONE_INDEX: dict[str, int] = {zone: index for index, zone in enumerate(ZONES)}
ADJACENCY: tuple[tuple[int, ...], ...] = tuple(
    tuple(1 if (row == col or col in ADJACENT_ZONES[row]) else 0 for col in ZONES) for row in ZONES
)


def is_same_or_adjacent(source: str, target: str) -> bool:
    """Return True when positions are in contact radius."""
    if source == target:
        return True
    return target in ADJACENT_ZONES.get(source, set())
