"""RoleConfig loader: YAML data + code pointers, with loud cross-validation."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
import yaml

import nowa_roles.procurement as _procurement_pkg
from nowa_body.lab_session import (
    ORDER_TOOL,
    SCENARIO_STOCK_CRITICAL,
    WRITE_ACCEPTED,
    BodyLabSession,
    LabSettings,
)
from nowa_body.role_config import (
    RoleConfigError,
    build_seeder,
    build_tool_registry,
    load_role_config,
    resolve_event_classifier,
    resolve_motor_adapter,
)
from nowa_body.tool_registry import MCPToolRegistry
from nowa_roles.procurement.event_classifier import classify_procurement_events

from body_support import make_test_agent


PROCUREMENT_CONFIG_PATH = str(
    Path(_procurement_pkg.__file__).resolve().parent / "config.yaml"
)

_DEFAULT_ACTION_TYPES = [
    "place_order_reliable_supplier",
    "place_order_cheap_supplier",
    "urgent_reorder",
    "diversify_supplier",
]

_DEFAULT_CAPABILITIES = [
    {
        "tool_id": "mcp__1c__create_purchase_order",
        "server_name": "1c_erp",
        "display_name": "Create purchase order",
        "description": "WRITE purchase order",
        "risk_level": "medium_write",
        "domain_tags": ["procurement"],
        "requires_approval": True,
        "action_types": ["place_order_reliable_supplier"],
    }
]

_FULL_ACTION_CAPABILITIES = [
    {
        **_DEFAULT_CAPABILITIES[0],
        "action_types": list(_DEFAULT_ACTION_TYPES),
    }
]

_DEFAULT_SEED = [
    {
        "context_tokens": ["a"],
        "action": "place_order_reliable_supplier",
        "consequence": "c",
        "reward": 0.0,
    }
]


def _write_config(
    tmp_path,
    mcp_capabilities=None,
    seed_corpus=...,
    extra=None,
    **overrides,
) -> str:
    payload = {
        "role_id": "test_role",
        "display_name": "Test Role",
        "mcp_capabilities": (
            list(_DEFAULT_CAPABILITIES)
            if mcp_capabilities is None
            else mcp_capabilities
        ),
        "affective_mapping": {},
        "event_classifier": (
            "nowa_roles.procurement.event_classifier:classify_procurement_events"
        ),
    }
    if seed_corpus is ...:
        payload["seed_corpus"] = list(_DEFAULT_SEED)
    elif seed_corpus is not None:
        payload["seed_corpus"] = seed_corpus
    if extra:
        payload.update(extra)
    payload.update(overrides)
    path = tmp_path / "config.yaml"
    path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return str(path)


class TestLoadRoleConfig:

    def test_loads_valid_procurement_config(self, tmp_path):
        config = load_role_config(PROCUREMENT_CONFIG_PATH)
        assert config.role_id == "procurement"
        assert len(config.capabilities) == 6
        assert len(config.seed_corpus) == 9

    def test_missing_file_raises(self):
        with pytest.raises(RoleConfigError, match="not found"):
            load_role_config("/nonexistent/config.yaml")

    def test_invalid_risk_level_raises_with_valid_options_listed(self, tmp_path):
        path = _write_config(tmp_path, mcp_capabilities=[
            {"tool_id": "x", "risk_level": "super_dangerous"}
        ])
        with pytest.raises(RoleConfigError, match="read_only"):
            load_role_config(path)

    def test_invalid_yaml_raises(self, tmp_path):
        path = tmp_path / "broken.yaml"
        path.write_text("role_id: [unterminated", encoding="utf-8")
        with pytest.raises(RoleConfigError, match="invalid YAML"):
            load_role_config(str(path))

    def test_seed_episode_without_action_raises(self, tmp_path):
        path = _write_config(
            tmp_path,
            seed_corpus=[{"context_tokens": ["a"], "consequence": "c", "reward": 0.1}],
        )
        with pytest.raises(RoleConfigError, match="no 'action'"):
            load_role_config(path)

    def test_from_mapping_matches_file_load(self, tmp_path):
        from nowa_body.role_config import load_role_config_from_mapping, seed_episodes_to_mappings

        from_file = load_role_config(PROCUREMENT_CONFIG_PATH)
        assert from_file.seed_corpus_module == ""
        assert from_file.seed_corpus[0].action == "mcp__drivemcp__create_purchase_order"
        raw = yaml.safe_load(Path(PROCUREMENT_CONFIG_PATH).read_text(encoding="utf-8"))
        from_map = load_role_config_from_mapping(raw, PROCUREMENT_CONFIG_PATH)
        assert from_map.role_id == from_file.role_id
        assert len(from_map.seed_corpus) == len(from_file.seed_corpus)
        dumped = seed_episodes_to_mappings(from_file.seed_corpus)
        assert dumped[0]["action"] == from_file.seed_corpus[0].action

    def test_affective_mapping_keeps_canonical_axes(self, tmp_path):
        path = _write_config(
            tmp_path,
            affective_mapping={
                "stock_critical_low": {
                    "valence": -0.7,
                    "arousal": 0.8,
                    "stress": 0.7,
                    "trust": -0.1,
                    "tags": ["risk"],
                    "intensity": 0.35,
                }
            },
        )
        config = load_role_config(path)
        entry = config.affective_mapping["stock_critical_low"]
        assert entry["stress"] == pytest.approx(0.7)
        assert entry["trust"] == pytest.approx(-0.1)
        assert "curiosity" not in entry
        assert entry["intensity"] == pytest.approx(0.35)
        assert entry["tags"] == ["risk"]

    def test_affective_mapping_shorthand_still_loads(self, tmp_path):
        path = _write_config(
            tmp_path,
            affective_mapping={"e": {"valence": 0.1, "arousal": 0.2, "tags": []}},
        )
        entry = load_role_config(path).affective_mapping["e"]
        assert entry["valence"] == pytest.approx(0.1)
        assert entry["intensity"] == pytest.approx(0.35)
        assert "stress" not in entry

    def test_affective_mapping_unknown_axis_raises(self, tmp_path):
        path = _write_config(
            tmp_path,
            affective_mapping={"e": {"valence": 0.0, "arousal": 0.5, "pain": 1.0}},
        )
        with pytest.raises(RoleConfigError, match="unknown key 'pain'"):
            load_role_config(path)


class TestValidateRoleConfig:

    def test_orphan_seed_action_raises(self, tmp_path):
        """The exact bug class this project has hit three times: a seed
        episode's action label that no capability declares."""
        path = _write_config(
            tmp_path,
            mcp_capabilities=[{
                "tool_id": "x", "risk_level": "read_only",
                "action_types": ["known_action"],
            }],
            seed_corpus=[{
                "context_tokens": ["a"], "action": "unknown_action",
                "consequence": "c", "reward": 0.1,
            }],
        )
        with pytest.raises(RoleConfigError, match="unknown_action"):
            load_role_config(path)

    def test_wait_and_monitor_never_flagged_as_orphan(self, tmp_path):
        """wait_and_monitor needs no capability — it means 'do nothing'."""
        path = _write_config(
            tmp_path,
            mcp_capabilities=[],
            seed_corpus=[{
                "context_tokens": ["a"], "action": "wait_and_monitor",
                "consequence": "c", "reward": 0.1,
            }],
        )
        load_role_config(path)  # must not raise

    def test_unseeded_action_type_warns_not_raises(self, tmp_path):
        path = _write_config(
            tmp_path,
            mcp_capabilities=[{
                "tool_id": "mcp__x__write", "risk_level": "medium_write",
            }],
            seed_corpus=[],
        )
        with pytest.warns(UserWarning, match="mcp__x__write"):
            load_role_config(path)


