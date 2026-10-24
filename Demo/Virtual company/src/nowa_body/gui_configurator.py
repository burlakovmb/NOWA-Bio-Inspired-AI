"""NOWA Role Configurator — thin Tk view over RoleConfiguratorController.

Launch::

    python -m nowa_body.gui_configurator
    # or run_role_configurator.bat
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import tkinter as tk
    from tkinter import messagebox, simpledialog, ttk
except ImportError:  # pragma: no cover - minimal Python builds omit Tk
    tk = None  # type: ignore[assignment]
    messagebox = None  # type: ignore[assignment]
    simpledialog = None  # type: ignore[assignment]
    ttk = None  # type: ignore[assignment]

if __package__ in (None, ""):  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nowa_body._compat import ensure_core_src_on_path
from nowa_body.gui_configurator_controller import (
    ConfiguratorError,
    MCP_TRANSPORTS,
    RiskDowngradeRequired,
    RoleConfiguratorController,
    SCENARIO_STOCK_CRITICAL,
    SCENARIOS,
    describe_memory_row,
    format_relative_mtime,
    list_roles,
)
from nowa_body.gui_configurator_i18n import I18n, STRINGS


def _idle_button_bg(widget) -> str:
    """Windows system button color when this Tk knows it."""

    if tk is None:
        return "#f0f0f0"
    try:
        widget.tk.call("winfo", "rgb", widget, "SystemButtonFace")
    except tk.TclError:
        return "#f0f0f0"
    return "SystemButtonFace"
from nowa_body.gui_employee_controller import EmployeeHostController, suggest_agent_id
from nowa_body.mcp_capability import CapabilityRisk
from nowa_body.approval_gate import ApprovalStatus

ensure_core_src_on_path()
from affective_space import AXES  # noqa: E402

_SHORTHAND_AXES = ("valence", "arousal")
_EXTRA_AXES = tuple(axis for axis in AXES if axis not in _SHORTHAND_AXES)

DEMO_ROOT = Path(__file__).resolve().parents[2]
RISK_VALUES = [risk.value for risk in CapabilityRisk]
TAB_KEYS = (
    "tab.servers",
    "tab.tools",
    "tab.vocab",
    "tab.affect",
    "tab.seed",
    "tab.validation",
    "tab.dryrun",
)
TAB_SERVERS = 0
TAB_TOOLS = 1
TAB_VOCAB = 2
TAB_AFFECT = 3
TAB_SEED = 4
TAB_VALIDATION = 5
TAB_DRYRUN = 6
N_TABS = 7
WIZARD_LAST_CONTENT = 5
SCENARIO_I18N = {
    "quiet": "scenario.quiet",
    "stock_critical": "scenario.stock_critical",
    "supplier_defaulted": "scenario.supplier_defaulted",
}


class RoleConfiguratorApp(tk.Tk if tk is not None else object):
    """Role list + seven-tab editor. Business rules live in the controller."""

    def __init__(
        self,
        controller: Optional[RoleConfiguratorController] = None,
        employee_host: Optional[EmployeeHostController] = None,
        lang: str | None = None,
    ) -> None:
        super().__init__()
        self.geometry("1280x800")
        self.minsize(960, 640)
        self.i18n = I18n(
            lang=lang or "en",
            pref_path=DEMO_ROOT / "results" / ".role_configurator_lang.json",
            force=lang in ("en", "ru"),
        )
        self.controller = controller or RoleConfiguratorController()
        self.employee_host = employee_host or EmployeeHostController(
            roles_root=self.controller.roles_root,
        )
        self._role_items: List[Any] = []
        self._wizard_step = 0
        self._seed_technical = False
        self._show_issue_technical = False
        self._current_event = ""
        self._axis_set: set = set()
        self._advanced_shown = False
        self._preset_fp = ""
        self._current_server_id = ""
        self._updating = False
        self._screen = "home"
        self._current_employee_id = ""
        self._emp_poll_after: Optional[str] = None
        self._emp_home_cards: Dict[str, Dict[str, Any]] = {}
        self._emp_card_fp: Dict[str, Any] = {}
        self._build()
        self._apply_language()
        self._show_list()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def t(self, key: str, **kwargs: Any) -> str:
        return self.i18n.t(key, **kwargs)

    def destroy(self) -> None:
        self._cancel_emp_poll()
        super().destroy()

    # ------------------------------------------------------------------ chrome
    def _build(self) -> None:
        self._help_buttons: Dict[str, ttk.Button] = {}
        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")

        header = ttk.Frame(self)
        header.pack(fill="x", padx=8, pady=(8, 0))
        self.lbl_title = ttk.Label(header, font=("Segoe UI", 12, "bold"))
        self.lbl_title.pack(side="left")
        lang_bar = ttk.Frame(header)
        lang_bar.pack(side="right")
        self.btn_lang_en = tk.Button(
            lang_bar, text="EN", command=lambda: self._set_language("en"),
            relief="raised", padx=8, pady=2, font=("Segoe UI", 10), cursor="hand2",
        )
        self.btn_lang_ru = tk.Button(
            lang_bar, text="RU", command=lambda: self._set_language("ru"),
            relief="raised", padx=8, pady=2, font=("Segoe UI", 10), cursor="hand2",
        )
        self.btn_lang_en.pack(side="left", padx=(0, 4))
        self.btn_lang_ru.pack(side="left")

        self.home_frame = ttk.Frame(self)
        self.list_frame = ttk.Frame(self.home_frame)
        self.employees_frame = ttk.Frame(self.home_frame)
        self.editor_frame = ttk.Frame(self)
        self.employee_card_frame = ttk.Frame(self)

        self._build_list(self.list_frame)
        self._build_employees_home(self.employees_frame)
        self._build_editor(self.editor_frame)
        self._build_employee_card(self.employee_card_frame)

        self.list_frame.pack(side="left", fill="both", expand=True)
        ttk.Separator(self.home_frame, orient="vertical").pack(side="left", fill="y", padx=4)
        self.employees_frame.pack(side="left", fill="both", expand=True)

        self._mark_readonly_text(
            self.txt_emp_log,
            self.txt_emp_narrative,
            self.txt_errors,
            self.txt_warns,
            self.txt_dryrun,
        )
        self._wire_clipboard_shortcuts()

        self.lbl_status = ttk.Label(self, padding=(10, 6))
        self.lbl_status.pack(side="bottom", fill="x")

    def _build_list(self, parent: ttk.Frame) -> None:
        head = ttk.Frame(parent)
        head.pack(fill="x", padx=12, pady=(12, 6))
        self.lbl_list_heading = ttk.Label(head, font=("Segoe UI", 11, "bold"))
        self.lbl_list_heading.pack(side="left")
        self._make_help_button(head, "list").pack(side="right")
        self.lst_roles = tk.Listbox(parent, height=16, font=("Segoe UI", 10))
        self.lst_roles.pack(fill="both", expand=True, padx=12, pady=4)
        self.lst_roles.bind("<Double-Button-1>", lambda _e: self._open_selected())
        btns = ttk.Frame(parent)
        btns.pack(fill="x", padx=12, pady=10)
        self.btn_new = ttk.Button(btns, command=self._on_new_role)
        self.btn_new.pack(side="left")
        self.btn_open = ttk.Button(btns, command=self._open_selected)
        self.btn_open.pack(side="left", padx=8)
        self.lbl_list_empty = ttk.Label(parent)

    def _build_employees_home(self, parent: ttk.Frame) -> None:
        head = ttk.Frame(parent)
        head.pack(fill="x", padx=12, pady=(12, 6))
        self.lbl_emp_heading = ttk.Label(head, font=("Segoe UI", 11, "bold"))
        self.lbl_emp_heading.pack(side="left")
        self._make_help_button(head, "employees").pack(side="right")
        body = ttk.Frame(parent)
        body.pack(fill="both", expand=True, padx=8, pady=4)
        self.emp_cards_inner = self._scrollable(body)
        self.lbl_emp_empty = ttk.Label(parent, wraplength=420)
        btns = ttk.Frame(parent)
        btns.pack(fill="x", padx=12, pady=10)
        self.btn_emp_new = ttk.Button(btns, command=self._on_new_employee)
        self.btn_emp_new.pack(side="left")

    def _build_employee_card(self, parent: ttk.Frame) -> None:
        bar = ttk.Frame(parent)
        bar.pack(fill="x", padx=8, pady=(8, 0))
        self.btn_emp_back = ttk.Button(bar, command=self._on_emp_back)
        self.btn_emp_back.pack(side="left")
        self.lbl_emp_title = ttk.Label(bar, font=("Segoe UI", 11, "bold"))
        self.lbl_emp_title.pack(side="left", padx=12)
        self.lbl_emp_badge = ttk.Label(bar)
        self.lbl_emp_badge.pack(side="right")

        self.lbl_emp_error = ttk.Label(parent, foreground="#a40000", wraplength=900)
        self.lbl_emp_error.pack(fill="x", padx=12, pady=(4, 0))

        self.frm_emp_stale = ttk.Frame(parent)
        self.lbl_emp_stale = ttk.Label(self.frm_emp_stale, wraplength=720, foreground="#8a5a00")
        self.lbl_emp_stale.pack(side="left", fill="x", expand=True)
        self.btn_emp_restart = ttk.Button(self.frm_emp_stale, command=self._on_emp_restart)
        self.btn_emp_restart.pack(side="right", padx=8)

        roles = ttk.Frame(parent)
        roles.pack(fill="x", padx=12, pady=(8, 0))
        self.lbl_emp_roles = ttk.Label(roles)
        self.lbl_emp_roles.pack(side="left")
        self.emp_roles_box = ttk.Frame(roles)
        self.emp_roles_box.pack(side="left", padx=8)
        self.btn_emp_add_role = ttk.Button(roles, command=self._on_emp_add_role)
        self.btn_emp_add_role.pack(side="left")

        rhythm = ttk.Frame(parent)
        rhythm.pack(fill="x", padx=12, pady=8)
        self.lbl_emp_tick = ttk.Label(rhythm)
        self.lbl_emp_tick.pack(side="left")
        self.ent_emp_tick = ttk.Entry(rhythm, width=8)
        self.ent_emp_tick.pack(side="left", padx=(4, 12))
        self.ent_emp_tick.bind("<FocusOut>", lambda _e: self._commit_emp_rhythm())
        self.lbl_emp_sensor = ttk.Label(rhythm)
        self.lbl_emp_sensor.pack(side="left")
        self.ent_emp_sensor = ttk.Entry(rhythm, width=8)
        self.ent_emp_sensor.pack(side="left", padx=(4, 12))
        self.ent_emp_sensor.bind("<FocusOut>", lambda _e: self._commit_emp_rhythm())
        self.lbl_emp_sleep = ttk.Label(rhythm)
        self.lbl_emp_sleep.pack(side="left")
        self.ent_emp_sleep = ttk.Entry(rhythm, width=8)
        self.ent_emp_sleep.pack(side="left", padx=(4, 4))
        self.ent_emp_sleep.bind("<FocusOut>", lambda _e: self._commit_emp_rhythm())
        self.lbl_emp_seconds = ttk.Label(rhythm)
        self.lbl_emp_seconds.pack(side="left")

        extras = ttk.Frame(parent)
        extras.pack(fill="x", padx=12, pady=(0, 8))
        self.lbl_emp_window = ttk.Label(extras)
        self.lbl_emp_window.pack(side="left")
        self.ent_emp_win_start = ttk.Entry(extras, width=4)
        self.ent_emp_win_start.pack(side="left", padx=4)
        ttk.Label(extras, text="–").pack(side="left")
        self.ent_emp_win_end = ttk.Entry(extras, width=4)
        self.ent_emp_win_end.pack(side="left", padx=4)
        self.ent_emp_win_start.bind("<FocusOut>", lambda _e: self._commit_emp_rhythm())
        self.ent_emp_win_end.bind("<FocusOut>", lambda _e: self._commit_emp_rhythm())
        self.lbl_emp_fatigue = ttk.Label(extras)
        self.lbl_emp_fatigue.pack(side="left", padx=(12, 4))
        self.ent_emp_fatigue = ttk.Entry(extras, width=6)
        self.ent_emp_fatigue.pack(side="left")
        self.ent_emp_fatigue.bind("<FocusOut>", lambda _e: self._commit_emp_rhythm())
        self.lbl_emp_sleep_hint = ttk.Label(parent, wraplength=900, foreground="#555")
        self.lbl_emp_sleep_hint.pack(fill="x", padx=12)

        self.lbl_emp_mcp = ttk.Label(parent, wraplength=900)
        self.lbl_emp_mcp.pack(anchor="w", padx=12, pady=(8, 0))
        self.lbl_emp_organs = ttk.Label(parent, wraplength=900)
        self.lbl_emp_organs.pack(anchor="w", padx=12)
        self.lbl_emp_memory = ttk.Label(parent, wraplength=900)
        self.lbl_emp_memory.pack(anchor="w", padx=12)

        actions = ttk.Frame(parent)
        actions.pack(fill="x", padx=12, pady=10)
        self.btn_emp_start = ttk.Button(actions, command=self._on_emp_start)
        self.btn_emp_start.pack(side="left")
        self.btn_emp_stop = ttk.Button(actions, command=self._on_emp_stop)
        self.btn_emp_stop.pack(side="left", padx=8)
        self.btn_emp_reset = ttk.Button(actions, command=self._on_emp_reset_memory)
        self.btn_emp_reset.pack(side="left", padx=8)
        self.btn_emp_delete = ttk.Button(actions, command=self._on_emp_delete)
        self.btn_emp_delete.pack(side="left", padx=8)

        # Writes a business limit kept from the ERP; packed only when present.
        self.frm_emp_alerts = ttk.Frame(parent)
        alerts_head = ttk.Frame(self.frm_emp_alerts)
        alerts_head.pack(fill="x")
        self.lbl_emp_alerts = ttk.Label(
            alerts_head, font=("Segoe UI", 10, "bold"), foreground="#a35200"
        )
        self.lbl_emp_alerts.pack(side="left")
        self.btn_emp_alerts_clear = ttk.Button(alerts_head, command=self._on_emp_clear_alerts)
        self.btn_emp_alerts_clear.pack(side="left", padx=8)
        self.lbl_emp_alerts_body = ttk.Label(
            self.frm_emp_alerts, wraplength=900, justify="left", foreground="#a35200"
        )
        self.lbl_emp_alerts_body.pack(anchor="w")

        self.lbl_emp_approval = ttk.Label(parent, font=("Segoe UI", 10, "bold"))
        self.lbl_emp_approval.pack(anchor="w", padx=12)
        approval_body = ttk.Frame(parent)
        approval_body.pack(fill="x", padx=8, pady=4)
        self.emp_approval_inner = self._scrollable(approval_body)

        logs = ttk.Frame(parent)
        logs.pack(fill="both", expand=True, padx=8, pady=8)
        left = ttk.Frame(logs)
        left.pack(side="left", fill="both", expand=True, padx=(0, 6))
        right = ttk.Frame(logs)
        right.pack(side="left", fill="both", expand=True, padx=(6, 0))
        self.lbl_emp_log = ttk.Label(left)
        self.lbl_emp_log.pack(anchor="w")
        self.txt_emp_log = tk.Text(left, wrap="word", height=10)
        self.txt_emp_log.pack(fill="both", expand=True)
        self.lbl_emp_narrative = ttk.Label(right)
        self.lbl_emp_narrative.pack(anchor="w")
        self.txt_emp_narrative = tk.Text(right, wrap="word", height=10)
        self.txt_emp_narrative.pack(fill="both", expand=True)

    def _build_editor(self, parent: ttk.Frame) -> None:
        bar = ttk.Frame(parent)
        bar.pack(fill="x", padx=8, pady=(8, 0))
        self.btn_back = ttk.Button(bar, command=self._on_back)
        self.btn_back.pack(side="left")
        self.lbl_editor_title = ttk.Label(bar, font=("Segoe UI", 11, "bold"))
        self.lbl_editor_title.pack(side="left", padx=12)
        self.btn_save_bar = ttk.Button(bar, command=self._on_save)
        self.btn_save_bar.pack(side="right")
        self.btn_history = ttk.Button(bar, command=self._on_history)
        self.btn_history.pack(side="right", padx=(0, 8))

        self.lbl_wizard = ttk.Label(parent, foreground="#8a5a00")
        self.wizard_nav = ttk.Frame(parent)
        self.btn_wiz_back = ttk.Button(self.wizard_nav, command=self._wizard_back)
        self.btn_wiz_next = ttk.Button(self.wizard_nav, command=self._wizard_next)
        self.btn_wiz_back.pack(side="left")
        self.btn_wiz_next.pack(side="left", padx=8)

        self.notebook = ttk.Notebook(parent)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=8)
        self.notebook.bind("<<NotebookTabChanged>>", lambda _e: self._on_tab_changed())

        self.tab_servers = ttk.Frame(self.notebook)
        self.tab_tools = ttk.Frame(self.notebook)
        self.tab_vocab = ttk.Frame(self.notebook)
        self.tab_affect = ttk.Frame(self.notebook)
        self.tab_seed = ttk.Frame(self.notebook)
        self.tab_validation = ttk.Frame(self.notebook)
        self.tab_dryrun = ttk.Frame(self.notebook)
        for frame in (
            self.tab_servers, self.tab_tools, self.tab_vocab, self.tab_affect,
            self.tab_seed, self.tab_validation, self.tab_dryrun,
        ):
            self.notebook.add(frame, text="")

        self._build_servers_tab()
        self._build_tools_tab()
        self._build_vocab_tab()
        self._build_affect_tab()
        self._build_seed_tab()
        self._build_validation_tab()
        self._build_dryrun_tab()

    def _scrollable(self, parent: ttk.Frame) -> ttk.Frame:
        canvas = tk.Canvas(parent, highlightthickness=0)
        scroll = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind(
            "<Configure>",
            lambda _e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        return inner

    def _build_servers_tab(self) -> None:
        top = ttk.Frame(self.tab_servers)
        top.pack(fill="x", padx=8, pady=8)
        self.lbl_servers_intro = ttk.Label(top, wraplength=820)
        self.lbl_servers_intro.pack(side="left", fill="x", expand=True)
        self._make_help_button(top, "servers").pack(side="right")
        self.btn_add_server = ttk.Button(top, command=self._on_add_server)
        self.btn_add_server.pack(side="right", padx=(0, 8))
        self.lbl_servers_placeholder = ttk.Label(self.tab_servers, wraplength=900)
        self.lbl_servers_placeholder.pack(fill="x", padx=10, pady=(0, 6))
        body = ttk.Frame(self.tab_servers)
        body.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.servers_inner = self._scrollable(body)

    def _build_tools_tab(self) -> None:
        top = ttk.Frame(self.tab_tools)
        top.pack(fill="x", padx=8, pady=8)
        self.lbl_tools_server = ttk.Label(top)
        self.lbl_tools_server.pack(side="left")
        self.cmb_tools_server = ttk.Combobox(top, state="readonly", width=24)
        self.cmb_tools_server.pack(side="left", padx=8)
        self.cmb_tools_server.bind("<<ComboboxSelected>>", lambda _e: self._on_tools_server_changed())
        self._make_help_button(top, "tools").pack(side="right")
        self.btn_discover = ttk.Button(top, command=self._on_discover)
        self.btn_discover.pack(side="right", padx=(0, 8))
        self.btn_add_tool = ttk.Button(top, command=self._on_add_manual_tool)
        self.btn_add_tool.pack(side="right", padx=8)
        self.lbl_high_note = ttk.Label(self.tab_tools, wraplength=900)
        self.lbl_high_note.pack(fill="x", padx=10, pady=(0, 6))
        body = ttk.Frame(self.tab_tools)
        body.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.tools_inner = self._scrollable(body)

    def _build_vocab_tab(self) -> None:
        top = ttk.Frame(self.tab_vocab)
        top.pack(fill="x", padx=8, pady=8)
        self.lbl_vocab_intro = ttk.Label(top)
        self.lbl_vocab_intro.pack(side="left")
        self._make_help_button(top, "vocab").pack(side="right")
        self.btn_add_vocab = ttk.Button(top, command=self._on_add_vocab)
        self.btn_add_vocab.pack(side="right", padx=(0, 8))
        self.lbl_wait_note = ttk.Label(self.tab_vocab, wraplength=900)
        self.lbl_wait_note.pack(fill="x", padx=10)
        body = ttk.Frame(self.tab_vocab)
        body.pack(fill="both", expand=True, padx=8, pady=8)
        self.vocab_inner = self._scrollable(body)

    def _build_affect_tab(self) -> None:
        inner = self._scrollable(self.tab_affect)
        self.affect_inner = inner

        top = ttk.Frame(inner)
        top.pack(fill="x", padx=10, pady=10)
        self.lbl_affect_what = ttk.Label(top)
        self.lbl_affect_what.pack(side="left")
        self.cmb_event = ttk.Combobox(top, state="readonly", width=40)
        self.cmb_event.pack(side="left", padx=8)
        self.cmb_event.bind("<<ComboboxSelected>>", lambda _e: self._load_event_into_sliders())
        self.btn_new_event = ttk.Button(top, command=self._on_new_event)
        self.btn_new_event.pack(side="left")
        self.btn_del_event = ttk.Button(top, command=self._on_delete_event)
        self.btn_del_event.pack(side="left", padx=4)
        self._make_help_button(top, "affect").pack(side="right")

        self.lbl_valence = ttk.Label(inner)
        self.lbl_valence.pack(anchor="w", padx=12, pady=(8, 0))
        valence_row = ttk.Frame(inner)
        valence_row.pack(fill="x", padx=12)
        self.lbl_valence_bad = ttk.Label(valence_row)
        self.lbl_valence_bad.pack(side="left")
        self.scl_valence = tk.Scale(
            valence_row, from_=-1.0, to=1.0, resolution=0.05,
            orient="horizontal", length=360, command=lambda _v: self._on_affect_slider(),
        )
        self.scl_valence.pack(side="left", padx=8)
        self.lbl_valence_good = ttk.Label(valence_row)
        self.lbl_valence_good.pack(side="left")
        self.lbl_valence_val = ttk.Label(valence_row)
        self.lbl_valence_val.pack(side="left", padx=8)

        self.lbl_arousal = ttk.Label(inner)
        self.lbl_arousal.pack(anchor="w", padx=12, pady=(12, 0))
        arousal_row = ttk.Frame(inner)
        arousal_row.pack(fill="x", padx=12)
        self.lbl_arousal_calm = ttk.Label(arousal_row)
        self.lbl_arousal_calm.pack(side="left")
        self.scl_arousal = tk.Scale(
            arousal_row, from_=0.0, to=1.0, resolution=0.05,
            orient="horizontal", length=360, command=lambda _v: self._on_affect_slider(),
        )
        self.scl_arousal.pack(side="left", padx=8)
        self.lbl_arousal_alarm = ttk.Label(arousal_row)
        self.lbl_arousal_alarm.pack(side="left")
        self.lbl_arousal_val = ttk.Label(arousal_row)
        self.lbl_arousal_val.pack(side="left", padx=8)
        self.lbl_arousal_hint = ttk.Label(inner, foreground="#8a5a00")

        presets = ttk.LabelFrame(inner)
        self.frm_presets = presets
        presets.pack(fill="x", padx=12, pady=16)
        self.preset_btn_row = ttk.Frame(presets)
        self.preset_btn_row.pack(fill="x")
        self.preset_buttons: Dict[str, ttk.Button] = {}
        actions = ttk.Frame(presets)
        actions.pack(fill="x")
        self.btn_save_preset = ttk.Button(actions, command=self._on_save_preset)
        self.btn_save_preset.pack(side="left", padx=6, pady=6)
        self.btn_preset_catalog = ttk.Button(actions, command=self._open_preset_catalog)
        self.btn_preset_catalog.pack(side="left", padx=6, pady=6)

        tags_row = ttk.Frame(inner)
        tags_row.pack(fill="x", padx=12)
        self.lbl_affect_tags = ttk.Label(tags_row)
        self.lbl_affect_tags.pack(side="left")
        self.lbl_tag_values = ttk.Label(tags_row)
        self.lbl_tag_values.pack(side="left", padx=8)
        self.btn_add_event_tag = ttk.Button(tags_row, command=self._on_add_event_tag)
        self.btn_add_event_tag.pack(side="left")

        self.btn_advanced = ttk.Button(inner, command=self._toggle_advanced_affect)
        self.btn_advanced.pack(anchor="w", padx=12, pady=8)
        self.frm_advanced = ttk.LabelFrame(inner)
        self.scl_extra: Dict[str, tk.Scale] = {}
        self.lbl_extra: Dict[str, ttk.Label] = {}
        self.btn_reset_axis: Dict[str, ttk.Button] = {}
        for axis in _EXTRA_AXES:
            row = ttk.Frame(self.frm_advanced)
            row.pack(fill="x", padx=8, pady=2)
            lbl = ttk.Label(row, width=12)
            lbl.pack(side="left")
            self.lbl_extra[axis] = lbl
            scale = tk.Scale(
                row, from_=-1.0, to=1.0, resolution=0.05,
                orient="horizontal", length=320,
                command=lambda _v, a=axis: self._on_extra_axis(a),
            )
            scale.pack(side="left", padx=8)
            self.scl_extra[axis] = scale
            reset = ttk.Button(row, command=lambda a=axis: self._on_reset_axis(a))
            reset.pack(side="left")
            self.btn_reset_axis[axis] = reset
        full_row = ttk.Frame(self.frm_advanced)
        full_row.pack(fill="x", padx=8, pady=4)
        self.lbl_arousal_full = ttk.Label(full_row, width=12)
        self.lbl_arousal_full.pack(side="left")
        self.scl_arousal_full = tk.Scale(
            full_row, from_=-1.0, to=1.0, resolution=0.05,
            orient="horizontal", length=320,
            command=lambda _v: self._on_arousal_full(),
        )
        self.scl_arousal_full.pack(side="left", padx=8)
        int_row = ttk.Frame(self.frm_advanced)
        int_row.pack(fill="x", padx=8, pady=4)
        self.lbl_intensity = ttk.Label(int_row, width=12)
        self.lbl_intensity.pack(side="left")
        self.scl_intensity = tk.Scale(
            int_row, from_=0.0, to=1.0, resolution=0.05,
            orient="horizontal", length=320,
            command=lambda _v: self._on_affect_slider(),
        )
        self.scl_intensity.pack(side="left", padx=8)
        self.scl_intensity.set(0.35)

        preview = ttk.LabelFrame(inner)
        self.frm_preview = preview
        preview.pack(fill="x", padx=12, pady=8)
        self.lbl_preview = ttk.Label(preview, wraplength=900, justify="left")
        self.lbl_preview.pack(anchor="w", padx=8, pady=4)
        self.lbl_preview_hint = ttk.Label(preview, wraplength=900, foreground="#555")
        self.lbl_preview_hint.pack(anchor="w", padx=8, pady=(0, 6))

        outcome = ttk.LabelFrame(inner)
        self.frm_outcome = outcome
        outcome.pack(fill="x", padx=12, pady=(0, 16))
        self.lbl_outcome = ttk.Label(outcome, wraplength=900, justify="left")
        self.lbl_outcome.pack(anchor="w", padx=8, pady=6)

    def _build_seed_tab(self) -> None:
        self.frm_seed_ro = ttk.Frame(self.tab_seed)
        self.lbl_seed_ro = ttk.Label(self.frm_seed_ro, wraplength=900)
        self.lbl_seed_ro.pack(side="left", padx=8, pady=8)
        self.btn_migrate = ttk.Button(self.frm_seed_ro, command=self._on_migrate)
        self.btn_migrate.pack(side="left", padx=8)

        top = ttk.Frame(self.tab_seed)
        top.pack(fill="x", padx=8, pady=8)
        self.frm_seed_top = top
        self.btn_add_lesson = ttk.Button(top, command=lambda: self._open_lesson_wizard())
        self.btn_add_lesson.pack(side="left")
        self.btn_edit_lesson = ttk.Button(top, command=self._on_edit_lesson)
        self.btn_edit_lesson.pack(side="left", padx=6)
        self.btn_del_lesson = ttk.Button(top, command=self._on_delete_lesson)
        self.btn_del_lesson.pack(side="left")
        self._make_help_button(top, "seed").pack(side="right")
        self.btn_seed_mode = ttk.Button(top, command=self._toggle_seed_mode)
        self.btn_seed_mode.pack(side="right", padx=(0, 8))

        self.lst_lessons = tk.Listbox(self.tab_seed, font=("Segoe UI", 10))
        self.lst_lessons.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def _build_validation_tab(self) -> None:
        val_top = ttk.Frame(self.tab_validation)
        val_top.pack(fill="x", padx=12, pady=(10, 0))
        self._make_help_button(val_top, "validation").pack(side="right")
        self.lbl_val_errors = ttk.Label(self.tab_validation, font=("Segoe UI", 10, "bold"))
        self.lbl_val_errors.pack(anchor="w", padx=12, pady=(10, 4))
        self.txt_errors = tk.Text(self.tab_validation, height=8, wrap="word")
        self.txt_errors.pack(fill="both", expand=True, padx=12)
        self.lbl_val_warns = ttk.Label(self.tab_validation, font=("Segoe UI", 10, "bold"))
        self.lbl_val_warns.pack(anchor="w", padx=12, pady=(10, 4))
        self.txt_warns = tk.Text(self.tab_validation, height=6, wrap="word")
        self.txt_warns.pack(fill="both", expand=True, padx=12)
        self.lbl_val_ok = ttk.Label(self.tab_validation)
        self.lbl_val_ok.pack(anchor="w", padx=12, pady=8)
        btns = ttk.Frame(self.tab_validation)
        btns.pack(fill="x", padx=12, pady=8)
        self.btn_save = ttk.Button(btns, command=self._on_save)
        self.btn_save.pack(side="right")
        self.btn_tech = ttk.Button(btns, command=self._toggle_issue_technical)
        self.btn_tech.pack(side="right", padx=8)
        jump = ttk.Frame(self.tab_validation)
        jump.pack(fill="x", padx=12, pady=(0, 8))
        self.btn_go_tools = ttk.Button(jump, command=lambda: self._goto_tab(TAB_TOOLS))
        self.btn_go_vocab = ttk.Button(jump, command=lambda: self._goto_tab(TAB_VOCAB))
        self.btn_go_seed = ttk.Button(jump, command=lambda: self._goto_tab(TAB_SEED))
        self.btn_go_tools.pack(side="left")
        self.btn_go_vocab.pack(side="left", padx=6)
        self.btn_go_seed.pack(side="left")

    def _build_dryrun_tab(self) -> None:
        top = ttk.Frame(self.tab_dryrun)
        top.pack(fill="x", padx=10, pady=10)
        self.lbl_scenario = ttk.Label(top)
        self.lbl_scenario.pack(side="left")
        self.cmb_scenario = ttk.Combobox(top, state="readonly", width=36)
        self.cmb_scenario.pack(side="left", padx=8)
        self.btn_dryrun = ttk.Button(top, command=self._on_dry_run)
        self.btn_dryrun.pack(side="left")
        self._make_help_button(top, "dryrun").pack(side="right")
        self.lbl_dry_summary = ttk.Label(self.tab_dryrun, wraplength=900)
        self.lbl_dry_summary.pack(anchor="w", padx=12)
        self.txt_dryrun = tk.Text(self.tab_dryrun, wrap="word")
        self.txt_dryrun.pack(fill="both", expand=True, padx=12, pady=8)
        extra = ttk.Frame(self.tab_dryrun)
        extra.pack(fill="x", padx=12, pady=(0, 8))
        self.btn_full_log = ttk.Button(extra, command=self._show_last_log)
        self.btn_memory = ttk.Button(extra, command=self._show_last_memory)
        self.btn_full_log.pack(side="left")
        self.btn_memory.pack(side="left", padx=8)
        self._last_dry = None

    # ------------------------------------------------------------------ language / screens
    def _set_language(self, lang: str) -> None:
        self.i18n.set_language(lang)
        self._apply_language()
        if self.controller.has_draft():
            self._refresh_editor()
        else:
            self._refresh_list()

    def _highlight_lang_buttons(self) -> None:
        active = {"relief": "sunken", "bg": "#dbeafe"}
        idle = {"relief": "raised", "bg": _idle_button_bg(self.btn_lang_en)}
        if self.i18n.lang == "en":
            self.btn_lang_en.configure(**active)
            self.btn_lang_ru.configure(**idle)
        else:
            self.btn_lang_ru.configure(**active)
            self.btn_lang_en.configure(**idle)

    def _apply_language(self) -> None:
        self.title(self.t("app.title"))
        self.lbl_title.configure(text=self.t("app.title"))
        self._highlight_lang_buttons()
        for btn in self._help_buttons.values():
            btn.configure(text=self.t("help.button"))
        self.lbl_list_heading.configure(text=self.t("list.heading"))
        self.btn_new.configure(text=self.t("list.new"))
        self.btn_open.configure(text=self.t("list.open"))
        self.lbl_list_empty.configure(text=self.t("list.empty"))
        self.btn_back.configure(text=self.t("list.back"))
        self.btn_history.configure(text=self.t("val.history"))
        self._sync_save_buttons()
        self.btn_wiz_back.configure(text=self.t("wizard.back"))
        self.btn_wiz_next.configure(text=self.t("wizard.next"))
        for idx, key in enumerate(TAB_KEYS):
            self.notebook.tab(idx, text=self.t(key))
        self.btn_add_server.configure(text=self.t("servers.add"))
        self.lbl_servers_intro.configure(text=self.t("servers.intro"))
        self.lbl_servers_placeholder.configure(text=self.t("servers.placeholder"))
        self.btn_discover.configure(text=self.t("tools.discover"))
        self.btn_add_tool.configure(text=self.t("tools.add_manual"))
        self.lbl_tools_server.configure(text=self.t("tools.server"))
        self.lbl_high_note.configure(text=self.t("tools.high_note"))
        self.lbl_vocab_intro.configure(text=self.t("vocab.intro"))
        self.btn_add_vocab.configure(text=self.t("vocab.add"))
        self.lbl_wait_note.configure(text=self.t("vocab.wait_note"))
        self.lbl_affect_what.configure(text=self.t("affect.what"))
        self.btn_new_event.configure(text=self.t("affect.new_event"))
        self.btn_del_event.configure(text=self.t("affect.delete_event"))
        self.lbl_valence.configure(text=self.t("affect.valence"))
        self.lbl_valence_bad.configure(text=self.t("affect.valence_bad"))
        self.lbl_valence_good.configure(text=self.t("affect.valence_good"))
        self.lbl_arousal.configure(text=self.t("affect.arousal"))
        self.lbl_arousal_calm.configure(text=self.t("affect.arousal_calm"))
        self.lbl_arousal_alarm.configure(text=self.t("affect.arousal_alarm"))
        self.frm_presets.configure(text=self.t("affect.presets"))
        self.btn_save_preset.configure(text=self.t("affect.save_preset"))
        self.btn_preset_catalog.configure(text=self.t("affect.preset_catalog"))
        self.lbl_affect_tags.configure(text=self.t("affect.tags"))
        self.btn_add_event_tag.configure(text=self.t("tools.add_tag"))
        self.btn_advanced.configure(text=self.t("affect.advanced"))
        self.frm_advanced.configure(text=self.t("affect.advanced"))
        self.frm_preview.configure(text=self.t("affect.preview"))
        self.lbl_preview_hint.configure(text=self.t("affect.preview_hint"))
        self.frm_outcome.configure(text=self.t("affect.outcome_title"))
        self.lbl_intensity.configure(text=self.t("affect.intensity"))
        self.lbl_arousal_full.configure(text=self.t("affect.arousal_full"))
        self.lbl_arousal_hint.configure(text=self.t("affect.arousal_negative_hint"))
        for axis, lbl in self.lbl_extra.items():
            lbl.configure(text=self.t(f"affect.axis.{axis}"))
        for btn in self.btn_reset_axis.values():
            btn.configure(text=self.t("affect.reset_axis"))
        self._rebuild_preset_buttons()
        self._refresh_outcome_help()
        self.lbl_seed_ro.configure(text=self.t("seed.readonly"))
        self.btn_migrate.configure(text=self.t("seed.migrate"))
        self.btn_add_lesson.configure(text=self.t("seed.add"))
        self.btn_edit_lesson.configure(text=self.t("seed.edit"))
        self.btn_del_lesson.configure(text=self.t("seed.delete"))
        self.btn_seed_mode.configure(
            text=self.t("seed.narrative" if self._seed_technical else "seed.technical")
        )
        self.lbl_val_errors.configure(text=self.t("val.errors"))
        self.lbl_val_warns.configure(text=self.t("val.warnings"))
        self.btn_tech.configure(
            text=self.t("val.hide_technical" if self._show_issue_technical else "val.technical")
        )
        self.btn_go_tools.configure(text=self.t("val.go_tools"))
        self.btn_go_vocab.configure(text=self.t("val.go_vocab"))
        self.btn_go_seed.configure(text=self.t("val.go_lesson"))
        self.lbl_scenario.configure(text=self.t("dryrun.scenario"))
        self.btn_dryrun.configure(text=self.t("dryrun.run"))
        self.btn_full_log.configure(text=self.t("dryrun.log"))
        self.btn_memory.configure(text=self.t("dryrun.memory"))
        self.lbl_emp_heading.configure(text=self.t("emp.heading"))
        self.lbl_emp_empty.configure(text=self.t("emp.empty"))
        self.btn_emp_new.configure(text=self.t("emp.new"))
        self.btn_emp_back.configure(text=self.t("emp.back"))
        self.lbl_emp_stale.configure(text=self.t("emp.stale"))
        self.btn_emp_restart.configure(text=self.t("emp.restart"))
        self.lbl_emp_roles.configure(text=self.t("emp.roles"))
        self.btn_emp_add_role.configure(text=self.t("emp.add_role"))
        self.lbl_emp_tick.configure(text=self.t("emp.tick"))
        self.lbl_emp_sensor.configure(text=self.t("emp.sensor"))
        self.lbl_emp_sleep.configure(text=self.t("emp.sleep_min"))
        self.lbl_emp_seconds.configure(text=self.t("emp.seconds"))
        self.lbl_emp_window.configure(text=self.t("emp.sleep_window"))
        self.lbl_emp_fatigue.configure(text=self.t("emp.fatigue"))
        self.lbl_emp_sleep_hint.configure(text=self.t("emp.sleep_hint"))
        self.btn_emp_start.configure(text=self.t("emp.start"))
        self.btn_emp_stop.configure(text=self.t("emp.stop"))
        self.btn_emp_reset.configure(text=self.t("emp.reset_memory"))
        self.btn_emp_delete.configure(text=self.t("emp.delete"))
        self.lbl_emp_approval.configure(text=self.t("emp.approval"))
        self.btn_emp_alerts_clear.configure(text=self.t("emp.alerts_clear"))
        self.lbl_emp_log.configure(text=self.t("emp.log"))
        self.lbl_emp_narrative.configure(text=self.t("emp.narrative"))
        self._fill_scenario_combo()
        if self._screen == "home":
            self._refresh_employees(rebuild=True)
        elif self._screen == "employee":
            self._emp_card_fp.clear()
            self._refresh_employee_card()

    def _fill_scenario_combo(self) -> None:
        labels = [self.t(SCENARIO_I18N[key]) for key in SCENARIOS]
        current = self.cmb_scenario.get()
        self.cmb_scenario["values"] = labels
        if current in labels:
            self.cmb_scenario.set(current)
        else:
            default = SCENARIOS.index(SCENARIO_STOCK_CRITICAL)
            self.cmb_scenario.set(labels[default])

    def _show_list(self) -> None:
        self._cancel_emp_poll()
        self.editor_frame.pack_forget()
        self.employee_card_frame.pack_forget()
        self.home_frame.pack(fill="both", expand=True)
        self._screen = "home"
        self._current_employee_id = ""
        self._refresh_list()
        self._refresh_employees()
        self.lbl_status.configure(text=self.t("statusbar.ready"))

    def _flush_focus(self) -> None:
        """Commit Entry FocusOut handlers (URL, login, password) before save/leave."""
        self.focus_set()
        self.update_idletasks()

    def _sync_save_buttons(self, report: Optional[Any] = None) -> None:
        if not hasattr(self, "btn_save_bar"):
            return
        if not self.controller.has_draft():
            label = self.t("val.save")
            self.btn_save_bar.configure(text=label, state="disabled")
            self.btn_save.configure(text=label, state="disabled")
            return
        report = report or self.controller.validate()
        if report.can_save:
            label = self.t("val.save_dirty") if self.controller.dirty else self.t("val.save")
            state = "normal"
        else:
            label = self.t("val.save_blocked")
            state = "disabled"
        self.btn_save_bar.configure(text=label, state=state)
        self.btn_save.configure(text=label, state=state)

    def _confirm_leave_editor(self) -> bool:
        self._flush_focus()
        if not self.controller.has_draft() or not self.controller.dirty:
            return True
        answer = messagebox.askyesnocancel(
            self.t("save.leave_title"),
            self.t("save.leave_body"),
            parent=self,
        )
        if answer is None:
            return False
        if not answer:
            return True
        try:
            self.controller.save(confirmed=True)
        except ConfiguratorError as exc:
            messagebox.showerror(self.t("error.title"), str(exc), parent=self)
            self._goto_tab(TAB_VALIDATION)
            return False
        self._note_role_saved()
        self._on_changed()
        return True

    def _on_back(self) -> None:
        if not self._confirm_leave_editor():
            return
        self._show_list()

    def _on_close(self) -> None:
        if self.controller.has_draft() and not self._confirm_leave_editor():
            return
        running = self.employee_host.running_count()
        if running:
            if not messagebox.askyesno(
                self.t("emp.close_title"),
                self.t("emp.close_running", n=running),
                parent=self,
            ):
                return
            self.employee_host.stop_all()
        self.destroy()

    def _show_editor(self) -> None:
        self._cancel_emp_poll()
        self.home_frame.pack_forget()
        self.employee_card_frame.pack_forget()
        self.editor_frame.pack(fill="both", expand=True)
        self._screen = "editor"
        self._sync_wizard_chrome()
        self._refresh_editor()

    def _refresh_list(self) -> None:
        self._role_items = list_roles(self.controller.roles_root)
        self.lst_roles.delete(0, "end")
        if not self._role_items:
            self.lbl_list_empty.pack(padx=12, pady=8)
            return
        self.lbl_list_empty.pack_forget()
        for item in self._role_items:
            if item.status == "valid":
                badge = "✓ " + self.t("status.valid")
            elif item.status == "warnings":
                n = item.status_detail.count(";") + 1 if item.status_detail else 1
                badge = "⚠ " + self.t("status.warnings", n=n)
            else:
                badge = "✗ " + self.t("status.error")
            meta = self.t(
                "list.meta",
                domain=self._tag_label(item.domain) if item.domain else item.domain,
                tools=item.n_tools,
                lessons=item.n_lessons,
                when=format_relative_mtime(item.mtime, lang=self.i18n.lang),
            )
            self.lst_roles.insert("end", f"{item.display_name}    {badge}    {meta}")

    def _open_selected(self) -> None:
        selection = self.lst_roles.curselection()
        if not selection:
            return
        item = self._role_items[int(selection[0])]
        try:
            self.controller.open_role(item.config_path)
        except (ConfiguratorError, OSError) as exc:
            messagebox.showerror(self.t("error.title"), str(exc), parent=self)
            return
        self._wizard_step = 0
        title = self.controller.draft().get("display_name") or item.display_name
        self.lbl_editor_title.configure(text=str(title))
        self._show_editor()

    def _on_new_role(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title(self.t("new.title"))
        dialog.transient(self)
        dialog.grab_set()
        ttk.Label(dialog, text=self.t("new.display_name")).grid(
            row=0, column=0, padx=8, pady=8, sticky="w",
        )
        ent_name = ttk.Entry(dialog, width=36)
        ent_name.grid(row=0, column=1, padx=8, pady=8)
        ent_name.focus_set()

        def accept() -> None:
            try:
                self.controller.new_role(ent_name.get())
            except ConfiguratorError as exc:
                messagebox.showerror(self.t("error.title"), str(exc), parent=dialog)
                return
            dialog.destroy()
            self._wizard_step = 0
            self.lbl_editor_title.configure(text=self.controller.draft().get("display_name") or "")
            self._show_editor()

        btns = ttk.Frame(dialog)
        btns.grid(row=1, column=0, columnspan=2, pady=10)
        ttk.Button(btns, text=self.t("new.create"), command=accept).pack(side="left", padx=6)
        ttk.Button(btns, text=self.t("new.cancel"), command=dialog.destroy).pack(side="left")

    # ------------------------------------------------------------------ refresh
    def _on_changed(self) -> None:
        self._refresh_editor()

    def _refresh_editor(self) -> None:
        if not self.controller.has_draft():
            return
        self._sync_wizard_chrome()
        self._refresh_servers()
        self._refresh_tools()
        self._refresh_vocab()
        self._refresh_affect()
        self._refresh_seed()
        self._refresh_validation()
        self._update_status_bar()

    def _sync_wizard_chrome(self) -> None:
        wizard = self.controller.wizard_mode
        if wizard:
            self.lbl_wizard.pack(fill="x", padx=12, pady=(6, 0))
            self.lbl_wizard.configure(text=self.t("wizard.banner", step=self._wizard_step + 1))
            self.wizard_nav.pack(fill="x", padx=12, pady=4)
            self.btn_wiz_next.configure(
                text=self.t("wizard.finish") if self._wizard_step >= WIZARD_LAST_CONTENT else self.t("wizard.next")
            )
        else:
            self.lbl_wizard.pack_forget()
            self.wizard_nav.pack_forget()
        for idx in range(N_TABS):
            if not wizard:
                state = "normal"
            elif idx == TAB_DRYRUN:
                state = "disabled"
            elif idx <= self._wizard_step:
                state = "normal"
            else:
                state = "disabled"
            self.notebook.tab(idx, state=state)
        if wizard:
            self.notebook.select(self._wizard_step)

    def _wizard_back(self) -> None:
        self._wizard_step = max(0, self._wizard_step - 1)
        self._sync_wizard_chrome()

    def _wizard_next(self) -> None:
        if self._wizard_step >= WIZARD_LAST_CONTENT:
            self.controller.wizard_mode = False
            self._sync_wizard_chrome()
            return
        self._wizard_step += 1
        self._sync_wizard_chrome()

    def _goto_tab(self, index: int) -> None:
        if self.controller.wizard_mode and index > self._wizard_step:
            return
        self.notebook.select(index)

    def _on_tab_changed(self) -> None:
        if not self.controller.has_draft():
            return
        current = self.notebook.index("current")
        if current == TAB_VALIDATION:
            self._refresh_validation()
        elif current == TAB_SERVERS:
            self._refresh_servers()
        elif current == TAB_TOOLS:
            self._refresh_tools()
        self._update_status_bar()

    def _update_status_bar(self) -> None:
        report = self.controller.validate()
        if report.errors:
            text = self.t("statusbar.err", n=len(report.errors))
        elif report.warnings:
            text = self.t("statusbar.warn", n=len(report.warnings))
        else:
            text = self.t(
                "statusbar.ok",
                tools=report.n_tools,
                decisions=report.n_decisions,
                lessons=report.n_lessons,
            )
        if self.controller.dirty:
            text = self.t("statusbar.dirty") + "  ·  " + text
        self.lbl_status.configure(text=text)
        self._sync_save_buttons(report)

    def _clear_inner(self, inner: ttk.Frame) -> None:
        for child in inner.winfo_children():
            child.destroy()

    def _refresh_servers(self) -> None:
        self._updating = True
        try:
            self._clear_inner(self.servers_inner)
            rows = self.controller.server_rows()
            if not rows:
                ttk.Label(self.servers_inner, text=self.t("servers.empty"), wraplength=800).pack(
                    anchor="w", padx=8, pady=8,
                )
                return
            for row in rows:
                title = row["display_name"] or row["server_id"]
                card = ttk.LabelFrame(
                    self.servers_inner,
                    text=f"{title}  ·  {row['server_id']}",
                )
                card.pack(fill="x", padx=4, pady=4)
                ttk.Label(card, text=self.t("servers.display")).grid(
                    row=0, column=0, sticky="w", padx=4, pady=2,
                )
                name_var = tk.StringVar(value=row["display_name"])
                name_ent = ttk.Entry(card, textvariable=name_var, width=36)
                name_ent.grid(row=0, column=1, sticky="w", padx=4, pady=2)
                name_ent.bind(
                    "<FocusOut>",
                    lambda _e, sid=row["server_id"], var=name_var: self._on_server_field(
                        sid, display_name=var.get(),
                    ),
                )
                ttk.Label(card, text=self.t("servers.transport")).grid(
                    row=1, column=0, sticky="w", padx=4, pady=2,
                )
                transport_var = tk.StringVar(value=row["transport"])
                transport = ttk.Combobox(
                    card, values=list(MCP_TRANSPORTS), textvariable=transport_var,
                    state="readonly", width=12,
                )
                transport.grid(row=1, column=1, sticky="w", padx=4)
                transport.bind(
                    "<<ComboboxSelected>>",
                    lambda _e, sid=row["server_id"], var=transport_var: self._on_server_field(
                        sid, transport=var.get(),
                    ),
                )
                enabled_var = tk.BooleanVar(value=row["enabled"])
                ttk.Checkbutton(
                    card, text=self.t("servers.enabled"), variable=enabled_var,
                    command=lambda sid=row["server_id"], var=enabled_var: self._on_server_field(
                        sid, enabled=bool(var.get()),
                    ),
                ).grid(row=1, column=2, sticky="w", padx=8)
                ttk.Label(card, text=self.t("servers.command")).grid(
                    row=2, column=0, sticky="w", padx=4, pady=2,
                )
                cmd_var = tk.StringVar(value=row["command"])
                cmd_ent = ttk.Entry(card, textvariable=cmd_var, width=36)
                cmd_ent.grid(row=2, column=1, columnspan=2, sticky="w", padx=4)
                cmd_ent.bind(
                    "<FocusOut>",
                    lambda _e, sid=row["server_id"], var=cmd_var: self._on_server_field(
                        sid, command=var.get(),
                    ),
                )
                ttk.Label(card, text=self.t("servers.args")).grid(
                    row=3, column=0, sticky="w", padx=4, pady=2,
                )
                args_var = tk.StringVar(value=row["args_text"])
                args_ent = ttk.Entry(card, textvariable=args_var, width=36)
                args_ent.grid(row=3, column=1, columnspan=2, sticky="w", padx=4)
                args_ent.bind(
                    "<FocusOut>",
                    lambda _e, sid=row["server_id"], var=args_var: self._on_server_field(
                        sid, args=var.get(),
                    ),
                )
                ttk.Label(card, text=self.t("servers.url")).grid(
                    row=4, column=0, sticky="w", padx=4, pady=2,
                )
                url_var = tk.StringVar(value=row["url"])
                url_ent = ttk.Entry(card, textvariable=url_var, width=36)
                url_ent.grid(row=4, column=1, columnspan=2, sticky="w", padx=4)
                url_ent.bind(
                    "<FocusOut>",
                    lambda _e, sid=row["server_id"], var=url_var: self._on_server_field(
                        sid, url=var.get(),
                    ),
                )
                ttk.Label(card, text=self.t("servers.username")).grid(
                    row=5, column=0, sticky="w", padx=4, pady=2,
                )
                user_var = tk.StringVar(value=row["username"])
                user_ent = ttk.Entry(card, textvariable=user_var, width=36)
                user_ent.grid(row=5, column=1, columnspan=2, sticky="w", padx=4)
                user_ent.bind(
                    "<FocusOut>",
                    lambda _e, sid=row["server_id"], var=user_var: self._on_server_field(
                        sid, username=var.get(),
                    ),
                )
                ttk.Label(card, text=self.t("servers.password")).grid(
                    row=6, column=0, sticky="w", padx=4, pady=2,
                )
                pass_var = tk.StringVar(value=row["password"])
                pass_ent = ttk.Entry(card, textvariable=pass_var, width=36, show="*")
                pass_ent.grid(row=6, column=1, columnspan=2, sticky="w", padx=4)
                pass_ent.bind(
                    "<FocusOut>",
                    lambda _e, sid=row["server_id"], var=pass_var: self._on_server_field(
                        sid, password=var.get(),
                    ),
                )
                count_key = (
                    "servers.tools_count" if row["n_catalog"]
                    else "servers.tools_count_no_catalog"
                )
                ttk.Label(
                    card,
                    text=self.t(
                        count_key,
                        catalog=row["n_catalog"],
                        included=row["n_included"],
                    ),
                ).grid(
                    row=7, column=0, columnspan=2, sticky="w", padx=8, pady=4,
                )
                ttk.Button(
                    card, text=self.t("servers.remove"),
                    command=lambda sid=row["server_id"], name=title: self._on_remove_server(sid, name),
                ).grid(row=7, column=2, sticky="e", padx=4, pady=4)
        finally:
            self._updating = False

    def _on_server_field(self, server_id: str, **fields: Any) -> None:
        if self._updating:
            return
        try:
            self.controller.update_server(server_id, **fields)
        except ConfiguratorError as exc:
            messagebox.showerror(self.t("error.title"), str(exc), parent=self)
            self._refresh_servers()
            return
        self._update_status_bar()

    def _on_add_server(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title(self.t("servers.title"))
        dialog.transient(self)
        dialog.grab_set()
        ttk.Label(dialog, text=self.t("servers.id")).grid(
            row=0, column=0, sticky="w", padx=8, pady=6,
        )
        ent_id = ttk.Entry(dialog, width=32)
        ent_id.grid(row=0, column=1, padx=8, pady=6)
        ent_id.focus_set()
        ttk.Label(dialog, text=self.t("servers.display")).grid(
            row=1, column=0, sticky="w", padx=8, pady=6,
        )
        ent_name = ttk.Entry(dialog, width=32)
        ent_name.grid(row=1, column=1, padx=8, pady=6)
        ttk.Label(dialog, text=self.t("servers.transport")).grid(
            row=2, column=0, sticky="w", padx=8, pady=6,
        )
        transport = ttk.Combobox(
            dialog, values=list(MCP_TRANSPORTS), state="readonly", width=16,
        )
        transport.set("mock")
        transport.grid(row=2, column=1, sticky="w", padx=8, pady=6)

        def accept() -> None:
            try:
                created = self.controller.add_server(
                    ent_id.get(),
                    display_name=ent_name.get(),
                    transport=transport.get() or "mock",
                )
            except ConfiguratorError as exc:
                messagebox.showerror(self.t("error.title"), str(exc), parent=dialog)
                return
            self._current_server_id = str(created.get("server_id") or "")
            dialog.destroy()
            self._on_changed()

        ttk.Button(dialog, text=self.t("new.create"), command=accept).grid(
            row=3, column=1, pady=10, sticky="e", padx=8,
        )

    def _on_remove_server(self, server_id: str, display_name: str) -> None:
        if not messagebox.askyesno(
            self.t("servers.remove"),
            self.t("servers.remove_confirm", server=display_name or server_id),
            parent=self,
        ):
            return
        try:
            self.controller.remove_server(server_id)
        except ConfiguratorError as exc:
            messagebox.showerror(self.t("error.title"), str(exc), parent=self)
            return
        if self._current_server_id == server_id:
            self._current_server_id = ""
        self._on_changed()

    def _on_tools_server_changed(self) -> None:
        self._current_server_id = str(self.cmb_tools_server.get() or "")
        self._refresh_tools()

    def _refresh_tools(self) -> None:
        servers = self.controller.server_rows()
        ids = [row["server_id"] for row in servers]
        if self._current_server_id not in ids:
            self._current_server_id = ids[0] if ids else ""
        self.cmb_tools_server["values"] = ids
        self.cmb_tools_server.set(self._current_server_id)
        self._clear_inner(self.tools_inner)
        if not self._current_server_id:
            ttk.Label(self.tools_inner, text=self.t("tools.no_server"), wraplength=800).pack(
                anchor="w", padx=8, pady=8,
            )
            ttk.Button(
                self.tools_inner, text=self.t("tools.go_servers"),
                command=lambda: self._goto_tab(TAB_SERVERS),
            ).pack(anchor="w", padx=8, pady=4)
            return
        vocab = self.controller.declared_action_types()
        for row in self.controller.tool_rows(server_id=self._current_server_id):
            card = ttk.LabelFrame(self.tools_inner, text=row["tool_id"])
            card.pack(fill="x", padx=4, pady=4)
            ttk.Label(card, text=row["display_name"]).grid(row=0, column=1, sticky="w", padx=4)
            included = tk.BooleanVar(value=row["included"])
            chk = ttk.Checkbutton(
                card, text=self.t("tools.included"), variable=included,
                command=lambda tid=row["tool_id"], var=included: self._toggle_included(tid, var),
            )
            chk.grid(row=0, column=0, sticky="w", padx=4, pady=2)
            ttk.Label(card, text=row["description"], wraplength=700).grid(
                row=1, column=0, columnspan=4, sticky="w", padx=8,
            )
            ttk.Label(card, text=self.t("tools.risk")).grid(row=2, column=0, sticky="w", padx=4)
            risk_var = tk.StringVar(value=self._risk_label(row["risk_level"]))
            combo = ttk.Combobox(
                card, values=[self._risk_label(value) for value in RISK_VALUES],
                textvariable=risk_var, state="readonly", width=18,
            )
            combo.grid(row=2, column=1, sticky="w")
            combo.bind(
                "<<ComboboxSelected>>",
                lambda _e, tid=row["tool_id"], var=risk_var: self._on_risk_change(
                    tid, self._risk_code(var.get()),
                ),
            )
            if row["included"] and not row["risk_confirmed"]:
                ttk.Label(card, text="💡 " + self.t("tools.heuristic")).grid(
                    row=2, column=2, sticky="w", padx=6,
                )
                ttk.Button(
                    card, text=self.t("tools.confirm_risk"),
                    command=lambda tid=row["tool_id"]: self._confirm_risk(tid),
                ).grid(row=2, column=3, padx=4)
            approval_var = tk.BooleanVar(value=row["requires_approval"])
            approval = ttk.Checkbutton(
                card,
                text=(
                    self.t("tools.approval_locked") if row["approval_locked_on"]
                    else self.t("tools.approval")
                ),
                variable=approval_var,
                command=lambda tid=row["tool_id"], var=approval_var: self._on_approval(tid, var),
            )
            approval.grid(row=3, column=0, columnspan=2, sticky="w", padx=4, pady=2)
            if row["approval_disabled"]:
                approval.state(["disabled"])
            poll_var = tk.BooleanVar(value=row["poll"])
            poll_chk = ttk.Checkbutton(
                card,
                text=self.t("tools.poll"),
                variable=poll_var,
                command=lambda tid=row["tool_id"], var=poll_var: self._on_poll(tid, var),
            )
            poll_chk.grid(row=3, column=2, sticky="w", padx=4, pady=2)
            if not row["poll_enabled"]:
                poll_chk.state(["disabled"])
            if row["included"] and not row["poll_enabled"]:
                ttk.Label(card, text=self.t("tools.poll_write"), foreground="#666").grid(
                    row=3, column=3, sticky="w", padx=4,
                )
            if row["irreversible_excluded"]:
                ttk.Label(card, text="🔴 " + self.t("risk.irreversible") + "  " + self.t("tools.not_included")).grid(
                    row=4, column=0, columnspan=4, sticky="w", padx=8,
                )
            if row["included"]:
                ttk.Label(card, text=self.t("tools.decisions")).grid(
                    row=5, column=0, sticky="nw", padx=4, pady=4,
                )
                box = ttk.Frame(card)
                box.grid(row=5, column=1, columnspan=3, sticky="w")
                selected = set(row["action_types"])
                for action in vocab:
                    av = tk.BooleanVar(value=action in selected)
                    ttk.Checkbutton(
                        box,
                        text=self._action_label(action),
                        variable=av,
                        command=lambda tid=row["tool_id"], act=action, var=av: self._toggle_tool_action(tid, act, var),
                    ).pack(side="left", padx=2)
                ttk.Button(
                    box, text=self.t("tools.add_decision"),
                    command=self._on_add_vocab_or_jump,
                ).pack(side="left", padx=4)
                ttk.Label(card, text=self.t("tools.tags") + ": " + ", ".join(
                    self._tag_label(tag) for tag in row["domain_tags"]
                )).grid(
                    row=6, column=0, columnspan=3, sticky="w", padx=8, pady=2,
                )
                ttk.Button(
                    card, text=self.t("tools.add_tag"),
                    command=lambda tid=row["tool_id"]: self._add_tool_tag(tid),
                ).grid(row=6, column=3, sticky="e")
                if row["poll"] and row["poll_required"]:
                    ttk.Label(card, text=self.t("tools.poll_defaults")).grid(
                        row=7, column=0, sticky="nw", padx=4, pady=4,
                    )
                    defaults_box = ttk.Frame(card)
                    defaults_box.grid(row=7, column=1, columnspan=3, sticky="w")
                    stored = row.get("poll_defaults") or {}
                    for name in row["poll_required"]:
                        row_fr = ttk.Frame(defaults_box)
                        row_fr.pack(anchor="w", pady=1)
                        ttk.Label(row_fr, text=f"{name}:").pack(side="left")
                        entry = ttk.Entry(row_fr, width=18)
                        entry.insert(0, str(stored.get(name, "") or ""))
                        entry.pack(side="left", padx=4)
                        entry.bind(
                            "<FocusOut>",
                            lambda _e, tid=row["tool_id"], key=name, widget=entry: (
                                self.controller.set_poll_default(tid, key, widget.get()),
                                self._update_status_bar(),
                            ),
                        )

    def _toggle_included(self, tool_id: str, var: tk.BooleanVar) -> None:
        self.controller.set_tool_included(
            tool_id, bool(var.get()), server_id=self._current_server_id or None,
        )
        self._on_changed()

    def _on_poll(self, tool_id: str, var: tk.BooleanVar) -> None:
        applied = self.controller.set_tool_poll(tool_id, bool(var.get()))
        if not applied:
            self._on_changed()
            return
        self._on_changed()

    def _on_approval(self, tool_id: str, var: tk.BooleanVar) -> None:
        # G2: HIGH_WRITE / IRREVERSIBLE cannot become False through this path.
        applied = self.controller.set_requires_approval(tool_id, bool(var.get()))
        if not applied:
            self._on_changed()
            return
        self._update_status_bar()

    def _on_risk_change(self, tool_id: str, risk_level: str) -> None:
        try:
            self.controller.set_tool_risk(tool_id, risk_level)
        except RiskDowngradeRequired as exc:
            reason = self._ask_downgrade(exc.heuristic, exc.requested)
            if not reason:
                self._refresh_tools()
                return
            try:
                self.controller.set_tool_risk(tool_id, risk_level, justification=reason)
            except ConfiguratorError as err:
                messagebox.showerror(self.t("error.title"), str(err), parent=self)
                self._refresh_tools()
                return
        except ConfiguratorError as exc:
            messagebox.showerror(self.t("error.title"), str(exc), parent=self)
            self._refresh_tools()
            return
        self._on_changed()

    def _confirm_risk(self, tool_id: str) -> None:
        try:
            self.controller.confirm_heuristic_risk(tool_id)
        except ConfiguratorError as exc:
            messagebox.showerror(self.t("error.title"), str(exc), parent=self)
        self._on_changed()

    def _ask_downgrade(self, heuristic: str, requested: str) -> str:
        dialog = tk.Toplevel(self)
        dialog.title(self.t("downgrade.title"))
        dialog.transient(self)
        dialog.grab_set()
        ttk.Label(
            dialog, wraplength=420,
            text=self.t(
                "downgrade.body",
                heuristic=self._risk_label(heuristic),
                requested=self._risk_label(requested),
            ),
        ).pack(padx=12, pady=8)
        text = tk.Text(dialog, height=4, width=50)
        text.pack(padx=12, pady=4)
        result = {"value": ""}

        def accept() -> None:
            value = text.get("1.0", "end").strip()
            if not value:
                return
            result["value"] = value
            dialog.destroy()

        btns = ttk.Frame(dialog)
        btns.pack(pady=8)
        ttk.Button(btns, text=self.t("downgrade.cancel"), command=dialog.destroy).pack(side="left", padx=6)
        ttk.Button(btns, text=self.t("downgrade.confirm"), command=accept).pack(side="left")
        dialog.wait_window()
        return result["value"]

    def _toggle_tool_action(self, tool_id: str, action: str, var: tk.BooleanVar) -> None:
        current: List[str] = []
        for row in self.controller.tool_rows():
            if row["tool_id"] == tool_id:
                current = list(row["action_types"])
                break
        if var.get():
            if action not in current:
                current.append(action)
        else:
            current = [item for item in current if item != action]
        self.controller.set_tool_action_types(tool_id, current)
        self._update_status_bar()

    def _add_tool_tag(self, tool_id: str) -> None:
        tag = simpledialog.askstring(self.t("tools.tags"), self.t("prompt.tag"), parent=self)
        if not tag:
            return
        cap = None
        for row in self.controller.tool_rows():
            if row["tool_id"] == tool_id:
                cap = row
                break
        tags = list(cap["domain_tags"] if cap else [])
        if tag.strip() not in tags:
            tags.append(tag.strip())
        self.controller.set_tool_tags(tool_id, tags)
        self._on_changed()

    def _on_discover(self) -> None:
        if not self._current_server_id:
            messagebox.showinfo(self.t("tab.tools"), self.t("tools.no_server"), parent=self)
            self._goto_tab(TAB_SERVERS)
            return
        try:
            rows = self.controller.discover_tools(server_id=self._current_server_id)
        except ConfiguratorError as exc:
            messagebox.showerror(self.t("error.title"), str(exc), parent=self)
            return
        included = sum(1 for row in rows if row.get("included"))
        messagebox.showinfo(
            self.t("tab.tools"),
            self.t("tools.discover_done", n=len(rows), included=included),
            parent=self,
        )
        self._on_changed()

    def _on_add_manual_tool(self) -> None:
        if not self._current_server_id:
            messagebox.showinfo(self.t("tab.tools"), self.t("tools.no_server"), parent=self)
            self._goto_tab(TAB_SERVERS)
            return
        dialog = tk.Toplevel(self)
        dialog.title(self.t("manual.title"))
        dialog.transient(self)
        dialog.grab_set()
        fields = [
            ("manual.tool_id", "tool_id"),
            ("manual.display", "display"),
            ("manual.description", "description"),
        ]
        entries: Dict[str, ttk.Entry] = {}
        for idx, (key, name) in enumerate(fields):
            ttk.Label(dialog, text=self.t(key)).grid(row=idx, column=0, sticky="w", padx=8, pady=4)
            ent = ttk.Entry(dialog, width=40)
            ent.grid(row=idx, column=1, padx=8, pady=4)
            entries[name] = ent
        ttk.Label(
            dialog, text=f"{self.t('tools.server')}: {self._current_server_id}",
        ).grid(row=3, column=0, columnspan=2, sticky="w", padx=8, pady=4)

        def accept() -> None:
            try:
                self.controller.add_manual_tool(
                    entries["tool_id"].get(),
                    display_name=entries["display"].get(),
                    description=entries["description"].get(),
                    server_name=self._current_server_id,
                    included=True,
                )
            except ConfiguratorError as exc:
                messagebox.showerror(self.t("error.title"), str(exc), parent=dialog)
                return
            dialog.destroy()
            self._on_changed()

        ttk.Button(dialog, text=self.t("new.create"), command=accept).grid(row=4, column=1, pady=8, sticky="e")

    def _on_add_vocab_or_jump(self) -> None:
        if not self.controller.declared_action_types():
            if messagebox.askyesno(self.t("tab.vocab"), self.t("vocab.empty"), parent=self):
                self._goto_tab(TAB_VOCAB)
            return
        self._on_add_vocab()

    def _refresh_vocab(self) -> None:
        self._clear_inner(self.vocab_inner)
        rows = self.controller.vocabulary_rows()
        if not rows:
            ttk.Label(self.vocab_inner, text=self.t("vocab.empty")).pack(anchor="w", padx=8, pady=8)
            return
        for row in rows:
            title = self._action_label(row["action_type"]) or row["action_type"]
            card = ttk.LabelFrame(self.vocab_inner, text=title)
            card.pack(fill="x", padx=4, pady=4)
            desc_key = f"decision.{row['action_type']}.desc"
            description = self.t(desc_key) if self._has_i18n(desc_key) else row["description"]
            if description:
                ttk.Label(card, text=description, wraplength=800).pack(
                    anchor="w", padx=8, pady=4,
                )
            else:
                ttk.Label(card, text=self.t("vocab.desc_hint"), wraplength=800).pack(
                    anchor="w", padx=8, pady=4,
                )
            if row["used_in_tools"]:
                ttk.Label(card, text=self.t("vocab.used_in", tools=", ".join(
                    self._tool_label(tid) for tid in row["used_in_tools"]
                ))).pack(
                    anchor="w", padx=8,
                )
            else:
                ttk.Label(card, text=self.t("vocab.unused")).pack(anchor="w", padx=8)
            if row["needs_motor_adapter"]:
                ttk.Label(card, text=self.t("vocab.needs_code")).pack(anchor="w", padx=8, pady=4)

    def _on_add_vocab(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title(self.t("vocab.add_title"))
        dialog.transient(self)
        dialog.grab_set()
        dialog.geometry("560x460")

        choices = self.controller.motor_adapter_decision_choices()
        source = tk.StringVar(value="adapter" if choices else "custom")
        selected_code = tk.StringVar(value=choices[0]["action_type"] if choices else "")

        ttk.Label(dialog, text=self.t("vocab.source_label"), font=("Segoe UI", 10, "bold")).pack(
            anchor="w", padx=12, pady=(12, 4),
        )
        ttk.Radiobutton(
            dialog, text=self.t("vocab.from_adapter"), variable=source, value="adapter",
        ).pack(anchor="w", padx=16)
        pick_row = ttk.Frame(dialog)
        pick_row.pack(fill="x", padx=32, pady=(0, 6))
        ttk.Label(pick_row, text=self.t("vocab.adapter_pick")).pack(side="left")
        labels_by_code = {
            row["action_type"]: self._action_label(row["action_type"])
            for row in choices
        }
        combo_values = [labels_by_code[row["action_type"]] for row in choices]
        cmb = ttk.Combobox(pick_row, state="readonly" if choices else "disabled", width=36, values=combo_values)
        cmb.pack(side="left", padx=8)
        if combo_values:
            cmb.set(combo_values[0])
        elif not choices:
            ttk.Label(dialog, text=self.t("vocab.adapter_empty"), wraplength=500).pack(
                anchor="w", padx=32, pady=(0, 4),
            )

        ttk.Radiobutton(
            dialog, text=self.t("vocab.from_custom"), variable=source, value="custom",
        ).pack(anchor="w", padx=16, pady=(4, 8))

        ttk.Label(dialog, text=self.t("vocab.name_label"), font=("Segoe UI", 10, "bold")).pack(
            anchor="w", padx=12, pady=(4, 2),
        )
        ttk.Label(dialog, text=self.t("vocab.name_hint"), wraplength=520).pack(anchor="w", padx=12)
        ent_name = ttk.Entry(dialog, width=56)
        ent_name.pack(fill="x", padx=12, pady=6)

        ttk.Label(dialog, text=self.t("vocab.desc_label"), font=("Segoe UI", 10, "bold")).pack(
            anchor="w", padx=12, pady=(8, 2),
        )
        ttk.Label(dialog, text=self.t("vocab.desc_hint"), wraplength=520).pack(anchor="w", padx=12)
        txt_desc = tk.Text(dialog, height=4, width=56, wrap="word")
        txt_desc.pack(fill="both", expand=True, padx=12, pady=6)

        def _choice_for_label(label: str) -> Optional[dict]:
            for row in choices:
                if labels_by_code.get(row["action_type"]) == label:
                    return row
            return None

        def _fill_from_choice() -> None:
            if source.get() != "adapter":
                return
            row = _choice_for_label(cmb.get())
            if row is None:
                return
            selected_code.set(row["action_type"])
            name = self._action_label(row["action_type"])
            desc_key = f"decision.{row['action_type']}.desc"
            desc = self.t(desc_key) if self._has_i18n(desc_key) else row["description"]
            ent_name.delete(0, "end")
            ent_name.insert(0, name)
            txt_desc.delete("1.0", "end")
            txt_desc.insert("1.0", desc)

        def _on_source() -> None:
            adapter_on = source.get() == "adapter" and bool(choices)
            cmb.configure(state="readonly" if adapter_on else "disabled")
            if adapter_on:
                _fill_from_choice()
            else:
                selected_code.set("")
                ent_name.delete(0, "end")
                txt_desc.delete("1.0", "end")
                ent_name.focus_set()

        cmb.bind("<<ComboboxSelected>>", lambda _e: _fill_from_choice())
        source.trace_add("write", lambda *_a: _on_source())
        if choices:
            _fill_from_choice()
        else:
            source.set("custom")
            ent_name.focus_set()

        def accept() -> None:
            name = ent_name.get().strip()
            description = txt_desc.get("1.0", "end").strip()
            action_id = selected_code.get().strip() if source.get() == "adapter" else ""
            try:
                self.controller.add_action_type(
                    action_type=action_id,
                    display_name=name,
                    description=description,
                )
            except ConfiguratorError as exc:
                messagebox.showerror(self.t("error.title"), str(exc), parent=dialog)
                return
            dialog.destroy()
            self._on_changed()

        btns = ttk.Frame(dialog)
        btns.pack(fill="x", padx=12, pady=10)
        ttk.Button(btns, text=self.t("new.cancel"), command=dialog.destroy).pack(side="right")
        ttk.Button(btns, text=self.t("vocab.add_confirm"), command=accept).pack(side="right", padx=8)

    def _event_label(self, name: str) -> str:
        return self.controller.event_display_name(name, lang=self.i18n.lang)

    def _event_code_from_label(self, label: str) -> str:
        shown = str(label or "").strip()
        for name in self.controller.affective_events():
            if self._event_label(name) == shown:
                return name
        return shown

    def _refresh_affect(self) -> None:
        events = self.controller.affective_events()
        self.cmb_event["values"] = [self._event_label(name) for name in events]
        if self._current_event in events:
            self.cmb_event.set(self._event_label(self._current_event))
        elif events:
            self._current_event = events[0]
            self.cmb_event.set(self._event_label(events[0]))
        else:
            self.cmb_event.set("")
            self._current_event = ""
        self._rebuild_preset_buttons()
        self._load_event_into_sliders()

    def _rebuild_preset_buttons(self) -> None:
        rows = self.controller.list_visible_affect_presets(self.i18n.lang)
        fingerprint = tuple((row["id"], row["label"]) for row in rows)
        if fingerprint == self._preset_fp and self.preset_buttons:
            return
        self._preset_fp = fingerprint
        for child in self.preset_btn_row.winfo_children():
            child.destroy()
        self.preset_buttons = {}
        for row in rows:
            btn = ttk.Button(
                self.preset_btn_row,
                text=row["label"],
                command=lambda pid=row["id"]: self._on_preset(pid),
            )
            btn.pack(side="left", padx=6, pady=6)
            self.preset_buttons[row["id"]] = btn

    def _set_advanced_visible(self, shown: bool) -> None:
        self._advanced_shown = shown
        if shown:
            if not self.frm_advanced.winfo_ismapped():
                self.frm_advanced.pack(fill="x", padx=12, pady=(0, 8), after=self.btn_advanced)
        else:
            self.frm_advanced.pack_forget()

    def _toggle_advanced_affect(self) -> None:
        self._set_advanced_visible(not self._advanced_shown)

    def _load_event_into_sliders(self) -> None:
        name = self._event_code_from_label(self.cmb_event.get())
        self._current_event = name
        if not name:
            self.lbl_preview.configure(text="")
            return
        self._updating = True
        try:
            data = self.controller.get_affective_event(name)
            valence = float(data["valence"])
            arousal = float(data["arousal"])
            self.scl_valence.set(valence)
            self.scl_arousal.set(max(0.0, arousal))
            self.scl_arousal_full.set(arousal)
            self.lbl_valence_val.configure(text=f"({valence:.2f})")
            self.lbl_arousal_val.configure(text=f"({arousal:.2f})")
            self.lbl_tag_values.configure(text=", ".join(self._tag_label(tag) for tag in data["tags"]))
            self.scl_intensity.set(float(data.get("intensity", 0.35)))
            self._axis_set = set(data.get("axes_set") or [])
            for axis, scale in self.scl_extra.items():
                scale.set(float(data[axis]) if axis in data else 0.0)
            expand = bool(self._axis_set) or arousal < 0 or abs(float(data.get("intensity", 0.35)) - 0.35) > 1e-9
            if expand:
                self._set_advanced_visible(True)
            if arousal < 0:
                self.lbl_arousal_hint.pack(anchor="w", padx=12)
            else:
                self.lbl_arousal_hint.pack_forget()
        finally:
            self._updating = False
        self._update_affect_preview()

    def _commit_affect(self) -> None:
        if self._updating or not self._current_event:
            return
        valence = float(self.scl_valence.get())
        arousal = float(self.scl_arousal_full.get()) if self._advanced_shown else float(self.scl_arousal.get())
        if not self._advanced_shown:
            arousal = float(self.scl_arousal.get())
        self.lbl_valence_val.configure(text=f"({valence:.2f})")
        self.lbl_arousal_val.configure(text=f"({arousal:.2f})")
        current = self.controller.get_affective_event(self._current_event)
        axes = {axis: float(self.scl_extra[axis].get()) for axis in self._axis_set}
        for axis in _EXTRA_AXES:
            if axis not in self._axis_set:
                axes[axis] = None
        self.controller.upsert_affective_event(
            self._current_event,
            valence,
            arousal,
            current.get("tags"),
            axes=axes,
            intensity=float(self.scl_intensity.get()),
        )
        if arousal < 0:
            self.lbl_arousal_hint.pack(anchor="w", padx=12)
        else:
            self.lbl_arousal_hint.pack_forget()
        self._update_affect_preview()
        self._update_status_bar()

    def _on_affect_slider(self) -> None:
        if self._updating:
            return
        if not self._advanced_shown:
            self._updating = True
            try:
                self.scl_arousal_full.set(float(self.scl_arousal.get()))
            finally:
                self._updating = False
        self._commit_affect()

    def _on_arousal_full(self) -> None:
        if self._updating:
            return
        val = float(self.scl_arousal_full.get())
        self._updating = True
        try:
            self.scl_arousal.set(max(0.0, val))
        finally:
            self._updating = False
        self._commit_affect()

    def _on_extra_axis(self, axis: str) -> None:
        if self._updating:
            return
        self._axis_set.add(axis)
        self._commit_affect()

    def _on_reset_axis(self, axis: str) -> None:
        self._axis_set.discard(axis)
        self._updating = True
        try:
            self.scl_extra[axis].set(0.0)
        finally:
            self._updating = False
        self._commit_affect()

    def _update_affect_preview(self) -> None:
        if not self._current_event:
            self.lbl_preview.configure(text="")
            return
        preview = self.controller.preview_affective_event(self._current_event)
        emotions = preview.get("emotions") or []
        if emotions:
            emo = " · ".join(
                f"{item.get('emotion')} {float(item.get('activation', 0.0)):.2f}"
                for item in emotions
            )
        else:
            emo = self.t("affect.preview_neutral")
        bias = preview.get("decision_bias") or {}
        ranks = preview.get("rank_weights") or {}
        bias_txt = " · ".join(
            f"{self.t('affect.bias.' + key)} {float(bias.get(key, 0.0)):+.2f}"
            for key in (preview.get("bias_keys") or bias)
        )
        rank_txt = " · ".join(
            f"{self.t('affect.rank.' + key)} {float(ranks.get(key, 0.0)):.2f}"
            for key in (preview.get("rank_keys") or ranks)
        )
        self.lbl_preview.configure(text=f"{emo}\n{bias_txt}\n{rank_txt}")

    def _refresh_outcome_help(self) -> None:
        lines = []
        for row in self.controller.outcome_impulse_rows():
            vec = row.get("vector") or {}
            bits = " ".join(f"{axis}{float(vec[axis]):+.1f}" for axis in vec if abs(float(vec[axis])) > 1e-9)
            lines.append(f"{row['status']}: {bits}")
        self.lbl_outcome.configure(text="\n".join(lines) if lines else self.t("affect.outcome_help"))

    def _on_preset(self, preset: str) -> None:
        if not self._current_event:
            return
        try:
            self.controller.apply_affect_preset(self._current_event, preset)
        except ConfiguratorError as exc:
            messagebox.showerror(self.t("error.title"), str(exc), parent=self)
            return
        self._load_event_into_sliders()
        self._update_status_bar()

    def _on_new_event(self) -> None:
        name = simpledialog.askstring(self.t("affect.new_event"), self.t("prompt.event"), parent=self)
        if not name:
            return
        self.controller.upsert_affective_event(name.strip(), 0.0, 0.5, [])
        self._current_event = name.strip()
        self._on_changed()

    def _on_delete_event(self) -> None:
        if not self._current_event:
            return
        if not messagebox.askyesno(self.t("affect.delete_event"), self.t("affect.delete_confirm"), parent=self):
            return
        self.controller.remove_affective_event(self._current_event)
        self._current_event = ""
        self._on_changed()

    def _on_save_preset(self) -> None:
        if not self._current_event:
            return
        pid = simpledialog.askstring(self.t("affect.save_preset"), self.t("affect.preset_id"), parent=self)
        if not pid:
            return
        label_en = simpledialog.askstring(self.t("affect.save_preset"), self.t("affect.preset_label_en"), parent=self) or ""
        label_ru = simpledialog.askstring(self.t("affect.save_preset"), self.t("affect.preset_label_ru"), parent=self) or ""
        factory_ids = {row["id"] for row in self.controller.list_all_affect_presets() if row["builtin"]}
        if pid.strip() in factory_ids:
            if not messagebox.askyesno(self.t("affect.save_preset"), self.t("affect.preset_overlay_warn"), parent=self):
                return
        try:
            self.controller.save_affect_preset(
                pid.strip(), label_en, label_ru, event_name=self._current_event,
            )
        except ConfiguratorError as exc:
            messagebox.showerror(self.t("error.title"), str(exc), parent=self)
            return
        self._preset_fp = ""
        self._rebuild_preset_buttons()

    def _open_preset_catalog(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title(self.t("affect.preset_catalog"))
        dialog.transient(self)
        dialog.grab_set()
        lst = tk.Listbox(dialog, height=12, width=50)
        lst.pack(fill="both", expand=True, padx=8, pady=8)

        def refresh_list() -> None:
            lst.delete(0, "end")
            for row in self.controller.list_all_affect_presets(self.i18n.lang):
                mark = self.t("affect.preset_builtin") if row["builtin"] else self.t("affect.preset_custom")
                if row["overlay"]:
                    mark += " · " + self.t("affect.preset_overlay")
                if row["hidden"]:
                    mark += " · " + self.t("affect.preset_hide")
                lst.insert("end", f"{row['label']}  ({row['id']}) — {mark}")

        def selected_id() -> str:
            sel = lst.curselection()
            if not sel:
                return ""
            rows = self.controller.list_all_affect_presets(self.i18n.lang)
            if int(sel[0]) >= len(rows):
                return ""
            return str(rows[int(sel[0])]["id"])

        def run(action) -> None:
            pid = selected_id()
            if not pid:
                return
            try:
                action(pid)
            except ConfiguratorError as exc:
                messagebox.showerror(self.t("error.title"), str(exc), parent=dialog)
                return
            refresh_list()
            self._preset_fp = ""
            self._rebuild_preset_buttons()

        btns = ttk.Frame(dialog)
        btns.pack(fill="x", padx=8, pady=8)
        ttk.Button(
            btns, text=self.t("affect.apply"),
            command=lambda: (self._on_preset(selected_id()), dialog.destroy()),
        ).pack(side="left")
        ttk.Button(
            btns, text=self.t("affect.preset_hide"),
            command=lambda: run(lambda pid: self.controller.hide_affect_preset(pid, True)),
        ).pack(side="left", padx=4)
        ttk.Button(
            btns, text=self.t("affect.preset_unhide"),
            command=lambda: run(lambda pid: self.controller.hide_affect_preset(pid, False)),
        ).pack(side="left", padx=4)
        ttk.Button(
            btns, text=self.t("affect.preset_restore"),
            command=lambda: run(self.controller.restore_factory_preset),
        ).pack(side="left", padx=4)
        ttk.Button(
            btns, text=self.t("affect.preset_delete"),
            command=lambda: run(self.controller.delete_affect_preset),
        ).pack(side="left", padx=4)
        ttk.Button(btns, text=self.t("new.cancel"), command=dialog.destroy).pack(side="right")
        refresh_list()

    def _on_add_event_tag(self) -> None:
        if not self._current_event:
            return
        tag = simpledialog.askstring(self.t("affect.tags"), self.t("prompt.tag"), parent=self)
        if not tag:
            return
        data = self.controller.get_affective_event(self._current_event)
        tags = list(data["tags"])
        if tag.strip() not in tags:
            tags.append(tag.strip())
        self.controller.upsert_affective_event(
            self._current_event, data["valence"], data["arousal"], tags,
        )
        self._on_changed()

    def _refresh_seed(self) -> None:
        readonly = self.controller.uses_seed_module
        if readonly:
            self.frm_seed_ro.pack(fill="x", padx=8, pady=6, before=self.frm_seed_top)
            self.btn_add_lesson.state(["disabled"])
            self.btn_edit_lesson.state(["disabled"])
            self.btn_del_lesson.state(["disabled"])
        else:
            self.frm_seed_ro.pack_forget()
            self.btn_add_lesson.state(["!disabled"])
            self.btn_edit_lesson.state(["!disabled"])
            self.btn_del_lesson.state(["!disabled"])
        self.lst_lessons.delete(0, "end")
        rows = self.controller.seed_rows(
            technical=self._seed_technical, lang=self.i18n.lang,
        )
        if not rows:
            self.lst_lessons.insert("end", self.t("seed.empty"))
            return
        for row in rows:
            self.lst_lessons.insert("end", f"{row['index'] + 1}. {row['narrative']}")

    def _toggle_seed_mode(self) -> None:
        self._seed_technical = not self._seed_technical
        self.btn_seed_mode.configure(
            text=self.t("seed.narrative" if self._seed_technical else "seed.technical")
        )
        self._refresh_seed()

    def _on_migrate(self) -> None:
        try:
            self.controller.migrate_seed_module_to_inline(write_file=bool(self.controller.path))
        except ConfiguratorError as exc:
            messagebox.showerror(self.t("error.title"), str(exc), parent=self)
            return
        self._on_changed()

    def _selected_lesson_index(self) -> Optional[int]:
        selection = self.lst_lessons.curselection()
        if not selection:
            return None
        rows = self.controller.seed_rows()
        idx = int(selection[0])
        if idx >= len(rows):
            return None
        return rows[idx]["index"]

    def _on_edit_lesson(self) -> None:
        idx = self._selected_lesson_index()
        if idx is None:
            return
        self._open_lesson_wizard(replace_index=idx)

    def _on_delete_lesson(self) -> None:
        idx = self._selected_lesson_index()
        if idx is None:
            return
        try:
            self.controller.remove_lesson(idx)
        except ConfiguratorError as exc:
            messagebox.showerror(self.t("error.title"), str(exc), parent=self)
            return
        self._on_changed()

    def _open_lesson_wizard(self, replace_index: Optional[int] = None) -> None:
        events = self.controller.affective_events()
        actions = self.controller.wizard_action_choices()
        if not events:
            messagebox.showinfo(self.t("lesson.title"), self.t("affect.new_event"), parent=self)
            self._goto_tab(TAB_AFFECT)
            return
        if not actions:
            messagebox.showinfo(self.t("lesson.title"), self.t("vocab.empty"), parent=self)
            self._goto_tab(TAB_VOCAB)
            return
        prefill: Dict[str, Any] = {}
        if replace_index is not None:
            raw = self.controller.get_lesson(replace_index)
            tokens = raw.get("context_tokens") or []
            prefill = {
                "events": [
                    tok.split(":", 1)[1] for tok in tokens
                    if str(tok).startswith("event:")
                ],
                "action": raw.get("action"),
                "consequence": raw.get("consequence"),
                "importance": float(raw.get("reward") or 0) * 10.0,
                "reinforce": bool(raw.get("reinforce")),
            }

        dialog = tk.Toplevel(self)
        dialog.title(self.t("lesson.title"))
        dialog.geometry("560x480")
        dialog.transient(self)
        dialog.grab_set()
        step = tk.IntVar(value=1)
        header = ttk.Label(dialog, font=("Segoe UI", 10, "bold"))
        header.pack(anchor="w", padx=12, pady=8)
        body = ttk.Frame(dialog)
        body.pack(fill="both", expand=True, padx=12)

        event_vars = {
            name: tk.BooleanVar(value=name in prefill.get("events", []))
            for name in events
        }
        action_var = tk.StringVar(value=str(prefill.get("action") or (actions[0]["action_type"] if actions else "")))
        importance = tk.DoubleVar(value=float(prefill.get("importance", 5)))
        reinforce_var = tk.BooleanVar(value=bool(prefill.get("reinforce")))

        frames: Dict[int, ttk.Frame] = {n: ttk.Frame(body) for n in range(1, 5)}

        ttk.Label(frames[1], text=self.t("lesson.when")).pack(anchor="w")
        for name, var in event_vars.items():
            ttk.Checkbutton(frames[1], text=self._event_label(name), variable=var).pack(anchor="w")

        ttk.Label(frames[2], text=self.t("lesson.then")).pack(anchor="w")
        for row in actions:
            ttk.Radiobutton(
                frames[2],
                text=self._action_label(row["action_type"]),
                variable=action_var,
                value=row["action_type"],
            ).pack(anchor="w")

        ttk.Label(frames[3], text=self.t("lesson.because")).pack(anchor="w")
        ttk.Label(frames[3], text=self.t("lesson.result")).pack(anchor="w", pady=(8, 0))
        existing = self.controller.existing_consequences()
        consequence_labels = [self._outcome_label(code) for code in existing]
        prefill_code = str(prefill.get("consequence") or "")
        consequence_shown = tk.StringVar(
            value=self._outcome_label(prefill_code) if prefill_code else "",
        )
        cmb = ttk.Combobox(
            frames[3], textvariable=consequence_shown, values=consequence_labels, width=40,
        )
        cmb.pack(anchor="w", pady=4)

        def selected_consequence() -> str:
            return self.controller.outcome_code_from_label(
                consequence_shown.get(), lang=self.i18n.lang,
            )

        def add_consequence() -> None:
            extra = simpledialog.askstring(self.t("lesson.new_result"), self.t("prompt.consequence"), parent=dialog)
            if extra:
                consequence_shown.set(extra.strip())

        ttk.Button(frames[3], text=self.t("lesson.new_result"), command=add_consequence).pack(anchor="w")

        ttk.Label(frames[4], text=self.t("lesson.how_important")).pack(anchor="w")
        scale_row = ttk.Frame(frames[4])
        scale_row.pack(fill="x")
        ttk.Label(scale_row, text=self.t("lesson.minor")).pack(side="left")
        tk.Scale(scale_row, from_=0, to=10, orient="horizontal", variable=importance, length=280).pack(side="left")
        ttk.Label(scale_row, text=self.t("lesson.critical")).pack(side="left")
        ttk.Checkbutton(frames[4], text=self.t("lesson.reinforce"), variable=reinforce_var).pack(anchor="w", pady=8)
        preview = ttk.Label(frames[4], wraplength=500)
        preview.pack(fill="x", pady=8)

        nav = ttk.Frame(dialog)
        nav.pack(fill="x", pady=8)

        def selected_events() -> List[str]:
            return [name for name, var in event_vars.items() if var.get()]

        def render() -> None:
            n = step.get()
            header.configure(text=self.t("lesson.step", step=n))
            for idx, frame in frames.items():
                frame.pack_forget()
            frames[n].pack(fill="both", expand=True)
            if n == 4:
                try:
                    mapping = self.controller.build_lesson_mapping(
                        selected_events(),
                        action_var.get(),
                        selected_consequence(),
                        float(importance.get()) / 10.0,
                        bool(reinforce_var.get()),
                    )
                    preview.configure(text=self.controller.lesson_narrative(
                        mapping, lang=self.i18n.lang,
                    ))
                except ConfiguratorError as exc:
                    preview.configure(text=str(exc))
            btn_back.configure(state="normal" if n > 1 else "disabled")
            btn_next.configure(
                text=self.t("lesson.save") if n == 4 else self.t("lesson.next")
            )

        def next_step() -> None:
            n = step.get()
            if n == 1 and not selected_events():
                return
            if n == 2 and not action_var.get():
                return
            if n == 3 and not selected_consequence():
                return
            if n == 4:
                try:
                    self.controller.add_lesson_from_wizard(
                        selected_events(),
                        action_var.get(),
                        selected_consequence(),
                        float(importance.get()),
                        bool(reinforce_var.get()),
                        replace_index=replace_index,
                    )
                except ConfiguratorError as exc:
                    messagebox.showerror(self.t("error.title"), str(exc), parent=dialog)
                    return
                dialog.destroy()
                self._on_changed()
                return
            step.set(n + 1)
            render()

        def back_step() -> None:
            step.set(max(1, step.get() - 1))
            render()

        ttk.Button(nav, text=self.t("lesson.cancel"), command=dialog.destroy).pack(side="left", padx=8)
        btn_next = ttk.Button(nav, command=next_step)
        btn_next.pack(side="right", padx=8)
        btn_back = ttk.Button(nav, text=self.t("lesson.back"), command=back_step)
        btn_back.pack(side="right")
        render()

    def _format_issue(self, issue: Any) -> str:
        params = dict(issue.params or {})
        if "actions" in params and isinstance(params["actions"], list):
            params = dict(params)
            params["actions"] = ", ".join(self._action_label(item) for item in params["actions"])
        if "action_type" in params:
            params = dict(params)
            params["action_type"] = self._action_label(str(params["action_type"]))
        try:
            domain = self.t(f"issue.{issue.code}", **params)
        except Exception:
            domain = issue.technical
        if self._show_issue_technical:
            return f"{domain}\n    {issue.technical}"
        return domain

    def _refresh_validation(self) -> None:
        report = self.controller.validate()
        self._set_text(self.txt_errors, "\n\n".join(self._format_issue(i) for i in report.errors) or "—")
        self._set_text(self.txt_warns, "\n\n".join(self._format_issue(i) for i in report.warnings) or "—")
        self.lbl_val_ok.configure(text=self.t(
            "val.ok",
            tools=report.n_tools,
            decisions=report.n_decisions,
            lessons=report.n_lessons,
        ))
        self._sync_save_buttons(report)

    def _toggle_issue_technical(self) -> None:
        self._show_issue_technical = not self._show_issue_technical
        self.btn_tech.configure(
            text=self.t("val.hide_technical" if self._show_issue_technical else "val.technical")
        )
        self._refresh_validation()

    def _on_save(self) -> None:
        self._flush_focus()
        try:
            preview = self.controller.save(confirmed=False)
        except ConfiguratorError as exc:
            messagebox.showerror(self.t("error.title"), str(exc), parent=self)
            return
        diff = preview.get("diff") or [self.t("save.none")]
        dialog = tk.Toplevel(self)
        dialog.title(self.t("save.title"))
        dialog.transient(self)
        dialog.grab_set()
        txt = tk.Text(dialog, width=80, height=14, wrap="word")
        txt.pack(padx=10, pady=10)
        txt.insert("1.0", "\n".join(diff))
        self._mark_readonly_text(txt)

        def confirm() -> None:
            try:
                result = self.controller.save(confirmed=True)
            except ConfiguratorError as exc:
                messagebox.showerror(self.t("error.title"), str(exc), parent=dialog)
                return
            dialog.destroy()
            messagebox.showinfo(self.t("save.title"), self.t("save.ok", path=result.get("path", "")), parent=self)
            self._note_role_saved()
            self._on_changed()

        btns = ttk.Frame(dialog)
        btns.pack(pady=8)
        ttk.Button(btns, text=self.t("save.cancel"), command=dialog.destroy).pack(side="left", padx=6)
        ttk.Button(btns, text=self.t("save.confirm"), command=confirm).pack(side="left")

    def _on_history(self) -> None:
        rows = self.controller.list_history()
        dialog = tk.Toplevel(self)
        dialog.title(self.t("history.title"))
        dialog.transient(self)
        lst = tk.Listbox(dialog, width=70, height=12)
        lst.pack(padx=10, pady=10, fill="both", expand=True)
        if not rows:
            lst.insert("end", self.t("history.empty"))
        else:
            for row in rows:
                lst.insert("end", f"{row['name']}  ({row['relative_mtime']})")

        def selected_path() -> Optional[str]:
            sel = lst.curselection()
            if not sel or not rows:
                return None
            return rows[int(sel[0])]["path"]

        def show_diff() -> None:
            path = selected_path()
            if not path:
                return
            lines = self.controller.history_diff(path)
            messagebox.showinfo(self.t("history.diff"), "\n".join(lines) or self.t("save.none"), parent=dialog)

        def restore() -> None:
            path = selected_path()
            if not path:
                return
            try:
                self.controller.restore_history(path)
            except ConfiguratorError as exc:
                messagebox.showerror(self.t("error.title"), str(exc), parent=dialog)
                return
            dialog.destroy()
            self._on_changed()

        btns = ttk.Frame(dialog)
        btns.pack(pady=8)
        ttk.Button(btns, text=self.t("history.diff"), command=show_diff).pack(side="left", padx=6)
        ttk.Button(btns, text=self.t("history.restore"), command=restore).pack(side="left")

    def _on_dry_run(self) -> None:
        label = self.cmb_scenario.get()
        scenario = SCENARIO_STOCK_CRITICAL
        for key in SCENARIOS:
            if self.t(SCENARIO_I18N[key]) == label:
                scenario = key
                break
        result = self.controller.dry_run(scenario=scenario, n_ticks=20)
        self._last_dry = result
        if not result.ok:
            messagebox.showerror(self.t("error.title"), result.error, parent=self)
            return
        lines = []
        for tick in result.ticks:
            decision = self._action_label(str(tick.get("action") or ""))
            line = self.t("dryrun.tick", tick=tick["tick"], decision=decision or "—")
            exec_result = tick.get("execution_result")
            if isinstance(exec_result, dict) and exec_result.get("status"):
                line += " — " + self._status_label(str(exec_result.get("status")))
            elif exec_result:
                line += " — " + str(exec_result)
            lines.append(line)
        self._set_text(self.txt_dryrun, "\n".join(lines))
        self.lbl_dry_summary.configure(text=self.t(
            "dryrun.summary",
            orders=result.n_orders,
            rejected=result.n_rejected,
            lessons=result.n_lessons,
        ))

    def _show_last_log(self) -> None:
        if self._last_dry is None:
            return None
        return self._show_scrollable_text(
            self.t("dryrun.log"),
            "\n".join(self._last_dry.log) or "—",
        )

    def _show_last_memory(self) -> Optional[tk.Toplevel]:
        if self._last_dry is None:
            return None
        return self._show_scrollable_text(
            self.t("dryrun.memory"),
            self._format_memory_text(self._last_dry.memory_rows),
        )

    def _action_label(self, code: str) -> str:
        if not code:
            return ""
        return self.controller.action_display_name(code, lang=self.i18n.lang)

    def _outcome_label(self, consequence: str) -> str:
        if not consequence:
            return ""
        return self.controller.outcome_display_name(consequence, lang=self.i18n.lang)

    def _tag_label(self, tag: str) -> str:
        return self.controller.tag_display_name(tag, lang=self.i18n.lang)

    def _tool_label(self, tool_id: str) -> str:
        for row in self.controller.tool_rows():
            if row["tool_id"] == tool_id:
                return str(row.get("display_name") or tool_id)
        return tool_id

    def _has_i18n(self, key: str) -> bool:
        table = STRINGS.get(self.i18n.lang) or {}
        return key in table or key in STRINGS["en"]

    def _risk_label(self, code: str) -> str:
        key = f"risk.{code}"
        if self._has_i18n(key):
            return self.t(key)
        return str(code or "")

    def _risk_code(self, label: str) -> str:
        shown = str(label or "").strip()
        for value in RISK_VALUES:
            if self._risk_label(value) == shown:
                return value
        return shown

    def _status_label(self, status: str) -> str:
        key = f"exec.{status}"
        if self._has_i18n(key):
            return self.t(key)
        return self._human_label(status)

    def _human_label(self, value: str) -> str:
        return str(value or "").replace("_", " ").strip()

    def _format_memory_text(self, rows: List[dict]) -> str:
        if not rows:
            return self.t("dryrun.memory.empty")
        groups: List[List[Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            desc = describe_memory_row(row)
            signature = (
                desc["action"],
                desc["result"],
                desc["consequence"],
                tuple(desc["events"]),
                tuple(desc["extra"]),
                desc["importance"],
            )
            if groups and groups[-1][0] == signature:
                groups[-1][1] += 1
                continue
            groups.append([signature, 1, desc])
        if not groups:
            return self.t("dryrun.memory.empty")
        blocks = [self.t("dryrun.memory.count", n=len(rows)), ""]
        for index, (_signature, count, desc) in enumerate(groups, start=1):
            lines = [f"{index}."]
            if desc["events"]:
                lines.append(self.t("dryrun.memory.situation", value=", ".join(desc["events"])))
            if desc["action"]:
                lines.append(self.t("dryrun.memory.decision", value=self._action_label(desc["action"])))
            result = str(desc["result"] or "")
            happened_key = f"dryrun.memory.happened.{result}"
            if happened_key in (STRINGS.get(self.i18n.lang) or {}):
                lines.append(self.t(happened_key))
            elif result:
                lines.append(self.t("dryrun.memory.happened.unknown", value=self._human_label(result)))
            elif desc["extra"]:
                lines.append(self.t("dryrun.memory.happened.unknown", value=", ".join(desc["extra"])))
            outcome = self._outcome_label(str(desc["consequence"] or ""))
            if outcome:
                lines.append(self.t("dryrun.memory.outcome", value=outcome))
            lines.append(self.t(f"dryrun.memory.importance.{desc['importance']}"))
            if count > 1:
                lines.append(self.t("dryrun.memory.times", n=count))
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)

    def _note_role_saved(self) -> None:
        role_id = ""
        if self.controller.has_draft():
            role_id = str(self.controller._draft.get("role_id") or "").strip()
        if role_id:
            self.employee_host.note_role_saved(role_id)

    def _cancel_emp_poll(self) -> None:
        handle = self._emp_poll_after
        self._emp_poll_after = None
        if handle is not None:
            try:
                self.after_cancel(handle)
            except Exception:
                pass

    def _schedule_emp_poll(self) -> None:
        self._cancel_emp_poll()
        if self._screen == "employee" or self.employee_host.running_count():
            self._emp_poll_after = self.after(200, self._on_emp_poll_tick)

    def _on_emp_poll_tick(self) -> None:
        self._emp_poll_after = None
        if self._screen == "home":
            self._refresh_employees()
        elif self._screen == "employee":
            self._refresh_employee_card()
        else:
            return
        self._schedule_emp_poll()

    def _fmt_sleep(self, seconds: float) -> str:
        value = float(seconds or 0)
        if value >= 3600 and value % 3600 == 0:
            return f"{int(value // 3600)}h"
        if value >= 60 and value % 60 == 0:
            return f"{int(value // 60)}m"
        if value == int(value):
            return f"{int(value)}s"
        return f"{value}s"

    def _fmt_sensor_when(self, last_sensor: str) -> str:
        if not last_sensor:
            return self.t("emp.none")
        try:
            when = datetime.fromisoformat(str(last_sensor))
            ago = max(0, int((datetime.now() - when).total_seconds()))
            return self.t("emp.ago", n=ago)
        except (TypeError, ValueError):
            return str(last_sensor)

    def _refresh_employees(self, *, rebuild: bool = False) -> None:
        rows = self.employee_host.list_rows()
        ids = [str(row.get("agent_id") or "") for row in rows]
        if rebuild or list(self._emp_home_cards) != ids:
            self._rebuild_employee_home_cards(rows)
        else:
            for row in rows:
                self._update_employee_home_card(row)
        if self.employee_host.running_count() and self._screen == "home":
            self._schedule_emp_poll()

    def _rebuild_employee_home_cards(self, rows: List[Dict[str, Any]]) -> None:
        self._clear_inner(self.emp_cards_inner)
        self._emp_home_cards = {}
        if not rows:
            self.lbl_emp_empty.pack(padx=12, pady=8)
            return
        self.lbl_emp_empty.pack_forget()
        for row in rows:
            self._create_employee_home_card(row)

    def _create_employee_home_card(self, row: Dict[str, Any]) -> None:
        agent_id = str(row.get("agent_id") or "")
        card = ttk.LabelFrame(self.emp_cards_inner, text=str(row.get("display_name") or agent_id))
        card.pack(fill="x", padx=6, pady=6)
        status_lbl = ttk.Label(card)
        status_lbl.pack(anchor="w", padx=8, pady=(4, 0))
        roles_lbl = ttk.Label(card)
        roles_lbl.pack(anchor="w", padx=8)
        rhythm_lbl = ttk.Label(card)
        rhythm_lbl.pack(anchor="w", padx=8)
        pending_lbl = ttk.Label(card)
        alerts_lbl = ttk.Label(card, foreground="#a35200")
        error_lbl = ttk.Label(card, wraplength=380, foreground="#a40000")
        btns = ttk.Frame(card)
        btns.pack(fill="x", padx=8, pady=6)
        start_btn = ttk.Button(
            btns, text=self.t("emp.start"),
            command=lambda aid=agent_id: self._start_employee(aid),
        )
        start_btn.pack(side="left")
        ttk.Button(
            btns, text=self.t("emp.stop"),
            command=lambda aid=agent_id: self._stop_employee(aid),
        ).pack(side="left", padx=6)
        ttk.Button(
            btns, text=self.t("emp.open"),
            command=lambda aid=agent_id: self._open_employee(aid),
        ).pack(side="left")
        ttk.Button(
            btns, text=self.t("emp.delete"),
            command=lambda aid=agent_id: self._delete_employee(aid),
        ).pack(side="left", padx=6)
        card.bind("<Double-Button-1>", lambda _e, aid=agent_id: self._open_employee(aid))
        self._emp_home_cards[agent_id] = {
            "card": card,
            "status": status_lbl,
            "roles": roles_lbl,
            "rhythm": rhythm_lbl,
            "pending": pending_lbl,
            "alerts": alerts_lbl,
            "error": error_lbl,
            "start": start_btn,
        }
        self._update_employee_home_card(row)

    def _update_employee_home_card(self, row: Dict[str, Any]) -> None:
        agent_id = str(row.get("agent_id") or "")
        widgets = self._emp_home_cards.get(agent_id)
        if not widgets:
            return
        display = str(row.get("display_name") or agent_id)
        widgets["card"].configure(text=display)
        status = str(row.get("status") or "stopped")
        widgets["status"].configure(text="● " + self.t(f"emp.status.{status}"))
        roles = ", ".join(row.get("role_ids") or []) or self.t("emp.none")
        widgets["roles"].configure(text=self.t("emp.roles_line", roles=roles))
        widgets["rhythm"].configure(text=self.t(
            "emp.rhythm_line",
            tick=row.get("tick_interval_s") or 1,
            sleep=self._fmt_sleep(float(row.get("sleep_min_interval_s") or 0)),
        ))
        pending_n = int(row.get("pending_n") or 0)
        pending_lbl = widgets["pending"]
        if pending_n:
            pending_lbl.configure(text=self.t("emp.pending", n=pending_n))
            if not pending_lbl.winfo_ismapped():
                pending_lbl.pack(anchor="w", padx=8, after=widgets["rhythm"])
        else:
            pending_lbl.pack_forget()
        alerts_n = len(row.get("alerts") or [])
        alerts_lbl = widgets["alerts"]
        if alerts_n:
            alerts_lbl.configure(text=self.t("emp.alerts_badge", n=alerts_n))
            if not alerts_lbl.winfo_ismapped():
                after = pending_lbl if pending_n else widgets["rhythm"]
                alerts_lbl.pack(anchor="w", padx=8, after=after)
        else:
            alerts_lbl.pack_forget()
        err = str(row.get("error_text") or "")
        error_lbl = widgets["error"]
        if err:
            error_lbl.configure(text=err)
            if not error_lbl.winfo_ismapped():
                after = alerts_lbl if alerts_n else (pending_lbl if pending_n else widgets["rhythm"])
                error_lbl.pack(anchor="w", padx=8, after=after)
        else:
            error_lbl.pack_forget()
        live = status not in ("stopped", "error")
        start_btn = widgets["start"]
        if live:
            start_btn.state(["disabled"])
        else:
            start_btn.state(["!disabled"])

    def _open_employee(self, agent_id: str) -> None:
        self._current_employee_id = agent_id
        self._emp_card_fp.clear()
        self.home_frame.pack_forget()
        self.editor_frame.pack_forget()
        self.employee_card_frame.pack(fill="both", expand=True)
        self._screen = "employee"
        self._refresh_employee_card(load_entries=True)
        self._schedule_emp_poll()

    def _on_emp_back(self) -> None:
        self._show_list()

    def _refresh_employee_card(self, *, load_entries: bool = False) -> None:
        agent_id = self._current_employee_id
        if not agent_id:
            return
        row = self.employee_host.row_for(agent_id)
        status = str(row.get("status") or "stopped")
        self.lbl_emp_title.configure(text=str(row.get("display_name") or agent_id))
        self.lbl_emp_badge.configure(text="● " + self.t(f"emp.status.{status}"))
        err = str(row.get("error_text") or "")
        self.lbl_emp_error.configure(text=err)
        if row.get("stale_roles") and status not in ("stopped", "error"):
            if not self.frm_emp_stale.winfo_ismapped():
                self.frm_emp_stale.pack(fill="x", padx=12, pady=6, after=self.lbl_emp_error)
        else:
            self.frm_emp_stale.pack_forget()
        stopped = status in ("stopped", "error")
        roles_fp = (tuple(str(item) for item in (row.get("role_ids") or [])), stopped)
        if self._emp_card_fp.get("roles") != roles_fp:
            self._render_emp_roles(row, editable=stopped)
            self._emp_card_fp["roles"] = roles_fp
        if load_entries:
            self._load_emp_rhythm_entries(row)
        mcp = " · ".join(
            f"{item.get('server_id')}  {item.get('transport')}  "
            f"{'ok' if item.get('ok') else '—'}"
            for item in (row.get("mcp") or [])
        ) or self.t("emp.none")
        self.lbl_emp_mcp.configure(text=f"{self.t('emp.mcp')}: {mcp}")
        self.lbl_emp_organs.configure(text=self.t(
            "emp.organs",
            read=int(row.get("n_read") or 0),
            write=int(row.get("n_write") or 0),
            when=self._fmt_sensor_when(str(row.get("last_sensor") or "")),
        ))
        checkpoint = str(row.get("checkpoint") or "") or self.t("emp.none")
        self.lbl_emp_memory.configure(text=self.t(
            "emp.memory",
            when=checkpoint,
            n=int(row.get("episodes") or 0),
        ))
        if stopped:
            can_start, _reason = self.employee_host.can_start(agent_id)
            self.btn_emp_start.configure(state="normal" if can_start else "disabled")
        else:
            self.btn_emp_start.configure(state="disabled")
        self.btn_emp_add_role.configure(state="normal" if stopped else "disabled")
        self.btn_emp_reset.configure(state="normal" if stopped else "disabled")
        pending = list(row.get("pending") or [])
        pending_fp = self._emp_pending_fp(pending)
        if self._emp_card_fp.get("pending") != pending_fp:
            self._render_emp_approvals(pending)
            self._emp_card_fp["pending"] = pending_fp
        self._render_emp_alerts(list(row.get("alerts") or []))
        self._set_text(self.txt_emp_log, "\n".join(row.get("log") or []) or "—")
        self._set_text(self.txt_emp_narrative, self._emp_narrative_text())

    _EMP_ALERTS_SHOWN = 5

    def _render_emp_alerts(self, alerts: List[Dict[str, Any]]) -> None:
        if not alerts:
            self.frm_emp_alerts.pack_forget()
            return
        self.lbl_emp_alerts.configure(text=self.t("emp.alerts", n=len(alerts)))
        lines = [self._fmt_emp_alert(item) for item in alerts[-self._EMP_ALERTS_SHOWN:]]
        self.lbl_emp_alerts_body.configure(text="\n".join(reversed(lines)))
        if not self.frm_emp_alerts.winfo_ismapped():
            self.frm_emp_alerts.pack(fill="x", padx=12, pady=(0, 6), before=self.lbl_emp_approval)

    def _fmt_emp_alert(self, alert: Dict[str, Any]) -> str:
        reason = str(alert.get("reason") or "")
        key = f"emp.alert_reason.{reason}"
        available = alert.get("available")
        shown = f"{available:g}" if isinstance(available, (int, float)) else "?"
        reason_text = self.t(key, available=shown)
        if reason_text == key:
            reason_text = reason
        at = str(alert.get("at") or "")
        return self.t(
            "emp.alert_line",
            at=at[11:16] if len(at) >= 16 else at,
            limit=str(alert.get("limit") or ""),
            summary=str(alert.get("summary") or alert.get("tool_id") or ""),
            reason=reason_text,
        )

    def _on_emp_clear_alerts(self) -> None:
        if self._current_employee_id:
            self.employee_host.clear_alerts(self._current_employee_id)
            self._refresh_employee_card()

    def _emp_pending_fp(self, pending: List[Any]) -> tuple:
        rows = []
        for item in pending:
            params = item.get("tool_params") or {}
            rows.append((
                str(item.get("action_id") or ""),
                json.dumps(params, ensure_ascii=False, sort_keys=True, default=str),
            ))
        return tuple(rows)

    def _load_emp_rhythm_entries(self, row: Dict[str, Any]) -> None:
        pairs = (
            (self.ent_emp_tick, row.get("tick_interval_s")),
            (self.ent_emp_sensor, row.get("sensor_refresh_interval_s")),
            (self.ent_emp_sleep, row.get("sleep_min_interval_s")),
            (self.ent_emp_win_start, (row.get("circadian_window") or [2, 5])[0]),
            (self.ent_emp_win_end, (row.get("circadian_window") or [2, 5])[1]),
            (
                self.ent_emp_fatigue,
                "" if row.get("fatigue_threshold") is None else row.get("fatigue_threshold"),
            ),
        )
        for widget, value in pairs:
            if self.focus_get() is widget:
                continue
            widget.delete(0, "end")
            widget.insert(0, "" if value is None else str(value))

    def _render_emp_roles(self, row: Dict[str, Any], *, editable: bool) -> None:
        for child in self.emp_roles_box.winfo_children():
            child.destroy()
        for role_id in row.get("role_ids") or []:
            chip = ttk.Frame(self.emp_roles_box)
            chip.pack(side="left", padx=2)
            ttk.Label(chip, text=str(role_id)).pack(side="left")
            if editable:
                ttk.Button(
                    chip, text="×", width=2,
                    command=lambda rid=role_id: self._remove_emp_role(rid),
                ).pack(side="left")

    def _render_emp_approvals(self, pending: List[Any]) -> None:
        self._clear_inner(self.emp_approval_inner)
        if not pending:
            ttk.Label(self.emp_approval_inner, text=self.t("emp.none")).pack(anchor="w", padx=8, pady=4)
            return
        for item in pending:
            card = ttk.LabelFrame(self.emp_approval_inner, text=str(item.get("tool_id") or ""))
            card.pack(fill="x", padx=4, pady=4)
            params = item.get("tool_params") or {}
            ttk.Label(card, text=json.dumps(params, ensure_ascii=False), wraplength=700).pack(
                anchor="w", padx=8, pady=4,
            )
            action_id = str(item.get("action_id") or "")
            btns = ttk.Frame(card)
            btns.pack(anchor="w", padx=8, pady=4)
            ttk.Button(
                btns, text=self.t("emp.approve"),
                command=lambda aid=action_id: self._emp_decide(aid, ApprovalStatus.APPROVED),
            ).pack(side="left")
            ttk.Button(
                btns, text=self.t("emp.reject"),
                command=lambda aid=action_id: self._emp_decide(aid, ApprovalStatus.REJECTED),
            ).pack(side="left", padx=6)
            ttk.Button(
                btns, text=self.t("emp.edit_params"),
                command=lambda aid=action_id, payload=params: self._emp_edit_params(aid, payload),
            ).pack(side="left")

    def _emp_narrative_text(self) -> str:
        agent_id = self._current_employee_id
        session = self.employee_host.sessions.get(agent_id)
        agent = getattr(session, "agent", None) if session is not None else None
        hip = getattr(agent, "hippocampus", None)
        experiences = list(getattr(hip, "experiences", []) or [])
        if not experiences:
            return self.t("emp.none")
        lines = []
        for exp in experiences[-20:]:
            if isinstance(exp, dict):
                lines.append(str(describe_memory_row(exp)))
            else:
                lines.append(str(exp))
        return "\n".join(lines)

    def _commit_emp_rhythm(self) -> None:
        agent_id = self._current_employee_id
        if not agent_id:
            return
        try:
            tick = float(self.ent_emp_tick.get().strip() or "1")
            sensor = float(self.ent_emp_sensor.get().strip() or "30")
            sleep_s = float(self.ent_emp_sleep.get().strip() or "3600")
            start = int(self.ent_emp_win_start.get().strip() or "2")
            end = int(self.ent_emp_win_end.get().strip() or "5")
            fatigue_raw = self.ent_emp_fatigue.get().strip()
            fatigue: Any = None if fatigue_raw in ("", "none", "null") else float(fatigue_raw)
        except (TypeError, ValueError) as exc:
            messagebox.showerror(self.t("error.title"), str(exc), parent=self)
            self._refresh_employee_card(load_entries=True)
            return
        if sleep_s == 0:
            if not messagebox.askyesno(
                self.t("emp.close_title"),
                self.t("emp.sleep_zero_confirm"),
                parent=self,
            ):
                self._refresh_employee_card(load_entries=True)
                return
        try:
            self.employee_host.update_rhythm(
                agent_id,
                tick_interval_s=tick,
                sensor_refresh_interval_s=sensor,
                sleep_min_interval_s=sleep_s,
                circadian_window=(start, end),
                fatigue_threshold=fatigue,
            )
        except Exception as exc:
            messagebox.showerror(self.t("error.title"), str(exc), parent=self)
            self._refresh_employee_card(load_entries=True)

    def _start_employee(self, agent_id: str) -> None:
        try:
            self.employee_host.start(agent_id)
        except Exception as exc:
            messagebox.showerror(self.t("error.title"), str(exc), parent=self)
        if self._screen == "employee":
            self._refresh_employee_card()
        else:
            self._refresh_employees()
        self._schedule_emp_poll()

    def _stop_employee(self, agent_id: str) -> None:
        try:
            self.employee_host.stop(agent_id)
        except Exception as exc:
            messagebox.showerror(self.t("error.title"), str(exc), parent=self)
        if self._screen == "employee":
            self._refresh_employee_card(load_entries=True)
        else:
            self._refresh_employees()

    def _on_emp_start(self) -> None:
        if self._current_employee_id:
            self._start_employee(self._current_employee_id)

    def _on_emp_stop(self) -> None:
        if self._current_employee_id:
            self._stop_employee(self._current_employee_id)

    def _on_emp_restart(self) -> None:
        if not self._current_employee_id:
            return
        try:
            self.employee_host.restart(self._current_employee_id)
        except Exception as exc:
            messagebox.showerror(self.t("error.title"), str(exc), parent=self)
        self._refresh_employee_card()
        self._schedule_emp_poll()

    def _on_emp_reset_memory(self) -> None:
        if not self._current_employee_id:
            return
        if not messagebox.askyesno(
            self.t("emp.reset_memory"),
            self.t("emp.reset_confirm"),
            parent=self,
        ):
            return
        try:
            self.employee_host.reset_memory(self._current_employee_id)
        except ConfiguratorError as exc:
            messagebox.showerror(self.t("error.title"), str(exc), parent=self)
        self._refresh_employee_card(load_entries=True)

    def _delete_employee(self, agent_id: str) -> None:
        row = self.employee_host.row_for(agent_id)
        name = str(row.get("display_name") or agent_id)
        if not messagebox.askyesno(
            self.t("emp.delete"),
            self.t("emp.delete_confirm", name=name),
            parent=self,
        ):
            return
        try:
            self.employee_host.delete_employee(agent_id)
        except Exception as exc:
            messagebox.showerror(self.t("error.title"), str(exc), parent=self)
            return
        if self._current_employee_id == agent_id:
            self._show_list()
            return
        self._refresh_employees(rebuild=True)

    def _on_emp_delete(self) -> None:
        if self._current_employee_id:
            self._delete_employee(self._current_employee_id)

    def _emp_decide(
        self,
        action_id: str,
        decision: Any,
        modified_params: Optional[Dict[str, Any]] = None,
    ) -> None:
        params = dict(modified_params or {})
        if not params:
            for item in self.employee_host.row_for(self._current_employee_id).get("pending") or []:
                if str(item.get("action_id") or "") == action_id:
                    params = dict(item.get("tool_params") or {})
                    break
        if decision == ApprovalStatus.APPROVED:
            qty = params.get("qty")
            try:
                qty_n = float(qty)
            except (TypeError, ValueError):
                qty_n = None
            if qty_n is not None and qty_n <= 0:
                if not messagebox.askyesno(
                    self.t("emp.approval"),
                    self.t("emp.qty_zero_confirm"),
                    parent=self,
                ):
                    return
        try:
            record = self.employee_host.complete_approval(
                self._current_employee_id,
                action_id,
                decision,
                modified_params=modified_params,
            )
        except Exception as exc:
            messagebox.showerror(self.t("error.title"), str(exc), parent=self)
            self._refresh_employee_card()
            return
        self._refresh_employee_card()
        if decision not in (ApprovalStatus.APPROVED, ApprovalStatus.MODIFIED):
            return
        result = getattr(record, "execution_result", None)
        if not isinstance(result, dict):
            return
        status = str(result.get("status") or "")
        if status in {"accepted", "ok", "success"}:
            number = result.get("document_number") or result.get("document_ref") or ""
            if number:
                messagebox.showinfo(
                    self.t("emp.approval"),
                    self.t("emp.write_ok", number=str(number)),
                    parent=self,
                )
            return
        detail = result.get("reason") or result.get("error") or json.dumps(
            result, ensure_ascii=False, default=str,
        )
        messagebox.showerror(
            self.t("error.title"),
            self.t("emp.write_failed", status=status or "error", detail=str(detail)),
            parent=self,
        )

    def _emp_edit_params(self, action_id: str, payload: Dict[str, Any]) -> None:
        raw = simpledialog.askstring(
            self.t("emp.edit_params"),
            self.t("emp.edit_params"),
            initialvalue=json.dumps(payload, ensure_ascii=False),
            parent=self,
        )
        if raw is None:
            return
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            messagebox.showerror(self.t("error.title"), str(exc), parent=self)
            return
        if not isinstance(parsed, dict):
            messagebox.showerror(self.t("error.title"), self.t("error.params_object"), parent=self)
            return
        self._emp_decide(action_id, ApprovalStatus.APPROVED, modified_params=parsed)

    def _remove_emp_role(self, role_id: str) -> None:
        agent_id = self._current_employee_id
        row = self.employee_host.row_for(agent_id)
        remaining = [item for item in row.get("role_ids") or [] if item != role_id]
        try:
            self.employee_host.assign_roles(agent_id, remaining)
        except ConfiguratorError as exc:
            messagebox.showerror(self.t("error.title"), str(exc), parent=self)
        self._refresh_employee_card(load_entries=True)

    def _on_emp_add_role(self) -> None:
        agent_id = self._current_employee_id
        current = list(self.employee_host.row_for(agent_id).get("role_ids") or [])
        options = [
            item for item in self.employee_host.assignable_roles()
            if item["role_id"] not in current
        ]
        if not options:
            return
        dialog = tk.Toplevel(self)
        dialog.title(self.t("emp.add_role"))
        dialog.transient(self)
        dialog.grab_set()
        vars_by_id: Dict[str, tk.BooleanVar] = {}
        for item in options:
            var = tk.BooleanVar(value=False)
            vars_by_id[item["role_id"]] = var
            chk = ttk.Checkbutton(
                dialog,
                text=f"{item['role_id']} — {item['display_name']}",
                variable=var,
            )
            chk.pack(anchor="w", padx=12, pady=2)
            if item.get("disabled"):
                chk.state(["disabled"])

        def accept() -> None:
            chosen = current + [rid for rid, var in vars_by_id.items() if var.get()]
            try:
                self.employee_host.assign_roles(agent_id, chosen)
            except ConfiguratorError as exc:
                messagebox.showerror(self.t("error.title"), str(exc), parent=dialog)
                return
            dialog.destroy()
            self._refresh_employee_card(load_entries=True)

        btns = ttk.Frame(dialog)
        btns.pack(pady=8)
        ttk.Button(btns, text=self.t("emp.new.cancel"), command=dialog.destroy).pack(side="left", padx=6)
        ttk.Button(btns, text=self.t("emp.add_role"), command=accept).pack(side="left")

    def _on_new_employee(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title(self.t("emp.new.title"))
        dialog.transient(self)
        dialog.grab_set()
        ttk.Label(dialog, text=self.t("emp.new.name")).grid(row=0, column=0, sticky="w", padx=12, pady=(12, 4))
        name_var = tk.StringVar()
        ent_name = ttk.Entry(dialog, textvariable=name_var, width=36)
        ent_name.grid(row=0, column=1, padx=12, pady=(12, 4))
        ttk.Label(dialog, text=self.t("emp.new.id")).grid(row=1, column=0, sticky="w", padx=12)
        id_var = tk.StringVar()
        ent_id = ttk.Entry(dialog, textvariable=id_var, width=36)
        ent_id.grid(row=1, column=1, padx=12)
        id_touched = {"value": False}

        def on_name_change(*_args: Any) -> None:
            if id_touched["value"]:
                return
            taken = [row["agent_id"] for row in self.employee_host.list_rows()]
            id_var.set(suggest_agent_id(name_var.get(), taken))

        name_var.trace_add("write", on_name_change)
        ent_id.bind("<Key>", lambda _e: id_touched.__setitem__("value", True))
        ttk.Label(dialog, text=self.t("emp.new.roles")).grid(
            row=2, column=0, columnspan=2, sticky="w", padx=12, pady=(8, 2),
        )
        roles_frame = ttk.Frame(dialog)
        roles_frame.grid(row=3, column=0, columnspan=2, sticky="w", padx=12)
        role_vars: Dict[str, tk.BooleanVar] = {}
        for item in self.employee_host.assignable_roles():
            var = tk.BooleanVar(value=False)
            role_vars[item["role_id"]] = var
            mark = "⚠ " if item["status"] == "warnings" else ""
            chk = ttk.Checkbutton(
                roles_frame,
                text=f"{mark}{item['role_id']} — {item['display_name']}",
                variable=var,
            )
            chk.pack(anchor="w")
            if item.get("disabled"):
                chk.state(["disabled"])
        ttk.Label(dialog, text=self.t("emp.new.rhythm")).grid(
            row=4, column=0, columnspan=2, sticky="w", padx=12, pady=(8, 2),
        )
        ttk.Label(dialog, text=self.t("emp.new.tick")).grid(row=5, column=0, sticky="w", padx=12)
        tick_var = tk.StringVar(value="1")
        ttk.Entry(dialog, textvariable=tick_var, width=10).grid(row=5, column=1, sticky="w", padx=12)
        ttk.Label(dialog, text=self.t("emp.new.sleep")).grid(row=6, column=0, sticky="w", padx=12)
        sleep_var = tk.StringVar(value="3600")
        ttk.Entry(dialog, textvariable=sleep_var, width=10).grid(row=6, column=1, sticky="w", padx=12)

        def create() -> None:
            chosen = [rid for rid, var in role_vars.items() if var.get()]
            try:
                sleep_s = float(sleep_var.get().strip() or "3600")
                tick_s = float(tick_var.get().strip() or "1")
            except ValueError as exc:
                messagebox.showerror(self.t("error.title"), str(exc), parent=dialog)
                return
            if sleep_s == 0 and not messagebox.askyesno(
                self.t("emp.new.title"), self.t("emp.sleep_zero_confirm"), parent=dialog,
            ):
                return
            try:
                self.employee_host.create_employee(
                    name_var.get(),
                    id_var.get(),
                    chosen,
                    tick_interval_s=tick_s,
                    sleep_min_interval_s=sleep_s,
                )
            except ConfiguratorError as exc:
                messagebox.showerror(self.t("error.title"), str(exc), parent=dialog)
                return
            dialog.destroy()
            self._refresh_employees()

        btns = ttk.Frame(dialog)
        btns.grid(row=7, column=0, columnspan=2, pady=12)
        ttk.Button(btns, text=self.t("emp.new.cancel"), command=dialog.destroy).pack(side="left", padx=6)
        ttk.Button(btns, text=self.t("emp.new.create"), command=create).pack(side="left")
        ent_name.focus_set()

    def _make_help_button(self, parent: tk.Misc, topic: str) -> ttk.Button:
        btn = ttk.Button(
            parent,
            text=self.t("help.button"),
            command=lambda t=topic: self._show_help(t),
        )
        self._help_buttons[topic] = btn
        return btn

    def _show_help(self, topic: str) -> tk.Toplevel:
        dialog = self._show_scrollable_text(
            self.t(f"help.{topic}.title"),
            self.t(f"help.{topic}.body"),
            close_key="help.close",
        )
        dialog.geometry("760x580")
        return dialog

    def _show_scrollable_text(
        self,
        title: str,
        body: str,
        *,
        close_key: str = "dryrun.close",
    ) -> tk.Toplevel:
        dialog = tk.Toplevel(self)
        dialog.title(title)
        dialog.transient(self)
        dialog.geometry("640x520")
        dialog.minsize(420, 280)
        ttk.Label(dialog, text=title, font=("Segoe UI", 10, "bold")).pack(
            anchor="w", padx=12, pady=(12, 6),
        )
        frame = ttk.Frame(dialog)
        frame.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        scroll = ttk.Scrollbar(frame)
        text = tk.Text(
            frame, wrap="word", font=("Segoe UI", 10), yscrollcommand=scroll.set,
        )
        scroll.configure(command=text.yview)
        text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        text.insert("1.0", body)
        self._mark_readonly_text(text)
        ttk.Button(dialog, text=self.t(close_key), command=dialog.destroy).pack(
            pady=(0, 12),
        )
        dialog.lift()
        dialog.focus_set()
        return dialog

    def _wire_clipboard_shortcuts(self) -> None:
        """Ctrl+C / Ctrl+A on any field, including a Russian keyboard layout."""
        self.bind_all("<Control-Insert>", self._on_copy_shortcut, add="+")
        self.bind_all("<KeyPress>", self._on_clipboard_keypress, add="+")

    def _on_clipboard_keypress(self, event: tk.Event) -> Optional[str]:
        if not (int(getattr(event, "state", 0) or 0) & 0x4):
            return None
        keysym = str(getattr(event, "keysym", "") or "").lower()
        keycode = int(getattr(event, "keycode", 0) or 0)
        if keysym in {"c", "cyrillic_es"} or keycode == 67:
            return self._on_copy_shortcut(event)
        if keysym in {"a", "cyrillic_ef"} or keycode == 65:
            return self._on_select_all_shortcut(event)
        return None

    def _mark_readonly_text(self, *widgets: tk.Text) -> None:
        """Keep selection and Ctrl+C; block typing into display panes."""
        for widget in widgets:
            widget.bind("<Key>", self._on_readonly_text_key, add="+")

    def _on_readonly_text_key(self, event: tk.Event) -> Optional[str]:
        if event.keysym in {
            "Left", "Right", "Up", "Down", "Home", "End", "Prior", "Next",
            "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R",
        }:
            return None
        if int(event.state) & 0x4:
            return None
        return "break"

    def _selected_text(self, widget: Any) -> str:
        if widget is None:
            return ""
        try:
            cls = str(widget.winfo_class())
        except tk.TclError:
            return ""
        try:
            if cls == "Text":
                return widget.get("sel.first", "sel.last")
            if cls in {"Entry", "TEntry", "TCombobox", "Spinbox", "TSpinbox"}:
                return str(widget.selection_get())
            if cls == "Listbox":
                indexes = widget.curselection()
                return "\n".join(widget.get(i) for i in indexes)
            if cls in {"Label", "TLabel"}:
                return str(widget.cget("text") or "")
        except tk.TclError:
            return ""
        return ""

    def _clipboard_target(
        self,
        event: Optional[tk.Event] = None,
        *,
        require_selection: bool = True,
    ) -> Any:
        candidates = []
        if event is not None:
            candidates.append(getattr(event, "widget", None))
        candidates.append(self.focus_get())
        for widget in candidates:
            if widget is None:
                continue
            if require_selection:
                if self._selected_text(widget):
                    return widget
            elif self._is_copyable_widget(widget):
                return widget
        return None

    def _is_copyable_widget(self, widget: Any) -> bool:
        try:
            cls = str(widget.winfo_class())
        except (tk.TclError, AttributeError):
            return False
        return cls in {
            "Text", "Entry", "TEntry", "TCombobox", "Spinbox", "TSpinbox",
            "Listbox", "Label", "TLabel",
        }

    def _on_copy_shortcut(self, event: Optional[tk.Event] = None) -> Optional[str]:
        widget = self._clipboard_target(event)
        text = self._selected_text(widget)
        if not text:
            return None
        self.clipboard_clear()
        self.clipboard_append(text)
        return "break"

    def _on_select_all_shortcut(self, event: Optional[tk.Event] = None) -> Optional[str]:
        widget = self._clipboard_target(event, require_selection=False)
        if widget is None:
            return None
        try:
            cls = str(widget.winfo_class())
        except tk.TclError:
            return None
        try:
            if cls == "Text":
                widget.tag_add("sel", "1.0", "end-1c")
                widget.mark_set("insert", "1.0")
                widget.see("insert")
                return "break"
            if cls in {"Entry", "TEntry", "TCombobox", "Spinbox", "TSpinbox"}:
                widget.selection_range(0, "end")
                return "break"
            if cls == "Listbox":
                widget.selection_set(0, "end")
                return "break"
        except tk.TclError:
            return None
        return None

    def _set_text(self, widget: tk.Text, value: str) -> None:
        if widget.get("1.0", "end-1c") == value:
            return
        try:
            if widget.tag_ranges("sel"):
                return
        except tk.TclError:
            pass
        yview = widget.yview()
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        try:
            widget.yview_moveto(yview[0])
        except (tk.TclError, IndexError, TypeError):
            pass


def main(argv: Optional[list[str]] = None) -> int:
    import argparse

    raw = list(sys.argv[1:] if argv is None else argv)
    preview = None
    if "--lang" in raw:
        index = raw.index("--lang")
        if index + 1 < len(raw):
            preview = raw[index + 1]
    help_i18n = I18n(lang=preview or "en", force=preview in ("en", "ru"))
    parser = argparse.ArgumentParser(description=help_i18n.t("cli.description"))
    parser.add_argument(
        "--lang",
        choices=("en", "ru"),
        default=None,
        help=help_i18n.t("cli.lang_help"),
    )
    args = parser.parse_args(argv)
    app = RoleConfiguratorApp(lang=args.lang)
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
