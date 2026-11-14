"""
Genome vector for evolutionary tuning of NOWA agent parameters.

This module is intentionally standalone and uses only Python standard library.
"""

from __future__ import annotations

import math
import random
import warnings
from collections import OrderedDict
from dataclasses import dataclass
from typing import Dict, List, Tuple


GENOME_VERSION = "1.0"


@dataclass(frozen=True)
class GeneDescriptor:
    """Metadata and constraints for one genome gene."""

    key: str
    module: str
    min_val: float
    max_val: float
    default: float
    sigma: float
    description: str

    def __post_init__(self):
        if self.min_val >= self.max_val:
            raise ValueError(f"Invalid range for gene {self.key}: min_val >= max_val")
        if not (self.min_val <= self.default <= self.max_val):
            raise ValueError(f"Default value out of range for gene {self.key}")
        if self.sigma <= 0.0:
            raise ValueError(f"Sigma must be positive for gene {self.key}")


def _clamp(value: float, min_val: float, max_val: float) -> float:
    return max(min_val, min(max_val, value))


def _safe_float(value, fallback: float) -> float:
    try:
        casted = float(value)
    except (TypeError, ValueError):
        return float(fallback)
    if math.isnan(casted) or math.isinf(casted):
        return float(fallback)
    return casted


def _build_gene_registry() -> "OrderedDict[str, GeneDescriptor]":
    specs = [
        # NM group: neuromodulators
        ("nm_da_ne_weight", "neuromodulators", -0.4, 0.0, -0.2, 0.05, "DA to NE inhibition"),
        ("nm_ne_da_weight", "neuromodulators", 0.0, 0.4, 0.2, 0.05, "NE to DA excitation"),
        ("nm_da_ach_weight", "neuromodulators", -0.5, -0.1, -0.3, 0.05, "DA to ACh inhibition"),
        ("nm_ach_da_weight", "neuromodulators", -0.5, -0.1, -0.3, 0.05, "ACh to DA inhibition"),
        ("nm_acc_k_ne", "neuromodulators", 0.2, 1.0, 0.5, 0.10, "ACC sensitivity to NE"),
        ("nm_acc_k_cort", "neuromodulators", 0.3, 1.2, 0.7, 0.10, "ACC sensitivity to cortisol"),
        ("nm_acc_k_ht", "neuromodulators", 0.1, 0.6, 0.35, 0.05, "ACC inhibition by serotonin"),
        ("nm_decay_half_life", "neuromodulators", 45.0, 180.0, 90.0, 15.0, "Neuromodulator half-life (sec)"),
        # AF group: affective space
        ("af_decay_valence", "affective_space", 0.80, 0.98, 0.92, 0.03, "Mood inertia"),
        ("af_decay_arousal", "affective_space", 0.60, 0.92, 0.80, 0.05, "Arousal calming speed"),
        ("af_decay_dominance", "affective_space", 0.88, 0.99, 0.97, 0.02, "Dominance stability"),
        ("af_decay_stress", "affective_space", 0.55, 0.88, 0.70, 0.05, "Stress relaxation speed"),
        ("af_decay_curiosity", "affective_space", 0.60, 0.90, 0.78, 0.05, "Curiosity decay"),
        ("af_decay_trust", "affective_space", 0.85, 0.99, 0.95, 0.02, "Trust inertia"),
        ("af_decay_attachment", "affective_space", 0.85, 0.99, 0.93, 0.02, "Attachment inertia"),
        ("af_lambda_reg", "affective_space", 0.01, 0.10, 0.05, 0.01, "Homeostatic return strength"),
        # Same value as affective_space.DEFAULT_BASELINE_ADAPT_RATE (tau = 6 h).
        ("af_baseline_adapt_rate", "affective_space", 0.0, 0.01, 1.0 / (6.0 * 3600.0), 0.5 / (6.0 * 3600.0), "Allostatic rate per second"),
        # WK group: wakefulness
        ("wk_circadian_amplitude", "wakefulness", 0.1, 0.5, 0.3, 0.05, "Circadian rhythm amplitude"),
        ("wk_circadian_phase", "wakefulness", -1.57, 1.57, 0.0, 0.30, "Chronotype phase shift"),
        ("wk_accumulation_factor", "wakefulness", 0.5, 2.0, 1.0, 0.20, "Fatigue accumulation factor"),
        ("wk_recovery_factor", "wakefulness", 0.5, 2.0, 1.0, 0.20, "Recovery factor"),
        # DR group: autonomous drives
        ("dr_curiosity_baseline", "autonomous", 0.05, 0.40, 0.18, 0.05, "Curiosity baseline"),
        ("dr_social_drive_baseline", "autonomous", 0.05, 0.45, 0.22, 0.05, "Social drive baseline"),
        ("dr_exploration_baseline", "autonomous", 0.05, 0.35, 0.12, 0.04, "Exploration baseline"),
        ("dr_energy_recovery_rate", "autonomous", 0.02, 0.10, 0.05, 0.01, "Energy recovery rate"),
        ("dr_cognitive_cost", "autonomous", 0.01, 0.06, 0.03, 0.01, "Cognitive energy cost"),
        ("dr_curiosity_threshold", "autonomous", 0.30, 0.65, 0.45, 0.05, "Curiosity activation threshold"),
        ("dr_social_threshold", "autonomous", 0.35, 0.70, 0.50, 0.05, "Social activation threshold"),
        (
            "dr_perception_radius_factor",
            "swarm",
            0.5,
            2.0,
            1.0,
            0.2,
            "Perception radius multiplier for swarm environment",
        ),
        # LR group: learning and memory
        ("lr_gamma", "value_layer", 0.80, 0.99, 0.95, 0.02, "Future reward discount"),
        ("lr_alpha_online", "value_layer", 0.01, 0.08, 0.03, 0.01, "Online learning rate"),
        ("lr_tonic_slow_rate", "value_layer", 0.003, 0.03, 0.01, 0.003, "Tonic dopamine inertia"),
        ("lr_similarity_threshold", "hippocampus", 0.40, 0.80, 0.60, 0.05, "Memory activation threshold"),
        ("lr_consolidation_threshold", "sleep", 0.10, 0.60, 0.30, 0.05, "Consolidation threshold"),
        # IM group: imagination
        ("im_goal_bias", "imagination", 0.10, 0.70, 0.35, 0.08, "Goal orientation in imagination"),
        ("im_confidence_decay", "imagination", 0.70, 0.99, 0.90, 0.05, "Confidence decay by depth"),
        ("im_novelty_weight", "imagination", 0.10, 0.70, 0.40, 0.08, "Novelty weight"),
        ("im_value_blend", "imagination", 0.30, 0.90, 0.60, 0.08, "Blend between memory and imagination"),
        # LT group: lifespan/time
        ("lt_max_lifespan_factor", "mortality", 0.5, 2.0, 1.0, 0.2, "Maximum lifespan multiplier"),
    ]

    registry: "OrderedDict[str, GeneDescriptor]" = OrderedDict()
    for key, module, min_val, max_val, default, sigma, description in specs:
        if key in registry:
            raise ValueError(f"Duplicate gene key in registry: {key}")
        registry[key] = GeneDescriptor(
            key=key,
            module=module,
            min_val=min_val,
            max_val=max_val,
            default=default,
            sigma=sigma,
            description=description,
        )
    return registry


