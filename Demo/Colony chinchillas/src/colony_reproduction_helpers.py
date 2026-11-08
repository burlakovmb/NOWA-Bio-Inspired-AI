"""Helpers for reproduction mechanics."""

from __future__ import annotations

import random

from config_colony import LITTER_SIZE


def resource_blocks_reproduction(food_pellets: float) -> bool:
    """Reproduction is blocked when food level is critically low."""
    return food_pellets < 0.15


def choose_litter_size(rng: random.Random | None = None) -> int:
    """Pick offspring count for one birth event."""
    random_source = rng if rng is not None else random
    return random_source.randint(*LITTER_SIZE)