class TestSeedCorpusModuleReference:

    def test_inline_and_module_together_raises(self, tmp_path):
        path = _write_config(
            tmp_path,
            seed_corpus=[{"action": "a", "context_tokens": [], "consequence": "c", "reward": 0.0}],
            extra={"seed_corpus_module": "nowa_roles.procurement.seed_corpus:PROCUREMENT_SEED_EPISODES"},
        )
        with pytest.raises(RoleConfigError, match="not both"):
            load_role_config(path)

    def test_module_reference_loads_existing_corpus(self, tmp_path):
        path = _write_config(
            tmp_path,
            seed_corpus=None,
            mcp_capabilities=[{
                "tool_id": "mcp__drivemcp__create_purchase_order",
                "server_name": "drivemcp",
                "display_name": "Create purchase order",
                "description": "WRITE purchase order",
                "risk_level": "medium_write",
                "domain_tags": ["procurement"],
                "requires_approval": True,
                "action_types": ["mcp__drivemcp__create_purchase_order"],
            }],
            extra={"seed_corpus_module": "nowa_roles.procurement.seed_corpus:PROCUREMENT_SEED_EPISODES"},
        )
        config = load_role_config(path)
        assert len(config.seed_corpus) == 8


class TestResolveOptionalCodePointers:

    def test_non_motor_adapter_subclass_raises(self, tmp_path):
        path = _write_config(tmp_path, extra={
            "motor_adapter": "builtins:dict"
        })
        config = load_role_config(path)
        with pytest.raises(RoleConfigError, match="MotorAdapter subclass"):
            resolve_motor_adapter(config, MCPToolRegistry("test"))

    def test_unset_motor_adapter_returns_none(self):
        config = load_role_config(PROCUREMENT_CONFIG_PATH)
        registry = build_tool_registry("test", config)
        assert resolve_motor_adapter(config, registry) is None

    def test_event_classifier_resolves_when_configured(self, tmp_path):
        path = _write_config(tmp_path)
        config = load_role_config(path)
        fn = resolve_event_classifier(config)
        assert fn is classify_procurement_events

    def test_procurement_yaml_has_no_required_event_classifier(self, tmp_path):
        raw = yaml.safe_load(Path(PROCUREMENT_CONFIG_PATH).read_text(encoding="utf-8"))
        raw.pop("event_classifier", None)
        path = tmp_path / "config.yaml"
        path.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")
        config = load_role_config(str(path))
        assert resolve_event_classifier(config) is None

    def test_non_callable_event_classifier_raises(self, tmp_path):
        path = _write_config(tmp_path, extra={
            "event_classifier": (
                "nowa_roles.procurement.seed_corpus:PROCUREMENT_SEED_EPISODES"
            ),
        })
        config = load_role_config(path)
        with pytest.raises(RoleConfigError, match="not callable"):
            resolve_event_classifier(config)


