"""Smoke tests for the Role Configurator GUI module."""

from pathlib import Path

import pytest

from nowa_body.gui_configurator import DEMO_ROOT, RoleConfiguratorApp, main
from nowa_body.gui_configurator_controller import DryRunResult, RoleConfiguratorController


def test_gui_module_exports_app_and_demo_root():
    assert RoleConfiguratorApp is not None
    assert callable(main)
    assert DEMO_ROOT.name == "Virtual company"
    assert (DEMO_ROOT / "src" / "nowa_body" / "gui_configurator.py").is_file()


@pytest.mark.tk
def test_app_builds_without_mainloop(tmp_path):
    app = RoleConfiguratorApp(controller=RoleConfiguratorController(roles_root=tmp_path))
    try:
        app.withdraw()
        app.update_idletasks()
        assert app.controller.has_draft() is False
        assert app.notebook.index("end") == 7
        app.controller.new_role("Lab")
        app._show_editor()
        app.update_idletasks()
        assert app.controller.can_save() is True
        assert str(app.btn_save_bar.cget("state")) == "normal"
        app.notebook.select(app.tab_affect)
        app.update_idletasks()
        assert str(app.btn_advanced.winfo_manager()) == "pack"
        app._rebuild_preset_buttons()
        assert "crisis" in app.preset_buttons
        # G2: approval widgets for irreversible tools are disabled after refresh
        app.controller.add_manual_tool("mcp__1c__delete_supplier", included=True)
        app._refresh_tools()
        app.update_idletasks()
        fake = __import__("tkinter").BooleanVar(master=app, value=False)
        app._on_approval("mcp__1c__delete_supplier", fake)
        assert app.controller._cap("mcp__1c__delete_supplier")["requires_approval"] is True
        locked = False
        for card in app.tools_inner.winfo_children():
            for child in card.winfo_children():
                text = str(child.cget("text")) if child.winfo_class() in {"TCheckbutton", "Checkbutton"} else ""
                if "cannot turn off" in text or "нельзя выключить" in text:
                    state = str(child.state()) if hasattr(child, "state") else ""
                    locked = "disabled" in state
        assert locked is True

        app.controller.add_manual_tool("mcp__1c__get_stock_levels", included=True)
        app._refresh_tools()
        app.update_idletasks()
        poll_states = {}
        for card in app.tools_inner.winfo_children():
            for child in card.winfo_children():
                if child.winfo_class() not in {"TCheckbutton", "Checkbutton"}:
                    continue
                text = str(child.cget("text"))
                if "Poll as sensor" in text or "Опрашивать как сенсор" in text:
                    state = str(child.state()) if hasattr(child, "state") else ""
                    poll_states[str(card.cget("text"))] = "disabled" in state
        assert poll_states.get("mcp__1c__get_stock_levels") is False
        assert poll_states.get("mcp__1c__delete_supplier") is True

        app.controller.add_server("drive_mcp", display_name="Drive MCP", transport="http")
        app.controller.update_server(
            "drive_mcp",
            url="http://localhost/DriveDemo/hs/mcp/",
            username="suport",
            password="",
        )
        app._refresh_servers()
        app.update_idletasks()
        labels = []
        for card in app.servers_inner.winfo_children():
            for child in card.winfo_children():
                if child.winfo_class() in {"TLabel", "Label"}:
                    labels.append(str(child.cget("text")))
        assert any("Username" in text or "Логин" in text for text in labels)
        assert any("Password" in text or "Пароль" in text for text in labels)

        app._last_dry = DryRunResult(
            ok=True,
            memory_rows=[
                {
                    "path": ["result:success", "action:place_order_reliable_supplier"],
                    "consequence": "approved",
                    "reward": 1.0,
                    "intensity": 1.0,
                }
            ]
            * 8,
        )
        dialog = app._show_last_memory()
        app.update_idletasks()
        body = ""
        has_scrollbar = False
        for frame in dialog.winfo_children():
            if frame.winfo_class() not in {"Frame", "TFrame"}:
                continue
            for child in frame.winfo_children():
                kind = child.winfo_class()
                if kind == "Text":
                    body = child.get("1.0", "end")
                if "Scrollbar" in kind:
                    has_scrollbar = True
        dialog.destroy()
        assert has_scrollbar is True
        assert "{'path'" not in body
        assert "place_order_reliable_supplier" not in body
        assert "Reliable supplier" in body or "Надёжный поставщик" in body
        assert "succeeded" in body or "успешно" in body
        assert "stored 8 times" in body or "записан 8 раз" in body
    finally:
        app.destroy()


