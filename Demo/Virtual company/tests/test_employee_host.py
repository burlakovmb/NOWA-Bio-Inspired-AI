"""Employee host: compose, poll, mock session, rhythm, routing (spec §8)."""

from __future__ import annotations

import ast
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import yaml

from nowa_body.employee_checkpoint import (
    episode_count,
    mind_path,
    prune_restored_pending,
    save_sidecar,
    sidecar_path,
)
from nowa_body.employee_config import (
    EmployeeConfigError,
    new_employee_config,
    save_employee_config,
)
from nowa_body.employee_session import EmployeeSession, spawn_employee_agent
from nowa_body.gui_configurator_i18n import STRINGS, assert_string_parity
from nowa_body.gui_employee_controller import EmployeeHostController
from nowa_body.hard_constraints import HardConstraintViolation
from nowa_body.mcp_capability import CapabilityRisk, MCPCapability
from nowa_body.mcp_router import MCPRouter
from nowa_body.mock_mcp import MockMCPClient, MockMCPTool
from nowa_body.role_compose import compose_roles
from nowa_body.role_config import RoleConfigError, load_role_config
from nowa_body.sensor_poller import poll_capabilities, poll_sensors

DEMO_SRC = Path(__file__).resolve().parents[1] / "src"
PROCUREMENT = DEMO_SRC / "nowa_roles" / "procurement" / "config.yaml"
GUI_PATH = DEMO_SRC / "nowa_body" / "gui_configurator.py"
CONTROLLER_PATH = DEMO_SRC / "nowa_body" / "gui_configurator_controller.py"
EMPLOYEE_CONTROLLER_PATH = DEMO_SRC / "nowa_body" / "gui_employee_controller.py"

POLL_SENSORS = {
    "mcp__drivemcp__get_stock_levels",
    "mcp__drivemcp__get_suppliers",
    "mcp__drivemcp__get_budget",
    "mcp__drivemcp__get_reorder_points",
    "mcp__drivemcp__get_replenishment_needs",
}


def _cap(
    tool_id: str,
    *,
    server: str,
    risk: str = "read_only",
    poll: bool = False,
    required: list | None = None,
    approval: bool | None = None,
) -> dict:
    schema: dict = {"type": "object"}
    if required:
        schema["required"] = list(required)
        schema["properties"] = {name: {"type": "string"} for name in required}
    is_read = risk == "read_only"
    return {
        "tool_id": tool_id,
        "server_name": server,
        "display_name": tool_id.split("__")[-1],
        "description": "READ" if is_read else "WRITE",
        "risk_level": risk,
        "requires_approval": False if is_read else (True if approval is None else approval),
        "poll": poll,
        "poll_defaults": {},
        "input_schema": schema,
        "domain_tags": ["lab"],
    }


def _write_role(root: Path, role_id: str, capabilities: list, **extra) -> Path:
    folder = Path(root) / role_id
    folder.mkdir(parents=True, exist_ok=True)
    payload = {
        "role_id": role_id,
        "display_name": role_id.replace("_", " ").title(),
        "mcp_capabilities": capabilities,
        "affective_mapping": {},
        "seed_corpus": extra.pop("seed_corpus", []),
    }
    payload.update(extra)
    path = folder / "config.yaml"
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def _mcp(tool_id: str, **kwargs) -> MCPCapability:
    return MCPCapability(
        tool_id=tool_id,
        server_name=kwargs.get("server_name", "alpha"),
        display_name=tool_id,
        description=kwargs.get("description", ""),
        risk_level=kwargs.get("risk_level", CapabilityRisk.READ_ONLY),
        poll=kwargs.get("poll", False),
        poll_defaults=kwargs.get("poll_defaults", {}),
        input_schema=kwargs.get("input_schema", {}),
        requires_approval=kwargs.get("requires_approval", False),
    )


class _CallLog:
    def __init__(self) -> None:
        self.calls: list = []

    def call_tool(self, tool_id: str, arguments=None):
        self.calls.append((tool_id, dict(arguments or {})))
        return {"status": "ok", "tool_id": tool_id}


class FakeClock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now = self.now + timedelta(seconds=seconds)


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


