"""Headless lab session for Phase 1 body-layer testing.

The tkinter GUI is a thin view over this object. Tests drive it without
opening a window. The demo role is procurement on MockMCP; this module is
not imported from ``nowa_body.__init__``.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from nowa_body._compat import ensure_core_src_on_path
from nowa_body.approval_gate import ApprovalGate, ApprovalStatus
from nowa_body.hard_constraints import HardConstraintViolation, assert_stage2_invariant
from nowa_body.mcp_capability import CapabilityRisk, MCPCapability
from nowa_body.mock_mcp import MockMCPClient, MockMCPTool
from nowa_body.motor_adapter import ProposedAction
from nowa_body.role_config import (
    build_encoder,
    build_seeder,
    build_tool_registry,
    load_role_config,
    resolve_event_classifier,
)
from nowa_body.runtime import BusinessAgentRuntime
from nowa_body.sleep_scheduler import SleepScheduler
from nowa_body.tool_registry import MCPToolRegistry

STOCK_TOOL = "mcp__drivemcp__get_stock_levels"
SUPPLIER_TOOL = "mcp__drivemcp__get_suppliers"
BUDGET_TOOL = "mcp__drivemcp__get_budget"
NEEDS_TOOL = "mcp__drivemcp__get_replenishment_needs"
ORDER_TOOL = "mcp__drivemcp__create_purchase_order"

SCENARIO_QUIET = "quiet"
SCENARIO_STOCK_CRITICAL = "stock_critical"
SCENARIO_SUPPLIER_DEFAULTED = "supplier_defaulted"
SCENARIOS = (SCENARIO_QUIET, SCENARIO_STOCK_CRITICAL, SCENARIO_SUPPLIER_DEFAULTED)

WRITE_ACCEPTED = "accepted"
WRITE_REJECTED = "rejected"
WRITE_TIMEOUT = "timeout"
WRITE_ERROR = "error"
WRITE_OUTCOMES = (WRITE_ACCEPTED, WRITE_REJECTED, WRITE_TIMEOUT, WRITE_ERROR)

FORCE_AUTO = "auto"
FORCE_ACTIONS = (
    FORCE_AUTO,
    "wait_and_monitor",
    ORDER_TOOL,
)

LAB_ACTIONS = [ORDER_TOOL, "wait_and_monitor"]


def _procurement_role_config_path() -> str:
    """Locate procurement config.yaml next to the role package (not repo root)."""
    import nowa_roles.procurement as procurement_role
    return str(Path(procurement_role.__file__).resolve().parent / "config.yaml")


@dataclass
class LabWorld:
    stock: Dict[str, dict]
    suppliers: Dict[str, dict]
    budget: Dict[str, Any]
    write_status: str = WRITE_ACCEPTED


@dataclass
class LabSettings:
    agent_id: str = "body_lab_buyer"
    seed: int = 42
    seed_intuition: bool = True
    auto_execute: bool = False
    scenario: str = SCENARIO_STOCK_CRITICAL
    write_status: str = WRITE_ACCEPTED
    force_action: str = ORDER_TOOL
    clock: datetime = field(default_factory=lambda: datetime(2026, 1, 1, 14, 0, 0))
    seconds_per_tick: float = 1.0
    sensor_refresh_interval_s: float = 5.0
    min_ticks_between_sleep: int = 8
    circadian_window: tuple = (2, 5)
    fatigue_threshold: float = 0.85
    fatigue_override: Optional[float] = None
    role_config_path: Optional[str] = None


class _FakeHippocampus:
    def __init__(self) -> None:
        self.experiences: List[Any] = []

    def store(self, path, consequence=None, intensity=1.0, reward=0.0, **kwargs):
        exp = SimpleNamespace(
            path=path, consequence=consequence, intensity=intensity, reward=reward
        )
        self.experiences.append(exp)
        return exp

    def reinforce(self, *args, **kwargs):
        return None

    def activate(self, *args, **kwargs):
        return []


class _FakeAffect:
    def __init__(self) -> None:
        self.axes: Dict[str, float] = {}
        self.step_calls: List[Any] = []

    def rank_weights(self) -> Dict[str, float]:
        return {}

    def snapshot(self) -> Dict[str, Any]:
        return {"axes": dict(self.axes)}

    def step(self, inputs=None, **kwargs):
        payload = inputs if inputs is not None else kwargs
        self.step_calls.append(payload)
        if isinstance(payload, dict):
            for key, value in payload.items():
                try:
                    self.axes[key] = float(value)
                except (TypeError, ValueError):
                    continue


class _StubWakefulness:
    def __init__(self) -> None:
        self.process_s = 0.0

    def get_sleep_pressure(self) -> float:
        return float(self.process_s)

    def update_waking(self, elapsed_seconds: Optional[float] = None) -> float:
        dt = 1.0 if elapsed_seconds is None else max(0.0, float(elapsed_seconds))
        self.process_s = min(1.0, self.process_s + dt * 0.0005)
        return self.process_s


class LabStubAgent:
    """Used when NOWA core cannot be imported."""

    def __init__(self, agent_id: str, action: str = "wait_and_monitor") -> None:
        self.agent_id = agent_id
        self.default_action = action
        self.hippocampus = _FakeHippocampus()
        try:
            from affective_space import AffectiveSpace
            self.affective_space = AffectiveSpace()
        except Exception:
            self.affective_space = _FakeAffect()
        self.sleep_calls = 0
        self.sleep_manager = SimpleNamespace(sleep_cycle=self._sleep)
        self.wakefulness = _StubWakefulness()
        self.last_step_events: List[str] = []
        self.selector = SimpleNamespace(actions=list(LAB_ACTIONS))

    def register_action_channel(self, *args, **kwargs) -> None:
        return None

    def set_organ_risk(self, *args, **kwargs) -> None:
        return None

    def _sleep(self) -> None:
        self.sleep_calls += 1
        self.wakefulness.process_s = 0.0

    def step(self, context_events, decision_only=True):
        del decision_only
        self.last_step_events = list(context_events or [])
        return self.default_action


class PressureKnob:
    """Optional fatigue override on top of the agent's WakefulnessState."""

    def __init__(self, inner: Any = None) -> None:
        self._inner = inner
        self.override: Optional[float] = None

    def get_sleep_pressure(self) -> float:
        if self.override is not None:
            return float(self.override)
        inner = self._inner
        if inner is None:
            return 0.0
        fn = getattr(inner, "get_sleep_pressure", None)
        if callable(fn):
            try:
                return float(fn())
            except Exception:
                return 0.0
        value = getattr(inner, "wakefulness", None)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        return 0.0

    def update_waking(self, elapsed_seconds: Optional[float] = None) -> float:
        inner = self._inner
        fn = getattr(inner, "update_waking", None)
        if callable(fn):
            try:
                if elapsed_seconds is None:
                    fn()
                else:
                    fn(elapsed_seconds=float(elapsed_seconds))
            except TypeError:
                try:
                    fn(elapsed_seconds)
                except Exception:
                    pass
            except Exception:
                pass
        return self.get_sleep_pressure()


