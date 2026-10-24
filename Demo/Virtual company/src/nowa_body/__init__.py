"""NOWA body layer — host over the platform ``mcp_body`` package."""

from ._compat import ensure_core_src_on_path

ensure_core_src_on_path()

from mcp_body import (
    ApprovalGate,
    ApprovalRecord,
    ApprovalStatus,
    BusinessHippocampusSeeder,
    CapabilityRisk,
    GenericEncoder,
    HardConstraintViolation,
    MCPCapability,
    MCPToolRegistry,
    ProposedAction,
    RISK_KEYWORDS,
    SchemaBinder,
    SeedEpisode,
    WAIT_AND_MONITOR,
    WorldState,
    assert_stage2_invariant,
    classify_risk_heuristic,
)

from .business_event_encoder import BusinessEventEncoder, BusinessEventImpulse
from .mock_mcp import MockMCPClient, MockMCPTool
from .runtime import BusinessAgentRuntime
from .motor_adapter import MotorAdapter
from .role_config import (
    RoleConfig,
    RoleConfigError,
    build_encoder,
    build_seeder,
    build_tool_registry,
    load_role_config,
    load_role_config_from_mapping,
    resolve_event_classifier,
    resolve_motor_adapter,
    seed_episodes_to_mappings,
    validate_role_config,
)
from .sleep_scheduler import SleepScheduler

__all__ = [
    "ApprovalGate",
    "ApprovalRecord",
    "ApprovalStatus",
    "BusinessAgentRuntime",
    "BusinessEventEncoder",
    "BusinessEventImpulse",
    "BusinessHippocampusSeeder",
    "CapabilityRisk",
    "GenericEncoder",
    "HardConstraintViolation",
    "MCPCapability",
    "MCPToolRegistry",
    "MockMCPClient",
    "MockMCPTool",
    "MotorAdapter",
    "ProposedAction",
    "RISK_KEYWORDS",
    "RoleConfig",
    "RoleConfigError",
    "SchemaBinder",
    "SeedEpisode",
    "SleepScheduler",
    "WAIT_AND_MONITOR",
    "WorldState",
    "assert_stage2_invariant",
    "build_encoder",
    "build_seeder",
    "build_tool_registry",
    "classify_risk_heuristic",
    "load_role_config",
    "load_role_config_from_mapping",
    "resolve_event_classifier",
    "resolve_motor_adapter",
    "seed_episodes_to_mappings",
    "validate_role_config",
]