class TestComposeRoles:

    def test_single_id_matches_load_role_config(self):
        loaded = load_role_config(str(PROCUREMENT))
        composed = compose_roles(["procurement"], DEMO_SRC / "nowa_roles")
        assert composed.role_id == loaded.role_id
        assert [cap.tool_id for cap in composed.capabilities] == [
            cap.tool_id for cap in loaded.capabilities
        ]
        assert [cap.poll for cap in composed.capabilities] == [
            cap.poll for cap in loaded.capabilities
        ]
        assert composed.display_name == loaded.display_name
        assert len(composed.seed_corpus) == len(loaded.seed_corpus)

    def test_same_tool_name_different_server_is_two_organs(self, tmp_path):
        _write_role(tmp_path, "alpha_role", [
            _cap("mcp__alpha__get_stock", server="alpha", poll=True),
        ])
        _write_role(tmp_path, "beta_role", [
            _cap("mcp__beta__get_stock", server="beta", poll=True),
        ])
        composed = compose_roles(["alpha_role", "beta_role"], tmp_path)
        ids = [cap.tool_id for cap in composed.capabilities]
        assert ids == ["mcp__alpha__get_stock", "mcp__beta__get_stock"]

    def test_same_tool_id_equivalent_is_one_organ(self, tmp_path):
        cap = _cap("mcp__alpha__get_stock", server="alpha", poll=True)
        _write_role(tmp_path, "one", [cap])
        _write_role(tmp_path, "two", [dict(cap)])
        composed = compose_roles(["one", "two"], tmp_path)
        assert [cap.tool_id for cap in composed.capabilities] == ["mcp__alpha__get_stock"]

    def test_same_tool_id_different_risk_raises(self, tmp_path):
        _write_role(tmp_path, "one", [
            _cap("mcp__alpha__get_stock", server="alpha", risk="read_only"),
        ])
        _write_role(tmp_path, "two", [
            _cap("mcp__alpha__get_stock", server="alpha", risk="low_write", approval=True),
        ])
        with pytest.raises(RoleConfigError, match="compose conflict on tool_id"):
            compose_roles(["one", "two"], tmp_path)

    def test_same_server_id_different_url_raises(self, tmp_path):
        _write_role(
            tmp_path,
            "one",
            [_cap("mcp__alpha__x", server="alpha")],
            mcp_servers=[{
                "server_id": "alpha",
                "transport": "http",
                "url": "http://one.example/mcp",
                "username": "",
                "password": "",
            }],
        )
        _write_role(
            tmp_path,
            "two",
            [_cap("mcp__alpha__y", server="alpha")],
            mcp_servers=[{
                "server_id": "alpha",
                "transport": "http",
                "url": "http://two.example/mcp",
                "username": "",
                "password": "",
            }],
        )
        with pytest.raises(RoleConfigError, match="compose conflict on MCP server"):
            compose_roles(["one", "two"], tmp_path)

    def test_affective_stress_mismatch_is_compose_conflict(self, tmp_path):
        cap = [_cap("mcp__alpha__get_stock", server="alpha", poll=True)]
        _write_role(
            tmp_path, "one", cap,
            affective_mapping={"low": {"valence": -0.5, "arousal": 0.5, "stress": 0.2, "tags": []}},
        )
        _write_role(
            tmp_path, "two", cap,
            affective_mapping={"low": {"valence": -0.5, "arousal": 0.5, "stress": 0.9, "tags": []}},
        )
        with pytest.raises(RoleConfigError, match="compose conflict on affective event"):
            compose_roles(["one", "two"], tmp_path)


class TestSensorPoller:

    def test_only_poll_true_read_is_in_poll_set(self):
        caps = [
            _mcp("mcp__a__on", poll=True),
            _mcp("mcp__a__off", poll=False),
            _mcp(
                "mcp__a__write",
                risk_level=CapabilityRisk.MEDIUM_WRITE,
                poll=True,
                requires_approval=True,
            ),
        ]
        polled = [cap.tool_id for cap in poll_capabilities(caps)]
        assert polled == ["mcp__a__on"]

    def test_write_poll_does_not_load(self, tmp_path):
        path = _write_role(tmp_path, "bad", [
            _cap("mcp__a__create_order", server="a", risk="high_write", poll=True),
        ])
        with pytest.raises(RoleConfigError, match="poll"):
            load_role_config(str(path))

    def test_read_poll_false_is_not_called_even_if_required_empty(self):
        router = _CallLog()
        poll_sensors(
            [
                _mcp("mcp__a__silent", poll=False, input_schema={"type": "object"}),
                _mcp("mcp__a__live", poll=True, input_schema={"type": "object"}),
            ],
            router,
            world_state=None,
            binder=None,
        )
        assert [item[0] for item in router.calls] == ["mcp__a__live"]


