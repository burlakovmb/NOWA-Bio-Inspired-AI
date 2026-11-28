"""NOWA procurement sandbox — Stage 1 training world for a virtual buyer.

The sandbox teaches one sovereign NOWA agent to make procurement decisions in
a simulated market, before any contact with real MCP data or real money.
"""

from .procurement_fitness import (
    GRADUATION_THRESHOLDS,
    NON_REGRESSION_FLOOR,
    PROCUREMENT_CRITERIA,
    STAGE_1A_CRITERIA,
    STAGE_1B_CRITERIA,
    STAGE_CRITERIA,
    ProcurementFitnessEvaluator,
    ProcurementFitnessVector,
)
from .procurement_hippocampus_seeder import (
    PROFESSIONAL_SEED_EPISODES,
    ProcurementHippocampusSeeder,
)
from .procurement_motor_adapter import OrderParams, ProcurementMotorAdapter
from .procurement_world import (
    PendingOrder,
    ProcurementWorld,
    ProcurementWorldConfig,
    VirtualProduct,
    VirtualSupplier,
)
from .sandbox_agent_factory import (
    PROCUREMENT_ACTIONS,
    create_procurement_agent,
    seed_procurement_intuition,
)
from .sandbox_checkpoint import (
    SandboxCheckpoint,
    load_checkpoint,
    restore_agent,
    save_checkpoint,
)
from .sandbox_config import SandboxConfig
from .sandbox_encoder import AFFECTIVE_MAPPING, SandboxEncoder, classify_world_events
from .scenario import Call, Observation, Outcome, Scenario
from .sandbox_observer import SandboxObserver
from .stage_baseline import (
    MIN_QUARTERS_FOR_BASELINE,
    compute_stage_1a_baseline,
    load_baseline,
    load_baseline_bundle,
    non_regression_floor,
    save_baseline,
)
from .world_difficulty import WorldDifficulty, estimate_difficulty
from .training_loop import QuarterResult, SandboxTrainer, SandboxTrainingResult

__version__ = "2.0.0"

__all__ = [
    "AFFECTIVE_MAPPING",
    "GRADUATION_THRESHOLDS",
    "MIN_QUARTERS_FOR_BASELINE",
    "NON_REGRESSION_FLOOR",
    "PROFESSIONAL_SEED_EPISODES",
    "PROCUREMENT_ACTIONS",
    "PROCUREMENT_CRITERIA",
    "STAGE_1A_CRITERIA",
    "STAGE_1B_CRITERIA",
    "STAGE_CRITERIA",
    "PendingOrder",
    "OrderParams",
    "ProcurementFitnessEvaluator",
    "ProcurementHippocampusSeeder",
    "ProcurementMotorAdapter",
    "ProcurementFitnessVector",
    "ProcurementWorld",
    "ProcurementWorldConfig",
    "QuarterResult",
    "SandboxCheckpoint",
    "SandboxConfig",
    "SandboxEncoder",
    "SandboxObserver",
    "Call",
    "Observation",
    "Outcome",
    "Scenario",
    "SandboxTrainer",
    "SandboxTrainingResult",
    "VirtualProduct",
    "VirtualSupplier",
    "WorldDifficulty",
    "classify_world_events",
    "compute_stage_1a_baseline",
    "create_procurement_agent",
    "estimate_difficulty",
    "load_baseline",
    "load_baseline_bundle",
    "load_checkpoint",
    "non_regression_floor",
    "restore_agent",
    "save_baseline",
    "save_checkpoint",
    "seed_procurement_intuition",
]