@pytest.mark.tk
def test_help_dialog_opens_on_each_page(tmp_path):
    from nowa_body.gui_configurator_i18n import HELP_TOPICS

    app = RoleConfiguratorApp(controller=RoleConfiguratorController(roles_root=tmp_path))
    try:
        app.withdraw()
        app.update_idletasks()
        assert set(app._help_buttons) == set(HELP_TOPICS)
        assert str(app._help_buttons["list"].cget("text")) in {"Help", "Справка"}
        for topic in HELP_TOPICS:
            dialog = app._show_help(topic)
            app.update_idletasks()
            body = ""
            close_label = ""
            for widget in dialog.winfo_children():
                kind = widget.winfo_class()
                if kind in {"TButton", "Button"}:
                    close_label = str(widget.cget("text"))
                if kind not in {"Frame", "TFrame"}:
                    continue
                for child in widget.winfo_children():
                    if child.winfo_class() == "Text":
                        body = child.get("1.0", "end")
            dialog.destroy()
            assert len(body.strip()) > 250
            assert close_label in {"Close", "Закрыть"}
        list_help = app._show_help("list")
        app.update_idletasks()
        list_body = ""
        for widget in list_help.winfo_children():
            if widget.winfo_class() not in {"Frame", "TFrame"}:
                continue
            for child in widget.winfo_children():
                if child.winfo_class() == "Text":
                    list_body = child.get("1.0", "end")
        list_help.destroy()
        assert "Open role" in list_body or "Открыть роль" in list_body
    finally:
        app.destroy()


def test_run_bat_exists():
    bat = Path(__file__).resolve().parents[1] / "run_role_configurator.bat"
    assert bat.is_file()
    text = bat.read_text(encoding="utf-8")
    assert "nowa_body.gui_configurator" in text


class _StubEmployeeHost:
    def __init__(self, row):
        self._row = row
        self.sessions = {}

    def list_rows(self):
        return [dict(self._row)]

    def row_for(self, agent_id):
        return dict(self._row)

    def running_count(self):
        return 1 if self._row.get("status") not in ("stopped", "error") else 0

    def can_start(self, agent_id):
        return False, str(self._row.get("status") or "running")


@pytest.mark.tk
def test_employee_poll_keeps_home_and_approval_widgets(tmp_path):
    pending = [
        {
            "action_id": "a1",
            "tool_id": "mcp__drivemcp__create_purchase_order",
            "tool_params": {"qty": 1.0, "supplier_id": "s1"},
        },
        {
            "action_id": "a2",
            "tool_id": "mcp__1c__create_purchase_order",
            "tool_params": {"qty": 2.0, "sku": "A"},
        },
    ]
    row = {
        "agent_id": "buyer",
        "display_name": "Buyer",
        "status": "awaiting_approval",
        "role_ids": ["procurement"],
        "tick_interval_s": 10.0,
        "sleep_min_interval_s": 3600.0,
        "pending_n": 2,
        "pending": pending,
        "error_text": "",
        "stale_roles": False,
        "mcp": [{"server_id": "drivemcp", "transport": "http", "ok": True}],
        "n_read": 8,
        "n_write": 2,
        "last_sensor": "",
        "checkpoint": "15:57",
        "episodes": 8,
        "log": ["tick 1"],
    }
    app = RoleConfiguratorApp(
        controller=RoleConfiguratorController(roles_root=tmp_path),
        employee_host=_StubEmployeeHost(row),
    )
    try:
        app.withdraw()
        app.update_idletasks()
        app._refresh_employees()
        home_start = app._emp_home_cards["buyer"]["start"]
        app._refresh_employees()
        assert app._emp_home_cards["buyer"]["start"] is home_start
        assert "pending" in str(app._emp_home_cards["buyer"]["pending"].cget("text")).lower() or "2" in str(
            app._emp_home_cards["buyer"]["pending"].cget("text")
        )

        app._open_employee("buyer")
        app.update_idletasks()
        approval_children = tuple(app.emp_approval_inner.winfo_children())
        assert len(approval_children) == 2
        app._refresh_employee_card()
        app.update_idletasks()
        assert tuple(app.emp_approval_inner.winfo_children()) == approval_children
        row["log"] = ["tick 1", "tick 2"]
        app._refresh_employee_card()
        assert "tick 2" in app.txt_emp_log.get("1.0", "end-1c")
        assert tuple(app.emp_approval_inner.winfo_children()) == approval_children
    finally:
        app.destroy()


