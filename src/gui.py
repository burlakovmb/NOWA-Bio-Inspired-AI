import tkinter as tk
from tkinter import scrolledtext, messagebox, ttk, filedialog
import asyncio
import json
import threading
import time

from hippocampus import NOWAHippocampus
from cortex import CortexMemory
from selector import ActionSelector
from agent import Agent
from sleep import SleepManager
from storage import AgentStorage
from data_loader import (
    load_experience_from_dataset,
    load_experiences_from_directory,
    load_experiences_from_datasets_folder,
    load_realizations_from_datasets,
    load_habits_from_datasets
)
from experience import Event, Path, EventType
from action_intent import RealizationMemory
from action_realizer import ActionRealizer, ActionRealizerWithSelector
from intent_memory import IntentMemory
from affect import AffectiveState
from self_model import SelfModel
from gui_i18n import (
    PHRASES,
    action_label,
    axis_label,
    drive_label,
    emotion_label,
    failure_label,
    format_auto_thought,
    get_language,
    mode_label,
    resolve_lang,
    set_language,
    tr,
    translate_block,
)
try:
    from autonomous_organism import (
        AutonomousOrganismAgent,
        DriveSystem,
        EnergySystem,
        OrganismHardLimits,
        SpeechGovernor,
    )
except Exception:
    AutonomousOrganismAgent = None
    DriveSystem = None
    EnergySystem = None
    OrganismHardLimits = None
    SpeechGovernor = None


class GUIEnvironmentInterface:
    """Simple environment adapter for interactive External Interaction Layer controls."""

    def __init__(self):
        self.observe_counter = 0

    def execute(self, action):
        params = dict(getattr(action, "parameters", {}) or {})
        try:
            reward = float(params.get("reward", 0.0))
        except Exception:
            reward = 0.0
        reward = max(-1.0, min(1.0, reward))

        try:
            success_probability = float(params.get("success_probability", 0.5 + 0.5 * reward))
        except Exception:
            success_probability = 0.5
        success_probability = max(0.0, min(1.0, success_probability))

        try:
            latency = float(params.get("latency", 0.02))
        except Exception:
            latency = 0.02
        latency = max(0.0, latency)

        signal = {"source": "gui_environment", "echo": dict(params)}
        custom_signal = params.get("signal")
        if isinstance(custom_signal, dict):
            signal.update(custom_signal)

        return {
            "reward": reward,
            "signal": signal,
            "success_probability": success_probability,
            "latency": latency,
        }

    def observe(self):
        self.observe_counter += 1
        return {
            "timestamp": time.time(),
            "source": "gui_environment",
            "payload": {
                "event": "polled_observation",
                "index": int(self.observe_counter),
            },
            "uncertainty": 0.25,
        }


