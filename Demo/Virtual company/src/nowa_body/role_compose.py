"""Union of several RoleConfig snapshots into one body for an employee.

Logic lives here, not in the Tk view. One composed config → one registry,
one WorldState, one BusinessAgentRuntime.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from ._compat import ensure_core_src_on_path
from .mcp_capability import MCPCapability
from .role_config import RoleConfig, RoleConfigError, load_role_config, validate_role_config

ensure_core_src_on_path()
from affective_space import AXES  # noqa: E402


def compose_roles(role_ids: Sequence[str], roles_root: Any) -> RoleConfig:
    """Load each id through ``load_role_config`` (G1) and merge.

    A single id is exactly ``load_role_config`` of that role.
    """
    ids = [str(item).strip() for item in role_ids if str(item).strip()]
    if not ids:
        raise RoleConfigError("compose_roles requires at least one role_id")
    root = Path(roles_root)
    if len(ids) == 1:
        return load_role_config(str(_config_path(root, ids[0])))

    loaded: List[RoleConfig] = []
    for role_id in ids:
        loaded.append(load_role_config(str(_config_path(root, role_id))))

    capabilities = _merge_capabilities(loaded)
    servers = _merge_servers(loaded)
    mapping = _merge_affective(loaded)
    aliases, bindings = _merge_lexicon(loaded)
    seeds: List[Any] = []
    for cfg in loaded:
        seeds.extend(list(cfg.seed_corpus or []))
    classifier_paths: List[str] = []
    for cfg in loaded:
        for ref in list(getattr(cfg, "event_classifier_paths", None) or []):
            text = str(ref or "").strip()
            if text and text not in classifier_paths:
                classifier_paths.append(text)
        path = str(cfg.event_classifier_path or "").strip()
        if path and path not in classifier_paths:
            classifier_paths.append(path)

    token_rules: Dict[str, Any] = {}
    for cfg in loaded:
        token_rules.update(dict(getattr(cfg, "token_rules", None) or {}))

    # Limits add up: a call must fit every role's rules.
    limits = [dict(row) for cfg in loaded for row in (getattr(cfg, "business_limits", None) or [])]

    composed = RoleConfig(
        role_id="+".join(ids),
        display_name=" + ".join(cfg.display_name for cfg in loaded),
        capabilities=capabilities,
        affective_mapping=mapping,
        seed_corpus=seeds,
        motor_adapter_path="",
        event_classifier_path=classifier_paths[0] if classifier_paths else "",
        source_path="<composed:" + "+".join(ids) + ">",
        seed_corpus_module="",
        field_aliases=aliases,
        param_bindings=bindings,
        mcp_servers=servers,
        event_classifier_paths=classifier_paths,
        token_rules=token_rules,
        business_limits=limits,
    )
    validate_role_config(composed)
    return composed


def _config_path(roles_root: Path, role_id: str) -> Path:
    path = Path(roles_root) / role_id / "config.yaml"
    if not path.is_file():
        raise RoleConfigError(f"role '{role_id}' not found at {path}")
    return path


def _capability_signature(cap: MCPCapability) -> Tuple[Any, ...]:
    risk = getattr(cap.risk_level, "value", cap.risk_level)
    return (
        str(risk),
        json.dumps(cap.input_schema or {}, sort_keys=True, default=str),
        json.dumps(cap.output_schema or {}, sort_keys=True, default=str),
        bool(cap.requires_approval),
        tuple(str(tag) for tag in (cap.domain_tags or [])),
        bool(getattr(cap, "poll", False)),
        json.dumps(getattr(cap, "poll_defaults", None) or {}, sort_keys=True, default=str),
    )


def _merge_capabilities(loaded: Sequence[RoleConfig]) -> List[MCPCapability]:
    by_id: Dict[str, MCPCapability] = {}
    owner: Dict[str, str] = {}
    order: List[str] = []
    for cfg in loaded:
        for cap in cfg.capabilities:
            tool_id = str(cap.tool_id or "")
            if not tool_id:
                continue
            if tool_id not in by_id:
                by_id[tool_id] = cap
                owner[tool_id] = cfg.role_id
                order.append(tool_id)
                continue
            if _capability_signature(by_id[tool_id]) != _capability_signature(cap):
                raise RoleConfigError(
                    f"compose conflict on tool_id '{tool_id}' between roles "
                    f"'{owner[tool_id]}' and '{cfg.role_id}': capability fields "
                    f"diverge (risk, schema, approval, tags, poll, poll_defaults)"
                )
    return [by_id[tool_id] for tool_id in order]


def _server_identity(server: Dict[str, Any]) -> Tuple[str, str, str]:
    return (
        str(server.get("transport") or "mock"),
        str(server.get("url") or "").strip().rstrip("/"),
        str(server.get("username") or "").strip(),
    )


def _merge_servers(loaded: Sequence[RoleConfig]) -> List[Dict[str, Any]]:
    by_id: Dict[str, Dict[str, Any]] = {}
    owner: Dict[str, str] = {}
    order: List[str] = []
    for cfg in loaded:
        for server in list(getattr(cfg, "mcp_servers", None) or []):
            if not isinstance(server, dict):
                continue
            sid = str(server.get("server_id") or "").strip()
            if not sid:
                continue
            incoming = dict(server)
            if sid not in by_id:
                by_id[sid] = incoming
                owner[sid] = cfg.role_id
                order.append(sid)
                continue
            existing = by_id[sid]
            if _server_identity(existing) != _server_identity(incoming):
                raise RoleConfigError(
                    f"compose conflict on MCP server '{sid}' between roles "
                    f"'{owner[sid]}' and '{cfg.role_id}': transport/url/username differ"
                )
            old_pw = str(existing.get("password") or "")
            new_pw = str(incoming.get("password") or "")
            if old_pw and new_pw and old_pw != new_pw:
                raise RoleConfigError(
                    f"compose conflict on MCP server '{sid}' between roles "
                    f"'{owner[sid]}' and '{cfg.role_id}': passwords differ"
                )
            if new_pw and not old_pw:
                existing["password"] = new_pw
            if incoming.get("enabled", True) or existing.get("enabled", True):
                existing["enabled"] = True
    return [by_id[sid] for sid in order]


def _merge_affective(loaded: Sequence[RoleConfig]) -> Dict[str, dict]:
    mapping: Dict[str, dict] = {}
    owner: Dict[str, str] = {}
    for cfg in loaded:
        for name, entry in (cfg.affective_mapping or {}).items():
            key = str(name)
            payload = dict(entry or {})
            if key not in mapping:
                mapping[key] = payload
                owner[key] = cfg.role_id
                continue
            previous = mapping[key]
            if _affective_entries_conflict(previous, payload):
                raise RoleConfigError(
                    f"compose conflict on affective event '{key}' between roles "
                    f"'{owner[key]}' and '{cfg.role_id}'"
                )
    return mapping


def _affective_entries_conflict(left: Dict[str, Any], right: Dict[str, Any], eps: float = 1e-9) -> bool:
    left_axes = {axis for axis in AXES if axis in left}
    right_axes = {axis for axis in AXES if axis in right}
    if left_axes != right_axes:
        return True
    for axis in left_axes:
        if abs(float(left[axis]) - float(right[axis])) > eps:
            return True
    if abs(float(left.get("intensity", 0.35)) - float(right.get("intensity", 0.35))) > eps:
        return True
    return list(left.get("tags") or []) != list(right.get("tags") or [])


def _merge_lexicon(loaded: Sequence[RoleConfig]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    aliases: Dict[str, Any] = {}
    bindings: Dict[str, Any] = {}
    for cfg in loaded:
        for key, value in (cfg.field_aliases or {}).items():
            if key in aliases and aliases[key] != value:
                warnings.warn(
                    f"compose: field_aliases['{key}'] from role '{cfg.role_id}' "
                    f"overrides an earlier value",
                    stacklevel=3,
                )
            aliases[key] = value
        for key, value in (cfg.param_bindings or {}).items():
            if key in bindings and bindings[key] != value:
                warnings.warn(
                    f"compose: param_bindings['{key}'] from role '{cfg.role_id}' "
                    f"overrides an earlier value",
                    stacklevel=3,
                )
            bindings[key] = value
    return aliases, bindings


__all__ = ["compose_roles"]
