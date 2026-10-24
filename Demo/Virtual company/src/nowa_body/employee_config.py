"""Load / save ``employee.yaml`` — named mind + roles + rhythm, not a role."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import yaml

AGENT_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,47}$")
HISTORY_DIR_NAME = ".history"
MAX_TICK_INTERVAL_S = 86400.0
DEFAULT_TICK_INTERVAL_S = 1.0
DEFAULT_SENSOR_REFRESH_S = 30.0
DEFAULT_SLEEP_MIN_S = 3600.0
DEFAULT_CIRCADIAN = (2, 5)
DEFAULT_FATIGUE = 0.85


class EmployeeConfigError(Exception):
    """Raised on malformed employee.yaml or a failed E1–E4 check."""


@dataclass
class SleepConfig:
    min_interval_s: float = DEFAULT_SLEEP_MIN_S
    circadian_window: Tuple[int, int] = DEFAULT_CIRCADIAN
    fatigue_threshold: Optional[float] = DEFAULT_FATIGUE


@dataclass
class EmployeeConfig:
    agent_id: str
    display_name: str
    role_ids: List[str]
    tick_interval_s: float = DEFAULT_TICK_INTERVAL_S
    sensor_refresh_interval_s: float = DEFAULT_SENSOR_REFRESH_S
    sleep: SleepConfig = field(default_factory=SleepConfig)
    seed_intuition: bool = True
    auto_execute: bool = False
    # Hippocampal activation half-life; None keeps the core default (1 h),
    # which forgets a working day before the nightly sleep can replay it.
    memory_half_life_s: Optional[float] = None
    schema_version: int = 1
    created_at: str = ""
    updated_at: str = ""
    source_path: str = ""


def default_employees_root(roles_root: Any) -> Path:
    """Sibling of ``nowa_roles/`` in production; nested under tmp roots in tests."""
    root = Path(roles_root)
    if root.name == "nowa_roles":
        return root.parent / "nowa_employees"
    return root / "nowa_employees"


def employee_dir(employees_root: Any, agent_id: str) -> Path:
    return Path(employees_root) / str(agent_id)


def employee_yaml_path(employees_root: Any, agent_id: str) -> Path:
    return employee_dir(employees_root, agent_id) / "employee.yaml"


def list_employee_ids(employees_root: Any) -> List[str]:
    root = Path(employees_root)
    if not root.is_dir():
        return []
    ids: List[str] = []
    for child in sorted(root.iterdir()):
        if child.is_dir() and (child / "employee.yaml").is_file():
            ids.append(child.name)
    return ids


def load_employee_config(
    path: str,
    roles_root: Optional[Any] = None,
) -> EmployeeConfig:
    target = Path(path)
    if not target.is_file():
        raise EmployeeConfigError(f"employee config not found: {path}")
    try:
        raw = yaml.safe_load(target.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise EmployeeConfigError(f"invalid YAML in {path}: {exc}") from exc
    config = employee_config_from_mapping(raw, str(target))
    if roles_root is not None:
        _assert_roles_exist(config.role_ids, Path(roles_root), str(target))
    return config


def employee_config_from_mapping(raw: Any, path: str) -> EmployeeConfig:
    if not isinstance(raw, dict):
        raise EmployeeConfigError(f"{path} must be a YAML mapping at the top level")
    agent_id = str(raw.get("agent_id") or "").strip()
    if not AGENT_ID_RE.match(agent_id):
        raise EmployeeConfigError(
            f"{path}: agent_id must match [a-z][a-z0-9_]{{1,47}}, got {agent_id!r}"
        )
    display_name = str(raw.get("display_name") or agent_id).strip() or agent_id
    role_ids = [str(item).strip() for item in (raw.get("role_ids") or []) if str(item).strip()]
    if not role_ids:
        raise EmployeeConfigError(
            f"{path}: role_ids must contain at least one role (E3)"
        )
    tick = _as_positive_float(
        raw.get("tick_interval_s"), "tick_interval_s", path, DEFAULT_TICK_INTERVAL_S,
    )
    if tick > MAX_TICK_INTERVAL_S:
        raise EmployeeConfigError(
            f"{path}: tick_interval_s must be <= {MAX_TICK_INTERVAL_S} (one day)"
        )
    sensor = _as_positive_float(
        raw.get("sensor_refresh_interval_s"),
        "sensor_refresh_interval_s",
        path,
        DEFAULT_SENSOR_REFRESH_S,
    )
    sleep = _parse_sleep(raw.get("sleep") or {}, path)
    half_life_raw = raw.get("memory_half_life_s")
    memory_half_life = (
        None if half_life_raw is None
        else _as_positive_float(half_life_raw, "memory_half_life_s", path, 3600.0)
    )
    created = str(raw.get("created_at") or "").strip()
    updated = str(raw.get("updated_at") or "").strip()
    try:
        schema_version = int(raw.get("schema_version") or 1)
    except (TypeError, ValueError) as exc:
        raise EmployeeConfigError(f"{path}: schema_version must be an integer") from exc
    return EmployeeConfig(
        agent_id=agent_id,
        display_name=display_name,
        role_ids=role_ids,
        tick_interval_s=tick,
        sensor_refresh_interval_s=sensor,
        sleep=sleep,
        seed_intuition=bool(raw.get("seed_intuition", True)),
        auto_execute=bool(raw.get("auto_execute", False)),
        memory_half_life_s=memory_half_life,
        schema_version=schema_version,
        created_at=created,
        updated_at=updated,
        source_path=path,
    )


def save_employee_config(
    config: EmployeeConfig,
    employees_root: Any,
    *,
    create_backup: bool = True,
) -> Path:
    if not AGENT_ID_RE.match(config.agent_id):
        raise EmployeeConfigError(
            f"agent_id must match [a-z][a-z0-9_]{{1,47}}, got {config.agent_id!r}"
        )
    if not config.role_ids:
        raise EmployeeConfigError("role_ids must contain at least one role (E3)")
    folder = employee_dir(employees_root, config.agent_id)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / "employee.yaml"
    now = datetime.now().isoformat(timespec="seconds")
    if not config.created_at:
        config.created_at = now
    config.updated_at = now
    config.source_path = str(target)
    if create_backup and target.exists():
        _backup_existing(target)
    payload = employee_config_to_mapping(config)
    target.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    return target


def employee_config_to_mapping(config: EmployeeConfig) -> Dict[str, Any]:
    sleep = config.sleep
    fatigue = sleep.fatigue_threshold
    return {
        "schema_version": int(config.schema_version or 1),
        "agent_id": config.agent_id,
        "display_name": config.display_name,
        "role_ids": list(config.role_ids),
        "tick_interval_s": float(config.tick_interval_s),
        "sensor_refresh_interval_s": float(config.sensor_refresh_interval_s),
        "sleep": {
            "min_interval_s": float(sleep.min_interval_s),
            "circadian_window": [int(sleep.circadian_window[0]), int(sleep.circadian_window[1])],
            "fatigue_threshold": None if fatigue is None else float(fatigue),
        },
        "seed_intuition": bool(config.seed_intuition),
        "auto_execute": bool(config.auto_execute),
        "memory_half_life_s": (
            None if config.memory_half_life_s is None else float(config.memory_half_life_s)
        ),
        "created_at": config.created_at,
        "updated_at": config.updated_at,
    }


def new_employee_config(
    agent_id: str,
    display_name: str,
    role_ids: Sequence[str],
    *,
    tick_interval_s: float = DEFAULT_TICK_INTERVAL_S,
    sensor_refresh_interval_s: float = DEFAULT_SENSOR_REFRESH_S,
    sleep_min_interval_s: float = DEFAULT_SLEEP_MIN_S,
    circadian_window: Tuple[int, int] = DEFAULT_CIRCADIAN,
    fatigue_threshold: Optional[float] = DEFAULT_FATIGUE,
    seed_intuition: bool = True,
    auto_execute: bool = False,
    memory_half_life_s: Optional[float] = None,
) -> EmployeeConfig:
    now = datetime.now().isoformat(timespec="seconds")
    mapping = {
        "schema_version": 1,
        "agent_id": agent_id,
        "display_name": display_name,
        "role_ids": list(role_ids),
        "tick_interval_s": tick_interval_s,
        "sensor_refresh_interval_s": sensor_refresh_interval_s,
        "sleep": {
            "min_interval_s": sleep_min_interval_s,
            "circadian_window": list(circadian_window),
            "fatigue_threshold": fatigue_threshold,
        },
        "seed_intuition": seed_intuition,
        "auto_execute": auto_execute,
        "memory_half_life_s": memory_half_life_s,
        "created_at": now,
        "updated_at": now,
    }
    return employee_config_from_mapping(mapping, "<new>")


def _assert_roles_exist(role_ids: Sequence[str], roles_root: Path, path: str) -> None:
    for role_id in role_ids:
        config = Path(roles_root) / role_id / "config.yaml"
        if not config.is_file():
            raise EmployeeConfigError(
                f"{path}: role_ids references missing role '{role_id}' (E2)"
            )


def _as_positive_float(value: Any, field_name: str, path: str, default: float) -> float:
    if value is None or value == "":
        result = float(default)
    else:
        try:
            result = float(value)
        except (TypeError, ValueError) as exc:
            raise EmployeeConfigError(
                f"{path}: '{field_name}' must be a number, got {value!r}"
            ) from exc
    if result <= 0:
        raise EmployeeConfigError(f"{path}: '{field_name}' must be > 0")
    return result


def _parse_sleep(raw: Any, path: str) -> SleepConfig:
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise EmployeeConfigError(f"{path}: sleep must be a mapping")
    loc = f"{path}: sleep"
    min_raw = raw.get("min_interval_s", DEFAULT_SLEEP_MIN_S)
    try:
        min_interval = float(min_raw)
    except (TypeError, ValueError) as exc:
        raise EmployeeConfigError(f"{loc}: min_interval_s must be a number") from exc
    if min_interval < 0:
        raise EmployeeConfigError(f"{loc}: min_interval_s must be >= 0")
    window = raw.get("circadian_window", list(DEFAULT_CIRCADIAN))
    if not isinstance(window, (list, tuple)) or len(window) != 2:
        raise EmployeeConfigError(f"{loc}: circadian_window must be two integers 0–23")
    try:
        start = int(window[0])
        end = int(window[1])
    except (TypeError, ValueError) as exc:
        raise EmployeeConfigError(f"{loc}: circadian_window must be two integers 0–23") from exc
    if not (0 <= start <= 23 and 0 <= end <= 23):
        raise EmployeeConfigError(f"{loc}: circadian_window hours must be 0–23")
    fatigue_raw = raw.get("fatigue_threshold", DEFAULT_FATIGUE)
    if fatigue_raw is None:
        fatigue: Optional[float] = None
    else:
        try:
            fatigue = float(fatigue_raw)
        except (TypeError, ValueError) as exc:
            raise EmployeeConfigError(
                f"{loc}: fatigue_threshold must be a number or null"
            ) from exc
    return SleepConfig(
        min_interval_s=min_interval,
        circadian_window=(start, end),
        fatigue_threshold=fatigue,
    )


def _backup_existing(target: Path) -> Path:
    history = target.parent / HISTORY_DIR_NAME
    history.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    backup = history / f"employee_{stamp}.yaml"
    if backup.exists():
        backup = history / f"employee_{stamp}_{datetime.now().microsecond}.yaml"
    backup.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
    return backup


__all__ = [
    "AGENT_ID_RE",
    "EmployeeConfig",
    "EmployeeConfigError",
    "SleepConfig",
    "default_employees_root",
    "employee_config_from_mapping",
    "employee_config_to_mapping",
    "employee_dir",
    "employee_yaml_path",
    "list_employee_ids",
    "load_employee_config",
    "new_employee_config",
    "save_employee_config",
]
