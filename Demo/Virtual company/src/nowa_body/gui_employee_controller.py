"""Headless employee host: CRUD, start/stop, approval, rhythm. No Tk."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .employee_checkpoint import (
    delete_memory_files,
    load_sidecar,
    mind_path,
    save_sidecar,
    sidecar_path,
)
from .employee_config import (
    AGENT_ID_RE,
    EmployeeConfig,
    EmployeeConfigError,
    default_employees_root,
    employee_dir,
    employee_yaml_path,
    list_employee_ids,
    load_employee_config,
    new_employee_config,
    save_employee_config,
)
from .employee_session import (
    STATUS_ERROR,
    STATUS_STOPPED,
    EmployeeHostError,
    EmployeeSession,
)
from .gui_configurator_controller import ConfiguratorError, inspect_role_file, list_roles
from .role_compose import compose_roles
from .role_config import RoleConfigError

LIVE_STATUSES = frozenset({
    "starting", "running", "sleeping", "awaiting_approval", "stopping",
})


def suggest_agent_id(display_name: str, taken: Sequence[str]) -> str:
    raw = str(display_name or "").strip().lower()
    chars: List[str] = []
    for ch in raw:
        if ch.isascii() and ch.isalnum():
            chars.append(ch)
        elif ch in " -_":
            chars.append("_")
    slug = "".join(chars).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    if not slug or not slug[0].isalpha():
        slug = ("employee_" + slug).strip("_") or "employee"
    if not re.match(r"^[a-z]", slug):
        slug = "e_" + slug
    slug = slug[:48]
    if len(slug) < 2:
        slug = (slug + "_x")[:48]
    taken_set = set(taken)
    if slug not in taken_set and AGENT_ID_RE.match(slug):
        return slug
    for idx in range(2, 1000):
        suffix = f"_{idx}"
        candidate = (slug[: 48 - len(suffix)] + suffix)
        if candidate not in taken_set and AGENT_ID_RE.match(candidate):
            return candidate
    return slug[:40] + "_new"


class EmployeeHostController:
    """Owns employee.yaml files and live ``EmployeeSession`` objects."""

    def __init__(self, roles_root: Any, employees_root: Optional[Any] = None) -> None:
        self.roles_root = Path(roles_root)
        self.employees_root = Path(
            employees_root if employees_root is not None else default_employees_root(self.roles_root)
        )
        self.sessions: Dict[str, EmployeeSession] = {}

    def list_rows(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for agent_id in list_employee_ids(self.employees_root):
            rows.append(self.row_for(agent_id))
        return rows

    def row_for(self, agent_id: str) -> Dict[str, Any]:
        session = self.sessions.get(agent_id)
        try:
            config = self._load(agent_id)
        except EmployeeConfigError as exc:
            return {
                "agent_id": agent_id,
                "display_name": agent_id,
                "status": STATUS_ERROR,
                "error_text": str(exc),
                "role_ids": [],
                "pending_n": 0,
                "stale_roles": False,
                "tick_interval_s": 1.0,
                "sleep_min_interval_s": 3600.0,
            }
        if session is not None:
            snap = session.snapshot()
            snap["role_ids"] = list(config.role_ids)
            return snap
        mind = mind_path(self.employees_root, agent_id)
        return {
            "agent_id": config.agent_id,
            "display_name": config.display_name,
            "status": STATUS_STOPPED,
            "error_text": "",
            "role_ids": list(config.role_ids),
            "pending_n": 0,
            "stale_roles": False,
            "tick_interval_s": float(config.tick_interval_s),
            "sensor_refresh_interval_s": float(config.sensor_refresh_interval_s),
            "sleep_min_interval_s": float(config.sleep.min_interval_s),
            "circadian_window": list(config.sleep.circadian_window),
            "fatigue_threshold": config.sleep.fatigue_threshold,
            "log": [],
            "alerts": self._stored_alerts(agent_id),
            "pending": [],
            "episodes": 0,
            "checkpoint": (
                __import__("datetime").datetime.fromtimestamp(mind.stat().st_mtime).strftime("%H:%M")
                if mind.is_file() else ""
            ),
            "mcp": [],
            "n_read": 0,
            "n_write": 0,
            "last_sensor": "",
            "tick_index": 0,
        }

    def create_employee(
        self,
        display_name: str,
        agent_id: str,
        role_ids: Sequence[str],
        *,
        tick_interval_s: float = 1.0,
        sensor_refresh_interval_s: float = 30.0,
        sleep_min_interval_s: float = 3600.0,
        circadian_window: Tuple[int, int] = (2, 5),
        fatigue_threshold: Optional[float] = 0.85,
    ) -> EmployeeConfig:
        name = str(display_name or "").strip()
        if not name:
            raise ConfiguratorError("display name is required")
        sid = str(agent_id or "").strip()
        if not AGENT_ID_RE.match(sid):
            raise ConfiguratorError(
                "id must be a slug: letter, then letters, digits or underscore (2–48 chars)"
            )
        if employee_yaml_path(self.employees_root, sid).is_file():
            raise ConfiguratorError(f"employee id already exists: {sid}")
        roles = [str(item).strip() for item in role_ids if str(item).strip()]
        if not roles:
            raise ConfiguratorError("choose at least one role")
        self._assert_roles_assignable(roles)
        config = new_employee_config(
            sid,
            name,
            roles,
            tick_interval_s=tick_interval_s,
            sensor_refresh_interval_s=sensor_refresh_interval_s,
            sleep_min_interval_s=sleep_min_interval_s,
            circadian_window=circadian_window,
            fatigue_threshold=fatigue_threshold,
        )
        save_employee_config(config, self.employees_root, create_backup=False)
        return config

    def load(self, agent_id: str) -> EmployeeConfig:
        return self._load(agent_id)

    def assign_roles(self, agent_id: str, role_ids: Sequence[str]) -> EmployeeConfig:
        session = self.sessions.get(agent_id)
        if session is not None and session.status not in (STATUS_STOPPED, STATUS_ERROR):
            raise ConfiguratorError("role assignment can be changed only while stopped")
        roles = [str(item).strip() for item in role_ids if str(item).strip()]
        if not roles:
            raise ConfiguratorError("choose at least one role")
        self._assert_roles_assignable(roles)
        config = self._load(agent_id)
        config.role_ids = roles
        save_employee_config(config, self.employees_root)
        if session is not None:
            session.config.role_ids = list(roles)
        return config

    def update_rhythm(
        self,
        agent_id: str,
        *,
        tick_interval_s: Optional[float] = None,
        sensor_refresh_interval_s: Optional[float] = None,
        sleep_min_interval_s: Optional[float] = None,
        circadian_window: Optional[Tuple[int, int]] = None,
        fatigue_threshold: Any = ...,
    ) -> EmployeeConfig:
        config = self._load(agent_id)
        if tick_interval_s is not None:
            config.tick_interval_s = float(tick_interval_s)
        if sensor_refresh_interval_s is not None:
            config.sensor_refresh_interval_s = float(sensor_refresh_interval_s)
        if sleep_min_interval_s is not None:
            config.sleep.min_interval_s = float(sleep_min_interval_s)
        if circadian_window is not None:
            config.sleep.circadian_window = (int(circadian_window[0]), int(circadian_window[1]))
        if fatigue_threshold is not ...:
            config.sleep.fatigue_threshold = (
                None if fatigue_threshold is None else float(fatigue_threshold)
            )
        save_employee_config(config, self.employees_root)
        session = self.sessions.get(agent_id)
        if session is not None:
            session.config = config
            session.apply_rhythm(
                tick_interval_s=tick_interval_s,
                sensor_refresh_interval_s=sensor_refresh_interval_s,
                sleep_min_interval_s=sleep_min_interval_s,
                circadian_window=circadian_window,
                fatigue_threshold=fatigue_threshold,
            )
        return config

    def can_start(self, agent_id: str) -> Tuple[bool, str]:
        session = self.sessions.get(agent_id)
        status = session.status if session is not None else STATUS_STOPPED
        if status not in (STATUS_STOPPED, STATUS_ERROR):
            return False, status
        try:
            config = self._load(agent_id)
        except EmployeeConfigError as exc:
            return False, str(exc)
        if not config.role_ids:
            return False, "no roles"
        try:
            compose_roles(config.role_ids, self.roles_root)
        except RoleConfigError as exc:
            return False, str(exc)
        return True, ""

    def start(self, agent_id: str, *, worker: bool = True) -> EmployeeSession:
        ok, reason = self.can_start(agent_id)
        if not ok:
            raise EmployeeHostError(reason or "start is not available")
        config = self._load(agent_id)
        previous = self.sessions.get(agent_id)
        clock = getattr(previous, "_clock", None) if previous is not None else None
        session = EmployeeSession(
            config,
            self.roles_root,
            self.employees_root,
            clock=clock if callable(clock) else None,
        )
        self.sessions[agent_id] = session
        session.start(worker=worker)
        return session

    def stop(self, agent_id: str) -> None:
        session = self.sessions.get(agent_id)
        if session is None:
            return
        session.stop()

    def restart(self, agent_id: str, *, worker: bool = True) -> EmployeeSession:
        self.stop(agent_id)
        return self.start(agent_id, worker=worker)

    def stop_all(self) -> int:
        ids = list(self.sessions.keys())
        for agent_id in ids:
            try:
                self.stop(agent_id)
            except Exception:
                continue
        return len(ids)

    def running_count(self) -> int:
        n = 0
        for session in self.sessions.values():
            if session.status in LIVE_STATUSES:
                n += 1
        return n

    def complete_approval(
        self,
        agent_id: str,
        action_id: str,
        decision: Any,
        *,
        modified_params: Optional[Dict[str, Any]] = None,
        rejection_reason: Optional[str] = None,
    ) -> Any:
        session = self.sessions.get(agent_id)
        if session is None:
            raise EmployeeHostError("employee is not running")
        return session.complete_approval(
            action_id,
            decision,
            modified_params=modified_params,
            rejection_reason=rejection_reason,
        )

    def clear_alerts(self, agent_id: str) -> None:
        """Forget the shown business-limit alerts (the person has seen them)."""
        session = self.sessions.get(agent_id)
        if session is not None:
            session.alerts.clear()
        if session is not None and session.status in LIVE_STATUSES:
            return  # the next Stop saves the cleared list
        path = sidecar_path(self.employees_root, agent_id)
        sidecar = load_sidecar(path)
        if sidecar.get("alerts"):
            sidecar["alerts"] = []
            save_sidecar(path, sidecar)

    def _stored_alerts(self, agent_id: str) -> List[Dict[str, Any]]:
        alerts = load_sidecar(sidecar_path(self.employees_root, agent_id)).get("alerts")
        return [item for item in alerts or [] if isinstance(item, dict)]

    def reset_memory(self, agent_id: str) -> None:
        session = self.sessions.get(agent_id)
        if session is not None and session.status not in (STATUS_STOPPED, STATUS_ERROR):
            raise ConfiguratorError("reset memory only while stopped")
        delete_memory_files(self.employees_root, agent_id)
        if session is not None:
            session.alerts.clear()

    def delete_employee(self, agent_id: str) -> None:
        """Stop if live, then remove the employee folder (yaml, mind, sidecar)."""
        sid = str(agent_id or "").strip()
        if not sid:
            raise ConfiguratorError("employee id is required")
        session = self.sessions.get(sid)
        if session is not None and session.status in LIVE_STATUSES:
            self.stop(sid)
        self.sessions.pop(sid, None)
        folder = employee_dir(self.employees_root, sid)
        if not folder.exists():
            raise ConfiguratorError(f"employee not found: {sid}")
        shutil.rmtree(folder)

    def snapshot(self, agent_id: str) -> Dict[str, Any]:
        return self.row_for(agent_id)

    def assignable_roles(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for item in list_roles(self.roles_root):
            disabled = item.status == "error"
            rows.append({
                "role_id": item.role_id,
                "display_name": item.display_name,
                "status": item.status,
                "disabled": disabled,
            })
        return rows

    def note_role_saved(self, role_id: str) -> None:
        rid = str(role_id or "")
        for session in self.sessions.values():
            if session.status in LIVE_STATUSES and rid in session.config.role_ids:
                session.stale_roles = True

    def _load(self, agent_id: str) -> EmployeeConfig:
        path = employee_yaml_path(self.employees_root, agent_id)
        return load_employee_config(str(path), roles_root=self.roles_root)

    def _assert_roles_assignable(self, role_ids: Sequence[str]) -> None:
        available = {item.role_id: item for item in list_roles(self.roles_root)}
        for role_id in role_ids:
            item = available.get(role_id)
            if item is None:
                path = self.roles_root / role_id / "config.yaml"
                item = inspect_role_file(str(path)) if path.is_file() else None
            if item is None:
                raise ConfiguratorError(f"role not found: {role_id}")
            if item.status == "error":
                raise ConfiguratorError(f"role '{role_id}' is invalid and cannot be assigned")


__all__ = ["EmployeeHostController", "suggest_agent_id"]
