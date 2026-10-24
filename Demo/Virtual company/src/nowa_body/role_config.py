"""Declarative role configuration: capability registry, affective mapping,
seed corpus as data. SchemaBinder poses WRITE arguments from JSON Schema.
Optional ``event_classifier`` is a token overlay, not required.
"""

from __future__ import annotations

import importlib
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml

from ._compat import clamp, ensure_core_src_on_path
from .business_event_encoder import BusinessEventEncoder
from .business_hippocampus_seeder import BusinessHippocampusSeeder, SeedEpisode
from .mcp_capability import CapabilityRisk, MCPCapability
from .motor_adapter import MotorAdapter
from .tool_registry import MCPToolRegistry

ensure_core_src_on_path()
from affective_space import AXES  # noqa: E402

_MAPPING_META = frozenset({"tags", "intensity"})
_DEFAULT_MAPPING_INTENSITY = 0.35


class RoleConfigError(Exception):
    """Raised on malformed config or a failed cross-validation check."""


@dataclass
class RoleConfig:
    role_id: str
    display_name: str
    capabilities: List[MCPCapability]
    affective_mapping: Dict[str, dict]
    seed_corpus: List[SeedEpisode]
    motor_adapter_path: str = ""
    event_classifier_path: str = ""
    source_path: str = ""
    seed_corpus_module: str = ""
    field_aliases: Dict[str, Any] = None
    param_bindings: Dict[str, Any] = None
    mcp_servers: List[Dict[str, Any]] = None
    event_classifier_paths: List[str] = None
    token_rules: Dict[str, Any] = None

    def __post_init__(self) -> None:
        if self.field_aliases is None:
            self.field_aliases = {}
        if self.token_rules is None:
            self.token_rules = {}
        if self.param_bindings is None:
            self.param_bindings = {}
        if self.mcp_servers is None:
            self.mcp_servers = []
        if self.event_classifier_paths is None:
            self.event_classifier_paths = (
                [self.event_classifier_path] if self.event_classifier_path else []
            )


def load_role_config(path: str) -> RoleConfig:
    """
    Parse config.yaml into a RoleConfig. Raises RoleConfigError with a
    specific, actionable message on any malformed field — never falls
    back to a partially-loaded silent default, because a silently
    dropped capability or seed episode is exactly the class of bug this
    project has hit three times already (mismatched ACTION tokens).
    """
    return load_role_config_from_mapping(_read_yaml(path), path)


def load_role_config_from_mapping(raw: Any, path: str) -> RoleConfig:
    """Build a RoleConfig from an in-memory YAML mapping.

    Same parsers and ``validate_role_config`` as ``load_role_config`` —
    the GUI editor uses this so unsaved drafts never construct
    ``MCPCapability`` / ``SeedEpisode`` by hand (spec G1).
    """
    if not isinstance(raw, dict):
        raise RoleConfigError(f"{path} must be a YAML mapping at the top level")

    role_id = _require_str(raw, "role_id", path)
    display_name = str(raw.get("display_name") or role_id)

    caps_raw = raw.get("mcp_capabilities") or []
    if not isinstance(caps_raw, list):
        raise RoleConfigError(f"{path}: mcp_capabilities must be a list")
    capabilities = [
        _parse_capability(entry, idx, path)
        for idx, entry in enumerate(caps_raw)
    ]
    affective_mapping = _parse_affective_mapping(
        raw.get("affective_mapping") or {}, path
    )
    seed_corpus = _load_seed_corpus(raw, path)

    motor_adapter_path = str(raw.get("motor_adapter") or "").strip()
    event_classifier_path = str(raw.get("event_classifier") or "").strip()
    field_aliases = raw.get("field_aliases") if isinstance(raw.get("field_aliases"), dict) else {}
    param_bindings = raw.get("param_bindings") if isinstance(raw.get("param_bindings"), dict) else {}
    token_rules = raw.get("token_rules") if isinstance(raw.get("token_rules"), dict) else {}
    mcp_servers = _parse_mcp_servers(raw.get("mcp_servers"), path)
    if not mcp_servers:
        mcp_servers = _servers_from_capabilities(capabilities)

    module_ref = str(raw.get("seed_corpus_module") or "").strip()
    inline_specified = "seed_corpus" in raw
    if inline_specified:
        module_ref = ""

    config = RoleConfig(
        role_id=role_id,
        display_name=display_name,
        capabilities=capabilities,
        affective_mapping=affective_mapping,
        seed_corpus=seed_corpus,
        motor_adapter_path=motor_adapter_path,
        event_classifier_path=event_classifier_path,
        source_path=path,
        seed_corpus_module=module_ref,
        field_aliases=dict(field_aliases or {}),
        param_bindings=dict(param_bindings or {}),
        mcp_servers=mcp_servers,
        event_classifier_paths=(
            [event_classifier_path] if event_classifier_path else []
        ),
        token_rules=dict(token_rules or {}),
    )
    validate_role_config(config)  # raises on cross-reference mismatches
    return config


