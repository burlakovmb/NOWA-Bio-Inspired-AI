"""NOWA Procurement Sandbox — full laboratory GUI.

Tabs:
  Run      — single Stage 1a/1b training with soft-stop / resume
  Sweep    — multi-seed Stage 1a
  Report   — readiness table + write baseline
  Results  — browse saved results JSON into table/charts

UI is bilingual (EN / RU); switch via flag buttons in the top-right corner.

Launch::

    python -m nowa_sandbox.gui_app
    # or run_gui.bat
"""

from __future__ import annotations

import os
import queue
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError:  # pragma: no cover - minimal Python builds omit Tk
    tk = None  # type: ignore[assignment]
    filedialog = None  # type: ignore[assignment]
    messagebox = None  # type: ignore[assignment]
    ttk = None  # type: ignore[assignment]

if __package__ in (None, ""):  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nowa_sandbox import __version__


def _idle_button_bg(widget) -> str:
    """Windows system button color when this Tk knows it."""

    if tk is None:
        return "#f0f0f0"
    try:
        widget.tk.call("winfo", "rgb", widget, "SystemButtonFace")
    except tk.TclError:
        return "#f0f0f0"
    return "SystemButtonFace"
from nowa_sandbox.gui_charts import FitnessChart
from nowa_sandbox.gui_controller import (
    DEMO_ROOT,
    RunController,
    RunSpec,
    SweepSpec,
    load_results_json,
)
from nowa_sandbox.gui_i18n import (
    I18n,
    criterion_column,
    criterion_labels,
    criterion_legend,
    format_readiness_localized,
)
from nowa_sandbox.procurement_fitness import (
    GRADUATION_THRESHOLDS,
    PROCUREMENT_CRITERIA,
    STAGE_1A_CRITERIA,
)
from nowa_sandbox.quarter_diagnostics import (
    diagnose_quarter,
    format_diagnosis_text,
    nr_floors_from_baseline,
)
from nowa_sandbox.procurement_world import ProcurementWorldConfig
from nowa_sandbox.stage_baseline import load_baseline_bundle
from nowa_sandbox.gui_world_tab import (
    build_world_tab,
    init_world_vars,
    apply_world_column_headers,
    get_curriculum_for_run,
)

from nowa_sandbox.world_editor import (
    PRODUCT_EDIT_FIELDS,
    SUPPLIER_EDIT_FIELDS,
    build_world_for_quarter,
    overrides_from_tables,
    snapshot_world,
)