class TestRouter:

    def test_alpha_tool_does_not_call_beta(self):
        alpha = MockMCPClient()
        beta = MockMCPClient()
        alpha.register(MockMCPTool("mcp__alpha__x", lambda _p: {"status": "ok", "who": "alpha"}))
        beta.register(MockMCPTool("mcp__beta__x", lambda _p: {"status": "ok", "who": "beta"}))
        router = MCPRouter({"alpha": alpha, "beta": beta})
        result = router.call_tool("mcp__alpha__x", {})
        assert result.get("who") == "alpha"
        assert beta.tools["mcp__beta__x"].call_log == []
        assert len(alpha.tools["mcp__alpha__x"].call_log) == 1


class TestEmployeeSessionMock:

    def _mock_role(self, tmp_path: Path, role_id: str = "stock_clerk") -> str:
        _write_role(
            tmp_path,
            role_id,
            [
                _cap("mcp__lab__get_stock", server="lab", poll=True),
                _cap("mcp__lab__create_order", server="lab", risk="medium_write"),
            ],
            seed_corpus=[{
                "context_tokens": ["stock_low"],
                "action": "mcp__lab__create_order",
                "consequence": "order_placed",
                "reward": 1.0,
            }],
        )
        return role_id

    def test_start_tick_stop_checkpoint_does_not_reseed(self, tmp_path):
        role_id = self._mock_role(tmp_path)
        employees = tmp_path / "nowa_employees"
        config = new_employee_config("buyer_a", "Buyer A", [role_id], seed_intuition=True)
        save_employee_config(config, employees, create_backup=False)
        session = EmployeeSession(config, tmp_path, employees)
        session.start(worker=False)
        assert session.last_start_seeded is True
        for _ in range(3):
            session.tick_once()
        after_first = episode_count(session.agent)
        session.stop()
        mind = mind_path(employees, "buyer_a")
        assert mind.is_file()
        again = EmployeeSession(config, tmp_path, employees)
        again.start(worker=False)
        assert again.last_start_seeded is False
        assert episode_count(again.agent) >= after_first
        again.stop()

    def test_empty_mind_seeds_when_enabled(self, tmp_path):
        role_id = self._mock_role(tmp_path)
        employees = tmp_path / "nowa_employees"
        config = new_employee_config("buyer_b", "Buyer B", [role_id], seed_intuition=True)
        save_employee_config(config, employees, create_backup=False)
        session = EmployeeSession(config, tmp_path, employees)
        session.start(worker=False)
        try:
            assert session.last_start_seeded is True
            assert episode_count(session.agent) >= 1
        finally:
            session.stop()

    def test_sleep_uses_wall_seconds_not_tick_count(self, tmp_path):
        role_id = self._mock_role(tmp_path)
        employees = tmp_path / "nowa_employees"
        config = new_employee_config(
            "sleeper",
            "Sleeper",
            [role_id],
            tick_interval_s=60.0,
            sleep_min_interval_s=3600.0,
            circadian_window=(2, 5),
            fatigue_threshold=0.0,
        )
        save_employee_config(config, employees, create_backup=False)
        clock = FakeClock(datetime(2026, 1, 1, 3, 0, 0))
        session = EmployeeSession(config, tmp_path, employees, clock=clock)
        session.start(worker=False)
        sleeps = 0
        try:
            for _ in range(50):
                result = session.tick_once(now=clock())
                if result.get("slept"):
                    sleeps += 1
                clock.advance(60)
        finally:
            session.stop()
        assert sleeps == 0

    def test_auto_execute_fails_for_high_write(self, tmp_path):
        _write_role(tmp_path, "cashier", [
            _cap("mcp__lab__post_payment", server="lab", risk="high_write"),
        ])
        employees = tmp_path / "nowa_employees"
        config = new_employee_config("risky", "Risky", ["cashier"], auto_execute=True)
        save_employee_config(config, employees, create_backup=False)
        session = EmployeeSession(config, tmp_path, employees)
        with pytest.raises(HardConstraintViolation, match="auto_execute"):
            session.start(worker=False)
        assert session.status == "error"

    def test_write_result_is_logged(self, tmp_path):
        role_id = self._mock_role(tmp_path)
        employees = tmp_path / "nowa_employees"
        config = new_employee_config("buyer_w", "Buyer W", [role_id])
        save_employee_config(config, employees, create_backup=False)
        session = EmployeeSession(config, tmp_path, employees)
        session.start(worker=False)
        try:
            result = session._execute_write("mcp__lab__create_order", {"qty": 1})
            assert result.get("status") == "accepted"
            assert any(
                "write mcp__lab__create_order status=accepted" in line
                for line in session.log
            )
        finally:
            session.stop()

    def test_limit_block_is_logged_and_kept_as_an_alert(self, tmp_path):
        role_id = self._mock_role(tmp_path)
        employees = tmp_path / "nowa_employees"
        config = new_employee_config("buyer_l", "Buyer L", [role_id])
        save_employee_config(config, employees, create_backup=False)
        session = EmployeeSession(config, tmp_path, employees)
        session.start(worker=False)
        try:
            assert session.runtime.limit_notifier == session._notify_limit
            session._notify_limit({
                "limit": "budget", "reason": "nothing_left", "available": 0.0,
                "tool_id": "mcp__lab__create_order", "summary": "create_order qty=5",
            })
            assert any(
                line.startswith("limit budget blocked create_order qty=5 reason=nothing_left")
                for line in session.log
            )
            alerts = session.snapshot()["alerts"]
            assert [a["limit"] for a in alerts] == ["budget"] and alerts[0]["at"]
            host = EmployeeHostController(tmp_path, employees)
            host.sessions["buyer_l"] = session
            assert len(host.row_for("buyer_l")["alerts"]) == 1
            host.clear_alerts("buyer_l")
            assert host.row_for("buyer_l")["alerts"] == []
        finally:
            session.stop()

    def test_alerts_and_open_shortages_survive_a_restart(self, tmp_path):
        role_id = self._mock_role(tmp_path)
        employees = tmp_path / "nowa_employees"
        config = new_employee_config("buyer_p", "Buyer P", [role_id])
        save_employee_config(config, employees, create_backup=False)
        notice = {"limit": "budget", "reason": "nothing_left", "available": 0.0,
                  "tool_id": "mcp__lab__create_order", "summary": "create_order qty=5"}
        session = EmployeeSession(config, tmp_path, employees)
        session.start(worker=False)
        session._notify_limit(dict(notice))
        session.runtime._limit_shortages["budget"] = 0.0
        session.stop()

        host = EmployeeHostController(tmp_path, employees)
        assert [a["limit"] for a in host.row_for("buyer_p")["alerts"]] == ["budget"]

        again = EmployeeSession(config, tmp_path, employees)
        again.start(worker=False)
        try:
            assert [a["summary"] for a in again.snapshot()["alerts"]] == ["create_order qty=5"]
            assert again.runtime._limit_shortages == {"budget": 0.0}
        finally:
            again.stop()

        host.clear_alerts("buyer_p")
        assert host.row_for("buyer_p")["alerts"] == []
        third = EmployeeSession(config, tmp_path, employees)
        third.start(worker=False)
        try:
            assert third.snapshot()["alerts"] == []
        finally:
            third.stop()

    def test_start_drops_sidecar_pending_when_approval_is_off(self, tmp_path):
        _write_role(
            tmp_path,
            "clerk",
            [
                _cap("mcp__lab__get_stock", server="lab", poll=True),
                _cap(
                    "mcp__lab__create_order",
                    server="lab",
                    risk="medium_write",
                    approval=False,
                ),
            ],
            seed_corpus=[{
                "context_tokens": ["stock_low"],
                "action": "mcp__lab__create_order",
                "consequence": "order_placed",
                "reward": 1.0,
            }],
        )
        employees = tmp_path / "nowa_employees"
        config = new_employee_config("buyer_p", "Buyer P", ["clerk"])
        save_employee_config(config, employees, create_backup=False)
        save_sidecar(sidecar_path(employees, "buyer_p"), {
            "pending": [{
                "action_id": "old1",
                "agent_id": "buyer_p",
                "tool_id": "mcp__lab__create_order",
                "tool_params": {"qty": 0.0},
                "requires_approval": True,
            }],
        })
        session = EmployeeSession(config, tmp_path, employees)
        session.start(worker=False)
        try:
            assert session.pending_rows() == []
            assert any("dropped 1 stale pending" in line for line in session.log)
        finally:
            session.stop()