@pytest.mark.tk
def test_tick_log_copy_and_selection_survives_refresh(tmp_path):
    app = RoleConfiguratorApp(controller=RoleConfiguratorController(roles_root=tmp_path))
    try:
        app.withdraw()
        app.update_idletasks()
        app._set_text(app.txt_emp_log, "alpha bravo charlie")
        app.txt_emp_log.focus_force()
        app.txt_emp_log.tag_add("sel", "1.6", "1.11")
        app.update()
        class _Evt:
            widget = app.txt_emp_log
        assert app._selected_text(app.txt_emp_log) == "bravo"
        assert app._on_copy_shortcut(_Evt()) == "break"
        assert app.clipboard_get() == "bravo"
        app._set_text(app.txt_emp_log, "alpha bravo charlie\nnext tick")
        assert app.txt_emp_log.get("sel.first", "sel.last") == "bravo"
        assert "next tick" not in app.txt_emp_log.get("1.0", "end-1c")
        app.txt_emp_log.tag_remove("sel", "1.0", "end")
        app._on_select_all_shortcut(_Evt())
        assert "alpha bravo charlie" in app._selected_text(app.txt_emp_log)
    finally:
        app.destroy()


class _AlertingEmployeeHost(_StubEmployeeHost):
    def clear_alerts(self, agent_id):
        self._row["alerts"] = []


@pytest.mark.tk
def test_business_limit_alerts_show_on_card_and_home_and_clear(tmp_path):
    row = {
        "agent_id": "buyer",
        "display_name": "Buyer",
        "status": "running",
        "role_ids": ["procurement"],
        "tick_interval_s": 10.0,
        "sleep_min_interval_s": 3600.0,
        "pending_n": 0,
        "pending": [],
        "error_text": "",
        "stale_roles": False,
        "log": [],
        "alerts": [
            {"at": "2026-10-20T09:15:00", "limit": "budget", "reason": "nothing_left",
             "available": 0.0, "summary": "create_purchase_order sku=sku-a qty=40"},
            {"at": "2026-10-21T11:30:00", "limit": "budget", "reason": "over_available",
             "available": 6.5, "summary": "create_purchase_order sku=sku-b qty=10"},
        ],
    }
    app = RoleConfiguratorApp(
        controller=RoleConfiguratorController(roles_root=tmp_path),
        employee_host=_AlertingEmployeeHost(row),
    )
    try:
        app.withdraw()
        app.update_idletasks()
        app._refresh_employees()
        assert "2" in str(app._emp_home_cards["buyer"]["alerts"].cget("text"))

        app._open_employee("buyer")
        app.update_idletasks()
        assert app.frm_emp_alerts.winfo_manager() == "pack"
        body = str(app.lbl_emp_alerts_body.cget("text"))
        first, second = body.splitlines()
        assert first.startswith("11:30") and "sku-b" in first and "6.5" in first
        assert second.startswith("09:15") and "sku-a" in second

        app._on_emp_clear_alerts()
        app.update_idletasks()
        assert app.frm_emp_alerts.winfo_manager() == ""
    finally:
        app.destroy()
