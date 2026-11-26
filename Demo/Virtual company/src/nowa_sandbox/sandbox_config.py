"""YAML configuration loading for the procurement sandbox.

Keeps world physics, training schedule and graduation thresholds in one file
so calibration sweeps (spec section 19) do not require code edits.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

from ._common import clamp, safe_float, safe_int
from .decision_consistency import ConsistencyConfig
from .procurement_fitness import (
    DEFAULT_CONSISTENCY,
    GRADUATION_THRESHOLDS,
    STAGE_CRITERIA,
)
from .price_memory import (
    DEFAULT_PRICE_BUCKET_Z,
    DEFAULT_PRICE_MEMORY_ALPHA,
    DEFAULT_PRICE_REWARD_GAIN,
)
from .procurement_world import ProcurementWorldConfig
from .stage_baseline import (
    COST_VS_CHANCE_FLOOR_DELTA,
    clamp_cost_vs_chance_floor_delta,
)


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "configs" / "default_world.yaml"


def _valid_stage(value: Any) -> str:
    """Fall back to Stage 1a rather than failing on a typo in YAML."""
    stage = str(value).strip()
    return stage if stage in STAGE_CRITERIA else "1a"


def _price_memory_alpha(value: Any, default: float) -> float:
    number = safe_float(value, default)
    if not 0.0 < number <= 1.0:
        raise ValueError(
            f"training.price_memory_alpha must be in (0, 1], got {value!r}"
        )
    return number


def _price_bucket_z(value: Any, default: float) -> float:
    number = safe_float(value, default)
    if not number > 0.0:
        raise ValueError(
            f"training.price_bucket_z must be > 0, got {value!r}"
        )
    return number


def _price_reward_gain(value: Any, default: float) -> float:
    number = safe_float(value, default)
    if not 0.0 <= number <= 0.4:
        raise ValueError(
            f"training.price_reward_gain must be in [0, 0.4], got {value!r}"
        )
    return number

def _consistency_nonempty_str(value: Any, key: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string, got {value!r}")
    return value


def _consistency_str_list(value: Any, key: str, *, non_empty: bool) -> Tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, list):
        raise ValueError(f"{key} must be a list of strings, got {value!r}")
    if non_empty and len(value) == 0:
        raise ValueError(
            f"{key} must be a non-empty list of strings, got {value!r}"
        )
    items = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{key} must be a list of strings, got {value!r}")
        items.append(item)
    return tuple(items)


def _consistency_min_decisions(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 2:
        raise ValueError(
            f"consistency.min_decisions must be an integer >= 2, got {value!r}"
        )
    return value


def _consistency_neutral(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(
            f"consistency.neutral must be in [0, 1], got {value!r}"
        )
    number = float(value)
    if not 0.0 <= number <= 1.0:
        raise ValueError(
            f"consistency.neutral must be in [0, 1], got {value!r}"
        )
    return number


def _consistency_from_mapping(raw: Any) -> ConsistencyConfig:
    if not isinstance(raw, Mapping):
        raise ValueError(f"consistency must be a mapping, got {raw!r}")
    data = dict(raw)
    defaults = DEFAULT_CONSISTENCY
    return ConsistencyConfig(
        entity_field=_consistency_nonempty_str(
            data.get("entity_field", defaults.entity_field),
            "consistency.entity_field",
        ),
        choice_field=_consistency_nonempty_str(
            data.get("choice_field", defaults.choice_field),
            "consistency.choice_field",
        ),
        attached_prefixes=_consistency_str_list(
            data.get("attached_prefixes", list(defaults.attached_prefixes)),
            "consistency.attached_prefixes",
            non_empty=False,
        ),
        counted_statuses=_consistency_str_list(
            data.get("counted_statuses", list(defaults.counted_statuses)),
            "consistency.counted_statuses",
            non_empty=True,
        ),
        min_decisions=_consistency_min_decisions(
            data.get("min_decisions", defaults.min_decisions)
        ),
        neutral=_consistency_neutral(data.get("neutral", defaults.neutral)),
    )


@dataclass
class TrainingConfig:
    n_quarters: int = 30
    sleep_every_n_days: int = 7
    stop_on_graduation: bool = True
    seed: int = 42
    seed_intuition: bool = True
    stage: str = "1a"
    """Curriculum stage (v1.1 section 26): "1a" rotating suppliers, "1b" persistent."""
    # Stage 1b only. K supplier sets, each held for quarters_per_supplier_set
    # quarters counted from the first Stage 1b quarter.
    supplier_set_count: int = 4
    quarters_per_supplier_set: int = 5
    # Coarse price band in context, and felt cost on an accepted order.
    # Off keeps the previous tokens and the flat 0.4 reward.
    price_perception: bool = True
    price_memory_alpha: float = DEFAULT_PRICE_MEMORY_ALPHA
    price_bucket_z: float = DEFAULT_PRICE_BUCKET_Z
    price_reward_gain: float = DEFAULT_PRICE_REWARD_GAIN


@dataclass
class StageBaselineConfig:
    # Lower bound of the normalized cost floor. A degenerate or near-zero
    # Stage 1a baseline must not let a random policy pass the Stage 1b guard.
    # Allowed range: 0.02–0.05.
    cost_vs_chance_floor_delta: float = COST_VS_CHANCE_FLOOR_DELTA


@dataclass
class OutputConfig:
    results_dir: str = "results/"
    save_per_quarter_snapshots: bool = True


@dataclass
class SandboxConfig:
    world: ProcurementWorldConfig = field(default_factory=ProcurementWorldConfig)
    training: TrainingConfig = field(default_factory=TrainingConfig)
    graduation_thresholds: Dict[str, float] = field(
        default_factory=lambda: dict(GRADUATION_THRESHOLDS)
    )
    stage_baseline: StageBaselineConfig = field(default_factory=StageBaselineConfig)
    consistency: ConsistencyConfig = field(default_factory=lambda: DEFAULT_CONSISTENCY)
    output: OutputConfig = field(default_factory=OutputConfig)

    @classmethod
    def from_mapping(cls, data: Optional[Mapping[str, Any]]) -> "SandboxConfig":
        data = dict(data or {})
        config = cls()

        world = dict(data.get("world") or {})
        defaults = ProcurementWorldConfig()
        config.world = ProcurementWorldConfig(
            initial_budget=safe_float(
                world.get("initial_budget", defaults.initial_budget),
                defaults.initial_budget,
            ),
            n_products=safe_int(world.get("n_products", defaults.n_products), defaults.n_products, minimum=0),
            n_suppliers=safe_int(world.get("n_suppliers", defaults.n_suppliers), defaults.n_suppliers, minimum=0),
            days_per_quarter=safe_int(
                world.get("days_per_quarter", defaults.days_per_quarter),
                defaults.days_per_quarter,
                minimum=0,
            ),
            demand_shock_probability=safe_float(
                world.get("demand_shock_probability", defaults.demand_shock_probability),
                defaults.demand_shock_probability,
            ),
            supplier_default_probability=safe_float(
                world.get("supplier_default_probability", defaults.supplier_default_probability),
                defaults.supplier_default_probability,
            ),
            late_delivery_probability_base=safe_float(
                world.get("late_delivery_probability_base", defaults.late_delivery_probability_base),
                defaults.late_delivery_probability_base,
            ),
            seed=None if world.get("seed") is None else safe_int(world.get("seed"), 0),
            max_lead_time_days=safe_int(
                world.get("max_lead_time_days", defaults.max_lead_time_days),
                defaults.max_lead_time_days,
                minimum=3,
            ),
            max_demand_per_day=safe_float(
                world.get("max_demand_per_day", defaults.max_demand_per_day),
                defaults.max_demand_per_day,
            ),
            min_reorder_days=safe_float(
                world.get("min_reorder_days", defaults.min_reorder_days),
                defaults.min_reorder_days,
            ),
            max_reorder_days=safe_float(
                world.get("max_reorder_days", defaults.max_reorder_days),
                defaults.max_reorder_days,
            ),
            min_initial_stock_days=safe_float(
                world.get("min_initial_stock_days", defaults.min_initial_stock_days),
                defaults.min_initial_stock_days,
            ),
            max_initial_stock_days=safe_float(
                world.get("max_initial_stock_days", defaults.max_initial_stock_days),
                defaults.max_initial_stock_days,
            ),
            max_demand_volatility=safe_float(
                world.get("max_demand_volatility", defaults.max_demand_volatility),
                defaults.max_demand_volatility,
            ),
            min_supplier_reliability=safe_float(
                world.get("min_supplier_reliability", defaults.min_supplier_reliability),
                defaults.min_supplier_reliability,
            ),
            max_price_volatility=safe_float(
                world.get("max_price_volatility", defaults.max_price_volatility),
                defaults.max_price_volatility,
            ),
        )

        training = dict(data.get("training") or {})
        defaults_training = TrainingConfig()
        config.training = TrainingConfig(
            n_quarters=safe_int(training.get("n_quarters", 30), 30, minimum=0),
            sleep_every_n_days=safe_int(training.get("sleep_every_n_days", 7), 7, minimum=1),
            stop_on_graduation=bool(training.get("stop_on_graduation", True)),
            seed=safe_int(training.get("seed", 42), 42),
            seed_intuition=bool(training.get("seed_intuition", True)),
            stage=_valid_stage(training.get("stage", "1a")),
            supplier_set_count=safe_int(
                training.get("supplier_set_count", defaults_training.supplier_set_count),
                defaults_training.supplier_set_count,
                minimum=1,
            ),
            quarters_per_supplier_set=safe_int(
                training.get(
                    "quarters_per_supplier_set",
                    defaults_training.quarters_per_supplier_set,
                ),
                defaults_training.quarters_per_supplier_set,
                minimum=1,
            ),
            price_perception=bool(
                training.get(
                    "price_perception", defaults_training.price_perception
                )
            ),
            price_memory_alpha=_price_memory_alpha(
                training.get(
                    "price_memory_alpha", defaults_training.price_memory_alpha
                ),
                defaults_training.price_memory_alpha,
            ),
            price_bucket_z=_price_bucket_z(
                training.get("price_bucket_z", defaults_training.price_bucket_z),
                defaults_training.price_bucket_z,
            ),
            price_reward_gain=_price_reward_gain(
                training.get(
                    "price_reward_gain", defaults_training.price_reward_gain
                ),
                defaults_training.price_reward_gain,
            ),
        )

        thresholds = dict(GRADUATION_THRESHOLDS)
        for criterion, value in dict(data.get("graduation_thresholds") or {}).items():
            if criterion in thresholds:
                thresholds[criterion] = clamp(
                    safe_float(value, thresholds[criterion]), 0.0, 1.0
                )
        config.graduation_thresholds = thresholds

        baseline_cfg = dict(data.get("stage_baseline") or {})
        config.stage_baseline = StageBaselineConfig(
            cost_vs_chance_floor_delta=clamp_cost_vs_chance_floor_delta(
                baseline_cfg.get(
                    "cost_vs_chance_floor_delta",
                    COST_VS_CHANCE_FLOOR_DELTA,
                )
            ),
        )

        if data.get("consistency") is not None:
            config.consistency = _consistency_from_mapping(data["consistency"])

        output = dict(data.get("output") or {})
        config.output = OutputConfig(
            results_dir=str(output.get("results_dir", "results/")),
            save_per_quarter_snapshots=bool(output.get("save_per_quarter_snapshots", True)),
        )
        return config

    @classmethod
    def from_yaml(cls, path: Any) -> "SandboxConfig":
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise RuntimeError(
                "pyyaml is required to load sandbox YAML configs; "
                "install it via requirements.txt"
            ) from exc

        text = Path(path).read_text(encoding="utf-8")
        data = yaml.safe_load(text) or {}
        if not isinstance(data, Mapping):
            raise ValueError(f"config at {path} must be a YAML mapping")
        return cls.from_mapping(data)

    @classmethod
    def load(cls, path: Optional[Any] = None) -> "SandboxConfig":
        """Load from ``path``, or return defaults when no config is supplied."""
        if path is None:
            return cls()
        return cls.from_yaml(path)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "world": {
                "initial_budget": self.world.initial_budget,
                "n_products": self.world.n_products,
                "n_suppliers": self.world.n_suppliers,
                "days_per_quarter": self.world.days_per_quarter,
                "demand_shock_probability": self.world.demand_shock_probability,
                "supplier_default_probability": self.world.supplier_default_probability,
                "late_delivery_probability_base": self.world.late_delivery_probability_base,
                "seed": self.world.seed,
                "max_lead_time_days": self.world.max_lead_time_days,
                "max_demand_per_day": self.world.max_demand_per_day,
                "min_reorder_days": self.world.min_reorder_days,
                "max_reorder_days": self.world.max_reorder_days,
                "min_initial_stock_days": self.world.min_initial_stock_days,
                "max_initial_stock_days": self.world.max_initial_stock_days,
                "max_demand_volatility": self.world.max_demand_volatility,
                "min_supplier_reliability": self.world.min_supplier_reliability,
                "max_price_volatility": self.world.max_price_volatility,
            },
            "training": {
                "n_quarters": self.training.n_quarters,
                "sleep_every_n_days": self.training.sleep_every_n_days,
                "stop_on_graduation": self.training.stop_on_graduation,
                "seed": self.training.seed,
                "seed_intuition": self.training.seed_intuition,
                "stage": self.training.stage,
                "supplier_set_count": self.training.supplier_set_count,
                "quarters_per_supplier_set": self.training.quarters_per_supplier_set,
                "price_perception": self.training.price_perception,
                "price_memory_alpha": self.training.price_memory_alpha,
                "price_bucket_z": self.training.price_bucket_z,
                "price_reward_gain": self.training.price_reward_gain,
            },
            "graduation_thresholds": dict(self.graduation_thresholds),
            "stage_baseline": {
                "cost_vs_chance_floor_delta": self.stage_baseline.cost_vs_chance_floor_delta,
            },
            "consistency": {
                "entity_field": self.consistency.entity_field,
                "choice_field": self.consistency.choice_field,
                "attached_prefixes": list(self.consistency.attached_prefixes),
                "counted_statuses": list(self.consistency.counted_statuses),
                "min_decisions": self.consistency.min_decisions,
                "neutral": self.consistency.neutral,
            },
            "output": {
                "results_dir": self.output.results_dir,
                "save_per_quarter_snapshots": self.output.save_per_quarter_snapshots,
            },
        }


__all__ = [
    "SandboxConfig",
    "TrainingConfig",
    "StageBaselineConfig",
    "OutputConfig",
    "DEFAULT_CONFIG_PATH",
]