class TestEmployeeController:

    def test_create_and_assign_roles(self, tmp_path):
        _write_role(tmp_path, "clerk", [
            _cap("mcp__lab__get_stock", server="lab", poll=True),
        ])
        host = EmployeeHostController(roles_root=tmp_path)
        host.create_employee("Buyer", "buyer_a", ["clerk"], tick_interval_s=60.0)
        yaml_path = host.employees_root / "buyer_a" / "employee.yaml"
        assert yaml_path.is_file()
        assert "nowa_roles" not in yaml_path.read_text(encoding="utf-8")
        row = host.row_for("buyer_a")
        assert row["status"] == "stopped"
        assert row["role_ids"] == ["clerk"]

    def test_delete_employee_removes_folder(self, tmp_path):
        _write_role(tmp_path, "clerk", [
            _cap("mcp__lab__get_stock", server="lab", poll=True),
        ])
        host = EmployeeHostController(roles_root=tmp_path)
        host.create_employee("Buyer", "buyer_del", ["clerk"])
        folder = host.employees_root / "buyer_del"
        (folder / "mind.pkl").write_bytes(b"x")
        assert folder.is_dir()
        host.delete_employee("buyer_del")
        assert folder.exists() is False
        assert host.list_rows() == []

    def test_missing_role_is_error(self, tmp_path):
        host = EmployeeHostController(roles_root=tmp_path)
        with pytest.raises(Exception):
            host.create_employee("Nobody", "nobody", ["missing"])

    def test_e2_load_rejects_unknown_role(self, tmp_path):
        employees = tmp_path / "nowa_employees" / "ghost"
        employees.mkdir(parents=True)
        (employees / "employee.yaml").write_text(
            yaml.safe_dump({
                "agent_id": "ghost",
                "display_name": "Ghost",
                "role_ids": ["no_such_role"],
                "tick_interval_s": 1,
            }),
            encoding="utf-8",
        )
        with pytest.raises(EmployeeConfigError, match="missing role"):
            from nowa_body.employee_config import load_employee_config
            load_employee_config(str(employees / "employee.yaml"), roles_root=tmp_path)