class GuidedAgent:
    """Proxies a real/stub agent and optionally forces an action_type."""

    def __init__(self, inner: Any) -> None:
        object.__setattr__(self, "_inner", inner)
        object.__setattr__(self, "force_action", "")
        inner_ws = getattr(inner, "wakefulness_state", None)
        if inner_ws is None:
            inner_ws = getattr(inner, "wakefulness", None)
        object.__setattr__(self, "wakefulness_state", PressureKnob(inner_ws))

    def step(self, context_events, decision_only=True):
        forced = str(getattr(self, "force_action", "") or "").strip()
        if forced and forced != FORCE_AUTO:
            return forced
        inner = object.__getattribute__(self, "_inner")
        step_fn = getattr(inner, "step", None)
        if not callable(step_fn):
            return "wait_and_monitor"
        try:
            return step_fn(context_events, decision_only=decision_only)
        except TypeError:
            return step_fn(context_events)

    def __getattr__(self, name: str) -> Any:
        return getattr(object.__getattribute__(self, "_inner"), name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in ("force_action", "wakefulness_state", "_inner", "backend"):
            object.__setattr__(self, name, value)
            return
        setattr(object.__getattribute__(self, "_inner"), name, value)


def _copy_stock(quiet: bool) -> Dict[str, dict]:
    if quiet:
        return {
            "sku_a": {
                "quantity": 80.0,
                "reorder_point": 20.0,
                "below_reorder_point": False,
                "base_demand_per_day": 1.0,
            },
            "sku_b": {
                "quantity": 50.0,
                "reorder_point": 10.0,
                "below_reorder_point": False,
                "base_demand_per_day": 0.4,
            },
        }
    return {
        "sku_a": {
            "quantity": 0.0,
            "reorder_point": 40.0,
            "below_reorder_point": True,
            "base_demand_per_day": 1.5,
        },
        "sku_b": {
            "quantity": 12.0,
            "reorder_point": 30.0,
            "below_reorder_point": True,
            "base_demand_per_day": 0.8,
        },
    }


def _copy_suppliers(*, defaulted: bool = False) -> Dict[str, dict]:
    return {
        "acme": {
            "reliability": 0.95,
            "unit_price": 8.0,
            "lead_time_days": 3,
            "reputation": 0.9,
            "is_defaulted": bool(defaulted),
            "offers": {
                "sku_a": {"unit_price": 8.0, "reliability": 0.95, "lead_time_days": 3},
                "sku_b": {"unit_price": 9.0, "reliability": 0.95, "lead_time_days": 3},
            },
        },
        "cheapco": {
            "reliability": 0.40,
            "unit_price": 3.5,
            "lead_time_days": 12,
            "reputation": 0.35,
            "is_defaulted": False,
            "offers": {
                "sku_a": {"unit_price": 3.5, "reliability": 0.4, "lead_time_days": 12},
                "sku_b": {"unit_price": 3.0, "reliability": 0.4, "lead_time_days": 12},
            },
        },
    }


def replenishment_needs(world: LabWorld) -> Dict[str, Any]:
    """The ERP's own trigger list, as 1C:Drive ``get_replenishment_needs`` returns it.

    Only positions below the reorder point, with a suggested quantity and the
    first supplier that has not defaulted.
    """
    supplier = next(
        (sid for sid, info in world.suppliers.items() if not info.get("is_defaulted")),
        next(iter(world.suppliers), ""),
    )
    items: Dict[str, dict] = {}
    for sku, info in world.stock.items():
        if not info.get("below_reorder_point"):
            continue
        reorder_point = float(info.get("reorder_point") or 0.0)
        quantity = float(info.get("quantity") or 0.0)
        items[sku] = {
            "quantity": quantity,
            "reorder_point": reorder_point,
            "suggested_qty": max(1.0, 2.0 * reorder_point - quantity),
            "default_supplier_id": supplier,
        }
    return {"status": "ok", "needs_replenishment": bool(items), "items": items}


def world_for_scenario(scenario: str, write_status: str = WRITE_ACCEPTED) -> LabWorld:
    name = scenario if scenario in SCENARIOS else SCENARIO_STOCK_CRITICAL
    if name == SCENARIO_QUIET:
        stock = _copy_stock(quiet=True)
        suppliers = _copy_suppliers(defaulted=False)
    elif name == SCENARIO_SUPPLIER_DEFAULTED:
        stock = _copy_stock(quiet=False)
        suppliers = _copy_suppliers(defaulted=True)
    else:
        stock = _copy_stock(quiet=False)
        suppliers = _copy_suppliers(defaulted=False)
    return LabWorld(
        stock=stock,
        suppliers=suppliers,
        budget={"remaining": 8_000.0, "utilization_ratio": 0.35},
        write_status=write_status if write_status in WRITE_OUTCOMES else WRITE_ACCEPTED,
    )


def _create_core_agent(agent_id: str, rng: random.Random) -> Optional[Any]:
    ensure_core_src_on_path()
    try:
        from agent_factory import AgentConfig, AgentFactory
    except Exception:
        return None
    try:
        factory = AgentFactory(AgentConfig(actions=list(LAB_ACTIONS)))
        return factory.spawn_random(rng=rng, agent_id=agent_id)
    except Exception:
        return None


def create_lab_agent(settings: LabSettings) -> GuidedAgent:
    rng = random.Random(int(settings.seed))
    inner = _create_core_agent(settings.agent_id, rng)
    backend = "core" if inner is not None else "stub"
    if inner is None:
        inner = LabStubAgent(settings.agent_id)
    agent = GuidedAgent(inner)
    agent.backend = backend
    agent.force_action = settings.force_action
    agent.wakefulness_state.override = settings.fatigue_override
    return agent


def _event_name(event: Any) -> str:
    if isinstance(event, str):
        return event
    return str(getattr(event, "name", event))


def _path_names(path: Any) -> List[str]:
    signature = getattr(path, "signature", None)
    if callable(signature):
        try:
            return [str(name) for name in signature()]
        except Exception:
            pass
    events = getattr(path, "events", None)
    if events is None:
        return [str(path)]
    return [_event_name(event) for event in events]


class BodyLabSession:
    """One MockMCP + one agent + one runtime. Safe to tick from tests or GUI."""

    def __init__(self, settings: Optional[LabSettings] = None) -> None:
        self.settings = settings or LabSettings()
        self.tick_index = 0
        self.log: List[str] = []
        self.mcp_history: List[dict] = []
        self.last_result: Dict[str, Any] = {}
        self.now = self.settings.clock
        self.world = world_for_scenario(self.settings.scenario, self.settings.write_status)
        self.agent: GuidedAgent = create_lab_agent(self.settings)
        self.client = MockMCPClient()
        self.registry = MCPToolRegistry(self.settings.agent_id)
        self.runtime: Optional[BusinessAgentRuntime] = None
        self._build_runtime()

    def reset(self, settings: Optional[LabSettings] = None) -> None:
        if settings is not None:
            self.settings = settings
        self.tick_index = 0
        self.log = []
        self.mcp_history = []
        self.last_result = {}
        self.now = self.settings.clock
        self.world = world_for_scenario(self.settings.scenario, self.settings.write_status)
        self.agent = create_lab_agent(self.settings)
        self.client = MockMCPClient()
        self.registry = MCPToolRegistry(self.settings.agent_id)
        self._build_runtime()
        self._note("reset")

    def _build_runtime(self) -> None:
        config_path = self.settings.role_config_path or _procurement_role_config_path()
        config = load_role_config(config_path)
        self.registry = build_tool_registry(self.settings.agent_id, config)
        encoder = build_encoder(config)
        seeder = build_seeder(config)
        event_classifier = resolve_event_classifier(config)

        if self.settings.seed_intuition:
            seeder.seed_agent(self.agent)

        # requires_approval override for auto_execute stays a runtime knob,
        # not a config concern — applied AFTER loading, on the specific
        # capability the lab cares about toggling:
        if self.settings.auto_execute:
            write_cap = self.registry.get(ORDER_TOOL)
            if write_cap is not None:
                write_cap.requires_approval = False

        self.client = MockMCPClient()
        self.client.register(MockMCPTool(STOCK_TOOL, lambda _p: {
            "status": "ok", "stock": self.world.stock,
        }))
        self.client.register(MockMCPTool(SUPPLIER_TOOL, lambda _p: {
            "status": "ok", "suppliers": self.world.suppliers,
        }))
        self.client.register(MockMCPTool(BUDGET_TOOL, lambda _p: {
            "status": "ok", **self.world.budget,
        }))
        self.client.register(MockMCPTool(NEEDS_TOOL, lambda _p: replenishment_needs(self.world)))
        self.client.register(MockMCPTool(ORDER_TOOL, self._write_order))

        scheduler = SleepScheduler(
            circadian_window=self.settings.circadian_window,
            fatigue_threshold=self.settings.fatigue_threshold,
            min_ticks_between_sleep=int(self.settings.min_ticks_between_sleep),
        )
        self.runtime = BusinessAgentRuntime(
            agent=self.agent,
            tool_registry=self.registry,
            approval_gate=ApprovalGate(
                mcp_executor=self._execute,
                capability_lookup=self.registry.get,
            ),
            encoder=encoder,
            sleep_scheduler=scheduler,
            sensor_refresh_interval_s=float(self.settings.sensor_refresh_interval_s),
            simulated_tick_seconds=float(self.settings.seconds_per_tick),
            event_classifier=event_classifier,
            param_bindings=getattr(config, "param_bindings", None) or {},
            field_aliases=getattr(config, "field_aliases", None) or {},
        )
        self.agent.force_action = self.settings.force_action
        self.agent.wakefulness_state.override = self.settings.fatigue_override

    def _write_order(self, params: dict) -> dict:
        status = self.world.write_status
        if status == WRITE_TIMEOUT:
            raise TimeoutError("mock MCP write timed out")
        if status == WRITE_ERROR:
            raise RuntimeError("mock MCP write failed")
        return {"status": status, "params": dict(params or {})}

    def _execute(self, tool_id: str, params: dict) -> dict:
        result = self.client.execute(tool_id, params or {})
        self.mcp_history.append(
            {"tool_id": tool_id, "params": dict(params or {}), "result": result}
        )
        return result

    def fetch_sensors(self) -> Dict[str, Any]:
        stock = self._execute(STOCK_TOOL, {})
        suppliers = self._execute(SUPPLIER_TOOL, {})
        budget = self._execute(BUDGET_TOOL, {})
        needs = self._execute(NEEDS_TOOL, {})
        return {
            "agent_id": self.settings.agent_id,
            "stock": self.world.stock,
            "suppliers": self.world.suppliers,
            "budget": self.world.budget,
            "tool_results": {
                STOCK_TOOL: stock,
                SUPPLIER_TOOL: suppliers,
                BUDGET_TOOL: budget,
                NEEDS_TOOL: needs,
            },
        }

    def apply_scenario(self, scenario: str) -> None:
        self.settings.scenario = scenario
        self.world = world_for_scenario(scenario, self.world.write_status)
        if self.runtime is not None:
            self.runtime._last_sensor_refresh = None
        self._note(f"scenario={scenario}")

    def set_write_status(self, status: str) -> None:
        if status not in WRITE_OUTCOMES:
            status = WRITE_ACCEPTED
        self.world.write_status = status
        self.settings.write_status = status
        self._note(f"write_status={status}")

    def set_force_action(self, action: str) -> None:
        self.settings.force_action = action
        self.agent.force_action = action
        self._note(f"force_action={action}")

    def set_clock(self, when: datetime) -> None:
        self.now = when
        self.settings.clock = when
        self._note(f"clock={when.isoformat(timespec='seconds')}")

    def set_fatigue_override(self, value: Optional[float]) -> None:
        self.settings.fatigue_override = value
        self.agent.wakefulness_state.override = value
        self._note(f"fatigue_override={value}")

    def tick_once(self) -> Dict[str, Any]:
        assert self.runtime is not None
        result = self.runtime.tick(self.fetch_sensors, now=self.now)
        self.tick_index += 1
        self.last_result = dict(result)
        self.now = self.now + timedelta(seconds=float(self.settings.seconds_per_tick))
        summary = (
            f"t={self.tick_index} action={result.get('action_type')} "
            f"approval={result.get('approval_status', '-')} "
            f"executed={result.get('executed', False)} "
            f"slept={result.get('slept', False)}"
        )
        if result.get("sleep_reason"):
            summary += f" sleep_reason={result.get('sleep_reason')}"
        self._note(summary)
        return result

    def tick_many(self, n: int) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for _ in range(max(0, int(n))):
            out.append(self.tick_once())
        return out

    def approve(self, action_id: str, decided_by: str = "lab") -> Any:
        assert self.runtime is not None
        record = self.runtime.complete_approval(
            action_id, ApprovalStatus.APPROVED, decided_by=decided_by
        )
        self._note(f"approved {action_id} executed={record.executed}")
        return record

    def reject(self, action_id: str, reason: str = "", decided_by: str = "lab") -> Any:
        assert self.runtime is not None
        record = self.runtime.complete_approval(
            action_id,
            ApprovalStatus.REJECTED,
            decided_by=decided_by,
            rejection_reason=reason or "rejected_in_lab",
        )
        self._note(f"rejected {action_id} reason={record.rejection_reason}")
        return record

    def modify(
        self,
        action_id: str,
        modified_params: Dict[str, Any],
        decided_by: str = "lab",
    ) -> Any:
        assert self.runtime is not None
        record = self.runtime.complete_approval(
            action_id,
            ApprovalStatus.MODIFIED,
            decided_by=decided_by,
            modified_params=modified_params,
        )
        self._note(f"modified {action_id} params={modified_params}")
        return record

    def probe_high_write_bypass(self) -> Dict[str, Any]:
        """B6: HIGH_WRITE cannot skip approval — used as a GUI probe button."""
        cap = MCPCapability(
            tool_id="mcp__1c__pay_invoice",
            server_name="1c_erp",
            display_name="Pay",
            description="",
            risk_level=CapabilityRisk.HIGH_WRITE,
            requires_approval=False,
        )
        invariant_error = ""
        try:
            assert_stage2_invariant(cap)
            invariant_raised = False
        except HardConstraintViolation as exc:
            invariant_raised = True
            invariant_error = str(exc)

        gate_error = ""
        gate_raised = False
        if self.runtime is not None:
            proposed = ProposedAction(
                action_id="probe-high-write",
                agent_id=self.settings.agent_id,
                tool_id="mcp__1c__pay_invoice",
                tool_params={"amount": 9999},
                risk_level=CapabilityRisk.HIGH_WRITE,
                intent_summary="pay_invoice(amount=9999)",
                requires_approval=False,
            )
            try:
                self.runtime.approval_gate.route(proposed)
            except HardConstraintViolation as exc:
                gate_raised = True
                gate_error = str(exc)
        ok = bool(invariant_raised and gate_raised)
        self._note(f"probe_high_write_bypass ok={ok}")
        return {
            "ok": ok,
            "invariant_raised": invariant_raised,
            "gate_raised": gate_raised,
            "invariant_error": invariant_error,
            "gate_error": gate_error,
        }

    def pending_rows(self) -> List[dict]:
        gate = getattr(self.runtime, "approval_gate", None)
        if gate is None:
            return []
        rows = []
        for action_id, record in gate.pending_queue.items():
            proposed = record.proposed_action
            rows.append({
                "action_id": action_id,
                "tool_id": proposed.tool_id,
                "summary": proposed.intent_summary,
                "risk": proposed.risk_level.value,
                "params": dict(proposed.tool_params),
            })
        return rows

    def episode_rows(self, limit: int = 20) -> List[dict]:
        hippo = getattr(self.agent, "hippocampus", None)
        experiences = list(getattr(hippo, "experiences", []) or [])
        rows = []
        for exp in experiences[-limit:]:
            path = getattr(exp, "path", None)
            consequence = getattr(exp, "consequence", None)
            rows.append({
                "path": _path_names(path),
                "consequence": _event_name(consequence) if consequence is not None else "",
                "reward": getattr(exp, "reward", None),
                "intensity": getattr(exp, "intensity", None),
            })
        return rows

    def snapshot(self) -> Dict[str, Any]:
        result = dict(self.last_result or {})
        proposed = result.get("proposed")
        proposed_view = None
        if proposed is not None:
            proposed_view = {
                "action_id": proposed.action_id,
                "tool_id": proposed.tool_id,
                "params": dict(proposed.tool_params),
                "summary": proposed.intent_summary,
                "risk": proposed.risk_level.value,
                "requires_approval": bool(proposed.requires_approval),
            }
        hippo = getattr(self.agent, "hippocampus", None)
        n_episodes = len(getattr(hippo, "experiences", []) or [])
        pressure = self.agent.wakefulness_state.get_sleep_pressure()
        return {
            "tick": self.tick_index,
            "now": self.now.isoformat(timespec="seconds"),
            "hour": self.now.hour,
            "backend": getattr(self.agent, "backend", "unknown"),
            "scenario": self.settings.scenario,
            "write_status": self.world.write_status,
            "force_action": self.agent.force_action,
            "action_type": result.get("action_type"),
            "approval_status": result.get("approval_status"),
            "executed": result.get("executed", False),
            "slept": result.get("slept", False),
            "sleep_reason": result.get("sleep_reason", ""),
            "sensor_refreshed": result.get("sensor_refreshed", False),
            "context_events": list(result.get("context_events") or []),
            "proposed": proposed_view,
            "execution_result": getattr(result.get("record"), "execution_result", None),
            "episodes": n_episodes,
            "pending": self.pending_rows(),
            "sleep_pressure": pressure,
            "mcp_history": list(self.mcp_history[-30:]),
            "log": list(self.log[-80:]),
            "episode_rows": self.episode_rows(),
        }

    def _note(self, message: str) -> None:
        stamp = self.now.strftime("%H:%M:%S")
        self.log.append(f"[{stamp} t={self.tick_index}] {message}")