GENE_REGISTRY: "OrderedDict[str, GeneDescriptor]" = _build_gene_registry()
GENE_KEYS = tuple(GENE_REGISTRY.keys())

GENE_GROUPS: "OrderedDict[str, List[str]]" = OrderedDict()
for _key in GENE_KEYS:
    _group = _key.split("_", 1)[0].upper()
    if _group not in GENE_GROUPS:
        GENE_GROUPS[_group] = []
    GENE_GROUPS[_group].append(_key)


@dataclass(frozen=True)
class GenomeVector:
    """
    Flat vector of evolvable scalar parameters.

    The object is functionally immutable: mutation and crossover return new objects.
    """

    genes: Dict[str, float]
    generation: int = 0
    lineage_id: str = ""

    def __post_init__(self):
        normalized: Dict[str, float] = {}
        missing = []
        for key, descriptor in GENE_REGISTRY.items():
            if key not in self.genes:
                missing.append(key)
                continue
            value = _safe_float(self.genes[key], descriptor.default)
            if value < descriptor.min_val or value > descriptor.max_val:
                raise ValueError(
                    f"Gene {key} out of range during construction: "
                    f"{value} not in [{descriptor.min_val}, {descriptor.max_val}]"
                )
            normalized[key] = value

        if missing:
            raise ValueError(f"Missing required genes: {', '.join(missing)}")

        object.__setattr__(self, "genes", normalized)
        object.__setattr__(self, "generation", max(0, int(self.generation)))
        object.__setattr__(self, "lineage_id", str(self.lineage_id))

    @classmethod
    def default(cls) -> "GenomeVector":
        genes = {key: descriptor.default for key, descriptor in GENE_REGISTRY.items()}
        return cls(genes=genes, generation=0, lineage_id="")

    @classmethod
    def random(cls, rng: random.Random = None) -> "GenomeVector":
        generator = rng if rng is not None else random.Random()
        genes = {
            key: generator.uniform(descriptor.min_val, descriptor.max_val)
            for key, descriptor in GENE_REGISTRY.items()
        }
        return cls(genes=genes, generation=0, lineage_id="")

    @classmethod
    def from_dict(cls, data: dict) -> "GenomeVector":
        raw = dict(data or {})
        if isinstance(raw.get("genes"), dict):
            source = dict(raw.get("genes") or {})
        else:
            source = raw

        genes: Dict[str, float] = {}
        for key, descriptor in GENE_REGISTRY.items():
            value = source.get(key, descriptor.default)
            casted = _safe_float(value, descriptor.default)
            clamped = _clamp(casted, descriptor.min_val, descriptor.max_val)
            if casted != clamped:
                warnings.warn(
                    (
                        f"Gene '{key}' value {casted} is out of range "
                        f"[{descriptor.min_val}, {descriptor.max_val}] and was clamped."
                    ),
                    RuntimeWarning,
                    stacklevel=2,
                )
            genes[key] = clamped

        generation = max(0, int(_safe_float(raw.get("generation", 0), 0.0)))
        lineage_id = str(raw.get("lineage_id", ""))
        return cls(genes=genes, generation=generation, lineage_id=lineage_id)

    @classmethod
    def from_array(cls, array: List[float], generation: int = 0) -> "GenomeVector":
        if len(array) != len(GENE_REGISTRY):
            raise ValueError(
                f"Array length mismatch: expected {len(GENE_REGISTRY)}, got {len(array)}"
            )

        genes: Dict[str, float] = {}
        for key, raw_value in zip(GENE_KEYS, array):
            descriptor = GENE_REGISTRY[key]
            casted = _safe_float(raw_value, descriptor.default)
            genes[key] = _clamp(casted, descriptor.min_val, descriptor.max_val)

        return cls(genes=genes, generation=max(0, int(generation)), lineage_id="")

    def _gene_value(self, key: str) -> float:
        descriptor = GENE_REGISTRY[key]
        raw = self.genes.get(key, descriptor.default)
        casted = _safe_float(raw, descriptor.default)
        return _clamp(casted, descriptor.min_val, descriptor.max_val)

    def mutate(
        self,
        rate: float = 0.05,
        sigma_scale: float = 1.0,
        rng: random.Random = None,
    ) -> "GenomeVector":
        mutation_rate = _clamp(_safe_float(rate, 0.05), 0.0, 1.0)
        sigma_factor = _clamp(_safe_float(sigma_scale, 1.0), 0.1, 5.0)
        generator = rng if rng is not None else random.Random()

        if mutation_rate <= 0.0:
            return GenomeVector(
                genes={key: self._gene_value(key) for key in GENE_KEYS},
                generation=self.generation,
                lineage_id=self.lineage_id,
            )

        genes: Dict[str, float] = {}
        for key, descriptor in GENE_REGISTRY.items():
            value = self._gene_value(key)
            if generator.random() <= mutation_rate:
                value += generator.gauss(0.0, descriptor.sigma * sigma_factor)
            genes[key] = _clamp(value, descriptor.min_val, descriptor.max_val)

        return GenomeVector(
            genes=genes,
            generation=self.generation,
            lineage_id=self.lineage_id,
        )

    def _sbx_pair(
        self,
        value_a: float,
        value_b: float,
        eta: float,
        rng: random.Random,
    ) -> Tuple[float, float]:
        if abs(value_a - value_b) < 1e-12:
            return value_a, value_b

        u = rng.random()
        if u <= 0.5:
            beta = (2.0 * u) ** (1.0 / (eta + 1.0))
        else:
            beta = (1.0 / (2.0 * (1.0 - u))) ** (1.0 / (eta + 1.0))

        child_a = 0.5 * ((1.0 + beta) * value_a + (1.0 - beta) * value_b)
        child_b = 0.5 * ((1.0 - beta) * value_a + (1.0 + beta) * value_b)
        return child_a, child_b

    def crossover(
        self,
        other: "GenomeVector",
        alpha: float = 0.5,
        mode: str = "arithmetic",
        rng: random.Random = None,
    ) -> Tuple["GenomeVector", "GenomeVector"]:
        blend = _clamp(_safe_float(alpha, 0.5), 0.0, 1.0)
        normalized_mode = str(mode).strip().lower()
        generator = rng if rng is not None else random.Random()

        child_a_genes: Dict[str, float] = {}
        child_b_genes: Dict[str, float] = {}

        for key, descriptor in GENE_REGISTRY.items():
            value_a = self._gene_value(key)
            value_b = other._gene_value(key)

            if normalized_mode == "arithmetic":
                new_a = (blend * value_a) + ((1.0 - blend) * value_b)
                new_b = ((1.0 - blend) * value_a) + (blend * value_b)
            elif normalized_mode == "uniform":
                if generator.random() < 0.5:
                    new_a, new_b = value_a, value_b
                else:
                    new_a, new_b = value_b, value_a
            elif normalized_mode == "sbx":
                new_a, new_b = self._sbx_pair(value_a, value_b, eta=2.0, rng=generator)
            else:
                raise ValueError(f"Unknown crossover mode: {mode}")

            child_a_genes[key] = _clamp(new_a, descriptor.min_val, descriptor.max_val)
            child_b_genes[key] = _clamp(new_b, descriptor.min_val, descriptor.max_val)

        child_generation = max(self.generation, other.generation) + 1
        lineage = f"{self.lineage_id}x{other.lineage_id}"[:64]

        child_a = GenomeVector(
            genes=child_a_genes,
            generation=child_generation,
            lineage_id=lineage,
        )
        child_b = GenomeVector(
            genes=child_b_genes,
            generation=child_generation,
            lineage_id=lineage,
        )
        return child_a, child_b

    def distance(self, other: "GenomeVector") -> float:
        squared = 0.0
        for key, descriptor in GENE_REGISTRY.items():
            span = descriptor.max_val - descriptor.min_val
            scaled_self = (self._gene_value(key) - descriptor.min_val) / span
            scaled_other = (other._gene_value(key) - descriptor.min_val) / span
            diff = scaled_self - scaled_other
            squared += diff * diff
        normalized = math.sqrt(squared) / math.sqrt(len(GENE_REGISTRY))
        return _clamp(normalized, 0.0, 1.0)

    def similarity(self, other: "GenomeVector") -> float:
        return 1.0 - self.distance(other)

    def to_agent_params(self) -> dict:
        g = {key: self._gene_value(key) for key in GENE_KEYS}
        return {
            "affective_space": {
                "axis_decay": {
                    "valence": g["af_decay_valence"],
                    "arousal": g["af_decay_arousal"],
                    "dominance": g["af_decay_dominance"],
                    "stress": g["af_decay_stress"],
                    "curiosity": g["af_decay_curiosity"],
                    "trust": g["af_decay_trust"],
                    "attachment": g["af_decay_attachment"],
                },
                "lambda_reg": g["af_lambda_reg"],
                "baseline_adapt_rate": g["af_baseline_adapt_rate"],
            },
            "wakefulness": {
                "circadian_amplitude": g["wk_circadian_amplitude"],
                "circadian_phase": g["wk_circadian_phase"],
                "accumulation_rate_factor": g["wk_accumulation_factor"],
                "recovery_rate_factor": g["wk_recovery_factor"],
            },
            "neuromodulators": {
                "interaction_overrides": {
                    "da_ne": g["nm_da_ne_weight"],
                    "ne_da": g["nm_ne_da_weight"],
                    "da_ach": g["nm_da_ach_weight"],
                    "ach_da": g["nm_ach_da_weight"],
                },
                "acc_k_ne": g["nm_acc_k_ne"],
                "acc_k_cort": g["nm_acc_k_cort"],
                "acc_k_ht": g["nm_acc_k_ht"],
                "decay_half_life": g["nm_decay_half_life"],
            },
            "autonomous": {
                "drive_baselines": {
                    "curiosity": g["dr_curiosity_baseline"],
                    "social_drive": g["dr_social_drive_baseline"],
                    "exploration": g["dr_exploration_baseline"],
                },
                "drive_thresholds": {
                    "curiosity": g["dr_curiosity_threshold"],
                    "social_drive": g["dr_social_threshold"],
                },
                "perception_radius_factor": g["dr_perception_radius_factor"],
                "energy_recovery_rate": g["dr_energy_recovery_rate"],
                "cognitive_cost": g["dr_cognitive_cost"],
            },
            "mortality": {
                "max_lifespan_factor": g["lt_max_lifespan_factor"],
            },
            "value_layer": {
                "gamma_default": g["lr_gamma"],
                "alpha_online_default": g["lr_alpha_online"],
                "tonic_slow_rate": g["lr_tonic_slow_rate"],
            },
            "hippocampus": {
                "similarity_threshold": g["lr_similarity_threshold"],
            },
            "sleep": {
                "consolidation_threshold": g["lr_consolidation_threshold"],
            },
            "imagination": {
                "goal_bias": g["im_goal_bias"],
                "confidence_decay": g["im_confidence_decay"],
                "state_novelty_weight": g["im_novelty_weight"],
                "value_blend": g["im_value_blend"],
            },
        }

    def to_dict(self) -> dict:
        return {
            "version": GENOME_VERSION,
            "generation": int(self.generation),
            "lineage_id": self.lineage_id,
            "genes": {key: self._gene_value(key) for key in GENE_KEYS},
        }

    def to_array(self) -> List[float]:
        return [self._gene_value(key) for key in GENE_KEYS]

    def validate(self) -> List[str]:
        issues: List[str] = []

        for key, descriptor in GENE_REGISTRY.items():
            if key not in self.genes:
                issues.append(f"Missing gene: {key}")
                continue

            raw_value = self.genes[key]
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                issues.append(f"Gene '{key}' has non-numeric value: {raw_value!r}")
                continue

            if math.isnan(value):
                issues.append(f"Gene '{key}' is NaN")
                continue

            if math.isinf(value):
                issues.append(f"Gene '{key}' is infinite")
                continue

            if value < descriptor.min_val or value > descriptor.max_val:
                issues.append(
                    f"Gene '{key}' out of range: {value} not in "
                    f"[{descriptor.min_val}, {descriptor.max_val}]"
                )

        for key in self.genes.keys():
            if key not in GENE_REGISTRY:
                issues.append(f"Unknown gene key: {key}")

        if self.generation < 0:
            issues.append("Generation must be non-negative")

        return issues

    def summary(self) -> dict:
        report = {}
        for group, keys in GENE_GROUPS.items():
            values = [self._gene_value(key) for key in keys]
            defaults = [GENE_REGISTRY[key].default for key in keys]

            mean_v = sum(values) / len(values)
            variance = sum((v - mean_v) ** 2 for v in values) / len(values)
            std_v = math.sqrt(variance)

            normalized_deviation = 0.0
            for key, value, default in zip(keys, values, defaults):
                descriptor = GENE_REGISTRY[key]
                span = descriptor.max_val - descriptor.min_val
                normalized_deviation += abs(value - default) / span
            normalized_deviation /= len(keys)

            report[group] = {
                "mean": mean_v,
                "std": std_v,
                "deviation_from_default": normalized_deviation,
            }
        return report