class NOWAGUI:
    def __init__(self, root, lang=None):
        set_language(resolve_lang(lang))
        self.root = root
        self._lang_buttons = {}
        self._set_title(self.root, "NOWA - Cognitive Agent Interface")
        self.root.geometry("1200x750")
        
        # Initialize agent
        self.hippocampus = NOWAHippocampus()
        self.cortex = CortexMemory()
        self.selector = ActionSelector(actions=[
            "ответить_кто_я",
            "сказать_привет",
            "отказаться",
            "помочь",
            "задать_вопрос"
        ])
        self.intent_memory = IntentMemory()
        self.sleep_manager = SleepManager(self.hippocampus, self.cortex, self.intent_memory)
        self.agent = Agent(self.hippocampus, self.cortex, self.selector, self.sleep_manager, self.intent_memory)
        self.environment_interface = GUIEnvironmentInterface()
        try:
            if hasattr(self.agent, "set_environment_interface"):
                self.agent.set_environment_interface(self.environment_interface)
        except Exception as e:
            print(f"[GUI] External environment init skipped: {e}")
        
        # Initialize self-model for introspection
        self.self_model = SelfModel(self.agent)
        
        # Initialize realization system (adaptive "mouth")
        self.realization_memory = RealizationMemory()
        self.action_realizer = ActionRealizer(self.realization_memory)
        self.realizer_with_selector = ActionRealizerWithSelector(self.action_realizer)
        
        # Load initial realizations from datasets if available
        self._load_initial_realizations()
        
        # Storage
        self.storage = AgentStorage()
        self.chat_history = []
        
        # Keep track of inspector window
        self.inspector_window = None
        self.autonomous_errors_window = None
        self.autonomous_errors_text = None
        
        # Time tracking for affect decay
        self.last_process_time = time.time()
        self.autonomous_last_tick_wall_time = time.time()
        self.autonomous_last_thought_time = 0.0
        self.autonomous_last_thought_signature = None
        self.autonomous_runtime = None
        self.autonomous_tick_interval_ms = 1000  # 1 tick == 1 second
        self.autonomous_lifecycle_running = False
        try:
            self._init_autonomous_runtime()
        except Exception as e:
            self.autonomous_runtime = None
            print(f"[GUI] Autonomous init disabled: {e}")
        
        self.setup_ui()
        self._localize_widget(self.root)
        self._style_lang_buttons()
        self.last_action = None
        self.last_context = None
        self.external_ui_busy = False
        try:
            self.update_autonomous_display()
        except Exception as e:
            print(f"[GUI] Autonomous display init skipped: {e}")
        try:
            self.update_external_interaction_display()
        except Exception as e:
            print(f"[GUI] External layer display init skipped: {e}")
        self.autonomous_lifecycle_running = True
        try:
            self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        except Exception:
            pass
        self._schedule_autonomous_lifecycle_tick()

    def _init_autonomous_runtime(self):
        """Initialize optional autonomous-organism runtime for GUI visualization."""
        self.autonomous_runtime = None
        # Preferred path: runtime is integrated inside Agent API.
        try:
            if hasattr(self.agent, "init_autonomous_runtime"):
                self.autonomous_runtime = self.agent.init_autonomous_runtime()
                return
        except Exception as e:
            print(f"[GUI] Agent autonomous init failed: {e}")

        # Fallback path for legacy Agent versions.
        if (
            AutonomousOrganismAgent is None
            or DriveSystem is None
            or EnergySystem is None
            or OrganismHardLimits is None
            or SpeechGovernor is None
        ):
            return

        affective_core = getattr(self.agent, "affective_space", None)
        if affective_core is None:
            return

        try:
            hard_limits = OrganismHardLimits(
                max_internal_cycles_per_window=10,
                internal_cycles_window_seconds=60.0,
                max_active_memory_recalls=6,
                max_speech_events_per_interval=4,
                speech_interval_seconds=30.0,
                energy_floor_threshold=0.08,
                drive_thresholds={
                    "curiosity": 0.45,
                    "social_drive": 0.50,
                    "goal_tension": 0.50,
                    "exploration": 0.48,
                    "energy_need": 0.55,
                },
            )
            drive_system = DriveSystem(
                initial_drives={
                    "curiosity": 0.18,
                    "social_drive": 0.22,
                    "goal_tension": 0.08,
                    "exploration": 0.12,
                    "energy_need": 0.02,
                }
            )
            energy_system = EnergySystem(
                energy=0.95,
                fatigue=0.05,
                cognitive_cost=0.03,
                recovery_rate=0.05,
                low_threshold=0.25,
                floor_threshold=0.08,
            )
            speech_governor = SpeechGovernor(
                communication_threshold=0.65,
                relevance_minimum=0.45,
                cooldown_seconds=6.0,
                max_speech_events_per_interval=hard_limits.max_speech_events_per_interval,
                speech_interval_seconds=hard_limits.speech_interval_seconds,
            )

            self.autonomous_runtime = AutonomousOrganismAgent(
                affective_core=affective_core,
                cognitive_core=self.selector,
                decision_engine=self.selector,
                memory_system=self.hippocampus,
                drive_system=drive_system,
                energy_system=energy_system,
                speech_governor=speech_governor,
                hard_limits=hard_limits,
                internal_trigger_threshold=0.45,
            )
        except Exception as e:
            self.autonomous_runtime = None
            print(f"[GUI] Autonomous runtime init skipped: {e}")

    def _run_autonomous_ticks(self, count: int = 1, dt_override: float = None, emit_chat: bool = False):
        try:
            ticks = max(1, int(count))
        except Exception:
            ticks = 1

        if dt_override is None:
            now = time.time()
            elapsed = max(0.01, now - getattr(self, "autonomous_last_tick_wall_time", now))
            dt = max(0.05, min(5.0, elapsed))
            self.autonomous_last_tick_wall_time = now
        else:
            dt = max(0.01, min(10.0, float(dt_override)))
            self.autonomous_last_tick_wall_time = time.time()

        last_tick = None
        try:
            # Prefer agent-level integration API.
            if hasattr(self.agent, "autonomous_tick"):
                for _ in range(ticks):
                    last_tick = self.agent.autonomous_tick(dt)
                self.autonomous_runtime = getattr(self.agent, "autonomous_runtime", self.autonomous_runtime)
                if not last_tick:
                    return None
            else:
                runtime = getattr(self, "autonomous_runtime", None)
                if runtime is None:
                    return None
                for _ in range(ticks):
                    last_tick = runtime.organism_step(dt)
        except Exception as e:
            if emit_chat:
                self.add_to_chat(tr("[AUTO] error: {error}", error=str(e)), "error")
            print(f"[GUI] Autonomous tick error: {e}")
            return None

        if emit_chat and last_tick is not None:
            mode = mode_label(last_tick.get("physiology_mode") or "idle")
            load = float(last_tick.get("cognitive_load", 0.0))
            active_drive = drive_label(last_tick.get("active_drive") or "none")
            energy_level = float(last_tick.get("energy_level", 0.0))
            cycle_flag = bool(last_tick.get("internal_cycle_triggered", False))
            self.add_to_chat(
                tr(
                    "[AUTO] tick x{ticks} | mode={mode} | load={load:.2f} | drive={drive} | energy={energy:.2f} | cycle={cycle}",
                    ticks=ticks,
                    mode=mode,
                    load=load,
                    drive=active_drive,
                    energy=energy_level,
                    cycle=cycle_flag,
                ),
                "system",
            )
            if bool(last_tick.get("speech_event", False)):
                speech_text = str(last_tick.get("speech_output", "")).strip()
                if speech_text:
                    self.add_to_chat(tr("[AUTO speech] {speech}", speech=speech_text), "system")

        return last_tick

    def run_autonomous_ticks_button(self, count: int):
        self._run_autonomous_ticks(count=count, emit_chat=True)
        self.update_affect_display()

    def _schedule_autonomous_lifecycle_tick(self):
        if not getattr(self, "autonomous_lifecycle_running", False):
            return
        interval_ms = max(200, int(getattr(self, "autonomous_tick_interval_ms", 1000)))
        try:
            if self.root is None or not self.root.winfo_exists():
                return
            self.root.after(interval_ms, self._autonomous_lifecycle_tick)
        except Exception:
            return

    def _autonomous_lifecycle_tick(self):
        if not getattr(self, "autonomous_lifecycle_running", False):
            return

        try:
            if self.root is None or not self.root.winfo_exists():
                return
            tick = self._run_autonomous_ticks(count=1, dt_override=1.0, emit_chat=False)

            if tick is not None:
                thought_text = self._format_autonomous_internal_thought(tick)
                if thought_text:
                    self.add_to_chat(thought_text, "system")

            if tick is not None and bool(tick.get("speech_event", False)):
                speech_text = str(tick.get("speech_output", "")).strip()
                if speech_text:
                    self.add_to_chat(tr("[AUTO] {speech}", speech=speech_text), "system")

            # Keep legacy affect widgets in sync with canonical affective core.
            try:
                projector = getattr(self.agent, "_project_legacy_affect_from_affective_space", None)
                if callable(projector):
                    projector(blend=0.3)
            except Exception:
                pass

            self.update_affect_display()
            self.update_temporal_display()
            self.update_stats(self.last_action or "auto")
        except Exception as e:
            print(f"[GUI] Autonomous lifecycle loop error: {e}")
        finally:
            self._schedule_autonomous_lifecycle_tick()

    def _format_autonomous_internal_thought(self, tick):
        if not isinstance(tick, dict):
            return ""
        if not bool(tick.get("internal_cycle_triggered", False)):
            return ""

        runtime = getattr(self, "autonomous_runtime", None)
        if runtime is None:
            runtime = getattr(self.agent, "autonomous_runtime", None)

        last_result = {}
        try:
            if runtime is not None and getattr(runtime, "internal_loop", None) is not None:
                last_result = dict(getattr(runtime.internal_loop, "last_result", {}) or {})
        except Exception:
            last_result = {}

        active_drive = str(tick.get("active_drive") or last_result.get("active_drive") or "none")
        best_action = str(tick.get("internal_best_action") or last_result.get("best_action") or "").strip()
        if not best_action:
            best_action = str((last_result.get("decision", {}) or {}).get("best_action", "")).strip()
        confidence = tick.get("internal_confidence", last_result.get("confidence", None))
        try:
            confidence_v = float(confidence) if confidence is not None else None
        except Exception:
            confidence_v = None

        signature = (active_drive, best_action, round(confidence_v, 2) if confidence_v is not None else None)
        now = time.time()
        if (
            signature == getattr(self, "autonomous_last_thought_signature", None)
            and (now - float(getattr(self, "autonomous_last_thought_time", 0.0))) < 4.0
        ):
            return ""
        self.autonomous_last_thought_signature = signature
        self.autonomous_last_thought_time = now

        return format_auto_thought(active_drive, best_action, confidence_v)

    def _on_close(self):
        self.autonomous_lifecycle_running = False
        try:
            if self.inspector_window and self.inspector_window.winfo_exists():
                self.inspector_window.destroy()
        except Exception:
            pass
        try:
            if self.autonomous_errors_window and self.autonomous_errors_window.winfo_exists():
                self.autonomous_errors_window.destroy()
        except Exception:
            pass
        self.root.destroy()

    def _classify_autonomous_failure(self, failure_item):
        mode = str((failure_item or {}).get("failure_mode", "")).strip()
        real_error_modes = {
            "affect_mutation_outside_interface",
            "internal_affect_apply_failed",
            "invariant_violation",
            "energy_deadlock",
        }
        if mode in real_error_modes:
            return "error"
        return "warning"

    def _split_autonomous_failures(self, failures):
        all_failures = list(failures or [])
        real_errors = []
        warnings = []
        for item in all_failures:
            level = self._classify_autonomous_failure(item)
            if level == "error":
                real_errors.append(item)
            else:
                warnings.append(item)
        return real_errors, warnings

    def _format_autonomous_failures_text(self, real_errors, warnings):
        lines = []
        lines.append(f"{tr('Критичные ошибки:')} {len(real_errors)}")
        lines.append(f"{tr('Предупреждения:')} {len(warnings)}")
        lines.append("")
        if not real_errors:
            lines.append(tr("Критичных ошибок не зафиксировано."))
            return "\n".join(lines)

        lines.append(tr("Список критичных ошибок:"))
        for idx, item in enumerate(real_errors, start=1):
            mode = failure_label(item.get("failure_mode", "unknown"))
            ts = item.get("timestamp", None)
            details = item.get("details", {}) or {}
            try:
                ts_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(ts)))
            except Exception:
                ts_str = str(ts)
            lines.append(f"{idx}. {mode} @ {ts_str}")
            if details:
                lines.append(f"   details: {details}")
        return "\n".join(lines)

    def _refresh_autonomous_errors_window(self):
        window = getattr(self, "autonomous_errors_window", None)
        text_widget = getattr(self, "autonomous_errors_text", None)
        if window is None or text_widget is None:
            return
        try:
            if not window.winfo_exists():
                return
        except Exception:
            return

        runtime = getattr(self, "autonomous_runtime", None)
        failures = []
        if runtime is not None:
            try:
                snapshot = runtime.snapshot()
                failures = list(snapshot.get("failures", []) or [])
            except Exception:
                failures = []
        real_errors, warnings = self._split_autonomous_failures(failures)
        header = getattr(self, "autonomous_errors_header", None)
        if header is not None:
            try:
                header.config(text=f"{tr('Критичные ошибки:')} {len(real_errors)}")
            except Exception:
                pass
        content = self._format_autonomous_failures_text(real_errors, warnings)
        try:
            text_widget.config(state=tk.NORMAL)
            text_widget.delete(1.0, tk.END)
            text_widget.insert(1.0, content)
            text_widget.config(state=tk.DISABLED)
        except Exception:
            pass

    def _open_autonomous_errors_window(self, _event=None):
        runtime = getattr(self, "autonomous_runtime", None)
        failures = []
        if runtime is not None:
            try:
                snapshot = runtime.snapshot()
                failures = list(snapshot.get("failures", []) or [])
            except Exception:
                failures = []
        real_errors, _warnings = self._split_autonomous_failures(failures)

        try:
            if self.autonomous_errors_window and self.autonomous_errors_window.winfo_exists():
                self._refresh_autonomous_errors_window()
                self.autonomous_errors_window.lift()
                self.autonomous_errors_window.focus_force()
                return
        except Exception:
            pass

        window = tk.Toplevel(self.root)
        self._set_title(window, "Критичные ошибки автономного организма")
        window.geometry("760x420")
        window.configure(bg="#f8fbf9")
        self.autonomous_errors_window = window

        header_color = "#c0392b" if real_errors else "#2e7d32"
        header_text = f"{tr('Критичные ошибки:')} {len(real_errors)}"
        header = tk.Label(
            window,
            text=header_text,
            font=("Helvetica", 11, "bold"),
            bg="#f8fbf9",
            fg=header_color,
            anchor=tk.W,
            justify=tk.LEFT,
        )
        header.pack(fill=tk.X, padx=10, pady=(10, 6))
        self.autonomous_errors_header = header

        text_widget = scrolledtext.ScrolledText(
            window,
            wrap=tk.WORD,
            font=("Courier", 9),
            bg="#ffffff",
            fg="#2c3e50",
        )
        text_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        self.autonomous_errors_text = text_widget
        self._refresh_autonomous_errors_window()

        try:
            self._bind_clipboard_shortcuts_recursive(window)
        except Exception:
            pass

        def _close_window():
            try:
                window.destroy()
            except Exception:
                pass
            self.autonomous_errors_window = None
            self.autonomous_errors_text = None

        window.protocol("WM_DELETE_WINDOW", _close_window)

    def update_autonomous_display(self):
        runtime = getattr(self, "autonomous_runtime", None)

        if not hasattr(self, "autonomous_status_label"):
            return

        if runtime is None:
            try:
                self.autonomous_status_label.config(text=tr("Автономный режим: отключен"))
                self.autonomous_drive_label.config(text=tr("Ведущий драйв: н/д"))
                self.autonomous_limits_label.config(text=tr("тики:0"))
                if hasattr(self, "autonomous_errors_link_label"):
                    self.autonomous_errors_link_label.config(
                        text=tr("ошибки:0"),
                        fg="#7f8c8d",
                        cursor="arrow",
                    )
                self.autonomous_energy_label.config(text="0.00")
                self.autonomous_fatigue_label.config(text="0.00")
                self._update_bar(self.autonomous_energy_bar, 0.0, 0, 1, "#e74c3c", "#27ae60")
                self._update_bar(self.autonomous_fatigue_bar, 0.0, 0, 1, "#27ae60", "#e74c3c")
            except Exception:
                pass
            self._refresh_autonomous_errors_window()
            return

        snapshot = runtime.snapshot()
        tick_count = int(snapshot.get("tick_count", 0))
        failures = list(snapshot.get("failures", []) or [])
        real_errors, _warnings = self._split_autonomous_failures(failures)

        last_tick = runtime.tick_history[-1] if runtime.tick_history else {}
        mode_key = str(last_tick.get("physiology_mode") or "idle")
        mode_text = mode_label(mode_key)
        cognitive_load = float(last_tick.get("cognitive_load", 0.0))
        active_drive = drive_label(last_tick.get("active_drive") or "none")
        cycle_flag = bool(last_tick.get("internal_cycle_triggered", False))
        speech_flag = bool(last_tick.get("speech_event", False))

        drives = dict(snapshot.get("drives", {}) or {})
        top_drive = drive_label("none")
        top_value = 0.0
        if drives:
            top_name, top_value = max(drives.items(), key=lambda item: float(item[1]))
            top_drive = drive_label(top_name)

        energy = dict(snapshot.get("energy", {}) or {})
        energy_level = float(energy.get("energy", 0.0))
        fatigue_level = float(energy.get("fatigue", 0.0))
        suppressed = bool(energy.get("suppress_internal_cycles", False))

        try:
            self.autonomous_status_label.config(
                text=(
                    f"{tr('режим:')}{mode_text} {tr('нагрузка:')}{cognitive_load:.2f} "
                    f"{tr('цикл:')}{int(cycle_flag)} {tr('речь:')}{int(speech_flag)}"
                )
            )
            self.autonomous_drive_label.config(
                text=(
                    f"{tr('ведущий:')}{active_drive} {tr('топ:')}{top_drive}={top_value:.2f} "
                    f"{tr('подавление:')}{int(suppressed)}"
                )
            )
            self.autonomous_limits_label.config(
                text=f"{tr('тики:')}{tick_count}"
            )
            if hasattr(self, "autonomous_errors_link_label"):
                err_count = len(real_errors)
                self.autonomous_errors_link_label.config(
                    text=f"{tr('ошибки:')}{err_count}",
                    fg="#c0392b" if err_count > 0 else "#1f6feb",
                    cursor="hand2",
                )
            self.autonomous_energy_label.config(text=f"{energy_level:.2f}")
            self.autonomous_fatigue_label.config(text=f"{fatigue_level:.2f}")
            self._update_bar(self.autonomous_energy_bar, energy_level, 0, 1, "#e74c3c", "#27ae60")
            self._update_bar(self.autonomous_fatigue_bar, fatigue_level, 0, 1, "#27ae60", "#e74c3c")
        except Exception:
            pass
        self._refresh_autonomous_errors_window()
        
    def _set_title(self, window, key):
        window._i18n_title = key
        window.title(tr(key))

    def _refresh_titles(self):
        for window in (
            self.root,
            getattr(self, "inspector_window", None),
            getattr(self, "autonomous_errors_window", None),
            getattr(self, "load_window", None),
            getattr(self, "dataset_window", None),
            getattr(self, "sleep_window", None),
        ):
            key = getattr(window, "_i18n_title", None) if window is not None else None
            if not key:
                continue
            try:
                if window.winfo_exists():
                    window.title(tr(key))
            except Exception:
                pass

    def _style_lang_buttons(self):
        active = get_language()
        for code, button in getattr(self, "_lang_buttons", {}).items():
            try:
                if code == active:
                    button.configure(bg="#dbeafe", fg="#1e3a5f", relief=tk.SOLID, bd=2, highlightbackground="#2563eb")
                else:
                    button.configure(bg="#34495e", fg="#ecf0f1", relief=tk.FLAT, bd=1, highlightbackground="#2c3e50")
            except Exception:
                pass

    def _localize_widget(self, widget):
        """Retarget labels, buttons, frames, and notebook tabs that use catalog keys."""

        try:
            children = widget.winfo_children()
        except Exception:
            children = ()
        for child in children:
            self._localize_widget(child)
        try:
            import tkinter.ttk as ttk_mod

            if isinstance(widget, ttk_mod.Notebook):
                mapping = getattr(widget, "_i18n_tabs", None)
                if mapping is None:
                    mapping = {}
                    for tab_id in widget.tabs():
                        current = widget.tab(tab_id, "text")
                        if current in PHRASES:
                            mapping[tab_id] = current
                    widget._i18n_tabs = mapping
                for tab_id, key in list(getattr(widget, "_i18n_tabs", {}).items()):
                    try:
                        widget.tab(tab_id, text=tr(key))
                    except Exception:
                        pass
        except Exception:
            pass
        try:
            key = getattr(widget, "_i18n_key", None)
            if key is None:
                current = widget.cget("text")
                if isinstance(current, str) and current in PHRASES:
                    widget._i18n_key = current
                    key = current
            if key:
                widget.configure(text=tr(key))
        except Exception:
            pass

    def _set_ui_language(self, lang):
        set_language(lang)
        self._style_lang_buttons()
        self._refresh_titles()
        self._localize_widget(self.root)
        for window in (
            getattr(self, "autonomous_errors_window", None),
            getattr(self, "load_window", None),
            getattr(self, "dataset_window", None),
            getattr(self, "sleep_window", None),
        ):
            if window is None:
                continue
            try:
                if window.winfo_exists():
                    self._localize_widget(window)
            except Exception:
                pass
        try:
            self._refresh_autonomous_errors_window()
        except Exception:
            pass
        try:
            self.update_affect_display()
            self.update_temporal_display()
            self.update_memory_display()
            self.update_stats(self.last_action or "нет")
            self.update_external_interaction_display()
        except Exception:
            pass
        try:
            if self.inspector_window and self.inspector_window.winfo_exists():
                self.open_inspector()
        except Exception:
            pass

    def setup_ui(self):
        # Title
        title_frame = tk.Frame(self.root, bg="#2c3e50")
        title_frame.pack(fill=tk.X, padx=0, pady=0)

        lang_box = tk.Frame(title_frame, bg="#2c3e50")
        lang_box.pack(side=tk.RIGHT, padx=10, pady=8)
        for code in ("en", "ru"):
            button = tk.Button(
                lang_box,
                text=code.upper(),
                command=lambda selected=code: self._set_ui_language(selected),
                font=("Helvetica", 9, "bold"),
                width=3,
                padx=4,
                pady=1,
            )
            button.pack(side=tk.LEFT, padx=2)
            self._lang_buttons[code] = button
        self._style_lang_buttons()
        
        title_label = tk.Label(
            title_frame, 
            text="🤖 NOWA - Neural Memory Agent",
            font=("Helvetica", 16, "bold"),
            bg="#2c3e50",
            fg="#ecf0f1"
        )
        title_label.pack(pady=10)
        
        # Main container with resizable panels
        main_frame = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Left panel - Chat (80% width, expandable)
        left_panel = tk.Frame(main_frame)
        main_frame.add(left_panel, weight=8)  # 80% of available space
        
        chat_label = tk.Label(left_panel, text="Диалог:", font=("Helvetica", 12, "bold"))
        chat_label.pack(anchor=tk.W)
        
        self.chat_display = scrolledtext.ScrolledText(
            left_panel,
            height=25,
            width=50,
            wrap=tk.WORD,
            state=tk.DISABLED
        )
        self.chat_display.pack(fill=tk.BOTH, expand=True, pady=5)
        # Enable clipboard shortcuts on main chat display and attach context menu
        try:
            self._bind_clipboard_shortcuts(self.chat_display)
            self.chat_display.bind("<Button-3>", lambda e: self._show_context_menu(e, self.chat_display))
        except Exception:
            pass
        
        # Input frame
        input_frame = tk.Frame(left_panel)
        input_frame.pack(fill=tk.X, pady=5)
        
        tk.Label(input_frame, text="Ввод:", font=("Helvetica", 10, "bold")).pack(anchor=tk.W)
        
        self.input_field = tk.Entry(input_frame, font=("Helvetica", 10))
        self.input_field.pack(fill=tk.X, pady=5)
        self.input_field.bind("<Return>", lambda e: self.send_message())
        # Enable clipboard shortcuts on input field and attach context menu
        try:
            self._bind_clipboard_shortcuts(self.input_field)
            self.input_field.bind("<Button-3>", lambda e: self._show_context_menu(e, self.input_field))
        except Exception:
            pass
        
        # Buttons frame
        button_frame = tk.Frame(left_panel)
        button_frame.pack(fill=tk.X, pady=5)
        
        send_btn = tk.Button(
            button_frame,
            text="Отправить",
            command=self.send_message,
            bg="#27ae60",
            fg="white",
            font=("Helvetica", 10, "bold")
        )
        send_btn.pack(side=tk.LEFT, padx=2)
        
        clear_btn = tk.Button(
            button_frame,
            text="Очистить",
            command=self.clear_chat,
            bg="#e74c3c",
            fg="white",
            font=("Helvetica", 10, "bold")
        )
        clear_btn.pack(side=tk.LEFT, padx=2)
        # Controls container: left rectangle for storage/debug, right rectangle for ratings
        controls_container = tk.Frame(left_panel)
        controls_container.pack(fill=tk.X, pady=5)

        left_box = tk.LabelFrame(controls_container, text="Действия", padx=6, pady=6)
        left_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0,5))

        right_box = tk.LabelFrame(controls_container, text="Оценка ответа", padx=6, pady=6)
        right_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5,0))

        # Storage/buttons go into left_box
        storage_frame = tk.Frame(left_box)
        storage_frame.pack(fill=tk.X)
        
        save_btn = tk.Button(
            storage_frame,
            text="Сохранить",
            command=self.save_state,
            bg="#3498db",
            fg="white",
            font=("Helvetica", 9, "bold")
        )
        save_btn.pack(side=tk.LEFT, padx=2)
        
        load_btn = tk.Button(
            storage_frame,
            text="Загрузить",
            command=self.load_state,
            bg="#9b59b6",
            fg="white",
            font=("Helvetica", 9, "bold")
        )
        load_btn.pack(side=tk.LEFT, padx=2)
        
        save_chat_btn = tk.Button(
            storage_frame,
            text="Сохранить диалог",
            command=self.save_chat,
            bg="#16a085",
            fg="white",
            font=("Helvetica", 9, "bold")
        )
        save_chat_btn.pack(side=tk.LEFT, padx=2)
        
        load_dataset_btn = tk.Button(
            storage_frame,
            text="Загрузить датасет",
            command=self.load_dataset_dialog,
            bg="#c0392b",
            fg="white",
            font=("Helvetica", 9, "bold")
        )
        load_dataset_btn.pack(side=tk.LEFT, padx=2)
        
        # Debug button
        debug_btn = tk.Button(
            storage_frame,
            text="Инспектор",
            command=self.open_inspector,
            bg="#e67e22",
            fg="white",
            font=("Helvetica", 9, "bold")
        )
        debug_btn.pack(side=tk.LEFT, padx=2)

        # Rating controls go into right_box (visual rectangle on the right)
        self.feedback_var = tk.IntVar(value=0)
        feedback_buttons_frame = tk.Frame(right_box)
        feedback_buttons_frame.pack(fill=tk.X)
        for i, label in enumerate(["😞", "😐", "🙂", "😊", "😍"], 1):
            rb = tk.Radiobutton(
                feedback_buttons_frame,
                text=label,
                variable=self.feedback_var,
                value=i-3,
                font=("Helvetica", 12)
            )
            rb.pack(side=tk.LEFT, padx=6)
        feedback_send_btn = tk.Button(
            right_box,
            text="Отправить оценку",
            command=self.submit_feedback,
            bg="#3498db",
            fg="white",
            font=("Helvetica", 9, "bold")
        )
        feedback_send_btn.pack(fill=tk.X, pady=(6,0))

        # External interaction controls
        external_box = tk.LabelFrame(
            left_panel,
            text="Слой внешнего взаимодействия",
            padx=6,
            pady=6,
        )
        external_box.pack(fill=tk.X, pady=(6, 4))

        obs_row = tk.Frame(external_box)
        obs_row.pack(fill=tk.X, pady=2)
        tk.Label(obs_row, text="источник:", font=("Helvetica", 8)).pack(side=tk.LEFT)
        self.external_obs_source_var = tk.StringVar(value="gui_manual")
        tk.Entry(obs_row, textvariable=self.external_obs_source_var, width=12, font=("Courier", 8)).pack(side=tk.LEFT, padx=4)
        tk.Label(obs_row, text="неопр.:", font=("Helvetica", 8)).pack(side=tk.LEFT, padx=(6, 0))
        self.external_obs_uncertainty_var = tk.StringVar(value="0.2")
        tk.Entry(obs_row, textvariable=self.external_obs_uncertainty_var, width=5, font=("Courier", 8)).pack(side=tk.LEFT, padx=4)
        tk.Label(obs_row, text="данные JSON:", font=("Helvetica", 8)).pack(side=tk.LEFT, padx=(6, 0))
        self.external_obs_payload_var = tk.StringVar(value='{"event":"manual"}')
        tk.Entry(obs_row, textvariable=self.external_obs_payload_var, font=("Courier", 8)).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

        obs_btn_row = tk.Frame(external_box)
        obs_btn_row.pack(fill=tk.X, pady=(2, 4))
        tk.Button(
            obs_btn_row,
            text="Добавить наблюдение",
            command=self.add_external_observation_from_ui,
            bg="#1abc9c",
            fg="white",
            font=("Helvetica", 8, "bold"),
        ).pack(side=tk.LEFT, padx=2)
        tk.Button(
            obs_btn_row,
            text="Опрос среды",
            command=self.poll_external_observation_from_ui,
            bg="#16a085",
            fg="white",
            font=("Helvetica", 8, "bold"),
        ).pack(side=tk.LEFT, padx=2)

        action_row = tk.Frame(external_box)
        action_row.pack(fill=tk.X, pady=2)
        tk.Label(action_row, text="действие:", font=("Helvetica", 8)).pack(side=tk.LEFT)
        self.external_action_type_var = tk.StringVar(value="explore")
        tk.Entry(action_row, textvariable=self.external_action_type_var, width=12, font=("Courier", 8)).pack(side=tk.LEFT, padx=4)
        tk.Label(action_row, text="приор:", font=("Helvetica", 8)).pack(side=tk.LEFT, padx=(6, 0))
        self.external_expected_prior_var = tk.StringVar(value="0.5")
        tk.Entry(action_row, textvariable=self.external_expected_prior_var, width=5, font=("Courier", 8)).pack(side=tk.LEFT, padx=4)
        tk.Label(action_row, text="задержка:", font=("Helvetica", 8)).pack(side=tk.LEFT, padx=(6, 0))
        self.external_delay_steps_var = tk.IntVar(value=0)
        tk.Spinbox(action_row, from_=0, to=999, textvariable=self.external_delay_steps_var, width=5, font=("Courier", 8)).pack(side=tk.LEFT, padx=4)
        tk.Label(action_row, text="прогноз:", font=("Helvetica", 8)).pack(side=tk.LEFT, padx=(6, 0))
        self.external_predicted_reward_var = tk.StringVar(value="0.0")
        tk.Entry(action_row, textvariable=self.external_predicted_reward_var, width=6, font=("Courier", 8)).pack(side=tk.LEFT, padx=4)

        action_params_row = tk.Frame(external_box)
        action_params_row.pack(fill=tk.X, pady=2)
        tk.Label(action_params_row, text="параметры JSON:", font=("Helvetica", 8)).pack(side=tk.LEFT)
        self.external_action_params_var = tk.StringVar(value='{"reward":0.0}')
        tk.Entry(action_params_row, textvariable=self.external_action_params_var, font=("Courier", 8)).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

        action_btn_row = tk.Frame(external_box)
        action_btn_row.pack(fill=tk.X, pady=(2, 4))
        tk.Button(
            action_btn_row,
            text="Выполнить действие",
            command=self.execute_external_action_from_ui,
            bg="#2980b9",
            fg="white",
            font=("Helvetica", 8, "bold"),
        ).pack(side=tk.LEFT, padx=2)
        tk.Button(
            action_btn_row,
            text="Обработать отложенные",
            command=self.resolve_external_feedback_from_ui,
            bg="#8e44ad",
            fg="white",
            font=("Helvetica", 8, "bold"),
        ).pack(side=tk.LEFT, padx=2)
        tk.Button(
            action_btn_row,
            text="Обновить статус",
            command=self.update_external_interaction_display,
            bg="#7f8c8d",
            fg="white",
            font=("Helvetica", 8, "bold"),
        ).pack(side=tk.LEFT, padx=2)

        self.external_status_label = tk.Label(
            external_box,
            text="набл:0 | ожидание:0 | шаг:0 | стратегии:0",
            font=("Courier", 8),
            fg="#2c3e50",
            anchor=tk.W,
            justify=tk.LEFT,
        )
        self.external_status_label.pack(fill=tk.X, pady=(2, 0))
        self.external_last_feedback_label = tk.Label(
            external_box,
            text="обратная связь: н/д",
            font=("Courier", 8),
            fg="#555",
            anchor=tk.W,
            justify=tk.LEFT,
        )
        self.external_last_feedback_label.pack(fill=tk.X, pady=(0, 2))
        
        # Right panel - Affective State, Stats and Feedback (scrollable, narrow right-aligned, 20% width)
        right_scroll_frame = tk.Frame(main_frame)
        main_frame.add(right_scroll_frame, weight=2)  # 20% of space, sticks to right
        
        right_scrollbar = tk.Scrollbar(right_scroll_frame)
        right_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        right_canvas = tk.Canvas(right_scroll_frame, bg="#ecf0f1", highlightthickness=0, width=250)
        right_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        right_scrollbar.config(command=right_canvas.yview)
        right_canvas.config(yscrollcommand=right_scrollbar.set)
        
        right_panel = tk.Frame(right_canvas, bg="#ecf0f1")
        right_canvas.create_window(0, 0, window=right_panel, anchor=tk.NW)
        
        # Bind mousewheel to canvas scroll only when pointer is over the right canvas
        def _on_mousewheel(event):
            right_canvas.yview_scroll(int(-1*(event.delta/120)), "units")

        def _bind_right_canvas_scroll(e):
            right_canvas.bind_all("<MouseWheel>", _on_mousewheel)

        def _unbind_right_canvas_scroll(e):
            try:
                right_canvas.unbind_all("<MouseWheel>")
            except Exception:
                pass

        right_canvas.bind("<Enter>", _bind_right_canvas_scroll)
        right_canvas.bind("<Leave>", _unbind_right_canvas_scroll)
        
        # ===== AFFECTIVE STATE SECTION =====
        affect_label = tk.Label(
            right_panel, 
            text="❤️ Аффективное состояние", 
            font=("Helvetica", 11, "bold"), 
            bg="#ecf0f1",
            fg="#c0392b"
        )
        affect_label.pack(anchor=tk.W, padx=10, pady=(10, 5))
        
        # Affective state frame with background
        affect_frame = tk.Frame(right_panel, bg="#fff5f5", relief=tk.SUNKEN, bd=1)
        affect_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Valence indicator
        tk.Label(affect_frame, text="Валентность:", font=("Helvetica", 9, "bold"), bg="#fff5f5").pack(anchor=tk.W, padx=5, pady=(5, 2))
        self.valence_bar = tk.Canvas(affect_frame, height=20, bg="#f5f5f5", highlightthickness=0)
        self.valence_bar.pack(fill=tk.X, padx=5, pady=2)
        self.valence_label = tk.Label(affect_frame, text="0.00", font=("Courier", 8), bg="#fff5f5", fg="#666")
        self.valence_label.pack(anchor=tk.W, padx=5, pady=0)
        
        # Arousal indicator
        tk.Label(affect_frame, text="Активация:", font=("Helvetica", 9, "bold"), bg="#fff5f5").pack(anchor=tk.W, padx=5, pady=(5, 2))
        self.arousal_bar = tk.Canvas(affect_frame, height=20, bg="#f5f5f5", highlightthickness=0)
        self.arousal_bar.pack(fill=tk.X, padx=5, pady=2)
        self.arousal_label = tk.Label(affect_frame, text="0.00", font=("Courier", 8), bg="#fff5f5", fg="#666")
        self.arousal_label.pack(anchor=tk.W, padx=5, pady=0)
        
        # Threat indicator
        tk.Label(affect_frame, text="Угроза:", font=("Helvetica", 9, "bold"), bg="#fff5f5").pack(anchor=tk.W, padx=5, pady=(5, 2))
        self.threat_bar = tk.Canvas(affect_frame, height=20, bg="#f5f5f5", highlightthickness=0)
        self.threat_bar.pack(fill=tk.X, padx=5, pady=2)
        self.threat_label = tk.Label(affect_frame, text="0.00", font=("Courier", 8), bg="#fff5f5", fg="#666")
        self.threat_label.pack(anchor=tk.W, padx=5, pady=0)
        
        # Curiosity indicator
        tk.Label(affect_frame, text="Любопытство:", font=("Helvetica", 9, "bold"), bg="#fff5f5").pack(anchor=tk.W, padx=5, pady=(5, 2))
        self.curiosity_bar = tk.Canvas(affect_frame, height=20, bg="#f5f5f5", highlightthickness=0)
        self.curiosity_bar.pack(fill=tk.X, padx=5, pady=2)
        self.curiosity_label = tk.Label(affect_frame, text="0.00", font=("Courier", 8), bg="#fff5f5", fg="#666")
        self.curiosity_label.pack(anchor=tk.W, padx=5, pady=0)

        # Affective background (Phase 3.75)
        tk.Label(affect_frame, text="Аффективный фон:", font=("Helvetica", 9, "bold"), bg="#fff5f5").pack(anchor=tk.W, padx=5, pady=(8, 2))
        bg_frame = tk.Frame(affect_frame, bg="#f6fbff", relief=tk.FLAT, bd=0)
        bg_frame.pack(fill=tk.X, padx=5, pady=(0, 5))

        tk.Label(bg_frame, text="Тревога:", font=("Helvetica", 8, "bold"), bg="#f6fbff").pack(anchor=tk.W, padx=5, pady=(4, 2))
        self.bg_anxiety_bar = tk.Canvas(bg_frame, height=16, bg="#f5f5f5", highlightthickness=0)
        self.bg_anxiety_bar.pack(fill=tk.X, padx=5, pady=1)
        self.bg_anxiety_label = tk.Label(bg_frame, text="0.00", font=("Courier", 8), bg="#f6fbff", fg="#666")
        self.bg_anxiety_label.pack(anchor=tk.W, padx=5, pady=0)

        tk.Label(bg_frame, text="Напряжение:", font=("Helvetica", 8, "bold"), bg="#f6fbff").pack(anchor=tk.W, padx=5, pady=(4, 2))
        self.bg_tension_bar = tk.Canvas(bg_frame, height=16, bg="#f5f5f5", highlightthickness=0)
        self.bg_tension_bar.pack(fill=tk.X, padx=5, pady=1)
        self.bg_tension_label = tk.Label(bg_frame, text="0.00", font=("Courier", 8), bg="#f6fbff", fg="#666")
        self.bg_tension_label.pack(anchor=tk.W, padx=5, pady=0)

        tk.Label(bg_frame, text="Удовлетворение:", font=("Helvetica", 8, "bold"), bg="#f6fbff").pack(anchor=tk.W, padx=5, pady=(4, 2))
        self.bg_satisfaction_bar = tk.Canvas(bg_frame, height=16, bg="#f5f5f5", highlightthickness=0)
        self.bg_satisfaction_bar.pack(fill=tk.X, padx=5, pady=1)
        self.bg_satisfaction_label = tk.Label(bg_frame, text="0.00", font=("Courier", 8), bg="#f6fbff", fg="#666")
        self.bg_satisfaction_label.pack(anchor=tk.W, padx=5, pady=0)

        tk.Label(bg_frame, text="Интерес:", font=("Helvetica", 8, "bold"), bg="#f6fbff").pack(anchor=tk.W, padx=5, pady=(4, 2))
        self.bg_interest_bar = tk.Canvas(bg_frame, height=16, bg="#f5f5f5", highlightthickness=0)
        self.bg_interest_bar.pack(fill=tk.X, padx=5, pady=1)
        self.bg_interest_label = tk.Label(bg_frame, text="0.00", font=("Courier", 8), bg="#f6fbff", fg="#666")
        self.bg_interest_label.pack(anchor=tk.W, padx=5, pady=(0, 4))

        # Affective space (Phase 4 pre)
        tk.Label(affect_frame, text="Аффективное пространство:", font=("Helvetica", 9, "bold"), bg="#fff5f5").pack(anchor=tk.W, padx=5, pady=(6, 2))
        space_frame = tk.Frame(affect_frame, bg="#fdfaf1", relief=tk.FLAT, bd=0)
        space_frame.pack(fill=tk.X, padx=5, pady=(0, 5))

        self.affective_space_bars = {}
        self.affective_space_value_labels = {}
        self.affective_space_colors = {
            "valence": "#27ae60",
            "arousal": "#f39c12",
            "dominance": "#16a085",
            "stress": "#e74c3c",
            "trust": "#3498db",
            "curiosity": "#9b59b6",
            "stability": "#2ecc71",
            "attachment": "#8e44ad",
        }
        self.affective_space_legacy_bars = {}
        self.affective_space_legacy_labels = {}

        space_axes = [
            ("valence", "Валентность"),
            ("arousal", "Возбуждение"),
            ("dominance", "Доминирование"),
            ("stress", "Стресс"),
            ("trust", "Доверие"),
            ("curiosity", "Любопытство"),
            ("stability", "Стабильность"),
            ("attachment", "Привязанность"),
        ]

        for axis, label in space_axes:
            tk.Label(space_frame, text=f"{label}:", font=("Helvetica", 8, "bold"), bg="#fdfaf1").pack(anchor=tk.W, padx=5, pady=(4, 2))
            bar = tk.Canvas(space_frame, height=14, bg="#f5f5f5", highlightthickness=0)
            bar.pack(fill=tk.X, padx=5, pady=1)
            value_label = tk.Label(space_frame, text="0.00", font=("Courier", 8), bg="#fdfaf1", fg="#666")
            value_label.pack(anchor=tk.W, padx=5, pady=0)
            self.affective_space_bars[axis] = bar
            self.affective_space_value_labels[axis] = value_label

        tk.Label(space_frame, text="Legacy overlay:", font=("Helvetica", 8, "italic"), bg="#fdfaf1", fg="#7f8c8d").pack(anchor=tk.W, padx=5, pady=(6, 2))
        for axis, label in (("pleasure", "Удовольствие"), ("pain", "Боль"), ("relaxation", "Расслабление"), ("focus", "Фокус")):
            tk.Label(space_frame, text=f"{label}:", font=("Helvetica", 7), bg="#fdfaf1", fg="#7f8c8d").pack(anchor=tk.W, padx=5, pady=(2, 0))
            bar = tk.Canvas(space_frame, height=10, bg="#f5f5f5", highlightthickness=0)
            bar.pack(fill=tk.X, padx=5, pady=1)
            value_label = tk.Label(space_frame, text="0.00", font=("Courier", 7), bg="#fdfaf1", fg="#999")
            value_label.pack(anchor=tk.W, padx=5, pady=0)
            self.affective_space_legacy_bars[axis] = bar
            self.affective_space_legacy_labels[axis] = value_label

        self.decision_bias_label = tk.Label(space_frame, text="bias: —", font=("Courier", 8), bg="#fdfaf1", fg="#2c3e50", wraplength=220, justify=tk.LEFT, anchor=tk.W)
        self.decision_bias_label.pack(anchor=tk.W, padx=5, pady=(4, 0))

        space_metrics = tk.Frame(space_frame, bg="#fdfaf1")
        space_metrics.pack(fill=tk.X, padx=5, pady=(4, 2))
        self.affective_space_speed_label = tk.Label(space_metrics, text="V: 0.00", font=("Courier", 8), bg="#fdfaf1", fg="#2c3e50")
        self.affective_space_speed_label.pack(anchor=tk.W)
        self.affective_space_conflict_label = tk.Label(space_metrics, text="Conflict: 0.00", font=("Courier", 8), bg="#fdfaf1", fg="#2c3e50")
        self.affective_space_conflict_label.pack(anchor=tk.W)

        # Semantic emotions (Phase 4.1)
        tk.Label(affect_frame, text="Semantic Emotions:", font=("Helvetica", 9, "bold"), bg="#fff5f5").pack(anchor=tk.W, padx=5, pady=(6, 2))
        sem_frame = tk.Frame(affect_frame, bg="#fff5f5")
        sem_frame.pack(fill=tk.X, padx=5, pady=(0, 5))
        self.semantic_emotions_summary_label = tk.Label(
            sem_frame,
            text="(none)",
            font=("Helvetica", 9, "italic"),
            bg="#fff5f5",
            fg="#2c3e50",
            wraplength=220,
            justify=tk.LEFT,
            anchor=tk.W
        )
        self.semantic_emotions_summary_label.pack(anchor=tk.W, pady=(0, 2))

        self.semantic_emotions_label = tk.Label(
            sem_frame,
            text="",
            font=("Courier", 7),
            bg="#fff5f5",
            fg="#2c3e50",
            justify=tk.LEFT,
            anchor=tk.W
        )
        self.semantic_emotions_label.pack(anchor=tk.W)

        # Emotional memory narratives (Phase 4.2)
        tk.Label(affect_frame, text="Эмоциональная память:", font=("Helvetica", 9, "bold"), bg="#fff5f5").pack(anchor=tk.W, padx=5, pady=(6, 2))
        mem_frame = tk.Frame(affect_frame, bg="#fff5f5")
        mem_frame.pack(fill=tk.X, padx=5, pady=(0, 5))
        self.emotional_memory_summary_label = tk.Label(
            mem_frame,
            text="(none)",
            font=("Helvetica", 9, "italic"),
            bg="#fff5f5",
            fg="#2c3e50",
            wraplength=220,
            justify=tk.LEFT,
            anchor=tk.W
        )
        self.emotional_memory_summary_label.pack(anchor=tk.W, pady=(0, 2))
        self.emotional_memory_metrics_label = tk.Label(
            mem_frame,
            text="",
            font=("Courier", 7),
            bg="#fff5f5",
            fg="#2c3e50",
            justify=tk.LEFT,
            anchor=tk.W
        )
        self.emotional_memory_metrics_label.pack(anchor=tk.W)

        # Emotional expectations (Phase 4.3)
        tk.Label(affect_frame, text="Эмоциональные ожидания:", font=("Helvetica", 9, "bold"), bg="#fff5f5").pack(anchor=tk.W, padx=5, pady=(6, 2))
        exp_frame = tk.Frame(affect_frame, bg="#fff5f5")
        exp_frame.pack(fill=tk.X, padx=5, pady=(0, 5))
        self.emotional_expectations_summary_label = tk.Label(
            exp_frame,
            text="(none)",
            font=("Helvetica", 9, "italic"),
            bg="#fff5f5",
            fg="#2c3e50",
            wraplength=220,
            justify=tk.LEFT,
            anchor=tk.W
        )
        self.emotional_expectations_summary_label.pack(anchor=tk.W, pady=(0, 2))
        self.emotional_expectations_metrics_label = tk.Label(
            exp_frame,
            text="",
            font=("Courier", 7),
            bg="#fff5f5",
            fg="#2c3e50",
            justify=tk.LEFT,
            anchor=tk.W
        )
        self.emotional_expectations_metrics_label.pack(anchor=tk.W)

        # Emotional regulation (Phase 4.4)
        tk.Label(affect_frame, text="Регуляция ожиданий:", font=("Helvetica", 9, "bold"), bg="#fff5f5").pack(anchor=tk.W, padx=5, pady=(6, 2))
        reg_frame = tk.Frame(affect_frame, bg="#fff5f5")
        reg_frame.pack(fill=tk.X, padx=5, pady=(0, 5))
        self.emotional_regulation_summary_label = tk.Label(
            reg_frame,
            text="(none)",
            font=("Helvetica", 9, "italic"),
            bg="#fff5f5",
            fg="#2c3e50",
            wraplength=220,
            justify=tk.LEFT,
            anchor=tk.W
        )
        self.emotional_regulation_summary_label.pack(anchor=tk.W, pady=(0, 2))
        self.emotional_regulation_metrics_label = tk.Label(
            reg_frame,
            text="",
            font=("Courier", 7),
            bg="#fff5f5",
            fg="#2c3e50",
            justify=tk.LEFT,
            anchor=tk.W
        )
        self.emotional_regulation_metrics_label.pack(anchor=tk.W)

        # Stability monitoring (Phase 4.5)
        tk.Label(affect_frame, text="Мониторинг устойчивости:", font=("Helvetica", 9, "bold"), bg="#fff5f5").pack(anchor=tk.W, padx=5, pady=(6, 2))
        stability_frame = tk.Frame(affect_frame, bg="#fff5f5")
        stability_frame.pack(fill=tk.X, padx=5, pady=(0, 5))
        self.stability_monitor_summary_label = tk.Label(
            stability_frame,
            text="(none)",
            font=("Helvetica", 9, "italic"),
            bg="#fff5f5",
            fg="#2c3e50",
            wraplength=220,
            justify=tk.LEFT,
            anchor=tk.W
        )
        self.stability_monitor_summary_label.pack(anchor=tk.W, pady=(0, 2))
        self.stability_monitor_metrics_label = tk.Label(
            stability_frame,
            text="",
            font=("Courier", 7),
            bg="#fff5f5",
            fg="#2c3e50",
            justify=tk.LEFT,
            anchor=tk.W
        )
        self.stability_monitor_metrics_label.pack(anchor=tk.W)

        # Value layer (Phase 5.0)
        tk.Label(affect_frame, text="Слой ценности (TD):", font=("Helvetica", 9, "bold"), bg="#fff5f5").pack(anchor=tk.W, padx=5, pady=(6, 2))
        value_frame = tk.Frame(affect_frame, bg="#fff5f5")
        value_frame.pack(fill=tk.X, padx=5, pady=(0, 5))
        self.value_layer_summary_label = tk.Label(
            value_frame,
            text="Данных пока нет",
            font=("Helvetica", 9, "italic"),
            bg="#fff5f5",
            fg="#2c3e50",
            wraplength=220,
            justify=tk.LEFT,
            anchor=tk.W
        )
        self.value_layer_summary_label.pack(anchor=tk.W, pady=(0, 2))
        self.value_layer_metrics_label = tk.Label(
            value_frame,
            text="",
            font=("Courier", 7),
            bg="#fff5f5",
            fg="#2c3e50",
            justify=tk.LEFT,
            anchor=tk.W
        )
        self.value_layer_metrics_label.pack(anchor=tk.W)
        
        # Neuromodulators diagnostic (minimal)
        tk.Label(affect_frame, text="Нейромодуляторы:", font=("Helvetica", 9, "bold"), bg="#fff5f5").pack(anchor=tk.W, padx=5, pady=(8, 2))
        nm_frame = tk.Frame(affect_frame, bg="#fff5f5")
        nm_frame.pack(fill=tk.X, padx=5, pady=(0, 5))

        self.da_label = tk.Label(nm_frame, text="DA: 0.00", font=("Courier", 8), bg="#fff5f5", fg="#2c3e50")
        self.da_label.pack(anchor=tk.W)
        self.ne_label = tk.Label(nm_frame, text="NE: 0.00", font=("Courier", 8), bg="#fff5f5", fg="#2c3e50")
        self.ne_label.pack(anchor=tk.W)
        self.ser_label = tk.Label(nm_frame, text="5-HT: 0.00", font=("Courier", 8), bg="#fff5f5", fg="#2c3e50")
        self.ser_label.pack(anchor=tk.W)
        self.cort_label = tk.Label(nm_frame, text="CORT: 0.00", font=("Courier", 8), bg="#fff5f5", fg="#2c3e50")
        self.cort_label.pack(anchor=tk.W)
        self.ach_label = tk.Label(nm_frame, text="ACh: 0.00", font=("Courier", 8), bg="#fff5f5", fg="#2c3e50")
        self.ach_label.pack(anchor=tk.W)
        
        # Readiness indicator
        readiness_frame = tk.Frame(affect_frame, bg="#fff5f5")
        readiness_frame.pack(fill=tk.X, padx=5, pady=(8, 5))
        tk.Label(readiness_frame, text="Готовность:", font=("Helvetica", 9, "bold"), bg="#fff5f5").pack(anchor=tk.W)
        self.readiness_label = tk.Label(readiness_frame, text="Не рассчитана", font=("Helvetica", 9, "italic"), bg="#fff5f5", fg="#27ae60")
        self.readiness_label.pack(anchor=tk.W)

        # Autonomous organism runtime section (Spec v1)
        auto_label = tk.Label(
            right_panel,
            text="Автономный организм",
            font=("Helvetica", 11, "bold"),
            bg="#ecf0f1",
            fg="#1f7a4c",
        )
        auto_label.pack(anchor=tk.W, padx=10, pady=(10, 5))

        auto_frame = tk.Frame(right_panel, bg="#eefaf2", relief=tk.SUNKEN, bd=1)
        auto_frame.pack(fill=tk.X, padx=10, pady=5)

        self.autonomous_status_label = tk.Label(
            auto_frame,
            text="Режим: инициализация",
            font=("Courier", 8),
            bg="#eefaf2",
            fg="#2c3e50",
            justify=tk.LEFT,
            anchor=tk.W,
        )
        self.autonomous_status_label.pack(anchor=tk.W, padx=5, pady=(5, 2))
        self.autonomous_drive_label = tk.Label(
            auto_frame,
            text="Ведущий драйв: н/д",
            font=("Courier", 8),
            bg="#eefaf2",
            fg="#2c3e50",
            justify=tk.LEFT,
            anchor=tk.W,
        )
        self.autonomous_drive_label.pack(anchor=tk.W, padx=5, pady=0)
        autonomous_limits_row = tk.Frame(auto_frame, bg="#eefaf2")
        autonomous_limits_row.pack(fill=tk.X, padx=5, pady=(0, 4))
        self.autonomous_limits_label = tk.Label(
            autonomous_limits_row,
            text="тики:0",
            font=("Courier", 8),
            bg="#eefaf2",
            fg="#2c3e50",
            justify=tk.LEFT,
            anchor=tk.W,
        )
        self.autonomous_limits_label.pack(side=tk.LEFT)
        self.autonomous_errors_link_label = tk.Label(
            autonomous_limits_row,
            text="ошибки:0",
            font=("Courier", 8, "underline"),
            bg="#eefaf2",
            fg="#1f6feb",
            justify=tk.LEFT,
            anchor=tk.W,
            cursor="hand2",
        )
        self.autonomous_errors_link_label.pack(side=tk.LEFT, padx=(10, 0))
        self.autonomous_errors_link_label.bind("<Button-1>", self._open_autonomous_errors_window)

        tk.Label(auto_frame, text="Энергия (автономная):", font=("Helvetica", 8, "bold"), bg="#eefaf2").pack(anchor=tk.W, padx=5, pady=(2, 1))
        self.autonomous_energy_bar = tk.Canvas(auto_frame, height=14, bg="#f5f5f5", highlightthickness=0)
        self.autonomous_energy_bar.pack(fill=tk.X, padx=5, pady=1)
        self.autonomous_energy_label = tk.Label(auto_frame, text="0.00", font=("Courier", 8), bg="#eefaf2", fg="#2c3e50")
        self.autonomous_energy_label.pack(anchor=tk.W, padx=5, pady=0)

        tk.Label(auto_frame, text="Энергетическая усталость (автономная):", font=("Helvetica", 8, "bold"), bg="#eefaf2").pack(anchor=tk.W, padx=5, pady=(2, 1))
        self.autonomous_fatigue_bar = tk.Canvas(auto_frame, height=14, bg="#f5f5f5", highlightthickness=0)
        self.autonomous_fatigue_bar.pack(fill=tk.X, padx=5, pady=1)
        self.autonomous_fatigue_label = tk.Label(auto_frame, text="0.00", font=("Courier", 8), bg="#eefaf2", fg="#2c3e50")
        self.autonomous_fatigue_label.pack(anchor=tk.W, padx=5, pady=0)

        self.autonomous_note_label = tk.Label(
            auto_frame,
            text="Физиологическая усталость — в блоке бодрствования",
            font=("Helvetica", 8, "italic"),
            bg="#eefaf2",
            fg="#4e6e5c",
        )
        self.autonomous_note_label.pack(anchor=tk.W, padx=5, pady=(2, 4))

        auto_mode_frame = tk.Frame(auto_frame, bg="#eefaf2")
        auto_mode_frame.pack(fill=tk.X, padx=5, pady=(2, 5))
        tk.Label(
            auto_mode_frame,
            text="Авторежим: 1 тик = 1 секунда (реальное время)",
            font=("Helvetica", 8, "italic"),
            bg="#eefaf2",
            fg="#1d6f42",
        ).pack(anchor=tk.W)
        
        # ===== WAKEFULNESS STATE SECTION =====
        wakefulness_label = tk.Label(
            right_panel,
            text="😴 Состояние бодрствования",
            font=("Helvetica", 11, "bold"),
            bg="#ecf0f1",
            fg="#8e44ad"
        )
        wakefulness_label.pack(anchor=tk.W, padx=10, pady=(10, 5))

        # Wakefulness frame
        wakefulness_frame = tk.Frame(right_panel, bg="#f9f0ff", relief=tk.SUNKEN, bd=1)
        wakefulness_frame.pack(fill=tk.X, padx=10, pady=5)

        # Wakefulness level indicator
        tk.Label(wakefulness_frame, text="Физиологическая усталость:", font=("Helvetica", 9, "bold"), bg="#f9f0ff").pack(anchor=tk.W, padx=5, pady=(5, 2))
        self.wakefulness_bar = tk.Canvas(wakefulness_frame, height=20, bg="#f5f5f5", highlightthickness=0)
        self.wakefulness_bar.pack(fill=tk.X, padx=5, pady=2)
        self.wakefulness_label = tk.Label(wakefulness_frame, text="0.00 (Полностью выспавшийся)", font=("Courier", 8), bg="#f9f0ff", fg="#666")
        self.wakefulness_label.pack(anchor=tk.W, padx=5, pady=0)

        # Cognitive reliability indicator
        tk.Label(wakefulness_frame, text="Когнитивная надежность:", font=("Helvetica", 9, "bold"), bg="#f9f0ff").pack(anchor=tk.W, padx=5, pady=(5, 2))
        self.reliability_bar = tk.Canvas(wakefulness_frame, height=20, bg="#f5f5f5", highlightthickness=0)
        self.reliability_bar.pack(fill=tk.X, padx=5, pady=2)
        self.reliability_label = tk.Label(wakefulness_frame, text="1.00 (Полностью надежен)", font=("Courier", 8), bg="#f9f0ff", fg="#27ae60")
        self.reliability_label.pack(anchor=tk.W, padx=5, pady=0)

        # Time stats
        time_stats_frame = tk.Frame(wakefulness_frame, bg="#f9f0ff")
        time_stats_frame.pack(fill=tk.X, padx=5, pady=(8, 5))
        tk.Label(time_stats_frame, text="Статистика времени:", font=("Helvetica", 8, "bold"), bg="#f9f0ff").pack(anchor=tk.W)
        self.wakefulness_stats = tk.Label(time_stats_frame, text="Бодрствова: 0.0ч | Спал: 0.0ч", font=("Courier", 8), bg="#f9f0ff", fg="#555")
        self.wakefulness_stats.pack(anchor=tk.W, padx=5, pady=2)

        # Sleep control buttons
        sleep_ctrl_frame = tk.Frame(wakefulness_frame, bg="#f9f0ff")
        sleep_ctrl_frame.pack(fill=tk.X, padx=5, pady=(5, 5))
        
        tk.Button(
            sleep_ctrl_frame,
            text="💤 Быстрый сон (30м)",
            command=lambda: self.open_sleep_dialog(default_cycles=1),
            bg="#8e44ad",
            fg="white",
            font=("Helvetica", 8, "bold")
        ).pack(side=tk.LEFT, padx=2)
        
        tk.Button(
            sleep_ctrl_frame,
            text="😴 Обычный сон (1ч)",
            command=lambda: self.open_sleep_dialog(default_cycles=2),
            bg="#8e44ad",
            fg="white",
            font=("Helvetica", 8, "bold")
        ).pack(side=tk.LEFT, padx=2)
        
        tk.Button(
            sleep_ctrl_frame,
            text="😪 Долгий сон (3ч)",
            command=lambda: self.open_sleep_dialog(default_cycles=6),
            bg="#8e44ad",
            fg="white",
            font=("Helvetica", 8, "bold")
        ).pack(side=tk.LEFT, padx=2)
        
        # ===== TEMPORAL LEVELS SECTION (Time-based behavior analysis) =====
        temporal_label = tk.Label(
            right_panel,
            text="⏱️ Временные уровни",
            font=("Helvetica", 11, "bold"),
            bg="#ecf0f1",
            fg="#3498db"
        )
        temporal_label.pack(anchor=tk.W, padx=10, pady=(10, 5))

        # Temporal levels frame
        temporal_frame = tk.Frame(right_panel, bg="#f0f8ff", relief=tk.SUNKEN, bd=1)
        temporal_frame.pack(fill=tk.X, padx=10, pady=5)

        # T0: Instantaneous (current moment)
        tk.Label(temporal_frame, text="T0 (Мгновение):", font=("Helvetica", 8, "bold"), bg="#f0f8ff", fg="#2980b9").pack(anchor=tk.W, padx=5, pady=(5, 2))
        self.t0_display = tk.Label(temporal_frame, text="val:0.00 arl:0.00 thr:0.00 cur:0.00", font=("Courier", 7), bg="#f0f8ff", fg="#555")
        self.t0_display.pack(anchor=tk.W, padx=5, pady=0)

        # T1: Short-term (sliding window)
        tk.Label(temporal_frame, text="T1 (Тренд):", font=("Helvetica", 8, "bold"), bg="#f0f8ff", fg="#16a085").pack(anchor=tk.W, padx=5, pady=(5, 2))
        self.t1_display = tk.Label(temporal_frame, text="val:+0.00 arl:+0.00 thr:-0.00 cur:+0.00", font=("Courier", 7), bg="#f0f8ff", fg="#555")
        self.t1_display.pack(anchor=tk.W, padx=5, pady=0)

        # T2: Baseline (consolidated mid-term)
        tk.Label(temporal_frame, text="T2 (Baseline - slow drift):", font=("Helvetica", 8, "bold"), bg="#f0f8ff", fg="#8e44ad").pack(anchor=tk.W, padx=5, pady=(5, 2))
        self.t2_display = tk.Label(temporal_frame, text="val:0.00 arl:0.00 thr:0.00 cur:0.00", font=("Courier", 7), bg="#f0f8ff", fg="#555")
        self.t2_display.pack(anchor=tk.W, padx=5, pady=0)

        # T3: Long-term attractor
        tk.Label(temporal_frame, text="T3 (Attractor - very slow):", font=("Helvetica", 8, "bold"), bg="#f0f8ff", fg="#c0392b").pack(anchor=tk.W, padx=5, pady=(5, 2))
        self.t3_display = tk.Label(temporal_frame, text="val:0.00 arl:0.00 thr:0.00 cur:0.00", font=("Courier", 7), bg="#f0f8ff", fg="#555")
        self.t3_display.pack(anchor=tk.W, padx=5, pady=0)

        # Window size info
        window_info = tk.Frame(temporal_frame, bg="#f0f8ff")
        window_info.pack(fill=tk.X, padx=5, pady=(5, 5))
        tk.Label(window_info, text="Окно T1:", font=("Helvetica", 8), bg="#f0f8ff").pack(side=tk.LEFT)
        self.window_display = tk.Label(
            window_info,
            text="0/10 (скользящее)",
            font=("Courier", 7, "bold"),
            bg="#f0f8ff",
            fg="#2980b9",
        )
        self.window_display.pack(side=tk.LEFT, padx=3)
        self.window_hint_display = tk.Label(
            temporal_frame,
            text="Всего шагов: 0",
            font=("Helvetica", 7),
            bg="#f0f8ff",
            fg="#666",
        )
        self.window_hint_display.pack(anchor=tk.W, padx=5, pady=(0, 5))
        
        # NOTE: feedback UI moved to the left panel (under dialog buttons)
        
        # Stats section (moved down - after feedback)
        stats_label = tk.Label(right_panel, text="📊 Статистика:", font=("Helvetica", 11, "bold"), bg="#ecf0f1")
        stats_label.pack(anchor=tk.W, padx=10, pady=(10, 5))
        
        self.stats_display = tk.Text(
            right_panel,
            height=6,
            width=30,
            wrap=tk.WORD,
            state=tk.DISABLED,
            bg="#ffffff"
        )
        self.stats_display.pack(fill=tk.X, padx=10, pady=5)

        # Agent lifetime display
        lifetime_frame = tk.Frame(right_panel, bg="#ecf0f1")
        lifetime_frame.pack(fill=tk.X, padx=10, pady=(2, 6))
        tk.Label(lifetime_frame, text="⏳ Время жизни агента:", font=("Helvetica", 9, "bold"), bg="#ecf0f1").pack(side=tk.LEFT)
        self.lifetime_label = tk.Label(lifetime_frame, text="0s", font=("Courier", 9), bg="#ecf0f1", fg="#555")
        self.lifetime_label.pack(side=tk.LEFT, padx=6)
        
        # Memory info
        memory_label = tk.Label(right_panel, text="🧠 Память:", font=("Helvetica", 11, "bold"), bg="#ecf0f1")
        memory_label.pack(anchor=tk.W, padx=10, pady=(10, 5))
        
        self.memory_display = tk.Text(
            right_panel,
            height=10,
            width=30,
            wrap=tk.WORD,
            state=tk.DISABLED,
            bg="#ffffff"
        )
        self.memory_display.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Update canvas scroll region to fit all content
        right_panel.update_idletasks()
        right_canvas.config(scrollregion=right_canvas.bbox("all"))
    
    def _bind_clipboard_shortcuts(self, widget):
        """Bind common clipboard shortcuts (Ctrl-C/V/X/A) to a widget."""
        try:
            def _copy(event):
                try:
                    # Prefer Text/Entry built-in binding
                    widget.event_generate("<<Copy>>")
                except Exception:
                    try:
                        sel = None
                        if isinstance(widget, tk.Entry):
                            sel = widget.selection_get()
                        else:
                            sel = widget.get("sel.first", "sel.last")
                        if sel:
                            self.root.clipboard_clear()
                            self.root.clipboard_append(sel)
                    except Exception:
                        pass
                return "break"

            def _paste(event):
                try:
                    txt = self.root.clipboard_get()
                    if txt is None:
                        return "break"
                    if isinstance(widget, tk.Entry):
                        widget.insert(tk.INSERT, txt)
                    else:
                        widget.insert(tk.INSERT, txt)
                except Exception:
                    pass
                return "break"

            def _cut(event):
                try:
                    widget.event_generate("<<Cut>>")
                except Exception:
                    try:
                        if isinstance(widget, tk.Entry):
                            sel = widget.selection_get()
                            self.root.clipboard_clear()
                            self.root.clipboard_append(sel)
                            try:
                                widget.delete("sel.first", "sel.last")
                            except Exception:
                                pass
                        else:
                            sel = widget.get("sel.first", "sel.last")
                            self.root.clipboard_clear()
                            self.root.clipboard_append(sel)
                            try:
                                widget.delete("sel.first", "sel.last")
                            except Exception:
                                pass
                    except Exception:
                        pass
                return "break"

            def _select_all(event):
                try:
                    if isinstance(widget, tk.Entry):
                        widget.select_range(0, tk.END)
                    else:
                        widget.tag_add(tk.SEL, "1.0", tk.END)
                        widget.mark_set(tk.INSERT, "1.0")
                        widget.see(tk.INSERT)
                except Exception:
                    pass
                return "break"

            def _on_ctrl_key(event):
                try:
                    keysym = (event.keysym or "").lower()
                    keycode = getattr(event, "keycode", None)

                    if keycode == 67 or keysym in ("c", "cyrillic_es"):
                        return _copy(event)
                    if keycode == 86 or keysym in ("v", "cyrillic_em"):
                        return _paste(event)
                    if keycode == 88 or keysym in ("x", "cyrillic_che"):
                        return _cut(event)
                    if keycode == 65 or keysym in ("a", "cyrillic_ef"):
                        return _select_all(event)
                except Exception:
                    pass
                return None

            widget.bind("<Control-c>", _copy)
            widget.bind("<Control-C>", _copy)
            widget.bind("<Control-Insert>", _copy)
            widget.bind("<Control-v>", _paste)
            widget.bind("<Control-V>", _paste)
            widget.bind("<Shift-Insert>", _paste)
            widget.bind("<Control-x>", _cut)
            widget.bind("<Control-X>", _cut)
            widget.bind("<Shift-Delete>", _cut)
            widget.bind("<Control-a>", _select_all)
            widget.bind("<Control-A>", _select_all)
            widget.bind("<Control-KeyPress>", _on_ctrl_key, add=True)
        except Exception:
            pass

    def _bind_clipboard_shortcuts_recursive(self, parent):
        """Bind clipboard shortcuts to all text-like widgets inside a container."""
        try:
            for child in parent.winfo_children():
                if isinstance(child, (tk.Entry, tk.Text, tk.Spinbox, ttk.Entry, ttk.Spinbox)):
                    self._bind_clipboard_shortcuts(child)
                self._bind_clipboard_shortcuts_recursive(child)
        except Exception:
            pass

    def _show_context_menu(self, event, widget):
        """Show a context menu (Cut/Copy/Paste/Select All) for the given widget."""
        try:
            menu = tk.Menu(self.root, tearoff=0)

            def _copy():
                try:
                    if isinstance(widget, tk.Entry):
                        sel = widget.selection_get()
                    else:
                        sel = widget.get("sel.first", "sel.last")
                    self.root.clipboard_clear()
                    self.root.clipboard_append(sel)
                except Exception:
                    pass

            def _paste():
                try:
                    txt = self.root.clipboard_get()
                    if isinstance(widget, tk.Entry):
                        widget.insert(tk.INSERT, txt)
                    else:
                        widget.insert(tk.INSERT, txt)
                except Exception:
                    pass

            def _cut():
                try:
                    if isinstance(widget, tk.Entry):
                        sel = widget.selection_get()
                        self.root.clipboard_clear()
                        self.root.clipboard_append(sel)
                        widget.delete(0, tk.END) if widget.index(tk.INSERT) == 0 else None
                        try:
                            widget.delete("sel.first", "sel.last")
                        except Exception:
                            pass
                    else:
                        sel = widget.get("sel.first", "sel.last")
                        self.root.clipboard_clear()
                        self.root.clipboard_append(sel)
                        try:
                            widget.delete("sel.first", "sel.last")
                        except Exception:
                            pass
                except Exception:
                    pass

            def _select_all():
                try:
                    if isinstance(widget, tk.Entry):
                        widget.select_range(0, tk.END)
                    else:
                        widget.tag_add(tk.SEL, "1.0", tk.END)
                        widget.mark_set(tk.INSERT, "1.0")
                        widget.see(tk.INSERT)
                except Exception:
                    pass

            menu.add_command(label=tr("Копировать"), command=_copy)
            menu.add_command(label=tr("Вырезать"), command=_cut)
            menu.add_command(label=tr("Вставить"), command=_paste)
            menu.add_separator()
            menu.add_command(label=tr("Выделить всё"), command=_select_all)

            menu.tk_popup(event.x_root, event.y_root)
        except Exception:
            pass

    def update_affect_display(self):
        """Обновить визуализацию аффективного состояния"""
        affect = self.agent.affect_state
        
        # Обновить Валентность (-1 до +1)
        self.valence_label.config(text=f"{affect.valence:.2f}")
        self._update_bar(self.valence_bar, affect.valence, -1, 1, "#e74c3c", "#27ae60")
        
        # Обновить Активацию (0 до 2)
        self.arousal_label.config(text=f"{affect.arousal:.2f}")
        self._update_bar(self.arousal_bar, affect.arousal, 0, 2, "#3498db", "#f39c12")
        
        # Обновить Угрозу (0 до 1)
        self.threat_label.config(text=f"{affect.threat:.2f}")
        self._update_bar(self.threat_bar, affect.threat, 0, 1, "#2ecc71", "#e74c3c")
        
        # Обновить Любопытство (0 до 1)
        self.curiosity_label.config(text=f"{affect.curiosity:.2f}")
        self._update_bar(self.curiosity_bar, affect.curiosity, 0, 1, "#95a5a6", "#9b59b6")

        # Обновить аффективный фон (Phase 3.75)
        try:
            bg = getattr(self.agent, "affective_background", None)
            snapshot = bg.snapshot() if bg is not None else {}
        except Exception:
            snapshot = {}

        bg_anxiety = float(snapshot.get("background_anxiety", 0.0))
        bg_tension = float(snapshot.get("background_tension", 0.0))
        bg_satisfaction = float(snapshot.get("background_satisfaction", 0.0))
        bg_interest = float(snapshot.get("background_interest", 0.0))

        self.bg_anxiety_label.config(text=f"{bg_anxiety:.2f}")
        self._update_bar(self.bg_anxiety_bar, bg_anxiety, 0, 1, "#bdc3c7", "#e74c3c")
        self.bg_tension_label.config(text=f"{bg_tension:.2f}")
        self._update_bar(self.bg_tension_bar, bg_tension, 0, 1, "#bdc3c7", "#f39c12")
        self.bg_satisfaction_label.config(text=f"{bg_satisfaction:.2f}")
        self._update_bar(self.bg_satisfaction_bar, bg_satisfaction, 0, 1, "#bdc3c7", "#27ae60")
        self.bg_interest_label.config(text=f"{bg_interest:.2f}")
        self._update_bar(self.bg_interest_bar, bg_interest, 0, 1, "#bdc3c7", "#3498db")

        # Обновить аффективное пространство (Phase 4 pre)
        try:
            space = getattr(self.agent, "affective_space", None)
            axes = getattr(space, "axes", {}) if space is not None else {}
            legacy_axes = (
                space.legacy_axes_snapshot()
                if (space is not None and hasattr(space, "legacy_axes_snapshot"))
                else {}
            )
        except Exception:
            space = None
            axes = {}
            legacy_axes = {}

        for axis, bar in getattr(self, "affective_space_bars", {}).items():
            value = float(axes.get(axis, 0.0))
            label = self.affective_space_value_labels.get(axis)
            if label is not None:
                label.config(text=f"{value:.2f}")
            color = self.affective_space_colors.get(axis, "#3498db")
            self._update_bar(bar, value, -1, 1, "#bdc3c7", color)

        for axis, bar in getattr(self, "affective_space_legacy_bars", {}).items():
            value = float(legacy_axes.get(axis, 0.0))
            label = getattr(self, "affective_space_legacy_labels", {}).get(axis)
            if label is not None:
                label.config(text=f"{value:.2f}")
            self._update_bar(bar, value, 0, 1, "#bdc3c7", "#95a5a6")

        try:
            bias = space.decision_bias() if space is not None else {}
            bits = " ".join(f"{axis_label(k)}={float(v):+.2f}" for k, v in dict(bias or {}).items())
            self.decision_bias_label.config(text=f"{tr('bias:')} {bits}" if bits else tr("bias: —"))
        except Exception:
            pass

        if space is not None:
            try:
                self.affective_space_speed_label.config(text=f"V: {space.speed():.2f}")
                self.affective_space_conflict_label.config(text=f"{tr('Conflict:')} {space.axis_conflict():.2f}")
            except Exception:
                pass
        else:
            try:
                self.affective_space_speed_label.config(text="V: 0.00")
                self.affective_space_conflict_label.config(text=tr("Conflict: 0.00"))
            except Exception:
                pass

        # Update semantic emotions (Phase 4.1)
        try:
            sem_layer = getattr(self.agent, "semantic_emotions", None)
            active = sem_layer.snapshot() if sem_layer is not None else []
        except Exception:
            active = []

        summary_text = tr("(none)")
        try:
            if sem_layer is not None and hasattr(sem_layer, "describe_brief"):
                summary_text = translate_block(sem_layer.describe_brief(space=space, background=snapshot))
        except Exception:
            summary_text = tr("(none)")

        lines = []
        if active:
            active_sorted = sorted(active, key=lambda item: float(item.get("activation", 0.0)), reverse=True)
            for item in active_sorted:
                name = emotion_label(item.get("emotion", "unknown"))
                activation = float(item.get("activation", 0.0))
                stability = float(item.get("stability", 0.0))
                obsessive = bool(item.get("obsessive", False))
                obs_tag = " obs" if obsessive else ""
                lines.append(f"{name}: {activation:.2f} st:{stability:.2f}{obs_tag}")

        sem_text = "\n".join(lines) if lines else tr("(none)")
        try:
            if hasattr(self, "semantic_emotions_summary_label") and self.semantic_emotions_summary_label is not None:
                self.semantic_emotions_summary_label.config(text=summary_text)
            if hasattr(self, "semantic_emotions_label") and self.semantic_emotions_label is not None:
                self.semantic_emotions_label.config(text=sem_text if lines else "")
        except Exception:
            pass

        # Update emotional memory narratives (Phase 4.2)
        try:
            mem_layer = getattr(self.agent, "emotional_memory", None)
            mem_snapshot = mem_layer.snapshot() if mem_layer is not None else {}
        except Exception:
            mem_layer = None
            mem_snapshot = {}

        mem_summary = tr("(none)")
        try:
            if mem_layer is not None and hasattr(mem_layer, "describe_brief"):
                mem_summary = translate_block(mem_layer.describe_brief(max_fragments=2))
        except Exception:
            mem_summary = tr("(none)")

        mem_lines = []
        try:
            episodes_count = len(mem_snapshot.get("episodes", []) or [])
            patterns = list(mem_snapshot.get("patterns", []) or [])
            mem_lines.append(f"episodes:{episodes_count} patterns:{len(patterns)}")
            if patterns:
                top = patterns[0]
                emotion = top.get("emotion", "unknown")
                rec = float(top.get("recurrence", 0.0))
                inertia = float(top.get("inertia", 0.0))
                obs = " obs" if bool(top.get("obsessive", False)) else ""
                mem_lines.append(f"top:{emotion} rec:{rec:.2f} in:{inertia:.2f}{obs}")
            traits = mem_snapshot.get("character_traits") or []
            if traits:
                mem_lines.append(f"traits:{', '.join(traits[:3])}")
        except Exception:
            mem_lines = []

        mem_text = "\n".join(mem_lines) if mem_lines else ""
        try:
            if hasattr(self, "emotional_memory_summary_label") and self.emotional_memory_summary_label is not None:
                self.emotional_memory_summary_label.config(text=mem_summary)
            if hasattr(self, "emotional_memory_metrics_label") and self.emotional_memory_metrics_label is not None:
                self.emotional_memory_metrics_label.config(text=mem_text)
        except Exception:
            pass

        # Update emotional expectations (Phase 4.3)
        try:
            exp_layer = getattr(self.agent, "emotional_expectations", None)
            exp_snapshot = exp_layer.snapshot() if exp_layer is not None else {}
        except Exception:
            exp_layer = None
            exp_snapshot = {}

        exp_summary = tr("(none)")
        try:
            if exp_layer is not None and hasattr(exp_layer, "describe_brief"):
                exp_summary = translate_block(exp_layer.describe_brief(max_lines=2))
        except Exception:
            exp_summary = tr("(none)")

        exp_lines = []
        try:
            expectations = list(exp_snapshot.get("expectations", []) or [])
            if expectations:
                top = expectations[0]
                emotion = top.get("emotion", "unknown")
                prob = float(top.get("probability", 0.0))
                conf = float(top.get("confidence", 0.0))
                trend = top.get("trend", "stable")
                risk = " risk" if bool(top.get("risk_of_repetition", False)) else ""
                exp_lines.append(f"top:{emotion} p:{prob:.2f} c:{conf:.2f} {trend}{risk}")
            dominant = exp_snapshot.get("dominant_forecast", "")
            if dominant:
                exp_lines.append(f"dominant:{dominant}")
            outlook = exp_snapshot.get("global_outlook", "")
            if outlook:
                exp_lines.append(f"outlook:{outlook}")
        except Exception:
            exp_lines = []

        exp_text = "\n".join(exp_lines) if exp_lines else ""
        try:
            if hasattr(self, "emotional_expectations_summary_label") and self.emotional_expectations_summary_label is not None:
                self.emotional_expectations_summary_label.config(text=exp_summary)
            if hasattr(self, "emotional_expectations_metrics_label") and self.emotional_expectations_metrics_label is not None:
                self.emotional_expectations_metrics_label.config(text=exp_text)
        except Exception:
            pass

        # Update emotional regulation (Phase 4.4)
        try:
            reg_layer = getattr(self.agent, "emotional_regulation", None)
            reg_snapshot = reg_layer.snapshot() if reg_layer is not None else {}
        except Exception:
            reg_layer = None
            reg_snapshot = {}

        reg_summary = tr("(none)")
        try:
            if reg_layer is not None and hasattr(reg_layer, "describe_brief"):
                reg_summary = translate_block(reg_layer.describe_brief(max_lines=2))
        except Exception:
            reg_summary = tr("(none)")

        reg_lines = []
        try:
            if reg_snapshot:
                active = bool(reg_snapshot.get("regulation_active", False))
                mode = reg_snapshot.get("regulation_mode", "none")
                reg_lines.append(f"active:{active} mode:{mode}")
                if "valence" in reg_snapshot and "arousal" in reg_snapshot and "uncertainty_tension" in reg_snapshot:
                    reg_lines.append(
                        "v:{:+.2f} a:{:.2f} u:{:.2f}".format(
                            float(reg_snapshot.get("valence", 0.0)),
                            float(reg_snapshot.get("arousal", 0.0)),
                            float(reg_snapshot.get("uncertainty_tension", 0.0)),
                        )
                    )
                factors = dict(reg_snapshot.get("modulation_factors", {}) or {})
                if factors:
                    reg_lines.append(
                        "mod: expl={:.2f} lr={:.2f} nov={:.2f} thr={:+.2f} hb={:.2f}".format(
                            float(factors.get("exploration_bias", 0.0)),
                            float(factors.get("learning_rate_scale", 1.0)),
                            float(factors.get("novelty_sensitivity_scale", 1.0)),
                            float(factors.get("decision_threshold_shift", 0.0)),
                            float(factors.get("habit_gain_scale", 1.0)),
                        )
                    )
                guidance = dict(reg_snapshot.get("neuromodulator_guidance", {}) or {})
                if guidance:
                    reg_lines.append(
                        "nm*: da={:+.3f} ne={:+.3f} 5ht={:+.3f} cort={:+.3f}".format(
                            float(guidance.get("dopamine", 0.0)),
                            float(guidance.get("norepinephrine", 0.0)),
                            float(guidance.get("serotonin", 0.0)),
                            float(guidance.get("cortisol", 0.0)),
                        )
                    )
                adj = reg_snapshot.get("applied_adjustments", {}) or {}
                bg_shift = adj.get("background_shift", {}) or {}
                nm_shift = adj.get("neuromodulator_shift", {}) or {}
                if bg_shift:
                    items = [f"{k}:{v:+.2f}" for k, v in bg_shift.items()]
                    reg_lines.append("bg: " + ", ".join(items[:3]))
                if nm_shift:
                    items = [f"{k}:{v:+.2f}" for k, v in nm_shift.items()]
                    reg_lines.append("nm: " + ", ".join(items[:3]))
        except Exception:
            reg_lines = []

        reg_text = "\n".join(reg_lines) if reg_lines else ""
        try:
            if hasattr(self, "emotional_regulation_summary_label") and self.emotional_regulation_summary_label is not None:
                self.emotional_regulation_summary_label.config(text=reg_summary)
            if hasattr(self, "emotional_regulation_metrics_label") and self.emotional_regulation_metrics_label is not None:
                self.emotional_regulation_metrics_label.config(text=reg_text)
        except Exception:
            pass

        # Update stability monitoring (Phase 4.5)
        try:
            stability_layer = getattr(self.agent, "stability_monitor", None)
            stability_snapshot = stability_layer.snapshot() if stability_layer is not None else {}
        except Exception:
            stability_layer = None
            stability_snapshot = {}

        stability_summary = tr("(none)")
        try:
            if stability_layer is not None and hasattr(stability_layer, "describe_brief"):
                stability_summary = translate_block(stability_layer.describe_brief(max_lines=2))
        except Exception:
            stability_summary = tr("(none)")

        stability_lines = []
        try:
            if stability_snapshot:
                index = float(stability_snapshot.get("stability_index", 1.0))
                recommendation = str(stability_snapshot.get("recommendation", "none"))
                stability_lines.append(f"index:{index:.2f} rec:{recommendation}")

                flags = stability_snapshot.get("drift_flags", {}) or {}
                stability_lines.append(
                    "flags: "
                    f"reg:{int(bool(flags.get('regulation_overuse', False)))} "
                    f"bg:{int(bool(flags.get('background_drift', False)))} "
                    f"nm:{int(bool(flags.get('neuromodulator_drift', False)))} "
                    f"lock:{int(bool(flags.get('dominant_emotion_lock', False)))} "
                    f"out:{int(bool(flags.get('outlook_bias', False)))}"
                )

                metrics = stability_snapshot.get("metrics", {}) or {}
                stability_lines.append(
                    f"r4.4:{float(metrics.get('regulation_activation_rate', 0.0)):.2f} "
                    f"bgμ:{float(metrics.get('mean_background_anxiety', 0.0)):.2f} "
                    f"esc:{float(metrics.get('escalating_ratio', 0.0)):.2f}"
                )
        except Exception:
            stability_lines = []

        stability_text = "\n".join(stability_lines) if stability_lines else ""
        try:
            if hasattr(self, "stability_monitor_summary_label") and self.stability_monitor_summary_label is not None:
                self.stability_monitor_summary_label.config(text=stability_summary)
            if hasattr(self, "stability_monitor_metrics_label") and self.stability_monitor_metrics_label is not None:
                self.stability_monitor_metrics_label.config(text=stability_text)
        except Exception:
            pass

        # Update value layer diagnostics (Phase 5.0)
        try:
            value_layer = getattr(self.agent, "value_layer", None)
            value_snapshot = value_layer.snapshot() if value_layer is not None else {}
        except Exception:
            value_layer = None
            value_snapshot = {}

        value_summary = "Данных пока нет"
        try:
            if value_snapshot:
                td_error = float(value_snapshot.get("last_td_error", 0.0))
                updates = int(value_snapshot.get("update_count", 0))
                if updates <= 0:
                    value_summary = "Слой ценности еще не обучался."
                elif td_error > 0.02:
                    value_summary = "Положительный сюрприз: результат лучше ожиданий."
                elif td_error < -0.02:
                    value_summary = "Отрицательный сюрприз: результат хуже ожиданий."
                else:
                    value_summary = "Ожидания и результат почти совпали."
        except Exception:
            value_summary = "Данных пока нет"

        value_lines = []
        try:
            if value_snapshot:
                value = float(value_snapshot.get("value", 0.0))
                td_error = float(value_snapshot.get("last_td_error", 0.0))
                dopamine_delta = float(value_snapshot.get("last_dopamine_delta", 0.0))
                state_count = int(value_snapshot.get("state_count", 0))
                max_states = int(value_snapshot.get("max_states", 0))
                updates = int(value_snapshot.get("update_count", 0))
                value_lines.append(
                    f"Оценка состояния: {value:+.3f}"
                )
                value_lines.append(
                    f"Ошибка прогноза (TD): {td_error:+.3f}"
                )
                value_lines.append(
                    f"Сдвиг дофамина от TD: {dopamine_delta:+.3f}"
                )
                value_lines.append(
                    f"Известных состояний: {state_count}/{max_states:,}".replace(",", " ")
                )
                value_lines.append(
                    f"Шагов обучения: {updates:,}".replace(",", " ")
                )
        except Exception:
            value_lines = []

        value_text = translate_block("\n".join(value_lines)) if value_lines else ""
        try:
            if hasattr(self, "value_layer_summary_label") and self.value_layer_summary_label is not None:
                self.value_layer_summary_label.config(text=value_summary)
            if hasattr(self, "value_layer_metrics_label") and self.value_layer_metrics_label is not None:
                self.value_layer_metrics_label.config(text=value_text)
        except Exception:
            pass
        
        # Обновить Готовность
        readiness = affect.adaptation_readiness()
        readiness_pct = int(readiness * 100)
        if readiness > 0.7:
            status = f"{tr('✅ Высокая')} ({readiness_pct}%)"
            color = "#27ae60"
        elif readiness > 0.4:
            status = f"{tr('⚠️ Средняя')} ({readiness_pct}%)"
            color = "#f39c12"
        else:
            status = f"{tr('❌ Низкая')} ({readiness_pct}%)"
            color = "#e74c3c"
        self.readiness_label.config(text=status, fg=color)
        
        # Update neuromodulators display if available
        try:
            nm = getattr(self.agent, 'neuromodulators', None)
            if nm is not None:
                self.da_label.config(text=f"DA: {getattr(nm, 'dopamine', 0.0):.2f}")
                self.ne_label.config(text=f"NE: {getattr(nm, 'norepinephrine', 0.0):.2f}")
                self.ser_label.config(text=f"5-HT: {getattr(nm, 'serotonin', 0.0):.2f}")
                self.cort_label.config(text=f"CORT: {getattr(nm, 'cortisol', 0.0):.2f}")
                self.ach_label.config(text=f"ACh: {getattr(nm, 'acetylcholine', 0.0):.2f}")
        except Exception:
            pass
        
        # Update wakefulness display
        self.update_wakefulness_display()
        self.update_autonomous_display()

        # Update agent lifetime display
        try:
            if hasattr(self.agent, 'get_lifetime'):
                secs = int(self.agent.get_lifetime())
                hrs = secs // 3600
                mins = (secs % 3600) // 60
                s = secs % 60
                if hrs > 0:
                    fmt = f"{hrs}h {mins}m {s}s"
                elif mins > 0:
                    fmt = f"{mins}m {s}s"
                else:
                    fmt = f"{s}s"
                self.lifetime_label.config(text=fmt)
        except Exception:
            pass
    
    def _update_bar(self, canvas, value, min_val, max_val, neg_color, pos_color):
        """Update progress bar safely for both one-sided and symmetric ranges."""
        canvas.delete("all")
        width = canvas.winfo_width()
        if width <= 1:
            width = 150
        height = 20

        try:
            value = float(value)
            min_val = float(min_val)
            max_val = float(max_val)
        except Exception:
            return

        if max_val <= min_val:
            max_val = min_val + 1.0

        clamped = max(min_val, min(max_val, value))
        symmetric_mode = (min_val < 0.0 < max_val)

        canvas.create_rectangle(0, 0, width, height, fill="#ecf0f1", outline="#bdc3c7")

        if symmetric_mode:
            span = max(1e-9, max_val - min_val)
            center_x = width * ((0.0 - min_val) / span)
            canvas.create_line(center_x, 0, center_x, height, fill="#999", dash=(2, 2))

            if clamped < 0:
                neg_span = max(1e-9, abs(min_val))
                bar_width = (abs(clamped) / neg_span) * center_x
                if bar_width > 0:
                    canvas.create_rectangle(
                        center_x - bar_width, 2, center_x, height - 2,
                        fill=neg_color, outline=neg_color,
                    )
            elif clamped > 0:
                pos_span = max(1e-9, max_val)
                bar_width = (clamped / pos_span) * max(0.0, width - center_x)
                if bar_width > 0:
                    canvas.create_rectangle(
                        center_x, 2, center_x + bar_width, height - 2,
                        fill=pos_color, outline=pos_color,
                    )
            return

        # One-sided range (e.g., [0,1])
        frac = (clamped - min_val) / max(1e-9, (max_val - min_val))
        frac = max(0.0, min(1.0, frac))
        bar_width = frac * width
        if bar_width > 0:
            color = pos_color if clamped >= 0 else neg_color
            canvas.create_rectangle(0, 2, bar_width, height - 2, fill=color, outline=color)

    def update_temporal_display(self):
        """Обновить визуализацию временных уровней (T0/T1/T2/T3)"""
        try:
            if not hasattr(self.agent, 'temporal'):
                return
            
            levels = self.agent.temporal.get_levels()
            
            # Extract values for display
            t0 = levels.get('T0', {})
            t1_mean = levels.get('T1_mean', {})
            t2 = levels.get('T2_baseline', {})
            t3 = levels.get('T3_attractor', {})
            
            # Format T0 (instantaneous)
            t0_val = f"val:{t0.get('valence', 0):.2f} arl:{t0.get('arousal', 0):.2f} thr:{t0.get('threat', 0):.2f} cur:{t0.get('curiosity', 0):.2f}"
            self.t0_display.config(text=t0_val)
            
            # Format T1 (trend - differences from T0)
            t1_val_delta = t1_mean.get('valence', 0) - t0.get('valence', 0)
            t1_arl_delta = t1_mean.get('arousal', 0) - t0.get('arousal', 0)
            t1_thr_delta = t1_mean.get('threat', 0) - t0.get('threat', 0)
            t1_cur_delta = t1_mean.get('curiosity', 0) - t0.get('curiosity', 0)
            
            t1_val_str = f"val:{t1_val_delta:+.2f} arl:{t1_arl_delta:+.2f} thr:{t1_thr_delta:+.2f} cur:{t1_cur_delta:+.2f}"
            self.t1_display.config(text=t1_val_str)
            
            # Format T2 (baseline)
            t2_val = f"val:{t2.get('valence', 0):.2f} arl:{t2.get('arousal', 0):.2f} thr:{t2.get('threat', 0):.2f} cur:{t2.get('curiosity', 0):.2f}"
            self.t2_display.config(text=t2_val)
            
            # Format T3 (long-term attractor)
            t3_val = f"val:{t3.get('valence', 0):.2f} arl:{t3.get('arousal', 0):.2f} thr:{t3.get('threat', 0):.2f} cur:{t3.get('curiosity', 0):.2f}"
            self.t3_display.config(text=t3_val)
            
            # Update window size info (T1 is a deque with max 10 items)
            t1_list = self.agent.temporal.t1
            window_size = len(t1_list) if t1_list else 0
            window_capacity = int(getattr(self.agent.temporal, "window_size", 10))
            self.window_display.config(
                text=tr("{count}/{capacity} (скользящее)", count=window_size, capacity=window_capacity)
            )
            total_steps = int(getattr(self.agent, "lived_steps", 0))
            if hasattr(self, "window_hint_display") and self.window_hint_display is not None:
                self.window_hint_display.config(text=tr("Всего шагов: {n}", n=total_steps))
        except Exception as e:
            # Silent fail for temporal display issues
            pass
    
    def update_wakefulness_display(self):
        """Обновить визуализацию состояния бодрствования"""
        try:
            if not hasattr(self.agent, 'wakefulness'):
                return
            
            wakefulness = self.agent.wakefulness
            
            # Update wakefulness level bar
            level = wakefulness.wakefulness
            fatigue_words = [
                tr("Полностью выспавшийся"),
                tr("Слегка усталый"),
                tr("Усталый"),
                tr("Очень усталый"),
                tr("Истощенный"),
            ]
            self.wakefulness_label.config(
                text=f"{level:.2f} ({fatigue_words[min(4, int(level * 5))]})"
            )
            self._update_bar(self.wakefulness_bar, level, 0, 1, "#95a5a6", "#e74c3c")
            
            # Update cognitive reliability bar
            reliability = wakefulness.get_cognitive_reliability()
            reliability_words = [
                tr("Недежен"),
                tr("Ненадежен"),
                tr("Средне"),
                tr("Надежен"),
                tr("Полностью надежен"),
            ]
            self.reliability_label.config(
                text=f"{reliability:.2f} ({reliability_words[min(4, int(reliability * 5))]})"
            )
            color = "#27ae60" if reliability > 0.7 else ("#f39c12" if reliability > 0.4 else "#e74c3c")
            self.reliability_label.config(fg=color)
            self._update_bar(self.reliability_bar, reliability, 0, 1, "#e74c3c", "#27ae60")
            
            # Update time statistics
            stats = wakefulness.get_statistics()
            awake_hours = stats['accumulated_waking_hours']
            sleep_hours = stats['total_sleep_hours']
            self.wakefulness_stats.config(
                text=tr(
                    "Бодрствова: {awake:.1f}ч | Спал: {sleep:.1f}ч",
                    awake=awake_hours,
                    sleep=sleep_hours,
                )
            )
        except Exception as e:
            # Silent fail
            pass
    
    def take_sleep(self, hours: float):
        """Принять сон на указанное количество часов"""
        try:
            seconds = hours * 3600
            
            # Show dialog
            response = messagebox.showinfo(
                tr("Сон"),
                tr(
                    "Агент спит {hours:.1f} часа(ов) ({minutes} минут)...",
                    hours=hours,
                    minutes=int(seconds / 60),
                ),
            )
            
            # Execute sleep in background thread
            def sleep_thread():
                self.agent.sleep(cycles=int(hours * 2))  # ~2 cycles per hour
                self.add_to_chat(
                    tr("[SYSTEM] Агент проснулся после {hours:.1f}ч сна.", hours=hours),
                    "system",
                )
                self.update_stats("sleep")
                self.update_affect_display()
                self.update_temporal_display()
                self.update_memory_display()
            
            threading.Thread(target=sleep_thread, daemon=True).start()
        except Exception as e:
            messagebox.showerror(tr("Ошибка сна"), tr("Ошибка: {error}", error=str(e)))
    
    def send_message(self):
        user_input = self.input_field.get().strip()
        if not user_input:
            return
        
        self.input_field.delete(0, tk.END)
        self.add_to_chat(tr("Вы: {user_input}", user_input=user_input), "user")
        
        # Process in separate thread
        threading.Thread(target=self.process_input, args=(user_input,), daemon=True).start()
        
    def process_input(self, user_input):
        try:
            context = [f"user:{user_input}"]
            self.last_context = context
            
            # Apply time-based decay to affective state (curiosity, threat, arousal, etc.)
            # This enables curiosity to decrease between interactions
            current_time = time.time()
            time_elapsed = current_time - self.last_process_time
            if time_elapsed > 0.0:  # Always apply decay if any time has passed
                self.agent.affect_state.decay_over_time(time_elapsed, half_life=60.0)
            self.last_process_time = current_time
            
            # Compute graded novelty: 1 - max_jaccard_similarity(context, recent_experience_signature)
            novelty = 0.0
            try:
                if hasattr(self, 'hippocampus'):
                    recent = getattr(self.hippocampus, 'experiences', [])[-50:]
                    # If no recent experiences, treat as fully novel
                    if not recent:
                        novelty = 1.0
                    else:
                        ctx_set = set(context)
                        max_sim = 0.0
                        # Compute Jaccard similarity against recent experiences
                        for exp in recent:
                            try:
                                sig = set(exp.path.signature())
                            except Exception:
                                sig = set()
                            union = ctx_set | sig
                            if union:
                                sim = len(ctx_set & sig) / len(union)
                            else:
                                sim = 0.0
                            if sim > max_sim:
                                max_sim = sim
                        novelty = max(0.0, min(1.0, 1.0 - max_sim))
            except Exception:
                novelty = 0.0

            # Step: store experience without learning (no reward needed during waking)
            action = self.agent.step(context, novelty=novelty)
            # Realize the action intent using learned realization experiences
            response = self.realizer_with_selector.convert_and_realize(action, context)
            
            self.add_to_chat(f"NOWA: {response}", "agent")
            self.update_stats(action)
            self.update_affect_display()  # Обновить аффективное состояние
            self.update_temporal_display()  # Обновить временные уровни
            self.update_memory_display()
            self.last_action = action
            
        except Exception as e:
            error_msg = f"Ошибка: {str(e)}"
            self.add_to_chat(error_msg, "error")
            print(f"DEBUG: {error_msg}")  # для отладки
    
    def _load_initial_realizations(self):
        """Load realization experiences and habits from datasets"""
        try:
            # Load realization forms (how to express intentions)
            realizations = load_realizations_from_datasets()
            for real in realizations:
                self.realization_memory.store(real)
            print(f"[GUI] Загружено {len(realizations)} реализаций")
            
            # Load habits (context -> action mapping for IntentMemory)
            habits = load_habits_from_datasets()
            print(f"[GUI] Загружено {len(habits)} привычек")
            for habit in habits:
                context = habit.get("context", [])
                action = habit.get("action", "")
                strength = habit.get("strength", 1.0)
                
                # Record habit in IntentMemory
                # Repeat based on strength to build initial habit traces
                for _ in range(int(strength)):
                    self.intent_memory.record_trace(context, action)
                    
            print(f"[GUI] IntentMemory инициализирована с привычками")
            
        except Exception as e:
            print(f"Could not load initial realizations: {e}")
            # This is OK - system will use fallbacks

    def _parse_json_mapping_field(self, raw_text, field_name):
        text = str(raw_text or "").strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except Exception as e:
            raise ValueError(tr("{field}: invalid JSON ({error})", field=field_name, error=e))
        if not isinstance(parsed, dict):
            raise ValueError(tr("{field}: JSON object expected", field=field_name))
        return dict(parsed)

    def _parse_predicted_reward_input(self, raw_text):
        text = str(raw_text or "").strip()
        if not text:
            return {}
        if text.startswith("{"):
            return self._parse_json_mapping_field(text, tr("прогноз награды"))
        try:
            return {"*": float(text)}
        except Exception as e:
            raise ValueError(tr("прогноз награды: ожидается число или JSON ({error})", error=e))

    def _set_external_ui_busy(self, busy):
        self.external_ui_busy = bool(busy)
        if not hasattr(self, "external_last_feedback_label"):
            return
        try:
            if busy:
                self.external_last_feedback_label.config(text=tr("обратная связь: обработка..."))
            else:
                text = str(self.external_last_feedback_label.cget("text") or "")
                if text == tr("обратная связь: обработка..."):
                    self.external_last_feedback_label.config(text=tr("обратная связь: н/д"))
        except Exception:
            pass

    def update_external_interaction_display(self):
        if not hasattr(self, "external_status_label"):
            return
        try:
            state = self.agent.get_external_interaction_state()
            self.external_status_label.config(
                text=(
                    f"{tr('набл:')}{int(state.get('observation_history', 0))} | "
                    f"{tr('ожидание:')}{int(state.get('pending_feedback', 0))} | "
                    f"{tr('шаг:')}{int(state.get('current_step', 0))} | "
                    f"{tr('стратегии:')}{int(state.get('strategy_count', 0))}"
                )
            )
        except Exception as e:
            self.external_status_label.config(text=tr("ошибка статуса внешнего слоя: {error}", error=str(e)))

    def add_external_observation_from_ui(self):
        try:
            source = str(self.external_obs_source_var.get() or "gui_manual").strip() or "gui_manual"
            payload = self._parse_json_mapping_field(self.external_obs_payload_var.get(), "observation payload")
            uncertainty = float(self.external_obs_uncertainty_var.get())
            uncertainty = max(0.0, min(1.0, uncertainty))
            observation = self.agent.observe_external_input(
                source=source,
                payload=payload,
                uncertainty=uncertainty,
            )
            self.add_to_chat(
                f"[ВНЕШН] добавлено наблюдение: источник={observation.source}, неопределенность={observation.uncertainty:.2f}",
                "system",
            )
            self.update_external_interaction_display()
        except Exception as e:
            messagebox.showerror(tr("Внешнее наблюдение"), str(e))

    def poll_external_observation_from_ui(self):
        if self.external_ui_busy:
            return
        self._set_external_ui_busy(True)

        def _worker():
            error_text = ""
            obs = None
            try:
                if hasattr(self.agent, "poll_external_observation_once"):
                    obs = asyncio.run(self.agent.poll_external_observation_once())
                if obs is None and hasattr(self.environment_interface, "observe"):
                    polled = self.environment_interface.observe()
                    if isinstance(polled, dict):
                        obs = self.agent.observe_external_input(
                            source=polled.get("source", "gui_environment"),
                            payload=dict(polled.get("payload", {}) or {}),
                            uncertainty=float(polled.get("uncertainty", 0.25)),
                            timestamp=polled.get("timestamp"),
                        )
            except Exception as e:
                error_text = str(e)

            def _done():
                self._set_external_ui_busy(False)
                if obs is not None:
                    self.add_to_chat(
                        f"[ВНЕШН] получено наблюдение: источник={getattr(obs, 'source', 'env')}, неопределенность={float(getattr(obs, 'uncertainty', 0.0)):.2f}",
                        "system",
                    )
                elif error_text:
                    self.add_to_chat(f"[ВНЕШН] ошибка опроса: {error_text}", "error")
                else:
                    self.add_to_chat("[ВНЕШН] опрос: наблюдение не получено", "system")
                self.update_external_interaction_display()

            self.root.after(0, _done)

        threading.Thread(target=_worker, daemon=True).start()

    def execute_external_action_from_ui(self):
        if self.external_ui_busy:
            return

        try:
            action_type = str(self.external_action_type_var.get() or "").strip()
            if not action_type:
                raise ValueError("требуется указать действие")
            parameters = self._parse_json_mapping_field(
                self.external_action_params_var.get(),
                "action parameters",
            )
            delay_steps = max(0, int(self.external_delay_steps_var.get()))
            predicted_reward = self._parse_predicted_reward_input(
                self.external_predicted_reward_var.get()
            )
            prior = float(self.external_expected_prior_var.get())
            prior = max(0.0, min(1.0, prior))
            expected_outcome = {
                "name": f"{action_type}_expected",
                "prior": prior,
            }
        except Exception as e:
            messagebox.showerror(tr("Внешнее действие"), str(e))
            return

        self._set_external_ui_busy(True)

        def _worker():
            error_text = ""
            result = None
            try:
                result = asyncio.run(
                    self.agent.execute_external_action(
                        action_type=action_type,
                        parameters=parameters,
                        expected_outcome=expected_outcome,
                        delay_feedback_steps=delay_steps,
                        predicted_reward=predicted_reward,
                    )
                )
            except Exception as e:
                error_text = str(e)

            def _done():
                self._set_external_ui_busy(False)
                if result is not None:
                    feedback = result.get("feedback", None)
                    queued = bool(result.get("queued", False))
                    if feedback is not None:
                        reward = float(getattr(feedback, "reward", 0.0))
                        success = float(getattr(feedback, "success_probability", 0.0))
                        latency = float(getattr(feedback, "latency", 0.0))
                    else:
                        reward = 0.0
                        success = 0.0
                        latency = 0.0
                    mode = "отложено" if queued else "применено"
                    self.add_to_chat(
                        f"[ВНЕШН] действие={action_type} -> награда={reward:+.2f}, успех={success:.2f}, задержка={latency:.3f}s ({mode})",
                        "system",
                    )
                    self.external_last_feedback_label.config(
                        text=f"обратная связь: награда={reward:+.2f}, p={success:.2f}, задержка={delay_steps}"
                    )
                else:
                    self.add_to_chat(f"[ВНЕШН] ошибка действия: {error_text}", "error")
                self.update_external_interaction_display()

            self.root.after(0, _done)

        threading.Thread(target=_worker, daemon=True).start()

    def resolve_external_feedback_from_ui(self):
        try:
            result = self.agent.resolve_external_feedback(
                current_step=getattr(self.agent, "lived_steps", 0)
            )
            resolved_count = int(result.get("resolved_count", 0))
            updates = list(result.get("learning_updates", []) or [])
            self.add_to_chat(
                f"[ВНЕШН] обработано отложенных сигналов: {resolved_count} шт., обновлений={len(updates)}",
                "system",
            )
            if updates:
                first = dict(updates[0] or {})
                reward = float(first.get("reward_signal", 0.0))
                self.external_last_feedback_label.config(
                    text=f"обратная связь: обработано={resolved_count}, награда={reward:+.2f}"
                )
            self.update_external_interaction_display()
        except Exception as e:
            self.add_to_chat(f"[ВНЕШН] ошибка обработки: {str(e)}", "error")
             
    def submit_feedback(self):
        if self.last_action is None or self.last_context is None:
            messagebox.showwarning(tr("Предупреждение"), tr("Сначала отправьте сообщение агенту"))
            return
            
        intensity = (self.feedback_var.get() + 3) / 5.0  # Convert [-2, 2] to [0.2, 1.0]
        feedback_rating = self.feedback_var.get()

        # Update affective state based on feedback
        # Map feedback from [-2, 2] to reward signal [-1.0, 1.0]
        reward_signal = feedback_rating / 2.0  # -1.0 to 1.0
        self.agent.affect_state.update_from_reward(reward_signal, intensity)

        feedback_result = {
            "updated": False,
            "td_error": 0.0,
            "salience": 0.0,
            "importance": 0.0,
        }
        try:
            feedback_result = self.agent.apply_feedback_to_last_experience(
                feedback_rating=feedback_rating,
                context_events=self.last_context,
                action_id=self.last_action,
            )
        except Exception:
            feedback_result = {
                "updated": False,
                "td_error": 0.0,
                "salience": abs(float(reward_signal)),
                "importance": 0.0,
            }
        
        feedback_text = {
            -2: tr("очень плохо (0.2)"),
            -1: tr("плохо (0.4)"),
            0: tr("нейтрально (0.6)"),
            1: tr("хорошо (0.8)"),
            2: tr("отлично (1.0)"),
        }
        
        self.add_to_chat(tr("Ваша оценка: {rating}", rating=feedback_text[feedback_rating]), "system")
        if feedback_result.get("updated"):
            td_error = float(feedback_result.get("td_error", 0.0))
            salience = float(feedback_result.get("salience", 0.0))
            self.add_to_chat(
                f"💾 Оценка добавлена в replay: TD={td_error:+.3f}, salience={salience:.3f}. Используйте 🌙 Сон.",
                "system",
            )
        else:
            self.add_to_chat("💾 Оценка сохранена. Используйте 🌙 Сон для консолидации.", "system")
        self.feedback_var.set(0)
        
        # Update affective display after feedback
        self.update_affect_display()
        self.update_memory_display()
        
    def add_to_chat(self, message, msg_type=""):
        self.chat_display.config(state=tk.NORMAL)
        
        if msg_type == "user":
            self.chat_display.insert(tk.END, message + "\n", "user")
        elif msg_type == "agent":
            self.chat_display.insert(tk.END, message + "\n", "agent")
        elif msg_type == "system":
            self.chat_display.insert(tk.END, message + "\n", "system")
        elif msg_type == "error":
            self.chat_display.insert(tk.END, message + "\n", "error")
        else:
            self.chat_display.insert(tk.END, message + "\n")
        
        # Добавить в историю
        self.chat_history.append(message)
        
        self.chat_display.tag_config("user", foreground="#2980b9", font=("Helvetica", 10, "bold"))
        self.chat_display.tag_config("agent", foreground="#27ae60", font=("Helvetica", 10, "bold"))
        self.chat_display.tag_config("system", foreground="#f39c12", font=("Helvetica", 9))
        self.chat_display.tag_config("error", foreground="#e74c3c", font=("Helvetica", 10, "bold"))
        
        self.chat_display.see(tk.END)
        self.chat_display.config(state=tk.DISABLED)
        
    def update_stats(self, action):
        if not hasattr(self, "stats_display") or self.stats_display is None:
            return
        agent_state = self.agent.get_state()
        
        stats_text = f"""Последнее действие:
{action}

Гиппокамп (шт):
{agent_state['hippocampus']['total_experiences']}

Кортекс (шт):
{agent_state['cortex']['total_patterns']}

Циклы сна:
{agent_state['sleep_cycles']}
"""
        self.stats_display.config(state=tk.NORMAL)
        self.stats_display.delete(1.0, tk.END)
        self.stats_display.insert(1.0, translate_block(stats_text))
        self.stats_display.config(state=tk.DISABLED)
        try:
            self.update_external_interaction_display()
        except Exception:
            pass
        
    def update_memory_display(self):
        agent_state = self.agent.get_state()
        hip_info = agent_state['hippocampus']
        ctx_info = agent_state['cortex']
        
        memory_text = f"""Эпизодическая память:
  Опытов: {hip_info['total_experiences']}
  Ср. подкр.: {hip_info.get('avg_reinforcement', 0):.2f}

Семантическая память:
  Паттернов: {ctx_info['total_patterns']}
  Ср. сила: {ctx_info.get('avg_strength', 0):.2f}

Память привычек (IntentMemory):
  Привычек: {len(self.intent_memory.traces) if self.intent_memory else 0}
  
Процесс сна:
  Циклов: {agent_state['sleep_cycles']}
"""

        # Add temporal chains info if available (once)
        chain_info = {}
        try:
            if hasattr(self.sleep_manager, 'chain_memory') and self.sleep_manager.chain_memory:
                chain_info = self.sleep_manager.chain_memory.statistics()
        except Exception:
            chain_info = {}

        memory_text += f"""
🔗 Temporal Chains:
    Ср. стабильность: {chain_info.get('avg_stability', 0):.2f}
"""
        
        self.memory_display.config(state=tk.NORMAL)
        self.memory_display.delete(1.0, tk.END)
        self.memory_display.insert(1.0, translate_block(memory_text))
        self.memory_display.config(state=tk.DISABLED)
    
    def open_inspector(self):
        """Открыть инспектор состояния агента"""
        # Close old inspector if it exists
        if self.inspector_window and self.inspector_window.winfo_exists():
            self.inspector_window.destroy()
        
        inspector = tk.Toplevel(self.root)
        self.inspector_window = inspector
        self._set_title(inspector, "Инспектор состояния агента (NOWA Cognitive)")
        inspector.geometry("900x650")
        
        # Create notebook for tabs
        notebook = ttk.Notebook(inspector)
        notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Tab 1: Experiences (Episodic Memory)
        exp_frame = tk.Frame(notebook)
        notebook.add(exp_frame, text="Эпизодическая память")
        
        exp_text = scrolledtext.ScrolledText(exp_frame, wrap=tk.WORD, font=("Courier", 9))
        exp_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        exp_content = "ЭПИЗОДИЧЕСКАЯ ПАМЯТЬ (Hippocampus)\n"
        exp_content += "=" * 80 + "\n\n"
        
        if self.hippocampus.experiences:
            for i, exp in enumerate(self.hippocampus.experiences, 1):
                exp_content += f"Опыт #{i}\n"
                exp_content += f"  Сигнатура: {exp.path.signature()}\n"
                exp_content += f"  События: {[e.name for e in exp.path.events]}\n"
                exp_content += f"  Интенсивность: {exp.intensity:.2f}\n"
                exp_content += f"  Подкрепление (раз): {exp.reinforcement_count}\n"
                exp_content += f"  Последняя активация: {exp.last_activated}\n"
                exp_content += "-" * 80 + "\n"
        else:
            exp_content += "Опытов нет. Отправьте сообщения агенту.\n"
        
        exp_text.insert(1.0, translate_block(exp_content))
        exp_text.config(state=tk.DISABLED)
        try:
            self._bind_clipboard_shortcuts(exp_text)
        except Exception:
            pass
        
        # Tab 2: Cortical Patterns (Semantic Memory)
        pat_frame = tk.Frame(notebook)
        notebook.add(pat_frame, text="Семантическая память")
        
        pat_text = scrolledtext.ScrolledText(pat_frame, wrap=tk.WORD, font=("Courier", 9))
        pat_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        pat_content = "СЕМАНТИЧЕСКАЯ ПАМЯТЬ (Cortex)\n"
        pat_content += "=" * 80 + "\n\n"
        pat_content += "⚠ Паттерны создаются ТОЛЬКО во время сна (SleepManager)!\n"
        pat_content += "Используйте 🌙 Сон для консолидации опытов в паттерны.\n\n"
        
        if hasattr(self.cortex, 'patterns') and self.cortex.patterns:
            for i, pattern in enumerate(self.cortex.patterns, 1):
                pat_content += f"Паттерн #{i}\n"
                pat_content += f"  Сигнатура: {pattern.signature if hasattr(pattern, 'signature') else pattern}\n"
                pat_content += f"  Сила: {pattern.strength if hasattr(pattern, 'strength') else 'N/A':.3f}\n"
                pat_content += f"  Создан: {pattern.created_at if hasattr(pattern, 'created_at') else 'N/A'}\n"
                pat_content += "-" * 80 + "\n"
        else:
            pat_content += "Паттернов нет. Запустите 🌙 Сон для консолидации.\n"
        
        pat_text.insert(1.0, translate_block(pat_content))
        pat_text.config(state=tk.DISABLED)
        try:
            self._bind_clipboard_shortcuts(pat_text)
        except Exception:
            pass
        
        # Tab 3: Selector State
        selector_frame = tk.Frame(notebook)
        notebook.add(selector_frame, text="Выбор действий")
        
        selector_text = scrolledtext.ScrolledText(selector_frame, wrap=tk.WORD, font=("Courier", 9))
        selector_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        selector_content = "ВЫБОР ДЕЙСТВИЙ (Action Selector)\n"
        selector_content += "=" * 80 + "\n\n"
        selector_content += "⚠ Селектор НЕ ОБУЧАЕТСЯ! Выбор основан на:\n"
        selector_content += "  • Активации опытов в гиппокампе (давление)\n"
        selector_content += "  • Паттернах в кортексе (смещение)\n"
        selector_content += "  • Пороге уверенности (0.7)\n\n"
        
        selector_content += f"Доступные действия ({len(self.selector.actions)}):\n"
        for action in sorted(self.selector.actions):
            selector_content += f"  • {action_label(action)}\n"
        
        selector_content += f"\nПараметры:\n"
        selector_content += f"  Порог уверенности: {self.selector.confidence_threshold:.2f}\n"
        selector_content += f"  Режим работы: Давление + смещение (без весов)\n"
        
        selector_text.insert(1.0, translate_block(selector_content))
        selector_text.config(state=tk.DISABLED)
        try:
            self._bind_clipboard_shortcuts(selector_text)
        except Exception:
            pass
        
        # Tab 4: Sleep & Consolidation
        sleep_frame = tk.Frame(notebook)
        notebook.add(sleep_frame, text="Консолидация")
        
        sleep_text = scrolledtext.ScrolledText(sleep_frame, wrap=tk.WORD, font=("Courier", 9))
        sleep_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        try:
            self._bind_clipboard_shortcuts(sleep_text)
        except Exception:
            pass
        
        agent_state = self.agent.get_state()
        sleep_content = "🌙 КОНСОЛИДАЦИЯ И СОН (Sleep Manager)\n"
        sleep_content += "=" * 80 + "\n\n"
        sleep_content += "📍 Цикл сна: Воспроизведение → Кластеризация → Консолидация → Забывание\n\n"
        
        sleep_content += "📊 СТАТИСТИКА СНА:\n"
        sleep_content += "-" * 80 + "\n"
        sleep_content += f"  Всего циклов сна:                  {agent_state['sleep_cycles']:3d} циклов\n"
        sleep_content += f"  Эпизодов в гиппокампе:            {agent_state['hippocampus']['total_experiences']:3d} опытов\n"
        sleep_content += f"  Паттернов в кортексе:             {agent_state['cortex']['total_patterns']:3d} паттернов\n"
        
        if agent_state['hippocampus']['total_experiences'] > 0:
            ratio = agent_state['cortex']['total_patterns'] / max(agent_state['hippocampus']['total_experiences'], 1)
            sleep_content += f"  Коэффициент консолидации:         {ratio:6.2f}\n"
        
        sleep_content += "\n⚙️  ПРОЦЕСС КОНСОЛИДАЦИИ:\n"
        sleep_content += "-" * 80 + "\n"
        sleep_content += "  1️⃣  Гиппокамп хранит недавние опыты\n"
        sleep_content += "  2️⃣  Во время сна опыты кластеризуются по сходству\n"
        sleep_content += "  3️⃣  Похожие кластеры консолидируются в паттерны\n"
        sleep_content += "  4️⃣  Нестабильные опыты забываются\n"
        sleep_content += "  5️⃣  Селектор использует паттерны для выбора действий\n"
        
        # Add temporal chains information
        sleep_content += "\n🔗 ВРЕМЕННЫЕ ЦЕПОЧКИ (Temporal Chains - Plan B):\n"
        sleep_content += "-" * 80 + "\n"
        try:
            if hasattr(self.sleep_manager, 'chain_memory') and self.sleep_manager.chain_memory:
                chain_info = self.sleep_manager.chain_memory.statistics()
                if chain_info.get('total_chains', 0) > 0:
                    sleep_content += f"  Всего цепочек:                     {chain_info['total_chains']:3d} цепочек\n"
                    sleep_content += f"  Средняя длина цепи:               {chain_info['avg_length']:6.2f} событий\n"
                    sleep_content += f"  Средняя стабильность:             {chain_info['avg_stability']:6.2f}\n"
                    sleep_content += f"  Средний net_affect:                {chain_info['avg_net_affect']:6.2f}\n"
                    if chain_info.get('last_chain_events'):
                        sleep_content += f"  Последняя цепь: {' → '.join(chain_info['last_chain_events'][:4])}...\n"
                else:
                    sleep_content += "  Цепочек ещё нет. Запустите сон после сообщений для формирования.\n"
        except Exception as e:
            sleep_content += f"  Ошибка при получении информации о цепочках: {str(e)}\n"
        
        sleep_text.insert(1.0, translate_block(sleep_content))
        sleep_text.config(state=tk.DISABLED)
        
        # Tab 5: Intent Memory (Habits)
        habits_frame = tk.Frame(notebook)
        notebook.add(habits_frame, text="Привычки (IntentMemory)")
        
        habits_text = scrolledtext.ScrolledText(habits_frame, wrap=tk.WORD, font=("Courier", 9))
        habits_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        habits_content = "ПАМЯТЬ ПРИВЫЧЕК (IntentMemory)\n"
        habits_content += "=" * 80 + "\n\n"
        habits_content += "📋 Привычки — это связи контекст → действие, сформированные из опыта\n"
        habits_content += "   (БЕЗ обучения, только накопление и консолидация)\n\n"
        
        if self.intent_memory and len(self.intent_memory.traces) > 0:
            habits_content += f"СТАТИСТИКА:\n"
            habits_content += f"  Всего привычек (traces): {len(self.intent_memory.traces)}\n"
            
            stats = self.intent_memory.get_stats()
            habits_content += f"\n  По типам действий:\n"
            for intent_type, data in stats['by_intent'].items():
                habits_content += f"    • {intent_type}:\n"
                habits_content += f"        Traces: {data['count']}\n"
                habits_content += f"        Всего strength: {data['total_strength']:.1f}\n"
                habits_content += f"        Средняя strength: {data['avg_strength']:.2f}\n"
            
            habits_content += f"\nДЕТАЛИ ПРИВЫЧЕК:\n"
            habits_content += "-" * 80 + "\n"
            
            # Group by intent type
            by_intent = {}
            for trace_key, trace in self.intent_memory.traces.items():
                if trace.intent_type not in by_intent:
                    by_intent[trace.intent_type] = []
                by_intent[trace.intent_type].append(trace)
            
            for intent_type in sorted(by_intent.keys()):
                traces = by_intent[intent_type]
                habits_content += f"\n🎯 {intent_type}:\n"
                for i, trace in enumerate(traces, 1):
                    habits_content += f"  [{i}] Context: {trace.context_signature}\n"
                    habits_content += f"      Strength: {trace.strength:.1f}\n"
                    habits_content += f"      Recency: {trace.recency:.2f}\n"
                    habits_content += f"      Age: {trace.age_in_seconds():.0f}s\n"
        else:
            habits_content += "Привычек нет. Отправьте сообщения агенту для формирования привычек.\n"
            habits_content += "\nПривычки формируются автоматически при:\n"
            habits_content += "  1. Повторении контекста\n"
            habits_content += "  2. Выборе действия\n"
            habits_content += "  3. Использовании во время сна\n"
        
        habits_text.insert(1.0, translate_block(habits_content))
        habits_text.config(state=tk.DISABLED)
        try:
            self._bind_clipboard_shortcuts(habits_text)
        except Exception:
            pass
        
        # Tab 6: Summary Statistics
        summary_frame = tk.Frame(notebook)
        notebook.add(summary_frame, text="Статистика")
        
        summary_text = scrolledtext.ScrolledText(summary_frame, wrap=tk.WORD, font=("Courier", 9))
        summary_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        summary_content = "📊 СВОДНАЯ СТАТИСТИКА АГЕНТА\n"
        summary_content += "=" * 80 + "\n\n"
        
        # Agent State
        summary_content += "🔍 СОСТОЯНИЕ АГЕНТА:\n"
        summary_content += "-" * 80 + "\n"
        summary_content += f"  👁️  Эпизодических воспоминаний:     {agent_state['hippocampus']['total_experiences']:3d} опытов\n"
        summary_content += f"  🧠 Семантических паттернов:        {agent_state['cortex']['total_patterns']:3d} паттернов\n"
        summary_content += f"  🌙 Циклов консолидации (сна):      {agent_state['sleep_cycles']:3d} циклов\n"
        
        if self.intent_memory:
            summary_content += f"  📋 Привычек (IntentMemory):        {len(self.intent_memory.traces):3d} привычек\n"
        
        if agent_state['hippocampus']['total_experiences'] > 0:
            ratio = agent_state['cortex']['total_patterns'] / max(agent_state['hippocampus']['total_experiences'], 1)
            summary_content += f"  📈 Коэффициент консолидации:      {ratio:6.2f} (паттерны/опыты)\n"
        
        # Hippocampus info
        summary_content += "\n📚 ЭПИЗОДИЧЕСКАЯ ПАМЯТЬ (Гиппокамп):\n"
        summary_content += "-" * 80 + "\n"
        hip_info = agent_state['hippocampus']
        if hip_info['total_experiences'] > 0:
            summary_content += f"  Всего опытов:                      {hip_info['total_experiences']}\n"
            summary_content += f"  Среднее подкрепление:             {hip_info.get('avg_reinforcement', 0):.2f}\n"
            summary_content += f"  Средняя активация:                {hip_info.get('avg_activation', 0):.2f}\n"
            summary_content += f"  Средняя стабильность:             {hip_info.get('avg_stability', 0):.2f}\n"
        else:
            summary_content += "  Опытов нет. Отправьте сообщения агенту.\n"
        
        # Cortex info
        summary_content += "\n🎯 СЕМАНТИЧЕСКАЯ ПАМЯТЬ (Кортекс):\n"
        summary_content += "-" * 80 + "\n"
        ctx_info = agent_state['cortex']
        if ctx_info['total_patterns'] > 0:
            summary_content += f"  Всего паттернов:                   {ctx_info['total_patterns']}\n"
            summary_content += f"  Средняя сила:                     {ctx_info.get('avg_strength', 0):.2f}\n"
        else:
            summary_content += "  Паттернов нет. Запустите 🌙 сон для консолидации.\n"
        
        # Temporal chains
        summary_content += "\n🔗 ВРЕМЕННЫЕ ЦЕПОЧКИ (Temporal Chains):\n"
        summary_content += "-" * 80 + "\n"
        try:
            if hasattr(self.sleep_manager, 'chain_memory') and self.sleep_manager.chain_memory:
                chain_info = self.sleep_manager.chain_memory.statistics()
                if chain_info.get('total_chains', 0) > 0:
                    summary_content += f"  Всего цепочек:                     {chain_info['total_chains']}\n"
                    summary_content += f"  Средняя длина цепи:               {chain_info['avg_length']:.2f} событий\n"
                    summary_content += f"  Средняя стабильность:             {chain_info['avg_stability']:.2f}\n"
                    summary_content += f"  Среднее значение аффекта:         {chain_info['avg_net_affect']:.2f}\n"
                else:
                    summary_content += "  Цепочек нет. Запустите 🌙 сон после нескольких сообщений.\n"
        except Exception:
            summary_content += "  Ошибка при получении информации о цепочках.\n"
        
        # Last action
        summary_content += "\n⚡ ПОСЛЕДНЕЕ ДЕЙСТВИЕ:\n"
        summary_content += "-" * 80 + "\n"
        if self.last_action:
            summary_content += f"  {self.last_action}\n"
        else:
            summary_content += "  Нет действий. Отправьте первое сообщение.\n"
        
        summary_content += "\n💡 ПОДСКАЗКИ:\n"
        summary_content += "-" * 80 + "\n"
        summary_content += "  • Отправьте 3-5 сообщений агенту\n"
        summary_content += "  • Нажмите 🌙 Сон для формирования паттернов и цепочек\n"
        summary_content += "  • Повторите процесс для лучшей консолидации\n"
        
        summary_text.insert(1.0, translate_block(summary_content))
        summary_text.config(state=tk.DISABLED)
        try:
            self._bind_clipboard_shortcuts(summary_text)
        except Exception:
            pass
        
        # Tab 7: Affective State (NEW)
        affect_frame = tk.Frame(notebook)
        notebook.add(affect_frame, text="❤️ Аффективное состояние")
        
        affect_text = scrolledtext.ScrolledText(affect_frame, wrap=tk.WORD, font=("Courier", 9))
        affect_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        try:
            self._bind_clipboard_shortcuts(affect_text)
        except Exception:
            pass
        
        affect_content = "АФФЕКТИВНОЕ СОСТОЯНИЕ (Affective Regulators)\n"
        affect_content += "=" * 80 + "\n\n"
        affect_content += "❤️ Операциональные параметры регуляции поведения (БЕЗ субъективности)\n\n"
        
        affect = self.agent.affect_state
        affect_content += "ТЕКУЩИЕ ПАРАМЕТРЫ:\n"
        affect_content += f"  {tr('Валентность')}:      {affect.valence:6.3f}  [-1.0 … +1.0]\n"
        affect_content += f"  {tr('Активация')}:        {affect.arousal:6.3f}  [0.0 … 2.0]\n"
        affect_content += f"  {tr('Угроза')}:            {affect.threat:6.3f}  [0.0 … 1.0]\n"
        affect_content += f"  {tr('Любопытство')}:    {affect.curiosity:6.3f}  [0.0 … 1.0]\n\n"
        
        affect_content += "ПРОИЗВОДНЫЕ ПОКАЗАТЕЛИ:\n"
        affect_content += f"  Серьезность конфликта:      {affect.conflict_severity():6.3f}  [0.0 до 1.0]\n"
        affect_content += f"  Готовность к адаптации:     {affect.adaptation_readiness():6.3f}  [0.0 до 1.0]\n"
        affect_content += f"  Модификатор давления:       {affect.get_action_pressure_modifier():6.3f}  [0.1 до 2.0]\n\n"

        space = getattr(self.agent, "affective_space", None)
        if space is not None:
            affect_content += "АФФЕКТИВНОЕ ПРОСТРАНСТВО (Phase 4 pre):\n"
            axes = getattr(space, "axes", {})
            for axis_name in (
                "pleasure",
                "pain",
                "arousal",
                "relaxation",
                "attachment",
                "rejection",
                "focus",
                "vulnerability",
            ):
                affect_content += (
                    f"  {axis_label(axis_name)}: {float(axes.get(axis_name, 0.0)):6.3f}  [0.0..1.0]\n"
                )
            try:
                affect_content += f"  Скорость V:     {space.speed():6.3f}\n"
                affect_content += f"  Конфликт осей:  {space.axis_conflict():6.3f}\n"
            except Exception:
                pass
            affect_content += "\n"

        sem_layer = getattr(self.agent, "semantic_emotions", None)
        if sem_layer is not None:
            affect_content += "SEMANTIC EMOTIONS (Phase 4.1):\n"
            try:
                bg_snapshot = {}
                bg = getattr(self.agent, "affective_background", None)
                if bg is not None:
                    bg_snapshot = bg.snapshot()
                summary = translate_block(sem_layer.describe_brief(space=space, background=bg_snapshot))
                affect_content += f"  Summary: {summary}\n"
            except Exception:
                pass
            sem_items = []
            try:
                sem_items = sem_layer.snapshot()
            except Exception:
                sem_items = []
            if sem_items:
                sem_items = sorted(sem_items, key=lambda item: float(item.get("activation", 0.0)), reverse=True)
                for item in sem_items:
                    name = emotion_label(item.get("emotion", "unknown"))
                    activation = float(item.get("activation", 0.0))
                    stability = float(item.get("stability", 0.0))
                    obsessive = bool(item.get("obsessive", False))
                    affect_content += f"  {name:14s} act:{activation:6.3f}  st:{stability:6.3f}  obs:{obsessive}\n"
            else:
                affect_content += "  (none)\n"
            affect_content += "\n"

        stability_layer = getattr(self.agent, "stability_monitor", None)
        if stability_layer is not None:
            affect_content += "STABILITY MONITORING (Phase 4.5):\n"
            try:
                st = stability_layer.snapshot()
                affect_content += f"  index: {float(st.get('stability_index', 1.0)):6.3f}\n"
                affect_content += f"  recommendation: {st.get('recommendation', 'none')}\n"
                flags = st.get("drift_flags", {}) or {}
                affect_content += (
                    "  flags: "
                    f"reg={bool(flags.get('regulation_overuse', False))}, "
                    f"bg={bool(flags.get('background_drift', False))}, "
                    f"nm={bool(flags.get('neuromodulator_drift', False))}, "
                    f"lock={bool(flags.get('dominant_emotion_lock', False))}, "
                    f"out={bool(flags.get('outlook_bias', False))}\n"
                )
                metrics = st.get("metrics", {}) or {}
                affect_content += (
                    "  metrics: "
                    f"r4.4={float(metrics.get('regulation_activation_rate', 0.0)):.3f}, "
                    f"bg_mean={float(metrics.get('mean_background_anxiety', 0.0)):.3f}, "
                    f"esc_ratio={float(metrics.get('escalating_ratio', 0.0)):.3f}\n"
                )
            except Exception:
                affect_content += "  (none)\n"
            affect_content += "\n"

        value_layer = getattr(self.agent, "value_layer", None)
        if value_layer is not None:
            affect_content += "СЛОЙ ЦЕННОСТИ (Phase 5.0):\n"
            try:
                vl = value_layer.snapshot()
                affect_content += f"  Оценка состояния: {float(vl.get('value', 0.0)):6.3f}\n"
                affect_content += f"  Ошибка прогноза (TD): {float(vl.get('last_td_error', 0.0)):6.3f}\n"
                affect_content += f"  Сдвиг дофамина от TD: {float(vl.get('last_dopamine_delta', 0.0)):6.3f}\n"
                affect_content += (
                    f"  Известных состояний: {int(vl.get('state_count', 0))}/{int(vl.get('max_states', 0))}, "
                    f"обновлений: {int(vl.get('update_count', 0))}\n"
                )
                state_key = str(vl.get("last_state_key", ""))
                if state_key:
                    affect_content += f"  Ключ последнего состояния: {state_key[:16]}...\n"
            except Exception:
                affect_content += "  (none)\n"
            affect_content += "\n"
        
        affect_content += "АССОЦИАЦИИ С СУЩНОСТЯМИ:\n"
        if affect.attachment or affect.affinity or affect.aversion:
            affect_content += f"  Привязанность: {dict(affect.attachment)}\n"
            affect_content += f"  Позитивные:    {dict(affect.affinity)}\n"
            affect_content += f"  Негативные:    {dict(affect.aversion)}\n"
        else:
            affect_content += "  Нет записанных ассоциаций\n"
        
        runtime = getattr(self, "autonomous_runtime", None)
        if runtime is not None:
            affect_content += "АВТОНОМНЫЙ ОРГАНИЗМ (Spec v1):\n"
            try:
                auto_snapshot = runtime.snapshot()
                auto_energy = auto_snapshot.get("energy", {}) or {}
                auto_drives = auto_snapshot.get("drives", {}) or {}
                auto_failures = list(auto_snapshot.get("failures", []) or [])
                auto_real_errors, auto_warnings = self._split_autonomous_failures(auto_failures)
                last_tick = runtime.tick_history[-1] if runtime.tick_history else {}
                mode_key = str(last_tick.get("physiology_mode") or "idle")
                mode_text = mode_label(mode_key)
                affect_content += f"  тики: {int(auto_snapshot.get('tick_count', 0))}\n"
                affect_content += (
                    f"  ошибки(критичные): {len(auto_real_errors)}, "
                    f"предупреждения: {len(auto_warnings)}\n"
                )
                affect_content += (
                    f"  энергия: {float(auto_energy.get('energy', 0.0)):.3f}, "
                    f"энергетическая_усталость: {float(auto_energy.get('fatigue', 0.0)):.3f}, "
                    f"подавление_циклов: {bool(auto_energy.get('suppress_internal_cycles', False))}\n"
                )
                if auto_drives:
                    sorted_drives = sorted(
                        auto_drives.items(),
                        key=lambda item: float(item[1]),
                        reverse=True,
                    )
                    top = ", ".join([f"{drive_label(k)}:{float(v):.2f}" for k, v in sorted_drives[:3]])
                    affect_content += f"  ведущие драйвы: {top}\n"
                affect_content += (
                    f"  последний активный драйв: {drive_label(last_tick.get('active_drive', 'none'))}, "
                    f"внутренний_цикл: {bool(last_tick.get('internal_cycle_triggered', False))}, "
                    f"речь: {bool(last_tick.get('speech_event', False))}\n"
                )
                affect_content += (
                    f"  физиология: режим={mode_text}, "
                    f"когнитивная_нагрузка={float(last_tick.get('cognitive_load', 0.0)):.3f}\n"
                )
            except Exception:
                affect_content += "  (none)\n"
            affect_content += "\n"
        # Get self-model analysis
        affect_content += "\n" + "=" * 80 + "\n"
        affect_content += "АНАЛИЗ САМОРЕФЛЕКСИИ (Self-Model):\n\n"
        
        try:
            readiness = self.self_model.get_regulatory_readiness_report()
            affect_content += f"Готовность системы: {readiness['readiness_level'].upper()}\n"
            affect_content += f"  Основной ингибитор: {readiness['primary_inhibitor']}\n"
            affect_content += f"  Рекомендация: {readiness['recommendation']}\n\n"
            
            limiting = self.self_model.report_limiting_factors()
            affect_content += "ОГРАНИЧИВАЮЩИЕ ФАКТОРЫ:\n"
            if limiting.get("status") == "no_limiting_factors":
                affect_content += "  Нет ограничивающих факторов\n"
            else:
                for factor, desc in limiting.items():
                    affect_content += f"  • {factor}: {desc}\n"
            
            affect_content += "\n"
            enabling = self.self_model.report_enabling_factors()
            affect_content += "ОБЛЕГЧАЮЩИЕ ФАКТОРЫ:\n"
            if enabling.get("status") == "no_enabling_factors":
                affect_content += "  Нет облегчающих факторов\n"
            else:
                for factor, desc in enabling.items():
                    affect_content += f"  • {factor}: {desc}\n"
        except Exception as e:
            affect_content += f"Ошибка при анализе: {str(e)}\n"
        
        affect_content += "\n" + "=" * 80 + "\n"
        affect_content += "ОПИСАНИЕ ОПЕРАЦИОНАЛЬНОГО СОСТОЯНИЯ:\n"
        affect_content += self.self_model.describe_operational_state() + "\n"
        
        affect_text.insert(1.0, translate_block(affect_content))
        affect_text.config(state=tk.DISABLED)

        # Ensure standard clipboard shortcuts work across the inspector dialog
        try:
            self._bind_clipboard_shortcuts_recursive(inspector)
        except Exception:
            pass
        self._localize_widget(inspector)
        
    def clear_chat(self):
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.delete(1.0, tk.END)
        self.chat_display.config(state=tk.DISABLED)
        self.input_field.delete(0, tk.END)
    
    def save_state(self):
        """Сохранить состояние агента"""
        try:
            filepath = self.storage.save_agent(
                self.hippocampus,
                self.cortex,
                self.selector,
                affect_state=self.agent.affect_state,
                temporal=self.agent.temporal,
                sleep_manager=self.sleep_manager,
                neuromodulators=getattr(self.agent, 'neuromodulators', None),
                affective_persistence=getattr(self.agent, 'affective_persistence', None),
                affective_background=getattr(self.agent, 'affective_background', None),
                affective_space=getattr(self.agent, 'affective_space', None),
                semantic_emotions=getattr(self.agent, 'semantic_emotions', None),
                emotional_memory=getattr(self.agent, 'emotional_memory', None),
                emotional_expectations=getattr(self.agent, 'emotional_expectations', None),
                emotional_regulation=getattr(self.agent, 'emotional_regulation', None),
                emotional_stability=getattr(self.agent, 'stability_monitor', None),
                value_layer=getattr(self.agent, 'value_layer', None),
                conflict_arbitration=getattr(self.agent, 'conflict_arbitration', None),
                intent_memory=getattr(self.agent, 'intent_memory', None),
                agent=self.agent
            )
            self.add_to_chat(f"Состояние сохранено: {filepath.split('/')[-1]}", "system")
            messagebox.showinfo(tr("Успех"), tr("Состояние агента сохранено!"))
        except Exception as e:
            messagebox.showerror(tr("Ошибка"), tr("Ошибка при сохранении: {error}", error=str(e)))
    
    def load_state(self):
        """Загрузить состояние агента"""
        saves = self.storage.get_save_files()
        if not saves:
            messagebox.showwarning(tr("Нет сохранений"), tr("Не найдены сохраненные файлы"))
            return
        
        # Создать окно выбора
        load_window = tk.Toplevel(self.root)
        self.load_window = load_window
        self._set_title(load_window, "Загрузить состояние")
        load_window.geometry("400x300")
        
        tk.Label(load_window, text="Выберите сохранение:", font=("Helvetica", 11, "bold")).pack(pady=10)
        
        listbox = tk.Listbox(load_window, font=("Helvetica", 10), height=10)
        listbox.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        for save in saves:
            listbox.insert(tk.END, f"{save['name']} ({save['modified']})")
        
        def load_selected():
            selection = listbox.curselection()
            if not selection:
                messagebox.showwarning(tr("Ошибка"), tr("Выберите сохранение"))
                return
            
            try:
                selected_save = saves[selection[0]]
                
                # Debug: print before load
                print(f"[LOAD DEBUG] Before load:")
                print(f"  sleep_manager.consolidation_cycles: {self.sleep_manager.consolidation_cycles}")
                print(f"  sleep_manager.chain_memory.chains: {len(self.sleep_manager.chain_memory.chains)}")
                
                timestamp = self.storage.load_agent(
                    self.hippocampus,
                    self.cortex,
                    self.selector,
                    selected_save['path'],
                    affect_state=self.agent.affect_state,
                    temporal=self.agent.temporal,
                    sleep_manager=self.sleep_manager,
                    neuromodulators=getattr(self.agent, 'neuromodulators', None),
                    affective_persistence=getattr(self.agent, 'affective_persistence', None),
                    affective_background=getattr(self.agent, 'affective_background', None),
                    affective_space=getattr(self.agent, 'affective_space', None),
                    semantic_emotions=getattr(self.agent, 'semantic_emotions', None),
                    emotional_memory=getattr(self.agent, 'emotional_memory', None),
                    emotional_expectations=getattr(self.agent, 'emotional_expectations', None),
                    emotional_regulation=getattr(self.agent, 'emotional_regulation', None),
                    emotional_stability=getattr(self.agent, 'stability_monitor', None),
                    value_layer=getattr(self.agent, 'value_layer', None),
                    conflict_arbitration=getattr(self.agent, 'conflict_arbitration', None),
                    intent_memory=getattr(self.agent, 'intent_memory', None),
                    agent=self.agent
                )
                
                # Debug: print after load
                print(f"[LOAD DEBUG] After load:")
                print(f"  sleep_manager.consolidation_cycles: {self.sleep_manager.consolidation_cycles}")
                print(f"  sleep_manager.chain_memory.chains: {len(self.sleep_manager.chain_memory.chains)}")
                
                # Close inspector to force refresh with new data
                if self.inspector_window and self.inspector_window.winfo_exists():
                    self.inspector_window.destroy()

                # If neuromodulators were restored into sleep_manager, attach to agent
                try:
                    if hasattr(self.sleep_manager, 'neuromodulators'):
                        self.agent.neuromodulators = self.sleep_manager.neuromodulators
                except Exception:
                    pass
                self._init_autonomous_runtime()
                
                self.add_to_chat(f"Состояние загружено из {selected_save['name']}", "system")
                self.update_memory_display()
                self.update_affect_display()
                self.update_stats(self.last_action or "no action")
                self.update_temporal_display()
                messagebox.showinfo(tr("Успех"), tr("Состояние агента загружено!"))
                load_window.destroy()
            except Exception as e:
                messagebox.showerror(tr("Ошибка"), tr("Ошибка при загрузке: {error}", error=str(e)))
        
        load_btn = tk.Button(
            load_window,
            text="Загрузить",
            command=load_selected,
            bg="#27ae60",
            fg="white",
            font=("Helvetica", 10, "bold")
        )
        load_btn.pack(pady=10)

        # Enable standard clipboard shortcuts inside this dialog
        try:
            self._bind_clipboard_shortcuts_recursive(load_window)
        except Exception:
            pass
        self._localize_widget(load_window)
    
    def save_chat(self):
        """Сохранить историю диалога"""
        try:
            # Получить текст из чата
            chat_text = self.chat_display.get(1.0, tk.END)
            messages = [line.strip() for line in chat_text.split('\n') if line.strip()]
            
            if not messages:
                messagebox.showwarning(tr("Предупреждение"), tr("Диалог пуст"))
                return
            
            filepath = self.storage.save_chat_history(messages)
            self.add_to_chat(f"Диалог сохранен: {filepath.split('/')[-1]}", "system")
            messagebox.showinfo(tr("Успех"), tr("История диалога сохранена!"))
        except Exception as e:
            messagebox.showerror(tr("Ошибка"), tr("Ошибка при сохранении: {error}", error=str(e)))
    
    def load_dataset_dialog(self):
        """Открыть окно загрузки датасета"""
        load_window = tk.Toplevel(self.root)
        self.dataset_window = load_window
        self._set_title(load_window, "Загрузить датасет")
        load_window.geometry("500x400")
        
        # Заголовок
        title_label = tk.Label(
            load_window,
            text="📂 Загрузка опыта из датасетов",
            font=("Helvetica", 12, "bold"),
            bg="#2c3e50",
            fg="#ecf0f1"
        )
        title_label.pack(fill=tk.X, padx=0, pady=0)
        
        main_frame = tk.Frame(load_window)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        
        # Опция 1: Загрузить из папки datasets
        opt1_frame = tk.LabelFrame(main_frame, text="Загрузить из папки datasets", font=("Helvetica", 10, "bold"), padx=10, pady=10)
        opt1_frame.pack(fill=tk.X, pady=10)
        
        opt1_label = tk.Label(
            opt1_frame,
            text="Загрузит все JSON файлы из папки datasets",
            font=("Helvetica", 9),
            fg="#555"
        )
        opt1_label.pack(anchor=tk.W, pady=5)
        
        def load_from_datasets_folder():
            try:
                experiences = load_experiences_from_datasets_folder()
                self._add_experiences_to_agent(experiences)
                self.add_to_chat(f"✅ Загружено {len(experiences)} опытов из папки datasets", "system")
                messagebox.showinfo(tr("Успех"), tr("Загружено {n} опытов из датасетов!", n=len(experiences)))
                load_window.destroy()
            except Exception as e:
                messagebox.showerror(tr("Ошибка"), tr("Ошибка при загрузке: {error}", error=str(e)))
        
        btn1 = tk.Button(
            opt1_frame,
            text="Загрузить из datasets",
            command=load_from_datasets_folder,
            bg="#27ae60",
            fg="white",
            font=("Helvetica", 10, "bold"),
            width=30
        )
        btn1.pack(pady=10)
        
        # Опция 2: Выбрать конкретный файл
        opt2_frame = tk.LabelFrame(main_frame, text="Загрузить конкретный файл", font=("Helvetica", 10, "bold"), padx=10, pady=10)
        opt2_frame.pack(fill=tk.X, pady=10)
        
        opt2_label = tk.Label(
            opt2_frame,
            text="Выберите JSON файл датасета вручную",
            font=("Helvetica", 9),
            fg="#555"
        )
        opt2_label.pack(anchor=tk.W, pady=5)
        
        def load_from_file():
            filepath = filedialog.askopenfilename(
                title=tr("Выберите JSON файл датасета"),
                filetypes=[(tr("JSON files"), "*.json"), (tr("All files"), "*.*")]
            )
            
            if filepath:
                try:
                    experiences = load_experience_from_dataset(filepath)
                    self._add_experiences_to_agent(experiences)
                    filename = filepath.split('\\')[-1]
                    self.add_to_chat(f"✅ Загружено {len(experiences)} опытов из {filename}", "system")
                    messagebox.showinfo(tr("Успех"), tr("Загружено {n} опытов из файла!", n=len(experiences)))
                    load_window.destroy()
                except Exception as e:
                    messagebox.showerror(tr("Ошибка"), tr("Ошибка при загрузке: {error}", error=str(e)))
        
        btn2 = tk.Button(
            opt2_frame,
            text="Выбрать файл",
            command=load_from_file,
            bg="#3498db",
            fg="white",
            font=("Helvetica", 10, "bold"),
            width=30
        )
        btn2.pack(pady=10)
        
        # Опция 3: Выбрать директорию
        opt3_frame = tk.LabelFrame(main_frame, text="Загрузить из директории", font=("Helvetica", 10, "bold"), padx=10, pady=10)
        opt3_frame.pack(fill=tk.X, pady=10)
        
        opt3_label = tk.Label(
            opt3_frame,
            text="Выберите папку с JSON файлами датасетов",
            font=("Helvetica", 9),
            fg="#555"
        )
        opt3_label.pack(anchor=tk.W, pady=5)
        
        def load_from_directory():
            directory = filedialog.askdirectory(title=tr("Выберите папку с датасетами"))
            
            if directory:
                try:
                    experiences = load_experiences_from_directory(directory)
                    self._add_experiences_to_agent(experiences)
                    self.add_to_chat(f"✅ Загружено {len(experiences)} опытов из директории", "system")
                    messagebox.showinfo(tr("Успех"), tr("Загружено {n} опытов из директории!", n=len(experiences)))
                    load_window.destroy()
                except Exception as e:
                    messagebox.showerror(tr("Ошибка"), tr("Ошибка при загрузке: {error}", error=str(e)))
        
        btn3 = tk.Button(
            opt3_frame,
            text="Выбрать папку",
            command=load_from_directory,
            bg="#9b59b6",
            fg="white",
            font=("Helvetica", 10, "bold"),
            width=30
        )
        btn3.pack(pady=10)

        # Enable standard clipboard shortcuts inside this dialog
        try:
            self._bind_clipboard_shortcuts_recursive(load_window)
        except Exception:
            pass
        self._localize_widget(load_window)
    
    def _add_experiences_to_agent(self, experiences):
        """Добавить загруженные опыты в память агента"""
        if not experiences:
            return
        
        for experience in experiences:
            # Добавить в эпизодическую память через hippocampus
            # experience.path уже содержит контекст и действие
            intensity = experience.intensity if hasattr(experience, 'intensity') else 1.0
            
            # Создаем consequence event для завершения опыта
            consequence = Event("success", EventType.CONSEQUENCE)
            
            self.hippocampus.store(experience.path, consequence=consequence, intensity=intensity)
            
            # Если есть подкрепление в исходных данных, усилить
            if hasattr(experience, 'reinforcement_count') and experience.reinforcement_count > 0:
                for _ in range(experience.reinforcement_count):
                    self.hippocampus.reinforce(experience.path, consequence=consequence, intensity=intensity)
        
        # Обновить отображение памяти
        self.update_memory_display()
        
        # Логирование
        print(f"Добавлено {len(experiences)} опытов в память агента")
    
    def add_to_chat_history(self, message):
        """Добавить сообщение в историю"""
        self.chat_history.append(message)
    
    def open_sleep_dialog(self, default_cycles=3):
        """Открыть окно управления сном и консолидацией"""
        sleep_window = tk.Toplevel(self.root)
        self.sleep_window = sleep_window
        self._set_title(sleep_window, "🌙 Консолидация памяти (Сон)")
        sleep_window.geometry("700x700")
        sleep_window.resizable(True, True)
        
        # Заголовок
        title_label = tk.Label(
            sleep_window,
            text="🌙 Консолидация опытов в паттерны",
            font=("Helvetica", 12, "bold"),
            bg="#2c3e50",
            fg="#ecf0f1"
        )
        title_label.pack(fill=tk.X, padx=0, pady=0)
        
        # Основной фрейм с контентом
        content_frame = tk.Frame(sleep_window, bg="white")
        content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        main_frame = content_frame
        
        # Инструкция
        info_label = tk.Label(
            main_frame,
            text="🧠 Во время сна опыты консолидируются в семантические паттерны.\nЭто ЕДИНСТВЕННЫЙ механизм обучения в NOWA!",
            font=("Helvetica", 10),
            justify=tk.LEFT,
            bg="white",
            fg="#27ae60"
        )
        info_label.pack(anchor=tk.W, pady=(0, 15))
        
        # Статистика ДО сна
        before_frame = tk.LabelFrame(main_frame, text="📊 Состояние памяти", font=("Helvetica", 10, "bold"), padx=10, pady=10, bg="white")
        before_frame.pack(fill=tk.X, pady=10)
        
        agent_state = self.agent.get_state()
        before_text = scrolledtext.ScrolledText(
            before_frame,
            height=6,
            width=75,
            wrap=tk.WORD,
            state=tk.DISABLED,
            bg="#ffffff",
            font=("Courier", 9)
        )
        before_text.pack(fill=tk.BOTH, expand=False)
        
        def update_state_display():
            """Обновить отображение состояния"""
            current_state = self.agent.get_state()
            before_text.config(state=tk.NORMAL)
            before_text.delete(1.0, tk.END)
            
            content = f"""Эпизодических воспоминаний: {current_state['hippocampus']['total_experiences']}
Семантических паттернов: {current_state['cortex']['total_patterns']}
Циклов сна: {current_state['sleep_cycles']}
Средняя интенсивность опыта: {current_state['hippocampus'].get('avg_intensity', 'N/A')}"""
            
            before_text.insert(1.0, translate_block(content))
            before_text.config(state=tk.DISABLED)
        
        update_state_display()
        
        # Параметры сна
        params_frame = tk.LabelFrame(main_frame, text="⚙️ Параметры консолидации", font=("Helvetica", 10, "bold"), padx=10, pady=10, bg="white")
        params_frame.pack(fill=tk.X, pady=10)
        
        tk.Label(params_frame, text="Количество циклов сна:", font=("Helvetica", 9), bg="white").pack(anchor=tk.W, pady=5)
        cycles_var = tk.IntVar(value=default_cycles)
        cycles_spinbox = tk.Spinbox(params_frame, from_=1, to=10, textvariable=cycles_var, width=10, font=("Helvetica", 9))
        cycles_spinbox.pack(anchor=tk.W, pady=5)
        
        cycles_label = tk.Label(
            params_frame,
            text="(Каждый цикл: replay TD/BG → decay/normalize → кластеризация → консолидация)",
            font=("Helvetica", 8),
            fg="#555",
            bg="white"
        )
        cycles_label.pack(anchor=tk.W, pady=5)
        
        # Результаты консолидации
        results_frame = tk.LabelFrame(main_frame, text="📈 Результаты консолидации", font=("Helvetica", 10, "bold"), padx=10, pady=10, bg="white")
        results_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        results_text = scrolledtext.ScrolledText(
            results_frame,
            height=6,
            width=75,
            wrap=tk.WORD,
            state=tk.DISABLED,
            bg="#ffffff",
            font=("Courier", 9)
        )
        results_text.pack(fill=tk.BOTH, expand=True)
        
        # Кнопки внизу окна
        button_frame = tk.Frame(sleep_window, bg="white")
        button_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=10, padx=10)
        
        def run_sleep():
            cycles = cycles_var.get()
            
            # Отключаем кнопку во время сна
            sleep_btn.config(state=tk.DISABLED)
            cycles_spinbox.config(state=tk.DISABLED)
            
            results_text.config(state=tk.NORMAL)
            results_text.delete(1.0, tk.END)
            results_text.insert(tk.END, tr("💤 Запуск {cycles} цикла(ов) консолидации...", cycles=cycles) + "\n\n")
            results_text.config(state=tk.DISABLED)
            sleep_window.update()
            
            try:
                # Запускаем консолидацию
                stats = self.agent.sleep(cycles=cycles)
                
                # Обновляем состояние в верхнем окне
                update_state_display()
                
                # Получаем новое состояние
                new_state = self.agent.get_state()
                
                results_text.config(state=tk.NORMAL)
                results_text.delete(1.0, tk.END)
                
                output = "✅ КОНСОЛИДАЦИЯ ЗАВЕРШЕНА\n"
                output += "=" * 75 + "\n\n"
                
                # Статистика
                output += "РЕЗУЛЬТАТЫ:\n"
                output += f"  • Кандидатов в replay: {stats.get('total_candidates', 0)}\n"
                output += f"  • Реплеев выполнено: {stats.get('total_replays', 0)}\n"
                output += f"  • Циклов с блокировкой replay: {stats.get('total_replay_blocked', 0)}\n"
                output += f"  • Оффлайн ΔV (сумма): {float(stats.get('total_value_delta', 0.0)):.4f}\n"
                output += f"  • Оффлайн ΔW (сумма): {float(stats.get('total_weight_delta', 0.0)):.4f}\n"
                output += f"  • Кластеров создано: {stats.get('total_clusters', 0)}\n"
                output += f"  • Паттернов консолидировано: {stats.get('total_patterns', 0)}\n"
                output += f"  • Нестабильных опытов забыто: {stats.get('total_forgotten', 0)}\n"
                output += f"  • Циклов с decay: {stats.get('decay_applied_cycles', 0)}\n"
                output += f"  • Циклов с normalization: {stats.get('normalization_applied_cycles', 0)}\n"
                output += f"  • Sleep update count: {int(stats.get('sleep_update_count', 0))}\n"
                output += f"  • Последняя дисперсия Value: {float(stats.get('last_value_variance', 0.0)):.4f}\n"
                output += f"  • Value variance ratio: {float(stats.get('value_variance_ratio', 0.0)):.4f}\n"
                output += f"  • Средний ACh за цикл: {float(stats.get('mean_ach_during_cycle', 0.0)):.4f}\n"
                output += f"  • Средний ACh над baseline: {float(stats.get('mean_ach_above_baseline', 0.0)):.4f}\n"
                
                output += "\nОБНОВЛЕННОЕ СОСТОЯНИЕ:\n"
                output += f"  • Эпизодических воспоминаний: {new_state['hippocampus']['total_experiences']}\n"
                output += f"  • Семантических паттернов: {new_state['cortex']['total_patterns']}\n"
                output += f"  • Всего циклов сна: {new_state['sleep_cycles']}\n"
                
                replay_state = new_state.get("sleep_replay", {}) or {}
                output += "\nReplay-состояние последнего цикла:\n"
                output += f"  • Блокировка replay: {bool(replay_state.get('replay_blocked', False))}\n"
                output += f"  • Отобрано эпизодов: {int(replay_state.get('replay_selected', 0))}\n"
                output += f"  • Выполнено replay: {int(replay_state.get('replays', 0))}\n"
                output += f"  • Value variance: {float(replay_state.get('value_variance', 0.0)):.4f}\n"
                
                results_text.insert(tk.END, translate_block(output))
                results_text.config(state=tk.DISABLED)
                
                # Обновляем главное окно
                self.update_memory_display()
                self.update_stats(self.last_action or "нет")
                self.update_affect_display()
                self.update_temporal_display()
                self.add_to_chat(
                    tr(
                        "✅ Консолидация завершена: {cycles} цикл(ов), {patterns} паттернов",
                        cycles=cycles,
                        patterns=new_state["cortex"]["total_patterns"],
                    ),
                    "system",
                )
                
            except Exception as e:
                results_text.config(state=tk.NORMAL)
                results_text.delete(1.0, tk.END)
                results_text.insert(tk.END, tr("❌ Ошибка при консолидации:") + f"\n{str(e)}")
                results_text.config(state=tk.DISABLED)
                messagebox.showerror(tr("Ошибка"), tr("Ошибка при консолидации: {error}", error=str(e)))
            finally:
                sleep_btn.config(state=tk.NORMAL)
                cycles_spinbox.config(state=tk.NORMAL)
        
        sleep_btn = tk.Button(
            button_frame,
            text="🌙 Начать консолидацию",
            command=run_sleep,
            bg="#8e44ad",
            fg="white",
            font=("Helvetica", 10, "bold"),
            width=30
        )
        sleep_btn.pack(side=tk.LEFT, padx=5)
        
        close_btn = tk.Button(
            button_frame,
            text="Закрыть",
            command=sleep_window.destroy,
            bg="#95a5a6",
            fg="white",
            font=("Helvetica", 10, "bold"),
            width=30
        )
        close_btn.pack(side=tk.LEFT, padx=5)

        # Enable standard clipboard shortcuts inside this dialog
        try:
            self._bind_clipboard_shortcuts_recursive(sleep_window)
        except Exception:
            pass
        self._localize_widget(sleep_window)
    
    def open_auto_training_dialog(self):
        """❌ Deprecated - использует невалидный механизм обучения"""
        messagebox.showwarning(
            tr("⚠️ Функция устарела"),
            "\n\n".join(
                [
                    tr("Автоматическая тренировка селектора больше не поддерживается."),
                    tr("В NOWA обучение происходит ТОЛЬКО во время сна через консолидацию."),
                    tr("Используйте вместо этого:"),
                    tr("1. 🌙 Сон - консолидирует опыты в паттерны"),
                    tr("2. Инспектор - смотрите состояние памяти"),
                    tr("Селектор действий НЕ имеет весов - он выбирает на основе давления активации!"),
                ]
            ),
        )


def main(argv=None):
    import argparse
    import sys

    raw = list(sys.argv[1:] if argv is None else argv)
    preview = None
    if "--lang" in raw:
        index = raw.index("--lang")
        if index + 1 < len(raw):
            preview = raw[index + 1]
    set_language(resolve_lang(preview))
    parser = argparse.ArgumentParser(description=tr("Run the NOWA cognitive interface"))
    parser.add_argument(
        "--lang",
        choices=("en", "ru"),
        default=None,
        help=tr("UI language. Overrides NOWA_LANG."),
    )
    args = parser.parse_args(argv)
    # Help text above was resolved before --lang was known. Pin the chosen language now.
    set_language(resolve_lang(args.lang))
    root = tk.Tk()
    gui = NOWAGUI(root, lang=args.lang)
    root.mainloop()
    return gui


if __name__ == "__main__":
    main()

