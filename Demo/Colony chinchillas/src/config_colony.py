"""Configuration constants for colony simulation."""

from __future__ import annotations

from typing import Final

MATURITY_AGE_S: Final[float] = 900.0
GESTATION_S: Final[float] = 300.0
HEAT_CYCLE_LENGTH_S: Final[float] = 600.0
ESTRUS_DURATION_S: Final[float] = 180.0
# More frequent refill keeps medium/large colonies sustainable.
REFILL_DAY_S: Final[float] = 600.0
OFFER_TIMEOUT_S: Final[float] = 10.0
# Old age is biological age in sim-seconds. A decision-step budget made
# lifespan follow dt and UI speed. Captive chinchillas mature at about
# 8 months and live about 10 years on average, a x15 ratio. The demo
# already maps maturity to MATURITY_AGE_S, so the cap is 15 * 900 = 13500 s.
# 13500 / GESTATION_S = 45 gestations, inside the real 10-15 year span
# (about 33-49 gestations of 111 days). The heat-cycle clock is a poorer
# anchor (the demo cycle is long relative to a real ~38-day cycle).
COLONY_MAX_LIFESPAN_AGE_S: Final[float] = 15.0 * MATURITY_AGE_S
# Kept as MortalitySystem.max_lifespan_steps for snapshots and the
# health-index normalizer. Ignored for death while max_lifespan_age_s is set.
COLONY_MAX_LIFESPAN_STEPS: Final[int] = 20000
# Global resource drain multiplier for colony balancing in dense populations.
RESOURCE_CONSUMPTION_MULTIPLIER: Final[float] = 2.0
# Owner decision: the demo default is on. Hunger, thirst, and sleep are a
# soft policy input, and ignored needs spend energy. An agent can still set
# physiology_as_policy False to keep the historical homeostatic gate.
PHYSIOLOGY_AS_POLICY: Final[bool] = True
UNMET_HUNGER_ENERGY_PER_S: Final[float] = 0.02
UNMET_THIRST_ENERGY_PER_S: Final[float] = 0.025
UNMET_SLEEP_ENERGY_PER_S: Final[float] = 0.02

MAX_INTERACTION_HISTORY: Final[int] = 50
MAX_HEARSAY_ITEMS: Final[int] = 20
MAX_AGENTS_DEMO: Final[int] = 8

LITTER_SIZE: Final[tuple[int, int]] = (1, 3)

NAME_POOL: Final[list[str]] = [
    "Luna",
    "Burya",
    "Orekh",
    "Milo",
    "Aster",
    "Nori",
    "Sora",
    "Vega",
]

OFFER_COOLDOWNS: Final[dict[str, float]] = {
    "sniff_greet": 30.0,
    "allogroom": 60.0,
    "chase": 120.0,
    "mount_display": 45.0,
}

JUVENILE_BLOCKED_OFFERS: Final[set[str]] = {
    "mount_display",
    "chase",
    "territorial_patrol",
    "hyperactivity",
}
