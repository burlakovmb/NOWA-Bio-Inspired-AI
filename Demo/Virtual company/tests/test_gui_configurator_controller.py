"""Role Configurator controller: spec G1–G7 and Definition of Done."""

from __future__ import annotations

import ast
import shutil
import uuid
from pathlib import Path

import pytest
import yaml

from nowa_body.gui_configurator_controller import (
    ADVANCED_AFFECT_AXES_ENABLED,
    AFFECT_PRESETS,
    ConfiguratorError,
    RiskDowngradeRequired,
    RoleConfiguratorController,
    SCENARIO_STOCK_CRITICAL,
    WAIT_AND_MONITOR,
    approval_control_state,
    classify_role_config_message,
    describe_memory_row,
    event_to_tokens,
    inspect_role_file,
    list_roles,
)
from nowa_body.mcp_capability import CapabilityRisk
from nowa_body.role_config import load_role_config, load_role_config_from_mapping
from nowa_roles.procurement import seed_corpus as procurement_seed_module

DEMO_SRC = Path(__file__).resolve().parents[1] / "src"
PROCUREMENT_CONFIG = (
    DEMO_SRC / "nowa_roles" / "procurement" / "config.yaml"
)
CONTROLLER_PATH = DEMO_SRC / "nowa_body" / "gui_configurator_controller.py"
GUI_PATH = DEMO_SRC / "nowa_body" / "gui_configurator.py"


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _assert_no_direct_constructors(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _call_name(node.func)
            assert name not in {"MCPCapability", "SeedEpisode"}, (
                f"{path.name} constructs {name}() — spec G1 forbids bypassing role_config parsers"
            )


def _controller(tmp_path: Path) -> RoleConfiguratorController:
    return RoleConfiguratorController(roles_root=tmp_path)


def _open_procurement_copy(tmp_path: Path) -> RoleConfiguratorController:
    role_dir = tmp_path / "procurement"
    role_dir.mkdir()
    shutil.copy(PROCUREMENT_CONFIG, role_dir / "config.yaml")
    ctrl = _controller(tmp_path)
    ctrl.open_role(str(role_dir / "config.yaml"))
    return ctrl


class TestG1NoDirectConstructors:

    def test_controller_does_not_construct_capability_or_seed(self):
        _assert_no_direct_constructors(CONTROLLER_PATH)

    def test_gui_does_not_construct_capability_or_seed(self):
        _assert_no_direct_constructors(GUI_PATH)

    def test_employee_host_controller_does_not_construct_capability_or_seed(self):
        employee_path = DEMO_SRC / "nowa_body" / "gui_employee_controller.py"
        _assert_no_direct_constructors(employee_path)

    def test_draft_round_trips_through_role_config_parsers(self, tmp_path):
        ctrl = _controller(tmp_path)
        ctrl.new_role("Lab")
        loaded = load_role_config_from_mapping(ctrl.draft(), "<draft>")
        assert loaded.display_name == "Lab"
        uuid.UUID(loaded.role_id)
        assert loaded.capabilities == []

    def test_new_role_assigns_unique_guids(self, tmp_path):
        ctrl = _controller(tmp_path)
        first = ctrl.new_role("Buyer")["role_id"]
        ctrl.save(confirmed=True)
        second = ctrl.new_role("Buyer")["role_id"]
        uuid.UUID(first)
        uuid.UUID(second)
        assert first != second

    def test_new_role_requires_display_name(self, tmp_path):
        ctrl = _controller(tmp_path)
        with pytest.raises(ConfiguratorError, match="display name"):
            ctrl.new_role("   ")


class TestRoleList:

    def test_list_roles_uses_real_load_and_marks_procurement_valid(self):
        items = list_roles(DEMO_SRC / "nowa_roles")
        by_id = {item.role_id: item for item in items}
        assert "procurement" in by_id
        item = by_id["procurement"]
        assert item.status == "valid"
        assert item.n_tools == 6
        assert item.n_lessons == 9

    def test_broken_config_is_error_badge(self, tmp_path):
        role_dir = tmp_path / "broken"
        role_dir.mkdir()
        (role_dir / "config.yaml").write_text("role_id: [unterminated", encoding="utf-8")
        item = inspect_role_file(str(role_dir / "config.yaml"))
        assert item.status == "error"
        assert item.status_detail


class TestToolsAndG2G4:

    def test_approval_locked_on_for_high_and_irreversible(self):
        high = approval_control_state(CapabilityRisk.HIGH_WRITE)
        irr = approval_control_state(CapabilityRisk.IRREVERSIBLE)
        read = approval_control_state(CapabilityRisk.READ_ONLY)
        medium = approval_control_state(CapabilityRisk.MEDIUM_WRITE)
        assert high["checked"] is True and high["disabled"] is True
        assert irr["locked_on"] is True
        assert read["checked"] is False and read["disabled"] is True
        assert medium["disabled"] is False

    def test_set_requires_approval_false_unreachable_for_irreversible(self, tmp_path):
        ctrl = _controller(tmp_path)
        ctrl.new_role("lab_role")
        ctrl.add_manual_tool("mcp__1c__delete_supplier", included=True)
        cap = [row for row in ctrl.tool_rows() if row["tool_id"].endswith("delete_supplier")][0]
        assert cap["risk_level"] == CapabilityRisk.IRREVERSIBLE.value
        applied = ctrl.set_requires_approval("mcp__1c__delete_supplier", False)
        assert applied is False
        assert ctrl._cap("mcp__1c__delete_supplier")["requires_approval"] is True

    def test_read_only_approval_cannot_be_turned_on(self, tmp_path):
        ctrl = _controller(tmp_path)
        ctrl.new_role("lab_role")
        ctrl.add_manual_tool("mcp__1c__get_stock_levels", included=True)
        applied = ctrl.set_requires_approval("mcp__1c__get_stock_levels", True)
        assert applied is False
        assert ctrl._cap("mcp__1c__get_stock_levels")["requires_approval"] is False

    def test_poll_enabled_on_read_disabled_on_write(self, tmp_path):
        ctrl = _controller(tmp_path)
        ctrl.new_role("lab_role")
        ctrl.add_manual_tool("mcp__1c__get_stock_levels", included=True)
        ctrl.add_manual_tool("mcp__1c__create_purchase_order", included=True)
        rows = {row["tool_id"]: row for row in ctrl.tool_rows()}
        read = rows["mcp__1c__get_stock_levels"]
        write = rows["mcp__1c__create_purchase_order"]
        assert read["poll_enabled"] is True
        assert read["poll"] is False
        assert write["poll_enabled"] is False
        assert ctrl.set_tool_poll("mcp__1c__get_stock_levels", True) is True
        assert ctrl._cap("mcp__1c__get_stock_levels")["poll"] is True
        assert ctrl.set_tool_poll("mcp__1c__create_purchase_order", True) is False
        assert ctrl._cap("mcp__1c__create_purchase_order")["poll"] is False

    def test_risk_downgrade_rejects_empty_justification(self, tmp_path):
        ctrl = _controller(tmp_path)
        ctrl.new_role("lab_role")
        ctrl.add_manual_tool("mcp__1c__delete_supplier", included=True)
        with pytest.raises(RiskDowngradeRequired):
            ctrl.set_tool_risk("mcp__1c__delete_supplier", "low_write")
        with pytest.raises(RiskDowngradeRequired):
            ctrl.set_tool_risk("mcp__1c__delete_supplier", "low_write", justification="   ")
        ctrl.set_tool_risk(
            "mcp__1c__delete_supplier", "low_write", justification="lab mock only",
        )
        desc = ctrl._cap("mcp__1c__delete_supplier")["description"]
        assert "[risk downgrade justified: lab mock only]" in desc

    def test_discovered_tool_risk_is_not_auto_confirmed(self, tmp_path):
        ctrl = _controller(tmp_path)
        ctrl.new_role("lab_role")
        ctrl.discover_mock_tools()
        ctrl.set_tool_included("mcp__1c__create_purchase_order", True)
        row = [r for r in ctrl.tool_rows() if r["tool_id"].endswith("create_purchase_order")][0]
        assert row["risk_confirmed"] is False
        assert row["heuristic_risk"]
        ctrl.confirm_heuristic_risk("mcp__1c__create_purchase_order")
        assert ctrl.is_risk_confirmed("mcp__1c__create_purchase_order") is True


class TestVocabularyAndAffect:

    def test_vocab_crud_and_write_channel_warning(self, tmp_path):
        ctrl = _controller(tmp_path)
        ctrl.new_role("lab_role")
        ctrl.add_action_type("brand_new_move", "Brand new", "needs a WRITE organ")
        rows = {row["action_type"]: row for row in ctrl.vocabulary_rows()}
        assert rows["brand_new_move"]["needs_motor_adapter"] is True
        ctrl.add_manual_tool("mcp__1c__create_purchase_order", included=True)
        ctrl.add_action_type(
            "mcp__1c__create_purchase_order",
            "Create purchase order",
            "WRITE organ",
        )
        rows = {row["action_type"]: row for row in ctrl.vocabulary_rows()}
        assert rows["mcp__1c__create_purchase_order"]["needs_motor_adapter"] is False

    def test_write_organ_choices_exclude_already_added(self, tmp_path):
        ctrl = _controller(tmp_path)
        ctrl.new_role("Buyer")
        ctrl.add_manual_tool("mcp__1c__create_purchase_order", included=True)
        codes = {row["action_type"] for row in ctrl.motor_adapter_decision_choices()}
        assert "mcp__1c__create_purchase_order" in codes
        assert WAIT_AND_MONITOR not in codes
        added = ctrl.add_action_type(
            action_type="mcp__1c__create_purchase_order",
            display_name="Create purchase order",
            description="Place an order",
        )
        assert added["action_type"] == "mcp__1c__create_purchase_order"
        codes = {row["action_type"] for row in ctrl.motor_adapter_decision_choices()}
        assert "mcp__1c__create_purchase_order" not in codes
        rows = {row["action_type"]: row for row in ctrl.vocabulary_rows()}
        assert rows["mcp__1c__create_purchase_order"]["needs_motor_adapter"] is False

    def test_used_in_tools_does_not_repeat_same_write_organ(self, tmp_path):
        ctrl = _controller(tmp_path)
        ctrl.new_role("Lab")
        ctrl.add_manual_tool("mcp__drivemcp__create_purchase_order", included=True)
        ctrl.set_tool_action_types(
            "mcp__drivemcp__create_purchase_order",
            ["mcp__drivemcp__create_purchase_order"],
        )
        rows = {row["action_type"]: row for row in ctrl.vocabulary_rows()}
        used = rows["mcp__drivemcp__create_purchase_order"]["used_in_tools"]
        assert used == ["mcp__drivemcp__create_purchase_order"]

    def test_add_decision_from_display_name_generates_unique_id(self, tmp_path):
        ctrl = _controller(tmp_path)
        ctrl.new_role("lab_role")
        first = ctrl.add_action_type(display_name="Срочный дозаказ", description="Быстрый поставщик")
        second = ctrl.add_action_type(display_name="Срочный дозаказ", description="Ещё раз")
        assert first["display_name"] == "Срочный дозаказ"
        assert first["action_type"].startswith("decision_")
        assert first["action_type"] != second["action_type"]
        uuid.UUID(first["action_type"].removeprefix("decision_"))

    def test_affect_presets_and_extra_axes(self, tmp_path):
        assert ADVANCED_AFFECT_AXES_ENABLED is True
        ctrl = _controller(tmp_path)
        ctrl.new_role("lab_role")
        assert ctrl.advanced_affect_visible is True
        ctrl.upsert_affective_event("stock_critical_low", 0.0, 0.5, ["procurement"])
        ctrl.apply_affect_preset("stock_critical_low", "crisis")
        data = ctrl.get_affective_event("stock_critical_low")
        assert data["valence"] == AFFECT_PRESETS["crisis"]["valence"]
        assert data["arousal"] == AFFECT_PRESETS["crisis"]["arousal"]
        assert data["stress"] == AFFECT_PRESETS["crisis"]["stress"]
        assert data["trust"] == pytest.approx(-0.15)
        assert data["tags"] == ["procurement"]
        ctrl.upsert_affective_event("stock_critical_low", 0.1, 0.2, ["procurement"])
        kept = ctrl.get_affective_event("stock_critical_low")
        assert kept["trust"] == pytest.approx(-0.15)
        preview = ctrl.preview_affective_event("stock_critical_low")
        routine = _controller(tmp_path)
        routine.new_role("other")
        routine.upsert_affective_event("quiet", 0.0, 0.1, [])
        routine.apply_affect_preset("quiet", "routine")
        prev_r = routine.preview_affective_event("quiet")
        assert preview["rank_weights"]["caution"] > prev_r["rank_weights"]["caution"]
        tokens = event_to_tokens("stock_critical_low", {"valence": -0.7, "arousal": 0.8, "tags": ["x"]})
        assert tokens == ["event:stock_critical_low", "valence:very_negative", "arousal:high", "domain:x"]

    def test_presets_are_global_across_roles(self, tmp_path):
        a = _controller(tmp_path)
        a.new_role("role_a")
        a.upsert_affective_event("e1", 0.2, 0.3, ["keep"])
        a.save_affect_preset("month_close", "Month close", "Закрытие месяца", event_name="e1")
        b = RoleConfiguratorController(roles_root=tmp_path)
        b.new_role("role_b")
        ids = {row["id"] for row in b.list_visible_affect_presets()}
        assert "month_close" in ids
        assert "crisis" in ids
        b.upsert_affective_event("other", 0.0, 0.5, ["untouched"])
        b.apply_affect_preset("other", "month_close")
        data = b.get_affective_event("other")
        assert data["valence"] == pytest.approx(0.2)
        assert data["tags"] == ["untouched"]
        catalog = tmp_path / "nowa_affect_presets.yaml"
        assert catalog.is_file()
        before = catalog.read_text(encoding="utf-8")
        role_file = tmp_path / str(a._draft["role_id"]) / "config.yaml"
        a._write_to_path(str(role_file), False)
        assert catalog.read_text(encoding="utf-8") == before
        assert "month_close" not in role_file.read_text(encoding="utf-8")

    def test_action_and_outcome_labels_follow_language(self, tmp_path):
        ctrl = _controller(tmp_path)
        ctrl.new_role("Lab")
        assert ctrl.action_display_name("urgent_reorder", "en") == "Urgent reorder"
        assert ctrl.action_display_name("urgent_reorder", "ru") == "Срочный дозаказ"
        assert "wait_and_monitor" not in ctrl.action_display_name(WAIT_AND_MONITOR, "ru")
        assert "наблюдать" in ctrl.action_display_name(WAIT_AND_MONITOR, "ru")
        assert ctrl.outcome_display_name("stock_restored", "ru") == "запас восстановлен"
        assert ctrl.outcome_code_from_label("запас восстановлен", "ru") == "stock_restored"
        assert ctrl.tag_display_name("procurement", "ru") == "закупки"

    def test_event_display_name_follows_language(self, tmp_path):
        ctrl = _open_procurement_copy(tmp_path)
        assert ctrl.affective_events() == [
            "stock_ok",
            "stock_low_covered",
            "stock_critical_low",
            "supplier_defaulted",
            "deal_closed_favorable",
            "budget_exceeded",
            "Заказ пришел вовремя",
        ]
        ru = ctrl.event_display_name("deal_closed_favorable", "ru")
        en = ctrl.event_display_name("deal_closed_favorable", "en")
        assert "deal_closed_favorable" not in ru
        assert "deal_closed_favorable" not in en
        assert "выгодных" in ru
        assert "favorable" in en
        assert "бюджет превышен" == ctrl.event_display_name("budget_exceeded", "ru")


class TestSeedWizardG5:

    def _role_with_tool_and_event(self, tmp_path: Path) -> RoleConfiguratorController:
        ctrl = _controller(tmp_path)
        ctrl.new_role("lab_role")
        ctrl.add_manual_tool("mcp__1c__create_purchase_order", included=True)
        ctrl.add_action_type("urgent_reorder", "Urgent reorder", "fast")
        ctrl.set_tool_action_types("mcp__1c__create_purchase_order", ["urgent_reorder"])
        ctrl.upsert_affective_event(
            "stock_critical_low", -0.7, 0.8, ["procurement", "urgency"],
        )
        return ctrl

    def test_wizard_builds_valid_seed_via_parser(self, tmp_path):
        ctrl = self._role_with_tool_and_event(tmp_path)
        mapping = ctrl.add_lesson_from_wizard(
            ["stock_critical_low"],
            "urgent_reorder",
            "stock_restored",
            8,
            True,
        )
        assert "event:stock_critical_low" in mapping["context_tokens"]
        assert "valence:very_negative" in mapping["context_tokens"]
        assert "arousal:high" in mapping["context_tokens"]
        assert "domain:procurement" in mapping["context_tokens"]
        assert mapping["reward"] == pytest.approx(0.8)
        assert mapping["intensity"] == pytest.approx(0.8)
        assert mapping["reinforce"] is True
        loaded = load_role_config_from_mapping(ctrl.draft(), "<draft>")
        assert loaded.seed_corpus[0].action == "urgent_reorder"

    def test_narrative_hides_raw_seed_fields(self, tmp_path):
        ctrl = self._role_with_tool_and_event(tmp_path)
        mapping = ctrl.add_lesson_from_wizard(
            ["stock_critical_low"], "urgent_reorder", "stock_restored", 8, True,
        )
        story = ctrl.lesson_narrative(mapping, technical=False)
        assert "context_tokens" not in story
        assert "reward=" not in story
        assert "intensity=" not in story
        assert "Urgent reorder" in story or "urgent_reorder" in story
        assert "stock_critical_low" not in story
        assert "stock_restored" not in story
        tech = ctrl.lesson_narrative(mapping, technical=True)
        assert "context_tokens" in tech
        assert "reward=" in tech
        ru = ctrl.lesson_narrative(mapping, technical=False, lang="ru")
        assert "Когда" in ru
        assert "запас критически низкий" in ru
        assert "Срочный дозаказ" in ru
        assert "запас восстановлен" in ru
        assert "да" in ru
        assert "When" not in ru
        assert ru != story

    def test_seed_module_is_read_only_until_migrate(self, tmp_path):
        role_dir = tmp_path / "modulerole"
        role_dir.mkdir()
        raw = yaml.safe_load(PROCUREMENT_CONFIG.read_text(encoding="utf-8"))
        raw.pop("seed_corpus", None)
        raw["seed_corpus_module"] = (
            "nowa_roles.procurement.seed_corpus:PROCUREMENT_SEED_EPISODES"
        )
        path = role_dir / "config.yaml"
        path.write_text(
            yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        ctrl = _controller(tmp_path)
        ctrl.open_role(str(path))
        assert ctrl.uses_seed_module is True
        with pytest.raises(ConfiguratorError, match="read-only"):
            ctrl.add_lesson_from_wizard(
                ["stock_critical_low"], WAIT_AND_MONITOR, "ok", 1, False,
            )
        rows = ctrl.migrate_seed_module_to_inline(write_file=True)
        assert len(rows) == 8
        assert ctrl.uses_seed_module is False
        payload = yaml.safe_load(Path(ctrl.path).read_text(encoding="utf-8"))
        assert "seed_corpus" in payload
        assert "seed_corpus_module" not in payload
        assert Path(procurement_seed_module.__file__).is_file()

    def test_event_to_tokens_shape(self):
        tokens = event_to_tokens(
            "stock_critical_low",
            {"valence": -0.7, "arousal": 0.8, "tags": ["procurement"]},
        )
        assert tokens[0] == "event:stock_critical_low"


class TestValidationG3AndHumanize:

    def test_save_blocked_on_orphan_seed_not_on_warnings(self, tmp_path):
        ctrl = _controller(tmp_path)
        ctrl.new_role("lab_role")
        ctrl.add_manual_tool("mcp__1c__create_purchase_order", included=True)
        ctrl.add_action_type("urgent_reorder", "Urgent", "")
        ctrl.set_tool_action_types("mcp__1c__create_purchase_order", ["urgent_reorder"])
        report = ctrl.validate()
        assert report.can_save is True
        assert any(issue.code == "unseeded_action" for issue in report.warnings)
        with pytest.raises(ConfiguratorError):
            ctrl.add_lesson_from_wizard(
                [], "ghost_action", "x", 1, False,
            )
        ctrl.upsert_affective_event("e", 0.0, 0.5, [])
        with pytest.raises(ConfiguratorError):
            ctrl.add_lesson_from_wizard(["e"], "ghost_action", "x", 1, False)
        ctrl._draft.setdefault("seed_corpus", []).append({
            "context_tokens": ["event:e"],
            "action": "ghost_action",
            "consequence": "x",
            "reward": 0.1,
            "intensity": 0.1,
            "reinforce": False,
        })
        report = ctrl.validate()
        assert report.can_save is False
        assert report.errors[0].code == "orphan_seed"
        assert report.errors[0].jump == "seed"
        with pytest.raises(ConfiguratorError, match="cannot save"):
            ctrl.save(confirmed=True)

    def test_humanize_orphan_and_unseeded_codes(self):
        orphan = (
            "config.yaml: seed_corpus references action(s) ['ghost_action'] that no "
            "mcp_capabilities entry declares in action_types."
        )
        code, params, jump = classify_role_config_message(orphan)
        assert code == "orphan_seed"
        assert params["actions"] == ["ghost_action"]
        assert jump == "seed"
        warn = (
            "config.yaml: action_type(s) ['urgent_reorder'] have no seed_corpus "
            "episode -- the agent starts with zero professional intuition for them."
        )
        code, params, jump = classify_role_config_message(warn)
        assert code == "unseeded_action"
        assert "urgent_reorder" in params["actions"]


class TestSaveG6G7:

    def test_mutations_do_not_touch_disk_until_save(self, tmp_path):
        ctrl = _open_procurement_copy(tmp_path)
        original = Path(ctrl.path).read_text(encoding="utf-8")
        ctrl.add_action_type("extra_decision", "Extra", "")
        assert Path(ctrl.path).read_text(encoding="utf-8") == original
        preview = ctrl.save(confirmed=False)
        assert preview["saved"] is False
        assert preview["needs_confirm"] is True
        assert Path(ctrl.path).read_text(encoding="utf-8") == original
        result = ctrl.save(confirmed=True)
        assert result["saved"] is True
        assert Path(ctrl.path).read_text(encoding="utf-8") != original
        history = list((Path(ctrl.path).parent / ".history").glob("config_*.yaml"))
        assert len(history) == 1
        assert history[0].read_text(encoding="utf-8") == original

    def test_new_role_save_creates_config_yaml(self, tmp_path):
        ctrl = _controller(tmp_path)
        ctrl.new_role("Sales")
        result = ctrl.save(confirmed=True)
        path = Path(result["path"])
        assert path.name == "config.yaml"
        loaded = load_role_config(str(path))
        assert loaded.display_name == "Sales"
        uuid.UUID(loaded.role_id)
        assert path.parent.name == loaded.role_id

    def test_diff_preview_mentions_added_tool(self, tmp_path):
        ctrl = _controller(tmp_path)
        ctrl.new_role("lab_role")
        ctrl.save(confirmed=True)
        ctrl.add_manual_tool("mcp__1c__cancel_order", included=True)
        lines = ctrl.diff_preview()
        assert any("cancel_order" in line for line in lines)

    def test_diff_preview_mentions_added_mcp_server(self, tmp_path):
        ctrl = _controller(tmp_path)
        ctrl.new_role("lab_role")
        ctrl.save(confirmed=True)
        ctrl.add_server("drive_mcp", display_name="Drive MCP", transport="http")
        ctrl.update_server(
            "drive_mcp",
            url="http://localhost/DriveDemo/hs/mcp/",
            username="suport",
            password="",
        )
        lines = ctrl.diff_preview()
        assert any("drive_mcp" in line and "added MCP server" in line for line in lines)
        ctrl.save(confirmed=True)
        reopened = _controller(tmp_path)
        reopened.open_role(ctrl.path)
        rows = {row["server_id"]: row for row in reopened.server_rows()}
        assert "drive_mcp" in rows
        assert rows["drive_mcp"]["url"] == "http://localhost/DriveDemo/hs/mcp/"
        assert rows["drive_mcp"]["username"] == "suport"


class TestDryRun:

    def test_dry_run_on_unsaved_procurement_draft_completes(self, tmp_path):
        ctrl = _open_procurement_copy(tmp_path)
        original = Path(ctrl.path).read_text(encoding="utf-8")
        ctrl.add_action_type("note_only", "Note", "not attached")
        result = ctrl.dry_run(scenario=SCENARIO_STOCK_CRITICAL, n_ticks=20)
        assert result.ok is True
        assert len(result.ticks) == 20
        assert Path(ctrl.path).read_text(encoding="utf-8") == original
        assert result.error == ""


class TestMcpServers:

    def test_open_procurement_groups_tools_under_server(self, tmp_path):
        ctrl = _open_procurement_copy(tmp_path)
        draft = ctrl.draft()
        servers = draft["mcp_servers"]
        by_id = {row["server_id"]: row for row in servers}
        assert set(by_id) == {"1c_erp", "drivemcp"}
        assert len(by_id["1c_erp"]["tools"]) == 4
        assert len(by_id["drivemcp"]["tools"]) == 6
        live_ids = {cap["tool_id"] for cap in draft["mcp_capabilities"]}
        assert live_ids == {tool["tool_id"] for tool in by_id["drivemcp"]["tools"]}
        assert {cap["server_name"] for cap in draft["mcp_capabilities"]} == {"drivemcp"}
        assert by_id["1c_erp"].get("enabled") is False

    def test_two_servers_isolate_tools_in_memory(self, tmp_path):
        ctrl = _controller(tmp_path)
        ctrl.new_role("Lab")
        ctrl.add_server("1c_erp", display_name="1C ERP")
        ctrl.add_server("crm", display_name="CRM")
        ctrl.add_manual_tool(
            "mcp__1c__get_stock_levels", server_name="1c_erp", included=True,
        )
        ctrl.add_manual_tool(
            "mcp__crm__list_leads",
            display_name="List leads",
            server_name="crm",
            included=True,
        )
        erp_included = {
            row["tool_id"]
            for row in ctrl.tool_rows(server_id="1c_erp")
            if row["included"]
        }
        crm_included = {
            row["tool_id"]
            for row in ctrl.tool_rows(server_id="crm")
            if row["included"]
        }
        assert erp_included == {"mcp__1c__get_stock_levels"}
        assert crm_included == {"mcp__crm__list_leads"}
        nested = {
            server["server_id"]: [tool["tool_id"] for tool in server["tools"]]
            for server in ctrl.draft()["mcp_servers"]
        }
        assert nested["1c_erp"] == ["mcp__1c__get_stock_levels"]
        assert nested["crm"] == ["mcp__crm__list_leads"]
        by_tool = {
            cap["tool_id"]: cap["server_name"]
            for cap in ctrl.draft()["mcp_capabilities"]
        }
        assert by_tool["mcp__1c__get_stock_levels"] == "1c_erp"
        assert by_tool["mcp__crm__list_leads"] == "crm"

    def test_disabled_server_drops_from_flatten_but_keeps_nested_tools(self, tmp_path):
        ctrl = _controller(tmp_path)
        ctrl.new_role("Lab")
        ctrl.add_server("1c_erp")
        ctrl.add_manual_tool("mcp__1c__get_stock_levels", included=True)
        ctrl.update_server("1c_erp", enabled=False)
        draft = ctrl.draft()
        assert draft["mcp_capabilities"] == []
        assert draft["mcp_servers"][0]["tools"][0]["tool_id"] == "mcp__1c__get_stock_levels"
        loaded = load_role_config_from_mapping(draft, "<draft>")
        assert loaded.capabilities == []
        assert ctrl._cap("mcp__1c__get_stock_levels")["tool_id"] == "mcp__1c__get_stock_levels"

    def test_new_role_has_empty_servers_then_add(self, tmp_path):
        ctrl = _controller(tmp_path)
        ctrl.new_role("Lab")
        assert ctrl.draft()["mcp_servers"] == []
        ctrl.add_server("1c_erp", "1C ERP")
        assert ctrl.server_rows()[0]["server_id"] == "1c_erp"
        assert ctrl.server_rows()[0]["n_tools"] == 0
        with pytest.raises(ConfiguratorError, match="already exists"):
            ctrl.add_server("1c_erp")
        with pytest.raises(ConfiguratorError, match="server_id"):
            ctrl.add_server("Bad Id!")

    def test_auth_fields_round_trip_yaml(self, tmp_path):
        ctrl = _controller(tmp_path)
        ctrl.new_role("Lab")
        ctrl.add_server("drive_mcp", display_name="Drive MCP", transport="http")
        ctrl.update_server(
            "drive_mcp",
            url="http://localhost/DriveDemo/hs/mcp/",
            username="suport",
            password="",
        )
        row = ctrl.server_rows()[0]
        assert row["username"] == "suport"
        assert row["password"] == ""
        ctrl.save(confirmed=True)
        raw = yaml.safe_load(Path(ctrl.path).read_text(encoding="utf-8"))
        server = raw["mcp_servers"][0]
        assert server["username"] == "suport"
        assert server["password"] == ""
        reopened = _controller(tmp_path)
        reopened.open_role(ctrl.path)
        row = reopened.server_rows()[0]
        assert row["transport"] == "http"
        assert row["url"] == "http://localhost/DriveDemo/hs/mcp/"
        assert row["username"] == "suport"
        assert row["password"] == ""

    def test_http_discover_catalogs_remote_tools(self, tmp_path, monkeypatch):
        from mcp_body.mcp_client import MCPToolDescriptor

        class Fake:
            def list_tools(self):
                return [
                    MCPToolDescriptor(name="get_stock_levels", description="READ stock"),
                    MCPToolDescriptor(name="list_metadata_objects", description="metadata"),
                ]

            def call_tool(self, name, arguments):
                return {"status": "ok"}

        captured: dict = {}

        def fake_from_server(server):
            captured.update(dict(server))
            return Fake()

        monkeypatch.setattr(
            "mcp_body.mcp_http.mcp_transport_from_server", fake_from_server,
        )
        ctrl = _controller(tmp_path)
        ctrl.new_role("Lab")
        ctrl.add_server("drive_mcp", display_name="Drive", transport="http")
        ctrl.update_server(
            "drive_mcp",
            url="http://localhost/DriveDemo/hs/mcp/",
            username="suport",
            password="",
        )
        rows = ctrl.discover_tools("drive_mcp")
        ids = {row["tool_id"] for row in rows}
        assert "mcp__drive_mcp__get_stock_levels" in ids
        assert "mcp__drive_mcp__list_metadata_objects" in ids
        assert captured["username"] == "suport"
        assert captured["password"] == ""
        assert captured["url"] == "http://localhost/DriveDemo/hs/mcp/"
        catalog_ids = {
            item["tool_id"] for item in ctrl.draft()["mcp_servers"][0]["catalog"]
        }
        assert catalog_ids == ids
        included = [row for row in rows if row["included"]]
        assert included == []
        ctrl.set_tool_included("mcp__drive_mcp__get_stock_levels", True, server_id="drive_mcp")
        ctrl.save(confirmed=True)
        reopened = _controller(tmp_path)
        reopened.open_role(ctrl.path)
        reopened_rows = reopened.tool_rows(server_id="drive_mcp")
        assert {row["tool_id"] for row in reopened_rows} == ids
        assert reopened.server_rows()[0]["n_catalog"] == 2
        assert reopened.server_rows()[0]["n_included"] == 1
        by_id = {row["tool_id"]: row for row in reopened_rows}
        assert by_id["mcp__drive_mcp__get_stock_levels"]["included"] is True
        assert by_id["mcp__drive_mcp__list_metadata_objects"]["included"] is False

    def test_http_discover_without_url_errors(self, tmp_path):
        ctrl = _controller(tmp_path)
        ctrl.new_role("Lab")
        ctrl.add_server("drive_mcp", transport="http")
        with pytest.raises(ConfiguratorError, match="url"):
            ctrl.discover_tools("drive_mcp")

    def test_live_drive_discover_with_suport_empty_password(self, tmp_path):
        from mcp_body.mcp_http import HttpMCPClient, HttpMCPError

        try:
            tools = HttpMCPClient(
                "http://localhost/DriveDemo/hs/mcp/",
                username="suport",
                password="",
                timeout=8,
            ).list_tools()
        except (HttpMCPError, OSError, TimeoutError):
            pytest.skip("Drive MCP is not published on localhost")
        if not tools:
            pytest.skip("Drive MCP returned no tools")
        ctrl = _controller(tmp_path)
        ctrl.new_role("Lab")
        ctrl.add_server("drive_mcp", display_name="Drive MCP", transport="http")
        ctrl.update_server(
            "drive_mcp",
            url="http://localhost/DriveDemo/hs/mcp/",
            username="suport",
            password="",
        )
        rows = ctrl.discover_tools("drive_mcp")
        ids = {row["tool_id"] for row in rows}
        assert "mcp__drive_mcp__get_stock_levels" in ids
        assert "mcp__drive_mcp__get_suppliers" in ids
        assert "mcp__drive_mcp__get_budget" in ids
        assert "mcp__drive_mcp__create_purchase_order" in ids
        assert "mcp__drive_mcp__list_metadata_objects" in ids
        assert "mcp__drive_mcp__get_metadata_structure" in ids
        assert len(rows) >= 6
        assert ctrl.server_rows()[0]["n_catalog"] == len(rows)
        assert ctrl.server_rows()[0]["n_included"] == 0


class TestMemoryNarrative:

    def test_describe_memory_row_hides_raw_tokens_and_reads_action(self):
        desc = describe_memory_row({
            "path": [
                "event:stock_critical_low",
                "valence:very_negative",
                "arousal:high",
                "domain:procurement",
                "result:success",
                "action:place_order_reliable_supplier",
            ],
            "consequence": "approved",
            "reward": 1.0,
            "intensity": 1.0,
        })
        assert desc["action"] == "place_order_reliable_supplier"
        assert desc["result"] == "success"
        assert desc["consequence"] == "approved"
        assert desc["events"] == ["stock critical low"]
        assert desc["importance"] == "critical"
        blob = " ".join(desc["events"] + desc["extra"] + [desc["action"], desc["result"]])
        assert "valence" not in blob
        assert "context_tokens" not in blob

    def test_describe_memory_row_accepts_top_level_action(self):
        desc = describe_memory_row({
            "path": ["result:failure"],
            "action": "urgent_reorder",
            "consequence": "rejected",
            "reward": 0.1,
        })
        assert desc["action"] == "urgent_reorder"
        assert desc["result"] == "failure"
        assert desc["importance"] == "low"


class TestLabSessionCustomPath:

    def test_body_lab_session_loads_injected_role_config_path(self, tmp_path):
        from nowa_body.lab_session import BodyLabSession, LabSettings, ORDER_TOOL

        dest = tmp_path / "config.yaml"
        shutil.copy(PROCUREMENT_CONFIG, dest)
        session = BodyLabSession(LabSettings(
            role_config_path=str(dest),
            seed_intuition=True,
            auto_execute=False,
            sensor_refresh_interval_s=300.0,
            min_ticks_between_sleep=10_000,
        ))
        assert session.registry.get(ORDER_TOOL) is not None
        result = session.tick_once()
        assert "action_type" in result