class SandboxLabApp(tk.Tk if tk is not None else object):
    """Main laboratory window."""

    def __init__(self, lang: str | None = None) -> None:
        super().__init__()
        self.geometry("1280x820")
        self.minsize(1000, 680)

        self.i18n = I18n(
            lang=lang or "en",
            pref_path=DEMO_ROOT / "results" / ".lab_lang.json",
            force=lang in ("en", "ru"),
        )
        self.controller = RunController()
        self._ui_queue: queue.Queue = queue.Queue()
        self._records: List[Dict[str, Any]] = []
        self._busy = False
        self._last_report: Optional[Dict[str, Any]] = None
        self._results_meta: Optional[Dict[str, Any]] = None

        self._build()
        self._apply_language()
        self.after(100, self._pump_queue)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def t(self, key: str, **kwargs: Any) -> str:
        return self.i18n.t(key, **kwargs)

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")

        # Top bar: title left, language flags right
        header = ttk.Frame(self)
        header.pack(fill="x", padx=8, pady=(8, 0))
        self.lbl_title = ttk.Label(header, font=("Segoe UI", 11, "bold"))
        self.lbl_title.pack(side="left")

        lang_bar = ttk.Frame(header)
        lang_bar.pack(side="right")
        self.btn_lang_en = tk.Button(
            lang_bar,
            text="EN",
            command=lambda: self._set_language("en"),
            relief="raised",
            padx=8,
            pady=2,
            font=("Segoe UI Emoji", 10),
            cursor="hand2",
        )
        self.btn_lang_ru = tk.Button(
            lang_bar,
            text="RU",
            command=lambda: self._set_language("ru"),
            relief="raised",
            padx=8,
            pady=2,
            font=("Segoe UI Emoji", 10),
            cursor="hand2",
        )
        self.btn_lang_en.pack(side="left", padx=(0, 4))
        self.btn_lang_ru.pack(side="left")

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=8)

        self.tab_world = ttk.Frame(self.notebook)
        self.tab_run = ttk.Frame(self.notebook)
        self.tab_sweep = ttk.Frame(self.notebook)
        self.tab_report = ttk.Frame(self.notebook)
        self.tab_results = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_world, text="World")
        self.notebook.add(self.tab_run, text="Run")
        self.notebook.add(self.tab_sweep, text="Sweep")
        self.notebook.add(self.tab_report, text="Report")
        self.notebook.add(self.tab_results, text="Results")

        self._quarter_overrides = {}
        self._world_products = []
        self._world_suppliers = []
        self.demo_root = DEMO_ROOT

        self._build_world_tab()
        self._build_run_tab()
        self._build_sweep_tab()
        self._build_report_tab()
        self._build_results_tab()

        status = ttk.Frame(self)
        status.pack(fill="x", padx=8, pady=(0, 6))
        self.status_var = tk.StringVar()
        ttk.Label(status, textvariable=self.status_var).pack(side="left")
        ttk.Label(status, text=f"demo: {DEMO_ROOT}", foreground="#666").pack(side="right")

    def _build_world_tab(self) -> None:
        init_world_vars(self)
        # days_var is created on Run tab; create early for World config.
        if not hasattr(self, "days_var"):
            self.days_var = __import__("tkinter").StringVar(value="90")
        if not hasattr(self, "seed_var"):
            self.seed_var = __import__("tkinter").StringVar(value="42")
        build_world_tab(self)

    def _build_run_tab(self) -> None:
        root = self.tab_run
        root.columnconfigure(1, weight=1)
        root.rowconfigure(2, weight=1)

        self.frm_config = ttk.LabelFrame(root, padding=8)
        self.frm_config.grid(row=0, column=0, columnspan=2, sticky="ew", padx=4, pady=4)
        for i in range(8):
            self.frm_config.columnconfigure(i, weight=1)

        self.stage_var = tk.StringVar(value="1a")
        if not hasattr(self, "seed_var"):
            self.seed_var = tk.StringVar(value="42")
        self.quarters_var = tk.StringVar(value="30")  # legacy / sweep fallback
        self.curriculum_summary_var = tk.StringVar(value="")
        if not hasattr(self, "days_var"):
            self.days_var = tk.StringVar(value="90")
        self.stop_grad_var = tk.BooleanVar(value=True)
        self.seed_int_var = tk.BooleanVar(value=True)
        self.config_var = tk.StringVar(value="configs/default_world.yaml")
        self.baseline_var = tk.StringVar(value="results/stage_1a_baseline.json")
        self.resume_var = tk.StringVar(value="")
        self.output_var = tk.StringVar(value="results/lab_run.json")
        self.checkpoint_var = tk.StringVar(value="checkpoints/lab_run.ckpt")

        self.lbl_stage = ttk.Label(self.frm_config)
        self.lbl_stage.grid(row=0, column=0, sticky="w")
        ttk.Combobox(
            self.frm_config,
            textvariable=self.stage_var,
            values=["1a", "1b"],
            width=6,
            state="readonly",
        ).grid(row=0, column=1, sticky="w", padx=4)
        self.lbl_seed = ttk.Label(self.frm_config)
        self.lbl_seed.grid(row=0, column=2, sticky="w")
        ttk.Entry(self.frm_config, textvariable=self.seed_var, width=8).grid(
            row=0, column=3, sticky="w"
        )
        self.lbl_quarters = ttk.Label(self.frm_config)
        self.lbl_quarters.grid(row=0, column=4, sticky="w")
        self.lbl_curriculum_summary = ttk.Label(
            self.frm_config, textvariable=self.curriculum_summary_var
        )
        self.lbl_curriculum_summary.grid(row=0, column=5, columnspan=1, sticky="w")
        self.lbl_days = ttk.Label(self.frm_config)
        self.lbl_days.grid(row=0, column=6, sticky="w")
        ttk.Entry(self.frm_config, textvariable=self.days_var, width=8).grid(
            row=0, column=7, sticky="w"
        )

        self.chk_stop_grad = ttk.Checkbutton(
            self.frm_config, variable=self.stop_grad_var
        )
        self.chk_stop_grad.grid(row=1, column=0, columnspan=2, sticky="w", pady=4)
        self.chk_seed_int = ttk.Checkbutton(
            self.frm_config, variable=self.seed_int_var
        )
        self.chk_seed_int.grid(row=1, column=2, columnspan=2, sticky="w")

        self.lbl_config = ttk.Label(self.frm_config)
        self.lbl_config.grid(row=2, column=0, sticky="w")
        ttk.Entry(self.frm_config, textvariable=self.config_var).grid(
            row=2, column=1, columnspan=5, sticky="ew", padx=4
        )
        ttk.Button(
            self.frm_config,
            text="…",
            width=3,
            command=lambda: self._browse_file(self.config_var),
        ).grid(row=2, column=6, sticky="w")

        self.lbl_baseline = ttk.Label(self.frm_config)
        self.lbl_baseline.grid(row=3, column=0, sticky="w")
        ttk.Entry(self.frm_config, textvariable=self.baseline_var).grid(
            row=3, column=1, columnspan=5, sticky="ew", padx=4
        )
        ttk.Button(
            self.frm_config,
            text="…",
            width=3,
            command=lambda: self._browse_file(self.baseline_var),
        ).grid(row=3, column=6, sticky="w")

        self.lbl_resume = ttk.Label(self.frm_config)
        self.lbl_resume.grid(row=4, column=0, sticky="w")
        ttk.Entry(self.frm_config, textvariable=self.resume_var).grid(
            row=4, column=1, columnspan=5, sticky="ew", padx=4
        )
        ttk.Button(
            self.frm_config,
            text="…",
            width=3,
            command=lambda: self._browse_file(self.resume_var),
        ).grid(row=4, column=6, sticky="w")

        self.lbl_output = ttk.Label(self.frm_config)
        self.lbl_output.grid(row=5, column=0, sticky="w")
        ttk.Entry(self.frm_config, textvariable=self.output_var).grid(
            row=5, column=1, columnspan=5, sticky="ew", padx=4
        )
        self.lbl_checkpoint = ttk.Label(self.frm_config)
        self.lbl_checkpoint.grid(row=6, column=0, sticky="w")
        ttk.Entry(self.frm_config, textvariable=self.checkpoint_var).grid(
            row=6, column=1, columnspan=5, sticky="ew", padx=4
        )

        ctrl = ttk.Frame(root)
        ctrl.grid(row=1, column=0, columnspan=2, sticky="ew", padx=4, pady=4)
        self.btn_start = ttk.Button(ctrl, command=self._on_start)
        self.btn_stop = ttk.Button(ctrl, command=self._on_stop, state="disabled")
        self.btn_resume = ttk.Button(ctrl, command=self._on_resume)
        self.btn_open = ttk.Button(ctrl, command=self._open_results)
        for b in (self.btn_start, self.btn_stop, self.btn_resume, self.btn_open):
            b.pack(side="left", padx=3)

        self.live_var = tk.StringVar()
        ttk.Label(ctrl, textvariable=self.live_var).pack(side="right", padx=8)

        paned = ttk.Panedwindow(root, orient="horizontal")
        paned.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=4, pady=4)

        left = ttk.Frame(paned)
        right = ttk.Frame(paned)
        paned.add(left, weight=1)
        paned.add(right, weight=2)

        self.lbl_log = ttk.Label(left)
        self.lbl_log.pack(anchor="w")
        self.log_text = tk.Text(left, height=20, wrap="word", font=("Consolas", 9))
        self.log_text.pack(fill="both", expand=True)
        self.log_text.configure(state="disabled")

        self.lbl_fitness = ttk.Label(right)
        self.lbl_fitness.pack(anchor="w")
        cols = ("q",) + tuple(PROCUREMENT_CRITERIA) + ("pass", "nr", "streak")
        self.tree = ttk.Treeview(right, columns=cols, show="headings", height=8)
        widths = {"q": 40, "pass": 40, "nr": 40, "streak": 48}
        for c in cols:
            self.tree.column(c, width=widths.get(c, 68), anchor="e")
        self.tree.pack(fill="x")
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        self.chart = FitnessChart(right, height=200)
        self.chart.pack(fill="both", expand=True, pady=(6, 0))

        self.lbl_diag = ttk.Label(right)
        self.lbl_diag.pack(anchor="w", pady=(6, 0))
        self.diag_text = tk.Text(right, height=10, wrap="word", font=("Consolas", 9))
        self.diag_text.pack(fill="both", expand=True)
        self.diag_text.configure(state="disabled")
        self._nr_floors: Dict[str, float] = {}
        self._selected_record_idx: Optional[int] = None

    def _build_sweep_tab(self) -> None:
        root = self.tab_sweep
        self.frm_sweep = ttk.LabelFrame(root, padding=10)
        self.frm_sweep.pack(fill="x", padx=8, pady=8)

        self.sweep_seeds_var = tk.StringVar(value="1, 7, 42, 100, 200")
        self.sweep_quarters_var = tk.StringVar(value="30")
        self.lbl_sweep_seeds = ttk.Label(self.frm_sweep)
        self.lbl_sweep_seeds.grid(row=0, column=0, sticky="w")
        ttk.Entry(self.frm_sweep, textvariable=self.sweep_seeds_var, width=40).grid(
            row=0, column=1, sticky="ew", padx=6
        )
        self.lbl_sweep_quarters = ttk.Label(self.frm_sweep)
        self.lbl_sweep_quarters.grid(row=1, column=0, sticky="w")
        ttk.Entry(self.frm_sweep, textvariable=self.sweep_quarters_var, width=8).grid(
            row=1, column=1, sticky="w", padx=6
        )
        self.lbl_sweep_writes = ttk.Label(self.frm_sweep, foreground="#555")
        self.lbl_sweep_writes.grid(row=2, column=0, columnspan=2, sticky="w", pady=6)

        btns = ttk.Frame(self.frm_sweep)
        btns.grid(row=3, column=0, columnspan=2, sticky="w")
        self.btn_sweep_start = ttk.Button(btns, command=self._on_sweep)
        self.btn_sweep_stop = ttk.Button(btns, command=self._on_stop)
        self.btn_sweep_to_report = ttk.Button(btns, command=self._sweep_to_report)
        self.btn_sweep_start.pack(side="left", padx=3)
        self.btn_sweep_stop.pack(side="left", padx=3)
        self.btn_sweep_to_report.pack(side="left", padx=3)

        self.lbl_sweep_note = ttk.Label(root, foreground="#555")
        self.lbl_sweep_note.pack(anchor="w", padx=12)

    def _build_report_tab(self) -> None:
        root = self.tab_report
        self.frm_report = ttk.LabelFrame(root, padding=8)
        self.frm_report.pack(fill="x", padx=8, pady=8)

        self.report_files: List[str] = []
        self.report_list = tk.Listbox(self.frm_report, height=6, selectmode="extended")
        self.report_list.pack(fill="x", expand=True)
        bf = ttk.Frame(self.frm_report)
        bf.pack(fill="x", pady=4)
        self.btn_report_add = ttk.Button(bf, command=self._report_add)
        self.btn_report_remove = ttk.Button(bf, command=self._report_remove)
        self.btn_report_clear = ttk.Button(bf, command=self._report_clear)
        self.btn_report_add_sweep = ttk.Button(bf, command=self._sweep_to_report)
        for b in (
            self.btn_report_add,
            self.btn_report_remove,
            self.btn_report_clear,
            self.btn_report_add_sweep,
        ):
            b.pack(side="left", padx=2)

        paths = ttk.Frame(root)
        paths.pack(fill="x", padx=8)
        self.report_baseline_var = tk.StringVar(value="results/stage_1a_baseline.json")
        self.lbl_report_write = ttk.Label(paths)
        self.lbl_report_write.pack(side="left")
        ttk.Entry(paths, textvariable=self.report_baseline_var).pack(
            side="left", fill="x", expand=True, padx=6
        )

        actions = ttk.Frame(root)
        actions.pack(fill="x", padx=8, pady=6)
        self.btn_report_check = ttk.Button(actions, command=self._on_report_check)
        self.btn_report_write = ttk.Button(actions, command=self._on_report_write)
        self.btn_report_check.pack(side="left", padx=3)
        self.btn_report_write.pack(side="left", padx=3)

        self.report_out = tk.Text(root, height=24, wrap="word", font=("Consolas", 9))
        self.report_out.pack(fill="both", expand=True, padx=8, pady=8)

    def _build_results_tab(self) -> None:
        root = self.tab_results
        bar = ttk.Frame(root)
        bar.pack(fill="x", padx=8, pady=8)
        self.results_path_var = tk.StringVar(value="")
        ttk.Entry(bar, textvariable=self.results_path_var).pack(
            side="left", fill="x", expand=True
        )
        self.btn_results_browse = ttk.Button(bar, command=self._results_browse)
        self.btn_results_load = ttk.Button(bar, command=self._results_load)
        self.btn_results_to_run = ttk.Button(bar, command=self._results_to_run)
        self.btn_results_browse.pack(side="left", padx=4)
        self.btn_results_load.pack(side="left", padx=4)
        self.btn_results_to_run.pack(side="left", padx=4)

        self.results_info = tk.StringVar()
        ttk.Label(root, textvariable=self.results_info).pack(anchor="w", padx=8)

        cols = ("q",) + tuple(PROCUREMENT_CRITERIA) + ("pass",)
        self.results_tree = ttk.Treeview(root, columns=cols, show="headings", height=14)
        for c in cols:
            self.results_tree.column(c, width=70, anchor="e")
        self.results_tree.pack(fill="both", expand=True, padx=8, pady=4)

        self.results_chart = FitnessChart(root, height=220)
        self.results_chart.pack(fill="both", expand=True, padx=8, pady=8)

    # ------------------------------------------------------------------ i18n
    def _set_language(self, lang: str) -> None:
        if lang == self.i18n.lang:
            self._highlight_lang_buttons()
            return
        self.i18n.set_language(lang)
        self._apply_language()

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
        t = self.t
        self.title(t("app.title", version=__version__))
        self.lbl_title.configure(text=t("app.title", version=__version__))
        self._highlight_lang_buttons()

        self.notebook.tab(self.tab_world, text=t("tab.world"))
        self.notebook.tab(self.tab_run, text=t("tab.run"))
        self.notebook.tab(self.tab_sweep, text=t("tab.sweep"))
        self.notebook.tab(self.tab_report, text=t("tab.report"))
        self.notebook.tab(self.tab_results, text=t("tab.results"))

        self.frm_config.configure(text=t("run.config"))
        self.frm_tuning.configure(text=t("world.tuning"))
        self.lbl_th_cost.configure(text=t("run.thresh_cost"))
        self.lbl_th_stock.configure(text=t("run.thresh_stockout"))
        self.lbl_th_budget.configure(text=t("run.thresh_budget"))
        self.lbl_th_risk.configure(text=t("run.thresh_risk"))
        self.lbl_th_div.configure(text=t("run.thresh_diversify"))
        self.lbl_th_cons.configure(text=t("run.thresh_consist"))
        self.lbl_budget_amt.configure(text=t("run.budget"))
        self.lbl_shock.configure(text=t("run.demand_shock"))
        self.lbl_default_p.configure(text=t("run.supplier_default"))
        if hasattr(self, "lbl_max_cycles"):
            self.lbl_max_cycles.configure(text=t("world.max_cycles"))
        if hasattr(self, "frm_world_quarters"):
            self.frm_world_quarters.configure(text=t("world.quarters_list"))
        if hasattr(self, "lbl_world_quarters"):
            self.lbl_world_quarters.configure(text=t("world.quarters_list"))
        if hasattr(self, "btn_q_add"):
            self.btn_q_add.configure(text=t("world.q_add"))
            self.btn_q_dup.configure(text=t("world.q_dup"))
            self.btn_q_del.configure(text=t("world.q_del"))
        if hasattr(self, "btn_world_apply"):
            self.btn_world_apply.configure(text=t("world.apply"))
            self.btn_world_save_file.configure(text=t("world.save_file"))
            self.btn_world_load_file.configure(text=t("world.load_file"))
            self.btn_world_template.configure(text=t("world.template"))
        if hasattr(self, "btn_prod_add"):
            add_txt = t("world.row_add_btn")
            del_txt = t("world.row_del_btn")
            self.btn_prod_add.configure(text=add_txt)
            self.btn_prod_del.configure(text=del_txt)
            self.btn_sup_add.configure(text=add_txt)
            self.btn_sup_del.configure(text=del_txt)
            self.btn_offer_add.configure(text=add_txt)
            self.btn_offer_del.configure(text=del_txt)
        self.lbl_world_budget.configure(text=t("world.budget_edit"))
        self.frm_world_products.configure(text=t("world.products"))
        self.frm_world_suppliers.configure(text=t("world.suppliers"))
        if hasattr(self, "frm_world_offers"):
            self.frm_world_offers.configure(text=t("world.offers"))
        apply_world_column_headers(self)

        self.lbl_stage.configure(text=t("run.stage"))
        self.lbl_seed.configure(text=t("run.seed"))
        self.lbl_quarters.configure(text=t("run.curriculum"))
        self.lbl_days.configure(text=t("run.days_q"))
        self.chk_stop_grad.configure(text=t("run.stop_grad"))
        self.chk_seed_int.configure(text=t("run.seed_intuition"))
        self.lbl_config.configure(text=t("run.config_yaml"))
        self.lbl_baseline.configure(text=t("run.baseline"))
        self.lbl_resume.configure(text=t("run.resume_ckpt"))
        self.lbl_output.configure(text=t("run.output_json"))
        self.lbl_checkpoint.configure(text=t("run.checkpoint"))
        self.btn_start.configure(text=t("run.start"))
        self.btn_stop.configure(text=t("run.soft_stop"))
        self.btn_resume.configure(text=t("run.resume"))
        self.btn_open.configure(text=t("run.open_results"))
        self.lbl_log.configure(text=t("run.log"))
        self.lbl_fitness.configure(text=t("run.fitness"))
        self.lbl_diag.configure(text=t("diag.title"))

        try:
            from nowa_sandbox.gui_world_tab import _sync_run_curriculum_label

            _sync_run_curriculum_label(self)
        except Exception:
            pass

        self.tree.heading("q", text=t("col.q"))
        self.tree.heading("pass", text=t("col.pass"))
        self.tree.heading("nr", text=t("col.nr"))
        self.tree.heading("streak", text=t("col.streak"))
        for c in PROCUREMENT_CRITERIA:
            self.tree.heading(c, text=criterion_column(self.i18n, c))

        self.frm_sweep.configure(text=t("sweep.title"))
        self.lbl_sweep_seeds.configure(text=t("sweep.seeds"))
        self.lbl_sweep_quarters.configure(text=t("sweep.quarters_each"))
        self.lbl_sweep_writes.configure(text=t("sweep.writes"))
        self.btn_sweep_start.configure(text=t("sweep.start"))
        self.btn_sweep_stop.configure(text=t("run.soft_stop"))
        self.btn_sweep_to_report.configure(text=t("sweep.to_report"))
        self.lbl_sweep_note.configure(text=t("sweep.note"))

        self.frm_report.configure(text=t("report.title"))
        self.btn_report_add.configure(text=t("report.add"))
        self.btn_report_remove.configure(text=t("report.remove"))
        self.btn_report_clear.configure(text=t("report.clear"))
        self.btn_report_add_sweep.configure(text=t("report.add_sweep"))
        self.lbl_report_write.configure(text=t("report.write_to"))
        self.btn_report_check.configure(text=t("report.check"))
        self.btn_report_write.configure(text=t("report.check_write"))

        self.btn_results_browse.configure(text=t("results.browse"))
        self.btn_results_load.configure(text=t("results.load"))
        self.btn_results_to_run.configure(text=t("results.to_run"))
        self.results_tree.heading("q", text=t("col.q"))
        self.results_tree.heading("pass", text=t("col.pass"))
        for c in PROCUREMENT_CRITERIA:
            self.results_tree.heading(c, text=criterion_column(self.i18n, c))

        labels = criterion_labels(self.i18n)
        self.chart.empty_message = t("chart.empty")
        self.results_chart.empty_message = t("chart.empty")
        self.chart.set_labels(labels)
        self.results_chart.set_labels(labels)

        if self._busy:
            self.status_var.set(t("status.running"))
        else:
            idle = {
                "",
                "Ready.",
                "Готово.",
                "Running…",
                "Выполняется…",
            }
            if self.status_var.get() in idle:
                self.status_var.set(t("status.ready"))

        if self._records:
            last = self._records[-1]
            n_pass = sum(
                1
                for r in self._records
                if (r.get("graduation") or {}).get("all_passed")
            )
            grad_at = last.get("graduated_at_quarter")
            if grad_at is None:
                for r in self._records:
                    if r.get("graduated_at_quarter") is not None:
                        grad_at = r.get("graduated_at_quarter")
                        break
            self.live_var.set(
                t(
                    "run.live",
                    q=last.get("quarter_index"),
                    n_pass=n_pass,
                    n=len(self._records),
                    grad_at=grad_at if grad_at is not None else "—",
                    streak=last.get("qualifying_streak", "—"),
                )
            )
            self._rebuild_tree_pass_labels()
        else:
            self.live_var.set(t("run.live_empty"))

        if self._results_meta:
            self.results_info.set(
                t(
                    "results.info",
                    name=self._results_meta["name"],
                    n=self._results_meta["n"],
                    n_pass=self._results_meta["n_pass"],
                )
            )
            self._rebuild_results_pass_labels()
        else:
            self.results_info.set(t("results.info_empty"))

        if self._last_report is not None:
            text = format_readiness_localized(self._last_report, self.i18n)
            self.report_out.delete("1.0", "end")
            self.report_out.insert("end", text)

        if self._selected_record_idx is not None:
            self._show_diagnosis_for_index(self._selected_record_idx)
        else:
            self._set_diag_text(self.t("diag.empty"))

    def _rebuild_tree_pass_labels(self) -> None:
        """Refresh yes/no in the live fitness table after a language switch."""
        for item, record in zip(self.tree.get_children(), self._records):
            self.tree.item(item, values=self._row_values(record))

    def _row_values(self, record: Dict[str, Any]) -> list:
        fitness = record.get("fitness") or {}
        values: list = [record.get("quarter_index")]
        for c in PROCUREMENT_CRITERIA:
            values.append(f"{float(fitness.get(c, 0.0)):.3f}")
        g = record.get("graduation") or {}
        values.append(self.t("yes") if g.get("all_passed") else self.t("no"))
        stage = (
            (g.get("stage") if isinstance(g, dict) else None)
            or self.stage_var.get().strip()
            or None
        )
        diag = diagnose_quarter(
            record,
            thresholds=self._current_thresholds(),
            nr_floors=self._nr_floors or None,
            stage=stage,
        )
        nr_applies = str(stage) == "1b" or isinstance(
            record.get("non_regression"), dict
        )
        if not nr_applies:
            values.append("—")
        else:
            values.append(self.t("yes") if not diag.nr_failures else self.t("no"))
        values.append(record.get("qualifying_streak", ""))
        return values

    def _set_diag_text(self, text: str) -> None:
        self.diag_text.configure(state="normal")
        self.diag_text.delete("1.0", "end")
        self.diag_text.insert("end", text)
        self.diag_text.configure(state="disabled")

    def _current_thresholds(self) -> Dict[str, float]:
        out = dict(GRADUATION_THRESHOLDS)
        for key, var in self.thresh_vars.items():
            try:
                out[key] = float(var.get())
            except (TypeError, ValueError):
                pass
        return out

    def _refresh_nr_floors(self) -> None:
        path = self.baseline_var.get().strip()
        if not path:
            self._nr_floors = dict(self.controller.last_nr_floors or {})
            return
        try:
            resolved = path if Path(path).is_absolute() else str(DEMO_ROOT / path)
            bundle = load_baseline_bundle(resolved)
            self._nr_floors = nr_floors_from_baseline(
                bundle.get("stage_1a_baseline") or {},
                bundle.get("stage_1a_spread_iqr") or {},
            )
        except Exception:
            self._nr_floors = dict(self.controller.last_nr_floors or {})

    def _on_tree_select(self, _event=None) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        item = sel[0]
        kids = list(self.tree.get_children())
        try:
            idx = kids.index(item)
        except ValueError:
            return
        self._show_diagnosis_for_index(idx)
        # Keep World tab in sync with the selected quarter.
        try:
            q = int(self._records[idx].get("quarter_index") or 0)
            if q > 0 and hasattr(self, "world_quarter_var"):
                self.world_quarter_var.set(str(q))
        except Exception:
            pass

    def _show_diagnosis_for_index(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._records):
            self._set_diag_text(self.t("diag.empty"))
            return
        self._selected_record_idx = idx
        self._refresh_nr_floors()
        record = self._records[idx]
        diagnosis = diagnose_quarter(
            record,
            thresholds=self._current_thresholds(),
            nr_floors=self._nr_floors or None,
            stage=(record.get("graduation") or {}).get("stage")
            or self.stage_var.get().strip()
            or None,
        )
        text = format_diagnosis_text(
            diagnosis,
            translate=self.t,
            criterion_label=lambda c: criterion_legend(self.i18n, c),
        )
        self._set_diag_text(text)

    def _rebuild_results_pass_labels(self) -> None:
        records = getattr(self, "_loaded_results", None) or []
        items = self.results_tree.get_children()
        for item, record in zip(items, records):
            fitness = record.get("fitness") or {}
            values = [record.get("quarter_index")]
            for c in PROCUREMENT_CRITERIA:
                values.append(f"{float(fitness.get(c, 0.0)):.3f}")
            g = record.get("graduation") or {}
            values.append(self.t("yes") if g.get("all_passed") else self.t("no"))
            self.results_tree.item(item, values=values)

    # ------------------------------------------------------------------ helpers
    def _filetypes_data(self):
        return [
            (self.t("filetypes.data"), "*.json *.yaml *.yml *.ckpt *.nowa"),
            (self.t("filetypes.all"), "*.*"),
        ]

    def _filetypes_json(self):
        return [
            (self.t("filetypes.json"), "*.json"),
            (self.t("filetypes.all"), "*.*"),
        ]

    def _browse_file(self, var: tk.StringVar) -> None:
        path = filedialog.askopenfilename(
            initialdir=str(DEMO_ROOT),
            filetypes=self._filetypes_data(),
        )
        if path:
            try:
                rel = os.path.relpath(path, DEMO_ROOT)
                var.set(rel if not rel.startswith("..") else path)
            except ValueError:
                var.set(path)

    def _open_results(self) -> None:
        folder = DEMO_ROOT / "results"
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(str(folder))  # noqa: S606 - Windows lab helper

    def _append_log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.btn_start.configure(state="disabled" if busy else "normal")
        self.btn_resume.configure(state="disabled" if busy else "normal")
        self.btn_stop.configure(state="normal" if busy else "disabled")
        self.btn_sweep_start.configure(state="disabled" if busy else "normal")
        self.status_var.set(self.t("status.running") if busy else self.t("status.ready"))

    def _clear_live(self) -> None:
        self._records.clear()
        self._selected_record_idx = None
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.chart.clear()
        self.live_var.set(self.t("run.live_empty"))
        self._set_diag_text(self.t("diag.empty"))

    def _add_record(self, record: Dict[str, Any]) -> None:
        self._records.append(record)
        self.tree.insert("", "end", values=self._row_values(record))
        self.tree.yview_moveto(1.0)

        self.live_var.set(
            self.t(
                "run.live",
                q=record.get("quarter_index"),
                n_pass=sum(
                    1
                    for r in self._records
                    if (r.get("graduation") or {}).get("all_passed")
                ),
                n=len(self._records),
                grad_at=self._graduated_at_label(),
                streak=record.get("qualifying_streak", "—"),
            )
        )
        self._refresh_chart(self.chart, self._records)
        # Auto-select latest quarter for diagnosis.
        kids = self.tree.get_children()
        if kids:
            self.tree.selection_set(kids[-1])
            self._show_diagnosis_for_index(len(self._records) - 1)

    def _graduated_at_label(self) -> str:
        for record in self._records:
            gat = record.get("graduated_at_quarter")
            if gat is not None:
                return str(gat)
        if any(r.get("graduated") for r in self._records):
            for r in self._records:
                if (r.get("graduation") or {}).get("all_passed"):
                    return str(r.get("quarter_index"))
        return "—"

    def _refresh_chart(self, chart: FitnessChart, records: Sequence[Dict[str, Any]]) -> None:
        if not records:
            chart.clear()
            return
        cats = [str(r.get("quarter_index")) for r in records]
        series = {
            c: [float((r.get("fitness") or {}).get(c, 0.0)) for r in records]
            for c in STAGE_1A_CRITERIA
        }
        for c in ("supplier_diversification", "decision_consistency"):
            series[c] = [float((r.get("fitness") or {}).get(c, 0.0)) for r in records]
        chart.set_data(cats, series, labels=criterion_labels(self.i18n))

    def _parse_run_spec(self, *, resume: bool = False) -> RunSpec:
        stage = self.stage_var.get().strip()
        if stage not in ("1a", "1b"):
            raise ValueError(self.t("err.stage"))
        seed = int(self.seed_var.get())
        days = int(self.days_var.get())
        baseline = self.baseline_var.get().strip() or None
        resume_from = self.resume_var.get().strip() or None
        if not resume:
            resume_from = None
        if stage == "1b" and not baseline and not resume_from:
            raise ValueError(self.t("err.baseline_1b"))
        thresholds = self._current_thresholds()
        curriculum = get_curriculum_for_run(self)
        try:
            max_cycles = int(self.max_cycles_var.get())
        except Exception:
            max_cycles = 500
        n_cur = int(curriculum.n_quarters)
        return RunSpec(
            stage=stage,
            seed=seed,
            quarters=n_cur,
            days_per_quarter=days,
            budget=float(self.budget_var.get()),
            products=None,
            suppliers=None,
            demand_shock_probability=float(self.demand_shock_var.get()),
            supplier_default_probability=float(self.supplier_default_var.get()),
            max_lead_time_days=int(self.max_lead_var.get()),
            max_demand_per_day=float(self.max_demand_var.get()),
            min_supplier_reliability=float(self.min_reliability_var.get()),
            config_path=self.config_var.get().strip() or "configs/default_world.yaml",
            baseline_from=baseline,
            resume_from=resume_from,
            output=self.output_var.get().strip() or "results/lab_run.json",
            checkpoint=self.checkpoint_var.get().strip() or None,
            stop_on_graduation=bool(self.stop_grad_var.get()),
            seed_intuition=bool(self.seed_int_var.get()),
            threshold_overrides=thresholds,
            quarter_overrides={},
            curriculum=curriculum,
            max_cycles=max(1, max_cycles),
        )

    # ------------------------------------------------------------------ queue bridge
    def _pump_queue(self) -> None:
        try:
            while True:
                kind, payload = self._ui_queue.get_nowait()
                if kind == "log":
                    self._append_log(payload)
                elif kind == "quarter":
                    self._add_record(payload)
                elif kind == "done":
                    result, error = payload
                    self._set_busy(False)
                    if error is not None:
                        self.status_var.set(self.t("status.error", error=error))
                        messagebox.showerror(self.t("dialog.run_failed"), str(error))
                    else:
                        graduated = bool(getattr(result, "graduated", False))
                        self.status_var.set(
                            self.t("status.finished_graduated")
                            if graduated
                            else self.t("status.finished")
                        )
                elif kind == "report":
                    self.report_out.delete("1.0", "end")
                    self.report_out.insert("end", payload)
        except queue.Empty:
            pass
        self.after(100, self._pump_queue)

    def _cb_log(self, message: str) -> None:
        self._ui_queue.put(("log", message))

    def _cb_quarter(self, record: Dict[str, Any]) -> None:
        self._ui_queue.put(("quarter", record))

    def _cb_done(self, result, error) -> None:
        self._ui_queue.put(("done", (result, error)))

    # ------------------------------------------------------------------ actions
    def _on_start(self) -> None:
        if self.controller.is_busy:
            messagebox.showwarning(self.t("dialog.busy_title"), self.t("dialog.busy"))
            return
        try:
            spec = self._parse_run_spec(resume=False)
        except Exception as exc:
            messagebox.showerror(self.t("dialog.invalid_config"), str(exc))
            return
        if self.output_var.get() in ("", "results/lab_run.json"):
            self.output_var.set(f"results/lab_stage{spec.stage}_seed{spec.seed}.json")
            spec.output = self.output_var.get()
        if self.checkpoint_var.get() in ("", "checkpoints/lab_run.ckpt"):
            self.checkpoint_var.set(
                f"checkpoints/lab_stage{spec.stage}_seed{spec.seed}.ckpt"
            )
            spec.checkpoint = self.checkpoint_var.get()

        self._clear_live()
        self._refresh_nr_floors()
        self._append_log(f"=== Start stage {spec.stage} seed={spec.seed} ===")
        self._set_busy(True)
        try:
            self.controller.start_run(
                spec,
                on_log=self._cb_log,
                on_quarter=self._cb_quarter,
                on_done=self._cb_done,
            )
        except RuntimeError as exc:
            self._set_busy(False)
            messagebox.showerror(self.t("dialog.cannot_start"), str(exc))

    def _on_resume(self) -> None:
        ckpt = self.resume_var.get().strip() or self.checkpoint_var.get().strip()
        if not ckpt:
            messagebox.showinfo(
                self.t("dialog.resume_title"), self.t("dialog.resume_need_ckpt")
            )
            return
        self.resume_var.set(ckpt)
        if self.controller.is_busy:
            messagebox.showwarning(self.t("dialog.busy_title"), self.t("dialog.busy"))
            return
        try:
            spec = self._parse_run_spec(resume=True)
        except Exception as exc:
            messagebox.showerror(self.t("dialog.invalid_config"), str(exc))
            return
        self._clear_live()
        self._append_log(f"=== Resume from {spec.resume_from} ===")
        self._set_busy(True)
        try:
            self.controller.start_run(
                spec,
                on_log=self._cb_log,
                on_quarter=self._cb_quarter,
                on_done=self._cb_done,
            )
        except RuntimeError as exc:
            self._set_busy(False)
            messagebox.showerror(self.t("dialog.cannot_resume"), str(exc))

    def _on_stop(self) -> None:
        if not self.controller.is_busy:
            return
        self.controller.request_stop()
        self.status_var.set(self.t("status.soft_stop"))
        self._append_log(self.t("log.soft_stop"))

    def _on_sweep(self) -> None:
        if self.controller.is_busy:
            messagebox.showwarning(self.t("dialog.busy_title"), self.t("dialog.busy"))
            return
        try:
            seeds = [
                int(x.strip())
                for x in self.sweep_seeds_var.get().split(",")
                if x.strip()
            ]
            quarters = int(self.sweep_quarters_var.get())
        except ValueError:
            messagebox.showerror(self.t("dialog.invalid"), self.t("dialog.seeds_int"))
            return
        if not seeds:
            messagebox.showerror(self.t("dialog.invalid"), self.t("dialog.need_seed"))
            return
        spec = SweepSpec(
            seeds=seeds,
            quarters=quarters,
            config_path=self.config_var.get().strip() or "configs/default_world.yaml",
            stop_on_graduation=False,
        )
        self._clear_live()
        self._append_log(f"=== Sweep seeds={seeds} quarters={quarters} ===")
        self._set_busy(True)
        try:
            self.controller.start_sweep(
                spec,
                on_log=self._cb_log,
                on_quarter=self._cb_quarter,
                on_done=self._cb_done,
            )
        except RuntimeError as exc:
            self._set_busy(False)
            messagebox.showerror(self.t("dialog.cannot_sweep"), str(exc))

    def _sweep_to_report(self) -> None:
        try:
            seeds = [
                int(x.strip())
                for x in self.sweep_seeds_var.get().split(",")
                if x.strip()
            ]
        except ValueError:
            seeds = [1, 7, 42, 100, 200]
        paths = []
        for seed in seeds:
            p = DEMO_ROOT / f"results/stage1a_lab_seed{seed}.json"
            alt = DEMO_ROOT / f"results/stage1a_v13_seed{seed}.json"
            if p.exists():
                paths.append(str(p))
            elif alt.exists():
                paths.append(str(alt))
        if not paths:
            messagebox.showinfo(
                self.t("dialog.no_files_title"), self.t("dialog.no_files")
            )
            return
        for path in paths:
            if path not in self.report_files:
                self.report_files.append(path)
                self.report_list.insert("end", path)
        self.status_var.set(self.t("status.added_files", n=len(paths)))

    def _report_add(self) -> None:
        paths = filedialog.askopenfilenames(
            initialdir=str(DEMO_ROOT / "results"),
            filetypes=self._filetypes_json(),
        )
        for path in paths:
            if path not in self.report_files:
                self.report_files.append(path)
                self.report_list.insert("end", path)

    def _report_remove(self) -> None:
        selected = list(self.report_list.curselection())
        for idx in reversed(selected):
            self.report_list.delete(idx)
            del self.report_files[idx]

    def _report_clear(self) -> None:
        self.report_list.delete(0, "end")
        self.report_files.clear()

    def _on_report_check(self) -> None:
        self._run_report(write=False)

    def _on_report_write(self) -> None:
        self._run_report(write=True)

    def _run_report(self, write: bool) -> None:
        if not self.report_files:
            messagebox.showinfo(
                self.t("dialog.report_title"), self.t("dialog.report_need_files")
            )
            return
        out = self.report_baseline_var.get().strip() if write else None
        if write and out and not Path(out).is_absolute():
            out = str(DEMO_ROOT / out)
        try:
            report = self.controller.write_baseline_report(
                self.report_files, write_baseline_to=out, method="median_all"
            )
            self._last_report = report
            text = format_readiness_localized(report, self.i18n)
            self._ui_queue.put(("report", text))
            if write and report.get("baseline_path"):
                self.baseline_var.set(
                    os.path.relpath(report["baseline_path"], DEMO_ROOT)
                    if str(report["baseline_path"]).startswith(str(DEMO_ROOT))
                    else report["baseline_path"]
                )
                self.status_var.set(
                    self.t("status.baseline_written", path=report["baseline_path"])
                )
            elif write and report.get("refused"):
                messagebox.showwarning(
                    self.t("dialog.baseline_refused"), report["refused"]
                )
        except Exception as exc:
            messagebox.showerror(self.t("dialog.report_failed"), str(exc))

    def _results_browse(self) -> None:
        path = filedialog.askopenfilename(
            initialdir=str(DEMO_ROOT / "results"),
            filetypes=self._filetypes_json(),
        )
        if path:
            self.results_path_var.set(path)

    def _results_load(self) -> None:
        path = self.results_path_var.get().strip()
        if not path:
            return
        try:
            records = load_results_json(path)
        except Exception as exc:
            messagebox.showerror(self.t("dialog.load_failed"), str(exc))
            return
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)
        for record in records:
            fitness = record.get("fitness") or {}
            values = [record.get("quarter_index")]
            for c in PROCUREMENT_CRITERIA:
                values.append(f"{float(fitness.get(c, 0.0)):.3f}")
            g = record.get("graduation") or {}
            values.append(self.t("yes") if g.get("all_passed") else self.t("no"))
            self.results_tree.insert("", "end", values=values)
        self._refresh_chart(self.results_chart, records)
        n_pass = sum(
            1 for r in records if (r.get("graduation") or {}).get("all_passed")
        )
        self._results_meta = {
            "name": Path(path).name,
            "n": len(records),
            "n_pass": n_pass,
        }
        self.results_info.set(
            self.t(
                "results.info",
                name=self._results_meta["name"],
                n=self._results_meta["n"],
                n_pass=self._results_meta["n_pass"],
            )
        )
        self._loaded_results = records

    def _results_to_run(self) -> None:
        records = getattr(self, "_loaded_results", None)
        if not records:
            self._results_load()
            records = getattr(self, "_loaded_results", None)
        if not records:
            return
        self._clear_live()
        for record in records:
            self._add_record(record)
        self.status_var.set(self.t("status.loaded_run", n=len(records)))

    def _on_close(self) -> None:
        if self.controller.is_busy:
            if not messagebox.askyesno(
                self.t("dialog.quit_title"), self.t("dialog.quit_busy")
            ):
                return
            self.controller.request_stop()
        self.destroy()


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    os.chdir(DEMO_ROOT)
    if str(DEMO_ROOT / "src") not in sys.path:
        sys.path.insert(0, str(DEMO_ROOT / "src"))
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
    app = SandboxLabApp(lang=args.lang)
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