class TestBuildHelpers:

    def test_build_tool_registry_registers_all_capabilities(self):
        config = load_role_config(PROCUREMENT_CONFIG_PATH)
        registry = build_tool_registry("test", config)
        assert len(registry.list_all()) == 6

    def test_build_seeder_seeds_agent(self):
        config = load_role_config(PROCUREMENT_CONFIG_PATH)
        seeder = build_seeder(config)
        agent = make_test_agent()
        n = seeder.seed_agent(agent)
        assert n == 9


class TestBodyLabSessionWiring:

    def test_lab_session_loads_yaml_capabilities(self):
        session = BodyLabSession(LabSettings(
            seed_intuition=True,
            auto_execute=False,
            scenario=SCENARIO_STOCK_CRITICAL,
            write_status=WRITE_ACCEPTED,
            force_action=ORDER_TOOL,
            clock=datetime(2026, 1, 15, 14, 0, 0),
            sensor_refresh_interval_s=300.0,
            min_ticks_between_sleep=10_000,
        ))
        assert len(session.registry.list_all()) == 6
        write_cap = session.registry.get(ORDER_TOOL)
        assert write_cap is not None
        assert write_cap.requires_approval is False
        assert write_cap.input_schema.get("required") == ["supplier_id", "sku", "qty"]
        assert session.runtime.motor_adapter is None
        assert session.runtime.schema_binder is not None

    def test_auto_execute_clears_write_approval_after_load(self):
        session = BodyLabSession(LabSettings(auto_execute=True))
        write_cap = session.registry.get(ORDER_TOOL)
        assert write_cap is not None
        assert write_cap.requires_approval is False
        stock_cap = session.registry.get("mcp__drivemcp__get_stock_levels")
        assert stock_cap is not None
        assert stock_cap.requires_approval is False
