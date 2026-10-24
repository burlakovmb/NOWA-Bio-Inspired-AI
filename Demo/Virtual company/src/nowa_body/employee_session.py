"""Live employee session: compose → transports → runtime → cooperative loop.

Not BodyLabSession. Dry-run of a role never constructs this class.
"""

from __future__ import annotations

import hashlib
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, Optional

from nowa_body._compat import ensure_core_src_on_path

from .approval_gate import ApprovalGate, ApprovalStatus
from .employee_checkpoint import (
    CheckpointError,
    apply_world_state_dict,
    episode_count,
    iso_now,
    load_mind,
    load_sidecar,
    memory_is_empty,
    mind_path,
    pending_to_list,
    prune_restored_pending,
    restore_pending,
    save_mind,
    save_sidecar,
    sidecar_path,
    world_state_to_dict,
)
from .employee_config import EmployeeConfig
from .hard_constraints import HardConstraintViolation
from .mcp_capability import CapabilityRisk
from .mcp_router import MCPRouter
from .mock_mcp import MockMCPClient, MockMCPTool
from .role_compose import compose_roles
from .role_config import (
    build_encoder,
    build_seeder,
    build_tool_registry,
    resolve_event_classifier,
    validate_role_config,
)
from .runtime import BusinessAgentRuntime
from .sensor_poller import poll_sensors
from .sleep_scheduler import SleepScheduler, configure_plasticity

STATUS_STOPPED = "stopped"
STATUS_STARTING = "starting"
STATUS_RUNNING = "running"
STATUS_SLEEPING = "sleeping"
STATUS_AWAITING_APPROVAL = "awaiting_approval"
STATUS_STOPPING = "stopping"
STATUS_ERROR = "error"

HIGH_RISKS = frozenset({CapabilityRisk.HIGH_WRITE, CapabilityRisk.IRREVERSIBLE})
TRANSPORT_WAIT_S = 30.0


class EmployeeHostError(Exception):
    """Start/stop failure visible on the employee card."""


def role_fingerprint(roles_root: Any, role_ids: List[str]) -> str:
    parts: List[str] = []
    root = Path(roles_root)
    for role_id in role_ids:
        path = root / role_id / "config.yaml"
        if not path.is_file():
            parts.append(f"{role_id}:missing")
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        stat = path.stat()
        parts.append(f"{role_id}:{stat.st_mtime_ns}:{stat.st_size}:{digest[:16]}")
    return "|".join(parts)


def spawn_employee_agent(agent_id: str, scheduler: Optional[SleepScheduler] = None) -> Any:
    """Core AgentFactory when available; lab stub otherwise. No force_action.

    ``scheduler`` sets the two-tier wake interval right after construction,
    before the first cycle; without it the core default applies until
    ``configure_plasticity`` runs.
    """
    ensure_core_src_on_path()
    try:
        from agent_factory import AgentConfig, AgentFactory

        factory = AgentFactory(AgentConfig(actions=["wait_and_monitor"]))
        agent = factory.spawn_default(agent_id=agent_id)
        if scheduler is not None:
            configure_plasticity(agent, scheduler)
        return agent
    except Exception:
        from .lab_session import LabSettings, create_lab_agent

        settings = LabSettings(agent_id=agent_id, force_action="", seed_intuition=False)
        return create_lab_agent(settings)