def seed_episodes_to_mappings(episodes: List[SeedEpisode]) -> List[dict]:
    """Serialize already-parsed seed episodes back to YAML mappings.

    Used by the GUI migration ``seed_corpus_module → seed_corpus`` so the
    inline copy is produced from objects the loader already built — not
    from a second, divergent constructor path.
    """
    rows: List[dict] = []
    for episode in episodes:
        rows.append({
            "context_tokens": list(episode.context_tokens),
            "action": str(episode.action),
            "consequence": str(episode.consequence),
            "reward": float(episode.reward),
            "intensity": float(episode.intensity),
            "reinforce": bool(episode.reinforce),
        })
    return rows


def _read_yaml(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        raise RoleConfigError(f"role config not found: {path}")
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise RoleConfigError(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise RoleConfigError(f"{path} must be a YAML mapping at the top level")
    return data


def _require_str(raw: dict, key: str, path: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RoleConfigError(
            f"{path}: '{key}' is required and must be a non-empty string"
        )
    return value.strip()


def _as_str_list(value: Any, field_name: str, path: str) -> List[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise RoleConfigError(f"{path}: '{field_name}' must be a list")
    return [str(item) for item in value]


def _as_float(value: Any, field_name: str, path: str, default: float) -> float:
    if value is None:
        return float(default)
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise RoleConfigError(
            f"{path}: '{field_name}' must be a number, got {value!r}"
        ) from exc


def _parse_capability(entry: Any, idx: int, path: str) -> MCPCapability:
    loc = f"{path}:mcp_capabilities[{idx}]"
    if not isinstance(entry, dict):
        raise RoleConfigError(f"{loc} must be a mapping")
    tool_id = _require_str(entry, "tool_id", loc)
    risk_raw = str(entry.get("risk_level") or "").strip()
    try:
        risk_level = CapabilityRisk(risk_raw)
    except ValueError as exc:
        valid = ", ".join(r.value for r in CapabilityRisk)
        raise RoleConfigError(
            f"{path}: mcp_capabilities[{idx}] ('{tool_id}') has invalid "
            f"risk_level '{risk_raw}'. Valid values: {valid}"
        ) from exc

    poll = bool(entry.get("poll", False))
    raw_defaults = entry.get("poll_defaults")
    if raw_defaults is None:
        poll_defaults: Dict[str, Any] = {}
    elif not isinstance(raw_defaults, dict):
        raise RoleConfigError(f"{loc}: poll_defaults must be a mapping")
    else:
        poll_defaults = dict(raw_defaults)
    if poll and risk_level is not CapabilityRisk.READ_ONLY:
        raise RoleConfigError(
            f"{path}: mcp_capabilities[{idx}] ('{tool_id}') has poll: true "
            f"but risk_level is '{risk_level.value}' — only READ_ONLY organs "
            f"may be polled as sensors"
        )

    return MCPCapability(
        tool_id=tool_id,
        server_name=str(entry.get("server_name") or ""),
        display_name=str(entry.get("display_name") or tool_id),
        description=str(entry.get("description") or ""),
        risk_level=risk_level,
        domain_tags=_as_str_list(entry.get("domain_tags"), "domain_tags", loc),
        requires_approval=bool(entry.get("requires_approval", True)),
        input_schema=dict(entry.get("input_schema") or {}),
        output_schema=dict(entry.get("output_schema") or {}),
        action_types=_as_str_list(entry.get("action_types"), "action_types", loc),
        cost_impact_estimate=entry.get("cost_impact_estimate"),
        max_autonomous_value=entry.get("max_autonomous_value"),
        poll=poll,
        poll_defaults=poll_defaults,
    )


def _parse_mcp_servers(raw: Any, path: str) -> List[Dict[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise RoleConfigError(f"{path}: mcp_servers must be a list")
    servers: List[Dict[str, Any]] = []
    for idx, entry in enumerate(raw):
        loc = f"{path}: mcp_servers[{idx}]"
        if not isinstance(entry, dict):
            raise RoleConfigError(f"{loc} must be a mapping")
        server_id = str(entry.get("server_id") or "").strip()
        if not server_id:
            raise RoleConfigError(f"{loc}: server_id is required")
        args = entry.get("args")
        if args is None:
            args_list: List[str] = []
        elif isinstance(args, list):
            args_list = [str(item) for item in args]
        else:
            args_list = [part for part in str(args).split() if part]
        catalog = entry.get("catalog")
        servers.append({
            "server_id": server_id,
            "display_name": str(entry.get("display_name") or server_id),
            "transport": str(entry.get("transport") or "mock"),
            "enabled": bool(entry.get("enabled", True)),
            "url": str(entry.get("url") or ""),
            "username": str(entry.get("username") or ""),
            "password": str(entry.get("password") or ""),
            "command": str(entry.get("command") or ""),
            "args": args_list,
            "timeout": entry.get("timeout"),
            "catalog": list(catalog) if isinstance(catalog, list) else [],
        })
    return servers


def _servers_from_capabilities(capabilities: List[MCPCapability]) -> List[Dict[str, Any]]:
    seen: List[str] = []
    servers: List[Dict[str, Any]] = []
    for cap in capabilities:
        sid = str(cap.server_name or "").strip()
        if not sid or sid in seen:
            continue
        seen.append(sid)
        servers.append({
            "server_id": sid,
            "display_name": sid,
            "transport": "mock",
            "enabled": True,
            "url": "",
            "username": "",
            "password": "",
            "command": "",
            "args": [],
            "timeout": None,
            "catalog": [],
        })
    return servers


def _parse_affective_mapping(raw: Any, path: str) -> Dict[str, dict]:
    if not isinstance(raw, dict):
        raise RoleConfigError(f"{path}: affective_mapping must be a mapping")
    result: Dict[str, dict] = {}
    for event_name, entry in raw.items():
        loc = f"{path}: affective_mapping['{event_name}']"
        if not isinstance(entry, dict):
            raise RoleConfigError(f"{loc} must be a mapping")
        unknown = [str(key) for key in entry if str(key) not in AXES and str(key) not in _MAPPING_META]
        if unknown:
            raise RoleConfigError(f"{loc} unknown key '{unknown[0]}'")
        parsed: Dict[str, Any] = {
            "valence": clamp(_as_float(entry.get("valence"), "valence", loc, 0.0), -1.0, 1.0),
            "arousal": clamp(_as_float(entry.get("arousal"), "arousal", loc, 0.5), -1.0, 1.0),
            "tags": _as_str_list(entry.get("tags"), "tags", loc),
            "intensity": clamp(
                _as_float(entry.get("intensity"), "intensity", loc, _DEFAULT_MAPPING_INTENSITY),
                0.0,
                1.0,
            ),
        }
        for axis in AXES:
            if axis in ("valence", "arousal"):
                continue
            if axis not in entry or entry.get(axis) is None:
                continue
            parsed[axis] = clamp(_as_float(entry.get(axis), axis, loc, 0.0), -1.0, 1.0)
        result[str(event_name)] = parsed
    return result


def _load_seed_corpus(raw: dict, path: str) -> List[SeedEpisode]:
    inline = raw.get("seed_corpus")
    module_ref = raw.get("seed_corpus_module")
    inline_specified = "seed_corpus" in raw
    if inline_specified and module_ref:
        raise RoleConfigError(
            f"{path}: specify either 'seed_corpus' (inline) or "
            f"'seed_corpus_module' (Python reference), not both"
        )
    if module_ref:
        return _load_seed_corpus_from_module(str(module_ref), path)
    if not isinstance(inline, list):
        raise RoleConfigError(f"{path}: 'seed_corpus' must be a list")
    episodes: List[SeedEpisode] = []
    for idx, entry in enumerate(inline):
        loc = f"{path}: seed_corpus[{idx}]"
        if not isinstance(entry, dict):
            raise RoleConfigError(f"{loc} must be a mapping")
        action = str(entry.get("action") or "").strip()
        if not action:
            raise RoleConfigError(
                f"{loc} has no 'action' — every seed "
                f"episode must carry an action label (lesson 2: a "
                f"context-only episode is inert)"
            )
        episodes.append(SeedEpisode(
            context_tokens=_as_str_list(
                entry.get("context_tokens"), "context_tokens", loc
            ),
            action=action,
            consequence=str(entry.get("consequence") or "unspecified_outcome"),
            reward=_as_float(entry.get("reward"), "reward", loc, 0.0),
            intensity=_as_float(entry.get("intensity"), "intensity", loc, 0.5),
            reinforce=bool(entry.get("reinforce", False)),
        ))
    return episodes


def _load_seed_corpus_from_module(ref: str, path: str) -> List[SeedEpisode]:
    """
    ref format: "package.module:ATTRIBUTE_NAME", pointing at an existing
    List[SeedEpisode] (e.g. the pre-existing PROCUREMENT_SEED_EPISODES).
    Backward-compat path for roles migrated before this spec, or for
    corpora too large/generated to hand-author as YAML.
    """
    module_path, _, attr_name = ref.partition(":")
    if not module_path or not attr_name:
        raise RoleConfigError(
            f"{path}: seed_corpus_module '{ref}' must be 'module:ATTRIBUTE'"
        )
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        raise RoleConfigError(f"{path}: cannot import '{module_path}': {exc}") from exc
    corpus = getattr(module, attr_name, None)
    if not isinstance(corpus, list):
        raise RoleConfigError(
            f"{path}: '{ref}' does not resolve to a list of SeedEpisode"
        )
    return list(corpus)


def validate_role_config(config: RoleConfig) -> None:
    """
    Cross-reference checks that catch the exact class of bug this project
    has hit three times: an ACTION label the ActionSelector will never
    see because nothing in the capability registry declares it.

    Raises RoleConfigError with the specific mismatched labels — fails
    loudly at config-load time, not silently at runtime months later.
    """
    known_actions = {"wait_and_monitor"}
    for cap in config.capabilities:
        if cap.tool_id:
            known_actions.add(str(cap.tool_id))
        known_actions.update(cap.action_types or [])

    seed_actions = {ep.action for ep in config.seed_corpus}
    orphan_seed_actions = {
        a for a in seed_actions
        if a not in known_actions
    }
    if orphan_seed_actions:
        raise RoleConfigError(
            f"{config.source_path}: seed_corpus references action(s) "
            f"{sorted(orphan_seed_actions)} that no mcp_capabilities entry "
            f"declares as tool_id (or deprecated action_types). These episodes "
            f"would be inert -- the ActionSelector will never recognise them "
            f"(lesson 2)."
        )

    unseeded = {cap.tool_id for cap in config.capabilities if cap.tool_id not in seed_actions and getattr(cap, "risk_level", None) and str(getattr(cap.risk_level, "value", cap.risk_level)) != "read_only"}
    if unseeded:
        warnings.warn(
            f"{config.source_path}: WRITE tool_id(s) {sorted(unseeded)} have "
            f"no seed_corpus episode -- the agent starts with zero "
            f"professional intuition for them.",
            stacklevel=2,
        )

    for cap in config.capabilities:
        if getattr(cap, "poll", False):
            risk = getattr(cap.risk_level, "value", cap.risk_level)
            if str(risk) != "read_only":
                raise RoleConfigError(
                    f"{config.source_path}: poll: true is not allowed on WRITE "
                    f"tool '{cap.tool_id}'"
                )


def build_tool_registry(agent_id: str, config: RoleConfig) -> MCPToolRegistry:
    registry = MCPToolRegistry(agent_id)
    for capability in config.capabilities:
        registry.register(capability)
    return registry


def build_encoder(config: RoleConfig) -> BusinessEventEncoder:
    return BusinessEventEncoder(
        affective_mapping=config.affective_mapping,
        field_aliases=getattr(config, "field_aliases", None) or {},
        token_rules=getattr(config, "token_rules", None) or {},
    )


def build_seeder(config: RoleConfig) -> BusinessHippocampusSeeder:
    return BusinessHippocampusSeeder(list(config.seed_corpus))


def resolve_motor_adapter(
    config: RoleConfig, tool_registry: MCPToolRegistry
) -> Optional[MotorAdapter]:
    """Deprecated: MotorAdapter is not required. Returns None when unset."""
    if not str(config.motor_adapter_path or "").strip():
        return None
    cls = _import_ref(config.motor_adapter_path, config.source_path, "motor_adapter")
    if not (isinstance(cls, type) and issubclass(cls, MotorAdapter)):
        raise RoleConfigError(
            f"{config.source_path}: motor_adapter '{config.motor_adapter_path}' "
            f"does not resolve to a MotorAdapter subclass"
        )
    return cls(tool_registry)


def resolve_event_classifier(config: RoleConfig) -> Optional[Callable[[str, dict], list]]:
    paths = [
        str(item).strip()
        for item in (getattr(config, "event_classifier_paths", None) or [])
        if str(item).strip()
    ]
    if not paths and str(config.event_classifier_path or "").strip():
        paths = [str(config.event_classifier_path).strip()]
    callables: List[Callable[..., Any]] = []
    for ref in paths:
        fn = _import_ref(ref, config.source_path, "event_classifier")
        if not callable(fn):
            raise RoleConfigError(
                f"{config.source_path}: event_classifier '{ref}' is not callable"
            )
        callables.append(fn)
    if not callables:
        return None
    if len(callables) == 1:
        return callables[0]

    def overlay(tool_id: str, payload: dict) -> list:
        tokens: List[Any] = []
        for fn in callables:
            try:
                result = fn(tool_id, payload)
            except TypeError:
                try:
                    result = fn(tool_id)
                except Exception:
                    continue
            except Exception:
                continue
            if result:
                tokens.extend(list(result))
        return tokens

    return overlay


def _import_ref(ref: str, path: str, field_name: str) -> Any:
    module_path, _, attr_name = ref.partition(":")
    if not module_path or not attr_name:
        raise RoleConfigError(
            f"{path}: '{field_name}' value '{ref}' must be 'module:Attribute'"
        )
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        raise RoleConfigError(f"{path}: cannot import '{module_path}': {exc}") from exc
    obj = getattr(module, attr_name, None)
    if obj is None:
        raise RoleConfigError(
            f"{path}: '{module_path}' has no attribute '{attr_name}'"
        )
    return obj


__all__ = [
    "RoleConfig",
    "RoleConfigError",
    "load_role_config",
    "load_role_config_from_mapping",
    "seed_episodes_to_mappings",
    "validate_role_config",
    "build_tool_registry",
    "build_encoder",
    "build_seeder",
    "resolve_motor_adapter",
    "resolve_event_classifier",
]