class TestProcurementPollMigration:

    def test_read_sensors_have_explicit_poll(self):
        config = load_role_config(str(PROCUREMENT))
        by_id = {cap.tool_id: cap for cap in config.capabilities}
        for tool_id in POLL_SENSORS:
            assert tool_id in by_id
            assert by_id[tool_id].poll is True
            assert by_id[tool_id].risk_level is CapabilityRisk.READ_ONLY
        assert by_id["mcp__drivemcp__create_purchase_order"].poll is False
        assert by_id["mcp__drivemcp__create_purchase_order"].requires_approval is False
        assert "mcp__1c__create_purchase_order" not in by_id


class TestI18nAndG1:

    def test_string_parity_and_employee_word(self):
        assert_string_parity()
        assert "сотрудник" in STRINGS["ru"]["emp.heading"].lower() or "сотрудники" in STRINGS["ru"]["emp.heading"].lower()
        for key, value in STRINGS["ru"].items():
            if str(key).startswith("emp."):
                assert "агент" not in str(value).lower()

    def test_gui_files_do_not_construct_capabilities(self):
        for path in (GUI_PATH, CONTROLLER_PATH, EMPLOYEE_CONTROLLER_PATH):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    assert _call_name(node.func) not in {"MCPCapability", "SeedEpisode"}

    def test_dry_run_module_does_not_name_employee_session(self):
        source = GUI_PATH.read_text(encoding="utf-8")
        assert "EmployeeSession" not in source
        lab = (DEMO_SRC / "nowa_body" / "lab_session.py").read_text(encoding="utf-8")
        assert "EmployeeSession" not in lab


def test_spawn_employee_agent_has_no_force_action():
    agent = spawn_employee_agent("unit_test_agent")
    force = getattr(agent, "force_action", "")
    assert force in ("", None)


def test_prune_restored_pending_drops_when_approval_off():
    cap = type("Cap", (), {"tool_id": "mcp__lab__create_order", "requires_approval": False})()
    proposed = type("P", (), {"tool_id": "mcp__lab__create_order"})()
    gate = type("G", (), {"pending_queue": {"a1": type("R", (), {"proposed_action": proposed})()}})()
    dropped = prune_restored_pending(gate, [cap])
    assert dropped == 1
    assert gate.pending_queue == {}


def test_prune_restored_pending_drops_on_fingerprint_change():
    cap = type("Cap", (), {"tool_id": "mcp__lab__create_order", "requires_approval": True})()
    proposed = type("P", (), {"tool_id": "mcp__lab__create_order"})()
    gate = type("G", (), {"pending_queue": {"a1": type("R", (), {"proposed_action": proposed})()}})()
    dropped = prune_restored_pending(
        gate, [cap], role_fingerprint="new", saved_fingerprint="old",
    )
    assert dropped == 1
    assert gate.pending_queue == {}