class EmployeeSession:
    """One named mind, one composed body, one daemon worker (optional)."""

    def __init__(
        self,
        config: EmployeeConfig,
        roles_root: Any,
        employees_root: Any,
        *,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self.config = config
        self.roles_root = Path(roles_root)
        self.employees_root = Path(employees_root)
        self._clock = clock or datetime.now
        self.status = STATUS_STOPPED
        self.error_text = ""
        self.stale_roles = False
        self.last_start_seeded = False
        self.tick_index = 0
        self.log: Deque[str] = deque(maxlen=200)
        self.snapshots: Deque[Dict[str, Any]] = deque(maxlen=50)
        self.last_sensor_at: Optional[datetime] = None
        self.composed: Optional[Any] = None
        self.agent: Any = None
        self.runtime: Optional[BusinessAgentRuntime] = None
        self.router: Optional[MCPRouter] = None
        self._fingerprint = ""
        self._stop_flag = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        self._save_error = ""

    def _now(self) -> datetime:
        return self._clock()

    @property
    def agent_id(self) -> str:
        return self.config.agent_id

    def roles_are_stale(self) -> bool:
        if not self._fingerprint:
            return False
        return role_fingerprint(self.roles_root, list(self.config.role_ids)) != self._fingerprint

    def start(self, *, worker: bool = True) -> None:
        with self._lock:
            if self.status not in (STATUS_STOPPED, STATUS_ERROR):
                raise EmployeeHostError(f"cannot start from status {self.status}")
            if not self.config.role_ids:
                raise EmployeeHostError("employee has no roles")
            self.status = STATUS_STARTING
            self.error_text = ""
            self._save_error = ""
            self.stale_roles = False
            self._stop_flag.clear()
            try:
                self._assemble()
            except Exception as exc:
                self._teardown_transports()
                self.runtime = None
                self.agent = None
                self.status = STATUS_ERROR
                self.error_text = str(exc)
                raise
            self.status = STATUS_RUNNING
            self._refresh_status_badge()
            self._append_log("started")
        if worker:
            self._thread = threading.Thread(
                target=self._loop,
                name=f"nowa-emp-{self.agent_id}",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            if self.status == STATUS_STOPPED and self.runtime is None:
                return
            self.status = STATUS_STOPPING
            self._stop_flag.set()
        thread = self._thread
        if thread is not None and thread.is_alive() and threading.current_thread() is not thread:
            thread.join(timeout=TRANSPORT_WAIT_S + 5.0)
        self._thread = None
        with self._lock:
            self._checkpoint_and_close()

    def tick_once(self, now: Optional[datetime] = None) -> Dict[str, Any]:
        with self._lock:
            return self._tick_unlocked(now)

    def complete_approval(
        self,
        action_id: str,
        decision: ApprovalStatus,
        decided_by: str = "human",
        rejection_reason: Optional[str] = None,
        modified_params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        with self._lock:
            if self.runtime is None:
                raise EmployeeHostError("employee is not running")
            record = self.runtime.complete_approval(
                action_id,
                decision,
                decided_by=decided_by,
                rejection_reason=rejection_reason,
                modified_params=modified_params,
            )
            self._refresh_status_badge()
            return record

    def apply_rhythm(
        self,
        tick_interval_s: Optional[float] = None,
        sensor_refresh_interval_s: Optional[float] = None,
        sleep_min_interval_s: Optional[float] = None,
        circadian_window: Optional[tuple] = None,
        fatigue_threshold: Any = ...,
    ) -> None:
        with self._lock:
            if tick_interval_s is not None:
                self.config.tick_interval_s = float(tick_interval_s)
            if sensor_refresh_interval_s is not None:
                self.config.sensor_refresh_interval_s = float(sensor_refresh_interval_s)
            if self.runtime is not None:
                self.runtime.sensor_refresh_interval_s = float(
                    self.config.sensor_refresh_interval_s
                )
                self.runtime.simulated_tick_seconds = float(self.config.tick_interval_s)
            scheduler = getattr(self.runtime, "sleep_scheduler", None) if self.runtime else None
            if sleep_min_interval_s is not None:
                self.config.sleep.min_interval_s = float(sleep_min_interval_s)
                if scheduler is not None:
                    scheduler.min_interval_s = float(sleep_min_interval_s)
            if circadian_window is not None:
                self.config.sleep.circadian_window = (
                    int(circadian_window[0]),
                    int(circadian_window[1]),
                )
                if scheduler is not None:
                    scheduler.circadian_window = self.config.sleep.circadian_window
            if fatigue_threshold is not ...:
                self.config.sleep.fatigue_threshold = (
                    None if fatigue_threshold is None else float(fatigue_threshold)
                )
                if scheduler is not None:
                    scheduler.fatigue_threshold = self.config.sleep.fatigue_threshold

    def pending_rows(self) -> List[Dict[str, Any]]:
        runtime = self.runtime
        if runtime is None:
            return []
        return pending_to_list(runtime.approval_gate)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return self._snapshot_unlocked()

    def _assemble(self) -> None:
        composed = compose_roles(self.config.role_ids, self.roles_root)
        validate_role_config(composed)
        if self.config.auto_execute:
            high = [
                cap.tool_id for cap in composed.capabilities
                if cap.risk_level in HIGH_RISKS
            ]
            if high:
                raise HardConstraintViolation(
                    f"auto_execute cannot apply to HIGH_WRITE/IRREVERSIBLE organs: {high}"
                )
            for cap in composed.capabilities:
                if cap.risk_level is not CapabilityRisk.READ_ONLY:
                    cap.requires_approval = False
        self.composed = composed
        self._fingerprint = role_fingerprint(self.roles_root, list(self.config.role_ids))
        self.router = self._open_transports(composed)
        sleep_cfg = self.config.sleep
        scheduler = SleepScheduler(
            circadian_window=sleep_cfg.circadian_window,
            fatigue_threshold=sleep_cfg.fatigue_threshold,
            min_ticks_between_sleep=0,
            min_interval_s=float(sleep_cfg.min_interval_s),
        )
        agent = spawn_employee_agent(self.config.agent_id, scheduler)
        mind = mind_path(self.employees_root, self.config.agent_id)
        self.last_start_seeded = False
        if mind.is_file():
            try:
                load_mind(agent, mind)
            except CheckpointError as exc:
                raise EmployeeHostError(f"broken mind checkpoint: {exc}") from exc
            if memory_is_empty(agent) and self.config.seed_intuition:
                build_seeder(composed).seed_agent(agent)
                self.last_start_seeded = True
        elif self.config.seed_intuition:
            build_seeder(composed).seed_agent(agent)
            self.last_start_seeded = True
        if self.config.memory_half_life_s is not None:
            hippocampus = getattr(agent, "hippocampus", None)
            if hippocampus is not None:
                hippocampus.activation_decay_half_life = float(self.config.memory_half_life_s)
        registry = build_tool_registry(self.config.agent_id, composed)
        encoder = build_encoder(composed)
        classifier = resolve_event_classifier(composed)
        # A checkpoint may carry the interval of an older schedule.
        configure_plasticity(agent, scheduler)
        gate = ApprovalGate(
            mcp_executor=self._execute_write,
            capability_lookup=registry.get,
        )
        runtime = BusinessAgentRuntime(
            agent=agent,
            tool_registry=registry,
            approval_gate=gate,
            encoder=encoder,
            sleep_scheduler=scheduler,
            sensor_refresh_interval_s=float(self.config.sensor_refresh_interval_s),
            simulated_tick_seconds=float(self.config.tick_interval_s),
            event_classifier=classifier,
            param_bindings=dict(composed.param_bindings or {}),
            field_aliases=dict(composed.field_aliases or {}),
        )
        self._wrap_sleep(agent)
        sidecar = load_sidecar(sidecar_path(self.employees_root, self.config.agent_id))
        if sidecar:
            apply_world_state_dict(runtime.world_state, sidecar.get("world_state"))
            restore_pending(gate, sidecar.get("pending") or [])
            dropped = prune_restored_pending(
                gate,
                composed.capabilities,
                role_fingerprint=self._fingerprint,
                saved_fingerprint=str(sidecar.get("role_fingerprint") or ""),
            )
            if dropped:
                self._append_log(f"dropped {dropped} stale pending write(s)")
            sleep_state = sidecar.get("sleep") or {}
            last_iso = sleep_state.get("last_slept_at")
            if last_iso:
                try:
                    scheduler._last_slept_at = datetime.fromisoformat(str(last_iso))
                except ValueError:
                    pass
            origin_iso = sleep_state.get("clock_origin")
            if origin_iso:
                try:
                    scheduler._clock_origin = datetime.fromisoformat(str(origin_iso))
                except ValueError:
                    pass
            try:
                scheduler._ticks_since_last_sleep = int(
                    sleep_state.get("ticks_since_last_sleep") or 0
                )
            except (TypeError, ValueError):
                pass
            try:
                self.tick_index = int(sidecar.get("tick_index") or 0)
            except (TypeError, ValueError):
                self.tick_index = 0
        runtime.register_organs_on_agent()
        self.agent = agent
        self.runtime = runtime

    def _open_transports(self, composed: Any) -> MCPRouter:
        transports: Dict[str, Any] = {}
        for server in list(getattr(composed, "mcp_servers", None) or []):
            if not isinstance(server, dict) or not server.get("enabled", True):
                continue
            sid = str(server.get("server_id") or "").strip()
            if not sid:
                continue
            transport = str(server.get("transport") or "mock").lower()
            if transport == "stdio":
                raise EmployeeHostError("stdio MCP transport is not supported in v1")
            if transport in ("http", "sse"):
                ensure_core_src_on_path()
                from mcp_body.mcp_http import HttpMCPError, mcp_transport_from_server

                try:
                    client = mcp_transport_from_server(server)
                    client.list_tools()
                except (HttpMCPError, ValueError, OSError, TypeError) as exc:
                    raise EmployeeHostError(
                        f"MCP server '{sid}' is unreachable: {exc}"
                    ) from exc
                transports[sid] = client
                continue
            client = self._build_mock_client(composed, sid)
            client.list_tools()
            transports[sid] = client
        return MCPRouter(transports)

    def _build_mock_client(self, composed: Any, server_id: str) -> MockMCPClient:
        client = MockMCPClient()
        for cap in composed.capabilities:
            if str(cap.server_name or "") != server_id:
                continue
            if cap.risk_level is CapabilityRisk.READ_ONLY:
                handler = lambda _p, c=cap: {"status": "ok", "tool_id": c.tool_id}
            else:
                handler = lambda p, c=cap: {
                    "status": "accepted",
                    "params": dict(p or {}),
                    "tool_id": c.tool_id,
                }
            tool = MockMCPTool(cap.tool_id, handler)
            tool.description = cap.description
            tool.input_schema = dict(cap.input_schema or {})
            client.register(tool)
        return client

    def _execute_write(self, tool_id: str, params: dict) -> dict:
        if self.router is None:
            result = {"status": "error", "reason": "no_router"}
            self._append_log(self._format_write_log(tool_id, result))
            return result
        result = self.router.call_tool(tool_id, params)
        if not isinstance(result, dict):
            result = {"status": "unknown", "value": result}
        self._append_log(self._format_write_log(tool_id, result))
        return result

    @staticmethod
    def _format_write_log(tool_id: str, result: Dict[str, Any]) -> str:
        status = str(result.get("status") or "unknown")
        detail = (
            result.get("reason")
            or result.get("document_number")
            or result.get("error")
            or ""
        )
        line = f"write {tool_id} status={status}"
        if detail:
            line += f" {detail}"
        return line

    def _wrap_sleep(self, agent: Any) -> None:
        manager = getattr(agent, "sleep_manager", None)
        sleep_fn = getattr(manager, "sleep_cycle", None)
        if not callable(sleep_fn):
            return

        def wrapped(*args: Any, **kwargs: Any) -> Any:
            previous = self.status
            self.status = STATUS_SLEEPING
            try:
                return sleep_fn(*args, **kwargs)
            finally:
                if not self._stop_flag.is_set() and self.status == STATUS_SLEEPING:
                    self.status = previous

        manager.sleep_cycle = wrapped

    def _sensor_fetcher(self) -> Dict[str, Any]:
        runtime = self.runtime
        composed = self.composed
        router = self.router
        if runtime is None or composed is None or router is None:
            return {"agent_id": self.agent_id, "tool_results": {}}
        observations = poll_sensors(
            composed.capabilities,
            router,
            runtime.world_state,
            runtime.schema_binder,
            agent_id=self.agent_id,
            param_bindings=runtime.param_bindings,
            field_aliases=runtime.field_aliases,
            hippocampus=getattr(self.agent, "hippocampus", None),
            log_warning=self._append_log,
        )
        self.last_sensor_at = self._now()
        return observations

    def _tick_unlocked(self, now: Optional[datetime] = None) -> Dict[str, Any]:
        if self.runtime is None:
            raise EmployeeHostError("employee is not running")
        clock = now or self._now()
        result = self.runtime.tick(self._sensor_fetcher, now=clock)
        self.tick_index += 1
        action = str(result.get("tool_id") or result.get("action_type") or "")
        line = f"t={self.tick_index} action={action}"
        if result.get("slept"):
            line += f" sleep={result.get('sleep_reason') or 'yes'}"
        approval = str(result.get("approval_status") or "")
        if approval == "pending":
            line += " pending"
        elif result.get("executed"):
            line += " executed"
        elif result.get("bind_failed"):
            line += " bind_failed"
        self._append_log(line)
        self.stale_roles = self.roles_are_stale()
        self._refresh_status_badge()
        snap = self._snapshot_unlocked()
        snap["tick_result"] = {
            "tick": self.tick_index,
            "action": action,
            "approval": result.get("approval_status"),
            "slept": bool(result.get("slept")),
            "sensor_refreshed": bool(result.get("sensor_refreshed")),
        }
        self.snapshots.append(snap)
        return result

    def _refresh_status_badge(self) -> None:
        if self.status in (STATUS_STOPPING, STATUS_ERROR, STATUS_STOPPED, STATUS_STARTING):
            return
        if self.status == STATUS_SLEEPING:
            return
        pending = self.pending_rows()
        self.status = STATUS_AWAITING_APPROVAL if pending else STATUS_RUNNING

    def _loop(self) -> None:
        while not self._stop_flag.is_set():
            try:
                self.tick_once()
            except Exception as exc:
                with self._lock:
                    self.status = STATUS_ERROR
                    self.error_text = str(exc)
                    self._append_log(f"error: {exc}")
                break
            interval = max(0.01, float(self.config.tick_interval_s))
            deadline = time.monotonic() + interval
            while time.monotonic() < deadline:
                if self._stop_flag.is_set():
                    break
                time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))

    def _checkpoint_and_close(self) -> None:
        save_failed = ""
        if self.agent is not None:
            try:
                save_mind(self.agent, mind_path(self.employees_root, self.config.agent_id))
            except CheckpointError as exc:
                save_failed = str(exc)
            else:
                sidecar = {
                    "world_state": world_state_to_dict(
                        getattr(self.runtime, "world_state", None)
                    ),
                    "pending": pending_to_list(
                        getattr(self.runtime, "approval_gate", None)
                    ),
                    "sleep": self._sleep_sidecar(),
                    "tick_index": self.tick_index,
                    "stopped_at": iso_now(),
                    "role_fingerprint": self._fingerprint,
                    "role_ids": list(self.config.role_ids),
                }
                try:
                    save_sidecar(
                        sidecar_path(self.employees_root, self.config.agent_id), sidecar
                    )
                except OSError as exc:
                    if not save_failed:
                        save_failed = str(exc)
        self._teardown_transports()
        self.runtime = None
        self.agent = None
        self._save_error = save_failed
        if save_failed:
            self.status = STATUS_ERROR
            self.error_text = f"checkpoint failed: {save_failed}"
            self._append_log(self.error_text)
        else:
            self.status = STATUS_STOPPED
            self.error_text = ""
            self._append_log("stopped")

    def _sleep_sidecar(self) -> Dict[str, Any]:
        scheduler = getattr(self.runtime, "sleep_scheduler", None) if self.runtime else None
        last = getattr(scheduler, "_last_slept_at", None)
        origin = getattr(scheduler, "_clock_origin", None)
        return {
            "last_slept_at": last.isoformat() if isinstance(last, datetime) else None,
            "clock_origin": origin.isoformat() if isinstance(origin, datetime) else None,
            "ticks_since_last_sleep": int(
                getattr(scheduler, "_ticks_since_last_sleep", 0) or 0
            ),
            "min_interval_s": float(self.config.sleep.min_interval_s),
        }

    def _teardown_transports(self) -> None:
        if self.router is not None:
            self.router.close()
        self.router = None

    def _append_log(self, message: str) -> None:
        self.log.append(str(message))

    def _snapshot_unlocked(self) -> Dict[str, Any]:
        pending = self.pending_rows()
        composed = self.composed
        n_read = n_write = 0
        if composed is not None:
            for cap in composed.capabilities:
                if cap.risk_level is CapabilityRisk.READ_ONLY:
                    n_read += 1
                else:
                    n_write += 1
        mcp_rows = []
        for server in list(getattr(composed, "mcp_servers", None) or []):
            if not isinstance(server, dict):
                continue
            sid = str(server.get("server_id") or "")
            ok = bool(self.router and sid in self.router.transports)
            mcp_rows.append({
                "server_id": sid,
                "transport": str(server.get("transport") or "mock"),
                "ok": ok,
            })
        last_sensor = ""
        if self.last_sensor_at is not None:
            last_sensor = self.last_sensor_at.isoformat(timespec="seconds")
        mind = mind_path(self.employees_root, self.config.agent_id)
        checkpoint_when = ""
        if mind.is_file():
            checkpoint_when = datetime.fromtimestamp(mind.stat().st_mtime).strftime("%H:%M")
        episodes = episode_count(self.agent) if self.agent is not None else 0
        return {
            "agent_id": self.config.agent_id,
            "display_name": self.config.display_name,
            "status": self.status,
            "error_text": self.error_text,
            "stale_roles": self.stale_roles or self.roles_are_stale(),
            "role_ids": list(self.config.role_ids),
            "tick_interval_s": float(self.config.tick_interval_s),
            "sensor_refresh_interval_s": float(self.config.sensor_refresh_interval_s),
            "sleep_min_interval_s": float(self.config.sleep.min_interval_s),
            "circadian_window": list(self.config.sleep.circadian_window),
            "fatigue_threshold": self.config.sleep.fatigue_threshold,
            "pending": pending,
            "pending_n": len(pending),
            "tick_index": self.tick_index,
            "log": list(self.log),
            "episodes": episodes,
            "n_read": n_read,
            "n_write": n_write,
            "mcp": mcp_rows,
            "last_sensor": last_sensor,
            "checkpoint": checkpoint_when,
            "save_error": self._save_error,
            "last_start_seeded": self.last_start_seeded,
        }


__all__ = [
    "EmployeeHostError",
    "EmployeeSession",
    "STATUS_AWAITING_APPROVAL",
    "STATUS_ERROR",
    "STATUS_RUNNING",
    "STATUS_SLEEPING",
    "STATUS_STARTING",
    "STATUS_STOPPED",
    "STATUS_STOPPING",
    "role_fingerprint",
    "spawn_employee_agent",
]
